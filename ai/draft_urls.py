from django.urls import path

from ai.drafts import DraftView, TweakView

urlpatterns = [
    path("", DraftView.as_view(), name="drafts"),
    path("<int:pk>/tweak/", TweakView.as_view(), name="draft_tweak"),
]
