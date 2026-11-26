Bạn mô tả quá trình Spring Boot khởi động một ứng dụng web và tạo máy chủ nhúng để tiếp nhận HTTP request như thế nào?
Bạn phân biệt máy chủ nhúng trong Spring Boot với việc đóng gói WAR để triển khai trên servlet container bên ngoài ra sao?
Bạn giải thích cách Spring Boot xác định ứng dụng thuộc loại Servlet, Reactive hay Non-Web từ classpath và cấu hình như thế nào?
Bạn phân biệt ServletWebServerApplicationContext với ReactiveWebServerApplicationContext về cách tạo và quản lý web server ra sao?
Bạn xác định những thành phần nào chịu trách nhiệm khởi tạo và cấu hình embedded Tomcat trong ứng dụng Spring MVC như thế nào?
Bạn so sánh embedded Tomcat, Jetty và Undertow khi lựa chọn servlet container cho một ứng dụng Spring Boot ra sao?
Bạn giải thích khi nào Spring Boot sử dụng Reactor Netty làm HTTP server cho một ứng dụng WebFlux như thế nào?
Bạn đánh giá những tiêu chí nào khi thay đổi embedded server nhưng vẫn giữ nguyên logic controller nghiệp vụ?
Bạn phân biệt quá trình ApplicationContext được refresh với thời điểm HTTP connector bắt đầu chấp nhận kết nối như thế nào?
Bạn xác minh cổng thực tế được cấp khi cấu hình server.port bằng 0 trong kiểm thử hoặc triển khai ra sao?
Bạn giải thích vai trò của WebServerInitializedEvent khi cần biết địa chỉ và cổng của web server đã khởi tạo như thế nào?
Bạn cấu hình server.address và server.port khi dịch vụ chỉ được phép lắng nghe trên một giao diện mạng cụ thể ra sao?
Bạn phân biệt context path của ứng dụng Servlet với base path của ứng dụng WebFlux khi tổ chức URL ra sao?
Bạn thiết kế cách tách cổng quản trị Actuator khỏi cổng phục vụ nghiệp vụ khi có yêu cầu cách ly truy cập như thế nào?
Bạn xử lý sự cố cổng bị chiếm dụng khi nhiều ứng dụng Spring Boot cùng khởi động trên một máy như thế nào?
Bạn kiểm tra một web server được tạo thành công nhưng ứng dụng chưa sẵn sàng nhận traffic bằng những trạng thái nào?
Bạn mô tả đường đi của HTTP request từ socket ở embedded servlet container tới DispatcherServlet trong Spring MVC như thế nào?
Bạn giải thích vai trò của Filter trong Servlet pipeline trước và sau khi request được DispatcherServlet xử lý ra sao?
Bạn phân biệt Filter với HandlerInterceptor trong Spring MVC về thời điểm áp dụng và khả năng truy cập handler như thế nào?
Bạn mô tả cách DispatcherServlet kết hợp HandlerMapping và HandlerAdapter để gọi đúng controller như thế nào?
Bạn xác định thứ tự thực thi và cơ chế dừng sớm của filter chain khi một lớp bảo mật từ chối request ra sao?
Bạn giải thích sự khác biệt giữa @Controller và @RestController khi Spring MVC hình thành HTTP response như thế nào?
Bạn phân tích cách Spring MVC lựa chọn phương thức controller dựa trên URL, HTTP method, headers và content type ra sao?
Bạn thiết kế cơ chế xử lý lỗi tập trung bằng @ControllerAdvice để trả trạng thái HTTP và nội dung lỗi nhất quán như thế nào?
Bạn phân biệt ngoại lệ phát sinh trong servlet filter với ngoại lệ phát sinh trong controller khi cấu hình error handling như thế nào?
Bạn giải thích vai trò của HttpMessageConverter khi Spring MVC chuyển đổi JSON request body thành đối tượng Java như thế nào?
Bạn xác định nguyên nhân một endpoint trả HTTP 415 hoặc 406 khi client khai báo Content-Type và Accept không phù hợp ra sao?
Bạn kiểm thử cách Spring MVC xử lý charset, ký tự Unicode và nội dung JSON lỗi định dạng như thế nào?
Bạn phân biệt dữ liệu từ path variable, query parameter, header và request body trong quá trình binding vào tham số controller ra sao?
Bạn thiết kế giới hạn kích thước request body và tải tệp multipart để tránh việc client làm cạn bộ nhớ như thế nào?
Bạn kiểm soát thao tác đọc file upload theo kiểu streaming hoặc ghi ra đĩa tạm khi tệp có kích thước lớn ra sao?
Bạn giải thích cách cấu hình bộ giải mã và serializer ảnh hưởng đến định dạng số, ngày giờ và dữ liệu đa hình trong JSON ra sao?
Bạn phân tích nguyên nhân một API trả dữ liệu JSON không đúng định dạng sau khi thay đổi cấu hình Jackson như thế nào?
Bạn so sánh hiệu ứng của response compression với độ trễ, CPU và băng thông trong một ứng dụng HTTP có payload lớn ra sao?
Bạn xác định cách kiểm tra header Content-Encoding và Accept-Encoding để bảo đảm nén response được thương lượng đúng như thế nào?
Bạn phân biệt Servlet xử lý đồng bộ với Servlet async request processing khi một request cần chờ tác vụ lâu ra sao?
Bạn sử dụng Callable hoặc DeferredResult trong Spring MVC để giải phóng servlet request thread trong thời gian chờ như thế nào?
Bạn phân tích những rủi ro khi gọi API chặn lâu trong một controller MVC đang chịu tải cao như thế nào?
Bạn giải thích vì sao tăng số servlet threads không nhất thiết cải thiện throughput nếu bottleneck nằm ở database connection pool ra sao?
Bạn lựa chọn các giới hạn thread, connection và hàng đợi chờ của embedded servlet server theo đặc điểm workload như thế nào?
Bạn phân biệt số kết nối TCP đang mở với số request được xử lý đồng thời khi HTTP keep-alive được bật như thế nào?
Bạn đánh giá tác động của keep-alive timeout tới việc tái sử dụng kết nối và khả năng tiêu thụ tài nguyên của server ra sao?
Bạn giải thích ý nghĩa của accept backlog khi các kết nối mới đến nhanh hơn khả năng server chấp nhận như thế nào?
Bạn chẩn đoán tình huống request chậm do servlet thread pool bão hòa nhưng CPU của máy vẫn còn thấp như thế nào?
Bạn thiết kế chiến lược giới hạn concurrency để bảo vệ dịch vụ khi nhiều request chậm cùng chiếm giữ tài nguyên như thế nào?
Bạn so sánh xử lý blocking I/O trong Spring MVC với event-loop và non-blocking I/O trong WebFlux theo vòng đời request như thế nào?
Bạn mô tả đường đi của một HTTP request trong Spring WebFlux từ HTTP server tới WebHandler và handler nghiệp vụ ra sao?
Bạn phân biệt mô hình annotated controller với functional routing qua RouterFunction trong Spring WebFlux như thế nào?
Bạn giải thích vai trò của WebFilter so với servlet Filter khi áp dụng logging hoặc xác thực trong pipeline reactive như thế nào?
Bạn phân biệt ServerWebExchange với HttpServletRequest khi cần truy cập HTTP request và response metadata như thế nào?
Bạn xác định thời điểm Spring WebFlux serialize Mono hoặc Flux thành HTTP response và khi nào response được xem là hoàn tất ra sao?
Bạn giải thích vì sao việc gọi block() trên Netty event-loop có thể làm suy giảm khả năng phục vụ đồng thời như thế nào?
Bạn thiết kế cách tích hợp một thư viện blocking legacy vào WebFlux mà không chiếm giữ thread event-loop như thế nào?
Bạn phân biệt publishOn với subscribeOn trong việc lựa chọn scheduler cho một phần pipeline WebFlux ra sao?
Bạn thiết kế bộ giới hạn concurrency và timeout cho luồng WebFlux có nhiều lời gọi tới dịch vụ ngoài như thế nào?
Bạn phân biệt xử lý Mono rỗng, Mono lỗi và Mono trả dữ liệu khi xây dựng HTTP status trong một controller reactive ra sao?
Bạn xử lý lỗi trong WebFlux qua @RestControllerAdvice hoặc cơ chế WebExceptionHandler tùy lớp phát sinh lỗi như thế nào?
Bạn phân biệt HttpMessageConverter của Spring MVC với HttpMessageReader và HttpMessageWriter trong WebFlux ra sao?
Bạn xác định vai trò của codec và DataBuffer trong WebFlux khi tiếp nhận hoặc phát dữ liệu theo luồng như thế nào?
Bạn lựa chọn giới hạn kích thước bộ đệm cho codec để tránh lỗi khi JSON body vượt mức cho phép như thế nào?
Bạn điều tra một lỗi DataBufferLimitException và thiết kế cách streaming hoặc điều chỉnh giới hạn theo nhu cầu như thế nào?
Bạn giải thích tại sao việc giữ DataBuffer quá lâu hoặc không giải phóng đúng có thể làm rò rỉ bộ nhớ với một số HTTP runtime như thế nào?
Bạn so sánh cách xử lý upload hoặc download tệp lớn trên Servlet và Reactive stack theo sử dụng bộ nhớ như thế nào?
Bạn xác định khi nào nên trả Flux dạng Server-Sent Events thay vì một response JSON hoàn chỉnh như thế nào?
Bạn thiết kế kiểm thử HTTP streaming để xác minh client nhận từng phần dữ liệu và có thể hủy subscription ra sao?
Bạn phân biệt backpressure trong Reactor pipeline với việc điều tiết tốc độ đọc ghi qua giao thức HTTP và TCP như thế nào?
Bạn kiểm tra hành vi khi một HTTP streaming client đọc dữ liệu quá chậm để tránh tích tụ bộ đệm vô hạn ra sao?
Bạn đánh giá khi nào WebFlux phù hợp hơn MVC và khi nào chuyển sang WebFlux không cải thiện hiệu năng như kỳ vọng?
Bạn thiết kế phép đo so sánh MVC và WebFlux ở cùng chức năng, cùng dependency và cùng mức tải để tránh kết luận sai như thế nào?
Bạn phân tích tác động của các thư viện database hoặc HTTP client blocking đối với lợi ích của WebFlux như thế nào?
Bạn xác định rủi ro khi cùng đưa Spring MVC và WebFlux starter lên classpath mà không hiểu web application type được chọn ra sao?
Bạn mô tả cách HTTP/1.1 keep-alive và HTTP/2 multiplexing ảnh hưởng đến quản lý kết nối và đồng thời xử lý request như thế nào?
Bạn kiểm tra khả năng hỗ trợ HTTP/2 của embedded server và cấu hình TLS trước khi bật giao thức trong production như thế nào?
Bạn giải thích cơ chế TLS handshake khác gì với xử lý HTTP request ở các lớp ứng dụng Spring Boot ra sao?
Bạn thiết kế cấu hình certificate, private key và trust material cho HTTPS connector mà không nhúng secret vào mã nguồn như thế nào?
Bạn xác định trường hợp nào cần TLS kết thúc tại reverse proxy và trường hợp nào cần mã hóa tiếp tới embedded server ra sao?
Bạn mô tả cách cấu hình mTLS khi ứng dụng Spring Boot phải xác thực danh tính client kết nối trực tiếp như thế nào?
Bạn thiết kế quy trình xoay vòng certificate mà hạn chế gián đoạn khi nhiều instance đang phục vụ request ra sao?
Bạn xử lý sự cố browser cảnh báo certificate không hợp lệ dù backend API vẫn trả nội dung đúng như thế nào?
Bạn phân biệt request scheme thực tế tại proxy với scheme mà Spring Boot nhìn thấy khi TLS đã được kết thúc ở upstream như thế nào?
Bạn giải thích vai trò của X-Forwarded-For, X-Forwarded-Proto và Forwarded khi request đi qua reverse proxy ra sao?
Bạn cấu hình xử lý forwarded headers để ứng dụng tạo redirect URL và secure cookie chính xác phía sau load balancer như thế nào?
Bạn đánh giá nguy cơ tin tưởng các forwarded headers do client không đáng tin cậy tự gửi và cách hạn chế như thế nào?
Bạn điều tra trường hợp redirect HTTPS bị lặp vòng khi reverse proxy và Spring Boot diễn giải scheme khác nhau ra sao?
Bạn thiết kế cách lưu và dùng client IP cho audit hoặc rate limiting khi phía trước có nhiều lớp proxy ra sao?
Bạn phân biệt việc load balancer phân phối kết nối với việc ứng dụng lưu trạng thái phiên người dùng theo từng instance như thế nào?
Bạn giải thích vòng đời HttpSession của Servlet trong Spring MVC khi request đầu tiên tạo session và cookie được gửi ra sao?
Bạn thiết kế quy tắc cookie HttpOnly, Secure và SameSite phù hợp khi ứng dụng phục vụ qua HTTPS và có luồng đăng nhập ra sao?
Bạn phân biệt session timeout, cookie expiration và invalidation khi người dùng đăng xuất khỏi một ứng dụng web như thế nào?
Bạn đánh giá rủi ro session fixation và thiết kế biện pháp đổi session identifier sau khi xác thực như thế nào?
Bạn lựa chọn lưu HttpSession nội bộ hay sử dụng Spring Session với một kho trạng thái dùng chung khi mở rộng nhiều replica ra sao?
Bạn xử lý sự cố một người dùng bị mất trạng thái đăng nhập sau khi load balancer chuyển request sang node khác như thế nào?
Bạn giải thích cơ chế WebSession trong WebFlux khác gì với HttpSession ở servlet stack về cách truy cập bất đồng bộ ra sao?
Bạn thiết kế session management cho API stateless để không vô tình tạo session với mọi request như thế nào?
Bạn phân tích mối liên hệ giữa cookie-based authentication, CORS và CSRF protection trong một ứng dụng web ra sao?
Bạn xác định cơ chế cấu hình CORS phù hợp khi frontend và backend hoạt động trên hai origin khác nhau như thế nào?
Bạn kiểm tra thứ tự filter chain khiến CORS preflight bị từ chối trước khi request tới controller như thế nào?
Bạn thiết kế giới hạn header size, query string và request body để giảm nguy cơ bị khai thác bằng request quá lớn ra sao?
Bạn xác định hành vi cần có khi client liên tục gửi HTTP request vượt giới hạn tài nguyên của server như thế nào?
Bạn lựa chọn timeout đọc request, timeout xử lý nghiệp vụ và timeout upstream để tránh một giới hạn làm che giấu giới hạn khác như thế nào?
Bạn phân tích sự khác biệt giữa connect timeout, read timeout và idle timeout trong một luồng HTTP nhiều hop như thế nào?
Bạn thiết kế cơ chế rate limiting ở reverse proxy hoặc ứng dụng và xác định các tín hiệu cần theo dõi khi hạn chế lưu lượng ra sao?
Bạn xử lý tình huống client gửi request chậm kéo dài nhằm giữ connection và tiêu thụ tài nguyên server như thế nào?
Bạn quyết định cách cấu hình maximum connections, worker threads và response queue dựa trên stress test theo tiêu chí nào?
Bạn mô tả cách Actuator health, readiness và liveness giúp điều phối lưu lượng đến nhiều instance Spring Boot ra sao?
Bạn phân biệt ứng dụng đã mở cổng HTTP với ứng dụng thực sự có thể phục vụ yêu cầu nghiệp vụ như thế nào?
Bạn thiết kế health check cho phụ thuộc database để tránh khiến lỗi tạm thời biến thành vòng lặp restart liên tục ra sao?
Bạn xác định các metrics về request count, error rate, latency và active connections cần thu thập từ web runtime như thế nào?
Bạn sử dụng Micrometer để phân tích p50, p95 và p99 latency của endpoint thay vì chỉ theo dõi thời gian trung bình ra sao?
Bạn thiết kế distributed tracing để liên kết request HTTP qua Spring Boot, database và một dịch vụ upstream như thế nào?
Bạn phân biệt thời gian chờ tại reverse proxy với thời gian Spring Boot xử lý request khi số liệu latency không khớp nhau ra sao?
Bạn phân tích một tình huống HTTP 502 hoặc 504 từ gateway trong khi ứng dụng Spring Boot không ghi nhận lỗi tương ứng như thế nào?
Bạn sử dụng access log của embedded server kết hợp application log và trace ID để xác định request bị thất bại tại bước nào ra sao?
Bạn xác định các chỉ số nào cho thấy event-loop của Reactor Netty đang bị blocking và cách kiểm tra giả thuyết như thế nào?
Bạn chẩn đoán lỗi connection pool cạn trên server hoặc HTTP client khi lượng request đồng thời tăng cao như thế nào?
Bạn phân biệt bottleneck CPU, servlet threads, event loop và database pool trong kết quả load test dựa trên những biểu hiện nào?
Bạn thiết kế benchmark để đo throughput, độ trễ, tỷ lệ lỗi và mức dùng bộ nhớ của web runtime theo nhiều cấp tải ra sao?
Bạn đánh giá ảnh hưởng của warm-up, connection reuse và phân phối kích thước payload tới kết quả benchmark như thế nào?
Bạn xây dựng cảnh báo khi tỷ lệ HTTP 5xx tăng mà không tạo quá nhiều cảnh báo từ các lỗi 4xx do client gây ra như thế nào?
Bạn thiết kế cơ chế thu thập lỗi serialization, quá hạn timeout và client disconnect để phân loại nguyên nhân suy giảm chất lượng dịch vụ ra sao?
Bạn giải thích graceful shutdown của embedded web server có ý nghĩa gì với kết nối mới và request đang được xử lý như thế nào?
Bạn cấu hình server.shutdown=graceful và thời hạn chờ phù hợp với thời lượng request dài nhất của ứng dụng ra sao?
Bạn mô tả cách readiness chuyển sang từ chối lưu lượng và cách load balancer ngừng gửi request tới instance sắp dừng như thế nào?
Bạn phối hợp SIGTERM, termination grace period và thời gian ngừng gửi traffic trong Kubernetes để giảm lỗi khi rolling deployment ra sao?
Bạn xử lý request đang xử lý quá lâu khi vượt ngân sách graceful shutdown và cân nhắc khả năng hủy như thế nào?
Bạn phân biệt dừng web server với dừng background task, scheduler và datasource trong thứ tự đóng ApplicationContext ra sao?
Bạn lựa chọn cách đóng WebSocket, SSE và HTTP streaming connection khi instance sắp được thay thế như thế nào?
Bạn thiết kế chiến lược retry và idempotency phía client để hạn chế trùng giao dịch khi connection bị cắt đúng lúc server trả response ra sao?
Bạn kiểm thử graceful shutdown khi ứng dụng đang xử lý upload lớn, request streaming và truy vấn database như thế nào?
Bạn xác định lý do một Spring Boot process không kết thúc dù HTTP listener đã ngừng hoạt động bằng những bước kiểm tra nào?
Bạn xây dựng integration test dùng cổng ngẫu nhiên để xác minh filter, controller, exception handler và HTTP response thực tế như thế nào?
Bạn kiểm thử WebFlux HTTP endpoint bằng WebTestClient để xác minh streaming, status và cancellation như thế nào?
Bạn phân biệt MockMvc test với kiểm thử chạy embedded servlet server thật khi cần phát hiện lỗi connector và TLS ra sao?
Bạn thiết kế bài kiểm thử integration cho ứng dụng sau reverse proxy nhằm xác minh forwarded headers, redirect và secure cookie như thế nào?
Bạn mô phỏng client chậm, payload quá lớn và nhiều kết nối idle để kiểm tra khả năng chống cạn tài nguyên của web server ra sao?
Bạn điều tra sự cố production khi số lượng thread tăng cao, CPU thấp và p99 latency tăng bằng lộ trình kiểm tra nào?
Bạn đề xuất kiến trúc và cấu hình web runtime Spring Boot cho hệ thống có REST API, streaming, TLS qua proxy và yêu cầu shutdown không gián đoạn như thế nào?
