# # models.py
# from django.db import models

# class Subject(models.Model):
#     name = models.CharField(max_length=200)
#     code = models.CharField(max_length=50, unique=True)
#     def __str__(self): return f"{self.code} - {self.name}"

# class Question(models.Model):
#     subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
#     text = models.TextField()
#     level = models.CharField(max_length=20, blank=True)
#     # NEW:
#     # image = models.ImageField(upload_to='question_images/', blank=True, null=True)
#     image = models.ImageField(upload_to='', blank=True, null=True)
#     mark = models.FloatField(default=1.0)
#     unit = models.CharField(max_length=120, blank=True)
#     def __str__(self): return self.text[:60]

# class Choice(models.Model):
#     question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
#     label = models.CharField(max_length=1)  # A-D
#     text = models.TextField()
#     is_correct = models.BooleanField(default=False)
#     class Meta:
#         unique_together = [('question', 'label')]

# class Exam(models.Model):
#     code = models.CharField(max_length=20, unique=True)   # mã đề
#     subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='exams')
#     duration_minutes = models.PositiveIntegerField(default=60)
#     question_count = models.PositiveIntegerField()
#     created_at = models.DateTimeField(auto_now_add=True)
#     def __str__(self): return f"{self.code} - {self.subject}"

# class ExamItem(models.Model):
#     exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='items')
#     question = models.ForeignKey('Question', on_delete=models.PROTECT)
#     order = models.PositiveIntegerField()
#     # NEW: trộn đáp án của riêng câu hỏi này?
#     mix_choices = models.BooleanField(default=False)

# class ExamChoice(models.Model):
#     item = models.ForeignKey(ExamItem, on_delete=models.CASCADE, related_name='choices')
#     label = models.CharField(max_length=1)
#     text = models.TextField()
#     is_correct = models.BooleanField(default=False)

# models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Subject(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    def __str__(self): return f"{self.code} - {self.name}"

class Question(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    level = models.CharField(max_length=20, blank=True)
    image = models.ImageField(upload_to='', blank=True, null=True)
    mark = models.FloatField(default=1.0)
    unit = models.CharField(max_length=120, blank=True)
    def __str__(self): return self.text[:60]

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    label = models.CharField(max_length=1)  # A-D
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    class Meta:
        unique_together = [('question', 'label')]

class Exam(models.Model):
    code = models.CharField(max_length=20, unique=True)   # mã đề
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='exams')
    duration_minutes = models.PositiveIntegerField(default=60)
    question_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # NEW: Thời gian thi thực tế
    start_time = models.DateTimeField(null=True, blank=True)  # Thời điểm bắt đầu cho phép thi
    end_time = models.DateTimeField(null=True, blank=True)    # Thời điểm kết thúc thi
    is_active = models.BooleanField(default=False)            # Kích hoạt đề thi
    
    def is_available_now(self):
        """Kiểm tra đề thi có thể làm bây giờ không"""
        now = timezone.now()
        if not self.is_active:
            return False
        if self.start_time and now < self.start_time:
            return False
        if self.end_time and now > self.end_time:
            return False
        return True
    
    def __str__(self): return f"{self.code} - {self.subject}"

class ExamItem(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey('Question', on_delete=models.PROTECT)
    order = models.PositiveIntegerField()
    mix_choices = models.BooleanField(default=False)

class ExamChoice(models.Model):
    item = models.ForeignKey(ExamItem, on_delete=models.CASCADE, related_name='choices')
    label = models.CharField(max_length=1)
    text = models.TextField()
    is_correct = models.BooleanField(default=False)

# NEW: Models cho chức năng thi
class StudentExamSession(models.Model):
    """Phiên thi của học sinh"""
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)  # Thời điểm bắt đầu làm bài
    end_time = models.DateTimeField(null=True, blank=True)  # Thời điểm nộp bài
    is_submitted = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)  # Điểm số
    total_marks = models.FloatField(null=True, blank=True)  # Tổng điểm tối đa
    
    class Meta:
        unique_together = [('student', 'exam')]  # Mỗi học sinh chỉ làm 1 lần/đề
    
    def get_remaining_time(self):
        """Tính thời gian còn lại (phút)"""
        if self.is_submitted:
            return 0
        
        now = timezone.now()
        exam_deadline = self.start_time + timezone.timedelta(minutes=self.exam.duration_minutes)
        
        # Kiểm tra deadline của kỳ thi
        if self.exam.end_time and self.exam.end_time < exam_deadline:
            exam_deadline = self.exam.end_time
            
        if now >= exam_deadline:
            return 0
            
        return int((exam_deadline - now).total_seconds() / 60)
    
    def is_time_up(self):
        """Kiểm tra đã hết giờ chưa"""
        return self.get_remaining_time() <= 0

class StudentAnswer(models.Model):
    """Câu trả lời của học sinh"""
    session = models.ForeignKey(StudentExamSession, on_delete=models.CASCADE, related_name='answers')
    exam_item = models.ForeignKey(ExamItem, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(ExamChoice, on_delete=models.CASCADE, null=True, blank=True)
    answered_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [('session', 'exam_item')]

# NEW: Profile để phân biệt admin/student
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('student', 'Student'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    student_id = models.CharField(max_length=20, blank=True)  # Mã sinh viên
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"