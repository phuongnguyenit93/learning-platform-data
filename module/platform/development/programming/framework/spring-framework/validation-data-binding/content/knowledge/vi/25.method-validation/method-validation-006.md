# Self-invocation, phương thức `final` và các giới hạn proxy trong Spring Method Validation

## 1. Vấn đề: có `@Validated` mà dữ liệu sai vẫn đi qua

Trong Spring, một service có thể đánh dấu `@Validated` trên class và đặt `@NotBlank`, `@Min`, `@NotNull` trên tham số. Lệnh gọi từ bean khác có thể ném lỗi ngay khi tham số vi phạm, trong khi chính service gọi `this.check(...)` thì lại chạy bình thường. Một số method `final` hoặc `private` cũng không được kiểm tra dù có constraint.

Điểm quyết định là **lời gọi có đi qua điểm kích hoạt method validation hay không**. Với Spring method validation kiểu AOP thường dùng cho service, điểm kích hoạt là **Spring proxy**; chỉ các lời gọi mà proxy có thể intercept mới chạy advice validation. Annotation Jakarta Validation mô tả quy tắc, nhưng **không tự làm mọi lời gọi Java được validate**.

Bài học này tập trung vào:

- **Self-invocation**: gọi method của chính object qua `this`, bỏ qua advice proxy.
- **`final`, `private`, `static` và class `final`**: vì sao proxy kiểu subclass (CGLIB) có giới hạn.
- **JDK dynamic proxy so với CGLIB**: trường hợp method implementation `final` vẫn có thể được validate khi gọi qua interface JDK proxy.
- Cách kiểm chứng bằng Java 17, Spring Framework 6.x và Hibernate Validator.
- Cách thiết kế service và controller để method validation diễn ra đúng boundary.

Ví dụ dùng **Spring Framework 6 / Jakarta Validation** với import `jakarta.validation.*`. Spring Framework 5 / Boot 2 dùng namespace cũ `javax.validation.*`; không trộn hai hệ thư viện và import.

## 2. Ba tầng cấu thành method validation

| Tầng | Thành phần tiêu biểu | Vai trò |
| --- | --- | --- |
| Quy tắc | `@NotNull`, `@NotBlank`, `@Min`, `@Valid` | Chỉ ra điều kiện đối với tham số, giá trị trả về hoặc object lồng nhau |
| Engine Jakarta Validation | `Validator`, `ExecutableValidator`, `ConstraintViolation` | Thực hiện phép kiểm tra theo constraint |
| Spring invocation boundary | `MethodValidationPostProcessor`, `MethodValidationInterceptor`, AOP proxy | Gọi engine tại thời điểm method được gọi qua proxy |

Với một service Spring được quản lý và cấu hình method validation theo AOP, luồng điển hình:

```text
Bean khác gọi service.save(x)
          |
          v
     Spring proxy
          |
          +--> MethodValidationInterceptor
          |      |
          |      +--> ExecutableValidator.validateParameters(...)
          |      |           |
          |      |           +--> vi phạm? Ném exception
          |      |
          |      +--> Gọi target.save(x) nếu tham số hợp lệ
          |      |
          |      +--> ExecutableValidator.validateReturnValue(...)
          |                  |
          |                  +--> vi phạm? Ném exception
          v
     Trả kết quả cho caller
```

Khi lời gọi ở bên trong class, ví dụ `this.save(x)`, phương thức được gọi trực tiếp trên target object. Nó **không quay lại proxy** để chạy interceptor cho method `save`.

`@Validated` của Spring (`org.springframework.validation.annotation.Validated`) ở type level là dấu hiệu để `MethodValidationPostProcessor` chọn bean cho proxy method validation. `@NotBlank` hoặc `@Min` mới là các constraint Jakarta Validation cụ thể. Nếu Spring container không đăng ký post-processor, hoặc caller không dùng proxy, việc gắn annotation đơn thuần không đảm bảo tự kiểm tra khi gọi method.

Trong một ứng dụng Spring thuần, có thể đăng ký:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class ValidationConfig {
    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

Một service tham gia xác thực method:

```java
import jakarta.validation.constraints.Min;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class OrderService {
    public void submit(@Min(1) int quantity) {
        // Xử lý đơn hàng.
    }
}
```

Hai đoạn trên là fragment của một ứng dụng Spring, không phải chương trình độc lập. Trong Spring Boot 3, validation starter và auto-configuration thông thường có thể tạo post-processor tương ứng; vẫn cần kiểm tra provider và đường gọi thực tế.

## 3. Self-invocation: vì sao `this.method()` bỏ qua validation?

Xét service:

```java
@Service
@Validated
public class AccountService {

    public String create(@NotBlank String username) {
        return "created:" + username;
    }

    public String createInternally(String username) {
        return this.create(username);
    }
}
```

Với một method-validation proxy thực sự được tạo, hai đường đi khác nhau:

```text
Bean A
 |
 +--> accountServiceProxy.create("")
 |          |
 |          +--> @NotBlank: lỗi, target.create không chạy
 |
 +--> accountServiceProxy.createInternally("")
            |
            +--> target.createInternally("")
                       |
                       +--> this.create("") -> chạy thân create
                                                không qua validation advice
```

Viết `create(username)` không có `this.` vẫn là self-invocation. Hai lời gọi dùng **cùng annotation `@NotBlank`** nhưng khác ranh giới intercept.

Các điểm dễ nhầm:

1. Bean khác gọi một **method public, có thể được advice** qua proxy thì method validation có hiệu lực.
2. Method ngoài gọi `this.inner(...)` thì method `inner` không được proxy advice riêng; nếu method **ngoài** có constraint của riêng nó, constraint ngoài vẫn có thể được kiểm tra.
3. Self-invocation có thể bỏ qua những advice khác của Spring AOP như transactions, caching hoặc asynchronous execution, tùy loại cấu hình.
4. Nếu thân method gọi `Validator.validate(...)` hay `ExecutableValidator` một cách tường minh, đó là kiểm tra thủ công nên vẫn chạy. Self-invocation chỉ bỏ qua interceptor tự động tại boundary bị vượt qua.
5. Đừng kết luận `@NotBlank` bị vô hiệu hóa toàn cục vì một đường đi không ném lỗi. Kiểm tra bean thực tế có được proxy và ai đang giữ reference.

## 4. JDK proxy và CGLIB: giới hạn không giống nhau

| Tính chất | JDK dynamic proxy | CGLIB (class proxy) |
| --- | --- | --- |
| Bản chất | Object implement các interface của target | Runtime subclass của target class |
| Có cần interface? | Có | Không |
| Lời gọi được intercept | Các method qua interface proxy | Các instance method subclass có thể override |
| Method implementation `final` | **Có thể intercept** qua interface trước khi gọi target | **Không intercept** qua override vì Java cấm override final |
| Class implementation `final` | Vẫn có thể dùng JDK proxy nếu có interface hợp lệ | Không thể tạo subclass, có thể thất bại khi proxy |
| Method `private` | Không thể gọi trực tiếp trên proxy interface | Không thể override/advice |
| Self-invocation bằng `this` | Bỏ qua advice | Bỏ qua advice |
| Kiểu nên inject | Interface được proxy | Concrete class hoặc kiểu hợp lệ |

Spring AOP có thể chọn JDK proxy khi target có interface, hoặc dùng CGLIB khi target không có interface; cấu hình `proxyTargetClass=true` có thể buộc class-based proxy. Không dựa vào tên class hoặc giả định mặc định của một starter: hãy kiểm tra **proxy thực sự**.

### 4.1. Vì sao CGLIB không intercept được `final`?

CGLIB dùng subclass và override method để chạy interceptor. Java cấm override method `final`. Nếu class `final` thì cũng không thể subclass. Với CGLIB, `private` không thể override, còn `static` là method của class chứ không phải instance method được AOP proxy wrap.

Ví dụ giới hạn:

```java
@Validated
public class BillingService {
    public final void bill(@NotNull String accountId) {
        // Method final không thể được CGLIB override.
    }
}
```

Đây là fragment minh họa. Nếu `BillingService` dùng CGLIB proxy, Spring không áp dụng method-validation advice lên lời gọi `bill(null)` vì method là `final`. Bean Validation annotation vẫn có trong metadata nhưng automatic method interception không xảy ra. Đừng bỏ qua kiểm tra đầu vào quan trọng chỉ vì đã nhìn thấy annotation.

### 4.2. JDK proxy có thể validate implementation `final`

```java
public interface BillingApi {
    void bill(@NotNull String accountId);
}

@Validated
public final class FinalBillingService implements BillingApi {
    @Override
    public final void bill(String accountId) {
        // Logic thực thi.
    }
}
```

Nếu Spring tạo **JDK proxy của `BillingApi`**, caller gọi `billingApi.bill(null)` lên proxy. Proxy chặn lời gọi **trước khi** chuyển tới method final của implementation; do đó vẫn có thể validate.

Điều kiện quan trọng là caller giữ **interface reference**. JDK proxy không phải subclass của `FinalBillingService`, nên không thể ép nó về implementation class để gọi các method riêng của class.

Đoạn trên đặt `@NotNull` ở **interface** và không thêm constraint tham số trên method override của implementation. Theo quy tắc kế thừa method constraints trong Jakarta Validation, một implementation thường không được tự tăng tiền điều kiện của tham số so với hợp đồng interface. Vi phạm quy tắc này có thể dẫn đến `ConstraintDeclarationException`.

## 5. Ví dụ Java 17 chạy độc lập bằng Maven

Ví dụ dựng hai Spring ApplicationContext: context CGLIB minh họa external/self/final/private và lời gọi bằng `new`; context JDK minh họa interface proxy có thể chặn method implementation final. Không cần chạy web server hay database.

Cấu trúc:

```text
method-validation-proxy-demo/
├── pom.xml
└── src/main/java/demo/
    └── MethodValidationProxyDemo.java
```

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>method-validation-proxy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.MethodValidationProxyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` và `spring-aop` có cùng phiên bản. `hibernate-validator` cung cấp implementation Jakarta Validation; `expressly` là implementation Jakarta Expression Language dùng cho message interpolation.

### 5.2. `src/main/java/demo/MethodValidationProxyDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

import java.util.function.Supplier;

public final class MethodValidationProxyDemo {

    @Validated
    public static class BookingService {
        public String check(@NotBlank String code) {
            return "accepted:" + code;
        }

        public String viaThis(String code) {
            return this.check(code);
        }

        public final String finalCheck(@NotBlank String code) {
            return "final:" + code;
        }

        public String viaPrivate(String code) {
            return privateCheck(code);
        }

        private String privateCheck(@NotBlank String code) {
            return "private:" + code;
        }
    }

    public interface TicketApi {
        String book(@NotBlank String code);
    }

    @Validated
    public static final class FinalTicketService implements TicketApi {
        @Override
        public final String book(String code) {
            return "ticket:" + code;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CglibConfig {
        @Bean
        static MethodValidationPostProcessor methodValidationPostProcessor() {
            MethodValidationPostProcessor p =
                    new MethodValidationPostProcessor();
            p.setProxyTargetClass(true);
            return p;
        }

        @Bean
        BookingService bookingService() {
            return new BookingService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JdkConfig {
        @Bean
        static MethodValidationPostProcessor methodValidationPostProcessor() {
            MethodValidationPostProcessor p =
                    new MethodValidationPostProcessor();
            p.setProxyTargetClass(false);
            return p;
        }

        @Bean
        TicketApi ticketApi() {
            return new FinalTicketService();
        }
    }

    private static void attempt(String label, Supplier<String> invocation) {
        try {
            System.out.println(label + ": " + invocation.get());
        } catch (ConstraintViolationException e) {
            System.out.println(label
                    + ": VIOLATION(" + e.getConstraintViolations().size() + ")");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext ctx =
                     new AnnotationConfigApplicationContext(CglibConfig.class)) {
            BookingService service = ctx.getBean(BookingService.class);
            System.out.println("CGLIB proxy: "
                    + AopUtils.isCglibProxy(service));

            attempt("external", () -> service.check(""));
            attempt("self", () -> service.viaThis(""));
            attempt("final", () -> service.finalCheck(""));
            attempt("private", () -> service.viaPrivate(""));
            attempt("new", () -> new BookingService().check(""));
            attempt("valid", () -> service.check("ABC"));
        }

        try (AnnotationConfigApplicationContext ctx =
                     new AnnotationConfigApplicationContext(JdkConfig.class)) {
            TicketApi tickets = ctx.getBean(TicketApi.class);
            System.out.println("JDK proxy: "
                    + AopUtils.isJdkDynamicProxy(tickets));
            attempt("JDK final", () -> tickets.book(""));
        }
    }
}
```

**Giải thích thiết kế:** `BookingService` không implement interface, `setProxyTargetClass(true)` tạo class-based proxy để kiểm tra `this` và method final. `FinalTicketService` là class final có interface; cấu hình JDK proxy cho phép chặn `TicketApi.book` mà không subclass implementation. Các method trả string thuần không có side effect, nên có thể quan sát đường gọi an toàn.

Chạy trong thư mục có `pom.xml` bằng JDK 17 và Maven:

```bash
mvn -q clean compile exec:java
```

**Các dòng chương trình dự kiến in ra stdout** (không bao gồm log riêng của Spring/Hibernate Validator):

```text
CGLIB proxy: true
external: VIOLATION(1)
self: accepted:
final: final:
private: private:
new: accepted:
valid: accepted:ABC
JDK proxy: true
JDK final: VIOLATION(1)
```

| Case | Đường gọi | `@NotBlank` được thực thi tự động? | Giải thích |
| --- | --- | --- | --- |
| `external` | Caller → CGLIB proxy → `check("")` | Có, 1 vi phạm | Public method có thể override và đi qua proxy |
| `self` | Caller → proxy → `viaThis("")` → `this.check("")` | Không đối với `check` nội bộ | Không quay lại proxy ở lời gọi bên trong |
| `final` | Caller → CGLIB proxy → `finalCheck("")` | Không | CGLIB không override final method |
| `private` | Caller → proxy → `viaPrivate` → private method | Không đối với private method | Method private không thể override |
| `new` | Caller → `new BookingService()` | Không | Không phải bean proxy của Spring |
| `valid` | Caller → CGLIB proxy → `check("ABC")` | Có, hợp lệ | Input đáp ứng `@NotBlank` |
| `JDK final` | Caller → JDK interface proxy → target final method | Có, 1 vi phạm | Proxy intercept ở interface |

Output không dựa vào text lỗi hoặc thứ tự `Set<ConstraintViolation<?>>`, chỉ dùng số vi phạm. Từ `accepted:` hay `final:` trong các case bypass, không suy ra production nên chấp nhận mã trống; ví dụ cố ý để thân method đơn giản nhằm chỉ ra **absence of advice**.

### 5.3. Tại sao hai context độc lập?

Nếu đặt cả hai service vào cùng một context và bật `proxyTargetClass=true` toàn cục, Spring có thể thử tạo CGLIB proxy cho class final của ví dụ JDK và thất bại. Việc tách context giữ cho mỗi phép thử chỉ phụ thuộc vào **loại proxy đang giải thích**.

## 6. Phương thức `final` không phải trường hợp duy nhất

### 6.1. `private` và `static`

- Method `private` không thể được subclass override và không phải method công khai của JDK interface proxy. Constraint tham số đặt trên private method không mặc nhiên được Spring AOP method-validation interceptor kiểm tra.
- Method `static` được gọi trên class, không trên instance proxy theo mô hình Spring AOP thông thường.
- Method ở superclass không visible cho subclass (ví dụ package-private từ package khác) có thể coi như private đối với CGLIB, vì vậy không advice được.
- Với CGLIB, lựa chọn dễ dự đoán nhất cho method cần advice là **public, không final, instance method**.

### 6.2. Class final, Java record và Kotlin

- Java `record` là final. Điều này chặn **CGLIB proxy của record như một service**, nhưng **không ngăn** dùng `@Valid` hay `Validator.validate(record)` để validate **dữ liệu record**. Đó là hai cơ chế khác nhau.
- Class `final` có implement interface vẫn có thể được **JDK proxy** wrap nếu method nằm trên interface được proxy và constraint metadata hợp lệ.
- Kotlin class và method thường final theo mặc định. Khi dùng class-based proxy, cần kiểm tra cấu hình `kotlin-spring`/all-open (nếu phù hợp) hoặc cân nhắc interface proxy.
- Không cố xử lý giới hạn CGLIB bằng cách chỉ thêm `@Validated` lên method final. Phải thay đổi ranh giới hoặc loại proxy.

### 6.3. Interface method constraints và quy tắc kế thừa

Jakarta Validation giới hạn việc **thêm tiền điều kiện tham số** trong method override. Ví dụ:

```java
public interface LoginApi {
    void login(String username);
}

public class LoginService implements LoginApi {
    @Override
    public void login(@NotBlank String username) {
        // Có thể vi phạm quy tắc Bean Validation method inheritance.
    }
}
```

Đây là fragment minh họa **thiết kế sai cần tránh**. Vì interface khai báo tham số không có constraint mà implementation thêm `@NotBlank`, provider có thể ném `ConstraintDeclarationException`. Đặt constraint vào **hợp đồng interface** khi các caller phải cùng tuân thủ điều kiện, rồi không khai báo lại ở method override. Với nhiều interface hoặc inheritance phức tạp, kiểm tra lại quy tắc của Jakarta Validation thay vì đoán provider sẽ gộp như ý.

## 7. Khắc phục self-invocation bằng cách tách bean

Thay vì để service gọi method cần AOP của chính mình:

```java
@Service
@Validated
public class RegistrationService {
    public void register(String email) {
        this.verifyEmail(email); // self-invocation
    }

    public void verifyEmail(@NotBlank String email) {
        // ...
    }
}
```

Tách thành hai bean (fragment minh họa cho ứng dụng Spring, bỏ imports và phần nghiệp vụ):

```java
@Service
@Validated
public class EmailPolicy {
    public void verifyEmail(@NotBlank String email) {
        // ...
    }
}

@Service
public class RegistrationService {
    private final EmailPolicy policy;

    public RegistrationService(EmailPolicy policy) {
        this.policy = policy;
    }

    public void register(String email) {
        policy.verifyEmail(email); // qua bean EmailPolicy được Spring inject
        // Tiếp tục xử lý.
    }
}
```

Khi `EmailPolicy` được Spring proxied đúng, lời gọi qua field được inject đi qua proxy và chạy validation. Cách này giúp ranh giới nghiệp vụ rõ ràng, dễ test và không khiến một service cần biết về hạ tầng proxy.

Những lựa chọn khác:

- **Inject self-reference proxy** (thường qua `@Lazy` để tránh vòng phụ thuộc), sau đó gọi trên tham chiếu proxy thay vì `this`. Hạn chế là dễ tạo circular dependency và khiến code gắn chặt với AOP.
- **`AopContext.currentProxy()`** chỉ khi cấu hình bật `exposeProxy=true` và có proxy context hợp lệ. Đây là giải pháp mang coupling mạnh với Spring, **không giúp CGLIB intercept method final**.
- **`ExecutableValidator` thủ công**: `validator.forExecutables().validateParameters(target, method, args)` và `validateReturnValue(...)` giúp kiểm tra các method/đối tượng không đi qua proxy. Ứng dụng phải tự xử lý reflection, groups và errors.
- **Guard trong domain logic**: nếu điều kiện là invariant phải đúng ở *mọi* đường gọi, kiểm tra tường minh trong constructor/method/domain service theo yêu cầu. Method validation ở boundary là tiện ích, không thay thế mọi bảo vệ nghiệp vụ.

Không cần tách bean cho mọi method private: chỉ tách khi cần chính xác **lời gọi qua proxy** hoặc ranh giới trách nhiệm rõ hơn.

## 8. Spring MVC 6.1+ có cơ chế method validation riêng

Spring Framework 6.1 giới thiệu **built-in method validation** trong quá trình xử lý controller của Spring MVC, không nhất thiết dựa vào service-style AOP proxy.

Ví dụ fragment cho ứng dụng có Spring Web MVC và Jakarta Validation:

```java
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {
    @GetMapping("/products")
    String list(@RequestParam @Min(1) int page) {
        return "page=" + page;
    }
}
```

Khi có constraint `@Min(1)` trực tiếp trên tham số và request đi qua pipeline MVC, request `page=0` có thể bị từ chối bởi **MVC built-in method validation**. Exception điển hình là **`HandlerMethodValidationException`**.

Nếu chỉ dùng `@Valid @RequestBody` cho object command và không cần method validation, MVC thường dùng argument-level validation và có thể ném **`MethodArgumentNotValidException`**. Khi method có direct constraint, MVC method validation có thể bao gồm cả nested validation của `@Valid`.

**Chú ý:** tài liệu Spring 6.1+ khuyến nghị **bỏ `@Validated` class-level ở controller** nếu muốn sử dụng built-in method validation; với class-level `@Validated`, controller có thể sử dụng AOP proxy validation thay vì built-in method validation.

Phân biệt boundary:

| Tình huống | Cơ chế |
| --- | --- |
| HTTP request vào controller Spring MVC 6.1+, direct parameter constraints | MVC built-in validation |
| Service Spring bean `@Validated` được gọi qua AOP proxy | `MethodValidationInterceptor` |
| Đối tượng DTO được `Validator.validate(...)` tường minh | Jakarta Validation trực tiếp |
| Gọi `new Controller().method(...)` hay `new Service().method(...)` | Không có MVC pipeline hoặc Spring AOP proxy tự động |
| Target service gọi `this.otherMethod(...)` | Không chạy interceptor riêng cho method bên trong |

Đừng chỉ so sánh hai annotation giống nhau để suy ra behavior giống nhau: controller validation và service method validation có **điểm kích hoạt, exception và xử lý lỗi** khác nhau.

## 9. Exceptions, groups và return value

### Exceptions

Với `MethodValidationPostProcessor` thông thường, vi phạm Jakarta Validation tạo **`jakarta.validation.ConstraintViolationException`**. Một số cấu hình Spring có thể bật chế độ `setAdaptConstraintViolations(true)` để nhận **Spring `MethodValidationException`**. Còn trong MVC built-in, exception đặc trưng là `HandlerMethodValidationException`. Hãy viết handler/test theo đúng đường validation đang dùng.

### Return value constraint

Method validation không chỉ kiểm tra input. Ví dụ fragment:

```java
public @NotNull String issueToken(@NotBlank String username) {
    return lookupToken(username);
}
```

`lookupToken` là hàm nghiệp vụ được giả định có sẵn. Nếu method được gọi qua proxy tương ứng, Jakarta Validation có thể kiểm tra `username` **trước khi method chạy** và `@NotNull` cho kết quả **sau khi method kết thúc**. Khi method trả `null`, một violation được báo tại ranh giới trả về.

### Cascading và null

`@Valid` yêu cầu kiểm tra các constraint của object con nếu object không null; nó **không tự buộc tham số khác null**. Chẳng hạn:

```java
public void register(@NotNull @Valid RegistrationRequest request) {
    // @NotNull kiểm tra null; @Valid kiểm tra object nếu có giá trị.
}
```

Đây chỉ là fragment. Nếu object con cần được validate bằng AOP method validation, method vẫn phải được gọi qua đúng proxy hoặc cơ chế Jakarta Validation khác.

### Validation groups

Spring `@Validated(SomeGroup.class)` có thể ảnh hưởng nhóm constraint được đánh giá khi method validation chạy. Một method có thể trông như “không validate” vì constraint nằm ngoài group đang active; đừng vội quy ngay cho self-invocation. Khi debug, kiểm tra group mặc định, group trên type/method và cấu hình provider thực tế.

## 10. Checklist chẩn đoán lỗi proxy method validation

Khi một phương thức có constraint nhưng vẫn nhận input sai:

1. **Có Spring bean hay chỉ là `new`?** Lấy bean qua dependency injection hoặc context.
2. **Bean thực tế có phải proxy?** Dùng `AopUtils.isAopProxy(service)`, `AopUtils.isCglibProxy(service)` và `AopUtils.isJdkDynamicProxy(service)`.
3. **Có `MethodValidationPostProcessor` và provider Jakarta Validation?** Với cấu hình Spring thuần, phải đăng ký; với Boot, kiểm tra validation starter và auto-configuration.
4. **Type có Spring `@Validated` không?** Đối với service AOP, đây thường là dấu hiệu để chọn bean.
5. **Caller có đi qua proxy không?** Tìm `this.method()`, gọi implicit method nội bộ, hoặc giữ reference target cũ.
6. **Method/class có `final` hay private/static không?** Đối chiếu với kiểu proxy JDK/CGLIB.
7. **Nếu JDK proxy, caller có dùng interface không?** Method có trên interface được proxy và constraint inheritance có hợp lệ không?
8. **Có constraint đúng kiểu và đúng validation group?** Kiểm tra import, group, type hỗ trợ và null semantics.
9. **Đang test service hay MVC controller?** Spring MVC 6.1+ có xử lý built-in khác.
10. **Có handler đã bắt và dịch lỗi?** `ConstraintViolationException` có thể đã được ánh xạ thành response hoặc bị catch.

Các phép kiểm thử nên có cả: external call tham số sai, external call hợp lệ, self-invocation, CGLIB final, JDK interface, new instance, và return-value constraint. Test method validation **phải lấy bean từ Spring context** nếu mục tiêu là kiểm chứng advice. Unit test tạo `new Service()` chỉ kiểm tra Java logic, không chứng minh được AOP.

### Sai lầm thường gặp

- Thêm `@Validated` nhiều lần mà không kiểm tra proxy boundary.
- Nghĩ class `final` và method `final` có hành vi giống nhau với JDK proxy và CGLIB.
- Bật `proxyTargetClass=true` rồi vẫn muốn inject interface proxy để khắc phục class final.
- Thêm constraint tham số ở method override mà không kiểm tra quy tắc Bean Validation inheritance.
- Tin rằng `@Valid` trên DTO làm mọi self-invocation tự validate.
- Dùng `AopContext.currentProxy()` như giải pháp mặc định, gây coupling khó bảo trì.
- Dựa vào thứ tự advice hoặc giả định validation luôn chạy trước transaction/caching khi chưa kiểm tra cấu hình order.
- Đặt mọi kiểm tra nghiệp vụ bắt buộc vào advice và để các đường gọi nội bộ không có guard.

## 11. Kết luận thực hành

Câu hỏi quan trọng khi method validation “không chạy” là: **“Lời gọi có đi qua proxy có khả năng intercept method này không?”**

- Qua proxy, method public/non-final tương thích: advice có thể thực thi.
- Qua `this`, private method, hoặc tạo object bằng `new`: không có tự động method validation từ Spring AOP tại boundary đó.
- Với CGLIB: class `final` không thể subclass, method `final` không thể advice.
- Với JDK proxy: method implementation `final` vẫn có thể được validate nếu được gọi qua interface proxy có metadata constraint hợp lệ.
- Với Spring MVC 6.1+: controller có thể dùng built-in method validation; cần đối chiếu theo pipeline HTTP thay vì chỉ áp mô hình service proxy.

Khi muốn ràng buộc được áp dụng ổn định, hãy tổ chức các bean theo đúng điểm giao tiếp, dùng phương thức/proxy phù hợp, và kiểm tra cả đường đi thành công lẫn đường bypass.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Java Bean Validation / Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — Proxying mechanisms, final methods và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — MVC Method Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Jakarta Bean Validation 3.0 — Method constraints, inheritance, executable validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 — Method validation reference](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
