# Giới hạn ghi dữ liệu cá nhân và nội dung biểu mẫu

Log giúp đội phát triển tìm nguyên nhân khi một request MVC thất bại. Tuy nhiên, một dòng log có thể vô tình chứa mật khẩu, email, số điện thoại, địa chỉ, nội dung người dùng nhập hoặc token phiên đăng nhập. Những dữ liệu này thường được sao chép sang hệ thống tập trung, công cụ APM, kho lưu trữ và bản sao lưu. Khi đã lan ra nhiều nơi, việc kiểm soát truy cập và xóa dữ liệu trở nên khó hơn.

Trong ứng dụng Model–View–Controller (MVC), dữ liệu cá nhân đi qua nhiều điểm: form trong View, request binding ở Controller, DTO, Service, exception, access log, trace và công cụ giám sát. Vì vậy, giới hạn dữ liệu ghi log phải được thiết kế xuyên suốt request lifecycle. Nguyên tắc quan trọng là chỉ ghi metadata cần cho vận hành, dùng allowlist trường an toàn, và giữ nội dung biểu mẫu trong luồng xử lý nghiệp vụ thay vì đưa vào log.

Bài học tập trung vào cách nhận diện dữ liệu nhạy cảm, chọn thông tin quan sát cần thiết, ghi log an toàn ở các tầng MVC, kiểm soát trace/metrics/APM, quản lý lưu trữ và kiểm thử để phát hiện rò rỉ.

## 1. Vì sao cần giới hạn dữ liệu trong log?

Một request tạo tài khoản có thể chứa email, mật khẩu, tên hiển thị và mã xác minh. Nếu ứng dụng ghi toàn bộ request body để chẩn đoán, log có thể lưu cả mật khẩu và mã xác minh. Nếu request lỗi validation, framework có thể ghi giá trị bị từ chối cùng thông báo lỗi. Nếu APM tự động thu thập header và body, dữ liệu nhạy cảm có thể được gửi sang một nhà cung cấp quan sát bên ngoài.

Các rủi ro thường gặp:

- Người có quyền đọc log có thể xem dữ liệu mà họ không được phép xem trong nghiệp vụ.
- Token, cookie hoặc mật khẩu bị sao chép vào hệ thống log và trở thành thông tin xác thực thứ hai.
- Nội dung biểu mẫu được giữ lâu hơn mục đích xử lý ban đầu.
- Dữ liệu được chuyển đến nhà cung cấp hoặc vùng lưu trữ khác mà nhóm phát triển không dự kiến.
- Một sự cố log có thể ảnh hưởng nhiều người dùng vì cùng một pipeline thu thập dữ liệu của toàn bộ request.
- Khi log được dùng để huấn luyện, phân tích hoặc chia sẻ nội bộ không đúng mục đích, phạm vi sử dụng dữ liệu có thể vượt quá nhu cầu vận hành.

Log là một bản sao dữ liệu. Nếu không có lý do rõ ràng để lưu một trường, hãy không ghi trường đó. Việc che dữ liệu sau khi đã thu thập chỉ là lớp bảo vệ bổ sung; tốt nhất là ngăn dữ liệu nhạy cảm đi vào log ngay từ nguồn.

## 2. Phân loại dữ liệu trước khi quyết định ghi

Không phải mọi metadata đều có mức rủi ro như nhau. Hãy lập danh mục dữ liệu mà request MVC có thể mang theo và xác định mục đích cần dùng.

| Nhóm dữ liệu | Ví dụ | Cách xử lý mặc định |
|---|---|---|
| Bí mật xác thực | Mật khẩu, access token, refresh token, session ID, API key | Không ghi; loại bỏ khỏi log, trace và exception |
| Dữ liệu cá nhân trực tiếp | Email, số điện thoại, họ tên, địa chỉ, ngày sinh | Không ghi giá trị thô; chỉ dùng nếu có mục đích vận hành được phê duyệt và biện pháp bảo vệ phù hợp |
| Dữ liệu nhạy cảm theo ngữ cảnh | Thông tin sức khỏe, tài chính, giấy tờ định danh, nội dung riêng tư | Không ghi nội dung; chỉ ghi mã sự kiện hoặc kết quả tối thiểu |
| Nội dung biểu mẫu | Ghi chú, bình luận, mô tả, câu trả lời, nội dung tải lên | Không ghi toàn bộ body hoặc giá trị trường |
| Định danh nội bộ | User ID, task ID, order ID, tenant ID | Đánh giá khả năng liên kết tới cá nhân; giới hạn trường hợp cần dùng và quyền truy cập |
| Metadata giao thức | HTTP method, route template, status, thời lượng | Thường có thể ghi nếu không chứa dữ liệu từ người dùng |
| Dữ liệu vận hành | Error code, event name, retry count, dependency name | Ưu tiên ghi theo mã và giá trị có miền hữu hạn |

Phân loại phụ thuộc sản phẩm. Một trường `comment` trong ứng dụng công việc có thể chứa thông tin riêng tư; một trường `searchQuery` có thể tiết lộ ý định, sức khỏe hoặc tài chính. Không thể kết luận dữ liệu an toàn chỉ vì tên trường không giống `password`.

### Định nghĩa mục đích của từng log event

Trước khi thêm log, hãy trả lời:

1. Sự kiện nào cần được quan sát?
2. Ai sẽ đọc log và dùng nó để quyết định điều gì?
3. Cần những trường nào để điều tra sự cố?
4. Có thể thay giá trị gốc bằng mã lỗi, trạng thái, loại thao tác hoặc định danh giả danh không?
5. Log cần được giữ trong bao lâu?

Nếu không có câu trả lời rõ ràng, không thêm trường dữ liệu vào log chỉ vì nó đang có sẵn trong request hoặc DTO.

## 3. Phân biệt application log, audit log, metric và trace

Các loại dữ liệu quan sát phục vụ mục đích khác nhau. Không nên dùng application log để thay thế tất cả.

| Loại dữ liệu | Mục đích | Ví dụ an toàn hơn |
|---|---|---|
| Application log | Chẩn đoán sự kiện và lỗi trong ứng dụng | `event=task.create`, `outcome=success`, `errorCode=VALIDATION_FAILED` |
| Audit log | Ghi lại hành động quan trọng cần truy vết trách nhiệm | Actor pseudonymous, action, resource reference, timestamp, outcome |
| Metric | Theo dõi xu hướng và tình trạng hệ thống | Request count theo route/status, latency histogram, error rate |
| Distributed trace | Theo dõi một request qua nhiều dịch vụ | Trace ID, span ID, service name, route template, duration |
| Access log | Ghi metadata HTTP tại proxy hoặc server | Method, route, status, duration, request ID |

Metric không nên chứa email, user ID hoặc nội dung tìm kiếm làm label. Trace không cần body để thể hiện đường đi của request. Audit log có thể cần định danh actor hoặc tài nguyên, nhưng vẫn phải giới hạn và kiểm soát truy cập. Hãy chọn đúng kênh cho từng mục đích.

## 4. Nguyên tắc allowlist: chỉ ghi trường đã được duyệt

Một cách triển khai an toàn là xây dựng log event theo danh sách trường cho phép. Không serialize toàn bộ request, DTO, entity hoặc session rồi hy vọng bộ lọc loại được mọi dữ liệu nhạy cảm.

Ví dụ, sự kiện tạo công việc có thể ghi:

```json
{
  "event": "task.create",
  "outcome": "success",
  "http.method": "POST",
  "http.route": "/tasks",
  "http.status_code": 303,
  "duration_ms": 42,
  "request_id": "7f8a1d9c-..."
}
```

Thông tin này đủ để biết hành động nào diễn ra, kết quả ra sao và request mất bao lâu. Không cần ghi tiêu đề, mô tả hoặc toàn bộ form người dùng đã gửi.

### Không ghi object tùy ý

Tránh các cách viết như:

```java
log.info("Request: {}", request);
log.debug("Form: {}", form);
log.info("User: {}", user);
log.debug("Payload: {}", objectMapper.writeValueAsString(requestDto));
```

Các object có thể chứa trường nhạy cảm hiện tại hoặc được bổ sung trong tương lai. Phương thức `toString()` cũng có thể được sinh tự động và đưa mọi field vào log. Việc thay đổi DTO vì mục đích API có thể vô tình làm thay đổi nội dung log.

Hãy ghi từng trường được duyệt:

```java
log.atInfo()
        .addKeyValue("event", "task.create")
        .addKeyValue("outcome", "success")
        .addKeyValue("http.route", "/tasks")
        .log("Task creation completed");
```

Ví dụ dùng API fluent của SLF4J 2.x. Nếu ứng dụng dùng phiên bản khác, có thể dùng logger có cấu trúc tương ứng. Các key và value được chọn rõ ràng; không đưa form object vào log.

## 5. Những nguồn rò rỉ thường gặp trong một request MVC

Dữ liệu có thể lọt vào log ở nhiều giai đoạn, kể cả khi Controller không chủ động ghi nội dung form.

### Access log và URL

URL có thể chứa email, mã mời, token đặt lại mật khẩu hoặc từ khóa tìm kiếm trong query string. Proxy và web server thường ghi URI đầy đủ theo mặc định. Nếu endpoint dùng query parameter cho dữ liệu riêng tư, access log có thể lưu chúng.

- Không đặt token hoặc bí mật trong path hay query string.
- Ưu tiên body hoặc header phù hợp cho dữ liệu cần bảo vệ, đồng thời cấu hình access log không ghi giá trị nhạy cảm.
- Dùng route template như `/users/{id}` thay vì URI thực `/users/alice@example.com` trong log ứng dụng.
- Kiểm tra access log ở ingress, reverse proxy, load balancer và Servlet container; sửa mỗi ứng dụng chưa đủ.

### Request header và cookie

Không ghi toàn bộ header map. Những header thường cần loại bỏ gồm `Authorization`, `Cookie`, `Set-Cookie`, header chứa API key, CSRF token và thông tin xác thực riêng của ứng dụng. `Referer` cũng có thể mang query string nhạy cảm.

Chỉ ghi header theo allowlist, chẳng hạn `Content-Type`, `Accept` hoặc một request ID đã được xác thực định dạng. Ngay cả các header tưởng như vô hại cũng cần xem xét ngữ cảnh và cấu hình proxy.

### Form object và request DTO

Không ghi `@ModelAttribute`, `@RequestBody`, `BindingResult` hoặc DTO bằng cách serialize toàn bộ object. Dữ liệu biểu mẫu có thể chứa nội dung tự do mà hệ thống không biết trước người dùng sẽ nhập gì.

### Exception và validation message

Exception có thể nhúng giá trị đầu vào vào message, ví dụ `Invalid email: alice@example.com`. Validation error có thể chứa `rejectedValue`. Log toàn bộ exception hoặc binding result mà không kiểm tra có thể làm lộ dữ liệu.

### SQL và ORM

SQL bind parameter log có thể chứa email, số điện thoại, nội dung tìm kiếm hoặc dữ liệu biểu mẫu. Không bật log tham số SQL ở production một cách mặc định. Khi cần điều tra, dùng dữ liệu đã làm sạch hoặc môi trường tái hiện với dữ liệu giả.

### APM và agent tự động thu thập

Agent có thể tự thu thập HTTP body, header, exception, SQL statement, database bind parameter, session attribute hoặc breadcrumb. Cấu hình ứng dụng an toàn không đủ nếu agent vẫn gửi dữ liệu thô sang hệ thống khác.

## 6. Ghi metadata HTTP mà không ghi nội dung request

Một log request hữu ích thường chỉ cần method, route template, status, thời lượng và request/trace ID. Route template tránh lưu giá trị path thực do người dùng cung cấp.

Trong Spring MVC, `HandlerInterceptor` có thể đọc route pattern sau khi `HandlerMapping` đã chọn handler:

```java
public class SafeRequestLogInterceptor implements HandlerInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(SafeRequestLogInterceptor.class);
    private static final String START_NANOS = "requestStartNanos";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        request.setAttribute(START_NANOS, System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {

        Object startValue = request.getAttribute(START_NANOS);
        long durationMs = startValue instanceof Long start
                ? (System.nanoTime() - start) / 1_000_000
                : -1;

        Object routeValue = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        String route = routeValue == null
                ? "unmatched"
                : routeValue.toString();

        log.atInfo()
                .addKeyValue("http.method", request.getMethod())
                .addKeyValue("http.route", route)
                .addKeyValue("http.status_code", response.getStatus())
                .addKeyValue("duration_ms", durationMs)
                .log("HTTP request completed");
    }
}
```

Đăng ký interceptor:

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new SafeRequestLogInterceptor())
                .addPathPatterns("/**");
    }
}
```

Ví dụ cố ý không ghi `request.getRequestURI()`, `request.getQueryString()`, header, parameter, body hoặc session. `BEST_MATCHING_PATTERN_ATTRIBUTE` thường chứa route pattern như `/tasks/{id}`. Với request không được ánh xạ, giá trị `unmatched` được dùng thay cho URI thực.

Interceptor này chỉ bao phủ request được xử lý trong Spring MVC. Request bị từ chối ở Security filter chain, static resource hoặc lỗi xảy ra trước mapping cần được quan sát ở filter/proxy tương ứng. Hãy dùng cùng chính sách allowlist ở các lớp đó.

## 7. Request ID và MDC không phải nơi chứa dữ liệu người dùng

Request ID giúp liên kết các log thuộc cùng một request. Nó không cần chứa email, user ID, session ID hoặc dữ liệu được mã hóa từ form. Dùng một mã ngẫu nhiên không mang ý nghĩa nghiệp vụ.

Ví dụ filter tạo request ID nội bộ và đưa vào MDC:

```java
@Component
public class RequestIdFilter extends OncePerRequestFilter {
    private static final String REQUEST_ID = "requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        MDC.put(REQUEST_ID, requestId);
        response.setHeader("X-Request-Id", requestId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(REQUEST_ID);
        }
    }
}
```

Pattern log có thể thêm `%X{requestId}` để gắn mã vào mỗi dòng. Filter xóa MDC trong `finally` để tránh dữ liệu của request trước rò sang request tiếp theo trên cùng thread.

Đây là ví dụ tạo request ID cho ứng dụng. Nếu hệ thống đã dùng Micrometer Tracing hoặc OpenTelemetry, nên dùng trace context chuẩn của hệ thống để liên kết span và log thay vì tự tạo một trace ID khác. Có thể vẫn dùng request ID riêng cho mục đích hỗ trợ, nhưng không nhầm nó với danh tính người dùng.

Không đưa thông tin cá nhân vào baggage hoặc MDC chỉ để tiện truy vấn. MDC được logger tự động đính kèm, nên một giá trị được đặt ở đó có thể xuất hiện trong mọi log của request.

### Xử lý request bất đồng bộ

MDC gắn với thread. Khi Spring MVC chuyển công việc sang executor hoặc async dispatch, context không nhất thiết tự truyền sang thread khác. Dùng cơ chế context propagation được hỗ trợ bởi Micrometer/OpenTelemetry hoặc executor đã cấu hình rõ. Chỉ truyền các trường quan sát đã được duyệt; không sao chép toàn bộ request attributes hay security context vào baggage/log.

## 8. Ghi lỗi validation mà không ghi giá trị bị từ chối

Khi người dùng gửi form không hợp lệ, ứng dụng thường cần biết trường nào sai và mã validation nào được kích hoạt. Không cần lưu giá trị người dùng đã nhập.

Ví dụ Controller xử lý lỗi:

```java
@PostMapping("/profile")
public String updateProfile(
        @Valid @ModelAttribute("form") ProfileForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        Set<String> allowedFields = Set.of("displayName", "phone");
        List<String> invalidFields = bindingResult.getFieldErrors().stream()
                .map(FieldError::getField)
                .filter(allowedFields::contains)
                .distinct()
                .toList();

        log.atWarn()
                .addKeyValue("event", "profile.update.rejected")
                .addKeyValue("error.code", "VALIDATION_FAILED")
                .addKeyValue("invalid_fields", invalidFields)
                .log("Profile form validation failed");

        return "profile/form";
    }

    profileService.update(form);
    return "redirect:/profile";
}
```

Danh sách field cũng phải là allowlist đã đánh giá. Với biểu mẫu chứa trường nhạy cảm, thậm chí tên field có thể tiết lộ thông tin; khi đó chỉ ghi số lượng trường sai hoặc nhóm lỗi.

Không ghi:

```java
log.warn("Validation errors: {}", bindingResult.getFieldErrors());
log.warn("Rejected value: {}", fieldError.getRejectedValue());
```

`FieldError` có thể chứa rejected value và default message. Message được nội suy cũng có thể nhúng giá trị nhập. Hãy ghi mã lỗi cố định và tên trường đã được duyệt, không ghi object lỗi nguyên vẹn.

## 9. Xử lý exception mà không để lộ nội dung biểu mẫu

Exception miền nên dùng mã lỗi ổn định hoặc loại exception rõ ràng. Khi ghi log, không mặc định rằng `exception.getMessage()` an toàn.

Ví dụ, thay vì đưa giá trị đầu vào vào message:

```java
throw new InvalidEmailException("Invalid email: " + email);
```

hãy dùng exception có mã hoặc message tổng quát:

```java
throw new InvalidProfileDataException("PROFILE_EMAIL_INVALID");
```

Advice có thể trả thông báo công khai và log mã lỗi:

```java
@RestControllerAdvice
public class ApiErrorHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiErrorHandler.class);

    @ExceptionHandler(InvalidProfileDataException.class)
    ResponseEntity<ProblemDetail> handleInvalidProfile(
            InvalidProfileDataException exception) {

        log.atWarn()
                .addKeyValue("event", "profile.update.rejected")
                .addKeyValue("error.code", "PROFILE_EMAIL_INVALID")
                .log("Profile update rejected");

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Thông tin hồ sơ chưa hợp lệ.");
        problem.setTitle("Không thể cập nhật hồ sơ");
        problem.setProperty("code", "PROFILE_EMAIL_INVALID");
        return ResponseEntity.badRequest().body(problem);
    }
}
```

Đối với lỗi ngoài dự kiến, stack trace có thể cần cho điều tra nhưng cần bảo đảm exception và thư viện không nhúng nội dung nhạy cảm. Tránh log toàn bộ request kèm exception. Cấu hình logging/APM phải được kiểm tra để không tự động thêm request body hoặc SQL bind parameters.

## 10. Định danh người dùng: dùng tối thiểu và giả danh khi phù hợp

Trong một số sự cố, đội vận hành cần biết một người dùng có gặp lỗi lặp lại hay không. Điều đó không có nghĩa phải ghi email hoặc số điện thoại.

Các lựa chọn:

- Không ghi định danh nếu route, thời gian và mã lỗi đã đủ để điều tra.
- Dùng mã tham chiếu nội bộ được giới hạn quyền truy cập nếu cần truy vết hành động.
- Dùng pseudonymous identifier khi cần liên kết nhiều sự kiện mà không hiển thị trực tiếp danh tính.
- Chỉ ghi vai trò hoặc nhóm quyền nếu điều đó đủ cho phân tích và không làm lộ membership nhạy cảm.

### Hash không tự động làm dữ liệu vô danh

Hash email hoặc số điện thoại bằng SHA-256 không nhất thiết bảo vệ được danh tính. Không gian giá trị có thể đoán được và kẻ tấn công có thể thử dictionary. Một mã hash ổn định vẫn cho phép liên kết hành vi của cùng một người qua thời gian.

Nếu cần pseudonymization, có thể dùng HMAC với khóa bí mật được quản lý riêng, giới hạn quyền và có chính sách luân chuyển. HMAC vẫn là dữ liệu giả danh có thể liên kết, không nên coi là dữ liệu vô danh. Không đưa khóa HMAC vào log hoặc source code.

Định danh nội bộ như `userId` cũng có thể là dữ liệu cá nhân khi có thể liên kết trở lại một cá nhân. Hãy đánh giá mục đích, phạm vi người đọc và thời hạn lưu trước khi ghi.

## 11. Không dùng nội dung form làm metric label hoặc trace attribute

Metrics và traces thường được gửi đến hệ thống tập trung, nên giới hạn dữ liệu ở đây quan trọng như log.

### Metrics có cardinality thấp

Các label phù hợp thường là route template, HTTP method, status class, service name hoặc error code có tập giá trị giới hạn.

Ví dụ:

```text
http_server_requests_seconds_count{
  method="POST",
  route="/tasks",
  status="2xx"
}
```

Không dùng các label như:

- `email="alice@example.com"`
- `user_id="918273"`
- `search_query="..."`
- `form_title="..."`
- `request_id="..."`

Các giá trị này có cardinality cao, làm tăng chi phí metrics và có thể tiết lộ dữ liệu cá nhân. Request ID thuộc log/trace context, không phải metric label.

### Trace attribute tối thiểu

Trace có thể chứa `http.method`, route template, status, service name và dependency name. Không thêm request body, form fields, raw URL, cookie, authorization header, SQL parameter hoặc nội dung exception do người dùng kiểm soát.

Không đưa PII vào OpenTelemetry baggage. Baggage được truyền giữa các dịch vụ và có thể bị ghi hoặc export ở nhiều điểm. Chỉ truyền metadata có mục đích rõ và được cho phép.

## 12. Cấu hình APM, tracing và SQL capture

Nhiều agent quan sát tự động thu thập dữ liệu mà không cần code ứng dụng gọi logger. Khi bật một agent mới hoặc nâng cấp phiên bản, hãy kiểm tra các nhóm cấu hình:

- HTTP request/response body capture: tắt hoặc chỉ bật cho endpoint và trường hợp đã được đánh giá.
- Header capture: allowlist rõ ràng; loại bỏ `Authorization`, `Cookie`, `Set-Cookie` và token.
- URL/query capture: không gửi query string chứa dữ liệu người dùng; dùng route template.
- SQL capture: không thu bind parameter hoặc giá trị literal nhạy cảm trong production.
- Exception capture: giới hạn thông tin message và context được gửi.
- Session/user attributes: không tự động attach object hoặc profile đầy đủ.
- Browser telemetry: không ghi form input, text field hoặc DOM snapshot có chứa dữ liệu riêng tư.
- Replay/session recording: mask input và vùng giao diện nhạy cảm; tắt recording trên màn hình có dữ liệu không thể mask đáng tin cậy.

Tên tùy chọn cụ thể phụ thuộc nhà cung cấp APM và phiên bản agent. Không dựa vào một tên cấu hình chung; hãy kiểm tra tài liệu, cấu hình đang chạy và payload thực tế được gửi.

### Kiểm tra ở cả đầu vào và đầu ra pipeline

Nên có nhiều lớp:

1. Ứng dụng chỉ phát log event theo allowlist.
2. Collector loại bỏ hoặc redact trường bị cấm trước khi export.
3. Backend giới hạn quyền truy cập và thời gian lưu.
4. Kiểm thử định kỳ xác nhận dữ liệu nhạy cảm không xuất hiện trong log, trace, metric hoặc dashboard.

Redaction tại collector là lớp phòng thủ bổ sung. Nếu dữ liệu đã được gửi qua mạng hoặc lưu ở buffer trước khi redact, nó vẫn có thể tồn tại ở một vị trí khác. Vì vậy, hãy chặn dữ liệu càng gần nguồn càng tốt.

## 13. Audit log không phải nơi lưu bản sao biểu mẫu

Một số hành động cần dấu vết trách nhiệm, ví dụ thay đổi quyền, duyệt giao dịch hoặc xóa tài nguyên. Audit log có mục tiêu khác application log: trả lời ai đã làm gì, với tài nguyên nào, khi nào và kết quả ra sao.

Một audit event tối thiểu có thể gồm:

```json
{
  "event": "access_policy.changed",
  "actor_ref": "hmac:8d2f...",
  "resource_type": "project",
  "resource_ref": "prj-204",
  "action": "member_role_updated",
  "outcome": "success",
  "occurred_at": "2026-11-19T15:00:00Z",
  "request_id": "7f8a1d9c-..."
}
```

Các giá trị trong ví dụ là giả định. `actor_ref` cần được tạo theo chính sách giả danh; `resource_ref` chỉ được ghi nếu cần và không tiết lộ danh tính ngoài phạm vi. Không cần lưu toàn bộ request JSON, nội dung ghi chú hoặc dữ liệu trước/sau nếu không có mục đích và cơ chế bảo vệ được xác định.

Nếu nghiệp vụ yêu cầu lưu giá trị trước và sau thay đổi, hãy xác định riêng trường nào được phép, ai có quyền đọc, thời hạn lưu, mã hóa và quy trình truy cập. Không tự động biến audit log thành bản sao của toàn bộ entity.

## 14. Giới hạn quyền truy cập, thời gian lưu và việc export

Ngay cả log đã giảm dữ liệu cũng cần được quản lý như một kho thông tin vận hành có kiểm soát.

### Quyền truy cập

- Chỉ cấp quyền đọc log cho vai trò cần điều tra hoặc vận hành.
- Tách quyền xem log tổng quát với quyền xem audit event nhạy cảm.
- Dùng SSO, MFA và phân quyền theo môi trường/tenant nếu hệ thống hỗ trợ.
- Ghi audit cho việc truy cập hoặc export log có độ nhạy cao.
- Không dùng chung tài khoản quản trị hoặc chia sẻ dashboard có dữ liệu cá nhân rộng rãi.

### Thời hạn lưu

- Đặt retention theo mục đích, loại dữ liệu và yêu cầu nội bộ/pháp lý áp dụng.
- Không giữ log vô thời hạn chỉ vì dung lượng lưu trữ còn đủ.
- Xác định thời hạn riêng cho application log, security event, audit log, trace và bản sao lưu.
- Kiểm tra dữ liệu hết hạn có thực sự được xóa khỏi index, archive và backup theo chính sách hay không.
- Không copy log production sang môi trường phát triển để tái hiện lỗi nếu chưa làm sạch dữ liệu.

### Truyền và lưu trữ

Dùng kênh truyền được bảo vệ, mã hóa khi lưu trữ và quản lý khóa theo chính sách tổ chức. Kiểm soát export sang nhà cung cấp bên ngoài, khu vực lưu trữ và tài khoản hỗ trợ. Việc một trường đã được che trên dashboard không có nghĩa bản gốc không còn trong raw event hoặc archive.

## 15. Thiết kế một chính sách log an toàn cho MVC

Một chính sách thực tế nên được viết thành quy tắc dễ áp dụng trong code review:

**Được phép ghi theo allowlist:**

- Tên event và mã lỗi ổn định.
- HTTP method, route template và status.
- Thời lượng, retry count, dependency name và kết quả.
- Request ID hoặc trace ID không mang ý nghĩa nghiệp vụ.
- Các mã tham chiếu giả danh đã được phê duyệt khi cần điều tra.

**Không ghi mặc định:**

- Request/response body hoặc toàn bộ form object.
- Password, token, cookie, session ID, API key và CSRF token.
- Email, số điện thoại, địa chỉ, ngày sinh và thông tin định danh.
- Nội dung bình luận, ghi chú, tin nhắn, mô tả hoặc câu trả lời tự do.
- Rejected value trong validation error.
- Query string, raw URL hoặc header map không lọc.
- SQL bind parameters, file upload content hoặc DOM snapshot.

**Chỉ ghi ngoại lệ khi có phê duyệt:**

- Một trường dữ liệu cụ thể thực sự cần cho điều tra.
- Có mục đích, phạm vi người đọc và thời hạn lưu được xác định.
- Có biện pháp giả danh, che dữ liệu hoặc giới hạn quyền phù hợp.
- Có kiểm thử xác nhận dữ liệu không bị phát tán sang kênh khác.

Chính sách cần được áp dụng ở application code, framework, proxy, agent APM, collector và backend log. Nếu chỉ viết trong tài liệu mà không có cấu hình hoặc kiểm thử hỗ trợ, rất dễ bị phá vỡ bởi một middleware mới.

## 16. Kiểm thử để phát hiện dữ liệu nhạy cảm bị ghi

Kiểm thử logging nên dùng marker giả lập có thể tìm kiếm, không dùng dữ liệu thật. Ví dụ tạo form với chuỗi `SECRET-MARKER-DO-NOT-LOG` rồi xác nhận marker không xuất hiện trong log capture.

### Kiểm thử log event ở cấp ứng dụng

Có thể dùng appender kiểm thử hoặc thư viện log capture để thu các sự kiện phát ra:

```java
@Test
void validationLogDoesNotContainSubmittedValue() {
    String secretMarker = "SECRET-MARKER-DO-NOT-LOG";

    ProfileForm form = new ProfileForm();
    form.setDisplayName(secretMarker);

    // Gọi luồng validation/controller bằng fixture phù hợp.
    // logCapture thu các event phát ra trong phạm vi test.

    assertThat(logCapture.allEventsAsString())
            .doesNotContain(secretMarker)
            .contains("VALIDATION_FAILED");
}
```

Đây là khung minh họa; `logCapture` là fixture do dự án cấu hình, và test nên gọi đúng luồng MVC hoặc component phát log. Không chỉ kiểm tra logger được gọi; cần kiểm tra toàn bộ message và structured arguments.

### Kiểm thử request filter và interceptor

Gửi request có marker trong body, query và header giả lập; xác nhận log event chỉ có route template, method, status, duration và request ID. Đồng thời kiểm tra `Authorization`, `Cookie`, `Set-Cookie` và `Referer` không xuất hiện.

### Kiểm thử exception và validation

- Tạo exception với message chứa marker để xác nhận logger không phát message thô nếu đó là loại exception có thể chứa dữ liệu đầu vào.
- Gửi form sai và xác nhận rejected value không được log.
- Kiểm tra response lỗi không chứa stack trace, SQL hoặc giá trị biểu mẫu ngoài hợp đồng.

### Kiểm thử pipeline quan sát

Trong môi trường kiểm thử, gửi marker qua request rồi kiểm tra event đã export đến collector/backend giả lập. Điều này phát hiện agent APM hoặc access log tự thu thập body dù application logger đã an toàn.

Kiểm thử nên chạy khi nâng cấp framework, logging encoder, tracing agent hoặc cấu hình proxy, vì các thay đổi này có thể làm xuất hiện trường dữ liệu mới.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Log toàn bộ request body để debug | Lưu mật khẩu, PII và nội dung biểu mẫu | Ghi metadata theo allowlist; tái hiện bằng dữ liệu giả |
| Log DTO hoặc entity bằng `toString()` | Field mới có thể tự động lọt vào log | Ghi event và trường cụ thể đã duyệt |
| Log `BindingResult` nguyên vẹn | Lộ rejected value và thông điệp nội suy | Ghi mã lỗi và tên trường đã cho phép |
| Log raw URL/query string | Lộ token, email hoặc từ khóa riêng tư | Ghi route template, bỏ query value |
| Log toàn bộ header | Lộ cookie, authorization và CSRF token | Allowlist header cần thiết |
| Ghi PII vào MDC hoặc trace baggage | Dữ liệu lan sang mọi log/span hoặc dịch vụ khác | Chỉ truyền request/trace ID và metadata tối thiểu |
| Dùng email/user ID làm metric label | Cardinality cao và lộ danh tính | Dùng route, status, error code có miền hữu hạn |
| Bật SQL bind logging trên production | Lộ giá trị query và dữ liệu biểu mẫu | Tắt mặc định, điều tra bằng dữ liệu giả hoặc đã làm sạch |
| Chỉ redact ở dashboard | Raw event, archive hoặc exporter vẫn giữ dữ liệu | Ngăn ở nguồn, lọc ở collector và kiểm tra backend |
| Dùng hash không khóa để giả danh email | Có thể dò ngược bằng dictionary | HMAC có quản lý khóa; vẫn xem là dữ liệu giả danh |
| Giữ log vô thời hạn | Tăng phạm vi và tác động của sự cố | Retention theo mục đích, xóa cả archive theo chính sách |

## 18. Quy trình rà soát một điểm ghi log

Trước khi thêm hoặc thay đổi log trong một chức năng MVC, hãy kiểm tra:

1. Log event này phục vụ mục đích vận hành hoặc bảo mật nào?
2. Có thể dùng metric, trace hoặc mã lỗi thay cho nội dung người dùng không?
3. Trường nào được phép ghi và ai đã duyệt allowlist đó?
4. Có trường nào đến từ form, DTO, entity, query string, header hoặc exception message không?
5. Route được ghi có phải route template thay vì URL thực không?
6. Request ID/trace ID có ngẫu nhiên và không chứa dữ liệu cá nhân không?
7. Metrics label có cardinality thấp và không chứa định danh không?
8. APM, SQL logger, proxy và browser telemetry có đang thu thập cùng dữ liệu không?
9. Log được export đến đâu, ai có thể đọc và thời hạn lưu là bao lâu?
10. Có test marker để chứng minh dữ liệu nhạy cảm không xuất hiện trong log, trace, metric và response lỗi không?

Giới hạn ghi dữ liệu cá nhân và nội dung biểu mẫu là một phần của thiết kế observability, không phải bước làm sạch sau khi sự cố đã xảy ra. Trong MVC, hãy giữ View và Controller xử lý dữ liệu nhập theo hợp đồng; Service và Model xử lý nghiệp vụ; logging chỉ ghi metadata tối thiểu cần cho vận hành. Allowlist, route template, mã lỗi ổn định, request/trace ID ngẫu nhiên, metrics cardinality thấp và kiểm thử marker giúp đội ngũ điều tra request mà không biến hệ thống log thành bản sao của dữ liệu người dùng.
