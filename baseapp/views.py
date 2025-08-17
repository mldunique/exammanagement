from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction
from io import BytesIO
from docx import Document
import re
from .models import Subject, Question, Choice

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