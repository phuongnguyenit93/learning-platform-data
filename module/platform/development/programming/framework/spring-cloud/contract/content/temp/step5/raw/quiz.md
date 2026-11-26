Câu 01. Mục tiêu của kiểm thử hợp đồng giữa hai dịch vụ là gì?
A. Kiểm kích thước heap của consumer khi gọi dịch vụ
B. Xác minh hành vi request/response mà hai phía đã cam kết
C. Đo throughput HTTP khi tăng số kết nối đồng thời
D. Đánh giá cách producer tổ chức transaction nội bộ
Đáp án đúng: B

Câu 02. Với Spring Cloud Contract, producer cần xác minh điều gì trên build của mình?
A. Stub Runner đã dùng hết cổng mạng khả dụng trong CI
B. Consumer có thể ghi trực tiếp vào database của producer
C. Implementation thực tế đáp ứng những contract đã công bố
D. Controller của producer được gọi trực tiếp từ consumer test
Đáp án đúng: C

Câu 03. Consumer kiểm thử tích hợp với stub có lợi thế chính nào?
A. Thay thế toàn bộ unit test của ứng dụng phía consumer
B. Chứng minh các contract chưa công bố đều tương thích
C. Kiểm logic lưu trữ nội bộ của producer trên database thật
D. Kiểm mã gọi API mà không cần chạy producer thực tế
Đáp án đúng: D

Câu 04. Trong Groovy DSL của HTTP contract, cặp cấu phần nào mô tả hành vi chính?
A. `buildscript` mô tả status và `dependencies` mô tả method
B. `request` mô tả đầu vào và `response` mô tả đầu ra
C. `triggeredBy` mô tả URL và `outputMessage` mô tả status
D. `baseClass` mô tả HTTP body và `stubRunner` mô tả header
Đáp án đúng: B

Câu 05. Groovy DSL và YAML DSL của Spring Cloud Contract được dùng để làm gì?
A. Điều khiển thread pool HTTP trong producer lúc khởi động
B. Biểu diễn hợp đồng hành vi để sinh test và stub tương ứng
C. Phân phối schema database cho các worker của consumer
D. Thay thế controller bằng response cache ở môi trường thật
Đáp án đúng: B

Câu 06. Muốn contract HTTP áp dụng cho `POST /orders`, cần khai báo gì?
A. HTTP method POST và đường dẫn `/orders` trong request
B. HTTP status 201 và đường dẫn `/orders` trong request
C. HTTP header Location và đường dẫn `/orders` trong response
D. HTTP method GET và đường dẫn `/orders` trong response
Đáp án đúng: A

Câu 07. Đối với body JSON đầu vào có mã đơn hàng thay đổi, loại kiểm tra nào phù hợp?
A. Bỏ kiểm JSON và chỉ đối chiếu HTTP status của producer
B. Dùng matcher/regex để chấp nhận giá trị theo mẫu hợp lệ
C. Gán cứng mã đơn hàng vào yêu cầu hợp lệ khi test
D. Chỉ so độ dài response mà không kiểm request body
Đáp án đúng: B

Câu 08. Contract mô tả tạo đơn hàng thành công nên kiểm những gì ở response?
A. Tên controller và số dòng Java trong service producer
B. Chiều dài stack trace cùng tên package khi chạy test
C. HTTP status cùng các trường body/header đã cam kết
D. Số kết nối JDBC và dung lượng heap sau mỗi lần gọi
Đáp án đúng: C

Câu 09. Muốn kiểm trường hợp GET đơn hàng không tồn tại, contract nên mô tả gì?
A. Chỉ cấu hình bộ mock database mà không khai báo HTTP
B. Chỉ đặt timeout trong Stub Runner mà không nêu response
C. Request xác định và response lỗi với status phù hợp
D. Request hợp lệ và response thành công được cache từ trước
Đáp án đúng: C

Câu 10. Khi API cam kết response JSON, phần header nào nên có trong contract?
A. `Authorization` ghi checksum của response JSON đã trả
B. `Accept` chỉ khai báo danh sách profile của producer
C. `Connection` lưu phiên bản schema database của consumer
D. `Content-Type` tương ứng kiểu nội dung JSON được trả
Đáp án đúng: D

Câu 11. Một field response chứa timestamp không cố định; cách viết contract nào giảm test giòn?
A. Xác minh định dạng bằng matcher thay vì thời gian cố định
B. Cố định timestamp bằng cách đổi thời gian của build agent
C. Loại bỏ kiểm response cho các field ngoài timestamp
D. Thay timestamp thành tên endpoint để stub dễ trả về hơn
Đáp án đúng: A

Câu 12. Khi cần kiểm thuộc tính lồng nhau trong request JSON, matcher thường dựa vào gì?
A. Tên class DTO mà client đã ghi trong application.yml
B. Đường dẫn thư mục Maven tới file contract tạo test
C. Tên bean Spring của controller xử lý request hiện tại
D. Đường dẫn JSONPath tới trường cần xác minh trong body
Đáp án đúng: D

Câu 13. Contract HTTP có query parameter bắt buộc `page`; nên mô tả ở đâu?
A. Trong artifact metadata thay cho HTTP request matcher
B. Trong phần request với tham số query cần so khớp
C. Trong phần response status thay cho điều kiện request
D. Trong cấu hình test base class thay cho HTTP request
Đáp án đúng: B

Câu 14. Khi contract có authorization header, test tốt nên làm gì?
A. Đưa access token production vào contract đã commit
B. Bỏ header trong request vì Stub Runner tự cấp token
C. Chỉ kiểm cookie session thay vì header mà API yêu cầu
D. Kiểm header hiện diện/đúng mẫu, tránh nhúng token thật
Đáp án đúng: D

Câu 15. Vì sao không nên ghi cứng một UUID sinh ngẫu nhiên vào kỳ vọng response?
A. Giá trị biến động khiến test dễ thất bại dù API đúng
B. Giá trị biến động làm Maven không xuất bản được stub JAR
C. Giá trị biến động khiến producer không thể trả mã HTTP
D. Giá trị biến động buộc WireMock đóng cổng sau mỗi lần gọi
Đáp án đúng: A

Câu 16. Theo cấu hình mặc định, producer thường đặt các file contract ở đâu?
A. Trong `.mvn/repository/contracts` bên trong dự án
B. Trong `src/test/resources/contracts` của dự án producer
C. Trong `src/main/java/contracts` của dự án producer
D. Trong `target/classes/contracts` như file Java chính
Đáp án đúng: B

Câu 17. Contract plugin dùng HTTP DSL để tạo loại kiểm thử nào phía producer?
A. Test kiểm tính ổn định CPU của từng thread web server
B. Test xác nhận HTTP implementation tuân thủ contract
C. Test xác nhận schema database theo migration mới nhất
D. Test thay producer bằng stub không gọi API implementation
Đáp án đúng: B

Câu 18. Producer sửa response status từ 200 sang 201 trái contract; tín hiệu nào mong đợi?
A. Generated contract test thất bại vì status không khớp
B. Client tự chuyển response về status đã công bố
C. Contract test chỉ kiểm body nên không phát hiện status
D. Stub Runner tự sửa contract sang status mới của server
Đáp án đúng: A

Câu 19. Khi test sinh ra cần gọi controller trong ngữ cảnh Spring MVC, base test nên chuẩn bị gì?
A. Một artifact stub đã deploy để thay implementation thật
B. Một broker message thay cho các request tới controller
C. MockMvc hoặc môi trường HTTP thích hợp cho generated test
D. Worker thread chạy mỗi contract như một scheduled task
Đáp án đúng: C

Câu 20. Contract test sinh ra phía producer khác unit test của service chủ yếu ở đâu?
A. Nó chỉ đánh giá thuật toán tính toán của method private
B. Nó chỉ đo thời gian kết nối JDBC của service nội bộ
C. Nó xác minh interface được cam kết qua hành vi bên ngoài
D. Nó chỉ kiểm trường hợp không liên quan tới HTTP contract
Đáp án đúng: C

Câu 21. Từ HTTP contract, loại stub nào thường được sinh để dùng cho consumer?
A. WireMock mapping mô phỏng request và response theo DSL
B. Một binary JVM chứa class controller của producer
C. Một cấu hình Spring Security bật toàn bộ authorization
D. Một bản sao đầy đủ của database và business service
Đáp án đúng: A

Câu 22. Khi publish stub của producer dưới dạng Maven artifact, classifier thường dùng là gì?
A. Classifier `tests` để phân biệt artifact stub của service
B. Classifier `sources` để phân biệt artifact stub của service
C. Classifier `stubs` để phân biệt artifact stub của service
D. Classifier `javadoc` để phân biệt artifact stub của service
Đáp án đúng: C

Câu 23. Vì sao dùng version rõ ràng khi publish stub artifact trong CI?
A. Consumer tự phát hiện database schema mà không cần API
B. Producer tự đổi cổng web server theo classifier artifact
C. Consumer có thể chọn hợp đồng theo đúng phiên bản producer
D. Producer tự cập nhật các dependency runtime ở consumer
Đáp án đúng: C

Câu 24. Khi consumer test cần mô phỏng producer từ stub artifact, thành phần nào hỗ trợ?
A. ApplicationRunner thay thế logic HTTP client của consumer
B. Actuator nạp artifact rồi tự ghi kết quả vào producer
C. JobLauncher đọc contract rồi sinh dữ liệu cho database
D. Stub Runner tải và khởi chạy stub phục vụ HTTP
Đáp án đúng: D

Câu 25. Annotation Spring Cloud Contract thường dùng để thiết lập Stub Runner cho test là gì?
A. `@EnableFeignClients` cấu hình stub server của producer
B. `@AutoConfigureStubRunner` cấu hình stub server cho test
C. `@AutoConfigureMockMvc` cấu hình stub server của producer
D. `@EnableDiscoveryClient` cấu hình stub server cho test
Đáp án đúng: B

Câu 26. Chế độ Stub Runner nào phù hợp khi artifact stub đã nằm trong local Maven repository?
A. `StubsMode.LOCAL` đọc stub artifact từ repository máy
B. `StubsMode.REMOTE` đọc stub artifact từ repository máy
C. `StubsMode.CLASSPATH` truy cập repository Maven qua mạng
D. `StubsMode.PRODUCER` đọc artifact từ repository máy
Đáp án đúng: A

Câu 27. Nếu CI cần lấy stub artifact từ repository chia sẻ, cấu hình hướng nào phù hợp?
A. Dùng classpath test để thay nội dung artifact trên server
B. Dùng một mock controller viết tay thay cho stub version
C. Dùng LOCAL và khóa toàn bộ truy cập network ở CI
D. Dùng REMOTE và cấu hình repository artifact truy cập được
Đáp án đúng: D

Câu 28. Stub Runner được cấp cổng ngẫu nhiên; consumer test nên tìm cổng như thế nào?
A. Suy cổng từ tên contract rồi cộng số phiên bản artifact
B. Gắn cứng cổng 8080 trong test ở từng môi trường CI
C. Đọc cổng quản trị từ JobRepository của producer đang chạy
D. Tra cổng của stub đang chạy qua API/đăng ký Stub Runner
Đáp án đúng: D

Câu 29. Trong consumer test, stub HTTP chứng minh chắc chắn điều gì?
A. Client xử lý các hành vi được mô phỏng từ contract
B. Producer đang triển khai chính xác từng endpoint trên production
C. Hệ thống database producer đang giữ dữ liệu nhất quán
D. Mạng thật giữa hai dịch vụ không có lỗi trong production
Đáp án đúng: A

Câu 30. Nếu consumer gọi URL không có mapping trong HTTP stub, nên kiểm gì trước?
A. Tên branch Git được checkout khi client code biên dịch
B. Số thread dành cho message listener của service consumer
C. Method, path, body và header so với mapping được phát hành
D. Thứ tự các migration của database bên phía producer
Đáp án đúng: C

Câu 31. Đối với contract thông điệp bất đồng bộ, DSL có thể khai báo gì?
A. Cấu hình servlet filter để ánh xạ message sang HTTP
B. Đường dẫn GET đóng vai trò destination của message
C. Điều kiện kích hoạt và message đầu ra được kỳ vọng
D. JDBC transaction của consumer dùng khi đọc endpoint
Đáp án đúng: C

Câu 32. Trong message contract, `triggeredBy` thường mô tả điều gì?
A. Địa chỉ URL của consumer dùng để gọi HTTP producer
B. Phương thức deserialize dữ liệu ở consumer runtime
C. Artifact classifier dùng để đóng gói stub lên Maven
D. Thao tác phía producer kích hoạt phát một message
Đáp án đúng: D

Câu 33. Trong message contract, `sentTo` thường xác định điều gì?
A. Đích nhận thông điệp trong output message
B. Tên base class của generated test phía producer
C. Tên dependency được Stub Runner tải từ Maven
D. Port HTTP mà producer dùng cho REST endpoint
Đáp án đúng: A

Câu 34. Khi producer phát event, hợp đồng message nên kiểm thông tin nào?
A. Destination, header và body đã thỏa thuận giữa hai phía
B. Tên package Java chứa method xử lý message nội bộ
C. Thông số connection pool của database phía consumer
D. Đường dẫn servlet context của HTTP producer service
Đáp án đúng: A

Câu 35. Để kiểm message thật được phát từ producer, test sinh ra cần tích hợp với gì?
A. Bean `ViewResolver` của ứng dụng Spring MVC hiện tại
B. JPA schema migrator chạy trước consumer HTTP test
C. Web server Stub Runner thay producer message thật
D. Cơ chế test message verifier/broker adapter phù hợp
Đáp án đúng: D

Câu 36. Producer thêm một field bắt buộc vào request khiến consumer cũ không gửi được; điều gì cần đánh giá?
A. Định dạng version Git của release pipeline producer
B. Thứ tự các message listener trong consumer test
C. Thông số heap của Stub Runner khi tải artifact version cũ
D. Khả năng tương thích với các contract consumer đang dùng
Đáp án đúng: D

Câu 37. Với API có response lỗi nghiệp vụ 422, nên đưa vào contract như thế nào?
A. Chỉ cấu hình HTTP timeout mà không ghi status lỗi
B. Chỉ đưa response thành công vào contract để test ổn định
C. Mô tả request lỗi và kỳ vọng status/body 422 tương ứng
D. Để consumer tự đoán body lỗi từ annotation controller
Đáp án đúng: C

Câu 38. Trong pipeline CI, thứ tự nào giúp phát hiện API breaking change trước khi phát hành?
A. Producer publish artifact rồi bỏ qua kiểm thử contract
B. Producer chạy generated tests rồi publish versioned stubs
C. Consumer đổi contract trong cache và bỏ bước test producer
D. Producer triển khai production trước rồi cập nhật stub từ log
Đáp án đúng: B

Câu 39. Consumer dùng một stub version mới chưa được kiểm trên producer; rủi ro chính là gì?
A. Stub có thể mô tả hành vi mà implementation chưa đáp ứng
B. Stub có thể tự mở các port khác với cấu hình CI
C. Stub có thể xóa version cũ trong repository Maven
D. Stub có thể tạo các database migration ngoài ý muốn
Đáp án đúng: A

Câu 40. Kết hợp provider contract tests và consumer stub tests mang lại bảo đảm nào?
A. Đánh giá trạng thái mạng và database production cùng lúc
B. Hai phía được kiểm theo cùng contract, nhưng vẫn cần test tích hợp
C. Đồng bộ thời điểm deploy hai dịch vụ khi release mới
D. Xác minh thay đổi chưa được mô tả trong contract hiện tại
Đáp án đúng: B
