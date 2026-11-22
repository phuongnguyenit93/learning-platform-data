# Khác biệt giữa `Executor.execute()` và `ExecutorService.submit()` khi tác vụ thất bại

Trong lập trình đa luồng Java, một tác vụ có thể được gửi vào bộ thực thi (executor) nhưng lại ném ngoại lệ khi chạy. Cả `execute()` và `submit()` đều có thể dùng để giao một `Runnable` cho executor; điểm khác biệt quan trọng là **đường đi của lỗi và cách chương trình phát hiện lỗi**. Nếu chọn cách gửi tác vụ mà không thiết kế cách nhận lỗi, ứng dụng có thể tiếp tục hoạt động trong khi một công việc quan trọng đã thất bại.

Bài này xét lỗi **xảy ra bên trong tác vụ**. Lỗi khi executor **từ chối nhận tác vụ** được phân biệt riêng ở phần dưới.

## 1. Hai phương thức thuộc những giao diện nào?

- `Executor.execute(Runnable command)` được khai báo trong `java.util.concurrent.Executor`. Phương thức trả về `void`: người gọi không nhận một đối tượng kết quả để chờ hoặc kiểm tra lỗi của tác vụ.
- `ExecutorService.submit(...)` được khai báo trong `java.util.concurrent.ExecutorService` (giao diện mở rộng `Executor`). Các overload thường dùng là `submit(Runnable)`, `submit(Callable<T>)` và `submit(Runnable, T result)`. Phương thức trả về `Future`, là đầu mối để theo dõi kết thúc, nhận kết quả hoặc nhận lỗi.

| Khía cạnh | `execute(Runnable)` | `submit(Runnable/Callable)` |
| --- | --- | --- |
| Giao diện sở hữu | `Executor` | `ExecutorService` |
| Giá trị trả về | `void` | `Future<?>` hoặc `Future<T>` |
| Khi công việc hoàn tất bình thường | Không có kết quả trả về trực tiếp | `Future.get()` trả `null` với `Runnable` thông thường, hoặc giá trị của `Callable<T>` |
| Khi thân tác vụ ném ngoại lệ và không tự bắt | Với `ThreadPoolExecutor` thực thi một `Runnable` trực tiếp, lỗi thường thoát khỏi `run()` của worker, có thể tới `UncaughtExceptionHandler` | Với cơ chế `FutureTask` thường dùng, lỗi được giữ trong `Future`; `get()` ném `ExecutionException` chứa lỗi gốc |
| Người gọi nhận ra thất bại bằng cách nào? | Thiết kế kênh báo lỗi bên trong tác vụ, handler/hook giám sát phù hợp, hoặc cơ chế riêng | Giữ lại `Future` và gọi `get()` (hoặc có cơ chế thu thập/giám sát các `Future`) |
| Có thể kiểm tra đã kết thúc qua đối tượng trả về? | Không | Có, bằng `isDone()`; nhưng `isDone() == true` **không chứng minh thành công** |
| Có thể hủy qua đối tượng trả về? | Không có `Future` do phương thức trả lại | Có, `Future.cancel(...)`, với những giới hạn của cơ chế hủy |

**Điểm mấu chốt:** `submit()` không khiến tác vụ ít lỗi hơn. Nó thay đổi cách biểu diễn và quan sát kết quả của tác vụ. `execute()` cũng không bảo đảm luôn in stack trace: điều này phụ thuộc executor, wrapper và cơ chế xử lý lỗi.

## 2. Đường đi của ngoại lệ

Xét một `Runnable` ném `IllegalStateException` và không tự bắt ngoại lệ.

**Trường hợp thường gặp: `ThreadPoolExecutor.execute(runnable)`**

1. Executor nhận `Runnable` và chạy `run()` bằng một worker.
2. `run()` ném `RuntimeException` hoặc `Error` ra ngoài.
3. Với `Runnable` trực tiếp trên `ThreadPoolExecutor`, worker kết thúc bất thường; lỗi có thể được chuyển tới `Thread.UncaughtExceptionHandler` của worker.
4. Executor có thể tạo worker thay thế để duy trì kích thước pool. Điều này **không có nghĩa toàn bộ thread pool bị hỏng**, cũng không tự động báo lỗi về luồng đã gọi `execute()`.

Nếu worker không có handler tùy chỉnh, bạn thường thấy stack trace do handler mặc định ghi ra luồng lỗi chuẩn. Không nên dựa vào việc “cứ `execute()` là console sẽ hiện lỗi”, bởi các triển khai `Executor` và cách bọc tác vụ có thể khác nhau.

**Trường hợp thường gặp: `ExecutorService.submit(runnable)`**

1. ExecutorService tạo một tác vụ có trạng thái/kết quả dạng `Future` (ví dụ `FutureTask`) rồi lên lịch chạy.
2. Khi thân tác vụ ném ngoại lệ, lớp bao kết quả bắt và lưu ngoại lệ.
3. `Future` chuyển sang trạng thái hoàn tất; một lỗi đã xảy ra vẫn làm `isDone()` trả `true`.
4. Khi người gọi `future.get()`, phương thức ném `ExecutionException`; `getCause()` cho biết ngoại lệ gốc đã khiến tác vụ thất bại.

Vì lỗi được giữ trong `Future`, `UncaughtExceptionHandler` của worker **thường không được gọi** cho lỗi của tác vụ gửi qua `submit()`. Nếu bỏ qua `Future` mà không có kênh giám sát khác, lỗi có thể không xuất hiện trong log.

Lưu ý phạm vi: `Executor` chỉ là hợp đồng thực thi lệnh. Có executor chạy tác vụ ngay trên luồng gọi, và có executor dùng worker riêng. Hành vi worker và stack trace ở trên mô tả `ThreadPoolExecutor` với tác vụ `Runnable` trực tiếp, không phải cam kết cho mọi executor.

## 3. Ví dụ Java 17+ có thể chạy: cùng một lỗi, hai cách quan sát

Tạo tệp **`ExecuteVsSubmitFailure.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

public class ExecuteVsSubmitFailure {
    public static void main(String[] args) throws Exception {
        CountDownLatch handlerFinished = new CountDownLatch(1);

        ThreadFactory factory = task -> {
            Thread worker = new Thread(task, "demo-worker");
            worker.setUncaughtExceptionHandler((thread, failure) -> {
                System.out.printf("execute/handler: %s: %s%n",
                        failure.getClass().getSimpleName(),
                        failure.getMessage());
                handlerFinished.countDown();
            });
            return worker;
        };

        ExecutorService pool = Executors.newSingleThreadExecutor(factory);
        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failed");
            });

            if (!handlerFinished.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("UncaughtExceptionHandler did not run");
            }

            Future<?> submitted = pool.submit((Runnable) () -> {
                throw new IllegalArgumentException("submit failed");
            });

            try {
                submitted.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException exception) {
                Throwable cause = exception.getCause();
                System.out.printf("submit/get: %s: %s%n",
                        cause.getClass().getSimpleName(),
                        cause.getMessage());
            }

            System.out.println("submit/isDone: " + submitted.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ExecuteVsSubmitFailure.java
java ExecuteVsSubmitFailure
```

Kết quả chuẩn trên cơ chế `ThreadPoolExecutor` do `Executors.newSingleThreadExecutor(...)` tạo:

```text
execute/handler: IllegalStateException: execute failed
submit/get: IllegalArgumentException: submit failed
submit/isDone: true
```

Ví dụ dùng `CountDownLatch` để đợi handler in xong trước khi chuyển sang phần `submit()`, nhờ đó thứ tự ba dòng có thể kiểm tra. Executor một luồng có thể tạo worker mới sau lần lỗi ở `execute()`; phần `submit()` vẫn được chạy. Handler tùy chỉnh đã xử lý việc ghi lỗi của `execute()`, nên không cần trông chờ stack trace mặc định của JVM.

Giải thích từng kết quả:

- Dòng `execute/handler` là thông báo từ `UncaughtExceptionHandler` của luồng thực thi. Người gọi `execute()` không nhận `ExecutionException` hoặc `Future` nào từ lời gọi đó.
- Dòng `submit/get` chỉ xuất hiện khi luồng gọi đọc `submitted.get(...)` và bắt `ExecutionException`. Lỗi ban đầu là `IllegalArgumentException`, lấy bằng `getCause()`.
- Dòng `submit/isDone: true` cho biết tác vụ đã **kết thúc**, dù kết thúc vì ngoại lệ. Đừng dùng `isDone()` như phép kiểm tra thành công.

Lệnh `get(5, TimeUnit.SECONDS)` chỉ giới hạn thời gian chờ của luồng gọi; thời gian chờ hết sẽ ném `TimeoutException`, không tự chứng minh tác vụ đã dừng. Ví dụ có `shutdown()` và `awaitTermination()` để dọn executor khi kết thúc.

## 4. `Runnable`, `Callable` và ngoại lệ checked

`Runnable.run()` không khai báo `throws` cho checked exception. Vì thế một `Runnable` không thể ném trực tiếp checked exception ra khỏi `run()` mà không xử lý hoặc gói nó trong unchecked exception. Ngược lại, `Callable<V>.call()` khai báo `throws Exception`, nên có thể báo checked exception khi tính toán thất bại.

Ví dụ đặt bên trong một phương thức có biến `ExecutorService pool`:

```java
Future<String> result = pool.submit(() -> {
    throw new java.io.IOException("cannot read data");
});

try {
    String value = result.get();
    System.out.println(value);
} catch (ExecutionException exception) {
    Throwable cause = exception.getCause();
    // cause là IOException("cannot read data") của tác vụ.
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    // Luồng đang chờ bị ngắt; cần quyết định cách kết thúc/chuyển lỗi.
}
```

Đây là **đoạn mã minh họa bên trong phương thức**, không phải một lớp Java độc lập; cần một `pool` đang hoạt động. `IOException` xảy ra trong worker được lưu làm nguyên nhân của `ExecutionException`. Kiểu trả về `Future<String>` đến từ `Callable<String>`, không phải từ `execute()`.

Với `submit(Runnable)`, nếu tác vụ thành công thì `get()` trả `null`; với `submit(Runnable, fixedResult)`, `get()` trả `fixedResult` khi thành công. Khi tác vụ thất bại, các biến thể đều có thể báo lỗi qua `ExecutionException`.

## 5. Ba loại thất bại cần phân biệt

### 5.1. Tác vụ ném ngoại lệ khi đang chạy

Ví dụ `NullPointerException`, `IllegalArgumentException`, `IllegalStateException` hoặc checked exception từ `Callable`. Với `submit()` và cơ chế `Future` thông thường, `get()` là nơi người đợi nhận `ExecutionException`. Với `execute()` trên worker của `ThreadPoolExecutor` và `Runnable` trực tiếp, lỗi chưa bắt có thể đi tới handler của worker.

`Future.get()` còn có các đường đi **khác** `ExecutionException`: `InterruptedException` khi chính luồng đang chờ bị ngắt; `CancellationException` nếu tác vụ bị hủy; và `TimeoutException` với overload có thời hạn nếu chưa có kết quả kịp lúc. Đừng gộp bốn tình huống thành “tác vụ đã ném exception”.

### 5.2. Executor từ chối nhận tác vụ

Khi executor đã `shutdown()` hoặc hàng đợi/pool quá tải theo chính sách từ chối, `execute()` có thể ném `RejectedExecutionException` **ngay tại thời điểm gửi**. `submit()` cũng có thể ném lỗi này ngay: nhiều triển khai `ExecutorService` bọc công việc thành `FutureTask` rồi gọi cơ chế `execute()` để gửi. Khi bị từ chối, có thể **không có `Future` nào được trả về**.

Ví dụ về cách nhận biết đúng vị trí:

```java
try {
    pool.submit(() -> System.out.println("running"));
} catch (java.util.concurrent.RejectedExecutionException rejected) {
    System.err.println("Executor refused the task: " + rejected);
}
```

Đây là đoạn đặt trong phạm vi đã có `ExecutorService pool`. Việc bắt lỗi từ chối ở **lời gọi gửi** không thay cho kiểm tra kết quả sau này bằng `Future.get()`. Một số `RejectedExecutionHandler` có thể chạy tác vụ ngay ở luồng gọi, hoặc bỏ tác vụ theo chính sách riêng; không được suy ra một quy tắc duy nhất cho mọi chính sách.

### 5.3. Tác vụ tự bắt rồi bỏ qua lỗi

Nếu bên trong `Runnable` có `try/catch` bắt ngoại lệ nhưng chỉ ghi log và trả về bình thường, executor nhìn thấy một tác vụ **hoàn tất bình thường**. Khi ấy:

- `execute()` không còn ngoại lệ chưa bắt để chuyển đến handler;
- `submit()` có `Future.get()` hoàn tất bình thường (`null` đối với `Runnable`), dù công việc nghiệp vụ thực tế có thể chưa thành công.

Muốn tác vụ được ghi nhận là thất bại, cần thiết kế rõ: ném lại ngoại lệ sau khi bổ sung ngữ cảnh, trả kiểu kết quả biểu diễn thành công/thất bại, hoặc truyền sự kiện lỗi tới kênh giám sát. Đừng dùng khối `catch` rỗng để làm “mất” lỗi.

## 6. Cách sử dụng đúng trong ứng dụng

**Chọn `execute()`** khi bạn chỉ muốn gửi một lệnh không cần lấy kết quả qua `Future`, đồng thời đã có chiến lược ghi log/báo thất bại rõ ràng. Ví dụ hệ thống có một `Runnable` tự xử lý lỗi và gửi tín hiệu lỗi tới nơi theo dõi. `execute()` không mang sẵn cơ chế cho người gửi truy vấn kết quả.

**Chọn `submit()`** khi người gửi cần biết việc đã hoàn thành, lấy kết quả, chờ có giới hạn thời gian hoặc yêu cầu hủy. Nhưng phải **giữ và tiêu thụ `Future`** hoặc đưa nó vào cơ chế quan sát tập trung. Gọi `submit()` rồi bỏ qua giá trị trả về thường khiến lỗi của tác vụ khó phát hiện.

Với luồng chờ kết quả, dùng quy tắc xử lý rõ ràng:

1. `ExecutionException`: lấy `getCause()` và xử lý/báo lỗi nghiệp vụ hoặc lỗi kỹ thuật gốc.
2. `InterruptedException`: bảo toàn tín hiệu ngắt bằng `Thread.currentThread().interrupt()` nếu không chuyển tiếp ngoại lệ; sau đó dừng hoặc kết thúc quy trình chờ phù hợp.
3. `CancellationException`: tác vụ đã bị hủy; không coi đó là hoàn tất thành công.
4. `TimeoutException` (khi gọi `get(timeout, unit)`): quyết định có chờ thêm, thử lại hay gọi `cancel(true)`; yêu cầu hủy bằng interrupt không bảo đảm một tác vụ không hợp tác sẽ lập tức dừng.

Đối với nhiều tác vụ, một cách đơn giản là lưu các `Future` vào danh sách và kiểm tra từng kết quả. Trong hệ thống thực tế, có thể xây dựng một đầu mối thu thập kết quả hoặc hoàn tất để tránh bỏ sót lỗi; đừng chỉ dựa vào việc executor còn đang chạy.

**Giám sát ở mức executor:** `ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` hữu ích khi muốn theo dõi tác vụ, nhưng `t` thường là `null` đối với tác vụ `submit()` đã được bọc trong `FutureTask` vì wrapper đã giữ ngoại lệ. Nếu cài đặt hook, phải xử lý trường hợp `r` là `Future` và đọc kết quả thận trọng (gồm hủy và ngắt), tránh tự làm hỏng worker hoặc chờ sai thời điểm. `UncaughtExceptionHandler` cũng không thay thế được thao tác kiểm tra `Future.get()`.

## 7. Các hiểu lầm và lỗi phổ biến

| Nhận định | Điều chính xác hơn |
| --- | --- |
| “`submit()` nuốt mất exception.” | `Future` thường **giữ** ngoại lệ. Lỗi trở nên khó thấy khi không ai kiểm tra kết quả. |
| “`execute()` luôn ném lỗi về lệnh gọi `execute()`.” | Nếu tác vụ chạy trên worker khác, lỗi xảy ra ở worker; lời gọi gửi có thể đã trả về. Executor chạy trực tiếp trên luồng gọi là trường hợp khác. |
| “`isDone() == true` nghĩa là thành công.” | `isDone()` cũng đúng khi tác vụ thất bại hoặc bị hủy. Cần kiểm tra `get()` hoặc trạng thái phù hợp. |
| “Bọc mọi công việc bằng `submit()` thì lỗi sẽ tự được log.” | Thông thường `submit()` không tự in lỗi của tác vụ ra console. Cần lấy `Future` và có chính sách quan sát. |
| “Một task của pool ném ngoại lệ thì cả pool dừng.” | Với `ThreadPoolExecutor`, worker có thể kết thúc bất thường và pool có thể thay worker; những tác vụ khác không mặc nhiên bị hủy. |
| “Có `UncaughtExceptionHandler` là đủ cho cả hai.” | Wrapper của `submit()` thường đã bắt lỗi, nên handler của worker không nhận lỗi đó. |
| “Bắt `Exception` quanh lời gọi `submit()` là bắt được lỗi của task.” | `try/catch` lúc gửi bắt được lỗi ngay thời điểm gửi (như từ chối). Lỗi sinh ra **sau** khi chạy cần xem `Future`. |

Có một ngoại lệ kỹ thuật cần hiểu đúng: người dùng có thể tự tạo `FutureTask` rồi truyền nó qua `execute()`. Khi ấy chính `FutureTask` sẽ giữ lỗi, dù lời gọi bên ngoài là `execute()`. Vì vậy hành vi lỗi phụ thuộc cả **loại tác vụ đã gửi** và **cách executor thực thi**, không chỉ tên phương thức.

## 8. Tự kiểm tra

**Tình huống A.** Gửi `pool.submit(() -> { throw new IllegalStateException("bad"); });`, bỏ `Future` và tiếp tục xử lý. Liệu người gửi có chắc nhìn thấy lỗi? **Không.** Executor có thể đã giữ lỗi trong `Future` mà không ghi ra console; cần chủ động nhận/quan sát kết quả.

**Tình huống B.** `Future<?> f` đã có `f.isDone() == true` và `f.isCancelled() == false`. Liệu tác vụ chắc thành công? **Không.** Nó vẫn có thể thất bại; `f.get()` sẽ ném `ExecutionException` nếu thất bại.

**Tình huống C.** Sau khi gọi `shutdown()`, cả `execute()` và `submit()` đều có thể bị từ chối. Đây có phải `ExecutionException` sinh ra khi `Future.get()` không? **Không.** Đây là lỗi lúc **gửi công việc** (`RejectedExecutionException`), có thể xảy ra trước khi có `Future`.

Khi thiết kế xử lý lỗi, hãy trả lời hai câu hỏi trước khi chọn API: *Ai chịu trách nhiệm biết tác vụ thành công hay thất bại?* và *Kênh nào chuyển thông tin thất bại tới người đó?* `execute()` phù hợp với lệnh đã có cách giám sát riêng; `submit()` cung cấp một `Future` để người gửi chủ động nhận kết quả và lỗi.