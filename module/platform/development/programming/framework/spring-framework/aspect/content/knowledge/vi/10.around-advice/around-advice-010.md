# Tránh nuốt ngoại lệ hoặc trả giá trị mặc định ngoài hợp đồng trong Spring AOP @Around

## 1. Vấn đề: advice có thể thay đổi hợp đồng của Spring service

`@Around` là loại advice của **Spring AOP theo cú pháp @AspectJ** có quyền bao quanh một method execution được proxy, gọi hoặc không gọi `ProceedingJoinPoint.proceed()`, quan sát kết quả và quyết định cuối cùng **giá trị hoặc ngoại lệ mà caller nhận được**.

Quyền này hữu ích để đo latency, ghi audit, thực hiện retry hoặc có một cơ chế fallback đã được thiết kế. Nhưng cũng dễ tạo bug âm thầm: một `catch` trong advice ghi log rồi `return null`, `return 0` hoặc `return new Object()`, biến **thất bại thật** thành **một lần trả về bình thường** hoặc phá kiểu trả về của method.

Ví dụ sai về mặt hợp đồng:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object unsafe(ProceedingJoinPoint pjp) {
    try {
        return pjp.proceed();
    } catch (Throwable error) {
        System.err.println(error.getMessage());
        return null; // Nuốt lỗi, dù submit() chưa chắc cho phép null.
    }
}
```

Đoạn này là **minh họa anti-pattern**, cần class `@Aspect`, imports và Spring AOP setup để chạy; nó không thuộc demo hoàn chỉnh ở phần sau. Nếu method đích công bố `String submit(...)` và caller kỳ vọng **trả mã xác nhận hoặc ném lỗi**, lời advice trên đã bí mật thêm outcome `null`. Nếu return type là primitive `int`, `null` có thể gây lỗi unboxing khi quay qua proxy, làm che mất nguyên nhân gốc.

**Mục tiêu bài học** là viết `@Around` Spring AOP sao cho:

1. **Mặc định giữ nguyên contract**: `proceed()` một lần, trả đúng result, ném lại chính `Throwable` gốc.
2. Nếu làm fallback, **phải có đặc tả rõ**: lỗi nào được chuyển đổi, kiểu/value hợp lệ, phạm vi retry, transaction và test.
3. Xác nhận outcome **qua Spring proxy thật**, không chỉ unit test trực tiếp gọi method trong aspect.
4. Phân biệt **normal return**, `null`, `void`, boxed primitive, checked/unchecked exceptions và async handles.

Theo ghi chú của module, nội dung chỉ tập trung vào **Spring Aspect và Spring AOP proxy**; không mở rộng sang AspectJ weaving hoặc AOP tổng quát.

## 2. Hợp đồng quan sát được của method là gì?

Đối với một public Spring service operation, contract bao gồm nhiều hơn signature Java:

| Phần contract | Ví dụ trong Spring service | Rủi ro khi advice làm sai |
| --- | --- | --- |
| Return type | `Receipt`, `String`, `int`, `void`, `Optional<Receipt>` | Trả object sai kiểu gây `ClassCastException`; `null` với primitive có thể gây unboxing failure. |
| Normal value | Mã giao dịch được phát hành, số lượng hàng còn tồn | Giá trị mặc định `0`/`false` giả thành công hoặc báo sai nghiệp vụ. |
| Nullability | Method có cho phép `null` hay không | `null` không được công bố khiến caller NPE/mất dữ liệu. |
| Failure types | `IllegalArgumentException`, `PaymentDeclinedException` | Advice nuốt lỗi, đổi loại ngoại lệ, làm caller không vào đúng `catch`. |
| Side effects | Ghi database, gửi message, gọi remote API | Retry hoặc `proceed()` lặp làm thực hiện nghiệp vụ nhiều lần. |
| Transaction | Lệnh ghi cần rollback khi ném một lỗi nhất định | Chuyển exception thành success có thể làm khác rollback semantics, tùy advisor ordering. |
| Security | Không cho phép caller trái quyền hoặc chuyển lỗi authorization | Fallback có thể che lỗi kiểm soát truy cập nếu xử lý quá rộng. |
| Async/reactive | Trả `CompletableFuture<T>`/`Mono<T>` | Advice chỉ thấy wrapper return; không tự quan sát completion cuối cùng. |

**Nguyên tắc:** không có quyền “nuốt một lỗi rồi trả giá trị bất kỳ” chỉ vì chữ ký advice là `Object around(...)`. `Object` là kiểu trả về của **advice**, còn method Java được proxy vẫn có kiểu trả về và semantics riêng.

### 2.1. Vì sao test chỉ thấy HTTP 200 chưa đủ?

Controller phía ngoài có thể:

- Dùng response mapping chuyển `null` thành một dạng response khác.
- Có exception handlers chỉ hoạt động nếu exception đúng kiểu được propagate.
- Trả HTTP 200 cho fallback nhưng nghiệp vụ đã bỏ qua thao tác lưu/gửi.
- Ghi metric “success” trên normal return của proxy dù target thất bại.
- Cố retry vì tưởng không có exception, dẫn đến trạng thái dữ liệu không mong muốn.

Vì vậy, kiểm tra Spring AOP cần assert **kết quả hoặc exception ở method boundary**, sau đó kiểm tra side effects (DB/message/transaction/security) khi nghiệp vụ cần.

## 3. Spring proxy và chỗ @Around có quyền quyết định outcome

```text
External caller / other Spring bean
                |
                | orderService.submit("A")
                v
       Spring AOP proxy
                |
                v
     @Around advice invoked
                |
                +-- pjp.proceed()
                |      |
                |      v
                |  target service method
                |      |
                |      +-- return value ----> advice ----> caller
                |      |
                |      +-- throw failure ---> advice ----> caller
                |
                +-- advice không proceed():
                |      +-- return value tự chọn hoặc throw lỗi tự chọn
                |
                +-- advice catch failure:
                       +-- throw nguyên failure (giữ contract)
                       +-- transform / return fallback (CHỈ khi contract cho phép)
```

Spring AOP là **proxy-based**; `@Around` không tự áp vào một service tạo bằng `new`, một method gọi bằng `this.inner()` trên target hoặc một class/method không proxy được. Muốn advice chạy, aspect phải là Spring bean, có Spring @AspectJ support, target là Spring-managed bean và lời gọi phải đi qua proxy.

Trong Spring Framework Java configuration, thường dùng:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class AopConfiguration {
    @Bean
    MonitoringAspect monitoringAspect() {
        return new MonitoringAspect();
    }
}
```

Đây là đoạn minh họa; `MonitoringAspect` là class `@Aspect` phải tồn tại. Trong Spring Boot có AOP auto-configuration phù hợp, thường không cần tự khai báo `@EnableAspectJAutoProxy`. Việc bật `proxyTargetClass=true` không xử lý self-invocation, và CGLIB không advice được `final` method.

## 4. Mẫu an toàn mặc định: proceed, quan sát, trả lại hoặc ném lại nguyên trạng

```java
@Aspect
public class ContractPreservingAspect {
    @Around("execution(public * com.example.orders..*Service.*(..))")
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        try {
            Object result = pjp.proceed();
            recordSuccess(pjp);
            return result; // Giữ nguyên object/value mà proceed() trả về.
        } catch (Throwable failure) {
            recordFailureSafely(pjp, failure);
            throw failure; // Giữ nguyên kiểu và chính Throwable gốc.
        }
    }

    private void recordSuccess(ProceedingJoinPoint pjp) {
        // Ghi metric không ném lỗi.
    }

    private void recordFailureSafely(
            ProceedingJoinPoint pjp, Throwable failure) {
        // Quan sát lỗi và không làm mất Throwable gốc.
    }
}
```

Đây là **mẫu minh họa**, không phải project runnable độc lập; các helper cần implementation và imports `@Aspect`, `@Around`, `ProceedingJoinPoint`. Trong code thật, instrumentation cũng có thể ném lỗi. Nếu `recordSuccess` ném, chính `catch(Throwable)` sẽ bắt lỗi instrumentation ấy và `recordFailureSafely` có thể xử lý nhầm đó là lỗi của target. Để giữ đúng semantics, nên **tách pha `proceed()` khỏi pha ghi số liệu** như ví dụ chạy hoàn chỉnh ở mục 7.

Một phiên bản bảo vệ lỗi instrumentation tốt hơn:

```java
@Around("execution(public * com.example.orders..*Service.*(..))")
public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
    final Object result;
    try {
        result = pjp.proceed();
    } catch (Throwable original) {
        try {
            observeFailure(original);
        } catch (RuntimeException telemetryError) {
            // Theo policy: ghi nhận telemetryError qua kênh lỗi độc lập.
        }
        throw original;
    }

    try {
        observeSuccess(result);
    } catch (RuntimeException telemetryError) {
        // Theo policy: không biến result hợp lệ thành lỗi nếu telemetry best-effort.
    }
    return result;
}
```

Đây là đoạn code minh họa trong `@Aspect` và giả định `observeFailure`/`observeSuccess` tồn tại. Không coi `catch(RuntimeException)` là giải pháp bảo vệ trước **mọi** lỗi: chúng ta đang chủ động chọn policy cho những lỗi instrumentation bình thường; errors nghiêm trọng không nên bị nuốt chỉ để giữ illusion thành công.

Nếu telemetry/audit **bắt buộc** phải ghi bền vững thì “best-effort ignore” cũng có thể sai contract; khi ấy cần thiết kế rõ transactional/outbox/reliable audit, không chỉ thay một dòng `catch`.

### 4.1. Vì sao chữ ký advice khai báo throws Throwable?

`ProceedingJoinPoint.proceed()` khai báo `throws Throwable`. Để propagation giữ nguyên mọi loại checked/unchecked exceptions phù hợp với method target, mẫu Spring `@Around` thường là:

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable
```

`throws Throwable` trên **method advice** không làm Java source contract của target đổi thành `throws Throwable` cho caller. Nó cho phép advice thực hiện `throw original` mà không ép mọi lỗi thành `RuntimeException`. Đối với JDK interface proxy và checked exception không được khai báo, quy tắc proxy/JDK có thể dẫn đến wrapping như `UndeclaredThrowableException`; điều này không cho phép advice tùy tiện ném checked exception mới ngoài contract.

`@Around` không nên đổi mọi `Exception` thành `new RuntimeException(error)` chỉ để compiler chấp nhận. Đổi exception type làm thay exception handlers, transaction rollback decisions và log diagnostics. Nếu có mapping nghiệp vụ, hãy định nghĩa mapping rõ và test trên loại proxy thực tế.

## 5. Các anti-pattern phổ biến

### 5.1. Ghi log rồi return null

```java
@Around("execution(* com.example.orders..*Service.*(..))")
public Object swallow(ProceedingJoinPoint pjp) {
    try {
        return pjp.proceed();
    } catch (Throwable error) {
        logger.error("Service failed", error);
        return null;
    }
}
```

Sai mặc định vì:

- `null` không tương thích với `int`, `boolean` hoặc các primitive return types.
- Với `String`/DTO method có contract non-null, caller nhận outcome không hợp lệ.
- Exception handler bên ngoài không biết lời gọi thực sự lỗi.
- Transaction/cache/metrics interceptors khác có thể nhận normal return, tùy vị trí advice trong chain.
- Advice đang bắt cả `Throwable`, bao gồm `Error`, nhưng lại không propagation.

Đây là **mã minh họa không chạy độc lập** vì chưa khai báo logger và aspect infrastructure.

### 5.2. Return giá trị mặc định “cho an toàn”

```java
catch (Exception error) {
    return 0;
}
```

Nếu contract `int remainingStock()` định nghĩa `0` là thật sự hết hàng, giá trị `0` giả từ lỗi database sẽ dẫn tới quyết định nghiệp vụ sai. Nếu contract `boolean authorized()`, `false` giả có thể che lỗi hệ thống — dù trong một số chính sách “fail closed” được chủ động quyết định, vẫn phải phân biệt “deny” với “authorization service unavailable”.

Đừng chọn fallback theo kiểu giá trị dễ biên dịch. Cần phân biệt:

- **No data hợp lệ**: có thể `Optional.empty()` hoặc một result type đã định nghĩa.
- **Failure nghiệp vụ**: exception hoặc explicit failure result theo contract.
- **Infrastructure failure**: timeout, DB unavailable; có thể retry, circuit breaker, lỗi cho caller, hoặc fallback rõ ràng theo policy.
- **Fatal error**: không được convert âm thầm thành business success.

### 5.3. Catch rồi ném một lỗi mới không giữ cause

```java
catch (Exception original) {
    throw new IllegalStateException("failed");
}
```

Đoạn code trên làm mất cause chain trừ khi lưu cause. Nếu **phải** dịch exception vì contract của boundary, tối thiểu:

```java
catch (RemoteServiceException original) {
    throw new OrderGatewayException("Remote order gateway failed", original);
}
```

Đây là ví dụ minh họa; `RemoteServiceException` và `OrderGatewayException` là domain/infrastructure types cần được định nghĩa trong ứng dụng. Mọi change type phải có chủ đích, vì caller/transaction/security có thể phân nhánh theo exception class.

Nếu không có policy chuyển đổi, **`throw original;`** bảo toàn thông tin tốt hơn.

### 5.4. Ném Exception sai thời điểm

```java
Object result = pjp.proceed();
doAudit(); // Có thể ném và thay một normal return bằng exception
return result;
```

Nếu audit được định nghĩa là **best-effort**, việc `doAudit()` ném lỗi có thể vi phạm contract của method đã thực thi thành công. Nếu audit được định nghĩa là **must-succeed**, đó không nhất thiết là bug nhưng phải được thể hiện trong business/transaction contract.

Đặt rõ loại audit (best-effort hay mandatory) và cách xử lý failure; đừng mặc định rằng audit phải “bất kể exception” hay “luôn được bỏ qua”.

### 5.5. Không gọi proceed()

```java
@Around("execution(* com.example.orders..*Service.*(..))")
public Object skip(ProceedingJoinPoint pjp) {
    return "ok";
}
```

`@Around` có quyền không gọi `proceed()`, nhưng như vậy **target chưa chạy**: DB update, validation, audit hay publish message trong target không xảy ra. Nếu chưa có contract về short-circuit (cache hit, access denied hoặc idempotency), đây là bug nghiêm trọng.

`@Before` hoặc `@AfterReturning` thích hợp hơn khi chỉ cần quan sát, không cần điều khiển call path.

### 5.6. Gọi proceed() hai lần vô tình

```java
Object a = pjp.proceed();
Object b = pjp.proceed();
return b;
```

Code này có thể khiến **target thực thi hai lần** theo semantics quanh advice; nếu method không idempotent, nó có thể trừ tiền hai lần, gửi hai sự kiện hay ghi DB hai lần. Không lạm dụng Spring AOP `@Around` để retry mù.

Retry chỉ hợp lệ khi:

- Operation được xác định là idempotent hoặc có idempotency key/deduplication.
- Có policy chỉ retry lỗi **transient** rõ ràng.
- Số attempts, backoff, timeout/deadline và cancellation hợp lý.
- Transaction boundaries, request scope, security context và side effects đã được kiểm chứng.
- Có integration tests xác minh chính xác số lần downstream được gọi.

## 6. Trả đúng kiểu và đúng giá trị: primitive, void, null, Optional

### 6.1. Method trả primitive

Giả sử target có:

```java
public int available() {
    return 12;
}
```

Trong `@Around`, `pjp.proceed()` trả `Object` chứa giá trị boxed `Integer` (hoặc giá trị đã được interceptor khác xử lý tương thích). Mẫu an toàn là **trả nguyên `Object` đó** để Spring proxy unbox theo return type `int`.

```java
Object result = pjp.proceed();
return result;
```

**Không trả `null`**, string `"0"`, hay `Integer` bất kỳ nếu contract đòi hỏi số lượng thực. Với target trả `boolean`, một `null` cũng không thể unbox thành primitive.

### 6.2. Method trả void

Với target:

```java
public void refresh() {
    // Thực hiện thao tác thật.
}
```

`proceed()` của around advice thường trả `null` trên normal completion của `void` method; đây **không phải fallback**. Returning `null` từ `@Around` sau khi `proceed()` thành công là hợp lệ đối với method `void`, khác hoàn toàn với việc cố tình `return null` trong `catch` sau một lỗi của target.

### 6.3. Method chủ đích cho phép null

```java
public String findNullable(String id) {
    return null;
}
```

Nếu contract công bố có thể trả `null`, around advice phải **giữ nguyên `null`** khi target return bình thường. Không được tự ý đổi `null` thành `"UNKNOWN"` nếu consumer dựa vào `null` như “không có dữ liệu”.

### 6.4. Optional và Result type

```java
public Optional<Order> find(String id) {
    // Optional.empty() được định nghĩa là "không tìm thấy".
}
```

Khi contract là `Optional<Order>`, một `Optional.empty()` hợp lệ; `return null` là khác hoàn toàn và thường làm sai contract.

Một result wrapper như `OperationResult<T>` có thể biểu đạt `SUCCESS`/`NOT_FOUND`/`FAILED` tường minh nếu business API được thiết kế như vậy. Nhưng advice không được bí mật thay một service vốn `throws` bằng `Result.fail(...)` khi method signature không hỗ trợ hoặc caller không được cập nhật.

### 6.5. Generics và runtime casts

`@Around` thường khai báo `Object` do `proceed()` trả `Object`. Java compiler không kiểm tra được mọi kiểu return của service tại compile time; Spring/JDK proxy có thể cast/unbox theo declared return type. Một method `List<Order> findAll()` không thể nhận `"error"`; lỗi type mismatch có thể xuất hiện **sau** khi advice return.

Để giảm rủi ro:

- Mặc định trả `pjp.proceed()` trực tiếp.
- Không ép `String.valueOf(...)` cho tất cả results.
- Khi transformation thật sự cần, giới hạn pointcut vào method cụ thể và kiểm thử kiểu trả về.
- Dùng typed result/contract trong service thay vì một aspect chung cố “chuẩn hóa” mọi return values.

## 7. Java 17+ Spring AOP demo: giữ nguyên normal return và ngoại lệ

Demo gồm một Spring-managed target, một Spring-managed aspect và một client lấy target bean từ `AnnotationConfigApplicationContext`. Nó kiểm tra:

- `String` normal return không đổi;
- `int` primitive unboxing không đổi;
- `void` normal completion;
- `null` hợp lệ của method nullable không bị thay;
- `IllegalArgumentException` được truyền nguyên trạng tới caller;
- advice quan sát **4 normal returns và 1 exceptional exit**.

Demo dùng Java 17+, Spring Framework 6.2.19, AspectJ Weaver 1.9.25.1. Đây là Spring Framework thuần, không dựa vào Spring Boot auto-configuration.

### 7.1. Cấu trúc project

```text
spring-around-contract/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/contract/
    ├── Main.java
    ├── AppConfig.java
    ├── OrderService.java
    └── ContractAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-around-contract'
```

**`build.gradle`**

```gradle
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.contract.Main'
}
```

`spring-context` mang container/Java-config; `spring-aop` và `aspectjweaver` hỗ trợ @AspectJ pointcuts. `@EnableAspectJAutoProxy` kích hoạt Spring proxy AOP, không phải AspectJ load-time weaving. Trong dự án Spring Boot nên dùng BOM tương thích với major version Boot thay vì cố ép versions demo.

### 7.2. Target service với các outcomes xác định

**`OrderService.java`**

```java
package com.example.contract;

public class OrderService {
    public String accept(String id) {
        return "accepted:" + id;
    }

    public int quantity() {
        return 12;
    }

    public void refresh() {
        System.out.println("target:refresh");
    }

    public String findNullable(String id) {
        return null;
    }

    public String reject(String id) {
        throw new IllegalArgumentException("invalid:" + id);
    }
}
```

Các method đều public, không final, class cũng không final. Đây là điều kiện đơn giản để Spring CGLIB proxy có thể intercept. `reject(..)` cố ý ném một exception từ target để kiểm tra advice không nuốt lỗi.

### 7.3. @Around advice không đổi contract

**`ContractAspect.java`**

```java
package com.example.contract;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ContractAspect {
    private final AtomicInteger normalReturns = new AtomicInteger();
    private final AtomicInteger exceptionalExits = new AtomicInteger();

    @Around("execution(public * com.example.contract.OrderService.*(..))")
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        final Object result;
        try {
            result = pjp.proceed();
        } catch (Throwable original) {
            exceptionalExits.incrementAndGet();
            throw original;
        }
        normalReturns.incrementAndGet();
        return result;
    }

    public int normalCount() {
        return normalReturns.get();
    }

    public int failureCount() {
        return exceptionalExits.get();
    }
}
```

Trong ví dụ, hai `AtomicInteger` không ném lỗi bình thường, nên instrumented outcome đúng với số `proceed()` hoàn tất hoặc ném lỗi. Spring AOP có thể có **các interceptors khác** nằm trong chain; nên gọi tên counter là “outcome quan sát tại `proceed()`” nếu ứng dụng thật có retry/transaction/security interceptors khác.

Điểm quan trọng:

1. `proceed()` được gọi **một lần** cho mỗi invocation.
2. Khi bình thường, `result` được trả về **nguyên trạng**, kể cả boxed primitive hoặc `null`.
3. Khi lỗi, lời advice làm một phép tăng đếm rồi `throw original;`, không tạo new exception.
4. `throws Throwable` trên chữ ký advice cho phép propagation không ép wrap exception.
5. Không có logic biến failure thành `null`, `0`, `false` hay object giả.

### 7.4. Đăng ký aspect và target với Spring

**`AppConfig.java`**

```java
package com.example.contract;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean
    ContractAspect contractAspect() {
        return new ContractAspect();
    }
}
```

`@Aspect` không tự đăng ký bean; `@Bean` trên config đăng ký `ContractAspect` và `OrderService`. `proxyTargetClass=true` chọn class-based proxy để `context.getBean(OrderService.class)` hợp lệ và thuận tiện cho demo. Không cần component scan vì tất cả beans đã khai báo tường minh.

### 7.5. Chạy và kiểm chứng outcome ngay tại client

**`Main.java`**

```java
package com.example.contract;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            ContractAspect aspect = context.getBean(ContractAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("accepted=" + service.accept("A"));
            System.out.println("quantity=" + service.quantity());

            service.refresh();

            System.out.println(
                "nullableIsNull=" + (service.findNullable("missing") == null)
            );

            try {
                service.reject("X");
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("normalReturns=" + aspect.normalCount());
            System.out.println("exceptionalExits=" + aspect.failureCount());
        }
    }
}
```

Chạy tại root project với JDK 17+ và Gradle đã cài:

```bash
gradle run --quiet
```

Nếu đã có Gradle wrapper: `./gradlew run --quiet` trên Linux/macOS, `gradlew.bat run --quiet` trên Windows.

**Các dòng `System.out` của demo theo đúng thứ tự** (không kể logging khác của Gradle/Spring/JVM):

```text
proxy=true
accepted=accepted:A
quantity=12
target:refresh
nullableIsNull=true
caught=invalid:X
normalReturns=4
exceptionalExits=1
```

### 7.6. Đối chiếu kết quả với contract

| Lời gọi | Kết quả target | Caller thực sự nhận | Counter |
| --- | --- | --- | --- |
| `accept("A")` | `"accepted:A"` | Chuỗi y hệt | normal +1 |
| `quantity()` | `12` kiểu `int` | `12`, không bị đổi thành `0`/`null` | normal +1 |
| `refresh()` | `void` normal completion | Không có returned value | normal +1 |
| `findNullable("missing")` | `null` là outcome hợp lệ | `null` giữ nguyên | normal +1 |
| `reject("X")` | Throw `IllegalArgumentException("invalid:X")` | Bị bắt đúng kiểu và đúng message | exceptional +1 |
| **Tổng** | 5 method calls | **4 normal, 1 exception** | normal=4, exceptional=1 |

Demo này không minh họa `@AfterThrowing` trực tiếp; nó cho thấy **`@Around` có thể bảo tồn exceptional flow** bằng `throw original`. Không biến các counters thành “business success/failure” một cách vô điều kiện: method `findNullable` return `null` bình thường nhưng có thể biểu đạt “không tìm thấy”.

## 8. Vì sao không thay exception bằng fallback vô điều kiện?

Giả sử method khai báo:

```java
public Receipt charge(String orderId)
        throws PaymentGatewayException;
```

Contract có thể nói rằng `Receipt` chỉ tồn tại khi giao dịch đã được xác nhận, còn `PaymentGatewayException` báo rằng chưa xác nhận được trạng thái. Nếu advice bắt mọi lỗi và trả `new Receipt("fake")`, caller có thể coi giao dịch đã được xử lý, mặc dù tiền chưa được ghi nhận.

Đây là **ví dụ nghiệp vụ minh họa**; `Receipt` và `PaymentGatewayException` cần được định nghĩa trong dự án thực. Điều Spring-specific cần nhớ là **`@Around` cho phép thay cả return lẫn throw**. Chính khả năng đó đòi hỏi ràng buộc contract.

### 8.1. Fallback có chủ đích phải có ba điều kiện

1. **Policy rõ:** lỗi nào được xử lý, lỗi nào phải propagation. Không catch tất cả `Throwable` rồi coi là “không tìm thấy”.
2. **Giá trị/kiểu hợp lệ:** fallback thuộc miền return và được API công bố, ví dụ `Optional.empty()` cho một lookup cho phép thiếu dữ liệu.
3. **Side effects an toàn:** biết chắc target đã/chưa commit, có thể retry hay không, và cache/transaction/security advisors nhìn outcome thế nào.

Chỉ khi cả ba điều kiện được đáp ứng, short-circuit hoặc fallback trong `@Around` mới là một **hành vi nghiệp vụ được thiết kế**, không phải kỹ thuật né exception.

### 8.2. Mẫu chỉ fallback trên lỗi cụ thể

```java
@Around("execution(* com.example.catalog.CatalogService.find(..))")
public Object cacheFallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (CatalogUnavailableException ex) {
        return Optional.empty();
    }
}
```

**Đây là snippet minh họa**, không chạy độc lập: `CatalogService` và `CatalogUnavailableException` cần được định nghĩa, method `find(..)` **phải công bố `Optional<...>`** như một return type hợp lệ, và policy phải cho phép coi “catalog không khả dụng” là “không tìm thấy” — một quyết định mà nhiều hệ thống **không cho phép** vì hai trạng thái không tương đương.

Ví dụ này chỉ cho thấy **cách giới hạn catch theo exception type**. Không được dùng như một lời khuyên production tự động để hợp nhất `unavailable` và `absent`. Phần lớn trường hợp đúng hơn là propagation exception hoặc trả một result type có trạng thái **UNAVAILABLE** tường minh.

### 8.3. Return type fallback phải tương thích Java

`Optional.empty()` hợp lệ khi target method return `Optional<T>`. Nó **không** hợp lệ khi target method return `T`, `String` hoặc `int`. Với generic types và erased runtime, một mismatch có thể chỉ nổ ở caller, nên test cả compile-time contract và runtime proxy behavior.

### 8.4. Đừng “sửa lỗi” kiểu bằng ép cast liều

```java
return (Receipt) (Object) "fallback";
```

Đây là mã minh họa hành vi sai, có thể ném `ClassCastException`. Nó không tạo một `Receipt` hợp lệ. Nếu muốn fallback cho `Receipt`, phải tạo ra một **Receipt đúng nghĩa** theo contract, không đánh tráo ý nghĩa thành công chỉ bằng cách làm compiler chấp nhận.

## 9. Retry và proceed(): một thay đổi có thể nhân đôi side effects

`@Around` cho phép `proceed()` nhiều lần. Cơ chế này có thể dùng cho retry ở tầng AOP nhưng **chỉ khi đã định nghĩa rõ ràng semantics**.

Ví dụ nguy hiểm:

```java
@Around("execution(* com.example.payment.PaymentService.charge(..))")
public Object badRetry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (RuntimeException ex) {
        return pjp.proceed(); // Thực thi lại, có thể charge thêm một lần.
    }
}
```

Nếu lần đầu DB commit xong nhưng network response bị mất, lần thứ hai có thể tạo giao dịch trùng. Spring AOP không tự phân biệt “failed before side effect” với “failed after side effect”. Retry cũng có thể tác động `@Transactional`/`@Cacheable`/`@Async` interceptors khác tùy advisor order.

**Thay vì retry mù**, cần:

- Phân loại transient/permanent errors.
- Idempotency key hoặc deduplication mechanism.
- Bounded attempts, backoff, timeouts.
- Quan sát transaction boundary; tránh retry bên trong một transaction đã rollback-only.
- Xác định exception cuối cùng vẫn được trả cho caller nếu hết attempts.
- Integration tests đo số lần downstream được gọi và trạng thái DB/message.
- Bảo đảm user/request context và security identity được truyền phù hợp khi async.

Nếu bài toán chỉ cần logging, đo thời gian hoặc counter, **không retry**; `proceed()` một lần là mặc định an toàn nhất.

## 10. Transaction và @Around: nuốt exception có thể đổi rollback semantics

Giả sử một Spring service dùng transaction interceptor:

```java
@Service
public class LedgerService {
    @Transactional
    public void transfer(String from, String to, long amount) {
        // Business operation với quy tắc transaction.
    }
}
```

Đây là code minh họa, không đầy đủ dependency/transaction manager. Nếu target method ném `RuntimeException` nhưng `@Around` catch rồi trả bình thường, chuyện transaction rollback tùy **thứ tự advisors**, tình trạng transaction hiện có, điểm lỗi và propagation:

- Nếu Spring transaction advice nhìn thấy **exception** trước khi exception bị aspect ngoài cùng nuốt, transaction có thể đã đánh dấu rollback hoặc kết thúc theo quy tắc riêng.
- Nếu transaction interceptor nhìn thấy **normal return** do một aspect nằm trong chain chuyển từ lỗi thành fallback, behavior có thể khác.
- `@Transactional` tự nó cần transaction manager và configuration, không được bật chỉ vì `@EnableAspectJAutoProxy`.

**Không kết luận “nuốt lỗi chắc chắn commit” hay “chắc chắn rollback”.** Điều đúng là **Spring transaction advisor quyết định trên outcome/exception nó thật sự quan sát được**, và `@Around` có thể làm thay outcome đó. Muốn xác nhận phải kiểm tra transaction manager, `@Order`, rollback rules và actual data state sau integration test.

### Sau commit có khác after-returning không?

Có. Một `@Around` quan sát target return bình thường hoặc một `@AfterReturning` chạy không phải cam kết DB transaction đã commit. Nếu cần side effect đáng tin sau commit, sử dụng transaction synchronization hoặc `@TransactionalEventListener(phase = AFTER_COMMIT)` theo đúng use case; không dùng một đoạn `catch` trong aspect để giả lập commit confirmation.

## 11. Spring security, caching và async: không biến lỗi thành “thành công”

### 11.1. Method security

Nếu Spring Method Security áp `@PreAuthorize` hoặc interceptor khác lên service, một `@Around` quá rộng có thể vô tình bao gồm method security policy. Không catch exception authorization rồi trả fallback `true` hoặc default DTO. **Security denial cần được giữ nguyên trừ khi có contract và policy bảo mật rất rõ.**

Thứ tự giữa custom aspect và method security advisors cần được kiểm tra; nếu advice đặt ngoài security interceptor mà cố bỏ `proceed()`, nó có thể **không cho security interceptor cơ hội chạy**, làm sai boundary. Tránh pointcut rộng áp lên tất cả framework beans/security methods.

### 11.2. Caching

Một cache aspect hoặc `@Cacheable` interceptor có thể short-circuit method theo contract cache. Nếu bạn thêm `@Around` trả giá trị mặc định khi backend lỗi, value đó có thể bị cache tùy thứ tự advisor chain/configuration; hậu quả là “fake success” tồn tại sau khi backend phục hồi.

Cần phân biệt “cache miss”, “data legitimately absent” và “backend unavailable”. Đừng coi ba trạng thái là `null` giống nhau.

### 11.3. CompletableFuture và async handle

Với method:

```java
public CompletableFuture<String> loadAsync(String id) {
    // Trả future ngay, công việc có thể kết thúc về sau.
}
```

`@Around` thấy `pjp.proceed()` trả một `CompletableFuture` **bình thường**, ngay cả nếu future ấy hoàn tất exceptional sau đó. `catch(Throwable)` quanh `proceed()` không tự bắt exception phát sinh bất đồng bộ bên trong future. Nếu policy cần error handling ở completion, phải dùng `whenComplete`/`handle` hoặc công cụ async tương ứng.

**Không thay một future bị fail bằng `CompletableFuture.completedFuture("ok")`** trừ khi API contract/policy thực sự định nghĩa fallback này.

### 11.4. Reactor Mono/Flux

Với reactive method trả `Mono<T>` hoặc `Flux<T>`, advice proxy nhìn thấy một **publisher object** lúc return. Lỗi có thể xuất hiện **khi subscribe**, sau khi `proceed()` đã trả bình thường. Dùng Reactor operators như `onErrorResume`/`doOnError` theo semantics reactive và lựa chọn policy rõ ràng; không mong `try/catch` trong `@Around` đồng bộ bắt mọi reactive error.

## 12. @AfterThrowing và @AfterReturning có phải lựa chọn tốt hơn?

Nếu yêu cầu chỉ là **quan sát** outcome mà không muốn thay return hoặc exception:

- `@AfterReturning`: chạy khi method execution đã kết thúc bình thường; có thể bind return value bằng `returning`.
- `@AfterThrowing`: chạy khi method execution thoát bằng exception; có thể bind thrown exception bằng `throwing`.
- `@After`: mang semantics finally.
- `@Around`: bao quanh và có quyền chủ động chuyển đổi outcome, nên cần cẩn trọng nhất.

Spring Framework hướng dẫn ưu tiên **advice ít quyền nhất đáp ứng yêu cầu**, vì như vậy tránh cả lớp bug quên `proceed()` hoặc trả sai value. Nếu chỉ cần đếm exception, `@AfterThrowing` an toàn thiết kế hơn `@Around` có `catch` tự chế.

Ví dụ observer với returning và throwing (không ghép vào demo nếu muốn giữ stdout):

```java
@AfterReturning(
    pointcut = "execution(* com.example.contract.OrderService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterResult(Object result) {
    // Quan sát kết quả trả về, không thay value.
}

@AfterThrowing(
    pointcut = "execution(* com.example.contract.OrderService.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterError(Throwable error) {
    // Quan sát lỗi, không tự biến exceptional exit thành success.
}
```

Đây là đoạn minh họa trong Spring-managed `@Aspect` có imports phù hợp. Tập method phù hợp của binding `Object result` có thể khác với advice không bind return type, nhất là `void`/primitives/generics; dùng integration test trên Spring version đang chạy.

Nếu cần recovery có chủ đích, `@Around` hoặc domain-level handler mới có quyền cần thiết, nhưng policy phải explicit và đủ test coverage.

## 13. Tách business fallback khỏi infrastructure advice khi có thể

Một thiết kế ổn định là để Spring service tự diễn đạt domain outcome:

```java
public Optional<InventoryItem> findAvailable(String sku) {
    // Optional.empty(): mặt hàng thực sự không có.
    // InventoryBackendUnavailableException: backend lỗi.
}
```

Như vậy Spring AOP `@Around` có thể **giữ nguyên returned Optional hoặc thrown backend exception**. Caller phân biệt legitimate absence và lỗi hạ tầng mà không phải đoán từ `null`/`false`.

Đây là đoạn minh họa; `InventoryItem`/`InventoryBackendUnavailableException` cần được định nghĩa trong ứng dụng thật. Nếu client yêu cầu fallback khi backend unavailable, đặt nó trong **một boundary có tên và contract**, ví dụ `InventoryQueryFacade.findCachedOrUnavailable()`, và kiểm thử:

- Value mới hay stale cache?
- Timeout bao nhiêu?
- Lỗi nào cho fallback, lỗi nào phải fail?
- Permission checks vẫn được thực thi?
- Response có biểu đạt degraded status?
- Những side effects nào đã hoặc chưa xảy ra?

Cách này tránh một `@Around` “tổng quát” âm thầm điều khiển mọi method của cả hệ thống.

## 14. Vì sao cùng @Around lại có thể chạy/không chạy?

Ngay cả một advice giữ nguyên contract cũng vô dụng nếu Spring AOP không intercept lời gọi.

| Hiện tượng | Giải thích trong Spring | Hướng kiểm tra |
| --- | --- | --- |
| `@Aspect` tồn tại nhưng không có advice | Class aspect chưa là bean hoặc AOP support chưa bật | `@Aspect` + `@Component` trong scan, hoặc `@Bean` + `@EnableAspectJAutoProxy`/Boot AOP starter |
| Method được gọi từ `this.method()` trên chính target | Self-invocation không quay qua Spring proxy | Tách sang injected collaborator bean hoặc đưa advice lên outer entry |
| Client dùng `new Service()` | Bỏ qua Spring container | Inject service bean từ context |
| `final` class với CGLIB | Không thể subclass | Dùng interface/JDK proxy nếu tương thích hoặc thay thiết kế |
| `final` method với CGLIB | Không override được method | Dùng entry method interceptable, kiểm thử |
| Spring trả JDK proxy nhưng caller muốn gọi method không có trên interface | Proxy không expose method ấy | Đưa vào interface hoặc chọn proxy strategy thích hợp |
| `AopUtils.isAopProxy(bean)=true` nhưng advice không chạy cho một method | Advisor/pointcut không match hoặc call path khác | Kiểm tra expression, bean target type, actual advice invocation |
| Exception bị mất sau thêm @Around | Advice catch rồi trả fallback/sai loại exception | Trace catch/return branch, assert expected throwable ở caller |
| Service trả sai type sau advice | Advice tạo default incompatible với target declared type | Return original proceed result, test primitive/generic/null branches |

### Phép đo tối thiểu

```java
OrderService bean = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(bean));
bean.reject("probe");
```

Đây là đoạn minh họa **có thể ném IllegalArgumentException** nên cần try/catch nếu không muốn test kết thúc với exception; nó dùng `OrderService` và `AopUtils` từ demo. Proxy true chỉ chứng minh có Spring AOP proxy, không khẳng định pointcut của aspect đang xét được dùng — phải quan sát counter/exception outcome.

## 15. Viết integration tests để khóa đúng contract

### 15.1. Không unit-test riêng aspect rồi cho rằng Spring AOP đã được kiểm chứng

`new ContractAspect().preserve(fakePjp)` có thể test logic Java của advice, nhưng không xác nhận:

- `@Aspect` có được Spring đăng ký bean không;
- `@EnableAspectJAutoProxy` có hoạt động không;
- Method target có được proxy không;
- Pointcut có match không;
- Exception/return type có vượt qua JDK/CGLIB proxy đúng không.

Cần ít nhất một integration test dùng `ApplicationContext` thật và gọi bean qua Spring reference.

### 15.2. Assertions nền tảng

Với demo `AppConfig`:

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    OrderService service = context.getBean(OrderService.class);
    ContractAspect aspect = context.getBean(ContractAspect.class);

    if (!"accepted:X".equals(service.accept("X"))) {
        throw new AssertionError("String return changed");
    }
    if (service.quantity() != 12) {
        throw new AssertionError("Primitive result changed");
    }
    service.refresh();
    if (service.findNullable("missing") != null) {
        throw new AssertionError("Nullability changed");
    }

    try {
        service.reject("Y");
        throw new AssertionError("Expected IllegalArgumentException");
    } catch (IllegalArgumentException ex) {
        if (!"invalid:Y".equals(ex.getMessage())) {
            throw new AssertionError("Wrong failure propagated", ex);
        }
    }

    if (aspect.normalCount() != 4 || aspect.failureCount() != 1) {
        throw new AssertionError("Wrong @Around outcome observations");
    }
}
```

Đoạn này là **biến thể test minh họa** dùng classes trong demo và import `AnnotationConfigApplicationContext`; không ghép vào `Main` nếu muốn giữ stdout mục 7.5.

### 15.3. Kiểm chứng cùng exception object nếu cần

Trong tình huống muốn xác nhận tuyệt đối `throw original` giữ object identity, có thể cấu hình target throw một preconstructed `RuntimeException` instance (thay vì tạo mới trong method), rồi caller dùng `==` để so exception object. Nhưng phải làm fixture test riêng, tránh giữ exception có stack trace cũ dùng chung trong production.

`==` chứng minh identity của reference; so message/type chỉ chứng minh behavior quan sát được phần nào. Cả hai đều có giá trị trong kiểm thử đúng mục tiêu.

### 15.4. Tests cho short-circuit/retry/fallback

Nếu ứng dụng **có chủ đích** thay return/exception:

- Assert điều kiện nào bỏ `proceed()`, target call count = 0 cho nhánh ấy.
- Assert retry attempts được giới hạn và số side effects chính xác.
- Assert lỗi “permanent” không retry và vẫn propagate.
- Assert timeout/cancellation không chuyển thành success giả.
- Assert fallback đúng API type, nullability và business status.
- Assert transaction rollback/commit và security denial thực sự.
- Assert future/reactive completion behavior bằng test async/reactive, không dựa chỉ vào synchronous advice output.

Không chấp nhận test chỉ gọi happy path rồi kết luận aspect đủ an toàn.

## 16. Checklist code review cho @Around

- [ ] `@Aspect` class và target service là Spring-managed beans, pointcut match và caller dùng proxy?
- [ ] Advice `@Around` có `ProceedingJoinPoint`, return type `Object`/compatible và khai báo `throws Throwable`?
- [ ] Nếu không chủ động short-circuit, luôn gọi `proceed()` **đúng một lần**?
- [ ] Normal return được giữ nguyên (`String`/DTO/`int`/`boolean`/`void`/`null`/`Optional`)?
- [ ] Target exception được ném lại **nguyên type, message và cause** khi không có explicit policy dịch lỗi?
- [ ] Có `catch(Throwable)` nhưng không `return null`/`0`/`false` vô điều kiện?
- [ ] Không chuyển exception authorization/transaction thành normal return ngoài contract?
- [ ] Instrumentation best-effort có error policy rõ, không tự tạo exception làm biến outcome?
- [ ] Nếu transform/fallback, API contract và return type đã cho phép và được test?
- [ ] Nếu retry, có idempotency key, bounded attempts và test side effects/transaction?
- [ ] Đã phân biệt null hợp lệ với null do lỗi bị nuốt, void normal với short-circuit?
- [ ] Đã kiểm tra Spring proxy kind và giới hạn self-invocation/final method?
- [ ] Với future/reactive, không nhận nhầm “method trả wrapper” là “tác vụ hoàn tất thành công”?
- [ ] Integration test dùng Spring context thật và assert cả return value, exception, counters, side effects?
- [ ] Pointcut không quá rộng và không áp nhầm security/framework beans?

**Ghi nhớ:** `@Around` trong Spring AOP là một **ranh giới có thể thay kết quả và ngoại lệ**. Mẫu an toàn khi chỉ quan sát là **`return pjp.proceed()` hoặc giữ nguyên result; catch rồi `throw original` nếu cần ghi lỗi**. Không trả mặc định chỉ để “tránh lỗi” nếu API contract chưa cho phép. Chỉ short-circuit, retry, fallback hoặc đổi exception khi **nghiệp vụ yêu cầu rõ và kiểm thử đầy đủ**.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — AOP Concepts and Advice Types](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html)
- [Spring Framework 6.2 — Proxying Mechanisms and Self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
