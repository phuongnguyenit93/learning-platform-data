# STEP 5 NEW — QUIZ / PHASE 2 — WORKER ONLY

## Scope và handoff

Prime đã **gắn đúng module root làm working directory** cho Worker trước khi giao. Nếu scope không được xác minh → BLOCKER, không tự tìm module. Nhận nguyên nội dung `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (kể cả note rỗng/nhiều dòng) và file Worker này. **Không đọc `module-info.json`/`master.json`/Google Sheets**, không tự tìm Knowledge hay loại khác. Metadata là ngữ cảnh, không phải quyền mở rộng WRITE.

Trong `<MODULE_ROOT>/content/temp/step5/`, toàn bộ file `raw/`, `format/`, `status/` đã do Prime tạo. Quyền sở hữu chỉ thuộc **quiz Phase 2**. Không sửa file khác, không commit/push/DB/import, không chạy STEP khác, không spawn Worker. Tôn trọng SPECIAL_NOTE nguyên văn, không bịa API, chạy code hay kết quả giả.

## Nhiệm vụ

Đọc `raw/quiz.md` đã PASS Phase 1, chuyển sang `format/quiz.yml` có đủ group. **READ:** raw quiz, status quiz; metadata Prime truyền. **WRITE:** format quiz và status quiz.
- Giữ **nguyên văn toàn bộ** câu hỏi, bốn lựa chọn, một đáp án đúng và không bỏ/trùng câu. Chỉ phân nhóm có nghĩa, `groupID` 1..N liên tiếp, `groupName` không rỗng; không viết thêm câu hỏi.
- Mỗi question có `index` là số nguyên **0-based trong từng group** (0,1,..., reset về 0 ở group mới), `question`, `readmeRelated: {anchorList: []}`, `answers` đúng bốn object `{id, answer, explanation: ""}` với ID A/B/C/D, và `correctAnswerId` khớp Phase 1. Không có `apiRelated`/anchor/file, không dùng ID Knowledge.
- Không bổ sung bất cứ `explanation` nào tại Phase 2. Phải rà gate chống lộ đáp án của raw; phát hiện vi phạm → BLOCKER, không tự đổi câu hỏi/đáp án tại Phase 2.
- Parse YAML, QA count, answer IDs, group, semantic equivalence, readback; sau PASS đổi `status/quiz.yml` từ `Phase 1` sang `Phase 2`.
## Gate, phục hồi, status

- Preflight `status/quiz.yml` phải đúng `status: Phase 1`; xác minh file nguồn của Phase trước và không có writer khác. Nếu đã ở `Phase 2`, kiểm lại output và báo `UNCHANGED_ALREADY_COMPLETE` nếu hoàn toàn hợp lệ; không rewrite/reset. Nếu trạng thái khác → BLOCKER.
- Nếu output đã được viết nhưng status vẫn ở Phase 1, **readback/đối chiếu trước** và tái sử dụng nếu đúng; không overwrite nội dung do tác giả/Worker khác. Nếu không chắc provenance → BLOCKER cho Prime.
- Trước WRITE snapshot input và status; khi ghi chỉ thay file thuộc quyền. Kiểm lại nội dung bằng readback UTF-8, parse YAML (nếu là YAML), tính đầy đủ và field-level semantic diff; không xóa hay đổi thông tin ngoài Phase. Nếu lỗi, giữ status cũ và báo BLOCKER.
- **Chỉ sau khi output hoàn chỉnh và QA/readback PASS** Worker sửa **duy nhất field `status`** trong `status/quiz.yml` từ `Phase 1` thành `Phase 2` rồi readback status. Prime chỉ QA và điều phối; Worker chính là người cập nhật status.
- Báo Prime `TYPE=QUIZ`, `PHASE=2`, `ITEM_COUNT`, `GROUP_COUNT` (nếu có), `OUTPUT_READBACK`, `STATUS_READBACK`, `SEMANTIC_DIFF_QA`, `SPECIAL_NOTE`, `BLOCKERS`; release ownership, về SLEEPING/Idle. Không tự sang Phase kế.
