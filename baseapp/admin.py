from django.contrib import admin
from .models import Subject, Question, Choice

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "short_text")
    search_fields = ("text", "subject__code", "subject__name")
    inlines = [ChoiceInline]

    def short_text(self, obj): return obj.text[:80]

admin.site.register(Subject)

