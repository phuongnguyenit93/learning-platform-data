# Kiểm thử ngắt bằng phối hợp luồng xác định thay vì chỉ `sleep`

Kiểm thử `Thread.interrupt()`, `InterruptedException` và hủy tác vụ trong Java dễ trở nên **flaky** nếu test khởi tạo worker, gọi `Thread.sleep(100)` rồi đoán rằng worker đã kịp chạy đến đúng vị trí. Trên máy phát triển, 100 ms có vẻ đủ; trên CI đang tải cao, scheduler có thể chưa cấp CPU cho worker. Ngược lại, trên máy nhanh, worker có thể hoàn thành trước khi test gửi interrupt.

Để kiểm thử đáng tin, hãy **phối hợp luồng bằng những tín hiệu có ngữ nghĩa rõ ràng**, thường là `CountDownLatch`, `BlockingQueue`, `Future`, `Semaphore` hoặc đồng bộ tương đương. Mục tiêu không phải ép hai thread chạy ở một thứ tự ngẫu nhiên được quan sát, mà là tạo quan hệ **“bước này xảy ra trước bước kia”** và khẳng định **kết quả theo hợp đồng**.

Bài thuộc **Java Core – Exception / Kiểm thử**, dùng Java 17+. Nội dung gồm ví dụ Java độc lập chạy bằng `javac`/`java`, ví dụ JUnit 5 có dependency riêng, tình huống `InterruptedException` xóa cờ interrupt, phân biệt ngắt caller và worker, và những cách tránh test treo hoặc sai logic.

## 1. Vì sao `Thread.sleep(...)` không phải cơ chế đồng bộ kiểm thử?

Mẫu test dễ gặp:

```java
Thread worker = new Thread(() -> {
    doSomeWork();
    waitForNextItem();
});

worker.start();
Thread.sleep(100);
worker.interrupt();
```

Đây là **mảnh mã minh họa**, không chạy độc lập vì `doSomeWork()` và `waitForNextItem()` chưa được định nghĩa. `sleep(100)` chỉ yêu cầu **thread đang gọi nó** nghỉ ít nhất xấp xỉ khoảng thời gian đó, không tạo cam kết rằng **worker** đã chạy, đã xong khởi tạo hoặc đang chờ ở thao tác muốn kiểm thử.

Các nguồn không xác định:

- Hệ điều hành và JVM tự lập lịch thread; `start()` không đợi `run()` đi tới một dòng cụ thể.
- CPU/CI có thể đang bận, máy ảo có thể tạm ngừng hoặc bị nhiễu bởi GC.
- Worker có thể kết thúc quá sớm, khiến `interrupt()` chỉ tác động lên thread không còn chạy.
- Worker có thể mới bắt đầu, chưa vào thao tác chờ, nên assertion kiểm tra trạng thái `WAITING` sẽ không đáng tin.
- `sleep` kéo dài suite mà không chứng minh thêm điều kiện logic.
- Tăng từ 100 ms lên 2 giây làm giảm xác suất race trong một vài môi trường, **không loại bỏ** race.

Cần phân biệt hai ý:

1. **Dùng sleep để đoán trạng thái** là anti-pattern của test đồng thời.
2. **Dùng timeout để giới hạn thời gian chờ** là kỹ thuật an toàn cần thiết. `latch.await(2, TimeUnit.SECONDS)` không dùng 2 giây để *giả định* worker đã sẵn sàng; nó chờ một **tín hiệu cụ thể** và thất bại rõ ràng nếu tín hiệu không đến.

Không phải `Thread.sleep` luôn sai. Nó phù hợp nếu **hành vi cần kiểm tra chính là ngủ hoặc xử lý thời gian**. Nhưng nó không nên là cách xác lập thứ tự giữa các thread trong phần lớn test interrupt.

## 2. Thiết kế test theo các sự kiện có thể quan sát

Một test interrupt tốt thường có các pha:

```text
                    Thread test                 Thread worker
                       |                             |
                 tạo latch và worker                 |
                       |                             |
                  worker.start() ------------------> run()
                       |                             |
                  ready.await()  <---------------- ready.countDown()
                       |                             |
                worker.interrupt() -----------------> tín hiệu ngắt
                       |                             |
                  done.await() <------------------- done.countDown()
                       |                             |
                kiểm tra trạng thái / kết quả
```

Các tín hiệu quan trọng:

- **`ready`**: worker đã đi đến một mốc xác định do test đặt.
- **`interrupt()`**: test gửi yêu cầu ngắt đến đúng đối tượng `Thread`.
- **`done`** hoặc `join()`**:** worker đã thực hiện phần kết thúc cần quan sát.
- **Assertion**: kiểm tra một kết quả có ngữ nghĩa, ví dụ worker bắt `InterruptedException`, cờ interrupt được khôi phục, không còn chạy, hoặc `Future` báo canceled.

Một `CountDownLatch` bắt đầu ở 1:

```java
CountDownLatch ready = new CountDownLatch(1);

// Trong worker:
ready.countDown();

// Trong test:
boolean signaled = ready.await(2, TimeUnit.SECONDS);
```

Đây là các **mảnh mã minh họa**. `countDown()` chuyển count về 0; những caller đang `await()` có thể tiếp tục. Trong một luồng thực thi đúng, các hành động trước `countDown()` **happen-before** những hành động sau `await()` trả về thành công, theo quy tắc memory consistency của `CountDownLatch`.

**Giới hạn cần hiểu:** nếu worker gọi `ready.countDown()` **ngay trước** `queue.take()`, khi test nhận `ready` nó chỉ biết worker đã đến mốc này; **không thể khẳng định worker đang nằm trong `queue.take()` đúng tại thời điểm test gọi `interrupt()`**. Tín hiệu có thể đến trước lúc worker bước vào `take()`. Nhưng đó không nhất thiết là vấn đề: API `take()` phải tôn trọng trạng thái interrupt **đã đặt sẵn hoặc được đặt khi đang chờ**, và test có thể kiểm tra cùng hợp đồng xử lý interrupt trong cả hai thứ tự.

Nếu muốn kiểm thử chính xác một trạng thái blocking nội bộ hiếm gặp, cần công cụ đồng bộ hoặc hook thiết kế riêng cho mục tiêu đó. Không dùng `Thread.State` được lấy một lần hoặc một khoảng `sleep` như bằng chứng tuyệt đối rằng worker đang ở đúng instruction.

## 3. Ví dụ Java 17: kiểm thử `InterruptedException` trên `CountDownLatch.await()`

Tạo tệp `InterruptLatchTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptLatchTest {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch neverOpen = new CountDownLatch(1);

        AtomicBoolean caught = new AtomicBoolean(false);
        AtomicBoolean flagCleared = new AtomicBoolean(false);
        AtomicBoolean flagRestored = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            ready.countDown();

            try {
                neverOpen.await();
            } catch (InterruptedException e) {
                caught.set(true);
                flagCleared.set(
                        !Thread.currentThread().isInterrupted());

                Thread.currentThread().interrupt();
                flagRestored.set(
                        Thread.currentThread().isInterrupted());
            }
        }, "interrupt-worker");

        worker.start();

        if (!ready.await(2, TimeUnit.SECONDS)) {
            worker.interrupt();
            throw new AssertionError("Worker not ready");
        }

        worker.interrupt();
        worker.join(2_000);

        if (worker.isAlive()) {
            worker.interrupt();
            throw new AssertionError("Worker did not finish");
        }

        if (!caught.get()
                || !flagCleared.get()
                || !flagRestored.get()) {
            throw new AssertionError("Interrupt contract violated");
        }

        System.out.println("caught = " + caught.get());
        System.out.println("cleared in catch = "
                + flagCleared.get());
        System.out.println("restored = " + flagRestored.get());
        System.out.println("worker alive = " + worker.isAlive());
    }
}
```

Lệnh chạy:

```bash
javac InterruptLatchTest.java
java InterruptLatchTest
```

Kết quả khi test thành công:

```text
caught = true
cleared in catch = true
restored = true
worker alive = false
```

Tại sao không cần ngủ?

1. Test đợi `ready` thay vì phỏng đoán thời điểm worker sẵn sàng.
2. Worker chờ một latch không có ai `countDown`, nên không thể đi qua `await()` bằng đường bình thường.
3. `interrupt()` có thể được gọi khi worker đã chờ **hoặc ngay trước lúc gọi** `await()`. Trong cả hai trường hợp, `CountDownLatch.await()` phản ứng với interrupt.
4. Khi `await()` ném `InterruptedException`, cờ interrupt của worker bị **xóa** theo hợp đồng thao tác chờ; vì vậy `flagCleared=true` trong nhánh `catch`.
5. Worker gọi `Thread.currentThread().interrupt()` để **khôi phục cờ** trước khi kết thúc; `flagRestored=true`.
6. `join(2000)` được dùng **làm giới hạn an toàn**, còn `isAlive()` và các biến trạng thái xác minh điều kiện mong muốn. Nếu worker vẫn chạy, test ném `AssertionError` chứ không báo qua loa là đạt.

`AtomicBoolean` được dùng để chia sẻ trạng thái an toàn giữa các thread. `join()` còn cung cấp quan hệ đồng bộ khi worker đã chấm dứt, nhưng các atomic flag giúp ý định kiểm thử rõ ràng và tránh truy cập dữ liệu chia sẻ không đồng bộ.

Trong kiểm thử thực, chọn timeout phù hợp với mức tải CI. Quá ngắn gây failure giả do môi trường; quá dài làm chẩn đoán test treo chậm. **Timeout là rào an toàn, không phải cách điều khiển thứ tự.**

## 4. Dùng `BlockingQueue.take()` để kiểm thử worker chờ việc

`BlockingQueue.take()` là điểm chờ điển hình ở consumer thread. Khi queue rỗng, worker đợi phần tử; khi bị interrupt, `take()` có thể ném `InterruptedException`.

Tệp `InterruptQueueTest.java`:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptQueueTest {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch cleaned = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);

        Thread consumer = new Thread(() -> {
            ready.countDown();
            try {
                String item = queue.take();
                throw new AssertionError("Unexpected item: " + item);
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            } finally {
                cleaned.countDown();
            }
        }, "queue-consumer");

        consumer.start();

        try {
            if (!ready.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Consumer not ready");
            }

            consumer.interrupt();

            if (!cleaned.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Cleanup not observed");
            }

            consumer.join(2_000);
            if (consumer.isAlive() || !interrupted.get()) {
                throw new AssertionError("Consumer did not stop correctly");
            }

            System.out.println("interrupt observed = true");
            System.out.println("cleanup observed = true");
            System.out.println("consumer alive = false");
        } finally {
            consumer.interrupt();
        }
    }
}
```

Chạy:

```bash
javac InterruptQueueTest.java
java InterruptQueueTest
```

Kết quả khi thành công:

```text
interrupt observed = true
cleanup observed = true
consumer alive = false
```

Queue không được `put` bất kỳ phần tử nào; worker vì vậy không thể hoàn thành `take()` theo đường đọc dữ liệu. Test gửi interrupt và yêu cầu worker báo `cleaned` trong `finally`.

**Lưu ý về thứ tự:** test không cần phân biệt tín hiệu interrupt đến ngay trước hay trong khi `take()` chờ. Cả hai đường đều thuộc hợp đồng cần hỗ trợ. Nếu cố gắng lấy trạng thái `WAITING` bằng polling rồi mới interrupt, test còn phụ thuộc JVM implementation và có thêm race.

Trong mã production, vòng consumer nên truyền `InterruptedException` lên hoặc khôi phục cờ và **thoát**. Nếu bắt xong lặp lại `take()` trong một vòng `while(true)` mà không đổi chính sách, cờ được khôi phục có thể làm nó ném ngay liên tiếp, gây vòng lặp bận.

## 5. Không nhầm `Thread.interrupt()` với việc tác vụ đã kết thúc

Một bài test yếu chỉ làm:

```java
worker.interrupt();
assertTrue(worker.isInterrupted());
```

Đây là mảnh mã JUnit minh họa. Kiểm tra một cờ tại một thời điểm **không chứng minh worker đã nhận/giải quyết tín hiệu**, cũng không chứng minh nó đã kết thúc. Một thao tác chờ có thể xóa cờ khi ném `InterruptedException`, và worker có thể khôi phục cờ hoặc không. Test đọc `isInterrupted()` bên ngoài rất dễ thấy `false` dù xử lý interrupt hoàn toàn đúng.

Nên quyết định hợp đồng rõ:

- Nếu kiểm tra **tín hiệu đã được xử lý**, cho worker đặt `AtomicBoolean` trong `catch` hoặc xác nhận callback.
- Nếu kiểm tra **đã dọn tài nguyên**, có latch `cleaned` hoặc test fake resource.
- Nếu kiểm tra **đã chấm dứt**, dùng `join(timeout)` rồi assert `!worker.isAlive()`.
- Nếu kiểm tra **khôi phục cờ**, đo `Thread.currentThread().isInterrupted()` **ở bên trong worker** sau thao tác restore; đừng đợi tới khi thread đã kết thúc mới suy luận từ đối tượng `Thread`.
- Nếu kiểm tra **hành vi nghiệp vụ**, thêm assertion rằng không có side effect sau khi nhận hủy.

Không mặc định mọi ứng dụng đều phải khôi phục cờ khi bắt `InterruptedException` và ngay lập tức truyền tiếp; nếu một phương thức `throws InterruptedException`, việc propagate thường đã phù hợp. Chọn chiến lược theo hợp đồng nhưng **test chính xác chiến lược ấy**.

## 6. Test chính caller bị ngắt khi đang gọi `Future.get()`

Ngắt luồng đang **chờ kết quả** khác với ngắt worker thực thi công việc. Nếu caller bị interrupt trong `Future.get()`, caller có thể nhận `InterruptedException`; **Future không mặc nhiên được hủy**, tác vụ nguồn có thể tiếp tục.

Có thể kiểm tra điều này mà không cần executor hoặc timing may rủi bằng một `CompletableFuture` chưa hoàn tất.

Tệp `FutureGetInterruptTest.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureGetInterruptTest {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> result = new CompletableFuture<>();
        CountDownLatch callerReady = new CountDownLatch(1);
        AtomicBoolean callerInterrupted = new AtomicBoolean(false);

        Thread caller = new Thread(() -> {
            callerReady.countDown();

            try {
                result.get();
                throw new AssertionError("Unexpected result");
            } catch (InterruptedException e) {
                callerInterrupted.set(true);
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.ExecutionException e) {
                throw new AssertionError("Unexpected task failure", e);
            }
        }, "waiting-caller");

        caller.start();

        if (!callerReady.await(2, TimeUnit.SECONDS)) {
            caller.interrupt();
            throw new AssertionError("Caller not ready");
        }

        caller.interrupt();
        caller.join(2_000);

        if (caller.isAlive() || !callerInterrupted.get()) {
            throw new AssertionError("Caller did not handle interrupt");
        }
        if (result.isDone()) {
            throw new AssertionError("Future was changed by caller interrupt");
        }

        System.out.println("caller interrupted = "
                + callerInterrupted.get());
        System.out.println("future done = " + result.isDone());

        result.complete("late result");
        System.out.println("future result = " + result.join());
    }
}
```

Chạy:

```bash
javac FutureGetInterruptTest.java
java FutureGetInterruptTest
```

Đầu ra:

```text
caller interrupted = true
future done = false
future result = late result
```

Tín hiệu `callerReady` là mốc trước `get()`. Interrupt có thể tới trước khi caller thực sự chờ ở `get()`, nhưng `get()` có khả năng phản ứng với **trạng thái interrupt đã đặt** hoặc **interrupt đến trong lúc chờ**. Vì Future chưa được complete ở thời điểm gửi tín hiệu, đường chờ thành công không xảy ra.

Sau khi caller thoát, `result.isDone()` vẫn là `false`: **interrupt caller không tự cancel Future**. Main chủ động `complete("late result")` để chứng minh nguồn kết quả có thể hoàn tất về sau.

Nếu hợp đồng nghiệp vụ quy định “caller bị ngắt thì phải hủy luôn tác vụ nền”, test phải bổ sung bước gửi cancel và kiểm tra hủy. Đó là **chính sách ứng dụng**, không phải tác động tự động của `Future.get()`.

## 7. Test `Future.cancel(true)` với sự hợp tác của worker

`Future.cancel(true)` không có nghĩa “giết worker”. Với `FutureTask` thông thường được trả từ `ExecutorService.submit`, lời gọi hủy thành công có thể gửi interrupt đến worker đang chạy. Một test tốt cần xác minh **hai tầng kết quả**:

1. Future được đánh dấu canceled: `cancel(...)`, `isCancelled()`, `get()` ném `CancellationException`.
2. Worker thực sự phản ứng với interrupt và chạy cleanup theo hợp đồng.

Tệp `FutureCancelCooperationTest.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelCooperationTest {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        try {
            Future<String> task = executor.submit(() -> {
                started.countDown();

                try {
                    new CountDownLatch(1).await();
                    return "unexpected";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "handled";
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Task not started");
            }

            boolean cancelled = task.cancel(true);
            if (!cancelled) {
                throw new AssertionError("Cancellation unexpectedly lost");
            }

            if (!finished.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not finish cleanup");
            }

            boolean getCancelled = false;
            try {
                task.get();
            } catch (CancellationException expected) {
                getCancelled = true;
            } catch (java.util.concurrent.ExecutionException e) {
                throw new AssertionError("Unexpected task failure", e);
            }

            if (!task.isCancelled()
                    || !sawInterrupt.get()
                    || !getCancelled) {
                throw new AssertionError("Cancellation contract violated");
            }

            System.out.println("cancel accepted = " + cancelled);
            System.out.println("future canceled = " + task.isCancelled());
            System.out.println("worker saw interrupt = "
                    + sawInterrupt.get());
            System.out.println("get canceled = " + getCancelled);
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FutureCancelCooperationTest.java
java FutureCancelCooperationTest
```

Kết quả:

```text
cancel accepted = true
future canceled = true
worker saw interrupt = true
get canceled = true
```

Lời gọi `started.await()` đảm bảo `Callable` đã bắt đầu trước khi hủy. Worker chờ một latch không bao giờ mở; nó chỉ rời thao tác chờ bằng interrupt hoặc một lỗi bất ngờ khiến test thất bại. Sau khi `cancel(true)` thành công, test đợi `finished` để xác nhận worker đã chạy `finally`, đồng thời kiểm tra worker có thực sự bắt `InterruptedException`.

**Phân biệt quan trọng:** Future có thể ở trạng thái canceled **trước** khi worker hoàn tất. Vì vậy `task.isDone() == true` hoặc `get()` ném `CancellationException` **không phải bằng chứng cleanup đã xong**. Latch `finished` là xác nhận riêng. Trong production cần cơ chế lifecycle tương đương hoặc chính sách shutdown phù hợp.

Với `CompletableFuture.cancel(true)`, tham số `true` không có cùng ý nghĩa yêu cầu ngắt worker như `FutureTask` nói trên. Không chuyển nguyên test này sang `CompletableFuture` rồi mặc định thread nền phải nhận interrupt; API có hợp đồng hủy khác nhau.

## 8. Ngắt lúc chờ khóa bằng `lockInterruptibly()`

Thao tác `synchronized` chờ lấy monitor **không thể bị hủy bằng `InterruptedException` chỉ vì đang đợi monitor**. Nếu cần một thao tác xin khóa có thể ngắt, `ReentrantLock.lockInterruptibly()` là lựa chọn phù hợp.

Một test có thể cho **main giữ khóa** trước khi worker cố lấy. Nhờ vậy worker không thể lấy khóa trước khi test gửi interrupt, và không cần sleep.

Tệp `InterruptibleLockTest.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockTest {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        AtomicBoolean acquired = new AtomicBoolean(false);

        lock.lock();
        Thread worker = new Thread(() -> {
            ready.countDown();

            try {
                lock.lockInterruptibly();
                try {
                    acquired.set(true);
                } finally {
                    lock.unlock();
                }
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            }
        }, "lock-waiter");

        try {
            worker.start();

            if (!ready.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker not ready");
            }

            worker.interrupt();
            worker.join(2_000);

            if (worker.isAlive()
                    || !interrupted.get()
                    || acquired.get()) {
                throw new AssertionError("Lock interrupt contract violated");
            }

            System.out.println("interrupt observed = "
                    + interrupted.get());
            System.out.println("lock acquired = " + acquired.get());
            System.out.println("worker alive = " + worker.isAlive());
        } finally {
            worker.interrupt();
            lock.unlock();
        }
    }
}
```

Chạy:

```bash
javac InterruptibleLockTest.java
java InterruptibleLockTest
```

Kết quả:

```text
interrupt observed = true
lock acquired = false
worker alive = false
```

Main đã nắm khóa trước khi worker bắt đầu, nên worker không thể lấy được khóa trong thời gian test giữ nó. Interrupt khiến `lockInterruptibly()` phản ứng dù tín hiệu đến **trước** lúc gọi hoặc **trong** lúc đang chờ. `acquired` vẫn `false`, worker kết thúc.

**Chú ý cleanup:** chỉ gọi `lock.unlock()` trong worker nếu worker **đã lấy được khóa**. Ở nhánh `InterruptedException` trước khi lock thành công, gọi `unlock()` sẽ sai. Trong ví dụ, worker đặt `unlock()` bên trong phần được thực hiện sau `lockInterruptibly()` thành công.

Nếu test đơn giản dùng `synchronized(lock)` trong worker thay vì `lockInterruptibly`, nó **không cùng hợp đồng**. Đừng ép test chờ monitor phải ném `InterruptedException`.

## 9. `CountDownLatch` có phải cách duy nhất?

Không. Chọn primitive theo điều kiện bạn cần chứng minh:

| Primitive | Tín hiệu hữu ích | Khi nên dùng |
|---|---|---|
| `CountDownLatch` | Một hoặc nhiều công việc đã đến mốc nhất định | Phối hợp pha sẵn sàng/kết thúc |
| `CyclicBarrier` | Nhiều bên cùng đến một mốc để tiếp tục | Kiểm thử nhiều worker qua từng vòng |
| `Phaser` | Các pha đồng bộ có số bên linh hoạt | Test nhiều bước trong workflow |
| `Semaphore` | Cấp/nhận permit | Kiểm tra chờ permit và interrupt |
| `BlockingQueue` | Có/không có phần tử | Test producer-consumer và thao tác blocking |
| `ReentrantLock` | Ai giữ/đợi lock | Test `lockInterruptibly` và tranh chấp |
| `Future` / `CompletableFuture` | Tác vụ có kết quả hoặc trạng thái hoàn thành | Test exceptional completion, caller interrupt, cancellation |
| `Thread.join()` | Worker đã kết thúc | Test lifecycle, đọc kết quả worker sau khi thoát |

Điểm chung: primitive phải có **quan hệ sự kiện xác định**. Không cần tạo nhiều latch nếu một primitive đã đủ. Tên latch như `ready`, `started`, `finished`, `release`, `cleanupDone` nên phản ánh **đúng sự kiện đã xảy ra**.

Phân biệt `ready.countDown()` với một cam kết mạnh hơn như “đã vào code blocking”. Nếu event nằm **trước lời gọi blocking**, `ready` chứng minh worker đến dòng tín hiệu, không chứng minh chính xác vị trí instruction sau đó. Thiết kế test nên không phụ thuộc việc scheduler chọn một trong hai thời điểm.

## 10. Sử dụng timeout như hàng rào an toàn

Không nên làm:

```java
ready.await();
worker.join();
```

trong test mà implementation có thể bug khiến latch không được mở hoặc worker không kết thúc. Test có nguy cơ treo mãi trên CI.

Nên dùng timeout ở điểm chờ của **thread test**:

```java
if (!ready.await(3, java.util.concurrent.TimeUnit.SECONDS)) {
    throw new AssertionError("Worker did not become ready");
}

worker.join(3_000);
if (worker.isAlive()) {
    throw new AssertionError("Worker did not terminate");
}
```

Đây là mảnh mã minh họa với `ready`, `worker` đã tồn tại. Timeout vừa buộc test **thất bại có thông điệp** khi thiếu event, vừa đặt giới hạn thời gian cho tình huống có bug.

Cần tách rõ:

- `await(3s)` **đợi sự kiện** `ready` và chỉ trả `true` khi event đã đến.
- `sleep(3s)` **đợi thời gian**, không quan sát sự kiện.
- `join(3000)` đợi thread kết thúc tối đa khoảng thời gian; phải kiểm tra `isAlive()` sau đó.
- `Future.get(timeout, unit)` đợi kết quả tối đa khoảng thời gian; `TimeoutException` **không tự động hủy** Future.
- `CountDownLatch.await(timeout, unit)` trả `boolean`; phải assert kết quả, không bỏ qua.

Timeout có thể cần nới trên CI chậm nhưng không nên dùng timeout làm **cách cưỡng ép thứ tự**. Nếu test thường thất bại do timeout dưới tải hợp lệ, xem lại deadline hoặc ranh giới công việc, không thay test bằng `sleep` dài hơn.

### Trường hợp timeout cũng cần cleanup

Nếu worker chưa kết thúc tại timeout, test không nên bỏ đi một thread non-daemon đang chạy vô hạn. Trong `finally` nên **gửi tín hiệu dừng**, mở latch/queue nếu thích hợp, shutdown executor và giới hạn nỗ lực chờ lại. Nếu test còn treo do code cố tình phớt lờ interrupt, đó là lỗi/lỗ hổng thiết kế cần giải quyết; Java không có cơ chế an toàn chung để ép giết một thread tùy ý.

Không dùng `Thread.stop()` để cưỡng bức kết thúc test. API này nguy hiểm, có thể làm hỏng trạng thái dùng chung.

## 11. Không dùng `Thread.State` làm đồng bộ chính

Một ý tưởng thường thấy:

```java
while (worker.getState() != Thread.State.WAITING) {
    Thread.yield();
}
worker.interrupt();
```

Đây là mảnh code minh họa **không khuyến nghị**. Các vấn đề:

- Thread có thể chuyển qua nhiều trạng thái nhanh giữa hai lần `getState()`.
- `WAITING` không tự nói worker đang chờ đúng latch/queue nào.
- Polling/busy spin có thể chiếm CPU hoặc treo nếu trạng thái mong muốn không xuất hiện.
- `Thread.yield()` chỉ là gợi ý scheduler, không phải primitive xác nhận sự kiện.
- Test trở nên lệ thuộc vào chi tiết scheduling, JVM và thư viện.

Nếu cần chứng minh một điểm trong thuật toán đã xảy ra, hãy đặt **hook đồng bộ tại chính điểm logic đó**. Nếu đang test một thư viện third-party không có hook, hãy kiểm tra **hành vi observable** theo hợp đồng (kết thúc khi interrupt, không mutate sau cancel) thay vì state nội bộ tại một thời khắc không kiểm soát được.

Thread state có thể hữu ích để **chẩn đoán** deadlock hoặc thread dump, nhưng không phải thay thế latch/barrier để điều khiển một test.

## 12. Kiểm thử với JUnit 5: assert sau khi worker hoàn tất

JUnit Jupiter cung cấp `@Test`, `assertTrue`, `assertFalse`, `assertEquals`, `assertThrows`... Các ví dụ JUnit bên dưới **cần dependency JUnit 5 và test runner** của Maven/Gradle/IDE; không phải chương trình độc lập chạy trực tiếp bằng `java`.

Mã JUnit minh họa trong `InterruptContractJUnitTest.java`:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class InterruptContractJUnitTest {
    @Test
    void interruptStopsWorkerWaitingOnLatch() throws Exception {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch blocked = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            ready.countDown();

            try {
                blocked.await();
            } catch (InterruptedException e) {
                caught.set(true);
                Thread.currentThread().interrupt();
            }
        });

        worker.start();

        try {
            assertTrue(ready.await(3, TimeUnit.SECONDS),
                    "Worker never reached ready point");

            worker.interrupt();
            worker.join(3_000);

            assertFalse(worker.isAlive(),
                    "Worker did not terminate");
            assertTrue(caught.get(),
                    "Worker did not handle InterruptedException");
        } finally {
            worker.interrupt();
            blocked.countDown();
            worker.join(3_000);
        }
    }
}
```

Test có ba phần riêng:

1. **Arrange:** tạo hai latch và trạng thái kiểm thử; worker chờ một latch đang đóng.
2. **Act:** test đợi `ready`, gửi `interrupt`.
3. **Assert:** đợi worker hoàn tất có giới hạn thời gian, kiểm tra `isAlive=false` và `caught=true`.

`finally` cố gắng giải phóng tình huống test fail trước khi worker kết thúc. `worker.join(3000)` trong cleanup cũng có thời hạn. **Không dùng `assertTrue(caught.get())` ngay sau `worker.interrupt()` mà chưa có đồng bộ hoàn tất**: test có thể đọc trạng thái trước khi worker vào `catch`.

Nếu test thread bị interrupt bởi môi trường ngoài, `await`/`join` có thể ném `InterruptedException`; test cần để runner nhận diện, đồng thời thực hiện cleanup thích hợp. Không nuốt interrupt của thread chạy test chỉ để giữ test xanh.

### JUnit `assertTimeout` không thay thế latch

`assertTimeout(...)` và `assertTimeoutPreemptively(...)` (trên JUnit 5) có thể giới hạn thời gian test nhưng **không xác lập thứ tự thực thi**. Đặc biệt timeout preemptive có thể chạy executable trong thread riêng, ảnh hưởng `ThreadLocal`, transaction context và logic interrupt. Chỉ dùng khi hiểu hợp đồng và rủi ro; vẫn cần latch, queue hoặc primitive đồng bộ để kiểm tra logic.

## 13. Test `InterruptedException` trong method riêng nên tách việc kiểm tra trạng thái

Một phương thức thực tế có thể:

```java
static void consume(java.util.concurrent.BlockingQueue<String> queue) {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String item = queue.take();
            process(item);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        releaseResources();
    }
}
```

Đây là **mẫu minh họa**, `process(String)` và `releaseResources()` do ứng dụng định nghĩa. Nếu đang test lớp này, không chỉ cần biết worker đã dừng. Nên tạo **fake processing** và **fake cleanup** có thể quan sát:

- `processedCount` phải bằng 0 nếu worker chưa nhận phần tử.
- `cleanupCount` phải bằng 1 khi worker kết thúc.
- `interruptedObserved` hoặc outcome riêng thể hiện worker đã thực thi chính sách interrupt.
- Không có item mới được xử lý sau khi nhận tín hiệu dừng nếu đó là hợp đồng.
- Worker không còn sống sau deadline được cấp.

Một fake tốt tạo ra tín hiệu bằng `CountDownLatch` hoặc atomic state, không bằng log string được đọc theo thời gian may rủi. Nếu cần kiểm tra nhiều pha có item thực, tách rõ `itemReceived`, `processingStarted`, `processingFinished` và `stopObserved`.

Đừng tùy tiện assert số lần thread bị scheduler chuyển trạng thái, số nanosecond để thoát hay `Thread.getState()` chính xác tại một thời điểm; chúng thường không thuộc hợp đồng ứng dụng.

## 14. Phân biệt các loại lỗi khi test ngắt bất đồng bộ

| Tình huống | Caller thường thấy | Điều test phải kiểm tra |
|---|---|---|
| Chính worker bị interrupt tại `await`, worker propagate checked exception từ `Callable` | `Future.get()` có thể ném `ExecutionException` có cause là `InterruptedException` nếu Future không canceled | Xác nhận cause, trạng thái Future, cleanup |
| Chính caller bị interrupt trong `Future.get()` | `InterruptedException` trực tiếp trong caller | Không tự suy worker bị hủy |
| `future.cancel(true)` thành công trên `FutureTask` | `get()` ném `CancellationException`; worker có thể nhận interrupt | Phân biệt Future canceled với worker đã dừng |
| `get(timeout, unit)` hết hạn | `TimeoutException` ở caller | Deadline không tự cancel task |
| Worker hoàn thành bình thường rồi caller gọi interrupt quá muộn | Có thể không có exception từ worker | Phải phối hợp để giữ task chưa hoàn tất |
| `CompletableFuture.cancel(true)` | Future canceled, `join()` thường ném `CancellationException` | Không mặc định interrupt thread nền |

Chú ý `Future.get()` không nhất thiết ném `InterruptedException` trong mọi trạng thái nếu caller đã bị interrupt: ví dụ trong những tình huống kết quả đã có sẵn và race, hợp đồng/implementation có thể có đường hoàn thành ngay. Do đó để test **caller bị interrupt khi đang chờ**, hãy giữ Future **chưa hoàn thành** cho tới sau khi caller đã quan sát interrupt.

Tương tự, một task có thể kết thúc trước khi `cancel(true)` được gọi. Test phải dùng `started` và điểm chờ có kiểm soát để đảm bảo task không hoàn thành sớm nếu muốn assert `cancel(true)` thành công.

## 15. Kiểm thử mà không giấu exception của worker

Nếu `Runnable.run()` ném `AssertionError` trong thread phụ, framework kiểm thử ở thread chính **không tự động biến nó thành test failure** trong mọi trường hợp. Ví dụ:

```java
Thread worker = new Thread(() -> {
    throw new AssertionError("Worker assertion failed");
});
worker.start();
worker.join();
```

Đây là mảnh minh họa. Lỗi có thể chỉ được báo qua uncaught exception handler của worker; test thread cần có cơ chế **thu nhận và xác minh lỗi từ worker**. Với executor, `Future.get()` giúp chuyển lỗi tác vụ về caller dưới `ExecutionException`, nhưng nếu đã gọi `cancel(...)` trên Future, `get()` trả trạng thái cancel thay vì lỗi worker sau đó.

Các lựa chọn:

- `AtomicReference<Throwable>` để lưu lỗi không mong muốn, đọc sau `join`/`done`.
- `Future.get()` cho task không bị hủy, kiểm tra `ExecutionException.getCause()`.
- `Thread.setUncaughtExceptionHandler(...)` để ghi nhận lỗi uncaught nếu phù hợp.
- Một kênh báo cáo kết quả tường minh, ví dụ `BlockingQueue<Outcome>`, có deadline.

### Ví dụ: bắt lỗi worker thay vì cho test giả xanh

Tệp `WorkerFailureCaptureTest.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class WorkerFailureCaptureTest {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                throw new IllegalStateException("worker failed");
            } catch (Throwable e) {
                failure.set(e);
            }
        });

        worker.start();
        worker.join(2_000);

        if (worker.isAlive()) {
            worker.interrupt();
            throw new AssertionError("Worker still alive");
        }

        Throwable observed = failure.get();
        if (!(observed instanceof IllegalStateException)) {
            throw new AssertionError("Wrong worker failure", observed);
        }

        System.out.println("worker failure = "
                + observed.getClass().getSimpleName());
    }
}
```

Chạy:

```bash
javac WorkerFailureCaptureTest.java
java WorkerFailureCaptureTest
```

Output:

```text
worker failure = IllegalStateException
```

Đây là một ví dụ **về kiểm tra kết quả của thread phụ**, không phải cách xử lý mọi `Throwable` trong production. Trong test, việc bắt và lưu giúp **chuyển lỗi sang thread đang chạy assertion**; ở production, bắt `Throwable` quá rộng có thể che `Error` nghiêm trọng và cần tránh trừ khi có ranh giới quản lý lỗi rõ ràng.

## 16. Đặt `finally` để test tự dọn dẹp khi assertion thất bại

Kiểm thử đồng thời có thể fail ở bất kỳ bước nào. Vì thế tài nguyên kiểm thử phải được dọn dẹp trong `finally`, kể cả khi một assertion ném `AssertionError`.

Ví dụ kiến trúc:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
CountDownLatch release = new CountDownLatch(1);

try {
    Future<?> task = executor.submit(() -> {
        release.await();
        return null;
    });

    // Phối hợp/test/assert ở đây.
} finally {
    release.countDown();
    executor.shutdownNow();
    executor.awaitTermination(3, TimeUnit.SECONDS);
}
```

Đây là **mảnh mã minh họa trong phương thức có `throws InterruptedException`** cùng imports phù hợp. `executor.submit(Callable)` cho phép lambda ném `InterruptedException`. Trong test thật, nếu `awaitTermination` trả `false`, phải xác định worker còn sống và fail/report rõ ràng; không chỉ gọi nó rồi bỏ qua giá trị.

Dọn dẹp có thể cần **đặt lại trạng thái interrupt** cho thread kiểm thử nếu phải catch `InterruptedException` ở boundary. Không nuốt exception của cleanup một cách tùy tiện, nhưng cũng không để cleanup failure che mất nguyên nhân test thất bại mà không ghi nhận; trường hợp có primary và secondary failure, `try-with-resources` hoặc cơ chế suppressed thích hợp giúp giữ cả hai.

Trong test fixture dùng thread tự quản, cân nhắc `setDaemon(true)` chỉ như một công cụ giảm rủi ro treo JVM, **không phải** thay thế cho `interrupt`, release và `join`. Một test chỉ xanh vì daemon worker bị bỏ lại sau khi JVM kết thúc chưa chứng minh lifecycle đúng.

## 17. Những anti-pattern hay gặp

### A. Dùng `sleep(100)` như dấu hiệu worker đã sẵn sàng

```java
worker.start();
Thread.sleep(100);
worker.interrupt();
```

Thay bằng latch có ý nghĩa: worker `ready.countDown()`, test `ready.await(timeout)`, rồi mới gửi tín hiệu. Tránh giả định thời gian chạy worker.

### B. Gửi interrupt rồi assert ngay

```java
worker.interrupt();
assertTrue(interruptedFlag.get());
```

Có thể fail vì worker chưa kịp xử lý. Đợi `done.await(timeout)` hoặc `join(timeout)` và **kiểm tra đã hoàn thành**, rồi mới đọc flag.

### C. Kiểm tra `isInterrupted()` bên ngoài khi worker đã bắt `InterruptedException`

Lời gọi chờ thường **xóa cờ** khi ném `InterruptedException`; worker có thể khôi phục cờ, sau đó kết thúc. Cờ đọc ở một thời điểm tùy ý không thể chứng minh exception có được bắt hay không. Đo cờ **trong worker**, ở đúng điểm trong hợp đồng.

### D. Chỉ kiểm tra `future.isDone()`

Sau `future.cancel(true)`, `isDone()` có thể là `true` dù worker còn chạy. Thêm `finished` hoặc lifecycle signal nếu test cần chứng minh cleanup/worker exit.

### E. Dùng `Thread.State.WAITING` như điều kiện chắc chắn

Thread state là snapshot tạm thời; không chứng minh worker đang chờ **đúng tài nguyên**. Dùng đồng bộ ứng dụng để chứng minh đúng trạng thái logic.

### F. `await()` vô hạn trong test có thể lỗi

Một bug có thể khiến latch không bao giờ mở và CI treo. Dùng `await(timeout)`, assert boolean, giải phóng tài nguyên trong `finally`.

### G. Test interrupt của caller nhưng lại hủy Future

Nếu mục tiêu là kiểm tra `Future.get()` trả `InterruptedException` khi caller bị ngắt, không tự gọi `future.cancel(true)` trước khi kiểm tra; lúc này `get()` có thể ném `CancellationException` theo trạng thái hủy. Giữ Future pending rồi interrupt caller là setup rõ ràng hơn.

### H. Swallow `InterruptedException` trong test

```java
try {
    latch.await();
} catch (InterruptedException ignored) {
}
```

Đây là mảnh minh họa **sai**: test có thể tiếp tục và báo xanh dù chính thread kiểm thử bị ngắt. Thông thường test method có thể `throws InterruptedException`; nếu phải bắt, khôi phục cờ và fail/propagate theo chính sách.

### I. Lệ thuộc thứ tự in log giữa nhiều thread

Những dòng `System.out.println` từ các thread khác nhau có thể xen kẽ. Nếu cần stdout chính xác, chỉ in ở main **sau khi đã đợi kết quả** như các ví dụ ở trên. Trong test production, kiểm tra state/event hơn là so sánh toàn bộ console transcript.

### J. Bỏ quên worker hoặc executor sau khi fail

Nếu assert fail trước bước shutdown, thread non-daemon có thể tiếp tục chạy vô hạn. Dùng `try/finally`, mở các latch dùng để chặn, `shutdownNow()` khi thích hợp và `awaitTermination(timeout)`; giữ dấu vết nếu dừng không thành công.

## 18. Checklist thiết kế một test interrupt đáng tin

Trước khi chốt test, hãy trả lời:

1. **Luồng nào bị interrupt?** Worker hay caller đang chờ `get()`/`join()`?
2. **Thao tác đích có thể ngắt không?** `BlockingQueue.take`, `CountDownLatch.await`, `lockInterruptibly` khác với chờ vào `synchronized`.
3. **Mốc `ready` chứng minh điều gì?** Nó có đủ để loại trừ task hoàn thành trước tín hiệu không?
4. **Đường thoát bình thường đã bị kiểm soát?** Queue rỗng, latch không mở, lock do test giữ, Future chưa hoàn tất?
5. **Không dựa vào may rủi scheduler?** Không dùng `sleep` để đoán thời điểm.
6. **Đợi worker xử lý xong chưa?** Có `done`, `join` hoặc `Future` thích hợp?
7. **Cờ interrupt được kiểm tra ở đúng thread/đúng thời điểm?** Có phân biệt `isInterrupted()` với `Thread.interrupted()` vốn xóa cờ?
8. **Có kiểm tra kết quả thực?** Loại exception, cause, trạng thái Future, cleanup và side effects.
9. **Có timeout để chống treo?** `await` trả `true`, `join` không còn sống, `get(timeout)` được xử lý đúng.
10. **Có cleanup kể cả khi test fail?** Mở latch, hủy task, đóng executor và báo lỗi còn sót.
11. **Lỗi thread phụ có được truyền về test thread?** Không để `AssertionError` của worker chỉ trôi vào log.
12. **Test có giữ đúng phạm vi hợp đồng?** Không ép một thứ tự ngẫu nhiên hoặc tên thread đặc thù JVM.

**Ghi nhớ:** test interrupt đúng không dựa vào “ngủ đủ lâu”. Hãy xây dựng **tín hiệu sẵn sàng, yêu cầu interrupt, tín hiệu hoàn tất và assertion** trên trạng thái có ý nghĩa. `CountDownLatch` và các primitive đồng bộ giúp tạo quan hệ sự kiện; timeout chỉ giới hạn test treo. Khi kiểm tra `Future`, luôn phân biệt **interrupt caller**, **interrupt worker**, **trạng thái canceled** và **worker thật sự đã dọn dẹp, kết thúc**.
