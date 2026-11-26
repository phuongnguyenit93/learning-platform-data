Câu 1. Với nhiều Spring Boot service, mục tiêu chính của Spring Cloud Config Server là gì?
A. Tạo bản build ứng dụng theo Git branch đang triển khai.
B. Gom file log tập trung rồi trả log theo application name.
C. Quản lý service registry theo instance và zone.
D. Cung cấp cấu hình tập trung theo ứng dụng và profile.
Đáp án đúng: D

Câu 2. Ứng dụng Spring Boot cần annotation nào để bật chức năng Config Server?
A. Đặt `@RefreshScope` trên class cấu hình của server.
B. Đặt `@EnableConfigurationProperties` trên main class.
C. Đặt `@EnableConfigServer` trên ứng dụng server.
D. Thêm `@EnableDiscoveryClient` để bật endpoint config.
Đáp án đúng: C

Câu 3. Config Server dùng Git backend; property nào chỉ định URL repository?
A. Đặt `spring.cloud.config.label` làm URL repository.
B. Dùng `spring.cloud.config.server.git.uri` cho Git backend.
C. Đặt `spring.cloud.config.uri` tại Config Server.
D. Đặt `spring.config.import` trỏ Git repo tại server.
Đáp án đúng: B

Câu 4. Config Client dùng cơ chế Config Data; khai báo nào để lấy cấu hình từ server?
A. Khai báo `management.config.server.uri` trên client.
B. Khai báo `spring.profiles.active=configserver:` ở client.
C. Khai báo `spring.cloud.config.server.git.uri` ở client.
D. Dùng `spring.config.import=configserver:...` trên client.
Đáp án đúng: D

Câu 5. Prefix `optional:` trong `spring.config.import=optional:configserver:...` mang ý nghĩa gì?
A. Cho phép client startup khi nguồn config không khả dụng.
B. Tự ưu tiên bản Git config mới nhất khi kết nối phục hồi.
C. Buộc startup lỗi ngay nếu Config Server không phản hồi.
D. Bỏ qua Config Server khi active profile là production.
Đáp án đúng: A

Câu 6. Thuộc tính nào thường dùng làm application name khi Config Client tải cấu hình?
A. Dùng `spring.application.name` phía Config Client.
B. Dùng `management.server.port` làm tên ứng dụng.
C. Dùng `spring.profiles.active` làm tên ứng dụng.
D. Dùng `spring.cloud.config.label` làm tên ứng dụng.
Đáp án đúng: A

Câu 7. Endpoint nào trả Environment theo application, profile và label tại Config Server?
A. Mẫu `/actuator/env/{application}/{profile}` trả Environment.
B. Mẫu `/{profile}/{application}[/{label}]` trả Environment.
C. Mẫu `/{application}/{label}[/{profile}]` trả Environment.
D. Mẫu `/{application}/{profile}[/{label}]` trả Environment.
Đáp án đúng: D

Câu 8. Trường `propertySources` trong Environment của Config Server biểu diễn gì?
A. Các property ghi lại sau lần refresh gần nhất trên client.
B. Danh sách profile được kích hoạt bởi Git backend.
C. Các nguồn thuộc tính được trả về theo thứ tự ưu tiên.
D. Một map thuộc tính được gộp, không còn tên các nguồn.
Đáp án đúng: C

Câu 9. Khi sử dụng Git backend, `label` của Config Server thường trỏ tới đâu?
A. Chọn Git branch hoặc tag chứa cấu hình cần lấy.
B. Một tenant key để lọc secret được trả cho client.
C. Một instance ID để xác định server nhận request.
D. Một Spring profile đang được bật ở Config Server.
Đáp án đúng: A

Câu 10. Ứng dụng `payment` có active profile `prod`; file nào biểu diễn cấu hình đặc thù?
A. File `payment-dev.yml` vì profile dev là lớp fallback.
B. File `payment-test.yml` vì test là profile nền.
C. File `payment-prod.yml` cho ứng dụng và profile đó.
D. File `prod-payment.yml` theo thứ tự profile rồi app.
Đáp án đúng: C

Câu 11. Config Server cần tìm tệp trong thư mục con của Git; property nào phù hợp?
A. Đặt `spring.cloud.config.server.git.default-label` thành path.
B. Đặt `spring.cloud.bus.destination` bằng đường dẫn thư mục.
C. Đặt `spring.cloud.config.server.git.search-paths` phù hợp.
D. Đặt `spring.cloud.config.client.search-paths` ở client.
Đáp án đúng: C

Câu 12. Muốn môi trường staging và production dùng hai Git branch cấu hình, nên làm gì?
A. Đổi `spring.application.name` thành tên môi trường.
B. Chọn Git label tương ứng với nhánh của từng môi trường.
C. Đổi `server.port` theo môi trường, giữ nguyên Git label.
D. Đổi management base path để tự chọn nhánh cấu hình.
Đáp án đúng: B

Câu 13. Muốn tái lập chính xác cấu hình cùng một bản phát hành, nên quản lý label thế nào?
A. Đặt label bằng thời gian khởi động mỗi container.
B. Pin Git label vào tag hoặc commit đã kiểm chứng.
C. Đặt label theo active profile mà bỏ qua commit Git.
D. Trỏ label tới head của branch phát triển liên tục.
Đáp án đúng: B

Câu 14. Khi Git config được sửa sau khi client đã startup, điều nào đúng?
A. Client tự thay phiên bản thư viện khi Git config đổi.
B. Config Server đẩy trực tiếp mọi file tới bộ nhớ JVM.
C. Giá trị trên client có thể cần refresh hoặc restart.
D. Bean trên client tự nhận mọi commit mà không cần tác động.
Đáp án đúng: C

Câu 15. Muốn startup báo lỗi khi Config Server bắt buộc không thể truy cập, cách nào phù hợp?
A. Dùng remote config import với prefix `optional:`.
B. Đặt Git search path để client bỏ qua lỗi kết nối server.
C. Kiểm tra `/actuator/health` của server thay cho import bắt buộc.
D. Dùng remote import bắt buộc, bỏ prefix `optional:`.
Đáp án đúng: D

Câu 16. Khi Config Server tạm thời mất kết nối mạng lúc client startup, retry nào phù hợp?
A. Retry liên tục không giới hạn mà không đo thời gian chờ.
B. Sửa Git label ngẫu nhiên sau mỗi lần không kết nối.
C. Retry có giới hạn, backoff và báo lỗi khi hết lượt.
D. Bỏ bước TLS verification để giảm xác suất timeout.
Đáp án đúng: C

Câu 17. Khi một property tồn tại ở nhiều nguồn, nên xác nhận giá trị hiệu lực thế nào?
A. Ưu tiên giá trị trong local YAML bất kể nguồn import.
B. Xem thứ tự ưu tiên của PropertySource trong Environment.
C. Ưu tiên source có filename dài nhất khi trùng key.
D. Ưu tiên giá trị từ Git bất kể bootstrap hay local config.
Đáp án đúng: B

Câu 18. Vì sao cần hạn chế quyền truy cập `/actuator/env` của Config Client?
A. Endpoint có thể hé lộ chi tiết cấu hình nhạy cảm.
B. Endpoint có thể tự phát Bus refresh tới tất cả node.
C. Endpoint có thể tự thay đổi JVM heap khi người dùng GET.
D. Endpoint có thể tự đổi Git label ngay khi được GET.
Đáp án đúng: A

Câu 19. Với một bean gắn `@RefreshScope`, refresh có thể dẫn tới hành vi nào?
A. Bean được tái tạo mỗi lần Config Server trả HTTP 200.
B. Bean được chuyển thành singleton bất biến sau refresh.
C. Bean được tái tạo khi sử dụng sau sự kiện refresh.
D. Bean được thay mới khi Git có commit mà không cần refresh.
Đáp án đúng: C

Câu 20. Muốn yêu cầu một Config Client nạp lại cấu hình khi đang chạy, thao tác nào phù hợp?
A. Gửi GET tới `/actuator/info` để tải lại Git repository.
B. Gửi POST tới `/actuator/loggers` để refresh property.
C. Gửi GET tới `/actuator/health` để kích hoạt refresh.
D. POST `/actuator/refresh` đã được expose và bảo vệ.
Đáp án đúng: D

Câu 21. Tại sao không phải mọi thay đổi cấu hình đều có hiệu lực ngay sau refresh?
A. Config Server chặn mọi property có kiểu dữ liệu số.
B. Git repository yêu cầu cấu hình chỉ được đọc một lần.
C. Refresh tự đóng mọi bean không thuộc web application.
D. Một số bean và thiết lập cần restart để áp dụng.
Đáp án đúng: D

Câu 22. Spring Cloud Bus giúp triển khai cấu hình mới trên nhiều instance bằng cách nào?
A. Gửi sự kiện refresh qua broker tới các instance liên quan.
B. Đồng bộ file application.yml bằng shared network volume.
C. Ghi lại property của từng instance vào bảng SQL trung tâm.
D. Gửi trực tiếp nội dung Git config vào JVM qua một servlet.
Đáp án đúng: A

Câu 23. Endpoint nào thường dùng để phát sự kiện refresh của Spring Cloud Bus?
A. GET `/actuator/metrics` sau mỗi lần Config Server commit.
B. POST `/actuator/busrefresh` khi đã cấu hình và expose.
C. POST `/actuator/loggers` khi thay Git profile của server.
D. GET `/actuator/health` khi thay đổi giá trị remote config.
Đáp án đúng: B

Câu 24. Để Spring Cloud Bus chuyển sự kiện giữa các instance, hạ tầng nào phù hợp?
A. Dùng Redis HTTP session chung với các Config Client.
B. Dùng JDBC transaction manager chung với Config Server.
C. Dùng reverse proxy cân bằng tải cho mọi actuator endpoint.
D. Dùng message broker được hỗ trợ như RabbitMQ hoặc Kafka.
Đáp án đúng: D

Câu 25. Khi expose endpoint refresh và busrefresh, kiểm soát nào phù hợp?
A. Giới hạn quyền gọi endpoint và lưu nhật ký thao tác.
B. Cho mọi client gọi refresh đến bất kỳ service nào.
C. Chỉ thay URL endpoint bằng chuỗi ngẫu nhiên rồi mở công khai.
D. Bỏ HTTPS khi endpoint chỉ có IP thuộc mạng nội bộ.
Đáp án đúng: A

Câu 26. Muốn quản lý API key cho các service qua cấu hình tập trung, cách nào an toàn hơn?
A. Dùng secret manager hoặc dữ liệu mã hóa với khóa riêng.
B. Đổi tên property thành `maskedPassword` rồi commit Git.
C. Đưa key vào tên branch để tránh xuất hiện trong nội dung.
D. Đặt plaintext key vào Git private và cấp quyền đọc chung.
Đáp án đúng: A

Câu 27. Với giá trị `{cipher}...` ở Config Server, cần bảo vệ yếu tố nào?
A. Chỉ port của container đang clone repository Git backend.
B. Khóa giải mã cùng quyền đọc bản cấu hình sau giải mã.
C. Chỉ cache TTL của Environment được gửi từ Config Server.
D. Chỉ active profile của Config Client đang nhận cấu hình.
Đáp án đúng: B

Câu 28. Khi bảo vệ API của Config Server, cách nào giảm nguy cơ lộ dữ liệu trên đường truyền?
A. Cache response HTTPS tại reverse proxy cho mọi client.
B. Đặt Config Server sau DNS tên miền nội bộ là đủ.
C. Đổi tên các endpoint config bằng một URL khó đoán.
D. Dùng TLS cùng xác thực và ủy quyền Config Client.
Đáp án đúng: D

Câu 29. Trước khi đổi cấu hình production qua Git, quy trình nào có kiểm soát hơn?
A. Push trực tiếp lên branch production rồi quan sát sau.
B. Review PR, test và ghi lại Git version được phát hành.
C. Thông báo qua chat mà không lưu thay đổi trong Git.
D. Đổi property trên từng pod mà không theo dõi commit.
Đáp án đúng: B

Câu 30. Nếu rollout làm lỗi một nhóm service, cách rollback cấu hình nào phù hợp?
A. Đặt Git branch thành chuỗi trống để bỏ qua cấu hình.
B. Đổi tên Config Server để client tự lấy lại bản trước.
C. Quay về Git label đã kiểm chứng và refresh hoặc restart.
D. Tăng số lần retry để giá trị sai được sửa khi tải.
Đáp án đúng: C

Câu 31. Muốn kiểm tra config drift giữa nhiều instance, nên theo dõi gì?
A. Chỉ xem số heap và thread mà mỗi service đang dùng.
B. So sánh Git label/commit cấu hình hiệu lực của từng node.
C. Chỉ xem số request HTTP đã qua load balancer mỗi node.
D. Chỉ xem uptime của Config Server mà không so các instance.
Đáp án đúng: B

Câu 32. Cách kiểm thử nào xác nhận Config Client đọc đúng profile và label từ Config Server?
A. Test client nhận đúng key theo profile/label từ Config Server.
B. Chỉ kiểm tra Config Server mở TCP port trả 200 ở health.
C. Chỉ kiểm tra giá trị local YAML mà không yêu cầu remote.
D. Mock `Environment.getProperty` và coi Git backend đúng.
Đáp án đúng: A
