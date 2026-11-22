# STEP_3_WORKER_PHASE_1_NEW — WORKER ONLY: Thiết kế Menu hai cấp

## Phạm vi và đầu vào

Một nhiệm vụ = **toàn bộ Menu hai cấp của một module, một ngôn ngữ**. Prime đưa **nội dung** `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (có thể rỗng) và đường dẫn module, ngôn ngữ, READ/WRITE. Không dùng `note.yml`, không tự đọc file `module-info.json` hay `master.json`. Với SPECIAL_NOTE nhiều dòng, phải đọc và áp dụng nguyên văn như ngữ cảnh nội dung, không phải quyền truy cập bổ sung.

Handoff mẫu:

```text
MODULE_LOCATION=<ABSOLUTE_MODULE_LOCATION>
LANG=vi
SERVICE_NAME=<SERVICE_NAME.VALUE>
SERVICE_NAME_DESCRIBE=<SERVICE_NAME_DESCRIBE.VALUE>
SPECIAL_NOTE=<nguyên văn SPECIAL_NOTE.VALUE>
READ=<MODULE_LOCATION>/content/knowledge/vi/menu.yml
WRITE=<MODULE_LOCATION>/content/knowledge/vi/menu.yml
INSTRUCTIONS=<java-learning>/learning-platform-data/module-generate-agent/worker/STEP_3_WORKER_PHASE_1_NEW.md
```

Chỉ được đọc file hướng dẫn này, nội dung Prime giao và file READ; **chỉ ghi `menu.yml`**. Không sửa file khác, sinh `note.yml`, viết Markdown, làm Phase 2, dùng Sheets/Gradle/DB, cập nhật checkpoint, spawn, commit hoặc push.

## Nhiệm vụ

1. "Thiết kế cho tôi menu 2 cấp của chủ đề (SERVICE_NAME) được giao
   Dùng để viết markdown document , nên phải thật đầy đủ và thật chi tiết
   Menu cấp 1 viết ngắn gọn thâu do là để tiêu đề"
2. Check thêm SPECIAL NOTE nếu cần thiết
3. Sau khi thiết kế xong trả về kết quả theo WRITE location theo prime đã đưa , cấu trúc theo đúng schema output phía dưới
   Nếu đã có nội dung hợp lệ, chỉ xác minh và báo `UNCHANGED_VERIFIED`, không overwrite; dữ liệu sai/xung đột → BLOCKER.

## Schema output

```yaml
menu:
  - level1: "Level 1"
    level2:
      - "Level 2"
      - "Level 2"
  - level1: "Level 1"
    level2:
      - "Level 2"
```

Root chỉ có `menu`, mỗi item chỉ có `level1`, `level2`. Không đặt `title`, `slug`, `index`, `status` hoặc cấp 3 ở file này.

Trước khi ghi, xác minh file chưa bị thay đổi; sau khi ghi, readback nguyên văn YAML, kiểm tra cấu trúc, số lượng và độ bao phủ theo SERVICE_NAME_DESCRIBE/SPECIAL_NOTE, không sửa file ngoài WRITE. Báo Prime `STATUS=COMPLETED/UNCHANGED_VERIFIED/BLOCKER/FAILED`, `PHASE=1`, `MODULE_LOCATION`, `LANG`, `MENU_LEVEL_1_COUNT`, `MENU_LEVEL_2_COUNT`, `CONTENT_QA`, `YAML_QA`, `READBACK`, `PRESERVED`, `BLOCKERS`. Release ownership và về SLEEPING, không tự làm Phase 2.
