# STEP_2_WORKER_NEW — WORKER ONLY: Roadmap, Reference và Base (VI)

## Quyền và nguồn

Một nhiệm vụ = **một module, ba file đầu ra, ngôn ngữ vi**. Prime đưa **nội dung** `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE` và `SPECIAL_NOTE` từ `module-info.json`, cùng `MODULE_LOCATION`. Không yêu cầu Prime gửi file metadata; không tự đọc `master.json`, Sheet, STEP cũ hoặc file Prime-only. `SPECIAL_NOTE` phải được hiểu toàn văn, không lược bỏ; coi nó là ngữ cảnh nội dung chứ không phải quyền truy cập bổ sung.

Chỉ được ghi ba file sau:

```text
<MODULE_LOCATION>/content/roadmap/vi/roadmap.yml
<MODULE_LOCATION>/content/reference/vi/references.yml
<MODULE_LOCATION>/content/base/vi/base.md
```

Không ghi `module-info.json`, `module_activate.json`, `master.json`, các thư mục language khác; không import DB/Gradle/Sheet, cập nhật checkpoint, spawn, commit hoặc push.

## W1. Preflight (trước khi soạn/ghi)

Kiểm tra đúng module và đọc toàn bộ ba file. Skeleton hợp lệ là `roadmap: []`, `references: []`, `base.md` trống/whitespace. Nếu **bất kỳ** file nào đã chứa nội dung người viết (một list không rỗng hoặc Markdown có nội dung), dừng cả nhiệm vụ: `BLOCKER: EXISTING_TARGET_CONTENT`; không ghi đè, không điền nốt hai file còn trống. Thiếu hoặc sai schema, đường dẫn không an toàn, ngôn ngữ không phải `vi` → BLOCKER.

## W2. Roadmap 1 cấp — ngắn để vẽ sơ đồ

> Thiết kế roadmap **1 cấp** theo chủ đề module. Roadmap dùng để **hiển thị sơ đồ**, không phải kế hoạch viết các Markdown document. Phải ngắn và ít mục: **dưới 10** (tối đa 9).

- Soạn **1–9** milestone theo tiến trình học tự nhiên, thường 5–8 nếu thích hợp; không ép số mục cố định. **Không tạo level2, child, chương con hoặc menu tài liệu.**
- Mỗi milestone có `id` là slug ASCII kebab-case duy nhất và ổn định; `title` tiếng Việt ngắn, làm nhãn sơ đồ; `purpose` thường một câu ngắn; `objectives` thường 2–4 mục tiêu cụ thể ngắn, mỗi item YAML một dòng.
- Dựa vào chủ đề học thể hiện trong SERVICE_NAME_DESCRIBE, phạm vi từ SERVICE_NAME và SPECIAL_NOTE. Tránh trùng lặp, chi tiết API vụn vặt, dàn bài nhiều trang; ưu tiên nền tảng → cơ chế chính → áp dụng/lựa chọn → lưu ý nếu phù hợp.
- `dependsOn`, `relatedKnowledge`, `relatedModules` **không bắt buộc**; chỉ thêm khi xác minh ID/route thực, không tự đặt sai. Schema:

```yaml
roadmap:
  - id: nen-tang
    title: "Nền tảng"
    purpose: "Hiểu lý do cần học chủ đề này."
    objectives:
      - "Nhận diện những thành phần quan trọng."
      - "Giải thích vai trò của từng thành phần."
```

*Ví dụ chỉ minh họa schema, không chép thành nội dung module thật.*

## W3. Reference tiếng Việt

Viết danh mục nguồn tham khảo sát chủ đề, ưu tiên official documentation, standards và tài liệu tác giả/nhà cung cấp. Mỗi mục phải có `title` và `url` **HTTPS tuyệt đối có thật**, `description` ngắn bằng tiếng Việt khi phù hợp. Kiểm chứng URL và nội dung đích nếu có thể truy cập, không tự bịa đường dẫn, tài liệu hoặc thông tin nguồn. Không thêm nguồn chỉ để đủ số, không đưa URL private/credential. Nếu không có nguồn tin cậy để bàn giao, báo BLOCKER.

```yaml
references:
  - title: "Tên tài liệu chính thức đã xác minh"
    url: "https://example.org/documentation"
    description: "Mô tả ngắn tài liệu giải thích nội dung gì."
```

URL ví dụ chỉ để minh họa cấu trúc, **không sử dụng làm nguồn thực**.

## W4. Base Markdown — thay B17 STEP 2 cũ

Viết **trực tiếp** `content/base/vi/base.md`. Bài giới thiệu tự đứng được, bằng tiếng Việt, có H1 tên chủ đề mà người học hiểu được và thông thường 1–3 đoạn trình bày mục đích, phạm vi, tư duy nền tảng, người học phù hợp và kết quả có thể đạt được. Có thể dùng danh sách ngắn nếu giúp dễ đọc. Giữ nhất quán với Roadmap và SPECIAL_NOTE; không chép toàn bộ roadmap thành bài dài, không sinh các bài Knowledge, không TODO/placeholder.

## W5. QA, ghi, readback và báo cáo

1. Chuẩn bị đủ **cả ba nội dung** trước khi ghi; kiểm tra Roadmap 1–9 mốc không trùng ID/title, Purpose/Objectives hợp lệ; Reference có URL thật liên quan; Base không rỗng và Markdown chuẩn.
2. Preflight lại cả ba đích ngay trước khi ghi: vẫn đúng skeleton, không bị thay đổi. Có thay đổi → `BLOCKER: SOURCE_CHANGED`; không tự ghi đè hoặc ghi dở. Chỉ ghi ba file đã giao.
3. Đọc lại toàn văn ba file, kiểm tra Unicode, số mốc, danh mục link, Base Markdown và phạm vi không bị sửa ngoài ba đường dẫn.
4. Báo Prime: `STATUS=COMPLETED/BLOCKER/FAILED`, `MODULE_LOCATION`, `LANG=vi`, `SERVICE_NAME`, `SPECIAL_NOTE=APPLIED/EMPTY/CONFLICT` (không cần chép lại nội dung), `ROADMAP_COUNT`, `ROADMAP_QA`, `REFERENCE_COUNT`, `REFERENCE_QA`, `BASE_QA`, `READBACK=PASS/FAIL`, `PRESERVED` và `BLOCKERS`. Sau đó release ownership/SLEEPING.

**Worker không đẩy dữ liệu vào DB**. Prime chỉ làm việc đó sau khi đủ ba output QA PASS.
