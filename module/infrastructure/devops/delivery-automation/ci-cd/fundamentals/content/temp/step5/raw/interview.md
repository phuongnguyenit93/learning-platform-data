Bạn phân biệt tích hợp liên tục, phân phối liên tục và triển khai liên tục như thế nào, và điều kiện nào khiến một nhóm nên chọn từng mức tự động hóa?
Bạn sẽ thiết kế quy tắc kích hoạt pipeline từ commit, pull request, merge và Git tag như thế nào để vừa phản hồi sớm vừa tránh phát hành nhầm thay đổi chưa được duyệt?
Khi xây dựng pipeline dưới dạng mã, bạn tổ chức các stage, job và quan hệ phụ thuộc ra sao để dễ kiểm tra thay đổi, tái sử dụng và xác định bước gây lỗi?
Bạn làm gì để một bản build chạy trên máy phát triển và CI tạo ra kết quả nhất quán, kể cả khi phụ thuộc hoặc phiên bản công cụ có thể thay đổi?
Bạn sẽ sắp xếp unit test, integration test và kiểm thử đầu cuối trong pipeline thế nào để cân bằng tốc độ phản hồi với độ tin cậy của bản phát hành?
Khi pipeline chạy chậm vì tải dependency và build lặp lại, bạn đánh giá cách dùng cache và chạy song song như thế nào mà vẫn tránh dùng kết quả cũ hoặc sai?
Bạn thiết kế cách đặt phiên bản, lưu trữ và truy vết artifact từ commit nguồn đến bản đang chạy trong production như thế nào để có thể triển khai lại chính xác?
Bạn bảo vệ thông tin bí mật và quyền của tài khoản CI/CD ra sao khi pipeline phải truy cập registry hoặc môi trường triển khai, nhất là với mã từ pull request bên ngoài?
Bạn sẽ xác định cổng chất lượng trước khi phát hành dựa trên kết quả kiểm thử, phân tích mã và quét lỗ hổng như thế nào khi một kiểm tra cho kết quả không ổn định hoặc có cảnh báo ngoại lệ?
Bạn quản lý cấu hình và quyền phê duyệt cho môi trường development, staging và production ra sao để hạn chế khác biệt môi trường và ngăn triển khai ngoài ý muốn?
Sau khi tự động triển khai một phiên bản mới, bạn sẽ kiểm chứng sức khỏe ứng dụng và quyết định tiếp tục hoặc dừng phát hành dựa trên tín hiệu nào?
Nếu bản phát hành vượt qua CI nhưng gây lỗi trên production, bạn sẽ truy vết từ commit, pipeline và artifact đến lần triển khai, thực hiện quay lui và xác nhận phục hồi như thế nào?
