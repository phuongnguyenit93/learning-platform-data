Câu 1. Muốn kích hoạt các endpoint quản trị Spring Boot Actuator, dependency nào thường được thêm?
A. Khai báo `micrometer-core` rồi mọi endpoint tự xuất hiện.
B. Khai báo `spring-boot-devtools` để bật các endpoint.
C. Khai báo `spring-boot-starter-web` rồi có đủ Actuator.
D. Khai báo `spring-boot-starter-actuator` trong dependencies.
Đáp án đúng: D

Câu 2. Nếu chưa đổi base path, Actuator web endpoint nằm dưới tiền tố nào?
A. Dưới đường dẫn `/health` cho mọi endpoint quản trị.
B. Dưới đường dẫn `/actuator` của ứng dụng Spring Boot.
C. Dưới đường dẫn `/metrics` cho mọi endpoint quản trị.
D. Dưới đường dẫn `/manage` khi chưa cấu hình thủ công.
Đáp án đúng: B

Câu 3. Cấu hình nào cho phép expose thêm health, info và metrics qua HTTP?
A. `management.endpoints.web.exposure.include=health,info,metrics`.
B. `management.server.port=health,info,metrics` trong app.
C. `management.endpoint.health.show-details=health,info,metrics` qua web.
D. `management.metrics.tags.application=health,info,metrics`.
Đáp án đúng: A

Câu 4. Endpoint đã enabled nhưng chưa được web-expose sẽ có đặc điểm nào?
A. Tự đổi URL thành `/actuator/health` để dùng chung.
B. Có thể hoạt động nhưng không truy cập được qua HTTP.
C. Vẫn được công khai qua web nhờ có bean endpoint.
D. Tự đổi thành đường dẫn POST trong HTTP router.
Đáp án đúng: B

Câu 5. Theo mapping mặc định, health trạng thái `DOWN` thường trả HTTP nào?
A. Trả `302 Found` để chuyển sang trang kiểm tra.
B. Trả `503 Service Unavailable` cho trạng thái DOWN.
C. Trả `200 OK` vì endpoint vẫn xử lý được request.
D. Trả `404 Not Found` vì không có health contributor.
Đáp án đúng: B

Câu 6. Muốn thêm kiểm tra health riêng cho một dependency, nên làm gì?
A. Tạo bean triển khai `HealthIndicator` và trả `Health`.
B. Tạo bean `InfoContributor` để đổi mã HTTP health.
C. Tạo bean `WebMvcConfigurer` để đổi status aggregator.
D. Tạo bean `MeterBinder` để đặt trạng thái health.
Đáp án đúng: A

Câu 7. `management.endpoint.health.show-details=when-authorized` có tác dụng nào?
A. Chỉ hiển thị chi tiết health cho đối tượng được phép.
B. Chỉ xuất health dưới Prometheus, không hiển thị details qua HTTP.
C. Tắt mọi health indicator không có quyền quản trị.
D. Trả chi tiết health công khai trên mọi đường dẫn web.
Đáp án đúng: A

Câu 8. Liveness probe của Kubernetes nên phản ánh điều gì?
A. Ứng dụng xử lý được bao nhiêu request đồng thời.
B. Instance đã sẵn sàng nhận traffic mới từ Service.
C. Tiến trình còn khỏe để tiếp tục chạy.
D. Database phụ thuộc đang có đủ connection cho truy vấn.
Đáp án đúng: C

Câu 9. Readiness probe của Spring Boot thường phản ánh điều gì?
A. Số phiên JVM heap dump từng được tải qua Actuator.
B. Tiến trình đã được khởi động lại bao nhiêu lần.
C. Luồng Java đang chờ lock dài nhất trong ứng dụng.
D. Instance có sẵn sàng nhận lưu lượng mới hay không.
Đáp án đúng: D

Câu 10. Muốn bật health probes ngoài môi trường Kubernetes, cấu hình nào phù hợp?
A. Đặt `management.endpoint.health.probes.enabled=true`.
B. Đặt `management.server.port=8081` để bật probes.
C. Đặt `management.endpoint.health.show-details=always` cho probes.
D. Đặt `management.endpoints.web.base-path=/ready`.
Đáp án đúng: A

Câu 11. Theo mặc định, status health nào thường ánh xạ HTTP 503?
A. Hai trạng thái `UNKNOWN` và `UP` đã tổng hợp.
B. Hai trạng thái `UP` và `UNKNOWN` của health.
C. Hai trạng thái `DOWN` và `OUT_OF_SERVICE`.
D. Hai trạng thái `UP` và `OUT_OF_SERVICE`.
Đáp án đúng: C

Câu 12. Vì sao không nên dựa vào database bên ngoài để quyết định liveness?
A. Liveness không cho phép thêm contributor của dependency vào group.
B. Liveness chỉ có thể đọc dữ liệu từ JVM heap memory.
C. Liveness phải bỏ qua mọi tín hiệu từ ApplicationContext.
D. Lỗi ngoài có thể khiến nhiều pod bị restart không cần thiết.
Đáp án đúng: D

Câu 13. GET `/actuator/metrics` thường hỗ trợ thao tác nào?
A. Trả toàn bộ chuỗi dữ liệu theo format Prometheus.
B. Liệt kê cấu trúc request mapping của controller.
C. Liệt kê tên các metric mà ứng dụng đang đăng ký.
D. Ghi cấu hình mức log cho từng logger đang hoạt động.
Đáp án đúng: C

Câu 14. GET `/actuator/metrics/{name}` thường trả về thông tin nào?
A. Chuỗi access log của server kể từ lúc khởi động.
B. Một heap snapshot của process ở thời điểm gọi.
C. Các measurement của meter và những tag khả dụng.
D. Danh sách endpoint đang expose theo từng HTTP port.
Đáp án đúng: C

Câu 15. Micrometer `Counter` phù hợp để đo giá trị nào?
A. Thời lượng của từng lượt xử lý request đến server.
B. Số sự kiện tích lũy như tổng lượt xử lý thành công.
C. Độ sâu queue tức thời đang chờ một worker nhận.
D. Phân bố kích thước byte của các payload gửi đi.
Đáp án đúng: B

Câu 16. Micrometer `Timer` phù hợp nhất với dạng phép đo nào?
A. Thời gian thao tác cùng số mẫu được ghi nhận.
B. Số luồng Netty đang mở khi ứng dụng khởi động.
C. Mức đang dùng của connection pool tại thời điểm đọc.
D. Số message đã tiêu thụ tính lũy kế qua các lần.
Đáp án đúng: A

Câu 17. Micrometer `Gauge` nên được dùng trong trường hợp nào?
A. Đo phân vị thời gian cho một thao tác HTTP.
B. Đếm số request lũy kế từ lúc ứng dụng khởi động.
C. Đọc mức hiện tại của một hàng đợi.
D. Ghi tổng dung lượng mọi message đã từng gửi.
Đáp án đúng: C

Câu 18. Vì sao dùng `userId` làm metric tag có thể gây vấn đề?
A. Tự giảm thời gian scrape xuống một mức cố định.
B. Tạo quá nhiều tổ hợp tag và time series để lưu.
C. Ngăn exporter Prometheus đọc các metric khác.
D. Tự thay metric kiểu Counter sang Timer cho user.
Đáp án đúng: B

Câu 19. Micrometer `DistributionSummary` phù hợp nhất để đo điều gì?
A. Thời gian hoàn tất từng request HTTP cùng số mẫu và phân vị.
B. Giá trị hiện tại của một queue được đọc từ broker.
C. Số request tăng dần kể từ lúc ứng dụng bắt đầu.
D. Phân bố kích thước payload hoặc giá trị không phải thời gian.
Đáp án đúng: D

Câu 20. Muốn xuất metric Actuator theo định dạng Prometheus, dependency nào cần thiết?
A. Thêm `spring-boot-devtools` để tạo metric Prometheus.
B. Thêm `micrometer-registry-prometheus` vào ứng dụng.
C. Thêm `spring-boot-starter-webflux` để kích hoạt registry.
D. Thêm `spring-boot-starter-data-jpa` để ghi time series.
Đáp án đúng: B

Câu 21. Muốn Prometheus scrape metric qua HTTP, endpoint nào cần được expose?
A. Expose `/actuator/metrics` mà không cần Prometheus registry.
B. Expose `/actuator/loggers` để đọc số liệu đo.
C. Expose `/actuator/prometheus` với chính sách truy cập.
D. Expose `/actuator/info` rồi dùng định dạng JSON.
Đáp án đúng: C

Câu 22. Trong mô hình scrape phổ biến, Prometheus thu thập metric thế nào?
A. Đồng bộ mỗi file log dưới dạng một mẫu metric.
B. Nhận được push từ Actuator ở mỗi lần Counter tăng.
C. Đọc dữ liệu trực tiếp từ Spring application context.
D. Chủ động GET endpoint metric theo chu kỳ.
Đáp án đúng: D

Câu 23. Đối với `/actuator/env` và `/actuator/heapdump`, chính sách nào phù hợp?
A. Đổi tên endpoint rồi không cần giới hạn truy cập.
B. Đưa endpoint lên port khác và bỏ xác thực quản trị.
C. Chỉ expose khi cần và áp kiểm soát quyền chặt chẽ.
D. Mở công khai do Actuator tự che mọi dữ liệu nhạy cảm.
Đáp án đúng: C

Câu 24. Nếu ứng dụng tự định nghĩa `SecurityFilterChain`, cần chú ý gì?
A. Tự đặt rule bảo vệ các endpoint Actuator được expose.
B. Mọi actuator endpoint được chặn kể cả đã permitAll.
C. Spring Boot tự thêm filter chain mới sau bean của app.
D. Actuator tự cấu hình bảo mật bỏ qua mọi rule tùy chỉnh.
Đáp án đúng: A

Câu 25. `management.server.port` thường được dùng vào mục đích nào?
A. Chỉnh thời gian chờ phản hồi cho health indicator.
B. Thay đổi port exporter Prometheus ở hệ giám sát.
C. Đặt mức log mặc định cho các endpoint đang expose.
D. Phục vụ endpoint quản trị trên một cổng khác ứng dụng.
Đáp án đúng: D

Câu 26. GET `/actuator/loggers/{name}` cho biết những gì về logger?
A. Giá trị configuration property đã mask tại endpoint env.
B. Mức log cấu hình và mức log thực tế đang hiệu lực.
C. Số lần gọi từng endpoint HTTP tính từ lúc boot.
D. Trạng thái readiness của pod và health tổng hợp.
Đáp án đúng: B

Câu 27. POST đến `/actuator/loggers/{name}` với body hợp lệ có thể làm gì?
A. Điều chỉnh `configuredLevel` khi ứng dụng đang chạy.
B. Chuyển các message log sang Prometheus registry.
C. Khởi động lại ứng dụng để cập nhật logging tự động.
D. Đổi mức log và ghi vĩnh viễn vào file cấu hình application.
Đáp án đúng: A

Câu 28. Endpoint `/actuator/conditions` hữu ích khi chẩn đoán vấn đề nào?
A. Vì sao một bean có nhiều dependency đang được inject.
B. Vì sao log level của một package bị thay đổi gần đây.
C. Vì sao request controller bị định tuyến sang URL khác.
D. Vì sao một auto-configuration match hoặc không match.
Đáp án đúng: D

Câu 29. Endpoint `/actuator/mappings` chủ yếu cung cấp loại dữ liệu nào?
A. Danh sách metric name cùng measurement hiện tại.
B. Danh sách class bean và dependency injection graph.
C. Danh sách thread đang chạy và trạng thái khóa lock.
D. Danh sách mapping HTTP hoặc handler đã đăng ký.
Đáp án đúng: D

Câu 30. Khi cho tải `/actuator/heapdump`, rủi ro nào cần tính đến?
A. Heap dump chỉ chứa số liệu Counter đã tổng hợp thành công.
B. Heap dump chỉ gồm metadata cấu hình của endpoint web.
C. Heap dump có thể chứa dữ liệu nhạy cảm và dung lượng lớn.
D. Heap dump bỏ qua các object session và thông tin của người dùng.
Đáp án đúng: C

Câu 31. Muốn `/actuator/httpexchanges` có dữ liệu trao đổi HTTP, thường cần gì?
A. Chỉ expose endpoint web mà không cần repository lưu.
B. Cung cấp bean `HttpExchangeRepository` để ghi exchange.
C. Chỉ thêm Prometheus registry để thu request/response.
D. Chỉ đặt `management.server.port` để ghi HTTP history.
Đáp án đúng: B

Câu 32. Bài kiểm thử nào xác nhận readiness probe phản ánh trạng thái ứng dụng?
A. Bật probes và kiểm tra readiness khi trạng thái thay đổi.
B. Chỉ kiểm tra endpoint `/actuator/metrics` có tên meter.
C. Chỉ khởi động context và đếm HealthIndicator bean.
D. Chỉ kiểm tra URL `/actuator/health` luôn trả `200 OK` qua HTTP.
Đáp án đúng: A
