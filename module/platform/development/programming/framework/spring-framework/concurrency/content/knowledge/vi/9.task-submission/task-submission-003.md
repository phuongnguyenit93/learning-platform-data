# Nhận kết quả, kiểm tra hoàn tất và nhận biết hủy qua Future

Khi gửi một tác vụ cho executor, bên gọi thường muốn biết ba điều: **kết quả là gì**, **công việc đã xong chưa**, và **yêu cầu hủy có được chấp nhận không**. Trong Java, `java.util.concurrent.Future<V>` là hợp đồng để truy cập trạng thái và kết quả của một phép tính có thể thực hiện bất đồng bộ. Spring Framework sử dụng chính hợp đồng này thông qua các executor có khả năng `submit`, đặc biệt là `AsyncTaskExecutor` và `ThreadPoolTaskExecutor`.

Điểm cần nhớ ngay từ đầu: **Future đại diện cho một phép tính; Future không tự tạo thread**. Executor quyết định nơi và cách chạy; Future cho bên gọi một *handle* để chờ, đọc kết quả, kiểm tra hoàn tất hoặc đề nghị hủy.

## 1. Từ gửi tác vụ tới nhận Future

Một `TaskExecutor` thuần cung cấp `execute(Runnable)` với kiểu trả về `void`. Muốn có handle kết quả, dùng `ExecutorService.submit(...)` của JDK hoặc `AsyncTaskExecutor.submit(...)` của Spring. `ThreadPoolTaskExecutor` là một implementation của `AsyncTaskExecutor`.

```java
// Mảnh mã minh họa với biến executor đã là một ExecutorService:
Future<Integer> value = executor.submit(() -> 21 * 2);
int answer = value.get(); // 42 sau khi tính xong.
```

Ở đây `submit(Callable<Integer>)` trả `Future<Integer>`. Biểu thức lambda được thực thi theo chính sách của executor; caller giữ Future và quyết định khi nào chờ. Đây là **mảnh mã tích hợp**, cần executor, import và xử lý ngoại lệ trong ngữ cảnh thật.

Có hai dạng gửi phổ biến:

| Cách gửi | Kiểu tác vụ | Handle nhận được | Ý nghĩa kết quả |
| --- | --- | --- | --- |
| `execute(Runnable)` | `Runnable` | Không có `Future` | Chỉ giao công việc |
| `submit(Runnable)` | `Runnable` | `Future<?>` | Nếu hoàn tất bình thường, `get()` trả `null` |
| `submit(Callable<T>)` | `Callable<T>` | `Future<T>` | `get()` trả giá trị `T` hoặc báo trạng thái lỗi/hủy |
| `submit(Runnable, T result)` | JDK `ExecutorService` với `Runnable` | `Future<T>` | `get()` trả `result` đã cung cấp khi chạy thành công |

Dạng `submit(Runnable, T result)` là phương thức của **`ExecutorService` JDK**, không nên mặc định gán nó cho interface `AsyncTaskExecutor` của Spring. Các implementation khác nhau có thể cung cấp thêm chức năng, nhưng code nên lập trình theo đúng kiểu interface đã chọn.

## 2. Các phương thức quan trọng của Future

```java
public interface Future<V> {
    boolean cancel(boolean mayInterruptIfRunning);
    boolean isCancelled();
    boolean isDone();
    V get() throws InterruptedException, java.util.concurrent.ExecutionException;
    V get(long timeout, java.util.concurrent.TimeUnit unit)
        throws InterruptedException, java.util.concurrent.ExecutionException,
               java.util.concurrent.TimeoutException;
}
```

Đây là **phần rút gọn các phương thức cơ bản của Future để học API Java 17**, không phải source interface đầy đủ cho mọi phiên bản Java. Không cần tự khai báo interface này trong ứng dụng.

- **`get()`**: chờ phép tính hoàn tất nếu cần, sau đó lấy giá trị hoặc ném ngoại lệ phản ánh lỗi/hủy. Nếu task chưa xong, thread **gọi get** có thể bị chặn.
- **`get(timeout, unit)`**: chờ tối đa một khoảng thời gian được chỉ định để lấy kết quả; khi chưa có kết quả kịp, ném `TimeoutException`. **Timeout khi chờ không tự hủy task**.
- **`isDone()`**: trả `true` khi phép tính ở trạng thái Future đã hoàn tất, bao gồm **thành công, thất bại hoặc bị hủy**. Nó không cho biết kết quả thành công.
- **`isCancelled()`**: trả `true` nếu Future đã bị hủy thành công trước khi hoàn tất bình thường.
- **`cancel(boolean)`**: thử chuyển Future sang trạng thái hủy. Giá trị `true` trả về có nghĩa yêu cầu hủy Future đã thành công theo hợp đồng của implementation; **không phải bằng chứng mọi thao tác bên ngoài của task đã dừng hoặc hoàn tác**.

Hai cách sử dụng thường đi cùng nhau: dùng `isDone()` để kiểm tra trạng thái không chặn, và dùng `get()` tại điểm cần **xác nhận kết quả cuối cùng, nhận exception và thiết lập quan hệ công bố bộ nhớ**. Gọi `isDone()` liên tục trong vòng lặp bận vừa lãng phí CPU vừa không thay thế thiết kế giao tiếp kết quả rõ ràng.

## 3. Đọc trạng thái Future như một bảng trạng thái

| Trạng thái hợp đồng | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Mới nộp, chưa hoàn tất | `false` | `false` | Có thể phải chờ |
| Hoàn tất bình thường | `true` | `false` | Trả giá trị (hoặc `null` cho Runnable) |
| Hoàn tất bằng exception | `true` | `false` | Ném `ExecutionException` chứa nguyên nhân |
| Đã hủy thành công | `true` | `true` | Ném `CancellationException` |

Sơ đồ trạng thái ở mức **Future**:

```text
       PENDING / RUNNING
         |     |      |
         |     |      +---- cancel thành công ----> CANCELLED
         |     |
         |     +----------- lỗi trong task -------> FAILED
         |
         +----------------- trả về bình thường ---> SUCCESS

   SUCCESS, FAILED, CANCELLED đều làm isDone() == true.
```

Lưu ý kỹ: `isDone() == true` vì **hủy** không đồng nghĩa mọi thread đang chạy tác vụ đó đã ngừng lập tức. `cancel(false)` có thể đánh dấu Future bị hủy trong khi task đã bắt đầu vẫn tiếp tục; `cancel(true)` chỉ **cố gắng** ngắt worker phù hợp với implementation. Hệ thống bên ngoài (database, HTTP, file) cũng không tự rollback nhờ Future bị hủy.

## 4. Một ví dụ Java 17+ chạy độc lập và có stdout xác định

Ví dụ sau thể hiện đủ các nhánh: nhận kết quả thành công, kiểm tra hoàn tất, chờ quá hạn, hủy một task còn xếp hàng và lấy nguyên nhân lỗi. Chương trình dùng executor **một worker**; một `CountDownLatch` giữ worker bận để task cần hủy chắc chắn vẫn nằm trong hàng đợi lúc gọi `cancel(false)`.

Tạo tệp **`FutureStateDemo.java`**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FutureStateDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch runningStarted = new CountDownLatch(1);
        CountDownLatch releaseRunning = new CountDownLatch(1);

        try {
            // 1. Nhận một kết quả thành công.
            Future<Integer> success = pool.submit(() -> 21 * 2);
            System.out.println("result = " + success.get());
            System.out.println("success done = " + success.isDone());

            // 2. Chiếm worker cho đến khi main chủ động thả latch.
            Future<?> running = pool.submit(() -> {
                runningStarted.countDown();
                releaseRunning.await();
                return null;
            });
            runningStarted.await();
            System.out.println("running done = " + running.isDone());

            // Chờ quá hạn không làm task tự dừng.
            try {
                running.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println("wait = timeout");
            }

            // 3. Worker đang bận nên tác vụ sau chắc chắn chờ trong queue.
            Future<String> queued = pool.submit(() -> "unreachable");
            System.out.println("cancel accepted = " + queued.cancel(false));
            System.out.println("cancelled = " + queued.isCancelled());
            System.out.println("cancel done = " + queued.isDone());

            try {
                queued.get();
            } catch (CancellationException ex) {
                System.out.println("cancel get = CancellationException");
            }

            // 4. Giải phóng worker và kiểm tra nguyên nhân của task lỗi.
            releaseRunning.countDown();
            running.get();
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalStateException("boom");
            });
            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failure cause = "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            releaseRunning.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac FutureStateDemo.java
java FutureStateDemo
```

Kết quả chuẩn:

```text
result = 42
success done = true
running done = false
wait = timeout
cancel accepted = true
cancelled = true
cancel done = true
cancel get = CancellationException
failure cause = IllegalStateException
```

**Vì sao kết quả lặp lại ổn định?**

1. `success.get()` chờ phép tính `21*2` nên giá trị đầu là `42`; sau `get()`, Future đó đã hoàn tất.
2. `runningStarted.await()` xác nhận worker đã vào lambda đang chờ `releaseRunning`. Tại điểm đọc, Future của task ấy chưa hoàn tất, và `get(20ms)` phải timeout do latch chưa được thả.
3. Pool chỉ có một worker đang bị giữ; task `queued` chưa thể bắt đầu. Bởi vậy `queued.cancel(false)` chấp nhận hủy mà không phải ngắt một task đang chạy.
4. Future đã hủy có `isCancelled=true`, `isDone=true`, và `get()` ném `CancellationException`, dù task ấy chưa từng chạy.
5. Sau khi thả latch và `running.get()` hoàn tất, task ném `IllegalStateException` được gửi vào pool; `failed.get()` báo `ExecutionException` với `getCause()` là `IllegalStateException`.

Khối `finally` luôn thả latch và yêu cầu đóng pool, tránh để một worker bị giữ vô hạn nếu nhánh khác phát sinh lỗi. Trong ứng dụng Spring thực, pool thường là bean có vòng đời do container quản lý; service **không nên tự shutdown bean pool dùng chung sau mỗi request**.

## 5. Phân biệt chờ kết quả với kiểm tra hoàn tất

Có ba nhu cầu khác nhau:

### Khi bắt buộc cần kết quả ngay lúc này

Gọi `get()` hoặc `get(timeout, unit)` và xử lý tất cả kết quả/ngoại lệ tương ứng. Nếu caller là thread HTTP request, việc gọi `get()` ngay sau `submit()` **vẫn có thể làm request chờ**; “đã dùng thread pool” không đồng nghĩa đường xử lý end-to-end đã trở thành không chặn.

### Khi chỉ cần quan sát trạng thái

Có thể dùng `isDone()` và `isCancelled()` để trả tình trạng task cho giao diện hoặc log. Nhưng `isDone()` không giải thích được task thành công hay thất bại; muốn xác định kết quả và nguyên nhân lỗi, cần `get()` hay cơ chế lưu trạng thái kết quả được thiết kế riêng.

**Không dùng** vòng lặp sau như cơ chế chờ chuẩn:

```java
while (!future.isDone()) {
    // Busy-spin: liên tục hỏi trạng thái và tiêu thụ CPU.
}
```

Đoạn trên là **minh họa cách làm không nên dùng**, giả sử đã có `future`. Nếu cần chờ, dùng `get()`/timeout hoặc kết hợp kết quả bất đồng bộ bằng API như `CompletableFuture`.

### Khi không muốn chờ vô thời hạn

Dùng `get(timeout, unit)`:

```java
try {
    Integer result = future.get(500, TimeUnit.MILLISECONDS);
    useResult(result);
} catch (TimeoutException ex) {
    // Caller hết thời gian đợi; task có thể vẫn chạy.
}
```

Đây là **mảnh mã tích hợp**, cần biến `future`, `useResult` và xử lý thêm các checked exceptions `InterruptedException`, `ExecutionException` trong phương thức chứa nó. `get(timeout)` chỉ áp dụng thời hạn cho **lượt chờ cụ thể**, không tự đặt deadline cho task và không tự kích hoạt hủy.

## 6. Yêu cầu hủy: cancel(false) và cancel(true)

Đối số `mayInterruptIfRunning` quyết định liệu implementation có được **thử ngắt thread đang chạy** task hay không.

| Lệnh gọi | Ý định | Điều không bảo đảm |
| --- | --- | --- |
| `future.cancel(false)` | Hủy Future; không chủ động interrupt worker đang chạy | Không bảo đảm một task đã bắt đầu sẽ ngừng làm việc |
| `future.cancel(true)` | Hủy Future; cho phép thử interrupt thread thực thi | Không buộc mọi code dừng; không tự rollback side effects |
| `future.isCancelled()` | Kiểm tra Future đã bị đánh dấu hủy thành công | Không chứng minh external request hoặc DB transaction đã dừng |
| `future.get()` sau hủy | Ném `CancellationException` | Không chờ cho đến khi mọi side effect của task đang chạy đã chấm dứt |

**Hủy là hợp tác.** Trong Java, `Thread.interrupt()` không giết thread. Các lời gọi chặn hỗ trợ interruption như `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await` thường ném `InterruptedException`. Code CPU-bound phải chủ động kiểm tra cờ interrupt và kết thúc ở vị trí an toàn. Một số thư viện I/O hoặc native API có cơ chế hủy riêng; không được mặc định mọi lời gọi đều đáp ứng interrupt.

Mảnh minh họa task có cơ chế hợp tác:

```java
Future<?> task = executor.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doOneSmallUnitOfWork();
    }
});
task.cancel(true); // Đề nghị ngắt nếu task còn đang chạy.
```

Đây là **mảnh mã tích hợp**, cần `executor`, `doOneSmallUnitOfWork()` và chính sách kết thúc/phục hồi công việc. Nếu `doOneSmallUnitOfWork()` có thể chặn hoặc ném `InterruptedException`, cần xử lý ngắt theo đúng hợp đồng của thao tác. Đừng nuốt interruption rồi lặp vô hạn.

Khi `cancel(false)` gọi trên một task **đang chạy**, nhiều implementation có thể đánh dấu Future là cancelled, nhưng worker vẫn tiếp tục; điều này dễ gây nhầm lẫn nếu chỉ nhìn `isDone=true`. Với task chưa bắt đầu và Future hủy thành công, task đó không nên bắt đầu chạy.

Đặc biệt lưu ý **`CompletableFuture.cancel(true)` khác kỳ vọng ngắt thread kiểu `FutureTask`**: theo JavaDoc của `CompletableFuture`, tham số `mayInterruptIfRunning` không có tác dụng ở implementation này vì interruption không phải cơ chế điều khiển xử lý của nó. Hãy kiểm tra loại Future thực tế trước khi dựa vào hủy bằng interrupt.

## 7. Bốn nhóm ngoại lệ khi nhận kết quả

Khi gọi `get()`/`get(timeout)`, cần phân biệt:

| Ngoại lệ | Nguồn gốc | Cách xử lý thích hợp |
| --- | --- | --- |
| `ExecutionException` | Task chạy và ném exception | Xem `getCause()`; báo lỗi nghiệp vụ hoặc log nguyên nhân |
| `InterruptedException` | **Thread đang chờ** `get` bị interrupt | Tôn trọng yêu cầu dừng; nếu bắt để xử lý, thường khôi phục interrupt flag |
| `CancellationException` | Future bị hủy | Đánh dấu kết quả canceled, tránh xử lý như thành công |
| `TimeoutException` | `get(timeout, unit)` chưa nhận được kết quả trong thời hạn | Xử lý deadline; quyết định riêng có hủy task không |

Mẫu xử lý tại ranh giới service có thời hạn:

```java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    future.cancel(true); // Chính sách tùy nghiệp vụ, không bảo đảm dừng ngay.
    throw new IllegalStateException("Task timed out", ex);
} catch (CancellationException ex) {
    throw new IllegalStateException("Task cancelled", ex);
} catch (ExecutionException ex) {
    throw new IllegalStateException("Task failed", ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Khôi phục trạng thái ngắt.
    throw new IllegalStateException("Wait interrupted", ex);
}
```

Đây là **mảnh phương thức minh họa**, giả sử `future` có kiểu `Future<T>`, phương thức trả `T`, và đã import `java.util.concurrent.*`. Lựa chọn `cancel(true)` khi timeout cần dựa trên khả năng dừng task, tính idempotent và tác dụng phụ; không phải quy tắc mặc định cho mọi ứng dụng.

Khi `get()` phát sinh `ExecutionException`, không nên chỉ log wrapper mà bỏ qua nguyên nhân. Bên trong `getCause()` mới có exception task đã ném. Ngược lại, `InterruptedException` ở caller không phải lỗi nghiệp vụ của worker và cũng **không tự nói task đã bị hủy**.

## 8. Các ranh giới bộ nhớ mà Future đảm bảo

Với `ExecutorService` và các cơ chế executor tuân thủ hợp đồng JDK, các hành động của caller **trước khi gửi task** có quan hệ *happens-before* với hành động trong task. Quan trọng hơn, các hành động của phép tính bất đồng bộ **happen-before** những hành động tiếp theo của thread sau khi lấy kết quả bằng **`Future.get()`**.

```text
caller:  prepare input --> submit(task) .......... get() --> read result
                             |                        ^
worker:                      +--> read input --> write output --> complete
```

Vì vậy, một mô hình hợp lệ là chuẩn bị dữ liệu trước submit, cho task tính toán, rồi chỉ đọc output sau khi `get()` trả về bình thường. Ví dụ trạng thái chia sẻ không có writer cạnh tranh khác có thể được công bố nhờ quan hệ này, ngay cả khi field không khai báo `volatile`.

Nhưng `get()` **không làm phép toán `counter++` nguyên tử**, không loại bỏ race giữa nhiều task và không cho phép đọc state tùy tiện trong lúc task đang chạy. `isDone()` được dùng để hỏi trạng thái; khi cần lập luận chuẩn về công bố dữ liệu và nhận kết quả, hãy dựa vào `get()` hoặc cơ chế đồng bộ có hợp đồng rõ ràng.

## 9. Trong Spring: AsyncTaskExecutor, ThreadPoolTaskExecutor và @Async

Spring `TaskExecutor` chỉ có `execute(Runnable)`. `AsyncTaskExecutor` mở rộng hợp đồng và cung cấp khả năng submit. `ThreadPoolTaskExecutor` là implementation thường dùng khi muốn cấu hình core/max/queue và lấy Future.

Ví dụ cấu hình bean trong Spring Framework (các snippet cần dependency `spring-context`, được container đăng ký, không phải chương trình JDK độc lập):

```java
@Configuration(proxyBeanMethods = false)
public class WorkerConfig {
    @Bean("workerPool")
    public ThreadPoolTaskExecutor workerPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(16);
        pool.setThreadNamePrefix("worker-");
        return pool;
    }
}
```

Giả sử một bean nhận `AsyncTaskExecutor` thông qua constructor/qualifier:

```java
Future<Integer> future = executor.submit(() -> expensiveCalculation());
try {
    Integer value = future.get(300, TimeUnit.MILLISECONDS);
    useValue(value);
} catch (TimeoutException ex) {
    // Tác vụ có thể vẫn chạy. Quyết định riêng có hủy hay trả trạng thái đang xử lý.
}
```

Đoạn trên cần import `AsyncTaskExecutor`, `Future`, `TimeUnit`, `TimeoutException` và xử lý các ngoại lệ còn lại. Lựa chọn thời gian chờ cần căn cứ SLO và nghiệp vụ; 300 ms chỉ là ví dụ.

Với phương thức `@Async`, khi đã bật `@EnableAsync` và lời gọi đi qua Spring proxy, phương thức có thể trả `Future<T>` hoặc `CompletableFuture<T>` để caller nhận handle:

```java
@Async("workerPool")
public CompletableFuture<Integer> calculate(int x) {
    return CompletableFuture.completedFuture(x * 2);
}
```

Trong ngữ cảnh này, đoạn code ở trên là **mảnh phương thức trong một Spring-managed bean**, cần khai báo import, `@EnableAsync`, bean executor và lời gọi **từ bên ngoài qua proxy**. `this.calculate(...)` tự gọi bên trong cùng object ở chế độ proxy mặc định thường bỏ qua cơ chế async. Phương thức trả `void` được đánh dấu `@Async` không mang `Future` về cho caller; để quan sát trạng thái/lỗi/kết quả, cần giao thức khác.

**Không nên gọi `get()` ngay trong chính executor có ít worker nếu kết quả phụ thuộc vào một task khác đang chờ cùng pool**: điều này có thể làm tất cả worker bị chặn trong khi task cần chạy không có worker rảnh, dẫn đến starvation/deadlock. Hãy thiết kế phụ thuộc bằng `CompletableFuture`/completion stages, pool phù hợp hoặc cấu trúc không chặn khi có thể.

## 10. Future và CompletableFuture giống, khác nhau ở đâu?

`CompletableFuture<T>` **implements `Future<T>`**, nên cũng có `get()`, `get(timeout)`, `isDone()`, `isCancelled()` và `cancel(...)`. Nhưng nó bổ sung khả năng hoàn tất một cách tường minh, kết hợp các stage và lập trình callback.

| Nhu cầu | `Future<T>` cơ bản | `CompletableFuture<T>` |
| --- | --- | --- |
| Chờ/đọc kết quả | `get()` | `get()`, `join()` |
| Kiểm tra trạng thái | `isDone()`, `isCancelled()` | Các phương thức Future, cộng API stage |
| Lấy exception | `ExecutionException` qua `get()` | `get()` hoặc `join()` thường ném `CompletionException` khi lỗi |
| Ghép phép tính | Không có API stage trong hợp đồng Java 17 `Future` | `thenApply`, `thenCompose`, `handle`, `exceptionally`... |
| Yêu cầu hủy bằng interrupt | Phụ thuộc implementation và `cancel(true)` | `cancel(true)` không dùng interrupt để dừng tính toán trong implementation này |

Ví dụ ghép kết quả, chỉ là **mảnh mã API** với `CompletableFuture<Integer> first` đã có:

```java
CompletableFuture<String> label = first.thenApply(x -> "Result = " + x);
String text = label.join();
```

`join()` cũng có thể chặn; nó báo lỗi qua các unchecked exceptions như `CompletionException`, còn `get()` khai báo checked `ExecutionException` và `InterruptedException`. Dù chọn kiểu nào, người dùng cần hiểu trạng thái terminal và chính sách timeout/hủy. `CompletableFuture` không tự bảo đảm một callback sẽ chạy trên thread nào: việc dùng biến thể `Async` và executor được chỉ định ảnh hưởng cách lập lịch.

## 11. Cần quan sát nhiều tác vụ? Đừng nhầm một Future với cả lô

Mỗi Future thường đại diện cho **một lần submit**. Nếu gửi ba task riêng, `futureA.isDone()` không nói `futureB` đã xong. Muốn chờ tất cả, lưu từng Future và gọi `get()` trên từng cái hoặc dùng cơ chế tổng hợp như `CompletableFuture.allOf` khi các tác vụ có kiểu thích hợp.

Ví dụ với `ExecutorService` JDK đã được tạo:

```java
List<Future<Integer>> tasks = new ArrayList<>();
for (int i = 1; i <= 3; i++) {
    final int input = i;
    tasks.add(executor.submit(() -> input * 10));
}
for (Future<Integer> task : tasks) {
    System.out.println(task.get());
}
```

Đây là **mảnh mã minh họa**, cần import và executor, không phải file Java độc lập. Các kết quả được in theo thứ tự **duyệt danh sách và chờ** `get()`, không chứng minh thứ tự thực thi hay hoàn thành trong pool giống nhau. Với nhiều task, cân nhắc tổng deadline thay vì cấp mỗi `get(timeout)` một khoảng riêng quá dài làm tổng thời gian vượt hạn mức yêu cầu.

Một lỗi kiến trúc khác: gọi `cancel()` trên một Future không tự hủy toàn bộ các task phụ thuộc nó, một request HTTP đang chạy ngoài process hoặc transaction trên worker khác. Hủy theo nhóm cần được thiết kế riêng, có nhận diện task và xử lý partial completion.

## 12. Hủy tác vụ không đồng nghĩa hoàn tác nghiệp vụ

Giả sử task đã:

1. Ghi một bản ghi vào database.
2. Gửi yêu cầu thanh toán qua HTTP.
3. Bị caller `cancel(true)` trước khi nhận response.

Future có thể chuyển sang trạng thái canceled, nhưng các tác dụng phụ ở bước 1–2 vẫn có thể đã xảy ra. Vì thế một thiết kế cần hủy thực sự nên phân biệt:

- **Hủy handle/chờ**: caller không còn muốn lấy kết quả.
- **Yêu cầu worker dừng**: worker kiểm tra cờ interrupt hoặc cờ cancellation của ứng dụng, rồi dừng ở điểm an toàn.
- **Hủy tác vụ tại dịch vụ ngoài**: có thể cần API riêng để dừng công việc đã gửi đi.
- **Bù trừ/khôi phục nghiệp vụ**: nếu đã ghi dữ liệu hoặc gọi dịch vụ ngoài, cần giao dịch, idempotency key hoặc luồng bù trừ theo nghiệp vụ; Future không làm thay.

Ngoài ra, **timeout ở caller không đảm bảo timeout ở worker hoặc downstream**. Một hệ thống có thể hết thời gian chờ HTTP trong 500 ms nhưng task chạy thêm nhiều giây. Cần phối hợp deadline, timeout của HTTP/DB client, vòng đời job và cơ chế tránh xử lý trùng.

## 13. Những lỗi thường gặp

1. **Nhầm `submit` với `get`.** `submit` tạo một Future, không tự đảm bảo đã có kết quả tại thời điểm trả về; `get` mới là thao tác chờ/lấy kết quả.
2. **Thấy `isDone=true` rồi kết luận thành công.** Future cũng hoàn tất do lỗi hoặc bị hủy; phải phân loại.
3. **Thấy `cancel(true)` trả true rồi coi thread đã chết.** Interruption chỉ là yêu cầu hợp tác, không phải cưỡng bức dừng và không rollback tác dụng phụ.
4. **Dùng `get(timeout)` và cho rằng task tự bị hủy.** `TimeoutException` chỉ nói lượt chờ hết hạn; chính sách hủy là quyết định riêng.
5. **Nuốt `InterruptedException` rồi tiếp tục chờ vô hạn.** Khi bắt ngắt ở caller, thường khôi phục cờ ngắt và kết thúc luồng xử lý phù hợp.
6. **Đọc `ExecutionException` mà không xem `getCause()`.** Nguyên nhân thực sự nằm ở exception do task ném.
7. **Đọc shared state trước khi Future hoàn tất.** Có thể xảy ra data race hoặc thấy giá trị cũ; sử dụng kết quả trả về hay cơ chế đồng bộ rõ.
8. **Gọi `get()` ngay sau mọi lần submit và tưởng đang xử lý song song.** Điều đó có thể tuần tự hóa caller; submit các task độc lập trước rồi lấy kết quả phù hợp.
9. **Chặn worker của pool để đợi task khác trong cùng pool.** Có thể dẫn đến starvation/deadlock; nên thiết kế phụ thuộc theo completion stage hoặc tách cơ chế thực thi.
10. **Nhầm `@Async` với lời gọi Java trực tiếp.** Trong mô hình proxy Spring, tự gọi `this.method()` không đi qua interceptor async.
11. **Giữ Future chỉ trong bộ nhớ rồi xem nó như trạng thái job bền vững.** Khi JVM khởi động lại, handle và trạng thái nội bộ mất; công việc dài hạn cần kho trạng thái/broker bền vững nếu nghiệp vụ yêu cầu.
12. **Không xử lý rejection lúc submit.** Khi executor quá tải hoặc đã đóng, `submit` có thể ném exception ngay; lúc đó chưa có Future hợp lệ để theo dõi.

## 14. Tự kiểm tra hiểu bài

**Câu 1.** `Future.isDone()` trả `true`. Có thể khẳng định đã nhận được kết quả thành công không?  
**Đáp án:** Không. Nó cũng true khi lỗi hoặc hủy; phải đọc kết quả/ngoại lệ hoặc kiểm tra trạng thái bổ sung.

**Câu 2.** `future.get(200, MILLISECONDS)` ném `TimeoutException`. Task có bị dừng không?  
**Đáp án:** Không tự động. Future có thể vẫn đang chờ hoặc chạy; muốn hủy cần gọi `cancel` theo chính sách thích hợp và task phải hỗ trợ dừng an toàn.

**Câu 3.** Một task đang thực hiện HTTP call; `cancel(true)` trả `true`. Có bảo đảm HTTP request đã được server bên kia hủy không?  
**Đáp án:** Không. Có thể đã có side effect; cần timeout/hủy ở HTTP client và cơ chế riêng ở hệ thống đích.

**Câu 4.** `get()` ném `ExecutionException`. Exception nghiệp vụ gốc ở đâu?  
**Đáp án:** `getCause()` của `ExecutionException`.

**Câu 5.** Cần một giá trị số nguyên từ task Spring. Nên chọn `TaskExecutor.execute` hay `AsyncTaskExecutor.submit(Callable<Integer>)`?  
**Đáp án:** `submit(Callable<Integer>)` cho `Future<Integer>` phù hợp với nhu cầu nhận kết quả.

**Câu 6.** Tại sao Future bị hủy vẫn có `isDone=true` dù worker có thể chưa dừng?  
**Đáp án:** `isDone` phản ánh trạng thái terminal **của Future**, không xác nhận mọi side effect hoặc thread thực thi đã chấm dứt vật lý.

Tóm lại, dùng **`get` để lấy kết quả**, **`isDone` để xem Future đã đi tới trạng thái cuối hay chưa**, **`isCancelled` để nhận biết trạng thái hủy**, và **`cancel` để yêu cầu hủy theo khả năng hợp tác của implementation**. Để vận hành chắc chắn, cần tính đến timeout, interruption, lỗi trong task và các tác dụng phụ đã phát sinh.

### Tài liệu tham khảo

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Spring Framework — AsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
