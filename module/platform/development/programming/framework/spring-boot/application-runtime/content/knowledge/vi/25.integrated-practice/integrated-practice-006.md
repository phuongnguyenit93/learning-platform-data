# Xây thành phần nền bằng SmartLifecycle với hai phase phụ thuộc

## 1. Mục tiêu bài thực hành

Một ứng dụng Spring Boot đôi khi có **thành phần nền (background component)** chỉ được phép chạy sau khi một thành phần hạ tầng đã sẵn sàng. Ví dụ: một consumer đọc message phải chờ connection tới broker; một polling worker dùng database pool; một stream processor phụ thuộc vào một client hoặc cache.

Vấn đề không chỉ nằm ở **khởi động đúng thứ tự**. Khi ứng dụng dừng, worker phải **ngừng nhận việc mới và hoàn tất công việc đang xử lý trước khi hạ tầng bị đóng**. Nếu đảo sai thứ tự, worker có thể sử dụng một connection đã bị shutdown; dữ liệu có thể mất hoặc bị xử lý nửa chừng.

Bài này xây **hai bean `SmartLifecycle` phụ thuộc**:

1. `Gateway` — mô phỏng tài nguyên hạ tầng đã được mở, **phase 100**.
2. `BackgroundWorker` — mô phỏng consumer chạy trên một thread nền và cần `Gateway`, **phase 200**.

Kết quả ta muốn kiểm chứng:

```text
KHỞI ĐỘNG
    Gateway.start()       (phase=100)
          |
          v
    BackgroundWorker.start() (phase=200)
          |
          v
    ApplicationReadyEvent

TRONG LÚC CHẠY
    Main yêu cầu một job
          |
          v
    BackgroundWorker gọi Gateway.handle(...)
          |
          v
    Main nhận Future hoàn tất

ĐÓNG BÌNH THƯỜNG
    ContextClosedEvent
          |
          v
    BackgroundWorker.stop(Runnable)   (phase=200)
      -> dừng nhận việc, chờ worker exit, gọi callback
          |
          v
    Gateway.stop(Runnable)            (phase=100)
          |
          v
    @PreDestroy các singleton
          |
          v
    context.close() trả về
```

Đây là một **bài thực hành tổng hợp** thuộc chủ đề Spring Boot Application Runtime. Nó kết hợp lifecycle context, `SmartLifecycle`, phase, phụ thuộc bean, thread nền, `CompletableFuture`, shutdown callback, event và destruction. Demo dùng một gateway **in-memory**, không kết nối broker hay database thật, để trình tự có thể được chứng minh bằng output không phụ thuộc mạng hoặc tốc độ máy.

**Phiên bản:** Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, Gradle Groovy. Trong bài, những phase 100/200 là **giá trị do ứng dụng tự chọn**, không phải hai phase đặc biệt được Spring dành sẵn.

## 2. Hiểu ba vòng đời trước khi viết code

Cần phân biệt:

| Khái niệm | Khi nào xuất hiện? | Chức năng |
| --- | --- | --- |
| **Bean creation / initialization** | Spring tạo object, inject dependency, gọi `@PostConstruct` | Chuẩn bị cấu hình và trạng thái object |
| **Lifecycle start / running** | `LifecycleProcessor.onRefresh()` gọi `SmartLifecycle.start()` nếu auto-start | Bắt đầu hoạt động của component |
| **Boot started / ready** | `SpringApplication` phát started/ready events quanh bước runners | Đánh dấu mốc startup của ứng dụng |
| **Lifecycle stop** | Khi `context.stop()` hoặc `context.close()` bình thường | Dừng hoạt động theo phase/dependency |
| **Singleton destruction** | Khi context đóng và destroy bean đủ điều kiện | Thu hồi tài nguyên / `@PreDestroy` |

Một singleton có thể **được tạo nhưng chưa running**. Ngược lại, trong quá trình đóng, bean còn tồn tại trong container khi lifecycle stop đang thực thi. Bởi vậy, không nên lấy constructor hoặc `@PostConstruct` làm tín hiệu “consumer được phép nhận message” nếu tài nguyên phụ thuộc chưa chạy.

`SmartLifecycle` được thiết kế để container điều phối những component có khái niệm `start/stop/running`. Đây là hợp đồng lifecycle ở cấp **Spring Framework**, không chỉ Spring Boot.

### 2.1. Phân biệt Lifecycle và SmartLifecycle

`Lifecycle` định nghĩa:

```java
void start();
void stop();
boolean isRunning();
```

`SmartLifecycle` kế thừa `Lifecycle` và `Phased`, bổ sung:

```java
boolean isAutoStartup();
int getPhase();
void stop(Runnable callback);
```

Hai đoạn trên là **chữ ký rút gọn để học API**, không phải file Java tự chạy. Class của bài thực hành sẽ implement đầy đủ các method thích hợp.

- `isAutoStartup()`: có tự khởi động tại `ApplicationContext.refresh()` hay không; mặc định của `SmartLifecycle` trên Spring 6.1 là `true`.
- `getPhase()`: sắp xếp thứ tự start/stop. Giá trị nhỏ start sớm; giá trị lớn stop sớm.
- `stop(Runnable callback)`: cho phép một component dừng bất đồng bộ và báo **đã dừng thật** về `LifecycleProcessor`.
- `isRunning()`: phản ánh **trạng thái thực tế mà implementation công bố**, không nên trả `true` vô điều kiện.

`SmartLifecycle.DEFAULT_PHASE` trong Spring Framework 6.1 bằng `Integer.MAX_VALUE`. Nếu không override `getPhase()`, một SmartLifecycle thông thường nằm ở phase rất cao: start muộn và stop sớm. Với hệ thống có dependency rõ, **chọn phase tường minh** thường dễ hiểu hơn. `Lifecycle` thường không triển khai `Phased` được processor xem như phase 0.

### 2.2. Phase quyết định thứ tự ra sao?

| Component | Phase | Khi start | Khi stop |
| --- | ---: | --- | --- |
| Hạ tầng `Gateway` | 100 | **Thứ nhất** | **Thứ hai** |
| Consumer `BackgroundWorker` | 200 | **Thứ hai** | **Thứ nhất** |

Quy tắc tổng quát:

```text
START:     phase thấp --------> phase cao
STOP:      phase cao  --------> phase thấp
```

Điều này phản ánh nguyên tắc dependency: consumer **phải có gateway trước khi chạy** và gateway **phải còn sống trong lúc consumer đang dừng**.

### 2.3. @DependsOn và phase: hai lớp bảo đảm

Ta sẽ khai báo bean worker với dependency injection và `@DependsOn("gateway")`:

```java
@Bean
@DependsOn("gateway")
BackgroundWorker worker(Gateway gateway, Trace trace) {
    return new BackgroundWorker(gateway, trace);
}
```

Đây là snippet trong configuration class, chưa độc lập. Hai ý:

1. Tham số `Gateway gateway` cho biết worker thực sự cần object gateway; không có gateway thì không tạo worker.
2. `@DependsOn("gateway")` diễn đạt quan hệ bean definition tường minh: **dependent start sau dependency, stop trước dependency**, kể cả khi phase có mâu thuẫn.

Trong demo, phase 100/200 và dependency đều **cùng hướng**, giúp người đọc dễ kiểm tra. Nếu các phase ngược nhau, quan hệ depends-on tường minh được Spring Framework ưu tiên khi điều phối những beans liên quan.

**Đừng nhầm:** `@DependsOn` không thay việc truyền `Gateway` vào constructor. Nó là metadata quan hệ lifecycle/initialization; worker vẫn cần reference gateway để gọi `handle(...)`. Ngược lại, phase không phải công cụ để chọn thứ tự gọi constructor hoặc `@Bean` method; những cơ chế đó còn do dependency graph quyết định.

## 3. Thiết kế hai thành phần nền có ownership rõ

### 3.1. Gateway (phase 100)

Hạ tầng mô phỏng có trách nhiệm:

- `start()`: đánh dấu tài nguyên mở/khả dụng.
- `handle("sample")`: xử lý một message và trả acknowledgement; từ chối nếu đã stopped.
- `stop()`: ngừng nhận I/O của gateway.
- `@PreDestroy`: cleanup phòng thủ nếu shutdown bất thường không đi qua stop bình thường.

Trong hệ thống thực, Gateway có thể là producer tới broker, client TCP, connection tới database hoặc API client. Nhưng nếu dùng thư viện có lifecycle riêng, cần tuân thủ contract của thư viện đó; `SmartLifecycle` không biến thao tác network thành durable transaction.

### 3.2. BackgroundWorker (phase 200)

Worker có trách nhiệm:

- `start()`: chỉ khởi động khi gateway đang running; tạo một thread nền **do worker sở hữu**.
- `submitOnce()`: phát tín hiệu cho thread xử lý **một job** và trả `CompletableFuture<String>` để caller có thể chờ kết quả.
- `stop(Runnable)`: dừng nhận job mới, đánh thức worker nếu chưa có job, cho phép job đang thực thi kết thúc, và **chỉ gọi callback khi worker đã thoát**.
- `stop()`: cung cấp biến thể đồng bộ cho caller muốn dừng tường minh; chờ callback có deadline.
- `@PreDestroy`: gọi stop phòng thủ nếu cần rồi đánh dấu destroy.

Đây là **one-shot worker** cho thí nghiệm determinism: nó chỉ nhận một message mỗi lần context được tạo. Một production consumer nhiều message cần queue, concurrency limit, kiểm tra trạng thái và khả năng restart bằng cách tạo lại runtime resources; phần sau nói rõ cách mở rộng.

### 3.3. Tách “đã gửi” khỏi “đã xử lý xong”

`submitOnce()` gửi tín hiệu yêu cầu job rồi trả Future. Nó **không bảo đảm job đã hoàn thành ngay lúc return**. Trong main ta gọi `future.get(5, TimeUnit.SECONDS)` để đợi kết quả hoặc nhận exception/timeout.

Nhờ vậy test không đánh đồng:

- Thread được `start()`.
- Một job được **gửi** tới worker.
- Job **thực thi** qua gateway.
- Future **hoàn tất thành công**.
- Component **dừng hẳn**.

`stop(Runnable)` còn cần phân biệt **đã yêu cầu dừng** với **dừng hoàn tất**, vì Spring phải chờ callback trước khi chuyển sang dừng phase phụ thuộc thấp hơn.

## 4. Cấu trúc project thực hành

Tạo một project Gradle Groovy. Đường dẫn đầy đủ:

```text
two-phase-lifecycle-lab/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/
    │   ├── java/com/example/twophase/
    │   │   └── TwoPhaseLifecycleApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/twophase/
            └── TwoPhaseLifecycleApplicationTest.java
```

Các class `Trace`, `Gateway`, `BackgroundWorker` và `LifecycleEvents` được đặt thành **nested static classes** trong file application để người học copy một file Java là đủ. Test sử dụng chính các class đó từ cùng package; không có annotation scan hoặc file bean nào bị bỏ thiếu.

Dự án cần **JDK 17+** và Gradle Wrapper phù hợp với JVM đã chọn. Nếu chưa có Gradle Wrapper, tạo wrapper bằng Gradle đã cài; những lệnh chạy `gradlew` phía dưới giả định wrapper đã sẵn có.

### 4.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot starter cung cấp `ApplicationContext`, annotations và JDK logging integration cần cho demo. Test starter cung cấp JUnit Jupiter và AssertJ.

**Không cần `spring-boot-starter-web`**, vì bài kiểm chứng vòng đời component nền, không kiểm HTTP server. Một context không có Tomcat sẽ giúp trace tránh bị chen bởi event web server.

### 4.2. settings.gradle

```groovy
rootProject.name = 'two-phase-lifecycle-lab'
```

### 4.3. application.properties

Tạo `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR

# Mỗi phase được đợi tối đa 10 giây khi dừng.
spring.lifecycle.timeout-per-shutdown-phase=10s
```

Hai phase thực hành **khác nhau** (100 và 200). Timeout áp dụng cho việc `DefaultLifecycleProcessor` chờ callback của mỗi phase; nó không tự đặt timeout cho mọi I/O bên trong worker. Demo chủ động dùng Future timeout ở main và deadline cho stop đồng bộ để tránh ví dụ “đợi mãi”.

### 4.4. Chuẩn bị đúng package

Tạo file **`src/main/java/com/example/twophase/TwoPhaseLifecycleApplication.java`**. Toàn bộ chương trình tiếp theo được đặt trong file này; tên public class trùng filename, package trùng thư mục.


## 5. File Java hoàn chỉnh: Gateway phase 100 và BackgroundWorker phase 200

```java
package com.example.twophase;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class TwoPhaseLifecycleApplication {

    public static void main(String[] args) throws Exception {
        Trace trace;

        try (ConfigurableApplicationContext context =
                SpringApplication.run(TwoPhaseLifecycleApplication.class, args)) {

            trace = context.getBean(Trace.class);
            BackgroundWorker worker = context.getBean(BackgroundWorker.class);

            trace.record("04 main: submit sample");
            String result = worker.submitOnce().get(5, TimeUnit.SECONDS);

            if (!"ACK:sample".equals(result)) {
                throw new IllegalStateException("Unexpected result: " + result);
            }
            trace.record("06 main: job observed");
        }

        // try-with-resources đã đóng Spring context ở đây.
        trace.record("12 main: context closed");

        List<String> expected = List.of(
                "01 gateway.start phase=100",
                "02 worker.start phase=200",
                "03 ApplicationReadyEvent",
                "04 main: submit sample",
                "05 gateway: handled sample",
                "06 main: job observed",
                "07 ContextClosedEvent",
                "08 worker.stop completed phase=200",
                "09 gateway.stop phase=100",
                "10 worker.@PreDestroy",
                "11 gateway.@PreDestroy",
                "12 main: context closed");

        if (!trace.snapshot().equals(expected)) {
            throw new IllegalStateException(
                    "Unexpected lifecycle trace: " + trace.snapshot());
        }
        System.out.println("CHECK PASS");
    }

    @Bean
    Trace trace() {
        return new Trace();
    }

    @Bean("gateway")
    Gateway gateway(Trace trace) {
        return new Gateway(trace);
    }

    @Bean("worker")
    @DependsOn("gateway")
    BackgroundWorker worker(Gateway gateway, Trace trace) {
        return new BackgroundWorker(gateway, trace);
    }

    @Bean
    LifecycleEvents lifecycleEvents(Trace trace) {
        return new LifecycleEvents(trace);
    }

    // Collector nằm trong context nhưng main giữ reference khi context đóng.
    static final class Trace {
        private final List<String> items = new ArrayList<>();

        synchronized void record(String value) {
            items.add(value);
            System.out.println(value);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    // Thành phần hạ tầng, phải chạy trước worker.
    static final class Gateway implements SmartLifecycle {
        private final Trace trace;
        private volatile boolean running;

        Gateway(Trace trace) {
            this.trace = trace;
        }

        @Override
        public synchronized void start() {
            if (running) {
                return;
            }
            running = true;
            trace.record("01 gateway.start phase=100");
        }

        @Override
        public synchronized void stop() {
            if (!running) {
                return;
            }
            running = false;
            trace.record("09 gateway.stop phase=100");
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                callback.run();
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }

        synchronized String handle(String value) {
            if (!running) {
                throw new IllegalStateException("Gateway is stopped");
            }
            trace.record("05 gateway: handled " + value);
            return "ACK:" + value;
        }

        @PreDestroy
        public void destroy() {
            if (isRunning()) {
                stop(); // Phòng thủ nếu cleanup không qua stop bình thường.
            }
            trace.record("11 gateway.@PreDestroy");
        }
    }

    // Thành phần nền cần Gateway còn hoạt động.
    static final class BackgroundWorker implements SmartLifecycle {
        private final Gateway gateway;
        private final Trace trace;

        private final CountDownLatch jobRequested = new CountDownLatch(1);
        private final CountDownLatch shutdownRequested = new CountDownLatch(1);
        private final CompletableFuture<String> result =
                new CompletableFuture<>();

        private volatile boolean running;
        private volatile boolean stopping;
        private volatile Runnable shutdownCallback;
        private Thread workerThread;

        BackgroundWorker(Gateway gateway, Trace trace) {
            this.gateway = gateway;
            this.trace = trace;
        }

        @Override
        public synchronized void start() {
            if (running) {
                return;
            }
            if (workerThread != null) {
                throw new IllegalStateException(
                        "This demo worker is one-shot and cannot restart");
            }
            if (!gateway.isRunning()) {
                throw new IllegalStateException(
                        "Gateway must be started before worker");
            }

            running = true;
            trace.record("02 worker.start phase=200");

            workerThread = new Thread(this::workLoop, "two-phase-worker");
            workerThread.setDaemon(true);
            workerThread.start();
        }

        CompletableFuture<String> submitOnce() {
            if (!running || stopping) {
                throw new IllegalStateException("Worker is not accepting jobs");
            }
            jobRequested.countDown();
            return result;
        }

        private void workLoop() {
            try {
                jobRequested.await();

                if (!stopping) {
                    try {
                        result.complete(gateway.handle("sample"));
                    } catch (RuntimeException ex) {
                        result.completeExceptionally(ex);
                    }
                } else {
                    result.cancel(false);
                }

                // Giữ worker tồn tại cho đến khi lifecycle stop.
                shutdownRequested.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                result.completeExceptionally(ex);
            } finally {
                running = false;
                trace.record("08 worker.stop completed phase=200");

                Runnable callback = shutdownCallback;
                if (callback != null) {
                    callback.run();
                }
            }
        }

        // Spring gọi biến thể này qua DefaultLifecycleProcessor.
        @Override
        public void stop(Runnable callback) {
            if (!running) {
                callback.run();
                return;
            }

            shutdownCallback = callback;
            stopping = true;            // Từ chối job mới.
            jobRequested.countDown();   // Đánh thức worker nếu chưa có job.
            shutdownRequested.countDown();

            // KHÔNG callback.run() tại đây.
            // Worker sẽ gọi callback sau khi thoát workLoop().
        }

        // Biến thể đồng bộ cho caller gọi stop() trực tiếp.
        @Override
        public void stop() {
            CountDownLatch finished = new CountDownLatch(1);
            stop(finished::countDown);
            try {
                if (!finished.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker stop timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while stopping worker", ex);
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 200;
        }

        @PreDestroy
        public void destroy() {
            if (isRunning()) {
                stop();
            }
            trace.record("10 worker.@PreDestroy");
        }
    }

    static final class LifecycleEvents {
        private final Trace trace;

        LifecycleEvents(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            trace.record("03 ApplicationReadyEvent");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            trace.record("07 ContextClosedEvent");
        }
    }
}
```

### 5.1. Tại sao source này là một ví dụ tự chứa?

- Một public top-level class có tên chính xác `TwoPhaseLifecycleApplication`, ở package `com.example.twophase`.
- Các class phụ `Trace`, `Gateway`, `BackgroundWorker` và `LifecycleEvents` nằm trong cùng file Java.
- Các bean được đăng ký bằng `@Bean` methods trong `@SpringBootApplication` class, không cần `@ComponentScan` bổ sung hay XML.
- `@DependsOn("gateway")` trỏ tới bean named `gateway` đã khai báo.
- `Gateway` và `BackgroundWorker` đều implement `SmartLifecycle`; các method `start`, `stop`, `isRunning`, `isAutoStartup` và `getPhase` có đầy đủ chữ ký.
- `@PreDestroy` dùng đúng namespace `jakarta.annotation` của Spring Boot 3.x.
- `CountDownLatch` và `CompletableFuture` thuộc JDK 17; không cần thư viện concurrency ngoài.
- `LifecycleEvents` là singleton được context quản lý, nên các `@EventListener` của nó nhận đúng event thuộc ứng dụng.
- Code không tạo web listener, không gọi database hoặc API network, và không đòi có thread scheduler của Spring.

### 5.2. Điều gì xảy ra khi context refresh?

1. Spring tạo/inject các beans cần thiết theo dependency graph.
2. `Gateway` và `BackgroundWorker` đã là objects, nhưng ban đầu `running=false`.
3. `DefaultLifecycleProcessor.onRefresh()` tìm các `SmartLifecycle` cần auto-start.
4. Phase 100 được bắt đầu trước phase 200: `Gateway.start()` đặt `running=true`.
5. `BackgroundWorker.start()` kiểm `gateway.isRunning()`, sau đó tạo một daemon thread để chờ job.
6. Boot tiếp tục mốc `ApplicationStartedEvent`, runners nếu có, rồi `ApplicationReadyEvent`.
7. Method `main` chỉ gửi job sau khi `SpringApplication.run` return.

**Vì sao worker không xử lý job trước dòng 04?** Vì thread chờ `jobRequested.await()`; chỉ `submitOnce()` mới gọi `jobRequested.countDown()`. Dù thread được CPU scheduler chạy sớm hay muộn, không có log xử lý job trước tín hiệu này.

### 5.3. Điều gì xảy ra khi xử lý một job?

- Main ghi log dòng 04 rồi gọi `submitOnce()`.
- `submitOnce()` đặt countdown cho `jobRequested` và trả `CompletableFuture<String>`.
- Thread worker được phép gọi `gateway.handle("sample")`. Gateway kiểm `running`, ghi log dòng 05 và trả `ACK:sample`.
- Worker gọi `result.complete("ACK:sample")`.
- Main đang đợi `get(5, SECONDS)` được đánh thức, xác nhận result rồi ghi dòng 06.

Đây là quan hệ đồng bộ hóa **không dựa vào sleep**: CompletableFuture không thể hoàn tất thành công theo code này trước khi gateway handle xong. `CountDownLatch` và Future còn thiết lập quan hệ memory visibility theo Java Concurrency API.

### 5.4. Điều gì xảy ra khi context.close()?

Vì `main` dùng try-with-resources, sau dòng 06 nó rời khối, Java gọi `context.close()`.

- Spring phát `ContextClosedEvent` khi đường close bình thường bắt đầu → dòng 07.
- Lifecycle processor chọn phase cao trước → gọi `BackgroundWorker.stop(Runnable)`.
- Worker đặt `stopping=true`, mở latch shutdown và **không gọi callback ngay**.
- Thread worker thoát `workLoop()`. Trong `finally`, nó ghi dòng 08 và gọi `shutdownCallback.run()`.
- Processor nhận thông báo phase 200 đã dừng, tiếp tục phase 100.
- `Gateway.stop()` ghi dòng 09. Không còn worker nào sử dụng gateway nữa.
- Trong giai đoạn destroy singleton, `BackgroundWorker.@PreDestroy` ghi dòng 10, sau đó `Gateway.@PreDestroy` ghi dòng 11 theo quan hệ phụ thuộc.
- `context.close()` trả về; main ghi dòng 12, kiểm trace và in `CHECK PASS`.

**Điều quan trọng nhất:** worker **không** báo stop complete ở thời điểm vừa được yêu cầu dừng. Spring chờ callback sau khi worker thread đã tới `finally`, vì vậy gateway phase thấp hơn vẫn còn sống trong lúc worker ngừng công việc.

### 5.5. Vì sao có cả @PreDestroy?

`SmartLifecycle.stop(...)` để điều phối việc **ngừng hoạt động** theo thứ tự. `@PreDestroy` dành cho **cleanup khi singleton bị destroy**. Một bean có thể cần cả hai: ví dụ dừng nhận message và drain trước, sau đó đóng các resource phụ trợ còn lại.

Ở demo, `@PreDestroy` gọi `stop()` **chỉ nếu vẫn running** như một biện pháp phòng thủ khi bootstrap thất bại giữa chừng hoặc một đường shutdown đặc biệt. Ở đường close bình thường, `stop` đã hoàn tất nên callback destroy chỉ in log.

Không coi `@PreDestroy` là thay thế cho `stop(Runnable)`: nếu đợi đến destruction mới ngừng consumer, Gateway có thể đang bị destroy và worker có thể dùng một tài nguyên đã đóng.

## 6. Chạy chương trình và dự đoán kết quả

### 6.1. Windows PowerShell

```powershell
.\gradlew.bat bootRun
```

### 6.2. macOS/Linux

```bash
./gradlew bootRun
```

Cần JDK 17+ với Gradle Wrapper tương thích. Từ project root, đảm bảo Gradle resolve được Spring Boot 3.3.13 và các dependencies. Không chạy lệnh trong thư mục `src/main/java`.

Nếu chạy đúng mã nguồn và môi trường bình thường, **các dòng do `Trace.record` và `System.out.println` trong source này tự in** theo thứ tự:

```text
01 gateway.start phase=100
02 worker.start phase=200
03 ApplicationReadyEvent
04 main: submit sample
05 gateway: handled sample
06 main: job observed
07 ContextClosedEvent
08 worker.stop completed phase=200
09 gateway.stop phase=100
10 worker.@PreDestroy
11 gateway.@PreDestroy
12 main: context closed
CHECK PASS
```

Gradle có thể in thêm các dòng task/build. Vì `logging.level.root=ERROR`, các log startup bình thường của Boot được giảm bớt; output kiểm chứng chỉ liệt kê những dòng **mã bài học chủ động in**, không tuyên bố toàn bộ console chính xác chỉ có 13 dòng trong mọi launcher.

### 6.3. Tại sao thứ tự ổn định?

| Mốc | Quan hệ bảo đảm |
| --- | --- |
| 01 trước 02 | Phase 100 start trước phase 200; worker còn kiểm gateway running |
| 02 trước 03 | `SmartLifecycle` auto-start trong context refresh, Boot ready event đến sau |
| 03 trước 04 | `SpringApplication.run` phát Ready event trước khi return trong đường startup thành công |
| 04 trước 05 | Main log trước khi mở `jobRequested` latch |
| 05 trước 06 | Worker hoàn thành `CompletableFuture` sau gateway.handle, main `get` trước log |
| 07 trước 08 | `ContextClosedEvent` trước `LifecycleProcessor.onClose()` bình thường |
| 08 trước 09 | Phase 200 chỉ báo callback khi worker thoát, sau đó phase 100 mới stop |
| 09 trước 10 | Lifecycle stop diễn ra trước singleton destruction bình thường |
| 10 trước 11 | Worker được khai báo phụ thuộc Gateway, dependent bean destroy trước dependency |
| 11 trước 12 | `context.close()` hoàn tất mới return khỏi try-with-resources |

Bảng nêu **quan hệ thứ tự trong đúng chương trình này**, không phải thứ tự toàn cục giữa mọi Java threads, mọi Spring beans hoặc mọi hệ điều hành. Thêm một custom asynchronous event multicaster hoặc dependency phức tạp có thể làm trace cần thiết kế lại; không copy assertion theo thứ tự vào hệ thống khác mà không xem context.

### 6.4. Một lưu ý về thread daemon

Thread do demo tạo được đặt `setDaemon(true)`. Điều này giúp ví dụ không vô tình giữ JVM chạy mãi nếu có lỗi test; **không** có nghĩa daemon thread được bảo đảm hoàn tất trước khi process exit.

Trong demo, main chờ Future, và `context.close()` chờ `SmartLifecycle.stop(Runnable)` báo hoàn tất. Vì thế lifecycle đảm nhiệm việc ngừng worker có kiểm soát; daemon flag không thay logic đó. Với ứng dụng phục vụ dài hạn, hãy để container quản lý executor/scheduler hoặc worker ownership phù hợp, không lấy daemon thread làm giải pháp shutdown.

### 6.5. Vì sao không dùng Thread.sleep để chờ?

Một code như:

```java
worker.submitOnce();
Thread.sleep(100);
context.close();
```

là **phản ví dụ**. Trên máy bận, job có thể chưa được schedule trong 100 ms; trên máy nhanh, nó hoàn tất từ sớm. `sleep` chỉ đoán timing chứ không chứng minh success.

Trong source đầy đủ, `CompletableFuture.get(5, TimeUnit.SECONDS)` kiểm **kết quả thực sự**, có deadline và có thể propagate failure. Khi dừng, callback báo **thực sự đã thoát** thay vì log “stop requested” rồi đóng dependency ngay.


## 7. Test tự động: assert phase và shutdown trace

Vì bài này có một chuỗi mốc cụ thể, nên bổ sung JUnit 5 test chạy `SpringApplication` thật để kiểm order. Nó tái sử dụng project và source ở trên, không tạo các bean khác.

Tạo **`src/test/java/com/example/twophase/TwoPhaseLifecycleApplicationTest.java`**:

```java
package com.example.twophase;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class TwoPhaseLifecycleApplicationTest {

    @Test
    void workerStartsAfterGatewayAndStopsBeforeGateway() throws Exception {
        SpringApplication app =
                new SpringApplication(TwoPhaseLifecycleApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        TwoPhaseLifecycleApplication.Trace trace;

        try (ConfigurableApplicationContext context = app.run()) {
            trace = context.getBean(
                    TwoPhaseLifecycleApplication.Trace.class);

            var gateway = context.getBean(
                    TwoPhaseLifecycleApplication.Gateway.class);
            var worker = context.getBean(
                    TwoPhaseLifecycleApplication.BackgroundWorker.class);

            assertThat(gateway.isRunning()).isTrue();
            assertThat(worker.isRunning()).isTrue();

            trace.record("04 main: submit sample");
            assertThat(worker.submitOnce().get(5, TimeUnit.SECONDS))
                    .isEqualTo("ACK:sample");
            trace.record("06 main: job observed");

            assertThat(trace.snapshot()).containsExactly(
                    "01 gateway.start phase=100",
                    "02 worker.start phase=200",
                    "03 ApplicationReadyEvent",
                    "04 main: submit sample",
                    "05 gateway: handled sample",
                    "06 main: job observed");
        }

        // try-with-resources đã đóng context.
        trace.record("12 main: context closed");

        assertThat(trace.snapshot()).containsExactly(
                "01 gateway.start phase=100",
                "02 worker.start phase=200",
                "03 ApplicationReadyEvent",
                "04 main: submit sample",
                "05 gateway: handled sample",
                "06 main: job observed",
                "07 ContextClosedEvent",
                "08 worker.stop completed phase=200",
                "09 gateway.stop phase=100",
                "10 worker.@PreDestroy",
                "11 gateway.@PreDestroy",
                "12 main: context closed");
    }
}
```

Code dùng `var` (hỗ trợ từ Java 10) để tránh viết dài tên nested static class trong test. Vì file test cùng package `com.example.twophase`, nó được phép truy cập các nested classes và method package-private của demo.

### 7.1. Chạy test

macOS/Linux:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Để chỉ chạy test đã tạo:

```bash
./gradlew test --tests "com.example.twophase.TwoPhaseLifecycleApplicationTest"
```

Nếu assertion đúng, Gradle `test` task thành công. Không cam kết một stdout test runner có định dạng chính xác giống nhau trên mọi bản Gradle; những chuỗi trong `containsExactly` là kết quả kiểm chứng chính.

### 7.2. Vì sao dùng SpringApplication thay ApplicationContextRunner?

`ApplicationContextRunner` cũng tạo và refresh một `ApplicationContext`, do đó có thể kiểm `SmartLifecycle.start()`, `stop(Runnable)` và `ContextClosedEvent`. Nhưng nó **không tự gọi `SpringApplication.run`**, nên không tự phát `ApplicationReadyEvent`. Test trong mục này muốn kiểm cả **context lifecycle** và **mốc Boot Ready**, vì vậy gọi một `SpringApplication` thực với `WebApplicationType.NONE` là đúng phạm vi.

Nếu muốn test **chỉ** thứ tự phase và các destruction callbacks, có thể dùng `ApplicationContextRunner` trong unit/auto-config test; phải bỏ assertion dựa vào `ApplicationReadyEvent` hoặc tự tách nó khỏi test.

### 7.3. Vì sao test không dùng Thread.sleep?

Nó kiểm `Future.get(timeout)`, vốn gắn với completion của computation. `stop(Runnable)` phối hợp với lifecycle processor bảo đảm phase 200 hoàn tất trước khi phase 100 bị dừng. Test chạy với scheduler timing khác nhau vẫn phải giữ được **thứ tự tương đối**.

Không nên kiểm “worker thread ID phải là 42”, “job chạy trong dưới 5 ms” hay “thread phase 200 luôn có CPU trước event ready”. Đây không phải các contract mà `SmartLifecycle` bảo đảm.

### 7.4. Test thêm đường shutdown khi chưa có job

Bài tập mở rộng: khởi động Spring context nhưng **không gọi `submitOnce()`**, sau đó đóng ngay. Trong source, `stop(Runnable)` sẽ mở `jobRequested` để đánh thức worker; `stopping=true` khiến thread **bỏ qua job** và exit, thay vì chờ mãi ở latch. Kết quả:

- Không có dòng `05 gateway: handled sample`.
- Không có dòng `06 main: job observed`.
- Vẫn có `worker.stop completed phase=200` trước `gateway.stop phase=100`.

Nếu test biến thể, bỏ các assertion mặc định về dòng 04–06 và kiểm các mốc còn lại. Điều này chứng minh shutdown phải hoạt động cả khi worker **chưa từng có công việc**.

## 8. Phân tích sâu SmartLifecycle.stop(Runnable)

### 8.1. Vì sao callback phải xuất hiện sau khi dừng thật?

Spring Framework 6.1 nói rõ `DefaultLifecycleProcessor` sử dụng `stop(Runnable)` và chờ callback của các components thuộc phase để biết shutdown phase đã hoàn tất. Với worker bất đồng bộ:

```text
Thread đóng context                 Background worker thread
------------------                 ------------------------
stop(callback) được gọi
  |
  +-- stopping=true
  +-- release shutdown latch ----> thấy tín hiệu shutdown
  |                                |
  |                                +--> xử lý xong việc đang chạy
  |                                +--> thoát workLoop
  |                                +--> running=false
  |                                +--> callback.run()
  |                                         |
  +<-------- callback acknowledged --------+
  |
  +--> chuyển tới phase thấp hơn
  +--> gateway.stop()
```

Nếu code gọi callback ngay sau `shutdownRequested.countDown()`, đó mới là **stop requested**, chưa phải **stop completed**. Lifecycle processor có thể dừng gateway trong lúc worker vẫn đang xử lý một message.

### 8.2. Callback chỉ cần chạy khi nào?

Theo hợp đồng, khi `DefaultLifecycleProcessor` gọi `SmartLifecycle.stop(Runnable)` với component đang running, implementation phải gọi callback **khi việc stop hoàn tất**. Nếu component đã stopped trước, implementation có thể gọi callback ngay để không làm processor phải chờ.

Trong demo:
- `stop(Runnable)` khi đang chạy: lưu callback, set `stopping`, mở latch; worker gọi callback ở `finally`.
- `stop(Runnable)` khi không running: callback chạy ngay.
- `stop()`: dùng latch của caller để đợi callback; không được bỏ callback hoặc trả về trước khi dừng khi người gọi cần biến thể đồng bộ.

**Giới hạn cố ý của demo:** Nó là worker dùng một thread và một job, và giả định một lifecycle coordinator dừng component trong một lần đóng context. Nếu có nhiều caller đồng thời gọi `stop(Runnable)`, code cần **đăng ký/hoàn tất nhiều callbacks an toàn** để không ghi đè callback cũ. Đó là yêu cầu production, không nên giấu đi dưới danh nghĩa “method có synchronized là đủ”.

### 8.3. Vì sao stop() và stop(Runnable) đều được implement?

`SmartLifecycle` kế thừa `Lifecycle.stop()`. Trong quá trình Spring lifecycle shutdown, processor gọi **biến thể `stop(Runnable)`**, không đương nhiên gọi `stop()` thay cho nó; nếu muốn dùng chung logic, phải ủy quyền rõ.

Bài demo:
- `stop(Runnable)` định nghĩa protocol shutdown chính.
- `stop()` là adapter đồng bộ đợi callback với timeout năm giây.

Trong production, hai biến thể phải thống nhất về trạng thái, idempotency và xử lý khi bị interrupt. Không được viết một biến thể gọi `shutdownNow()`, còn biến thể khác chỉ đổi boolean, khiến behavior khác nhau tùy API được gọi.

### 8.4. Timeout của Spring là timeout theo phase

Trong Spring Framework 6.1, `DefaultLifecycleProcessor` có **mặc định 30 giây cho mỗi shutdown phase**. Spring Boot 3.3 có property:

```properties
spring.lifecycle.timeout-per-shutdown-phase=10s
```

Trong demo, 10 giây là deadline processor đợi callback của phase. Một ứng dụng có nhiều phases còn phải tính thời gian của các phases khác và hoạt động cleanup sau đó.

**Nếu timeout:** processor có thể tiếp tục đi tới phase tiếp theo hoặc destruction dù worker chưa thực sự dừng. Do đó app phải có timeout I/O, khả năng interrupt/cooperative cancellation và thiết kế dependency an toàn. Không hiểu timeout như “JVM tự hủy thread và rollback mọi side effects sau 10s”.

### 8.5. Callback báo một mốc kỹ thuật, không tự chứng minh business commit

Một worker có thể dừng thread nhưng vẫn còn message chưa ack ở broker hoặc transaction chưa commit. Trong hệ thống thật, hãy định nghĩa `stop complete` bằng:

- ngừng nhận job mới;
- đợi hoặc checkpoint những job đang chạy;
- ack/nack các message theo protocol;
- flush/commit/close tài nguyên đúng order;
- mới gọi callback.

Nếu các bước trên không thể hoàn tất, không tự báo **success** chỉ vì thread đã dừng. Cần log lỗi, timeouts, retry state, idempotency và chính sách recovery rõ.

## 9. Vì sao cần @DependsOn khi đã có getPhase()?

Hai cơ chế có phạm vi khác:

| Cơ chế | Định nghĩa | Khi phù hợp |
| --- | --- | --- |
| `getPhase()` | Thứ tự start/stop theo **nhóm phase** | Hệ thống biết “hạ tầng chạy trước consumer”, không nhất thiết có reference trực tiếp |
| Constructor injection | Worker nhận đúng object Gateway | Có tương tác trực tiếp và dependency type cụ thể |
| `@DependsOn("gateway")` | Quan hệ bean definition tường minh | Muốn bảo đảm thứ tự lifecycle ngay cả khi phase thay đổi |
| `@Order` | Ordering cho những collection/extension points cụ thể | Không phải API chính để sắp `SmartLifecycle` phases |
| `@PostConstruct` | Bean initialization callback | Không phải mốc start/stop hoạt động |
| `ContextClosedEvent` | Thông báo context đang đóng | Không chứng minh worker đã dừng |

Trong ví dụ, cả ba hướng đều nhất quán:

```text
worker ---- uses ----> gateway
phase(worker)=200 > phase(gateway)=100
@DependsOn(worker -> gateway)
```

Khi thêm hạ tầng thứ ba, phải thiết kế dependency graph rõ thay vì chỉ chọn phase tùy tiện. Chẳng hạn `consumer(200)` cần `decoder(150)` và `gateway(100)`: start 100→150→200, shutdown 200→150→100 nếu dependency thích hợp và không có ràng buộc đối nghịch.

### 9.1. Thí nghiệm đổi phase cho “sai”

Giữ `@DependsOn("gateway")` nhưng đổi:

```java
// Trong BackgroundWorker.getPhase()
return 50;  // Thấp hơn Gateway 100, cố ý tạo mâu thuẫn.
```

Đây là **đoạn sửa trong class hiện có**, không dán thành một method thứ hai. Theo hợp đồng Spring, dependency tường minh được ưu tiên khi start/stop các bean liên quan; do đó gateway vẫn phải start trước worker, và worker vẫn stop trước gateway.

Tuy nhiên, việc cấu hình phase mâu thuẫn với dependency là **mùi thiết kế**: khó cho người đọc và dễ tạo thứ tự bất ngờ với các component thứ ba. Trong production, giữ phase và dependency cùng chiều như 100/200.

### 9.2. Thí nghiệm bỏ DependsOn nhưng giữ injection

Nếu bỏ annotation `@DependsOn`, worker vẫn nhận một `Gateway` qua method `@Bean` và Spring phải tạo dependency đó trước khi tạo worker. Nhưng có thể khác cách processor xử lý các quan hệ lifecycle tường minh khi thiết kế phức tạp. Bài này cố ý giữ `@DependsOn` để **đặt ràng buộc lifecycle rõ ràng**, không dựa vào suy đoán về trình tự constructor.

### 9.3. Thí nghiệm hai bean cùng phase

Nếu hai worker có `getPhase()==200` mà không có dependency giữa chúng, không được dựa vào thứ tự stop/start mà JVM tình cờ ghi log. `SmartLifecycle` cho phép các component cùng phase được điều phối theo thứ tự không đảm bảo hợp đồng nghiệp vụ. Hãy dùng phase khác hoặc dependency tường minh nếu một worker buộc phải chờ worker còn lại.

## 10. Không nhầm lifecycle start với ứng dụng đã ready

`SmartLifecycle.start()` chạy trong `ApplicationContext.refresh()` (với `isAutoStartup()==true`), tức **trước** `ApplicationStartedEvent` và `ApplicationReadyEvent` của Spring Boot 3.3. Nhưng trong nhiều implementation, `start()` có thể chỉ **submit** một tác vụ nền rồi return.

Phân biệt:

1. **Bean tồn tại:** object được đăng ký.
2. **Lifecycle đã nhận start:** `start()` được gọi.
3. **Worker thực sự nhận việc:** thread/executor/consumer đã sẵn sàng.
4. **Ứng dụng được Boot công bố ready:** `ApplicationReadyEvent` và trạng thái readiness của Boot theo pipeline thông thường.
5. **Nghiệp vụ sẵn sàng:** những điều kiện riêng như kết nối broker, quyền truy cập và dữ liệu bắt buộc đã được xác nhận.

Trong demo, `BackgroundWorker.start()` tạo daemon thread rồi return. Main chỉ gửi công việc **sau `SpringApplication.run` return**. Điều đó không đồng nghĩa rằng một production worker đã kết nối broker thật xong ngay lúc `start` return.

Nếu sẵn sàng của worker là điều kiện trước khi nhận traffic:

- Thực hiện handshake/health check với deadline trước khi công bố readiness, hoặc
- Đánh dấu trạng thái readiness riêng ở mức ứng dụng và chỉ chuyển `ACCEPTING_TRAFFIC` khi đạt điều kiện, hoặc
- Dùng runner/initialization orchestration có chờ kết quả bắt buộc.

**Đừng** chỉ set `running=true` trước khi một connection được mở rồi gọi đó là thành công. `isRunning()` nên thể hiện trạng thái mà component thực sự có thể bảo đảm, và readiness có thể là một tín hiệu mạnh hơn.

## 11. Dừng context và hủy singleton: các sự kiện khác nhau

Trong đường close bình thường của Spring Framework 6.1:

```text
context.close()
  |
  +--> ContextClosedEvent
  +--> LifecycleProcessor.onClose()
  |      +--> stop phase cao trước
  |      +--> stop phase thấp sau
  +--> destroyBeans()
  |      +--> @PreDestroy / DisposableBean / custom destroy method
  +--> close bean factory và cleanup context
```

Vì vậy trong demo:

- Dòng **07 `ContextClosedEvent`** nói shutdown **bắt đầu**.
- Dòng **08** nói thread worker **đã thoát** và callback stop được báo.
- Dòng **09** nói gateway **đã dừng**.
- Dòng **10,11 `@PreDestroy`** là bước destroy của singleton sau lifecycle stop bình thường.
- Dòng **12** xác nhận `context.close()` đã return.

**Không lấy `ContextClosedEvent` làm bằng chứng “mọi task hoàn tất”**. Nếu một listener đóng context tự submit thêm async work rồi return, Spring có thể tiến hành dừng executor ngay sau đó. Những việc cần được drain phải đặt trong protocol `SmartLifecycle.stop(Runnable)` hoặc một owner tương đương.

### 11.1. context.stop() khác context.close()

`context.stop()` là thao tác lifecycle, làm container dừng các component theo contract và có thể cho phép `context.start()` trong context còn hoạt động. Nó **không** destroy toàn bộ bean và không có nghĩa JVM đã exit.

`context.close()` đóng context, dừng lifecycle components rồi destroy singleton đủ điều kiện; context đã đóng thì không nên start lại.

**Một giới hạn của demo:** Worker được viết theo mô hình one-shot và cố ý ném exception nếu `start()` được gọi lại sau khi thread cũ đã kết thúc. Vì vậy, **không dùng demo nguyên xi để kiểm `context.stop(); context.start()`**. Nếu cần restartable component thật, hãy tạo một `RunState` mới cho mỗi lần start (thread, latch, future, callback state), bảo đảm idempotent start/stop và đóng trạng thái cũ xong mới mở trạng thái mới.

### 11.2. Startup failure và @PreDestroy

Nếu `Gateway.start()` throw khi context đang refresh, hoặc `BackgroundWorker.start()` throw vì dependency chưa sẵn sàng, Spring Boot có thể đi vào startup failure handling. Trong đường refresh bị hủy, **không bảo đảm mọi lifecycle bean đều đã nhận stop trước destruction**.

Do đó các method `@PreDestroy` trong ví dụ **kiểm trạng thái** và gọi stop phòng thủ khi còn chạy. Trong production, cleanup phải chịu được object mới được tạo một phần, connection chưa mở hoặc worker thread chưa được start.

Đừng viết `@PreDestroy` luôn gọi `thread.join()` khi `thread==null`, hoặc đóng connection chưa bao giờ được mở mà không kiểm tra trạng thái.

### 11.3. SIGTERM và SIGKILL

- Khi `context.close()` được gọi hoặc JVM có cơ hội thực thi shutdown hook bình thường, Spring có thể điều phối stop theo phase.
- Khi SIGKILL, crash JVM, mất điện hoặc kill cưỡng bức, callback Java **không được bảo đảm chạy**.
- Spring lifecycle không thay thế durable queue, checkpoint, idempotency hoặc transaction protocol khi phải phục hồi những job đã được nhận.

Đây là lý do worker thật phải có **crash recovery** bên cạnh graceful stop.

## 12. Những lỗi dễ mắc khi tự triển khai SmartLifecycle

| Triệu chứng / thiết kế sai | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Worker phase thấp hơn gateway dù phụ thuộc gateway | Có thể start trước dependency hoặc stop sau dependency nếu không có quan hệ tường minh | Gateway phase 100, worker 200; khai báo dependency |
| Chỉ dùng `@Order` để sắp worker lifecycle | `@Order` không phải `SmartLifecycle.getPhase` | Override `getPhase` |
| `isRunning()` luôn trả true | Processor không biết trạng thái thật, khó stop idempotent | Dùng trạng thái thread-safe cập nhật đúng |
| `start()` tạo thread mỗi lần gọi, không kiểm running | Trùng worker, double-consume message | Start idempotent hoặc thiết kế RunState tái khởi động rõ |
| `stop(Runnable)` gọi callback ngay sau submit shutdown | Worker có thể vẫn đang sử dụng gateway | Callback sau drain và thread exit |
| `stop(Runnable)` quên gọi callback | Processor đợi timeout phase, shutdown chậm | Gọi callback đúng lúc, kể cả đường lỗi |
| `stop()` là no-op còn stop(Runnable) dừng thật | API không nhất quán | Dùng chung logic shutdown |
| Worker tự tạo non-daemon thread mà không quản lý | JVM có thể không thoát | Owner quản lý thread, stop/join/deadline |
| Thread daemon được xem như graceful shutdown | Daemon không bảo đảm hoàn tất work | Chờ Future + lifecycle callback |
| Worker tiếp tục nhận message sau khi stop requested | Có thể bỏ mất work khi gateway stop | Đặt stopping flag/disable subscription trước drain |
| Không đợi in-flight tasks | Giao dịch dở dang, mất message | Await/checkpoint/ack trước callback |
| `Thread.sleep` được dùng để test order | Race phụ thuộc scheduling | Latch/Future/trace có synchronization |
| Gọi `context.close()` trong `@PostConstruct` | Context có thể chưa refresh xong | Quản lý shutdown ở orchestrator phù hợp |
| Dùng `@PreDestroy` thay toàn bộ stop protocol | Dependency có thể bị dừng sai thời điểm | Dừng theo SmartLifecycle trước destroy |
| Dùng `@DependsOn` nhưng sai tên bean | Bean creation có thể thất bại | Đối chiếu tên bean chính xác |
| Hai beans cùng phase, không ràng buộc nhưng assert thứ tự | Ordering không phải business contract | Khai báo phase/dependency |
| Lạm dụng phase `Integer.MAX_VALUE` cho mọi worker | Khó điều phối với server/executor có phase riêng | Dùng phase rõ và xem infrastructure interactions |
| Đánh dấu `running=false` trước khi thread thật dừng | Spring có thể coi component stopped quá sớm | Update trạng thái khi ngừng thật |
| Stop timeout rồi bỏ qua lỗi | Có thể đóng gateway khi worker còn dùng | Bounded drain, log, interrupt/retry/recovery |
| Gọi callback hai lần hoặc từ nhiều stop callers | Processor/collector có thể bị double notify | Thiết kế callback completion đúng một lần |
| Worker startup thất bại vẫn return ready | Dịch vụ nhận traffic khi dependency chưa sẵn sàng | Fail-fast hoặc readiness gate |
| Tưởng lifecycle callback luôn chạy sau SIGKILL | Crash không cho phép Java cleanup | Checkpoint/durable queue và reconciliation |

### 12.1. Debug khi output đảo thứ tự

Nếu thấy worker start trước gateway:

1. Xác minh hai bean đều thực sự implement `SmartLifecycle` và được Spring quản lý.
2. In `getPhase()` của **instance** thực tế, tránh nhầm class cấu hình với object.
3. Kiểm `@DependsOn` hoặc bean dependency graph, tên bean.
4. Có ai gọi `worker.start()` thủ công trong constructor/`@PostConstruct`/listener không?
5. Có worker tự mở thread trong constructor trước khi lifecycle processor chạy không?
6. Có đang xem log từ thread async và suy thành thứ tự callback đồng bộ không?

Nếu thấy gateway stop trước worker hoàn tất:

1. `stop(Runnable)` của worker có gọi callback **quá sớm** không?
2. Worker đã thật sự ngừng nhận job và drain inflight chưa?
3. Có phase timeout khiến processor đi tiếp không?
4. Có component khác ngoài Spring đóng gateway thủ công không?
5. Có bean dependency tường minh hoặc phase bị thay đổi trong profile khác không?
6. Có refresh failure/SIGKILL mà bạn nhầm là close bình thường không?

### 12.2. Quan sát tốt hơn trong production

Log tối thiểu:

```text
component=gateway phase=100 transition=starting
component=gateway phase=100 transition=running
component=consumer phase=200 transition=starting
component=consumer phase=200 transition=running
component=consumer phase=200 transition=stopping inflight=3
component=consumer phase=200 transition=stopped inflight=0
component=gateway phase=100 transition=stopped
```

Đây là **schema log gợi ý**, không phải stdout của demo. Tùy nhu cầu, thêm job ID, durations, queue backlog, lastSuccessAt, cancellation count, retry count và exception type; tránh ghi token/password/payload nhạy cảm.

Đối với lỗi production, một trace có timestamps và phase hữu ích hơn một Boolean `running` duy nhất. Nhưng không dùng timestamps để suy ra happens-before khi log từ nhiều threads không có synchronization; dùng completion signals có contract.


## 13. Mở rộng demo thành worker nền thực sự

Demo chỉ có một message để người học nhìn rõ phase. Muốn dùng cho message consumer hoặc poller dài hạn, phải thiết kế thêm các điểm sau.

### 13.1. Queue và backpressure

Nếu dùng `BlockingQueue<Job>`:

- `start()` đăng ký/khởi động worker loop.
- Caller `submit` đưa job vào queue có **capacity hữu hạn**.
- Khi queue đầy, trả rejected/busy hoặc đẩy sang một broker durable.
- `stop` ngừng nhận job, đợi queue drain hoặc chuyển pending jobs sang trạng thái recoverable.
- `stop(Runnable)` báo hoàn tất sau khi đã xử lý đủ chính sách.

Không dùng một queue vô hạn làm bằng chứng không mất việc: JVM crash có thể làm mất toàn bộ pending jobs chỉ nằm trong memory.

### 13.2. Dùng executor do Spring quản lý

Một service phức tạp thường nên dùng `ThreadPoolTaskExecutor`, `TaskExecutor`, scheduler hoặc thư viện consumer được Spring quản lý, thay vì tạo `new Thread(...)` thủ công. Khi đó cần hiểu **hai chủ sở hữu lifecycle**:

- Bean worker quản lý subscription/job semantics.
- Executor bean quản lý thread pool và task execution.

Nếu worker phụ thuộc executor, phải chọn phase/depends-on sao cho worker **stop và drain** trước khi executor bị shutdown. Không tự đóng một executor shared mà nhiều bean còn dùng.

### 13.3. Thiết kế stop nhiều lần không ghi đè callback

Trong demo `shutdownCallback` chỉ lưu **một** callback cho một lần stop do Spring điều phối. Production nên định nghĩa một terminal completion signal, ví dụ `CompletableFuture<Void> stopped`, rồi cho mọi caller đăng ký callback lên **cùng future**:

```java
stopped.whenComplete((ignored, error) -> callback.run());
requestShutdownOnce();
```

Đây là **snippet minh họa**, cần `stopped`/`requestShutdownOnce` và chính sách xác định đã stop thật. Ý tưởng: mỗi caller có thể được thông báo, không ghi đè callback của người trước. Nếu shutdown fail, hãy log/metrics và trả outcome phù hợp chứ không silently báo hoàn tất thành công.

### 13.4. Cho phép context.stop()/start() nhiều chu kỳ

Một `SmartLifecycle` production-grade có thể được start/stop nhiều lần khi context còn sống. Nếu muốn hỗ trợ, thiết kế state machine:

```text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                       ^                    |
                       +---- STARTING <-----+
```

Mỗi lần `start` từ `STOPPED` cần tạo mới thread, latches, subscription, future và callback registry; tránh reuse `CountDownLatch(0)` hoặc một completed Future từ vòng trước. Đảm bảo có synchronizing lock/CAS giữa `STARTING` và `STOPPING` để không tạo double workers.

Nếu không hỗ trợ restart, cần **ghi rõ contract và không quảng bá component như một lifecycle bean có thể pause/resume vô hạn**. Demo chủ động throw khi restart thay vì lặng lẽ giữ một thread đã chết.

### 13.5. Timeout có nhiều tầng

Không dùng một `spring.lifecycle.timeout-per-shutdown-phase` để giả định đủ mọi thứ. Cần budget cho:

- HTTP/database/broker I/O.
- Queue drain và ack.
- Executor await termination.
- Spring phase stop callbacks.
- Shutdown hooks và Kubernetes termination grace period.
- Timeout của caller đang `Future.get`.

Các budget phải **tương thích và có khoảng dư**. Nếu Kubernetes kill process sau 10 giây nhưng mỗi phase đợi 30 giây, không thể trông đợi graceful shutdown hoàn tất.

### 13.6. Phase giữa các thư viện

Spring Boot app thật có embedded web server, schedulers, task executors, message listener containers và nhiều infrastructure beans cũng implement `SmartLifecycle`. Một phase tự chọn phải xét thứ tự stop của **toàn bộ dependencies**. Hai số 100/200 trong bài là đủ để minh họa, nhưng không phải chuẩn phase dành cho broker/JDBC/executor.

Nếu consumer cần một shared HTTP client, message broker connector và thread pool, vẽ dependency graph thật rồi chọn phase tương ứng; thêm explicit dependency khi cần. Đừng gán `Integer.MAX_VALUE` cho mọi consumer vì nghĩ “càng cao càng tốt” mà không xét những server/executor cũng có phase cao.

## 14. Bài tập thực hành mở rộng

**Bài 1 — đổi phase.** Thay `Gateway.getPhase()` thành 50, giữ worker 200. Kỳ vọng gateway vẫn start trước và stop sau worker. Quan sát trace và cập nhật nhãn/expected output tương ứng.

**Bài 2 — thử mâu thuẫn phase và dependency.** Giữ `@DependsOn("gateway")` nhưng đặt worker phase 50, gateway phase 100. Giải thích vì sao explicit dependency có thể ưu tiên phase. Không nên giữ cấu hình mâu thuẫn trong production.

**Bài 3 — bỏ callback.** Trong `BackgroundWorker.stop(Runnable)` cố ý không bao giờ gọi callback sau worker exit. Quan sát thời gian shutdown theo `spring.lifecycle.timeout-per-shutdown-phase`. Đây là bài tập lỗi có kiểm soát; khôi phục callback sau khi thử.

**Bài 4 — callback quá sớm.** Gọi `callback.run()` ngay trong `stop(Runnable)`, trước khi thread thoát. Thêm giả lập I/O chậm có latch và xem gateway có thể bị stop khi worker chưa xong. Đây là phản ví dụ, không dùng trong code thật.

**Bài 5 — chưa có job.** Khởi động context rồi close mà không gọi `submitOnce()`. Worker phải thoát và phase 200 hoàn tất, không treo ở `jobRequested.await()`.

**Bài 6 — lỗi gateway.** Đổi `Gateway.handle` thành ném `IllegalStateException`. Main phải nhận exceptional completion từ `CompletableFuture.get`; vì code dùng try-with-resources, context vẫn được đóng. Trace thành công nguyên bản không còn hợp lệ; assert failure path riêng.

**Bài 7 — isAutoStartup=false.** Đổi worker `isAutoStartup()` thành false. Xác nhận worker không auto-start tại refresh. Thử gọi `context.start()` hoặc `worker.start()` có chủ đích, sau đó stop đúng. Không sử dụng nguyên main vì nó đang giả định worker đã running.

**Bài 8 — thread safety.** Gọi `submitOnce()` từ nhiều thread. Quan sát giới hạn one-shot worker; sửa thành API có queue, từ chối duplicate hoặc dùng `AtomicBoolean` để chấp nhận đúng một submission. Không công bố demo đang hỗ trợ nhiều job khi nó chỉ có một Future.

**Bài 9 — thời điểm readiness.** Cho `Gateway.start` mô phỏng handshake có lỗi. Quyết định fail-fast trong refresh hay dùng một readiness gate nếu component có thể phục hồi. Nêu bằng chứng ready cần mạnh hơn việc tạo thread.

**Bài 10 — tích hợp broker thật.** Thay in-memory Gateway bằng adapter của broker test container; implement stop của consumer để unsubscribe/drain/ack trước khi connector stop. Ghi rõ timeout/ack/recovery cho các message đã nhận.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Hai bean phase 100 và 200 sẽ start theo thứ tự nào?

**Đáp:** Phase 100 trước, phase 200 sau, trừ khi có dependency tường minh yêu cầu một quan hệ mạnh hơn cần tôn trọng.

**Câu 2.** Khi shutdown bình thường, phase nào stop trước?

**Đáp:** Phase 200 trước phase 100.

**Câu 3.** Vì sao worker phase 200 cần Gateway phase 100?

**Đáp:** Worker gọi `Gateway.handle(...)`. Gateway phải được start trước khi worker hoạt động, và phải còn sống khi worker đang drain/stop.

**Câu 4.** `@DependsOn("gateway")` có giống constructor injection không?

**Đáp:** Không. Constructor injection cung cấp object dependency, còn `@DependsOn` diễn đạt quan hệ bean definition/lifecycle rõ ràng.

**Câu 5.** `@Order(1)` trên worker có tự thay `getPhase()` không?

**Đáp:** Không. SmartLifecycle processor lấy phase từ `getPhase()`/`Phased` và dependency graph.

**Câu 6.** `SmartLifecycle` auto-start lúc nào?

**Đáp:** Khi context refresh và `isAutoStartup()` trả true; không phải do `ApplicationReadyEvent` tự gọi.

**Câu 7.** `SmartLifecycle.DEFAULT_PHASE` trong Spring 6.1 có giá trị gì?

**Đáp:** `Integer.MAX_VALUE`. Trong bài đã override cụ thể 100/200.

**Câu 8.** Vì sao không gọi callback ngay lúc `stop(Runnable)` vừa set stopping?

**Đáp:** Worker có thể còn đang chạy; callback phải báo **đã dừng thật** để dependency phase thấp không bị đóng sớm.

**Câu 9.** Spring gọi `stop()` hay `stop(Runnable)` khi stop SmartLifecycle qua processor?

**Đáp:** Biến thể `stop(Runnable)`. Implementation chịu trách nhiệm ủy quyền tới logic chung nếu cần.

**Câu 10.** Nếu worker chưa từng được giao job, phải xử lý stop thế nào?

**Đáp:** Đánh thức nó khỏi latch/queue chờ, đặt stopping state, cho worker exit, rồi gọi callback.

**Câu 11.** `@PreDestroy` trong Gateway có thể thay worker.stop không?

**Đáp:** Không. Nếu Gateway bị destroy trước khi consumer ngừng, consumer có thể dùng resource đã đóng.

**Câu 12.** `ContextClosedEvent` có nghĩa mọi worker đã dừng chưa?

**Đáp:** Chưa. Nó được phát trước lifecycle stop trong đường close bình thường.

**Câu 13.** Timeout mặc định của `DefaultLifecycleProcessor` Spring 6.1 là gì?

**Đáp:** 30 giây **mỗi phase**; có thể chỉnh bằng `spring.lifecycle.timeout-per-shutdown-phase` ở Boot 3.3.

**Câu 14.** `CompletableFuture.get` trong demo kiểm điều gì?

**Đáp:** Caller chờ kết quả job được xử lý qua Gateway, không chỉ đợi `submitOnce` trả về.

**Câu 15.** Vì sao đặt worker thread là daemon vẫn cần shutdown callback?

**Đáp:** Daemon không bảo đảm công việc hoàn thành; lifecycle cần đợi worker stop để đóng dependency theo thứ tự.

**Câu 16.** Demo có chạy lại `worker.start()` sau stop không?

**Đáp:** Không. Nó là one-shot worker có latches/future dùng một lần; production cần tạo lại run state.

**Câu 17.** Lỗi `Gateway.start()` ném exception có chắc được worker.stop xử lý trước destroy không?

**Đáp:** Không. Refresh failure có thể dẫn tới destruction mà không đầy đủ stop callbacks; cleanup cần phòng thủ.

**Câu 18.** Lúc nào nên dùng `SmartLifecycle` thay `ApplicationRunner`?

**Đáp:** Khi component có trách nhiệm **chạy dài hạn và dừng có điều phối**, đặc biệt có phase/dependency và asynchronous shutdown. Runner phù hợp công việc startup một lần; chúng có thể phối hợp nhưng không thay vai trò cho nhau.

**Câu 19.** Hai component cùng phase mà không dependency, có nên assert ai start trước?

**Đáp:** Không. Muốn thứ tự nghiệp vụ phải thể hiện phase khác hoặc depends-on rõ.

**Câu 20.** Nếu container bị SIGKILL, callback stop có chắc chạy không?

**Đáp:** Không. Công việc quan trọng cần checkpoint, durable queue và recovery.

## 16. Tổng kết và tài liệu chính thức

Nhớ bảy nguyên tắc:

1. `SmartLifecycle` tách **bean đã được tạo** khỏi **component đang hoạt động** và được Spring `LifecycleProcessor` tự start/stop theo contract.
2. **Phase thấp start trước, phase cao stop trước.** Trong demo: Gateway **100** trước Worker **200** khi start; Worker **200** trước Gateway **100** khi stop.
3. **Dependency tường minh được ưu tiên hơn phase** khi có xung đột. Dùng injection và `@DependsOn` để nêu rõ worker cần gateway.
4. **`stop(Runnable callback)` phải báo sau khi stop hoàn tất**. Không gọi callback sớm ngay sau yêu cầu shutdown, không quên gọi.
5. **`ContextClosedEvent` → stop lifecycle → destroy singleton** là trình tự đóng context bình thường. `@PreDestroy` không thay protocol stop theo phase.
6. **Future/CountDownLatch** giúp test job completion và shutdown order mà không phụ thuộc `Thread.sleep`.
7. **Demo một job không tương đương worker production**: muốn nhiều task/restart cần queue, state machine, timeout, shutdown idempotent, metrics, durability và crash recovery.

Tài liệu chính thức:

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): phase, auto-start, dependency ưu tiên phase, callback stop.
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): `onRefresh`, `onClose`, stop theo phase và timeout.
- [Spring Framework — Bean Lifecycle / Startup and Shutdown Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): sự khác nhau giữa bean destruction và `Lifecycle`, mặc định 30 giây per phase trong Spring 6.1.
- [Spring Framework — Depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): dependent starts after và destroys/stops before dependency.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): cấu hình `spring.lifecycle.timeout-per-shutdown-phase`, web-server graceful shutdown là trường hợp khác của lifecycle stop.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): `ApplicationStartedEvent`/`ApplicationReadyEvent` và các mốc startup.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html) và [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cơ chế đồng bộ hóa và quan sát kết quả công việc nền.

**Kết luận:** Một thành phần nền an toàn không chỉ có `new Thread(...)` và `boolean running`. Nó cần biết **ai phải hoạt động trước mình**, **ai phải đợi mình dừng**, **lúc nào task thực sự hoàn tất**, và **khi nào mới được gọi shutdown callback**. `SmartLifecycle` cùng phase, dependency và completion signaling cung cấp nền tảng để Spring Boot điều phối những ranh giới đó một cách kiểm chứng được.
