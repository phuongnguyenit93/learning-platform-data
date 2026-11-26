Câu 1: Trong Hexagonal Architecture, inbound port biểu diễn điều gì?
A. Giao diện SQL mà database đưa ra cho ứng dụng
B. Điểm khởi tạo mọi kết nối giữa hai database
C. Chi tiết HTTP routing của riêng Spring MVC
D. Hợp đồng gọi use case từ bên ngoài
Đáp án đúng: D

Câu 2: Đối với API tạo đơn hàng, thành phần nào là inbound adapter?
A. JPA repository triển khai truy vấn lưu đơn hàng
B. Client SDK gọi hệ thống thanh toán bên thứ ba
C. REST controller chuyển dữ liệu vào use case
D. Bộ kết nối gửi sự kiện tới message broker
Đáp án đúng: C

Câu 3: Trong luồng lưu đơn hàng, outbound port nên diễn tả gì?
A. Cách cấu hình Hibernate SessionFactory cụ thể
B. Chi tiết JDBC URL và connection pool của môi trường
C. Hợp đồng lưu và tìm đơn hàng mà lõi cần dùng
D. Các HTTP header do controller tiếp nhận
Đáp án đúng: C

Câu 4: Một adapter JPA trong Ports & Adapters thường có nhiệm vụ gì?
A. Định nghĩa tất cả quy tắc tính tổng tiền trong entity
B. Quyết định toàn bộ thứ tự màn hình của web client
C. Tự thay thế mọi inbound port bằng repository
D. Hiện thực outbound port bằng truy cập dữ liệu JPA
Đáp án đúng: D

Câu 5: Chiều phụ thuộc mong muốn của mã lõi Hexagonal là gì?
A. Lõi import trực tiếp controller và JPA adapter
B. Lõi khai báo port và không phụ thuộc lớp adapter
C. Domain tham chiếu cấu hình Spring Boot để chạy
D. Use case tạo HTTP client bằng URL hardcode
Đáp án đúng: B

Câu 6: Nếu thay REST bằng CLI nhưng giữ nghiệp vụ, điểm mở rộng nào phù hợp?
A. Thêm inbound adapter CLI gọi cùng inbound port
B. Viết lại domain entity để xử lý tham số dòng lệnh
C. Đổi outbound repository thành một REST controller
D. Chuyển mọi quy tắc nghiệp vụ vào CLI mới
Đáp án đúng: A

Câu 7: Vì sao domain entity không nên dùng HttpServletRequest?
A. Vì mọi domain entity bắt buộc được lưu trong Redis
B. Vì HttpServletRequest chỉ hoạt động với JDBC
C. Vì lớp entity không thể có bất kỳ phương thức nào
D. Đó là chi tiết vận chuyển ngoài ranh giới domain
Đáp án đúng: D

Câu 8: Trong một use case đặt hàng, việc phối hợp domain và lưu trữ nằm ở đâu?
A. View template trực tiếp gọi EntityManager và cổng trả tiền
B. JPA entity tự lấy HTTP request để quyết định xử lý
C. Application use case điều phối qua các outbound port
D. Controller ghi SQL và tính toàn bộ chính sách giảm giá
Đáp án đúng: C

Câu 9: Thiết kế port thanh toán tốt ưu tiên hợp đồng nào?
A. postJson(url,headers,body) theo tên thư viện HTTP
B. createWebClient(baseUrl) theo cấu hình Spring
C. setConnectTimeout(milliseconds) theo mạng nội bộ
D. charge(paymentRequest) theo khái niệm nghiệp vụ
Đáp án đúng: D

Câu 10: Khi REST API đổi cấu trúc JSON, lớp nào nên chịu trách nhiệm ánh xạ?
A. Domain entity chứa trực tiếp Jackson annotation cho mọi API
B. Inbound adapter chuyển DTO sang lệnh use case
C. Outbound database adapter thay đổi cấu trúc JSON
D. Lớp core use case trực tiếp parse ServletInputStream
Đáp án đúng: B

Câu 11: Nếu core new JpaOrderRepository() ngay trong use case, nguyên tắc nào bị phá?
A. Đảo ngược phụ thuộc giữa use case và hạ tầng
B. Ranh giới DTO giữa view và REST endpoint
C. Cơ chế lazy loading bên trong ORM session
D. Chính sách retry khi giao tiếp message broker
Đáp án đúng: A

Câu 12: Trong Java, port có thể được biểu diễn bằng cấu trúc nào?
A. Controller class nằm trong package web của framework
B. Interface nằm phía lõi với phương thức theo nhu cầu
C. Cấu hình YAML cho URL của database production
D. Servlet filter xử lý token ở tầng HTTP
Đáp án đúng: B

Câu 13: Khi unit test use case với database chưa sẵn sàng, nên làm gì?
A. Khởi động production database bằng dữ liệu thật
B. Cấp fake repository triển khai outbound port
C. Mock toàn bộ entity để không cần kiểm tra domain
D. Bỏ qua kiểm thử vì use case phụ thuộc network
Đáp án đúng: B

Câu 14: Để xác nhận JPA adapter ánh xạ đúng, kiểu test nào phù hợp?
A. Integration test adapter với database thử nghiệm
B. Unit test use case chỉ với fake in-memory repository
C. Kiểm thử CSS của trang gọi endpoint nghiệp vụ
D. Chỉ kiểm tra interface port có tên đúng quy tắc
Đáp án đúng: A

Câu 15: Khi cần thay PostgreSQL bằng MongoDB, thay đổi nào cần được khoanh vùng?
A. Đổi tất cả command DTO của inbound adapter
B. Thay adapter lưu trữ, giữ hợp đồng port
C. Thay mọi domain rule bằng câu truy vấn của MongoDB
D. Buộc mọi use case trả MongoDB Document thay domain
Đáp án đúng: B

Câu 16: Một hệ thống có REST và message consumer cùng kích hoạt use case, thiết kế nào hợp lý?
A. Message consumer được đặt vào outbound repository
B. REST controller phải kế thừa message consumer
C. Mỗi kênh phải sao chép toàn bộ quy tắc domain
D. Hai inbound adapter gọi chung hợp đồng use case
Đáp án đúng: D

Câu 17: Một bộ xử lý event nhận từ Kafka kích hoạt nghiệp vụ thường thuộc loại gì?
A. Outbound adapter do lõi gọi để xuất sự kiện
B. Domain entity tự thực thi network listener
C. Inbound adapter nhận event rồi gọi use case
D. Repository adapter chỉ chịu trách nhiệm chạy SQL
Đáp án đúng: C

Câu 18: Một cổng gọi dịch vụ tỷ giá bên ngoài là ví dụ của gì?
A. Outbound port do HTTP client adapter hiện thực
B. Inbound port được triển khai bởi view template
C. Controller nội bộ bắt buộc kết nối trực tiếp database
D. Domain entity định nghĩa endpoint /exchange-rate
Đáp án đúng: A

Câu 19: Ai nên sở hữu interface OrderRepository ở thiết kế Hexagonal?
A. Lõi định nghĩa port theo nhu cầu use case
B. Bộ driver JDBC vì driver quyết định nghiệp vụ
C. Package của thư viện ORM vì nó sinh domain rule
D. Web controller vì nó xử lý JSON của client
Đáp án đúng: A

Câu 20: Khi thiết kế outbound port, dấu hiệu nào cho thấy abstraction bị rò rỉ?
A. Port dùng OrderId và trả Order theo miền nghiệp vụ
B. Port mô tả chức năng findById mà use case cần
C. Port trả Page<JpaEntity> và nhận EntityManager
D. Port có kết quả Optional khi không có bản ghi
Đáp án đúng: C

Câu 21: Nếu use case cần transaction, quyết định nào giúp giữ ranh giới?
A. Chèn DataSource vào từng domain entity để commit
B. Đặt transaction chỉ ở lớp view cho mọi luồng truy cập
C. Điều phối transaction ở application boundary phù hợp
D. Bắt controller trực tiếp tự commit mọi JPA session
Đáp án đúng: C

Câu 22: Một adapter trả lỗi HTTP 404 khi order không tồn tại nên xử lý thế nào?
A. Domain ném ResponseStatusException làm hợp đồng nghiệp vụ
B. Chuyển kết quả/lỗi use case sang HTTP ở inbound adapter
C. Outbound repository quyết định mã HTTP của REST client
D. Domain entity tự trả ResponseEntity ở mọi trường hợp
Đáp án đúng: B

Câu 23: Trong Spring Boot, việc kết nối port với adapter thường thực hiện ở đâu?
A. Constructor domain entity tự quét classpath controller
B. Composition root hoặc cấu hình dependency injection
C. Mỗi use case tra bean bằng ApplicationContext tĩnh
D. Lớp port tạo adapter bằng reflection ở mọi lời gọi
Đáp án đúng: B

Câu 24: Một outbound adapter gửi email mới có thể dùng port nào sẵn có?
A. NotificationPort để use case phát thông báo
B. OrderController chỉ dùng để trả JSON cho client
C. CustomerView được render trên trình duyệt web
D. Command DTO dành riêng để nhận HTTP request
Đáp án đúng: A

Câu 25: Vì sao không nên tạo một port CRUD chung cho mọi bảng một cách máy móc?
A. Vì Hexagonal cấm tất cả thao tác cập nhật dữ liệu
B. Vì ORM chỉ tương thích với interface có đúng một method
C. Vì các bảng database không có khóa định danh
D. Port theo nhu cầu use case, không mô phỏng cấu trúc bảng
Đáp án đúng: D

Câu 26: Trong phép thử core, điểm nào chứng minh cô lập framework tốt?
A. Test luôn cần khởi động web server thật trên port 8080
B. Test cần mở transaction bằng repository production
C. Test yêu cầu container Kafka trước mỗi assertion
D. Use case chạy bằng POJO và fake port, không cần Spring
Đáp án đúng: D

Câu 27: Khi tách module Gradle theo Hexagonal, quy tắc nào đúng?
A. Module adapter phụ thuộc module core, không ngược lại
B. Module core phụ thuộc mọi adapter để gọi implementation
C. Module domain phụ thuộc controller để nhận dữ liệu
D. Module use case phải import cấu hình JPA trong adapter
Đáp án đúng: A

Câu 28: Muốn chuyển dần ứng dụng Spring đang trộn logic vào controller, bước nào hợp lý?
A. Viết lại toàn bộ dữ liệu và giao diện trước khi tạo port
B. Di chuyển mọi repository thành controller mới trước tiên
C. Tách use case/port để controller cũ gọi vào
D. Đổi package bằng tên hexagonal mà không đổi dependency
Đáp án đúng: C
