from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction
from io import BytesIO
from docx import Document
from random import sample, shuffle
import re, zipfile, os
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from .models import Subject, Question, Choice, Exam, ExamItem, ExamChoice
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.text.paragraph import Paragraph
from docx.table import Table
from docx.oxml.ns import qn

def home(request):
    subjects = Subject.objects.all()
    return render(request, 'home.html', {'subjects': subjects})

def login(request):
    return render(request, 'login.html')

@require_http_methods(["GET", "POST"])
def import_docx(request):
    subjects = Subject.objects.all()
    if request.method == "POST":
        file = request.FILES.get("file")
        if not file:
            messages.error(request, "Hãy chọn file .docx (Template).")
            return redirect("import_docx")

        raw = file.read()

        # 1) Parse Template.docx (đọc text + image, xử lý nhãn/giá trị xuống dòng)
        try:
            meta, items = _parse_template_docx(raw)
        except Exception as e:
            messages.error(request, f"Lỗi đọc Template.docx: {e}")
            return redirect("import_docx")

        # 2) Map Subject từ header
        subj_raw = (meta['subject'] or '').strip()
        subject = (Subject.objects.filter(code__iexact=subj_raw).first()
                   or Subject.objects.filter(name__iexact=subj_raw).first())
        if not subject:
            messages.error(request, f"Subject '{subj_raw}' không tồn tại. Tạo trước trong admin.")
            return redirect("import_docx")

        # 3) Kiểm tra mã đề
        exam_code = (meta['topic_code'] or '').strip()
        if not exam_code:
            messages.error(request, "Thiếu Topic code (Mã đề).")
            return redirect("import_docx")
        if Exam.objects.filter(code=exam_code).exists():
            messages.error(request, f"Mã đề '{exam_code}' đã tồn tại.")
            return redirect("import_docx")

        # Helper: lưu file đúng tên (overwrite nếu trùng tên)
        def save_binary_exact(filename: str, data: bytes) -> str:
            # filename chỉ là tên file (không path); default_storage đang trỏ MEDIA_ROOT
            if default_storage.exists(filename):
                default_storage.delete(filename)
            return default_storage.save(filename, ContentFile(data))

        warns = []
        with transaction.atomic():
            created_qs = []

            # 4) Tạo Question/Choice và LƯU ẢNH trực tiếp từ docx theo quy tắc tên
            for q in items:
                qobj = Question.objects.create(
                    subject=subject,
                    text=q.get("text") or "",
                    mark=q.get("mark") or 1.0,
                    unit=q.get("unit") or ""
                )

                # Lưu ảnh (nếu parser có): q["image"] (bytes), q["image_name"] (tên gốc trong docx)
                blob = q.get("image")
                orig = (q.get("image_name") or "").strip()
                if blob:
                    # Lấy phần mở rộng từ tên gốc; fallback .jpg
                    ext = os.path.splitext(orig)[1].lower() or '.jpg'
                    if ext not in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}:
                        ext = '.jpg'

                    # QN từ tài liệu; nếu thiếu, dùng thứ tự hiện tại
                    qn = q.get('id') or (len(created_qs) + 1)
                    # Tên file theo yêu cầu: subjectId_examCode_Q{soThuTu}.{ext}
                    safe_exam = re.sub(r'[^A-Za-z0-9_-]+', '-', exam_code)
                    filename = f"{subject.id}_{safe_exam}_Q{qn}{ext}"

                    saved = save_binary_exact(filename, blob)
                    # ImageField lưu relative path trong MEDIA_ROOT
                    qobj.image.name = saved
                    qobj.save(update_fields=["image"])

                # Lưu lựa chọn A–D
                for label, text in (q.get("choices") or []):
                    Choice.objects.create(
                        question=qobj, label=label, text=text,
                        is_correct=(label == q.get("answer"))
                    )

                created_qs.append((qobj, bool(q.get("mix"))))

            # 5) Tạo Exam + ExamItem + ExamChoice (trộn đáp án nếu mix=True)
            exam = Exam.objects.create(
                code=exam_code,
                subject=subject,
                duration_minutes=60,
                question_count=len(created_qs),
            )
            for idx, (qobj, mix) in enumerate(created_qs, start=1):
                item = ExamItem.objects.create(
                    exam=exam, question=qobj, order=idx, mix_choices=mix
                )
                opts = list(qobj.choices.order_by('label'))
                if mix:
                    from random import shuffle
                    shuffle(opts)
                labels = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                for i, opt in enumerate(opts):
                    ExamChoice.objects.create(
                        item=item, label=labels[i], text=opt.text, is_correct=opt.is_correct
                    )

        msg = f"Đã import {len(created_qs)} câu hỏi cho {subject}. Tạo đề '{exam.code}'."
        if '_num_quiz_mismatch' in meta:
            exp, found = meta['_num_quiz_mismatch']
            warns.append(f"Số câu trong header: {exp}; thực tế: {found}.")
        messages.success(request, msg)
        if warns:
            messages.warning(request, "Cảnh báo:\n" + "\n".join(warns))
        return redirect('exam_preview', exam_id=exam.id)

    return render(request, "import_docx.html", {"subjects": subjects})

def exam_create(request):
    subjects = Subject.objects.all()
    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()
        subject_id = request.POST.get('subject_id')
        duration = int(request.POST.get('duration') or 60)
        n = int(request.POST.get('num_questions') or 10)

        if not code:
            messages.error(request, "Nhập mã đề thi.")
            return redirect('exam_create')

        subject = get_object_or_404(Subject, id=subject_id)
        if Exam.objects.filter(code=code).exists():
            messages.error(request, "Mã đề đã tồn tại.")
            return redirect('exam_create')

        all_qs = list(Question.objects.filter(subject=subject).prefetch_related('choices'))
        if len(all_qs) < n:
            messages.error(request, f"Môn {subject} chỉ có {len(all_qs)} câu, không đủ {n}.")
            return redirect('exam_create')

        picked = sample(all_qs, n)   # chọn ngẫu nhiên n câu
        with transaction.atomic():
            exam = Exam.objects.create(
                code=code, subject=subject,
                duration_minutes=duration, question_count=n
            )
            for idx, q in enumerate(picked, start=1):
                item = ExamItem.objects.create(exam=exam, question=q, order=idx)
                opts = list(q.choices.all())
                shuffle(opts)  # xáo trộn đáp án
                labels = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                for i, opt in enumerate(opts):
                    ExamChoice.objects.create(
                        item=item,
                        label=labels[i],
                        text=opt.text,
                        is_correct=opt.is_correct  # đúng/sai giữ nguyên theo đáp án gốc
                    )
        return redirect('exam_preview', exam_id=exam.id)

    return render(request, 'exam_create.html', {'subjects': subjects})

def exam_preview(request, exam_id):
    exam = get_object_or_404(Exam.objects.select_related('subject'), id=exam_id)
    items = exam.items.select_related('question').prefetch_related('choices').order_by('order')
    return render(request, 'exam_preview.html', {'exam': exam, 'items': items})

def _norm(s: str) -> str:
    if s is None: return ""
    s = s.replace("\xa0", " ")
    s = re.sub(r"[：]", ":", s)  # fullwidth colon -> :
    return re.sub(r"\s+", " ", s).strip()

def _iter_block_items(doc):
    """
    Trả về các block theo đúng thứ tự hiển thị: Paragraph hoặc Table.
    """
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)

def _extract_images_from_paragraph(paragraph):
    """Trả về list [(filename, blob)] các ảnh xuất hiện trong paragraph."""
    out = []
    for run in paragraph.runs:
        # tìm blip (ảnh) trong run
        for blip in run._r.xpath('.//a:blip'):
            rId = blip.get(qn('r:embed'))
            if not rId: 
                continue
            part = paragraph.part.related_parts.get(rId)
            if not part:
                continue
            filename = os.path.basename(part.partname)
            blob = part.blob
            out.append((filename, blob))
    return out

def _doc_to_stream(byte_content):
    """
    Trả về 'dòng sự kiện' theo thứ tự hiển thị:
      {'type':'text', 'text': '...'}
      {'type':'image', 'filename':'xxx.jpg','blob': b'...'}
    Dùng cho cả header và body (bảng/đoạn).
    """
    doc = Document(BytesIO(byte_content))
    stream = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            txt = _norm(block.text)
            imgs = _extract_images_from_paragraph(block)
            if txt: stream.append({'type':'text','text':txt})
            for fn, blob in imgs:
                stream.append({'type':'image','filename':fn,'blob':blob})
        else:
            # Table: đi theo hàng; ghép 2 cột kiểu [KEY][VALUE]
            for row in block.rows:
                # nhiều tài liệu merge cell -> các cell có text trùng; lấy theo index
                cells = row.cells
                # xử lý từng cell -> many paragraphs
                # Trường hợp "QN=1 | <stem>" ở 2 cột
                left_txt = _norm("\n".join(_norm(p.text) for p in cells[0].paragraphs)) if len(cells)>=1 else ""
                right_txt = _norm("\n".join(_norm(p.text) for p in cells[1].paragraphs)) if len(cells)>=2 else ""

                # ảnh trong mỗi cell
                for p in cells[0].paragraphs:
                    for fn, blob in _extract_images_from_paragraph(p):
                        stream.append({'type':'image','filename':fn,'blob':blob})
                if len(cells)>=2:
                    for p in cells[1].paragraphs:
                        for fn, blob in _extract_images_from_paragraph(p):
                            stream.append({'type':'image','filename':fn,'blob':blob})

                # các mẫu đặc thù
                if re.match(r'^QN\s*=\s*\d+', left_txt, re.I):
                    stream.append({'type':'text','text': left_txt})
                    if right_txt:
                        stream.append({'type':'text','text': right_txt})
                    continue

                # Lựa chọn a./b./c./d. chia 2 cột
                if re.match(r'^[A-Da-d][\.\)]$', left_txt) and right_txt:
                    stream.append({'type':'text','text': f"{left_txt} {right_txt}"})
                    continue
                if re.match(r'^[A-Da-d][\.\)]\s+.+', left_txt):
                    stream.append({'type':'text','text': left_txt})
                    continue

                # Hàng kiểu ANSWER/MARK/UNIT/MIX chia 2 cột
                if re.match(r'^(ANSWER|MARK|UNIT|MIX\s*CHOICES)$', left_txt, re.I) and right_txt:
                    stream.append({'type':'text','text': f"{left_txt}: {right_txt}"})
                    continue

                # còn lại: đẩy từng cột nếu có
                if left_txt:  stream.append({'type':'text','text': left_txt})
                if right_txt: stream.append({'type':'text','text': right_txt})
    return stream

def _parse_template_docx(byte_content):
    """
    Header: Subject / Number of Quiz / Lecturer / Date / Topic code (chỉ text)
    Body:  QN=<n>, stem (có thể kèm [file:xxx]), options a–d, ANSWER / MARK / UNIT / MIX
           Ảnh: lấy trực tiếp từ .docx; mỗi câu nhận ảnh nhúng đầu tiên gặp sau QN=...
    Trả về:
      meta: dict
      questions: list[{
        id:int, text:str, choices:[(label,text)], answer:'A'..'D',
        image_name:str|None, image:bytes|None, mark:float, unit:str, mix:bool
      }]
    """
    stream = _doc_to_stream(byte_content)  # <- tạo chuỗi sự kiện {'type': 'text'|'image', ...}

    # ---- header ---- (chỉ đọc TEXT đến khi gặp QN=)
    meta = {'subject': None, 'num_quiz': None, 'lecturer': None, 'date': None, 'topic_code': None}
    header_patterns = {
        'subject':    r'^(Subject|Môn\s*học)\s*:\s*(.+)$',
        'num_quiz':   r'^(Number\s*of\s*Quiz|Số\s*câu\s*hỏi)\s*:\s*(\d+)$',
        'lecturer':   r'^(Lecturer|Giảng\s*viên)\s*:\s*(.+)$',
        'date':       r'^(Date|Ngày\s*phát\s*hành)\s*:\s*(.+)$',
        'topic_code': r'^(Topic\s*code|Mã\s*đề)\s*:\s*(.+)$',
    }
    i = 0
    while i < len(stream):
        ev = stream[i]; i += 1
        if ev['type'] != 'text':
            # header KHÔNG lấy ảnh → bỏ qua
            continue
        ln = _norm(ev['text'])
        if re.match(r'^QN\s*=\s*\d+', ln, re.I):
            i -= 1  # trả lại để vòng sau xử lý như question
            break
        for k, pat in header_patterns.items():
            m = re.match(pat, ln, re.I)
            if m:
                val = m.group(2).strip()
                meta[k] = int(val) if k == 'num_quiz' else val

    missing = [k for k, v in meta.items() if not v]
    if missing:
        raise ValueError("Thiếu thông tin header: " + ", ".join(missing))

    # ---- questions ----
    questions = []
    cur = None
    pending = None  # 'answer' | 'mark' | 'unit' | 'mix'

    while i < len(stream):
        ev = stream[i]; i += 1

        # ẢNH: chỉ gán khi đang ở trong 1 câu hỏi (sau QN=) và chưa có ảnh
        if ev['type'] == 'image':
            if cur and not cur.get("image"):
                cur["image_name"] = ev.get('filename')
                cur["image"] = ev.get('blob')
            continue

        # TEXT
        ln = _norm(ev['text'])
        if not ln:
            continue

        # Bắt đầu câu hỏi
        m_qn = re.match(r'^QN\s*=\s*(\d+)', ln, re.I)
        if m_qn:
            if cur:
                questions.append(cur)
            cur = {
                "id": int(m_qn.group(1)),
                "text": "",
                "choices": [],
                "answer": None,
                "image_name": None,
                "image": None,
                "mark": 1.0,
                "unit": "",
                "mix": False
            }
            pending = None
            continue

        if not cur:
            # chưa vào block QN -> bỏ qua
            continue

        # Nếu đang chờ giá trị cho KEY ở dòng trước (ANSWER/MARK/UNIT/MIX)
        if pending:
            if pending == 'answer' and re.match(r'^[A-D]$', ln, re.I):
                cur['answer'] = ln.upper(); pending = None; continue
            if pending == 'mark' and re.match(r'^[0-9]+(?:\.[0-9]+)?$', ln):
                cur['mark'] = float(ln); pending = None; continue
            if pending == 'unit':
                cur['unit'] = ln; pending = None; continue
            if pending == 'mix' and re.match(r'^(Yes|No)$', ln, re.I):
                cur['mix'] = (ln.lower() == 'yes'); pending = None; continue
            # nếu không khớp → rơi xuống như text thường (không consume)

        # Ảnh ghi kiểu [file:xxx] ngay trong text (nếu có) → gán rồi bỏ khỏi text
        img_in_ln = re.findall(r'\[file\s*:\s*([^\]]+)\]', ln, re.I)
        if img_in_ln and not cur.get("image_name"):
            cur["image_name"] = img_in_ln[0].strip()
            ln = re.sub(r'\[file\s*:\s*[^\]]+\]', '', ln, flags=re.I).strip()

        # Lựa chọn A-D
        m_opt = re.match(r'^([A-Da-d])[\.\)]\s*(.+)$', ln)
        if m_opt:
            cur["choices"].append((m_opt.group(1).upper(), m_opt.group(2).strip()))
            continue

        # KEY: value (cùng dòng) HOẶC KEY: (trống) -> bật pending để lấy ở dòng kế tiếp
        m_kv = re.match(r'^(ANSWER|MARK|UNIT|MIX\s*CHOICES)\s*:\s*(.*)$', ln, re.I)
        if m_kv:
            key = m_kv.group(1).upper()
            val = _norm(m_kv.group(2))
            if key.startswith('ANSWER'):
                if val and re.match(r'^[A-D]$', val, re.I): cur['answer'] = val.upper()
                else: pending = 'answer'
            elif key == 'MARK':
                if val: cur['mark'] = float(val)
                else: pending = 'mark'
            elif key == 'UNIT':
                if val: cur['unit'] = val
                else: pending = 'unit'
            else:  # MIX CHOICES
                if val: cur['mix'] = (val.lower() == 'yes')
                else: pending = 'mix'
            continue

        # Thân đề (gộp nhiều dòng)
        cur["text"] = (cur["text"] + ("\n" if cur["text"] else "") + ln).strip()

    if cur:
        questions.append(cur)

    # Đối chiếu số câu
    if meta.get('num_quiz') and meta['num_quiz'] != len(questions):
        meta['_num_quiz_mismatch'] = (meta['num_quiz'], len(questions))

    # Validate từng câu
    for q in questions:
        if len(q["choices"]) < 2:
            raise ValueError(f"Câu QN={q['id']} có ít hơn 2 phương án.")
        if not q.get("answer"):
            raise ValueError(f"Câu QN={q['id']} thiếu ANSWER.")

    return meta, questions

def _peek_next_non_empty(all_lines, i):
    """Trả về (value, index) của dòng kế tiếp KHÔNG rỗng (sau i-1), hoặc (None, i_current)."""
    j = i
    while j < len(all_lines):
        v = _norm(all_lines[j])
        if v:
            return v, j
        j += 1
    return None, i  # không có gì tiếp theo

def _take_if(pattern, text, flags=0):
    m = re.match(pattern, text, flags)
    return m.group(1) if m else None
