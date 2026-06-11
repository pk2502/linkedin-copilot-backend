from django.urls import path
from generations.views import GenerationListView, GenerationDeleteView

urlpatterns = [
    path("", GenerationListView.as_view(), name="generation_list"),
    path("<int:pk>/", GenerationDeleteView.as_view(), name="generation_delete"),
]
