# Spring AOP: Aspect singleton được nhiều lời gọi sử dụng đồng thời

## 1. Bản chất vấn đề

Trong Spring Framework, một aspect khai báo bằng `@Aspect` và đăng ký như Spring bean (ví dụ `@Component`) **mặc định dùng singleton instantiation model**: về cơ bản có **một instance của aspect trong một ApplicationContext**. Cùng instance này có thể xử lý advice cho **nhiều lời gọi và nhiều luồng** đồng thời.

```java
@Aspect
@Component
public class AuditAspect {
    @Before("execution(* demo.concurrent.WorkerService.process(..))")
    public void before(JoinPoint jp) {
        System.out.println(jp.getSignature().getName());
    }
}
```

Đây là **fragment**: cần có imports, Spring configuration, bean đích và caller đi qua AOP proxy. Không có quy tắc nào nói rằng Spring sẽ tạo một `AuditAspect` mới cho mỗi invocation `process()`. Nếu ứng dụng web nhận nhiều requests hoặc hai worker threads cùng gọi service, lời gọi advice có thể **đè thời gian lên nhau** trong cùng một object aspect.

Phải phân biệt ba câu hỏi:

1. **Có bao nhiêu instance aspect?** Mặc định một aspect singleton cho mỗi bean/application context tương ứng.
2. **Có bao nhiêu lần advice được gọi?** Tương ứng những invocations match pointcut và thật sự đi qua Spring AOP proxy.
3. **Bao nhiêu luồng có thể thực thi cùng advice?** Có thể nhiều luồng cùng lúc; Spring không tự `synchronized` toàn bộ method advice chỉ vì aspect là singleton.

**Kết luận:** Singleton **không có nghĩa** single-threaded, không phải mutex, và không tự bảo đảm thread safety. Vấn đề quan trọng nhất là **state nào nằm trong field của aspect** và **state nào chỉ tồn tại cục bộ trong mỗi lần advice invocation**.

Bài tập trung hoàn toàn vào **Spring Aspect / Spring AOP proxy**, concurrency của aspect instance, điểm đặt state và những giới hạn proxy/lifecycle. Không đi sâu vào AOP nói chung hoặc AspectJ compile-time/load-time weaving.

## 2. Singleton của Spring là theo container, không phải toàn JVM

Spring IoC định nghĩa singleton scope theo **một bean definition trong một container**:

- Cùng Spring bean name trong cùng ApplicationContext thường trả lại cùng object được quản lý.
- Có **hai ApplicationContext độc lập** thì có thể có hai instance aspect tương ứng, nếu mỗi context tạo aspect bean.
- Không đồng nhất Spring singleton scope với GoF singleton dựa trên `static instance` toàn JVM/classloader.
- Singleton aspect **khác** singleton target service: đó có thể là hai bean definitions khác nhau, được khởi tạo và quản lý độc lập.

Cấu hình quen thuộc:

```java
@Configuration
@ComponentScan("demo.concurrent")
@EnableAspectJAutoProxy
public class AppConfig {}
```

Trong package được scan, Spring thấy `@Aspect @Component` rồi đăng ký aspect bean. Hạ tầng Spring AOP tạo advisor từ các advice và gắn chúng vào Spring proxy cho target beans phù hợp.

Một người có thể gọi:

```java
var context = new AnnotationConfigApplicationContext(AppConfig.class);
AuditAspect first = context.getBean(AuditAspect.class);
AuditAspect second = context.getBean(AuditAspect.class);
System.out.println(first == second); // true trong cùng context singleton.
```

Đây là **fragment**, nên đóng context khi dùng xong. Nó chứng minh hai lần tra cứu bean trả cùng reference; **không chứng minh advice chỉ thực thi một lần**. Một object có thể có một triệu lần gọi method, kể cả nhiều lần đang chạy song song.

### Khi nào aspect được tạo?

- Spring tạo bean/đăng ký advisor trong quá trình context khởi tạo theo bean lifecycle và cấu hình.
- Khi invocation đi qua proxy và pointcut khớp, advice method được gọi trên aspect instance đã được Spring quản lý.
- Advice không được tạo mới theo từng request chỉ vì một HTTP request mới xuất hiện.
- `@PostConstruct` (nếu dùng) trên aspect nói về **khởi tạo bean**, không phải hook “trước mỗi invocation”.

**Không giữ request data trong field của singleton aspect** chỉ vì field được gán bên trong một before advice.

## 3. Sơ đồ hai lời gọi song song trên cùng một aspect

```text
                     Spring ApplicationContext
                              |
                       singleton AuditAspect
                         shared fields
                         /          \
                        /            \
               Thread A             Thread B
                  |                    |
       Spring proxy.process("A")  Spring proxy.process("B")
                  |                    |
          advice invocation A   advice invocation B
          local variables A     local variables B
                  |                    |
                  +---- cùng một object aspect ----+
                  |                    |
              Target A             Target B
                  |                    |
           return "done-A"       return "done-B"
```

Những thứ **có thể chia sẻ**:

- Các instance fields của aspect: `currentId`, `startTime`, counter, cache, map, collection...
- Các collaborator objects được inject vào aspect: repository, metrics registry, logger wrapper, service...
- Static fields/global state do ứng dụng tự tạo.
- Trạng thái của **singleton target bean** nếu target cũng là singleton.

Những thứ **riêng cho mỗi lần invocation**:

- Method parameters của advice, ví dụ `JoinPoint jp`, `ProceedingJoinPoint pjp`.
- Local variables tạo bên trong advice, ví dụ `String id`, `long startedAt`.
- Kết quả của `proceed()` và exception của một invocation cụ thể (trừ khi bạn cố ý gán chúng vào shared state).

Không cần tạo một aspect object cho từng invocation để bảo vệ local variables: **mỗi lời gọi Java có stack frame riêng**. Nhưng nếu một local variable tham chiếu tới **một object mutable chia sẻ**, object đó vẫn có thể chịu race condition.

## 4. Phản ví dụ: lưu dữ liệu từng request vào field

```java
@Aspect
@Component
public class UnsafeAuditAspect {
    private String currentRequestId; // SHARED giữa các lời gọi.

    @Before("execution(* demo.concurrent.WorkerService.process(..))"
          + " && args(requestId)")
    public void before(String requestId) {
        currentRequestId = requestId; // Ghi đè state singleton.
    }

    @AfterReturning("execution(* demo.concurrent.WorkerService.process(..))")
    public void after() {
        System.out.println("completed request=" + currentRequestId);
    }
}
```

Đây là **phản ví dụ cố ý không an toàn** và không thuộc chương trình runnable ở mục 8. Dù field `currentRequestId` chỉ có một String, logic ghi rồi đọc xuyên qua hai advice calls khác nhau đã ràng buộc dữ liệu của **invocation A** vào shared field của **aspect bean**.

Một interleaving hợp lệ:

```text
Thread A: before("A") -> currentRequestId = "A"
Thread B: before("B") -> currentRequestId = "B"
Thread A: target A returns
Thread A: after() -> đọc currentRequestId là "B" (SAI)
Thread B: after() -> cũng có thể đọc "B"
```

Không có mối liên hệ invocation-A riêng biệt được Spring tạo ra cho field. `@Order` hay tên method khác nhau không ngăn hai threads xen kẽ nhau. **Việc advice “vào trước, ra sau” áp dụng cho một invocation chain**, không biến toàn bộ singleton aspect thành vùng critical section.

### 4.1. Thêm `volatile` đã đủ chưa?

```java
private volatile String currentRequestId;
```

**Chưa đủ.** `volatile` có thể cung cấp visibility của giá trị mới nhất, nhưng không gắn giá trị A với invocation A. Trong ví dụ, thread A càng dễ nhìn thấy giá trị B được cập nhật mới. Mục tiêu không phải “đọc giá trị mới nhất”, mà là **đọc đúng dữ liệu thuộc request hiện tại**.

### 4.2. `synchronized` advice có phải giải pháp?

Nếu chỉ đặt `synchronized` trên `before()` và `after()`, hai method calls được khóa riêng rẽ, **không có lock giữ xuyên suốt target execution**. Lời gọi A có thể nhường chỗ cho before B rồi mới vào after A, nên vẫn sai.

Kể cả khóa toàn bộ `@Around`:

```java
@Around("execution(* demo.concurrent.WorkerService.process(..))")
public synchronized Object serializeAll(ProceedingJoinPoint pjp)
        throws Throwable {
    return pjp.proceed();
}
```

đoạn trên chỉ là **fragment**, không phải khuyến nghị. Nó làm một số invocation theo cùng aspect instance chạy tuần tự, có thể tạo nút thắt cổ chai và tác động tới latency/throughput; việc dùng `synchronized` không tự bao quát mọi đường gọi bypass proxy, callback async hoặc các bean contexts khác. Đối với dữ liệu per-invocation, **local variables** tốt hơn là khóa toàn bộ business operation.

### 4.3. `AtomicReference<String>` có sửa “current request” không?

Không. `AtomicReference` làm các thao tác cập nhật/đọc reference trở nên atomic và có memory visibility; nó vẫn đại diện cho **một ô giá trị dùng chung**. Khi A ghi rồi B ghi, A không có cách biết giá trị sau cùng thuộc A. Sử dụng atomic references cho **shared coordination state**, không thay thế context theo invocation.

## 5. An toàn nhất: dữ liệu theo invocation nằm trong local variables

Với yêu cầu log/timing trước và sau method, Spring khuyến nghị `@Around` vì nó có thể giữ cả hai giá trị trên **cùng stack frame của một advice invocation**:

```java
@Aspect
@Component
public class SafeAuditAspect {
    @Around("execution(* demo.concurrent.WorkerService.process(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String requestId = (String) pjp.getArgs()[0]; // Local.
        long started = System.nanoTime();             // Local.

        try {
            Object result = pjp.proceed();
            System.out.println("finished " + requestId
                    + " in " + (System.nanoTime() - started) + " ns");
            return result;
        } catch (Throwable ex) {
            System.out.println("failed " + requestId);
            throw ex;
        }
    }
}
```

Đoạn trên là **fragment minh họa**, giả định method `process(String)` đúng signature và có một argument kiểu String. Nếu pointcut rộng cho nhiều signatures, phải kiểm tra `getArgs().length` và types. Trong production, requestId có thể nhạy cảm: dùng log policy/redaction phù hợp.

**Vì sao đúng hơn?**

- Mỗi lời gọi `around(...)` có `requestId` và `started` riêng.
- Thread B không thể gán trực tiếp vào local variable của stack frame thread A.
- `pjp.proceed()` có thể chạy các interceptors khác hoặc target, rồi return về **cùng** frame chứa `started`.
- Exception được rethrow, result được giữ nguyên. Không vô tình nuốt exception hoặc thay return value.
- Aspect có thể vẫn chỉ có **một instance** trong Spring context; không cần tạo aspect mới.

**Một giới hạn:** `@Around` đo thời gian cho phần invocation đồng bộ bên trong `proceed()`. Nếu method trả `CompletableFuture<T>` hoặc reactive publisher chưa hoàn tất, elapsed time này có thể chỉ là thời gian tạo wrapper, không phải thời gian hoàn thành tác vụ async. Thời gian completion cần được đo bằng API completion/reactive tương ứng.

## 6. Khi thực sự cần shared metrics thì dùng cấu trúc thread-safe

Không phải **mọi field** đều xấu. Một Spring aspect có thể giữ immutable configuration hoặc **state chia sẻ có mục đích và thread-safe**.

### 6.1. Immutable dependencies và config

```java
@Aspect
@Component
public class PolicyAspect {
    private final String environment = "demo";
    private final AuditPort auditPort;

    public PolicyAspect(AuditPort auditPort) {
        this.auditPort = auditPort;
    }
}
```

Đây là fragment, `AuditPort` là interface giả định. `final` giúp cố định reference sau khởi tạo, nhưng nếu `auditPort` trỏ tới một mutable object không thread-safe thì việc inject vào singleton aspect **không tự biến collaborator đó thành thread-safe**.

Spring chịu trách nhiệm lifecycle và safe publication của singleton bean state được hoàn tất trong giai đoạn initialization thông thường. Nếu config field được mutate **sau** khi bean đã công bố, phải áp dụng concurrency control thích hợp như `volatile` hoặc lock; Spring không tự đồng bộ runtime mutations của bạn.

### 6.2. Counters: `AtomicInteger` / `LongAdder`

```java
private final AtomicInteger active = new AtomicInteger();
private final AtomicInteger peak = new AtomicInteger();
private final LongAdder completed = new LongAdder();

int now = active.incrementAndGet();
peak.accumulateAndGet(now, Math::max);

try {
    return pjp.proceed();
} finally {
    active.decrementAndGet();
    completed.increment();
}
```

Đây là fragment dành cho `@Around`, cần các imports từ `java.util.concurrent.atomic`. Các counters này là **shared aggregate state**, không phải request-specific data:

- `active`: số invocations hiện trong đoạn `try/finally` theo mức quan sát của aspect.
- `peak`: giá trị concurrent cao nhất quan sát được theo atomic accumulation.
- `completed`: số lần rời advice, bao gồm cả exceptional exits nếu `finally` chạy.
- `LongAdder` thường phù hợp counters chịu contention cao, nhưng `sum()` khi đang cập nhật đồng thời không phải snapshot tuyến tính hoàn toàn; các kết quả quan sát metrics có thể là gần thời điểm đọc.
- Counter metrics không chứng minh target method đã thành công; cần naming/logic riêng nếu bạn chỉ muốn đếm success.

**Không** dùng `int count++` không đồng bộ trên singleton aspect để đếm chính xác mọi lời gọi: phép tăng gồm đọc-sửa-ghi, nên concurrent updates có thể bị mất.

### 6.3. Map/cache chia sẻ

Nếu cần lookup/cache metrics theo method name hoặc tag ổn định, có thể dùng `ConcurrentHashMap` hoặc library cache có concurrency policy phù hợp. Nhưng thread-safe map không tự bảo vệ **mutable value objects** trong map. Cần quy tắc expire/evict, cardinality control và tránh key chứa PII.

Ví dụ sơ lược:

```java
private final ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

void countByMethod(String name) {
    counts.computeIfAbsent(name, key -> new LongAdder()).increment();
}
```

Fragment này phù hợp với keys có cardinality được quản lý; không nên dùng raw request IDs làm keys mãi mãi, vì dễ gây memory growth. Trong ứng dụng thực, hệ thống metrics như Micrometer/Observation có thể giảm việc tự quản lý counter lifecycle.

## 7. Khi state phải sống ngoài một advice invocation

### 7.1. `ThreadLocal` chỉ tách theo thread

Một `ThreadLocal<String>` có thể phục vụ code đồng bộ sâu bên trong **cùng thread**, nhưng không phải request scope: thread pool tái sử dụng thread, nested proxy calls có thể ghi đè context, và executor không tự truyền giá trị sang thread khác. Nếu phải dùng, lưu giá trị cũ rồi restore/remove trong `finally`:

```java
String previous = operationContext.get();
operationContext.set(operationId);
try {
    return pjp.proceed();
} finally {
    if (previous == null) operationContext.remove();
    else operationContext.set(previous);
}
```

Đây là fragment cần `operationContext`, `operationId` và `pjp`. Khi chỉ cần đo thời gian cho một `@Around`, local `long started` vẫn đơn giản hơn; bài ThreadLocal phía sau sẽ kiểm tra nesting, MDC và thread reuse bằng test.

### 7.2. Request-scoped dependency không biến aspect thành per-request

Aspect singleton có thể sử dụng một request-scoped collaborator qua scoped proxy/provider trong web-aware context. Scope quyết định **target dependency được resolve thế nào**; aspect instance không tự đổi scope. Callback chạy khi request context không còn hoạt động cần xử lý riêng, đặc biệt ở background tasks. Không đổi `@Aspect` sang `@RequestScope` rồi coi mọi rủi ro concurrency đã hết.

### 7.3. Completion của async/reactive khác lúc method return

`@Around` thông thường kết thúc sau `pjp.proceed()`. Nếu target trả `CompletableFuture` chưa hoàn thành hoặc `Mono` chưa subscribe, duration chỉ đo boundary đồng bộ. Muốn ghi thời gian hoàn tất, gắn đo tại completion callback hoặc reactive subscription/terminal operator, có state riêng và lifecycle rõ ràng. Bài `@Async` và Reactor phía sau phân tích cách propagate context giữa các luồng và subscriptions.

## 8. Ví dụ chạy được: một singleton aspect xử lý hai invocation đồng thời

Dự án sau dùng **Java 17, Maven và Spring Framework 6.2.x** (không cần Spring Boot). Nó cố ý tránh log bên trong hai worker threads để stdout **có thứ tự ổn định**. Hai lời gọi vẫn được chứng minh **thực sự overlap** nhờ `CountDownLatch` trong target.

Mục tiêu quan sát:

1. Hai lần `getBean(MonitorAspect.class)` trong cùng context cho một instance.
2. Consumer nhận Spring AOP proxy qua `WorkerPort`.
3. Hai threads có thể đi vào **cùng advice method** song song; chỉ số `peak=2` xác nhận overlap.
4. Dữ liệu theo invocation `id` nằm trong local variable, không trong field.
5. Counter `AtomicInteger` an toàn khi increment/decrement; sau hai lời gọi `activeAfter=0`.
6. Kết quả từ hai requests không bị trộn: sau khi sort, `[done-A, done-B]`.

### 8.1. Cấu trúc thư mục

```text
spring-aop-concurrent-aspect/
├── pom.xml
└── src/main/java/demo/concurrent/
    ├── AppConfig.java
    ├── WorkerPort.java
    ├── WorkerService.java
    ├── MonitorAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-concurrent-aspect</artifactId>
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

### 8.3. `AppConfig.java`

```java
package demo.concurrent;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

Spring component scan đăng ký service và aspect. Với `WorkerService implements WorkerPort` và `proxyTargetClass=false`, Spring Framework thuần ưu tiên **JDK dynamic proxy** cho service.

### 8.4. `WorkerPort.java`

```java
package demo.concurrent;

public interface WorkerPort {
    String process(String id);
}
```

Consumer chỉ cần interface. JDK proxy triển khai interface này; không cast nó thành concrete target service.

### 8.5. `WorkerService.java`

```java
package demo.concurrent;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class WorkerService implements WorkerPort {
    private final CountDownLatch bothEntered = new CountDownLatch(2);

    @Override
    public String process(String id) {
        bothEntered.countDown();

        try {
            if (!bothEntered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Expected two concurrent calls");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Worker interrupted", ex);
        }

        return "done-" + id;
    }
}
```

`CountDownLatch(2)` giữ lời gọi thứ nhất ở target cho tới khi lời gọi thứ hai cũng vào. Do đó không dựa vào cách scheduler in log xen kẽ để **chứng minh hai invocations cùng lúc**.

Target chỉ phục vụ bài demo đúng **hai invocations trong một context**; latch không tự reset và sẽ không đại diện cho mỗi request pair trong một ứng dụng thực. Việc dùng synchronized trên target sẽ khiến ví dụ deadlock/timeout; đó cũng chính là lý do không khóa toàn bộ lời gọi chỉ để làm metrics.

### 8.6. `MonitorAspect.java`

```java
package demo.concurrent;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class MonitorAspect {
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();
    private final LongAdder elapsedNanos = new LongAdder();

    @Around("execution(* demo.concurrent.WorkerService.process(..))")
    public Object monitor(ProceedingJoinPoint pjp) throws Throwable {
        String id = (String) pjp.getArgs()[0]; // Riêng mỗi invocation.
        long started = System.nanoTime();       // Riêng mỗi invocation.

        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            Object result = pjp.proceed();

            if (!("done-" + id).equals(result)) {
                throw new IllegalStateException("Mismatched result for " + id);
            }
            return result;
        } finally {
            elapsedNanos.add(System.nanoTime() - started);
            active.decrementAndGet();
        }
    }

    public int active() {
        return active.get();
    }

    public int peak() {
        return peak.get();
    }

    public long elapsedNanos() {
        return elapsedNanos.sum();
    }
}
```

Điểm quan trọng:

- Aspect có ba **shared fields** nhưng chúng thuộc nhóm aggregate/metrics có cơ chế thread-safe; không giữ `id` hoặc `started` trong field.
- Mỗi lần advice gọi `proceed()` đúng **một** lần.
- `id` và `started` là local, nên hai threads không ghi đè dữ liệu của nhau.
- `finally` đưa `active` về đúng 0 khi hai invocations hoàn thành, kể cả một invocation ném exception.
- `peak.accumulateAndGet(now, Math::max)` giữ max concurrent count một cách atomic.
- `elapsedNanos.sum()` có thể dùng cho aggregate timing, nhưng demo không in thời gian vì số nanoseconds phụ thuộc máy và scheduling.
- Validation `"done-" + id` chỉ để chứng minh **per-invocation identity**; trong logging aspect sản xuất, không hardcode target result contract như vậy.

### 8.7. `Main.java`

```java
package demo.concurrent;

import java.util.List;
import java.util.concurrent.Executors;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            WorkerPort port = context.getBean(WorkerPort.class);
            MonitorAspect aspect = context.getBean(MonitorAspect.class);

            System.out.println("singletonAspect="
                    + (aspect == context.getBean(MonitorAspect.class)));
            System.out.println("jdkProxy="
                    + AopUtils.isJdkDynamicProxy(port));

            var pool = Executors.newFixedThreadPool(2);
            try {
                var a = pool.submit(() -> port.process("A"));
                var b = pool.submit(() -> port.process("B"));

                List<String> results = List.of(a.get(), b.get())
                        .stream().sorted().toList();

                System.out.println("results=" + results);
                System.out.println("peak=" + aspect.peak());
                System.out.println("activeAfter=" + aspect.active());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`, máy cần JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.concurrent.Main
```

**Stdout dự kiến nếu hai worker threads đều chạy trong timeout 10 giây** (không tính log Maven/Spring riêng):

```text
singletonAspect=true
jdkProxy=true
results=[done-A, done-B]
peak=2
activeAfter=0
```

Đây là ví dụ **deterministic về thứ tự print** vì chỉ thread main in; các worker thực thi song song nhưng không in stdout. Nếu môi trường cực kỳ chậm, deadline 10 giây có thể khiến `CountDownLatch.await(...)` timeout và chương trình báo lỗi thay vì ra stdout trên. Đây là ràng buộc môi trường của demo, không phải kết quả bình thường của Spring AOP.

### 8.8. Giải thích vì sao `peak=2`

1. Main lấy bean `WorkerPort` qua context, nên lời gọi đi qua AOP proxy. Aspect được đăng ký Spring singleton.
2. Thread A đi vào `MonitorAspect.monitor(...)`, tăng `active` lên 1, sau đó tiến đến `WorkerService.process("A")` và đợi latch.
3. Thread B đi vào **cùng MonitorAspect instance**, tăng `active` lên 2, cập nhật `peak` thành 2 rồi tiến tới target.
4. Hai target invocations gặp latch và đều có thể trở về; không có sự khóa tuần tự trong aspect.
5. Mỗi around advice instance giữ `id`/`started` trong local variables, bảo toàn result tương ứng A và B.
6. Cả hai advice invocations rời `finally` và giảm counter. Khi Main gọi `Future.get()` thành công cho cả hai, `activeAfter=0`.
7. Thứ tự tasks hoàn thành là không chắc chắn, nhưng kết quả được sorted nên in `[done-A, done-B]` một cách ổn định.

**Kiểm chứng khác biệt:** nếu thêm `synchronized` trên method `monitor(...)`, thread A có thể giữ lock và đợi B tại latch, trong khi B không thể vào advice để tới target; kết quả là timeout. Đây là lý do dùng local state và thread-safe metrics thay vì serialize toàn bộ business execution.

## 9. Mô hình aspect instantiation nâng cao không đồng nghĩa per-invocation

Tài liệu Spring cho `@AspectJ` style còn đề cập một số instantiation models khác singleton:

| Model trong Spring @AspectJ | Ý nghĩa đại thể | Có đảm bảo một instance / mỗi invocation? |
| --- | --- | --- |
| Mặc định singleton | Một aspect instance được dùng lại trong context | **Không** |
| `perthis(...)` | Gắn aspect instance với một proxy object phù hợp theo biểu thức | **Không** — nhiều invocations trên cùng proxy có thể dùng chung |
| `pertarget(...)` | Gắn aspect instance với một target object phù hợp | **Không** — target có thể phục vụ nhiều invocations đồng thời |
| `pertypewithin(...)` | Gắn aspect instance với một type phù hợp | **Không** — không phải per-call |
| `percflow(...)` / `percflowbelow(...)` | Không được Spring AOP proxy hỗ trợ theo docs | Không dùng như cách sửa concurrency |

Các mô hình trên là **chủ đề nâng cao**; không phải giải pháp đầu tiên cho state per-invocation. Đừng phát biểu sai rằng Spring AOP chỉ hỗ trợ singleton mà hoàn toàn không có mô hình per-object — tài liệu chính thức xác nhận `perthis`, `pertarget` và `pertypewithin` có hỗ trợ trong @AspectJ configuration.

Ví dụ dạng fragment:

```java
@Aspect("pertarget(execution(* demo.concurrent.WorkerService.process(..)))")
public class TargetScopedAspect {
    // State vẫn chia sẻ giữa các lời gọi trên cùng target.
}
```

Đây chỉ minh họa cú pháp, **không** đặt vào chương trình runnable ở mục 8. Với `pertarget`, việc tạo aspect instance dựa trên target identity khi pointcut phù hợp, không tự tách dữ liệu per-thread/per-request. Trước khi dùng những mô hình nâng cao, kiểm tra Spring version, cấu hình đăng ký aspect và integration tests.

**Ghi chú quan trọng:** Scope của Spring bean `@Scope("prototype")` và AspectJ-style per-clause instantiation **không phải cùng một mô hình**. Không đổi annotation bean scope rồi suy ra một advice method instance được tạo cho từng invocation.

## 10. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Log request A hiện ID của request B | Field singleton `currentId` bị ghi đè | Dùng local variable trong `@Around`, hoặc context được thiết kế rõ |
| Start time/duration giữa hai lời gọi bị trộn | Lưu `startedAt` trong aspect instance field | Đặt `long started` trong advice local frame |
| Counter thấp hơn số lần gọi thực | `count++` không atomic | Dùng `AtomicInteger`/`LongAdder`/metrics registry |
| Thêm `volatile` vẫn sai request | Visibility không tạo per-invocation isolation | Không lưu request context trong một shared field |
| `synchronized @Before`/`@After` vẫn lệch dữ liệu | Lock chỉ quanh từng method advice, không nối một invocation | Đổi thiết kế sang local state/around |
| `synchronized @Around` làm service nghẽn | Serialize toàn bộ chain/target | Không khóa nếu chỉ cần đo/log; dùng thread-safe aggregator |
| `ThreadLocal` còn dữ liệu từ request trước | Worker thread pool tái sử dụng, quên `remove()` | Cleanup/restore trong finally; ưu tiên explicit context |
| Nested advice xóa ThreadLocal của outer | Inner call `remove()` sau khi ghi đè old value | Save old, restore trong finally hoặc context API phù hợp |
| `@Async` không thấy ThreadLocal | Task chuyển thread, không tự propagate | Task decoration/context propagation tùy Spring module |
| `@Around` elapsed thấp hơn async processing | Method return future/publisher sớm | Đo completion theo async/reactive API |
| Singleton aspect inject singleton mutable service và bị race | Collaborator không thread-safe | Sửa state ownership/concurrency ở collaborator |
| Dùng `@Order` để bảo đảm không có hai threads xen kẽ | `@Order` chỉ precedence trong một interceptor chain | Chọn concurrency control thích hợp |
| `perthis` vẫn có race | Nhiều threads gọi cùng proxy | Dùng local state hoặc atomic/lock có mục đích |
| `pertarget` vẫn có race | Nhiều threads gọi cùng target instance | Không xem per-target là per-thread/per-request |
| Bean tự `new` không có advice | Không có Spring proxy | Dùng Spring-managed dependency |
| `this.process()` không qua advice | Self-invocation bypass Spring proxy | Tách operation sang Spring bean khác nếu cần advice |
| Aspect không có effect | `@Aspect` chưa được đăng ký bean hoặc chưa bật auto-proxy | `@Component`/`@Bean` và `@EnableAspectJAutoProxy`/Boot AOP |
| JDK proxy không expose implementation-only method | Interface surface giới hạn | Dùng public interface method hoặc cấu hình CGLIB có cân nhắc |
| CGLIB không intercept `final`/`private` method | Không override được | Đổi method/bean boundary phù hợp |
| Nhiều ApplicationContexts có nhiều singleton aspects | Singleton là per-container/bean | Kiểm tra context ownership và cấu hình thực tế |

## 11. Checklist thiết kế singleton Spring Aspect an toàn

1. **Xác định scope thật:** aspect là Spring bean trong context nào, có per-clause instantiation model đặc biệt không.
2. **Kiểm tra target và proxy:** Spring có quản lý target không, pointcut match, caller có đi qua proxy không.
3. **Liệt kê tất cả aspect fields:** config immutable, collaborator references, shared aggregate state, hay dữ liệu per-invocation?
4. **Di chuyển per-invocation state vào local variables** của advice; dùng `@Around` khi cần nối đoạn trước/sau `proceed()`.
5. **Shared aggregates phải thread-safe:** atomic/LongAdder hoặc metrics library; nghĩ tới snapshot consistency và cardinality.
6. **Không lạm dụng `volatile`/`synchronized`:** chúng giải quyết visibility/mutual exclusion, không tạo request identity.
7. **Đừng lưu `JoinPoint` hay `ProceedingJoinPoint` trong singleton fields** để dùng lại về sau; đây là state của invocation hiện tại.
8. **Xem collaborator thread safety:** `final` dependency reference không làm các mutable internals bên trong collaborator an toàn.
9. **Xem ThreadLocal lifecycle:** cleanup, nested calls, async hops, executor reuse và context propagation.
10. **Đảm bảo outcome:** advice gọi `proceed()` theo nhu cầu, giữ return value và truyền exception đúng.
11. **Test concurrency thật:** dùng latch/barrier để ép overlap và kiểm tra race/độ đúng, không đoán từ một lần log may mắn.
12. **Khi có transactions/cache/security/async:** kiểm tra advisor ordering và ranh giới thực thi, không coi một singleton aspect là global lock.

### Bộ test tình huống hữu ích

| Test | Kỳ vọng |
| --- | --- |
| Tra `getBean(Aspect.class)` hai lần cùng context | Cùng reference nếu default singleton |
| Hai threads gọi chung Spring proxy đồng thời | Advice chạy concurrent nếu không tự serialize |
| Request A/B có argument khác nhau | Local request data giữ đúng A/B |
| Atomics đếm active/peak | Không mất increment, số peak phản ánh overlap |
| Shared field `currentId` | Có thể sai khi interleave; không dùng trong production |
| Có method gọi `this.inner()` | Không có interception mới cho self-invocation |
| Object tạo qua `new` | Không được Spring AOP advice |
| Lỗi từ target | `finally` cleanup metrics đúng, exception vẫn truyền ra ngoài |
| Lời gọi trả future | Đừng hiểu đồng bộ elapsed là toàn bộ thời gian async |
| Multiple contexts | Không suy rằng một aspect singleton duy nhất toàn JVM |

## 12. Câu hỏi ôn tập

**1. Spring `@Aspect @Component` singleton có nghĩa advice chỉ chạy một lần không?** Không. Một aspect instance phục vụ nhiều matched invocations; các threads có thể vào advice cùng lúc.

**2. Vì sao lưu `currentRequestId` vào field là nguy hiểm?** Hai calls đồng thời ghi đè shared state, khiến after advice đọc dữ liệu của invocation khác.

**3. `volatile` sửa được race “request A đọc ID của B” không?** Không. Nó giúp visibility, không tạo dữ liệu riêng theo invocation.

**4. Tại sao `@Around` local `started` an toàn hơn field `started`?** Local thuộc stack frame từng invocation; khi `proceed()` trả, cùng frame nhận kết quả và duration tương ứng.

**5. Trường hợp nào nên có mutable aspect fields?** Khi đó là shared state thật sự như metrics aggregates và được bảo vệ bằng concurrency primitives/structures phù hợp.

**6. `@Order(1)` có bảo đảm Thread B đợi Thread A kết thúc không?** Không. Nó điều chỉnh precedence của advisor trong một invocation chain, không là mutex giữa requests.

**7. Vì sao `ThreadLocal` cần `remove()` hoặc restore?** Thread pool tái sử dụng threads và nested calls có thể ghi đè context; cleanup tránh data leak/cross-request contamination.

**8. `perthis` hoặc `pertarget` có nghĩa một aspect instance mỗi lời gọi không?** Không. Chúng liên hệ aspect instance với proxy/target object, mà một object có thể có nhiều calls concurrent.

**9. Một `@Around` đo timer quanh `proceed()` có đếm xong CompletableFuture chưa?** Không nhất thiết; future có thể hoàn thành sau khi method invocation đồng bộ return.

**10. Spring singleton scope có phải đúng một instance aspect trong toàn JVM không?** Không; thông thường per bean definition/per ApplicationContext, khác GoF static singleton.

## Tài liệu Spring Framework chính thức

- [Spring Framework 6.2 — Aspect Instantiation Models: singleton, perthis, pertarget, pertypewithin](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/instantiation-models.html)
- [Spring Framework — Bean Scopes: singleton theo container](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Declaring Advice: Around Advice và local state khi đo thời gian](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — Bean Initialization / thread-safe publication và mutable runtime fields](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Proxying Mechanisms: JDK/CGLIB và self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ support và aspect beans](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
