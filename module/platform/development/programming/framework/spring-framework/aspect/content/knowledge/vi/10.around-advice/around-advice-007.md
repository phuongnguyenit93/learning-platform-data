# Bao quanh đường thành công và ngoại lệ bằng try/catch/finally trong Spring @Around

## 1. Vấn đề: một invocation có thể return, throw hoặc được phục hồi

Khi một Spring service được bao bởi `@Around` advice, lời gọi đến method có thể có các kết cục khác nhau:

- **Normal return:** method thực hiện xong, trả một giá trị, kể cả `null`.
- **Exceptional completion:** method hoặc một interceptor phía trong ném ngoại lệ ra ngoài.
- **Recovered completion:** phần bên trong có ném ngoại lệ, nhưng `@Around` bắt và chủ động trả một giá trị fallback hợp lệ.
- **Early return:** `@Around` quyết định không gọi `proceed()`; target và các interceptor phía trong không được chạy ở invocation đó.

Dùng `try/catch/finally` đúng cách trong `@Around` giúp ta **quan sát từng đường đi, giữ nguyên kết quả/exception theo mặc định và luôn thực hiện bước cleanup** khi execution đi ra khỏi advice theo quy tắc Java thông thường.

Đây là kiến thức **Spring Aspect**: `@Around` nằm trong interceptor chain của **Spring AOP proxy**, không phải một khối `try` bao quanh mọi lời gọi Java ở mọi nơi trong chương trình.

### Quy tắc cốt lõi

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();

    try {
        Object result = pjp.proceed();
        return result;
    } catch (Throwable failure) {
        throw failure;
    } finally {
        long duration = System.nanoTime() - started;
        // Ghi nhận duration hoặc dọn trạng thái do advice quản lý.
    }
}
```

Đây là **snippet minh họa**, cần đặt trong Spring `@Aspect` bean có các import và cấu hình AOP. Nó thể hiện ba việc quan trọng:

1. `pjp.proceed()` yêu cầu **phần còn lại của Spring interceptor chain** tiếp tục; chỉ khi chain tiến tới target thì method nghiệp vụ mới thật sự chạy.
2. `catch` có thể quan sát và xử lý ngoại lệ thoát ra từ `proceed()`; nếu không có chủ đích chuyển kết quả, hãy **throw lại** exception.
3. `finally` chạy khi control flow đi ra khỏi `try` qua return/throw, bất kể caller cuối cùng nhận normal value hay exception. Nó không nhất thiết chỉ chạy ở đường lỗi.

**Phạm vi:** Spring Framework, Spring `@AspectJ` annotation style, proxy-based AOP, `ProceedingJoinPoint` và các kết cục do caller của proxy nhìn thấy. Không mở rộng sang AspectJ compile-time weaving hoặc các join point không được Spring AOP hỗ trợ như constructor/field access.

## 2. Sơ đồ luồng đúng của Spring @Around

```text
Client
  |
  v
Spring AOP proxy
  |
  v
@Around advice
  |
  +-- Code trước try/proceed
  |
  +-- try {
  |      pjp.proceed() ---------> Các advisors phía trong
  |                                  |
  |                                  v
  |                              Target method
  |                                  |
  |                         +--------+--------+
  |                         |                 |
  |                      return              throw
  |                         |                 |
  |                         v                 v
  |                   try nhận result   catch nhận exception
  |                         |                 |
  |                   return result     rethrow hoặc fallback
  |                         |                 |
  |                         +--------+--------+
  |                                  |
  +-- finally: dọn trạng thái / ghi tổng thời gian
  |
  v
Caller nhận value hoặc exception do advice đưa ra ngoài
```

Có hai tầng kết cục cần phân biệt:

- **Kết cục của `proceed()`:** phần interceptor chain phía trong trả normal result hoặc ném exception.
- **Kết cục của invocation nhìn từ bên ngoài advice:** có thể khác nếu `catch` trả fallback, advice đổi result, hoặc advice tự throw exception mới.

Chẳng hạn, target ném `IllegalStateException` nhưng `@Around` nằm ngoài bắt exception và return `"FALLBACK"`: caller có thể **không nhận exception**, dù target đã thất bại. Nếu Spring transaction interceptor nằm bên trong và đã xử lý rollback thì việc return fallback ở advice phía ngoài **không hoàn tác rollback**. Ngược lại, khi transaction interceptor nằm ngoài và chỉ thấy normal return, trạng thái rollback có thể khác. Vì vậy xử lý exception trong aspect không chỉ là quyết định ghi log.

### Spring proxy là điều kiện bắt buộc

`@Around` không chạy nếu:
- Bạn tự tạo target bằng `new Service()` ngoài Spring.
- Target gọi `this.otherMethod()`: self-invocation đi thẳng vào target.
- Method không khớp pointcut hoặc target không được AOP proxy.
- Method không thể được proxy intercept vì ràng buộc visibility/type, như `private`/`final` trên CGLIB.
- Một interceptor **phía ngoài** short-circuit trước khi đi tới `@Around` của bạn.

Vì thế, khi debug “finally không chạy”, kiểm tra **advice có được gọi ngay từ đầu hay không**, không chỉ kiểm tra cú pháp `finally`.

## 3. Vai trò chính xác của try, catch và finally

### 3.1. try: chạy phần chain và giữ kết quả

```java
Object result = pjp.proceed();
return result;
```

`proceed()` không đơn giản là gọi một phương thức Java thông thường; trong Spring AOP, nó đi tiếp qua các advisor còn lại rồi mới tới target nếu không có interceptor short-circuit.

Ở đường normal:
- `proceed()` trả về giá trị tương thích target method contract.
- `return result` giữ nguyên reference mà caller của proxy nhìn thấy.
- `finally` vẫn chạy **trước khi** caller nhận kết quả.

Ở đường exceptional:
- `proceed()` ném exception.
- Các statement nằm sau nó trong `try` không được thực hiện.
- Java tìm `catch` phù hợp; `finally` vẫn chạy khi thoát phạm vi.

### 3.2. catch: phân loại exception và chủ động quyết định

```java
try {
    return pjp.proceed();
} catch (IOException ex) {
    // Trường hợp failure từ I/O.
    throw ex;
} catch (RuntimeException ex) {
    // Trường hợp unchecked failure.
    throw ex;
}
```

Đây là snippet cần import `java.io.IOException` và đặt trong `@Around` method `throws Throwable`. Chọn kiểu catch là lựa chọn có ý nghĩa:
- `catch(IOException ex)` chỉ bắt `IOException` hoặc subtype.
- `catch(RuntimeException ex)` bắt các runtime exceptions.
- `catch(Throwable ex)` có thể bắt cả `Error` và mọi throwable; rất rộng nên phù hợp với quan sát + **rethrow nguyên vẹn**, không phù hợp để nuốt tất cả lỗi.

**Thông lệ cho tracing/metrics:** nếu không có chính sách phục hồi thực sự, `catch` chỉ ghi nhận exception rồi `throw ex`; giữ nguyên loại exception, stack trace và nguyên nhân. Không tự đổi thành `new RuntimeException(ex)` vì thay đổi hợp đồng lỗi.

### 3.3. finally: có chạy ngay cả khi return trong catch không?

Có. Java thực thi `finally` khi đi ra khỏi khối `try`/`catch` bằng `return` hoặc `throw` trong những điều kiện unwind thông thường.

```java
try {
    return pjp.proceed();
} catch (IllegalStateException ex) {
    return "FALLBACK";
} finally {
    System.out.println("cleanup");
}
```

Trong trường hợp `proceed` throw `IllegalStateException`, advice vào `catch`, chọn giá trị `"FALLBACK"`, **chạy `finally`**, rồi mới return kết quả ấy cho caller.

### 3.4. Đường nào chạy callback nào?

| Tình huống trong `@Around` | `catch` | `finally` | Caller thấy |
| --- | --- | --- | --- |
| `proceed()` return `"OK"` | Không | Có | `"OK"` |
| `proceed()` return `null` | Không | Có | `null` |
| `proceed()` throw `IOException`, advice rethrow | Catch phù hợp | Có | `IOException` |
| `proceed()` throw `IllegalStateException`, advice rethrow | Catch phù hợp | Có | `IllegalStateException` |
| `proceed()` throw `IllegalStateException`, advice return fallback | Catch phù hợp | Có | Giá trị fallback |
| Advice return ngay trong `try` mà không gọi `proceed()` | Không | Có | Kết quả do advice tạo |
| Advice throw ngay trong `try` trước `proceed()` | Catch phù hợp nếu có | Có | Exception hoặc fallback |
| Interceptor phía ngoài không gọi tiếp vào advice này | Không vào advice | Không | Tùy interceptor bên ngoài |

Đây là các kết quả **theo vị trí advice đang xét**. Nếu có advice khác ở ngoài và bên trong, chúng có thể nhìn thấy kết cục khác nhau.

## 4. Công thức đo thời gian và logging đúng

### 4.1. Dùng finally, tránh chỉ log sau proceed

Cách thiếu sót:

```java
long started = System.nanoTime();
Object result = pjp.proceed();
System.out.println("elapsed=" + (System.nanoTime() - started));
return result;
```

Nếu `proceed()` ném exception, dòng ghi duration bị bỏ qua. Lúc đó metrics chỉ bao gồm normal invocations; những lời gọi thất bại (thường mất nhiều thời gian hơn) lại vắng mặt.

Cách đúng:

```java
long started = System.nanoTime();
try {
    return pjp.proceed();
} finally {
    long elapsed = System.nanoTime() - started;
    System.out.println("elapsedNs=" + elapsed);
}
```

Nếu cần phân biệt normal/failed cũng có thể thêm biến local hoặc `catch`:

```java
long started = System.nanoTime();
boolean failed = false;
try {
    return pjp.proceed();
} catch (Throwable ex) {
    failed = true;
    throw ex;
} finally {
    record(pjp.getSignature().getName(),
           failed,
           System.nanoTime() - started);
}
```

Ở đây `record(...)` là hàm giả định, không phải API Spring; nó phải được định nghĩa trong aspect hoặc helper phù hợp. **Dùng biến local per-invocation**, không dùng một field singleton mutable như `boolean failed` trong Spring `@Aspect`; cùng một aspect instance có thể được nhiều request threads dùng đồng thời.

### 4.2. Đo ở phía ngoài hay bên trong cache/transaction?

Giả sử cùng method được advice bởi logging `@Around` và caching:

```text
Client -> logging @Around -> cache interceptor -> target
```

Nếu `@Around` nằm ngoài cache, nó có thể ghi nhận cả cache hit mà không cần target chạy. Nếu cache interceptor nằm ngoài, cache hit có thể trả kết quả ngay và **không đi vào logging advice** phía trong.

Tương tự, duration ở ngoài transaction interceptor có thể bao gồm thời gian xử lý transaction; duration ở trong có thể chỉ đo một phạm vi hẹp. Vì thế phải đặt tên metric đúng boundary, ví dụ `service_proxy_duration` khác với `target_method_duration`.

Không tự kết luận “@Around luôn ngoài transaction/cache” nếu chưa xác định **advisor precedence** bằng `@Order`/`Ordered` hoặc cấu hình order tương ứng.

## 5. Catch rồi rethrow: quan sát lỗi mà không đổi hợp đồng

Một observability aspect nên có chính sách mặc định:

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (Throwable ex) {
        System.out.println("errorType="
            + ex.getClass().getSimpleName());
        throw ex;
    } finally {
        System.out.println("invocationFinished");
    }
}
```

Ví dụ trên có thể quan sát cả checked và unchecked exceptions từ `proceed()`. Không nên làm như sau:

```java
catch (Throwable ex) {
    System.out.println("error");
    return null;
}
```

vì hành vi này **nuốt mọi throwable**, bao gồm cả lỗi hệ thống nghiêm trọng, và trả `null` dù caller có thể mong primitive hay kết quả bắt buộc khác.

### Checked và unchecked exceptions trong Spring proxy

- `IOException` là checked exception; interface/target method nên khai báo `throws IOException` nếu nó là phần hợp đồng.
- `IllegalStateException` là unchecked; không cần `throws`.
- Với JDK dynamic proxy, một checked exception không thuộc interface method `throws` có thể bị bao bởi `UndeclaredThrowableException` khi ra khỏi proxy. Đây là một lý do nên giữ đúng hợp đồng Java và kiểm tra nguyên nhân exception khi dùng JDK proxy.
- Không nhầm việc `@AfterThrowing` có thể bind `Throwable` với việc mọi checked exception sẽ luôn ra caller dưới dạng type gốc trong mọi thiết kế proxy.

## 6. Catch rồi return fallback: khi nào chính đáng?

Một fallback có thể hợp lệ khi:
- Method là **read-only query** và cho phép trả dữ liệu dự phòng.
- Một remote service tạm mất kết nối nhưng nghiệp vụ có giá trị cache an toàn.
- Caller contract cho phép giá trị thay thế và có cách đánh dấu nó không phải kết quả mới nhất.
- Đã có chính sách loại ngoại lệ được phép phục hồi, thời hạn dữ liệu, logging và cảnh báo.

Ví dụ:

```java
@Around("execution(public String com.example.app.service.LookupService.lookup(..))")
public Object fallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "NOT_AVAILABLE";
    } finally {
        System.out.println("lookupFinished");
    }
}
```

Đây là đoạn minh họa **chỉ hợp lệ cho một method trả `String` khi nghiệp vụ chấp nhận `NOT_AVAILABLE`**. Nếu method trả `int`, trả string sẽ vi phạm return contract. Nếu method cập nhật database hoặc chuyển tiền, nuốt exception có thể khiến caller tưởng thao tác đã thành công.

Một fallback có chủ đích nên được đo thành hai chỉ số khác nhau:
- `inner_failure_count`: phần `proceed()` đã ném exception.
- `proxy_normal_return_count`: advice đã đổi exception thành normal return cho caller.

Chúng có thể **cùng tăng ở một invocation**. Không dùng một nhãn success/failure đơn giản mà bỏ mất sự khác biệt này.

### Điều gì xảy ra với @AfterReturning và @AfterThrowing?

Trong một Spring AOP proxy, những advice ở **vị trí khác nhau** nhìn thấy outcome tại vị trí của chúng trong interceptor chain:

```text
Outer @AfterReturning / @AfterThrowing
         |
         v
Fallback @Around
         |
         v
Inner @AfterReturning / @AfterThrowing
         |
         v
Target
```

Khi target throw, inner `@AfterThrowing` có thể thấy exception. Nếu fallback around bắt nó và return, outer `@AfterReturning` có thể thấy normal completion thay vì exception.

Do đó không thể phát biểu “cứ target throw thì mọi `@AfterThrowing` đều chạy”; phải nói rõ advisor nằm ở đâu và liệu chain có được đi qua hay không.

### Không dùng return trong finally

Ví dụ sau là anti-pattern nghiêm trọng:

```java
try {
    return pjp.proceed();
} finally {
    return "OVERRIDDEN";
}
```

`return` trong `finally` **ghi đè** cả kết quả return và exception đang được truyền ra. Nó có thể nuốt `IOException` hoặc `IllegalStateException`, làm lạc mất nguyên nhân sự cố, hỏng rollback và tạo kết quả giả. Nếu cleanup cũng throw exception, exception cleanup có thể che khuất exception gốc.

Để giữ semantics, chỉ làm cleanup/logging không phá vỡ luồng trong `finally`; khi cleanup có thể fail, cần thiết kế xử lý lỗi/suppressed exceptions phù hợp, tránh tự động thay kết cục của method nghiệp vụ.

## 7. Ví dụ chạy được: normal, null, checked, unchecked, fallback

Ví dụ dưới đây dùng **Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1 và Gradle**. Dùng Spring Framework thuần để nhìn rõ proxy/advice, không phụ thuộc AOP auto-configuration của Spring Boot.

### 7.1. Cấu trúc dự án

```text
spring-around-flow/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/flow/
    ├── TaskService.java
    ├── FlowAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Cấu hình Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-around-flow'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.flow.DemoApplication'
}
```

`spring-context` cung cấp IoC container; `spring-aop` chứa Spring AOP proxy infrastructure; `aspectjweaver` cung cấp những thành phần cần để Spring phân tích pointcut. Không cần web server hay database.

### 7.3. Target trả kết quả hoặc ném hai loại exception

`src/main/java/demo/flow/TaskService.java`:

```java
package demo.flow;

import java.io.IOException;

public class TaskService {

    public String execute(String mode) throws IOException {
        System.out.println("target:" + mode);

        if ("ok".equals(mode)) {
            return "SAVED";
        }
        if ("empty".equals(mode)) {
            return null;
        }
        if ("checked".equals(mode)) {
            throw new IOException("offline");
        }
        if ("unchecked".equals(mode)) {
            throw new IllegalStateException("broken");
        }
        if ("recover".equals(mode)) {
            throw new IllegalStateException("retryable");
        }
        return "UNKNOWN";
    }

    public void selfCall() throws IOException {
        System.out.println("target:selfCall");
        String value = execute("ok");
        System.out.println("target:selfResult:" + value);
    }
}
```

`TaskService` là Spring bean target, chưa phải proxy khi được tạo bằng `new` trong `@Bean`. `execute` là public non-final method và ném checked `IOException` theo hợp đồng. `selfCall()` cũng public, nhưng `execute("ok")` bên trong nó là **self-invocation** trực tiếp trên target.

### 7.4. Aspect bao quanh năm đường với try/catch/finally

`src/main/java/demo/flow/FlowAspect.java`:

```java
package demo.flow;

import java.io.IOException;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class FlowAspect {

    @Around(
        "execution(public String demo.flow.TaskService.execute(String))"
    )
    public Object aroundExecute(ProceedingJoinPoint pjp) throws Throwable {
        String mode = (String) pjp.getArgs()[0];
        System.out.println("around:enter:" + mode);

        try {
            Object result = pjp.proceed();
            System.out.println("around:normal:" + mode
                    + ":" + String.valueOf(result));
            return result;

        } catch (IOException ex) {
            System.out.println("around:checked:" + mode
                    + ":" + ex.getMessage());
            throw ex;

        } catch (IllegalStateException ex) {
            System.out.println("around:unchecked:" + mode
                    + ":" + ex.getMessage());

            if ("recover".equals(mode)) {
                System.out.println("around:fallback:" + mode);
                return "FALLBACK";
            }
            throw ex;

        } finally {
            System.out.println("around:finally:" + mode);
        }
    }
}
```

Ý nghĩa từng nhánh:
- `try` gọi `proceed()` **đúng một lần**. Lời gọi này tiến vào phần chain bên trong rồi tới target.
- `"ok"` trả `"SAVED"`, advice log `around:normal:ok:SAVED`, rồi return chính kết quả đó.
- `"empty"` trả `null`, advice log `around:normal:empty:null` và return `null`. Đây vẫn là normal completion.
- `"checked"` ném `IOException`, advice vào đúng catch checked, log rồi **rethrow**.
- `"unchecked"` ném `IllegalStateException`, advice log rồi **rethrow** vì không phải chế độ recover.
- `"recover"` ném `IllegalStateException`, advice log và trả `"FALLBACK"` theo chính sách minh họa. Caller **không nhận** `IllegalStateException` này.
- `finally` log cho cả năm trường hợp đã đi vào advice, kể cả return từ catch.
- Các biến `mode`/`result` chỉ tồn tại trong invocation; không có trạng thái mutable chia sẻ giữa nhiều threads trong singleton aspect.

Cách tổ chức catch này mang tính **giảng dạy**. Trong production, không nên quyết định fallback bằng một string mode chung chung nếu chính sách nghiệp vụ không cho phép; hãy dùng exception type riêng, marker annotation, pointcut phạm vi hẹp hoặc abstraction retry/fallback rõ ràng.

### 7.5. Cấu hình ApplicationContext và bật AOP

`src/main/java/demo/flow/AppConfig.java`:

```java
package demo.flow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public FlowAspect flowAspect() {
        return new FlowAspect();
    }
}
```

`@Aspect` chỉ đánh dấu lớp chứa advice; `@Bean` đăng ký aspect instance trong Spring container. `@EnableAspectJAutoProxy` kích hoạt auto-proxy creator. `proxyTargetClass=true` yêu cầu class-based proxy nên client có thể lấy bean bằng `TaskService.class`. Không cần component scan.

### 7.6. Main gọi qua proxy và tự bắt exception để in kết quả

`src/main/java/demo/flow/DemoApplication.java`:

```java
package demo.flow;

import java.io.IOException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) throws IOException {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            TaskService service = context.getBean(TaskService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            invoke(service, "ok");
            invoke(service, "empty");
            invoke(service, "checked");
            invoke(service, "unchecked");
            invoke(service, "recover");

            service.selfCall();
        }
    }

    private static void invoke(TaskService service, String mode) {
        try {
            String result = service.execute(mode);
            System.out.println("caller:" + mode + ":" + result);
        } catch (IOException | IllegalStateException ex) {
            System.out.println("caller:" + mode + ":throws:"
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }
    }
}
```

Các lời gọi `invoke(...)` đi qua Spring-managed `service` proxy. Method `selfCall()` không khớp pointcut của `FlowAspect` (pointcut chỉ chọn `execute`), và trong method này lời gọi `execute("ok")` không đi qua proxy.

### 7.7. Lệnh chạy và stdout chính xác

Tại thư mục chứa `build.gradle`:

```bash
gradle run
```

Nếu project có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

**Các dòng từ Java code**, không tính logs từ Gradle hoặc môi trường:

```text
proxy=true
around:enter:ok
target:ok
around:normal:ok:SAVED
around:finally:ok
caller:ok:SAVED
around:enter:empty
target:empty
around:normal:empty:null
around:finally:empty
caller:empty:null
around:enter:checked
target:checked
around:checked:checked:offline
around:finally:checked
caller:checked:throws:IOException:offline
around:enter:unchecked
target:unchecked
around:unchecked:unchecked:broken
around:finally:unchecked
caller:unchecked:throws:IllegalStateException:broken
around:enter:recover
target:recover
around:unchecked:recover:retryable
around:fallback:recover
around:finally:recover
caller:recover:FALLBACK
target:selfCall
target:ok
target:selfResult:SAVED
```

### 7.8. Đọc kết quả theo từng kết cục

| Input | Kết cục của `proceed()` | `catch` | `finally` | Kết cục caller thấy |
| --- | --- | --- | --- | --- |
| `ok` | Return `"SAVED"` | Không | Có | `"SAVED"` |
| `empty` | Return `null` | Không | Có | `null` |
| `checked` | Throw `IOException("offline")` | `catch IOException`, rethrow | Có | `IOException` |
| `unchecked` | Throw `IllegalStateException("broken")` | `catch IllegalStateException`, rethrow | Có | `IllegalStateException` |
| `recover` | Throw `IllegalStateException("retryable")` | `catch IllegalStateException`, return fallback | Có | `"FALLBACK"` |

Dòng `caller:recover:FALLBACK` cho thấy một exception thực sự đã xuất hiện trong phần target/inner chain, nhưng được `@Around` biến thành normal return tại ranh giới proxy. Điều này **không tương đương** với việc target chưa từng ném exception.

Cuối chương trình:

```text
target:selfCall
target:ok
target:selfResult:SAVED
```

không có các dòng `around:enter:ok`/`around:finally:ok` thêm lần nữa. Điều đó minh họa lời gọi nội bộ `this.execute(...)` bỏ qua Spring AOP proxy. Đổi `try/catch/finally` không khắc phục self-invocation; muốn advice chạy cần lời gọi đi qua một Spring-managed proxy thích hợp.

## 8. So sánh với @AfterReturning, @AfterThrowing và @After

Có ba loại advice Spring hữu ích khi không cần điều khiển flow:

| Mục tiêu | Loại advice phù hợp | Ghi chú |
| --- | --- | --- |
| Quan sát method trả bình thường | `@AfterReturning` | Return `null` vẫn là normal return |
| Quan sát exception thoát ra ngoài method execution | `@AfterThrowing` | `throwing` có thể bind `Throwable`/subtype |
| Dọn dẹp hoặc ghi nhận kết thúc cả hai đường | `@After` | Tương đương after-finally; không tự đổi return hoặc swallow exception |
| Giữ cùng biến đo giữa trước và sau, hoặc điều khiển kết quả | `@Around` | Có quyền `proceed`/short-circuit/catch/rethrow |

Ví dụ:

```java
@AfterReturning(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    returning = "value",
    argNames = "value"
)
public void afterNormal(Object value) {
    // Normal completion, kể cả null.
}
```

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterThrown(Throwable error) {
    // Exceptional completion, checked hoặc unchecked.
}
```

```java
@After("execution(* com.example.app.service..*.*(..))")
public void afterFinally() {
    // Khi method execution khớp đã kết thúc.
}
```

Đây là **các snippets minh họa** phải đặt trong `@Aspect` và đăng ký vào context; không nên dán đồng thời với demo mà không cân nhắc precedence của nhiều advisors.

Một khác biệt thực tiễn:
- `@AfterReturning` không được dùng để thay reference trả cho caller bằng return value mới từ advice.
- `@AfterThrowing` không phải cơ chế tổng quát để catch rồi return fallback.
- `@After` không phân loại “success” hay “failure”.
- `@Around` có thể điều khiển return/throw nên phải bảo toàn contract khi không muốn đổi nghiệp vụ.

### Vì sao @AfterReturning và @AfterThrowing không nhất thiết cùng đo “target outcome”?

Khi các advisors lồng nhau, một `@Around` phía trong có thể biến exception thành fallback. `@AfterReturning` phía ngoài chỉ quan sát normal return; `@AfterThrowing` phía trong có thể đã quan sát exception trước đó. Ngược lại, cache/retry interceptor bên ngoài có thể không đi vào một advice nằm bên trong.

Để đánh giá số lượt “thành công”, hãy xác định mình đang đo **target attempts** hay **caller-visible proxy calls**. Nếu hai hệ thống metrics đo hai lớp khác nhau, số lượng không nhất thiết trùng khớp.

## 9. Các sai lầm thường gặp với finally

### 9.1. Throw trong finally che mất exception gốc

```java
try {
    return pjp.proceed();
} finally {
    throw new IllegalStateException("logging failed");
}
```

Đây là anti-pattern: kể cả target return thành công hoặc throw `IOException`, caller vẫn nhận `IllegalStateException("logging failed")`, mất outcome gốc. Nếu logging, tracing hoặc cleanup có thể thất bại, cần thiết kế lỗi phụ **không che giấu lỗi nghiệp vụ**; có thể catch lỗi logging có chọn lọc, dùng logger/counter an toàn hoặc giữ suppressed cause theo policy.

### 9.2. Return trong finally làm mất kết quả

```java
try {
    return pjp.proceed();
} finally {
    return "ALWAYS";
}
```

Tương tự, code này ghi đè mọi return và exception. Không dùng `return` trong `finally` của around advice trừ khi có chính sách đặc biệt được review rất kỹ; trong phần lớn trường hợp đây là bug.

### 9.3. Đặt cả code sau proceed và finally rồi đếm hai lần

```java
Object result = pjp.proceed();
incrementCompleted();
return result;
```

đếm chỉ normal returns, còn:

```java
try {
    Object result = pjp.proceed();
    incrementCompleted();
    return result;
} finally {
    incrementCompleted();
}
```

lại **đếm hai lần trên normal return** và một lần trên exception. Nếu muốn đếm tổng số lượt hoàn tất, chỉ increment trong `finally`; nếu muốn hai metrics riêng, đặt tên rõ `normal_count` và `total_completed_count`.

Các snippets ở đây dùng `incrementCompleted()` như helper giả định; không phải API chuẩn của Spring.

### 9.4. Dùng field singleton để lưu trạng thái mỗi invocation

Sai:

```java
@Aspect
public class UnsafeAspect {
    private long started;

    @Around("execution(* com.example.app.service..*.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        started = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            System.out.println(System.nanoTime() - started);
        }
    }
}
```

Nếu aspect là singleton (phổ biến trong Spring), nhiều threads ghi đè `started`. Hãy dùng **biến local** `long started` trong method advice hoặc một context được quản lý đúng theo invocation, không dùng state chia sẻ không đồng bộ.

### 9.5. Gọi finally bên ngoài vùng try

Nếu muốn cleanup cho mọi nhánh **trong advice**, đặt code nhạy cảm vào `try`. Ví dụ:

```java
Object[] args = pjp.getArgs();
String first = ((String) args[0]).trim(); // Có thể throw trước try.
try {
    return pjp.proceed(new Object[] { first });
} finally {
    cleanup();
}
```

Nếu code xử lý argument nằm trước `try` ném `ClassCastException` hoặc `ArrayIndexOutOfBoundsException`, `finally` này **không chạy**, vì control flow chưa vào `try`. Đặt ranh giới `try` bao cả những thao tác mà bạn muốn cleanup bao phủ và kiểm tra argument arity/type trước khi dùng.

## 10. Tương tác với transaction, cache, retry và exception handler

### 10.1. Spring transaction không đồng nghĩa catch/rethrow semantics

Với Spring `@Transactional` ở proxy mode, rollback được quyết định bởi transaction interceptor, loại exception và cấu hình rollback. Theo quy tắc mặc định phổ biến trong Spring Framework, unchecked `RuntimeException` và `Error` kích hoạt rollback; checked exception không mặc định rollback trừ khi cấu hình `rollbackFor`/cơ chế tương ứng.

**Không suy ra “catch rồi rethrow checked exception” luôn rollback.** Spring transaction rules vẫn áp dụng độc lập.

Nếu một `@Around` nằm **bên trong** transaction interceptor và catch exception rồi return fallback, transaction interceptor ở ngoài có thể xem lần gọi là normal completion. Nếu `@Around` nằm **bên ngoài**, transaction interceptor có thể đã quyết định rollback dựa trên exception từ inner method trước khi outer around trả fallback. Cấu trúc thật phụ thuộc advisor order.

### 10.2. Cache hit cũng là normal completion ở một số vị trí

Một cache interceptor có thể trả cache hit mà **không tiếp tục gọi target**. `@Around` phía ngoài cache vẫn thấy `proceed()` return bình thường (dù target chưa chạy). `@Around` phía trong cache có thể không chạy trên cache hit.

Vì thế `around:normal` trong logging aspect có thể nghĩa “proxy invocation trả bình thường”, không nhất thiết “target method vừa chạy thành công”. Chọn tên log/metric phù hợp với điểm quan sát.

### 10.3. Retry có thể làm cùng một caller invocation có nhiều exceptions

Khi retry interceptor hoặc `@Around` gọi `proceed()` nhiều lần, target có thể thất bại hai lần rồi thành công lần thứ ba. Một advice phía ngoài retry có thể thấy một normal return; advice phía trong có thể thấy các attempts đã throw. Phải xác định rõ cần đo **request outcome** hay **attempt outcome**.

Để retry an toàn, cân nhắc:
- Giới hạn số lần thử, backoff và timeout;
- Idempotency, tránh ghi đôi hoặc gửi hai lần;
- Exception nào được retry;
- Transaction boundary cho từng attempt;
- Tương tác với logging/trace và metric counters.

Không thay retry policy bằng catch-all rồi gọi `proceed()` vô hạn.

### 10.4. Spring MVC exception handler là lớp khác

`@ControllerAdvice`/`@ExceptionHandler` của Spring MVC có thể xử lý exception **sau khi** proxy của controller/service ném exception ra ngoài. Chúng không làm exception “biến mất” đối với `@Around` của service nếu service interceptor chain đã quan sát và rethrow exception trước đó.

Ngược lại, nếu `@Around` của service catch rồi return fallback, web layer có thể không có exception để handler xử lý. Phân biệt rõ:
- **Spring AOP @Around:** điều khiển một method invocation qua proxy.
- **Spring MVC exception handling:** xử lý exception trong request dispatch/web handler flow.

Đừng nhập hai cơ chế thành một câu “catch trong AOP là ControllerAdvice”.

## 11. Bảng chẩn đoán đường thành công/lỗi

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/cách sửa |
| --- | --- | --- |
| `finally` không xuất hiện khi gọi service | Lời gọi không qua Spring AOP proxy; pointcut không khớp; outer advisor short-circuit | Kiểm tra `AopUtils.isAopProxy`, bean registration, call path, advisor chain |
| `finally` không xuất hiện khi exception ném trước `try` | Code gây lỗi chạy ngoài vùng try | Đặt vùng try bao đúng phần cần cleanup |
| Catch không chạy với exception đã được target nuốt | Target tự `catch` và normal return | Log ở target catch hoặc thiết kế advice khác |
| Catch chỉ thấy `IllegalStateException` mà không thấy `IOException` | Bắt subtype cụ thể | Thêm catch phù hợp hoặc `Throwable` + rethrow khi cần observability |
| Caller không nhận exception mà target đã throw | Advice catch rồi return fallback | Xem chính sách fallback và advisor order |
| Caller nhận exception lạ từ logging | Finally/catch ném lỗi mới che exception gốc | Tách lỗi instrumentation, giữ original failure |
| Caller nhận `null` dù target return non-null | Advice trả `void` hoặc chủ động return `null` | Dùng `Object` và `return pjp.proceed()` |
| Duration chỉ có cho success | Đặt logging sau `proceed()`, không ở `finally` | Đo trong finally |
| Counter success tăng khi trả `null` | `null` vẫn là normal return | Phân biệt normal completion và business success |
| Counter ghi hai lần khi return | Increment trong cả try và finally | Tách normal/total hoặc chỉ một nơi |
| Self-invocation không có advice | `this.method()` bypass proxy | Tách bean cộng tác hoặc gọi qua proxy phù hợp |
| Method `final`/`private` không được advice | CGLIB không override được | Thiết kế API/proxy lại |
| Catch không thấy exception tạo ở advisor phía ngoài | Advice đang nằm bên trong, ngoại lệ từ phía ngoài không đi qua catch này | Xác định vị trí advisor/preference |
| Exception checked bị wrap khi dùng JDK proxy | Interface method không khai báo checked exception | Sửa method contract và kiểm tra cause |
| Aspect log nhạy cảm | In `pjp.getArgs()`/exception payload không lọc | Masking/allowlist, tránh log credentials/PII |

## 12. Quy trình kiểm thử và debug có hệ thống

1. **Đăng ký Spring AOP:** `@Aspect` class đã là Spring bean chưa? `@EnableAspectJAutoProxy` hoặc Boot AOP auto-config có bật trong đúng context không?
2. **Lấy proxy thật:** client gọi `context.getBean(...)` hoặc injected dependency? Không dùng `new Target()` để kiểm tra advice.
3. **Xác định proxy type:** `AopUtils.isJdkDynamicProxy` hay `isCglibProxy`? Method có proxy được và visible không?
4. **Kiểm tra pointcut:** `execution(...)` có đúng class/method/return type/parameters? Có bị package naming đổi không?
5. **Kiểm tra self-invocation:** có `this.otherMethod()` hay call từ constructor/init không?
6. **Xác định ranh giới try:** lỗi xảy ra **trước** hay **trong** try? Catch type có khớp exception không?
7. **Kiểm tra result/exception:** return type có tương thích? Có swallow hoặc wrap exception không cần thiết không?
8. **Kiểm tra finally:** có return/throw từ finally che original outcome? Cleanup có thể throw không?
9. **Xác định interceptor order:** caching/transaction/retry có làm target không chạy hoặc đổi outcome không?
10. **Test năm trường hợp:** return object, return null, checked exception, unchecked exception, catch→fallback.
11. **Test self-invocation:** call method từ một target method khác; xác nhận lời gọi nội bộ không đi qua proxy.
12. **Test concurrency:** nếu aspect là singleton, mọi state per-invocation phải local hoặc quản lý thread-safe.

Một snippet kiểm tra nhanh khi đã có Spring `context`:

```java
Object bean = context.getBean("taskService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Cần import `org.springframework.aop.support.AopUtils`; đây là **snippet chẩn đoán**, không phải file Java độc lập. `isAopProxy=true` chứng minh bean có proxy, nhưng chưa chứng minh mọi method hoặc mọi call path đều đi qua advice.

## 13. Checklist thiết kế try/catch/finally trong @Around

- [ ] Advice dùng `ProceedingJoinPoint` làm tham số đầu, trả `Object`, và `throws Throwable` khi truyền exception từ `proceed()`.
- [ ] Mặc định gọi `proceed()` đúng một lần; 0/n lần chỉ khi có chính sách rõ.
- [ ] `try` bao trọn phần code mà bạn muốn quản lý cleanup/metrics.
- [ ] `catch` chọn đúng exception type; không nuốt `Throwable` tùy tiện.
- [ ] Nếu không chủ đích fallback, **rethrow original exception**.
- [ ] `finally` không `return`/`throw` ngoài ý muốn, không che exception nghiệp vụ.
- [ ] Không log dữ liệu nhạy cảm từ `getArgs()` hoặc error message không kiểm soát.
- [ ] Tách metric normal return, exception, recovered fallback và completed.
- [ ] Chọn vị trí aspect so với cache, transaction, retry có chủ đích và có test.
- [ ] Dùng biến local per invocation, tránh mutable state không đồng bộ trong singleton aspect.
- [ ] Đảm bảo fallback đúng return type và nghiệp vụ cho phép.
- [ ] Đã thử cả return `null`, checked/unchecked exception và self-invocation.
- [ ] Với logic chỉ cần after-return/after-throw/finally mà không cần flow control, cân nhắc `@AfterReturning`, `@AfterThrowing`, `@After` đơn giản hơn.

## 14. Kết luận

Trong Spring `@Around`, `try/catch/finally` giúp bạn nắm cả hai đường **trả bình thường** và **ném ngoại lệ**, đồng thời thực hiện cleanup khi advice unwind:

- **`try` + `proceed()`:** tiếp tục Spring interceptor chain và nhận normal result hoặc exception.
- **`catch`:** quan sát exception; rethrow nếu không có chính sách chuyển đổi được xác nhận.
- **`finally`:** ghi metric tổng/dọn trạng thái ở cả normal return, rethrow và fallback return.

Điều quan trọng hơn cú pháp là **định nghĩa chính xác outcome ở vị trí của advice trong proxy chain**. Caller-visible result có thể khác target outcome nếu quanh nó có fallback, cache hoặc retry. `@Around` có thể giúp hệ thống vững chắc hơn, nhưng cũng có thể làm lỗi nghiêm trọng khó phát hiện nếu nuốt exception, đổi return type hoặc làm sai transaction semantics.

Bài toán chỉ thuộc Spring AOP khi invocation đi qua **Spring-managed proxy** và pointcut khớp. Một `try/finally` hoàn hảo không thể thay thế điều kiện proxy, không sửa self-invocation và không tự chặn mọi Java method.

### Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): Spring `@Around`, `ProceedingJoinPoint.proceed()`, return value, throwing, `@After` và advice ordering.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): các loại advice, normal/exceptional completion và around advice.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký và kích hoạt aspect trên Spring beans.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, self-invocation và ranh giới proxy.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules và exception handling, độc lập với cách aspect log lỗi.
