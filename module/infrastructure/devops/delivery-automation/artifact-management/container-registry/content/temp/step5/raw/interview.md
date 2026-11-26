Bạn giải thích vai trò của container registry trong quy trình phân phối phần mềm và phân biệt registry, repository, container image với các loại artifact OCI khác như thế nào?
Tag và digest khác nhau ra sao về khả năng thay đổi và truy xuất phiên bản, và khi nào bạn sẽ yêu cầu triển khai image bằng digest?
Bạn mô tả luồng push và pull một image từ lúc build đến khi workload khởi chạy, bao gồm cách registry lưu manifest và layer như thế nào?
Khi pipeline CI nhận lỗi 401 hoặc 403 lúc push image, bạn sẽ điều tra thông tin xác thực, token và quyền truy cập theo trình tự nào?
Bạn sẽ thiết kế quyền push, pull và xóa artifact trong registry cho lập trình viên, tài khoản CI và môi trường production theo nguyên tắc quyền tối thiểu ra sao?
Bạn tích hợp việc ký image và kiểm tra chữ ký trước khi triển khai như thế nào để xác minh nguồn gốc và tính toàn vẹn của artifact?
Nếu bước quét image phát hiện lỗ hổng nghiêm trọng ngay trước giờ phát hành, bạn đánh giá rủi ro và xác định điều kiện chặn, sửa hoặc chấp nhận ngoại lệ như thế nào?
Bạn sẽ thiết kế quy trình CI/CD để build image một lần, lưu vào registry và dùng cùng artifact đó xuyên suốt các môi trường kiểm thử đến production ra sao?
Trong quá trình thăng hạng một bản phát hành từ staging lên production, bạn làm gì để bảo đảm digest đã được kiểm thử không thay đổi và có thể truy vết việc phê duyệt?
Bạn xây dựng chính sách giữ phiên bản, xóa tag, dọn artifact không còn được tham chiếu và bảo vệ các digest cần rollback như thế nào?
Nếu tag đang dùng ở production đột ngột trỏ đến digest khác sau một lần push và ứng dụng lỗi, bạn sẽ truy vết sự thay đổi và khôi phục phiên bản ổn định ra sao?
Khi registry gặp sự cố mất dữ liệu hoặc gián đoạn kéo dài, bạn lập kế hoạch sao lưu, nhân bản, phục hồi manifest và layer, rồi kiểm chứng khả năng pull sau khôi phục như thế nào?
