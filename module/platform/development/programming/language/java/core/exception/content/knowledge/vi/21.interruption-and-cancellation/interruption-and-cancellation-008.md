# Phân biệt ngắt luồng, hủy `Future` và kết thúc cưỡng bức trong Java

Khi một công việc chạy quá lâu hoặc ứng dụng cần dừng, ba thao tác thường bị đánh đồng là **ngắt luồng** (`Thread.interrupt()`), **hủy tác vụ** (`Future.cancel(...)`) và **kết thúc cưỡng bức** (chẳng hạn `Thread.stop()` hoặc chấm dứt tiến trình). Chúng có **đối tượng tác động, hợp đồng kết quả và rủi ro hoàn toàn khác nhau**. Không có lời gọi nào trong hai cách đầu bảo đảm rằng một đoạn mã tùy ý sẽ ngừng thực thi ngay lập tức.

Bài thuộc phần **Ngắt và hủy** của Java Core Exception, dùng API Java 17+. Sau khi học, bạn cần giải thích được: ai nhận interrupt, tại sao `Future` có thể báo đã hủy trong khi worker còn chạy, cách phân biệt các ngoại lệ khi lấy kết quả, và khi nào phải dùng ranh giới tiến trình thay vì cố ép dừng một luồng.

## 1. Ba cấp độ điều khiển khác nhau

| Cơ chế | Đối tượng chính | Tác động trực tiếp | Có bảo đảm worker dừng ngay? |
|---|---|---|---|
| `thread.interrupt()` | Một `Thread` cụ thể | Đặt trạng thái interrupt hoặc đánh thức thao tác chờ có hỗ trợ interrupt | **Không** |
| `future.cancel(false)` | Trạng thái một `Future` | Yêu cầu hủy Future, không yêu cầu ngắt worker đang chạy | **Không** |
| `future.cancel(true)` | Trạng thái `Future` và khả năng yêu cầu ngắt worker | Nếu hủy được, Future chuyển sang canceled; implementation có thể interrupt worker đang chạy | **Không** |
| `executor.shutdown()` | Vòng đời executor | Ngừng nhận tác vụ mới, tiếp tục xử lý tác vụ đã nhận | **Không** |
| `executor.shutdownNow()` | Executor và những task đang thực thi/đợi | Cố gắng interrupt task đang chạy, ngừng nhận/chạy task đang chờ và trả về danh sách task chưa bắt đầu | **Không** |
| `Thread.stop()` | Một luồng | Cơ chế dừng bất đồng bộ nguy hiểm, đã bị deprecated | **Không nên dùng** |
| Kết thúc cả tiến trình JVM/OS | Tiến trình | Chấm dứt môi trường chạy của nhiều luồng cùng lúc | Mất cả tiến trình; không phải cách hủy một task Java an toàn |

**Phân biệt đối tượng:** `Thread` là luồng thực thi, `Future` là tay nắm theo dõi kết quả/trạng thái một tác vụ, `ExecutorService` là bộ quản lý thực thi nhiều tác vụ. Thực hiện thao tác trên một đối tượng không đồng nghĩa những đối tượng còn lại tự chuyển cùng một trạng thái.

Một sơ đồ ngắn:

```text
Caller giữ Future<T>                           Worker Thread
         │                                           │
         ├─ thread.interrupt() ──► cờ interrupt ────► │
         │                                      worker tự xử lý
         │
         ├─ future.cancel(false) ─► Future=canceled   │ có thể tiếp tục
         │
         └─ future.cancel(true) ──► Future=canceled   │
                                   + thử interrupt ─►│ có thể dừng hợp tác

Đã canceled ──► future.get() ném CancellationException
Worker lỗi mà Future chưa bị canceled ──► get() ném ExecutionException
```

Sơ đồ mô tả cách `FutureTask` được dùng phổ biến bởi `ExecutorService.submit(...)`. **Không phải mọi triển khai `Future` dùng interrupt để điều khiển tính toán.** Ví dụ, `CompletableFuture.cancel(boolean)` bỏ qua tham số `mayInterruptIfRunning` theo hợp đồng của chính nó; hủy `CompletableFuture` không mặc nhiên ngắt thread chạy công việc.

## 2. Ngắt luồng: `Thread.interrupt()` là yêu cầu hợp tác

Mỗi `Thread` có một trạng thái interrupt. Khi luồng A gọi `worker.interrupt()`, Java báo hiệu cho `worker` rằng có yêu cầu ngắt:

- Nếu worker đang tính toán và không gọi thao tác chờ có thể ngắt, cờ interrupt được đặt; worker thường tiếp tục chạy cho tới khi tự kiểm tra và phản ứng.
- Nếu worker đang chờ trong `Thread.sleep`, `Object.wait`, `Thread.join`, `BlockingQueue.take`, `CountDownLatch.await` hoặc nhiều thao tác chờ interruptible khác, lời gọi chờ có thể kết thúc sớm bằng `InterruptedException`.
- Những thao tác chờ nêu trên thường **xóa cờ interrupt khi ném `InterruptedException`**. Mã bắt ngoại lệ cần quyết định truyền tiếp tín hiệu hoặc khôi phục cờ và kết thúc công việc.
- `Thread.currentThread().isInterrupted()` đọc cờ của luồng hiện tại mà không xóa; phương thức tĩnh `Thread.interrupted()` đọc **và xóa cờ của luồng hiện tại**.

`interrupt()` **không tự tạo `CancellationException`**, không biến task đã submit thành canceled, và không có nghĩa caller cũng bị interrupt. Nếu worker chủ động bắt `InterruptedException`, dọn tài nguyên và trả kết quả bình thường, `Future` có thể hoàn thành **thành công**.

### Ví dụ Java 17 độc lập: interrupt một Thread, không có Future

Tạo tệp `ThreadInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class ThreadInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean observed = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            ready.countDown();
            try {
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                observed.set(true);
                Thread.currentThread().interrupt();
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("received interrupt = " + observed.get());
        System.out.println("worker alive = " + worker.isAlive());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ThreadInterruptDemo.java
java ThreadInterruptDemo
```

Đầu ra:

```text
received interrupt = true
worker alive = false
```

`ready` bảo đảm worker đã đi đến đoạn xử lý trước khi main phát tín hiệu; dù worker chưa kịp gọi `await()`, trạng thái interrupt vẫn khiến lần chờ ấy ném `InterruptedException`. Worker tự thoát khỏi `run()` nên kết thúc, chứ không phải `interrupt()` cưỡng ép dừng. `join()` đợi worker kết thúc trước khi in kết quả; `AtomicBoolean` ghi lại việc worker nhận tín hiệu.

Trong `catch`, ta khôi phục cờ với `Thread.currentThread().interrupt()` vì `await()` đã xóa cờ khi ném ngoại lệ. Nếu phương thức cho phép `throws InterruptedException`, truyền tiếp ngoại lệ thường minh bạch hơn; khi bắt ở ranh giới vòng đời, có thể khôi phục cờ rồi thoát.

### Công việc CPU phải hợp tác kiểm tra cờ

Đây là **phương thức minh họa** có thể đặt bên trong một class, không phải tệp chạy độc lập:

```java
static long calculateUntilStopped() {
    long count = 0;
    while (!Thread.currentThread().isInterrupted()) {
        count++;
    }
    return count;
}
```

Nếu thay điều kiện bằng `while (true)` và không có thao tác chờ interruptible, gọi `interrupt()` sẽ không tự ném `InterruptedException` ở vòng lặp CPU đó. Cũng đừng dùng `Thread.interrupted()` như phép kiểm tra vô hại: nó xóa cờ, có thể làm mất tín hiệu cho tầng khác.

## 3. `Future.cancel(false)`: hủy kết quả quan sát được, không ngắt worker

`Future.cancel(boolean mayInterruptIfRunning)` thử hủy Future:

```java
boolean accepted = future.cancel(false);
```

Đây là **mảnh mã minh họa** có biến `future` kiểu `Future<?>`. Khi `cancel(false)` thành công với `FutureTask` đang chạy, Future chuyển sang trạng thái **canceled**, nhưng việc thực thi worker **không bị yêu cầu interrupt**; worker có thể tiếp tục và thậm chí hoàn thành tính toán. Kết quả cuối cùng không còn nhận được qua `get()` của Future đã hủy.

Sau khi Future đã hủy thành công:

- `future.isCancelled()` trả `true`.
- `future.isDone()` trả `true` vì Future có trạng thái kết thúc theo hợp đồng của nó.
- `future.get()` ném `CancellationException` trực tiếp.
- `isDone() == true` **không chứng minh** worker đã thoát và dọn dẹp xong.

Nếu task đã hoàn thành hoặc đã bị hủy trước đó, lời gọi `cancel(...)` tiếp theo thường trả `false` theo hợp đồng `Future`. Kết quả trả về phụ thuộc trạng thái tại thời điểm race, vì vậy **phải dùng giá trị thực trả về** thay vì mặc định cancel luôn thành công.

Về vận hành, `cancel(false)` phù hợp khi không còn quan tâm kết quả, muốn tránh tác vụ chưa bắt đầu chạy tiếp theo khả năng của implementation, hoặc không muốn yêu cầu interrupt một worker đang làm công việc khó hủy an toàn. Nó **không phải** một cơ chế dừng worker đang chạy.

## 4. `Future.cancel(true)`: hủy Future và cho phép yêu cầu interrupt

```java
boolean accepted = future.cancel(true);
```

Với `FutureTask` thông thường được trả bởi `ExecutorService.submit(...)`, nếu việc hủy thành công và tác vụ đang chạy, implementation sẽ cố gắng gửi interrupt tới thread chạy nó. Tuy nhiên:

1. Future có thể chuyển sang canceled **trước khi** worker phản ứng hoặc thoát; caller thấy `CancellationException` từ `get()` ngay cả khi worker vẫn đang dọn dẹp.
2. Worker có thể đang thực hiện mã không hỗ trợ interrupt hoặc cố tình nuốt interrupt; nó vẫn có thể chạy.
3. Nếu worker đã hoàn tất trước yêu cầu hủy, `cancel(true)` có thể trả `false` và Future giữ kết quả đã hoàn tất.
4. Một API khác triển khai `Future` có thể có quy tắc hủy riêng. Đặc biệt `CompletableFuture.cancel(true)` không dùng tham số `true` để interrupt tác vụ nền.

**`cancel(true)` có nghĩa là “cho phép yêu cầu interrupt nếu phù hợp”, không phải “kill thread ngay”.** Worker cần code xử lý cooperative cancellation để dừng an toàn.

### Ví dụ Java 17 độc lập: `cancel(false)` và `cancel(true)`

Tạo tệp `FutureCancelModesDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelModesDemo {
    public static void main(String[] args) throws Exception {
        withoutInterrupt();
        withInterrupt();
    }

    private static void withoutInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);

        try {
            Future<Integer> future = executor.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    return 42;
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(false);

            System.out.println("cancel(false) = " + accepted);
            System.out.println("cancelled = " + future.isCancelled());
            System.out.println("worker still waiting = "
                    + (finished.getCount() == 1));

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get = CancellationException");
            }

            release.countDown();
            finished.await();
            System.out.println("worker finished after release = true");
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }

    private static void withInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                    return "normal";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "worker handled interrupt";
                } finally {
                    finished.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);
            finished.await();

            System.out.println("cancel(true) = " + accepted);
            System.out.println("worker saw interrupt = "
                    + sawInterrupt.get());
            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get = CancellationException");
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac FutureCancelModesDemo.java
java FutureCancelModesDemo
```

Đầu ra:

```text
cancel(false) = true
cancelled = true
worker still waiting = true
get = CancellationException
worker finished after release = true
cancel(true) = true
worker saw interrupt = true
get = CancellationException
```

Trong nhánh thứ nhất, `started.await()` bảo đảm task đã chạy; `release` còn đóng, nên worker chưa hoàn tất khi `cancel(false)` được gọi. Future báo canceled và `get()` ném `CancellationException`, nhưng worker tiếp tục chờ đến khi main mở `release`.

Trong nhánh thứ hai, worker chờ một latch không bao giờ được mở. `cancel(true)` yêu cầu interrupt, `await()` ném `InterruptedException`, worker ghi nhận tín hiệu, khôi phục cờ rồi thoát. Dù worker tự trả chuỗi `"worker handled interrupt"`, bên nhận **không lấy được chuỗi đó** vì Future đã bị hủy. `finished.await()` chỉ dùng để đợi phần `finally` của worker chạy xong trước khi đọc `sawInterrupt`; đối với thao tác thật, muốn xác nhận toàn bộ worker đã kết thúc có thể cần cơ chế lifecycle như `awaitTermination(...)`.

**Đừng suy từ kết quả của ví dụ thành cam kết cho mọi tác vụ:** ví dụ chủ động dùng `CountDownLatch`, mã worker hợp tác với interrupt và executor chỉ có một worker. Một tác vụ chặn I/O không interruptible hoặc bị kẹt trong thư viện bên ngoài có thể không dừng khi gọi `cancel(true)`.

## 5. Ngắt worker trực tiếp không nhất thiết hủy `Future`

Nếu worker nhận interrupt qua `worker.interrupt()` hoặc do executor gửi interrupt mà **không có lời gọi `Future.cancel(...)`**, Future có thể kết thúc theo hai đường:

- Worker **để `InterruptedException` thoát khỏi `Callable`**: Future hoàn thành **thất bại**; `future.get()` ném `ExecutionException`, `getCause()` là `InterruptedException`.
- Worker **bắt `InterruptedException`, dọn dẹp và return giá trị**: Future có thể hoàn thành **thành công** và `get()` trả giá trị đó.

Hai tình huống khác với một Future đã hủy, khi `get()` ném `CancellationException` dù worker còn xử lý dở.

### Ví dụ độc lập: interrupt worker tạo `ExecutionException`, không phải cancellation

Tạo tệp `WorkerInterruptedFailureDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class WorkerInterruptedFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                new CountDownLatch(1).await();
                return "not reached";
            });

            started.await();
            executor.shutdownNow();

            try {
                future.get();
            } catch (ExecutionException e) {
                System.out.println("cause = "
                        + e.getCause().getClass().getSimpleName());
            }

            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac WorkerInterruptedFailureDemo.java
java WorkerInterruptedFailureDemo
```

Đầu ra:

```text
cause = InterruptedException
cancelled = false
```

`shutdownNow()` yêu cầu interrupt worker đang thực thi. Khi bị ngắt, lời gọi `await()` ném `InterruptedException` và `Callable` không bắt ngoại lệ đó, vì thế `FutureTask` ghi nhận **thất bại của task**. Caller đọc bằng `get()` thấy `ExecutionException`, không phải `CancellationException`, vì không có lời gọi `future.cancel(...)`.

Điểm quan trọng: `executor.shutdownNow()` **không đồng nghĩa** với `future.cancel(true)`. Nó cố ngắt các task đang chạy, nhưng có thể trả về các task chưa từng bắt đầu; Future tương ứng với task nằm trong danh sách chờ có thể vẫn chưa được tự động chuyển sang canceled. Ứng dụng phải quản lý lifecycle và Future của các tác vụ đó theo đúng hợp đồng executor cụ thể.

## 6. Người gọi `Future.get()` bị ngắt là một chuyện khác

Hai luồng có thể tham gia cùng một Future:

```text
Caller/main                               Executor worker
    │                                          │
    ├─ future.get() ───── chờ ───────────────► chạy Callable
    │
    └─ caller bị interrupt
             │
             ▼
      get() ném InterruptedException
             │
      Future/worker có thể vẫn chạy
```

Nếu **caller** bị interrupt trong khi đợi `get()`, `get()` có thể ném trực tiếp **`InterruptedException`**; không có suy luận tự động rằng worker cũng bị ngắt hay Future đã bị cancel. Ngược lại, khi **worker** ném `InterruptedException` thoát khỏi `Callable` mà Future chưa canceled, bên gọi `get()` thấy **`ExecutionException`** chứa `InterruptedException` ở `getCause()`.

| Điều xảy ra | Bên gọi `Future.get()` thường thấy |
|---|---|
| Callable trả về bình thường | Giá trị `T` |
| Callable ném ngoại lệ, Future chưa canceled | `ExecutionException` có cause là lỗi worker |
| Chính caller đang chờ bị interrupt | `InterruptedException` trực tiếp |
| Future bị cancel thành công | `CancellationException` trực tiếp |
| `get(timeout, unit)` hết hạn trong khi vẫn chưa có kết quả | `TimeoutException` |

`InterruptedException`, `ExecutionException` và `TimeoutException` là checked exception; `CancellationException` là unchecked exception. Timeout của `get(timeout, unit)` **không tự hủy** Future; nếu cần dừng, caller phải chủ động quyết định có gọi `cancel(...)` hay không.

Mẫu xử lý (mảnh mã trong một phương thức có `future` hợp lệ, có kiểu trả về phù hợp):

```java
try {
    return future.get(2, java.util.concurrent.TimeUnit.SECONDS);
} catch (java.util.concurrent.TimeoutException e) {
    future.cancel(true);           // Chính sách chủ động yêu cầu hủy.
    throw e;
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    future.cancel(true);           // Chỉ khi yêu cầu ngắt caller cũng phải hủy task.
    throw e;
}
```

Nếu phương thức chỉ có nhiệm vụ **đợi** và tác vụ phải được phép tiếp tục dù caller ngừng đợi, hãy bỏ `future.cancel(true)` khỏi nhánh `InterruptedException`. Không có chính sách duy nhất phù hợp mọi trường hợp.

## 7. Vì sao `Thread.stop()` không phải giải pháp?

Trước đây Java có `Thread.stop()` để dừng một thread bất đồng bộ. API này đã bị **deprecated** vì nguy hiểm. Nó có thể làm thread dừng ở vị trí không thể dự đoán, giải phóng các monitor khi trạng thái đối tượng đang dang dở, phá vỡ invariant dữ liệu dùng chung và khiến những thread khác nhìn thấy trạng thái không nhất quán.

Ví dụ tình huống cần tránh:

```java
synchronized (account) {
    account.debit(100);
    // Nếu bị ép dừng tại đây, chưa chắc thao tác cân đối liên quan đã xong.
    ledger.recordDebit(100);
}
```

Đây là **mảnh mã minh họa**, các đối tượng `account` và `ledger` là giả định. Một cơ chế cưỡng bức dừng giữa hai bước có thể để hệ thống ở trạng thái dở dang; `synchronized` chỉ bảo đảm khóa được quản lý theo quy tắc JVM, không bảo đảm chuỗi cập nhật nghiệp vụ trở thành transaction nguyên tử.

Các cách liên quan cũng cần hiểu đúng:

- `Thread.suspend()`/`resume()` là API lỗi thời nguy hiểm, có thể tạo deadlock; không dùng để quản lý vòng đời.
- `Thread.stop()` không nên dùng để xử lý task treo; Java không cung cấp API an toàn tổng quát để giết **một luồng bất kỳ** và vẫn bảo toàn mọi invariant/tài nguyên.
- `System.exit(...)` chấm dứt **cả JVM**, không phải riêng Future hoặc worker. Dữ liệu chưa ghi, request đang xử lý và nhiều tài nguyên khác cùng chịu ảnh hưởng.
- Kết thúc tiến trình bằng công cụ hệ điều hành hoặc `Process.destroyForcibly()` tác động ở **ranh giới process**, không có cùng ý nghĩa với `Thread.interrupt()`. Nếu tác vụ không tin cậy cần có khả năng dừng cưỡng bức, hãy cân nhắc chạy **trong tiến trình riêng**, giao tiếp qua IPC và quy định rõ timeout, dữ liệu có thể mất, dọn tài nguyên, retry và giám sát.

**Lựa chọn kiến trúc:** với công việc Java trong cùng JVM, ưu tiên điểm dừng hợp tác. Với tác vụ không thể tin cậy sẽ phản ứng với interrupt (ví dụ đoạn mã third-party có nguy cơ treo), cô lập sang process/container riêng có thể tạo ranh giới cắt bỏ mạnh hơn, nhưng việc kết thúc cưỡng bức vẫn có hậu quả nghiệp vụ và tài nguyên.

## 8. `ExecutorService`: dừng nhận việc, yêu cầu dừng và chờ xác nhận

Ba thao tác phổ biến có ý nghĩa khác nhau:

1. `shutdown()` báo executor ngừng nhận task mới, còn task đã nhận được phép tiếp tục; **không tự đợi** chúng hoàn tất.
2. `shutdownNow()` cố gắng interrupt các tác vụ đang chạy, ngừng xử lý task chờ, trả về danh sách các task chưa bắt đầu; đây là yêu cầu **best effort**.
3. `awaitTermination(timeout, unit)` đợi trạng thái executor đã kết thúc trong khoảng thời gian giới hạn và trả `boolean`; luồng **đang đợi** có thể nhận `InterruptedException`.

Một mẫu shutdown có thời hạn (đoạn mã đặt trong phương thức, biến `executor` đã tồn tại):

```java
executor.shutdown();

try {
    if (!executor.awaitTermination(3, java.util.concurrent.TimeUnit.SECONDS)) {
        executor.shutdownNow();

        if (!executor.awaitTermination(3, java.util.concurrent.TimeUnit.SECONDS)) {
            System.err.println("Executor chưa dừng sau khi yêu cầu ngắt");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Hai khoảng 3 giây **chỉ là ví dụ**: hãy chọn theo thời gian đáp ứng, độ nguy hiểm của việc ngắt, khả năng rollback và các thỏa thuận về dữ liệu. Đoạn mã không chứng minh mọi worker đã dừng nếu `awaitTermination` trả `false`. Khi có dữ liệu cần bảo toàn, ứng dụng phải có kế hoạch dọn dẹp, checkpoint hoặc xử lý bù.

Nếu một worker đang giữ lock hoặc kết nối, cần `try/finally` ở chính worker để dọn tài nguyên. Không trông chờ một lời gọi `shutdownNow()` từ caller tự làm thay trách nhiệm đó.

## 9. Chọn cách ngắt hay hủy theo tình huống

| Tình huống | Hướng xử lý phù hợp | Điều cần xác nhận |
|---|---|---|
| Thread tự quản đang chờ queue/latch | `thread.interrupt()`, worker bắt/truyền tín hiệu và thoát | `join()` có timeout hoặc cơ chế hoàn tất |
| Future chưa bắt đầu, không còn cần kết quả | `future.cancel(false)` hoặc chính sách hủy task đợi | `cancel(...)` có thành công; không đọc kết quả từ Future đã hủy |
| Callable đang chạy, có hỗ trợ interrupt | `future.cancel(true)` nếu hợp đồng nghiệp vụ cho phép | Tài nguyên/side effect đã dọn, worker đã ngừng nếu cần |
| Caller hết hạn chờ kết quả nhưng worker vẫn hữu ích | `get(timeout, unit)`, trả trạng thái timeout, không bắt buộc cancel | Tránh tự suy timeout nghĩa là task đã dừng |
| Caller bị interrupt khi gọi `get()` | Propagate hoặc khôi phục cờ; quyết định riêng có cancel task hay không | Caller và worker là hai luồng độc lập |
| Dừng cả executor có thời hạn | `shutdown()`, `awaitTermination`, sau đó cân nhắc `shutdownNow()` | Task chưa bắt đầu, task còn treo, tài nguyên |
| Code không phản ứng interrupt, nguy cơ treo không kiểm soát | Cô lập sang process riêng với timeout và giám sát | Hệ quả khi giết process, retry/idempotency, dữ liệu dang dở |

Nếu task thay đổi dữ liệu bên ngoài (ghi DB, gửi HTTP, chuyển tiền...), hủy Future **không hoàn tác** mọi tác dụng phụ đã xảy ra. Cần nghĩ đến tính idempotent, transaction, timeout phía dịch vụ, compensation và việc tránh submit trùng khi retry.

### Điểm dừng hợp tác trong worker

Một vòng lặp consumer thường có dạng (mẫu minh họa, `process` và `cleanup` do ứng dụng định nghĩa):

```java
static void runConsumer(java.util.concurrent.BlockingQueue<String> queue) {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String item = queue.take();
            process(item);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        cleanup();
    }
}
```

Nếu `process` cũng có thao tác blocking hoặc thay đổi trạng thái chung, nó phải có hợp đồng lỗi/hủy phù hợp. Bắt `InterruptedException` rồi khôi phục cờ nhưng **tiếp tục một vòng `while(true)`** thường dẫn tới lặp nóng: lần chờ interruptible tiếp theo có thể ném ngoại lệ ngay lập tức.

Đôi khi task phải hoàn tất một phần **không thể ngắt an toàn** trước khi kết thúc. Thiết kế cần nói rõ ranh giới đó, dùng vùng thao tác ngắn, rollback khi phù hợp và giữ tín hiệu ngắt cho tầng có trách nhiệm. Không tùy tiện nuốt interrupt để che lỗi vòng đời.

## 10. Những ngộ nhận cần tránh

### “`isDone()` nghĩa là worker đã chạy xong”

Sai. Một Future bị cancel có `isDone() == true`, `isCancelled() == true` mặc dù worker có thể còn chạy hoặc đang dọn dẹp. `isDone()` chỉ là trạng thái terminal của **Future**, không phải lời xác nhận toàn bộ worker đã thoát.

### “`cancel(true)` luôn ném `InterruptedException` trong caller”

Sai. `cancel(true)` trả `boolean` cho caller. Khi Future đã bị hủy, `get()` ném `CancellationException`. `InterruptedException` có thể xuất hiện **trong worker** tại thao tác chờ được ngắt, hoặc **trong caller** nếu chính caller bị interrupt khi chờ một API interruptible.

### “`cancel(false)` chỉ hủy task chưa bắt đầu”

Chưa đầy đủ. Với `FutureTask` đang chạy, `cancel(false)` vẫn có thể hủy **Future** mà không interrupt worker; worker còn làm tiếp nhưng kết quả không còn lấy qua Future ấy. Chi tiết có thể khác giữa các implementation, nên đọc hợp đồng cụ thể.

### “Worker ném `InterruptedException` thì Future chắc chắn canceled”

Sai. Nếu Callable để ngoại lệ thoát và không có thao tác cancel thắng race, Future có thể báo **thất bại** bằng `ExecutionException` có cause là `InterruptedException`. Nếu worker bắt ngoại lệ và return, Future có thể **thành công**.

### “`shutdownNow()` hủy hết Future”

Sai. `shutdownNow()` là nỗ lực dừng executor; nó trả task chưa bắt đầu và không mặc nhiên tương đương gọi `cancel(true)` trên từng Future. Quản lý những Future còn giữ bên ngoài là trách nhiệm tầng điều phối.

### “Có interrupt là có rollback”

Sai. Interrupt tác động lên điều khiển luồng chứ không phải cơ chế transaction. Một task đã ghi dữ liệu, gửi thông báo hay tạo tệp có thể đã tạo side effect trước khi tín hiệu đến.

### “Cưỡng bức dừng một Thread giúp hệ thống an toàn hơn”

Sai. Dừng tại vị trí tùy ý có thể phá invariant và để tài nguyên dang dở. Cách an toàn hơn là dừng hợp tác; khi không kiểm soát được mã, thay đổi ranh giới thực thi (ví dụ process riêng) và chấp nhận bài toán recovery của process.

## 11. Checklist xử lý ngắt và hủy trong ứng dụng thật

Trước khi quyết định hủy một công việc, hãy trả lời:

1. **Ai điều khiển?** Caller, worker, Future hay executor? Luồng nào thực sự nhận interrupt?
2. **Muốn dừng chờ hay dừng công việc?** Timeout của caller có nghĩa task hết giá trị không?
3. **Task có hợp tác không?** Nó có điểm `isInterrupted()`, blocking API interruptible hoặc cờ dừng riêng không?
4. **Kết quả gì được báo?** Future returned value, `ExecutionException`, `CancellationException`, hay caller thấy `InterruptedException`?
5. **Đã dọn xong chưa?** Có `finally`, `join`, `awaitTermination`, latch hoặc một tín hiệu hoàn tất đáng tin không?
6. **Side effect nào đã xảy ra?** Có cần rollback, idempotency, compensation hoặc chống retry trùng không?
7. **Nếu task treo vĩnh viễn?** Có deadline và ranh giới process thích hợp không, thay vì dựa vào `Thread.stop()`?

**Kết luận kỹ thuật:** `Thread.interrupt()` là **tín hiệu hợp tác gửi đến luồng**; `Future.cancel(false/true)` là **yêu cầu đổi trạng thái Future**, trong đó `true` có thể cho phép ngắt worker tùy implementation; `shutdownNow()` chỉ là nỗ lực dừng executor; kết thúc cưỡng bức cần ranh giới riêng và có rủi ro. Luôn phân biệt **tín hiệu yêu cầu dừng**, **trạng thái kết quả của Future** và **bằng chứng công việc đã thật sự kết thúc**.
