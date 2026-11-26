Câu 01. Trong Spring MVC, thành phần nào là front controller nhận request rồi điều phối đến handler?
A. `HandlerInterceptor` chạy callback quanh handler MVC
B. `HttpMessageConverter` chuyển dữ liệu HTTP thành object
C. `ViewResolver` chọn template để hiển thị HTML response
D. `DispatcherServlet` phân phối request đến MVC handler
Đáp án đúng: D

Câu 02. `@RestController` ở Spring MVC tương đương cách kết hợp annotation nào?
A. `@Configuration` cùng `@Bean` để định nghĩa handler
B. `@Controller` cùng `@ResponseStatus` cho HTTP status
C. `@Controller` cùng `@ResponseBody` cho response body
D. `@ControllerAdvice` cùng `@ExceptionHandler` xử lý lỗi
Đáp án đúng: C

Câu 03. Muốn ánh xạ GET `/orders/{id}` vào controller method, annotation nào phù hợp?
A. `@PostMapping("/orders/{id}")` cho HTTP POST
B. `@GetMapping("/orders/{id}")` cho HTTP GET
C. `@PutMapping("/orders/{id}")` cho HTTP PUT
D. `@DeleteMapping("/orders/{id}")` cho HTTP DELETE
Đáp án đúng: B

Câu 04. Trong route `/orders/{id}`, annotation nào bind đoạn `{id}` vào tham số Java?
A. `@RequestHeader("id")` lấy từ HTTP header của client
B. `@CookieValue("id")` lấy từ cookie của request
C. `@PathVariable("id")` lấy giá trị từ URI template
D. `@RequestParam("id")` lấy từ query string của URL
Đáp án đúng: C

Câu 05. Khi URL là `/search?q=spring`, annotation nào bind giá trị `q` vào method?
A. `@CookieValue("q")` đọc cookie từ browser request
B. `@PathVariable("q")` đọc biến route của URI template
C. `@RequestHeader("q")` đọc header HTTP tên tương ứng
D. `@RequestParam("q")` đọc query parameter từ request
Đáp án đúng: D

Câu 06. Để controller nhận giá trị header `X-Request-ID`, annotation nào đúng?
A. `@RequestHeader("X-Request-ID")` lấy header theo tên
B. `@RequestParam("X-Request-ID")` đọc query parameter
C. `@PathVariable("X-Request-ID")` đọc route variable
D. `@CookieValue("X-Request-ID")` đọc cookie request
Đáp án đúng: A

Câu 07. Trong `@RequestMapping`, thuộc tính nào giới hạn request theo `Content-Type` body?
A. `headers = "Accept=application/json"` kiểm header Accept
B. `params = "format=json"` kiểm query param từ client
C. `produces = "application/json"` chọn media type đầu ra
D. `consumes = "application/json"` chọn media type đầu vào
Đáp án đúng: D

Câu 08. Trong `@RequestMapping`, thuộc tính nào góp phần chọn representation dựa trên HTTP `Accept`?
A. `headers = "Content-Type=application/json"` kiểm input
B. `consumes = "application/json"` khai báo media type input
C. `produces = "application/json"` khai báo kiểu output
D. `params = "format=json"` kiểm query param từ client
Đáp án đúng: C

Câu 09. Muốn chuyển JSON trong request body thành một DTO Java, annotation nào thường dùng?
A. `@RequestParam` đọc trực tiếp từ query parameters
B. `@RequestBody` đọc body qua HttpMessageConverter
C. `@PathVariable` ánh xạ đoạn path vào tham số Java
D. `@ModelAttribute` chủ yếu bind form và query params
Đáp án đúng: B

Câu 10. Nếu form gửi các trường `name`, `age` qua query/form data, kiểu bind object nào phù hợp?
A. `@RequestHeader` lấy các HTTP headers thành object
B. `@PathVariable` lấy toàn bộ URI template thành object
C. `@RequestBody` giải mã JSON body thành object Java
D. `@ModelAttribute` bind form/query vào Java bean
Đáp án đúng: D

Câu 11. Muốn Jakarta Validation kiểm tra DTO nhận bằng `@RequestBody`, cần annotation nào trên parameter?
A. `@ResponseStatus` kích hoạt validation cho DTO
B. `@ResponseBody` kích hoạt validation cho DTO binding
C. `@RequestMapping` kích hoạt validation cho DTO
D. `@Valid` kích hoạt validation cho DTO được binding
Đáp án đúng: D

Câu 12. Trong MVC controller, để xử lý các lỗi binding/validation của `@ModelAttribute` ngay tại method, nên đặt gì?
A. `HandlerInterceptor` ngay sau tham số model được kiểm tra
B. `WebDataBinder` ở vị trí cuối của controller method
C. `BindingResult` đặt ngay sau tham số cần validation
D. `ModelAndView` trước tham số model đang được kiểm tra
Đáp án đúng: C

Câu 13. Muốn gom xử lý exception thành JSON cho nhiều REST controller, cách nào phù hợp?
A. `@RequestMapping` và các method `@ResponseBody` để bắt lỗi
B. `@RestControllerAdvice` và các method `@ExceptionHandler`
C. `@ModelAttribute` và các method `@PostMapping` để bắt lỗi
D. `@Controller` và các method `@InitBinder` để bắt lỗi
Đáp án đúng: B

Câu 14. Để tạo HTTP error body theo định dạng Problem Details trong Spring 6, API nào phù hợp?
A. `SseEmitter.send(detail)` đẩy event thay cho error body
B. `ResponseEntity.ok(detail)` tạo HTTP body status 200 OK
C. `ProblemDetail.forStatusAndDetail(status, detail)`
D. `ModelAndView(viewName, detail)` tạo HTML error view
Đáp án đúng: C

Câu 15. Muốn kiểm soát đồng thời HTTP status, headers và body từ controller, kiểu trả về nào phù hợp?
A. `ResponseEntity<T>` đặt status, headers và body
B. `Model` chỉ gom attributes cho template render
C. `HttpHeaders` chỉ biểu diễn các response headers
D. `BindingResult` chỉ biểu diễn các lỗi dữ liệu bind
Đáp án đúng: A

Câu 16. Nếu controller method tạo resource và muốn mặc định trả HTTP 201, annotation nào phù hợp?
A. `@ResponseStatus(HttpStatus.CREATED)` đặt status response
B. `@RequestBody(HttpStatus.CREATED)` đặt status response
C. `@ExceptionHandler(HttpStatus.CREATED)` đặt status response
D. `@ResponseBody(HttpStatus.CREATED)` đặt status response
Đáp án đúng: A

Câu 17. Khi có một loại tham số controller tùy biến cần resolve từ request, extension point nào phù hợp?
A. `ViewResolver` chọn template dựa trên tên view
B. `HandlerMethodArgumentResolver` xử lý custom argument
C. `HttpMessageConverter` serialize response body JSON
D. `HandlerExceptionResolver` chuyển exception thành status
Đáp án đúng: B

Câu 18. Thành phần nào trong Spring MVC thường đọc request body và ghi response body theo media type?
A. `HandlerInterceptor` kiểm tra logic trước handler MVC
B. `ViewResolver` chọn view theo tên trả về từ controller
C. `HttpMessageConverter` đọc và ghi HTTP body
D. `LocaleResolver` quyết định locale của HTTP request
Đáp án đúng: C

Câu 19. Muốn chạy logic `preHandle` trước controller trong chuỗi Spring MVC, dùng gì?
A. `HandlerInterceptor` gắn vào MVC handler mapping
B. `ViewResolver` áp dụng trước khi chạy controller
C. `HttpMessageConverter` chạy trước handler mapping
D. `ResponseBodyAdvice` áp dụng trước khi gọi controller
Đáp án đúng: A

Câu 20. Để giới hạn nguồn cross-origin được trình duyệt cho phép gọi controller, dùng gì?
A. `@PathVariable("Origin")` khai báo origin được phép
B. `@CrossOrigin(origins = "https://app.example")` cấu hình CORS
C. `@RequestHeader("Origin")` cấp quyền gọi API từ origin
D. `@ResponseStatus(OK)` cấp quyền CORS cho origin
Đáp án đúng: B

Câu 21. Với conditional GET, `If-None-Match` trùng ETag hiện tại thường khiến server trả mã nào?
A. `200 OK` phải gửi lại toàn bộ response body
B. `201 Created` xác nhận tạo resource mới
C. `412 Precondition Failed` cho GET cache hợp lệ
D. `304 Not Modified` không cần gửi lại body cũ
Đáp án đúng: D

Câu 22. Theo HTTP semantics, method nào có ý nghĩa idempotent khi cùng request được lặp lại?
A. `PATCH` không có ràng buộc về idempotency mặc định
B. `CONNECT` mở tunnel tới máy chủ được chỉ định
C. `POST` tạo thao tác mới trên collection mỗi lần gọi
D. `PUT` có ngữ nghĩa idempotent cho cùng request
Đáp án đúng: D

Câu 23. Để nhận tệp được upload qua `multipart/form-data` trong Spring MVC, kiểu nào thường dùng?
A. `InputStream` được servlet tự bind thành multipart file
B. `Resource` đại diện file trên classpath/server
C. `MultipartFile` đại diện cho phần file upload
D. `HttpHeaders` giữ metadata headers của request
Đáp án đúng: C

Câu 24. Trong Spring MVC async, controller trả `Callable<T>` chủ yếu giúp gì?
A. Nhả servlet thread trong khi Callable chạy ở executor
B. Tự đổi toàn bộ ứng dụng MVC thành Reactive Streams
C. Giữ servlet thread chờ hết Callable rồi mới trả
D. Bỏ cơ chế Servlet async dispatch khi có Callable
Đáp án đúng: A

Câu 25. Nếu kết quả MVC async sẽ được cung cấp từ callback bên ngoài, kiểu nào phù hợp?
A. `ModelAndView` gửi kết quả async qua HTTP streaming
B. `DeferredResult<T>` được complete từ callback sau đó
C. `ResponseEntity<T>` tự mở async task sau khi trả về
D. `Callable<T>` chỉ tính kết quả trong tác vụ executor
Đáp án đúng: B

Câu 26. Muốn đặt timeout riêng cho một tác vụ async MVC dùng `Callable`, wrapper nào hữu ích?
A. `ResponseBodyEmitter` cấu hình timeout cho stream
B. `WebAsyncTask<T>` đặt timeout cho Callable
C. `DeferredResult<T>` cấp timeout cho Callable task
D. `SseEmitter` cấu hình timeout cho SSE stream
Đáp án đúng: B

Câu 27. Server chỉ cần đẩy luồng sự kiện văn bản một chiều qua HTTP tới trình duyệt, Spring MVC có gì?
A. `SseEmitter` hỗ trợ stream server-sent events
B. `WebSocketHandler` cung cấp kênh WebSocket hai chiều
C. `DeferredResult` hoàn thành một response khi sẵn sàng
D. `ResponseEntity` tạo một response body thông thường
Đáp án đúng: A

Câu 28. Trong Spring WebFlux, kiểu Reactor nào biểu diễn bất đồng bộ 0 hoặc 1 phần tử?
A. `ResponseEntity<T>` bao kết quả HTTP đồng bộ
B. `DeferredResult<T>` nhận kết quả async của MVC
C. `Flux<T>` có thể phát một chuỗi nhiều giá trị
D. `Mono<T>` là publisher phát tối đa một giá trị
Đáp án đúng: D

Câu 29. Trong Spring WebFlux, kiểu Reactor nào biểu diễn bất đồng bộ 0 đến N phần tử?
A. `ModelAndView` gắn model và view cho MVC
B. `Flux<T>` phát chuỗi nhiều phần tử bất đồng bộ
C. `Mono<T>` phát tối đa một phần tử hoặc hoàn thành
D. `Callable<T>` dùng để trả một giá trị khi thực thi
Đáp án đúng: B

Câu 30. Trong Reactive Streams, cơ chế nào cho subscriber kiểm soát lượng dữ liệu nhận?
A. Publisher đẩy dữ liệu không phụ thuộc subscriber
B. Subscriber chỉ đổi TCP buffer size để giới hạn
C. HTTP response status quyết định batch size
D. Backpressure dùng tín hiệu demand/request(n)
Đáp án đúng: D

Câu 31. Khi phải dùng thư viện blocking I/O bên trong WebFlux, cách tránh chặn event-loop nào phù hợp?
A. Dùng `Schedulers.parallel()` cho blocking I/O dài
B. Gọi `block()` trong handler rồi tăng event-loop threads
C. Giữ blocking call trên event-loop của Netty server
D. Đưa bước blocking sang `Schedulers.boundedElastic()`
Đáp án đúng: D

Câu 32. WebClient GET `/users/42` trả JSON User; pipeline nào phù hợp để nhận `Mono<User>`?
A. `get().uri("/users/42").retrieve().bodyToMono(User.class)`
B. `get().uri("/users/42").retrieve().bodyToMono(String.class)`
C. `get().uri("/users/42").retrieve().bodyToFlux(User.class)`
D. `get().uri("/users/42").retrieve().toEntityList(User.class)`
Đáp án đúng: A

Câu 33. Muốn WebClient chuyển HTTP 404 thành domain error tùy biến trong luồng `retrieve`, API nào phù hợp?
A. `ResponseSpec.onStatus(...)` ánh xạ status sang lỗi
B. `RequestHeadersSpec.accept(...)` đổi response status
C. `RequestBodySpec.contentType(...)` đọc lỗi từ body
D. `ClientResponse.cookies()` tự ném domain exception
Đáp án đúng: A

Câu 34. Nếu cần phân nhánh logic đọc body theo HTTP status của WebClient response, cách nào phù hợp?
A. Dùng `bodyToMono` đọc headers như HTTP body
B. Dùng `exchangeToMono` để xử lý `ClientResponse`
C. Dùng `defaultHeader` để đổi status của HTTP response
D. Dùng `retrieve()` rồi bỏ qua các status của response
Đáp án đúng: B

Câu 35. Với Spring HTTP Service Client, factory nào tạo proxy từ interface khai báo HTTP method?
A. `HttpServiceProxyFactory` tạo proxy từ HTTP interface
B. `RestControllerAdvice` tạo proxy từ HTTP exchange annotations
C. `HandlerMapping` tạo proxy từ REST service interface
D. `HandlerAdapter` tạo proxy từ REST service interface
Đáp án đúng: A

Câu 36. Trong một HTTP Service Client interface, annotation nào ánh xạ method đến GET `/orders/{id}`?
A. `@GetMapping("/orders/{id}")` cho handler server MVC
B. `@RequestBody("/orders/{id}")` lấy response body
C. `@GetExchange("/orders/{id}")` khai báo GET request
D. `@MessageMapping("/orders/{id}")` cho STOMP broker
Đáp án đúng: C

Câu 37. Muốn HTTP Service Client sử dụng `WebClient` để thực thi HTTP, adapter nào phù hợp?
A. `WebClientAdapter` kết nối HTTP proxy với WebClient
B. `HttpMessageConverter` thay HTTP client transport
C. `WebSocketHandlerAdapter` chuyển HTTP calls thành WS
D. `ReactorClientHttpConnector` làm controller argument resolver
Đáp án đúng: A

Câu 38. Với endpoint WebSocket thuần, interface nào xử lý message và lifecycle của session?
A. `HandlerMethodArgumentResolver` nhận các WS sessions
B. `WebSocketHandler` xử lý message và session callbacks
C. `HandlerInterceptor` nhận frames từ WebSocket session
D. `HttpMessageConverter` phân phối WebSocket frames
Đáp án đúng: B

Câu 39. Khi dùng Spring STOMP messaging qua WebSocket, annotation nào nhận message ở destination ứng dụng?
A. `@GetMapping("/chat.send")` ánh xạ STOMP message
B. `@RequestBody("/chat.send")` ánh xạ STOMP message
C. `@MessageMapping("/chat.send")` nhận STOMP message
D. `@ResponseStatus("/chat.send")` ánh xạ STOMP message
Đáp án đúng: C

Câu 40. Muốn test Spring MVC và WebFlux controller không dùng HTTP server thật, chọn cặp công cụ nào phù hợp?
A. `SseEmitter` cho MVC và `WebSocketHandler` cho WebFlux
B. `HttpServiceProxyFactory` cho MVC và `ModelAndView` cho WebFlux
C. `MockMvc` cho MVC và `WebTestClient` bind WebFlux context
D. `WebClient` cho MVC và `RestTemplate` cho WebFlux
Đáp án đúng: C
