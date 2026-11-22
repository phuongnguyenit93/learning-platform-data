# Observability Telemetry Pipeline Tool Fluentd

Fluentd là công cụ mã nguồn mở để thu thập, xử lý và chuyển tiếp log đến nhiều hệ thống đích. Trong hệ thống có nhiều dịch vụ, một pipeline log ổn định giúp dữ liệu được chuẩn hóa, định tuyến và sẵn sàng cho việc tìm kiếm, phân tích sự cố. Module này dành cho lập trình viên, kỹ sư vận hành và người mới bắt đầu làm việc với pipeline telemetry.

Lộ trình gồm tám mốc ngắn, bắt đầu từ mô hình sự kiện của Fluentd và cấu trúc cấu hình. Bạn sẽ làm quen với nguồn log, parser, filter, tag và quy tắc routing để biết cách biến log thô thành bản ghi hữu ích rồi chuyển đến đúng đích. Tiếp theo là buffer và retry, những cơ chế quan trọng để ứng phó khi hệ thống nhận dữ liệu chậm hoặc gặp lỗi.

Sau khi học cách theo dõi chỉ số vận hành và xử lý lỗi thường gặp, bạn sẽ thử xây dựng một pipeline đơn giản từ tệp log đến đầu ra và kiểm tra dữ liệu thực tế. Trọng tâm là hiểu dòng chảy của dữ liệu, biết đọc cấu hình và tự chẩn đoán vấn đề trước khi áp dụng Fluentd vào hệ thống lớn.