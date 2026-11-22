# STEP 1 NEW — Kích hoạt module

> Trạng thái: Bộ khung. Chờ hướng dẫn tiếp theo; chưa triển khai hoặc chạy STEP này.

## Quy trình dự kiến

1. Nhận đường dẫn module được chỉ định trong `java-learning/learning-platform-data/module/`.
2. Đặt `module_activate.json` tại chính thư mục module đó, với `isModule: true`.
3. Dùng `script/module/step1/activate_module.py` để tìm các thư mục trong `java-learning/learning-platform-data/module/` có file `module_activate.json` chứa boolean `isModule = true`.
4. Tạo `module-info.json` trong mỗi thư mục phù hợp từ `java-learning/module-info-base.json` nếu chưa có; nếu đã có, chỉ bổ sung field còn thiếu và giữ nguyên giá trị hiện hữu.
5. AI điền `SERVICE_NAME` (chữ hoa, các từ cách nhau bằng `_`) và `SERVICE_NAME_DESCRIBE` (mô tả thật ngắn gọn mục đích học của module phù hợp).

Các chi tiết thực thi và điều kiện nghiệm thu sẽ được bổ sung theo hướng dẫn tiếp theo.
