Trong Onion Architecture, chiều phụ thuộc mã nguồn nào là đúng?
A. Domain import adapter để tự kết nối database
B. Vòng ngoài import abstraction ở vòng trong
C. Application gọi ngược controller để xử lý HTTP
D. Các lớp import hai chiều để dùng chung tính năng
Đáp án đúng: B

Domain service trực tiếp tạo JDBC Connection đi ngược mục tiêu nào?
A. Giữ use case có thể gọi từ nhiều endpoint
B. Giữ quy tắc định giá trong domain model
C. Giữ domain không lệ thuộc cách lưu trữ
D. Giữ controller tách khỏi DTO của tầng view
Đáp án đúng: C

Repository interface mà use case cần để lấy Order nên đặt ở đâu?
A. Lớp trong khai báo nhu cầu truy cập dữ liệu
B. Trong presentation cạnh thành phần render
C. Trong infrastructure cạnh driver DB cụ thể
D. Trong controller xử lý tuyến HTTP gọi vào
Đáp án đúng: A

Lớp JdbcOrderRepository hiện thực một port nên nằm ở đâu?
A. Infrastructure triển khai port của core
B. Domain, nơi entity tạo câu lệnh SQL
C. Application, nơi use case mở kết nối JDBC
D. Presentation, nơi controller viết query
Đáp án đúng: A

Use case tạo đơn trong application thường có vai trò gì?
A. Đăng ký route HTTP cho các phiên bản API
B. Quản lý kết nối và pool của JDBC driver
C. Tự triển khai toàn bộ SQL cho từng database
D. Phối hợp domain objects và các port
Đáp án đúng: D

Bất biến đơn hàng không được có tổng âm nên được bảo vệ ở đâu?
A. Cấu hình gateway, trước khi chuyển HTTP
B. Domain model, không chỉ ở lớp nhận request
C. Controller REST, trước khi gửi vào service
D. Repository adapter, trước khi mapping row DB
Đáp án đúng: B

Controller REST ở vòng ngoài nên dùng nghiệp vụ như thế nào?
A. Truy cập trực tiếp bảng để chạy mọi validation
B. Đặt tất cả quy tắc business trong HTTP handler
C. Chuyển dữ liệu vào và gọi use case tương ứng
D. Đưa Servlet API vào mọi entity của domain
Đáp án đúng: C

Thiết kế nào thể hiện dependency inversion ở ranh giới dữ liệu?
A. Entity domain gọi trực tiếp Redis client
B. Core import package của Hibernate Session
C. Use case dùng new để tạo adapter JDBC cụ thể
D. Use case phụ thuộc một Repository port
Đáp án đúng: D

Tại composition root của ứng dụng, công việc nào thường diễn ra?
A. Nối adapter vào port của core khi khởi tạo
B. Để use case tự sửa import lúc khởi động
C. Đặt toàn bộ quy tắc nghiệp vụ trong main
D. Để entity tự quét classpath chọn adapter
Đáp án đúng: A

Muốn kiểm thử domain rule giảm giá độc lập hạ tầng, cách nào phù hợp?
A. Chạy browser qua Selenium trước khi assert
B. Mở cơ sở dữ liệu và broker ở mọi unit test
C. Khởi chạy REST server để gọi mỗi domain rule
D. Tạo domain object rồi kiểm tra hành vi
Đáp án đúng: D

Khi test use case mà không kết nối DB, cách nào phù hợp?
A. Tạo JDBC connection thật trong mỗi test
B. Thay persistence port bằng fake repository
C. Mock toàn bộ domain entity thay cho port
D. Mock luôn chính use case để khỏi chạy logic
Đáp án đúng: B

Thay một loại cơ sở dữ liệu mà port vẫn phù hợp, lớp nào cần sửa chủ yếu?
A. Các tuyến HTTP trên presentation layer
B. Adapter lưu trữ ở tầng infrastructure
C. Các bất biến được giữ trong entity domain
D. Hợp đồng đầu vào của use case application
Đáp án đúng: B

Cách nào vi phạm nguyên tắc cách ly domain với công nghệ gửi sự kiện?
A. Domain phát event độc lập framework
B. Adapter phía ngoài publish qua một port
C. Entity trực tiếp gọi SDK message broker
D. Application gọi port thông báo ở lớp trong
Đáp án đúng: C

Request DTO gắn với HTTP nên được xử lý thế nào khi gọi domain?
A. Chuyển dữ liệu tại ranh giới vào use case
B. Để entity domain trực tiếp đọc HTTP header
C. Nhúng route URL vào trường dữ liệu domain
D. Đưa nguyên ServletRequest vào entity domain
Đáp án đúng: A

Chiều import giữa core và adapter nào phù hợp Onion Architecture?
A. Hai bên import nhau để tự chọn implementation
B. Core import mọi repository adapter cần dùng
C. Core import REST controller để chia sẻ model
D. Adapter import port core, không có chiều ngược
Đáp án đúng: D

Khi nào việc thêm abstraction giúp Onion Architecture rõ ràng hơn?
A. Khi mọi class phải có interface đồng tên
B. Khi muốn domain gọi trực tiếp SDK của DB
C. Khi boundary cần đảo chiều phụ thuộc
D. Khi controller phải chứa mọi business rule
Đáp án đúng: C
