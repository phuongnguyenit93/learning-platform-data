# Problem detail

Khi API trả lỗi, client cần biết request thất bại vì lý do gì và có thể xử lý tiếp như thế nào. Chỉ trả một status code như `400`, `404` hoặc `409` thường chưa đủ để phân biệt các lỗi nghiệp vụ. Mỗi endpoint tự tạo một cấu trúc lỗi riêng cũng khiến client phải viết nhiều bộ phân tích khác nhau.

**Problem Details for HTTP APIs**, được chuẩn hóa trong RFC 9457, cung cấp một cấu trúc chung cho nội dung lỗi HTTP. Spring Framework hỗ trợ chuẩn này qua `ProblemDetail`, `ErrorResponse`, `ErrorResponseException` và `ResponseEntityExceptionHandler`. Với API Spring HATEOAS, Problem Details giúp thống nhất cách mô tả lỗi của endpoint resource, action và hypermedia workflow.

Bài học này thuộc chương **Error representation** trong module **SPRING_HATEOAS**, tập trung vào các trường chuẩn của Problem Details, cách tạo response `application/problem+json`, mở rộng dữ liệu lỗi, xử lý exception tập trung, biểu diễn validation error, bảo vệ thông tin nhạy cảm và kiểm thử bằng MockMvc.

Sau bài học, bạn có thể:

- Giải thích mục đích của RFC 9457 và cấu trúc Problem Details.
- Phân biệt `type`, `title`, `status`, `detail` và `instance`.
- Tạo `ProblemDetail` bằng Spring Framework.
- Mở rộng problem response bằng extension properties.
- Dùng `ErrorResponse` và `ErrorResponseException`.
- Xây dựng `@RestControllerAdvice` với `ResponseEntityExceptionHandler`.
- Chuẩn hóa lỗi validation và lỗi nghiệp vụ.
- Xử lý lỗi authentication/authorization trong security filter chain.
- Kết hợp Problem Details với API HATEOAS mà không nhầm media type.
- Kiểm thử status, content type, problem type và extension fields.

## 1. Vì sao cần Problem Details?

Giả sử một API có nhiều loại lỗi:

- Request gửi JSON không hợp lệ.
- Đơn hàng không tồn tại.
- Đơn hàng đã được giao nên không thể hủy.
- Người dùng không có quyền phê duyệt.
- Một field không thỏa validation.

Nếu mỗi lỗi có cấu trúc riêng, client phải xử lý nhiều dạng response:

```json
{ "error": "ORDER_NOT_FOUND", "message": "Không tìm thấy đơn hàng" }
```

```json
{ "success": false, "reason": "INVALID_INPUT", "errors": [] }
```

```json
{ "code": 409, "description": "Order cannot be cancelled" }
```

RFC 9457 thống nhất một cấu trúc có thể dùng cho nhiều HTTP API. Client có thể đọc các trường chuẩn, sau đó sử dụng `type` hoặc extension fields để phân biệt các loại lỗi nghiệp vụ.

Problem Details không thay thế HTTP status code. Status vẫn thể hiện kết quả ở tầng HTTP; body bổ sung thông tin máy đọc được và thông tin giúp người dùng hoặc nhà phát triển hiểu vấn đề.

## 2. RFC 9457 và application/problem+json

RFC 9457 định nghĩa định dạng Problem Details cho HTTP APIs và thay thế RFC 7807. Media type JSON tương ứng là:

```http
Content-Type: application/problem+json
```

Ví dụ response:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng có mã 42.",
  "instance": "/orders/42"
}
```

Client không cần biết exception Java nào đã xảy ra. Nó có thể kiểm tra HTTP status, đọc `type` để nhận diện loại problem và dùng `detail` để hiển thị thông báo phù hợp.

`application/problem+json` là media type của error representation. Nó khác `application/hal+json`, vốn mô tả resource representation có `_links` và `_embedded`.

## 3. Năm trường chuẩn của Problem Details

RFC 9457 định nghĩa năm thành viên chuẩn:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `type` | URI reference | Định danh loại vấn đề. Nếu bỏ qua, mặc định là `about:blank`. |
| `title` | String | Tóm tắt ngắn gọn loại vấn đề; thường ổn định giữa các lần xuất hiện, trừ khi được bản địa hóa. |
| `status` | Number | HTTP status code gắn với problem. Đây là thông tin tham khảo trong body; HTTP response status mới là status thực tế. |
| `detail` | String | Giải thích cụ thể cho lần xảy ra lỗi này, giúp client hiểu hoặc khắc phục vấn đề. |
| `instance` | URI reference | Định danh lần xuất hiện cụ thể của problem. |

Không bắt buộc phải có cả năm trường trong mọi response. Hãy cung cấp các trường có ý nghĩa và bảo đảm body `status` khớp HTTP status thực tế.

`detail` không phải nơi đưa stack trace hoặc exception message nội bộ. `instance` cũng không nhất thiết là URL của resource gây lỗi; nó định danh occurrence của problem và có thể là URI path của request hoặc URI riêng cho một mã sự cố.

## 4. Hiểu type và about:blank

`type` là định danh loại problem. Khi không cung cấp, RFC 9457 xem type là `about:blank`, nghĩa là problem không có semantics bổ sung ngoài HTTP status.

Với lỗi nghiệp vụ, nên dùng URI ổn định cho từng loại problem:

```text
https://api.example.com/problems/order-not-found
https://api.example.com/problems/order-cannot-be-cancelled
https://api.example.com/problems/validation-error
```

URI type có thể trỏ tới trang tài liệu giải thích problem. Nếu URI có thể truy cập, trang đó nên mô tả ý nghĩa, điều kiện phát sinh, cách xử lý và các extension fields liên quan.

Không dùng tên class exception như `com.example.OrderNotFoundException` làm type công khai. Class có thể được đổi tên hoặc chuyển package mà không làm thay đổi semantics của API. URI type nên ổn định và độc lập với implementation.

Khi type là `about:blank`, title nên tương ứng với mô tả chuẩn của HTTP status. Với type riêng, title mô tả loại problem đó và không nên thay đổi tùy theo từng occurrence.

## 5. Phân biệt title, detail và instance

Ba trường này phục vụ mục đích khác nhau:

| Trường | Ví dụ | Cách dùng |
|---|---|---|
| `title` | `Order cannot be cancelled` | Tóm tắt loại lỗi, có thể được bản địa hóa. |
| `detail` | `Đơn hàng 42 đã được giao nên không thể hủy.` | Giải thích tình huống cụ thể và gợi ý khắc phục nếu phù hợp. |
| `instance` | `/orders/42/cancellation` | Định danh occurrence gắn với request đã thất bại. |

Nếu có request ID hoặc trace ID, có thể công bố một extension field như `requestId` để người dùng gửi cho bộ phận hỗ trợ. Không nhầm `requestId` với `instance`: một request có thể tạo nhiều problem occurrence, còn instance định danh problem occurrence theo hợp đồng API.

## 6. Tạo ProblemDetail bằng Spring Framework

Spring Framework 6 trở lên cung cấp `org.springframework.http.ProblemDetail`. Có thể tạo đối tượng bằng factory `forStatus(...)` hoặc `forStatusAndDetail(...)`:

```java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy đơn hàng có mã 42.");

problem.setType(URI.create(
        "https://api.example.com/problems/order-not-found"));
problem.setTitle("Order not found");
problem.setInstance(URI.create("/orders/42"));
```

`forStatusAndDetail(...)` khởi tạo problem với status và detail. Các setter cho phép định nghĩa type, title và instance. Khi trả `ProblemDetail` từ controller hoặc exception handler, Spring MVC dùng status trong problem làm HTTP status và chọn media type problem tương ứng khi content negotiation phù hợp.

Ví dụ endpoint có thể trả trực tiếp:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/orders/{id}")
OrderResponse one(@PathVariable Long id) {
    return orderService.findResponseById(id);
}
```

Trong trường hợp có lỗi, controller không cần tự tạo response JSON theo cấu trúc riêng; exception handler có thể chuyển exception thành `ProblemDetail` thống nhất.

## 7. Thêm extension properties

RFC 9457 cho phép thêm extension members để cung cấp thông tin riêng của API. Ví dụ một validation problem có thể bổ sung danh sách lỗi field:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "Một hoặc nhiều trường không hợp lệ.");

problem.setType(URI.create(
        "https://api.example.com/problems/validation-error"));
problem.setTitle("Request validation failed");
problem.setProperty("code", "VALIDATION_ERROR");
problem.setProperty("errors", List.of(
        Map.of(
                "pointer", "/email",
                "detail", "Phải là địa chỉ email hợp lệ."),
        Map.of(
                "pointer", "/quantity",
                "detail", "Giá trị phải lớn hơn 0.")));
```

Với Jackson, Spring đăng ký `ProblemDetailJacksonMixin` để map `properties` được serialize thành các property cấp cao nhất của JSON. Response sẽ có dạng:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "Một hoặc nhiều trường không hợp lệ.",
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "pointer": "/email",
      "detail": "Phải là địa chỉ email hợp lệ."
    },
    {
      "pointer": "/quantity",
      "detail": "Giá trị phải lớn hơn 0."
    }
  ]
}
```

Map `properties` không xuất hiện thành một object lồng tên `properties`; các extension được đưa lên cấp cao nhất. Hãy đặt tên extension rõ ràng, tài liệu hóa schema và tránh trùng tên với năm trường chuẩn.

## 8. Thiết kế extension fields ổn định

Extension fields là một phần hợp đồng API. Nên thống nhất schema giữa các endpoint:

| Extension | Ý nghĩa | Quy tắc |
|---|---|---|
| `code` | Mã lỗi ổn định cho client | Không dùng message đã bản địa hóa làm code. |
| `requestId` | Mã để tra cứu log hoặc hỗ trợ | Không chứa token hoặc thông tin định danh bí mật. |
| `errors` | Danh sách lỗi validation | Có cấu trúc nhất quán như `pointer`, `code`, `detail`. |
| `retryAfterSeconds` | Gợi ý thời gian chờ trước khi thử lại | Chỉ cung cấp khi server có thể xác định thời gian hợp lý. |

Client nên dựa vào `type`, `code` và các extension được tài liệu hóa để xử lý logic. Không nên parse chuỗi `detail` để suy ra loại lỗi vì detail có thể được bản địa hóa hoặc thay đổi câu chữ.

Không đưa toàn bộ object exception, entity hoặc request body vào extension. Extension chỉ nên chứa dữ liệu có ích cho client và được phép công khai.

## 9. ProblemDetail và ErrorResponse

Spring cung cấp hai abstraction có vai trò khác nhau:

| Kiểu | Vai trò |
|---|---|
| `ProblemDetail` | Body theo RFC 9457: type, title, status, detail, instance và extension properties. |
| `ErrorResponse` | Hợp đồng hoàn chỉnh của error response: HTTP status, headers và body `ProblemDetail`. |
| `ErrorResponseException` | Implementation cơ sở để exception mang status, headers và problem body. |
| `ResponseEntityExceptionHandler` | Base class cho `@ControllerAdvice`, xử lý các exception Spring MVC và tạo problem response. |

Các exception Spring MVC tích hợp sẵn triển khai `ErrorResponse`. Nhờ đó, các lỗi như method không được hỗ trợ, media type không hỗ trợ, request body không đọc được hoặc validation thất bại có thể được biểu diễn theo cùng định dạng.

`ProblemDetail` tập trung vào body. `ErrorResponse` còn mang headers và status cần dùng cho HTTP response, giúp exception tự mô tả cách ánh xạ sang response.

## 10. Ném ErrorResponseException cho lỗi nghiệp vụ

`ErrorResponseException` là một runtime exception có thể được dùng trực tiếp hoặc mở rộng thành exception nghiệp vụ:

```java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponseException;

public class OrderNotFoundException extends ErrorResponseException {

    public OrderNotFoundException(Long orderId) {
        super(HttpStatus.NOT_FOUND, createProblem(orderId), null);
    }

    private static ProblemDetail createProblem(Long orderId) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đơn hàng có mã " + orderId + ".");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        problem.setProperty("orderId", orderId);

        return problem;
    }
}
```

Khi service ném `OrderNotFoundException`, Spring MVC có thể dùng thông tin `ErrorResponse` để tạo response problem mà không cần một handler riêng chỉ cho exception này.

Status truyền vào constructor phải nhất quán với status của `ProblemDetail`. Không để exception khai báo `404` trong HTTP response nhưng body lại có `status: 400`.

## 11. Xử lý exception tập trung bằng ResponseEntityExceptionHandler

`ResponseEntityExceptionHandler` là base class thuận tiện cho REST API dùng Spring MVC. Có thể mở rộng nó trong `@RestControllerAdvice` để xử lý exception nghiệp vụ và giữ cơ chế xử lý exception MVC tích hợp sẵn:

```java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    @ExceptionHandler(OrderCannotBeCancelledException.class)
    ProblemDetail handleOrderCannotBeCancelled(
            OrderCannotBeCancelledException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Đơn hàng không thể hủy ở trạng thái hiện tại.");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-cannot-be-cancelled"));
        problem.setTitle("Order cannot be cancelled");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_CANNOT_BE_CANCELLED");

        return problem;
    }
}
```

Ví dụ dùng `409 Conflict` vì request hợp lệ về cú pháp nhưng xung đột với trạng thái hiện tại của resource. `instance` được đặt rõ ràng từ request path để response không phụ thuộc vào hành vi mặc định có thể khác giữa các phiên bản Spring.

Base class tiếp tục xử lý các exception MVC mà nó hỗ trợ. Với exception nghiệp vụ riêng, thêm `@ExceptionHandler` và trả `ProblemDetail` hoặc `ResponseEntity<ProblemDetail>`.

## 12. Bật Problem Details cho exception MVC trong Spring Boot

Với Spring Boot phiên bản hỗ trợ cấu hình này, có thể bật Problem Details cho các exception MVC tích hợp bằng:

```properties
spring.mvc.problemdetails.enabled=true
```

Spring Boot sẽ cấu hình một `ResponseEntityExceptionHandler` để xử lý các exception MVC phổ biến theo RFC 9457. Điều này giúp các lỗi như `400`, `404`, `405` hoặc `415` có cấu trúc problem thống nhất.

Nếu ứng dụng cần tùy chỉnh một exception MVC cụ thể trong khi Boot đã đăng ký handler mặc định, hãy kiểm tra thứ tự `@ControllerAdvice`. Handler do Boot tự cấu hình có order `0`; advice tùy chỉnh cần có thứ tự ưu tiên cao hơn nếu muốn nhận exception trước. Tránh vô tình tạo hai handler cùng nhận một exception mà không kiểm soát thứ tự.

Nếu đã tự mở rộng `ResponseEntityExceptionHandler`, không cần thêm một handler khác chỉ để bật cùng chức năng cho các exception MVC.

## 13. Xử lý lỗi validation

Với Bean Validation, Spring MVC có thể ném `MethodArgumentNotValidException` khi request body không thỏa constraint. `ResponseEntityExceptionHandler` đã có cơ chế xử lý exception này và tạo `ProblemDetail`.

Ví dụ request DTO:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
        @NotBlank String customerName,
        @Email String email,
        @Min(1) int quantity) {
}
```

Controller:

```java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping("/orders")
OrderResponse create(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
```

Nếu validation thất bại, API nên trả `400 Bad Request` với `application/problem+json` và extension `errors` mô tả từng field. Ví dụ:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "detail": "Một hoặc nhiều trường không hợp lệ.",
  "errors": [
    {
      "pointer": "/email",
      "code": "Email",
      "detail": "Phải là địa chỉ email hợp lệ."
    },
    {
      "pointer": "/quantity",
      "code": "Min",
      "detail": "Giá trị phải lớn hơn hoặc bằng 1."
    }
  ]
}
```

RFC 9457 không áp đặt schema cụ thể cho extension `errors`. Ứng dụng phải tài liệu hóa cấu trúc này, bao gồm quy tắc `pointer` dùng JSON Pointer hay tên field đơn giản. Không trả giá trị đầu vào nhạy cảm trong lỗi validation.

## 14. Tùy chỉnh validation error trong advice

Nếu cần một schema extension nhất quán, có thể override `handleMethodArgumentNotValid(...)` của `ResponseEntityExceptionHandler`. Ví dụ theo chữ ký Spring Framework 6.2:

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.context.request.WebRequest;

@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    List<Map<String, String>> errors = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> Map.of(
                    "pointer", "/" + error.getField().replace(".", "/"),
                    "code", error.getCode() == null ? "InvalidValue" : error.getCode(),
                    "detail", error.getDefaultMessage() == null
                            ? "Giá trị không hợp lệ."
                            : error.getDefaultMessage()))
            .toList();

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status,
            "Một hoặc nhiều trường không hợp lệ.");
    problem.setType(URI.create(
            "https://api.example.com/problems/validation-error"));
    problem.setTitle("Request validation failed");
    problem.setProperty("code", "VALIDATION_ERROR");
    problem.setProperty("errors", errors);

    return handleExceptionInternal(ex, problem, headers, status, request);
}
```

Ví dụ trên dùng chữ ký API của Spring Framework 6.2. Khi dùng phiên bản khác, hãy kiểm tra chữ ký override trong Javadoc tương ứng. Mapping field path trong ví dụ là minh họa; nếu cần JSON Pointer chuẩn, phải escape `~` thành `~0` và `/` thành `~1` trong từng token.

Gọi `handleExceptionInternal(...)` giúp response đi qua cơ chế chung của base class, giữ status và headers mà Spring MVC đã xác định.

## 15. Phân biệt lỗi HTTP và lỗi nghiệp vụ

Problem Details không có nghĩa mọi lỗi đều trả `400`. Hãy chọn HTTP status phản ánh đúng loại lỗi:

| Tình huống | Status thường dùng | Problem type gợi ý |
|---|---:|---|
| JSON sai cú pháp hoặc field không hợp lệ | `400 Bad Request` | `/problems/validation-error` |
| Chưa xác thực | `401 Unauthorized` | `/problems/authentication-required` |
| Đã xác thực nhưng thiếu quyền | `403 Forbidden` | `/problems/access-denied` |
| Resource không tồn tại | `404 Not Found` | `/problems/order-not-found` |
| Method không được hỗ trợ | `405 Method Not Allowed` | `about:blank` hoặc type riêng |
| Media type request không hỗ trợ | `415 Unsupported Media Type` | `about:blank` hoặc type riêng |
| Xung đột với trạng thái hiện tại | `409 Conflict` | `/problems/order-cannot-be-cancelled` |
| Quá nhiều request | `429 Too Many Requests` | `/problems/rate-limit-exceeded` |
| Lỗi không dự kiến phía server | `500 Internal Server Error` | `/problems/internal-error` |

Status cụ thể phụ thuộc hợp đồng API và ngữ cảnh. Không dùng `200 OK` chỉ vì server muốn trả một object lỗi; client và intermediary cần status HTTP chính xác để xử lý retry, authentication và cache.

## 16. Problem Details trong API HATEOAS

Resource response thành công có thể dùng `application/hal+json`, chứa `_links` và `_embedded`. Problem Details thường dùng `application/problem+json`, có schema lỗi riêng theo RFC 9457.

Không mặc định rằng mọi Problem Details đều là HAL document. Khi request thất bại, response problem không tự động có `_links.self`, `_embedded` hoặc affordance như một `RepresentationModel` thông thường.

Nếu client cần thông tin giúp xử lý lỗi, có thể:

- Dùng `type` trỏ tới tài liệu mô tả loại lỗi.
- Dùng extension field ổn định như `retryAfterSeconds`, `requestId` hoặc `errors`.
- Dùng HTTP `Link` header với relation phù hợp, ví dụ `help`, nếu API muốn công bố URI hướng dẫn.
- Tạo một media type lỗi riêng có hypermedia nếu hợp đồng thật sự cần điều hướng phức tạp, nhưng phải định nghĩa và tài liệu hóa rõ.

Ví dụ header hướng dẫn:

```http
Link: <https://api.example.com/problems/order-cannot-be-cancelled>; rel="help"
```

Không nhúng `_links` vào Problem Details rồi gọi đó là HAL nếu media type vẫn là `application/problem+json`. Nếu dùng extension chứa link, hãy mô tả schema và semantics để client biết đó là extension của API.

## 17. Lỗi authentication và authorization

Lỗi do Spring Security filter chain xảy ra trước khi request tới controller. Vì vậy, `@RestControllerAdvice` không nhất thiết nhận được các lỗi `401` và `403` do security filter phát sinh.

Để trả Problem Details nhất quán cho security errors, cấu hình `AuthenticationEntryPoint` cho trường hợp chưa xác thực và `AccessDeniedHandler` cho trường hợp đã xác thực nhưng không đủ quyền. Các handler này cần ghi status, `Content-Type: application/problem+json` và body theo RFC 9457.

Không đưa chi tiết xác thực như token, tên provider nội bộ, stack trace hoặc thông tin người dùng khác vào `detail`. Với resource mà chính sách bảo mật yêu cầu che giấu sự tồn tại, ứng dụng có thể trả `404` thay vì tiết lộ `403`; hãy áp dụng nhất quán theo threat model và hợp đồng API.

## 18. Bảo mật thông tin trong Problem Details

Error response là dữ liệu công khai gửi qua mạng. Chỉ đưa thông tin cần thiết để client hiểu và khắc phục request:

- Không gửi stack trace hoặc tên class nội bộ.
- Không gửi SQL, câu lệnh database, hostname nội bộ hoặc file path máy chủ.
- Không đưa access token, cookie, secret hoặc request body nhạy cảm vào extension.
- Không phản chiếu nguyên văn input chưa được lọc nếu nó có thể chứa HTML, script hoặc dữ liệu cá nhân.
- Không tiết lộ resource có tồn tại hay không nếu chính sách yêu cầu che giấu.
- Dùng `requestId` hoặc `instance` để đội vận hành tra log ở hệ thống nội bộ.

`detail` nên đủ rõ cho người dùng API nhưng không tiết lộ cách triển khai. Log nội bộ có thể lưu exception và stack trace đầy đủ; response công khai chỉ nên chứa mã tra cứu và thông tin an toàn.

## 19. Quốc tế hóa title và detail

Spring `ErrorResponse` hỗ trợ message code để `ResponseEntityExceptionHandler` tra cứu `type`, `title` và `detail` thông qua `MessageSource`. Cách này cho phép trả thông điệp theo locale của request mà vẫn giữ problem type ổn định.

Ví dụ message bundle:

```properties
problemDetail.title.com.example.OrderNotFoundException=Order not found
problemDetail.com.example.OrderNotFoundException=Không tìm thấy đơn hàng được yêu cầu.
```

Mã message mặc định cho title và detail được tạo dựa trên tên đầy đủ của exception class. Có thể cung cấp message code tùy chỉnh khi triển khai `ErrorResponse` hoặc `ErrorResponseException`.

Không bản địa hóa `type` thành một URI khác cho từng ngôn ngữ. `type` và extension `code` nên ổn định; `title` và `detail` có thể được bản địa hóa. Nếu client cần logic máy đọc được, hãy dựa vào type/code thay vì so sánh câu chữ.

## 20. Client đọc Problem Details

Client nên kiểm tra HTTP status và media type trước khi diễn giải body. Nếu response có `application/problem+json`, có thể parse các trường chuẩn và extension đã biết.

Quy tắc xử lý gợi ý:

1. Đọc HTTP status để quyết định nhóm xử lý tổng quát.
2. Đọc `type` để xác định loại problem cụ thể.
3. Dùng extension `code` hoặc `errors` nếu API đã công bố schema.
4. Hiển thị `detail` cho người dùng khi phù hợp, nhưng không dùng nó làm điều kiện logic.
5. Dùng `instance` hoặc `requestId` khi cần liên hệ bộ phận hỗ trợ.
6. Nếu gặp `type` chưa biết, fallback theo HTTP status và không giả định extension chưa biết.

Client nên chịu được extension field mới. RFC 9457 cho phép API mở rộng problem object; client không nên thất bại chỉ vì response có thêm property mà nó chưa biết.

## 21. Kiểm thử Problem Details bằng MockMvc

Test nên xác nhận cả HTTP status, media type và body:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderProblemDetailTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsProblemDetailWhenOrderDoesNotExist() throws Exception {
        mockMvc.perform(get("/orders/999999")
                        .accept("application/problem+json"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        "application/problem+json"))
                .andExpect(jsonPath("$.type")
                        .value("https://api.example.com/problems/order-not-found"))
                .andExpect(jsonPath("$.title").value("Order not found"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.detail").isNotEmpty())
                .andExpect(jsonPath("$.instance").value(endsWith("/orders/999999")))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }
}
```

Test giả định `/orders/999999` không tồn tại và exception handler công bố extension `code`. Nếu API dùng instance URI khác request path, điều chỉnh assertion theo quy ước instance đã chọn.

## 22. Kiểm thử validation extension

Với validation problem, kiểm tra cấu trúc extension `errors` và các field path:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void returnsFieldErrorsForInvalidCreateOrderRequest() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept("application/problem+json")
                    .content("""
                            {
                              "customerName": "",
                              "email": "not-an-email",
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    "application/problem+json"))
            .andExpect(jsonPath("$.type")
                    .value("https://api.example.com/problems/validation-error"))
            .andExpect(jsonPath("$.errors").isArray())
            .andExpect(jsonPath("$.errors.length()").value(3));
}
```

Ví dụ giả định request DTO dùng `@NotBlank`, `@Email`, `@Min(1)` và handler đã chuẩn hóa lỗi thành extension `errors`. Nếu locale thay đổi, không assert nguyên văn `detail`; hãy kiểm tra type, code và cấu trúc field error.

## 23. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ trả status code, không có problem body | Client khó phân biệt loại lỗi. | Dùng `ProblemDetail` cho các error response cần nội dung máy đọc được. |
| HTTP status khác body `status` | Client nhận hai tín hiệu mâu thuẫn. | Dùng cùng status khi tạo body và response. |
| Dùng `detail` làm error code | Client bị phụ thuộc câu chữ và locale. | Dùng `type` hoặc extension `code` ổn định. |
| Dùng class exception làm `type` | Refactor nội bộ làm thay đổi hợp đồng công khai. | Dùng URI type ổn định theo semantics. |
| Đưa stack trace vào `detail` | Lộ thông tin triển khai và dữ liệu nhạy cảm. | Ghi log nội bộ, trả thông báo an toàn. |
| Nhầm Problem Details với HAL | Client dùng sai parser hoặc kỳ vọng `_links`. | Dùng đúng media type `application/problem+json`. |
| Đặt extension trong object `properties` lồng | JSON không theo cách Spring Jackson mixin serialize. | Dùng `setProperty`; Spring sẽ flatten map ra top-level. |
| Cho rằng `@ControllerAdvice` bắt mọi lỗi security | `401`/`403` từ filter chain có thể không đi qua MVC advice. | Cấu hình entry point và access denied handler. |
| Bắt mọi `Exception` rồi trả 400 | Lỗi server bị phân loại sai. | Ánh xạ exception theo nguyên nhân và status chính xác. |
| Chỉ test body, không test Content-Type | Client không biết chọn parser nào. | Kiểm tra `application/problem+json`. |

## 24. Quy trình triển khai Problem Details

1. Chọn các loại lỗi API cần body máy đọc được và xác định HTTP status tương ứng.
2. Định nghĩa URI `type` ổn định cho từng loại lỗi nghiệp vụ.
3. Thiết kế `title`, `detail`, `instance` và extension fields theo một quy ước chung.
4. Dùng `ProblemDetail` để tạo body và bảo đảm status khớp HTTP response.
5. Dùng `ErrorResponseException` hoặc `@RestControllerAdvice` cho lỗi nghiệp vụ.
6. Dùng `ResponseEntityExceptionHandler` để chuẩn hóa exception MVC và validation.
7. Cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler` cho lỗi phát sinh trong Spring Security filter chain.
8. Trả `application/problem+json` và giữ riêng media type lỗi với HAL resource representation.
9. Loại bỏ stack trace, secret và dữ liệu nội bộ khỏi response.
10. Kiểm thử status, content type, type, instance và extension fields qua MockMvc.
11. Tài liệu hóa problem type, extension schema, locale và cách client xử lý lỗi chưa biết.

Problem Details giúp API trả lỗi theo một hợp đồng nhất quán, có thể được client xử lý mà không phụ thuộc vào exception hoặc cấu trúc nội bộ. Trong Spring HATEOAS, hãy giữ rõ ranh giới giữa resource representation và error representation, đồng thời dùng problem type và extension fields ổn định để client có thể phục hồi hoặc hướng dẫn người dùng đúng cách.

## Tài liệu tham khảo

- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [Spring Framework – Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework – ProblemDetail API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework – ErrorResponse API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework – ErrorResponseException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/ErrorResponseException.html)
- [Spring Framework – ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
