# STEP_4_NEW — PRIME ONLY: Viết Knowledge local và đồng bộ trạng thái

## Mục tiêu

STEP 3 NEW đã tạo cấu trúc Knowledge đầy đủ theo ngôn ngữ trong chính module
(`--lang vi` mặc định; dùng cùng một `--lang` ở STEP 3 và STEP 4):
`content/knowledge/<lang>/{menu.yml,menu-level-1-slug.yml,menu-detail-status.yml,
<index>.<chapter-slug>/<lesson-slug>.{yml,md}}`.

**Schema STEP 3 NEW:** YAML bài học chỉ có `menuLevel1`, `menuLevel2`,
`status`; không có `note.yml`, `topic`, `specialNote`. Để Worker có đủ ngữ
cảnh, **Prime trực tiếp đọc ba giá trị SERVICE_NAME, SERVICE_NAME_DESCRIBE,
SPECIAL_NOTE từ module-info.json và gửi nguyên nội dung cho Worker ở mỗi
lượt giao bài**. Không gửi file metadata, không yêu cầu Worker tự đọc metadata.

**STEP 4 NEW không PREPARE lại file, không dùng Google Sheets, không gọi Gradle,
không tạo rowXX/manifest hay nội dung Summary.** Chỉ giao Worker viết
Markdown cho từng bài, sau đó cập nhật `status: WRITTEN` trong YAML của bài.
Prime đọc bảng tổng hợp sau `refresh_menu_status.py` để giao tiếp/khôi phục;
cuối STEP xác minh mọi bài đã được viết ở mức kỹ thuật. QA Knowledge chuyên sâu
là STEP 6 NEW; STEP 5 NEW tạo Quiz, Interview và Case Study trước đó.

**Bộ STEP_4.md và worker/STEP_4_WORKER.md cũ giữ nguyên cho workflow legacy**.
Khi chạy workflow NEW, các chỉ dẫn legacy về Sheet/J3/rowXX/Gradle không được
áp dụng cho tài liệu Knowledge mới; không tự chuyển sang STEP 5 legacy.

## 0. Prime preflight

1. Đọc `GENERAL_AGENT_RULES.md`, toàn bộ `rules/`,
   `STEP_4_NEW.md`, `worker/STEP_4_WORKER_NEW.md`; giới hạn pool
   **NORMAL tối đa 3**, SPECIAL chỉ N do người dùng chỉ rõ, ưu tiên Worker
   SLEEPING và một bài/Worker/lượt. Theo dõi ownership, QA/readback, BLOCKER.
2. Xác định duy nhất `<MODULE_LOCATION>` nằm trong `java-learning/learning-platform-data/module/`,
   có `module_activate.json.isModule = true` và `module-info.json`. Xác nhận
   `MODULE_LANGUAGE.VALUE` có ngôn ngữ được giao. **Prime** lấy nguyên giá trị
   `SERVICE_NAME.VALUE`, `SERVICE_NAME_DESCRIBE.VALUE` và `SPECIAL_NOTE.VALUE`
   **từ module-info.json của chính module**. Không lấy từ `master.json`,
   `note.yml` hoặc suy từ tên thư mục. `SPECIAL_NOTE.VALUE` có thể rỗng hoặc
   nhiều dòng; giữ nguyên văn, không tự tóm tắt.
3. Đảm bảo `script/module-generate/step3/generate_menu_detail.py` đã chạy: tồn tại `menu-detail-status.yml`,
   đủ chapter và đủ cặp `<slug>.yml` / `<slug>.md`.
4. Trước khi giao việc, chạy refresh `--dry-run` để kiểm tra cấu trúc;
   chạy refresh thật nếu cần đồng bộ lại tiến độ sau các Worker trước đó.
   Không tự reset bài đã viết.

## 1. Lệnh Python (chạy ở `java-learning/learning-platform-data`)

```powershell
# Kiểm tra toàn bộ cấu trúc và xem số status cần cập nhật (không ghi file).
python script/module-generate/step4/refresh_menu_status.py --module "module/platform/development/programming/paradigm/data-oriented" --lang vi --dry-run

# Đồng bộ status từ YAML bài học vào menu-detail-status.yml.
python script/module-generate/step4/refresh_menu_status.py --module "module/platform/development/programming/paradigm/data-oriented" --lang vi

# Completion gate kỹ thuật: tất cả bài phải hoàn thành và Markdown không rỗng.
python script/module-generate/step4/refresh_menu_status.py --module "module/platform/development/programming/paradigm/data-oriented" --lang vi --verify
```

**Nguồn chuẩn status:** `<chapter>/<lesson>.yml`, trường `status`.
`menu-detail-status.yml` là **bản tổng hợp dẫn xuất**, không phải nơi Worker
sửa trực tiếp. Refresh giữ nguyên `slug`, `title`, thứ tự `childs`,
format văn bản không liên quan và mọi file Markdown.

- `status: ""` = bài chưa hoàn tất, dù .md đã có nội dung đang viết dở.
- `status: WRITTEN` = Worker đã lưu Markdown thành công và readback.
- Status không rỗng mà Markdown trống/thiếu, info sai, slug/title/thứ tự không
  khớp, file dư hoặc thiếu → **BLOCKER, không ghi một phần**.
- Refresh sao chép **nguyên status**; khi `--verify`, chỉ các trạng thái
  `WRITTEN` (hoặc legacy `UPLOADED`, `SKIPPED_EXISTING` với Markdown hợp lệ)
  được coi là hoàn thành. STEP 4 NEW không sinh status legacy.
- `--verify` chỉ kiểm tra hoàn tất lưu trữ, **không QA kiến thức và code**.
  Không chia bài theo giới hạn Google Sheets C:N.
- `--dry-run` không đổi bất kỳ file nào. Khi status không đổi, refresh không
  ghi lại file tổng hợp. Lỗi dữ liệu được kiểm tra trước khi thay thế file
  tổng hợp bằng atomic rename.

## 2. Prime điều phối Worker (một bài/lượt)

Prime đọc lại `menu-detail-status.yml` sau refresh, lập queue tất cả
`childs[].status == ""`, ánh xạ:
- Parent slug + vị trí chapter (bắt đầu từ 1): `1.overview/`.
- Child slug trong bảng: `overview-001`.
- Hai file đúng sở hữu: `1.overview/overview-001.yml`,
  `1.overview/overview-001.md`.

**BẮT BUỘC giao việc gối đầu (rolling dispatch), không chờ đủ một đợt:**
Prime giữ các Worker đủ điều kiện làm việc liên tục trong giới hạn pool
(NORMAL tối đa 3; SPECIAL tối đa N do người dùng chỉ định). Ngay khi **bất kỳ**
Worker nào báo xong **một bài**, Prime nghiệm thu kết quả và readback của riêng
bài đó, xác nhận Worker đã release ownership và về SLEEPING/Idle, rồi **giao
ngay bài PENDING tiếp theo cho chính Worker đó** nếu còn bài hợp lệ. **Không
đợi** các Worker ACTIVE khác hoàn thành để giao lượt tiếp theo. Ví dụ, Worker 1
xong bài A và nhận bài D trong lúc Worker 2/3 vẫn viết bài B/C.

Prime theo dõi riêng `PENDING`, `ACTIVE`, `COMPLETED` và
`BLOCKER/FAILED`; một bài có `status: ""` nhưng đang thuộc Worker ACTIVE
**không được giao lại**. Chỉ những bài PENDING chưa có owner mới được phân công.
Không giao đồng thời nhiều bài cho một Worker; không vượt giới hạn pool.

**Ở MỖI lượt giao bài**, Prime tự truyền **nguyên nội dung** ba giá trị
`SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` đã đọc trong preflight
từ `module-info.json`. Đây là dữ liệu đầu vào **trong lời giao việc**, **không
đính kèm hoặc truyền đường dẫn file module-info.json** cho Worker. Prime vẫn
giao hai đường dẫn file bài học để Worker đọc YAML và viết Markdown/status;
không gửi Google Sheets row.

Mẫu handoff (thay placeholder bằng **giá trị thật**, không đưa tên biến làm
nội dung; `SPECIAL_NOTE` nhiều dòng cần ranh giới khối rõ ràng):

```text
MODULE_LOCATION=<ABSOLUTE_MODULE_LOCATION>
LANG=<lang>
SERVICE_NAME=<nội dung của SERVICE_NAME.VALUE>
SERVICE_NAME_DESCRIBE=<nội dung của SERVICE_NAME_DESCRIBE.VALUE>
SPECIAL_NOTE=<nguyên văn toàn bộ SPECIAL_NOTE.VALUE, kể cả khi rỗng hoặc nhiều dòng>
INFO=<ABSOLUTE_MODULE_LOCATION>/content/knowledge/<lang>/1.overview/overview-001.yml
MARKDOWN=<ABSOLUTE_MODULE_LOCATION>/content/knowledge/<lang>/1.overview/overview-001.md
INSTRUCTIONS=<java-learning>/learning-platform-data/module-generate-agent/worker/STEP_4_WORKER_NEW.md
```

Prime yêu cầu Worker sử dụng cả ba giá trị để hiểu đúng chủ đề, phạm vi và
ghi chú; coi SPECIAL_NOTE là **ngữ cảnh nội dung**, không phải quyền mở rộng
phạm vi ghi. Worker không được tự đọc `module-info.json`, `master.json` hoặc
các YAML của bài khác để suy metadata.

Worker chỉ được ghi Markdown được giao và **duy nhất field** `status` trong
YAML bài tương ứng. Prime không giao cùng một bài cho hai Worker đang ACTIVE;
không tính .md khác trạng thái là đã xong; không tự QA/refactor nội dung chuyên
môn trong STEP 4.

**Sau từng Worker báo kết quả**, kể cả khi những Worker khác còn ACTIVE
(hoặc khi Prime restart):
1. Xác minh report, readback Markdown/status, cặp file có thật và Worker đã
   release ownership. Nếu BLOCKER/FAILED, ghi nhận đúng bài và xử lý theo
   bằng chứng; không coi Worker đó là SLEEPING sẵn sàng nhận việc.
2. Prime chạy `script/module-generate/step4/refresh_menu_status.py` để đồng
   bộ trạng thái tổng hợp và readback `menu-detail-status.yml`. Prime thực
   hiện refresh tuần tự, không cho nhiều tiến trình cùng ghi bảng tổng hợp.
3. Nếu Worker đã hoàn thành hợp lệ và đang SLEEPING/Idle, **giao ngay** một bài
   `status: ""` chưa có owner cho Worker đó; giữ nguyên các bài Worker khác
   đang ACTIVE. Không chờ đủ 3 Worker hay chờ cả đợt mới giao tiếp.
4. Tiếp tục quy trình trên đến khi không còn bài PENDING chưa được giao;
   xử lý BLOCKER theo từng bài, không reset hoặc overwrite bài có status khác rỗng.

**Chỉ khi** không còn bài PENDING, **không còn Worker ACTIVE** và mọi bài đã
được nghiệm thu, chạy `refresh_menu_status.py --verify`, readback các status
và xác nhận **không còn worker ACTIVE/blocked**. Queue hết bài chưa giao nhưng
vẫn còn Worker ACTIVE chưa được xem là hoàn tất. Báo:
`MODULE_LOCATION`, `SERVICE_NAME`, `TOTAL`, `PENDING`, `WRITTEN`,
`REFRESH`, `VERIFY`, `WORKER_OWNERSHIP`, `READBACK`, `BLOCKERS`.

**Không tự checkpoint** `master.json.CURRENT_STEP.VALUE` hoặc Google Sheets
J3 theo luồng legacy; checkpoint của workflow NEW (nếu áp dụng) chỉ thao tác
`module-info.json.CURRENT_STEP.VALUE` sau khi đủ gate và theo chỉ dẫn Prime
được chốt. Không commit, push,
publish, import Oracle, chạy STEP 5 cũ hoặc xóa dữ liệu.

## 3. Nguồn chuẩn SPECIAL_NOTE

`SPECIAL_NOTE` chỉ lấy từ `module-info.json.SPECIAL_NOTE.VALUE`, do Prime gửi
**dưới dạng nội dung** khi giao từng bài học. Nếu ghi chú cần thay đổi, Prime
phải lấy lại giá trị mới nhất trước khi giao lượt tiếp theo; Worker đang viết
phải được điều phối lại nếu ngữ cảnh đã thay đổi. Không tạo `note.yml` và
không thêm `topic`/`specialNote` vào YAML bài học.

Script `script/module-generate/knowledge-modify-special-note.py` thuộc luồng
legacy, **không phải bước của STEP 4 NEW** và không được Prime gọi trên
Knowledge theo schema mới.
