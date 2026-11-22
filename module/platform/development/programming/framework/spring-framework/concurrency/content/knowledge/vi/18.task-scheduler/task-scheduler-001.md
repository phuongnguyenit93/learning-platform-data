# `TaskScheduler` biểu diễn lập lịch tách khỏi môi trường thực thi

**Module:** Spring Framework - concurrency  
**Nhóm:** TaskScheduler  
**Chủ đề:** TaskScheduler biểu diễn lập lịch tách khỏi môi trường thực thi.

## 1. Hai câu hỏi khác nhau: khi nào chạy và chạy bằng tài nguyên nào?

Một ứng dụng có thể cần đồng bộ dữ liệu mỗi 5 phút, hủy yêu cầu hết hạn sau 30 giây, hoặc tạo báo cáo lúc 09:00 theo giờ Việt Nam. Các trường hợp này luôn có hai quyết định:

1. **Scheduling policy:** việc nên được kích hoạt *khi nào*? Một lần tại `Instant`, sau một `Duration`, theo fixed-rate, fixed-delay, hoặc bởi `Trigger` như cron?
2. **Execution policy:** callback chạy ở đâu? Có bao nhiêu worker, queue thế nào, có phải chờ DB/HTTP không, lúc quá tải xử lý ra sao?

Spring dùng `org.springframework.scheduling.TaskScheduler` để biểu diễn **nhu cầu lập lịch** dưới một giao diện ổn định. Mã nghiệp vụ yêu cầu “chạy Runnable tại thời điểm T” mà không cần biết backend đang bọc `ScheduledExecutorService` của JDK, thread pool riêng hay scheduler do container cung cấp.

```text
Business code
      |
      | TaskScheduler.schedule(task, when/trigger)
      v
TaskScheduler SPI của Spring
      |
      +-- ThreadPoolTaskScheduler: local scheduler threads
      +-- ConcurrentTaskScheduler: adapter của JDK scheduler
      +-- DefaultManagedTaskScheduler: container-managed
      |
      v
Backend quyết định thread, queue, lifecycle
      |
      v
Runnable.run()
```

**Cảnh báo quan trọng:** “tách abstraction” **không có nghĩa** Spring luôn dùng một timer thread rồi tự chuyển business work sang một worker pool khác. `ThreadPoolTaskScheduler` truyền thống **thực thi callback ngay trên scheduler threads**. Nếu callback chặn I/O lâu, chính scheduler threads sẽ bận và những lịch khác có thể bị trễ. Muốn tách timer khỏi business worker thực sự, phải chủ động dispatch sang `TaskExecutor`.

## 2. Phân biệt các interface và implementation

| API | Vai trò | Phương thức tiêu biểu | Điều không mặc định |
| --- | --- | --- | --- |
| JDK `Executor` | Giao `Runnable` đi thực thi | `execute(Runnable)` | Không biểu diễn lịch thời gian |
| Spring `TaskExecutor` | Abstraction thực thi cho các component Spring | `execute(Runnable)` | Không tự tạo cron/fixed-delay |
| JDK `ScheduledExecutorService` | Executor có khả năng lập lịch | `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay` | Không nhận `Trigger` Spring trực tiếp |
| Spring `TaskScheduler` | Abstraction yêu cầu khởi động theo thời điểm/quy tắc | `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay` | Không tự durable hay cluster-wide once |
| `ThreadPoolTaskScheduler` | Implementation Spring với local `ScheduledThreadPoolExecutor` | Bean config pool, clock, error handler | Callback chạy trên scheduler threads |
| `ConcurrentTaskScheduler` | Thích nghi scheduler JDK sẵn có | `TaskScheduler` | Ownership của backend vẫn phải rõ |
| `DefaultManagedTaskScheduler` | Dùng managed scheduler trong Jakarta EE | `TaskScheduler` | Không tự thay quy tắc container |
| Quartz | Job/trigger subsystem có hỗ trợ JobStore | Trigger, JobDetail, JobStore | Persistence chỉ khi cấu hình đúng |

`ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` không tương đương: loại trước tối ưu việc giao công việc vào worker pool; loại sau có semantics scheduling dựa trên thời gian. Một implementation có thể hỗ trợ hơn một interface, nhưng logic nghiệp vụ nên phụ thuộc **interface đúng mục đích**.

## 3. Các phương thức quan trọng của `TaskScheduler`

Trong Spring Framework 6.2, giao diện có các phương thức chính:

```java
public interface TaskScheduler {
    Clock getClock();

    ScheduledFuture<?> schedule(
            Runnable task, Instant startTime);
    ScheduledFuture<?> schedule(
            Runnable task, Trigger trigger);

    ScheduledFuture<?> scheduleAtFixedRate(
            Runnable task, Instant startTime, Duration period);
    ScheduledFuture<?> scheduleAtFixedRate(
            Runnable task, Duration period);

    ScheduledFuture<?> scheduleWithFixedDelay(
            Runnable task, Instant startTime, Duration delay);
    ScheduledFuture<?> scheduleWithFixedDelay(
            Runnable task, Duration delay);
}
```

Đây là **phác thảo chữ ký API**, không phải source code để viết lại. Spring còn có một số overload cũ dùng `Date`/`long` đã deprecated; hãy ưu tiên `Instant` và `Duration`.

### Một lần tại thời điểm tuyệt đối

```java
Instant when = scheduler.getClock().instant().plusSeconds(30);

ScheduledFuture<?> handle =
        scheduler.schedule(
                () -> expireRequest(requestId),
                when);
```

Đây là **đoạn minh họa**: cần có `scheduler`, `requestId` và method `expireRequest`. `Instant` là thời điểm tuyệt đối; khi lịch được nhận, callback sẽ chạy vào hoặc sau mốc đó theo khả năng backend. Nếu mốc đã qua, nó được chạy càng sớm càng tốt.

`getClock()` cho phép tính thời gian theo clock của scheduler thay vì trộn các nguồn clock tùy ý; điều này còn hữu ích khi kiểm thử.

### Fixed-rate theo nhịp dự kiến

```java
ScheduledFuture<?> handle =
        scheduler.scheduleAtFixedRate(
                this::measureHealth,
                Duration.ofSeconds(5));
```

`measureHealth` là method thuộc ứng dụng. Khoảng **5 giây giữa các mốc bắt đầu dự kiến** là policy. Nếu một lần chạy kéo dài 7 giây, lần tiếp theo có thể trễ so với lịch dự kiến; không có bảo đảm real-time chính xác đến millisecond.

### Fixed-delay nghỉ sau khi callback hoàn tất

```java
ScheduledFuture<?> handle =
        scheduler.scheduleWithFixedDelay(
                this::pollPartner,
                Duration.ofSeconds(5));
```

`pollPartner` thuộc ứng dụng. Delay bắt đầu **sau khi callback trước đã hoàn thành**. Callback chạy 7 giây cộng delay 5 giây khiến lần kế không bắt đầu trước khoảng 12 giây tính từ đầu lần trước.

### Trigger cho lịch linh hoạt

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Trigger trigger = new CronTrigger("0 0/5 * * * *", zone);

ScheduledFuture<?> handle =
        scheduler.schedule(this::refreshCatalog, trigger);
```

Đây là đoạn minh họa cần imports `ZoneId`, `Trigger`, `CronTrigger` và method `refreshCatalog`. Spring cron có **sáu trường**: giây, phút, giờ, ngày trong tháng, tháng, thứ. Biểu thức này kích hoạt ở giây 0 của mỗi phút chia hết cho 5 theo zone chỉ định.

Nếu `Trigger` không trả thời điểm tiếp theo, `schedule(Runnable, Trigger)` **có thể trả `null`**; code lưu handle phải kiểm tra.

## 4. Fixed-rate, fixed-delay và cron không thể dùng thay nhau

Cho một callback chạy 7 giây với period/delay 5 giây:

```text
fixed-rate, period=5s:
Mốc dự kiến:  0s ---- 5s ---- 10s ---- 15s ...
Thực thi:     [0s ------ 7s][7s ------- 14s]...
               Lần thứ hai bị trễ so với mốc 5s.

fixed-delay, delay=5s:
Thực thi:     [0s ------ 7s].....[12s ------- 19s]...
                         ^ khoảng nghỉ 5 giây sau completion
```

Với `ScheduledThreadPoolExecutor` của JDK, các lần thực thi định kỳ của **cùng một scheduled task** không chồng nhau, kể cả với fixed-rate. Tuy nhiên nhiều scheduled tasks khác nhau, nhiều replicas, hoặc việc offload sang pool khác có thể chạy chồng nhau.

**Bẫy offload:** nếu callback chỉ làm `worker.execute(this::longJob)` rồi return nhanh, scheduler xem **callback dispatch** đã hoàn thành. Fixed-delay khi đó đo khoảng nghỉ từ lần dispatch trước, không phải từ lúc `longJob` kết thúc. Nếu nghiệp vụ yêu cầu không overlap, cần guard hoặc hệ thống job có khả năng claim/lock.

Cron phục vụ **lịch theo giờ địa phương** hơn là nhịp giữa các lần chạy. 09:00 giờ Việt Nam không phải luôn tương đương “cứ thêm đúng 24 giờ” ở mọi zone trên thế giới; các zone có DST còn có giờ bị lặp hoặc không tồn tại.

## 5. `Trigger` và `TriggerContext`

`Trigger` có API conceptually như sau:

```java
public interface Trigger {
    Instant nextExecution(TriggerContext context);
}
```

Đây là phác thảo; dùng interface thật của Spring. `TriggerContext` có:

```java
Clock getClock();
Instant lastScheduledExecution();
Instant lastActualExecution();
Instant lastCompletion();
```

- `lastScheduledExecution`: mốc **dự kiến** của lần trước.
- `lastActualExecution`: lúc callback **thực sự bắt đầu**.
- `lastCompletion`: lúc callback **kết thúc**.
- `getClock`: clock của scheduler.

Ở lần đầu, các `Instant` lịch sử có thể `null`. Ví dụ Trigger chạy ngay lần đầu rồi sau đó chờ 20 giây tính từ lần hoàn tất:

```java
Trigger afterCompletion = ctx -> {
    Instant last = ctx.lastCompletion();
    return last == null
            ? ctx.getClock().instant()
            : last.plusSeconds(20);
};
```

Đây là đoạn minh họa đặt trong method có import Spring `Trigger` và `Instant`. Khi chỉ cần fixed-delay thông thường, dùng API `scheduleWithFixedDelay` gọn hơn.

Trong Spring 6.2, `CronTrigger` có cách tính lenient và fixed execution. Lenient có thể bỏ mốc cron bị lỡ khi task dài; fixed dựa trên scheduled time, có thể làm các lần tới chạy muộn để không bỏ mốc. **Không** được suy ra rằng một Trigger trong RAM tự biết phải phát lại mọi tick khi JVM đã chết qua giờ cron rồi khởi động lại.

## 6. Implementation quyết định thread và lifecycle

`ThreadPoolTaskScheduler` là implementation phổ biến bọc `ScheduledThreadPoolExecutor`; mặc định số scheduler threads là **1** và có thể thay bằng `setPoolSize(int)`. Theo Javadoc, **task chạy trên chính scheduler threads**, không tự tách worker. `ScheduledFuture` của một one-shot Runnable đại diện việc Runnable hoàn tất.

`ConcurrentTaskScheduler` bọc `ScheduledExecutorService` đã được tạo/cấp ở nơi khác. Nếu backend thuộc thư viện hoặc container, phải xác định rõ ai shutdown; adapter không cho phép một component tùy tiện đóng tài nguyên shared.

`DefaultManagedTaskScheduler` dùng managed scheduler của Jakarta EE khi container áp đặt quy tắc quản lý thread.

`SimpleAsyncTaskScheduler` từ Spring 6.1 hướng tới mô hình thread-per-task/virtual threads của JDK 21. Với fixed-delay, nó thực thi callback trên scheduler thread đơn; do đó không được suy diễn rằng tất cả task đều chạy trên virtual thread. Virtual threads không làm CPU, DB connection hoặc rate limit trở thành vô hạn.

**Thiết kế quan trọng:** nếu callback nặng/blocking kéo dài, tăng scheduler pool size hoặc, tốt hơn khi cần cô lập, chỉ dùng timer để dispatch sang một `TaskExecutor` riêng. Nếu có queue và backpressure, phải quản lý overload ở worker pool thay vì giữ scheduler thread chờ.

## 7. Java 17 chạy độc lập: kiểm chứng thời gian và cancellation

Ví dụ JDK minh họa fixed-rate/fixed-delay bằng các `Instant` cố định, sau đó dùng scheduler thật. Latch giúp kiểm tra hoàn thành mà không đoán thứ tự thread bằng `Thread.sleep`.

Lưu **`SchedulingSemanticsDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SchedulingSemanticsDemo {

    public static void main(String[] args) throws Exception {
        Instant firstStart =
                Instant.parse("2026-01-01T00:00:00Z");
        Instant firstCompletion = firstStart.plusSeconds(7);
        Duration interval = Duration.ofSeconds(5);

        System.out.println("plannedRate=" +
                firstStart.plus(interval));
        System.out.println("plannedDelay=" +
                firstCompletion.plus(interval));

        ScheduledExecutorService executor =
                Executors.newSingleThreadScheduledExecutor();

        try {
            AtomicInteger runs = new AtomicInteger();

            ScheduledFuture<?> once = executor.schedule(
                    runs::incrementAndGet,
                    10, TimeUnit.MILLISECONDS);

            once.get(5, TimeUnit.SECONDS);
            System.out.println("oneShotRuns=" + runs.get());
            System.out.println("oneShotDone=" + once.isDone());

            CountDownLatch ticks = new CountDownLatch(3);

            ScheduledFuture<?> repeated =
                    executor.scheduleWithFixedDelay(
                            ticks::countDown, 0, 10,
                            TimeUnit.MILLISECONDS);

            boolean reached = ticks.await(5, TimeUnit.SECONDS);
            repeated.cancel(false);

            System.out.println("atLeastThreeTicks=" + reached);
            System.out.println("periodicCancelled=" +
                    repeated.isCancelled());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac SchedulingSemanticsDemo.java
java SchedulingSemanticsDemo
```

**Stdout khi chạy hoàn tất bình thường:**

```text
plannedRate=2026-01-01T00:00:05Z
plannedDelay=2026-01-01T00:00:12Z
oneShotRuns=1
oneShotDone=true
atLeastThreeTicks=true
periodicCancelled=true
```

Mốc fixed-rate dự kiến thứ hai là `00:00:05Z`; mốc fixed-delay là `00:00:12Z` do completion 7 giây cộng delay 5 giây. `once.get()` đảm bảo one-shot đã xong trước khi in. Với periodic, chỉ khẳng định **ít nhất** ba tick vì tick tiếp có thể chen vào trước lúc cancel; không in số tick chính xác khi chưa kiểm soát race đó.

`ScheduledFuture.cancel(false)` ngăn các lần kích hoạt tương lai theo backend, **không** có nghĩa có thể hủy mọi thao tác I/O đã chạy.

## 8. Spring Boot hoàn chỉnh: dùng interface `TaskScheduler`

Ví dụ này dùng **Java 17+**, **Spring Boot 3.5.7** và Maven, chạy dạng CLI. Nó khai báo `ThreadPoolTaskScheduler` bean nhưng tra cứu bằng kiểu `TaskScheduler`, chạy one-shot theo `Instant` và fixed-delay theo `Duration`.

### 8.1. Cấu trúc

```text
task-scheduler-demo/
├── pom.xml
└── src/main/java/com/example/scheduler/
    ├── SchedulerConfiguration.java
    └── SchedulerDemoApplication.java
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
    <artifactId>task-scheduler-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 8.3. `src/main/java/com/example/scheduler/SchedulerConfiguration.java`

```java
package com.example.scheduler;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class SchedulerConfiguration {

    @Bean("jobScheduler")
    public ThreadPoolTaskScheduler jobScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("scheduled-demo-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
```

Bean được Spring quản lý vòng đời initialize/shutdown. `setPoolSize(1)` chỉ để dễ quan sát rằng callback chạy trên scheduler thread; không phải gợi ý pool size cho production.

### 8.4. `src/main/java/com/example/scheduler/SchedulerDemoApplication.java`

```java
package com.example.scheduler;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.scheduling.TaskScheduler;

@SpringBootApplication
public class SchedulerDemoApplication {

    public static void main(String[] args) throws Exception {
        SpringApplication app =
                new SpringApplication(SchedulerDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(
                Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            TaskScheduler scheduler =
                    context.getBean("jobScheduler", TaskScheduler.class);

            AtomicInteger runs = new AtomicInteger();
            AtomicBoolean onSchedulerThread = new AtomicBoolean();

            ScheduledFuture<?> once = scheduler.schedule(
                    () -> {
                        runs.incrementAndGet();
                        onSchedulerThread.set(
                                Thread.currentThread().getName()
                                        .startsWith("scheduled-demo-"));
                    },
                    scheduler.getClock().instant().plusMillis(10));

            once.get(5, TimeUnit.SECONDS);

            System.out.println("oneShotRuns=" + runs.get());
            System.out.println("schedulerThread=" +
                    onSchedulerThread.get());
            System.out.println("oneShotDone=" + once.isDone());

            CountDownLatch ticks = new CountDownLatch(3);
            ScheduledFuture<?> repeated =
                    scheduler.scheduleWithFixedDelay(
                            ticks::countDown,
                            Duration.ofMillis(10));

            boolean reached = ticks.await(5, TimeUnit.SECONDS);
            repeated.cancel(false);

            System.out.println("atLeastThreeTicks=" + reached);
            System.out.println("periodicCancelled=" +
                    repeated.isCancelled());
        }
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn -q spring-boot:run
```

**Các dòng `System.out` dự kiến khi chương trình hoàn tất bình thường:**

```text
oneShotRuns=1
schedulerThread=true
oneShotDone=true
atLeastThreeTicks=true
periodicCancelled=true
```

Ứng dụng tắt banner và root logging trong ví dụ; build tool có thể in thêm thông tin khác. Cách dùng `oneShot.get(timeout)` và latch giúp main không in trước khi các điều kiện kiểm thử được quan sát.

**Vì sao ví dụ không có `@EnableScheduling`?** Đây là cách dùng `TaskScheduler.schedule(...)` **programmatic**, không phải method có `@Scheduled`. Bật `@EnableScheduling` chỉ cần để Spring nhận diện và đăng ký các method `@Scheduled` từ bean.

## 9. `@Scheduled`, `@EnableScheduling` và `SchedulingConfigurer`

Dạng khai báo phổ biến:

```java
@Configuration
@EnableScheduling
public class ScheduleConfiguration {

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("cron-");
        return scheduler;
    }
}

@Component
class CachePoller {

    @Scheduled(fixedDelay = 5, timeUnit = TimeUnit.SECONDS)
    public void poll() {
        // Đồng bộ dữ liệu ngắn, có timeout thực.
    }

    @Scheduled(cron = "0 0/5 * * * *", zone = "Asia/Ho_Chi_Minh")
    public void refreshEveryFiveMinutes() {
        // Chạy theo lịch địa phương.
    }
}
```

Đây là **hai class minh họa**, cần imports Spring và `TimeUnit`; không phải tệp duy nhất có thể biên dịch mà không có project. `@EnableScheduling` bật xử lý annotation trong đúng application context. `@EnableAsync` phục vụ `@Async`, là cơ chế khác.

Spring Framework mặc định tìm một `TaskScheduler` bean duy nhất hoặc bean tên `"taskScheduler"`, sau đó xét `ScheduledExecutorService` và có thể fallback scheduler một thread; Spring Boot có auto-configuration riêng tùy phiên bản và classpath, vì vậy cần kiểm tra bean thực tế.

Khi có nhiều scheduler, chỉ định chính xác bằng `SchedulingConfigurer`:

```java
@Configuration
@EnableScheduling
class ExplicitSchedulerConfig implements SchedulingConfigurer {
    private final TaskScheduler chosen;

    ExplicitSchedulerConfig(
            @Qualifier("businessScheduler") TaskScheduler chosen) {
        this.chosen = chosen;
    }

    @Override
    public void configureTasks(ScheduledTaskRegistrar registrar) {
        registrar.setTaskScheduler(chosen);
    }
}
```

Đây là class minh họa cần imports tương ứng và bean `"businessScheduler"`. Không nhầm `SchedulingConfigurer` với `AsyncConfigurer`: cái sau chọn executor mặc định cho `@Async`, không phải scheduler của cron.

`@Scheduled` method thông thường không nhận tham số; đối tượng cần thiết được DI. Nếu một request muốn tạo reminder theo `jobId`/deadline động, dùng API programmatic hoặc durable job store thay vì tạo nhiều method `@Scheduled` khác nhau.

## 10. Tách scheduler callback khỏi business job dài

Vì `ThreadPoolTaskScheduler` chạy callback ngay trên scheduler threads, một tác vụ blocking dài sẽ giữ tài nguyên timer. Có thể để scheduler chỉ gửi tín hiệu rồi trả nhanh:

```text
TaskScheduler (canh giờ)
       |
       | tick đến hạn
       v
Runnable dispatch
       |
       | TaskExecutor.execute(...)
       v
TaskExecutor (bounded workers + queue)
       |
       v
Business job (DB / HTTP / CPU)
```

Pattern Spring:

```java
@Service
public class CleanupSchedule {
    private final TaskScheduler scheduler;
    private final TaskExecutor worker;

    public CleanupSchedule(
            @Qualifier("jobScheduler") TaskScheduler scheduler,
            @Qualifier("cleanupExecutor") TaskExecutor worker) {
        this.scheduler = scheduler;
        this.worker = worker;
    }

    public ScheduledFuture<?> start() {
        return scheduler.scheduleAtFixedRate(() -> {
            try {
                worker.execute(this::cleanup);
            } catch (TaskRejectedException ex) {
                recordRejectedTick(ex);
            }
        }, Duration.ofMinutes(1));
    }
}
```

Đây là **class minh họa**, cần imports và các method `cleanup`, `recordRejectedTick`; các bean scheduler/worker phải tồn tại. `start()` nên được gọi tại lifecycle phù hợp và handle được giữ để hủy, không gọi mỗi HTTP request.

**Không được quên:**

- Future của scheduler theo dõi **tick**, không tự biết business job ở worker xong hay chưa.
- Một tick mới có thể enqueue job mới khi job cũ còn chạy. Muốn cấm overlap, thêm guard/concurrency limit.
- `TaskExecutor` có thể từ chối tác vụ; `TaskRejectedException` phải được quan sát và xử lý.
- `CallerRunsPolicy` trên worker pool có thể buộc **scheduler thread** tự chạy job khi full, phá ý định offload.
- `@Transactional`/MDC/ThreadLocal không tự động đi theo mọi worker; cần ranh giới transaction và context propagation đúng.
- Các task ở RAM không tự được lưu để chạy sau restart.

Một single-flight guard đơn giản trong một JVM:

```java
private final AtomicBoolean running = new AtomicBoolean();

void onTick() {
    if (!running.compareAndSet(false, true)) {
        recordSkippedOverlap();
        return;
    }

    try {
        worker.execute(() -> {
            try {
                doBusinessWork();
            } finally {
                running.set(false);
            }
        });
    } catch (TaskRejectedException ex) {
        running.set(false);
        recordRejected(ex);
    }
}
```

Đây là đoạn thành viên minh họa, cần class có `worker`, `AtomicBoolean` và các method nghiệp vụ/metric. `running=true` tính cả job đã enqueue nhưng chưa chạy; cuối job luôn reset bằng `finally`. Guard chỉ bảo vệ **một instance**, không thay thế cluster lock.

## 11. Lỗi, cancellation và clock

Có **hai thời điểm lỗi**:

1. **Lỗi nhận lịch:** scheduler shutdown/quá tải, `schedule(...)` có thể ném `TaskRejectedException` ở caller.
2. **Lỗi khi thực thi:** Runnable đã được lên lịch rồi mới ném exception; cần error handler/metrics trong worker. Với JDK `ScheduledExecutorService`, một periodic task ném exception không xử lý sẽ không chạy các kỳ tiếp theo; Spring `ThreadPoolTaskScheduler` có `setErrorHandler(ErrorHandler)` và chính sách riêng, thường log/suppress lỗi cho repeating tasks.

Không giả định mọi implementation có cách xử lý lỗi giống hệt nhau. Test error handler theo Spring version và kiểu task. Đừng bắt mọi `Exception` rồi im lặng để lịch nhìn có vẻ “đang chạy”.

`ScheduledFuture.get()` của **periodic** không phải “lấy kết quả tick vừa rồi”, có thể chờ mãi; dùng metrics/callback để quan sát từng kỳ. `cancel(false)` dừng các lần scheduled tiếp theo nhưng không tự dừng một JDBC query/HTTP request trong worker khác.

Về clock: `Instant` là một mốc tuyệt đối, `Duration` là khoảng trôi qua, `ZoneId` dùng cho giờ địa phương. Một cron theo 09:00 ở vùng có DST cần xét ngày giờ bị lặp hoặc bị bỏ. Mốc dự kiến không phải cam kết hard real-time; GC pause, CPU throttling và scheduler thread bận đều gây scheduling lag.

## 12. Nhiều replica và tính bền vững

Giả sử có ba Spring instances cùng bật:

```java
@Scheduled(cron = "0 0 9 * * *", zone = "Asia/Ho_Chi_Minh")
public void reconcile() {
    // Nghiệp vụ đối soát.
}
```

Đây là method minh họa cần nằm trong bean có `@EnableScheduling` được bật. Đến 09:00, mỗi instance có thể tự kích hoạt, tức **có thể có ba lần thực thi**. `TaskScheduler` không tự có distributed lock hoặc leader election.

Khi chỉ muốn một job toàn cụm, cân nhắc database lease/lock, leader election, broker/queue hoặc Quartz có cluster JobStore. Vẫn cần idempotency và xử lý crash window: worker có thể đã làm side effect rồi chết trước khi ghi `SUCCEEDED`.

Một local `ThreadPoolTaskScheduler` không persist lịch. Nếu server tắt vào giờ cron rồi bật lại 10 phút sau, nó không tự biết chính xác những job nào cần được chạy bù. Nếu không được bỏ việc, cần durable job ID, due time, trạng thái, retry và reconciliation; có thể dùng DB/job queue, transactional outbox hoặc hệ thống scheduler chuyên dụng với JobStore.

## 13. Chọn giải pháp theo tình huống

| Nhu cầu | Gợi ý | Điều cần kiểm tra |
| --- | --- | --- |
| Một lần sau 30 giây, chấp nhận mất khi restart | `schedule(task, Instant)` | Cancel/lifecycle |
| Poll nhẹ, nghỉ sau callback | Fixed-delay | Execution time và scheduler lag |
| Thu thập metric theo nhịp | Fixed-rate | Bị trễ dưới tải |
| Chạy 09:00 mỗi ngày | Cron + zone | Timezone, DST, downtime |
| Callback có blocking I/O dài | Dispatch sang TaskExecutor | Queue, overlap, rejection |
| Container quản lý thread | `DefaultManagedTaskScheduler` | Ownership của container |
| Đã có JDK scheduled pool | `ConcurrentTaskScheduler` | Shutdown backend đúng nơi |
| Cần một job trên toàn cụm | Distributed coordination | Lease/fencing, idempotency |
| Job phải survive restart | Durable job store/Quartz thích hợp | Recovery, audit, retry |
| Muốn thay backend không sửa domain | Inject `TaskScheduler` | Tránh API implementation-specific |

## 14. Kiểm thử và quan sát

**Unit test** policy: dùng `Instant.parse(...)`, `Duration` cố định; với custom `Trigger`, mock `TriggerContext` và clock để kiểm tra `nextExecution`. Test trường hợp lần đầu thiếu lịch sử, khi task trễ, khi trigger kết thúc (`null`), timezone và DST.

**Integration test** scheduler: dùng `CountDownLatch`, `ScheduledFuture.get(timeout)` cho one-shot; với periodic, đợi số tick *tối thiểu* rồi cancel. Tránh `Thread.sleep` và assertion đòi đúng số tick tuyệt đối khi cancellation cạnh tranh với callback.

**Failure test:** giữ scheduler thread bằng latch để thấy lịch khác trễ; simulate worker queue full, xem rejection; cho callback ném lỗi và quan sát những kỳ sau; đóng context; test nhiều replica/distributed lock nếu nghiệp vụ yêu cầu.

**Production metrics:** scheduled/actual/completion time, scheduling lag p95/p99, callback duration, error count, rejected ticks, overlap skipped, worker active/queue depth, DB connection wait, JVM CPU/GC và backlog durable. Một scheduler không báo exception chưa có nghĩa nghiệp vụ đang thành công.

## 15. Những lỗi phổ biến

| Sai lầm | Hậu quả | Sửa |
| --- | --- | --- |
| Nghĩ `TaskScheduler` và `TaskExecutor` cùng một API | Không phân biệt thời điểm và worker | Chọn abstraction đúng |
| Nghĩ `ThreadPoolTaskScheduler` tự có worker pool khác | Blocking job giữ scheduler threads | Offload khi cần |
| Pool size 1 với callback HTTP 60 giây | Các lịch khác bị trễ | Timeout, sizing, dispatch ngắn |
| Fixed-delay callback chỉ enqueue rồi return | Business jobs có thể overlap | Guard/concurrency limit |
| Fixed-rate nghĩa là không bao giờ trễ | GC/CPU/worker bận gây lag | Đo độ trễ |
| Cron Spring chỉ có năm trường | Biểu thức sai | Dùng sáu trường gồm giây |
| Không chỉ định timezone | Sai giờ nghiệp vụ khi đổi môi trường | Zone rõ |
| `schedule(Trigger)` luôn trả Future | NPE nếu trigger không có next | Kiểm tra null |
| Gọi periodic `future.get()` trong controller | Chặn vô hạn | Theo dõi metric/latch |
| Cancel scheduled Future rồi nghĩ job offload dừng | Job vẫn chạy ở worker | Hủy/timeout riêng |
| Tạo scheduler mỗi request | Trùng lịch, rò thread | Bean singleton/lifecycle |
| Quên `@EnableScheduling` với `@Scheduled` | Annotation không được đăng ký | Bật đúng context |
| Một lịch trên nhiều replicas, nghĩ chạy một lần | Side effect bị lặp | Cluster coordination |
| Dùng scheduler RAM cho job không được mất | Restart bỏ lỡ | Durable job store |
| Nuốt lỗi trong callback | Không thấy nghiệp vụ thất bại | ErrorHandler/metrics |
| Worker dùng `CallerRunsPolicy` | Scheduler thread chạy job dài | Rejection policy phù hợp |

## 16. Tự kiểm tra

**1.** `TaskScheduler` khác `TaskExecutor` thế nào?  
**Đáp:** TaskScheduler quyết định **khi nào** chạy qua `Instant`, `Duration`, `Trigger`. TaskExecutor cung cấp cơ chế giao task để thực thi.

**2.** `ThreadPoolTaskScheduler` có luôn tách timer và worker thread không?  
**Đáp:** Không. Callback chạy trên scheduler threads.

**3.** Fixed-delay 5 giây, task mất 7 giây. Lần tiếp theo sớm nhất khoảng khi nào?  
**Đáp:** Khoảng 12 giây sau lúc bắt đầu lần đầu, chưa kể trì hoãn hạ tầng.

**4.** Fixed-rate 5 giây, task đầu mất 7 giây. Mốc dự kiến lần hai?  
**Đáp:** Sau 5 giây, nhưng task thực tế sẽ trễ khi worker chưa rảnh.

**5.** Vì sao dùng `scheduler.getClock()`?  
**Đáp:** Để tính due time theo clock scheduler và dễ test.

**6.** `"0 0/5 * * * *"` trong Spring cron có nghĩa gì?  
**Đáp:** Mỗi năm phút tại giây 0, theo timezone được chọn.

**7.** `schedule(Runnable, Trigger)` có thể trả null không?  
**Đáp:** Có, khi trigger không còn lần chạy tiếp.

**8.** Fixed-delay có ngăn hai business jobs overlap nếu callback chỉ enqueue sang pool khác?  
**Đáp:** Không, vì callback đã hoàn thành trước business job.

**9.** Có ba replicas cùng `@Scheduled`, có chắc toàn cụm chỉ chạy một job không?  
**Đáp:** Không. Mỗi replica có lịch riêng; cần coordination/idempotency.

**10.** `cancel(false)` có dừng HTTP call đang chạy không?  
**Đáp:** Không tự động.

**11.** Có cần `@EnableScheduling` để gọi trực tiếp `TaskScheduler.schedule(...)`?  
**Đáp:** Không, chỉ cần cho `@Scheduled` annotation.

**12.** Công việc không được bỏ lỡ khi restart, chỉ dùng local TaskScheduler đủ không?  
**Đáp:** Không. Cần persistence và recovery.

## 17. Ghi nhớ và tài liệu chính thức

`TaskScheduler` **tách cách diễn đạt lịch** khỏi backend cụ thể. Nhưng backend vẫn quyết định thread và giới hạn thực tế. Muốn tách scheduler thread khỏi business worker, phải dispatch sang một executor riêng và xử lý overlap/rejection có chủ đích.

- Một lần: `schedule(task, Instant)`.
- Theo nhịp: `scheduleAtFixedRate(task, Duration)`.
- Nghỉ sau callback: `scheduleWithFixedDelay(task, Duration)`.
- Theo chính sách: `schedule(task, Trigger)` với cron hoặc trigger tùy chỉnh.
- Kiểm soát: `ScheduledFuture`, clock, cancel, error handler.
- Production: latency, timezone, cluster coordination, durability, idempotency.

**Tài liệu chính thức:**

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html).
- [Spring Framework 6.2 — `TaskScheduler`](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/TaskScheduler.html).
- [Spring Framework 6.2 — `ThreadPoolTaskScheduler`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html).
- [Spring Framework 6.2 — `SchedulingConfigurer`](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/annotation/SchedulingConfigurer.html).
- [Spring Framework 6.2 — `CronTrigger`](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/support/CronTrigger.html).
- [Java SE 17 — `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html).
- [Java SE 17 — `ScheduledFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html).