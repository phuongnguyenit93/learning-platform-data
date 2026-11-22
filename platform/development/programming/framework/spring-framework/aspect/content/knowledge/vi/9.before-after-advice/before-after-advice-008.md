# Spring AOP: giới hạn của `@AfterThrowing` khi muốn phục hồi lỗi

## 1. Câu hỏi thực tế: ghi nhận lỗi có đồng nghĩa với xử lý lỗi?

Trong Spring Framework, `@AfterThrowing` là một loại advice thuộc `@AspectJ` style. Nó được gọi khi một **method execution được pointcut chọn kết thúc bất thường bằng cách ném exception** trong luồng Spring AOP proxy có thể intercept.

Điều quan trọng nhất: **`@AfterThrowing` có thể quan sát exception, nhưng không phải cơ chế bắt exception rồi trả một kết quả thành công thay cho target.**

```java
@Aspect
@Component
public class FailureAspect {
    @AfterThrowing(
        pointcut = "execution(* demo.recovery.CatalogService.find(..))",
        throwing = "ex"
    )
    public void onFailure(IllegalStateException ex) {
        System.out.println("[afterThrowing] " + ex.getMessage());
        // Kết thúc advice bình thường không làm exception của target biến mất.
    }
}
```

Đây là fragment; imports, service và chương trình hoàn chỉnh ở mục 7. Khi một caller gọi `find("DOWN")` **qua proxy**, method target ném `IllegalStateException`:

1. Spring AOP cho lời gọi đi đến target.
2. Target kết thúc bằng exception phù hợp với `@AfterThrowing`.
3. Advice nhận exception và có thể log, ghi metric, báo lỗi, làm tác vụ bổ trợ.
4. Nếu advice tự hoàn tất bình thường, **exception ban đầu vẫn tiếp tục được truyền ra caller**.
5. `onFailure(...)` là method Java `void`; nó không cung cấp cơ chế `return "DEFAULT"` để thay kết quả của `find(...)`.

Đừng dựa vào tên method như `doRecoveryActions` trong một số ví dụ tài liệu mà suy ra advice này tự chữa lành luồng exception. “Recovery action” có thể là **side effect** (ghi nhật ký/sự kiện/cảnh báo), không phải **biến lời gọi thất bại thành lời gọi thành công**.

Bài tập trung hoàn toàn vào **Spring Aspect, Spring AOP proxy và advice semantics**. Những kiến thức AOP chung hoặc AspectJ bytecode weaving không thuộc phạm vi.

## 2. Vị trí của `@AfterThrowing` trong luồng execution

```text
Caller gọi Spring bean proxy
           |
           v
    Spring AOP proxy
           |
   Advisor/pointcut match
           |
           v
    Target.find("DOWN")
           |
           +-- ném IllegalStateException
                      |
                      v
               @AfterThrowing
               - đọc exception
               - log / alert / metrics
               - chạy xong bình thường
                      |
                      v
              exception đi tiếp
                      |
                      v
              Caller nhận lỗi
```

Nếu method target **trả về bình thường**, `@AfterThrowing` không chạy vì không có exceptional method exit. Điều này đúng cả khi method có logic “xử lý lỗi” nội bộ, miễn cuối cùng nó vẫn return bình thường.

```java
public String find(String key) {
    try {
        return externalStore.load(key);
    } catch (IllegalStateException ex) {
        return "LOCAL-DEFAULT";
    }
}
```

Đoạn trên là fragment giả định có `externalStore`; vì exception được **target tự bắt rồi trả về bình thường**, một advice `@AfterThrowing` áp lên `find()` không được gọi cho execution này. Nếu cần quan sát mọi kết quả, xem `@AfterReturning`, `@After` hoặc `@Around` theo yêu cầu.

### “Lỗi” khác với “trả giá trị biểu thị lỗi”

Nếu target trả `null`, `Optional.empty()`, `Result.failure(...)` hoặc HTTP response báo lỗi **mà không ném exception ra khỏi execution được AOP quan sát**, `@AfterThrowing` sẽ không tự chạy. Nó quan sát **exceptional exit** của join point, không đọc business status trong return value.

## 3. Tại sao không thể dùng `@AfterThrowing` để nuốt exception?

Hãy so sánh ba tình huống sau.

### 3.1. Advice log exception rồi return bình thường

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void logFailure(IllegalStateException ex) {
    System.out.println("failed: " + ex.getMessage());
}
```

Thân advice return kiểu `void` và kết thúc bình thường. **Target đã ném exception**; Spring không nhận một giá trị thành công mới từ advice. Do đó caller vẫn nhận exception.

Không thể sửa bằng cách thay `void logFailure` thành một method `String logFailure(...)` rồi `return "DEFAULT"`. Đây không phải contract thay thế return value của `@AfterThrowing`. Spring dùng `@Around`, hoặc cơ chế xử lý lỗi ở tầng caller/service, khi cần phục hồi thật sự.

### 3.2. Advice tự ném exception khác

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void translate(IllegalStateException ex) {
    throw new CatalogUnavailableException("catalog offline", ex);
}
```

Đây là fragment, giả định `CatalogUnavailableException` là exception type thực tế của ứng dụng. Advice có thể làm một exception mới được truyền qua interceptor chain thay cho exception cũ. **Đây vẫn là kết thúc bằng lỗi**, không phải phục hồi thành công.

Nếu cần translation có ý nghĩa ổn định, hãy cân nhắc exception mapping ở service boundary hoặc infrastructure layer phù hợp. Trong Spring, các cơ chế như repository exception translation, transaction và web exception resolution có contract riêng; chúng không đồng nghĩa với `@AfterThrowing` có thể trả fallback.

**Lưu ý quan trọng:** exception mới do advice ném có thể che đi original exception nếu không giữ `cause`. Nếu buộc phải đổi exception, nên truyền original làm cause và chọn exception type tương thích signature/caller contract. Với JDK dynamic proxy, unchecked exception và checked exception không được khai báo có hành vi khác nhau.

### 3.3. Advice bắt exception bằng `try/catch` của chính nó

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void observe(IllegalStateException ex) {
    try {
        diagnosticService.record(ex);
    } catch (RuntimeException loggingFailure) {
        // Không để lỗi của subsystem quan sát che lỗi nghiệp vụ gốc.
    }
}
```

Đây là fragment sử dụng collaborator `diagnosticService` giả định. `try/catch` bên trong advice chỉ bắt exception phát sinh từ **chính thao tác được gọi trong advice** (ví dụ ghi metric thất bại). Nó không thể quay lại thời điểm trước khi target ném lỗi để “bắt lại” exception của target và thay đổi kết quả invocation.

Dù advice swallow lỗi của `diagnosticService.record(...)`, original exception của target **vẫn đi về caller**.

## 4. `throwing` vừa bind exception vừa giới hạn loại exception

Một declaration:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void onIllegalState(IllegalStateException ex) {
    System.out.println("state error: " + ex.getMessage());
}
```

có hai hiệu ứng liên quan:

1. `throwing = "ex"` liên kết giá trị exception với tham số advice tên `ex`.
2. Kiểu tham số `IllegalStateException` làm advice chỉ chạy khi exception thrown **có kiểu phù hợp** (bao gồm subclass phù hợp).

Một `IllegalArgumentException` cũng là `RuntimeException` nhưng **không phải** `IllegalStateException`, nên advice trên không nhận lỗi đó. Nếu muốn quan sát nhiều loại exception, có thể dùng `Throwable`:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex"
)
public void observeAll(Throwable ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Tuy nhiên, “mọi exception” ở đây vẫn là **những exceptional exits thuộc phạm vi join point/advice mà Spring AOP proxy quan sát được**. Nó không trở thành global exception handler của toàn JVM hoặc của tất cả framework interceptors.

### 4.1. Tên binding phải khớp chính xác

```java
@AfterThrowing(pointcut = "execution(* demo.recovery..*Service.*(..))",
               throwing = "failure")
public void logFailure(Throwable failure) {
    System.out.println(failure.getMessage());
}
```

`throwing="failure"` phải chỉ tới tham số `failure` của method advice. Nếu annotation dùng `throwing="ex"` nhưng method chỉ có tham số tên `failure`, Spring có thể lỗi khi tạo advice/resolve parameter binding.

Các dự án build không giữ Java parameter names có thể cần khai báo `argNames` rõ ràng, ví dụ:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "failure",
    argNames = "failure"
)
public void report(Throwable failure) {
    System.out.println(failure.getMessage());
}
```

Khi thêm `JoinPoint`, nó thường là tham số đầu tiên đặc biệt:

```java
@AfterThrowing(
    pointcut = "execution(* demo.recovery.CatalogService.find(..))",
    throwing = "ex",
    argNames = "ex"
)
public void report(JoinPoint joinPoint, Throwable ex) {
    System.out.println(joinPoint.getSignature().getName()
            + " failed: " + ex.getClass().getSimpleName());
}
```

Hai đoạn là phương án minh họa, không đồng thời dùng trong cùng ví dụ chạy nếu không muốn log lặp.

### 4.2. Advice không phải callback “catch mọi lỗi”

Tài liệu Spring lưu ý `@AfterThrowing` **không phải general exception-handling callback**. Cụ thể, advice này được định nghĩa để nhận exceptional exit từ **user-declared target method (join point)**, không phải cứ một `@After` hay `@AfterReturning` đi cùng ném exception thì mặc định `@AfterThrowing` sẽ được gọi để xử lý nó.

Với nhiều aspects và interceptor chain phức tạp, exception do một advisor khác ném có thể đi qua tầng bao ngoài khác nhau tùy precedence. Vì vậy không xây thiết kế dựa trên giả định “mọi exception ở bất kỳ đâu đều đến đây”. Hãy xác định cụ thể **method đang được advice**, **nguồn exception**, và **thứ tự advisors**.

## 5. Nếu cần thực sự phục hồi: cách làm phù hợp

### 5.1. Xử lý trong target hoặc caller

Nếu fallback là một phần nghiệp vụ của operation, có thể xử lý trực tiếp trong service method:

```java
public String findWithFallback(String key) {
    try {
        return externalStore.load(key);
    } catch (IllegalStateException ex) {
        return "DEFAULT";
    }
}
```

Đây là fragment giả định có `externalStore`. Lời gọi hoàn tất bình thường nên một `@AfterThrowing` trên `findWithFallback()` sẽ **không chạy** cho lỗi đã bị bắt bên trong. Cách này rõ ràng khi fallback thuộc nghiệp vụ và không cần một cross-cutting policy dùng chung.

Tương tự, caller có thể tự dùng `try/catch` bao quanh lời gọi Spring bean proxy và trả kết quả khác, miễn contract cho phép:

```java
try {
    return catalog.find(key);
} catch (IllegalStateException ex) {
    return "DEFAULT";
}
```

Đây là fragment bên trong một method trả `String`; `catalog` là Spring-managed dependency. Khi method target đã ném lỗi, `@AfterThrowing` bên trong proxy thường có cơ hội quan sát lỗi trước khi exception đi đến caller bắt, còn caller chịu trách nhiệm quyết định fallback.

### 5.2. Dùng `@Around` để bao quanh và điều khiển `proceed()`

Trong Spring AOP, `@Around` nhận `ProceedingJoinPoint`; nó có quyền:

- Gọi `proceed()` để thực thi phần còn lại của chain/target.
- Bắt exception ném ra từ `proceed()`.
- Trả về một giá trị fallback **tương thích với kiểu trả về của method**.
- Nếu requirement cho phép, bỏ qua target, retry theo chính sách rõ ràng hoặc thay return value.

```java
@Around("execution(* demo.recovery.CatalogService.findWithFallback(..))")
public Object recover(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "DEFAULT";
    }
}
```

Nếu method `findWithFallback(..)` trả `String`, `"DEFAULT"` là giá trị hợp lệ. Nhưng nếu return type là primitive `int`, `void`, `CompletableFuture<T>` hay một domain-specific result, fallback phải phù hợp contract, nếu không có thể lỗi kiểu/unboxing hoặc làm hỏng semantics.

**Không nhầm `@Around` catch exception với việc transaction tự phục hồi:** Nếu transaction interceptor ở bên trong advice đã đánh dấu rollback-only, bắt exception phía ngoài rồi trả bình thường không có nghĩa transaction có thể commit. Tương tự, trong reactive/asynchronous methods, lỗi có thể xuất hiện trong publisher/future **sau khi method đã return**; `@AfterThrowing` ở method execution boundary không đương nhiên nhận lỗi bất đồng bộ đó.

### 5.3. Chọn retry hay fallback với chính sách rõ ràng

Một retry chỉ hợp lý khi operation **an toàn để thực hiện lại**, có timeout/backoff/circuit breaker phù hợp và không gây duplicate side effects. Không tự gọi `proceed()` lặp nhiều lần trong `@AfterThrowing` vì nó không được cấp `ProceedingJoinPoint`. Nếu cần retries, cân nhắc Spring Retry hoặc Spring Framework resilience facilities phù hợp thay vì viết mã thủ công thiếu safeguards.

Với một lệnh ghi tiền, đặt hàng hay gửi email, retry vô hạn hoặc trả fallback giả “thành công” có thể nguy hiểm hơn ném lỗi. Chọn policy theo **contract nghiệp vụ**; chỉ dùng `@Around` khi có lý do rõ ràng và kiểm thử.

## 6. Bảng so sánh các loại advice trong trường hợp lỗi

| Advice | Khi nào chạy trong Spring AOP? | Có thể làm gì với lỗi? | Có thay exception thành return thành công? |
| --- | --- | --- | --- |
| `@Before` | Trước method execution được proxy intercept | Kiểm tra/log trước; tự ném exception để ngăn execution | Không theo cơ chế `proceed()`; không có return của target |
| `@AfterReturning` | Khi execution kết thúc bình thường | Quan sát return value | Không dùng để return một reference hoàn toàn mới thay target |
| `@AfterThrowing` | Khi execution kết thúc bằng exception phù hợp | Log, metric, alert, quan sát exception; có thể ném exception khác | **Không** — không swallow lỗi hoặc return fallback |
| `@After` | Khi execution kết thúc theo finally semantics | Cleanup bất kể thành công/thất bại | Không phải cơ chế recovery |
| `@Around` | Bao quanh method execution | Catch exception từ `proceed()`, retry/bỏ qua nếu phù hợp, return fallback | **Có thể** nếu contract cho phép và chain/transaction phù hợp |

Ví dụ một advice `@AfterThrowing` ghi log rồi hoàn tất không làm lời gọi trở nên “successful”; để trả thành công cần một điểm **bao quanh** exceptional execution hoặc xử lý lỗi ở caller/target phù hợp.

## 7. Dự án Java 17 + Spring Framework 6.2 chạy được

Ví dụ Spring Framework thuần, không dùng Spring Boot. Hai lời gọi được cố tình tách trên **hai target methods khác nhau** để quan sát rõ:

- `find()` có `@AfterThrowing` cho `IllegalStateException`: advice log nhưng **caller vẫn nhận exception**.
- `findWithFallback()` có `@Around`: advice catch `IllegalStateException` và trả `"DEFAULT"`.
- `findFromInside()` gọi `this.find()` từ target: **bypass Spring proxy**, dù `find()` có pointcut match, nên `@AfterThrowing` **không chạy** cho lời gọi nội bộ.
- `find("OK")` thành công: `@AfterThrowing` không chạy.

### 7.1. Cấu trúc thư mục

```text
spring-after-throwing-recovery/
├── pom.xml
└── src/main/java/demo/recovery/
    ├── AppConfig.java
    ├── CatalogOperations.java
    ├── CatalogService.java
    ├── RecoveryAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-after-throwing-recovery</artifactId>
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
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. `AppConfig.java`

```java
package demo.recovery;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` tìm các component trong package `demo.recovery`. `@EnableAspectJAutoProxy` bật Spring AOP auto-proxy creator. Với `CatalogService implements CatalogOperations` và `proxyTargetClass=false`, ví dụ sử dụng **JDK dynamic proxy**.

### 7.4. `CatalogOperations.java`

```java
package demo.recovery;

public interface CatalogOperations {
    String find(String key);
    String findWithFallback(String key);
    String findFromInside(String key);
}
```

Cả ba business methods đều được công bố qua interface để caller có thể gọi trên JDK proxy.

### 7.5. `CatalogService.java`

```java
package demo.recovery;

import org.springframework.stereotype.Service;

@Service
public class CatalogService implements CatalogOperations {
    @Override
    public String find(String key) {
        System.out.println("[target] find " + key);
        if ("DOWN".equals(key)) {
            throw new IllegalStateException("storage unavailable");
        }
        return "ITEM-" + key;
    }

    @Override
    public String findWithFallback(String key) {
        System.out.println("[target] findWithFallback " + key);
        if ("DOWN".equals(key)) {
            throw new IllegalStateException("storage unavailable");
        }
        return "ITEM-" + key;
    }

    @Override
    public String findFromInside(String key) {
        System.out.println("[target] findFromInside " + key);
        try {
            return this.find(key); // Không đi qua Spring AOP proxy.
        } catch (IllegalStateException ex) {
            System.out.println("[target] internal fallback");
            return "LOCAL-DEFAULT";
        }
    }
}
```

Service minh họa ba đường execution:

- `find` có thể ném `IllegalStateException` ra ngoài target.
- `findWithFallback` bản thân target không phục hồi; việc catch sẽ do `@Around` đảm nhận.
- `findFromInside` tự catch lỗi của `this.find()`. Lời gọi đó không đi qua proxy, nên `@AfterThrowing` trên `find()` không nhận nó.

### 7.6. `RecoveryAspect.java`

```java
package demo.recovery;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class RecoveryAspect {
    @AfterThrowing(
        pointcut = "execution(* demo.recovery.CatalogService.find(..))",
        throwing = "ex"
    )
    public void onFindFailure(IllegalStateException ex) {
        System.out.println("[afterThrowing] " + ex.getMessage());
    }

    @Around("execution(* demo.recovery.CatalogService.findWithFallback(..))")
    public Object recoverFind(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (IllegalStateException ex) {
            System.out.println("[around] recovered " + ex.getMessage());
            return "DEFAULT";
        }
    }
}
```

Hai advices có **pointcuts tách biệt**, không cạnh tranh precedence trên cùng invocation:

- `@AfterThrowing` áp lên `find(..)`, log lỗi và kết thúc bình thường; lỗi **vẫn truyền tới caller**.
- `@Around` áp lên `findWithFallback(..)`, catch exception từ `proceed()` và trả `"DEFAULT"` (hợp lệ vì method trả `String`).
- Cả hai chỉ áp dụng nếu method call đi qua Spring proxy.
- `@Component` làm aspect được đăng ký Spring bean; `@Aspect` một mình chưa đủ.

### 7.7. `Main.java`

```java
package demo.recovery;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogOperations catalog =
                    context.getBean(CatalogOperations.class);

            System.out.println("jdkProxy="
                    + AopUtils.isJdkDynamicProxy(catalog));

            System.out.println("success=" + catalog.find("OK"));

            try {
                catalog.find("DOWN");
            } catch (IllegalStateException ex) {
                System.out.println("caller caught=" + ex.getMessage());
            }

            System.out.println("fallback="
                    + catalog.findWithFallback("DOWN"));
            System.out.println("internal="
                    + catalog.findFromInside("DOWN"));
            System.out.println("fallbackSuccess="
                    + catalog.findWithFallback("OK"));
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` bằng Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.recovery.Main
```

Các dòng `System.out` theo thứ tự trong ví dụ (không tính log Maven/Spring riêng nếu có):

```text
jdkProxy=true
[target] find OK
success=ITEM-OK
[target] find DOWN
[afterThrowing] storage unavailable
caller caught=storage unavailable
[target] findWithFallback DOWN
[around] recovered storage unavailable
fallback=DEFAULT
[target] findFromInside DOWN
[target] find DOWN
[target] internal fallback
internal=LOCAL-DEFAULT
[target] findWithFallback OK
fallbackSuccess=ITEM-OK
```

### 7.8. Phân tích kết quả

| Thao tác | Target | `@AfterThrowing` | `@Around` | Caller nhận |
| --- | --- | --- | --- | --- |
| `catalog.find("OK")` | Return `"ITEM-OK"` | Không chạy | Không áp dụng | `"ITEM-OK"` |
| `catalog.find("DOWN")` | Ném `IllegalStateException` | Log `storage unavailable` | Không áp dụng | **Exception** |
| `catalog.findWithFallback("DOWN")` | Ném exception | Không match pointcut này | Catch và return `"DEFAULT"` | **Giá trị thành công `"DEFAULT"`** |
| `catalog.findFromInside("DOWN")` | Bắt lỗi nội bộ từ `this.find()` | Không thấy nested `find` vì self-invocation | Không áp dụng | `"LOCAL-DEFAULT"` |
| `catalog.findWithFallback("OK")` | Return `"ITEM-OK"` | Không match | Trả nguyên kết quả `proceed()` | `"ITEM-OK"` |

**Đọc hai dòng quan trọng:**

```text
[afterThrowing] storage unavailable
caller caught=storage unavailable
```

Chúng chứng minh advice đã **quan sát lỗi** nhưng chưa **phục hồi**. Ngược lại:

```text
[around] recovered storage unavailable
fallback=DEFAULT
```

là một example về **catch + return fallback** trong around advice.

Không có lời gọi bất đồng bộ, không có transactions và hai advices chọn hai method khác nhau, nên ví dụ không phụ thuộc thứ tự chạy giữa những advices khác nhau trên cùng một join point.

## 8. Vì sao `@AfterThrowing` có thể không chạy dù đã xảy ra lỗi?

### 8.1. Target catch lỗi rồi return bình thường

```java
public String find(String key) {
    try {
        return gateway.load(key);
    } catch (IllegalStateException ex) {
        return "CACHED";
    }
}
```

Fragment giả định có `gateway`. Method execution `find` kết thúc bình thường, nên `@AfterThrowing` **không kích hoạt** cho exception đã bị target bắt. Nếu muốn advice xử lý lỗi xảy ra **bên trong method đã được catch**, phải đổi nơi đặt boundary hoặc event/reporting contract; Spring proxy không có khả năng theo dõi mọi lệnh `throw` được catch trong target.

### 8.2. Ngoại lệ không khớp kiểu tham số

```java
@AfterThrowing(pointcut = "execution(* demo.recovery..*Service.*(..))",
               throwing = "ex")
public void observe(IllegalStateException ex) {
    // Chỉ bắt các exception phù hợp kiểu IllegalStateException.
}
```

Nếu method ném `IllegalArgumentException`, advice này không nhận. Muốn quan sát nhiều loại, cân nhắc `Throwable`, nhưng tránh log nhạy cảm hoặc đánh đồng mọi exception với lỗi nghiệp vụ.

### 8.3. Lời gọi không đi qua Spring AOP proxy

```java
new CatalogService().find("DOWN");
```

Đây là object tự tạo, không phải Spring bean proxy; advice của Spring AOP **không chạy**. Tương tự, self-invocation `this.find("DOWN")` từ target không tạo interception mới.

### 8.4. Pointcut sai signature, package hoặc bean

Một expression `execution(* demo.other.CatalogService.find(..))` không khớp target ở `demo.recovery`. Hoặc class aspect chỉ có `@Aspect` nhưng chưa được đăng ký Spring bean qua `@Component`/`@Bean`. Khi đó Spring không có advisor đúng để chạy `@AfterThrowing`.

### 8.5. Phương thức không được proxy intercept

Với JDK proxy, method phải thuộc các public interface methods mà proxy công bố. Với CGLIB, `private`/`final` methods không thể được advice theo cơ chế override và `final class` không thể subclass. `static` method không được gọi qua instance proxy.

### 8.6. Exception xuất hiện sau khi method return

Một method trả `CompletableFuture<T>` hoặc reactive `Mono<T>` có thể **return bình thường** một wrapper trong khi lỗi chỉ xảy ra khi future hoàn tất hoặc publisher được subscribe. `@AfterThrowing` cho method execution thông thường không tự biết về mọi lỗi xảy ra sau thời điểm return. Muốn xử lý lỗi async/reactive, dùng API thích hợp như completion handlers, Reactor error operators hoặc hỗ trợ framework tương ứng.

### 8.7. Một advice khác đã phục hồi lỗi trước khi exception tới điểm quan sát

Khi nhiều advisors cùng áp dụng, một `@Around` có thể bắt exception từ phần chain bên trong và trả bình thường; advisor bên ngoài chỉ thấy kết quả bình thường. Tùy precedence, exception có thể đã được một advice bên trong quan sát trước khi outer advice recover. Không đưa ra quy tắc tuyệt đối như “`@AfterThrowing` luôn chạy trước/luôn chạy sau `@Around`” nếu chưa xét cụ thể advisor ordering.

## 9. Giới hạn khi kết hợp với transactions, retries và web errors

### 9.1. `@Transactional` và rollback

Spring declarative transaction thường được triển khai bằng interceptor. Nếu method ném exception đi qua transaction interceptor, Spring có thể đánh dấu rollback theo quy tắc rollback, rồi một outer `@Around` mới catch exception và trả fallback. **Catch phía ngoài không làm rollback flag tự biến mất.**

Nếu catch trước khi exception vượt qua transaction boundary, transaction interceptor có thể chỉ thấy return bình thường; tuy nhiên transaction đã có thể bị marked rollback-only ở những luồng khác. Khi cần rollback/recovery rõ ràng, đặt transaction boundary và policy thứ tự advisor có chủ đích, thêm integration tests kiểm tra trạng thái commit/rollback thật.

Đặc biệt, không dùng một `@AfterThrowing` chỉ để tuyên bố “đã xử lý lỗi nên transaction sẽ commit”. Nó chỉ là advice theo exceptional execution và không khôi phục giao dịch đã rollback.

### 9.2. Retry: rủi ro side effects

Nếu muốn tự động gọi lại operation, `@AfterThrowing` không có `ProceedingJoinPoint` nên không điều khiển lại target execution. Dùng một cơ chế retry phù hợp (ví dụ Spring Retry khi dự án dùng) hoặc `@Around` nhưng bảo đảm:

- operation là idempotent hoặc có cơ chế chống trùng;
- giới hạn số lần, backoff, timeout;
- logging/metrics tránh trùng lặp khó kiểm soát;
- transaction boundaries phù hợp với từng lần thử;
- exception cuối cùng có contract rõ ràng.

Đừng tự động retry một method chuyển tiền/ghi đơn hàng chỉ vì nhìn thấy exception trong aspect.

### 9.3. HTTP exception response không phải Spring AOP recovery

Trong Spring MVC, một lỗi từ service có thể được xử lý ở ranh giới web bằng `@ExceptionHandler`/`@ControllerAdvice` hoặc các cơ chế xử lý exception khác. Điều đó chuyển **exception thành HTTP response** cho client, nhưng không có nghĩa `@AfterThrowing` của service đã return fallback cho service caller.

Các trách nhiệm này khác nhau:

- Spring AOP `@AfterThrowing`: quan sát **exceptional method execution**.
- Spring MVC exception resolver: chuyển lỗi ứng dụng thành **web response** thích hợp.
- Service/caller/`@Around`: có thể quyết định **domain fallback** nếu contract cho phép.

## 10. Checklist chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| Advice in log lỗi nhưng caller vẫn nhận exception | Đây là hành vi đúng của `@AfterThrowing` | Nếu cần fallback, xử lý ở caller/target hoặc `@Around` |
| Thử `return "DEFAULT"` trong after-throwing method | Không phải contract thay return của advice này | Dùng `@Around` và kiểu return đúng |
| Advice ném exception khác thì không còn thấy lỗi gốc | Exception của advice có thể che lỗi ban đầu | Truyền original làm cause, giữ exception contract |
| `@AfterThrowing` không chạy với `IllegalArgumentException` | Tham số bind kiểu `IllegalStateException` lọc exception | Sửa kiểu ràng buộc hoặc xử lý exception tương ứng |
| `@AfterThrowing` không chạy khi target đã catch | Execution return bình thường | Di chuyển error-handling boundary |
| `@AfterThrowing` không chạy ở `this.method()` | Self-invocation bypass proxy | Tách method sang bean khác và inject |
| `@AfterThrowing` không chạy trên object `new` | Đối tượng ngoài Spring container | Dùng Spring-managed bean |
| Advice không thấy exception từ một `@AfterReturning` khác | `@AfterThrowing` không phải global exception callback | Xét đúng join point/source/ordering |
| `@AfterThrowing` không thấy lỗi của `CompletableFuture` | Method đã return bình thường trước lúc future fail | Dùng completion/error handlers |
| `@Around` trả fallback nhưng transaction vẫn rollback | Transaction boundary đã xử lý exception hoặc rollback-only | Thiết kế advisor/transaction ordering và test rollback |
| Dùng `Throwable` nhưng log lỗi bị lặp | Nhiều aspects, retries, nhiều proxy boundaries | Phân định một nơi log/observability, tránh double count |
| `@AfterThrowing` chạy nhầm phương thức | Pointcut quá rộng hoặc bean target khác | Thu hẹp expression, kiểm tra bean/target |
| Không có Spring proxy | Aspect/target chưa là Spring beans, auto-proxy chưa bật | Kiểm tra `@Aspect @Component` và `@EnableAspectJAutoProxy`/Boot AOP |

### Quy trình kiểm tra có hệ thống

1. Xác minh target và aspect cùng được Spring quản lý; hạ tầng Spring AOP đã kích hoạt.
2. Trên reference thực tế từ DI/context, xác minh `AopUtils.isAopProxy(...)`.
3. Xác minh method được caller gọi qua proxy, không phải `this` hoặc object tạo bằng `new`.
4. Kiểm tra pointcut và kiểu exception của `throwing` binding.
5. Phân biệt exception **thoát khỏi target method** với exception đã được target catch hoặc async error sau return.
6. Kiểm tra `@AfterThrowing` có chỉ log hay có ném exception mới.
7. Nếu muốn caller nhận fallback thành công, chọn điểm xử lý exception phù hợp: target, caller hoặc `@Around`.
8. Với transactions, retries, async, web exceptions, test behavior ở boundary tương ứng, không suy đoán từ một dòng log advice.

## 11. Câu hỏi tự đánh giá

**1. `@AfterThrowing` log exception rồi return bình thường; caller nhận gì?** Caller vẫn nhận exception từ target (trừ khi một interceptor ở tầng khác xử lý nó). Advice không tự chuyển exception thành return thành công.

**2. Có thể khai báo method `@AfterThrowing` trả `String` để thay return value không?** Không. Advice này không có contract điều khiển `proceed()`/return kết quả của join point; dùng `@Around` khi cần phục hồi.

**3. Vì sao `@AfterThrowing(..., throwing="ex")` với `IllegalStateException ex` không chạy khi target ném `IllegalArgumentException`?** Vì kiểu exception tham số advice giới hạn matching.

**4. Nếu method target tự catch và return `"CACHED"`, `@AfterThrowing` trên method đó có chạy không?** Không. Execution đã kết thúc bình thường; exception không thoát ra ngoài join point.

**5. Sự khác biệt giữa `@Around` và `@AfterThrowing` về recovery?** `@Around` có thể catch exception từ `proceed()` rồi trả fallback hợp lệ; `@AfterThrowing` chủ yếu quan sát exceptional execution và không tự chuyển thành success.

**6. Nếu `@AfterThrowing` ném exception mới, đó có phải recovery không?** Không. Caller vẫn nhận lỗi, dù loại lỗi có thể khác; cần giữ original cause khi chuyển đổi exception.

**7. Tại sao self-invocation `this.find()` không được `@AfterThrowing` chặn?** Lời gọi không qua Spring AOP proxy, dù pointcut có thể match method signature.

**8. `@AfterThrowing` có tự bắt mọi exception của một `@AfterReturning` đi cùng không?** Không nên giả định. Spring nêu rõ nó không phải callback xử lý exception tổng quát; cần xét nguồn exception và advisor chain.

**9. Một `CompletableFuture` thất bại sau khi method đã return sẽ tự kích hoạt `@AfterThrowing` của method đó không?** Không cho một method execution đã trả future bình thường; cần error-handling mechanism của async/future.

## Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice, After Throwing Advice và Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Concepts: After Throwing Advice](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring Framework — Spring AOP Advice API (Throws Advice)](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html)
- [Spring Framework — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
