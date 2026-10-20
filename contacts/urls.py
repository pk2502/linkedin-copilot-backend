from django.urls import path

from contacts.views import ContactDetailView, ContactListView, ContactLookupView, ContactTouchView

urlpatterns = [
    path("", ContactListView.as_view(), name="contact_list"),
    path("lookup/", ContactLookupView.as_view(), name="contact_lookup"),
    path("touch/", ContactTouchView.as_view(), name="contact_touch"),
    path("<int:pk>/", ContactDetailView.as_view(), name="contact_detail"),
]
