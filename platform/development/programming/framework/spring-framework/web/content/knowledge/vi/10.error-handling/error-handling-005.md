# ProblemDetail, ErrorResponse và định dạng lỗi theo RFC 9457 trong Spring MVC

## 1. Vấn đề: tại sao REST API cần một hợp đồng lỗi thống nhất?

Một API thành công có thể trả DTO JSON rõ ràng nhưng lại trả nhiều kiểu lỗi không nhất quán:

```json
{"error":"not_found"}
```

```json
{"message":"Cannot find order","timestamp":"2026-10-21T10:00:00Z"}
```

```json
{"success":false,"data":null,"code":404}
```

Client phải viết nhiều nhánh xử lý và không biết đâu là thông tin dành cho máy, đâu là lời giải thích dành cho người. Việc trả HTTP `200 OK` nhưng đặt `"code":404` trong body còn làm sai HTTP semantics: bộ nhớ đệm, monitoring và client HTTP có thể hiểu đây là thành công.

**RFC 9457 — Problem Details for HTTP APIs** (xuất bản tháng 7/2023, thay thế RFC 7807) đề xuất một biểu diễn lỗi máy đọc được, dựa trên HTTP status và các field chung. Spring Framework 6.x hỗ trợ trực tiếp bằng:

- `org.springframework.http.ProblemDetail` — đối tượng biểu diễn một problem.
- `org.springframework.web.ErrorResponse` — hợp đồng để exception mô tả status, headers và `ProblemDetail`.
- `org.springframework.web.ErrorResponseException` — lớp exception nền thuận tiện triển khai `ErrorResponse`.
- `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` — base class cho `@ControllerAdvice` xử lý các lỗi thường gặp trong Spring MVC thành error response.

Bài này tập trung vào **Spring Web MVC (Servlet stack)**, không phải Spring WebFlux. Phần ví dụ cố định **Java 17, Spring Boot 3.3.5 và Spring Framework 6.1.x**, tránh dùng nhầm extension points chỉ xuất hiện ở những phiên bản mới hơn.

Mục tiêu học:

1. Hiểu ý nghĩa chuẩn RFC 9457, các field và media type `application/problem+json`.
2. Biết khi nào dùng `ProblemDetail`, `ErrorResponse` và `ErrorResponseException`.
3. Xử lý lỗi nghiệp vụ, lỗi validation và các lỗi MVC thường gặp theo một dạng thống nhất.
4. Dùng `@RestControllerAdvice` / `ResponseEntityExceptionHandler` một cách có phạm vi, không làm mất HTTP status.
5. Thiết kế extensions như `code`, `errors`, `traceId` an toàn, ổn định, dễ quốc tế hóa và kiểm thử.
6. Nhận biết giới hạn: không phải mọi exception, filter, security response hay streaming error đều tự động thành Problem Detail.

## 2. Đọc một response theo RFC 9457

Ví dụ một client hỏi về đơn hàng không tồn tại:

```http
GET /api/orders/999 HTTP/1.1
Host: localhost:8080
Accept: application/problem+json, application/json
```

Response theo hợp đồng minh họa:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 999",
  "instance": "/api/orders/999",
  "code": "ORDER_NOT_FOUND"
}
```

Các field chuẩn:

| Field | Kiểu JSON | Ý nghĩa cần ghi nhớ |
| --- | --- | --- |
| `type` | URI string | Định danh **loại vấn đề**: cùng loại lỗi nên dùng cùng một URI ổn định |
| `title` | String | Mô tả ngắn, dễ đọc về **loại lỗi**; không nên đổi tùy từng occurrence, ngoại trừ ngôn ngữ |
| `status` | Number | Mã trạng thái HTTP của occurrence khi problem được tạo; **actual HTTP status vẫn là thông tin giao thức quan trọng nhất** |
| `detail` | String | Giải thích cụ thể cho **lần xảy ra lỗi**, giúp client/người dùng hiểu |
| `instance` | URI string | Xác định **lần xảy ra cụ thể**; thường là request path hoặc URI do hệ thống cấp |

RFC 9457 không bắt buộc mọi JSON problem chứa đủ cả năm field trong mọi trường hợp. `type` mặc định mang nghĩa `about:blank` khi không khai báo; `status` hữu ích nhất khi cùng giá trị với HTTP response status; `title` có thể mặc định từ HTTP reason phrase với `about:blank`. Các nội dung như `detail` và `instance` có thể không xuất hiện nếu không được cung cấp.

**`type` khác `instance`:** `type` cho biết lỗi thuộc *loại gì* (ví dụ sản phẩm không tồn tại), còn `instance` cho biết *lần gặp lỗi nào* (ví dụ request `/api/orders/999`). Với URI `https://api.example.com/problems/order-not-found`, tên miền `example.com` chỉ để **minh họa**; trong hệ thống thật nên dùng URI do tổ chức kiểm soát, ổn định và lý tưởng là có trang tài liệu giải thích cách xử lý.

### Extension members không phải field chuẩn

`code` trong JSON trên là **extension** của ứng dụng. RFC cho phép thêm tên/value tùy theo problem type, ví dụ:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Invalid request",
  "status": 400,
  "detail": "Some submitted fields are invalid",
  "errors": [
    {"field":"quantity","message":"must be greater than or equal to 1"},
    {"field":"sku","message":"must not be blank"}
  ]
}
```

Ở đây `errors` cũng là extension, không phải schema validation chính thức bắt buộc từ RFC. Khi muốn client dựa trên `code` hoặc `errors`, server phải tài liệu hóa kiểu, ý nghĩa và tính ổn định của chúng. Với lỗi trên object JSON lồng nhau, có thể dùng đường dẫn theo **JSON Pointer** như `"/customer/address/postalCode"` thay vì chỉ một tên field không phân biệt được nested location.

### Media type và HTTP status

- JSON representation chuẩn dùng **`application/problem+json`**.
- RFC cũng xác định representation XML `application/problem+xml` khi dùng XML, nhưng Spring Boot Web mặc định không nhất thiết có XML converter; không cam kết XML chỉ vì RFC định nghĩa.
- Với `400`, `404`, `409`, `422`, `500`, **header/status line thực** không được mâu thuẫn với body `status`.
- Không biến mọi lỗi thành `200` chỉ để frontend dễ parse. API client nên kiểm tra status trước rồi đọc body.
- `Problem Details` thường dùng cho lỗi 4xx/5xx, nhưng RFC không giới hạn máy móc chỉ cho những mã này. Không dùng nó để thay thế mọi representation thành công.

## 3. Ba abstraction của Spring: mối quan hệ và lựa chọn

### 3.1. ProblemDetail là dữ liệu của một lỗi

`ProblemDetail` không phải một exception. Đây là object chứa thông tin RFC; có các factory và setter:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "No order exists with id 999");
problem.setType(URI.create(
        "https://api.example.com/problems/order-not-found"));
problem.setTitle("Order not found");
problem.setInstance(URI.create("/api/orders/999"));
problem.setProperty("code", "ORDER_NOT_FOUND");
```

Đây là snippet Java cần imports `java.net.URI`, `org.springframework.http.HttpStatus` và `org.springframework.http.ProblemDetail`. Khi được trả từ `@ExceptionHandler` trong MVC, Spring biết render nó và đặt HTTP status phù hợp từ `ProblemDetail.status`. Nếu chưa gán `instance`, Spring MVC có thể đặt request path khi render `ProblemDetail`.

`ProblemDetail.forStatus(HttpStatus.BAD_REQUEST)` tạo lỗi chỉ với status và các defaults. `ProblemDetail.forStatusAndDetail(...)` tiện khi đã có thông điệp ngắn cho client. Lưu ý `detail` **không phải** chỗ đổ nguyên `exception.getMessage()` từ database, stack trace, tokens hoặc câu SQL.

#### Dynamic properties trong JSON

`problem.setProperty("code", "ORDER_NOT_FOUND")` lưu extension trong một `Map` của `ProblemDetail`. Khi dùng Jackson với Spring MVC, `ProblemDetailJacksonMixin` đưa extension lên **top-level JSON** như `"code"`, không tạo `"properties":{"code":...}`. Tránh extension trùng tên các field chuẩn (`type`, `title`, `status`, `detail`, `instance`) vì gây mơ hồ.

### 3.2. ErrorResponse là hợp đồng cho exception có thông tin HTTP

`ErrorResponse` là interface ở package `org.springframework.web`, cho phép Spring xem exception như một phản hồi HTTP có cấu trúc. Các member cốt lõi:

```java
HttpStatusCode getStatusCode();
HttpHeaders getHeaders();
ProblemDetail getBody();
```

Các chữ ký trên rút gọn để giải thích, không phải file interface độc lập có imports đầy đủ. Interface còn có tiện ích và các message codes giúp xử lý quốc tế hóa.

Nhiều exception của Spring MVC, chẳng hạn loại lỗi argument/validation hoặc media type, mang `ErrorResponse` và có thể được chuyển thành `ProblemDetail` thông qua hệ xử lý exception của MVC. Điều đó **không có nghĩa** chỉ cần ném mọi `RuntimeException` là tự động có thông điệp RFC an toàn; exception tùy ý vẫn cần chính sách map.

### 3.3. ErrorResponseException là một cách chủ động ném lỗi

`ErrorResponseException` (Spring Framework từ 6.0) là `RuntimeException` implement `ErrorResponse`. Ví dụ:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "This order cannot be placed while the product is locked.");
problem.setType(URI.create(
        "https://api.example.com/problems/product-locked"));
problem.setTitle("Product locked");
problem.setProperty("code", "PRODUCT_LOCKED");

throw new ErrorResponseException(HttpStatus.CONFLICT, problem, null);
```

Đây là **snippet** trong một method, không phải chương trình `main`. Exception đã mang status `409 Conflict` và body problem. Khi có `ResponseEntityExceptionHandler` hoạt động, exception này được xử lý theo RFC. Constructor nhận `status, ProblemDetail, cause` có sẵn ở Spring 6.1.

Không sử dụng `ErrorResponseException` để ném bừa mọi lỗi: nếu cần một domain exception riêng dễ hiểu, hãy khai báo `OrderNotFoundException` rồi map ở `@ExceptionHandler`; cả hai đều hợp lệ tùy thiết kế.

### 3.4. ResponseEntityExceptionHandler là cơ sở tái sử dụng

`ResponseEntityExceptionHandler` có các method xử lý nhiều exception do Spring MVC tạo ra. Subclass dùng `@ControllerAdvice` hoặc `@RestControllerAdvice` để:

- Giữ cách xử lý tương đối thống nhất cho `400`, `405`, `406`, `415` và các lỗi MVC khác.
- Override một handler cụ thể, ví dụ `handleMethodArgumentNotValid`, để bổ sung `errors`.
- Tạo `ProblemDetail` tùy biến và điều chỉnh logic xây `ResponseEntity`.
- Kết hợp `MessageSource` nhằm lấy message theo locale.

Đối với Spring MVC 6.1, đây là base class thích hợp để chuẩn hóa lỗi đến từ framework. Không coi nó là “bắt mọi `Exception` không phân biệt”: chưa bắt các lỗi nghiệp vụ custom trừ khi bạn cung cấp handler/kiểu phù hợp; các lỗi xảy ra **ngoài DispatcherServlet** (như phần của Spring Security filter chain) cũng có con đường xử lý khác.

## 4. Luồng lỗi đi qua Spring MVC

```text
HTTP request
    |
    v
DispatcherServlet / HandlerMapping
    |
    v
Handler method / argument resolution / validation
    |
    +---- thành công -----------------> controller response
    |
    +---- lỗi: exception
                  |
                  v
        HandlerExceptionResolver chain
                  |
          +-------+--------------------------+
          |                                  |
   @ExceptionHandler ở controller     @ControllerAdvice
          |                            / ResponseEntityExceptionHandler
          |                                  |
          +--------------+-------------------+
                         |
                         v
                 ProblemDetail / ResponseEntity
                         |
                         v
                   HttpMessageConverter
                         |
                         v
             HTTP 4xx/5xx + application/problem+json
```

Đường đi trên là mô hình khái quát. Các resolver của Spring có thứ tự; `@ExceptionHandler` gần controller và advice có điều kiện match/order. Một `@ControllerAdvice` quá rộng hoặc có nhiều handler trùng nhau có thể làm exception bị giải quyết khác dự kiến. Khi response đã commit, framework có thể không còn thay status/body được nữa.

| Nguồn lỗi | Ví dụ | Status điển hình | Cách xử lý |
| --- | --- | --- | --- |
| JSON body sai cú pháp | `{"sku":` | `400` | `HttpMessageNotReadableException` |
| Bean Validation thất bại | `quantity=0` với `@Min(1)` | `400` | `MethodArgumentNotValidException` cho `@Valid @RequestBody` |
| Route/method không hỗ trợ | `PUT` vào endpoint chỉ `POST` | `405` | `HttpRequestMethodNotSupportedException` |
| Không nhận media type | `text/plain` gửi vào JSON endpoint | `415` | `HttpMediaTypeNotSupportedException` |
| Client không chấp nhận output | `Accept: application/xml` nhưng chỉ trả JSON | `406` | `HttpMediaTypeNotAcceptableException` |
| Tài nguyên nghiệp vụ không tồn tại | Order id không có | `404` | Custom exception + `@ExceptionHandler` |
| Trạng thái nghiệp vụ xung đột | Product đang locked | `409` | `ErrorResponseException`/domain mapping |
| Lỗi hệ thống ngoài dự kiến | DB timeout, NPE | `500` | Logging nội bộ; body an toàn, không lộ stack |

**Lưu ý:** status cụ thể có thể chịu ảnh hưởng bởi annotations, custom exception handlers và cấu hình. Ví dụ `422 Unprocessable Content` đôi khi được API dùng cho validation thay vì `400`; chọn đúng semantics theo hợp đồng và giữ nhất quán. Không mặc định nói `@Valid` luôn trả `422` hoặc mọi controller luôn trả JSON RFC khi chưa cấu hình.

### Spring Boot 3.3 và lựa chọn bật problem details

Trong Spring Boot 3.3, thuộc tính:

```properties
spring.mvc.problemdetails.enabled=true
```

cho phép auto-configuration xử lý các lỗi MVC được hỗ trợ thành problem details. **Giá trị mặc định của thuộc tính ở Boot 3.3 là `false`**; không được giả định Boot tự bật chỉ vì project có `spring-boot-starter-web`.

Có hai hướng triển khai phổ biến:

- **Hướng A:** bật property trên và thêm advice khác cho exception nghiệp vụ, chú ý thứ tự của advice khi tùy biến built-in errors.
- **Hướng B:** tự tạo một `@RestControllerAdvice extends ResponseEntityExceptionHandler` để xử lý các lỗi MVC và custom errors tập trung.

**Ví dụ chạy ở phần 5 chọn hướng B**, vì vậy **không bật** property trên trong `application.properties`. Tránh tạo nhiều bean xử lý cùng nhóm lỗi với cùng độ ưu tiên rồi giả định chúng tự phối hợp; cần xác định chủ sở hữu chính sách lỗi và kiểm tra thực tế.

## 5. Ví dụ hoàn chỉnh: Java 17 + Spring MVC + RFC 9457

Ứng dụng demo xử lý đơn hàng:

- `POST /api/orders` với JSON `{"sku":"BOOK-1","quantity":2}` trả `201 Created`.
- `sku="MISSING"` ném custom `ProductNotFoundException`, map sang `404` và mã `PRODUCT_NOT_FOUND`.
- `sku="LOCKED"` ném `ErrorResponseException`, trả `409` và mã `PRODUCT_LOCKED`.
- `quantity=0` hoặc `sku=""` gây Bean Validation `400`, trả extension `errors`.
- JSON malformed gây lỗi converter, được base handler xử lý thành RFC response.

Không có database, authentication, giao dịch hay persistence; các lỗi là **giả lập có kiểm soát** để nhìn rõ vòng đời HTTP.

### 5.1. Cấu trúc Maven

```text
problem-details-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/problems/
    │       ├── ProblemDetailsApplication.java
    │       ├── OrderController.java
    │       ├── ProductNotFoundException.java
    │       └── ApiErrorAdvice.java
    └── test/
        └── java/demo/problems/
            └── ApiErrorContractTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
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
```

**`src/main/java/demo/problems/ProblemDetailsApplication.java`**

```java
package demo.problems;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProblemDetailsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProblemDetailsApplication.class, args);
    }
}
```

### 5.2. Domain exception tách biệt HTTP

**`ProductNotFoundException.java`**

```java
package demo.problems;

public class ProductNotFoundException extends RuntimeException {
    private final String sku;

    public ProductNotFoundException(String sku) {
        super("Product not found");
        this.sku = sku;
    }

    public String getSku() {
        return sku;
    }
}
```

Exception này không biết HTTP status hay JSON schema. `ApiErrorAdvice` quyết định khi nó đi qua boundary REST thì status `404` và problem type nào được dùng. Với ứng dụng nhiều transport (REST, batch job, messaging), giữ domain exception tách với Spring Web có thể giúp tái sử dụng.

### 5.3. Controller tạo dữ liệu thành công và hai loại lỗi nghiệp vụ

**`OrderController.java`**

```java
package demo.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.ErrorResponseException;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record CreateOrderRequest(
            @NotBlank String sku,
            @Min(1) int quantity) {}

    public record OrderReceipt(long orderId, String sku, int quantity) {}

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderRequest input) {

        if ("MISSING".equals(input.sku())) {
            throw new ProductNotFoundException(input.sku());
        }

        if ("LOCKED".equals(input.sku())) {
            ProblemDetail body = ProblemDetail.forStatusAndDetail(
                    HttpStatus.CONFLICT,
                    "This product cannot be ordered while locked.");
            body.setType(URI.create(
                    "https://api.example.com/problems/product-locked"));
            body.setTitle("Product locked");
            body.setProperty("code", "PRODUCT_LOCKED");
            throw new ErrorResponseException(
                    HttpStatus.CONFLICT, body, null);
        }

        OrderReceipt receipt = new OrderReceipt(
                1001L, input.sku(), input.quantity());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }
}
```

- `@Valid @RequestBody`: JSON converter đọc request thành record, sau đó validation kiểm tra các constraints.
- `@Min(1)` trên `int quantity`: `0` là giá trị không hợp lệ, nhưng **field vắng mặt** có thể trở thành `0` vì primitive default; ở API thực cần tách missing và zero nếu contract quan tâm (dùng `Integer` + `@NotNull`).
- Hai nhánh `MISSING` và `LOCKED` mô phỏng các trạng thái để test. Trong production phải kiểm tra quyền sở hữu, tồn tại và trạng thái tại tầng service/database.
- `ResponseEntity<OrderReceipt>` của nhánh thành công không dùng RFC error schema; response là JSON DTO thường.
- `ErrorResponseException` chỉ tạo khi đã có tình huống HTTP `409` rõ ràng. Nó không nên chứa thông tin nội bộ nhạy cảm.

### 5.4. Advice: custom 404 và extension errors cho Bean Validation

**`ApiErrorAdvice.java`**

```java
package demo.problems;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail notFound(
            ProductNotFoundException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Requested product was not found.");
        problem.setType(URI.create(
                "https://api.example.com/problems/product-not-found"));
        problem.setTitle("Product not found");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        return problem;
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status, "One or more request fields are invalid.");
        problem.setType(URI.create(
                "https://api.example.com/problems/invalid-request"));
        problem.setTitle("Invalid request");
        problem.setProperty("code", "INVALID_REQUEST");

        List<Map<String, String>> errors = exception
                .getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "message", Objects.toString(
                                error.getDefaultMessage(), "Invalid value")))
                .sorted(Comparator.comparing(item -> item.get("field")))
                .toList();

        problem.setProperty("errors", errors);

        return handleExceptionInternal(
                exception, problem, headers, status, request);
    }
}
```

**Giải thích từng lựa chọn:**

- `@RestControllerAdvice` làm các `@ExceptionHandler` trả body JSON; kế thừa `ResponseEntityExceptionHandler` xử lý lỗi framework.
- `notFound` được gọi với exception nghiệp vụ riêng, trả `ProblemDetail`. Spring MVC dùng `problem.status=404` làm HTTP status và ưu tiên `application/problem+json` cho JSON problem.
- `setInstance(URI.create(request.getRequestURI()))` cung cấp request path để nhận diện occurrence; không đưa query string chứa token/password vào instance.
- `handleMethodArgumentNotValid` override đúng chữ ký của Spring 6.1. Trong trường hợp validation đầu vào trên `@RequestBody`, status mặc định thường là `400`.
- `getFieldErrors()` đưa ra lỗi theo field; `sorted(...)` làm mảng ổn định khi test. Dùng `Objects.toString(...,"Invalid value")` để không ném NullPointerException khi default message vắng mặt.
- `handleExceptionInternal(...)` giữ đường xử lý chung của base class thay vì tự dựng mọi thứ từ đầu.
- Snippet chỉ trả **tên field + message**, không đưa `FieldError.getRejectedValue()` vào body, tránh vô ý echo password/PII.
- URI `https://api.example.com/...` trong bài là địa chỉ minh họa. Khi triển khai thật, thay bằng URI do hệ thống sở hữu và tài liệu hóa ổn định.
- Lỗi media type, malformed JSON và một số lỗi MVC khác do các method sẵn có của `ResponseEntityExceptionHandler` giải quyết. Không cần viết `catch (Exception)` cho mọi trường hợp ở controller.

### 5.5. Chạy và quan sát response

Yêu cầu JDK 17+ và Maven. Từ thư mục `problem-details-demo` chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Đây là hai lệnh chạy **tuần tự**, không phải một lệnh. Khi Spring Boot khởi động cổng `8080`, hãy gửi các request dưới đây.

**Thành công — HTTP 201, không phải Problem Detail:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"sku":"BOOK-1","quantity":2}'
```

Phần quan trọng của response:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":1001,"sku":"BOOK-1","quantity":2}
```

**Không tìm thấy sản phẩm — HTTP 404:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"MISSING","quantity":2}'
```

Body minh họa theo mapping chính xác trong example:

```json
{
  "type": "https://api.example.com/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "Requested product was not found.",
  "instance": "/api/orders",
  "code": "PRODUCT_NOT_FOUND"
}
```

Đường `instance` là `/api/orders` do `HttpServletRequest.getRequestURI()` trong advice. Thứ tự key và indentation ở trên chỉ phục vụ đọc; JSON serializer thường trả một dòng.

**Sản phẩm bị khóa — HTTP 409:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"LOCKED","quantity":2}'
```

Kết quả mong đợi gồm status `409 Conflict`, `Content-Type: application/problem+json`, và body có:

```json
{
  "type": "https://api.example.com/problems/product-locked",
  "title": "Product locked",
  "status": 409,
  "detail": "This product cannot be ordered while locked.",
  "instance": "/api/orders",
  "code": "PRODUCT_LOCKED"
}
```

`instance` có thể được Spring gán theo request path khi body problem chưa có instance. Không suy luận HTTP headers khác, thứ tự key hoặc JSON whitespace là contract.

**Validation lỗi — HTTP 400 cùng mảng errors:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"","quantity":0}'
```

Ví dụ kết quả:

```json
{
  "type": "https://api.example.com/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/orders",
  "code": "INVALID_REQUEST",
  "errors": [
    {
      "field": "quantity",
      "message": "must be greater than or equal to 1"
    },
    {
      "field": "sku",
      "message": "must not be blank"
    }
  ]
}
```

Thông điệp `message` thực tế do Bean Validation provider và locale quyết định; phần body minh họa ngôn ngữ tiếng Anh thường gặp. Contract test nên kiểm tra **tên field, mã lỗi và HTTP status**, tránh phụ thuộc wording cụ thể nếu ứng dụng hỗ trợ i18n.

**JSON hỏng — HTTP 400 nhưng không nhất thiết cùng `errors`:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  --data-binary '{"sku":'
```

Spring có thể ném `HttpMessageNotReadableException` ở bước parse body, trước Bean Validation. Base class sẽ xử lý lỗi này theo behavior của framework, nên response thường là `400` với problem body nhưng **không có mảng `errors` do override validation ở trên**. Không tự chế tên field khi JSON hỏng và chưa tạo được DTO.

### 5.6. Kiểm thử hợp đồng lỗi với MockMvc

**`src/test/java/demo/problems/ApiErrorContractTest.java`**

```java
package demo.problems;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiErrorContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validRequestReturns201() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"BOOK-1\",\"quantity\":2}"))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.orderId").value(1001))
           .andExpect(jsonPath("$.sku").value("BOOK-1"));
    }

    @Test
    void productNotFoundReturnsProblemDetail() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"MISSING\",\"quantity\":1}"))
           .andExpect(status().isNotFound())
           .andExpect(content().contentTypeCompatibleWith(
                    MediaType.parseMediaType("application/problem+json")))
           .andExpect(jsonPath("$.status").value(404))
           .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
           .andExpect(jsonPath("$.instance").value("/api/orders"));
    }

    @Test
    void lockedProductReturnsConflict() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"LOCKED\",\"quantity\":1}"))
           .andExpect(status().isConflict())
           .andExpect(jsonPath("$.status").value(409))
           .andExpect(jsonPath("$.code").value("PRODUCT_LOCKED"));
    }

    @Test
    void invalidRequestReportsFields() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"\",\"quantity\":0}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
           .andExpect(jsonPath("$.errors[0].field").value("quantity"))
           .andExpect(jsonPath("$.errors[1].field").value("sku"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":"))
           .andExpect(status().isBadRequest());
    }
}
```

Chạy kiểm thử:

```bash
mvn test
```

Bộ test có **5 test methods**. Nếu setup đúng và tất cả đều pass, Maven kết thúc exit code `0`; dòng tổng kết có thể hiển thị `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`, còn thời gian/log phụ thuộc môi trường.

`MockMvc` kiểm thử response thông qua MVC framework mà không cần server port thật. Tuy nhiên contract tests cần bổ sung trường hợp media type `415`, `405`, `404` của resource khác, i18n, quyền truy cập, lỗi không mong đợi và headers tùy contract. Tránh test toàn bộ lỗi bằng so sánh raw JSON string, vì thứ tự JSON object keys không phải ngữ nghĩa của RFC.

## 6. @ExceptionHandler, @RestControllerAdvice và lựa chọn phạm vi

Một handler cục bộ có thể dành cho riêng controller:

```java
@ExceptionHandler(ProductNotFoundException.class)
public ProblemDetail notFound(ProductNotFoundException ex) {
    ProblemDetail p = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
    p.setTitle("Product not found");
    return p;
}
```

Đây là snippet cần đặt trong controller/advice cùng imports. Nó không phải file chạy độc lập. Nếu chỉ một controller có error contract đặc thù, local handler có thể đủ.

Khi có nhiều controller, dùng `@RestControllerAdvice` cho một tập API hoặc module. Một số tham số selector của `@ControllerAdvice`:

- `basePackages` hoặc `basePackageClasses` — giới hạn controller theo package.
- `assignableTypes` — giới hạn controller theo class/interface.
- `annotations` — áp dụng cho controller có annotation nhất định.
- `@Order` — quyết định ưu tiên giữa nhiều advice phù hợp.

Đừng tạo một `@ExceptionHandler(Exception.class)` toàn cục mà trả `400` cho mọi lỗi. NPE, lỗi database hoặc lỗi serialization nội bộ không phải lỗi client. Một handler 500 fallback nếu cần phải **log exception server-side** và trả detail an toàn, không che khuất telemetry/incident. Nếu ứng dụng có Spring Security, các lỗi `AuthenticationException` và `AccessDeniedException` có thể được `AuthenticationEntryPoint`/`AccessDeniedHandler` xử lý trong filter chain, không chắc đi qua cùng MVC advice.

### @ResponseStatus và ResponseStatusException

`@ResponseStatus(HttpStatus.NOT_FOUND)` trên exception hoặc controller method có thể điều khiển status, nhưng không tự thiết kế đầy đủ RFC error schema. `ResponseStatusException` là một loại `ErrorResponseException` có thể hữu ích cho một trạng thái HTTP cụ thể; vẫn cần cân nhắc định nghĩa `type`, `code` và thông tin công khai. Với domain exception như `ProductNotFoundException`, handler riêng thường diễn đạt hợp đồng rõ ràng hơn.

### Tránh xung đột khi bật Spring Boot problem details

Nếu `spring.mvc.problemdetails.enabled=true`, Boot có thể đăng ký advice của chính nó để xử lý nhiều lỗi built-in. Khi muốn override behavior một nhóm exception này bằng advice khác, phải xác định thứ tự (`@Order`) và cách chọn exception handler. Trong ví dụ ở phần 5 đã chủ động kế thừa `ResponseEntityExceptionHandler` và không bật property, nên có một nơi sở hữu chính sách MVC errors của ứng dụng.

## 7. Chọn mã HTTP status đúng với lỗi

| Status | Tình huống thường gặp | Phân biệt quan trọng |
| --- | --- | --- |
| `400 Bad Request` | JSON malformed, field/type không hợp lệ, validation request | Request không phù hợp hợp đồng |
| `401 Unauthorized` | Thiếu hoặc không hợp lệ thông tin xác thực | Thường cần `WWW-Authenticate` phù hợp cơ chế |
| `403 Forbidden` | Đã xác thực nhưng không đủ quyền | Không đổi thành 200; tránh lộ chi tiết policy |
| `404 Not Found` | Resource không có hoặc không tiết lộ sự tồn tại | Có thể cần tránh lộ enumeration |
| `405 Method Not Allowed` | Dùng HTTP method không được route hỗ trợ | HTTP `Allow` header có ý nghĩa |
| `406 Not Acceptable` | Không tạo được representation client chấp nhận | Phân biệt từ `Content-Type` của request |
| `409 Conflict` | Xung đột trạng thái hiện tại của resource | Không phải tất cả validation errors |
| `415 Unsupported Media Type` | Request body format không hỗ trợ | Ví dụ gửi `text/plain` cho endpoint chỉ nhận JSON |
| `422 Unprocessable Content` | Server hiểu media/type/cú pháp, nhưng không xử lý nội dung theo semantics | Tùy contract phân biệt với `400` |
| `429 Too Many Requests` | Client vượt giới hạn tần suất | Cân nhắc `Retry-After` phù hợp |
| `500 Internal Server Error` | Lỗi server không đoán trước | Detail phải tránh tiết lộ nội bộ |
| `503 Service Unavailable` | Server tạm thời không phục vụ | Có thể dùng `Retry-After` nếu biết |

Không nên viết `status=404` trong JSON trong khi HTTP response thật vẫn `200`. Tương tự, nếu `ResponseEntity` chủ động đặt HTTP status khác `ProblemDetail.status`, cần sửa ngay sự bất nhất.

## 8. Thiết kế problem type và extension thành hợp đồng dài hạn

### 8.1. Chọn URI type ổn định

Một URI như `https://api.example.com/problems/order-not-found` đại diện một **loại lỗi**. Nó không phải occurrence ID và không nên chứa dữ liệu user-specific. Khi sử dụng namespace thực:

1. Công bố mô tả lỗi, status, các extension, nguyên nhân và hướng khắc phục.
2. Giữ URI ổn định qua các bản deploy.
3. Tránh tạo type mới cho từng tham số/sản phẩm/id.
4. Không tái sử dụng cùng URI cho semantics hoàn toàn khác.
5. Nếu thay đổi breaking error schema, cập nhật contract theo chính sách versioning.

RFC 9457 khuyến nghị type URI khi dereference có thể trả tài liệu giúp người đọc hiểu lỗi, nhưng không yêu cầu client phải truy cập mạng vào URI để xử lý response. Client nên map stable type/code theo dữ liệu nó có, không bắt buộc fetch tài liệu ở runtime.

### 8.2. Type, code và title khác nhau như thế nào?

Ví dụ:

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 999",
  "code": "ORDER_NOT_FOUND"
}
```

- **`type`:** định danh machine-readable theo tinh thần RFC.
- **`code`:** tiện ích tùy chọn của ứng dụng, hữu ích nếu organization đã có error codes và SDK dùng enum. Không bắt buộc bởi RFC.
- **`title`:** nhãn ngắn để con người đọc, có thể được bản địa hóa; không nên dùng title như mã ổn định.
- **`detail`:** nội dung lần xảy ra, có thể thay đổi theo ngôn ngữ/giá trị cụ thể; client không nên parse text message để quyết định hành vi.

Nếu API đã có `type` ổn định và consumer dùng nó, đừng thêm `code` chỉ để lặp lại cùng thông tin mà không có ích. Nếu cần cả hai, định nghĩa consistency rule và test để tránh mismatch.

### 8.3. Validation errors theo trường

RFC 9457 cho phép extension `errors` theo contract của từng problem type; dạng sau hữu ích với form UI:

```json
{
  "type": "https://api.example.com/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "errors": [
    {
      "pointer": "/shippingAddress/postalCode",
      "code": "INVALID_FORMAT",
      "message": "Invalid postal code"
    }
  ]
}
```

`pointer` ở đây là JSON Pointer theo **đề xuất hợp đồng ứng dụng**; không mặc định Spring tự biến `FieldError.getField()` thành JSON Pointer. Với nested Java Bean path như `shippingAddress.postalCode`, phải chuyển đổi escape RFC 6901 cẩn thận; không đơn giản `replace(".", "/")` nếu key có ký tự đặc biệt, dấu slash hoặc mảng.

Nên giữ field errors nhất quán về shape và tránh trả giá trị `rejectedValue` chứa dữ liệu nhạy cảm. Một số constraint trên class-level hoặc cross-field chỉ có global errors, không có field path; nếu hợp đồng cần báo chúng, thiết kế loại extension tương ứng, thay vì âm thầm bỏ qua.

### 8.4. Trace ID và correlation ID

Để người dùng báo lỗi và bộ phận hỗ trợ tra log, có thể bổ sung `traceId` từ hệ thống tracing:

```json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected server error occurred.",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Đây chỉ là JSON minh họa. `traceId` là extension, không bắt buộc theo RFC. Đừng tự phát sinh “trace ID” tùy tiện từ UUID trong từng exception rồi tuyên bố có thể tra trong log nếu log không gắn cùng ID. Nếu dùng Micrometer Tracing/OpenTelemetry, lấy ID từ active trace/observation và bảo đảm logger, exporter, response liên kết được.

Không trả stack trace, đường dẫn file nội bộ, SQL syntax, user email, access token, connection string hoặc secrets cho client.

## 9. Quốc tế hóa và xử lý thông điệp một cách an toàn

Problem Details hỗ trợ human-readable `title` và `detail` theo ngôn ngữ; client có thể gửi `Accept-Language`. Tuy nhiên `type`, `code` và HTTP status phải giữ **nghĩa ổn định** khi ngôn ngữ thay đổi.

Spring hỗ trợ `MessageSource`. `ResponseEntityExceptionHandler` có thể tra message codes cho `type`, `title` và `detail` của `ErrorResponse`. Mẫu code mặc định thường gồm:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.<fully-qualified-exception-class>
```

Ví dụ chính sách translation của tổ chức có thể map `INVALID_REQUEST` thành title Việt/Anh. Với custom exceptions và `ProblemDetail` xây thủ công, bạn cần chủ động dùng `MessageSource` hoặc policy riêng, không mong string viết cứng trong controller tự dịch.

Những nguyên tắc nên tuân thủ:

- Đừng để locale đổi `type URI`/`code`.
- Đừng dùng `detail` làm format máy parse cố định; nó có thể chứa văn bản bản địa hóa.
- Message dành cho client khác với log message dành cho dev/ops.
- Client cần hiển thị UX có thể dựa vào `code` hoặc `type` để tự trình bày lời giải thích phù hợp, tránh buộc backend trả thông tin quá chi tiết.
- Không đưa thông điệp từ exception nội bộ hoặc database thẳng vào `detail` nếu chưa kiểm tra an toàn.

## 10. Những giới hạn của ProblemDetail trong triển khai thực tế

### 10.1. Không tự động bao trùm toàn bộ stack

Những lỗi trong Servlet filter, Spring Security, reverse proxy, API gateway, container, servlet asynchronous timeout, SSE/websocket hoặc response stream đã commit có thể bypass MVC advice. Nếu yêu cầu một lỗi JSON thống nhất xuyên lớp, phải phối hợp nhiều tầng và test riêng. Không giả định `@RestControllerAdvice` sẽ bắt exception authentication/authorization từ security filter chain.

### 10.2. Không “bọc” ProblemDetail thêm một envelope lạ

Nếu global `ResponseBodyAdvice` tự biến mọi response thành:

```json
{"success":false,"data":{"type":"...","title":"...","status":400}}
```

thì body đó **không còn là Problem Detail top-level** theo schema `application/problem+json` mà client RFC đang mong đợi. Trường hợp cần envelope riêng phải đổi media type/contract cho phù hợp hoặc loại trừ `ProblemDetail` khỏi wrapper. Với Spring MVC, converter được chọn **trước** hook `ResponseBodyAdvice.beforeBodyWrite`; thay kiểu object tùy tiện có thể gây lỗi serialize.

### 10.3. Chuyển lỗi 500 không nên làm mất telemetry

Một fallback handler toàn cục kiểu:

```java
@ExceptionHandler(Exception.class)
public ProblemDetail fallback(Exception ex) {
    return ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "An unexpected server error occurred.");
}
```

Đây là **snippet minh họa**, không phải file đầy đủ. Nó cho client response an toàn nhưng có thể làm lỗi được xem như đã xử lý, ảnh hưởng logging và observation nếu không có policy rõ. Trong thực tế phải log đầy đủ server-side theo chuẩn không lộ secrets, tích hợp tracing/metrics, và đảm bảo không “nuốt” lỗi mà vận hành cần phát hiện.

### 10.4. Không thay thế validation và authorization

`ProblemDetail` chỉ là **biểu diễn lỗi**. Nếu server chấp nhận request thiếu quyền, trả JSON đẹp không sửa được lỗ hổng. Tương tự, DTO validation phải chạy độc lập; conversion/validation errors chỉ được ánh xạ thành problem sau khi phát hiện. Tránh sử dụng `ProblemDetail` như một kho tùy ý cho dữ liệu lỗi kinh doanh không có HTTP semantics rõ ràng.

### 10.5. Status/body nhất quán với RFC

- Dùng `ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND,...)` và trả từ `@ExceptionHandler` thường khiến Spring chọn status tương ứng.
- Nếu dùng `ResponseEntity<ProblemDetail>`, phải bảo đảm `ResponseEntity.status` và `ProblemDetail.status` bằng nhau.
- Media type `application/problem+json` là định dạng JSON chuyên dụng; giữ body object top-level, không trả chuỗi JSON tự ghép.
- Không nên đưa ProblemDetail body vào `204 No Content`, `304 Not Modified` hay phản hồi `HEAD` trái semantics body.
- Error response có thể cần cache control, retry, rate-limit headers; Problem Details không tự tạo mọi header chính sách.

### 10.6. Không nạp các thông tin nhạy cảm vào extensions

`ProblemDetail.setProperty("debug", exception)` hoặc `setProperty("params", request.getParameterMap())` có thể vô tình serialize thông tin nội bộ, PII hoặc secret. Hãy duyệt whitelist field/giá trị an toàn và giới hạn độ dài. Bởi extensions được Jackson đưa lên top-level, việc “gửi thêm cho tiện debug” có tác động công khai trực tiếp.

## 11. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `400` nhưng body không phải RFC | Boot problem-details chưa bật, không có handler phù hợp | Kiểm tra `spring.mvc.problemdetails.enabled` hoặc advice tự định nghĩa |
| `ProblemDetail` nhưng HTTP status `200` | Trả DTO JSON tùy biến/ResponseEntity status sai | Kiểm tra status line và `ProblemDetail.status` |
| Có `"properties":{"code":...}` thay vì top-level `code` | Không sử dụng Spring Jackson mixin/config tương ứng | Kiểm tra `ProblemDetailJacksonMixin` và converter |
| `type` luôn là `about:blank` | Chưa gán type URI | Nếu cần machine-readable problem riêng, đặt type ổn định |
| Lỗi validation có `400` nhưng không có `errors` | Base handler không định nghĩa extension tùy chỉnh | Override đúng `handleMethodArgumentNotValid` |
| Exception nghiệp vụ trả `500` | Chưa map custom exception | Thêm `@ExceptionHandler` với status/type rõ |
| Security error có HTML hoặc response khác | Exception xảy ra trong filter chain trước MVC | Cấu hình security handler/gateway riêng |
| `@RestControllerAdvice` không chạy | Package scan hoặc scope, thứ tự/xung đột handler | Kiểm tra bean, `@Order`, stack trace |
| `406` hoặc `415` ngoài ý muốn | `Accept`/`Content-Type` không phù hợp | Kiểm tra media type, converter và endpoint mapping |
| `500` lộ SQL hoặc stack trace | Trả `ex.getMessage()` thẳng vào `detail` | Thay thông điệp chung, ghi exception ở log nội bộ |
| Client parse lỗi theo `detail` không ổn định | Client dựa vào văn bản bản địa hóa | Chuyển sang `type`/`code` |
| Lỗi RFC bị double-wrap | Global `ResponseBodyAdvice` tác động cả `ProblemDetail` | Loại trừ ErrorResponse/ProblemDetail đúng phạm vi |
| `instance` lộ tokens | Gắn nguyên URL và query vào response | Dùng path/opaque occurrence ID an toàn |
| Thêm extension làm SDK cũ hỏng | Client closed schema không bỏ qua field mới | Có contract test và versioning chính sách |

Một quy trình kiểm tra nhanh:

1. Gửi request bằng `curl -i` để xem **HTTP status và `Content-Type` thực**.
2. Xác định lỗi sinh từ argument resolver, validation, controller/service, MVC handler hay filter/gateway.
3. Kiểm tra bean `@ControllerAdvice`, thứ tự và handlers của `ResponseEntityExceptionHandler`.
4. Kiểm tra `type`, `title`, `status`, `detail`, `instance` và extensions có đúng contract không.
5. Kiểm tra nguyên nhân server-side qua log/traces không chứa bí mật; không phơi stack trace.
6. Chạy contract tests cho ít nhất một lỗi nghiệp vụ, validation, malformed JSON và unexpected 500.
7. Kiểm tra cả client cũ với error schema mới, đặc biệt nếu từng dùng error DTO tự định nghĩa.

## 12. Quy tắc thiết kế hợp đồng lỗi bền vững

Một API dùng Problem Details nên có ít nhất:

- **Danh mục problem types:** URI, title và HTTP status phù hợp với từng loại vấn đề; các extension field được công bố.
- **Quy tắc status rõ:** `400` validation, `404` không tìm thấy, `409` xung đột, `500` lỗi server — điều chỉnh theo nghiệp vụ nhưng nhất quán.
- **Quy tắc nội dung bảo mật:** chi tiết công khai an toàn, không leak secrets/stack/internal identifiers.
- **Mã ổn định cho machine consumers:** ưu tiên `type`; bổ sung `code` nếu contract cần.
- **Validation extension schema:** dùng `errors` một cách nhất quán, tránh khác shape giữa các endpoint.
- **Locale policy:** title/detail có thể bản địa hóa, type/code không đổi.
- **Correlation ID:** nếu cần, liên kết response với log/traces; không bịa ID không thể tra.
- **Kiểm thử ngược:** giữ fixtures hoặc OpenAPI schema đã phát hành; tránh làm hỏng clients đọc `application/problem+json`.
- **Ngoại lệ có chủ đích:** proxy/security/streaming/legacy response không theo cùng MVC pipeline cần chính sách riêng.
- **Một nơi sở hữu policy:** tránh nhiều advice toàn cục cùng rewrite lỗi không dự đoán được.

## 13. Bài tập kiểm tra kiến thức

1. `ProblemDetail.type` và `ProblemDetail.instance` khác nhau ở điểm nào?
2. Một endpoint trả `HTTP 200 OK` nhưng body `{"status":404}`. Vì sao đây là hợp đồng sai?
3. `ErrorResponseException` khác gì với `ProblemDetail` chỉ là dữ liệu?
4. Lỗi `@Valid @RequestBody` nên được bắt bởi method nào của `ResponseEntityExceptionHandler` trong ví dụ?
5. Vì sao `@RestControllerAdvice` không bảo đảm thay thế mọi response lỗi của Spring Security/gateway?
6. `setProperty("code", "...")` xuất hiện ở đâu trong JSON khi dùng Jackson/Spring?
7. `detail` và `title` có nên là mã ổn định mà frontend parse bằng cách so chuỗi không?
8. Khi nào nên dùng `409 Conflict` thay vì `400 Bad Request`?
9. Vì sao `ProblemDetail` không thể thay validation, authorization hay business rules?
10. Nếu bật `spring.mvc.problemdetails.enabled=true` đồng thời có advice kế thừa `ResponseEntityExceptionHandler`, bạn cần kiểm tra điều gì?
11. Nếu API hỗ trợ đa ngôn ngữ, field nào nên thay đổi theo locale, field nào không?
12. Vì sao không nên trả `FieldError.getRejectedValue()` và `Exception.getMessage()` tùy ý trong body lỗi?

**Gợi ý trả lời:** (1) `type` định danh loại lỗi, `instance` định danh occurrence. (2) HTTP status thật báo thành công trong khi body báo lỗi. (3) Exception mang status/headers/body theo `ErrorResponse`; `ProblemDetail` là object biểu diễn. (4) `handleMethodArgumentNotValid`. (5) Lỗi có thể xảy ra ngoài MVC handler resolver chain. (6) Extension top-level JSON. (7) Không, dùng type/code. (8) Khi xung đột trạng thái tài nguyên khiến request hiện tại không được thực hiện. (9) Đây chỉ là error representation. (10) Thứ tự và xung đột handler. (11) title/detail có thể dịch; type/code/status giữ ngữ nghĩa. (12) Có thể lộ dữ liệu nhạy cảm và implementation details.

## 14. Tài liệu tham khảo

- [RFC 9457 — Problem Details for HTTP APIs, IETF](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Spring Framework — Error Responses (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.1.21 — ProblemDetail Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework 6.1.21 — ErrorResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework 6.1.21 — ErrorResponseException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/ErrorResponseException.html)
- [Spring Framework 6.1 — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot — Servlet Web Applications: Problem Details](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)

Tất cả code thuộc ví dụ Spring MVC/Jackson, không áp dụng nguyên vẹn cho WebFlux. HTTP payloads là ví dụ hợp đồng có thể kiểm tra bằng `curl`/`MockMvc`; status mặc định, error text và headers bên ngoài code ví dụ vẫn có thể khác theo môi trường, locale và cấu hình.
