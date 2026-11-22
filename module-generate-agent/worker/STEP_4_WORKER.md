# STEP 4 — WORKER ONLY: Viết Markdown vào file rowXX.md

## Vai trò và phạm vi

**Mỗi lượt giao đúng một row; Worker chỉ soạn Markdown file local.** Không gọi Google Sheets, không chia C:N, không dùng Google Sheets plugin, không chạy Gradle task, không QA/chấm/refactor bài. STEP 5 mới QA nội dung.

Prime gửi **đúng ba dòng**:

```text
/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/row21-info.yml
/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/row21.md
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_4_WORKER.md
```

Worker đọc toàn văn file này rồi đọc **duy nhất `rowXX-info.yml` được giao** làm nguồn nội dung. Không đọc trực tiếp Sheet, STEP Prime, GENERAL, rules, TXT, README cũ, file info khác hoặc dựa vào lịch sử hội thoại để đổi đề bài. Không tự xác định row khác hoặc spawn worker.

## W1 — Đọc đúng info

File `rowXX-info.yml` đã do task thuần code PREPARE tạo, gồm:

```yaml
row: 21
topic: "Tên module từ B1"
specialNote: "Nội dung Special Note (nếu có)"
menuLevel1: "Tên chương nguyên văn"
menuLevel2: "Tên bài học nguyên văn"
status: ''
```

- `topic`: B1; `specialNote`: ô dưới nhãn Special Note trong Module Project; `menuLevel1`: chủ đề cha; `menuLevel2`: **đề bài trực tiếp** cho Markdown.
- STEP 4 **không tạo Summary**. Nếu thấy field `summary` legacy trong file info cũ, **giữ nguyên, không sử dụng và không sửa**. STEP 5 dùng `GroupX/summary.yml` với `lessons[].markdownSummary`.
- Nếu Special Note trống thì vẫn bình thường. Không tự chuyển tên bài thành một câu hỏi trung gian.
- Nếu file info thiếu/trống hoặc sai định dạng, báo `BLOCKER: INVALID_INFO_FILE`. **Không tự vào Google Sheets để sửa dữ liệu.**
- Nếu `status` không rỗng, không ghi đè file đã thuộc lượt trước; báo Prime xử lý ownership.
- Hàng/folder chỉ có một Worker sở hữu mỗi lượt; không sửa file khác.

## W2 — Soạn README Markdown đầy đủ

Soạn một tài liệu Markdown tự chứa, giải thích chi tiết đúng `menuLevel2` trong ngữ cảnh `topic`, `menuLevel1` và `specialNote`. Giữ yêu cầu chất lượng đầu ra về hình thức như STEP 4 cũ: trình bày phù hợp với chủ đề bằng heading, đoạn giải thích, ví dụ, code block, bảng, sơ đồ khi hữu ích; không giới hạn chiều sâu hoặc đặt mục tiêu số chữ; không viết tóm tắt để vừa một ô Sheet.

**Không chạy lượt Content QA, không đánh giá code/stdout/Markdown bằng checklist, không so sánh/refactor với bài khác.** Việc rà soát chính xác, đầy đủ, trùng lặp và nhất quán thuộc **STEP 5**.

## W3 — Lưu file Markdown; đánh dấu status

1. Viết **toàn bộ chuỗi Markdown nguyên vẹn** vào đúng file `rowXX.md` do Prime chỉ định, UTF-8, không chia fragment 30.000 ký tự, không thêm YAML QA. Chỉ sửa file `rowXX.md` và trường `status` trong `rowXX-info.yml` tương ứng.
2. Chỉ khi file Markdown đã lưu thành công, đọc lại file hoặc kiểm tra nguyên văn để bảo đảm không lỗi ghi file, sau đó đổi **duy nhất** `status: ''` thành `status: WRITTEN` trong file info. Giữ nguyên `row`, `topic`, `specialNote`, `menuLevel1` và `menuLevel2`.
3. Nếu ghi/readback local lỗi hoặc file có trạng thái khác ban đầu, báo `BLOCKER` và **không** đánh dấu `WRITTEN`. Đây là readback lưu trữ, **không phải QA nội dung**.
4. Không tự ghi `UPLOADED` hoặc `SKIPPED_EXISTING`: đây là status legacy, không còn được cấp ở STEP 4. Không sửa `manifest.yml` (Prime chạy `refreshStep4KnowledgeStatus` để đồng bộ từ info YAML).
5. Không tự chia Markdown thành ô Sheet. Prime chạy `verifyStep4Knowledge` local để kiểm tra file vừa giới hạn kỹ thuật của STEP 5 (tối đa 12 × 30.000 UTF-16 units). Nếu quá dài, báo blocker để xử lý, không truncate bài.

## W4 — Báo cáo và SLEEPING

Trả về `STATUS=COMPLETED/BLOCKER/FAILED`, `ROW`, `INFO_PATH`, `MARKDOWN_PATH`, `TOTAL_CHARS`, `FILE_WRITE`, `READBACK` (kiểm tra kỹ thuật) và `INFO_STATUS=WRITTEN` khi đã hoàn tất. Nếu lỗi, nêu loại lỗi file thực tế.

`COMPLETED` chỉ có nghĩa **đã viết đủ file và cập nhật status**, không có nghĩa nội dung được QA hoặc đã lên Google Sheets. Sau báo cáo, giải phóng ownership và về SLEEPING để Prime có thể giao row tiếp theo.

**Prime STEP 4 chỉ chạy REFRESH/VERIFY local rồi checkpoint STEP 4, không ghi C:N. Prime STEP 5 mới chạy Gradle PUBLISH sau Knowledge QA/refactor.**
