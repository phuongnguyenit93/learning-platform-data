# Biểu diễn dữ liệu thiếu và lỗi nghiệp vụ trong hợp đồng API

Một API tốt phải cho client biết rõ ba tình huống khác nhau: tài nguyên hoặc dữ liệu không tồn tại, yêu cầu hợp lệ nhưng nghiệp vụ không thể thực hiện, và hệ thống gặp lỗi khi xử lý. Trong ứng dụng reactive, các tình huống này thường được biểu diễn bằng `Mono.empty()`, tín hiệu `onError` hoặc một giá trị kết quả có kiểu. Nếu dùng chúng thay thế tùy tiện cho nhau, API có thể trả nhầm `200 OK`, che giấu lỗi, hoặc khiến client không biết nên hiển thị trạng thái nào và có nên thử lại hay không.

Hợp đồng API cần thống nhất ý nghĩa của dữ liệu thiếu, lỗi đầu vào, xung đột nghiệp vụ và lỗi hạ tầng. Với Spring WebFlux và Project Reactor, controller có thể trả `Mono<T>`, `Flux<T>` hoặc `Mono<ResponseEntity<T>>`; service có thể phát một giá trị, hoàn tất rỗng hoặc phát lỗi. Các lựa chọn này phải được ánh xạ thành HTTP status và response body có ý nghĩa ổn định.

Bài học thuộc chương **Thiết kế ứng dụng** của REACTIVE_PROGRAMMING. Module học các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung tập trung vào cách thiết kế hợp đồng API để phân biệt dữ liệu thiếu với lỗi nghiệp vụ, giữ semantics rõ ràng qua pipeline reactive và giúp client xử lý kết quả nhất quán.

## Ba trạng thái cần phân biệt

Khi một client gọi API lấy đơn hàng theo ID, có ít nhất ba kết quả khác nhau:

1. **Có dữ liệu:** đơn hàng tồn tại và caller được phép xem. API trả representation cùng status thành công.
2. **Không có dữ liệu:** không có đơn hàng mang ID đó. Đây có thể là kết quả bình thường của thao tác tìm kiếm, nhưng với endpoint đọc một tài nguyên cụ thể, thường được biểu diễn bằng `404 Not Found`.
3. **Không thể xử lý:** dữ liệu tồn tại nhưng nghiệp vụ từ chối yêu cầu, hoặc dependency gặp sự cố. API cần status và error body phù hợp để client biết cách phản ứng.

Ví dụ:

| Tình huống | Ý nghĩa | HTTP thường dùng |
|---|---|---|
| Đơn hàng tồn tại | Đọc thành công | `200 OK` |
| Không có đơn hàng với ID được yêu cầu | Tài nguyên không tồn tại | `404 Not Found` |
| Danh sách đơn hàng không có phần tử phù hợp | Truy vấn hợp lệ, kết quả rỗng | `200 OK` với `[]` |
| Yêu cầu tạo đơn thiếu trường bắt buộc hoặc sai định dạng | Đầu vào không hợp lệ | `400 Bad Request` hoặc `422 Unprocessable Content`, theo quy ước API |
| Không đủ tồn kho hoặc trạng thái hiện tại không cho phép thao tác | Xung đột quy tắc nghiệp vụ | Thường là `409 Conflict` |
| Người dùng chưa xác thực hoặc không có quyền | Lỗi xác thực/phân quyền | `401 Unauthorized` hoặc `403 Forbidden` |
| Database hoặc dịch vụ phụ thuộc tạm thời không hoạt động | Lỗi hạ tầng | `503 Service Unavailable`, `502 Bad Gateway` hoặc status phù hợp |

Không nên trả cùng một status cho mọi trường hợp “không có kết quả”. Client cần biết đó là danh sách rỗng hợp lệ, một tài nguyên không tồn tại, hay một thao tác bị từ chối.

## Dữ liệu thiếu trong `Mono` và `Flux`

`Mono<T>` biểu diễn không hoặc một phần tử. Vì vậy, `Mono.empty()` là cách hợp lệ để nói rằng nguồn hoàn tất mà không có giá trị. `Mono.error(error)` biểu diễn một terminal signal lỗi. Hai trường hợp có semantics khác nhau:

```java
Mono<Order> found = Mono.just(order);
Mono<Order> missing = Mono.empty();
Mono<Order> failed = Mono.error(new IllegalStateException("database unavailable"));
```

- `found` phát `onNext(order)` rồi `onComplete`.
- `missing` phát `onComplete` mà không có `onNext`.
- `failed` phát `onError` và kết thúc subscription.

`Flux<T>` cũng có thể hoàn tất rỗng. Với endpoint trả danh sách, một `Flux<Order>` rỗng thường có nghĩa là truy vấn hợp lệ nhưng không có phần tử phù hợp. Khi serialize thành JSON array, kết quả thường là `[]`, không phải lỗi 404.

Reactive Streams không cho phép `null` làm phần tử `onNext`. Không dùng `Mono.just(null)` để biểu diễn dữ liệu thiếu. Nếu adapter cũ trả `null` hoặc `Optional.empty()`, hãy chuyển đổi ở ranh giới:

```java
Mono<Order> order = Mono.justOrEmpty(legacyRepository.findOrNull(id));
```

`Mono.justOrEmpty` biến giá trị `null` hoặc `Optional.empty()` thành Mono rỗng. Từ đó, service hoặc controller quyết định Mono rỗng có nghĩa là “không tìm thấy”, “không có tùy chọn” hay một trạng thái hợp lệ khác.

### Đừng để `Mono.empty()` tự quyết định HTTP status

Một Mono rỗng không chứa đủ thông tin để tự quyết định mọi hợp đồng API. Cùng một `Mono.empty()` có thể mang ý nghĩa khác nhau tùy endpoint:

- Tìm một tài nguyên theo ID: thường cần chuyển thành 404.
- Tìm một tùy chọn không bắt buộc: có thể trả 204 hoặc representation có trường bị thiếu, tùy hợp đồng.
- Xóa tài nguyên: hoàn tất rỗng có thể ánh xạ thành 204.
- Tìm danh sách: dùng `Flux.empty()` để tạo danh sách rỗng.

Hãy đặt quyết định ở lớp biết ngữ nghĩa nghiệp vụ, thường là service hoặc adapter HTTP, thay vì mặc định mọi Mono rỗng đều là lỗi.

## Thiết kế endpoint đọc một tài nguyên

Với endpoint `GET /orders/{id}`, nếu đơn hàng không tồn tại, API thường trả 404. Có thể chuyển Mono rỗng thành một exception nghiệp vụ có kiểu:

```java
import reactor.core.publisher.Mono;

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(String id) {
        super("Order not found: " + id);
    }
}

class OrderService {
    private final OrderRepository repository;

    Mono<Order> findRequired(String id) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
    }
}
```

`switchIfEmpty` chỉ chạy Publisher thay thế khi nguồn hoàn tất mà không phát phần tử. Nếu repository phát `onError`, lỗi đó tiếp tục truyền xuống; `switchIfEmpty` không phải cơ chế bắt lỗi.

Controller có thể trả DTO và để exception handler tập trung ánh xạ lỗi:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/orders/{id}")
    Mono<OrderView> getOrder(@PathVariable String id) {
        return service.findRequired(id).map(OrderView::from);
    }
}
```

Cách này giữ controller tập trung vào luồng thành công. `OrderNotFoundException` được chuyển thành HTTP 404 ở `@RestControllerAdvice`, nơi có thể áp dụng response body chuẩn cho toàn API.

Một lựa chọn khác là biểu diễn rõ status tại controller bằng `Mono<ResponseEntity<T>>`:

```java
@GetMapping("/orders/{id}")
Mono<ResponseEntity<OrderView>> getOrder(@PathVariable String id) {
    return orderService.findById(id)
        .map(order -> ResponseEntity.ok(OrderView.from(order)))
        .defaultIfEmpty(ResponseEntity.<OrderView>notFound().build());
}
```

Chọn một quy ước nhất quán. Nếu toàn ứng dụng dùng exception nghiệp vụ và exception advice, tránh viết mỗi controller một cách xử lý rỗng khác nhau.

## Danh sách rỗng không phải tài nguyên không tồn tại

Với `GET /orders?customerId=...`, một danh sách rỗng thường là kết quả thành công. Endpoint nên trả `200 OK` cùng array rỗng:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/orders")
Flux<OrderView> findOrders(@RequestParam String customerId) {
    return orderService.findByCustomer(customerId)
        .map(OrderView::from);
}
```

Nếu không có đơn hàng, Flux hoàn tất rỗng và representation JSON là `[]`. Trả 404 cho danh sách rỗng có thể khiến client hiểu nhầm rằng endpoint hoặc customer không tồn tại. Nếu API cần xác nhận customer tồn tại trước khi tìm đơn hàng, đó là một quy tắc riêng: service có thể kiểm tra customer rồi trả 404 nếu customer không tồn tại, nhưng vẫn trả `200 []` nếu customer hợp lệ và chưa có đơn hàng.

Một cách viết rõ ràng khi cần kiểm tra cả customer:

```java
import java.util.List;

Mono<List<OrderView>> findCustomerOrders(String customerId) {
    return customerService.findRequired(customerId)
        .flatMapMany(customer -> orderService.findByCustomer(customer.id()))
        .map(OrderView::from)
        .collectList();
}
```

Nếu customer không tồn tại, `findRequired` phát lỗi 404 theo hợp đồng. Nếu customer tồn tại nhưng không có đơn hàng, `collectList()` phát một list rỗng. Kiểu `Mono<List<T>>` phát một list ngay cả khi list rỗng; điều này khác với `Mono.empty()`.

## Phân biệt trường bị thiếu, `null` và giá trị rỗng trong JSON

Trong JSON, ba biểu diễn sau không nhất thiết có cùng ý nghĩa:

```json
{}
```

```json
{"phone": null}
```

```json
{"phone": ""}
```

- Trường không xuất hiện có thể có nghĩa là client không gửi hoặc không muốn thay đổi trường đó.
- Trường xuất hiện với `null` có thể có nghĩa là xóa giá trị, không biết giá trị hoặc đầu vào không hợp lệ; API phải quy định rõ.
- Chuỗi rỗng là một giá trị có mặt nhưng không chứa ký tự; với số điện thoại, nó thường không hợp lệ hoặc cần chuẩn hóa thành thao tác xóa theo quy tắc được công bố.

Với `POST`, trường bắt buộc bị thiếu thường là lỗi validation. Với `PATCH`, trường bị bỏ qua thường có nghĩa là giữ nguyên; trường `null` có thể có nghĩa là xóa nếu trường đó cho phép xóa. Không nên gộp cả hai thành một Java `null` nếu nghiệp vụ cần phân biệt.

Ví dụ, một DTO PATCH dùng `JsonNode` có thể kiểm tra field có tồn tại hay không:

```java
import com.fasterxml.jackson.databind.JsonNode;

void applyPatch(JsonNode patch, Customer customer) {
    if (patch.has("phone")) {
        JsonNode phone = patch.get("phone");
        if (phone.isNull()) {
            customer.clearPhone();
        } else if (phone.isTextual()) {
            customer.changePhone(phone.asText());
        } else {
            throw new InvalidPatchException("phone must be text or null");
        }
    }
}
```

Đoạn mã minh họa sự khác biệt giữa field vắng mặt và field có `null`. Trong ứng dụng thực tế, nên đặt logic chuyển đổi trong một mapper/command handler và validate kiểu dữ liệu, độ dài, định dạng trước khi cập nhật entity. Có thể dùng một kiểu tri-state chuyên dụng hoặc thư viện như `JsonNullable<T>` nếu hợp đồng PATCH cần phân biệt absent, explicit null và value ở nhiều trường.

Đừng mặc định Jackson sẽ giữ được sự khác biệt này nếu DTO chỉ có field nullable thông thường. Sau khi deserialize, cả trường bị thiếu và trường `null` tường minh có thể trở thành cùng một giá trị Java `null`.

## Lỗi validation và lỗi nghiệp vụ

Lỗi validation xảy ra khi request không đáp ứng cấu trúc hoặc quy tắc đầu vào: thiếu customer ID, số lượng âm, email sai định dạng. Lỗi nghiệp vụ xảy ra khi dữ liệu đầu vào hợp lệ về cấu trúc nhưng không thể thực hiện trong trạng thái hiện tại: đơn hàng đã thanh toán, tồn kho không đủ hoặc tài khoản bị khóa.

Nên phân loại lỗi bằng kiểu exception hoặc kiểu kết quả có tên rõ ràng, không dựa vào việc so khớp chuỗi message:

```java
class InsufficientStockException extends RuntimeException {
    InsufficientStockException(String sku) {
        super("Insufficient stock for sku: " + sku);
    }
}

class OrderAlreadyPaidException extends RuntimeException {
    OrderAlreadyPaidException(String orderId) {
        super("Order is already paid: " + orderId);
    }
}
```

Sau đó ánh xạ từng loại sang status phù hợp. Ví dụ, không đủ tồn kho có thể là `409 Conflict` nếu kết quả phụ thuộc trạng thái kho tại thời điểm xử lý. Một giá trị ngoài miền cho phép có thể là `422 Unprocessable Content`. API cần ghi rõ quy ước và giữ ổn định qua các phiên bản.

### Lỗi nghiệp vụ có phải luôn là `onError`?

Không nhất thiết. Một nghiệp vụ có thể có kết quả từ chối được dự kiến và là một phần bình thường của luồng, ví dụ quyết định tín dụng trả `APPROVED` hoặc `DECLINED`. Khi đó, có thể biểu diễn bằng một kiểu kết quả:

```java
sealed interface CreditDecision permits Approved, Declined {}

record Approved(String reference) implements CreditDecision {}
record Declined(String reasonCode) implements CreditDecision {}

Mono<CreditDecision> evaluateCredit(Application application) {
    // Publisher phát Approved hoặc Declined như kết quả nghiệp vụ.
    return creditEngine.evaluate(application);
}
```

Nếu `DECLINED` là kết quả được mong đợi của việc đánh giá, nó có thể là `onNext(Declined)` rồi `onComplete`, không phải lỗi kỹ thuật. API có thể trả `200 OK` với decision representation nếu endpoint mô tả kết quả đánh giá; hoặc trả 4xx nếu hợp đồng định nghĩa request bị từ chối. Quyết định phụ thuộc semantics của tài nguyên và thao tác, không phụ thuộc việc Java dùng exception hay record.

Ngược lại, nếu client yêu cầu một chuyển trạng thái không hợp lệ như thanh toán một đơn đã hủy, đó thường là conflict và có thể được biểu diễn bằng exception nghiệp vụ chuyển thành `409`. Điều quan trọng là client phân biệt được kết quả nghiệp vụ bình thường với lỗi khiến thao tác không thể hoàn thành.

## Chuẩn hóa error response bằng Problem Details

Một response lỗi ổn định nên có cấu trúc nhất quán để client không phải phân tích message tùy ý. Problem Details chuẩn hóa bởi RFC 9457 (kế thừa RFC 7807) định nghĩa các trường như:

| Trường | Ý nghĩa |
|---|---|
| `type` | URI định danh loại vấn đề; có thể dùng URI tài liệu mô tả lỗi |
| `title` | Tên ngắn gọn của loại vấn đề |
| `status` | HTTP status tương ứng |
| `detail` | Giải thích cụ thể cho lần xảy ra lỗi này, không tiết lộ thông tin nhạy cảm |
| `instance` | URI định danh lần xảy ra vấn đề, nếu có |
| extension members | Trường mở rộng như `code`, `errors`, `correlationId` theo hợp đồng API |

Ví dụ response lỗi:

```json
{
  "type": "https://api.example.com/problems/insufficient-stock",
  "title": "Không đủ tồn kho",
  "status": 409,
  "detail": "Một hoặc nhiều sản phẩm không còn đủ số lượng để đặt.",
  "instance": "/orders",
  "code": "INVENTORY_CONFLICT",
  "correlationId": "corr-847"
}
```

`code` là mã ổn định để client xử lý theo chương trình; `detail` dành cho người đọc và có thể được bản địa hóa. Client không nên dựa vào nội dung `detail` để quyết định luồng vì câu chữ có thể thay đổi. Không đưa SQL, stack trace, hostname nội bộ, token hoặc dữ liệu cá nhân vào Problem Details.

### Ánh xạ exception bằng `@RestControllerAdvice`

Spring Framework hỗ trợ `ProblemDetail` trong các phiên bản hiện đại. Có thể tập trung ánh xạ exception nghiệp vụ:

```java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(OrderNotFoundException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy đơn hàng được yêu cầu."
        );
        problem.setType(URI.create("https://api.example.com/problems/order-not-found"));
        problem.setTitle("Không tìm thấy tài nguyên");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }

    @ExceptionHandler(InsufficientStockException.class)
    ResponseEntity<ProblemDetail> handleStockConflict(InsufficientStockException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Không đủ tồn kho để hoàn tất yêu cầu."
        );
        problem.setType(URI.create("https://api.example.com/problems/insufficient-stock"));
        problem.setTitle("Xung đột tồn kho");
        problem.setProperty("code", "INVENTORY_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

Handler tập trung giúp mọi endpoint trả cùng cấu trúc lỗi cho cùng loại exception. Không đưa trực tiếp `error.getMessage()` vào `detail` nếu message có thể chứa ID nhạy cảm, câu truy vấn hoặc thông tin nội bộ. Có thể ghi chi tiết kỹ thuật vào log/trace với quyền truy cập phù hợp, đồng thời trả client một thông điệp an toàn.

### Lỗi validation có danh sách field

Với request body không hợp lệ, API có thể trả `400` hoặc `422` theo quy ước. Response nên cung cấp danh sách field và mã lỗi ổn định:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ExceptionHandler(WebExchangeBindException.class)
ResponseEntity<ProblemDetail> handleValidation(WebExchangeBindException error) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "Một hoặc nhiều trường trong yêu cầu không hợp lệ."
    );
    problem.setType(URI.create("https://api.example.com/problems/validation"));
    problem.setTitle("Dữ liệu đầu vào không hợp lệ");
    List<Map<String, String>> fieldErrors = error.getFieldErrors().stream()
        .map(fieldError -> Map.of(
            "field", fieldError.getField(),
            "code", "INVALID_VALUE"
        ))
        .toList();
    problem.setProperty("errors", fieldErrors);

    return ResponseEntity.badRequest().body(problem);
}
```

Ví dụ bỏ qua default message của validator để tránh vô tình trả thông tin không phù hợp. Ứng dụng có thể bổ sung message đã bản địa hóa từ catalog lỗi của mình. Tùy kiểu binding và phiên bản Spring, lỗi validation có thể được biểu diễn bởi `WebExchangeBindException` hoặc exception liên quan; hãy kiểm tra đúng loại exception trong stack đang sử dụng và có test cho request body thực tế.

## Ánh xạ lỗi hạ tầng và lỗi không mong đợi

Lỗi nghiệp vụ có thể ánh xạ thành 4xx. Lỗi hạ tầng như database unavailable, timeout hoặc lỗi kết nối upstream thường là 5xx hoặc status gateway phù hợp. Không nên trả 404 cho lỗi database chỉ vì repository không thể đọc dữ liệu; “không tìm thấy” và “không thể truy vấn” có ý nghĩa khác nhau.

Ví dụ chuyển lỗi từ dependency thành exception ở ranh giới adapter:

```java
import java.util.concurrent.TimeoutException;

Mono<Payment> payment = paymentClient.findPayment(orderId)
    .onErrorMap(TimeoutException.class,
        error -> new PaymentDependencyUnavailableException(error));
```

`onErrorMap` giữ terminal signal là lỗi nhưng đổi loại lỗi sang abstraction phù hợp với ứng dụng. Global handler có thể ánh xạ `PaymentDependencyUnavailableException` thành `503 Service Unavailable` hoặc `504 Gateway Timeout` theo vai trò của service và chính sách API.

Nếu dùng `onErrorResume` để fallback, hãy chắc chắn fallback là kết quả hợp lệ:

```java
Mono<ExchangeRate> rate = rateClient.latestRate(currency)
    .onErrorResume(ExchangeRateUnavailableException.class,
        error -> cachedRates.find(currency)
            .switchIfEmpty(Mono.error(error)));
```

Ví dụ chỉ dùng cache khi có tỷ giá đã lưu. Nếu cache cũng rỗng, lỗi ban đầu tiếp tục được phát. Trong ứng dụng thật, response có thể cần đánh dấu dữ liệu cache là stale hoặc ghi metadata nguồn dữ liệu để client không hiểu nhầm đó là tỷ giá mới nhất.

Không viết `onErrorResume(error -> Mono.empty())` như một cách chung để làm API “không bị lỗi”. Cách đó biến lỗi database hoặc timeout thành dữ liệu thiếu, có thể khiến endpoint trả 404 hoặc danh sách rỗng và che giấu sự cố.

## Status code là một phần của hợp đồng

Một số status thường gặp và cách chọn:

| Status | Dùng khi | Lưu ý cho client |
|---|---|---|
| `200 OK` | Đọc hoặc xử lý thành công có representation | Parse response theo schema thành công |
| `201 Created` | Tạo tài nguyên mới thành công | Có thể cung cấp `Location` tới tài nguyên mới |
| `202 Accepted` | Đã tiếp nhận công việc bất đồng bộ, chưa hoàn tất | Client cần theo dõi trạng thái hoặc nhận event |
| `204 No Content` | Thành công nhưng không có body, ví dụ xóa thành công | Không cố parse JSON body |
| `400 Bad Request` | Request sai cú pháp hoặc validation theo quy ước API | Sửa request trước khi gửi lại |
| `401 Unauthorized` | Thiếu hoặc credential không hợp lệ | Xác thực lại; server thường kèm challenge phù hợp |
| `403 Forbidden` | Đã xác thực nhưng không có quyền | Không retry cùng credential để mong thành công |
| `404 Not Found` | Tài nguyên được định danh không tồn tại hoặc không được tiết lộ | Kiểm tra ID và quyền truy cập |
| `409 Conflict` | Trạng thái hiện tại xung đột với thao tác | Đọc trạng thái mới rồi quyết định bước tiếp theo |
| `422 Unprocessable Content` | Cú pháp hợp lệ nhưng nội dung không đáp ứng quy tắc xử lý | Sửa dữ liệu hoặc lựa chọn nghiệp vụ |
| `429 Too Many Requests` | Vượt giới hạn tốc độ | Tôn trọng `Retry-After` nếu được gửi |
| `500 Internal Server Error` | Lỗi không mong đợi ở server | Không lặp liên tục; dùng retry có giới hạn nếu phù hợp |
| `502/503/504` | Gateway/upstream lỗi, service tạm không khả dụng hoặc timeout | Có thể retry có backoff tùy semantics và deadline |

Không có một bảng ánh xạ duy nhất phù hợp mọi API. Điều quan trọng là quy ước được tài liệu hóa, dùng nhất quán và không làm client phải suy đoán từ message tự do.

## Hợp đồng cho thao tác không có body

`Mono<Void>` thường phù hợp với thao tác chỉ cần biểu diễn hoàn tất hoặc lỗi, ví dụ xóa tài nguyên:

```java
@DeleteMapping("/orders/{id}")
Mono<ResponseEntity<Void>> deleteOrder(@PathVariable String id) {
    return orderService.delete(id)
        .thenReturn(ResponseEntity.noContent().build());
}
```

Đoạn mã trên trả 204 nếu service hoàn tất. Nhưng nếu hợp đồng yêu cầu 404 khi ID không tồn tại, service phải phát `OrderNotFoundException` thay vì hoàn tất rỗng. `Mono<Void>` không mang thông tin “đã xóa một bản ghi” hay “không có bản ghi”; nếu cần phân biệt, service phải biểu diễn kết quả rõ ràng hoặc phát lỗi nghiệp vụ.

Với lệnh bất đồng bộ, có thể trả `202 Accepted` cùng URL trạng thái:

```java
@PostMapping("/reports")
Mono<ResponseEntity<ReportJobAccepted>> createReport(@RequestBody ReportRequest request) {
    return reportService.submit(request)
        .map(job -> ResponseEntity.accepted()
            .body(new ReportJobAccepted(job.id(), "/report-jobs/" + job.id())));
}
```

`202` có nghĩa server đã tiếp nhận, không phải báo cáo đã hoàn thành. API cần cung cấp cách đọc trạng thái hoặc phát event để client biết kết quả cuối.

## Hợp đồng ổn định cho client

Client thường cần nhiều hơn một status code. Nên quy định:

- Mã lỗi ổn định (`code`) không phụ thuộc câu chữ hoặc ngôn ngữ.
- Cấu trúc lỗi chuẩn cho mọi endpoint, ví dụ Problem Details.
- Trường nào có thể thiếu, trường nào có thể `null`, trường nào luôn có mặt.
- Danh sách rỗng được biểu diễn bằng `[]` hay một envelope có metadata phân trang.
- Lỗi nào có thể retry và điều kiện retry; nếu có, cung cấp `Retry-After` hoặc thông tin retry phù hợp.
- Correlation ID hoặc trace ID nào được trả để hỗ trợ liên hệ với đội vận hành, nhưng không dùng làm định danh nghiệp vụ.
- Phiên bản schema và chính sách tương thích khi thêm hoặc đổi trường.

Không để client phụ thuộc vào exception class, stack trace hoặc message nội bộ. Client chỉ nên phụ thuộc vào hợp đồng HTTP công khai: status, content type, schema và mã lỗi đã được tài liệu hóa.

## Kiểm thử hợp đồng bằng `WebTestClient`

`WebTestClient` có thể kiểm tra status, header, body và Problem Details của endpoint WebFlux. Nên có test riêng cho dữ liệu có, dữ liệu thiếu, danh sách rỗng, lỗi nghiệp vụ và lỗi hạ tầng.

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class OrderApiContractTest {
    private final WebTestClient client;

    OrderApiContractTest(WebTestClient client) {
        this.client = client;
    }

    @Test
    void missingOrderUsesNotFoundProblem() {
        client.get()
            .uri("/orders/missing")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(404)
            .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
    }

    @Test
    void emptyOrderCollectionIsSuccessfulArray() {
        client.get()
            .uri("/orders?customerId=customer-without-orders")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("[]");
    }
}
```

Test đầu xác nhận không tìm thấy một tài nguyên trả Problem Details 404. Test thứ hai xác nhận danh sách rỗng vẫn là response thành công với array rỗng. Với ứng dụng có envelope phân trang, hãy kiểm tra `items: []`, `total: 0` và metadata theo hợp đồng thực tế.

### Kiểm thử request validation

Gửi request thiếu trường hoặc sai giá trị và xác nhận status cùng field error:

```java
client.post()
    .uri("/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("""{"customerId":"","items":[]}""")
    .exchange()
    .expectStatus().isBadRequest()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
    .expectBody()
    .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
    .jsonPath("$.errors").isArray();
```

Trong test thực tế, body phải khớp DTO và rule validation của endpoint. Test nên xác nhận client nhận được field path và code ổn định, không assert toàn bộ câu `detail` nếu câu đó có thể được bản địa hóa.

## Kiểm thử semantics của service bằng `StepVerifier`

Ở cấp service, `StepVerifier` xác nhận khác biệt giữa hoàn tất rỗng và lỗi:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OrderServiceTest {
    @Test
    void missingOrderBecomesTypedDomainError() {
        Mono<Order> result = Mono.<Order>empty()
            .switchIfEmpty(Mono.error(new OrderNotFoundException("missing")));

        StepVerifier.create(result)
            .expectError(OrderNotFoundException.class)
            .verify();
    }

    @Test
    void optionalLookupCanRemainEmpty() {
        StepVerifier.create(Mono.<Order>empty())
            .verifyComplete();
    }
}
```

Hai test minh họa hai hợp đồng service khác nhau: `findRequired` biến dữ liệu thiếu thành lỗi miền; một lookup tùy chọn có thể giữ Mono rỗng. Không nên chỉ test controller; test service giúp đảm bảo semantics không bị thay đổi khi pipeline được kết hợp với operator khác.

## Lỗi thường gặp khi thiết kế hợp đồng reactive

**Dùng `Mono.empty()` cho mọi lỗi.** Client không phân biệt được không tìm thấy với database lỗi hoặc timeout. Giữ lỗi hạ tầng ở `onError` và ánh xạ đúng status.

**Dùng `Mono.error` cho danh sách rỗng.** Một truy vấn danh sách hợp lệ không có kết quả thường nên trả `200 []`, không phải 404 hoặc 500.

**Cho rằng `switchIfEmpty` bắt cả lỗi.** Operator chỉ xử lý hoàn tất không có phần tử. Dùng `onErrorResume` hoặc exception handler cho `onError`.

**Nuốt lỗi bằng `onErrorResume(error -> Mono.empty())`.** Cách này có thể biến lỗi dependency thành 404 hoặc danh sách rỗng, che giấu sự cố và tạo dữ liệu sai cho client.

**Trả `200` với body `null`.** `null` không phải phần tử hợp lệ của Reactive Streams và tạo hợp đồng mơ hồ. Dùng representation rõ ràng, 204, 404 hoặc Problem Details tùy trường hợp.

**Không phân biệt field absent với explicit null trong PATCH.** DTO nullable thông thường có thể làm mất thông tin này. Dùng tri-state representation và test cả hai request.

**Dùng message exception làm mã lỗi.** Câu chữ thay đổi theo phiên bản hoặc ngôn ngữ. Dùng error code ổn định và Problem Details.

**Trả stack trace hoặc thông tin dependency cho client.** Đây là dữ liệu nội bộ và có thể lộ cấu trúc hệ thống. Ghi chi tiết vào log/trace được bảo vệ, response chỉ chứa thông tin công khai.

**Retry mọi lỗi 4xx/5xx như nhau.** Lỗi validation và quyền truy cập không tự hết khi retry. Chỉ retry lỗi tạm thời, có giới hạn và idempotency phù hợp.

**Dùng `Mono<Void>` nhưng cần phân biệt không tồn tại.** `Mono<Void>` chỉ thể hiện hoàn tất hoặc lỗi. Nếu không tìm thấy phải trả 404, service cần phát lỗi typed hoặc trả kiểu kết quả biểu diễn rõ trạng thái.

## Tự kiểm tra

1. `Mono.empty()` khác `Mono.error(...)` như thế nào về terminal signal?
2. Vì sao danh sách rỗng thường trả `200 []`, còn một tài nguyên cụ thể không tồn tại thường trả 404?
3. Khi nào nên dùng `switchIfEmpty`, `onErrorMap` và `onErrorResume`?
4. Vì sao không nên chuyển mọi lỗi database thành Mono rỗng?
5. Trường JSON bị bỏ qua, `null` và chuỗi rỗng có thể mang những ý nghĩa khác nhau nào trong PATCH?
6. Khi nào một kết quả từ chối nghiệp vụ nên là giá trị có kiểu thay vì tín hiệu `onError`?
7. Problem Details giúp client xử lý lỗi ổn định như thế nào?
8. Vì sao `Mono<Void>` không đủ để biểu diễn đồng thời “đã xóa” và “không tìm thấy” nếu hợp đồng cần phân biệt?
9. Cần kiểm thử những trường hợp nào bằng `WebTestClient` và `StepVerifier` để xác nhận hợp đồng?
10. Vì sao error code ổn định quan trọng hơn việc client phân tích chuỗi `detail`?

Khi biểu diễn dữ liệu thiếu bằng semantics rõ ràng, giữ lỗi nghiệp vụ và lỗi hạ tầng ở các loại riêng, rồi ánh xạ chúng thành HTTP status cùng Problem Details ổn định, API reactive sẽ dễ tích hợp và dễ vận hành hơn. Client có thể quyết định chính xác khi nào hiển thị trạng thái rỗng, khi nào yêu cầu người dùng sửa dữ liệu, khi nào cần cập nhật trạng thái và khi nào nên thử lại.
