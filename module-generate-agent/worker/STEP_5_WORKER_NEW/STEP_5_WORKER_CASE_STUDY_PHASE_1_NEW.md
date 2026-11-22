# STEP 5 NEW — CASE_STUDY / PHASE 1 — WORKER ONLY

## Scope và handoff

Prime đã **gắn đúng module root làm working directory** cho Worker trước khi giao. Nếu scope không được xác minh → BLOCKER, không tự tìm module. Nhận nguyên nội dung `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (kể cả note rỗng/nhiều dòng) và file Worker này. **Không đọc `module-info.json`/`master.json`/Google Sheets**, không tự tìm Knowledge hay loại khác. Metadata là ngữ cảnh, không phải quyền mở rộng WRITE.

Trong `<MODULE_ROOT>/content/temp/step5/`, toàn bộ file `raw/`, `format/`, `status/` đã do Prime tạo. Quyền sở hữu chỉ thuộc **casestudy Phase 1**. Không sửa file khác, không commit/push/DB/import, không chạy STEP khác, không spawn Worker. Tôn trọng SPECIAL_NOTE nguyên văn, không bịa API, chạy code hay kết quả giả.

## Nhiệm vụ

Tạo các tình huống thực tế phù hợp metadata Prime truyền. **READ:** metadata, `status/casestudy.yml`. **WRITE:** chỉ `raw/casestudy.md` và status.
- **Một tình huống/vấn đề trên một dòng**, chưa phân group/YAML, chưa viết `resolve`, `knowledge`, `answer` hoặc code.
- Chọn tình huống đa dạng, thực tế, bối cảnh đủ rõ để người học phân tích; không bắt buộc mỗi tình huống sẽ có mã Java.
- Đối chiếu nội dung với SPECIAL_NOTE, QA không rỗng/trùng, exact readback; sau PASS đổi duy nhất `status/casestudy.yml` từ `Phase 0` sang `Phase 1`.
## Gate, phục hồi, status

- Preflight `status/casestudy.yml` phải đúng `status: Phase 0`; xác minh file nguồn của Phase trước và không có writer khác. Nếu đã ở `Phase 1`, kiểm lại output và báo `UNCHANGED_ALREADY_COMPLETE` nếu hoàn toàn hợp lệ; không rewrite/reset. Nếu trạng thái khác → BLOCKER.
- Nếu output đã được viết nhưng status vẫn ở Phase 0, **readback/đối chiếu trước** và tái sử dụng nếu đúng; không overwrite nội dung do tác giả/Worker khác. Nếu không chắc provenance → BLOCKER cho Prime.
- Trước WRITE snapshot input và status; khi ghi chỉ thay file thuộc quyền. Kiểm lại nội dung bằng readback UTF-8, parse YAML (nếu là YAML), tính đầy đủ và field-level semantic diff; không xóa hay đổi thông tin ngoài Phase. Nếu lỗi, giữ status cũ và báo BLOCKER.
- **Chỉ sau khi output hoàn chỉnh và QA/readback PASS** Worker sửa **duy nhất field `status`** trong `status/casestudy.yml` từ `Phase 0` thành `Phase 1` rồi readback status. Prime chỉ QA và điều phối; Worker chính là người cập nhật status.
- Báo Prime `TYPE=CASE_STUDY`, `PHASE=1`, `ITEM_COUNT`, `GROUP_COUNT` (nếu có), `OUTPUT_READBACK`, `STATUS_READBACK`, `SEMANTIC_DIFF_QA`, `SPECIAL_NOTE`, `BLOCKERS`; release ownership, về SLEEPING/Idle. Không tự sang Phase kế.
