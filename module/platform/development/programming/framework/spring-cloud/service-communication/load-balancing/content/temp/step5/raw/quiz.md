Câu 1. Spring Cloud LoadBalancer dùng service ID chủ yếu để thực hiện việc gì?
A. Chọn một ServiceInstance đích cho lời gọi của client
B. Đăng ký service ID mới vào mọi registry đang hoạt động
C. Đọc cấu hình môi trường từ Config Server cho client
D. Đảm bảo mọi request tới service đều trả HTTP 200
Đáp án đúng: A

Câu 2. DiscoveryClient và Spring Cloud LoadBalancer khác nhau chủ yếu ở đâu?
A. Discovery chọn client retry; LoadBalancer đăng ký instance
B. Discovery thực thi HTTP; LoadBalancer lưu cấu hình profile
C. Discovery cung cấp instance; LoadBalancer chọn đích gọi
D. Discovery cấp timeout; LoadBalancer quyết định trạng thái Pod
Đáp án đúng: C

Câu 3. DiscoveryClient.getInstances("orders") thường trả về dữ liệu gì?
A. Một RestClient đã cấu hình để gọi service orders
B. Các ServiceInstance đã biết của service orders
C. Kết quả HTTP của request cuối cùng đến orders
D. Một CircuitBreaker đang bảo vệ service orders
Đáp án đúng: B

Câu 4. Đối tượng ServiceInstance trong Spring Cloud thường chứa gì?
A. Danh sách request body mới nhất của service tương ứng
B. Số lần retry và bộ đếm timeout của từng HTTP client
C. Service ID, host, port, URI và thông tin metadata
D. Toàn bộ bean definition được tạo bởi service từ xa
Đáp án đúng: C

Câu 5. RoundRobinLoadBalancer chọn backend theo nguyên tắc nào?
A. Luân phiên lựa chọn trong tập instance ứng viên
B. Ưu tiên instance luôn có độ trễ trung bình thấp nhất
C. Chỉ chọn instance có tên trùng với profile đang chạy
D. Chọn cố định instance đầu tiên của registry mỗi lần
Đáp án đúng: A

Câu 6. Khi dùng RandomLoadBalancer, lựa chọn đích dựa trên điều gì?
A. Chọn theo thứ tự lần lượt của tên service ID
B. Chọn instance có bộ nhớ trống lớn nhất trên host
C. Chọn ngẫu nhiên từ các instance được cung cấp
D. Chọn instance có số lượng HTTP connection nhỏ nhất
Đáp án đúng: C

Câu 7. ServiceInstanceListSupplier đóng vai trò nào trong Spring Cloud LoadBalancer?
A. Thực thi request HTTP và chuyển đổi response của client
B. Cung cấp danh sách instance cho chính sách chọn đích
C. Lưu số lần retry của từng phương thức OpenFeign
D. Chuyển mọi kết quả discovery sang cấu hình ConfigMap
Đáp án đúng: B

Câu 8. Một lớp ServiceInstanceListSupplier dùng discovery thường lấy nguồn từ đâu?
A. Danh sách instance do DiscoveryClient tương ứng cung cấp
B. Danh sách endpoint viết sẵn trong mọi REST controller
C. Các URL timeout do HTTP client lưu trong cache
D. Các tên bean @Service đang có trong ApplicationContext
Đáp án đúng: A

Câu 9. Nếu danh sách instance được cache, rủi ro vận hành nào cần lưu ý?
A. Cache tự động làm mọi instance thành cùng một Pod
B. Cache buộc tất cả request bỏ qua cơ chế health check
C. Cache tự tăng tỷ lệ retry mỗi khi backend giảm tải
D. Địa chỉ backend trong cache có thể đã không còn hợp lệ
Đáp án đúng: D

Câu 10. Điều gì giúp giảm việc truy vấn discovery lặp lại nhưng vẫn kiểm soát dữ liệu cũ?
A. Dùng cache có TTL phù hợp tốc độ thay đổi backend
B. Giữ cache vĩnh viễn để tránh mọi request tới registry
C. Tắt mọi health check rồi chỉ tăng connect timeout
D. Lưu từng response HTTP vào danh sách ServiceInstance
Đáp án đúng: A

Câu 11. HealthCheckServiceInstanceListSupplier hướng tới mục tiêu nào?
A. Tạo một circuit breaker mới cho mỗi instance trong cache
B. Lọc instance ứng viên dựa trên kết quả health check
C. Thay thế HTTP client bằng Kubernetes readiness controller
D. Đăng ký thêm instance khi bộ nhớ của service tăng
Đáp án đúng: B

Câu 12. Vì sao instance vừa được health check thành công vẫn có thể lỗi ở lần gọi sau?
A. Health check cam kết trạng thái thành công suốt vòng đời
B. Sức khỏe có thể thay đổi giữa lúc check và request thật
C. Health check sẽ chuyển client sang kết nối không cần timeout
D. Health check tự rollback một request đã gửi tới server
Đáp án đúng: B

Câu 13. Khi thiết kế endpoint dùng cho health check instance, tiêu chí nào phù hợp?
A. Phản hồi nhanh, giới hạn tải và phản ánh khả năng phục vụ
B. Luôn quét toàn bộ database ở mỗi health check liên tục
C. Trả thông tin xác thực để client tự xác minh với registry
D. Đợi đủ các thao tác batch hoàn thành rồi mới trả HTTP
Đáp án đúng: A

Câu 14. Khi không có instance đủ điều kiện cho service ID, client cần xử lý thế nào?
A. Tự chuyển sang service ID bất kỳ còn hoạt động trong registry
B. Báo lỗi có kiểm soát hoặc dùng fallback theo nghiệp vụ
C. Tạo một ServiceInstance giả để đánh dấu request thành công
D. Bỏ mọi timeout để chờ vô hạn đến khi registry có Pod
Đáp án đúng: B

Câu 15. Muốn ưu tiên backend cùng zone, cần điều kiện nào ở chính sách cân bằng tải?
A. Chỉ khai logging.level cho các package client đã tạo
B. Chỉ cấu hình timeout vì zone tự gắn vào mọi request
C. Đặt zone thành tên HTTP method trong RestClient
D. Có metadata zone và supplier áp dụng chính sách ưu tiên
Đáp án đúng: D

Câu 16. Chọn instance theo trọng số (weight) thường hữu ích khi nào?
A. Khi muốn chia lưu lượng theo tỷ lệ không đồng đều
B. Khi mọi instance phải nhận đúng số request như nhau
C. Khi muốn đo latency mà không chọn backend thực tế
D. Khi client chỉ có đúng một instance cố định để gọi
Đáp án đúng: A

Câu 17. Vì sao không nên mặc định coi round-robin là sticky session theo người dùng?
A. Round-robin luân phiên, không giữ ánh xạ user vào một đích
B. Round-robin dùng cookie để chọn instance cố định theo phiên
C. Round-robin luôn lấy hash từ Authorization header để định tuyến
D. Round-robin tự phục hồi session state khi backend restart
Đáp án đúng: A

Câu 18. Spring Cloud LoadBalancer không thay thế cơ chế nào nhằm giới hạn số call đồng thời?
A. ServiceInstanceListSupplier dùng tạo danh sách ứng viên
B. Service discovery để cập nhật danh sách endpoint
C. Một chính sách chọn instance như round-robin
D. Bulkhead hoặc giới hạn concurrency của HTTP client
Đáp án đúng: D

Câu 19. Khi cần cấu hình cân bằng tải cho từng service ID riêng, thành phần nào liên quan?
A. EnvironmentChangeEvent tạo mới toàn bộ HTTP service trong registry
B. FeignContract lưu mặc định cấu hình retry toàn hệ thống
C. DiscoveryClient trực tiếp sửa mọi request interceptor
D. LoadBalancerClientFactory quản lý context cấu hình theo service
Đáp án đúng: D

Câu 20. Khi dùng RestClient, bean nào phù hợp để tự động chọn backend theo service ID?
A. RestClient.ResponseSpec có @RefreshScope ở mỗi lần gọi
B. RestClient.RequestBodySpec dùng @Qualifier đặt tên endpoint
C. RestClient.Builder được đánh dấu @LoadBalanced và cấu hình đủ
D. RestClient được gọi với URL IP cố định không dùng filter
Đáp án đúng: C

Câu 21. Với RestClient đã bật client-side load balancing, URL nào thường thể hiện service ID?
A. http://10.0.0.12/api/items với IP cố định của backend
B. https://api.example.com/items trỏ tới máy chủ được chọn
C. http://inventory/api/items với inventory là tên logic
D. http://localhost:8080/items trỏ thẳng tới app hiện hành
Đáp án đúng: C

Câu 22. Nếu RestClient.Builder không được tích hợp Spring Cloud LoadBalancer, chuyện gì dễ xảy ra khi gọi tên logic?
A. Client tự tìm tất cả instance từ DiscoveryClient theo tên
B. Tên service được xử lý như host thông thường qua DNS
C. RestClient luôn chạy round-robin ngay cả khi thiếu starter
D. Client sẽ mặc định tạo ServiceInstanceListSupplier động
Đáp án đúng: B

Câu 23. Đối với WebClient, cách cấu hình nào thường kích hoạt load balancing theo service ID?
A. Gắn @LoadBalanced trên từng DTO của HTTP response
B. Dùng WebClient.Builder được đánh dấu @LoadBalanced
C. Tạo WebClient với mọi URI là Pod IP đã được chọn sẵn
D. Đặt tên bean WebClient giống hệt tên discovery server
Đáp án đúng: B

Câu 24. Vì sao cần tránh gọi block() trong WebFlux event-loop khi dùng WebClient?
A. Block tự tắt mọi filter của WebClient khi có retry
B. Block biến response thành ServiceInstanceListSupplier mới
C. Block tự gọi health endpoint của instance trước request
D. Block giữ thread đang chạy và làm giảm xử lý đồng thời
Đáp án đúng: D

Câu 25. @FeignClient(name="catalog") khi không cấu hình URL trực tiếp thường có ý nghĩa gì?
A. Bắt buộc gọi cổng mặc định 8080 của localhost theo class name
B. Tạo Config Server tên catalog để giải quyết thuộc tính timeout
C. Dùng tên catalog làm service ID để tìm backend qua load balancing
D. Tự thêm một instance catalog vào registry khi client khởi động
Đáp án đúng: C

Câu 26. Nếu @FeignClient được đặt URL cụ thể, hiệu lực phổ biến đối với load balancing theo tên là gì?
A. Client hướng đến URL đó thay vì chọn instance qua service ID
B. Client chuyển mọi request qua discovery dù URL đã cố định
C. Client tự phân phối request cho mọi host có cùng DNS suffix
D. Client dùng URL chỉ để xác định profile của OpenFeign
Đáp án đúng: A

Câu 27. Connect timeout trên HTTP client chủ yếu ràng buộc giai đoạn nào?
A. Tổng thời gian retry của mọi attempt sau khi có response
B. Khoảng chờ giữa các lần lấy danh sách từ discovery
C. Thời gian service tự làm mới instance cache định kỳ
D. Thời gian thiết lập kết nối tới backend được chọn
Đáp án đúng: D

Câu 28. Read timeout trên HTTP client thường nhắm vào điều gì?
A. Thời gian phân giải các bean có @LoadBalanced khi startup
B. Thời gian chờ nhận dữ liệu phản hồi từ backend
C. Thời gian chạy health check của DiscoveryClient
D. Thời gian còn lại của một ServiceInstance trong registry
Đáp án đúng: B

Câu 29. Tại sao có load balancer rồi vẫn phải cấu hình timeout riêng?
A. LoadBalancer tự đóng socket khi mọi request quá một giây
B. DiscoveryClient tự đặt timeout tối ưu cho từng HTTP method
C. Round-robin đồng nghĩa không có request nào bị treo
D. Chọn backend không giới hạn được thời gian chờ response
Đáp án đúng: D

Câu 30. Khi bật retry cho giao tiếp giữa các service, cách cấu hình nào ít rủi ro?
A. Lặp lại vô hạn để bảo đảm request được phục vụ khi backend lỗi
B. Tắt timeout để request retry hoàn tất trước khi client hủy
C. Giới hạn số attempt, timeout và backoff theo ngân sách gọi
D. Tăng song song mọi retry để giảm độ trễ bằng mọi giá
Đáp án đúng: C

Câu 31. Vì sao cần kiểm soát retry cho HTTP POST tạo đơn hàng?
A. Mọi HTTP POST mặc định được server rollback nếu client lỗi
B. Lần gọi trước có thể đã ghi thành công dù client timeout
C. LoadBalancer tự đánh dấu request tạo đơn là idempotent
D. Retry tự sinh khóa idempotency tương ứng với order ID
Đáp án đúng: B

Câu 32. Khi muốn thử một instance khác sau lỗi phù hợp, cơ chế nào cần được xem xét?
A. Cấu hình retry và chính sách thử instance kế tiếp phù hợp
B. Giữ cố định IP ban đầu rồi chỉ tăng connect timeout
C. Buộc discovery loại instance cũ vĩnh viễn ngay sau một lỗi
D. Tắt ServiceInstanceListSupplier ở lần retry thứ hai
Đáp án đúng: A

Câu 33. Điểm cần lưu ý khi ghép retry với load balancer là gì?
A. Retry làm các lời gọi thất bại trở thành health check
B. Retry luôn dùng một instance mới mà không cần cấu hình
C. LoadBalancer sẽ giới hạn tổng thời gian retry thay client
D. Lỗi từ từng attempt có thể khuếch đại tải backend
Đáp án đúng: D

Câu 34. Khi backend phản hồi HTTP 429 kèm Retry-After, hành vi nào nên cân nhắc?
A. Thử liên tục ngay lập tức vì 429 chỉ là lỗi DNS
B. Chuyển mọi request sau đó sang instance đầu danh sách
C. Tôn trọng Retry-After và retry có giới hạn khi an toàn
D. Xóa toàn bộ cache discovery để bắt backend nhận tải
Đáp án đúng: C

Câu 35. Nếu discovery trả danh sách rỗng, fallback tốt nên tuân thủ nguyên tắc nào?
A. Trả dữ liệu thành công giả cho mọi thao tác ghi quan trọng
B. Gọi lại liên tục service chưa có instance trong registry
C. Tự chọn bất kỳ service có metadata tương tự để gọi
D. Trả kết quả thay thế có ý nghĩa và không che lỗi nghiệp vụ
Đáp án đúng: D

Câu 36. Vì sao registry có thể cung cấp instance không còn sẵn sàng?
A. Danh sách service ID mặc định không bao gồm instance mới
B. Mọi instance luôn được xác minh bằng giao dịch nghiệp vụ
C. Chỉ metadata zone mới được phép dùng để loại backend
D. Cập nhật discovery có độ trễ so với trạng thái backend thật
Đáp án đúng: D

Câu 37. Khi dùng Kubernetes Service DNS ổn định, có nhất thiết phải cài client-side discovery không?
A. Có; Kubernetes Service DNS luôn cần DiscoveryClient hỗ trợ
B. Có; ClusterIP không thể truy cập nếu thiếu RestClient filter
C. Không; chỉ cần thêm khi có yêu cầu định tuyến phía client
D. Không; vì load balancing chỉ hoạt động qua OpenFeign
Đáp án đúng: C

Câu 38. Để kiểm tra logic chọn backend mà không chạy registry thật, nên làm gì?
A. Bắt buộc dựng Eureka cluster và tất cả backend trong unit test
B. Chỉ assert @LoadBalanced tồn tại mà không xem instance chọn
C. Mock HTTP response nhưng không tạo danh sách instance đầu vào
D. Dùng ServiceInstanceListSupplier giả lập với tập instance xác định
Đáp án đúng: D

Câu 39. Kiểm thử trường hợp hết instance nên xác nhận điều gì?
A. Lời gọi thất bại có kiểm soát hoặc trả fallback đúng quy định
B. Client tự kết nối đến bất kỳ instance khác tên đang sẵn sàng
C. LoadBalancer tự tạo bản ghi ServiceInstance với host rỗng
D. HTTP client im lặng hoàn tất thành công dù chưa gọi backend
Đáp án đúng: A

Câu 40. Để đánh giá chính sách health check trong test, kịch bản nào phù hợp?
A. Một backend có CPU cao vẫn bắt buộc được chọn đầu tiên
B. Một backend lỗi health và không được chọn khi bộ lọc cập nhật
C. Một backend thiếu endpoint nhưng tự được đánh dấu healthy
D. Một backend vừa xuất hiện luôn bị cấm gọi tới khi restart
Đáp án đúng: B

Câu 41. Nhãn metric nào thường an toàn về cardinality cho load balancing?
A. Request ID duy nhất của mỗi lần gọi client tới backend
B. Access token được gắn vào từng HTTP request header
C. Service ID và loại kết quả với tập giá trị hữu hạn
D. Timestamp mili giây dùng đặt tên instance trong timer
Đáp án đúng: C

Câu 42. Để điều tra lỗi theo nhiều service, thông tin nào nên được truyền qua HTTP?
A. Tên bean Spring đang xử lý request trong client
B. Trace context chuẩn để nối span giữa các dịch vụ
C. Số counter Prometheus đang được scrape tại thời điểm gọi
D. Metadata cache của toàn bộ ServiceInstanceListSupplier
Đáp án đúng: B

Câu 43. Khi log một request thất bại do không chọn được backend, nên lưu gì?
A. Service ID, loại lỗi và correlation ID không chứa secret
B. Toàn bộ Authorization header và access token để debug
C. Danh sách đầy đủ Secret từ Config Server đang hoạt động
D. Cookie session thô và request body cho mọi lần thất bại
Đáp án đúng: A

Câu 44. Load balancing giúp tránh tập trung lưu lượng, nhưng không thay thế gì khi backend bị lỗi dây chuyền?
A. Circuit breaker và giới hạn tài nguyên ở đường gọi phụ thuộc
B. ServiceInstanceListSupplier cấp ứng viên theo discovery
C. Chính sách round-robin cho các service có nhiều instance
D. Cơ chế ánh xạ service ID tới instance từ registry
Đáp án đúng: A

Câu 45. Khi áp dụng chính sách weight, cần kiểm chứng điều gì sau khi triển khai?
A. Mọi request phải luôn đi tới một backend duy nhất đã chọn
B. Phân bố request theo trọng số và tỷ lệ lỗi của từng backend
C. Cache discovery phải bị tắt để nhận đúng trọng số theo chu kỳ
D. Trọng số thay thế hoàn toàn mọi quy tắc timeout hoặc retry
Đáp án đúng: B

Câu 46. Nếu bật caching của instance list, hướng giám sát nào hữu ích?
A. Chỉ đo heap của JVM mà không kiểm tra backend thực tế
B. Chỉ đếm số class thuộc package LoadBalancer ở startup
C. Chỉ kiểm tra số phiên bản Config Server đang kết nối
D. Theo dõi độ trễ cập nhật backend và tỷ lệ chọn instance lỗi
Đáp án đúng: D

Câu 47. Trong rollout nhiều replica, xác nhận nào cho thấy giao tiếp ổn định hơn?
A. Mọi Pod mới nhận bằng nhau ngay cả khi chưa readiness
B. Mọi client giữ nguyên một IP cho tới khi rollout kết thúc
C. Traffic tới backend sẵn sàng, lỗi và độ trễ trong ngưỡng
D. Tất cả request bị retry ít nhất một lần trước khi thành công
Đáp án đúng: C

Câu 48. Cân bằng tải phía client khác reverse proxy phía server ở điểm cốt lõi nào?
A. Registry tự thực thi HTTP request thay cho HTTP client
B. Proxy thay đổi profile Spring khi backend tăng replica
C. Client chọn instance đích trước khi gửi request tới backend
D. Client phải tạo một service ID mới cho mọi lần kết nối
Đáp án đúng: C
