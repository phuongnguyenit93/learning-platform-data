# Callable<T> so với Runnable khi cần trả kết quả

## 1. Bài toán: tác vụ chạy ở thread khác sẽ trả kết quả như thế nào?

Trong Java Concurrency, một công việc được gửi cho executor thường chạy ở thread khác với thread gửi. Khi chỉ cần **thực hiện hành động** (ghi log, cập nhật trạng thái, gửi thông báo), `Runnable` là một lựa chọn tự nhiên. Khi công việc cần **tính toán và trả về một giá trị**, `Callable<T>` biểu diễn kết quả trực tiếp qua kiểu `T`.

Cả hai đều là **functional interface**, có thể triển khai bằng lambda:

```java
Runnable printMessage = () -> System.out.println("Done");

Callable<Integer> calculate = () -> 21 * 2;
```

Sự khác biệt quan trọng không nằm ở việc “có chạy bất đồng bộ hay không”. Bản thân `Runnable.run()` và `Callable.call()` chỉ là các phương thức thông thường: gọi trực tiếp thì chúng chạy trên **thread hiện tại**. Chúng chỉ chạy theo cơ chế bất đồng bộ khi được giao cho `Thread`, `Executor`, `ExecutorService` hoặc một cơ chế điều phối khác.

Khi giao cho `ExecutorService`, ứng dụng nhận kết quả thông qua một `Future<T>` thay vì nhận trực tiếp tại lời gọi `submit(...)`. `Future` là **đại diện cho kết quả có thể xuất hiện trong tương lai**, cung cấp cách chờ hoàn tất, nhận giá trị, nhận ngoại lệ, kiểm tra trạng thái và yêu cầu hủy.

## 2. So sánh Runnable và Callable<T>

| Đặc điểm | `Runnable` | `Callable<T>` |
| --- | --- | --- |
| Giao diện | `java.lang.Runnable` | `java.util.concurrent.Callable<T>` |
| Phương thức trừu tượng | `void run()` | `T call() throws Exception` |
| Kết quả trả trực tiếp từ phương thức | Không có (`void`) | Có, kiểu `T` |
| Checked exception trong chữ ký | `run()` không khai báo checked exception | `call()` khai báo `throws Exception` |
| Dùng với `Thread` trực tiếp | `new Thread(runnable)` | Không truyền trực tiếp `Callable` vào constructor `Thread` |
| Dùng với `Executor.execute(...)` | Có, nhận `Runnable` | Không nhận `Callable` trực tiếp |
| Dùng với `ExecutorService.submit(...)` | Có, nhận `Future<?>` hoặc `Future<T>` nếu cung cấp kết quả cố định | Có, nhận `Future<T>` |
| Kịch bản điển hình | Task thực hiện hành động, không tạo kết quả logic | Task tính toán, truy vấn, xử lý dữ liệu và trả về kết quả |

Điểm cần nhớ: `Runnable` không đồng nghĩa “fire-and-forget”. Khi gửi `Runnable` bằng `ExecutorService.submit(runnable)`, caller vẫn nhận `Future<?>` để **đợi hoàn tất và quan sát lỗi**; chỉ là không có giá trị nghiệp vụ từ `run()`.

Ngược lại, `Callable<T>` không tự sinh thread hay tự bảo đảm chạy song song. Một `Callable` chạy qua `call()` trực tiếp vẫn là lời gọi đồng bộ.

## 3. API và kiểu kết quả của execute/submit

Hai abstraction thường gặp:

```java
// Fragment minh họa các chữ ký liên quan (không phải chương trình độc lập).
interface Executor {
    void execute(Runnable command);
}

// Một phần API của ExecutorService:
Future<?> submit(Runnable task);
<T> Future<T> submit(Runnable task, T result);
<T> Future<T> submit(Callable<T> task);
```

### 3.1. execute(Runnable): giao việc, không trả Future

`executor.execute(runnable)` trả về `void`. Khi lời gọi thành công, executor đã nhận việc theo chính sách của nó, nhưng **không có handle kết quả** mà API này trả về cho caller. Nó cũng không bảo đảm công việc đã hoàn tất khi `execute` trả về.

Nếu `Runnable.run()` ném unchecked exception trong worker thread, cơ chế xử lý lỗi của thread/`ThreadPoolExecutor` có thể ghi nhận nó thông qua `UncaughtExceptionHandler` hoặc `afterExecute` (tùy cách tùy biến). Lỗi không được chuyển thành `Future.get()` vì không có Future nào được trả về. Nếu executor từ chối task, `RejectedExecutionHandler` có thể ném `RejectedExecutionException` ngay khi gửi việc.

### 3.2. submit(Runnable): có Future, giá trị hoàn thành là null

```java
Future<?> future = executor.submit(
        () -> System.out.println("Side effect finished"));

Object result = future.get(); // null nếu Runnable hoàn tất bình thường
```

`future.get()` đợi tới khi Runnable kết thúc (trừ khi bị interrupt hoặc task bị hủy). Khi thành công, giá trị trả về là `null`; nếu Runnable ném lỗi khi chạy, `get()` ném `ExecutionException` với nguyên nhân ở `getCause()`.

Đừng nhầm `Future<?>` với “không theo dõi được công việc”. Nó theo dõi **vòng đời** dù không chứa kết quả tính toán.

### 3.3. submit(Runnable, result): giá trị cố định khi thành công

```java
Future<String> future = executor.submit(
        () -> performSideEffect(),
        "ACK");
```

Đây là ví dụ fragment: `performSideEffect()` do ứng dụng định nghĩa. Sau khi `Runnable` chạy thành công, `future.get()` trả chuỗi `"ACK"` do caller cung cấp **trước** lúc chạy. Đây không phải giá trị mà `run()` tự tính và trả về. Nếu Runnable ném lỗi, `get()` ném `ExecutionException` chứ không trả `"ACK"`.

Dùng cách này khi bản thân tác vụ không có giá trị cần tính, nhưng caller muốn một Future có kiểu cụ thể và giá trị biểu thị hoàn tất.

### 3.4. submit(Callable<T>): giá trị do chính tác vụ tính toán

```java
Callable<Integer> task = () -> 20 + 22;
Future<Integer> future = executor.submit(task);
Integer answer = future.get(); // 42 khi tính toán thành công
```

`Callable.call()` có thể trả `null` nếu đó là kết quả hợp lệ của nghiệp vụ; kiểu `T` không yêu cầu non-null. Chọn kiểu trả về rõ ràng (`Integer`, `String`, `List<Record>`, một record kết quả...) để caller hiểu chính xác kết quả tính toán.

## 4. Ví dụ Java 17 độc lập: cùng executor, ba cách nhận kết quả

Chương trình sử dụng **single-thread executor** và luôn gọi `get()` trước khi chuyển sang tác vụ tiếp theo, nên thứ tự các dòng in ra được kiểm soát. Ngoại lệ từ `Callable` cũng được minh họa dưới dạng nguyên nhân của `ExecutionException`.

Lưu vào `CallableVsRunnableDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CallableVsRunnableDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Runnable action = () ->
                    System.out.println("Runnable: side effect");
            Future<?> actionFuture = executor.submit(action);
            System.out.println("Runnable result: " + actionFuture.get());

            Callable<Integer> computation = () -> 20 + 22;
            Future<Integer> computationFuture =
                    executor.submit(computation);
            System.out.println("Callable result: " + computationFuture.get());

            Future<String> fixedResult = executor.submit(
                    () -> System.out.println("Runnable: acknowledged"),
                    "ACK");
            System.out.println("Fixed result: " + fixedResult.get());

            Callable<String> failing = () -> {
                throw new IOException("source unavailable");
            };
            Future<String> failedFuture = executor.submit(failing);
            try {
                System.out.println(failedFuture.get());
            } catch (ExecutionException exception) {
                System.out.println(
                        "Failure cause: "
                        + exception.getCause().getClass().getSimpleName());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac CallableVsRunnableDemo.java
java CallableVsRunnableDemo
```

Kết quả:

```text
Runnable: side effect
Runnable result: null
Callable result: 42
Runnable: acknowledged
Fixed result: ACK
Failure cause: IOException
```

Giải thích: ở lần gửi thứ nhất, `submit(Runnable)` chỉ cho biết đã hoàn tất, nên `get()` là `null`. Ở lần thứ hai, `Callable<Integer>` thực sự tạo ra `42`. Ở lần thứ ba, `"ACK"` được truyền từ phía caller, không đến từ `Runnable.run()`. Ở lần cuối, `IOException` được giữ làm nguyên nhân của `ExecutionException`; nó không tự xuất hiện như một ngoại lệ của lời gọi `submit`.

Ví dụ dùng `main throws Exception` để giữ mã gọn; trong ứng dụng thực tế, code sử dụng `get()` cần có kế hoạch xử lý `InterruptedException`, `ExecutionException`, timeout và hủy. Đoạn `finally` gửi yêu cầu shutdown và thử chờ tối đa 5 giây; đây không phải bảo đảm mọi task bất hợp tác sẽ dừng tức thì sau `shutdownNow()`.

## 5. Future<T> là cầu nối giữa thread gửi và kết quả

Khi gọi `submit(Callable<T>)`, executor thường biến nhiệm vụ thành một đối tượng kiểu `RunnableFuture<T>` (một ví dụ triển khai là `FutureTask<T>`). Worker có thể chạy wrapper dạng `Runnable`, còn `Future<T>` cho caller các thao tác:

| API | Ngữ nghĩa |
| --- | --- |
| `T get()` | Chờ kết quả; thành công thì trả `T`; có thể bị gián đoạn hoặc ném ngoại lệ nếu task lỗi/hủy |
| `T get(long timeout, TimeUnit unit)` | Chờ tối đa khoảng thời gian chỉ định; có thể ném `TimeoutException` |
| `boolean isDone()` | `true` nếu task đã hoàn tất bình thường, lỗi hoặc bị hủy |
| `boolean isCancelled()` | `true` nếu task đã bị hủy |
| `boolean cancel(boolean mayInterruptIfRunning)` | Cố gắng hủy; giá trị trả về cho biết yêu cầu hủy có thành công theo trạng thái Future hay không |

Một `Future` có thể đại diện cho các trạng thái logic:

```text
SUBMITTED / QUEUED → RUNNING → COMPLETED_SUCCESS
                            └──→ COMPLETED_FAILURE
              └───────────────→ CANCELLED
```

Đây là sơ đồ khái niệm về vòng đời task; các chuyển trạng thái chi tiết còn phụ thuộc loại `Future`. **`isDone() == true` không có nghĩa task thành công**, bởi vì task lỗi hoặc bị hủy cũng là “done”. Cần `get()` hoặc cơ chế ghi nhận kết quả rõ ràng để phân biệt các trường hợp.

### Kết quả, lỗi, hủy: ba đường kết thúc cần phân biệt

```java
// Fragment: future do ExecutorService.submit(callable) trả về.
try {
    String value = future.get(1, TimeUnit.SECONDS);
    System.out.println("Success: " + value);
} catch (java.util.concurrent.TimeoutException timedOut) {
    System.out.println("Still waiting");
} catch (java.util.concurrent.CancellationException cancelled) {
    System.out.println("Cancelled");
} catch (java.util.concurrent.ExecutionException failed) {
    Throwable cause = failed.getCause();
    System.out.println("Task failed: " + cause);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
}
```

Đây là fragment sử dụng `Future<String> future` đã được khai báo ở nơi khác.

- **`ExecutionException`**: tác vụ đã chạy và kết thúc bằng exception hoặc error; kiểm tra `getCause()` để biết lỗi gốc. `Callable.call()` cho phép checked exception; `Future.get()` không ném thẳng checked exception đó.
- **`CancellationException`** (unchecked): Future đã bị hủy. `get()` không trả một kết quả hợp lệ.
- **`TimeoutException`**: `get(timeout, unit)` đã chờ quá giới hạn; **task thường vẫn đang tiếp tục**. Muốn hủy, caller phải yêu cầu riêng, chẳng hạn `cancel(true)`, và chấp nhận rằng hủy chỉ mang tính hợp tác.
- **`InterruptedException`**: thread đang chờ `get()` bị ngắt; điều này **không tự hủy task phía worker**. Mã ứng dụng thường khôi phục interrupt flag hoặc truyền ngoại lệ lên tầng trên theo hợp đồng của mình.

### Future và khả năng thấy dữ liệu giữa các thread

`Future` còn cung cấp ràng buộc memory consistency: các hành động của tác vụ bất đồng bộ **happen-before** các hành động sau khi thread khác lấy kết quả qua `Future.get()` tương ứng. Vì vậy, `get()` hữu ích như một điểm đồng bộ để đọc dữ liệu mà task đã công bố đúng cách.

Tuy nhiên, `Future.get()` **không** biến mọi trạng thái shared mutable thành thread-safe. Nếu nhiều task cùng sửa một `ArrayList` hoặc biến thông thường trong lúc đang chạy, vẫn cần đồng bộ hóa, collection concurrent hoặc thiết kế không chia sẻ mutable state. Với kết quả đơn giản, ưu tiên **trả kết quả trực tiếp từ `Callable`** thay vì ghi vào biến toàn cục rồi tự chờ.

## 6. Checked exception và lỗi bị “ẩn” khi dùng submit

`Callable<T>.call() throws Exception` cho phép code bất đồng bộ gọi các API có checked exception:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

// Fragment: code đọc file và báo IOException qua Future.get().
Callable<String> readText = () ->
        Files.readString(Path.of("data.txt"));
```

`Files.readString` có thể ném `IOException`; vì `call()` khai báo `throws Exception`, lambda trên hợp lệ. Đối với `Runnable.run()`, caller phải bắt checked exception bên trong và tự xử lý hoặc wrap thành unchecked exception; nó không thể khai báo `throws IOException` khi override `run()`.

Một khác biệt thực tế là cách quan sát lỗi của tác vụ:

- `execute(runnable)`: exception unchecked không được xử lý từ `run()` có thể đi qua cơ chế uncaught exception của worker; caller không có `Future` do lời gọi này trả về.
- `submit(runnable/callable)`: executor thường thực thi wrapper `FutureTask`, wrapper **ghi nhận exception**. Vì thế exception của task không nhất thiết xuất hiện ở log uncaught exception của worker. Caller cần gọi `get()` hoặc có đường ghi nhận lỗi khác.
- `submit` vẫn có thể ném `RejectedExecutionException` **ngay lúc gửi** nếu executor từ chối theo chính sách ném lỗi. Đây là lỗi **admission**, khác `ExecutionException` do bản thân task chạy thất bại.

Lỗi phổ biến: sử dụng `submit` rồi bỏ luôn Future. Nếu task thất bại, ứng dụng có thể không đọc được nguyên nhân và tưởng rằng công việc thành công. Với các tác vụ quan trọng, hãy giữ Future, gom kết quả, hoặc có đường thu thập ngoại lệ và metric được thiết kế rõ.

## 7. Nguy cơ chờ vô hạn và cách dùng timeout

`Future.get()` không có timeout có thể chặn caller mãi nếu task không hoàn tất hoặc Future bị bỏ quên vì một chính sách từ chối im lặng. Trong hệ thống có deadline, `get(timeout, unit)` giúp giới hạn **thời gian caller chờ**, nhưng không đồng nghĩa giới hạn thời gian xử lý trên worker.

Ví dụ fragment:

```java
try {
    Result result = resultFuture.get(500, TimeUnit.MILLISECONDS);
    use(result);
} catch (TimeoutException timedOut) {
    boolean cancellationRequested = resultFuture.cancel(true);
    reportTimeout(cancellationRequested);
}
```

`Result`, `resultFuture`, `use` và `reportTimeout` là các thành phần giả định của ứng dụng; đoạn này minh họa ý tưởng, **không phải chương trình độc lập**. `cancel(true)` thử interrupt thread đang chạy, nhưng Java không thể cưỡng ép dừng một task bỏ qua interrupt hoặc mắc kẹt ở thao tác không có khả năng interrupt. Nếu task gây side effect, hủy cũng không hoàn tác những việc đã làm trước đó.

### Bẫy thread starvation deadlock

Một task chạy trong executor một luồng lại gửi task thứ hai vào **cùng** executor và chờ `get()` của task thứ hai:

```java
// PHẢN VÍ DỤ (không chạy): single-thread executor có thể deadlock.
// Callable<String> outer = () -> {
//     Future<String> inner = sameSingleThreadPool.submit(() -> "ready");
//     return inner.get(); // worker đang chạy outer, inner chưa được chạy
// };
```

Worker duy nhất bận chờ `inner`, còn `inner` nằm trong queue chờ worker rảnh. Cần tránh phụ thuộc đồng bộ kiểu này: tổ chức task thành chuỗi xử lý, dùng executor độc lập và capacity thích hợp khi thật sự cần, hoặc áp dụng composition không chặn. **Callable trả kết quả không loại bỏ nguy cơ deadlock khi caller chờ sai chỗ.**

## 8. Hủy task và interrupt có nghĩa gì?

Ví dụ dùng `Future<String> future = executor.submit(callable)`:

- `future.cancel(false)`: yêu cầu hủy mà không cố interrupt nếu task đã chạy. Future có thể chuyển sang trạng thái canceled, nhưng side effect của task đang thực thi **có thể vẫn tiếp tục**.
- `future.cancel(true)`: nếu task đang chạy, Future có thể gửi interrupt tới thread đang thực thi. Task chỉ dừng kịp thời khi code hoặc các thao tác blocking hợp tác với interrupt.
- `future.get()` sau khi hủy thành công sẽ ném `CancellationException`.
- `future.isCancelled()` là trạng thái của Future; không bảo đảm mọi resource đã được đóng hoặc side effect đã được rollback.

Callable có thể kiểm tra interrupt trong tác vụ lặp:

```java
// Fragment: Runnable hoặc Callable đều có thể kiểm tra interrupt.
while (!Thread.currentThread().isInterrupted()) {
    performOneSmallStep();
}
```

Tác vụ gọi API blocking có thể nhận `InterruptedException`. Không nên nuốt ngoại lệ đó rồi tiếp tục chạy vô hạn; có thể truyền lại từ `Callable.call()`, hoặc khôi phục interrupt flag trong `Runnable.run()` trước khi thoát.

Shutdown executor và cancel Future là hai cơ chế khác nhau. `shutdown()` ngừng nhận việc mới và cho việc đã nhận hoàn tất; `shutdownNow()` cố interrupt worker và trả danh sách các tác vụ đang chờ chưa bắt đầu, **không bảo đảm** tác vụ đang chạy dừng ngay.

## 9. Callable từ Runnable: adapter và FutureTask

Nếu đang có `Runnable` thực hiện hành động nhưng API nhận `Callable<T>`, Java cung cấp adapter:

```java
// Fragment: Runnable đã tồn tại.
Runnable update = () -> System.out.println("Updated");
Callable<String> asCallable =
        java.util.concurrent.Executors.callable(update, "OK");
```

`asCallable.call()` chạy `update.run()` rồi trả `"OK"` nếu hoàn thành bình thường; nếu Runnable ném exception unchecked, exception vẫn được truyền qua lời gọi `call()`. Adapter **không biến side effect thành một kết quả tính toán**.

`FutureTask<V>` triển khai `RunnableFuture<V>`, tức vừa có thể được executor chạy như `Runnable`, vừa có thể được đọc như `Future<V>`:

```java
// Fragment, minh họa hai vai trò của FutureTask.
java.util.concurrent.FutureTask<Integer> task =
        new java.util.concurrent.FutureTask<>(() -> 6 * 7);

executor.execute(task); // execute nhận Runnable.
Integer result = task.get(); // FutureTask đồng thời là Future<Integer>.
```

Không cần tự tạo `FutureTask` trong trường hợp thông thường: `ExecutorService.submit(callable)` đã lo việc tạo Future và lập lịch. `FutureTask` hữu ích khi cần kiểm soát wrapper hoặc tích hợp một API chỉ nhận `Runnable`. Không gọi `run()` thủ công rồi lại gửi cùng task, trừ khi thật sự hiểu semantics về hoàn tất một lần của `FutureTask`.

Một constructor khác là `new FutureTask<>(Runnable, V result)`: về bản chất tương đương ý tưởng `submit(Runnable, result)`, với giá trị `result` được cố định trước.

## 10. Nhiều Callable: invokeAll và invokeAny

`ExecutorService` có hai API làm việc với một tập `Callable`:

| API | Ý nghĩa | Kết quả |
| --- | --- | --- |
| `invokeAll(Collection<? extends Callable<T>>)` | Chờ tất cả hoàn tất | Danh sách `Future<T>` theo thứ tự tương ứng với collection đầu vào; từng `get()` có thể trả giá trị hoặc báo lỗi |
| `invokeAll(tasks, timeout, unit)` | Chờ tối đa một thời hạn chung | Sau khi trở về, các task chưa hoàn tất được yêu cầu hủy |
| `invokeAny(Collection<? extends Callable<T>>)` | Chờ **một** task hoàn tất thành công | Trả giá trị `T` từ một task thành công; không hứa task nào thắng khi nhiều task cạnh tranh |
| `invokeAny(tasks, timeout, unit)` | Tương tự nhưng giới hạn thời gian | Có thể ném `TimeoutException` khi không có kết quả thành công đúng hạn |

`invokeAny` không phải “trả kết quả của task hoàn thành đầu tiên, kể cả khi nó lỗi”: nó tìm **kết quả thành công**; nếu một task thất bại, các task khác vẫn có thể thắng. Khi chọn được kết quả hoặc không còn lý do tiếp tục, API xử lý hủy các tác vụ chưa hoàn tất theo hợp đồng của nó. Không dùng `invokeAny` để giả định thứ tự chạy hay dựa vào tác dụng phụ của tất cả task.

Ví dụ chương trình độc lập `BatchCallableDemo.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BatchCallableDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 2 * 3,
                    () -> 4 * 5,
                    () -> 6 * 7);
            List<Future<Integer>> futures = executor.invokeAll(tasks);
            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get();
            }
            System.out.println("Total = " + total);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BatchCallableDemo.java
java BatchCallableDemo
```

Stdout:

```text
Total = 68
```

Dù có hai worker và ba task có thể hoàn thành theo thứ tự khác nhau, `invokeAll` trả Future tương ứng với thứ tự trong collection. Tổng `6 + 20 + 42 = 68` không phụ thuộc thứ tự thực thi.

## 11. Callable trong ScheduledExecutorService

Nhóm **Future & Scheduling** còn có các tác vụ được lên lịch. `ScheduledExecutorService` hỗ trợ:

- `schedule(Runnable command, long delay, TimeUnit unit)` trả `ScheduledFuture<?>`: chạy **một lần** sau độ trễ tối thiểu, không trả kết quả nghiệp vụ.
- `schedule(Callable<V> callable, long delay, TimeUnit unit)` trả `ScheduledFuture<V>`: chạy **một lần** sau độ trễ tối thiểu, cho phép nhận giá trị `V` từ `get()`.
- `scheduleAtFixedRate(...)` và `scheduleWithFixedDelay(...)` nhận `Runnable` để chạy lặp; một tác vụ lặp thành công thường không hoàn tất Future theo cách one-shot. **Không gọi `get()` rồi chờ mỗi chu kỳ trả về một giá trị**: Future của periodic task thường chỉ hoàn tất do hủy hoặc kết thúc bất thường.

Ví dụ một lịch hẹn tính toán `ScheduledCallableDemo.java`:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledCallableDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        try {
            ScheduledFuture<Integer> future =
                    scheduler.schedule(() -> 7 * 6, 50, TimeUnit.MILLISECONDS);
            System.out.println("Scheduled result = " + future.get());
        } finally {
            scheduler.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ScheduledCallableDemo.java
java ScheduledCallableDemo
```

Stdout:

```text
Scheduled result = 42
```

Lưu ý: `50 ms` là **độ trễ yêu cầu trước khi có thể thực thi**, không phải bảo đảm thời điểm chạy chính xác 50 ms hoặc hoàn tất đúng hạn. Scheduling phụ thuộc tải và khả năng cấp worker. Không cần dùng framework nào để lên lịch Callable kiểu này.

## 12. Khi nào chọn Callable<T>, khi nào giữ Runnable?

**Chọn `Callable<T>` khi:**

1. Giá trị trả về là một phần hợp đồng của tác vụ (tổng tiền, kết quả phân tích, dữ liệu truy vấn, đối tượng đầu ra).
2. Muốn trình biên dịch kiểm tra kiểu trả về của kết quả `Future<T>`, tránh dùng biến toàn cục hoặc holder mutable.
3. Task cần gọi API có checked exception và muốn công bố lỗi thông qua `Future.get()`.
4. Cần dùng `invokeAll`, `invokeAny` hoặc `schedule(Callable, delay, unit)` để nhận kết quả.

**Chọn `Runnable` khi:**

1. Task mang mục đích hành động, không có giá trị tính toán cần trả (cập nhật cache, phát notification, log, cleanup).
2. API yêu cầu `Runnable`, như `new Thread(runnable)`, `Executor.execute(runnable)` hoặc lịch chạy định kỳ.
3. Chỉ cần biết task đã xong/thất bại qua `Future<?>` từ `submit(runnable)`.
4. Cần giá trị thành công cố định, có thể dùng `submit(runnable, result)` thay vì tạo một Callable chỉ để trả cùng một hằng số.

Không nên ép mọi `Runnable` thành `Callable<Void>`. Cách này hợp lệ khi có lý do thiết kế (trả `null`) nhưng làm code dài hơn mà không tự tạo thêm giá trị nghiệp vụ. Nếu task có giá trị thực, `Callable<Result>` thường biểu đạt ý định tốt nhất.

### Bảng quyết định nhanh

| Mục tiêu | Lời gọi ưu tiên | Giá trị caller nhận |
| --- | --- | --- |
| Chỉ giao task và không cần handle | `execute(Runnable)` | Không có Future |
| Giao task và muốn theo dõi hoàn tất/lỗi | `submit(Runnable)` | `Future<?>`, `get() == null` nếu thành công |
| Giao task hành động và muốn hằng số khi thành công | `submit(Runnable, T result)` | `Future<T>` trả giá trị cố định |
| Task tính và trả kết quả kiểu T | `submit(Callable<T>)` | `Future<T>` trả kết quả từ `call()` |
| Nhiều tác vụ cho kết quả | `invokeAll`/`invokeAny` với `Callable<T>` | Danh sách Future hoặc một giá trị thành công |
| Tính toán một lần sau độ trễ | `schedule(Callable<T>, delay, unit)` | `ScheduledFuture<T>` |

## 13. Lỗi thường gặp và cách tránh

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ rằng `Callable.call()` tự chạy thread khác | Đây là một phương thức bình thường nếu gọi trực tiếp | Dùng `ExecutorService.submit(callable)` hoặc scheduler |
| Muốn lấy kết quả từ `Runnable.run()` | `run()` trả `void` | Đổi thành `Callable<Result>` hoặc dùng `submit(runnable, fixedValue)` nếu chỉ cần giá trị cố định |
| Gọi `submit(callable)` rồi chờ trả về giá trị T trực tiếp | `submit` trả về `Future<T>`, không trả T | Dùng `future.get()` ở vị trí được phép block |
| Không giữ Future sau `submit` | Exception của task có thể chỉ được lưu trong Future và không được quan sát | Giữ handle, đọc kết quả, theo dõi và log lỗi |
| Coi `isDone()` là thành công | Hủy và lỗi cũng được xem là done | Gọi `get()`, xử lý `ExecutionException`/`CancellationException` |
| Bắt `ExecutionException` và bỏ qua `getCause()` | Mất nguyên nhân gây lỗi | Dùng nguyên nhân để chẩn đoán hoặc chuyển lỗi có ngữ cảnh |
| Dùng `get()` không timeout trên đường xử lý nhạy độ trễ | Caller có thể chờ lâu hoặc vô hạn | Chọn timeout/deadline, thiết kế callback/composition khi cần |
| Nghĩ rằng `get(timeout)` đã dừng task | Timeout chỉ giới hạn việc **chờ** | Nếu phù hợp, yêu cầu `cancel(true)` và hỗ trợ interrupt |
| Cho worker chờ Future của task queued cùng single-thread pool | Có thể bị thread starvation deadlock | Tổ chức lại phụ thuộc và tránh blocking bên trong worker |
| Dùng `DiscardPolicy` rồi `submit` và `get()` | Task bị bỏ âm thầm, Future có thể không bao giờ hoàn tất | Ưu tiên handler báo lỗi rõ và admission control đúng |
| Dùng `Future.get()` trên lịch chạy định kỳ | Periodic Future không có kết quả mỗi chu kỳ | Báo cáo kết quả mỗi tick qua cơ chế riêng, hủy đúng vòng đời |
| Nhầm `Future.get()` với khóa bảo vệ shared state | Nó tạo quan hệ memory visibility theo hợp đồng, không tránh data race giữa nhiều writer | Dùng thiết kế immutable/đồng bộ khi có chia sẻ dữ liệu |

## 14. Tự kiểm tra

1. **`Runnable` có thể gửi bằng `submit` không?** Có. Caller nhận `Future<?>`; nếu chạy thành công, `get()` trả `null`.
2. **`submit(Runnable, "OK")` khác `submit(Callable<String>)` ở đâu?** Cách đầu trả giá trị cố định do caller cung cấp sau khi Runnable thành công; cách sau trả giá trị thực do `call()` tính.
3. **Một `Callable<Integer>` ném `IOException`; điều gì xảy ra khi `Future.get()`?** `get()` ném `ExecutionException`, `getCause()` là `IOException` tương ứng.
4. **`get(timeout)` ném `TimeoutException` có dừng task không?** Không. Đó chỉ là timeout của thao tác chờ; cần chính sách cancel riêng.
5. **`isDone() == true` đã chứng minh task thành công chưa?** Chưa; task có thể lỗi hoặc bị hủy.
6. **`schedule(Callable<T>, delay, unit)` có trả kết quả không?** Có, thông qua `ScheduledFuture<T>`; độ trễ yêu cầu không bảo đảm thời điểm thực thi tuyệt đối.
7. **Khi nào dùng `execute(Runnable)` thay `submit(Runnable)`?** Khi không cần handle Future và muốn giao việc theo hợp đồng `Executor`; nếu cần đợi hoàn tất hoặc đọc lỗi, `submit` phù hợp hơn.
8. **Vì sao đừng gọi `Future.get()` của một task queued ngay trong worker duy nhất của cùng executor?** Worker sẽ bị chặn trong khi task kia chưa thể được chạy.

## Tài liệu tham khảo

- [Java SE 17: Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html)
- [Java SE 17: Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html)
- [Java SE 17: ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17: Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17: FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17: ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
