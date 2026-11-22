# `orTimeout`, `completeOnTimeout` và việc tác vụ có thực sự dừng hay không

Khi làm việc với `CompletableFuture`, ta thường muốn quy định: “Nếu công việc chưa xong sau một khoảng thời gian thì báo lỗi hoặc trả giá trị dự phòng”. Java cung cấp `orTimeout(...)` và `completeOnTimeout(...)` để giải quyết nhu cầu đó. Tuy nhiên, **future đã hết hạn không đồng nghĩa luồng đang tính toán đã dừng**.

Đây là một phân biệt quan trọng khi xử lý ngoại lệ, hủy tác vụ và tài nguyên trong hệ thống bất đồng bộ. Một yêu cầu có thể đã trả `TimeoutException` cho người gọi trong khi tác vụ bên dưới vẫn tiếp tục đọc dữ liệu, giữ kết nối, tính toán hoặc ghi vào hệ thống khác. Bài học này giải thích chính xác điều gì được bảo đảm, điều gì không được bảo đảm và cách thiết kế giới hạn thời gian an toàn.

## 1. Hai đối tượng khác nhau: kết quả được quan sát và công việc đang chạy

Hãy phân biệt:

- **Công việc thực tế**: đoạn mã trong `Supplier`, `Runnable`, `Callable`, hoặc một stage bất đồng bộ. Nó có thể chạy trên `ForkJoinPool.commonPool()` hoặc một `Executor` được chỉ định.
- **`CompletableFuture`**: đối tượng đại diện cho một kết quả hoàn tất bình thường, hoàn tất thất bại hoặc bị hủy. Người gọi có thể đọc kết quả qua `join()`, `get()` hoặc callback.
- **Giới hạn thời gian** (*deadline/timeout*): thời điểm đến hạn để chọn kết quả quan sát. Giới hạn này không tự cung cấp cơ chế dừng logic bên trong công việc.

Mô hình:

```text
Người gọi                        Worker thực thi
    |                                  |
    |-- supplyAsync(...) ------------->| bắt đầu tác vụ
    |                                  | đang chờ / xử lý
    |-- orTimeout(100 ms)              |
    |                                  | vẫn đang xử lý
    |<-- future hoàn tất với lỗi ------| 100 ms đến hạn
    |    TimeoutException             |
    |                                  | có thể tiếp tục
    |                                  | có thể tạo tác dụng phụ
    |                                  | sau đó trả kết quả thật
    |                                  v
    |                          kết quả thật đến quá muộn,
    |                          không thay kết quả timeout
```

Nếu công việc đã bắt đầu thì `orTimeout`/`completeOnTimeout` **không hứa sẽ ngắt luồng hoặc hủy I/O đang diễn ra**. Ngược lại, nếu công việc chưa khởi chạy, cơ chế thực thi cụ thể có thể bỏ qua phần tính toán sau khi future đã hoàn tất. Không suy ra một quy tắc tuyệt đối “luôn chạy hết” hoặc “luôn bị dừng”; điều API bảo đảm là cách `CompletableFuture` **hoàn tất**.

## 2. So sánh hợp đồng hai API

Cả hai phương thức đều có từ Java 9, nên sử dụng bình thường trên Java 17+:

```java
CompletableFuture<T> orTimeout(long timeout, TimeUnit unit);
CompletableFuture<T> completeOnTimeout(T value, long timeout, TimeUnit unit);
```

Đây là **chữ ký minh họa** của các phương thức generic, không phải chương trình Java độc lập.

| Thuộc tính | `orTimeout(timeout, unit)` | `completeOnTimeout(value, timeout, unit)` |
| --- | --- | --- |
| Nếu future chưa hoàn tất khi hết hạn | Hoàn tất **thất bại** với `TimeoutException` | Hoàn tất **bình thường** bằng `value` dự phòng |
| `join()` sau khi timeout thắng | Thường ném `CompletionException`, `getCause()` là `TimeoutException` | Trả `value` |
| `get()` sau khi timeout thắng | Ném `ExecutionException`, `getCause()` là `TimeoutException` | Trả `value` |
| `isCompletedExceptionally()` nếu timeout thắng | `true` | `false` |
| `isDone()` nếu timeout thắng | `true` | `true` |
| `isCancelled()` vì riêng thao tác timeout | `false` | `false` |
| Có tự ngắt luồng đang chạy không? | **Không bảo đảm; không thực hiện yêu cầu ngắt công việc** | **Không bảo đảm; không thực hiện yêu cầu ngắt công việc** |
| Đối tượng trả về | **Chính future được gọi**, không phải một bản sao | **Chính future được gọi**, không phải một bản sao |

Điểm dễ nhầm nhất là **cả hai sửa trạng thái của cùng `CompletableFuture`** nếu timeout đến trước kết quả thật. Viết `CompletableFuture<T> timed = source.orTimeout(...)` không tạo một “lớp quan sát độc lập” trên `source`; `timed == source` là `true`.

Tương tự, `completeOnTimeout(fallback, ...)` không lưu “cả giá trị gốc lẫn fallback” để chọn lại sau này. Khi future đã hoàn tất bằng fallback, một nỗ lực hoàn tất bình thường từ tác vụ đến muộn không thể thay thế kết quả đó bằng `complete(...)` thông thường.

## 3. Thứ tự hoàn tất: ai thắng cuộc đua?

Cả hai API đều đặt một khả năng hoàn tất **nếu future vẫn chưa xong vào lúc đến hạn**. Hệ thống có một cuộc đua giữa kết quả thật và hành động timeout:

```text
                    Future chưa hoàn tất
                             |
                 +-----------+-----------+
                 |                       |
      Tác vụ hoàn tất trước          Timeout đến trước
                 |                       |
      kết quả/lỗi thật thắng      +--------+--------+
                                 |                 |
                             orTimeout      completeOnTimeout
                                 |                 |
                           TimeoutException     fallback
```

Nếu tác vụ hoàn tất trước hạn, timeout không thay đổi kết quả thật. Nếu timeout hoàn tất future trước, kết quả được tạo sau đó thường không thể ghi đè trạng thái đã được chốt. Nếu hai sự kiện đến sát nhau, **không được dựa vào thứ tự theo cảm giác hoặc số mili giây ghi trong log**; hành động hoàn tất nào thắng cuộc đua mới quyết định kết quả.

Các điểm cần nhớ:

1. Thời hạn tính từ lúc **gọi phương thức đặt timeout**, không phải mặc định từ khi worker thực sự bắt đầu chạy. Tác vụ còn xếp hàng trong executor vẫn có thể hết hạn trước khi chạy.
2. Thời gian biểu kiến có thể lệch vì lịch chạy của JVM, tải máy và việc callback được kích hoạt. Timeout là chính sách giới hạn chờ/kết quả, không phải đồng hồ thời gian thực với sai số bằng 0.
3. Nếu future đã hoàn tất từ trước, gọi hai API không đổi trạng thái đã chốt; một timeout đặt sau đó không làm kết quả cũ biến mất.
4. Một stage mới có thể phụ thuộc vào future đã bị timeout. Khi `orTimeout` thắng, các nhánh chỉ xử lý thành công như `thenApply` thường bỏ qua phần xử lý giá trị và truyền trạng thái lỗi. Khi `completeOnTimeout` thắng, chúng có thể chạy với **fallback như thể đó là giá trị thành công**.
5. `isDone()` không cho biết đã thành công, lỗi, hủy hay chạy xong công việc vật lý. Đây chỉ là dấu hiệu **future đã hoàn tất**.

## 4. Ví dụ Java 17+ có thể chạy: future hết hạn nhưng worker vẫn hoạt động

Ví dụ dùng `CountDownLatch` để chắc chắn worker đã bắt đầu và cố tình chờ tín hiệu giải phóng từ `main`. Nhờ vậy, lúc deadline xảy ra, ta biết công việc thật **chưa kết thúc**. Ta kiểm chứng riêng hai API trên hai future độc lập, không đặt cả hai timeout lên cùng một future.

Tạo tệp **`TimeoutRealityDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TimeoutRealityDemo {
    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Demo synchronization timed out");
        }
    }

    private static CompletableFuture<String> blockedWork(
            ExecutorService pool,
            CountDownLatch started,
            CountDownLatch release,
            CountDownLatch finished) {
        return CompletableFuture.supplyAsync(() -> {
            started.countDown();
            try {
                release.await();
                return "real result";
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new CompletionException(exception);
            } finally {
                finished.countDown();
            }
        }, pool);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch releaseError = new CountDownLatch(1);
        CountDownLatch releaseFallback = new CountDownLatch(1);

        try {
            CountDownLatch startedError = new CountDownLatch(1);
            CountDownLatch finishedError = new CountDownLatch(1);
            CompletableFuture<String> originalError =
                    blockedWork(pool, startedError, releaseError, finishedError);
            await(startedError);

            CompletableFuture<String> timed =
                    originalError.orTimeout(150, TimeUnit.MILLISECONDS);
            System.out.println("orTimeout same future: "
                    + (timed == originalError));

            try {
                timed.join();
            } catch (CompletionException exception) {
                System.out.println("orTimeout cause: "
                        + exception.getCause().getClass().getSimpleName());
            }

            System.out.println("orTimeout work finished at deadline: "
                    + (finishedError.getCount() == 0));
            releaseError.countDown();
            await(finishedError);
            System.out.println("orTimeout still exceptional: "
                    + originalError.isCompletedExceptionally());

            CountDownLatch startedFallback = new CountDownLatch(1);
            CountDownLatch finishedFallback = new CountDownLatch(1);
            CompletableFuture<String> originalFallback =
                    blockedWork(pool, startedFallback, releaseFallback,
                            finishedFallback);
            await(startedFallback);

            CompletableFuture<String> fallback =
                    originalFallback.completeOnTimeout(
                            "fallback", 150, TimeUnit.MILLISECONDS);
            System.out.println("completeOnTimeout same future: "
                    + (fallback == originalFallback));
            System.out.println("completeOnTimeout result: " + fallback.join());
            System.out.println("completeOnTimeout work finished at deadline: "
                    + (finishedFallback.getCount() == 0));

            releaseFallback.countDown();
            await(finishedFallback);
            System.out.println("completeOnTimeout result after work: "
                    + originalFallback.join());
        } finally {
            releaseError.countDown();
            releaseFallback.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TimeoutRealityDemo.java
java TimeoutRealityDemo
```

Đầu ra:

```text
orTimeout same future: true
orTimeout cause: TimeoutException
orTimeout work finished at deadline: false
orTimeout still exceptional: true
completeOnTimeout same future: true
completeOnTimeout result: fallback
completeOnTimeout work finished at deadline: false
completeOnTimeout result after work: fallback
```

**Giải thích các kết quả:**

- Hai dòng `same future: true` chứng minh kết quả phương thức là cùng đối tượng được gọi. Không có future độc lập được tạo ra chỉ bằng hai phương thức timeout này.
- Nhánh `orTimeout`: `join()` kết thúc với `CompletionException`, bên trong là `TimeoutException`. `finishedError` vẫn chưa được giảm về 0 vì worker còn đang chờ `releaseError`. Như vậy **future đã thất bại do timeout trước khi công việc thật kết thúc**.
- Sau khi `main` mở khóa cho worker, công việc thực tế đi đến cuối và trả `"real result"`; nhưng `originalError` vẫn `isCompletedExceptionally() == true`, vì trạng thái lỗi timeout đã thắng trước đó.
- Nhánh `completeOnTimeout`: `join()` trả `"fallback"` dù worker chưa xong. Sau khi worker được giải phóng và trả kết quả thật, future vẫn trả `"fallback"` vì kết quả dự phòng đã hoàn tất future từ trước.

Ví dụ đợi `started` trước khi đặt thời hạn và chỉ giải phóng worker **sau khi** quan sát timeout; kết quả không phụ thuộc vào việc hệ điều hành chọn chạy worker nhanh hay chậm. Các lệnh chờ có giới hạn năm giây bảo vệ chương trình thử nghiệm khỏi treo vô hạn nếu môi trường gặp sự cố. Trong ứng dụng thật, không nên để tác vụ đợi latch nhân tạo như vậy; đây chỉ là công cụ chứng minh sự khác biệt giữa **hoàn tất `CompletableFuture`** và **hoàn tất xử lý thực tế**.

## 5. `get(timeout, unit)` khác gì `orTimeout` và `completeOnTimeout`?

Một phương thức dễ bị nhầm với hai API trên là:

```java
T result = future.get(100, TimeUnit.MILLISECONDS);
```

Đây là đoạn minh họa trong phạm vi đã có `future`, có kiểu kết quả `T` và xử lý các checked exception. `get(timeout, unit)` giới hạn **thời gian một lần gọi đang chờ**, không tự chuyển future chưa xong thành trạng thái lỗi timeout. Nếu hết thời gian chờ, lần gọi đó ném trực tiếp `TimeoutException`, còn future có thể tiếp tục chưa hoàn tất và sau đó cho kết quả thành công.

| API | Điều bị giới hạn | Tác động lên trạng thái future khi hết hạn | Ngoại lệ/giá trị nhìn thấy |
| --- | --- | --- | --- |
| `future.get(100, MILLISECONDS)` | Lần gọi **chờ kết quả** của luồng hiện tại | Không tự hoàn tất future | Ném `TimeoutException` trực tiếp ở lời gọi chờ |
| `future.orTimeout(100, MILLISECONDS)` | Thời hạn để **future còn được phép chờ hoàn tất** | Chuyển future chưa xong thành hoàn tất lỗi | `join()` thường ném `CompletionException` bọc `TimeoutException`; `get()` ném `ExecutionException` bọc cause |
| `future.completeOnTimeout(fallback, 100, MILLISECONDS)` | Thời hạn để future nhận kết quả thật trước fallback | Chuyển future chưa xong thành hoàn tất bình thường | `join()`/`get()` trả `fallback` |

`get(timeout, unit)` còn có thể ném `InterruptedException` khi **luồng đang chờ** bị ngắt, `ExecutionException` nếu công việc đã hoàn tất lỗi, và `CancellationException` nếu future bị hủy. Đây là những đường đi khác `TimeoutException` của chính lời gọi chờ.

Ví dụ thứ hai còn cho thấy cách đặt deadline lên **một stage phụ thuộc** để giới hạn kết quả dành cho người gọi mà giữ nguyên future nguồn.

Tạo tệp **`TimeoutViewDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutViewDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> original = new CompletableFuture<>();

        try {
            original.get(50, TimeUnit.MILLISECONDS);
        } catch (TimeoutException exception) {
            System.out.println("get wait timed out: true");
        }

        System.out.println("original done after get: " + original.isDone());
        original.complete("ready");
        System.out.println("original after completion: " + original.join());

        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> view = source.thenApply(value -> value);
        view.orTimeout(50, TimeUnit.MILLISECONDS);

        try {
            view.join();
        } catch (CompletionException exception) {
            System.out.println("view cause: "
                    + exception.getCause().getClass().getSimpleName());
        }

        System.out.println("source done at view deadline: " + source.isDone());
        source.complete("late success");
        System.out.println("source after completion: " + source.join());
        System.out.println("view still exceptional: "
                + view.isCompletedExceptionally());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TimeoutViewDemo.java
java TimeoutViewDemo
```

Đầu ra:

```text
get wait timed out: true
original done after get: false
original after completion: ready
view cause: TimeoutException
source done at view deadline: false
source after completion: late success
view still exceptional: true
```

Giải thích: `original.get(...)` hết hạn nhưng `original.isDone()` vẫn `false`, nên lời gọi `complete("ready")` vẫn tạo ra kết quả thành công. Ở ví dụ `source`/`view`, `thenApply(value -> value)` tạo **một `CompletableFuture` phụ thuộc mới**; đặt `orTimeout` trên `view` chỉ làm **view** hoàn tất lỗi. `source` vẫn có thể hoàn tất bình thường với `"late success"` và vẫn giữ kết quả đó. Cách này tách “deadline hiển thị cho người gọi” ra khỏi future nguồn; nó **vẫn không tự dừng công việc** tạo ra `source`.

Không áp dụng mẹo tạo stage phụ thuộc một cách máy móc nếu thiết kế yêu cầu ngăn tất cả tác dụng phụ sau khi timeout. Khi ấy, cần một giao thức dừng riêng ở tầng thực thi.

## 6. Vậy `cancel(true)` có dừng tác vụ của `CompletableFuture` không?

Đối với **chính triển khai `CompletableFuture`**, `cancel(mayInterruptIfRunning)` chuyển một future chưa hoàn tất sang trạng thái bị hủy bằng `CancellationException`. Tài liệu API nói rõ đối số `mayInterruptIfRunning` **không có tác dụng trong triển khai này vì không dùng interrupt để điều khiển việc xử lý**.

Vì thế:

- `completableFuture.cancel(true)` không bảo đảm interrupt được luồng đang chạy supplier.
- `isCancelled() == true` nghĩa là **đối tượng future** đã ở trạng thái hủy, không xác nhận mã của supplier đã kết thúc.
- Nếu một future **trực tiếp** bị hủy, `join()`/`get()` có thể ném `CancellationException` trực tiếp. Với stage phụ thuộc, ngoại lệ có thể được bọc trong `CompletionException`.
- `orTimeout` không đồng nghĩa `cancel(true)`: nó hoàn tất lỗi bằng `TimeoutException`. `completeOnTimeout` còn hoàn tất **bình thường** bằng fallback.

Cần phân biệt với **`Future` trả về từ `ExecutorService.submit(...)`**: triển khai thông dụng dùng `FutureTask`, khi `cancel(true)` có thể cố ngắt luồng tác vụ đang chạy. Đó vẫn là **yêu cầu ngắt hợp tác**; mã không phản hồi interrupt hoặc đang mắc trong I/O không hỗ trợ ngắt có thể không dừng tức khắc. Đừng chuyển kết luận của `FutureTask` sang `CompletableFuture` một cách tự động.

Nếu ứng dụng phải dừng một thao tác cụ thể sau khi hết hạn, hãy thiết kế **quyền điều khiển công việc** ở bên thực thi, chẳng hạn một `Future<?>` điều khiển được, tín hiệu hủy do ứng dụng sở hữu, thời hạn I/O do client hỗ trợ, hoặc API hủy chính thức của thư viện. Sau khi yêu cầu hủy, vẫn cần chờ/xác nhận công việc đã dừng nếu bước tiếp theo đòi hỏi điều đó.

## 7. Chiến lược hủy hợp tác và giới hạn I/O

Timeout ở tầng `CompletableFuture` nên được kết hợp với chính sách thực thi cụ thể:

### 7.1. Công việc CPU

Nếu một vòng lặp tính toán kéo dài và phải hỗ trợ hủy, hãy kiểm tra trạng thái yêu cầu dừng ở các điểm hợp lý. Khi công việc chạy trong ngữ cảnh mà luồng **thực sự được ngắt**, có thể kiểm tra `Thread.currentThread().isInterrupted()` và kết thúc an toàn. Với `CompletableFuture.orTimeout` riêng lẻ, đừng chờ cờ interrupt tự xuất hiện: API này không gửi nó.

Nếu mã có thể nhận một cờ hủy riêng, ví dụ `AtomicBoolean stopRequested`, vòng lặp có thể kiểm tra cờ đó để quyết định dừng. Cần đảm bảo chính cơ chế quản lý deadline/hủy của ứng dụng thực sự đặt cờ. Chỉ tạo cờ rồi không có ai cập nhật thì không có hiệu quả.

### 7.2. Công việc đang chờ

Các thao tác như `BlockingQueue.take()`, `Thread.sleep()` hoặc `Future.get()` có thể phản ứng với `InterruptedException` khi luồng đang thực thi chúng bị ngắt. Tác vụ nên bắt ngắt ở tầng phù hợp, khôi phục trạng thái bằng `Thread.currentThread().interrupt()` nếu không truyền ngoại lệ lên, rồi kết thúc và dọn dẹp. Nhưng **timeout của `CompletableFuture` không tự kích hoạt bước ngắt này**.

### 7.3. I/O từ xa, cơ sở dữ liệu và dịch vụ ngoài

Một yêu cầu mạng vẫn có thể tiếp tục dùng socket hoặc tạo tác dụng phụ sau khi future đã timeout. Vì vậy:

1. Cấu hình timeout ở **client I/O** (kết nối, đọc, toàn bộ lời gọi) hoặc API deadline do thư viện cung cấp.
2. Nếu client có cơ chế hủy thật, gắn nó với vòng đời của yêu cầu. Kiểm tra hợp đồng xem hủy có giải phóng tài nguyên và ngăn phản hồi đến muộn không.
3. Với thao tác có tác dụng phụ như chuyển tiền, ghi đơn hàng hoặc phát sự kiện, dùng khóa idempotency hoặc thiết kế tránh xử lý lặp. Một lần “timeout ở người gọi” không chứng minh thao tác phía máy chủ chưa thực hiện.
4. Theo dõi thời điểm bắt đầu, thời điểm báo timeout, thời điểm công việc thật kết thúc và thời gian giữ tài nguyên; hai thời điểm này có thể khác nhau nhiều.

Timeout bảo vệ **thời gian chờ của người gọi**. Muốn bảo vệ **tài nguyên và tính đúng đắn khi dừng công việc**, phải kết hợp cơ chế dừng/hạn mức thích hợp.

## 8. Thiết kế pipeline an toàn: không vô tình che lỗi hoặc làm hỏng nguồn

### 8.1. Dùng `orTimeout` khi quá hạn phải là lỗi

Nếu công việc trả về quá muộn là không hợp lệ đối với hợp đồng API, có thể dùng:

```java
CompletableFuture<Response> result =
        loadAsync().orTimeout(2, TimeUnit.SECONDS);
```

Đây là đoạn minh họa yêu cầu kiểu `Response` và hàm `loadAsync()` của ứng dụng. Nếu `loadAsync()` trả về một future đang được nhiều nơi dùng chung, gọi `orTimeout` **sẽ áp thời hạn lên chính future đó**, tác động tới mọi người đang quan sát nó. Nếu cần timeout riêng cho một người gọi, tạo một dependent stage rồi áp thời hạn lên stage phụ thuộc:

```java
CompletableFuture<Response> shared = loadAsync();
CompletableFuture<Response> callerView =
        shared.thenApply(value -> value)
                .orTimeout(2, TimeUnit.SECONDS);
```

Đây cũng là đoạn minh họa cần `loadAsync()` và kiểu `Response`. `shared` không bị timeout trực tiếp từ `callerView`. `callerView` chỉ giới hạn cách người gọi này nhận kết quả; công việc nền của `shared` vẫn cần cơ chế dừng riêng nếu thật sự muốn hủy.

### 8.2. Dùng `completeOnTimeout` khi giá trị dự phòng là kết quả hợp lệ

```java
CompletableFuture<String> displayName =
        fetchDisplayNameAsync()
                .completeOnTimeout("Ẩn danh", 300, TimeUnit.MILLISECONDS);
```

Đây là đoạn minh họa cần `fetchDisplayNameAsync()` của ứng dụng. Cách này hữu ích cho dữ liệu phục vụ hiển thị mà việc fallback được chấp nhận. Nhưng `displayName.isCompletedExceptionally()` sẽ trả `false` nếu fallback thắng; các stage sau có thể nhìn thấy `"Ẩn danh"` như giá trị thành công. Nếu cần phân biệt fallback với thành công thật, thay kiểu dữ liệu trả về bằng cấu trúc thể hiện **nguồn kết quả** (*REAL* hoặc *FALLBACK*) hoặc ghi chỉ số riêng về timeout.

Không nên dùng fallback thành công âm thầm cho một công việc mà “thành công thật” là điều kiện bắt buộc, chẳng hạn xác nhận thanh toán. Người gọi có thể tưởng tác vụ gốc thành công trong khi nó chỉ hết hạn và vẫn đang chạy.

### 8.3. Không đặt cả hai phương thức lên cùng future để mong “lỗi rồi dự phòng”

Ví dụ:

```java
future.orTimeout(100, TimeUnit.MILLISECONDS)
      .completeOnTimeout(fallback, 200, TimeUnit.MILLISECONDS);
```

Đây là ví dụ **về thiết kế cần tránh**, không phải chương trình độc lập (`future` và `fallback` do ứng dụng cung cấp). Hai lời gọi đều thao tác trên cùng future; nếu deadline 100 ms hoàn tất lỗi trước, deadline 200 ms không còn cơ hội đổi sang fallback. Nếu các thời hạn bằng nhau, kết quả phụ thuộc cuộc đua. Muốn chuyển lỗi timeout sang dự phòng, có thể tạo **stage xử lý ngoại lệ** bằng `exceptionally` hoặc `handle`, nhưng chỉ phục hồi đúng loại lỗi mà ứng dụng muốn phục hồi:

```java
CompletableFuture<String> withFallback =
        future.orTimeout(100, TimeUnit.MILLISECONDS)
              .exceptionally(error -> {
                  Throwable cause = error;
                  while (cause instanceof java.util.concurrent.CompletionException
                          && cause.getCause() != null) {
                      cause = cause.getCause();
                  }
                  if (cause instanceof java.util.concurrent.TimeoutException) {
                      return "fallback";
                  }
                  throw new java.util.concurrent.CompletionException(cause);
              });
```

Đây là đoạn mã minh họa trong phạm vi đã có `CompletableFuture<String> future`. `exceptionally` tạo một **stage mới**, trong khi `orTimeout` đã thay đổi chính `future`. Nếu nguồn được chia sẻ, hãy tạo view độc lập trước rồi mới gắn timeout/khôi phục. Không nên bắt mọi ngoại lệ và trả fallback giống nhau, vì sẽ che cả lỗi lập trình và lỗi dữ liệu.

### 8.4. Callback sau timeout có thể chạy trước khi worker dừng

Khi `completeOnTimeout` thắng, một stage `thenApply`, `thenAccept` hay `whenComplete` có thể bắt đầu trên đường hoàn tất của future mặc dù supplier vẫn chạy. Nếu callback ghi dữ liệu, phát sự kiện hoặc giải phóng một tài nguyên mà worker còn dùng, cần điều phối rõ ràng.

Một số callback **không có hậu tố `Async`** có thể được chạy bởi luồng thực hiện hành động `complete`, bao gồm cả luồng kích hoạt timeout. Vì vậy, không đặt phép tính nặng hoặc I/O chặn lâu trong callback đồng bộ chỉ vì nghĩ nó luôn chạy trên worker gốc. Với logic nặng, cân nhắc biến thể `whenCompleteAsync`, `handleAsync`, `thenApplyAsync` cùng executor chủ đích và quản lý hàng đợi/tài nguyên của executor đó.

## 9. Giám sát trạng thái: nên ghi gì để không nhầm?

Một hệ thống có deadline nên quan sát **cả kết quả ở tầng future lẫn vòng đời thực thi**:

| Tín hiệu | Diễn giải đúng |
| --- | --- |
| `future.isDone() == true` | Future đã có trạng thái kết thúc; chưa chắc công việc thực tế đã dừng |
| `future.isCompletedExceptionally() == true` | Future hoàn tất bất thường (bao gồm timeout, hủy hoặc lỗi khác), chưa xác định nguyên nhân cụ thể |
| `future.isCancelled() == true` | Future bị hủy, không bảo đảm luồng tính toán đã dừng |
| `join()` báo `CompletionException` có cause `TimeoutException` | Deadline kiểu `orTimeout` đã khiến future kết thúc lỗi, nếu đây là đường đi timeout đã cấu hình |
| `completeOnTimeout` trả fallback | Future hoàn tất bình thường bằng giá trị dự phòng; phải dùng metadata riêng nếu cần biết đây là fallback |
| Worker đã báo hoàn tất và tài nguyên được giải phóng | Tín hiệu riêng từ công việc/quản lý thực thi; cần theo dõi ngoài `isDone()` của future khi có deadline |

Log nên có mã yêu cầu, tên thao tác, thời hạn, trạng thái timeout hay thành công, và trạng thái dừng thực tế khi có thể xác minh. Không ghi dữ liệu bí mật vào log. Nếu người gọi trả phản hồi timeout rồi yêu cầu phía sau vẫn chạy, việc đo số request “đã trả” không phản ánh số tác vụ đang tiêu thụ tài nguyên.

Đừng dùng một phép `getCause()` bất cẩn để kết luận rằng worker ném `TimeoutException`: đó có thể là lỗi do **cơ chế deadline** tạo ra, không phải ngoại lệ phát sinh trong supplier. Ngược lại, nếu supplier tự ném `TimeoutException` trong ngữ cảnh của ứng dụng, cần kiểm tra nguồn và stack trace để phân biệt.

## 10. Các lỗi thường gặp

| Hiểu nhầm | Hậu quả thực tế | Cách xử lý |
| --- | --- | --- |
| “Hết hạn là tác vụ nền chắc chắn dừng.” | Worker vẫn giữ tài nguyên hoặc phát sinh tác dụng phụ | Thiết kế cơ chế hủy riêng và theo dõi kết thúc thật |
| “`orTimeout` tạo future mới, nguồn vẫn nguyên.” | Vô tình áp deadline lên kết quả dùng chung | Ghi nhớ `orTimeout` trả `this`; tạo stage phụ thuộc nếu cần view riêng |
| “`completeOnTimeout` tạo fallback nhưng sau đó kết quả thật sẽ thay lại.” | Xử lý sai trạng thái và dữ liệu dự phòng | Kết quả hoàn tất đầu tiên thắng; kết quả đến muộn không ghi đè bình thường |
| “`completeOnTimeout` báo `isCompletedExceptionally() == true` khi fallback.” | Giám sát không thấy timeout | Fallback là hoàn tất bình thường; theo dõi nguồn kết quả riêng |
| “`get(timeout)` làm future thất bại.” | Nhầm giới hạn chờ với trạng thái kết quả | Timeout từ `get(timeout)` trực tiếp chỉ kết thúc lần chờ |
| “`cancel(true)` trên `CompletableFuture` luôn interrupt supplier.” | Hủy giả, task vẫn chạy | Cần `Future` điều khiển thực thi hoặc giao thức hủy riêng |
| “Timeout tự đóng HTTP/DB connection.” | Cạn pool, công việc tồn tại sau khi caller rời đi | Cài đặt timeout/hủy ở I/O client và dọn dẹp tài nguyên |
| “Có thể dùng nhiều timeout nối nhau để thay lỗi bằng fallback.” | Kết quả không như mong đợi vì cùng future đã chốt | Tạo stage xử lý lỗi hoặc chính sách deadline nhất quán |
| “Từ `isDone()` có thể suy ra worker đã hoàn tất.” | Giải phóng tài nguyên sớm hoặc khởi động công việc trùng | Theo dõi vòng đời worker và cơ chế xác nhận riêng |

## 11. Câu hỏi tự kiểm tra

**Tình huống 1.** `CompletableFuture<String> f` còn đang chạy. Gọi `f.orTimeout(100, MILLISECONDS)` và timeout xảy ra trước. `f.join()` trả gì?  
**Trả lời:** Thường ném `CompletionException` có cause là `TimeoutException`; `f.isCompletedExceptionally()` là `true`. Không thể từ đó kết luận supplier đã dừng.

**Tình huống 2.** Cùng trường hợp, gọi `f.completeOnTimeout("cached", 100, MILLISECONDS)`. Hạn đến trước. Sau đó supplier trả `"fresh"`. `f.join()` nhận gì?  
**Trả lời:** `"cached"`; future đã hoàn tất bình thường bằng fallback, kết quả đến muộn không thay thế được nó qua cơ chế hoàn tất thông thường.

**Tình huống 3.** `f.get(100, MILLISECONDS)` ném `TimeoutException`, nhưng `f.isDone()` vẫn `false`. Có sai hợp đồng không?  
**Trả lời:** Không. `get(timeout)` chỉ giới hạn thời gian chờ một lần; nó không tự làm future hoàn tất.

**Tình huống 4.** Gọi `CompletableFuture<String> timed = f.orTimeout(...)`. `timed == f` là gì?  
**Trả lời:** `true`. `orTimeout` trả về chính future được gọi; `completeOnTimeout` cũng vậy.

**Tình huống 5.** Future vừa trả fallback, `isCompletedExceptionally()` là `false`; điều này chứng minh API mạng đã thành công chưa?  
**Trả lời:** Chưa. Đó chỉ chứng minh future đã hoàn tất bình thường, có thể bằng giá trị dự phòng; tác vụ mạng vẫn có thể đang chạy.

**Tình huống 6.** Muốn áp deadline riêng cho người gọi A mà giữ future dùng chung cho B, nên đặt timeout ở đâu?  
**Trả lời:** Trên một dependent stage mới dành cho A (ví dụ `shared.thenApply(v -> v).orTimeout(...)`), không trực tiếp trên `shared`; nếu cần dừng xử lý bên dưới thì vẫn phải xây dựng cơ chế hủy.

**Tình huống 7.** `CompletableFuture.cancel(true)` đã thành công thì có thể chắc chắn luồng supplier nhận interrupt chưa?  
**Trả lời:** Không. Trong triển khai `CompletableFuture`, tham số `mayInterruptIfRunning` không điều khiển interrupt của computation.

## 12. Tài liệu API

- [Java 17 — `CompletableFuture.orTimeout`, `completeOnTimeout`, `cancel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): đặc tả trạng thái hoàn tất, đối tượng trả về và ý nghĩa tham số hủy.
- [Java 17 — `Future.get(timeout, unit)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): giới hạn thời gian chờ và các ngoại lệ có thể phát sinh.
- [Java 17 — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html) và [Java 17 — `TimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeoutException.html): phân biệt lớp bọc lỗi bất đồng bộ và tín hiệu quá hạn.

Điều cần nhớ khi thiết kế: **`orTimeout` hoàn tất future bằng lỗi; `completeOnTimeout` hoàn tất future bằng giá trị; `get(timeout)` chỉ giới hạn một lần chờ. Không API nào trong ba API này tự bảo đảm chấm dứt công việc bất đồng bộ đang chạy.** Muốn thực sự dừng công việc, hãy đưa yêu cầu dừng đến cơ chế thực thi hoặc I/O và xác nhận nó được xử lý.