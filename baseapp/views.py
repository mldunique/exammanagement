from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction
from io import BytesIO
from docx import Document
from random import sample, shuffle
import re
from .models import Subject, Question, Choice, Exam, ExamItem, ExamChoice

def home(request):
    subjects = Subject.objects.all()
    return render(request, 'home.html', {'subjects': subjects})

def login(request):
    return render(request, 'login.html')

def _parse_docx(byte_content):
    """
    Hỗ trợ 2 format phổ biến:
    1) Q1. Nội dung...
       A. ...
       B. ...
       C. ...
       D. ...
       Answer: B

    2) Q1. Nội dung...
       A. ...
       B. ... *
       C. ...
       D. ...
    (dấu * ở phương án đúng)
    """
    doc = Document(BytesIO(byte_content))
    questions, cur = [], None

    for p in doc.paragraphs:
        line = (p.text or "").strip()
        if not line:
            continue

        m_q = re.match(r'^(?:Q\s*\d+\.|\d+\.)\s*(.+)', line, flags=re.I)
        if m_q:
            if cur: questions.append(cur)
            cur = {"text": m_q.group(1).strip(), "choices": [], "answer": None}
            continue

        if cur:
            # A./A) phương án
            m_opt = re.match(r'^([A-D])[\.\)]\s*(.+?)(\s*\*)?$', line)
            if m_opt:
                label = m_opt.group(1).upper()
                text = m_opt.group(2).strip()
                star = m_opt.group(3)
                cur["choices"].append((label, text))
                if star: cur["answer"] = label
                continue

            # Answer: B / Đáp án: B
            m_ans = re.match(r'^(?:Answer|Đáp\s*án)\s*[:：]\s*([A-D])', line, flags=re.I)
            if m_ans:
                cur["answer"] = m_ans.group(1).upper()
                continue

    if cur: questions.append(cur)
    return questions

@require_http_methods(["GET", "POST"])
def import_docx(request):
    subjects = Subject.objects.all()
    if request.method == "POST":
        file = request.FILES.get("file")
        subject_id = request.POST.get("subject_id")
        if not file or not subject_id:
            messages.error(request, "Hãy chọn môn học và file .docx")
            return redirect("import_docx")

        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            messages.error(request, "Môn học không hợp lệ")
            return redirect("import_docx")

        try:
            items = _parse_docx(file.read())
        except Exception as e:
            messages.error(request, f"Lỗi đọc file: {e}")
            return redirect("import_docx")

        created, warns = 0, []
        with transaction.atomic():
            for idx, q in enumerate(items, start=1):
                if not q["text"]:
                    warns.append(f"Câu {idx}: thiếu nội dung.")
                    continue
                if len(q["choices"]) < 2:
                    warns.append(f"Câu {idx}: ít hơn 2 phương án.")
                    continue
                if not q.get("answer"):
                    # fallback: đánh A là đúng nếu không có Answer
                    q["answer"] = "A"
                    warns.append(f"Câu {idx}: thiếu đáp án → mặc định A.")

                qobj = Question.objects.create(subject=subject, text=q["text"])
                for label, text in q["choices"]:
                    Choice.objects.create(
                        question=qobj, label=label, text=text,
                        is_correct=(label == q["answer"])
                    )
                created += 1

        messages.success(request, f"Đã import {created} câu hỏi vào {subject}.")
        if warns:
            messages.warning(request, "Cảnh báo:\n" + "\n".join(warns))
        return redirect("import_docx")

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