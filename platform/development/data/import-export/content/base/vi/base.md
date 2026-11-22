# Data Import Export

Nhập và xuất dữ liệu là cầu nối giữa ứng dụng Java với file, API và các hệ thống bên ngoài. Module này giới thiệu cách tổ chức luồng import/export, lựa chọn định dạng dữ liệu và xử lý đúng encoding, schema cũng như lỗi chuyển đổi. Các ví dụ tập trung vào CSV, JSON và Excel, kết hợp Java I/O với thư viện phù hợp.

Bạn nên biết Java cơ bản, collections và thao tác file. Lộ trình bắt đầu từ định dạng, mã hóa và API đọc/ghi; tiếp theo là parse dữ liệu đầu vào, ánh xạ sang DTO và serialize dữ liệu đầu ra. Những mốc cuối đi vào xử lý batch/streaming, khôi phục khi có lỗi, kiểm soát dữ liệu không tin cậy và kiểm thử khả năng import/export qua lại.

Hoàn thành module, bạn có thể thiết kế quy trình nhập xuất có kiểm tra dữ liệu, chọn cách xử lý phù hợp với kích thước file và giải thích các vấn đề thực tế như sai encoding, lệch cột, dữ liệu lỗi, ghi dở, CSV formula injection hoặc tiêu thụ quá nhiều bộ nhớ.