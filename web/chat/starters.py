"""Learning topics shown in the sidebar and as suggestion cards on the empty chat (Bootstrap Icons only)."""

TOPICS = [
    {"key": "grammar", "icon": "bi-spellcheck", "title": "ตรวจไวยากรณ์",
     "hint": "แก้ประโยคให้ถูกและเป็นธรรมชาติ พร้อมเหตุผล",
     "prompt": "ช่วยตรวจไวยากรณ์และเกลาประโยคนี้ให้เป็นธรรมชาติ พร้อมอธิบายว่าผิดตรงไหนครับ: "},
    {"key": "conversation", "icon": "bi-chat-square-text", "title": "ฝึกบทสนทนา",
     "hint": "จำลองสถานการณ์จริง สลับกันพูดทีละประโยค",
     "prompt": "จำลองสถานการณ์สั่งอาหารที่ร้านอาหาร ให้พี่ริวเป็นพนักงาน แล้วผมเป็นลูกค้า เริ่มได้เลยครับ"},
    {"key": "vocabulary", "icon": "bi-journal-text", "title": "คำศัพท์และสำนวน",
     "hint": "ศัพท์ตามหัวข้อ พร้อมคำอ่านและประโยคตัวอย่าง",
     "prompt": "สอนคำศัพท์ที่ใช้บ่อย 10 คำในหัวข้อการเดินทาง พร้อมคำอ่าน คำแปล และประโยคตัวอย่างครับ"},
    {"key": "exam", "icon": "bi-mortarboard", "title": "เตรียมสอบ",
     "hint": "JLPT, TOEIC, HSK ข้อสอบเสมือนจริงพร้อมเฉลย",
     "prompt": "ขอข้อสอบเสมือนจริง 5 ข้อตามระดับของผม แบบปรนัย แล้วเฉลยพร้อมอธิบายทีละข้อครับ"},
    {"key": "explain", "icon": "bi-lightbulb", "title": "อธิบายแบบเจาะลึก",
     "hint": "เทียบโครงสร้างที่สับสนบ่อย ทีละขั้น",
     "prompt": "ช่วยอธิบายความต่างของโครงสร้างที่คนไทยสับสนบ่อย พร้อมตัวอย่างและแบบฝึกหัดสั้นๆ ครับ"},
    {"key": "image", "icon": "bi-image", "title": "แปลจากรูปภาพ",
     "hint": "ถ่ายรูปการบ้านหรือหน้าหนังสือส่งมาได้เลย",
     "prompt": "ช่วยแปลและสรุปคำศัพท์จากรูปนี้ พร้อมอธิบายไวยากรณ์ที่ใช้ครับ", "needs_image": True},
]

# Shown first in the language picker; the rest follow alphabetically by Thai name.
POPULAR_LANGUAGES = ["ja", "en", "zh", "ko", "fr", "de", "es"]
