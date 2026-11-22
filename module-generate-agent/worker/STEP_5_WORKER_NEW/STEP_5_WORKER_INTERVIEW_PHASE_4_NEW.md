# STEP 5 NEW — INTERVIEW / PHASE 4 — WORKER ONLY

## Scope và handoff

Prime đã **gắn đúng module root làm working directory** cho Worker trước khi giao. Nếu scope không được xác minh → BLOCKER, không tự tìm module. Nhận nguyên nội dung `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (kể cả note rỗng/nhiều dòng) và file Worker này. **Không đọc `module-info.json`/`master.json`/Google Sheets**, không tự tìm Knowledge hay loại khác. Metadata là ngữ cảnh, không phải quyền mở rộng WRITE.

Trong `<MODULE_ROOT>/content/temp/step5/`, toàn bộ file `raw/`, `format/`, `status/` đã do Prime tạo. Quyền sở hữu chỉ thuộc **interview Phase 4**. Không sửa file khác, không commit/push/DB/import, không chạy STEP khác, không spawn Worker. Tôn trọng SPECIAL_NOTE nguyên văn, không bịa API, chạy code hay kết quả giả.

## Nhiệm vụ

Đọc `format/interview.yml` đã PASS Phase 3; **một Worker phụ trách TẤT CẢ group** và điền `questions[].answer` trực tiếp trong **cùng `format/interview.yml`**. **READ:** format, raw, status interview, metadata. **WRITE:** chỉ format interview và status interview.
- `answer` là chuỗi Markdown có đủ chiều sâu để trả lời câu hỏi, dùng `knowledge` làm nền; nêu cơ chế, điều kiện, so sánh/trade-off khi hữu ích. Không bịa output compile/run.
- Không tạo file answer riêng, không chia nhỏ group và không đổi `question`, `knowledge`, group, `readmeRelated.anchorList` hay thứ tự.
- Semantic diff chỉ answer; kiểm đủ mọi câu/group và exact readback YAML. Sau PASS đổi `status/interview.yml` từ `Phase 3` sang `Phase 4`.
## Gate, phục hồi, status

- Preflight `status/interview.yml` phải đúng `status: Phase 3`; xác minh file nguồn của Phase trước và không có writer khác. Nếu đã ở `Phase 4`, kiểm lại output và báo `UNCHANGED_ALREADY_COMPLETE` nếu hoàn toàn hợp lệ; không rewrite/reset. Nếu trạng thái khác → BLOCKER.
- Nếu output đã được viết nhưng status vẫn ở Phase 3, **readback/đối chiếu trước** và tái sử dụng nếu đúng; không overwrite nội dung do tác giả/Worker khác. Nếu không chắc provenance → BLOCKER cho Prime.
- Trước WRITE snapshot input và status; khi ghi chỉ thay file thuộc quyền. Kiểm lại nội dung bằng readback UTF-8, parse YAML (nếu là YAML), tính đầy đủ và field-level semantic diff; không xóa hay đổi thông tin ngoài Phase. Nếu lỗi, giữ status cũ và báo BLOCKER.
- **Chỉ sau khi output hoàn chỉnh và QA/readback PASS** Worker sửa **duy nhất field `status`** trong `status/interview.yml` từ `Phase 3` thành `Phase 4` rồi readback status. Prime chỉ QA và điều phối; Worker chính là người cập nhật status.
- Báo Prime `TYPE=INTERVIEW`, `PHASE=4`, `ITEM_COUNT`, `GROUP_COUNT` (nếu có), `OUTPUT_READBACK`, `STATUS_READBACK`, `SEMANTIC_DIFF_QA`, `SPECIAL_NOTE`, `BLOCKERS`; release ownership, về SLEEPING/Idle. Không tự sang Phase kế.
