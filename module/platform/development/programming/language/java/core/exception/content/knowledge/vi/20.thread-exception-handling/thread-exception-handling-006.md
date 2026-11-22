# `Future.get()` và `ExecutionException` trong Java

Trong lập trình đồng thời, một tác vụ chạy ở luồng khác có thể hoàn thành thành công, thất bại hoặc bị hủy. `Future<T>` đại diện cho kết quả sẽ có trong tương lai; `get()` là điểm mà luồng gọi **chờ kết quả** và **quan sát lỗi của tác vụ**. Bài này tập trung vào `Future.get()` và `ExecutionException` trong Java 17+, thuộc chủ đề **Ngoại lệ và luồng**.

## 1. Mô hình: lỗi xảy ra ở luồng nào, được nhận ở đâu?

Ví dụ, `ExecutorService.submit(Callable<T>)` gửi tác vụ cho executor. Lời gọi `submit()` thường trả về một `Future<T>` ngay, trong khi tác vụ có thể chưa bắt đầu, đang chạy hoặc đã kết thúc.

```text
Luồng gọi                              Luồng worker
-----------                            ------------
submit(callable) ────────►             chờ lịch chạy
      │                                 chạy call()
      ▼                                 │
Future<T>                               ├─ return T ─► hoàn thành thành công
      │                                 └─ throw X  ─► hoàn thành thất bại
      ▼
future.get()
      ├─ thành công ─► nhận T
      ├─ thất bại ──► ExecutionException (cause = X)
      ├─ đã hủy ────► CancellationException
      └─ bị ngắt lúc chờ ─► InterruptedException
```

Một ngoại lệ phát sinh trong `Callable.call()` **không tự động nhảy sang luồng đã gọi `submit()`**. Executor ghi lại trạng thái thất bại của tác vụ; khi gọi `get()`, bên nhận thấy `ExecutionException` chứa ngoại lệ gốc trong `getCause()`.

Điểm phân biệt quan trọng:

- **Ngoại lệ của tác vụ**: phát sinh trong worker; `get()` ném `ExecutionException`, ngoại lệ gốc nằm trong `cause`.
- **Ngắt luồng đang chờ**: xảy ra ở luồng đang gọi `get()`; `get()` ném trực tiếp `InterruptedException`. Điều này không có nghĩa tác vụ đã thất bại hoặc bị hủy.
- **Hủy Future**: `cancel(...)` thành công khiến `get()` ném trực tiếp `CancellationException` (unchecked), không bọc trong `ExecutionException`.
- **Hết hạn chờ**: chỉ có ở `get(timeout, unit)`; ném `TimeoutException` khi kết quả chưa sẵn sàng trong khoảng chờ. Tác vụ không tự động bị hủy.

## 2. Hai biến thể của `get()` và các ngoại lệ

Các chữ ký liên quan:

```java
T get() throws InterruptedException, ExecutionException;

T get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
```

`get()` không có timeout có thể chờ vô thời hạn. `get(timeout, unit)` chờ tối đa thời gian yêu cầu; `TimeoutException` là tín hiệu về **thời gian chờ của caller**, không phải trạng thái hoàn thành cuối cùng của worker.

| Tình huống quan sát | `get()` biểu hiện | Ý nghĩa và xử lý |
|---|---|---|
| `Callable` trả kết quả | Trả `T` | Tác vụ hoàn thành thành công |
| Tác vụ ném `IOException`, `RuntimeException` hoặc `Error` | Ném `ExecutionException` | Xem `getCause()` để biết lỗi thực sự |
| Future đã bị hủy thành công | Ném `CancellationException` | Xử lý nhánh hủy riêng |
| Luồng gọi bị interrupt khi chờ | Ném `InterruptedException` | Dừng/thoát theo chính sách ngắt của caller |
| `get(timeout, unit)` chưa có kết quả đúng hạn | Ném `TimeoutException` | Có thể thử chờ tiếp hoặc chủ động hủy |
| `get()` được gọi lại khi Future đã thành công | Trả lại kết quả | Không chạy lại tác vụ |
| `get()` được gọi lại khi Future đã thất bại | Lại ném `ExecutionException` | Không tự retry tác vụ |

`ExecutionException` là **checked exception**; `InterruptedException` và `TimeoutException` cũng là checked exception. `CancellationException` kế thừa `IllegalStateException` và là **unchecked exception**.

`Future` còn có `isDone()` và `isCancelled()`. `isDone() == true` chỉ nói rằng Future đã kết thúc theo một trong các trạng thái **thành công, lỗi hoặc hủy**; không khẳng định `get()` sẽ trả kết quả thành công. `isCancelled()` cho biết Future đã bị hủy.

## 3. Ví dụ chạy độc lập: kết quả thành công và lỗi từ worker

Tạo tệp `FutureGetDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureGetDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> good = executor.submit(() -> 6 * 7);

            Future<Integer> bad = executor.submit((Callable<Integer>) () -> {
                throw new IllegalArgumentException("mã âm");
            });

            printResult("good", good);
            printResult("bad", bad);
        } finally {
            executor.shutdown();
        }
    }

    private static void printResult(String name, Future<Integer> future)
            throws InterruptedException {
        try {
            System.out.println(name + " = " + future.get());
        } catch (ExecutionException e) {
            Throwable cause = e.getCause();
            System.out.println(name + " lỗi: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FutureGetDemo.java
java FutureGetDemo
```

Kết quả chuẩn:

```text
good = 42
bad lỗi: IllegalArgumentException: mã âm
```

Thứ tự hoàn thành **thực tế** của hai worker có thể khác nhau, nhưng thứ tự in vẫn như trên vì chương trình gọi `printResult("good", ...)` trước. Đối với `bad`, `submit()` không ném ngay `IllegalArgumentException`; câu lệnh `future.get()` làm xuất hiện `ExecutionException` ở luồng `main`. Gọi `getCause()` trả về `IllegalArgumentException` đã phát sinh trong worker. `shutdown()` nằm trong `finally` để yêu cầu executor ngừng nhận tác vụ mới kể cả khi nhánh xử lý kết quả gặp lỗi.

Lưu ý: trên Java 17, `ExecutorService` chưa dùng được trực tiếp với `try (ExecutorService executor = ...)` theo kiểu `AutoCloseable`; mẫu `try/finally` ở trên phù hợp với Java 17.

## 4. Xử lý `ExecutionException`: nhìn vào nguyên nhân gốc

`ExecutionException` mô tả **tác vụ thất bại khi thực thi**; loại lỗi nghiệp vụ hoặc kỹ thuật thật nằm trong `getCause()`. Một `Callable` được phép ném checked exception, ví dụ `IOException`. Caller không bắt `IOException` trực tiếp từ `Future.get()` mà sẽ thấy `ExecutionException` có cause là `IOException`.

Trong một phương thức đang xử lý kết quả Future, có thể phân loại nguyên nhân như sau (đoạn mã đặt **bên trong** nhánh `catch (ExecutionException e)`; không phải chương trình chạy độc lập):

```java
Throwable cause = e.getCause();

if (cause instanceof IllegalArgumentException invalidInput) {
    // Phân loại lỗi dữ liệu/đầu vào.
    System.err.println("Đầu vào không hợp lệ: " + invalidInput.getMessage());
} else if (cause instanceof java.io.IOException ioError) {
    // Lỗi I/O gốc do Callable ném ra.
    System.err.println("Lỗi truy cập I/O: " + ioError.getMessage());
} else {
    // Giữ chuỗi nguyên nhân khi chuyển lên lớp ứng dụng.
    throw new IllegalStateException("Tác vụ bất đồng bộ thất bại", cause);
}
```

Các nguyên tắc:

1. **Giữ cause** khi ghi log hoặc bọc lại: `new IllegalStateException("...", cause)`. Chỉ in `e.getMessage()` có thể làm mất ngữ cảnh ngoại lệ gốc.
2. **Không mặc định** mọi cause là `RuntimeException`; worker có thể ném checked exception hoặc `Error`. Với lỗi hệ thống nghiêm trọng, cân nhắc chính sách xử lý/escalation riêng, đừng âm thầm nuốt lỗi.
3. Chỉ **retry** khi có chiến lược rõ ràng: lấy lại cùng một `Future` không chạy lại tác vụ. Muốn chạy lại phải tạo lần submit mới và xét đến tính idempotent, giới hạn số lần thử, backoff.
4. Không biến mọi lỗi thành giá trị dự phòng nếu việc đó che mất lỗi quan trọng. Ở ranh giới dịch vụ, có thể chuyển cause thành lỗi miền nghiệp vụ nhưng cần giữ nguyên chuỗi nguyên nhân.

`submit(Runnable)` cũng trả về `Future<?>` và lưu thất bại của Runnable để `get()` báo bằng `ExecutionException`; khi Runnable hoàn thành bình thường, `get()` thường trả `null` (hoặc giá trị result được cung cấp qua overload `submit(Runnable, result)`).

**So với `execute(Runnable)`**: `execute` không trả Future để caller gọi `get()`. Cách lỗi được báo/phơi bày từ worker phụ thuộc executor và uncaught-exception handling. Vì vậy không dùng `submit()` rồi bỏ qua Future nếu cần biết tác vụ có thành công hay không.

## 5. Ví dụ chạy độc lập: timeout không đồng nghĩa hủy tác vụ

Tệp `FutureTimeoutDemo.java` sử dụng `CountDownLatch` để bảo đảm tác vụ chưa thể hoàn thành trước khi caller thử chờ. Nhờ vậy, ví dụ không phụ thuộc vào tốc độ máy hay `Thread.sleep(...)`.

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
        CountDownLatch gate = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                gate.await();
                return "hoàn thành";
            });

            try {
                System.out.println(future.get(100, TimeUnit.MILLISECONDS));
            } catch (TimeoutException e) {
                System.out.println("Hết hạn chờ");
            }

            System.out.println("Đã xong? " + future.isDone());
            gate.countDown();
            System.out.println("Kết quả sau đó: " + future.get());
        } finally {
            gate.countDown();
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Kết quả:

```text
Hết hạn chờ
Đã xong? false
Kết quả sau đó: hoàn thành
```

`TimeoutException` chỉ chấm dứt lần **đợi** đầu tiên. Future vẫn có thể đang chạy; sau khi mở `gate`, lần `get()` tiếp theo lấy được kết quả. Khi timeout trong ứng dụng thực tế, chọn một trong các cách xử lý có chủ đích: tiếp tục xử lý công việc khác và kiểm tra lại; báo timeout cho caller trong khi worker được phép chạy tiếp; hoặc gọi `cancel(true)` nếu thực sự muốn yêu cầu hủy và tác vụ có hỗ trợ interrupt. Không coi timeout là chứng cứ rằng worker đã dừng.

Không nên dùng `get()` vô hạn trên đường xử lý có yêu cầu latency (chẳng hạn luồng nhận HTTP) nếu không có kế hoạch timeout, giới hạn tài nguyên và xử lý thất bại.

## 6. `InterruptedException`: caller bị ngắt, không phải `ExecutionException`

`get()` là thao tác chờ **có thể bị ngắt**. Nếu luồng **đang gọi `get()`** bị interrupt trong lúc đợi, `get()` ném `InterruptedException`. Đây là sự kiện điều khiển luồng chờ; nó không chứng minh rằng `Callable` của Future đã ném ngoại lệ. Ngược lại, một `InterruptedException` ném **trong worker** mà thoát khỏi `Callable.call()` là một thất bại của tác vụ và sẽ được quan sát dưới dạng cause của `ExecutionException` khi caller gọi `get()`.

Khi phương thức cho phép, cách đơn giản nhất là **truyền tiếp** checked exception:

```java
static <T> T await(Future<T> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
```

Nếu bắt `InterruptedException` để chuyển thành unchecked exception, thường phải **khôi phục cờ interrupt** của luồng hiện tại để tầng gọi cao hơn không mất tín hiệu:

```java
try {
    return future.get();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Luồng chờ đã bị ngắt", e);
} catch (ExecutionException e) {
    throw new IllegalStateException("Tác vụ thất bại", e.getCause());
}
```

Đoạn trên là phần thân minh họa của phương thức trả về cùng kiểu với kết quả `future.get()`. Khi việc hủy Future phù hợp nghiệp vụ, caller có thể **chủ động** gọi `future.cancel(true)` trong nhánh bị ngắt; `get()` bị interrupt không tự thực hiện hành động này.

Đừng bỏ qua `InterruptedException` bằng `catch (InterruptedException ignored) {}` rồi tiếp tục đợi vô thời hạn. Và đừng nhầm hai chiều interrupt: gọi `future.cancel(true)` thường yêu cầu ngắt **luồng worker** đang chạy tác vụ, còn `Thread.currentThread().interrupt()` tác động lên **luồng caller** hiện tại.

## 7. `cancel(...)`, `CancellationException` và trạng thái hoàn thành

```java
boolean accepted = future.cancel(true);

try {
    Object value = future.get();
} catch (java.util.concurrent.CancellationException cancelled) {
    // Future đã bị hủy; không xử lý như ExecutionException.
}
```

Đây là đoạn sử dụng minh họa, không phải chương trình độc lập. `cancel(true)` thử hủy và, nếu tác vụ đang chạy, cho phép yêu cầu interrupt worker; nó **không bảo đảm** mã worker đang thực thi sẽ dừng ngay, nhất là khi tác vụ phớt lờ interrupt. `cancel(false)` không yêu cầu interrupt worker đang chạy. Giá trị boolean trả về cho biết yêu cầu hủy có thành công theo trạng thái Future hay không; không phải xác nhận worker đã dọn dẹp xong mọi tài nguyên.

Sau khi hủy thành công, `isCancelled()` và `isDone()` đều trả `true`, và `get()` ném `CancellationException`. Tương tự, nếu một tác vụ đã thất bại, `isDone()` vẫn là `true`. Vì vậy phải **đọc kết quả hoặc ngoại lệ từ `get()`** nếu cần phân biệt thành công và lỗi.

Nếu timeout dẫn tới yêu cầu hủy, dùng mẫu có quyết định rõ:

```java
try {
    return future.get(2, java.util.concurrent.TimeUnit.SECONDS);
} catch (java.util.concurrent.TimeoutException timeout) {
    future.cancel(true); // Yêu cầu dừng theo chính sách của ứng dụng.
    throw timeout;
}
```

Đây cũng là đoạn thân phương thức minh họa; phương thức bao ngoài phải khai báo/xử lý `InterruptedException`, `ExecutionException` và `TimeoutException`, cũng như có kiểu trả về phù hợp.

## 8. Những bẫy đồng thời khi dùng `get()`

### 8.1. Deadlock/starvation khi chờ tác vụ cùng executor nhỏ

Một tác vụ chạy trong executor **chỉ có một worker** rồi gửi tác vụ con vào cùng executor và gọi `get()` chờ nó sẽ chiếm worker duy nhất; tác vụ con không có luồng để chạy.

```java
// Minh họa bẫy; KHÔNG chạy đoạn này như một chương trình thực tế.
ExecutorService one = Executors.newSingleThreadExecutor();
Future<String> outer = one.submit(() -> {
    Future<String> inner = one.submit(() -> "inner");
    return inner.get(); // Chờ tác vụ con chưa có worker để chạy.
});
System.out.println(outer.get()); // Có thể chờ vô hạn.
```

Hãy tránh chờ phụ thuộc chéo bên trong pool có tài nguyên hạn chế; thay bằng cấu trúc tác vụ không blocking, tách executor phù hợp hoặc thiết kế luồng xử lý không cần chờ một công việc đang nằm trong cùng hàng đợi.

### 8.2. `isDone()` rồi `get()` không thay thế xử lý ngoại lệ

Ngay cả khi:

```java
if (future.isDone()) {
    // get() sẽ không cần đợi trạng thái hoàn thành,
    // nhưng vẫn có thể ném ExecutionException hoặc CancellationException.
    future.get();
}
```

`isDone()` không cho biết kết quả tốt hay xấu. Nếu có cạnh tranh với thao tác `cancel()`, trạng thái cũng có thể thay đổi giữa lúc kiểm tra và lúc gọi `get()`. Thông thường dùng trực tiếp `get()` trong `try/catch` hoặc phương án timeout sẽ rõ hơn.

### 8.3. Quên lấy kết quả của Future

Với tác vụ đưa vào `submit`, các lỗi được lưu trong Future; nếu không gọi `get()` hoặc không có cơ chế quan sát khác, hệ thống có thể bỏ sót lỗi. Nên gom Future và đọc trạng thái hoàn thành, hoặc dùng một cơ chế xử lý bất đồng bộ có báo lỗi rõ ràng.

### 8.4. Đánh đồng `shutdown()` và `cancel()`

`executor.shutdown()` chỉ từ chối tác vụ mới và cho các tác vụ đã nhận cơ hội hoàn tất. Nó **không** tự hủy tất cả Future và không đợi đến khi toàn bộ worker kết thúc. Khi cần chờ executor đóng, sử dụng `awaitTermination(...)` với timeout và chiến lược interrupt; khi cần yêu cầu dừng mạnh hơn, cân nhắc `shutdownNow()` cùng mã tác vụ có hợp tác xử lý interrupt.

### 8.5. Hiểu sai visibility giữa các luồng

Theo hợp đồng bộ nhớ của `Future`, các hành động của tác vụ bất đồng bộ **happens-before** các hành động theo sau `Future.get()` tương ứng trong luồng khác. Nhờ đó, `get()` là điểm đồng bộ quan trọng khi tiêu thụ kết quả và dữ liệu được công bố bởi tác vụ. Quy tắc này không có nghĩa mọi biến chia sẻ trong toàn bộ ứng dụng tự động thread-safe; các truy cập đồng thời độc lập vẫn cần bảo vệ phù hợp.

## 9. So sánh nhanh với `CompletableFuture`

`CompletableFuture<T>` cũng triển khai `Future<T>`:

| Cách chờ | Khi giai đoạn bất đồng bộ thất bại | Khi thread caller bị interrupt |
|---|---|---|
| `future.get()` | `ExecutionException` chứa cause gốc | Có thể ném `InterruptedException` |
| `future.get(timeout, unit)` | `ExecutionException` chứa cause gốc | Có thể ném `InterruptedException`; thêm `TimeoutException` |
| `completableFuture.join()` | Thường là `CompletionException` (unchecked) chứa cause gốc | Không khai báo `InterruptedException` |

Nếu CompletableFuture bị hủy, cả `get()` và `join()` có thể ném `CancellationException` trực tiếp. `join()` không phải phép thay thế hoàn toàn cho `get()` vì cách báo lỗi và xử lý interrupt khác nhau. Nếu đang phối hợp nhiều tác vụ theo luồng bất đồng bộ, những phép ghép như `thenApply`, `thenCompose`, `handle` và `exceptionally` của CompletableFuture có thể giảm nhu cầu chặn worker bằng `get()`; đây là lựa chọn thiết kế bổ sung, không làm thay đổi hợp đồng lỗi của `Future.get()`.

## 10. Mẫu quyết định xử lý lỗi và checklist

Một luồng xử lý thông dụng có bốn nhánh tách biệt:

```text
Gọi Future.get(timeout, unit)
    ├─ trả kết quả            → dùng kết quả đã hoàn thành
    ├─ ExecutionException    → lấy cause và phân loại lỗi tác vụ
    ├─ InterruptedException  → tôn trọng interrupt của caller; propagate hoặc restore
    ├─ TimeoutException      → quyết định chờ tiếp, báo chậm hay cancel
    └─ CancellationException → xử lý hủy như một trạng thái riêng
```

Trước khi đưa code dùng `Future` vào production, kiểm tra:

- Tác vụ đã được gửi bằng `submit(...)` và Future được giữ lại để quan sát thành công/thất bại.
- Bên đọc xử lý `ExecutionException.getCause()` đúng loại lỗi cần quan tâm, giữ chuỗi nguyên nhân khi chuyển lỗi.
- Caller có chính sách timeout nếu không thể chờ vô hạn; timeout được phân biệt với hủy.
- `InterruptedException` không bị nuốt; propagate hoặc khôi phục interrupt khi cần.
- Không có chờ lồng nhau trong executor dễ làm cạn worker; tác vụ có hỗ trợ hủy/interrupt nếu cần.
- Executor được shutdown; có phương án chờ termination hoặc dọn tài nguyên theo vòng đời dịch vụ.

**Ghi nhớ:** `get()` là điểm nhận kết quả và ngoại lệ của tác vụ bất đồng bộ. `ExecutionException` cho biết **worker đã thất bại** và `getCause()` giải thích lỗi gốc; `InterruptedException`, `TimeoutException` và `CancellationException` mô tả ba tình huống riêng ở phía chờ hoặc trạng thái hủy, cần xử lý riêng theo chính sách ứng dụng.
