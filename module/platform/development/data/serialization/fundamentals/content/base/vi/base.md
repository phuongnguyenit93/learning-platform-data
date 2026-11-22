# Data Serialization Fundamentals

Serialization chuyển dữ liệu từ đối tượng hoặc cấu trúc trong chương trình thành biểu diễn có thể lưu trữ hoặc truyền đi; deserialization tái tạo dữ liệu từ biểu diễn đó. Nắm được hai chiều chuyển đổi giúp dữ liệu giữ đúng ý nghĩa khi đi qua tệp, API, thông điệp hay các hệ thống khác nhau.

Module này giới thiệu nền tảng độc lập với thư viện cụ thể: định dạng văn bản và nhị phân, ánh xạ kiểu dữ liệu, mã hóa ký tự, cấu trúc và schema, tương thích phiên bản, xử lý đầu vào không tin cậy và kiểm thử độ chính xác. Nội dung dành cho người đã biết kiểu dữ liệu và cấu trúc chương trình cơ bản, chưa cần kinh nghiệm với công cụ serialization chuyên dụng.

Lộ trình gồm bảy mốc, đi từ khái niệm đến lựa chọn định dạng, mô hình hóa payload, tiến hóa schema, kiểm soát rủi ro và kiểm thử round-trip. Hoàn thành module, bạn có thể đọc và đánh giá một hợp đồng dữ liệu, nhận ra các đánh đổi quan trọng và chuẩn bị sử dụng thư viện serialization trong thực tế.