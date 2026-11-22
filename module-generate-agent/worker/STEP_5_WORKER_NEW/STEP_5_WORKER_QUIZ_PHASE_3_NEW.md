# STEP 5 NEW — QUIZ / PHASE 3 — WORKER ONLY

## Scope và handoff

Prime đã **gắn đúng module root làm working directory** cho Worker trước khi giao. Nếu scope không được xác minh → BLOCKER, không tự tìm module. Nhận nguyên nội dung `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (kể cả note rỗng/nhiều dòng) và file Worker này. **Không đọc `module-info.json`/`master.json`/Google Sheets**, không tự tìm Knowledge hay loại khác. Metadata là ngữ cảnh, không phải quyền mở rộng WRITE.

Trong `<MODULE_ROOT>/content/temp/step5/`, toàn bộ file `raw/`, `format/`, `status/` đã do Prime tạo. Quyền sở hữu chỉ thuộc **quiz Phase 3**. Không sửa file khác, không commit/push/DB/import, không chạy STEP khác, không spawn Worker. Tôn trọng SPECIAL_NOTE nguyên văn, không bịa API, chạy code hay kết quả giả.

## Nhiệm vụ

Đọc `format/quiz.yml` Phase 2, bổ sung **chỉ** `answers[].explanation` cho mọi lựa chọn A/B/C/D ở mọi group. **READ:** format, raw, status quiz, metadata. **WRITE:** chỉ `format/quiz.yml` và `status/quiz.yml`.
- Mỗi explanation giải thích cụ thể vì sao lựa chọn đúng hoặc sai; dựa trên kỹ thuật thực, không giải thích chung chung hoặc bịa API/code chạy.
- **Bất biến:** `groupID`, `groupName`, thứ tự/số lượng question, `question`, `answers[].id`, `answers[].answer`, `correctAnswerId`, `readmeRelated.anchorList: []`. Không lén sửa đáp án.
- Nếu nhận ra câu chưa có một đáp án duy nhất/distractor lộ đáp án, báo `STEP5_QUIZ_ANSWER_LEAK` cho Prime chuyển lại đúng owner Phase 1; không tự thay question/answers ở Phase 3.
- Semantic diff chỉ 4 explanation/câu, parse/readback YAML; sau PASS đổi `status/quiz.yml` từ `Phase 2` sang `Phase 3`. **Quiz hoàn tất STEP 5 tại Phase 3**, không có Phase 4.
## Gate, phục hồi, status

- Preflight `status/quiz.yml` phải đúng `status: Phase 2`; xác minh file nguồn của Phase trước và không có writer khác. Nếu đã ở `Phase 3`, kiểm lại output và báo `UNCHANGED_ALREADY_COMPLETE` nếu hoàn toàn hợp lệ; không rewrite/reset. Nếu trạng thái khác → BLOCKER.
- Nếu output đã được viết nhưng status vẫn ở Phase 2, **readback/đối chiếu trước** và tái sử dụng nếu đúng; không overwrite nội dung do tác giả/Worker khác. Nếu không chắc provenance → BLOCKER cho Prime.
- Trước WRITE snapshot input và status; khi ghi chỉ thay file thuộc quyền. Kiểm lại nội dung bằng readback UTF-8, parse YAML (nếu là YAML), tính đầy đủ và field-level semantic diff; không xóa hay đổi thông tin ngoài Phase. Nếu lỗi, giữ status cũ và báo BLOCKER.
- **Chỉ sau khi output hoàn chỉnh và QA/readback PASS** Worker sửa **duy nhất field `status`** trong `status/quiz.yml` từ `Phase 2` thành `Phase 3` rồi readback status. Prime chỉ QA và điều phối; Worker chính là người cập nhật status.
- Báo Prime `TYPE=QUIZ`, `PHASE=3`, `ITEM_COUNT`, `GROUP_COUNT` (nếu có), `OUTPUT_READBACK`, `STATUS_READBACK`, `SEMANTIC_DIFF_QA`, `SPECIAL_NOTE`, `BLOCKERS`; release ownership, về SLEEPING/Idle. Không tự sang Phase kế.
