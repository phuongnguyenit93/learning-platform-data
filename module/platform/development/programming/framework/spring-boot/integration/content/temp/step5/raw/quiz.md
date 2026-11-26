Câu 1. Trong Spring Boot, `RestClient` thường phù hợp nhất với kiểu tích hợp nào?
A. Gọi HTTP đồng bộ bằng API fluent và nhận kết quả cụ thể.
B. Gọi HTTP phi chặn trả `Mono` hoặc `Flux` qua WebClient.
C. Gửi sự kiện qua topic với offset của consumer.
D. Nhận message từ queue bằng listener chạy nền.
Đáp án đúng: A

Câu 2. Với `WebClient.retrieve().bodyToMono(...)`, khi nào HTTP request thường được thực hiện?
A. Khi publisher có subscription để bắt đầu xử lý.
B. Ngay lúc gọi `bodyToMono` dù chưa ai subscribe.
C. Ngay lúc khởi tạo bean `WebClient` trong context.
D. Sau khi đóng ứng dụng để flush các request tồn.
Đáp án đúng: A

Câu 3. Muốn đặt connect timeout và response timeout cho HTTP client, hướng nào phù hợp?
A. Đặt `spring.datasource.hikari.connection-timeout` cho pool DB.
B. Đặt `spring.transaction.default-timeout` để điều khiển HTTP.
C. Cấu hình các timeout trên HTTP client transport tương ứng.
D. Đổi Redis TTL để thay thời gian chờ HTTP request.
Đáp án đúng: C

Câu 4. Với Spring `WebClient`, cách xử lý HTTP 4xx/5xx thành lỗi nghiệp vụ nào phù hợp?
A. Dùng `WebClient.Builder.baseUrl(...)` để đổi status lỗi.
B. Dùng `@Transactional` để rollback response từ server.
C. Dùng `retrieve().onStatus(...)` để ánh xạ HTTP status.
D. Dùng `bodyToMono(...)` để tự động retry mọi status lỗi.
Đáp án đúng: C

Câu 5. Khi retry HTTP POST sau timeout không rõ server đã xử lý chưa, nên làm gì?
A. Chỉ tăng số retry của client, không lưu dấu request đã xử lý.
B. Dùng idempotency key và lưu kết quả chống xử lý trùng.
C. Giảm timeout để server trả response trước khi commit.
D. Đổi POST sang GET mà vẫn giữ side effect ban đầu.
Đáp án đúng: B

Câu 6. Đối tác trả HTTP 429 có `Retry-After`. Chiến lược nào phù hợp?
A. Chỉ tăng số connection để vượt giới hạn phía đối tác.
B. Retry ngay liên tục cho tới khi server chấp nhận request.
C. Chuyển tất cả request sang HTTP POST để tránh 429.
D. Retry có giới hạn, backoff và tôn trọng `Retry-After`.
Đáp án đúng: D

Câu 7. Trong Spring Boot, `@ConfigurationProperties` hỗ trợ cách quản lý cấu hình nào?
A. Đọc property nhưng chỉ hỗ trợ String qua `@Value`.
B. Tự đồng bộ mọi property giữa các service đang chạy.
C. Thay thế cơ chế profile và environment của Spring.
D. Bind nhóm thuộc tính vào bean có kiểu và xác thực.
Đáp án đúng: D

Câu 8. Khi kết nối dịch vụ ngoài cần API key, cách quản lý nào an toàn hơn?
A. Lưu khóa trong `application.yml` profile production đã commit Git.
B. Lấy khóa từ kho secret được bảo vệ, không commit vào Git.
C. Đưa khóa vào query string của endpoint để dễ debug.
D. Ghi khóa vào log để mọi replica dùng lại khi restart.
Đáp án đúng: B

Câu 9. Với HikariCP, `maximumPoolSize` chủ yếu giới hạn điều gì?
A. Số entity JPA tối đa được đọc trong mỗi query.
B. Số transaction tối đa trên toàn bộ cluster database.
C. Số HTTP request tối đa của controller đồng thời.
D. Số kết nối database tối đa do pool quản lý.
Đáp án đúng: D

Câu 10. Một service ghi DB rồi gọi HTTP và publish broker trong `@Transactional`. Nhận định nào đúng?
A. Mọi bước đều commit nguyên tử khi đặt `@Transactional`.
B. Broker phải chờ DB commit nhờ annotation của Spring.
C. Transaction cục bộ không tự bao phủ HTTP và broker.
D. HTTP response có thể rollback nếu transaction DB lỗi.
Đáp án đúng: C

Câu 11. Vì sao gọi method `@Transactional` qua `this` trong cùng bean dễ gây hiểu nhầm?
A. Lời gọi nội bộ có thể bỏ qua transaction proxy của Spring.
B. Lời gọi nội bộ luôn được interceptor xử lý như gọi qua bean.
C. Lời gọi nội bộ tự rollback mọi HTTP request đã gửi trước.
D. Lời gọi nội bộ luôn tạo transaction mới với `REQUIRES_NEW`.
Đáp án đúng: A

Câu 12. Dùng Flyway hoặc Liquibase trong ứng dụng Spring Boot giúp điều gì?
A. Theo dõi và áp dụng migration schema có kiểm soát.
B. Biến mọi thay đổi schema thành event qua RabbitMQ.
C. Thay toàn bộ transaction manager của ứng dụng.
D. Đổi schema tự động theo mọi entity trong runtime.
Đáp án đúng: A

Câu 13. Khi truy vấn JPA phát sinh lỗi N+1, cách tối ưu nào thường hiệu quả?
A. Chỉ chuyển mọi association sang `FetchType.LAZY`.
B. Chỉ tăng kích thước connection pool cho từng service khi load cao.
C. Chỉ tăng TTL cache mà không xét các truy vấn phát sinh.
D. Dùng fetch join, entity graph hoặc batch fetch phù hợp.
Đáp án đúng: D

Câu 14. Với `@Cacheable` gọi qua Spring proxy, điều gì xảy ra khi cache hit?
A. Cache bị xóa để bảo đảm lần gọi nào cũng tải mới.
B. Method được gọi trước khi kiểm tra cache hiện tại.
C. Giá trị cache được trả mà không chạy method đích.
D. Chỉ cache exception, còn dữ liệu luôn đọc từ DB.
Đáp án đúng: C

Câu 15. Sau khi cập nhật dữ liệu gốc, cách nào giảm nguy cơ cache trả bản cũ?
A. Đổi tên bean service nhưng giữ nguyên cache entries.
B. Chỉ tăng số replica service dùng chung một cache key.
C. Evict hoặc cập nhật các cache key liên quan theo chính sách.
D. Tăng TTL của bản cache hiện tại để giảm truy vấn DB.
Đáp án đúng: C

Câu 16. Đặt TTL cho entry trong cache thường có tác dụng nào?
A. Giới hạn thời gian entry được giữ trước khi hết hạn.
B. Đảm bảo mọi cache hit đều dùng đúng bản dữ liệu mới nhất.
C. Bảo đảm cache và database luôn nhất quán tức thời.
D. Đồng bộ transaction DB với tất cả cache node tự động.
Đáp án đúng: A

Câu 17. Trong hệ thống nhiều tenant, cache key nên xử lý thông tin tenant thế nào?
A. Chỉ ẩn tenant ID khỏi API nhưng dùng một vùng cache chung.
B. Dùng chung cache key mọi tenant và chỉ lọc tại REST controller.
C. Gắn tenant đã xác thực vào key và kiểm tra quyền truy cập.
D. Tin tenant ID client gửi mà không đối chiếu danh tính.
Đáp án đúng: C

Câu 18. Khi nhiều request cùng gặp cache miss cho một key nóng, cách nào hữu ích?
A. Tăng độ trễ của mọi cache hit bằng một khoảng chờ chung.
B. Đặt TTL vô hạn để không cần kiểm soát độ mới dữ liệu.
C. Đồng bộ tác vụ tải theo key để hạn chế cache stampede.
D. Để tất cả request đồng thời tải DB cùng một bản dữ liệu.
Đáp án đúng: C

Câu 19. Khi gọi `RabbitTemplate.convertAndSend(...)`, tác vụ chính là gì?
A. Xác nhận message do `@RabbitListener` vừa xử lý.
B. Chuyển payload thành message và publish qua exchange.
C. Đồng bộ offset của consumer với transaction DB.
D. Đăng ký consumer mới và ack message từ queue được chỉ định.
Đáp án đúng: B

Câu 20. Trong Spring AMQP, listener ở chế độ `AcknowledgeMode.AUTO` xử lý thành công thì sao?
A. Message chỉ được ack khi database commit ở consumer.
B. Producer tự ack message khi publish vào exchange.
C. Container ack message sau khi listener xử lý xong.
D. Ứng dụng bắt buộc gọi `basicAck` trên channel.
Đáp án đúng: C

Câu 21. Một consumer nhận lại message do mất kết nối trước ack. Cách xử lý nào an toàn hơn?
A. Áp idempotency theo message ID hoặc khóa nghiệp vụ.
B. Tắt consumer ack để broker không giao lại message.
C. Chỉ tăng prefetch để message được cấp lại ít hơn.
D. Bỏ mọi message có cờ redelivered mà không xét xử lý trước.
Đáp án đúng: A

Câu 22. Một `@KafkaListener` ghi DB và commit offset. Điều nào cần lưu ý?
A. Kafka offset commit mặc định rollback mọi DB bên ngoài.
B. Kafka tự điều phối transaction JPA chỉ từ annotation.
C. Offset commit thay thế được khóa idempotency của bản ghi.
D. Commit offset không tự tạo atomic transaction với DB.
Đáp án đúng: D

Câu 23. Outbox pattern giúp nhất quán khi ghi DB và phát sự kiện bằng cách nào?
A. Dùng HTTP request thay broker để tự có commit xuyên hệ thống.
B. Ghi dữ liệu nghiệp vụ và outbox cùng một transaction DB.
C. Ghi DB trước rồi coi mọi lần publish sau đó đều thành công.
D. Publish trực tiếp trước, sau đó mới ghi DB nếu publish ACK.
Đáp án đúng: B

Câu 24. Trong Spring Integration, `IntegrationFlow` thường dùng để mô tả điều gì?
A. Pipeline message qua channel và các bước xử lý endpoint.
B. Cấu hình DataSource và tạo schema SQL bằng migration.
C. Transaction JPA bao phủ tất cả remote service.
D. Ánh xạ REST controller thành Kafka consumer ngay trong flow.
Đáp án đúng: A

Câu 25. Với Spring Integration `DirectChannel`, cách hiểu nào phù hợp?
A. Gửi message đồng bộ tới một subscriber được chọn.
B. Luôn ghi message vào hàng đợi trước khi giao cho handler.
C. Phát bản sao message tới toàn bộ subscriber đồng thời.
D. Luôn lưu message xuống database để bảo đảm replay.
Đáp án đúng: A

Câu 26. Với `PublishSubscribeChannel`, cơ chế phân phối message nào được dùng?
A. Chỉ gửi tới handler có routing key khớp chính xác.
B. Phân phát message tới các subscriber đã đăng ký.
C. Giữ message đến khi nhận ACK từ HTTP client.
D. Chọn đúng một consumer theo vòng quay của queue.
Đáp án đúng: B

Câu 27. `@MessagingGateway` của Spring Integration thường giải quyết nhu cầu nào?
A. Chạy migration schema theo thứ tự cấu hình bean.
B. Tự tạo exchange RabbitMQ cho mọi repository bean.
C. Thay thế HTTP client bằng JDBC template nội bộ.
D. Ánh xạ lời gọi method sang gửi/nhận message qua channel.
Đáp án đúng: D

Câu 28. Trong Spring Integration, router thường thực hiện nhiệm vụ nào?
A. Gộp các message theo correlation ID để tạo payload tổng hợp.
B. Biến đổi payload sang kiểu dữ liệu mới để gửi tiếp.
C. Bỏ message không đạt điều kiện bằng message filter.
D. Chọn channel đầu ra theo nội dung hoặc header message.
Đáp án đúng: D

Câu 29. Trong Spring Integration, transformer chủ yếu xử lý điều gì?
A. Giữ message trong queue chờ worker xử lý.
B. Biến đổi payload message sang dạng phục vụ bước tiếp.
C. Chia một message thành nhiều message con.
D. Chọn channel đầu ra dựa trên header message.
Đáp án đúng: B

Câu 30. Khi luồng Spring Integration có xử lý lỗi bất đồng bộ, `errorChannel` có thể dùng làm gì?
A. Tự retry mọi lỗi với số lần không giới hạn.
B. Nhận `ErrorMessage` để điều phối nhánh xử lý lỗi.
C. Chuyển mọi HTTP status lỗi thành kết quả thành công.
D. Thay thế transaction database để commit message.
Đáp án đúng: B

Câu 31. Muốn thử luồng HTTP → DB → broker sát thực tế, cách kiểm thử nào phù hợp?
A. Chỉ kiểm tra bean Spring khởi tạo không lỗi khi startup.
B. Chỉ mock service method rồi coi như kiểm thử tích hợp.
C. Chỉ chạy unit test converter mà không gửi message.
D. Dùng HTTP stub và Testcontainers cho DB, broker liên quan.
Đáp án đúng: D

Câu 32. Muốn truy vết một yêu cầu đi qua HTTP, DB và broker, nên làm gì?
A. Đổi request ID ở từng hop mà không liên kết chúng.
B. Duy trì trace/correlation ID qua các chặng và đo latency.
C. Ghi toàn bộ payload nhạy cảm vào log để tra cứu.
D. Chỉ đo CPU JVM rồi suy ra thứ tự mọi message.
Đáp án đúng: B
