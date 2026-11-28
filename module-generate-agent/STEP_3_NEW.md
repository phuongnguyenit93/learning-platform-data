# STEP_3_NEW — PRIME ONLY: Menu hai cấp và skeleton bài học

## Mục tiêu

STEP 3 NEW thiết kế Menu **hai cấp**, dành cho việc viết Markdown document sau này, rồi tạo skeleton bài học trong `<MODULE_LOCATION>/content/knowledge/<lang>/`. Không đọc/ghi Google Sheets, Gradle hoặc database.

**Thay đổi mới:** Không tạo `note.yml`; không sinh `topic` hoặc `specialNote` trong YAML của bài học. **Không xóa hay thay đổi những file/trường cũ đã tồn tại**; việc dọn dữ liệu cũ sẽ có yêu cầu riêng.

Hai script chính:

- `script/module-generate/step3/generate_menu_skeleton.py`: khởi tạo `menu.yml` và `menu-level-1-slug.yml` nếu chưa có.
- `script/module-generate/step3/generate_menu_detail.py`: kiểm tra Menu và Slug, sinh `menu-detail-status.yml` cùng các cặp YAML/Markdown của từng bài. Các helper dùng chung và xử lý field detail được gộp trực tiếp trong file này.

## 0. Prime preflight

1. Đọc toàn văn STEP này, hai file `worker/STEP_3_WORKER_PHASE_1_NEW.md`, `worker/STEP_3_WORKER_PHASE_2_NEW.md` và quy định chung về quyền sở hữu, pool Worker, QA và readback.
2. Xác minh chính xác thư mục module bên trong `learning-platform-data/module/`. Với workflow NEW, module cần có `module-info.json` và `module_activate.json` với boolean `isModule: true`.
3. Đọc **giá trị nội dung** `SERVICE_NAME.VALUE`, `SERVICE_NAME_DESCRIBE.VALUE`, `SPECIAL_NOTE.VALUE` từ `module-info.json`. Không lấy dữ liệu thay thế từ tên folder hoặc `master.json`. `SERVICE_NAME` phải theo UPPER_SNAKE_CASE. `SPECIAL_NOTE` có thể rỗng; nếu có nội dung phải chuyển **nguyên văn**, bao gồm xuống dòng, cho Worker.
4. Chọn `<lang>` phù hợp với module (mặc định `vi`; có thể là `en`). Giữ cùng ngôn ngữ trong cả hai phase và khi chạy script.
5. Không xóa, tự di chuyển hoặc ghi đè `content/knowledge/` cũ. Nếu có layout flat cũ hay nội dung xung đột, báo BLOCKER.

## 1. Prime chạy skeleton

Chạy từ root `learning-platform-data`:

```powershell
python script/module-generate/step3/generate_menu_skeleton.py --module "<MODULE_LOCATION>" --lang vi --dry-run
python script/module-generate/step3/generate_menu_skeleton.py --module "<MODULE_LOCATION>" --lang vi
```

Chỉ tạo hai file còn thiếu, với nội dung khởi tạo `menu: []`:

```text
content/knowledge/<lang>/
  menu.yml
  menu-level-1-slug.yml
```

Script **không tạo `note.yml`**, không nhận `--special-note`, không ghi đè file đã có. `note.yml` legacy hiện hữu, nếu có, phải được giữ nguyên.

## 2. Phase 1 — Worker thiết kế Menu hai cấp

Prime gửi đường dẫn và **nội dung** metadata, không đưa file metadata:

```text
MODULE_LOCATION=<ABSOLUTE_MODULE_LOCATION>
LANG=<lang>
SERVICE_NAME=<SERVICE_NAME.VALUE>
SERVICE_NAME_DESCRIBE=<SERVICE_NAME_DESCRIBE.VALUE>
SPECIAL_NOTE=<nguyên văn SPECIAL_NOTE.VALUE, có thể nhiều dòng hoặc rỗng>
READ=<MODULE_LOCATION>/content/knowledge/<lang>/menu.yml
WRITE=<MODULE_LOCATION>/content/knowledge/<lang>/menu.yml
INSTRUCTIONS=<DATA_ROOT>/module-generate-agent/worker/STEP_3_WORKER_PHASE_1_NEW.md
```

Đề bài bắt buộc:

> Thiết kế cho tôi Menu **hai cấp** của chủ đề module. Menu dùng để viết các Markdown document, nên cần **đầy đủ và chi tiết**. Menu cấp 1 viết **ngắn** vì là tiêu đề; menu cấp 2 là các bài học cụ thể.

Worker dùng nội dung `SERVICE_NAME_DESCRIBE` và `SPECIAL_NOTE` để giới hạn phạm vi, không sinh Markdown ở phase này. Schema `menu.yml`:

```yaml
menu:
  - level1: "Tư duy OOP"
    level2:
      - "OOP là gì?"
      - "Đối tượng và trạng thái"
  - level1: "Thực hành OOP"
    level2:
      - "Thiết kế lớp"
```

Không thêm `index`, `slug` hoặc `status` vào `menu.yml`. Worker báo QA/readback và release ownership. **Prime nghiệm thu Phase 1 trước khi giao Phase 2.**

## 3. Phase 2 — Worker đặt slug tiếng Anh

Sau Phase 1 QA PASS, Prime truyền lại nội dung metadata như trên, cùng:

```text
READ=<MODULE_LOCATION>/content/knowledge/<lang>/menu.yml,<MODULE_LOCATION>/content/knowledge/<lang>/menu-level-1-slug.yml
WRITE=<MODULE_LOCATION>/content/knowledge/<lang>/menu-level-1-slug.yml
INSTRUCTIONS=<DATA_ROOT>/module-generate-agent/worker/STEP_3_WORKER_PHASE_2_NEW.md
```

Worker đọc toàn bộ `level1`/`level2` để hiểu ý nghĩa của chapter; mỗi cấp 1 có đúng một slug **theo ngữ nghĩa tiếng Anh, tương đối ngắn gọn**, dùng lowercase kebab-case, không trùng và không dùng tên Windows bị cấm. Ưu tiên khoảng **40 ký tự trở xuống** nếu vẫn truyền đạt đủ nghĩa (giới hạn kỹ thuật hiện tại là 80); không kéo dài slug bằng cách lặp tiền tố tên module hoặc ghép máy móc từ tiếng Việt không dấu với tiếng Anh. Chọn cách diễn đạt tiếng Anh đúng với nội dung chương, không đơn thuần phiên âm/bỏ dấu tiêu đề. `title` trùng nguyên văn tiêu đề; `index` bắt đầu bằng 0 và tăng liên tiếp.

```yaml
menu:
  - title: "Tư duy OOP"
    slug: oop-basic
    index: 0
  - title: "Thực hành OOP"
    slug: oop-practice
    index: 1
```

Worker chỉ sửa `menu-level-1-slug.yml`. Prime QA toàn bộ title/slug/index trước khi chạy generator detail.

## 4. Prime chạy generate_menu_detail.py

```powershell
python script/module-generate/step3/generate_menu_detail.py --module "<MODULE_LOCATION>" --lang vi --dry-run
python script/module-generate/step3/generate_menu_detail.py --module "<MODULE_LOCATION>" --lang vi
```

Script xác minh schema/thứ tự/slug/đường dẫn, tạo cây:

```text
content/knowledge/<lang>/
  menu.yml
  menu-level-1-slug.yml
  menu-detail-status.yml
  1.oop-basic/
    oop-basic-001.yml
    oop-basic-001.md
    oop-basic-002.yml
    oop-basic-002.md
  2.oop-practice/
    oop-practice-001.yml
    oop-practice-001.md
```

**YAML bài học sinh mới chỉ có ba field**:

```yaml
menuLevel1: "Tư duy OOP"
menuLevel2: "OOP là gì?"
status: ""
```

Không tạo `topic` hay `specialNote`. Markdown `.md` mới khởi tạo rỗng để STEP 4 viết. Bảng `menu-detail-status.yml` sinh **schema STEP 5 NEW** với `slug`, `title`, `status`, `difficult`, `focus` (Trọng tâm), `problemSolved` (Vấn đề giải quyết), `mechanism` (Cơ chế), `applicationValue` (Giá trị ứng dụng) và `summary` (Summary Markdown từng bài):

```yaml
menu:
  - slug: oop-basic
    title: "Tư duy OOP"
    childs:
      - slug: oop-basic-001
        title: "OOP là gì?"
        status: ""
        difficult: ""
        focus: ""
        problemSolved: ""
        mechanism: ""
        applicationValue: ""
        summary: ""
```

**Tương thích dữ liệu cũ:** Nếu `note.yml` đã tồn tại, không xóa. Nếu YAML bài học hiện có `topic` hoặc `specialNote`, giữ nguyên dữ liệu và không viết lại những field đó; đồng thời không sinh chúng vào YAML mới. Nội dung Markdown, status và metadata do người viết được bảo toàn. Sai `menuLevel1`/`menuLevel2`, slug hay có file generated dư → BLOCKER. Với file detail đã có schema mới nhưng thiếu field, generator chỉ bổ sung khóa còn thiếu, không ghi đè giá trị cũ. Với file detail **đã tồn tại mang các khóa cũ** `keyQuestion`, `valueForModule`, `mindset`: **không tự đổi tên, thêm 4 khóa thay thế hay sửa file hiện có**; migration riêng sẽ làm sau theo yêu cầu.

STEP 3 NEW **không tạo** object `chapter`, `roadmap` hoặc `comparisonMarkdown`. STEP 5 NEW sẽ làm việc trên các bài thuộc cùng Menu cấp 1 để cung cấp dữ liệu so sánh có cấu trúc; frontend có thể dựng bảng sau này. Không sửa những `menu-detail-status.yml` đã tồn tại trong `module/` ở lượt đồng bộ thiết kế này.

## 5. Prime QA

- Hai phase đã QA/readback PASS, Menu hợp lý, không lặp, slug tiếng Anh đúng ngữ nghĩa và tương đối ngắn, index liên tục.
- Mỗi menu cấp 2 tạo đúng một cặp `.yml`/`.md`; số chapter và bài đúng với Menu.
- **File YAML mới** có chính xác `menuLevel1`, `menuLevel2`, `status`. Không tạo `note.yml` và không sinh `topic`/`specialNote`.
- **Dữ liệu legacy không bị dọn/xóa**; rerun idempotent và bảo toàn nội dung người viết.
- Bảng detail có đúng identity và các field tương ứng. `--dry-run` không ghi. Không sửa module/lang khác.

Chỉ coi STEP 3 hoàn thành khi cả hai Worker phase, generator và Prime QA đạt PASS. Không tự cập nhật Sheets/Gradle/database, không commit, push hoặc tự chạy STEP tiếp.
