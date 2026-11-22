# Self-invocation làm bỏ qua method validation trong Spring

## 1. Bối cảnh: cùng một constraint, kết quả khác nhau tùy đường gọi

Một lỗi rất khó chẩn đoán trong Spring là: phương thức có `@NotBlank`, `@NotNull` hay `@Min` hoạt động khi được gọi từ bean khác, nhưng **không được kiểm tra** khi một method trong chính class gọi nó bằng `this` hoặc gọi trực tiếp không có chữ `this`.

Ví dụ:

~~~java
@Service
@Validated
public class RegistrationService {

    public String register(String code) {
        return checkCode(code);
    }

    @NotBlank
    public String checkCode(@NotBlank String code) {
        return code;
    }
}
~~~

Đoạn trên là **snippet**, imports và dự án đầy đủ được trình bày ở phần 9. Khi một Spring bean khác gọi **proxy** của `RegistrationService.checkCode("")`, Method Validation có thể ném `ConstraintViolationException` vì input rỗng. Nhưng `register("")` gọi nội bộ `checkCode("")` trên **cùng target object**, không qua proxy lần thứ hai, nên constraints của `checkCode` có thể **không được AOP đánh giá**.

Đây là vấn đề **self-invocation bypass**. Không nên giải thích rằng “`@NotBlank` chỉ hoạt động ở controller” hoặc “Spring không kiểm tra String rỗng”; bản chất là **interceptor không có cơ hội chặn lời gọi nội bộ**.

**Phạm vi bài:** Spring-driven method validation trên **service beans** thông qua AOP proxy, cách tái hiện bằng Java 17+/Spring Boot 3.x, cách phân biệt với Spring MVC 6.1+ built-in method validation, phương án sửa, test chứng minh và các giới hạn thực tế.

### Dấu hiệu quan sát

| Đường gọi | Điều xảy ra khi có proxy đúng cấu hình |
| --- | --- |
| `otherBean -> proxy.checkCode("")` | Constraint trên input của `checkCode` được kiểm tra; có exception. |
| `otherBean -> proxy.register("") -> this.checkCode("")` | Chỉ advice của `register` (nếu có) chạy; advice của `checkCode` bị bypass. |
| `new RegistrationService().checkCode("")` | Java object thuần, không Spring proxy, không AOP validation. |
| `proxy.methodWithInvalidReturn()` | Constraint trên return value có thể được kiểm tra. |
| `proxy.outer() -> this.methodWithInvalidReturn()` | Return-value constraint của inner bị bypass; outer chỉ được kiểm tra theo constraints của chính outer. |

**Phân biệt quan trọng:** `register` không có constraint thì input rỗng có thể đi qua, nhưng nếu `register` **tự** có `@NotBlank` trên parameter, proxy vẫn có thể kiểm tra `register`. Điều đó **không chứng minh** `checkCode` đã được validate. Khi test self-invocation, đừng vô tình đặt cùng constraint ở outer method khiến bài test mất khả năng phát hiện bypass.

## 2. Cơ chế Spring AOP proxy

Spring AOP thường dùng **JDK dynamic proxy** hoặc **class-based CGLIB proxy**. Proxy là một object khác với target bean theo nghĩa interception: lời gọi từ bên ngoài đi vào proxy, proxy chạy các advice cần thiết, rồi mới chuyển tới implementation.

~~~text
Bên ngoài Spring bean
        |
        v
    AOP PROXY
        |
        +-- MethodValidationInterceptor
        |     |
        |     +-- Kiểm tra method parameters
        |     +-- Nếu sai: validation exception
        |
        v
 TARGET BEAN.method(...)
        |
        +-- chạy nghiệp vụ
        |
        v
    AOP PROXY
        |
        +-- Kiểm tra return value
        |     +-- Nếu sai: validation exception
        |
        v
 Caller nhận kết quả
~~~

Với:

~~~java
@NotBlank
public String normalize(@NotBlank String value) {
    return value.trim();
}
~~~

khi phương thức được gọi qua proxy, interceptor có thể kiểm tra **parameter trước body**, sau đó **return value sau khi body trả bình thường**. Nếu input không đạt, target method thường chưa được thực thi; nếu output không đạt, target method có thể đã thực thi xong và thậm chí có side effect.

### Đường self-invocation

~~~text
Caller
   |
   v
Proxy của RegistrationService
   |
   v
Target.register(...)
   |
   +-- this.checkCode(code)
            |
            v
        Target.checkCode(...)
            |
            +-- KHÔNG đi qua proxy
            +-- MethodValidationInterceptor của checkCode
                không chạy
~~~

Sau khi proxy chuyển control vào `Target.register`, `this` trỏ tới target object. Một lời gọi `this.checkCode(...)` hoặc `checkCode(...)` tiếp tục đi thẳng trong target. Spring docs nêu rõ self-invocation trong proxy-based AOP bỏ qua advice của method được gọi nội bộ.

**Xóa chữ `this` không chữa được lỗi**:

~~~java
public String outer(String code) {
    return checkCode(code); // vẫn implicit this
}
~~~

Không có một quy tắc Java tự động “quay lại AOP proxy” cho call này. Muốn interceptor chạy cần **đường gọi đi qua proxy**, hoặc kiểm tra invariant bằng cơ chế tường minh khác.

## 3. Điều kiện để service method validation hoạt động

Không phải cứ nhìn thấy annotation là Spring tự kiểm tra mọi method call. Với **Spring-driven service method validation** theo cấu hình thông dụng, cần:

1. **Bean do Spring quản lý**, ví dụ `@Service` và được component scan. `new Service()` không tạo proxy.
2. **Jakarta Bean Validation provider** như Hibernate Validator, thường qua `spring-boot-starter-validation` trong Spring Boot.
3. **Method validation infrastructure** như `MethodValidationPostProcessor` cùng Spring AOP. Boot có thể auto-configure khi các điều kiện classpath/context phù hợp.
4. **`org.springframework.validation.annotation.Validated` trên target service type** để Spring-driven method validation chọn bean.
5. **Constraint đúng vị trí** — `@NotBlank` trên method parameter hoặc method return; không chỉ là annotation trên một DTO không được cascade.
6. **Lời gọi bên ngoài đi qua proxy**, không phải self-call trên `this`.
7. **Method proxy được**: class/method visibility, JDK interface coverage, CGLIB final/private limitations.
8. **Validation groups đúng** và interceptor/exception adapter cấu hình phù hợp.

Trong Spring Framework thuần, tài liệu chính thức giới thiệu:

~~~java
@Configuration
public class ValidationConfig {
    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
~~~

Đây là **snippet** cần imports Spring `@Configuration`, `@Bean` và `MethodValidationPostProcessor`. Với Spring Boot đã tự cấu hình processor, **không đăng ký thêm một processor thứ hai** mà không kiểm tra context; nhiều auto-proxy mechanisms có thể làm test và hành vi phức tạp.

### `@Validated` khác `@Valid`

| Annotation/API | Vai trò |
| --- | --- |
| Spring `@Validated` trên service class | Đánh dấu target cho AOP-driven method validation; có thể chỉ định validation groups. |
| Jakarta `@Valid` trên DTO/parameter | Cascade validation trên object được annotate; **không tự nó là constraint**. |
| Jakarta `@NotBlank` trên String parameter/return | Constraint thật, kiểm tra null/empty/whitespace. |
| Jakarta `@NotNull` trên reference parameter/return | Constraint thật, bắt giá trị khác null. |
| Jakarta `@Min` trên numeric parameter | Constraint thật, giới hạn số nhỏ nhất. |
| Jakarta `ExecutableValidator` | API kiểm tra method parameters/return **tường minh**, không cần AOP proxy nếu được gọi đúng. |

Ví dụ:

~~~java
@Service
@Validated
class OrderService {
    @NotNull
    public Receipt create(
            @NotNull @Valid OrderInput input) {
        // implementation tương ứng
        return null; // chỉ là anti-pattern minh họa
    }
}
~~~

Đoạn này là **anti-pattern snippet** chứ không phải chương trình cần chạy: return null cố ý vi phạm. `@NotNull` ở trước return type là constraint của **giá trị trả về**; `@NotNull @Valid` trên input là kiểm tra input reference + cascade. Trong production không trả null trái hợp đồng.

### Validation groups không phải self-invocation

Khi dùng `@Validated(RegistrationGroup.class)`, một số constraints có thể chỉ thuộc group khác Default. Nếu test sai group, không thấy exception dù lời gọi đã đi qua proxy. Để cô lập self-invocation, demo này chỉ dùng `@NotBlank` trong **Default group**, sau đó mới kiểm tra groups khi chẩn đoán dự án thật.

## 4. Vì sao private/final/proxy type cũng khiến annotation không được chặn?

### Class-based proxy (CGLIB)

CGLIB tạo subclass của target. Nó **không thể override**:
- `final` methods,
- `private` methods,
- methods không visible phù hợp (ví dụ một số package-private members từ package khác).

`final` class không thể được subclass bằng class-based proxy. Không nên đặt một constraint quan trọng chỉ trên private/final helper rồi dựa vào Spring AOP để chạy nó.

Ví dụ dễ nhầm:

~~~java
@Service
@Validated
class ExampleService {

    public String outer(String input) {
        return privateCheck(input);
    }

    @NotBlank
    private String privateCheck(@NotBlank String input) {
        return input;
    }
}
~~~

Đây là **snippet** chỉ minh họa hạn chế. `privateCheck` không phải interceptable method theo Spring proxy-based AOP. Ngay cả khi `outer` gọi qua proxy, `privateCheck` cũng là internal call.

### JDK dynamic proxy

JDK proxies expose các methods trong interfaces được proxy. Nếu method chỉ tồn tại trên implementation nhưng không có trong interface, caller inject interface không thể gọi nó. Đừng sửa lỗi bằng cách chuyển `spring.aop.proxy-target-class=true` và nghĩ self-invocation được giải quyết: cả JDK proxy **lẫn CGLIB đều gặp bypass khi method trên target tự gọi nhau**.

### Giai đoạn khởi tạo bean

Constructor và lời gọi từ `@PostConstruct` không đi qua một fully initialized external proxy như caller bình thường. Không dựa vào self-calls trong giai đoạn khởi tạo để kích hoạt AOP method validation. Nếu cần kiểm tra cấu hình lúc startup, dùng một cơ chế explicit validation hoặc lifecycle component phù hợp sau khi context sẵn sàng.

## 5. Hai dạng lỗi: input bị bỏ kiểm tra và return value bị bỏ kiểm tra

### 5.1. Bỏ kiểm tra tham số

~~~java
public String viaThis(String text) {
    return this.checked(text);
}

@NotBlank
public String checked(@NotBlank String text) {
    return text;
}
~~~

Lời gọi bên ngoài `proxy.checked("")` có thể ném `ConstraintViolationException` trước khi body `checked` chạy. Lời gọi `proxy.viaThis("")` thì method `viaThis` không có constraint, inner không đi qua proxy, nên có thể **trả `""` không báo lỗi**.

Điều này nguy hiểm khi input đi đến service qua **message queue**, **scheduler**, **batch job**, **event consumer** hoặc internal service, không qua một HTTP controller có `@Valid`. Chỉ có tests từ controller không bảo đảm mọi caller khác được bảo vệ.

### 5.2. Bỏ kiểm tra giá trị trả về

~~~java
public String viaThisReturn() {
    return invalidReturn();
}

@NotBlank
public String invalidReturn() {
    return "";
}
~~~

`proxy.invalidReturn()` qua external proxy có thể bị reject **sau khi method trả**. Nhưng `proxy.viaThisReturn()` gọi inner trực tiếp nên không kiểm tra return constraint của `invalidReturn` và có thể trả chuỗi rỗng.

**Hệ quả khi có side effects:** một method đã ghi database/sent event trước khi return violation bị phát hiện không có nghĩa transaction chắc chắn rollback. Nó có thể đã commit trước đó. Khi xử lý lỗi 5xx, thiết kế transaction, idempotency và reconciliation phải độc lập với việc có annotation method validation.

### 5.3. Không nhầm annotation với hợp đồng của outer method

Nếu `outer` tự có `@NotBlank` return constraint, proxy có thể kiểm tra **kết quả của outer**, bắt chuỗi rỗng sau self-call. Nhưng đó là bảo vệ **của outer**, không sửa được việc inner method không có interceptor khi gọi nội bộ. Nếu inner cần kiểm tra tham số *trước* khi side effects bắt đầu, chỉ thêm return constraint cho outer có thể là quá muộn.

## 6. Phân biệt AOP method validation và Spring MVC built-in method validation

**Spring Framework 6.1+** có built-in method validation cho **MVC controller handler methods**. Spring docs khuyến nghị gỡ class-level `@Validated` khỏi controller khi muốn dùng cơ chế MVC built-in thay vì AOP proxy.

Hai pipeline:

~~~text
Spring MVC HandlerMethodValidator
    -> Handler method parameters / return value
    -> MethodArgumentNotValidException hoặc
       HandlerMethodValidationException tùy signature

Spring-driven service method validation (AOP)
    -> @Validated service proxy
    -> MethodValidationInterceptor
    -> ConstraintViolationException (mặc định) hoặc
       MethodValidationException (khi adapt enabled)
~~~

Trong MVC, input method validation errors thường được map thành **HTTP 400**, return-value method validation errors thành **HTTP 500**. Với service AOP, `ConstraintViolationException` không tự động là lỗi client có status 400: nó có thể đến từ **server-generated return value**.

Ví dụ MVC không cần class-level `@Validated`:

~~~java
@RestController
class SampleController {

    @GetMapping("/pages")
    public String pages(
            @RequestParam @Min(1) int size) {
        return "size=" + size;
    }
}
~~~

Đây là snippet; `size=0` được built-in MVC method validation từ Spring 6.1+ kiểm tra, không chứng minh self-calls trong service được intercept.

Tương tự, `@Valid @RequestBody RequestDto` thường được MVC validate sau deserialization. Nếu JSON invalid đã bị reject tại controller, điều đó **không có nghĩa** một inner service method có `@NotBlank` được kiểm tra qua AOP. Một request hợp lệ có thể che bug self-invocation rất lâu.

**Ranh giới rõ:** bài này chẩn đoán **service AOP proxy self-call**; không khẳng định mọi Spring/Jakarta validation đều bị bypass khi cùng class gọi nhau.

## 7. Cách kiểm tra thực tế: proxy, advice và lời gọi invalid

Một bước chẩn đoán nhanh:

~~~java
boolean proxyPresent = AopUtils.isAopProxy(service);
boolean cglib = AopUtils.isCglibProxy(service);
boolean jdk = AopUtils.isJdkDynamicProxy(service);
~~~

`AopUtils` thuộc `org.springframework.aop.support.AopUtils`. Biến `service` phải là object inject từ Spring context, **không phải `new Service()`**.

Nếu `isAopProxy==false`, kiểm tra method validation infrastructure, `@Validated`, component scan, provider và proxy limitations. Nếu `isAopProxy==true`, điều đó chỉ chứng minh **có AOP proxy**, không chứng minh proxy có đúng **method-validation advice** hoặc self-call quay lại proxy.

Một test tối thiểu cần:
1. Lấy bean từ Spring context.
2. Assert bean có proxy.
3. Gọi `bean.checked("")` trực tiếp qua injected reference.
4. Mong chờ validation exception.
5. Gọi `bean.viaThis("")` với input tương tự.
6. Quan sát self-call không bị chặn.
7. Refactor bằng một bean khác rồi test lại.

Không log nguyên bean hoặc request body để debug. Dữ liệu có thể chứa password/token/PII. Log metadata an toàn như class, method và error category; tránh serialize `ConstraintViolation#getInvalidValue()` hoặc raw parameters.

## 8. Phương án sửa: chọn theo độ rõ và mức phụ thuộc framework

### 8.1. Ưu tiên: tách thành hai Spring beans

Không nên:

~~~java
@Service
@Validated
class UnsafeWorkflow {
    public String process(String value) {
        return validateValue(value);
    }

    public String validateValue(@NotBlank String value) {
        return value;
    }
}
~~~

Nên:

~~~java
@Service
@Validated
class CheckedService {
    public String validateValue(@NotBlank String value) {
        return value;
    }
}

@Service
class Workflow {
    private final CheckedService checkedService;

    Workflow(CheckedService checkedService) {
        this.checkedService = checkedService;
    }

    public String process(String value) {
        return checkedService.validateValue(value);
    }
}
~~~

Đây là snippets kiến trúc; code đầy đủ ở phần 9. `checkedService` là **Spring-injected bean reference**. Khi nó là AOP proxy và method được advise, lời gọi đi qua interceptor. Đây là cách có ưu điểm về testability và separation of concerns, không cần vòng phụ thuộc hoặc `AopContext`.

### 8.2. Self injection

Spring AOP docs có đề cập có thể inject proxy của chính bean và gọi qua reference thay vì `this`. Ví dụ cần dùng thận trọng:

~~~java
@Service
@Validated
public class SelfInjectedService {

    private final ObjectProvider<SelfInjectedService> self;

    public SelfInjectedService(
            ObjectProvider<SelfInjectedService> self) {
        this.self = self;
    }

    public String process(String value) {
        return self.getObject().check(value);
    }

    public String check(@NotBlank String value) {
        return value;
    }
}
~~~

Đây là **snippet** cần imports `org.springframework.beans.factory.ObjectProvider`, `@Service`, `@Validated`, `@NotBlank`. `ObjectProvider` trì hoãn lookup tới lúc gọi; khi có proxy đúng type, `self.getObject()` có thể nhận proxy và không còn self-call trực tiếp.

Nhược điểm: phụ thuộc Spring container, có thể phức tạp khi circular dependencies, proxy type hoặc lifecycle không phù hợp. **Đừng dùng self injection mặc định** khi tách bean đơn giản và rõ ràng hơn.

### 8.3. `AopContext.currentProxy()`

Một số code dùng:

~~~java
((MyService) AopContext.currentProxy())
        .validatedMethod(value);
~~~

Cần `exposeProxy=true` và method đang chạy trong proxy invocation phù hợp. Nếu không có exposed proxy, lời gọi có thể ném exception. Nó coupling domain code với Spring AOP, khó test bằng plain object và dễ phụ thuộc kiểu proxy. **Spring docs xem đây là cách ít được khuyến khích**; tránh dùng chỉ để “làm cho annotation chạy”.

### 8.4. Kiểm tra tường minh trong method hoặc boundary

Một domain invariant quan trọng có thể được kiểm tra trực tiếp trong method body mà không phụ thuộc AOP:

~~~java
public String requireText(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(
                "Text must not be blank");
    }
    return text;
}
~~~

Đây là Java logic thuần và chạy với mọi lời gọi, kể cả `this` hoặc `new`. Trong API public, nên map exception theo **nguồn lỗi thực tế**, không tự trả 400 nếu exception đến từ một server-generated value.

Khi muốn Jakarta Bean Validation dựa trên annotations, có thể dùng:

~~~java
Set<ConstraintViolation<RequestDto>> violations =
        validator.validate(request);
~~~

Đây là snippet với `validator` là `jakarta.validation.Validator` và `request` là `RequestDto`; nó kiểm tra bean constraints. Với constraints trên **method parameters hoặc return**, dùng `validator.forExecutables().validateParameters(...)` và `validateReturnValue(...)` đúng method/target, không nhầm `validate(request)` đã kiểm tra hết executable constraints.

### 8.5. AspectJ weaving

AspectJ compile-time/load-time weaving có thể áp dụng advice vào bytecode và không gặp đúng hạn chế self-invocation của Spring AOP proxy. Tuy nhiên setup/build/debug/deployment phức tạp hơn; không tự chuyển một app chỉ vì hai methods gọi nhau. **Refactor sang collaborator bean** thường phù hợp hơn.

## 9. Dự án Maven chạy được: Spring Boot 3.5.16, Java 17+

Dự án cố ý trình diễn **lỗi** và **cách sửa**:

- `SelfCallingService`: self-call bỏ qua parameter và return constraints của inner.
- `CheckedTextService`: validator method được đặt ở Spring bean khác.
- `DelegatingWorkflow`: gọi `CheckedTextService` qua Spring-injected proxy.
- `TextController`: một endpoint legacy cố tình cho thấy bypass, các endpoint khác minh họa Spring MVC built-in và `@Valid @RequestBody`.
- `SelfInvocationTest`: test proxy thực, direct call, self-call và manual Jakarta ExecutableValidator.
- `TextControllerTest`: test Spring MVC khác với service AOP.

Đây là demo **không có database, không xác thực người dùng và không có side effects**. Một endpoint được cố ý thiết kế sai để minh họa, không được giữ nguyên khi đưa lên production.

### 9.1. `pom.xml`

Spring Boot `3.5.16` có trên Maven Central, được công bố 25/06/2026; nhà phát hành ghi rõ đây là **bản cuối có hỗ trợ OSS của nhánh 3.5.x**. Pin version này để tái hiện Spring Framework 6.x behavior; với dự án production mới nên dùng một nhánh còn bảo trì OSS (ví dụ Boot 4.x) hoặc dịch vụ support phù hợp, và cập nhật code/tests theo version đó.

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
    <artifactId>self-invocation-validation</artifactId>
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
~~~

Trong demo này, Boot auto-configures method validation khi có provider/context phù hợp, nên không khai báo thêm `MethodValidationPostProcessor` thủ công. `spring-boot-starter-aop` được thêm tường minh để làm rõ sự phụ thuộc của AOP-based service method validation.

### 9.2. `SelfInvocationApplication.java`

`src/main/java/com/example/selfcall/SelfInvocationApplication.java`:

~~~java
package com.example.selfcall;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SelfInvocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelfInvocationApplication.class, args);
    }
}
~~~

### 9.3. `SelfCallingService.java`

`src/main/java/com/example/selfcall/SelfCallingService.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class SelfCallingService {

    public String viaThis(String text) {
        return this.checked(text);
    }

    public String viaImplicitThis(String text) {
        return checked(text);
    }

    public String viaThisReturn() {
        return invalidReturn();
    }

    @NotBlank
    public String checked(@NotBlank String text) {
        return text;
    }

    @NotBlank
    public String invalidReturn() {
        return "";
    }
}
~~~

Giải thích: class được đánh dấu `@Validated` và Spring quản lý. `checked` có parameter và return constraints. Nhưng outer methods **không có direct constraints** và gọi inner từ cùng target, nên không kích hoạt advice riêng của inner. `invalidReturn` được cố ý viết sai để test return-value validation khi gọi trực tiếp qua proxy.

### 9.4. `CheckedTextService.java`

`src/main/java/com/example/selfcall/CheckedTextService.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CheckedTextService {

    @NotBlank
    public String check(@NotBlank String text) {
        return text;
    }

    @NotBlank
    public String invalidReturn() {
        return "";
    }
}
~~~

### 9.5. `DelegatingWorkflow.java`

`src/main/java/com/example/selfcall/DelegatingWorkflow.java`:

~~~java
package com.example.selfcall;

import org.springframework.stereotype.Service;

@Service
public class DelegatingWorkflow {

    private final CheckedTextService checked;

    public DelegatingWorkflow(CheckedTextService checked) {
        this.checked = checked;
    }

    public String submit(String text) {
        return checked.check(text);
    }

    public String brokenReturnForTest() {
        return checked.invalidReturn();
    }
}
~~~

Lời gọi `checked.check(text)` là **lời gọi trên Spring-injected bean**, chứ không phải `this.check(text)` của target `CheckedTextService`. Với bean proxy đúng, parameter/return constraints được đánh giá.

### 9.6. `TextRequest.java`

`src/main/java/com/example/selfcall/TextRequest.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.constraints.NotBlank;

public record TextRequest(@NotBlank String value) {
}
~~~

Record chứa Bean Validation constraint trên input. MVC có thể kiểm tra record này nhờ `@Valid @RequestBody`, độc lập với việc service tự gọi method qua `this`.

### 9.7. `TextController.java`

`src/main/java/com/example/selfcall/TextController.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/diagnostics")
public class TextController {

    private final SelfCallingService legacy;
    private final DelegatingWorkflow workflow;

    public TextController(
            SelfCallingService legacy,
            DelegatingWorkflow workflow) {
        this.legacy = legacy;
        this.workflow = workflow;
    }

    // Anti-pattern: self-call phía service có thể trả 200 với text rỗng.
    @GetMapping("/legacy")
    public String legacy(@RequestParam("value") String value) {
        return legacy.viaThis(value);
    }

    // Built-in MVC handler method validation (Spring Framework 6.1+).
    @GetMapping("/mvc")
    public String mvc(
            @RequestParam("value") @NotBlank String value) {
        return value;
    }

    // MVC kiểm tra DTO trước; service delegate dùng proxy riêng.
    @PostMapping(path = "/submit",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> submit(
            @Valid @RequestBody TextRequest request) {
        return ResponseEntity.ok(
                workflow.submit(request.value()));
    }
}
~~~

**Không gắn class-level `@Validated` lên controller**, để Spring MVC 6.1+ dùng built-in handler method validation. Nếu gắn class-level annotation ấy, Spring có thể dùng AOP proxy-based method validation cho controller, làm exception types và test thay đổi.

### Các endpoint và expected status

| Endpoint | Input | Kết quả thiết kế trong demo |
| --- | --- | --- |
| `GET /diagnostics/legacy` | `value=` | 200 + body rỗng — **cố ý chứng minh bypass**, không phải API an toàn. |
| `GET /diagnostics/mvc` | `value=` | 400 do handler parameter `@NotBlank`. |
| `GET /diagnostics/mvc` | `value=hello` | 200, body `hello`. |
| `POST /diagnostics/submit` | `{"value":""}` | 400 do `@Valid @RequestBody`. |
| `POST /diagnostics/submit` | `{"value":"hello"}` | 200, body `hello`. |

Endpoint legacy chỉ là test fixture. Không được dùng nó để kết luận “200 với dữ liệu sai là chấp nhận được”; mục tiêu là để một regression test có thể làm rõ lỗi rồi yêu cầu sửa.

## 10. `SelfInvocationTest.java`: 12 test chứng minh AOP behavior

`src/test/java/com/example/selfcall/SelfInvocationTest.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class SelfInvocationTest {

    @Autowired
    SelfCallingService self;

    @Autowired
    CheckedTextService checked;

    @Autowired
    DelegatingWorkflow workflow;

    @Autowired
    Validator validator;

    @Test
    void beanIsProxied() {
        assertTrue(AopUtils.isAopProxy(self));
        assertTrue(AopUtils.isAopProxy(checked));
    }

    @Test
    void externalCallRejectsBlankParameter() {
        assertThrows(ConstraintViolationException.class,
                () -> self.checked(""));
    }

    @Test
    void explicitThisBypassesParameterCheck() {
        assertEquals("", self.viaThis(""));
    }

    @Test
    void implicitThisAlsoBypassesParameterCheck() {
        assertEquals("", self.viaImplicitThis(""));
    }

    @Test
    void externalValidCallWorks() {
        assertEquals("hello", self.checked("hello"));
    }

    @Test
    void externalCallChecksReturnConstraint() {
        assertThrows(ConstraintViolationException.class,
                () -> self.invalidReturn());
    }

    @Test
    void internalCallSkipsReturnConstraint() {
        assertEquals("", self.viaThisReturn());
    }

    @Test
    void delegatedCallRejectsBlankInput() {
        assertThrows(ConstraintViolationException.class,
                () -> workflow.submit(""));
    }

    @Test
    void delegatedCallAcceptsValidInput() {
        assertEquals("hello", workflow.submit("hello"));
    }

    @Test
    void delegatedReturnViolationIsDetected() {
        assertThrows(ConstraintViolationException.class,
                () -> workflow.brokenReturnForTest());
    }

    @Test
    void newObjectIsNotAnAopProxy() {
        SelfCallingService plain = new SelfCallingService();
        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals("", plain.checked(""));
    }

    @Test
    void manualExecutableValidationStillFindsConstraints()
            throws Exception {
        SelfCallingService plain = new SelfCallingService();

        Method inputMethod = SelfCallingService.class
                .getMethod("checked", String.class);

        var inputErrors = validator.forExecutables()
                .validateParameters(
                        plain, inputMethod, new Object[] {""});

        assertFalse(inputErrors.isEmpty());

        Method outputMethod = SelfCallingService.class
                .getMethod("invalidReturn");

        var outputErrors = validator.forExecutables()
                .validateReturnValue(
                        plain, outputMethod, "");

        assertFalse(outputErrors.isEmpty());
    }
}
~~~

**Ý nghĩa của 12 tests:**

1. Bean có Spring AOP proxy.
2. External invalid input bị chặn.
3. Explicit `this` bypass parameter constraint.
4. Implicit `this` bypass tương tự.
5. External valid input thành công.
6. External invalid return bị chặn.
7. Internal invalid return không bị chặn.
8. Delegate bean khác chặn invalid input.
9. Delegate chấp nhận valid input.
10. Delegate bắt invalid return.
11. Java `new` không có proxy.
12. Jakarta `ExecutableValidator` thủ công vẫn thấy metadata constraint.

**Exception nuance:** Với cấu hình mặc định `MethodValidationPostProcessor`, method-validation AOP thường ném `ConstraintViolationException`. Nếu dự án bật `setAdaptConstraintViolations(true)`, Spring có thể ném `MethodValidationException` thay vì exception đó; tests phải phù hợp với cấu hình, không xóa negative cases.

**Điểm mạnh của test thủ công:** Bean Validation metadata vẫn tồn tại dù self-call bypass; `ExecutableValidator` có thể kiểm tra vì ta **gọi explicit API**, tách biệt nguyên nhân “không có annotation” khỏi “không đi qua proxy”.

## 11. `TextControllerTest.java`: 7 MockMvc tests tách MVC khỏi AOP

`src/test/java/com/example/selfcall/TextControllerTest.java`:

~~~java
package com.example.selfcall;

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
class TextControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void legacyCallDemonstratesIncorrect200() throws Exception {
        mvc.perform(get("/diagnostics/legacy")
                    .param("value", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(""));
    }

    @Test
    void mvcMethodValidationRejectsBlankQuery()
            throws Exception {
        mvc.perform(get("/diagnostics/mvc")
                    .param("value", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mvcMethodValidationAcceptsValidQuery()
            throws Exception {
        mvc.perform(get("/diagnostics/mvc")
                    .param("value", "hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("hello"));
    }

    @Test
    void validJsonBodyCallsDelegatedWorkflow()
            throws Exception {
        mvc.perform(post("/diagnostics/submit")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"value":"hello"}
                            """))
                .andExpect(status().isOk())
                .andExpect(content().string("hello"));
    }

    @Test
    void blankJsonBodyFieldIsRejectedByMvc()
            throws Exception {
        mvc.perform(post("/diagnostics/submit")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"value":""}
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedJsonIsRejectedBeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/diagnostics/submit")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"value\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredQueryIsBadRequest()
            throws Exception {
        mvc.perform(get("/diagnostics/mvc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Có **7 MockMvc tests**. Test đầu cố ý ghi nhận behavior **không an toàn** để chứng minh bypass trong demo; sau khi sửa ứng dụng thật, nó phải được chuyển thành test khẳng định input invalid bị từ chối.

Trong phần `@Valid @RequestBody`, Spring MVC kiểm tra record ngay ở argument resolution; điều này **khác** AOP method validation trên `CheckedTextService`. Vì vậy bộ test service (12) là cần thiết ngoài HTTP tests (7).

### 11.1. Chạy bộ tests

Trong thư mục có `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Nếu tạo Maven wrapper:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
mvnw.cmd test
mvnw.cmd spring-boot:run
~~~

Tổng cộng **19 tests**: 12 service tests + 7 MockMvc tests. Chúng được **thiết kế** cho phiên bản và mã nguồn nêu trên; việc cung cấp code trong bài **không chứng minh đã chạy Maven/JUnit**. Khi tích hợp vào repository, hãy chạy thực tế và kiểm tra reports. Test status/body có thể cần điều chỉnh nếu dự án thêm Spring Security, global `@ControllerAdvice` hoặc custom web configuration.

### 11.2. Curl

~~~bash
curl -i "http://localhost:8080/diagnostics/legacy?value="
curl -i "http://localhost:8080/diagnostics/mvc?value="
curl -i "http://localhost:8080/diagnostics/mvc?value=hello"

curl -i -X POST "http://localhost:8080/diagnostics/submit" \
  -H "Content-Type: application/json" \
  -d '{"value":"hello"}'

curl -i -X POST "http://localhost:8080/diagnostics/submit" \
  -H "Content-Type: application/json" \
  -d '{"value":""}'
~~~

Dự kiến status của năm request là **200, 400, 200, 200, 400**. Request đầu **cố ý cho thấy lỗi**; hai response bodies thành công là `hello` khi input hợp lệ. Body lỗi mặc định của Spring Boot không bị hardcode vì tùy version/config `ProblemDetail` và exception handlers.

## 12. Debug khi tests hoặc production không như kỳ vọng

### 12.1. `AopUtils.isAopProxy(service) == false`

Kiểm tra:
- Bean có do container quản lý không hay bị tạo bằng `new`?
- `@Validated` có nằm trên class hoặc vị trí processor nhận diện không?
- Có `spring-boot-starter-validation`, Jakarta provider và method validation post-processor không?
- Có Spring AOP classpath và post-processing được bật không?
- Class có `final`, method visibility hoặc proxy constraints không?
- Bean có bị thay bằng mock/spy không còn advice trong test không?

**Không tự đăng ký thêm processor ngay lập tức** khi chưa kiểm tra Boot auto-config. Hai processor có thể gây khó đoán hơn một processor đúng.

### 12.2. Proxy có thật nhưng invalid input không tạo exception

Kiểm tra:
- Gọi đúng bean proxy hay đang gọi vào `this`?
- Constraint có đặt **trên parameter/return của đúng method** không?
- `@NotBlank` trên type thích hợp không? `@Min` trên numeric?
- Có validation group khác Default không?
- `MethodValidationPostProcessor` có chọn annotation `@Validated` không?
- Lời gọi là public/interceptable và qua interface được proxy hay không?
- Cấu hình `adaptConstraintViolations` có khiến exception class khác không?

**Một breakpoint trong method body không đủ** để kết luận validation đã chạy; self-call vẫn vào method body như Java bình thường.

### 12.3. Chỉ lỗi khi từ web nhưng không lỗi từ job

Có thể web controller đã `@Valid`/built-in method validation, còn job gọi service self-call. Viết tests **gọi trực tiếp Spring-injected service** và kiểm chứng cả đường job/batch. DTO constraints ở web không bảo vệ mọi entry point.

### 12.4. `@Transactional` hoặc `@Async` cũng hoạt động lạ

Các proxy-based advice khác cũng có thể bị self-invocation bypass. Nhưng không giải quyết bằng cách gom mọi method vào một service và thêm nhiều annotations; hãy tách component boundary rõ, dùng transaction boundary phù hợp và test side effects.

### 12.5. Return-value violation được map thành HTTP 400

Đừng viết global:

~~~java
@ExceptionHandler(ConstraintViolationException.class)
ResponseEntity<?> onViolation(ConstraintViolationException ex) {
    return ResponseEntity.badRequest().build();
}
~~~

Đây là **anti-pattern** nếu handler có thể nhận cả service return-value violations. Một `ConstraintViolationException` từ service AOP không tự chứng minh input client sai. Cần biết lỗi xảy ra ở **parameter do client cung cấp**, **return value do server tạo**, hay service nội bộ. Với MVC 6.1+ built-in, `HandlerMethodValidationException#isForReturnValue()`/`getStatusCode()` phân biệt 400/500; với service AOP cần kiến trúc mapping tương ứng.

### 12.6. Dùng `AopContext.currentProxy()` khiến test plain Java fail

`AopContext` cần proxy exposure + invocation context. Nếu test tạo `new` object, không có current proxy. Chuyển sang injected collaborator bean là cách đơn giản hơn. Đừng buộc domain code phụ thuộc `AopContext` chỉ để tránh refactor.

## 13. Lỗi thường gặp và cách sửa

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `this.validate(value)` với `@NotBlank` ở inner | AOP validation của inner bị bypass. | Tách bean và inject proxy, hoặc explicit validation. |
| Bỏ chữ `this` | Vẫn là implicit self-call. | Thay đường gọi, không chỉ cú pháp. |
| Chỉ đặt `@Validated` trên class | Không bảo đảm mọi lời gọi được advise. | Kiểm tra provider, processor, proxy và boundary. |
| `new Service().checked(value)` | Không có Spring-managed proxy. | Lấy bean từ context hoặc validate tường minh. |
| Chỉ test outer method có constraint riêng | Che bug inner self-invocation. | Test constraints inner trực tiếp/qua outer tách biệt. |
| Dùng `private`/`final` methods để kỳ vọng AOP | Advice không chặn theo proxy mechanisms chuẩn. | Public/interceptable collaborator methods. |
| JDK proxy expose thiếu method | Caller không thể gọi implementation-only method qua interface. | Thiết kế interface/proxy type phù hợp. |
| Dùng self injection ở constructor | Circular dependency/lifecycle phức tạp. | Ưu tiên tách bean, test lazy lookup nếu cần. |
| Dùng `AopContext.currentProxy()` mặc định | Tăng coupling, cần exposeProxy config. | Refactor collaborator. |
| Boot đã có post-processor nhưng tự tạo thêm | Có thể làm proxy/advice phức tạp. | Kiểm tra context/autoconfiguration. |
| Dùng `@Valid` ở MVC rồi coi service an toàn | Queue/job có thể bypass service validation. | Service-level proxy/explicit tests. |
| Catch tất cả `ConstraintViolationException` -> 400 | Che server return errors. | Phân loại đúng input vs return value. |
| Chỉ check `isAopProxy` | Proxy có thể có advisor khác hoặc self-call. | Test invalid argument/return qua proxy. |
| Đổi `proxy-target-class` để chữa self-call | JDK/CGLIB đều bypass this-calls. | Tách bean. |
| AspectJ weaving chỉ để sửa một helper | Deployment phức tạp không cần thiết. | Refactor trước. |

## 14. Checklist regression tests

- [ ] Có test bean `@Validated` được Spring quản lý và có AOP proxy.
- [ ] Có test direct external call với parameter invalid → validation exception.
- [ ] Có test `this.inner(invalid)` → thể hiện bypass trong bản lỗi.
- [ ] Có test `inner(invalid)` không ghi `this` → vẫn bypass.
- [ ] Có test external return-value violation và internal return-value bypass.
- [ ] Có test lời gọi giữa **hai Spring beans** sau refactor bị chặn.
- [ ] Có test valid input qua proxy được chấp nhận.
- [ ] Có test plain `new` instance không tự chạy method validation.
- [ ] Có test `ExecutableValidator` thủ công nhìn thấy constraint metadata.
- [ ] Kiểm tra `@Validated`/provider/AOP/MethodValidationPostProcessor đúng cấu hình.
- [ ] Không dùng private/final methods làm security validation boundary dựa trên AOP.
- [ ] Nếu JDK proxy, interface có expose method cần advice.
- [ ] Không có circular self injection không cần thiết hoặc phụ thuộc `AopContext` mặc định.
- [ ] Phân biệt service AOP với Spring MVC built-in 6.1+.
- [ ] Không gắn class-level `@Validated` lên controller nếu muốn MVC built-in và chưa đánh giá AOP.
- [ ] Với method validation exception adaptation, test `ConstraintViolationException` vs `MethodValidationException` đúng configuration.
- [ ] Input validation chạy **trước side effects**, output validation và transaction boundary được kiểm tra.
- [ ] API không trả 400 cho server return violation hoặc leak rejected values.
- [ ] Có tests cho scheduled jobs/event consumers ngoài request HTTP.
- [ ] Re-run regression tests khi đổi service injection, proxy mode, groups hoặc Spring version.

**Kết luận:** Trong Spring AOP-based method validation, **`this.inner(...)` và `inner(...)` không đi qua proxy**, vì vậy `@NotBlank`/`@NotNull`/`@Min` trên inner method có thể **không được kiểm tra** ở cả parameter lẫn return value. Bản sửa thường tốt nhất là **đưa inner method cần validation sang một Spring bean khác rồi inject/gọi bean ấy**, hoặc áp dụng validation tường minh. Phải kiểm chứng bằng các tests gọi **bean proxy thực** và tách biệt với Spring MVC 6.1+ built-in handler validation.

## Tài liệu tham khảo

- Spring Framework 6.2 — **Proxying Mechanisms / Understanding AOP Proxies**, self-invocation và giải pháp: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — **Spring-driven Method Validation**, `MethodValidationPostProcessor` và exception adaptation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 Javadoc — `MethodValidationPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework 6.2 — **MVC Validation**, ``MethodArgumentNotValidException` / `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — AOP proxy mechanisms trên branch hiện tại: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Jakarta Bean Validation 3.0 API — `ExecutableValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator
- Spring Boot 3.5.16 công bố 25/06/2026 (cuối nhánh OSS 3.5.x): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
