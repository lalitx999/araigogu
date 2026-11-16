from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from .archetypes import ARCHETYPE_CHOICES

ARCHETYPES = ARCHETYPE_CHOICES


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self._create(email, password, **extra)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    full_name = models.CharField("ชื่อ-นามสกุล", max_length=150)
    bio = models.CharField("ไบโอ", max_length=300, blank=True)
    archetype = models.CharField("Archetype", max_length=1, choices=ARCHETYPES, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]
    objects = UserManager()

    first_name = None
    last_name = None

    def __str__(self):
        return self.full_name or self.email

    @property
    def avatar_url(self):
        from django.templatetags.static import static
        return static(f"img/archetypes/{self.archetype}.jpg") if self.archetype else static("img/Ryupro.png")


class ConsentLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    policy_version = models.CharField(max_length=10, default="1.0")
    consented_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    platform = models.CharField(max_length=50, default="web")
