# Code Quality Formatting Spotless

Spotless là công cụ tự động kiểm tra và chuẩn hóa định dạng mã nguồn, được tích hợp phổ biến qua plugin Gradle và Maven. Module này giúp bạn thiết lập quy tắc định dạng thống nhất cho dự án Java, xác định những tệp cần xử lý và phân biệt bước kiểm tra với bước tự động sửa. Trọng tâm là tính nhất quán của mã nguồn, không thay thế các công cụ phân tích lỗi chương trình.

Bạn nên biết Java cơ bản và cách chạy build bằng Gradle hoặc Maven. Lộ trình bắt đầu từ cài đặt Spotless, chọn target và các formatter step như google-java-format, import ordering, khoảng trắng và license header. Sau đó bạn thực hành các lệnh check/apply, quản lý cấu hình trong dự án nhiều module, cân nhắc baseline cho mã cũ và tích hợp kiểm tra vào CI.

Kết thúc module, bạn có thể cấu hình Spotless cho phạm vi phù hợp, tự động kiểm tra và sửa vi phạm định dạng, đọc diff khi có thay đổi ngoài dự kiến, đồng thời duy trì cùng một chuẩn giữa môi trường local và pipeline.