# `TaskExecutorAdapter`: thích nghi hợp đồng `Executor` của JDK trong Spring

**Module:** Spring Framework - concurrency  
**Nhóm:** Chọn bộ thực thi  
**Chủ đề:** `TaskExecutorAdapter` thích nghi hợp đồng `Executor` của JDK.

## 1. Bài toán: đã có `Executor` của JDK, muốn dùng qua API của Spring

Nhiều hệ thống Java đã có sẵn bộ thực thi công việc (`Executor` hoặc `ExecutorService`) do thư viện khác, container hoặc tầng hạ tầng cung cấp. Trong khi đó, mã Spring có thể muốn giao tiếp qua `TaskExecutor` hoặc `AsyncTaskExecutor`, gắn `TaskDecorator` và thống nhất cách báo từ chối tác vụ. **`TaskExecutorAdapter` là lớp cầu nối theo chiều JDK → Spring**.

Một cách hình dung:

```text
Mã gọi dùng Spring TaskExecutor / AsyncTaskExecutor
                      |
                      v
     TaskExecutorAdapter (adapter, không chứa worker riêng)
                      |
                      v
        JDK Executor / ExecutorService có sẵn
                      |
                      v
       Thread/queue/scheduling thật của delegate
```

Đối tượng adapter **không tự tạo thread pool, không tự quyết định số worker, không tự lưu job bền vững**. Nó chuyển lời gọi sang executor đã được truyền vào constructor. Nếu delegate chạy tác vụ ngay trên thread gọi, adapter cũng có thể chạy đồng bộ; nếu delegate có thread pool, công việc chạy theo lịch của pool đó.

Ví dụ định hướng:

```java
Executor jdkExecutor = ...; // Executor đã tồn tại trong ứng dụng.
TaskExecutorAdapter springExecutor = new TaskExecutorAdapter(jdkExecutor);
springExecutor.execute(() -> doWork());
```

Đây là **đoạn minh họa**, cần khai báo `jdkExecutor`, `doWork()` và import các kiểu tương ứng trong ứng dụng của bạn. Điểm chính là **giữ nguyên delegate**, thay đổi giao diện mà phía tiêu thụ sử dụng.

### Vì sao không dùng thẳng `Executor`?

Bạn *có thể* dùng thẳng JDK `Executor` ở nhiều nơi trong Spring: `TaskExecutor` kế thừa hợp đồng `Executor`, và nhiều điểm tích hợp Spring chấp nhận `Executor`. Adapter hữu ích khi:

- API yêu cầu một đối tượng kiểu `TaskExecutor`/`AsyncTaskExecutor` của Spring.
- Muốn `submit(Runnable)` hoặc `submit(Callable<T>)` trả `Future` kể cả khi delegate chỉ là `Executor`.
- Muốn áp dụng `TaskDecorator` ở ranh giới giao việc.
- Muốn cách báo lỗi từ chối theo `TaskRejectedException` của Spring.
- Muốn tái sử dụng một executor đã có mà chưa cần chuyển toàn bộ cấu hình sang `ThreadPoolTaskExecutor`.

Adapter là một **lựa chọn tích hợp**, không phải bước bắt buộc cho mọi trường hợp bất đồng bộ.

## 2. Các hợp đồng cần phân biệt

| Giao diện/lớp | Đóng vai trò gì? | Khả năng nổi bật |
| --- | --- | --- |
| `java.util.concurrent.Executor` | Hợp đồng JDK cơ bản | `execute(Runnable)`, không quy định phải tạo thread mới |
| `java.util.concurrent.ExecutorService` | Hợp đồng JDK mở rộng | `submit`, `Future`, `shutdown`, chờ kết thúc, các thao tác xử lý nhiều task |
| `org.springframework.core.task.TaskExecutor` | Giao diện Spring, cũng là `Executor` | `execute(Runnable)` dưới mô hình task executor của Spring |
| `org.springframework.core.task.AsyncTaskExecutor` | Giao diện Spring mở rộng `TaskExecutor` | `submit(Runnable)` / `submit(Callable<T>)` trả `Future` |
| `org.springframework.core.task.support.TaskExecutorAdapter` | Bọc JDK `Executor` | Cung cấp `AsyncTaskExecutor` của Spring bằng cách ủy quyền/bao `FutureTask`, tùy delegate |
| `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` | Executor do Spring cấu hình và quản lý | Thread pool, queue, thread name, lifecycle, metrics/cấu hình phù hợp Spring |
| `org.springframework.core.task.support.ExecutorServiceAdapter` | Adapter **ngược chiều** | Đưa Spring `TaskExecutor` ra dạng JDK `ExecutorService`; lifecycle vẫn thuộc executor thực |

Tên `TaskExecutorAdapter` dễ khiến ta tưởng nó là một “công cụ tạo pool”; thực chất nó chỉ làm **thích nghi giao diện**. Cũng không nên nhầm nó với `ExecutorServiceAdapter`: hai lớp đi ngược chiều nhau.

**Ghi chú phiên bản:** bài này dùng những API ổn định `execute`, `submit` và `setTaskDecorator`. Ở dòng Spring Framework 6.2, `TaskExecutorAdapter` còn triển khai `AsyncListenableTaskExecutor`; ở Spring Framework 7, tập giao diện đã được đơn giản hóa về `AsyncTaskExecutor`. Không dựa vào `submitListenable` khi viết ví dụ có khả năng chuyển phiên bản.

## 3. `execute(Runnable)`: ủy quyền thực thi, không hứa chạy trên thread khác

Hợp đồng JDK `Executor.execute` chỉ nhận một `Runnable` để executor xử lý; cách thực thi phụ thuộc delegate:

```java
Executor inline = Runnable::run;
TaskExecutorAdapter adapter = new TaskExecutorAdapter(inline);

adapter.execute(() -> System.out.println("work"));
```

Ở ví dụ này, `Runnable::run` gọi `run()` **ngay tại thread hiện tại**, nên `execute` có tính chất đồng bộ. Nếu thay delegate bằng `Executors.newFixedThreadPool(2)`, task được lên lịch qua thread pool. Adapter không đổi cách hành xử căn bản đó.

Một số vấn đề cần phân biệt:

- Lệnh `execute()` **trả về `void`**; không có `Future` trực tiếp để nhận kết quả.
- Không mặc định suy ra task đã hoàn thành khi `execute` trả về; điều này chỉ đúng với delegate chạy trực tiếp.
- Nếu executor từ chối vì đã shutdown hoặc đã đầy, lời gọi có thể ném lỗi tại thời điểm giao việc.
- Lỗi runtime **bên trong** task xảy ra lúc task thực thi; nếu task ở worker thread, ngoại lệ không tự quay về request thread đã gọi `execute`.
- Thay delegate thành executor mới là quyết định về worker, queue, độ song song và chính sách backpressure; thay adapter đơn thuần không thực hiện điều đó.

## 4. `submit`: bổ sung hợp đồng `Future` cho cả `Executor` thường

`AsyncTaskExecutor` có hai kiểu gọi:

```java
Future<?> done = adapter.submit((Runnable) () -> performAction());
Future<Integer> result = adapter.submit(() -> calculateValue());
```

Đây là **đoạn minh họa** cần phương thức `performAction()` và `calculateValue()` thích hợp. Với `Runnable`, `Future.get()` thành công trả `null`; với `Callable<T>`, nó trả giá trị kiểu `T`. Một ngoại lệ khi thực thi được lưu trong `Future`; gọi `get()` ném `ExecutionException` có `getCause()` là lỗi gốc. `get()` chặn thread gọi đến khi xong hoặc lỗi.

Về cơ chế, `TaskExecutorAdapter` có hai nhánh quan trọng:

1. **Delegate là `ExecutorService` và chưa cấu hình `TaskDecorator`:** adapter có thể gọi thẳng `ExecutorService.submit(...)` của delegate và trả lại `Future` mà delegate tạo.
2. **Delegate chỉ là `Executor` hoặc đã đặt `TaskDecorator`:** adapter tạo `FutureTask`, giao `Runnable` này bằng `execute`, rồi trả `FutureTask` cho phía gọi. Điều này cho phép một `Executor` vốn chỉ có `execute` vẫn phục vụ `submit`.

Đường đi điển hình:

```text
submit(Callable<T>)
       |
       +-- ExecutorService + không decorator --> delegate.submit(callable)
       |
       +-- Executor thường / có decorator --> FutureTask(callable)
                                              |
                                              v
                                  delegate.execute(FutureTask được bọc)
                                              |
                                              v
                                   Future<T> cho bên gọi
```

Cả hai nhánh vẫn phụ thuộc vào delegate: một executor chạy trực tiếp khiến `Future` hoàn tất ngay trên thread gọi; pool có thể xử lý chậm; queue quá tải có thể từ chối.

### `Future` không tự biến tác vụ thành job lâu dài

`Future` biểu diễn một lần tính toán **trong tiến trình đang chạy**. Nó không tự lưu trạng thái vào database, không tự retry sau crash và không đồng nghĩa client HTTP có thể tra cứu kết quả sau khi response kết thúc.

Nếu controller gọi `future.get()` ngay sau `submit`, thread controller vẫn **chờ** task xong. Chỉ chuyển từ `execute` sang `submit` không giúp giải phóng request thread. Việc xử lý nền và hợp đồng HTTP phải được thiết kế riêng.

## 5. Ví dụ Java 17 chạy được: direct executor, pool, `submit`, decorator, rejection

Ví dụ hoàn chỉnh sau minh họa chính xác các tính chất:

- Delegate **chạy trực tiếp** (`Runnable::run`) khiến adapter cũng chạy đồng bộ.
- Delegate là JDK `ExecutorService` với hai worker và queue có giới hạn; adapter nhận việc và trả `Future`.
- `TaskDecorator` bọc các callback để đếm số lần task thực thi.
- Delegate từ chối một task; adapter báo `TaskRejectedException` ở Spring.

Chọn **JDK 17+**, Maven và **Spring Core 6.2.12** cho ví dụ cố định phiên bản. Cấu trúc:

```text
taskexecutor-adapter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── TaskExecutorAdapterDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>taskexecutor-adapter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/TaskExecutorAdapterDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.core.task.support.TaskExecutorAdapter;

public class TaskExecutorAdapterDemo {

    public static void main(String[] args) throws Exception {
        Thread callingThread = Thread.currentThread();

        // Executor hợp lệ của JDK, nhưng luôn chạy ngay tại thread gọi.
        Executor directExecutor = Runnable::run;
        TaskExecutorAdapter direct = new TaskExecutorAdapter(directExecutor);
        AtomicInteger sameThread = new AtomicInteger();

        direct.execute(() -> sameThread.set(
                Thread.currentThread() == callingThread ? 1 : 0));

        System.out.println("inline=" + (sameThread.get() == 1));
        System.out.println("inlineResult=" + direct.submit(() -> 6 * 7).get());

        // Pool JDK thật: 2 worker, queue tối đa 8 job đang chờ.
        ExecutorService jdkPool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(8),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            TaskExecutorAdapter spring = new TaskExecutorAdapter(jdkPool);
            AtomicInteger decoratedRuns = new AtomicInteger();

            spring.setTaskDecorator(task -> () -> {
                decoratedRuns.incrementAndGet();
                task.run();
            });

            Future<Integer> answer = spring.submit(() -> 40 + 2);
            CountDownLatch signal = new CountDownLatch(1);
            spring.execute(signal::countDown);
            Future<?> noResult = spring.submit(() -> { });

            // Chỉ trong demo: chờ để xác định output.
            System.out.println("poolResult=" + answer.get());
            if (!signal.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("execute task did not finish");
            }
            noResult.get();
            System.out.println("decorated=" + decoratedRuns.get());
        } finally {
            // Chủ sở hữu delegate quản lý shutdown, không phải adapter.
            jdkPool.shutdown();
            if (!jdkPool.awaitTermination(10, TimeUnit.SECONDS)) {
                jdkPool.shutdownNow();
            }
        }

        Executor alwaysReject = task -> {
            throw new RejectedExecutionException("busy");
        };
        TaskExecutorAdapter rejecting = new TaskExecutorAdapter(alwaysReject);

        try {
            rejecting.execute(() -> { });
        } catch (TaskRejectedException ex) {
            System.out.println("rejected=TaskRejectedException");
        }
    }
}
```

Chạy tại thư mục dự án:

```bash
mvn -q compile exec:java -Dexec.mainClass=TaskExecutorAdapterDemo
```

**Stdout của chương trình khi hoàn tất bình thường:**

```text
inline=true
inlineResult=42
poolResult=42
decorated=3
rejected=TaskRejectedException
```

Giải thích output:

- `inline=true`: adapter dùng `Runnable::run`, chạy trên thread gọi; tên lớp có chữ “TaskExecutor” không bảo đảm bất đồng bộ.
- `inlineResult=42`: `submit(Callable)` vẫn làm việc dù delegate chỉ có `Executor.execute`. Vì delegate chạy trực tiếp, phép tính đã xong trước khi `submit` trả về.
- `poolResult=42`: delegate JDK có worker pool; `Future.get()` đợi kết quả trả ra từ worker. Đây là chỗ chương trình demo **cố ý chờ** để in đúng output.
- `decorated=3`: có ba lời giao task qua cùng adapter sau khi đặt decorator: `submit(Callable)`, `execute(Runnable)`, `submit(Runnable)`. Decorator bọc callback trong cả ba trường hợp.
- `rejected=TaskRejectedException`: lỗi `RejectedExecutionException` từ delegate khi giao việc được chuyển thành ngoại lệ của Spring. Đó là lỗi *nhận việc*, khác với lỗi bên trong task đã nhận.

`Future.get()` trong ví dụ dùng để kiểm tra, không đại diện cho cách tối ưu độ trễ HTTP. Trong ứng dụng thật, không nên vô tình giữ một request thread chờ cùng pool đang quá tải.

## 6. `TaskDecorator`: bọc callback ở ranh giới chạy task

`setTaskDecorator(TaskDecorator)` cho phép thêm logic **quanh lúc chạy** task, thường dùng cho trace/metrics hoặc truyền một số context từ thread gửi task sang thread chạy task:

```java
TaskExecutorAdapter adapter = new TaskExecutorAdapter(jdkExecutor);

adapter.setTaskDecorator(task -> () -> {
    long started = System.nanoTime();
    try {
        task.run();
    } finally {
        long durationNanos = System.nanoTime() - started;
        metrics.record(durationNanos);
    }
});
```

Đây là **đoạn minh họa**: `jdkExecutor` và `metrics` là dependency cần định nghĩa trong ứng dụng. Decorator bọc `Runnable` được adapter thực thi, **có thể là callback nội bộ như `FutureTask`**, không nhất thiết chính là Runnable/Callable do người dùng gửi vào.

Khi cần truyền `ThreadLocal`, hãy chụp giá trị ở **thread gửi task** trong giai đoạn `decorate`, rồi đặt và khôi phục giá trị cũ ở **thread worker** trong `run`:

```java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

static org.springframework.core.task.TaskDecorator traceDecorator() {
    return task -> {
        String captured = TRACE_ID.get(); // Thread gửi task.
        return () -> {
            String previous = TRACE_ID.get(); // Thread worker.
            try {
                if (captured == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(previous);
                }
            }
        };
    };
}
```

Đây là **đoạn phương thức minh họa**, cần đặt bên trong một class có trường `TRACE_ID` tương ứng. Trong ứng dụng production nên ưu tiên cơ chế truyền context chính thức của stack đang dùng, tránh tự sao chép dữ liệu nhạy cảm vào pool. Đừng nhầm việc truyền trace/MDC với việc tự mang theo database transaction; transaction gắn với thread và hệ thống quản lý transaction, không được nhân bản tùy tiện sang worker.

### Ngoại lệ trong decorator: `execute` khác `submit`

Với lời gọi `submit`, callback mà decorator thấy có thể là một `FutureTask`: `FutureTask.run()` **giữ lại exception trong Future**, không nhất thiết ném ngoại lệ ra khỏi `run()` cho wrapper bắt. Vì vậy:

```java
// Không đủ để kết luận mọi Callable đã thành công.
adapter.setTaskDecorator(task -> () -> {
    try {
        task.run();
    } catch (Exception ex) {
        logFailure(ex);
        throw ex;
    }
});
```

Đây chỉ là **đoạn minh họa** với `logFailure` chưa định nghĩa. Khi `submit`, một `Callable` thất bại vẫn có thể làm `task.run()` trở về bình thường đối với decorator, còn `future.get()` mới ném `ExecutionException`. Thiết kế error reporting theo contract `Future`/completion handler hoặc báo lỗi tường minh trong worker; đừng dựa vào một `catch` của decorator để bắt mọi lỗi nghiệp vụ.

## 7. Từ rejection của JDK sang lỗi của Spring

Một `ThreadPoolExecutor` có thể từ chối task khi đã shutdown hoặc vượt khả năng nhận việc theo giới hạn cấu hình. Với chính sách `AbortPolicy`, JDK ném `RejectedExecutionException`. `TaskExecutorAdapter` bắt lỗi từ quá trình giao việc và chuyển thành `TaskRejectedException` để phù hợp với hợp đồng Spring.

```text
Spring caller
    |
    | adapter.execute(task) / submit(task)
    v
JDK delegate nhận task?
    |
    +-- Có --> task chờ/chạy --> thành công hoặc lỗi nội bộ của task
    |
    +-- Không --> RejectedExecutionException
                       |
                       v
                  TaskRejectedException
```

**Phân biệt hai lỗi:**

- **Rejection:** executor không nhận việc; với `AbortPolicy` nó xuất hiện ngay lúc `execute`/`submit`. Bên gọi có thể phản ứng: trả `503`/`429` tùy giao thức, chuyển sang queue khác, hoặc báo hệ thống bận.
- **Execution failure:** task được nhận nhưng lỗi khi chạy; với `submit`, lỗi được quan sát qua `Future.get()`/completion handling. Không nên tự động retry thao tác có side effect nếu chưa có chiến lược idempotency.

Một số `RejectedExecutionHandler` của JDK **không ném lỗi**: `CallerRunsPolicy` có thể thực thi task ngay trên thread gửi (trừ trường hợp executor đã shutdown). Khi đó adapter không thể suy đoán rằng tác vụ đã bị từ chối, và request thread có thể bị chặn lâu. Chọn chính sách theo nhu cầu backpressure và trách nhiệm phản hồi, không mặc định rằng dùng adapter bảo đảm luôn ném `TaskRejectedException`.

## 8. Tích hợp vào Spring: bean adapter quanh pool JDK

Một ứng dụng có executor JDK đang được dùng bởi thư viện khác có thể công bố adapter như bean Spring. Ví dụ **hai file** trong một ứng dụng Spring Boot dùng Spring Framework 6.x:

**`AsyncExecutorConfig.java`** (đặt trong package ứng dụng, ví dụ `com.example.jobs`):

```java
package com.example.jobs;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.support.TaskExecutorAdapter;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncExecutorConfig {

    @Bean(name = "jdkBusinessPool", destroyMethod = "shutdown")
    public ExecutorService jdkBusinessPool() {
        return new ThreadPoolExecutor(
                2, 4, 30L, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(100),
                new ThreadPoolExecutor.AbortPolicy());
    }

    @Bean("businessExecutor")
    public AsyncTaskExecutor businessExecutor(
            @Qualifier("jdkBusinessPool") ExecutorService jdkPool) {
        return new TaskExecutorAdapter(jdkPool);
    }
}
```

Ở đây:

- `jdkBusinessPool` là **backend executor thật**, với tối đa 4 worker và 100 chỗ trong queue; `AbortPolicy` từ chối khi không còn sức chứa.
- `businessExecutor` chỉ là một đối tượng Spring bọc delegate đó. Chương trình không có *hai* thread pool.
- `destroyMethod="shutdown"` áp dụng cho **bean sở hữu `ExecutorService`**. Adapter không phải `ExecutorService` và không cung cấp lifecycle `shutdown()` thay mặt delegate.
- Cấu hình bean là ví dụ độc lập về cách kết nối; đặt nó vào ứng dụng có cấu hình phù hợp, tránh tạo nhiều executor trùng vai trò.

**`ReportService.java`**:

```java
package com.example.jobs;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("businessExecutor")
    public CompletableFuture<String> createReport(String reportId) {
        String artifactId = "report-" + reportId;
        return CompletableFuture.completedFuture(artifactId);
    }
}
```

Đây là **file class trong ứng dụng Spring**, không phải chương trình có `main` độc lập. Với `@EnableAsync`, lời gọi công khai đi qua Spring proxy tới `ReportService.createReport` được giao cho bean executor được đặt tên. `CompletableFuture.completedFuture(...)` bên trong là kết quả do worker tính ra; future mà bên gọi nhận biểu diễn lời gọi bất đồng bộ do Spring quản lý.

**Hai giới hạn quan trọng:**

1. Gọi `this.createReport(...)` từ chính `ReportService` **không đi qua proxy** trong chế độ proxy mặc định, nên `@Async` có thể không có hiệu lực. Gọi từ một Spring bean khác, hoặc dùng cơ chế invocation phù hợp.
2. Việc `@Async` trả future không tự ghi job bền vững. Nếu tiến trình dừng, task đang trong queue bộ nhớ có thể mất. Với tác vụ quan trọng, cần một kho trạng thái/queue bền vững và cách khôi phục.

Nếu ứng dụng đã dùng `ThreadPoolTaskExecutor`, thường chỉ cần dùng chính bean đó cho `@Async`. Chọn `TaskExecutorAdapter` khi bạn thực sự phải **tiêu thụ executor JDK đang có** hoặc cần lộ giao diện Spring một cách có chủ đích.

## 9. Quyền sở hữu và vòng đời: ai đóng pool?

Điều gì xảy ra khi gọi:

```java
ExecutorService jdkPool = java.util.concurrent.Executors.newFixedThreadPool(2);
TaskExecutorAdapter adapter = new TaskExecutorAdapter(jdkPool);
```

`adapter` **không trở thành chủ sở hữu mặc định** của `jdkPool`. Adapter không có API `shutdown()` như `ExecutorService`, không tự đóng pool khi đối tượng adapter bị bỏ tham chiếu. Thành phần tạo/đăng ký pool phải quản lý `shutdown` theo hợp đồng của ứng dụng.

Nếu bạn viết chương trình Java thường: dùng `try/finally`, shutdown và chờ các worker kết thúc khi có thể. Trong Spring IoC: có thể đăng ký backend dưới dạng bean có destroy method hoặc dùng executor Spring có lifecycle tích hợp.

**Không đóng pool ở mỗi request**: một shared executor phục vụ nhiều request; shutdown sau request đầu tiên sẽ làm các request tiếp theo bị từ chối. Ngược lại, nếu tạo executor mới mỗi lần gọi controller mà không đóng, ứng dụng có thể rò thread và cạn tài nguyên.

`ExecutorServiceAdapter` (Spring → JDK) là một lớp khác: nó phơi bày giao diện JDK của một `TaskExecutor` phía sau. Theo hợp đồng của lớp đó, lifecycle vẫn do backend đảm nhận; các thao tác shutdown trên adapter ngược chiều không có ý nghĩa thay thế việc quản lý backend.

## 10. Chọn adapter hay `ThreadPoolTaskExecutor`?

| Tình huống | Khuyến nghị | Lý do |
| --- | --- | --- |
| Đã có JDK `ExecutorService` do thư viện/ứng dụng quản lý, cần interface Spring | `TaskExecutorAdapter` | Tái sử dụng đúng pool hiện hữu, không đổi ownership |
| Chỉ có `Executor` JDK, nhưng bên gọi cần `submit`/`Future` | `TaskExecutorAdapter` | Cung cấp `FutureTask` phù hợp qua hợp đồng `AsyncTaskExecutor` |
| Dự án Spring mới, muốn cấu hình pool/queue/thread name/lifecycle qua bean Spring | `ThreadPoolTaskExecutor` | Cấu hình rõ và quản lý cùng container |
| Cần chạy task theo lịch hoặc cron | `TaskScheduler`/scheduler phù hợp | Adapter không tự cung cấp khả năng schedule |
| Cần executor từ container hoặc thư viện ngoài theo chuẩn riêng | Xem adapter của tích hợp tương ứng; có thể dùng `TaskExecutorAdapter` | Trước tiên cần tôn trọng ownership/quy tắc của container |
| Cần xử lý job bền vững qua restart và nhiều instance | DB/broker + worker | Adapter chỉ chuyển lời gọi trong một tiến trình |
| Chỉ có vài lời gọi `execute` qua `Executor` và API Spring đã nhận `Executor` | Có thể dùng trực tiếp JDK `Executor` | Không cần thêm lớp bọc khi không có lợi ích thực tế |

Một số lớp Spring như `ConcurrentTaskExecutor` cũng hỗ trợ thích nghi executor JDK với các tiện ích của `spring-context`; đó là lựa chọn khác ở tầng scheduling/concurrency. Không cần dựng nhiều tầng adapter nếu một bean hiện tại đã đáp ứng contract.

## 11. Các lỗi triển khai thường gặp

### 11.1. Tưởng adapter tự tạo thread mới

```java
TaskExecutorAdapter adapter = new TaskExecutorAdapter(Runnable::run);
adapter.execute(() -> longOperation());
```

Đây là **đoạn minh họa**, với `longOperation()` do bạn định nghĩa. Tác vụ này chạy ngay trong thread gọi. Nếu muốn chạy nền, chọn executor delegate thực sự xử lý trên worker khác.

### 11.2. Chọn `submit` rồi gọi `get()` ngay trong controller

`Future<T>` không phải tín hiệu tác vụ nền đã tách vòng đời HTTP. `get()` có thể giữ thread HTTP tới khi worker xong. Nếu cần trả kết quả trong cùng response, dùng cơ chế async request của Spring MVC/WebFlux phù hợp; nếu cần trả `202 Accepted` rồi theo dõi sau, thiết kế job ID, trạng thái, retry và lưu trữ.

### 11.3. Không giới hạn queue hoặc không xử lý rejection

`Executors.newFixedThreadPool(n)` dùng queue không giới hạn theo khả năng bộ nhớ, nên giới hạn **số worker** chưa tương đương giới hạn **số công việc tồn đọng**. Với tải thực, cân nhắc `ThreadPoolExecutor` có queue hữu hạn, handler rõ ràng, theo dõi queue depth, rejected count và latency.

### 11.4. Coi lỗi trong `Future` giống lỗi ném khi gửi task

`execute`/`submit` có thể bị từ chối ngay. Nhưng task đã được nhận rồi mới thất bại sẽ được quan sát ở luồng xử lý/lúc truy cập `Future`. Với `submit`, phải xử lý `ExecutionException` hoặc callback thích hợp. `TaskDecorator` chỉ bọc execution callback, không bảo đảm bắt hết exception bên trong `FutureTask`.

### 11.5. Cố “lan truyền transaction” qua decorator

Một `ThreadLocal` trace ID có thể truyền an toàn nếu có thiết kế capture/restore/cleanup. Nhưng database transaction gắn với resource và transaction manager; không sao chép nó sang worker bằng thao tác copy context. Worker muốn cập nhật DB phải mở transaction theo yêu cầu nghiệp vụ, và phải cân nhắc việc enqueue task trước hay sau commit.

### 11.6. Quên self-invocation với `@Async`

`@EnableAsync` ở chế độ proxy không bắt được lời gọi nội bộ qua `this`. Trước khi đổ lỗi cho adapter, kiểm tra method có được gọi qua Spring proxy, bean executor có tên đúng và service có thực sự được Spring quản lý.

### 11.7. Dùng nhiều adapter rồi nghĩ đã có nhiều pool độc lập

Hai `TaskExecutorAdapter` cùng trỏ vào một `ExecutorService` thì vẫn chia sẻ cùng worker/queue, chịu ảnh hưởng tải lẫn nhau. Muốn cô lập tác vụ quan trọng, cần các delegate executor riêng với kích thước và chính sách backpressure riêng.

### 11.8. Đóng delegate từ nơi không sở hữu

Nếu executor được chia sẻ, một thành phần tự `shutdown()` có thể làm tất cả consumer khác thất bại. Xác định rõ người tạo pool, phạm vi bean và thời điểm đóng trong lifecycle ứng dụng.

## 12. Câu hỏi tự kiểm tra và bài tập

**Câu 1.** `TaskExecutorAdapter` nhận `Executor direct = Runnable::run`. Lệnh `adapter.submit(() -> 42)` có thực sự chạy bất đồng bộ không?  
**Đáp:** Không. Delegate chạy `Runnable` trên thread gọi nên `FutureTask` hoàn tất trong lúc `submit` đang gọi; adapter không ép tạo thread mới.

**Câu 2.** Vì sao `TaskExecutorAdapter` có thể `submit(Callable)` dù delegate chỉ có `execute(Runnable)`?  
**Đáp:** Adapter có thể bọc `Callable` trong `FutureTask` rồi chuyển `FutureTask` vào `Executor.execute`. `FutureTask` vừa là `Runnable` vừa là `Future`.

**Câu 3.** Nếu delegate là `ExecutorService`, adapter luôn gọi `executorService.submit` chứ?  
**Đáp:** Không. Không có decorator, adapter có thể ủy quyền trực tiếp; có decorator, adapter có thể bọc task thành `FutureTask` để chạy qua đường decorator/`execute`.

**Câu 4.** Trong Spring, ai nên shutdown executor JDK đã bọc?  
**Đáp:** Thành phần/bean sở hữu delegate; bản thân `TaskExecutorAdapter` không thay thế lifecycle của `ExecutorService`.

**Câu 5.** Tại sao một decorator `try { task.run(); } catch (...)` có thể không thấy lỗi của `Callable` gửi qua `submit`?  
**Đáp:** Callback có thể là `FutureTask`; nó bắt lỗi của `Callable` và lưu để `Future.get()` ném `ExecutionException`, thay vì phát lỗi ra khỏi `run()`.

**Câu 6.** Ba replica Spring dùng cùng một DB. Chỉ bọc JDK pool bằng `TaskExecutorAdapter` có bảo vệ nhất quán dữ liệu liên replica không?  
**Đáp:** Không. Adapter chỉ liên quan việc gửi task tới executor trong JVM; ranh giới DB/phân tán cần transaction, locking/version, idempotency hoặc kiến trúc phù hợp.

### Bài tập ngắn

1. Thay delegate trực tiếp `Runnable::run` bằng `Executors.newSingleThreadExecutor()`. Dùng `CountDownLatch` để xác định work có chạy trên thread khác và **nhớ đóng delegate**.
2. Đặt decorator đếm số task và gửi lần lượt `execute`, `submit(Runnable)`, `submit(Callable)`. Vì sao số lần wrap có thể khác số lần task thành công?
3. Tạo một `ThreadPoolExecutor` có 1 worker, queue 1 phần tử và `AbortPolicy`; giữ worker bận với latch, thêm tác vụ vào queue, rồi thử gửi tác vụ thứ ba. Quan sát `TaskRejectedException` khi pool không nhận thêm việc. Dọn latch/pool bằng `finally`.
4. Trong một ứng dụng Spring, công bố một bean `AsyncTaskExecutor` bằng `TaskExecutorAdapter` quanh pool JDK. Dùng `@Async("...")` trên một service được **bean khác** gọi và quan sát thread; thử gọi nội bộ để hiểu ảnh hưởng proxy.

## 13. Ghi nhớ

`TaskExecutorAdapter` **thích nghi hợp đồng** giữa Spring và JDK; backend executor vẫn quyết định khi nào và bằng thread nào task chạy, có chỗ trong queue hay không, và khi nào cần shutdown.

- **`execute`** chuyển `Runnable` tới delegate.
- **`submit`** trả `Future`, ủy quyền qua `ExecutorService.submit` khi phù hợp hoặc dùng `FutureTask` khi cần.
- **`TaskDecorator`** bọc callback, hữu ích cho metrics/context; phải xử lý exception của `Future` bằng contract phù hợp.
- **Rejection** có thể được biểu diễn bằng `TaskRejectedException`, còn lỗi task đã chạy phải được theo dõi riêng.
- **Không có bảo đảm tự động** về async thread, durability, retry, isolation, transaction hay lifecycle chỉ vì có adapter.

Tài liệu chính thức để đối chiếu API:

- [Spring Framework 6.2 — `TaskExecutorAdapter` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html).
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).
- [Spring Framework 6.2 — `AsyncTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html).
- [Java SE 17 — `Executor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html).
- [Java SE 17 — `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- [Java SE 17 — `FutureTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html).
- [Spring Framework 7 — `TaskExecutorAdapter` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html).