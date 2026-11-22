# Spring Data Relational JDBC

Spring Data JDBC cung cấp mô hình truy cập cơ sở dữ liệu quan hệ theo các nguyên tắc của Spring Data và thiết kế theo aggregate trong Domain-Driven Design. Module này giúp bạn xây dựng lớp lưu trữ rõ ràng dựa trên đối tượng, repository và SQL, đồng thời hiểu các đặc điểm của Spring Data JDBC như vòng đời lưu toàn aggregate, ánh xạ tường minh và không phụ thuộc vào persistence context như JPA.

Lộ trình một cấp gồm tám mốc, bắt đầu với cách thiết lập Spring Data JDBC và xác định ranh giới aggregate. Tiếp theo, bạn học ánh xạ entity, xây dựng repository, tùy biến truy vấn SQL, quản lý transaction và optimistic locking, rồi mở rộng qua callbacks và auditing. Mốc cuối tập trung kiểm thử với cơ sở dữ liệu và quan sát các câu SQL mà ứng dụng phát sinh.

Nội dung phù hợp với người đã có kiến thức Java, Spring Boot và SQL cơ bản. Sau module, bạn có thể thiết kế aggregate và bảng nhất quán, viết các thao tác CRUD và truy vấn đúng nhu cầu, xử lý giao dịch an toàn, cũng như kiểm chứng hành vi lưu trữ trong ứng dụng thực tế.