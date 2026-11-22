# ExecutionException và truy nguyên lỗi task trong Java Concurrency

## 1. Vì sao task thất bại nhưng thread gọi không nhận exception ngay?

Khi gọi một phương thức Java đồng bộ, exception có thể đi ngược lên call stack của **chính thread gọi**:

```java
String value = parseData(input); // Có thể ném exception ngay tại đây.
```

Nhưng với `ExecutorService`, task chạy ở **worker thread khác**. Thread nộp công việc và worker không chia sẻ call stack. Nếu task ném exception, exception đó **không tự động nhảy sang** thread đã gọi `submit()`.

Java cung cấp `Future` để giữ **trạng thái hoàn thành** và kết quả của tác vụ. Khi thread khác gọi `Future.get()`, API có thể **bọc lỗi mà task đã ném** trong `ExecutionException`, đưa thông tin lỗi trở lại cho caller.

```text
Thread gọi submit                  Worker thread
------------------                 ------------------
executor.submit(callable)  ───────> callable.call()
          │                             │
          │                         throw IOException
          │                             │
          ▼                             ▼
Future<T>                       Future lưu thất bại
          │                             │
future.get()  <────────────────────────┘
          │
          ▼
throw ExecutionException
       └── getCause() -> IOException gốc
```

**ExecutionException là lớp bọc báo task thực thi thất bại**, không phải tên của mọi lỗi concurrency. Nó khác `InterruptedException` khi thread đang chờ bị ngắt, `TimeoutException` khi chờ quá thời hạn, và `CancellationException` khi future đã bị hủy.

Bài học thuộc **Future & Scheduling**, phạm vi **Java concurrency nói chung**, không phụ thuộc framework.

## 2. Ba vai trò: caller, executor và Future

Có thể chia trách nhiệm như sau:

1. **Caller:** tạo/nộp task; giữ `Future`; quyết định khi nào cần đợi và cách xử lý thành công hoặc thất bại.
2. **Executor:** nhận task và sắp xếp worker thực thi; không nhất thiết trả lỗi task trực tiếp tại `submit()`.
3. **Future:** cho phép theo dõi trạng thái hoàn thành, nhận kết quả khi thành công hoặc truy nguyên lỗi khi thất bại/hủy.

`submit(Callable<T>)` trả `Future<T>`. `submit(Runnable)` trả `Future<?>` mà `get()` bình thường cho `null` nếu task hoàn thành thành công. Riêng `submit(Runnable, T result)` có thể trả một giá trị được caller cung cấp sau khi Runnable hoàn thành bình thường.

### Các ngoại lệ quan trọng của Future.get()

| Trạng thái khi gọi `Future.get()` | Hành vi phổ biến |
| --- | --- |
| Task thành công | Trả giá trị (có thể `null` với Runnable) |
| Task ném exception hoặc error không được xử lý | Ném `ExecutionException`, `getCause()` là lỗi được lưu |
| Task/Future đã bị hủy | Ném `CancellationException` (unchecked) |
| Thread **đang chờ** bị interrupt | Ném `InterruptedException` |
| `get(timeout, unit)` hết thời hạn | Ném `TimeoutException` |
| Task vẫn chạy và không có timeout | `get()` có thể đợi vô hạn |

**Không nhầm:** `Future.get()` không tự gửi interrupt chỉ vì caller đợi lâu. `TimeoutException` cũng không tự hủy task: task có thể tiếp tục chạy sau khi caller ngừng đợi.

Lời gọi `get()` có thể ném `InterruptedException` ngay cả khi **task hoàn toàn bình thường**, vì người bị ngắt là thread đang **chờ kết quả**. Đó không phải bằng chứng worker thất bại.

## 3. Ví dụ Java 17+: truy nguyên IOException bên trong ExecutionException

Tạo tệp `ExecutionExceptionBasicsDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutionExceptionBasicsDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<String> result = executor.submit(() -> {
                throw new IOException("cannot read report.csv");
            });

            try {
                System.out.println(result.get());
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println("wrapper="
                        + e.getClass().getSimpleName());
                System.out.println("cause="
                        + cause.getClass().getSimpleName());
                System.out.println("message=" + cause.getMessage());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac ExecutionExceptionBasicsDemo.java
java ExecutionExceptionBasicsDemo
```

Kết quả khi không có yêu cầu interrupt bên ngoài:

```text
wrapper=ExecutionException
cause=IOException
message=cannot read report.csv
```

Diễn giải:

- `submit()` trả `Future<String>`; lambda là `Callable` vì có kiểu kết quả của task và ném `IOException`.
- Worker thực thi `call()` và ném `IOException`.
- Future ghi lại trạng thái thất bại. Caller gọi `result.get()` thì nhận `ExecutionException`.
- `getCause()` trả `IOException` gốc để caller nhận diện vấn đề đọc file.
- `finally` yêu cầu đóng executor dù `get()` ném hoặc xử lý lỗi; `awaitTermination` kiểm tra có kết thúc trong thời hạn hay không.

**Không chỉ xem `e.getMessage()` của wrapper**. Nội dung hữu ích về domain thường nằm ở `e.getCause()` và toàn bộ cause chain. Trong hệ thống thật, vẫn nên giữ stack trace gốc và thông tin task để tìm dòng code đã gây lỗi.

## 4. `getCause()`, cause chain và nguyên nhân gốc

Một lỗi có thể được bọc nhiều tầng:

```text
ExecutionException
  └── IllegalStateException("processing failed")
        └── IllegalArgumentException("invalid orderId")
```

Thông thường:

- **Wrapper:** exception báo lỗi vượt qua ranh giới bất đồng bộ, chẳng hạn `ExecutionException`.
- **Cause trực tiếp:** throwable mà task ném hoặc throwable được một tầng nghiệp vụ bọc lại.
- **Root cause:** lỗi nằm sâu nhất trong cause chain, nếu có một chuỗi `getCause()` liên tục.
- **Suppressed exceptions:** các lỗi khác được gắn bằng `addSuppressed()`, thường thấy khi tài nguyên `close()` cũng thất bại; chúng **không thuộc cause chain tuyến tính**.

### Ví dụ 2: xem từng tầng của chuỗi lỗi

Tạo tệp `ExecutionCauseChainDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutionCauseChainDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Void> task = executor.submit(() -> {
                try {
                    throw new IllegalArgumentException("invalid orderId");
                } catch (IllegalArgumentException e) {
                    throw new IllegalStateException("processing failed", e);
                }
            });

            try {
                task.get();
            } catch (ExecutionException e) {
                Throwable direct = e.getCause();
                Throwable root = direct.getCause();

                System.out.println("direct="
                        + direct.getClass().getSimpleName());
                System.out.println("direct message=" + direct.getMessage());
                System.out.println("root="
                        + root.getClass().getSimpleName());
                System.out.println("root message=" + root.getMessage());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac ExecutionCauseChainDemo.java
java ExecutionCauseChainDemo
```

Kết quả khi không bị interrupt ngoài ý muốn:

```text
direct=IllegalStateException
direct message=processing failed
root=IllegalArgumentException
root message=invalid orderId
```

Trong ví dụ, `IllegalStateException` là ngữ cảnh nghiệp vụ **gần nhất** do task ném, còn `IllegalArgumentException` là lỗi thấp hơn được nối bằng constructor `new IllegalStateException(message, cause)`.

**Không phải lúc nào “root cause” cũng đủ để quyết định xử lý.** Có khi tầng cao thêm thông tin quan trọng (mã công việc, bước xử lý, điều kiện retry). Đừng bỏ `IllegalStateException("processing failed")` chỉ vì đã tìm được `IllegalArgumentException`.

### Đi theo chuỗi cause một cách an toàn

Một helper minh họa:

```java
static Throwable deepestCause(Throwable throwable) {
    Throwable current = throwable;
    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
```

Đây là **đoạn phương thức minh họa**, không có `main`. Trong code chẩn đoán tổng quát, có thể cần bảo vệ trước chuỗi cause tạo thành vòng bất thường (ví dụ qua throwable tùy chỉnh), tránh vòng lặp vô hạn. `printStackTrace()` vốn có cơ chế trình bày nguyên nhân và suppressed exceptions theo cấu trúc; thường hiệu quả hơn việc tự ghép chỉ root message.

## 5. Giữ stack trace thay vì chỉ in một dòng message

Khi một worker thất bại, muốn truy nguyên cần biết **loại lỗi, vị trí, ngữ cảnh và đường dẫn lời gọi**. Thao tác hữu ích:

```java
try {
    future.get();
} catch (ExecutionException e) {
    Throwable failure = e.getCause();
    logger.error("Task {} failed", taskId, failure);
}
```

Đây là **pseudocode tích hợp logging**, `future`, `taskId` và `logger` được ứng dụng định nghĩa. Một logger phù hợp có thể lưu toàn bộ stack trace của `failure`; còn truyền `e` nguyên vẹn cũng giữ cause chain.

Với Java thuần, có thể dùng:

```java
failure.printStackTrace(System.err);
```

Nhưng output stack trace phụ thuộc tên tệp, dòng code, lambda, JDK và cách biên dịch, nên **không nên bịa output cố định**. Khi muốn demo chính xác, in `getClass().getSimpleName()` và `getMessage()`; khi debug thực tế, giữ **toàn bộ throwable**, không chỉ chuỗi ký tự.

Các gợi ý log:

- Ghi loại task, task ID hoặc correlation ID, thời điểm nộp/chạy, tên worker khi có ích.
- Ghi wrapper và cause chain, đặc biệt lỗi gốc cùng stack trace.
- Dùng mức độ log tương xứng với loại lỗi dự kiến hay bất thường.
- Không log dữ liệu nhạy cảm (token, mật khẩu, nội dung riêng tư) chỉ để có thêm ngữ cảnh.
- Không tự động retry vì thấy một exception mà chưa xét side effect task đã thực hiện.

## 6. `submit()` khác `execute()` trong cách quan sát exception

`ExecutorService` kế thừa `execute(Runnable)` và bổ sung `submit(...)`.

**`submit()`:** trả `Future`. Trong các executor tiêu chuẩn như `ThreadPoolExecutor`, task thường được bọc trong một `RunnableFuture` (ví dụ `FutureTask`) giữ kết quả hoặc throwable. Nếu Runnable/Callable thất bại, exception được lưu để caller lấy ra qua `Future.get()`; lỗi đó không nhất thiết xuất hiện trực tiếp ở `UncaughtExceptionHandler` của worker.

**`execute()`:** không trả Future. Nếu một Runnable ném exception không bắt, worker thread có thể kết thúc bất thường và exception đi qua cơ chế uncaught exception của thread/runtime, tùy executor. Với `ThreadPoolExecutor`, lỗi từ task được truyền ra khỏi `run()` và worker có thể được thay thế nếu pool còn chạy. Không có `Future.get()` để caller tự lấy lỗi.

Bảng so sánh:

| Tiêu chí | `execute(Runnable)` | `submit(Runnable/Callable)` |
| --- | --- | --- |
| Trả về | `void` | `Future<?>` hoặc `Future<T>` |
| Caller lấy kết quả | Không có Future của lời gọi | `get()` |
| Caller truy exception task | Cần logging, handler hoặc giao thức báo lỗi khác | `get()` ném `ExecutionException` |
| Hủy task riêng | Phải có cơ chế/handle khác | `Future.cancel(...)` |
| Rủi ro khi bỏ qua | Task thất bại không được báo tới caller | Future lưu lỗi nhưng **nếu không gọi `get()` thì caller có thể không biết** |

**Không nên nói “submit nuốt exception” theo nghĩa xóa mất lỗi.** Nó **giữ throwable trong Future** và chuyển cho caller qua `get()`. Nếu code nộp rồi bỏ quên `Future`, lỗi dễ trở nên không được quan sát — đó là vấn đề thiết kế giám sát kết quả.

### Phản ví dụ: nộp rồi bỏ Future

```java
executor.submit(() -> {
    throw new IllegalStateException("failed");
});
// Bỏ qua Future: caller không đọc trạng thái task.
```

Đây là đoạn minh họa. Không nên xem “không có exception ở thread caller” là bằng chứng task chạy thành công.

Một thiết kế tốt giữ `Future` ở tầng chịu trách nhiệm kiểm tra outcome, hoặc đặt đường báo lỗi rõ ràng vào callback/channel/monitoring của ứng dụng.

## 7. Ví dụ 3: nhiều Future, không bỏ sót lỗi một task

Một lỗi thường gặp là nộp hàng chục task rồi chỉ gọi `get()` trên một task. Các Future còn lại có thể thất bại mà không được ghi nhận.

Tạo tệp `MultipleTaskFailuresDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MultipleTaskFailuresDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> good = executor.submit(() -> 7);
            Future<Integer> bad = executor.submit(() -> {
                throw new IllegalStateException("bad order");
            });

            List<Future<Integer>> futures = List.of(good, bad);
            for (int i = 0; i < futures.size(); i++) {
                try {
                    System.out.println("task " + i
                            + " result=" + futures.get(i).get());
                } catch (ExecutionException e) {
                    Throwable cause = e.getCause();
                    System.out.println("task " + i + " failed="
                            + cause.getClass().getSimpleName()
                            + ": " + cause.getMessage());
                }
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac MultipleTaskFailuresDemo.java
java MultipleTaskFailuresDemo
```

Kết quả khi không bị interrupt ngoài ý muốn:

```text
task 0 result=7
task 1 failed=IllegalStateException: bad order
```

Thứ tự hoàn thành trong worker **không nhất thiết giống thứ tự nộp**, nhưng caller duyệt futures theo index `0` rồi `1`; vì vậy thứ tự dòng log được xác định. `get()` đợi từng Future hoàn thành rồi đọc result/failure.

**Giới hạn của cách duyệt tuần tự:** nếu Future đầu chậm, caller có thể chờ nó dù một Future sau đã thất bại. Khi cần xử lý kết quả **theo thứ tự hoàn thành** chứ không theo thứ tự nộp, có thể dùng `ExecutorCompletionService`.

## 8. `ExecutorCompletionService` để quan sát kết quả theo thứ tự hoàn thành

`ExecutorCompletionService<V>` nhận các `Callable<V>` và đưa Future đã hoàn thành vào một completion queue. Caller gọi `take()` để nhận Future của task **đã kết thúc** (thành công, thất bại hoặc bị hủy) rồi `get()` để phân biệt outcome.

Mẫu minh họa:

```java
ExecutorCompletionService<String> completed =
        new ExecutorCompletionService<>(executor);

completed.submit(() -> fetchA());
completed.submit(() -> fetchB());

for (int i = 0; i < 2; i++) {
    Future<String> future = completed.take();
    try {
        String value = future.get();
        consume(value);
    } catch (ExecutionException e) {
        reportFailure(e.getCause());
    }
}
```

Đây là đoạn minh họa trong ngữ cảnh có import `java.util.concurrent.*` và định nghĩa `executor`, `fetchA`, `fetchB`, `consume` và `reportFailure`. Thứ tự nhận có thể thay đổi giữa các lần chạy, nên không in stdout cố định.

Ưu điểm là một task nhanh không bị việc caller chờ một task chậm **đứng trước trong danh sách** cản việc quan sát. Tuy nhiên, code vẫn phải:

- Biết số lượng task đã nộp hoặc có protocol dừng.
- Xử lý cả `CancellationException` và `InterruptedException` phù hợp.
- Có chính sách cancel các task còn lại nếu lỗi nghiêm trọng.
- Quản lý vòng đời executor.
- Không để completion queue/tập Future tích lũy vô hạn nếu producer nhanh hơn consumer.

`ExecutorCompletionService` giúp **thu thập outcome**, không tự biến exception task thành kết quả thành công.

## 9. TimeoutException, InterruptedException và CancellationException khác ExecutionException

Một trong những sai lầm gây nhầm lẫn chẩn đoán nhất là gom mọi failure của `get()` thành “task throw exception”.

### `TimeoutException`

`future.get(100, TimeUnit.MILLISECONDS)` ném `TimeoutException` nếu thời hạn chờ hết mà Future chưa hoàn tất. Điều đó không có nghĩa task bị lỗi hay đã bị hủy. Task có thể tiếp tục sau timeout.

### `InterruptedException`

Thread **đang đợi `get()`** bị interrupt. Task có thể vẫn chạy bình thường. Nếu không thể propagate, hãy khôi phục cờ và rời workflow ở điểm an toàn. Không nhầm ngắt thread caller với exception gốc do worker ném.

### `CancellationException`

Future đã bị hủy, `get()` ném `CancellationException`. Một task đã bắt đầu có thể vẫn đang cleanup hoặc vẫn chạy nếu không hợp tác với interrupt; `isCancelled()` không tự chứng minh mọi việc dọn dẹp đã hoàn tất.

### `ExecutionException`

Task hoàn thành bất thường vì ném `Throwable` trong quá trình thực thi. `getCause()` chứa lỗi task đã ném (hoặc lỗi được tầng task bọc lại). Không nên xử lý theo kiểu timeout hoặc cancel nếu không có căn cứ.

### Bảng gợi ý phản ứng

| Exception từ `get()` | Ý nghĩa | Hướng xử lý hợp lý |
| --- | --- | --- |
| `ExecutionException` | Task thất bại | Truy nguyên `getCause()`, log stack trace, phân loại retry/fail |
| `TimeoutException` | Chờ kết quả quá lâu | Quyết định chờ thêm, cancel hoặc trả timeout cho caller |
| `InterruptedException` | Caller đang chờ bị ngắt | Propagate hoặc khôi phục interrupt, dọn workflow |
| `CancellationException` | Future bị cancel | Xác nhận trạng thái hủy, xử lý cleanup/outcome nếu cần |

## 10. Ví dụ 4: hết thời gian chờ không đồng nghĩa task thất bại

Tạo tệp `FutureTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> task = executor.submit(() -> {
                started.countDown();
                release.await();
                return "OK";
            });

            started.await();
            try {
                task.get(50, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("caller timed out");
            }

            release.countDown();
            System.out.println("later result=" + task.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Kết quả khi không có interrupt từ bên ngoài:

```text
caller timed out
later result=OK
```

Lý do kết quả xác định:

- Task gửi `started` rồi đợi `release`, nên **chưa thể hoàn tất** khi caller thử `get(50ms)`.
- Timeout làm `get` ném exception **trong caller**, nhưng **không hủy** task.
- Main mở `release`; task tiếp tục và trả `"OK"`.
- Lần `get()` sau nhận kết quả thành công.

`finally` mở `release` cả khi có exception, tránh worker bị kẹt do caller thoát sớm. `shutdownNow()` trong ví dụ chỉ để dọn executor; trong hệ thống cần graceful shutdown có thể dùng `shutdown()` rồi fallback theo chính sách riêng.

## 11. `Future.get()` có bảo đảm bộ nhớ gì?

`Future` không chỉ lưu kết quả. API Java concurrency có quy tắc memory consistency quan trọng: **các hành động do asynchronous computation thực hiện xảy ra trước (happens-before) các hành động sau khi thread khác lấy kết quả qua `Future.get()`** theo hợp đồng Future.

Ví dụ nếu task ghi một object kết quả trước khi hoàn thành, caller sau khi `get()` trả về thành công có quan hệ bộ nhớ để nhìn thấy những ghi được công bố qua đường này.

Nhưng tránh suy rộng:

- `get()` không tự làm một object mutable tiếp tục bị nhiều thread sửa trở nên thread-safe.
- `get()` không biến hai lần đọc state từ hai phiên bản khác nhau thành một atomic snapshot.
- Nếu task thất bại giữa nhiều cập nhật không có transaction, `ExecutionException` không rollback các cập nhật đã xảy ra.
- Nếu caller không đợi/get và đọc shared state riêng theo đường thiếu đồng bộ, cần giao thức memory visibility khác.

Với các thiết kế mới, ưu tiên tạo immutable result/DTO hoàn chỉnh trong task rồi trả qua Future. Reader không sửa result và không để worker tiếp tục sửa result sau khi trả.

## 12. `CompletableFuture`: get() và join() bọc lỗi khác nhau

`CompletableFuture<T>` vừa là `Future<T>` vừa hỗ trợ composition bất đồng bộ. Hai phương thức chờ phổ biến:

- `future.get()`: khai báo checked exceptions `InterruptedException` và `ExecutionException` (khi computation thất bại).
- `future.join()`: không khai báo checked exception; khi completion thất bại thường ném **`CompletionException`** (unchecked).
- Nếu Future bị hủy, `get()` và `join()` có thể ném `CancellationException` trực tiếp.
- Các callback như `exceptionally`, `handle`, `whenComplete` có thể xử lý hoặc quan sát thất bại mà không gọi `get` tại mỗi tầng.

Lỗi bên trong `CompletionException` cũng thường nằm tại `getCause()`. Trong những chain phức tạp, `CompletionException`/`ExecutionException` có thể được bọc ở nhiều tầng; đừng giả định cause chỉ có đúng một cấp.

### Ví dụ 5: cùng một lỗi qua get và join

Tạo tệp `CompletableFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class CompletableFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<Integer> future = new CompletableFuture<>();
        future.completeExceptionally(
                new IllegalArgumentException("bad input"));

        try {
            future.get();
        } catch (ExecutionException e) {
            System.out.println("get wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("get cause="
                    + e.getCause().getClass().getSimpleName());
        }

        try {
            future.join();
        } catch (CompletionException e) {
            System.out.println("join wrapper="
                    + e.getClass().getSimpleName());
            System.out.println("join cause="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac CompletableFailureDemo.java
java CompletableFailureDemo
```

Kết quả:

```text
get wrapper=ExecutionException
get cause=IllegalArgumentException
join wrapper=CompletionException
join cause=IllegalArgumentException
```

Không có thread race trong ví dụ vì Future đã được hoàn thành exceptionally trước khi gọi hai phương thức. Ví dụ chỉ minh họa **hai loại wrapper** của API chờ khác nhau.

Với các stage asynchronous phức tạp, lỗi có thể được truyền qua `CompletionException` ở giữa chain, và `get()` vẫn bọc theo contract của Future. Cách truy nguyên là xem **cause chain đầy đủ**, không cứng nhắc kỳ vọng một lớp bọc duy nhất.

## 13. Dùng exceptionally, handle, whenComplete đúng mục đích

Khi dùng `CompletableFuture`, có thể xử lý lỗi bằng pipeline thay vì đợi và catch tại mọi nơi.

```java
CompletableFuture<Integer> recovered = operation
        .exceptionally(error -> {
            report(error);
            return 0;
        });
```

Đây là đoạn minh họa, `operation` là `CompletableFuture<Integer>` và `report` do ứng dụng định nghĩa. `exceptionally` có thể **biến một completion thất bại thành kết quả mặc định**. Cách này chỉ phù hợp khi fallback `0` là hợp đồng nghiệp vụ hợp lệ — nếu không, sẽ che lỗi và tạo dữ liệu sai.

`handle((value, error) -> ...)` nhận cả trạng thái thành công và thất bại để tạo một kết quả mới. `whenComplete((value, error) -> ...)` chủ yếu dùng để **quan sát** outcome và thường giữ nguyên kết quả/exception ban đầu nếu callback không tự ném lỗi, không được hiểu là cơ chế recovery mặc định.

### Ví dụ 6: phân loại lỗi rồi fallback có chủ đích

Tạo tệp `CompletableRecoveryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class CompletableRecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        source.completeExceptionally(
                new IllegalArgumentException("invalid quantity"));

        int result = source.exceptionally(error -> {
            Throwable cause = error.getCause() != null
                    ? error.getCause() : error;
            System.out.println("handled="
                    + cause.getClass().getSimpleName());
            return -1;
        }).join();

        System.out.println("result=" + result);
    }
}
```

```bash
javac CompletableRecoveryDemo.java
java CompletableRecoveryDemo
```

Kết quả:

```text
handled=IllegalArgumentException
result=-1
```

`-1` chỉ là **fallback minh họa**, không phải lời khuyên dùng `-1` cho mọi lỗi. Một hệ thống thật có thể trả một kiểu `Result<T>` chứa success/error, propagate throwable hoặc retry theo chính sách. Quan trọng là đừng gọi recovery một cách mù quáng rồi bỏ qua failure gốc.

### Cẩn thận khi dùng exceptionally với side effect

Callback phục hồi có thể chạy trên thread khác hoặc trong thread gọi completion, tùy cách stage được xây dựng. Nếu callback ghi log, ghi dữ liệu shared hoặc gọi API khác, vẫn cần hiểu thread safety của thao tác đó. `CompletableFuture` không loại trừ yêu cầu đồng bộ trên các object mutable ngoài nó.

## 14. ScheduledExecutorService: lỗi trong tác vụ định kỳ

`ScheduledExecutorService` cũng có `ScheduledFuture<?>`. Với tác vụ được lên lịch một lần, `future.get()` có thể trả kết quả hoặc `ExecutionException` nếu task ném lỗi.

Đối với tác vụ định kỳ bằng `scheduleAtFixedRate` hoặc `scheduleWithFixedDelay`, có điểm khác biệt rất quan trọng:

> Nếu một lần chạy của periodic task ném exception không được xử lý, các lần chạy tiếp theo của **cùng scheduled task** bị ngăn theo hợp đồng `ScheduledThreadPoolExecutor`/`ScheduledExecutorService`. Future của periodic task có thể hoàn thành bất thường.

Vì một periodic task bình thường có thể chạy lặp cho đến khi bị hủy, `get()` trên future của nó thường **không trả về thành công** khi chuỗi lặp vẫn đang hoạt động. Nó có thể hoàn thành bất thường do exception hoặc hủy.

### Ví dụ 7: truy nguyên lỗi periodic task

Tạo tệp `ScheduledTaskFailureDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ScheduledTaskFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicInteger runs = new AtomicInteger();

        try {
            ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
                    () -> {
                        int n = runs.incrementAndGet();
                        throw new IllegalStateException("failed at run " + n);
                    },
                    0, 1, TimeUnit.SECONDS);

            try {
                future.get();
            } catch (ExecutionException e) {
                System.out.println("cause="
                        + e.getCause().getClass().getSimpleName());
                System.out.println("message=" + e.getCause().getMessage());
            }

            System.out.println("runs=" + runs.get());
        } finally {
            scheduler.shutdownNow();
            scheduler.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac ScheduledTaskFailureDemo.java
java ScheduledTaskFailureDemo
```

Kết quả khi không có interrupt ngoài ý muốn:

```text
cause=IllegalStateException
message=failed at run 1
runs=1
```

Lần chạy đầu tăng `runs` thành `1` rồi ném `IllegalStateException`; periodic future hoàn thành thất bại, các lượt tiếp theo không được tiếp tục. Caller gọi `get()` nhận `ExecutionException`, truy nguyên qua `getCause()`.

**Rủi ro thường gặp:** một scheduled task bị lỗi có thể **ngừng chạy định kỳ** trong khi những thành phần còn lại của ứng dụng vẫn sống. Nếu không giữ `ScheduledFuture` hoặc có đường báo lỗi, hệ thống có thể âm thầm ngừng công việc theo lịch.

Nếu muốn một task tiếp tục sau một lỗi nghiệp vụ có thể phục hồi, task có thể **bắt và xử lý chính lỗi đó** ở ranh giới mỗi lượt. Nhưng tuyệt đối không nuốt mọi `Throwable` vô điều kiện: lỗi nghiêm trọng, trạng thái không hợp lệ hoặc yêu cầu shutdown có thể đòi dừng, báo lỗi hoặc khởi động lại thành phần theo chính sách.

## 15. invokeAll và invokeAny: lỗi nằm ở đâu?

`ExecutorService.invokeAll(tasks)` thường trả về một danh sách `Future` tương ứng cho các callable sau khi chúng hoàn tất theo hợp đồng. **Trả về danh sách không có nghĩa mọi callable thành công**. Cần duyệt và gọi `get()` trên từng Future để kiểm tra lỗi.

```java
List<Future<Integer>> futures = executor.invokeAll(tasks);
for (Future<Integer> future : futures) {
    try {
        consume(future.get());
    } catch (ExecutionException e) {
        reportFailure(e.getCause());
    }
}
```

Đây là đoạn minh họa có import `java.util.concurrent.*` và `java.util.List`; `tasks`, `consume`, `reportFailure` là thành phần của ứng dụng.

Với `invokeAll(timeout, unit)`, các task chưa hoàn thành khi hết hạn có thể bị cancel theo contract; `get()` của chúng có thể ném `CancellationException`, **không nhất thiết là `ExecutionException`**.

`invokeAny(tasks)` có mục tiêu khác: trả kết quả của **một task hoàn thành thành công**. Nếu không có task nào hoàn thành thành công (và không bị các tình huống interrupt/timeout khác chi phối), nó có thể ném `ExecutionException`. Việc một task trong nhóm thất bại **không nhất thiết làm `invokeAny` thất bại** nếu một task khác thành công.

Không nhầm rằng `invokeAll` = “mọi kết quả đều thành công” hoặc `invokeAny` = “kết quả task hoàn thành đầu tiên bất kể thất bại”. Luôn đọc hợp đồng từng API.

## 16. Exception của task có thể là RuntimeException, checked Exception hoặc Error

Một `Callable<T>` khai báo `T call() throws Exception`, nên có thể ném checked exception như `IOException`. Một `Runnable` không được khai báo ném checked exception từ `run()`, nhưng vẫn có thể ném `RuntimeException` hoặc `Error` không bắt.

Khi được nộp qua `submit()` và task thất bại, `ExecutionException.getCause()` có thể là:

- `IOException` do `Callable` ném.
- `IllegalArgumentException`, `IllegalStateException`, `NullPointerException` hoặc một runtime exception khác.
- `Error` như `AssertionError`, `OutOfMemoryError` hoặc những lỗi nghiêm trọng khác.

Không nên viết `catch (Exception e)` rồi mặc định mọi lỗi đều an toàn để retry. `Error` thường báo một vấn đề nghiêm trọng cần xử lý ở mức vận hành hơn là “thử lại vài lần”. `ExecutionException` là checked exception, nhưng **cause của nó là `Throwable`**; code phân loại cần biết rằng nó có thể không phải subclass của `Exception`.

Không bịa quy tắc rằng mọi `Error` bắt buộc làm JVM chết ngay: `FutureTask` có thể ghi lại `Error` như outcome của task. Tuy vậy, việc tiếp tục ứng dụng sau lỗi nghiêm trọng có an toàn hay không tùy nguyên nhân cụ thể và trạng thái JVM.

## 17. Truy nguyên lỗi mà không làm mất ngữ cảnh

Một chiến lược tốt là phân loại dựa trên **cause** và giữ **wrapper/context** trong log hoặc exception của tầng cao:

```java
try {
    return future.get();
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    throw new TaskFailedException(taskId, cause);
}
```

Đây là đoạn minh họa, `TaskFailedException` và `taskId` do ứng dụng định nghĩa. Một exception mới có cause gốc giúp tầng trên có thêm task ID mà không làm mất đường truy nguyên.

Khi viết wrapper của riêng mình:

```java
throw new IllegalStateException("load config failed", original);
```

là tốt hơn:

```java
throw new IllegalStateException("load config failed");
```

nếu muốn giữ lỗi nguyên nhân. Đoạn thứ hai làm mất cause chain trừ khi có cơ chế khác lưu lại.

Không nên chỉ lấy `cause.getMessage()` rồi xây một exception không có cause. Message không đủ phân biệt các loại lỗi và không giữ stack trace. Với các lỗi đa tầng, giữ cả suppressed exceptions khi ghi log đầy đủ.

### Có nên unwrap rồi ném lại cause?

Có khi API của tầng trên muốn ném lại đúng `IOException` hoặc một exception cụ thể. Nhưng `ExecutionException.getCause()` có kiểu `Throwable`; không thể ném tùy tiện ở method chỉ khai báo checked exceptions hạn chế. Hãy **phân loại** có chủ đích hoặc dùng wrapper domain có cause:

```java
Throwable cause = e.getCause();
if (cause instanceof java.io.IOException io) {
    throw io;
}
throw new IllegalStateException("task failed", cause);
```

Đây là đoạn minh họa bên trong method có thể khai báo `throws IOException`; `e` là `ExecutionException` đã bắt. Pattern matching `instanceof` được hỗ trợ trên Java 17.

Đừng catch mọi `Throwable` rồi biến thành một kết quả “OK” hoặc lặp lại vô hạn. Các lỗi như `OutOfMemoryError` có thể làm quá trình recovery không đáng tin.

## 18. Phân loại lỗi để retry an toàn

Một task thất bại không đồng nghĩa retry luôn đúng. Hãy xem **tính lặp lại được** và mức độ thành công một phần:

| Loại tình huống | Retry ngay có hợp lý? | Cần kiểm tra |
| --- | --- | --- |
| Lỗi mạng tạm thời khi đọc một tài nguyên | Có thể, với giới hạn/backoff | Timeout, idempotency, tài nguyên còn hợp lệ |
| Dữ liệu input sai định dạng | Thường không | Validation, trả lỗi rõ |
| Ghi database thất bại giữa nhiều bước | Chỉ khi có transaction/reconciliation | Commit đã xảy ra phần nào chưa? |
| Task bị cancel | Thường không retry mù quáng | Chủ thể hủy, lý do hủy |
| Caller `get(timeout)` hết hạn | Không suy ra worker thất bại | Task còn chạy? Có nên cancel không? |
| JVM `Error` nghiêm trọng | Thường cần cơ chế vận hành riêng | Trạng thái process/tài nguyên còn an toàn không? |

Ví dụ một task gọi API thanh toán, API đã commit nhưng phản hồi bị mất; worker ném timeout exception và Future trả `ExecutionException`. Nếu retry không có idempotency, có thể thanh toán hai lần. Vì vậy **cause chain là dữ liệu chẩn đoán**, không thay thế kiểm tra trạng thái giao dịch.

Nên áp dụng giới hạn số lần thử, backoff, deadline, circuit breaker khi phù hợp và quy tắc không thực thi side effect hai lần.

## 19. Xử lý InterruptedException khi chờ Future

Nếu thread caller bị interrupt trong `Future.get()`, phương thức có thể ném `InterruptedException` và bỏ chờ. Trong nhiều API interruptible, cờ interrupt bị xóa khi exception được ném; xử lý hợp lệ thường là:

**Truyền lên nếu API cho phép:**

```java
String read(Future<String> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
```

**Hoặc khôi phục cờ rồi kết thúc đường chờ:**

```java
try {
    String value = future.get();
    consume(value);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException e) {
    report(e.getCause());
}
```

Đây là hai đoạn minh họa; `consume`, `report` do ứng dụng định nghĩa. `InterruptedException` nói về **thread caller**, không mặc nhiên nói task đã lỗi. Tùy chính sách, caller có thể gọi `future.cancel(true)` để yêu cầu worker dừng, nhưng phải hiểu interrupt worker là best-effort.

**Không nuốt tín hiệu:**

```java
try {
    future.get();
} catch (InterruptedException ignored) {
    // Bỏ qua rồi lặp lại vô hạn: mất khả năng hủy.
}
```

Đây là phản ví dụ. Nếu cần tiếp tục chờ dù bị interrupt, đó phải là quyết định có chủ đích, có deadline và khôi phục cờ khi thoát. Đặc biệt khi ứng dụng shutdown, bỏ qua interrupt làm worker/caller dễ bị treo.

## 20. Hủy Future và cleanup của task

`Future.cancel(true)` có thể yêu cầu ngắt task đang chạy. Sau khi Future được đánh dấu canceled, `future.get()` ném `CancellationException` thay vì `ExecutionException` cho nhánh đó. Tuy vậy:

- Task có thể chưa bắt đầu: cancel ngăn nó chạy.
- Task đang chạy: yêu cầu interrupt được gửi nếu implementation hỗ trợ; task có thể hợp tác và dừng.
- Task bỏ qua interrupt: code có thể tiếp tục chạy sau khi Future đã canceled.
- Task có `finally` giải phóng file/lock/socket: Future canceled **không chứng minh finally đã chạy xong**.

Nếu cần biết cleanup thực tế đã hoàn tất, hãy có tín hiệu riêng như `CountDownLatch` trong `finally` hoặc đợi vòng đời executor theo hợp đồng. `Future.get()` sau cancel có thể ném `CancellationException` ngay, nên không phải một “join cleanup” đáng tin cho task đó.

Điều tương tự xảy ra khi `ExecutorService.shutdownNow()`: nó là yêu cầu dừng best-effort, không biến một tác vụ tùy ý thành trạng thái kết thúc an toàn ngay lập tức.

## 21. Quan sát exception ở thời điểm phù hợp

Có ba thời điểm khác nhau:

1. **Nộp task (`submit`):** task có thể chưa chạy; `submit()` thường chỉ trả Future. Lỗi do *không nhận task* như `RejectedExecutionException` có thể xảy ra ngay tại thời điểm nộp, **không phải một `ExecutionException` được bọc bên trong Future**.
2. **Thực thi task (worker):** task có thể thành công, fail hoặc bị cancel; trạng thái được ghi nhận bởi Future/handler.
3. **Quan sát kết quả (`get`/callback):** caller nhận outcome hoặc exception khi quyết định quan sát.

Điều này giải thích vì sao:

```java
Future<Integer> f = executor.submit(() -> 1 / 0);
// submit() có thể trả Future bình thường.
f.get(); // ExecutionException chứa ArithmeticException.
```

Đây là đoạn minh họa, `executor` đã được tạo và caller xử lý checked exceptions. Nó không có nghĩa exception “xảy ra lúc get” trong worker: lỗi toán học xảy ra lúc task thực thi, còn `get()` là **thời điểm lỗi được báo lại cho caller**.

### Khi nào cần log tại worker?

Với các task fire-and-forget, nếu không ai giữ Future, phải có cơ chế chủ động báo failure: log trong task boundary, callback, supervisor hoặc đường kết quả tập trung. Không log cùng một Throwable nhiều lần ở mọi tầng rồi gây nhiễu. Có thể lựa chọn một tầng sở hữu trách nhiệm báo lỗi, lưu nguyên cause chain và correlation ID.

## 22. Lỗi trong callback cũng là một lỗi task khác

Với `CompletableFuture`, một stage có thể thành công nhưng callback xử lý kết quả lại ném lỗi:

```java
CompletableFuture<Integer> mapped =
        CompletableFuture.completedFuture(3)
                .thenApply(value -> {
                    throw new IllegalStateException("mapping failed");
                });
```

Đây là đoạn minh họa. Future nguồn thành công với giá trị `3`, nhưng stage `mapped` thất bại. Nếu chỉ kiểm tra Future nguồn, bạn sẽ **không thấy lỗi của stage tiếp theo**. Mỗi stage tạo một completion/outcome mới.

Một chuỗi stage có thể có nhiều tầng wrapper, nên hãy ghi:

- Stage nào thất bại, tên bước và key dữ liệu (không chứa bí mật).
- Cause và stack trace tại bước đó.
- Chỗ nào tạo fallback (`exceptionally`) và chỗ nào còn propagate lỗi.
- Completion cuối cùng mà caller thực sự đợi là stage nào.

`whenComplete` được dùng để quan sát outcome nhưng callback cũng có thể ném exception, làm trạng thái downstream khác đi theo hợp đồng. Đừng tự cho callback “chỉ log” là không bao giờ ảnh hưởng kết quả nếu nó có thể ném.

## 23. Các lỗi thường gặp khi xử lý ExecutionException

### Lỗi 1 — Chỉ catch ExecutionException mà bỏ qua nguyên nhân

```java
catch (ExecutionException e) {
    System.out.println("failed");
}
```

Làm mất ngữ cảnh chẩn đoán. Nên xem `e.getCause()` và lưu stack trace phù hợp.

### Lỗi 2 — Bắt rồi trả kết quả mặc định vô điều kiện

Một lỗi dữ liệu nghiêm trọng có thể bị biến thành số `0` hoặc danh sách rỗng mà caller tưởng hợp lệ. Fallback phải theo **hợp đồng nghiệp vụ**, không phải cách né exception.

### Lỗi 3 — Gọi submit rồi quên Future

Future giữ failure; nếu không đọc, caller có thể không thấy lỗi. Cần người chịu trách nhiệm thu thập kết quả hoặc cơ chế supervisor/log.

### Lỗi 4 — Nhầm TimeoutException với ExecutionException

Timeout nói rằng caller đợi quá hạn, **không** chứng minh worker đã thất bại. Nếu cần, kiểm tra `isDone()`, quyết định cancel và truy outcome khi task thực sự hoàn thành.

### Lỗi 5 — Nhầm CancellationException với lỗi gốc của task

Future canceled có ngữ nghĩa riêng; `get()` ném `CancellationException`. Không tự báo rằng worker đã ném một exception nghiệp vụ nào đó.

### Lỗi 6 — Nuốt InterruptedException

Caller bị interrupt khi chờ mà vẫn lặp `get()` vô hạn có thể làm shutdown kẹt. Propagate hoặc khôi phục cờ và thoát ở điểm an toàn.

### Lỗi 7 — Gọi Future.get() trong pool một worker để chờ task con cùng pool

Nếu worker duy nhất của single-thread executor nộp một task con vào chính pool rồi đợi `get()`, task con không có worker để chạy: **thread-starvation deadlock**. ExecutionException không cứu được vòng chờ. Tránh phụ thuộc vòng, dùng kiến trúc task khác hoặc executor có khả năng thực thi tương ứng.

### Lỗi 8 — Tưởng `execute` và `submit` có cùng cơ chế báo exception

`submit` ghi lỗi vào Future; `execute` không trả Future. Nếu dựa vào `UncaughtExceptionHandler` để thấy lỗi của mọi task submit, có thể bỏ sót.

### Lỗi 9 — Log message nhưng không giữ cause

Một câu `e.getMessage()` không đủ để thấy chỗ xảy ra hoặc lỗi bị bọc. Log throwable có stack trace và cause, cân nhắc suppressed exceptions.

### Lỗi 10 — Retry task có side effect mà không kiểm tra commit

Task đã có thể ghi database/gửi message trước khi ném exception. Retry mù quáng dễ tạo tác dụng phụ trùng lặp.

### Lỗi 11 — Không quan sát lỗi của scheduled task lặp lại

Một lần chạy periodic task ném exception có thể khiến các lần sau bị ngăn. Nếu không giữ `ScheduledFuture` hoặc có giám sát, lịch chạy có thể dừng mà không ai nhận ra.

## 24. Checklist truy nguyên khi task bất đồng bộ thất bại

Khi nhận `ExecutionException` hoặc lỗi một stage của `CompletableFuture`, hãy kiểm tra:

1. **Tên task và ID:** task nào, input/correlation nào, worker nào thực thi?
2. **API nộp:** `submit`, `execute`, `schedule`, `invokeAll` hay CompletableFuture stage nào?
3. **API chờ:** `get()`, `get(timeout)`, `join()`, callback? Wrapper có thể khác.
4. **Loại outcome:** task thất bại (`ExecutionException`/`CompletionException`), caller bị interrupt, timeout hay canceled?
5. **Cause trực tiếp:** `getCause()` là kiểu gì? Message gì?
6. **Cause chain:** tầng nào tạo wrapper, tầng nào thêm ngữ cảnh, root cause nào thực sự hữu ích?
7. **Suppressed errors:** có lỗi cleanup thứ cấp không?
8. **Stack trace:** lỗi bắt đầu tại phương thức nào? Đường gọi worker và stage liên quan?
9. **Side effect:** task đã sửa state hoặc resource nào trước khi fail? Có thể retry an toàn không?
10. **Giám sát:** ai giữ Future, ai ghi log failure, có metric theo loại lỗi không?
11. **Lifecycle:** executor/scheduler còn sống, đã shutdown hay task định kỳ ngừng chạy?
12. **Chính sách:** propagate, fallback, retry, cancel các task còn lại hoặc chuyển thành domain error?

Bản chất của `ExecutionException` là chuyển lỗi qua ranh giới bất đồng bộ. **Chẩn đoán đúng** còn cần biết task được nộp khi nào, ở đâu và lỗi đã ảnh hưởng tới trạng thái nào.

## 25. Tự kiểm tra kiến thức

**Câu 1.** Một `Callable` ném `IOException`; thread caller gọi `future.get()`. Loại exception caller nhận thường là gì?

**Đáp án:** `ExecutionException`; `getCause()` là `IOException` do task ném.

**Câu 2.** Nếu chỉ gọi `executor.submit(task)` mà không giữ Future hoặc quan sát outcome, có thể bỏ sót lỗi không?

**Đáp án:** Có. Lỗi được giữ trong Future của task nhưng caller không tự nhận exception tại `submit()`.

**Câu 3.** `future.get(100, MILLISECONDS)` ném `TimeoutException` có nghĩa task chắc chắn đã thất bại không?

**Đáp án:** Không. Task có thể còn đang chạy và hoàn thành sau đó.

**Câu 4.** `future.get()` ném `InterruptedException` là lỗi do task ném hay do thread chờ?

**Đáp án:** Đó là tín hiệu **thread gọi `get()` bị interrupt**. Không tự suy ra task đã thất bại.

**Câu 5.** Khi Future bị hủy, `get()` thường ném exception nào?

**Đáp án:** `CancellationException`, một unchecked exception, không phải `ExecutionException`.

**Câu 6.** `CompletableFuture.get()` và `CompletableFuture.join()` bọc lỗi khác nhau thế nào?

**Đáp án:** `get()` thường ném checked `ExecutionException`, `join()` thường ném unchecked `CompletionException`. Trong cả hai trường hợp, cần xem cause.

**Câu 7.** Vì sao `IllegalStateException("processing failed", cause)` tốt hơn bỏ cause?

**Đáp án:** Giữ chuỗi nguyên nhân để truy ngược lỗi gốc và stack trace, đồng thời thêm ngữ cảnh nghiệp vụ.

**Câu 8.** Nếu `ScheduledFuture` của một periodic task nhận `ExecutionException` vì một lượt chạy ném lỗi, các lượt tiếp theo có tiếp tục bình thường không?

**Đáp án:** Với `scheduleAtFixedRate`/`scheduleWithFixedDelay` tiêu chuẩn, một lượt periodic task thất bại bất thường sẽ ngăn các lượt tiếp theo của chính task đó.

**Câu 9.** `ExecutorService.invokeAll` trả về danh sách Future có chứng minh mọi task thành công không?

**Đáp án:** Không. Cần gọi `get()` trên từng Future để phân biệt thành công, exception hoặc cancellation.

**Câu 10.** `Future.get()` sau khi task thành công có ý nghĩa JMM gì?

**Đáp án:** Hành động của computation trước khi hoàn thành xảy ra trước những hành động của caller sau khi lấy kết quả theo hợp đồng Future; không thay thế việc đồng bộ những sửa đổi shared mutable state xảy ra về sau.

**Câu 11.** Một task đã ghi database nhưng ném exception khi gửi response. Có nên retry lập tức từ đầu không?

**Đáp án:** Không nếu chưa kiểm tra commit/idempotency; retry có thể nhân đôi tác dụng phụ.

**Câu 12.** Tại sao không chỉ log root cause mà bỏ các wrapper tầng nghiệp vụ?

**Đáp án:** Wrapper có thể chứa ngữ cảnh quan trọng: tên bước, task ID, trạng thái xử lý và quy tắc retry. Cần nhìn cả cause chain.

## 26. Tổng kết

`ExecutionException` là **cơ chế báo lại lỗi của công việc bất đồng bộ qua `Future.get()`**. Khi gặp nó, bước đầu tiên là **`getCause()`**, sau đó giữ và đọc **cả cause chain, stack trace, ngữ cảnh task và các side effect có thể đã xảy ra**.

Điều cần phân biệt rõ: **task thất bại** (`ExecutionException`), **caller hết thời gian chờ** (`TimeoutException`), **caller bị ngắt khi chờ** (`InterruptedException`), và **Future bị hủy** (`CancellationException`). Với `CompletableFuture`, `join()` thường dùng `CompletionException`; với scheduled periodic task, một lỗi không xử lý có thể ngăn những lần chạy tiếp theo.

Muốn hệ thống đáng tin cậy, không chỉ nộp task mà còn phải có **chủ sở hữu Future/outcome**, quy tắc log/propagate/retry, timeout/cancel rõ ràng và xử lý lifecycle executor. Ngoại lệ được bọc không làm mất lỗi gốc nếu ta **giữ `getCause()` và quan sát đúng tầng**, nhưng cũng không tự giải quyết giao dịch đã thất bại một phần hoặc tài nguyên chưa được dọn.
