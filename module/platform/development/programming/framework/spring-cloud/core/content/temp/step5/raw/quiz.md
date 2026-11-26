Câu 1. Spring Cloud release train BOM chủ yếu giúp giải quyết việc gì khi thêm nhiều module Cloud?
A. Tự khóa phiên bản Spring Boot và Java cho cả ứng dụng
B. Tự thêm toàn bộ Spring Cloud starter vào classpath
C. Quản lý các phiên bản module Spring Cloud tương thích
D. Thay Spring Boot dependency management khi build Maven
Đáp án đúng: C

Câu 2. Vì sao phải kiểm tra Spring Cloud release train với phiên bản Spring Boot hiện tại?
A. Train phải tương thích với phiên bản Spring Boot đang dùng
B. Mọi release train sẽ tự nâng phiên bản Boot trong dự án
C. Chỉ phiên bản Boot mới nhất mới kết nối được Config Server
D. Tương thích Cloud phụ thuộc duy nhất vào cấu hình profile
Đáp án đúng: A

Câu 3. Điểm khác biệt giữa nhập Spring Cloud BOM và thêm một starter là gì?
A. BOM chỉ quản lý bean; starter chỉ bổ sung repository
B. BOM quản lý version; starter bổ sung dependency khi build
C. BOM tự kích hoạt discovery; starter chỉ quản lý phiên bản
D. BOM chỉ dùng khi chạy; starter chỉ dùng trong kiểm thử
Đáp án đúng: B

Câu 4. Spring Cloud Commons cung cấp giá trị chính nào cho các thành phần Cloud?
A. Thực thi Config Server mặc định cho mọi ứng dụng Spring Boot
B. Tự triển khai một registry phân tán cho từng ApplicationContext
C. Thay IoC container của Spring Framework bằng container riêng
D. Cung cấp abstraction chung về discovery và load balancing
Đáp án đúng: D

Câu 5. Spring Cloud Context chủ yếu bổ sung khả năng gì cho hệ thống phân tán?
A. Thực hiện truy vấn registry thay cho DiscoveryClient
B. Tự đổi HTTP client sang giao thức gRPC khi startup
C. Lưu metadata của tất cả service instance vào database
D. Quản lý bối cảnh cấu hình và cơ chế refresh runtime
Đáp án đúng: D

Câu 6. Spring Cloud compatibility verifier hữu ích ở tình huống nào?
A. Phát hiện cặp phiên bản Spring Boot và Cloud không hỗ trợ
B. Đo khả năng chịu tải của backend qua LoadBalancerClient
C. Kiểm tra Config Server trả các property hợp lệ về kiểu
D. Kiểm tra service instance có đủ CPU và memory lúc chạy
Đáp án đúng: A

Câu 7. Sau khi nâng Spring Cloud release train, cách đánh giá tương thích nào hợp lý?
A. Chỉ so sánh số module Maven trước và sau lần nâng cấp
B. Kiểm thử startup, auto-config và giao tiếp service
C. Chỉ đổi tên artifact và xem version hiển thị khi build
D. Chỉ kiểm tra dữ liệu của một profile trong Config Server
Đáp án đúng: B

Câu 8. Khi kết hợp Spring Boot BOM với Spring Cloud BOM, nên xử lý phiên bản thế nào?
A. Buộc tất cả thư viện Spring Framework dùng bản mới nhất
B. Loại dependency management của Boot khi đã có Cloud BOM
C. Chọn hai BOM tương thích, tránh override version tùy ý
D. Trộn module từ các Cloud train khác nhau theo từng starter
Đáp án đúng: C

Câu 9. Một tính năng Spring Cloud thường tự kích hoạt khi có dependency phù hợp nhờ cơ chế nào?
A. Classloader tự tải module chưa khai báo khi chạy
B. Config Server tự phát sinh bean cho thư viện còn thiếu
C. DiscoveryClient tự quét class @Configuration của JAR
D. Auto-configuration dựa trên classpath và bean hiện có
Đáp án đúng: D

Câu 10. Đối với Spring Cloud Config Client dùng Config Data API, khai báo nguồn nào phù hợp?
A. Đặt spring.config.import thành configserver: cùng địa chỉ nguồn
B. Chỉ đặt spring.cloud.config.enabled mà không khai báo import
C. Thay spring.config.import bằng tên bean DiscoveryClient
D. Khai spring.profiles.active bằng địa chỉ HTTP Config Server
Đáp án đúng: A

Câu 11. Trong spring.config.import, tiền tố optional:configserver: có ý nghĩa gì?
A. Có thể tiếp tục startup nếu nguồn config không khả dụng
B. Buộc client đợi Config Server thành công rồi mới startup
C. Luôn bỏ qua remote config ngay cả khi server hoạt động
D. Cho phép tải mọi config mà không xác thực tới server
Đáp án đúng: A

Câu 12. Với ứng dụng dùng Config Data API, nhận định nào về bootstrap.yml là đúng?
A. bootstrap.yml là cách duy nhất để tải mọi remote property
B. File bootstrap.yml luôn có ưu tiên cao hơn command-line
C. Config import chỉ hoạt động khi đã bật bootstrap context
D. bootstrap.yml không bắt buộc khi dùng config import
Đáp án đúng: D

Câu 13. spring.application.name thường giúp Config Client thực hiện điều gì?
A. Quyết định @RefreshScope bean nào được tạo ở lần đầu
B. Định danh ứng dụng khi chọn bộ cấu hình từ nguồn ngoài
C. Xác định port cho mọi ServiceInstance cùng tên
D. Bắt buộc đặt tên cho tất cả bean trong context
Đáp án đúng: B

Câu 14. Khi Spring Cloud Config Client sử dụng profile staging, kết quả thường là gì?
A. Tự thay package root của ứng dụng thành staging
B. Tự đăng ký một registry instance mới cho profile
C. Bỏ mọi property chung của ứng dụng khi bật profile
D. Nhận cấu hình ứng dụng tương ứng với profile staging
Đáp án đúng: D

Câu 15. Nếu có một property tại nhiều PropertySource, giá trị nào thường được chọn?
A. Theo file có thời gian sửa gần nhất bất kể nguồn
B. Theo bean truy cập property trước tiên khi khởi động
C. Theo số lượng service instance đã đăng ký vào registry
D. Theo thứ tự ưu tiên PropertySource trong Environment
Đáp án đúng: D

Câu 16. Nếu Config Server không khả dụng và nguồn được khai báo là bắt buộc, điều gì có thể xảy ra?
A. Client chuyển sang bootstrap mà không cần khai báo
B. Client tự tạo bản sao Config Server ở cổng mặc định
C. Có thể startup lỗi khi thiếu remote config bắt buộc
D. DiscoveryClient tự trả bộ property của backend
Đáp án đúng: C

Câu 17. @RefreshScope thường có tác dụng gì đối với một bean đọc external properties?
A. Tự sửa giá trị của mọi biến static không cần proxy
B. Cho phép hủy target đã cache và tạo lại sau refresh
C. Khởi tạo một ApplicationContext mới ở mỗi HTTP request
D. Lập lịch poll Config Server dù chưa cấu hình sự kiện
Đáp án đúng: B

Câu 18. Khi mở Actuator refresh endpoint, biện pháp vận hành nào cần áp dụng?
A. Mở endpoint công khai để các service tự gọi refresh
B. Dùng endpoint này thay thế cơ chế lưu secret server
C. Giới hạn exposure và xác thực quyền thay đổi cấu hình
D. Cho endpoint chạy với quyền admin không cần audit
Đáp án đúng: C

Câu 19. Một @RefreshScope bean thường được truy cập thông qua thành phần nào?
A. ThreadLocal giữ target bean theo từng HTTP request
B. ServiceRegistry thay thế bean definition khi lookup
C. Proxy quản lý target bean có thể tạo lại khi refresh
D. Một prototype được tạo mới khi mọi lần ghi log
Đáp án đúng: C

Câu 20. Tại sao một @Value đã inject vào singleton không tự đổi sau khi sửa file cấu hình?
A. Spring Cloud tự bỏ mọi PropertySource sau khi startup
B. Singleton không tự inject lại property sau sửa file
C. Giá trị annotation @Value chỉ đọc được lúc compile
D. Config Client không cho phép thay đổi file bên ngoài
Đáp án đúng: B

Câu 21. EnvironmentChangeEvent trong Spring Cloud Context liên quan tới chức năng nào?
A. Tạo một ServiceInstance mới khi registry thiếu service
B. Đóng ApplicationContext sau mọi thay đổi profile
C. Thông báo các key cấu hình thay đổi cho listener
D. Đặt lại trạng thái circuit breaker của mọi dependency
Đáp án đúng: C

Câu 22. Sau khi refresh invalidates target của @RefreshScope, target mới thường có lúc nào?
A. Khi kết thúc mọi HTTP request đang chờ trong server
B. Khi registry đã xác nhận từng instance được restart
C. Khi JVM tạo classloader mới cho phiên bản ứng dụng
D. Target mới được tạo lúc proxy cần dùng lại bean
Đáp án đúng: D

Câu 23. Vì sao không nên xem refresh là tương đương với restart toàn bộ ứng dụng?
A. Refresh luôn dựng lại toàn bộ ApplicationContext của tiến trình
B. Một số tài nguyên và giá trị lúc khởi tạo có thể không đổi
C. Refresh tự nạp lại classpath và mọi dependency đã nâng
D. Refresh bắt buộc đóng database của các replica khác
Đáp án đúng: B

Câu 24. Cần chẩn đoán giá trị property có hiệu lực, bước nào hữu ích?
A. Chỉ xem số instance trả về từ DiscoveryClient hiện tại
B. Ghi toàn bộ property nhạy cảm vào log để đối chiếu
C. Đổi tên các bean để buộc Environment đọc lại file
D. Kiểm tra Environment và ưu tiên, che dữ liệu nhạy cảm
Đáp án đúng: D

Câu 25. DiscoveryClient.getInstances("billing") thường cung cấp kết quả nào?
A. Danh sách ServiceInstance của service ID billing
B. Danh sách property nguồn ngoài của ứng dụng billing
C. Danh sách request vừa qua của HTTP gateway billing
D. Danh sách breaker transition của dependency billing
Đáp án đúng: A

Câu 26. DiscoveryClient.getServices() thường trả dữ liệu nào?
A. Các service ID đã biết qua hệ thống discovery
B. Danh sách bean @Service trong context cục bộ
C. Danh sách ứng dụng đang bật profile production
D. Danh sách release train đã cài trong JVM
Đáp án đúng: A

Câu 27. Một ServiceInstance của Spring Cloud Commons thường mang thông tin gì?
A. Tên config profile, timeout và mật khẩu Config Server
B. Service ID, host, port, URI và metadata của instance
C. Tên circuit breaker, số failure và trạng thái OPEN
D. Định nghĩa bean, scope và vòng đời trong context
Đáp án đúng: B

Câu 28. ReactiveDiscoveryClient khác DiscoveryClient thường ở khía cạnh nào?
A. Tự lưu cache vào Redis mỗi khi registry thay đổi
B. Chỉ hỗ trợ instance cấu hình thủ công trong YAML
C. Luôn trả về RestTemplate đã gắn @LoadBalanced
D. Truy vấn instance bằng reactive publisher
Đáp án đúng: D

Câu 29. CompositeDiscoveryClient dùng khi nào là hợp lý?
A. Tạo Config Server dự phòng cho mọi profile của app
B. Buộc mỗi service chỉ có một instance được đăng ký
C. Kết hợp nhiều DiscoveryClient theo thứ tự cấu hình
D. Thay discovery bằng round-robin không cần registry
Đáp án đúng: C

Câu 30. ServiceRegistry abstraction phục vụ thao tác nào?
A. Chọn request nào sẽ được chuyển sang HTTP fallback
B. Đọc property value từ Config Server theo profile
C. Đăng ký và hủy đăng ký instance qua Registration
D. Phân tích trace để chọn instance có latency thấp
Đáp án đúng: C

Câu 31. Registration trong Spring Cloud Commons biểu thị điều gì?
A. Phiên bản BOM đang được dùng ở mỗi module Maven
B. Một cấu hình refresh scope áp dụng cho mọi bean
C. Một phiên gọi HTTP được giữ trong load balancer
D. Registration mô tả instance để đăng ký với registry
Đáp án đúng: D

Câu 32. Với discovery client implementation có auto-configuration, @EnableDiscoveryClient thường thế nào?
A. Bắt buộc có trên mọi method HTTP trong controller
B. Có thể không cần annotation để kích hoạt discovery
C. Phải đặt trên tất cả ServiceInstance class được tạo
D. Cần thay thế BeanFactory bằng DiscoveryClientFactory
Đáp án đúng: B

Câu 33. SimpleDiscoveryClient thường phù hợp với lựa chọn nào?
A. Danh sách instance tĩnh được khai báo qua properties
B. Service registry động có leader election tích hợp
C. Registry phân tán tự đăng ký khi node chuyển mạng
D. Service discovery dựa duy nhất trên HTTP access log
Đáp án đúng: A

Câu 34. Vì sao vẫn cần timeout khi DiscoveryClient trả về một instance?
A. getInstances() tự chạy transaction business để test
B. ServiceInstance bảo đảm HTTP response sẽ luôn thành công
C. Registry có thể stale nên vẫn cần timeout và health check
D. Client-side load balancing tự thay thế mọi TCP timeout
Đáp án đúng: C

Câu 35. Spring Cloud LoadBalancer thường chọn backend dựa trên thông tin nào?
A. Tên configuration class của từng HTTP controller
B. Phiên bản release train mà Config Server cung cấp
C. Danh sách property đang bị thay đổi bởi refresh
D. Service ID và danh sách instance có thể sử dụng
Đáp án đúng: D

Câu 36. Với RestTemplate gọi URL dạng http://billing, giải pháp nào hỗ trợ cân bằng tải client-side?
A. Chỉ đặt @Profile("billing") trên RestTemplate bean
B. Dùng @LoadBalanced RestTemplate và LoadBalancer
C. Chỉ tạo bean @RefreshScope cho từng HTTP request
D. Gắn tên service vào Basic Auth credentials
Đáp án đúng: B

Câu 37. Với WebClient gọi URI theo service ID, cách chuẩn bị nào phù hợp?
A. Tạo WebClient.Builder có @LoadBalanced và hạ tầng cần thiết
B. Đánh dấu @LoadBalanced lên mọi String chứa URL service
C. Bật application profile reactive sẽ tự chọn instance
D. Gắn @EnableDiscoveryClient vào từng method của WebClient
Đáp án đúng: A

Câu 38. LoadBalancerClient.choose("inventory") chủ yếu nhận kết quả nào?
A. Environment của ứng dụng đang chứa profile inventory
B. CircuitBreaker theo nhóm dependency tên inventory
C. Trả ServiceInstance đã chọn cho service inventory
D. ApplicationContext của remote inventory instance
Đáp án đúng: C

Câu 39. Discovery và load balancing khác nhau chủ yếu thế nào?
A. Discovery tìm instance; load balancing chọn nơi gửi request
B. Discovery phát request; load balancing đồng bộ Config Server
C. Discovery chỉ lấy metrics; load balancing cập nhật profile
D. Discovery chọn trace; load balancing thay circuit breaker
Đáp án đúng: A

Câu 40. Khi không có instance cho service ID cần gọi, ứng dụng nên làm gì?
A. Xử lý lỗi có kiểm soát hoặc dùng fallback phù hợp
B. Chọn một service ID bất kỳ còn trong registry
C. Tạo một ServiceInstance trống và báo thành công
D. Vô hiệu timeout để request chờ registry vô hạn
Đáp án đúng: A

Câu 41. spring.application.name có vai trò nào đối với hệ thống dịch vụ?
A. Luôn là host thực được LoadBalancerClient lựa chọn
B. Đặt tên logic cho ứng dụng trong config và discovery
C. Luôn là URL Config Server mà mọi replica truy cập
D. Buộc mỗi instance dùng cùng cổng và instance ID
Đáp án đúng: B

Câu 42. Vì sao service load balancing vẫn cần timeout và retry được kiểm soát?
A. LoadBalancer sẽ tự replay mọi request lỗi network
B. Chọn endpoint không bảo đảm lời gọi phản hồi đúng hạn
C. Một ServiceInstance luôn có trạng thái healthy chính xác
D. DiscoveryClient tự sinh retry policy cho mọi HTTP client
Đáp án đúng: B

Câu 43. Khi retry một lệnh ghi qua service client, yếu tố nào quan trọng?
A. Dùng request ID mới ở mỗi retry để tránh ghi trùng
B. Bỏ timeouts vì retry có thể đợi vô hạn để an toàn
C. Giữ breaker luôn CLOSED khi có một retry thành công
D. Giới hạn retry và giữ idempotency cho tác vụ ghi
Đáp án đúng: D

Câu 44. Khi kiểm thử logic chọn instance mà không chạy registry thật, nên chọn cách nào?
A. Bắt buộc truy cập registry production cho unit test
B. Chỉ mock Config Server và bỏ danh sách instance
C. Mock DiscoveryClient hoặc supplier trong kiểm thử
D. Chỉ kiểm tra annotation @LoadBalanced không gọi thử
Đáp án đúng: C

Câu 45. Để kiểm thử @RefreshScope nhận cấu hình mới, assertion nào có ý nghĩa?
A. Đổi property, refresh rồi đọc bean đã tạo mới
B. Chỉ xác minh file YAML có đúng tên profile cần dùng
C. Chỉ khởi tạo thêm RestTemplate không gọi vào endpoint
D. Chỉ đo số lượng ServiceInstance trong registry
Đáp án đúng: A

Câu 46. Khi health indicator của discovery báo UP, nên diễn giải thế nào?
A. Mọi service đã đăng ký chắc chắn trả HTTP 200
B. Mọi request sẽ không cần timeout hoặc fallback
C. UP chỉ phản ánh discovery, không đảm bảo backend khỏe
D. Service registry sẽ tự sửa toàn bộ instance lỗi
Đáp án đúng: C

Câu 47. Trong metric của load balancer, lựa chọn tag nào giúp tránh cardinality cao?
A. URL kèm orderId để mỗi lần gọi có nhãn duy nhất
B. Dùng service ID ổn định, tránh request ID hoặc token
C. Email tài khoản để phân tích lưu lượng từng khách
D. API key thật để xác định nguồn metric theo người dùng
Đáp án đúng: B

Câu 48. ServiceInstance metadata có thể hỗ trợ trường hợp nào khi chọn backend?
A. Cấp metadata instance cho chính sách chọn backend
B. Tự đồng bộ mọi refresh property sang các instance
C. Thay thế SSL certificate của client khi bị thu hồi
D. Xóa yêu cầu phân quyền khi routing theo service ID
Đáp án đúng: A
