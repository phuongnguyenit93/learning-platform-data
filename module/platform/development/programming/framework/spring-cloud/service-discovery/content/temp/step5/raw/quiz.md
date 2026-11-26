Câu 1. Service discovery trong Spring Cloud chủ yếu giải quyết bài toán nào?
A. Tạo API gateway mới mỗi khi service thay đổi số replica.
B. Chia transaction giữa các service bằng một registry chung.
C. Tra cứu instance theo tên service thay vì cố định host và port.
D. Lưu địa chỉ service trong cấu hình của từng consumer lúc build.
Đáp án đúng: C

Câu 2. Khi đăng ký Spring Boot service vào registry, service ID mặc định thường lấy từ đâu?
A. Giá trị `spring.profiles.active` tại lúc instance start.
B. Giá trị `management.server.port` của actuator service.
C. Dùng `spring.application.name` của ứng dụng.
D. Giá trị `server.servlet.context-path` của HTTP service.
Đáp án đúng: C

Câu 3. Lời gọi `DiscoveryClient.getInstances("catalog")` thường trả về gì?
A. Một HTTP client được tạo sẵn để gọi service `catalog`.
B. Địa chỉ IP của registry node đang giữ bản ghi `catalog`.
C. Một `Registration` để thêm service ID `catalog` vào registry.
D. Danh sách `ServiceInstance` thuộc service ID `catalog`.
Đáp án đúng: D

Câu 4. Muốn tạo địa chỉ gọi từ một `ServiceInstance`, phương thức nào phù hợp?
A. Dùng `getUri()` để lấy URI do instance cung cấp.
B. Dùng `getServiceId()` để lấy URI đầy đủ của instance.
C. Dùng `getInstanceId()` để đọc hostname và HTTP scheme.
D. Dùng `getMetadata()` để lấy URL gốc từ tên service.
Đáp án đúng: A

Câu 5. Metadata của `ServiceInstance` nên được sử dụng cho mục đích nào?
A. Thay TLS certificate trong kết nối của từng HTTP client.
B. Thay thế token xác thực cho lời gọi giữa hai service.
C. Mang thuộc tính như zone hoặc version để hỗ trợ chọn node.
D. Dùng metadata để registry loại node lỗi trước khi client gọi.
Đáp án đúng: C

Câu 6. Phân biệt `DiscoveryClient` với `ServiceRegistry` trong Spring Cloud thế nào?
A. DiscoveryClient quản lý transaction; ServiceRegistry cân tải.
B. DiscoveryClient tra cứu; ServiceRegistry đăng ký instance.
C. DiscoveryClient tạo DNS; ServiceRegistry định tuyến HTTP.
D. DiscoveryClient tạo bản ghi; ServiceRegistry tra URI đích.
Đáp án đúng: B

Câu 7. Muốn dùng Eureka client với Spring Cloud, dependency starter nào phù hợp?
A. `spring-cloud-starter-netflix-eureka-server` trong consumer.
B. `spring-cloud-starter-consul-discovery` cho ứng dụng.
C. `spring-cloud-starter-loadbalancer` thay toàn bộ Eureka client.
D. `spring-cloud-starter-netflix-eureka-client` cho ứng dụng.
Đáp án đúng: D

Câu 8. Cấu hình nào chỉ định nơi Eureka client kết nối đến registry?
A. Đặt `spring.cloud.loadbalancer.ribbon.enabled`.
B. Đặt `eureka.instance.instance-id` thành registry URL.
C. Đặt `spring.cloud.discovery.client.simple.instances`.
D. Đặt `eureka.client.service-url.defaultZone` phù hợp.
Đáp án đúng: D

Câu 9. Hai replica cùng tên service trên Eureka cần tránh trùng thông tin nào?
A. Dùng Git branch riêng để registry biết mỗi replica khác nhau.
B. Dùng một HTTP port cố định cho tất cả replica trên một host.
C. Dùng instance ID riêng để Eureka phân biệt từng replica.
D. Dùng service ID riêng cho từng replica trong cùng ứng dụng.
Đáp án đúng: C

Câu 10. Khi `eureka.client.register-with-eureka=false`, điều nào đúng?
A. Client tắt endpoint HTTP của ứng dụng đang chạy.
B. Client không tự đăng ký nhưng vẫn có thể tải registry.
C. Client đổi trạng thái các instance sang OUT_OF_SERVICE.
D. Client ngừng tải registry nhưng vẫn tự đăng ký instance.
Đáp án đúng: B

Câu 11. Khi `eureka.client.fetch-registry=false`, tác động trực tiếp là gì?
A. Client dừng heartbeat dù vẫn được cấu hình đăng ký service.
B. Client không tải danh sách registry nhưng vẫn có thể đăng ký.
C. Client xóa bản ghi các replica khác khỏi Eureka server.
D. Client chọn instance cùng vùng dù không cấu hình cân tải.
Đáp án đúng: B

Câu 12. Heartbeat của Eureka client khi đã đăng ký chủ yếu nhằm việc gì?
A. Gia hạn lease để registry nhận biết instance còn hiện diện.
B. Gửi trạng thái transaction đang mở ở database về Eureka.
C. Cập nhật version JAR của ứng dụng trên từng lần heartbeat.
D. Cập nhật Git label của Config Server mỗi khi registry đổi.
Đáp án đúng: A

Câu 13. Khi Eureka self-preservation bật lúc mạng có vấn đề, hệ quả nào cần lưu ý?
A. Eureka tăng số replica ứng dụng để khắc phục lỗi mạng.
B. Client đổi IP của các instance để thay cho bản ghi stale.
C. Instance stale có thể được giữ lâu vì eviction bị hạn chế.
D. Registry loại instance thiếu heartbeat sau lần kiểm tra đầu.
Đáp án đúng: C

Câu 14. Client dùng registry cache chưa cập nhật sau khi một node chết có thể gặp gì?
A. HTTP request được server chuyển thành một heartbeat Eureka.
B. Cache stale có thể trỏ tới node đã ngừng phục vụ.
C. Registry cache làm toàn bộ node còn lại ngừng phục vụ HTTP.
D. Client restart node lỗi khi phát hiện cache không còn mới.
Đáp án đúng: B

Câu 15. Khi shutdown có kế hoạch, cách nào giúp giảm request mới tới instance?
A. Giữ readiness UP đến sau khi HTTP server đã đóng socket.
B. Tăng Eureka lease timeout để client có thêm thời gian gọi.
C. Ngừng nhận traffic và deregister trước khi dừng tiến trình.
D. Đợi hết phiên người dùng rồi giữ instance UP trên registry.
Đáp án đúng: C

Câu 16. Trong Spring Cloud Consul Discovery, service được đăng ký với thành phần nào?
A. Config Server Git backend thông qua môi trường bootstrap.
B. Spring Cloud Gateway route repository thông qua WebFlux.
C. Eureka peer replication thông qua Netflix service client.
D. Consul agent hoặc Consul API thông qua discovery integration.
Đáp án đúng: D

Câu 17. Consul HTTP health check cho Spring Boot có Actuator thường dùng đường dẫn nào?
A. `/actuator/beans` để đo số lượng bean trong service.
B. `/actuator/metrics` vì nó chứa tất cả trạng thái health.
C. `/actuator/mappings` để kiểm tra controller có hoạt động.
D. `/actuator/health` khi health endpoint được cấu hình phù hợp.
Đáp án đúng: D

Câu 18. Khi tra cứu Consul bằng health query chỉ lấy passing service, node critical sẽ ra sao?
A. Node bị loại khi người dùng gọi actuator refresh.
B. Được đổi thành service ID khác rồi gửi tới consumer.
C. Không xuất hiện trong tập instance passing được trả về.
D. Vẫn được chọn vì HTTP health check không liên quan registry.
Đáp án đúng: C

Câu 19. Consul TTL health check cần thao tác gì để duy trì trạng thái passing?
A. Đặt instance vào maintenance mode theo định kỳ.
B. Dựa vào HTTP keep-alive mà không cập nhật TTL check.
C. Gửi tín hiệu heartbeat cho TTL check trước khi hết hạn.
D. Reset metric counter để Consul biết ứng dụng còn chạy.
Đáp án đúng: C

Câu 20. Khi cấp Consul ACL token cho ứng dụng, nguyên tắc nào phù hợp?
A. Giới hạn quyền đọc/ghi service theo nhu cầu của workload.
B. Giấu hostname Consul để thay cho kiểm tra quyền registry.
C. Để token trong endpoint metadata để client khác sử dụng.
D. Cấp ACL token quản trị datacenter cho ứng dụng.
Đáp án đúng: A

Câu 21. Trong triển khai microservice, readiness khác liveness ở điểm quan trọng nào?
A. Readiness phản ánh khả năng nhận request mới của instance.
B. Readiness kiểm tra tiến trình còn tồn tại trên hệ điều hành.
C. Liveness thay thế được cơ chế cân tải giữa các service.
D. Liveness đo kết nối tới các DB và không xét tiến trình.
Đáp án đúng: A

Câu 22. Với `@LoadBalanced RestClient.Builder`, URI `http://billing/invoices` được hiểu thế nào?
A. `billing` là zone ID quyết định nơi lưu cache của Registry.
B. `billing` là tên bean RestClient được gọi thay cho HTTP.
C. `billing` là hostname của Eureka server phải được DNS resolve.
D. `billing` là service ID để LoadBalancer chọn instance đích.
Đáp án đúng: D

Câu 23. Muốn `WebClient` gọi theo service ID với Spring Cloud LoadBalancer, nên cấu hình gì?
A. Bean `WebClient.Builder` với base URL của Config Server.
B. Dùng `@LoadBalanced WebClient.Builder` và LoadBalancer.
C. Bean `DiscoveryClient` được đánh dấu `@Transactional`.
D. Bean `ServiceRegistry` làm connector thay cho WebClient.
Đáp án đúng: B

Câu 24. Spring Cloud LoadBalancer thường chọn gì khi client gọi tên một service?
A. Một registry peer để thực thi logic của service thay client.
B. Một instance đích trong tập endpoint khả dụng của service.
C. Một database connection thuộc pool của instance được chọn.
D. Một Config Server node để đọc cấu hình mỗi request.
Đáp án đúng: B

Câu 25. `ServiceInstanceListSupplier` trong Spring Cloud LoadBalancer có nhiệm vụ nào?
A. Tạo HTTP health response cho instance được chọn.
B. Thay thế DiscoveryClient trong tất cả môi trường cloud.
C. Đăng ký từng replica lên Eureka ở mỗi HTTP request.
D. Cung cấp tập ServiceInstance cho chiến lược chọn instance.
Đáp án đúng: D

Câu 26. Khi dùng zone-aware routing, lợi ích và rủi ro nào cần cân nhắc?
A. Zone preference bảo đảm không xử lý trùng HTTP request.
B. Gửi request cùng zone dù instance khỏe ở zone khác.
C. Định tuyến giữa zone làm request có transaction phân tán.
D. Ưu tiên gần zone giảm độ trễ nhưng cần đường fallback.
Đáp án đúng: D

Câu 27. Nếu service ID không còn instance khả dụng, HTTP caller nên xử lý thế nào?
A. Trả lỗi phù hợp và retry hoặc fallback theo chính sách rõ.
B. Ghi URI bất kỳ vào registry để lần gọi sau thành công.
C. Giữ kết nối tới node gần nhất dù node đã bị đánh dấu lỗi.
D. Giữ request vô hạn đến khi Eureka tạo lại instance mới.
Đáp án đúng: A

Câu 28. Registry tạm mất kết nối nhưng client còn cached instances, lưu ý nào đúng?
A. Cache có thể giúp gọi tạm nhưng endpoint có thể stale.
B. Client có danh sách live chính xác nhờ cache khi registry down.
C. Registry outage buộc ứng dụng dừng các HTTP call.
D. Cache kiểm tra sức khỏe từng instance trước từng request.
Đáp án đúng: A

Câu 29. Sau khi tra được instance URI từ discovery, bảo mật giữa hai service cần gì?
A. URI từ registry đồng nghĩa endpoint đã được cấp quyền service.
B. Vẫn cần xác thực, ủy quyền và kiểm tra TLS của đích.
C. Service ID thay cho chữ ký access token khi gọi giữa service.
D. Metadata instance xác thực danh tính thay access token.
Đáp án đúng: B

Câu 30. Vì sao cần hạn chế quyền đăng ký hoặc sửa instance trong service registry?
A. Tránh Config Server tự đổi profile khi một instance mới lên.
B. Tránh endpoint giả mạo bị đưa vào tập instance discovery.
C. Tránh client nhận quá nhiều metric từ actuator endpoint.
D. Tránh Eureka mất kết nối tới database của service khác.
Đáp án đúng: B

Câu 31. Muốn unit test service chọn instance từ `DiscoveryClient`, cách nào phù hợp?
A. Mock `getInstances` trả các ServiceInstance xác định.
B. Kiểm tra annotation của client mà không tra instance.
C. Mock response HTTP mà không kiểm tra việc chọn node.
D. Chạy Eureka thật trong mỗi assertion đơn giản của unit test.
Đáp án đúng: A

Câu 32. Khi giám sát service discovery và load balancing, nhóm số liệu nào hữu ích?
A. Registry fetch lỗi, instance stale, no-instance và call lỗi.
B. Số byte heap, classpath JAR, compiler thread và test count.
C. Số Git branch, build artifact, image layer và cache hit CI.
D. Số HTTP header, JSON field, DTO property và SQL column.
Đáp án đúng: A
