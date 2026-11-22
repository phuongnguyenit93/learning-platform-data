# Không bỏ qua Future rồi đánh mất lỗi nghiệp vụ

## 1. Vấn đề: tác vụ thất bại nhưng hệ thống không biết

Một API Spring nhận yêu cầu tạo hóa đơn, gửi tác vụ sang executor và nhận một `Future` hoặc `CompletableFuture`. Sau đó code bỏ qua handle được trả về:

~~~java
// Anti-pattern: snippet trong service, không phải class độc lập.
invoiceWorker.generateInvoice(invoiceId); // CompletableFuture<Invoice>
return "Đã tiếp nhận";
~~~

Nếu worker ném `IllegalStateException` do hóa đơn không hợp lệ, lỗi **có thể được lưu trong Future** thay vì truyền tới luồng HTTP. Không gọi `get()/join()`, không gắn completion handler, không ghi trạng thái job và không có cơ chế giám sát khác thì tầng nghiệp vụ có thể mãi nghĩ việc đã thành công. Ngay cả khi Future đã `isDone() == true`, trạng thái ấy **không đồng nghĩa thành công**.

Các hệ quả thường gặp:

- Client nhận phản hồi “đã xử lý” nhưng không có hóa đơn; không thấy mã lỗi nghiệp vụ tương ứng.
- `ExecutorService.submit` bắt exception của `Callable` bên trong `FutureTask`, nên có thể **không xuất hiện stack trace từ thread uncaught-exception handler**.
- `CompletableFuture.supplyAsync` hoàn tất exceptionally nhưng không tự ép ứng dụng quan sát; chuỗi `thenApply` chỉ chạy khi thành công, còn các stage lỗi bị bỏ qua.
- `@Async` trả `Future/CompletableFuture` cho phép truyền lỗi cho caller qua kết quả, nhưng **caller phải sử dụng hoặc chuyển tiếp handle**.
- Lỗi từ một job quan trọng biến thành “silent failure”, ảnh hưởng tiền, tồn kho, email, audit và tính nhất quán.

**Quy tắc:** bất cứ khi nào code **gửi việc và nhận Future**, phải chỉ rõ **ai sở hữu Future, ai quan sát terminal state, ai ghi nhận lỗi nghiệp vụ, và ai thông báo hoặc retry**. Không nhất thiết phải block với `get()`; có thể gắn `whenComplete`, trả lại Future cho caller hoặc ghi trạng thái job ở cơ chế bền vững.

## 2. Future thực chất là gì?

### 2.1. execute, submit, CompletableFuture và @Async

| API | Người gọi nhận gì? | Lỗi trong task được xử lý theo đường nào? |
| --- | --- | --- |
| `Executor.execute(Runnable)` | `void` | Unchecked exception có thể thoát khỏi `run()` và được executor/thread uncaught handler xử lý; còn tùy implementation |
| `ExecutorService.submit(Callable<T>)` | `Future<T>` | Exception được lưu trong Future; `get()` ném `ExecutionException` có `getCause()` |
| `CompletableFuture.supplyAsync(supplier, executor)` | `CompletableFuture<T>` | Stage hoàn tất exceptionally; `join()` thường ném `CompletionException`, `get()` ném `ExecutionException` |
| `@Async` trả `CompletableFuture<T>` | Future proxy trả lại | Exception từ method có thể được quan sát trong Future; phải truyền/gắn handler |
| `@Async` trả `void` | Không có Future | Dùng `AsyncUncaughtExceptionHandler`/log/metrics do caller không nhận exception dưới dạng Future |
| Executor từ chối task khi submit | Có thể **không trả Future** | `RejectedExecutionException` (JDK) hoặc `TaskRejectedException` (Spring), tùy adapter/chính sách |

`Future` và `CompletableFuture` biểu diễn kết quả **sau này**, không phải bằng chứng nhiệm vụ thành công. Khi một task bị từ chối, hủy, mất khỏi queue hoặc kẹt I/O, đường xử lý cũng khác nhau. Thiết kế phải tính cả **submission failure** và **execution failure**, chứ không chỉ bắt exception trong method nghiệp vụ.

### 2.2. Một Future đã hoàn tất chưa chắc thành công

| Trạng thái | `Future.isDone()` | `get()` | Có cần xử lý? |
| --- | --- | --- | --- |
| Đang xếp hàng/chạy | `false` | Có thể chờ | Deadline, timeout, queue health |
| Thành công | `true` | Trả kết quả | Cập nhật `SUCCEEDED` |
| Ném lỗi nghiệp vụ | `true` | `ExecutionException` | Ghi `FAILED`, phân loại lỗi, retry khi phù hợp |
| Bị hủy | `true` | `CancellationException` | Ghi `CANCELLED` |
| Bị discard im lặng trước khi chạy | Có thể giữ `false` mãi | Có thể chờ vô hạn | Rejection minh bạch, giới hạn thời gian, reconciliation |

`CompletableFuture.isCompletedExceptionally()` trả `true` khi kết quả hoàn tất exceptional, gồm các trường hợp như cancellation. `Future.isDone()` không kể cho ta biết nguyên nhân, và chỉ gọi `isDone()` cũng không làm lỗi tự được ghi log.

## 3. Tại sao submit() có thể che lỗi?

Java `ExecutorService.submit(Callable<T>)` thường bọc task trong `RunnableFuture/FutureTask`. `FutureTask` bắt exception từ `Callable.call()` và ghi vào trạng thái Future. Một worker thread có thể xử lý task tiếp theo mà không in trực tiếp exception của task trước ra stderr. Nếu caller chỉ giữ hoặc bỏ qua reference `Future`, lỗi nghiệp vụ nằm đó mà không ai xử lý.

~~~java
// Snippet, giả sử executor là ExecutorService đang hoạt động.
Future<String> result = executor.submit(() -> {
    throw new IllegalArgumentException("invalid invoice");
});

// Không được bỏ result nếu nghiệp vụ yêu cầu hoàn tất.
// Không đồng nghĩa task thành công chỉ vì submit() trả về bình thường.
~~~

Cách quan sát đồng bộ có giới hạn:

~~~java
// Snippet tại ranh giới cần nhận kết quả (không phải chương trình độc lập).
try {
    String path = result.get(3, TimeUnit.SECONDS);
    markSucceeded(path);
} catch (ExecutionException ex) {
    Throwable businessCause = ex.getCause();
    markFailed(businessCause);
} catch (TimeoutException ex) {
    markTimedOut(ex);
    // Quyết định thêm việc cancel/retry theo contract nghiệp vụ.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    markInterrupted(ex);
} catch (CancellationException ex) {
    markCancelled(ex);
}
~~~

`markSucceeded`/`markFailed`/`markTimedOut`/`markInterrupted`/`markCancelled` là các thao tác ứng dụng giả định. Cần import `java.util.concurrent.*`. `get(timeout)` chỉ giới hạn thời gian **caller chờ**; nó không tự cancel task và không biến Future chưa hoàn tất thành trạng thái terminal.

Một HTTP controller cần trả nhanh **không nên** gọi `get()` ngay sau submit rồi tự gọi đó là xử lý nền. Thay vào đó, trả một API asynchronous response phù hợp hoặc trả `202 Accepted` kèm job ID **sau khi thật sự nhận/lưu yêu cầu**, rồi cung cấp endpoint tra trạng thái.

## 4. Java 17: ví dụ độc lập minh họa lỗi bị giữ trong Future

Ví dụ hoàn chỉnh dưới đây không phụ thuộc race/thread scheduling để xác nhận kết quả: executor **một worker** chạy task lỗi, sau đó chạy task đánh dấu. `marker.get(...)` bảo đảm task lỗi đã kết thúc trước khi kiểm tra. Phần `CompletableFuture` dùng `failedFuture` và `whenComplete` để minh họa cách quan sát và cách *vô tình nuốt lỗi*.

Lưu đúng tên **`FutureFailureDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class FutureFailureDemo {
    static final class BusinessException extends RuntimeException {
        BusinessException(String message) {
            super(message);
        }
    }

    static Throwable unwrap(Throwable error) {
        while ((error instanceof ExecutionException
                || error instanceof CompletionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            // Worker giữ BusinessException trong FutureTask.
            Future<String> failedSubmit = executor.submit(() -> {
                throw new BusinessException("invalid invoice");
            });

            // Worker đơn luồng xử lý marker sau failedSubmit.
            Future<String> marker = executor.submit(() -> "marker");
            System.out.println("MARKER=" + marker.get(3, TimeUnit.SECONDS));
            System.out.println("SUBMIT_DONE=" + failedSubmit.isDone());

            try {
                failedSubmit.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("SUBMIT_CAUSE="
                        + unwrap(ex).getClass().getSimpleName());
            }

            CompletableFuture<String> failed =
                    CompletableFuture.failedFuture(
                            new BusinessException("stock mismatch"));

            AtomicInteger observedCount = new AtomicInteger();
            CompletableFuture<String> observed =
                    failed.whenComplete((value, error) -> {
                        if (error != null) {
                            observedCount.incrementAndGet();
                        }
                    });

            try {
                observed.join();
            } catch (CompletionException ex) {
                System.out.println("OBSERVED_CAUSE="
                        + unwrap(ex).getClass().getSimpleName());
            }
            System.out.println("OBSERVATIONS=" + observedCount.get());

            // Fallback làm stage MỚI thành công; lỗi gốc vẫn còn.
            CompletableFuture<String> fallback =
                    failed.exceptionally(ex -> "DEFAULT");
            System.out.println("FALLBACK=" + fallback.join());

            String handled = failed.handle((value, error) ->
                    error == null ? value
                            : "FAILED:" + unwrap(error).getMessage()).join();
            System.out.println("HANDLED=" + handled);
            System.out.println("ORIGINAL_EXCEPTIONAL="
                    + failed.isCompletedExceptionally());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 FutureFailureDemo.java
java FutureFailureDemo
~~~

Stdout **do chương trình in**, theo đúng thứ tự:

~~~text
MARKER=marker
SUBMIT_DONE=true
SUBMIT_CAUSE=BusinessException
OBSERVED_CAUSE=BusinessException
OBSERVATIONS=1
FALLBACK=DEFAULT
HANDLED=FAILED:stock mismatch
ORIGINAL_EXCEPTIONAL=true
~~~

**Giải thích:** task lỗi đã kết thúc khi marker được xử lý xong trên cùng executor đơn luồng. `SUBMIT_DONE=true` không biểu thị thành công; chỉ khi gọi `failedSubmit.get` mới thấy nguyên nhân `BusinessException`. Với `CompletableFuture.failedFuture`, `whenComplete` tăng biến đếm nhưng **không chữa lỗi**; `observed.join()` vẫn ném `CompletionException`. Ngược lại, `exceptionally` chuyển lỗi thành chuỗi fallback `DEFAULT` trong **stage mới**. Vì `failed` gốc vẫn exceptional, `ORIGINAL_EXCEPTIONAL=true`.

Ví dụ dùng giá trị xác định, không gọi mạng, không cần Spring, không cần `Thread.sleep` và không dựa vào thứ tự ngẫu nhiên giữa nhiều worker. Nó chỉ giải thích semantics; trong sản xuất phải thay `System.out` bằng logger/metrics và cập nhật trạng thái job.

## 5. Các công cụ của CompletableFuture: chọn đúng để không đánh mất lỗi

### 5.1. whenComplete: quan sát và chuyển tiếp trạng thái

~~~java
// Snippet, future có kiểu CompletableFuture<Invoice>.
CompletableFuture<Invoice> observed =
        future.whenComplete((invoice, error) -> {
            if (error != null) {
                log.error("invoice failed, invoiceId={}", invoiceId, error);
            }
        });
return observed;
~~~

`log`/`invoiceId` và kiểu `Invoice` thuộc service ứng dụng. `whenComplete` chạy cho cả thành công và lỗi, thích hợp cho structured logging, metric hoặc audit nhẹ. **Nó trả một Future mới mang cùng trạng thái/kết quả theo mặc định**, không biến lỗi thành thành công. Nếu callback tự ném lỗi trong khi upstream thành công, stage trả về cũng có thể lỗi; nếu upstream vốn lỗi, nguyên nhân của upstream được ưu tiên theo hợp đồng `CompletionStage`.

**Không gắn callback rồi bỏ luôn đường giám sát còn lại** nếu log cũng có thể thất bại. Với nghiệp vụ quan trọng, vẫn cần DB job status / outbox, retry và reconciliation. Ngoài ra `whenComplete` không tạo worker riêng: callback có thể chạy trên thread vừa hoàn tất stage hoặc trên caller khi stage đã xong. Giữ callback gọn và tránh I/O/blocking lâu trong completion thread.

### 5.2. handle: đổi cả thành công lẫn thất bại thành giá trị mới

~~~java
// Snippet trong service, kiểu Outcome do ứng dụng định nghĩa.
record Outcome<T>(String status, T value, String errorCode) { }

CompletableFuture<Outcome<Invoice>> outcome = future.handle(
        (value, error) -> error == null
                ? new Outcome<>("SUCCEEDED", value, null)
                : new Outcome<>("FAILED", null, mapErrorCode(error)));
~~~

`mapErrorCode` là method nghiệp vụ, snippet không độc lập. Vì `handle` trả giá trị mới, stage `outcome` có thể **hoàn tất bình thường ngay cả khi upstream lỗi**. Đây là cách đúng nếu contract của API là trả kết quả có trạng thái rõ ràng. Nhưng nếu chỉ `return null` hoặc trả đối tượng “success” mặc định khi có lỗi, bạn đang **che lỗi nghiệp vụ**.

### 5.3. exceptionally: phục hồi có chủ đích, không nuốt mọi lỗi

~~~java
// Snippet: chỉ cho phép fallback khi lỗi phụ trợ thật sự không quan trọng.
CompletableFuture<Recommendation> recommendations =
        remoteSuggestions.exceptionally(error -> {
            log.warn("recommendation service unavailable", error);
            return Recommendation.empty();
        });
~~~

Nếu gợi ý sản phẩm là tính năng phụ và API có fallback hợp lệ, hành vi trên có thể phù hợp. Nhưng nếu `remoteSuggestions` đang tính thuế, tồn kho, thanh toán hoặc trạng thái đơn hàng, trả `Recommendation.empty()` theo cách tương tự có thể che mất dữ liệu bắt buộc.

Đặc biệt không dùng một `exceptionally(ex -> null)` bao trùm mọi công việc quan trọng rồi quên gắn error status. `exceptionally` tạo một stage mới **thành công** nếu handler trả giá trị bình thường; caller phía sau không còn biết có lỗi nếu không lưu nguyên nhân trong kết quả hoặc metric.

### 5.4. thenApply và thenAccept không nhận nhánh lỗi

~~~java
// Sai khi dùng như cơ chế xử lý mọi lỗi:
future.thenAccept(value -> log.info("done: {}", value));
~~~

`thenAccept` chỉ chạy khi upstream thành công. Nếu upstream exceptional, callback thành công không chạy; **stage trả về vẫn exceptional**. Nếu không giữ stage đó và không có observer khác, lỗi vẫn có thể bị bỏ quên.

Đúng hơn:

~~~java
// Snippet minh họa: theo dõi cả hai kết quả.
CompletableFuture<Void> tracked = future.whenComplete(
        (value, error) -> {
            if (error != null) {
                log.error("failed", error);
            } else {
                log.info("done: {}", value);
            }
        }).thenApply(ignored -> null);
~~~

Ở đây `tracked` được giữ hoặc trả cho caller; ví dụ `thenApply(ignored -> null)` đổi kiểu giá trị trả thành `Void` sau thành công. Nếu upstream lỗi thì nhánh `thenApply` không chạy và stage vẫn thất bại. Khi chỉ cần quan sát, không bắt buộc biến đổi thành Void; thường đủ `return future.whenComplete(...)`.

### 5.5. get() và join() khác nhau ở kiểu exception

| API | Lỗi trong task | Interrupted/cancellation |
| --- | --- | --- |
| `Future.get()` | `ExecutionException`, lấy `getCause()` | `InterruptedException` hoặc `CancellationException` |
| `Future.get(timeout, unit)` | Như trên, có thêm `TimeoutException` khi quá hạn chờ | Hạn chờ không tự hủy task |
| `CompletableFuture.join()` | Thường `CompletionException` với cause gốc | Không ném checked `InterruptedException`; cancellation có thể ném `CancellationException` |
| `CompletableFuture.get()` | `ExecutionException` | Cũng là `Future` nên có checked interruption/timeout variant |

Tại ranh giới API và logging, thường nên **unwrap `ExecutionException`/`CompletionException`** rồi phân loại cause gốc, giữ stack trace và context. Không gói mọi lỗi thành `RuntimeException("failed")` mà không truyền cause; làm như vậy mất thông tin chẩn đoán.

## 6. Spring @Async: trả Future để lỗi có đường truyền về

### 6.1. Lỗi nghiệp vụ xảy ra sau khi dispatch

Một Spring-managed bean:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InvoiceWorker {
    @Async("invoiceExecutor")
    public CompletableFuture<String> generate(String id) {
        if ("BAD".equals(id)) {
            throw new IllegalArgumentException("invoice rejected");
        }
        return CompletableFuture.completedFuture("invoice/" + id);
    }
}
~~~

Khi được gọi từ **bean khác qua Spring proxy** và `@EnableAsync` đã bật, method chạy trên executor mang tên `invoiceExecutor`. Với return type `CompletableFuture`, exception của target được biểu diễn bằng exceptional completion, để caller có thể `whenComplete` hoặc `get()`. Đừng tự gọi `this.generate(...)` từ cùng class rồi mong interceptor được kích hoạt.

Nếu đổi signature thành `@Async public void generate(...)`, caller không có Future để truyền thất bại. Khi đó lỗi sẽ đi qua `AsyncUncaughtExceptionHandler` (mặc định Spring chủ yếu log), và phải có kênh quan sát riêng nếu công việc có ảnh hưởng nghiệp vụ.

### 6.2. Ví dụ Spring Boot 3.3.5 chạy được

Ví dụ Java 17 + Maven sau có một công việc thành công và một công việc ném lỗi. `ApplicationRunner` **cố ý chờ có hạn** để in một kết quả ổn định; trong HTTP API sản xuất, nên trả Future, callback hoặc job ID thay vì block request tương tự.

Cấu trúc:

~~~text
spring-observed-future/
├── pom.xml
└── src/main/java/com/example/failure/
    ├── AsyncFailureApplication.java
    └── InvoiceWorker.java
~~~

`pom.xml`:

~~~xml
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
    <artifactId>spring-observed-future</artifactId>
    <version>1.0.0</version>
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
~~~

`src/main/java/com/example/failure/AsyncFailureApplication.java`:

~~~java
package com.example.failure;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class AsyncFailureApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(AsyncFailureApplication.class, args)) {
            // Demo kết thúc sau khi ApplicationRunner đã kiểm tra Future.
        }
    }

    @Bean("invoiceExecutor")
    ThreadPoolTaskExecutor invoiceExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("invoice-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner verify(InvoiceWorker worker) {
        return args -> {
            CompletableFuture<String> ok = worker.generate("A-1");
            CompletableFuture<String> failed = worker.generate("BAD");

            AtomicInteger errorCount = new AtomicInteger();
            CompletableFuture<String> observed =
                    failed.whenComplete((value, error) -> {
                        if (error != null) {
                            errorCount.incrementAndGet();
                        }
                    });

            // Chuyển lỗi thành trạng thái HIỂN THỊ có chủ đích cho demo.
            CompletableFuture<String> report = observed.handle(
                    (value, error) -> error == null
                            ? "OK"
                            : "FAILED:" + root(error).getClass().getSimpleName());

            String success = ok.get(5, TimeUnit.SECONDS);
            String failureStatus = report.get(5, TimeUnit.SECONDS);

            System.out.println("SUCCESS=" + success);
            System.out.println("FAILURE_STATUS=" + failureStatus);
            System.out.println("ERROR_OBSERVATIONS=" + errorCount.get());
            System.out.println("ORIGINAL_FAILED="
                    + failed.isCompletedExceptionally());
        };
    }

    private static Throwable root(Throwable error) {
        while ((error instanceof CompletionException
                || error instanceof ExecutionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

`src/main/java/com/example/failure/InvoiceWorker.java`:

~~~java
package com.example.failure;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InvoiceWorker {
    @Async("invoiceExecutor")
    public CompletableFuture<String> generate(String id) {
        if ("BAD".equals(id)) {
            throw new IllegalArgumentException("invoice rejected");
        }
        return CompletableFuture.completedFuture("invoice/" + id);
    }
}
~~~

Chạy:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua startup/shutdown log, bốn dòng in từ `ApplicationRunner` có nội dung:

~~~text
SUCCESS=invoice/A-1
FAILURE_STATUS=FAILED:IllegalArgumentException
ERROR_OBSERVATIONS=1
ORIGINAL_FAILED=true
~~~

**Vì sao ổn định?** Mọi biến được đọc **sau** `report.get(5, SECONDS)`; `report` chỉ hoàn tất sau khi `whenComplete` tăng counter và `handle` tạo trạng thái cho lỗi. Tên luồng, thứ tự hai worker hoàn tất và log startup không ảnh hưởng bốn giá trị này. Lỗi nghiệp vụ vẫn còn ở `failed` gốc, trong khi `report` là biểu diễn có chủ đích cho demo.

Khi chuyển sang production, thay `errorCount` bằng structured logging, metrics và trạng thái job; không in stack trace nhạy cảm hoặc mã đơn hàng đầy đủ vào log không được kiểm soát. Demo không chạy network, DB hoặc transaction, nên chưa có các bảo đảm bền vững.

## 7. @Async void: không có Future thì ai tiếp nhận lỗi?

Với method `void`:

~~~java
// Snippet trong Spring-managed bean.
@Async("invoiceExecutor")
public void sendReceipt(String invoiceId) {
    throw new IllegalStateException("mail gateway failed");
}
~~~

Caller không nhận được Future, do đó không thể dùng `get()`. Theo Spring, lỗi chưa bắt được chuyển đến `AsyncUncaughtExceptionHandler`. Có thể cấu hình handler:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, parameters) -> {
            System.err.println("ASYNC_VOID_ERROR method="
                    + method.getName()
                    + ", cause=" + error.getClass().getSimpleName());
        };
    }
}
~~~

Đây là class cấu hình Spring đầy đủ, nhưng cần nằm trong một ứng dụng/context có bean async và executor tương ứng; không phải chương trình `main` độc lập. `System.err` dùng để minh họa, không phải hệ thống observability production. `@EnableAsync` chỉ cần được bật đúng context; nếu đã có cấu hình tương ứng thì không cần khai báo trùng.

**Hạn chế:** handler có thể log/metric và mở quy trình xử lý khác, nhưng **không trả kết quả trực tiếp tới caller**. Với nghiệp vụ phải bảo đảm hoàn tất hoặc retry, thường nên dùng `CompletableFuture<T>` (hoặc hàng đợi bền vững), vì có thể kết hợp phản hồi, timeout và truyền exception. Đừng cho rằng cấu hình handler là đủ để đảm bảo email/audit/thanh toán được thực hiện chính xác.

## 8. Khi trả Future cho caller: ai chịu trách nhiệm quan sát?

Một anti-pattern trong controller:

~~~java
// Snippet trong @RestController; không độc lập.
@PostMapping("/invoices/{id}/generate")
public ResponseEntity<Void> generate(@PathVariable String id) {
    worker.generate(id); // Bỏ mất Future.
    return ResponseEntity.accepted().build();
}
~~~

Phản hồi `202 Accepted` có thể phù hợp nếu hệ thống **thật sự đã tiếp nhận** yêu cầu để xử lý sau, có cách tra trạng thái và xử lý rejection. Nhưng nếu chỉ gửi lên một in-memory pool không có job ledger, khi task thất bại hoặc ứng dụng restart, caller không thể biết chuyện gì xảy ra. Ngoài ra `worker.generate` có thể ném `TaskRejectedException` **ngay lúc submit** nếu pool đầy; phải chuyển trường hợp này thành phản hồi có ý nghĩa thay vì trả 202 sai.

### 8.1. Contract chờ kết quả: trả CompletableFuture lên tầng biết xử lý

~~~java
// Snippet trong Spring service/gateway.
public CompletableFuture<Invoice> generate(String id) {
    return worker.generateInvoice(id)
            .whenComplete((value, error) -> {
                if (error != null) {
                    log.error("Invoice processing failed, id={}", id, error);
                }
            });
}
~~~

Ở đây `worker`, `Invoice` và `log` là thành phần do ứng dụng cung cấp. Người gọi phải tiếp tục trả Future (cho MVC async response nếu phù hợp) hoặc gắn terminal handler. Không phải cách đúng nếu gateway tự gọi xong rồi **bỏ cả Future lẫn việc ghi trạng thái**. Một completion callback có thể log lỗi nhưng không tự bảo đảm task tồn tại sau khi ứng dụng restart.

### 8.2. Contract job nền: ghi trạng thái bền vững

Thay vì coi Future trong RAM là job ledger, dùng một bảng trạng thái trong DB, ví dụ:

~~~text
PENDING -> RUNNING -> SUCCEEDED
                  \-> FAILED
          \-> REJECTED
          \-> TIMED_OUT / CANCELLED (theo quy tắc hệ thống)
~~~

Một quy trình đáng tin cậy hơn:

1. Nhận request với **idempotency key** và tạo bản ghi job `PENDING` trong transaction.
2. Ghi/dispatch công việc bằng cơ chế có thể phục hồi (outbox/message broker hoặc dispatcher đáng tin cậy). Chỉ phản hồi đã chấp nhận khi điều kiện tiếp nhận của API thật sự thỏa.
3. Worker claim job và chuyển `RUNNING`, thực thi với timeout I/O và kiểm tra điều kiện hủy.
4. Khi thành công, ghi `SUCCEEDED` và kết quả; khi lỗi, lưu `FAILED` cùng error code/trạng thái retry, không chỉ log stack trace.
5. Sau restart, reconciliation tìm job `PENDING/RUNNING` quá hạn và quyết định retry/compensation, đồng thời đảm bảo idempotency của side effects.

Trên nhiều pod, một `CompletableFuture` ở JVM của pod A không truy cập được từ pod B; DB/job store cần là nguồn dữ liệu chia sẻ. Không coi ghi trạng thái DB và side effect bên ngoài là một transaction nguyên tử nếu thực tế chúng không cùng transaction; dùng outbox và idempotency khi cần.

## 9. Xử lý submission rejection, timeout và cancellation

### 9.1. Hai thời điểm lỗi khác nhau

**Submission failure:** ngay khi gọi `executor.execute/submit` hoặc lời gọi `@Async` qua proxy, executor có thể từ chối vì shutdown/queue đầy, ném `RejectedExecutionException` (JDK) hoặc `TaskRejectedException` (Spring). Nếu call chưa trả Future, không có handle để gắn `whenComplete`.

~~~java
// Snippet minh họa tại nơi dispatch Spring @Async.
try {
    CompletableFuture<String> future = worker.generate("A-1");
    return future.whenComplete((value, error) -> recordOutcome(value, error));
} catch (org.springframework.core.task.TaskRejectedException ex) {
    recordRejected(ex);
    throw ex;
}
~~~

`recordOutcome`/`recordRejected` là phương thức nghiệp vụ giả định. Với API, có thể map sang `503 Service Unavailable` hoặc `429 Too Many Requests` theo contract. Nếu dùng `DiscardPolicy` hoặc `DiscardOldestPolicy` im lặng, `Future` có thể pending mãi mà không có lỗi hiển thị; ưu tiên policy ném lỗi và theo dõi saturation.

**Execution failure:** job đã được nhận và chạy, nhưng thao tác thực tế ném exception; Future hoàn tất exceptional, hãy dùng observer hoặc kết quả trả lên caller. Hai đường lỗi cần test riêng.

### 9.2. Timeout không đồng nghĩa task đã dừng

~~~java
// Snippet trên một CompletableFuture do ứng dụng sở hữu.
CompletableFuture<String> bounded =
        worker.generate("A-1").orTimeout(10, TimeUnit.SECONDS);
~~~

`orTimeout` (Java 9+) sẽ làm CompletableFuture đó hoàn tất exceptionally với `TimeoutException` nếu chưa hoàn tất sau hạn, nhưng **không tự interrupt hoặc dừng worker**, không tự rollback DB và không tự xóa task đã xếp hàng. Nó trả **chính Future đang gọi**, ảnh hưởng cả các tham chiếu khác tới cùng object. Nếu cần một timeout chỉ ở lớp quan sát mà không muốn mutate upstream Future, hãy tạo stage riêng hoặc wrapper phù hợp rồi quản lý timeout của riêng stage.

Tương tự, `future.get(10, SECONDS)` chỉ kết thúc thời gian **caller đợi**; nó không tự hoàn tất hoặc hủy Future.

`future.cancel(true)` là một yêu cầu hủy, không bảo đảm dừng tác vụ phớt lờ interrupt. Với `CompletableFuture`, cancellation là một dạng exceptional completion; tham số `mayInterruptIfRunning` không trực tiếp điều khiển interrupt job upstream theo cách `FutureTask` có thể làm.

Nếu HTTP client đã timeout nhưng worker còn ghi hóa đơn, request retry có thể tạo hóa đơn hai lần. Cần idempotency, transaction boundary thích hợp, deadline truyền xuống I/O, và trạng thái job để ghi nhận kết quả muộn.

## 10. Không để exception handler vô tình phá mất tín hiệu lỗi

### 10.1. Rất nhiều code “bắt lỗi” nhưng lại trả success

~~~java
// Anti-pattern: biến mọi lỗi thành kết quả rỗng không phân biệt.
CompletableFuture<List<Invoice>> maybe =
        invoiceFuture.exceptionally(error -> List.of());
~~~

Nếu `List.of()` ở đây được API giải thích là “không có hóa đơn” thì đang đánh đồng *lỗi hệ thống* với *không có dữ liệu*. Chỉ dùng fallback khi nghiệp vụ định nghĩa rõ đó là phản hồi hợp lệ và ghi nhận trạng thái degraded.

Một mẫu có trạng thái rõ hơn:

~~~java
// Snippet với record và nghiệp vụ trong service.
record JobResult<T>(String status, T value, String errorCode) { }

CompletableFuture<JobResult<Invoice>> visible = invoiceFuture.handle(
        (value, error) -> {
            if (error == null) {
                return new JobResult<>("SUCCEEDED", value, null);
            }
            return new JobResult<>("FAILED", null, classify(error));
        });
~~~

`classify` do ứng dụng định nghĩa; cần phân loại giữa lỗi business không nên retry và lỗi hạ tầng có thể retry. Tránh gửi stack trace, SQL query hay thông tin nhạy cảm cho client; lưu logs riêng và expose error code tối thiểu.

### 10.2. Unwrap exception nhưng vẫn giữ nguyên nhân gốc

Các stage có thể thêm `CompletionException` hoặc `ExecutionException`. Khi ghi log/metric:

~~~java
// Snippet helper, thích hợp đặt trong class utility.
static Throwable rootCause(Throwable error) {
    while ((error instanceof CompletionException
            || error instanceof ExecutionException)
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
~~~

Helper này chỉ gỡ **wrapper của concurrency API**, không nhất thiết đi xuyên mọi `cause` nghiệp vụ. Ví dụ một `BusinessRuleException` có một `SQLException` làm cause thì **mã lỗi nghiệp vụ** có thể phải giữ `BusinessRuleException` làm root để phân loại, đồng thời log cả stack trace. Không tùy tiện lấy deepest cause và làm mất ngữ nghĩa nghiệp vụ.

### 10.3. Callback thất bại cũng cần được theo dõi

`future.whenComplete(...)` trả **một stage mới**. Nếu callback ghi DB/log ném exception, stage mới có thể exceptional; nếu chỉ quan sát stage gốc, có thể bỏ sót lỗi của chính observer. Vì vậy:

- Giữ/trả stage từ `whenComplete` nếu callback là một phần bắt buộc của luồng nghiệp vụ.
- Tránh làm blocking I/O nặng trong completion callback; nếu cần write bền vững, thiết kế bước riêng với retry.
- Dùng metric cảnh báo observer/persistence failures và reconciler đối chiếu job ledger.
- `thenApplyAsync`/`whenCompleteAsync` có thể cần executor riêng; nếu executor ấy quá tải, stage tiếp nối cũng có thể lỗi hoặc bị treo tùy rejection policy.

### 10.4. CompletableFuture.allOf() có thể che lỗi thành phần

~~~java
// Snippet: không giả định việc tạo barrier là thu được giá trị.
CompletableFuture<Void> all =
        CompletableFuture.allOf(priceFuture, stockFuture, taxFuture);
~~~

`allOf` hoàn tất khi **tất cả** các Future con hoàn tất; nếu có lỗi, barrier cũng exceptional. Nếu không ai xử lý `all` hoặc Future con, kết quả tổng hợp vẫn có thể bị bỏ quên. Khi cần quan sát từng nguồn, gắn `whenComplete`/`handle` cho **từng Future con** trước khi tạo barrier, rồi tùy contract chọn fail toàn bộ hay trả báo cáo partial failure có trạng thái rõ. `allOf` không tự lưu danh sách các kết quả hoặc mọi exception.

## 11. Transaction, logging và điều kiện “nghiệp vụ đã thành công”

- **Transaction:** `@Transactional` của HTTP thread không tự chạy theo worker thread. Đặt transaction ở đường xử lý của worker/service được Spring proxy quản lý. Nếu worker bắt exception rồi trả `completedFuture("OK")`, transaction có thể không rollback theo kỳ vọng; quản lý rollback/exception propagation theo quy tắc nghiệp vụ.
- **Log:** đưa job ID, trace ID, source, error code và stack trace vào structured logs; tránh chỉ in “task failed” không có định danh. Thread-local MDC/security không tự truyền qua thread khác nếu không cấu hình propagation.
- **Metric:** theo dõi `submitted`, `running`, `succeeded`, `failed`, `rejected`, `timed_out`, `cancelled` và `pending_over_deadline`; số job hoàn tất thành công không nói được có bao nhiêu job thất bại bị bỏ quên.
- **Alert:** báo động khi job chạy quá deadline, tỷ lệ business failure tăng hoặc hàng đợi bão hòa. Với tác vụ bắt buộc, log lỗi chưa chắc đủ; phải có người/cơ chế tiếp nhận và hành động.
- **Retry:** chỉ retry các lỗi phù hợp (ví dụ HTTP 503 tạm thời), giới hạn số lần và backoff. Business validation 4xx thường không retry mù. Retry cần idempotency để không tạo side effect trùng.
- **Shutdown:** khi process dừng, task chưa chạy trong queue có thể không bao giờ có kết quả; cần quản lý graceful shutdown, cancellation và lưu trạng thái bền vững với job quan trọng.
- **Chia sẻ trạng thái:** Java Future nằm trong RAM của một JVM; nhiều instance cần kho chung để giữ kết quả, retry và trạng thái terminal.

### Các trạng thái lỗi không nên đánh đồng

| Trạng thái | Ví dụ | Xử lý đề xuất |
| --- | --- | --- |
| `FAILED_BUSINESS` | Không đủ tồn kho, đơn không hợp lệ | Ghi error code, báo caller; thường không retry vô hạn |
| `FAILED_TRANSIENT` | Remote service 503, tạm mất kết nối | Retry có giới hạn, exponential backoff + jitter |
| `REJECTED` | Executor bão hòa | Backpressure, 429/503, queue bền vững khi cần |
| `TIMED_OUT` | Deadline hết nhưng worker chưa chắc dừng | Đánh dấu trạng thái cần đối soát, idempotency, kiểm tra kết quả muộn |
| `CANCELLED` | Hủy được Future | Bảo đảm UI/status phản ánh cancellation, lưu ý side effect có thể đã xảy ra |
| `SUCCEEDED` | Kết quả nghiệp vụ và side effect đã được xác nhận | Ghi kết quả/metadata cần thiết |

Không dùng một exception handler chung bắt `Throwable` rồi trả mã `200 OK` cho tất cả trường hợp; cần phân loại và trả contract nhất quán.

## 12. Checklist kiểm thử và review

Một test đáng tin nên có **ít nhất năm nhánh**: thành công, business exception, timeout, submission rejection và cancellation. Ngoài ra cần kiểm tra observer/retry và shutdown trong sản phẩm quan trọng.

1. **Đã giữ handle?** Mỗi `submit/supplyAsync/@Async` có caller nhận và xử lý Future, hoặc một watcher/job store rõ ràng?
2. **Đã quan sát terminal failure?** `whenComplete` có nhánh `error != null`, `get/join` có catch đúng kiểu, hoặc `handle` trả outcome lỗi tường minh?
3. **Có bỏ stage trả về của callback?** Nếu `whenComplete` là thao tác bắt buộc, có theo dõi chính stage mới khi callback thất bại không?
4. **Có đang nuốt lỗi?** Tìm `exceptionally(ex -> null)`, `catch (Exception e) { return defaultValue; }`, `Future<?>` không dùng, `thenAccept` chỉ log success.
5. **Chữ ký Spring đúng?** `@Async` trả `void`, `Future<T>` hoặc `CompletableFuture<T>`; method public và được gọi qua proxy từ bean khác; executor cụ thể được xác định?
6. **Lỗi xảy ra lúc submit hay lúc execute?** Có kiểm tra `TaskRejectedException`/queue saturation mà không cần đợi Future vốn chưa được trả?
7. **Có deadline?** `get(timeout)`/`orTimeout` và timeout I/O thực sự, cộng theo dõi task chạy muộn?
8. **HTTP contract?** Trả 202 chỉ khi yêu cầu đã được tiếp nhận đúng nghĩa; response/status rõ cho `FAILED/REJECTED`, không báo thành công giả?
9. **Trạng thái bền vững?** Với job quan trọng, có job ledger, outbox/broker, retry, idempotency và reconciliation sau restart?
10. **Có log có tương quan?** Job ID, error code, cause, trace và metric, nhưng không rò dữ liệu nhạy cảm?
11. **Test worker thật?** Test có kiểm tra một `@Async` bị business exception trên thread của pool và đúng proxy path, không chỉ test method trực tiếp?
12. **Test allOf/partial failure?** Có case một child thất bại, một child pending, deadline và thu trạng thái riêng từng nguồn?

### Câu hỏi tự kiểm tra

1. Tại sao `ExecutorService.submit` trả về một `Future` nhưng exception của `Callable` có thể không xuất hiện ở stderr?
2. `future.isDone() == true` có đủ chứng minh nghiệp vụ đã thành công chưa?
3. Nếu `CompletableFuture` thất bại, `thenApply` hoặc `thenAccept` có chạy không? Đặt observer lỗi ở đâu?
4. `whenComplete` khác `handle` và `exceptionally` về việc giữ nguyên hay biến đổi trạng thái lỗi như thế nào?
5. Tại sao `get(5, SECONDS)` hết hạn không có nghĩa worker đã bị hủy hoặc DB transaction rollback?
6. Trong Spring `@Async void`, caller lấy exception qua đâu? Khi nào nên chuyển sang return type `CompletableFuture<T>`?
7. Nếu pool từ chối ngay khi submit, `whenComplete` trên Future có xử lý được không nếu Future chưa hề trả về?
8. Một API báo 202 nhưng không có job ID hay job store, chuyện gì xảy ra khi process bị kill giữa chừng?
9. Nếu một callback ghi audit bị lỗi, vì sao chỉ giám sát Future gốc có thể không đủ?
10. `exceptionally(ex -> fallback)` được phép ở trường hợp nào, và trường hợp nào nó biến lỗi nghiêm trọng thành kết quả “thành công” sai?

**Kết luận:** Future là **kênh mang kết quả và lỗi**, không phải một lệnh “gửi rồi quên”. Hãy giữ hoặc chuyển tiếp handle, quan sát mọi nhánh hoàn tất, phân loại lỗi nghiệp vụ, gắn deadline và ghi trạng thái bền vững khi cần. Khi không giữ Future, phải có một cơ chế quan sát khác được thiết kế rõ ràng; không để exception bị giữ trong Future rồi biến mất khỏi luồng nghiệp vụ.

## Tài liệu tham khảo chính thức

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — Task Execution, @Async và exception handling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
