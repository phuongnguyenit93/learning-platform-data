# Giữ dữ liệu riêng cho lời gọi trong biến cục bộ của Spring Aspect

## 1. Bài toán thực hành: ghép đúng dữ liệu trước và sau một lời gọi

Một aspect cần ghi **thời gian, kết quả và lỗi** của `OrderService.submit(id)`. Cùng một singleton aspect có thể xử lý hai invocations đồng thời: A thành công, B ném exception. Mục tiêu không chỉ là tránh sai timestamp, mà còn bảo đảm `outcome` của A không bị ghi bằng trạng thái của B.

Với state gắn một invocation, giữ toàn bộ tiến trình **capture → `proceed()` → observe → cleanup** trong một `@Around`:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    final long startedNanos = System.nanoTime();
    String outcome = "THROWN";
    try {
        Object result = pjp.proceed();
        outcome = "RETURNED";
        return result;
    } finally {
        record(outcome, System.nanoTime() - startedNanos);
    }
}
```

Đây là fragment: `record(...)` là helper của ứng dụng và phải có chính sách nếu sink lỗi. Khi A/B cùng gọi advice, mỗi execution frame chứa `startedNanos`/`outcome` riêng; `final` không phải nguồn bảo đảm thread safety, **phạm vi biến local** mới là điểm cốt lõi. `proceed()` có thể ném `Throwable`; `finally` vẫn quan sát thất bại đồng bộ rồi exception tiếp tục lan ra ngoài, trừ khi bản thân recorder ném lỗi.

Bài này thực hành cách giữ state per-invocation trong Spring AOP, bao gồm return/throw, shared metrics, nhiều lời gọi lồng nhau và giới hạn future/reactive. Demo mục 7 sử dụng hai luồng có latch để xác nhận **A→RETURNED** và **B→THROWN** mà không phụ thuộc thứ tự scheduler.

## 2. Chọn lifetime đúng cho từng giá trị

Spring `@Aspect` là bean singleton theo mặc định trong `ApplicationContext`, nhưng một method advice có **execution frame riêng cho mỗi lần được gọi**. Field của aspect tồn tại giữa các lần advice; local của `@Around` chỉ sống trong invocation đó.

| Dữ liệu | Lifetime đúng | Thiết kế |
| --- | --- | --- |
| `startedNanos`, `outcome`, `Throwable`, method name | Một lời advice invocation | Local variables trong `@Around` |
| ID của lời gọi hiện tại | Một invocation | Local `String`/immutable snapshot từ argument hoặc provider |
| Số lượt thực thi/latency aggregate | Nhiều invocations | `LongAdder`, atomic counter hoặc metrics backend |
| Kết quả audit tra cứu về sau | Nhiều invocations | Concurrent sink/map với key duy nhất và retention policy |
| Config hoặc dependency | Vòng đời bean aspect | `final` reference, đánh giá riêng thread safety của dependency |
| Context xuyên threads/subscriptions | Theo contract async/reactive | Propagation/Reactor Context, không dựa vào field “current request” |

`local Object[] args = pjp.getArgs()` chỉ tách **reference của array** khỏi field aspect; các object mutable bên trong vẫn có thể được chia sẻ. Khi cần snapshot đáng tin, copy dữ liệu scalar cần thiết theo chính sách audit. Một `LongAdder` thread-safe cũng không tự làm phép kiểm tra–cập nhật nhiều trường trở thành atomic.

Điều quan trọng hơn scope là **cách kết thúc**: local state còn dùng được trong cùng `finally` của `@Around`; hai advice methods `@Before` và `@After` thì không chia sẻ Java locals. Các phần sau phân tích return/exception và chạy demo.

## 3. Vì sao @Around đặc biệt phù hợp để giữ state một invocation?

Spring reference khuyên dùng around advice khi cần chia sẻ state từ lúc **trước** đến lúc **sau** một method execution một cách thread-safe, ví dụ đồng hồ đo thời gian.

Một `@Around` bao quanh `ProceedingJoinPoint.proceed()`:

```text
Client -> Spring AOP proxy
          |
          v
        @Around
          |
          +-- local started = now
          |
          +-- try {
          |      pjp.proceed()
          |         |
          |         +-- other advisors
          |         +-- target method
          |    }
          |
          +-- catch Throwable: local outcome = failure
          |
          +-- finally: local elapsed = now - started
          |
          v
        return / rethrow tới caller
```

Dù target return bình thường, return `null` hay ném exception, khi control flow đi vào `try` rồi unwind thông thường, `finally` có thể truy cập **cùng local `started`** của invocation đó.

### 3.1. Ví dụ chỉ đo thời gian

```java
@Around("execution(public * com.example.service..*.*(..))")
public Object time(ProceedingJoinPoint pjp) throws Throwable {
    final long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        final long elapsed = System.nanoTime() - start;
        System.out.println(pjp.getSignature().getName() + "=" + elapsed);
    }
}
```

Đây là **snippet minh họa**, không độc lập: cần `@Aspect`, các imports và Spring AOP configuration. Timestamp được lưu trong Java local primitive, không nằm ở field Spring bean. Stdout của duration **không cố định** giữa các lần chạy.

### 3.2. Quan sát normal/exception bằng state local

```java
@Around("execution(public * com.example.service..*.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    final long start = System.nanoTime();
    String outcome = "THROWN";

    try {
        Object result = pjp.proceed();
        outcome = "RETURNED";
        return result;
    } finally {
        long elapsed = System.nanoTime() - start;
        record(pjp.getSignature().getName(), outcome, elapsed);
    }
}
```

Trong snippet này `record(...)` là helper giả định, không phải API Spring. Nếu `proceed()` return (kể cả `null`), `outcome` đổi thành `"RETURNED"`. Nếu `proceed()` ném exception, lệnh gán đó không chạy, nên `outcome` còn là `"THROWN"` và `finally` nhận trạng thái failure.

**Giới hạn:** Nếu method `record` trong `finally` tự ném exception, nó có thể che exception gốc từ `proceed()`. Instrumentation phải tránh làm hỏng business flow; dùng metrics backend/logging được cấu hình an toàn và có chính sách khi backend lỗi.

### 3.3. try/catch/finally có thay đổi proxy outcome không?

Một `@Around` chỉ dùng `try/finally` và `return pjp.proceed()` giữ nguyên normal result hoặc exception thoát ra từ inner chain. Thêm `catch(Throwable ex) { throw ex; }` để quan sát cũng giữ nguyên exception khi **rethrow cùng object**.

Ngược lại:

```java
catch (IllegalStateException ex) {
    return "FALLBACK";
}
```

là **chuyển kết cục**: inner chain đã throw nhưng caller bên ngoài có thể thấy normal return. Nếu bạn lưu outcome `"THROWN"` trong finally trước khi trả fallback, phải đặt tên metric là **inner failure**, không được tự gọi nó là **caller-visible failure**. Với Spring transaction/cache/retry, vị trí advisors trong chain ảnh hưởng nơi kết quả được quan sát.

## 4. Anti-pattern: field giữ outcome của request đang chạy

```java
@Aspect
public class UnsafeTraceAspect {
    private String currentId;
    private long startedNanos;

    @Around("execution(* com.example.service..*.*(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        currentId = String.valueOf(pjp.getArgs()[0]);
        startedNanos = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            System.out.println(currentId + ":" +
                    (System.nanoTime() - startedNanos));
        }
    }
}
```

Đây là phản ví dụ, không phải cách triển khai. Sau khi A set `currentId="A"` rồi vào target, B có thể set `currentId="B"`; A thoát `finally` và ghi nhầm B. Thêm `volatile` chỉ thay đổi visibility của field dùng chung; `synchronized` toàn bộ advice có thể tuần tự hóa cả nghiệp vụ, ảnh hưởng throughput và làm các lời gọi lồng nhau khó quản lý.

Sửa bằng cách khai báo `String currentId` và `long startedNanos` **bên trong method advice**, giống pattern ở mục 1. Một giá trị local tham chiếu DTO mutable vẫn có thể bị thay đổi từ nơi khác; nếu báo cáo cần bản chụp chính xác, dùng immutable snapshot thay vì lưu cả argument graph.

## 5. Dùng local cho giá trị per-invocation, dùng thread-safe structure cho số liệu tổng hợp

Một ứng dụng thường cần hai lớp dữ liệu:

1. **Trong invocation**: `start`, `id`, `outcome`, `Throwable error`, `Object result` — nên là local.
2. **Sau invocation**: total requests, latency metrics, audit records — cần lưu ra nơi có nhiều threads ghi cùng lúc.

Không phải vì `private long completed` nằm trong `@Aspect` mà Spring tự quản concurrency. Nếu đếm:

```java
private long completed;

public void increment() {
    completed++; // Read-modify-write không atomic.
}
```

thì update có thể bị mất khi hai threads cùng tăng.

Một ví dụ shared counter phù hợp hơn:

```java
private final LongAdder completed = new LongAdder();

public long completedCount() {
    return completed.sum();
}
```

Với import `java.util.concurrent.atomic.LongAdder`, các calls `completed.increment()` có thể được nhiều threads thực hiện an toàn, phù hợp số liệu thống kê có concurrency cao. `sum()` là snapshot **không phải giao dịch atomic với tất cả increments đang diễn ra**; khi có các requests in-flight, không nên dùng nó làm invariant tuyệt đối nếu không đồng bộ thêm.

Đối với dữ liệu mỗi invocation phải tra cứu, có thể dùng:

```java
private final ConcurrentMap<String, Observation> observations =
    new ConcurrentHashMap<>();
```

mà `Observation` là immutable record. Nhưng bạn cần key **duy nhất cho mỗi invocation** và chính sách tránh memory leak: xóa/giới hạn dữ liệu hoặc đẩy sang tracing/metrics backend. Ví dụ chạy phía dưới dùng key `A`, `B` **duy nhất trong demo**, không phải contract phù hợp nếu production có thể nhận cùng business id đồng thời nhiều lần.

## 6. Vì sao @Before và @After thường không chia sẻ được biến local?

Hai advice methods là **hai Java method invocations khác nhau**:

```java
@Before("execution(* com.example.service..*.*(..))")
public void before() {
    long started = System.nanoTime();
}

@After("execution(* com.example.service..*.*(..))")
public void after() {
    // Không thể truy cập biến local "started" của before().
}
```

`started` chỉ tồn tại trong execution frame của `before()`. `after()` không thể tự lấy lại nó chỉ bằng trùng tên pointcut, và Spring không có cơ chế mặc định “ghép đôi local variables” giữa hai advice methods.

Nếu mục tiêu là đo thời gian từ before đến after của **cùng một method invocation**, dùng một `@Around` với `try/finally`. Đây là thiết kế đơn giản hơn tạo `ThreadLocal` rồi tự ghép cặp `@Before`/`@After`.

### Khi nào vẫn dùng @Before/@After?

- `@Before` thích hợp nếu chỉ cần check điều kiện/log trước method, **không** cần giữ biến qua phần thực thi.
- `@AfterReturning` thích hợp nếu chỉ cần biết normal result.
- `@AfterThrowing` thích hợp nếu chỉ cần ghi nhận exception.
- `@After` thích hợp cho cleanup không phụ thuộc state tạo từ lời gọi `@Before`.
- `@Around` thích hợp khi cần **một local scope chứa cả phần trước và phần sau**.

Spring reference khuyên dùng **advice ít quyền nhất** đáp ứng nhu cầu; không cần dùng `@Around` cho mọi việc. Nhưng đối với start/stop timer cần chia sẻ `start` per invocation, `@Around` mang lại scope tốt nhất.

## 7. Project chạy được: hai lời gọi đồng thời, không lẫn trạng thái

Để chứng minh tính tách biệt, ví dụ Java 17 sau tạo một Spring target bean, một singleton aspect, rồi gọi method target **đồng thời trên hai threads**. `CountDownLatch` giữ cả hai lời gọi ở trong target trước khi chúng được phép kết thúc.

Aspect ghi nhận:
- `id` lấy từ arguments, lưu vào local;
- `startedNanos` lưu vào local;
- `outcome` là local được cập nhật sau `proceed()`;
- `elapsedNanos` là local trong `finally`;
- kết quả cuối được đưa vào `ConcurrentHashMap` an toàn cho concurrent writes.

**Stdout được in sau khi cả hai `Future` hoàn tất**, nên không phụ thuộc thread A/B nào chạy trước. Demo cố ý cho `A` return bình thường, `B` throw unchecked exception; ta xác minh cả hai được ghi đúng outcome.

### 7.1. Môi trường và cấu trúc

- Java **17+**;
- Spring Framework **6.1.14**;
- AspectJ Weaver **1.9.22.1**;
- Gradle hỗ trợ Java 17;
- Không cần Spring Boot, web server hoặc database.

```text
spring-aop-local-state/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/local/
    ├── Gate.java
    ├── WorkService.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 7.2. Gradle project

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-local-state'
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
    mainClass = 'demo.local.DemoApplication'
}
```

`spring-context` cung cấp container/configuration; `spring-aop` cung cấp proxying infrastructure; `aspectjweaver` hỗ trợ phân tích Spring `@AspectJ` pointcut expressions.

### 7.3. Đồng bộ hai invocations bằng CountDownLatch

`src/main/java/demo/local/Gate.java`:

```java
package demo.local;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class Gate {
    private final CountDownLatch entered = new CountDownLatch(2);
    private final CountDownLatch release = new CountDownLatch(1);

    public void waitInsideTarget() {
        entered.countDown();

        try {
            if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("release timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }
    }

    public void awaitBothEntered() throws InterruptedException {
        if (!entered.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("workers did not enter");
        }
    }

    public void open() {
        release.countDown();
    }
}
```

`Gate` chỉ phục vụ **test concurrency**, không phải một component AOP. Mỗi worker gọi `waitInsideTarget()` sẽ báo đã vào method rồi chờ. `main` đợi cả hai tới chỗ chờ trước khi thả cho chúng chạy tiếp. Timeout bảo vệ demo khỏi chờ vô hạn nếu môi trường lỗi.

### 7.4. Spring target service

`src/main/java/demo/local/WorkService.java`:

```java
package demo.local;

public class WorkService {
    private final Gate gate;

    public WorkService(Gate gate) {
        this.gate = gate;
    }

    public String handle(String id) {
        gate.waitInsideTarget();

        if ("B".equals(id)) {
            throw new IllegalStateException("failed-B");
        }
        return "OK-" + id;
    }
}
```

Method `handle` là public non-final, target class cũng non-final; Spring có thể tạo CGLIB class-based proxy. Với `id="A"` sẽ return `"OK-A"`, với `id="B"` ném `IllegalStateException("failed-B")`. Cả hai execution cùng đi qua một shared `Gate` chỉ để xác minh chúng thực sự overlap.

### 7.5. Aspect an toàn: local state + ConcurrentHashMap

`src/main/java/demo/local/TraceAspect.java`:

```java
package demo.local;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TraceAspect {
    private final ConcurrentMap<String, Observation> records =
        new ConcurrentHashMap<>();

    public record Observation(String outcome, long elapsedNanos) {}

    @Around(
        value = "execution(public String demo.local.WorkService.handle(String))"
              + " && args(id)",
        argNames = "id"
    )
    public Object observe(ProceedingJoinPoint pjp, String id)
            throws Throwable {

        // Per-invocation locals:
        final String invocationId = id;
        final long startedNanos = System.nanoTime();
        String outcome = "THROWN";

        try {
            Object result = pjp.proceed();
            outcome = "RETURNED";
            return result;
        } finally {
            final long elapsedNanos =
                System.nanoTime() - startedNanos;

            // Chỉ bước tổng hợp cross-invocation mới ghi shared state.
            records.put(invocationId,
                new Observation(outcome, elapsedNanos));
        }
    }

    public String outcomeFor(String id) {
        Observation found = records.get(id);
        return found == null ? "MISSING" : found.outcome();
    }

    public int recordedCount() {
        return records.size();
    }
}
```

**Phân tích từng biến:**
- `pjp` là current `ProceedingJoinPoint`. `ProceedingJoinPoint` phải đứng đầu chữ ký `@Around`.
- `id` được Spring bind từ `args(id)`; `argNames="id"` cố ý bỏ tên `pjp` vì đó là tham số `ProceedingJoinPoint` đầu tiên.
- `invocationId` sao chép **reference immutable `String`** đến local riêng. Nếu actual argument là một object mutable, muốn snapshot dữ liệu thì cần immutable representation/copy.
- `startedNanos`, `outcome`, `elapsedNanos` là locals thuộc execution frame của chính lần advice chạy.
- Nếu `proceed()` return, `outcome` đổi sang `"RETURNED"`; nếu throw, nó giữ `"THROWN"`.
- `finally` đặt kết quả cuối cùng vào `ConcurrentHashMap`. Bản ghi `Observation` là Java record immutable.
- Demo dùng `id` duy nhất `A`/`B` làm key. Trong production **phải dùng invocation id thực sự unique** hoặc aggregation design khác; hai calls có cùng business id không nên vô tình ghi đè nhau.
- `records` là **field shared** nhưng an toàn khi nhiều threads `put` đồng thời nhờ `ConcurrentHashMap`; nó dành cho kết quả đã hoàn thành, không chứa những timestamps đang xử lý.
- Advice **không đổi exception/result**: trả đúng `result`, và khi `proceed()` throw thì `finally` xong, exception vẫn tiếp tục đi ra.
- `elapsedNanos` được lưu nhưng **không in giá trị đo** vì duration thực tế thay đổi theo môi trường.

**Điểm kiểm chứng chính:** Khi A và B overlap trong target, cả hai đều chạy **cùng `TraceAspect` instance** nhưng locals không đè nhau. Sau khi hai futures hoàn tất, map chứa `A→RETURNED` và `B→THROWN`.

### 7.6. Cấu hình Spring AOP

`src/main/java/demo/local/AppConfig.java`:

```java
package demo.local;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public Gate gate() {
        return new Gate();
    }

    @Bean
    public WorkService workService(Gate gate) {
        return new WorkService(gate);
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@Aspect` một mình **không đăng ký bean**. `@Bean traceAspect()` tạo aspect trong Spring container; `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật Spring AOP và ép class-based proxy cho target `WorkService` không khai báo service interface.

`Gate` là shared Spring bean nhưng dùng các primitives `CountDownLatch` thread-safe. `TraceAspect` là shared bean chứa một map concurrent, còn mỗi lời gọi `observe(...)` có local state riêng.

### 7.7. Main thực thi hai threads và in kết quả ổn định

`src/main/java/demo/local/DemoApplication.java`:

```java
package demo.local;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkService service = context.getBean(WorkService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);
            Gate gate = context.getBean(Gate.class);

            ExecutorService pool = Executors.newFixedThreadPool(2);

            try {
                Future<String> a =
                    pool.submit(() -> service.handle("A"));

                Future<String> b = pool.submit(() -> {
                    try {
                        return service.handle("B");
                    } catch (IllegalStateException ex) {
                        return ex.getClass().getSimpleName()
                            + ":" + ex.getMessage();
                    }
                });

                // Bảo đảm cả hai lời gọi đã vào target trước khi mở gate.
                gate.awaitBothEntered();
                gate.open();

                String aValue = a.get();
                String bValue = b.get();

                System.out.println("proxy="
                    + AopUtils.isAopProxy(service));
                System.out.println("overlapped=true");
                System.out.println("A=" + aValue);
                System.out.println("B=" + bValue);
                System.out.println("traceA="
                    + aspect.outcomeFor("A"));
                System.out.println("traceB="
                    + aspect.outcomeFor("B"));
                System.out.println("recorded="
                    + aspect.recordedCount());

            } finally {
                gate.open();
                pool.shutdownNow();
            }
        }
    }
}
```

**Tại sao stdout không phụ thuộc race?**
- `CountDownLatch entered` đợi **cả hai invocations** đã tới code target.
- Main mở `release` sau khi chúng đều đã đi vào, đảm bảo thời gian overlap.
- Không in trực tiếp từ target, advice hoặc worker threads, chỉ in **sau khi `a.get()` và `b.get()` xong**.
- Vì `Future.get()` hoàn thành sau khi advice đã chạy xong `finally`, các entries đã nằm trong concurrent map khi main đọc.
- `A`/`B` là keys riêng nên order `put` không ảnh hưởng kết quả được đọc.
- `pool.shutdownNow()` dùng trong `finally` để giải phóng resources cả khi có lỗi; `gate.open()` đảm bảo không để worker chờ gate vô hạn.

### 7.8. Chạy bằng Gradle

Từ thư mục project có `build.gradle`:

```bash
gradle run
```

Nếu đã cài Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

**Stdout do Java code in ra** khi các tasks hoàn thành trong khoảng timeout cấu hình:

```text
proxy=true
overlapped=true
A=OK-A
B=IllegalStateException:failed-B
traceA=RETURNED
traceB=THROWN
recorded=2
```

Các dòng Gradle hoặc logging hệ thống không nằm trong khối stdout này. Nếu máy không thể khởi tạo hai workers hoặc bị treo quá 10 giây, demo báo timeout thay vì khẳng định kết quả trong điều kiện môi trường không được đáp ứng.

### 7.9. Giải thích chứng minh

| Yếu tố | Invocation A | Invocation B |
| --- | --- | --- |
| Target call | `service.handle("A")` | `service.handle("B")` |
| Kết cục của `proceed()` | Return `"OK-A"` | Throw `IllegalStateException("failed-B")` |
| Local `invocationId` | `"A"` | `"B"` |
| Local `outcome` sau proceed | `"RETURNED"` | `"THROWN"` |
| Chạy `finally` | Có | Có |
| Dữ liệu aggregate | `records["A"] = Observation("RETURNED", ...)` | `records["B"] = Observation("THROWN", ...)` |

Cả A và B cùng dùng **một instance `TraceAspect`**, nhưng không có `currentId` hoặc `startedNanos` field để chúng tranh nhau ghi. Dùng locals nghĩa là không có trường shared để rò rỉ identifier hay timestamp của B sang A.

### 7.10. Nếu bỏ @Around, gọi trực tiếp target?

Lời gọi:

```java
WorkService service = new WorkService(new Gate());
```

tạo object ngoài Spring container; nó không phải proxy nên `TraceAspect.observe` **không tự chạy**. Ví dụ trên chỉ là minh họa về proxy boundary, **không tự chạy được như project ở phần 7** vì cần điều khiển `Gate` và threads đúng cách.

Lời gọi nội bộ kiểu `this.handle("A")` từ một method của chính `WorkService` cũng bypass Spring AOP proxy; advice method và locals của advice **không được khởi tạo** cho lời gọi nội bộ ấy. Không thể giải quyết self-invocation chỉ bằng đổi field thành local.

## 8. `ThreadLocal` không phải lựa chọn mặc định cho timer

`@Before` và `@After` là hai method calls khác nhau nên không thể trực tiếp dùng chung một local `started`; đó là lý do `@Around` thuận tiện hơn. Dùng `ThreadLocal<Long>` để truyền timestamp giữa chúng đưa thêm các nghĩa vụ: xóa/restore trong `finally`, bảo toàn outer state nếu nested advice chạy cùng thread, kiểm tra thread pool reuse và xử lý lúc advisor không được đi vào vì pointcut/ordering.

Khi bắt buộc dùng context theo thread, nên giữ previous value để trả lại outer scope:

```java
String previous = traceId.get();
traceId.set(currentId);
try {
    return pjp.proceed();
} finally {
    if (previous == null) traceId.remove();
    else traceId.set(previous);
}
```

Đây là fragment cần `traceId`, `currentId`, `pjp`. State của một advice invocation đơn lẻ vẫn nên là local; chuyên bài ThreadLocal sẽ triển khai cleanup, MDC, nested calls và thread hops đầy đủ.

## 9. Local state khi chuyển sang `@Async`, `CompletableFuture` hoặc Reactor

Local variables tiếp tục **cách ly các lần advice được gọi**, nhưng khoảng lifetime mà chúng mô tả phụ thuộc vào điểm intercept. Nếu `@Async` có async advisor ngoài `@Around`, phần code target/advice trong worker có thể diễn ra ở thread khác caller. Nếu `@Around` đo phía caller, nó có thể chỉ thấy thời gian submit và future được trả về. Phải quan sát advisor ordering và proxy path thực tế trước khi đặt tên metric.

```java
@Around("execution(* com.example.service..*.loadAsync(..))")
public Object measureCall(ProceedingJoinPoint pjp) throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        System.out.println("method-boundary-ns=" + (System.nanoTime() - start));
    }
}
```

Snippet đo đúng **method execution boundary**, không hứa đo được completion của một `CompletableFuture` còn pending. Với Reactor `Mono`/`Flux`, trả publisher có thể xảy ra trước subscription; muốn đo mỗi subscription, tạo timestamp bên trong `defer` và dùng `doFinally` phù hợp. Cả hai trường hợp đều không có lý do chuyển timestamp của một invocation thành mutable singleton field.

Các bài về `@Async` và reactive pipeline phía sau dạy riêng vấn đề thread/context propagation, completion, lỗi và cancellation.

## 10. Invocation lồng nhau và retry: local state có còn đúng không?

### 10.1. Nested invocation qua proxy

Nếu một service method A gọi method B **qua một Spring-managed proxy** và cả hai match cùng `@Around`, Spring gọi advice hai lần:

```text
A advice frame:
  local startedA
  proceed A
    -> B advice frame:
         local startedB
         proceed B
         finally elapsedB
  finally elapsedA
```

`startedA` và `startedB` là locals khác nhau ngay cả khi cả hai lời gọi xảy ra **trên cùng thread**. Đây là lợi thế so với một `ThreadLocal<Long>` đơn lẻ bị overwritten ở lần B.

Nếu A gọi `this.B()` bên trong cùng target và bypass proxy, sẽ **không có B advice frame**, nên điều này không phải bằng chứng local bị lẫn — đơn giản là Spring AOP không chặn B.

### 10.2. Retry với nhiều lần proceed()

Spring `@Around` được phép gọi `pjp.proceed()` nhiều lần. Nếu một invocation tạo local `started` trước loop rồi thực hiện ba attempts, timestamp đo **toàn bộ retry scope**, không phải thời gian từng attempt.

Muốn mỗi attempt có thời gian riêng:

```java
for (int attempt = 1; attempt <= 3; attempt++) {
    long attemptStart = System.nanoTime();
    try {
        Object result = pjp.proceed();
        recordAttempt(attempt, System.nanoTime() - attemptStart);
        return result;
    } catch (RetryableException ex) {
        recordAttempt(attempt, System.nanoTime() - attemptStart);
        if (attempt == 3) {
            throw ex;
        }
    }
}
throw new AssertionError("unreachable");
```

**Snippet thuật toán** cần định nghĩa `RetryableException`/`recordAttempt(...)` và thêm nó trong `@Around` với `throws Throwable`. Đây không phải mã production: retry cần backoff, idempotency, timeout và transaction semantics. Ý chính: local `attemptStart` là **per-attempt**, còn local `started` bên ngoài vòng lặp là **per-around-invocation**. Bạn phải chọn đúng scope muốn đo.

Một lời gọi của caller có thể gồm nhiều attempts và multiple target executions. Đừng coi `one @Around invocation = exactly one target execution` nếu chính advice của bạn hoặc retry advisor gọi `proceed()` nhiều lần.

## 11. Những ngoại lệ mà local state không tự giải quyết

### 11.1. Mutable target arguments

```java
Object[] args = pjp.getArgs();
SomeMutableDto dto = (SomeMutableDto) args[0];
```

Các biến `args` và `dto` là local **references**, nhưng DTO object có thể là shared mutable argument được nhiều threads truyền vào. Nếu advice mutate `dto` không đồng bộ, vẫn có race.

Muốn ghi snapshot cho audit, chỉ lưu những trường cần thiết thành immutable values, hoặc tạo defensive copy theo semantics của DTO.

### 11.2. Shared dependency của aspect

```java
private final SimpleDateFormat formatter = new SimpleDateFormat("...");
```

Nếu nhiều advice invocations cùng gọi shared formatter không thread-safe, việc đổi timestamp sang local **không sửa vấn đề ở dependency**. Dùng thread-safe API như `java.time.format.DateTimeFormatter`, immutable configuration hoặc synchronization hợp lý trong dependency.

### 11.3. Chính advice ghi log hoặc metrics có thể ném exception

Nếu `finally` dùng một mutable logger/sink sai cách hoặc ném exception, kết cục nghiệp vụ có thể bị thay đổi. Local variable giúp chống state interleaving; nó không bảo đảm logging backend luôn an toàn. Cần có policy instrumentation-failure rõ: metric có thể bị drop? Audit bắt buộc thì rollback? Ai quan sát sự cố sink?

### 11.4. Dữ liệu bí mật không nên vào logs

`pjp.getArgs()` có thể chứa password/token/PII. Local snapshot không làm dữ liệu an toàn hơn về quyền riêng tư. Chỉ log metadata đã allowlist, che thông tin bí mật, và không giữ object graph lớn trong map singleton khiến memory retention.

### 11.5. Context boundary và nhiều ApplicationContexts

Aspect singleton là theo **container scope** thực tế; ứng dụng có nhiều `ApplicationContext` có thể tạo nhiều aspect instances. Không suy luận từ “singleton Spring bean” rằng mọi application trong JVM cùng dùng đúng một object. Trái lại, một singleton aspect trong một context vẫn phục vụ nhiều threads, nên per-invocation locals luôn hữu ích.

## 12. Ma trận lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Log request A in ID của B | Field `currentRequestId` bị threads ghi đè | Chuyển ID thành local trong `@Around` |
| Duration sai khi gọi đồng thời | Shared field `startedNanos` bị overwrite | Đặt `startedNanos` trong scope invocation |
| Thêm `volatile` vẫn sai | Visibility không tạo per-invocation copies | Dùng local; chọn shared-state design đúng |
| `synchronized` làm throughput giảm mạnh | Serializes whole advice/target invocation | Bỏ shared-state dependency thay vì lock cả method |
| Số lượt hoàn thành nhỏ hơn thực tế | `counter++` trên singleton aspect bị lost update | `AtomicLong`/`LongAdder` hoặc metrics backend |
| ThreadLocal của request trước còn ở request mới | Quên `remove()` trong pooled thread | Dùng `try/finally` và restore/remove đúng |
| Nested method B làm duration A sai | `ThreadLocal<Long>` bị overwriting bởi B | Dùng nested locals của `@Around` hoặc stack/context có thiết kế |
| Async future còn chạy nhưng around đã in completed | Đo method return thay vì async task completion | Instrument completion stage / tracing framework |
| Reactor Mono mới được tạo đã thấy “duration” | Method trả publisher trước khi subscription xử lý | Dùng Reactor operators/context theo subscription |
| Map aggregate ghi sai khi same business ID | Key không unique per invocation | Dùng invocation ID duy nhất, tránh silent overwrite |
| Map quan sát tăng mãi | Không có eviction/retention policy | Xóa/TTL/metrics backend, không giữ mọi invocation vô hạn |
| Aspect không chạy khi gọi `this.method()` | Self-invocation bypass proxy | Tách Spring collaborator, gọi qua proxy |
| Local chứa DTO nhưng data vẫn race | Reference local trỏ tới shared mutable DTO | Snapshot immutable/copy hoặc synchronize dependency |
| Advice không chạy vì không có proxy | Aspect chưa là bean, chưa bật AOP, pointcut mismatch | Kiểm tra registration, `AopUtils.isAopProxy` và method signature |
| Logging exception che lỗi gốc | `finally` tự throw | Tách instrumentation failure policy và preserve cause |
| Concurrency test lúc pass lúc fail | Test phụ thuộc thread scheduling | Dùng `CountDownLatch`/phối hợp deterministic và xác minh sau `Future.get()` |

## 13. Checklist review một Spring Aspect có state

- [ ] Mỗi giá trị gắn với **một invocation** (`started`, `id`, `error`, `result`) được lưu dưới dạng local.
- [ ] Không có singleton mutable fields chỉ phục vụ “current request” hoặc “current method invocation”.
- [ ] `@Around` return đúng `pjp.proceed()` và rethrow exception khi không có fallback policy.
- [ ] `finally` ghi nhận cleanup/timing cho cả normal và throwing completion, không `return`/`throw` ngoài chủ đích.
- [ ] Mutable shared counters dùng primitive/thread-safe implementation phù hợp.
- [ ] Shared maps dùng concurrent collection, key unique và có retention policy.
- [ ] Không hiểu `final` reference là deep immutability của object mà nó trỏ tới.
- [ ] Không dùng `ThreadLocal` cho việc có thể giải quyết đơn giản bằng `@Around` local variables.
- [ ] Nếu dùng ThreadLocal, restore/remove trong finally và kiểm thử nested invocation/thread reuse.
- [ ] Đã xác định async/reactive boundary: cần đo method call hay entire task/subscription?
- [ ] Nested calls, retries và nhiều `proceed()` có scope đo tường minh.
- [ ] Advice không log dữ liệu nhạy cảm hoặc giữ object graph lớn trong singleton state.
- [ ] Spring `@Aspect` thực sự là Spring bean; target qua Spring-managed proxy và pointcut khớp.
- [ ] Có test đồng thời thật, không chỉ test tuần tự; không phụ thuộc thứ tự threads trong stdout.
- [ ] Có test normal return và thrown exception để xác nhận per-invocation state không bị lẫn.

## 14. Kết luận

Đối với **Spring Aspect**, cách an toàn và đơn giản nhất để giữ dữ liệu riêng cho một lời gọi là **biến cục bộ trong một `@Around` advice**:

```java
@Around("execution(* com.example.service..*.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        // elapsed thuộc đúng một advice invocation.
    }
}
```

Từ đó phân biệt rõ:
- **Local state per invocation:** timestamp, argument snapshot, outcome, failure, temporary buffer.
- **Shared state across invocations:** aggregate metrics, counters, audit storage — cần thread-safe mechanism và lifecycle rõ ràng.
- **Thread-bound/reactive context:** chỉ dùng khi nhu cầu vượt phạm vi một advice invocation, có context propagation và cleanup phù hợp.

Spring AOP chỉ áp dụng advice khi lời gọi đi qua **Spring-managed proxy**. Biến local bảo vệ dữ liệu của **advice invocation thật sự tồn tại**; nó không khiến self-invocation tự được advise, không tự tách shared mutable DTO, và không biến một synchronous `@Around` thành bộ đo full asynchronous task duration.

### Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice, Around Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): Spring khuyến nghị around advice khi cần chia sẻ state trước–sau invocation theo cách thread-safe, `ProceedingJoinPoint.proceed()` và return/throw.
- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html): singleton aspect mặc định, `perthis`/`pertarget`/`pertypewithin` và giới hạn `percflow`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, call path, self-invocation.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): đăng ký và kích hoạt aspects trong Spring context.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): phạm vi method-execution join points và semantics các loại advice.
- [Spring Framework — Asynchronous Execution](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): execution context của `@Async` và task scheduling.
