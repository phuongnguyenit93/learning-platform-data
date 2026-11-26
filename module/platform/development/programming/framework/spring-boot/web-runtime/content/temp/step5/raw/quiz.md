Câu 01. Với `spring-boot-starter-web` và không đổi dependency, web server nhúng mặc định nào được dùng?
A. Undertow phục vụ ứng dụng theo mô hình Servlet
B. Reactor Netty phục vụ ứng dụng theo mô hình reactive
C. Jetty phục vụ ứng dụng theo mô hình Servlet
D. Tomcat phục vụ ứng dụng theo mô hình Servlet
Đáp án đúng: D

Câu 02. Muốn chuyển ứng dụng MVC từ embedded Tomcat sang Jetty, cách cấu hình dependency nào phù hợp?
A. Loại `starter-tomcat` rồi thêm `starter-jetty`
B. Đổi tên context-path để Spring chọn Jetty thay Tomcat
C. Giữ Tomcat và chỉ đổi `server.port` sang cổng Jetty
D. Thêm `starter-webflux` để Tomcat tự đổi thành Jetty
Đáp án đúng: A

Câu 03. Ứng dụng chỉ dùng `spring-boot-starter-webflux`; web server nhúng mặc định thường là gì?
A. Reactor Netty phục vụ request theo mô hình reactive
B. Tomcat phục vụ request theo mô hình reactive
C. Jetty phục vụ request theo mô hình reactive
D. Undertow phục vụ request theo mô hình reactive
Đáp án đúng: A

Câu 04. Khi cả `starter-web` và `starter-webflux` nằm trên classpath, Spring Boot mặc định chọn stack nào?
A. Reactive WebFlux do cả hai starter đều có HTTP codec
B. Servlet MVC do có các thành phần Web MVC
C. Không khởi động vì không xác định được web stack
D. Reactive WebFlux do phát hiện Reactor trên classpath
Đáp án đúng: B

Câu 05. Nếu hai web starter cùng có mặt, cách ép Spring Boot sử dụng reactive web application là gì?
A. Đặt `spring.main.web-application-type=reactive`
B. Đặt `server.servlet.context-path=reactive`
C. Đặt `spring.mvc.async.request-timeout=reactive`
D. Đặt `server.tomcat.threads.max=reactive`
Đáp án đúng: A

Câu 06. Khi đặt `server.port=0` cho embedded server, điều gì xảy ra lúc startup?
A. Máy chủ tắt HTTP connector và chỉ giữ management port
B. Máy chủ sử dụng cổng 8080 theo fallback mặc định
C. Máy chủ từ chối start do cấu hình cổng không hợp lệ
D. Máy chủ bind vào một cổng trống do hệ điều hành chọn
Đáp án đúng: D

Câu 07. Muốn giới hạn embedded server chỉ lắng nghe trên một địa chỉ mạng cụ thể, property nào phù hợp?
A. `server.servlet.context-path` chọn địa chỉ bind
B. `management.endpoint.health.path` chọn địa chỉ bind
C. `server.address` chọn địa chỉ bind của listener
D. `server.port` chọn địa chỉ bind của listener
Đáp án đúng: C

Câu 08. Trong ứng dụng Spring MVC trên Servlet, thành phần nào xử lý request ở tầng servlet trước `DispatcherServlet`?
A. `ViewResolver` chạy trước filter chain của container
B. `HandlerInterceptor` chạy trước filter chain của container
C. Servlet `Filter` chạy trong filter chain của container
D. `HttpMessageConverter` chạy trước filter chain của container
Đáp án đúng: C

Câu 09. Thành phần nào làm front controller tiếp nhận request HTTP và điều phối các handler Spring MVC?
A. `HandlerMapping` nhận request bằng socket của Tomcat
B. `DispatcherServlet` là servlet trung tâm của Spring MVC
C. `HandlerAdapter` tự nhận request từ network connector
D. `ViewResolver` thực hiện dispatch HTTP của container
Đáp án đúng: B

Câu 10. Sau khi nhận request, thành phần Spring MVC nào xác định handler phù hợp với mapping?
A. `HttpMessageConverter` chuyển request body sang object
B. `HandlerMapping` tìm handler theo yêu cầu hiện tại
C. `ViewResolver` tìm template cho model được trả về
D. `HandlerAdapter` thực thi method của handler đã chọn
Đáp án đúng: B

Câu 11. Khi đã tìm thấy handler, thành phần nào Spring MVC dùng để gọi handler theo loại phù hợp?
A. `HttpMessageConverter` đọc hoặc ghi HTTP message body
B. `HandlerMapping` chỉ chọn handler từ mapping registry
C. `HandlerAdapter` thực thi handler đã được resolve
D. `ViewResolver` tìm view phù hợp cho model trả về
Đáp án đúng: C

Câu 12. Trong Spring MVC, thành phần nào chuyển JSON request body thành Java object khi cấu hình hỗ trợ?
A. `HandlerExceptionResolver` giải mã body HTTP thành object
B. `ViewResolver` giải mã body HTTP thành object
C. `HttpMessageConverter` giải mã body HTTP thành object
D. `HandlerMapping` giải mã body HTTP thành object
Đáp án đúng: C

Câu 13. `@RestController` trả DTO dưới dạng JSON trong Spring MVC; cơ chế nào thường đảm nhiệm serialization?
A. `HandlerMapping` serialize DTO sau khi chọn handler
B. `HandlerInterceptor` chuyển DTO sang JSON mặc định
C. `ViewResolver` kết xuất JSON bằng MVC template
D. Jackson converter thuộc hệ `HttpMessageConverter`
Đáp án đúng: D

Câu 14. Trong WebFlux functional/annotated handling, front controller tương ứng MVC DispatcherServlet là gì?
A. `WebFilter` chọn handler theo annotation controller
B. `DispatcherServlet` điều phối các handler của WebFlux
C. `DispatcherHandler` điều phối các handler của WebFlux
D. `HandlerMapping` đọc trực tiếp request từ TCP connector
Đáp án đúng: C

Câu 15. Muốn xử lý cross-cutting trước/sau request trong WebFlux reactive chain, nên dùng thành phần nào?
A. Servlet `Filter` can thiệp luồng `ServerWebExchange`
B. `WebFilter` can thiệp luồng `ServerWebExchange`
C. MVC `HandlerInterceptor` can thiệp `ServerWebExchange`
D. MVC `ViewResolver` can thiệp `ServerWebExchange`
Đáp án đúng: B

Câu 16. Muốn gọi HTTP upstream bằng API client non-blocking trả `Mono`/`Flux`, nên dùng gì?
A. `WebClient` hỗ trợ HTTP client dạng reactive
B. `RestClient` cung cấp Mono/Flux theo mặc định
C. `HttpURLConnection` cung cấp Mono/Flux theo mặc định
D. `RestTemplate` cung cấp Mono/Flux theo mặc định
Đáp án đúng: A

Câu 17. Một controller dùng `@RestController` và trả `Mono`, có tự động đổi MVC sang server WebFlux không?
A. Không; loại ứng dụng vẫn do stack và cấu hình quyết định
B. Không; method trả Mono bị từ chối trong Spring MVC
C. Có; method trả Mono sẽ tự chuyển server sang WebFlux
D. Có; annotation RestController tự kích hoạt Reactor Netty
Đáp án đúng: A

Câu 18. Trong Spring MVC xử lý JDBC đồng bộ, việc chờ truy vấn lâu thường ảnh hưởng ra sao?
A. Event loop Netty xử lý thay các request thread Servlet
B. Spring tự chuyển JDBC sang reactive trước khi truy vấn
C. Request thread Servlet bị giữ trong lúc chờ JDBC
D. Servlet container giải phóng request thread khi JDBC chờ
Đáp án đúng: C

Câu 19. Với Reactor Netty trong WebFlux, vì sao tránh chạy I/O blocking trực tiếp trên event loop?
A. Blocking khiến các Mono tự chuyển sang transaction rollback
B. Blocking khiến WebFilter mất khả năng đọc header request
C. Blocking buộc Servlet tạo thêm thread theo mỗi HTTP request
D. Blocking giữ event-loop thread và làm chậm các kết nối khác
Đáp án đúng: D

Câu 20. Khi WebFlux phải gọi thư viện blocking cũ, lựa chọn scheduler Reactor nào hay dùng?
A. `Schedulers.boundedElastic()` cách ly tác vụ blocking
B. `Schedulers.single()` cấp thread riêng cho từng request
C. `Schedulers.parallel()` dùng cho gọi JDBC blocking kéo dài
D. `Schedulers.immediate()` chuyển blocking sang worker pool
Đáp án đúng: A

Câu 21. Reactive Streams backpressure trong WebFlux chủ yếu giúp gì khi consumer xử lý chậm?
A. Ép HTTP client tăng request rate cho đúng cấu hình topK
B. Thay thế giới hạn kích thước body của các codec HTTP
C. Điều phối demand thay vì phát vô hạn dữ liệu vào consumer
D. Buộc Servlet gọi `request.getInputStream()` bất đồng bộ
Đáp án đúng: C

Câu 22. Để stream server-sent events từ WebFlux controller, tổ hợp nào phù hợp?
A. Trả `Mono` và chọn media type `multipart/form-data`
B. Trả `Flux` nhưng thiết lập media type `application/zip`
C. Trả `Flux` với media type `text/event-stream`
D. Trả `List` sau khi gom đủ dữ liệu với `application/json`
Đáp án đúng: C

Câu 23. Khi WebFlux báo vượt bộ nhớ đệm codec do aggregate body quá lớn, cấu hình nào cần xem?
A. `server.max-http-request-header-size` giới hạn buffer codec
B. `spring.codec.max-in-memory-size` giới hạn buffer codec
C. `spring.servlet.multipart.max-file-size` giới hạn buffer codec
D. `server.tomcat.accept-count` giới hạn buffer codec
Đáp án đúng: B

Câu 24. Với Servlet multipart upload, muốn giới hạn dung lượng từng file, property nào phù hợp?
A. `spring.servlet.multipart.max-file-size` giới hạn file upload
B. `spring.servlet.multipart.max-request-size` giới hạn file upload
C. `spring.codec.max-in-memory-size` giới hạn file upload
D. `server.max-http-request-header-size` giới hạn file upload
Đáp án đúng: A

Câu 25. Muốn hạn chế độ lớn phần header của HTTP request ở embedded server, property nào liên quan?
A. `spring.servlet.multipart.max-request-size` giới hạn header
B. `server.tomcat.max-http-form-post-size` giới hạn header
C. `server.max-http-request-header-size` giới hạn header
D. `spring.codec.max-in-memory-size` giới hạn header
Đáp án đúng: C

Câu 26. Khi Tomcat worker threads bị bão hòa do blocking handlers, property nào điều chỉnh số request-processing threads tối đa?
A. `server.connection-timeout` giới hạn thread xử lý request
B. `server.tomcat.max-connections` giới hạn thread xử lý request
C. `server.tomcat.accept-count` giới hạn thread xử lý request
D. `server.tomcat.threads.max` giới hạn thread xử lý request
Đáp án đúng: D

Câu 27. Với MVC đồng bộ, dấu hiệu nào gợi ý thiếu request threads khi nhiều truy vấn DB chậm?
A. p95 giảm vì thread tự giải phóng khi JDBC còn chờ
B. Thời gian chờ tăng cùng mức sử dụng Tomcat threads cao
C. Số active threads bằng không khi controller đang xử lý
D. Tomcat chuyển toàn bộ blocking JDBC sang event loop
Đáp án đúng: B

Câu 28. Trong cấu hình Tomcat của Spring Boot, `server.tomcat.max-connections` chủ yếu đặt giới hạn gì?
A. Số request đang chờ trong hàng đợi accept backlog
B. Số kết nối Tomcat có thể chấp nhận và duy trì cùng lúc
C. Số byte tối đa của multipart request khi upload
D. Số worker thread xử lý Java controller cùng một lúc
Đáp án đúng: B

Câu 29. Bật HTTPS trực tiếp trên embedded server với keystore, nhóm cấu hình nào có vai trò chính?
A. `server.servlet.session.timeout` cùng thông tin password
B. `server.http2.enabled` cùng thông tin password phù hợp
C. `server.tomcat.threads.max` cùng thông tin password
D. `server.ssl.key-store` cùng thông tin password phù hợp
Đáp án đúng: D

Câu 30. Nếu embedded server và nền tảng hỗ trợ HTTP/2, property nào bật giao thức này trong Spring Boot?
A. `server.http2.enabled=true` kích hoạt hỗ trợ HTTP/2
B. `server.compression.enabled=true` kích hoạt hỗ trợ HTTP/2
C. `server.ssl.enabled=true` bật HTTP/2 cả khi thiếu ALPN
D. `server.servlet.session.timeout=2` kích hoạt HTTP/2
Đáp án đúng: A

Câu 31. Ứng dụng sau reverse proxy HTTPS cần đọc scheme/host gốc từ forwarded headers; cấu hình nào hữu ích?
A. `server.servlet.session.timeout=framework` xử lý headers
B. `spring.codec.max-in-memory-size=framework` xử lý headers
C. `server.tomcat.threads.max=framework` xử lý headers
D. `server.forward-headers-strategy=framework` xử lý headers
Đáp án đúng: D

Câu 32. Khi xử lý `X-Forwarded-Proto` từ client không qua proxy đáng tin, rủi ro bảo mật là gì?
A. Header giả khiến Servlet tự tăng timeout của session
B. Header giả buộc TLS ở proxy tự sinh chứng chỉ mới
C. Header giả thay đổi context-path của ứng dụng lúc build
D. Header giả có thể làm sai scheme/host khi sinh URL
Đáp án đúng: D

Câu 33. Nếu chỉ muốn session cookie Servlet gửi qua HTTPS, property Spring Boot nào phù hợp?
A. `server.servlet.session.cookie.secure=true` đánh dấu Secure
B. `server.servlet.session.cookie.http-only=true` đánh dấu Secure
C. `server.servlet.session.cookie.same-site=lax` đánh dấu Secure
D. `server.servlet.session.cookie.name=secure` đánh dấu Secure
Đáp án đúng: A

Câu 34. Muốn thiết lập hành vi SameSite của session cookie Servlet, cấu hình nào tương ứng?
A. `server.servlet.session.cookie.http-only=true` điều khiển SameSite
B. `server.servlet.session.timeout=30m` điều khiển SameSite
C. `server.servlet.session.cookie.secure=true` điều khiển SameSite
D. `server.servlet.session.cookie.same-site=lax` điều khiển SameSite
Đáp án đúng: D

Câu 35. Nhiều replica Servlet cần giữ session sau khi một node mất; cách nào phù hợp?
A. Dùng `server.port=0` để container tự đồng bộ các HttpSession
B. Dùng HttpSession trong bộ nhớ từng node không chia sẻ state
C. Dùng Spring Session với Redis chung để lưu session ngoài node
D. Dùng cookie name giống nhau nhưng giữ session riêng mỗi node
Đáp án đúng: C

Câu 36. Muốn embedded web server ngừng nhận request mới và chờ request đang chạy khi tắt, dùng gì?
A. `server.shutdown=graceful` bật graceful shutdown
B. `spring.lifecycle.timeout-per-shutdown-phase` tự bật graceful
C. `management.endpoint.shutdown.enabled=true` tự bật graceful
D. `server.tomcat.threads.max=0` bật graceful shutdown
Đáp án đúng: A

Câu 37. Property nào giới hạn thời gian chờ ở mỗi phase dừng `SmartLifecycle` trong Spring Boot?
A. `spring.mvc.async.request-timeout` quy định phase dừng
B. `spring.lifecycle.timeout-per-shutdown-phase` quy định timeout
C. `server.servlet.session.timeout` quy định timeout phase dừng
D. `server.connection-timeout` quy định timeout của phase dừng
Đáp án đúng: B

Câu 38. Khi các Actuator health probes được bật, endpoint nào phản ánh khả năng nhận traffic?
A. `/actuator/metrics` cho trạng thái readiness riêng
B. `/actuator/health/liveness` cho trạng thái readiness
C. `/actuator/health` cho trạng thái readiness riêng
D. `/actuator/health/readiness` cho trạng thái readiness
Đáp án đúng: D

Câu 39. Muốn đo số lượng và độ trễ HTTP requests của Spring Boot qua Micrometer, meter nào liên quan?
A. `http.client.requests` ghi các quan sát request HTTP
B. `http.server.requests` ghi các quan sát request HTTP
C. `jvm.threads.live` ghi các quan sát request HTTP
D. `process.cpu.usage` ghi các quan sát request HTTP
Đáp án đúng: B

Câu 40. p95 latency tăng khi truy vấn downstream chậm; loại dữ liệu nào giúp lần ra bước gây trễ?
A. Danh sách bean khởi động nhưng không ghi thời gian xử lý
B. Trace spans nối request với thời gian gọi downstream
C. Thông số build image không gắn theo từng request
D. Chỉ số heap tổng cộng không gắn trace ID request
Đáp án đúng: B
