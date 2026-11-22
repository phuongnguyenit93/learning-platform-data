# STEP 5 NEW — INTERVIEW / PHASE 3 — WORKER ONLY

## Scope và handoff

Prime đã **gắn đúng module root làm working directory** cho Worker trước khi giao. Nếu scope không được xác minh → BLOCKER, không tự tìm module. Nhận nguyên nội dung `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (kể cả note rỗng/nhiều dòng) và file Worker này. **Không đọc `module-info.json`/`master.json`/Google Sheets**, không tự tìm Knowledge hay loại khác. Metadata là ngữ cảnh, không phải quyền mở rộng WRITE.

Trong `<MODULE_ROOT>/content/temp/step5/`, toàn bộ file `raw/`, `format/`, `status/` đã do Prime tạo. Quyền sở hữu chỉ thuộc **interview Phase 3**. Không sửa file khác, không commit/push/DB/import, không chạy STEP khác, không spawn Worker. Tôn trọng SPECIAL_NOTE nguyên văn, không bịa API, chạy code hay kết quả giả.

## Nhiệm vụ

Đọc `format/interview.yml` Phase 2, điền **duy nhất** `questions[].knowledge` cho mọi câu ở tất cả group. **READ:** format, raw, status interview, metadata. **WRITE:** chỉ format interview và status interview.
- Knowledge nêu nguyên lý/kiến thức cần vận dụng để người học tự trả lời; không phải câu trả lời hoàn chỉnh. Không điền `answer` (giữ chuỗi rỗng ở Phase 3).
- Semantic diff phải giữ nguyên `question`, group, số lượng/thứ tự, `readmeRelated.anchorList: []` và các field ngoài knowledge. Không suy/điền Knowledge ID.
- QA mọi knowledge nonblank/đủ căn cứ, parse/readback; sau PASS đổi `status/interview.yml` từ `Phase 2` sang `Phase 3`.
## Gate, phục hồi, status

- Preflight `status/interview.yml` phải đúng `status: Phase 2`; xác minh file nguồn của Phase trước và không có writer khác. Nếu đã ở `Phase 3`, kiểm lại output và báo `UNCHANGED_ALREADY_COMPLETE` nếu hoàn toàn hợp lệ; không rewrite/reset. Nếu trạng thái khác → BLOCKER.
- Nếu output đã được viết nhưng status vẫn ở Phase 2, **readback/đối chiếu trước** và tái sử dụng nếu đúng; không overwrite nội dung do tác giả/Worker khác. Nếu không chắc provenance → BLOCKER cho Prime.
- Trước WRITE snapshot input và status; khi ghi chỉ thay file thuộc quyền. Kiểm lại nội dung bằng readback UTF-8, parse YAML (nếu là YAML), tính đầy đủ và field-level semantic diff; không xóa hay đổi thông tin ngoài Phase. Nếu lỗi, giữ status cũ và báo BLOCKER.
- **Chỉ sau khi output hoàn chỉnh và QA/readback PASS** Worker sửa **duy nhất field `status`** trong `status/interview.yml` từ `Phase 2` thành `Phase 3` rồi readback status. Prime chỉ QA và điều phối; Worker chính là người cập nhật status.
- Báo Prime `TYPE=INTERVIEW`, `PHASE=3`, `ITEM_COUNT`, `GROUP_COUNT` (nếu có), `OUTPUT_READBACK`, `STATUS_READBACK`, `SEMANTIC_DIFF_QA`, `SPECIAL_NOTE`, `BLOCKERS`; release ownership, về SLEEPING/Idle. Không tự sang Phase kế.
