Bạn giải thích vai trò của Spring Web trong việc xử lý HTTP request và xây dựng giao tiếp giữa các thành phần ứng dụng như thế nào?
Bạn phân biệt Spring MVC với Spring WebFlux theo mô hình thực thi, API lập trình và loại workload phù hợp ra sao?
Bạn đánh giá khi nào chọn Spring MVC cho một REST service có JDBC blocking thay vì chuyển toàn bộ sang WebFlux như thế nào?
Bạn giải thích vì sao sử dụng WebFlux không tự động giúp mọi ứng dụng có throughput cao hơn Spring MVC ra sao?
Bạn mô tả luồng xử lý một HTTP request qua servlet container, DispatcherServlet, controller và response trong Spring MVC như thế nào?
Bạn phân biệt trách nhiệm của DispatcherServlet, HandlerMapping, HandlerAdapter và ViewResolver trong cơ chế Spring MVC ra sao?
Bạn giải thích cách DispatcherServlet chọn một handler phù hợp khi nhiều controller đăng ký các đường dẫn gần giống nhau như thế nào?
Bạn xác định những rủi ro khi cấu hình servlet mapping hoặc context path không khớp với đường dẫn mà client sử dụng ra sao?
Bạn thiết kế phân tách controller, application service và repository để controller không chứa toàn bộ logic nghiệp vụ như thế nào?
Bạn lựa chọn @Controller với @ResponseBody hay @RestController cho từng loại HTTP endpoint theo hợp đồng phản hồi như thế nào?
Bạn phân biệt @RequestMapping ở class và method khi tổ chức nhiều endpoint thuộc cùng một API resource ra sao?
Bạn thiết kế route dùng @GetMapping, @PostMapping, @PutMapping, @PatchMapping và @DeleteMapping dựa trên HTTP semantics như thế nào?
Bạn xác định hành vi khi nhiều handler methods có điều kiện route trùng hoặc nhập nhằng và cách chẩn đoán khi ứng dụng khởi động ra sao?
Bạn phân biệt path variables, query parameters, headers và cookies khi lựa chọn nơi nhận từng loại dữ liệu từ client như thế nào?
Bạn sử dụng @PathVariable để bind identifier và xử lý lỗi khi đoạn path không đúng kiểu dữ liệu mong đợi như thế nào?
Bạn thiết kế @RequestParam với required, defaultValue và collection parameters mà không làm mất ý nghĩa của tham số bị thiếu ra sao?
Bạn phân biệt việc bind @RequestHeader với đọc toàn bộ HttpHeaders khi endpoint cần xác thực một header bắt buộc như thế nào?
Bạn quyết định khi nào dùng @CookieValue và khi nào nên tách xử lý cookie hoặc session vào thành phần bảo mật như thế nào?
Bạn đánh giá ảnh hưởng của trailing slash, URL encoding và các ký tự đặc biệt tới việc khớp route trong các phiên bản Spring như thế nào?
Bạn giải thích mục tiêu của PathPattern matching và những khác biệt cần kiểm tra khi di chuyển từ cấu hình path matcher cũ ra sao?
Bạn thiết kế route có nested resource path mà vẫn tránh lặp identifier hoặc đặt URL theo hành động RPC không cần thiết như thế nào?
Bạn xác định cách giới hạn HTTP methods được hỗ trợ và xử lý phản hồi 405 khi client gọi sai phương thức ra sao?
Bạn phân biệt các điều kiện consumes và produces trong @RequestMapping với Content-Type và Accept headers của HTTP như thế nào?
Bạn xử lý trường hợp client gửi JSON nhưng controller chỉ chấp nhận form data và trả lỗi 415 theo cơ chế nào?
Bạn phân tích một lỗi 406 Not Acceptable do client yêu cầu media type không thể tạo ra từ server như thế nào?
Bạn thiết kế endpoint trả nhiều biểu diễn dữ liệu dựa trên content negotiation mà không phá vỡ hợp đồng API như thế nào?
Bạn giải thích vai trò của HandlerInterceptor và khi nào nên sử dụng nó thay vì Servlet Filter như thế nào?
Bạn phân biệt preHandle, postHandle và afterCompletion của MVC interceptor về thời điểm và loại tác vụ phù hợp ra sao?
Bạn thiết kế correlation ID xuyên qua filter và controller mà không làm rò rỉ dữ liệu trong MDC giữa các request như thế nào?
Bạn đánh giá vì sao logging toàn bộ request body trong filter có thể gây tiêu thụ bộ nhớ và làm lộ dữ liệu nhạy cảm ra sao?
Bạn xác định những xử lý nào thuộc Servlet Filter chain và những xử lý nào nên nằm trong controller advice hoặc service như thế nào?
Bạn giải thích @RequestBody khác @ModelAttribute về nguồn dữ liệu đầu vào và cơ chế chuyển đổi như thế nào?
Bạn mô tả cách HttpMessageConverter chuyển JSON request body thành object Java và tạo response body từ kết quả handler ra sao?
Bạn phân biệt lỗi JSON không hợp lệ với lỗi chuyển đổi một property sang kiểu Java khi điều tra HTTP 400 như thế nào?
Bạn thiết kế DTO cho HTTP request thay vì bind trực tiếp JPA entity để tránh mass assignment và rò rỉ trường nội bộ như thế nào?
Bạn lựa chọn Java record hoặc immutable DTO cho request body theo nhu cầu validation và khả năng tương thích serializer ra sao?
Bạn sử dụng @ModelAttribute khi nhận form fields và xác định trường hợp nào không phù hợp cho JSON REST request như thế nào?
Bạn phân biệt Converter, Formatter và PropertyEditor khi tùy biến chuyển đổi query/path parameters trong Spring MVC ra sao?
Bạn thiết kế Converter cho một domain identifier để mọi controller không phải tự parse cùng một kiểu tham số như thế nào?
Bạn xác định cách cấu hình date/time formatting theo timezone và locale mà không làm sai ý nghĩa timestamp của API như thế nào?
Bạn kiểm tra lỗi binding collection hoặc nested object khi client gửi tên field không đúng cấu trúc DTO như thế nào?
Bạn phân biệt @InitBinder và WebDataBinder với global conversion/validation configuration về phạm vi áp dụng như thế nào?
Bạn thiết kế whitelist các field được phép bind để client không thay đổi các thuộc tính nghiệp vụ bị cấm ra sao?
Bạn giải thích Bean Validation được kích hoạt qua @Valid hoặc @Validated ở controller và liên hệ với các constraint annotations như thế nào?
Bạn phân biệt @NotNull, @NotBlank và @NotEmpty theo giá trị nào nên bị từ chối trong một HTTP request như thế nào?
Bạn thiết kế validation groups cho thao tác tạo mới và cập nhật mà vẫn giữ DTO dễ bảo trì như thế nào?
Bạn xác định cách xử lý nested validation trên danh sách đối tượng con khi request body chứa một aggregate phức tạp ra sao?
Bạn phân biệt BindingResult đặt ngay sau đối tượng được validate với xử lý exception validation tập trung như thế nào?
Bạn đánh giá khi nào method parameter validation khác với validation request body và loại exception cần bắt tùy phiên bản Spring ra sao?
Bạn thiết kế lỗi validation trả danh sách field errors mà không đưa giá trị password hoặc token vào response như thế nào?
Bạn phân biệt kiểm tra cú pháp dữ liệu bằng Bean Validation với kiểm tra invariant nghiệp vụ cần gọi service hoặc database như thế nào?
Bạn xây dựng thông báo lỗi validation nhiều ngôn ngữ bằng MessageSource và locale resolution của HTTP request như thế nào?
Bạn thiết kế test cho request có trường thừa, trường thiếu và giá trị null để xác nhận chính sách deserialization/validation ra sao?
Bạn giải thích vai trò của @ExceptionHandler và @ControllerAdvice trong việc chuẩn hóa phản hồi lỗi HTTP như thế nào?
Bạn phân biệt @RestControllerAdvice với @ControllerAdvice khi API chỉ trả dữ liệu JSON thay vì view như thế nào?
Bạn thiết kế cấu trúc error response có mã lỗi ổn định, message an toàn và correlation ID cho nhiều controller như thế nào?
Bạn sử dụng ProblemDetail hoặc ErrorResponse của Spring Framework để biểu diễn lỗi HTTP theo hợp đồng chung như thế nào?
Bạn phân biệt trả HTTP 400, 401, 403, 404, 409 và 422 theo các trường hợp lỗi đầu vào, quyền hạn hoặc trạng thái nghiệp vụ ra sao?
Bạn xác định khi nào nên trả 500 thay vì biến lỗi lập trình hoặc database bất ngờ thành lỗi 400 cho client như thế nào?
Bạn giải thích cách exception resolver của Spring MVC phối hợp với @ExceptionHandler và response status để tạo phản hồi như thế nào?
Bạn đánh giá những tình huống response đã commit khiến global exception handler không thể thay đổi status hoặc body như thế nào?
Bạn thiết kế xử lý lỗi có nested causes nhưng không đưa stack trace hoặc internal exception message ra HTTP response như thế nào?
Bạn phân biệt domain exception với transport-level HTTP exception để application service không phụ thuộc Servlet API ra sao?
Bạn xác định cách kiểm thử error contract khi request đi qua @ControllerAdvice, filter và handler mapping như thế nào?
Bạn thiết kế API quản lý resource dùng HTTP status 201 và Location header sau khi tạo mới như thế nào?
Bạn phân biệt PUT và PATCH theo ngữ nghĩa thay thế toàn bộ representation và cập nhật một phần dữ liệu như thế nào?
Bạn giải thích idempotency của các HTTP methods và giới hạn khi một POST bị client retry sau timeout như thế nào?
Bạn thiết kế idempotency key cho endpoint tạo thanh toán để không tạo bản ghi trùng khi client gửi lại request ra sao?
Bạn lựa chọn response 202 Accepted với job status endpoint khi xử lý nghiệp vụ chưa thể hoàn thành trong cùng HTTP request như thế nào?
Bạn xác định khi nào trả 204 No Content và khi nào nên trả resource representation sau một cập nhật thành công ra sao?
Bạn thiết kế phân trang endpoint với page, size và sort parameters để kiểm soát thứ tự ổn định và giới hạn tài nguyên như thế nào?
Bạn đánh giá khác biệt giữa offset paging và cursor/keyset paging khi dữ liệu bị cập nhật trong lúc client duyệt nhiều trang như thế nào?
Bạn thiết kế bộ lọc truy vấn có whitelist field/operator để tránh tạo truy vấn database tùy ý từ query parameters như thế nào?
Bạn lựa chọn cách biểu diễn ngày, timezone, decimal và enum trong JSON API để tránh mơ hồ giữa các client như thế nào?
Bạn giải thích vai trò của ETag và If-None-Match trong conditional GET để giảm truyền dữ liệu không thay đổi như thế nào?
Bạn thiết kế cập nhật có điều kiện bằng If-Match hoặc version field để tránh lost update giữa nhiều client như thế nào?
Bạn phân biệt Cache-Control dành cho browser/proxy với application cache tại server khi tối ưu GET endpoint như thế nào?
Bạn xử lý HEAD và OPTIONS requests phù hợp với HTTP contract và CORS preflight như thế nào?
Bạn xác định khi nào CORS là chính sách của browser chứ không phải cơ chế xác thực hoặc phân quyền ở API như thế nào?
Bạn cấu hình CORS theo allowed origins, methods, headers và credentials mà không mở quyền quá rộng như thế nào?
Bạn phân biệt CORS policy ở Spring MVC với cấu hình Spring Security filter chain để tránh xung đột hoặc xử lý preflight sai ra sao?
Bạn đánh giá rủi ro CSRF khi ứng dụng sử dụng cookie-based authentication so với bearer token gửi qua Authorization header như thế nào?
Bạn thiết kế kiểm soát truy cập theo tenant ID lấy từ security context thay vì tin trực tiếp query parameter do client gửi như thế nào?
Bạn bảo vệ API trước header spoofing khi ứng dụng đứng sau reverse proxy và dùng Forwarded hoặc X-Forwarded-* headers như thế nào?
Bạn xác định cơ chế giới hạn request body và file upload để tránh client chiếm bộ nhớ hoặc ổ đĩa của server như thế nào?
Bạn thiết kế upload multipart/form-data với @RequestPart và @RequestParam theo hợp đồng metadata và file content như thế nào?
Bạn kiểm tra MIME type, kích thước và nội dung file tải lên mà không chỉ tin Content-Type do client khai báo như thế nào?
Bạn tránh path traversal khi client gửi filename chứa dấu phân cách thư mục hoặc chuỗi nguy hiểm như thế nào?
Bạn thiết kế endpoint download file trả Content-Disposition và Content-Type chính xác mà không lộ đường dẫn nội bộ như thế nào?
Bạn phân biệt trả byte array với streaming response cho file lớn theo mức sử dụng RAM và phản hồi khi client hủy kết nối như thế nào?
Bạn giải thích vai trò của Servlet async processing trong Spring MVC khi controller trả Callable hoặc DeferredResult như thế nào?
Bạn phân biệt Callable và DeferredResult theo nơi thực thi công việc và cách hoàn tất HTTP response bất đồng bộ như thế nào?
Bạn đánh giá vì sao async MVC giải phóng servlet request thread nhưng không biến code JDBC blocking thành nonblocking I/O ra sao?
Bạn thiết kế timeout và kết quả fallback cho DeferredResult khi một downstream không phản hồi trước deadline như thế nào?
Bạn xác định cách xử lý exception phát sinh trong Callable so với exception ném trước khi request chuyển sang chế độ async như thế nào?
Bạn sử dụng WebAsyncTask khi cần cấu hình timeout hoặc executor riêng cho một Callable trong Spring MVC như thế nào?
Bạn phân biệt StreamingResponseBody với gửi toàn bộ response body đã buffer khi cần stream file hoặc dữ liệu lớn ra sao?
Bạn thiết kế SSE endpoint trong MVC với SseEmitter và xử lý emitter timeout, lỗi kết nối hoặc client disconnect như thế nào?
Bạn phân tích rủi ro giữ quá nhiều SseEmitter đang mở khi client kết nối dài hạn và server có giới hạn tài nguyên ra sao?
Bạn xác định cách duy trì correlation ID và SecurityContext khi controller MVC chuyển công việc sang TaskExecutor như thế nào?
Bạn kiểm thử timeout và xử lý exception của DeferredResult bằng MockMvc mà không dựa vào thời gian chờ ngẫu nhiên như thế nào?
Bạn giải thích reactive streams và vai trò của Publisher, Subscriber, demand và backpressure trong Spring WebFlux như thế nào?
Bạn phân biệt Mono và Flux theo số lượng tín hiệu dữ liệu và cách biểu diễn lỗi hoặc completion ra sao?
Bạn mô tả luồng xử lý một HTTP request qua WebHandler, WebFilter và handler trong Spring WebFlux như thế nào?
Bạn so sánh annotated controllers với functional endpoints dùng RouterFunction và HandlerFunction trong WebFlux như thế nào?
Bạn thiết kế functional route với predicate theo path và HTTP method mà vẫn giữ validation và error handling rõ ràng như thế nào?
Bạn phân biệt ServerRequest và ServerResponse của functional WebFlux endpoints với @RequestBody và ResponseEntity của annotated controllers ra sao?
Bạn giải thích cơ chế WebFlux sử dụng codecs để decode/encode HTTP messages và các rủi ro khi payload quá lớn như thế nào?
Bạn xác định vì sao gọi block trên event-loop có thể khiến nhiều request WebFlux bị nghẽn dù CPU chưa bão hòa như thế nào?
Bạn thiết kế ranh giới dùng boundedElastic khi phải tích hợp thư viện blocking vào reactive pipeline mà chưa thể thay thế nó ra sao?
Bạn phân biệt subscribeOn và publishOn theo ảnh hưởng tới thread thực thi trong một WebFlux request như thế nào?
Bạn đánh giá trường hợp nào cần tránh tự gọi subscribe trong controller hoặc service trả Mono/Flux cho WebFlux như thế nào?
Bạn thiết kế xử lý lỗi với onErrorResume, onErrorMap hoặc global error handler mà không nuốt lỗi nghiệp vụ quan trọng ra sao?
Bạn phân biệt WebExceptionHandler của WebFlux với @RestControllerAdvice ở annotated controllers theo phạm vi bắt lỗi như thế nào?
Bạn xác định cách propagation của Reactor Context khác ThreadLocal khi cần mang trace ID hoặc danh tính người dùng qua pipeline như thế nào?
Bạn thiết kế WebFilter thêm thông tin request vào Reactor Context mà không dùng mutable singleton field như thế nào?
Bạn phân tích các trường hợp backpressure không tự động bảo vệ database hoặc HTTP client khi upstream tạo request nhanh hơn downstream như thế nào?
Bạn lựa chọn flatMap concurrency và prefetch phù hợp để giới hạn số lời gọi downstream đồng thời trong reactive service ra sao?
Bạn thiết kế timeout tổng thể cho một WebFlux endpoint đang kết hợp nhiều publishers thay vì chỉ timeout từng lời gọi riêng như thế nào?
Bạn xử lý cancellation khi client đóng kết nối giữa lúc Flux đang stream để tài nguyên hoặc subscription được giải phóng như thế nào?
Bạn đánh giá rủi ro giữ DataBuffer sau khi decode hoặc tự thao tác byte buffer mà không release đúng cách như thế nào?
Bạn thiết kế xử lý file upload hoặc streaming request body trong WebFlux mà không buffer toàn bộ nội dung lên heap ra sao?
Bạn so sánh Server-Sent Events với WebSocket theo hướng truyền dữ liệu, khả năng tương thích client và tính hai chiều như thế nào?
Bạn kiểm thử một SSE Flux có heartbeat hoặc sự kiện liên tục mà không đợi stream kết thúc như thế nào?
Bạn quyết định khi nào dùng WebFlux với R2DBC hoặc reactive driver và khi nào Spring MVC với JDBC vẫn dễ vận hành hơn ra sao?
Bạn phân tích sự khác nhau giữa lỗi timeout, cancellation và downstream 5xx trong một reactive request chain như thế nào?
Bạn giải thích vai trò của WebClient như HTTP client bất đồng bộ và khác biệt với các client blocking truyền thống ra sao?
Bạn thiết kế cấu hình WebClient.Builder với baseUrl, default headers và codecs để gọi một downstream HTTP service như thế nào?
Bạn phân biệt retrieve với exchangeToMono hoặc exchangeToFlux khi cần kiểm soát status, headers và body ở mức chi tiết ra sao?
Bạn xử lý lỗi HTTP 4xx và 5xx từ WebClient bằng onStatus mà không làm mất nội dung lỗi cần thiết cho chẩn đoán như thế nào?
Bạn xác định khi nào bodyToMono, bodyToFlux và toEntity phù hợp với contract của downstream API như thế nào?
Bạn thiết kế WebClient gọi API trả danh sách lớn và xử lý dữ liệu theo luồng mà không giữ toàn bộ kết quả trong RAM ra sao?
Bạn phân biệt connect timeout, response timeout và timeout trong Reactor pipeline theo điểm chờ và tác động tới request như thế nào?
Bạn lựa chọn connection pooling, max connections và pending acquire timeout cho WebClient dựa trên giới hạn downstream ra sao?
Bạn đánh giá nguy cơ gọi WebClient.block trong event-loop WebFlux và cách tổ chức adapter khi consumer là ứng dụng MVC blocking như thế nào?
Bạn thiết kế retry có backoff cho WebClient chỉ trên lỗi tạm thời và phương thức HTTP an toàn để không gửi trùng side effect như thế nào?
Bạn phân biệt retry do mất kết nối trước khi request được gửi với trường hợp response bị mất sau khi downstream đã xử lý request ra sao?
Bạn xây dựng circuit breaker hoặc bulkhead xung quanh WebClient để giới hạn lỗi dây chuyền khi downstream chậm như thế nào?
Bạn xử lý status 429 cùng Retry-After header khi downstream áp dụng rate limit cho một nhóm client như thế nào?
Bạn xác định cách truyền Authorization header khi gọi dịch vụ khác mà không vô tình chuyển token người dùng sang domain không tin cậy như thế nào?
Bạn thiết kế ExchangeFilterFunction cho logging/tracing và bảo vệ credentials, cookies hoặc request body nhạy cảm như thế nào?
Bạn phân biệt HTTP client filters với Servlet Filter hoặc WebFilter ở phía server theo phạm vi thực thi như thế nào?
Bạn xử lý redirects trong HTTP client để tránh SSRF hoặc gửi nhầm Authorization header tới hostname ngoài allowlist như thế nào?
Bạn thiết kế WebClient gọi endpoint trả multipart hoặc upload file qua BodyInserters mà vẫn kiểm soát kích thước dữ liệu như thế nào?
Bạn đánh giá ảnh hưởng của maxInMemorySize khi decode một response lớn và phương án stream hoặc từ chối payload ra sao?
Bạn xác định khi nào nên reuse WebClient instance thay vì tạo HTTP client và connection pool mới cho mỗi request như thế nào?
Bạn kiểm thử WebClient bằng mock HTTP server để xác minh URL, headers, payload, timeout và mapping lỗi thực tế như thế nào?
Bạn giải thích Spring HTTP Service Client cho phép mô tả một HTTP API bằng Java interface có annotations như thế nào?
Bạn phân biệt interface có @HttpExchange với các method @GetExchange hoặc @PostExchange theo cách công bố contract như thế nào?
Bạn thiết kế HTTP Service interface truyền path variables, query params, headers và request body theo đúng downstream API như thế nào?
Bạn mô tả vai trò của HttpServiceProxyFactory trong việc tạo proxy client từ một interface được khai báo như thế nào?
Bạn lựa chọn WebClientAdapter hay RestClientAdapter cho HttpServiceProxyFactory theo mô hình reactive và blocking như thế nào?
Bạn phân biệt Spring RestClient với WebClient khi xây dựng HTTP Service Client và đánh giá yêu cầu phiên bản Spring Framework ra sao?
Bạn xác định giới hạn hỗ trợ return types và blocking/reactive behavior của HTTP interface tùy client adapter như thế nào?
Bạn thiết kế chính sách error mapping và timeout ở adapter/client thay vì nhúng retry tùy ý vào từng interface method như thế nào?
Bạn quản lý base URL và credentials của nhiều downstream clients mà không đặt dữ liệu môi trường trong HTTP interface như thế nào?
Bạn đánh giá cách version một HTTP Service interface khi downstream thêm trường mới hoặc đổi HTTP status contract như thế nào?
Bạn kiểm thử một HTTP Service proxy bằng mock server để bảo đảm annotations tạo đúng HTTP method, path và serialized body như thế nào?
Bạn so sánh HTTP Service Client với viết trực tiếp WebClient calls về khả năng tái sử dụng, quan sát lỗi và maintainability ra sao?
Bạn giải thích quá trình WebSocket HTTP upgrade và ý nghĩa của kết nối hai chiều lâu dài trong ứng dụng Spring như thế nào?
Bạn phân biệt WebSocket với HTTP polling và SSE theo yêu cầu truyền dữ liệu thời gian thực như thế nào?
Bạn xác định khi nào nên sử dụng WebSocketHandler cấp thấp và khi nào dùng STOMP messaging abstractions của Spring như thế nào?
Bạn mô tả vai trò của TextWebSocketHandler và BinaryWebSocketHandler khi ứng dụng cần xử lý hai loại payload khác nhau như thế nào?
Bạn thiết kế endpoint WebSocket kiểm tra Origin và quyền người dùng trong handshake để hạn chế kết nối không hợp lệ ra sao?
Bạn phân biệt xác thực ở HTTP handshake với việc kiểm tra quyền trên từng STOMP destination hoặc message như thế nào?
Bạn xử lý session lifecycle của WebSocket khi client mất mạng, reconnect hoặc đóng kết nối không sạch như thế nào?
Bạn thiết kế heartbeat và idle timeout để phát hiện kết nối WebSocket chết mà không tiêu tốn tài nguyên quá mức ra sao?
Bạn phân tích rủi ro lưu danh sách WebSocketSession trong một singleton mutable map khi số kết nối tăng và có nhiều thread gửi message như thế nào?
Bạn lựa chọn cơ chế gửi message an toàn khi nhiều tác vụ đồng thời muốn ghi vào cùng một WebSocket session như thế nào?
Bạn giải thích vai trò của @EnableWebSocketMessageBroker, @MessageMapping và @SendTo khi dùng Spring STOMP messaging như thế nào?
Bạn phân biệt application destination prefix với broker destination prefix trong luồng STOMP từ client tới server như thế nào?
Bạn thiết kế subscription theo user destination để một thông báo riêng tư không bị phát nhầm tới toàn bộ người dùng ra sao?
Bạn so sánh simple in-memory message broker với STOMP broker relay khi ứng dụng được triển khai nhiều instance như thế nào?
Bạn xác định hạn chế của simple broker khi cần lưu thông điệp, replay hoặc giao nhận đảm bảo sau restart ra sao?
Bạn xử lý sự kiện reconnect của STOMP client để tránh subscription trùng hoặc trạng thái ứng dụng bị sai như thế nào?
Bạn lựa chọn chính sách giới hạn kích thước frame, message và send buffer để bảo vệ WebSocket server khỏi client quá tải ra sao?
Bạn thiết kế cách quan sát số session đang mở, tần suất reconnect và số message thất bại trên WebSocket như thế nào?
Bạn kiểm thử WebSocket handshake và STOMP messaging end-to-end mà không coi việc tạo connection thành công là đã xác minh phân quyền ra sao?
Bạn phân biệt việc bảo vệ HTTP endpoints, WebSocket handshake và STOMP message authorization trong kiến trúc bảo mật như thế nào?
Bạn giải thích MockMvc mô phỏng Spring MVC request pipeline mà không cần khởi động HTTP server thực như thế nào?
Bạn lựa chọn MockMvc standalone setup hay webApplicationContextSetup tùy cần kiểm tra controller độc lập hoặc toàn bộ cấu hình MVC như thế nào?
Bạn thiết kế MockMvc test cho route, validation, @ControllerAdvice và JSON response status cùng headers như thế nào?
Bạn sử dụng MockMvc asyncDispatch để xác nhận kết quả cuối của Callable hoặc DeferredResult thay vì chỉ trạng thái bắt đầu async như thế nào?
Bạn phân biệt WebTestClient bindToApplicationContext với bindToServer khi kiểm thử WebFlux bằng mock runtime hoặc server thật ra sao?
Bạn kiểm thử reactive response streaming bằng StepVerifier hoặc WebTestClient mà không buộc phải thu hết Flux vào một List như thế nào?
Bạn thiết kế integration test cho multipart upload hoặc file download để kiểm tra cả content headers và nội dung byte chính xác ra sao?
Bạn xây dựng test HTTP Service Client khi downstream trả 429, 5xx hoặc body sai schema để xác minh cách ánh xạ lỗi và chính sách retry như thế nào?
Bạn xác định cách kiểm thử timeout, retry và cancellation của WebClient một cách xác định mà không dựa vào Thread.sleep ra sao?
Bạn thiết kế contract tests cho REST API để phát hiện thay đổi không tương thích ở status codes, payload fields và content negotiation như thế nào?
Bạn kiểm tra CORS preflight, thiếu authentication và quyền truy cập tenant trong HTTP integration test theo những trường hợp nào?
Bạn phân biệt kiểm thử Servlet stack với reactive WebFlux stack khi chọn MockMvc, WebTestClient hoặc server thật như thế nào?
Bạn thiết kế test WebSocket nhiều client để phát hiện gửi message sai user destination hoặc xử lý sai khi reconnect như thế nào?
Bạn lựa chọn log, metrics và distributed tracing nào để theo dõi latency và lỗi từ HTTP server qua WebClient tới downstream như thế nào?
Bạn phân tích sự cố p99 HTTP latency tăng dù CPU thấp bằng cách kiểm tra thread pool, connection pool và downstream timeouts như thế nào?
Bạn xác định cách cấu hình graceful shutdown, request draining và hủy reactive subscriptions để giảm lỗi trong quá trình rollout như thế nào?
Bạn thiết kế chiến lược giới hạn số kết nối WebSocket và HTTP requests đồng thời để không làm kiệt tài nguyên khi tải tăng đột biến như thế nào?
Bạn đề xuất kiến trúc Spring Web cho hệ thống có REST API, WebFlux streaming, HTTP Service Clients và WebSocket với hợp đồng rõ ràng, bảo mật, kiểm thử và observability như thế nào?
