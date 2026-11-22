# Spring MVC: Bean Validation, binding lỗi và phản hồi đầu vào không hợp lệ

## 1. Mục tiêu và phạm vi

Trong Spring MVC, một request đi qua nhiều bước **trước khi controller gọi nghiệp vụ**: chọn handler → lấy tham số, đọc JSON/form → chuyển kiểu (binding) → áp dụng Bean Validation → gọi method của controller → xây dựng response. Đầu vào sai ở mỗi bước có thể dẫn đến **loại exception khác nhau**, nhưng API nên trả mã HTTP và cấu trúc lỗi **nhất quán, dễ kiểm thử, không làm lộ thông tin nhạy cảm**.

Bài học này hướng tới Spring Boot **3.5.x**, Spring Framework **6.2**, Java **17**, Servlet Spring MVC, JUnit Jupiter và MockMvc. Cơ chế Java Bean Validation dùng package `jakarta.validation`, không phải `javax.validation` của các dự án Spring Boot 2.x cũ.

Kết thúc bài, bạn có thể:

1. Phân biệt constraint validation với lỗi JSON parse và lỗi convert kiểu.
2. Dùng `@NotBlank`, `@NotNull`, `@Size`, `@Min`, `@Max` và `@Valid` đúng mục tiêu.
3. Hiểu khi nào xảy ra `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
4. Xử lý `BindingResult` ở đúng vị trí nếu controller muốn tự quyết định phản hồi.
5. Chuẩn hóa HTTP 400 với `@RestControllerAdvice` mà không tiết lộ rejected values hay stack trace.
6. Dùng `@WebMvcTest` + `MockMvc` để kiểm thử biên dưới/đúng/trên, JSON sai, form binding và query/path conversion.
7. Chứng minh service **không được gọi** khi input bị MVC từ chối.

### Những câu hỏi khác nhau

| Câu hỏi | Cơ chế | Ví dụ |
| --- | --- | --- |
| Request body có parse được không? | `HttpMessageConverter`/Jackson | JSON sai cú pháp hoặc `"quantity":"many"` |
| Dữ liệu có chuyển thành kiểu Java được không? | `WebDataBinder`, `ConversionService`, argument resolvers | `quantity=abc` với form field `Integer` |
| Giá trị Java đã chuyển kiểu có hợp lệ không? | Jakarta Bean Validation provider (thường Hibernate Validator) | `@Min(1)`, `@NotBlank` |
| Một tham số controller có constraint trực tiếp không? | Spring MVC method validation | `@RequestParam @Min(1) int quantity` |
| API sẽ gửi lỗi gì cho client? | `@RestControllerAdvice` hoặc `ResponseEntityExceptionHandler` | `400`, mã lỗi ổn định và trường vi phạm |
| Lỗi được phát hiện trước business call chưa? | MockMvc + Mockito verification | `verifyNoInteractions(service)` |

**Nguyên tắc:** HTTP 400 không phải một bằng chứng đủ. Một test tốt kiểm tra **status + body lỗi + không có side effect**.

## 2. Điều kiện bắt buộc: validation provider có trên classpath

Các annotation như `@NotBlank` và `@Min` định nghĩa constraint, nhưng để Bean Validation chạy cần một implementation của Jakarta Validation. Với Spring Boot 3.5, cách phổ biến là thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Starter này đưa Hibernate Validator và những dependency phù hợp vào ứng dụng. `spring-boot-starter-web` trong Boot 3.x **không nên được giả định** là đã bao gồm implementation validation. `spring-boot-starter-test` cung cấp JUnit/Mockito/Spring Test nhưng **không thay thế** starter validation trong ứng dụng.

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

Giữ version của các starter dưới quyền quản lý Spring Boot BOM/parent/plugin. Không tự trộn Hibernate Validator, Jakarta Validation API và Spring Framework của những major versions khác nhau.

### Jakarta constraints hay gặp

| Constraint | Áp dụng điển hình | Điều cần lưu ý |
| --- | --- | --- |
| `@NotNull` | Object, `Integer`, nested DTO | Chỉ cấm `null`; chuỗi trống vẫn hợp lệ |
| `@NotBlank` | `CharSequence`, ví dụ `String` | Cấm null/chuỗi toàn khoảng trắng |
| `@NotEmpty` | String/collection/array/map | Cấm null/rỗng, nhưng chuỗi toàn khoảng trắng có thể qua |
| `@Size(min,max)` | String/collection/array/map | Kiểm tra chiều dài/kích thước; null thường không bị loại |
| `@Min`/`@Max` | Các kiểu số nguyên/số phù hợp | Các cận là **bao gồm cả** giá trị biên |
| `@Positive`/`@PositiveOrZero` | Số | Lưu ý zero khác nhau |
| `@Pattern(regexp=...)` | String | Matcher kiểm tra regex, không thay business validation |
| `@Email` | String | Kiểm tra định dạng, không chứng minh email tồn tại |
| `@Past`/`@Future` | Date/time | Thời gian tham chiếu cần được kiểm soát trong test |
| `@Valid` | Object lồng nhau hoặc phần tử container | **Kích hoạt cascade**, tự nó không cấm null |
| `@Validated` | Annotation của Spring | Kích hoạt validation, có thể chọn **groups** |

**Quy tắc null:** nhiều constraint như `@Min`, `@Size` không loại null. Muốn field bắt buộc cần `@NotNull`/`@NotBlank` thích hợp. Với số lượng phải bắt buộc và nằm trong `[1,10]`, dùng `Integer` + `@NotNull @Min(1) @Max(10)`; dùng primitive `int` có thể khiến field JSON bị bỏ qua trở thành 0 thay vì phân biệt “thiếu” với “0”.

## 3. Luồng xử lý JSON và vị trí của @Valid

Ví dụ:

```java
public record CreateOrderRequest(
    @NotBlank(message = "sku must not be blank")
    String sku,
    @NotNull(message = "quantity required")
    @Min(value = 1, message = "quantity must be >= 1")
    @Max(value = 10, message = "quantity must be <= 10")
    Integer quantity,
    @NotNull(message = "address required")
    @Valid Address address
) {
    public record Address(
        @NotBlank(message = "city required") String city) {}
}
```

Nếu method là:

```java
@PostMapping
ResponseEntity<?> create(@Valid @RequestBody CreateOrderRequest body) {
    // Chỉ được gọi khi JSON và DTO đáp ứng điều kiện.
}
```

Đây là đoạn mô tả; ví dụ project chạy được đầy đủ nằm ở mục 8.

Các bước chính:

1. `@RequestBody` yêu cầu Spring MVC đọc nội dung thông qua `HttpMessageConverter`.
2. Jackson tạo `CreateOrderRequest` và chuyển các giá trị JSON sang kiểu Java.
3. Nếu message không đọc được, Spring có thể ném `HttpMessageNotReadableException`; **chưa đến bước Bean Validation**.
4. Khi JSON được parse, `@Valid` yêu cầu provider validate các constraints trên DTO.
5. Nếu DTO có field violations và không có `Errors`/`BindingResult` ngay sau đối số, Spring thường ném `MethodArgumentNotValidException` → HTTP 400.
6. Nếu hợp lệ, controller mới gọi `OrderService`; sau đó response thành công do controller định nghĩa.

Các request sau đều có thể tạo **400**, nhưng vì nguyên nhân khác nhau:

| Request | Giai đoạn thất bại | Lỗi thường gặp |
| --- | --- | --- |
| `{"sku":"   ","quantity":2,"address":{"city":"Huế"}}` | Bean Validation | `@NotBlank` |
| `{"sku":"SKU-1","quantity":0,"address":{"city":"Huế"}}` | Bean Validation | `@Min(1)` |
| `{"sku":"SKU-1","quantity":11,"address":{"city":"Huế"}}` | Bean Validation | `@Max(10)` |
| `{"sku":"SKU-1","address":{"city":"Huế"}}` | Bean Validation | `@NotNull` trên quantity |
| `{"sku":"SKU-1","quantity":2,"address":null}` | Bean Validation | `@NotNull` trên address |
| `{"sku":"SKU-1","quantity":2,"address":{"city":""}}` | Nested validation | `address.city` |
| `{"sku":"SKU-1","quantity":"many",...}` | Message conversion | `HttpMessageNotReadableException` |
| `{not-json` | JSON syntax | `HttpMessageNotReadableException` |
| Body thiếu hoàn toàn | `@RequestBody(required=true)` | Thường `HttpMessageNotReadableException` |

Trong các bảng trên, HTTP status và error body thực tế có thể bị tùy biến bằng `@ControllerAdvice`, cấu hình Boot/Spring hoặc converters. Bài mẫu sẽ định nghĩa contract phản hồi riêng để assertions ổn định.

### Nested validation: @Valid khác @NotNull

`@Valid Address address` chỉ dẫn validator đi sâu vào object khi object tồn tại. Nếu gửi `"address":null`, nested `city` không được validate vì không có object để cascade. Muốn address bắt buộc, dùng cả `@NotNull` **và** `@Valid`. Tương tự, với `List<@Valid LineItem>` cần đánh giá null list, list rỗng và từng phần tử theo hợp đồng bằng các constraints bổ sung.

## 4. @RequestBody và @ModelAttribute không có cùng binding pipeline

`@RequestBody` thường đọc JSON/XML qua message converter. `@ModelAttribute` dùng `WebDataBinder` để bind query parameters, form data, path variables và một số request values vào Java bean/command object.

Một form:

```java
public class OrderForm {
    @NotBlank
    private String sku;

    @NotNull
    @Min(1)
    private Integer quantity;

    public OrderForm() {}
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

Với `quantity=abc` trên form, binder cố chuyển String thành `Integer` và ghi nhận lỗi `typeMismatch`. Trong controller:

```java
@PostMapping("/form-preview")
ResponseEntity<?> preview(
        @Valid @ModelAttribute OrderForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(/* error DTO */);
    }
    return ResponseEntity.ok(/* preview */);
}
```

**Vị trí của `BindingResult` rất quan trọng:** nó phải xuất hiện **ngay sau** argument được bind/validate. Đặt `Model model`, `HttpServletRequest` hay tham số khác ở giữa có thể khiến Spring không ghép error result đúng object. Nếu không có `BindingResult`/`Errors` và input sai, Spring có thể ném `MethodArgumentNotValidException`. Với body JSON cũng có thể dùng `@Valid @RequestBody Dto dto, BindingResult result` nếu muốn xử lý lỗi ở method.

### BindingResult chứa gì?

- `hasErrors()`: có ít nhất một lỗi (field hoặc global).
- `getFieldErrors()`: các field errors; tên field có thể là `quantity` hoặc `address.city`.
- `getGlobalErrors()`: object-level rules như cross-field constraints.
- `getFieldError("quantity")`: một lỗi field cụ thể.
- `FieldError.getCode()`: thường mang mã như `typeMismatch`/`NotNull`/`Min`; các codes có thể được triển khai/resolve theo cấu hình.
- `getDefaultMessage()`: thông điệp default/đã resolve theo validation settings.

Nếu đã nhận `BindingResult`, controller phải **chủ động** xử lý `hasErrors()` trước khi gọi service. Chỉ thêm `BindingResult` rồi không kiểm tra sẽ vô tình để input sai đi tới nghiệp vụ.

### Bảo vệ khỏi over-posting/mass assignment

Không bind trực tiếp entity JPA với tất cả fields (ví dụ `isAdmin`, `price`, `balance`) từ client vào domain object. Dùng DTO/form riêng chỉ có các fields cho phép, hoặc `@InitBinder` với allowlist `setAllowedFields(...)` khi phù hợp. Validation **không thay** authorization hay các quy tắc “ai được sửa trường nào”.

## 5. Validation trên tham số method: @Min, @NotBlank và HandlerMethodValidationException

Từ Spring Framework 6.1, Spring MVC có **built-in method validation**. Một constraint đặt **trực tiếp** trên method parameter, chẳng hạn:

```java
@GetMapping("/estimate")
Estimate estimate(@RequestParam @Min(1) @Max(10) int quantity) {
    return new Estimate(quantity * 100);
}
```

có thể khiến request `/estimate?quantity=0` ném `HandlerMethodValidationException`, thay vì `MethodArgumentNotValidException` của một DTO riêng lẻ. Trong MVC 6.2, khi method validation áp dụng, nó cũng bao gồm các nested constraints qua `@Valid` và có thể **thay thế** validation ở argument resolver level.

Điểm cần phân biệt:

| Tình huống | Exception điển hình |
| --- | --- |
| `@Valid @RequestBody CreateOrderRequest`, không có trực tiếp method constraints khác | `MethodArgumentNotValidException` |
| `@Valid @ModelAttribute OrderForm`, không có `BindingResult`, không có method validation khác | `MethodArgumentNotValidException` |
| `@RequestParam @Min(1) int quantity` | `HandlerMethodValidationException` |
| `@PathVariable long id` mà request là `abc` | `MethodArgumentTypeMismatchException` |
| `@RequestParam int quantity` nhưng thiếu query parameter bắt buộc | `MissingServletRequestParameterException` |
| `@Valid @ModelAttribute OrderForm form, BindingResult result` với lỗi form | Controller đọc `BindingResult` và quyết định response |
| JSON không thể đọc | `HttpMessageNotReadableException` |

**Không gắn `@Validated` ở cấp class của controller một cách máy móc.** Với Spring MVC 6.1+, class-level `@Validated` có thể kích hoạt method validation thông qua AOP proxy, làm hành vi khác với built-in MVC method validation. Nếu muốn sử dụng built-in support và `HandlerMethodValidationException`, tài liệu Spring khuyên bỏ class-level `@Validated` ở controller. Với service beans, class-level `@Validated` vẫn thường được dùng để kích hoạt method validation qua proxy khi phù hợp.

**Cẩn thận với return-value validation:** `HandlerMethodValidationException` đối với lỗi đầu vào thường có HTTP 400; khi validation lỗi ở **giá trị trả về** của controller, đó là vấn đề phía server và thường là HTTP 500. Không ép mọi exception cùng type thành 400; nên dùng `ex.getStatusCode()` khi xử lý exception đó.

## 6. Thiết kế phản hồi lỗi ổn định

Một JSON response thuận tiện cho UI và tests:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "quantity",
      "message": "quantity must be >= 1"
    }
  ]
}
```

Ví dụ này chủ động phân biệt các mã ở tầng API:

| Code | Ý nghĩa | HTTP status |
| --- | --- | --- |
| `VALIDATION_ERROR` | DTO/form đã bind nhưng vi phạm constraints | 400 |
| `MALFORMED_BODY` | Không đọc được JSON/body thiếu/sai kiểu | 400 |
| `METHOD_VALIDATION` | Constraint trên controller method parameter/return | Theo exception, 400 cho input, 500 cho return |
| `MISSING_PARAMETER` | Thiếu request parameter bắt buộc | 400 |
| `TYPE_MISMATCH` | Path/query value không convert được | 400 |

Đây là **hợp đồng do ứng dụng mẫu tự định nghĩa**, không phải format mặc định bắt buộc của Spring Boot. Spring hỗ trợ `ProblemDetail` (RFC 9457) và `ResponseEntityExceptionHandler`, có thể thay bằng standard problem response nếu hệ thống đã chọn chuẩn đó. Dù dùng format nào, tests nên assert **mã lỗi ổn định, status và key fields**, không bám vào nội dung exception nội bộ hoặc thứ tự lỗi không được cam kết.

### Bảo mật trong response

- Không echo raw JSON, token, mật khẩu hoặc rejected value từ `FieldError.getRejectedValue()`.
- Không gửi stack trace, SQL/driver message, thông tin cấu trúc class/package ra client.
- Không cố hiển thị raw `HttpMessageNotReadableException.getMessage()` vì có thể chứa chi tiết converter và payload.
- Có thể trả field + message đã chọn; nếu multilingual, dùng `MessageSource` với mã lỗi stable và localization.
- Sắp xếp errors nếu frontend muốn thứ tự xác định; một input có nhiều constraint violations trên một field không đảm bảo thứ tự mặc định.
- Không biến mọi `Exception` thành HTTP 400; lỗi server bất ngờ phải được ghi nhận đúng trạng thái phía server.

## 7. Tổ chức dự án mẫu

Ví dụ đầy đủ nhắm **Spring Boot 3.5.0, Java 17, Maven**, không cần database, Docker hoặc network ngoài. `OrderService` là bean nhỏ; khi `@WebMvcTest` chạy, nó được thay bằng `@MockitoBean` để chắc chắn **input không hợp lệ không gọi service**.

Cây tệp:

```text
mvc-validation-demo/
├── pom.xml
└── src/
    ├── main/java/example/validation/
    │   ├── DemoApplication.java
    │   ├── OrderService.java
    │   ├── CreateOrderRequest.java
    │   ├── OrderForm.java
    │   ├── OrderApiError.java
    │   ├── OrderController.java
    │   └── OrderErrorHandler.java
    └── test/java/example/validation/
        └── OrderControllerTest.java
```

### 7.1. Maven pom.xml

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
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mvc-validation-demo</artifactId>
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
</project>
```

### 7.2. Application và service

`src/main/java/example/validation/DemoApplication.java`:

```java
package example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/example/validation/OrderService.java`:

```java
package example.validation;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final AtomicLong nextId = new AtomicLong(100);

    public long create(String sku, int quantity, String city) {
        // Bản demo: tạo ID trong bộ nhớ; không có database.
        return nextId.incrementAndGet();
    }
}
```

Bean `OrderService` thực có thể chạy khi khởi động application; trong test MVC slice nó được mock. **Không** nhầm câu lệnh tăng ID ở service mẫu với kiểm thử persistence: bài này chủ ý chỉ kiểm tra hợp đồng input/output của Spring MVC.

### 7.3. DTO JSON với nested validation

`src/main/java/example/validation/CreateOrderRequest.java`:

```java
package example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank(message = "sku must not be blank")
        @Size(min = 3, max = 20, message = "sku length must be 3..20")
        String sku,

        @NotNull(message = "quantity required")
        @Min(value = 1, message = "quantity must be >= 1")
        @Max(value = 10, message = "quantity must be <= 10")
        Integer quantity,

        @NotNull(message = "address required")
        @Valid Address address
) {
    public record Address(
            @NotBlank(message = "city required") String city) {
    }
}
```

Record constructor và Java 17 được hỗ trợ. JSON property names là `sku`, `quantity`, `address`. `@NotNull` trên address bảo vệ việc dereference `request.address().city()` trong controller sau khi validation PASS.

### 7.4. DTO form

`src/main/java/example/validation/OrderForm.java`:

```java
package example.validation;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderForm {
    @NotBlank(message = "sku must not be blank")
    private String sku;

    @NotNull(message = "quantity required")
    @Min(value = 1, message = "quantity must be >= 1")
    @Max(value = 10, message = "quantity must be <= 10")
    private Integer quantity;

    public OrderForm() {
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

`OrderForm` có constructor không tham số + setters để Spring bind form parameters một cách trực quan. Với `quantity=abc`, conversion bị lỗi và `BindingResult` ghi nhận field error trước khi service chạy.

### 7.5. Response contract

`src/main/java/example/validation/OrderApiError.java`:

```java
package example.validation;

import java.util.List;

public record OrderApiError(
        String code,
        List<Violation> errors
) {
    public record Violation(String field, String message) {
    }
}
```

Không có rejected values hay thông điệp từ exception nội bộ trong response. Đây là API contract ví dụ; trong một sản phẩm đã chuẩn hóa `ProblemDetail`, nên theo chuẩn của sản phẩm thay vì tạo hai định dạng.

### 7.6. Controller

`src/main/java/example/validation/OrderController.java`:

```java
package example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    public record Created(long id) {}
    public record Estimate(int total) {}
    public record Preview(String sku, Integer quantity) {}

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Created> create(
            @Valid @RequestBody CreateOrderRequest request) {
        long id = service.create(
                request.sku(),
                request.quantity(),
                request.address().city());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Created(id));
    }

    // Constraint trực tiếp trên @RequestParam: MVC method validation.
    @GetMapping("/estimate")
    public Estimate estimate(
            @RequestParam
            @Min(value = 1, message = "quantity must be >= 1")
            @Max(value = 10, message = "quantity must be <= 10")
            int quantity) {
        return new Estimate(quantity * 100);
    }

    // Endpoint minh họa lỗi chuyển kiểu ở @PathVariable.
    @GetMapping("/by-id/{id}")
    public Created byId(@PathVariable long id) {
        return new Created(id);
    }

    @PostMapping(
        path = "/form-preview",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formPreview(
            @Valid @ModelAttribute OrderForm form,
            BindingResult result) {
        // BindingResult PHẢI đứng ngay sau OrderForm.
        if (result.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(OrderErrorHandler.fromBinding(result));
        }

        return ResponseEntity.ok(
                new Preview(form.getSku(), form.getQuantity()));
    }
}
```

Chúng ta **không đặt `@Validated` ở class-level controller**, để `@RequestParam @Min/@Max` đi qua MVC built-in method validation của Spring Framework 6.2. Nếu đang dùng bản Spring cũ hơn, hoặc dự án có các annotation AOP method validation riêng, cần kiểm tra cơ chế thực tế trước khi áp dụng.

### 7.7. @RestControllerAdvice xử lý từng loại lỗi

`src/main/java/example/validation/OrderErrorHandler.java`:

```java
package example.validation;

import java.util.Comparator;
import java.util.List;

import example.validation.OrderApiError.Violation;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class OrderErrorHandler {

    public static OrderApiError fromBinding(BindingResult result) {
        List<Violation> fields = result.getFieldErrors().stream()
                .map(e -> new Violation(
                        e.getField(), e.getDefaultMessage()))
                .sorted(Comparator.comparing(Violation::field))
                .toList();

        return new OrderApiError("VALIDATION_ERROR", fields);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<OrderApiError> invalidDto(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(fromBinding(ex.getBindingResult()));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<OrderApiError> invalidMethod(
            HandlerMethodValidationException ex) {

        List<Violation> violations = ex.getAllValidationResults().stream()
                .flatMap(p -> p.getResolvableErrors().stream()
                        .map(e -> new Violation(
                                p.getMethodParameter().getParameterName()
                                        != null
                                ? p.getMethodParameter().getParameterName()
                                : "arg" + p.getMethodParameter()
                                        .getParameterIndex(),
                                e.getDefaultMessage())))
                .sorted(Comparator.comparing(Violation::field))
                .toList();

        // Trả 400 cho input validation, giữ 500 cho return validation.
        return ResponseEntity.status(ex.getStatusCode())
                .body(new OrderApiError(
                        "METHOD_VALIDATION", violations));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<OrderApiError> unreadableBody(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(new OrderApiError(
                        "MALFORMED_BODY",
                        List.of(new Violation(
                                "body", "invalid or missing JSON body"))));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<OrderApiError> missingQuery(
            MissingServletRequestParameterException ex) {
        return ResponseEntity.badRequest()
                .body(new OrderApiError(
                        "MISSING_PARAMETER",
                        List.of(new Violation(
                                ex.getParameterName(),
                                "required parameter missing"))));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<OrderApiError> typeMismatch(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.badRequest()
                .body(new OrderApiError(
                        "TYPE_MISMATCH",
                        List.of(new Violation(
                                ex.getName(), "invalid value type"))));
    }
}
```

Điểm kỹ thuật:

- `fromBinding` được dùng cả ở handler cho `MethodArgumentNotValidException` và endpoint form dùng `BindingResult`; vì vậy JSON/form có cùng cấu trúc field errors.
- Với nhiều lỗi trên một field, `Comparator.comparing(Violation::field)` chỉ cố định thứ tự **giữa các field**; không hứa thứ tự giữa hai message cùng field. Tests chỉ kiểm tra field/message khi một constraint cụ thể bị kích hoạt.
- `HandlerMethodValidationException.getStatusCode()` giữ nguyên 400 hay 500 theo input/return validation.
- Handler JSON không đưa `ex.getMessage()` ra client.
- Không catch toàn bộ `Exception` rồi trả 400: lỗi hệ thống hoặc bug trong controller cần được xử lý như lỗi server.

`@RestControllerAdvice` được Spring Boot MVC slice nhận diện; để dễ dự đoán, đặt trong package được application scan và test slice scan. Nếu dự án có component scan customization, hãy `@Import(OrderErrorHandler.class)` vào test khi cần, nhưng tránh import trùng/khác phạm vi không chủ ý.

## 8. Bộ MockMvc test cho thành công, validation và binding errors

Tệp `src/test/java/example/validation/OrderControllerTest.java`:

```java
package example.validation;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderService service;

    @Test
    void validJsonReturns201AndCallsService() throws Exception {
        when(service.create("SKU-1", 2, "Ha Noi")).thenReturn(101L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":2,
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(101));

        verify(service).create("SKU-1", 2, "Ha Noi");
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 10})
    void boundariesOneAndTenAreAccepted(int quantity)
            throws Exception {
        when(service.create("SKU-1", quantity, "Ha Noi"))
                .thenReturn(102L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":%d,
                         "address":{"city":"Ha Noi"}}
                        """.formatted(quantity)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(102));

        verify(service).create("SKU-1", quantity, "Ha Noi");
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 11})
    void outOfRangeQuantityIsRejectedBeforeService(int quantity)
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":%d,
                         "address":{"city":"Ha Noi"}}
                        """.formatted(quantity)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void blankSkuIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"   ","quantity":2,
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("sku must not be blank"));

        verifyNoInteractions(service);
    }

    @Test
    void skuTooLongIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"ABCDEFGHIJKLMNOPQRSTU",
                         "quantity":2,"address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("sku length must be 3..20"));

        verifyNoInteractions(service);
    }

    @Test
    void missingQuantityIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1",
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("quantity required"));

        verifyNoInteractions(service);
    }

    @Test
    void missingAddressIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":2}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("address required"));

        verifyNoInteractions(service);
    }

    @Test
    void nestedCityValidationIsApplied() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":2,
                         "address":{"city":""}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address.city"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("city required"));

        verifyNoInteractions(service);
    }

    @Test
    void malformedJsonIsRejectedBeforeService() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{not-json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));

        verifyNoInteractions(service);
    }

    @Test
    void incompatibleJsonTypeIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":"many",
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));

        verifyNoInteractions(service);
    }

    @Test
    void missingRequiredJsonBodyReturns400() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));

        verifyNoInteractions(service);
    }

    @Test
    void missingQueryParameterReturns400() throws Exception {
        mvc.perform(get("/api/orders/estimate"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void directConstraintOnQueryParameterUsesMethodValidation()
            throws Exception {
        mvc.perform(get("/api/orders/estimate")
                    .param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION"));

        verifyNoInteractions(service);
    }

    @Test
    void pathVariableWrongTypeReturns400() throws Exception {
        mvc.perform(get("/api/orders/by-id/not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("id"));

        verifyNoInteractions(service);
    }

    @Test
    void formTypeConversionErrorIsHandledByBindingResult()
            throws Exception {
        mvc.perform(post("/api/orders/form-preview")
                    .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                    .param("sku", "SKU-1")
                    .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void validFormReturnsPreviewWithoutServiceCall()
            throws Exception {
        mvc.perform(post("/api/orders/form-preview")
                    .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                    .param("sku", "SKU-1")
                    .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("SKU-1"))
                .andExpect(jsonPath("$.quantity").value(2));

        verifyNoInteractions(service);
    }
}
```

Các test ở trên là một class thực tế, không phụ thuộc database. Bài kiểm tra **MockMvc qua Spring MVC request binding thật**, chứ không gọi thẳng controller method bằng Java. `@MockitoBean` thay bean service trong context của MVC slice. Mockito state được Spring test infrastructure reset theo test lifecycle mặc định, tránh một stub làm nhiễm các method khác.

Các assertions không so thứ tự toàn bộ mảng errors khi có nhiều violations. Với một input chỉ làm sai một constraint, `errors[0]` đủ rõ. Khi kiểm tra nhiều fields cùng sai, nên dùng JSONPath kiểm tra sự tồn tại của đúng field và message mà không yêu cầu thứ tự không được hợp đồng bảo đảm.

### Điều không được suy ra từ MVC slice

- Không chứng minh database lưu đúng: service đang mock.
- Không chứng minh `@Transactional` của service hoạt động.
- Không chứng minh kết nối mạng thật, TLS hoặc API gateway.
- Không chứng minh authorization nếu application chưa có security policy/filter.
- Không chứng minh validation xảy ra với một DTO khi controller **quên `@Valid`**: tests lúc đó sẽ phát hiện service được gọi hoặc HTTP không còn 400.

Nếu cần kiểm tra cả controller + service + DB, dùng `@SpringBootTest` và `@AutoConfigureMockMvc` với test database/cleanup thích hợp; không ép `@WebMvcTest` nạp tất cả repository chỉ để kiểm chứng persistence.

## 9. Kết quả dự kiến và cách chạy

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Hoặc chỉ chạy class:

```bash
mvn test -Dtest=OrderControllerTest
```

Trong bài mẫu có **16 test methods**: 14 method `@Test` và 2 method `@ParameterizedTest`. Vì mỗi parameterized test chạy với hai giá trị, tổng là **18 test invocations**. Kỳ vọng **18 PASS, 0 FAILED, 0 SKIPPED** khi JDK 17+, dependencies và build phù hợp. Mã không in `System.out.println` nên không có stdout ứng dụng cố định; Maven Surefire sẽ ghi kết quả trong `target/surefire-reports`.

### Ma trận xác minh

| Nhóm | Request mẫu | Expected HTTP/JSON | Có gọi service không? |
| --- | --- | --- | --- |
| Thành công | POST SKU-1, quantity=2, city=Ha Noi | 201, id=101 | Có, đúng 1 |
| Biên min/max | quantity=1/10 | 201 | Có |
| Ngoài biên | quantity=0/11 | 400, VALIDATION_ERROR, field quantity | Không |
| SKU whitespace | `"sku":"   "` | 400, field sku | Không |
| SKU vượt 20 ký tự | 21 ký tự | 400, field sku | Không |
| Quantity thiếu | Không có quantity | 400, field quantity | Không |
| Address thiếu | Không có address | 400, field address | Không |
| Nested city rỗng | `"address":{"city":""}` | 400, field address.city | Không |
| JSON sai | `{not-json` | 400, MALFORMED_BODY | Không |
| Quantity JSON sai kiểu | `"many"` | 400, MALFORMED_BODY | Không |
| Body JSON thiếu | POST không body | 400, MALFORMED_BODY | Không |
| Thiếu query | GET estimate không quantity | 400, MISSING_PARAMETER | Không |
| Query vi phạm @Min | quantity=0 | 400, METHOD_VALIDATION | Không |
| Path sai kiểu | /by-id/not-a-number | 400, TYPE_MISMATCH | Không |
| Form bind sai kiểu | quantity=not-a-number | 400, field quantity | Không |
| Form hợp lệ | sku=SKU-1, quantity=2 | 200, preview | Không (preview không có nghiệp vụ) |

Mục tiêu quan trọng là **phát hiện regression về validation và request binding**. Khi sửa constraint từ `@Min(1)` thành `@Min(0)`, case quantity=0 phải FAIL. Nếu xóa `@Valid` khỏi body, những test invalid phải FAIL vì service mock có thể bị gọi hoặc kết quả không còn 400.

## 10. @Validated, validation groups và khi nào sử dụng

`@Valid` là annotation chuẩn của Jakarta Validation để kích hoạt object validation/cascade. `@Validated` là annotation Spring, ngoài kích hoạt validation còn có thể chọn groups.

Ví dụ khái niệm:

```java
public interface CreateGroup {}
public interface UpdateGroup {}

public record UserInput(
    @NotBlank(groups = CreateGroup.class)
    String initialPassword,

    @NotBlank(groups = UpdateGroup.class)
    String currentPassword
) {}

@PostMapping("/users")
public void create(@Validated(CreateGroup.class)
                   @RequestBody UserInput request) {
    // Kiểm tra nhóm CreateGroup.
}
```

Đây là **trích đoạn**, không đầy đủ imports/controller/service. Groups giúp tái sử dụng DTO với rule khác nhau, nhưng không nên dùng quá mức khi create/update thực sự có hợp đồng khác: hai DTO riêng thường dễ đọc và bảo mật hơn.

Phân biệt thêm:

- `@Validated` trên **service class** thường kích hoạt proxy-based method validation (nếu provider/config hỗ trợ).
- `@Validated` ở **controller class** có thể làm method validation đi qua AOP proxy thay vì cơ chế MVC 6.1+; khi muốn sử dụng `HandlerMethodValidationException` theo tài liệu MVC, không đặt class-level `@Validated`.
- Khi controller method có trực tiếp `@Min`/`@NotBlank` trên parameter, built-in method validation có thể áp dụng ngay cả khi không có `@Validated` ở class.
- `@Valid` tự nó **không phải constraint**, nên chỉ `@Valid` không đủ để kích hoạt built-in method validation trên tất cả kiểu tham số; nó thường là tín hiệu validate object ở resolver stage nếu không có method constraints khác.

## 11. Trường hợp khó: collection, null, cross-field và format dữ liệu

### Collection

Đừng cho rằng `@Valid List<OrderItem>` mà không có constraint container sẽ luôn xử lý hết các biến thể theo cùng đường argument resolver của một command object thông thường. Khi request là một array JSON ở top-level, một lựa chọn rõ hơn là wrapper DTO:

```java
public record BatchRequest(
    @NotEmpty
    java.util.List<@Valid Item> items
) {}

public record Item(@NotBlank String sku) {}
```

Đây là **trích đoạn**, cần các imports Jakarta Validation thích hợp. Wrapper làm đường validation của một command object rõ ràng, đồng thời cho phép giới hạn kích thước batch và custom constraint ở cấp request.

### Cross-field validation

Nếu quy tắc là “ngày kết thúc phải sau ngày bắt đầu” hoặc “khi thanh toán bằng thẻ thì token bắt buộc”, một `@NotBlank` trên từng field không đủ. Có thể tạo custom class-level constraint + `ConstraintValidator` hoặc dùng domain/service validation; quan trọng là test cả tổ hợp hợp lệ và không hợp lệ. Cross-field violation có thể là object/global error thay vì field error; nếu API muốn map vào một field, validator cần xây property node phù hợp.

**Lưu ý về ví dụ error handler:** `fromBinding` đang chỉ trả `getFieldErrors()` để mã ngắn, nên một class-level/global error có thể khiến `errors=[]`. Trong production, nên bổ sung `getGlobalErrors()` với location như `"_object"` và mã/message ổn định nếu có class-level constraints. Với JSON/form cùng field errors như bài này, nó đáp ứng ma trận đã định nghĩa.

### Null và chuỗi

- `@NotNull` không cấm `""` và `"   "`.
- `@NotBlank` cấm null và chuỗi chỉ gồm whitespace.
- `@Size(min=3)` không mặc nhiên cấm null.
- `@NotNull @Valid Nested` vừa bắt buộc object tồn tại vừa kiểm tra constraint bên trong.
- Dùng `Integer` khi cần phân biệt field số **không xuất hiện** với giá trị 0.

### Kiểu chuyển đổi và binding errors

- Form `quantity=abc`: binder không convert được `Integer`, lưu field error trong `BindingResult` khi controller có tham số liền kề.
- JSON `"quantity":"abc"`: Jackson không deserialize được `Integer`, dẫn tới `HttpMessageNotReadableException` trước validation.
- Query `?quantity=abc` với `@RequestParam int quantity`: thường `MethodArgumentTypeMismatchException`, không phải `MethodArgumentNotValidException`.
- Query bị thiếu với `@RequestParam` bắt buộc: thường `MissingServletRequestParameterException`.
- Multipart/form-data `@RequestPart` có quy tắc binding/validation phù hợp loại part; cần test multipart riêng nếu endpoint dùng upload.

Không “sửa” lỗi parse bằng cách catch chung rồi đặt default 0; như vậy client có thể bị chấp nhận sai dữ liệu và nghiệp vụ bị gọi không đúng.

## 12. ProblemDetail và ResponseEntityExceptionHandler

Spring Framework 6.x hỗ trợ `ProblemDetail` để tạo error response theo chuẩn Problem Details (RFC 9457), có status/title/detail/instance và các extension properties. Nếu API team đã dùng format này, có thể kế thừa `ResponseEntityExceptionHandler` để tùy biến các lỗi MVC:

```java
@RestControllerAdvice
class StandardProblemHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        ProblemDetail body = ProblemDetail.forStatus(status);
        body.setTitle("Validation failed");
        return handleExceptionInternal(
                ex, body, headers, status, request);
    }
}
```

Đây là **trích đoạn cần imports**, không đặt đồng thời vào project mẫu vì có thể tạo hai exception advices và làm test không còn một contract rõ ràng. Trong Spring Framework 6.2, override method nhận `HttpHeaders`, `HttpStatusCode` và `WebRequest` như trên; khi nâng major version, kiểm tra chữ ký.

Nếu **đã extends `ResponseEntityExceptionHandler`**, đừng tự tạo một `@ExceptionHandler(MethodArgumentNotValidException.class)` riêng trong cùng class để đăng ký trùng xử lý với inherited exception handler. Chọn **override protected handler** hoặc **độc lập `@ExceptionHandler`** như project mẫu, không phối hợp trùng lặp.

## 13. Kiểm tra thêm response status và security

Thông thường client input không hợp lệ sẽ trả HTTP 400, nhưng **không phải mọi lỗi request đều là 400**:

| Tình huống | Mã thường phù hợp | Nguyên tắc |
| --- | --- | --- |
| Invalid JSON, missing required body, type mismatch | 400 | Client cần sửa request |
| DTO Bean Validation fail | 400 | Không gọi nghiệp vụ |
| Thiếu authentication | 401 | Do Spring Security/API contract quyết định |
| Thiếu permission | 403 | Không biến thành validation 400 |
| Content-Type không hỗ trợ | 415 | Không bắt chung thành 400 |
| HTTP method không hỗ trợ | 405 | Giữ đúng method contract |
| Resource không tồn tại | 404 | Không nhầm với invalid format ID |
| Business conflict, ví dụ SKU hết hàng | 409 hoặc mã domain được định nghĩa | Business rule, không chỉ Bean Validation |
| Return-value validation fail | Thường 500 | Bug server/contract nội bộ |
| Lỗi database/remote chưa xử lý | 5xx phù hợp | Không che bằng `@ExceptionHandler(Exception.class)` trả 400 |

Không phải mọi response 400 đều do Bean Validation. Nếu viết test cho `@Valid`, hãy assert field/code cụ thể; nếu chỉ assert 400 thì một request sai Content-Type hoặc sai JSON cũng có thể PASS test mà controller chưa hề chạy validator.

Với Spring Security, request POST qua MockMvc có thể bị chặn bởi CSRF hoặc authentication trước validation. Khi test Spring Security, dùng các test utilities hợp lệ như `spring-security-test`, `@WithMockUser` và CSRF request post-processor theo chính sách dự án. Đừng tắt security filters để làm một test validation pass rồi dùng nó làm bằng chứng endpoint đã an toàn.

## 14. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `@Valid` không có tác dụng | Thiếu provider hoặc thiếu `@Valid` trên controller argument | Thêm validation starter; kiểm tra annotation/import |
| DTO quantity thiếu vẫn được nhận | Dùng primitive `int` hoặc không có `@NotNull` | Dùng `Integer` + `@NotNull` khi field bắt buộc |
| Nested object không được validate | Thiếu `@Valid` trên field; null không bị `@Valid` cấm | Thêm `@Valid` + `@NotNull` theo contract |
| Form `quantity=abc` không có exception như dự kiến | Controller dùng `BindingResult` liền kề nên nhận lỗi cục bộ | Kiểm tra `result.hasErrors()` và trả 400 |
| BindingResult không dùng được | Đặt sau một tham số khác hoặc sai argument | Đặt ngay sau validated form/body |
| `HandlerMethodValidationException` xuất hiện thay `MethodArgumentNotValidException` | Có constraint trực tiếp trên parameter hoặc method validation áp dụng | Handle cả hai kiểu |
| Controller có `@Validated` làm behavior khác | Method validation qua AOP proxy | Bỏ class-level `@Validated` nếu muốn MVC built-in validation |
| JSON sai kiểu được trả 400 nhưng thiếu field details | Lỗi Jackson xảy ra trước Bean Validation | Có mã `MALFORMED_BODY` và thông điệp an toàn |
| `@Size` cho String trống không như mong đợi | `@Size` không thay `@NotBlank` | Chọn đúng constraint và test null/empty/whitespace |
| Không có message mong muốn | Message interpolation, locale, bundle khác | Dùng stable error code, test message khi hợp đồng cam kết |
| Tests chập chờn vì thứ tự FieldErrors | Mỗi field có nhiều violations, thứ tự không bảo đảm | Không assert thứ tự trừ khi API sắp xếp rõ |
| `@WebMvcTest` không tìm thấy service | Slice không scan service bình thường | Dùng `@MockitoBean` hoặc `@Import` đúng phạm vi |
| Advice không được áp dụng | Component scan/test slice filter khác dự kiến | Kiểm tra `@RestControllerAdvice` và package/import |
| Mọi input sai thành 500 | Không có validator/exception mapping hoặc exception bị xử lý sai | Debug resolved exception trong MockMvc và thêm handler đúng |
| Test chỉ gọi trực tiếp controller | Bỏ qua HttpMessageConverter và MVC binding | Dùng MockMvc request thật |
| Bị lộ giá trị mật khẩu trong lỗi | Echo rejected values/raw exception | Không trả `getRejectedValue()` hoặc stack trace |
| Boot 4 lỗi import `@WebMvcTest` | Test module thay đổi | Dùng focused starter và package Boot 4 tương ứng |

## 15. Bài tập mở rộng

1. **Nhiều lỗi một request:** gửi SKU trắng và quantity 0, kiểm tra response có **cả hai field names** mà không dựa vào thứ tự mặc định.
2. **Global error:** thêm custom class-level constraint kiểm tra mối quan hệ giữa SKU và quantity; mở rộng handler để bao phủ `getGlobalErrors()`.
3. **Validation groups:** tạo Create vs Update contracts; so sánh hai DTO riêng với `@Validated(Group.class)`.
4. **JSON null vs missing:** test từng trường và đảm bảo response ổn định.
5. **Query số không hợp lệ:** thêm test `/estimate?quantity=abc` để so sánh type mismatch với range constraint.
6. **Nested collection:** thêm `List<@Valid Item>` với `@NotEmpty` và kiểm tra đường lỗi theo index phần tử.
7. **Content-Type:** gửi JSON với `text/plain` và xác nhận 415, không phải 400 validation.
8. **Locale:** nếu dùng message bundles, kiểm tra `Accept-Language` và đảm bảo error code không phụ thuộc ngôn ngữ.
9. **Security:** tích hợp `spring-security-test` và kiểm tra 401/403 không bị handler validation biến thành 400.
10. **Integration:** dùng `@SpringBootTest + @AutoConfigureMockMvc` với service thật để xác minh request hợp lệ gây side effect chính xác; request sai không ghi dữ liệu.

Khi làm bài tập, tách **validation rule tests** khỏi **service business tests**. Validation không được dùng để thay domain authorization, inventory consistency hoặc transaction constraints.

## 16. Checklist nghiệm thu

- [ ] Project có `spring-boot-starter-validation`/provider tương thích với Boot version?
- [ ] Imports đúng `jakarta.validation.*` với Boot 3/4?
- [ ] `@Valid` đặt trên controller DTO cần validate, `@Valid` cũng đặt trên nested field?
- [ ] Các field bắt buộc dùng `@NotNull`/`@NotBlank` thay vì chỉ dùng `@Min`/`@Size`?
- [ ] Có test ngay dưới, tại và ngay trên ngưỡng `[1,10]`?
- [ ] JSON malformed, sai kiểu, body thiếu và DTO constraint violation được phân biệt?
- [ ] Form `@ModelAttribute` có `BindingResult` ngay sau argument và kiểm tra `hasErrors()`?
- [ ] Có test `MethodArgumentNotValidException` và `HandlerMethodValidationException`?
- [ ] Direct parameter constraints chạy qua MVC built-in validation, không bị class-level AOP `@Validated` làm khác ý định?
- [ ] Controller advice trả status, code và fields ổn định, không leak rejected values?
- [ ] Error handler không gom mọi exception vào 400?
- [ ] MockMvc test assert response lẫn `verifyNoInteractions(service)` ở các case invalid?
- [ ] Test không nhầm MVC slice với persistence/HTTP transport integration?
- [ ] Thông điệp lỗi/localization có đúng API contract và không phụ thuộc thứ tự không xác định?
- [ ] Khi nâng Spring Boot, đã đối chiếu test starter, exception APIs và imports?

## 17. Tài liệu chính thức để tra cứu

1. [Spring Framework 6.2 — Controller Method Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` vs `HandlerMethodValidationException`, `@Valid` và direct constraints.
2. [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): JSON conversion, `@Valid`, `BindingResult`.
3. [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): data binding, conversion errors và local `BindingResult`.
4. [Spring Framework — Web MVC Validator](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html): cấu hình global/local Validator.
5. [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`/`ResponseEntityExceptionHandler`.
6. [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): provider và `@Validated` cho service method.
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, MockMvc và bean mock.
8. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, nested validation, groups và validators.
9. [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/): cập nhật cấu trúc test modules nếu ứng dụng dùng Boot 4.

### Lưu ý Spring Boot 4

Dòng Spring Boot 4 sử dụng các starter test theo công nghệ; với Spring MVC, kiểm tra `spring-boot-starter-webmvc-test` và package mới của `@WebMvcTest`. Dự án mẫu ở trên **nhắm 3.5.x**, không được đổi mỗi số version rồi giữ nguyên imports. Phần logic Jakarta Validation và nguyên tắc phân loại lỗi vẫn là nền tảng, nhưng luôn kiểm tra tài liệu chính thức theo version thực tế.

**Ghi nhớ:** Bean Validation trả lời **“giá trị Java có hợp lệ không?”**; binding/conversion trả lời **“request có tạo được giá trị Java không?”**; controller advice quyết định **“client nhận thông báo lỗi an toàn, ổn định như thế nào?”**. MockMvc cần kiểm tra cả ba, cùng việc **không gọi nghiệp vụ** với input không hợp lệ.
