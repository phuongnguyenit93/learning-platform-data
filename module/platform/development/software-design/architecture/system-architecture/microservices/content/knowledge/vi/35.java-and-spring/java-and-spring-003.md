# Xây dựng REST API và HTTP client có timeout tường minh

## 1. Bối cảnh: API đáng tin cậy phải biết khi nào dừng chờ

Trong hệ thống Java/Spring, một REST API thường nhận request, kiểm tra dữ liệu, thực hiện nghiệp vụ, gọi database hoặc các dịch vụ khác rồi trả HTTP response. Một endpoint có thể chạy tốt khi mọi dependency khỏe, nhưng bị treo hoặc giữ tài nguyên lâu khi database, payment provider hay service phía sau phản hồi chậm.

Một lỗi phổ biến là chỉ cấu hình timeout ở gateway hoặc chỉ đặt read timeout cho một HTTP client. Trong thực tế, một request có thể phải chờ ở nhiều giai đoạn:
- Chờ lấy connection từ pool.
- Phân giải DNS và thiết lập TCP connection.
- Thực hiện TLS handshake.
- Gửi request.
- Chờ response headers.
- Đọc response body.
- Chờ retry hoặc xử lý các bước downstream tiếp theo.

Nếu một giai đoạn không có giới hạn phù hợp, thread, connection, memory hoặc request slot có thể bị giữ lâu. Khi nhiều request cùng chờ, service có thể cạn thread pool hoặc connection pool, khiến cả những request vốn có thể hoàn tất nhanh cũng bị ảnh hưởng.

**Timeout tường minh (explicit timeout)** là việc đặt giới hạn thời gian rõ ràng cho các thao tác có thể chờ, dựa trên ngân sách latency của luồng nghiệp vụ. Timeout giúp service ngừng chờ một dependency quá lâu, giải phóng tài nguyên và thực hiện hành vi lỗi có kiểm soát.

Timeout không tự làm dependency nhanh hơn, không bảo đảm request phía server chưa thực hiện side effect và cũng không thay thế retry, circuit breaker, idempotency hay graceful degradation. Một thiết kế tốt phải kết hợp hợp đồng API rõ ràng với timeout ở từng hop và deadline tổng thể.

Sau bài học, người học có thể:
1. Thiết kế REST resource, HTTP method, status code và error response nhất quán.
2. Xây dựng controller Spring Boot có validation, DTO và exception handling.
3. Phân biệt connect, connection-pool acquisition, response/read, write và end-to-end timeout.
4. Cấu hình timeout tường minh cho RestClient, WebClient và JDK HttpClient.
5. Phân bổ deadline xuyên qua nhiều service để tránh request chờ vô hạn.
6. Kết hợp timeout với retry có giới hạn, idempotency, circuit breaker và bulkhead.
7. Kiểm thử timeout và quan sát latency, timeout rate, pool pressure trong production.

## 2. REST API là hợp đồng tài nguyên

REST API nên biểu diễn tài nguyên và trạng thái nghiệp vụ bằng URI và HTTP semantics. Ví dụ một API quản lý đơn hàng:

~~~text
GET    /api/v1/orders/{orderId}
POST   /api/v1/orders
PUT    /api/v1/orders/{orderId}
PATCH  /api/v1/orders/{orderId}
DELETE /api/v1/orders/{orderId}
GET    /api/v1/orders?status=PAID&page=0&size=20
~~~

URI nên xác định tài nguyên, còn HTTP method thể hiện hành động. Tránh thiết kế mọi thao tác thành POST với tên động như /getOrder, /updateOrder, /deleteOrder nếu không có lý do về contract hoặc compatibility.

Một REST API tốt cần thống nhất:
- Resource naming và URI hierarchy.
- Request/response schema.
- HTTP method và semantics.
- Status code.
- Validation và error model.
- Authentication/authorization.
- Pagination, filtering và sorting.
- Idempotency và concurrency.
- Versioning và compatibility.
- Timeout/deadline và behavior khi dependency lỗi.

### 2.1. Chọn HTTP method theo semantics

| Method | Mục đích | Idempotent theo HTTP semantics? | Ví dụ |
| --- | --- | --- | --- |
| GET | Đọc representation | Có | Lấy chi tiết đơn |
| HEAD | Đọc metadata headers | Có | Kiểm tra resource |
| POST | Tạo hoặc thực hiện command | Không mặc định | Tạo đơn hàng |
| PUT | Thay thế representation tại URI | Có | Cập nhật toàn bộ địa chỉ |
| PATCH | Thay đổi một phần | Không mặc định; phụ thuộc patch semantics | Cập nhật ghi chú |
| DELETE | Xóa hoặc yêu cầu xóa | Có theo semantics | Hủy resource nếu contract cho phép |

Idempotent nghĩa là gửi cùng request nhiều lần có hiệu quả trạng thái dự kiến tương đương một lần, không có nghĩa response phải giống hệt hoặc server không ghi log. POST có thể được thiết kế idempotent bằng idempotency key, đặc biệt với tạo đơn hoặc thanh toán.

### 2.2. Status code thường dùng

| Code | Ý nghĩa thường gặp | Khi sử dụng |
| --- | --- | --- |
| 200 OK | Thành công và có response body | Đọc hoặc cập nhật có representation |
| 201 Created | Tạo tài nguyên thành công | Có thể kèm Location |
| 202 Accepted | Đã nhận xử lý bất đồng bộ | Chưa khẳng định nghiệp vụ hoàn tất |
| 204 No Content | Thành công không có body | DELETE hoặc cập nhật không trả representation |
| 400 Bad Request | Request sai cú pháp/không hợp lệ | JSON lỗi, parameter không hợp lệ |
| 401 Unauthorized | Chưa xác thực hợp lệ | Thiếu hoặc token không hợp lệ |
| 403 Forbidden | Đã xác thực nhưng không có quyền | Không được phép thực hiện |
| 404 Not Found | Không tìm thấy hoặc không được tiết lộ sự tồn tại | Resource không tồn tại theo contract |
| 409 Conflict | Xung đột trạng thái | Duplicate, optimistic locking conflict |
| 422 Unprocessable Content | Nội dung hợp cú pháp nhưng vi phạm quy tắc xử lý | Validation nghiệp vụ nếu API chọn semantics này |
| 429 Too Many Requests | Bị giới hạn tốc độ | Rate limit hoặc quota |
| 500 Internal Server Error | Lỗi không dự kiến phía server | Exception không được ánh xạ cụ thể |
| 502 Bad Gateway | Gateway nhận phản hồi không hợp lệ từ upstream | Proxy/gateway |
| 503 Service Unavailable | Tạm thời không thể phục vụ | Quá tải, maintenance, dependency unavailable |
| 504 Gateway Timeout | Gateway không nhận được phản hồi kịp thời từ upstream | Timeout tại gateway |

Không trả 200 cho mọi kết quả rồi đưa mã lỗi nghiệp vụ vào body nếu client cần dựa vào HTTP semantics để retry, cache, monitor hoặc xử lý lỗi. Cũng không dùng 500 cho mọi lỗi validation hay quyền truy cập.

## 3. Thiết kế request và response DTO

Không nên expose trực tiếp JPA entity làm API contract. Entity phản ánh persistence model; DTO phản ánh contract công khai. Nếu trả entity, thay đổi database mapping có thể vô tình làm thay đổi API, lộ field nội bộ hoặc tạo vòng tham chiếu JSON.

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<@Valid OrderLineRequest> lines,
    @NotBlank String currency
) {}

public record OrderLineRequest(
    @NotBlank String productId,
    @Positive int quantity
) {}

public record OrderResponse(
    String orderId,
    String status,
    BigDecimal totalAmount,
    String currency,
    Instant createdAt
) {}
~~~

Controller cần dùng validation phù hợp:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderApplicationService orderService;

    public OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        URI location = URI.create("/api/v1/orders/" + created.orderId());
        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{orderId}")
    public OrderResponse get(@PathVariable String orderId) {
        return orderService.get(orderId);
    }
}
~~~

Các import và domain types được lược bớt để tập trung vào cấu trúc. Trong ứng dụng thực tế, cần xác định rõ validation ở DTO, authorization ở application/service layer và mapping giữa domain model với response.

### 3.1. Validation cú pháp và validation nghiệp vụ

Validation cú pháp có thể kiểm tra:
- Field bắt buộc.
- Độ dài, format, kiểu dữ liệu.
- Số lượng dương.
- Danh sách không rỗng.
- Ngày giờ theo định dạng hợp lệ.

Validation nghiệp vụ có thể kiểm tra:
- Khách hàng đang active.
- Sản phẩm được phép bán.
- Số lượng không vượt giới hạn.
- Đơn hàng có thể chuyển từ trạng thái hiện tại sang trạng thái yêu cầu.
- Currency được hỗ trợ.

Không nên đưa mọi validation vào annotation. Những điều kiện cần truy vấn trạng thái nghiệp vụ hoặc phụ thuộc nhiều thành phần nên nằm ở application/domain service với transaction semantics rõ ràng.

### 3.2. Pagination, filtering và sorting

API list nên giới hạn kích thước trang và có quy tắc sorting ổn định:

~~~http
GET /api/v1/orders?status=PAID&page=0&size=20&sort=createdAt,desc
~~~

Cần:
- Đặt default và maximum page size.
- Allowlist field có thể sort; không nối trực tiếp tên field client vào SQL.
- Có thứ tự phụ ổn định, ví dụ createdAt cùng orderId.
- Cân nhắc cursor pagination cho dataset lớn hoặc dữ liệu thay đổi liên tục.
- Áp dụng authorization và tenant scope trước khi trả count/result.
- Không để page size vô hạn tạo tải lớn.

Pagination không chỉ là chi tiết giao diện; nó ảnh hưởng query plan, memory, response size và latency.

## 4. Error response thống nhất với Problem Details

Client cần hiểu lỗi mà không phụ thuộc stack trace hoặc tên exception nội bộ. Spring Framework hỗ trợ Problem Details theo RFC 9457 ở các phiên bản hiện đại. Một response có thể có:
- type: loại lỗi hoặc tài liệu giải thích.
- title: tiêu đề ngắn.
- status: HTTP status.
- detail: thông tin an toàn cho client.
- instance: URI của request gây lỗi.
- extension fields: errorCode, fieldErrors, correlationId.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/orders",
  "errorCode": "ORDER_REQUEST_INVALID",
  "fieldErrors": [
    {
      "field": "lines[0].quantity",
      "code": "must-be-positive"
    }
  ],
  "correlationId": "01JEXAMPLE"
}
~~~

Không trả SQL, stack trace, host nội bộ, secret hoặc dữ liệu của tenant khác trong error body. Correlation ID giúp client/support liên hệ với logs/traces nhưng không nên dùng nó làm metric label cardinality cao.

### 4.1. Exception handling tập trung

Ví dụ Spring Boot:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ProblemDetail handleNotFound(
            OrderNotFoundException exception,
            HttpServletRequest request) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail("The requested order does not exist.");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("errorCode", "ORDER_NOT_FOUND");
        return problem;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail handleValidation(
            MethodArgumentNotValidException exception,
            HttpServletRequest request) {
        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setTitle("Request validation failed");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("errorCode", "REQUEST_INVALID");
        return problem;
    }
}
~~~

Đây là ví dụ rút gọn. Cần thêm handler cho lỗi domain, conflict, authentication/authorization, malformed JSON, upstream timeout và lỗi không mong đợi. Không expose exception message gốc nếu message có thể chứa dữ liệu nhạy cảm.

### 4.2. Timeout trong response contract

Nếu service gọi dependency và hết timeout, cần chọn status phù hợp theo vai trò:
- API trực tiếp phụ thuộc upstream và không thể hoàn thành: thường 503 hoặc 504 theo contract và vị trí gateway.
- API nhận command bất đồng bộ nhưng đã lưu durable job: có thể trả 202 và operation resource.
- Request client hết thời gian chờ: client có thể không biết server đã commit hay chưa.

Không biến mọi timeout thành 500. Cần phân biệt timeout nội bộ, timeout upstream, caller cancellation và deadline đã hết. Error code ổn định giúp client xử lý mà không phải parse text.

## 5. Timeout là nhiều giới hạn khác nhau

Một HTTP call có nhiều giai đoạn. Tên gọi trong thư viện có thể khác nhau, nên cần đọc semantics của client và phiên bản đang dùng.

| Timeout | Giới hạn điều gì? | Rủi ro nếu không đặt |
| --- | --- | --- |
| Pool acquisition | Thời gian chờ lấy connection từ pool | Request xếp hàng vô hạn khi pool cạn |
| Connect | Thời gian thiết lập kết nối TCP | Chờ lâu khi host/network không thể kết nối |
| TLS handshake | Thời gian hoàn tất TLS nếu client expose riêng | Kết nối bảo mật bị treo ở handshake |
| Response/header | Thời gian chờ response hoặc headers từ server | Chờ upstream phản hồi quá lâu |
| Read/socket | Khoảng chờ dữ liệu tiếp theo từ socket | Body stream có thể dừng giữa chừng |
| Write | Thời gian gửi request/body | Upload hoặc socket ghi bị kẹt |
| Request/call deadline | Giới hạn tổng thời gian của một lần gọi theo semantics client | Các giai đoạn riêng lẻ đều có giới hạn nhưng tổng vẫn quá dài |
| End-to-end deadline | Ngân sách của toàn bộ business request qua nhiều service | Mỗi hop chờ hợp lệ nhưng tổng trải nghiệm vượt SLO |

Không phải client nào cũng có một setting riêng cho mọi loại timeout. Một số thư viện dùng response timeout, socket timeout hoặc call timeout với semantics khác nhau. Phải kiểm tra version và tài liệu API thực tế, không copy một cấu hình sang thư viện khác rồi giả định tương đương.

### 5.1. Connect timeout

Connect timeout giới hạn thời gian thiết lập kết nối. Nó không giới hạn thời gian server xử lý request sau khi kết nối đã thành công.

Ví dụ:
- Service A mở kết nối tới B.
- TCP connect hoàn thành trong 20 ms.
- B nhận request nhưng xử lý 10 giây.
- Connect timeout 300 ms không ngăn A chờ response 10 giây.

### 5.2. Pool acquisition timeout

HTTP client thường tái sử dụng connection. Khi mọi connection trong pool đang bận, request mới có thể chờ tới khi có connection rảnh. Đây là một hàng đợi riêng.

Nếu pool tối đa 50 connections và 50 request đều bị upstream giữ 5 giây, request thứ 51 có thể chờ pool dù network và upstream vẫn hoạt động. Cần đặt pending/acquire timeout và giới hạn concurrency.

### 5.3. Response/read timeout

Response timeout thường giới hạn thời gian chờ response hoặc khoảng chờ dữ liệu, tùy client. Socket read timeout có thể là khoảng thời gian không nhận được dữ liệu; nếu server gửi một ít dữ liệu đều đặn, tổng thời gian stream vẫn có thể dài.

Với streaming response hoặc tải file lớn, cần hiểu rõ semantics giữa idle timeout và total deadline. Một timeout 1 giây cho mỗi lần read không nhất thiết giới hạn toàn bộ download ở 1 giây.

### 5.4. Request/call timeout

Một số client hỗ trợ deadline tổng cho một lần HTTP exchange. Đây là lớp quan trọng để giới hạn cả connect, gửi và nhận theo semantics của thư viện. Tuy nhiên, không được giả định mọi API request timeout bao trùm mọi hoạt động xử lý body hoặc mọi callback; kiểm tra docs và test trên version thực tế.

### 5.5. End-to-end deadline

Một request từ gateway qua order-service, inventory-service và payment-service có thể tiêu thụ thời gian ở nhiều hop. Cần truyền ngân sách deadline hoặc remaining timeout để service con biết thời gian còn lại. Nếu mỗi service tự đặt 5 giây, một call chain nhiều tầng có thể kéo dài vượt xa SLO.

## 6. Phân bổ ngân sách thời gian

Giả sử client có timeout tổng 3 giây. Gateway dành 200 ms cho auth/routing và 2,8 giây cho backend. order-service cần:
- 150 ms xử lý và truy vấn local.
- Tối đa 700 ms cho inventory.
- Tối đa 900 ms cho payment.
- 250 ms cho ghi order và trả response.
- Phần còn lại cho network, scheduling và biến động.

Đây là ví dụ minh họa; các con số phải dựa trên latency baseline, SLO, workload và tail distribution.

Một nguyên tắc quan trọng:
- Timeout downstream phải nhỏ hơn deadline còn lại của caller.
- Timeout ở service nên đủ chừa thời gian serialize response và cleanup.
- Không cộng retry vô hạn vào ngân sách.
- Không cấu hình mọi hop cùng một timeout lớn.
- Có safety margin cho queueing, network và scheduler.
- Phải xem p95/p99, không chỉ average.

### 6.1. Ví dụ ngân sách theo tầng

~~~text
Mobile/client deadline:          3.0 s
  API gateway budget:            2.8 s
    order-service budget:        2.4 s
      inventory call:            0.6 s
      payment call:               0.9 s
      local work + DB:            0.5 s
      response/overhead reserve:  0.4 s
  gateway/client reserve:         0.2 s
~~~

Các bước trong order-service có thể tuần tự hoặc song song; nếu song song, cách tính tổng budget khác nhưng vẫn phải kiểm soát fan-out và cancellation. Không lấy tổng timeout của các nhánh song song rồi cho rằng caller có thể chờ lâu hơn deadline.

### 6.2. Deadline propagation

Có thể truyền deadline tuyệt đối hoặc remaining duration qua request context/header nội bộ. Nếu truyền timestamp, các máy phải xử lý clock skew; nếu truyền remaining duration, mỗi hop phải trừ thời gian đã tiêu thụ và không reset về giá trị ban đầu.

Header nội bộ không tự đáng tin chỉ vì tên bắt đầu bằng X. Gateway/service mesh nên xóa hoặc ghi đè header do client gửi, sau đó tạo context đáng tin. Không cho client kéo dài deadline vượt giới hạn policy của server.

### 6.3. Không chỉ dựa vào client timeout

Nếu client timeout sau 2 giây, server có thể vẫn tiếp tục chạy và ghi database sau đó. Với request đã bị caller hủy, ứng dụng cần xử lý cancellation/interrupt phù hợp và xác định operation có được phép tiếp tục hay không.

Đối với command ghi dữ liệu:
- Kiểm tra idempotency key.
- Có thể lưu trạng thái operation và trả 202.
- Không giả định timeout nghĩa là transaction rollback.
- Có endpoint tra cứu kết quả nếu client không biết commit đã xảy ra chưa.
- Dùng transaction và outbox để bảo đảm side effect nhất quán.

## 7. Cấu hình HTTP client trong Spring: chọn đúng API

Các lựa chọn thường gặp:
- **RestClient:** API đồng bộ hiện đại của Spring Framework 6.1+, phù hợp request/response blocking.
- **WebClient:** API reactive/non-blocking, phù hợp streaming và hệ thống reactive.
- **RestTemplate:** API đồng bộ cũ, vẫn tồn tại trong nhiều codebase; nên xem lộ trình framework và chuẩn của dự án.
- **JDK HttpClient:** HTTP client của Java, có thể tích hợp qua request factory hoặc dùng trực tiếp.
- **Apache HttpClient 5 / Jetty client / Reactor Netty:** cung cấp connection pooling và timeout controls theo implementation.

Không cần dùng WebClient chỉ vì hệ thống có nhiều service. Nếu application đang dùng Spring MVC và call đồng bộ, RestClient có thể đơn giản hơn. WebClient trong ứng dụng blocking vẫn có thể bị gọi theo cách block, làm mất lợi ích reactive nếu không thiết kế phù hợp.

Phiên bản Spring Boot/Spring Framework quyết định API khả dụng. RestClient được giới thiệu trong Spring Framework 6.1; các cấu hình request factory và client connector phải tương thích dependency version. Trước khi copy snippet, kiểm tra BOM và phiên bản thư viện đang dùng.

## 8. RestClient với Apache HttpClient 5: cấu hình pool và timeout

Ví dụ dưới đây minh họa Spring Framework 6.1+ và Apache HttpClient 5. Tên method và package có thể thay đổi theo minor version; cần dùng dependency version được Spring Boot BOM quản lý.

~~~java
@Configuration
public class PartnerHttpConfiguration {

    @Bean
    CloseableHttpClient partnerApacheClient() {
        ConnectionConfig connectionConfig = ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofMilliseconds(300))
            .setSocketTimeout(Timeout.ofMilliseconds(900))
            .build();

        PoolingHttpClientConnectionManager connectionManager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(100)
                .setMaxConnPerRoute(30)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

        RequestConfig requestConfig = RequestConfig.custom()
            .setConnectionRequestTimeout(Timeout.ofMilliseconds(150))
            .setResponseTimeout(Timeout.ofMilliseconds(900))
            .build();

        return HttpClients.custom()
            .setConnectionManager(connectionManager)
            .setDefaultRequestConfig(requestConfig)
            .evictExpiredConnections()
            .build();
    }

    @Bean
    RestClient partnerRestClient(CloseableHttpClient partnerApacheClient) {
        HttpComponentsClientHttpRequestFactory factory =
            new HttpComponentsClientHttpRequestFactory(partnerApacheClient);

        return RestClient.builder()
            .baseUrl("https://partner.example")
            .requestFactory(factory)
            .build();
    }
}
~~~

Các import chính thuộc Apache HttpClient 5 và Spring HTTP client. Ví dụ giả định dependency Apache HttpClient 5 đã được khai báo. Cần kiểm tra constructor và timeout types theo đúng phiên bản Spring/HttpClient trong dự án.

Ý nghĩa các giá trị minh họa:
- Connect 300 ms: giới hạn thiết lập kết nối.
- Socket 900 ms: giới hạn chờ dữ liệu socket theo semantics của client.
- Pool acquisition 150 ms: giới hạn chờ connection từ pool.
- Response 900 ms: giới hạn chờ phản hồi theo RequestConfig.
- Pool tổng 100, tối đa 30 connection mỗi route: giới hạn concurrency connection.

Các con số không phải mặc định production. Chọn theo latency distribution, traffic, downstream capacity và tổng deadline. Nếu response body streaming, cần xem socket timeout và response timeout thực tế tương tác ra sao.

### 8.1. Gọi API qua RestClient

~~~java
@Service
public class PartnerCatalogClient {
    private final RestClient restClient;

    public PartnerCatalogClient(
            @Qualifier("partnerRestClient") RestClient restClient) {
        this.restClient = restClient;
    }

    public PartnerProduct getProduct(String productId) {
        return restClient.get()
            .uri("/api/products/{id}", productId)
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                (request, response) -> {
                    throw new PartnerProductNotFoundException(productId);
                }
            )
            .body(PartnerProduct.class);
    }
}
~~~

Cần thêm DTO, exception và mapping lỗi tương ứng. Với lỗi 4xx/5xx, RestClient có thể ném exception theo default status handler; custom handler giúp chuẩn hóa lỗi domain. Không nên bắt mọi exception rồi trả null, vì sẽ làm mất thông tin timeout, lỗi giao thức và lỗi nghiệp vụ.

### 8.2. Connection pool là tài nguyên có giới hạn

Pool size quá nhỏ làm request chờ lâu; quá lớn có thể làm upstream quá tải hoặc vượt giới hạn file descriptor/connection. Cần đo:
- leased/active connections.
- available/idle connections.
- pending acquisition.
- acquisition latency và timeout.
- connection reuse/eviction.
- số connection theo route/host.

Đặt maxConnPerRoute theo năng lực dependency, không chỉ theo số thread của ứng dụng. Nếu upstream giới hạn 50 concurrent requests, client pool 500 không tạo ra thêm capacity thật.

### 8.3. Idle eviction và connection lifetime

Connection có thể bị đóng bởi load balancer hoặc server khi idle. Client cần chiến lược validate/evict connection stale, TTL hoặc connection lifetime phù hợp. Không đặt lifetime tùy tiện thấp đến mức liên tục handshake, cũng không giữ connection mãi bất chấp hạ tầng giữa đường.

## 9. RestClient với JDK HttpClient

Java HttpClient hỗ trợ connect timeout ở cấp client và request timeout ở cấp HttpRequest. Ví dụ:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(300))
    .followRedirects(HttpClient.Redirect.NORMAL)
    .build();

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://partner.example/api/products/42"))
    .timeout(Duration.ofMillis(900))
    .header("Accept", "application/json")
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);
~~~

Connect timeout giới hạn kết nối; request timeout giới hạn thời gian của request theo semantics JDK HttpClient. Nó không cung cấp đầy đủ các knob quản lý connection-pool acquisition như Apache pool. Nếu cần pool limits, connection reuse policy hoặc socket-specific control chi tiết, hãy cân nhắc implementation client khác.

JDK HttpClient có API đồng bộ và bất đồng bộ. Với sendAsync, phải xử lý CompletionStage, cancellation và exception đúng cách. Không chặn event-loop hoặc thread pool dùng chung bằng thao tác blocking không có giới hạn.

## 10. WebClient với Reactor Netty: timeout và connection pool

WebClient phù hợp với ứng dụng reactive hoặc khi cần streaming/non-blocking I/O. Reactor Netty cho phép cấu hình connection pool, connect timeout và response timeout.

~~~java
@Configuration
public class PartnerWebClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        ConnectionProvider provider =
            ConnectionProvider.builder("partner-pool")
                .maxConnections(100)
                .pendingAcquireMaxCount(200)
                .pendingAcquireTimeout(Duration.ofMillis(150))
                .build();

        HttpClient httpClient = HttpClient.create(provider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
            .responseTimeout(Duration.ofMillis(900));

        return WebClient.builder()
            .baseUrl("https://partner.example")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Đây là cấu hình minh họa cho Reactor Netty. Nếu cần idle read/write timeout riêng, có thể cấu hình handler phù hợp, nhưng cần kiểm tra lifecycle và tác động tới connection reuse. Không thêm ReadTimeoutHandler một cách máy móc cho mọi call mà không hiểu nó đo idle socket hay tổng thời gian.

### 10.1. Gọi WebClient với deadline tổng

~~~java
public Mono<PartnerProduct> getProduct(String productId) {
    return webClient.get()
        .uri("/api/products/{id}", productId)
        .retrieve()
        .bodyToMono(PartnerProduct.class)
        .timeout(Duration.ofSeconds(1));
}
~~~

Toán tử timeout trên publisher giới hạn thời gian chờ ở reactive chain và phát TimeoutException nếu vượt quá. Nó không thay thế cấu hình connect/pool timeout và không bảo đảm server đã dừng xử lý side effect. Cần kiểm tra cancellation có được truyền tới connector và downstream operation theo đúng phiên bản.

### 10.2. Không trộn blocking và reactive tùy tiện

Một controller Spring MVC gọi WebClient rồi block có thể giữ servlet thread trong lúc chờ, nên vẫn phải đặt timeout và cân nhắc pool/thread capacity. Một controller WebFlux gọi JDBC blocking trên event-loop có thể làm nghẽn toàn bộ event loop.

Chọn mô hình đồng bộ hoặc reactive nhất quán với stack. Nếu phải tích hợp blocking dependency trong reactive flow, dùng scheduler phù hợp và giới hạn concurrency; không chỉ đổi RestTemplate thành WebClient rồi cho rằng service đã non-blocking.

## 11. Read timeout, response timeout và total timeout khác nhau

Ví dụ server gửi response body từng chunk mỗi 500 ms trong 30 giây:
- Idle read timeout 1 giây có thể không kích hoạt vì luôn có dữ liệu trong khoảng ngắn.
- Total call deadline 2 giây sẽ giới hạn toàn bộ thời gian chờ theo semantics client.
- Gateway timeout 3 giây có thể hủy request phía caller, nhưng server/upstream vẫn có thể tiếp tục.
- Client disconnect có thể không dừng một query hoặc side effect đã chạy ở server.

Với download/streaming:
- Đặt idle timeout để phát hiện kết nối đứng.
- Đặt total deadline nếu nghiệp vụ có giới hạn tổng.
- Có cơ chế resume/range hoặc chunking nếu file lớn.
- Giới hạn kích thước và tốc độ.
- Hủy stream/giải phóng tài nguyên khi caller cancel.

Với long polling, server-sent events hoặc WebSocket, timeout policy khác request/response ngắn. Không áp dụng cùng một deadline vài giây nếu giao thức yêu cầu kết nối dài; thay vào đó cấu hình heartbeat, idle timeout, reconnect và resource limits.

## 12. Timeout cho database và các dependency khác

HTTP timeout không đủ nếu service còn gọi:
- JDBC/database.
- Redis/cache.
- Kafka producer/consumer.
- Object storage.
- External payment/email.
- DNS hoặc identity provider.

Với JDBC, cần kiểm soát connection acquisition, statement/query timeout, transaction timeout và pool. Với Redis cần connect/command timeout và pool borrow timeout. Với Kafka cần delivery timeout, request timeout và consumer poll settings theo mục tiêu. Các tên config cụ thể phụ thuộc client/version.

Không đặt một timeout duy nhất cho toàn bộ dependency. Query đọc đơn giản, payment authorization và export file có latency profile khác nhau. Timeout cần gắn với operation và business priority.

### 12.1. Timeout và transaction

Nếu một transaction database đang mở trong lúc gọi HTTP downstream, connection/lock có thể bị giữ lâu. Tránh mở transaction rồi gọi một dependency chậm nếu có thể. Cân nhắc tách bước, outbox/saga, optimistic concurrency và commit boundary phù hợp.

### 12.2. Cancellation không đồng nghĩa rollback

Client timeout có thể xảy ra sau khi server đã commit. Database statement cancel có thể không được gửi hoặc không thể dừng kịp. Một payment provider có thể đã authorize dù client không nhận response.

Với command có side effect, thiết kế:
- Idempotency key duy nhất theo business operation.
- Tra cứu trạng thái giao dịch.
- Retry cùng key thay vì tạo operation mới.
- Reconciliation với provider.
- Outbox và state machine cho quy trình nhiều bước.

## 13. Retry: chỉ dùng khi có cơ sở

Timeout là tín hiệu call không hoàn thành trong deadline. Retry có thể giúp khi lỗi tạm thời, nhưng cũng có thể khuếch đại tải và tạo side effect trùng.

Một policy retry cần:
- Allowlist lỗi có thể retry.
- Số lần retry nhỏ và giới hạn tổng thời gian.
- Exponential backoff.
- Jitter để tránh đồng loạt retry.
- Retry budget theo service/operation.
- Idempotency cho write operation.
- Respect Retry-After với 429/503 khi phù hợp.
- Không retry lỗi validation, auth hoặc các 4xx không thể phục hồi.
- Không retry khi deadline đã hết.

Ví dụ pseudocode:

~~~text
deadline = now + 2 seconds
attempt = 0

while attempt < 2:
    remaining = deadline - now
    if remaining <= 0:
        fail with deadline exceeded

    call dependency with timeout <= remaining

    if success:
        return result

    if error is not retryable:
        fail

    if operation is not safe/idempotent:
        fail or query operation status

    delay = bounded exponential backoff + random jitter
    if delay >= remaining:
        fail

    wait delay
    attempt += 1
~~~

Đây là nguyên lý, không phải mã production. Không dùng Thread.sleep trên servlet/event-loop thread; dùng scheduler hoặc resilience library phù hợp. Cần bảo đảm mỗi attempt không vượt remaining deadline.

### 13.1. Retry storm

Giả sử service có 1.000 request/giây, mỗi request retry 3 lần khi dependency chậm. Upstream có thể nhận tới 4.000 request/giây trong khi capacity đang giảm. Nhiều service trong call chain cùng retry sẽ nhân tải lên theo cấp số nhân.

Giải pháp:
- Retry một tầng được chọn, không phải mọi tầng.
- Giới hạn số attempt và tổng retry budget.
- Backoff với jitter.
- Circuit breaker khi lỗi vượt ngưỡng.
- Bulkhead và admission control.
- Không retry request đã quá deadline.
- Dùng idempotency key cho command.

## 14. Circuit breaker, bulkhead và rate limit

Timeout giới hạn một call; circuit breaker ngăn liên tục gọi dependency đang lỗi. Bulkhead cách ly tài nguyên của từng dependency hoặc workload. Rate limit giới hạn tốc độ đầu vào.

**Circuit breaker** thường có ba trạng thái:
- Closed: cho phép call, theo dõi lỗi/latency.
- Open: chặn call tạm thời và trả lỗi/fallback nhanh.
- Half-open: cho một số probe thử để xác định dependency đã phục hồi chưa.

**Bulkhead** có thể giới hạn concurrent calls hoặc tách thread pool/pool connection cho dependency. Nếu payment chậm, nó không nên chiếm hết tài nguyên khiến catalog cũng ngừng phục vụ.

**Rate limit** bảo vệ cả service và downstream khỏi burst. Cần phân biệt limit theo user, tenant, API key, route và global capacity.

Timeout, breaker và bulkhead bổ trợ nhau:
- Timeout ngăn call giữ tài nguyên quá lâu.
- Bulkhead ngăn một dependency chiếm toàn bộ capacity.
- Breaker giảm call tới dependency đã có dấu hiệu hỏng.
- Rate limit kiểm soát tải đến.
- Fallback cho phép degraded response khi nghiệp vụ cho phép.

Không cấu hình fallback trả dữ liệu giả hoặc xác nhận giao dịch thành công khi dependency thanh toán chưa xác minh.

## 15. Security khi xây dựng REST API và HTTP client

### 15.1. Authentication và authorization

- Xác thực token/certificate theo issuer, audience, signature và expiry.
- Kiểm tra permission trên từng resource/action.
- Tenant identity phải được xác minh, không tin header client tự gửi.
- Không để ID khó đoán thay thế authorization.
- Giới hạn admin endpoints và Actuator.
- Không trả thông tin tồn tại resource khác tenant qua lỗi khác biệt không chủ đích.

### 15.2. Input và output

- Validate size, type, format và content.
- Giới hạn request body và multipart upload.
- Chặn mass assignment bằng DTO riêng.
- Không deserialize polymorphic type nguy hiểm tùy tiện.
- Encode output phù hợp context.
- Giới hạn page size, filter complexity và sort allowlist.

### 15.3. HTTP client và SSRF

Nếu client nhận URL từ user hoặc cấu hình có thể bị thao túng, có nguy cơ Server-Side Request Forgery. Không cho request tùy ý tới localhost, metadata endpoint, private network hoặc internal admin service. Dùng allowlist host/scheme, DNS/IP validation phù hợp, egress policy và redirect validation.

Không forward Authorization header hoặc cookie sang host khác chỉ vì client follow redirect. Cần xác định chính sách redirect và credential propagation.

### 15.4. Secret và logging

- Lấy credentials từ secret manager.
- Không hardcode token/password trong source hoặc YAML commit.
- Không log Authorization, Cookie, payment data hoặc PII không cần thiết.
- Redact headers/body trong HTTP wire logging.
- Giữ correlation ID nhưng không log dữ liệu nhạy cảm cùng ID đó.
- Xoay credential và giới hạn scope theo dependency.

## 16. Cấu hình timeout bên ngoài code

Không nên hardcode timeout trong mọi call site. Dùng configuration properties để có thể điều chỉnh theo môi trường, nhưng phải validate giá trị và giới hạn maximum.

Ví dụ YAML:

~~~yaml
clients:
  partner:
    base-url: https://partner.example
    connect-timeout: 300ms
    connection-request-timeout: 150ms
    response-timeout: 900ms
    total-timeout: 1200ms
    max-connections: 100
    max-connections-per-route: 30
~~~

Ví dụ configuration properties:

~~~java
@ConfigurationProperties(prefix = "clients.partner")
@Validated
public record PartnerClientProperties(
    URI baseUrl,
    @NotNull Duration connectTimeout,
    @NotNull Duration connectionRequestTimeout,
    @NotNull Duration responseTimeout,
    @NotNull Duration totalTimeout,
    @Min(1) int maxConnections,
    @Min(1) int maxConnectionsPerRoute
) {}
~~~

Đây là model cấu hình minh họa; cần bật configuration properties scanning/registration trong Spring Boot và bổ sung validation như timeout dương, totalTimeout lớn hơn các stage phù hợp, pool-per-route không vượt tổng pool. Không expose secret qua actuator configprops/env endpoints.

### 16.1. Không để cấu hình môi trường phá vỡ deadline

Staging có thể dùng timeout 5 giây vì test server chậm, production lại 1 giây; hoặc một override vô tình tăng lên 60 giây. Nên có policy giới hạn tối đa, log startup các giá trị không nhạy cảm, và dashboard/alert theo timeout configuration version.

Thay đổi timeout cũng là thay đổi behavior và capacity. Cần review, test và rollout như một config change, không chỉ coi là chỉnh một con số.

## 17. API versioning và backward compatibility

Một API công khai cần chính sách version:
- URI version như /api/v1/orders.
- Header/media type version nếu tổ chức có chuẩn.
- Backward-compatible additive changes.
- Deprecation và sunset notice.
- Contract tests với consumer.
- Migration guide.

Không phải mọi field mới đều an toàn. Thêm enum value có thể làm consumer cũ lỗi nếu deserialize nghiêm ngặt. Đổi optional thành required là breaking change. Đổi meaning/status transition có thể phá logic dù JSON schema không đổi.

Versioning không thay thế contract compatibility. Ghi rõ consumer nào dùng API, lịch deprecation và owner để tránh endpoint cũ tồn tại vô thời hạn.

## 18. Idempotency cho POST và command API

Timeout làm client không biết server đã xử lý xong hay chưa. Với POST tạo đơn, client có thể retry và tạo hai đơn nếu server không có cơ chế idempotency.

Một flow:
1. Client tạo idempotency key duy nhất cho một business intent.
2. Gửi key trong header.
3. Server lưu key cùng tenant, operation và request fingerprint.
4. Nếu key đã xử lý với cùng payload, trả lại kết quả đã lưu.
5. Nếu cùng key nhưng payload khác, trả conflict.
6. Nếu operation đang chạy, trả trạng thái processing hoặc chờ trong deadline có giới hạn.
7. TTL của idempotency record phải đủ dài theo retry window và nghĩa vụ nghiệp vụ.

Ví dụ:

~~~http
POST /api/v1/orders
Idempotency-Key: 7a5b0a4d-...
Content-Type: application/json
~~~

Idempotency key cần scope đúng tenant/user/operation và được lưu bền phù hợp. Chỉ lưu trong local memory hoặc cache dễ mất có thể không đủ bảo vệ khi failover.

## 19. Quan sát REST API và HTTP client

Một hệ thống timeout tốt cần biết call chậm ở đâu và vì sao. Nên đo:
- Request rate theo route/method.
- Success/error rate theo status và outcome.
- Server duration p50/p95/p99.
- Client dependency duration p50/p95/p99.
- Connect, pool acquire và response timeout count.
- Active/idle/pending connections.
- Retry attempts và retry exhaustion.
- Circuit breaker state/transitions.
- Cancellation/deadline exceeded.
- Request/response size.
- Trace span cho downstream call.
- Business completion rate.

### 19.1. Phân biệt timeout ở các lớp

Tên metric nên thể hiện timeout xảy ra ở:
- Gateway/client deadline.
- Pool acquisition.
- TCP connect.
- TLS handshake nếu instrument được.
- Response/read.
- Application deadline.
- Database statement/connection.
- Async message processing deadline.

Nếu chỉ có một counter tên http_timeout, incident responder không biết phải xem pool, network hay upstream.

### 19.2. Tracing

Một trace checkout có thể cho thấy:
- Gateway: 40 ms.
- order-service local processing: 100 ms.
- inventory HTTP call: 700 ms.
- payment HTTP call: timeout sau 900 ms.
- Order API trả 503 sau tổng 1,9 giây.

Span cần gắn dependency name, operation, status và timeout outcome. Không ghi request body chứa thông tin nhạy cảm vào trace. Parent span duration bao gồm child span; không cộng duration lồng nhau thành total latency.

### 19.3. Cardinality và dữ liệu nhạy cảm

Không dùng orderId, userId, token, raw URL query hoặc exception message làm metric labels. Dùng route template như /orders/{orderId}, status class, dependency và outcome. Correlation ID phù hợp với logs/traces theo access policy hơn là metric labels.

## 20. Kiểm thử timeout và REST contract

### 20.1. Controller tests

Dùng MockMvc hoặc WebTestClient theo stack để kiểm tra:
- HTTP method/route.
- Request validation.
- Status code.
- Response schema.
- Problem Details.
- Authentication/authorization.
- Pagination/filter behavior.
- Header và content negotiation.

Ví dụ MockMvc minh họa:

~~~java
mockMvc.perform(post("/api/v1/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":"","lines":[],"currency":"VND"}
            """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON));
~~~

Đoạn test yêu cầu Spring test setup và exception handler phù hợp. Không nên chỉ kiểm status code; kiểm tra errorCode/field errors theo contract.

### 20.2. Client timeout tests

Dùng mock HTTP server như WireMock hoặc MockWebServer để mô phỏng:
- Connection không hoàn tất hoặc host không thể kết nối.
- Response headers chậm.
- Body đọc chậm theo chunk.
- Server trả 500/503/429.
- Connection pool bị giữ hết.
- Server trả response rồi đóng socket.
- Redirect tới host khác.
- Request đã commit side effect nhưng response bị mất.

Kiểm tra:
- Call kết thúc trong giới hạn kỳ vọng.
- Exception/outcome được map đúng.
- Connection được giải phóng.
- Retry count không vượt policy.
- Không tạo duplicate side effect.
- Metric/tracing có timeout classification.
- Thread/pool không bị rò sau nhiều lần test.

### 20.3. Không chỉ test happy path

Một client timeout cấu hình đúng trong trường hợp server chậm 10 giây nhưng vẫn có thể bị treo khi pool acquisition hoặc TLS handshake. Test cần bao phủ các giai đoạn mà client implementation thực sự cung cấp timeout.

### 20.4. Load test và saturation

Khi tăng concurrency, đo:
- Active threads và queue.
- Pool leased/pending.
- Timeout rate.
- p95/p99.
- Upstream concurrency.
- Retry amplification.
- Memory và GC.

Nếu timeout tăng khi pending acquisition tăng nhưng connect/response latency bình thường, có thể pool quá nhỏ hoặc downstream giữ connection lâu. Nếu pool không pending nhưng response timeout tăng, cần điều tra upstream/network.

## 21. Timeout trong async và message-driven API

Không phải mọi thao tác nên giữ HTTP request mở tới khi hoàn tất. Với công việc dài:
1. API xác thực và nhận command.
2. Ghi durable job/operation state.
3. Publish event qua outbox hoặc queue.
4. Trả 202 Accepted cùng operation ID/Location.
5. Client poll hoặc nhận webhook/event khi hoàn tất.
6. Operation có status, deadline, retry policy và terminal state rõ.

Ví dụ:

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/operations/op-123
Retry-After: 2
Content-Type: application/json

{
  "operationId": "op-123",
  "status": "PENDING"
}
~~~

Client có thể gọi GET operation resource. Cần tránh polling quá dày; hỗ trợ backoff, webhook hoặc SSE khi phù hợp. Operation status cần được bảo vệ authorization và tenant scope.

### 21.1. Timeout của consumer

Worker cũng cần giới hạn:
- Max processing duration.
- Dependency call deadline.
- Message visibility/lease/ack timeout.
- Retry count và DLQ.
- Idempotency/deduplication.
- Heartbeat/lease renewal cho job dài.
- Shutdown grace period.

HTTP timeout và consumer processing timeout cần phối hợp để tránh API trả 202 nhưng job bị lặp vô hạn hoặc bị ack trước khi commit.

## 22. Xử lý caller cancellation và server shutdown

Caller có thể đóng kết nối hoặc hủy request. Ứng dụng cần xác định:
- Có thể hủy downstream call không?
- Database statement có thể cancel không?
- Nếu command đã commit, có tiếp tục xử lý outbox không?
- Có nên trả lỗi hay ghi operation state?
- Request đang chạy được drain thế nào khi pod shutdown?

Khi rolling deploy, server nên ngừng nhận request mới, chờ request đang chạy trong grace period, rồi đóng connection/pool. Nếu shutdown timeout quá ngắn, các giao dịch đang commit có thể bị gián đoạn; nếu quá dài, rollout và recovery chậm.

Không coi cancellation từ client là tín hiệu chắc chắn để rollback nghiệp vụ. Side effects cần state machine và idempotency.

## 23. Các lỗi cấu hình phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đặt connect timeout | Server có thể xử lý rất lâu sau khi kết nối | Thêm response/call deadline |
| Chỉ đặt read timeout | Pool acquisition hoặc connect vẫn chờ | Cấu hình timeout theo từng stage |
| Không đặt pool acquisition timeout | Request xếp hàng khi pool cạn | Giới hạn pending wait/count |
| Mỗi hop đặt 5 giây | Tổng call chain vượt SLO | Propagate deadline/remaining budget |
| Retry vô hạn | Retry storm và cạn tài nguyên | Max attempts, backoff, jitter, budget |
| Retry POST không idempotent | Tạo đơn/charge trùng | Idempotency key và status lookup |
| Timeout = server rollback | Hiểu sai trạng thái transaction | Kiểm tra operation state/reconcile |
| WebClient nhưng gọi block tùy tiện | Giữ thread và mất lợi ích reactive | Chọn stack và thread model nhất quán |
| Dùng read timeout làm total timeout | Stream có thể kéo dài vô hạn | Idle timeout + total deadline |
| Pool quá lớn | Gây quá tải upstream | Align pool với capacity downstream |
| Pool quá nhỏ | Pending acquisition và latency | Đo pool pressure, tune có kiểm soát |
| Log toàn bộ HTTP wire data | Lộ token/PII | Redaction và log có chọn lọc |
| Bắt mọi exception rồi trả null | Mất phân loại lỗi | Map timeout, upstream error, domain error riêng |
| Không test body chậm | Timeout chỉ đúng ở response header | Test streaming/chunked response |
| Tin client cancel dừng server | Side effect vẫn có thể commit | Idempotency, cancellation và reconciliation |

## 24. Quy trình triển khai REST API và client an toàn

**Bước 1 — Định nghĩa contract.** Chốt resource, methods, status, DTO, validation, error model, auth, pagination và versioning.

**Bước 2 — Xác định latency budget.** Dùng SLO và baseline để xác định deadline caller, budget service và timeout từng dependency.

**Bước 3 — Chọn HTTP client.** RestClient cho call đồng bộ, WebClient cho reactive/streaming, JDK/Apache/Reactor theo pool và timeout requirements.

**Bước 4 — Cấu hình pool và timeout.** Đặt connect, pool acquisition, response/read và total deadline theo semantics của thư viện; giới hạn pool/concurrency.

**Bước 5 — Xây dựng resilience policy.** Timeout, retry có giới hạn, idempotency, circuit breaker, bulkhead, rate limit và fallback hợp lệ.

**Bước 6 — Bảo vệ API.** Authentication, authorization, validation, input limits, tenant scope, SSRF protection và secret redaction.

**Bước 7 — Instrument.** Đo API latency/error, dependency latency, timeout stage, pool pending, retry, breaker và business outcome.

**Bước 8 — Test.** Contract tests, controller tests, delayed response, pool exhaustion, cancellation, duplicate side effect và load test.

**Bước 9 — Rollout.** Thử ở staging với latency injection; rollout có quan sát; điều chỉnh theo evidence thay vì tăng timeout để che lỗi.

**Bước 10 — Vận hành.** Runbook cho upstream timeout, pool exhaustion, retry storm, breaker open và dependency recovery.

## 25. Ví dụ xuyên suốt: order-service gọi inventory và payment

Giả sử POST checkout có deadline 2,5 giây. order-service gọi:
- inventory-service để reserve.
- payment-service để authorize.
- database để lưu order và outbox.

Một policy minh họa:
- Pool acquisition mỗi dependency: tối đa 100 ms.
- Connect: tối đa 250 ms.
- Response timeout inventory: 500 ms.
- Response timeout payment: 800 ms.
- Local DB/application work: có budget riêng.
- Tổng order-service deadline: 2,2 giây, chừa thời gian gateway/client.

Các call có thể tuần tự hoặc một phần song song. Nếu inventory reserve thành công nhưng payment timeout, order-service cần release reservation hoặc chuyển saga sang trạng thái pending/reconciliation theo contract. Nếu payment provider đã authorize nhưng response bị mất, retry phải dùng idempotency key và có khả năng tra cứu transaction.

Không được trả 201 Created chỉ vì đã gửi request tới payment provider. Cần xác định chính xác trạng thái đơn hàng và điều kiện tạo resource. Nếu xử lý tiếp tục bất đồng bộ, trả 202 và operation status có thể phù hợp hơn.

### 25.1. State machine ví dụ

~~~text
CREATED
  → INVENTORY_RESERVED
  → PAYMENT_PENDING
  → PAYMENT_AUTHORIZED
  → CONFIRMED

Nhánh lỗi:
  PAYMENT_PENDING → PAYMENT_UNKNOWN
  PAYMENT_UNKNOWN → RECONCILING
  RECONCILING → CONFIRMED hoặc PAYMENT_FAILED
  PAYMENT_FAILED → INVENTORY_RELEASED
~~~

Đây là state machine khái niệm. Trạng thái PAYMENT_UNKNOWN quan trọng khi timeout khiến service không biết provider đã xử lý hay chưa. Không đánh dấu FAILED ngay rồi gửi payment mới nếu giao dịch cũ có thể đã thành công.

## 26. Thiết kế API cho thao tác có thể mất kết nối

Đối với command quan trọng, cân nhắc trả một operation resource:
- POST /orders nhận lệnh và idempotency key.
- Response 202 cùng operation ID.
- GET /operations/{id} trả trạng thái.
- Khi terminal state, operation chứa kết quả hoặc link tới resource.
- Client retry POST cùng key khi không nhận được response.
- Server lưu request fingerprint và kết quả để trả nhất quán.

Cách này giảm thời gian giữ HTTP connection, nhưng cần lưu state bền, cleanup/retention, authorization và API lifecycle. Không dùng 202 chỉ để tránh đặt timeout cho một tác vụ vốn phải hoàn tất đồng bộ trong thời gian ngắn.

## 27. Checklist review trước khi đưa API/client lên production

### API contract
- [ ] URI biểu diễn resource rõ ràng.
- [ ] HTTP method và idempotency semantics đúng.
- [ ] Status code có ý nghĩa nhất quán.
- [ ] DTO tách khỏi persistence entity.
- [ ] Validation cú pháp và nghiệp vụ rõ.
- [ ] Error response không lộ nội bộ.
- [ ] Pagination/filter/sort có giới hạn.
- [ ] Authentication/authorization/tenant scope được enforce.
- [ ] OpenAPI hoặc contract được cập nhật.

### HTTP client
- [ ] Connect timeout được cấu hình.
- [ ] Pool acquisition timeout/count được cấu hình nếu có pool.
- [ ] Response/read timeout được cấu hình.
- [ ] Total call/deadline được xác định theo semantics client.
- [ ] Pool size align với downstream capacity.
- [ ] Retry có max attempts, backoff, jitter và retry budget.
- [ ] Write operation có idempotency.
- [ ] Circuit breaker/bulkhead phù hợp.
- [ ] Redirect, TLS, DNS và credential forwarding được kiểm soát.
- [ ] Cancellation và response body resource được giải phóng.

### Vận hành
- [ ] Metrics timeout theo stage/outcome.
- [ ] Dashboard pool active/pending.
- [ ] Trace dependency call.
- [ ] Alert theo user impact/SLO.
- [ ] Test delayed header/body và pool exhaustion.
- [ ] Runbook có bước xác định dependency và mitigation.
- [ ] Timeout config có validation và version tracking.

## 28. Bài tập thực hành

Một order-service Spring Boot có API POST /orders. Handler gọi pricing-service, inventory-service và payment-service bằng HTTP client mặc định, không có timeout. Khi payment-service chậm, thread pool của order-service tăng active threads, request latency p99 vượt 8 giây và người dùng bấm tạo đơn nhiều lần.

**Yêu cầu A — REST contract:** thiết kế request/response DTO, status code, validation, error response và idempotency key cho POST /orders.

**Yêu cầu B — Timeout map:** xác định pool acquisition, connect, response/read và total deadline cho từng dependency. Giải thích ngân sách tổng và phần dự phòng cho local work.

**Yêu cầu C — Client implementation:** chọn RestClient hoặc WebClient phù hợp với stack hiện tại; cấu hình connection pool, timeout tường minh và properties theo environment.

**Yêu cầu D — Failure semantics:** mô tả điều gì xảy ra khi inventory reserve thành công nhưng payment timeout; xử lý trạng thái unknown và reconciliation.

**Yêu cầu E — Retry/resilience:** xác định lỗi được retry, số lần tối đa, backoff, jitter, breaker, bulkhead và giới hạn concurrency.

**Yêu cầu F — Observability:** đề xuất metric và trace để phân biệt pool exhaustion, connect timeout, response timeout và downstream latency.

**Yêu cầu G — Testing:** viết test cho response chậm, body stream chậm, pool cạn, payment commit nhưng response mất, và duplicate POST cùng idempotency key.

**Yêu cầu H — Rollout:** đề xuất cách triển khai thay đổi timeout ở staging/canary, success criteria và rollback khi error rate tăng.

Một lời giải tốt phải chỉ ra **timeout ở tầng nào**, **tổng deadline là bao nhiêu**, **operation có thể đã commit hay chưa**, và **cách bảo đảm retry không tạo side effect trùng**.

## 29. Câu hỏi tự kiểm tra

1. REST API contract cần những thành phần nào ngoài URI?
2. PUT khác PATCH ở semantics nào?
3. Vì sao POST timeout có thể tạo giao dịch trùng khi client retry?
4. 202 Accepted có nghĩa nghiệp vụ đã hoàn tất không?
5. Connect timeout có giới hạn thời gian server xử lý request không?
6. Pool acquisition timeout giải quyết tình huống nào?
7. Read timeout và total request deadline khác nhau ra sao với streaming response?
8. Vì sao mọi hop không nên đặt cùng timeout 5 giây?
9. Làm sao truyền remaining deadline mà không reset budget?
10. Khi nào nên dùng RestClient và khi nào WebClient phù hợp?
11. JDK HttpClient có cung cấp những timeout controls nào trong ví dụ?
12. Vì sao WebClient gọi block có thể vẫn giữ servlet thread?
13. Circuit breaker khác timeout như thế nào?
14. Retry có thể khuếch đại sự cố ra sao?
15. Idempotency key cần scope và lưu trữ thế nào?
16. Vì sao client cancel không chứng minh server đã rollback?
17. Cần đo metric nào để phát hiện pool exhaustion?
18. Tại sao không log toàn bộ HTTP headers/body?
19. Khi nào nên dùng async operation resource thay vì giữ request mở?
20. Vì sao timeout config phải được review như một thay đổi capacity?

## 30. Ghi nhớ

- REST API là hợp đồng tài nguyên gồm URI, method, status, DTO, validation, security và error model.
- **Timeout phải tường minh ở nhiều giai đoạn**: chờ pool, connect, response/read và deadline tổng, theo semantics của HTTP client.
- **End-to-end deadline cần được phân bổ xuyên call chain**; mỗi service chỉ dùng phần ngân sách còn lại.
- RestClient phù hợp với call đồng bộ trong Spring hiện đại; WebClient phù hợp reactive/streaming; JDK/Apache/Reactor cung cấp các khả năng timeout và pooling khác nhau.
- Timeout không bảo đảm server chưa commit. Command cần idempotency, operation status và reconciliation.
- Retry phải có giới hạn, backoff, jitter và retry budget; kết hợp circuit breaker, bulkhead và rate limit để bảo vệ downstream.
- Test phải bao phủ pool exhaustion, response/body chậm, cancellation và side effect đã commit nhưng response mất.
- Metrics/traces cần phân biệt timeout stage, dependency, pool pressure và business outcome.
- Một hệ thống đáng tin cậy biết **khi nào chờ, chờ tối đa bao lâu, khi nào dừng và làm gì khi kết quả của thao tác chưa rõ**.
