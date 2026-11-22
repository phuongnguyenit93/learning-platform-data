# Phân biệt lỗi đọc JSON với lỗi chuyển đổi tham số trong Spring Boot MVC

## 1. Vấn đề và mục tiêu

Khi xây dựng REST API với Spring Boot, có nhiều trường hợp client gửi dữ liệu đầu vào không hợp lệ và nhận **HTTP 400 Bad Request**. Hai lỗi dễ bị đánh đồng nhất là:

1. **Lỗi đọc body JSON**: Spring MVC không thể đọc/giải mã HTTP request body thành kiểu Java mà `@RequestBody` yêu cầu. Trường hợp thường gặp có `HttpMessageNotReadableException`.
2. **Lỗi chuyển đổi tham số**: Spring MVC đã tìm được giá trị từ URL path, query string, header hoặc cookie nhưng không thể chuyển sang kiểu tham số Java, chẳng hạn `"abc"` thành `long`. Trường hợp phổ biến có `MethodArgumentTypeMismatchException`.

Chúng có thể cùng trả 400, nhưng **đường xử lý, ngoại lệ, lớp cần tùy chỉnh và hướng khắc phục khác nhau**. Một JSON hoàn toàn hợp lệ về *cú pháp* vẫn có thể thất bại lúc ánh xạ sang kiểu Java. Ngược lại, một query parameter không phải JSON nên không cần JSON parser.

Bài tập trung vào **Spring MVC Servlet stack**, ví dụ Spring Boot 3.5.16 + Java 17+, `spring-boot-starter-web`. Phần cuối phân biệt ngắn với Spring WebFlux vì hai stack có API giải mã và ngoại lệ không hoàn toàn trùng nhau.

## 2. Bản đồ dữ liệu đầu vào và chỗ phát sinh lỗi

~~~text
HTTP request
  |
  +-- request line: POST /orders/abc?page=no HTTP/1.1
  |      |
  |      +-- path/query/header/cookie -> HandlerMethodArgumentResolver
  |                                      -> ConversionService/WebDataBinder
  |                                      -> lỗi chuyển đổi tham số nếu sai kiểu
  |
  +-- headers: Content-Type: application/json
  |      |
  |      +-- chọn HttpMessageConverter phù hợp với media type và kiểu đích
  |               |
  |               +-- không có converter phù hợp: thường 415
  |
  +-- body: {"quantity":"not-a-number"}
         |
         +-- @RequestBody -> HttpMessageConverter (thường Jackson)
                              |
                              +-- JSON sai cú pháp / không đọc được body
                              +-- JSON hợp lệ nhưng không tạo được Java object
                              |      -> thường HttpMessageNotReadableException
                              |
                              +-- tạo Java object thành công
                                     |
                                     +-- @Valid / Bean Validation
                                            -> thường MethodArgumentNotValidException
                                     |
                                     +-- gọi controller
~~~

Đây là bản đồ khái quát, không phải toàn bộ nội bộ framework; Spring MVC có nhiều resolver và converter với các điều kiện khác nhau. Nếu handler mapping đã từ chối request do `consumes` không khớp, lỗi 415 còn có thể xuất hiện **trước khi bắt đầu đọc body**.

### Hai cách viết controller gây hai nhánh khác nhau

~~~java
@PostMapping("/orders")
public OrderResponse create(@RequestBody CreateOrderRequest input) {
    // Đọc HTTP body theo media type, thường dùng Jackson cho JSON.
}

@GetMapping("/orders/{id}")
public OrderResponse find(@PathVariable("id") long id,
                          @RequestParam("page") int page) {
    // Lấy giá trị dạng text từ path/query rồi chuyển sang long/int.
}
~~~

Các method trên là **minh họa**, chưa đủ class và import để chạy độc lập. Đối với `@RequestBody`, dữ liệu phải đi qua `HttpMessageConverter`; đối với `@PathVariable` hoặc `@RequestParam`, MVC thường lấy chuỗi từ request và chuyển kiểu qua `ConversionService`/binder.

## 3. Lỗi đọc JSON: HttpMessageNotReadableException

### 3.1. Đường đi của @RequestBody

Khi method nhận `@RequestBody CreateOrderRequest request`, Spring MVC thường dùng `RequestResponseBodyMethodProcessor` để đọc body bằng một `HttpMessageConverter` phù hợp. Với JSON và Jackson trên classpath, converter JSON chuyển stream bytes thành đối tượng Java.

~~~text
Content-Type: application/json
           |
           v
HttpMessageConverter được chọn
           |
           v
Jackson đọc tokens -> ánh xạ properties/constructor/record
           |
           +-- thành công: tạo CreateOrderRequest
           +-- thất bại: HttpMessageNotReadableException
~~~

Những trường hợp có thể dẫn tới `HttpMessageNotReadableException`:

- **JSON sai cú pháp**: thiếu ngoặc, thiếu dấu phẩy, có token không hợp lệ.
- **JSON không đúng cấu trúc Java mong đợi**: gửi mảng trong khi yêu cầu một object; gửi object trong khi cần scalar, tùy cấu hình.
- **Giá trị của JSON không thể deserialize thành kiểu Java**: chẳng hạn trường `quantity` khai báo `int` nhưng body có `"quantity":"abc"`.
- **Enum/date/custom deserializer thất bại**: JSON có thể hợp lệ nhưng định dạng không phù hợp với kiểu hoặc chính sách Jackson.
- **Thiếu body bắt buộc** với `@RequestBody(required = true)`, khi pipeline không có nội dung để đọc.

**Lưu ý:** ngoại lệ này mô tả lỗi *đọc HTTP message*, không chỉ lỗi cú pháp JSON. Các media type/converter khác cũng có thể phát sinh ngoại lệ tương tự. Trong ứng dụng REST JSON, nó là dấu hiệu hữu ích để phân biệt với lỗi query/path.

### 3.2. JSON hợp lệ không có nghĩa là DTO tạo được

Giả sử Java có:

~~~java
public record CreateOrderRequest(String product, int quantity) {
}
~~~

Body thứ nhất là JSON **không hợp lệ**:

~~~json
{"product":"book","quantity":
~~~

Body thứ hai có JSON **hợp lệ** nhưng không tạo được record theo cách ánh xạ thông thường:

~~~json
{"product":"book","quantity":"many"}
~~~

Hai body có nguyên nhân kỹ thuật khác nhau ở Jackson, nhưng MVC thường biểu diễn chúng bằng `HttpMessageNotReadableException` ở ranh giới `@RequestBody`. Vì vậy một error handler chung có thể trả mã nghiệp vụ `INVALID_JSON_BODY`; nếu cần tách nhỏ, có thể phân loại nested cause (ví dụ lỗi parse và lỗi mapping), nhưng không nên phụ thuộc vào toàn bộ text thông báo của Jackson.

Body hợp lệ:

~~~json
{"product":"book","quantity":2}
~~~

có thể tạo record thành công; việc bản ghi hợp lệ về quy tắc nghiệp vụ hay không là **bước khác**, ví dụ Bean Validation.

### 3.3. Kiểu của đối số quyết định có parse JSON hay không

Không được kết luận rằng mọi method có `@RequestBody` đều parse JSON thành object. Ví dụ:

~~~java
@PostMapping("/raw")
String raw(@RequestBody String input) {
    return input;
}
~~~

Đây là method minh họa. `StringHttpMessageConverter` có thể nhận toàn bộ body dưới dạng chuỗi thay vì gọi Jackson để kiểm tra cú pháp JSON, tùy converter/media type. Khi đó chuỗi `{"a":` có thể đi vào method như text. Muốn kiểm tra JSON phải deserialize/validate một kiểu đích JSON thích hợp hoặc chủ động parse theo yêu cầu.

### 3.4. HTTP 400 hay 415?

Khi header `Content-Type` không được converter/handler hỗ trợ, như gửi `text/plain` đến endpoint chỉ xử lý JSON DTO, Spring MVC thường trả **415 Unsupported Media Type** qua `HttpMediaTypeNotSupportedException`. Đây là **lỗi lựa chọn media type**, không phải lỗi parse JSON.

Khi header là `application/json`, converter JSON được chọn nhưng payload không parse/map được, thường trả **400 Bad Request** qua `HttpMessageNotReadableException`.

Đừng dùng một error code `INVALID_JSON` để che mọi lỗi 400/415: client cần biết phải sửa **Content-Type**, **cấu trúc body**, hay **giá trị query/path**.

## 4. Lỗi chuyển đổi tham số: MethodArgumentTypeMismatchException

### 4.1. Đường đi của @PathVariable / @RequestParam

~~~java
@GetMapping("/orders/{id}")
String find(@PathVariable("id") long id,
            @RequestParam("page") int page) {
    return id + ":" + page;
}
~~~

Với request `GET /orders/not-a-number?page=1`:

1. Router chọn mapping `/orders/{id}`.
2. Resolver của `@PathVariable` lấy chuỗi `"not-a-number"`.
3. Spring MVC dùng conversion service/binder để chuyển thành `long`.
4. Chuyển đổi thất bại và có thể ném `MethodArgumentTypeMismatchException` trước khi controller chạy.

Với `GET /orders/42?page=wrong`, tương tự nhưng tham số lỗi là `page` kiểu `int`.

Các đối số khác cũng đi qua conversion cơ bản khi cần: `@RequestHeader`, `@CookieValue`, `@MatrixVariable`, một số `@RequestParam` kiểu UUID, Boolean, Enum, LocalDate, v.v.

### 4.2. Ngoại lệ mang những thông tin gì?

Trong Spring MVC, `MethodArgumentTypeMismatchException` (package `org.springframework.web.method.annotation`) kế thừa từ `TypeMismatchException`. Nó thường cung cấp:

- `getName()`: tên đối số method, như `"page"` hoặc `"id"`.
- `getValue()`: giá trị đầu vào gây lỗi (có thể nhạy cảm).
- `getRequiredType()`: class đích như `int`/`long`.
- `getParameter()`: metadata của `MethodParameter`.
- `getCause()`: nguyên nhân conversion ở bên dưới.

Trả tên field và thông điệp an toàn cho client thường hữu ích. **Không trả nguyên `getValue()`, `getCause().getMessage()` hoặc stack trace** nếu dữ liệu có thể chứa thông tin cá nhân, token hay chi tiết implementation.

### 4.3. Thiếu tham số không phải lỗi chuyển đổi

Request `GET /orders/42` trong khi controller yêu cầu `@RequestParam("page") int page` có thể ném `MissingServletRequestParameterException`. Không có chuỗi `page` để convert, nên không nên phân loại là `MethodArgumentTypeMismatchException`.

Tương tự, header bắt buộc bị thiếu có thể là `MissingRequestHeaderException`, cookie thiếu là `MissingRequestCookieException`. Những trường hợp required argument bị chuyển thành `null` sau conversion cũng có thể được Spring xử lý dưới dạng missing-argument exception tùy annotation và kiểu đích.

### 4.4. Custom converter và formatter

Nếu một value object từ URI/query cần cách convert mới, đăng ký `Converter` hoặc `Formatter` cho MVC qua `WebMvcConfigurer.addFormatters`, không viết Jackson deserializer chỉ để sửa `@PathVariable`.

Ví dụ extension:

~~~java
@Configuration
class MvcConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, OrderCode.class,
                text -> new OrderCode(text));
    }
}
~~~

Đây là **trích đoạn minh họa**, cần record `OrderCode` và các import. Nó chỉ giúp chuyển nguồn String cho những tham số phù hợp; không có nghĩa Jackson tự động dùng converter đó để decode `@RequestBody`. Đầu vào JSON thông thường cần cấu hình `ObjectMapper`, module, annotation Jackson hoặc custom deserializer đúng cách.

Đối với `LocalDate` trong query, Spring MVC hỗ trợ `@DateTimeFormat` và các formatter. Đối với field ngày trong JSON DTO, cơ chế Jackson như `@JsonFormat` và module Java Time mới là điều cần cân nhắc.

## 5. Bảng tra lỗi thường gặp

| Request/sự cố | Đường xử lý chính | Ngoại lệ điển hình | HTTP mặc định thường gặp |
|---|---|---|---|
| `@RequestBody` nhận JSON thiếu dấu đóng | JSON message converter | `HttpMessageNotReadableException` | 400 |
| JSON hợp lệ nhưng `int quantity` nhận `"abc"` | Jackson JSON → Java | `HttpMessageNotReadableException` | 400 |
| `@RequestBody(required=true)` không có body | Body resolver/converter | `HttpMessageNotReadableException` | 400 |
| JSON đúng kiểu nhưng `@Valid` vi phạm `@Min` | Bean Validation sau deserialize | `MethodArgumentNotValidException` | 400 |
| `@RequestParam int page` nhận `page=abc` | MVC ConversionService | `MethodArgumentTypeMismatchException` | 400 |
| `@PathVariable long id` nhận `id=nope` | MVC ConversionService | `MethodArgumentTypeMismatchException` | 400 |
| `@RequestParam page` bắt buộc bị thiếu | Argument resolver | `MissingServletRequestParameterException` | 400 |
| `@RequestHeader` bắt buộc bị thiếu | Header resolver | `MissingRequestHeaderException` | 400 |
| Body có `Content-Type: text/plain` nhưng handler/converter chỉ nhận JSON DTO | Media type mapping/converter | `HttpMediaTypeNotSupportedException` | 415 |
| `Accept` yêu cầu kiểu response mà server không thể cung cấp | Response content negotiation | `HttpMediaTypeNotAcceptableException` | 406 |
| `@ModelAttribute` form field sai kiểu | Data binder + BindingResult | Có thể là lỗi binding/`MethodArgumentNotValidException` tùy chữ ký | Thường 400 hoặc method tự xử lý `BindingResult` |
| Constraint trực tiếp trên controller method param bị vi phạm | Method validation | `HandlerMethodValidationException` | Thường 400 đối với request input |

Bảng mô tả **hành vi mặc định điển hình** trong Spring MVC hiện đại. Global exception handler, `@ControllerAdvice`, `BindingResult`, method signature, converter tùy biến, Spring Security và Spring Boot configuration có thể thay đổi cách biểu diễn response.

**Quan trọng:** không coi tất cả `TypeMismatchException` của ứng dụng là lỗi của một controller parameter. Type mismatch có thể xuất hiện ở các cơ chế binding khác. Handler `MethodArgumentTypeMismatchException` cụ thể giúp tránh bắt quá rộng.

## 6. Phân biệt với validation và lỗi nghiệp vụ

Lỗi JSON/body conversion, lỗi tham số, lỗi validation và lỗi nghiệp vụ là bốn giai đoạn khác nhau.

**Giai đoạn A — Decode/deserialize:** JSON có đọc được không? Có thể tạo Java object không?

~~~json
{"product":"book","quantity":"many"}
~~~

Nếu Java cần `int quantity`, JSON này hợp lệ cú pháp nhưng deserialize không thành công. Controller chưa được gọi.

**Giai đoạn B — Conversion của URL/header:** query `?page=xyz` có đổi được thành `int` hay không? Nếu không, controller chưa được gọi.

**Giai đoạn C — Validation trên object đã tạo:** body:

~~~json
{"product":"book","quantity":0}
~~~

vẫn map được vào Java record, nhưng nếu field có `@Min(1)` và method có `@Valid`, nó vi phạm constraint, thường dẫn đến `MethodArgumentNotValidException`. Không nên gọi đó là lỗi JSON parser.

**Giai đoạn D — Business rule:** body hợp lệ và pass validation, nhưng sản phẩm đã hết hàng hoặc đơn hàng không được phép chuyển trạng thái. Đây là quyết định nghiệp vụ của service/controller, có thể trả 409 hoặc 422 theo hợp đồng API. Framework **không tự chọn 422** chỉ vì một field không thỏa luật nghiệp vụ.

Với direct `@Min`/`@NotBlank` đặt trên method parameters, Spring Framework 6.1+ còn có `HandlerMethodValidationException`. Đừng viết handler chỉ bắt `MethodArgumentNotValidException` rồi mặc định nó bao trùm mọi validation.

## 7. Ví dụ hoàn chỉnh: Spring Boot 3.5.16, Java 17+, Maven

Bài demo dựng một REST controller có hai endpoint:

- `POST /api/orders`: nhận JSON body qua `@Valid @RequestBody`.
- `GET /api/orders/{orderId}?page=...`: nhận path/query, convert sang `long` và `int`.

Thêm `@RestControllerAdvice` để trả **hai error codes khác nhau** cho lỗi đọc JSON và lỗi chuyển đổi tham số. Các lỗi validation và 415 được để Spring MVC xử lý mặc định để thấy chúng là nhánh riêng.

### 7.1. Cấu trúc thư mục

~~~text
request-error-demo/
  pom.xml
  src/
    main/
      java/com/example/inputerrors/
        RequestErrorApplication.java
        OrderController.java
        RequestErrorAdvice.java
    test/
      java/com/example/inputerrors/
        RequestErrorMvcTest.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>request-error-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>

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

Ví dụ sử dụng Spring Boot 3.5.16 để đảm bảo nhất quán API và package. Dự án production cần chọn dòng Boot còn được hỗ trợ và cập nhật theo chính sách bảo mật; khi nâng sang 4.x, rà soát starter, cấu trúc module, API và tests.

### 7.3. Entry point

File `src/main/java/com/example/inputerrors/RequestErrorApplication.java`:

~~~java
package com.example.inputerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestErrorApplication.class, args);
    }
}
~~~

### 7.4. REST controller và record DTO

File `src/main/java/com/example/inputerrors/OrderController.java`:

~~~java
package com.example.inputerrors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    public record CreateOrderRequest(
            @NotBlank String product,
            @Min(1) int quantity) {
    }

    public record CreateOrderResponse(String product, int quantity) {
    }

    @PostMapping("/api/orders")
    public CreateOrderResponse create(
            @Valid @RequestBody CreateOrderRequest request) {
        return new CreateOrderResponse(
                request.product(), request.quantity());
    }

    @GetMapping("/api/orders/{orderId}")
    public String read(
            @PathVariable("orderId") long orderId,
            @RequestParam("page") int page) {
        return "orderId=" + orderId + ";page=" + page;
    }
}
~~~

Giải thích:

- Đối với `create`, Spring đọc body, Jackson tạo `CreateOrderRequest`, validation mới kiểm tra `@NotBlank`/`@Min`. Method chỉ được gọi khi các bước đầu vào cần thiết thành công.
- Đối với `read`, MVC lấy path/query từ URL, chuyển sang `long`/`int` và mới gọi method. Body JSON không tham gia luồng này.
- Trả về một record tự động được Jackson serialize thành JSON khi converter và content negotiation hỗ trợ. Ví dụ không chứa database; tác dụng chính là tách các kiểu lỗi request.

### 7.5. Global advice: hai error codes riêng

File `src/main/java/com/example/inputerrors/RequestErrorAdvice.java`:

~~~java
package com.example.inputerrors;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class RequestErrorAdvice {

    public record ApiError(
            String code, String field, String message) {
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadableBody(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_JSON_BODY",
                        "body",
                        "Request body không đọc được hoặc không khớp kiểu dữ liệu"));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidParameter(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_PARAMETER",
                        ex.getName(),
                        "Tham số không thể chuyển sang kiểu yêu cầu"));
    }
}
~~~

**Điểm cần chú ý:**

- Hai `@ExceptionHandler` bắt **hai loại exception khác nhau**. Cùng HTTP 400 nhưng JSON error có `code` riêng để frontend hướng dẫn người dùng chính xác hơn.
- Handler không trả lại body lỗi, raw query, stack trace hay `ex.getMostSpecificCause().getMessage()`. Đây là lựa chọn an toàn khi có thể chứa dữ liệu nhạy cảm.
- `ex.getName()` là tên tham số Java như `orderId` hoặc `page`. Nếu muốn bảo đảm contract với tên public của `@PathVariable`/`@RequestParam`, cần kiểm tra metadata annotation và quy tắc mapping của hệ thống.
- Bài demo không bắt `MethodArgumentNotValidException`, `HttpMediaTypeNotSupportedException` và exception khác. Điều đó **cố ý**: chúng được Spring Boot/MVC xử lý mặc định; client không nên kỳ vọng mọi response lỗi đều có cấu trúc `ApiError` khi chưa bổ sung policy chung.
- Không nên dùng `@ExceptionHandler(Exception.class)` để biến mọi lỗi thành 400. Bugs, database error, timeouts hoặc exceptions server-side cần được phân loại đúng.
- Khi bật Problem Details hoặc có nhiều `@ControllerAdvice`, cần kiểm tra thứ tự advice để không có hai handler cùng tranh chấp. Với project mẫu, cấu hình mặc định đơn giản và advice này xử lý trực tiếp hai exception mục tiêu.

### 7.6. Chạy và gọi bằng curl

Trong thư mục project có `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Nếu project đã tạo Maven Wrapper thì có thể dùng `./mvnw spring-boot:run` hoặc `mvnw.cmd spring-boot:run` trên Windows.

**JSON đúng:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":2}'
~~~

Dự kiến HTTP **200 OK** và body JSON tương đương:

~~~json
{"product":"book","quantity":2}
~~~

Whitespace/ordering trong serialized JSON không phải hợp đồng cứng; hai trường có giá trị như trên mới là điều cần kiểm tra.

**JSON sai cú pháp:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":'
~~~

Dự kiến HTTP **400** và body do advice tạo:

~~~json
{
  "code": "INVALID_JSON_BODY",
  "field": "body",
  "message": "Request body không đọc được hoặc không khớp kiểu dữ liệu"
}
~~~

**JSON hợp lệ nhưng không map được quantity thành int:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":"many"}'
~~~

Dự kiến HTTP **400**, cùng `code=INVALID_JSON_BODY`. Không được gọi đây là `MethodArgumentTypeMismatchException` chỉ vì tên field có kiểu `int`: nguồn dữ liệu nằm trong **JSON body**, qua Jackson.

**Path parameter sai kiểu:**

~~~bash
curl -i "http://localhost:8080/api/orders/abc?page=1"
~~~

Dự kiến HTTP **400**, body:

~~~json
{
  "code": "INVALID_PARAMETER",
  "field": "orderId",
  "message": "Tham số không thể chuyển sang kiểu yêu cầu"
}
~~~

**Query parameter sai kiểu:**

~~~bash
curl -i "http://localhost:8080/api/orders/42?page=xyz"
~~~

Dự kiến HTTP **400**, `code=INVALID_PARAMETER`, `field=page`.

**Query parameter thiếu:**

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Dự kiến HTTP **400** do missing parameter, nhưng body có thể **khác** cấu trúc custom `ApiError` vì demo không định nghĩa handler cho `MissingServletRequestParameterException`.

**Body map được nhưng validation không đạt:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":0}'
~~~

Dự kiến HTTP **400** từ Bean Validation, không phải `INVALID_JSON_BODY`. Nếu cần hợp đồng lỗi thống nhất, bổ sung xử lý `MethodArgumentNotValidException`.

**Sai Content-Type:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: text/plain" \
  -d '{"product":"book","quantity":2}'
~~~

Dự kiến **415 Unsupported Media Type** vì dữ liệu gửi đến endpoint `@RequestBody CreateOrderRequest` không có converter thích hợp cho `text/plain` theo cấu hình mặc định.

Dùng `curl -i` có cả status line, header và body; các JSON block trên chỉ minh họa **body** được tạo, không phải toàn bộ output của curl.

## 8. MockMvc tests: kiểm chứng hai lỗi thật sự khác nhánh

MockMvc gọi Spring MVC pipeline mà không phải bind TCP port. Để test cả converter, argument resolver và advice trong cùng context, dùng `@SpringBootTest` + `@AutoConfigureMockMvc` của Boot 3.5.

File `src/test/java/com/example/inputerrors/RequestErrorMvcTest.java`:

~~~java
package com.example.inputerrors;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
class RequestErrorMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validJsonIsAccepted() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.product").value("book"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void malformedJsonIsReportedAsBodyError() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON_BODY"))
                .andExpect(jsonPath("$.field").value("body"));
    }

    @Test
    void validJsonWithWrongFieldTypeIsAlsoBodyError() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":\"many\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON_BODY"));
    }

    @Test
    void invalidPathVariableIsArgumentTypeMismatch() throws Exception {
        mvc.perform(get("/api/orders/abc").param("page", "1"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.field").value("orderId"));
    }

    @Test
    void invalidQueryParameterIsArgumentTypeMismatch() throws Exception {
        mvc.perform(get("/api/orders/42").param("page", "wrong"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.field").value("page"));
    }

    @Test
    void validPathAndQueryAreAccepted() throws Exception {
        mvc.perform(get("/api/orders/42").param("page", "3"))
                .andExpect(status().isOk())
                .andExpect(content().string("orderId=42;page=3"));
    }

    @Test
    void missingQueryParamIsNotTypeMismatch() throws Exception {
        mvc.perform(get("/api/orders/42"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void jsonValidationErrorIsNotJsonReadFailure() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedContentTypeIsNotMalformedJson() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("{\"product\":\"book\",\"quantity\":2}"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Khi đủ dependencies, nhóm test này phân biệt 400 của body decoding với 400 của path/query conversion, 400 của validation, 400 của tham số bị thiếu và 415 của media type. Các test chỉ kiểm tra body `ApiError` ở những trường hợp advice mẫu chủ động quản lý, tránh phụ thuộc vào thông điệp mặc định của Boot.

Trong project thật, cũng nên kiểm tra status/error code qua HTTP integration test `RANDOM_PORT`, vì MockMvc không kiểm tra TCP stack, reverse proxy, TLS hay HTTP client thực tế.

## 9. Thiết kế hợp đồng lỗi API có cấu trúc

Thay vì trả thông báo exception của thư viện một cách tùy tiện, backend nên cung cấp các trường ổn định để client xử lý:

| Field | Ví dụ | Lưu ý |
|---|---|---|
| `code` | `INVALID_JSON_BODY`, `INVALID_PARAMETER`, `VALIDATION_ERROR` | Ổn định và có tài liệu |
| `message` | Thông điệp ngắn cho con người | Không chứa stack trace, SQL, token, nguyên body |
| `field` hoặc `errors[]` | `page`, `orderId`, `quantity` | Chỉ lộ metadata được cho phép |
| `requestId` | ID từ hệ thống tracing | Dùng để tra log nội bộ, không lộ secrets |
| `status` | 400, 415, 422 theo hợp đồng | Không đưa mọi lỗi vào một mã nếu nguyên nhân khác |

**Một contract thống nhất không đồng nghĩa một mã lỗi duy nhất.** Hệ thống có thể cùng dùng HTTP 400 cho JSON và query conversion nhưng `code` nghiệp vụ riêng. Không nên expose nguyên `JsonMappingException.getPathReference()` nếu DTO chứa field nhạy cảm hoặc internal class names.

### Problem Details theo RFC 9457

Spring Framework hỗ trợ `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler` để biểu diễn lỗi chuẩn (thường có `type`, `title`, `status`, `detail`, `instance`).

Với Spring Boot 3.5, có thể chọn hỗ trợ built-in cho Spring MVC bằng:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Khi bật, Boot có thể auto-configure `ResponseEntityExceptionHandler` xử lý built-in MVC exceptions. Nếu ứng dụng đồng thời có `@ControllerAdvice` tự bắt các exception này, cần xem **thứ tự advice và phạm vi bắt lỗi**, đặc biệt nếu muốn advice custom có ưu tiên cao hơn cấu hình mặc định của Boot (thường order 0). Demo ở trên không bật flag này để tách đơn giản hai loại exception.

Ngoài ra có thể chọn **toàn bộ contract là `ProblemDetail`** thay vì record `ApiError`. Ví dụ trích đoạn riêng cho một `@ExceptionHandler`:

~~~java
ProblemDetail problem = ProblemDetail.forStatus(
        HttpStatus.BAD_REQUEST);
problem.setTitle("Invalid request parameter");
problem.setDetail("A query or path parameter has an invalid type");
problem.setProperty("code", "INVALID_PARAMETER");
return problem;
~~~

Đây là đoạn minh họa, cần import `ProblemDetail`, `HttpStatus` và đặt trong method handler. `ProblemDetail` có thể được Spring serialize dưới media type `application/problem+json` khi converter được cấu hình phù hợp.

Nếu đã extend `ResponseEntityExceptionHandler`, ưu tiên override các protected handler hooks phù hợp thay vì khai báo trùng `@ExceptionHandler` cho cùng built-in exception theo cách gây ambiguity.

## 10. Cách debug nhanh theo đường dữ liệu

### 10.1. Khi POST JSON trả 400

Kiểm tra theo thứ tự:

1. `Content-Type` có là `application/json` hoặc một kiểu được converter hỗ trợ không?
2. Body bytes/encoding có hợp lệ không? Có bị filter/gateway đọc mất trước `@RequestBody` không?
3. JSON syntax có hợp lệ không?
4. Cấu trúc JSON có match DTO/record, property names và constructor không?
5. Enum/date/number hoặc custom deserializer có convert được không?
6. Nếu decode thành công, có constraint `@Valid`/method validation nào thất bại không?
7. Xem **exception type đầu tiên có ý nghĩa** trong log; không suy ra lỗi từ việc thấy mỗi status 400.

Bước 1 có thể phát hiện 415 thay vì 400; bước 6 chỉ ra validation, không phải JSON parser.

### 10.2. Khi GET path/query trả 400

Kiểm tra:

1. Handler mapping có match path và HTTP method không?
2. Giá trị `@PathVariable` hoặc `@RequestParam` có hiện diện không?
3. Giá trị được URL-encode đúng chưa? Ví dụ dấu `+` trong query có thể được diễn giải khác với dấu cộng literal.
4. Kiểu Java cần gì: `int`, `UUID`, `LocalDate`, `Enum`?
5. `ConversionService`, `@DateTimeFormat`, `Converter` hoặc formatter riêng có đang áp dụng không?
6. Ngoại lệ là `MethodArgumentTypeMismatchException` hay `MissingServletRequestParameterException` hoặc một lỗi binding khác?

Ví dụ: `GET /api/orders/42?page=abc` không có JSON body, nên sửa `ObjectMapper` sẽ không giải quyết được lỗi này.

### 10.3. Phân biệt lỗi trên wire với nested cause

Khi Jackson không parse được JSON, nested cause có thể là `JsonParseException`, `JsonMappingException` hoặc kiểu con. Tuy nhiên ở ranh giới `@RequestBody`, Spring MVC thường bọc thành `HttpMessageNotReadableException`. Khi xem log, hãy phân biệt **exception Spring MVC dùng để chọn HTTP response** với **nguyên nhân chi tiết bên trong Jackson**.

Với query/path, nested cause có thể là `NumberFormatException` hoặc conversion failure; nhưng advice phù hợp thường bắt `MethodArgumentTypeMismatchException` ở tầng MVC thay vì bắt mọi `NumberFormatException` toàn ứng dụng.

**Không bắt `RuntimeException` rồi luôn trả 400**, vì nó che cả lỗi logic, null pointer, transaction failure hoặc server bug đáng lẽ trả 500.

## 11. Các hiểu nhầm cần tránh

- **“JSON hợp lệ thì không thể có HttpMessageNotReadableException.”** Sai. JSON đúng cú pháp vẫn có thể không map được sang kiểu Java hoặc custom deserializer từ chối.
- **“Bất cứ giá trị int sai kiểu đều là MethodArgumentTypeMismatchException.”** Sai. `int` trong JSON body được giải mã qua Jackson; `int` từ query/path đi qua MVC conversion.
- **“Cả hai trả 400 nên dùng một error code.”** Không nên. Client thường cần biết sửa body hay tham số.
- **“`@Valid` là JSON parser.”** Sai. Validation diễn ra khi object/argument đã được tạo; exception có thể khác.
- **“Không có `page` là type mismatch.”** Sai. Thường thuộc nhóm missing parameter, không phải conversion.
- **“Sai `Content-Type` là JSON syntax error.”** Sai. Thường 415 do media type.
- **“Cứ dùng `Converter<String, T>` thì Jackson sẽ dùng nó cho JSON.”** Không có bảo đảm; converter MVC và Jackson deserializer thuộc những cơ chế khác nhau.
- **“`@RequestBody String` luôn kiểm tra JSON.”** Sai; string converter có thể chuyển raw body thành String.
- **“`@ModelAttribute` form field sai luôn ném MethodArgumentTypeMismatchException.”** Sai. Binding errors có thể được chứa trong `BindingResult` hoặc ném exception phù hợp chữ ký method.
- **“Vì muốn thông tin lỗi dễ debug nên trả nguyên stack trace và request body.”** Không an toàn. Ghi log nội bộ có kiểm soát, trả mã lỗi và mô tả an toàn.
- **“Spring Boot luôn trả 422 cho validation.”** Sai. Mặc định thường 400; 422 là lựa chọn contract riêng khi phù hợp.
- **“Các exception servlet MVC giống hệt WebFlux.”** Sai. WebFlux dùng reactive reader/codec và ngoại lệ được xử lý theo stack khác.

## 12. Liên hệ với Spring WebFlux

Spring WebFlux cũng nhận JSON body và convert path/query, nhưng không dùng đúng pipeline `HttpMessageConverter` Servlet MVC cho tất cả trường hợp.

| Tầng | Spring MVC | Spring WebFlux |
|---|---|---|
| Đọc `@RequestBody` | `HttpMessageConverter` | `HttpMessageReader`/reactive codecs |
| Lỗi body decoding | Thường `HttpMessageNotReadableException` | Thường `ServerWebInputException` với cause liên quan codec/decoding |
| Validation body | Thường `MethodArgumentNotValidException` | `WebExchangeBindException` trong nhiều trường hợp |
| Query/path conversion | ConversionService/binder theo MVC | Reactive controller argument resolvers và ConversionService |
| Error advice | MVC `@RestControllerAdvice`, MVC exception types | WebFlux advice/error handling với exception types phù hợp |
| Problem Details property | `spring.mvc.problemdetails.enabled` | `spring.webflux.problemdetails.enabled` |

Đừng copy một `@ExceptionHandler(HttpMessageNotReadableException.class)` từ dự án MVC sang WebFlux và mặc định nó sẽ xử lý mọi JSON decoding error. Với WebFlux, kiểm tra `ServerWebInputException`, `DecodingException`, `WebExchangeBindException`, `WebExceptionHandler` và kiểu tham số reactive cụ thể của endpoint.

Bài demo vẫn cố ý dùng Spring MVC để thấy rõ hai exception đích; không thêm `spring-boot-starter-webflux` vào project khi không cần.

## 13. Checklist cho API production

1. **Chuẩn hóa lỗi theo nguồn dữ liệu:** JSON body, path/query/header, validation, Content-Type và business rules không nhập một.
2. **Chọn HTTP status có ý nghĩa:** 400 cho input sai theo default, 415 cho media type không hỗ trợ, 404 cho resource không có, 409 cho xung đột trạng thái, 500 cho lỗi server. Không suy ra mọi trường hợp tuyệt đối chỉ từ exception class.
3. **Thiết kế error code ổn định:** `INVALID_JSON_BODY`, `INVALID_PARAMETER`, `MISSING_PARAMETER`, `VALIDATION_ERROR`, `UNSUPPORTED_MEDIA_TYPE`.
4. **Giữ message an toàn:** không trả raw body/secret, nội dung stack trace, đường dẫn class nội bộ hoặc SQL.
5. **Tùy chỉnh đúng tầng:** Jackson/`HttpMessageConverter` cho JSON, MVC `ConversionService` cho query/path, Bean Validation cho constraint, service cho business rules.
6. **Thử cả JSON syntax và JSON mapping:** nhiều test suite chỉ có JSON thiếu dấu ngoặc mà không kiểm tra body có sai kiểu.
7. **Thử path/query chuyển đổi:** invalid number, invalid UUID/enum/date, missing required param, required=false và `Optional`.
8. **Thử Content-Type và Accept:** đảm bảo 415/406 không bị handler chung chuyển thành 400.
9. **Thử `@Valid` và method validation:** theo đúng phiên bản Spring Framework, kiểm tra `MethodArgumentNotValidException` và `HandlerMethodValidationException` khi cần.
10. **Kiểm tra custom advice/Problem Details:** tránh handler conflict, giữ response contract nhất quán và tránh lỗi 500 do advice tự gây.
11. **Kiểm tra log và trace ID:** ghi nguyên nhân nội bộ theo chính sách bảo mật; không log toàn bộ request body chứa thông tin nhạy cảm.
12. **Rà soát khi nâng Boot/Framework:** import, starter, Jackson major version, exception behavior và format mặc định có thể thay đổi.

**Kết luận:** muốn phân biệt lỗi đúng, hãy hỏi **dữ liệu đang được lấy từ đâu và xử lý bởi thành phần nào?** Nếu từ **JSON body qua `HttpMessageConverter`**, lỗi đọc/deserialize thường là `HttpMessageNotReadableException`. Nếu từ **query/path/header qua type conversion**, lỗi chuyển kiểu thường là `MethodArgumentTypeMismatchException`. Validation và media type là hai nhóm độc lập; API nên biểu diễn đúng từng trường hợp và có test chứng minh.

## Tài liệu chính thức

- Spring Framework — `@RequestBody` và `HttpMessageConverter`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — Type Conversion của path/query/header: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — Validation và `MethodArgumentNotValidException`/`HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@ExceptionHandler`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — Error Responses / RFC 9457 Problem Details: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — `MethodArgumentTypeMismatchException` API: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/method/annotation/MethodArgumentTypeMismatchException.html
- Spring Boot 3.5 — Servlet Web Applications và Error Handling: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework — WebFlux `@RequestBody` và validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
