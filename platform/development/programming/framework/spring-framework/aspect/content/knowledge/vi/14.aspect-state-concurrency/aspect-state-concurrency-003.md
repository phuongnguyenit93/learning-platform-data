# Nguy cơ lưu JoinPoint, người dùng hoặc thời gian bắt đầu vào field của Spring Aspect

## 1. Lỗi dữ liệu nghiêm trọng hơn sai số đo

Khi audit aspect giữ một `ProceedingJoinPoint`, current actor hoặc start timestamp trong mutable instance fields, request A có thể **ghi nhận tên người dùng hoặc đối số của request B** dù business result của A vẫn đúng. Trong Spring AOP, `@Aspect` là Spring bean thường có một singleton instance trong context; những fields đó không đại diện riêng cho invocation nào.

```java
@Aspect
public class UnsafeAuditAspect {
    private ProceedingJoinPoint currentJoinPoint;
    private String currentActor;

    @Around("execution(* com.example..service.*.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        currentJoinPoint = pjp;
        currentActor = currentActorId(); // helper giả định
        try {
            return pjp.proceed();
        } finally {
            auditSink.write(currentActor, currentJoinPoint); // helper giả định
        }
    }
}
```

Đây là **anti-pattern minh họa**, không phải ví dụ chạy độc lập. Sai lầm còn có thể gây giữ dữ liệu nhạy cảm lâu trong bộ nhớ, nhất là khi lưu cả `JoinPoint`/arguments/target. Bài này tập trung vào **giới hạn vòng đời `JoinPoint`, snapshot identity có kiểm soát và rủi ro audit xuyên yêu cầu**; bài biến cục bộ ngay trước đó giải thích tổng quát về stack frame và timer.

## 2. Cái gì được phép giữ sau invocation?

| Giá trị | Cách sử dụng thích hợp | Rủi ro khi giữ trên singleton aspect |
| --- | --- | --- |
| `ProceedingJoinPoint` | Đọc signature/args và gọi `proceed()` trong advice hiện tại | Lẫn invocation, giữ reference đến target/proxy/arguments |
| Actor từ `SecurityContextHolder` | Chụp **ID đã cho phép ghi audit** vào local | Giữ security principal hoặc token qua request |
| Thời điểm bắt đầu | `long started = System.nanoTime()` local để đo elapsed | Time của request B ghi đè A |
| `Throwable`/result | Xử lý trong `catch/finally` của invocation | Rò rỉ lỗi/kết quả request khác |
| `AuditSink` hoặc `MeterRegistry` | Inject dependency có contract concurrency và retention rõ | Chính sink vẫn có thể không thread-safe |

Không dùng `JoinPoint` như một background command có thể `proceed()` tùy ý sau khi advice kết thúc. Nếu cần truyền thông tin cho queue/audit storage, trích xuất scalar snapshot được phép lưu rồi chuyển cho sink thread-safe; `pjp.getArgs().clone()` chỉ tạo shallow copy, không đóng băng object graph.

## 3. Timeline chứng minh nhầm danh tính

```text
T1 (Alice): currentActor = "alice"; currentJoinPoint = jpAlice
T1 (Alice): vào target rồi chờ I/O
T2 (Bob):   currentActor = "bob";   currentJoinPoint = jpBob
T1 (Alice): target trả về; finally đọc actor "bob" và jpBob
```

Đây là một lịch xen kẽ hợp lệ, đủ để chứng minh shared fields **không diễn đạt được identity của một invocation**. `volatile` hoặc `AtomicReference` có thể cải thiện visibility/atomic reference operations nhưng vẫn chỉ giữ dữ liệu của invocation cập nhật gần nhất. Khóa riêng từng phép gán không bảo vệ vòng đời của target call. Khóa toàn bộ `@Around` làm tuần tự hóa nghiệp vụ và không giải quyết callback async, nhiều context hay advice bypass proxy.

Demo mục 7 tạo timeline Alice/Bob bằng `CountDownLatch`, rồi so sánh `unsafe(alice)=bob` với local snapshot `safe(alice)=alice`. Không cần log credentials hay dữ liệu người dùng thật để kiểm thử hiện tượng này.

## 4. Giữ `ProceedingJoinPoint` trong field còn có rủi ro vòng đời và bảo mật

`ProceedingJoinPoint` cho phép đọc signature, arguments, proxy, target và chuyển tiếp invocation bằng `proceed()`. Nó gắn với **lời gọi đang được advice**.

```java
@Aspect
public class BadJoinPointCache {
    private ProceedingJoinPoint saved;

    @Around("execution(* com.example..service.*.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        saved = pjp;         // Sai: lưu invocation vào shared field.
        return pjp.proceed();
    }
}
```

Đây là fragment phản ví dụ. Ba vấn đề:

1. **Sai invocation:** request khác thay `saved`; callback/log đọc nhầm tên method, target hoặc arguments.
2. **Giữ object graph quá lâu:** join point có thể tham chiếu đến arguments, proxy, target và invocation chain; giữ lâu có thể giữ PII, credentials, mutable DTOs và bộ nhớ.
3. **Lạm dụng `proceed()`:** đừng lưu `pjp` để một thread hoặc event callback khác gọi `saved.proceed()` sau khi advice đã return. `pjp` không phải general-purpose background command; nó mang invocation context/interceptor chain của thời điểm gọi.

Đúng hơn, trích xuất metadata tối thiểu trong local scope:

```java
final String methodName = pjp.getSignature().getName();
final String actorId = actorProvider.currentActorId();
final long startedNanos = System.nanoTime();
```

Đây là **fragment** cần `actorProvider`. Sau đó chỉ gửi `methodName`, `actorId` được cho phép và elapsed duration sang audit/metrics sink. Không giữ raw `pjp` hoặc toàn bộ `Object[] args` lâu hơn cần thiết.

### Copy mảng đối số không phải copy toàn bộ dữ liệu

```java
Object[] arguments = pjp.getArgs().clone();
```

Thao tác này chỉ **shallow-copy** array; nếu phần tử là object mutable, nội dung object có thể tiếp tục thay đổi. Không nên log nguyên argument graph hoặc lưu mảng không giới hạn. Nếu cần immutable snapshot cho audit, định nghĩa DTO ghi nhận **các trường scalar được cho phép** với chính sách redaction rõ ràng.

## 5. Thiết kế an toàn: biến local trong `@Around`

```java
@Around("execution(public * com.example..service.*.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    final String method = pjp.getSignature().getName();
    final String actor = actorProvider.currentActorId();
    final long startedNanos = System.nanoTime();
    String outcome = "SUCCESS";

    try {
        return pjp.proceed();
    } catch (Throwable error) {
        outcome = "FAILURE";
        throw error;
    } finally {
        long elapsed = System.nanoTime() - startedNanos;
        auditRecorder.record(actor, method, outcome, elapsed);
    }
}
```

Đây là **production-style fragment**, chưa phải chương trình độc lập vì cần `actorProvider` và `auditRecorder` được inject. Điểm đúng:

- `actor` và `startedNanos` thuộc stack frame của **invocation hiện tại**.
- `pjp` được sử dụng trong phạm vi advice đang thực thi, không bị copy sang singleton field.
- `auditRecorder` có thể là shared dependency, với điều kiện implementation chịu được concurrency và quản lý data retention.
- `finally` quan sát normal return và synchronous exception.
- Throw lại lỗi gốc giúp giữ method exception semantics; đừng nuốt Throwable vô tình.

**Lưu ý:** Nếu `auditRecorder.record(...)` tự ném exception trong `finally`, nó có thể che exception gốc. Cần policy telemetry failure rõ ràng, ví dụ xử lý logging sink failures có kiểm soát để không làm sai business operation, nếu yêu cầu hệ thống cho phép.

### `System.nanoTime()` đúng cho elapsed duration

Dùng `System.nanoTime()` để đo khoảng thời gian trong cùng JVM; không dùng nó như epoch timestamp. `System.currentTimeMillis()` hoặc `Instant.now()` phù hợp ghi thời điểm lịch sử, nhưng wall clock có thể được hiệu chỉnh, nên không lý tưởng để đo latency ngắn.

Tránh `private long startNanos` trên singleton aspect. Nếu A và B overlap, hiệu `now - startNanos` có thể thuộc về B và không phản ánh duration của A.

**Nếu target trả Future/Publisher:** thời gian từ trước tới sau `pjp.proceed()` đo **lúc Java method trả handle/publisher**, không tự đo Future completion hoặc reactive terminal signal. Muốn metric completion phải gắn callback/Publisher operator với **snapshot data cục bộ**, không giữ `ProceedingJoinPoint` để dùng bất đồng bộ.

## 6. Lấy người dùng hiện tại trong Spring: đọc xong, snapshot local

Với Spring Security servlet stack, một ứng dụng có thể đọc:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String actorId =
        authentication == null ? "anonymous" : authentication.getName();
```

Đây là fragment Spring Security; cần imports `Authentication` và `SecurityContextHolder`. Default strategy thường dùng thread-bound security context, nhưng ứng dụng có thể cấu hình khác. Không suy rằng principal hiện tại luôn có thể đọc từ thread bất kỳ.

Không làm:

```java
private Authentication currentAuth;

@Before("serviceOperation()")
public void capture() {
    currentAuth = SecurityContextHolder.getContext().getAuthentication();
}

@AfterReturning("serviceOperation()")
public void log() {
    // currentAuth có thể thuộc về lời gọi khác.
}
```

Đây là **anti-pattern**. `@Before` và `@AfterReturning` là hai advice invocations khác nhau; shared field không phải kênh trao đổi per-request đáng tin cậy. Ngay cả khi identity không đổi trong một request, các requests có thể xen kẽ.

Đúng hơn, snapshot **actor ID đã được cho phép dùng** vào local variable của **một `@Around`**, rồi truyền tới audit sink. Không nên giữ `Authentication` hoặc raw principal/token nếu không thực sự cần.

### Người dùng không chỉ đến từ HTTP request

Spring Aspect có thể được kích hoạt từ scheduled jobs, message listeners, batch executors, integration tests hoặc CLI. Những lời gọi đó có thể không có servlet request hoặc authenticated user. `actorProvider` cần định nghĩa rõ fallback như `system-job`/`anonymous` tùy policy, thay vì ngầm giả định `SecurityContextHolder.getContext().getAuthentication()` luôn khác null.

Với đa tenant, không dùng một field `currentTenant` trên aspect làm policy source of truth. Một request tenant A bị gắn ID tenant B có thể biến vấn đề observability thành lỗi data isolation nghiêm trọng.

## 7. Demo Java 17+ chạy được: hai calls đồng thời, output xác định

Demo này chứng minh lỗi chia sẻ field trên **một Spring singleton aspect**, không dựa vào race ngẫu nhiên.

Các bước:

1. Thread Alice gọi `service.process("alice")` qua Spring proxy; aspect ghi fields `alice`, target chờ ở gate.
2. Main xác nhận Alice đã tới target.
3. Thread Bob gọi `service.process("bob")` qua **cùng proxy**; aspect ghi đè fields thành `bob`, target chờ.
4. Main xác nhận Bob tới target rồi mới mở gate.
5. Hai calls hoàn tất; main in **sau khi lấy cả hai `Future.get()`**, nên thứ tự output ổn định.

Aspect sẽ lưu một snapshot **unsafe** (đọc từ shared fields) và **safe** (đọc từ local variables) vào `ConcurrentHashMap` chỉ để so sánh. Đây là ví dụ giáo dục, **không khuyến nghị** giữ raw request data trong map của aspect trên production.

Môi trường cố định: **JDK 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Maven**. Đây là versions minh họa, không tuyên bố mới nhất.

### 7.1. Cấu trúc project

```text
spring-aop-invocation-scope/
├── pom.xml
└── src/main/java/com/example/scope/
    ├── GatedService.java
    ├── SnapshotAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-invocation-scope</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp Spring application context và những Spring AOP dependencies trong cây phụ thuộc; `aspectjweaver` hỗ trợ parsing/matching của `@AspectJ` expressions. Không cần web server hoặc AspectJ weaving agent.

### 7.3. `src/main/java/com/example/scope/GatedService.java`

```java
package com.example.scope;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class GatedService {
    private final CountDownLatch aliceEntered = new CountDownLatch(1);
    private final CountDownLatch bobEntered = new CountDownLatch(1);
    private final CountDownLatch releaseGate = new CountDownLatch(1);

    public String process(String user) {
        if ("alice".equals(user)) {
            aliceEntered.countDown();
        } else if ("bob".equals(user)) {
            bobEntered.countDown();
        } else {
            throw new IllegalArgumentException("Unknown demo user");
        }

        try {
            releaseGate.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }

        return "ok:" + user;
    }

    public void awaitAlice() throws InterruptedException {
        if (!aliceEntered.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout waiting for alice");
        }
    }

    public void awaitBob() throws InterruptedException {
        if (!bobEntered.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout waiting for bob");
        }
    }

    public void release() {
        releaseGate.countDown();
    }
}
```

`CountDownLatch` đảm bảo thứ tự **Alice vào target trước, Bob vào target sau, rồi cả hai mới được phép rời target**. Các method điều khiển `awaitAlice`/`awaitBob`/`release` không khớp pointcut, nên không ghi đè aspect fields.

### 7.4. `src/main/java/com/example/scope/SnapshotAspect.java`

```java
package com.example.scope;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class SnapshotAspect {
    // CỐ TÌNH SAI: per-invocation state nằm trong singleton fields.
    private volatile String sharedUser;
    private volatile ProceedingJoinPoint sharedJoinPoint;
    private volatile long sharedStartNanos;

    // Chỉ dùng trong DEMO để ghi snapshots thread-safe.
    private final ConcurrentMap<String, String> unsafe =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<String, String> safe =
            new ConcurrentHashMap<>();

    @Around(
        value = "execution(public java.lang.String "
              + "com.example.scope.GatedService.process(..))"
              + " && args(user)",
        argNames = "user"
    )
    public Object around(ProceedingJoinPoint pjp, String user)
            throws Throwable {
        // ĐÚNG: mỗi invocation có local snapshot riêng.
        final String localUser = user;
        final ProceedingJoinPoint localJoinPoint = pjp;
        final long localStarted = System.nanoTime();

        // SAI: mỗi call ghi đè slot chung.
        sharedUser = user;
        sharedJoinPoint = pjp;
        sharedStartNanos = localStarted;

        try {
            return pjp.proceed();
        } finally {
            unsafe.put(user,
                    "fieldUser=" + sharedUser
                    + ", fieldJoinArg=" + sharedJoinPoint.getArgs()[0]);

            safe.put(user,
                    "localUser=" + localUser
                    + ", localJoinArg=" + localJoinPoint.getArgs()[0]);

            // Đo timing bằng localStarted, KHÔNG bằng sharedStartNanos.
            long elapsed = System.nanoTime() - localStarted;
            // elapsed được cố ý không in để giữ stdout xác định.
        }
    }

    public String unsafeFor(String user) {
        return unsafe.get(user);
    }

    public String safeFor(String user) {
        return safe.get(user);
    }
}
```

Các fields `sharedUser`/`sharedJoinPoint`/`sharedStartNanos` được viết **cố ý sai** để chứng minh race; `volatile` giúp các threads nhìn thấy updates nhưng không tạo isolation. Khi Bob vào target, shared fields cuối cùng là của Bob. Gate chỉ mở **sau** sự kiện ấy, nên cuối hai invocations đều đọc field của Bob.

`localUser`, `localJoinPoint` và `localStarted` vẫn riêng cho lời gọi đang thực thi. `ConcurrentHashMap` chỉ giúp main in snapshots sau completion mà không phát sinh thêm data race trong test; đừng copy nó thành unbounded production storage của user data.

### 7.5. `src/main/java/com/example/scope/AppConfig.java`

```java
package com.example.scope;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public GatedService gatedService() {
        return new GatedService();
    }

    @Bean
    public SnapshotAspect snapshotAspect() {
        return new SnapshotAspect();
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass=true)` bật Spring proxy-based AOP; CGLIB class proxy được dùng vì `GatedService` không implement interface. `SnapshotAspect` được đăng ký làm Spring bean bằng `@Bean`; `@Aspect` đơn lẻ chưa đăng ký bean.

### 7.6. `src/main/java/com/example/scope/DemoApp.java`

```java
package com.example.scope;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            GatedService service = context.getBean(GatedService.class);
            SnapshotAspect aspect = context.getBean(SnapshotAspect.class);
            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));

            ExecutorService executor = Executors.newFixedThreadPool(2);
            try {
                Future<String> alice =
                        executor.submit(() -> service.process("alice"));
                service.awaitAlice();

                Future<String> bob =
                        executor.submit(() -> service.process("bob"));
                service.awaitBob();
                service.release();

                String aliceResult = alice.get(10, TimeUnit.SECONDS);
                String bobResult = bob.get(10, TimeUnit.SECONDS);

                System.out.println("resultAlice=" + aliceResult);
                System.out.println("resultBob=" + bobResult);
                System.out.println("unsafe(alice)=" + aspect.unsafeFor("alice"));
                System.out.println("unsafe(bob)=" + aspect.unsafeFor("bob"));
                System.out.println("safe(alice)=" + aspect.safeFor("alice"));
                System.out.println("safe(bob)=" + aspect.safeFor("bob"));
            } finally {
                service.release();
                executor.shutdownNow();
            }
        }
    }
}
```

Hai threads gọi **cùng Spring-managed proxy**. Main đợi kết quả futures trước khi in nên worker A/B hoàn thành theo thứ tự nào cũng không làm thay đổi **thứ tự các dòng stdout do main in ra**. Nếu timeout xảy ra trên môi trường quá chậm, ví dụ sẽ báo lỗi thay vì cho một kết luận sai.

### 7.7. Chạy và stdout dự kiến

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.scope.DemoApp
```

Trong điều kiện không timeout, các dòng do code tạo ra:

```text
isAopProxy=true
resultAlice=ok:alice
resultBob=ok:bob
unsafe(alice)=fieldUser=bob, fieldJoinArg=bob
unsafe(bob)=fieldUser=bob, fieldJoinArg=bob
safe(alice)=localUser=alice, localJoinArg=alice
safe(bob)=localUser=bob, localJoinArg=bob
```

Diễn giải:

1. Spring trả AOP proxy cho `GatedService`, không phải raw object được caller tự `new`.
2. Alice vào advice, gán shared fields, rồi đứng chờ trong target.
3. Bob vào **cùng singleton aspect**, ghi đè fields thành dữ liệu Bob, rồi cũng đứng chờ.
4. Main mở gate; target của Alice/Bob lần lượt có thể rời trước/sau tùy scheduler, nhưng cả hai trả đúng kết quả nghiệp vụ.
5. Cả hai unsafe snapshots nhìn **cùng slot cuối cùng** là Bob, nên Alice bị gán nhầm identity và join point.
6. Hai safe snapshots dùng **local variables** nên mỗi call được ghi đúng identity.

Đây là ví dụ có chủ đích chứng minh **cross-invocation data contamination**, không phải khuyến nghị ghi user ID thật vào log hoặc map. Code và stdout đã được rà soát tĩnh, chưa chạy Maven trên máy mục tiêu.

## 8. Cách tổ chức production-style

Một aspect production nên chứa **shared-safe dependencies**, không giữ mutable current invocation fields:

```java
@Aspect
public class SafeAuditAspect {
    private final ActorProvider actors;
    private final AuditSink sink;

    public SafeAuditAspect(ActorProvider actors, AuditSink sink) {
        this.actors = actors;
        this.sink = sink;
    }

    @Around("execution(public * com.example..service.*.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        final String actorId = actors.currentActorId();
        final String method = pjp.getSignature().getName();
        final long started = System.nanoTime();
        String outcome = "SUCCESS";

        try {
            return pjp.proceed();
        } catch (Throwable ex) {
            outcome = "FAILURE";
            throw ex;
        } finally {
            long duration = System.nanoTime() - started;
            sink.write(actorId, method, outcome, duration);
        }
    }
}
```

Đây là fragment cần interfaces `ActorProvider` và `AuditSink`. Một `AuditSink` thread-safe có thể ghi các sự kiện độc lập; không lưu “actor hiện tại” vào field của chính aspect. `actorId` nên là identifier được quyền ghi nhận, đã redacted/normalized theo policy.

Nếu `sink.write` có nguy cơ ném exception, cần quyết định chính sách xử lý để lỗi logging/telemetry không che lỗi nghiệp vụ nếu đó không phải yêu cầu. Nếu operation trả Future/Publisher, đo separately **method return** và **asynchronous completion**.

### Field nào hợp lý?

| Aspect field | Đánh giá |
| --- | --- |
| `private final AuditSink sink` | Đúng nếu implementation xử lý concurrency an toàn |
| `private final MeterRegistry registry` | Hợp lý theo contract thư viện |
| `private final String serviceName` | Immutable config |
| `private final AtomicLong totalCalls` | Có thể đúng nếu cố ý đếm tổng số calls |
| `private String currentUser` | Sai cho singleton aspect nhiều invocations |
| `private ProceedingJoinPoint lastJoinPoint` | Sai nếu dùng làm current invocation state hoặc lưu lâu |
| `private long startTime` | Sai làm timestamp cho invocation hiện tại |
| `private Throwable lastException` | Dễ trộn exceptions giữa requests |
| `private Map<String, Object> requests` không cleanup | Nguy cơ retention, PII và memory growth |

Cần phân biệt **shared aggregate state** (ví dụ counter) với **shared per-request state** (sai). Một counter thread-safe có thể dùng `LongAdder` hoặc Micrometer registry; nhưng đừng dùng counter để lưu user hay start time.

## 9. ThreadLocal không phải lời giải phổ quát

`ThreadLocal` có một slot **theo thread**, không phải theo Spring AOP invocation:

```java
private static final ThreadLocal<Long> STARTED = new ThreadLocal<>();

@Before("serviceOperation()")
public void before() {
    STARTED.set(System.nanoTime());
}

@After("serviceOperation()")
public void after() {
    long elapsed = System.nanoTime() - STARTED.get();
    STARTED.remove();
}
```

Đây là **fragment có nhiều rủi ro**, cần named pointcut. Các vấn đề:

- **Thread pool reuse:** quên `remove()` khiến request khác trên cùng worker thread thấy dữ liệu cũ.
- **Nested proxy calls:** cùng thread đi vào outer advice rồi inner advice, `STARTED.set` của inner **ghi đè** start time outer trước khi outer kết thúc.
- **Async callbacks:** Future completion có thể ở thread khác, không thấy ThreadLocal của caller.
- **Reactive Reactor:** có thể đổi scheduler/thread và nhiều subscriptions; cần `Reactor Context`/framework context propagation phù hợp.
- **Exception:** phải cleanup trong `finally`, không dựa vào normal return.
- **Ordering/matching:** hai advice riêng có thể không chạy đối xứng trong mọi cấu hình; không nên nối lifecycle qua ThreadLocal khi `@Around` local dễ hơn.

`InheritableThreadLocal` cũng không tự propagate an toàn vào worker pools đã tạo sẵn. Nếu bắt buộc dùng ThreadLocal để tương tác legacy API, hãy thiết kế **stack push/pop**, cleanup trong `finally`, handling nested invocation và thread hops. Với start time/actor của **chính một `@Around`**, local variables ít lỗi hơn.

### MDC: khôi phục context cũ

Nếu aspect gắn operation ID vào MDC, cần lưu giá trị cũ trong local rồi khôi phục:

```java
String previous = MDC.get("operationId");
try {
    MDC.put("operationId", safeOperationId);
    return pjp.proceed();
} finally {
    if (previous == null) {
        MDC.remove("operationId");
    } else {
        MDC.put("operationId", previous);
    }
}
```

Đây là fragment cần SLF4J `MDC`, `pjp` và `safeOperationId`. Việc khôi phục giúp nested calls, nhưng không tự giải quyết propagation qua thread khác. Đừng giữ raw security context/principal trong singleton aspect field.

## 10. Ngay cả một thread cũng có thể ghi đè field: reentrancy

```text
Thread 1:
  around(OuterService.run)  -> sharedStart = t1
     target outer
        -> gọi InnerService qua Spring proxy
           around(InnerService.work) -> sharedStart = t2
           target inner
           inner finally đọc t2
     outer finally đọc sharedStart=t2  <-- sai, phải là t1
```

Không cần đa luồng, **nested advice invocations trên cùng thread** cũng có thể overwite singleton field. Một `ThreadLocal<Long>` duy nhất cũng bị ghi đè trong nested calls.

**Đúng:** local `long started = System.nanoTime()` trong **mỗi** invocation của `@Around`.

Chú ý Spring AOP proxy boundary: nếu target gọi `this.otherMethod()`, đó là self-invocation bypass proxy thường thấy và không tạo một advisor invocation mới. Nhưng việc ấy không làm field-state an toàn, vì nested **cross-bean calls qua Spring proxy** vẫn xảy ra.

## 11. Thay đổi aspect instantiation có đủ để bảo vệ audit?

`perthis` và `pertarget` có thể liên kết instance aspect với proxy/target tương ứng theo cấu hình Spring hỗ trợ, nhưng **hai lời gọi cùng proxy/target vẫn có thể xảy ra đồng thời**. Prototype scope cũng không hứa tạo aspect mới cho từng method invocation. Vì vậy không thay field `currentActor` bằng một field trên per-target aspect rồi cho rằng audit đã được cách ly. Snapshot local và sink có concurrency contract rõ ràng vẫn là giải pháp phù hợp cho bài này.

## 12. Future, @Async và reactive Publisher

Một lời gọi Spring service có thể return:

- `CompletableFuture<T>` khi background task vẫn đang chạy.
- `Mono<T>` hoặc `Flux<T>` trước subscription, đặc biệt cold publisher.
- Handle từ task đã hoàn tất ngay, tùy implementation.

Nếu `@Around` chỉ đo `System.nanoTime()` quanh `pjp.proceed()`, nó đo **Java method invocation/assembly**, không tự đo Future completion/Publisher terminal signal.

Nếu cần đo completion:

```java
@Around("execution(* com.example.jobs.JobService.start(..))")
public Object monitor(ProceedingJoinPoint pjp) throws Throwable {
    final String methodName = pjp.getSignature().getName();
    final long started = System.nanoTime();

    CompletionStage<?> stage = (CompletionStage<?>) pjp.proceed();
    return stage.whenComplete((value, error) -> {
        long duration = System.nanoTime() - started;
        metrics.record(methodName, duration, error);
    });
}
```

Đây là **fragment** chỉ cho `CompletionStage` và cần `metrics`, không dành cho mọi `Future` thuần. Callback chỉ capture **methodName/start** (scalar local values), không capture raw `pjp` để truy cập sau khi original advice đã return.

Với Reactor, `@Around` có thể return publisher được decorate bằng `doOnSubscribe`/`doOnError`/`doFinally`, chú ý **một method return có thể có nhiều subscriptions**. Không tự `subscribe()` trong aspect chỉ để log vì có thể kích hoạt công việc thêm một lần. Không lưu `ProceedingJoinPoint` vào một lambda sống lâu chỉ để biết tên method; snapshot scalar metadata trước khi return.

Cần đánh giá thêm propagation của Spring Security context, Reactor `Context`, MDC và tracing khi callbacks chạy ở threads khác. Không cố dùng một shared `currentUser` field để “truyền context” sang async worker.

## 13. Kiểm thử và chẩn đoán

Một integration test đáng tin cho chủ đề này cần:

1. Bật Spring AOP, đăng ký aspect là Spring bean và lấy target qua `ApplicationContext`.
2. Dùng `AopUtils.isAopProxy(bean)` để xác minh proxy hiện diện; nhưng vẫn assert lời advice thực sự chạy.
3. Gọi **cùng proxy** từ hai threads với inputs/actor IDs phân biệt.
4. Dùng `CountDownLatch`/`CyclicBarrier` để tạo overlap có chủ đích; không trông chờ `Thread.sleep()` làm race “thỉnh thoảng” xuất hiện.
5. Assert event của A giữ đúng method/user/arguments của A và tương tự B.
6. Test nested calls: service A proxy → service B proxy → cùng aspect trên **một thread**.
7. Test exception path để cleanup/timing không bị bỏ qua.
8. Nếu dùng ThreadLocal/MDC, kiểm tra cleanup sau requests và reuse executor threads.
9. Với Future/Publisher, kiểm tra method return **khác** async completion/reactive terminal.
10. Kiểm tra data retention: audit sink không vô hạn giữ `JoinPoint` hoặc raw request payloads.
11. Nếu record timing, assert duration hợp lý chứ không cứng một số nanosecond chính xác.
12. Đảm bảo output kiểm thử không in credentials/tokens hoặc toàn bộ người dùng thật.

**Không nhầm việc một `AopUtils.isAopProxy(bean)` trả true với việc aspect cụ thể đang khớp mọi method.** Bean có thể được proxy bởi advisor khác; phải kiểm tra pointcut và events.

## 14. Lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Audit của Alice gắn Bob | Shared `currentUser` singleton field | Snapshot actor thành local variable per advice call |
| Log args/method của request khác | Shared `ProceedingJoinPoint` field bị override | Giữ `pjp` local, chỉ extract metadata cần thiết |
| Duration quá ngắn/dài hoặc sai | Shared `startedNanos` bị overwrite | `final long start` local và elapsed trong `finally` |
| Thêm `volatile` vẫn sai | Visibility không tạo isolation | Xóa per-call fields |
| Dùng `AtomicReference` vẫn lẫn | Một slot chung giữ “last invocation” | Truyền scalar metadata explicit |
| Khóa `synchronized` gây nghẽn | Serialize business calls | Giữ locals, không khóa quanh `proceed()` |
| Aspect giữ request references quá lâu | Lưu JoinPoint/args trong field/map | Không retain raw request, dùng bounded/approved audit sink |
| ThreadLocal sai ở nested invocation | Một slot theo thread không phải stack | Local `@Around` hoặc push/pop có cleanup nếu cần |
| Log dính dữ liệu request trước trong pool | Quên `ThreadLocal.remove()`/MDC cleanup | `finally` + khôi phục state cũ |
| Future metric ghi trước job completion | Đo method return thay vì completion | CompletionStage callbacks hoặc reactive operators |
| Async callback không thấy user/MDC | Context chuyển thread | Framework context propagation/snapshot ID |
| Prototype/per-proxy aspect vẫn race | Không đồng nghĩa per invocation | Trạng thái chỉ để trong advice local |
| `@Before` ghi start, `@After` đọc field sai | Hai advice khác nhau chia sẻ singleton state | Dùng một `@Around` và local |
| Không có advice | Bean không thuộc Spring, AOP chưa bật, self-invocation | Kiểm tra context/proxy/invocation path |

## 15. Checklist review

- [ ] Không có field mang nghĩa `currentUser`, `currentJoinPoint`, `currentRequest`, `startTime` của invocation.
- [ ] Shared dependencies là thread-safe theo contract; configuration bất biến.
- [ ] `JoinPoint`/`ProceedingJoinPoint` được dùng tại invocation scope, không cache lâu dài.
- [ ] Actor ID được snapshot local và là dữ liệu được phép ghi audit.
- [ ] Timing dùng local `System.nanoTime()`, có `finally` cho sync success/failure.
- [ ] Method-return timing và Future/Publisher completion được phân biệt.
- [ ] Không dùng `volatile`/`AtomicReference` như giải pháp thay thế per-call isolation.
- [ ] Nếu có ThreadLocal/MDC, cleanup đúng và hỗ trợ nested calls.
- [ ] Không mặc định perthis/pertarget/prototype đồng nghĩa per request.
- [ ] Test overlap hai threads trên cùng Spring proxy với actor khác nhau.
- [ ] Test cross-bean nested invocation trên một thread.
- [ ] Không giữ raw request/credentials/arguments trong unbounded field/map.
- [ ] Spring bean registration, proxy boundary và pointcut đều được kiểm tra.

### Tài liệu Spring Framework chính thức

- **Aspect Instantiation Models** — default singleton, perthis và pertarget: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- **Declaring Advice / Around Advice** — `ProceedingJoinPoint`, `proceed()`: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- **AOP Concepts** — Spring proxy và advice execution: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- **Proxying Mechanisms** — JDK/CGLIB, self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Security concurrency support** — context propagation: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- **Spring scheduling and @Async**: https://docs.spring.io/spring-framework/reference/integration/scheduling.html

**Kết luận:** Một Spring `@Aspect` singleton có thể xử lý nhiều join points đồng thời. Lưu **`JoinPoint`, người dùng hiện tại hoặc start timestamp vào fields** dễ tạo race, lẫn identity, sai duration và giữ dữ liệu nhạy cảm quá lâu. Giữ state trong **local scope của mỗi advice invocation**, đưa metadata tối thiểu đến sink thread-safe và dùng cơ chế async/reactive context propagation đúng lifecycle.
