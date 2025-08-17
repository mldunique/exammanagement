from django.db import models
from django.conf import settings

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

    def __str__(self):
        return f"{self.code} - {self.subject}"


class ExamItem(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    order = models.PositiveIntegerField()


class ExamChoice(models.Model):
    item = models.ForeignKey(ExamItem, on_delete=models.CASCADE, related_name='choices')
    label = models.CharField(max_length=1)  # A, B, C, ...
    text = models.TextField()
    is_correct = models.BooleanField(default=False)


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
        ('ongoing', 'On going'),
        ('submitted', 'Submitted'),
        ('expired', 'Expired'),
        ('forfeited', 'Forfeited'),
    )
    status = models.CharField(max_length=16, choices=STATUS, default='ongoing')

    class Meta:
        indexes = [
            models.Index(fields=['user', 'exam', 'status']),
        ]
        unique_together = [('exam', 'user', 'status')]  


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers')
    item = models.ForeignKey(ExamItem, on_delete=models.PROTECT)
    chosen_choice = models.ForeignKey(ExamChoice, on_delete=models.PROTECT, null=True, blank=True)

    # denormalize để chấm điểm nhanh
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = [('attempt', 'item')]
        indexes = [models.Index(fields=['attempt'])]
