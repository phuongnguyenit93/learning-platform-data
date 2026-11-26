# Error response trong MVC

Một REST API cần có hợp đồng lỗi ổn định giống như hợp đồng response thành công. Khi request sai định dạng, tài nguyên không tồn tại, trạng thái nghiệp vụ xung đột hoặc server gặp sự cố, client cần nhận được HTTP status phù hợp cùng nội dung giải thích có cấu trúc. Trong Spring MVC, có thể xử lý lỗi tập trung bằng `@RestControllerAdvice`, `@ExceptionHandler` và `ResponseEntityExceptionHandler`.

Spring Framework hỗ trợ `ProblemDetail` và `ErrorResponse` để triển khai Problem Details theo RFC 9457. `ProblemDetail` mô tả loại lỗi, tiêu đề, chi tiết, status và URI của lần xảy ra lỗi. Các trường mở rộng như mã lỗi nghiệp vụ, danh sách validation violation hoặc correlation ID giúp client xử lý cụ thể hơn. Với API dùng Spring HATEOAS, cần xác định rõ error representation có phải HAL hay Problem Details; không nên giả định mọi error body tự động có `_links`.

## Vì sao cần hợp đồng lỗi thống nhất?

Nếu mỗi controller tự trả lỗi theo một cấu trúc khác nhau, client phải viết nhiều nhánh để phân tích response. Ví dụ, endpoint này trả `{ "message": "not found" }`, endpoint khác trả `{ "error": "ORDER_MISSING" }`, còn endpoint thứ ba trả một HTML error page. Cách đó làm client khó tái sử dụng logic xử lý lỗi.

Một error contract tốt cần:

- Dùng HTTP status phản ánh đúng loại kết quả.
- Có cấu trúc body nhất quán giữa các endpoint.
- Cung cấp mã lỗi ổn định để client phân nhánh.
- Giữ thông tin chi tiết đủ giúp người dùng sửa request hoặc liên hệ hỗ trợ.
- Không để lộ stack trace, SQL, token, thông tin xác thực hoặc dữ liệu nhạy cảm.
- Giữ tương thích khi thêm trường mở rộng.

Ví dụ, khi client gửi một đơn hàng với trạng thái không được phép chuyển đổi, server có thể trả `409 Conflict` cùng mã `ORDER_STATE_CONFLICT`. Client có thể hiển thị thông báo phù hợp mà không phải phân tích câu tiếng Việt trong trường `detail`.

## Problem Details theo RFC 9457

RFC 9457 định nghĩa định dạng chuẩn để biểu diễn lỗi HTTP bằng media type `application/problem+json` hoặc `application/problem+xml`. Với JSON, một problem document có các member chuẩn:

| Member | Ý nghĩa |
| --- | --- |
| `type` | URI định danh loại vấn đề; nếu không có thường dùng `about:blank`. |
| `title` | Tóm tắt ngắn gọn loại vấn đề. |
| `status` | HTTP status của lần xảy ra lỗi. |
| `detail` | Giải thích cụ thể cho lần xảy ra lỗi này. |
| `instance` | URI định danh lần xảy ra lỗi cụ thể. |

Ví dụ response khi không tìm thấy đơn hàng:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng được yêu cầu.",
  "instance": "/api/orders/8c5c2c5d-12c1-4f1c-9db4-43c8a15a9f10",
  "code": "ORDER_NOT_FOUND"
}
```

`code` là extension member do API định nghĩa, không phải member chuẩn của RFC. Có thể thêm extension để mô tả lỗi validation, correlation ID hoặc thông tin hỗ trợ. Client nên dùng `type` hoặc `code` để nhận diện lỗi; không nên parse chuỗi `detail` vì nội dung đó dành cho con người và có thể thay đổi theo ngôn ngữ.

URI trong `type` định danh loại lỗi, còn `instance` định danh lần xảy ra lỗi. Hai URI này không có cùng mục đích. Một loại lỗi `order-not-found` có thể xuất hiện trong nhiều request, mỗi request có một `instance` khác nhau.

## ProblemDetail trong Spring Framework

Spring Framework cung cấp `org.springframework.http.ProblemDetail` từ Spring Framework 6.0. Có thể tạo problem document bằng factory method:

```java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy đơn hàng được yêu cầu.");

problem.setType(URI.create(
        "https://api.example.com/problems/order-not-found"));
problem.setTitle("Order not found");
problem.setInstance(URI.create("/api/orders/8c5c2c5d-12c1-4f1c-9db4-43c8a15a9f10"));
problem.setProperty("code", "ORDER_NOT_FOUND");
```

Các phương thức quan trọng:

- `forStatus(...)` tạo problem với status cho trước.
- `forStatusAndDetail(...)` tạo problem với status và detail.
- `setType(...)`, `setTitle(...)`, `setInstance(...)` thiết lập các member chuẩn.
- `setProperty(...)` thêm extension member.

Spring MVC nhận biết `ProblemDetail` là error response và có thể serialize thành `application/problem+json`. Status HTTP được lấy từ status của problem. Nếu ứng dụng cần kiểm soát header hoặc status cụ thể hơn, có thể trả `ResponseEntity<ProblemDetail>`.

## Xử lý exception nghiệp vụ bằng @RestControllerAdvice

`@RestControllerAdvice` cho phép xử lý exception phát sinh từ nhiều controller trong một nơi. `@ExceptionHandler` ánh xạ loại exception sang response phù hợp.

Đầu tiên, định nghĩa exception nghiệp vụ:

```java
import java.util.UUID;

public class OrderNotFoundException extends RuntimeException {

    private final UUID orderId;

    public OrderNotFoundException(UUID orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    public UUID getOrderId() {
        return orderId;
    }
}
```

Advice chuyển exception thành Problem Details:

```java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(
            OrderNotFoundException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đơn hàng được yêu cầu.");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_NOT_FOUND");
        problem.setProperty("orderId", ex.getOrderId());

        return problem;
    }
}
```

Khi service ném `OrderNotFoundException`, advice tạo response `404` với problem type và mã lỗi ổn định. Trường `orderId` chỉ nên được thêm nếu việc công bố ID đó phù hợp với chính sách dữ liệu của API.

Không cần bắt mọi exception trong từng controller. Hãy để exception nghiệp vụ đi lên tầng advice, đồng thời giữ các quy tắc xử lý transaction và logging tại tầng phù hợp. Tránh trả `ex.getMessage()` trực tiếp cho client nếu message có thể chứa thông tin nội bộ.

## ResponseEntityExceptionHandler cho lỗi Spring MVC

Spring MVC có nhiều exception chuẩn như lỗi đọc JSON, thiếu parameter, method không được hỗ trợ, validation thất bại hoặc media type không phù hợp. `ResponseEntityExceptionHandler` cung cấp cơ chế xử lý tập trung cho nhóm lỗi MVC này và có thể trả Problem Details.

Có thể kế thừa lớp này để tùy biến response validation:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.net.URI;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class MvcProblemHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                "Dữ liệu request không hợp lệ.");

        problem.setType(URI.create(
                "https://api.example.com/problems/validation-failed"));
        problem.setTitle("Validation failed");
        problem.setProperty("code", "VALIDATION_FAILED");

        List<Map<String, String>> violations = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "message", Objects.toString(
                                error.getDefaultMessage(), "Giá trị không hợp lệ.")))
                .toList();

        problem.setProperty("violations", violations);

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }
}
```

`handleMethodArgumentNotValid(...)` được gọi khi dữ liệu gắn với `@Valid` hoặc `@Validated` không vượt qua Bean Validation trong quá trình bind request body. Việc gọi `handleExceptionInternal(...)` giữ luồng xử lý chung của `ResponseEntityExceptionHandler`, bao gồm header và status.

Khi kế thừa `ResponseEntityExceptionHandler`, không khai báo một handler tổng quát khác bắt cùng các exception mà lớp cha đã xử lý nếu không có chủ đích. Có thể thêm `@ExceptionHandler` cho exception nghiệp vụ riêng trong cùng advice, miễn là không tạo mapping mơ hồ.

### Thứ tự xử lý exception

Một `@ExceptionHandler` đặt ngay trong controller được ưu tiên cho exception phát sinh từ controller đó. Nếu không có handler cục bộ phù hợp, Spring mới xét các `@ControllerAdvice`/`@RestControllerAdvice` toàn cục. Khi ứng dụng có nhiều advice, có thể dùng `@Order` để quy định thứ tự áp dụng. Hãy tránh khai báo nhiều handler cùng bắt một loại exception với thứ tự không rõ ràng.

### Ranh giới với Spring Security

Không phải mọi lỗi HTTP đều đi qua Spring MVC. Spring Security thường xử lý xác thực và phân quyền trong filter chain trước khi request đến controller. Vì vậy, `@RestControllerAdvice` không nhất thiết nhận được lỗi `401` hoặc `403` do security filter tạo ra. Nếu muốn cùng một Problem Details contract cho các lỗi này, cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` để ghi response Problem Details ở tầng Security. Tương tự, lỗi do servlet container hoặc gateway phát sinh ngoài DispatcherServlet cần được xử lý ở tầng tương ứng.

## Validation error từ request body

DTO đầu vào có thể dùng Jakarta Bean Validation để mô tả quy tắc:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @Positive int quantity,
        @Size(max = 250) String note
) {
}
```

Controller kích hoạt validation:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping("/api/orders")
ResponseEntity<?> create(@Valid @RequestBody CreateOrderRequest request) {
    return ResponseEntity.ok(orderService.create(request));
}
```

Nếu `quantity` không dương hoặc `customerId` rỗng, Spring MVC ném validation exception và advice trả Problem Details. Ví dụ body:

```json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "Dữ liệu request không hợp lệ.",
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "quantity",
      "message": "must be greater than 0"
    }
  ]
}
```

`violations` là extension do API định nghĩa. Hãy thống nhất tên field, cấu trúc lỗi và cách biểu diễn lỗi lồng nhau để client có thể gắn lỗi vào form. Không nên đưa toàn bộ `BindingResult` hoặc object exception nội bộ vào response.

Tùy loại tham số và phiên bản Spring, lỗi validation có thể đến từ `MethodArgumentNotValidException`, `HandlerMethodValidationException` hoặc `ConstraintViolationException`. Nếu API dùng method validation cho query/path parameter, cần kiểm tra và xử lý loại exception tương ứng thay vì chỉ xử lý lỗi request body.

## Phân biệt lỗi cú pháp, validation và lỗi nghiệp vụ

Các lỗi có thể xảy ra ở nhiều giai đoạn:

| Giai đoạn | Ví dụ | HTTP status thường dùng |
| --- | --- | --- |
| Đọc request | JSON sai cú pháp, body không thể deserialize | `400 Bad Request` |
| Bind parameter | UUID hoặc ngày giờ sai định dạng | `400 Bad Request` |
| Bean Validation | `quantity` âm, trường bắt buộc rỗng | `400 Bad Request` theo quy ước phổ biến của Spring MVC |
| Kiểm tra quy tắc nghiệp vụ | Chuyển đơn hàng từ trạng thái không cho phép | `409 Conflict` hoặc status phù hợp với hợp đồng |
| Tài nguyên không tồn tại | Không có order với ID đã gửi | `404 Not Found` |
| Xác thực/phân quyền | Chưa đăng nhập hoặc không đủ quyền | `401 Unauthorized` / `403 Forbidden` |

Không phải mọi lỗi đều là validation. Ví dụ, `quantity = 2` có thể vượt qua Bean Validation nhưng vẫn vi phạm giới hạn tồn kho. Lỗi đó thuộc nghiệp vụ và cần mã lỗi riêng như `INSUFFICIENT_STOCK`.

`422 Unprocessable Content` có thể được chọn cho một số lỗi nội dung hợp lệ về cú pháp nhưng không xử lý được theo quy tắc ứng dụng; tuy nhiên, hãy dùng nhất quán và tài liệu hóa thay vì tùy tiện đổi status giữa các endpoint.

## ErrorResponse và ErrorResponseException

Spring Framework cung cấp `ErrorResponse` như một abstraction cho lỗi HTTP. Interface này mô tả status, headers và `ProblemDetail` body. `ErrorResponseException` là exception có thể mang trực tiếp các thông tin đó.

Ví dụ một exception domain có thể kế thừa `ErrorResponseException`:

```java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponseException;

public class OrderConflictException extends ErrorResponseException {

    public OrderConflictException(String currentStatus) {
        super(
                HttpStatus.CONFLICT,
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.CONFLICT,
                        "Đơn hàng không thể chuyển sang trạng thái được yêu cầu."),
                null);

        getBody().setType(URI.create(
                "https://api.example.com/problems/order-state-conflict"));
        getBody().setTitle("Order state conflict");
        getBody().setProperty("code", "ORDER_STATE_CONFLICT");
        getBody().setProperty("currentStatus", currentStatus);
    }
}
```

Khi exception triển khai `ErrorResponse`, Spring MVC có thể dùng status, headers và body của nó trong cơ chế xử lý lỗi. Cách này phù hợp khi một loại exception luôn mang cùng semantics HTTP. Với những exception cần ánh xạ khác nhau tùy ngữ cảnh, `@RestControllerAdvice` vẫn là nơi linh hoạt để chuyển đổi.

## Chọn HTTP status có ý nghĩa

Problem Details không thay thế HTTP status. Status vẫn là tín hiệu chính để intermediary và client hiểu kết quả của request.

| Status | Khi thường dùng |
| --- | --- |
| `400` | Request không hợp lệ, body hoặc parameter sai định dạng. |
| `401` | Thiếu hoặc thông tin xác thực không hợp lệ. |
| `403` | Đã xác thực nhưng không có quyền thực hiện. |
| `404` | Resource không tồn tại hoặc không được công bố cho caller. |
| `405` | HTTP method không được endpoint hỗ trợ. |
| `409` | Xung đột với trạng thái hiện tại của resource. |
| `412` | Điều kiện trong request header như `If-Match` không thỏa mãn. |
| `415` | Request body dùng media type không được hỗ trợ. |
| `429` | Client gửi quá nhiều request trong khoảng thời gian quy định. |
| `500` | Lỗi không mong đợi phía server. |
| `503` | Service tạm thời không khả dụng. |

Không trả `200 OK` với body `{ "success": false }` cho một request thất bại ở mức HTTP nếu status lỗi phù hợp hơn. Điều đó khiến cache, monitoring, retry policy và client khó nhận biết kết quả thực.

## Content negotiation cho error response

Error response cũng là một representation HTTP. Với Problem Details, media type là `application/problem+json`. Client nên chấp nhận media type lỗi cùng với media type thành công mà API cung cấp:

```http
Accept: application/hal+json, application/problem+json
```

Response thành công có thể là HAL; response lỗi có thể là Problem Details. Hai body có mục đích khác nhau và có thể dùng media type khác nhau. Nếu client chỉ chấp nhận `application/hal+json`, hãy quyết định và tài liệu hóa cách server xử lý khi cần trả error body `application/problem+json`.

Trong Spring MVC, `ProblemDetail` được hỗ trợ bởi cơ chế HTTP message conversion của Spring. Hãy kiểm thử `Content-Type` thực tế trong cấu hình ứng dụng, nhất là khi có custom converter, content negotiation strategy hoặc advice khác.

## Kết hợp error response với Spring HATEOAS

Spring HATEOAS giúp client khám phá resource và action qua link. Tuy nhiên, Problem Details theo RFC 9457 không phải HAL và không tự có `_links` hoặc `_embedded`. Hai mục tiêu cần được phân biệt:

- Problem Details chuẩn hóa cách mô tả lỗi HTTP.
- HAL chuẩn hóa cách biểu diễn link và embedded resource.

Một Problem Detail có thể chứa extension member theo hợp đồng API, ví dụ `code`, `violations`, `traceId` hoặc một object `support`. Nếu muốn cung cấp link khôi phục trong Problem Details, hãy định nghĩa extension schema rõ ràng và đảm bảo client hiểu nó. Không nên đưa một object `_links` vào `application/problem+json` rồi mặc định mọi client sẽ xử lý như HAL.

Nếu API cần error representation có hypermedia đầy đủ, có thể định nghĩa một model lỗi riêng kế thừa `RepresentationModel` và trả dưới media type HAL. Khi đó, cần tài liệu hóa rõ cấu trúc lỗi và link như `support`, `retry` hoặc `order`, đồng thời giữ HTTP status phù hợp. Chỉ dùng cách này khi client thực sự cần điều hướng từ error representation; với phần lớn lỗi validation hoặc malformed request, Problem Details đơn giản thường đủ.

Ví dụ Problem Details có extension cung cấp thông tin hỗ trợ:

```json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "Đơn hàng không thể hủy ở trạng thái hiện tại.",
  "code": "ORDER_STATE_CONFLICT",
  "support": {
    "href": "https://support.example.com/orders",
    "rel": "help"
  }
}
```

`support` là extension do API tự định nghĩa, không phải cấu trúc link chuẩn của RFC 9457 hay HAL. Nếu dùng, hãy mô tả cách client đọc nó trong tài liệu API.

## Correlation ID và logging

Khi lỗi xảy ra, client cần một mã để cung cấp cho đội vận hành mà không phải gửi stack trace. Có thể thêm correlation ID hoặc trace ID vào response:

```json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "Đã xảy ra lỗi. Vui lòng thử lại sau.",
  "code": "INTERNAL_ERROR",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Trace ID nên được tạo hoặc xác minh bởi hạ tầng tracing đáng tin cậy và ghi cùng log server. Không đưa stack trace hoặc exception message thô vào response production. Nếu hệ thống dùng `traceparent`, hãy duy trì correlation xuyên các service và chỉ công bố identifier phù hợp với chính sách vận hành.

## Bảo mật khi xây error body

Error response là dữ liệu gửi ra ngoài ranh giới server. Không nên trả:

- Stack trace, tên class nội bộ hoặc đường dẫn file trên server.
- SQL statement, connection string hoặc tên bảng nhạy cảm.
- Token, session ID, secret hoặc header xác thực.
- Dữ liệu cá nhân không cần thiết để giải thích lỗi.
- Nội dung exception từ thư viện bên thứ ba chưa được lọc.

Với lỗi `404`, một số hệ thống chủ động dùng cùng response cho “không tồn tại” và “không được phép biết resource tồn tại” để tránh tiết lộ dữ liệu. Hãy thống nhất hành vi theo chính sách authorization của API.

## Kiểm thử Problem Details bằng MockMvc

Kiểm thử cần xác nhận status, media type và các member quan trọng:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderErrorResponseTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsProblemDetailWhenOrderDoesNotExist() throws Exception {
        mockMvc.perform(get("/api/orders/{id}",
                        "8c5c2c5d-12c1-4f1c-9db4-43c8a15a9f10")
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.type")
                        .value("https://api.example.com/problems/order-not-found"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }
}
```

Fixture cần bảo đảm ID trong test không tồn tại. Với validation, gửi body sai và xác nhận `400`, `code=VALIDATION_FAILED` cùng `violations`. Với lỗi xung đột, xác nhận `409` và mã domain tương ứng. Nếu ứng dụng hỗ trợ nhiều media type, kiểm tra cả response thành công HAL và response lỗi Problem Details để bảo vệ content negotiation.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Mỗi controller tự trả một JSON lỗi khác nhau | Client phải viết nhiều parser và nhánh xử lý. | Chuẩn hóa bằng ProblemDetail và advice tập trung. |
| Trả `200` cho lỗi nghiệp vụ | HTTP client và monitoring hiểu request đã thành công. | Dùng status phù hợp như 404 hoặc 409. |
| Đưa exception message thô vào `detail` | Có thể làm lộ thông tin nội bộ. | Dùng thông điệp an toàn và mã lỗi ổn định. |
| Client parse nội dung `detail` | Logic phụ thuộc ngôn ngữ và câu chữ. | Dùng `type` hoặc extension `code`. |
| Chỉ xử lý `MethodArgumentNotValidException` | Bỏ sót lỗi method validation hoặc lỗi binding khác. | Xử lý các exception phù hợp với phiên bản Spring và kiểu đầu vào. |
| Coi ProblemDetail là HAL | Client tìm `_links` nhưng response không có cấu trúc HAL. | Phân biệt `application/problem+json` và `application/hal+json`. |
| Công bố link khôi phục nhưng không mô tả schema | Client không biết cách đọc extension. | Định nghĩa extension contract hoặc dùng HAL error model riêng. |
| Trả stack trace trong production | Rò rỉ chi tiết triển khai và bảo mật. | Log nội bộ, trả thông tin an toàn cùng trace ID. |

## Nguyên tắc thiết kế

- Dùng HTTP status để biểu đạt kết quả request.
- Chuẩn hóa body lỗi bằng Problem Details theo RFC 9457.
- Dùng `ProblemDetail`, `ErrorResponse` và `ErrorResponseException` của Spring Framework.
- Dùng `@RestControllerAdvice` cho lỗi domain và `ResponseEntityExceptionHandler` cho lỗi MVC chuẩn.
- Định nghĩa `type` và extension `code` ổn định; không buộc client parse `detail`.
- Mô tả validation violation theo cấu trúc nhất quán.
- Phân biệt Problem Details với HAL; chỉ thêm hypermedia khi hợp đồng có nhu cầu rõ ràng.
- Giữ error body an toàn, không tiết lộ stack trace hoặc dữ liệu nội bộ.
- Kiểm thử status, media type, problem type và extension members.

Error response trong Spring MVC cần giúp client hiểu lỗi bằng status HTTP và một representation nhất quán. `ProblemDetail` cùng `@RestControllerAdvice` và `ResponseEntityExceptionHandler` cung cấp nền tảng để chuẩn hóa lỗi; Spring HATEOAS có thể bổ sung khả năng điều hướng khi hợp đồng cần, nhưng phải công bố rõ media type và cấu trúc extension. Khi mã lỗi ổn định, thông tin an toàn và test bao phủ các trường hợp chính, client có thể xử lý lỗi mà không phụ thuộc vào chi tiết triển khai của server.
