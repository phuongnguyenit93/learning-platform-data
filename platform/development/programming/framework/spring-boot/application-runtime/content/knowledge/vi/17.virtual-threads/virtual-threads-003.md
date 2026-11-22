# Thành phần dùng executor hoặc scheduler khi bật luồng ảo trong Spring Boot

Khi chạy Spring Boot trên **Java 21+**, bạn có thể bật virtual threads (luồng ảo) bằng cấu hình `spring.threads.virtual.enabled=true`. Thay đổi này không có nghĩa **mọi** thao tác của ứng dụng đột nhiên chạy trong virtual thread. Nó làm Spring Boot **điều chỉnh một số thành phần được auto-configure**, đặc biệt là **task executor** và **task scheduler**. Những component thực sự sử dụng các tài nguyên đó mới hưởng hành vi tương ứng.

Hai ý cần nắm trước tiên:

- **Executor** trả lời câu hỏi *tác vụ sẽ được thực thi ở đâu?* Ví dụ một lời gọi `@Async` có thể được submit tới một `AsyncTaskExecutor`.
- **Scheduler** trả lời câu hỏi *khi nào cần kích hoạt tác vụ?* Ví dụ `@Scheduled` được đăng ký với một `TaskScheduler`, từ đó chạy công việc theo lịch.

Khi bật virtual threads, Spring Boot 3.3 có thể tự tạo **`SimpleAsyncTaskExecutor` sử dụng virtual threads** và **`SimpleAsyncTaskScheduler` sử dụng virtual threads** thay cho những thread pool mặc định thông thường. Nhưng hành vi còn phụ thuộc vào **phiên bản Java, điều kiện auto-configuration, bean do ứng dụng tự khai báo, loại trigger và cách method được gọi**.

Bài học dùng **Spring Boot 3.3.x, Spring Framework 6.1.x và Java 21**. Các phần nói về Java 17 chỉ để đối chiếu khi *chưa thể bật* virtual threads.

## 1. Virtual thread thực sự thay đổi điều gì?

Virtual threads là một tính năng chính thức của Java 21 (JEP 444). Một virtual thread là một `java.lang.Thread` nhẹ hơn platform thread trong nhiều tình huống, đặc biệt với code I/O blocking theo mô hình thread-per-task.

Ví dụ độc lập với Spring, chạy trên Java 21:

~~~java
public class VirtualThreadBasics {
    public static void main(String[] args) throws Exception {
        Thread task = Thread.ofVirtual()
                .name("sample-vt")
                .start(() -> {
                    System.out.println(
                            "inside virtual = "
                                    + Thread.currentThread().isVirtual());
                });
        task.join();

        System.out.println(
                "main virtual = "
                        + Thread.currentThread().isVirtual());
    }
}
~~~

Biên dịch/chạy trong thư mục chứa `VirtualThreadBasics.java`:

~~~bash
javac VirtualThreadBasics.java
java VirtualThreadBasics
~~~

Kết quả:

~~~text
inside virtual = true
main virtual = false
~~~

Virtual thread không loại bỏ nhu cầu dùng CPU, bộ nhớ, socket, database pool hoặc giới hạn kết nối. Nó đặc biệt hữu ích để giảm chi phí giữ **rất nhiều công việc đang chờ I/O** so với việc mỗi tác vụ dùng một platform thread đắt hơn.

**Đừng hiểu là “virtual thread = nhanh hơn mọi tác vụ”.** Một công việc CPU-bound vẫn cần CPU thực; virtual threads không làm tăng số CPU cores. Với giới hạn upstream, nhiều virtual threads thậm chí có thể tạo nhiều lời gọi đồng thời hơn mức dependency chịu được.

Trong Java 21, có những trường hợp virtual thread bị **pin** vào carrier thread khi blocking trong vùng `synchronized` hoặc native code. Điều đó có thể giảm khả năng mở rộng. Vì vậy cần đo workload thực, không thay đổi cấu hình production chỉ dựa vào số lượng thread tạo được.

## 2. Cách bật trong Spring Boot

Với Spring Boot 3.3 trên Java 21+, đặt trong `src/main/resources/application.properties`:

~~~properties
spring.threads.virtual.enabled=true
~~~

Hoặc trong `application.yml`:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Cấu hình này có tác dụng khi **runtime thực sự là Java 21+**. Nếu ứng dụng vẫn chạy trên Java 17, không thể sử dụng virtual threads của JDK bằng cách chỉ đổi một property; cần nâng cấp runtime/JDK tương thích trước.

Để kiểm chứng bản Java:

~~~bash
java -version
~~~

Ngoài ra, trong chương trình Java 21 có thể kiểm tra:

~~~java
System.out.println(Thread.currentThread().isVirtual());
~~~

Nếu dòng trên in `false` trong `main`, **không** có nghĩa feature chưa bật: `main` thường chạy trên platform thread; chỉ những task được đưa vào executor/scheduler có virtual-thread support mới cần chạy trên virtual thread.

### So sánh hai chế độ cấu hình

| Khía cạnh | Không bật virtual threads, thông thường | Bật `spring.threads.virtual.enabled=true` trên Java 21+ |
|---|---|---|
| Executor do Boot tự cấu hình | Thường là `ThreadPoolTaskExecutor` | Thường là `SimpleAsyncTaskExecutor` tạo virtual thread cho task |
| Scheduler do Boot tự cấu hình | Thường là `ThreadPoolTaskScheduler` | Thường là `SimpleAsyncTaskScheduler` hỗ trợ virtual threads |
| `@Async` hợp lệ dùng executor mặc định | Thường chạy trên platform worker pool | Có thể chạy trên virtual thread do Boot executor tạo |
| `@Scheduled` dùng scheduler mặc định | Thường dùng scheduled platform thread pool | Có thể chạy trên virtual threads, **tùy loại trigger** |
| Một `ThreadPoolTaskExecutor` tự khai báo | Vẫn theo cấu hình của chính bean | **Không tự biến** thành virtual-thread executor |
| Một `ThreadPoolTaskScheduler` tự khai báo | Vẫn theo cấu hình của chính bean | **Không tự biến** thành virtual-thread scheduler |
| Thread name / pool size | Phụ thuộc pool được cấu hình | Không được mặc nhiên suy ra cùng cơ chế pool |
| Liveness của JVM | Phụ thuộc non-daemon threads và các thành phần khác | Virtual threads là daemon; cần lưu ý keep-alive |

Bảng mô tả **điều kiện auto-configuration thông thường**, không phải cam kết bất kỳ ứng dụng có mọi loại dependency/custom bean đều nhận đúng hai implementation trên.

## 3. Thành phần nào sử dụng executor?

Executor là nơi thực thi một `Runnable` hoặc `Callable`. Trong hệ Spring, có thể gặp:

- `java.util.concurrent.Executor`: contract JDK để chạy task.
- `org.springframework.core.task.TaskExecutor`: abstraction task execution của Spring.
- `org.springframework.core.task.AsyncTaskExecutor`: mở rộng để nộp tác vụ bất đồng bộ.
- `ThreadPoolTaskExecutor`: Spring adapter cho platform-thread pool có cấu hình core/max/queue.
- `SimpleAsyncTaskExecutor`: tạo thread mới theo từng task, có khả năng dùng **virtual threads** trong Spring Framework 6.1+.

Trong cấu hình mặc định của Boot khi đáp ứng điều kiện, task executor bean có tên **`applicationTaskExecutor`**. Nó có thể được sử dụng bởi các hạ tầng tích hợp task execution như:

1. **`@Async`** khi đã bật `@EnableAsync` và cơ chế chọn executor không bị override.
2. **Spring MVC asynchronous request processing** khi có loại/tên executor phù hợp được MVC nhận diện theo cấu hình.
3. **Một số thành phần framework hoặc code ứng dụng** được chủ động inject đúng `AsyncTaskExecutor` / `TaskExecutor` đó.
4. **Các lời gọi submit task do chính ứng dụng viết** khi sử dụng bean executor được chọn.

Không nên suy rộng rằng tất cả HTTP requests, tất cả Reactor/WebFlux event-loop tasks, mọi `CompletableFuture.supplyAsync(...)` hay mọi thư viện bên thứ ba tự động chuyển sang Boot executor:

- `CompletableFuture.supplyAsync(...)` **không truyền Executor** thường sử dụng common ForkJoinPool, không mặc nhiên dùng `applicationTaskExecutor`.
- `new Thread(...)` tự tạo platform thread nếu bạn không chủ động chọn API virtual thread.
- Một thư viện có executor riêng sẽ tiếp tục dùng executor đó, trừ khi được cấu hình thay thế.
- Luồng xử lý request của embedded server là chủ đề cấu hình container **riêng**, không được đánh đồng với việc Spring MVC dùng `applicationTaskExecutor` cho asynchronous MVC processing.
- Reactive event loop là một cơ chế thực thi khác; bật property virtual threads không biến mọi event loop thành virtual thread.

**Muốn biết thật sự component đang chạy ở đâu, hãy kiểm tra executor đang được inject và `Thread.currentThread().isVirtual()` bên trong task.**

## 4. @Async, @EnableAsync và virtual-thread executor

Ví dụ:

~~~java
@Service
public class MailJob {

    @Async
    public CompletableFuture<String> send(String message) {
        // Khi proxy xử lý @Async, method được submit tới executor.
        return CompletableFuture.completedFuture("sent:" + message);
    }
}
~~~

Đây là đoạn **minh họa** cần import `Service`, `Async`, `CompletableFuture` và bật `@EnableAsync` trong cấu hình Spring.

Điều kiện để hiểu đúng:

1. `@EnableAsync` kích hoạt hạ tầng xử lý `@Async`.
2. Caller phải gọi method **qua Spring proxy** hợp lệ. `this.send(...)` tự gọi bên trong chính bean thông thường **không** bị interceptor `@Async` xử lý ở proxy mode mặc định.
3. Hệ thống phải chọn được executor: bằng `@Async("beanName")`, `AsyncConfigurer`, bean chuyên dụng hoặc executor mặc định theo cấu hình.
4. Nếu executor được chọn là `SimpleAsyncTaskExecutor` đã bật virtual threads, method có thể chạy trên virtual thread.
5. Nếu executor được chọn là `ThreadPoolTaskExecutor` platform thread do bạn tự tạo, method vẫn chạy trên platform thread dù property ảo đang bật.

Ví dụ chọn rõ bean do Boot tự cấu hình (nếu bean đó tồn tại):

~~~java
@Async("applicationTaskExecutor")
public CompletableFuture<Boolean> inspect() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().isVirtual());
}
~~~

Đây là method minh họa trong một Spring bean, không phải chương trình độc lập. Cách này hữu ích khi cần biết chính xác executor nào được dùng. Nhưng nó cũng tạo dependency vào **tên bean**; trong ứng dụng có cấu hình custom, phải kiểm tra bean còn được tạo hay đã bị thay bằng bean khác.

### SimpleAsyncTaskExecutor không phải một pool cố định

Khi dùng virtual threads, `SimpleAsyncTaskExecutor` có mô hình tạo **một thread mới cho mỗi task** thay vì “lấy lại một worker” từ platform-thread pool cố định:

~~~text
Task 1 --> virtual thread 1
Task 2 --> virtual thread 2
Task 3 --> virtual thread 3
...
~~~

Do đó `core-size`, `max-size` và `queue-capacity` là những tham số **thuộc mô hình thread pool**, không tự có cùng ý nghĩa trên `SimpleAsyncTaskExecutor`.

Không đặt `spring.task.execution.pool.max-size=500` rồi kết luận “số virtual threads tối đa là 500”. Khi Boot dùng SimpleAsyncTaskExecutor, các property liên quan pool không điều khiển kiểu bean này theo cách áp dụng cho ThreadPoolTaskExecutor.

Nếu yêu cầu giới hạn concurrency, cần chính sách riêng: `SimpleAsyncTaskExecutor` có cơ chế `setConcurrencyLimit(...)`, hoặc bạn sử dụng semaphore/rate limiter, queue có backpressure hay quota phù hợp với downstream. Một giới hạn concurrency trên executor chưa đủ để quản lý toàn bộ traffic ở cluster.

## 5. Thành phần nào sử dụng scheduler?

Spring scheduling liên quan:

- `org.springframework.scheduling.TaskScheduler`: interface lập lịch cho task.
- `ThreadPoolTaskScheduler`: dùng scheduled platform thread pool thông thường.
- `SimpleAsyncTaskScheduler`: kiểu scheduler tối ưu cho thread-per-task, phù hợp virtual threads.
- `ScheduledAnnotationBeanPostProcessor`: hạ tầng đăng ký các phương thức `@Scheduled` khi đã bật `@EnableScheduling`.

Một method:

~~~java
@Scheduled(fixedRate = 10_000)
public void poll() {
    // Được kích hoạt theo lịch, không phải tự động gọi qua @Async.
}
~~~

Đây là method minh họa trong một Spring bean. Nếu không bật scheduling, chỉ đặt annotation không bảo đảm có trigger.

Khi Boot auto-configure scheduler mặc định và virtual threads được bật, implementation thường là `SimpleAsyncTaskScheduler`. Scheduler vẫn phải **tính toán và lưu lịch**, nhưng có thể dispatch các lần chạy ở virtual threads.

### Chú ý đặc biệt: fixedDelay khác fixedRate/cron

Với `SimpleAsyncTaskScheduler`:

- Các trigger kiểu **fixed-rate** và **cron** được thiết kế thuận lợi cho việc thực hiện tác vụ trên các thread mới, có thể là virtual threads khi tính năng được bật.
- Tác vụ **fixed-delay** có đặc tính khác: nó được thực thi trên **một scheduler thread**, để giữ đúng semantics về khoảng trễ *sau khi lần trước hoàn tất*.
- Vì vậy, **không mặc nhiên tuyên bố “mọi @Scheduled method đều là virtual thread”** khi bật property.

Spring Framework 6.1 khuyến nghị đặc biệt chú ý việc dùng `fixedDelay` với `SimpleAsyncTaskScheduler`. Một fixed-delay task chạy lâu có thể chiếm scheduler thread và làm chậm tác vụ fixed-delay hoặc lịch khác. Nếu workload thích hợp, cân nhắc fixed-rate/cron với giới hạn overlap hoặc thiết kế trigger tách khỏi worker.

So sánh:

| Trigger | Ý nghĩa lịch | Điều cần chú ý ở SimpleAsyncTaskScheduler |
|---|---|---|
| `@Scheduled(fixedRate=...)` | Nhịp theo khoảng giữa thời điểm bắt đầu lịch | Có thể dispatch task trên virtual thread; cần xử lý tác vụ chồng lấn. |
| `@Scheduled(cron="...")` | Kích hoạt theo thời điểm lịch cron | Có thể dispatch task trên virtual thread; phải xét timezone và nhiều replicas. |
| `@Scheduled(fixedDelay=...)` | Chờ một khoảng sau khi lần trước chạy xong | Chạy trên một scheduler thread; không nên chặn quá lâu. |
| `@Scheduled(initialDelay=...)` | Đợi trước lần kích hoạt đầu | Chỉ là tùy chọn thời điểm, không tự quyết định thread type. |

**Lựa chọn fixed-rate không chỉ để “ép virtual thread”.** Nếu mỗi tick làm phát sinh công việc dài và có thể chồng lấn, phải thêm idempotency, concurrency cap, timeout, backpressure và chính sách xử lý khi quá tải.

## 6. Ví dụ Java 21 + Spring Boot 3.3 chạy được và tự kiểm tra thread type

Ví dụ này không khai báo `Executor` hoặc `TaskScheduler` thủ công, để **Spring Boot auto-configuration** có thể chọn implementation phù hợp khi property virtual threads được bật.

Mục tiêu kiểm chứng:

1. `applicationTaskExecutor` là `SimpleAsyncTaskExecutor`.
2. `taskScheduler` là `SimpleAsyncTaskScheduler`.
3. Một method `@Async` chạy trên virtual thread.
4. Một trigger `@Scheduled(fixedRate=...)` chạy trên virtual thread.
5. Một trigger `@Scheduled(fixedDelay=...)` cho thấy đặc điểm chạy trên scheduler thread.

Để tránh sai lầm rằng `main()` thoát quá sớm vì virtual threads là daemon, `ApplicationRunner` chờ ba tác vụ quan sát báo hoàn tất rồi mới cho context đóng.

### Cấu trúc dự án

~~~text
virtual-task-demo/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/virtualtasks/VirtualTaskApplication.java
        └── resources/application.properties
~~~

Tệp `build.gradle`:

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
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.virtualtasks.VirtualTaskApplication'
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
spring.application.name=virtual-task-demo
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
logging.level.root=INFO
~~~

`spring.main.keep-alive=true` không bắt buộc để chạy đúng chương trình demo này vì runner chờ bằng platform main thread; property được đưa vào để minh họa cách cấu hình ứng dụng nền cần tiếp tục tồn tại khi phần lớn công việc chạy bằng daemon virtual threads. Bài học sẽ giải thích kỹ hơn ở phần sau.

Tệp `src/main/java/com/example/virtualtasks/VirtualTaskApplication.java`:

~~~java
package com.example.virtualtasks;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class VirtualTaskApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(VirtualTaskApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner đã đợi ba tác vụ hoàn tất.
        }
    }

    @Bean
    ProbeSignals probeSignals() {
        return new ProbeSignals();
    }

    @Bean
    AsyncWorker asyncWorker(ProbeSignals signals) {
        return new AsyncWorker(signals);
    }

    @Bean
    TickSources tickSources(AsyncWorker worker, ProbeSignals signals) {
        return new TickSources(worker, signals);
    }

    @Bean
    ApplicationRunner report(
            ProbeSignals signals, ApplicationContext context) {
        return args -> {
            if (!signals.completed.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for scheduled/async work");
            }

            Object executor =
                    context.getBean("applicationTaskExecutor");
            Object scheduler =
                    context.getBean("taskScheduler");

            System.out.println(
                    "Executor type = "
                            + executor.getClass().getSimpleName());
            System.out.println(
                    "Scheduler type = "
                            + scheduler.getClass().getSimpleName());
            System.out.println(
                    "@Async virtual = " + signals.asyncVirtual.get());
            System.out.println(
                    "fixedRate virtual = " + signals.rateVirtual.get());
            System.out.println(
                    "fixedDelay virtual = " + signals.delayVirtual.get());
        };
    }

    public static final class ProbeSignals {
        final CountDownLatch completed = new CountDownLatch(3);
        final AtomicReference<Boolean> asyncVirtual =
                new AtomicReference<>();
        final AtomicReference<Boolean> rateVirtual =
                new AtomicReference<>();
        final AtomicReference<Boolean> delayVirtual =
                new AtomicReference<>();
    }

    public static class AsyncWorker {
        private final ProbeSignals signals;

        public AsyncWorker(ProbeSignals signals) {
            this.signals = signals;
        }

        @Async("applicationTaskExecutor")
        public void doWork() {
            signals.asyncVirtual.set(
                    Thread.currentThread().isVirtual());
            signals.completed.countDown();
        }
    }

    public static class TickSources {
        private final AsyncWorker worker;
        private final ProbeSignals signals;

        public TickSources(AsyncWorker worker, ProbeSignals signals) {
            this.worker = worker;
            this.signals = signals;
        }

        @Scheduled(initialDelay = 250, fixedRate = 60000)
        public void fixedRateTick() {
            signals.rateVirtual.set(
                    Thread.currentThread().isVirtual());
            signals.completed.countDown();

            // Đi qua Spring proxy của bean AsyncWorker riêng.
            worker.doWork();
        }

        @Scheduled(initialDelay = 250, fixedDelay = 60000)
        public void fixedDelayTick() {
            signals.delayVirtual.set(
                    Thread.currentThread().isVirtual());
            signals.completed.countDown();
        }
    }
}
~~~

**Tại sao hai bean khác nhau?** `TickSources` gọi `AsyncWorker.doWork()` qua một bean đã được Spring proxy. Nếu `doWork()` nằm trong cùng class và được gọi bằng `this.doWork()`, cơ chế `@Async` theo proxy mode mặc định có thể không chạy; khi đó sẽ không có sự chuyển thread mà ví dụ muốn kiểm chứng.

**Tại sao dùng CountDownLatch(3)?** Runner không cần đoán thời gian scheduling. Hai trigger và một async task mỗi bên báo hoàn tất một lần. Sau khi latch về 0, các giá trị thread type đã được ghi trước đó nên runner có thể đọc chúng an toàn.

**Tại sao không tự khai báo executor/scheduler bean?** Khi project không có bean làm Boot task execution/scheduling auto-configuration back off, việc tự cấu hình có thể chọn đúng các implementation dùng virtual threads. Nếu bạn thêm custom executor vào ví dụ, kết quả sẽ không còn phản ánh đường mặc định này.

### Cách chạy

Cài JDK 21 và dùng Gradle tương thích với Java 21. Trong thư mục dự án có Gradle wrapper, chạy:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu cần đổi JDK cho Gradle, cấu hình Java toolchain trong ví dụ yêu cầu JDK 21 có thể được Gradle tìm thấy. Chạy riêng `javac VirtualTaskApplication.java` không đủ vì code phụ thuộc vào Spring Boot và Spring Framework trên classpath.

Bỏ qua log Spring Boot/Gradle, **stdout của chương trình trong điều kiện auto-configuration đã mô tả** là:

~~~text
Executor type = SimpleAsyncTaskExecutor
Scheduler type = SimpleAsyncTaskScheduler
@Async virtual = true
fixedRate virtual = true
fixedDelay virtual = false
~~~

Thứ tự năm dòng là xác định do chúng được in liên tiếp trong runner **sau khi** cả ba tín hiệu hoàn tất. Thứ tự hai scheduled methods thực sự bắt đầu không cần cố định; latch giúp loại bỏ sự phụ thuộc vào thứ tự đó. Nếu output khác, trước hết kiểm tra version Java/Boot, property có thực sự có hiệu lực, bean `applicationTaskExecutor` và `taskScheduler`, custom bean hoặc proxy configuration trong project.

Lưu ý: dòng `fixedDelay virtual = false` mô tả đặc điểm của `SimpleAsyncTaskScheduler` trong Spring Framework 6.1, khi fixed-delay task thực thi trên scheduler thread thông thường. Nó không phải tuyên bố rằng mọi TaskScheduler hoặc mọi phiên bản JDK đều luôn chạy fixed-delay trên platform thread.

## 7. Khi thêm custom Executor, điều gì xảy ra?

Một ứng dụng thực tế thường đã có thread pool để xử lý email, report, message hoặc các công việc có độ ưu tiên khác nhau.

Ví dụ minh họa **thay đổi hành vi so với chương trình mục 6**:

~~~java
@Bean("reportExecutor")
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("report-platform-");
    return executor;
}
~~~

Đoạn này cần import `ThreadPoolTaskExecutor` và được đặt trong class cấu hình có `@Bean`. Khi bean custom loại `Executor` xuất hiện, điều kiện auto-configuration của Boot có thể **không tạo** executor mặc định như trước. Nếu method được đánh dấu:

~~~java
@Async("reportExecutor")
public void generateReport() {
    System.out.println(Thread.currentThread().isVirtual());
}
~~~

thì nó dùng đúng bean `reportExecutor` bạn chọn. Với `ThreadPoolTaskExecutor` platform threads thông thường ở trên, `isVirtual()` là `false` dù `spring.threads.virtual.enabled=true`.

**Không gọi code này là một “ví dụ độc lập”**: nó là hai mảnh cấu hình/method minh họa, cần đặt vào Spring bean và có `@EnableAsync`, import phù hợp.

Để giữ tự động virtual threads cho một nhóm tác vụ mà vẫn có platform pool riêng cho nhóm khác, cần **tạo các bean rõ ràng, chọn executor bằng qualifier và kiểm tra điều kiện auto-config**. Đừng đoán Boot sẽ vẫn tạo `applicationTaskExecutor` nếu đã có một `Executor` loại khác; hãy kiểm tra bean thực tế trong context.

Một custom `SimpleAsyncTaskExecutor` có thể được cấu hình hỗ trợ virtual threads:

~~~java
@Bean("virtualReportExecutor")
SimpleAsyncTaskExecutor virtualReportExecutor() {
    SimpleAsyncTaskExecutor executor =
            new SimpleAsyncTaskExecutor("report-vt-");
    executor.setVirtualThreads(true);
    executor.setConcurrencyLimit(100);
    return executor;
}
~~~

Đoạn này cũng là cấu hình bổ sung, cần import `SimpleAsyncTaskExecutor` và một Spring configuration class. `setConcurrencyLimit(100)` thể hiện nhu cầu giới hạn **công việc đồng thời**, không tạo một pool 100 platform workers. Khi tự khai báo bean, bạn còn phải kiểm tra lifecycle/shutdown và việc Spring quản lý executor của bạn như thế nào.

**Một nguyên tắc thực dụng:** không trộn ngầm executor của request, executor của batch và executor của event handler. Chọn theo tên, có metrics/timeout/quota riêng, và chỉ bật virtual threads cho workload đã kiểm tra.

## 8. Khi thêm custom TaskScheduler, điều gì xảy ra?

Một project có thể muốn scheduled jobs dùng scheduler riêng:

~~~java
@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler =
            new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-platform-");
    return scheduler;
}
~~~

Đây là method minh họa cần import `ThreadPoolTaskScheduler`. Khi đã có scheduler bean do ứng dụng khai báo, Spring Boot có thể **back off** việc tạo scheduler mặc định sử dụng virtual threads.

Hệ quả: `@Scheduled` dùng scheduler tự khai báo trên sẽ vẫn chạy trên **platform threads** thông thường, trừ khi cấu hình của bạn thực sự chọn một implementation khác. Bật một property chung **không chuyển đổi kiểu object bạn đã tạo trong Java**.

Trường hợp cần chủ động dùng virtual-thread scheduler có thể tự tạo `SimpleAsyncTaskScheduler`, bật virtual threads và quản lý lifecycle tương ứng. Tuy nhiên, nếu Boot đã cung cấp cấu hình phù hợp, bắt đầu bằng **auto-configuration** thường an toàn và ít phức tạp hơn.

### Pool properties không còn mang cùng ý nghĩa

Trong chế độ platform threads, bạn có thể dùng:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.scheduling.pool.size=4
~~~

Những property này chủ yếu hướng đến các implementation dựa trên thread pool. Khi Boot chọn `SimpleAsyncTaskExecutor` và `SimpleAsyncTaskScheduler` cho virtual threads, **đừng mong** `pool.max-size` hay `pool.size` sẽ tạo giới hạn virtual-thread concurrency tương ứng. Và nếu executor/scheduler đã do bạn tự tạo bằng `new`, những property auto-configuration này cũng không mặc nhiên được bind vào bean của bạn.

Kiểm tra **bean type thực tế**, chính sách concurrency và metrics thay vì đọc cấu hình rồi suy luận không có kiểm chứng.

## 9. Web MVC, HTTP server và reactive runtime: tránh suy luận quá rộng

Virtual threads được Boot tích hợp ở nhiều điểm, nhưng các **đường xử lý request** không luôn đi qua cùng một bean:

| Tình huống | Điều cần xác minh |
|---|---|
| `@Async` trên service | Proxy có chạy không? Executor nào được chọn? |
| Spring MVC asynchronous request processing | MVC có sử dụng `applicationTaskExecutor` phù hợp không? |
| HTTP request bình thường qua embedded servlet container | Container phiên bản hiện tại dùng executor/request thread model nào? |
| WebFlux/Reactor event loop | Scheduler/event loop của Reactor có đang được thay thế hay không? Không mặc định giả định có. |
| `CompletableFuture.supplyAsync(...)` không truyền executor | Thường là common ForkJoinPool, không tự dùng Spring executor. |
| `@Scheduled` | TaskScheduler nào được chọn, trigger thuộc fixed-rate, fixed-delay hay cron? |
| Kafka/Rabbit/Quartz hoặc client library khác | Có executor/scheduler riêng hay không? Không tự suy luận đều dùng virtual threads. |

Một request HTTP đang ở platform thread **vẫn có thể gọi** một `@Async` service được chuyển sang virtual thread. Ngược lại, một HTTP server có thể dùng virtual-thread support của chính container nhưng một custom `ThreadPoolTaskExecutor` trong service vẫn dùng platform threads. Không có mâu thuẫn ở đây: **mỗi thành phần có tài nguyên thực thi riêng**.

Nếu cần đánh giá chính xác năng lực của HTTP server, phải xem cấu hình container và Spring Boot version tương ứng. Bài này không coi việc bật virtual threads cho `applicationTaskExecutor` là bằng chứng mọi request handling đều đổi thread type.

## 10. Virtual threads không tự giải quyết blocking downstream

Virtual threads giúp giảm một loại chi phí chờ, nhưng **không** làm các dependency vô hạn.

Giả sử service có 10.000 virtual threads gọi một database chỉ cho phép pool 50 connections. Trong thực tế, tối đa số connection được cung cấp bởi pool vẫn là tài nguyên hữu hạn. Nhiều tác vụ sẽ chờ, timeout hoặc bị từ chối.

Các giới hạn cần quản lý:

- **Database pool:** số connection, queue chờ, timeout, transaction duration.
- **HTTP client:** max connections/streams, upstream rate limit, timeout, retry.
- **CPU:** một tác vụ tính toán nặng vẫn tranh CPU cores.
- **Memory:** task, stack state và dữ liệu giữ trong virtual threads vẫn tiêu thụ heap/native resources.
- **Remote API:** không thể gửi nhiều request hơn quota rồi mong hết lỗi.
- **Scheduler:** quá nhiều scheduled tasks hoặc fixed-delay method blocking vẫn có thể tạo trì hoãn.
- **Hệ thống downstream:** hàng loạt task cùng thức dậy có thể gây “thundering herd”.

Vì vậy khi chuyển sang virtual threads, vẫn phải thiết kế **backpressure**:

~~~text
Request / scheduler tick
        |
        v
Giới hạn nhận việc (semaphore / rate limiter / queue hữu hạn)
        |
        v
Virtual-thread executor
        |
        v
Client / connection pool / dependency
        |
        v
Timeout, retry có kiểm soát, circuit breaker, metrics
~~~

Không đưa mọi tác vụ vào một queue vô hạn rồi chỉ tăng số virtual threads. Với công việc phải sống sót qua restart, cần queue bền vững hoặc job storage riêng, không phải chỉ một in-memory executor.

## 11. Virtual threads và synchronized, pinning trong Java 21

Virtual threads giúp việc chờ I/O của Java code **không chiếm carrier thread** trong nhiều trường hợp. Tuy vậy, trong Java 21, một virtual thread có thể bị **pin** khi thực hiện blocking trong vùng monitor `synchronized` hoặc một số thao tác native/foreign. Khi đó carrier platform thread có thể bị giữ lại trong thời gian virtual thread chờ.

Ví dụ một anti-pattern để suy nghĩ:

~~~java
synchronized (lock) {
    // Một lời gọi I/O có thể block lâu.
    remoteClient.call();
}
~~~

Đây là **mã minh họa** với biến `lock` và `remoteClient` đã tồn tại, không phải chương trình độc lập. Khi chạy trong virtual thread trên Java 21, vùng synchronized kết hợp blocking I/O kéo dài có thể làm hiệu quả virtual threads suy giảm rõ rệt.

Hướng cải thiện:

1. Giữ vùng `synchronized` nhỏ và không chứa I/O blocking.
2. Dùng concurrency primitive phù hợp nếu cần cấu trúc đồng bộ khác; không thay tùy tiện mà không kiểm chứng semantics.
3. Đặt timeout cho I/O và giới hạn công việc đồng thời.
4. Sử dụng Java Flight Recorder/quan sát pinning theo khả năng của JDK/runtime đang chạy.
5. Đo throughput, latency và carrier-thread usage trước/sau chuyển đổi.

Đừng nhầm pinning với deadlock: một task bị pin **không nhất thiết** là deadlock, nhưng có thể làm carrier threads trở nên khan hiếm dưới tải cao. Khả năng xử lý pinning khác nhau theo phiên bản JDK; ở đây tập trung vào Java 21.

## 12. ThreadLocal, MDC, transaction và security context

Virtual thread vẫn là một `Thread`, vì vậy API `ThreadLocal` tồn tại và hoạt động trên virtual threads. Nhưng điều đó **không có nghĩa thread-bound state của caller tự động đi sang một task mới**.

| Nội dung | Điều cần làm rõ |
|---|---|
| `ThreadLocal` | Có trên virtual thread, nhưng state nằm trên từng thread; không tự đồng nhất với caller. |
| MDC/log correlation | Cần cơ chế context propagation hoặc `TaskDecorator` phù hợp nếu cần mang correlation giữa threads. |
| Spring SecurityContext | Xác minh và cấu hình propagation theo framework; không coi worker đã có quyền của request thread. |
| Spring transaction | Transaction gắn với execution context/thread của lời gọi; `@Async` không tự mang transaction đang mở của caller sang worker. |
| Request attributes | Có thể không tồn tại khi task chạy muộn hơn request hoặc ngoài MVC context. |
| Caching và mutable state | Nhiều tác vụ đồng thời có thể tạo race; virtual threads không tự tạo thread-safety. |

Ví dụ, một method `@Transactional` gọi `@Async`. Worker có thể chạy trên một virtual thread **khác thread transaction**. Không được mặc định giả định worker dùng chung transaction đó. Nếu task cần transaction riêng, hãy thiết kế transaction boundary trên service được gọi qua proxy thích hợp.

Tương tự, việc một HTTP request đã hết hạn không tự hủy tất cả virtual-thread tasks mà nó đã submit. Bạn cần cancellation, timeout, tracing và ownership của công việc nền.

## 13. Virtual threads là daemon: vì sao cần keep-alive?

Java virtual threads là **daemon threads**. JVM không nhất thiết giữ process sống chỉ vì còn virtual threads đang chạy. Điều này đặc biệt quan trọng với ứng dụng Spring Boot **không có web server hoặc thành phần non-daemon giữ JVM sống**, nhưng lại chỉ có scheduler/executor dùng virtual threads.

Spring Boot cung cấp:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Khi `spring.main.keep-alive=true`, Spring Boot giữ ứng dụng sống phù hợp với chế độ virtual threads ngay cả khi không còn platform non-daemon threads do các thành phần khác tạo. Với chương trình console batch chỉ cần chạy xong một công việc và kết thúc, giữ process sống vô hạn có thể **không phải** mục tiêu.

Nhớ phân biệt:

- **Server/web app:** request listener/server có thể giữ process sống theo cách riêng; vẫn cần kiểm tra vận hành thực tế.
- **Background-only app:** nếu chỉ còn virtual-thread scheduler, cần nghĩ đến cách giữ JVM sống.
- **Batch app:** nếu mục tiêu là hoàn thành job rồi thoát, nên await completion có timeout và đóng context; không nên bật keep-alive vô điều kiện.

Ví dụ mục 6 cố ý chờ bằng `CountDownLatch` và đóng context khi hoàn tất để biểu diễn điều kiện kết thúc rõ ràng. Trong production, shutdown phải được thiết kế chủ động, không dựa vào tình cờ còn/không còn non-daemon thread.

## 14. Shutdown và lifecycle của executor/scheduler

Bật virtual threads **không** bỏ qua nhu cầu dừng tác vụ:

1. Ngừng nhận task mới.
2. Dừng scheduled trigger hoặc hủy schedule tương ứng.
3. Cho tác vụ đang chạy một thời gian để hoàn tất hoặc yêu cầu cancel/interrupt.
4. Giải phóng connection/client/resource.
5. Đóng context và tuân thủ timeout/grace period của platform.

Một task được nộp cho `SimpleAsyncTaskExecutor` tạo virtual thread mới không giống queue của một `ThreadPoolTaskExecutor`. Vì vậy không thể dựa nguyên xi vào những giả định “worker pool có 8 thread, queue 100 task” để dự đoán shutdown.

`ThreadPoolTaskScheduler` và `SimpleAsyncTaskScheduler` cũng không có cấu trúc nội bộ giống nhau. Với fixed-delay task, phải cân nhắc việc callback chạy dài trên scheduler thread. Với fixed-rate/cron tasks, phải xử lý overlap/cancellation theo hợp đồng nghiệp vụ.

Nếu ứng dụng cần một job **chắc chắn được chạy dù Pod restart**, task executor/scheduler trong JVM không thay thế message broker, durable scheduler hoặc transaction log. Cần xác định rõ lưu trữ, retry, idempotency và phân công ownership của công việc.

## 15. Khi nào nên ưu tiên virtual threads và khi nào nên giữ platform pool?

| Đặc điểm workload | Hướng cân nhắc |
|---|---|
| Nhiều request/task chờ I/O blocking, có giới hạn downstream rõ | Virtual threads thường đáng thử nghiệm. |
| CPU-bound công việc nặng kéo dài | Virtual threads không thêm CPU; cần giới hạn concurrency theo cores. |
| Tác vụ I/O dùng nhiều synchronized blocking trên Java 21 | Đo pinning và cân nhắc refactor trước khi chuyển. |
| Lịch fixed-delay dài, cần tránh giữ scheduler thread | Cân nhắc scheduler khác, fixed-rate/cron phù hợp hoặc offload có kiểm soát. |
| Task cần pool hữu hạn với queue/rejection policy chặt | Thread pool platform hoặc executor tự thiết kế có thể dễ kiểm soát hơn. |
| Công việc ngắn, cần throughput ổn định và ít overhead | Đo benchmark; không nhất thiết virtual threads luôn thắng. |
| Client/downstream đã có concurrency limit rất nhỏ | Virtual threads không tăng capacity phía downstream. |
| Ứng dụng có executor/scheduler custom nhiều nơi | Đánh giá và chuyển **từng bean**; property chung không đủ. |

Một lộ trình an toàn:

1. Nâng JDK lên Java 21+ và giữ Spring Boot version hỗ trợ.
2. Bật `spring.threads.virtual.enabled=true` ở môi trường thử nghiệm.
3. Kiểm tra bean types/threaddump và xác nhận mỗi workload thật sự dùng virtual thread.
4. Đo throughput, latency p95/p99, CPU, heap, GC, downstream connection pool, retry và pinning.
5. Đặt giới hạn concurrency/rate phù hợp.
6. Kiểm tra stop/restart/shutdown, cancellation và tracing.
7. Chỉ triển khai rộng sau khi xác minh lợi ích và rủi ro thực tế.

## 16. Lỗi thường gặp

**Lỗi 1 — “Bật một property, mọi Java thread trong process đều là virtual threads”.**

Sai. Nó thay đổi những integration được Boot hỗ trợ; `main`, thread pool custom, event loop và nhiều thư viện có thể vẫn dùng platform threads.

**Lỗi 2 — “@Async chắc chắn chạy trên virtual thread khi property bật”.**

Không chắc. Phải bật `@EnableAsync`, gọi qua Spring proxy và chọn đúng executor. Custom `ThreadPoolTaskExecutor` vẫn tạo platform workers.

**Lỗi 3 — “Mọi @Scheduled đều chạy trên virtual thread”.**

Sai với mặc định `SimpleAsyncTaskScheduler` ở Java 21: fixed-delay task có đặc điểm chạy trên **scheduler thread**. Cần xét loại trigger.

**Lỗi 4 — “Cấu hình pool.max-size là đã giới hạn virtual threads”.**

Không với `SimpleAsyncTaskExecutor`. Pool properties thuộc mô hình pool; cần concurrency limit/backpressure thích hợp.

**Lỗi 5 — “Dùng CompletableFuture.supplyAsync không truyền executor thì sẽ lấy Boot applicationTaskExecutor”.**

Không mặc định. Nó thường chọn common pool của JDK. Muốn dùng Spring executor, truyền rõ executor tương thích.

**Lỗi 6 — “Đặt @Async trong cùng class và tự gọi là đã chuyển thread”.**

Không ở proxy mode thông thường; self-invocation bỏ qua interceptor.

**Lỗi 7 — “Virtual threads không có ThreadLocal”.**

Sai. Có ThreadLocal; vấn đề là chi phí và propagation của thread-bound state giữa caller và worker.

**Lỗi 8 — “Virtual threads làm kết nối DB và CPU vô hạn”.**

Sai. Tài nguyên downstream vẫn hữu hạn; quá nhiều concurrency có thể gây quá tải hơn trước.

**Lỗi 9 — “Một ứng dụng scheduler-only sẽ sống mãi vì còn virtual threads”.**

Không chắc vì virtual threads là daemon. Cần cân nhắc `spring.main.keep-alive` hoặc chiến lược await rõ ràng.

**Lỗi 10 — “spring.threads.virtual.enabled tự đổi các bean executor/scheduler do tôi viết”.**

Không. Một object `new ThreadPoolTaskExecutor()` vẫn là loại đó, cho tới khi bạn chủ động thay thế nó.

**Lỗi 11 — “Virtual threads giải quyết mọi tình huống synchronized blocking”.**

Không trong Java 21; pinning có thể giảm khả năng mở rộng. Cần quan sát và sửa blocking trong critical sections khi thích hợp.

**Lỗi 12 — “Một @Scheduled cron chỉ chạy một lần trong Kubernetes cluster”.**

Không. Mỗi replica có thể có scheduler riêng. Nếu job cần single execution trong toàn cụm, thiết kế leader election/distributed lock, durable job state và idempotency.

## 17. Bài thực hành tự kiểm chứng

Dựa trên ví dụ mục 6, thử lần lượt:

1. **Tắt `spring.threads.virtual.enabled`** và quan sát bean type/threaddata thay đổi theo mặc định platform-thread của Spring Boot 3.3.
2. **Chỉ bật virtual threads** và kiểm tra `@Async virtual=true`, `fixedRate virtual=true`, `fixedDelay virtual=false` ở điều kiện demo.
3. **Thêm custom `ThreadPoolTaskExecutor` với bean name `applicationTaskExecutor`**, rồi kiểm tra `@Async` còn dùng virtual thread không. Cần lưu ý điều kiện auto-config và tránh khai báo trùng bean.
4. **Thêm custom `ThreadPoolTaskScheduler` tên `taskScheduler`** để so sánh thread type của scheduled methods. Thực hiện trong một lần chạy riêng, không chồng hai bean cùng tên.
5. **Bỏ `@EnableAsync`** và xem lời gọi worker có còn đi qua async interceptor không.
6. **Bỏ `@EnableScheduling`** và xem runner timeout vì không có trigger, từ đó hiểu vai trò hạ tầng scheduling.
7. **Thêm blocking I/O có timeout** vào worker rồi đo concurrency và thời gian phản hồi; không chạy tải vô hạn.
8. **Thử fixed-delay method dài** trên scheduler virtual-aware, quan sát độ trễ của những lịch khác.
9. **Thử ứng dụng không web server, không keep-alive**, so sánh kết thúc JVM với phiên bản có `spring.main.keep-alive=true`; nhớ kiểm soát và đóng process khi test.
10. **Chạy nhiều replicas trong staging**, kiểm tra scheduled job có bị thực thi trùng trên mỗi instance không.

Gợi ý kiểm tra nhanh trong code:

~~~java
System.out.println(
        "Thread = " + Thread.currentThread().getName()
                + ", virtual = "
                + Thread.currentThread().isVirtual());
~~~

Đoạn này là code Java 21 đặt **bên trong chính method đang được kiểm tra**; nếu chỉ chạy trong `main()` hoặc bên ngoài proxy, nó không phản ánh thread của `@Async`/`@Scheduled`.

### Tài liệu tham khảo

- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — SpringApplication và keep-alive: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 — `SimpleAsyncTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html
- Spring Framework 6.1 — `SimpleAsyncTaskScheduler`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html
- OpenJDK — JEP 444 Virtual Threads: https://openjdk.org/jeps/444

**Ghi nhớ:** `spring.threads.virtual.enabled=true` trên Java 21+ cho phép **những thành phần được Spring Boot tự cấu hình** dùng virtual-thread-aware executor và scheduler. `@Async` phụ thuộc vào **executor được chọn**; `@Scheduled` phụ thuộc vào **scheduler và loại trigger** (đặc biệt lưu ý `fixedDelay`). Custom pools, Reactor event loops, các thư viện có executor riêng và transaction/thread-bound state **không tự chuyển đổi**. Muốn vận hành đúng cần kiểm tra bean thực tế, thread type, giới hạn concurrency, tác vụ blocking, keep-alive và chính sách shutdown.
