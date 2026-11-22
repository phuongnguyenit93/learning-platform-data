# Thực nghiệm kiểm tra tham số và giá trị trả về qua AOP proxy trong Spring Framework

## 1. Mục tiêu bài thực hành

Một service trong ứng dụng Spring có thể được gọi từ REST controller, message consumer, scheduled job hoặc service khác. Việc kiểm tra dữ liệu ở tầng HTTP **không đảm bảo** mọi lời gọi service đều hợp lệ. Jakarta Bean Validation hỗ trợ constraints trên tham số và giá trị trả về của method; Spring có thể tự áp dụng chúng khi lời gọi đi qua **AOP proxy**.

Ví dụ:

~~~java
@Service
@Validated
public class StockService {

    public String allocate(
            @NotBlank String sku,
            @Min(1) int units) {
        return sku + ":" + units;
    }

    @NotBlank
    public String findReference() {
        return "";
    }
}
~~~

Đây là đoạn **minh họa class**, cần imports để biên dịch. Khi `StockService` được Spring quản lý và được proxy bởi `MethodValidationPostProcessor`:
- Gọi `allocate("PEN", 2)` từ bean khác: thành công.
- Gọi `allocate("", 0)` **qua proxy**: kiểm tra tham số trước method body và ném `ConstraintViolationException`.
- Gọi `findReference()` **qua proxy**: method body chạy, rồi giá trị trả về rỗng vi phạm `@NotBlank` và ném `ConstraintViolationException`.
- Gọi `new StockService().allocate("",0)` trên object tự tạo, không có proxy: method body chạy, trừ khi chính code method tự validate.
- Bên trong service, gọi `this.allocate("",0)`: thường **bỏ qua advice** vì đây là self-invocation trên target.

Bài sẽ thực nghiệm và kiểm thử:
1. Có hay không có Spring-managed AOP proxy.
2. Constraint cho từng parameter trước khi thực hiện business logic.
3. Constraint cho return value **sau** khi method trả về.
4. `@Valid` cascade trên request/value-object đi qua method parameter.
5. `ConstraintViolation#getPropertyPath()` và `ElementKind.PARAMETER/RETURN_VALUE`.
6. Gọi trực tiếp object tạo bằng `new`, self-invocation và gọi qua bean khác.
7. Lỗi thường gặp với JDK/CGLIB proxy, `final`/`private`, validation groups và transaction advice.
8. Phân biệt AOP method validation của service với **built-in MVC method validation** từ Spring Framework 6.1.
9. Test JUnit/SpringBootTest và MockMvc với cách ánh xạ lỗi an toàn.
10. Khi nào dùng `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` và `MethodValidationException` thay cho exception mặc định.

Phiên bản ví dụ: **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Validation và JUnit Jupiter**. Các source files của project được cho đầy đủ, còn những đoạn khác được gắn nhãn minh họa. Kết quả kiểm thử trong bài là **kỳ vọng**, không khẳng định đã chạy Maven thực tế.

## 2. Cơ chế: bean, proxy, interceptor và ExecutableValidator

### 2.1. Đường chạy qua Spring AOP

~~~text
Bean khác hoặc controller
       |
       v
Spring-managed StockService reference
       |
       v
[AOP Proxy: JDK dynamic proxy hoặc CGLIB]
       |
       v
MethodValidationInterceptor
       |
       +-- ExecutableValidator.validateParameters(...)
       |        |
       |        +-- invalid -> ConstraintViolationException
       |
       v
Target StockService.allocate(...)
       |
       v
MethodValidationInterceptor
       |
       +-- ExecutableValidator.validateReturnValue(...)
       |        |
       |        +-- invalid -> ConstraintViolationException
       |
       v
Caller nhận return value hợp lệ
~~~

Thực tế Spring AOP có thể có nhiều advisors/interceptors (validation, transactions, caching, retry...). Thứ tự phụ thuộc cấu hình và `order`, nên sơ đồ trên chủ yếu minh họa **validation trước khi target body chạy và validation sau khi nhận return**. Đừng suy từ sơ đồ rằng transaction commit luôn diễn ra trước/sau return validation theo một thứ tự cố định cho mọi hệ thống; cần integration tests khi các advice có tác động phụ.

Spring Framework sử dụng `MethodValidationPostProcessor` để áp `MethodValidationInterceptor` vào các bean phù hợp. Với Spring Boot, tính năng method validation được auto-config khi có Bean Validation provider trên classpath; thường dùng `spring-boot-starter-validation`. Target class cần `@Validated` ở cấp type để được postprocessor chọn.

### 2.2. Hai bên của hợp đồng method

~~~java
public @NotBlank String reserve(
        @NotBlank String sku,
        @Min(1) int units) {
    return sku + ":" + units;
}
~~~

- Các constraints **trên parameters** được kiểm trước khi gọi target body.
- Các constraints **trên return value** đặt trên method, kiểm sau khi target body hoàn thành.
- `@Valid` trên một parameter hoặc return value cho phép *cascaded validation* các properties của object; `@Valid` bản thân không phải một constraint kiểm null.
- `@NotNull` trên parameter hoặc return giúp cấm null tường minh.
- Validation thường áp cho *public service methods được gọi qua proxy*, không phải một phép kiểm tra mỗi câu lệnh Java trong lớp.

### 2.3. Không chỉ là annotation

Thêm `@NotBlank` vào một method **không tự động** khiến mọi lời gọi Java thuần đều kiểm tra. Cần:
- Một Jakarta Bean Validation provider, ví dụ Hibernate Validator.
- Spring context tạo Bean Validation infrastructure.
- `MethodValidationPostProcessor` và proxy/advice phù hợp.
- Bean có `@Validated` theo cấu hình Spring-driven method validation.
- Caller lấy bean từ context và **đi qua proxy**.

Nếu bạn tự tạo `new StockService()`, gọi method trên object đó không đi qua interceptor. Nếu bạn lấy `StockService` bằng `@Autowired` từ Spring context, lời gọi qua proxy được bảo vệ.

## 3. Phân biệt Spring `@Validated` và Jakarta `@Valid`

| Annotation | Nơi dùng | Ý nghĩa |
| --- | --- | --- |
| `org.springframework.validation.annotation.Validated` | Class service | Đánh dấu bean cho Spring-driven method validation; có thể chọn groups |
| `jakarta.validation.Valid` | Parameter, field, getter, return | Cascade validation vào nested object |
| `jakarta.validation.constraints.NotBlank` | String parameter/return/property | Không null, không rỗng/toàn whitespace |
| `jakarta.validation.constraints.Pattern` | String parameter/property | Đúng regular expression |
| `jakarta.validation.constraints.Min` | Numeric parameter/property/return | Lớn hơn hoặc bằng ngưỡng |
| `jakarta.validation.constraints.NotNull` | Parameter/return/property | Bắt buộc không null |
| `org.springframework.validation.beanvalidation.MethodValidationPostProcessor` | Spring infrastructure | Tạo method-validation advisor/proxy |
| `jakarta.validation.executable.ExecutableValidator` | Jakarta API | Kiểm tra parameter/return của method trực tiếp |

Một lỗi phổ biến là chỉ đặt `@Valid` trên service class; annotation này **không thay `@Validated` ở type level** trong cơ chế Spring AOP method validation. Một lỗi khác là dùng `@Validated` nhưng chỉ đặt `@Valid` trên object parameter, rồi tưởng mọi method có `@Valid` sẽ bị kiểm tra giá trị null: muốn cấm null cần thêm `@NotNull`.

Một điểm cần tách bạch:
- **Spring MVC 6.1+** có built-in method validation riêng cho handler methods, ví dụ direct `@Min` trên `@RequestParam`; nó có thể ném `HandlerMethodValidationException`.
- **Spring service AOP** trong bài này dùng `MethodValidationPostProcessor` và, theo mặc định, ném `ConstraintViolationException`.
- Không nên đưa `@Validated` cấp controller class chỉ để kích hoạt MVC validation mới; tài liệu Spring khuyến nghị bỏ class-level `@Validated` trong controller nếu muốn dùng built-in MVC method validation. Còn với **service bean**, `@Validated` cấp class là điều kiện của ví dụ AOP này.

## 4. Exceptions: parameter và return phải được phân biệt

### 4.1. Mặc định: `ConstraintViolationException`

Spring method-validation interceptor thường ném:

~~~java
jakarta.validation.ConstraintViolationException
~~~

Exception này chứa `Set<ConstraintViolation<?>>`. Mỗi violation có:
- `getPropertyPath()`: đường dẫn method/parameter/property/return value.
- `getConstraintDescriptor()`: annotation constraint và attributes.
- `getMessage()`: thông điệp sau interpolation.
- `getMessageTemplate()`: template gốc.
- `getInvalidValue()`: **giá trị không hợp lệ, có thể là secret**.
- `getRootBean()`, `getLeafBean()`: tham chiếu object liên quan.

**Không serialize `ConstraintViolation` hoặc `ex.getMessage()` thành public JSON.** Nội dung có thể lộ input, Java method names, return value, regex hoặc dữ liệu nghiệp vụ.

### 4.2. Dùng Path node kind thay vì đoán từ chuỗi

Jakarta Validation có `jakarta.validation.ElementKind`:
- `ElementKind.PARAMETER` cho một tham số.
- `ElementKind.RETURN_VALUE` cho giá trị trả về.
- `ElementKind.PROPERTY` cho field lồng nhau được cascade.
- `ElementKind.METHOD` đại diện method.
- `ElementKind.CROSS_PARAMETER` cho constraint liên quan nhiều tham số.

Ví dụ duyệt:

~~~java
// Snippet bên trong test hoặc diagnostic code.
boolean isReturnViolation = violation.getPropertyPath()
        .iterator()
        .next()
        .getKind() == ElementKind.RETURN_VALUE;
~~~

**Đoạn trên chỉ minh họa việc đọc một node, không phải thuật toán đúng**: node đầu tiên của method property path thường là `METHOD`, không phải `RETURN_VALUE`. Cách chuẩn hơn là **duyệt toàn bộ nodes** rồi xem có `RETURN_VALUE` hay không (code runnable ở phần tests).

Không dựa vào chuỗi `".<return value>"` hoặc `"arg0"` vì tên parameter có thể thay đổi theo compiler `-parameters`, Hibernate Validator, provider và method signature. Chỉ dựa vào `Path.Node#getKind()` khi phân loại.

### 4.3. Mapping lỗi HTTP cần bối cảnh trust boundary

Một `ConstraintViolationException` từ **service** có thể xảy ra vì:
- Client đã gửi input sai đến service.
- Controller gọi service sai contract do bug.
- Message consumer/background job gọi service sai.
- Service trả về kết quả sai, là lỗi phía server.

Vì vậy, **không nên viết một global handler biến tất cả `ConstraintViolationException` thành HTTP 400**. Trong project:
- Endpoint `/lab/proxy/allocate` biết chắc hai parameter đi từ client và chỉ gọi một service method không có return constraint; nó bắt lỗi input ở **ngay biên này** để trả 400 với mã công khai tổng quát.
- Endpoint `/lab/proxy/broken-return` ném return violation từ service, global handler trả 500 tối giản.
- Với service exception không có đủ ngữ cảnh ở biên API, handler toàn cục mặc định trả 500, không tiết lộ message.

Ở production, có thể thêm validation phía REST request và chuyển đổi lỗi có chủ đích, không dùng catch-all 400 che bug nội bộ.

### 4.4. Tùy chọn: `MethodValidationException`

Từ Spring Framework 6.1, `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` yêu cầu interceptor biến các violations thành `MethodValidationResult` rồi ném `org.springframework.validation.method.MethodValidationException`. Khi đó kết quả có `ParameterValidationResult`/`MessageSourceResolvable` và có thể dùng message localization.

Ví dụ cấu hình **tùy chọn, không đồng thời dùng với demo mặc định**:

~~~java
@Configuration
class AdaptedMethodValidationConfig {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        MethodValidationPostProcessor p =
                new MethodValidationPostProcessor();
        p.setAdaptConstraintViolations(true);
        return p;
    }
}
~~~

Đây là **snippet**, cần imports `org.springframework.context.annotation.Bean`, `Configuration` và `org.springframework.validation.beanvalidation.MethodValidationPostProcessor`. Khi triển khai trong Boot, phải chú ý auto-configuration/back-off để chỉ có postprocessor có chủ đích; đừng đăng ký hai bean method-validation postprocessors rồi bất ngờ nhận nested proxy/advice.

**Quan trọng:** khi bật option này, tests đang chờ `ConstraintViolationException` trong project sẽ cần cập nhật sang `MethodValidationException`. Đừng bật flag lẫn lộn rồi khẳng định cùng một behavior.

## 5. Project thực hành chạy được (Java 17, Spring Boot 3.5.7)

Mục tiêu là **học AOP proxy qua service**, không biến controller thành một mẫu ứng dụng quản lý kho production. Project gồm một service có direct constraints, một nested DTO, một facade gọi service qua bean reference và một HTTP adapter để nhìn thấy kết quả.

### 5.1. Cấu trúc

~~~text
pom.xml
src/main/java/com/example/methodaop/
  MethodAopApplication.java
  AllocationCommand.java
  StockService.java
  StockFacade.java
  StockLabController.java
  SafeMethodErrorAdvice.java
src/test/java/com/example/methodaop/
  StockServiceProxyTest.java
  ExecutableValidatorTest.java
  StockLabHttpTest.java
~~~

### 5.2. `pom.xml`

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
    <artifactId>method-validation-aop-lab</artifactId>
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

`spring-boot-starter-validation` cung cấp Bean Validation provider. Spring Boot 3.5 auto-config method validation khi provider hiện diện; `spring-boot-starter-aop` khai báo rõ ý định dùng proxy infrastructure. Không cần tự khai báo một `MethodValidationPostProcessor` trong **demo mặc định**; Boot sẽ thiết lập nó. Nếu project thực tế tắt auto-config hoặc dùng Spring Framework không có Boot, cần đăng ký postprocessor phù hợp theo hướng dẫn chính thức.

### 5.3. `MethodAopApplication.java`

~~~java
// src/main/java/com/example/methodaop/MethodAopApplication.java
package com.example.methodaop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodAopApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodAopApplication.class, args);
    }
}
~~~

### 5.4. `AllocationCommand.java`: cascade trên record

~~~java
// src/main/java/com/example/methodaop/AllocationCommand.java
package com.example.methodaop;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record AllocationCommand(
        @NotBlank
        @Pattern(regexp = "[A-Z]{3,8}")
        String sku,

        @Min(1)
        int units) {
}
~~~

- `@NotBlank` từ chối chuỗi null, rỗng hoặc whitespace.
- `@Pattern` chỉ cho từ 3 đến 8 chữ cái A–Z, để dễ quan sát một đầu vào có canary marker bị chặn. Regex là quy tắc demo, không phải SKU policy chung.
- `@Min(1)` kiểm tra số lượng.
- Record là immutable; method service sẽ nhận nó thông qua `@Valid` để cascade validation. Thêm `@NotNull` ở method parameter để cấm object null.

### 5.5. `StockService.java`: nơi AOP thực sự hoạt động

~~~java
// src/main/java/com/example/methodaop/StockService.java
package com.example.methodaop;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import java.util.concurrent.atomic.AtomicInteger;

@Service
@Validated
public class StockService {

    private final AtomicInteger executions = new AtomicInteger();

    public String allocate(
            @NotBlank @Pattern(regexp = "[A-Z]{3,8}") String sku,
            @Min(1) int units) {

        executions.incrementAndGet();
        return sku + ":" + units;
    }

    public String allocateCommand(
            @NotNull @Valid AllocationCommand input) {

        executions.incrementAndGet();
        return input.sku() + ":" + input.units();
    }

    @NotBlank
    public String brokenReference() {
        // Cố ý trả chuỗi rỗng để kiểm thử return constraint.
        return "";
    }

    // Phương thức wrapper không có constraints.
    public String callThroughThis() {
        // Self-invocation trên target, không đi lại qua proxy.
        return this.allocate("", 0);
    }

    public int executionCount() {
        return executions.get();
    }
}
~~~

**Điểm thực nghiệm quan trọng:**

1. `@Service` để Spring tạo bean.
2. `@Validated` cấp class để Spring method-validation postprocessor chọn target.
3. `@NotBlank`, `@Pattern`, `@Min` trực tiếp trên `allocate` parameters.
4. `@NotNull @Valid` trên `allocateCommand`: null object và nested fields được kiểm riêng.
5. `@NotBlank` trên `brokenReference()` là constraint **trên method return value**.
6. `AtomicInteger` quan sát method body có chạy hay không.
7. `callThroughThis()` cố ý gọi `this.allocate("",0)` để chứng minh self-invocation bypass. **Không sao chép anti-pattern này vào business code production.**

Trong một lời gọi **qua proxy** với tham số sai, `executions` không tăng vì interceptor từ chối trước khi target body chạy. Khi `brokenReference()` trả `""`, target body đã chạy rồi; interceptor mới báo lỗi return-value.

`StockService` không implements interface và **không final**. Với cấu hình class-based proxy phù hợp, Spring có thể tạo CGLIB subclass; tests chỉ yêu cầu có AOP proxy, không phụ thuộc tên class proxy hay ký hiệu `$$SpringCGLIB$$`.

### 5.6. `StockFacade.java`: lời gọi đi qua một bean khác

~~~java
// src/main/java/com/example/methodaop/StockFacade.java
package com.example.methodaop;

import org.springframework.stereotype.Component;

@Component
public class StockFacade {

    private final StockService stock;

    public StockFacade(StockService stock) {
        this.stock = stock;
    }

    public String allocateInvalidThroughDependency() {
        // Reference được inject là Spring-managed bean/proxy.
        return stock.allocate("", 0);
    }

    public String allocateValidThroughDependency() {
        return stock.allocate("PEN", 2);
    }
}
~~~

Đường chạy:

~~~text
StockFacade.allocateInvalidThroughDependency()
     |
     v
Injected StockService proxy
     |
     v
MethodValidationInterceptor.validateParameters(...)
     |
     v
ConstraintViolationException (target allocate() không chạy)
~~~

Ngược lại, `StockService.callThroughThis()` chạy trên target đã đi vào method và gọi tiếp `this.allocate("",0)`; lời gọi nội bộ không quay lại proxy. Không nên sửa bằng cách gọi `AopContext.currentProxy()` nếu có thể refactor qua một bean khác; cách đó phụ thuộc proxy exposure và coupling với AOP.

### 5.7. `StockLabController.java`: HTTP boundary tách input và internal bug

~~~java
// src/main/java/com/example/methodaop/StockLabController.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/lab/proxy")
public class StockLabController {

    private final StockService stock;

    public StockLabController(StockService stock) {
        this.stock = stock;
    }

    @GetMapping("/allocate")
    public ResponseEntity<?> allocate(
            @RequestParam String sku,
            @RequestParam int units) {

        // Endpoint này chuyển CHÍNH HAI input của client
        // sang allocate, vốn KHÔNG có return constraint.
        try {
            return ResponseEntity.ok(
                    Map.of("receipt", stock.allocate(sku, units)));
        } catch (ConstraintViolationException invalidInput) {
            // Chỉ mapping có chủ đích tại đúng trust boundary.
            // Không return invalidInput.getMessage().
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_ALLOCATION_INPUT"));
        }
    }

    @GetMapping("/broken-return")
    public String brokenReturn() {
        // Return-value violation của service phải là 500.
        return stock.brokenReference();
    }
}
~~~

Ở đây `ConstraintViolationException` được bắt cục bộ trong endpoint `allocate` bởi ta đã biết **trực tiếp** method đang gọi nhận hai input từ request và không có return constraint. Trong service thật với nhiều thao tác, không được tùy tiện coi mọi `ConstraintViolationException` là lỗi của client.

Nếu `units=abc`, Spring MVC có thể thất bại khi parse `@RequestParam int` **trước** khi gọi service. Loại lỗi này là `MethodArgumentTypeMismatchException` của argument resolver, không phải AOP `ConstraintViolationException`. Demo có safe handler riêng cho case đó, nhưng trọng tâm vẫn là kiểm tra qua proxy.

### 5.8. `SafeMethodErrorAdvice.java`: không làm lộ chi tiết service

~~~java
// src/main/java/com/example/methodaop/SafeMethodErrorAdvice.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.Map;

@RestControllerAdvice
public class SafeMethodErrorAdvice {

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<Map<String, String>> internalContractFailure(
            ConstraintViolationException ignored) {

        // Bên ngoài endpoint allocate, không giả định
        // service exception là lỗi client: mặc định 500.
        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("code", "INTERNAL_METHOD_CONTRACT_ERROR"));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Map<String, String>> badQueryType(
            MethodArgumentTypeMismatchException ignored) {

        // Không echo raw query value hoặc converter exception.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_QUERY_TYPE"));
    }
}
~~~

Không dùng `getMessage()`/`getInvalidValue()`/`getPropertyPath()` nguyên dạng để trả HTTP response. Với production, nên chuẩn hóa error format bằng `ProblemDetail`, quyết định public code/path/message một cách rõ, giữ log/traces an toàn và thực hiện authorization ở service.

## 6. Test qua Spring context: chứng minh method interceptor đang hoạt động

### 6.1. `StockServiceProxyTest.java`

~~~java
// src/test/java/com/example/methodaop/StockServiceProxyTest.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.ElementKind;
import jakarta.validation.ConstraintViolation;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

import java.util.Set;
import java.util.stream.StreamSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class StockServiceProxyTest {

    @Autowired
    StockService stock;

    @Autowired
    StockFacade facade;

    @Autowired
    ApplicationContext context;

    private static boolean hasNodeKind(
            ConstraintViolation<?> violation, ElementKind expected) {
        return StreamSupport.stream(
                violation.getPropertyPath().spliterator(), false)
                .anyMatch(node -> node.getKind() == expected);
    }

    @Test
    void springBeanIsActuallyAnAopProxy() {
        assertTrue(AopUtils.isAopProxy(stock));

        assertFalse(context.getBeansOfType(
                MethodValidationPostProcessor.class).isEmpty());
    }

    @Test
    void invalidParametersThrowBeforeBusinessBodyRuns() {
        int before = stock.executionCount();

        ConstraintViolationException error =
                assertThrows(ConstraintViolationException.class,
                        () -> stock.allocate(
                                "CANARY_PRIVATE_SKU", 0));

        assertEquals(before, stock.executionCount());
        assertTrue(error.getConstraintViolations().stream()
                .anyMatch(v -> hasNodeKind(
                        v, ElementKind.PARAMETER)));

        // Không assert exact exception.getMessage(): nó có thể
        // chứa input, tên parameter, message tùy provider.
    }

    @Test
    void validParametersRunBodyAndReturnExpectedValue() {
        int before = stock.executionCount();

        String receipt = stock.allocate("PEN", 2);

        assertEquals("PEN:2", receipt);
        assertEquals(before + 1, stock.executionCount());
    }

    @Test
    void returnConstraintIsCheckedAfterMethodBody()
            throws Exception {

        ConstraintViolationException error =
                assertThrows(ConstraintViolationException.class,
                        () -> stock.brokenReference());

        assertTrue(error.getConstraintViolations().stream()
                .anyMatch(v -> hasNodeKind(
                        v, ElementKind.RETURN_VALUE)));
    }

    @Test
    void manuallyConstructedObjectHasNoSpringProxy() {
        StockService plain = new StockService();

        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals(":0", plain.allocate("", 0));
        assertEquals(1, plain.executionCount());
    }

    @Test
    void selfInvocationSkipsMethodValidationAdvice() {
        int before = stock.executionCount();

        // Outer call enters target; this.allocate bypasses proxy.
        String result = stock.callThroughThis();

        assertEquals(":0", result);
        assertEquals(before + 1, stock.executionCount());
    }

    @Test
    void injectedProxyFromAnotherBeanStillRejectsInvalidInput() {
        int before = stock.executionCount();

        assertThrows(ConstraintViolationException.class,
                () -> facade.allocateInvalidThroughDependency());

        assertEquals(before, stock.executionCount());
    }

    @Test
    void facadeCanCallValidServiceMethod() {
        int before = stock.executionCount();

        assertEquals("PEN:2",
                facade.allocateValidThroughDependency());

        assertEquals(before + 1, stock.executionCount());
    }

    @Test
    void cascadeValidationChecksNestedRecordProperties() {
        AllocationCommand invalid =
                new AllocationCommand("", 0);

        ConstraintViolationException error =
                assertThrows(ConstraintViolationException.class,
                        () -> stock.allocateCommand(invalid));

        Set<String> paths = error.getConstraintViolations()
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(java.util.stream.Collectors.toSet());

        assertTrue(paths.stream().anyMatch(
                path -> path.contains("sku")));
        assertTrue(paths.stream().anyMatch(
                path -> path.contains("units")));
    }

    @Test
    void notNullProtectsNullCommand() {
        assertThrows(ConstraintViolationException.class,
                () -> stock.allocateCommand(null));
    }

    @Test
    void validNestedCommandRunsBody() {
        int before = stock.executionCount();

        assertEquals("PEN:2",
                stock.allocateCommand(
                        new AllocationCommand("PEN", 2)));

        assertEquals(before + 1, stock.executionCount());
    }
}
~~~

**11 JUnit methods** ở class này. Điểm cốt lõi:
- `AopUtils.isAopProxy(stock)` chứng minh object injected không phải POJO thuần.
- `MethodValidationPostProcessor` tồn tại trong context.
- Input sai bị chặn **trước** increment trong target.
- Return invalid được nhận diện qua `ElementKind.RETURN_VALUE`.
- `new StockService()` và `this.allocate(...)` bypass advice, nhưng phép kiểm ở cấp method target **không tự chạy**.
- Lời gọi từ `StockFacade` qua injected bean reference đi qua proxy.
- `@NotNull @Valid` kiểm tra nested record; không chỉ primitive/direct scalar constraints.
- Không dùng exact parameter path như `arg0` hay `sku` làm điều kiện duy nhất vì parameter-name discovery/provider có thể khác nhau.

### 6.2. Tại sao self-invocation test có ý nghĩa?

Khi client gọi `stock.callThroughThis()`, lần gọi **ngoài** đi qua proxy. Nhưng method `callThroughThis` không có direct parameter/return constraints. Target method chạy, rồi:

~~~java
return this.allocate("", 0);
~~~

Đây là lời gọi qua `this` trên **target**. Proxy không intercept lại `allocate`, nên invalid parameters không được kiểm tra trong lời gọi nội bộ đó. Demo trả `":0"` và tăng execution count, hoàn toàn có chủ đích để quan sát điểm mù.

Cách khắc phục production:
1. Đưa logic được kiểm tra sang **bean riêng** và inject bean đó.
2. Đảm bảo mọi entrypoint nghiệp vụ quan trọng gọi method qua Spring-managed bean.
3. Nếu method phải an toàn trước mọi lời gọi kể cả trực tiếp, thêm kiểm tra invariant trong domain method/bên trong code hoặc dùng validation tường minh.
4. Không dựa hoàn toàn vào proxy advice như ranh giới bảo mật duy nhất.
5. Chỉ dùng self-injection/AopContext khi thật sự hiểu nguy cơ vòng phụ thuộc/coupling; refactor thành collaborators thường đơn giản hơn.

## 7. Jakarta ExecutableValidator: đối chứng không cần proxy

AOP là cách Spring chủ động gọi Jakarta `ExecutableValidator`. Ta có thể gọi validator **trực tiếp** để kiểm tra method parameters/return values, kể cả với object tạo bằng `new`, nếu có `jakarta.validation.Validator` được cấu hình.

### 7.1. Cách API hoạt động

~~~java
ExecutableValidator executable =
        validator.forExecutables();

Set<ConstraintViolation<StockService>> parameterErrors =
        executable.validateParameters(
                plainTarget,
                method,
                new Object[]{"CANARY_BAD_SKU", 0});

Set<ConstraintViolation<StockService>> returnErrors =
        executable.validateReturnValue(
                plainTarget,
                returnMethod,
                "");
~~~

Đây là snippet trong test method, cần imports và các biến từ `ExecutableValidatorTest`. Không phải lời gọi qua proxy. Vì vậy:
- `ExecutableValidator` có thể phát hiện constraints trên POJO thuần.
- Nó **không tự ngăn method body chạy** nếu caller không chủ động dừng trước khi gọi.
- Caller tự quyết định ném exception hoặc xử lý violations.
- Spring AOP tự động hóa phần kiểm trước/sau và tạo exception theo cấu hình.

### 7.2. `ExecutableValidatorTest.java`

~~~java
// src/test/java/com/example/methodaop/ExecutableValidatorTest.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ElementKind;
import jakarta.validation.Validator;
import jakarta.validation.executable.ExecutableValidator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;
import java.util.Set;
import java.util.stream.StreamSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ExecutableValidatorTest {

    @Autowired
    Validator validator;

    @Test
    void directExecutableValidatorFindsParameterViolations()
            throws Exception {

        StockService target = new StockService();
        Method method = StockService.class.getMethod(
                "allocate", String.class, int.class);

        ExecutableValidator executable =
                validator.forExecutables();
        Set<ConstraintViolation<StockService>> errors =
                executable.validateParameters(
                        target, method,
                        new Object[]{"CANARY_INVALID_SKU", 0});

        assertTrue(errors.size() >= 2);
        assertTrue(errors.stream().anyMatch(v ->
                StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false)
                        .anyMatch(n -> n.getKind()
                                == ElementKind.PARAMETER)));

        // Chỉ validateParameters không gọi method body.
        assertEquals(0, target.executionCount());
    }

    @Test
    void directExecutableValidatorChecksReturnValue()
            throws Exception {

        StockService target = new StockService();
        Method method = StockService.class.getMethod(
                "brokenReference");

        Set<ConstraintViolation<StockService>> errors =
                validator.forExecutables().validateReturnValue(
                        target, method, "");

        assertFalse(errors.isEmpty());
        assertTrue(errors.stream().anyMatch(v ->
                StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false)
                        .anyMatch(n -> n.getKind()
                                == ElementKind.RETURN_VALUE)));
    }
}
~~~

**2 JUnit methods**. `validateParameters` nhận target object, `Method` và mảng arguments theo đúng thứ tự reflection. `validateReturnValue` nhận target, method và return value thực tế. Với constructors, Jakarta có các API `validateConstructorParameters`/`validateConstructorReturnValue` riêng, không cần lôi vào bài này.

Không gọi `getInvalidValue()` để log. Trong tests có thể kiểm tra constraint annotation types, path node kinds hoặc số lượng tối thiểu; **không public hóa `ConstraintViolation` object**.

## 8. HTTP integration: quan sát status mà không lộ thông tin nội bộ

### 8.1. `StockLabHttpTest.java`

~~~java
// src/test/java/com/example/methodaop/StockLabHttpTest.java
package com.example.methodaop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StockLabHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validInputCrossesProxyAndProducesReceipt()
            throws Exception {

        mvc.perform(get("/lab/proxy/allocate")
                    .param("sku", "PEN")
                    .param("units", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.receipt")
                        .value("PEN:2"));
    }

    @Test
    void invalidUserInputMapsToSafe400AtSpecificBoundary()
            throws Exception {

        mvc.perform(get("/lab/proxy/allocate")
                    .param("sku", "CANARY_SECRET_SKU")
                    .param("units", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ALLOCATION_INPUT"))
                .andExpect(content().string(not(
                        containsString("CANARY_SECRET_SKU"))))
                .andExpect(content().string(not(
                        containsString("ConstraintViolationException"))))
                .andExpect(content().string(not(
                        containsString("allocate.sku"))));
    }

    @Test
    void brokenServiceReturnMapsToSafe500()
            throws Exception {

        mvc.perform(get("/lab/proxy/broken-return"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_METHOD_CONTRACT_ERROR"))
                .andExpect(content().string(not(
                        containsString("brokenReference"))))
                .andExpect(content().string(not(
                        containsString("ConstraintViolationException"))));
    }

    @Test
    void wrongQueryTypeNeverEchoesRawValue()
            throws Exception {

        mvc.perform(get("/lab/proxy/allocate")
                    .param("sku", "PEN")
                    .param("units", "CANARY_NOT_AN_INT"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_QUERY_TYPE"))
                .andExpect(content().string(not(
                        containsString("CANARY_NOT_AN_INT"))));
    }
}
~~~

**4 JUnit methods**. Chúng kiểm tra ba đường riêng:
- Query hợp lệ → Spring argument conversion thành công → service proxy → 200.
- Query có số hợp lệ nhưng vi phạm `@Min` hoặc SKU sai `@Pattern` → service AOP từ chối và endpoint có mapping input 400 an toàn.
- Query parse sai kiểu `int` → lỗi ở MVC resolver, chưa tới service, xử lý `MethodArgumentTypeMismatchException`.
- Service trả return value sai constraint → 500 tối giản, không lộ nội bộ.

Test không kiểm tra đầy đủ production authentication, transaction hay database rollback; đó là các chủ đề khác.

### 8.2. Đếm số test

| Test class | Methods | Kỳ vọng |
| --- | ---: | --- |
| `StockServiceProxyTest` | 11 | Proxy, parameter, return, self-invocation, cascade |
| `ExecutableValidatorTest` | 2 | Validator trực tiếp |
| `StockLabHttpTest` | 4 | HTTP + trust boundary |
| **Tổng** | **17** | **17 lượt JUnit test dự kiến** |

Không có parameterized tests trong project này, nên method count bằng invocation count. Nếu thêm test parameterized, phải tính theo số invocations, không chỉ đếm annotations.

### 8.3. Lệnh chạy

~~~bash
mvn test
~~~

Chỉ chạy service AOP:

~~~bash
mvn -Dtest=StockServiceProxyTest test
~~~

Chỉ chạy executable validation:

~~~bash
mvn -Dtest=ExecutableValidatorTest test
~~~

Chỉ chạy MockMvc:

~~~bash
mvn -Dtest=StockLabHttpTest test
~~~

**Kết quả dự kiến:** 17 tests PASS với files và dependency đúng như bài, trong môi trường Spring Boot 3.5.7/Java 17. Đây là phân tích tĩnh, **không phải kết quả thực thi Maven**. Khi chạy thật, xác nhận số tests/failures trong Surefire XML và xem logs của Spring Boot nếu context không tạo proxy như mong đợi.

Nếu `isAopProxy(stock)` trả false, đừng vội bỏ assertion. Kiểm tra ``spring-boot-starter-validation`, `@Service`, `@Validated` cấp class, bean được inject từ context, Bean Validation provider và method-validation postprocessor. Nếu context dùng `spring.aop.proxy-target-class` hoặc custom proxy factory, proxy class/type có thể thay đổi nhưng `AopUtils.isAopProxy` vẫn là kiểm tra phù hợp.

## 9. Curl: chạy thử service validation từ bên ngoài

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

### 9.1. Input hợp lệ

~~~bash
curl -i "http://localhost:8080/lab/proxy/allocate?sku=PEN&units=2"
~~~

Response kỳ vọng:

~~~json
{"receipt":"PEN:2"}
~~~

### 9.2. SKU/số lượng không hợp lệ nhưng parse được

~~~bash
curl -i "http://localhost:8080/lab/proxy/allocate?sku=CANARY_SECRET_SKU&units=0"
~~~

Request đến service proxy. SKU vi phạm `@Pattern`, `units=0` vi phạm `@Min(1)`. Controller chỉ trả:

~~~json
{"code":"INVALID_ALLOCATION_INPUT"}
~~~

với HTTP 400. Nó không đưa vào response mảng `ConstraintViolation` hay raw canary string.

### 9.3. Query sai kiểu — chưa vào service

~~~bash
curl -i "http://localhost:8080/lab/proxy/allocate?sku=PEN&units=ABC"
~~~

Spring MVC không chuyển được `ABC` sang `int`, nên `SafeMethodErrorAdvice` trả HTTP 400:

~~~json
{"code":"INVALID_QUERY_TYPE"}
~~~

Đây **không phải** lỗi `@Min` trong AOP; nó nằm ở argument resolution/type conversion của MVC.

### 9.4. Return value không hợp lệ

~~~bash
curl -i "http://localhost:8080/lab/proxy/broken-return"
~~~

Method `brokenReference()` của service trả chuỗi rỗng, bị interceptor phát hiện **sau khi method chạy**. Global advice trả 500:

~~~json
{"code":"INTERNAL_METHOD_CONTRACT_ERROR"}
~~~

Không biến thành 400, không in Java method name hoặc nội dung exception cho client.

Lệnh shell dùng `curl` thông thường. Những URL query có dấu cách hoặc ký tự đặc biệt nên dùng `--get --data-urlencode`; ở production **không đặt credentials/tokens trong URL**, vì access logs và proxies có thể ghi query string.

## 10. Thực nghiệm AOP proxy: JDK versus CGLIB

Spring AOP dùng proxy, nhưng có hai cách chủ yếu:

| Đặc điểm | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| Cơ chế | Triển khai interfaces | Tạo subclass của target class |
| Phù hợp | Bean có interface, caller dùng interface | Bean class không interface hoặc force class proxy |
| Method có thể advice | Chủ yếu methods được expose qua interface | Methods có thể override |
| `final class` | Interface proxy có thể khả thi tùy thiết kế | Không thể subclass final class |
| `final method` | Không dựa vào subclass override | Không thể advice bằng subclass override |
| `private method` | Không thể gọi qua public interface proxy | Không thể override/advice |
| Self-invocation qua `this` | Bypass | Bypass |
| Test ổn định | `AopUtils.isAopProxy` | `AopUtils.isAopProxy` |

Với `StockService` của project không implements interface, Spring có thể dùng CGLIB. Nếu chuyển sang:

~~~java
public interface StockOperations {
    String allocate(String sku, int units);
}
~~~

và cho `StockService implements StockOperations`, JDK proxy có thể chỉ expose interface type, khiến việc inject concrete class không còn phù hợp nếu config dùng interface-based proxy. Khi đổi kiểu proxy cần test bean wiring và method annotations. Không ép `@Validated`/constraints trên interface và implementation theo cách vi phạm **Jakarta Bean Validation inheritance rules**: overriding method không được tùy ý thêm parameter constraints làm mạnh preconditions.

**Tránh dùng `final` cho Spring service class cần class-based proxy.** Java records mặc định final, vì vậy record phù hợp làm immutable input/output DTO nhưng không phải class thuận tiện để Spring tạo CGLIB method-validation proxy. Các methods private/final tự nhiên không nên là nơi duy nhất giữ security invariants nếu bạn chỉ trông chờ proxy.

### 10.1. Các phép kiểm proxy trong test

~~~java
// Snippet trong test có stock được inject:
assertTrue(AopUtils.isAopProxy(stock));

Class<?> visibleClass = stock.getClass();
System.out.println(visibleClass.getName());
~~~

Không hard-code chuỗi tên lớp proxy trong assertion; tên generator thay đổi theo version và config. Nếu muốn xem target type, Spring có `AopUtils.getTargetClass(stock)` nhưng cũng không nên serialize thông tin class đó ra public API.

Đừng sử dụng `stock.getClass()==StockService.class` như điều kiện thành công: khi proxied, `getClass()` có thể là subclass hoặc JDK proxy type.

## 11. Self-invocation và các điểm mù khác

### 11.1. Self-invocation qua `this`

~~~text
External caller
   |
   v
Spring proxy
   |
   v
Target.callThroughThis()
   |
   +--> this.allocate("",0)   <-- không quay lại proxy
             |
             v
          body chạy
~~~

Một test chỉ gọi `stock.allocate("",0)` từ bên ngoài sẽ pass và khiến reviewer tin service luôn được bảo vệ. Nhưng một refactor sau đó đưa lời gọi vào cùng class bằng `this.allocate` sẽ bỏ qua advice. Vì thế test `selfInvocationSkipsMethodValidationAdvice` có mục đích cảnh báo.

### 11.2. Object tạo bằng `new`

~~~java
StockService plain = new StockService();
String value = plain.allocate("", 0);
~~~

Nếu không tự validate trong method body, lời gọi này trả `":0"` vì không có Spring proxy. Đừng biến cách tạo POJO trực tiếp thành pattern production cho một service đang phụ thuộc AOP method validation. Trong unit tests, muốn kiểm tra behavior của method body thuần thì `new` phù hợp; muốn kiểm tra **method validation** phải dùng Spring context hoặc gọi `ExecutableValidator` tường minh.

### 11.3. `@PostConstruct`/constructor và lifecycle

Advice dựa trên proxy không áp cho mọi hoạt động trong constructor hoặc initialization callbacks. Gọi một method cùng bean từ `@PostConstruct` cũng không phải lời gọi external xuyên proxy theo cách thông thường. Không dùng method-validation AOP như cơ chế kiểm tra tính hợp lệ của chính bean khi khởi tạo; dùng constructor invariants, Bean Validation tường minh hoặc Spring configuration validation thích hợp.

### 11.4. Scheduled, async, transactional methods

`@Scheduled`, `@Async` và `@Transactional` cũng liên quan proxy/lifecycle/context. Một method có thể chạy trên thread khác, dùng proxy khác hoặc có advice order khác. Đừng giả định lỗi return validation luôn xảy ra **trước transaction commit** trong mọi cấu hình.

Trong hệ thống có side effects:
- Parameter validation xảy ra trước target invocation khi qua validation interceptor.
- Return validation xảy ra sau khi target body đã chạy, nhưng thứ tự so với transaction/retry advisors có thể đổi thời điểm rollback/commit.
- Nếu return violation cần rollback, hãy viết integration test với transaction manager/database thực tế, không chỉ assert exception.
- Với `CompletableFuture`, reactive publishers hoặc suspend functions, semantics của “return value” có thể khác giá trị được emit về sau; cần kiểm tra hỗ trợ của framework và test riêng.

### 11.5. Bean không được proxy

Nếu `@Validated` bị đặt trên object không được đăng ký là bean, hoặc bean nằm ngoài component scan, interceptor không xuất hiện. Các lỗi thường gặp:
- `StockService` được tạo bằng `new` trong controller thay vì inject.
- Tắt/loại `spring-boot-starter-validation` hoặc provider.
- Bean class cuối cùng `final` nhưng cần CGLIB subclass.
- Gọi `private`/`final` method rồi tưởng có advice.
- Lấy target object trực tiếp thay vì proxy từ context.
- Test `@SpringBootTest` nhưng có `@MockBean` hoặc custom test config thay service thật bằng mock; Mockito stub có thể bỏ qua method interceptor.
- `@Validated` bị bỏ khỏi service class trong refactor.
- Một custom BeanPostProcessor thay đổi proxy chain/order.

## 12. Validation groups và kế thừa method constraints

### 12.1. Groups trên `@Validated`

Jakarta constraints có `groups`:

~~~java
public interface StrictChecks {}

@Min(value = 10, groups = StrictChecks.class)
private int minimum;
~~~

Đây là **snippet**, không phải class trong demo. Spring `@Validated(StrictChecks.class)` có thể chọn validation group cho bean/method. Khi chỉ chọn `StrictChecks`, constraints thuộc `Default` không nhất thiết cũng chạy; nếu muốn cả hai, cần policy groups/group sequence phù hợp.

Ở service production:
- Chỉ dùng groups khi có use case thực, ví dụ create/update hoặc tier-specific checks.
- Viết tests xác nhận đúng group được áp qua proxy.
- Không dùng validation group làm authorization; user không có quyền không thể chỉ đổi group để được phép gán dữ liệu bảo vệ.

### 12.2. Parameter constraints trên methods kế thừa

Jakarta Bean Validation có quy tắc **không làm mạnh preconditions** khi override/implement methods: không thể tùy ý thêm parameter constraint vào implementation nếu interface/base method chưa có cùng contract theo các quy tắc cho phép. Return constraints có quy tắc hậu điều kiện khác; có thể có những trường hợp được tăng cường hậu điều kiện mà không vi phạm.

Ví dụ cần review cẩn thận:

~~~java
interface AllocationApi {
    String allocate(String sku, int units);
}

class RestrictedAllocation implements AllocationApi {
    @Override
    public String allocate(@NotBlank String sku, int units) {
        return sku;
    }
}
~~~

Đây là **anti-pattern minh họa**, không thuộc runnable project. Hibernate Validator có thể ném `ConstraintDeclarationException` vì implementation thêm constraint parameter vào method kế thừa theo cách không hợp lệ. Hãy đặt executable constraints thống nhất theo interface/base contract và test khi chuyển JDK/CGLIB proxy.

## 13. Bảo mật response, logging và vấn đề lỗi dữ liệu

### 13.1. Không xuất trực tiếp `ConstraintViolationException`

Một handler không an toàn:

~~~java
// Không dùng cho REST response:
@ExceptionHandler(ConstraintViolationException.class)
public Object unsafe(ConstraintViolationException ex) {
    return ex.getConstraintViolations();
}
~~~

`ConstraintViolation#getInvalidValue()` có thể chứa password, access token, email hoặc nested domain object. `getPropertyPath()` có thể chứa tên method/class nội bộ. `getMessage()` có thể bị custom interpolator/validator ghép raw input. Một generic serialization có thể lộ nhiều metadata hơn dự định.

Handler an toàn của demo chỉ trả `code` cố định; hệ thống lớn có thể dùng `ProblemDetail` với public code/path/message đã được **allowlist** và lokalization từ `MessageSource`.

### 13.2. Không tự động log raw exception message

~~~java
// Không nên với input nhạy cảm:
logger.warn("Method validation failed: {}", ex.getMessage());
~~~

Trong một số provider, message của `ConstraintViolationException` chứa tên method/parameter và message interpolated; custom message có thể mang input. Logs/APM có vòng đời rộng hơn response HTTP và dễ chia sẻ. Hãy log metadata có giới hạn: service name, public error code, server-generated correlation ID, method category sau khi kiểm soát, count of violations — không log raw rejected values hoặc credentials.

### 13.3. Return violation thường là lỗi nội bộ

Nếu service hứa trả một reference không blank mà lại trả chuỗi rỗng, client không có đủ thông tin để sửa lỗi. HTTP 500 an toàn và monitoring nội bộ thích hợp hơn HTTP 400. Nếu lỗi xảy ra sau side effects, cần xem transaction/retry policy để tránh ghi dữ liệu một phần.

### 13.4. Phân biệt input validation và permission checks

`@NotBlank`, `@Pattern`, `@Min` xác nhận cú pháp/giới hạn; chúng không chứng minh caller có quyền xuất kho, sửa tồn kho hay truy cập tenant. Authorization phải được áp riêng ở security/service boundary. Những values phù hợp constraints vẫn có thể là hành động bị cấm.

## 14. Đối chiếu AOP service với built-in MVC method validation

| Tiêu chí | Service method validation qua AOP | MVC handler method validation 6.1+ |
| --- | --- | --- |
| Điểm kích hoạt | Bean service `@Validated`, proxy | Controller handler có direct parameter/return constraints |
| Cơ chế | `MethodValidationPostProcessor` + advice | MVC handler validation infrastructure |
| Tham số được kiểm tra | Jakarta executable constraints trên service parameters | MVC handler parameters sau argument resolution |
| Return được kiểm tra | Jakarta executable return constraints qua proxy | MVC handler return constraints |
| Exception mặc định | `ConstraintViolationException` | `HandlerMethodValidationException` |
| Alternative | `MethodValidationException` nếu adapt=true | Xử lý `HandlerMethodValidationException` |
| Self-invocation | Bypass proxy advice | Không cùng khái niệm gọi target qua service proxy |
| Object `@Valid` | Cascade khi method validation chạy | Có thể có object validation riêng `MethodArgumentNotValidException` |
| Use case | Service được gọi từ nhiều loại entrypoint | HTTP request/response boundary |
| Handler | Ánh xạ lỗi theo trust boundary, không tất cả 400 | 400 cho input; 500 cho return violation theo MVC semantics |

**Không gộp hai exception vào một giả định duy nhất.** Ví dụ service có `@Validated` cấp class sẽ được kiểm bằng AOP; controller không nhất thiết cần `@Validated` cấp class. Với MVC 6.1+, trực tiếp `@Min` trên `@RequestParam` có thể tạo `HandlerMethodValidationException`, không phải `ConstraintViolationException`, trừ khi bạn chủ động đưa controller sang AOP path.

## 15. Hỏi đáp khi test thất bại

### 15.1. Vì sao gọi `allocate("",0)` không ném lỗi?

Kiểm tra theo thứ tự:
1. Có gọi trên bean Spring injected hay `new`?
2. `StockService` có `@Service` và nằm trong component scan không?
3. `@Validated` có ở **class** không?
4. `spring-boot-starter-validation` có Bean Validation provider không?
5. `MethodValidationPostProcessor` có được tạo không?
6. `AopUtils.isAopProxy(stock)` có true không?
7. Lời gọi có đi qua injected proxy hay `this`?
8. Method có public và có thể được proxy/advised không?
9. Có config adapt violations đổi exception type không?
10. Có test replacement/mocking bean làm mất advice không?

### 15.2. Vì sao nhận `MethodValidationException` thay vì `ConstraintViolationException`?

Hệ thống có thể cấu hình `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`. Điều đó biến output sang Spring `MethodValidationResult` và exception phù hợp, thay đổi APIs/handling. Bài demo không bật option. Rà bean config và giữ tests đồng bộ với policy.

### 15.3. Vì sao lỗi return-value không phải 400?

Giá trị trả về do server tạo là một phần lời hứa của service. Nếu không đạt constraint, client thường không thể chỉnh input để giải quyết. Tách status 500 và giới hạn chi tiết public, đồng thời log/alert an toàn cho team vận hành.

### 15.4. Vì sao test `getPropertyPath().toString()` không giống tutorial?

Parameter name discovery có thể cho `arg0`/`arg1` hoặc names từ `-parameters`; provider có thể định dạng path khác. Dùng `ElementKind.PARAMETER`/`RETURN_VALUE` và constraint annotation types để test property semantics; tránh hard-code toàn bộ path string khi không là API contract.

### 15.5. Vì sao test direct `new StockService()` không ném exception?

Bởi nó không qua Spring-managed proxy, không phải vì Jakarta constraints “không hoạt động”. `ExecutableValidatorTest` chứng minh provider vẫn có thể tìm các violations trên POJO thuần khi bạn **gọi validator tường minh**.

### 15.6. Vì sao service được proxy nhưng self-invocation vẫn lọt?

Spring AOP proxy intercept **external method calls đi vào proxy**, không tự intercept mọi lời gọi từ `this` bên trong target. Refactor logic sang bean khác hoặc kiểm tra invariants trực tiếp trong domain method, không tắt test cảnh báo.

### 15.7. Vì sao `@Valid` trên DTO không kiểm null object?

`@Valid` là cascade marker; null reference thường không cascade sang properties. Thêm `@NotNull` trên parameter nếu muốn cấm null. Với primitive `int`, object null không áp dụng; dùng `@Min` cho giá trị số.

### 15.8. Vì sao test return validation có thể không rollback database?

Thứ tự validation advice với transaction advisor có thể khác. Return violation xảy ra sau method body, nhưng commit/rollback phụ thuộc interceptor nesting và transaction manager. Viết integration test thật với database, không chỉ assert `ConstraintViolationException`.

### 15.9. Vì sao CGLIB/JDK khác behavior sau refactor?

Thêm interface hoặc đổi `spring.aop.proxy-target-class` có thể đổi kiểu proxy. JDK proxy chỉ expose method qua interfaces, nên caller injection và annotation location phải theo proxy method contract. Đừng ép concrete implementation injection khi ứng dụng đã chọn interface-based proxy.

## 16. Bài tập tăng độ khó

1. Bỏ `@Validated` khỏi `StockService`, chạy `StockServiceProxyTest` và giải thích vì sao test proxy/violations fail.
2. Thay `@Min(1)` bằng `@Min(5)`, kiểm tra `allocate("PEN",2)` nay fail trước increment.
3. Thêm `@NotNull` lên return của một method trả null, kiểm tra `ElementKind.RETURN_VALUE`.
4. Thêm `@Valid` vào `AllocationCommand` mới có nested object, kiểm tra property paths và không cần controller.
5. Đổi `callThroughThis()` thành lời gọi qua bean collaborator, xác minh invalid input được chặn; không dùng `AopContext` nếu không cần.
6. Viết direct `ExecutableValidator.validateParameters` cho cùng input mà proxy từ chối; so sánh số violations và trạng thái method body.
7. Thay exception policy sang `setAdaptConstraintViolations(true)`, cập nhật tests cho `MethodValidationException` và `ParameterValidationResult`.
8. Viết negative test với method `final` trên class-based proxy, quan sát advice có/không hoạt động và loại bỏ anti-pattern.
9. Định nghĩa interface có executable constraints, class implement, so sánh JDK/CGLIB proxy khi dùng interface injection.
10. Thêm transaction thật với persistence, cố tình tạo return violation rồi kiểm tra commit/rollback theo advisor ordering.
11. Gửi số lượng `units=ABC` qua HTTP và đối chiếu với `units=0`: lỗi MVC conversion khác lỗi AOP method validation.
12. Thêm ConstraintViolation custom message chứa chuỗi canary, xác nhận response và logs không lộ canary.
13. Thêm nhóm `StrictChecks`, áp `@Validated(StrictChecks.class)` và kiểm tra nhóm thực sự chạy.
14. Tạo scheduled job gọi bean proxy và so sánh với lời gọi nội bộ trong chính bean; không assume scheduler luôn bypass/đi qua mà phải quan sát wiring.
15. Chuyển REST layer sang WebFlux; giữ service AOP, nhưng viết WebTestClient và tránh coi reactive return publisher như giá trị đã emit.

## 17. Checklist khi đưa method validation vào service thật

- [ ] Service là Spring-managed bean, không `new` ở production wiring.
- [ ] Có `@Validated` ở type theo chính sách Spring AOP method validation.
- [ ] Jakarta Bean Validation provider có mặt và `MethodValidationPostProcessor` được auto-config hoặc khai báo đúng một cách có chủ đích.
- [ ] Test `AopUtils.isAopProxy` và một invalid invocation xuyên proxy.
- [ ] Parameter constraints bảo vệ input; return constraints bảo vệ output contract.
- [ ] `@NotNull` kết hợp `@Valid` khi null object phải bị từ chối.
- [ ] Test `ConstraintViolationException` mặc định hoặc `MethodValidationException` nếu adapt=true.
- [ ] Không assert exact raw provider messages/paths khi không thuộc contract.
- [ ] Kiểm tra `ElementKind.PARAMETER`/`RETURN_VALUE` thay vì đoán dựa vào string.
- [ ] Có negative test cho `new`/self-invocation để không nhầm coverage.
- [ ] Tránh `private`/`final` methods là nơi duy nhất trông chờ proxy advice.
- [ ] Cẩn trọng với interface constraints và inheritance rules; đổi JDK/CGLIB cần regression tests.
- [ ] Không biến mọi service `ConstraintViolationException` thành HTTP 400.
- [ ] HTTP 500 cho lỗi return/internal contract, response không tiết lộ giá trị hay method details.
- [ ] Không serialize raw `ConstraintViolation`/`getInvalidValue()`/`ex.getMessage()` hoặc log credentials.
- [ ] Validation khác authorization; quyền thao tác phải có kiểm tra riêng.
- [ ] Với transactions, async, caching, retry, kiểm thử advice ordering và side effects.
- [ ] Nâng Spring/Boot/validator phải chạy lại JUnit và HTTP integration regression suite.

## 18. Tóm tắt trực quan

~~~text
CALLER ---> AOP PROXY ---> validateParameters()
                               |
                               +-- FAIL -> ConstraintViolationException
                               |
                               v
                          TARGET METHOD
                               |
                               v
                         validateReturnValue()
                               |
                               +-- FAIL -> ConstraintViolationException
                               |
                               v
                        VALID RETURN TO CALLER

this.method(...) / new MyService()
             -> bypass Spring proxy advice
             -> no automatic AOP method validation

Validator.forExecutables()
             -> explicit validation on any suitable target
             -> separate from proxy interception
~~~

**Thông điệp cuối:** `@Validated` không phải phép màu kiểm mọi lời gọi Java. Nó cho phép Spring tạo advice quanh **những lần gọi đi qua proxy**. Trước target method, validation kiểm parameter contract; sau target method, nó kiểm return contract. Muốn tin vào cơ chế này, hãy test chính proxy, test self-invocation và test lỗi 400/500 ở đúng biên API, thay vì chỉ nhìn thấy annotations trong source code.

## 19. Tài liệu tham khảo

- Spring Framework 6.2 — Java Bean Validation / Spring-driven Method Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — Proxying Mechanisms and Self Invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — AOP Proxies: https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html
- Spring Framework 6.2 — MVC Validation and class-level @Validated distinction: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MethodValidationPostProcessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework 6.2 — MethodValidationInterceptor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html
- Spring Framework 6.2 — MethodValidationException Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/MethodValidationException.html
- Spring Framework 6.2 — ParameterValidationResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Boot 3.5 — Validation and method validation auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Jakarta Bean Validation 3.1 — Executable Validation, Path, inheritance and groups: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — ExecutableValidator API: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/executable/executablevalidator
- OWASP Developer Guide — Handle all Errors and Exceptions: https://devguide.owasp.org/en/04-design/02-web-app-checklist/10-handle-errors-exceptions/
