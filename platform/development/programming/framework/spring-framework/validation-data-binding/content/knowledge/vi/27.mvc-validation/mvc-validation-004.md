# Ràng buộc trực tiếp trên tham số controller trong Spring MVC

## 1. Từ binding dữ liệu đến kiểm tra tham số phương thức

Một handler trong Spring MVC có thể nhận dữ liệu từ URL, query string, HTTP header, cookie hoặc request body. Ngoài việc chuyển dữ liệu sang kiểu Java, ứng dụng thường cần kiểm tra các điều kiện nghiệp vụ cơ bản như:

- Mã định danh từ đường dẫn phải là số dương.
- Tham số `page` phải lớn hơn hoặc bằng 1.
- `limit` phải nằm trong khoảng cho phép.
- Từ khóa tìm kiếm không được rỗng hoặc chỉ gồm khoảng trắng.
- Một HTTP header tùy chọn ở tầng binding nhưng bắt buộc theo quy tắc Bean Validation phải có nội dung.

Trong Spring Framework 6.1 trở lên, bạn có thể gắn **Jakarta Bean Validation constraint trực tiếp lên tham số của phương thức controller**:

```java
@GetMapping("/products/{id}")
public String find(
        @PathVariable("id") @Positive long id,
        @RequestParam("page") @Min(1) int page,
        @RequestParam("keyword") @NotBlank String keyword) {

    return "id=" + id + ",page=" + page + ",keyword=" + keyword;
}
```

Đây là đoạn minh họa chữ ký handler; ứng dụng chạy đầy đủ ở mục 5. Các annotation `@Positive`, `@Min`, `@NotBlank` ở **ngay trên tham số method** là *direct constraints*. Chúng khác với việc đặt `@NotBlank` lên một field trong DTO rồi đánh dấu DTO bằng `@Valid`.

**Điểm cốt lõi:** Spring MVC 6.1+ có cơ chế **built-in method validation** cho controller. Khi có constraint trực tiếp trên tham số hoặc trên return value của handler, Spring có thể kiểm tra toàn bộ hợp đồng phương thức mà không cần thêm class-level `@Validated` để tạo AOP proxy.

## 2. Phân biệt ba vai trò annotation

Đừng coi mọi annotation trong chữ ký controller đều làm cùng một việc:

| Annotation | Vai trò |
| --- | --- |
| `@PathVariable` | Lấy một phần từ URL path và chuyển sang kiểu Java |
| `@RequestParam` | Lấy request parameter từ query/form và chuyển kiểu |
| `@RequestHeader` | Lấy giá trị HTTP header |
| `@CookieValue` | Lấy giá trị cookie |
| `@RequestBody` | Dùng HTTP message converter đọc body thành object |
| `@Min(1)`, `@Positive`, `@NotBlank`, `@Pattern`, ... | Ràng buộc **trực tiếp** đối với giá trị tham số |
| `@Valid` | Đánh dấu cascade để kiểm tra constraint **bên trong** một object |
| `@Validated` (Spring) | Chọn validation groups; class-level `@Validated` trên bean thường là marker cho AOP method validation |

Ví dụ:

```java
@RequestParam("page") @Min(1) int page
```

`@RequestParam` giải quyết việc **lấy và chuyển kiểu** `page`; `@Min(1)` giải quyết việc **giá trị số nguyên đã chuyển** có đạt mức tối thiểu không.

Một `@RequestParam("page") int page` không mặc nhiên buộc trang phải lớn hơn 0. Ngược lại, chỉ viết `@Min(1) int page` mà không hiểu cách argument resolver lấy giá trị cũng không bảo đảm nguồn dữ liệu đúng theo API mong muốn. Ghép annotation lấy dữ liệu với constraint phù hợp giúp hợp đồng rõ ràng.

## 3. Khi nào Spring MVC kích hoạt method validation?

Tài liệu Spring Framework 6.1/6.2 phân biệt hai đường validation chính.

### 3.1. Validation riêng một command object

Nếu một tham số `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart` đại diện cho command object được đánh dấu `@Valid` hay `@Validated`, và method **không** có điều kiện làm bật whole-method validation, Spring thường kiểm tra riêng object đó.

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody CreateOrderRequest body) {
    // CreateOrderRequest chứa constraint trên các field.
}
```

Đoạn minh họa này yêu cầu DTO và import khi tích hợp. Khi object đã đọc được nhưng vi phạm constraint, nếu không có `Errors`/`BindingResult` liền sau, lỗi thường là `MethodArgumentNotValidException`. Với form object hoặc request part cũng có quy tắc xử lý riêng tương tự.

### 3.2. Method validation do có direct constraint

Khi bạn khai báo constraint trực tiếp trên **một tham số** hoặc **return value**:

```java
@GetMapping("/orders")
public String list(@RequestParam("page") @Min(1) int page) {
    return "page=" + page;
}
```

Spring MVC áp dụng method validation cho toàn handler. Cơ chế này cũng có thể kiểm tra các constraint lồng nhau thông qua `@Valid` của những command object khác trong cùng chữ ký. Nếu validation thất bại và không có cơ chế xử lý lỗi cục bộ phù hợp, MVC ném:

```java
org.springframework.web.method.annotation.HandlerMethodValidationException
```

Lỗi trên **tham số đầu vào** có trạng thái HTTP mặc định **400 Bad Request**; lỗi validation trên **return value** có trạng thái **500 Internal Server Error**, vì đây thường là lỗi hợp đồng do server tạo ra.

`@Valid` **không phải** một constraint trực tiếp. Vì vậy chỉ có `@Valid` trên DTO không tự kích hoạt method validation trong mọi trường hợp. Ngược lại, `@NotNull @Valid` trên cùng một tham số có `@NotNull` là direct constraint và có thể khiến whole-method validation áp dụng.

### 3.3. Spring MVC 6.1+ khác AOP service method validation

Một service bean thường dùng `@Validated` cấp class và `MethodValidationPostProcessor` để kiểm tra phương thức qua Spring AOP proxy. Nhưng **đối với controller Spring MVC 6.1+**, tài liệu khuyến nghị **bỏ class-level `@Validated`** nếu muốn sử dụng method validation built-in.

- Controller MVC built-in: thường nhận `HandlerMethodValidationException`.
- Spring AOP method validation: tùy cấu hình, thường nhận `ConstraintViolationException` hoặc `MethodValidationException`.
- Cả hai có thể dựa trên cùng Jakarta Bean Validation provider nhưng đi qua hạ tầng và loại exception khác nhau.

Đừng thêm `@Validated` lên mọi `@RestController` theo thói quen từ các phiên bản cũ rồi cho rằng kết quả vẫn giống nhau. Đây là một nguyên nhân phổ biến làm `@ControllerAdvice` bắt sai loại exception.

## 4. Chọn constraint đúng cho từng kiểu giá trị

| Đầu vào | Constraint thường dùng | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `int page` | `@Min(1)` hoặc `@Positive` | Trang phải từ 1 trở lên |
| `int limit` | `@Min(1) @Max(100)` | Chặn giá trị ngoài khoảng |
| `long id` | `@Positive` | Chỉ số dương |
| `String keyword` | `@NotBlank` | Không `null`, không rỗng, không toàn whitespace |
| `String code` | `@Pattern(regexp = "...")` | Phải khớp biểu thức chính quy; `null` được cho phép trừ khi có constraint khác |
| `String email` | `@Email` + `@NotBlank` khi bắt buộc | Kiểm tra cú pháp email và yêu cầu hiện diện là hai điều khác nhau |
| `Integer quantity` | `@NotNull @Min(1)` | Chặn cả thiếu giá trị và số nhỏ |
| `List<String> tags` | `@NotEmpty`, `@Size(max=...)` | Ràng buộc collection; các phần tử có thể cần constraint riêng |
| Giá trị trả về `String` | `@NotBlank` trên method | Kiểm tra hậu điều kiện sau khi handler chạy |

Một số khác biệt dễ bỏ sót:

- `@Min`, `@Max`, `@Positive` và `@Pattern` **thường coi `null` là hợp lệ**. Khi muốn không cho `null`, ghép `@NotNull` hoặc annotation phù hợp khác.
- `@NotBlank` dành cho `CharSequence`; không dùng cho `Integer` hay `List<?>`. Với collection dùng `@NotEmpty`/`@Size`.
- `@Pattern` kiểm tra toàn bộ giá trị theo regex; ví dụ mã `"PRD-123"` có thể dùng `@Pattern(regexp="PRD-[0-9]{3}")`.
- Constraint chỉ đánh giá **sau khi** giá trị đã được argument resolver/converter tạo thành đối số Java. Nếu Spring không thể chuyển `"abc"` thành `int`, lỗi chuyển kiểu xuất hiện trước khi `@Min` có cơ hội đánh giá.
- Một annotation `@NotNull` không tự bảo đảm HTTP parameter “bắt buộc”: `@RequestParam` có `required=true` mặc định, và missing parameter có đường lỗi riêng.

**Tránh over-validation:** ví dụ `@Size(min=1)` trên chuỗi vẫn cho chuỗi toàn dấu cách; chọn `@NotBlank` nếu mục tiêu là có nội dung thực.

## 5. Ví dụ chạy đầy đủ với Java 17 và Spring Boot 3.5.6

Ví dụ sau có ba tình huống thực tế:

1. Direct constraints trên path variable, query parameter và header.
2. Lỗi thiếu header được giải quyết bằng ràng buộc `@NotBlank` dù header được phép thiếu ở tầng binding.
3. Constraint trên return value của handler.

Chương trình dùng **Spring Boot 3.5.6**, Java 17+ và Maven 3.x; không cần database. Nó không đặt `@Validated` cấp class trên controller, nhằm sử dụng **built-in method validation của Spring MVC**.

### 5.1. Cấu trúc dự án

```text
controller-direct-validation/
├── pom.xml
└── src/main/java/demo/
    ├── DirectValidationApplication.java
    ├── TicketController.java
    └── ValidationErrorHandler.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>controller-direct-validation</artifactId>
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

`spring-boot-starter-web` cung cấp Spring MVC và embedded server; `spring-boot-starter-validation` cung cấp Bean Validation provider (Hibernate Validator qua starter).

### 5.3. DirectValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DirectValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(DirectValidationApplication.class, args);
    }
}
```

### 5.4. TicketController.java

```java
package demo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TicketController {

    @GetMapping("/tickets/{ticketId}")
    public String ticket(
            @PathVariable("ticketId") @Positive long ticketId,
            @RequestParam("count") @Min(1) @Max(10) int count,
            @RequestHeader(value = "X-Client", required = false)
                    @NotBlank String client) {

        return "OK:" + ticketId + ":" + count + ":" + client;
    }

    @GetMapping("/broken")
    @NotBlank
    public String broken() {
        // Cố ý vi phạm constraint trên return value.
        return "";
    }
}
```

Phân tích chữ ký `ticket`:

- `@PathVariable("ticketId")` giải quyết nguồn dữ liệu, `@Positive` yêu cầu ID lớn hơn 0.
- `@RequestParam("count")` đọc query parameter và chuyển thành `int`, còn `@Min(1) @Max(10)` kiểm tra khoảng cho phép.
- `@RequestHeader(value="X-Client", required=false)` cho phép Spring truyền `null` nếu header thiếu ở **bước phân giải request**. Nhưng `@NotBlank` vẫn cấm `null`/chuỗi rỗng/chuỗi toàn whitespace ở **bước validation**. Đây là ví dụ cố ý tách yêu cầu của argument resolver với constraint.
- `@NotBlank` của `broken()` nằm ở **cấp phương thức**, có nghĩa kiểm tra String trả về. Body method đã chạy trước khi ràng buộc này được đánh giá.
- **Không có `@Validated` ở class**, vì ta muốn cơ chế MVC built-in từ Spring 6.1+.

### 5.5. ValidationErrorHandler.java

```java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationErrorHandler {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<String> handle(HandlerMethodValidationException ex) {

        return ResponseEntity.status(ex.getStatusCode())
            .body(ex.isForReturnValue()
                ? "INVALID_RETURN"
                : "INVALID_INPUT");
    }
}
```

Handler này chủ động trả một **body cố định** để kiểm tra dễ. `ex.getStatusCode()` giữ HTTP status tương ứng do Spring chọn: 400 cho lỗi đầu vào, 500 cho lỗi return value. Trong API thực tế, bạn có thể chuyển các lỗi thành JSON có mã, vị trí, thông báo an toàn và correlation ID. Đừng trả nguyên object exception hay rejected values ra public API.

### 5.6. Lệnh chạy

Ở thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Server lắng nghe `localhost:8080` theo cấu hình mặc định nếu cổng còn trống. Mở một terminal khác (bash, zsh hoặc WSL) để chạy các request bên dưới.

**Case A — tất cả tham số hợp lệ:**

```bash
curl -s -X GET 'http://localhost:8080/tickets/8?count=3' \
  -H 'X-Client: demo'
```

HTTP status: **200 OK**. Body chính xác:

```text
OK:8:3:demo
```

**Case B — hai direct constraints cùng sai:**

```bash
curl -s -X GET 'http://localhost:8080/tickets/0?count=0' \
  -H 'X-Client: demo'
```

`ticketId=0` vi phạm `@Positive` và `count=0` vi phạm `@Min(1)`. Spring MVC ném `HandlerMethodValidationException` trước khi gọi thân `ticket`. Handler trả status **400 Bad Request** và body:

```text
INVALID_INPUT
```

**Case C — thiếu header mà tầng binding cho phép thiếu:**

```bash
curl -s -X GET 'http://localhost:8080/tickets/8?count=3'
```

Do `required=false`, Spring có thể truyền `client=null`. `@NotBlank` coi `null` là không hợp lệ. Handler trả status **400 Bad Request** và body:

```text
INVALID_INPUT
```

**Case D — vi phạm constraint trên return value:**

```bash
curl -s -X GET 'http://localhost:8080/broken'
```

`broken()` được gọi và trả `""`; hậu điều kiện `@NotBlank` bị vi phạm. `HandlerMethodValidationException#isForReturnValue()` là `true`. Handler trả status **500 Internal Server Error** và body:

```text
INVALID_RETURN
```

**Case E — giá trị chưa chuyển được sang int:**

```bash
curl -i -X GET 'http://localhost:8080/tickets/8?count=abc' \
  -H 'X-Client: demo'
```

Lỗi `"abc"` không chuyển được thành `int` xảy ra ở **argument resolution/type conversion**. Nó không phải vi phạm `@Min` hay `@Max` đã chạy thành công; framework thường dùng `MethodArgumentTypeMismatchException` và trả HTTP 400 qua xử lý lỗi mặc định. **Không kỳ vọng body `INVALID_INPUT` từ handler chỉ bắt `HandlerMethodValidationException`.** Body thực tế của nhánh conversion phụ thuộc cấu hình Spring Boot và handler của ứng dụng.

Tương tự, bỏ hẳn query parameter `count` với `@RequestParam` mặc định `required=true` thường gây `MissingServletRequestParameterException` trước bước Bean Validation. Đừng đánh đồng lỗi *không nhận được đối số* với lỗi *constraint của đối số đã nhận*.

Các khối `text` trên mô tả body do ứng dụng trả. `curl -s` không tự bổ sung newline; response headers, log Spring/Maven hoặc error response mặc định nằm ngoài body được mô tả.

## 6. Lỗi thiếu, lỗi conversion và lỗi constraint

Một API như `GET /tickets/{id}?count=...` có ít nhất ba lớp kiểm tra riêng:

| Tình huống | Tầng xử lý | Ngoại lệ thường gặp |
| --- | --- | --- |
| Thiếu `@RequestParam(required=true)` | Phân giải request parameter | `MissingServletRequestParameterException` |
| `count=abc` nhưng tham số là `int` | Chuyển kiểu | `MethodArgumentTypeMismatchException` |
| `count=0`, chuyển được sang int nhưng vi phạm `@Min(1)` | Built-in method validation | `HandlerMethodValidationException` |
| `@Valid @RequestBody DTO` parse thành công nhưng field sai, không có direct constraint khác | Validation một object | `MethodArgumentNotValidException` |
| JSON body sai cú pháp | HTTP message conversion | `HttpMessageNotReadableException` |
| Return value vi phạm `@NotBlank` | Built-in method validation sau khi handler chạy | `HandlerMethodValidationException`, status 500 |

Đây là các trường hợp **điển hình trong Spring MVC 6.1+/Boot 3.x**, không phải khẳng định mọi phiên bản, signature hay cấu hình đều tạo đúng một exception duy nhất. Custom resolvers, group validation, AOP hoặc `@ControllerAdvice` có thể thay đổi đường xử lý.

### Khi nào cần @NotNull nếu @RequestParam có required?

- `@RequestParam(required=true)` kiểm tra **có giá trị request parameter để phân giải hay không**. Khi thiếu, Spring có thể ném exception trước validation.
- `@NotNull` là **constraint Jakarta Validation** trên giá trị Java sau phân giải. Nó phát hiện `null` trong các tình huống đối số được phép nhận `null`.
- `@NotBlank` còn đòi hỏi String có nội dung không chỉ là whitespace.

Nếu muốn điều khiển riêng cách trả lỗi “missing” và lỗi “blank”, hãy xác định rõ contract API và xử lý cả hai đường, không tùy tiện chuyển mọi param thành `required=false` chỉ để ép chúng vào method validation.

## 7. Direct constraint và @Valid trên DTO có thể cùng tồn tại

Giả sử endpoint:

```java
@PostMapping("/purchases")
public ResponseEntity<Void> purchase(
        @Valid @RequestBody PurchaseRequest body,
        @RequestParam("priority") @Min(1) int priority) {

    // ...
    return ResponseEntity.noContent().build();
}
```

Đây là đoạn tích hợp minh họa; `PurchaseRequest` và imports cần được khai báo. Vì `priority` có direct constraint, Spring MVC có thể dùng **method validation cho toàn phương thức**, bao gồm cả việc cascade vào `PurchaseRequest` qua `@Valid`.

Nếu chỉ có:

```java
@PostMapping("/purchases")
public ResponseEntity<Void> purchase(
        @Valid @RequestBody PurchaseRequest body) {

    // ...
    return ResponseEntity.noContent().build();
}
```

thì ở trường hợp thông thường, framework áp dụng **argument-level validation** cho DTO và có thể ném `MethodArgumentNotValidException` khi field sai. Hai chữ ký chỉ khác một tham số có `@Min` nhưng có thể kéo theo **exception type khác nhau** — lý do controller advice phải hỗ trợ cả hai.

Nếu bạn thêm `@NotNull` trực tiếp vào cùng tham số DTO:

```java
@NotNull @Valid @RequestBody PurchaseRequest body
```

thì `@NotNull` là direct constraint, còn `@Valid` là cascade marker. Tuy nhiên lỗi thiếu/không đọc được request body vẫn có thể xảy ra ở converter/resolver trước validation. `@NotNull` không thay thế `@RequestBody(required=true)` hoặc xử lý lỗi HTTP message conversion.

## 8. BindingResult và Errors trong cùng handler

Với một đối tượng form, đặt `BindingResult` hoặc `Errors` **ngay sau tham số cần bind/validate** để controller có thể xử lý các lỗi phù hợp tại chỗ:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        BindingResult formErrors,
        @RequestParam("page") @Min(1) int page) {

    // ...
    return "result";
}
```

Đây là đoạn minh họa, không phải chương trình độc lập. Khi method validation áp dụng, tài liệu Spring MVC xác định rằng **handler chỉ được gọi nếu tất cả các validation errors thuộc những method parameters có `Errors` ngay sau**. Vì vậy:

- Nếu chỉ có lỗi của `form` và `formErrors` nhận được toàn bộ lỗi của form, handler có thể chạy và tự quyết định view/status.
- Nếu `page=0` vi phạm `@Min(1)`, trong chữ ký trên không có `Errors` gắn sau `page` theo kiểu command object, nên `HandlerMethodValidationException` có thể được ném và handler không chạy.
- Nếu bạn đặt `Model` hoặc tham số khác giữa `form` và `formErrors`, cặp không còn đúng hợp đồng của Spring MVC.

Không dùng `BindingResult` để “bắt mọi constraint” của cả phương thức. Nó gắn với kết quả binding/validation của một object cụ thể. Khi muốn chuẩn hóa lỗi tất cả tham số method-level, dùng `HandlerMethodValidationException` và API tương ứng.

## 9. Đọc HandlerMethodValidationException theo từng tham số

`HandlerMethodValidationException` triển khai `MethodValidationResult` nên cung cấp thông tin **có cấu trúc** thay vì yêu cầu parse message text.

Các API đáng biết:

| API | Tác dụng |
| --- | --- |
| `ex.getStatusCode()` | HTTP status lỗi đầu vào hoặc return value |
| `ex.isForReturnValue()` | `true` nếu vi phạm hậu điều kiện trên kết quả trả về |
| `ex.getMethod()` | Method đang được kiểm tra |
| `ex.getParameterValidationResults()` | Các kết quả validation cho tham số/return value |
| `ex.getAllErrors()` | Các lỗi dạng `MessageSourceResolvable` |
| `result.getMethodParameter()` | Metadata và vị trí tham số |
| `result.getResolvableErrors()` | Danh sách lỗi gắn với kết quả đó |
| `result.getArgument()` | Giá trị đối số, cần thận trọng với dữ liệu nhạy cảm |
| `result.getContainerIndex()/getContainerKey()` | Thông tin phần tử collection/map nếu có |

Ví dụ bổ sung cho `@ExceptionHandler`, **không phải một chương trình độc lập**:

```java
// Các import cần có: MessageSourceResolvable,
// ParameterValidationResult, HandlerMethodValidationException.
for (ParameterValidationResult result
        : ex.getParameterValidationResults()) {

    int index = result.getMethodParameter().getParameterIndex();

    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        String[] codes = error.getCodes();
        String defaultMessage = error.getDefaultMessage();

        // Tạo error DTO chỉ chứa vị trí/mã/thông báo an toàn.
        // Không mặc định trả toàn bộ method argument cho client.
    }
}
```

Spring còn có `HandlerMethodValidationException.Visitor` để nhóm kết quả theo loại tham số, chẳng hạn request param, path variable hoặc model attribute; đó là lựa chọn tốt khi muốn định dạng lỗi khác nhau theo nguồn đầu vào. Các kết quả lỗi của DTO được cascade có thể có field errors, chứ không nhất thiết chỉ là `@Min`/`@NotBlank` trên scalar argument.

Khi xuất lỗi cho client, nên giữ contract độc lập với tên tham số Java — tên có thể phụ thuộc cấu hình biên dịch và parameter-name metadata. Cũng không nên log `getArgument()` hoặc rejected value nguyên bản nếu có thể chứa mật khẩu, token, email hoặc dữ liệu cá nhân.

## 10. Phân biệt HTTP status của lỗi đầu vào và lỗi return value

Method validation có hai thời điểm:

```text
HTTP request
   │
   ├── argument resolution / type conversion
   │      └── có thể lỗi ngay ở bước này
   ▼
Built-in method validation: tham số trực tiếp và @Valid cascade
   │
   ├── sai → HandlerMethodValidationException → 400
   ▼
Controller method body chạy
   │
   ▼
Built-in method validation: return value
   │
   ├── sai → HandlerMethodValidationException → 500
   ▼
MVC return value handling / HTTP response
```

**Return-value validation là hậu điều kiện.** Nếu một controller đã gọi service, cập nhật database hoặc phát message rồi trả kết quả sai, hậu điều kiện phát hiện lỗi **sau** những thao tác đó. Nó không tự rollback database hoặc thu hồi external side effect. Thiết kế transaction, idempotency và kiểm thử side effect vẫn phải được thực hiện riêng.

HTTP 400 thường phản ánh đầu vào không đúng hợp đồng API; HTTP 500 trên return value phản ánh lỗi logic hoặc invariant phía server. Khi tùy biến `@ControllerAdvice`, đừng vô tình biến mọi `HandlerMethodValidationException` thành HTTP 400 vì sẽ che giấu vi phạm hậu điều kiện.

## 11. Validation groups và các tình huống nâng cao

Các direct constraints dùng group của Jakarta Bean Validation; nếu không chỉ định, chúng thuộc `Default`. Ví dụ:

```java
public interface AdvancedChecks {}

@GetMapping("/reports")
@Validated(AdvancedChecks.class)
public String report(
        @RequestParam("limit")
        @Min(value = 1, groups = AdvancedChecks.class) int limit) {

    return "limit=" + limit;
}
```

Đây là đoạn minh họa cần import `@Validated` từ Spring; đặt annotation ở cấp **method** để lựa chọn nhóm mà method validation sử dụng. Không nên dùng class-level `@Validated` trên controller chỉ để chọn group nếu mục tiêu là dùng MVC built-in, vì class-level có thể làm Spring chọn đường AOP.

Với collection hoặc nested parameter, phải phân biệt:

- Constraint trên **chính collection**: `@NotEmpty`, `@Size`.
- Constraint trên **phần tử**: ví dụ `List<@NotBlank String>`, với type-use constraints khi provider và đường resolution hỗ trợ.
- Cascade sang object: `List<@Valid ItemRequest>` hoặc `@Valid ItemRequest`, tùy kiểu và hợp đồng Bean Validation.

Đừng giả định một scalar constraint như `@NotBlank` có thể áp dụng cho mọi kiểu; provider có thể ném `UnexpectedTypeException` nếu không có validator hỗ trợ kiểu Java tương ứng.

### Custom constraints

Một custom Jakarta Bean Validation constraint khai báo `@Constraint(validatedBy=...)` có thể được dùng trực tiếp trên tham số nếu annotation cho phép `ElementType.PARAMETER`. Khi đó nó tham gia method validation theo cùng cơ chế. Nhưng việc kiểm tra cần được thực thi bởi provider, và custom `ConstraintValidator` nên stateless/thread-safe theo mục tiêu sử dụng.

## 12. Kiểm thử đúng đường MVC

Có hai cấp kiểm thử khác nhau:

1. **Unit test trực tiếp phương thức Java** (ví dụ `new TicketController().ticket(0, 0, "")`) chỉ kiểm thử code trong thân handler. Nó không tự chạy Spring MVC argument resolvers hoặc built-in method validation.
2. **Integration test qua HTTP hoặc MockMvc** mới kiểm tra được constraint được phát hiện, exception type và HTTP status do MVC tạo ra.

Bộ case nên có:

| Input | Kết quả cần kiểm chứng |
| --- | --- |
| `ticketId=8, count=3`, có header `X-Client: demo` | HTTP 200, handler trả kết quả |
| `ticketId=0` | Direct `@Positive` sai, HTTP 400 |
| `count=0` | Direct `@Min` sai, HTTP 400 |
| `count=11` | Direct `@Max` sai, HTTP 400 |
| Header vắng với `required=false @NotBlank` | Constraint sai, HTTP 400 |
| `count=abc` | Type conversion error, không phải lỗi `@Min` |
| Thiếu query `count` | Missing required parameter trước validation |
| `GET /broken` | Return value `@NotBlank` sai, HTTP 500 |
| `@Valid @RequestBody` với field sai, không có direct constraint khác | Đường `MethodArgumentNotValidException` |
| `@Valid @RequestBody` cùng với direct `@Min` tham số khác | Đường whole-method validation khi áp dụng |
| Controller vô tình có class-level `@Validated` | Kiểm chứng lại AOP hay MVC built-in thực sự chạy |

Nếu tests phụ thuộc loại exception, tránh gắn `@Validated` lung tung vào controller. Với API cần thông báo nhiều ngôn ngữ, dùng mã lỗi/message bundle và `MessageSource` thay vì dựa vào `ConstraintViolation#getMessage()` mặc định hoặc parse `getMessage()` của exception.

## 13. Lỗi thường gặp và hướng khắc phục

| Hiện tượng | Nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| `@Min(1)` có vẻ không chạy | Thiếu Bean Validation provider hoặc sai cách tích hợp | Dùng `spring-boot-starter-validation` và test qua MVC |
| Thiếu param tạo lỗi khác `@Min` | `@RequestParam(required=true)` lỗi ở argument resolution | Xử lý missing-parameter riêng |
| `count=abc` không tạo Min violation | Không convert được sang số | Xử lý type mismatch |
| Chỉ dùng `@Valid` mà kỳ vọng direct method validation | `@Valid` là marker cascade, không phải constraint | Thêm constraint phù hợp nếu có ràng buộc trực tiếp |
| Controller có `@Validated` cấp class, exception không đúng mong đợi | AOP validation thay thế/ảnh hưởng MVC built-in | Với Spring MVC 6.1+, cân nhắc bỏ class-level marker |
| Chỉ bắt `MethodArgumentNotValidException` | Handler còn có direct parameter constraints | Bắt thêm `HandlerMethodValidationException` |
| `BindingResult` sau DTO nhưng vẫn có exception | Lỗi trên tham số method khác không có Errors kề bên | Hiểu quy tắc toàn bộ lỗi và method validation |
| `@Min` cho phép null | Đặc tả cho phép null với numeric constraint | Ghép `@NotNull` hoặc `required` phù hợp |
| `@NotBlank` được đặt trên Integer | Kiểu không được hỗ trợ | Chọn numeric constraint |
| Return value sai nhưng API trả 400 | Custom advice ép mọi validation error về 400 | Phân biệt `isForReturnValue()` và giữ HTTP 500 |
| Trả rejected argument cho client | Expose dữ liệu nhạy cảm | Chỉ xuất field/code/message đã chuẩn hóa |
| Test gọi controller trực tiếp và không thấy lỗi | Bỏ qua Spring MVC runtime | Kiểm thử qua MockMvc hoặc HTTP |

## 14. Tổng kết

**Ràng buộc trực tiếp trên tham số controller** nghĩa là đặt annotation constraint của Jakarta Bean Validation — như `@Min`, `@Positive`, `@NotBlank` — ngay trên tham số handler, bên cạnh annotation lấy dữ liệu như `@RequestParam` hoặc `@PathVariable`. Từ Spring MVC 6.1, những ràng buộc này có thể kích hoạt **method validation built-in**, với `HandlerMethodValidationException` cho lỗi đầu vào hoặc hậu điều kiện.

Hãy phân biệt rõ **argument resolution**, **type conversion**, **constraint validation** và **controller body**. Phân biệt tiếp `@Valid` trên command object với direct constraint, tránh class-level `@Validated` khi muốn dùng MVC built-in, và xử lý cả `MethodArgumentNotValidException` lẫn `HandlerMethodValidationException` ở API boundary. Kiểm thử qua Spring MVC thực sự là cách tin cậy để xác nhận hợp đồng được thực thi.

## Tài liệu tham khảo

- Spring Framework 6.2 Reference — Validation của Spring MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Reference — Request parameters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework 6.2 Reference — Type conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework 6.2 Reference — Request body và validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 Javadoc — `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Reference — Cấu hình validator cho MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Jakarta Bean Validation 3.0 Specification — Constraint declaration và executable validation: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html