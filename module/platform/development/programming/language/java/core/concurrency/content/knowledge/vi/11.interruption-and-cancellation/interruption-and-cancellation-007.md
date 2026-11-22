# Future.cancel(true) và các giới hạn thực tế trong Java Concurrency

## 1. Mục tiêu và ý nghĩa của hủy tác vụ

Trong ứng dụng đa luồng, đôi lúc một công việc không còn cần thiết: người gọi đã hết hạn chờ, yêu cầu bị đóng, worker phải nhường tài nguyên, hoặc ứng dụng đang shutdown. Với một tác vụ đã gửi vào `ExecutorService`, đối tượng `Future<?>` giúp người gọi truy xuất kết quả hoặc **yêu cầu hủy** thông qua `cancel(boolean mayInterruptIfRunning)`.

Lời gọi thường thấy:

~~~java
boolean accepted = future.cancel(true);
~~~

Có một điểm cực kỳ quan trọng:

> **`Future.cancel(true)` báo yêu cầu hủy được chấp nhận và, nếu phù hợp với implementation, cố ngắt thread đang chạy; nó không bảo đảm business logic đã dừng tại thời điểm `cancel` trả về, không tự rollback side effect và không bắt buộc mọi API I/O thoát ngay.**

Sau bài, bạn sẽ biết:
- Đọc đúng ý nghĩa `cancel(true)`, `cancel(false)`, giá trị trả về, `isCancelled()`, `isDone()`, `get()`.
- Phân biệt **trạng thái của Future** với **vòng đời thực của mã trong Callable/Runnable**.
- Viết task **hợp tác với interruption** và quản lý cleanup trong `finally`.
- Hiểu tại sao task bỏ qua interrupt có thể tiếp tục làm việc **sau khi Future đã cancelled**.
- Phân biệt `Future.get(timeout, unit)` chỉ hết hạn chờ với hành động **cancel task**.
- Hủy tác vụ **trước khi bắt đầu**, trong khi đang chạy và sau khi đã hoàn thành; xử lý các race ở ranh giới.
- Tránh kỳ vọng sai về blocking I/O, synchronized/locks, CPU-bound loops, `CompletableFuture.cancel(true)` và shutdown của executor.
- Thiết kế timeout, cancellation, idempotency, resource cleanup và kiểm chứng bằng ví dụ **Java 17+**.

**Phạm vi:** Java SE, `java.util.concurrent` và concurrency của Java nói chung. Không dùng các cơ chế riêng của Spring vì phần liên quan Spring đã có chương riêng.

## 2. Future đại diện cho kết quả, không phải công tắc dừng cưỡng bức

`Future<V>` đại diện cho **kết quả cuối của một phép tính bất đồng bộ**, cung cấp:
- `get()`: đợi và lấy kết quả nếu task hoàn thành bình thường; có thể ném `ExecutionException` nếu task thất bại.
- `get(timeout, unit)`: đợi **tối đa một khoảng thời gian** rồi ném `TimeoutException` nếu chưa có kết quả.
- `cancel(boolean)`: yêu cầu hủy theo hợp đồng của implementation.
- `isCancelled()`: task đã được đánh dấu hủy **trước khi hoàn thành bình thường** hay chưa.
- `isDone()`: phép tính đã **hoàn thành, thất bại hoặc được đánh dấu hủy** hay chưa.

Các trạng thái thường được quan sát:

~~~text
         submit
            |
            v
       Chưa bắt đầu --------------+
            |                    |
            v                    |
         Đang chạy                |
          /   \                   |
         /     \                  |
 Hoàn tất     Exception           |
         \     /                  |
          \   /                   |
           v v                    |
        Done bình thường/         |
        Done do lỗi               |
                                 |
       cancel(...) thành công ---+
                   |
                   v
           Future cancelled
          isDone == true
          isCancelled == true
          get() -> CancellationException

Thread có thể vẫn tiếp tục chạy sau khi Future đã cancelled.
~~~

Đây là sơ đồ **trạng thái quan sát của Future**, không phải sơ đồ đầy đủ của mọi thread/JVM. Một task có thể nhận tín hiệu interrupt rồi cần thêm thời gian cleanup. Một task **bỏ qua** interrupt còn có thể chạy tiếp tới khi tự kết thúc, dù kết quả của nó không còn được Future công bố.

**`isDone() == true` không đồng nghĩa “thread đã dừng”**. Nó chỉ cho biết phép tính đại diện bởi Future đã ở trạng thái hoàn tất theo contract, và **cancellation là một kiểu hoàn tất**.

## 3. cancel(true) và cancel(false) chính xác có nghĩa gì?

Signature của interface:

~~~java
boolean cancel(boolean mayInterruptIfRunning);
~~~

| Tình huống | `cancel(true)` | `cancel(false)` |
| --- | --- | --- |
| Task còn nằm trong queue, chưa chạy | Nếu hủy thành công, task không được thực hiện | Tương tự: không thực hiện task đã hủy |
| Task đã bắt đầu nhưng chưa hoàn tất | Yêu cầu hủy; implementation như `FutureTask` có thể/cố interrupt worker | Yêu cầu hủy **không yêu cầu interrupt** worker đang chạy |
| Task đã hoàn tất trước lời gọi | Thường trả `false`; kết quả đã cố định | Tương tự |
| Hủy đã được chấp nhận | `isCancelled()==true` và `isDone()==true` | Tương tự |
| Task vẫn có thể thực thi code sau cancel? | **Có**, nếu task không hợp tác hoặc chưa quan sát interrupt | **Có** nếu task đang chạy, vì không yêu cầu interrupt |
| `get()` sau khi Future bị hủy | Ném `CancellationException` | Tương tự |

Lưu ý `cancel(true)` **không thay thế `Thread.stop()`**: đây không phải lệnh giết thread không điều kiện. Nó chỉ thiết lập cơ chế hủy của Future và yêu cầu ngắt khi implementation hỗ trợ; code tác vụ cần **hợp tác** để dừng đúng. Không nên dùng `Thread.stop()` vì khả năng để object ở trạng thái không nhất quán.

### Giá trị trả về true/false

- `true`: lời gọi đã **thành công trong việc chuyển Future sang trạng thái cancelled** theo hợp đồng; **không chứng minh worker đã kết thúc**.
- `false`: không thể thực hiện hủy, ví dụ phép tính đã hoàn thành hoặc đã ở trạng thái không thể hủy theo implementation. Không dùng `false` đơn lẻ để kết luận “task đã hoàn thành thành công”: nó có thể thất bại hoặc bị hủy trước đó.
- `cancel(true)` có thể cạnh tranh với việc task tự kết thúc. Nếu một trong hai thắng trước, kết quả của lời gọi hủy tùy thời điểm; code phải chấp nhận cả hai đường đi.
- Nếu trạng thái là cancelled, các lần `get()` sau đó ném `CancellationException`, không trả kết quả do task vừa tính được, ngay cả khi phần mã trong worker vẫn tiếp tục chạy.

Với `ExecutorService.submit(...)` ở các executor thông dụng của Java, Future thường được triển khai dựa trên `FutureTask` và hỗ trợ việc interrupt worker khi `cancel(true)` thành công lúc task đang chạy. Nhưng **Future là một interface**; các implementation khác có thể có chính sách hủy khác, nên phải đọc contract cụ thể.

### CancellationException không phải InterruptedException

`Future.get()` có thể ném các exception khác nhau:
- `CancellationException` (*unchecked*): **Future đang ở trạng thái cancelled**.
- `InterruptedException` (*checked*): **thread đang gọi get** bị interrupt trong lúc chờ, không có nghĩa tác vụ chắc chắn bị hủy.
- `ExecutionException` (*checked*): computation hoàn thành bằng lỗi được lưu trong Future.
- `TimeoutException` (*checked*, với timed get): caller chưa nhận được kết quả trong khoảng chờ; task **có thể vẫn chạy và Future chưa bị hủy**.

Đây là bốn tình huống khác nhau. Không bắt `TimeoutException` rồi báo “task cancelled” nếu chưa thực sự gọi `cancel` và kiểm tra kết quả.

## 4. Interruption hoạt động như một yêu cầu hợp tác

Mỗi Java `Thread` có **interrupt status**. `Thread.interrupt()` thiết lập trạng thái đó và có tác động tới một số thao tác chờ; các API khác nhau phản ứng khác nhau.

Một task CPU-bound nên tự kiểm tra status:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doSmallUnitOfWork();
}
// Ra khỏi vòng lặp và cleanup.
~~~

Snippet giả định `doSmallUnitOfWork()` đã khai báo, không phải chương trình độc lập. Phải chia công việc thành đơn vị đủ nhỏ để kiểm tra status; nếu một vòng xử lý kéo dài hàng phút mà không kiểm tra, cancellation sẽ chậm.

Một task đang dùng API interruptible như `Thread.sleep()`, `Object.wait()`, `BlockingQueue.take()`, `CountDownLatch.await()` hoặc `Condition.await()` có thể nhận `InterruptedException`. Theo hợp đồng của các thao tác thường gặp này, khi exception được ném, **interrupt status bị xóa**.

Ví dụ hàm `Callable` có thể để exception truyền lên:

~~~java
Callable<String> task = () -> {
    while (true) {
        Thread.sleep(1_000);
        doSmallUnitOfWork();
    }
};
~~~

Đây là snippet, cần import `java.util.concurrent.Callable` và khai báo method giả định. Khi `sleep` bị interrupt, lambda có thể thoát bằng `InterruptedException`; Future đã cancelled vẫn không chuyển trở lại trạng thái hoàn thành bình thường.

Nếu phải bắt `InterruptedException` nhưng tầng hiện tại không thể truyền tiếp, một mẫu xử lý:

~~~java
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Khôi phục trạng thái.
    return;
}
~~~

Đây là đoạn minh họa trong method `void`. Quan trọng nhất là **thoát hoặc xử lý chính sách hủy rõ ràng**, không nuốt exception rồi lại bắt đầu chờ vô hạn.

### Hai cách kiểm tra interrupt status

- `Thread.currentThread().isInterrupted()`: kiểm tra **không xóa** status.
- `Thread.interrupted()`: phương thức static kiểm tra **và xóa** status của **thread hiện tại**.

Nếu vô tình dùng `Thread.interrupted()` để kiểm tra nhiều lần mà không ghi nhớ kết quả, có thể xóa mất yêu cầu hủy. Dùng `isInterrupted()` khi chỉ muốn biết có nên dừng hay không.

## 5. Ví dụ Java 17: task hợp tác với cancel(true)

Chương trình tạo một task có vòng `Thread.sleep()` interruptible. Main đợi task bắt đầu, gọi `cancel(true)`, đợi worker thực sự rời tác vụ qua latch, rồi kiểm tra `Future`. Không dựa vào ngủ ngẫu nhiên để đo timing.

Tạo file **`CooperativeCancellationDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CooperativeCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            Callable<String> work = () -> {
                started.countDown();
                try {
                    while (true) {
                        Thread.sleep(60_000);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "stopped-by-interrupt";
                } finally {
                    exited.countDown();
                }
            };

            Future<String> future = pool.submit(work);
            started.await();

            boolean accepted = future.cancel(true);
            exited.await(); // Khác với Future.isDone(): chờ task thực sự thoát.

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("isCancelled=" + future.isCancelled());
            System.out.println("isDone=" + future.isDone());
            System.out.println("workerExited=" + (exited.getCount() == 0));

            try {
                System.out.println("result=" + future.get());
            } catch (CancellationException e) {
                System.out.println("get=CancellationException");
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                System.out.println("executor-not-terminated");
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac CooperativeCancellationDemo.java
java CooperativeCancellationDemo
~~~

Stdout trên đường thực thi bình thường, khi worker hợp tác và executor kết thúc:

~~~text
cancelAccepted=true
isCancelled=true
isDone=true
workerExited=true
get=CancellationException
~~~

**Phân tích:**
1. `started.await()` bảo đảm worker đã bước vào callable; task chưa tự hoàn tất vì nó liên tục chờ trong `sleep`.
2. `cancel(true)` trên Future do executor trả về đánh dấu hủy và yêu cầu interrupt.
3. `Thread.sleep` quan sát interrupt bằng `InterruptedException`, worker đi tới `finally` và hạ latch `exited`.
4. `exited.await()` kiểm tra worker **đã thực sự rời callable**, điều mà `future.isDone()` sau hủy **không tự chứng minh**.
5. Dù callable có nhánh `return "stopped-by-interrupt"`, Future đã cancelled nên `future.get()` ném `CancellationException` chứ **không** trả chuỗi đó.
6. `shutdownNow` ở `finally` giúp tránh giữ worker nếu có lỗi giữa chừng; đây vẫn là cơ chế hủy best-effort, không phải bảo đảm mọi tác vụ bất hợp tác dừng.

Lưu ý demo dùng `exited.await()` không timeout để minh họa tín hiệu xác nhận worker kết thúc. Trong code production nên dùng **deadline** cho thời gian chờ shutdown và có chiến lược xử lý khi task không phản hồi interruption.

## 6. Vì sao Future cancelled không có nghĩa worker đã dừng?

Đây là giới hạn quan trọng nhất của `cancel(true)`. Một task có thể:
- Không gọi API interruptible và không kiểm tra `isInterrupted()`.
- Bắt `InterruptedException` rồi bỏ qua, tiếp tục công việc.
- Đang ở một thao tác native hoặc blocking I/O không đáp ứng interruption ngay.
- Đang giữ lock hoặc thực hiện một callback dài trước khi tới điểm kiểm tra.
- Đang trong `finally` cleanup, có thể còn thực hiện side effect sau thời điểm Future được đánh dấu cancelled.

### Ví dụ Java 17: task cố tình bỏ qua interrupt

Chương trình sau **cố ý thiết kế không hợp tác**: worker chờ một latch, nhưng nếu bị interrupt, nó bắt exception và **tiếp tục chờ**. Main hủy Future rồi mới cho phép worker hoàn tất. Demo chứng minh có thể có code chạy sau `cancel(true)`, không tạo một vòng CPU nóng.

Tạo file **`UncooperativeCancellationDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class UncooperativeCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean sideEffectAfterCancel = new AtomicBoolean(false);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                try {
                    while (true) {
                        try {
                            release.await();
                            break;
                        } catch (InterruptedException ignored) {
                            // CỐ Ý SAI: bỏ qua cancellation để minh họa.
                        }
                    }
                    sideEffectAfterCancel.set(true);
                    return "completed-despite-cancel";
                } finally {
                    exited.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureDone=" + future.isDone());
            System.out.println("workerExitedBeforeRelease="
                    + (exited.getCount() == 0));

            release.countDown();
            exited.await();

            System.out.println("sideEffectAfterCancel="
                    + sideEffectAfterCancel.get());
            System.out.println("futureStillCancelled=" + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get=CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac UncooperativeCancellationDemo.java
java UncooperativeCancellationDemo
~~~

Stdout trong đường thực thi bình thường:

~~~text
cancelAccepted=true
futureDone=true
workerExitedBeforeRelease=false
sideEffectAfterCancel=true
futureStillCancelled=true
get=CancellationException
~~~

**Điều gì xảy ra?**
- `cancel(true)` có thể interrupt worker đang đợi `release.await()`; nhưng code **cố tình nuốt** `InterruptedException` và chờ lại.
- Ngay sau cancel, `Future.isDone()==true`, trong khi `exited` chưa được count down: task chưa kết thúc.
- Main cho `release` về 0. Worker tiếp tục ghi một side effect minh họa, kết thúc callable và hạ `exited`.
- Future vẫn cancelled; `get()` ném `CancellationException` dù logic worker đã return bình thường.

Đây là ví dụ **anti-pattern**, không phải khuyến nghị bỏ qua interrupt. Trong thực tế, side effect có thể là ghi DB, gửi HTTP, cập nhật cache hoặc làm thay đổi dữ liệu nghiệp vụ mà caller đã tưởng không còn xảy ra.

**Hệ quả thiết kế:** nếu tính đúng yêu cầu “sau khi hủy thì tuyệt đối không ghi kết quả”, chỉ `Future.cancel(true)` không đủ. Cần phối hợp bằng state machine, token/generation, idempotency, quyền commit hoặc giao thức xử lý ở tài nguyên cuối. Worker cần kiểm tra cancellation **trước điểm commit**; nếu commit thuộc hệ thống bên ngoài, phải thiết kế tương ứng tại hệ thống đó.

## 7. cancel(false): hủy kết quả mà không yêu cầu ngắt worker

`future.cancel(false)` không phải “hủy nhẹ hơn nhưng chắc chắn dừng”:
- Nếu task **chưa chạy** và hủy thành công, worker không thực hiện công việc đó.
- Nếu task **đã chạy**, `FutureTask` có thể chuyển Future sang cancelled mà **không interrupt** worker. Task đang chạy có thể tiếp tục tính toán hoặc làm I/O cho đến khi tự dừng.
- Caller thấy `get()` ném `CancellationException`, nhưng không thể suy rằng hoạt động phía trong đã dừng.
- `cancel(false)` có thể phù hợp khi không muốn gửi interrupt tới một task đã chạy nhưng không còn cần kết quả; điều này **không giải phóng ngay** slot trong thread pool.

Khi task được triển khai bằng `FutureTask`, quyết định cancel khác với tín hiệu interrupt: một việc là thay **state của Future**, một việc là cố tác động vào **thread thực thi**. Trong chương trình có nhiều loại Future, luôn xem Javadoc của implementation thay vì áp đặt chi tiết `FutureTask` cho tất cả.

## 8. Hủy trước khi task bắt đầu: tác vụ không được thực thi

Khi dùng một executor có một worker, ta có thể cố tình giữ worker bận bằng tác vụ đầu tiên và đưa tác vụ thứ hai vào queue. Nếu hủy tác vụ thứ hai **trước khi nó được chạy**, runnable của nó không được gọi.

Tạo file **`CancelQueuedTaskDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelQueuedTaskDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch blockerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean queuedWorkRan = new AtomicBoolean(false);

        try {
            Future<?> blocker = pool.submit(() -> {
                blockerStarted.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            blockerStarted.await();

            Future<?> queued = pool.submit(() ->
                    queuedWorkRan.set(true));

            boolean accepted = queued.cancel(true);
            release.countDown();
            blocker.get();

            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("queuedWasExecuted=" + queuedWorkRan.get());
            System.out.println("queuedCancelled=" + queued.isCancelled());

            try {
                queued.get();
            } catch (CancellationException e) {
                System.out.println("queuedGet=CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac CancelQueuedTaskDemo.java
java CancelQueuedTaskDemo
~~~

Stdout khi executor hoạt động bình thường:

~~~text
cancelAccepted=true
queuedWasExecuted=false
queuedCancelled=true
queuedGet=CancellationException
~~~

**Lý do kết quả không phụ thuộc thứ tự chạy:**
1. `newSingleThreadExecutor` chỉ thực hiện một task tại một thời điểm.
2. Task `blocker` đã bắt đầu và đang chờ `release`, nên task thứ hai chỉ có thể xếp hàng.
3. `queued.cancel(true)` được gọi trước khi mở `release`, do đó queued task chưa thể chạy.
4. Khi worker xử lý Future đã canceled, nội dung runnable không được thực thi; `queuedWorkRan` vẫn false.
5. `queued.get()` ném `CancellationException`.

**Giới hạn:** việc hủy một Future đang đợi trong queue không nhất thiết làm nó **biến mất ngay lập tức khỏi mọi cấu trúc queue nội bộ**. Cơ chế loại task hủy khỏi work queue và quản lý memory có thể phụ thuộc executor/implementation. Không suy “cancel thành công” đồng nghĩa kích thước queue được giảm ngay.

## 9. Future.get(timeout) không tự hủy task

`Future.get(timeout, TimeUnit.MILLISECONDS)` chỉ giới hạn **thời gian thread gọi get chờ kết quả**. Khi ném `TimeoutException`:
- Future **có thể vẫn running** hoặc đang đợi trong queue.
- `isCancelled()` thường vẫn false, trừ khi có bên khác đã hủy.
- Task **không tự nhận interrupt** chỉ vì caller hết hạn `get`.
- Caller cần quyết định có gọi `future.cancel(true)` hay không, hoặc để task tiếp tục làm việc.

### Ví dụ Java 17: timeout chỉ thuộc về caller

Tạo file **`TimedGetDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimedGetDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> future = pool.submit(() -> {
                started.countDown();
                release.await();
                return 42;
            });

            started.await();

            try {
                future.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("get=TimeoutException");
            }

            System.out.println("cancelled=" + future.isCancelled());
            System.out.println("doneBeforeRelease=" + future.isDone());

            release.countDown();
            System.out.println("resultAfterRelease=" + future.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac TimedGetDemo.java
java TimedGetDemo
~~~

Stdout khi main không bị interrupt và task hoạt động bình thường:

~~~text
get=TimeoutException
cancelled=false
doneBeforeRelease=false
resultAfterRelease=42
~~~

Task bị chặn tại `release.await()` trong khi main gọi `get(20ms)`. Hết 20ms, main nhận `TimeoutException` nhưng Future chưa canceled; sau khi `release.countDown()`, task hoàn tất và `get()` trả 42.

**Bẫy thường gặp:** caller timeout rồi retry một nghiệp vụ khác trong khi task cũ vẫn chạy. Hai tác vụ có thể cùng gây side effect (đặt hàng hai lần, ghi dữ liệu hai lần...). Giới hạn thời gian chờ kết quả **không thay thế** deadline của chính thao tác từ xa, không thay thế cancellation, và không thay thế idempotency.

### Mẫu deadline và cancel khi timeout

~~~java
try {
    return future.get(timeout, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    boolean cancelAccepted = future.cancel(true);
    // Log/cập nhật trạng thái theo yêu cầu.
    // cancelAccepted không bảo đảm worker đã thực sự dừng.
    throw e;
}
~~~

Đây là snippet **bên trong method có future, timeout và kiểu trả về phù hợp**; cần import `TimeoutException` và `TimeUnit`. Nếu timeout của caller là một phần của deadline đầu-cuối, tổng thời gian ở queue, I/O, retry và cleanup đều phải được tính; chỉ thêm `get(timeout)` chưa tạo deadline cho toàn bộ business operation.

## 10. Một hạn chế dễ nhầm: CompletableFuture.cancel(true)

`CompletableFuture<T>` triển khai `Future<T>` nhưng có chính sách cancel riêng. Theo Javadoc Java 17, **tham số `mayInterruptIfRunning` không có tác dụng trong implementation của `CompletableFuture` vì interruption không được sử dụng để điều khiển quá trình xử lý**.

Vì vậy, nếu `CompletableFuture.supplyAsync(...)` đã chạy:
- `cf.cancel(true)` có thể chuyển CompletableFuture sang trạng thái cancelled.
- Caller của `cf.get()`/`cf.join()` quan sát cancellation theo contract của CompletableFuture.
- **Không được suy** từ `cancel(true)` rằng thread đang thực thi `supplyAsync` đã bị interrupt.
- Worker có thể chạy tiếp, làm side effect hoặc hoàn tất calculation, nhưng không làm CompletableFuture đã canceled công bố lại kết quả bình thường.
- Các dependent stages có thể hoàn thành exceptional/cancellation tùy đồ thị phụ thuộc; không có bảo đảm ngắt thread tương ứng.

### Ví dụ Java 17: cancel CompletableFuture không interrupt worker

Tạo file **`CompletableFutureCancelDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableFutureCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        try {
            CompletableFuture<String> cf =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "work-finished";
                        } catch (InterruptedException e) {
                            sawInterrupt.set(true);
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            exited.countDown();
                        }
                    }, pool);

            started.await();
            boolean accepted = cf.cancel(true);

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + cf.isCancelled());
            System.out.println("workerExitedBeforeRelease="
                    + (exited.getCount() == 0));

            release.countDown();
            exited.await();

            System.out.println("interruptObserved=" + sawInterrupt.get());

            try {
                cf.join();
            } catch (CancellationException e) {
                System.out.println("join=CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac CompletableFutureCancelDemo.java
java CompletableFutureCancelDemo
~~~

Stdout trên đường thực thi bình thường với worker không nhận interruption bên ngoài:

~~~text
cancelAccepted=true
futureCancelled=true
workerExitedBeforeRelease=false
interruptObserved=false
join=CancellationException
~~~

Đây là khác biệt rất đáng nhớ giữa **Future do executor trả về** và **CompletableFuture của một pipeline bất đồng bộ**. Không mặc định tất cả implementation của `Future.cancel(true)` đều interrupt task runner giống nhau. Nếu cần một kênh hủy có interrupt cụ thể, phải quản lý task handle/`FutureTask` tương ứng, timeout và cancellation token ở abstraction của bạn.

## 11. Những thao tác thường không phản hồi interruption như mong đợi

### 11.1. CPU-bound loop không kiểm tra cờ

Ví dụ sai:

~~~java
while (true) {
    performCpuWork(); // Không kiểm tra interrupt hoặc cancellation token.
}
~~~

`cancel(true)` có thể đặt interrupt status nhưng **không tự chèn một nhánh break** vào vòng lặp. Task có thể tiếp tục mãi. Tách CPU work thành chunk nhỏ và kiểm tra `Thread.currentThread().isInterrupted()` tại các checkpoint.

### 11.2. Chờ monitor lock bằng synchronized

Một thread đang cố **vào `synchronized(lock)`** có thể ở `Thread.State.BLOCKED`. Việc interrupt thông thường **không khiến thao tác tranh monitor của `synchronized` ném `InterruptedException` hoặc tự bỏ cuộc**. Khi cuối cùng lấy được monitor, code phải kiểm tra interrupt/cancellation nếu muốn dừng.

Nếu cần chờ lock với khả năng interrupt, cân nhắc `ReentrantLock.lockInterruptibly()` hoặc `tryLock(timeout, unit)`, bảo đảm `unlock()` trong `finally`. Các API có semantics riêng; đừng đổi lock chỉ vì hy vọng cancel thành công mà không xét giao thức nghiệp vụ.

### 11.3. Blocking I/O

Không có bảo đảm chung rằng `Thread.interrupt()` ngắt tức thì **mọi** `InputStream.read()`, socket/file I/O hay native blocking call trên mọi JDK. Ví dụ:
- Với một số `InterruptibleChannel`, interruption khi block có thể làm channel đóng và ném `ClosedByInterruptException`.
- Một số socket/stream truyền thống phụ thuộc timeout, `close()` hoặc triển khai I/O cụ thể; `Socket#setSoTimeout` đặt thời gian tối đa chờ đọc với những API tương ứng.
- Một lời gọi từ thư viện/driver có thể xử lý interruption theo chính hợp đồng của nó, không theo ý caller.

Nếu task đang chờ một dependency bên ngoài, **timeout của đúng API I/O** và **cleanup/đóng resource** thường quan trọng không kém interrupt. Không mặc định đóng một resource từ thread khác lúc nào cũng an toàn: phải theo contract, lifecycle và ownership của tài nguyên ấy.

### 11.4. Callback hoặc cleanup dài

Ngay cả task hợp tác có thể vẫn chạy `finally` sau khi bị interrupt:
- Đóng stream, hoàn trả connection, giải phóng lock.
- Ghi metric hoặc trạng thái kết thúc.
- Hoàn tất một operation không thể bỏ dở mà không vi phạm invariant.

Do đó, khoảng thời gian từ **cancel accepted** đến **resource fully released** có thể không bằng 0. Với hệ thống cần shutdown đúng, nên theo dõi kết thúc bằng latch/termination của executor hoặc một tín hiệu cleanup riêng, không chỉ `Future.isDone()` của task đã hủy.

## 12. Hủy task và hủy executor là hai cấp độ khác nhau

### shutdown()

`ExecutorService.shutdown()` bắt đầu đóng nhận task mới, nhưng **các task đã submit được phép hoàn thành** theo hợp đồng. `shutdown()` không đồng nghĩa gửi interrupt để hủy mọi task đang chạy.

### shutdownNow()

`ExecutorService.shutdownNow()` **cố gắng** dừng task đang hoạt động và ngừng xử lý task đang chờ. Implementation thông dụng dùng `Thread.interrupt()` để yêu cầu task đang chạy dừng, nhưng đó là **best-effort**; nếu task không phản hồi interruption, nó có thể tiếp tục. Phương thức trả danh sách các task chưa bắt đầu được thực thi; cách thể hiện task/Future phải xét đúng implementation.

### awaitTermination()

`awaitTermination(timeout, unit)` đợi executor đạt trạng thái terminated hoặc hết timeout (hoặc caller bị interrupt). Đây là **cách quan sát kết thúc executor** sau `shutdown()/shutdownNow()`, không tự động yêu cầu dừng task nếu bạn chưa khởi động shutdown.

Mẫu thường dùng:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            // Báo task không hợp tác hoặc cleanup kéo dài.
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là snippet, giả định `pool` là `ExecutorService` đã được khởi tạo. Các timeout minh họa không thay thế SLO thực; với một service phức tạp có thể cần deadline tổng, kiểm soát task chặn I/O và theo dõi những tài nguyên không được giải phóng.

**Đừng mặc định gọi `cancel(true)` trên từng Future là đủ để thread pool shutdown.** Một task bỏ qua interrupt có thể khiến executor không terminate và giữ cả tiến trình sống nếu sử dụng platform threads non-daemon.

## 13. Bảo vệ business invariant và side effect khi cancellation

Cancellation có thể đến tại nhiều điểm:

~~~text
queued -> started -> validated -> remote call -> commit -> cleanup -> done
   |         |          |            |          |         |
   +---- cancel yêu cầu ở bất kỳ thời điểm nào -------+
~~~

Những rủi ro:
- **Đã commit trước khi cancel đến:** caller có thể thấy Future cancelled nhưng side effect đã xảy ra; không thể rollback bằng interrupt.
- **Đang gọi remote API khi cancel đến:** lệnh từ xa có thể đã hoàn tất dù caller không nhận response; retry có thể tạo duplicate.
- **Đang giữ lock khi cancel đến:** task phải đảm bảo `finally` nhả lock; interruption không tự rollback trạng thái.
- **Một phần state đã cập nhật:** task không được bỏ ngang để lại invariant sai, ví dụ giảm tồn kho mà không ghi đơn hàng tương ứng.
- **Task đã bị canceled nhưng vẫn chạy:** nó có thể publish kết quả muộn, ghi đè trạng thái của tác vụ thay thế.

Các thiết kế phòng vệ:
1. **Idempotency key:** cùng một yêu cầu nghiệp vụ chỉ có một hiệu ứng được chấp nhận tại hệ thống thực hiện side effect.
2. **Generation/version/token:** chỉ lần chạy đang hợp lệ được quyền publish/commit kết quả; task cũ bị hủy không được ghi đè phiên bản mới.
3. **Trạng thái rõ ràng:** `NEW -> RUNNING -> COMMITTING -> SUCCEEDED/FAILED/CANCELLED` theo giao thức có atomic transition ở phạm vi cần thiết.
4. **Transaction/compensation:** với cập nhật nhiều tài nguyên, định nghĩa rollback hoặc bù trừ nếu việc ngắt giữa chừng gây state dở dang.
5. **Cancellation checkpoints:** kiểm tra interrupt/token trước bước nặng và ngay trước commit khi có thể; vẫn cần giao thức nguyên tử để tránh race giữa “đã kiểm tra” và “commit”.
6. **Thời gian chờ hữu hạn:** timeout cho I/O, lock wait và cleanup; đừng dựa duy nhất vào timed get.
7. **Cleanup đúng ownership:** try-with-resources và `finally`, trả connection, nhả semaphore, unlock; không để task hủy giữ tài nguyên vô hạn.

### Điều quan trọng về “kiểm tra trước commit”

Đoạn sau **chưa đủ** nếu phải bảo đảm tuyệt đối không có commit sau cancellation:

~~~java
if (!Thread.currentThread().isInterrupted()) {
    commitToExternalSystem();
}
~~~

Một cancel có thể đến **sau lần kiểm tra nhưng trước commit**. Nếu contract nghiệp vụ cần loại trừ side effect từ task bị hủy, phải có một giao thức xác nhận quyền commit tại hệ thống đích hoặc một atomic state transition thống nhất; đơn thuần xem interrupt flag không đủ.

## 14. Future.cancel(true) và các mô hình Future khác

### FutureTask

`FutureTask<V>` là implementation có thể chạy một `Callable`/`Runnable`. Khi hủy một task đang chạy bằng `cancel(true)` và thành công, nó cố interrupt thread đang chạy. Dù task tiếp tục chạy, trạng thái kết quả của FutureTask vẫn là cancelled. Trong các executor phổ biến, `submit` tạo task theo mẫu này hoặc tương đương.

### ScheduledFuture

`ScheduledExecutorService.schedule(...)` và các phương thức periodic trả `ScheduledFuture`; hủy có thể ngăn các lần thực thi được lập lịch tiếp theo. Với một lần thực thi **đang chạy**, mayInterruptIfRunning vẫn chỉ mang semantics tương ứng của implementation. Với periodic task, cancellation không làm những side effect trước đó biến mất. Chính sách loại bỏ task đã hủy khỏi delay queue cũng phụ thuộc executor (ví dụ `ScheduledThreadPoolExecutor#setRemoveOnCancelPolicy`), không mặc định hủy làm memory queue giảm tức khắc.

### CompletableFuture

`CompletableFuture.cancel(true)` **không sử dụng interrupt để điều khiển task** trong implementation Java 17. Nó là một cách **hoàn thành exceptional** của future và ảnh hưởng tới các stage phụ thuộc, nhưng không phải tương đương `FutureTask.cancel(true)`. Muốn thực sự yêu cầu task dừng, cần một kênh cancellation được chính công việc hỗ trợ.

### Thread và ForkJoinTask

Nếu quản lý `Thread` trực tiếp, `thread.interrupt()` chỉ là yêu cầu hủy; bạn không tự có một Future kết quả. Với `ForkJoinTask`, semantics cancellation/interrupt cũng không nên suy từ FutureTask; hãy đọc tài liệu của implementation cụ thể. **Không xây abstraction chung “mọi Future đều interrupt worker khi cancel(true)”**.

## 15. Những lỗi thường gặp

| Nhầm lẫn hoặc lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `cancel(true) == true` được hiểu là thread đã dừng | Side effect/cleanup vẫn có thể chạy | Theo dõi task exited hoặc giao thức hoàn tất riêng |
| `isDone() == true` được hiểu là công việc thành công | Cancel và exception cũng là done | Kiểm tra `isCancelled()`, xử lý `get()` đúng |
| `get()` sau cancel được kỳ vọng trả kết quả task đã tính | Thực tế ném `CancellationException` | Tách trạng thái Future và hành vi worker |
| Bắt `InterruptedException` rồi tiếp tục vô hạn | Task không hợp tác với cancellation | Propagate hoặc restore status và thoát |
| Dùng `Thread.interrupted()` để kiểm tra nhưng bỏ qua giá trị | Xóa interrupt status | Dùng `isInterrupted()` khi muốn đọc không xóa |
| CPU loop không kiểm tra cờ | Không phản hồi cancel | Thêm checkpoint và công việc theo chunk |
| Chờ `synchronized` bị cạnh tranh và mong interrupt giải phóng ngay | Không có hợp đồng như lockInterruptibly | Dùng lock API phù hợp hoặc xem xét cấu trúc khóa |
| Giả định mọi I/O dừng vì interrupt | Task tiếp tục block | Timeout/close theo API I/O |
| `get(timeout)` được hiểu là task đã bị cancel | Task vẫn chạy, dễ retry trùng | Gọi cancel riêng nếu cần và bảo vệ idempotency |
| `cancel(false)` được hiểu là task sẽ dừng | Task đang chạy có thể tiếp tục | Hiểu semantics “không yêu cầu interrupt” |
| `CompletableFuture.cancel(true)` được hiểu là interrupt worker | Không đúng với Java 17 | Thêm cancellation token/task handle riêng |
| Dùng `shutdownNow()` và tin executor chắc chắn terminated | Noncooperative workers có thể tiếp tục | `awaitTermination` có deadline và cảnh báo |
| Dừng giữa hai lần sửa shared state | Invariant nghiệp vụ sai | Bảo vệ commit/rollback, cleanup trong finally |
| Cancel task cũ rồi lập tức submit task mới mà không có version guard | Kết quả muộn của task cũ ghi đè dữ liệu mới | Generation/version/idempotent commit |
| Không thiết lập timeout cho downstream I/O | Cancel có thể không giải phóng worker | Timeout ở đúng API và giới hạn concurrency |
| Không kiểm tra task đang chạy có được release resource không | Leak connection, semaphore, lock | Try-with-resources, finally, completion metrics |

## 16. Kiểm thử cancellation đáng tin

Một test hợp lý phải đo **hai việc khác nhau**:
1. Trạng thái **Future**: `cancel` trả gì, `isCancelled/isDone` thế nào, `get` ném gì.
2. Trạng thái **thực thi**: callable đã chạy đến đâu, đã thoát chưa, cleanup và side effect cuối có xảy ra không.

Cách kiểm thử:
- **Sử dụng latch/barrier** để buộc task thực sự bắt đầu hoặc thực sự nằm trong queue trước khi cancel; không dùng `Thread.sleep(100)` làm bằng chứng về thứ tự chạy.
- Test hủy **trước khi bắt đầu**, khi đang `sleep/take/wait`, khi làm CPU và khi task không hợp tác.
- Test `cancel(true)` và `cancel(false)` trên implementation thực sự sử dụng.
- Test riêng `CompletableFuture.cancel(true)`: kết quả cancelled không phải bằng chứng interruption.
- Test `get(timeout)`: xác nhận Future vẫn có thể hoàn tất sau khi caller timeout.
- Dùng `CountDownLatch exited` hoặc `awaitTermination` để xác nhận worker/executor đã dừng thực sự; **không dùng Future.isDone() sau cancel như assertion thay thế**.
- Đảm bảo mọi nhánh test đều **release latch trong `finally`** và đóng executor để không khiến test treo.
- Khi side effect quan trọng, dùng fake resource/gateway và xác nhận không bị duplicate hoặc ghi đè sau cancel; đừng chỉ kiểm tra một biến boolean “cancel requested”.
- Kiểm tra interruption bị catch/clear hoặc callback native I/O không hỗ trợ hủy; không suy luận rằng một test sleep thành công nghĩa mọi công việc đều interruptible.
- Theo dõi metric: cancel requests, cancel accepted, worker exits, cleanup duration, pool active count, queued count, timeout và tác vụ vẫn chạy quá deadline.

Nếu đo latency, phân biệt:
- **Cancellation request latency:** thời gian gọi `cancel`.
- **Task stop latency:** từ yêu cầu hủy tới lúc worker không thực thi task nữa.
- **Resource release latency:** tới lúc tất cả connection/lock/permit được trả.
- **Business finality latency:** tới lúc hệ thống biết rõ side effect thành công, thất bại hay cần bù trừ.

Các khoảng này **không nhất thiết giống nhau**.

## 17. Câu hỏi tự kiểm tra

1. `Future.cancel(true)` trả `true` có chứng minh worker đã thoát không? **Không.** Nó chỉ chứng minh Future đã chấp nhận cancellation theo contract.
2. Một Future đã cancelled có thể `isDone() == true` trong khi runnable còn chạy không? **Có.**
3. Sau cancellation thành công, `Future.get()` ném exception gì? **`CancellationException`**.
4. `Future.get(timeout)` ném `TimeoutException` có tự interrupt/cancel task không? **Không.**
5. Nếu một `Callable` bắt `InterruptedException` rồi bỏ qua và tiếp tục chờ, `cancel(true)` có buộc nó dừng không? **Không.**
6. Với `cancel(false)` trên một `FutureTask` đã chạy, task có thể tiếp tục không? **Có, vì không yêu cầu interrupt.**
7. Hủy một task đang xếp hàng trước khi worker nhận nó có thể làm runnable không được chạy không? **Có, nếu cancellation thành công theo executor/Future đó.**
8. `Thread.currentThread().isInterrupted()` và `Thread.interrupted()` khác nhau ở đâu? **Hàm thứ nhất không xóa cờ; hàm static thứ hai xóa cờ của thread hiện tại.**
9. Tại sao một task đang cố vào synchronized có thể không dừng ngay khi bị interrupt? **Chờ monitor qua synchronized không phải thao tác lock interruptible như `lockInterruptibly()`.**
10. Interrupt có bảo đảm đóng mọi socket hoặc làm mọi `InputStream.read()` trở về ngay không? **Không**, semantics phụ thuộc API và implementation.
11. Với Java 17, `CompletableFuture.cancel(true)` có interrupt thread đang xử lý `supplyAsync` không? **Không phải cơ chế của implementation CompletableFuture**; cờ mayInterruptIfRunning không có tác dụng.
12. `shutdownNow()` có bảo đảm mọi task đã dừng không? **Không, chỉ nỗ lực best-effort.**
13. Tại sao Future bị hủy vẫn có thể tạo một bản ghi database? **Worker có thể đã commit trước cancel, đang ở giữa I/O, hoặc tiếp tục chạy sau khi Future đã cancelled.**
14. Tại sao check interrupt ngay trước khi gửi request ra ngoài vẫn chưa bảo đảm không có side effect sau cancellation? **Có race giữa check và commit; cần idempotency/giao thức commit.**
15. Khi nào nên restore interrupted flag trong catch? **Khi code không thể propagate `InterruptedException` và cần để tầng gọi biết yêu cầu interrupt, đồng thời thoát/tuân thủ chính sách hủy.**
16. `CancellationException` và `InterruptedException` của `get()` khác nhau thế nào? **Exception đầu cho biết Future bị hủy; exception sau cho biết thread gọi `get` bị interrupt.**
17. Khi cancel một task xếp hàng, có thể khẳng định nó lập tức bị loại khỏi mọi queue executor không? **Không; cách quản lý queued/cancelled tasks phụ thuộc implementation.**
18. Nếu task đã cancel nhưng bạn vẫn cần bảo đảm resource được đóng, phải theo dõi gì? **Kết thúc thực thi và cleanup theo giao thức riêng, không chỉ `isDone`.**

## 18. Kết luận

`Future.cancel(true)` là **yêu cầu hủy có khả năng gửi interrupt**, không phải cơ chế cưỡng bức dừng code Java. Khi cancel được chấp nhận, Future có thể lập tức báo `isCancelled()==true` và `isDone()==true`; `get()` ném `CancellationException`, nhưng worker **vẫn có thể đang chạy, cleanup hoặc tạo side effect**.

Task cần hợp tác với interruption, chọn API I/O có timeout/hủy thích hợp và nhả resource trong `finally`. `get(timeout)` chỉ giới hạn thời gian chờ của caller, còn `CompletableFuture.cancel(true)` trong Java 17 **không dùng interrupt** để điều khiển worker. Đối với nghiệp vụ có side effect không thể trùng lặp, thêm **idempotency, quyền commit, trạng thái kết thúc rõ ràng và giám sát stop latency**; không lấy giá trị trả về của `cancel` làm bằng chứng mọi hậu quả đã biến mất.

## Tài liệu tham khảo Java SE 17

- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `isCancelled`, `isDone`, `get` và timeout.
- [FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): implementation kết quả task và cancellation.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `shutdown`, `shutdownNow`, `awaitTermination`.
- [Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `interrupted` và `isInterrupted`.
- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `cancel` và ghi chú `mayInterruptIfRunning`.
- [ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): `lockInterruptibly`, `tryLock`.
- [InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html): đóng channel khi interrupt block và `ClosedByInterruptException`.
