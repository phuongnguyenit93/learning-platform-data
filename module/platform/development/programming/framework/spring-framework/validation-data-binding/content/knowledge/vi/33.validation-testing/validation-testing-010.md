# Kiểm thử method validation qua bean proxy thực trong Spring Framework

## 1. Vì sao unit test gọi trực tiếp service chưa đủ?

Giả sử một dịch vụ Spring áp dụng ràng buộc ngay trên method:

```java
@Service
@Validated
public class BookingRulesService {

    public String verifyReference(@NotBlank String reference) {
        return reference.trim();
    }

    @NotNull
    public String findReceipt(boolean exists) {
        return exists ? "RCPT-390" : null;
    }
}
```

Đây là đoạn mô tả ý tưởng; project đầy đủ ở phần sau. Hai quy tắc cần được thực thi:

- `verifyReference(" ")`: tham số chỉ có khoảng trắng vi phạm `@NotBlank`.
- `findReceipt(false)`: method trả `null`, vi phạm `@NotNull` trên giá trị trả về.

Nhưng đoạn test này **không kiểm tra Spring method validation**:

```java
BookingRulesService service = new BookingRulesService();
String text = service.verifyReference(" ");
```

Kết quả của lời gọi Java thuần là `""`, **không tự ném** `ConstraintViolationException`. Annotation `@NotBlank` là metadata, còn cơ chế Jakarta Bean Validation cần được một validator hoặc interceptor chủ động thực thi. Một instance tạo bằng `new` không đi qua Spring container nên không có advice của `MethodValidationPostProcessor`.

Cùng một nguy cơ xuất hiện khi:

- Tạo service với `new` trong JUnit.
- Dùng Mockito `mock(...)`, nhưng mặc định method body và Spring advice không được thực thi.
- Dùng một slice test mà bean service được thay bằng mock.
- Gọi một method có constraint từ method khác **trong cùng class** (self-invocation).
- Đặt `@Validated` sai chỗ, thiếu Bean Validation provider, hoặc final/private method làm proxy không chặn được lời gọi.

**Mục tiêu bài này:** viết integration test lấy **bean proxy thực từ Spring ApplicationContext**, xác minh thật sự có proxy, gọi qua proxy, kiểm tra input parameter constraints, cascaded `@Valid`, return-value constraints, validation groups, exception type và self-invocation. Bài còn đưa đường HTTP minh họa để quan sát request đi qua controller tới service proxy, cùng cách tránh nhầm với method validation tích hợp của Spring MVC.

**Phạm vi:** Java 17+, Spring Boot 3.3.6, Spring Framework 6.1.x, Spring AOP proxy-based method validation và Jakarta Validation. Từ Spring MVC 6.1 có cơ chế built-in method validation trên controller khác với AOP service validation. Ví dụ là một dự án chạy độc lập khi có JDK 17, Gradle và dependencies; các kết quả test được ghi là **kỳ vọng**, không phải khẳng định đã thực thi trong quá trình soạn bài.

## 2. Spring-driven method validation hoạt động như thế nào?

### 2.1. Thành phần liên quan

| Thành phần | Vai trò |
| --- | --- |
| `jakarta.validation.constraints.*` | Khai báo các constraints `@NotBlank`, `@Min`, `@NotNull`… |
| `@Valid` | Yêu cầu kiểm tra **cascaded object** trên tham số/return value khi validation được kích hoạt |
| `org.springframework.validation.annotation.Validated` | Đánh dấu **target class** cần Spring AOP method validation, tùy chọn các groups |
| `MethodValidationPostProcessor` | Bean post-processor tìm các bean đủ điều kiện và tạo validation advisor/proxy |
| `MethodValidationInterceptor` | Advice thực thi Jakarta `ExecutableValidator` trước/sau method invocation |
| `jakarta.validation.Validator` / `ExecutableValidator` | Nhà cung cấp Bean Validation, thường Hibernate Validator |
| `ConstraintViolationException` | Exception mặc định khi method validation phát hiện vi phạm |
| `MethodValidationException` | Kiểu thay thế khi cấu hình Spring adapter chuyển violations sang `MethodValidationResult` |
| Spring AOP proxy | Biên thực thi cần lời gọi **đi qua proxy** |

Spring Boot có thể tự cấu hình method validation khi có Bean Validation provider (thường nhờ `spring-boot-starter-validation`). Đối với method validation do Spring AOP thực hiện, **target service class cần `@Validated` ở cấp type**. Nếu cấu hình Spring thuần không có Boot auto-configuration tương ứng, có thể khai báo `MethodValidationPostProcessor` làm Spring bean. Không thêm bean thủ công khi Boot đã cung cấp một post-processor phù hợp, vì cấu hình trùng có thể khó debug.

### 2.2. Dòng chảy qua proxy

```text
JUnit @SpringBootTest / controller / bean khác
              |
              | gọi public service method
              v
   Spring-managed proxy của service
              |
              v
   MethodValidationInterceptor
              |
              | validateParameters(target, method, args, groups)
              | có violations? -> ConstraintViolationException
              v
   Method body của target service
              |
              | thực thi business logic
              v
   MethodValidationInterceptor
              |
              | validateReturnValue(target, method, result, groups)
              | có violations? -> ConstraintViolationException
              v
         Caller nhận result
```

Các bước trên là luồng khái niệm. Thứ tự tương tác với `@Transactional`, caching hoặc custom advisors có thể phụ thuộc cấu hình/order; đừng từ sơ đồ này suy ra transaction đã commit trước khi return validation hoặc mọi ngoại lệ đều được ném trước khi persistence flush.

### 2.3. Phân biệt @Valid và @Validated

- `@Valid` là annotation của Jakarta Validation: đánh dấu vị trí cần **cascading** vào object được tham chiếu. **Nó không tự tạo Spring AOP proxy**.
- `@Validated` của Spring ở class level là dấu hiệu cho `MethodValidationPostProcessor` tìm và proxy bean. Nó có thể chỉ định group.
- `@NotBlank`, `@Min`, `@NotNull` là **constraint annotations** thực sự; chúng quyết định tính hợp lệ của parameter/return/object.
- `@Validated(SomeGroup.class)` ở method level có thể **ghi đè nhóm** dùng cho method cụ thể, nhưng không thay thế nhu cầu `@Validated` ở class level để tạo proxy.

Nếu class có `@Validated` nhưng không có method constraint và cũng không có cascade cần kiểm tra, proxy có thể tồn tại nhưng không tìm thấy violation ở những method cụ thể. Do đó **chỉ assert proxy tồn tại chưa đủ**: phải gọi một method với input sai và chứng minh interceptor ném exception.

## 3. Tại sao phải dùng @SpringBootTest trong bài kiểm thử này?

Có hai loại test khác nhau:

### 3.1. Unit test của business method

```java
BookingRulesService plain = new BookingRulesService();

assertEquals("", plain.verifyReference(" "));
```

Test này có thể phù hợp để kiểm tra `String#trim()`. Nhưng nó **không xác minh** các constraints ở biên AOP.

### 3.2. Integration test của Spring proxy

```java
@SpringBootTest
class BookingRulesServiceTest {

    @Autowired
    BookingRulesService service;

    @Test
    void mustHaveProxy() {
        assertTrue(AopUtils.isAopProxy(service));
    }
}
```

Đây là snippet rút gọn, cần JUnit/Spring imports và context cấu hình đúng. `@SpringBootTest` tạo ApplicationContext gần thực tế; `@Autowired` lấy object do container trả về — thường là một **proxy**, không phải target thuần. Test có thể gọi method bình thường rồi bắt `ConstraintViolationException`.

Tại sao cần cả hai assertions?

1. `AopUtils.isAopProxy(service)`: chứng minh object đang dùng là Spring AOP proxy.
2. `assertThrows(ConstraintViolationException.class, () -> service.verifyReference(" "))`: chứng minh advice validation thực sự hoạt động cho method mong muốn.

Nếu chỉ có assertion 1, bean có thể được proxy bởi transaction/cache/security mà **không có** method validation advisor; nếu chỉ có assertion 2, bạn có thể tình cờ nhận exception do **code trong method tự throw**, chứ không phải Jakarta method validation. Trong ví dụ, method body **không tự throw** nên cùng hai phép kiểm tra cung cấp bằng chứng rõ ràng.

## 4. Hai cơ chế validation thường bị nhầm trong ứng dụng MVC

### 4.1. AOP service method validation

```java
@Service
@Validated
public class BookingRulesService {
    public int doubleSeats(@Min(1) int seats) {
        return seats * 2;
    }
}
```

Lời gọi qua bean proxy với `seats=0` thường sinh `jakarta.validation.ConstraintViolationException` khi dùng cấu hình mặc định của `MethodValidationPostProcessor`.

### 4.2. Spring MVC built-in method validation từ Framework 6.1

```java
@GetMapping("/quantity")
public int quantity(@RequestParam @Min(1) int value) {
    return value;
}
```

Đây là constraint **trực tiếp trên controller method parameter**. Spring MVC 6.1+ có khả năng method validation **tích hợp ngay trong HandlerMethod** mà không cần proxy service tương ứng. Trong trường hợp có violation, nó có thể ném `HandlerMethodValidationException`. Nếu chỉ có `@Valid @RequestBody` hoặc `@Valid @ModelAttribute` cho một command object, kiểu exception thường gặp là `MethodArgumentNotValidException`; direct constraints có thể làm method validation supersede argument validation.

**Lưu ý từ tài liệu Spring:** để tận dụng built-in method validation của Spring MVC 6.1+, nên bỏ `@Validated` ở **cấp controller class**. Annotation `@Validated` trên **service class** vẫn là cách kích hoạt Spring AOP method validation của bài học.

Trong dự án runnable, controller **không** có constraints trực tiếp và **không** có `@Validated` class level. Nó chỉ gọi một `@Validated` service bean. Nhờ vậy tests chỉ ra đúng đường AOP service đang được kiểm tra.

## 5. Điều kiện để proxy chặn được lời gọi

1. Đối tượng do Spring container tạo và đã qua bean post-processing.
2. Có Bean Validation provider và method validation post-processor/advisor.
3. Target class có `@Validated` ở cấp type.
4. Caller giữ bean **proxy**, không tự `new` target.
5. Phương thức eligible cho proxy, thường là public, không bị final/private cản trở.
6. Lời gọi **đi từ bên ngoài qua proxy**, không đi qua `this.method()` bên trong target.
7. Constraint đặt ở vị trí được Jakarta Bean Validation hỗ trợ và không vi phạm quy tắc inheritance của executable constraints.
8. Validation groups được chọn đúng; constraint ở một group khác có thể bị bỏ qua một cách hợp lệ.

### 5.1. JDK dynamic proxy và CGLIB proxy

Spring AOP thường chọn:

- **JDK dynamic proxy** nếu proxy dựa trên interface. Caller nên inject interface mà proxy triển khai; các method không có trong interface có thể không lộ qua JDK proxy.
- **CGLIB class-based proxy** khi cần proxy class. Nó tạo subclass tại runtime, nên không thể override final method và không thể subclass final class.

Ví dụ runnable chọn **class không implement interface**, không final và methods public, vì vậy Spring có thể tạo class-based proxy và test có thể inject bằng concrete class. Cấu hình `spring.aop.proxy-target-class=true` giúp ý định rõ ràng. Không nên thiết kế source test phụ thuộc JDK/CGLIB khi mục tiêu chỉ là xác minh method validation, trừ khi chính proxy strategy là điều cần kiểm thử.

Đối với interface-based service, đặt constraints nhất quán trên interface contract; Jakarta Validation hạn chế việc implementation method **thêm/siết preconditions** so với method đã khai báo ở interface hoặc superclass, vì có thể gây `ConstraintDeclarationException`. Đừng chuyển annotation giữa interface và implementation mà không test.

### 5.2. Final, private và self-invocation

- `final class` không cho CGLIB subclass.
- `final method` không thể được CGLIB override để chèn advice.
- `private method` không phải public proxy boundary.
- `this.someMethod()` từ bên trong target không đi lại qua proxy; advice không có cơ hội xử lý.
- Một bean tự inject chính nó để gọi proxy có thể tạo vòng phụ thuộc và coupling; refactor để lời gọi được thực hiện bởi **bean khác** thường rõ ràng hơn.
- `AopContext.currentProxy()` cần bật expose-proxy và tạo coupling vào Spring AOP; tài liệu Spring khuyến nghị tránh khi có thể.

Nếu service method thực sự cần validation nội bộ, có hai hướng sạch: tách phần được validate thành một Spring-managed collaborator được inject và gọi qua bean proxy, hoặc dùng `Validator`/`ExecutableValidator` tường minh tại đúng boundary. Không dùng self-invocation như một đường vòng được đảm bảo validation.

## 6. Dự án runnable Spring Boot 3.3.6, Java 17

Project này cung cấp:

- `BookingRulesService` có `@Validated` trên class.
- Parameter constraints `@NotBlank` và `@Min`.
- Cascaded request record bằng `@Valid @NotNull`.
- Return-value constraint `@NotNull`.
- Method-level `@Validated(ReviewChecks.class)` để chứng minh groups.
- Method `callOwnValidator` cố ý self-invocation để test nhược điểm proxy.
- `BookingController` không đặt `@Valid` trên body, giúp chứng minh service proxy xử lý cascaded validation.
- `@RestControllerAdvice` phân loại input vs return violations trong **phạm vi demo**.
- `@SpringBootTest` và `@AutoConfigureMockMvc` để test bean proxy thực và đường HTTP.

### 6.1. Cấu trúc source

```text
method-validation-proxy-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/proxyvalidation/
        MethodValidationProxyApplication.java
        BookingRequest.java
        BookingReceipt.java
        ApiError.java
        ReviewChecks.java
        BookingRulesService.java
        BookingController.java
        ValidationAdvice.java
      resources/
        application.properties
    test/
      java/com/example/proxyvalidation/
        BookingRulesServiceProxyTest.java
```

Đây là project độc lập. Không cần database, không cần external service. Có thể chạy toàn bộ tests bằng Spring Test + embedded servlet environment do Spring Boot test auto-config sử dụng.

### 6.2. settings.gradle

```groovy
rootProject.name = 'method-validation-proxy-demo'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Giải thích:

- `spring-boot-starter-validation` cung cấp Bean Validation provider như Hibernate Validator.
- `spring-boot-starter-aop` cung cấp hạ tầng proxy/aspect phù hợp và làm ý định demo rõ ràng.
- `spring-boot-starter-web` cung cấp Spring MVC và Jackson để test request qua HTTP.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito, Spring Test và MockMvc.
- `-parameters` giúp runtime biết tên method parameters; hữu ích để kiểm tra violation path, nhưng test tránh khẳng định cứng chuỗi path phụ thuộc tên parameter.

### 6.4. application.properties

`src/main/resources/application.properties`:

```properties
spring.application.name=method-validation-proxy-demo
spring.aop.proxy-target-class=true
```

`proxy-target-class=true` chọn class-based proxy khi thích hợp. Đây **không phải** công tắc thay thế `@Validated`: một bean không có pointcut/advisor validation vẫn không tự được validate chỉ vì property này được bật.

### 6.5. Main class

`src/main/java/com/example/proxyvalidation/MethodValidationProxyApplication.java`:

```java
package com.example.proxyvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodValidationProxyApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MethodValidationProxyApplication.class, args
        );
    }
}
```

### 6.6. Request record và validation constraints

`src/main/java/com/example/proxyvalidation/BookingRequest.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record BookingRequest(
        @NotBlank String reference,
        @NotNull @Min(1) Integer seats
) {}
```

`@NotBlank` chặn null/blank reference. `@NotNull` chặn thiếu seats. `@Min(1)` kiểm tra số ghế dương khi không null; riêng `@Min` không coi null là vi phạm. Không dùng kiểu `int` trong request record nếu nghiệp vụ cần phân biệt “không gửi seats” với “gửi 0”.

### 6.7. DTO response

`src/main/java/com/example/proxyvalidation/BookingReceipt.java`:

```java
package com.example.proxyvalidation;

public record BookingReceipt(String receipt) {}
```

`src/main/java/com/example/proxyvalidation/ApiError.java`:

```java
package com.example.proxyvalidation;

public record ApiError(
        String code,
        String message
) {}
```

Không serialize `ConstraintViolation` trực tiếp vào response: `getInvalidValue()`, root bean và provider metadata có thể làm lộ dữ liệu hoặc gây JSON serialization phức tạp. Đối với demo, chỉ trả máy đọc được `code` và thông báo chung không chứa giá trị bị từ chối.

### 6.8. Marker interface cho một validation group

`src/main/java/com/example/proxyvalidation/ReviewChecks.java`:

```java
package com.example.proxyvalidation;

public interface ReviewChecks {}
```

Marker interface không có method. Nó đóng vai trò token nhóm `ReviewChecks.class` theo Jakarta Validation.

### 6.9. Service có method constraints và class-level @Validated

`src/main/java/com/example/proxyvalidation/BookingRulesService.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BookingRulesService {

    public String verifyReference(
            @NotBlank String reference) {

        return reference.trim();
    }

    public int doubleSeats(@Min(1) int seats) {
        return seats * 2;
    }

    public String create(
            @Valid @NotNull BookingRequest request) {

        return "BOOKED:" + request.reference();
    }

    @NotNull
    public String findReceipt(boolean exists) {
        return exists ? "RCPT-390" : null;
    }

    @Validated(ReviewChecks.class)
    public String review(
            @NotBlank(groups = ReviewChecks.class) String summary,
            @NotBlank String comment) {

        return summary.trim() + ":" + comment;
    }

    public String callOwnValidator(String reference) {
        // Cố ý gọi this.verifyReference(reference) bằng nội bộ.
        // Đây KHÔNG phải lời gọi qua Spring proxy!
        return verifyReference(reference);
    }
}
```

Cách đọc constraints:

- `verifyReference(" ")`: `@NotBlank` ở parameter; proxy sẽ ném exception trước khi chạy `trim()`.
- `doubleSeats(0)`: `@Min(1)` ở parameter; proxy sẽ chặn trước method body.
- `create(new BookingRequest(" ",0))`: `@Valid` yêu cầu cascade vào record; phát hiện `@NotBlank(reference)` và `@Min(seats)`.
- `create(null)`: `@NotNull` trên parameter phát hiện null; `@Valid` **không tự coi null là lỗi**.
- `findReceipt(false)`: method body trả null; interceptor kiểm tra **return value** và ném exception.
- `review(" ", "text")`: method-level `@Validated(ReviewChecks.class)` chọn group ReviewChecks và áp dụng constraint tương ứng.
- `review("OK", " ")`: `comment` có `@NotBlank` trong group `Default`, nhưng `review` được chỉ định chỉ chạy `ReviewChecks`; vì vậy ở cấu hình này comment rỗng **không bị** Default-group constraint kiểm tra. Đây là khác biệt nhóm được cố ý tạo để học.
- `callOwnValidator(" ")`: method này không có parameter constraint; khi nó gọi `verifyReference` từ trong **cùng target object**, lời gọi không đi lại qua proxy. Kết quả là chuỗi rỗng được trả về, cho thấy self-invocation bỏ qua advice.

**Đừng coi self-invocation test là hành vi nên dùng trong nghiệp vụ.** Nó chứng minh một giới hạn của proxy-based AOP để người học biết tại sao code nội bộ có thể không được validate.

### 6.10. Controller chỉ đóng vai trò caller của service proxy

`src/main/java/com/example/proxyvalidation/BookingController.java`:

```java
package com.example.proxyvalidation;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final BookingRulesService rules;

    public BookingController(BookingRulesService rules) {
        this.rules = rules;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<BookingReceipt> create(
            @RequestBody BookingRequest request) {

        String receipt = rules.create(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new BookingReceipt(receipt));
    }

    @GetMapping("/receipt")
    public BookingReceipt findReceipt(
            @RequestParam(defaultValue = "true")
            boolean exists) {

        return new BookingReceipt(rules.findReceipt(exists));
    }
}
```

Controller không dùng `@Valid` trên `@RequestBody` **có chủ đích**, nhằm chứng minh record constraints được kích hoạt khi controller gọi **`rules.create(request)` qua service proxy**. Nếu thêm `@Valid` vào controller parameter, Spring MVC có thể bắt lỗi trước khi service chạy, làm test HTTP không còn chứng minh được service method validation.

Trong ứng dụng production, controller `@Valid` và service method validation có thể cùng tồn tại khi các boundary cần hợp đồng riêng. Nhưng test phải tách rõ **boundary nào** đang được xác minh.

### 6.11. @RestControllerAdvice phân biệt input violation và return violation

`src/main/java/com/example/proxyvalidation/ValidationAdvice.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.ElementKind;
import jakarta.validation.Path;
import java.util.stream.StreamSupport;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiError> constraints(
            ConstraintViolationException exception) {

        boolean returnViolation = exception.getConstraintViolations()
                .stream()
                .flatMap(v -> StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false
                ))
                .map(Path.Node::getKind)
                .anyMatch(kind -> kind == ElementKind.RETURN_VALUE);

        if (returnViolation) {
            return ResponseEntity.internalServerError().body(
                    new ApiError(
                            "SERVER_CONTRACT",
                            "The server produced an invalid result"
                    )
            );
        }

        // Chỉ là mapping cho API demo kiểm soát rõ
        // service methods được gọi từ controller này.
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_INPUT",
                        "The request violates an input constraint"
                )
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_JSON",
                        "The request body cannot be read"
                )
        );
    }
}
```

**Tại sao phải phân biệt return violation?**

- Parameter violation do client gửi giá trị không hợp lệ ở endpoint này → HTTP **400**.
- Return-value violation xảy ra vì service trả kết quả không đáp ứng contract → **lỗi server**, thường HTTP **500**.
- JSON sai cú pháp khiến Jackson không tạo được request object → `HttpMessageNotReadableException`, không phải `ConstraintViolationException` từ proxy.

**Giới hạn:** một `ConstraintViolationException` phát sinh từ service nội bộ không phải lúc nào cũng do HTTP client gây ra. Trong sản phẩm thật, không nên catch mọi `ConstraintViolationException` rồi mặc định báo 400. Cần biết caller và tầng trách nhiệm, tách application/domain exceptions với HTTP input validation, và giữ error codes an toàn. Advice trên được giới hạn về mục đích minh họa hai endpoint và cách phân biệt parameter/return nodes.

Nếu dùng `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`, exception có thể là Spring `MethodValidationException` thay vì Jakarta `ConstraintViolationException`. Bộ test này sử dụng **cấu hình mặc định** nên assert `ConstraintViolationException`; không tự bật chế độ adapter trong project.

## 7. Integration tests thật: @SpringBootTest và AopUtils

Tệp `src/test/java/com/example/proxyvalidation/BookingRulesServiceProxyTest.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.ElementKind;
import jakarta.validation.Path;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingRulesServiceProxyTest {

    @Autowired
    BookingRulesService service;

    @Autowired
    MockMvc mvc;

    @Test
    void actualSpringBeanIsAopProxy() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    void invalidBlankParameterIsRejectedByProxy() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.verifyReference(" ")
        );

        assertEquals(
                Set.of("NotBlank"),
                constraintNames(exception)
        );
    }

    @Test
    void invalidNumericParameterIsRejectedByProxy() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.doubleSeats(0)
        );

        assertEquals(
                Set.of("Min"),
                constraintNames(exception)
        );
    }

    @Test
    void validParametersExecuteMethodBody() {
        assertEquals(
                "BOOK-390",
                service.verifyReference(" BOOK-390 ")
        );
        assertEquals(4, service.doubleSeats(2));
    }

    @Test
    void nestedRecordConstraintsAreValidated() {
        BookingRequest request = new BookingRequest(" ", 0);

        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.create(request)
        );

        assertEquals(
                Set.of("NotBlank", "Min"),
                constraintNames(exception)
        );

        assertEquals(2, exception.getConstraintViolations().size());
    }

    @Test
    void nullRequestRequiresExplicitNotNull() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.create(null)
        );

        assertEquals(
                Set.of("NotNull"),
                constraintNames(exception)
        );
    }

    @Test
    void validCascadedRecordIsAccepted() {
        assertEquals(
                "BOOKED:REF-390",
                service.create(
                        new BookingRequest("REF-390", 2)
                )
        );
    }

    @Test
    void invalidReturnValueIsRejectedAfterMethodBody() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.findReceipt(false)
        );

        assertEquals(
                Set.of("NotNull"),
                constraintNames(exception)
        );
        assertTrue(hasReturnNode(exception));
    }

    @Test
    void validReturnValueIsAccepted() {
        assertEquals("RCPT-390", service.findReceipt(true));
    }

    @Test
    void methodGroupOverridesDefaultGroup() {
        assertEquals(
                "OK: ",
                service.review("OK", " ")
        );
    }

    @Test
    void methodSpecificGroupConstraintIsChecked() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.review(" ", "comment")
        );

        assertEquals(
                Set.of("NotBlank"),
                constraintNames(exception)
        );
    }

    @Test
    void selfInvocationBypassesMethodValidationAdvice() {
        // callOwnValidator không bị ràng buộc trực tiếp.
        // Lời gọi bên trong sang verifyReference không qua proxy.
        assertEquals(
                "",
                service.callOwnValidator(" ")
        );
    }

    @Test
    void newInstanceIsNotSpringProxy() {
        BookingRulesService plain = new BookingRulesService();

        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals("", plain.verifyReference(" "));
        assertEquals(null, plain.findReceipt(false));
    }

    @Test
    void httpEndpointUsesRealServiceProxyForInput() throws Exception {
        mvc.perform(post("/api/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"reference":" ","seats":0}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void httpEndpointUsesRealServiceProxyForReturn() throws Exception {
        mvc.perform(get("/api/bookings/receipt")
                .param("exists", "false"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("SERVER_CONTRACT"));
    }

    @Test
    void validHttpRequestSucceeds() throws Exception {
        mvc.perform(post("/api/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"reference":"ABC-390","seats":2}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.receipt")
                    .value("BOOKED:ABC-390"));
    }

    @Test
    void malformedJsonDoesNotReachMethodValidation()
            throws Exception {

        mvc.perform(post("/api/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reference\":\"X\",\"seats\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    private static Set<String> constraintNames(
            ConstraintViolationException exception) {

        return exception.getConstraintViolations()
                .stream()
                .map(v -> v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName())
                .collect(Collectors.toSet());
    }

    private static boolean hasReturnNode(
            ConstraintViolationException exception) {

        return exception.getConstraintViolations()
                .stream()
                .flatMap(v -> StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false
                ))
                .map(Path.Node::getKind)
                .anyMatch(kind -> kind == ElementKind.RETURN_VALUE);
    }
}
```

Có **17 test methods**, trong đó các test quan trọng nhất là:

- `actualSpringBeanIsAopProxy`: Spring context thật trả proxy.
- `invalidBlankParameterIsRejectedByProxy`: parameter constraint hoạt động khi gọi qua bean.
- `nestedRecordConstraintsAreValidated`: `@Valid` cascade đến component constraints của record.
- `invalidReturnValueIsRejectedAfterMethodBody`: kiểm tra violation path có node `RETURN_VALUE`, không chỉ so exception type.
- `selfInvocationBypassesMethodValidationAdvice`: chứng minh hạn chế proxy-based AOP.
- `newInstanceIsNotSpringProxy`: đối chứng giữa plain object và bean proxy.
- Các tests `httpEndpoint...`: xác nhận request đi qua real controller tới proxied service.
- `methodGroupOverridesDefaultGroup` và `methodSpecificGroupConstraintIsChecked`: xác nhận phương pháp chọn group có hiệu lực.

### 7.1. Lệnh chạy

Từ thư mục project với Gradle wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu project chưa có wrapper, có thể dùng Gradle đã cài đặt để sinh wrapper hoặc chạy:

```bash
gradle test
```

**Kỳ vọng:** 17 tests PASS khi project đúng cấu hình Spring Boot 3.3.6, Java 17 và dependencies được nêu. Đây là expected behavior của mã nguồn tham khảo, **không** phải khẳng định test đã được thực thi trong quá trình soạn bài.

### 7.2. Vì sao test assert annotation names thay vì default message?

Một `ConstraintViolation` có `getMessage()`, `getMessageTemplate()`, `getPropertyPath()`, `getConstraintDescriptor()`. Default messages như “must not be blank” có thể khác theo `Locale` và provider; đường method parameter path còn phụ thuộc parameter names/metadata.

Bộ test dùng annotation types `NotBlank`, `Min`, `NotNull` — bất biến hơn đối với bài demo — và kiểm tra số lượng violations. Nó **không phụ thuộc thứ tự** của `Set<ConstraintViolation>`, vì Set không cam kết iteration order.

Đối với return-value validation, dùng `Path.Node#getKind() == ElementKind.RETURN_VALUE` chắc chắn hơn so sánh một chuỗi path mà provider có thể biểu diễn khác.

### 7.3. Tại sao nên kiểm tra test trả về thành công?

Một test chỉ assert exception khi sai có thể bỏ sót cấu hình sai khiến **mọi input** đều bị từ chối. Cặp test hợp lệ xác nhận advice không làm thay đổi business result khi không có violation:

```java
assertEquals(
        "BOOK-390",
        service.verifyReference(" BOOK-390 ")
);
assertEquals(
        "RCPT-390",
        service.findReceipt(true)
);
```

Phải test cả **đường đúng** và **đường sai** để tránh false positives từ một exception được ném bởi code khác hoặc một proxy khác.

### 7.4. Khi nào dùng MockMvc, khi nào chỉ cần @SpringBootTest?

Nếu chỉ quan tâm method validation của service, `@SpringBootTest` + `@Autowired` service đủ để xác minh real proxy. `MockMvc` cần khi muốn chắc chắn controller dùng bean service đã inject, HTTP error mapping hợp lý và JSON contract không lộ raw violations.

Ngược lại, chỉ có `@WebMvcTest` và một mock service **không chứng minh** method validation của service hoạt động. Slice test thường chỉ tạo controller layer và những dependency được khai báo cho slice; nếu service bị thay bằng Mockito mock, method validation advisor của bean thật không nhất thiết chạy.

## 8. Kết quả HTTP mong đợi

### 8.1. Input không hợp lệ bị chặn ở proxy

```bash
curl -i -X POST http://localhost:8080/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"reference":" ","seats":0}'
```

Kỳ vọng HTTP **400 Bad Request**:

```json
{
  "code": "INVALID_INPUT",
  "message": "The request violates an input constraint"
}
```

Lỗi này đến từ `rules.create(request)` qua method validation proxy, vì controller không gắn `@Valid` lên body.

### 8.2. Request hợp lệ

```bash
curl -i -X POST http://localhost:8080/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"reference":"ABC-390","seats":2}'
```

Kỳ vọng HTTP **201 Created**:

```json
{"receipt":"BOOKED:ABC-390"}
```

### 8.3. Return value trái hợp đồng

```bash
curl -i 'http://localhost:8080/api/bookings/receipt?exists=false'
```

`findReceipt(false)` có thể chạy xong method body và trả `null`, nhưng interceptor kiểm tra `@NotNull` trên return value nên báo lỗi. Kỳ vọng HTTP **500 Internal Server Error** theo advice trong demo:

```json
{
  "code": "SERVER_CONTRACT",
  "message": "The server produced an invalid result"
}
```

Không trả 400 cho tình huống này: client gửi `exists=false` theo contract của endpoint, còn method đã hứa return không null nhưng không giữ lời. Đây là vấn đề phía server.

### 8.4. JSON bị hỏng không qua đến service

```bash
curl -i -X POST http://localhost:8080/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"reference":"ABC-390","seats":'
```

Kỳ vọng HTTP 400 với code `INVALID_JSON`. Jackson không tạo được `BookingRequest`; method validation proxy chưa có input object để kiểm tra.

## 9. Test bằng Mockito mock: vì sao không thay real proxy?

Mockito rất hữu ích để unit-test logic riêng. Nhưng:

```java
BookingRulesService service =
        org.mockito.Mockito.mock(BookingRulesService.class);

service.verifyReference(" ");
```

là một lời gọi vào **mock**, không phải Spring bean qua `MethodValidationInterceptor`. Theo mặc định Mockito không gọi implementation thực và không tự kích hoạt method validation của Spring. Nếu không stub, method có thể trả default của mock (ví dụ null). Vì vậy:

- Một test thấy method được gọi qua `verify(mock).verifyReference(...)` chỉ chứng minh interaction, không chứng minh constraint được thi hành.
- Một `@WebMvcTest` có service được mock vẫn có giá trị kiểm tra HTTP controller mapping, nhưng không phải bằng chứng cho AOP method validation.
- Mockito `spy` cũng cần thận trọng: một spy đơn lẻ không phải Spring proxy; các tình huống @SpyBean/bean overriding có thể thay cấu trúc proxy, phải xác minh cấu hình.
- Nếu muốn unit-test rule trên DTO, gọi trực tiếp `jakarta.validation.Validator#validate` hoặc `ExecutableValidator#validateParameters` trong test riêng. Đó là **test provider**, không phải test đường Spring proxy.
- Nếu mục tiêu là đủ chắc chắn bean trong production được post-process, dùng integration test lấy bean thật và assert `AopUtils.isAopProxy` + exception.

### 9.1. Phân biệt Manual ExecutableValidator và proxy invocation

Một kiểm thử Jakarta validation thuần có thể sử dụng:

```java
Method method = BookingRulesService.class.getMethod(
        "doubleSeats", int.class
);

BookingRulesService plain = new BookingRulesService();

Set<ConstraintViolation<BookingRulesService>> violations =
        validator.forExecutables().validateParameters(
                plain, method, new Object[]{0}
        );
```

Đây là **snippet** cần imports `java.lang.reflect.Method`, `java.util.Set`, `jakarta.validation.ConstraintViolation` và `Validator`, giả sử `validator` đã có. Nó có thể tìm violation trực tiếp thông qua provider, **không cần proxy**. Vì vậy test này không chứng minh Spring container đã cấu hình `MethodValidationPostProcessor`.

Ngược lại, gọi `service.doubleSeats(0)` với injected proxy và nhận `ConstraintViolationException` chứng minh đường AOP đang hoạt động.

## 10. Một ví dụ tiêu cực: self-invocation bỏ qua validation

Nhắc lại service:

```java
public String callOwnValidator(String reference) {
    return verifyReference(reference);
}
```

Nếu caller bên ngoài làm:

```java
service.callOwnValidator(" ");
```

thì:

```text
Caller -> Spring proxy -> target.callOwnValidator(" ")
                               |
                               v
                     target.verifyReference(" ")
                               |
                               v
                            returns ""
             (không đi lại qua Spring proxy)
```

Giá trị `""` có thể được trả về dù `verifyReference` có `@NotBlank` ở tham số. Đây là hành vi proxy-based Spring AOP, không phải Bean Validation “bỏ qua annotation ngẫu nhiên”.

**Cách sửa được khuyến nghị:** tách method đã được validate vào collaborator bean khác:

```java
@Service
@Validated
public class ReferenceRules {

    public String verify(@NotBlank String reference) {
        return reference.trim();
    }
}

@Service
public class BookingWorkflow {

    private final ReferenceRules rules;

    public BookingWorkflow(ReferenceRules rules) {
        this.rules = rules;
    }

    public String process(String reference) {
        return rules.verify(reference);
    }
}
```

Đây là snippet minh họa hai classes (trong mã nguồn thực phải tách thành hai files nếu đều public). Khi `BookingWorkflow` gọi `rules.verify`, nó gọi một Spring-managed bean reference, nên nếu bean đó đã được proxy, method validation có thể chạy. Đây là cách giảm coupling so với tự inject chính mình hay dùng `AopContext.currentProxy()`.

## 11. Validation groups: lớp và phương thức

Trong Spring method validation, nhóm được xác định bằng `@Validated`:

```java
@Service
@Validated
public class OrderApprovalService {

    @Validated(ReviewChecks.class)
    public void approve(
            @NotBlank(groups = ReviewChecks.class) String ticket,
            @NotBlank String note) {
        // business logic
    }
}
```

Ở đây class-level `@Validated` kích hoạt proxy với mặc định `Default`. Method-level `@Validated(ReviewChecks.class)` **thay nhóm** cho method `approve`, không tự động “gộp thêm” Default. Vì vậy:

- `approve(" ", "reason")`: ticket thuộc ReviewChecks không hợp lệ, có violation.
- `approve("A-390", " ")`: `note` thuộc Default nên không được đánh giá khi chỉ chạy ReviewChecks.

Đây là lựa chọn cần hiểu cẩn thận: một constraint bắt buộc trong Default có thể không còn được áp trên method nếu method chọn nhóm khác. Nếu cần kiểm tra cả hai, cấu hình groups/sequence rõ ràng; đừng dựa vào việc hai annotation tự động cộng dồn.

### 11.1. @Validated chỉ đặt trên method chưa đủ kích hoạt pointcut

Sai ý định:

```java
@Service
public class OrderApprovalService {

    @Validated(ReviewChecks.class)
    public void approve(
            @NotBlank(groups = ReviewChecks.class) String ticket) {
    }
}
```

Với Spring-driven AOP method validation mặc định, đặt `@Validated` **chỉ trên method** không thay thế class-level `@Validated` để bean được chọn cho proxy. Javadoc Spring `Validated` nêu rõ method-level annotation dùng để override group, còn class-level marker cần cho pointcut.

## 12. JDK proxy, interface và các quy tắc overriding của Jakarta Validation

Một service interface có thể được proxied bằng JDK dynamic proxy:

```java
public interface ReceiptService {

    String read(@NotBlank String code);
}
```

Implementation:

```java
@Service
@Validated
public class ReceiptServiceImpl implements ReceiptService {

    @Override
    public String read(String code) {
        return code;
    }
}
```

Các đoạn trên là snippet minh họa, không thuộc project runnable. Ở đây constraint đặt trên **interface contract** và implementation không đặt thêm parameter constraints.

Không nên viết interface không có constraints rồi thêm `@NotBlank` chỉ trên overriding method mà tin nó luôn hợp lệ. Jakarta Validation có quy tắc “subtype không được làm mạnh preconditions” đối với method parameter constraints; provider có thể ném `ConstraintDeclarationException`. Return-value constraints có quy tắc khác nhưng vẫn cần đọc specification khi override/compose interfaces.

Nếu bean dùng JDK proxy:

- Inject qua `ReceiptService` interface là cách tự nhiên.
- Không chắc có thể inject bằng `ReceiptServiceImpl` concrete type.
- Các method chỉ có trên implementation mà không có interface có thể không truy cập được qua JDK proxy.
- Test nên assert `AopUtils.isAopProxy(...)` và hành vi khi gọi bằng interface reference, thay vì giả định class-based proxy nếu ứng dụng cho phép nhiều strategies.

Nếu muốn class-based proxy, cấu hình phù hợp và không đánh dấu class/methods cần advice là final. Đừng bật CGLIB toàn dự án chỉ để “chữa” một test injection fail mà không hiểu nguyên nhân.

## 13. Exception type và cấu hình method validation

### 13.1. ConstraintViolationException mặc định

Spring `MethodValidationPostProcessor` trong cấu hình thông thường tạo `MethodValidationInterceptor`. Khi phát hiện violations ở parameter/return, nó ném `jakarta.validation.ConstraintViolationException`. Test có thể inspect:

```java
ConstraintViolationException error = assertThrows(
        ConstraintViolationException.class,
        () -> service.doubleSeats(0)
);

Set<?> violations = error.getConstraintViolations();
```

Không dựa vào thứ tự duyệt `Set<ConstraintViolation>` để tìm “lỗi đầu tiên”. Với nhiều violations, dùng `stream().map(...).collect(toSet())` nếu chỉ cần membership; nếu phải xuất HTTP errors có thứ tự, map ra DTO và `sorted(...)` bằng comparator cố định.

### 13.2. MethodValidationException khi adaptConstraintViolations bật

Spring Framework có cấu hình:

```java
processor.setAdaptConstraintViolations(true);
```

Đây là snippet minh họa với biến `processor` kiểu `MethodValidationPostProcessor`. Khi bật, Spring chuyển raw Jakarta violations sang `MethodValidationResult`/`MessageSourceResolvable` và có thể ném Spring `MethodValidationException`.

Không viết test cứng `assertThrows(ConstraintViolationException.class, ...)` cho một ứng dụng đã bật chế độ này rồi kết luận method validation không hoạt động. Đọc Bean configuration và test theo exception contract đã chọn.

### 13.3. Nơi bắt exception phù hợp

Với service method được gọi bởi:

- HTTP controller: có thể mapping input violation sang 400 nếu xác định input do client gây ra; return violation thường là 500.
- Scheduler: không có HTTP 400/500; cần phân loại job failure.
- Kafka/event consumer: có thể dẫn tới dead-letter, retry hoặc poison message policy.
- Service khác: caller cần quyết định xử lý nghiệp vụ, không mặc định “lỗi người dùng”.
- Transactional operation: tùy advisor order, validation có thể xảy ra trước/hoặc sau một phần công việc; exception sau method body có thể có implications về rollback. Cần integration tests cho transaction boundary nếu quan trọng.

Không catch mọi `ConstraintViolationException` rồi luôn trả “Invalid request” cho frontend.

## 14. Những lỗi khiến test dễ PASS giả

| Test/thiết lập | Vì sao có thể đánh lừa | Cách kiểm chứng đúng |
| --- | --- | --- |
| `new Service().method(...)` | Không có Spring proxy | Inject bean từ ApplicationContext |
| `Mockito.mock(Service.class)` | Mock bỏ method body/advice | Integration test real bean riêng |
| Chỉ assert `@Validated` có trên class | Annotation tồn tại không chứng minh post-processor chạy | `AopUtils.isAopProxy` + invalid call |
| Chỉ assert proxy là true | Proxy có thể do AOP feature khác | Assert `ConstraintViolationException` thực sự |
| Chỉ test `@Valid` với object hợp lệ | Không chứng minh cascade bắt lỗi | Dùng record sai và kiểm tra nested violations |
| Chỉ test input parameter | Bỏ sót return contract | Method trả null với `@NotNull` |
| Gọi `this.validate(...)` | Không đi lại qua proxy | Gọi qua injected collaborator |
| `final` method/class khi dùng class proxy | Advice không thể override | Bỏ final ở boundary hoặc dùng strategy phù hợp |
| Thiếu `spring-boot-starter-validation` | Không có provider phù hợp | Kiểm tra dependency và bean validation |
| Tự thêm post-processor trùng Boot | Có nguy cơ double-advice/cấu hình khó hiểu | Ưu tiên auto config nếu đã đủ |
| `@Validated` chỉ ở method | Không đủ làm class pointcut | Đặt marker ở class level |
| Chọn group sai | Constraint “không chạy” có thể là đúng semantics | Test theo group được chọn |
| Assert message tiếng Anh | Text có thể khác locale/provider | Inspect annotation type/path/error code |
| Assert violation đầu tiên | `Set` không hứa iteration order | So sánh tập hoặc sort |
| Dùng `@WebMvcTest` với mocked service | Không kiểm tra service bean/proxy thật | `@SpringBootTest` hoặc test slice tự đưa real bean |
| Dùng `@Valid` trên controller và test HTTP | Controller có thể bắt lỗi trước service | Test service trực tiếp hoặc tách boundary |
| Bỏ qua return-value validation | Lỗi hợp đồng server không bị phát hiện | Test null/invalid return qua proxy |
| Gộp mọi method violation thành HTTP 400 | Có thể che lỗi phía server | Phân loại parameter/return và caller |
| Dựa vào method parameter name cố định | Metadata `-parameters`/provider ảnh hưởng path | Assert annotation types và Node kinds |
| Dùng service trong cùng class qua self-call | Bỏ qua advice ở lời gọi bên trong | Tách bean khác hoặc explicit validation |

## 15. Kiểm thử trong bối cảnh @Transactional và @Async

### 15.1. @Transactional cùng method validation

`@Transactional` cũng thường dùng Spring AOP proxy. Nếu đặt cả `@Transactional` và `@Validated` trên service, có thể có nhiều advisors trên cùng bean. Tương quan order giữa validation advisor và transaction advisor phải được xem xét nếu input/output validation có thể gây rollback hoặc nếu lỗi return-value xảy ra sau business writes.

Ví dụ method ghi database rồi trả null trái `@NotNull` không tự bảo đảm database rollback trong mọi cấu hình chỉ vì có method validation. Cần test thực tế:

1. Đọc dữ liệu ban đầu.
2. Gọi qua proxied service.
3. Bắt return-value violation.
4. Trong transaction độc lập, kiểm tra trạng thái database sau exception.
5. Ghi rõ kỳ vọng rollback hay commit theo architecture và advisor order.

Không làm test này bằng `new Service()` hoặc H2 khác transaction model production rồi suy ra toàn bộ semantics.

### 15.2. @Async và luồng khác

Nếu method được chạy bất đồng bộ, nơi exception xuất hiện có thể nằm trong `Future`/`CompletableFuture` hoặc handler async, không phải stack đồng bộ của caller. Kết hợp @Async proxy và method validation có thể tạo ordering/return-type validation khác. Bộ test đồng bộ trong bài **không chứng minh** hệ thống async sẽ ném cùng exception ngay tại lời gọi.

Để test async, phải chờ completion, kiểm tra cause và verify input/return rule theo contract đã thiết kế. Không dùng `Thread.sleep` làm cơ chế đồng bộ duy nhất.

## 16. Checklist khi viết bài test cho bean proxy thật

1. Project có Jakarta Bean Validation provider và Spring AOP/method validation support?
2. Bean service được Spring container quản lý, không tạo bằng `new` trong test?
3. Class-level `@Validated` nằm trên đúng target class?
4. Method cần validate có public proxy boundary, không final/private?
5. Test inject đúng bean reference thực tế từ ApplicationContext?
6. Assert `AopUtils.isAopProxy(bean)`, sau đó assert **constraint actually enforced**?
7. Có test một tham số `@NotBlank` sai, một `@Min` sai và các case hợp lệ?
8. Có test cascaded `@Valid` trên object sai, và `@NotNull` với object null?
9. Có test return-value `@NotNull` vi phạm, xác minh `ElementKind.RETURN_VALUE`?
10. Nếu có groups, có test @Validated class/method interaction?
11. Có test self-invocation để phát hiện đường gọi bỏ qua AOP?
12. Có biết Mockito mock/@WebMvcTest không thay thế full-context proxy test?
13. Có phân biệt service AOP `ConstraintViolationException` với Spring MVC built-in `HandlerMethodValidationException`?
14. Có xác định Spring `MethodValidationException` khi bật adapter?
15. Có tránh phụ thuộc thứ tự Set và raw default message text?
16. Có HTTP integration test đi qua controller vào **bean service thật** nếu API cần?
17. Có phân loại input violations/return violations đúng khi mapping HTTP status?
18. Có giữ response an toàn, không serialize raw `ConstraintViolation` hoặc invalid values?
19. Nếu service có @Transactional/@Async, có test riêng advisor/transaction/async semantics?
20. Có chạy lại full integration tests khi nâng Spring Boot/Spring Framework/provider?

**Kết luận:** method validation của Spring là **hành vi tại biên AOP proxy**. Annotation trên source code không đủ để chứng minh nó chạy. Để test đúng, lấy bean thật bằng `@SpringBootTest`, xác nhận `AopUtils.isAopProxy`, gọi các method có constraints qua bean đã inject và kiểm tra exceptions/violations. Đối chứng bằng `new` và self-invocation sẽ cho thấy tại sao các unit tests không qua proxy có thể bỏ sót lỗi. Khi kết hợp với MVC, giữ ranh giới rõ giữa service AOP validation, controller argument validation và controller built-in method validation từ Spring 6.1.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): tự cấu hình method validation khi có Jakarta provider, sử dụng `@Validated` ở class level.
- [Spring Framework 6.2 — Java Bean Validation / Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html): `MethodValidationPostProcessor`, proxy-based validation và exceptions.
- [Spring Framework 6.1 — MethodValidationPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html): advisor/pointcut, nhóm validation và `setAdaptConstraintViolations`.
- [Spring Framework 6.1 — @Validated Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/validation/annotation/Validated.html): class pointcut và method-level group override.
- [Spring Framework — Spring AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK vs CGLIB proxy, final/private, self-invocation.
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `ExecutableValidator`, parameter/return constraints, cascading và inheritance rules.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` và `@AutoConfigureMockMvc`.
