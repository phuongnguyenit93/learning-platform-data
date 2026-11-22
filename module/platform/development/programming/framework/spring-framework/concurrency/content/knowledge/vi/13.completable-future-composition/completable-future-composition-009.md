# Tránh gửi tác vụ hai lần khi vừa dùng `@Async` vừa dùng `supplyAsync()`

**Module:** Spring Framework - concurrency  
**Nhóm kiến thức:** Kết hợp CompletableFuture  
**Mục tiêu:** Phân biệt hai cơ chế lên lịch `@Async` và `CompletableFuture.supplyAsync()`, tránh tạo tác vụ bao ngoài chỉ để chờ tác vụ bên trong, chọn đúng executor và vẫn ghép các bước xử lý bằng `CompletableFuture` một cách có kiểm soát.

## 1. Vì sao dùng hai API bất đồng bộ cùng lúc có thể là phản tác dụng?

Xem một Spring service đã bật `@EnableAsync`:

```java
@Async("businessExecutor")
public CompletableFuture<String> create(String id) {
    return CompletableFuture.supplyAsync(
            () -> createReportBlocking(id));
}
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập: `createReportBlocking` và executor bean `"businessExecutor"` phải tồn tại. Một lời gọi qua Spring proxy ở đây có **hai lần giao tác vụ**:

1. Spring AOP intercept `@Async("businessExecutor")` và submit **method invocation** vào `businessExecutor`.
2. Khi một worker của pool đó chạy method, `CompletableFuture.supplyAsync(...)` tiếp tục submit **supplier** sang executor mặc định của `CompletableFuture`, thường là `ForkJoinPool.commonPool()`.

```text
Caller / HTTP thread
      |
      | gọi Spring proxy
      v
@Async("businessExecutor")
      |
      | SUBMIT #1
      v
Worker của businessExecutor (OUTER)
      |
      | body gọi supplyAsync
      | SUBMIT #2
      v
Worker của commonPool (INNER)
      |
      | chạy createReportBlocking(id)
      v
Future bên trong hoàn thành
      |
      v
Future do Spring proxy cung cấp hoàn thành
```

**Hai task submissions không có nghĩa nghiệp vụ bị chạy hai lần.** Trong ví dụ, supplier `createReportBlocking(id)` thường vẫn chỉ chạy **một lần cho mỗi invocation được chấp nhận**. Lãng phí nằm ở **hai lần scheduling**, nhiều queue/thread và khả năng có một worker ngoài đang chờ worker trong.

Ở Spring Framework **6.x**, `AsyncExecutionInterceptor` thực thi method đích trong một task của executor ngoài. Nếu method đích trả `Future`, interceptor có thể gọi `Future.get()` để lấy giá trị khi thực hiện task ngoài. Do đó, nếu inner future chưa hoàn tất, **outer worker có thể bị giữ để chờ**. Nó không tương đương với `thenCompose` phi chặn.

Hệ quả:

- Worker ngoài bận nhưng không làm công việc hữu ích, nên throughput có thể giảm.
- Tác vụ blocking I/O vô tình chạy trên `ForkJoinPool.commonPool()` thay vì I/O pool đã giới hạn.
- Trace/MDC và các `ThreadLocal` có thể mất qua ranh giới thứ hai.
- Lỗi/rejection/timeout phải được hiểu ở **hai** tầng.
- Nếu cả hai submit cùng một pool ít thread, có thể xảy ra **starvation hoặc deadlock**.

Trước khi thêm `supplyAsync` vào một method đã `@Async`, hãy hỏi: **“Tầng outer thực sự làm công việc gì, hay chỉ tạo Future khác rồi đợi?”**

## 2. Ba cơ chế thường bị nhầm

| Cách viết | Có submit task mới? | Ai chọn executor? | Tác dụng |
| --- | --- | --- | --- |
| `@Async("pool")` | Có, nếu lời gọi đi qua proxy async | Spring `@Async`/qualifier | Chuyển lời gọi method sang pool |
| `CompletableFuture.completedFuture(x)` | **Không** | Không cần executor | Tạo Future đã có kết quả `x` |
| `CompletableFuture.supplyAsync(fn)` | Có | Thường `ForkJoinPool.commonPool()` của JDK | Giao supplier cho executor mặc định JDK |
| `CompletableFuture.supplyAsync(fn, executor)` | Có | Executor được truyền vào | Giao supplier vào pool chỉ định |
| `thenApply(fn)` | Không mặc định gửi tác vụ riêng | Completion thread hoặc thread đăng ký callback | Biến đổi giá trị đã có |
| `thenApplyAsync(fn, executor)` | Có, cho callback | Executor chỉ định | Dời biến đổi nặng sang pool |
| `thenCompose(fn)` | Không tự thêm worker chỉ để chờ | Theo Future mà `fn` trả về | Nối một công việc đã có async contract |

`@Async` không phải tên khác của `CompletableFuture.supplyAsync`. `@Async` là **Spring proxy advice**; `supplyAsync` là **API JDK**. Việc Spring có bean tên `taskExecutor`, `applicationTaskExecutor` hay implement `AsyncConfigurer` **không** tự động thay executor của lệnh static `CompletableFuture.supplyAsync` không truyền tham số.

`completedFuture` cũng không tự làm công việc “chạy nền”. Nó chỉ phù hợp trong một method **đã được `@Async` proxy chuyển lên worker**, hoặc khi kết quả thực sự đã sẵn sàng.

## 3. Mẫu A — Một lần scheduling do Spring quản lý

Khi method của service thực hiện công việc đồng bộ/blocking, nhưng caller muốn nhận Future, để **Spring làm chủ bước chuyển thread**:

```java
@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> create(String reportId) {
        String result = createReportBlocking(reportId);
        return CompletableFuture.completedFuture(result);
    }
}
```

Đây là **class minh họa**; cần imports của Spring, `CompletableFuture`, method `createReportBlocking` và bean `"reportExecutor"`. Luồng:

```text
caller -> @Async proxy -> reportExecutor worker
                                   |
                                   | createReportBlocking(reportId)
                                   v
                       completedFuture(result)
                                   |
                                   v
                         caller's Future
```

**Chỉ một lần submit.** `createReportBlocking()` chạy trực tiếp trong worker do Spring chọn, và `completedFuture` không tạo task thứ hai.

Theo Javadoc Spring `@Async`, khi target method khai báo return type là `CompletableFuture<T>`, target có thể trả một **temporary future** đã chứa kết quả tính được (thường `CompletableFuture.completedFuture(result)`). Caller sẽ nhận một **actual asynchronous Future** do proxy Spring cung cấp. Hai đối tượng Future không bắt buộc là cùng một object.

Nếu method ném exception, Future phía caller hoàn thành lỗi. Nếu executor từ chối ngay lúc giao invocation, caller có thể gặp `TaskRejectedException` ở ranh giới submit. Lỗi business sau khi task đã nhận và lỗi không nhận task là **hai tình huống khác nhau**.

**Phù hợp:** service hiện có hàm tính toán, JDBC/HTTP client đồng bộ, thao tác tốn CPU được giao vào executor phù hợp. Các blocking operation vẫn phải có timeout, connection limit và chống overload; `@Async` không làm chúng trở thành non-blocking I/O.

## 4. Mẫu B — Không `@Async`, giao một supplier bằng JDK API

Nếu codebase tổ chức các bước bằng `CompletableFuture` thay vì annotation, để **method bình thường** trả Future:

```java
@Service
public class ReportWorkflow {

    private final Executor reportExecutor;

    public ReportWorkflow(
            @Qualifier("reportExecutor") Executor reportExecutor) {
        this.reportExecutor = reportExecutor;
    }

    public CompletableFuture<String> create(String reportId) {
        return CompletableFuture.supplyAsync(
                () -> createReportBlocking(reportId),
                reportExecutor);
    }
}
```

Đây là class minh họa: `createReportBlocking` chưa định nghĩa; cần imports `@Service`, `@Qualifier`, `Executor`, `CompletableFuture`. Luồng:

```text
caller -> create(...)  [không có @Async]
               |
               | supplyAsync(..., reportExecutor)
               v
        reportExecutor worker
               |
               v
        createReportBlocking(...)
```

**Cũng chỉ một lần submit.** Method `create` được gọi ngay trên thread caller nhưng chỉ tạo một future và gửi supplier, nên thường trả nhanh. Tác vụ business chạy trên worker.

Có thể chọn mẫu A hoặc B tùy kiến trúc. Điểm quan trọng là **không vô tình kết hợp cả hai mà không có công việc hữu ích ở tầng ngoài**.

Nếu một method gọi `CompletableFuture.supplyAsync` **không truyền executor**, việc đó thường gửi sang `ForkJoinPool.commonPool()` với một số fallback tùy điều kiện parallelism; nó **không** tự sử dụng `@Async("reportExecutor")` hay một executor bean được Spring quản lý. Với blocking JDBC, HTTP đồng bộ hoặc tác vụ có yêu cầu isolation, nên chọn executor tường minh, queue hữu hạn và giới hạn downstream.

## 5. Mẫu C — Dữ liệu đã bất đồng bộ: ghép các Future, không tạo outer worker

Giả sử hai client trả `CompletableFuture<Integer>` từ trước:

```java
@Service
public class QuoteService {

    private final PriceClient priceClient;
    private final ShippingClient shippingClient;

    public QuoteService(
            PriceClient priceClient,
            ShippingClient shippingClient) {
        this.priceClient = priceClient;
        this.shippingClient = shippingClient;
    }

    public CompletableFuture<Integer> quote(
            String sku, String address) {
        CompletableFuture<Integer> price =
                priceClient.fetchAsync(sku);
        CompletableFuture<Integer> shipping =
                shippingClient.fetchAsync(address);

        return price.thenCombine(shipping, Integer::sum);
    }
}
```

Đoạn trên là class **minh họa**: `PriceClient`/`ShippingClient` là dependency của ứng dụng. Hai lời gọi client có thể là non-blocking I/O thực, hoặc tự có pool của chúng. `QuoteService.quote` không cần annotation `@Async` chỉ vì return type là `CompletableFuture`: nó đã có async contract từ hai nguồn.

Khi B cần kết quả A:

```java
public CompletableFuture<Receipt> submitOrder(String id) {
    return priceClient.fetchAsync(id)
            .thenCompose(price -> receiptClient.createAsync(id, price));
}
```

Đoạn minh họa cần `Receipt`, `receiptClient` và `priceClient`. `thenCompose` ghép một `CompletionStage` do callback trả về mà không viết `.get()`/`.join()` để chặn thread trong continuation.

**Không nhầm:** `thenCompose` không làm công việc B tự chạy nếu `receiptClient.createAsync` không thực sự bắt đầu nó. Nó chỉ diễn đạt quan hệ phụ thuộc và làm phẳng Future thay vì tạo `CompletableFuture<CompletableFuture<T>>`.

## 6. Vì sao `@Async` và `supplyAsync` cùng một pool có thể gây deadlock?

Ví dụ cố tình sai, không dùng trong production:

```java
@Bean("tinyPool")
public ThreadPoolTaskExecutor tinyPool() {
    ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
    e.setCorePoolSize(1);
    e.setMaxPoolSize(1);
    e.setQueueCapacity(10);
    return e;
}

@Async("tinyPool")
public CompletableFuture<String> dangerous() {
    return CompletableFuture.supplyAsync(
            () -> slowBusinessWork(),
            tinyPool);
}
```

Đây là **hai đoạn minh họa** thuộc các class Spring phù hợp, không phải một file biên dịch độc lập; cần bean/field `tinyPool` và method `slowBusinessWork`. Nếu lời gọi đi qua Spring async proxy trong **Spring Framework 6.x**, luồng có thể là:

1. Proxy submit tác vụ **OUTER** vào `tinyPool`.
2. Worker duy nhất chạy method đích và gọi `supplyAsync(..., tinyPool)`.
3. Tác vụ **INNER** vào queue vì worker đang bận.
4. Method đích trả `CompletableFuture<String>` của inner.
5. Async interceptor đợi `Future.get()` ở worker OUTER để lấy giá trị.
6. INNER cần worker để chạy, nhưng worker duy nhất vẫn đang chờ INNER.

```text
tinyPool:
  worker-1: OUTER -> Future.get(INNER) -> chờ...
  queue:    INNER -> đang đợi worker-1
```

Kết quả có thể là **starvation/deadlock** không có tiến triển. Với 2, 4, 8 worker, lỗi có thể chỉ xuất hiện khi số outer task đồng thời đủ lớn chiếm hết worker, còn tất cả inner task nằm ở queue. Vì vậy chạy một request thành công không chứng minh thiết kế an toàn.

Tăng `maxPoolSize` để che lỗi không phải phương án nền tảng: khi burst lớn hơn giới hạn mới, triệu chứng có thể quay lại. `Future.get(timeout)` ở caller cũng không bảo đảm giải phóng worker mà Spring interceptor đang dùng để đợi.

**Sửa:** loại bỏ một tầng. Nếu `slowBusinessWork()` thực sự đồng bộ, dùng `@Async + completedFuture`. Nếu muốn tự lên lịch bằng `supplyAsync`, bỏ `@Async` khỏi method.

## 7. Java 17 chạy độc lập: đếm scheduling và số lần xử lý thật

Chương trình này chỉ dùng JDK, giúp phân biệt “hai lần submit” với “nghiệp vụ chạy hai lần”. Nó dùng **hai executor khác nhau** để tránh deadlock trong ví dụ. Ở đường double, outer worker **chủ động gọi `join()`** để mô phỏng một task ngoài chờ task trong; đây là **mô hình minh họa**, không phải trình giả lập chính xác toàn bộ Spring AOP.

Lưu thành file **`DoubleSchedulingJdkDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DoubleSchedulingJdkDemo {

    static final class CountingExecutor implements Executor, AutoCloseable {
        private final ExecutorService delegate =
                Executors.newSingleThreadExecutor();
        private final AtomicInteger submissions = new AtomicInteger();

        @Override
        public void execute(Runnable task) {
            submissions.incrementAndGet();
            delegate.execute(task);
        }

        int count() {
            return submissions.get();
        }

        @Override
        public void close() throws InterruptedException {
            delegate.shutdown();
            if (!delegate.awaitTermination(5, TimeUnit.SECONDS)) {
                delegate.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (CountingExecutor outer = new CountingExecutor();
             CountingExecutor inner = new CountingExecutor()) {

            AtomicInteger singleRuns = new AtomicInteger();
            AtomicInteger doubleRuns = new AtomicInteger();

            CompletableFuture<String> single =
                    CompletableFuture.supplyAsync(() -> {
                        singleRuns.incrementAndGet();
                        return "done";
                    }, outer);

            CompletableFuture<String> doubleScheduled =
                    CompletableFuture.supplyAsync(() ->
                            CompletableFuture.supplyAsync(() -> {
                                doubleRuns.incrementAndGet();
                                return "done";
                            }, inner).join(), outer);

            System.out.println("single=" + single.join());
            System.out.println("double=" + doubleScheduled.join());
            System.out.println("singleRuns=" + singleRuns.get());
            System.out.println("doubleRuns=" + doubleRuns.get());
            System.out.println("outerSubmissions=" + outer.count());
            System.out.println("innerSubmissions=" + inner.count());
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac DoubleSchedulingJdkDemo.java
java DoubleSchedulingJdkDemo
```

**Stdout chính xác khi chương trình hoàn tất bình thường:**

```text
single=done
double=done
singleRuns=1
doubleRuns=1
outerSubmissions=2
innerSubmissions=1
```

Giải thích:

- Có **hai logical requests** trong cùng chương trình: `single` và `doubleScheduled`.
- Mỗi request gọi nghiệp vụ đúng một lần (`singleRuns=1`, `doubleRuns=1`).
- Outer executor nhận **hai** task — một cho mỗi logical request.
- Inner executor nhận **một** task chỉ thuộc đường `doubleScheduled`.
- Tổng số task được gửi là **ba**, dù chỉ có hai lần thực thi business work. Double scheduling ở request thứ hai không đồng nghĩa duplicate side effect.

`CompletableFuture.join()` ở `main` chỉ chờ kết quả cuối để in kiểm thử. `join()` **bên trong outer task** thuộc đường double mới là điểm mô phỏng việc chiếm worker để chờ công việc trên pool khác.

Lưu ý `Executors.newSingleThreadExecutor()` có queue bộ nhớ không giới hạn theo công suất xử lý; đây chỉ là một ví dụ ngắn, không phải mẫu executor cho production chịu tải lớn.

## 8. Ví dụ Spring Boot hoàn chỉnh: một tầng, hai tầng, và pipeline thuần Future

Ví dụ dùng **Java 17+**, **Spring Boot 3.5.7** với Spring Framework 6.2.x và Maven, gồm hai `ThreadPoolTaskExecutor` độc lập để quan sát ranh giới:

- `outerExecutor` có thread prefix `outer-`.
- `innerExecutor` có thread prefix `inner-`.
- Method `singleDispatch` dùng `@Async` + `completedFuture`.
- Method `doubleDispatch` cố tình dùng `@Async` + `supplyAsync` để minh họa hai tầng, **không khuyến nghị dùng trong production**.
- Method `composeWithoutOuterAsync` không có `@Async`; nó gửi hai supplier độc lập rồi ghép bằng `thenCombine`.

### 8.1. Cấu trúc dự án

```text
double-dispatch-spring/
├── pom.xml
└── src/main/java/com/example/doubledispatch/
    ├── DoubleDispatchApplication.java
    ├── ExecutorConfiguration.java
    └── JobService.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>double-dispatch-spring</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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
```

`spring-boot-starter-aop` mang theo khả năng proxy/AOP cần cho ví dụ. Đây là chương trình CLI, không cần web server.

### 8.3. `src/main/java/com/example/doubledispatch/ExecutorConfiguration.java`

```java
package com.example.doubledispatch;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ExecutorConfiguration {

    @Bean("outerExecutor")
    public ThreadPoolTaskExecutor outerExecutor() {
        ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
        e.setCorePoolSize(2);
        e.setMaxPoolSize(2);
        e.setQueueCapacity(8);
        e.setThreadNamePrefix("outer-");
        e.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return e;
    }

    @Bean("innerExecutor")
    public ThreadPoolTaskExecutor innerExecutor() {
        ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
        e.setCorePoolSize(2);
        e.setMaxPoolSize(2);
        e.setQueueCapacity(8);
        e.setThreadNamePrefix("inner-");
        e.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return e;
    }
}
```

Ở đây hai pool được tách để thử nghiệm an toàn; production chỉ tạo pool thứ hai khi có loại workload khác thực sự cần tách. `ThreadPoolTaskExecutor` do Spring quản lý lifecycle qua bean; queue hữu hạn và `AbortPolicy` giúp biết khi quá tải.

### 8.4. `src/main/java/com/example/doubledispatch/JobService.java`

```java
package com.example.doubledispatch;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    private final Executor innerExecutor;

    public JobService(@Qualifier("innerExecutor") Executor innerExecutor) {
        this.innerExecutor = innerExecutor;
    }

    // Một lần submit: business xử lý trong worker của Spring.
    @Async("outerExecutor")
    public CompletableFuture<String> singleDispatch(String id) {
        boolean onOuter =
                Thread.currentThread().getName().startsWith("outer-");
        String value = onOuter ? "outer-" + id : "unexpected";
        return CompletableFuture.completedFuture(value);
    }

    // Cố tình minh họa anti-pattern hai lần submit.
    @Async("outerExecutor")
    public CompletableFuture<String> doubleDispatch(String id) {
        boolean onOuter =
                Thread.currentThread().getName().startsWith("outer-");

        return CompletableFuture.supplyAsync(() -> {
            boolean onInner =
                    Thread.currentThread().getName().startsWith("inner-");
            return onOuter && onInner
                    ? "outer+inner-" + id
                    : "unexpected";
        }, innerExecutor);
    }

    // Không @Async: tự xây pipeline JDK, không có outer task.
    public CompletableFuture<Integer> composeWithoutOuterAsync() {
        CompletableFuture<Integer> price =
                CompletableFuture.supplyAsync(
                        () -> 100, innerExecutor);

        CompletableFuture<Integer> shipping =
                CompletableFuture.supplyAsync(
                        () -> 25, innerExecutor);

        return price.thenCombine(shipping, Integer::sum);
    }
}
```

- Với `singleDispatch`, caller nhận Future từ proxy sau khi Spring đã giao invocation vào pool `outer-`. Trong body không có thêm `supplyAsync`.
- Với `doubleDispatch`, Spring giao invocation vào `outer-`; body lại giao supplier vào `inner-`. Theo Spring Framework 6.x, interceptor có thể chờ inner Future trước khi hoàn thành Future trả cho caller. Đây là ví dụ **để thấy thiết kế có hai tầng**, không phải khuyến nghị.
- Với `composeWithoutOuterAsync`, method bình thường bắt đầu hai tác vụ JDK vào `inner-`, sau đó dùng `thenCombine`. Orchestrator không `join()` và không cần một worker bao ngoài chỉ để chờ.

### 8.5. `src/main/java/com/example/doubledispatch/DoubleDispatchApplication.java`

```java
package com.example.doubledispatch;

import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DoubleDispatchApplication {

    public static void main(String[] args) throws Exception {
        SpringApplication app =
                new SpringApplication(DoubleDispatchApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            JobService jobs = context.getBean(JobService.class);

            System.out.println("single=" +
                    jobs.singleDispatch("A").get(5, TimeUnit.SECONDS));

            System.out.println("double=" +
                    jobs.doubleDispatch("B").get(5, TimeUnit.SECONDS));

            System.out.println("composed=" +
                    jobs.composeWithoutOuterAsync().get(
                            5, TimeUnit.SECONDS));
        }
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn -q spring-boot:run
```

**Ba dòng do `System.out` chủ động in khi demo chạy bình thường:**

```text
single=outer-A
double=outer+inner-B
composed=125
```

`single=outer-A` cho thấy body `@Async` ở pool ngoài. `double=outer+inner-B` cho thấy body bắt đầu ở pool ngoài, supplier ở pool trong. `composed=125` cho thấy hai Future độc lập được ghép mà không có tầng `@Async` bao ngoài. `main` cố tình chờ bằng `get(timeout)` để có output xác định; cách kiểm thử CLI này không phải mẫu viết controller HTTP không chặn.

Nhận diện pool theo **thread name** chỉ nên dùng ở ví dụ và khi debug, không phải điều kiện nghiệp vụ đáng tin. Giá trị core/max/queue ở đây được chọn để demo; cần load test và giới hạn CPU, JDBC/HTTP connections khi dùng thực tế.

## 9. `@Async`, Spring proxy và self-invocation

`@Async` ở chế độ proxy mặc định chỉ có hiệu lực khi lời gọi đi qua Spring-managed proxy. Hai tình huống cần tách bạch:

**Double dispatch:** lời gọi qua proxy, Spring submit một lần, body `supplyAsync` submit thêm lần nữa.

**Không có dispatch từ Spring:** lời gọi `this.doAsync()` trong cùng bean, đối tượng tự tạo bằng `new`, hoặc chưa bật `@EnableAsync`; annotation có thể không được intercept.

Ví dụ:

```java
@Service
public class ServiceA {

    public CompletableFuture<String> caller() {
        return this.worker(); // self-invocation, bỏ qua proxy @Async
    }

    @Async("businessExecutor")
    public CompletableFuture<String> worker() {
        return CompletableFuture.completedFuture(blockingWork());
    }
}
```

Đoạn class minh họa cần imports và method `blockingWork`. Khi gọi `caller()`, `this.worker()` có thể chạy **trực tiếp trên thread caller**, dù return type là `CompletableFuture`. `completedFuture` không tự tạo worker.

**Chẩn đoán:** kiểm tra có `@EnableAsync` trong đúng application context; method public được gọi từ bean khác qua proxy; bean executor đúng tên; thread dump và metrics có thấy một hay hai lần submit; tránh chỉ dựa trên việc method trả Future.

## 10. Khi nào thêm một stage async nữa là hợp lệ?

Không phải cứ có nhiều Future hoặc nhiều stage là sai. Điều cần loại bỏ là **tác vụ bao ngoài không có giá trị**.

Ví dụ:

```java
CompletableFuture<byte[]> compressed =
        downloadedBytes.thenApplyAsync(
                bytes -> compressCpuHeavy(bytes),
                cpuExecutor);
```

Đoạn minh họa cần `downloadedBytes`, `compressCpuHeavy` và `cpuExecutor`. Đây là **một bước CPU nặng thực sự** cần tách khỏi thread đang hoàn thành I/O; dùng `thenApplyAsync` và CPU pool là có lý do.

Khi A trả dữ liệu và B trả Future:

```java
CompletableFuture<Receipt> receipt =
        quoteFuture.thenCompose(
                quote -> paymentClient.chargeAsync(quote));
```

Đoạn minh họa cần `Receipt`, `quoteFuture`, `paymentClient`. `thenCompose` nối hai stage mà không chặn một worker ở giữa bằng `join()`.

Ngược lại, mã sau tạo thêm một worker chỉ để chờ:

```java
CompletableFuture<Receipt> receipt =
        CompletableFuture.supplyAsync(
                () -> paymentClient.chargeAsync(quote).join(),
                executor);
```

Đây là đoạn minh họa với `paymentClient`, `quote`, `executor`; trong worker sẽ có một `.join()` chặn. Khi dependency đã trả Future, thường tốt hơn là **trả future trực tiếp** hoặc dùng `thenCompose`, không cần bọc nó trong supplier rồi block.

Có thể có ngoại lệ kiến trúc (chuyển từ một boundary blocking cũ sang một pool riêng, chính sách isolation đặc biệt, nhiệm vụ outer làm preprocessing nặng). Nhưng phải xác định **work thật của mỗi stage**, tài nguyên dùng và cách chờ. Trong Spring 6.x, một `@Async` method trả inner Future vẫn có nguy cơ outer worker chờ inner; khi đó chuyển sang orchestrator không `@Async` thường là lời giải tốt hơn.

## 11. Lỗi, từ chối tác vụ và cancellation ở hai tầng

Một pipeline có hai điểm submit phải xử lý **hai điểm có thể thất bại**:

- **Outer rejection:** Spring `@Async` không gửi được invocation vì executor đã shutdown/quá tải; với `ThreadPoolTaskExecutor` và `AbortPolicy`, có thể ném `TaskRejectedException` ngay lúc caller gửi.
- **Inner rejection:** `CompletableFuture.supplyAsync(..., executor)` không gửi được supplier. Với Spring executor, lỗi nhận việc cũng có thể theo contract `TaskRejectedException`; với JDK `ThreadPoolExecutor` thường là `RejectedExecutionException`.
- **Inner execution failure:** supplier đã được nhận nhưng ném exception; inner Future hoàn thành ngoại lệ, rồi lỗi được lan qua cơ chế async proxy / Future phía caller.
- **Timeout:** caller `get(timeout)` chỉ giới hạn thời gian chờ của caller. `orTimeout` hoàn thành Future ngoại lệ khi quá hạn nhưng **không chắc ngắt** một HTTP request/JDBC query hoặc giải phóng outer worker đang chờ inner.
- **Cancellation:** `CompletableFuture.cancel(true)` hoàn thành Future với `CancellationException` theo hợp đồng; `mayInterruptIfRunning` không đảm bảo ngắt supplier. Cần cancellation thực ở HTTP/JDBC client hoặc cơ chế hợp tác riêng.
- **Retry:** nhiều tầng retry không có idempotency có thể lặp side effect dù vấn đề ban đầu chỉ là scheduling. Với email, chuyển tiền hoặc cập nhật DB, cần khóa nghiệp vụ và idempotency phù hợp.

Ví dụ quan sát lỗi phía caller:

```java
CompletableFuture<Report> future = service.createReport(id);

future.whenComplete((value, error) -> {
    if (error != null) {
        metrics.failed(id, error);
    } else {
        metrics.completed(id);
    }
});
```

Đây là đoạn minh họa, cần kiểu `Report`, `service`, `id`, `metrics`. `whenComplete` dùng để quan sát. Muốn phục hồi thành giá trị khác, cần `exceptionally`/`handle` theo hợp đồng; đừng mặc định coi lỗi tạo báo cáo như một báo cáo thành công rỗng.

Với `@Async void`, caller không có Future để quan sát kết quả, nên dùng `AsyncUncaughtExceptionHandler` hoặc cơ chế ghi trạng thái phù hợp. Với `@Async CompletableFuture<T>`, lỗi nghiệp vụ nên được quan sát qua Future/completion stage.

**Không dùng `CallerRunsPolicy` vô thức** để “giải quyết” overload: khi pool đầy, policy này có thể thực thi task trên chính thread gửi, làm một Servlet request thread bị giữ lâu. Dùng queue hữu hạn, admission control và phản hồi overload rõ ràng.

## 12. Context, transaction và việc chuyển thread hai lần

Mỗi lần rời thread gọi có thể ảnh hưởng những giá trị gắn với thread:

- MDC/trace ID (`ThreadLocal`), locale và một số security/request context không tự chuyển qua mọi executor.
- Spring `@Transactional` gắn với transaction manager/resource theo thread; không được tự copy transaction từ caller sang inner task.
- `TaskDecorator` có thể hỗ trợ capture/restore context cho task trong **một executor cụ thể**, nhưng không tự bảo đảm context đi qua `commonPool` nếu inner dùng `supplyAsync` không truyền executor.
- Nếu một transaction DB đang mở trong outer worker rồi inner tự chạy update DB, chúng không mặc nhiên cùng một transaction. Thiết kế transaction riêng cho worker thật và đảm bảo thứ tự commit khi cần.
- Nếu task phải chạy sau khi HTTP request kết thúc, tránh phụ thuộc trực tiếp vào request-scope object sống ngắn; truyền ID/dữ liệu đã validate.

Việc giảm một tầng scheduling thường cũng giúp giảm số bước phải truyền context và đơn giản hóa tracing. Với các giai đoạn thực sự cần đổi pool, truyền context bằng cơ chế được stack hỗ trợ và cleanup trong `finally`.

## 13. Checklist kiểm tra code thật

Trước khi chốt cách viết:

1. **Đánh dấu nơi gửi task:** tìm tất cả `@Async`, `supplyAsync`, `runAsync`, `thenApplyAsync`, `thenComposeAsync`, `Executor.execute` hoặc `submit` trong call graph.
2. **Xác định ai làm work:** outer method có CPU/IO work thật không? Hay chỉ tạo một Future khác?
3. **Xác định từng executor:** named Spring bean, JDK common pool, task scheduler, virtual-thread executor hay client I/O? Đừng suy từ tên method.
4. **Kiểm tra lời gọi qua proxy:** `@EnableAsync`, bean được Spring quản lý, không self-invocation.
5. **Kiểm tra Future target:** `completedFuture` đã có giá trị hay `supplyAsync` còn task phía sau? Worker ngoài có đang chờ Future không?
6. **Kiểm tra pool/queue:** core/max/queue hữu hạn, chính sách rejection, tránh chờ task trong chính pool ít worker.
7. **Kiểm tra lỗi:** lỗi nhận task, lỗi khi chạy, exceptional completion, timeout, cancellation phải được quan sát riêng.
8. **Kiểm tra side effect:** đếm lần business method thực chạy, phân biệt với số callback/task được submit.
9. **Kiểm tra context:** trace/MDC, security, transaction, request lifecycle ở mỗi ranh giới thread.
10. **Kiểm tra hợp đồng với caller:** HTTP đợi Future, trả Future qua MVC async, hay trả `202` với durable job? `CompletableFuture` trong RAM **không** tự bền vững sau restart.

### Một phép thử xác định thay vì đoán timing

Với Java thuần, dùng executor tự đếm `execute`, như `DoubleSchedulingJdkDemo` ở trên. Với Spring integration test, dùng hai bean executor được instrument hoặc `TaskDecorator` để xác nhận nơi business chạy, kết hợp `CountDownLatch` để kiểm soát lúc worker bận. Không cần `Thread.sleep` để hy vọng tạo race.

Test thêm:

- Một request đi qua proxy `@Async`, business chạy một lần.
- Code anti-pattern dùng hai pool thực sự tạo hai submissions.
- Khi outer và inner dùng cùng pool 1 worker + queue hữu hạn, **test có timeout nghiêm ngặt** chứng minh rủi ro kẹt trong Spring/version được dùng; không chủ động tạo deadlock trên production.
- Một inner stage ném exception, Future phía caller lỗi, không bị nuốt.
- Outer hoặc inner bị từ chối khi queue đầy, hệ thống trả lỗi hợp đồng thay vì báo đã nhận job.
- `@Async` self-invocation chạy khác lời gọi qua Spring proxy.

## 14. Dấu hiệu trong production cho thấy bị double scheduling

| Dấu hiệu | Giải thích có thể | Cách kiểm chứng |
| --- | --- | --- |
| `activeCount` outer cao nhưng CPU thấp | Worker ngoài đang chờ inner | Thread dump tìm `Future.get`/`join` |
| Inner queue tăng dù outer queue cũng tăng | Cùng logical request đi qua hai pool | Trace hai lần submit, gắn correlation ID |
| Tăng worker outer không cải thiện throughput | Bottleneck nằm ở inner/downstream | Đo queue wait và execution time từng pool |
| Common pool có nhiều blocking JDBC task | `supplyAsync` không truyền executor | Tìm source callsite và thread names |
| Trace ID có ở outer nhưng mất ở inner | Context không đi qua executor thứ hai | Kiểm tra TaskDecorator và context propagation |
| CPU/GC tăng do nhiều callback/FutureTask | Extra allocations/scheduling | Profile allocation, quan sát queue |
| Thỉnh thoảng treo khi tải cao | Outer đợi inner trên cùng pool | Thread dump và kiểm thử saturation |
| Client timeout nhưng worker vẫn bận | Timeout caller không dừng inner | Theo dõi lifetime task, connection timeout/cancel |

Không khẳng định chỉ từ một metric. Một worker có CPU thấp có thể đang chờ mạng hoặc lock theo thiết kế. Cần đối chiếu thread dump, call graph và timing trước khi kết luận do double scheduling.

**Sửa triệt để** là dời scheduling đến đúng stage thực hiện work, bỏ outer wrapper không có ích. Sau refactor, đo lại throughput, p95/p99, số lần reject, queue depth và độ hoàn thiện của trace.

## 15. Các lỗi thường gặp và cách sửa

| Lỗi | Tại sao sai/nguy hiểm? | Cách sửa |
| --- | --- | --- |
| `@Async` method chỉ trả `supplyAsync` | Hai lần submit, worker ngoài có thể chờ | `@Async + completedFuture` hoặc bỏ `@Async` |
| `@Async` và `supplyAsync` gửi cùng fixed pool | Nguy cơ worker chờ task đang queue cùng pool | Chọn một tầng; không `get/join` trong worker |
| Không truyền executor cho `supplyAsync` | Work chạy ngoài Spring pool mong muốn | Truyền executor hoặc chỉ dùng `@Async` |
| Tin rằng hai lần submit = side effect chạy hai lần | Chẩn đoán sai nguyên nhân | Đếm submissions và business executions riêng |
| Bọc Future của SDK trong một `supplyAsync(() -> future.join())` | Tạo worker chỉ để block | Trả Future hoặc `thenCompose` |
| Gọi `this.doAsync()` trong cùng bean | Bỏ qua Spring proxy | Gọi qua bean khác hoặc cấu trúc lại |
| Controller gọi `.join()` ngay | HTTP thread vẫn chặn | Trả async result, hoặc job API riêng |
| `get(timeout)` rồi nghĩ đã cancel inner task | Worker và I/O có thể vẫn chạy | Timeout/cancel thật ở client/driver |
| Mặc định retry cả hai tầng | Side effect có thể lặp ngoài dự kiến | Idempotency, retry budget, dedupe |
| Queue không giới hạn và nhiều nested Future | Tăng backlog, memory và latency | Bounded queue, backpressure/admission |
| Chỉ thêm thread để chữa deadlock | Che lỗi tạm, không giải quyết vòng chờ | Bỏ wait/scheduling không cần thiết |
| Copy transaction sang worker bằng ThreadLocal | Sai boundary và rò tài nguyên | Transaction độc lập và context propagation đúng |
| Bỏ mặc `CompletableFuture` lỗi | Lỗi không được ghi nhận | Quan sát `whenComplete`, `handle`, job status |
| Trả HTTP `202` ngay sau Future RAM | Crash có thể mất job | Durable job/outbox/broker khi cần |

## 16. Câu hỏi tự kiểm tra

**1.** `@Async("ioPool")` method trả `CompletableFuture.supplyAsync(() -> jdbcCall())`. Có mấy lần gửi task và supplier thường chạy ở đâu?  
**Đáp:** Có hai tầng submit khi Spring proxy hoạt động: outer vào `ioPool`, inner thường vào `ForkJoinPool.commonPool()` nếu không truyền executor.

**2.** Thay bằng `return CompletableFuture.completedFuture(jdbcCall())` có chạy JDBC ở worker không?  
**Đáp:** Có, nếu lời gọi đi qua Spring `@Async` proxy. `completedFuture` không tự tạo task.

**3.** Vì sao hai task submissions không đồng nghĩa `jdbcCall()` chạy hai lần?  
**Đáp:** Outer task có thể chỉ giao và chờ inner; phần nghiệp vụ nằm trong inner supplier, chạy một lần. Retry/side effect là vấn đề riêng.

**4.** Một fixed pool có 1 worker và queue 10. Outer `@Async` gọi `supplyAsync` trên cùng pool, rồi trả Future. Rủi ro gì?  
**Đáp:** Outer giữ worker chờ inner; inner đợi worker còn bận: deadlock/starvation.

**5.** Phải dùng `@Async` để ghép hai client đã trả Future chưa?  
**Đáp:** Không. Orchestrator có thể không `@Async`, khởi động các Future rồi dùng `thenCombine`.

**6.** Khi B trả Future và phụ thuộc A, có nên viết `thenApply(a -> bAsync(a).join())` không?  
**Đáp:** Tránh, vì callback có thể chặn worker. Dùng `thenCompose(a -> bAsync(a))`.

**7.** `@Async` tự quyết định executor cho `CompletableFuture.supplyAsync(fn)` không tham số không?  
**Đáp:** Không. Static API JDK dùng quy tắc executor của JDK; cần truyền executor nếu muốn dùng Spring bean.

**8.** `thenApplyAsync(fn, cpuExecutor)` có luôn là double scheduling sai không?  
**Đáp:** Không. Nếu đó là bước CPU nặng riêng cần pool khác, async boundary đó có công việc thật và có thể hợp lý.

**9.** Caller `future.get(2, SECONDS)` hết hạn có làm ngừng HTTP call trong inner worker không?  
**Đáp:** Không. Đây là timeout chờ của caller; cần timeout/cancel ở client I/O thực.

**10.** `@Async` method được gọi qua `this.method()` có chắc được Spring chuyển thread không?  
**Đáp:** Không. Self-invocation bỏ qua proxy theo `AdviceMode.PROXY` mặc định.

## 17. Ghi nhớ và tài liệu chính thức

**Nguyên tắc:** một tác vụ nghiệp vụ chỉ nên có **một owner của việc gửi task** ở mỗi ranh giới thực sự cần thiết. Dùng nhiều stage để ghép kết quả là bình thường; tạo một **outer worker chỉ để đợi inner worker** là cấu trúc nên tránh.

- **Có `@Async` cho blocking method:** tính toán trong worker Spring, trả `CompletableFuture.completedFuture(result)`.
- **Muốn tự dùng JDK Future:** bỏ `@Async`, gọi `supplyAsync(supplier, executor)` trực tiếp.
- **Nguồn đã là Future:** trả/ghép `thenCombine`, `thenCompose`, `allOf`; tránh thêm outer worker.
- **Tác vụ chuyển pool có chủ đích:** dùng biến thể `Async` với executor tường minh và xác định business work thật, tài nguyên, timeout.
- **Chẩn đoán:** đếm số lần submit và số lần business chạy riêng, kiểm tra Spring proxy, thread dump, queue và exceptional completion.
- **Vận hành:** timeout/cancel thực, queue hữu hạn, context propagation và idempotency. Future trong RAM không thay thế durable job queue.

Tài liệu tham khảo:

- [Spring Framework 6.2 — `@Async` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/Async.html) — temporary Future từ target và actual Future do proxy cung cấp.
- [Spring Framework 6.2 — `AsyncExecutionInterceptor`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/interceptor/AsyncExecutionInterceptor.html) — invocation được giao cho executor của Spring.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — annotation, qualifier, exception handling và executor.
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — core/max/queue/lifecycle/rejection.
- [Java SE 17 — `CompletableFuture` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — `completedFuture`, `supplyAsync`, policies, composition, exception và cancellation.
- [Java SE 17 — `Executor` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html) — hợp đồng gửi task của JDK.