# Tách lỗi của tác vụ khỏi lỗi ở luồng đang chờ

Trong lập trình đa luồng Java, **luồng thực hiện tác vụ** (*worker*) và **luồng chờ kết quả** (*waiting thread/caller*) có thể gặp hai loại thất bại hoàn toàn khác nhau. Một phép tính có thể lỗi trong worker, trong khi caller vẫn chờ bình thường. Ngược lại, caller có thể bị ngắt hoặc hết thời gian chờ dù tác vụ vẫn đang chạy đúng.

Nếu trộn các tình huống này, ứng dụng dễ báo nhầm “tác vụ thất bại” khi chỉ có một yêu cầu chờ đã hết hạn; dễ hủy công việc đang cần thiết hoặc thử lại cùng một giao dịch hai lần. Để thiết kế xử lý exception đúng, phải trả lời riêng:

1. **Tác vụ đã hoàn thành như thế nào?** Thành công, thất bại hay bị hủy?
2. **Lần chờ này kết thúc thế nào?** Nhận được kết quả, bị ngắt, hết hạn chờ hay quan sát một tác vụ thất bại/bị hủy?
3. **Caller có còn quyền hoặc nhu cầu chờ nữa không?** Thất bại của thao tác chờ không mặc nhiên quyết định vòng đời tác vụ.

Bài này tập trung vào cơ chế `Future`, `ExecutorService` và `CompletableFuture` trong Java 17+, cùng cách phân loại, truyền thông tin và xử lý các đường lỗi trong hệ thống thực tế.

## 1. Hai hoạt động, hai ranh giới exception

Xét mô hình:

```text
Luồng caller                         Luồng worker
    |                                      |
    |--- submit(callable) --------------->| nhận tác vụ
    |<-- Future --------------------------|
    |                                      | tính toán / gọi I/O
    |--- future.get()                      |
    |        |                             |
    |        |                             +-- thành công: result
    |        |                             |
    |        |                             +-- thất bại: Throwable
    |        |
    +-- kết thúc chờ: value / ExecutionException
                    / InterruptedException
                    / TimeoutException / CancellationException
```

Một exception được ném trong `Callable.call()` **không tự động được ném trực tiếp trên stack của caller**. Với `ExecutorService.submit`, executor ghi nhận kết quả của tác vụ vào một `Future`; caller gọi `get()` để truy cập kết quả hoặc biết vì sao nó không có kết quả.

Tương tự, exception xảy ra trong `future.get()` không nhất thiết xuất phát từ logic bên trong task. Caller có thể bị ngắt khi đang chờ, hoặc thời hạn chờ do caller chọn có thể hết trước khi task kết thúc.

Ví dụ:

- Worker đọc dữ liệu và ném `IllegalArgumentException("bad input")`. Caller chờ bình thường, nhưng `Future.get()` ném `ExecutionException` có `getCause()` là `IllegalArgumentException`.
- Worker đang đợi I/O, caller chờ bằng `get()` thì bị thread khác gọi `interrupt()`. Chính caller gặp `InterruptedException`; worker có thể vẫn chạy.
- Worker cần 5 giây, caller chỉ cho phép đợi 100 ms bằng `get(100, MILLISECONDS)`. Caller gặp `TimeoutException`; tác vụ không bị hủy chỉ vì lần chờ hết hạn.
- Ai đó đã gọi `future.cancel(...)` thành công. Khi quan sát `Future` đã bị hủy, `get()` ném `CancellationException`.

Cần hiểu **nơi ngoại lệ phát sinh và ý nghĩa vòng đời** trước khi quyết định retry, cancel, rollback hoặc trả lỗi.

## 2. Bốn đường kết thúc quan trọng của Future.get

`Future<V>.get()` có thể trả giá trị hoặc ném exception. Phiên bản có timeout bổ sung `TimeoutException`.

| Kết quả quan sát khi caller chờ | Loại exception tại caller | Ý nghĩa chính | Có chứng minh task tự thất bại? |
| --- | --- | --- | --- |
| Task thành công | Không; `get()` trả `V` | Có kết quả | Không |
| Task kết thúc do exception | `ExecutionException` | Lỗi xảy ra trong quá trình thực thi task; đọc `getCause()` | **Có**, với task đã hoàn thành exceptional |
| Thread gọi `get()` bị ngắt khi chờ | `InterruptedException` | Thao tác chờ của **caller** bị gián đoạn | **Không** |
| Hết hạn chờ của `get(timeout, unit)` | `TimeoutException` | Caller chưa nhận kết quả trong khoảng đợi được cấp | **Không** |
| `Future` đã bị hủy | `CancellationException` (unchecked) | Kết quả không còn được cung cấp vì hủy | Không đồng nghĩa task thất bại theo logic nghiệp vụ |

Có thể thấy `Future.get()` không chỉ “ném exception của worker”. Nó là một API **chờ và quan sát trạng thái**, nên có các exception gắn với cả **kết quả** lẫn **chính hành vi chờ**.

### ExecutionException: lỗi thuộc quá trình chạy task

`ExecutionException` là lớp bao (checked exception) báo rằng phép tính do `Future` đại diện đã kết thúc bất thường. Hãy xem `getCause()` để biết lỗi nền:

```java
try {
    String value = future.get();
} catch (ExecutionException wrapper) {
    Throwable taskFailure = wrapper.getCause();
    // Phân loại theo lỗi có ý nghĩa của task/API.
}
```

Đây là snippet minh họa, giả định `future` là `Future<String>` và phần còn lại của chương trình xử lý `InterruptedException`. Không nên xem chính lớp `ExecutionException` là lỗi nghiệp vụ: nhiều loại thất bại khác nhau đều có thể bị bao trong lớp này.

Nếu `taskFailure` là một exception ứng dụng có mã lỗi ổn định, có thể xử lý có chủ đích. Nếu là bug hoặc `Error` nghiêm trọng, không tùy tiện biến thành lỗi “dữ liệu không hợp lệ”.

### InterruptedException: lỗi thuộc lần chờ của caller

`InterruptedException` trong `Future.get()` thường cho biết **thread đang gọi `get`** đã bị ngắt trong khi chờ. Java cho phép thread khác yêu cầu interruption, ví dụ khi hệ thống shutdown hoặc hủy workflow. Điều đó **không nói rằng worker đã bị ngắt** và cũng không nói rằng worker đã thất bại.

Mẫu xử lý khi không thể truyền `InterruptedException` trực tiếp lên caller:

```java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new WaitAbortedException("Đã dừng chờ kết quả", interrupted);
}
```

Đoạn này chỉ minh họa, với `future`, kiểu trả về và `WaitAbortedException` được xác định bởi API thực. Việc gọi `Thread.currentThread().interrupt()` phục hồi cờ interrupt mà thao tác blocking đã thường xóa khi ném `InterruptedException`. Nếu phương thức có thể khai báo `throws InterruptedException` và để caller quyết định, có thể truyền tiếp chính checked exception đó.

**Không gọi `future.cancel(true)` vô điều kiện trong catch** nếu caller chỉ bị ngắt nhưng tác vụ là công việc được chia sẻ, hoặc chính sách của ứng dụng muốn tác vụ tiếp tục. Chỉ hủy khi caller thực sự sở hữu quyền hủy và giao kèo vận hành yêu cầu như vậy.

### TimeoutException: hết thời gian chờ, chưa phải timeout của task

`future.get(200, TimeUnit.MILLISECONDS)` giới hạn **thời gian caller chờ để lấy kết quả**. Nếu timeout xảy ra:

- `Future` có thể vẫn đang chạy, đang đợi trong queue hoặc vừa hoàn thành gần thời điểm hết hạn.
- `get(timeout, unit)` **không tự gọi `cancel`**.
- Caller có thể chờ lại sau, kiểm tra `isDone()`, hoặc chọn hủy nếu chính sách đã định.
- Nếu đã quyết định retry công việc mới, cần kiểm tra liệu công việc cũ có còn side effect hoặc có đang xử lý cùng dữ liệu không.

`TimeoutException` cũng không đồng nghĩa với timeout ở tầng socket, query hay dịch vụ bên ngoài. Một task có thể tự ném `SocketTimeoutException`; khi đó `Future.get` báo `ExecutionException` có cause là exception của **worker**, không phải `TimeoutException` của thao tác chờ.

### CancellationException: trạng thái đã hủy

Sau khi `Future.cancel(...)` thành công, `isCancelled()` trả `true` và `get()` ném `CancellationException`. `CancellationException` là unchecked exception.

`cancel(true)` có thể yêu cầu ngắt thread đang chạy, nhưng không bảo đảm code worker sẽ lập tức ngừng: nó phải hợp tác với interruption và có thể đã thực hiện side effect. `cancel(false)` không ngắt task đang chạy; với task chưa bắt đầu có thể ngăn thực thi, còn với task đang chạy `Future` có thể chuyển sang trạng thái hủy theo hợp đồng implementation dù công việc nền vẫn tiếp tục.

Vì thế **trạng thái đã hủy của Future** không chứng minh rằng tác vụ đã dừng mọi hoạt động hoặc rollback xong.

## 3. Ví dụ Java 17 hoàn chỉnh: tách ba nguồn lỗi

Ví dụ sau có ba nhóm kết quả được kiểm soát:

1. Task tự ném `IllegalArgumentException`; caller thấy `ExecutionException` và cause.
2. Chính task ném **`InterruptedException`**; caller vẫn thấy **`ExecutionException`**, vì exception đó xảy ra trong `Callable`.
3. Task thứ ba bị chặn bằng `CountDownLatch`. Lần chờ đầu hết hạn; lần chờ khác bị interruption; cuối cùng task vẫn được giải phóng và trả kết quả thành công.

Ví dụ cố ý dùng latch thay cho `Thread.sleep(...)` để kết quả không phụ thuộc vào thứ tự lập lịch tình cờ giữa các thread.

Tạo tệp `TaskAndWaiterFailuresDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class TaskAndWaiterFailuresDemo {

    private static void printTaskFailure(
            String label, Future<String> future)
            throws InterruptedException {
        try {
            future.get();
            System.out.println(label + ": unexpected success");
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            System.out.println(
                label + ": ExecutionException -> "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage()
            );
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch releaseTask = new CountDownLatch(1);

        try {
            Future<String> failed = executor.submit(
                (Callable<String>) () -> {
                    throw new IllegalArgumentException("bad input");
                }
            );
            printTaskFailure("TASK_ERROR", failed);

            Future<String> taskInterrupted = executor.submit(
                (Callable<String>) () -> {
                    throw new InterruptedException("from task");
                }
            );
            printTaskFailure("TASK_INTERRUPTED", taskInterrupted);

            CountDownLatch taskStarted = new CountDownLatch(1);
            Future<String> pending = executor.submit(
                (Callable<String>) () -> {
                    taskStarted.countDown();
                    releaseTask.await();
                    return "done";
                }
            );

            // Đảm bảo worker đang ở trước điểm trả kết quả;
            // releaseTask chưa được giải phóng.
            taskStarted.await();

            try {
                pending.get(1, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println(
                    "WAIT_TIMEOUT: cancelled=" + pending.isCancelled()
                );
            } catch (ExecutionException ex) {
                System.out.println("unexpected task failure");
            }

            AtomicReference<String> waitOutcome =
                    new AtomicReference<>("not observed");

            Thread waiter = new Thread(() -> {
                try {
                    pending.get();
                    waitOutcome.set("unexpected success");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    waitOutcome.set(
                        "InterruptedException; restored="
                            + Thread.currentThread().isInterrupted()
                    );
                } catch (ExecutionException ex) {
                    waitOutcome.set("unexpected task failure");
                }
            }, "waiting-thread");

            waiter.start();
            // Worker chưa được giải phóng nên waiter
            // không thể nhận kết quả thành công trước interrupt.
            waiter.interrupt();
            waiter.join();
            System.out.println("WAIT_INTERRUPTED: " + waitOutcome.get());

            // Caller có thể nhận kết quả sau hai lần chờ thất bại.
            releaseTask.countDown();
            try {
                System.out.println("TASK_RESULT: " + pending.get());
            } catch (ExecutionException ex) {
                System.out.println("unexpected task failure");
            }
        } finally {
            releaseTask.countDown();
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 TaskAndWaiterFailuresDemo.java
java TaskAndWaiterFailuresDemo
```

Stdout:

```text
TASK_ERROR: ExecutionException -> IllegalArgumentException: bad input
TASK_INTERRUPTED: ExecutionException -> InterruptedException: from task
WAIT_TIMEOUT: cancelled=false
WAIT_INTERRUPTED: InterruptedException; restored=true
TASK_RESULT: done
```

Đối chiếu từng tình huống:

- `TASK_ERROR`: exception được ném trong `Callable`, được `Future` lưu giữ. Người gọi nhận `ExecutionException` và phân loại `IllegalArgumentException` qua `getCause()`.
- `TASK_INTERRUPTED`: **worker tự ném `InterruptedException`** trong task. Điều này không làm `future.get()` của main ném `InterruptedException`; main đang chờ bình thường nên vẫn nhận `ExecutionException`. Hai exception có tên giống nhau nhưng phát sinh ở hai luồng khác nhau.
- `WAIT_TIMEOUT`: task thứ ba chưa thể trả kết quả vì `releaseTask` vẫn ở giá trị chưa được giải phóng. Lần chờ bị timeout và `pending.isCancelled()` vẫn `false`.
- `WAIT_INTERRUPTED`: thread `waiting-thread` bị gọi `interrupt()` khi đang chuẩn bị/đang thực hiện `get()`. Nó bắt `InterruptedException`, phục hồi cờ interrupt bằng `Thread.currentThread().interrupt()`; `isInterrupted()` trả `true`. Task không bị hủy.
- `TASK_RESULT`: sau khi `releaseTask.countDown()`, task hoàn thành và trả `"done"`. Cả timeout lẫn interruption của một waiter trước đó đều không làm task bị lỗi.
- `finally` giải phóng latch nếu main rời đoạn xử lý vì lỗi bất ngờ, rồi yêu cầu executor shutdown. `shutdownNow()` chỉ là yêu cầu dừng/chặn công việc; trong ví dụ thành công, các `Future.get()` đã hoàn thành trước khi cleanup.

**Giới hạn của ví dụ:** thread `waiter` bắt đúng các exception liên quan tới `get()`; `join()` của main vẫn có thể bị ngắt bởi cơ chế bên ngoài, và main khai báo `throws InterruptedException`. Trong ứng dụng thực, quản lý executor thường do một component owner chịu trách nhiệm với lifecycle có kiểm soát; không mặc định dùng `shutdownNow()` để kết thúc mọi tác vụ đang chạy.

## 4. Vì sao InterruptedException có thể xuất hiện ở hai vị trí?

Đây là điểm gây nhầm lẫn lớn nhất. Cùng là `InterruptedException`, nhưng ý nghĩa thay đổi theo **nơi ném và nơi bắt**:

### 4.1. InterruptedException ném trong worker

Giả sử `Callable<String>.call()` gọi `BlockingQueue.take()`, bị ngắt và cho `InterruptedException` truyền ra. Tác vụ thất bại; với `FutureTask` của `submit`, nó được ghi là nguyên nhân của một kết thúc exceptional.

Caller chờ qua `Future.get()`:

```java
try {
    future.get();
} catch (ExecutionException ex) {
    if (ex.getCause() instanceof InterruptedException) {
        // Chính task đã bị gián đoạn rồi kết thúc bằng exception.
    }
}
```

Đoạn minh họa giả định có `future`. `ExecutionException` thuộc lớp quan sát kết quả; `InterruptedException` là cause xảy ra trong worker. Caller có thể vẫn chưa từng bị interrupt.

### 4.2. InterruptedException ném bởi get() ở caller

Nếu thread đang chờ bị interrupt, `get()` có thể ném `InterruptedException` ngay ở caller:

```java
try {
    future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Chính việc chờ đã bị ngắt; không suy ra task thất bại.
}
```

Đoạn này cũng chỉ là snippet, giả định xử lý `ExecutionException` được viết ở nơi phù hợp. Caller có thể rời khỏi phép chờ trong khi worker tiếp tục.

Một khác biệt kỹ thuật quan trọng: `Thread.interrupted()` **đọc và xóa** trạng thái interrupt của thread hiện tại; `Thread.currentThread().isInterrupted()` đọc nhưng không xóa. Đừng dùng `Thread.interrupted()` như lệnh “kiểm tra vô hại” trong các luồng điều khiển còn cần biết interrupt.

Trong task, nếu bắt `InterruptedException` nhưng không thể truyền tiếp, có thể phục hồi cờ interrupt rồi kết thúc có kiểm soát. Không biến interruption thành lỗi nghiệp vụ thông thường để thử lại vô hạn.

## 5. Timeout khi chờ khác với timeout xảy ra trong tác vụ

Hai dạng đều có chữ “timeout”, nhưng thuộc hai hợp đồng khác nhau:

**Timeout của lời gọi chờ:**

```java
future.get(500, TimeUnit.MILLISECONDS);
```

Nếu không có kết quả đúng lúc, **chính caller** nhận `TimeoutException`. Task không tự biết rằng caller đã bỏ chờ. Caller có thể chọn tiếp tục chờ, kiểm tra `isDone()` hoặc yêu cầu cancel.

**Timeout bên trong task:**

```java
Callable<String> task = () -> {
    // Một operation có thể ném SocketTimeoutException.
    return fetchRemoteData();
};
```

Đây là snippet giả định `fetchRemoteData()` và import phù hợp. Nếu operation trong worker ném `java.net.SocketTimeoutException` và exception ấy truyền ra `call()`, `Future.get()` ném `ExecutionException` với `getCause()` là `SocketTimeoutException`. Người gọi đã nhận **kết quả thất bại của task**, không chỉ hết giới hạn thời gian của lần chờ.

Điều kiện caller cần xử lý khác nhau:

| Nguồn timeout | Tác vụ có được biết là thất bại? | Quyết định thường gặp |
| --- | --- | --- |
| `Future.get(timeout)` vượt hạn | Chưa; có thể còn chạy hoặc sắp xong | Chờ lại, trả trạng thái pending, hoặc hủy nếu sở hữu quyền và có chính sách. |
| Timeout network trong `Callable` và exception truyền ra | Có, task hoàn thành exceptional | Phân loại lỗi I/O, đánh giá retry/idempotency. |
| Deadline ở tầng service chủ động cancel task | `Future` có thể chuyển sang trạng thái canceled; worker có thể chưa dừng | Báo hủy, phối hợp cleanup và xử lý side effect theo contract. |

Một yêu cầu HTTP bên ngoài trả “request timeout” không chứng minh thao tác phía server đã rollback. Nếu thực hiện lại ngay, có thể tạo dữ liệu trùng. Cần idempotency key hoặc cơ chế đối soát khi thích hợp.

## 6. CancellationException và giới hạn của cancel()

Một `Future` có thể được hủy bằng `cancel(boolean mayInterruptIfRunning)`. Lời gọi trả `boolean` cho biết việc chuyển sang trạng thái hủy có thành công theo `Future` hay không. Sau khi hủy thành công, `isCancelled()` trả `true` và `get()` ném `CancellationException`.

Ví dụ chạy độc lập Java 17, không yêu cầu executor:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

public class CancelledResultDemo {
    public static void main(String[] args) {
        CompletableFuture<String> result = new CompletableFuture<>();
        System.out.println("cancelled: " + result.cancel(false));

        try {
            result.join();
        } catch (CancellationException ex) {
            System.out.println("observed: CancellationException");
        }

        System.out.println("isCancelled: " + result.isCancelled());
    }
}
```

Biên dịch và chạy:

```bash
javac CancelledResultDemo.java
java CancelledResultDemo
```

Stdout:

```text
cancelled: true
observed: CancellationException
isCancelled: true
```

Ở đây `CompletableFuture` được tạo chưa hoàn thành, `cancel(false)` đánh dấu nó hoàn thành exceptional vì cancellation; không có worker nào để ngắt. `join()` ném `CancellationException` trực tiếp đối với trạng thái cancelled của chính future.

**Lưu ý đặc biệt đối với `CompletableFuture`:** tham số `mayInterruptIfRunning` của `CompletableFuture.cancel` không được sử dụng để điều khiển interrupt một task đang chạy theo cách của một `FutureTask`; cancellation được biểu diễn ở trạng thái hoàn thành của `CompletableFuture`. Đừng suy luận từ việc gọi `cancel(true)` rằng một luồng tính toán gắn với nó đã chắc chắn bị ngắt.

Với `FutureTask` hoặc implementation executor cụ thể, `cancel(true)` có thể yêu cầu interrupt thread chạy task. Yêu cầu này có thể không được phản hồi nếu task không hợp tác, đang trong một thao tác không interruptible hoặc đã thực hiện side effect trước khi dừng.

## 7. Vì sao Thread.join() không thể truyền lại lỗi của tác vụ?

`Thread.join()` chỉ chờ thread kết thúc, không mang đối tượng kết quả. Một `Thread` có thể kết thúc bình thường hoặc do uncaught exception, nhưng caller không nhận một `ExecutionException` từ `join()`.

Snippet minh họa:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("failed");
});
worker.start();
worker.join();

// join() trả về khi worker kết thúc; không ném lại "failed".
```

Đoạn code này cần đặt trong phương thức khai báo hoặc xử lý `InterruptedException`. Worker có thể báo uncaught exception qua `Thread.UncaughtExceptionHandler`, nhưng đó là kênh quan sát cuối cùng của **thread**, không phải một `Future` trả kết quả cho caller.

Với một tác vụ cần người gọi xử lý được lỗi và giá trị, ưu tiên abstraction kết quả như `Future`, `CompletionStage` hoặc kênh truyền kết quả có cấu trúc. Đừng dựa vào default uncaught handler để làm logic giao dịch.

## 8. ExecutorService.execute khác submit ở đường đi của exception

`execute(Runnable)` và `submit(Callable/Runnable)` có thể khác cách exception được chuyển tới client.

| API | Exception do task ném | Kênh quan sát |
| --- | --- | --- |
| `new Thread(runnable).start()` | Nếu thoát khỏi `run()`, thread kết thúc bất thường | Uncaught handler của thread/`ThreadGroup`. |
| `ThreadPoolExecutor.execute(runnable)` | Với `Runnable` thông thường và implementation chuẩn, unchecked exception thoát khỏi worker; worker có thể bị thay thế | Handler, log của worker, hoặc hook quản lý executor. |
| `ExecutorService.submit(callable)` | Exception được wrapper task như `FutureTask` bắt và ghi nhận | `Future.get()` nhận `ExecutionException` với cause. |
| `CompletableFuture.supplyAsync(supplier)` | Exception được phản ánh vào trạng thái completed exceptionally | `join/get`, `whenComplete`, `handle`, `exceptionally`. |

Đây là các hành vi thường gặp ở implementation chuẩn; nếu executor/framework sử dụng wrapper, cơ chế xử lý có thể khác. Một số framework bắt task error và gọi callback nội bộ thay vì để exception thoát đến uncaught handler.

Nếu override `ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` để giám sát, không chỉ kiểm tra `t`: với tác vụ do `submit` tạo thành `FutureTask`, `t` có thể bằng `null` dù task đã thất bại, do lỗi được lưu trong `Future`. Cần hiểu thời điểm hoàn thành, trạng thái hủy và cách truy cập `Future.get()` phù hợp trước khi xây dựng cơ chế giám sát chung.

## 9. CompletableFuture: get, join và callback lỗi

`CompletableFuture` cũng cho thấy khác biệt giữa **trạng thái kết quả** và **cách người gọi quan sát**.

Khi một stage hoàn thành exceptional vì lỗi nghiệp vụ, có hai cách đọc phổ biến:

- `future.get()`: dùng checked `ExecutionException` cho thất bại của stage; người gọi phải quan tâm `InterruptedException`.
- `future.join()`: thường ném unchecked `CompletionException` cho thất bại của stage; không khai báo checked `InterruptedException`. `join()` không trở thành một API chờ có thể ngắt theo cùng cách `get()`.
- Khi stage bị hủy, `join()` có thể ném `CancellationException` trực tiếp; các stage phụ thuộc có thể thể hiện hủy ở dạng exceptional completion và wrapping phù hợp với quan hệ stage.

Một ví dụ Java 17 độc lập dùng `CompletableFuture.failedFuture`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class StageFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                    new IllegalStateException("bad state")
                );

        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println(
                "JOIN: " + ex.getCause().getClass().getSimpleName()
            );
        }

        try {
            failed.get();
        } catch (ExecutionException ex) {
            System.out.println(
                "GET: " + ex.getCause().getClass().getSimpleName()
            );
        }

        String recovered = failed.exceptionally(ex -> "fallback").join();
        System.out.println("RECOVERY: " + recovered);
    }
}
```

Biên dịch và chạy:

```bash
javac StageFailureDemo.java
java StageFailureDemo
```

Stdout:

```text
JOIN: IllegalStateException
GET: IllegalStateException
RECOVERY: fallback
```

`failedFuture` tạo một future **đã hoàn thành exceptional** nên không cần thread thực thi và không có race trong ví dụ. `join` và `get` chỉ là hai cách quan sát cùng một trạng thái đã thất bại.

`exceptionally` tạo một stage mới có thể trả giá trị thay thế. Nó không sửa trực tiếp exception của stage gốc; `failed` vẫn là stage thất bại. Nếu hàm recovery tự ném exception, stage mới cũng có thể hoàn thành exceptional.

### whenComplete và handle

- `whenComplete((value, error) -> ...)` chủ yếu để quan sát giá trị hoặc lỗi và trả một stage phụ thuộc. Nếu callback chạy thành công, stage phụ thuộc giữ trạng thái thành công/thất bại của stage gốc. Nếu callback tự ném, cần đọc quy tắc exceptional completion để hiểu lỗi nào được ưu tiên.
- `handle((value, error) -> result)` có thể **biến cả kết quả thành công lẫn lỗi thành một kết quả mới**, phù hợp khi muốn phân loại và chuyển lỗi ở ranh giới của pipeline.
- `exceptionally(error -> fallback)` xử lý đường lỗi để tạo giá trị thay thế.
- `join()` rất tiện nhưng không tự phân loại lỗi và không có checked `InterruptedException`; với hệ thống muốn cooperative cancellation của caller, chọn cơ chế chờ và giám sát thích hợp.

Không dùng callback chỉ ghi log làm bằng chứng “đã xử lý” nếu luồng nghiệp vụ vẫn cần ra quyết định. Phải quản lý stage trả về và sự thất bại của callback.

## 10. Timeout của CompletableFuture và điểm dễ nhầm

`CompletableFuture` có những API timeout làm thay đổi trạng thái future, khác với `get(timeout)`:

| API | Tác động |
| --- | --- |
| `future.get(timeout, unit)` | Đặt giới hạn chờ cho **một lần gọi**; nếu hết hạn ném `TimeoutException`, tự nó không hoàn thành/hủy future. |
| `future.orTimeout(timeout, unit)` | Sắp đặt để **chính CompletableFuture này** hoàn thành exceptional bằng `TimeoutException` nếu đến hạn mà vẫn chưa hoàn thành. |
| `future.completeOnTimeout(value, timeout, unit)` | Sắp đặt để **chính CompletableFuture này** hoàn thành bình thường bằng giá trị dự phòng nếu hết hạn trước khi nó hoàn thành. |

Các phương thức `orTimeout` và `completeOnTimeout` trả về chính `CompletableFuture` đang được cấu hình; chúng không phải là một bản sao tách biệt của phép tính ban đầu.

Khi `orTimeout` làm future hoàn thành exceptional, gọi `get()` sau đó thường ném `ExecutionException` với cause là `TimeoutException`. Đây là **lỗi đã được ghi vào trạng thái future**. Nó khác với một lời gọi `get(timeout)` tự ném `TimeoutException` ngay tại waiter.

`completeOnTimeout` cũng chỉ thiết lập kết quả của `CompletableFuture` nếu nó vẫn chưa hoàn thành lúc đến hạn; nó **không mặc nhiên ngắt hoặc dừng công việc nền** đang cố hoàn thành future. Nếu công việc cũ có side effect, vẫn phải kiểm soát riêng.

Với pipeline không muốn can thiệp trạng thái shared future chỉ để giới hạn thời gian đợi của một caller, hãy dùng cơ chế chờ có timeout hoặc thiết kế một stage riêng có chính sách timeout rõ ràng, thay vì gọi `orTimeout` tùy tiện lên shared future.

## 11. Biểu diễn lỗi ổn định qua ranh giới async

Trong API async, caller nên phân biệt **lỗi nghiệp vụ của tác vụ** và **lỗi vận hành khi chờ**. Chỉ đưa các loại lỗi cần caller xử lý vào hợp đồng công khai; tránh làm lộ exception nội bộ của executor hoặc dependency.

Ví dụ:

```java
public CompletableFuture<Report> generateReport(ReportRequest request);
```

Đây là chữ ký minh họa; `Report`, `ReportRequest` và class chứa phương thức chưa định nghĩa. Hợp đồng cần nêu:

- Future sẽ hoàn thành bình thường với `Report` trong điều kiện nào?
- Nó hoàn thành exceptional với lỗi nào có ý nghĩa ổn định: validation, không có dữ liệu, mất kết nối, hạn mức?
- Exception gốc của task được giữ trong `cause` như thế nào?
- Ai có quyền cancel và liệu cancel có dừng công việc thực tế không?
- Có giới hạn thời gian ở mức tác vụ hoặc workflow không, và timeout có thể xảy ra sau side effect nào?
- Nếu caller ngừng chờ, kết quả có còn được lưu, sự kiện có được gửi tiếp hay không?

Không nên viết API async mà buộc người dùng bắt kiểu exception của thư viện HTTP/DB nội bộ nếu đó không phải cam kết thiết kế. Cũng không nên biến mọi exception thành `RuntimeException("Failed")` rồi làm mất mã lỗi hoặc nguyên nhân có giá trị điều tra.

Nếu cần trả trạng thái “pending” hoặc “retry later” cho tầng HTTP, kết quả đó phải dựa trên chính sách của workflow; một `TimeoutException` tại waiter không đủ để tuyên bố toàn bộ task đã thất bại.

## 12. Ai sở hữu quyền hủy và vòng đời tác vụ?

Caller có quyền chờ không tự động có quyền **hủy task cho mọi người**. Một `Future` có thể đại diện cho tác vụ độc quyền của một request, hoặc một công việc được nhiều caller cùng quan sát.

Cân nhắc:

1. Task là **độc quyền** hay được **chia sẻ**? Hủy theo timeout của một caller có khiến caller khác mất công việc không?
2. Task đã thực hiện side effect chưa? Có idempotency key hoặc thao tác bù không?
3. `cancel(true)` có được task hỗ trợ bằng interruption không? Task có cleanup trong `finally`/`try-with-resources` không?
4. Nếu caller bị ngắt, chính sách có yêu cầu truyền `InterruptedException`, khôi phục cờ rồi thoát, hay vẫn duy trì task?
5. Khi executor shutdown, ai chờ task kết thúc và giải phóng tài nguyên? Không được để việc một waiter bỏ chờ làm mồ côi tài nguyên.

Tránh kết hợp mù quáng:

```java
catch (TimeoutException ex) {
    future.cancel(true);
    return retrySameOperation();
}
```

Đây là snippet **minh họa một cách làm có thể nguy hiểm**, không phải chương trình độc lập. Nếu task cũ đã ghi một phần dữ liệu hoặc không phản hồi interruption, việc retry ngay có thể gây thao tác trùng. Trước khi hủy/thử lại, phải xác định quyền sở hữu, bảo đảm dừng và tính idempotent của thao tác.

Trong một hệ thống xử lý thanh toán, timeout của request ở tầng web có thể cần trả “đang xử lý” và cung cấp mã tra cứu trạng thái, thay vì khẳng định “thanh toán thất bại”.

## 13. Xử lý exception đúng theo từng lớp

Một ví dụ giả định hệ thống có web request đợi task nhập báo cáo:

- **Task layer** bắt những exception mà nó có thể giải thích hoặc khắc phục; exception còn lại được Future/CompletionStage ghi nhận.
- **Task boundary** dịch lỗi vendor thành mã lỗi ổn định của ứng dụng, bảo toàn cause để chẩn đoán.
- **Waiting/request layer** phân biệt `ExecutionException` (task đã thất bại), `InterruptedException` (caller bị ngắt), `TimeoutException` (lần chờ hết hạn), `CancellationException` (result bị hủy).
- **Workflow owner** quyết định có cancel hay chờ tiếp, theo tính quan trọng của tác vụ và quyền sở hữu.
- **Monitoring** theo dõi task thất bại cũng như waiter timeout/interruption, nhưng không gộp tất cả thành cùng một chỉ số “task failure”.

Mẫu phân loại **minh họa**, không phải chương trình độc lập:

```java
try {
    return future.get(waitDuration, TimeUnit.MILLISECONDS);
} catch (ExecutionException ex) {
    Throwable taskCause = ex.getCause();
    throw translateTaskFailure(taskCause);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new WaitingInterruptedException(ex);
} catch (TimeoutException ex) {
    throw new ResultNotReadyException(ex);
} catch (CancellationException ex) {
    throw new TaskCancelledException(ex);
}
```

Các kiểu `WaitingInterruptedException`, `ResultNotReadyException`, `TaskCancelledException`, hàm `translateTaskFailure`, biến `future` và `waitDuration` là phần giả định của API ứng dụng. Quan trọng là **mỗi nhánh có ý nghĩa khác nhau**, và không gọi `future.cancel(true)` nếu policy không yêu cầu.

Nếu một lỗi `ExecutionException` mang cause `InterruptedException` do **task** thất bại thì đừng nhầm và tự đánh dấu **waiter** bị ngắt. Không gọi `Thread.currentThread().interrupt()` trên waiter chỉ vì cause từ worker là `InterruptedException`: đó là interrupt thuộc bối cảnh của worker, không thuộc thread hiện tại.

## 14. Đừng quên xử lý khi waiter bị interrupt

Interruption là cơ chế hợp tác, không giống việc ném một exception nghiệp vụ thông thường. Khi một phương thức blocking ném `InterruptedException`, trạng thái interrupt của thread hiện tại thường đã được xóa. Hai cách xử lý phù hợp:

**Cách A — truyền tiếp interruption:**

```java
public String waitResult(Future<String> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
```

Snippet này là một phương thức Java hợp lệ khi nằm trong một class và có import tương ứng. Caller cao hơn quyết định dừng hoặc phục hồi; phương thức không đổi nghĩa lỗi.

**Cách B — đổi loại lỗi nhưng khôi phục cờ:**

```java
try {
    return future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new WaitingInterruptedException(ex);
}
```

Snippet này cần ngữ cảnh class/kiểu như đã nêu; mục đích là giữ tín hiệu interruption cho các tầng sau.

Không swallow `InterruptedException` rồi gọi `get()` lại trong vòng lặp vô hạn. Làm vậy có thể khiến shutdown không hoàn tất hoặc caller bị kẹt lâu hơn chính sách cho phép.

Nếu trong `finally` phải cleanup resource thuộc quyền sở hữu của caller, hãy dọn đúng phạm vi; không tự đóng tài nguyên của worker chỉ vì waiter bị ngắt.

## 15. Kiểm thử các kênh lỗi một cách độc lập

Một bộ test tốt phân biệt được nguồn thất bại ngay cả khi output nhìn tương tự nhau.

| Kịch bản | Kỳ vọng ở caller | Khẳng định về task |
| --- | --- | --- |
| `Callable` trả giá trị | `get()` trả kết quả | Thành công |
| `Callable` ném `IllegalArgumentException` | `ExecutionException`; cause là `IllegalArgumentException` | Hoàn thành thất bại |
| `Callable` ném `InterruptedException` | `ExecutionException`; cause là `InterruptedException` | Hoàn thành thất bại do exception trong task |
| Thread gọi `get()` bị interrupt khi đang chờ | `InterruptedException` tại waiter | Không kết luận task đã thất bại |
| `get(timeout)` hết hạn khi task còn bị chặn | `TimeoutException` | Không bị hủy bởi `get(timeout)` |
| `cancel(...)` thành công | `CancellationException` khi `get()` | Future bị hủy; không suy ra mọi side effect đã dừng |
| `CompletableFuture` exceptional | `get()` thường dùng `ExecutionException`; `join()` thường dùng `CompletionException` | Stage chứa thất bại |
| `CompletableFuture.orTimeout` hoàn thành exceptional | `get()` nhận `ExecutionException` có cause `TimeoutException` | Đây là trạng thái exceptional của future |

Dùng `CountDownLatch`, `Phaser` hoặc synchronization phù hợp để kiểm soát thứ tự test. Không dựa hoàn toàn vào `Thread.sleep(50)` rồi hy vọng tác vụ vẫn đang chạy; test theo thời gian như vậy dễ thất thường khi CI bị quá tải.

Chú ý rằng task có thể đã hoàn thành ngay trước khi caller gọi `interrupt` hoặc `get(timeout)`. Trong test muốn chắc chắn phân biệt lỗi waiter, cần giữ task ở một điểm chưa thể trả kết quả — ví dụ latch chưa được mở — như chương trình ở mục 3.

### Tránh test “đúng exception nhưng sai luồng”

Nếu test cần xác nhận `InterruptedException` của **caller**, hãy điều khiển thread đang gọi `get()` và kiểm tra code catch ở **thread đó**. Không thể kiểm tra bằng cách khiến worker throw `InterruptedException` rồi nghĩ đã thử đường lỗi waiter.

Ngược lại, nếu test cần xác nhận task failure, hãy dùng `Future.get()` và kiểm tra `ExecutionException.getCause()`. Gọi `join()` của `Thread` trực tiếp hoặc chỉ kiểm tra log của `UncaughtExceptionHandler` không thay thế bộ kiểm tra hợp đồng `Future`.

## 16. Lỗi thường gặp

**“`Future.get()` ném `InterruptedException` nên task đã bị ngắt.”** Sai: đó thường là thread gọi `get` bị ngắt. Task có thể tiếp tục chạy và trả kết quả sau.

**“Task ném `InterruptedException` nên caller phải catch `InterruptedException` từ `get`.”** Với `submit(Callable)` thông thường, task failure được bao trong `ExecutionException`, kể cả cause là `InterruptedException`.

**“`TimeoutException` nghĩa là tác vụ thất bại.”** Timeout của lần chờ chỉ nói caller chưa nhận kết quả kịp thời. Không tự hủy hoặc gán lỗi cho task.

**“Hết hạn chờ thì retry ngay.”** Tác vụ cũ có thể vẫn đang ghi dữ liệu. Retry có thể gây trùng side effect; xem xét idempotency và quyền hủy.

**“`cancel(true)` đã ngừng mọi hoạt động.”** Interruption có tính hợp tác; trạng thái canceled không chứng minh worker đã giải phóng xong tài nguyên hay rollback.

**“Bỏ `Future` là lỗi đã được logger ghi.”** Với `submit`, exception có thể được lưu trong Future và không thoát đến uncaught handler; nếu không ai đọc Future thì thất bại có thể bị bỏ qua.

**“Cứ `catch (Exception)` rồi trả một lỗi chung.”** Cách này làm mất phân biệt task failure, waiting interruption, deadline và cancellation. Việc retry hoặc trả trạng thái sai dễ xảy ra.

**“`CompletionException` và `ExecutionException` khác nguyên nhân nghiệp vụ.”** Chúng thường là hai lớp bao tùy API quan sát (`join` hoặc `get`) cho cùng thất bại của một `CompletableFuture`.

**“Lỗi của worker là lỗi interrupt của caller.”** Không khôi phục cờ interrupt của caller dựa trên `ExecutionException.getCause() instanceof InterruptedException` nếu caller chưa bị ngắt.

**“Catch `ExecutionException` là đủ cho `get`.”** Còn có `InterruptedException`; `get(timeout)` có `TimeoutException`; hủy dẫn tới `CancellationException`. Tài liệu và code phải phản ánh đủ đường lỗi mà caller cần xử lý.

## 17. Bài tập và câu hỏi tự kiểm tra

**Bài 1.** Một tác vụ xử lý file có thể mất 10 giây. API HTTP đợi `future.get(2, SECONDS)` rồi nhận `TimeoutException`. Có nên trả về “xử lý thất bại” và gửi lại task ngay?

**Gợi ý đáp án:** Không được kết luận task đã thất bại. Nên có mã công việc/trạng thái pending, xác định chính sách hủy hoặc chờ tiếp, và kiểm soát idempotency trước khi retry.

**Bài 2.** Worker gọi `queue.take()`, bị ngắt và truyền `InterruptedException` ra khỏi `Callable`. Caller gọi `get()` không bị interrupt. Caller bắt exception nào?

**Đáp án:** `ExecutionException`, với `getCause() instanceof InterruptedException`. `InterruptedException` là lỗi xảy ra trong worker, không phải exception trực tiếp của thao tác chờ ở caller.

**Bài 3.** Trong một lần chờ khác, caller đang gọi `get()` thì thread khác gọi `caller.interrupt()`. `Future` của worker có tự động canceled không?

**Đáp án:** Không. `get` của caller có thể ném `InterruptedException`, nhưng Future vẫn có thể chạy và hoàn thành; chỉ cancel khi chủ sở hữu thực hiện chính sách hủy phù hợp.

**Bài 4.** `CompletableFuture.failedFuture(new IllegalStateException("bad"))` được quan sát bằng `join()` và `get()`. Khác biệt?

**Đáp án:** `join` thường ném `CompletionException` chứa cause `IllegalStateException`, còn `get` ném checked `ExecutionException` chứa cause tương ứng. Trạng thái thất bại nền của stage là như nhau.

**Bài 5.** Caller `A` và `B` cùng quan sát một `CompletableFuture` shared. `A` gọi `orTimeout(...)` với deadline ngắn. Điều gì có thể ảnh hưởng tới `B`?

**Đáp án:** `orTimeout` tác động tới chính `CompletableFuture`; nếu deadline thắng, future hoàn thành exceptional cho mọi người quan sát, kể cả `B`. Nếu chỉ muốn giới hạn thời gian chờ riêng của `A`, không nên tùy tiện sửa shared future theo cách này.

## 18. Nguyên tắc ghi nhớ

Hãy phân loại exception theo **chủ thể chịu tác động** trước khi quyết định hành vi:

- **`ExecutionException` + cause:** tác vụ đã hoàn thành thất bại; đọc cause để xử lý lỗi từ worker.
- **`InterruptedException` ném trực tiếp bởi `get()`:** luồng caller bị ngắt khi chờ; truyền tiếp hoặc phục hồi interrupt, không tự kết luận task thất bại.
- **`TimeoutException` trực tiếp từ `get(timeout)`:** thời gian chờ của caller đã hết; task có thể vẫn tiếp tục.
- **`CancellationException`:** kết quả đã bị hủy theo trạng thái Future; việc dừng thực thi nền phụ thuộc API và cooperation.
- **`CompletionException` trong `CompletableFuture.join()`:** một cách bao lỗi khi quan sát trạng thái exceptional của stage; đọc cause thay vì nhầm với lỗi của chính luồng chờ.

Ranh giới rõ ràng giúp caller phản ứng chính xác với lỗi thật sự của task, interruption của chính mình, deadline đã hết hoặc cancellation. Nhờ vậy, ứng dụng có thể giữ trạng thái nhất quán, tránh retry trùng và bảo toàn thông tin nguyên nhân để xử lý, giám sát và chẩn đoán.