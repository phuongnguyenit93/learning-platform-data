Bạn xác định những tương tác nào giữa controller, service và database cần được kiểm chứng bằng integration test thay vì unit test?
Khi một API trả HTTP 201, bạn thu thập bằng chứng gì để xác nhận dữ liệu đã được lưu đúng chứ không chỉ phản hồi thành công?
Bạn lựa chọn @SpringBootTest, @WebMvcTest hoặc @DataJpaTest theo tương tác thực tế cần kiểm chứng ra sao?
Bạn tổ chức Spring TestContext và test profile để chỉ khởi tạo những bean cần thiết mà vẫn phản ánh cấu hình production như thế nào?
Nếu một integration test xanh trên máy cá nhân nhưng thiếu bean trên CI, bạn truy tìm sự khác biệt cấu hình từ đâu?
Bạn xác định khi nào tái sử dụng ApplicationContext và khi nào dùng @DirtiesContext để tránh rò rỉ trạng thái giữa các test?
Bạn cấu hình Testcontainers với cùng loại và phiên bản database sử dụng ở môi trường vận hành như thế nào?
Bạn chọn database chạy trong Testcontainers hay database nhúng dựa trên loại lỗi tích hợp cần phát hiện ra sao?
Bạn truyền địa chỉ kết nối và credential sinh động của container vào Spring TestContext bằng cơ chế nào?
Bạn thiết kế health check và readiness cho container để tránh chạy truy vấn khi dịch vụ chưa khởi động hoàn chỉnh ra sao?
Bạn giữ các bài test độc lập về dữ liệu trong khi tái sử dụng container để giảm thời gian khởi động bằng cách nào?
Bạn kiểm tra một migration database bằng dữ liệu có từ phiên bản trước để phát hiện lỗi tương thích như thế nào?
Bạn tạo fixture có quan hệ khóa ngoại phức tạp mà vẫn dễ đọc và dễ bảo trì bằng cách nào?
Bạn lựa chọn seed bằng SQL, factory Java hoặc gọi API thiết lập dữ liệu tùy theo mục tiêu xác minh như thế nào?
Bạn xử lý các cột unique và khóa sinh tự động để các integration test chạy song song không va chạm dữ liệu ra sao?
Bạn phân biệt rollback transaction của test với transaction do request HTTP thực hiện trên thread khác như thế nào?
Trong tình huống controller gọi service và repository rồi lỗi giữa chừng, bạn kiểm tra rollback thực sự bằng cách nào?
Bạn kiểm thử các ranh giới transaction khi một service gọi phương thức khác với propagation mới như thế nào?
Bạn thiết kế tình huống hai giao dịch cập nhật đồng thời để xác minh optimistic locking mà không phụ thuộc lịch thực thi ngẫu nhiên ra sao?
Khi một bài test luôn rollback, bạn làm thế nào để phát hiện lỗi chỉ xuất hiện tại thời điểm flush hoặc commit?
Bạn kiểm tra ràng buộc database như unique, not-null và foreign key để chắc chắn exception được dịch đúng ở tầng service như thế nào?
Bạn sử dụng JUnit Jupiter lifecycle để quản lý fixture, cleanup và tài nguyên container theo phạm vi từng ca kiểm thử ra sao?
Bạn thiết kế @ParameterizedTest để bao phủ nhiều tổ hợp dữ liệu đầu vào mà mỗi ca thất bại vẫn có thông báo rõ ràng như thế nào?
Bạn chọn MockMvc, WebTestClient hoặc client HTTP thật dựa trên phần của HTTP stack phải được kiểm thử như thế nào?
Bạn kiểm chứng security filter, xác thực và phân quyền khi gọi API thật bằng Spring Test như thế nào?
Bạn bảo đảm một truy vấn có tenant ID không vô tình trả dữ liệu của tenant khác qua API như thế nào?
Bạn kiểm tra việc ánh xạ JSON sang DTO, validation và xử lý lỗi HTTP trong cùng một integration test ra sao?
Bạn thiết kế assertions trên bản ghi database sau khi API xử lý để phát hiện sai lệch do mapping hoặc trigger như thế nào?
Bạn chọn kiểm tra trạng thái nghiệp vụ nào để tránh test phụ thuộc vào thứ tự cột hoặc cách triển khai SQL ra sao?
Bạn kiểm tra việc ghi dữ liệu và phát message qua broker khi hai thao tác không nằm trong cùng một transaction như thế nào?
Bạn dùng Testcontainers để chạy broker thật và xác minh routing key, header cùng payload phát ra ra sao?
Bạn quyết định khi nào thay broker bằng fake và khi nào phải dùng broker thật để kiểm tra ack, retry hoặc phân phối thông điệp?
Bạn xây dựng consumer test để xác nhận một message bị gửi trùng không tạo tác động nghiệp vụ trùng lặp như thế nào?
Bạn thiết kế kiểm thử dead-letter queue và số lần retry mà không dùng Thread.sleep cố định ra sao?
Bạn chờ một trạng thái bất đồng bộ xuất hiện trong database với timeout và điều kiện quan sát được như thế nào?
Bạn mô phỏng sự cố broker không khả dụng giữa một luồng xử lý và kiểm tra chính sách phục hồi bằng cách nào?
Bạn tích hợp HTTP stub server để điều khiển response, timeout và lỗi kết nối của dịch vụ bên ngoài như thế nào?
Bạn xác minh client gửi đúng method, path, headers và body mà không gắn test vào chi tiết serialization không cần thiết ra sao?
Bạn chọn dữ liệu thử cho các phản hồi 4xx, 5xx và timeout của đối tác nhằm kiểm tra hành vi fallback như thế nào?
Bạn kiểm tra retry có backoff của HTTP client để tránh tình huống thử lại vô hạn hoặc gửi trùng tác vụ không idempotent ra sao?
Bạn so sánh contract test và integration test chạy với sandbox thật khi muốn phát hiện thay đổi API từ nhà cung cấp như thế nào?
Bạn đảm bảo các test không kết nối nhầm tới hệ thống production dù biến môi trường CI bị cấu hình sai như thế nào?
Bạn kiểm tra cách ứng dụng xử lý sự kiện có schema cũ khi producer và consumer được triển khai ở thời điểm khác nhau ra sao?
Bạn ghi nhận log SQL, HTTP và message correlation ID thế nào để lần theo một bài test thất bại qua nhiều thành phần?
Bạn thu thập log từ container thất bại mà vẫn ẩn password, token và dữ liệu riêng tư bằng cách nào?
Bạn phân biệt một lỗi do business logic với lỗi do image container, DNS hoặc network isolation dựa trên những dấu hiệu gì?
Bạn chuẩn bị cấu hình Docker và tài nguyên CI nào để bộ Testcontainers không bị flaky do thiếu bộ nhớ hoặc timeout?
Bạn lựa chọn chạy tuần tự hay song song các integration test khi nhiều ca chia sẻ database hoặc broker như thế nào?
Bạn phân bổ bộ integration test nhanh cho pull request và bộ kiểm thử mở rộng chạy định kỳ dựa trên rủi ro nào?
Bạn đo thời gian tải Spring context, khởi động container và thực thi query để xác định điểm tốn thời gian trong suite như thế nào?
Nếu một test chỉ chạy đúng khi theo sau test khác, bạn truy tìm trạng thái nào chưa được dọn dẹp ra sao?
Bạn thiết kế negative test cho database hoặc broker để kiểm chứng thông báo lỗi ứng dụng mà không phụ thuộc vào chuỗi lỗi nhà cung cấp như thế nào?
Bạn xác minh một luồng API cập nhật nhiều bảng rồi phát sự kiện có giữ các bất biến nghiệp vụ sau khi thất bại ở bước cuối như thế nào?
Bạn đánh giá chất lượng integration suite qua khả năng phát hiện lỗi cấu hình, migration, transaction và hợp đồng giao tiếp thay vì chỉ đếm test pass như thế nào?
