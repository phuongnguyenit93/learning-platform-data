# ExecutionException, CompletionException và nguyên nhân gốc

## 1. Tại sao một lỗi nghiệp vụ lại xuất hiện dưới tên exception khác?

Khi một công việc Java chạy qua `ExecutorService`, `CompletableFuture` hay Spring `@Async`, lỗi xảy ra **trong worker** thường không được ném trực tiếp vào stack của **thread gọi**. Thay vào đó, lỗi được lưu như trạng thái thất bại của một `Future`. Khi caller lấy kết quả hoặc phối hợp các giai đoạn, API báo thất bại bằng một **exception bao bọc (wrapper exception)**.

Hai wrapper quan trọng nhất:

- **`ExecutionException`**: thường gặp khi gọi `Future.get()`, `CompletableFuture.get()` hoặc `get(timeout, unit)` và computation đã thất bại. Đây là **checked exception**.
- **`CompletionException`**: thường gặp khi gọi `CompletableFuture.join()`, `getNow(...)` hoặc dùng các chuỗi `CompletionStage` có giai đoạn hoàn thành lỗi. Đây là **unchecked exception**.

Ví dụ một worker gặp `IllegalStateException("database unavailable")`. Caller có thể quan sát:

~~~text
Future.get()
  └── ExecutionException
        └── cause: IllegalStateException("database unavailable")

CompletableFuture.join()
  └── CompletionException
        └── cause: IllegalStateException("database unavailable")
~~~

Cả hai đường đều có thể mô tả **cùng một lỗi gốc**, chứ không phải hai lỗi nghiệp vụ khác nhau. Cần đọc **`getCause()`** và toàn bộ cause chain để hiểu lý do thật sự. Không nên tạo alert chỉ vì thấy `ExecutionException` rồi kết luận executor bị hỏng.

**Thông điệp chính:** wrapper nói về *cơ chế truyền kết quả bất đồng bộ*; nguyên nhân bên trong mới thường nói về *điều kiện nghiệp vụ/kỹ thuật dẫn tới thất bại*. Nhưng đừng mù quáng bỏ tất cả wrapper: đôi khi một exception ở tầng ứng dụng có ý nghĩa và cần được giữ nguyên trong log.

## 2. Mô hình lỗi của một công việc bất đồng bộ

### 2.1. Lỗi xảy ra ở worker, được quan sát ở caller

~~~text
Thread caller                           Worker trong pool
-------------                           ------------------
future = executor.submit(task)  ----->  chạy task
                                                |
                                                +-- throw SQLException /
                                                |   IllegalStateException
                                                |
                                                +-- Future ghi nhận thất bại

future.get() -------------------------->  Future đã hoàn thành lỗi
      |
      +-- throw ExecutionException(cause)
      |
      +-- caller xử lý hoặc chuyển lỗi sang domain/API
~~~

Nếu caller dùng `CompletableFuture.join()`, đường trả lỗi thường đi qua `CompletionException`, không phải `ExecutionException`. Đoạn code gọi `get` vẫn có thể **chặn chờ** cho đến khi worker hoàn thành; wrapper chỉ xuất hiện ở thời điểm caller quan sát trạng thái thất bại.

Phân biệt rõ **exception khi submit** và **exception khi thực thi**:

- **Submit bị từ chối**: một `RejectedExecutionException` (hoặc `TaskRejectedException` qua Spring TaskExecutor) có thể xuất hiện ngay khi gửi task. Khi đó chưa chắc đã có Future để đợi.
- **Task được nhận rồi thất bại**: lỗi thường được giữ bên trong Future/CompletableFuture và xuất hiện khi `get`, `join` hoặc callback quan sát lỗi.
- **Task bị policy bỏ âm thầm**: một Future có thể **không hoàn thành** nếu task không chạy và không bị hủy; gọi `get()` vô thời hạn không nhất thiết nhận được wrapper nào.

Không nên dùng chung một `catch (ExecutionException)` để xử lý mọi vấn đề của thread pool: rejection, cancellation, timeout và interruption có đường báo lỗi khác.

### 2.2. Cấu trúc Throwable và cause chain

Các lớp liên quan trong JDK:

~~~text
Throwable
  └── Exception
       ├── InterruptedException              (checked)
       ├── TimeoutException                  (checked)
       ├── ExecutionException                (checked wrapper)
       └── RuntimeException
            ├── CompletionException          (unchecked wrapper)
            └── CancellationException        (unchecked)
~~~

Ví dụ:

~~~java
Throwable outer = new CompletionException(
        new ExecutionException(
                new IllegalStateException("connection lost")));
~~~

Đây là một **mảnh code minh họa** cần import `java.util.concurrent.*`. Cause chain lúc này gồm **hai wrapper**. Chỉ gọi `outer.getCause()` một lần sẽ còn thấy `ExecutionException`. Nếu cần diễn giải lỗi gốc, phải đi tiếp qua wrapper thích hợp.

Không phải Throwable nào cũng có `getCause()`. Một exception có thể không có cause, có suppressed exceptions hoặc có cause mang ý nghĩa domain. Vì vậy một helper nên có **điều kiện dừng rõ ràng**, không luôn lặp tới Throwable sâu nhất rồi quên mất các tầng trung gian.

## 3. ExecutionException: hợp đồng của Future.get()

### 3.1. Khi nào xuất hiện?

`Future.get()` chờ cho đến khi công việc hoàn thành, rồi:

1. **Thành công**: trả giá trị.
2. **Worker thất bại**: ném `ExecutionException`, với `getCause()` đại diện cho lỗi của computation.
3. **Future bị hủy**: ném `CancellationException`, không phải `ExecutionException`.
4. **Thread đang chờ bị interrupt**: ném `InterruptedException`.
5. **Dùng bản `get(timeout, unit)` và hết thời gian chờ**: ném `TimeoutException`.

`ExecutionException` là checked exception; code Java phải bắt hoặc khai báo nó. Ví dụ:

~~~java
try {
    String result = future.get(3, TimeUnit.SECONDS);
    consume(result);
} catch (ExecutionException ex) {
    Throwable computationError = ex.getCause();
    reportFailure(computationError);
}
~~~

Đây là **mảnh code minh họa**, chưa bao gồm `future`, `consume`, `reportFailure`, cũng như các nhánh xử lý `InterruptedException`, `TimeoutException` và `CancellationException`. Trong code thật cần xử lý đầy đủ hợp đồng của `get(timeout)`.

**Một điểm quan trọng:** `ExecutionException` cho biết computation đã thất bại; nó không phải bản thân lỗi `SQLException`, `IllegalArgumentException` hay exception domain. Lấy cause để xác định nguyên nhân, nhưng **giữ wrapper trong exception log** nếu cần nhìn ranh giới giữa caller và worker.

### 3.2. Future từ ExecutorService và CompletableFuture

Cả hai dạng này có thể đưa lỗi tới `ExecutionException` khi caller gọi `get()`:

~~~java
Future<String> f1 = executor.submit(() -> {
    throw new IllegalArgumentException("bad input");
});

CompletableFuture<String> f2 =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));
~~~

Đây là mảnh code cần khai báo `executor`. Dù loại Future khác nhau, việc gọi `get()` trên một computation thất bại đều theo hợp đồng `Future`.

Khác biệt nằm ở API bổ sung: `CompletableFuture` có `join`, `handle`, `exceptionally`, `whenComplete`, `thenCompose` và nhiều cách phối hợp không đòi caller chờ ngay tại mỗi bước.

## 4. CompletionException: hợp đồng của CompletableFuture.join()

`CompletableFuture.join()` chờ kết quả giống `get()` ở điểm có thể **block**, nhưng **không khai báo checked exception**. Nếu stage đã hoàn thành lỗi bởi một computation, `join()` thường ném `CompletionException` bao bọc nguyên nhân.

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("remote API failed"));

try {
    failed.join();
} catch (CompletionException ex) {
    System.out.println(ex.getCause().getMessage());
}
~~~

Stdout của **mảnh code** khi chạy trong một method hợp lệ:

~~~text
remote API failed
~~~

`join()` không có overload nhận timeout. Nếu cần giới hạn thời gian chờ ở caller, có thể dùng `get(timeout, unit)`; còn `CompletableFuture.orTimeout` thay đổi **trạng thái hoàn thành của future** nếu chưa xong đúng hạn và không mặc nhiên ngắt computation nền.

### 4.1. Vì sao CompletionException cũng có thể ở giữa một chuỗi?

Với `CompletableFuture`, exception có thể phát sinh từ một callback của `thenApply`, `thenCombine`, `thenCompose`, `supplyAsync` hoặc một stage khác.

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("not-a-number")
                .thenApply(Integer::parseInt);
~~~

Stage `parsed` hoàn thành exceptional vì `NumberFormatException`; khi caller `parsed.join()`, nó quan sát `CompletionException` với cause liên quan đến `NumberFormatException`.

**Callback nhận `Throwable` không phải lúc nào cũng nhận cùng một hình dạng wrapper** ở mọi vị trí trong chuỗi. Tùy stage, bạn có thể nhận chính nguyên nhân gốc hoặc một `CompletionException` bao bên ngoài. Do đó code xử lý lỗi nên biết kiểm tra cause chain thay vì hard-code `(MyDomainException) error.getCause()` mà không kiểm tra kiểu và `null`.

### 4.2. CompletableFuture.get() và join() trên cùng một future

Đây là sự khác biệt có tính hệ thống:

| Quan sát | `CompletableFuture.get()` | `CompletableFuture.join()` |
| --- | --- | --- |
| Có chờ nếu chưa xong? | Có | Có |
| Khi hoàn thành thành công | Trả kết quả | Trả kết quả |
| Khi hoàn thành lỗi | Thường ném `ExecutionException` | Thường ném `CompletionException` |
| Kiểu exception báo lỗi computation | Checked | Unchecked |
| Khi cancelled | `CancellationException` | `CancellationException` |
| Nếu caller bị interrupt khi chờ | Có thể ném `InterruptedException` | Không khai báo `InterruptedException` |
| Timeout trực tiếp | `get(timeout, unit)` | Không có `join(timeout)` |
| Cần lấy cause? | `ex.getCause()` | `ex.getCause()` |

Javadoc `CompletableFuture` còn nêu rõ: nếu exceptional completion đang mang một `CompletionException`, các overload `get` có thể ném `ExecutionException` với **cùng cause** nằm trong wrapper ấy, trong khi `join` có thể ném chính `CompletionException`. **Không giả định hai API tạo ra cause chain có cùng số tầng**, kể cả khi underlying failure giống nhau.

## 5. Lấy nguyên nhân gốc an toàn

### 5.1. Unwrap những wrapper đã biết, không tháo mọi lớp tùy tiện

Một helper thường đủ tốt cho hai loại wrapper đang học:

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

static Throwable unwrapAsyncFailure(Throwable error) {
    Throwable current = error;

    // Giới hạn để tránh vòng lặp bất thường trong cause chain.
    for (int depth = 0; depth < 32; depth++) {
        boolean asyncWrapper =
                current instanceof ExecutionException
                || current instanceof CompletionException;

        if (!asyncWrapper) {
            break;
        }

        Throwable cause = current.getCause();
        if (cause == null || cause == current) {
            break;
        }
        current = cause;
    }
    return current;
}
~~~

Đây là **mảnh method Java** hợp lệ khi đặt trong một class, không phải chương trình hoàn chỉnh. Hàm chỉ tháo **`ExecutionException` và `CompletionException`**. Nếu gặp `IllegalStateException`, `SQLException`, một lỗi domain hoặc một wrapper có ngữ nghĩa khác, nó **dừng lại** để ứng dụng tự quyết định.

Tại sao không viết luôn `while (t.getCause() != null) t = t.getCause()`?

- Một tầng domain như `PaymentRejectedException` có thể chứa cause kỹ thuật nhưng bản thân nó mới là tín hiệu cần map thành lỗi nghiệp vụ.
- `DataAccessException`, `UndeclaredThrowableException`, reflection wrappers và HTTP client exceptions có hợp đồng riêng.
- Log chỉ lỗi dưới cùng sẽ đánh mất việc lỗi đã đi qua asynchronous boundary và các tầng mapping.
- Một cause chain dị thường có thể khiến loop không an toàn; giới hạn depth và kiểm tra self-cause là biện pháp phòng vệ.

**Đừng xóa wrapper khỏi log**. Có thể dùng unwrapped cause để **phân loại** lỗi, nhưng vẫn ghi full `Throwable` ở ranh giới quan sát:

~~~java
try {
    return future.get(5, TimeUnit.SECONDS);
} catch (ExecutionException ex) {
    Throwable cause = unwrapAsyncFailure(ex);
    logFailure("Async execution failed", ex, cause);
    throw translateToDomainError(cause);
}
~~~

Đây là đoạn minh họa; cần triển khai `logFailure`, `translateToDomainError`, `future` và bắt các exception khác của `get(timeout)`. Không lặp kiểu log nguyên stack trace ở nhiều tầng gây nhiễu; mỗi ranh giới nên có trách nhiệm rõ ràng.

### 5.2. Cause, suppressed exceptions và stack trace

Ba dữ liệu này không đồng nghĩa:

- **Cause (`getCause()`)**: Throwable gắn với nguyên nhân trực tiếp của một wrapper hoặc lỗi ở tầng cao.
- **Suppressed (`getSuppressed()`)**: các lỗi bổ sung, ví dụ lỗi khi đóng tài nguyên trong `try-with-resources`; **không** phải cause chain.
- **Stack trace**: call stacks tại nơi các Throwable được tạo/throw; với async, wrapper và nguyên nhân có thể ghi dấu **hai thread/rành giới khác nhau**.

Không thay full exception bằng `logger.error("{}", ex.getMessage())`, vì message thường thiếu type, cause và stack trace. Tránh logging dữ liệu nhạy cảm trong input, URL có token, request body hoặc chi tiết nội bộ cần được che.

## 6. Ví dụ Java 17 độc lập: so sánh get, join, cause và recovery

Ví dụ này **không cần Spring** để kiểm tra semantic chuẩn của JDK. Nó dùng `CompletableFuture.failedFuture(...)` với một lỗi xác định và `ExecutorService.submit(...)` để thấy cả hai nguồn Future đều được bọc khi dùng `get`.

Tạo đúng tệp **`FutureExceptionDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureExceptionDemo {

    public static void main(String[] args) throws Exception {
        IllegalStateException root =
                new IllegalStateException("database unreachable");

        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(root);

        try {
            failed.get();
        } catch (ExecutionException ex) {
            printFailure("get", ex);
        }

        try {
            failed.join();
        } catch (CompletionException ex) {
            printFailure("join", ex);
        }

        Throwable nested = new CompletionException(
                new ExecutionException(root));
        System.out.println("nested root: " +
                unwrap(nested).getMessage());

        String fallback = failed.exceptionally(ex -> "cached").join();
        System.out.println("exceptionally: " + fallback);

        String handled = failed.handle((value, error) ->
                error == null ? value : "recovered").join();
        System.out.println("handle: " + handled);

        CompletableFuture<String> observed =
                failed.whenComplete((value, error) -> {
                    // Quan sát thôi, không thay thế lỗi gốc.
                });
        System.out.println("whenComplete stays failed: " +
                observed.isCompletedExceptionally());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> submitted = pool.submit(() -> {
                throw new IllegalArgumentException("bad request");
            });

            try {
                submitted.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                printFailure("submit", ex);
            }
        } finally {
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void printFailure(String label, Throwable error) {
        Throwable root = unwrap(error);
        System.out.println(label + " wrapper: " +
                error.getClass().getSimpleName());
        System.out.println(label + " root: " +
                root.getClass().getSimpleName() +
                ": " + root.getMessage());
    }

    private static Throwable unwrap(Throwable error) {
        Throwable current = error;
        for (int depth = 0; depth < 32; depth++) {
            if (!(current instanceof ExecutionException)
                    && !(current instanceof CompletionException)) {
                break;
            }

            Throwable cause = current.getCause();
            if (cause == null || cause == current) {
                break;
            }
            current = cause;
        }
        return current;
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac FutureExceptionDemo.java
java FutureExceptionDemo
~~~

**Stdout chính xác** với điều kiện lệnh thực thi bình thường:

~~~text
get wrapper: ExecutionException
get root: IllegalStateException: database unreachable
join wrapper: CompletionException
join root: IllegalStateException: database unreachable
nested root: database unreachable
exceptionally: cached
handle: recovered
whenComplete stays failed: true
submit wrapper: ExecutionException
submit root: IllegalArgumentException: bad request
~~~

**Giải thích từng quan sát:**

1. `failedFuture(root)` tạo một `CompletableFuture` đã hoàn thành lỗi bằng `IllegalStateException`.
2. `get()` ném **`ExecutionException`**; `join()` ném **`CompletionException`**. Hai wrapper khác nhau nhưng helper đều tìm tới lỗi gốc.
3. `new CompletionException(new ExecutionException(root))` mô phỏng hai tầng bao; helper gỡ đúng hai tầng.
4. `exceptionally(...)` tạo một stage **phục hồi** với giá trị `cached`.
5. `handle(...)` được gọi cho cả kết quả thành công lẫn thất bại; ở đây trả `recovered`.
6. `whenComplete(...)` chỉ quan sát; khi callback không ném lỗi, stage trả về vẫn **exceptional** vì upstream đã thất bại.
7. `ExecutorService.submit` nhận một Callable ném `IllegalArgumentException`. `Future.get` báo `ExecutionException`, nguyên nhân là lỗi từ Callable. Dùng `get(timeout)` ở đây để test không chờ vô hạn nếu môi trường bất thường.
8. `finally` shutdown pool do ví dụ tự tạo, không để thread tồn tại ngoài chương trình.

Kết quả được xây dựng bằng exception type/message và các Future hoàn thành xác định, không dựa vào thứ tự thread hoặc thời gian ngẫu nhiên. Chương trình vẫn có thể bị ảnh hưởng nếu JVM không có tài nguyên để tạo worker hoặc bị interrupt bất thường; stdout trên là hợp đồng của đường chạy thành công.

## 7. Trong Spring @Async: lỗi thực thi đi qua proxy như thế nào?

Với Spring, `@Async` ở chế độ proxy mặc định cần:

1. `@EnableAsync` có hiệu lực trong đúng `ApplicationContext`.
2. Service/worker là **bean do Spring quản lý**.
3. Lời gọi method đi qua **Spring proxy**; self-invocation `this.method()` thường không kích hoạt annotation.
4. Có executor phù hợp được chọn, ví dụ bằng `@Async("ioExecutor")`.
5. Method trả kiểu hợp lệ: `void`, `Future<T>` hoặc `CompletableFuture<T>` theo API/version.

Ví dụ method trong service bean:

~~~java
@Async("ioExecutor")
public CompletableFuture<String> fetch(String key) {
    if (key.isBlank()) {
        throw new IllegalArgumentException("blank key");
    }
    return CompletableFuture.completedFuture(loadFromRemote(key));
}
~~~

Đây là **mảnh method minh họa** cần import `@Async`, `CompletableFuture`, `loadFromRemote` và bean `ioExecutor`. Nếu `loadFromRemote` ném exception trong worker, Future trả về cho caller có thể hoàn thành exceptional. `get()` trên Future ấy thường báo `ExecutionException`; `join()` báo `CompletionException`.

**Đừng nhầm lỗi từ Spring proxy với lỗi gốc.** Wrapper vẫn thuộc JDK Future/CompletionStage semantics; business exception của method `fetch` nằm trong cause chain.

### 7.1. @Async void: không có Future cho caller

~~~java
@Async("ioExecutor")
public void refreshIndex() {
    throw new IllegalStateException("index write failed");
}
~~~

Đây là mảnh minh họa. Khi method trả `void`, caller **không có Future để gọi `get` hoặc `join`**, nên exception chạy trên worker không tự động xuất hiện ở caller. Spring có `AsyncUncaughtExceptionHandler` để xử lý những lỗi loại này. Ví dụ cấu hình bên trong một class `@Configuration`:

~~~java
@EnableAsync
@Configuration
class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, args) ->
                System.err.println("Async void error in " +
                        method.getName() + ": " + error);
    }
}
~~~

Đây là **mảnh cấu hình**, cần import `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, `@EnableAsync`, `@Configuration` và chính sách logging production. Nếu ứng dụng có nhiều class cấu hình, sắp xếp để không vô tình khai báo nhiều `AsyncConfigurer` xung đột.

Với nhiệm vụ mà caller cần biết **đã thành công hay chưa**, cân nhắc kiểu `CompletableFuture<T>` và/hoặc job status bền vững. `@Async void` không thể truyền exception trực tiếp trở lại caller chỉ bằng `try/catch` bao quanh lời gọi.

### 7.2. Rejection và lỗi trước khi worker chạy

Một pool bão hòa có thể **không nhận** task. Khi handler ném exception, phía submit có thể thấy `RejectedExecutionException` hoặc `TaskRejectedException` ở **thời điểm gửi**, thay vì `ExecutionException` khi lấy kết quả. Nếu dùng policy `DiscardPolicy` hoặc `DiscardOldestPolicy` bỏ công việc âm thầm, Future có thể không bao giờ hoàn thành; **không có wrapper** để unwrap.

Do đó muốn điều tra “`@Async` bị lỗi” phải xác định lỗi xảy ra ở **submission**, **execution**, **completion-stage callback** hay **waiting**. Cả bốn điểm có khả năng báo lỗi khác nhau.

## 8. Demo Spring Framework: get và join trên cùng loại @Async method

Demo độc lập này dùng **Java 17+, Spring Framework 6.1.14 và Gradle 8.5+**. Nó không cần Spring Boot, servlet container hay database. Worker bean `FailureWorker` cố ý ném một `IllegalStateException` trên executor Spring; caller đọc bằng `get(timeout)`, `join()` và tạo một nhánh recovery.

### 8.1. Cấu trúc tệp

~~~text
spring-async-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncRootCauseDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spring-async-exception-demo'
~~~

**build.gradle**:

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
    mainClass = 'demo.AsyncRootCauseDemo'
}
~~~

**src/main/java/demo/AsyncRootCauseDemo.java**:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncRootCauseDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            FailureWorker worker = context.getBean(FailureWorker.class);

            // Gửi cả hai job trước; caller quan sát lỗi sau.
            CompletableFuture<String> a = worker.load("A");
            CompletableFuture<String> b = worker.load("B");

            try {
                a.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                printFailure("get", ex);
            }

            try {
                b.join();
            } catch (CompletionException ex) {
                printFailure("join", ex);
            }

            CompletableFuture<String> recovered =
                    worker.load("C")
                            .exceptionally(error -> "cached-C");
            System.out.println("fallback: " +
                    recovered.get(5, TimeUnit.SECONDS));
        }
    }

    private static void printFailure(String label, Throwable error) {
        Throwable cause = error;
        for (int depth = 0; depth < 32; depth++) {
            if (!(cause instanceof ExecutionException)
                    && !(cause instanceof CompletionException)) {
                break;
            }
            if (cause.getCause() == null ||
                    cause.getCause() == cause) {
                break;
            }
            cause = cause.getCause();
        }

        System.out.println(label + " wrapper: " +
                error.getClass().getSimpleName());
        System.out.println(label + " root: " +
                cause.getClass().getSimpleName() +
                ": " + cause.getMessage());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("io-");
            return executor;
        }

        @Bean
        public FailureWorker failureWorker() {
            return new FailureWorker();
        }
    }

    public static class FailureWorker {
        @Async("ioExecutor")
        public CompletableFuture<String> load(String key) {
            throw new IllegalStateException("load failed: " + key);
        }
    }
}
~~~

Tại thư mục project, chạy:

~~~bash
gradle run
~~~

Nếu có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

**Các dòng do chương trình tự in** khi executor khởi động và các Future hoàn thành trong thời gian chờ:

~~~text
get wrapper: ExecutionException
get root: IllegalStateException: load failed: A
join wrapper: CompletionException
join root: IllegalStateException: load failed: B
fallback: cached-C
~~~

Spring hoặc Gradle có thể in log khởi động bên ngoài năm dòng trên. Tên thread/độ trễ tùy runtime, nhưng code không in tên worker nên expected stdout không phụ thuộc scheduling.

**Giải thích:** `@EnableAsync` bật hạ tầng async; `FailureWorker` được Spring tạo qua `@Bean` và proxy có thể intercept public method `load`. Caller lấy worker qua context, không tự `new` ở bên ngoài. Khi method ném `IllegalStateException` trên thread executor, Future trả về từ proxy lưu lỗi; `get` và `join` bộc lộ wrapper khác nhau. `exceptionally` xử lý trạng thái exceptional để đưa giá trị fallback. Đó là **quyết định ở tầng caller**, không phải Spring tự chữa lỗi gốc.

## 9. Xử lý lỗi trong chuỗi CompletableFuture

### 9.1. exceptionally: chỉ phục hồi ở nhánh lỗi

~~~java
CompletableFuture<String> safe =
        worker.load("A").exceptionally(error -> {
            Throwable root = unwrapAsyncFailure(error);
            recordFailure(root);
            return "cached-value";
        });
~~~

Đây là mảnh code cần hàm `unwrapAsyncFailure`, `recordFailure` và bean `worker`. Nếu upstream thành công, callback `exceptionally` không được gọi; nếu thất bại, callback chọn fallback. Chọn fallback **không đồng nghĩa dữ liệu gốc đã được xử lý thành công** — cần định nghĩa rõ semantic và trạng thái job.

### 9.2. handle: xử lý cả thành công lẫn thất bại

~~~java
CompletableFuture<Result> result = worker.load("A")
        .handle((value, error) -> {
            if (error != null) {
                return Result.failed(unwrapAsyncFailure(error));
            }
            return Result.success(value);
        });
~~~

Mảnh code này cần định nghĩa kiểu `Result` và helper. `handle` được chạy sau khi stage trước hoàn tất, cho phép chuyển **cả success và failure** thành một kiểu kết quả miền ứng dụng. Nhưng nếu callback `handle` tự ném exception, stage mới vẫn có thể hoàn thành exceptional.

### 9.3. whenComplete: quan sát, không tự chuyển lỗi thành thành công

~~~java
CompletableFuture<String> traced = worker.load("A")
        .whenComplete((value, error) -> {
            if (error != null) {
                logFailure(unwrapAsyncFailure(error));
            }
        });
~~~

Đoạn trên không tự hồi phục lỗi. Khi stage gốc đã thất bại, stage `traced` vẫn hoàn thành lỗi nếu callback chỉ ghi log. Không dùng `whenComplete` như thể nó tương đương `exceptionally`.

### 9.4. thenApply/thenCompose: lỗi lan truyền qua phụ thuộc

~~~java
CompletableFuture<String> output = worker.load("A")
        .thenApply(String::trim)
        .thenApply(String::toUpperCase);
~~~

Nếu `load("A")` thất bại, các callback biến đổi thông thường **không chạy**; future `output` cũng có thể kết thúc exceptional. Không cần từng callback có `try/catch` riêng nếu bạn đã có một ranh giới xử lý lỗi chung phù hợp.

Với `thenCompose`, callback trả Future khác; nếu stage trước thất bại, callback thường không được gọi, lỗi đi qua downstream. Các lỗi của Future do callback trả ra cũng trở thành lỗi của stage kết hợp. Điều này có thể tạo thêm tầng `CompletionException` khi caller `join`.

### 9.5. allOf và nhiều lỗi cùng lúc

~~~java
CompletableFuture<Void> all =
        CompletableFuture.allOf(taskA, taskB, taskC);
~~~

Đây là mảnh code, các Future cần được tạo trước. Khi một hoặc nhiều nhánh hoàn thành lỗi, `all` có thể hoàn thành exceptional; **không xem một cause duy nhất là danh sách toàn bộ lỗi của ba nhánh**. Nếu nghiệp vụ cần báo cáo lỗi từng task, sau khi các task hoàn tất hãy kiểm tra từng Future có kiểm soát, hoặc chuyển từng nhánh thành một `Result` chứa success/failure trước khi tổng hợp.

Đừng dùng `CompletableFuture.allOf(...).join()` ngay giữa dòng thực thi mà không biết các nhánh đã được submit và xử lý thế nào. Nếu cần API bất đồng bộ xuyên tầng, có thể trả future tổng hợp thay vì block caller.

## 10. Timeout, cancellation và interruption không phải ExecutionException

Một ranh giới xử lý lỗi tốt cần phân biệt:

| Tín hiệu | Thường đến từ đâu? | Hành động phù hợp |
| --- | --- | --- |
| `ExecutionException` | `Future.get()` sau khi computation thất bại | Xem cause; map/retry/log theo nguyên nhân |
| `CompletionException` | `CompletableFuture.join()` hoặc stage exception | Xem cause; đừng xem wrapper là lỗi domain |
| `TimeoutException` | `get(timeout)` hoặc nguồn timeout | Phân biệt timeout **chờ** với task thất bại/đã dừng |
| `InterruptedException` | Caller bị interrupt khi đợi trong `get` | Tôn trọng cancellation/shutdown, thường khôi phục interrupt flag |
| `CancellationException` | Future đã bị hủy | Xử lý trạng thái canceled; không coi là lỗi computation thông thường |
| `RejectedExecutionException`/`TaskRejectedException` | Executor từ chối ở submission | Backpressure, phản hồi quá tải, retry có giới hạn hoặc durable queue |

### 10.1. Xử lý get(timeout) có chủ đích

~~~java
try {
    return future.get(5, TimeUnit.SECONDS);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException(ex);
} catch (TimeoutException ex) {
    throw new DownstreamTimeoutException(ex);
} catch (CancellationException ex) {
    throw new OperationCancelledException(ex);
} catch (ExecutionException ex) {
    Throwable failure = unwrapAsyncFailure(ex);
    throw mapToApplicationException(failure);
}
~~~

Đây là **đoạn code minh họa**; `future`, các exception miền ứng dụng và hàm mapping chưa được định nghĩa. Thứ tự catch trên chỉ minh họa chính sách. Khi bắt `InterruptedException`, việc khôi phục interrupt flag thường thích hợp nếu exception không được truyền ra theo contract, để vòng đời thread có cơ hội phản ứng đúng.

**Timeout khi đợi không tự hủy công việc.** `future.cancel(true)` cũng chỉ yêu cầu/cố gắng hủy theo contract/implementation; không thể đảm bảo mọi I/O hoặc external side effect dừng ngay. Với `CompletableFuture`, cancellation là một dạng exceptional completion và không tự điều khiển tất cả tác vụ nguồn đã gửi ở nơi khác.

### 10.2. Có thể dùng orTimeout/completeOnTimeout, nhưng hiểu hậu quả

~~~java
CompletableFuture<String> timed =
        worker.load("A").orTimeout(3, TimeUnit.SECONDS);
~~~

`orTimeout` có thể hoàn thành **exceptional** CompletableFuture nếu chưa xong đúng hạn; `completeOnTimeout` có thể hoàn thành bằng giá trị mặc định. Những API này không bảo đảm computation đang chạy bị interrupt hay database operation tự rollback. Nếu stage `timed` đã thất bại do timeout, `get` và `join` tiếp tục có thể biểu hiện thông qua wrapper, bên trong là `TimeoutException`.

Nếu sử dụng timeout cho cả HTTP request và worker, cần quy định rõ trạng thái nào là timeout của caller, trạng thái nào là timeout của downstream, trạng thái nào là kết quả cuối của job. Không dùng message exception như một mã trạng thái duy nhất.

## 11. Ánh xạ nguyên nhân gốc thành hành vi nghiệp vụ

Khi đã xác định cause thuộc loại gì, tầng service/controller có thể quyết định:

~~~text
Async wrapper
    |
    v
Unwrap ExecutionException / CompletionException
    |
    +-- Validation/domain exception ---> trả lỗi input hoặc trạng thái domain
    |
    +-- Timeout/temporary network -----> retry có giới hạn hoặc 503/504
    |
    +-- Cancellation ------------------> trạng thái cancelled, không retry tùy tiện
    |
    +-- Data integrity/permanent ------> báo lỗi ổn định, không retry mù quáng
    |
    +-- Unknown -----------------------> log đầy đủ, phản hồi lỗi an toàn
~~~

Đây là ví dụ **quy tắc xử lý mang tính thiết kế**, không phải bảng mapping HTTP bắt buộc cho mọi API. Tầng giao thức phải phân biệt exception nội bộ với thông tin được phép trả cho client. Không gửi stack trace, SQL, access token hoặc thông tin bí mật vào HTTP response.

**Không retry mọi `ExecutionException`.** Wrapper không cho biết lỗi có tạm thời hay không. Retry cần xét **nguyên nhân gốc**, tính **idempotent** của thao tác, retry budget, exponential backoff/jitter và giới hạn tải. Một lỗi nghiệp vụ như tham số sai sẽ không tự hết nếu thử lại y nguyên. Một tác vụ đã thực hiện side effect trước khi lỗi có thể tạo duplicate nếu retry không có idempotency key.

Tương tự, không nuốt hết bằng `exceptionally(e -> null)` nếu `null` làm tầng trên hiểu là thành công. Fallback phải có nghĩa rõ ràng (ví dụ cached read hợp lệ) hoặc chuyển thành kiểu `Result.failed(...)`.

## 12. Quan sát lỗi: log, tracing và tính nhất quán

Một lỗi qua async boundary có thể mang:

- **Thread worker**: nơi phát sinh `IllegalStateException`, `SQLException`, v.v.
- **Thread caller**: nơi gọi `get`/`join` và thấy wrapper.
- **Trace/correlation ID**: giúp nối hai hoạt động thuộc một request/job.
- **Job ID**: xác định tác vụ riêng, thời điểm submit, bắt đầu, hoàn thành hoặc thất bại.
- **Executor metadata**: tên pool, queue size, rejection count, active threads và latency.

**Ghi log đầy đủ một lần tại ranh giới chịu trách nhiệm**, ví dụ logger nhận nguyên `Throwable`, thay vì chỉ message. Tùy chiến lược quan sát, có thể bổ sung **unwrapped cause type** vào trường phân loại nhưng giữ full cause chain để điều tra.

Mã giả minh họa:

~~~java
Throwable cause = unwrapAsyncFailure(error);
logger.error("async_job_failed jobId={} causeType={}",
        jobId, cause.getClass().getSimpleName(), error);
~~~

Cần định nghĩa `logger`, `jobId` và helper. Nếu dùng SLF4J, đối số Throwable cuối thường được logger hiểu là stack trace; cách log chi tiết phụ thuộc binding/version. Không log dữ liệu nhạy cảm hoặc input nguyên văn không cần thiết.

**MDC và ThreadLocal không tự truyền qua `@Async`** vì worker có thread khác. Nếu muốn trace/correlation ID trên worker, cần chủ động truyền trong DTO hoặc cấu hình context propagation/`TaskDecorator` phù hợp, đồng thời cleanup để tránh lẫn dữ liệu giữa những task dùng chung thread pool.

### 12.1. Đo trạng thái trước khi quyết định nguyên nhân

Không nên đoán “Future treo vì exception”: có thể task còn chờ trong queue, đang chạy chậm, bị deadlock, hoặc bị handler từ chối/bỏ âm thầm. Một Future chưa hoàn thành **không hề có `ExecutionException` để bóc**. Cần kiểm tra pool saturation, submitted/started/completed/rejected counters, task age, timeout và thread dump khi phù hợp.

Nếu `@Async` không thực sự chạy qua Spring proxy (ví dụ self-invocation hoặc object tự tạo bằng `new`), lỗi có thể ném **đồng bộ ngay tại caller**. Không được suy diễn mọi exception của method có annotation đều đi qua `CompletableFuture`.

## 13. Các anti-pattern phổ biến và cách sửa

| Anti-pattern | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| Chỉ log `ex.getMessage()` của `ExecutionException` | Mất nguyên nhân và stack trace | Log Throwable đầy đủ, đọc `getCause()` khi phân loại |
| `catch (Exception e) { return null; }` | Che lỗi, caller tưởng thành công | Trả fallback hợp lệ hoặc stage failed, log/map rõ |
| `(IOException) ex.getCause()` không kiểm tra kiểu | `ClassCastException` hoặc nhầm wrapper | Unwrap wrapper đã biết, kiểm tra `instanceof` trước khi map |
| `join()` được cho là non-blocking | Vẫn có thể chặn thread | Dùng continuation, chỉ join ở ranh giới cần kết quả |
| Retry mọi `CompletionException` | Không xét nguyên nhân, có thể tạo side effect trùng | Retry theo cause + idempotency + budget |
| Mong `@Async void` ném lỗi về caller | Caller không có Future kết quả | Dùng Future nếu cần giám sát, hoặc AsyncUncaughtExceptionHandler |
| Coi `TimeoutException` từ get là lỗi của worker | Timeout chỉ là giới hạn **chờ** | Theo dõi trạng thái task và hủy/thử lại đúng hợp đồng |
| Nuốt `InterruptedException` rồi tiếp tục | Phá cancellation/shutdown semantics | Khôi phục interrupt flag hoặc propagate phù hợp |
| Chỉ xem cause của `allOf` là toàn bộ lỗi | Có thể bỏ sót các nhánh hỏng khác | Tổng hợp kết quả/lỗi từng nhánh |
| Bỏ Future mà không attach observer | Lỗi nền không ai xử lý | Lưu handle, callback, metrics/job status |
| Dùng `DiscardPolicy` cho task quan trọng | Task mất không báo lỗi, Future có thể pending | Rejection rõ ràng, backpressure hoặc durable queue |
| Gọi `future.get()` trong worker pool một thread và child cần cùng pool | Có thể starvation deadlock | Dùng continuation hoặc thay dependency/pool |

## 14. Checklist kiểm thử và code review

### 14.1. Test tối thiểu

1. **Thành công**: `get`/`join` trả giá trị dự kiến.
2. **Thất bại từ worker**: `get` bắt `ExecutionException`, cause giữ exception mong đợi.
3. **Thất bại qua CompletableFuture**: `join` ném `CompletionException`, cause được unwrap đúng.
4. **Nhiều wrapper**: `CompletionException(new ExecutionException(root))` được helper tháo đúng nhưng không mất lỗi domain.
5. **Fallback**: `exceptionally`/ `handle` trả giá trị theo hợp đồng, `whenComplete` không tự thay thế failure.
6. **Một nhánh thất bại trong allOf**: downstream xử lý exceptional completion, kiểm tra trạng thái từng nhánh khi cần.
7. **Cancellation**: kiểm tra `CancellationException` thay vì `ExecutionException`.
8. **Timeout chờ**: `get(timeout)` ném `TimeoutException` và không mặc định dừng task.
9. **Interruption**: caller bị interrupt có xử lý flag và vòng đời phù hợp.
10. **Spring context**: `@EnableAsync`, worker bean, qualifier và proxy hoạt động; kiểm tra lỗi qua Future từ một bean khác.
11. **@Async void**: handler ghi nhận lỗi, không dựa vào caller catch.
12. **Pool quá tải**: task rejection được quan sát; không nhầm rejection với computation failure.

### 14.2. Review trước production

- [ ] Phân biệt `ExecutionException` và `CompletionException` theo API `get`/`join`.
- [ ] Không unwrap bừa mọi tầng Throwable; giữ full exception chain trong log.
- [ ] Catch riêng `InterruptedException`, `TimeoutException`, `CancellationException` và rejection khi cần.
- [ ] `@Async` được gọi qua bean/proxy của đúng ApplicationContext.
- [ ] Chọn executor bằng qualifier khi có nhiều pool.
- [ ] Không gọi `get()`/`join()` sớm nếu mục tiêu là chồng lấp các tác vụ độc lập.
- [ ] Có boundary xử lý lỗi: fallback, mapping, retry hoặc error result có ngữ nghĩa.
- [ ] Có timeout và chính sách cancellation/cleanup phù hợp.
- [ ] Có metrics cho exception type gốc, queue saturation, rejection và job trạng thái lâu.
- [ ] Với tác vụ bắt buộc, có durability qua job store/outbox/broker thay vì chỉ Future trong memory.

## 15. Câu hỏi tự kiểm tra

1. **`Future.get()` báo `ExecutionException` có chứng minh executor bị lỗi không?** Không. Nó thường là wrapper của lỗi ném trong computation; đọc `getCause()`.
2. **`CompletableFuture.join()` có non-blocking vì ném unchecked exception không?** Không. Nó vẫn có thể chờ kết quả.
3. **Với cùng một `CompletableFuture.failedFuture(root)`, `get` và `join` thường ném gì?** `get` ném `ExecutionException`; `join` ném `CompletionException`, đều liên quan đến root.
4. **`get(timeout)` bị timeout thì worker đã thất bại chưa?** Không nhất thiết. Đây là timeout khi caller đợi; task có thể vẫn chạy.
5. **Future bị cancel có ném `ExecutionException` không?** Thông thường báo `CancellationException`.
6. **Lấy `ex.getCause()` một lần có luôn ra lỗi gốc không?** Không. Có thể còn nhiều wrapper hoặc một tầng domain có ý nghĩa.
7. **Vì sao không nên unwrap mọi `getCause()` tới tận cùng?** Có thể làm mất ngữ nghĩa của exception tầng ứng dụng và bối cảnh truyền lỗi.
8. **`exceptionally` khác `whenComplete` ra sao?** `exceptionally` có thể phục hồi bằng giá trị; `whenComplete` chủ yếu quan sát và không tự biến failure thành success.
9. **`handle` có chạy cả lúc thành công và lỗi không?** Có; callback nhận value/error phù hợp.
10. **`CompletableFuture.allOf` thất bại có cho biết mọi lỗi của mọi task không?** Không; muốn báo cáo tất cả phải ghi nhận từng nhánh.
11. **Với `@Async void`, caller lấy lỗi qua `Future.get` được không?** Không có Future để gọi; cần handler/log/monitoring khác.
12. **Nếu method `@Async` bị tự gọi bằng `this.method()` thì exception có đi qua Future proxy không?** Thường không, vì self-invocation bỏ qua proxy ở mode mặc định.
13. **Tại sao log cả wrapper và cause?** Để biết cả ranh giới async và nguyên nhân kỹ thuật/nghiệp vụ.
14. **Một `CompletionException` có nghĩa nên retry luôn?** Không. Quyết định retry dựa trên nguyên nhân, idempotency và retry budget.

**Ghi nhớ:** `ExecutionException` và `CompletionException` thường là **vỏ bọc của lỗi bất đồng bộ**, không phải nguyên nhân gốc. Biết `get()` và `join()` báo lỗi thế nào, unwrap có kiểm soát, giữ full stack trace và phân biệt timeout/cancellation/rejection giúp xử lý đúng nghiệp vụ trong Java và Spring `@Async`.

### Tài liệu chính thức

- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
