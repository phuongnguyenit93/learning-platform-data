# Database Schema Migration Flyway

**Flyway** là công cụ quản lý phiên bản và triển khai thay đổi cơ sở dữ liệu thông qua các migration được lưu cùng mã nguồn. Thay vì sửa schema thủ công ở từng môi trường, nhóm phát triển viết những bước thay đổi rõ ràng, cho Flyway áp dụng theo thứ tự và kiểm tra lịch sử đã thực thi. Cách làm này giúp giảm sai lệch giữa môi trường phát triển, kiểm thử và production.

Lộ trình gồm **8 mốc**: cấu hình Flyway; versioned migrations; repeatable migrations; schema history; validate và repair; baseline cho cơ sở dữ liệu có sẵn; tích hợp Spring Boot; cuối cùng là triển khai an toàn qua CI/CD. Người học thực hành tạo migration SQL, chạy các lệnh info/migrate/validate, quan sát checksum và xử lý tình huống migration lỗi mà không tùy tiện chỉnh sửa lịch sử.

Học phần phù hợp với developer hoặc DevOps engineer đã biết SQL, khái niệm schema quan hệ và cấu hình ứng dụng Java cơ bản. Sau khi học, bạn có thể tổ chức migration theo phiên bản, triển khai trên nhiều môi trường, phát hiện thay đổi không nhất quán và lập quy trình kiểm tra, sao lưu cùng khôi phục trước các thay đổi dữ liệu quan trọng.