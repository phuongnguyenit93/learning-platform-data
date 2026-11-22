# Liên hệ @Async và @Scheduled với tài nguyên thực thi trong Spring Boot

Trong Spring Boot, hai annotation `@Async` và `@Scheduled` khiến phương thức được thực thi theo cách không còn đơn thuần là “caller gọi trực tiếp và chạy ngay trên chính thread của caller”. Tuy nhiên chúng **giải quyết hai bài toán khác nhau**:

- **`@Async`**: *chạy công việc ở đâu?* — chuyển một lời gọi đủ điều kiện sang `Executor` / `TaskExecutor`, thường là một pool có worker threads và hàng đợi.
- **`@Scheduled`**: *khi nào cần kích hoạt công việc?* — đăng ký trigger định kỳ với `TaskScheduler` / `ScheduledExecutorService`, dùng tài nguyên của scheduler để gọi method đúng lịch.

Do đó, không phải “thêm annotation thì có thread miễn phí”. Tác vụ vẫn dùng CPU, heap, thread, connection, queue và ngân sách thời gian của **chính tiến trình Java**. Nếu scheduling dùng một thread và một task blocking chiếm thread đó, những lần kích hoạt khác có thể bị trì hoãn. Nếu async pool quá nhỏ hoặc hàng đợi không có giới hạn, công việc có thể chậm, bị từ chối hoặc làm tăng bộ nhớ tới mức nguy hiểm.

Bài học thuộc mục **Luồng và tác vụ** của Spring Boot Application Runtime. Ví dụ chạy với **Java 17+ và Spring Boot 3.3.x**, mặc định dùng platform threads; phần cuối giải thích thêm virtual threads trên Java 21+.

## 1. Bản đồ cơ chế: trigger và executor là hai vai trò

~~~text
HTTP request / runner / event / method khác
               |
               | gọi bean @Async qua Spring proxy
               v
       ThreadPoolTaskExecutor
          |    |    |
       worker threads + queue
               |
               v
          Business method
               |
               +---- có thể gọi DB / HTTP / broker


Spring TaskScheduler
       |
       | đến thời điểm @Scheduled (cron/fixedRate/fixedDelay)
       v
scheduled method
       |
       +--- chạy xử lý trực tiếp trên scheduler thread
       |
       +--- hoặc gọi bean @Async qua proxy
                         |
                         v
                  Async TaskExecutor
                         |
                         v
                    Worker thread
~~~

Một scheduled method **không tự động** được gửi sang async executor. Mặc định, với scheduler pool thông thường, phần thân method được thực thi trên **thread của scheduler**. Chỉ khi bạn **chủ động** gửi công việc sang một executor khác, hoặc gọi một Spring bean có `@Async` qua proxy hợp lệ, phần xử lý mới chuyển sang pool tương ứng.

Điều này tạo ra hai ngân sách riêng:

1. **Ngân sách kích hoạt:** scheduler threads, thời gian chờ tới tick tiếp theo, độ trễ trong việc gọi scheduled method.
2. **Ngân sách xử lý:** executor workers, queue capacity, số lượng tác vụ đang chạy, giới hạn downstream dependency.

Nếu đồng nhất hai ngân sách này, scheduler có thể vừa trễ tick vừa không kiểm soát được backlog.

## 2. @Async làm việc như thế nào?

Ví dụ một service:

~~~java
@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Thực hiện công việc trong executor đã chọn.
        return CompletableFuture.completedFuture("report-" + reportId);
    }
}
~~~

Đây là đoạn **minh họa**, cần import `Service`, `Async`, `CompletableFuture`, bật `@EnableAsync` và khai báo executor bean tên `reportExecutor` nếu muốn chạy đúng như annotation.

Luồng thông thường:

1. Một caller gọi method trên **Spring proxy của bean**.
2. Proxy nhận biết `@Async("reportExecutor")`.
3. Proxy đóng gói invocation thành task và nộp vào executor tương ứng.
4. Caller được trả về sớm (với kiểu trả về hỗ trợ), thay vì chờ thân method hoàn tất trên caller thread.
5. Worker thread lấy task từ queue và thực thi method.
6. Thành công, lỗi, hủy task và hoàn tất `Future`/`CompletableFuture` đều phải được xử lý theo hợp đồng của method.

**Điểm quyết định:** `@Async` không có ý nghĩa khi method được gọi bằng cách không đi qua interceptor/proxy phù hợp, chẳng hạn self-invocation của một method trong cùng class ở proxy mode thông thường.

### Kích hoạt @Async

Spring không tự xử lý tất cả `@Async` chỉ vì annotation có trên classpath. Hãy bật:

~~~java
@Configuration
@EnableAsync
class AsyncConfiguration {
}
~~~

Đây là đoạn khai báo cấu hình, không phải class độc lập nếu thiếu các import. Có thể đặt `@EnableAsync` trực tiếp trên main `@SpringBootApplication` class như ví dụ đầy đủ bên dưới.

`@Async` có thể áp dụng cho method trả về `void`, `Future<T>` hoặc `CompletableFuture<T>` theo hợp đồng Spring. Nếu `void` method ném exception, caller không nhận được exception qua return value; cần logging và `AsyncUncaughtExceptionHandler` khi thích hợp. Với `CompletableFuture`, caller nên quan sát kết quả bằng `whenComplete(...)`, `handle(...)` hoặc API tương ứng. Không nên tạo task rồi bỏ qua hoàn toàn thành công/thất bại.

## 3. @Scheduled làm việc như thế nào?

Bật scheduling bằng:

~~~java
@Configuration
@EnableScheduling
class SchedulingConfiguration {
}
~~~

Một bean có thể khai báo:

~~~java
@Scheduled(fixedDelay = 5000)
public void pollInbox() {
    // Tác vụ được gọi lại sau khi lần trước hoàn tất và chờ 5 giây.
}
~~~

Trong trường hợp phương thức đồng bộ thông thường:

- **`fixedDelay`**: khoảng chờ được tính từ **kết thúc lần gọi trước** đến **bắt đầu lần sau**.
- **`fixedRate`**: cố gắng kích hoạt theo nhịp đều tính theo thời điểm bắt đầu; nếu scheduler thiếu thread hoặc công việc kéo dài, lần chạy có thể bị trễ, không có bảo đảm luôn đúng tuyệt đối từng millisecond.
- **`cron`**: kích hoạt theo biểu thức lịch, có thể cần xét time zone, DST và sự trùng lặp trong môi trường nhiều instance.
- **`initialDelay`**: chờ một khoảng ban đầu trước lần chạy đầu, hữu ích để giảm nhiễu ngay lúc startup.

Ví dụ cú pháp:

~~~java
@Scheduled(initialDelay = 1000, fixedRate = 10000)
public void refreshMetadata() {
    // Xem xét duration và concurrency của method.
}
~~~

Với scheduler `ThreadPoolTaskScheduler` có **một thread** như cấu hình mặc định không dùng virtual threads của Spring Boot, nhiều scheduled method có thể tranh cùng một thread. Một method ngủ 30 giây hoặc đợi HTTP request timeout rất lâu có thể làm các tick khác chậm đáng kể.

**Đừng hiểu `@Scheduled` là hệ thống hàng đợi công việc bền vững.** Nếu process chết, lịch tick trong bộ nhớ không tự động thành một distributed job có trạng thái, retry và exactly-once. Trong Kubernetes có ba replicas, mỗi replica có thể đăng ký và chạy cùng một `@Scheduled` method. Muốn “chỉ một instance chạy”, cần leader election, distributed lock, scheduler ngoài hoặc thiết kế idempotent.

## 4. Spring Boot tự cấu hình executor và scheduler nào?

Trong **Spring Boot 3.3** với Java 17 / platform threads và chưa có bean tùy chỉnh làm thay đổi điều kiện auto-configuration:

| Nhu cầu | Loại thường được Boot tự tạo | Điểm mặc định cần nhớ |
|---|---|---|
| Task execution, ví dụ `@EnableAsync` | `ThreadPoolTaskExecutor` | Pool bắt đầu với **8 core threads**; các property dưới `spring.task.execution.*` điều chỉnh cách chạy/queue. |
| Scheduling, ví dụ `@EnableScheduling` | `ThreadPoolTaskScheduler` | **Pool size mặc định 1 thread**, các property dưới `spring.task.scheduling.*` có thể điều chỉnh. |

Điều kiện “chưa có bean tùy chỉnh” rất quan trọng. Khi ứng dụng tự đăng ký `Executor`, Boot có thể **back off** việc tạo async executor mặc định; khi ứng dụng tự đăng ký `TaskScheduler`, Boot cũng có thể không tạo thêm scheduler mặc định. Không được giả định mọi `spring.task.execution.*` property luôn áp dụng cho executor bạn tự `new ThreadPoolTaskExecutor()`.

Ví dụ khi **dùng auto-configuration của Boot**, cấu hình trong `application.properties`:

~~~properties
spring.task.execution.thread-name-prefix=app-async-
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=10s

spring.task.scheduling.thread-name-prefix=app-schedule-
spring.task.scheduling.pool.size=2
~~~

Ở đây:

- Async pool có 8 core threads, giới hạn tối đa 16, queue capacity 100.
- Khi tất cả core threads đang bận, task thường được đưa vào queue trước; khi queue đầy, pool có thể tăng đến max size; khi cả pool và queue đều đầy, task có thể bị **reject**.
- Scheduler có 2 threads, cho phép một số lịch chạy song song hơn trường hợp một scheduler thread.
- **Queue không giới hạn** có thể khiến `max-size` gần như không được dùng theo cách bạn kỳ vọng; cần hiểu chính sách xếp hàng của `ThreadPoolExecutor`.

Đặt queue capacity hữu hạn là một cách quản lý **backpressure**: hệ thống phải quyết định xử lý thế nào khi không còn chỗ, chứ không thể nhận công việc vô hạn.

## 5. Chọn Executor cho @Async và TaskScheduler cho @Scheduled

Hai loại bean nên có tên và trách nhiệm rõ ràng:

~~~java
@Bean("businessExecutor")
ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("business-");
    return executor;
}

@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-");
    return scheduler;
}
~~~

Đây là các **factory method minh họa** cần nằm trong class cấu hình có các import của Spring. Khi là bean, Spring sẽ quản lý initialization và destruction của chúng; không gọi thủ công `initialize()` lên chính instance bean này trong factory method rồi để container initialize lặp.

Để một async method chọn pool trên:

~~~java
@Async("businessExecutor")
public CompletableFuture<Result> calculate(...) {
    // ...
}
~~~

Đoạn là minh họa, cần class `Result` và method body phù hợp. Phần value của `@Async` có thể chỉ rõ bean executor/qualifier, giúp tránh “thêm một Executor bean mới khiến các @Async cũ vô tình đổi pool”.

Với `@Scheduled`, một bean `TaskScheduler` phù hợp có thể được dùng bởi processor. Khi chỉ có một scheduler bean và đặt tên chuẩn `taskScheduler`, lựa chọn thường rõ ràng. Nếu nhiều scheduler cùng tồn tại, cần xác định scheduler cần dùng bằng API cấu hình thích hợp hoặc thuộc tính chọn scheduler trên annotation khi phiên bản Spring hỗ trợ, thay vì đoán container sẽ chọn ngẫu nhiên.

**Không dùng cùng một pool cho mọi việc chỉ vì có thể.** Một công việc blocking kéo dài, một scheduler và việc xử lý HTTP async có đặc tính tải khác nhau. Pool tách biệt giúp áp dụng timeout, queue, metrics và shutdown khác nhau.

## 6. Ví dụ đầy đủ: scheduled trigger gửi task sang async executor

Chương trình dưới đây tạo rõ ràng:

- Một scheduler tên `taskScheduler` với thread prefix `timer-`.
- Một executor tên `bizExecutor` với thread prefix `jobs-`.
- Một bean có `@Scheduled` dùng scheduler để kích hoạt.
- Một bean **khác** có `@Async("bizExecutor")` để xử lý công việc trên executor.
- Một `ApplicationRunner` chờ task hoàn tất, in kết quả so sánh thread, rồi chương trình đóng context.

Cấu trúc:

~~~text
thread-resources-demo/
├── build.gradle
└── src/main/java/com/example/threads/ThreadResourcesApplication.java
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.threads.ThreadResourcesApplication'
}
~~~

### ThreadResourcesApplication.java

Tạo file `src/main/java/com/example/threads/ThreadResourcesApplication.java`:

~~~java
package com.example.threads;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ThreadResourcesApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ThreadResourcesApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext ignored = application.run(args)) {
            // ApplicationRunner đã chờ task hoàn tất.
        }
    }

    @Bean("bizExecutor")
    ThreadPoolTaskExecutor bizExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("jobs-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("timer-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(5);
        return scheduler;
    }

    @Bean
    Signals signals() {
        return new Signals();
    }

    @Bean
    AsyncWorker asyncWorker(Signals signals) {
        return new AsyncWorker(signals);
    }

    @Bean
    ScheduledTrigger scheduledTrigger(
            AsyncWorker worker, Signals signals) {
        return new ScheduledTrigger(worker, signals);
    }

    @Bean
    ApplicationRunner reportThreadOwnership(Signals signals) {
        return args -> {
            boolean finished = signals.done.await(10, TimeUnit.SECONDS);
            if (!finished) {
                throw new IllegalStateException(
                        "Timed out waiting for the scheduled async task");
            }

            String triggerThread = signals.triggerThread.get();
            String workerThread = signals.workerThread.get();

            System.out.println("task completed = true");
            System.out.println(
                    "trigger uses scheduler = "
                            + triggerThread.startsWith("timer-"));
            System.out.println(
                    "worker uses executor = "
                            + workerThread.startsWith("jobs-"));
            System.out.println(
                    "different threads = "
                            + !triggerThread.equals(workerThread));
        };
    }

    public static final class Signals {
        final CountDownLatch done = new CountDownLatch(1);
        final AtomicReference<String> triggerThread =
                new AtomicReference<>();
        final AtomicReference<String> workerThread =
                new AtomicReference<>();
    }

    public static class ScheduledTrigger {
        private final AsyncWorker worker;
        private final Signals signals;

        ScheduledTrigger(AsyncWorker worker, Signals signals) {
            this.worker = worker;
            this.signals = signals;
        }

        @Scheduled(initialDelay = 200, fixedDelay = 60000)
        public void tick() {
            signals.triggerThread.set(Thread.currentThread().getName());
            // Gọi qua bean khác, đã được Spring @Async proxy.
            worker.process();
        }
    }

    public static class AsyncWorker {
        private final Signals signals;

        AsyncWorker(Signals signals) {
            this.signals = signals;
        }

        @Async("bizExecutor")
        public void process() {
            signals.workerThread.set(Thread.currentThread().getName());
            signals.done.countDown();
        }
    }
}
~~~

Mọi class phụ trợ trong ví dụ là nested classes. `ScheduledTrigger` và `AsyncWorker` **khác instance**, và `worker.process()` là lời gọi qua bean đã được Spring container xử lý, không phải `this.process()` tự gọi trong cùng object.

Tại sao dùng `CountDownLatch`? Vì scheduling chạy trong background. Nếu `main` chỉ gọi `run()` rồi đóng context ngay, ứng dụng console có thể dừng trước khi scheduled tick đầu tiên xảy ra. Runner chờ task đầu hoàn thành để có thể kiểm tra. Thời gian chờ **10 giây** là giới hạn của ví dụ kiểm thử, không phải timeout khuyến nghị cho production.

### Chạy và quan sát

Trong thư mục dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Đây là chương trình Spring Boot có dependency tương ứng; không thể chạy riêng file Java bằng một lệnh `javac` trần mà không có classpath chứa Spring Framework/Spring Boot.

Trong điều kiện chạy bình thường, bỏ qua log Spring Boot và những dòng Gradle, **stdout do code demo chủ động in** là:

~~~text
task completed = true
trigger uses scheduler = true
worker uses executor = true
different threads = true
~~~

Bốn dòng trên được in trong `ApplicationRunner` **sau khi** `CountDownLatch` báo task hoàn tất, nên thứ tự của chúng ổn định. `triggerThread` có prefix `timer-`; `workerThread` có prefix `jobs-`. Tên thread thật có thể chứa hậu tố số khác nhau, vì vậy chương trình kiểm tra prefix rồi in boolean thay vì khẳng định một tên thread cố định.

**Cách hiểu kỹ thuật:**

1. `@EnableScheduling` làm Spring đăng ký method `ScheduledTrigger.tick()` theo lịch.
2. `ThreadPoolTaskScheduler` dùng thread `timer-...` để gọi `tick()`.
3. `tick()` lưu thread name rồi gọi `AsyncWorker.process()` **qua một bean được Spring quản lý**.
4. `@Async("bizExecutor")` chuyển lần thực thi `process()` sang `ThreadPoolTaskExecutor`, thread tên `jobs-...`.
5. Worker lưu tên thread, báo hoàn thành; runner đọc hai tên để xác nhận khác nhau.
6. Khi chương trình thoát khối try, context đóng, dừng scheduler và executor theo lifecycle của Spring.

Không cần HTTP server trong ví dụ. `WebApplicationType.NONE` giúp tập trung vào tài nguyên background thay vì số thread của Tomcat hoặc những thành phần web khác.

## 7. Điều gì xảy ra khi @Scheduled xử lý trực tiếp công việc blocking?

Nếu không chuyển sang async executor, một scheduled method như sau chạy trên scheduler thread:

~~~java
@Scheduled(fixedDelay = 1000)
public void slowPoll() throws InterruptedException {
    Thread.sleep(5000);  // Mô phỏng I/O bị chặn năm giây.
}
~~~

Đây là method minh họa trong một bean có scheduling đã bật; **không** thêm trực tiếp vào chương trình mục 6 nếu muốn giữ stdout đã mô tả.

Với `fixedDelay = 1000`:

- Một lần chạy kéo dài khoảng 5 giây.
- Spring chờ khoảng 1 giây **sau khi lần chạy kết thúc** rồi mới lên lịch lần tiếp.
- Chu kỳ thực tế của riêng method này khoảng 6 giây, chưa tính scheduling latency.
- Nếu pool scheduler chỉ có một thread, trong khoảng chờ blocking nó cũng không còn rảnh để xử lý những scheduled task khác.

Tăng `spring.task.scheduling.pool.size` có thể giúp **nhiều job khác nhau** không phải tranh một thread, nhưng không thay thế timeout, retry có kiểm soát hoặc kiến trúc tách xử lý nặng khỏi scheduler.

Với `fixedRate=1000`, scheduler cố duy trì nhịp một giây, nhưng không có đủ CPU/thread thì lần kích hoạt vẫn trễ. **Fixed rate không phải lời hứa mỗi invocation sẽ luôn chạy đồng thời hay được kích hoạt đúng thời điểm**; với một task được đăng ký đơn lẻ trên scheduler thông thường, các lần chạy trực tiếp không tự nhiên tạo ra một task mới chồng lấn trên cùng schedule.

Với `cron`, bạn cũng phải xem xét timezone, DST, khoảng ngừng ứng dụng và việc mỗi replica tự chạy lịch của mình.

## 8. Vì sao ghép @Scheduled với @Async có thể nguy hiểm nếu thiếu giới hạn?

Giả sử scheduler kích hoạt mỗi 1 giây còn mỗi công việc async xử lý mất 30 giây. Khi `@Scheduled` chỉ **submit** task vào executor rồi trả về ngay, nó có thể tiếp tục kích hoạt các lần tiếp theo mà không chờ công việc trước hoàn thành.

~~~text
Scheduler: tick1 tick2 tick3 tick4 tick5 ...
                |     |     |     |
                v     v     v     v
Executor:     queue / worker 1 / worker 2 ...
                |
           backlog tăng dần nếu tốc độ đến > tốc độ xử lý
~~~

Khi đó:

- **`fixedDelay` đo thời gian hoàn thành của scheduled method submit**, không phải mặc nhiên đợi async worker xử lý xong.
- Các lần xử lý **có thể chồng lấn**, nếu executor có nhiều thread.
- Queue có thể tăng dần, gây độ trễ và tiêu thụ heap.
- Nếu queue hữu hạn, executor có thể từ chối task mới khi bão hòa.
- Một tác vụ không idempotent có thể chạy trùng công việc nếu có nhiều trigger, retry hoặc nhiều Pod.
- Scheduler vẫn có thể “đúng giờ” trong khi backlog xử lý thực tế đã rất lớn.

Nếu muốn tại một thời điểm chỉ chạy một job, cần một chính sách cụ thể:

1. **Không offload sang async** nếu job ngắn, an toàn và scheduler có năng lực phù hợp.
2. Dùng `Semaphore` hoặc một cờ trạng thái để **bỏ qua tick khi job trước chưa xong**, nếu bỏ qua là chấp nhận được.
3. Dùng **hàng đợi bền vững có giới hạn** khi mọi công việc phải được lưu và xử lý sau; không dựa vào queue nội bộ của thread pool cho durability.
4. Sử dụng **distributed lock/leader election** khi nhiều instance có thể cùng kích hoạt cùng một công việc.
5. Thiết kế **idempotency key** và retry/backoff để không tạo hiệu ứng phụ trùng lặp.

**Cảnh báo:** Đặt cả `@Scheduled` và `@Async` trên **cùng một method** có thể tạo ngữ nghĩa khó theo dõi, phụ thuộc cơ chế bean/proxy và completion semantics. Với mục tiêu học và vận hành, mẫu **scheduled trigger bean → async worker bean** như ví dụ mục 6 thường rõ ràng hơn.

## 9. Queue, pool size và lỗi từ chối task

Hãy xét một executor có:

~~~properties
spring.task.execution.pool.core-size=2
spring.task.execution.pool.max-size=4
spring.task.execution.pool.queue-capacity=10
~~~

Khi cấu hình này áp dụng cho **executor do Boot tự cấu hình** (không phải bean custom của ví dụ mục 6), cơ chế cơ bản của `ThreadPoolExecutor` là:

1. Tạo/tận dụng core workers để xử lý task.
2. Khi core workers đều bận, đưa task mới vào queue nếu còn chỗ.
3. Khi queue đầy, có thể tạo thêm worker tới max size.
4. Khi cả worker slots và queue đều bão hòa, task mới có thể bị **từ chối** theo rejection policy.

Trong Spring, trường hợp từ chối có thể biểu hiện bằng `TaskRejectedException` tại nơi submit task; đối với lời gọi `@Async`, caller có thể nhận exception khi proxy không nộp task thành công.

**Không có cấu hình “vô hạn mà an toàn”**: số thread quá lớn gây context-switch và tải downstream, queue quá lớn gây latency và heap pressure, còn queue quá nhỏ có thể reject thường xuyên. Phải dựa trên thời gian xử lý và tốc độ nhận việc để chọn.

Ví dụ tư duy sizing:

~~~text
Tốc độ nhận:  20 công việc/giây
Thời gian xử lý trung bình: 0,5 giây
Concurrency tối thiểu ước lượng: ~10 công việc đang xử lý
~~~

Đây là phép ước lượng từ quan hệ `concurrency ≈ throughput × latency` (Little’s Law trong điều kiện ổn định), **không phải cấu hình pool được khuyến nghị tự động**. Cần tính cả percentile latency, blocking I/O, retry, CPU cores, downstream rate limits và spike traffic.

### Hai loại “đúng hạn” khác nhau

- **Scheduler lag**: tick đến trễ do scheduler thiếu thread hoặc callback blocking.
- **Executor queue wait**: tick đã được submit đúng hạn nhưng worker bắt đầu xử lý trễ vì queue.

Một dashboard chỉ hiển thị thời điểm gọi `@Scheduled` sẽ **không phản ánh** thời gian job thực sự hoàn thành. Nên đo riêng schedule-to-submit, submit-to-start, processing duration, active workers, queue depth, task rejection và outcome.

## 10. @Async là proxy — tự gọi trong cùng bean sẽ không chuyển thread

Đây là lỗi phổ biến:

~~~java
@Service
public class InvoiceService {

    public void prepare() {
        sendInBackground(); // self-invocation, không đi qua proxy
    }

    @Async("bizExecutor")
    public void sendInBackground() {
        // Có thể vẫn chạy ngay trên caller thread!
    }
}
~~~

Đoạn trên chỉ minh họa, yêu cầu import và các bean cần thiết. Với `@EnableAsync` ở **proxy mode mặc định**, lời gọi `this.sendInBackground()` hoặc `sendInBackground()` trong chính class không đi qua Spring async interceptor.

Hệ quả:

- Code trông có `@Async` nhưng thực tế có thể xử lý đồng bộ.
- Thread pool đã cấu hình không được dùng.
- Request/scheduler thread có thể bị blocking lâu.
- Tại sao kiểm tra thread name quan trọng? Vì nó giúp xác định proxy đã chuyển việc vào executor chưa.

Cách sửa đáng tin cậy: tách phần async sang **một Spring bean khác** và inject nó, đúng như `ScheduledTrigger` và `AsyncWorker` trong ví dụ mục 6. Không dùng `new AsyncWorker(...)` bằng tay rồi mong annotation hoạt động. Ngoài ra, method class/method quá hạn chế cho proxy (ví dụ final method dưới một số kiểu proxy) có thể không được intercept; nên thiết kế API service có thể proxy được.

## 11. Cùng JVM không có nghĩa cùng thread hoặc cùng transaction

Khi một method chạy sang async worker thread, hãy xem xét những thứ vốn gắn với thread:

| Dữ liệu hoặc cơ chế | Điều cần chú ý |
|---|---|
| `ThreadLocal` tự viết | Không tự sao chép sang worker thread. |
| Logging MDC / trace context | Có thể mất correlation nếu không cấu hình context propagation. |
| Spring SecurityContext | Không được mặc định coi là có trên mọi thread; dùng executor wrapper/context propagation phù hợp. |
| Transaction bound to caller thread | Không tự truyền nguyên transaction context sang worker. |
| Request attributes | Có thể không tồn tại hoặc request đã kết thúc khi task chạy. |
| EntityManager / Hibernate session | Không mặc nhiên thread-safe hoặc còn mở ở worker. |
| Cancellation / interruption | Cần thiết kế riêng, không suy ra mọi việc sẽ lập tức dừng. |

Ví dụ một controller có `@Transactional` gọi `@Async`. Không nên nghĩ thao tác trong worker sẽ dùng **chính transaction đang mở trên request thread**. Nếu job cần transaction, hãy thiết kế transaction boundary thích hợp trong service được worker gọi và xác minh nó chạy qua proxy quản lý transaction hợp lệ.

**Phạm vi exception:** nếu async method trả `CompletableFuture<T>`, kết quả lỗi nằm trong future. Nếu `void`, không có giá trị trả về để caller quan sát; nên cấu hình handler, logging, metrics và alert. Với `@Scheduled` synchronous method ném exception, cách scheduler/error handler xử lý sẽ khác với lỗi bên trong một async task đã được submit; đừng nghĩ scheduler luôn nhìn thấy exception xảy ra ở worker.

## 12. Shutdown: executor và scheduler đều có tài nguyên cần giải phóng

Trong runtime, scheduler có các timer task, còn executor có queue và worker threads. Cả hai cần xử lý đúng khi context đóng hoặc Pod nhận SIGTERM.

Những câu hỏi phải giải quyết:

- Có **dừng nhận task mới** trước khi đóng pool không?
- Những task đang chạy sẽ hoàn tất hay bị yêu cầu hủy?
- Queue đang chờ được xử lý hết, hủy hay lưu sang một queue bền vững?
- Thời gian tối đa chờ shutdown là bao lâu?
- Khi task bị interrupt, code có dọn dẹp tài nguyên và khôi phục interrupt flag đúng không?
- Có task nào đang chờ I/O không có timeout, khiến shutdown kéo dài không?

Trong ví dụ mục 6 có:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(5);

scheduler.setWaitForTasksToCompleteOnShutdown(true);
scheduler.setAwaitTerminationSeconds(5);
~~~

Các lệnh này thể hiện **chính sách chờ** khi shutdown; phải hiểu rằng task có thể kéo dài hơn thời gian chờ và một hệ thống có nhiệm vụ critical cần chính sách bền vững hơn. Khi dùng graceful shutdown của Kubernetes, đồng bộ tổng thời gian cleanup với `terminationGracePeriodSeconds`, readiness transition và timeout từ ingress/load balancer.

Với `@Scheduled` có tần suất cao, shutdown nên ngăn tick mới và không tạo thêm backlog trong lúc executor đang ngừng. Hành vi cancel/interrupt đối với scheduled futures phụ thuộc cấu hình của `TaskScheduler` và phiên bản Spring; đừng suy luận đơn giản rằng “close context = tất cả task vừa chạy sẽ hoàn tất ngay lập tức”.

Nếu job phải chạy **chắc chắn và không mất dữ liệu** khi pod restart, đừng coi in-memory executor queue là nguồn lưu trữ bền vững. Sử dụng message broker, database job table hoặc scheduler bền vững kèm ack/retry/idempotency theo yêu cầu.

## 13. Đo lường tài nguyên và phát hiện nghẽn

Một hệ thống production nên biết:

| Tín hiệu | Phản ánh |
|---|---|
| Active async worker count | Có bao nhiêu worker đang xử lý. |
| Async executor queue size | Backlog và thời gian chờ tiềm tàng. |
| Task rejection count | Pool/queue không nhận thêm được task. |
| Scheduler trigger delay | Lịch được kích hoạt trễ bao nhiêu so với dự kiến. |
| Work duration p50/p95/p99 | Tác vụ có tăng latency hay không. |
| Error/timeout/retry counts | Việc đang thất bại hay retry tạo thêm tải. |
| Thread dump / blocked threads | Deadlock hoặc blocking kéo dài. |
| Heap, GC, CPU, connection pool | Áp lực tài nguyên thực tế trong JVM. |

Micrometer/Actuator có thể tích hợp với một số executor được instrument đúng cách, nhưng **đừng mặc định mọi bean custom tự xuất đầy đủ mọi metric**. Kiểm tra dashboard đang thu thập tín hiệu nào, đăng ký metrics theo tên executor/scheduler và correlation ID khi cần.

Với scheduler, theo dõi **actual start time** của công việc so với scheduled due time có thể quan trọng hơn chỉ nhìn thời điểm gọi method. Với async, theo dõi **queue wait** giúp phân biệt lỗi CPU-bound với lỗi downstream chậm.

### Tách workload theo đặc tính

- Công việc **CPU-bound**: thường không nên dùng số worker lớn hơn nhiều so với số CPU cores nếu không có lý do.
- Công việc **blocking I/O**: có thể cần nhiều concurrency hơn, nhưng phải có timeouts và giới hạn kết nối downstream.
- Công việc **độ ưu tiên thấp**: nên có pool/queue riêng để không chiếm chỗ của request critical.
- Công việc **định kỳ kích hoạt**: method trigger nên nhanh, tránh gọi mạng lâu trên scheduler thread nếu có nhiều lịch quan trọng cùng chia pool.
- Công việc **cần đúng một lần trong cụm**: cần distributed coordination, không chỉ chỉnh số thread của scheduler trong từng Pod.

## 14. Java 21 virtual threads thay đổi điều gì?

Spring Boot 3.3 hỗ trợ `spring.threads.virtual.enabled=true` khi chạy trên **Java 21+**. Khi bật:

- Boot có thể tự cấu hình `SimpleAsyncTaskExecutor` sử dụng **virtual threads** thay cho `ThreadPoolTaskExecutor` thông thường.
- Scheduling có thể dùng `SimpleAsyncTaskScheduler` thay cho `ThreadPoolTaskScheduler`.
- Các property pool size trước đó có thể **không còn áp dụng** như với thread pool platform threads.
- Với `SimpleAsyncTaskScheduler`, các fixed-delay tasks có đặc điểm riêng: tác vụ fixed-delay chạy trên một scheduler thread, vì vậy nên cân nhắc fixed-rate/cron và semantics cụ thể.
- Virtual threads giúp mô hình blocking I/O có khả năng mở rộng ở nhiều trường hợp, nhưng **không** làm CPU, database connection pool, API rate limit hay memory trở nên vô hạn.

Ví dụ cấu hình (chỉ khi chạy Java 21+):

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

`spring.main.keep-alive=true` cần cân nhắc với ứng dụng console chỉ có virtual threads, vì virtual threads là **daemon threads** và không tự giữ JVM sống khi hết các non-daemon threads. Không sao chép cặp property này vào ví dụ Java 17 ở mục 6; ví dụ đó đã tạo pool platform threads tường minh nên mục đích là kiểm chứng sự tách biệt scheduler/executor truyền thống.

**Đặc biệt:** khi tự khai báo `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` như trong ví dụ mục 6, việc chỉ bật property virtual threads **không tự biến các bean custom ấy thành virtual-thread implementations**. Muốn chuyển phải chọn loại executor/scheduler phù hợp và kiểm thử lại hành vi.

## 15. Kiểm thử và bài thực hành

Giữ chương trình ví dụ mục 6, thử từng thay đổi riêng:

1. **In tên thread thật** trong `ScheduledTrigger.tick()` và `AsyncWorker.process()`. Quan sát một thread có prefix `timer-`, thread kia có prefix `jobs-`.
2. **Bỏ `@Async` khỏi `AsyncWorker.process()`**: method sẽ chạy trực tiếp trên scheduler thread. Khi đó dòng “worker uses executor” thành `false` và “different threads” thành `false`.
3. **Bỏ `@EnableAsync`** nhưng giữ annotation `@Async`: quan sát lời gọi không còn được xử lý theo async proxy thông thường.
4. **Bỏ `@EnableScheduling`**: tick không được đăng ký, runner chờ quá 10 giây rồi ném timeout. Đây là ví dụ lỗi có thể kiểm chứng, không phải kỳ vọng startup vẫn thành công.
5. **Cho scheduled method ngủ 3 giây** và thêm một scheduled method khác: quan sát độ trễ khi scheduler pool size chỉ là 1.
6. **Giảm executor queue capacity** và submit nhiều task blocking có kiểm soát: quan sát thời gian chờ và hành vi task rejection. Không chạy stress test không giới hạn trên môi trường dùng chung.
7. **Gọi một `@Async` method bằng self-invocation** trong cùng class rồi so sánh thread name với lời gọi qua một bean khác.
8. **Mô phỏng shutdown** trong khi job đang chạy: xác minh timeout, interrupt, dọn resource và báo cáo những việc chưa hoàn tất.

Khi kiểm thử production behavior, đừng chỉ nhìn có bao nhiêu dòng log. Hãy xác minh ba câu hỏi độc lập: **tick có được kích hoạt đúng lịch? task có được nộp vào executor thành công? task có hoàn tất hoặc thất bại theo hợp đồng không?**

## 16. Những lỗi thiết kế thường gặp

**Lỗi 1 — “@Scheduled chạy trên @Async pool theo mặc định”.**

Sai. Scheduler và executor là hai khái niệm, với cấu hình và tài nguyên khác nhau. Muốn offload hãy gọi worker bean được `@Async` xử lý hoặc submit task vào executor phù hợp.

**Lỗi 2 — “Thêm @Async thì tác vụ không dùng tài nguyên JVM”.**

Sai. Nó vẫn dùng thread, CPU, heap, connection và queue; chỉ chuyển ngữ cảnh thực thi.

**Lỗi 3 — “Pool scheduler một thread vẫn chạy mọi job đúng giờ”.**

Không. Một method blocking có thể làm trễ các tick khác. Cần đo workload và điều chỉnh scheduler pool/thiết kế offload.

**Lỗi 4 — “@Scheduled fixedDelay bảo đảm đợi async worker xong”.**

Không tự động. Nếu scheduled method chỉ submit async task rồi trả về, fixedDelay tính theo thời gian method submit kết thúc, không đợi worker xử lý.

**Lỗi 5 — “Tôi cấu hình spring.task.execution.pool.* nên mọi @Async đều dùng pool đó”.**

Không chắc. Một bean `Executor` tự khai báo, `AsyncConfigurer`, qualifier hoặc context khác có thể thay thế việc chọn executor. Nếu có executor custom, những property auto-config có thể không áp dụng.

**Lỗi 6 — “@Async tự gọi trong cùng class vẫn chạy trên thread khác”.**

Không ở proxy mode mặc định. Tách worker sang bean khác, gọi qua Spring proxy.

**Lỗi 7 — “Queue càng lớn thì càng an toàn”.**

Queue quá lớn có thể tăng latency, giữ nhiều object trong heap và che giấu quá tải. Cần sizing, backpressure, timeout và rejection policy.

**Lỗi 8 — “Cron chỉ chạy một lần trên toàn Kubernetes deployment”.**

Sai. Mỗi replica thường có scheduler riêng. Cần distributed coordination cho job phải chỉ chạy một lần.

**Lỗi 9 — “Transaction/request context tự được truyền sang async thread”.**

Không mặc nhiên. Thread-bound state cần thiết kế context propagation riêng; transaction boundary phải rõ.

**Lỗi 10 — “Đóng context là tất cả task đang chờ đã được lưu bền vững”.**

Không. Executor queue trong bộ nhớ có thể mất khi process chết. Work critical phải có cơ chế lưu trữ, ack và retry phù hợp.

## 17. Checklist trước khi triển khai

- Bật chính xác `@EnableAsync` và `@EnableScheduling` ở nơi cần thiết.
- Biết bean nào đang thực thi mỗi `@Async` (name/qualifier/AsyncConfigurer) và bean nào đang điều phối `@Scheduled`.
- In/quan sát thread name để xác nhận proxy async hoạt động; kiểm tra self-invocation.
- Thiết lập scheduler pool phù hợp và tránh blocking trực tiếp trên tick.
- Thiết lập executor core/max/queue/rejection theo tải và giới hạn downstream.
- Tách job trigger khỏi job processing nếu processing có thể lâu; đồng thời chống backlog tràn và overlap sai.
- Phân biệt fixedRate, fixedDelay, cron và initialDelay bằng test có duration thực.
- Không giả định distributed single execution khi chạy nhiều replica.
- Xử lý exception của `void @Async` và `CompletableFuture`; báo metrics về task failed/rejected.
- Cân nhắc MDC, tracing, security, transaction, request context qua thread boundary.
- Bảo đảm graceful shutdown, timeout, dọn thread/queue và chính sách lưu trữ công việc quan trọng.
- Khi dùng Java 21 virtual threads, xem lại loại executor/scheduler và các property thực sự có hiệu lực.

### Tài liệu chính thức

- Spring Boot 3.3 — *Task Execution and Scheduling*: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Framework 6.1 — *Task Execution and Scheduling*: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 — `@Async` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework 6.1 — `@Scheduled` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html

**Ghi nhớ:** `@Scheduled` quyết định **thời điểm kích hoạt**, `@Async` quyết định **nơi xử lý**. Scheduler thread không tự biến thành async worker thread. Trong Spring Boot, cả hai phụ thuộc vào những **tài nguyên thực thi hữu hạn** được quản lý trong JVM. Thiết kế đúng phải chỉ rõ scheduler nào tạo tick, executor nào xử lý, queue có thể chứa bao nhiêu task, khi quá tải phải làm gì và khi shutdown phải dừng ra sao.
