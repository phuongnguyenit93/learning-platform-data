# ProblemDetail và ErrorResponse theo khả năng phiên bản trong Spring Framework

## Mục tiêu học tập

Khi một REST API nhận JSON sai, dữ liệu form vi phạm constraint, thiếu query parameter hoặc không tìm thấy một đơn hàng, server cần trả về lỗi mà client **đọc được bằng máy**, **dễ hiểu**, **an toàn** và **ổn định theo phiên bản**. Trong Spring Framework hiện đại, hai khái niệm quan trọng là `ProblemDetail` và `ErrorResponse`. Chúng không đồng nghĩa:

- `ProblemDetail` là **đối tượng nội dung lỗi** dựa trên chuẩn Problem Details for HTTP APIs (RFC 9457, kế thừa RFC 7807).
- `ErrorResponse` là **hợp đồng phản hồi lỗi** của Spring, bao gồm HTTP status, headers và một body dạng `ProblemDetail`. Nhiều exception của Spring MVC/WebFlux hiện thực hợp đồng này.

Bài thuộc nhóm **Phản hồi lỗi** và đặc biệt nhấn mạnh cụm **“theo khả năng phiên bản”**: phải xác định dự án đang dùng Spring 5.x, 6.0, 6.1, 6.2 hoặc 7.x trước khi sao chép một API mới. Sau bài học, bạn có thể:

1. Giải thích năm trường chuẩn `type`, `title`, `status`, `detail`, `instance` và extension properties.
2. Tạo `ProblemDetail` bằng `forStatus(...)`/`forStatusAndDetail(...)`, gán nội dung phù hợp và trả qua `@ExceptionHandler`.
3. Phân biệt `ProblemDetail`, `ErrorResponse`, `ErrorResponseException` và `ResponseEntityExceptionHandler`.
4. Tùy biến lỗi `@Valid @RequestBody` qua `MethodArgumentNotValidException` và lỗi native method validation qua `HandlerMethodValidationException` ở phiên bản có hỗ trợ.
5. Hiểu cấu hình `spring.mvc.problemdetails.enabled`/`spring.webflux.problemdetails.enabled`, cách dùng `@RestControllerAdvice` và thứ tự handler.
6. Dùng `MessageSource` để địa phương hóa `detail` mà không làm lộ dữ liệu riêng tư; bổ sung danh sách field errors có quy ước ổn định.
7. Viết và kiểm thử một Spring Boot 3.5 / Java 17+ API với kết quả 201, 400 và 404 có thể dự đoán.
8. Chọn chiến lược tương thích ngược cho Spring 5.x hoặc dự án không bật phản hồi chuẩn.

## 1. Vì sao cần một định dạng lỗi chung?

Không có hợp đồng chung, mỗi endpoint có thể trả một dạng khác nhau:

~~~json
{"message":"bad input"}
~~~

~~~json
{"status":"ERROR","errorCode":12,"errors":["quantity"]}
~~~

~~~text
Order missing
~~~

Client phải viết nhiều bộ parser cho cùng một loại lỗi. RFC 9457 đề xuất một cấu trúc chuẩn, thường được biểu diễn bằng media type `application/problem+json`:

~~~json
{
  "type": "https://example.org/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order does not exist.",
  "instance": "/api/orders/999",
  "code": "ORDER_NOT_FOUND"
}
~~~

Năm thành viên đầu là thành viên chuẩn; `code` là trường mở rộng của ứng dụng. Spring có thể serialize đối tượng `ProblemDetail` thành JSON này khi Jackson có mặt.

**Phân biệt HTTP status với JSON `status`:** response thực phải là HTTP **404**, trong khi trường `"status":404` chỉ diễn đạt lại trạng thái để body có ý nghĩa khi được lưu hoặc xem tách khỏi HTTP exchange. Không được chủ đích trả HTTP 200 với body `"status":404`. RFC 9457 dự định status bên trong phù hợp với HTTP status thực tế do server tạo.

### 1.1. Năm thành viên chuẩn

| Thành viên | Mục đích | Lưu ý |
| --- | --- | --- |
| `type` | URI xác định **loại** lỗi, tương đối ổn định | Không phải URL bắt buộc truy cập được, nhưng nên dẫn tới tài liệu nếu dùng HTTPS |
| `title` | Tiêu đề ngắn mô tả loại lỗi | Nên ổn định cho cùng một type |
| `status` | Mã trạng thái HTTP dạng số | Phải nhất quán với response thực |
| `detail` | Giải thích sự cố **cụ thể ở lần xảy ra** | Có thể địa phương hóa, không chứa stack trace hoặc bí mật |
| `instance` | URI xác định lần/scope xảy ra lỗi, thường là request path | Không nhất thiết có đủ domain, không nên chứa token trong query |

`type` mặc định có thể là `about:blank`, nghĩa là chưa định nghĩa một loại lỗi chuyên biệt. `title` mặc định thường theo HTTP status phrase khi có thể. `instance` có thể được Spring điền từ request path nếu chưa gán và response được render qua các đường framework hỗ trợ.

### 1.2. Extension properties

Chuẩn cho phép thêm các thuộc tính như:

~~~json
{
  "type": "https://example.org/problems/invalid-request",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/orders",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerName", "code": "NotBlank"},
    {"field": "quantity", "code": "Min"}
  ]
}
~~~

`errors` **không phải một trường bắt buộc của RFC 9457**: đây là hợp đồng riêng do API tạo. Khi khai báo extension, hãy định nghĩa rõ tên, kiểu JSON, thứ tự nếu có ý nghĩa, và chính sách versioning. Tránh trùng tên với các thành viên chuẩn. Danh sách field errors nên có giá trị máy có thể xử lý (`field`, `code`) và, nếu cần, một message đã bản địa hóa.

**Không tự động đưa `rejectedValue` của `FieldError` vào payload**, vì có thể chứa mật khẩu, access token, địa chỉ cá nhân hoặc nội dung chưa escape.

## 2. Ma trận hỗ trợ theo phiên bản

Cần phân biệt **Spring Framework** (nơi định nghĩa API) với **Spring Boot** (cung cấp auto-configuration và dependency management). Các mốc quan trọng:

| Dòng công nghệ | Khả năng | Cách áp dụng |
| --- | --- | --- |
| Spring Framework 5.3 / Boot 2.x | Chưa có `org.springframework.http.ProblemDetail` và `org.springframework.web.ErrorResponse` chuẩn của Spring 6 | Dùng `@ExceptionHandler` + DTO lỗi riêng + `ResponseEntity` |
| Spring Framework 6.0 / Boot 3.0+ | Có `ProblemDetail`, `ErrorResponse`, `ErrorResponseException` và `ResponseEntityExceptionHandler` hỗ trợ Problem Details | Có thể tự trả `ProblemDetail` từ advice/handler |
| Spring Framework 6.1 / Boot 3.2+ | Native **controller method validation** và `HandlerMethodValidationException`; nhiều API hoàn thiện hơn | Xử lý riêng validation ở cấp method khi cần |
| Spring Framework 6.2 / Boot 3.4, 3.5 | Có `ErrorResponse.Interceptor` và hook cấu hình như `WebMvcConfigurer.addErrorResponseInterceptors(...)` | Có thể bổ sung dữ liệu/chính sách chung khi render ProblemDetail |
| Spring Framework 7.x / Boot 4.x | Tiếp tục hỗ trợ các abstractions, có thể mở rộng cấu hình và thay đổi signature/API tùy minor | Kiểm tra tài liệu/Javadoc **đúng dòng** trước khi migrate |

Dòng bảng là định hướng về **mốc feature** chứ không bảo đảm mọi tổ hợp version đều tương thích. Ví dụ Spring Boot 3.5.x thông thường quản lý Spring Framework 6.2.x. Không ép riêng một version Spring Framework khác với dependency BOM của Boot nếu chưa kiểm tra tương thích.

**RFC 7807 so với RFC 9457:** Spring Framework 6.0 ra đời khi nhiều tài liệu còn gọi Problem Details là RFC 7807. RFC 9457 về sau thay thế, làm rõ và phát triển chuẩn. Class `ProblemDetail` của Spring 6.x vẫn là class tương ứng; không có một class Java mới bắt buộc mang tên `Rfc9457ProblemDetail`. Khi thấy tài liệu cũ nhắc RFC 7807, hãy so phiên bản trước khi kết luận code đã lỗi thời.

### 2.1. Quy tắc kiểm tra khả năng thay vì đoán từ tên API

Trước khi dùng code mẫu, kiểm tra:

~~~bash
mvn dependency:tree
~~~

hoặc xem Spring Framework version trong Spring Boot BOM/Gradle dependency report. Tra Javadoc đúng version:

~~~text
org.springframework.http.ProblemDetail
org.springframework.web.ErrorResponse
org.springframework.web.ErrorResponseException
org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler
org.springframework.web.method.annotation.HandlerMethodValidationException
org.springframework.web.servlet.config.annotation.WebMvcConfigurer
~~~

Một method có thể hiện diện trong Javadoc của Spring 7 hoặc 6.2 nhưng **không tồn tại trong 6.0**. Compiler error kiểu “cannot find symbol” khi sao chép hook mới không có nghĩa import sai: có thể chỉ là feature chưa xuất hiện trong dependency version hiện tại.

## 3. ProblemDetail: tạo body lỗi

`ProblemDetail` thuộc package:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
~~~

Cách tạo thông dụng:

~~~java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "The requested order does not exist.");

problem.setType(URI.create(
        "https://example.org/problems/order-not-found"));
problem.setTitle("Order not found");
problem.setInstance(URI.create("/api/orders/999"));
problem.setProperty("code", "ORDER_NOT_FOUND");
~~~

Đây là **snippet** cần import `java.net.URI`, chưa phải chương trình độc lập. `forStatus(HttpStatus.BAD_REQUEST)` cũng tồn tại khi không cần gán `detail` ngay. Trên Spring 6.x, `ProblemDetail` có các setters cho những thành viên chuẩn và extension properties.

### 3.1. Nên dùng type như thế nào?

Một convention tốt là dùng URI ổn định:

~~~text
https://example.org/problems/validation-failed
https://example.org/problems/order-not-found
https://example.org/problems/order-conflict
~~~

Đừng tạo type theo nội dung chi tiết mỗi request, chẳng hạn `/problems/order-999-missing`; type mô tả **loại**, còn `instance` mô tả **lần xảy ra**. Client có thể dựa trên `type` hoặc extension `code` để phân nhánh logic. Nếu dùng URL như type, nên công bố giải thích loại lỗi, cách xử lý và versioning.

### 3.2. getProperties và Jackson

`ProblemDetail.setProperty("code", "ORDER_NOT_FOUND")` thêm extension vào properties map. Với Jackson được Spring tích hợp, extension map được **unwrap thành các trường JSON cùng cấp** với type/title/status/detail/instance. Một số serializer khác có thể giữ chúng dưới key `properties`; vì vậy hãy kiểm thử JSON thực và không giả định mọi framework ngoài Spring/Jackson đều giống nhau.

`ProblemDetail` cũng hỗ trợ subclass để có các thuộc tính bổ sung có kiểu cụ thể, thông qua copy constructor. Cách này hữu ích nếu SDK/OpenAPI client cần một schema có extension được mô hình hóa chặt chẽ. Với một vài key như `code` và `errors`, `setProperty(...)` thường đủ.

## 4. ErrorResponse không chỉ là JSON body

`org.springframework.web.ErrorResponse` là **interface**, không phải JSON bean thay thế `ProblemDetail`. Nó đại diện một phản hồi lỗi đầy đủ:

~~~text
ErrorResponse
  |
  +-- getStatusCode()    → HTTP 400/404/409...
  +-- getHeaders()       → headers cần gửi
  +-- getBody()          → ProblemDetail
  +-- message codes      → tùy biến type/title/detail qua MessageSource
~~~

Nhiều exception của Spring MVC/WebFlux hiện thực `ErrorResponse`, gồm `MethodArgumentNotValidException` và `HandlerMethodValidationException` ở những phiên bản hỗ trợ. Nhờ vậy framework có thể xử lý nhất quán status, headers và body.

### 4.1. ErrorResponseException

`org.springframework.web.ErrorResponseException` là một RuntimeException đã implement `ErrorResponse`. Nó hữu ích khi muốn **ném một lỗi có HTTP status và body xác định**, thay vì xây dựng một exception hoàn toàn tùy ý.

~~~java
ProblemDetail body = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Order cannot be modified in its current state.");

body.setType(URI.create(
        "https://example.org/problems/order-conflict"));
body.setProperty("code", "ORDER_CONFLICT");

throw new ErrorResponseException(
        HttpStatus.CONFLICT, body, null);
~~~

Snippet cần import `ErrorResponseException`, `HttpStatus`, `ProblemDetail`, `URI`. Constructor dùng `HttpStatusCode status`, `ProblemDetail body` và optional `Throwable cause` xuất hiện từ Spring 6.0. Khi handler thích hợp có mặt, exception có thể được render với body ProblemDetail. Với những exception thuộc domain, một `@ExceptionHandler` riêng vẫn phù hợp nếu muốn tách domain model khỏi Spring HTTP classes.

### 4.2. Builder và i18n

Spring có `ErrorResponse.builder(...)` / `ErrorResponse.create(...)` trong các phiên bản hỗ trợ; builder giúp khai báo status, detail và các message codes. Một `ErrorResponse` cung cấp mã để tra `type`, `title` và `detail` qua `MessageSource`. Điều này khác với `ProblemDetail` thuần, vốn chỉ giữ nội dung và không tự mang rule phân giải message codes của exception.

Một số API đáng chú ý:

~~~java
HttpStatusCode status = errorResponse.getStatusCode();
HttpHeaders headers = errorResponse.getHeaders();
ProblemDetail body = errorResponse.getBody();
~~~

Đây là snippet khi biến `errorResponse` đã có. Trong hệ thống xử lý lỗi, **không** mặc định sửa một object `ProblemDetail` static dùng chung giữa nhiều requests: nội dung như `instance`, message theo locale và trace metadata thuộc từng lần lỗi, có thể dẫn đến rò rỉ qua request khác nếu tái sử dụng mutable instance.

## 5. Render qua @ExceptionHandler và ResponseEntityExceptionHandler

Trong Spring MVC annotated controllers, có nhiều cách dùng Problem Details:

1. Trả trực tiếp `ProblemDetail` từ `@ExceptionHandler`.
2. Trả `ResponseEntity<ProblemDetail>` để kiểm soát status/headers.
3. Ném một `ErrorResponseException` để framework/advice xử lý.
4. Kế thừa `ResponseEntityExceptionHandler` trong `@ControllerAdvice`/`@RestControllerAdvice` để xử lý tập exception có sẵn, rồi override những protected methods cần tùy biến.

### 5.1. @ExceptionHandler trả ProblemDetail

~~~java
@RestControllerAdvice
class DomainErrors {

    @ExceptionHandler(OrderMissingException.class)
    ProblemDetail notFound(OrderMissingException ex) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Requested order does not exist.");

        p.setTitle("Order not found");
        p.setType(URI.create(
                "https://example.org/problems/order-not-found"));
        return p;
    }
}
~~~

Đây là **snippet**, giả định `OrderMissingException` do ứng dụng định nghĩa. Spring MVC hiểu `status` của ProblemDetail và ưu tiên media type Problem Details như `application/problem+json` trong quá trình content negotiation; với response qua cơ chế framework, `instance` có thể được điền từ request path nếu không đặt.

Nếu muốn gửi header như `Retry-After` hoặc `WWW-Authenticate`, có thể cần `ResponseEntity` hoặc một `ErrorResponse` có headers phù hợp; đừng chỉ đặt mọi metadata vào JSON body.

### 5.2. ResponseEntityExceptionHandler giải quyết điều gì?

Một `@RestControllerAdvice extends ResponseEntityExceptionHandler` thừa hưởng logic xử lý nhiều exception do Spring MVC phát sinh (JSON không đọc được, media type sai, `MethodArgumentNotValidException`, thiếu tham số v.v.). Base class có `@ExceptionHandler` phù hợp và các protected hooks để thay đổi response mà **không tự copy cả bộ xử lý exception của framework**.

Ví dụ override cho validation lỗi:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    ProblemDetail body = ex.getBody();
    body.setTitle("Validation failed");
    body.setDetail("One or more fields are invalid.");
    return handleExceptionInternal(
            ex, body, headers, status, request);
}
~~~

Đây là snippet bên trong subclass phù hợp và cần imports. `handleMethodArgumentNotValid` có signature như trên ở Spring 6.0–6.2. Không tự khai báo lại `@ExceptionHandler(MethodArgumentNotValidException.class)` trên cùng advice kế thừa class này: có thể tạo mapping exception handler trùng với method thừa kế.

### 5.3. Một lỗi HTTP không phải lúc nào cũng là validation error

| Tình huống | Exception thường gặp | Ý nghĩa |
| --- | --- | --- |
| `@Valid @RequestBody DTO` có constraint sai | `MethodArgumentNotValidException` | Input bean không hợp lệ |
| JSON không parse được | `HttpMessageNotReadableException` | Decode HTTP body thất bại trước validation |
| `@RequestParam @Min(1) int count` vi phạm (Spring 6.1+) | `HandlerMethodValidationException` | Native controller method validation |
| URL được mapping nhưng method không hỗ trợ | `HttpRequestMethodNotSupportedException` | HTTP 405 |
| Content-Type không được chấp nhận | `HttpMediaTypeNotSupportedException` | HTTP 415 |
| Domain không tìm được entity | Custom `OrderMissingException` | App tự map thành 404 |
| Bug bất ngờ | `NullPointerException` hoặc exception nội bộ | Thường HTTP 500, không được giả thành lỗi input |

**Lưu ý về method validation:** `@Valid` chỉ đánh dấu validation/cascade của bean; direct constraint như `@Min` trên method parameter có thể kích hoạt native method validation ở Spring Framework 6.1+. Lỗi input method thường ánh xạ 400, còn vi phạm ràng buộc return value là lỗi phía server và có thể ánh xạ 500. Không đánh đồng cả hai.

## 6. Spring Boot tự bật Problem Details hay phải cấu hình?

Trong Spring Boot 3.x, property quan trọng:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Khi bật, Boot có thể tự cấu hình `ResponseEntityExceptionHandler` cho các exception web phổ biến để render Problem Details. Nếu không bật, đừng tự động cho rằng mọi Spring exception trong ứng dụng sẽ trả RFC 9457; phản hồi mặc định có thể do `BasicErrorController` hoặc exception resolvers xử lý theo cấu hình.

Với WebFlux:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Đây là **property cho reactive stack**, không thay thế property MVC. Hãy chọn đúng theo starter và loại ứng dụng.

### Hai chiến lược thay thế nhau

**Chiến lược A — dùng Boot auto-configuration:** bật `spring.mvc.problemdetails.enabled=true`, rồi thêm advice có thứ tự ưu tiên cao hơn nếu muốn override riêng một loại exception. Advice auto-configured của Boot có order cụ thể, thường là 0 trong tài liệu; kiểm tra chính xác phiên bản trước khi dựa vào thứ tự.

**Chiến lược B — advice tự quản lý:** không bật Boot auto Problem Details, viết một `@RestControllerAdvice extends ResponseEntityExceptionHandler`, override các protected handler cần thiết, tự xử lý domain exceptions. Ví dụ chạy được ở mục 9 chọn chiến lược B.

**Không** kết hợp tùy tiện cả hai rồi hy vọng framework tự chọn handler bạn mong muốn. Hai advice cùng có mapping cho built-in exceptions có thể cạnh tranh theo order và phạm vi. Viết MockMvc tests cho từng exception quan trọng; tránh bắt catch-all `Exception.class` trong một advice có precedence cao nếu nó sẽ nuốt mapping 400/404 đã có.

## 7. Field errors: mở rộng có kiểm soát

RFC 9457 không quy định một schema duy nhất cho lỗi nhiều trường. Một API có thể đưa danh sách đã chuẩn hóa vào `errors`:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "errors": [
    {"field": "customerName", "code": "NotBlank"},
    {"field": "quantity", "code": "Min"}
  ]
}
~~~

Nguồn lỗi Spring MVC:

~~~java
List<FieldError> fields =
        ex.getBindingResult().getFieldErrors();

for (FieldError error : fields) {
    String name = error.getField();
    String code = error.getCode();
    String message = error.getDefaultMessage();
    boolean conversionFailure = error.isBindingFailure();
}
~~~

Đây là snippet khi `ex` là `MethodArgumentNotValidException`, cần import `FieldError`. `getCode()` có thể là `NotBlank`, `Min`, `typeMismatch` hoặc code khác do validator/custom resolver tạo. Nên giữ `code` cho logic máy; `message` có thể dịch theo request locale.

**Không** nên đưa:

~~~java
error.getRejectedValue()
~~~

vào JSON chỉ vì đã có accessor. Trường bị từ chối có thể là mật khẩu/token, thông tin y tế hoặc dữ liệu người dùng chưa được kiểm soát; còn exception messages có thể lộ tên class hoặc query database.

### 7.1. Tính ổn định của errors array

Tập constraint violations của Jakarta Validation không bảo đảm thứ tự phù hợp UX. Nếu contract JSON cần thứ tự ổn định, hãy sort theo `field` rồi `code`, hoặc dùng thứ tự field được định nghĩa bởi sản phẩm. Cũng có thể có nhiều vi phạm trên cùng một field. Không tự động map thành `Map<String,String>` làm mất các lỗi khác nếu nghiệp vụ muốn hiển thị đầy đủ.

### 7.2. Binding khác Bean Validation

`quantity=abc` trong HTML form với `Integer quantity` là **lỗi type conversion** (`typeMismatch`), còn `quantity=0` là **lỗi @Min` sau khi convert thành công. Với JSON, body `{"quantity":"abc"}` có thể thất bại ngay ở Jackson deserialization và gây `HttpMessageNotReadableException`, thay vì `MethodArgumentNotValidException`. Không đảm bảo mọi input lỗi đều có `FieldError`; error response layer phải nhận diện giai đoạn lỗi.

## 8. Quốc tế hóa type/title/detail

Các exception `ErrorResponse` expose message codes để `ResponseEntityExceptionHandler` và `MessageSource` có thể tra:

~~~text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.<fully-qualified-exception-class>
~~~

Ví dụ cho `MethodArgumentNotValidException`:

~~~properties
problemDetail.title.org.springframework.web.bind.MethodArgumentNotValidException=Invalid request
problemDetail.org.springframework.web.bind.MethodArgumentNotValidException=Request validation failed
~~~

Đây là ví dụ Spring 6.x; chính xác default codes và detail arguments còn tùy exception/version. Với một `FieldError`, Spring có các mã như `NotBlank.createOrderCommand.customerName` và `NotBlank.customerName`, khác với nhóm codes của `ErrorResponse`.

Tài liệu Spring nêu rằng `ErrorResponse` hỗ trợ default message codes cho **type, title, detail**, và detail arguments có thể được resolve qua MessageSource. `ResponseEntityExceptionHandler` xử lý localization trước khi render. Nếu code tự đặt `title/detail` trong một `ProblemDetail` và không dùng ErrorResponse resolution, bạn cần gọi `MessageSource` trực tiếp như ví dụ mục 9.

**Chọn policy rõ ràng:**

- `type`: URI ổn định, không đổi theo locale.
- `code`: identifier ổn định cho client, không đổi theo locale.
- `title`: có thể dịch nhưng giữ ý nghĩa nhất quán.
- `detail`: thông điệp có thể dịch theo `Accept-Language`, không chứa bí mật.
- `errors[].code`: giữ ổn định; `errors[].message` nếu có thì dịch.

## 9. Demo runnable: Spring Boot 3.5.7 / Spring MVC / Java 17+

Ta tạo một API có ba hành vi:

1. `POST /api/orders` nhận JSON qua `@Valid @RequestBody`; thành công trả 201, sai field trả ProblemDetail 400 với `errors`.
2. `GET /api/orders/{id}`: `id=1` trả dữ liệu, ID khác báo 404 với type và code rõ ràng.
3. `GET /api/orders/limits?count=...`: direct `@Min(1)` kiểm tra native method validation Spring 6.1+, nếu sai trả 400 do base `ResponseEntityExceptionHandler` xử lý.

Ví dụ chọn **manual `@RestControllerAdvice extends ResponseEntityExceptionHandler`**, không bật Boot auto-advice, để việc điều chỉnh các lỗi được mô tả rõ. Không có database hoặc Spring Security trong demo; ngoài production cần bổ sung authorization và không dùng ID đơn giản để kiểm soát truy cập.

### 9.1. Cấu trúc thư mục

~~~text
problem-details-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/problems/
    │   │   ├── Application.java
    │   │   ├── CreateOrderCommand.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderMissingException.java
    │   │   ├── OrderController.java
    │   │   └── ApiErrorAdvice.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       └── messages_vi.properties
    └── test/
        └── java/com/example/problems/
            └── OrderApiTest.java
~~~

### 9.2. pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>problem-details-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`spring-boot-starter-web` cung cấp Spring MVC + Jackson, `spring-boot-starter-validation` cung cấp Jakarta Bean Validation, test starter cung cấp MockMvc/JUnit. Không cần dependency riêng cho `ProblemDetail` vì nó thuộc Spring Framework 6.x. Spring Boot parent quản lý dependency versions; trong production nên dùng bản vá được tổ chức duy trì.

### 9.3. Application.java

~~~java
package com.example.problems;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 9.4. CreateOrderCommand.java

~~~java
package com.example.problems;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderCommand(
        @NotBlank String customerName,
        @NotNull @Min(1) Integer quantity) {
}
~~~

`@NotBlank` kiểm tra tên không rỗng/whitespace; `@NotNull` yêu cầu có quantity; `@Min(1)` yêu cầu số dương. Sử dụng `Integer` để biểu đạt null khi field thiếu. Record thích hợp cho DTO immutable của JSON API. Validation annotations này thuộc `jakarta.validation`, không dùng package `javax.validation` của Spring Boot 2.

### 9.5. OrderReceipt.java

~~~java
package com.example.problems;

public record OrderReceipt(
        String result,
        String customerName,
        Integer quantity) {
}
~~~

Đây là DTO demo để xác minh response 200/201 và không có database.

### 9.6. OrderMissingException.java

~~~java
package com.example.problems;

public final class OrderMissingException
        extends RuntimeException {
}
~~~

Ví dụ cố tình không mang input raw vào exception. Ứng dụng thật có thể lưu internal diagnostic metadata riêng; không nên xuất trực tiếp message nội bộ cho client.

### 9.7. OrderController.java

~~~java
package com.example.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderCommand command) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new OrderReceipt(
                        "created",
                        command.customerName(),
                        command.quantity()));
    }

    @GetMapping("/{id}")
    public OrderReceipt find(@PathVariable long id) {
        if (id != 1L) {
            throw new OrderMissingException();
        }
        return new OrderReceipt("found", "Lan", 2);
    }

    @GetMapping("/limits")
    public String limits(
            @RequestParam @Min(1) int count) {
        return "limit:" + count;
    }
}
~~~

**Lưu ý:** Không gắn `@Validated` ở cấp class controller nếu muốn đi theo cơ chế native controller method validation của Spring 6.1+. `@Min(1)` trên `count` là constraint trực tiếp nên có thể phát `HandlerMethodValidationException`; `@Valid` trên JSON DTO dùng đường argument validation thông thường.

### 9.8. ApiErrorAdvice.java

~~~java
package com.example.problems;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.MessageSource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.context.request.WebRequest;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    private final MessageSource messages;

    public ApiErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    public record FieldIssue(String field, String code) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<FieldIssue> issues = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(error.getCode(), "invalid")))
                .sorted(Comparator.comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        ProblemDetail body = ex.getBody();
        body.setType(URI.create(
                "https://example.org/problems/validation"));
        body.setTitle("Validation failed");
        body.setDetail("One or more fields are invalid.");
        body.setProperty("code", "VALIDATION_FAILED");
        body.setProperty("errors", issues);

        return handleExceptionInternal(
                ex, body, headers, status, request);
    }

    @ExceptionHandler(OrderMissingException.class)
    public ProblemDetail orderMissing(
            OrderMissingException ex,
            HttpServletRequest request,
            Locale locale) {

        String detail = messages.getMessage(
                "problem.orderMissing", null, locale);

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, detail);

        body.setType(URI.create(
                "https://example.org/problems/order-not-found"));
        body.setTitle("Order not found");
        body.setInstance(URI.create(request.getRequestURI()));
        body.setProperty("code", "ORDER_NOT_FOUND");
        return body;
    }
}
~~~

Phân tích kỹ:

- `ApiErrorAdvice` kế thừa `ResponseEntityExceptionHandler`; không tạo một `@ExceptionHandler(MethodArgumentNotValidException.class)` thứ hai vì base class đã có.
- Override `handleMethodArgumentNotValid(...)` theo đúng chữ ký Spring 6.2: đối số thứ ba là `HttpStatusCode` và cuối là `WebRequest`.
- `ex.getBody()` trả một `ProblemDetail` gắn với exception; ta sửa body **của lần lỗi hiện tại**, không dùng đối tượng static mutable.
- `FieldIssue` chỉ có `field` và `code`. Không echo `getRejectedValue()`, không gửi exception stack trace hoặc target object.
- Danh sách errors được sort để test/contract ổn định. Nếu có nhiều lỗi cùng field, mỗi lỗi có thể tạo một entry.
- `handleExceptionInternal(...)` giữ status và headers do framework chọn; không hardcode 400 mà bỏ qua trạng thái/headers từ exception.
- `orderMissing(...)` dùng `MessageSource` và Locale để dịch `detail` cho một domain exception; `type`/`code` giữ ổn định.
- `instance` gắn request path chứ không chứa query/token; HTTP status được lấy từ `ProblemDetail.status` là 404.
- Với các built-in exceptions khác như JSON malformed và method validation, logic thừa kế của `ResponseEntityExceptionHandler` tạo Problem Details phù hợp, không phải mọi exception được gom thành `VALIDATION_FAILED`.

URI `https://example.org/problems/...` trong demo là namespace minh họa; dự án thật thay bằng domain tài liệu API được kiểm soát, không sử dụng ví dụ như tài liệu production.

### 9.9. application.properties

~~~properties
server.port=8080
spring.mvc.problemdetails.enabled=false
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Tại sao chủ động đặt `spring.mvc.problemdetails.enabled=false`? Ví dụ đã có advice kế thừa `ResponseEntityExceptionHandler`, nên không cần Boot tạo một advice built-in khác cạnh tranh. **Tắt Boot auto-advice không tắt class `ProblemDetail` hoặc logic custom advice.** Nếu chọn chiến lược Boot auto-advice, hãy bật property và cân nhắc khác biệt về thứ tự advice.

### 9.10. messages.properties

~~~properties
problem.orderMissing=Requested order does not exist.
~~~

### 9.11. messages_vi.properties

~~~properties
problem.orderMissing=Đơn hàng không tồn tại.
~~~

Đây là Spring MessageSource bundles, được dùng trong `orderMissing(...)`. Locale do Spring MVC resolve từ header. Không cần để raw messages trong exception hoặc controller. Spring Boot nhận diện message source nhờ file gốc `messages.properties`.

### 9.12. Chạy bằng Maven

~~~bash
mvn spring-boot:run
~~~

Thành công:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerName":"Lan","quantity":2}'
~~~

Status mong đợi **201 Created**, JSON body:

~~~json
{
  "result": "created",
  "customerName": "Lan",
  "quantity": 2
}
~~~

Sai ràng buộc:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerName":"","quantity":2}'
~~~

Status mong đợi **400 Bad Request**, media type tương thích `application/problem+json`, body có các trường ít nhất:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerName", "code": "NotBlank"}
  ]
}
~~~

Spring có thể bổ sung `instance` theo request path. Đừng viết test so khớp toàn bộ JSON nếu một trường mặc định có thể thay đổi theo framework version; hãy assert các thành viên contract do ứng dụng định nghĩa.

Domain 404:

~~~bash
curl -i -H "Accept-Language: vi" \
  "http://localhost:8080/api/orders/999"
~~~

Body chính:

~~~json
{
  "type": "https://example.org/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Đơn hàng không tồn tại.",
  "instance": "/api/orders/999",
  "code": "ORDER_NOT_FOUND"
}
~~~

Đối với JSON bị hỏng cú pháp, ví dụ `{"quantity":`, response dự kiến là HTTP 400 do `HttpMessageNotReadableException`; body mặc định có thể khác giữa các Spring minor versions. `ResponseEntityExceptionHandler` tạo phản hồi lỗi phù hợp, nhưng code của demo không khẳng định nội dung error message cố định.

## 10. MockMvc: xác minh HTTP status và contract JSON

File `src/test/java/com/example/problems/OrderApiTest.java`:

~~~java
package com.example.problems;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validJsonCreatesOrder() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerName":"Lan","quantity":2}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result").value("created"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void invalidBeanReturnsProblemDetails() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerName":"","quantity":2}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.title").value(
                        "Validation failed"))
                .andExpect(jsonPath("$.code").value(
                        "VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors[0].field").value(
                        "customerName"))
                .andExpect(jsonPath("$.errors[0].code").value(
                        "NotBlank"));
    }

    @Test
    void missingQuantityAlsoProducesFieldError()
            throws Exception {

        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerName":"Lan"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value(
                        "quantity"))
                .andExpect(jsonPath("$.errors[0].code").value(
                        "NotNull"));
    }

    @Test
    void domainNotFoundUsesEnglishMessage()
            throws Exception {

        mvc.perform(get("/api/orders/999")
                        .header("Accept-Language", "en"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.code").value(
                        "ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.detail").value(
                        "Requested order does not exist."))
                .andExpect(jsonPath("$.instance").value(
                        "/api/orders/999"));
    }

    @Test
    void domainNotFoundUsesVietnameseMessage()
            throws Exception {

        mvc.perform(get("/api/orders/999")
                        .header("Accept-Language", "vi"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value(
                        "Đơn hàng không tồn tại."));
    }

    @Test
    void existingOrderSucceeds() throws Exception {
        mvc.perform(get("/api/orders/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("found"));
    }

    @Test
    void malformedJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void nativeMethodValidationRejectsCount()
            throws Exception {

        mvc.perform(get("/api/orders/limits")
                        .param("count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void nativeMethodValidationAcceptsCount()
            throws Exception {

        mvc.perform(get("/api/orders/limits")
                        .param("count", "3"))
                .andExpect(status().isOk())
                .andExpect(content().string("limit:3"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Chín tests** kiểm tra: thành công 201, lỗi `NotBlank` 400 với extension, thiếu quantity tạo `NotNull`, domain 404 bằng tiếng Anh/Việt, đơn hàng hợp lệ 200, JSON hỏng 400, native method validation sai/đúng. Test quan trọng là **assert HTTP status thật, media type và các trường contract**; không chỉ so field `status` nằm trong JSON.

Một số tests phụ thuộc vào behavior của Spring 6.2 (ví dụ `HandlerMethodValidationException`), nên không copy nguyên bộ sang Spring 5.x rồi kỳ vọng compile. Các files được thiết kế cho Spring Boot 3.5.7 với Java 17+; chưa thực thi lệnh Maven trong môi trường của bài học.

## 11. ErrorResponse.Interceptor: chỉ dùng khi phiên bản hỗ trợ

Từ Spring Framework **6.2**, interface `ErrorResponse.Interceptor` cho phép can thiệp trước khi một ProblemDetail error response được render. Với Spring MVC, `WebMvcConfigurer` có hook `addErrorResponseInterceptors(...)`.

Ví dụ **tùy chọn**:

~~~java
@Configuration
class ProblemMetadataConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addErrorResponseInterceptors(
            List<ErrorResponse.Interceptor> interceptors) {

        interceptors.add((detail, errorResponse) -> {
            detail.setProperty("service", "orders-api");
        });
    }
}
~~~

Snippet cần imports `@Configuration`, `WebMvcConfigurer`, `List` và `ErrorResponse`. Nó **không phải** file bắt buộc của demo và không được dùng với Spring 6.0/6.1 nếu không tồn tại interface/hook đó.

Ứng dụng có thể thêm metadata như service code hoặc một correlation ID đã được kiểm soát. Interceptor **không tự có HttpServletRequest trong chữ ký**, vì vậy đừng giả định có thể lấy header hay current user trực tiếp từ tham số; nếu phải dùng request context, hãy thiết kế cách truyền an toàn theo stack và kiểm thử riêng.

Một interceptor không thay thế `@ExceptionHandler` để chọn HTTP status hoặc mapping exception; mục đích chính là bổ sung/điều chỉnh ProblemDetail trước rendering.

## 12. Khác biệt giữa MVC và WebFlux

Spring MVC và Spring WebFlux đều có `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler`, nhưng **không dùng cùng import của lớp exception handler**.

| Vấn đề | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| HTTP stack | Servlet | Reactive WebFlux |
| Base advice class | `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` | `org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler` |
| Validation của bean request | Thường `MethodArgumentNotValidException` | Thường `WebExchangeBindException` |
| Native handler method validation | `HandlerMethodValidationException` (Spring 6.1+) | `HandlerMethodValidationException` (Spring 6.1+) |
| Boot switch | `spring.mvc.problemdetails.enabled` | `spring.webflux.problemdetails.enabled` |
| Request context | `WebRequest`/`HttpServletRequest` | `ServerWebExchange` |
| Testing | `MockMvc` | `WebTestClient` |

Ví dụ ý tưởng trong WebFlux:

~~~java
@RestControllerAdvice
class ReactiveErrors
        extends org.springframework.web.reactive.result
                .method.annotation.ResponseEntityExceptionHandler {

    // Override protected handlers với ServerWebExchange
    // theo Javadoc của Spring WebFlux version đang dùng.
}
~~~

Đây là **snippet kiến trúc**, không phải file chạy độc lập và không đủ imports. Khi code thực sự, hãy giữ fully qualified class name trên một dòng trong Java hoặc import lớp chính xác; snippet xuống dòng FQN ở trên chỉ để đọc trong tài liệu. Tránh chép chữ ký Servlet MVC `WebRequest` sang WebFlux rồi cố ép compile.

Trong WebFlux, response streaming có thể đã gửi headers/body khi phát sinh lỗi muộn. Khi HTTP response đã committed, không thể dễ dàng đổi status thành 400/500 và gửi một ProblemDetail hoàn chỉnh. Nếu API yêu cầu toàn bộ batch hợp lệ trước khi trả, có thể cần validate/buffer trước khi stream hoặc dùng giao thức thông báo lỗi trên từng event.

## 13. Tương thích Spring 5.x: không dùng API chưa tồn tại

Với Spring Framework 5.3 / Boot 2.x, `ProblemDetail` và `ErrorResponse` của Spring 6 chưa có. **Không import những class đó bằng cách đổi package hoặc chép trực tiếp mã Spring 6.**

Một lựa chọn tương thích là DTO riêng và `ResponseEntity`:

~~~java
public record ApiError(
        int status,
        String code,
        String message) {
}

@RestControllerAdvice
class LegacyErrors {

    @ExceptionHandler(OrderMissingException.class)
    ResponseEntity<ApiError> notFound(
            OrderMissingException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        404,
                        "ORDER_NOT_FOUND",
                        "Requested order does not exist."));
    }
}
~~~

Đây là snippet có các imports Spring MVC/JDK liên quan và exception class do ứng dụng định nghĩa. Với Java 17, `record` có thể dùng trong một project Spring 5.3 phù hợp; nếu dự án còn dùng Java 8/11, thay bằng Java class thường có fields/getters/constructor. Phần quan trọng là **hợp đồng JSON của riêng bạn có thể mô phỏng RFC 9457** dù chưa có class `ProblemDetail`.

Khi nâng cấp lên Spring 6, cân nhắc:

1. Đổi namespace `javax.validation` → `jakarta.validation` và các Jakarta APIs có liên quan.
2. Giữ nguyên error codes ổn định mà client đang dựa vào.
3. Thống nhất response statuses/type/instance; không buộc client thay parser một cách âm thầm.
4. Di chuyển về `ProblemDetail`/`ErrorResponse` khi thực sự có giá trị.
5. Test lại `Content-Type`, exception precedence và `MessageSource`.

## 14. Security và contract của phản hồi lỗi

ProblemDetail làm format nhất quán, **không tự biến mọi error response thành an toàn**.

### 14.1. Tránh lộ internals

Không phản hồi:

- Stack trace đầy đủ, JVM package/class names, database SQL hoặc JDBC URL.
- `Exception.getMessage()` không kiểm soát từ thư viện ngoài.
- `FieldError.getRejectedValue()` cho password/token/OTP/thông tin nhạy cảm.
- Authentication secrets, internal hostnames, connection strings, API keys.
- Query string trong `instance` nếu nó chứa token trên URL.

Nếu cần debug, trả một correlation ID an toàn cho client và ghi chi tiết trong logs/observability nội bộ. Không biến mọi `Exception.class` thành HTTP 400 chỉ vì client sẽ “dễ parse” hơn; phải bảo đảm 4xx và 5xx phản ánh đúng nguồn lỗi.

### 14.2. Đặt status theo loại lỗi

| Loại lỗi | HTTP status thường dùng | Ghi chú |
| --- | --- | --- |
| JSON syntax / invalid payload | 400 | Đọc input thất bại |
| Bean Validation / thiếu tham số | 400 | Theo mapping/framework, hoặc 422 khi contract có chủ đích |
| Không xác thực | 401 | Kèm headers cần thiết, ví dụ WWW-Authenticate khi phù hợp |
| Không được phép | 403 | Không lộ tài nguyên người dùng không được phép xem |
| Không tìm thấy | 404 | Có thể che tài nguyên để tránh enumeration theo security policy |
| Xung đột trạng thái | 409 | Domain conflict, optimistic locking tùy thiết kế |
| Payload quá lớn | 413 | Giới hạn upload/body |
| Lỗi server | 500 | Không leak exception nội bộ |

Không có quy tắc RFC bắt buộc mọi Bean Validation error là 422. `MethodArgumentNotValidException` mặc định thường ánh xạ HTTP 400; nếu muốn 422, phải chọn chính sách rõ, không sửa cả header và body thiếu nhất quán.

### 14.3. OpenAPI/SDK clients

Để client xử lý tốt:

- Công bố media type `application/problem+json` cho lỗi của từng endpoint, hoặc mô tả dùng chung trong OpenAPI.
- Định nghĩa schema cho các extension `code`/`errors`; không coi chúng là thành viên chuẩn mặc định.
- Giữ type URI ổn định. Nếu thay ý nghĩa của type, cân nhắc version.
- Dùng `code` máy đọc ổn định, còn `title/detail` có thể theo locale.
- Test rằng thư viện client vẫn parse được nếu server thêm extension keys mới.

## 15. Những lỗi phổ biến và chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm được `ProblemDetail` | Spring Framework 5.x hoặc dependency sai | Dùng DTO riêng hoặc nâng lên Spring 6+ đúng cách |
| Không tìm được `addErrorResponseInterceptors` | Spring Framework dưới 6.2 | Chỉ dùng interceptor trên 6.2+ |
| Không có `HandlerMethodValidationException` | Spring dưới 6.1 | Kiểm tra method validation theo stack/version hiện tại |
| Body vẫn là `{"timestamp":...,"error":...}` | Boot auto Problem Details chưa bật hoặc request đi qua BasicErrorController | Kiểm tra property/advice/exception route |
| Có hai advice cho built-in exceptions | Bật Boot property đồng thời tự extends ResponseEntityExceptionHandler | Đặt order/phạm vi rõ hoặc chọn một chiến lược |
| Domain exception trả HTTP 500 | Chưa có mapping hoặc dùng handler sai stack | Thêm @ExceptionHandler hoặc ErrorResponseException phù hợp |
| JSON có `status=400` nhưng HTTP 200 | Trả DTO thường thay vì ProblemDetail/ResponseEntity đúng status | Đồng bộ HTTP và body |
| `errors` không có trên mọi lỗi 400 | Không phải mọi lỗi là Bean Validation; ví dụ JSON malformed | Chuẩn hóa mỗi loại lỗi theo chính sách |
| Trả raw exception message | Lộ thông tin hệ thống | Dùng detail an toàn và logs riêng |
| `instance` chứa token | Đưa nguyên URL/query vào body | Dùng path/tracking identifier không nhạy cảm |
| Lỗi `typeMismatch` không có trong danh sách Bean Validation | Thất bại conversion trước validation | Phân biệt binder/Jackson/validator |
| Test không ổn định vì thứ tự lỗi | Violations không bảo đảm thứ tự phù hợp | Sort field/code hoặc assert không phụ thuộc thứ tự |
| MessageSource không dịch | Key/base bundle/locale không khớp | Kiểm tra message codes và Accept-Language |
| Copy chữ ký WebRequest vào WebFlux | MVC và WebFlux khác base class/method signatures | Dùng đúng package ServerWebExchange |
| Client nhận text/HTML thay vì JSON | Content negotiation, exception handler hoặc container error page khác | Test content type theo Accept và status |
| Thêm class-level @Validated cho controller vô tình đổi exception | Spring AOP method validation tác động | Dùng native Spring 6.1+ khi phù hợp |
| Status 500 sau khi stream đã bắt đầu | Response committed | Validate trước khi write hoặc dùng giao thức stream lỗi |
| HTTP 404 có format khác các lỗi còn lại | Có lỗi đi qua Boot error path thay vì advice | Kiểm tra routing, advice, properties và test contract |

### Checklist nâng cấp theo phiên bản

1. Xem effective Spring Framework version qua dependency tree/BOM.
2. Có `ProblemDetail` và `ErrorResponse` hay chưa? Nếu không, dùng DTO lỗi tương thích.
3. Có native controller method validation `HandlerMethodValidationException` không? Nếu có, kiểm thử direct constraints.
4. Có `ErrorResponse.Interceptor` trên 6.2+ không? Chỉ dùng nếu thực sự cần intercept trước rendering.
5. Dự án dùng MVC hay WebFlux? Chọn đúng `ResponseEntityExceptionHandler` package.
6. Boot có tự tạo problem advice không? Xác định property và advice ordering.
7. Có custom exception handler nào nuốt built-in handler không? Kiểm tra `@Order`, `@ControllerAdvice` scopes.
8. Lỗi input chuyển thành 400/422 theo contract; lỗi server/hậu điều kiện không bị giấu thành 400.
9. Kiểm tra content negotiation và `application/problem+json`.
10. Kiểm tra localization, không lộ bí mật và backward compatibility của `code/type/errors` extensions.

## 16. Bài tập vận dụng

**Bài 1.** Giải thích sự khác biệt giữa `ProblemDetail` và `ErrorResponse`. Vì sao chỉ có body JSON không đủ để biểu diễn headers và status của một HTTP error response?

**Bài 2.** Chạy ví dụ với `customerName=""` và `quantity=0`. Vì sao danh sách `errors` có thể chứa hai entries? Hãy sắp xếp chúng theo field/code để đảm bảo JSON ổn định.

**Bài 3.** Gửi body JSON không hợp cú pháp. Vì sao đó là `HttpMessageNotReadableException` thay vì `MethodArgumentNotValidException`? Nêu cách test HTTP status và media type mà không phụ thuộc câu lỗi nội bộ.

**Bài 4.** Thêm một direct constraint `@Min(1)` vào query parameter. Đối chiếu behavior trên Spring 6.0 và 6.1+; vì sao không nên cho rằng mọi validation exception có cùng class?

**Bài 5.** Thay một domain 404 thành `ErrorResponseException` mang `ProblemDetail`; bảo đảm HTTP status và body status đều 404. Khi nào ném exception có HTTP semantics thuận tiện hơn custom domain advice?

**Bài 6.** Bật `spring.mvc.problemdetails.enabled=true` trong một dự án đang có advice kế thừa `ResponseEntityExceptionHandler`. Kiểm tra thứ tự resolution; chọn chiến lược tránh hai handler cạnh tranh.

**Bài 7.** Tạo hai bản dịch của `problem.orderMissing`. Gửi `Accept-Language: vi` và `en`; vì sao `type` và `code` nên giữ nguyên dù `detail` thay đổi?

**Bài 8.** Viết extension `traceId` cho ProblemDetail mà không xuất JWT, session ID hoặc stack trace. Kiểm tra giá trị do hệ thống cấp, không để người dùng tùy ý đặt trace ID tin cậy.

**Bài 9.** Với Spring Framework 5.3, xây một DTO lỗi mô phỏng năm trường chuẩn. Lập kế hoạch migrate lên Spring 6 sao cho API client không phải thay logic lỗi ngay lập tức.

**Bài 10.** Viết contract tests cho HTTP 400, 404, 409 và 500; đảm bảo lỗi nội bộ không lộ exception message, status trong JSON khớp HTTP, và extension errors chỉ xuất hiện khi thích hợp.

## Kết luận

Hãy ghi nhớ ba tầng:

~~~text
Domain / binding / validation exception
                  |
                  v
        ErrorResponse contract
        (status + headers + body)
                  |
                  v
        ProblemDetail (RFC 9457)
        type/title/status/detail/instance
        + extension properties
                  |
                  v
       HTTP 4xx/5xx + problem+json
~~~

`ProblemDetail` là mô hình body, `ErrorResponse` là hợp đồng HTTP error đầy đủ, còn `ResponseEntityExceptionHandler` là công cụ giúp xử lý các exception web thông dụng. **Khả năng phiên bản** quyết định API nào có sẵn: Spring 5.x cần DTO riêng; 6.0 có Problem Details; 6.1 bổ sung native controller method validation; 6.2 bổ sung ErrorResponse interceptor. Chọn đúng stack MVC/WebFlux và cấu hình Boot, rồi test status, media type, content và thông tin riêng tư để có phản hồi lỗi ổn định.

## Tài liệu tham khảo

- [Spring Framework 6.2 — MVC Error Responses và RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — ProblemDetail Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework 6.2 — ErrorResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework 6.2 — ErrorResponseException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/ErrorResponseException.html)
- [Spring Framework 6.2 — ErrorResponse.Interceptor (since 6.2)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/ErrorResponse.Interceptor.html)
- [Spring Framework 6.2 — MVC ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — WebMvcConfigurer.addErrorResponseInterceptors](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework 6.2 — MVC Validation and HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
