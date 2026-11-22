# Mô phỏng công việc đang chạy rồi thực hiện dừng có kiểm soát trong Spring Boot

## 1. Mục tiêu và kết quả cần quan sát

Một ứng dụng Spring Boot có thể đang xử lý message, chạy batch job, tạo báo cáo, gửi yêu cầu tới dịch vụ ngoài hoặc phục vụ HTTP request khi nhận lệnh dừng. Nếu chỉ gọi `ExecutorService.shutdownNow()` hoặc `System.exit(0)` ngay lập tức, công việc đang chạy có thể bị gián đoạn, mất kết quả hoặc không kịp commit/acknowledge. Ngược lại, nếu tiếp tục nhận việc mới trong lúc shutdown, ứng dụng có thể không bao giờ dừng xong.

Bài thực hành tổng hợp này mô phỏng **một tác vụ đã bắt đầu nhưng chưa kết thúc**, rồi thực hiện **controlled/graceful shutdown** theo thứ tự có thể kiểm chứng:

1. Spring Boot khởi tạo một bean `SmartLifecycle` có worker thread được quản lý.
2. Worker nhận **một job** và báo rõ job đang chạy.
3. Job cố ý dừng ở một `CountDownLatch` để mô phỏng công việc dài.
4. Thread khác yêu cầu `ApplicationContext.close()`.
5. Context phát `ContextClosedEvent`, sau đó yêu cầu worker dừng qua `stop(Runnable)`.
6. Worker **ngừng nhận việc mới** nhưng **chưa hủy ngay** job đang xử lý.
7. Đề nghị nộp job mới bị từ chối; job cũ vẫn còn in-flight.
8. Luồng điều phối mở latch để job cũ hoàn tất.
9. Executor chấm dứt, callback của `SmartLifecycle.stop(Runnable)` được gọi sau khi drain xong.
10. Spring mới hoàn tất destruction callbacks và việc đóng `ApplicationContext`.

**Tiêu chí thành công:** có bằng chứng rằng không nhận thêm work sau shutdown request, công việc cũ hoàn thành trước callback stop, bean được hủy sau stop và `context.close()` chỉ trả về sau khi hệ thống đã dừng theo hợp đồng.

Ví dụ dùng **Java 17+**, **Spring Boot 3.5.16**, Maven, `ExecutorService` và `CountDownLatch`. Không cần database, Kafka, HTTP server, sleep giả hoặc tài nguyên ngoài để chạy.

> Đây là mô phỏng lifecycle có kiểm soát, không phải lời cam kết exactly-once trên hệ thống phân tán. Với message broker, transaction hoặc external service thật, còn cần timeout, idempotency, acknowledgement và recovery policy riêng.

## 2. Graceful shutdown là gì?

Một shutdown có kiểm soát không chỉ là “đóng tài nguyên cho nhanh”. Nó là chuỗi trạng thái:

~~~text
RUNNING
   |
   | Yêu cầu shutdown
   v
STOPPING / DRAINING
   |
   +-- Từ chối nhận job mới
   +-- Không tạo thêm work dài hạn
   +-- Chờ job đang xử lý hoàn tất trong deadline
   +-- Commit/ack/flush theo hợp đồng nghiệp vụ
   +-- Đóng executor/connection/subscription do bean sở hữu
   |
   v
STOPPED
   |
   +-- Gửi SmartLifecycle stop callback
   +-- Spring tiếp tục đóng các phase khác
   +-- Chạy @PreDestroy / destroy callbacks
   |
   v
CONTEXT CLOSED
~~~

Ba khái niệm bắt buộc phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Stop accepting** | Không nhận công việc mới | Consumer ngừng poll; scheduler không submit task mới |
| **Drain in-flight** | Cho công việc đã nhận hoàn tất hoặc đi vào policy timeout | Đợi task, ack message sau commit |
| **Release resources** | Đóng tài nguyên mà component thực sự sở hữu | Shutdown executor, close client/pool, unsubscribe |

Nếu chỉ làm **stop accepting** mà không chờ drain, job có thể bị bỏ dở. Nếu chỉ drain nhưng vẫn nhận thêm job, danh sách in-flight có thể tăng vô hạn. Nếu đóng connection pool trước khi các job kết thúc, những job còn đang chạy có thể thất bại giữa chừng.

### Graceful khác forced shutdown

- **Graceful:** ưu tiên hoàn thành việc đã nhận trong thời hạn cho phép, tránh nhận việc mới, sau đó đóng resource theo thứ tự.
- **Forced:** sau deadline, dùng interrupt/cancellation/kill hoặc dừng chấp nhận kết quả. Có thể phải retry công việc còn dang dở ở instance khác.
- **Crash/SIGKILL:** có thể không chạy Spring lifecycle callbacks; yêu cầu recovery bên ngoài.

Một giải pháp production phải có **deadline và chính sách xử lý quá hạn**, không được đợi vô hạn chỉ vì gọi đó là graceful.

## 3. Vì sao chọn SmartLifecycle thay vì chỉ @PreDestroy?

Spring Framework có `Lifecycle` và `SmartLifecycle` để điều phối start/stop các bean có hoạt động nền. `SmartLifecycle` cung cấp:

~~~java
void start();
void stop();
void stop(Runnable callback);
boolean isRunning();
boolean isAutoStartup();
int getPhase();
~~~

Đây là **các chữ ký trọng tâm được trích để học**, không phải interface tự viết lại. Sử dụng `org.springframework.context.SmartLifecycle` từ Spring Framework.

Trong đường `ApplicationContext.close()` thông thường:
- Spring phát `ContextClosedEvent`.
- `LifecycleProcessor.onClose()` yêu cầu dừng các bean thuộc lifecycle.
- Với `SmartLifecycle`, processor dùng `stop(Runnable callback)` để biết lúc nào component thật sự dừng.
- Các phase shutdown được điều phối và có giới hạn thời gian chờ.
- Sau đó Spring gọi destruction callback, ví dụ `@PreDestroy` và `@Bean(destroyMethod=...)`.

**Điểm cốt lõi:** `@PreDestroy` là đường **destruction**, còn `stop(Runnable)` phục vụ **điều phối dừng**. Nếu phải đợi job đang chạy để đảm bảo thứ tự trước các bean khác bị destroy, chỉ đặt `executor.shutdown()` trong `@PreDestroy` thường là chưa đủ.

### Sự khác biệt giữa stop() và stop(Runnable)

`Lifecycle.stop()` là dạng dừng đồng bộ. `SmartLifecycle.stop(Runnable)` cho phép completion callback để lifecycle processor điều phối **shutdown bất đồng bộ**:

~~~text
stop(callback) được gọi
   |
   +-- Đánh dấu không nhận work mới
   +-- Yêu cầu executor ngừng nhận task
   +-- KHÔNG gọi callback khi task vẫn chạy
   +-- Khi executor thực sự terminated:
          callback.run()
~~~

Nếu `stop(Runnable)` chỉ gọi `ExecutorService.shutdown()` rồi ngay lập tức `callback.run()`, callback **báo hoàn tất quá sớm**: `shutdown()` không đợi các task đang chạy.

Ngược lại, nếu không gọi callback khi đã dừng thật, Spring có thể đợi tới hết timeout của shutdown phase. Vì vậy callback là một phần quan trọng của **hợp đồng lifecycle**, không phải dòng log mang tính trang trí.

## 4. Thiết kế state machine cho mô phỏng

Dùng trạng thái rõ ràng thay vì boolean rời rạc:

~~~text
NEW
  |
  | start() (auto-start khi ApplicationContext refresh)
  v
RUNNING
  |
  | stop(Runnable) / context.close()
  v
STOPPING
  | \
  |  +-- trySubmit() -> REJECTED
  |  +-- job đang chạy vẫn hoàn tất
  |  +-- callback được giữ lại để phát sau completion
  |
  +-- awaitTermination success
  v
STOPPED

Nếu executor không kết thúc trong deadline:
STOPPING -> FAILED_STOP / ghi nhận timeout để điều tra
~~~

### Những bất biến cần giữ

1. Khi `RUNNING`, component có quyền nhận job.
2. Từ lúc chuyển sang `STOPPING`, **mọi submit mới phải bị từ chối**.
3. Việc chuyển state và gọi `ExecutorService.shutdown()` phải được bảo vệ bằng cùng một monitor/lock với đường submit để tránh race.
4. `isRunning()` có thể còn true trong `STOPPING` vì tài nguyên thực chưa kết thúc; chỉ chuyển false khi stop hoàn tất.
5. Không gọi callback trước khi executor terminated.
6. Nếu nhiều lời gọi `stop(callback)` đến trong `STOPPING`, lưu đủ callback; không chạy shutdown lần hai.
7. Sau `STOPPED`, lời gọi stop lặp lại là no-op nhưng callback mới vẫn được hoàn tất.
8. Destruction callback có thể gọi cùng đường stop an toàn mà không double-close.
9. Nếu timeout xảy ra, ghi nhận lỗi và tránh tuyên bố đã dừng thành công khi tài nguyên vẫn chạy.
10. Không dựa vào `Thread.sleep(...)` để đo lường thứ tự giữa hai thread; dùng synchronization primitives.

### Race condition nếu không có lock

~~~java
if (accepting) {
    executor.submit(job);
}
~~~

Đây là **pseudocode**, chưa có định nghĩa `accepting`, `executor`, `job`. Nếu thread A kiểm tra `accepting=true` rồi thread B chuyển sang STOPPING và shutdown executor, thread A có thể submit sau đó và nhận `RejectedExecutionException`. Điều đó không hẳn làm mất an toàn nếu caller xử lý lỗi đúng, nhưng khó giữ một contract “accept/reject” nhất quán.

Trong demo, cùng một `monitor` bảo vệ **state + đường submit + quyết định shutdown**, nên một submit không thể chen vào giữa lúc stop thay state và đóng cửa nhận việc.

## 5. Vì sao dùng CountDownLatch, không dùng Thread.sleep?

`Thread.sleep(1000)` chỉ ngủ một khoảng thời gian; nó không chứng minh rằng worker **đã bắt đầu** trước khi shutdown, và có thể gây flakiness trên máy CI chậm.

Ta dùng ba latch:

| Latch | Bên phát tín hiệu | Bên chờ | Chứng minh |
| --- | --- | --- | --- |
| `jobStarted` | Worker thread khi bắt đầu xử lý | Main/test | Job đã thực sự vào vùng in-flight |
| `releaseJob` | Main/test khi cho phép hoàn thành | Worker thread | Job bị giữ lại có chủ đích cho tới khi phép đo xong |
| `stopRequested` | `SmartLifecycle.stop(Runnable)` sau khi ngừng nhận job | Main/test | Đường close đã đi tới lệnh stop của component |

Trình tự xác định:

~~~text
Main                Worker                   Close thread         Stop coordinator
 |                     |                          |                     |
 | submit job          |                          |                     |
 |-------------------->| jobStarted.countDown     |                     |
 | await jobStarted    | await releaseJob         |                     |
 |<--------------------|                          |                     |
 | request context.close()                        |                     |
 |----------------------------------------------->| ContextClosedEvent  |
 |                     |                          | stop(callback)      |
 |                     |                          | -> STOPPING         |
 | await stopRequested |                          | -> executor.shutdown|
 |<-----------------------------------------------|                     |
 | trySubmit -> false  |                          |                     |
 | releaseJob.countDown|                          |                     |
 |-------------------->| job finishes             |                     |
 |                     |-------------------------? | awaitTermination    |
 |                     |                          |                     |
 |                     |                          | callback invoked <--|
 |                     |                          | @PreDestroy         |
 |                     |                          | close() returns     |
 | join close thread  <--------------------------|                     |
~~~

Sơ đồ minh họa đồng bộ, dấu `?` chỉ là điểm giao tiếp giữa worker và coordinator. Không có yêu cầu job và stop coordinator phải chạy ở cùng thread.

## 6. Project Spring Boot Java 17+ chạy hoàn chỉnh

Bài tạo một Maven project duy nhất, với:

- Một `@SpringBootApplication` chạy non-web.
- Một singleton bean `ManagedWorker implements SmartLifecycle`.
- Một `ExecutorService` đơn luồng mô phỏng tác vụ dài.
- Một `ApplicationListener<ContextClosedEvent>` để quan sát mốc đóng context.
- Một thread riêng yêu cầu `context.close()`.
- Một completion coordinator đợi executor terminated rồi gọi các stop callbacks.
- Một `@PreDestroy` làm cleanup dự phòng.
- Một JUnit 5 test kiểm tra không callback quá sớm và không nhận job mới khi STOPPING.

Ví dụ **không kết nối database, web server, message broker**. Các tình huống trễ thật và force-kill được thảo luận riêng.

### 6.1. Cấu trúc thư mục

~~~text
controlled-shutdown-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/shutdown/
    │   │   └── ControlledShutdownApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/shutdown/
            └── ManagedWorkerTest.java
~~~

### 6.2. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>controlled-shutdown-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
~~~

`spring-boot-starter` đủ cho ứng dụng non-web. `spring-boot-starter-test` cung cấp JUnit Jupiter cho bài kiểm thử; nó không cần tạo Spring test context vì test unit có thể khởi tạo `ManagedWorker` trực tiếp.

### 6.3. Tệp application.properties

~~~properties
spring.application.name=controlled-shutdown-demo
spring.main.banner-mode=off

# Giới hạn tổng thời gian Spring chờ callback trong mỗi shutdown phase.
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Giá trị 25 giây chỉ phục vụ bài thực hành. **Timeout của Spring không cưỡng chế executor hay task thực sự dừng**: nó chỉ giới hạn thời gian lifecycle processor chờ callback phase. Trong code sẽ có deadline riêng cho `ExecutorService.awaitTermination(...)`.

### 6.4. Tệp Java đầy đủ

Lưu thành `src/main/java/com/example/shutdown/ControlledShutdownApplication.java`:

~~~java
package com.example.shutdown;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;

@SpringBootApplication
public class ControlledShutdownApplication {

    public static void main(String[] args) throws InterruptedException {
        SpringApplication application =
                new SpringApplication(ControlledShutdownApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);
        ManagedWorker worker = context.getBean(ManagedWorker.class);
        AtomicReference<Throwable> closeError = new AtomicReference<>();

        try {
            System.out.println("02_CONTEXT_READY");

            worker.submitOneJob();
            worker.awaitJobStarted();
            System.out.println("04_IN_FLIGHT=" + worker.inFlight());

            System.out.println("05_MAIN_REQUEST_CLOSE");
            Thread closer = new Thread(() -> {
                try {
                    context.close();
                    System.out.println("13_CONTEXT_CLOSE_RETURNED");
                } catch (Throwable error) {
                    closeError.set(error);
                }
            }, "context-close-thread");
            closer.start();

            worker.awaitStopRequested();
            System.out.println("08_LATE_SUBMISSION_ACCEPTED="
                    + worker.tryLateSubmission());

            System.out.println("09_MAIN_RELEASE_JOB");
            worker.releaseJob();

            closer.join(20_000);
            if (closer.isAlive()) {
                throw new IllegalStateException("context close timed out");
            }
            if (closeError.get() != null) {
                throw new IllegalStateException(
                        "context close failed", closeError.get());
            }

            System.out.println("14_FINAL_RUNNING=" + worker.isRunning());
        } finally {
            // Đảm bảo không giữ job mãi nếu có assertion/await thất bại.
            worker.releaseJob();
            if (context.isActive()) {
                context.close();
            }
        }
    }

    @Bean
    ManagedWorker managedWorker() {
        return new ManagedWorker();
    }

    @Bean
    ApplicationListener<ContextClosedEvent> closeEventListener() {
        return event -> System.out.println("06_CONTEXT_CLOSED_EVENT");
    }

    public static final class ManagedWorker implements SmartLifecycle {

        private enum State {
            NEW, RUNNING, STOPPING, STOPPED, FAILED
        }

        private final Object monitor = new Object();
        private final CountDownLatch jobStarted = new CountDownLatch(1);
        private final CountDownLatch releaseJob = new CountDownLatch(1);
        private final CountDownLatch stopRequested = new CountDownLatch(1);
        private final AtomicInteger inFlight = new AtomicInteger();
        private final List<Runnable> callbacks = new ArrayList<>();

        private State state = State.NEW;
        private ExecutorService executor;

        @Override
        public void start() {
            synchronized (monitor) {
                if (state == State.RUNNING) {
                    return;
                }
                if (state != State.NEW) {
                    throw new IllegalStateException(
                            "Restart not supported in this demo: " + state);
                }

                executor = Executors.newSingleThreadExecutor(task -> {
                    Thread thread = new Thread(task, "managed-job-thread");
                    thread.setDaemon(false);
                    return thread;
                });

                state = State.RUNNING;
                System.out.println("01_LIFECYCLE_STARTED");
            }
        }

        public void submitOneJob() {
            synchronized (monitor) {
                if (state != State.RUNNING) {
                    throw new IllegalStateException(
                            "Not accepting jobs: " + state);
                }

                inFlight.incrementAndGet();
                try {
                    executor.execute(() -> {
                        System.out.println("03_JOB_STARTED");
                        jobStarted.countDown();

                        try {
                            if (!releaseJob.await(15, TimeUnit.SECONDS)) {
                                System.err.println(
                                        "JOB_DEADLINE_EXPIRED");
                            }
                        } catch (InterruptedException exception) {
                            Thread.currentThread().interrupt();
                            System.err.println("JOB_INTERRUPTED");
                        } finally {
                            inFlight.decrementAndGet();
                            System.out.println("10_JOB_FINISHED");
                        }
                    });
                } catch (RuntimeException error) {
                    inFlight.decrementAndGet();
                    throw error;
                }
            }
        }

        public void awaitJobStarted() throws InterruptedException {
            if (!jobStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("job did not start");
            }
        }

        public void awaitStopRequested() throws InterruptedException {
            if (!stopRequested.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "lifecycle stop was not requested");
            }
        }

        public void releaseJob() {
            releaseJob.countDown();
        }

        public int inFlight() {
            return inFlight.get();
        }

        public boolean tryLateSubmission() {
            synchronized (monitor) {
                if (state != State.RUNNING) {
                    return false;
                }
                executor.execute(() ->
                        System.out.println("UNEXPECTED_LATE_JOB_EXECUTED"));
                return true;
            }
        }

        @Override
        public void stop(Runnable callback) {
            Objects.requireNonNull(callback, "callback");
            ExecutorService executorToWait = null;
            boolean completeImmediately = false;

            synchronized (monitor) {
                if (state == State.NEW) {
                    state = State.STOPPED;
                    completeImmediately = true;
                } else if (state == State.STOPPED) {
                    completeImmediately = true;
                } else if (state == State.STOPPING) {
                    // Gộp tất cả callback vào cùng một lần shutdown.
                    callbacks.add(callback);
                } else if (state == State.FAILED) {
                    throw new IllegalStateException(
                            "Previous shutdown failed");
                } else {
                    // RUNNING: khóa cổng nhận work trước khi shutdown.
                    state = State.STOPPING;
                    callbacks.add(callback);
                    executor.shutdown();
                    System.out.println("07_STOP_REQUESTED");
                    stopRequested.countDown();
                    executorToWait = executor;
                }
            }

            if (completeImmediately) {
                callback.run();
            }
            if (executorToWait != null) {
                awaitTerminationInBackground(executorToWait);
            }
        }

        private void awaitTerminationInBackground(ExecutorService target) {
            Thread coordinator = new Thread(() -> {
                try {
                    boolean terminated =
                            target.awaitTermination(15, TimeUnit.SECONDS);
                    if (!terminated) {
                        System.err.println("SHUTDOWN_FORCE_INTERRUPT");
                        target.shutdownNow();
                        terminated = target.awaitTermination(
                                3, TimeUnit.SECONDS);
                    }

                    if (!terminated) {
                        failStop("executor did not terminate");
                        return;
                    }
                    completeStop();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    target.shutdownNow();
                    failStop("stop coordinator interrupted");
                }
            }, "stop-coordinator");

            coordinator.setDaemon(true);
            coordinator.start();
        }

        private void completeStop() {
            List<Runnable> ready;
            synchronized (monitor) {
                state = State.STOPPED;
                ready = new ArrayList<>(callbacks);
                callbacks.clear();
                System.out.println("11_STOP_COMPLETED");
            }

            // Callback nằm ngoài monitor để tránh reentrant deadlock.
            for (Runnable callback : ready) {
                try {
                    callback.run();
                } catch (RuntimeException error) {
                    System.err.println(
                            "STOP_CALLBACK_FAILED="
                                    + error.getClass().getSimpleName());
                }
            }
        }

        private void failStop(String message) {
            synchronized (monitor) {
                state = State.FAILED;
                System.err.println("SHUTDOWN_FAILED=" + message);
            }
            // Không phát callback hoàn tất nếu worker chưa terminated.
            // LifecycleProcessor sẽ dùng timeout của phase.
        }

        @Override
        public void stop() {
            CountDownLatch done = new CountDownLatch(1);
            stop(done::countDown);
            try {
                if (!done.await(20, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("stop() timed out");
                }
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while waiting to stop", exception);
            }
        }

        @Override
        public boolean isRunning() {
            synchronized (monitor) {
                return state == State.RUNNING
                        || state == State.STOPPING;
            }
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }

        @PreDestroy
        public void destroy() {
            // Backup cleanup: không tạo lần shutdown thứ hai
            // nếu SmartLifecycle đã chuyển STOPPED.
            stop();
            System.out.println("12_BEAN_DESTROYED");
        }
    }
}
~~~

Đây là **toàn bộ mã Java chạy được** của ứng dụng. Không có phương thức giả `doWork()`, không cần cấu hình service bên ngoài và không cần gọi `System.exit`.

### 6.5. Giải thích các điểm an toàn của implementation

**Bảo vệ trạng thái và đường submit bằng một monitor.** `start`, `submitOneJob`, `tryLateSubmission`, `stop(Runnable)` và `isRunning` đều truy cập state một cách đồng bộ. Khi `STOPPING` đã được ghi nhận, lời gọi `tryLateSubmission` phải trả false. `executor.shutdown()` nằm trong cùng vùng đồng bộ với việc chuyển state, tránh việc submit thành công xen giữa quyết định đóng cổng.

**Đếm in-flight đúng phạm vi.** `inFlight.incrementAndGet()` xảy ra trước `executor.execute(...)`; nếu submit ném exception, bộ đếm được rollback. Task giảm counter trong `finally`, kể cả bị interrupt. Vì vậy counter mô tả số task đã được nhận và chưa hoàn tất, không chỉ số thread còn tồn tại.

**Không block lifecycle callback thread quá lâu.** `stop(Runnable)` chỉ thay state, shutdown executor nhanh rồi tạo một thread coordinator. Thread đó đợi `awaitTermination`, không giữ `monitor` trong lúc chờ. Với `DefaultLifecycleProcessor`, callback cho phép Spring chờ theo phase thay vì bị buộc phải đợi I/O ngay trên thread gọi stop.

**Từ chối task mới trước khi đợi task cũ.** `executor.shutdown()` ngừng nhận task; đồng thời guard `state != RUNNING` trả false cho lời gọi muộn. Không có task mới vô tình làm tăng thời gian drain.

**Callback chỉ chạy sau termination.** Chỉ `completeStop()` gọi các callback, và phương thức này chỉ được gọi khi `awaitTermination` thành công. Nếu không dừng được sau các deadline, code chuyển `FAILED` và cố ý không phát tín hiệu “đã hoàn tất”. Spring có thể hết timeout phase; production cần escalation rõ.

**Callback của các lời gọi stop lặp được giữ lại.** Khi state đang `STOPPING`, callback thứ hai được lưu vào `callbacks` chứ không làm executor shutdown lần nữa. `completeStop` lấy một bản sao, xóa queue và gọi từng callback bên ngoài monitor.

**Dọn dẹp bổ sung bằng `@PreDestroy`.** Trong đường close bình thường, callback từ SmartLifecycle đã hoàn tất trước bean destruction. Lời gọi `stop()` trong `destroy()` trở thành no-op an toàn, rồi in marker. Nếu stop có lỗi/timeout, fallback có thể thất bại; không được dùng dòng log này làm cam kết mọi tài nguyên đã giải phóng trong failure path.

**Không cho restart generation trong demo.** `start()` chỉ cho phép trạng thái NEW → RUNNING, tránh tình huống reuse CountDownLatch và executor đã đóng. Nếu ứng dụng thật cần `context.stop() → context.start()`, cần tạo generation mới, thay toàn bộ latch/executor phù hợp và test thêm. Không giả vờ code demo hỗ trợ restart khi chưa thiết kế.

### 6.6. Tại sao dùng daemon thread cho coordinator?

`stop-coordinator` là thread ngắn để chờ completion và báo callback. Nó được đánh dấu daemon nhằm không giữ JVM sống vô hạn **chỉ vì một lỗi ở thread điều phối**. Nhưng task thread `managed-job-thread` là non-daemon và **phải được shutdown đúng cách**. Việc dùng daemon cho coordinator **không thay thế** timeout/cleanup và không đảm bảo callback nếu JVM bị force-kill.

Trong đường chạy bình thường, main chờ `context.close()` hoàn tất, nên coordinator có cơ hội chạy xong trước khi process kết thúc.

### 6.7. Vì sao có hai deadline cho executor?

Trong `awaitTerminationInBackground`:
1. Đợi tối đa **15 giây** để task kết thúc tự nhiên.
2. Nếu không, gửi `shutdownNow()` để yêu cầu interrupt task còn chạy.
3. Đợi thêm tối đa **3 giây**.
4. Nếu executor vẫn chưa terminated, ghi `SHUTDOWN_FAILED` và **không báo callback hoàn tất giả**.

Những số này chỉ là lựa chọn phục vụ demo; Spring `spring.lifecycle.timeout-per-shutdown-phase=25s` là một **deadline ở cấp processor**, không tự dừng executor. Ứng dụng production nên đặt deadline bảo đảm tương thích với hệ thống điều phối ngoài process và quan sát time budget qua các phase.

**Quan trọng:** `shutdownNow()` chỉ cố gắng interrupt các task; nếu task không xử lý interrupt hoặc kẹt trong I/O không thể hủy, không có bảo đảm đã dừng. Khi đó cần compensation/idempotent retry hoặc cơ chế force termination có kiểm soát từ orchestrator.

## 7. Chạy ứng dụng và đọc output theo thứ tự

### 7.1. Biên dịch, kiểm thử rồi chạy JAR

Mở terminal trong thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn package
java -jar target/controlled-shutdown-demo-0.0.1-SNAPSHOT.jar
~~~

`mvn test` chạy JUnit được mô tả ở mục sau. `mvn package` tạo executable JAR. Khi chạy `java -jar`, chương trình tự tạo một job, tự mở một thread yêu cầu đóng context rồi kết thúc. Không cần bấm Ctrl+C giữa chừng, vì main điều phối bằng latch.

### 7.2. Các marker từ chính chương trình

**Trong đường chạy thành công**, bỏ qua Spring Boot framework logs và những log từ Maven. Các marker do source Java này in theo thứ tự:

~~~text
01_LIFECYCLE_STARTED
02_CONTEXT_READY
03_JOB_STARTED
04_IN_FLIGHT=1
05_MAIN_REQUEST_CLOSE
06_CONTEXT_CLOSED_EVENT
07_STOP_REQUESTED
08_LATE_SUBMISSION_ACCEPTED=false
09_MAIN_RELEASE_JOB
10_JOB_FINISHED
11_STOP_COMPLETED
12_BEAN_DESTROYED
13_CONTEXT_CLOSE_RETURNED
14_FINAL_RUNNING=false
~~~

Các marker trên là **kết quả kỳ vọng dựa vào thứ tự latch và callback của demo**, không phải bản log đo trực tiếp từ một lần chạy tại thời điểm viết. Nếu task bị timeout, coordinator bị interrupt hoặc dependency/framework bị lỗi, output có thể khác và chương trình phải được điều tra theo failure path.

### 7.3. Phân tích từng marker

**01_LIFECYCLE_STARTED** — `DefaultLifecycleProcessor` auto-start bean `ManagedWorker` trong quá trình refresh bởi `isAutoStartup() == true`. Khi `SpringApplication.run` trả về, worker sẵn sàng nhận task.

**02_CONTEXT_READY** — thread main đã nhận context và bean, chưa yêu cầu stop.

**03_JOB_STARTED** — task được executor thực sự chạy và phát `jobStarted.countDown()`. Main chỉ đi tiếp khi latch xác nhận.

**04_IN_FLIGHT=1** — task vẫn đang chờ `releaseJob`, vì vậy bộ đếm còn 1. Không thể nhầm “đã submit nhưng chưa chạy” với “task thật sự in-flight”.

**05_MAIN_REQUEST_CLOSE** — main tạo thread `context-close-thread` và yêu cầu `context.close()`. Main không tự block ở lời gọi đó, vì còn phải mở latch cho job được kết thúc.

**06_CONTEXT_CLOSED_EVENT** — Spring phát sự kiện bắt đầu đóng context. Tại mốc này, callback destruction chưa nhất thiết chạy.

**07_STOP_REQUESTED** — `SmartLifecycle.stop(Runnable)` chuyển state RUNNING → STOPPING, gọi `executor.shutdown()` và phát `stopRequested.countDown()`. Job cũ vẫn đang chạy.

**08_LATE_SUBMISSION_ACCEPTED=false** — main chờ `stopRequested` trước khi thử submit, nên quyết định được xác định bằng state STOPPING; không có job mới chen vào hàng đợi.

**09_MAIN_RELEASE_JOB** — main cho phép task cũ kết thúc bằng `releaseJob.countDown()`. Nếu không có lệnh này, task phải chờ timeout hoặc interrupt.

**10_JOB_FINISHED** — task chạy `finally`, giảm in-flight từ 1 về 0, giải phóng worker thread sau khi runnable trả về.

**11_STOP_COMPLETED** — stop coordinator thấy `ExecutorService.awaitTermination(...)` trả true, chuyển state STOPPED, rồi mới phát các callback cho lifecycle processor.

**12_BEAN_DESTROYED** — Spring tiếp tục đường close và gọi `@PreDestroy` trên bean. Vì stop đã hoàn tất, fallback stop không đóng lại executor.

**13_CONTEXT_CLOSE_RETURNED** — lời gọi `context.close()` trong thread đóng context đã trả về, sau khi các bước lifecycle/destruction bình thường kết thúc.

**14_FINAL_RUNNING=false** — main đã join thread đóng context, thấy bean không còn hoạt động. Đây không phải một lời gọi nghiệp vụ mới trên bean đã destroy; ví dụ chỉ quan sát state đã được bảo vệ bởi monitor.

### 7.4. Điều chứng minh quan trọng nhất

Không phải chỉ thấy chương trình “dừng được”, mà là **thứ tự bất biến**:

~~~text
STOP_REQUESTED
    < SUBMIT_AFTER_STOP_REJECTED
    < JOB_RELEASED
    < JOB_FINISHED
    < STOP_COMPLETED
    < BEAN_DESTROYED
    < CONTEXT_CLOSE_RETURNED
~~~

Dấu `<` ở đây có nghĩa **xảy ra trước**, không phải toán tử Java. Những quan hệ này được đảm bảo bởi latch, lock, executor termination và callback trong demo. Nếu không có synchronization, chỉ nhìn vào timestamp cách nhau vài mili-giây sẽ không đủ làm bằng chứng.

**Không thể suy từ `ContextClosedEvent` rằng worker đã dừng.** Trong Spring Framework, event được công bố trước lifecycle stop và singleton destruction trong đường close bình thường. Marker 06 đến trước 07 chính là phép kiểm chứng.

## 8. Kiểm thử tự động bằng JUnit 5

Ngoài chương trình main, dùng **một unit test thuần** cho worker để kiểm tra:
- Stop callback chưa được gọi khi job vẫn kẹt ở latch.
- Không còn nhận job mới khi trạng thái là STOPPING.
- Sau khi release latch, callback được gọi và in-flight bằng 0.
- Hai lời gọi stop bất đồng bộ không gây double-close và mỗi callback được gửi đủ.

Không cần khởi động Spring TestContext trong các unit test này vì các method lifecycle là Java bình thường và có thể gọi trực tiếp. Điều này giảm thời gian test và làm assertion ổn định.

### 8.1. Tệp ManagedWorkerTest.java

Lưu vào `src/test/java/com/example/shutdown/ManagedWorkerTest.java`:

~~~java
package com.example.shutdown;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ManagedWorkerTest {

    @Test
    void stopWaitsForInFlightWorkAndRejectsNewWork()
            throws InterruptedException {
        var worker =
                new ControlledShutdownApplication.ManagedWorker();
        worker.start();

        try {
            worker.submitOneJob();
            worker.awaitJobStarted();

            CountDownLatch stopped = new CountDownLatch(1);
            worker.stop(stopped::countDown);
            worker.awaitStopRequested();

            assertFalse(worker.tryLateSubmission());
            assertEquals(1, worker.inFlight());
            assertTrue(worker.isRunning());

            // Không dùng sleep: callback chưa thể hoàn tất
            // khi job còn bị chặn bởi releaseJob latch.
            assertFalse(stopped.await(50, TimeUnit.MILLISECONDS));

            worker.releaseJob();
            assertTrue(stopped.await(10, TimeUnit.SECONDS));
            assertEquals(0, worker.inFlight());
            assertFalse(worker.isRunning());
        } finally {
            worker.releaseJob();
            worker.stop();
        }
    }

    @Test
    void repeatedStopRequestsCompleteBothCallbacks()
            throws InterruptedException {
        var worker =
                new ControlledShutdownApplication.ManagedWorker();
        worker.start();

        try {
            worker.submitOneJob();
            worker.awaitJobStarted();

            CountDownLatch callbacks = new CountDownLatch(2);
            worker.stop(callbacks::countDown);
            worker.stop(callbacks::countDown);

            assertFalse(worker.tryLateSubmission());
            assertEquals(1, worker.inFlight());

            worker.releaseJob();
            assertTrue(callbacks.await(10, TimeUnit.SECONDS));
            assertEquals(0, worker.inFlight());
            assertFalse(worker.isRunning());
        } finally {
            worker.releaseJob();
            worker.stop();
        }
    }
}
~~~

Đây là **tệp Java test đầy đủ**, dùng JUnit Jupiter từ `spring-boot-starter-test` của pom.xml. Các phép kiểm tra không dựa vào thời gian sleep để tạo thứ tự. Thời hạn `await(..., TimeUnit.SECONDS)` chỉ là giới hạn chống treo test nếu có regression.

### 8.2. Lệnh chạy test

~~~bash
mvn -Dtest=ManagedWorkerTest test
~~~

Kỳ vọng trong project sạch: **2 tests, 0 failures, 0 errors**. Maven/Surefire logs thay đổi theo môi trường; không khẳng định một bản stdout đầy đủ có timestamp cố định.

### 8.3. Vì sao callback không được báo sớm?

Ở test thứ nhất, worker đã chạy job và đang chờ `releaseJob`. Test gọi `worker.stop(stopped::countDown)` rồi kiểm tra:

~~~java
assertFalse(stopped.await(50, TimeUnit.MILLISECONDS));
~~~

Nếu callback được gọi ngay sau `executor.shutdown()`, latch `stopped` sẽ về 0 và assertion thất bại. Khi mở `releaseJob`, task kết thúc; coordinator thấy executor terminated và gửi callback, nên assertion tiếp theo thành công.

### 8.4. Tại sao try/finally cần thiết trong test?

Nếu assertion fail, test vẫn phải mở latch và gọi stop để tránh để lại non-daemon worker thread trong Maven test JVM. Không có `finally`, test có thể báo lỗi nhưng process Maven không thoát, khiến CI timeout.

Đó là chính một bài học về **resource ownership trong kiểm thử lifecycle**: người tạo worker ngoài Spring TestContext phải có đường cleanup riêng.

## 9. Thử sửa một lỗi cố ý: callback được gọi quá sớm

Giả sử sửa tạm method `stop(Runnable callback)` thành ý tưởng sau:

~~~java
@Override
public void stop(Runnable callback) {
    executor.shutdown();
    callback.run(); // Sai cho task còn in-flight!
}
~~~

Đây là **đoạn minh họa lỗi**, không phải code thay thế đầy đủ vì còn thiếu state/lock/callback queue. Trong mô phỏng:
- Spring có thể nhận tín hiệu phase đã dừng.
- Nhưng job vẫn chờ latch.
- Spring bắt đầu destroy các singleton khác trong khi job có thể còn đang sử dụng chúng.
- Test “callback chưa đến khi job còn chạy” sẽ fail.

**Bài học:** callback của SmartLifecycle không đồng nghĩa “đã gửi yêu cầu dừng”; nó có nghĩa “component đã hoàn tất dừng theo contract”.

## 10. Thử sửa một lỗi khác: không chặn công việc mới

Nếu bỏ guard trong `tryLateSubmission()` và luôn submit:

~~~java
executor.execute(newJob);
~~~

Đây là **pseudocode** vì `newJob` chưa định nghĩa. Khi executor đã nhận `shutdown()`, `execute` có thể ném `RejectedExecutionException`. Trong những thiết kế khác, đường submit còn có thể lọt vào giữa state check và shutdown, làm nhận một job mới sau khi hệ thống đã bắt đầu dừng.

Thiết kế tốt nên có một API tường minh như:
- `boolean trySubmit(Job job)` trả false khi không nhận.
- Hoặc `submit(...)` ném một exception riêng có thể nhận diện cho “service unavailable/stopping”.
- Nếu là HTTP endpoint, trả status theo hợp đồng (ví dụ 503 khi instance không nhận việc nữa).
- Nếu là message consumer, ngừng polling/receiving thay vì tiếp tục nhận rồi bỏ message.

Không được im lặng “accept” một job mà sẽ không bao giờ được thực thi.

## 11. Thử case timeout: job không chịu hoàn thành

Trong demo, ta điều khiển `releaseJob` để job kết thúc nhanh. Nếu **không mở latch**, task chờ tối đa 15 giây rồi tự thoát với marker `JOB_DEADLINE_EXPIRED`. Coordinator cũng đợi executor tối đa 15 giây, sau đó thử `shutdownNow()` và đợi thêm 3 giây.

Để thử thực tế, cần thay đổi code test/harness có chủ đích, không chỉ bỏ một dòng ở main mà quên đường `finally` cũng release latch. Một biến thể an toàn là tạo test điều khiển worker riêng và có timeout toàn test.

### Các kết quả có thể xảy ra

| Job behavior | Coordinator | Spring lifecycle | Điều cần ghi nhận |
| --- | --- | --- | --- |
| Hoàn thành trước 15s | awaitTermination=true | Callback sau completion | Graceful success |
| Chưa xong sau 15s nhưng chịu interrupt | shutdownNow → terminated | Callback sau termination | Forced cancellation; có thể cần retry |
| Không chịu interrupt sau thêm 3s | FAILED, không callback | Processor có thể đợi tới timeout phase | Không được báo “shutdown sạch” |
| JVM bị SIGKILL | Không bảo đảm coordinator/callback chạy | Không bảo đảm destroy | External recovery bắt buộc |

**Không đặt marker “STOP_COMPLETED” vào đường timeout mà executor còn sống.** Nếu hệ thống không thể dừng, báo cáo trạng thái chưa hoàn tất và để tầng vận hành quyết định escalation.

### Interrupt có bảo đảm rollback không?

Không. `Thread.interrupt()` chỉ gửi tín hiệu hợp tác tới thread. Những tác vụ gọi `wait`, `sleep` hoặc `CountDownLatch.await` thường ném `InterruptedException`, nhưng code nghiệp vụ phải tự xử lý đúng. Một native call, deadlock hoặc thư viện không hỗ trợ cancellation có thể không kết thúc kịp.

Trong job thật:
- Kiểm tra `Thread.currentThread().isInterrupted()` ở điểm phù hợp.
- Không nuốt `InterruptedException` rồi tiếp tục loop vô hạn.
- Bảo toàn interrupt flag khi chuyển sang cleanup.
- Cần transaction rollback hoặc acknowledgement policy khi một bước chưa hoàn tất.
- Không khẳng định mọi side effect ngoài JVM được hủy chỉ vì thread đã dừng.

### Hạn chế của demo ở đường lỗi

Code chọn **không phát callback** nếu worker chưa terminated để tránh báo thành công giả. Điều đó làm Spring chờ tới phase timeout. Khi lifecycle processor tiếp tục destroy bean, `@PreDestroy` có thể phát sinh lỗi nếu worker vẫn STOPPING/FAILED. Đây là một kết quả thất bại cần báo động và xử lý ở production, không phải bằng chứng rằng shutdown graceful đã thành công.

Một implementation production có thể chọn protocol khác: cancellation token, phased stopping, circuit breaker, resource fencing hoặc escalation trước deadline, nhưng phải minh bạch về tình trạng những job chưa hoàn thành.

## 12. SmartLifecycle phase: thứ tự giữa worker và dependency

Nếu worker dùng chung một client hoặc connection pool:
- Worker phải **ngừng nhận job và drain** khi client còn sống.
- Sau khi worker dừng, bean owner của client mới được phép close.

`SmartLifecycle.getPhase()` giúp điều phối giữa các lifecycle beans:

~~~text
START: phase thấp -> phase cao
STOP : phase cao  -> phase thấp
~~~

Ví dụ:

| Thành phần | Phase | Khi start | Khi stop |
| --- | ---: | --- | --- |
| Shared infrastructure/client (cũng là Lifecycle) | -100 | Trước | Sau |
| Worker/consumer | 100 | Sau | Trước |
| Endpoint/consumer sát người dùng | 200 | Sau cùng | Trước hơn |

Nếu client chỉ là singleton thông thường có destruction callback, Spring thường stop các SmartLifecycle beans trong `onClose()` trước khi destroy singleton. Tuy vậy, phải bảo đảm callback worker thật sự chỉ đến sau khi job không còn dùng client.

Không chọn phase theo cảm tính. Quan hệ `depends-on` và điều kiện cụ thể của container có thể ảnh hưởng thứ tự. Các thành phần dùng nhiều dependency nên có sơ đồ ownership/phase và test shutdown để tránh đóng client quá sớm.

### isRunning() phải phản ánh đúng trạng thái

Trong demo, `isRunning()` trả true cho cả RUNNING và STOPPING. Điều này cố ý: STOPPING còn có resource hoặc job in-flight, nên bean **chưa thực sự dừng xong**. Chỉ sau coordinator confirmed terminated mới trả false.

Không báo false ngay sau `executor.shutdown()` nếu việc dừng chưa hoàn tất; điều đó có thể làm framework hoặc test nghĩ resource đã đóng. Ngược lại, nếu bean đã stop thành công mà vẫn báo true, lifecycle processor có thể tiếp tục xử lý sai khi stop lặp.

## 13. context.stop(), context.close() và System.exit() trong bài thực hành

Ba thao tác khác nhau:

| API | Hành động | Phù hợp cho mô phỏng này? |
| --- | --- | --- |
| `worker.stop()` | Dừng riêng worker theo contract đồng bộ | Có khi chỉ muốn dừng worker |
| `worker.stop(callback)` | Dừng worker, báo completion | Có; được lifecycle processor dùng khi close |
| `context.stop()` | Dừng các `Lifecycle` beans nhưng giữ context và singleton | Có thể dùng nếu cần pause/restart, nhưng demo không hỗ trợ restart generation |
| `context.close()` | Dừng lifecycle, destroy managed singleton, kết thúc context | **Có**, lựa chọn của demo |
| `SpringApplication.exit(context)` | Đóng context và tính process exit code | Có thể dùng cho CLI cần code |
| `System.exit(code)` | Bắt đầu shutdown toàn JVM/process | Không cần trong demo; không dùng thay cho graceful drain |

**Vì sao main tạo thread riêng để gọi context.close?** Nếu main gọi `context.close()` trực tiếp, nó sẽ đợi lifecycle processor tới lúc worker dừng, trong khi chính main cũng đang giữ latch `releaseJob`. Cả hai phía sẽ phụ thuộc lẫn nhau. Ta tách:
- Thread close yêu cầu shutdown và chờ callback.
- Thread main giữ quyền mở latch.
- Worker thread thực hiện job.
- Stop coordinator chờ executor termination.

Đó là một cách mô phỏng được **work in flight khi shutdown**, không cần hai process hay một HTTP client. Trong ứng dụng thực, người yêu cầu shutdown thường là OS/JVM hook, admin orchestration hoặc container runtime chứ không phải main thread tự tạo một close thread.

### Tránh deadlock giữa close và release

Anti-pattern:

~~~java
worker.submitOneJob();
worker.awaitJobStarted();
context.close();       // Chờ job hoàn tất ...
worker.releaseJob();   // ... nhưng dòng này không tới kịp.
~~~

Đây là đoạn minh họa lỗi trong main. `context.close()` có thể block đợi stop callback, còn worker chờ `releaseJob`; đó là dependency vòng dẫn tới timeout. Trong demo, thread riêng gọi close cho phép main mở latch **sau khi** biết stop đã được yêu cầu.

### Spring Boot shutdown hook

Spring Boot mặc định đăng ký shutdown hook để đóng ApplicationContext khi JVM đi vào shutdown bình thường. Điều đó khác với việc một module tự gọi `System.exit(0)`. Nếu code tắt shutdown hook hoặc JVM bị SIGKILL, không có bảo đảm lifecycle callback chạy.

Không cần kích hoạt hook để chạy demo: ta gọi `context.close()` tường minh và chờ nó kết thúc. Vì thế marker thứ tự dễ kiểm chứng hơn việc gửi tín hiệu OS có timing khó điều khiển.

## 14. Mối liên hệ với graceful shutdown HTTP server

Demo là **ứng dụng non-web**, nên không có HTTP request đang xử lý. Đây là lựa chọn có chủ đích để chỉ tập trung vào worker lifecycle. Đối với một Spring Boot web application, framework hỗ trợ graceful shutdown cho embedded web servers trong đường đóng `ApplicationContext`.

Theo Spring Boot 3.5:
- Graceful shutdown được bật mặc định với các embedded web servers được hỗ trợ.
- Nó xảy ra trong giai đoạn đóng context, khi `SmartLifecycle` beans dừng.
- Server ngừng nhận request mới theo cơ chế của từng server; các request đang xử lý được cấp một grace period.
- Có thể cấu hình thời gian chờ theo phase bằng `spring.lifecycle.timeout-per-shutdown-phase`.

Ví dụ khi đưa concept sang web app:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Đây là **cấu hình tham khảo cho web app**, không phải yêu cầu của demo non-web. Bản chất graceful shutdown HTTP có khác biệt giữa Tomcat, Jetty, Reactor Netty và Undertow; không suy rằng mọi server sẽ trả cùng một HTTP status khi sắp dừng.

### HTTP request khác background job

- Request in-flight thường do web server quản lý và drain theo graceful shutdown.
- Job do `ExecutorService` tự tạo **không mặc nhiên được web server biết đến**.
- Message consumer có thể do framework listener container sở hữu, có stop/ack semantics riêng.
- Một HTTP endpoint submit job vào queue nội bộ cần phối hợp: **ngừng nhận request mới + ngừng nhận job mới + drain job đã nhận**.

Chỉ bật `server.shutdown=graceful` không tự dừng mọi custom executor trong ứng dụng. Bean owner của executor vẫn phải có lifecycle cleanup đúng.

### Readiness trong Kubernetes

Một pod cần thời gian để load balancer/Service ngừng gửi traffic mới. Trong production:
1. Thông báo instance không còn sẵn sàng nhận request mới, ví dụ qua readiness state/probe.
2. Cho routing cập nhật.
3. Ngừng nhận work mới.
4. Drain in-flight work trong giới hạn deployment.
5. Đóng context và resource.
6. Để process kết thúc sau cleanup hoặc bị orchestrator force-kill khi hết deadline.

Spring Boot `ApplicationAvailability` và Actuator readiness probes hỗ trợ tín hiệu availability. **`context.isRunning()` hoặc `ContextClosedEvent` một mình không phải readiness protocol đầy đủ.**

## 15. Nếu công việc là message consumer thay vì ExecutorService

Với Kafka/JMS/RabbitMQ hoặc một broker khác, cần bổ sung các thao tác có ý nghĩa nghiệp vụ:

~~~text
RUNNING
  |
  +-- pause/stop polling new deliveries
  +-- stop extending queue of unacked messages
  +-- keep in-flight task contexts alive
  +-- finish business transaction
  +-- commit/ack if successful
  +-- nack/requeue/let lease expire on incomplete work
  +-- close consumer/session/client as owner contract permits
  +-- signal SmartLifecycle stop callback
~~~

**Không ack một message chỉ vì đã nhận hoặc chỉ vì JVM sắp shutdown.** Ack phải theo contract về durable processing. Nếu job chưa hoàn thành:
- Có thể để broker retry.
- Cần idempotency key để chống xử lý trùng.
- Với transactional outbox, cần đảm bảo event/DB commit đồng nhất.
- Có thể dùng lease timeout để công việc bị bỏ dở được nhận bởi instance khác.
- Phải xác định thứ tự ngừng consumer trước khi đóng database connection pool mà handler đang dùng.

Không chuyển nguyên code fake latch của bài vào Kafka production. Dùng lifecycle API của listener container và broker-specific semantics thay vì tự giả định `executor.shutdown()` tương đương stop polling.

## 16. Nếu công việc là batch job dài

Với batch job hoặc scheduled job:
- Có thể giữ checkpoint theo từng chunk.
- Dừng nhận job mới nhưng cho chunk đang chạy hoàn thành.
- Kết quả có thể là COMPLETED, STOPPED, FAILED hoặc CANCELED tùy framework.
- Timeout có thể yêu cầu lưu progress và retry sau khi process mới lên.
- Một job quan trọng không nên chỉ dựa vào trạng thái trong RAM khi shutdown.

Ví dụ với Spring Batch, cần dùng JobRepository và cơ chế stop/restart theo contract Spring Batch thay vì xem `SmartLifecycle` thay thế tất cả job metadata. Bài mô phỏng chỉ cung cấp **mẫu tư duy lifecycle và synchronization**.

### Stop tốt là stop có khả năng quan sát

Với batch thực, cần ghi:
- Job ID, attempt ID hoặc correlation ID.
- Thời điểm bắt đầu stop.
- Số task/chunk chưa hoàn thành.
- Deadline và thời gian drain thực tế.
- Kết quả commit/rollback/ack.
- Lý do fail/timeout.
- Có cần retry hay được đánh dấu thành công không?

Tránh log payload cá nhân, secret hoặc access token.

## 17. Theo dõi số công việc in-flight

Trong demo, `AtomicInteger inFlight` mô tả số job đã nhận nhưng chưa chạy xong. Counter hợp lệ vì:
- Tăng trước khi submit thành công.
- Rollback khi submit ném exception.
- Giảm trong `finally` của task.
- Test chỉ đọc sau các tín hiệu có thứ tự.

Trong hệ thống nhiều loại work, nên tách:
- `queued`: đã nhận nhưng chưa bắt đầu.
- `inFlight`: đang xử lý.
- `completed`: đã hoàn tất.
- `failed`: có lỗi.
- `cancelled`: bị hủy.
- `rejected`: bị từ chối khi shutdown.

**Không nên chỉ nhìn executor queue empty để kết luận dừng xong.** Queue rỗng nhưng một task đang chạy vẫn có thể giữ transaction hoặc connection. `ExecutorService.awaitTermination(...)` trả true khi executor đã terminated sau shutdown, nhưng đó cũng không chứng minh một external side effect đã được commit thành công nếu code task xử lý lỗi sai.

### Metrics và health/readiness

Trong production, có thể xuất metrics:
- Gauge `inflight_jobs`.
- Gauge `accepting_work` hoặc state RUNNING/STOPPING.
- Counter `shutdown_rejected_total`.
- Timer `shutdown_drain_duration`.
- Counter `shutdown_forced_total`.
- Event/log cho timeout.

Health/liveness và readiness cần thiết kế riêng: một instance STOPPING có thể vẫn sống về process nhưng không nên nhận traffic mới. Không coi `liveness=false` là bước đầu tiên của graceful shutdown vì orchestrator có thể kill instance sớm hơn dự kiến.

## 18. Kiểm thử concurrency có tính quyết định

### 18.1. Happy path

Bắt đầu một job, đợi jobStarted, yêu cầu stop, đợi stopRequested, thử submit lần nữa và xác nhận bị từ chối. Sau đó release job; đợi callback; xác minh in-flight = 0 và isRunning = false.

### 18.2. Callback không được gọi trước job completion

Giữ `releaseJob` chưa mở. `stop(Runnable)` đã được gọi, nhưng `stopped.await(50ms)` trả false. Đây là kiểm tra quan trọng nhất để ngăn bug “callback sau shutdown() nhưng trước termination”.

### 18.3. Stop hai lần

Gọi `stop(callbackA)` rồi `stop(callbackB)` khi state STOPPING. Cả hai callback phải chạy sau cùng một lượt executor shutdown. Không sinh thêm executor hoặc coordinator mới; nếu callbackA ném RuntimeException, callbackB vẫn cần có cơ hội chạy.

### 18.4. Stop khi chưa start

Một implementation đời thực phải có hợp đồng rõ khi stop được gọi trước start. Trong demo, state NEW chuyển STOPPED và callback được chạy ngay; không có executor cần dọn. Sau đó start lại bị từ chối vì demo không hỗ trợ restart. Nếu requirement thật cần start sau stop chưa chạy, phải đổi state machine và tests.

### 18.5. Stop sau khi đã STOPPED

Gọi stop lần nữa không close resource trùng; `stop(callback)` khi STOPPED vẫn gọi callback ngay để hoàn tất hợp đồng của caller. Trong `@PreDestroy`, stop đồng bộ vì vậy trở thành no-op.

### 18.6. Stop cạnh tranh với submit

Dùng hai thread và một barrier để cùng tiến vào monitor. Một submit có thể thắng lock và được nhận **trước** khi state chuyển STOPPING; hoặc stop thắng và submit bị từ chối. Điều đúng là **không có submit nào được chấp nhận sau khi STOPPING đã được công bố**. Không viết test ép một kết quả duy nhất nếu thứ tự race chưa được kiểm soát.

### 18.7. Failure/timeout

Tạo task không trả về hoặc bỏ qua interrupt trong môi trường test có timeout. Xác minh:
- Executor vẫn chưa terminated.
- Callback không báo thành công giả.
- Có diagnostic timeout.
- Framework chờ tối đa phase timeout theo cấu hình.
- Test process vẫn có cách force-cleanup trong subprocess để không làm treo toàn suite.

Những test cố tình tạo thread không chịu dừng nên chạy ở **subprocess cách ly**, không để non-daemon worker kéo dài vô hạn trong test runner chính.

## 19. Bảng kiểm lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `System.exit(0)` ngay khi có job | Mất dữ liệu/không kịp commit | Dừng nhận, drain, đóng context trước exit |
| Chỉ dùng `executor.shutdown()` rồi gọi callback | Báo phase đã dừng khi job vẫn chạy | Đợi `awaitTermination` trước callback |
| Gọi `shutdownNow()` ngay từ đầu | Interrupt work đang làm, không graceful | Cho grace period trước, force theo policy |
| Không chặn submit khi STOPPING | Queue tiếp tục tăng, shutdown kéo dài | Guard state dưới lock, reject mới |
| Dùng volatile boolean với check-then-submit rời rạc | Race giữa submit và shutdown | Cùng monitor hoặc state machine/queue protocol |
| Dùng `Thread.sleep` để ép thứ tự | Flaky trên CI | CountDownLatch/Phaser/Barrier |
| Không giữ callback stop lần hai | Caller hoặc framework chờ vô ích | Queue callbacks trong STOPPING |
| Gọi callback dưới lock | Reentrant deadlock hoặc block không cần thiết | Copy callback list, gọi ngoài lock |
| `isRunning=false` quá sớm | Framework/test nghĩ resource đã dừng | Chỉ chuyển sau termination |
| Không có @PreDestroy fallback | Partial shutdown có thể rò resource | Cleanup idempotent từ destroy |
| Đóng shared client trước worker | Job đang chạy lỗi giữa chừng | Stop phase/dependency, owner lifetime đúng |
| Phase timeout thấp hơn task deadline | Spring tiếp tục destroy trước callback | Căn chỉnh deadlines, test worst-case |
| Không xử lý InterruptedException | Task vẫn chạy hoặc hủy sai | Restore flag, cleanup, có policy |
| Bỏ qua forced termination | Mất dữ liệu khi SIGKILL/crash | Checkpoint, retry, idempotency |
| Đếm chỉ task queue | Bỏ sót task đang chạy | Theo dõi in-flight và termination |
| Xem ContextClosedEvent như “đã đóng xong” | Đọc trạng thái sai | Phân biệt event bắt đầu close với close return |
| Không join close thread trong test | Assertion chạy trước shutdown hoàn tất | Join/future với timeout |
| Kéo một latch demo vào production | Logic cố ý block không có deadline nghiệp vụ | Dùng task completion/cancellation thực |
| Giả định restart được sau stop | Executor/latches đã dùng xong | Tạo generation mới nếu yêu cầu restart |
| Đưa System.exit vào JUnit test | Giết cả test JVM | Subprocess khi test process exit |

## 20. Khi nào nên chọn giải pháp khác?

### Một job đơn giản trong một method

Nếu work đồng bộ và caller có thể chờ bằng method call thông thường, không nhất thiết cần SmartLifecycle. Có thể dùng `try-with-resources` để mở/đóng tài nguyên ở đúng scope.

### Một pool tác vụ do Spring quản lý

Nếu đang dùng `ThreadPoolTaskExecutor` hoặc `TaskScheduler` do Spring quản lý, hãy tận dụng cấu hình shutdown và lifecycle của chính bean/framework. Không tự bọc một executor thứ hai rồi tạo thêm thread không cần thiết.

### Một background consumer cần có API pause/resume

Nếu bạn chỉ muốn tạm ngừng nhận message mà giữ application context hoạt động, điều khiển consumer/listener container riêng. `context.close()` là lệnh kết thúc toàn context, không dùng làm pause nếu cần khởi động lại cùng bean.

### Một web server đang chạy

Dùng graceful shutdown của embedded web server/Actuator readiness và điều phối ở tầng deployment. Đừng chọn demo non-web rồi kết luận chỉ cần một CountDownLatch là HTTP request sẽ được drain đúng.

### Một công việc phải tồn tại vượt process

Nếu cần kết quả sau JVM restart/crash, dùng hàng đợi bền vững, database checkpoint, transaction hoặc workflow engine. Thread và latch chỉ tồn tại trong RAM của process, không thể bảo đảm durability.

## 21. Câu hỏi ôn tập

**Câu 1:** Vì sao `ExecutorService.shutdown()` không đủ chứng minh worker đã dừng?

**Trả lời:** Nó ngừng nhận task mới nhưng không đợi task đang chạy kết thúc. Cần chờ termination hoặc có completion protocol.

**Câu 2:** Tại sao test phải đợi `jobStarted` trước khi yêu cầu close?

**Trả lời:** Để chắc chắn task đã thực sự bắt đầu, không chỉ vừa được submit. Nếu không, test có thể kiểm tra một job chưa chạy.

**Câu 3:** Tại sao test đợi `stopRequested` trước khi thử gửi job muộn?

**Trả lời:** Để đảm bảo state đã chuyển STOPPING, từ đó việc từ chối submit có kết quả xác định.

**Câu 4:** Khi nào được gọi `SmartLifecycle.stop(Runnable)` callback?

**Trả lời:** Sau khi component thực sự hoàn tất dừng theo contract, không phải ngay sau khi gửi yêu cầu shutdown.

**Câu 5:** Vì sao callback được gọi ngoài `synchronized(monitor)`?

**Trả lời:** Callback có thể truy cập state hoặc bean khác, dẫn tới reentrant deadlock/block nếu giữ lock.

**Câu 6:** Khi `ContextClosedEvent` được phát, mọi bean đã destroy chưa?

**Trả lời:** Chưa. Event được phát khi bắt đầu đóng, trước lifecycle stop và singleton destruction trong đường close thông thường.

**Câu 7:** Tại sao main không gọi `context.close()` trực tiếp trước `releaseJob`?

**Trả lời:** Vì close có thể đợi callback stop, trong khi worker cần main mở latch; nếu làm tuần tự trên cùng thread sẽ tạo deadlock/tới deadline.

**Câu 8:** `@PreDestroy` thay thế được `stop(Runnable)` không?

**Trả lời:** Không. Destruction callback không cung cấp completion signaling cho LifecycleProcessor theo phase; cả hai có vai trò riêng.

**Câu 9:** `spring.lifecycle.timeout-per-shutdown-phase` có tự interrupt task bị treo không?

**Trả lời:** Không. Nó giới hạn thời gian Spring chờ phase; executor/task cần timeout và cancellation riêng.

**Câu 10:** Vì sao `isRunning()` trong demo vẫn true ở STOPPING?

**Trả lời:** Vì executor/job còn hoạt động; component chưa hoàn tất việc stop. Chỉ sau termination mới false.

**Câu 11:** Nếu job bỏ qua interrupt, `shutdownNow()` có chắc kết thúc nó không?

**Trả lời:** Không. Java interrupt là tín hiệu hợp tác; cần policy escalation, isolation và recovery khác.

**Câu 12:** Nếu stop được gọi hai lần trong lúc STOPPING, cần làm gì?

**Trả lời:** Không shutdown resource lần hai; gộp vào quá trình stop đang chạy và lưu callback mới cho khi hoàn tất.

**Câu 13:** Trong demo, có thể gọi `start()` sau `stop()` không?

**Trả lời:** Không, mã demo cố ý từ chối để tránh reuse latches/executor. Ứng dụng cần restart phải triển khai generation mới.

**Câu 14:** Nếu worker sử dụng DataSource, ai nên dừng trước?

**Trả lời:** Worker cần ngừng nhận work và hoàn tất transaction trước khi DataSource owner đóng pool, thông qua lifecycle/ownership đúng.

**Câu 15:** In-flight bằng 0 có đồng nghĩa mọi external side effect đã durable không?

**Trả lời:** Không. Nó chỉ mô tả trạng thái task trong JVM; commit/ack/durability phải theo contract nghiệp vụ.

**Câu 16:** Vì sao không dùng SmartLifecycle đơn thuần để bảo đảm exactly-once sau crash?

**Trả lời:** JVM crash có thể bỏ qua lifecycle và retry có thể chạy lại job; cần idempotency, transaction, lease/checkpoint bên ngoài.

**Câu 17:** `context.close()` có đồng nghĩa `System.exit()`?

**Trả lời:** Không. Close đóng một context; System.exit bắt đầu shutdown toàn JVM và có process exit status.

**Câu 18:** Vì sao không chỉ dùng `Thread.sleep(100)` trong test concurrency?

**Trả lời:** Không chứng minh event thực xảy ra trước/sau, phụ thuộc tải hệ thống, dễ flaky; latch có quan hệ happens-before rõ.

## 22. Bài tập mở rộng

### Bài tập A — số job nhiều hơn một

Đổi `newSingleThreadExecutor` thành pool cố định 2 hoặc 3 threads; nhận ba task, cho hai task chờ latch và một task hoàn thành sớm. Theo dõi queued/in-flight riêng. Chỉ báo callback sau khi cả ba job đã kết thúc.

### Bài tập B — callback bị gọi sớm

Cố ý gọi callback ngay sau `executor.shutdown()` trong bản test riêng. Kiểm tra test mục 8 phát hiện lỗi. Khôi phục implementation đúng và bảo đảm tests PASS.

### Bài tập C — stop lặp

Thêm ba callback khác nhau khi worker STOPPING. Dùng counter hoặc CountDownLatch(3) để kiểm tra mỗi callback chạy đúng một lần và không có executor shutdown trùng.

### Bài tập D — job bị interrupt

Tạo job có thời hạn dài hơn deadline graceful, không mở latch cho tới sau deadline; kiểm tra `shutdownNow()` gửi interrupt. Ghi lại sự khác biệt giữa “hoàn tất tự nhiên” và “cancellation”. Dùng subprocess khi có nguy cơ task không dừng.

### Bài tập E — graceful shutdown web

Tạo một phiên bản riêng có `spring-boot-starter-web` và endpoint slow request nhưng có deadline. Bật `server.shutdown=graceful`; gửi SIGTERM từ script/terminal riêng, đo request in-flight, readiness và response. Không đặt System.exit trong controller.

### Bài tập F — thay CountDownLatch bằng queue thật

Sử dụng `BlockingQueue` với producer/consumer, stop nhận work mới rồi cho consumer xử lý hết queue. Chú ý race giữa producer đang submit và shutdown, cơ chế poison pill/close queue và timeout.

### Bài tập G — tạo generation restart được

Mở rộng state machine để `STOPPED → RUNNING` bằng một `ExecutorService` và bộ latches mới cho mỗi generation. Kiểm tra start/stop lặp, không tạo hai worker hoặc dùng lại CountDownLatch đã đếm về 0.

### Bài tập H — đo thời gian drain

Dùng `System.nanoTime()` để đo từ lúc STOPPING tới STOP_COMPLETED. Ghi metric histogram/timer; không đo bằng timestamp định dạng text có độ chính xác thấp và không dùng nanoTime như wall clock.

### Bài tập I — điều phối shutdown nhiều phase

Thêm bean giả `SharedInfrastructure implements SmartLifecycle` với phase -100. Worker phase +100 phụ thuộc nó. Assert worker stop trước hạ tầng và job không dùng resource đã đóng.

### Bài tập J — cleanup khi startup fail

Cho bean worker mở executor nhưng sau đó khởi tạo một dependency thất bại. Viết rollback đường khởi tạo và cleanup fallback, không dựa tuyệt đối vào context.close vì bean chưa đăng ký thành công có thể không nhận destroy callback.

### Bài tập K — active counter khi exception

Cho task ném exception sau khi bắt đầu nhưng trước khi tự return. Xác nhận `finally` luôn giảm inFlight, không để metric kẹt ở 1. Thêm log lỗi mà không lộ payload nhạy cảm.

### Bài tập L — readiness và traffic drain

Trong một app có Actuator, chuyển readiness sang refusing traffic trước khi ngừng worker. Đo thời gian để load balancer ngừng gửi request và đảm bảo deadline của Kubernetes không ngắn hơn tổng các bước drain thực tế.

## 23. Checklist review một controlled shutdown

Trước khi chuyển demo thành hệ thống thực, phải trả lời:

1. **Nguồn work** là gì: HTTP, broker, scheduler, batch hay pool?
2. **Ai sở hữu** worker/executor/client và ai có quyền gọi shutdown?
3. **Điểm dừng nhận việc mới** ở đâu? Có race với producer không?
4. **In-flight** được đếm từ mốc nào tới mốc nào? Có rollback khi submit fail không?
5. **Cơ chế chờ completion** là gì: Future, latch, queue drain, awaitTermination hay broker ack?
6. **Callback stop** chỉ đến sau termination hay được báo sớm?
7. **Có nhiều stop callers** không? Mỗi callback có được hoàn tất đúng contract?
8. **Deadline** ở cấp task, executor, lifecycle phase và orchestrator đã tương thích chưa?
9. **Interrupt/cancel** có được task xử lý an toàn không?
10. **Resource dependencies** có sống đủ lâu để job hoàn tất không?
11. **@PreDestroy** có cleanup fallback và idempotent không?
12. **ContextClosedEvent** có bị hiểu nhầm thành đã destroy xong không?
13. **Readiness/traffic drain** có thiết kế nếu là web/microservice không?
14. **Crash/SIGKILL** có recovery/idempotency/checkpoint bên ngoài không?
15. **Metrics/log** có ghi rõ số in-flight, rejected, completed, timeout?
16. **Unit/integration tests** có kiểm tra chính thứ tự shutdown thay vì chỉ “không ném exception”?
17. **Production restart** có cần hỗ trợ generation mới sau stop không?
18. **Bảo mật** có đảm bảo log không chứa token/customer payload hay job secrets?

## 24. Tài liệu chính thức

- [Spring Framework — Lifecycle và SmartLifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): thứ tự phase, stop callback, Spring lifecycle processor và bean destruction.
- [Spring Framework — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html): `start`, `stop(Runnable)`, `isRunning`, callback và auto-start.
- [Spring Framework — DefaultLifecycleProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): chờ callback và timeout của phase.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): quá trình đóng web ApplicationContext, graceful server request drain và `spring.lifecycle.timeout-per-shutdown-phase`.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): khởi tạo context, runners, events và shutdown hook.
- [Spring Boot 3.5.16 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): cấu hình non-web và đăng ký shutdown hook.
- [Java SE 17 — ExecutorService Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`, hợp đồng termination.
- [Java SE 17 — CountDownLatch Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordination, memory consistency effects và timeout.
- [Java SE 17 — Thread Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): interrupt, daemon threads và lifecycle.

### Ghi nhớ cuối cùng

1. **Ngừng nhận work mới trước khi drain work cũ**; cả hai phải được đồng bộ tránh race.
2. `ExecutorService.shutdown()` **không đợi task hoàn tất**; sử dụng `awaitTermination` và callback đúng thời điểm.
3. `SmartLifecycle.stop(Runnable)` phải gọi callback **sau khi component thực sự dừng**.
4. `CountDownLatch` giúp mô phỏng trạng thái in-flight và thứ tự shutdown xác định mà không dùng sleep giả.
5. Trong demo, `ContextClosedEvent` đến **trước** lifecycle stop, còn `@PreDestroy` đến **sau** stop thành công.
6. Không gọi `context.close()` trực tiếp trên thread duy nhất còn giữ quyền giải phóng task, nếu điều đó tạo dependency vòng.
7. Có timeout và failure policy; **không báo STOPPED khi executor còn sống**.
8. `getPhase()` và resource ownership quyết định thứ tự worker, client, pool được đóng.
9. Dừng JVM cưỡng bức không bảo đảm chạy callback; job quan trọng cần **transaction, retry, idempotency và checkpoint**.
10. Một shutdown đáng tin phải **được kiểm thử về thứ tự, rejection, completion, thời gian và cleanup**, không chỉ thấy process cuối cùng tắt.
