# STEP_3_WORKER_PHASE_2_NEW — WORKER ONLY: Đặt slug tiếng Anh cho Menu cấp 1

## Điều kiện và quyền

Chỉ nhận nhiệm vụ **sau khi Prime xác nhận Phase 1 QA/readback PASS**. Prime cung cấp MODULE_LOCATION, LANG, nội dung SERVICE_NAME, SERVICE_NAME_DESCRIBE, SPECIAL_NOTE và READ/WRITE. **Không đọc `note.yml` hay file metadata**. Một lượt giao chỉ được ghi `menu-level-1-slug.yml`, không sửa `menu.yml`, Markdown, `note.yml` cũ, module khác hoặc ngôn ngữ khác.

```text
MODULE_LOCATION=<ABSOLUTE_MODULE_LOCATION>
LANG=vi
SERVICE_NAME=<SERVICE_NAME.VALUE>
SERVICE_NAME_DESCRIBE=<SERVICE_NAME_DESCRIBE.VALUE>
SPECIAL_NOTE=<nguyên văn SPECIAL_NOTE.VALUE>
READ=<MODULE_LOCATION>/content/knowledge/vi/menu.yml,<MODULE_LOCATION>/content/knowledge/vi/menu-level-1-slug.yml
WRITE=<MODULE_LOCATION>/content/knowledge/vi/menu-level-1-slug.yml
INSTRUCTIONS=<java-learning>/learning-platform-data/module-generate-agent/worker/STEP_3_WORKER_PHASE_2_NEW.md
```

Không chạy Python/Sheets/DB/Gradle, cập nhật checkpoint, spawn, commit, push hoặc chuyển STEP.

## Nhiệm vụ

1. Đọc toàn bộ `menu.yml` gồm level1 và level2, đối chiếu mô tả module và SPECIAL_NOTE để hiểu ngữ nghĩa từng chương.
2. Tạo **đúng một entry cho mỗi level1**; `title` trùng nguyên văn, giữ thứ tự, `index` là số nguyên bắt đầu 0 và liên tiếp.
3. `slug` phải **diễn đạt đúng ngữ nghĩa chương bằng tiếng Anh và tương đối ngắn**, không đơn thuần bỏ dấu tiếng Việt hoặc ghép từ Việt không dấu với từ tiếng Anh. Ưu tiên **khoảng 40 ký tự trở xuống** nếu vẫn rõ nghĩa; không thêm tiền tố tên module dài dòng hay lặp ngữ cảnh đã có ở đường dẫn module. Dùng lowercase kebab-case, regex `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`, giới hạn kỹ thuật tối đa 80 ký tự; không trùng, không chọn tên chung chung hay Windows reserved names `con`/`prn`/`aux`/`nul`/`com1..9`/`lpt1..9`. Nếu thuật ngữ chuyên môn cần dài hơn mức ưu tiên để không sai nghĩa, cho phép nhưng vẫn phải ngắn gọn nhất có thể.
4. Nếu output đã có đầy đủ đúng title/slug/index thì báo `UNCHANGED_VERIFIED`; nội dung khác hoặc xung đột → BLOCKER, không overwrite.

```yaml
menu:
  - title: "Tư duy OOP"
    slug: oop-basic
    index: 0
  - title: "Thực hành OOP"
    slug: oop-practice
    index: 1
```

Root chỉ có `menu`, mỗi phần tử đúng ba key `title`/`slug`/`index`. Không ghi level2, filename hoặc status.

Trước khi ghi, kiểm tra menu nguồn không đổi và output còn skeleton `menu: []`. Sau write, readback cả hai file, kiểm tra title/count/index/slug, bảo toàn menu cấp 2. Báo Prime `STATUS=COMPLETED/UNCHANGED_VERIFIED/BLOCKER/FAILED`, `PHASE=2`, `MENU_COUNT`, `SLUG_COUNT`, `INDEX_CHECK`, `UNIQUE_SLUGS`, `READBACK`, `PRESERVED`, `BLOCKERS`. Release ownership, SLEEPING; Prime sẽ chạy `generate_menu_detail.py`.
