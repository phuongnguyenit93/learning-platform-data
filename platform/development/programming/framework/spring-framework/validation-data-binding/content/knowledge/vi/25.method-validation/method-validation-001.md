# Ràng buộc trên tham số và giá trị trả về trong Spring Framework

## 1. Bản chất của method validation

Ràng buộc trên tham số và giá trị trả về mô tả **hợp đồng của một phương thức**. Tham số là *tiền điều kiện* mà người gọi phải thỏa trước khi thực thi; giá trị trả về là *hậu điều kiện* mà phương thức phải đáp ứng sau khi thực thi. Jakarta Bean Validation cho phép khai báo các quy tắc này bằng annotation quen thuộc, thay vì chỉ đặt constraint trên thuộc tính của DTO.

~~~java
public @NotBlank String createCode(
        @NotBlank String prefix,
        @Min(1) int sequence) {
    return prefix + "-" + sequence;
}
~~~

Trong ví dụ, `prefix` không được `null`, rỗng hoặc toàn khoảng trắng; `sequence` phải từ 1 trở lên; chuỗi được trả về không được trống. Ràng buộc nằm trên các **tham số** hoặc **phương thức**, nên kiểm tra giá trị đầu vào/đầu ra của lần gọi thay vì kiểm tra field của một bean đã có sẵn.

Điểm dễ nhầm nhất: **annotation không khiến JVM tự động validate mỗi lần gọi**. Phải có thành phần thực hiện validation, chẳng hạn Spring AOP interceptor cho service, cơ chế method validation của Spring MVC 6.1+, hoặc lời gọi `ExecutableValidator` thủ công.

Bài học này phân biệt ba điểm kích hoạt:

| Ngữ cảnh | Cách kích hoạt | Tình huống điển hình |
| --- | --- | --- |
| Spring service/bean | `@Validated` ở cấp class và lời gọi đi qua Spring proxy | Kiểm tra tham số service và kết quả trả về |
| Spring MVC 6.1+ handler | Constraint trực tiếp trên handler parameter hoặc return value; MVC tích hợp sẵn | Trả lỗi HTTP cho input sai hoặc return không hợp lệ |
| Jakarta Validation thuần | `validator.forExecutables()` rồi gọi `validateParameters` / `validateReturnValue` | Test, integration tùy chỉnh, hiểu cơ chế gốc |

`@Valid` là chỉ dẫn **cascaded validation** cho object lồng nhau, không phải constraint cấm `null` và không tự khởi tạo interceptor. Với Spring Boot 3.x, package của chuẩn là `jakarta.validation.*`, không dùng lẫn `javax.validation.*` của thế hệ trước.

## 2. Các loại ràng buộc của executable

### 2.1. Trên từng tham số

~~~java
public void reserve(
        @NotBlank String sku,
        @Min(1) int quantity,
        @NotNull @Valid Address address) {
    // Xử lý nghiệp vụ sau khi tham số hợp lệ.
}
~~~

`@NotBlank` kiểm tra `CharSequence`, `@Min` kiểm tra giá trị số, `@NotNull` cấm null, còn `@Valid` đi vào các constraint của `Address` (ví dụ `@NotBlank city`). Ràng buộc `@Valid` riêng lẻ vẫn xem `null` là hợp lệ; cần kết hợp `@NotNull` nếu object là bắt buộc.

Cẩn thận với null semantics: các constraint như `@Min` và `@Size` thường chấp nhận null; đó là thiết kế để có thể kiểm tra “bắt buộc” bằng `@NotNull` độc lập. Không dùng `@NotBlank` trên loại không phải `CharSequence` như `Order` hoặc `List<Order>`. Nếu giá trị là số nhưng truyền từ HTTP dưới dạng chuỗi, Spring thực hiện binding/conversion trước khi Jakarta Validation kiểm tra kiểu sau chuyển đổi.

### 2.2. Trên giá trị trả về

Đặt constraint lên **khai báo method** để validate kết quả:

~~~java
@NotNull(message = "Không tìm thấy dữ liệu trả về")
public Customer findCustomer(String id) {
    // ...
}

@NotEmpty
public List<@NotNull @Valid Customer> getCustomers() {
    // ...
}
~~~

Ở method `findCustomer`, `@NotNull` áp dụng lên **giá trị trả về**, không phải tham số `id`. Ở method `getCustomers`:
- `@NotEmpty` ràng buộc list khác null và có ít nhất một phần tử.
- `@NotNull` trên tham số kiểu buộc từng phần tử của list khác null.
- `@Valid` trên tham số kiểu yêu cầu cascade vào từng object `Customer`.

Để áp dụng constraint lên phần tử của container tùy chỉnh, Bean Validation còn cần `ValueExtractor` thích hợp; đối với `List`/`Map`/`Optional`, các provider phổ biến đã hỗ trợ extractor mặc định.

Phân biệt:

| Khai báo | `null` là lỗi? | Ý nghĩa |
| --- | --- | --- |
| `@NotNull Foo find()` | Có | Object kết quả không được null |
| `@NotBlank String code()` | Có | String không null và có ký tự không phải khoảng trắng |
| `@Size(min=1) List<?> items()` | Không, nếu chỉ dùng `@Size` | Chỉ kiểm tra size khi list khác null |
| `@NotNull @Size(min=1) List<?> items()` | Có | List phải tồn tại và có phần tử |
| `@Valid Foo load()` | Không | Cascade khi có object kết quả |

Kiểm tra return value **diễn ra sau khi thân method đã chạy**. Violation ở hậu điều kiện không chứng minh rằng nghiệp vụ chưa tạo side effect, và không tự cam kết sẽ rollback transaction.

### 2.3. Ràng buộc liên tham số

Quy tắc “`startDate` không sau `endDate`” không được đảm bảo chỉ bởi `@NotNull` trên hai tham số. Đây là **cross-parameter constraint**, kiểm tra `Object[]` biểu diễn toàn bộ bộ tham số trong một lần gọi. Phần 7 có ví dụ đầy đủ.

### 2.4. Constructor

Jakarta Validation cũng có thể kiểm tra tham số constructor và object tạo ra:
- `ExecutableValidator.validateConstructorParameters(...)`;
- `ExecutableValidator.validateConstructorReturnValue(...)`.

Lời gọi Java `new` thông thường **không đi qua Spring bean proxy**, vì vậy đừng kỳ vọng `@Validated` trên một service tự kích hoạt validation của tất cả constructor ứng dụng.

## 3. Ví dụ chạy được: Spring Boot 3.5.7, Java 17

Ví dụ có một service kiểm tra tham số lẫn giá trị trả về, một controller thể hiện validation của Spring MVC, cùng test JUnit. Dùng Spring Boot 3.5.7 (Spring Framework 6.2), Java 17 và Jakarta Validation.

Cấu trúc tệp:

~~~text
pom.xml
src/main/java/com/example/demo/
  DemoApplication.java
  Customer.java
  CodeService.java
  CodeController.java
src/test/java/com/example/demo/
  CodeServiceTest.java
  CodeControllerTest.java
  ExecutableValidationTest.java
~~~

### 3.1. Dependencies

~~~xml
<!-- pom.xml -->
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
    <artifactId>method-validation-demo</artifactId>
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
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-validation` cung cấp API và provider Jakarta Validation (thường Hibernate Validator). `spring-boot-starter-aop` hỗ trợ interception ở service. `spring-boot-starter-web` cần cho controller Spring MVC và `MockMvc` trong test.

### 3.2. Bootstrap

~~~java
// src/main/java/com/example/demo/DemoApplication.java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 3.3. Object kết quả có constraint lồng nhau

~~~java
// src/main/java/com/example/demo/Customer.java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;

public final class Customer {
    @NotBlank(message = "Tên khách hàng không được trống")
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

### 3.4. Service áp dụng method constraints

~~~java
// src/main/java/com/example/demo/CodeService.java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CodeService {

    @NotBlank(message = "Mã trả về không được trống")
    public String createCode(
            @NotBlank(message = "Tiền tố không được trống") String prefix,
            @Min(value = 1, message = "Thứ tự phải từ 1") int sequence) {
        return prefix + "-" + sequence;
    }

    // Cố tình sai để quan sát hậu điều kiện.
    @NotBlank(message = "Mã trả về không được trống")
    public String brokenCode() {
        return "";
    }

    // @Valid kiểm tra sâu object được trả về.
    @NotNull(message = "Khách hàng không được null")
    @Valid
    public Customer brokenCustomer() {
        return new Customer("");
    }
}
~~~

`@Validated` tại **cấp class** làm Spring nhận diện bean cần method validation. Khi ứng dụng gọi `createCode(" ", 0)` qua proxy, cả hai tham số vi phạm constraint, và interceptor báo lỗi trước khi gọi thân method. `brokenCode()` sẽ chạy và trả `""` rồi bị kiểm tra return value; `brokenCustomer()` thất bại vì `Customer.name` vi phạm `@NotBlank` sau cascaded validation.

Không cần gọi `Validator.validate(...)` trong phương thức service. Spring sẽ thực hiện kiểm tra qua integration của nó khi bean và interceptor đã được cấu hình.

### 3.5. JUnit xác minh lời gọi qua Spring proxy

~~~java
// src/test/java/com/example/demo/CodeServiceTest.java
package com.example.demo;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CodeServiceTest {

    @Autowired
    CodeService service;

    @Test
    void acceptsValidParametersAndReturn() {
        assertEquals("ORD-7", service.createCode("ORD", 7));
    }

    @Test
    void rejectsInvalidParameters() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.createCode(" ", 0));
        assertEquals(2, ex.getConstraintViolations().size());
    }

    @Test
    void rejectsInvalidReturnValue() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                service::brokenCode);
        assertEquals(1, ex.getConstraintViolations().size());
    }

    @Test
    void validatesReturnedObjectRecursively() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                service::brokenCustomer);
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("Tên khách hàng không được trống",
                ex.getConstraintViolations().iterator().next().getMessage());
    }
}
~~~

**Kết quả kỳ vọng:** bốn test PASS khi `CodeService` được cấp từ Spring context. Với cơ chế method validation AOP mặc định của Spring Boot 3.5, violation thường được đóng trong `jakarta.validation.ConstraintViolationException`. Nếu ứng dụng cấu hình `MethodValidationPostProcessor` theo chế độ `adaptConstraintViolations`, có thể nhận `MethodValidationException` theo mô hình lỗi của Spring; mã bắt lỗi phải phù hợp cấu hình thực tế.

Nếu tự gọi `new CodeService().createCode(" ", 0)` thay vì bean injected, không có proxy kiểm tra và method có thể trả chuỗi `" -0"`. Việc đặt annotation không làm một Java object thông thường tự động được validate.

## 4. Spring MVC: constraint trực tiếp trên handler parameter và return

Spring Framework 6.1 trở lên có **built-in method validation** cho `@RequestMapping` handler. Khi method có constraint thực sự trên tham số hoặc trên giá trị trả về, MVC kiểm tra contract của method. Không cần gắn `@Validated` cấp class trên controller trong phương án này.

### 4.1. Controller

~~~java
// src/main/java/com/example/demo/CodeController.java
package com.example.demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/codes")
public class CodeController {

    @GetMapping("/preview")
    @NotBlank(message = "Kết quả không được trống")
    public String preview(
            @RequestParam @NotBlank String prefix,
            @RequestParam @Min(1) int sequence) {
        return prefix + "-" + sequence;
    }
}
~~~

Không thêm `@Validated` trên `CodeController`: annotation cấp class sẽ khiến method validation đi theo hướng AOP proxy, thay vì cơ chế MVC tích hợp dành cho controller của Spring Framework 6.1+.

Request hợp lệ:

~~~http
GET /api/codes/preview?prefix=INV&sequence=3 HTTP/1.1
Host: localhost:8080
~~~

Response body:

~~~text
INV-3
~~~

Nếu `prefix` trống hoặc `sequence=0`, Spring MVC method validation báo lỗi tham số. Mặc định nó ném `HandlerMethodValidationException` tương ứng HTTP **400 Bad Request**. Khi **giá trị trả về** vi phạm ràng buộc của method, cùng loại exception tương ứng HTTP **500 Internal Server Error**, bởi đó là lỗi contract đầu ra của phía server.

### 4.2. MockMvc test

~~~java
// src/test/java/com/example/demo/CodeControllerTest.java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CodeControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validRequest() throws Exception {
        mvc.perform(get("/api/codes/preview")
                .param("prefix", "INV")
                .param("sequence", "3"))
            .andExpect(status().isOk())
            .andExpect(content().string("INV-3"));
    }

    @Test
    void invalidParameter() throws Exception {
        mvc.perform(get("/api/codes/preview")
                .param("prefix", "")
                .param("sequence", "0"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Kết quả kỳ vọng: request hợp lệ nhận HTTP 200 với nội dung `INV-3`; request không hợp lệ nhận HTTP 400. Body lỗi có thể được tùy biến bằng `@ControllerAdvice`/`ProblemDetail` nên không nên giả định định dạng lỗi cố định trong test chung.

### 4.3. `@Valid @RequestBody` có giống method validation không?

Xét một handler chỉ có `@Valid` trên object request:

~~~java
@PostMapping("/orders")
public void submit(@Valid @RequestBody OrderForm form) {
    // ...
}
~~~

Đây là **đoạn handler minh họa**, giả định `OrderForm` là DTO có field constraints. Nếu không có direct method constraint khác, MVC thường áp dụng validation cho từng argument và báo lỗi bằng `MethodArgumentNotValidException`.

Nếu thêm constraint trực tiếp trên một tham số:

~~~java
@PostMapping("/orders")
public void submit(
        @RequestParam @Min(1) int retries,
        @Valid @RequestBody OrderForm form) {
    // ...
}
~~~

`@Min(1)` kích hoạt method validation cho handler, và cơ chế này bao gồm nested validation cho `OrderForm`. Khi có violation, Spring MVC thường dùng `HandlerMethodValidationException`. Các trường hợp có `Errors` hoặc `BindingResult` ngay sau tham số có quy tắc xử lý riêng: handler có thể được gọi khi mọi lỗi đều thuộc các tham số có `Errors` ngay sau và không có lỗi trên tham số khác.

**Cần xử lý cả hai dạng exception** khi xây một API có nhiều loại handler: `MethodArgumentNotValidException` cho kiểm tra request object riêng lẻ, và `HandlerMethodValidationException` cho method validation.

## 5. Kiểm tra thủ công với `ExecutableValidator`

Lớp chuẩn `jakarta.validation.executable.ExecutableValidator` định nghĩa các thao tác:
- `validateParameters(object, method, values, groups...)`: kiểm tra tham số và cross-parameter.
- `validateReturnValue(object, method, returnValue, groups...)`: kiểm tra giá trị trả về, kể cả cascade.
- `validateConstructorParameters(constructor, values, groups...)`.
- `validateConstructorReturnValue(constructor, createdObject, groups...)`.

Các phương thức trên **không gọi method nghiệp vụ**, chỉ đánh giá các giá trị được cung cấp. Điều này giúp xác định xem một lỗi nằm ở constraint definition hay nằm ở cấu hình Spring integration.

~~~java
// src/test/java/com/example/demo/ExecutableValidationTest.java
package com.example.demo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.executable.ExecutableValidator;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ExecutableValidationTest {

    @Test
    void manuallyChecksParametersAndResult() throws Exception {
        CodeService target = new CodeService();

        Method create = CodeService.class.getMethod(
                "createCode", String.class, int.class);
        Method broken = CodeService.class.getMethod("brokenCode");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            ExecutableValidator executable =
                    factory.getValidator().forExecutables();

            var invalidInput = executable.validateParameters(
                    target, create, new Object[]{" ", 0});

            var invalidResult = executable.validateReturnValue(
                    target, broken, "");

            assertEquals(2, invalidInput.size());
            assertEquals(1, invalidResult.size());
        }
    }
}
~~~

Chạy toàn bộ test:

~~~bash
mvn test
~~~

Với project và code ở trên, kỳ vọng **7 test PASS**: 4 service, 2 MVC, 1 Jakarta executable. Nếu chỉ muốn chạy test API thuần:

~~~bash
mvn -Dtest=ExecutableValidationTest test
~~~

Chưa thể khẳng định nguyên văn log Maven vì log phụ thuộc runtime. Test thủ công này gọi `ExecutableValidator` trên một `new CodeService()`; vì vậy nó chứng minh constraint có thể được kiểm tra **không cần Spring proxy** khi bạn chủ động gọi API.

### 5.1. Property path của method violation

`ConstraintViolation#getPropertyPath()` có các node thường gặp:
- `ElementKind.METHOD`: method đang được kiểm tra.
- `ElementKind.PARAMETER`: tham số gây lỗi.
- `ElementKind.CROSS_PARAMETER`: quan hệ giữa nhiều tham số.
- `ElementKind.RETURN_VALUE`: kết quả trả về.
- `ElementKind.PROPERTY`: thuộc tính lồng nhau khi cascade.

Chuỗi path có thể giống `createCode.arg0`, `createCode.prefix`, hoặc `brokenCode.<return value>`. Tên tham số có thể thay đổi theo cờ biên dịch `-parameters` và `ParameterNameProvider`, vì vậy phần mềm xử lý lỗi nên ưu tiên các node và `Path.Node#getKind()` thay vì suy luận cứng từ tên chuỗi.

Một đoạn duyệt node minh họa, dùng bên trong test nơi `invalidInput` đã tồn tại:

~~~java
for (var violation : invalidInput) {
    for (var node : violation.getPropertyPath()) {
        System.out.println(node.getKind() + ": " + node.getName());
    }
}
~~~

Không ghi cố định stdout tên param vì provider/metadata có thể khác nhau.

## 6. Cross-parameter constraint cho nhiều tham số

Khi phương thức có `start` và `end` đều là `LocalDate`, `@NotNull` đảm bảo chúng tồn tại nhưng không đảm bảo `start <= end`. Ta có thể khai báo annotation dành cho mảng tham số và validator có `ValidationTarget.PARAMETERS`.

### 6.1. Annotation

~~~java
// src/main/java/com/example/demo/ChronologicalDates.java
package com.example.demo;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({ElementType.METHOD, ElementType.CONSTRUCTOR,
         ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ChronologicalDatesValidator.class)
public @interface ChronologicalDates {
    String message() default "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

### 6.2. Validator

~~~java
// src/main/java/com/example/demo/ChronologicalDatesValidator.java
package com.example.demo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;
import java.time.LocalDate;

@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public final class ChronologicalDatesValidator
        implements ConstraintValidator<ChronologicalDates, Object[]> {

    @Override
    public boolean isValid(Object[] args,
                           ConstraintValidatorContext context) {
        if (args == null || args.length != 2) {
            throw new IllegalArgumentException(
                    "ChronologicalDates yêu cầu đúng hai tham số");
        }
        if (args[0] == null || args[1] == null) {
            return true; // Giao cho @NotNull xử lý từng tham số.
        }
        LocalDate start = (LocalDate) args[0];
        LocalDate end = (LocalDate) args[1];
        return !start.isAfter(end);
    }
}
~~~

`@SupportedValidationTarget(ValidationTarget.PARAMETERS)` làm rõ đây là constraint áp dụng cho **toàn bộ tham số**, không phải return value. Validator chỉ phù hợp với executable có đúng hai tham số `LocalDate`. Trên method như sau:

~~~java
// Đoạn minh họa nằm trong @Service @Validated.
// Các import cần có: LocalDate, NotNull và ChronologicalDates.
@ChronologicalDates
public void schedule(@NotNull LocalDate start,
                     @NotNull LocalDate end) {
    // ...
}
~~~

Nếu `start` sau `end`, violation của custom constraint thuộc **cross-parameter**. Nó không mặc định tự ánh xạ vào một trường `end` trong UI. Nếu muốn field path cụ thể, cần tạo custom violation đúng node và kiểm tra metadata `ConstraintViolation#getPropertyPath()`.

Khi constraint có thể nhắm cả return và parameters, spec yêu cầu phân biệt target cho tình huống nhập nhằng (ví dụ `validationAppliesTo` với `ConstraintTarget.PARAMETERS`). Không viết một `ConstraintValidator<..., Object[]>` như validator giá trị trả về nếu thực chất muốn kiểm tra quan hệ giữa tham số.

## 7. Groups, kế thừa và những giới hạn thiết kế

### 7.1. Nhóm validation

Group mặc định là `jakarta.validation.groups.Default`. Bạn có thể tạo group đặc biệt:

~~~java
public interface FinalSubmission {}

public void confirm(
        @NotBlank(groups = FinalSubmission.class) String token) {
    // ...
}
~~~

Đây là **hai khai báo minh họa**, cần đặt interface và method vào class phù hợp. Constraint `@NotBlank` trong ví dụ thuộc `FinalSubmission`, nên không tự chạy khi chỉ validate group Default. Có thể chọn `@Validated(FinalSubmission.class)` ở mức bean/method phù hợp với Spring integration, hoặc gọi:

~~~java
// Đoạn minh họa khi đã có executable, target, method và args:
executable.validateParameters(
        target, method, args, FinalSubmission.class);
~~~

Kết hợp groups với `@Valid` và `@ConvertGroup` cần thiết kế cẩn thận để nhóm đang chạy đúng với mục tiêu của nghiệp vụ. Không kỳ vọng mọi group tự động chạy trong một lần.

### 7.2. Kế thừa/interface

Jakarta Bean Validation yêu cầu hợp đồng phương thức tuân nguyên lý thay thế:

- **Không tăng tiền điều kiện** ở subtype: thêm parameter constraint mới trong override của method không có constraint tương ứng ở base/interface thường vi phạm spec.
- **Có thể tăng hậu điều kiện** ở subtype: bổ sung một return constraint hợp lệ có thể chấp nhận được.
- Không khai báo cascade return `@Valid` lặp lại nhiều lần dọc cùng nhánh kế thừa khi spec cấm double cascading.

Ví dụ **không hợp lệ theo quy tắc chuẩn**:

~~~java
interface Lookup {
    String find(String code);
}

class StrictLookup implements Lookup {
    @Override
    public String find(@NotBlank String code) {
        return code;
    }
}
~~~

`StrictLookup` thêm ràng buộc cho caller vốn có quyền gọi `Lookup.find` với chuỗi trống, nên provider có thể báo `ConstraintDeclarationException` khi phân tích constraints. Hướng đúng là đặt ràng buộc trong hợp đồng:

~~~java
interface Lookup {
    String find(@NotBlank String code);
}

class NormalLookup implements Lookup {
    @Override
    public String find(String code) {
        return code;
    }
}
~~~

Hai khối là **hai phương án độc lập**, không khai báo chung hai interface `Lookup` trong một source file. Khi interface được proxy, cũng nên test method validation từ bên ngoài bean, bởi kiểu proxy và metadata có thể ảnh hưởng cách framework tìm annotation.

### 7.3. Không phải mọi method đều được proxy

Spring AOP dùng proxy, vì vậy cần chú ý:
- Self-invocation `this.otherMethod(...)` không đi qua proxy.
- `private` method không thể được Spring AOP proxy chặn thông thường.
- `final` method không thể bị subclass proxy override để gắn interceptor; cấu hình JDK dynamic proxy/class proxy ảnh hưởng phạm vi.
- `static` method constraint không portable theo Jakarta Bean Validation.
- Object tạo bằng `new` ở ngoài Spring context không nhận được interceptor của Spring.

Cho service thông thường, bắt đầu bằng **public non-final method trên Spring bean** được gọi qua một bean khác. Chỉ cân nhắc weaving/AspectJ hay validation thủ công nếu có yêu cầu cụ thể.

### 7.4. Return validation và bất đồng bộ

Với `CompletionStage<T>`, `CompletableFuture<T>` hoặc reactive publisher, constraint trên chính kiểu return có thể chỉ kiểm tra **wrapper được trả về tại thời điểm method hoàn tất**, không tự động đợi phần tử tương lai. Nếu cần validate item được phát sau đó, sử dụng integration dành cho pipeline bất đồng bộ. Không gắn `@Valid` một cách máy móc rồi tin rằng mọi phần tử tương lai đã được đánh giá.

## 8. Xử lý exception theo đúng tầng

Có ba dạng thường gặp:

| Exception | Nơi thường phát sinh | Ý nghĩa |
| --- | --- | --- |
| `ConstraintViolationException` | Service method validation qua proxy (mặc định thông dụng) | Violation tham số hoặc return |
| `MethodArgumentNotValidException` | Spring MVC validate `@Valid @RequestBody`/`@ModelAttribute` một object riêng | Input object không hợp lệ |
| `HandlerMethodValidationException` | Spring MVC 6.1+ built-in method validation | Input method (thường 400) hoặc return method (thường 500) |

Spring AOP còn có cơ chế tùy chọn `MethodValidationException` khi bật điều chỉnh violations thành `MethodValidationResult` qua `MethodValidationPostProcessor`. Vì vậy, mã bắt exception cần xét **phiên bản Spring** và cấu hình đang chạy.

Với API, dùng `@ControllerAdvice`/`ResponseEntityExceptionHandler` để chuẩn hóa thông điệp và mã HTTP. Lỗi đầu vào nên xác định được parameter/field để người dùng sửa; lỗi return thường là lỗi phía server, không được che bằng HTTP 400. Tránh trả trực tiếp rejected values chứa token, mật khẩu hoặc dữ liệu nhạy cảm.

Trong controller, `BindingResult` ngay sau argument dạng form có thể giúp xử lý lỗi ngay tại handler. Tuy nhiên, với nhiều tham số và direct method constraints, Spring MVC chỉ gọi handler nếu mọi validation errors thuộc các tham số có `Errors` ngay sau; lỗi ở tham số khác sẽ làm phát sinh `HandlerMethodValidationException`.

## 9. Các lỗi phổ biến

1. **Nhầm `@Valid` với `@Validated`:** `@Valid` cascade object; `@Validated` của Spring gắn với method validation và groups tùy ngữ cảnh.
2. **Chỉ thêm constraint nhưng không kích hoạt validation:** cần Spring proxy/MVC integration/`ExecutableValidator`.
3. **Gọi service qua `new` hoặc `this`:** không đi qua Spring AOP interceptor.
4. **Gắn `@Validated` cấp class controller trên Spring MVC 6.1+** nhưng mong dùng built-in method validation; chọn đường tích hợp nhất quán.
5. **Bắt mỗi `MethodArgumentNotValidException`:** cần tính thêm `HandlerMethodValidationException` cho direct method constraints.
6. **Gán mọi violation thành HTTP 400:** return violation của server khác input invalid.
7. **Quên `@NotNull`:** các constraint như `@Min`/`@Size` không nhất thiết coi null là sai.
8. **Dùng sai constraint cho loại dữ liệu:** `@NotBlank` chỉ dành cho `CharSequence`, `@Min` cho số.
9. **Thêm parameter constraint ở override:** có thể vi phạm kế thừa và làm provider ném `ConstraintDeclarationException`.
10. **Dựa vào tên `arg0` trong path:** tên tham số có thể phụ thuộc `-parameters`/`ParameterNameProvider`.
11. **Cho rằng lỗi return sẽ đảo ngược side effect:** validation xảy ra sau thân method; thứ tự transaction interceptor có thể ảnh hưởng rollback.
12. **Bỏ qua test nested/cross-parameter:** test riêng cả giá trị hợp lệ, tham số sai, return sai, null và cascade.

## 10. Checklist triển khai

- Liệt kê tiền điều kiện từng tham số, quy tắc nhiều tham số và hậu điều kiện trả về.
- Chọn constraint đúng type; kết hợp `@NotNull` và `@Valid` khi cần.
- Với service: `@Service @Validated`, provider validation và AOP, lời gọi đi qua Spring bean.
- Với controller Spring MVC 6.1+: dùng constraint trực tiếp và cơ chế MVC tích hợp; quản lý HTTP 400/500 phù hợp.
- Dùng `ExecutableValidator` để test hợp đồng độc lập với Spring; xem property path theo node kind.
- Xử lý inheritance, groups, proxy boundaries, validation trên container/async return đúng semantics.
- Kiểm tra kết quả với test tích hợp trước khi sử dụng trên luồng nghiệp vụ có side effect.

## Tài liệu tham khảo

- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Jakarta Bean Validation — Method and constructor constraints, ExecutableValidator: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation — ExecutableValidator API: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator
- Hibernate Validator Reference Guide — Method constraints: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#chapter-method-constraints
