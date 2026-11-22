# Phân biệt lỗi nghiệp vụ, lỗi đầu vào và lỗi hạ tầng trong Spring WebFlux

## 1. Vì sao cần phân loại lỗi trước khi xử lý?

Một HTTP request có thể thất bại vì nhiều lý do rất khác nhau. Client gửi JSON sai cấu trúc, người dùng yêu cầu một đơn hàng không tồn tại, quy tắc nghiệp vụ từ chối giao dịch, hoặc database/upstream service đang mất kết nối. Tất cả đều có thể xuất hiện dưới dạng một reactive error signal, nhưng **ý nghĩa, HTTP status, cách retry, cách log và trách nhiệm khắc phục** hoàn toàn khác nhau.

Nếu gom mọi exception vào một `catch` chung rồi trả 500, API sẽ gây hiểu nhầm cho client. Nếu chuyển mọi lỗi thành 400, lỗi hạ tầng sẽ bị đổ cho người dùng. Nếu retry mọi lỗi, hệ thống có thể lặp side effect, tăng tải khi dependency đang hỏng hoặc trì hoãn phản hồi cho một request vốn không thể thành công.

Trong bài này, ta dùng ba nhóm chính:

1. **Lỗi đầu vào (input/client errors):** request không đúng hợp đồng, thiếu dữ liệu, sai kiểu, sai định dạng hoặc không vượt qua validation.
2. **Lỗi nghiệp vụ (business/domain errors):** request hợp lệ về cú pháp nhưng kết quả không được phép theo trạng thái hoặc quy tắc domain.
3. **Lỗi hạ tầng (infrastructure/dependency errors):** ứng dụng không thể hoàn thành công việc vì database, message broker, dịch vụ bên ngoài, network hoặc tài nguyên vận hành gặp sự cố.

Ngoài ba nhóm trên, còn có lỗi xác thực/phân quyền và lỗi lập trình ngoài dự kiến. Chúng cần được phân loại riêng để không ép mọi tình huống vào một trong ba nhóm.

Mục tiêu không phải chỉ chọn một status code. Mục tiêu là tạo **hợp đồng lỗi ổn định**: client biết nên sửa request, hiển thị thông báo nghiệp vụ, thử lại sau hay báo lỗi không mong đợi; đội vận hành có đủ thông tin để tìm nguyên nhân mà không làm lộ dữ liệu nhạy cảm.

## 2. Vòng đời lỗi trong một pipeline Reactor

Trong WebFlux, lỗi thường đi qua `Mono` hoặc `Flux` dưới dạng tín hiệu `onError`. Một Publisher chỉ có một terminal outcome: hoàn tất (`onComplete`) hoặc lỗi (`onError`); sau terminal signal đó, nó không tiếp tục phát dữ liệu bình thường.

~~~java
Mono<Order> order = repository.findById(id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
~~~

Nếu repository không tìm thấy dữ liệu, `switchIfEmpty` thay completion rỗng bằng một error signal. Lỗi đi qua các toán tử downstream cho tới khi được xử lý hoặc tới ranh giới HTTP.

Các toán tử thường gặp:

| Toán tử | Vai trò | Có xử lý lỗi không? |
| --- | --- | --- |
| `doOnError` | Quan sát/log/đếm metric khi lỗi đi qua | Không; lỗi vẫn tiếp tục |
| `onErrorMap` | Chuyển exception sang loại khác, giữ nguyên nguyên nhân nếu cần | Chuyển loại lỗi, nhưng vẫn là lỗi |
| `onErrorResume` | Chọn Publisher thay thế khi gặp loại lỗi phù hợp | Có thể phục hồi hoặc phát lỗi mới |
| `onErrorReturn` | Thay lỗi bằng một giá trị mặc định | Có thể che mất thất bại |
| `retryWhen` | Subscribe lại nguồn theo chính sách retry | Có thử lại; không bảo đảm lần sau thành công |
| `timeout` | Phát lỗi nếu nguồn không đáp ứng trong thời hạn | Tạo lỗi timeout |
| `switchIfEmpty` | Xử lý trường hợp không có phần tử | Không phải lỗi nếu nguồn complete rỗng |

Ví dụ, `doOnError` không biến lỗi thành thành công:

~~~java
return service.load(id)
    .doOnError(error -> log.error("load failed", error));
~~~

Ngược lại, `onErrorResume` có thể thay lỗi bằng response dự phòng:

~~~java
return cache.find(id)
    .onErrorResume(CacheUnavailableException.class,
        error -> database.find(id));
~~~

Đây là phục hồi có chủ đích: cache hỏng nhưng database vẫn là nguồn dữ liệu chính thức. Không nên dùng `onErrorResume(error -> Mono.empty())` một cách tổng quát vì nó có thể biến lỗi thật thành “không tìm thấy dữ liệu”, khiến API trả sai status và che giấu sự cố.

**Lỗi reactive không đồng nghĩa với exception đồng bộ.** Exception được ném bên trong `map`, `flatMap` hoặc callback thường được Reactor chuyển thành `onError`. Vì vậy phải thiết kế xử lý lỗi theo pipeline, không dựa vào `try/catch` bao quanh lúc tạo Publisher.

## 3. Nhóm 1 — Lỗi đầu vào: client cần sửa request

Lỗi đầu vào xảy ra khi request vi phạm hợp đồng API trước hoặc trong quá trình chuyển dữ liệu thành đối tượng ứng dụng.

### 3.1. Những tình huống thường gặp

- JSON sai cú pháp hoặc không thể decode thành DTO.
- Thiếu trường bắt buộc, chuỗi rỗng, số lượng âm hoặc giá trị nằm ngoài giới hạn.
- Path variable/query parameter không chuyển được sang kiểu đích.
- `Content-Type` không được endpoint hỗ trợ.
- Request body vượt giới hạn kích thước.
- Dữ liệu có cú pháp hợp lệ nhưng không đạt validation ở tầng request.

Cần phân biệt **parse/validation** với **business rule**. Ví dụ, `quantity = -1` là đầu vào không hợp lệ nếu hợp đồng DTO yêu cầu số lượng dương. Nhưng nếu `quantity = 5` hợp lệ mà kho chỉ còn 2 sản phẩm, đó là kết quả nghiệp vụ, có thể được biểu diễn là không đủ hàng hoặc xung đột trạng thái.

### 3.2. HTTP status phù hợp

| Tình huống | Status thường dùng | Ý nghĩa |
| --- | --- | --- |
| Body malformed, DTO không hợp lệ | 400 Bad Request | Client cần sửa nội dung request |
| Sai `Content-Type`/media type request | 415 Unsupported Media Type | Server không đọc định dạng body đó |
| Không có representation response phù hợp với `Accept` | 406 Not Acceptable | Server không thể trả định dạng client yêu cầu |
| Payload vượt giới hạn | 413 Payload Too Large | Client cần giảm kích thước |
| Path/method không có route phù hợp | 404 hoặc 405 | Sai tài nguyên hoặc HTTP method |

Không phải mọi lỗi xảy ra trước khi vào service đều có cùng status. Ví dụ, JSON hợp lệ nhưng không thỏa validation thường là 400; JSON hợp lệ và validation đạt nhưng quy tắc domain từ chối lại là lỗi nghiệp vụ.

### 3.3. Validation ở DTO

Dùng Bean Validation để diễn đạt điều kiện của request:

~~~java
public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) @Max(100) int quantity
) {}
~~~

Trong controller:

~~~java
@PostMapping("/orders")
public Mono<OrderView> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Spring WebFlux giải mã body rồi thực hiện validation trước khi gọi method controller. Nếu dữ liệu không hợp lệ, framework phát lỗi binding/validation, thường là `WebExchangeBindException`, để xử lý ở ranh giới HTTP.

Với tham số reactive như `@RequestBody Mono<CreateOrderRequest>`, validation được áp dụng trên giá trị sau khi decode theo cơ chế hỗ trợ của WebFlux. Dù dùng dạng nào, đừng tự subscribe vào body chỉ để gọi validator; hãy để framework và pipeline quản lý việc đọc.

### 3.4. Validation không thay thế kiểm tra nghiệp vụ

Ví dụ:

- `sku` không được để trống: validation đầu vào.
- `quantity` phải lớn hơn 0: validation đầu vào.
- SKU không còn bán: quy tắc domain.
- Người dùng không sở hữu đơn hàng: phân quyền/domain tùy hợp đồng.
- Kho hết hàng sau khi kiểm tra trạng thái: kết quả nghiệp vụ.

Đưa mọi quy tắc domain vào Bean Validation sẽ khiến DTO gắn chặt với trạng thái database hoặc dịch vụ ngoài. Validation ở request nên nhanh, xác định và kiểm tra hình dạng/giới hạn cơ bản. Các quy tắc cần trạng thái hiện tại nên nằm trong service/domain flow.

## 4. Nhóm 2 — Lỗi nghiệp vụ: request hợp lệ nhưng không thể thực hiện

Lỗi nghiệp vụ xảy ra khi hệ thống hiểu request nhưng không thể hoặc không được phép hoàn thành thao tác theo trạng thái hiện tại.

### 4.1. Ví dụ

- Đơn hàng không tồn tại.
- Sản phẩm không còn hàng.
- Không thể chuyển trạng thái từ `CANCELLED` sang `SHIPPED`.
- Mã giao dịch đã được sử dụng.
- Tài khoản không đủ số dư.
- Một yêu cầu trùng lặp xung đột với tài nguyên hiện tại.

Lỗi này không nhất thiết là bug hay sự cố hạ tầng. Hệ thống có thể hoạt động hoàn toàn bình thường và đang từ chối một thao tác hợp lệ về mặt cú pháp.

### 4.2. Status code là một phần của hợp đồng domain

| Tình huống | Status thường dùng | Ghi chú |
| --- | --- | --- |
| Resource không tồn tại | 404 Not Found | Có thể là lỗi truy vấn tài nguyên |
| Trạng thái hiện tại xung đột với thao tác | 409 Conflict | Ví dụ đơn đã hủy nhưng client yêu cầu giao hàng |
| Nội dung hợp lệ về cú pháp nhưng không thể xử lý theo quy tắc API | 422 Unprocessable Content | Dùng khi hợp đồng API phân biệt rõ với 400 |
| Người dùng đã xác thực nhưng không có quyền | 403 Forbidden | Thuộc authorization/security, không phải lỗi input thông thường |

Không có một bảng ánh xạ duy nhất đúng cho mọi domain. Ví dụ, “hết hàng” có thể được API coi là 409 do trạng thái kho xung đột, 422 do điều kiện nghiệp vụ không thỏa, hoặc trả 200 với trạng thái đơn hàng từ chối trong một quy trình bất đồng bộ. Hãy chọn theo hợp đồng API và giữ nhất quán.

### 4.3. Dùng exception có tên miền rõ ràng

~~~java
public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(long id) {
        super("Order not found: " + id);
    }
}

public final class OrderConflictException extends RuntimeException {
    public OrderConflictException(String message) {
        super(message);
    }
}
~~~

Service phát exception có ý nghĩa domain:

~~~java
public Mono<Order> findRequired(long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
}
~~~

Không dùng `IllegalArgumentException` cho tất cả lỗi nghiệp vụ. Exception quá chung khiến tầng HTTP không biết nên trả 400, 404 hay 409. Một kiểu lỗi có tên rõ giúp mapping, test và log dễ hiểu.

### 4.4. Không để tầng HTTP quyết định quy tắc domain

Controller có thể gọi service và trả Publisher:

~~~java
@GetMapping("/orders/{id}")
public Mono<OrderView> get(@PathVariable long id) {
    return orderService.findRequired(id)
        .map(OrderView::from);
}
~~~

Service quyết định đơn hàng có tồn tại và thao tác có hợp lệ không. Lớp HTTP chỉ chuyển kết quả domain thành status/body. Tránh đặt điều kiện như “nếu trạng thái đơn là CANCELLED thì trả 409” rải rác trong nhiều controller.

## 5. Nhóm 3 — Lỗi hạ tầng: ứng dụng không hoàn thành vì dependency hoặc môi trường

Lỗi hạ tầng xảy ra khi ứng dụng không thể thực hiện công việc do tài nguyên hoặc dịch vụ phụ thuộc không sẵn sàng.

### 5.1. Nguồn lỗi thường gặp

- Database không kết nối được, connection pool cạn hoặc transaction timeout.
- Redis/cache, message broker hoặc object storage không phản hồi.
- Dịch vụ HTTP bên ngoài trả lỗi 5xx, đóng kết nối hoặc timeout.
- DNS, TLS, network route hoặc credential kết nối dependency có vấn đề.
- Thread pool, queue hoặc giới hạn tài nguyên bị cạn.
- Circuit breaker đang mở vì dependency có tỷ lệ lỗi cao.

Không nên phân loại mọi exception từ thư viện thành lỗi hạ tầng ngay lập tức. Ví dụ, một HTTP 404 từ upstream có thể có nghĩa tài nguyên domain không tồn tại; nó cũng có thể chỉ ra URL cấu hình sai. Cần hiểu hợp đồng của dependency trước khi chuyển thành lỗi public API.

### 5.2. Status code thường dùng

| Tình huống | Status thường dùng | Ý nghĩa |
| --- | --- | --- |
| Dịch vụ tạm thời không khả dụng | 503 Service Unavailable | Client có thể thử lại sau |
| Gateway/proxy chờ upstream quá lâu | 504 Gateway Timeout | Upstream không phản hồi đúng hạn |
| Lỗi nội bộ không phân loại được | 500 Internal Server Error | Server không hoàn thành request |
| Giới hạn tải/rate limit | 429 Too Many Requests | Client cần giảm tốc hoặc chờ theo Retry-After |

Nếu API đang hoạt động như gateway gọi dịch vụ khác, 504 có thể mô tả timeout upstream. Nếu một ứng dụng đơn giản timeout khi xử lý nội bộ, 503 hoặc 500 có thể phù hợp hơn theo semantics của API. Không ánh xạ mọi `TimeoutException` thành 504 mà không xét vai trò của service.

### 5.3. Tạo exception hạ tầng có ngữ nghĩa

~~~java
public final class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(Throwable cause) {
        super("Inventory dependency is unavailable", cause);
    }
}

public final class UpstreamTimeoutException extends RuntimeException {
    public UpstreamTimeoutException(Throwable cause) {
        super("Inventory dependency timed out", cause);
    }
}
~~~

Giữ `cause` để log và điều tra. Nhưng **không trả message kỹ thuật hoặc cause ra client**. Client chỉ cần biết dịch vụ tạm thời không sẵn sàng hoặc upstream timeout, không cần hostname database, câu SQL, stack trace hay token.

### 5.4. Chuyển lỗi thư viện thành lỗi ứng dụng tại ranh giới dependency

Ví dụ với WebClient:

~~~java
public Mono<Inventory> loadInventory(String sku) {
    return webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .onStatus(HttpStatusCode::is5xxServerError,
            response -> Mono.error(
                new InventoryUnavailableException(
                    new IllegalStateException("upstream 5xx"))))
        .bodyToMono(Inventory.class)
        .onErrorMap(WebClientRequestException.class,
            error -> new InventoryUnavailableException(error));
}
~~~

Đây là mã minh họa cho việc chuyển lỗi transport/5xx thành exception của ứng dụng. Trong thực tế, hãy phân biệt status upstream theo hợp đồng: 404 có thể trở thành `InventoryNotFoundException`; 429 có thể cần backoff; 401/403 upstream thường là lỗi credential/service configuration, không nên trả nguyên status đó cho người gọi public API.

## 6. Bảng phân loại tổng hợp

| Câu hỏi chẩn đoán | Nhóm lỗi | Hướng xử lý |
| --- | --- | --- |
| Request có đúng cú pháp, kiểu và giới hạn không? | Đầu vào | Trả 400/413/415/406 phù hợp; nêu trường cần sửa |
| Request hợp lệ nhưng trạng thái domain từ chối thao tác? | Nghiệp vụ | Trả 404/409/422 hoặc kết quả domain theo hợp đồng |
| Dependency có sẵn sàng và phản hồi đúng hạn không? | Hạ tầng | Timeout, retry có giới hạn, circuit breaker, 503/504 |
| Lỗi không được dự kiến và không có mapping? | Bug/unknown | 500, log đầy đủ ở server |
| Người gọi có danh tính và quyền phù hợp? | Security | 401/403, không tiết lộ tài nguyên nhạy cảm |

Một cách thực tế để phân loại là xem **ai có thể khắc phục**:

- Client sửa body/header/path: lỗi đầu vào.
- Người dùng hoặc quy trình nghiệp vụ thay đổi trạng thái/đưa ra lựa chọn khác: lỗi nghiệp vụ.
- Đội vận hành khôi phục database/network/upstream hoặc giảm tải: lỗi hạ tầng.
- Developer sửa logic: lỗi lập trình.

## 7. Tạo hợp đồng lỗi ổn định cho API

### 7.1. Không trả exception class hoặc stack trace

Một error response tốt nên có:

- `timestamp`: thời điểm lỗi.
- `status`: HTTP status.
- `code`: mã lỗi ổn định để client xử lý.
- `message`: thông báo an toàn, dễ hiểu.
- `path`: endpoint đã gọi.
- `traceId`/`requestId`: mã tương quan để hỗ trợ tra log.

Ví dụ response:

~~~json
{
  "timestamp": "2026-11-08T02:00:00Z",
  "status": 503,
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Inventory service is temporarily unavailable.",
  "path": "/api/orders",
  "traceId": "9b8d..."
}
~~~

Thời gian và trace ID ở trên chỉ minh họa định dạng. API thật nên giữ tên field và mã lỗi ổn định giữa các phiên bản.

### 7.2. Mã lỗi ổn định quan trọng hơn message

Client nên dựa vào `code` như `ORDER_NOT_FOUND`, `ORDER_CONFLICT`, `REQUEST_VALIDATION_FAILED` hoặc `INVENTORY_UNAVAILABLE`, không phân tích chuỗi `message`. Message có thể được bản địa hóa hoặc chỉnh sửa; code là phần hợp đồng máy đọc.

Không đưa tên Java exception vào response như `"error": "InventoryUnavailableException"` vì nó ràng buộc public API với implementation nội bộ.

### 7.3. Không tiết lộ thông tin nội bộ

Không trả cho client:

- Stack trace hoặc class/package nội bộ.
- SQL, tên bảng, connection string, hostname hoặc IP nội bộ.
- Access token, cookie, mật khẩu, secret hoặc header nhạy cảm.
- Raw message từ dependency nếu có thể chứa dữ liệu người dùng hoặc hạ tầng.
- Dữ liệu của resource mà caller không có quyền xem.

Hãy ghi chi tiết ở server với trace ID, còn response chỉ chứa thông tin cần thiết để client hành động.

### 7.4. `Retry-After` và retry hint

Với lỗi tạm thời như 503 hoặc 429, server có thể gửi `Retry-After` nếu biết thời điểm phù hợp. Không nên khuyến khích client retry ngay liên tục. Với lỗi nghiệp vụ hoặc validation, retry nguyên request không thay đổi thường không có ích.

## 8. Xử lý lỗi ở đúng tầng trong Spring WebFlux

Có nhiều lớp xử lý lỗi; mỗi lớp có phạm vi riêng.

### 8.1. Xử lý cục bộ bằng Reactor

Dùng `onErrorResume` khi một thành phần có chiến lược phục hồi cụ thể:

~~~java
return cache.get(key)
    .onErrorResume(CacheUnavailableException.class,
        error -> database.find(key));
~~~

Nếu cache là tối ưu hóa và database là nguồn dữ liệu chính, fallback này hợp lý. Nếu cả cache và database đều lỗi, hãy để lỗi tiếp tục; không trả giá trị rỗng giả.

Dùng `onErrorMap` để chuẩn hóa lỗi tại ranh giới:

~~~java
return repository.save(entity)
    .onErrorMap(DuplicateKeyException.class,
        error -> new OrderConflictException("Order already exists"));
~~~

Giữ nguyên nguyên nhân khi chuyển exception. Đừng đổi mọi lỗi database thành `OrderConflictException`; chỉ chuyển khi đã xác định đúng điều kiện duplicate theo hợp đồng.

### 8.2. `@RestControllerAdvice` và `@ExceptionHandler`

Đối với annotated controller, `@RestControllerAdvice` là nơi phù hợp để ánh xạ exception thành HTTP status và error body thống nhất.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> notFound(
        OrderNotFoundException error,
        ServerWebExchange exchange
    ) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(ApiError.of(
                "ORDER_NOT_FOUND",
                "Order was not found.",
                exchange
            ));
    }
}
~~~

Spring WebFlux hỗ trợ exception handler đồng bộ hoặc reactive. Chọn một kiểu return nhất quán trong ứng dụng. Với nhiều lỗi, tạo các handler cụ thể và một fallback cuối cho exception không mong đợi.

### 8.3. `WebExceptionHandler`

`WebExceptionHandler` nằm ở tầng ngoài của WebFlux handler/filter chain. Nó phù hợp với lỗi thoát ra từ filter hoặc phần web pipeline mà `@ControllerAdvice` không xử lý, và có thể dùng trong cấu hình toàn cục.

Phân biệt:

| Cơ chế | Phạm vi |
| --- | --- |
| `onErrorResume` / `onErrorMap` | Một Publisher hoặc một ranh giới service |
| `@ExceptionHandler` / `@RestControllerAdvice` | Annotated controller dispatch |
| `HandlerFilterFunction` | Functional route được gắn filter |
| `WebFilter` | Chuỗi WebFlux rộng hơn, trước/sau handler |
| `WebExceptionHandler` | Lỗi thoát ra ngoài filter/handler chain |

Functional endpoint không phải annotated controller; nếu cần xử lý lỗi riêng theo router, có thể dùng `HandlerFilterFunction`. Với lỗi toàn pipeline, cân nhắc `WebExceptionHandler`.

### 8.4. Không bắt lỗi quá sớm

Nếu service bắt mọi exception và trả `Mono.empty()`, tầng HTTP không còn phân biệt được resource không tồn tại, dependency hỏng hay bug. Chỉ xử lý cục bộ những lỗi mà thành phần đó thực sự có thể phục hồi; các lỗi còn lại phải tiếp tục truyền lên.

## 9. Retry, timeout và circuit breaker: chỉ áp dụng cho lỗi có thể phục hồi

### 9.1. Không retry lỗi đầu vào hoặc lỗi nghiệp vụ

Các trường hợp thường không nên retry tự động:

- DTO thiếu trường hoặc sai định dạng.
- Không đủ hàng theo trạng thái hiện tại.
- Đơn hàng không tồn tại.
- Người dùng không có quyền.
- Trạng thái domain xung đột.

Retry cùng request trong cùng điều kiện thường chỉ tạo thêm tải và lặp lại kết quả từ chối.

### 9.2. Retry lỗi hạ tầng có điều kiện

Reactor hỗ trợ `retryWhen`:

~~~java
return webClientCall()
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(this::isTransientFailure)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure())
    );
~~~

Đây là mẫu minh họa. `isTransientFailure` phải là hàm do ứng dụng định nghĩa để chỉ nhận những lỗi có thể phục hồi, ví dụ một số lỗi kết nối hoặc 503 tạm thời. Hai lần retry nghĩa là tối đa ba lần thực hiện tính cả lần đầu.

Retry cần có:

- Giới hạn số lần và thời gian tổng.
- Exponential backoff và jitter để tránh nhiều client retry cùng lúc.
- Timeout cho từng lần gọi và deadline tổng cho request.
- Metric số lần retry, số lần hết retry và latency.
- Chính sách rõ khi client đã hủy request.

### 9.3. Cẩn thận với side effect và idempotency

Một thao tác POST tạo đơn hàng có thể đã được database commit nhưng response từ upstream bị mất. Nếu retry toàn bộ thao tác, có nguy cơ tạo hai đơn. Với thao tác ghi, cần thiết kế idempotency key, unique constraint, transaction hoặc cơ chế deduplication phù hợp.

Không retry một Publisher tùy tiện chỉ vì nó phát lỗi. Phải hiểu side effect đã xảy ra tới đâu và nguồn có thể được thực hiện lại an toàn không.

### 9.4. Timeout không tự giải quyết resource leak

~~~java
return inventoryClient.reserve(sku, quantity)
    .timeout(Duration.ofMillis(500));
~~~

Timeout phát lỗi khi operation không hoàn thành trong hạn. Driver/client cần hỗ trợ cancellation đúng cách để hủy request hoặc giải phóng resource. Không phải mọi hệ thống bên ngoài đều rollback công việc đã bắt đầu khi subscriber cancel.

### 9.5. Circuit breaker và bulkhead

Circuit breaker có thể tạm ngừng gọi dependency liên tục thất bại, giúp hệ thống không tiêu tốn tài nguyên vào một upstream đang hỏng. Bulkhead giới hạn số thao tác đồng thời để một dependency không chiếm hết tài nguyên của ứng dụng.

Các cơ chế này thường được triển khai bằng thư viện như Resilience4j hoặc gateway/client policy. Chúng không thay thế phân loại lỗi: lỗi đầu vào vẫn là lỗi đầu vào, domain conflict vẫn là conflict, còn circuit-open là một tín hiệu dependency tạm thời không sẵn sàng.

## 10. Quan sát lỗi: log, trace và metric

### 10.1. Dùng request ID/correlation ID

Một request ID nên đi cùng log của filter, controller, service và lời gọi dependency. Có thể tạo ID tại `WebFilter`, đặt vào exchange attribute và response header. Nếu nhận ID từ gateway, cần xác định gateway có đáng tin và chuẩn hóa giá trị đầu vào.

Không lưu request ID trong field mutable của singleton service vì nhiều request chạy đồng thời có thể ghi đè lẫn nhau.

### 10.2. Log một lần ở ranh giới phù hợp

Nếu mọi lớp đều log cùng một exception ở mức ERROR, một lỗi sẽ tạo nhiều bản ghi trùng nhau. Một cách làm tốt:

- Service ghi context cần thiết khi chuyển lỗi dependency thành exception ứng dụng.
- Global exception handler ghi lỗi chưa được dự kiến hoặc lỗi cần cảnh báo.
- Lỗi validation/business có thể ghi ở mức INFO/WARN theo policy, không nhất thiết là ERROR.
- Luôn có trace ID để nối các log cùng request.

Không log request body hoặc header nhạy cảm mặc định.

### 10.3. Metric nên dùng nhãn có cardinality thấp

Có thể đếm request theo status và error code ổn định:

- `http.server.requests` theo method, route template, status.
- `api.errors` theo nhóm `INPUT`, `BUSINESS`, `INFRASTRUCTURE`, `UNKNOWN`.
- `dependency.calls` theo dependency, outcome và timeout/retry.
- `retry.exhausted` và `circuit.breaker.state`.

Không dùng user ID, order ID, URL chứa path variable hoặc exception message làm metric tag; số lượng giá trị có thể tăng không giới hạn và gây áp lực lên metrics backend.

## 11. Ví dụ Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Ví dụ mô phỏng API tạo và tra cứu đơn hàng. Nó phân biệt:

- Validation đầu vào: SKU rỗng hoặc số lượng ngoài giới hạn → 400.
- Lỗi nghiệp vụ: đơn không tồn tại → 404; SKU mô phỏng xung đột → 409.
- Lỗi hạ tầng: inventory service mô phỏng không sẵn sàng → 503; phản hồi quá chậm → 504.
- Lỗi ngoài dự kiến → 500 với message an toàn.

Dự án dùng Spring Boot **3.5.7**, Java 17, WebFlux và Bean Validation.

### 11.1. Cấu trúc project

~~~text
webflux-error-taxonomy/
├── pom.xml
└── src/main/java/example/errors/
    ├── OrderApiApplication.java
    ├── OrderController.java
    ├── OrderService.java
    ├── InventoryGateway.java
    ├── RequestIdWebFilter.java
    ├── ApiExceptionHandler.java
    ├── ApiError.java
    ├── CreateOrderRequest.java
    ├── OrderView.java
    ├── OrderNotFoundException.java
    ├── OrderConflictException.java
    ├── InventoryUnavailableException.java
    └── UpstreamTimeoutException.java
└── src/test/java/example/errors/
    └── OrderApiIntegrationTest.java
~~~

### 11.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-error-taxonomy</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. `OrderApiApplication.java`

~~~java
package example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
~~~

### 11.4. `CreateOrderRequest.java`

~~~java
package example.errors;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) @Max(100) int quantity
) {}
~~~

### 11.5. `OrderView.java`

~~~java
package example.errors;

public record OrderView(
    long id,
    String sku,
    int quantity,
    String status
) {}
~~~

### 11.6. Các exception có ý nghĩa rõ ràng

`OrderNotFoundException.java`:

~~~java
package example.errors;

public final class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(long id) {
        super("Order not found: " + id);
    }
}
~~~

`OrderConflictException.java`:

~~~java
package example.errors;

public final class OrderConflictException extends RuntimeException {

    public OrderConflictException(String message) {
        super(message);
    }
}
~~~

`InventoryUnavailableException.java`:

~~~java
package example.errors;

public final class InventoryUnavailableException extends RuntimeException {

    public InventoryUnavailableException() {
        super("Inventory dependency is unavailable");
    }

    public InventoryUnavailableException(Throwable cause) {
        super("Inventory dependency is unavailable", cause);
    }
}
~~~

`UpstreamTimeoutException.java`:

~~~java
package example.errors;

public final class UpstreamTimeoutException extends RuntimeException {

    public UpstreamTimeoutException(Throwable cause) {
        super("Inventory dependency timed out", cause);
    }
}
~~~

### 11.7. `InventoryGateway.java`

Đây là gateway mô phỏng dependency để ví dụ chạy độc lập, không cần database hay dịch vụ inventory thật:

~~~java
package example.errors;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class InventoryGateway {

    public Mono<Void> reserve(String sku, int quantity) {
        Mono<Void> operation;

        if ("DOWN".equalsIgnoreCase(sku)) {
            operation = Mono.error(
                new InventoryUnavailableException());
        } else if ("SLOW".equalsIgnoreCase(sku)) {
            operation = Mono.delay(Duration.ofSeconds(2)).then();
        } else if ("CONFLICT".equalsIgnoreCase(sku)) {
            operation = Mono.error(
                new OrderConflictException(
                    "Inventory reservation conflicts with current state"));
        } else {
            operation = Mono.empty();
        }

        return operation
            .timeout(Duration.ofMillis(250))
            .onErrorMap(
                TimeoutException.class,
                UpstreamTimeoutException::new
            );
    }
}
~~~

Trong hệ thống thật, thay gateway mô phỏng bằng WebClient, R2DBC hoặc client tương ứng. Chỉ chuyển các lỗi kết nối/timeout/5xx đã được xác định sang exception hạ tầng. Không đổi tất cả lỗi dependency thành 503.

### 11.8. `OrderService.java`

~~~java
package example.errors;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private record StoredOrder(
        long id,
        String sku,
        int quantity
    ) {}

    private final InventoryGateway inventory;
    private final AtomicLong sequence = new AtomicLong(100);
    private final ConcurrentMap<Long, StoredOrder> orders =
        new ConcurrentHashMap<>();

    public OrderService(InventoryGateway inventory) {
        this.inventory = inventory;
    }

    public Mono<OrderView> create(CreateOrderRequest request) {
        return inventory.reserve(request.sku(), request.quantity())
            .then(Mono.fromSupplier(() -> {
                long id = sequence.incrementAndGet();
                StoredOrder order = new StoredOrder(
                    id, request.sku(), request.quantity());
                orders.put(id, order);

                return new OrderView(
                    id, order.sku(), order.quantity(), "CREATED");
            }));
    }

    public Mono<OrderView> findById(long id) {
        StoredOrder order = orders.get(id);

        if (order == null) {
            return Mono.empty();
        }

        return Mono.just(new OrderView(
            order.id(), order.sku(), order.quantity(), "CREATED"));
    }
}
~~~

Map đồng thời và `AtomicLong` chỉ phục vụ demo trong một process. Dữ liệu sẽ mất khi ứng dụng restart. Hệ thống production nên dùng repository/database và transaction phù hợp.

### 11.9. `OrderController.java`

~~~java
package example.errors;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<OrderView>> create(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        return service.create(request)
            .map(order -> ResponseEntity
                .created(URI.create("/api/orders/" + order.id()))
                .body(order));
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<OrderView>> get(
        @PathVariable long id
    ) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(id)))
            .map(ResponseEntity::ok);
    }
}
~~~

`@Valid` xử lý lỗi đầu vào trước khi method chạy. Các exception từ service tiếp tục đi trong reactive pipeline và được `ApiExceptionHandler` ánh xạ thành HTTP response.

### 11.10. `RequestIdWebFilter.java`

~~~java
package example.errors;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestIdWebFilter implements WebFilter {

    public static final String ATTRIBUTE =
        RequestIdWebFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(ATTRIBUTE, requestId);
        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);

        return chain.filter(exchange);
    }
}
~~~

Mỗi request có một ID riêng. Filter không tự subscribe; nó trả về Publisher của `chain.filter(exchange)` để framework quản lý lifecycle.

### 11.11. `ApiError.java`

~~~java
package example.errors;

import java.time.Instant;

public record ApiError(
    Instant timestamp,
    int status,
    String code,
    String message,
    String path,
    String traceId
) {}
~~~

### 11.12. `ApiExceptionHandler.java`

~~~java
package example.errors;

import java.time.Instant;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
        OrderNotFoundException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.NOT_FOUND,
            "ORDER_NOT_FOUND",
            "Order was not found.",
            exchange
        );
    }

    @ExceptionHandler(OrderConflictException.class)
    public ResponseEntity<ApiError> conflict(
        OrderConflictException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.CONFLICT,
            "ORDER_CONFLICT",
            "The requested operation conflicts with the current order or inventory state.",
            exchange
        );
    }

    @ExceptionHandler(InventoryUnavailableException.class)
    public ResponseEntity<ApiError> inventoryUnavailable(
        InventoryUnavailableException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.SERVICE_UNAVAILABLE,
            "INVENTORY_UNAVAILABLE",
            "Inventory service is temporarily unavailable.",
            exchange
        );
    }

    @ExceptionHandler(UpstreamTimeoutException.class)
    public ResponseEntity<ApiError> upstreamTimeout(
        UpstreamTimeoutException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.GATEWAY_TIMEOUT,
            "INVENTORY_TIMEOUT",
            "Inventory service did not respond in time.",
            exchange
        );
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> validationFailed(
        WebExchangeBindException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.BAD_REQUEST,
            "REQUEST_VALIDATION_FAILED",
            "One or more request fields are invalid.",
            exchange
        );
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ApiError> invalidInput(
        ServerWebInputException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.BAD_REQUEST,
            "INVALID_REQUEST_BODY",
            "The request body or parameter could not be read.",
            exchange
        );
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(
        Exception error,
        ServerWebExchange exchange
    ) {
        // Log full details server-side with the request ID.
        // Never send error.getMessage() or the stack trace to the client.
        return response(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected server error occurred.",
            exchange
        );
    }

    private ResponseEntity<ApiError> response(
        HttpStatus status,
        String code,
        String message,
        ServerWebExchange exchange
    ) {
        String traceId = String.valueOf(
            exchange.getAttribute(RequestIdWebFilter.ATTRIBUTE));

        ApiError body = new ApiError(
            Instant.now(),
            status.value(),
            code,
            message,
            exchange.getRequest().getPath().value(),
            traceId
        );

        return ResponseEntity.status(status).body(body);
    }
}
~~~

Trong class này, các exception cụ thể được xử lý trước fallback `Exception`. Không dùng `error.getMessage()` làm response message. Trong ứng dụng thật, hãy bổ sung logger ở fallback và chỉ log chi tiết một lần theo policy. Có thể thêm handler cho các lỗi validation method, security hoặc rate limit tùy API.

### 11.13. Chạy ứng dụng và thử từng nhóm lỗi

Từ thư mục chứa `pom.xml`, chạy:

~~~bash
mvn spring-boot:run
~~~

**A. Request hợp lệ — tạo đơn hàng:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"PEN","quantity":2}'
~~~

Kết quả chính dự kiến: HTTP 201 Created, có `Location: /api/orders/101` và body tương tự:

~~~json
{"id":101,"sku":"PEN","quantity":2,"status":"CREATED"}
~~~

**B. Lỗi đầu vào — SKU rỗng và quantity bằng 0:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":0}'
~~~

Kết quả dự kiến: HTTP 400, `code` là `REQUEST_VALIDATION_FAILED`.

**C. Lỗi nghiệp vụ — xung đột tồn kho:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"CONFLICT","quantity":1}'
~~~

Kết quả dự kiến: HTTP 409, `code` là `ORDER_CONFLICT`.

**D. Lỗi hạ tầng — inventory service không sẵn sàng:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"DOWN","quantity":1}'
~~~

Kết quả dự kiến: HTTP 503, `code` là `INVENTORY_UNAVAILABLE`.

**E. Lỗi hạ tầng — upstream timeout:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"SLOW","quantity":1}'
~~~

Kết quả dự kiến: HTTP 504 sau khoảng 250 ms, `code` là `INVENTORY_TIMEOUT`.

**F. Lỗi nghiệp vụ — đơn không tồn tại:**

~~~bash
curl -i http://localhost:8080/api/orders/999999
~~~

Kết quả dự kiến: HTTP 404, `code` là `ORDER_NOT_FOUND`.

Các body lỗi có cùng cấu trúc `ApiError`; giá trị timestamp, path và traceId thay đổi theo request. Ví dụ 503:

~~~json
{
  "timestamp": "2026-11-08T02:00:00Z",
  "status": 503,
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Inventory service is temporarily unavailable.",
  "path": "/api/orders",
  "traceId": "..."
}
~~~

## 12. Kiểm thử hợp đồng lỗi bằng WebTestClient

Kiểm thử status và error code thay vì phụ thuộc vào chuỗi exception nội bộ:

~~~java
package example.errors;

import static org.springframework.http.MediaType.APPLICATION_JSON;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderApiIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void invalidInputReturns400() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("REQUEST_VALIDATION_FAILED");
    }

    @Test
    void businessConflictReturns409() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("CONFLICT", 1))
            .exchange()
            .expectStatus().isEqualTo(409)
            .expectBody()
            .jsonPath("$.code").isEqualTo("ORDER_CONFLICT");
    }

    @Test
    void dependencyUnavailableReturns503() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("DOWN", 1))
            .exchange()
            .expectStatus().isEqualTo(503)
            .expectHeader().exists("X-Request-Id")
            .expectBody()
            .jsonPath("$.code").isEqualTo("INVENTORY_UNAVAILABLE");
    }

    @Test
    void dependencyTimeoutReturns504() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("SLOW", 1))
            .exchange()
            .expectStatus().isEqualTo(504)
            .expectBody()
            .jsonPath("$.code").isEqualTo("INVENTORY_TIMEOUT");
    }

    @Test
    void missingOrderReturns404() {
        client.get()
            .uri("/api/orders/999999")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Test tích hợp kiểm tra HTTP boundary. Ngoài ra nên kiểm thử riêng service bằng `StepVerifier` để xác minh domain Publisher phát giá trị, complete rỗng hoặc lỗi đúng loại. Ví dụ:

~~~java
StepVerifier.create(service.findById(999999))
    .expectNextCount(0)
    .verifyComplete();
~~~

Với method `findById`, complete rỗng là hợp đồng repository; controller chuyển trạng thái đó thành `OrderNotFoundException`. Test hai lớp riêng giúp biết lỗi nằm ở domain service hay ở HTTP mapping.

## 13. Các lỗi thiết kế thường gặp

**Lỗi 1 — Trả 500 cho mọi exception.** Client không biết request cần sửa hay server đang hỏng. Tạo exception taxonomy và mapping rõ ràng.

**Lỗi 2 — Trả 400 cho lỗi database.** Client không thể sửa request để khôi phục database. Phân loại dependency failure và trả status phù hợp như 503/504.

**Lỗi 3 — Trả 500 cho validation.** Dữ liệu sai thuộc trách nhiệm client; dùng 400 hoặc status được hợp đồng API quy định.

**Lỗi 4 — Dùng `IllegalArgumentException` cho cả input và business rule.** Tầng HTTP không thể phân biệt ổn định. Dùng exception có tên theo domain và loại lỗi.

**Lỗi 5 — Coi “không tìm thấy” là infrastructure failure.** Repository trả empty có thể là kết quả bình thường. Chỉ chuyển thành 404 khi endpoint yêu cầu resource tồn tại.

**Lỗi 6 — Retry mọi lỗi bằng `retry()` vô hạn.** Có thể tạo retry storm, tăng tải và lặp side effect. Dùng retry có điều kiện, giới hạn, backoff và deadline.

**Lỗi 7 — Retry POST không có idempotency.** Một lần ghi có thể đã thành công dù response bị mất. Dùng idempotency key, unique constraint hoặc transaction phù hợp.

**Lỗi 8 — Nuốt lỗi bằng `onErrorResume(error -> Mono.empty())`.** API có thể trả 404 hoặc response rỗng trong khi dependency thật sự đã hỏng. Chỉ fallback khi semantics rõ ràng.

**Lỗi 9 — Dùng `doOnError` như thể nó đã xử lý lỗi.** `doOnError` chỉ quan sát; lỗi tiếp tục truyền. Muốn phục hồi phải dùng `onErrorResume` hoặc toán tử phù hợp.

**Lỗi 10 — Bắt `Throwable` và trả một giá trị mặc định.** Có thể che cả lỗi nghiêm trọng của runtime. Bắt các loại exception ứng dụng đã hiểu; để lỗi không mong đợi tới global fallback.

**Lỗi 11 — Trả `exception.getMessage()` cho client.** Message có thể chứa SQL, URL nội bộ, token hoặc dữ liệu cá nhân. Dùng message công khai an toàn và log chi tiết phía server.

**Lỗi 12 — Dùng HTTP status làm mã lỗi duy nhất.** Nhiều tình huống khác nhau cùng là 409 hoặc 400. Thêm `code` ổn định để client phân biệt.

**Lỗi 13 — Log cùng một exception ở mọi tầng.** Tạo nhiều bản ghi trùng lặp và gây nhiễu. Chọn ranh giới log chính, truyền trace ID và thêm context khi chuyển lỗi.

**Lỗi 14 — Đặt retry trong controller mà không hiểu service.** Retry nên ở ranh giới dependency hoặc use case có đủ thông tin về idempotency và lỗi transient.

**Lỗi 15 — Map mọi upstream 4xx thành lỗi client public.** 401/403/404 từ dependency có thể là lỗi credential hoặc contract nội bộ. Chuyển status theo ngữ nghĩa API của chính mình.

**Lỗi 16 — Không xử lý response đã committed.** Nếu stream đã gửi một phần body, không thể đổi status và ghi một error JSON thay thế. Thiết kế giao thức streaming có error event hoặc kết thúc stream.

**Lỗi 17 — Xem cancellation là lỗi server 500.** Client disconnect có thể hủy subscription; đây là tín hiệu lifecycle cần cleanup, không phải exception để trả một response mới.

**Lỗi 18 — Dùng metric tag có order ID hoặc message lỗi.** Cardinality tăng không giới hạn. Dùng route template, status và error code có tập giá trị hữu hạn.

## 14. Checklist thiết kế và rà soát

Khi thêm một endpoint mới, tự hỏi:

1. DTO có kiểm tra cú pháp, kiểu và giới hạn cơ bản không?
2. Quy tắc nào là validation đầu vào, quy tắc nào phụ thuộc trạng thái domain?
3. Các business outcome có exception/result type rõ ràng không?
4. Dependency failure có được chuyển thành exception ứng dụng tại ranh giới client không?
5. Có timeout và deadline phù hợp cho lời gọi ngoài không?
6. Retry có giới hạn và chỉ áp dụng cho lỗi transient không?
7. Thao tác ghi có idempotent hoặc có cơ chế deduplication không?
8. Global exception handler có ánh xạ status/code/message an toàn không?
9. Lỗi không mong đợi có trả 500 mà không lộ chi tiết nội bộ không?
10. Request ID/trace ID có giúp nối log giữa các tầng không?
11. Có metric cho validation, business conflict, dependency error và timeout không?
12. Test có kiểm tra status, error code, response shape và không tiết lộ secret không?
13. Nếu response streaming, đã xác định điều gì xảy ra khi lỗi sau khi commit chưa?
14. Nếu client cancel, resource và subscription có được cleanup đúng không?

## 15. Bài tập tự kiểm tra

1. JSON sai cú pháp thường thuộc nhóm nào và status nào? **Lỗi đầu vào; thường 400 Bad Request.**
2. `quantity = 0` khi hợp đồng yêu cầu ít nhất 1 thuộc nhóm nào? **Validation đầu vào; thường 400.**
3. Request hợp lệ nhưng đơn hàng đã hủy nên không thể giao tiếp thuộc nhóm nào? **Lỗi nghiệp vụ; thường 409 Conflict.**
4. Tìm đơn hàng không tồn tại thường ánh xạ status nào? **404 Not Found.**
5. Database tạm thời mất kết nối thuộc nhóm nào? **Lỗi hạ tầng; thường 503 hoặc 500 tùy hợp đồng/vai trò.**
6. Gateway chờ upstream quá deadline có thể trả status nào? **504 Gateway Timeout.**
7. `doOnError` có làm Publisher thành công không? **Không; chỉ quan sát lỗi.**
8. `onErrorMap` khác `onErrorResume` thế nào? **Một bên chuyển loại lỗi; một bên thay bằng Publisher khác để phục hồi hoặc phát lỗi mới.**
9. Có nên retry validation error không? **Không; request cần được sửa.**
10. Có nên retry POST tạo đơn hàng không? **Chỉ khi side effect được bảo vệ bằng idempotency/deduplication và policy retry có giới hạn.**
11. Vì sao không trả `error.getMessage()` cho client? **Có thể lộ thông tin nội bộ hoặc dữ liệu nhạy cảm.**
12. Mã `ORDER_CONFLICT` có vai trò gì khi status đều là 409? **Cho client biết chính xác tình huống theo hợp đồng mà không phân tích message.**
13. `@RestControllerAdvice` xử lý phạm vi nào? **Exception trong annotated controller dispatch.**
14. Khi nào dùng `WebExceptionHandler`? **Lỗi ở tầng web pipeline thoát ra ngoài filter/handler chain.**
15. Client cancel stream có nên được map thành 500 không? **Không; xử lý như lifecycle cancellation và cleanup.**
16. Circuit breaker thay thế error classification không? **Không; nó chỉ kiểm soát việc gọi dependency khi có dấu hiệu thất bại.**

## 16. Ghi nhớ và tài liệu tham khảo

- **Lỗi đầu vào:** request sai cú pháp/kiểu/validation; thường là 400, 413, 415 hoặc 406.
- **Lỗi nghiệp vụ:** request hợp lệ nhưng trạng thái/quy tắc domain từ chối; thường là 404, 409 hoặc 422 theo hợp đồng.
- **Lỗi hạ tầng:** dependency/network/tài nguyên không sẵn sàng; có thể là 503, 504 hoặc 500 tùy vai trò và nguyên nhân.
- **Lỗi không mong đợi:** 500, log đầy đủ phía server, không tiết lộ nội bộ.
- Dùng exception type có ý nghĩa, giữ nguyên cause và ánh xạ ở ranh giới HTTP.
- `doOnError` chỉ quan sát; `onErrorMap` chuẩn hóa; `onErrorResume` phục hồi; `retryWhen` thử lại theo policy.
- Retry phải có giới hạn, backoff, timeout và idempotency cho side effect.
- `@RestControllerAdvice` xử lý controller; `WebExceptionHandler` xử lý lỗi rộng hơn của WebFlux pipeline.
- Response cần có status, error code ổn định, message an toàn và trace ID.
- Cancellation là lifecycle signal; không nhầm với lỗi server.

Tài liệu chính thức:

1. [Spring Framework Reference — WebFlux Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html): xử lý exception trong annotated controller và `@ExceptionHandler`.
2. [Spring Framework Reference — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): Bean Validation, request binding và lỗi validation.
3. [Spring Framework Reference — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): error response, Problem Details và `ResponseEntityExceptionHandler`.
4. [Spring Framework Reference — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): reactive pipeline, Publisher, codecs và lifecycle.
5. [Project Reactor Reference — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorMap`, `onErrorResume`, retry và error signal.
6. [Project Reactor API — Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html): retry policy, backoff và giới hạn retry.
7. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ý nghĩa HTTP status code như 400, 404, 409, 413, 415, 422, 429, 500, 503 và 504.
