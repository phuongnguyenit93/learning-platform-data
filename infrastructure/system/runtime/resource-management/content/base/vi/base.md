# Runtime Resource Management

Runtime Resource Management là quá trình kiểm soát tài nguyên mà ứng dụng sử dụng trong lúc chạy: CPU, bộ nhớ, luồng, file, socket và các kết nối. Quản lý tốt những tài nguyên này giúp hệ thống phản hồi ổn định, tránh cạn kiệt tài nguyên và phục hồi an toàn khi gặp quá tải.

Nội dung dành cho người học đã có kiến thức cơ bản về tiến trình, luồng và ứng dụng Java, muốn hiểu mối liên hệ giữa mã nguồn, JVM và giới hạn của hệ điều hành hoặc container. Trọng tâm là vòng đời cấp phát–sử dụng–thu hồi, cách đặt giới hạn và cách quan sát hành vi thực tế; không yêu cầu xây dựng hệ thống điều phối tài nguyên riêng.

Lộ trình bắt đầu từ vòng đời tài nguyên, tiếp đến CPU, bộ nhớ, thread/executor, I/O, connection pool và quota. Cuối cùng, người học kết hợp các chỉ số và công cụ chẩn đoán để phát hiện nghẽn, rò rỉ, quá tải và xác minh hiệu quả của thay đổi.