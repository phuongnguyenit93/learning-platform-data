# Không nuốt InterruptedException hoặc làm mất tín hiệu hủy trong Java

## 1. Vì sao việc xử lý InterruptedException là một phần của tính đúng đắn?

Một tác vụ chạy đồng thời có thể phải dừng trước khi hoàn thành: người dùng hủy, quá thời hạn xử lý, ứng dụng shutdown, hoặc một task khác không còn cần kết quả. Java sử dụng **interrupt** như một yêu cầu hủy hợp tác. Những phép chờ có thể ngắt, chẳng hạn `Thread.sleep()`, `Object.wait()`, `Thread.join()`, `BlockingQueue.take()`, `CountDownLatch.await()` và `Condition.await()`, thông báo cho caller bằng `InterruptedException`.

Sai lầm nguy hiểm:

~~~java
// SAI: đây chỉ là minh họa, không phải chương trình độc lập.
try {
    blockingOperation();
} catch (InterruptedException ignored) {
    // Bỏ qua rồi tiếp tục làm việc.
}
~~~

Một phương thức chờ thông thường **xóa interrupt status** khi ném `InterruptedException`. Nếu catch rỗng, tín hiệu hủy có thể biến mất trong mắt các tầng phía trên. Tác vụ tiếp tục hoạt động như chưa có gì xảy ra, khiến shutdown treo, request vượt deadline, hoặc side effect được thực hiện sau khi bên gọi đã yêu cầu hủy.

**Nguyên tắc:** Một tầng code không có quyền tự ý làm biến mất yêu cầu hủy mà tầng khác có thể cần biết. Khi nhận `InterruptedException`, hãy **truyền lên**, hoặc **khôi phục interrupt status và thoát theo hợp đồng** nếu không thể truyền checked exception; trường hợp chủ động xử lý hoàn toàn tín hiệu phải được thiết kế và tài liệu hóa rõ.

Bài này chỉ xét cơ chế interrupt và hủy của **Java concurrency nói chung**, không phụ thuộc framework.

### Mục tiêu sau bài

Bạn sẽ có khả năng:

1. Giải thích vì sao `InterruptedException` thường đi kèm việc clear cờ ngắt và điều gì xảy ra nếu catch rỗng.
2. Phân biệt **propagate**, **restore flag**, **handle hoàn toàn** và **nuốt tín hiệu**.
3. Viết ví dụ Java 17+ minh họa mất interrupt, truyền ngoại lệ, khôi phục cờ và cleanup trong worker.
4. Phối hợp `Future.cancel(true)`, executor shutdown, latch và xác nhận task thật sự dừng mà không suy diễn sai từ trạng thái Future.
5. Tránh mất yêu cầu hủy trong catch rộng, retry loop, xử lý timeout, khóa và I/O.
6. Thiết kế test không phụ thuộc `Thread.sleep` của thread điều phối để đoán lịch chạy.

## 2. Interrupt status và ý nghĩa của InterruptedException

Mỗi thread có một trạng thái interrupt. `target.interrupt()` là yêu cầu ngắt thread đích; không phải lệnh ép thread đó dừng ngay lập tức. Nếu thread đang chờ trong phương thức interruptible, phương thức có thể ném `InterruptedException` và thread cần phản ứng.

Ba API dễ nhầm:

| API | Tác động | Có xóa flag không? |
| --- | --- | --- |
| `target.interrupt()` | Yêu cầu ngắt thread đích | Đây không phải thao tác kiểm tra/clear |
| `target.isInterrupted()` | Quan sát cờ của thread đích | Không |
| `Thread.interrupted()` | Đọc cờ của **thread đang chạy** | **Có**, test-and-clear |

**`Thread.interrupted()` là phương thức static.** Không nên viết `worker.interrupted()` để hỏi worker: lời gọi static đó vẫn kiểm tra và xóa flag của **current thread**. Hãy dùng `worker.isInterrupted()` nếu cần quan sát trạng thái worker từ nơi khác.

Khi một phép chờ `sleep`, `wait`, `join` hoặc `await` nhận interrupt theo hợp đồng và ném `InterruptedException`, **flag thường đã bị clear** tại thời điểm catch chạy. Ngoại lệ chứa thông tin “vừa có yêu cầu ngắt” ngay cả khi `Thread.currentThread().isInterrupted()` trong catch trả false.

### Interrupt là yêu cầu, không phải kết quả hoàn thành

~~~text
Caller                     Worker
  |                           |
  +-- interrupt() ----------->|  yêu cầu hủy
  |                           |
  |                           +-- nhận biết qua polling hoặc wait
  |                           +-- cleanup / bảo toàn invariant
  |                           +-- kết thúc
  |
  +-- join() / latch -------->|  xác nhận hoàn tất
~~~

Gửi interrupt không bảo đảm tài nguyên được đóng, transaction được rollback hoặc worker đã rời khỏi critical section. Nếu caller cần xác nhận, hãy dùng `Thread.join()`, `CountDownLatch`, một kênh kết quả hoặc cơ chế lifecycle được thiết kế riêng.

### Happens-before

Java Memory Model có quy tắc đồng bộ liên quan interrupt: hành động ngắt một thread **happens-before** điểm thread đích phát hiện ra interrupt theo cơ chế JMM thích hợp. Điều này không biến interrupt thành message queue hay transaction; các cập nhật trạng thái dùng chung khác vẫn cần giao thức phù hợp, và một thread không bao giờ kiểm tra tín hiệu có thể không tiến triển đến điểm nhận biết.

## 3. Catch rỗng phá hợp đồng hủy như thế nào?

Xét một worker:

~~~java
// SAI: code minh họa trong Runnable.
while (hasMoreWork()) {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ignored) {
        // Flag đã bị clear, vòng lặp tiếp tục.
    }

    performSideEffect();
}
~~~

Caller gọi `worker.interrupt()` để yêu cầu ngừng xử lý. Khi `sleep()` ném `InterruptedException`, catch rỗng khiến vòng lặp vẫn chạy và `performSideEffect()` vẫn có thể được gọi sau yêu cầu hủy. Nếu vòng này chạy vô hạn, worker có thể không bao giờ dừng.

Cũng nguy hiểm khi catch rồi chỉ ghi log:

~~~java
// SAI nếu không có chính sách xử lý hủy khác.
catch (InterruptedException ex) {
    logger.warn("Interrupted", ex);
}
// Tiếp tục làm việc sau catch.
~~~

**Logging không phải xử lý hủy.** Một log line không khôi phục interrupt status, không truyền exception, không ngừng side effect và không báo caller rằng task đã kết thúc.

### Vì sao cờ bị mất?

Trình tự phổ biến:

~~~text
Ban đầu: interrupt flag = false
Caller: worker.interrupt()       -> flag = true
Worker: Thread.sleep(...)        -> InterruptedException
                                   flag được clear trước khi catch
Worker: catch rỗng              -> flag vẫn false
Worker: poll isInterrupted()     -> false
Worker: tiếp tục công việc       -> yêu cầu hủy bị mất
~~~

Nếu một tầng code **chủ động tiêu thụ** yêu cầu hủy theo hợp đồng riêng, việc không restore có thể hợp lý. Nhưng “catch vì compiler bắt buộc” rồi bỏ qua không phải xử lý có chủ ý.

## 4. Ba lựa chọn xử lý InterruptedException

### 4.1. Lựa chọn A: truyền exception lên caller

Ưu tiên khi method có thể khai báo `throws InterruptedException`:

~~~java
// Mã minh họa, không phải chương trình độc lập.
void waitForMoreWork() throws InterruptedException {
    queue.take();
}
~~~

Caller nhận rõ tín hiệu rằng việc chờ bị ngắt, có thể dừng task, hủy workflow hoặc xử lý theo tầng sở hữu công việc. Thường **không cần** tự restore flag trước khi propagate, vì bản thân exception đã mang thông tin điều khiển.

Nếu cần cleanup tại tầng hiện tại, dùng `finally`:

~~~java
// Mã minh họa trong method có hợp đồng throws; không độc lập.
void process() throws InterruptedException {
    acquireResource();
    try {
        doInterruptibleStep();
    } finally {
        releaseResource();
    }
}
~~~

`finally` chạy khi exception được truyền lên (trừ các tình huống chấm dứt JVM bất thường). Cleanup cũng có thể ném exception khác; cần thiết kế để không vô tình che mất lỗi/ngắt quan trọng.

### 4.2. Lựa chọn B: không thể throws, restore flag và thoát

`Runnable.run()` không khai báo checked `InterruptedException`. Mẫu thường dùng:

~~~java
// Mẫu Runnable, không phải chương trình độc lập.
Runnable task = () -> {
    try {
        doInterruptibleWork();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
};
~~~

Khôi phục cờ bằng `Thread.currentThread().interrupt()` cho phép code khác trong thread có cơ hội nhận biết. **`return` rất quan trọng** khi ý định là hủy tác vụ; nếu chỉ restore rồi tiếp tục vòng lặp hoặc làm side effect thì task chưa thực sự tôn trọng yêu cầu hủy.

Một cách khác là ném một unchecked exception có semantics cancellation được API của bạn định nghĩa, nhưng phải chú ý cleanup, logging và hợp đồng báo lỗi. Không tùy tiện biến mọi interrupt thành một lỗi nghiệp vụ thông thường.

### 4.3. Lựa chọn C: xử lý hoàn toàn theo giao thức cụ thể

Đôi khi một tầng *có trách nhiệm sở hữu quyết định hủy* và chủ động thực hiện một hành động nhất quán rồi tiếp tục, chẳng hạn một vòng quản lý dịch vụ cần đóng một phiên làm việc, báo trạng thái và chuyển sang pha khác. Khi đó:

- Phải xác định rõ **ai sở hữu interrupt policy**.
- Không trả kết quả như thể công việc cũ đã thành công.
- Tài liệu hóa vì sao clear flag là cố ý và vì sao không phải propagate/restore.
- Đảm bảo code tầng trên không còn cần nhận tín hiệu đó.
- Tránh tạo vòng lặp bỏ qua vô hạn mọi interrupt.

Đây là lựa chọn có điều kiện, **không** phải lý do để dùng catch rỗng mặc định.

## 5. Ví dụ 1 — so sánh nuốt và khôi phục flag (Java 17+)

Ví dụ chạy ngay trong main để không phụ thuộc lịch scheduler. Chương trình cố tình minh họa **một hành vi sai** rồi cách restore đúng.

Tạo tệp `SwallowVsRestoreDemo.java`:

~~~java
public class SwallowVsRestoreDemo {
    public static void main(String[] args) {
        Thread.currentThread().interrupt();

        try {
            Thread.sleep(10);
        } catch (InterruptedException ignored) {
            // SAI: minh họa tín hiệu bị nuốt.
        }

        System.out.println(
            "after swallow = "
                + Thread.currentThread().isInterrupted()
        );

        Thread.currentThread().interrupt();

        try {
            Thread.sleep(10);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }

        System.out.println(
            "after restore = "
                + Thread.currentThread().isInterrupted()
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SwallowVsRestoreDemo.java
java SwallowVsRestoreDemo
~~~

Stdout chính xác trên luồng main trong hoàn cảnh ví dụ:

~~~text
after swallow = false
after restore = true
~~~

Lần `sleep(10)` đầu gặp cờ interrupt đã đặt và ném `InterruptedException`; JVM clear flag. Catch rỗng khiến lần `isInterrupted()` sau đó trả false. Lần thứ hai, catch khôi phục flag nên lần đọc sau trả true.

**Lưu ý:** Ví dụ cố ý để flag của main ở true lúc kết thúc để dễ quan sát; trong chương trình thực cần policy rõ ràng của thread sở hữu thực thi. Dòng `Thread.sleep(10)` không dùng làm cơ chế đồng bộ thời gian, mà chỉ là một điểm chờ interruptible có thể thử trực tiếp.

## 6. Ví dụ 2 — propagate InterruptedException lên tầng gọi (Java 17+)

Tạo tệp `PropagateInterruptDemo.java`:

~~~java
public class PropagateInterruptDemo {
    static void waitForStep() throws InterruptedException {
        Thread.sleep(1000);
    }

    static void runStep() throws InterruptedException {
        waitForStep(); // Không che mất InterruptedException.
    }

    public static void main(String[] args) {
        Thread.currentThread().interrupt();

        try {
            runStep();
            System.out.println("unexpected completion");
        } catch (InterruptedException ex) {
            System.out.println("caller received interruption");
            System.out.println(
                "flag in catch = "
                    + Thread.currentThread().isInterrupted()
            );
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PropagateInterruptDemo.java
java PropagateInterruptDemo
~~~

Stdout chính xác:

~~~text
caller received interruption
flag in catch = false
~~~

`runStep()` không sở hữu quyết định hủy nên chỉ khai báo `throws InterruptedException` và cho exception đi lên. `main` nhận ngoại lệ, thấy cờ đã clear khi được sleep thông báo, rồi restore vì đây là rìa xử lý của ví dụ.

Một lưu ý thiết kế: nếu code cần cleanup và cleanup có thể bị interrupt, hãy suy nghĩ kỹ **thứ tự restore flag**. Nếu restore quá sớm rồi gọi một phép chờ interruptible trong cleanup, phép chờ đó có thể ném ngay. Đừng chỉ copy-paste công thức mà không xem việc giải phóng tài nguyên cụ thể.

## 7. Ví dụ 3 — worker phản hồi hủy và chạy cleanup (Java 17+)

Ta sẽ dùng `CountDownLatch` để xác nhận worker đi vào vùng chờ và cleanup được thực hiện, không dùng `sleep` trong main để đoán thời điểm worker đã chạy.

Tạo tệp `CooperativeCleanupDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeCleanupDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch cleaned = new CountDownLatch(1);
        AtomicBoolean cancellationObserved = new AtomicBoolean();
        AtomicBoolean flagRestored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try {
                entered.countDown();
                for (;;) {
                    Thread.sleep(1000);
                }
            } catch (InterruptedException ex) {
                cancellationObserved.set(true);
                Thread.currentThread().interrupt();
                flagRestored.set(
                    Thread.currentThread().isInterrupted()
                );
            } finally {
                cleaned.countDown();
            }
        }, "cleanup-worker");

        worker.start();
        entered.await();

        worker.interrupt();
        worker.join();
        cleaned.await();

        System.out.println(
            "cancellation observed = " + cancellationObserved.get()
        );
        System.out.println("flag restored = " + flagRestored.get());
        System.out.println("cleanup reached = true");
        System.out.println("worker stopped = " + !worker.isAlive());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CooperativeCleanupDemo.java
java CooperativeCleanupDemo
~~~

Stdout khi không có lỗi ngoại lai:

~~~text
cancellation observed = true
flag restored = true
cleanup reached = true
worker stopped = true
~~~

Phân tích:

1. Worker đếm `entered` trước khi tới vòng sleep. Caller chờ latch rồi mới gửi interrupt.
2. Nếu interrupt đến **trước** lần sleep đầu tiên, sleep nhận cờ đã đặt và ném `InterruptedException`; nếu đến **trong khi** sleep, lời chờ bị ngắt.
3. Worker ghi nhận đã quan sát cancellation, restore flag rồi đi vào `finally`, báo đã tới cleanup.
4. Main `join()` để chờ worker kết thúc rồi mới in các biến kết quả.
5. `AtomicBoolean` cho phép lưu các cờ kết quả an toàn trong ví dụ; `join()` còn cung cấp quan hệ happens-before đối với những hành động trước khi worker kết thúc.

**Không hiểu sai “cleanup reached”:** ví dụ chỉ chứng minh `finally` đã chạy và đếm latch, không giả vờ rằng file/network/database nào đó đã được đóng. Trong ứng dụng thực, đặt các thao tác giải phóng tài nguyên tại `finally` hoặc try-with-resources và xác định cách báo lỗi cleanup riêng.

### Cleanup khi có cả InterruptedException và exception khác

Nếu `close()` hoặc cleanup có thể ném exception khác, lỗi cleanup có thể **che** ngoại lệ ban đầu nếu không quản lý cẩn thận. Try-with-resources giúp giữ các exception bị suppress theo ngữ nghĩa Java phù hợp. Với giao thức hủy, cần bảo đảm hai thông tin không bị bỏ mất: yêu cầu cancel và lỗi dọn dẹp thật sự quan trọng.

## 8. Ví dụ 4 — BlockingQueue.take() và xử lý interrupt (Java 17+)

`BlockingQueue.take()` là primitive chờ có thể ngắt. Khi chưa có item, consumer nên chờ thay vì bận spin; khi bị hủy, consumer phải kết thúc hoặc trả cancellation theo hợp đồng.

Tạo tệp `InterruptibleQueueDemo.java`:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptibleQueueDemo {
    public static void main(String[] args)
            throws InterruptedException {
        BlockingQueue<Integer> queue =
            new LinkedBlockingQueue<>();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean noticed = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread consumer = new Thread(() -> {
            entered.countDown();

            try {
                Integer item = queue.take();
                System.out.println("item = " + item);
            } catch (InterruptedException ex) {
                noticed.set(true);
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        }, "queue-consumer");

        consumer.start();
        entered.await();

        consumer.interrupt();
        consumer.join();

        System.out.println("noticed = " + noticed.get());
        System.out.println("restored = " + restored.get());
        System.out.println("queue empty = " + queue.isEmpty());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InterruptibleQueueDemo.java
java InterruptibleQueueDemo
~~~

Stdout khi không có tác động ngoài ví dụ:

~~~text
noticed = true
restored = true
queue empty = true
~~~

Queue luôn trống và không có producer nào thêm phần tử; consumer không thể lấy item, nên câu lệnh in `item = ...` không chạy trong thực thi hợp lệ của ví dụ. Caller gửi interrupt sau khi consumer đã vào vùng xử lý. Nếu interrupt đến trước `take()`, `take()` nhận trạng thái đó và phản hồi bằng `InterruptedException`; nếu đến khi đang chờ, chờ bị ngắt.

Worker catch exception, ghi nhận yêu cầu hủy, khôi phục flag rồi rời khỏi task. Caller `join()` trước khi đọc kết quả. Đừng nhầm `Thread.interrupted()` (test-and-clear) với cách kiểm tra cờ trong catch; `Thread.currentThread().isInterrupted()` chỉ đọc và không xóa.

**Nếu queue có item và task được phép kết thúc bình thường trước yêu cầu cancel**, output có thể khác. Ví dụ cố ý không có producer để tập trung vào cơ chế interrupt của `take()`.

## 9. Không phải mọi phương thức blocking phản ứng giống nhau

| API/chỗ chờ | Phản ứng với interrupt điển hình | Điều cần nhớ |
| --- | --- | --- |
| `Thread.sleep()` | Ném `InterruptedException`, clear flag | Không nhả intrinsic monitor thread đang giữ |
| `Object.wait()` | Ném `InterruptedException`, clear flag và reacquire monitor trước khi thoát | Phải giữ đúng monitor; chờ trong `while` |
| `Thread.join()` | Thread **gọi join** có thể nhận `InterruptedException` | Không tự interrupt thread đang được join |
| `CountDownLatch.await()` | Ném `InterruptedException` | Không tự đặt count về 0 |
| `BlockingQueue.take()/put()` | Có thể ném `InterruptedException` khi chờ | Task xử lý state queue đúng contract |
| `Condition.await()` | Có thể ném `InterruptedException`, reacquire associated lock | Vẫn kiểm tra predicate trong while |
| `Semaphore.acquire()` | Có thể ném `InterruptedException` | Giải phóng permit đã acquire riêng |
| `ReentrantLock.lockInterruptibly()` | Chờ lấy lock có thể bị ngắt | Chỉ unlock nếu đã acquire |
| `ReentrantLock.lock()` | Không dừng chờ chỉ vì interrupt | Flag có thể còn để xử lý sau |
| Chờ **vào `synchronized`** | Không có `InterruptedException` chỉ vì chờ monitor | Interrupt không ép lấy hoặc release monitor |
| `Future.cancel(true)` | Yêu cầu hủy, có thể interrupt worker | Best effort, không bảo đảm task sạch ngay |
| `CompletableFuture.cancel(true)` | Theo API, tham số `mayInterruptIfRunning` không dùng để điều khiển thực thi | Không xem nó là yêu cầu interrupt tới underlying computation |

Các I/O API có ngữ nghĩa khác nhau. Một số interruptible channel trong NIO có thể bị đóng và phát sinh `ClosedByInterruptException`; một số loại socket, stream hoặc native blocking I/O khác có giới hạn riêng. Không hứa “mọi I/O đều thoát khi interrupt” nếu chưa kiểm tra chính xác Javadoc của tài nguyên đó.

### Vì sao sleep không phù hợp làm đồng bộ?

Caller ngủ 100ms rồi kiểm tra worker có còn chạy hay không không xác nhận worker đã đi vào điểm interruptible. Với test, dùng `CountDownLatch`, `CyclicBarrier`, `Future` hoặc kênh trạng thái rõ ràng. Ngược lại, `Thread.sleep` trong *worker* là một điểm chờ interruptible hợp lệ khi thật sự cần chờ thời gian.

## 10. Future.cancel(true): trạng thái hủy và lifecycle worker khác nhau

Khi dùng executor, caller thường không trực tiếp giữ `Thread` instance của worker. `Future.cancel(true)` yêu cầu hủy task, và nếu task đang chạy, có thể interrupt thread thực thi nó.

**Không đồng nhất:**

- `future.cancel(true) == true`: request hủy được Future chấp nhận theo hợp đồng API.
- `future.isCancelled() == true`: Future được đánh dấu hủy.
- **Code worker đã vào catch/cleanup**: một sự kiện thực thi khác.
- **Tài nguyên đã được giải phóng**: cần xác nhận theo API tài nguyên.
- **Một nghiệp vụ ngoài JVM đã rollback**: không được suy ra từ interrupt.

### Ví dụ 5 — Future cancel và xác nhận cleanup riêng (Java 17+)

Tạo tệp `FutureCancelCleanupDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelCleanupDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawCancellation = new AtomicBoolean();

        try {
            Future<?> future = executor.submit(() -> {
                entered.countDown();
                try {
                    for (;;) {
                        Thread.sleep(1000);
                    }
                } catch (InterruptedException ex) {
                    sawCancellation.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            entered.await();
            boolean cancelAccepted = future.cancel(true);
            finished.await();

            System.out.println("cancel accepted = " + cancelAccepted);
            System.out.println("future cancelled = " + future.isCancelled());
            System.out.println("task caught interrupt = "
                + sawCancellation.get());
            System.out.println("cleanup reached = true");
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                System.out.println("executor still shutting down");
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FutureCancelCleanupDemo.java
java FutureCancelCleanupDemo
~~~

Stdout khi task và executor hoàn tất bình thường theo thiết kế:

~~~text
cancel accepted = true
future cancelled = true
task caught interrupt = true
cleanup reached = true
~~~

`entered` khiến main yêu cầu hủy khi task đã bắt đầu chạy. Task không tự hoàn thành nếu không có interrupt, vì vòng sleep là vô hạn. `cancel(true)` gửi yêu cầu hủy tới task đang chạy; `sleep` phản hồi bằng ngoại lệ. `finished.await()` quan sát đường code cuối của task, tách khỏi trạng thái Future.

Không dùng `future.get()` sau cancel để mong nhận kết quả tính toán bình thường: nó có thể ném `CancellationException` theo contract. `Future.isDone()` và `isCancelled()` không tự bảo đảm mọi side effect bên ngoài đã kết thúc.

### Executor shutdown

- `shutdown()` không nhận task mới và đợi các task cũ được xử lý theo cơ chế shutdown; **không yêu cầu interrupt tất cả task đang chạy**.
- `shutdownNow()` cố ngắt task đang chạy và trả về các task chưa bắt đầu; đó là **best effort**.
- `awaitTermination(timeout, unit)` cho caller đợi kết thúc executor trong một khoảng thời gian; timeout không bảo đảm mọi task đã dừng.

Một task nuốt `InterruptedException` có thể làm cả shutdown trở nên rất khó dự đoán, ngay cả khi caller đã gọi `shutdownNow()`.

## 11. Mẫu cleanup: khôi phục cờ ở đâu cho an toàn?

Khuyến nghị “catch rồi `Thread.currentThread().interrupt()`” rất hữu ích, nhưng thứ tự cleanup quan trọng.

### 11.1. Cleanup không cần chờ interruptible

~~~java
// Mẫu minh họa trong Runnable, không phải chương trình độc lập.
try {
    doBlockingWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} finally {
    closeOwnedNonBlockingResources();
}
~~~

Khi cleanup chắc chắn không phụ thuộc một lời chờ interruptible và luôn xử lý được tài nguyên, mẫu này tương đối đơn giản. Nhưng nếu việc đóng tài nguyên có thể chặn hoặc ném exception, cần thiết kế thêm.

### 11.2. Cleanup cần một phép chờ interruptible

Nếu restore flag ngay, một `Thread.sleep`, `BlockingQueue.put` hoặc `Condition.await` trong cleanup có thể ném ngay vì flag đang set. Đôi khi cần **hoãn restore đến sau cleanup**:

~~~java
// Mẫu minh họa, không phải chương trình độc lập.
// Giả sử cleanup() không che lỗi nghiêm trọng và có giới hạn thời gian.
boolean interrupted = false;
try {
    doBlockingWork();
} catch (InterruptedException ex) {
    interrupted = true;
} finally {
    try {
        cleanup();
    } finally {
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Mẫu trên đặt restore trong `finally` lồng nhau, nên kể cả khi `cleanup()` ném exception, flag vẫn được khôi phục. Tuy nhiên, **exception của cleanup có thể trở thành exception cuối cùng**: trong code thực cần báo/ghép lỗi theo API đang sử dụng. Nếu cleanup cũng bị interrupt, phải xét **cả hai tín hiệu** và chính sách retry/timeout thích hợp. Không cố chờ vô hạn chỉ để cleanup “cho xong”, đặc biệt khi ứng dụng đang shutdown.

### 11.3. Try-with-resources

Nếu thao tác mở tài nguyên được biểu diễn bằng `AutoCloseable`, try-with-resources giúp bảo đảm `close()` được gọi khi rời scope, kể cả lúc có exception. Exception từ `close()` có thể được ghi dưới dạng **suppressed exception** nếu đã có exception chính.

Dù vậy, try-with-resources **không tự restore interrupt status** sau `InterruptedException`; caller vẫn cần propagate hoặc xử lý cờ theo hợp đồng. Đối với tài nguyên bên ngoài, việc gọi `close()` cũng không phải lúc nào là hành động tức thời hoặc không thể lỗi.

## 12. Những bẫy nâng cao thường làm mất tín hiệu hủy

### 12.1. Catch Exception rộng và retry sai

~~~java
// SAI: mẫu minh họa, không phải chương trình độc lập.
while (true) {
    try {
        doBlockingWork();
        break;
    } catch (Exception ex) {
        log(ex);
        // Retry mọi lỗi, kể cả InterruptedException.
    }
}
~~~

`InterruptedException` là subclass của `Exception`, nên một catch rộng có thể vô tình nuốt tín hiệu. Nếu cần retry những lỗi tạm thời, **tách catch InterruptedException trước**:

~~~java
// Mẫu minh họa, không phải chương trình độc lập.
try {
    doBlockingWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (TransientFailure ex) {
    scheduleRetryIfAllowed(ex);
}
~~~

`TransientFailure` ở đây là loại exception nghiệp vụ giả định. Đừng coi ngắt là lỗi mạng để retry tự động, vì chính chủ sở hữu task có thể đang yêu cầu dừng.

### 12.2. Utility method trả default value sau interrupt

~~~java
// SAI nếu caller xem giá trị mặc định là kết quả hợp lệ.
String readValue() {
    try {
        return blockingRead();
    } catch (InterruptedException ignored) {
        return "";
    }
}
~~~

Trả chuỗi rỗng làm tầng gọi tưởng đọc thành công và có thể ghi dữ liệu sai. Nếu không thể throws, cần API diễn đạt rõ “đã hủy” như kết quả có trạng thái, callback hủy, unchecked cancellation phù hợp hoặc restore flag và dừng theo thiết kế.

### 12.3. Gọi Thread.interrupted() trong logging

~~~java
// Nguy hiểm nếu chỉ định quan sát:
boolean interrupted = Thread.interrupted();
~~~

Phương thức trên **xóa cờ current thread**. Nếu chỉ muốn hỏi có bị interrupt hay không, dùng `Thread.currentThread().isInterrupted()`. Không dùng `worker.interrupted()` để quan sát worker, vì đây vẫn là static method tác động đến current thread.

### 12.4. Catch InterruptedException rồi tiếp tục khóa

Khi một thread đợi `lockInterruptibly()` và bị interrupt, nó **không lấy được lock bằng lần chờ đó**. Không được gọi `unlock()` nếu chưa acquire. Mẫu đúng:

~~~java
// Mẫu minh họa, lock là ReentrantLock.
try {
    lock.lockInterruptibly();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
try {
    mutateSharedState();
} finally {
    lock.unlock();
}
~~~

Trong khi đó `ReentrantLock.lock()` và chờ **vào `synchronized`** không tự thoát chỉ vì có interrupt; việc restore flag không “phá khóa”. Cần lựa chọn primitive và thứ tự lock phù hợp từ đầu.

### 12.5. Interrupt khi đang giữ intrinsic monitor

`Thread.sleep(...)` **không** nhả monitor thread đang giữ. Một worker ngủ trong `synchronized(lock)` có thể làm thread khác chờ lock, dù bản thân nó bị interrupt và đi vào catch. Không thiết kế chờ I/O hoặc sleep dài trong critical section nếu có thể tránh.

`Object.wait()` thì nhả monitor của object dùng để wait, sau đó reacquire trước khi thoát. Khi `wait()` bị ngắt và ném `InterruptedException`, bạn vẫn phải kiểm tra và bảo vệ invariant trong vùng monitor tương ứng. Không suy luận mọi phương thức chờ đều có hành vi nhả khóa giống nhau.

### 12.6. Nuốt interrupt trong thư viện không thuộc quyền sở hữu

Một utility được gọi từ executor có thể không biết toàn bộ lifecycle của task. Nếu utility bắt `InterruptedException` rồi bỏ qua, caller có thể không còn cơ hội áp dụng chính sách hủy. Với thư viện dùng chung, mặc định nên **propagate** khi có thể; nếu API không cho, khôi phục cờ và báo status rõ ràng thay vì áp đặt tiếp tục.

### 12.7. Multiple interrupts và cờ boolean

Interrupt status là **một trạng thái**, không phải hàng đợi tích lũy số lần interrupt. Gọi `interrupt()` nhiều lần không tạo ra nhiều “token” tương ứng để tiêu thụ từng cái. `Thread.interrupted()` clear cờ một lần và không chứng minh chỉ có duy nhất một request từng xảy ra.

Nếu cần đếm yêu cầu, lưu lý do hủy, phân biệt deadline và user cancel, hoặc truyền nhiều sự kiện, hãy sử dụng **giao thức trạng thái riêng** như message queue, atomic state machine hoặc cancellation token chuyên biệt, không phụ thuộc vào số lần flag đổi.

## 13. Khi nào không restore flag?

Không nên biến nguyên tắc “restore flag” thành công thức máy móc trong mọi tầng:

1. **Method khai báo `throws InterruptedException`:** truyền exception lên thường đủ; không phải luôn restore trước khi throws.
2. **Tầng sở hữu quyết định hủy đã xử lý đầy đủ:** có thể chủ ý tiêu thụ tín hiệu nếu hợp đồng cho phép, nhưng phải giữ correctness và thông báo trạng thái phù hợp.
3. **Đã quyết định kết thúc task bằng exception/hủy rõ ràng:** việc restore thêm có thể hữu ích hoặc không tùy contract executor/tầng gọi; không dựa vào flag như kênh duy nhất.
4. **Cleanup cần chờ interruptible:** cân nhắc trì hoãn restore đến sau cleanup, tránh gây lỗi ngay tại lời chờ.
5. **Một exception khác đang xảy ra đồng thời:** quản lý thứ tự ưu tiên lỗi, suppressed exceptions và tính chất cancellation mà ứng dụng yêu cầu.

Mấu chốt là **đừng âm thầm đánh mất yêu cầu hủy**; truyền bằng exception, cờ, kết quả có trạng thái hoặc kênh phối hợp rõ ràng đều có thể là một phần thiết kế đúng nếu ownership nhất quán.

## 14. Kiểm thử để phát hiện mất tín hiệu hủy

### 14.1. Những kịch bản cần có

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Interrupt đến **trước** khi gọi sleep/take/await | Phép chờ phản hồi theo hợp đồng; task không tiếp tục như thường |
| Interrupt đến **trong lúc** chờ | Task nhận exception hoặc tín hiệu theo API |
| Catch không thể throws | Restore flag hoặc truyền trạng thái hủy rõ, không tiếp tục side effect |
| Utility method có `throws InterruptedException` | Caller nhận exception, không bị che bởi catch rộng |
| Executor `cancel(true)` | Task có cơ hội hợp tác và đạt cleanup, không chỉ Future state |
| Cleanup có exception | Không che mất thông tin quan trọng về cancel và lỗi cleanup |
| CPU-bound worker | Poll `isInterrupted()` giữa đơn vị công việc hữu hạn |
| Worker không chịu dừng | Test timeout, thu thập thread dump; không treo cả suite |
| Dữ liệu dùng chung | Invariant vẫn đúng sau hủy một phần công việc |
| I/O không phản ứng ngắt | Chính sách timeout/close theo API cụ thể |

### 14.2. Không dùng sleep để phỏng đoán lịch chạy

Sai lầm phổ biến là main tạo worker, ngủ 50ms rồi gửi interrupt, sau đó giả định worker chắc chắn đang ở `queue.take()`. Trên máy chậm hoặc CI bận, thứ tự có thể khác.

Dùng `CountDownLatch` hoặc primitive phối hợp để đánh dấu worker đã tới một điểm được xác định, rồi hủy. Tuy nhiên, một latch đặt ngay **trước** blocking operation chỉ bảo đảm worker đến vùng code đó, không chứng minh nó đã thực sự block; ví dụ trong bài được thiết kế để cả hai thời điểm interrupt trước và trong lời chờ đều dẫn tới một kết quả nhất quán.

### 14.3. Tách “future cancelled” khỏi “worker cleanup done”

Dùng hai điểm quan sát nếu nghiệp vụ cần cả hai:

- `future.isCancelled()` cho biết trạng thái hủy của Future theo contract.
- Một latch/kênh kết quả do worker phát ra sau cleanup cho biết code đã đạt mốc hoàn thành.

Không nhầm `Future.get()` bị `CancellationException` với bằng chứng tài nguyên bên ngoài đã được đóng. Nếu worker bỏ qua interrupt, nó có thể còn chạy dù Future đã bị hủy.

### 14.4. Quan sát production

- Log **lý do cancel**, thời điểm gửi yêu cầu, thời điểm worker nhận, và kết quả cleanup, thay vì chỉ log một cờ có thể clear.
- Đo thời gian từ khi yêu cầu hủy tới khi task hoàn tất; thống kê tỉ lệ task vượt deadline.
- Kiểm tra pool có shutdown đúng thời hạn, thread nào vẫn `RUNNABLE`/`WAITING`/`BLOCKED` và chúng chờ API nào.
- Với I/O, theo dõi timeout, đóng connection/channel và xử lý side effect bất định, thay vì giả định interrupt luôn có tác dụng ngay.
- Không cố sửa bằng `Thread.stop()`: ép dừng thread ở điểm bất kỳ có thể phá bất biến; API này không an toàn.

## 15. Checklist khi code review

- Code nào bắt `InterruptedException`? **Mỗi catch có một quyết định hủy rõ ràng** chưa?
- Method nào có thể `throws InterruptedException`? Có truyền lên thay vì tự ý nuốt không?
- Trong `Runnable`/callback không thể throws, có restore flag hoặc kênh trạng thái hủy phù hợp và **thoát** không?
- Có catch `Exception`/`Throwable` rộng nuốt tín hiệu của API blocking không?
- Có utility “đọc lỗi thì trả default” che mất `InterruptedException` không?
- Có lời gọi `Thread.interrupted()` ở chỗ chỉ định quan sát, làm clear flag ngoài ý muốn không?
- Có nhầm `worker.interrupted()` là truy vấn worker thay vì current thread không?
- Có retry loop tiếp tục chạy sau khi bị hủy không? Có kiểm tra `isInterrupted()` ở điểm phù hợp không?
- Cleanup có giữ lock quá lâu, thực hiện I/O vô hạn hoặc yêu cầu chờ interruptible sau khi đã restore flag không?
- `lockInterruptibly()` thất bại có thể dẫn tới `unlock()` sai không?
- Với Future, có phân biệt request cancel, trạng thái Future và hoàn tất side effect/cleanup không?
- Có timeout, interrupt, shutdown path và test để không mắc kẹt vô thời hạn không?
- Có xử lý trạng thái nghiệp vụ bị cập nhật dở khi hủy giữa một workflow không?
- Đã chọn API blocking có contract interrupt phù hợp hoặc một lối hủy riêng cho I/O chưa?

## 16. Câu hỏi tự kiểm tra

**1.** Vì sao đoạn `catch (InterruptedException ignored) {}` thường khiến worker không dừng?

Phép chờ thường đã clear interrupt flag khi ném exception. Catch rỗng làm mất tín hiệu và worker tiếp tục chạy nếu không có một cơ chế hủy khác.

**2.** Một helper có thể `throws InterruptedException`. Nên khôi phục cờ rồi mới ném lại không?

Thông thường helper chỉ cần **propagate** exception. Tầng caller nhận tín hiệu và có trách nhiệm quyết định. Restore trước khi throws không phải quy tắc bắt buộc, và có thể ảnh hưởng cleanup ở tầng trên.

**3.** Vì sao trong `Runnable.run()` thường dùng `Thread.currentThread().interrupt()` khi bắt `InterruptedException`?

`run()` không khai báo checked exception đó. Restore flag cho tầng khác có cơ hội quan sát yêu cầu, và task thường phải thoát/cancel theo hợp đồng.

**4.** Gọi `Thread.interrupted()` trong một câu log có nguy cơ gì?

Nó đọc **và xóa** interrupt flag của current thread. Nếu chỉ muốn quan sát mà không sửa trạng thái, dùng `Thread.currentThread().isInterrupted()`.

**5.** `Future.cancel(true)` trả true. Có chắc worker đã chạy cleanup và đóng file không?

Không. Trạng thái Future không đồng nghĩa toàn bộ code worker và side effect đã kết thúc. Dùng kênh xác nhận riêng nếu cần.

**6.** Sau khi restore flag, code bắt đầu gọi `BlockingQueue.take()` để đẩy thông điệp cleanup. Điều gì cần chú ý?

`take()` là interruptible; khi flag đã set, nó có thể ném `InterruptedException` ngay. Cần lập kế hoạch cleanup và chọn cách thông báo/đợi phù hợp trước khi restore hoặc tránh chờ dài trong cleanup.

**7.** Main bị interrupt khi đang chờ `worker.join()`. Thread nào nhận `InterruptedException`?

**Main**, tức thread đang gọi join. Worker không tự động nhận interrupt chỉ vì caller bị ngắt. Caller phải quyết định có gửi yêu cầu hủy riêng tới worker hay không.

**8.** Một thread chờ để vào `synchronized(lock)`. Gọi interrupt có ép nó dừng chờ monitor không?

Không. Việc chờ intrinsic monitor không phải một thao tác chờ interruptible như `ReentrantLock.lockInterruptibly()`. Interrupt có thể đặt cờ nhưng không tự lấy hoặc nhả monitor.

**9.** Có tình huống nào không restore flag là đúng không?

Có, nếu một tầng sở hữu hủy đã **chủ động xử lý hoàn toàn tín hiệu** theo hợp đồng rõ ràng hoặc đang propagate exception. Điều cấm kỵ là vô tình đánh mất yêu cầu mà bên khác vẫn dựa vào.

**10.** Cần chứng minh điều gì để nói một tác vụ đã được hủy an toàn?

Task đã nhận hoặc xử lý yêu cầu hủy theo contract, giữ được invariant, giải phóng tài nguyên cần thiết, có kết quả/trạng thái hủy rõ ràng và không còn thực hiện side effect trái phép sau khi hoàn tất. Chỉ có cờ Future hoặc lời gọi `interrupt()` chưa đủ.

**Ghi nhớ:** `InterruptedException` không phải một ngoại lệ phiền phức để catch rồi bỏ qua. Nó là tín hiệu điều khiển về yêu cầu hủy. Hãy **propagate** khi có thể; **restore interrupt status và thoát** khi không thể truyền tiếp; chỉ **tiêu thụ có chủ ý** nếu tầng hiện tại thật sự sở hữu chính sách hủy. Luôn phối hợp cleanup, invariant và xác nhận hoàn thành bằng cơ chế phù hợp.