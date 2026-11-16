from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm

from .models import ARCHETYPES

User = get_user_model()


class BootstrapMixin:
    """Bootstrap classes are set here (not by inline JS) so a strict CSP stays possible."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"


class RegisterForm(BootstrapMixin, UserCreationForm):
    accept_terms = forms.BooleanField(
        label="ยอมรับข้อตกลงการใช้งาน",
        error_messages={"required": "กรุณายอมรับข้อตกลงการใช้งาน"},
    )

    class Meta:
        model = User
        fields = ("full_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("อีเมลนี้มีผู้ใช้งานแล้ว")
        return email


class LoginForm(BootstrapMixin, AuthenticationForm):
    username = forms.EmailField(label="อีเมล")


class ProfileForm(forms.ModelForm):
    archetype = forms.ChoiceField(choices=[("", "")] + ARCHETYPES, required=False)

    class Meta:
        model = User
        fields = ("full_name", "bio", "archetype")

    def clean_archetype(self):
        value = self.cleaned_data.get("archetype", "")
        # Archetype A (P'Ryu) is admin-only, as in the original
        if value == "A" and not self.instance.is_staff and self.instance.archetype != "A":
            raise forms.ValidationError("ตัวละครนี้สำหรับผู้ดูแลเท่านั้น")
        return value


class ResetRequestForm(BootstrapMixin, PasswordResetForm):
    pass


class NewPasswordForm(BootstrapMixin, SetPasswordForm):
    pass
