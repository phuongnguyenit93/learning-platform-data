# Công việc bất đồng bộ do runner tạo không tự được chờ đến khi hoàn tất

Khi một ứng dụng Spring Boot khởi động, `ApplicationRunner` và `CommandLineRunner` là hai điểm mở rộng để thực hiện logic **sau khi ApplicationContext đã refresh** nhưng **trước khi quá trình khởi động bình thường được coi là hoàn tất**. Spring Boot gọi và chờ **phương thức `run(...)` của từng runner trả về**. Tuy nhiên, nếu runner chỉ gửi một công việc vào executor, khởi chạy một `CompletableFuture`, gọi một phương thức `@Async` hoặc tạo thread riêng rồi trả về ngay, Spring Boot **không mặc nhiên đợi công việc bất đồng bộ đó kết thúc**.

Đây là khác biệt rất quan trọng:

- **Runner kết thúc**: phương thức `run(...)` đã trả về, không còn chạy đồng bộ trên luồng gọi runner.
- **Công việc bất đồng bộ kết thúc**: thread hoặc task được runner khởi chạy đã thực hiện xong, xử lý kết quả/lỗi và giải phóng tài nguyên cần thiết.
- **Ứng dụng được báo ready**: Spring Boot đã đi qua các bước khởi động thông thường, bao gồm việc gọi runners; mặc định điều này **không bảo đảm** công việc chạy nền do runners khởi tạo đã hoàn tất.

Nếu một công việc chạy nền thực chất là **điều kiện bắt buộc** để dịch vụ nhận traffic an toàn, bạn phải thiết kế việc chờ, trạng thái readiness hoặc cơ chế phối hợp riêng. Không nên coi `ApplicationReadyEvent` là tín hiệu mọi task bất đồng bộ đã xong.

## 1. Runner nằm ở đâu trong chuỗi khởi động?

Spring Boot hỗ trợ hai interface thông dụng:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Hai interface đều có phương thức tên `run`, nhưng `ApplicationRunner` nhận đối tượng `ApplicationArguments` đã phân tích tham số, còn `CommandLineRunner` nhận mảng các chuỗi command-line ban đầu.

Sau khi context refresh thành công, Boot lần lượt xử lý các mốc chính:

~~~mermaid
flowchart TD
    A["SpringApplication.run(args)"] --> B["Tạo và refresh ApplicationContext"]
    B --> C["ApplicationStartedEvent"]
    C --> D["Gọi các ApplicationRunner và CommandLineRunner"]
    D --> E{"Runner trả về hay ném lỗi?"}
    E -->|"Trả về"| F["Tiếp tục runner khác nếu có"]
    F --> G["ApplicationReadyEvent"]
    G --> H["SpringApplication.run trả về context"]
    E -->|"Ném lỗi chưa xử lý"| I["Xử lý startup failure"]
    D -.-> J["Runner gửi task vào executor"]
    J -.-> K["Task chạy trên luồng khác"]
    K -.-> L["Task kết thúc hoặc thất bại về sau"]
~~~

Đường nét đứt là nhánh task bất đồng bộ: Spring Boot **không tự nối** nhánh đó vào điều kiện để bước `ApplicationReadyEvent` được phát. Nếu `runner.run(...)` ném exception đồng bộ, startup có thể thất bại. Nhưng nếu exception xảy ra **sau khi runner đã trả về**, trong một task chạy nền, lỗi đó không tự biến thành exception của `SpringApplication.run(...)`.

Bước `ApplicationReadyEvent` đánh dấu Boot đã hoàn tất luồng startup bình thường và các runners đã trả về. Readiness state mặc định còn được Boot cập nhật theo lifecycle của nó. Không có bảo đảm mặc định rằng mọi tác vụ mà runners tạo ra đều được đợi tới cuối.

## 2. Phân biệt lời gọi đồng bộ và bất đồng bộ

**Runner đồng bộ:**

~~~java
@Bean
ApplicationRunner synchronousRunner() {
    return args -> {
        System.out.println("Bat dau cong viec");
        performRequiredWork(); // Lời gọi đồng bộ.
        System.out.println("Cong viec da xong");
    };
}
~~~

Đoạn trên **chỉ minh họa**, giả định `performRequiredWork()` đã được định nghĩa và thực sự chạy đồng bộ. Trong trường hợp đó, Boot không thể đi qua runner cho đến khi phương thức trả về hoặc ném exception.

**Runner gửi task bất đồng bộ:**

~~~java
@Bean
ApplicationRunner backgroundRunner(ExecutorService executor) {
    return args -> {
        executor.submit(() -> performRequiredWork());
        System.out.println("Da gui task, runner sap ket thuc");
    };
}
~~~

Đây cũng là **đoạn minh họa**, yêu cầu có một `ExecutorService` và phương thức `performRequiredWork()`. `submit(...)` trả lại một `Future` ngay khi task được chấp nhận, không đợi kết quả. Nếu bỏ qua `Future`, runner kết thúc sau lời gọi `submit(...)` và câu in ra. Task có thể chưa bắt đầu, đang chạy, đã xong hoặc sẽ thất bại.

Điểm cốt lõi: **gọi API bất đồng bộ không đồng nghĩa Boot sẽ theo dõi hoặc chờ task đó**. Người viết ứng dụng phải quyết định liệu việc chờ có cần thiết, chờ bao lâu và ứng dụng nên làm gì nếu task lỗi.

## 3. Ví dụ chạy được: Ready và run trả về trong khi task chưa xong

Ví dụ dùng **Java 17+ và Spring Boot 3.3.5** để có phiên bản dependency cụ thể, dễ tái lập. Nó dùng một `CountDownLatch` làm “cửa chặn” có chủ đích: task không thể hoàn tất trước khi `SpringApplication.run(...)` trả về. Nhờ đó thứ tự các dòng quan sát được là xác định, không phụ thuộc vào tốc độ CPU.

### Cấu trúc dự án

~~~text
async-runner-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/runner/AsyncRunnerDemo.java
        └── resources/
            └── application.properties
~~~

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>async-runner-demo</artifactId>
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
~~~

Tạo `src/main/resources/application.properties` để giảm log phụ khi học:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Tạo `src/main/java/com/example/runner/AsyncRunnerDemo.java`:

~~~java
package com.example.runner;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AsyncRunnerDemo {

    public static void main(String[] args) throws InterruptedException {
        SpringApplication app = new SpringApplication(AsyncRunnerDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            JobState state = context.getBean(JobState.class);

            System.out.println(
                    "4. run returned; completed=" + state.completed.get());

            // Chính main giải phóng task, không phải Spring Boot.
            try {
                state.allowCompletion.countDown();
                state.finished.await();
                System.out.println(
                        "6. main observed; completed="
                                + state.completed.get());
            } finally {
                state.allowCompletion.countDown();
            }
        }
    }

    @Bean
    JobState jobState() {
        return new JobState();
    }

    @Bean(destroyMethod = "shutdown")
    ExecutorService jobExecutor() {
        return Executors.newSingleThreadExecutor();
    }

    @Bean
    ApplicationRunner startBackgroundJob(
            JobState state, ExecutorService jobExecutor) {

        return args -> {
            System.out.println("1. runner: submitting job");

            jobExecutor.execute(() -> {
                try {
                    state.allowCompletion.await();
                    state.completed.set(true);
                    System.out.println("5. background: job completed");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println("5. background: interrupted");
                } finally {
                    state.finished.countDown();
                }
            });

            System.out.println(
                    "2. runner: returned, completed="
                            + state.completed.get());
        };
    }

    @Bean
    ApplicationListener<ApplicationReadyEvent> readyListener(
            JobState state) {
        return event -> System.out.println(
                "3. ApplicationReadyEvent; completed="
                        + state.completed.get());
    }

    static final class JobState {

        final CountDownLatch allowCompletion = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);
        final AtomicBoolean completed = new AtomicBoolean(false);
    }
}
~~~

### Chạy và kết quả

Cần Java 17+ và Maven đã cài. Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

Nếu dự án có Maven wrapper, có thể thay bằng `./mvnw -q spring-boot:run` (Windows PowerShell: `.\mvnw.cmd -q spring-boot:run`).

Với đúng ba file trên và không có thành phần ứng dụng khác, **stdout do class này tự in trong trường hợp thành công** là:

~~~text
1. runner: submitting job
2. runner: returned, completed=false
3. ApplicationReadyEvent; completed=false
4. run returned; completed=false
5. background: job completed
6. main observed; completed=true
~~~

Bỏ qua thông báo riêng của Maven/JVM nếu môi trường phát sinh chúng. `logging.level.root=ERROR` và `banner-mode=off` giúp giảm log thông thường của Boot; kết quả ở đây chỉ mô tả các dòng do ví dụ chủ động in ra.

**Giải thích từng dòng:**

1. Runner bắt đầu và gửi một `Runnable` vào `ExecutorService`. Worker thread có thể được tạo rất sớm, nhưng dừng tại `state.allowCompletion.await()`.
2. Runner in `completed=false` rồi trả về. Không có lời gọi `Future.get()` hoặc `CountDownLatch.await()` nào trong runner.
3. Boot tiếp tục phát `ApplicationReadyEvent` mặc dù background task chưa hoàn tất.
4. `SpringApplication.run(...)` trả về một `ConfigurableApplicationContext` đang active. Lúc này task vẫn đang chờ “cửa chặn”.
5. **Chính code trong `main`** gọi `allowCompletion.countDown()` sau dòng 4, task mới được phép hoàn tất và in dòng 5.
6. `main` chủ động gọi `finished.await()` để quan sát task đã xong, in dòng 6, rồi đóng context. Điều này là hành vi được chúng ta viết vào ví dụ, **không phải tính năng chờ tự động của Boot**.

Ví dụ sử dụng `AtomicBoolean` để công khai trạng thái giữa các thread và `CountDownLatch` để điều phối thứ tự có thể dự đoán. Đây là dụng cụ kiểm chứng kiến thức, **không phải công thức nên dùng trong mọi ứng dụng production**. Trong ứng dụng thật, task thường nhận công việc qua queue, service hoặc executor theo chính sách vận hành cụ thể.

`@Bean(destroyMethod = "shutdown")` yêu cầu Spring gọi `shutdown()` lên executor khi context đóng. Nhưng `shutdown()` của `ExecutorService` **không tự đợi mọi task hoàn thành**; vì vậy ví dụ đợi `finished` trước khi đóng context. Đóng context và việc đã xử lý xong mọi công việc là hai điều cần phân biệt.

## 4. Điều Spring Boot thực sự chờ

Trong startup bình thường:

- **Có chờ:** phương thức `ApplicationRunner.run(ApplicationArguments)` hoặc `CommandLineRunner.run(String...)` đang thực hiện đồng bộ, bao gồm những lời gọi mà chính runner chủ động chờ.
- **Không tự chờ:** một `Thread` đã gọi `start()`, một task vừa được `executor.submit(...)`, một `CompletableFuture` chưa được join, hay công việc `@Async` được kích hoạt qua proxy.
- **Có thể thất bại startup:** exception được ném đồng bộ ra khỏi runner và không bị xử lý, kể cả exception từ `Future.get()` nếu runner có gọi nó.
- **Không tự thất bại startup:** exception chỉ xảy ra trong một task chạy nền **sau khi runner trả về**. Task cần đường ghi nhận và xử lý lỗi riêng.

Một điểm khác biệt dễ bị bỏ qua: `ExecutorService.execute(...)` có thể ném `RejectedExecutionException` ngay khi gửi task nếu executor từ chối nhận việc. Đây là lỗi **đồng bộ trong runner** và có thể làm startup thất bại. Ngược lại, một exception ném trong code được executor chấp nhận chạy về sau không tự động quay lại thread đang gọi runner.

## 5. Khi nào nên chờ task ngay trong runner?

Có những công việc **bắt buộc hoàn tất trước khi ứng dụng nhận traffic**: ví dụ tải cấu hình quan trọng chưa có nơi fallback, xác minh schema tương thích hoặc khởi tạo dữ liệu nội bộ mà request đầu tiên chắc chắn cần đến.

Nếu thời gian hoàn thành hợp lý và có thể đo đếm được, runner có thể **chủ động chờ**:

~~~java
@Bean
ApplicationRunner requiredInitialization(ExecutorService executor) {
    return args -> {
        Future<?> future = executor.submit(() -> {
            // Thực hiện một thao tác khởi tạo bắt buộc.
            initializeRequiredData();
        });

        try {
            future.get(30, TimeUnit.SECONDS);
        } catch (TimeoutException ex) {
            future.cancel(true);
            throw new IllegalStateException(
                    "Initialization exceeded 30 seconds", ex);
        } catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw ex;
        }
    };
}
~~~

Đoạn trên là **mẫu minh họa để đặt trong class cấu hình Spring**, không phải chương trình độc lập. Nó yêu cầu các import `java.util.concurrent.Future`, `TimeUnit`, `TimeoutException`, `InterruptedException` và một phương thức `initializeRequiredData()` do ứng dụng định nghĩa. Exception thực thi từ task còn có thể được bọc trong `ExecutionException` và được truyền ra từ `Future.get(...)`. Phương thức `ApplicationRunner.run(...)` cho phép ném `Exception`.

Kết quả của thiết kế này:

- Nếu task hoàn thành, `future.get(...)` trả về, runner kết thúc, rồi Boot mới tiến tới ready.
- Nếu task ném lỗi, runner nhận exception qua `Future.get(...)`; startup có thể bị đánh dấu thất bại.
- Nếu task không hoàn thành trong 30 giây, runner chủ động báo lỗi thay vì chờ vô hạn.
- `future.cancel(true)` chỉ **yêu cầu** hủy/ngắt task; không bảo đảm code đang chạy thực sự dừng, nhất là khi thao tác I/O hoặc thư viện không phản ứng với interrupt.

Đây là ví dụ task chạy nền nhưng **có chờ tường minh**; nó không mâu thuẫn với nguyên tắc “Boot không tự chờ async”. Boot chỉ đang chờ runner; còn runner đã tự quyết định đợi `Future`.

**Không nên chờ vô hạn** trên một task phụ thuộc mạng, queue hoặc dịch vụ ngoài. Nếu task là một consumer dự định chạy mãi (ví dụ đọc Kafka liên tục), việc chờ nó kết thúc sẽ khiến startup không bao giờ đạt ready. Đối với dịch vụ chạy liên tục, hãy phân biệt trạng thái “đã khởi chạy và sẵn sàng nhận công việc” với trạng thái “đã xử lý xong tất cả công việc”.

## 6. `CompletableFuture`: rất dễ viết fire-and-forget

Ví dụ:

~~~java
@Bean
ApplicationRunner warmupRunner(Executor executor) {
    return args -> {
        CompletableFuture<Void> job =
                CompletableFuture.runAsync(
                        () -> warmUpLocalCache(), executor);

        // Không join/get/handle: runner có thể trở về ngay.
        System.out.println("Warm-up requested");
    };
}
~~~

Đây là đoạn minh họa cần `java.util.concurrent.CompletableFuture`, `Executor` và phương thức `warmUpLocalCache()` được định nghĩa. Biến `job` được tạo nhưng chưa ai chờ hay quan sát kết quả. Một exception bên trong `warmUpLocalCache()` thường khiến future hoàn thành **exceptionally**; nếu không ai đọc future, vấn đề có thể bị bỏ qua khỏi luồng điều phối startup.

Có hai cách xử lý tùy yêu cầu:

**A. Công việc là điều kiện khởi động:**

~~~java
CompletableFuture<Void> job =
        CompletableFuture.runAsync(() -> warmUpLocalCache(), executor);

// Cố ý đợi; lỗi từ task được bọc và truyền lên caller.
job.join();
~~~

`join()` có thể ném `CompletionException` khi task lỗi; nếu chờ vô hạn, runner cũng có thể bị chặn vô hạn. Với Java 17, có thể sử dụng deadline bằng `orTimeout(...)` hoặc các API `get(timeout, unit)`, đồng thời xử lý exception và chính sách hủy công việc. Không dùng `join()` tràn lan trên những task được thiết kế để tồn tại suốt vòng đời ứng dụng.

**B. Công việc chạy nền không chặn startup:**

~~~java
CompletableFuture.runAsync(() -> warmUpLocalCache(), executor)
        .whenComplete((unused, error) -> {
            if (error != null) {
                log.error("Warm-up failed", error);
            } else {
                log.info("Warm-up completed");
            }
        });
~~~

Đoạn này cần có logger `log` và phương thức `warmUpLocalCache()` trong class bao quanh. Nó giúp quan sát thành công/thất bại, nhưng **không tự làm startup đợi hoặc thất bại**. Nếu startup đã ready mà warm-up lỗi, hệ thống cần cơ chế retry, degraded mode hoặc cảnh báo phù hợp.

Nếu không truyền executor vào `CompletableFuture.runAsync(...)`/`supplyAsync(...)`, Java thường sử dụng `ForkJoinPool.commonPool()`. Đây là pool chung, không phải executor được Spring context sở hữu. Đừng dựa vào nó để bảo đảm graceful shutdown, kiểm soát giới hạn tải hoặc giữ JVM sống cho một công việc quan trọng. Hãy chọn executor được quản lý rõ ràng.

## 7. `@Async` cũng không tự đổi hợp đồng của runner

Spring hỗ trợ `@Async` khi bật async execution, ví dụ:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Một service được gọi qua Spring proxy có thể viết:

~~~java
@Service
public class ReportWarmupService {

    @Async
    public CompletableFuture<String> prepare() {
        // Công việc minh họa.
        return CompletableFuture.completedFuture("ready");
    }
}
~~~

Rồi runner khác bean gọi:

~~~java
@Bean
ApplicationRunner reportRunner(ReportWarmupService service) {
    return args -> {
        CompletableFuture<String> result = service.prepare();
        // Không gọi result.get()/join(): runner chưa chờ task.
    };
}
~~~

Ba đoạn trên là **cấu hình minh họa**, cần import Spring `@Configuration`, `@EnableAsync`, `@Service`, `@Bean`, `@Async` và Java `CompletableFuture`. Khi chạy thực tế, thay phần minh họa bằng logic nghiệp vụ và cấu hình executor phù hợp.

**Điều quan trọng:**

- `@Async` được thực thi thông qua cơ chế proxy/interceptor của Spring. Một phương thức gọi `this.prepare()` trong **chính cùng object** thường bỏ qua proxy và không chạy bất đồng bộ như mong muốn.
- Phải bật `@EnableAsync` hoặc có cấu hình tương đương để `@Async` được xử lý.
- Gọi một phương thức `@Async` qua proxy thường trả về nhanh, nhưng không có quy tắc Spring Boot phải chờ future trước `ApplicationReadyEvent`.
- Với phương thức `@Async` trả về `void`, không có future cho caller thu thập lỗi; cần cấu hình logging và `AsyncUncaughtExceptionHandler` phù hợp cho exception chưa được xử lý.
- Với `CompletableFuture<T>` hoặc `Future<T>`, caller có thể chủ động theo dõi hoặc chờ để xử lý kết quả/lỗi. Hãy phân biệt exception trả về qua future với exception đồng bộ xảy ra khi lời gọi bị từ chối.
- Đặt tên và cấu hình executor rõ ràng. Nếu dùng executor mặc định, cần biết giới hạn thread/queue và cách nó được Spring quản lý trên phiên bản đang chạy.

Không thêm `@Async` lên runner rồi cho rằng Boot sẽ tự hiểu khi nào công việc đó hoàn tất. Hợp đồng khởi động cần được thiết kế tường minh thay vì dựa vào tên annotation.

## 8. `ApplicationReadyEvent` và readiness không bảo đảm background job đã xong

Trong Spring Boot, `ApplicationStartedEvent` được phát trước khi chạy startup runners, còn `ApplicationReadyEvent` được phát sau khi các runner hoàn tất theo cách gọi đồng bộ. Tuy nhiên:

~~~text
Startup:
  context refresh
  ApplicationStartedEvent
  runner gửi task vào queue --------> background task bắt đầu
  runner trả về
  ApplicationReadyEvent                 background task còn chạy
  SpringApplication.run trả về          background task còn chạy
                                       background task hoàn tất
~~~

Nếu dịch vụ dùng readiness probe để quyết định đưa traffic vào, bạn cần trả lời câu hỏi: **“Đã ready” có nghĩa task khởi tạo nào bắt buộc phải xong?**

Có ba cách thiết kế phổ biến:

| Yêu cầu | Cách xử lý |
|---|---|
| Task bắt buộc xong trước khi nhận request | Thực hiện đồng bộ hoặc runner chủ động chờ future với timeout, báo lỗi startup nếu thất bại. |
| Task hữu ích nhưng không bắt buộc | Chạy nền, cho phép ứng dụng ready, có log/metric/retry; request không được phụ thuộc tuyệt đối vào kết quả chưa sẵn sàng. |
| Task chạy nền nhưng cần báo “chưa ready” cho tới khi hoàn tất | Quản lý một trạng thái readiness riêng, gắn vào health indicator/probe hoặc một cơ chế availability được điều phối đúng lifecycle. |

Spring Boot có các trạng thái như `ReadinessState.ACCEPTING_TRAFFIC` và `ReadinessState.REFUSING_TRAFFIC`. Boot tự công bố trạng thái readiness trong chuỗi startup, vì vậy nếu ứng dụng tự phát sự kiện đổi readiness quá sớm rồi Boot tiếp tục công bố `ACCEPTING_TRAFFIC`, trạng thái có thể bị ghi đè. Không thiết kế readiness phụ thuộc task chỉ bằng một lần gọi đổi trạng thái bất kỳ trong runner rồi cho rằng hiệu lực tồn tại mãi; hãy kiểm tra đúng mốc phát event và cơ chế health đang dùng.

Với một job quan trọng, cân nhắc định nghĩa health indicator riêng dựa trên trạng thái hoàn thành thành công của job. Lúc đó readiness phản ánh điều kiện nghiệp vụ rõ ràng, thay vì chỉ suy diễn từ việc runner đã được gọi.

## 9. Executor, JVM và trách nhiệm đóng tài nguyên

Một task không được Boot tự chờ vẫn có ảnh hưởng thực tế lên vòng đời process. Một số trường hợp:

**Executor tạo thủ công nhưng không quản lý:**

~~~java
Executors.newSingleThreadExecutor().submit(this::runLongJob);
~~~

Đây là đoạn minh họa, giả định có `runLongJob()` và import `Executors`. Với thread factory mặc định, executor loại này thường tạo **non-daemon thread**. Nếu không gọi shutdown, tiến trình Java có thể vẫn tồn tại ngay cả khi các công việc chính đã xong; sự cố này dễ bị nhầm là “Spring Boot chưa tắt”.

**Task trên daemon/common pool:** thread daemon không phải cơ chế giữ JVM sống. Nếu không còn non-daemon thread, JVM có thể kết thúc trước khi task hoàn tất. Do đó không thể suy ra rằng một tác vụ được gửi vào common pool sẽ luôn kịp chạy xong sau khi `main` trả về.

**Executor được đăng ký thành Spring bean:**

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService jobExecutor() {
    return Executors.newFixedThreadPool(2);
}
~~~

Bean có callback destroy rõ ràng, nên lúc Spring đóng context nó gọi `shutdown()`. Nhưng `shutdown()` chỉ yêu cầu ngừng nhận task mới và cho task đã nhận xử lý theo hợp đồng của executor; bản thân nó **không đồng nghĩa đợi hoàn tất**. Nếu cần chờ một khoảng thời gian hữu hạn, phải có logic như `awaitTermination(timeout, unit)` trong chủ sở hữu executor, hoặc cấu hình executor/lifecycle component có chính sách chờ shutdown phù hợp.

Với `ThreadPoolTaskExecutor` của Spring, có thể cấu hình số thread, độ dài hàng đợi và những thiết lập chờ lúc shutdown (tùy phiên bản). Quan trọng hơn tên API là hợp đồng vận hành: **ngừng nhận việc mới, đợi công việc đang chạy trong giới hạn cho phép, xử lý việc chưa hoàn tất, đóng tài nguyên**. Task quan trọng vẫn cần chính sách idempotency/retry nếu ứng dụng bị kill đột ngột hoặc bị mất điện, vì graceful shutdown không phải bảo đảm tuyệt đối.

Không tự tạo executor trong mỗi lần gọi runner nếu không có đường đóng và giám sát rõ ràng. Đừng đặt executor ở local variable rồi để mất reference trong khi task còn chạy.

## 10. Exception chạy nền không tự trở thành lỗi startup

Một trong những tình huống khó chẩn đoán nhất:

~~~java
@Bean
ApplicationRunner example(ExecutorService executor) {
    return args -> {
        executor.submit(() -> {
            throw new IllegalStateException("remote index unavailable");
        });
    };
}
~~~

Đây là ví dụ minh họa. `executor.submit(...)` trả về một `Future`, nhưng runner bỏ qua nó. Nếu task ném exception, `Future` hoàn thành trong trạng thái thất bại; exception không tự bay qua thread của runner để làm `SpringApplication.run(...)` thất bại.

Muốn phát hiện lỗi, có thể giữ future:

~~~java
Future<?> result = executor.submit(this::buildIndex);
try {
    result.get(20, TimeUnit.SECONDS);
} catch (ExecutionException ex) {
    throw new IllegalStateException(
            "Index build failed", ex.getCause());
}
~~~

Đoạn này là ví dụ nằm trong method đã có executor, phương thức `buildIndex()` và các import phù hợp. Thực tế còn cần xử lý `InterruptedException` và `TimeoutException`; nếu ứng dụng chọn fail startup, nên đặt chính sách hủy task, deadline và cleanup.

Trong ứng dụng không chặn startup, hãy ít nhất theo dõi trạng thái của future, ghi log lỗi kèm nguyên nhân, metric/thời gian xử lý và retry có kiểm soát. Nếu task cập nhật trạng thái để HTTP request dựa vào, cần đồng bộ visibility giữa thread bằng `volatile`, `AtomicReference`, synchronized hoặc data structure thread-safe.

## 11. Nhiều runner và `@Order` không làm task bất đồng bộ tuần tự

Spring Boot cho phép đăng ký nhiều bean runner. Thứ tự gọi runner có thể được điều khiển bằng `@Order` hoặc `Ordered`. Nhưng thứ tự này áp dụng cho **lời gọi runner đồng bộ**, không tự xếp hàng và chờ toàn bộ task mà từng runner gửi đi.

Ví dụ:

~~~text
Runner A (@Order(1)):
    executor.submit(taskA)
    return

Runner B (@Order(2)):
    readDataCreatedByTaskA()
    return
~~~

Nếu `taskA` chưa xong, runner B có thể đọc dữ liệu chưa sẵn sàng dù `@Order(1)` nhỏ hơn `@Order(2)`. Để B phụ thuộc kết quả A, nên:

- Biểu diễn dependency giữa các bean hoặc các bước khởi tạo một cách rõ ràng.
- Chuyển cùng một quy trình đồng bộ bắt buộc vào runner điều phối và chờ tương ứng.
- Hoặc phối hợp các future bằng `thenCompose(...)`, `allOf(...)`, `join()` hoặc một cơ chế orchestration phù hợp, có deadline và error handling.

Tương tự, hai `ApplicationContext` khác nhau có thể mỗi bên chạy runner và sinh task nền riêng. `ApplicationReadyEvent` của context A không có nghĩa background task của context B đã hoàn tất; cũng không có nghĩa event của sibling hoặc parent đồng nghĩa với readiness nghiệp vụ toàn hệ thống.

## 12. Tránh deadlock do chờ không đúng cách

Việc chủ động chờ không phải lúc nào cũng an toàn. Một lỗi điển hình:

~~~text
Executor chỉ có một worker thread
    |
    +-- Task A chạy trên worker
           |
           +-- Task A submit Task B vào CHÍNH executor đó
           |
           +-- Task A gọi Future.get() và chờ Task B
                  |
                  +-- Task B không được chạy:
                      worker duy nhất còn đang bị Task A giữ
~~~

Đó là một dạng **thread-starvation deadlock**. Tương tự, callback bean startup hoặc runner có thể đợi một task mà task đó lại chờ bean, lock, tài nguyên hoặc sự kiện chỉ được phát sau khi runner trả về.

Nguyên tắc bảo vệ:

- Không block trong task của một executor đơn luồng để chờ một task khác cũng cần executor đơn luồng đó.
- Đặt timeout và theo dõi stack/thread dump khi nghi ngờ startup bị treo.
- Đừng chờ một sự kiện mà Spring chỉ phát **sau khi runner hoàn tất**, ví dụ đợi `ApplicationReadyEvent` ngay trong runner hiện tại sẽ dẫn đến sự chờ vòng.
- Tránh dùng `Thread.sleep(...)` để “bảo đảm công việc khác đã xong”; sleep chỉ thay đổi thời gian, không thiết lập quan hệ hoàn thành đáng tin.
- Với task cần kết quả, cân nhắc biểu diễn pipeline bất đồng bộ rồi chỉ block ở ranh giới phù hợp, hoặc dùng cơ chế startup tương ứng.

Một dịch vụ cần xử lý message liên tục phải báo trạng thái “consumer đã đăng ký/đang hoạt động” theo cách phù hợp, chứ không được `join()` vào vòng lặp consumer bất tận rồi hy vọng đạt ready.

## 13. Mẫu chọn chiến lược theo nhu cầu

| Loại công việc runner tạo | Startup có nên chờ? | Cách kiểm soát |
|---|---|---|
| Kiểm tra cấu hình bắt buộc, nhanh và hữu hạn | Thường **có** | Chạy đồng bộ hoặc chờ `Future.get(timeout)`, fail startup nếu lỗi. |
| Khởi tạo dữ liệu tối thiểu mà endpoint chắc chắn cần | Thường **có**, hoặc đánh readiness chưa đạt | Timeout, lỗi rõ ràng, readiness theo trạng thái thực. |
| Warm cache tùy chọn | Không nhất thiết | Chạy nền, theo dõi hoàn thành và cho phép fallback khi cache chưa có. |
| Đồng bộ dữ liệu bên ngoài mất nhiều phút | Thường **không chặn toàn bộ startup**, trừ yêu cầu nghiệp vụ | Job riêng, persistence/checkpoint, retry, metric, API chịu được trạng thái đang xử lý. |
| Consumer/scheduler phải chạy liên tục | **Không chờ kết thúc** | Quản lý lifecycle, readiness dựa trên trạng thái đăng ký/health, shutdown đúng cách. |
| Tạo report hoặc gửi sự kiện không bắt buộc | Có thể không | Queue hoặc worker bền vững, retry/idempotency; tránh chỉ fire-and-forget trong bộ nhớ nếu dữ liệu phải được bảo toàn. |
| Migration/schema upgrade bắt buộc | Thường cần hoàn tất trước phục vụ request | Công cụ migration chuyên dụng, giới hạn thời gian, xử lý cạnh tranh giữa nhiều instance. |

Lựa chọn quan trọng không phải “sử dụng async hay sync” mà là **hợp đồng sẵn sàng của ứng dụng**. Hãy mô tả việc cần hoàn tất, thời điểm deadline, nguồn thông tin lỗi và hành vi khi task chưa hoàn tất.

## 14. Các lỗi thường gặp

**Lỗi 1 — “`ApplicationRunner.run(...)` được Boot chờ, nên task nó tạo cũng được chờ”.**

Sai. Boot chờ **lời gọi runner**, không tự quản lý toàn bộ cây task do runner tạo. `submit(...)`/`runAsync(...)` thường trả về trước khi task hoàn tất.

**Lỗi 2 — “Thấy `ApplicationReadyEvent` tức mọi warm-up task đã hoàn thành”.**

Không đảm bảo. Nếu runner gửi task nền rồi trả về, ready event có thể được phát khi task vẫn còn đang chạy.

**Lỗi 3 — “Exception trong future sẽ tự gây startup failure”.**

Không phải khi runner không quan sát future. Lỗi task cần được truyền về bằng `get/join` hoặc xử lý bất đồng bộ, tùy mục tiêu.

**Lỗi 4 — “`@Async` trong cùng class tự tạo thread khác”.**

Với Spring proxy thông thường, self-invocation bỏ qua interceptor; để kích hoạt async qua proxy, gọi phương thức trên Spring bean qua ranh giới proxy được cấu hình thích hợp.

**Lỗi 5 — “Dùng `@Order` là runner B chắc chắn thấy dữ liệu task A tạo”.**

`@Order` sắp xếp lời gọi runners, không có bảo đảm về thời điểm kết thúc task nền của A.

**Lỗi 6 — “`ExecutorService.shutdown()` sẽ block tới khi mọi task xong”.**

Không. Muốn đợi, bạn cần thêm cơ chế như `awaitTermination(...)` hoặc policy quản lý lifecycle phù hợp.

**Lỗi 7 — “Task nền tồn tại thì JVM chắc chắn còn sống”.**

Không đúng trong mọi trường hợp. Thread daemon không giữ JVM sống; non-daemon executor không shutdown lại có thể khiến process không thoát. Kết quả phụ thuộc thread factory, lifecycle context và trạng thái các luồng còn lại.

**Lỗi 8 — “Chỉ cần `Thread.sleep(1000)` trước khi trả runner”.**

Thời gian chờ cố định không chứng minh công việc đã hoàn tất. Dùng `Future`, `CountDownLatch`, trạng thái health hoặc cơ chế đồng bộ có hợp đồng rõ ràng.

**Lỗi 9 — “Task thất bại sau ready cũng không sao vì ứng dụng vẫn active”.**

Nếu dữ liệu do task tạo là dependency bắt buộc của request, dịch vụ có thể active nhưng trả kết quả sai hoặc lỗi. Cần readiness/fallback/error reporting phù hợp với nghiệp vụ.

## 15. Bài thực hành tự kiểm chứng

Từ ví dụ Maven ở mục 3, thử từng thay đổi một:

1. Bỏ lời gọi `state.finished.await()` ở `main`, nhưng vẫn mở `allowCompletion`. Quan sát `main` có thể đóng context trước khi bạn kiểm tra trạng thái hoàn thành; thứ tự log ngoài những ràng buộc còn lại cần được xem là có cạnh tranh.
2. Chuyển `allowCompletion.countDown()` vào trong runner **trước khi trả về**. Task có thể hoàn thành trước hoặc sau `ApplicationReadyEvent` tùy lịch chạy; không có bảo đảm thứ tự như lúc còn “cửa chặn”.
3. Trong runner, đợi `state.finished.await()` trong khi task vẫn chờ `allowCompletion` chỉ được `main` mở **sau khi `app.run(...)` trả về**. Đây là một ví dụ **deadlock**, vì `main` không thể đi đến điểm mở latch khi runner còn đang chờ. Chỉ thử biến thể này khi đã hiểu và có phương án kết thúc tiến trình thử nghiệm.
4. Thay executor trong ví dụ bằng `CompletableFuture.runAsync(...)` nhưng vẫn giữ logic hoàn thành. Xác nhận không có phép chờ mặc định nào được thêm vào startup.
5. Cho task ném exception, giữ `Future<?>` từ `submit(...)` rồi lần lượt thử **không đọc future** và **gọi `get()` trong runner**. So sánh việc Boot có nhận exception trong luồng startup không.
6. Thêm một runner thứ hai với `@Order` lớn hơn runner đầu tiên. Xác nhận thứ tự **gửi việc** có thể được điều khiển nhưng thứ tự **task hoàn tất** vẫn cần được phối hợp riêng.

### Tài liệu tham khảo

- Spring Boot 3.3 — SpringApplication, runners và startup events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Application availability, liveness và readiness: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability
- Java 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

**Ghi nhớ:** Spring Boot chờ các phương thức `ApplicationRunner.run(...)` / `CommandLineRunner.run(...)` trả về; nó **không tự chờ task bất đồng bộ** mà những phương thức đó đã khởi tạo. Nếu công việc bắt buộc trước khi ready, runner phải chủ động chờ với deadline hoặc ứng dụng phải điều phối readiness theo trạng thái thực. Nếu công việc có thể chạy nền, hãy thiết kế executor, quan sát lỗi, retry và shutdown rõ ràng — không coi fire-and-forget là một hợp đồng hoàn thành.
