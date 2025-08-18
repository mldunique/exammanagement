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
        assets_zip = request.FILES.get("assets_zip")  # NEW: zip ảnh (optional)
        if not file:
            messages.error(request, "Hãy chọn file .docx (Template).")
            return redirect("import_docx")

        raw = file.read()

        # Ưu tiên parser Template
        try:
            meta, items = _parse_template_docx(raw)
        except Exception as e:
            messages.error(request, f"Lỗi đọc Template.docx: {e}")
            return redirect("import_docx")

        # map Subject
        subj_raw = (meta['subject'] or '').strip()
        subject = (Subject.objects.filter(code__iexact=subj_raw).first()
                   or Subject.objects.filter(name__iexact=subj_raw).first())
        if not subject:
            messages.error(request, f"Subject '{subj_raw}' không tồn tại. Tạo trước trong admin.")
            return redirect("import_docx")

        exam_code = (meta['topic_code'] or '').strip()
        if not exam_code:
            messages.error(request, "Thiếu Topic code (Mã đề).")
            return redirect("import_docx")
        if Exam.objects.filter(code=exam_code).exists():
            messages.error(request, f"Mã đề '{exam_code}' đã tồn tại.")
            return redirect("import_docx")

        # --- chuẩn bị kho ảnh: giải nén zip (nếu có) ---
        image_map = {}  # name -> bytes
        if assets_zip:
            try:
                zf = zipfile.ZipFile(assets_zip)
                for n in zf.namelist():
                    low = n.split('/')[-1]
                    if re.search(r'\.(png|jpe?g|gif|bmp|webp)$', low, re.I):
                        image_map[low] = zf.read(n)
            except Exception as e:
                messages.error(request, f"Không đọc được file ảnh .zip: {e}")
                return redirect("import_docx")

        warns = []
        with transaction.atomic():
            created_qs = []
            # thư mục đích: media/question_images/<exam_code>/
            base_dir = os.path.join('question_images', exam_code)

            for q in items:
                qobj = Question.objects.create(
                    subject=subject, text=q["text"],
                    mark=q.get("mark") or 1.0,
                    unit=q.get("unit") or ""
                )
                # lưu ảnh nếu có
                img_name = (q.get("image_name") or "").strip()
                if img_name:
                    data = image_map.get(img_name)
                    if data:
                        path = os.path.join(base_dir, img_name)
                        saved = default_storage.save(path, ContentFile(data))
                        qobj.image.name = saved
                        qobj.save(update_fields=["image"])
                    else:
                        warns.append(f"QN={q['id']}: không tìm thấy ảnh '{img_name}' trong .zip")

                for label, text in q["choices"]:
                    Choice.objects.create(
                        question=qobj, label=label, text=text,
                        is_correct=(label == q["answer"])
                    )
                created_qs.append((qobj, q.get("mix", False)))

            # tạo Exam + Item + ExamChoice
            exam = Exam.objects.create(
                code=exam_code, subject=subject,
                duration_minutes=60, question_count=len(created_qs)
            )
            for idx, (qobj, mix) in enumerate(created_qs, start=1):
                item = ExamItem.objects.create(exam=exam, question=qobj, order=idx, mix_choices=bool(mix))
                opts = list(qobj.choices.order_by('label'))
                if item.mix_choices:
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
        if warns: messages.warning(request, "Cảnh báo:\n" + "\n".join(warns))
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

def _doc_to_lines(byte_content):
    """
    Flatten toàn bộ docx -> list dòng text, gồm:
      - Paragraph: lấy text
      - Table: duyệt theo hàng; nếu có 2 cột kiểu [KEY][VALUE] sẽ ghép "KEY: VALUE"
               riêng đáp án a/b/c/d ghép "a. text", v.v.
    """
    doc = Document(BytesIO(byte_content))
    lines = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            t = _norm(block.text)
            if t: lines.append(t)
        else:  # Table
            for row in block.rows:
                cells = [ _norm(p.text) for p in row.cells ]
                # bỏ trùng khi Word merge cell trả ra nhiều ô giống nhau
                if len(cells) >= 2 and cells[0] == cells[1]:
                    cells = cells[:1]
                if not any(cells): 
                    continue

                # các hàng đặc thù
                left = cells[0] if len(cells) >= 1 else ""
                right = cells[1] if len(cells) >= 2 else ""

                # QN=1 ở cột trái
                if re.match(r"^QN\s*=\s*\d+", left, re.I):
                    lines.append(left)
                    # phần nội dung ở cột phải (nếu có) cũng là text đề
                    if right: lines.append(right)
                    continue

                # Lựa chọn a./b./c./d. tách làm 2 cột
                if re.match(r"^[A-Da-d][\.\)]$", left) and right:
                    lines.append(f"{left} {right}")
                    continue
                if re.match(r"^[A-Da-d][\.\)]\s+.+", left):
                    lines.append(left)  # đã kèm text ở cùng cột
                    continue

                # Hàng kiểu ANSWER / MARK / UNIT / MIX CHOICES nằm 2 cột
                if re.match(r"^(ANSWER|MARK|UNIT|MIX\s*CHOICES)$", left, re.I) and right:
                    lines.append(f"{left}: {right}")
                    continue

                # Hàng nội dung đề trong 1 cột
                if left: lines.append(left)
                if right: lines.append(right)

    # lọc dòng rỗng liên tiếp
    return [ln for ln in lines if _norm(ln)]

def _parse_template_docx(byte_content):
    """
    Đọc header (Subject/Number of Quiz/Lecturer/Date/Topic code) + danh sách câu hỏi
    trong bảng theo format bạn gửi.
    """
    all_lines = _doc_to_lines(byte_content)

    # ---- header ----
    meta = {'subject': None, 'num_quiz': None, 'lecturer': None, 'date': None, 'topic_code': None}
    header_patterns = {
        'subject':   r'^(Subject|Môn\s*học)\s*:\s*(.+)$',
        'num_quiz':  r'^(Number\s*of\s*Quiz|Số\s*câu\s*hỏi)\s*:\s*(\d+)$',
        'lecturer':  r'^(Lecturer|Giảng\s*viên)\s*:\s*(.+)$',
        'date':      r'^(Date|Ngày\s*phát\s*hành)\s*:\s*(.+)$',
        'topic_code':r'^(Topic\s*code|Mã\s*đề)\s*:\s*(.+)$',
    }
    i = 0
    while i < len(all_lines):
        ln = _norm(all_lines[i])
        if re.match(r'^QN\s*=\s*\d+', ln, re.I):  # hết header, sang câu hỏi
            break
        for k, pat in header_patterns.items():
            m = re.match(pat, ln, re.I)
            if m:
                val = m.group(2).strip()
                meta[k] = int(val) if k == 'num_quiz' else val
        i += 1

    missing = [k for k, v in meta.items() if not v]
    if missing:
        raise ValueError("Thiếu thông tin header: " + ", ".join(missing))

    # ---- questions ----
    questions = []
    cur = None
    while i < len(all_lines):
        ln = _norm(all_lines[i]); i += 1
        if not ln: 
            continue

        m_qn = re.match(r'^QN\s*=\s*(\d+)', ln, re.I)
        if m_qn:
            if cur: questions.append(cur)
            cur = {"id": int(m_qn.group(1)), "text": "", "choices": [], "answer": None,
                   "image_name": None, "mark": 1.0, "unit": "", "mix": False}
            continue

        if not cur: 
            continue

        # hình ảnh [file:xxx]
        m_img = re.match(r'^\[file\s*:\s*([^\]]+)\]$', ln, re.I)
        if m_img:
            cur["image_name"] = m_img.group(1).strip()
            continue

        # ANSWER (cùng dòng hoặc ở dòng kế)
        m = _take_if(r'^ANSW?ER\s*:\s*([A-D])$', ln, re.I)
        if m:
            cur["answer"] = m.upper()
            continue
        if re.match(r'^ANSW?ER\s*:?\s*$', ln, re.I):
            nxt, j = _peek_next_non_empty(all_lines, i)
            if nxt and re.match(r'^[A-D]$', nxt, re.I):
                cur["answer"] = nxt.upper()
                i = j + 1  # CONSUME dòng giá trị
                continue
            # nếu không khớp, đừng consume; để ln đó xử lý như text khác

        # MARK (cùng dòng hoặc ở dòng kế)
        m = _take_if(r'^MARK\s*:\s*([0-9]+(?:\.[0-9]+)?)$', ln, re.I)
        if m:
            cur["mark"] = float(m)
            continue
        if re.match(r'^MARK\s*:?\s*$', ln, re.I):
            nxt, j = _peek_next_non_empty(all_lines, i)
            if nxt and re.match(r'^[0-9]+(?:\.[0-9]+)?$', nxt):
                cur["mark"] = float(nxt)
                i = j + 1
                continue

        # UNIT (cùng dòng hoặc ở dòng kế)
        m = _take_if(r'^UNIT\s*:\s*(.+)$', ln, re.I)
        if m:
            cur["unit"] = m.strip()
            continue
        if re.match(r'^UNIT\s*:?\s*$', ln, re.I):
            nxt, j = _peek_next_non_empty(all_lines, i)
            if nxt:
                cur["unit"] = nxt
                i = j + 1
                continue

        # MIX CHOICES (cùng dòng hoặc ở dòng kế)
        m = _take_if(r'^MIX\s*CHOICES\s*:\s*(Yes|No)$', ln, re.I)
        if m:
            cur["mix"] = (m.lower() == 'yes')
            continue
        if re.match(r'^MIX\s*CHOICES\s*:?\s*$', ln, re.I):
            nxt, j = _peek_next_non_empty(all_lines, i)
            if nxt and re.match(r'^(Yes|No)$', nxt, re.I):
                cur["mix"] = (nxt.lower() == 'yes')
                i = j + 1
                continue


        # đáp án A–D
        m_opt = re.match(r'^([A-Da-d])[\.\)]\s*(.+)$', ln)
        if m_opt:
            cur["choices"].append((m_opt.group(1).upper(), m_opt.group(2).strip()))
            continue

        # nội dung đề
        cur["text"] = (cur["text"] + ("\n" if cur["text"] else "") + ln).strip()

    if cur: questions.append(cur)

    # đối chiếu số câu
    if meta.get('num_quiz') and meta['num_quiz'] != len(questions):
        meta['_num_quiz_mismatch'] = (meta['num_quiz'], len(questions))

    # validate
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
