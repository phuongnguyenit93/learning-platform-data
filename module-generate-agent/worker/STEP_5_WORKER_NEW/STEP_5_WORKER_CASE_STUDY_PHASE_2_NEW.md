# STEP 5 NEW — CASE_STUDY / PHASE 2 — WORKER ONLY

## Scope và handoff

Prime đã **gắn đúng module root làm working directory** cho Worker trước khi giao. Nếu scope không được xác minh → BLOCKER, không tự tìm module. Nhận nguyên nội dung `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (kể cả note rỗng/nhiều dòng) và file Worker này. **Không đọc `module-info.json`/`master.json`/Google Sheets**, không tự tìm Knowledge hay loại khác. Metadata là ngữ cảnh, không phải quyền mở rộng WRITE.

Trong `<MODULE_ROOT>/content/temp/step5/`, toàn bộ file `raw/`, `format/`, `status/` đã do Prime tạo. Quyền sở hữu chỉ thuộc **casestudy Phase 2**. Không sửa file khác, không commit/push/DB/import, không chạy STEP khác, không spawn Worker. Tôn trọng SPECIAL_NOTE nguyên văn, không bịa API, chạy code hay kết quả giả.

## Nhiệm vụ

Đọc `raw/casestudy.md` và chuyển **toàn bộ** tình huống thành `format/casestudy.yml` có group. **READ:** raw casestudy, status casestudy, metadata Prime truyền. **WRITE:** format casestudy và status casestudy.
- YAML root `caseStudy:` là list group; `groupID` 1..N liên tiếp, `groupName` không rỗng, `cases` không rỗng; mỗi tình huống có một item, bảo toàn nghĩa/câu chữ và thứ tự raw.
- Item shape: `index: 0` (0-based, tăng 1 theo thứ tự **trong từng group**), `situation: "<tình huống gốc>"`, `resolve: ""`, `knowledge: ""`, `answer: ""`, `readmeRelated: {anchorList: []}`. Không điền resolve/knowledge/answer trong Phase 2.
- **Dùng `answer`, không dùng `code`/`codes`**. Không thêm `apiRelated`, anchor/file, ID Knowledge.
- Parse YAML, QA từng item/raw, readback; sau PASS đổi `status/casestudy.yml` từ `Phase 1` sang `Phase 2`.
## Gate, phục hồi, status

- Preflight `status/casestudy.yml` phải đúng `status: Phase 1`; xác minh file nguồn của Phase trước và không có writer khác. Nếu đã ở `Phase 2`, kiểm lại output và báo `UNCHANGED_ALREADY_COMPLETE` nếu hoàn toàn hợp lệ; không rewrite/reset. Nếu trạng thái khác → BLOCKER.
- Nếu output đã được viết nhưng status vẫn ở Phase 1, **readback/đối chiếu trước** và tái sử dụng nếu đúng; không overwrite nội dung do tác giả/Worker khác. Nếu không chắc provenance → BLOCKER cho Prime.
- Trước WRITE snapshot input và status; khi ghi chỉ thay file thuộc quyền. Kiểm lại nội dung bằng readback UTF-8, parse YAML (nếu là YAML), tính đầy đủ và field-level semantic diff; không xóa hay đổi thông tin ngoài Phase. Nếu lỗi, giữ status cũ và báo BLOCKER.
- **Chỉ sau khi output hoàn chỉnh và QA/readback PASS** Worker sửa **duy nhất field `status`** trong `status/casestudy.yml` từ `Phase 1` thành `Phase 2` rồi readback status. Prime chỉ QA và điều phối; Worker chính là người cập nhật status.
- Báo Prime `TYPE=CASE_STUDY`, `PHASE=2`, `ITEM_COUNT`, `GROUP_COUNT` (nếu có), `OUTPUT_READBACK`, `STATUS_READBACK`, `SEMANTIC_DIFF_QA`, `SPECIAL_NOTE`, `BLOCKERS`; release ownership, về SLEEPING/Idle. Không tự sang Phase kế.
