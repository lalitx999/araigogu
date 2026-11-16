from django.urls import path

from . import views

urlpatterns = [
    path("about/", views.about, name="about"),
    path("faq/", views.faq, name="faq"),
    path("guides/", views.guides, name="guides"),
    path("guides/<slug:slug>/", views.guide, name="guide"),
    path("offline/", views.offline, name="offline"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap"),
    path("llms.txt", views.llms_txt, name="llms"),
    path("llms-full.txt", views.llms_full_txt, name="llms_full"),
    path("llm.txt", views.llms_txt),            # common misspelling, same file
    path("llm-full.txt", views.llms_full_txt),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
]
