from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth import authenticate, login as auth_login, logout
from io import BytesIO
from docx import Document
from random import sample, shuffle
from datetime import timedelta
import re
from .models import Subject, Question, Choice, Exam, ExamItem, ExamChoice, ExamAttempt, AttemptAnswer

# Helper functions
def is_admin(user):
    """Kiểm tra user có quyền admin không"""
    return user.is_staff or user.is_superuser

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

# Authentication views
def login_view(request):
    """Đăng nhập - phân biệt admin và user"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        print(user)
        if user is not None:
            auth_login(request, user)
            # Phân hướng theo quyền
            if is_admin(user):
                print("REIGHT")
                return render(request, 'admin_home.html')
            else:
                return render(request, 'student_home.html')
        else:
            messages.error(request, 'Tài khoản hoặc mật khẩu không đúng')
    
    return render(request, 'login.html')

def logout_view(request):
    """Đăng xuất"""
    logout(request)
    return redirect('login')

# =============================================================================
# ADMIN VIEWS (Yêu cầu 1, 3) - Chỉ cho admin/staff
# =============================================================================

# @login_required
# @user_passes_test(is_admin)
def admin_home(request):
    """Trang chủ admin - quản lý hệ thống"""
    subjects = Subject.objects.all()
    exams = Exam.objects.select_related('subject').order_by('-created_at')[:10]
    
    stats = {
        'total_subjects': Subject.objects.count(),
        'total_questions': Question.objects.count(),
        'total_exams': Exam.objects.count(),
        'active_attempts': ExamAttempt.objects.filter(status='ongoing').count(),
    }
    print(subjects)
    print(stats)
    print(exams)
    return render(request, 'login.html')
    # return render(request, 'admin_home.html', {
    #     'subjects': subjects,
    #     'exams': exams,
    #     'stats': stats
    # })

# @login_required
# @user_passes_test(is_admin)
# @require_http_methods(["GET", "POST"])
def import_docx(request):
    print("DÓC")
    """Import câu hỏi từ file docx (Yêu cầu 1) - CHỈ ADMIN"""
    subjects = Subject.objects.all()
    if request.method == "POST":
        file = request.FILES.get("file")
        subject_id = request.POST.get("subject_id")
        
        if not file or not subject_id:
            messages.error(request, "Hãy chọn môn học và file .docx")
            return render("import_docx")

        if not file.name.endswith('.docx'):
            messages.error(request, "Chỉ chấp nhận file .docx")
            return render("import_docx")

        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            messages.error(request, "Môn học không hợp lệ")
            return render("import_docx")

        try:
            items = _parse_docx(file.read())
        except Exception as e:
            messages.error(request, f"Lỗi đọc file: {e}")
            return render("import_docx")

        if not items:
            messages.error(request, "Không tìm thấy câu hỏi nào trong file")
            return render("import_docx")

        created, warns = 0, []
        with transaction.atomic():
            for idx, q in enumerate(items, start=1):
                # Kiểm tra định dạng
                if not q["text"]:
                    warns.append(f"Câu {idx}: thiếu nội dung câu hỏi.")
                    continue
                
                if len(q["choices"]) < 2:
                    warns.append(f"Câu {idx}: cần ít nhất 2 phương án.")
                    continue
                
                if len(q["choices"]) > 6:
                    warns.append(f"Câu {idx}: tối đa 6 phương án.")
                    continue
                
                # Kiểm tra đáp án
                if not q.get("answer"):
                    q["answer"] = "A"
                    warns.append(f"Câu {idx}: không tìm thấy đáp án → mặc định A.")
                
                # Kiểm tra đáp án có hợp lệ không
                choice_labels = [label for label, _ in q["choices"]]
                if q["answer"] not in choice_labels:
                    warns.append(f"Câu {idx}: đáp án {q['answer']} không có trong danh sách phương án.")
                    q["answer"] = choice_labels[0]

                # Tạo câu hỏi
                qobj = Question.objects.create(subject=subject, text=q["text"])
                for label, text in q["choices"]:
                    Choice.objects.create(
                        question=qobj, 
                        label=label, 
                        text=text,
                        is_correct=(label == q["answer"])
                    )
                created += 1

        messages.success(request, f"Đã import thành công {created} câu hỏi vào môn {subject}.")
        if warns:
            messages.warning(request, "Cảnh báo:\n" + "\n".join(warns))
        return render("import_docx")

    return render(request, "import_docx.html", {"subjects": subjects})

@login_required
@user_passes_test(is_admin)
def exam_create(request):
    """Tạo đề thi (Yêu cầu 3) - CHỈ ADMIN"""
    subjects = Subject.objects.all()
    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()
        subject_id = request.POST.get('subject_id')
        duration = int(request.POST.get('duration') or 60)
        n = int(request.POST.get('num_questions') or 10)
        
        # Lấy thông tin scheduling (Yêu cầu 4)
        scheduled_start = request.POST.get('scheduled_start')
        scheduled_end = request.POST.get('scheduled_end')

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

        # Chọn ngẫu nhiên n câu hỏi
        picked = sample(all_qs, n)
        
        with transaction.atomic():
            exam = Exam.objects.create(
                code=code, 
                subject=subject,
                duration_minutes=duration, 
                question_count=n,
                scheduled_start=scheduled_start if scheduled_start else None,
                scheduled_end=scheduled_end if scheduled_end else None,
            )
            
            for idx, q in enumerate(picked, start=1):
                item = ExamItem.objects.create(exam=exam, question=q, order=idx)
                
                # Xáo trộn thứ tự các đáp án
                opts = list(q.choices.all())
                shuffle(opts)
                
                labels = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                for i, opt in enumerate(opts):
                    ExamChoice.objects.create(
                        item=item,
                        label=labels[i],
                        text=opt.text,
                        is_correct=opt.is_correct
                    )
                    
        messages.success(request, f"Đã tạo đề thi {code} thành công!")
        return redirect('exam_preview', exam_id=exam.id)

    return render(request, 'admin/exam_create.html', {'subjects': subjects})

@login_required
@user_passes_test(is_admin)
def exam_preview(request, exam_id):
    """Xem trước đề thi - CHỈ ADMIN"""
    exam = get_object_or_404(Exam.objects.select_related('subject'), id=exam_id)
    items = exam.items.select_related('question').prefetch_related('choices').order_by('order')
    return render(request, 'admin/exam_preview.html', {'exam': exam, 'items': items})

@login_required
@user_passes_test(is_admin)
def exam_manage(request):
    """Quản lý đề thi - danh sách tất cả đề thi"""
    exams = Exam.objects.select_related('subject').order_by('-created_at')
    return render(request, 'admin/exam_manage.html', {'exams': exams})

# =============================================================================
# STUDENT VIEWS (Yêu cầu 5) - Cho học sinh/người dự thi
# =============================================================================

@login_required
def student_home(request):
    """Trang chủ học sinh - xem đề thi khả dụng"""
    now = timezone.now()
    
    # Lấy các đề thi khả dụng (trong thời gian cho phép)
    available_exams = Exam.objects.filter(
        is_active=True,
        scheduled_start__lte=now,
        scheduled_end__gte=now
    ).exclude(
        attempts__user=request.user,
        attempts__status__in=['submitted', 'expired']
    ).select_related('subject')
    
    # Lấy lịch sử thi của user
    my_attempts = ExamAttempt.objects.filter(
        user=request.user
    ).select_related('exam').order_by('-started_at')[:5]
    
    # Kiểm tra có bài thi đang làm dở không
    ongoing_attempt = ExamAttempt.objects.filter(
        user=request.user,
        status='ongoing'
    ).select_related('exam').first()
    
    context = {
        'available_exams': available_exams,
        'my_attempts': my_attempts,
        'ongoing_attempt': ongoing_attempt,
    }
    
    return render(request, 'student/home.html', context)

@login_required
def exam_start(request, exam_id):
    """Bắt đầu làm bài thi (Yêu cầu 5) - CHỈ STUDENT"""
    exam = get_object_or_404(Exam, id=exam_id)
    
    # Kiểm tra quyền admin không được thi
    if is_admin(request.user):
        messages.error(request, "Admin không thể tham gia thi.")
        return redirect('admin_home')
    
    # Kiểm tra đề thi có khả dụng không
    if not exam.is_available:
        messages.error(request, "Đề thi này hiện không khả dụng.")
        return redirect('student_home')
    
    # Kiểm tra xem user đã có attempt ongoing không
    existing_attempt = ExamAttempt.objects.filter(
        exam=exam, 
        user=request.user, 
        status='ongoing'
    ).first()
    
    if existing_attempt:
        return redirect('exam_take', attempt_id=existing_attempt.id)
    
    # Kiểm tra xem user đã thi xong chưa
    completed_attempt = ExamAttempt.objects.filter(
        exam=exam,
        user=request.user,
        status__in=['submitted', 'expired']
    ).first()
    
    if completed_attempt:
        messages.info(request, "Bạn đã hoàn thành bài thi này rồi.")
        return redirect('exam_result', attempt_id=completed_attempt.id)
    
    # Tạo attempt mới
    with transaction.atomic():
        attempt = ExamAttempt.objects.create(
            exam=exam,
            user=request.user,
            expires_at=timezone.now() + timedelta(minutes=exam.duration_minutes),
            total_count=exam.question_count
        )
        
        # Tạo các câu trả lời trống
        for item in exam.items.all():
            AttemptAnswer.objects.create(attempt=attempt, item=item)
    
    return redirect('exam_take', attempt_id=attempt.id)

@login_required
def exam_take(request, attempt_id):
    """Làm bài thi (Yêu cầu 5) - CHỈ STUDENT"""
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related('exam', 'user'),
        id=attempt_id,
        user=request.user
    )
    
    # Kiểm tra trạng thái
    if attempt.status != 'ongoing':
        if attempt.status == 'submitted':
            return redirect('exam_result', attempt_id=attempt.id)
        messages.error(request, "Bài thi đã kết thúc hoặc hết hạn.")
        return redirect('student_home')
    
    # Kiểm tra thời gian
    if timezone.now() > attempt.expires_at:
        # Auto submit khi hết thời gian
        with transaction.atomic():
            attempt.submitted_at = timezone.now()
            attempt.status = 'expired'
            
            # Tính điểm
            correct = attempt.answers.filter(is_correct=True).count()
            attempt.correct_count = correct
            attempt.score = (correct / attempt.total_count) * 100 if attempt.total_count > 0 else 0
            attempt.save()
            
        messages.warning(request, "Bài thi đã hết thời gian và được nộp tự động.")
        return redirect('exam_result', attempt_id=attempt.id)
    
    # Lấy danh sách câu hỏi và câu trả lời
    items = attempt.exam.items.select_related('question').prefetch_related('choices').order_by('order')
    answers = {ans.item_id: ans for ans in attempt.answers.select_related('chosen_choice')}
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save_answer':
            item_id = request.POST.get('item_id')
            choice_id = request.POST.get('choice_id')
            
            try:
                item = ExamItem.objects.get(id=item_id, exam=attempt.exam)
                choice = ExamChoice.objects.get(id=choice_id, item=item) if choice_id else None
                
                answer = AttemptAnswer.objects.get(attempt=attempt, item=item)
                answer.chosen_choice = choice
                answer.is_correct = choice.is_correct if choice else False
                answer.save()
                
                return JsonResponse({'success': True})
            except (ExamItem.DoesNotExist, ExamChoice.DoesNotExist, AttemptAnswer.DoesNotExist):
                return JsonResponse({'success': False, 'error': 'Invalid data'})
        
        elif action == 'submit':
            # Nộp bài
            with transaction.atomic():
                attempt.submitted_at = timezone.now()
                attempt.status = 'submitted'
                
                # Tính điểm
                correct = attempt.answers.filter(is_correct=True).count()
                attempt.correct_count = correct
                attempt.score = (correct / attempt.total_count) * 100 if attempt.total_count > 0 else 0
                attempt.save()
            
            messages.success(request, "Đã nộp bài thành công!")
            return redirect('exam_result', attempt_id=attempt.id)
    
    # Tính thời gian còn lại
    time_left = (attempt.expires_at - timezone.now()).total_seconds()
    
    context = {
        'attempt': attempt,
        'items': items,
        'answers': answers,
        'time_left_seconds': max(0, int(time_left)),
    }
    
    return render(request, 'student/exam_take.html', context)

@login_required
def exam_result(request, attempt_id):
    """Xem kết quả thi (Yêu cầu 5) - CHỈ STUDENT"""
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related('exam', 'user'),
        id=attempt_id,
        user=request.user
    )
    
    if attempt.status == 'ongoing':
        messages.info(request, "Bài thi chưa hoàn thành.")
        return redirect('exam_take', attempt_id=attempt.id)
    
    # Lấy chi tiết câu trả lời
    items = attempt.exam.items.select_related('question').prefetch_related('choices').order_by('order')
    answers = {ans.item_id: ans for ans in attempt.answers.select_related('chosen_choice')}
    
    # Tính toán thống kê
    results = []
    for item in items:
        answer = answers.get(item.id)
        correct_choice = item.choices.filter(is_correct=True).first()
        
        results.append({
            'item': item,
            'user_choice': answer.chosen_choice if answer else None,
            'correct_choice': correct_choice,
            'is_correct': answer.is_correct if answer else False,
        })
    
    context = {
        'attempt': attempt,
        'results': results,
    }
    
    return render(request, 'student/exam_result.html', context)

@login_required
def my_results(request):
    """Xem tất cả kết quả thi của mình"""
    attempts = ExamAttempt.objects.filter(
        user=request.user,
        status__in=['submitted', 'expired']
    ).select_related('exam').order_by('-submitted_at')
    
    return render(request, 'student/my_results.html', {'attempts': attempts})