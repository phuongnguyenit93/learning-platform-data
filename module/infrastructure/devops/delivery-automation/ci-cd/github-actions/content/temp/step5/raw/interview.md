Trong GitHub Actions, bạn sẽ giải thích vai trò của workflow YAML, job, step và action như thế nào, và những điểm cấu hình nào quyết định một workflow được thực thi?
Bạn sẽ lựa chọn và kết hợp các sự kiện push, pull_request và workflow_dispatch cùng bộ lọc nhánh hoặc đường dẫn ra sao để chạy CI đúng lúc mà không bỏ sót thay đổi quan trọng?
Khi lựa chọn giữa GitHub-hosted runner và self-hosted runner cho dự án Java, bạn sẽ cân nhắc những yếu tố nào về môi trường build, tài nguyên, truy cập mạng và rủi ro bảo mật?
Một pipeline cần kiểm thử thành công trước khi đóng gói và phát hành; bạn sẽ tổ chức quan hệ phụ thuộc giữa các job, điều kiện chạy và việc truyền kết quả ra sao để giữ đúng thứ tự?
Bạn sẽ thiết kế matrix để kiểm thử dự án Java trên nhiều phiên bản JDK hoặc hệ điều hành như thế nào, đồng thời kiểm soát thời gian chạy, số job song song và cách xử lý một cấu hình thất bại?
Cache dependency và workflow artifact trong GitHub Actions khác nhau về mục đích, vòng đời và phạm vi sử dụng như thế nào, và khi nào bạn sẽ chọn từng cơ chế?
Nếu một workflow Maven hoặc Gradle chạy ổn trên máy phát triển nhưng thất bại trên GitHub Actions, bạn sẽ kiểm tra môi trường JDK, dependency, lệnh build và log theo trình tự nào?
Bạn sẽ thiết kế quy trình kiểm thử, đóng gói và lưu artifact cho ứng dụng Java ra sao để một bản phát hành có thể truy ngược về commit và lần chạy CI đã tạo ra nó?
Khi nhiều repository cần cùng một quy trình build và phát hành, bạn sẽ quyết định lúc nào nên dùng reusable workflow hoặc composite action, và quản lý phiên bản phần tái sử dụng ấy thế nào?
Đối với workflow chạy trên pull request từ fork, bạn sẽ đánh giá rủi ro lộ secrets và lạm dụng GITHUB_TOKEN như thế nào, đồng thời giới hạn quyền của token ở đâu?
Bạn sẽ thiết lập xác thực OIDC từ GitHub Actions tới nhà cung cấp đám mây như thế nào để phát hành mà không lưu khóa truy cập dài hạn, và cần ràng buộc những thuộc tính tin cậy nào?
Nếu hai lần chạy workflow cùng triển khai lên production và một lần phát hành gặp lỗi, bạn sẽ vận dụng environment protection, approval, concurrency và cơ chế rollback ra sao để giảm rủi ro?
