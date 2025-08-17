from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class Subject(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class Question(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    level = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.text[:60]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    label = models.CharField(max_length=1)  # A-D
    text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = [('question', 'label')]


class Exam(models.Model):
    code = models.CharField(max_length=20, unique=True)   # mã đề
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exams')
    duration_minutes = models.PositiveIntegerField(default=60)
    question_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Thêm các trường để scheduling (Yêu cầu 4)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.subject}"
    
    @property
    def is_available(self):
        """Kiểm tra đề thi có sẵn sàng để thi không"""
        if not self.is_active:
            return False
        
        now = timezone.now()
        if self.scheduled_start and now < self.scheduled_start:
            return False
        
        if self.scheduled_end and now > self.scheduled_end:
            return False
            
        return True


class ExamItem(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    order = models.PositiveIntegerField()

    class Meta:
        unique_together = [('exam', 'order')]
        ordering = ['order']


class ExamChoice(models.Model):
    item = models.ForeignKey(ExamItem, on_delete=models.CASCADE, related_name='choices')
    label = models.CharField(max_length=1)  # A, B, C, ...
    text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = [('item', 'label')]
        ordering = ['label']


class ExamAttempt(models.Model):    
    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name='attempts')
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='exam_attempts')

    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)

    correct_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0)
    score = models.FloatField(null=True, blank=True)  # 0..100

    STATUS = (
        ('ongoing', 'Đang thi'),
        ('submitted', 'Đã nộp bài'),
        ('expired', 'Hết thời gian'),
        ('forfeited', 'Bỏ thi'),
    )
    status = models.CharField(max_length=16, choices=STATUS, default='ongoing')

    class Meta:
        indexes = [
            models.Index(fields=['user', 'exam', 'status']),
            models.Index(fields=['exam', 'status']),
        ]
        # Sửa lại constraint để cho phép user thi lại nếu cần
        unique_together = [('exam', 'user', 'status')]  

    def __str__(self):
        return f"{self.user} - {self.exam.code} - {self.status}"
    
    @property
    def time_remaining(self):
        """Tính thời gian còn lại (giây)"""
        if self.status != 'ongoing':
            return 0
        
        remaining = (self.expires_at - timezone.now()).total_seconds()
        return max(0, remaining)
    
    @property 
    def is_expired(self):
        """Kiểm tra có hết thời gian không"""
        return timezone.now() > self.expires_at


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers')
    item = models.ForeignKey(ExamItem, on_delete=models.PROTECT)
    chosen_choice = models.ForeignKey(ExamChoice, on_delete=models.PROTECT, null=True, blank=True)

    # denormalize để chấm điểm nhanh
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('attempt', 'item')]
        indexes = [
            models.Index(fields=['attempt']),
            models.Index(fields=['attempt', 'is_correct']),
        ]

    def save(self, *args, **kwargs):
        if self.chosen_choice:
            self.answered_at = timezone.now()
        super().save(*args, **kwargs)