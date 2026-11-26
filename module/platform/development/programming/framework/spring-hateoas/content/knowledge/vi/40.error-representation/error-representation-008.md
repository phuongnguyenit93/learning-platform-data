# Error media type

Một REST API cần trả lỗi theo định dạng mà client có thể đọc và xử lý ổn định. Nếu mỗi endpoint tự tạo JSON lỗi theo một cấu trúc khác nhau, client phải viết nhiều nhánh phân tích và khó phân biệt loại lỗi với một lần phát sinh lỗi cụ thể. HTTP Problem Details chuẩn hóa cách mô tả lỗi bằng media type `application/problem+json`.

Spring HATEOAS cung cấp kiểu `Problem` để tạo representation theo định dạng này, cùng hằng số `MediaTypes.HTTP_PROBLEM_DETAILS_JSON`. Spring Framework cũng cung cấp `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler` để tích hợp Problem Details vào xử lý exception của Spring MVC. Hai API có mục đích gần nhau nhưng là hai kiểu Java khác nhau; cần chọn một cách xây dựng nhất quán cho từng luồng xử lý.

Trong API hypermedia, response lỗi vẫn phải giữ đúng HTTP status và cung cấp đủ thông tin để client quyết định bước tiếp theo. Problem Details không phải một tài nguyên HAL: nó không tự có `_links` hoặc `_embedded`. Nếu cần đường dẫn trợ giúp hoặc URI liên quan, có thể công bố chúng qua extension members hoặc HTTP `Link` header với relation phù hợp.

## Vì sao cần một error media type?

HTTP status code cho biết kết quả ở mức giao thức, ví dụ `400 Bad Request`, `403 Forbidden`, `404 Not Found` hoặc `409 Conflict`. Nhưng status code thường chưa giải thích được nguyên nhân nghiệp vụ cụ thể.

Ví dụ, hai request đều có thể nhận `409 Conflict`:

- Một đơn hàng đã được thanh toán nên không thể hủy.
- Một mã đặt chỗ đã được sử dụng bởi giao dịch khác.

Client cần biết loại vấn đề để hiển thị thông báo phù hợp, hướng dẫn người dùng hoặc quyết định có thể thử lại hay không. `application/problem+json` cung cấp cấu trúc chung để truyền thông tin đó.

Không phải mọi response lỗi đều cần body Problem Details. Nếu HTTP status đã đủ để client hiểu và không cần thông tin bổ sung, response có thể không có body. Problem Details phù hợp khi API cần cung cấp thêm ngữ nghĩa lỗi theo một cấu trúc có thể tái sử dụng.

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-already-paid",
  "title": "Order cannot be cancelled",
  "status": 409,
  "detail": "The order has already been paid.",
  "instance": "urn:uuid:72f1df7c-7ca4-44e2-9a35-f2c772d25b12"
}
```

Client có thể xử lý chung mọi Problem Details trước, rồi dùng `type` để nhận diện trường hợp nghiệp vụ cụ thể. Điều này tránh việc phải suy luận loại lỗi từ chuỗi `detail` vốn có thể được bản địa hóa hoặc thay đổi cách diễn đạt.

## application/problem+json và RFC 9457

RFC 9457, *Problem Details for HTTP APIs*, định nghĩa mô hình JSON và media type `application/problem+json`. RFC này thay thế RFC 7807. Các thành viên chuẩn của đối tượng Problem Details gồm:

| Member | Ý nghĩa | Lưu ý |
|---|---|---|
| `type` | URI reference định danh loại vấn đề | Khóa nhận diện chính của problem type; nếu vắng mặt, mặc định là `about:blank` |
| `title` | Tóm tắt ngắn, dễ đọc của loại vấn đề | Nên ổn định giữa các lần phát sinh, ngoại trừ bản địa hóa |
| `status` | HTTP status code tương ứng với vấn đề | Chỉ mang tính thông tin; HTTP status trong response mới là nguồn sự thật cho giao thức |
| `detail` | Giải thích cụ thể cho lần phát sinh này | Không dùng để client phân loại lỗi bằng cách so sánh chuỗi |
| `instance` | URI reference nhận diện lần phát sinh vấn đề cụ thể | Có thể dùng URI hoặc URN duy nhất cho từng occurrence |

Tất cả các member trên ngoại trừ ý nghĩa mặc định của `type` đều có thể vắng mặt. RFC cho phép bổ sung các extension members ở cấp cao nhất để truyền dữ liệu riêng của problem type.

Ví dụ lỗi validation với extension `errors`:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "urn:uuid:42f8ed0e-ec64-4f3e-9f11-86f63f8a75a4",
  "errors": [
    {
      "pointer": "#/quantity",
      "code": "must-be-positive",
      "detail": "Quantity must be greater than zero."
    },
    {
      "pointer": "#/email",
      "code": "invalid-format",
      "detail": "Email address is not valid."
    }
  ]
}
```

`errors` không phải member chuẩn của RFC 9457; đây là extension do API định nghĩa. Tài liệu API cần mô tả schema, ý nghĩa và cách client xử lý extension này.

### type và instance không có cùng ý nghĩa

`type` định danh một loại vấn đề, ví dụ “đơn hàng đã thanh toán”. Nhiều lần phát sinh khác nhau có thể dùng cùng `type`.

`instance` định danh một lần phát sinh cụ thể, ví dụ một yêu cầu hủy đơn hàng tại một thời điểm. Nó hữu ích cho log, hỗ trợ khách hàng và đối chiếu trace. Có thể dùng `urn:uuid:...` hoặc URI của hệ thống hỗ trợ nếu URI đó thực sự xác định một occurrence.

Nếu `type` là URI HTTP có thể truy cập, tài liệu tại URI đó nên giải thích loại vấn đề cho người hoặc công cụ hỗ trợ. Client không nên tự động truy cập URI `type` trong mọi trường hợp; chỉ nên dereference khi có nhu cầu hiển thị tài liệu hoặc hỗ trợ debug. `type` là định danh trước hết, không phải lệnh điều hướng bắt buộc.

### status trong body và HTTP status

Response có thể chứa `status: 409`, nhưng server vẫn phải gửi HTTP status `409 Conflict`. Client và intermediary sử dụng status của HTTP để xử lý response. Member `status` trong body giúp giữ ngữ cảnh khi nội dung được lưu lại hoặc chuyển qua hệ thống khác.

Không trả HTTP `200 OK` chỉ vì body có `"status": 400`. Làm như vậy khiến cache, gateway, monitoring và client HTTP hiểu sai kết quả request.

## Phân biệt media type lỗi với media type thành công

Media type mô tả định dạng của response body. Nó độc lập với media type của request body và với HTTP status code.

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Request `Content-Type` | `application/json` | Định dạng body mà client gửi lên |
| Request `Accept` | `application/hal+json, application/problem+json` | Những định dạng client có thể nhận |
| Response thành công `Content-Type` | `application/hal+json` | Representation tài nguyên có hypermedia link HAL |
| Response lỗi `Content-Type` | `application/problem+json` | Problem Details theo RFC 9457 |
| HTTP status | `400`, `403`, `409`, `500` | Kết quả request ở mức HTTP |

Ví dụ client gửi JSON nhưng chấp nhận cả HAL và Problem Details:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json, application/problem+json

{
  "productId": "P-100",
  "quantity": -2
}
```

Nếu request hợp lệ, server có thể trả `application/hal+json`. Nếu request vi phạm validation, server có thể trả `application/problem+json`. `Content-Type` của response phản ánh body thực tế được gửi.

Không serialize object Problem Details rồi gắn nhãn `application/hal+json` nếu body không có cấu trúc HAL. Tương tự, response tài nguyên thành công không nên bị gắn nhãn `application/problem+json`.

## application/problem+json khác application/hal+json như thế nào?

HAL mô tả tài nguyên và quan hệ điều hướng qua `_links` cùng `_embedded`. Problem Details mô tả một vấn đề HTTP qua `type`, `title`, `status`, `detail`, `instance` và extension members.

| Đặc điểm | HAL JSON | Problem Details JSON |
|---|---|---|
| Media type | `application/hal+json` | `application/problem+json` |
| Cấu trúc đặc trưng | `_links`, `_embedded` | `type`, `title`, `status`, `detail`, `instance` |
| Mục đích | Biểu diễn tài nguyên và khả năng điều hướng | Giải thích lỗi ở mức HTTP/API |
| Dùng cho | Response thành công hoặc representation tài nguyên | Thường dùng cho response 4xx và 5xx |
| Link | Link relation được serialize trong `_links` | Có thể mở rộng bằng URI hoặc dùng HTTP `Link` header |

Một response lỗi vẫn có thể cung cấp URI tới tài liệu hướng dẫn hoặc tài nguyên liên quan. Ví dụ:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Link: <https://api.example.com/help/permissions>; rel="help"

{
  "type": "https://api.example.com/problems/insufficient-permission",
  "title": "Permission denied",
  "status": 403,
  "detail": "You do not have permission to approve this order.",
  "instance": "urn:uuid:0ec8b150-7c1c-4ca3-9f32-7b7f8f8bda64"
}
```

Header `Link` dùng Web Linking để công bố relation `help`. Đây là cách cung cấp liên kết HTTP bên ngoài JSON Problem Details. Nếu muốn extension member trong body, API có thể định nghĩa `help` hoặc `supportUri`, nhưng phải mô tả semantics riêng.

## Các media type lỗi trong Spring HATEOAS

Spring HATEOAS 3.1.2 cung cấp một số constant trong `org.springframework.hateoas.MediaTypes`:

| Constant | Giá trị | Vai trò |
|---|---|---|
| `HTTP_PROBLEM_DETAILS_JSON` | `application/problem+json` | Media type Problem Details theo RFC 9457 |
| `HTTP_PROBLEM_DETAILS_JSON_VALUE` | `application/problem+json` | Dạng `String` để dùng trong annotation |
| `VND_ERROR_JSON` | `application/vnd.error+json` | Media type lỗi vendor cũ |
| `VND_ERROR_JSON_VALUE` | `application/vnd.error+json` | Dạng `String` tương ứng |

Với API mới, ưu tiên `application/problem+json` và RFC 9457. Spring HATEOAS có kiểu `Problem` trong package `org.springframework.hateoas.mediatype.problem` để xây dựng Problem Details.

Các lớp `VndErrors` và `VndErrors.VndError` trong package `org.springframework.hateoas.mediatype.vnderrors` đã deprecated từ Spring HATEOAS 1.1; tài liệu API hướng dẫn dùng `Problem` để tạo thông báo lỗi trung lập vendor. Constant `VND_ERROR_JSON` vẫn tồn tại để tương thích, nhưng không nên chọn định dạng cũ cho hợp đồng mới.

## Tạo Problem Details bằng Spring HATEOAS Problem

`Problem` là kiểu dữ liệu miền của Spring HATEOAS để xây dựng response Problem Details. Có thể tạo instance rỗng bằng `Problem.create()`, sau đó thiết lập type, title, status, detail, instance và extension properties.

Ví dụ payment service từ chối giao dịch vì số dư không đủ:

```java
import java.net.URI;
import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.mediatype.problem.Problem;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record PaymentRequest(UUID orderId, BigDecimal amount) {}

record PaymentResult(
        boolean success,
        BigDecimal balance,
        BigDecimal amount
) {}

@RestController
public class PaymentController {

    private final PaymentService payments;

    public PaymentController(PaymentService payments) {
        this.payments = payments;
    }

    @PutMapping("/api/payments")
    public ResponseEntity<?> issuePayment(@RequestBody PaymentRequest request) {
        PaymentResult result = payments.issuePayment(
                request.orderId(), request.amount());

        if (result.success()) {
            return ResponseEntity.ok(result);
        }

        Problem problem = Problem.create()
                .withType(URI.create(
                        "https://api.example.com/problems/out-of-credit"))
                .withTitle("Insufficient credit")
                .withStatus(HttpStatus.FORBIDDEN)
                .withDetail("The account balance is lower than the payment amount.")
                .withInstance(URI.create("urn:uuid:" + UUID.randomUUID()))
                .withProperties(Map.of(
                        "balance", result.balance(),
                        "required", result.amount()
                ));

        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .contentType(MediaTypes.HTTP_PROBLEM_DETAILS_JSON)
                .header(HttpHeaders.LINK,
                        "<https://api.example.com/help/payments>; rel=\"help\"")
                .body(problem);
    }
}
```

`PaymentRequest`, `PaymentResult` và `PaymentService` là các kiểu nghiệp vụ của ứng dụng. Ví dụ dùng record accessor như `orderId()` và `balance()`; điều chỉnh theo model thực tế.

Các điểm cần chú ý:

- `withType(...)` nhận URI định danh loại vấn đề. URI nên do API kiểm soát và có tài liệu giải thích.
- `withStatus(...)` đặt status trong body; `ResponseEntity.status(...)` đặt HTTP status tương ứng.
- `withInstance(...)` tạo định danh riêng cho lần phát sinh lỗi.
- `withProperties(...)` thêm extension members ở cấp cao nhất của JSON.
- `contentType(MediaTypes.HTTP_PROBLEM_DETAILS_JSON)` công bố đúng media type.
- `Link` header cung cấp link trợ giúp bằng relation `help`.

Spring HATEOAS reference mô tả `Problem` theo RFC 7807. RFC 9457 đã thay thế RFC 7807 và duy trì mô hình Problem Details JSON tương thích; khi dùng extension members, hãy tuân thủ quy tắc của RFC 9457 và tài liệu API hiện hành.

## Dùng ProblemDetail của Spring Framework

Spring Framework cũng có `org.springframework.http.ProblemDetail`. Kiểu này được tích hợp trực tiếp với Spring MVC exception handling, `ErrorResponse` và `ResponseEntityExceptionHandler`.

Ví dụ xử lý một lỗi nghiệp vụ bằng `@RestControllerAdvice`:

```java
import java.net.URI;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderAlreadyPaidException.class)
    public ProblemDetail handleOrderAlreadyPaid(OrderAlreadyPaidException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "A paid order cannot be cancelled."
        );

        problem.setType(URI.create(
                "https://api.example.com/problems/order-already-paid"));
        problem.setTitle("Order cannot be cancelled");
        problem.setInstance(URI.create("urn:uuid:" + UUID.randomUUID()));
        problem.setProperty("orderId", exception.getOrderId());

        return problem;
    }
}
```

Spring MVC sử dụng `status` trong `ProblemDetail` để đặt HTTP status. Khi serialize bằng Jackson, các property trong map được tạo bởi `setProperty(...)` được đưa lên cấp cao nhất của JSON, thay vì nằm trong object `properties` lồng bên trong.

Từ Spring Framework 7.1, `instance` không còn tự động được gán bằng request path. Theo RFC 9457, `instance` nên nhận diện lần phát sinh vấn đề cụ thể. Vì vậy, hãy gán URI/URN occurrence rõ ràng khi cần định danh để tra cứu hoặc hỗ trợ.

### Problem và ProblemDetail khác nhau thế nào?

| Kiểu | Package | Khi nào dùng |
|---|---|---|
| `Problem` | `org.springframework.hateoas.mediatype.problem` | Khi muốn tạo Problem Details bằng API domain của Spring HATEOAS và dùng `MediaTypes.HTTP_PROBLEM_DETAILS_JSON` |
| `ProblemDetail` | `org.springframework.http` | Khi tích hợp trực tiếp với Spring MVC exception handling và `ErrorResponse` |

Hai kiểu không phải cùng một class và không nên trộn API của chúng trong một object. Cả hai đều có thể biểu diễn các trường Problem Details; chọn kiểu phù hợp với tầng xử lý lỗi của ứng dụng.

## Xử lý exception MVC với ResponseEntityExceptionHandler

Spring Framework định nghĩa:

- `ProblemDetail`: body Problem Details.
- `ErrorResponse`: contract cung cấp HTTP status, response headers và body Problem Details.
- `ErrorResponseException`: exception cơ sở triển khai `ErrorResponse`.
- `ResponseEntityExceptionHandler`: base class cho `@ControllerAdvice`, xử lý các exception Spring MVC và `ErrorResponseException`.

Để bật Problem Details cho các exception MVC dựng sẵn trong Spring Boot, có thể cấu hình:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

Spring Boot sẽ tự cấu hình một `ResponseEntityExceptionHandler` để xử lý các exception tích hợp. Nếu ứng dụng cần thay đổi cách xử lý một exception cụ thể, cần chú ý thứ tự của `@ControllerAdvice` tùy chỉnh so với handler tự cấu hình.

Nếu cần tùy chỉnh nhiều exception MVC, có thể kế thừa `ResponseEntityExceptionHandler`:

```java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class GlobalApiExceptionHandler extends ResponseEntityExceptionHandler {

    @ExceptionHandler(OrderAlreadyPaidException.class)
    public ProblemDetail handleOrderAlreadyPaid(OrderAlreadyPaidException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "A paid order cannot be cancelled."
        );
        problem.setType(URI.create(
                "https://api.example.com/problems/order-already-paid"));
        problem.setTitle("Order cannot be cancelled");
        problem.setProperty("orderId", exception.getOrderId());
        return problem;
    }
}
```

Trong class này cần import thêm `java.net.URI`. `ResponseEntityExceptionHandler` đã xử lý các exception MVC tích hợp; method `@ExceptionHandler` ở trên bổ sung cách ánh xạ exception nghiệp vụ của ứng dụng.

`ResponseEntityExceptionHandler` còn cung cấp các method override để tùy chỉnh response cho từng nhóm lỗi hoặc điểm tạo `ResponseEntity` cuối cùng. Khi override, giữ nguyên status và headers cần thiết do Spring cung cấp, trừ khi hợp đồng API có chủ đích thay đổi chúng.

## Content negotiation cho error media type

Client có thể công bố khả năng nhận Problem Details trong `Accept`:

```http
Accept: application/hal+json, application/problem+json
```

Response thành công có thể dùng HAL JSON, còn response lỗi dùng Problem Details JSON. Server cần bảo đảm message converter có thể ghi body tương ứng và trả đúng `Content-Type`.

Spring Framework nhận diện `ProblemDetail` như một body có media type có thể tạo là `application/problem+json` hoặc `application/problem+xml`. Khi có Jackson JSON/XML phù hợp trên classpath, converter ưu tiên media type Problem Details trong content negotiation.

Một số quy tắc thực tế:

1. Dùng `Accept` để client nêu media type lỗi mà nó hiểu.
2. Dùng `Content-Type` để server công bố đúng định dạng body thực tế.
3. Không thay HTTP status bằng một field trong JSON.
4. Nếu `title` hoặc `detail` được bản địa hóa theo `Accept-Language`, công bố `Content-Language` và cân nhắc `Vary: Accept-Language`.
5. Nếu cùng URI có thể trả body khác nhau theo `Accept`, cache phải phân biệt các biến thể, thường bằng `Vary: Accept`.
6. Không trả HTML stack trace hoặc trang lỗi mặc định cho API client khi hợp đồng yêu cầu Problem Details.

RFC 9457 cho phép nội dung Problem Details được thương lượng theo cơ chế HTTP. Ví dụ của RFC cũng minh họa server trả `application/problem+json` dù client không liệt kê media type đó trong `Accept`, theo các quy tắc HTTP. Dù vậy, client API nên gửi rõ `application/problem+json` để diễn đạt khả năng xử lý lỗi của mình.

## Extension members và liên kết trợ giúp

RFC 9457 cho phép extension members ở cấp cao nhất. Chúng hữu ích khi một loại lỗi cần thông tin bổ sung cho client, chẳng hạn:

- `errors`: danh sách lỗi validation.
- `retryable`: cho biết thao tác có thể thử lại theo quy tắc nghiệp vụ hay không.
- `orderId`: định danh đơn hàng liên quan.
- `balance`: số dư hiện tại trong một lỗi thanh toán.
- `accounts`: danh sách URI của tài nguyên liên quan.

Không có extension member nào trong danh sách trên là chuẩn chung. Mỗi extension phải được tài liệu hóa và có kiểu dữ liệu ổn định.

Nếu cần cung cấp đường dẫn trợ giúp, có thể dùng HTTP `Link` header:

```http
Link: <https://api.example.com/help/orders>; rel="help"
```

Nếu cần đưa URI vào body, dùng extension member có tên và semantics rõ ràng:

```json
{
  "type": "https://api.example.com/problems/payment-required",
  "title": "Payment is required",
  "status": 402,
  "detail": "Complete payment before dispatch.",
  "instance": "urn:uuid:2d91ef67-fc39-4b16-8a62-16dcebf84d9d",
  "paymentUri": "https://api.example.com/payments/P-42"
}
```

`paymentUri` là extension của API. Client không được giả định mọi Problem Details đều có field này.

### Không đưa toàn bộ HAL vào Problem Details một cách tùy tiện

Problem Details và HAL giải quyết hai hợp đồng khác nhau. Nếu body Problem Details được thêm object `_links` theo quy ước riêng, client chỉ hiểu HAL sẽ không tự động biết rằng đây là một HAL representation hợp lệ. Có thể:

- Dùng HTTP `Link` header để cung cấp các link trợ giúp chuẩn.
- Định nghĩa extension member có schema và semantics riêng.
- Trả một tài nguyên lỗi theo media type hypermedia riêng nếu ứng dụng thực sự cần mô hình hóa lỗi như resource có điều hướng.

Không gắn `application/hal+json` cho Problem Details chỉ để có `_links`; cần chọn media type theo cấu trúc thực tế của representation.

## Validation errors và JSON Pointer

Với lỗi validation, client thường cần biết field nào sai. RFC 9457 cho phép API định nghĩa extension như `errors`, trong đó mỗi lỗi có thể dùng JSON Pointer để xác định vị trí trong request body.

Ví dụ request:

```json
{
  "customer": {
    "email": "not-an-email"
  },
  "items": [
    { "productId": "P-100", "quantity": 0 }
  ]
}
```

Response lỗi:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "Correct the invalid fields and submit the request again.",
  "instance": "urn:uuid:4e1a6ed5-7ac4-4c0a-8fb6-98b3e1ed08a0",
  "errors": [
    {
      "pointer": "#/customer/email",
      "code": "invalid-email",
      "detail": "Enter a valid email address."
    },
    {
      "pointer": "#/items/0/quantity",
      "code": "must-be-positive",
      "detail": "Quantity must be greater than zero."
    }
  ]
}
```

JSON Pointer dùng `#` URI fragment và các segment phân tách bằng `/`. Nếu tên property chứa `~` hoặc `/`, JSON Pointer cần escape tương ứng thành `~0` hoặc `~1`. Hãy dùng thư viện hoặc helper phù hợp để tạo pointer, tránh tự nối chuỗi khi tên field có thể chứa ký tự đặc biệt.

Không đưa giá trị nhạy cảm người dùng đã gửi vào `detail` hoặc extension members. Với lỗi xác thực, có thể chỉ trả pointer, code và thông báo an toàn.

## Bản địa hóa title và detail

`title` là bản tóm tắt của problem type và nên giữ ổn định giữa các occurrence, ngoại trừ bản dịch. `detail` giải thích lần phát sinh cụ thể và có thể thay đổi theo ngữ cảnh. Server có thể dùng `Accept-Language` để chọn ngôn ngữ:

```http
GET /api/orders/ORD-1001 HTTP/1.1
Accept: application/problem+json
Accept-Language: vi
```

Ví dụ response:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Content-Language: vi
Vary: Accept-Language
```

Spring Framework hỗ trợ message codes cho `type`, `title` và `detail` của `ErrorResponse`. `ResponseEntityExceptionHandler` có thể phân giải các message code đó qua `MessageSource`. Với exception tùy chỉnh, có thể tổ chức message bundle theo locale để nội dung lỗi nhất quán.

Không dùng câu `detail` đã bản địa hóa làm khóa điều kiện trong client. Client nên phân loại bằng `type` hoặc extension `code` ổn định.

## Kiểm thử Error media type bằng MockMvc

Test cần xác nhận cả HTTP status, media type và các trường Problem Details. Ví dụ controller trả `409 Conflict` khi hủy một đơn đã thanh toán:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorMediaTypeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsProblemDetailsForPaidOrderCancellation() throws Exception {
        mockMvc.perform(post("/api/orders/ORD-1001/cancellation")
                .accept(MediaTypes.HTTP_PROBLEM_DETAILS_JSON))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HTTP_PROBLEM_DETAILS_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.com/problems/order-already-paid"))
            .andExpect(jsonPath("$.title").value("Order cannot be cancelled"))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.instance").exists())
            .andExpect(header().string("Link", containsString("rel=\"help\"")));
    }
}
```

Test giả định fixture `ORD-1001` tồn tại và đã ở trạng thái `PAID`. Nếu controller dùng `Problem` của Spring HATEOAS, `Content-Type` cần tương thích `MediaTypes.HTTP_PROBLEM_DETAILS_JSON`. Nếu dùng `ProblemDetail`, Spring Framework sẽ chọn Problem Details media type qua message converter.

### Kiểm tra extension members

Với lỗi validation, kiểm tra extension member có đúng cấu trúc:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HTTP_PROBLEM_DETAILS_JSON)
        .content("""
                {
                  "productId": "P-100",
                  "quantity": 0
                }
                """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HTTP_PROBLEM_DETAILS_JSON))
    .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/validation-error"))
    .andExpect(jsonPath("$.errors").isArray())
    .andExpect(jsonPath("$.errors[0].pointer").exists())
    .andExpect(jsonPath("$.errors[0].code").exists());
```

Đoạn test này là phần bổ sung trong cùng class `ErrorMediaTypeTest`; cần import thêm `org.springframework.http.MediaType` và static import đã khai báo ở trên. Nội dung request phải khớp DTO validation của ứng dụng.

### Kiểm tra media type thành công và lỗi riêng biệt

Nếu cùng endpoint có thể trả HAL khi thành công và Problem Details khi lỗi, hãy kiểm tra cả hai nhánh. Không chỉ kiểm tra body JSON vì cả hai media type đều dùng cú pháp JSON nhưng có semantics khác nhau.

Các trường hợp nên có:

| Trường hợp | Assertion |
|---|---|
| Request hợp lệ | Status 2xx và `Content-Type: application/hal+json` |
| Request sai dữ liệu | Status 4xx và `Content-Type: application/problem+json` |
| Exception không mong đợi | Status 5xx và body lỗi không tiết lộ stack trace |
| `Accept` có Problem Details | Error response có đúng media type |
| Lỗi validation | `errors` có pointer/code đúng contract |
| Error có help link | HTTP `Link` header có relation `help` |
| Locale khác nhau | `Content-Language` và nội dung `title`/`detail` đúng locale |

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả HTTP 200 với body có `status: 400` | Gateway và client hiểu request thành công | Đặt HTTP status đúng với lỗi |
| Gắn `application/hal+json` cho Problem Details | Client HAL cố phân tích body không có cấu trúc HAL | Dùng `application/problem+json` |
| Gắn `application/problem+json` cho JSON lỗi tùy ý | Client không thể dựa vào schema RFC 9457 | Trả các member chuẩn và extension có tài liệu |
| Dùng `detail` để phân loại lỗi | Client hỏng khi nội dung được dịch hoặc chỉnh câu chữ | Dùng `type` hoặc extension code ổn định |
| Dùng cùng URI cho mọi `instance` | Không thể phân biệt các lần phát sinh lỗi | Tạo URI/URN occurrence riêng |
| Dùng `type` thay cho `instance` | Trộn loại lỗi với lần phát sinh cụ thể | Giữ `type` ổn định, `instance` duy nhất |
| Trả stack trace hoặc SQL message | Lộ chi tiết implementation và thông tin nhạy cảm | Chuyển exception nội bộ thành thông báo an toàn |
| Coi extension member là chuẩn RFC | Client khác không biết cách diễn giải | Tài liệu hóa extension và schema |
| Dùng `VndErrors` cho API mới | Phụ thuộc abstraction đã deprecated | Dùng `Problem` hoặc `ProblemDetail` |
| Nhầm `Problem` với `ProblemDetail` | Dùng sai package hoặc converter | Chọn API theo tầng Spring HATEOAS hay Spring Framework |
| Giả định Problem Details tự có `_links` | Client không tìm được relation HAL | Dùng Link header hoặc extension đã định nghĩa |
| Chỉ kiểm tra JSON body | Bỏ sót status và media type sai | Assert status, Content-Type, headers và body |

## Quy trình thiết kế Error media type

1. Chọn HTTP status phản ánh đúng semantics của lỗi.
2. Dùng `application/problem+json` cho JSON Problem Details.
3. Chọn `type` URI ổn định cho từng loại vấn đề và cung cấp tài liệu khi phù hợp.
4. Đặt `title` ổn định, `detail` an toàn và cụ thể cho occurrence.
5. Dùng `instance` URI/URN riêng khi cần truy vết từng lần phát sinh.
6. Chỉ thêm extension members có schema và semantics được công bố.
7. Dùng `Problem` của Spring HATEOAS hoặc `ProblemDetail` của Spring Framework theo kiến trúc xử lý lỗi.
8. Dùng `ResponseEntityExceptionHandler` hoặc `@RestControllerAdvice` để chuẩn hóa lỗi MVC và lỗi nghiệp vụ.
9. Công bố link trợ giúp qua HTTP `Link` header hoặc extension phù hợp.
10. Kiểm thử HTTP status, media type, body, extension, locale và header bằng MockMvc.

## Kết luận

`application/problem+json` cung cấp một định dạng lỗi thống nhất theo RFC 9457 cho REST API. HTTP status vẫn quyết định kết quả giao thức; các member `type`, `title`, `detail`, `instance` và extension members giúp client hiểu nguyên nhân và xử lý lỗi. Spring HATEOAS cung cấp `Problem` cùng `MediaTypes.HTTP_PROBLEM_DETAILS_JSON`; Spring Framework cung cấp `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler`. Với API hypermedia, cần phân biệt Problem Details với HAL, công bố link trợ giúp bằng cơ chế phù hợp và giữ extension members ổn định. Khi status, media type, error type và instance được thiết kế rõ ràng, client có thể xử lý lỗi nhất quán mà không phụ thuộc vào chuỗi thông báo hoặc chi tiết implementation.

## Tài liệu tham khảo

- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): media type `application/problem+json`, các member chuẩn, extension members và problem type.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): HTTP status, content negotiation và semantics của response.
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html): HTTP `Link` header và link relation.
- [Spring HATEOAS Reference – HTTP Problem Details](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.problem): kiểu `Problem` và cách tạo Problem Details response.
- [Spring HATEOAS – Problem API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/problem/Problem.html): factory, standard members và extension properties.
- [Spring HATEOAS – MediaTypes API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html): `HTTP_PROBLEM_DETAILS_JSON` và `VND_ERROR_JSON`.
- [Spring Framework – Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler` và Spring MVC integration.
