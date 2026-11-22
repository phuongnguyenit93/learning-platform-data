# Java Core Logging

Logging là cách ứng dụng Java ghi lại những sự kiện quan trọng để hỗ trợ theo dõi hoạt động, chẩn đoán sự cố và điều tra hành vi bất thường. Module **Java Core Logging** giúp người học hiểu từ API logging có sẵn trong JDK đến hệ sinh thái SLF4J và backend phổ biến, đồng thời xây dựng thói quen ghi log có chủ đích thay vì lạm dụng `System.out.println`.

Lộ trình gồm tám mốc, bắt đầu từ vai trò của log và `java.util.logging`, tiếp đến là SLF4J, mức độ log, cấu hình và đầu ra. Những mốc sau tập trung vào ngữ cảnh yêu cầu qua MDC, dữ liệu có cấu trúc, ghi nhận exception an toàn, chi phí hiệu năng và kiểm thử. Các ví dụ ưu tiên ứng dụng Java thông thường; nguyên tắc có thể áp dụng cho nhiều môi trường chạy và framework.

Nội dung phù hợp với người đã nắm cú pháp Java, class, exception và kiến thức lập trình đa luồng cơ bản. Sau khi hoàn thành, bạn có thể chọn cấp độ log thích hợp, cấu hình nơi xuất log, liên kết sự kiện qua mã tương quan, tránh ghi dữ liệu nhạy cảm và kiểm chứng rằng bản ghi đủ hữu ích cho việc vận hành.