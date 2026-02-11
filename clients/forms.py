"""Forms for client management."""
from django import forms
from .models import Client

tw = "w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": tw, "placeholder": "Client name"}),
            "active": forms.CheckboxInput(attrs={"class": "rounded text-blue-500"}),
        }


class ClientAccountMappingForm(forms.Form):
    """Add account_ids to a client."""
    account_ids = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": tw,
            "rows": 4,
            "placeholder": "Enter account IDs (one per line)",
        }),
        help_text="One account ID per line",
    )

    def clean_account_ids(self):
        raw = self.cleaned_data["account_ids"]
        ids = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        if not ids:
            raise forms.ValidationError("Provide at least one account ID.")
        return ids
