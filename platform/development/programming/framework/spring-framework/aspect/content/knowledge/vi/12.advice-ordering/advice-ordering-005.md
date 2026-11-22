# Thứ tự giữa các loại advice trong cùng một @Aspect của Spring AOP

## 1. Câu hỏi cần giải quyết

Một Spring `@Aspect` có thể chứa cùng lúc nhiều method mang `@Around`, `@Before`, `@After`, `@AfterReturning` và `@AfterThrowing`. Khi tất cả các advice đều có pointcut khớp một lời gọi service, **advice nào chạy trước, advice nào chạy sau, và vì sao `@After` lại xuất hiện cuối cùng dù được xếp ở mức precedence cao hơn `@AfterReturning`?**

Đây là câu hỏi về **thứ tự trong interceptor chain của Spring AOP**, không đơn thuần là thứ tự những method được viết trong file Java.

Theo tài liệu Spring Framework hiện đại, khi nhiều **loại advice khác nhau trong cùng một lớp `@Aspect`** đều khớp một method-execution join point, Spring gán **precedence từ cao xuống thấp**:

1. `@Around`
2. `@Before`
3. `@After`
4. `@AfterReturning`
5. `@AfterThrowing`

**Ngoại lệ dễ nhầm:** `@After` có ngữ nghĩa *after finally*, nên khi method kết thúc, **`@After` thực sự được gọi sau `@AfterReturning` hoặc `@AfterThrowing` trong cùng aspect**. Precedence quy định **vị trí advice trong interceptor chain**, chứ không phải danh sách thứ tự những dòng log được in theo chiều thời gian.

Trong một method invocation chạy bình thường, bạn thường quan sát:

```text
@Around (trước proceed)
    @Before
        target method
    @AfterReturning
    @After
@Around (sau proceed / finally)
```

Nếu target method ném exception:

```text
@Around (trước proceed)
    @Before
        target method -> throw
    @AfterThrowing
    @After
@Around (catch/finally)
```

Hai flow trên dành cho **một lớp `@Aspect` duy nhất có các loại advice tương ứng**, tất cả cùng nhắm vào một Spring bean method, với `@Around` gọi `proceed()` một lần và không cố ý biến đổi kết quả/exception.

**Phạm vi:** Spring Framework `@AspectJ`-style **proxy-based AOP**. Bài chỉ nói về cách Spring tạo và chạy advisor/interceptor từ một `@Aspect`; không mở rộng sang thứ tự bytecode weaving/constructor/field join points của AspectJ compiler độc lập.

### Mục tiêu sau bài

- Thuộc precedence giữa **các loại advice** trong **cùng một `@Aspect`**.
- Phân biệt precedence **trên đường vào** và thứ tự callback **trên đường ra**.
- Giải thích tại sao `@After` chạy sau `@AfterReturning` hoặc `@AfterThrowing`.
- Biết thứ tự **hai advice cùng loại trong cùng một `@Aspect` là không xác định**.
- Phân biệt order trong **cùng aspect** với `@Order`/`Ordered` dùng cho **nhiều aspects**.
- Chạy thử Java 17/Spring Framework 6.1 với cả normal return, `null`, thrown exception và exception được bắt trong target.
- Hiểu giới hạn: self-invocation, `@Around` bỏ qua `proceed()`, advisor khác chặn đường gọi và exception phát ra từ advice khác.

## 2. Precedence không phải thứ tự dòng code

### 2.1. “On the way in” và “on the way out”

Spring AOP dựng một **chuỗi interceptor** ở phía sau Spring-managed proxy. Khi lời gọi đi từ client vào target:

- Advice có **precedence cao hơn** nằm ở phía **ngoài** của chuỗi.
- Advice phía ngoài có thể quan sát lời gọi **trước** những advice phía trong.
- Khi phần chuỗi phía trong hoàn thành và call stack unwind, advice phía ngoài thường được quay lại **sau cùng**.

Ví dụ hai around interceptors giả định có precedence A cao hơn B:

```text
A:before
    B:before
        target
    B:after
A:after
```

A được gọi trước “on the way in” và sau “on the way out”. Đây là quy tắc chung của nested interceptors.

Tuy nhiên, từng advice type có semantics riêng. Một `@Before` chạy ở phần trước invocation, còn `@AfterReturning` chỉ chạy khi phần join point phù hợp **return bình thường**. Không thể suy ra thứ tự log chỉ bằng cách đọc danh sách precedence như một hàng đợi FIFO.

### 2.2. Thứ tự chuẩn trong một @Aspect (Spring Framework 6.1)

| Precedence | Advice type | Thời điểm thực thi |
| ---: | --- | --- |
| 1 — cao nhất | `@Around` | Bắt đầu trước phần còn lại của chain; gọi `proceed()` để tiếp tục; có thể quan sát kết quả/exception sau đó |
| 2 | `@Before` | Chạy trước target method execution khi interceptor chain tới nó |
| 3 | `@After` | Có vị trí precedence cao hơn các after advice chuyên biệt nhưng callback chạy theo `finally`, **sau** `@AfterReturning`/`@AfterThrowing` của cùng aspect |
| 4 | `@AfterReturning` | Chỉ chạy nếu execution kết thúc **bình thường**, kể cả trả `null` hoặc `void` |
| 5 — thấp nhất | `@AfterThrowing` | Chỉ chạy nếu execution kết thúc bằng **exception thoát ra** |

**Lưu ý phiên bản:** Quy tắc phân loại precedence giữa các advice type trong cùng một `@Aspect` đã được Spring Framework làm rõ từ **5.2.7** và vẫn được tài liệu 5.3/6.x mô tả. Đừng áp câu “thứ tự mọi advice trong cùng aspect là bất định” từ những bản tài liệu Spring cũ cho mọi phiên bản hiện đại. Phần **hai advice cùng loại** vẫn bất định, như mục 7.

### 2.3. Vì sao `@After` có precedence cao hơn nhưng chạy muộn?

Spring xử lý `@After` theo semantics tương đương:

```java
try {
    // Chuyển lời gọi xuống những interceptor phía trong.
} finally {
    // Thực hiện @After.
}
```

Các `@AfterReturning`/`@AfterThrowing` ở phía trong chỉ hoàn thành khi chain bên trong unwind, sau đó `finally` của `@After` mới được chạy.

Do đó **xếp `@After` thứ ba trong danh sách precedence nhưng đặt log của `@After` sau các advice chuyên biệt là hoàn toàn nhất quán**. Đó chính là khác biệt giữa:
- **Precedence:** thứ tự xếp **interceptor chain**;
- **Event timing:** thứ tự thực tế của các callback khi call stack chạy và unwind.

Không đổi `@Order` chỉ để ép `@After` in trước `@AfterReturning` trong cùng aspect. `@Order` chủ yếu dùng để xác định precedence **giữa các aspect khác nhau**, không thay semantics after-finally.

## 3. Hai đường hoàn tất chính: normal và throwing

### 3.1. Method trả bình thường

Một method có thể trả:
- Một `String` hoặc object có giá trị.
- `null`.
- Không có giá trị nếu return type `void`.
- Một status thất bại về nghiệp vụ như `"REJECTED"` nhưng không ném exception.

Đây đều là **normal completion** đối với Spring AOP nếu exception không thoát ra khỏi method execution. Khi tất cả các advice của cùng aspect match và `@Around` gọi `proceed()`, đường bình thường đi qua:

```text
around:enter
before
target returns value
afterReturning(value)
after
around:return(value)
around:finally
caller sees value
```

`@AfterThrowing` không chạy ở đường này.

**Không đồng nhất normal return với business success.** `return null` hoặc `return "DECLINED"` vẫn là một lần hoàn tất bình thường về mặt Java, nhưng có thể là thất bại nghiệp vụ. Dùng metric names phản ánh đúng semantics, không tự gọi mọi lần `@AfterReturning` là “success business”.

### 3.2. Method ném exception ra ngoài

Nếu target ném `IllegalStateException` và exception thoát ra theo interceptor chain:

```text
around:enter
before
target throws
afterThrowing(exception)
after
around:catch(exception)
around:finally
caller sees exception
```

`@AfterReturning` không chạy ở đường này. `@AfterThrowing` có thể bind exception bằng `throwing` parameter, còn `@After` vẫn được chạy sau đó theo after-finally semantics.

`@Around` ở bên ngoài có thể catch/rethrow exception; thứ tự log `around:catch` xuất hiện sau `after` trong ví dụ này vì `proceed()` đã unwind xong interceptor phía trong.

### 3.3. Target tự catch exception rồi return

Ví dụ:

```java
public String safeWork() {
    try {
        return remoteOperation();
    } catch (IOException ex) {
        return "FALLBACK";
    }
}
```

Đây là snippet minh họa, chưa định nghĩa `remoteOperation`. Nếu exception được target bắt nội bộ và method **return bình thường**, Spring AOP chỉ quan sát normal completion của join point:
- `@AfterReturning` chạy;
- `@AfterThrowing` không chạy cho exception đã bị bắt;
- `@After` chạy.

Spring AOP không intercept từng câu lệnh `throw`/`catch` *bên trong* method. Đó không phải lỗi về thứ tự advice.

### 3.4. Throw từ advice khác không giống throw từ target

Tài liệu Spring cảnh báo: các loại advice trong cùng một aspect được thiết kế **để áp dụng vào join point**, vì vậy `@AfterThrowing` không được hiểu là “bộ bắt mọi exception từ `@After` hoặc `@AfterReturning` của chính aspect đó”.

Ví dụ `@AfterReturning` tự ném một exception khi xử lý kết quả. Không nên thiết kế `@AfterThrowing` trong cùng aspect với kỳ vọng bắt được exception ấy như một error handler chung. Hãy quản lý lỗi instrumentation trong chính advice, bảo toàn original business outcome khi cần, hoặc tạo policy exception rõ ràng bằng `@Around`. Tương tác với những advisor **khác aspect** phụ thuộc vị trí trong chain.

## 4. @Around giữ vai trò bao ngoài nhưng có thể đổi flow

`@Around` là advice có precedence cao nhất trong cùng aspect, nhưng có khả năng **điều khiển** có chạy target hay không.

### 4.1. Dạng bảo toàn outcome

```java
@Around("execution(* com.example.app.service..*.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("around:enter");
    try {
        return pjp.proceed();
    } finally {
        System.out.println("around:finally");
    }
}
```

Đây là snippet trong một Spring `@Aspect`, cần import và Spring AOP configuration. `proceed()` tiếp tục phần chain phía trong đúng một lần. `finally` chạy khi `proceed()` return hoặc throw theo Java semantics thông thường.

### 4.2. @Around không gọi proceed

```java
@Around("execution(public String com.example.app.service.LookupService.lookup(..))")
public Object shortCircuit(ProceedingJoinPoint pjp) {
    return "CACHED";
}
```

Nếu code trả kết quả mà không gọi `proceed()`, những advice nằm **phía trong** cũng không được chạy, và method target không được thực thi. Kết quả đó không phải “Spring bỏ qua @Before một cách ngẫu nhiên”; around advice đã chủ động dừng chain.

Nếu code logging của bạn muốn `@Before`, `@AfterReturning`, `@After` vẫn chạy, **đừng short-circuit ở around ngoài chúng**.

### 4.3. @Around catch rồi trả fallback

```java
@Around("execution(public String com.example.app.service.LookupService.lookup(..))")
public Object recover(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

Đây là snippet minh họa. Nếu target throw `IllegalStateException`, phần advice phía trong của **cùng aspect** có thể đã ghi nhận `@AfterThrowing` trước khi around advice ở phía ngoài catch rồi return `"FALLBACK"`. Lời gọi nhìn từ bên ngoài around lại kết thúc bình thường. Vì vậy:
- **Target/inner chain outcome:** exception.
- **Caller-visible proxy outcome:** normal return `"FALLBACK"`.

Không diễn giải mọi dòng log `@AfterThrowing` là một exception chắc chắn đã tới caller. Khi có fallback, cache, transaction hoặc retry, cần định nghĩa **vị trí đo lường** của từng metric.

### 4.4. @Around throw trước proceed

Nếu around advice ném exception **trước** khi gọi `proceed()`, những advice bên trong chưa được đi tới. Vì vậy `@AfterThrowing` cùng aspect có thể không chạy cho exception được tạo từ chính around advice ngoài. Không cố dùng một advice trong cùng aspect như bộ xử lý lỗi toàn cục của mọi advice khác.

## 5. Ví dụ chạy được: xem đúng thứ tự bằng stdout

Ví dụ sau dùng:
- **Java 17+**;
- **Spring Framework 6.1.14**;
- **AspectJ Weaver 1.9.22.1**;
- Gradle;
- Một `@Aspect` có đủ **năm loại advice khác nhau** nhắm tới cùng một target method.

Bốn tình huống:
1. `work("ok")` trả `"OK"`.
2. `work("empty")` trả `null`.
3. `work("fail")` ném `IllegalStateException`.
4. `work("recovered")` tự catch `IllegalStateException` rồi trả `"FALLBACK"`.

Tất cả các lời gọi từ `main` đi qua Spring-managed AOP proxy. Ví dụ cố ý **không dùng nhiều advice cùng loại**, để thứ tự in log được quyết định bởi các semantics của Spring 6.1, không rơi vào trường hợp thứ tự không xác định.

### 5.1. Cấu trúc project

```text
spring-aop-advice-order/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/order/
    ├── WorkService.java
    ├── OrderingAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-advice-order'
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
    mainClass = 'demo.order.DemoApplication'
}
```

`spring-context` cung cấp `AnnotationConfigApplicationContext` và Java configuration; `spring-aop` cung cấp proxy infrastructure; `aspectjweaver` cho phép Spring phân tích pointcut của `@Aspect`. Đây là Spring Framework thuần, không có Spring Boot logging hay auto-configuration để làm nhiễu ví dụ.

### 5.3. Service có ba kiểu outcome

`src/main/java/demo/order/WorkService.java`:

```java
package demo.order;

public class WorkService {

    public String work(String mode) {
        System.out.println("target:" + mode);

        if ("ok".equals(mode)) {
            return "OK";
        }
        if ("empty".equals(mode)) {
            return null;
        }
        if ("fail".equals(mode)) {
            throw new IllegalStateException("broken");
        }
        if ("recovered".equals(mode)) {
            try {
                throw new IllegalStateException("temporary");
            } catch (IllegalStateException ex) {
                return "FALLBACK";
            }
        }
        return "UNKNOWN";
    }
}
```

Đoạn `recovered` cố ý catch ngay trong target, nên method execution **không** ném exception ra khỏi Spring AOP proxy. Đây là một test phân biệt “đã từng có throw trong code Java” với “method execution kết thúc bằng exception”.

### 5.4. Một @Aspect với đúng năm advice types

`src/main/java/demo/order/OrderingAspect.java`:

```java
package demo.order;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class OrderingAspect {

    private static final String POINTCUT =
        "execution(public String demo.order.WorkService.work(String))";

    @Around(POINTCUT)
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String mode = (String) pjp.getArgs()[0];
        System.out.println("around:enter:" + mode);

        try {
            Object result = pjp.proceed();
            System.out.println(
                "around:return:" + String.valueOf(result));
            return result;
        } catch (Throwable ex) {
            System.out.println(
                "around:catch:" + ex.getClass().getSimpleName());
            throw ex;
        } finally {
            System.out.println("around:finally:" + mode);
        }
    }

    @Before(POINTCUT)
    public void before(JoinPoint jp) {
        String mode = (String) jp.getArgs()[0];
        System.out.println("before:" + mode);
    }

    @AfterReturning(
        pointcut = POINTCUT,
        returning = "result",
        argNames = "result"
    )
    public void afterReturning(Object result) {
        System.out.println(
            "afterReturning:" + String.valueOf(result));
    }

    @AfterThrowing(
        pointcut = POINTCUT,
        throwing = "error",
        argNames = "error"
    )
    public void afterThrowing(Throwable error) {
        System.out.println(
            "afterThrowing:" + error.getClass().getSimpleName());
    }

    @After(POINTCUT)
    public void afterFinally(JoinPoint jp) {
        String mode = (String) jp.getArgs()[0];
        System.out.println("after:" + mode);
    }
}
```

**Vì sao ví dụ này không phụ thuộc vào `-parameters`?**
- `@Around` chỉ nhận `ProceedingJoinPoint` làm tham số.
- `@Before`/`@After` chỉ nhận `JoinPoint` đứng đầu.
- `@AfterReturning` khai báo `returning="result"` và `argNames="result"` tường minh.
- `@AfterThrowing` khai báo `throwing="error"` và `argNames="error"` tường minh.

Từ Spring AOP standpoint:
- `@Around` mở đường vào và là nơi cuối cùng unwind trong ví dụ.
- `@Before` chạy trước khi target được gọi.
- `@AfterReturning` chạy cho `ok`, `empty` và `recovered`.
- `@AfterThrowing` chỉ chạy cho `fail`.
- `@After` chạy sau advice theo nhánh return/throw, nhưng trước khi `proceed()` hoàn thành và `@Around` in các dòng sau.

**Chú ý:** Dùng `private static final String POINTCUT` như trên hợp lệ khi annotation attribute là compile-time constant (`static final String` được ghép từ string literal). Đây không phải biến tính tại runtime.

### 5.5. Bật Spring AOP và đăng ký bean

`src/main/java/demo/order/AppConfig.java`:

```java
package demo.order;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public WorkService workService() {
        return new WorkService();
    }

    @Bean
    public OrderingAspect orderingAspect() {
        return new OrderingAspect();
    }
}
```

`@Aspect` **không** tự động đăng ký bean; ở đây `@Bean orderingAspect()` làm điều đó. `@EnableAspectJAutoProxy(proxyTargetClass = true)` kích hoạt Spring AOP, đồng thời dùng class-based proxy vì `WorkService` không implement interface trong demo.

### 5.6. Entry point

`src/main/java/demo/order/DemoApplication.java`:

```java
package demo.order;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkService service = context.getBean(WorkService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            invoke(service, "ok");
            invoke(service, "empty");
            invoke(service, "fail");
            invoke(service, "recovered");
        }
    }

    private static void invoke(WorkService service, String mode) {
        try {
            String result = service.work(mode);
            System.out.println("caller:" + mode + ":" + result);
        } catch (IllegalStateException ex) {
            System.out.println(
                "caller:" + mode + ":throws:"
                + ex.getClass().getSimpleName());
        }
    }
}
```

### 5.7. Chạy ứng dụng

Ở thư mục chứa `build.gradle`, dùng Gradle hỗ trợ Java 17:

```bash
gradle run
```

Nếu có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

**Output do chương trình Java in ra**, không tính các dòng Gradle hay logging môi trường:

```text
proxy=true
around:enter:ok
before:ok
target:ok
afterReturning:OK
after:ok
around:return:OK
around:finally:ok
caller:ok:OK
around:enter:empty
before:empty
target:empty
afterReturning:null
after:empty
around:return:null
around:finally:empty
caller:empty:null
around:enter:fail
before:fail
target:fail
afterThrowing:IllegalStateException
after:fail
around:catch:IllegalStateException
around:finally:fail
caller:fail:throws:IllegalStateException
around:enter:recovered
before:recovered
target:recovered
afterReturning:FALLBACK
after:recovered
around:return:FALLBACK
around:finally:recovered
caller:recovered:FALLBACK
```

### 5.8. Diễn giải kết quả

| Input | `@Before` | Nhánh completion | `@After` | Đường `@Around` |
| --- | --- | --- | --- | --- |
| `ok` | `before:ok` | `afterReturning:OK` | `after:ok` | `enter` → `return:OK` → `finally` |
| `empty` | `before:empty` | `afterReturning:null` | `after:empty` | `enter` → `return:null` → `finally` |
| `fail` | `before:fail` | `afterThrowing:IllegalStateException` | `after:fail` | `enter` → `catch` → `finally` |
| `recovered` | `before:recovered` | `afterReturning:FALLBACK` | `after:recovered` | `enter` → `return:FALLBACK` → `finally` |

Những kết luận có thể kiểm tra trực tiếp:

1. `@Around` in `around:enter` **trước** `@Before`; sau khi target và các advice trong chain hoàn tất, around mới in phần `return/catch/finally`.
2. `@After` xuất hiện **sau** `@AfterReturning` hoặc `@AfterThrowing`, dù nó có precedence cao hơn hai loại ấy trong bảng precedence.
3. `return null` vẫn là normal return, không làm `@AfterThrowing` chạy.
4. Exception được target bắt và chuyển thành `"FALLBACK"` không thoát ra khỏi method execution, nên đi theo `@AfterReturning`.
5. Ngoại lệ `IllegalStateException` của `fail` được `@AfterThrowing` quan sát và vẫn truyền tới caller vì `@Around` rethrow nguyên exception.
6. Output chỉ chứng minh thứ tự trong **cùng một `@Aspect`** với **mỗi advice type xuất hiện một lần**, không chứng minh thứ tự hai `@Before` khác nhau trong cùng aspect.

## 6. Mô hình interceptor chain giải thích output

Spring xử lý lời gọi theo một chuỗi kết hợp. Với demo, có thể hình dung đơn giản như sau:

```text
Client
  |
  v
Spring AOP proxy
  |
  +-- Around interceptor [precedence 1]
  |       enter
  |       try {
  |           |
  |           +-- Before interceptor [2]
  |           |       before
  |           |       |
  |           |       +-- After(finally) interceptor [3]
  |           |       |       try {
  |           |       |           |
  |           |       |           +-- AfterReturning [4]
  |           |       |           |      |
  |           |       |           |      +-- AfterThrowing [5]
  |           |       |           |              |
  |           |       |           |              v
  |           |       |           |            target
  |           |       |           |
  |           |       |           +-- normal: afterReturning
  |           |       |           +-- throw: afterThrowing
  |           |       |       } finally {
  |           |       |           after
  |           |       |       }
  |           |       |
  |       } finally {
  |           around:finally
  |       }
  |
  v
Caller
```

Đây là **sơ đồ lý giải semantics**, không phải mô hình triển khai nội bộ được đảm bảo mọi phiên bản hoặc interceptor implementation đều giống từng node. Nhưng với Spring `@AspectJ` advice ordering được mô tả trong tài liệu, mô hình cho thấy đúng lý do `@After` log sau completion-specific advice.

### Vì sao không viết “@After chạy trước @AfterReturning”?

Vì câu ấy chỉ dựa trên danh sách precedence và bỏ qua cơ chế finally. **Precedence cao hơn** tức advice có quyền *bao ngoài* các advice thấp hơn; với after-finally, callback đặt tại **bước thoát** khỏi phạm vi bao ngoài, nên thực sự được gọi muộn hơn.

### Vì sao không viết “@After luôn là dòng cuối cùng”?

Vì `@Around` có precedence cao hơn, nằm ngoài `@After` và có thể có phần xử lý sau `proceed()`; trong ví dụ nó in `around:return` và `around:finally` **sau `@After`**. Nếu còn aspects khác, transaction/cache/retry hoặc interceptor tùy chỉnh, vị trí log cũng có thể đổi.

## 7. Hai advice cùng loại trong cùng một @Aspect: thứ tự không xác định

Một điểm khác dễ nhầm:

```java
@Aspect
public class DoubleBeforeAspect {

    @Before("execution(* demo.order.WorkService.work(..))")
    public void firstLog() {
        System.out.println("A");
    }

    @Before("execution(* demo.order.WorkService.work(..))")
    public void secondLog() {
        System.out.println("B");
    }
}
```

Đây là **snippet minh họa**, không dán vào project ở mục 5 nếu muốn giữ exact stdout.

Không được cam kết `A` luôn in trước `B` chỉ vì `firstLog()` được viết ở dòng trên trong Java source. Với hai advice cùng loại trong cùng một `@Aspect`, Spring reference nêu **ordering không xác định**, do Java reflection trên class do `javac` biên dịch không cung cấp thứ tự khai báo nguồn đáng tin cậy.

### Cách khắc phục

**Cách 1 — Gộp vào một advice** nếu hai hành động luôn phải đi cùng nhau:

```java
@Before("execution(* demo.order.WorkService.work(..))")
public void logInOrder() {
    System.out.println("A");
    System.out.println("B");
}
```

Bây giờ thứ tự `A` rồi `B` là thứ tự **các statement trong cùng một Java method**, nên rõ ràng.

**Cách 2 — Tách thành hai aspects** nếu cần policy độc lập và ordering qua `@Order`:

```java
@Aspect
@Order(10)
public class FirstAspect {
    @Before("execution(* demo.order.WorkService.work(..))")
    public void first() { System.out.println("A"); }
}
```

```java
@Aspect
@Order(20)
public class SecondAspect {
    @Before("execution(* demo.order.WorkService.work(..))")
    public void second() { System.out.println("B"); }
}
```

Đây là snippets minh họa, cần import `@Aspect`, `@Order`, `@Before` và đăng ký cả hai thành Spring beans. Aspect có giá trị `@Order` **thấp hơn** có precedence **cao hơn**: `FirstAspect` được gọi trước trên đường vào.

**Cách không giải quyết:** Đặt `@Order(1)` lên **một aspect chứa cả hai `@Before`** không làm thứ tự giữa hai method advice cùng loại trở nên xác định. `@Order` ở aspect level không phải annotation đánh số thứ tự từng method trong cùng `@Aspect`.

## 8. Cùng aspect so với nhiều aspect: không đánh đồng

### 8.1. Quy tắc trong một aspect

Trong **một** lớp `@Aspect` và với các **loại advice khác nhau**, Spring có precedence theo loại:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

Đó là **precedence**, không phải thứ tự in log after phase. `@After` thực sự chạy sau completion-specific advice do finally semantics.

### 8.2. Quy tắc giữa những aspects

Giữa **hai hoặc nhiều lớp `@Aspect`**, nếu không chỉ định, Spring không bảo đảm thứ tự giữa các aspects khi nhiều advice cùng match.

Dùng:
- `@Order(int)` trên class aspect;
- Hoặc implements `org.springframework.core.Ordered` trên bean aspect.

Giá trị order **nhỏ hơn có precedence cao hơn**. Với hai around aspects:

```text
@Order(1): around A before
    @Order(2): around B before
        target
    @Order(2): around B after
@Order(1): around A after
```

Advice precedence bên trong từng aspect và aspect-level ordering là **hai chiều phân loại liên quan nhưng không đồng nhất**. Khi viết integration test nên ghi rõ đang kiểm tra dimension nào.

### 8.3. Khi có transaction, cache, retry

`@Transactional`/`@Cacheable` trong proxy mode đóng góp interceptor/advisor từ hạ tầng Spring khác. Những advisors ấy không nhất thiết là advice methods trong **chính lớp `@Aspect` của bạn**. Vì vậy không được lấy bảng precedence 5 loại advice rồi tuyên bố logging luôn ở ngoài transaction hoặc luôn ở trong cache.

Trong một proxy có nhiều advisors:
- Thứ tự Spring `@Order` và thứ tự advisor infrastructure có thể ảnh hưởng scope đo thời gian.
- Cache hit có thể short-circuit trước khi một advice phía trong chạy.
- Retry có thể làm target chạy nhiều lần dù caller chỉ gọi proxy một lần.
- Transaction rollback dựa trên exception rules và thứ tự transaction interceptor quan sát outcome.

Cần inspect advisor ordering hoặc test theo ApplicationContext thực tế, không phỏng đoán từ thứ tự code.

## 9. @AfterReturning, @AfterThrowing và @After không thay thế nhau

### 9.1. @AfterReturning chỉ khi normal completion

```java
@AfterReturning(
    pointcut = "execution(* demo.order.WorkService.work(..))",
    returning = "value",
    argNames = "value"
)
public void completed(Object value) {
    // Kể cả null vẫn là normal completion.
}
```

`returning` có thể bind result; kiểu parameter advice là một ràng buộc kiểu. Đổi `Object` thành `String` có thể giới hạn những trường hợp phù hợp hơn. Không dùng after-returning để thay reference trả về cho caller; muốn đổi kết quả dùng `@Around`.

### 9.2. @AfterThrowing chỉ khi exceptional completion

```java
@AfterThrowing(
    pointcut = "execution(* demo.order.WorkService.work(..))",
    throwing = "error",
    argNames = "error"
)
public void failed(Throwable error) {
    // Exception thoát ra từ execution.
}
```

Nếu method target tự catch exception trước khi return fallback, `@AfterThrowing` không được gọi cho exception đã được catch bên trong target. Nếu advice parameter chỉ có kiểu `IllegalArgumentException` thì những exception khác không được bind. Dùng `Throwable` khi cần quan sát cả checked/unchecked, nhưng không swallow lỗi ở advice chỉ có vai trò ghi log.

### 9.3. @After theo finally

```java
@After("execution(* demo.order.WorkService.work(..))")
public void finished() {
    // Cả normal và exceptional completion.
}
```

`@After` không biết kết quả cuối là business success hay failure; nó chỉ thực hiện hook theo finally. Nếu cần biết kết quả và exception trong cùng một scope, dùng `@Around` và kiểm soát `proceed()` cẩn thận.

### 9.4. Một @Before ném exception thì sao?

`@Before` có thể ném exception, khiến phần chain phía trong không được tiếp tục. Khi đó target method có thể **chưa chạy**, và các completion advice đứng phía trong có thể không được gọi. Đừng suy ra mọi call đã vào proxy chắc chắn có đủ các dòng `@After`/`@AfterThrowing` của cùng aspect nếu phần chain bị cắt trước khi chúng được vào.

Một câu đúng hơn là: “`@After` có finally semantics **nếu Spring đã đi vào interceptor tương ứng**.” Không phải: “`@After` luôn chạy với mọi exception ở bất kỳ vị trí nào trong proxy.”

## 10. Những lỗi đọc log rất thường gặp

| Hiện tượng | Hiểu đúng | Cách kiểm tra |
| --- | --- | --- |
| `@After` log sau `@AfterReturning` dù có precedence cao hơn | After-finally interceptor bao ngoài completion advice | Phân biệt chain precedence và callback event time |
| `@Around` log sau `@After` | Around advice đang unwind sau `proceed()` | Xem `try/finally` trong `@Around` |
| `@AfterThrowing` không chạy khi return `null` | `null` là normal return | Kiểm tra method có throw ra ngoài hay không |
| `@AfterThrowing` không thấy exception target đã catch | Exception không thoát khỏi method execution | Ghi nhận ở target catch khi cần |
| Hai `@Before` cùng aspect đảo thứ tự giữa môi trường | Same-type advice ordering không xác định | Gộp method hoặc tách thành aspects có `@Order` |
| Đặt `@Order` lên một aspect nhưng hai `@Before` vẫn không ổn định | `@Order` quản precedence giữa aspects, không sắp xếp method cùng loại | Thiết kế lại tổ chức advice |
| `@After` không chạy khi `@Before` ném exception | Chain chưa vào after-finally interceptor | Kiểm tra phần nào của chain đã được chạy |
| `@After` không chạy khi around return trước `proceed` | Inner advisors không được đi tới | Kiểm tra branch short-circuit |
| Log thứ tự khác do transaction/cache | Infrastructure advisors có precedence riêng | Kiểm tra `Advised.getAdvisors()` và effective order |
| `@AfterThrowing` trong cùng aspect không bắt exception do `@AfterReturning` tạo | Advice type áp dụng vào join point, không phải global error handler | Xử lý exception trong advice gây lỗi hoặc quanh phạm vi phù hợp |
| Gọi `this.otherMethod()` nhưng không thấy advice | Self-invocation bypass Spring proxy | Tách bean hoặc gọi qua dependency đã proxy |
| Aspect hoạt động trên method này, không trên method kia | Pointcut/visibility/proxy type khác nhau | Xác minh method signature, `final`/`private`, JDK vs CGLIB |
| `@Aspect` annotation có nhưng advice không chạy | Aspect chưa thành Spring bean, chưa bật AOP hoặc bean target không proxy | Đăng ký `@Bean`/`@Component` và bật `@EnableAspectJAutoProxy` |

## 11. Kiểm thử đúng thứ tự trong cùng @Aspect

### 11.1. Kiểm thử có chủ đích

Với một integration test, nên ghi nhận event list, ví dụ:

```text
around.enter
before
target
afterReturning
after
around.exit
```

Rồi so sánh với expected events **trên một Spring-managed proxy**. Không unit test trực tiếp `new WorkService()` và kỳ vọng event list từ `@Aspect` được thêm vào.

Ở trường hợp exception:

```text
around.enter
before
target.throw
afterThrowing
after
around.catch
around.finally
```

Không so sánh thứ tự hai advice cùng loại trừ khi bạn đã thiết kế bảo đảm bằng gộp code hoặc tách aspects.

### 11.2. Có cần dùng @Order trong cùng aspect không?

Không cần để đạt precedence **theo loại advice** như ở phần 2. Nếu chỉ có một `@Around`, một `@Before`, một `@After`, một `@AfterReturning` và một `@AfterThrowing` đều khớp join point, Spring áp quy tắc loại advice. `@Order` chỉ phát huy khi **có nhiều aspects/advisors khác** cần xác định vị trí tương đối.

### 11.3. Cách inspect advisor chain

Nếu bean có Spring AOP proxy hỗ trợ `Advised`, có thể chẩn đoán:

```java
import org.springframework.aop.framework.Advised;
import org.springframework.aop.Advisor;

Object bean = context.getBean("workService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

Đây là **snippet chẩn đoán** cần biến `context` có sẵn, không phải file standalone. Nó cho biết chain có advisor nào; tên lớp hạ tầng hoặc thứ tự phát biểu từ `toString()` có thể phụ thuộc Spring version, vì vậy **không** dùng tên class generated làm hợp đồng logic. Nếu cần lý giải sâu, inspect advisor instances và pointcuts cùng với event log thực tế.

### 11.4. Test cả null, exception và side effects

Đối với hệ thống thật, thêm test:
- `return null` có đi vào `@AfterReturning`?
- Exception checked/unchecked được `@AfterThrowing` bind bằng type phù hợp?
- Target tự catch exception rồi return có được tính normal completion?
- Advice `@Around` có giữ nguyên result/exception khi không có policy fallback?
- Khi nhiều advisors có transaction/cache/retry, thứ tự event có được mô tả chính xác ở điểm quan sát?
- Với `@Before` throw hoặc `@Around` không `proceed()`, các advice phía trong có được bỏ qua như dự kiến?
- Nếu có nhiều `@Aspect`, precedence `@Order` có được đăng ký đúng không?

## 12. Version notes và phạm vi đảm bảo

### 12.1. Spring Framework 5.2.7 trở về sau

Quy tắc precedence theo loại advice trong cùng một `@Aspect` được Spring nêu rõ từ phiên bản **5.2.7**:

```text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
```

Trong đó `@After` có after-finally semantics, nên **callback chạy sau completion-specific advice**. Nếu bạn duy trì ứng dụng rất cũ, đọc đúng Spring reference theo phiên bản đó trước khi đưa ra kết luận về order.

### 12.2. Spring Framework 6.x

Project phần 5 dùng `spring-context:6.1.14` và `spring-aop:6.1.14`, vì vậy không phụ thuộc những thay đổi mặc định Spring Boot. Với Spring 6.2 hoặc 7.0, nên kiểm tra tài liệu cùng phiên bản khi có vấn đề đặc thù, nhưng nguyên tắc **phân biệt precedence với finally callback timing** được tài liệu Spring hiện đại duy trì.

### 12.3. Spring Boot không đổi nghĩa @After

Spring Boot có thể cấu hình Spring AOP tự động khi đủ dependencies và có các properties ảnh hưởng loại proxy. Nhưng Boot không biến `@After` thành một callback before `@AfterReturning`, cũng không biến source declaration order của các advice methods thành cơ chế sắp xếp được bảo đảm.

### 12.4. Khác biệt giữa @AspectJ style và XML AOP

Đối với một `@Aspect` class dùng annotation style, Spring reference nêu precedence theo loại advice như trên. Trong **schema-based XML AOP**, việc sắp xếp advice elements trong một `<aop:aspect>` có quy tắc riêng theo **thứ tự phần tử XML được khai báo**. Không trộn hai cơ chế và kết luận vì XML có thứ tự khai báo nên Java `@Aspect` cũng phải chạy theo thứ tự source methods.

## 13. Checklist khi xây dựng một @Aspect nhiều advice

- [ ] Chỉ sử dụng các advice types thực sự cần thiết cho cross-cutting concern.
- [ ] Nắm rõ precedence trong một `@Aspect`: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`.
- [ ] Nhớ `@After` chạy **sau** `@AfterReturning`/`@AfterThrowing` của cùng aspect khi unwind.
- [ ] Với normal return, kể cả `null`, dùng `@AfterReturning`; với exception thoát ra, dùng `@AfterThrowing`.
- [ ] Không suy luận business success chỉ từ `@AfterReturning`.
- [ ] `@Around` gọi `proceed()` khi cần target và inner chain thực thi; không nuốt exception trừ khi có chính sách.
- [ ] Không có hai advice cùng loại cần thứ tự cố định trong **cùng** `@Aspect`; nếu có, gộp hoặc tách aspect.
- [ ] Dùng `@Order`/`Ordered` khi phải điều khiển precedence **giữa** aspects.
- [ ] Đã phân biệt code source order với advisor precedence.
- [ ] Có integration test qua Spring-managed proxy cho normal, null, thrown và recovered completion.
- [ ] Không nhầm transaction/cache/retry advisor với advice method cùng `@Aspect`.
- [ ] Có test hoặc quan sát thực cho self-invocation, short-circuit và exception do advice khác phát sinh.
- [ ] Không sửa logic chỉ để “ép” log theo danh sách precedence; hiểu call stack vào/ra mới là nền tảng.

## 14. Kết luận

Trong **cùng một Spring `@Aspect`**, thứ tự **precedence** giữa các advice types từ cao đến thấp là:

**`@Around` → `@Before` → `@After` → `@AfterReturning` → `@AfterThrowing`.**

Nhưng khi method hoàn tất, **`@After` được thực thi sau `@AfterReturning` hoặc `@AfterThrowing`**, vì nó là một finally-style advice bao ngoài hai nhánh completion. `@Around` vẫn có thể thực hiện phần cleanup/catch sau khi `proceed()` quay lại. Đây là lý do không thể đọc precedence thành “các log luôn xuất hiện theo thứ tự từ trái qua phải”.

Với **hai advice cùng loại trong cùng một `@Aspect`**, thứ tự không được bảo đảm; hãy gộp chúng nếu có dependency về thứ tự, hoặc tách thành các `@Aspect` có `@Order` thích hợp. Với những **aspects khác nhau**, cần xét order của aspect, các advisors khác và call path qua Spring proxy.

### Tài liệu chính thức

- [Spring Framework — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): precedence các advice types trong một `@Aspect`, after-finally semantics, same-type order không xác định và `@Order` giữa aspects.
- [Spring Framework 5.3 — AOP Advice Ordering](https://docs.spring.io/spring-framework/docs/5.3.x/reference/html/core.html): mốc làm rõ từ Spring Framework 5.2.7 và thứ tự các loại advice.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` và `@Around`.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): bật Spring AOP, đăng ký `@Aspect` thành Spring bean.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): ranh giới JDK/CGLIB proxy và self-invocation.
- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html): lưu ý khác biệt về thứ tự advice elements trong `<aop:aspect>` XML so với annotation-based `@Aspect`.
