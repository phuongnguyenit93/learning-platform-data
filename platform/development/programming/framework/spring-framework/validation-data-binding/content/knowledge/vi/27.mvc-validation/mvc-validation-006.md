# Phân biệt cơ chế tích hợp MVC với @Validated qua AOP trong Spring Framework

## 1. Vấn đề: cùng một constraint nhưng có nhiều đường thực thi

Trong Spring Framework, cả controller lẫn service đều có thể dùng các constraint của Jakarta Validation như `@NotBlank`, `@Min`, `@NotNull` hoặc `@Valid`. Tuy nhiên, **annotation chỉ là metadata**: phải có một cơ chế đọc metadata và chủ động kiểm tra thì ràng buộc mới phát huy tác dụng.

Ví dụ:

```java
@GetMapping("/orders")
public String find(@RequestParam @Min(1) long id) {
    return "order-" + id;
}
```

Một request `GET /orders?id=0` sẽ được xử lý bởi bộ máy Spring MVC. Còn trong một Spring service:

```java
@Service
@Validated
public class OrderService {

    public String find(@Min(1) long id) {
        return "order-" + id;
    }
}
```

Một lời gọi `orderService.find(0)` có thể được kiểm tra bởi **Spring AOP method-validation proxy**, nhưng chỉ khi bean/proxy và hạ tầng validation đã cấu hình phù hợp. Hai con đường không giống nhau về lúc kích hoạt, loại lỗi, xử lý HTTP và giới hạn kỹ thuật.

Thậm chí với controller, Spring MVC còn phân biệt **validation từng argument DTO** với **method validation của toàn bộ handler**.

Trong bài này ta tách rõ ba nhánh:

1. **MVC argument validation:** `@Valid @RequestBody`, `@Valid @ModelAttribute` hoặc `@Valid @RequestPart` trên một command object.
2. **MVC built-in method validation:** Spring Framework **6.1+** kiểm tra trực tiếp constraint trên method parameters/return của handler `@RequestMapping`, **không cần AOP proxy**.
3. **AOP method validation:** `@Validated` ở class level (thường trên service) cộng `MethodValidationPostProcessor`, kiểm tra lời gọi **đi qua proxy**.

**Mục tiêu:** biết nhánh nào thực sự chạy, khi nào nên có/không có `@Validated` ở controller, phân biệt `MethodArgumentNotValidException` với `HandlerMethodValidationException` và `ConstraintViolationException`, chạy ví dụ Java 17+ với Spring MVC và viết test để chứng minh.

> **Phạm vi phiên bản:** Nội dung dùng Spring Framework 6.1+/6.2.x và Spring Boot 3.x, Jakarta Validation (`jakarta.validation.*`). Đặc biệt, cơ chế MVC built-in method validation được bổ sung ở **Spring Framework 6.1**, nên không nên suy diễn hành vi này ngược về Spring MVC 6.0. WebFlux có hệ thống handler riêng và cần xem tài liệu dành cho reactive stack.

## 2. Bản đồ kiến trúc: validation xảy ra ở đâu?

### 2.1. Request HTTP đi qua Spring MVC

```text
HTTP request
    |
    v
DispatcherServlet
    |
    v
HandlerMapping chọn controller method
    |
    v
Argument resolvers / WebDataBinder / HttpMessageConverter
    |
    +--> Bind JSON/form/query/path thành method arguments
    |
    +--> Nếu DTO @Valid/@Validated đủ điều kiện:
    |       argument validation
    |       -> MethodArgumentNotValidException khi lỗi
    |
    +--> Nếu handler cần method validation do @Constraint trực tiếp:
            MVC built-in method validation (Framework 6.1+)
            -> HandlerMethodValidationException khi lỗi
    |
    v
Gọi handler, nhận return value
    |
    +--> Nếu có return constraints, MVC cũng có thể
          kiểm tra return sau khi handler chạy
    |
    v
Xử lý response / exception resolvers
```

Đây là luồng khái niệm, không phải thứ tự nội bộ của mọi thành phần trong mọi cấu hình. Điểm thiết yếu là **MVC đã có điểm tích hợp vào quá trình bind arguments và gọi handler**. Nó không bắt buộc dùng proxy để kiểm tra method constraints ở controller từ Spring 6.1 trở đi.

### 2.2. Lời gọi method trên Spring bean qua AOP

```text
Một Spring bean gọi serviceProxy.someMethod(args)
    |
    v
Spring AOP proxy / MethodValidationInterceptor
    |
    +--> validate method parameters
    |       nếu có violations: thường throw
    |       ConstraintViolationException
    |
    v
Target service method thực thi
    |
    v
Method return value
    |
    +--> validate method return
    |       nếu có violations: throw exception
    |
    v
Caller nhận kết quả
```

Đây là một cơ chế khác: proxy bao quanh **lời gọi phương thức trên bean Spring**. Nó không biết request HTTP được parse như thế nào, không trực tiếp quản lý `BindingResult` hay ánh xạ lỗi thành mã HTTP 400.

### 2.3. Cùng dùng Jakarta Validation nhưng không cùng integration

Ở tầng dưới, cả MVC và AOP đều có thể nhờ Jakarta Validation provider (thường Hibernate Validator) kiểm tra các constraint. Điểm khác biệt là **ai gọi validator, trong thời điểm nào và ai chuyển violation thành response/exception**. Không phải do `@Min` ở MVC “mạnh hơn” `@Min` ở service.

## 3. Bảng so sánh cốt lõi

| Tiêu chí | MVC argument validation | MVC built-in method validation (6.1+) | AOP `@Validated` method validation |
| --- | --- | --- | --- |
| Mục tiêu | Một DTO/command object được bind từ request | Toàn bộ hợp đồng method của controller | Hợp đồng method của bean đi qua proxy |
| Khởi phát | `@Valid` hoặc `@Validated` trên `@RequestBody`/`@ModelAttribute`/`@RequestPart` thích hợp | Có constraint như `@Min`/`@NotBlank` **trực tiếp** trên parameter hoặc return | `@Validated` class level và `MethodValidationPostProcessor` |
| Có cần AOP? | Không | **Không** | **Có** |
| Gắn với HTTP? | Có, là argument resolution của MVC | Có, là handler method của MVC | Không bắt buộc; dùng được ở service không có HTTP |
| Constraint trên DTO property? | Có qua cascade | Có thể bao gồm qua `@Valid` khi method validation được kích hoạt | Có thể cascade khi method parameter/return dùng `@Valid` |
| Lỗi thường gặp | `MethodArgumentNotValidException` | `HandlerMethodValidationException` | `ConstraintViolationException` mặc định |
| HTTP status theo framework | Thường 400 cho input sai | Input thường 400; lỗi **return value** là 500 | Không mặc định là HTTP 400; phụ thuộc cách xử lý exception |
| `BindingResult` | Có thể đặt ngay sau DTO để xử lý cục bộ | Có thể xử lý lỗi cục bộ theo quy tắc method validation | Không phải hợp đồng riêng của AOP proxy |
| Lời gọi Java trực tiếp không đi qua MVC | Không chạy binding/validation MVC | Không chạy validation MVC | Chỉ chạy nếu đi qua proxy đủ điều kiện |
| Self-invocation `this.method()` | Không liên quan với request binding | Không phải điểm kiểm tra MVC của request | Thường **bỏ qua** advice của proxy |

**Không gộp ba cột này thành một cơ chế.** Ví dụ, `@Valid` trên DTO không nhất thiết kích hoạt method validation; còn `@Validated` class-level ở controller có thể đưa bạn sang nhánh AOP cũ thay vì nhánh MVC built-in mà bạn muốn sử dụng.

## 4. `@Valid`, `@Validated` và `@Constraint`: vai trò thật sự

### 4.1. `@Valid` của Jakarta Validation

```java
@PostMapping("/people")
public ResponseEntity<?> create(
        @Valid @RequestBody PersonRequest request) {
    // ...
}
```

`@Valid` biểu thị **cascaded validation**: kiểm tra các constraint trên object `PersonRequest` sau khi dữ liệu được parse/bind. Nó không phải constraint trực tiếp với `message`, `groups`, `payload` như `@NotBlank`.

Nếu một handler **không cần method validation** vì không có direct constraints trên parameters/return, trường hợp `@Valid @RequestBody` như trên thường được argument resolver xử lý và có thể ném `MethodArgumentNotValidException` khi không có `BindingResult` ngay sau.

### 4.2. `@Validated` của Spring

`org.springframework.validation.annotation.Validated` có hai vai trò khác nhau tùy **vị trí**:

- **Trên một argument DTO** (ví dụ `@Validated(Create.class) @RequestBody Request request`): đóng vai trò validation hint/group, tương tự `@Valid` ở khía cạnh kích hoạt validation nhưng có thể chỉ rõ groups.
- **Trên class Spring bean** (ví dụ `@Service @Validated`): là dấu hiệu để `MethodValidationPostProcessor` tìm bean cần áp method-validation **AOP proxy**.

`@Validated` **không phải** một Jakarta `@Constraint`; nó không tự kiểm tra một `String` hoặc `int`. Bạn vẫn cần `@NotBlank`, `@Min`, một custom constraint, `@Valid`... trên đúng target.

**Điểm dễ nhầm:** Dùng `@Validated` trên một DTO argument để chọn groups không đồng nghĩa phải gắn `@Validated` lên cả controller class. Tác dụng và đường đi có thể khác nhau.

### 4.3. Constraint trực tiếp trên handler parameter

```java
@GetMapping("/page")
public String page(@RequestParam("size") @Min(1) int size) {
    return "size=" + size;
}
```

`@Min` là một **direct constraint** trên method parameter. Với Spring MVC 6.1+ có Jakarta Validation provider, nó kích hoạt nhánh **MVC built-in method validation**. Khi `size=0`, lỗi thường đi qua `HandlerMethodValidationException`, không phải `MethodArgumentNotValidException`.

Tương tự, constraint đặt **trực tiếp lên method** như:

```java
@NotBlank
@GetMapping("/token")
public String token() {
    return "";
}
```

đánh dấu một **return value constraint**. Sau khi handler chạy, MVC có thể kiểm tra return value và báo lỗi qua `HandlerMethodValidationException`, với HTTP status **500** đối với vi phạm hậu điều kiện của server theo contract của exception.

### 4.4. Method có cả direct constraint lẫn DTO `@Valid`

```java
@PostMapping("/items")
public ResponseEntity<?> create(
        @RequestParam("count") @Min(1) int count,
        @Valid @RequestBody ItemRequest request) {
    // ...
}
```

Vì `@Min` nằm trực tiếp trên parameter `count`, handler này **cần method validation**. Spring MVC 6.1+ để method validation kiểm tra cả `count` và các constraint bên trong `ItemRequest` qua `@Valid`; nó **thay thế** validation riêng của argument resolver cho DTO trong trường hợp này, tránh kiểm tra trùng.

Do đó cùng một DTO `ItemRequest` với `name=""` có thể dẫn tới **loại exception khác nhau** tùy chữ ký controller:
- Handler chỉ có `@Valid @RequestBody ItemRequest`: thường `MethodArgumentNotValidException`.
- Handler có thêm direct `@Min` trên parameter khác: thường `HandlerMethodValidationException`.

Đây là thay đổi hành vi đáng chú ý khi nâng cấp sang Framework 6.1+ hoặc bổ sung direct constraints vào controller.

## 5. Vì sao nên bỏ `@Validated` ở class controller nếu dùng MVC 6.1+?

Tài liệu Spring Framework nêu rõ: **nếu một controller có class-level `@Validated`, method validation được áp dụng qua AOP proxy**. Để dùng **MVC built-in method validation** có từ Spring 6.1, hãy **gỡ `@Validated` khỏi controller class**.

### 5.1. Mẫu nên tránh khi muốn MVC built-in

```java
@RestController
@Validated // Lựa chọn method validation qua AOP proxy.
@RequestMapping("/api")
public class SampleController {

    @GetMapping("/quantity")
    public String quantity(
            @RequestParam("count") @Min(1) int count) {
        return "count=" + count;
    }
}
```

Mã này không có nghĩa không hợp lệ ở mọi phiên bản; trước Spring 6.1, AOP là cách thường dùng để enforce direct constraints ở controller. Nhưng với MVC 6.1+, nó **không phải** cấu hình khuyến nghị nếu bạn muốn cơ chế built-in và loại exception/handling chuẩn cho MVC.

### 5.2. Mẫu khuyến nghị trên MVC 6.1+

```java
@RestController
@RequestMapping("/api")
public class SampleController { // Không @Validated ở class.

    @GetMapping("/quantity")
    public String quantity(
            @RequestParam("count") @Min(1) int count) {
        return "count=" + count;
    }
}
```

Nếu có provider Jakarta Validation và MVC được cấu hình đúng, direct `@Min` sẽ được xác minh **trong luồng handler invocation của MVC**.

**Không suy diễn:** “Xóa `@Validated` khỏi controller” **không** có nghĩa bỏ validation. Nó chỉ chọn cơ chế MVC built-in để validate method. `@Valid`/`@Validated` đặt **trên DTO argument** để kích hoạt validation/nhóm có thể vẫn cần thiết.

### 5.3. Service vẫn có thể dùng `@Validated`

```java
@Service
@Validated
public class PricingService {

    public BigDecimal price(
            @NotBlank String sku,
            @Min(1) int quantity) {
        return BigDecimal.TEN;
    }
}
```

Ở service, không có Spring MVC argument resolver nào bao quanh lời gọi từ code khác. Nếu muốn enforce method contracts, `@Validated` class level và method-validation AOP là lựa chọn bình thường, với điều kiện bean được quản lý và lời gọi đi qua proxy.

Đừng “gỡ tất cả `@Validated` khỏi dự án” chỉ vì đọc hướng dẫn dành riêng cho **MVC controller class**.

## 6. Ngoại lệ: không thể xử lý cả ba nhánh bằng một giả định

### 6.1. `MethodArgumentNotValidException`

Thường xuất hiện khi Spring MVC bind và validate một **DTO argument riêng lẻ**, ví dụ:

```java
public record NewUser(
        @NotBlank(message = "name.required") String name) {}

@PostMapping("/users")
public void create(@Valid @RequestBody NewUser user) {
    // ...
}
```

Nếu body chứa `{"name":""}` và handler không cần method validation, Spring MVC thường trả HTTP 400 và báo `MethodArgumentNotValidException`. Ngoại lệ này mang dữ liệu binding/validation như `BindingResult`, `FieldError`, giúp trả lỗi theo field.

### 6.2. `HandlerMethodValidationException`

Đây là ngoại lệ Spring MVC dành cho **handler method validation**. Các tình huống:
- Direct parameter `@Min(1)` sai.
- Direct parameter `@NotBlank` sai.
- Một DTO `@Valid` sai **trong handler đã kích hoạt method validation**.
- Return value constraint sai, ví dụ `@NotNull` đặt trên method nhưng method trả `null`.

Spring MVC mặc định xử lý input validation failure dưới dạng **400 Bad Request**. Đối với return value validation failure, exception biểu thị một lỗi hậu điều kiện phía server và dùng **500 Internal Server Error**. Lỗi return không phải lỗi người dùng gửi request, nên không nên chuyển thành 400 một cách mù quáng.

### 6.3. `ConstraintViolationException` qua AOP

`MethodValidationPostProcessor` mặc định có thể dùng `MethodValidationInterceptor` ném `jakarta.validation.ConstraintViolationException` khi parameter/return của method được proxy không hợp lệ. Ngoại lệ này chứa tập `ConstraintViolation<?>` và **không tự** gắn với HTTP status 400.

Nếu một controller gọi service và service ném exception này, cần một chính sách xử lý thích hợp: lỗi đầu vào đã được quy về client có thể là 400/422 tùy API; vi phạm invariant hoặc return contract của service có thể là 500. Không tạo handler “bất kỳ ConstraintViolationException nào đều là 400” vì có thể che giấu lỗi lập trình.

Từ Spring 6.1, `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` có thể chuyển violations thành kết quả Spring và ném `org.springframework.validation.method.MethodValidationException` thay vì `ConstraintViolationException`. Cần biết cấu hình thực tế trước khi viết exception handler.

### 6.4. Bảng điều hướng exception

| Tình huống | Nhánh xử lý chính | Loại lỗi thường gặp |
| --- | --- | --- |
| `@Valid @RequestBody Dto`, không cần method validation | MVC argument resolver | `MethodArgumentNotValidException` |
| `@Valid @ModelAttribute Dto`, không cần method validation | MVC binder | `MethodArgumentNotValidException` |
| `@Valid @RequestPart Dto`, không cần method validation | MVC part + converter | `MethodArgumentNotValidException` |
| `@Min(1) @RequestParam int` của controller 6.1+ không class `@Validated` | MVC built-in method | `HandlerMethodValidationException` |
| Handler có direct `@Min` và DTO `@Valid` bị sai | MVC built-in method | `HandlerMethodValidationException` |
| Controller return `@NotNull` sai | MVC built-in method return | `HandlerMethodValidationException` (thường 500) |
| `@Validated` Spring service nhận invalid parameters qua proxy | Spring AOP | `ConstraintViolationException` (mặc định) |
| AOP với adapt enabled | Spring AOP | `MethodValidationException` |
| Thiếu `@RequestParam(required=true)` | MVC argument resolver/binding | `MissingServletRequestParameterException`, không phải Bean Validation |
| Chuỗi query `"abc"` không đổi được sang `int` | MVC type conversion | Lỗi kiểu `MethodArgumentTypeMismatchException`, không phải `@Min` |

Bảng mô tả cơ chế mặc định/thông dụng; cấu hình `@ControllerAdvice`, `BindingResult` và phiên bản Framework có thể thay đổi phản hồi thực tế. Khi debug, ưu tiên nhìn exception type và stack trace thật.

## 7. Ví dụ Spring Boot 3.5.6 + Java 17 chạy độc lập

Mục tiêu ví dụ là **thấy cả ba con đường trong một ứng dụng**:

1. Endpoint `GET /api/quantity?count=0`: direct `@Min` trên controller ⇒ MVC built-in method validation.
2. Endpoint `POST /api/profiles`: chỉ `@Valid @RequestBody` ⇒ MVC argument validation.
3. Endpoint `POST /api/mixed`: kết hợp direct `@Min` và DTO `@Valid` ⇒ MVC built-in method validation bao phủ cả DTO.
4. Một `ReservationService` có `@Validated` class level ⇒ method validation qua AOP proxy.
5. Kiểm thử tự động phân biệt chính **exception class**, không chỉ HTTP status.

Ví dụ dùng Spring Boot **3.5.6** (một bản có thật thuộc họ Boot 3.5, dùng Spring Framework 6.2.x). Đây là phiên bản minh họa nhất quán, không ngụ ý là phiên bản Boot mới nhất. Không sao chép thẳng dependency version giữa các major Boot khác nhau mà không kiểm tra tương thích.

### 7.1. Cấu trúc thư mục

```text
mvc-vs-aop-validation/
├── pom.xml
└── src/
    ├── main/java/demo/validation/
    │   ├── ValidationModesApplication.java
    │   ├── ProfileRequest.java
    │   ├── ReservationService.java
    │   └── DemoController.java
    └── test/java/demo/validation/
        └── ValidationModesTest.java
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
    <artifactId>mvc-vs-aop-validation</artifactId>
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
            <artifactId>spring-boot-starter-aop</artifactId>
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

- `spring-boot-starter-web` cung cấp Spring MVC và embedded Servlet container.
- `spring-boot-starter-validation` cung cấp Jakarta Validation integration/provider.
- `spring-boot-starter-aop` làm rõ hạ tầng proxy dành cho service; trong một dự án khác, phụ thuộc này có thể đã đến từ starter khác.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test và `MockMvc`.
- Dependency versions được Boot parent quản lý.

### 7.3. `ValidationModesApplication.java`

```java
package demo.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationModesApplication.class, args);
    }
}
```

Không cần khai báo thêm `MethodValidationPostProcessor` thủ công nếu hạ tầng auto-configuration của Boot đã thiết lập nó. Đăng ký một bean post-processor thứ hai khi không cần có thể tạo hành vi proxy phức tạp không mong muốn.

### 7.4. `ProfileRequest.java`

```java
package demo.validation;

import jakarta.validation.constraints.NotBlank;

public record ProfileRequest(
        @NotBlank(message = "profile.name.blank") String name) {
}
```

Constraint thuộc **thuộc tính của DTO**. Điều quyết định loại exception không phải annotation này thay đổi, mà là **method của controller** chứa DTO có hay không có direct method constraints.

### 7.5. `ReservationService.java` — AOP method validation

```java
package demo.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import java.util.concurrent.atomic.AtomicInteger;

@Service
@Validated
public class ReservationService {

    private final AtomicInteger calls = new AtomicInteger();

    @NotBlank(message = "reservation.result.blank")
    public String reserve(
            @NotBlank(message = "reservation.code.blank") String code,
            @Min(value = 1, message = "reservation.count.small")
            int count) {

        calls.incrementAndGet();
        return code.repeat(count);
    }

    public int calls() {
        return calls.get();
    }
}
```

**Vì sao cần `@Validated` ở đây?** Đây là Spring service bean, không phải handler của MVC. `MethodValidationPostProcessor` tìm class có `@Validated` và đặt method-validation advice lên proxy. Khi bean khác inject `ReservationService` rồi gọi `reserve("", 2)` **qua proxy**, constraint của method parameter được kiểm tra trước khi body chạy; bộ đếm `calls` không tăng.

`@NotBlank` đặt trên method là constraint **return value**, được kiểm tra sau khi method trả. Ví dụ luôn tạo return hợp lệ nếu inputs hợp lệ, nhưng hậu điều kiện vẫn được thể hiện để học cách phân biệt hai giai đoạn.

Cũng cần lưu ý: `@Validated` trên class không bắt buộc mọi method đều có violations. Method `calls()` không có constraint; nó chỉ cung cấp số lần business method đã được thực thi để test minh bạch.

### 7.6. `DemoController.java` — MVC built-in, không AOP controller

```java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class DemoController {

    // Cố ý KHÔNG đặt @Validated lên controller class.

    @GetMapping("/quantity")
    public Map<String, Integer> quantity(
            @RequestParam("count") @Min(1) int count) {
        return Map.of("count", count);
    }

    @PostMapping("/profiles")
    public Map<String, String> profile(
            @Valid @RequestBody ProfileRequest request) {
        return Map.of("name", request.name());
    }

    @PostMapping("/mixed")
    public Map<String, Object> mixed(
            @RequestParam("count") @Min(1) int count,
            @Valid @RequestBody ProfileRequest request) {
        return Map.of(
                "count", count,
                "name", request.name());
    }
}
```

Có ba điểm cần quan sát:

- `quantity()` có `@Min` **trực tiếp** trên parameter ⇒ Spring MVC 6.1+ dùng method validation tích hợp.
- `profile()` chỉ có `@Valid` trên một DTO argument ⇒ Spring MVC dùng argument validation thông thường; không cần AOP.
- `mixed()` có `@Min` trực tiếp ⇒ Spring MVC dùng method validation, **bao phủ** việc validate nested `ProfileRequest` qua `@Valid`.

Đây là cách so sánh cùng một DTO `ProfileRequest` ở hai đường khác nhau mà không phải thêm `@Validated` ở class controller.

### 7.7. `ValidationModesTest.java` — test cả ba con đường

```java
package demo.validation;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationModesTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReservationService service;

    @Test
    void mvcDirectConstraintUsesHandlerMethodValidation() throws Exception {
        mvc.perform(get("/api/quantity")
                        .param("count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(result ->
                        assertInstanceOf(
                                HandlerMethodValidationException.class,
                                result.getResolvedException()));
    }

    @Test
    void mvcDtoOnlyUsesArgumentValidation() throws Exception {
        mvc.perform(post("/api/profiles")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(result ->
                        assertInstanceOf(
                                MethodArgumentNotValidException.class,
                                result.getResolvedException()));
    }

    @Test
    void mixedHandlerValidatesNestedDtoAtMethodLevel() throws Exception {
        mvc.perform(post("/api/mixed")
                        .param("count", "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(result ->
                        assertInstanceOf(
                                HandlerMethodValidationException.class,
                                result.getResolvedException()));
    }

    @Test
    void mvcAcceptsValidInput() throws Exception {
        mvc.perform(get("/api/quantity")
                        .param("count", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void serviceProxyRejectsInvalidInputBeforeMethodBody() {
        int before = service.calls();

        ConstraintViolationException error =
                assertThrows(
                        ConstraintViolationException.class,
                        () -> service.reserve("", 2));

        assertEquals(before, service.calls());
        assertEquals(1, error.getConstraintViolations().size());
    }

    @Test
    void serviceProxyAcceptsValidInput() {
        assertEquals("ABAB", service.reserve("AB", 2));
    }
}
```

Chạy test từ thư mục dự án:

```bash
mvn test
```

**Kỳ vọng 6 test đều pass trong môi trường Maven/JDK 17 hợp lệ.** Những assertion có ý nghĩa sau:

| Test | Ý nghĩa của kết quả |
| --- | --- |
| `mvcDirectConstraintUsesHandlerMethodValidation` | MVC trả 400 và resolved exception là `HandlerMethodValidationException` |
| `mvcDtoOnlyUsesArgumentValidation` | DTO có `@Valid` độc lập trả 400 với `MethodArgumentNotValidException` |
| `mixedHandlerValidatesNestedDtoAtMethodLevel` | Cùng DTO sai nhưng handler có direct `@Min` nên exception thuộc nhánh method |
| `mvcAcceptsValidInput` | Giá trị `count=2` qua MVC được chấp nhận |
| `serviceProxyRejectsInvalidInputBeforeMethodBody` | Lời gọi service qua proxy ném `ConstraintViolationException`; bộ đếm không tăng |
| `serviceProxyAcceptsValidInput` | Service với input hợp lệ trả `"ABAB"` |

Dùng `MockMvc` ở ba test đầu để quan sát exception **sau khi MVC exception resolver đã xử lý**. Dùng `assertThrows` khi gọi trực tiếp Spring service bean đã được inject để chứng minh **AOP proxy**. Đây là hai cấp kiểm thử khác nhau.

Thứ tự thực thi các test không được đảm bảo. Vì thế test đếm số lần gọi service ghi lại `before = service.calls()` ngay trước lời gọi sai, không khẳng định tổng số lần gọi trong test suite luôn bằng 0.

Nếu test MVC direct constraint **không** ra `HandlerMethodValidationException`, trước tiên kiểm tra Spring Framework có tối thiểu 6.1 và class controller không có `@Validated`. Nếu test service **không** ném exception, kiểm tra `@Validated` ở service, bean post-processor, dependency validation/AOP và đối tượng được inject có thực sự là proxy hay không.

### 7.8. Chạy ứng dụng và kiểm tra bằng HTTP

Khởi động:

```bash
mvn spring-boot:run
```

Gửi request hợp lệ:

```bash
curl -i 'http://localhost:8080/api/quantity?count=2'
```

Kỳ vọng HTTP **200** với JSON:

```json
{"count":2}
```

Input vi phạm direct constraint:

```bash
curl -i 'http://localhost:8080/api/quantity?count=0'
```

Kỳ vọng HTTP **400**. Hình dạng body lỗi tùy Spring Boot error handling và cấu hình Problem Details; không giả định JSON body luôn chứa một trường cụ thể nếu bạn chưa viết `@ControllerAdvice`.

Một DTO vi phạm:

```bash
curl -i -X POST \
  'http://localhost:8080/api/profiles' \
  -H 'Content-Type: application/json' \
  -d '{"name":""}'
```

Cũng thường trả HTTP **400**, nhưng đó là nhánh **argument validation**. Chỉ nhìn status 400 sẽ không biết được provider/framework đã đi qua cơ chế nào; vì vậy test phải đối chiếu loại exception như `ValidationModesTest`.

Cùng DTO ấy ở handler kết hợp:

```bash
curl -i -X POST \
  'http://localhost:8080/api/mixed?count=1' \
  -H 'Content-Type: application/json' \
  -d '{"name":""}'
```

Kỳ vọng HTTP **400**, nhưng nhánh **MVC method validation** được kích hoạt bởi `@Min` ở parameter `count`.

## 8. `BindingResult` và `Errors` tương tác thế nào?

Đây là ranh giới quan trọng của MVC mà AOP service không có.

### 8.1. Xử lý lỗi DTO locally

```java
@PostMapping("/profiles")
public ResponseEntity<?> create(
        @Valid @RequestBody ProfileRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "profile.invalid"));
    }

    return ResponseEntity.ok(Map.of("name", request.name()));
}
```

Đây là đoạn **minh họa** thay thế method `profile()` ở ví dụ chính, không phải đoạn cần chép thêm nguyên xi vào `DemoController.java`. Bạn cần import `BindingResult` và `ResponseEntity`. `BindingResult` phải xuất hiện **ngay sau** argument được bind/validate. Khi validation errors được xử lý cục bộ, controller có thể trả mã lỗi riêng mà không cần `MethodArgumentNotValidException` đi lên global handler.

### 8.2. Khi handler đồng thời có method validation

```java
@PostMapping("/mixed")
public ResponseEntity<?> mixed(
        @Valid @RequestBody ProfileRequest request,
        BindingResult errors,
        @RequestParam("count") @Min(1) int count) {
    // ...
}
```

Với MVC 6.1+ method validation, Spring vẫn xem xét `Errors`/`BindingResult` của parameter được hỗ trợ. Handler chỉ được gọi khi **mọi validation errors đều thuộc những parameters có `Errors` hoặc `BindingResult` ngay sau** để xử lý. Nếu còn lỗi ở một parameter khác, chẳng hạn `count=0` mà không có `BindingResult` tương ứng, `HandlerMethodValidationException` vẫn có thể được ném.

Vì vậy không kết luận rằng “đã có một `BindingResult` trong method thì mọi lỗi method validation đều được nuốt”. `BindingResult` chỉ gắn với **argument liền trước** và chỉ bao phủ lỗi trong phạm vi được MVC hỗ trợ.

### 8.3. AOP không tiêu thụ `BindingResult` như MVC

`MethodValidationInterceptor` trong service không tham gia MVC argument binding. Nếu bạn truyền một đối tượng `BindingResult` bất kỳ vào service, interceptor không tự coi đó là kênh nhận lỗi cho method parameter trước. Nó vẫn xử lý Jakarta constraint violations theo chính sách AOP (thường ném `ConstraintViolationException`).

## 9. Validation nhóm (groups): đừng đặt `@Validated` sai vị trí

Ví dụ một DTO có quy tắc bổ sung trong nhóm `Publish`:

```java
public interface Publish {}

public record ArticleRequest(
        @NotBlank String title,
        @Size(min = 20, groups = Publish.class) String body) {}
```

Đây là đoạn minh họa, cần import `jakarta.validation.constraints.NotBlank` và `Size`.

### 9.1. Chọn nhóm cho một MVC DTO argument

```java
@PostMapping("/articles")
public void publish(
        @Validated(Publish.class)
        @RequestBody ArticleRequest request) {
    // ...
}
```

`@Validated(Publish.class)` nằm **trên argument** và truyền validation hint/group thích hợp cho việc validate DTO. Nếu chỉ yêu cầu nhóm `Publish`, các constraint thuộc `Default` như `@NotBlank` không tự được kiểm tra, trừ khi có kế thừa/group sequence hoặc cấu hình khác. Để áp cả hai nhóm, có thể khai báo `@Validated({Default.class, Publish.class})` khi đúng yêu cầu.

### 9.2. Chọn nhóm ở AOP service

```java
@Service
@Validated(Publish.class)
public class PublishingService {

    public void publish(
            @NotBlank(groups = Publish.class) String title) {
        // ...
    }
}
```

Ở service, class-level `@Validated(Publish.class)` **là annotation được AOP sử dụng để chọn bean và groups**. Đừng áp công thức “xóa @Validated ở controller” vào service này; hai nơi có vai trò khác nhau.

### 9.3. Không trộn class-level controller AOP và DTO groups tùy tiện

Nếu controller cần validate DTO theo nhóm, ưu tiên `@Validated(Publish.class)` **ở argument cần nhóm**, thay vì chuyển cả controller sang class-level `@Validated` chỉ để có groups. Class-level controller annotation có hệ quả kiến trúc lớn hơn: đổi đường đi method validation sang AOP proxy, làm khác loại exception và khả năng tích hợp với MVC.

Với method-level groups và validation trực tiếp ở handler, hãy kiểm tra tài liệu/framework version cùng các hạn chế hiện tại thay vì suy luận rằng mọi tùy chọn group của AOP service tự động có cùng ý nghĩa trong MVC built-in.

## 10. Vì sao Spring AOP đôi khi không validate dù đã có `@Validated`?

AOP proxy không phải máy ảo chèn kiểm tra vào mọi method call. Nó chỉ tham gia các lời gọi **đi qua proxy** và thỏa điều kiện advisor/interceptor.

### 10.1. Self-invocation

```java
@Service
@Validated
public class PaymentService {

    public void process() {
        charge(-1); // Lời gọi từ chính target: thường bỏ qua proxy.
    }

    public void charge(@Min(1) int amount) {
        // ...
    }
}
```

Đoạn minh họa này cần các import Spring/Jakarta Validation. Khi `process()` chạy trong cùng target, lời gọi `this.charge(-1)` không đi qua proxy bên ngoài. Vì vậy method validation advice thường không thực thi cho `charge` ở nhánh ấy.

Cách xử lý thường là tách thành bean khác và gọi bean đó qua dependency injection, hoặc điều chỉnh kiến trúc để lời gọi đi qua proxy. Nếu một luồng nội bộ bắt buộc được enforce không phụ thuộc Spring AOP, cân nhắc gọi Jakarta Validation API trực tiếp tại điểm kiểm soát phù hợp hoặc thể hiện invariant bằng kiểm tra Java thuần.

### 10.2. Object tự tạo bằng `new`

```java
PaymentService service = new PaymentService();
service.charge(-1);
```

Đây **không phải** Spring-managed proxy; chỉ có `@Validated` trong source không khiến một object do `new` tạo ra được Spring AOP kiểm tra.

### 10.3. Giới hạn proxy JDK/CGLIB

- JDK dynamic proxy làm việc qua interface; class-based proxy dựa trên subclass/CGLIB.
- Private method không phải join point có thể được advice theo kiểu proxy thông thường.
- Final method không thể bị override để class-based proxy advice theo cách tiêu chuẩn.
- Interface/implementation, method visibility, bean lifecycle và cách lời gọi được resolve có thể ảnh hưởng việc advisor nhìn thấy method metadata.

Khi debug, không chỉ tìm annotation mà phải xác minh **đường gọi thực** và bean được lấy từ Spring container.

### 10.4. MVC built-in cũng có ranh giới riêng

Spring MVC built-in method validation chỉ tham gia **handler invocation qua DispatcherServlet và cơ chế MVC**. Nếu bạn gọi trực tiếp method của controller từ test như một hàm Java, đó không phải một HTTP handler invocation; không thể lấy việc “không thấy exception” khi gọi trực tiếp để kết luận MVC validation không hoạt động.

Hãy dùng `MockMvc` hoặc một HTTP test đi qua MVC để chứng minh nhánh này.

## 11. Đọc và chuẩn hóa lỗi đúng lớp

### 11.1. Nếu chọn `ResponseEntityExceptionHandler`

Spring Framework cung cấp `ResponseEntityExceptionHandler` cho MVC. Trong một `@ControllerAdvice` kế thừa nó, bạn có thể override các điểm xử lý tương ứng cho:

- `handleMethodArgumentNotValid(...)`: DTO argument validation.
- `handleHandlerMethodValidationException(...)`: MVC method validation.

Những method này cho phép chuyển lỗi thành `ProblemDetail`/`ResponseEntity` nhất quán. Chữ ký chính xác phụ thuộc Spring Framework version; khi triển khai thật, mở JavaDoc của phiên bản đang dùng, không copy chữ ký của một release khác. Cũng có thể dùng `@ExceptionHandler` phù hợp, tránh khai báo trùng với handler đã được superclass cung cấp.

### 11.2. Với `HandlerMethodValidationException`

Ngoại lệ có cấu trúc method validation results, cho phép truy cập kết quả theo từng method parameter. Ngoài `getAllValidationResults()`, Spring cung cấp cách duyệt qua các kết quả/visitor API. Nếu phải trả về tên field/parameter cho client, nên dựa vào metadata và cấu trúc kết quả thay vì tách message chuỗi tùy ý.

Với lỗi return value, hãy log đủ ngữ cảnh phục vụ vận hành và trả **server error** thay vì đổ trách nhiệm cho request. Không đưa mọi giá trị invalid trả trực tiếp tới client vì có thể chứa thông tin nhạy cảm.

### 11.3. Với `ConstraintViolationException` từ service AOP

Bạn có thể duyệt:

```java
for (ConstraintViolation<?> violation
        : exception.getConstraintViolations()) {

    String path = violation.getPropertyPath().toString();
    String message = violation.getMessage();
    // Chuyển thành error code / structured response theo API contract.
}
```

Đây là fragment minh họa với biến `exception` là `ConstraintViolationException` và import Jakarta Validation tương ứng. `ConstraintViolation` không đồng nghĩa `FieldError` của MVC. Một method parameter có thể có path như `reserve.code` hoặc `reserve.arg0` tùy `ParameterNameProvider` và compiler flag.

Nếu controller gọi service mà service ném `ConstraintViolationException`, nên xử lý nó tại **biên ứng dụng** theo phân loại lỗi và chính sách API. Đừng để mọi exception unchecked tự biến thành lỗi 500 không rõ ý nghĩa, cũng đừng mặc định mọi violation đều là lỗi input của HTTP client.

### 11.4. Lỗi parsing/binding không phải lỗi Bean Validation

Ví dụ:
- Thiếu required query parameter `count`: `MissingServletRequestParameterException`.
- Truyền `count=abc` để bind vào `int`: lỗi chuyển kiểu.
- JSON không đọc được: `HttpMessageNotReadableException`.

Những lỗi này có thể xảy ra **trước khi** `@Min(1)` có một giá trị `int` hợp lệ để kiểm tra. Đó là lý do trả về 400 không chứng minh lỗi đến từ Jakarta Validation.

## 12. Bài tập đối chiếu: chỉ thay một annotation

Đây là cách thực hành hữu ích khi nâng cấp dự án.

### Thí nghiệm A: controller không class-level `@Validated`

```java
@RestController
public class ExampleController {

    @GetMapping("/example")
    public String get(@RequestParam("n") @Min(1) int n) {
        return Integer.toString(n);
    }
}
```

Trong Spring MVC 6.1+ với provider được cấu hình, gửi `?n=0`. Ghi nhận `HandlerMethodValidationException`. Đây là nhánh built-in.

### Thí nghiệm B: thêm `@Validated` lên class controller

```java
@RestController
@Validated
public class ExampleController {
    // Cùng handler như trên.
}
```

Lúc này bạn đã yêu cầu đường đi method validation qua **AOP** cho controller. Nếu method validation hoạt động qua proxy, loại exception có thể đổi sang `ConstraintViolationException` hoặc exception đã được adapt; cơ chế xử lý HTTP cũng có thể khác. Không chỉ so sánh HTTP status, hãy xem exception thực tế, proxy và cấu hình post-processor.

Đây là thí nghiệm riêng, **không sửa `DemoController.java` của ví dụ chạy chính** nếu bạn muốn giữ sáu test trước đó đúng.

### Thí nghiệm C: giữ controller MVC built-in, thêm `@Validated` cho service

Đặt `@Validated` ở `ReservationService` như code mục 7. Sử dụng `MockMvc` kiểm tra controller và `assertThrows` kiểm tra service. Bạn sẽ thấy hai con đường cùng tồn tại mà không mâu thuẫn:
- Controller validation bởi MVC.
- Service validation bởi AOP.

Đó thường là cách tách trách nhiệm mong muốn.

### Thí nghiệm D: gỡ `@Min` khỏi `mixed()`

Nếu `mixed()` chỉ còn `@Valid @RequestBody ProfileRequest` (và không có direct method constraints khác), hãy dự đoán exception cho `{"name":""}`. Trong cấu hình thông thường, validation quay về nhánh argument resolver và `MethodArgumentNotValidException`. Không cần thay annotation nào trên record `ProfileRequest`.

## 13. Checklist khi nâng cấp từ Spring 6.0 sang 6.1+

1. **Xác nhận phiên bản:** ứng dụng có Framework 6.1+ và Jakarta Validation provider không?
2. **Kiểm kê controller có class-level `@Validated`:** đây thường là dấu hiệu method validation qua AOP ở controller cũ.
3. **Quyết định chuyển sang MVC built-in:** với controller cần built-in, bỏ class-level `@Validated` theo hướng dẫn Spring. Không xóa bừa các argument-level `@Valid`/`@Validated`.
4. **Kiểm kê các method direct constraints:** `@Min`, `@NotBlank`, `@NotNull` trên parameters và return.
5. **Cập nhật exception handling:** thêm xử lý `HandlerMethodValidationException` bên cạnh `MethodArgumentNotValidException`; tránh handler chỉ hỗ trợ một loại.
6. **Test lại các handler kết hợp DTO `@Valid` và direct constraints:** exception có thể đổi từ argument-level sang method-level, không phải do DTO rule đã mất.
7. **Kiểm tra `BindingResult` nằm đúng vị trí:** ngay sau argument cần xử lý; đừng giả định một `BindingResult` bắt mọi lỗi của handler.
8. **Giữ service `@Validated` khi cần:** AOP method validation ở service không bị MVC built-in thay thế.
9. **Kiểm tra self-invocation và proxy:** logic gọi từ cùng bean có thể né method-validation AOP.
10. **Phân biệt lỗi input và return:** input bad request, return invariant failure thường là server error.
11. **Viết test cho exception type, không chỉ HTTP status:** 400 có thể là missing parameter, JSON parse, DTO validation hoặc handler method validation.
12. **Không đăng ký trùng hạ tầng:** tránh tự tạo nhiều post-processors/advisors nếu Spring Boot đã cấu hình.

## 14. Các lỗi hiểu sai thường gặp

| Nhận định sai | Sự thật | Cách sửa |
| --- | --- | --- |
| “Có `@Valid` là có method validation” | `@Valid` là cascade; DTO argument validation có thể chạy riêng | Kiểm tra có direct `@Constraint` trên handler hay không |
| “Spring MVC method validation luôn phải có `@Validated` trên controller” | Từ Framework 6.1, MVC hỗ trợ built-in không cần class-level `@Validated` | Gỡ class-level annotation khi chủ đích dùng MVC built-in |
| “Controller có `@Validated` chắc chắn vẫn đi qua MVC built-in mới” | Class-level `@Validated` chọn đường AOP proxy theo tài liệu Spring | Tách annotation controller/service đúng vai trò |
| “Service `@Validated` không cần proxy” | Method validation AOP phụ thuộc lời gọi qua Spring proxy | Kiểm tra bean thực tế và self-invocation |
| “`@Valid @RequestBody` sai luôn là `MethodArgumentNotValidException`” | Khi handler có direct constraints, MVC method validation có thể bao phủ cả DTO | Test handler kết hợp và xử lý `HandlerMethodValidationException` |
| “Cả 3 exception đều tự là HTTP 400” | AOP exception không có default HTTP status; MVC return failure thường 500 | Phân loại nguồn lỗi và thời điểm |
| “`BindingResult` ở đâu cũng bắt hết lỗi” | Gắn với argument ngay trước và cơ chế validation tương ứng | Đặt đúng vị trí, xét lỗi ở parameters khác |
| “Gọi controller method trực tiếp là test MVC validation” | Direct Java call không đi qua DispatcherServlet | Sử dụng MockMvc/HTTP integration test |
| “`@Validated` trên DTO argument giống hệt trên class controller” | Ở argument nó chọn validation hints/groups, ở class có thể kích hoạt proxy | Đọc theo vị trí đặt annotation |
| “`@NotBlank` chạy ngay khi JSON string được parse” | Cần bước validation sau binding/argument resolution | Có provider và annotation kích hoạt ở đúng tầng |
| “Không thấy lỗi nghĩa là đã pass validation” | Có thể validation không được kích hoạt, không có proxy hoặc annotation sai vị trí | Test invalid input và assert type exception |
| “Tự throw `ConstraintViolationException` là chức năng mặc định của `Validator.validate()`” | API Jakarta Validation trực tiếp trả `Set<ConstraintViolation>` | Caller quyết định throw, khác interceptor AOP |

## 15. Tình huống thiết kế thực tế

### 15.1. Controller nhận DTO, service thực hiện nghiệp vụ

Thiết kế thường hợp lý:

```text
Client HTTP
   |
   v
Spring MVC controller
 - bind JSON/form/query
 - @Valid DTO + direct parameter constraints
 - chuyển lỗi input thành response nhất quán
   |
   v
Spring service bean
 - @Validated method contracts qua AOP (nếu cần)
 - kiểm tra bất biến nghiệp vụ và authorization
 - xử lý transactional logic
   |
   v
Repository / external services
```

**Không cần đặt `@Validated` lên controller class chỉ vì service có `@Validated`.** Mỗi tầng có trách nhiệm riêng.

Validation DTO ở biên giúp phản hồi nhanh cho client; method validation ở service giữ hợp đồng khi service được gọi từ nhiều nguồn (HTTP, scheduler, message consumer, CLI), **nếu** các lời gọi đều qua proxy được cấu hình đúng. Các invariant quan trọng vẫn cần được bảo vệ ở domain/service chứ không giao toàn bộ cho các annotation HTTP.

### 15.2. Có bị validate trùng không?

Có thể. Ví dụ controller `@Valid` một DTO, sau đó service được `@Validated` lại có `@Valid` cho cùng DTO. Hai tầng kiểm tra ở hai ranh giới khác nhau; không phải lúc nào cũng thừa, vì service còn được gọi từ nguồn khác. Tuy nhiên, với một request, hệ thống có thể tốn hai lần validate.

Khác với trường hợp trên, khi **cùng một handler MVC** cần method validation do có direct constraints, Spring 6.1+ thiết kế method validation **thay thế** argument validation riêng tương ứng, tránh double validation bên trong cùng một handler. Đừng nhầm hai kịch bản này.

### 15.3. Khi nào gọi `ExecutableValidator` thủ công?

Nếu một thư viện/integration không đi qua Spring MVC hay AOP proxy, vẫn có thể lấy:

```java
jakarta.validation.Validator validator = /* injected validator */;
var executables = validator.forExecutables();

var problems = executables.validateParameters(
        targetObject, reflectedMethod, argumentArray);
```

Đây là đoạn minh họa vì `targetObject`, `reflectedMethod`, `argumentArray` phải được xác định theo tình huống. API trả `Set<ConstraintViolation<T>>`. Nó chứng minh cả MVC và AOP chỉ là **các cách tích hợp để gọi cơ chế validation**, không phải là cơ chế duy nhất mà Jakarta Validation cung cấp.

### 15.4. Khi nào không nên dùng constraint annotations?

Có những bất biến phải kiểm tra trong domain logic (ví dụ số lượng tồn kho tại thời điểm giao dịch, quyền thao tác, sự tồn tại của entity trong DB). `@Min`/`@NotBlank` không thay thế transaction, authorization hoặc kiểm tra race condition. MVC validation và service method validation giải quyết **hợp đồng dữ liệu**, không bảo đảm mọi business invariant phức tạp.

## 16. Tự đánh giá kiến thức

1. Một controller không có `@Validated` class level nhưng có `@Min(1)` trên `@RequestParam`, chạy Spring MVC 6.2. Khi gửi `0`, cơ chế nào kiểm tra và exception thường là gì?
2. Cùng controller trên, thêm `@Validated` ở **class level**. Tại sao loại exception và cách xử lý có thể thay đổi?
3. Hai handler cùng nhận `@Valid @RequestBody ProfileRequest`. Handler A chỉ có DTO; handler B còn có `@Min` ở tham số query. Vì sao khi DTO rỗng có thể nhận hai loại exception khác nhau?
4. Đặt `@Validated` trên `ReservationService` rồi gọi `this.reserve("", 1)` từ bên trong chính service. Vì sao validation có thể bị bỏ qua?
5. Service AOP ném `ConstraintViolationException`, trong đó vi phạm thuộc **return value**. Có nên tự động trả HTTP 400 cho client không? Giải thích.
6. Khi MVC handler có `BindingResult` ngay sau DTO nhưng `@Min` trên parameter khác thất bại, handler có được gọi không? Vì sao?
7. Một request thiếu `@RequestParam(required=true)` nhận 400; có thể kết luận `@Min` đã chạy không? Phải kiểm tra gì?
8. Nếu muốn validate method của service trong unit test mà không khởi động Spring, API nào của Jakarta Validation có thể dùng?
9. Khi nâng cấp từ Spring 6.0 sang 6.1+, đâu là các test cần bổ sung để chứng minh đã chuyển đúng từ controller AOP sang MVC built-in?
10. Vì sao `@Validated(Group.class)` trên argument DTO và `@Validated(Group.class)` trên service class không có cùng vai trò kiến trúc?

**Kết luận ngắn:** MVC validation là **một phần vòng đời xử lý HTTP**; Spring MVC 6.1+ có built-in method validation trên handler; Spring `@Validated` class level là **cách kích hoạt AOP method validation** cho các bean như service. Chọn đúng cơ chế dựa vào nơi lời gọi đi qua, đừng chỉ nhìn thấy cùng annotation `@Min` rồi cho rằng mọi nơi đều có cùng exception và hành vi.

## 17. Tài liệu tham khảo

- [Spring Framework 6.2 — Validation của Spring MVC controller methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Java Bean Validation và method validation qua AOP](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Understanding AOP proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — `@RequestBody`, Bean Validation và `BindingResult`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — `ResponseEntityExceptionHandler`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — `HandlerMethodValidationException`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework — `MethodValidationPostProcessor`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Jakarta Validation specification — method và parameter validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintdeclarationvalidationprocess-methodlevelconstraints)
- [Spring Boot — Dependency validation và cấu hình ứng dụng](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Boot 3.5.6 release announcement](https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now/)