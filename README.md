# Arai Go Gu (rebuild)

เว็บเรียนภาษากับ "พี่ริว" + ชุมชนโซเชียล สร้างใหม่ทั้งหมดจากโปรเจกต์ PHP เดิม

```
web/         Django 5.2 LTS  — auth, chat, community, admin, templates (เจ้าของ MySQL)
ai-service/  FastAPI         — /v1/chat, /v1/moderate, /v1/comment (stateless, ไม่ต่อ DB)
deploy/      Caddyfile (HTTPS)        scripts/  smoke.sh, backup.sh
docker-compose.yml       dev  (db + ai-service + web/runserver)
docker-compose.prod.yml  prod (db + ai-service + web/gunicorn + caddy; DB ไม่เปิดพอร์ต)
```

## กฎของโปรเจกต์

- **ดีไซน์**: โทนขาว ดำ เทา กระจกฝ้า (โหมดสว่าง/มืด/ตามระบบ) ใช้ไอคอน Bootstrap Icons เท่านั้น ห้ามใช้อิโมจิ
  - ทุกหน้าที่ต้องล็อกอินอยู่ในกรอบเดียวกับแชท (`templates/app/base.html` + `_sidebar.html`): เมนูซ้ายมีแชทใหม่ ชุมชน ความก้าวหน้า หัวข้อการเรียน ประวัติแชท และโปรไฟล์ด้านล่าง
  - สไตล์กลางอยู่ที่ `web/static/css/app.css` (โทเคนสี ปุ่ม แผง ฟอร์ม) ส่วนเฉพาะหน้าอยู่ที่ `web/static/css/pages/` (chat_app, progress, community, settings, auth, about)
  - หน้าเข้าสู่ระบบ/สมัคร/รีเซ็ตรหัส/429/404/500 ใช้ `accounts/auth_base.html`; หน้า About (`/about/`) เป็นหน้าแนะนำแยก
  - จุดที่เปลี่ยนจากของเดิมโดยตั้งใจ: ปิดช่องโหว่ XSS ในแชท, ตัวเลข "Trending" เป็นจำนวนโพสต์จริง, ตัดปุ่ม Follow/ตัวเลข Followers และลิงก์ที่ไม่มีปลายทางออก (ยังไม่มีระบบ follow)
- **ห้าม CDN**: Bootstrap 5.3.8 (ไฟล์ที่คุณให้), Bootstrap Icons 1.11.1, ฟอนต์ Kanit/Outfit/Inter/Noto Sans Thai และ qrcode-generator (SweetAlert2 กับ AOS ยังอยู่ใน vendor แต่ไม่มีหน้าไหนใช้แล้ว)
  อยู่ใน `web/static/vendor/` และ `web/static/fonts/` ทั้งหมด บังคับด้วย CSP `default-src 'self'` (บล็อกทุก host ภายนอก) + เทสต์สแกนหา URL ภายนอก
  + เทสต์เรนเดอร์ทุกหน้าแล้วเช็คว่าไฟล์ `/static/...` ที่อ้างถึงมีจริง ข้อยกเว้นเดียวคือลิงก์บริจาค `tipme.in.th` (hyperlink + ข้อมูลใน QR ไม่ใช่ไฟล์ที่โหลดมาใช้)
  CSP อนุญาต inline script/style เพราะดีไซน์เดิมใช้ `onclick=""`, `<script>` และ `style=""` จำนวนมาก
- **แหล่งที่มาของไฟล์ในเครื่อง**: npm registry (bootstrap-icons 1.11.1, @fontsource/kanit 5.3.0, @fontsource-variable/outfit และ inter 5.3.0, qrcode-generator 1.4.4)
  และคัดลอกจากโปรเจกต์อื่นในเครื่องคุณ (SweetAlert2 11.26.25, AOS, Noto Sans Thai)
- **AJAX แบบเสริม** (`static/js/community.js`, ปิด JS แล้วฟอร์มยังทำงานปกติ): ไลก์/รีโพสต์/บุ๊กมาร์กไม่รีโหลดหน้า, ปุ่ม "โหลดเพิ่ม" ใน feed,
  คอมเมนต์พี่ริวถูกสร้างเบื้องหลังหลังโพสต์ (`POST /community/post/<id>/ryu/`) ผู้โพสต์ไม่ต้องรอ AI; ส่วนอื่นใช้ JS เดิมของแต่ละหน้า
- กฎเดิมที่คงไว้: โพสต์ได้วันละ 1 โพสต์, ตัวละคร A (พี่ริว) เลือกได้เฉพาะแอดมิน, โพสต์ที่ AI ขอให้แก้จะขึ้นหน้าต่าง "พี่ริวขอแนะนำ..." ใน feed

## รันบน localhost (ไม่ใช้ docker)

```bash
scripts/dev.sh setup     # ครั้งแรก: สร้าง .venv, ติดตั้ง, migrate (ใช้ SQLite ไม่ต้องตั้ง DB)
scripts/dev.sh           # เปิด ai-service (:8001) + web (:8000)  กด Ctrl+C หยุดทั้งคู่
scripts/dev.sh user      # สร้างแอดมิน
scripts/dev.sh test      # เทสต์ทั้งหมด
```

- เว็บ http://localhost:8000 · แอดมิน /admin/ · ai-service http://localhost:8001/health
- secret อ่านจาก `.env` (สุ่มใหม่ ไม่ได้ copy จากโปรเจกต์เดิม) ใส่ `OPENAI_API_KEY` **ตัวใหม่** เพื่อให้ AI ตอบจริง
  ถ้าเว้นว่าง: แชทแจ้งว่า AI ยังไม่พร้อม (ไม่บันทึกอะไร), โพสต์ลงได้แต่ติด `needs_review` ให้แอดมินตรวจ, ไม่มีคอมเมนต์พี่ริว
- ตรวจ end-to-end 17 ข้อ (ตอนเปิดเซิร์ฟเวอร์อยู่): `scripts/smoke.sh`
- ใช้ MySQL บน localhost แทน SQLite: `USE_MYSQL=1 scripts/dev.sh setup` (ต้อง `brew install mysql pkg-config` และสร้าง DB/user ตามหัวไฟล์ `scripts/dev.sh`)

## docker (ทางเลือก ไม่จำเป็นสำหรับ localhost)

`docker-compose.yml` = dev (db + ai-service + web) ใช้เมื่ออยากได้ MySQL ในคอนเทนเนอร์: `docker compose up --build`
ยังไม่เคยถูกทดสอบ

## Production

1. `cp .env.prod.example .env.prod` บนเซิร์ฟเวอร์ แล้วกรอกทุกค่า (โดเมนต้องชี้ DNS มาที่เครื่องก่อน)
2. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
3. สำรองข้อมูล: `scripts/backup.sh` (ใส่ cron รายวัน เก็บ 14 ไฟล์ล่าสุด)
4. อีเมลลืมรหัสผ่านใช้ SMTP จาก `EMAIL_*` (ตอน dev พิมพ์ลง console)

## การป้องกันค่าใช้จ่าย/การโจมตี

| ที่ | จำกัด |
|---|---|
| โพสต์ | 10/ชม./ผู้ใช้ (ตัดก่อนเรียก OpenAI) |
| คอมเมนต์ | 30/ชม./ผู้ใช้ |
| คอมเมนต์พี่ริว | 20/ชม./ผู้ใช้ |
| แชท | `AI_DAILY_CHAT_LIMIT` (100)/วัน/ผู้ใช้ |
| ทดลองใช้แชท (ไม่สมัคร) | `GUEST_DAILY_CHAT_LIMIT` (10)/วัน/เบราว์เซอร์ และ `GUEST_DAILY_IP_LIMIT` (40)/วัน/IP, ไม่แนบรูป, ใช้ Groq เท่านั้น |
| สมัครสมาชิก | 5/ชม./IP |
| ล็อกอินผิด | 10/15 นาที/IP |
| ขอรีเซ็ตรหัส | 5/ชม./IP |
| ai-service | OpenAI พร้อมกันได้ 8 สาย |

ตัวนับเก็บใน MySQL (DatabaseCache) ใช้ร่วมกันได้ทุก worker; หลัง proxy ต้องตั้ง `DJANGO_BEHIND_PROXY=1` เพื่อใช้ IP จริง

## ยังไม่ได้ทำ (ตั้งใจ)

- ย้ายข้อมูลผู้ใช้/แชทเดิม (ต้องมี hasher รองรับ `$2y$`), ระบบ follow จริง (ปุ่ม Follow/ตัวเลข Followers เป็นแค่หน้าตา เหมือนของเดิม), notification, ยืนยันอีเมล
- ข้อจำกัดบน MySQL: "คอมเมนต์พี่ริวหนึ่งอันต่อโพสต์" บังคับด้วยโค้ด ไม่ใช่ unique index (MySQL ไม่รองรับ conditional index)
