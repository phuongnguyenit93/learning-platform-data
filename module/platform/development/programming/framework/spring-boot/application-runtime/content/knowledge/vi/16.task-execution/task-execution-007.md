# Truyền ngắt luồng và thiết kế tác vụ có thể hủy

## 1. Mục tiêu: hủy một tác vụ mà không làm hỏng trạng thái hệ thống

Trong Spring Boot, một công việc có thể chạy trong luồng xử lý HTTP, `ApplicationRunner`, `@Async`, `@Scheduled`, executor xử lý job nền hoặc consumer nhận message. Khi người dùng hủy job, request hết thời hạn hoặc application shutdown, công việc cần kết thúc **có kiểm soát**, chứ không chỉ ngừng in log.

Những câu hỏi cần trả lời:

- Ai sở hữu công việc, ai được phép gửi yêu cầu hủy?
- Tín hiệu hủy đến task bằng cách nào?
- Task đang chạy CPU loop, `sleep`, chờ queue, I/O mạng hay database có phản ứng không?
- Khi đang ghi database hoặc ack message, task có thể dừng tại điểm nào an toàn?
- Bên điều phối có phân biệt được **đã yêu cầu hủy** với **đã thực sự kết thúc** không?
- Shutdown của Spring context có đủ thời gian drain, cleanup và đóng các dependency không?

Trong Java, **interruption là yêu cầu hợp tác**. `Thread.interrupt()` không phải lệnh cưỡng bức giết luồng. Task phải phản hồi với cờ ngắt hoặc `InterruptedException`, đồng thời thiết kế timeout, cleanup và phục hồi công việc chưa xong. Đối với I/O không hỗ trợ ngắt, cần sử dụng cancellation API của thư viện hoặc deadline riêng.

Nội dung áp dụng cho **Java 17+**, Spring Framework 6.x và Spring Boot 3.3.x. Ví dụ runnable trong bài dùng Spring Boot 3.3.13, Java 17, Maven và `spring-boot-starter`.

## 2. Thread interruption là một tín hiệu, không phải thao tác dừng tức thời

Mỗi `Thread` trong Java có **interrupted status**. Một thread có thể yêu cầu thread khác ngắt:

```java
worker.interrupt();
```

`worker` là tham chiếu `Thread` giả định đã được tạo; đây là câu lệnh minh họa.

Ở thread nhận tín hiệu, có thể kiểm tra:

```java
boolean requested = Thread.currentThread().isInterrupted();
```

Khi worker đang bị chặn trong những API hỗ trợ ngắt như `Thread.sleep`, `Object.wait`, `Thread.join` hoặc `BlockingQueue.take`, API thường ném `InterruptedException`. Nhưng nếu worker chạy CPU loop không kiểm tra cờ, nó có thể tiếp tục chạy vô hạn dù đã bị interrupt.

| API / tình huống | Ý nghĩa |
| --- | --- |
| `someThread.interrupt()` | Yêu cầu ngắt `someThread`; **không bảo đảm task đã dừng** |
| `someThread.isInterrupted()` | Đọc interrupted status của thread được chỉ định, **không xóa cờ** |
| `Thread.currentThread().isInterrupted()` | Đọc cờ của thread hiện tại, không xóa |
| `Thread.interrupted()` | Static method: đọc cờ thread hiện tại **và xóa cờ** |
| `Thread.sleep(...)` khi bị ngắt | Ném `InterruptedException`, thông thường xóa cờ khi ném |
| CPU loop không kiểm tra cờ | Có thể bỏ qua yêu cầu ngắt |
| Blocking HTTP/JDBC call | Hành vi phụ thuộc client/driver; phải cài timeout/cancel riêng |
| `Thread.stop()` | Đã deprecated vì không an toàn; **không sử dụng** |

### 2.1. `isInterrupted()` và `Thread.interrupted()` không hoán đổi được

```java
Thread thread = Thread.currentThread();

boolean a = thread.isInterrupted(); // Đọc nhưng không reset.
boolean b = Thread.interrupted();    // Đọc và reset cờ hiện tại.
```

Giả sử cờ đã là `true`. Sau `isInterrupted()`, code phía sau vẫn nhận thấy interrupt; sau `Thread.interrupted()`, cờ đã bị xóa. Vì vậy, vòng lặp muốn **quan sát** yêu cầu hủy thường dùng:

```java
while (!Thread.currentThread().isInterrupted()) {
    processNextChunk();
}
```

Đây là đoạn minh họa cần `processNextChunk()` có thật và mỗi vòng đủ ngắn. Nếu hàm xử lý block trong một API không phản ứng với interrupt, kiểm tra cờ ở đầu vòng **không đủ** để bảo đảm thời gian hủy.

### 2.2. Vì sao `InterruptedException` thường làm cờ bị xóa?

`InterruptedException` đã là một tín hiệu có kiểu cho tầng gọi biết thread bị yêu cầu ngắt trong khi đang đợi. Nhiều blocking API xóa interrupted status khi ném exception. Do đó, nếu bạn bắt exception và không truyền đi, code phía trên có thể không còn nhìn thấy cờ interrupt.

Có hai cách xử lý chủ đạo:

1. **Truyền `InterruptedException` lên tầng gọi** khi signature cho phép.
2. **Khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi thoát công việc** khi không thể khai báo checked exception.

Không được bắt rồi âm thầm tiếp tục như thể tác vụ hoàn thành bình thường.

## 3. Truyền ngắt xuyên suốt các method

### 3.1. Propagate là cách đơn giản nhất khi API cho phép

```java
void waitForData() throws InterruptedException {
    Thread.sleep(1000L);
}

void processBatch() throws InterruptedException {
    waitForData();
    commitResult();
}
```

Đây là mã minh họa; `commitResult()` cần được cài đặt riêng. Nếu thread bị interrupt trong `waitForData()`, exception lan ra khỏi `processBatch()` và **không thực hiện** `commitResult()`.

Lợi ích là tầng điều phối biết task không hoàn tất thành công. Không wrap exception vô nghĩa hoặc đặt một `catch` ở helper chỉ để ghi log rồi chạy tiếp.

### 3.2. Boundary không thể ném checked exception

`Runnable#run()` không cho khai báo `throws InterruptedException`. Hãy khôi phục cờ và kết thúc:

```java
Runnable worker = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            Thread.sleep(1000L);
            processOneBatch();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        closeOwnedResources();
    }
};
```

`processOneBatch()` và `closeOwnedResources()` là các method giả định có sẵn trong class chứa đoạn code. `finally` chạy khi task thoát, phục vụ giải phóng tài nguyên **do task sở hữu**. Nếu cleanup có I/O, vẫn cần giới hạn thời gian và chính sách riêng khi cleanup thất bại.

Nếu tầng trên cần nhận lý do, có thể ở một boundary phù hợp:

```java
try {
    performBlockingStartupStep();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Startup cancelled", e);
}
```

Đây là đoạn minh họa có method `performBlockingStartupStep()` khai báo `throws InterruptedException`. Có thể phù hợp trong startup bắt buộc, nhưng ở API request hoặc message worker, cần chuyển thành trạng thái cancellation của domain thay vì mặc định coi mọi interrupt là business error.

### 3.3. Mẫu sai: nuốt ngắt

```java
try {
    Thread.sleep(1000L);
} catch (InterruptedException ignored) {
    System.out.println("still working");
}
continueProcessing();
```

`continueProcessing()` là method minh họa. Bằng cách này, task bỏ qua lệnh hủy; cờ interrupt có thể đã bị xóa bởi `sleep`. Hậu quả là shutdown kéo dài hoặc job tiếp tục ghi dữ liệu sau khi người dùng đã hủy.

Mẫu sai khác:

```java
while (true) {
    try {
        Thread.sleep(1000L);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
```

Vòng lặp vẫn không có đường thoát. Mỗi vòng sau có thể gặp `InterruptedException` ngay lập tức, gây busy loop. **Khôi phục cờ phải đi cùng quyết định rời tác vụ**, hoặc propagate exception lên tầng kiểm soát.

### 3.4. `finally` không thay thế thiết kế transaction

Nếu interrupt đến giữa các bước `read -> update database -> ack message`, việc cleanup bộ nhớ không tự rollback database commit hoặc gửi lại message. Cần ranh giới transaction, idempotency key, cách lưu checkpoint và quy tắc chỉ ack khi kết quả đã bền vững.

Không log “success” khi task chỉ xử lý được một phần rồi bị hủy. Trạng thái `CANCELLED`, `TIMED_OUT`, `FAILED` và `SUCCEEDED` phải có định nghĩa nghiệp vụ rõ.

## 4. Thiết kế tác vụ CPU-bound và I/O-bound có thể hủy

### 4.1. CPU-bound: kiểm tra giữa các chunk

Với xử lý dữ liệu lớn:

```java
for (int i = 0; i < items.size(); i++) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    transform(items.get(i));
}
```

Đoạn này minh họa, cần `items` và method `transform(...)` có thật. Nếu một lần `transform` mất vài chục phút, chỉ kiểm tra trước nó vẫn không bảo đảm cancel nhanh. Hãy phân chia tác vụ thành những chunk có giới hạn, có checkpoint và kiểm tra thường xuyên hợp lý.

**Không cần** kiểm tra interrupt sau từng phép cộng trong một vòng tính toán cực nhỏ nếu nó tạo overhead không đáng có; chọn điểm kiểm tra phù hợp với yêu cầu cancellation latency.

### 4.2. Blocking queue hoặc chờ điều kiện

API như `BlockingQueue.take()` có khả năng ném `InterruptedException`; thường nên propagate ở worker method hoặc restore cờ rồi break khi ở `Runnable`.

Tránh dùng `while (true) { queue.poll(); }` quay liên tục và tốn CPU. Nếu dùng `poll(timeout, unit)`, code có thể định kỳ kiểm tra cancellation token hoặc shutdown flag, nhưng vẫn cần phản ứng đúng với interrupt.

### 4.3. I/O bên ngoài có thể không phản ứng với interrupt

Không có bảo đảm chung rằng `Thread.interrupt()` sẽ dừng ngay:

- HTTP request đang chờ response.
- JDBC query đang chạy ở database.
- SDK cloud có retry nội bộ.
- File I/O hoặc native blocking call của một thư viện.
- Kết nối message broker không có deadline.

Phải xem contract client cụ thể và thiết kế connect/read timeout, request cancellation API, SQL query timeout, deadline tổng cùng khả năng retry. Có thể thread đã bị đánh dấu interrupted nhưng I/O vẫn đang block cho đến khi socket timeout.

Đừng thay timeout thực tế bằng một `Future.cancel(true)` rồi coi như đã giải quyết vấn đề.

### 4.4. Cancellation token khi interrupt chưa đủ

Một cờ hợp tác ở tầng ứng dụng:

```java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean(false);

    public void cancel() {
        requested.set(true);
    }

    public boolean isCancellationRequested() {
        return requested.get();
    }
}
```

Đây là file Java 17 độc lập có thể đặt ở `CancellationToken.java`. Worker kiểm tra token giữa các chunk. Token hữu ích khi muốn truyền yêu cầu hủy qua nhiều phương thức hoặc giữ handle qua job registry. Tuy nhiên, token **không tự đánh thức** một `sleep` hoặc network call; thường kết hợp token + interrupt + I/O timeout.

### 4.5. Deadline tổng khác timeout cho một lần gọi

Một task có bốn request, mỗi request timeout 20 giây và thêm retry có thể vượt budget 60 giây. Deadline cần bao phủ cả I/O, retry, backoff, xử lý dữ liệu và cleanup trong phạm vi cho phép.

Đối với thời lượng trong cùng JVM, `System.nanoTime()` là nguồn đo elapsed time phù hợp hơn clock timestamp:

```java
long started = System.nanoTime();
long budget = TimeUnit.SECONDS.toNanos(30);

while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    long remaining = budget - (System.nanoTime() - started);
    if (remaining <= 0L) {
        throw new IllegalStateException("Job deadline exceeded");
    }
    processChunkWithin(remaining);
}
```

Đây là đoạn minh họa, cần `hasMoreWork()` và `processChunkWithin(...)` có thật. Với business API, chọn exception/status hợp lý thay vì luôn dùng `IllegalStateException`. Cần xử lý ràng buộc giá trị budget và không truyền duration âm sang client.

## 5. `Future.cancel(true)`: yêu cầu ngắt chứ chưa chứng minh đã dừng

Với `ExecutorService`:

```java
Future<?> future = executor.submit(() -> doWork());
boolean accepted = future.cancel(true);
```

Hai biến `executor` và `doWork()` cần định nghĩa phù hợp. `mayInterruptIfRunning=true` yêu cầu implementation thử interrupt thread chạy task, nếu thread đó được biết tới.

| Trạng thái task lúc gọi cancel | Điều có thể xảy ra |
| --- | --- |
| Chưa được chạy | Task thường bị ngăn không chạy |
| Đang chạy và hỗ trợ interrupt | Nhận tín hiệu, thoát qua cờ hoặc exception |
| Đang chạy nhưng bỏ qua interrupt | `Future` có thể đã cancelled mà phần thân task còn chạy |
| Đã hoàn tất | `cancel` thường không thay đổi kết quả |
| Executor implementation khác | Cần đọc hợp đồng thực tế; không giả định mọi executor giống nhau |

**`future.isCancelled()` biểu thị trạng thái của Future, không nhất thiết chứng minh code của task đã chạy xong `finally`.** Nếu cần đóng dependency an toàn, hãy đợi completion signal riêng hoặc executor termination.

### 5.1. `Future.get(timeout)` không tự hủy task

```java
try {
    Object value = future.get(2, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException e) {
    future.cancel(true);
    throw e;
}
```

Đây là minh họa: `future`, `use` cần có; method chứa đoạn code cần khai báo/giải quyết các checked exceptions. `get(timeout)` chỉ giới hạn **thời gian chờ của caller**. Đến `TimeoutException`, worker vẫn có thể đang chạy; muốn hủy phải chủ động gửi yêu cầu và task phải hợp tác.

Nếu chính caller bị ngắt trong lúc `get(...)`, hãy cân nhắc hủy child task rồi propagate `InterruptedException` hoặc restore cờ ở boundary phù hợp.

### 5.2. `CompletableFuture.cancel(true)` khác `FutureTask`

Đây là điểm dễ sai khi sử dụng async APIs:

```java
CompletableFuture<Void> result =
        CompletableFuture.runAsync(this::longRunningTask);
result.cancel(true);
```

Đoạn trên giả định `longRunningTask()` tồn tại. Theo JavaDoc, `CompletableFuture.cancel(boolean)` không dùng interrupt để điều khiển công việc; tham số `mayInterruptIfRunning` **không có tác dụng** đối với implementation này. Future có thể chuyển sang cancelled trong khi `longRunningTask` vẫn đang làm việc.

Tương tự, `CompletableFuture.orTimeout(...)` có thể làm future hoàn thành bất thường vì timeout nhưng không bảo đảm body bên dưới dừng. Nếu cần cancellation thực sự, dùng handle của executor-owned `Future`, cancellation token hoặc API abort của thư viện phù hợp, rồi kiểm tra completion.

## 6. Shutdown một executor: mềm trước, mạnh sau

Phân biệt ba lệnh:

- `ExecutorService.shutdown()`: không nhận tác vụ mới, cho tasks đã nộp tiếp tục theo chính sách executor; **không chủ động interrupt mọi task**.
- `ExecutorService.shutdownNow()`: cố ngừng tasks đang chạy (thường interrupt) và trả về danh sách queued tasks chưa bắt đầu; **không bảo đảm** chúng đã dừng hết.
- `awaitTermination(timeout, unit)`: chờ executor thật sự termination trong một ngân sách, trả `false` nếu chưa xong; có thể bị interrupt khi chờ.

Mẫu xử lý:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Tasks still running");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là snippet minh họa trong một method có `ExecutorService executor` và import `TimeUnit`. Thời lượng 10+5 giây là ví dụ, phải phù hợp shutdown budget thực tế. `shutdownNow()` không phải kill switch; nếu task bỏ qua interrupt, phải có chính sách log, retry hoặc phục hồi khi process kết thúc.

### 6.1. Phối hợp với tài nguyên phụ thuộc

Thứ tự an toàn thường là:

```text
Ngừng nhận job mới
        ↓
Cho in-flight tasks drain trong deadline
        ↓
Yêu cầu cancel tasks vượt thời hạn
        ↓
Đợi xác nhận task dừng / ghi nhận task chưa xong
        ↓
Đóng database/HTTP client/message transport do task còn dùng
```

Nếu đóng connection pool trước khi worker hoàn tất ghi kết quả, một tác vụ đã nhận interrupt vẫn có thể gặp lỗi trong cleanup hoặc mất ack. Đó là lý do ứng dụng cần lifecycle coordination, không chỉ gọi `shutdownNow()` từ một shutdown hook tùy ý.

## 7. Ví dụ hoàn chỉnh: Spring Boot 3.3 + Java 17 hủy task có xác nhận

Ví dụ này tạo một `ExecutorService` dưới dạng Spring bean và dùng `ApplicationRunner` để gửi task. Task thông báo đã bắt đầu qua `CountDownLatch`, sau đó chờ trong `Thread.sleep`. Caller gửi `Future.cancel(true)` và **đợi latch kết thúc riêng** để xác nhận phần thân task đã rời khỏi `finally`.

Không cần HTTP server. Trên luồng startup này, demo hoàn thành rồi mới cho `SpringApplication.run()` trả về.

### 7.1. Cấu trúc dự án

```text
cancellable-worker-demo/
├── pom.xml
└── src/main/java/com/example/cancel/
    └── CancellableWorkerApplication.java
```

### 7.2. File `pom.xml`

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
    <artifactId>cancellable-worker-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 7.3. File `CancellableWorkerApplication.java`

```java
package com.example.cancel;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CancellableWorkerApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(CancellableWorkerApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner được Boot gọi xong trước khi run() trả về.
        }
    }

    @Bean(destroyMethod = "shutdown")
    ExecutorService workerPool() {
        return Executors.newSingleThreadExecutor();
    }

    @Bean
    ApplicationRunner demonstrateCancellation(ExecutorService pool) {
        return args -> {
            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch finished = new CountDownLatch(1);

            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    while (!Thread.currentThread().isInterrupted()) {
                        Thread.sleep(60_000L);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                future.cancel(true);
                throw new IllegalStateException("Task did not start");
            }
            System.out.println("task-started");

            boolean accepted = future.cancel(true);
            System.out.println("cancel-requested=" + accepted);

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not stop");
            }
            System.out.println("task-stopped");
            System.out.println("future-cancelled=" + future.isCancelled());
        };
    }
}
```

### 7.4. Chạy

Trong thư mục chứa `pom.xml`:

```bash
mvn package
java -jar target/cancellable-worker-demo-0.0.1-SNAPSHOT.jar
```

Nếu đã tạo Maven Wrapper:

```bash
./mvnw package
```

Windows PowerShell khi có wrapper:

```powershell
.\mvnw.cmd package
```

Ví dụ cần JDK 17+, Maven và dependency Spring Boot trên classpath, không thể dùng `javac` thuần khi chưa cấu hình thư viện.

### 7.5. Output kỳ vọng

Những dòng do **code demo tự in** theo thứ tự:

```text
task-started
cancel-requested=true
task-stopped
future-cancelled=true
```

Log của Boot/build tool có thể xen giữa. Thứ tự này được bảo vệ bởi hai latch chứ không dựa vào việc ngủ đoán thời điểm worker đã bắt đầu.

Giải thích:

1. Task gọi `started.countDown()` khi bắt đầu. Caller đợi được latch rồi mới in `task-started`.
2. Task vẫn đang ở vòng `sleep`, nên caller có thể yêu cầu `future.cancel(true)` và nỗ lực interrupt worker.
3. Khi worker nhận ngắt trong `Thread.sleep`, nó ném `InterruptedException`; code khôi phục interrupted status và chạy `finally`.
4. `finished.countDown()` đánh dấu phần thân task đã đến điểm kết thúc được thiết kế. Caller đợi latch trước khi in `task-stopped`.
5. `future.isCancelled()` là trạng thái Future, không phải lý do duy nhất để tin task đã dừng.

Nếu worker không phản ứng với ngắt, caller hết hạn ở `finished.await(...)` và fail demo, thay vì tuyên bố thành công. Trong hệ thống thật phải ghi nhận job chưa dừng và có fallback.

### 7.6. Vai trò của Spring context

Bean `ExecutorService` do Spring sở hữu và có `destroyMethod="shutdown"` rõ ràng. Khi context đóng, executor không nhận thêm việc. Tuy nhiên, việc hủy **một job cụ thể** vẫn là trách nhiệm của component sở hữu `Future`.

Không nên tạo executor tự phát trong mỗi request rồi để nó sống mãi không đóng. Trong sản phẩm, dùng executor có lifecycle được quản lý, giới hạn số thread/queue và nơi lưu handle job để có thể cancel và cleanup.

## 8. Ứng dụng vào `ThreadPoolTaskExecutor`, `@Async` và scheduler

### 8.1. Managed `ThreadPoolTaskExecutor`

Spring Framework có `ThreadPoolTaskExecutor`. Một configuration minh họa:

```java
@Bean(name = "businessExecutor")
ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("business-");
    executor.setWaitForTasksToCompleteOnShutdown(false);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
```

Đây là đoạn method thuộc một class `@Configuration`; cần imports `@Bean` và `ThreadPoolTaskExecutor`. `setAwaitTerminationSeconds(10)` là ngân sách chờ trong shutdown, **không phải timeout mỗi task**. Chi tiết dừng task tùy lifecycle processor và chính sách executor, không bảo đảm mọi task được interrupt tức thì.

Spring Boot 3.3 có thể auto-configure executor thích hợp khi không có `Executor` bean khác. Ví dụ property cho auto-configured executor:

```properties
spring.task.execution.pool.core-size=2
spring.task.execution.pool.max-size=4
spring.task.execution.pool.queue-capacity=20
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
```

Những property tự động **không mặc nhiên áp dụng** cho mọi executor custom do ứng dụng tự tạo. Khi `await-termination=true`, tác vụ có thể được cho hoàn tất tự nhiên; chọn policy theo yêu cầu job drain, không chỉ vì tên property chứa chữ `await`.

### 8.2. `@Async` chưa chắc có đường hủy bạn cần

Để dùng `@Async`, ứng dụng phải bật async support (`@EnableAsync` ở config thích hợp) và method được gọi thông qua Spring proxy. Self-invocation trong cùng bean thường không đi qua proxy nên không tạo đường async như mong muốn.

Ví dụ minh họa:

```java
@Service
class ReportService {

    @Async("businessExecutor")
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture("done");
    }
}
```

Method cần import `@Service`, `@Async` và `CompletableFuture`; config cần executor tên `businessExecutor`. Đây là minh họa return type, không phải job nền chạy lâu.

Nếu caller nhận `CompletableFuture`, **đừng giả định `cancel(true)` sẽ interrupt worker**. Với job cần ngừng ở giữa, có thể chọn `ExecutorService.submit(...)`/`ThreadPoolTaskExecutor.submit(...)` để lấy `Future<?>` đúng hợp đồng, hoặc quản lý cancellation token/API hủy riêng.

### 8.3. `@Scheduled` cũng cần hợp tác

Một scheduled job có thể đã bắt đầu chạy trước shutdown. Scheduler ngừng trigger mới không đồng nghĩa phần thân job đang chạy đã dừng. Batch job dài cần kiểm tra interrupt/token, timeout I/O, checkpoint và xử lý replay.

Chính sách Spring Boot `spring.task.scheduling.*` khác `spring.task.execution.*`; chỉ chỉnh một nhóm property không chắc tác động nhóm kia.

### 8.4. `ApplicationRunner` và readiness

Runner chạy sau context refresh nhưng trước `ApplicationReadyEvent`. Nếu runner đợi task vô hạn, web server có thể đã bind cổng nhưng ứng dụng chưa ready. Với startup step bắt buộc, dùng deadline và propagate lỗi để Boot không tuyên bố ready sai.

Nếu runner chỉ submit một background task rồi trả về, Boot có thể công bố readiness chấp nhận traffic dù task đó chưa xong. Khi việc nền bắt buộc phải hoàn thành trước traffic, cần custom readiness indicator hoặc giữ bước đó trong runner đồng bộ.

### 8.5. `SmartLifecycle.stop(Runnable)` cần báo đúng lúc

Với service nền chạy suốt vòng đời, `SmartLifecycle` là một cách quản lý start/stop. `stop(Runnable callback)` phải:

1. Ngừng nhận task mới.
2. Yêu cầu drain hoặc cancel những task còn chạy.
3. Đợi completion trong budget.
4. Gọi `callback.run()` sau khi đã hoàn thành việc stop theo hợp đồng.

Không gọi callback ngay sau `Future.cancel(true)` nếu task vẫn có thể dùng datasource/transport. `spring.lifecycle.timeout-per-shutdown-phase` chỉ là ngân sách chờ theo phase, **không giết task không hợp tác**. Khi shutdown có dependency, worker cần dừng trước resource mà nó còn sử dụng.

## 9. Khi ứng dụng shutdown hoặc client hủy request

### 9.1. HTTP client disconnect không phải global interrupt

Người dùng đóng trình duyệt không bảo đảm một job đã được submit sang executor của server tự bị interrupt. Tùy Spring MVC/WebFlux, async request, reactive cancellation và client library, tín hiệu có thể hoặc không truyền đến công việc nền.

Với job dài, nên có job ID, registry trạng thái, API cancel có kiểm tra quyền và cleanup handle khi job kết thúc. Đừng tìm `Thread` theo tên rồi interrupt tùy tiện; đó không phải mô hình ownership an toàn.

### 9.2. Ngừng nhận việc mới trước khi hủy in-flight

Một workflow bền vững là chuyển instance sang trạng thái không nhận traffic mới, dừng consumer/scheduler mới, sau đó drain hoặc cancel việc đang chạy. Cuối cùng mới đóng connection pools và transports.

Trong Kubernetes, phải đo và cấu hình `terminationGracePeriodSeconds`, readiness/liveness, graceful shutdown và Spring lifecycle timeout tương thích. Nếu process bị kill cưỡng bức, Java callbacks không được bảo đảm chạy; message replay và idempotency vẫn cần thiết.

### 9.3. Không thể bảo đảm mọi công việc đã hoàn thành chỉ bằng interrupt

Nếu process chết đột ngột hoặc một native I/O call không trả về, không có cách nào bảo đảm transaction phân tán hoàn tất chỉ nhờ Java interrupt. Phải có durable state, retry/checkpoint, idempotency và chính sách phục hồi trên instance tiếp theo.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Bắt `InterruptedException` rồi bỏ qua | Mất tín hiệu hủy, tiếp tục công việc | Propagate hoặc restore + exit |
| Gọi `Thread.interrupted()` chỉ để kiểm tra | Vô tình xóa cờ ngắt | Dùng `isInterrupted()` |
| Gọi `interrupt()` rồi kết luận task đã dừng | Tác vụ có thể còn đang chạy | Đợi completion signal riêng |
| Task CPU không kiểm tra cờ | Cancel bị bỏ qua | Kiểm tra tại chunk boundary |
| I/O không có timeout | Shutdown có thể treo | Client timeout / request cancel |
| `Future.get(timeout)` timeout nhưng không cancel | Worker còn chạy nền | Quyết định cancel và xác nhận stop |
| `CompletableFuture.cancel(true)` được coi là thread interrupt | Công việc thực tế có thể tiếp tục | Token hoặc executor-owned Future |
| `shutdownNow()` được coi là kill cưỡng bức | Task vẫn giữ tài nguyên | `awaitTermination`, deadline, fallback |
| Runner chạy vòng vô hạn | Boot không đến `ApplicationReadyEvent` | Managed background lifecycle |
| `@Async` self-invocation | Method có thể chạy đồng bộ | Gọi qua Spring proxy hoặc dùng executor tường minh |
| Destroy datasource trước worker | Worker lỗi giữa flush/ack | Thứ tự lifecycle và graceful drain |
| Chỉ restore cờ nhưng lặp vô hạn | Busy loop, shutdown kẹt | Break/return/propagate |
| Hủy sau khi đã commit một phần | Retry có thể ghi trùng | Transaction boundary và idempotency |

### 10.1. Không dùng `Thread.stop()`

`Thread.stop()` có thể khiến thread dừng khi đang giữ lock hoặc đang cập nhật state, phá invariant của các object dùng chung. Nó đã bị deprecated vì không an toàn. Hãy dùng cooperative cancellation cùng deadline, timeout và lifecycle quản lý tài nguyên.

### 10.2. Tránh retry trên mọi exception

Interrupted/cancelled là một trạng thái điều khiển, không nên tự động bị xử lý như lỗi mạng transient rồi retry 10 lần. Nếu code cần retry một tác vụ mới sau restart, hãy làm theo chính sách durable state/idempotency ở tầng điều phối, không để worker đang bị hủy tự khởi động lại ngay trong `catch`.

### 10.3. Tác vụ bị cancel có thể vẫn phải cleanup

Cancellation latency là khoảng từ khi có yêu cầu đến khi công việc thực sự rời khỏi critical section. Nếu cleanup cần flush hoặc trả lock, hãy quan sát thời gian cleanup và giới hạn riêng; đừng đo latency chỉ đến lúc `future.isCancelled()` chuyển `true`.

## 11. Kiểm thử cancellation có ý nghĩa

Một test tốt phải xác nhận cả **yêu cầu hủy đã gửi** và **task đã kết thúc thật**.

### 11.1. Dùng latch thay cho `Thread.sleep` trong test điều phối

Test worker báo `started.countDown()` khi đã chạy, báo `finished.countDown()` trong `finally`. Test caller đợi started, gửi `future.cancel(true)`, đợi finished với timeout và kiểm tra cleanup. Cách này tránh race do giả định thread chắc đã bắt đầu sau 100 ms.

### 11.2. Test đường exception và khôi phục cờ

Với helper `throws InterruptedException`, test rằng caller nhận exception, không chạy business action tiếp theo. Với `Runnable` tự catch, test rằng task thoát, cleanup chạy, và không tự xử lý batch mới.

### 11.3. Test I/O không hợp tác

Stub một client giả lập blocking hoặc từ chối cancellation. Xác nhận deadline của caller không treo vô hạn, chính sách fail rõ và hệ thống không đóng tài nguyên đang còn dùng một cách vô ý. Đừng giả định mọi driver phản ứng như `Thread.sleep()`.

### 11.4. Integration test Spring context

Tạo context có worker/executor thật, nộp task rồi đóng context. Xác nhận thứ tự stop, không nhận job mới, thời gian chờ phù hợp, log task chưa hoàn tất, và không mất khả năng replay nếu shutdown bị force-kill.

## 12. Checklist thiết kế trước production

- [ ] Xác định **owner** của mỗi task và API được phép yêu cầu hủy.
- [ ] Giữ `Future`/cancellation token/job ID cho đến khi job kết thúc, xóa handle đúng lúc.
- [ ] Chia CPU loop thành các chunk để quan sát interrupt.
- [ ] Propagate `InterruptedException` khi có thể; tại boundary khác restore flag và thoát.
- [ ] Đặt connect/read/request timeouts và deadline tổng có giới hạn retry.
- [ ] Không nhầm `Future.cancel(true)` với xác nhận đã dừng.
- [ ] Không nhầm `CompletableFuture.cancel(true)` với interrupt worker.
- [ ] Dùng completion signal nếu shutdown phải chờ resource được giải phóng.
- [ ] Xử lý rollback/checkpoint/idempotency cho việc dở dang hoặc đã commit một phần.
- [ ] Ngừng nhận job mới trước khi drain/cancel in-flight tasks.
- [ ] Giữ dependency sống cho đến khi worker ngừng dùng.
- [ ] Kiểm thử các kịch bản timeout, interrupt, cancel race và process bị kill.
- [ ] Theo dõi số job bị hủy, cancellation latency, timeout và worker không dừng đúng hạn.

## 13. Nguồn tham khảo chính thức

- [Java 17 `Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `isInterrupted`, `Thread.interrupted`, interruption khi blocking.
- [Java 17 `Future` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `get`, trạng thái cancellation.
- [Java 17 `CompletableFuture` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `cancel(boolean)` không dùng interrupt điều khiển processing.
- [Java 17 `ExecutorService` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): cấu hình task executors và schedulers.
- [Spring Framework 6.1 — `ThreadPoolTaskExecutor`](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): quản lý thread pool và shutdown.
- [Spring Framework — `SmartLifecycle`](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/SmartLifecycle.html): stop callback và lifecycle phases.

## 14. Ghi nhớ

**Interrupt là tín hiệu yêu cầu hợp tác, không phải nút giết thread.** Task phải kiểm tra cờ, propagate `InterruptedException` hoặc restore flag và thoát ở boundary thích hợp.

`Future.cancel(true)` là nỗ lực interrupt, chưa bảo đảm worker đã dừng. Với `CompletableFuture`, tham số `true` không có tác dụng interrupt underlying work. `Future.get(timeout)` chỉ giới hạn thời gian chờ, và `shutdownNow()` cũng chỉ là nỗ lực hủy.

Một tác vụ có thể hủy đúng nghĩa cần cả **cancellation signal**, **deadline/I/O timeouts**, **completion acknowledgement**, **cleanup đúng thứ tự** và **trạng thái bền vững để retry an toàn**. Trong Spring Boot, hãy gắn các yêu cầu đó với ownership của executor, readiness và lifecycle khi shutdown thay vì chỉ thêm một lời gọi `interrupt()`.