# Sử dụng `TaskExecutor` hoặc `TaskScheduler` do Spring quản lý — Spring Boot 3.3

## 1. Mục tiêu và bối cảnh

Một ứng dụng Spring Boot không chỉ làm việc trong thread HTTP request. Nó có thể cần đồng bộ dữ liệu, gửi thông báo, xử lý tệp, tính toán nền, kiểm tra sức khỏe định kỳ hoặc chạy báo cáo lúc 09:00. Nếu mỗi service tự tạo `new Thread(...)` hoặc `Executors.newFixedThreadPool(...)`, việc quản lý tài nguyên trở nên khó khăn: thread pool không được đóng đúng lúc, task bị mất khi shutdown, số thread tăng thiếu kiểm soát, exception không được theo dõi và lịch chạy không liên kết với lifecycle của Spring.

Spring Framework có hai abstraction giải quyết đúng hai bài toán:

- **`TaskExecutor`**: giao một công việc để thực thi; phù hợp với xử lý bất đồng bộ theo yêu cầu.
- **`TaskScheduler`**: đăng ký thời điểm hoặc chu kỳ thực thi; phù hợp với tác vụ one-shot, fixed rate, fixed delay và cron.

Khi khai báo executor/scheduler dưới dạng **Spring beans**, container quản lý quá trình tạo, dependency injection, initialization, destruction và có thể phối hợp với lifecycle. Spring Boot 3.3 còn tự cấu hình executor/scheduler mặc định khi thích hợp. Các annotation `@Async` và `@Scheduled` cung cấp cách sử dụng ở mức khai báo.

Sau bài này, bạn cần làm được:

1. Phân biệt **giao công việc** với **công việc đã hoàn tất**, **thực thi ngay** với **thực thi theo lịch**.
2. Khai báo `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` là các Spring beans có giới hạn hợp lý.
3. Dùng `TaskExecutor.execute`, `@Async`, `TaskScheduler.schedule`, `@Scheduled` và `ScheduledFuture` đúng ngữ nghĩa.
4. Hiểu `@EnableAsync`, `@EnableScheduling`, việc chọn bean theo tên và self-invocation của Spring AOP.
5. Xử lý timeout, cancellation, task rejection, lỗi bất đồng bộ và shutdown.
6. Chạy ví dụ Java 21 + Spring Boot 3.3.13, kiểm tra bằng JUnit, giải thích vì sao `ApplicationReadyEvent` không tự đợi background tasks.
7. Quyết định khi nào nên dùng scheduler in-memory và khi nào cần durable queue hoặc job scheduler phân tán.

## 2. So sánh TaskExecutor với TaskScheduler

| Tiêu chí | `TaskExecutor` | `TaskScheduler` |
| --- | --- | --- |
| Mục đích | Thực thi `Runnable` được giao | Đăng ký công việc chạy tại thời điểm hay theo chu kỳ |
| API cơ bản | `execute(Runnable)` | `schedule(Runnable, Instant)` |
| Kết quả/handle | `AsyncTaskExecutor.submit(...)` có `Future` | `ScheduledFuture<?>` để hủy/theo dõi |
| Annotation thường đi kèm | `@Async` | `@Scheduled` |
| Hạ tầng bật annotation | `@EnableAsync` | `@EnableScheduling` |
| Implementation phổ biến | `ThreadPoolTaskExecutor` | `ThreadPoolTaskScheduler` |
| Rủi ro | Pool/queue đầy, lỗi không được quan sát | Job chạy trễ, chồng tải, hẹn giờ sai timezone |
| Khi dừng context | Xử lý các tasks trong queue/running theo chính sách shutdown | Ngừng đăng ký, cancel/drain các công việc theo lifecycle |

**Lưu ý:** `TaskExecutor` không mặc nhiên là một thread pool: interface này là abstraction. Một implementation có thể đồng bộ, tạo thread cho mỗi task hoặc dùng một pool. `TaskScheduler` cũng ẩn implementation scheduling bên dưới.

### 2.1. Luồng xử lý

```text
Service / Controller / ApplicationRunner
          |
          +-- executor.execute(runnable)
          |       |
          |       +-- queue / worker thread
          |              +-- chạy
          |              +-- thành công hoặc lỗi
          |
          +-- scheduler.schedule(runnable, when)
                  |
                  +-- hẹn thời điểm
                  +-- đến thời điểm, worker chạy
                  +-- hoàn thành hoặc scheduling tiếp
```

Lời gọi `execute` hoặc `schedule` **không phải** tín hiệu business task đã hoàn thành. Với executor bất đồng bộ, caller có thể đi tiếp khi task vẫn nằm trong queue. Với scheduler, task còn có thể chưa tới thời điểm chạy.

Để **bảo đảm đã xong**, cần `Future`/`CompletableFuture`, latch, callback hoặc một job-state bền vững. Để **bảo đảm thứ tự nghiệp vụ**, còn cần nêu rõ task B phụ thuộc task A, không chỉ dựa vào thread names hay thứ tự log tình cờ.

### 2.2. TaskExecutor và Java ExecutorService

`TaskExecutor` của Spring tương tự `java.util.concurrent.Executor` ở phương thức `execute(Runnable)`, nhưng được tích hợp dependency injection và cách cấu hình/lifecycle của Spring.

`AsyncTaskExecutor` hỗ trợ việc submit và nhận handle. `ThreadPoolTaskExecutor` triển khai các hợp đồng này bằng thread pool có thể cấu hình.

Không phải tất cả TaskExecutor đều có `shutdown()`, `submit()` hoặc khả năng chỉnh queue; đây là tính năng của từng interface/implementation. Khi viết một service chỉ cần chạy fire-and-forget, có thể phụ thuộc interface `TaskExecutor`. Khi cần `Future`, phụ thuộc `AsyncTaskExecutor` hoặc một abstraction nghiệp vụ có trả future.

## 3. Tại sao phải để Spring quản lý?

Một anti-pattern thường gặp:

```java
@Service
class UnsafeNotificationService {
    private final ExecutorService pool = Executors.newFixedThreadPool(8);

    void submit(String id) {
        pool.submit(() -> send(id));
    }

    private void send(String id) {
        // Một cuộc gọi I/O giả định.
    }
}
```

**Đây là đoạn minh họa, không phải chương trình độc lập**: thiếu imports, cũng chưa có phương thức dừng pool. Nếu service không shutdown pool, ứng dụng có thể giữ non-daemon threads sau khi context đã đóng. Nếu mỗi service tạo một pool riêng, tài nguyên càng khó theo dõi.

Thiết kế tốt hơn:

```java
@Service
class NotificationService {
    private final TaskExecutor notificationExecutor;

    NotificationService(
            @Qualifier("notificationExecutor") TaskExecutor notificationExecutor) {
        this.notificationExecutor = notificationExecutor;
    }

    void submit(String id) {
        notificationExecutor.execute(() -> send(id));
    }

    private void send(String id) {
        // Business task.
    }
}
```

**Đây là minh họa DI**, cần import `@Service`, `@Qualifier`, `TaskExecutor` và định nghĩa bean `notificationExecutor`. Điểm thay đổi: component chỉ gửi việc; cấu hình pool và shutdown ở một nơi.

Lợi ích:

- Spring quản lý initialization/destroy của executor implementation tương ứng.
- Pool có tên và giới hạn được tái sử dụng cho nhóm workload thích hợp.
- Có thể tiêm một implementation khác trong test.
- Có thể đặt thread-name prefix, metrics, rejection policy, tracing phù hợp.
- Ngừng nhận công việc mới và drain/cancel khi context đóng có thể được điều phối ở cấp ứng dụng.

**Giới hạn:** pool được Spring quản lý vẫn là **in-memory execution**. Nếu JVM crash trước khi task hoàn thành, Spring không tự lưu task xuống ổ cứng hay tự replay sau restart. Tác vụ nghiệp vụ quan trọng cần durable queue, transaction/outbox hoặc job store.

## 4. Spring Boot 3.3 auto-configuration

### 4.1. Executor mặc định

Trong Spring Boot 3.3.13, nếu context không có `Executor` bean tùy biến, Boot có thể auto-configure một `AsyncTaskExecutor`. Trên Java 21:

- Khi không bật virtual threads, thường là `ThreadPoolTaskExecutor`.
- Nếu `spring.threads.virtual.enabled=true`, có thể là `SimpleAsyncTaskExecutor` dùng virtual threads.

Trong chế độ platform threads, auto-configured `ThreadPoolTaskExecutor` có 8 core threads theo mặc định của Boot 3.3; có thể thay đổi qua cấu hình:

```properties
spring.task.execution.thread-name-prefix=app-exec-
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=10s
```

Các properties trên mô tả **auto-configured executor**. Chúng không tự chỉnh những bean custom mà ứng dụng tự tạo bằng `new ThreadPoolTaskExecutor()`.

Khi ứng dụng đăng ký `Executor` bean riêng, auto-configuration có thể back off. Nếu dùng Spring MVC/WebFlux cho xử lý request bất đồng bộ, hãy chú ý yêu cầu về `AsyncTaskExecutor` và tên bean **`applicationTaskExecutor`**; đừng thay đổi executor mặc định mà vô tình ảnh hưởng các integration. Khi có nhiều executor, `@Async` không qualifier có thể chọn không như mong muốn; dùng `@Async("beanName")` hoặc cấu hình `AsyncConfigurer` rõ ràng.

### 4.2. Scheduler mặc định

Khi scheduling infrastructure cần scheduler (ví dụ `@EnableScheduling`), Spring Boot có thể auto-configure:

- `ThreadPoolTaskScheduler` với một thread theo mặc định.
- `SimpleAsyncTaskScheduler` dùng virtual threads trong cấu hình Java 21 và `spring.threads.virtual.enabled=true`; khi đó pool-size properties của scheduler truyền thống không áp dụng theo cách cũ.

Ví dụ khi dùng pool-based auto-configured scheduler:

```properties
spring.task.scheduling.thread-name-prefix=sched-
spring.task.scheduling.pool.size=2
```

Một scheduler một thread có thể làm các công việc khác trễ lịch khi có task chạy lâu. Nhưng tăng threads cũng không thay thế logic hạn chế concurrency, tránh overlap và kiểm soát downstream capacity.

### 4.3. Khi nào nên tự tạo bean?

Dùng auto-config khi nhu cầu đơn giản và cấu hình qua properties là đủ.

Tạo custom beans khi cần:

- Tách nhóm tác vụ I/O và CPU để tránh starvation.
- Dùng pool/queue giới hạn có chính sách backpressure riêng.
- Dùng nhiều schedulers khác nhau cho tác vụ dài/ngắn.
- Đặt executor rõ ràng cho `@Async("ioTaskExecutor")`.
- Đặt scheduler rõ ràng cho `@Scheduled(scheduler="taskScheduler")` ở Spring Framework 6.1.
- Cấu hình shutdown, metrics, task rejection hoặc thread-name prefix riêng.

**Quy tắc:** custom `@Bean` thì custom luôn trách nhiệm cấu hình; không kỳ vọng mọi property của Boot tự động apply vào nó.

## 5. ThreadPoolTaskExecutor: cấu hình thực dụng

Cấu hình mẫu:

```java
@Bean("ioTaskExecutor")
ThreadPoolTaskExecutor ioTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setThreadNamePrefix("io-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
```

**Đoạn minh họa trong class `@Configuration`**, cần imports phù hợp; bản đầy đủ ở mục 7.

Ý nghĩa:

- **corePoolSize**: số worker core.
- **maxPoolSize**: trần số worker.
- **queueCapacity**: giới hạn số tác vụ đang đợi.
- **threadNamePrefix**: dễ nhận diện trong logs/thread dump.
- **waitForTasksToCompleteOnShutdown**: yêu cầu shutdown chờ xử lý tasks đã nhận theo policy implementation.
- **awaitTerminationSeconds**: thời hạn chờ termination được cấu hình cho executor.

ThreadPoolExecutor thường tăng tới core threads, sau đó xếp queue và chỉ cân nhắc tăng tới max khi queue đã đầy. Do vậy việc tăng riêng `maxPoolSize` nhưng giữ queue quá lớn **không bảo đảm** số threads thực tế tăng.

**Cảnh báo lifecycle:** `setWaitForTasksToCompleteOnShutdown(true)` cần được thiết kế cùng shutdown của những beans mà task phụ thuộc. Pool có thể tiếp tục xử lý task trong lúc context bắt đầu destroy data source/HTTP clients. Với service production, cần điều phối dừng nhận job, drain với deadline và giữ dependencies sống đủ lâu (ví dụ sử dụng `SmartLifecycle`), không coi một flag là bảo đảm shutdown an toàn.

### 5.1. Queue đầy và task rejection

Nếu pool và queue đều hết capacity, `execute`/`submit` có thể ném `TaskRejectedException` theo implementation Spring.

Không được nuốt exception rồi báo task đã nhận. Phương án:

- Từ chối request phù hợp, thông báo retry có backoff.
- Gửi job sang durable queue nếu không được phép mất.
- Drop có kiểm soát nếu đó là best-effort task, kèm metric.
- Với task startup thiết yếu, cho startup thất bại rõ ràng khi pool không nhận được việc.

Tránh retry vô hạn trong request thread hoặc tạo một thread mới mỗi lần queue đầy: đây là cách khuếch đại overload.

### 5.2. Chọn pool size theo workload

- CPU-bound: concurrency thường không nên tăng quá xa số CPU cores.
- I/O-bound: có thể dùng nhiều concurrency hơn nhưng phải xét connection pools, timeout, rate limit và memory.
- Scheduler: callback càng dài càng chiếm scheduler threads, nên cân nhắc tách job execution khỏi scheduling.
- Tác vụ có deadline: không nên dùng chung pool với tác vụ block vô hạn.

Không có một `core=8, max=64` phù hợp cho mọi ứng dụng. Chọn bằng load tests, metrics và khả năng downstream.

## 6. ThreadPoolTaskScheduler: cấu hình và hợp đồng

Cấu hình mẫu:

```java
@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("scheduled-");
    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.setAwaitTerminationSeconds(10);
    return scheduler;
}
```

`ThreadPoolTaskScheduler` triển khai lịch chạy qua cơ chế `ScheduledExecutorService` và tích hợp Spring lifecycle. Bean tên **`taskScheduler`** là tên convention dễ được scheduling infrastructure chọn. Khi có nhiều scheduler, phải xác định rõ scheduler của từng job.

### 6.1. TaskScheduler API cơ bản

| API | Ý nghĩa |
| --- | --- |
| `schedule(Runnable, Instant)` | Hẹn một lần tại thời điểm chỉ định |
| `schedule(Runnable, Trigger)` | Đăng ký theo trigger, ví dụ cron |
| `scheduleAtFixedRate(Runnable, Duration)` | Lặp theo fixed rate |
| `scheduleWithFixedDelay(Runnable, Duration)` | Lặp theo fixed delay |
| `ScheduledFuture.cancel(false)` | Yêu cầu hủy lần tiếp theo mà không interrupt task đang chạy |

`TaskScheduler` không tự tạo persistent job. Các registration tồn tại trong quá trình sống của context/JVM. Muốn sống qua deploy/restart, cần lưu định nghĩa job tại nguồn bền vững và tái đăng ký, hoặc dùng Quartz/job scheduler chuyên dụng.

### 6.2. Fixed rate, fixed delay và cron

**Fixed rate**: tính thời điểm thực thi gần theo nhịp bắt đầu dự kiến.

```java
@Scheduled(fixedRate = 10_000, initialDelay = 1_000)
public void refreshSnapshot() {
    // Công việc nhẹ chạy theo chu kỳ.
}
```

**Fixed delay**: đợi đủ khoảng thời gian từ lúc lần trước **kết thúc** đến lần kế tiếp.

```java
@Scheduled(fixedDelay = 10_000, initialDelay = 1_000)
public void pollRemoteService() {
    // Có thể mất thời gian khác nhau mỗi lần.
}
```

**Cron**: chạy theo lịch giờ/ngày.

```java
@Scheduled(
        cron = "0 0 9 * * MON-FRI",
        zone = "Asia/Ho_Chi_Minh")
public void sendWorkdayReport() {
    // 09:00 thứ Hai đến thứ Sáu theo múi giờ đã chọn.
}
```

**Các phương thức trên là ví dụ minh họa trong một Spring bean**, không nằm trong project chính ở mục 7. Phải có `@EnableScheduling`, import `org.springframework.scheduling.annotation.Scheduled` và một bean được scan/đăng ký.

Spring cron có **6 trường (bao gồm giây)**. Đừng sao chép nguyên mẫu cron 5 trường của công cụ khác. Với lịch nghiệp vụ theo địa phương, chỉ định zone rõ ràng; nếu zone có DST, phải xét thời điểm bị bỏ qua hoặc lặp lại.

**Không suy luận fixed rate luôn chạy chồng nhau:** scheduler thực tế, số threads và cách trigger đăng ký quyết định khi nào một execution có thể được bắt đầu. Một job chậm có thể gây trễ, backlog hoặc những mốc chạy không đúng kỳ vọng; cần kiểm thử đúng implementation của bạn.

### 6.3. Chỉ định scheduler cho @Scheduled trong Spring 6.1

```java
@Scheduled(
        fixedDelay = 15_000,
        scheduler = "taskScheduler")
public void cleanup() {
    // ...
}
```

Attribute `scheduler` có trong Spring Framework 6.1 để chỉ rõ tên/qualifier scheduler. Khi không chỉ định và có nhiều scheduler beans, việc lựa chọn có thể không đúng ý hoặc gây ambiguity. Với nhiều nhóm công việc, nên dùng qualifier tường minh.

## 7. Ví dụ hoàn chỉnh chạy được — Java 21 + Spring Boot 3.3.13

Demo **non-web** không cần database hoặc broker, minh họa một executor và scheduler đều là Spring beans. Một `ApplicationRunner` gọi `@Async` trên **bean khác**, chờ `CompletableFuture` với timeout, sau đó hẹn một one-shot task và chờ `CountDownLatch`. Nhờ chờ completion, chương trình có output xác định.

### 7.1. Cấu trúc dự án

```text
managed-tasks-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/tasks/
    │   ├── ManagedTasksApplication.java
    │   ├── TaskConfiguration.java
    │   ├── ManagedWorker.java
    │   └── DemoRunner.java
    └── test/java/com/example/tasks/
        └── ManagedTasksIntegrationTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>managed-tasks-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 7.3. Application main

Tệp `src/main/java/com/example/tasks/ManagedTasksApplication.java`:

```java
package com.example.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ManagedTasksApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManagedTasksApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner đã hoàn tất trước khi SpringApplication.run trả về.
        }
    }
}
```

`@SpringBootApplication` được đặt trong package gốc để scan các classes. `WebApplicationType.NONE` ngăn app mở HTTP server. Context được đóng bằng `try-with-resources` để Spring quản lý cleanup.

### 7.4. Cấu hình managed beans

Tệp `src/main/java/com/example/tasks/TaskConfiguration.java`:

```java
package com.example.tasks;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@EnableAsync
@EnableScheduling
public class TaskConfiguration {

    @Bean("ioTaskExecutor")
    public ThreadPoolTaskExecutor ioTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("io-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

Spring quản lý initialization/destroy của hai beans này. Không cần gọi `executor.initialize()` hoặc `scheduler.initialize()` thủ công trong `@Bean` factory methods. `@EnableAsync` kích hoạt Spring AOP async; `@EnableScheduling` kích hoạt xử lý `@Scheduled` methods nếu có.

### 7.5. Worker dùng @Async và trả kết quả

Tệp `src/main/java/com/example/tasks/ManagedWorker.java`:

```java
package com.example.tasks;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ManagedWorker {

    @Async("ioTaskExecutor")
    public CompletableFuture<String> normalize(String text) {
        String value = text.toUpperCase(Locale.ROOT);
        return CompletableFuture.completedFuture(value);
    }
}
```

Do method được gọi **qua Spring bean proxy**, đoạn tính toán sẽ chạy trong pool `ioTaskExecutor`. Return type `CompletableFuture` giúp caller quan sát lỗi và completion. Trong method đã gắn `@Async`, không cần bọc tiếp `CompletableFuture.supplyAsync` rồi vô tình chuyển sang một executor khác.

### 7.6. Runner gọi executor và scheduler

Tệp `src/main/java/com/example/tasks/DemoRunner.java`:

```java
package com.example.tasks;

import java.time.Instant;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;

@Component
public class DemoRunner implements ApplicationRunner {

    private final ManagedWorker worker;
    private final ThreadPoolTaskScheduler scheduler;

    public DemoRunner(
            ManagedWorker worker,
            @Qualifier("taskScheduler") ThreadPoolTaskScheduler scheduler) {
        this.worker = worker;
        this.scheduler = scheduler;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        System.out.println("RUNNER begin");

        CompletableFuture<String> work = worker.normalize("spring boot");
        String result = work.get(5, TimeUnit.SECONDS);
        System.out.println("ASYNC result=" + result);

        CountDownLatch completed = new CountDownLatch(1);
        ScheduledFuture<?> handle = scheduler.schedule(
                completed::countDown,
                Instant.now().plusMillis(100));

        if (handle == null) {
            throw new IllegalStateException("Scheduler rejected task");
        }
        if (!completed.await(5, TimeUnit.SECONDS)) {
            handle.cancel(false);
            throw new IllegalStateException("Scheduled task timed out");
        }

        System.out.println("SCHEDULE one-shot done");
        System.out.println("RUNNER done");
    }
}
```

Diễn giải:

1. Boot gọi `ApplicationRunner.run` sau khi context refresh.
2. Caller từ runner đến `ManagedWorker.normalize` đi qua Spring proxy nên `@Async("ioTaskExecutor")` có hiệu lực.
3. `work.get(5, TimeUnit.SECONDS)` chờ task async hoàn tất; nếu thất bại/timeout, runner ném lỗi và startup không đi tới nhánh ready thành công.
4. `scheduler.schedule(Runnable, Instant)` đăng ký one-shot runnable.
5. `CountDownLatch` được giảm ngay khi runnable thực thi; runner chờ tối đa 5 giây rồi mới in dòng hoàn tất.
6. Sau khi runner trả về bình thường, Boot mới tiếp tục đến `ApplicationReadyEvent`.

Trong demo, scheduled task chỉ làm `countDown()` nên latch phản ánh completion chính xác. Với task thật, signal phải được phát **sau công việc thiết yếu**; nếu task có exception, cần kênh truyền lỗi về caller, ví dụ `CompletableFuture`/`AtomicReference<Throwable>`, thay vì chỉ gọi latch trong finally và coi mọi kết quả là thành công.

### 7.7. Build và chạy

Cần JDK 21, Maven và có thể tải dependencies:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/managed-tasks-demo-0.0.1-SNAPSHOT.jar
```

Bốn dòng do **chương trình chủ động in** trong lần chạy JAR là:

```text
RUNNER begin
ASYNC result=SPRING BOOT
SCHEDULE one-shot done
RUNNER done
```

Các log, banner và timestamps từ Spring Boot có thể xen giữa; khối trên **không phải toàn bộ stdout**.

Thứ tự được bảo đảm bằng `Future.get` và `CountDownLatch.await`, không dựa vào `Thread.sleep` hoặc scheduler ngẫu nhiên. Nếu runner chỉ submit jobs mà không chờ, `ApplicationReadyEvent` có thể được phát trong khi các công việc vẫn chưa hoàn thành.

### 7.8. Lưu ý về shutdown trong demo

Sau khi `SpringApplication.run` trả về, `try-with-resources` đóng context. Trong một ứng dụng web/worker chạy lâu, context thông thường tồn tại cho đến khi nhận tín hiệu shutdown, và pool vẫn dùng để phục vụ tasks mới. Demo đóng ngay có chủ đích vì hai công việc minh họa đã được đợi hoàn tất.

## 8. Annotation @Async và self-invocation

### 8.1. Cách đúng

```java
@Service
class ReportFacade {
    private final ManagedWorker worker;

    ReportFacade(ManagedWorker worker) {
        this.worker = worker;
    }

    CompletableFuture<String> start(String text) {
        return worker.normalize(text);
    }
}
```

Đây là **mẫu bổ sung**, cần imports nếu dùng riêng. `ReportFacade` và `ManagedWorker` là hai Spring beans, do đó lời gọi giữa chúng đi qua proxy được Spring tạo cho `@Async`.

### 8.2. Self-invocation khiến @Async có vẻ không hoạt động

```java
@Service
class IncorrectService {

    public void submit() {
        this.processAsync(); // Lời gọi nội bộ, có thể bỏ qua proxy.
    }

    @Async("ioTaskExecutor")
    public void processAsync() {
        // ...
    }
}
```

Đây là **anti-pattern minh họa**. Ở proxy mode mặc định, lời gọi `this.processAsync()` trong cùng instance không đi qua async proxy, nên method có thể chạy đồng bộ trên thread caller. Sửa bằng cách chuyển method async sang một bean khác và inject bean đó; không khuyến nghị tự inject chính bean hay dùng `AopContext` để chữa thiết kế thiếu rõ ràng.

### 8.3. @Async void và kết quả

- `@Async void`: caller không nhận future để biết success/failure. Lỗi có thể được đưa tới `AsyncUncaughtExceptionHandler`.
- `@Async CompletableFuture<T>`: phù hợp khi cần chờ kết quả, ghép workflow hoặc xử lý exception.
- `@Async` không tự tạo giao dịch xuyên thread, không tự retry task và không tự đảm bảo lưu job qua restart.
- Với nhiều executors, dùng `@Async("beanName")` thay vì trông chờ lựa chọn mặc định.

## 9. TaskScheduler: one-shot, recurring và cancel

### 9.1. One-shot tại một Instant

```java
ScheduledFuture<?> reminder = taskScheduler.schedule(
        () -> sendReminder(reminderId),
        Instant.now().plusSeconds(60));
```

Đây là **đoạn minh họa**, cần bean `TaskScheduler`, biến `reminderId` và method `sendReminder`. Với lịch một lần, `Instant` biểu diễn một mốc thời gian tuyệt đối; task có thể chạy trễ nếu scheduler bận hoặc app chưa chạy tới mốc.

### 9.2. Fixed rate/fixed delay qua code

```java
ScheduledFuture<?> metrics = taskScheduler.scheduleAtFixedRate(
        this::reportMetrics,
        Duration.ofSeconds(30));

ScheduledFuture<?> polling = taskScheduler.scheduleWithFixedDelay(
        this::pollUpdates,
        Duration.ofSeconds(10));
```

Đây là mẫu đặt trong một bean có các methods `reportMetrics`, `pollUpdates`, imports `Duration`. Giữ handle nếu muốn hủy từ component điều phối hoặc khi cấu hình thay đổi.

### 9.3. CronTrigger

```java
CronTrigger trigger = new CronTrigger(
        "0 0 9 * * MON-FRI",
        ZoneId.of("Asia/Ho_Chi_Minh"));

ScheduledFuture<?> handle =
        taskScheduler.schedule(this::sendDailyReport, trigger);
```

Đây là minh họa, cần imports `CronTrigger`, `ZoneId` và method. Dùng `CronTrigger` cho điều phối lịch động; với lịch tĩnh, `@Scheduled(cron=...)` thường đơn giản hơn.

### 9.4. Cancel

```java
boolean cancellationRequested = handle.cancel(false);
```

`cancel(false)` yêu cầu ngừng các lần chạy tương lai nhưng **không interrupt** task đã chạy. `cancel(true)` có thể yêu cầu interrupt, nhưng không bảo đảm task hợp tác dừng ngay. Đừng coi cancel là rollback tự động cho DB writes hoặc external side effects.

### 9.5. Scheduler không tự bảo đảm exactly-once

Trong cluster 3 replicas, mỗi replica có thể đăng ký cùng một `@Scheduled` method, vì thế công việc có thể chạy **ba lần**. Spring scheduling local không tự bầu leader hoặc lưu job state liên node. Nếu yêu cầu job chỉ chạy một lần cho toàn hệ thống, cần giải pháp như distributed lock, Quartz với job store cấu hình phù hợp, broker/queue hoặc một service scheduler chuyên dụng.

Đối với task quan trọng phải sống qua deploy/restart, đừng chỉ giữ một `ScheduledFuture` trong memory.

## 10. Lỗi, timeout và concurrency

### 10.1. Execution exceptions

Khi gọi `Future.get(5, TimeUnit.SECONDS)`, caller có thể gặp:

| Tình huống | Kết quả |
| --- | --- |
| Thành công | Future trả value |
| Task ném exception | `ExecutionException` chứa cause |
| Hết thời gian chờ | `TimeoutException` |
| Thread caller bị interrupt | `InterruptedException` |
| Task đã bị hủy | `CancellationException` |
| Pool/queue quá tải | Rejection có thể xảy ra khi submit |

Nếu bắt `InterruptedException` để tiếp tục xử lý, thường cần `Thread.currentThread().interrupt()` trước khi thoát hoặc propagate đúng cách. Không dùng `catch(Exception ignored)` rồi âm thầm coi job hoàn tất.

**Quan trọng:** timeout khi đợi một Future không tự bảo đảm tác vụ đã dừng; cần cancellation/interrupt và logic cooperatively cancel phù hợp.

### 10.2. Scheduler error handling

Một công việc định kỳ có thể ném lỗi; chính sách tiếp tục lần chạy tiếp theo phụ thuộc cách đăng ký và error handler của scheduler. Cần kiểm soát logging, metric, retry và trạng thái business job. `ThreadPoolTaskScheduler` hỗ trợ cấu hình error handler; đừng coi một exception trong recurring task là chắc chắn đã được gửi lại request thread.

### 10.3. Backpressure

Khi pool core=2, max=4, queue=32, nhiều tasks bị block trong I/O có thể khiến queue đầy và task bị reject. Phải xem đây là tín hiệu overload. Tăng pool lên vô hạn không sửa root cause: DB connection pool hoặc external API có thể bão hòa sớm hơn.

Một service có thể dùng semaphore hoặc rate limiter, bounded queue, 429/503 tương ứng, và circuit breaker khi tải vượt năng lực phục vụ.

### 10.4. ThreadLocal, transaction và MDC

Một `@Transactional` method gửi việc `@Async` sang pool **không làm transaction thread-local tự đi theo**. Task có thể đọc dữ liệu trước commit. `SecurityContext`, MDC correlation, request context hoặc custom ThreadLocal cũng thường không tự propagate.

Cần phân ranh transaction mới cho worker khi cần; để tác vụ chỉ chạy sau commit, cân nhắc `@TransactionalEventListener(phase=AFTER_COMMIT)` hoặc outbox tùy mức độ cần bền vững. Đối với tracing, sử dụng context propagation/`TaskDecorator` thích hợp, không cố copy transaction object qua threads.

## 11. Context lifecycle và shutdown

### 11.1. Spring-managed không có nghĩa job sẽ sống qua crash

Khi context đóng, Spring có thể gọi destroy/shutdown lifecycle trên `ThreadPoolTaskExecutor`, `ThreadPoolTaskScheduler` managed beans. Nhưng kill -9, power loss hay JVM crash có thể bỏ qua shutdown hooks. Không có bảo đảm mọi task queued/running sẽ hoàn tất.

### 11.2. Shutdown có thứ tự

Một trình tự mong muốn:

```text
Nhận lệnh dừng
  |
  +-- Ngừng nhận việc mới
  +-- Hủy/đình chỉ lịch recurring khi thích hợp
  +-- Drain công việc đang xử lý trong deadline
  +-- Lưu checkpoint hoặc job status
  +-- Dừng executor/scheduler
  +-- Đóng dependencies được task sử dụng
```

`setWaitForTasksToCompleteOnShutdown(true)` chưa đủ nếu jobs còn dùng datasource hoặc client bị Spring đóng trong cùng shutdown. Với startup/shutdown phức tạp, dùng `SmartLifecycle`, phase và `stop(Runnable callback)` để phối hợp drain cùng dependency graph, nhưng phải gọi callback khi stop thật sự hoàn tất.

### 11.3. Scheduled task lâu và pool một thread

Nếu dùng scheduler auto-config mặc định một thread, một scheduled job chạy 90 giây có thể làm job khác trễ. Giải pháp:

- Đảm bảo callback ngắn và có timeout.
- Tăng scheduler threads khi đã đo tải và biết concurrency phù hợp.
- Tách scheduler khỏi executor chạy I/O nặng, kèm completion tracking.
- Dùng job scheduler có persistence nếu cần durable scheduling.
- Quan sát scheduled lag và queue, không chỉ số lần chạy.

### 11.4. Java 21 virtual threads

Cấu hình:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot 3.3 có thể chuyển **auto-configured** execution/scheduling sang implementation dùng virtual threads. Điều này không tự biến `ThreadPoolTaskExecutor` custom ở mục 7 thành virtual-thread executor. Virtual threads hữu ích cho nhiều công việc I/O chờ nhưng không tăng CPU cores hoặc DB capacity, vì vậy vẫn phải giới hạn concurrency và bảo vệ downstream.

Với `SimpleAsyncTaskScheduler` dùng virtual threads, fixed-delay có scheduling semantics đáng lưu ý; các jobs fixed-rate/cron thường phù hợp hơn trong mô hình virtual-thread-aligned. Tài liệu Spring Framework 6.1 giải thích chi tiết về các trường hợp này.

## 12. Kiểm thử bằng Spring Boot Test và JUnit

### 12.1. Không dùng sleep để chứng minh hoàn tất

`Thread.sleep(100)` trong test không bảo đảm task đã chạy: máy CI chậm hoặc GC pause có thể khiến test ngẫu nhiên fail. Dùng `Future.get(timeout)`, `CountDownLatch.await(timeout)` hoặc fake scheduler/clock.

### 12.2. Integration test

Tệp `src/test/java/com/example/tasks/ManagedTasksIntegrationTest.java`:

```java
package com.example.tasks;

import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ManagedTasksApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ManagedTasksIntegrationTest {

    @Autowired
    private ManagedWorker worker;

    @Autowired
    @Qualifier("taskScheduler")
    private ThreadPoolTaskScheduler scheduler;

    @Test
    void processesAsyncAndScheduledTasks() throws Exception {
        assertEquals("HELLO",
                worker.normalize("hello").get(5, TimeUnit.SECONDS));

        CountDownLatch finished = new CountDownLatch(1);
        ScheduledFuture<?> handle = scheduler.schedule(
                finished::countDown,
                Instant.now().plusMillis(50));

        assertNotNull(handle);
        assertTrue(finished.await(5, TimeUnit.SECONDS));
    }
}
```

`@SpringBootTest` khởi tạo context thật, cho phép kiểm tra wiring executor/scheduler. Test này có thể kích hoạt `DemoRunner` trong quá trình Spring Boot startup, vì đó là một `ApplicationRunner` bean; các dòng runner trong test logs không có nghĩa test bị chạy trùng.

Khi dùng scheduler khác hoặc sửa cấu hình thread pool, vẫn nên để timeout hữu hạn. Nếu test có nhiều tasks và có thể thất bại, dùng `try/finally` hủy handle, tránh rò rỉ scheduling registration.

### 12.3. Unit test nhanh hơn

Không nhất thiết mọi test đều cần Boot context. Nếu business service chỉ phụ thuộc `TaskExecutor`, có thể inject một fake executor chạy `runnable.run()` trực tiếp để unit test logic; nhưng test ấy **không chứng minh** thread pool configuration hoạt động. Dùng integration test cho phần Spring wiring và test với latches cho concurrency quan trọng.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `@Async` không chạy nền | Quên `@EnableAsync`, self-invocation hoặc bean không được quản lý | Bật async infrastructure, gọi qua Spring proxy |
| `@Scheduled` không chạy | Quên `@EnableScheduling`, bean chưa scan, context đã đóng | Kiểm tra registration và scheduling |
| Pool do Boot auto-config không có | Custom `Executor` làm auto-config back off | Phân biệt auto-config và named custom beans |
| Thread pool không tăng đến max | Queue còn chỗ, chưa đạt ngưỡng | Kiểm tra core/queue/max semantics |
| `@Async` chọn sai executor | Nhiều beans cùng kiểu, qualifier không rõ | `@Async("ioTaskExecutor")` |
| Cron chạy không đúng giờ | Cron sai 6 fields hoặc timezone | Chọn zone và test lịch |
| Nhiều replicas chạy cùng một job | Scheduling in-memory trên từng JVM | Distributed lock/persistent scheduler |
| Scheduler chạy chậm | Job blocking chiếm scheduler thread | Tăng pool có tính toán hoặc tách execution |
| App báo ready dù task chưa xong | Runner submit rồi trả về | Chờ completion có timeout nếu thiết yếu |
| Task bị mất khi app restart | Chỉ xếp trong memory queue | Durable queue, outbox, job persistence |
| `@Async void` lỗi không về caller | Không có Future | AsyncUncaughtExceptionHandler/monitoring |
| Shutdown treo hoặc task dùng resource đã đóng | Drain/shutdown phase không được phối hợp | `SmartLifecycle`, timeout, dependency order |
| Task không thấy transaction đang active | Giao việc sang thread khác | New transaction boundary/AFTER_COMMIT/outbox |
| Test dùng `Thread.sleep` thất thường | Không có completion signal | Latches/futures/fake clock |
| `@Scheduled` callback có args request | Framework gọi method theo lịch, không theo request | Dùng injected dependencies hoặc scheduling programmatic |

### 13.1. Checklist chẩn đoán

1. Executor/scheduler có đúng là Spring beans chưa?
2. `@EnableAsync` và `@EnableScheduling` có đang hiệu lực?
3. Lời gọi `@Async` có đi qua Spring proxy?
4. Đang sử dụng bean named executor/scheduler nào?
5. Task đã submit, đã bắt đầu, hay đã hoàn tất? Có Future/ack không?
6. Có pool/queue saturation hoặc task rejection?
7. `@Scheduled` dùng fixedRate, fixedDelay hay cron, timezone nào?
8. Job có chạy lâu hơn chu kỳ, hoặc nhiều instances cùng chạy?
9. Có exception bị bỏ qua trong background thread?
10. Có phụ thuộc ThreadLocal/transaction của request thread?
11. Trong shutdown, có ngừng nhận job trước khi đóng dependencies?
12. Nếu JVM chết, task có cần sống lại từ durable state không?

## 14. Tình huống áp dụng

**Gửi email best-effort:** một `@Async("ioTaskExecutor")` method phù hợp nếu mất một số thông báo không gây lỗi dữ liệu, nhưng vẫn cần timeout, lỗi và metrics. Nếu email cần chắc chắn gửi sau commit, dùng outbox/queue.

**Tính toán ngắn:** một `TaskExecutor` được giới hạn concurrency phù hợp với CPU; tránh quá nhiều threads để xử lý việc tính toán CPU-bound.

**Làm mới cache định kỳ:** `@Scheduled(fixedDelay=...)` hoặc programmatic schedule phù hợp khi refresh mỗi replica là hợp lệ. Nếu chỉ một writer trong cluster, cần coordination.

**Hẹn lời nhắc trong JVM:** `TaskScheduler.schedule` rất tiện cho một one-shot không yêu cầu persistence. Nếu người dùng mong lời nhắc sống qua deploy/restart, cần job store hoặc scheduler bền vững.

**Startup data verification:** `ApplicationRunner` có thể gửi việc vào Spring-managed executor và **đợi Future** thành công trước khi Boot phát `ApplicationReadyEvent`. Nếu task thất bại, propagate exception để startup báo lỗi thay vì ready giả.

**Ứng dụng xử lý message:** task executor chỉ là nơi chạy worker; nghiệp vụ acknowledgment, retry, idempotency, deduplication, ordering theo business key và shutdown của consumer vẫn cần thiết kế riêng.

## 15. Bài tập và câu hỏi tự kiểm tra

1. So sánh `TaskExecutor.execute(Runnable)` với `TaskScheduler.schedule(Runnable, Instant)`.
2. Vì sao `new Thread(...)` trong mọi service khó quản lý lifecycle?
3. Giải thích khác biệt giữa submit task và task hoàn tất.
4. Viết hai beans `ioTaskExecutor` và `cpuTaskExecutor`, chỉ định executor bằng `@Async`.
5. Vì sao `this.processAsync()` trong cùng bean có thể không chạy nền?
6. Trong ví dụ Maven, vì sao `ASYNC result` có trước `RUNNER done`?
7. Nếu xóa `completed.await(...)` trong runner, `ApplicationReadyEvent` có bảo đảm scheduled task đã chạy không?
8. Khi queueCapacity lớn, tại sao maxPoolSize có thể ít được sử dụng?
9. Với core=1, max=2, queue=1 và bốn tasks đồng thời, task cuối có thể bị reject như thế nào?
10. Khi nào nên dùng fixedRate, khi nào nên dùng fixedDelay?
11. Viết cron 09:00 các ngày làm việc theo `Asia/Ho_Chi_Minh`.
12. Làm sao hủy một registration `ScheduledFuture` khi thay đổi lịch?
13. Vì sao task periodic quá lâu trên scheduler một thread làm job khác trễ?
14. Vì sao `@Async void` không phù hợp khi caller cần biết kết quả nghiệp vụ?
15. Mô tả cách dùng `CompletableFuture` và timeout để phối hợp một startup task.
16. Vì sao thread khác không tự thấy transaction thread-local của publisher?
17. Khi nào nên dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox?
18. Vì sao Spring-managed pool không có nghĩa task được lưu bền vững qua JVM crash?
19. Nếu 3 pods đều có `@Scheduled`, có bao nhiêu lần job có thể được chạy trong cùng một mốc lịch?
20. Đề xuất cách test scheduling không dùng `Thread.sleep`.
21. Tại sao cần xét shutdown dependency trước khi bật `waitForTasksToCompleteOnShutdown`?
22. Với Java 21 virtual threads, các auto-configured executors có thể thay đổi ra sao?
23. Một hệ thống xử lý 1000 tasks mỗi giây nhưng DB chỉ xử lý được 100 transactions mỗi giây: tăng pool có giải quyết triệt để không?
24. Thiết kế pipeline `QUEUED → RUNNING → DONE/FAILED` có deadline, retry, backpressure và durable store cho job không được mất.

**Tiêu chí đạt:** cấu hình Spring-managed executor và scheduler đúng, chạy được demo Java 21/Spring Boot 3.3, hiểu completion/timeout, dùng scheduling API phù hợp, và thiết kế có kiểm soát về lỗi, shutdown, transaction và scale.

## 16. Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 — TaskExecutor API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework 6.1 — TaskScheduler API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework 6.1 — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 — ThreadPoolTaskScheduler: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
- Spring Framework 6.1 — EnableAsync: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework 6.1 — Scheduled: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
