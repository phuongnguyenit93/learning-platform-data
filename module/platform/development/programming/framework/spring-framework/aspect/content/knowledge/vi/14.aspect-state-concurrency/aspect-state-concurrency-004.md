# Phụ thuộc được tiêm vào aspect và yêu cầu an toàn luồng trong Spring AOP

## 1. Vấn đề cần giải quyết

Trong ứng dụng Spring, một `@Aspect` thường là bean singleton của `ApplicationContext`. Khi nhiều request gọi những Spring bean được proxy, các advice có thể chạy đồng thời trên **cùng một instance aspect**. Việc Spring tiêm một dependency thành công chỉ xác nhận rằng bean được tìm thấy và gắn vào aspect; nó **không chứng minh** dependency hoặc cách dùng dependency là thread-safe.

Bài này tập trung vào **Spring-managed aspect, Spring AOP proxy, DI và phạm vi bean Spring**, không đi sâu lại các khái niệm AOP tổng quát.

Một `@Before`, `@AfterReturning` hay `@Around` có thể gọi repository, recorder, clock, policy service, tracer và client HTTP. Mọi tương tác với trạng thái dùng chung của những dependency này cần được kiểm tra theo cùng các tiêu chuẩn của Java concurrency.

## 2. Ba loại trạng thái cần phân biệt

| Loại | Ví dụ | Quy tắc |
| --- | --- | --- |
| Dữ liệu của **một lần gọi** | `JoinPoint`, đối số, user ID, thời điểm bắt đầu, stopwatch, exception | Giữ trong biến cục bộ của advice hoặc một context object cục bộ |
| Trạng thái **dùng chung có chủ đích** | Tổng số lượt gọi, bộ đếm metric, bộ nhớ đệm đồng thời | Dùng primitive/concurrent abstraction phù hợp: `AtomicInteger`, `LongAdder`, `ConcurrentHashMap`, hoặc synchronization khi cần |
| Dependency được tiêm | Logger, repository, singleton service, custom recorder | Xem contract và implementation; injection, `final` và singleton **không tự tạo** bảo đảm thread-safe |

Ví dụ **sai** trong một singleton aspect:

~~~java
@Aspect
@Component
class UnsafeTraceAspect {
    private Object[] lastArgs;
    private long startedAt;

    @Around("execution(* demo.CatalogService.quote(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        lastArgs = pjp.getArgs();
        startedAt = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            // Một thread khác có thể đã thay lastArgs và startedAt.
            System.out.println(lastArgs[0] + ":" + (System.nanoTime() - startedAt));
        }
    }
}
~~~

Điều nguy hiểm nằm ở fields dùng chung, không nằm ở `ProceedingJoinPoint` như một khái niệm. Một lời gọi B có thể ghi fields giữa hai bước của lời gọi A và làm A ghi sai request, log nhầm định danh, hoặc thậm chí rò rỉ thông tin.

Cách sửa đúng:

~~~java
@Around("execution(* demo.CatalogService.quote(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    Object[] argsForThisCall = pjp.getArgs().clone();
    long startedForThisCall = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - startedForThisCall;
        record(argsForThisCall, elapsed);
    }
}
~~~

`record(...)` trong ví dụ chỉ là lời gọi minh họa; bản thân implementation của recorder cũng phải an toàn khi truy cập đồng thời. Sao chép mảng chỉ bảo vệ **cấu trúc mảng**, không deep-copy các đối tượng mutable bên trong.

## 3. Spring tạo và tiêm aspect như thế nào?

Với cấu hình `@EnableAspectJAutoProxy` hoặc hạ tầng AOP tương đương của Spring Boot, Spring lấy bean đã khai báo `@Aspect` và biến các advice phù hợp thành advisors cho proxy.

- `@Component` + `@Aspect` có thể được component scan tìm thấy; có thể thay bằng method `@Bean` trả về instance aspect.
- Constructor injection là lựa chọn thuận tiện nhất: dependency bắt buộc được xác nhận lúc khởi tạo và reference của nó có thể là `final`.
- Spring aspect mặc định sử dụng mô hình singleton; target bean được proxy có thể có scope khác. Scope target và scope dependency cần xem riêng.
- Spring AOP áp dụng tại **method execution qua proxy**. Một self-invocation như `this.quote(...)` bên trong target đi thẳng đến target và bỏ qua advice trên lời gọi đó.

Ví dụ constructor injection:

~~~java
@Aspect
@Component
public class TraceAspect {
    private final MetricRecorder recorder;

    public TraceAspect(MetricRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(* demo.CatalogService.quote(..))")
    public void before(JoinPoint joinPoint) {
        Object[] invocationArgs = joinPoint.getArgs().clone();
        recorder.increment();
        // invocationArgs chỉ tồn tại trong lần advice hiện tại.
    }
}
~~~

`final` giữ reference `recorder` không đổi sau construction; nếu implementation `recorder.increment()` dùng `count++` trên một `int` thường, vẫn có race/lost update.

## 4. Ví dụ chạy được: Spring 6.2, Java 17, Maven

Project tối thiểu, có đầy đủ các file:

~~~text
spring-aspect-dependency-concurrency/
  pom.xml
  src/main/java/demo/App.java
  src/main/java/demo/CatalogService.java
  src/main/java/demo/MetricRecorder.java
  src/main/java/demo/TraceAspect.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aspect-dependency-concurrency</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.25</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**CatalogService.java**

~~~java
package demo;

import org.springframework.stereotype.Component;

@Component
public class CatalogService {
    public String quote(String sku) {
        return "quote:" + sku;
    }
}
~~~

**MetricRecorder.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class MetricRecorder {
    private final AtomicInteger calls = new AtomicInteger();

    public void increment() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
~~~

**TraceAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    private final MetricRecorder recorder;

    public TraceAspect(MetricRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(public * demo.CatalogService.quote(..))")
    public void beforeQuote(JoinPoint jp) {
        Object[] localArgs = jp.getArgs().clone();
        if (localArgs.length != 1) {
            throw new IllegalStateException("Unexpected method signature");
        }
        recorder.increment();
    }
}
~~~

**App.java**

~~~java
package demo;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    public static void main(String[] args) throws Exception {
        try (var ctx = new AnnotationConfigApplicationContext(App.class)) {
            CatalogService catalog = ctx.getBean(CatalogService.class);
            MetricRecorder recorder = ctx.getBean(MetricRecorder.class);

            ExecutorService pool = Executors.newFixedThreadPool(4);
            CountDownLatch start = new CountDownLatch(1);
            try {
                List<Future<String>> futures = new ArrayList<>();
                for (int i = 0; i < 20; i++) {
                    final int index = i;
                    Callable<String> task = () -> {
                        start.await();
                        return catalog.quote("sku-" + index);
                    };
                    futures.add(pool.submit(task));
                }
                start.countDown();
                Set<String> distinct = new HashSet<>();
                for (Future<String> future : futures) {
                    distinct.add(future.get());
                }
                System.out.println("distinctResults=" + distinct.size());
                System.out.println("recordedCalls=" + recorder.count());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.App
~~~

Kết quả ứng dụng mong đợi (bỏ qua thông báo riêng của Maven nếu có):

~~~text
distinctResults=20
recordedCalls=20
~~~

Kết quả trên xác nhận bộ đếm thread-safe và dữ liệu tác vụ độc lập. Nó **không chứng minh rằng mọi dependency tùy ý** cũng thread-safe. Đoạn mã này đã được rà soát tĩnh theo API Spring/Java; không có kết quả thực thi Maven được khẳng định.

## 5. Dependency nào cần kiểm tra kỹ?

### Singleton service có state mutable

Một `@Service` singleton chứa `ArrayList`, `HashMap`, `int counter`, `StringBuilder` hoặc request ID trong field có nguy cơ race khi aspect gọi đồng thời. Đừng coi `private final HashMap` là an toàn chỉ vì reference final. Dùng cấu trúc đồng thời, lock hoặc thiết kế stateless tùy invariant.

### Spring Data repository, giao dịch và persistence context

Các bean repository thường là proxy Spring được thiết kế cho shared injection. Nhưng entity/JPA persistence context cụ thể, transaction resource và các mutable objects trả về không mặc nhiên được chia sẻ giữa các luồng. Giữ transaction theo đúng ranh giới nghiệp vụ; đừng lưu `EntityManager` đã gắn với một invocation vào field aspect để dùng cho request tiếp theo.

### Bean request-scoped và scoped proxy

Nếu một singleton aspect cần dependency request-scoped, hãy thiết kế scoped proxy hoặc `ObjectProvider` theo Spring. Việc chuyển thread qua `@Async` hoặc `CompletableFuture` có thể không còn request context để resolve dependency. Không cache một request-scoped target vừa resolve vào field singleton.

### HTTP clients, metrics, loggers và tracing

Đọc contract của thư viện cụ thể. Nhiều client/metric abstractions cho phép dùng lại đồng thời, nhưng builder/request/response/session cụ thể có thể mutable. Dùng per-invocation builder, message và span. Với tracing context gắn thread, close scope trong `finally` đúng thread và tránh để lẫn request.

## 6. Atomic không đồng nghĩa mọi thuật toán đều đúng

`AtomicInteger.incrementAndGet()` bảo đảm tăng đếm không mất cập nhật. Nó **không** bảo đảm một chuỗi kiểm tra–cập nhật trên nhiều field:
 
~~~java
if (active.get() < limit) {
    active.incrementAndGet(); // Có thể vượt limit khi nhiều thread chạy cùng lúc.
}
~~~

Nếu invariant cần toàn bộ thao tác nguyên tử, dùng CAS loop, `Semaphore`, lock hoặc cơ chế dữ liệu có thao tác nguyên tử tương ứng. Với metric tần suất rất cao, `LongAdder` có thể phù hợp hơn `AtomicInteger` nếu mục tiêu là throughput và không cần snapshot tuyến tính hóa chính xác tại mọi thời điểm.

## 7. Advice chạy trên luồng nào?

Advice Spring AOP đồng bộ chạy trong luồng đang thực hiện lời gọi qua proxy, trừ khi các advisor như `@Async`, scheduler hoặc reactive pipeline thay đổi thời điểm/luồng quan sát.

- `@Async`: advice bên ngoài async interceptor có thể chạy ở caller thread, trong khi target thực thi ở executor thread. Thứ tự advisor và cấu hình proxy quyết định ranh giới quan sát.
- `Future`/`CompletionStage`: method return thành công với future **khác** công việc async hoàn tất thành công. Không coi `@AfterReturning` là callback terminal result.
- Reactor `Mono`/`Flux`: method có thể trả một publisher trước khi pipeline được subscribe. Để theo dõi terminal signal, tích hợp Reactor operators một cách có chủ đích, không chia sẻ mutable field ở aspect.
- ThreadLocal: không lưu vào field để “thay thế” ThreadLocal; nếu dùng ThreadLocal thì có hợp đồng set/restore/remove, kiểm tra thread pool và self-invocation.

## 8. Cách kiểm thử race và phạm vi Spring

Kiểm thử song song nên sử dụng barrier/latch để tạo cạnh tranh, chạy nhiều lượt và khẳng định invariant. Tránh so sánh thứ tự log giữa threads vì scheduler không cố định. Với demo trên, assert được `recordedCalls == N` và mỗi response đúng input; cố tình dùng `int++` không bảo đảm mọi lần chạy đều thất bại, vì race là bất định.

Kiểm tra bean thực sự đi qua proxy bằng `AopUtils.isAopProxy(bean)`, chạy cả JDK proxy và class-based proxy khi ứng dụng có hai mô hình. Thử self-invocation, method `final`/`private` và target tạo bằng `new` để phân biệt lỗi proxy boundary với lỗi concurrency.

## 9. Checklist áp dụng trong Spring

1. Xác nhận lifecycle của aspect trong `ApplicationContext`, loại target và cấu hình proxy.
2. Giữ đối số, `JoinPoint`, user ID, thời điểm bắt đầu, kết quả và exception trong scope của invocation.
3. Kiểm tra mọi dependency được tiêm: có mutable state không, thread-safety contract nào, scope nào?
4. Dùng constructor injection và `final` reference để rõ dependency, nhưng kiểm tra riêng tính an toàn của implementation.
5. Đo/kiểm thử concurrency thực tế, kiểm tra multi-field invariants và event ordering, không dựa trên một lần test.
6. Rà soát `@Async`, giao dịch, request scope, reactive context và cleanup trước khi triển khai.

## 10. Tài liệu chính thức

- Spring Framework Reference — Core AOP, `@AspectJ` support, advice và Spring proxies: https://docs.spring.io/spring-framework/reference/core/aop.html
- Spring Framework Reference — Bean scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Java API — AtomicInteger: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html

**Ghi nhớ:** Trong Spring, một dependency được tiêm vào aspect có thể được **nhiều lời gọi proxy dùng đồng thời**. Hãy giữ trạng thái lời gọi trong local variables và chứng minh an toàn luồng cho mọi trạng thái thực sự chia sẻ.