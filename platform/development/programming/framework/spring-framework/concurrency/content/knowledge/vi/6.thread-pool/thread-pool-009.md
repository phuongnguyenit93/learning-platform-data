# Đặt tên luồng bằng threadNamePrefix hoặc ThreadFactory

## 1. Vì sao cần đặt tên luồng?

Trong ứng dụng Spring có nhiều nguồn công việc chạy đồng thời, tên luồng (**thread name**) là một dấu hiệu chẩn đoán rất hữu ích. Khi đọc log, thread dump hoặc kết quả theo dõi hiệu năng, tên như `http-nio-8080-exec-5`, `order-worker-2`, `report-scheduler-1` giúp người vận hành nhận ra **nhóm tác vụ** và **pool** đang xử lý, thay vì chỉ thấy các tên mặc định kiểu `pool-3-thread-1`.

Tên luồng trả lời câu hỏi **"mã đang chạy trên loại worker nào?"**, nhưng không tự trả lời **"request nào?"**, **"task nào?"**, **"user nào?"** hoặc **"công việc đã thành công hay chưa?"**. Một luồng trong thread pool có thể xử lý nhiều task khác nhau trong suốt vòng đời của nó.

Trong chủ đề **Nhóm luồng** của Spring concurrency, có hai cách đặt tên phổ biến:

- **`setThreadNamePrefix(...)`** trên các executor/scheduler do Spring cung cấp, ví dụ `ThreadPoolTaskExecutor`, `ThreadPoolTaskScheduler`, `SimpleAsyncTaskExecutor`. Đây thường là lựa chọn ngắn gọn khi chỉ cần prefix dễ nhận biết.
- **`ThreadFactory`** của `java.util.concurrent`: cung cấp một chính sách tạo **Thread**. Dùng khi làm việc trực tiếp với JDK ExecutorService/ThreadPoolExecutor hoặc cần tùy chỉnh quá trình tạo thread, như format tên, daemon, priority, uncaught exception handler, hay kết hợp với một runtime đã có factory.

Ví dụ cách đọc log:

~~~text
2026-10-29 09:00:00 INFO  [report-scheduler-1] Trigger report #42
2026-10-29 09:00:00 INFO  [report-worker-2]    Start report #42
2026-10-29 09:00:02 INFO  [report-worker-2]    Complete report #42
~~~

Đây là **log minh họa**, không phải output được đảm bảo tự xuất hiện khi cấu hình tên luồng. Tên `report-scheduler-` cho thấy nguồn thực thi nhiệm vụ lập lịch, còn `report-worker-` cho thấy pool làm công việc nền. Cần có logger hoặc lệnh in thích hợp mới thấy các dòng như trên.

## 2. Cần hiểu Thread, task, executor và ThreadFactory khác nhau thế nào

| Khái niệm | Vai trò | Có giữ tên luồng không? |
| --- | --- | --- |
| `Runnable` / `Callable<T>` | Mô tả một công việc cần thực thi | Không; cùng task có thể được thực thi bởi worker do executor chọn |
| `Thread` | Luồng Java thực hiện mã | Có tên, lấy bằng `Thread.currentThread().getName()` |
| `ThreadFactory` | Tạo đối tượng Thread mới theo yêu cầu của executor | Có thể đặt tên, daemon, priority và các thuộc tính khác lúc tạo |
| `Executor` / `TaskExecutor` | Nhận công việc rồi quyết định cách thực thi | Có thể sử dụng ThreadFactory và tái sử dụng các thread |
| `ThreadPoolTaskExecutor` | Bean Spring quản lý một ThreadPoolExecutor | Có thể đặt `threadNamePrefix` hoặc cấu hình factory |
| `ThreadPoolTaskScheduler` | Bean Spring quản lý ScheduledThreadPoolExecutor | Có thể đặt `threadNamePrefix` cho scheduler threads |

**ThreadFactory tạo thread, không tạo task cho từng lần submit.** Nếu pool đang có worker rảnh thì task mới có thể chạy trên worker cũ mà không gọi `ThreadFactory.newThread(...)` nữa. Vì vậy một task ID không nên được nhét cố định vào tên thread khi tạo, vì tên ấy sẽ tồn tại và có thể bị dùng lại cho task tiếp theo.

Luồng có thể quan sát tên hiện tại:

~~~java
String name = Thread.currentThread().getName();
System.out.println("Thread = " + name);
~~~

Đây chỉ là một mảnh code minh họa. Khi chạy ở các môi trường khác nhau, tên thực tế phụ thuộc runtime và executor.

## 3. Cách 1 — dùng threadNamePrefix trong Spring

### 3.1. Đặt prefix cho ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` là triển khai TaskExecutor phổ biến của Spring. Trong một bean configuration:

~~~java
@Configuration
public class ExecutorConfig {
    @Bean("orderExecutor")
    public ThreadPoolTaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-worker-");
        return executor;
    }
}
~~~

Đoạn trên là **mảnh cấu hình Spring** cần import `@Configuration`, `@Bean`, `ThreadPoolTaskExecutor` và có mặt trong ApplicationContext. Spring gọi lifecycle initialization của bean, do đó thường không cần gọi `initialize()` thủ công khi bean được tạo như trên. Nếu tự `new ThreadPoolTaskExecutor()` **ngoài** container, phải quản lý khởi tạo và shutdown thích hợp.

Khi pool tạo worker, tên được sinh từ prefix và hậu tố chỉ số, ví dụ `order-worker-1`, `order-worker-2`. **Không nên viết nghiệp vụ phụ thuộc chỉ số**: pool có thể tạo thêm/thay worker, và thứ tự các log có thể khác giữa những lần chạy.

Nếu dùng `@Async`:

~~~java
@Service
public class OrderWorker {
    @Async("orderExecutor")
    public CompletableFuture<String> process() {
        String thread = Thread.currentThread().getName();
        return CompletableFuture.completedFuture(thread);
    }
}
~~~

Đây là mảnh code minh họa cần import và `@EnableAsync`. Khi một bean khác gọi method công khai thông qua **Spring proxy**, phần thân `process()` được gửi đến bean `orderExecutor`. Nhờ vậy tên thread thường có prefix `order-worker-`.

Nếu gọi `this.process()` từ chính bean, lời gọi thường **bỏ qua proxy** trong mode mặc định. Khi đó việc quan sát một thread không có prefix **không nhất thiết là lỗi prefix**: trước tiên hãy kiểm tra ranh giới proxy và `@EnableAsync`.

### 3.2. Đặt prefix cho ThreadPoolTaskScheduler

Đối với công việc theo lịch, cấu hình một scheduler riêng:

~~~java
@Bean("taskScheduler")
public ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-");
    return scheduler;
}
~~~

Ví dụ minh họa này cần đặt trong `@Configuration` với import tương ứng. Những method `@Scheduled` thường được kích hoạt bởi TaskScheduler, và `ThreadPoolTaskScheduler` truyền thống chạy callback trên scheduler thread; do đó prefix `schedule-` sẽ giúp nhận ra các lần kích hoạt lịch.

**`TaskScheduler` và `TaskExecutor` không tự chia sẻ cùng một pool.** Nếu method `@Scheduled` chỉ gọi một service `@Async("orderExecutor")` rồi trả về, có thể thấy hai prefix khác nhau trên cùng hành trình nghiệp vụ:

~~~text
schedule-1       -> đến giờ, kích hoạt công việc
order-worker-3   -> thực thi phần xử lý được gửi sang @Async
~~~

Đừng gán `order-worker-` cho scheduler chỉ vì lịch đó tạo ra công việc của nhóm order. Mục tiêu của tên là **phản ánh pool thực sự tạo thread**, từ đó dễ tìm nơi nghẽn.

### 3.3. Prefix áp dụng ở thời điểm tạo thread

`setThreadNamePrefix` định cấu hình cách đặt tên **cho thread mới được tạo**. Cách làm nhất quán là đặt giá trị khi tạo bean, **trước lúc executor/scheduler bắt đầu xử lý task**. Đổi prefix lúc pool đã có worker không bảo đảm đổi tên các worker sẵn có.

Việc đặt tên **không thay đổi** corePoolSize, maxPoolSize, queueCapacity, policy từ chối công việc, khả năng giao dịch hay tính thread-safe của service. Prefix phục vụ quan sát và vận hành, không phải cơ chế bảo vệ chia sẻ dữ liệu.

## 4. Cách 2 — dùng ThreadFactory của Java

`java.util.concurrent.ThreadFactory` là functional interface:

~~~java
@FunctionalInterface
public interface ThreadFactory {
    Thread newThread(Runnable runnable);
}
~~~

Đây là chữ ký interface để giải thích, không cần tự khai báo lại trong chương trình đang dùng JDK. Khi cần tạo worker, một executor thường gọi `newThread(Runnable)`. Factory phải tạo **Thread mới, chưa khởi chạy**, và trả lại cho executor quản lý việc start/execute.

Một implementation thường có ba phần:

1. Một **prefix mô tả chức năng** (`batch-import-`).
2. Một bộ đếm **AtomicInteger** để cấp hậu tố riêng cho những thread do factory này tạo ra.
3. Một factory mặc định hoặc lời gọi `new Thread(task)` để tạo thread, rồi đặt tên trước khi trả về.

Ví dụ độc lập dùng Java 17:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public final class NamedThreadFactory implements ThreadFactory {
    private final ThreadFactory delegate = Executors.defaultThreadFactory();
    private final AtomicInteger sequence = new AtomicInteger();
    private final String prefix;

    public NamedThreadFactory(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }
        this.prefix = prefix;
    }

    @Override
    public Thread newThread(Runnable task) {
        Thread thread = delegate.newThread(task);
        thread.setName(prefix + sequence.incrementAndGet());
        return thread;
    }
}
~~~

Class này **biên dịch được nếu lưu trong `NamedThreadFactory.java`**, nhưng chưa chứa `main()` để chạy độc lập. Khi dùng `Executors.defaultThreadFactory()` làm delegate, ta giữ các đặc tính mặc định của JDK như thread nền tảng (platform thread), non-daemon và priority thông thường, rồi chỉ đổi tên. Trong môi trường container/managed runtime, chính sách thread có thể cần factory được runtime cấp; không tự ý thay đổi daemon hay priority khi chưa hiểu các ràng buộc.

Sử dụng với JDK ExecutorService:

~~~java
ExecutorService executor =
        Executors.newFixedThreadPool(3, new NamedThreadFactory("batch-import-"));

try {
    Future<String> result =
            executor.submit(() -> Thread.currentThread().getName());
    System.out.println(result.get());
} finally {
    executor.shutdown();
}
~~~

Mảnh code trên cần các import `java.util.concurrent.*` và class `NamedThreadFactory` trước đó. Tên có thể là `batch-import-1`, nhưng không được dựa vào con số cụ thể vì thời điểm khởi tạo/reuse worker có thể thay đổi.

### 4.1. ThreadFactory có thể làm nhiều hơn đặt tên

Một ThreadFactory tùy chỉnh có thể gán:

- **Tên** qua `Thread.setName(...)`.
- **Daemon status** qua `Thread.setDaemon(...)` trước khi start.
- **Priority** qua `Thread.setPriority(...)` nếu cần và runtime cho phép.
- **UncaughtExceptionHandler** qua `Thread.setUncaughtExceptionHandler(...)` cho exception không được bắt ở ranh giới Thread.
- **ThreadGroup** hoặc đặc tính thread khác khi thực sự có nhu cầu.

Nhưng các hành vi này có tác động vận hành: daemon thread không ngăn JVM kết thúc; priority là **gợi ý** cho scheduler, không phải SLA; exception của task gửi qua `submit()` thường được ghi trong `Future` thay vì luôn đi tới handler ở mức Thread. Vì vậy **đừng dùng UncaughtExceptionHandler như cách duy nhất quan sát lỗi async task**.

### 4.2. Dùng Spring CustomizableThreadFactory

Spring cũng cung cấp `org.springframework.scheduling.concurrent.CustomizableThreadFactory`, là một implementation của ThreadFactory với các tùy chọn từ `CustomizableThreadCreator`:

~~~java
ThreadFactory factory =
        new CustomizableThreadFactory("archive-");

ExecutorService executor = Executors.newFixedThreadPool(2, factory);
~~~

Đây là mảnh code cần import tương ứng và đóng executor khi không dùng nữa. Lựa chọn này phù hợp nếu muốn đặt prefix dễ dàng ngay cả khi đang tạo một JDK ExecutorService, nhưng đã dùng Spring Framework làm dependency.

### 4.3. Cấp ThreadFactory cho executor Spring

Các executor thuộc họ `ExecutorConfigurationSupport` như `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` trong Spring 6.1 cho phép cấu hình **`setThreadFactory(ThreadFactory)`**:

~~~java
@Bean("batchExecutor")
ThreadPoolTaskExecutor batchExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadFactory(new CustomizableThreadFactory("batch-"));
    return executor;
}
~~~

Đây là mảnh cấu hình cần khai báo trong class `@Configuration`, cùng các import. **Khi đã cấp một ThreadFactory riêng, factory ấy chịu trách nhiệm cách tạo/đặt tên thread.** Đừng kỳ vọng `setThreadNamePrefix` trên executor tự động được ghép tiếp với một custom factory bất kỳ. Nếu chỉ cần đổi tên, ưu tiên cấu hình `setThreadNamePrefix` và tránh thêm tầng factory không cần thiết.

## 5. So sánh trực tiếp: threadNamePrefix và ThreadFactory

| Tiêu chí | `setThreadNamePrefix("order-")` | `ThreadFactory` tùy chỉnh |
| --- | --- | --- |
| Mức abstraction | Thuộc cấu hình executor/scheduler Spring | Chính sách tạo thread của Java |
| Độ phức tạp | Rất ít mã; thường chỉ một setter | Cần implementation/lambda và quản lý các thuộc tính thread |
| Mục tiêu chính | Dễ nhận diện worker theo pool | Kiểm soát chi tiết khi một Thread mới được tạo |
| Áp dụng cho | Những implementation Spring có setter tương ứng | JDK executors, hoặc Spring executors hỗ trợ custom factory |
| Suffix chỉ số | Do triển khai Spring tạo theo quy tắc nội bộ | Do chính factory định nghĩa; nên dùng counter an toàn đồng thời |
| Tùy chỉnh daemon/priority/handler | Có thể dùng API khác tùy implementation; prefix chỉ đổi tên | Có thể thực hiện trực tiếp trong factory |
| Phù hợp nhất | App Spring, yêu cầu quan sát theo chức năng | Kết hợp JDK executor, yêu cầu đặt tên đặc thù hoặc môi trường có factory riêng |

Có thể xem `threadNamePrefix` là **cấu hình tiện lợi** cho một phần nhu cầu mà ThreadFactory tổng quát hơn đáp ứng. Hai cách đều đặt tên cho **thread**, không đặt tên cho mỗi **task**.

## 6. Ví dụ hoàn chỉnh: Spring TaskExecutor, @Async, TaskScheduler và JDK ThreadFactory

Bài tập dùng **Java 17+, Spring Framework 6.1.14, Gradle 8.5+**. Nó in những phép kiểm tra boolean để output có thể dự đoán chính xác, thay vì phụ thuộc chỉ số worker ngẫu nhiên.

Cấu trúc:

~~~text
thread-naming-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ThreadNamingDemo.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'thread-naming-demo'
~~~

### build.gradle

~~~groovy
plugins {
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
}

application {
    mainClass = 'demo.ThreadNamingDemo'
}
~~~

### src/main/java/demo/ThreadNamingDemo.java

~~~java
package demo;

import java.time.Instant;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public final class ThreadNamingDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // 1. TaskExecutor do Spring quản lý.
            var orderExecutor = context.getBean(
                    "orderExecutor", ThreadPoolTaskExecutor.class);
            String directName = orderExecutor.submit(
                    () -> Thread.currentThread().getName())
                    .get(5, TimeUnit.SECONDS);
            System.out.println("Spring TaskExecutor: " +
                    directName.startsWith("order-"));

            // 2. @Async gọi qua proxy của Spring.
            String asyncName = context.getBean(Worker.class)
                    .process().get(5, TimeUnit.SECONDS);
            System.out.println("Spring @Async: " +
                    asyncName.startsWith("order-"));

            // 3. ThreadPoolTaskScheduler dùng prefix riêng.
            var scheduler = context.getBean(
                    "taskScheduler", ThreadPoolTaskScheduler.class);
            var scheduledName = new CompletableFuture<String>();
            scheduler.schedule(
                    () -> scheduledName.complete(
                            Thread.currentThread().getName()),
                    Instant.now().plusMillis(50));
            String actualSchedulerName =
                    scheduledName.get(5, TimeUnit.SECONDS);
            System.out.println("Spring TaskScheduler: " +
                    actualSchedulerName.startsWith("schedule-"));

            // 4. JDK ExecutorService dùng ThreadFactory riêng.
            ExecutorService jdkPool = Executors.newFixedThreadPool(
                    2, new NamedFactory("import-"));
            try {
                String jdkName = jdkPool.submit(
                        () -> Thread.currentThread().getName())
                        .get(5, TimeUnit.SECONDS);
                System.out.println("JDK ThreadFactory: " +
                        jdkName.startsWith("import-"));
            } finally {
                jdkPool.shutdown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("orderExecutor")
        public ThreadPoolTaskExecutor orderExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("order-");
            return executor;
        }

        @Bean("taskScheduler")
        public ThreadPoolTaskScheduler taskScheduler() {
            ThreadPoolTaskScheduler scheduler =
                    new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(1);
            scheduler.setThreadNamePrefix("schedule-");
            return scheduler;
        }

        @Bean
        public Worker worker() {
            return new Worker();
        }
    }

    public static class Worker {
        @Async("orderExecutor")
        public CompletableFuture<String> process() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }
    }

    public static final class NamedFactory implements ThreadFactory {
        private final ThreadFactory delegate =
                Executors.defaultThreadFactory();
        private final AtomicInteger count = new AtomicInteger();
        private final String prefix;

        public NamedFactory(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public Thread newThread(Runnable task) {
            Thread thread = delegate.newThread(task);
            thread.setName(prefix + count.incrementAndGet());
            return thread;
        }
    }
}
~~~

Để chạy từ thư mục `thread-naming-demo`:

~~~bash
gradle run
~~~

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Với điều kiện các task được chấp nhận và hoàn thành trước timeout năm giây, **bốn dòng do chương trình tự in** là:

~~~text
Spring TaskExecutor: true
Spring @Async: true
Spring TaskScheduler: true
JDK ThreadFactory: true
~~~

Log khởi động của Spring/Gradle có thể xuất hiện ngoài bốn dòng trên. Tên thread thực tế có hậu tố khác nhau nên ví dụ chỉ xác minh prefix. Nếu thiếu dependency, môi trường quá tải, task bị từ chối hoặc timeout, chương trình có thể báo lỗi thay vì in đủ bốn dòng; đó là tình huống vận hành cần kiểm tra.

Giải thích:

1. `orderExecutor.submit(...)` gửi một Callable tới pool của Spring. Tên thực thi bắt đầu bằng `order-`.
2. `Worker.process()` được gọi qua bean do Spring quản lý; `@EnableAsync` và `@Async("orderExecutor")` đưa phần thân method sang chính pool đó. Nếu gọi method bằng `this.process()` nội bộ, proxy thường không hoạt động.
3. `ThreadPoolTaskScheduler.schedule(...)` kích hoạt callback trên worker riêng có prefix `schedule-`.
4. `Executors.newFixedThreadPool(..., new NamedFactory("import-"))` yêu cầu factory cấp thread mới khi pool cần worker. Factory đặt tên `import-1`, `import-2`, ... theo bộ đếm riêng.
5. `Future.get` và `CompletableFuture.get` được dùng có chủ đích để **demo** đợi kết quả trước khi in. Trong nghiệp vụ thật, không nên đợi ngay tại caller nếu mục tiêu là xử lý bất đồng bộ mà không block.
6. `try` đóng `AnnotationConfigApplicationContext` giúp Spring xử lý vòng đời các bean executor/scheduler; `finally` gọi shutdown cho pool JDK được tạo thủ công.

## 7. Cấu hình tên luồng qua Spring Boot application.yml

Nếu dùng Spring Boot và để Boot tự cấu hình task executor/scheduler theo cơ chế auto-configuration, các property sau thường được dùng:

~~~yaml
spring:
  task:
    execution:
      thread-name-prefix: "app-async-"
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 100
    scheduling:
      thread-name-prefix: "app-schedule-"
      pool:
        size: 2
~~~

Đây là **cấu hình Spring Boot**; project Spring Framework thuần ở mục 6 không tự đọc những property này. Nó áp dụng cho các bean do cơ chế auto-configuration tương ứng tạo ra. Khi bạn **tự khai báo** `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler`, đừng mặc định các property Boot sẽ tự chỉnh tên/size của mọi bean tùy chỉnh.

Trong ứng dụng có nhiều executors, có thể chọn tên theo chức năng ở từng bean:

~~~java
@Async("invoiceExecutor")
public CompletableFuture<Void> generateInvoice() {
    // Sử dụng pool invoiceExecutor đã được cấu hình.
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là đoạn minh họa method, cần nằm trong Spring bean, có @EnableAsync, executor tương ứng và import. Tên bean `invoiceExecutor` dùng để **chọn pool**; tên thread thực tế dựa vào ThreadFactory/prefix của pool. **Tên bean và threadNamePrefix là hai cấu hình khác nhau**. Việc có bean tên `invoiceExecutor` không bảo đảm log xuất hiện `invoice-` nếu chưa kiểm tra factory.

Ngoài ra, trong Spring Boot quy tắc chọn executor mặc định cho `@Async`, Spring MVC, WebFlux và các tích hợp khác có thể phụ thuộc tên bean như `applicationTaskExecutor`, kiểu `AsyncTaskExecutor` và số bean trong context. Nếu cần biết chính xác pool nào chạy một method, hãy kiểm tra cả **đường gọi** và **cấu hình chọn bean**, thay vì chỉ đổi prefix của một pool không được sử dụng.

## 8. Đặt tên có ích cho log, thread dump và giám sát

### 8.1. Chọn một quy ước dễ đọc

Một format thực tế là:

~~~text
<domain-or-component>-<role>-<thread-sequence>
~~~

Ví dụ: `payment-io-3`, `billing-async-7`, `cleanup-schedule-1`.

Nên chọn prefix:

- **Ngắn, rõ vai trò**: `order-async-`, `report-schedule-`, `sync-worker-`.
- **Phân biệt pool**: khi có `@Async` và scheduler, đừng dùng cùng một prefix gây nhầm.
- **Ổn định trong một phiên bản ứng dụng**: nếu tên log đổi thường xuyên, dashboard hoặc bộ lọc thread dump sẽ khó sử dụng.
- **Không chứa dữ liệu nhạy cảm**: không nhúng email, access token, user id, session id hoặc payload vào tên thread. Thread được tái sử dụng và tên có thể bị log/thread dump lưu lại.
- **Không lệ thuộc vào hậu tố**: số đếm chỉ giúp phân biệt worker tại thời điểm quan sát, không phải khóa nghiệp vụ hay ID toàn cục.

Nếu chạy nhiều JVM/pod, hai thread ở hai instance có thể cùng tên `order-1`. Hãy dùng **service/instance/pod ID** ở trường log hoặc nhãn metrics thích hợp; không suy ra uniqueness trên toàn cluster từ threadNamePrefix.

### 8.2. Hiển thị tên thread trong log

Với Logback, pattern thường dùng `%thread` hoặc `%t` để hiển thị tên thread. Ví dụ một pattern minh họa:

~~~text
%d{HH:mm:ss.SSS} [%thread] %-5level %logger{30} - %msg%n
~~~

Khi một worker có tên `order-2`, dòng log có thể trông như:

~~~text
09:15:23.142 [order-2] INFO  OrderProcessor - Completed order
~~~

Tên worker chỉ nói **thread nào đang chạy**, không phải order nào. Để nối các log của một request/task, cần một **correlation ID**, trace/span ID hoặc MDC ở trường phù hợp. Khi chuyển sang `@Async`, MDC/ThreadLocal **không mặc nhiên lan truyền** sang thread mới; có thể cấu hình `TaskDecorator`, cơ chế context propagation của Spring/Micrometer hoặc wrapper thích hợp, đồng thời bảo đảm cleanup trên thread pool.

### 8.3. Kiểm tra trực tiếp trong chương trình

Trong một method được gọi bởi worker:

~~~java
System.out.printf("thread=%s%n",
        Thread.currentThread().getName());
~~~

Đây là cách xác nhận nhanh pool đang thực thi. Với hệ thống đang chạy, dùng thread dump (`jcmd <pid> Thread.print` trên JDK hỗ trợ) hoặc công cụ quan sát JVM để tìm thread theo prefix. Nếu một thread có tên `report-scheduler-1` bị block trong I/O lâu, điều đó gợi ý scheduler callback đang chiếm thời gian; nếu `report-worker-*` đều bận, xem xét backlog và concurrency của executor.

**Không nên để nghiệp vụ rẽ nhánh theo tên thread**, ví dụ `if (getName().startsWith("order-"))` để phân quyền, kiểm tra đã chạy async hay quyết định được phép truy cập database. Tên có thể đổi bằng cấu hình hoặc do thư viện tạo; nó không phải hợp đồng bảo mật.

## 9. Những lỗi triển khai dễ gặp

### 9.1. Đổi tên thread bằng Thread.currentThread().setName(...) ngay trong task

Ví dụ dễ gây sai lệch quan sát:

~~~java
executor.execute(() -> {
    Thread.currentThread().setName("processing-order-42");
    processOrder();
});
~~~

Đây là mảnh minh họa cần executor và method `processOrder()` được định nghĩa. Nếu worker được pool tái sử dụng và code không khôi phục tên ban đầu, **task tiếp theo có thể chạy trên thread vẫn mang tên order-42**. Log sẽ dẫn tới kết luận sai.

Nếu một yêu cầu đặc biệt thật sự cần đổi tên tạm thời, phải lưu tên cũ và khôi phục trong `finally`:

~~~java
String previous = Thread.currentThread().getName();
try {
    Thread.currentThread().setName(previous + "-temporary");
    // Công việc cần gắn nhãn tạm thời.
} finally {
    Thread.currentThread().setName(previous);
}
~~~

Tuy nhiên, thường tốt hơn dùng MDC/structured logging để ghi task ID và giữ thread name phản ánh **pool**. Đừng thay đổi tên worker vô cớ trong code nghiệp vụ.

### 9.2. Tạo ThreadFactory trả về cùng một Thread

Factory phải tạo **Thread mới** khi được yêu cầu. Trả về cùng một instance cho nhiều lần gọi có thể dẫn đến lỗi kiểu `IllegalThreadStateException` hoặc executor không khởi chạy được worker mới. Không tự `start()` bên trong `newThread()`: executor chịu trách nhiệm lúc bắt đầu chạy.

Không tạo một `new Thread(...)` cho mỗi request chỉ để đặt tên nếu nhiệm vụ thực tế cần **giới hạn concurrency, queue, lifecycle và shutdown**. Hãy dùng executor được cấu hình đúng.

### 9.3. Bộ đếm đặt tên không thread-safe

Trong ThreadFactory có thể dùng `AtomicInteger.incrementAndGet()` hoặc cơ chế đồng bộ tương đương. Dùng `int next++` không được bảo vệ có thể tạo tên trùng nếu factory bị nhiều thread gọi đồng thời. Tên trùng không nhất thiết làm executor hỏng, nhưng mất giá trị quan sát và dễ gây hiểu nhầm.

Cũng không suy ra chỉ vì tên luồng có hậu tố tăng liên tục thì task luôn được chạy đúng thứ tự gửi. Pool nhiều worker có thể hoàn thành không theo thứ tự.

### 9.4. Dùng prefix nhưng không kiểm tra đúng executor

Có thể đã cấu hình `batchExecutor.setThreadNamePrefix("batch-")`, nhưng method thực tế chạy bằng common pool, executor khác, hoặc scheduler. Ví dụ `CompletableFuture.supplyAsync(...)` không truyền executor thường dùng `ForkJoinPool.commonPool()`, không tự lấy Spring TaskExecutor của ứng dụng. Muốn dùng pool của bạn, **truyền executor rõ ràng**:

~~~java
CompletableFuture<String> future = CompletableFuture.supplyAsync(
        () -> Thread.currentThread().getName(),
        batchExecutor);
~~~

Đây là đoạn minh họa cần có `batchExecutor` tương thích `Executor`. Với `@Async`, dùng qualifier trên annotation và bảo đảm lời gọi qua proxy. Với `@Scheduled`, kiểm tra TaskScheduler được chọn. Với MVC Callable, Spring Batch hay Integration, kiểm tra điểm tích hợp riêng thay vì dựa vào một tên bean đoán trước.

### 9.5. Nhầm vấn đề naming với vấn đề concurrency

Một worker tên `single-` **không có nghĩa** pool chỉ có một thread; phải kiểm tra thực tế pool size. Prefix `priority-high-` cũng không tự nâng OS priority. Việc đặt tên không giải quyết race condition, starvation, task rejection, memory pressure hay transaction propagation.

Các thay đổi daemon/priority/uncaught handler qua ThreadFactory nên có lý do rõ ràng và kiểm thử, đặc biệt khi Spring quản lý lifecycle của pool.

## 10. Virtual threads và managed execution: lưu ý riêng

**JDK 17** trong ví dụ sử dụng platform threads. Trên **JDK 21+**, có thể dùng virtual threads và các cách tạo thread tương ứng; Spring Framework/Spring Boot phiên bản phù hợp cũng có lựa chọn hỗ trợ virtual threads. Các API tạo/factory và cơ chế quản lý concurrency ở môi trường virtual-thread có thể khác pool platform threads truyền thống. Không nên suy luận rằng mỗi virtual thread đều phải có một worker được tái sử dụng giống ThreadPoolExecutor.

Khi chọn tên cho virtual threads, vẫn phải cân nhắc correlation ID và observability: số lượng virtual threads có thể rất lớn; đặt một giá trị mang dữ liệu request vào tên thread không phải cách đáng tin để gắn kết toàn bộ log. Nếu một application server hoặc Jakarta EE container **quản lý việc tạo thread**, nên dùng managed executor/thread factory do môi trường cung cấp theo contract của nó, tránh tự tạo thread làm lệch lifecycle, context và chính sách vận hành.

Trong một ứng dụng có nhiều runtime, hãy xác định chính xác **ai sở hữu thread** trước khi chọn cấu hình tên. Đổi tên pool không đồng nghĩa sửa được cách thực thi của runtime khác.

## 11. Cách chọn giải pháp và checklist kiểm tra

**Chỉ cần log phân biệt các pool Spring:** ưu tiên `setThreadNamePrefix` trong bean `ThreadPoolTaskExecutor` hoặc `ThreadPoolTaskScheduler` (hoặc property Spring Boot khi dùng auto-configuration).

**Dùng một JDK ExecutorService riêng:** cung cấp `ThreadFactory` khi tạo pool qua `Executors.newFixedThreadPool(..., factory)` hoặc constructor thích hợp của `ThreadPoolExecutor`.

**Cần tên hoặc chính sách tạo thread đặc thù:** dùng ThreadFactory tùy chỉnh, ưu tiên delegate từ factory mặc định/managed factory phù hợp, chỉ thay những thuộc tính cần thiết. Với Spring executor hỗ trợ `setThreadFactory`, factory được cung cấp sẽ quyết định tên và thuộc tính thread.

Khi triển khai, kiểm tra lần lượt:

1. **Pool thực thi thật sự**: dòng code nào gửi task, bằng execute/submit, @Async proxy hay scheduler?
2. **Chỗ cấu hình có hiệu lực**: bean có được Spring tạo/khởi tạo không? Boot property có đang tác động đến auto-configured bean đúng không?
3. **Tên quan sát được**: log hoặc `Thread.currentThread().getName()` có prefix dự kiến không?
4. **Tính nhất quán**: các pool khác nhau có tiền tố đủ phân biệt; không mã hóa request/user ID vào tên worker.
5. **Điều kiện quá tải**: queue, core/max threads và chính sách rejection có phù hợp throughput không?
6. **Vòng đời**: executor do Spring quản lý hay do ứng dụng tự tạo, ai chịu trách nhiệm shutdown?
7. **Giám sát**: thread naming hỗ trợ đọc log/dump, nhưng metrics, trace ID và context propagation vẫn cần cấu hình riêng.

## 12. Câu hỏi tự kiểm tra

1. Vì sao hai lần `executor.submit(...)` có thể in cùng một thread name? **Vì pool tái sử dụng worker để chạy nhiều task.**
2. Một TaskExecutor đã có tên bean `paymentExecutor`, có chắc các worker bắt đầu bằng `payment-`? **Không; cần kiểm tra threadNamePrefix hoặc ThreadFactory thực tế.**
3. `setThreadNamePrefix("batch-")` có buộc pool tạo thread mới cho mỗi task không? **Không; chỉ ảnh hưởng tên thread được tạo, pool vẫn có thể tái sử dụng worker.**
4. Khi nào chọn ThreadFactory tùy chỉnh? **Khi dùng JDK executor hoặc cần chính sách tạo thread vượt quá prefix đơn giản.**
5. Vì sao không đổi tên worker thành order ID rồi để nguyên? **Task tiếp theo có thể tái sử dụng cùng worker và kế thừa tên gây nhầm.**
6. Nếu method `@Async("mailExecutor")` vẫn in tên HTTP thread, cần kiểm tra gì trước? **@EnableAsync, bean được Spring quản lý, self-invocation/proxy và executor thực tế.**
7. `@Scheduled` với `ThreadPoolTaskScheduler` có tự dùng prefix của `ThreadPoolTaskExecutor` không? **Không; scheduler được cấu hình/chọn riêng.**
8. Tên `worker-1` có duy nhất trên nhiều pod không? **Không; cần thêm instance/pod ID ở dữ liệu observability.**

**Ghi nhớ:** `threadNamePrefix` là cách cấu hình ngắn gọn cho các executor Spring; `ThreadFactory` là cơ chế tổng quát của Java để tạo và đặt tên thread. Cả hai phục vụ nhận diện **luồng thực thi**, còn định danh **công việc** nên được truyền/ghi nhận qua tham số, MDC, trace hoặc log có cấu trúc.

### Tài liệu chính thức

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework — CustomizableThreadFactory API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/CustomizableThreadFactory.html)
- [Java 17 — ThreadFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html)
- [Java 17 — Executors API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
