# Xử lý riêng lỗi thiếu dữ liệu, sai kiểu và vi phạm constraint trong Spring MVC

## 1. Mục tiêu: không phải mọi HTTP 400 đều giống nhau

Giả sử API cần nhận số lượng qua query parameter và tạo đơn hàng bằng JSON. Những request sau cùng có thể nhận HTTP **400 Bad Request**, nhưng **nguyên nhân khác nhau**:

```http
GET /api/query
```

Không có query parameter `quantity`.

```http
GET /api/query?quantity=abc
```

Có `quantity`, nhưng `abc` không chuyển được sang `Integer`.

```http
GET /api/bounded?quantity=0
```

Chuyển kiểu thành công, nhưng giá trị vi phạm `@Min(1)`.

```http
POST /api/orders
Content-Type: application/json

{"customer":"Mai","units":0,"delivery":{"city":"Hanoi"}}
```

JSON giải mã được thành DTO, nhưng `units=0` vi phạm `@Min(1)`.

```http
POST /api/orders
Content-Type: application/json

{"customer":"Mai","units":{"unexpected":1},"delivery":{"city":"Hanoi"}}
```

JSON hợp lệ về **cú pháp**, nhưng `units` là object, không phải số nguyên; Jackson/message converter không thể tạo DTO theo schema.

Nếu một API trả chung:

```json
{"error":"Validation failed"}
```

cho mọi tình huống, frontend không biết nên yêu cầu nhập field còn thiếu, sửa định dạng, hay đổi giá trị nằm ngoài miền cho phép. Log và metric cũng không phân biệt lỗi request với lỗi hợp đồng server.

**Mục tiêu học:** phân loại chính xác **missing**, **type/binding/decoding error**, và **constraint violation**; chọn exception handler tương ứng, định nghĩa error code ổn định, giữ HTTP status đúng, tránh rò rỉ raw input, và kiểm thử được từng trường hợp trên Spring MVC.

Phạm vi chính: **Spring MVC Servlet stack**, Java 17+, Spring Framework **6.1+/6.2.x** và Spring Boot 3.x, Jakarta Validation. Spring WebFlux có các exception riêng, không được sao chép nguyên danh sách Servlet MVC sang reactive stack.

## 2. Bốn giai đoạn request có thể thất bại

Luồng khái niệm:

```text
HTTP request
   |
   v
[1] Handler mapping và argument presence
   |   - query/header/part bắt buộc có mặt?
   |   - HTTP method, Content-Type phù hợp?
   v
[2] Decoding và binding/conversion
   |   - "42" -> Integer
   |   - JSON -> DTO bằng Jackson
   |   - form fields -> DTO bằng WebDataBinder
   v
[3] Bean Validation / handler method validation
   |   - @NotBlank, @NotNull, @Min, @Size, @Valid
   |   - return-value constraints (lỗi server)
   v
[4] Business / persistence / downstream
       - điều kiện nghiệp vụ, quyền, database, ...
```

Điểm quan trọng: **nếu bước trước thất bại, bước sau có thể chưa chạy**. Ví dụ `quantity=abc` không tạo ra được `int` để `@Min(1)` kiểm tra. Một field JSON sai kiểu có thể bị từ chối trước khi một `@NotNull` hay `@Min` trên DTO được đánh giá.

Không dùng tên chung “validation error” cho mọi lỗi được phát hiện trước khi controller chạy. Spring MVC phân biệt nguồn lỗi và thường cung cấp các exception types riêng.

### 2.1. Bảng định tuyến loại lỗi

| Đầu vào | Giai đoạn | Exception Spring MVC thường thấy | Nhóm phản hồi |
| --- | --- | --- | --- |
| Thiếu `@RequestParam(required=true)` | Presence/argument resolution | `MissingServletRequestParameterException` | `MISSING_PARAMETER` |
| Thiếu `@RequestHeader(required=true)` | Presence | `MissingRequestHeaderException` | `MISSING_HEADER` |
| Thiếu required multipart part | Presence | `MissingServletRequestPartException` | `MISSING_PART` |
| Required `@RequestBody` rỗng | Request body resolution | Thường `HttpMessageNotReadableException` | `BODY_UNREADABLE` hoặc tách `MISSING_BODY` có chủ đích |
| `quantity=abc` → `Integer` | Type conversion | `MethodArgumentTypeMismatchException` (nhánh `TypeMismatchException`) | `TYPE_MISMATCH` |
| Form `units=abc` → `Integer` | WebDataBinder | `FieldError` với `isBindingFailure()==true`; khi không có `BindingResult` thường được bọc thành `MethodArgumentNotValidException` | `FIELD_BINDING_ERROR` |
| JSON sai cú pháp | `HttpMessageConverter`/Jackson | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| JSON có field sai kiểu, ví dụ object → integer | Converter/Jackson | Thường `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| JSON thiếu field DTO + `@NotNull` | Validation sau decode | Thường `MethodArgumentNotValidException` | `CONSTRAINT_VIOLATION` |
| DTO `@Valid` có `@NotBlank` sai | Validation argument | `MethodArgumentNotValidException` | `CONSTRAINT_VIOLATION` |
| Direct `@Min` trên handler parameter (MVC 6.1+) | Handler method validation | `HandlerMethodValidationException` | `METHOD_CONSTRAINT_VIOLATION` |
| Constraint trên return của handler sai | Return method validation | `HandlerMethodValidationException` | `RETURN_CONTRACT_VIOLATION`, thường 500 |
| `@Service @Validated` qua Spring AOP proxy | Service method validation | Mặc định thường `ConstraintViolationException` | Phụ thuộc nguồn lỗi và hợp đồng API |

Đây là các trường hợp **thông thường**, không phải lời hứa mọi framework version/configuration luôn phát cùng exception. `@ControllerAdvice`, `@Validated` class-level, `BindingResult`, custom argument resolver và converter có thể thay đổi đường đi.

## 3. Nhóm 1 — Lỗi thiếu dữ liệu

### 3.1. Thiếu query parameter bắt buộc

```java
@GetMapping("/query")
public Map<String, Integer> query(
        @RequestParam("quantity") Integer quantity) {
    return Map.of("quantity", quantity);
}
```

`@RequestParam` mặc định `required=true`. Request:

```http
GET /api/query
```

không có `quantity`; Spring có thể ném `MissingServletRequestParameterException` **trước khi handler được gọi**. Có thể đọc `ex.getParameterName()` và `ex.getParameterType()` để định vị field nhưng không nên công bố toàn bộ exception message/stack trace.

**Phân biệt:**
- **Không có parameter:** `/api/query`.
- **Có parameter rỗng:** `/api/query?quantity=`.
- **Có parameter sai kiểu:** `/api/query?quantity=abc`.

Với `Integer`, chuỗi rỗng có thể được chuyển thành `null` và tiếp tục gây `MissingServletRequestParameterException` theo nhánh *missing after conversion*. Thuộc tính `ex.isMissingAfterConversion()` của exception giúp chẩn đoán trường hợp này. Đừng tuyên bố mọi dấu `?quantity=` luôn bị xem như `quantity=abc`.

### 3.2. `required=false` không phải validation

```java
@GetMapping("/optional")
public String optional(
        @RequestParam(name = "quantity", required = false)
        Integer quantity) {
    return quantity == null ? "missing" : "present";
}
```

Khi `required=false`, tham số có thể là null; controller chịu trách nhiệm xử lý. Nhưng nếu có `quantity=abc`, việc chuyển kiểu vẫn có thể thất bại. Bỏ yêu cầu presence **không** đồng nghĩa bỏ type conversion.

Có thể dùng `Optional<Integer>` nếu phù hợp. Tránh `int` primitive cho một parameter optional mà bạn cần biểu diễn “không có”.

### 3.3. Thiếu HTTP request body

Với:

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest body) {
    // ...
}
```

`@RequestBody` mặc định `required=true`. Nếu body không có nội dung, MVC thường tạo `HttpMessageNotReadableException` với nguyên nhân **required body missing**. Đây chưa phải `@NotBlank` của DTO, vì DTO chưa được tạo.

Nếu sản phẩm cần **error code riêng cho thiếu body** mà không dựa vào cách phân tích chuỗi exception message, có thể chọn chủ đích:

```java
@PostMapping("/orders")
public void create(
        @Valid @RequestBody(required = false) OrderRequest body) {

    if (body == null) {
        throw new MissingBodyException();
    }
    // ...
}
```

Khi đó request body hoàn toàn vắng mặt có thể đi tới controller với `body=null` và được xử lý bằng custom exception `MissingBodyException`. Ngược lại, body **có nội dung nhưng JSON sai** vẫn bị converter từ chối trước khi vào handler.

**Lưu ý:** Đây là một lựa chọn API design để phân loại rõ lỗi, không phải quy định rằng mọi endpoint phải đặt `required=false`. Nếu giữ mặc định `required=true`, để tách chính xác missing-body khỏi JSON decoding error bạn cần xử lý có cấu trúc với thông tin nguồn lỗi; không nên so khớp một message tiếng Anh có thể đổi theo phiên bản.

### 3.4. Thiếu field trong JSON khác thiếu cả body

Giả sử DTO:

```java
public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer units) {}
```

Body:

```json
{"customer":"Mai"}
```

JSON hợp lệ, Jackson có thể tạo `OrderRequest` với `units=null` và Bean Validation phát hiện `@NotNull`. Đây thường là **`MethodArgumentNotValidException`**, không phải `MissingServletRequestParameterException`, vì `units` là **property của request DTO**, không phải một `@RequestParam`.

Với `int units` primitive thay vì `Integer`, trường thiếu có thể thành `0` theo cấu hình Jackson thông thường. Nếu API cần biết rõ “không gửi” so với “gửi 0”, dùng `Integer` với `@NotNull` và `@Min(1)`; còn nếu cần phân biệt **JSON property absent** với explicit `null`, cần chiến lược Jackson/DTO hoặc validation riêng, không chỉ dựa vào `@NotNull`.

### 3.5. Thiếu header, part và path

- `@RequestHeader("X-Client-Id")` bắt buộc thiếu → thường `MissingRequestHeaderException`.
- `@RequestPart("file")` bắt buộc thiếu → thường `MissingServletRequestPartException`.
- Multipart part **có mặt nhưng file 0 byte** là vấn đề khác, cần kiểm tra `MultipartFile.isEmpty()`.
- Với `@PathVariable`, một segment URL vắng mặt thường khiến **route không match** (404), chứ không nhất thiết ném `MissingPathVariableException`. Exception này có thể biểu thị lỗi mapping/template ở phía ứng dụng; không mặc định mọi trường hợp missing path là lỗi input 400.

Trong bài này, demo runnable tập trung vào query, body, JSON DTO và form vì chúng thể hiện đầy đủ ba nhóm lỗi mục tiêu.

## 4. Nhóm 2 — Lỗi sai kiểu và conversion

### 4.1. Type mismatch của query parameter

```java
@GetMapping("/query")
public Map<String, Integer> query(
        @RequestParam("quantity") Integer quantity) {
    return Map.of("quantity", quantity);
}
```

Nếu gọi:

```http
GET /api/query?quantity=abc
```

Spring không thể chuyển String `"abc"` thành `Integer`; lỗi thường là `MethodArgumentTypeMismatchException` (kế thừa `TypeMismatchException`).

Nó khác trường hợp:
- `quantity` không tồn tại → missing parameter.
- `quantity=0` → conversion thành công; không có constraint trong ví dụ này, nên 0 **không tự là lỗi**.
- `quantity=0` cộng `@Min(1)` → conversion thành công nhưng vi phạm method constraint.

Trong `ResponseEntityExceptionHandler`, điểm override tương ứng là **`handleTypeMismatch(TypeMismatchException, ...)`**. Không tự định nghĩa một `@ExceptionHandler(MethodArgumentTypeMismatchException.class)` cạnh superclass nếu gây xung đột với các exception handlers sẵn có; override protected handler thích hợp để giữ cách xử lý nhất quán.

### 4.2. JSON sai cú pháp

```http
POST /api/orders
Content-Type: application/json

{"customer":
```

Jackson không thể parse body. `@Valid` trên DTO chưa có cơ hội chạy; Spring MVC thường đưa lỗi về `HttpMessageNotReadableException`.

Không trả mã lỗi `CONSTRAINT_VIOLATION` vì message type/field constraints không phải tác nhân ban đầu.

### 4.3. JSON hợp lệ nhưng không thể deserialize sang DTO

```json
{
  "customer": "Mai",
  "units": {"unexpected": true},
  "delivery": {"city": "Hanoi"}
}
```

`units` trong Java được khai báo `Integer`, nhưng client gửi object. JSON **đúng cú pháp** song **không đúng kiểu dữ liệu của hợp đồng API**. Converter có thể ném `HttpMessageNotReadableException`, thường bọc exception của Jackson như `MismatchedInputException`.

Thông qua root cause và path của Jackson, bạn *có thể* phân biệt lỗi cú pháp với schema/type, nhưng phải kiểm soát cách ánh xạ vì exception cause chains và coercion configuration thay đổi theo release. Demo chọn mã ổn định `BODY_UNREADABLE` cho hai tình huống decode, đồng thời phân biệt chúng với query type mismatch và Bean Validation.

**Không trả raw body hay Jackson exception message cho client:** exception có thể chứa đường dẫn/kiểu Java nội bộ hoặc nội dung người dùng. Chỉ đưa thông báo an toàn và correlation ID.

### 4.4. Form `@ModelAttribute` sai kiểu

```java
public class OrderForm {
    private Integer units;
    public Integer getUnits() { return units; }
    public void setUnits(Integer units) { this.units = units; }
}
```

Với form field `units=abc`, Spring `WebDataBinder` thường ghi một `FieldError` có:
- `getField()` = `"units"`.
- `isBindingFailure()` = `true`.
- `getCode()` hoặc `getCodes()` có mã liên quan `typeMismatch`.

Nếu controller dùng `@Valid @ModelAttribute` và không có `BindingResult` ngay sau, Spring thường phát `MethodArgumentNotValidException`, bao gồm cả field binding errors. Vì thế **không được mặc định rằng mọi `MethodArgumentNotValidException` đều thuần Jakarta constraint violation**.

Khi cần tách riêng, dùng `FieldError.isBindingFailure()`:
- `true` → lỗi binding, thường type mismatch.
- `false` → lỗi từ validator, thường constraint violation.

Một request có thể mang **cả hai loại FieldError** trên các field khác nhau. Có thể chọn error response có category tổng hợp và danh sách lỗi theo từng field, thay vì ép mọi lỗi vào một nhãn.

### 4.5. Lỗi cấu hình converter khác lỗi client sai kiểu

`ConversionNotSupportedException` có thể xuất hiện nếu ứng dụng thiếu converter/PropertyEditor cần thiết hoặc không hỗ trợ conversion theo cách đúng. Đây có thể là **lỗi cấu hình phía server**, mặc định nên xử lý khác `MethodArgumentTypeMismatchException` do client gửi `abc`.

Đừng viết catch-all cho `TypeMismatchException` rồi luôn trả 400 nếu status do Spring truyền vào là 500. Trong override handler, **tôn trọng `HttpStatusCode status`** từ framework; phân loại code nội bộ theo exception và ngữ cảnh.

## 5. Nhóm 3 — Vi phạm Jakarta Bean Validation

### 5.1. DTO argument validation

```java
public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer units) {}

@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest request) {
    // ...
}
```

Với JSON:

```json
{"customer":"  ","units":0}
```

Jackson tạo được object. Constraint `@NotBlank` cấm chuỗi toàn khoảng trắng và `@Min(1)` cấm 0. Spring MVC argument validation có thể ném `MethodArgumentNotValidException` nếu handler không có `BindingResult` ngay sau argument.

**Khác biệt giữa annotation:**
- `@NotNull` bắt null nhưng không bắt chuỗi blank.
- `@NotBlank` dành cho String/CharSequence, bắt null, rỗng, toàn whitespace.
- `@Min(1)` kiểm tra giới hạn số, thường cho phép null; cần `@NotNull` nếu bắt buộc gửi.
- `@Valid` yêu cầu cascade vào object/field nested, không phải một direct `@Constraint`.
- `@Email` kiểm tra định dạng email nhưng không tự yêu cầu non-null; thường kết hợp `@NotBlank` nếu bắt buộc.

### 5.2. DTO lồng nhau và cascade

```java
public record Delivery(@NotBlank String city) {}

public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer units,
        @NotNull @Valid Delivery delivery) {}
```

Nếu `delivery=null`, `@NotNull` phát hiện thiếu object. Nếu `delivery={"city":""}`, `@Valid` đi sâu và `@NotBlank` trên `city` phát hiện lỗi ở path `delivery.city`.

Không gắn `@Valid` mà quên `@NotNull` rồi kỳ vọng null bị cấm. Khi nested reference là null, cascade thường không đánh giá các field bên trong.

### 5.3. Direct constraint trên handler từ Spring MVC 6.1+

```java
@GetMapping("/bounded")
public Map<String, Integer> bounded(
        @RequestParam("quantity") @Min(1) int quantity) {
    return Map.of("quantity", quantity);
}
```

`@Min(1)` được đặt trực tiếp trên method parameter. Với Spring MVC 6.1+ (và Bean Validation provider), Spring có **built-in method validation**; giá trị `quantity=0` có thể dẫn tới `HandlerMethodValidationException`, không phải `MethodArgumentNotValidException`.

Bài này **không đặt class-level `@Validated` lên controller**. Theo tài liệu Spring, class-level `@Validated` có thể chuyển method validation qua Spring AOP proxy, làm exception/handling khác với MVC built-in. Nếu muốn dùng cơ chế MVC mới, bỏ annotation ở cấp controller class.

### 5.4. Handler có cả `@Valid` DTO và direct constraint

```java
@PostMapping("/mixed")
public void mixed(
        @RequestParam("batch") @Min(1) int batch,
        @Valid @RequestBody OrderRequest request) {
    // ...
}
```

Vì có direct constraint trên `batch`, Spring MVC 6.1+ dùng **method validation** cho handler và có thể bao phủ DTO `@Valid`. Kết quả lỗi DTO cũng có thể thuộc `HandlerMethodValidationException`.

Vì thế một `@RestControllerAdvice` dành cho API cần xem xét **cả `MethodArgumentNotValidException` lẫn `HandlerMethodValidationException`**. Chỉ bắt một trong hai có thể khiến API thiếu error format khi chữ ký controller thay đổi.

### 5.5. Constraint trên return value: lỗi server

```java
@NotNull
@GetMapping("/reference")
public String reference() {
    return null;
}
```

Đây là một endpoint **cố tình sai để minh họa**; đừng đưa vào production. Constraint trên return value thất bại thường được phản ánh bằng `HandlerMethodValidationException` với status **500 Internal Server Error**. Không biến mọi vi phạm constraint thành 400, vì đây là lỗi hậu điều kiện phía ứng dụng.

## 6. Quy tắc thiết kế mã lỗi ổn định

Một schema đơn giản cho bài học:

```json
{
  "code": "CONSTRAINT_VIOLATION",
  "fields": [
    {"field": "customer", "code": "NotBlank"},
    {"field": "units", "code": "Min"}
  ]
}
```

Các nguyên tắc:
1. **HTTP status** biểu thị class lỗi ở tầng HTTP; input sai thường 400, unsupported media type thường 415, lỗi return invariant của server thường 500.
2. **`code`** là định danh máy đọc được, ổn định, ví dụ `MISSING_PARAMETER`, `TYPE_MISMATCH`, `BODY_UNREADABLE`, `FIELD_BINDING_ERROR`, `CONSTRAINT_VIOLATION`.
3. **`fields[]`** chứa field names và error codes; thứ tự được sắp xếp để test ổn định.
4. **Message hiển thị** có thể dịch qua `MessageSource`, không phải cách frontend nên phân biệt loại lỗi.
5. Không đính kèm `getRejectedValue()`, request body, stack trace hay Java class names nội bộ vào response public.
6. Khi cần khả năng theo dõi, thêm correlation/request ID ở tầng logging/observability; đừng đưa secrets vào metrics labels.
7. Với request có nhiều FieldErrors, giữ **mức chi tiết theo từng field**; một response có thể vừa có binding failure vừa có validation failure.

Trong sản phẩm thật, nên cân nhắc chuẩn **RFC 9457 Problem Details** qua `ProblemDetail` hoặc `ErrorResponse`. Ví dụ dưới dùng JSON gọn để tập trung vào cách phân loại. Không tự bịa rằng JSON này là body mặc định Spring sinh ra.

## 7. Dự án mẫu Java 17 + Spring Boot 3.5.6

Ví dụ thực thi bốn endpoint chính:
- `GET /api/query`: lỗi thiếu tham số và lỗi chuyển kiểu query.
- `GET /api/bounded`: lỗi method constraint `@Min`.
- `POST /api/orders`: phân biệt thiếu toàn bộ body, body không đọc được và DTO constraint violations.
- `POST /api/form`: xử lý lỗi type binding và constraint trong `@ModelAttribute`.

Một `@RestControllerAdvice` kế thừa `ResponseEntityExceptionHandler` override các protected handler phù hợp, giữ nguyên status được Spring chọn.

**Vì sao Boot 3.5.6?** Đây là bản Boot 3.5 cụ thể có thật, dùng Java 17+ và Spring Framework 6.2.x. Không ngụ ý đó là release mới nhất. Ví dụ có `spring-boot-starter-validation` để chắc chắn Jakarta provider hiện diện trong cấu hình thông thường.

### 7.1. Cấu trúc thư mục

```text
mvc-error-categories/
├── pom.xml
└── src/
    ├── main/java/demo/errors/
    │   ├── ErrorCategoryApplication.java
    │   ├── OrderRequest.java
    │   ├── OrderForm.java
    │   ├── MissingBodyException.java
    │   ├── ExampleController.java
    │   └── ApiExceptionHandler.java
    └── test/java/demo/errors/
        └── ErrorCategoryTest.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>mvc-error-categories</artifactId>
    <version>1.0-SNAPSHOT</version>

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

### 7.3. `ErrorCategoryApplication.java`

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorCategoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorCategoryApplication.class, args);
    }
}
```

### 7.4. `OrderRequest.java`

```java
package demo.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderRequest(
        @NotBlank(message = "customer.required")
        String customer,

        @NotNull(message = "units.required")
        @Min(value = 1, message = "units.min")
        Integer units,

        @NotNull(message = "delivery.required")
        @Valid
        Delivery delivery) {

    public record Delivery(
            @NotBlank(message = "delivery.city.required")
            String city) {
    }
}
```

`Integer units` giúp `null` khác `0`. `@Min` không tự bắt null, nên có thêm `@NotNull`. `@NotNull @Valid Delivery` tách “thiếu nested object” với “nested city không hợp lệ”.

### 7.5. `OrderForm.java`

```java
package demo.errors;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderForm {
    @NotBlank(message = "label.required")
    private String label;

    @NotNull(message = "units.required")
    @Min(value = 1, message = "units.min")
    private Integer units;

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public Integer getUnits() {
        return units;
    }

    public void setUnits(Integer units) {
        this.units = units;
    }
}
```

Form DTO dùng setter binding để quan sát rõ `FieldError.isBindingFailure()` khi `units=abc`.

### 7.6. `MissingBodyException.java`

```java
package demo.errors;

public class MissingBodyException extends RuntimeException {
    public MissingBodyException() {
        super("Required order body is absent");
    }
}
```

Exception riêng này phục vụ **chính sách phân loại missing body** của ứng dụng. Nó không thay `HttpMessageNotReadableException` do JSON converter sinh khi body có nội dung nhưng sai cấu trúc.

### 7.7. `ExampleController.java`

```java
package demo.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class ExampleController {

    // Cố ý không có @Validated ở class level.

    @GetMapping("/query")
    public Map<String, Integer> query(
            @RequestParam("quantity") Integer quantity) {
        return Map.of("quantity", quantity);
    }

    @GetMapping("/bounded")
    public Map<String, Integer> bounded(
            @RequestParam("quantity") @Min(1) int quantity) {
        return Map.of("quantity", quantity);
    }

    @PostMapping(path = "/orders",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> orders(
            @Valid @RequestBody(required = false)
            OrderRequest body) {

        if (body == null) {
            throw new MissingBodyException();
        }

        return Map.of(
                "customer", body.customer(),
                "units", body.units(),
                "city", body.delivery().city());
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> form(
            @Valid @ModelAttribute("orderForm")
            OrderForm form) {

        return Map.of(
                "label", form.getLabel(),
                "units", form.getUnits());
    }
}
```

**Giải thích:**
- `query()` không có `@Min`, nên `quantity=0` là input hợp lệ; chỉ **presence và type** bị kiểm tra ở argument resolution.
- `bounded()` có direct `@Min`, kích hoạt MVC built-in method validation cho giá trị số đã chuyển kiểu thành công.
- `orders()` chọn `@RequestBody(required=false)` để nhận null khi body vắng, rồi chủ động ném `MissingBodyException`. Body sai cấu trúc vẫn thất bại tại Jackson.
- `orders()` dùng `@Valid` để kiểm tra `OrderRequest` nếu object được tạo.
- `form()` không có `BindingResult` nên framework sẽ báo lỗi binding/validation lên exception handler; chính handler phân biệt `FieldError.isBindingFailure()`.
- Các response thành công dùng `Map.of` với các field đã được validate thành nonnull.

### 7.8. `ApiExceptionHandler.java` — phân loại lỗi theo đúng nguồn

```java
package demo.errors;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> response(
            HttpStatusCode status,
            String code,
            List<Map<String, String>> fields) {

        Map<String, Object> payload =
                Map.of("code", code, "fields", fields);
        return new ResponseEntity<>(payload, status);
    }

    private static Map<String, String> issue(
            String field, String code) {
        return Map.of("field", field, "code", code);
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return response(status, "MISSING_PARAMETER",
                List.of(issue(ex.getParameterName(), "required")));
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Tên query parameter lấy từ MVC exception nếu có.
        String field = ex instanceof MethodArgumentTypeMismatchException m
                ? m.getName() : "parameter";

        return response(status, "TYPE_MISMATCH",
                List.of(issue(field, "typeMismatch")));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Không đưa raw JSON/Jackson message ra client.
        return response(status, "BODY_UNREADABLE", List.of());
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        var fieldErrors = ex.getBindingResult().getFieldErrors();

        var issues = fieldErrors.stream()
                .map(e -> issue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "typeMismatch"
                                : e.getCode() == null
                                        ? "invalid"
                                        : e.getCode()))
                .distinct()
                .sorted(Comparator.comparing(m -> m.get("field")))
                .toList();

        boolean bindingFailure = fieldErrors.stream()
                .anyMatch(FieldError::isBindingFailure);

        // Trong response có thể có cả binding lẫn validation issues.
        String code = bindingFailure
                ? "FIELD_BINDING_ERROR"
                : "CONSTRAINT_VIOLATION";

        return response(status, code, issues);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        String code = ex.isForReturnValue()
                ? "RETURN_CONTRACT_VIOLATION"
                : "METHOD_CONSTRAINT_VIOLATION";

        // Giữ status của framework: input thường 400, return thường 500.
        return response(status, code, List.of());
    }

    @ExceptionHandler(MissingBodyException.class)
    public ResponseEntity<Object> missingBody(
            MissingBodyException ex) {
        return response(HttpStatus.BAD_REQUEST,
                "MISSING_BODY", List.of());
    }
}
```

**Vì sao kế thừa `ResponseEntityExceptionHandler`?**

Spring đã có một bộ xử lý exception MVC với các protected override points. Nếu subclass dùng `@ExceptionHandler` mới cho cùng exception mà superclass đã nhận, có thể xảy ra xung đột mapping. Override `handleTypeMismatch`, `handleHttpMessageNotReadable`, `handleMethodArgumentNotValid`, `handleHandlerMethodValidationException`... giúp giữ đúng luồng Spring.

**Vì sao status lấy từ tham số `status`?**

Một `TypeMismatchException` thông thường do client gửi `abc` có thể là 400, nhưng loại conversion không được hỗ trợ do cấu hình server có thể dùng status khác. Method validation trên return có thể là 500. Giữ `status` sẽ không vô tình chuyển lỗi backend thành lỗi client.

**Vì sao dùng `FieldError.isBindingFailure()`?**

Với form, exception `MethodArgumentNotValidException` có thể chứa cả lỗi conversion lẫn constraint. Tách theo từng field trước khi đặt category tổng hợp. Trong sản phẩm thật, nên bổ sung category vào mỗi issue (ví dụ `binding`/`constraint`) nếu response đồng thời có nhiều lỗi; ví dụ giữ payload nhỏ để dễ kiểm thử.

## 8. Kiểm thử end-to-end với MockMvc

`MockMvc` đưa request qua Spring MVC argument resolvers, message converters, binder, Jakarta Validator và exception resolvers mà không mở cổng HTTP thật.

### 8.1. `ErrorCategoryTest.java`

```java
package demo.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorCategoryTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID_JSON = """
        {
          "customer":"Mai",
          "units":2,
          "delivery":{"city":"Hanoi"}
        }
        """;

    @Test
    void missingRequiredQueryParameterHasOwnCode() throws Exception {
        mvc.perform(get("/api/query"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("quantity"));
    }

    @Test
    void nonNumericQueryParameterHasTypeCode() throws Exception {
        mvc.perform(get("/api/query").param("quantity", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("quantity"));
    }

    @Test
    void zeroIsNotInvalidWithoutConstraint() throws Exception {
        mvc.perform(get("/api/query").param("quantity", "0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.quantity").value(0));
    }

    @Test
    void directMinConstraintHasSeparateCode() throws Exception {
        mvc.perform(get("/api/bounded").param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_CONSTRAINT_VIOLATION"));
    }

    @Test
    void wrongTypeStillFailsBeforeMinConstraint() throws Exception {
        mvc.perform(get("/api/bounded").param("quantity", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"));
    }

    @Test
    void missingBodyHasExplicitCode() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MISSING_BODY"));
    }

    @Test
    void malformedJsonIsNotBeanValidation() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"customer\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BODY_UNREADABLE"));
    }

    @Test
    void wrongJsonFieldTypeIsBodyUnreadable() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "units":{"unexpected":true},
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BODY_UNREADABLE"));
    }

    @Test
    void missingDtoFieldIsConstraintViolation() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].field").value("units"))
                .andExpect(jsonPath("$.fields[0].code").value("NotNull"));
    }

    @Test
    void zeroDtoValueViolatesMin() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "units":0,
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].code").value("Min"));
    }

    @Test
    void blankCustomerViolatesNotBlank() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"  ",
                              "units":2,
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field").value("customer"))
                .andExpect(jsonPath("$.fields[0].code").value("NotBlank"));
    }

    @Test
    void nestedDtoValidationHasFieldPath() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "units":2,
                              "delivery":{"city":""}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("delivery.city"));
    }

    @Test
    void validOrderSucceeds() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer").value("Mai"))
                .andExpect(jsonPath("$.units").value(2));
    }

    @Test
    void formFieldWrongTypeIsBindingError() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "Box")
                        .param("units", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("FIELD_BINDING_ERROR"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("units"));
    }

    @Test
    void formConstraintHasDifferentCode() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "")
                        .param("units", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].code")
                        .value("NotBlank"));
    }

    @Test
    void formMissingFieldIsNotNullViolation() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "Box"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].field").value("units"));
    }

    @Test
    void validFormSucceeds() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "Box")
                        .param("units", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.units").value(3));
    }
}
```

**Kỳ vọng 17 test cases đều pass** với Java 17, Maven và các dependencies đúng phiên bản. Đây là một bộ test minh họa theo hành vi mong đợi, **chưa phải bằng chứng đã chạy trên môi trường thực**.

Các test chỉ có một lỗi field khi assert `fields[0]`, tránh phụ thuộc thứ tự khi có nhiều violations. Khi hệ thống thực có nhiều FieldErrors, hãy so sánh tập/đường dẫn và error codes thay vì assume thứ tự từ provider.

### 8.2. Chạy Maven

Tại thư mục `mvc-error-categories`:

```bash
mvn test
```

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Maven/Surefire sẽ in kết quả theo cấu hình máy. Không cố định stdout log của Spring Boot; quan trọng là assertions của JUnit/MockMvc.

## 9. Thử bằng curl và đọc kết quả

### 9.1. Thiếu query parameter

```bash
curl -i 'http://localhost:8080/api/query'
```

Kỳ vọng HTTP 400:

```json
{
  "code":"MISSING_PARAMETER",
  "fields":[{"field":"quantity","code":"required"}]
}
```

### 9.2. Sai kiểu query

```bash
curl -i 'http://localhost:8080/api/query?quantity=abc'
```

Kỳ vọng HTTP 400:

```json
{
  "code":"TYPE_MISMATCH",
  "fields":[{"field":"quantity","code":"typeMismatch"}]
}
```

### 9.3. Vi phạm direct method constraint

```bash
curl -i 'http://localhost:8080/api/bounded?quantity=0'
```

Kỳ vọng HTTP 400:

```json
{
  "code":"METHOD_CONSTRAINT_VIOLATION",
  "fields":[]
}
```

### 9.4. Thiếu JSON body

```bash
curl -i -X POST \
  'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json'
```

Kỳ vọng HTTP 400 với mã `MISSING_BODY` do controller chủ động ném custom exception.

### 9.5. JSON sai kiểu

```bash
curl -i -X POST \
  'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Mai","units":{"x":1},"delivery":{"city":"Hanoi"}}'
```

Kỳ vọng HTTP 400 với mã `BODY_UNREADABLE`. Đây **không phải** lỗi `@Min` vì converter chưa tạo được `Integer units`.

### 9.6. JSON hợp lệ nhưng vi phạm constraint

```bash
curl -i -X POST \
  'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Mai","units":0,"delivery":{"city":"Hanoi"}}'
```

Kỳ vọng HTTP 400 với mã `CONSTRAINT_VIOLATION` và field code `Min` cho `units`.

Các JSON response trong phần này do **ApiExceptionHandler của demo** tạo ra; không phải định dạng bắt buộc của Spring MVC. Key order trong JSON không phải contract.

## 10. `BindingResult`: xử lý cục bộ mà không ném exception

Trong một controller khác, nếu muốn tự điều khiển lỗi của form:

```java
@PostMapping("/form-local")
public ResponseEntity<?> local(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        boolean wrongType = errors.getFieldErrors().stream()
                .anyMatch(FieldError::isBindingFailure);

        return ResponseEntity.badRequest().body(
                Map.of("code", wrongType
                        ? "FIELD_BINDING_ERROR"
                        : "CONSTRAINT_VIOLATION"));
    }

    return ResponseEntity.ok().build();
}
```

Đây là **fragment minh họa**, không có trong project mục 7. Phải import `BindingResult`, `FieldError`, `Map` và Spring annotations tương ứng.

`BindingResult` phải đặt **ngay sau argument được bind/validate**. Nếu không có `BindingResult` đúng chỗ, framework thường ném exception. Khi có nó, controller có thể xem `errors.getFieldErrors()`, `getGlobalErrors()`, `getSuppressedFields()` và phản hồi riêng.

**Cảnh báo:** Nếu method cũng có **direct method constraints**, Spring MVC 6.1+ có thể dùng `HandlerMethodValidationException`; không phải mọi lỗi đều được thu vào một `BindingResult` duy nhất. Bổ sung direct `@Min` vào một parameter khác có thể đổi cơ chế validation của handler.

## 11. Cách làm tốt hơn khi request chứa nhiều lỗi cùng lúc

Ví dụ form gửi:

```text
label=
units=abc
```

Một field sai constraint, field kia sai kiểu. Nếu chỉ trả một mã tổng quát `FIELD_BINDING_ERROR`, frontend có thể không biết `label` cũng cần sửa. Response chi tiết nên có per-field category:

```json
{
  "code":"INPUT_INVALID",
  "fields":[
    {"field":"label","category":"constraint","code":"NotBlank"},
    {"field":"units","category":"binding","code":"typeMismatch"}
  ]
}
```

Đây là thiết kế **đề xuất**, không phải response của project mục 7. Có thể tạo cấu trúc:

```java
public record Issue(
        String field,
        String category,
        String code) {}
```

và chuyển `FieldError` thành:
- `isBindingFailure()==true` → `category="binding"`.
- Ngược lại → `category="constraint"`.
- Global `ObjectError` không có field cụ thể → `category="object"`.

Đừng chỉ lấy thông báo cuối cùng của exception và parse để xác định loại lỗi. Dùng metadata do Spring cung cấp, giữ event logs/metrics theo categories có tính ổn định.

## 12. `HandlerMethodValidationException` có cấu trúc theo parameter

Trong Spring MVC 6.1+, `HandlerMethodValidationException` có:
- `getAllValidationResults()`, cung cấp các `ParameterValidationResult`.
- `isForReturnValue()`, phân biệt lỗi parameter hay return.
- `getStatusCode()`, phản ánh mã phù hợp.
- `visitResults(...)`, visitor theo loại handler argument như `@RequestParam`, `@RequestHeader`, `@ModelAttribute`.

Muốn trả lỗi chi tiết hơn, có thể duyệt `ParameterValidationResult.getResolvableErrors()` hoặc visitor để phân biệt lỗi trực tiếp trên query parameter với lỗi lồng trong object. Không dùng một regex tách exception message để đoán field.

Ví dụ khái niệm:

```java
for (var parameterResult : exception.getAllValidationResults()) {
    var parameter = parameterResult.getMethodParameter();

    for (var error : parameterResult.getResolvableErrors()) {
        // Chuyển MethodParameter + MessageSourceResolvable
        // sang code/path ổn định của API.
    }
}
```

Đây là **fragment** có biến `exception` kiểu `HandlerMethodValidationException`; không phải một đoạn hoàn chỉnh nằm trong project chạy. Chọn error schema, locale và message source phù hợp khi triển khai. Không tự coi return-value violation là lỗi do user gửi, và đừng expose giá trị return nội bộ.

## 13. Lỗi từ service method validation và business validation

### 13.1. `@Validated` trên Spring service qua proxy

```java
@Service
@Validated
public class InventoryService {

    public void reserve(@Min(1) int count) {
        // ...
    }
}
```

Nếu bean được method-validation AOP quản lý và lời gọi đi qua proxy, input `count=0` thường dẫn tới `jakarta.validation.ConstraintViolationException`. Đây không phải cùng đường xử lý với `HandlerMethodValidationException` của MVC handler, và exception này **không mặc định luôn là 400**.

Nếu service được gọi bởi scheduler/message listener mà không có HTTP client, error cần chính sách xử lý khác. Nếu là một bug nội bộ (ví dụ service trả giá trị trái hợp đồng) thì có thể là 500; nếu trực tiếp do client nhập sai ở một boundary được xác minh, có thể mapping thành input validation error.

### 13.2. Business rule khác Jakarta annotation constraint

Một đơn hàng có `units=3` có thể vượt lượng tồn kho, dù `@Min(1)` hoàn toàn pass. Đây là **business conflict** hoặc domain rule, không phải type conversion. Tùy API, có thể chọn 409 Conflict/422 Unprocessable Content hoặc code nghiệp vụ khác, nhưng phải nhất quán với hợp đồng và semantics.

Không đưa lỗi business authorization hoặc database connectivity vào nhóm `CONSTRAINT_VIOLATION` chỉ vì có chữ “validation” trong log.

## 14. Chuẩn hóa bằng RFC 9457 Problem Details

Nếu API không muốn tự tạo JSON structure hoàn toàn, Spring Framework có `ProblemDetail` và `ErrorResponse` hỗ trợ RFC 9457.

Ví dụ ý tưởng:

```java
ProblemDetail problem =
        ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
problem.setTitle("Invalid input");
problem.setDetail("One or more fields are invalid");
problem.setProperty("code", "CONSTRAINT_VIOLATION");
problem.setProperty("fields", List.of("customer", "units"));
```

Đây là **fragment**, cần imports. Spring MVC có thể serialize `ProblemDetail` thành `application/problem+json` với các trường chuẩn `type`, `title`, `status`, `detail`, `instance` và extension properties.

Việc sử dụng RFC 9457 giúp công cụ/client hiểu status theo chuẩn mà vẫn giữ application-specific error codes. Đừng dùng chung một `detail` chứa raw exception messages có thể tiết lộ thông tin nhạy cảm. Nếu đa ngữ, resolve detail/title qua `MessageSource` và locale, còn `code` nên ổn định qua ngôn ngữ.

Nếu subclass đã extends `ResponseEntityExceptionHandler` như project chính, các override protected handler là cách ít rủi ro hơn việc đăng ký nhiều `@ExceptionHandler` cùng loại dẫn đến ambiguous mappings.

## 15. Vấn đề an toàn, privacy và logging

### 15.1. Không phản hồi giá trị bị từ chối một cách mù quáng

`FieldError.getRejectedValue()` và `ConstraintViolation.getInvalidValue()` có thể mang password, token, số giấy tờ, nội dung hồ sơ. Log cả object/form body có thể để lộ dữ liệu cá nhân.

Trong response, ưu tiên:
- Tên field công khai do API contract định nghĩa.
- Error code và giới hạn hợp lệ.
- Message chung, đã địa phương hóa và không chứa raw value.
- Request ID/correlation ID để người vận hành tra log.

### 15.2. Log server riêng, không đẩy stack trace cho client

Với `HttpMessageNotReadableException`, log cấu trúc an toàn như endpoint, error category, request ID, content-type và source exception class khi cần. Không log raw body mặc định và không đưa stack trace ra HTTP response.

Có thể theo dõi metric phân loại:
- `missing_parameter`
- `body_unreadable`
- `type_mismatch`
- `binding_failure`
- `constraint_violation`
- `handler_method_validation`

Giữ metric labels có cardinality thấp; không dùng giá trị request thật hoặc dynamic exception messages làm label.

### 15.3. Không lạm dụng 422

HTTP 400 phù hợp cho nhiều lỗi request malformed/missing/constraint trong mặc định Spring. 422 Unprocessable Content có thể phù hợp với một hợp đồng API cụ thể khi payload đúng kiểu và syntax nhưng nội dung không đáp ứng điều kiện nghiệp vụ. Tuy vậy **không tự đổi mọi `MethodArgumentNotValidException` thành 422**, nhất là khi nó có cả binding failures.

Nếu chọn 422, phải định nghĩa rõ ranh giới với 400 và test nhất quán cho mọi endpoint.

## 16. Checklist debug nhanh

1. **Đọc request thực tế:** HTTP method, URL, query, Content-Type, body có mặt không?
2. **Xác định field ở đâu:** `@RequestParam`/`@RequestHeader`, JSON `@RequestBody`, form `@ModelAttribute` hay multipart `@RequestPart`?
3. **Missing trước binding?** Required parameter/part/header có vắng mặt không?
4. **Input đã chuyển thành Java type được chưa?** `abc` không thành Integer là type mismatch, chưa phải `@Min`.
5. **JSON parse thành DTO được chưa?** Malformed JSON và JSON type mismatch thuộc message converter.
6. **DTO property null vì thiếu?** Dùng `@NotNull` nếu trường bắt buộc.
7. **Nullable wrapper hay primitive?** `Integer` phân biệt null với 0, `int` thường không.
8. **Có `@Valid`/`@Validated` đúng chỗ?** Field annotations một mình không bảo đảm argument validation chạy.
9. **Có direct method constraints?** `@Min` trên handler parameter có thể đổi exception sang `HandlerMethodValidationException`.
10. **Có class-level `@Validated` trên controller?** Có thể chuyển sang AOP path ngoài MVC built-in.
11. **Với `@ModelAttribute`, kiểm tra `FieldError.isBindingFailure()`** để không nhầm type mismatch với constraints.
12. **Với `BindingResult`, đúng vị trí ngay sau argument chưa?** Nếu không, controller có thể không được gọi.
13. **Với `ResponseEntityExceptionHandler`, dùng protected overrides đúng chữ ký phiên bản Spring.**
14. **Không hard-code mọi exception thành 400:** đặc biệt conversion config error và return contract error.
15. **Viết test cho từng nguyên nhân**, không chỉ kiểm tra HTTP status.
16. **Kiểm tra message/codes theo locale** nếu response đa ngữ.
17. **Không công bố raw input/stack traces**; dùng mã lỗi ổn định và request ID.

## 17. Lỗi hiểu sai thường gặp

| Nhận định | Thực tế |
| --- | --- |
| “Thiếu JSON field là thiếu `@RequestParam`” | JSON property được deserialize vào DTO rồi kiểm tra bằng `@NotNull`/`@NotBlank`; thường là Bean Validation |
| “JSON sai kiểu luôn là `MethodArgumentTypeMismatchException`” | JSON thường qua Jackson/`HttpMessageConverter` → `HttpMessageNotReadableException` |
| “`MethodArgumentNotValidException` chỉ chứa constraint errors” | Form binder có thể đưa type mismatch vào `BindingResult` |
| “`@Min` cũng kiểm tra chuỗi `abc`” | Phải chuyển được sang type phù hợp trước khi `@Min` đánh giá |
| “`@Valid` tự cấm null ở mọi field” | `@Valid` là cascade; field cần `@NotNull`/constraint thích hợp |
| “`@Min` tự cấm null” | `@Min` thường bỏ qua null; dùng thêm `@NotNull` |
| “Mọi lỗi từ `@Validated` đều là MVC method validation” | `@Service @Validated` thường đi qua AOP proxy, exception khác |
| “Một HTTP 400 cho biết chắc loại lỗi” | Missing, type mismatch, decoding, binding và validation đều có thể 400 |
| “`BindingResult` ở cuối method có thể bắt mọi lỗi” | Phải ngay sau argument và phạm vi lỗi có giới hạn |
| “Bắt `TypeMismatchException` là luôn trả 400” | Một số lỗi conversion do server config; cần tôn trọng status |
| “Return constraint sai cũng là client bad request” | Vi phạm hậu điều kiện phía server, thường 500 |
| “`MissingPathVariableException` luôn nghĩa là URL thiếu segment” | URL thiếu segment thường không match mapping; exception có thể là lỗi khai báo mapping |
| “Trả `ex.getMessage()` cho client giúp debug tốt hơn” | Có thể lộ thông tin nội bộ/PII; dùng mã ổn định và log an toàn |
| “`@RestControllerAdvice` nào cũng có thể định nghĩa trùng handlers” | Có thể gây ambiguous exception mappings; nếu extends `ResponseEntityExceptionHandler`, override protected methods |
| “Cứ dùng 422 cho Bean Validation” | Spring defaults thường 400; cần hợp đồng phân loại rõ và test |

## 18. Bài tập tự luyện

1. Đổi `@RequestParam("quantity") Integer` thành `@RequestParam(required=false) Integer` và kiểm tra missing vs `quantity=abc`.
2. Gửi `?quantity=` để quan sát `MissingServletRequestParameterException.isMissingAfterConversion()` khi conversion trả null.
3. Đổi `Integer units` thành `int units` trong record, gửi JSON thiếu `units` và giải thích vì sao lỗi có thể đổi.
4. Bỏ `@NotNull` trên `units`, giữ `@Min(1)`. Vì sao JSON thiếu field có thể không bị chặn?
5. Gửi body `{"units":{"unexpected":true}}` rồi `{"units":0}`, phân tích decoder error và validator error.
6. Thêm `@Valid` trên nested `delivery`, rồi lần lượt bỏ `@NotNull` và `@Valid` để nhận ra vai trò từng annotation.
7. Thêm `@Size(min=3)` trên `customer`; kiểm tra cùng một field có hai constraint cùng thất bại và thứ tự errors.
8. Thử `@ModelAttribute OrderForm` với `units=abc` và `label=""`; xem `FieldError.isBindingFailure()` trên từng field.
9. Thay cách trả một global error code bằng danh sách issues có `category=type/binding/constraint` theo từng field.
10. Đặt một direct `@Min` lên parameter khác của controller nhận DTO `@Valid`; xem exception có đổi sang `HandlerMethodValidationException` không.
11. Tạo một return-value constraint cố ý sai trong test riêng để xác minh response 500 và `RETURN_CONTRACT_VIOLATION`.
12. Thêm một required `@RequestHeader` và missing multipart part; viết exception mappings chuyên biệt cho mỗi loại.
13. Thử dữ liệu form đúng định dạng nhưng vi phạm custom Spring `Validator`; xác định loại `FieldError`.
14. Viết error DTO hoặc `ProblemDetail` có `instance`/request ID nhưng không expose raw rejected values.
15. Viết tests cho một locale tiếng Việt và một locale tiếng Anh, giữ machine-readable `code` không đổi.

**Ghi nhớ:** “Thiếu”, “sai kiểu” và “vi phạm constraint” là **ba loại khác nhau ở các bước khác nhau**. Phân loại bằng annotation location, argument resolver, converter, `BindingResult` và exception type, không bằng phép đoán từ thông điệp. Spring MVC cho sẵn `ResponseEntityExceptionHandler` để chuẩn hóa lỗi mà vẫn giữ đúng status, đặc biệt phân biệt lỗi do client gửi với lỗi hợp đồng return của server.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — REST error responses và RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — FieldError JavaDoc / isBindingFailure](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — RequestBody và BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — ModelAttribute binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — HandlerMethodValidationException JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Boot 3.5 — Testing Spring MVC via MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)