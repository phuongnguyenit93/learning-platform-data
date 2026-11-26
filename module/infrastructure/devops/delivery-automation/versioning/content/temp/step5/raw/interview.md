Bạn sẽ giải thích ý nghĩa của MAJOR, MINOR và PATCH trong Semantic Versioning như thế nào, và cần xác định hợp đồng tương thích nào trước khi áp dụng quy tắc tăng phiên bản?
Khi một API thay đổi kiểu dữ liệu của trường phản hồi, một tính năng mới được bổ sung và một lỗi cũ được sửa, bạn sẽ đánh giá tác động tương thích để chọn mức tăng phiên bản cho từng thay đổi ra sao?
Với một thư viện đang ở phiên bản 0.x.y và chưa cam kết API ổn định, bạn sẽ truyền đạt kỳ vọng tương thích cho người dùng và quyết định thời điểm phát hành 1.0.0 như thế nào?
Bạn sẽ so sánh thứ tự các bản 2.3.0-alpha.2, 2.3.0-alpha.10, 2.3.0-rc.1 và 2.3.0 theo SemVer ra sao, và áp dụng quy tắc đó khi chọn bản để kiểm thử hoặc phát hành thế nào?
Bạn sẽ sử dụng build metadata như mã commit hoặc định danh job CI trong phiên bản theo SemVer như thế nào, và cần lưu ý điều gì khi so sánh độ ưu tiên giữa các phiên bản có metadata khác nhau?
Git tag, phiên bản khai báo trong mã nguồn và phiên bản artifact có vai trò khác nhau như thế nào, và bạn sẽ bảo đảm chúng cùng trỏ về đúng một bản phát hành bất biến bằng cách nào?
Đối với ứng dụng Java được đóng gói thành JAR và container image, bạn sẽ thiết lập cách đặt phiên bản và ghi nhận định danh artifact như thế nào để đối chiếu chính xác với commit đã build?
Khi một thư viện phụ thuộc công bố bản MINOR mới nhưng làm hỏng ứng dụng, bạn sẽ điều tra hợp đồng tương thích, ràng buộc phiên bản dependency và chính sách nâng cấp như thế nào?
Bạn sẽ xây dựng và rà soát changelog từ commit hoặc pull request như thế nào để người dùng nhận biết thay đổi quan trọng, tính tương thích ngược và các bước di chuyển bắt buộc?
Bạn sẽ thiết kế quy trình phát hành tự động từ Git tag trong CI/CD ra sao để kiểm thử, tạo phiên bản, công bố artifact và xử lý an toàn trường hợp job bị chạy lại hoặc hai lần phát hành diễn ra đồng thời?
Khi cần xác định chính xác phiên bản đang chạy trên production, bạn sẽ liên kết thông tin từ deployment, artifact hoặc image digest, Git tag, commit và lịch sử pipeline như thế nào để kiểm chứng nguồn gốc?
Nếu phải rollback một bản production bị lỗi rồi phát hành hotfix, bạn sẽ tổ chức phiên bản, tag, changelog và artifact như thế nào để tránh nhầm lẫn giữa bản đã triển khai, bản đã thu hồi và bản sửa mới?
