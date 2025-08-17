from django.db import models

class Subject(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    def __str__(self): return f"{self.code} - {self.name}"

class Question(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    level = models.CharField(max_length=20, blank=True)
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
    def __str__(self): return f"{self.code} - {self.subject}"

class ExamItem(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey('Question', on_delete=models.PROTECT)
    order = models.PositiveIntegerField()

class ExamChoice(models.Model):
    item = models.ForeignKey(ExamItem, on_delete=models.CASCADE, related_name='choices')
    label = models.CharField(max_length=1)  # A, B, C, ...
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
