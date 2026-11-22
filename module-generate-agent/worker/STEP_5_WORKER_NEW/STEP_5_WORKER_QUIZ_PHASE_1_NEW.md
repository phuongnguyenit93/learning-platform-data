# STEP 5 NEW — QUIZ / PHASE 1 — WORKER ONLY

## Scope và handoff

Prime đã **gắn đúng module root làm working directory** cho Worker trước khi giao. Nếu scope không được xác minh → BLOCKER, không tự tìm module. Nhận nguyên nội dung `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`, `SPECIAL_NOTE` (kể cả note rỗng/nhiều dòng) và file Worker này. **Không đọc `module-info.json`/`master.json`/Google Sheets**, không tự tìm Knowledge hay loại khác. Metadata là ngữ cảnh, không phải quyền mở rộng WRITE.

Trong `<MODULE_ROOT>/content/temp/step5/`, toàn bộ file `raw/`, `format/`, `status/` đã do Prime tạo. Quyền sở hữu chỉ thuộc **quiz Phase 1**. Không sửa file khác, không commit/push/DB/import, không chạy STEP khác, không spawn Worker. Tôn trọng SPECIAL_NOTE nguyên văn, không bịa API, chạy code hay kết quả giả.

## Nhiệm vụ

Tạo toàn bộ bộ câu hỏi trắc nghiệm cho SERVICE_NAME và SERVICE_NAME_DESCRIBE, có xét SPECIAL_NOTE. **READ:** metadata do Prime truyền, trạng thái `status/quiz.yml`. **WRITE:** chỉ `raw/quiz.md` và status.
- Văn bản Markdown thô: mỗi câu có câu hỏi, đúng bốn lựa chọn `A.`/`B.`/`C.`/`D.` và một dòng `Đáp án đúng: A|B|C|D`; một dòng trống ngăn hai câu. Không YAML, group hay explanation.
- Mọi câu chỉ có một đáp án đúng, bốn lựa chọn cùng mức hợp lý/cấu trúc/độ cụ thể. Distractor là nhầm lẫn kỹ thuật có thực, không phi lý. Đáp án đúng không nổi bật nhờ độ dài, câu chữ, điều kiện, ví dụ, từ khóa lặp hoặc dấu hiệu format.
- Tỷ lệ lựa chọn dài nhất/ngắn nhất > 1,5 là **cờ đỏ** cần review; không nhồi chữ để qua ngưỡng. Blind review từng câu (che đáp án). Với >=4 câu, A/B/C/D đúng lệch nhau không quá 1, không có ba chữ đúng liên tiếp hay chu kỳ đoán được. Với >=10 câu, đáp án đúng dài nhất ở >40% câu thì phải rà và sửa.
- Trước WRITE, QA 100% câu và báo `ANSWER_LEAK_QA`, thống kê A/B/C/D, flagged indices. Nếu không thể tạo Quiz đạt yêu cầu: `BLOCKER: STEP5_QUIZ_ANSWER_LEAK`; không ghi bài sơ sài.
- Sau readback nội dung và QA PASS, cập nhật `status/quiz.yml` từ `Phase 0` thành `Phase 1`.
## Gate, phục hồi, status

- Preflight `status/quiz.yml` phải đúng `status: Phase 0`; xác minh file nguồn của Phase trước và không có writer khác. Nếu đã ở `Phase 1`, kiểm lại output và báo `UNCHANGED_ALREADY_COMPLETE` nếu hoàn toàn hợp lệ; không rewrite/reset. Nếu trạng thái khác → BLOCKER.
- Nếu output đã được viết nhưng status vẫn ở Phase 0, **readback/đối chiếu trước** và tái sử dụng nếu đúng; không overwrite nội dung do tác giả/Worker khác. Nếu không chắc provenance → BLOCKER cho Prime.
- Trước WRITE snapshot input và status; khi ghi chỉ thay file thuộc quyền. Kiểm lại nội dung bằng readback UTF-8, parse YAML (nếu là YAML), tính đầy đủ và field-level semantic diff; không xóa hay đổi thông tin ngoài Phase. Nếu lỗi, giữ status cũ và báo BLOCKER.
- **Chỉ sau khi output hoàn chỉnh và QA/readback PASS** Worker sửa **duy nhất field `status`** trong `status/quiz.yml` từ `Phase 0` thành `Phase 1` rồi readback status. Prime chỉ QA và điều phối; Worker chính là người cập nhật status.
- Báo Prime `TYPE=QUIZ`, `PHASE=1`, `ITEM_COUNT`, `GROUP_COUNT` (nếu có), `OUTPUT_READBACK`, `STATUS_READBACK`, `SEMANTIC_DIFF_QA`, `SPECIAL_NOTE`, `BLOCKERS`; release ownership, về SLEEPING/Idle. Không tự sang Phase kế.
