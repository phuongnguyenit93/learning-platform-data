# InterruptedException và cách xử lý hợp lệ trong Java

Một thread có thể đang chờ dữ liệu, ngủ, chờ khóa hoặc đợi tác vụ khác. Khi ứng dụng muốn **yêu cầu thread dừng công việc đang làm**, Java thường dùng cơ chế **interrupt**. Đây là một **tín hiệu hợp tác**, không phải lệnh giết thread. Nhiều API chặn (*blocking APIs*) phản hồi tín hiệu ấy bằng cách ném `InterruptedException` để mã ứng dụng có cơ hội hủy công việc, đóng tài nguyên hoặc chuyển thông tin hủy lên tầng gọi.

Vấn đề không chỉ là biết cách `catch (InterruptedException e)`. Cần quyết định **ai sở hữu quyền hủy**, có nên tiếp tục tác vụ hay dừng, trạng thái interrupt của thread đã bị thay đổi thế nào, và bảo đảm dọn tài nguyên trong mọi đường thoát.

Bài này thuộc chủ đề **Interrupt & Hủy**, phạm vi **Java concurrency nói chung (Java 17+)**. Không xét cơ chế hủy của framework Spring.

Sau bài học, bạn sẽ:
- Giải thích sự khác nhau giữa `Thread.interrupt()`, interrupt status và `InterruptedException`.
- Hiểu vì sao một số phương thức chặn ném `InterruptedException` và **xóa trạng thái interrupt** khi ném.
- Biết hai chính sách thông dụng: **propagate** hoặc **re-interrupt rồi thoát**.
- Xử lý đúng ở `Runnable`, `Callable`, vòng lặp worker, `ExecutorService` và `Future.cancel(true)`.
- Phân biệt interrupt với timeout, cancellation, trạng thái hoàn tất và việc đóng tài nguyên.
- Nhận diện các anti-pattern như nuốt ngoại lệ, tiếp tục vô hạn, reset flag vô ý và dùng interrupt như phương thức dừng cưỡng bức.

## 1. Interrupt là tín hiệu hợp tác, không phải Thread.stop()

### 1.1. Interrupt status là gì?

Mỗi đối tượng `Thread` có một trạng thái **interrupted status**. Một thread khác có thể yêu cầu gián đoạn bằng:

~~~java
worker.interrupt();
~~~

Lời gọi này **không đồng nghĩa** worker dừng ngay. Tùy worker đang làm gì:

- Nếu đang chờ trong một API hỗ trợ interrupt như `Thread.sleep(...)`, `Object.wait(...)`, `Thread.join(...)`, `BlockingQueue.take()` hay `CountDownLatch.await()`, lời gọi chặn thường **ném `InterruptedException`** để worker quyết định cách xử lý.
- Nếu đang tính toán CPU và không kiểm tra trạng thái, nó có thể **tiếp tục chạy**.
- Nếu đang gọi API I/O hoặc thư viện bên ngoài, hành vi có thể khác: một số API đáp ứng interrupt theo hợp đồng riêng, một số phép chặn không giải phóng ngay. **Không mặc định mọi thao tác I/O đều bị cắt ngay**.
- Nếu worker đã hoàn tất, lời gọi interrupt không mang ý nghĩa “hủy lại công việc đã xong”.

Hợp đồng căn bản: **bên yêu cầu hủy gửi tín hiệu; bên thực thi hợp tác dừng**. Một giao thức dừng tốt thường kết hợp interrupt với kiểm tra trạng thái, giải phóng tài nguyên, timeout và chờ worker thực sự kết thúc.

### 1.2. Vì sao không dùng Thread.stop()?

`Thread.stop()` là API không an toàn và đã bị deprecated. Việc dừng cưỡng bức có thể làm thread nhả monitor trong lúc bất biến của object mới được cập nhật một phần, để những thread khác quan sát trạng thái không nhất quán. Cách hiện đại là **cooperative cancellation**: thread chủ động thoát khỏi đoạn xử lý ở thời điểm phù hợp.

`Thread.interrupt()` không tự động rollback thay đổi, không gọi `close()` thay mọi resource và không buộc thread thực thi `finally` ngay tại thời điểm signal.

## 2. Phân biệt Thread.interrupt(), isInterrupted() và Thread.interrupted()

Ba API dễ nhầm:

| API | Ai gọi / kiểm tra ai? | Có xóa interrupt status không? |
| --- | --- | --- |
| `someThread.interrupt()` | Gửi yêu cầu gián đoạn đến `someThread` | Không phải thao tác kiểm tra/xóa cờ theo nghĩa của người gọi |
| `someThread.isInterrupted()` | Đọc trạng thái interrupt của `someThread` | **Không** xóa |
| `Thread.interrupted()` | Static method kiểm tra **thread hiện tại** | **Có**, kiểm tra và **xóa** status |

**Điểm quan trọng:** Dù viết `t.interrupted()` vẫn gọi **static method** của `Thread`, nó kiểm tra thread **đang thực thi lời gọi**, không phải `t`. Nên viết đúng `Thread.interrupted()` để tránh hiểu lầm.

Ví dụ Java 17+ chạy độc lập:

~~~java
// InterruptFlagDemo.java
public class InterruptFlagDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        System.out.println("Initial: " + current.isInterrupted());
        current.interrupt();

        System.out.println("After interrupt: " + current.isInterrupted());
        System.out.println("Static check: " + Thread.interrupted());
        System.out.println("After static check: " +
            current.isInterrupted());
    }
}
~~~

~~~bash
javac InterruptFlagDemo.java
java InterruptFlagDemo
~~~

Stdout:

~~~text
Initial: false
After interrupt: true
Static check: true
After static check: false
~~~

Lần gọi `Thread.interrupted()` trả `true` vì status đang được đặt, **đồng thời xóa nó**. Sau đó `isInterrupted()` trả `false`.

**Không dùng `Thread.interrupted()` để chỉ “xem thử” một cờ mà vẫn mong caller khác thấy cờ ấy.** Nếu bạn vô ý xóa interrupt status trong một helper, tầng ngoài có thể không biết đã có yêu cầu hủy.

## 3. InterruptedException có ý nghĩa gì?

`InterruptedException` là **checked exception**. Những phương thức có khả năng chờ và phản hồi interrupt thường khai báo `throws InterruptedException`; caller phải **truyền tiếp** hoặc **bắt và xử lý**.

Ví dụ thường gặp trong Java 17:

| API | Vì sao có thể chờ? | Khi bị interrupt lúc chờ |
| --- | --- | --- |
| `Thread.sleep(...)` | Ngủ một khoảng thời gian | Ném `InterruptedException` |
| `Thread.join(...)` | Chờ thread khác kết thúc | Ném `InterruptedException` |
| `Object.wait(...)` | Chờ điều kiện trên monitor | Ném `InterruptedException` |
| `BlockingQueue.put(e)` | Chờ queue có chỗ | Ném `InterruptedException` |
| `BlockingQueue.take()` | Chờ queue có item | Ném `InterruptedException` |
| `CountDownLatch.await()` | Chờ count về 0 | Ném `InterruptedException` |
| `Semaphore.acquire()` | Chờ permit | Ném `InterruptedException` |
| `ReentrantLock.lockInterruptibly()` | Chờ lấy lock, có thể ngắt | Ném `InterruptedException` |
| `Condition.await()` | Chờ signal/predicate | Ném `InterruptedException` |
| `Future.get()` | Chờ tác vụ bất đồng bộ hoàn thành | Có thể ném `InterruptedException` cho **thread đang gọi get** |
| `ExecutorService.awaitTermination(...)` | Chờ executor kết thúc | Ném `InterruptedException` |

**Không phải mọi API đợi đều như vậy.** Ví dụ `ReentrantLock.lock()` không khai báo `InterruptedException` và không thoát chỉ vì caller bị interrupt, còn `lockInterruptibly()` được thiết kế cho trường hợp cần đáp ứng yêu cầu gián đoạn khi chờ khóa. Một số kiểu I/O phản hồi bằng exception khác hoặc cơ chế riêng.

### 3.1. Vì sao cờ thường bị xóa khi ném?

Với `Thread.sleep`, `Object.wait` và `Thread.join`, khi lời gọi phát hiện interrupt và ném `InterruptedException`, interrupt status bị **xóa theo hợp đồng API**. Nhiều phương thức chờ trong `java.util.concurrent` cũng ném ngoại lệ và tiêu thụ trạng thái theo hợp đồng riêng.

Hệ quả: bên nhận `catch (InterruptedException e)` **không được giả định** rằng `Thread.currentThread().isInterrupted()` vẫn là `true`. Đây là lý do mẫu **re-interrupt** tồn tại khi tầng hiện tại không thể truyền ngoại lệ lên.

### 3.2. Ví dụ độc lập kiểm chứng trạng thái trước và sau catch

~~~java
// InterruptedSleepDemo.java
import java.util.concurrent.CountDownLatch;

public class InterruptedSleepDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                System.out.println("Worker ready");
                ready.countDown();
                Thread.sleep(60_000);
                System.out.println("Unexpected completion");
            } catch (InterruptedException e) {
                System.out.println("Flag in catch: " +
                    Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("Flag restored: " +
                    Thread.currentThread().isInterrupted());
            } finally {
                System.out.println("Cleanup executed");
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("Main finished");
    }
}
~~~

~~~bash
javac InterruptedSleepDemo.java
java InterruptedSleepDemo
~~~

Stdout (không có interrupt bên ngoài lên thread main):

~~~text
Worker ready
Flag in catch: false
Flag restored: true
Cleanup executed
Main finished
~~~

`ready.countDown()` diễn ra trước khi main gọi `worker.interrupt()`. Worker có thể đang `sleep` hoặc chưa kịp vào `sleep`; ở cả hai trường hợp, phép `sleep` phát hiện interrupt và ném. Khi đã ném, status được xóa, nên dòng đầu trong catch in `false`. Mã chủ động gọi `interrupt()` trên thread hiện tại để khôi phục trạng thái. `finally` chạy khi worker thoát scope.

**Lưu ý:** ví dụ không có thao tác chờ thứ hai trong worker sau khi đặt lại flag, vì một blocking call tiếp theo có thể ném ngay nếu nó chú ý đến trạng thái interrupt. Trong thiết kế thực tế, hãy quyết định đường thoát và cleanup rõ ràng thay vì re-interrupt rồi tiếp tục xử lý vô hạn.

## 4. Chính sách hợp lệ thứ nhất: truyền tiếp InterruptedException

Nếu phương thức của bạn **có thể khai báo `throws InterruptedException`**, cách đơn giản và thường tốt nhất là **không nuốt tín hiệu**. Cho exception truyền lên tầng có trách nhiệm quyết định hủy.

~~~java
// Minh họa phương thức trong class ứng dụng:
static String receive(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

Hàm `receive` ở trên chỉ là đoạn code minh họa, cần `import java.util.concurrent.BlockingQueue;` trong file thật.

### 4.1. Ví dụ chạy được: phương thức truyền tiếp, worker quyết định dừng

~~~java
// PropagateInterruptedDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class PropagateInterruptedDemo {
    private static String receive(BlockingQueue<String> queue)
            throws InterruptedException {
        return queue.take();
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                receive(queue);
                System.out.println("Unexpected message");
            } catch (InterruptedException e) {
                System.out.println("Worker cancelled");
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Worker cleanup");
            }
        });

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
        System.out.println("Main done");
    }
}
~~~

~~~bash
javac PropagateInterruptedDemo.java
java PropagateInterruptedDemo
~~~

Stdout:

~~~text
Worker cancelled
Worker cleanup
Main done
~~~

Việc `started.countDown()` chỉ bảo đảm worker đã vào lambda, chưa chắc đang đứng trong `take()`. Nhưng vì queue rỗng và main đặt interrupt, worker sẽ nhận `InterruptedException` trong `take()` dù interrupt đến trước hay trong lúc chờ. Tầng `receive` không chặn thông tin hủy; chỉ tầng `Runnable` phải bắt vì `Runnable.run()` không khai báo checked exception.

### 4.2. Khi cleanup nhưng vẫn muốn truyền exception

~~~java
// Mã minh họa, resource đã mở và work là method có thể ném InterruptedException.
try {
    work();
} finally {
    releaseLocalState();
}
~~~

Nếu `work()` ném `InterruptedException`, khối `finally` vẫn chạy (trong điều kiện JVM tiếp tục thực thi thông thường), sau đó ngoại lệ truyền lên caller. Điều này thường **rõ ràng hơn** việc catch exception rồi âm thầm tiếp tục.

Với resource là `AutoCloseable`, ưu tiên `try-with-resources`, vì Java gọi `close()` lúc thoát scope. Việc đóng resource không tự đảm bảo task đã hoàn thành nghiệp vụ; nếu bị hủy giữa chừng, cần xem xét giao thức rollback/compensation phù hợp.

### 4.3. Có cần re-interrupt khi đã throw tiếp?

Nếu bạn **truyền tiếp chính `InterruptedException`**, thông tin gián đoạn đã được chuyển lên caller qua exception; thường **không cần** khôi phục flag ở tầng trung gian. Caller cuối cùng quyết định việc đặt lại status hay dừng.

Không biến mẫu re-interrupt thành công thức máy móc “catch ở đâu cũng interrupt lại rồi throw” vì điều đó có thể ảnh hưởng các blocking calls của tầng trên. Quan trọng là có **một hợp đồng xử lý nhất quán** và không làm mất yêu cầu hủy.

## 5. Chính sách hợp lệ thứ hai: restore interrupt rồi kết thúc

Một số interface không cho phương thức hiện tại ném checked `InterruptedException`. Ví dụ `Runnable.run()`, `Supplier.get()` hoặc callback không khai báo checked exception. Ở ranh giới ấy, mẫu thường gặp:

~~~java
// Mã minh họa trong Runnable:
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

`doInterruptibleWork()` là tên minh họa, không phải Java API có sẵn. Ý nghĩa:

1. Catch đúng loại `InterruptedException`.
2. **Khôi phục interrupt flag**, để tầng sở hữu thread hoặc code chạy sau có thể biết đã từng có yêu cầu gián đoạn.
3. **Thoát** khỏi công việc hiện tại (return, break vòng worker, hoặc chuyển sang kết thúc theo giao thức), tránh tiếp tục như thể mọi việc bình thường.

### 5.1. Vòng consumer chờ BlockingQueue

~~~java
// Mã minh họa trong Runnable; queue và handle đã khai báo:
while (!Thread.currentThread().isInterrupted()) {
    try {
        Message item = queue.take();
        handle(item);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
    }
}
~~~

Đoạn này không chạy độc lập vì `Message` và `handle` là API giả định. Nếu `handle(item)` thực hiện I/O có thể bị gián đoạn hoặc ném lỗi nghiệp vụ, phải thiết kế chính sách tiếp theo. Việc lặp kiểm tra `isInterrupted()` **không xóa** flag.

**Sai lầm đặc biệt nguy hiểm:**

~~~java
// Anti-pattern: nuốt interrupt rồi tiếp tục vòng lặp.
while (true) {
    try {
        queue.take();
    } catch (InterruptedException ignored) {
        // Không dừng, không thông báo, không restore status.
    }
}
~~~

Sau khi blocking call ném, flag thường đã bị xóa. Vòng tiếp tục chờ và **bỏ qua yêu cầu hủy**. Điều này có thể khiến `shutdownNow()` hoặc cơ chế hủy ứng dụng không đạt kết quả mong muốn.

Một biến thể tệ khác là catch, re-interrupt, rồi **tiếp tục ngay** chờ `take()` trong vòng vô hạn. Vì flag vẫn đặt, API chặn có thể liên tục ném lại, gây vòng lặp lỗi/CPU cao. Nếu lựa chọn restore status, phải đi kèm **đường thoát**.

### 5.2. Nếu phương thức buộc phải trả một giá trị?

Nếu contract không cho ném checked exception, bạn có thể:
- Trả một kết quả biểu diễn **cancelled** rõ ràng nếu API hỗ trợ.
- Khôi phục flag rồi chuyển thông tin lên bằng một kiểu kết quả/exception **đã được API chấp nhận**.
- Để tầng quản lý thread quyết định retry/hủy thay vì tự retry vô hạn.

Không tự tạo giá trị thành công giả (ví dụ trả `0` cho một giao dịch chưa hoàn thành) chỉ để “bắt cho xong ngoại lệ”. Cách chuyển sang unchecked exception có thể phù hợp một số abstraction, nhưng cần hợp đồng rõ ràng; việc wrap bừa `InterruptedException` thành `RuntimeException` và không restore có thể làm mất trạng thái hủy đối với tầng điều phối.

## 6. InterruptedException không phải lúc nào cũng có nghĩa “đã dừng xong”

Một thread bị interrupt **có thể**:
- Bắt exception và thoát đúng cách.
- Bắt exception rồi tiếp tục làm việc.
- Đang ở code không phản hồi interrupt.
- Đang cleanup hoặc thực hiện I/O/transaction chưa hoàn tất.

Vì thế `interrupt()` là **yêu cầu**, không phải **xác nhận đã hoàn thành việc hủy**. Muốn biết worker đã thật sự kết thúc, có thể `join()`, đợi `CountDownLatch`/`Future` hoặc một tín hiệu hoàn tất thích hợp, kèm timeout nếu cần.

Cần phân biệt các trạng thái:

| Sự kiện | Kết luận chắc chắn |
| --- | --- |
| `worker.interrupt()` được gọi | Đã gửi yêu cầu gián đoạn theo hợp đồng Thread |
| `worker.isInterrupted() == true` | Interrupt status đang được đặt tại thời điểm quan sát |
| Blocking call ném `InterruptedException` | Lời gọi đã thoát theo đường gián đoạn |
| `worker.join()` trả về bình thường | Worker đã kết thúc |
| `Future.cancel(true)` trả true | Future được đánh dấu hủy; có yêu cầu interrupt nếu task đang chạy và hỗ trợ |
| `Future.isCancelled() == true` | Future ở trạng thái canceled, **không chứng minh worker đã dừng tức thì** |
| `ExecutorService.shutdownNow()` trả về | Đã thử dừng bằng interrupt và trả danh sách task chưa bắt đầu; **không bảo đảm** worker đã kết thúc |

### 6.1. Interrupt không rollback

Nếu task thực hiện:
1. Ghi tệp hoặc cơ sở dữ liệu.
2. Gửi một request.
3. Chờ response và bị interrupt.

Không thể suy ra công đoạn 1 hoặc 2 đã được tự động đảo ngược. Cancellation là câu chuyện **lifecycle và hợp đồng nghiệp vụ**, không chỉ một exception của thread. Hãy thiết kế transactional boundary, idempotency, retry hoặc compensation theo hệ thống cụ thể.

## 7. Future.cancel(true) và interrupt trong ExecutorService

`ExecutorService.submit(...)` trả một `Future`. Với các implementation thông dụng dựa trên `FutureTask`, `cancel(true)` yêu cầu hủy và **cố gián đoạn thread đang chạy**; nhưng không đảm bảo task dừng ngay. `cancel(false)` không yêu cầu interrupt worker đang chạy.

Sau khi Future được hủy:
- `future.isCancelled()` có thể trả `true`.
- `future.get()` ném `CancellationException` (unchecked), không trả kết quả ngay cả khi mã task đã thực hiện một phần.
- Worker có thể vẫn đang cleanup hoặc chưa phản hồi interrupt.

### Ví dụ Java 17+ phân biệt Future đã hủy với worker hoàn tất

~~~java
// FutureCancellationDemo.java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        try {
            Future<String> future = pool.submit(() -> {
                entered.countDown();
                try {
                    neverReleased.await();
                    return "completed";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "stopped cooperatively";
                } finally {
                    finished.countDown();
                }
            });

            entered.await();
            boolean accepted = future.cancel(true);

            finished.await(); // Đợi task thực sự thoát scope.
            System.out.println("Cancel accepted: " + accepted);
            System.out.println("Future cancelled: " + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get(): CancellationException");
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Worker did not terminate");
            }
        }
    }
}
~~~

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Trong điều kiện chạy bình thường, không có interrupt bên ngoài, stdout:

~~~text
Cancel accepted: true
Future cancelled: true
get(): CancellationException
~~~

Lập luận:
- Main chỉ gọi `cancel(true)` sau khi task đã bắt đầu (`entered.await()`). Task đang hoặc sắp chờ một latch không bao giờ được mở.
- Việc cancel yêu cầu interrupt; task bắt `InterruptedException`, phục hồi flag, rồi rời scope. `finished.await()` xác nhận `finally` đã chạy.
- Future vẫn là **cancelled**, nên `get()` ném `CancellationException` dù callable đã trả chuỗi `"stopped cooperatively"` trong lúc xử lý hủy.
- `pool.shutdownNow()` là bước cleanup executor, không thay thế việc worker tự xử lý interrupt; ví dụ chờ pool kết thúc có giới hạn.

**Điểm cần kiểm tra với API khác:** Không phải mọi loại `Future` hoặc abstraction bất đồng bộ đều triển khai `cancel(true)` bằng cách interrupt thread xử lý. Cần đọc hợp đồng **loại Future cụ thể**; ví dụ `CompletableFuture.cancel(boolean)` có semantics khác về việc interrupt. Không suy từ tham số `true` thành một bảo đảm phổ quát rằng mọi loại async computation bị cắt ngay.

## 8. Shutdown executor đúng cách và xử lý interrupt của thread điều phối

Một service sở hữu `ExecutorService` cần có kế hoạch ngừng nhận task mới và đợi các task đã nhận kết thúc. `shutdown()` không tự dừng task đang đợi vô hạn trên queue hay I/O. `shutdownNow()` cố gián đoạn các task đang chạy, nhưng vẫn cần task hợp tác.

### 8.1. Mẫu graceful shutdown trong Java 17

~~~java
// ExecutorShutdownDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            pool.execute(() -> System.out.println("Task finished"));
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                        System.err.println("Executor still running");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

~~~bash
javac ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

Trong lần chạy bình thường, stdout:

~~~text
Task finished
~~~

Cách đọc:
1. `shutdown()` ngừng nhận task mới, **không** tự chờ.
2. `awaitTermination(...)` chờ có hạn cho executor kết thúc.
3. Khi timeout, `shutdownNow()` yêu cầu interrupt tác vụ đang chạy và trả các task chưa bắt đầu; không bảo đảm mọi worker đã dừng.
4. Nếu **thread đang điều phối shutdown** bị interrupt khi đang chờ, cần bảo toàn tín hiệu bằng `Thread.currentThread().interrupt()` và có chính sách xử lý tiếp. Mẫu này thử `shutdownNow()` trước khi restore flag.

**Lưu ý về JDK:** Trên Java 17, `ExecutorService` không cung cấp `AutoCloseable.close()` theo các phiên bản mới hơn. Quản lý shutdown chủ động như trên thay vì giả định `try (ExecutorService e = ...)` biên dịch được trên mọi JDK.

### 8.2. Điều gì xảy ra khi catch InterruptedException từ awaitTermination?

Đây là interrupt của **thread caller đang chờ executor**, không nhất thiết là interrupt của worker trong pool. Caller phải quyết định: tiếp tục đợi trong một giao thức đặc biệt hay yêu cầu shutdown mạnh hơn, rồi khôi phục status/propagate theo contract. Không được mặc định ngoại lệ cho caller có nghĩa các worker đã chết.

## 9. Interruptible lock, Condition và điểm chờ khác nhau

### 9.1. Lock.lock() so với lockInterruptibly()

`ReentrantLock.lock()` lấy khóa theo cơ chế không thoát bằng `InterruptedException`. Nếu caller đang chờ khóa và bị interrupt, lời gọi thường vẫn tiếp tục đợi cho tới khi nhận khóa (trạng thái interrupt được giữ/khôi phục theo implementation phù hợp). Ngược lại, `lockInterruptibly()` cho phép chờ khóa bị ngắt.

Ví dụ chạy độc lập Java 17+:

~~~java
// InterruptibleLockDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch ready = new CountDownLatch(1);

        lock.lock(); // Main giữ khóa.
        try {
            Thread waiter = new Thread(() -> {
                ready.countDown();
                try {
                    lock.lockInterruptibly();
                    try {
                        System.out.println("Unexpected acquisition");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException e) {
                    System.out.println("Waiter interrupted");
                    Thread.currentThread().interrupt();
                }
            });

            waiter.start();
            ready.await();
            waiter.interrupt();
            waiter.join();
        } finally {
            lock.unlock();
        }

        System.out.println("Main released lock");
    }
}
~~~

~~~bash
javac InterruptibleLockDemo.java
java InterruptibleLockDemo
~~~

Stdout:

~~~text
Waiter interrupted
Main released lock
~~~

Main giữ lock đến sau khi `waiter.join()`, nên waiter không thể lấy khóa. Nó nhận interrupt và `lockInterruptibly()` ném; waiter chỉ gọi `unlock()` khi thật sự lấy khóa thành công. `finally` ở main nhả khóa sau khi waiter kết thúc.

**Cảnh báo:** Không đặt `unlock()` ngoài khối chỉ chạy khi caller đã lấy được khóa. Nếu `lockInterruptibly()` ném trước khi thành công, việc `unlock()` sai ownership có thể ném `IllegalMonitorStateException`.

### 9.2. Condition.await() và Object.wait()

`Object.wait()` phải được gọi khi thread giữ monitor tương ứng; trong khi chờ, nó **nhả monitor** và khi trở về phải lấy lại monitor theo contract. `Condition.await()` thường nhả associated lock khi chờ và lấy lại trước khi trở về, theo hợp đồng condition/lock tương ứng. Cả hai có thể ném `InterruptedException`.

Nếu chờ một predicate, luôn dùng vòng lặp:

~~~java
// Mã minh họa trong class có lock, condition và boolean ready:
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    consumeReadyState();
} finally {
    lock.unlock();
}
~~~

`consumeReadyState()` là phương thức ứng dụng giả định. Tại đây `condition.await()` có thể ném, nên phương thức bao quanh cần khai báo `throws InterruptedException` hoặc catch đúng chính sách. `finally` nhả lock; không tự đoán tình trạng predicate sau khi bị interrupt.

**Vì sao dùng while?** Có thể có spurious wakeup hoặc state bị thread khác thay đổi trước lúc tiếp tục chạy, nên luôn kiểm tra lại điều kiện.

### 9.3. Thread.sleep không nhả monitor

`Thread.sleep(...)` **không nhả** bất kỳ monitor nào mà thread đang giữ. Nếu thread ngủ trong `synchronized`, các thread cần cùng monitor vẫn bị chặn. Vì vậy không dùng sleep như một cách “cho thread khác cơ hội vào khóa” trong giao thức điều kiện. Dùng `wait/notify` hoặc `Condition` theo hợp đồng khi cần nhả khóa lúc chờ.

## 10. Hợp tác dừng trong tác vụ CPU-bound

Một vòng tính toán không gọi API chặn có thể **không bao giờ ném `InterruptedException`** chỉ vì thread khác gọi `interrupt()`. Nó phải chủ động kiểm tra cờ gián đoạn ở những điểm hợp lý.

~~~java
// CooperativeCpuDemo.java
import java.util.concurrent.CountDownLatch;

public class CooperativeCpuDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (!Thread.currentThread().isInterrupted()) {
                // Minh họa điểm kiểm tra; không thực hiện công việc thật.
                Thread.onSpinWait();
            }
            System.out.println("CPU worker stopped");
        });

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
        System.out.println("Main observed termination");
    }
}
~~~

~~~bash
javac CooperativeCpuDemo.java
java CooperativeCpuDemo
~~~

Stdout trong lần chạy bình thường:

~~~text
CPU worker stopped
Main observed termination
~~~

Thread kiểm tra bằng `isInterrupted()` nên không tự xóa cờ; main gửi interrupt rồi `join()` để biết thực sự kết thúc.

Ví dụ dùng spin để minh họa đơn giản, **không phải kỹ thuật xử lý CPU-bound hiệu quả**. Trong một thuật toán thật, kiểm tra flag sau mỗi chunk công việc phù hợp, tránh vòng lặp trống đốt CPU. Đối với thao tác blocking hỗ trợ interrupt, ưu tiên API đó thay vì tự spin.

### 10.1. Cờ volatile riêng so với interrupt

Một ứng dụng có thể dùng `volatile boolean stopRequested` để yêu cầu worker dừng vòng tính toán, nhất là khi không dùng blocking APIs. Nhưng nếu worker đang kẹt ở `BlockingQueue.take()`, chỉ đặt `stopRequested = true` **không tự đánh thức take**. Có thể cần `interrupt`, sentinel hoặc timed poll. Đừng giữ hai cơ chế dừng không nhất quán (ví dụ một nơi đặt cờ, nơi khác interrupt mà worker chỉ theo dõi một cái).

## 11. Cleanup, try-with-resources và tính đúng nghiệp vụ

### 11.1. Cleanup cần chạy khi code thật sự thoát scope

Một worker thường có:
- Resource như `InputStream`, `Reader`, `Socket` hoặc kết nối.
- Trạng thái context như `ThreadLocal`.
- Lock hoặc semaphore permit.
- Task đang cập nhật nhiều bước.

Khi có interrupt, thiết kế đường thoát qua `finally` hoặc `try-with-resources`:

~~~java
// Mã minh họa trong class; resource và process có hợp đồng phù hợp.
try (Resource resource = openResource()) {
    process(resource); // Có thể ném InterruptedException.
} finally {
    threadContext.remove();
}
~~~

`Resource`, `openResource()`, `process(...)` và `threadContext` là tên giả định để minh họa cấu trúc, không phải file độc lập. `try-with-resources` gọi `close()` khi rời scope và `finally` dọn context. Nhưng **cancellation không tự động đóng resource ngay lúc caller gửi interrupt**: chỉ khi luồng thực thi đi qua scope dọn dẹp, hoặc owner có giao thức đóng riêng.

### 11.2. Giữ interrupt flag có thể tác động lên cleanup

Sau khi catch và re-interrupt, các blocking calls tiếp theo của **cùng thread** có thể phát hiện cờ và ném nhanh. Nếu cleanup cần chờ interruptible API, hãy thiết kế rõ cách thực hiện:
- Nếu có thể, cho cleanup xảy ra trong `finally` trước khi tín hiệu hủy được chuyển lên caller.
- Nếu phải đợi một bước đóng tài nguyên có timeout, xác định có cần trì hoãn, khôi phục hoặc xử lý lại trạng thái interrupt theo contract, **không vô tình xóa vĩnh viễn tín hiệu**.
- Đừng chạy I/O blocking vô hạn trong `finally` rồi kỳ vọng cancellation luôn hoàn thành nhanh.
- Đối với permit/lock, chỉ nhả khi đã thực sự sở hữu; đối với `ThreadLocal` theo task, dọn mapping trong `finally`, nhất là worker pool tái sử dụng thread.

Không có một mẫu cleanup duy nhất phù hợp mọi API. Điều phải giữ là **không mất yêu cầu hủy** và **không bỏ lại trạng thái/handle** ngoài phạm vi sở hữu.

## 12. Phân biệt InterruptedException với TimeoutException và CancellationException

| Loại | Thường xuất hiện ở đâu? | Ý nghĩa chính |
| --- | --- | --- |
| `InterruptedException` | `sleep`, `join`, `take`, `await`, `Future.get`, `lockInterruptibly` | **Thread đang chờ** được yêu cầu gián đoạn |
| `TimeoutException` | `Future.get(timeout, unit)` | Caller đã chờ quá hạn; **task chưa chắc bị hủy** |
| `CancellationException` | `Future.get()` sau khi Future bị cancel | Future bị hủy, không cung cấp kết quả |
| `ExecutionException` | `Future.get()` khi Callable lỗi | Task đã kết thúc bằng exception (cause ở `getCause()`) |
| `RejectedExecutionException` | Submit khi executor không nhận thêm task hoặc quá tải tùy cấu hình | Task bị từ chối nhận, không đồng nghĩa interrupt |

Ví dụ: `future.get(100, MILLISECONDS)` ném `TimeoutException` **không tự gọi `future.cancel(true)`**. Caller phải quyết định có yêu cầu hủy hay không và xử lý việc task có thể vẫn chạy. Ngược lại, `Future.get()` có thể ném `InterruptedException` vì **thread caller** bị interrupt trong lúc chờ; điều đó **không có nghĩa task đang chạy nhất thiết bị interrupt hoặc cancel**.

**Không gộp các ngoại lệ này vào một catch tổng quát rồi bỏ qua**: chúng biểu diễn các trạng thái lifecycle khác nhau và cần phản ứng khác nhau.

## 13. Những anti-pattern phổ biến

| Sai lầm | Tại sao sai | Hướng xử lý |
| --- | --- | --- |
| `catch (InterruptedException ignored) {}` | Nuốt yêu cầu hủy | Truyền tiếp hoặc restore + thoát |
| Catch, restore flag, rồi lặp blocking ngay | Có thể ném liên tục, gây busy error loop | Thoát worker hoặc chuyển sang đường kết thúc |
| Catch và `return success` dù task dở dang | Báo sai kết quả nghiệp vụ | Báo cancelled/failure theo contract |
| Gọi `Thread.interrupted()` để chỉ kiểm tra | Nó xóa flag của current thread | Dùng `isInterrupted()` nếu không muốn xóa |
| Dùng `interrupt()` như “kill ngay” | Worker có thể không hợp tác | Cài cooperative cancellation + chờ termination |
| Giữ lock khi đang chờ vô hạn mà không có đường hủy | Có thể kéo dài contention/deadlock | Thiết kế lock/condition/timeout phù hợp |
| Gọi `unlock()` khi `lockInterruptibly()` chưa thành công | Sai ownership, exception khác | Chỉ unlock trong scope sau khi nhận lock |
| `shutdownNow()` rồi cho rằng mọi task đã dừng | Chỉ cố interrupt, task có thể chạy tiếp | Theo dõi termination và đường thoát worker |
| `Future.get(timeout)` timeout rồi coi task đã cancel | Timeout chỉ ngừng chờ caller | Cancel riêng nếu cần, có giám sát kết thúc |
| Dựa vào `finally` như cơ chế chống process kill | JVM crash/halt có thể không chạy finally | Cần recovery/durable consistency nếu yêu cầu |
| Tự reset interrupt status không có chủ đích | Mất dấu hiệu hủy cho caller | Chỉ xóa khi sở hữu giao thức |
| Đem `InterruptedException` ra làm exception nghiệp vụ tùy ý | Nhầm tín hiệu lifecycle với lỗi dữ liệu | Giữ ý nghĩa hủy/chờ bị gián đoạn |

### 13.1. Không nên “bắt Exception chung rồi retry”

~~~java
// Mã minh họa anti-pattern:
while (true) {
    try {
        doWork();
    } catch (Exception e) {
        log(e);
    }
}
~~~

Nếu `doWork()` chặn và ném `InterruptedException`, catch tổng quát có thể **nuốt** nó; thread không dừng. Còn `doWork`, `log` là placeholder, không phải chương trình Java độc lập.

Tách `InterruptedException` thành nhánh xử lý riêng ở những chỗ có thể ném, rồi mới phân loại các lỗi khác. Nếu bắt `Exception` ở tầng giám sát, hãy bảo đảm tín hiệu hủy không bị biến thành “error thông thường, thử lại ngay”.

### 13.2. Không phải mọi catch đều phải re-interrupt

Nếu caller thật sự yêu cầu **chờ dù bị interrupt** (một số cơ chế nội bộ đặc biệt), có thể tạm ghi nhận interrupt, tiếp tục chờ, rồi restore status khi rời phạm vi. Nhưng đây là **ngoại lệ cần chủ đích rõ**, không phải mặc định cho worker. Nếu mục tiêu là phản hồi yêu cầu dừng, tiếp tục chờ không giới hạn thường trái với hợp đồng hủy.

## 14. Checklist thiết kế và tự kiểm tra

### Checklist nhanh

1. **Ai sở hữu quyền dừng?** Main thread, service, executor hay thành phần giám sát?
2. **Worker đang chờ ở đâu?** `sleep`, `take`, `await`, lock, I/O hay vòng CPU?
3. **API có hỗ trợ interrupt không?** Phải đọc hợp đồng chính xác; không đoán mọi blocking call đều ném `InterruptedException`.
4. **Phương thức có thể throw tiếp không?** Nếu có, ưu tiên truyền `InterruptedException` tới tầng quyết định. Nếu không, restore flag và thoát theo giao thức.
5. **Mọi đường thoát có cleanup không?** `finally`, try-with-resources, unlock/permit/ThreadLocal.
6. **Có chờ xác nhận kết thúc không?** `join()`/`Future`/`awaitTermination` phù hợp, có timeout khi cần.
7. **Có nhầm timeout với hủy không?** Timed wait timeout không tự cancel task.
8. **Có producer/consumer bị kẹt vô hạn không?** Giao thức dừng phải đánh thức được các worker đang chờ.
9. **Có báo trạng thái nghiệp vụ đúng không?** Task bị hủy không được tự báo thành công hoặc làm mất công việc không có recovery.
10. **Có test race giữa “đã gửi interrupt” và “chưa vào blocking call” không?** Blocking API tương thích phải phát hiện status đã đặt; code của bạn không được dựa chỉ vào thứ tự sleep.

### Câu hỏi tự kiểm tra

**1.** `worker.interrupt()` có bảo đảm worker dừng ngay không?  
**Đáp án:** Không. Đây là yêu cầu hợp tác; worker có thể bắt exception rồi tiếp tục hoặc chưa kiểm tra flag.

**2.** Khác nhau giữa `Thread.interrupted()` và `Thread.currentThread().isInterrupted()`?  
**Đáp án:** Cả hai xem current thread khi gọi theo mẫu này, nhưng `Thread.interrupted()` **xóa status**, còn `isInterrupted()` **không** xóa.

**3.** Sau khi `Thread.sleep` ném `InterruptedException`, `isInterrupted()` thường là gì?  
**Đáp án:** `false` vì phép chờ đã xóa status khi ném. Nếu không thể throw tiếp và muốn giữ thông tin cho tầng ngoài, gọi `Thread.currentThread().interrupt()`.

**4.** Một phương thức `throws InterruptedException` nên làm gì khi `queue.take()` bị interrupt?  
**Đáp án:** Thường để ngoại lệ truyền lên caller, dọn resource trong `finally` nếu cần; không nuốt nó.

**5.** `Runnable.run()` không khai báo checked exception; worker bị interrupt nên làm gì?  
**Đáp án:** Một lựa chọn hợp lệ là catch `InterruptedException`, re-interrupt current thread, rồi thoát task; chính sách cụ thể tùy contract.

**6.** `Future.cancel(true)` trả true có chứng minh toàn bộ side effect của task đã dừng?  
**Đáp án:** Không. Future bị đánh dấu cancelled và có yêu cầu interrupt khi phù hợp; task có thể vẫn chạy hoặc cleanup.

**7.** Nếu `future.get(timeout)` ném `TimeoutException`, task tự bị cancel?  
**Đáp án:** Không. Caller cần quyết định cancel riêng và xử lý completion.

**8.** `lock.lock()` và `lock.lockInterruptibly()` có khác khi đang chờ không?  
**Đáp án:** Có. `lockInterruptibly()` có thể thoát chờ bằng `InterruptedException`; `lock()` không có cùng hợp đồng ném checked exception.

**9.** Trong worker loop, bắt `InterruptedException` rồi tiếp tục `take()` vô hạn gây gì?  
**Đáp án:** Nuốt tín hiệu dừng hoặc vòng lỗi liên tục nếu restore rồi lặp, làm shutdown không tiến triển.

**10.** Đã bắt `InterruptedException` rồi restore flag, có nên tiếp tục gọi `sleep()` như không có gì xảy ra?  
**Đáp án:** Thường không. `sleep()` có thể phát hiện flag và ném ngay; nếu muốn dừng, hãy thoát theo giao thức.

**11.** Có thể dùng `join()` để xác nhận worker đã kết thúc sau interrupt không?  
**Đáp án:** Có, nếu `join()` trả về bình thường. Caller nên cân nhắc timed join và xử lý việc thread đang chờ bị interrupt.

**12.** `ExecutorService.shutdown()` có giải phóng mọi task đang `BlockingQueue.take()` không?  
**Đáp án:** Không. Shutdown không tự interrupt hoặc cung cấp item; cần giao thức worker stop/cancel và chờ kết thúc.

**13.** Một worker cập nhật tệp xong mới bị interrupt. Việc catch `InterruptedException` có tự hoàn tác tệp không?  
**Đáp án:** Không. Phải thiết kế transaction/recovery/compensation tương ứng nếu nghiệp vụ cần.

**Ghi nhớ:** `InterruptedException` là tín hiệu quan trọng của **cooperative cancellation**. **Truyền tiếp** khi có thể; nếu tầng hiện tại không thể truyền checked exception thì thường **khôi phục interrupt flag và thoát**. Luôn phân biệt **yêu cầu hủy** với **đã kết thúc**, giữ cleanup đúng phạm vi và không biến interrupt thành lỗi thông thường bị nuốt mất.

### Tài liệu tham khảo chuẩn

- Java SE 17, `Thread.interrupt()`, `Thread.interrupted()`, `isInterrupted()` và `sleep()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17, `InterruptedException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html
- Java SE 17, `BlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Java SE 17, `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17, `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17, `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html