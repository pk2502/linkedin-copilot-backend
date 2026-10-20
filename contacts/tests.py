import datetime

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from ai.test_drafts import DraftTestCase
from contacts.models import Contact
from contacts.services import find_or_create, normalize_linkedin_url
from generations.models import Generation

URL = "https://www.linkedin.com/in/priya-shah/"


class NormalizeTests(TestCase):
    def test_canonical_profile_urls(self):
        for raw in (
            "https://www.linkedin.com/in/Priya-Shah/?miniProfileUrn=x",
            "https://in.linkedin.com/in/priya-shah",
            "https://linkedin.com/in/priya-shah/details/experience/",
        ):
            self.assertEqual(normalize_linkedin_url(raw), URL)

    def test_rejects_other_urls(self):
        for raw in ("", "https://evil.com/in/priya", "https://www.linkedin.com/company/acme/", "not a url"):
            self.assertEqual(normalize_linkedin_url(raw), "")


class FindOrCreateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="correct-horse-battery-staple")

    def test_matches_by_url_then_by_name_and_company(self):
        by_name = find_or_create(self.user, "Priya Shah", "Acme")
        self.assertEqual(find_or_create(self.user, "priya shah", "ACME"), by_name)
        # A later extension draft adds the URL to the web-made contact.
        self.assertEqual(find_or_create(self.user, "Priya Shah", "Acme", linkedin_url=URL), by_name)
        by_name.refresh_from_db()
        self.assertEqual(by_name.linkedin_url, URL)
        self.assertEqual(find_or_create(self.user, "P. Shah", "", linkedin_url=URL), by_name)

    def test_never_merges_two_profiles_with_the_same_name(self):
        first = find_or_create(self.user, "Sam Lee", "Acme", linkedin_url="https://www.linkedin.com/in/sam-1/")
        second = find_or_create(self.user, "Sam Lee", "Acme", linkedin_url="https://www.linkedin.com/in/sam-2/")
        self.assertNotEqual(first, second)

    def test_fills_missing_details_but_keeps_existing_ones(self):
        contact = find_or_create(self.user, "Priya Shah", "", linkedin_url=URL)
        find_or_create(self.user, "Priya Shah", "Acme", "EM", linkedin_url=URL)
        find_or_create(self.user, "Priya Shah", "Globex", "CTO", linkedin_url=URL)
        contact.refresh_from_db()
        self.assertEqual((contact.company, contact.role), ("Acme", "EM"))

    def test_needs_a_name_for_a_new_contact(self):
        self.assertIsNone(find_or_create(self.user, "", "Acme"))


class DraftTrackingTests(DraftTestCase):
    def test_a_draft_creates_a_drafted_contact_and_links_it(self):
        response = self.draft("connection_request", linkedin_url=URL)

        contact = Contact.objects.get()
        self.assertEqual((contact.name, contact.status, contact.linkedin_url), ("Priya Shah", "drafted", URL))
        self.assertEqual(response.json()["contact_id"], contact.id)
        self.assertEqual(Generation.objects.get().contact, contact)
        self.assertNotIn("linkedin_url", Generation.objects.get().input_data)
        self.assertNotIn("priya-shah", self.fake.last_user_message)

    def test_drafts_for_the_same_person_share_one_contact(self):
        self.draft("connection_request")
        self.add_profile()
        self.draft("referral_request")
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(Generation.objects.filter(contact__isnull=False).count(), 2)

    def test_recruiter_name_is_used_for_recruiter_replies(self):
        self.add_profile()
        self.draft("recruiter_reply")
        self.assertEqual(Contact.objects.get().name, "Sam Lee")

    def test_tweaks_belong_to_the_same_contact(self):
        draft_id = self.draft("connection_request").json()["id"]
        self.fake.replies = [{"text": "Shorter."}]
        self.client.post(f"/api/drafts/{draft_id}/tweak/", {"variant": 0, "instruction": "shorter"}, format="json")
        self.assertEqual(Generation.objects.latest("id").contact, Contact.objects.get())

    def test_drafting_again_does_not_reset_status(self):
        self.draft("connection_request", linkedin_url=URL)
        contact = Contact.objects.get()
        contact.mark_sent()
        contact.save()
        self.draft("followup", linkedin_url=URL)
        contact.refresh_from_db()
        self.assertEqual(contact.status, "sent")


class ContactApiTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}")

    def make(self, user=None, **fields):
        defaults = {"name": "Priya Shah", "company": "Acme"}
        return Contact.objects.create(user=user or self.user, **{**defaults, **fields})

    def touch(self, event, **overrides):
        body = {"linkedin_url": URL, "name": "Priya Shah", "company": "Acme", "event": event, **overrides}
        return self.client.post("/api/contacts/touch/", body, format="json")


@override_settings(FOLLOW_UP_DAYS=5)
class TouchTests(ContactApiTestCase):
    def test_sent_creates_or_updates_and_sets_a_follow_up(self):
        response = self.touch("sent")

        self.assertEqual(response.status_code, 200)
        contact = Contact.objects.get()
        self.assertEqual(contact.status, "sent")
        self.assertEqual(contact.follow_up_on, timezone.localdate() + datetime.timedelta(days=5))
        self.assertEqual(response.json()["follow_up_due"], False)

    def test_replied_clears_the_follow_up(self):
        self.touch("sent")
        response = self.touch("replied")
        self.assertEqual(response.json()["status"], "replied")
        self.assertIsNone(Contact.objects.get().follow_up_on)

    def test_replied_from_an_unknown_person_is_ignored(self):
        self.assertEqual(self.touch("replied").status_code, 204)
        self.assertFalse(Contact.objects.exists())

    def test_done_contacts_are_left_alone(self):
        self.make(linkedin_url=URL, status="done")
        self.touch("sent")
        self.assertEqual(Contact.objects.get().status, "done")

    def test_rejects_non_profile_urls(self):
        response = self.touch("sent", linkedin_url="https://www.linkedin.com/messaging/thread/1/")
        self.assertEqual(response.status_code, 400)

    def test_requires_auth(self):
        self.client.credentials()
        self.assertEqual(self.touch("sent").status_code, 401)


class ListAndLookupTests(ContactApiTestCase):
    def test_lists_only_own_contacts_with_filters(self):
        today = timezone.localdate()
        due = self.make(name="Due", status="sent", sent_at=timezone.now(), follow_up_on=today)
        self.make(name="Waiting", status="sent", follow_up_on=today + datetime.timedelta(days=2))
        self.make(name="Replied", status="replied")
        other = User.objects.create_user(username="bob", password="correct-horse-battery-staple")
        self.make(user=other, name="Not mine", status="sent", follow_up_on=today)

        names = lambda query="": [c["name"] for c in self.client.get(f"/api/contacts/{query}").json()]
        self.assertEqual(sorted(names()), ["Due", "Replied", "Waiting"])
        self.assertEqual(sorted(names("?status=sent")), ["Due", "Waiting"])
        self.assertEqual(names("?due=1"), ["Due"])
        self.assertEqual(names("?search=repl"), ["Replied"])
        listed = self.client.get("/api/contacts/?due=1").json()[0]
        self.assertEqual((listed["id"], listed["follow_up_due"], listed["days_since_sent"]), (due.id, True, 0))
        self.assertEqual(self.client.get("/api/contacts/?status=nope").status_code, 400)

    def test_lookup_by_profile_url(self):
        contact = self.make(linkedin_url=URL)
        response = self.client.get("/api/contacts/lookup/", {"linkedin_url": "https://www.linkedin.com/in/Priya-Shah/?x=1"})
        self.assertEqual(response.json()["id"], contact.id)
        missing = self.client.get("/api/contacts/lookup/", {"linkedin_url": "https://www.linkedin.com/in/nobody/"})
        self.assertEqual(missing.status_code, 404)

    def test_last_draft_id_is_the_latest_original_draft(self):
        contact = self.make()
        first = Generation.objects.create(user=self.user, generation_type="followup", input_data={}, output="a", contact=contact)
        Generation.objects.create(user=self.user, generation_type="followup", input_data={}, output="b", contact=contact, parent=first)
        self.assertEqual(self.client.get("/api/contacts/").json()[0]["last_draft_id"], first.id)


@override_settings(FOLLOW_UP_DAYS=5)
class UpdateTests(ContactApiTestCase):
    def patch(self, contact, **body):
        return self.client.patch(f"/api/contacts/{contact.id}/", body, format="json")

    def test_status_changes_set_dates(self):
        contact = self.make()
        self.assertEqual(self.patch(contact, status="sent").json()["status"], "sent")
        contact.refresh_from_db()
        self.assertIsNotNone(contact.sent_at)
        self.assertIsNotNone(contact.follow_up_on)

        self.patch(contact, status="done", outcome="positive", notes="Referred me!")
        contact.refresh_from_db()
        self.assertEqual((contact.status, contact.outcome, contact.notes), ("done", "positive", "Referred me!"))
        self.assertIsNone(contact.follow_up_on)

    def test_snooze_by_setting_the_follow_up_date(self):
        contact = self.make(status="sent", follow_up_on=timezone.localdate())
        later = (timezone.localdate() + datetime.timedelta(days=3)).isoformat()
        self.assertEqual(self.patch(contact, follow_up_on=later).json()["follow_up_due"], False)

    def test_cannot_change_url_or_dates_directly(self):
        contact = self.make()
        self.patch(contact, linkedin_url="https://www.linkedin.com/in/x/", sent_at="2020-01-01T00:00:00Z")
        contact.refresh_from_db()
        self.assertEqual((contact.linkedin_url, contact.sent_at), ("", None))

    def test_invalid_values_are_rejected(self):
        contact = self.make()
        self.assertEqual(self.patch(contact, status="ghosted").status_code, 400)
        self.assertEqual(self.patch(contact, notes="x" * 2001).status_code, 400)

    def test_delete_keeps_the_drafts(self):
        contact = self.make()
        draft = Generation.objects.create(user=self.user, generation_type="followup", input_data={}, output="a", contact=contact)
        self.assertEqual(self.client.delete(f"/api/contacts/{contact.id}/").status_code, 204)
        draft.refresh_from_db()
        self.assertIsNone(draft.contact)

    def test_other_users_contacts_are_not_found(self):
        other = User.objects.create_user(username="bob", password="correct-horse-battery-staple")
        contact = self.make(user=other)
        self.assertEqual(self.patch(contact, notes="hi").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/contacts/{contact.id}/").status_code, 404)


class FollowUpDueTests(TestCase):
    def test_due_only_when_sent_and_date_reached(self):
        user = User.objects.create_user(username="alice", password="correct-horse-battery-staple")
        today = timezone.localdate()
        cases = [
            ("sent", today, True),
            ("sent", today - datetime.timedelta(days=1), True),
            ("sent", today + datetime.timedelta(days=1), False),
            ("replied", today, False),
            ("sent", None, False),
        ]
        for status, date, expected in cases:
            with self.subTest(status=status, date=date):
                contact = Contact(user=user, name="X", status=status, follow_up_on=date)
                self.assertEqual(contact.follow_up_due, expected)
