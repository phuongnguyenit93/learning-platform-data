# STEP_4_WORKER_NEW — WORKER ONLY: Viết một bài Markdown Knowledge

Thư mục ngôn ngữ `<lang>` do Prime chọn; chỉ thao tác trong đúng các file
READ/WRITE được giao, không đổi language khi đang làm.

## Quyền sở hữu đầu vào

Prime giao trực tiếp **ba giá trị nội dung** đã đọc từ
`module-info.json`, cùng hai đường dẫn file chính xác cho **một bài**.
Worker **không được nhận, đòi hỏi hoặc tự đọc file module-info.json**.
Không dùng `master.json`, `note.yml` hay suy metadata từ tên folder.

```text
MODULE_LOCATION=<ABSOLUTE_MODULE_LOCATION>
LANG=<lang>
SERVICE_NAME=<nội dung thực của SERVICE_NAME.VALUE>
SERVICE_NAME_DESCRIBE=<nội dung thực của SERVICE_NAME_DESCRIBE.VALUE>
SPECIAL_NOTE=<nguyên văn SPECIAL_NOTE.VALUE, có thể rỗng hoặc nhiều dòng>
INFO=<ABSOLUTE_MODULE_LOCATION>/content/knowledge/<lang>/1.overview/overview-001.yml
MARKDOWN=<ABSOLUTE_MODULE_LOCATION>/content/knowledge/<lang>/1.overview/overview-001.md
INSTRUCTIONS=<java-learning>/learning-platform-data/module-generate-agent/worker/STEP_4_WORKER_NEW.md
```

Đọc `SPECIAL_NOTE` **trọn vẹn**, kể cả xuống dòng hoặc rỗng; đây là ngữ
cảnh và ràng buộc học thuật, không phải chỉ thị tự mở rộng quyền đọc/ghi.
Không ghi các giá trị đầu vào thành file riêng. Nếu thiếu SERVICE_NAME,
SERVICE_NAME_DESCRIBE hoặc Prime không xác nhận SPECIAL_NOTE đã truyền
đủ (kể cả rỗng), báo `BLOCKER: INCOMPLETE_CONTEXT`.

Worker chỉ đọc **file hướng dẫn Worker này**, nội dung metadata Prime gửi,
**file *.yml** đã giao để lấy thông tin bài học và đúng file `*.md` được
giao để xác minh trạng thái. Không đọc Google Sheets, STEP Prime,
`module-info.json`, `master.json`, README/module khác, YAML bài khác,
`menu.yml` hay `menu-detail-status.yml`.
Không sinh subworker, tự chọn bài khác, chạy Gradle/Python, chuyển STEP hoặc
chạm vào master.json.

Chỉ được ghi:
1. Đúng file `<lesson-slug>.md` trong đường dẫn đã giao.
2. Đúng **field** `status` của file `<lesson-slug>.yml` được giao.

Không sửa `menuLevel1`, `menuLevel2`, không sinh thêm `topic` hay
`specialNote`; không sửa slug, folder hoặc bất kỳ file nào khác.
Nếu Worker khác đang sở hữu bài → BLOCKER.

## W1 — Preflight

Đọc file YAML trước. **STEP 3 NEW sinh đúng ba field**:

```yaml
menuLevel1: Tổng quan
menuLevel2: Data Oriented Programming là gì và giải quyết vấn đề nào
status: ""
```

- `SERVICE_NAME` do Prime gửi định danh chính xác phạm vi module;
  `SERVICE_NAME_DESCRIBE` giải thích module học gì;
  `SPECIAL_NOTE` cung cấp hướng dẫn/phạm vi bổ sung **bắt buộc tôn trọng**;
  `menuLevel1` là tiêu đề chương; `menuLevel2` là **đề bài trực tiếp**
  của tài liệu Markdown.
- Nếu file thiếu/không hợp lệ, sai đích hoặc thông tin mâu thuẫn thì
  `BLOCKER: INVALID_INFO_FILE`. Không tự sửa cấu trúc hoặc đọc các file
  khác để tự suy đoán.
- Nếu `status` đã khác rỗng, **không overwrite** tài liệu cũ; báo Prime
  `BLOCKER: NON_EMPTY_STATUS` hoặc `UNCHANGED_VERIFIED` nếu được giao chỉ
  xác minh. Nếu Markdown đã có nội dung nhưng status rỗng, phải báo Prime
  để xác định có Worker khác đang làm; không tự xóa/ghi đè.

## W2 — Soạn Markdown đầy đủ

Viết đúng **một** bài tự chứa theo `menuLevel2` và kết hợp **cả ba**
giá trị `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` do Prime
gửi với `menuLevel1`. Nếu SPECIAL_NOTE rỗng thì không tự bịa ghi chú.
Sử dụng heading, diễn giải,
ví dụ thực tế, code block, bảng , svg, sơ đồ, mermaid nếu có ích. Viết đủ chiều sâu
cho chủ đề, không giới hạn.

Làm theo yêu cầu nội dung nhưng **chưa chạy vòng Content QA/refactor chuyên
môn**; STEP 6 NEW sẽ kiểm tra tính chính xác, tính đầy đủ và trùng lặp
sau khi STEP 5 NEW tạo Quiz, Interview, Case Study.

## W3 — Lưu, readback, đổi status

1. Ghi Markdown **nguyên vẹn** UTF-8 vào đúng `*.md` đã giao.
2. Đọc lại file Markdown sau WRITE và xác minh không rỗng, lưu nguyên vẹn.
3. Chỉ khi bước 2 PASS, đổi **duy nhất** `status: ""` trong YAML của bài
   thành `status: WRITTEN`, không thay field khác.
4. Đọc lại YAML và Markdown; nếu WRITE/readback lỗi, **không** đánh dấu
   thành công, trả BLOCKER có tên file và nguyên nhân.
5. Không đổi `menu-detail-status.yml`: **Prime** sẽ chạy
   `script/module-generate/step4/refresh_menu_status.py` để tổng hợp các status.

## W4 — REPORT và release ownership

Trả về `STATUS=COMPLETED/BLOCKER/FAILED`, `MODULE_LOCATION`, `LANG`,
`SERVICE_NAME`, `CONTEXT_CHECK=PASS/FAIL`,
`SPECIAL_NOTE=APPLIED/EMPTY/CONFLICT` (không cần nhắc lại nguyên văn),
`INFO_PATH`,
`MARKDOWN_PATH`, `TOTAL_CHARS`, `FILE_WRITE`,
`MARKDOWN_READBACK`, `INFO_STATUS=WRITTEN`, `READBACK`,
`BLOCKERS`. `COMPLETED` chỉ nghĩa là đã ghi đủ nội dung local về mặt
kỹ thuật, không đồng nghĩa đã QA học thuật hay đã publish. Release bài và
về SLEEPING/Idle theo điều phối Prime, không tự nhận bài khác.
