# Timeout khác cancellation thế nào? — Java concurrency

Một lời gọi Java có thể chạy quá lâu vì thread đang chờ khóa, chờ phần tử trong queue, chờ I/O, hoặc tính toán mất nhiều thời gian. Khi đó ứng dụng thường cần hai cơ chế nghe có vẻ giống nhau nhưng **không đồng nghĩa**:

- **Timeout:** đặt **giới hạn thời gian chờ** hoặc ngân sách thời gian cho một hoạt động. Khi vượt giới hạn, *người chờ* có thể nhận kết quả "hết hạn", `false`, `null` hoặc một exception. Điều đó **không tự khẳng định công việc được chờ đã dừng**.
- **Cancellation:** **yêu cầu chấm dứt công việc** hoặc ngăn nó bắt đầu, theo một giao thức hủy. Yêu cầu có thể được tiếp nhận nhưng task còn phải hợp tác dừng, xử lý side effect và giải phóng tài nguyên. Không phải mọi API cancellation đều làm việc đó tức thời hoặc bằng interruption.

Ví dụ đơn giản: thread A gọi `future.get(100, MILLISECONDS)` để đợi một task trên thread B. Nếu quá 100 ms, A nhận `TimeoutException` và tiếp tục. **Task của B vẫn có thể đang chạy**. Nếu A muốn yêu cầu B dừng, cần một bước riêng, chẳng hạn `future.cancel(true)` theo hợp đồng của loại future/producer đang dùng. Ngay cả khi gọi cancel, không được xem task chắc chắn đã dừng hoặc dữ liệu bên ngoài đã được rollback.

Bài thuộc phần **Interrupt & Hủy** của **Java concurrency nói chung**, tập trung vào JDK 17+ và `java.util.concurrent`, không dùng thành phần concurrency riêng của Spring Framework.

## 1. Một bảng phân biệt nhanh

| Khía cạnh | Timeout | Cancellation |
| --- | --- | --- |
| Câu hỏi chính | "Tôi có chờ quá thời hạn không?" | "Tôi có yêu cầu công việc ngừng/không chạy nữa không?" |
| Trọng tâm | Thời gian chờ, deadline hoặc timeout của operation | Vòng đời và trạng thái của task/operation |
| Ví dụ Java | `Future.get(timeout, unit)`, `BlockingQueue.poll(timeout, unit)`, `Lock.tryLock(timeout, unit)` | `Future.cancel(...)`, `Thread.interrupt()`, cancellation token, đóng resource |
| Tác động mặc định tới worker khác | **Không nhất thiết** | Có thể gửi tín hiệu/yêu cầu, nhưng **không bảo đảm dừng ngay** |
| Kết quả thường gặp | `TimeoutException`, `false`, `null` hoặc exception I/O riêng | `CancellationException` khi lấy kết quả của future đã hủy; flag/trạng thái hủy; interruption tùy API |
| Task có thể vẫn chạy? | Có | Cũng có, nếu không hợp tác hoặc API không hỗ trợ dừng |
| Resource bên ngoài tự rollback? | Không | Không |
| Hợp đồng cần thiết | Deadline, đơn vị thời gian, điều kiện hết hạn | Ai sở hữu task, cách truyền yêu cầu, cleanup, trạng thái hoàn tất |

**Timeout có thể dẫn đến cancellation**, nhưng đó là **chính sách được code chủ động lựa chọn**, không phải một quy tắc Java áp dụng cho mọi method.

## 2. Phân biệt bốn sự kiện trong một request

Trong một hệ thống concurrent, ít nhất bốn mốc có thể khác nhau:

1. **Hết hạn chờ của caller:** caller không muốn đợi thêm.
2. **Yêu cầu hủy được phát ra:** caller hoặc coordinator gọi cancel/interrupt/close.
3. **Worker quan sát yêu cầu hủy:** worker thoát khỏi blocking call hoặc kiểm tra cancellation token.
4. **Worker thật sự hoàn tất cleanup:** không còn làm việc, khóa/permit/resource đã được giải phóng theo giao thức.

Sơ đồ:

```text
Caller                           Task/worker
------                           -----------
submit task  ------------------> start work
wait up to 100 ms                 |
       |                          | doing work
timeout (caller stops waiting)    |
       |                          | STILL RUNNING possible
optional cancel(true) ----------> interrupt request / cancel flag
       |                          | detects request when/if supported
caller returns                    | stops useful work, runs cleanup
                                  +--> terminated/cleaned up
```

Các mốc này có thể cách nhau rất xa. Một API trả `true` từ `cancel()` **không mặc nhiên chứng minh** bước cuối đã hoàn tất. Người gọi muốn chờ cleanup cần một giao thức completion riêng nếu contract cancellation không bao gồm nó.

## 3. "Timeout" có thể nằm ở những tầng nào?

Từ "timeout" không xác định một hành vi duy nhất:

- **Timeout khi chờ kết quả:** người gọi ngừng chờ; task có thể tiếp tục. Ví dụ `Future.get(100, MILLISECONDS)`.
- **Timeout khi lấy tài nguyên:** nếu không lấy được lock/permit/queue item trong thời hạn, operation trả thất bại; chưa bắt đầu phần công việc cần tài nguyên. Ví dụ `ReentrantLock.tryLock(...)`.
- **Timeout của một thao tác I/O:** network read/connection attempt có thể báo hết thời gian theo hợp đồng I/O; điều này không tự rollback remote request hoặc đóng mọi resource.
- **Timeout được áp đặt lên trạng thái future:** một API có thể **hoàn thành future với kết quả lỗi/fallback**, nhưng underlying work có thể vẫn đang làm. Ví dụ `CompletableFuture.orTimeout(...)`.
- **Deadline cho cả workflow:** một thời điểm kết thúc dùng chung để hạn chế nhiều bước gọi liên tiếp; mỗi bước nhận phần thời gian còn lại.

Đọc **Javadoc của đúng phương thức** trước khi suy ra hậu quả. Một `TimeoutException` từ `Future.get` không mang cùng nghĩa vòng đời với `SocketTimeoutException` từ một thao tác network read.

## 4. Ví dụ Java 17+: `Future.get(timeout)` chỉ giới hạn thời gian đợi

Lưu thành `FutureTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> future = pool.submit(() -> {
                release.await();
                return 42;
            });

            boolean timedOut = false;
            try {
                future.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                timedOut = true;
            }

            System.out.println("Wait timed out: " + timedOut);
            System.out.println("Task done after timeout: "
                    + future.isDone());

            release.countDown();
            System.out.println("Later result: " + future.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Stdout trên đường chạy bình thường:

```text
Wait timed out: true
Task done after timeout: false
Later result: 42
```

**Vì sao kết quả xác định?**

- Task đợi `release` chưa được mở. Vì vậy ngay cả khi worker được scheduler chạy sớm, task vẫn **không thể hoàn tất** trước thời điểm main mở latch.
- `get(30, MILLISECONDS)` hết hạn chờ trên thread main và ném `TimeoutException`; đoạn code **không hề gọi `cancel`**.
- `future.isDone()` vẫn false vì task chưa hoàn tất và chưa bị cancel.
- Sau `release.countDown()`, worker mới có thể trả 42; main gọi `future.get()` lần nữa lấy kết quả.
- `finally` giải phóng latch ngay cả khi lỗi để tránh bỏ mặc worker đang đợi, rồi yêu cầu executor shutdown.

Một lần `get` bị timeout **không làm future biến thành timed-out state vĩnh viễn**. Cùng future có thể được chờ lại, trả kết quả hoặc bị cancel theo chính sách riêng.

## 5. Nếu timeout thì task có thể làm gì tiếp?

Sau `future.get(timeout)` ném `TimeoutException`:

- Task có thể **chưa bắt đầu** vì nằm trong hàng đợi executor.
- Task có thể **đang chạy** và vẫn ghi dữ liệu, gọi callback hoặc gửi network request.
- Task có thể **hoàn thành ngay sau khi caller hết hạn**.
- Task có thể sau đó thất bại với exception khác mà caller không còn lấy kết quả.
- Một job khác có thể bị phụ thuộc vào side effect của task, dù request bên ngoài đã trả "timeout".

Do đó, "caller đã hết hạn" và "task đã dừng" không phải hai trạng thái tương đương. Nếu timeout là lý do không muốn sử dụng kết quả đến muộn, cần quy định **stale-result handling**, idempotency hoặc generation/version token để kết quả đến sau không ghi đè trạng thái mới.

Không nên dùng `Thread.sleep(...)` để kết luận task chắc chắn đã dừng; chỉ một completion primitive hoặc lifecycle protocol xác định mới cho biết điều đó.

## 6. `Future.cancel(boolean)` thực sự cam kết điều gì?

`Future.cancel(mayInterruptIfRunning)` cố gắng hủy computation liên quan. Tham số:

- `false`: nếu computation đã bắt đầu, không yêu cầu interrupt thread đang chạy qua tham số này; implementation có thể không dừng một task đang thực thi.
- `true`: nếu task đang chạy trên một thread được quản lý phù hợp, implementation có thể **yêu cầu interrupt** thread đó nhằm tạo cơ hội dừng hợp tác.

Khi cancellation được thực hiện thành công theo `Future` contract, các lần gọi `isCancelled()` và `isDone()` có thể phản ánh trạng thái canceled/done của **future**. `get()` trên future đã cancel ném `CancellationException`. Nhưng **trạng thái future đã cancel không phải giấy chứng nhận worker đã cleanup xong**.

Đặc biệt:

- `cancel(true)` **không cưỡng bức giết** thread.
- Nhiều blocking calls trong Java phản hồi interruption; một số I/O không làm vậy ngay, hoặc có exception/semantics khác.
- Code có thể bắt `InterruptedException` rồi nuốt nó, khiến task tiếp tục.
- Task có thể đang ở giữa side effect bên ngoài; không thể tự hoàn tác HTTP request hoặc file write đã xảy ra.
- Một task đã hoàn thành trước lời gọi cancel có thể không được cancel; phải xét race giữa completion và cancellation.

## 7. Ví dụ Java 17+: yêu cầu hủy và worker hợp tác dừng

Lưu thành `FutureCancelDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch stopped = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            Future<Integer> future = pool.submit(() -> {
                try {
                    entered.countDown();
                    Thread.sleep(60_000);
                    return 42;
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return -1;
                } finally {
                    stopped.countDown();
                }
            });

            entered.await();
            boolean accepted = future.cancel(true);
            stopped.await();

            boolean canceledOnGet = false;
            try {
                future.get();
            } catch (CancellationException e) {
                canceledOnGet = true;
            }

            System.out.println("Cancellation accepted: " + accepted);
            System.out.println("Worker saw interrupt: "
                    + sawInterrupt.get());
            System.out.println("Future canceled: " + future.isCancelled());
            System.out.println("Get canceled: " + canceledOnGet);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac FutureCancelDemo.java
java FutureCancelDemo
```

Stdout trên đường chạy thành công của chương trình:

```text
Cancellation accepted: true
Worker saw interrupt: true
Future canceled: true
Get canceled: true
```

Tại sao chương trình không dựa vào lịch chạy ngẫu nhiên?

1. `entered.countDown()` cho biết task đã bước vào vùng `try`; main không cancel một task chưa chạy.
2. Task cố ngủ 60 giây. Nếu main interrupt **trước** khi worker gọi sleep, sleep nhận flag và ném `InterruptedException`; nếu interrupt **trong** lúc sleep, lời gọi được đánh thức bằng exception.
3. Catch đánh dấu `sawInterrupt` và khôi phục flag bằng `Thread.currentThread().interrupt()` để không làm mất thông tin yêu cầu hủy tại ranh giới không thể throw.
4. `finally` luôn đếm `stopped` khi task rời khối đó; main `await()` trước khi kiểm tra kết quả, xác định cleanup demo đã chạy.
5. Future bị cancel nên `get()` ném `CancellationException`, **không trả -1** dù thân task có nhánh trả -1 khi bị ngắt.

Điểm quan trọng: ví dụ dùng một task hợp tác với interruption để minh họa. **Đừng suy rộng rằng mọi `Future.cancel(true)` ở mọi implementation đều cam kết worker đã dừng ngay**. `stopped` là một completion signal riêng của demo; ứng dụng thực cũng nên có cách quan sát cleanup nếu cần.

## 8. `cancel(false)` và `cancel(true)` không phải chế độ "nhẹ/nặng" tuyệt đối

Tham số chỉ thể hiện **có cho phép thử interrupt worker đang chạy hay không**, không quy định mức ưu tiên của request hoặc thời gian hoàn thành.

Với `FutureTask`/task từ `ExecutorService`, `cancel(false)` có thể khiến future chuyển sang trạng thái canceled nhưng worker đang chạy vẫn tiếp tục nếu không có một signaling mechanism khác. `cancel(true)` có thể giúp một worker đang chờ bằng API interruptible thoát nhanh hơn, song worker vẫn có thể bỏ qua interrupt hoặc mất thời gian cleanup.

Tình huống chọn thường gặp:

- Một task đã bắt đầu và công việc không nên tiếp tục: cân nhắc `cancel(true)` khi việc interrupt được document là an toàn và task có cleanup phù hợp.
- Một operation không được phép ngắt giữa bước critical, hoặc có cancellation token riêng: có thể dùng cách khác, nhưng phải định nghĩa nhiệm vụ còn chạy thế nào sau khi future canceled.
- Chỉ không muốn dùng kết quả đến muộn, nhưng muốn công việc nền hoàn tất phục vụ cache: **chỉ timeout khi chờ** rồi để task tiếp tục có thể là chính sách hợp lệ.

Không chọn `cancel(true)` theo phản xạ nếu tác vụ đang giữ một resource có giao thức không an toàn khi dừng giữa chừng. **Cooperative cancellation** đòi hỏi code xác định các điểm hủy và bất biến sau hủy.

## 9. Timeout trên `BlockingQueue` là chờ có giới hạn, không "hủy producer"

`BlockingQueue.poll(timeout, unit)` chờ tối đa khoảng thời gian tương ứng để lấy một phần tử. Nếu không có phần tử khi thời hạn hết, nó trả `null`. Nó không phát lệnh dừng đến producer khác.

Lưu thành `QueueTimeoutDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class QueueTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        Integer first = queue.poll(20, TimeUnit.MILLISECONDS);
        System.out.println("First poll timed out: " + (first == null));

        queue.offer(7);
        Integer second = queue.poll(1, TimeUnit.SECONDS);
        System.out.println("Next item: " + second);
    }
}
```

```bash
javac QueueTimeoutDemo.java
java QueueTimeoutDemo
```

Stdout chính xác:

```text
First poll timed out: true
Next item: 7
```

Không có producer nào thêm phần tử trước lần `poll` đầu, nên kết quả là `null` sau thời gian chờ. Việc không lấy được item **không thay đổi trạng thái hủy của queue hoặc một thread**. Sau đó chương trình thêm `7` và lấy được bình thường.

Một `poll` bị timeout khác với `take()` bị interrupt: `poll` trả `null` theo hợp đồng timeout, còn `take` có thể ném `InterruptedException` khi người chờ bị yêu cầu ngắt. Chúng cần được xử lý bằng hai nhánh logic khác nhau.

## 10. Timeout khi chờ lock không có nghĩa thread giữ lock bị cancel

`ReentrantLock.tryLock(timeout, unit)` thử lấy lock trong giới hạn thời gian, có thể trả `false` nếu không lấy được. Caller thất bại trong việc lấy lock, **không gửi yêu cầu hủy thread đang giữ lock**.

Ví dụ có điều phối rõ, lưu thành `TimedLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TimedLockDemo {
    public static void main(String[] args) throws Exception {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch holderAcquired = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                holderAcquired.countDown();
                releaseHolder.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        }, "lock-holder");

        holder.start();
        holderAcquired.await();

        boolean acquiredWhileHeld = false;
        try {
            acquiredWhileHeld =
                    lock.tryLock(30, TimeUnit.MILLISECONDS);
        } finally {
            if (acquiredWhileHeld) {
                lock.unlock();
            }
        }

        releaseHolder.countDown();
        holder.join();

        boolean acquiredAfterRelease =
                lock.tryLock(1, TimeUnit.SECONDS);
        try {
            System.out.println("Acquired while held: "
                    + acquiredWhileHeld);
            System.out.println("Acquired after release: "
                    + acquiredAfterRelease);
        } finally {
            if (acquiredAfterRelease) {
                lock.unlock();
            }
        }
    }
}
```

```bash
javac TimedLockDemo.java
java TimedLockDemo
```

Stdout trên đường chạy bình thường:

```text
Acquired while held: false
Acquired after release: true
```

Trong lần thử đầu, holder chắc chắn đang sở hữu lock vì main đã đợi `holderAcquired` và chưa mở `releaseHolder`. Vì thế caller không thể lấy được lock trong khoảng timeout, trừ khi holder bị interrupt ngoài dự kiến hoặc một bên chủ động mở latch. Sau khi main mở latch và `join` hoàn tất, lock đã được nhả, nên lần thử sau thành công.

**Cần biết:** `tryLock(timeout, unit)` là phép chờ **có thể bị interrupt** và có `throws InterruptedException`. Nếu thread caller bị interrupt trong lúc đợi, exception không có nghĩa holder bị cancel. Trong code thật, luôn nhả `ReentrantLock` trong `finally` khi đã lấy được.

## 11. `CompletableFuture.orTimeout` và `completeOnTimeout`

Java 9+ cung cấp hai API quan trọng:

- `future.orTimeout(timeout, unit)`: nếu chưa complete đúng hạn, **hoàn thành chính CompletableFuture đó exceptionally** với `TimeoutException`.
- `future.completeOnTimeout(value, timeout, unit)`: nếu chưa complete đúng hạn, **hoàn thành chính CompletableFuture đó bình thường** với một giá trị fallback.

Các method này **thay đổi trạng thái của CompletableFuture được gọi**, khác với `Future.get(timeout)` chỉ làm **lần chờ của caller** hết hạn. Tuy nhiên, **chúng không tự cam kết interrupt hoặc dừng underlying computation** do một worker khác đang làm.

Lưu thành `CompletableFutureTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableFutureTimeoutDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> timeoutFuture =
                new CompletableFuture<>();

        timeoutFuture.orTimeout(20, TimeUnit.MILLISECONDS);

        boolean sawTimeout = false;
        try {
            timeoutFuture.join();
        } catch (CompletionException e) {
            sawTimeout = e.getCause() instanceof TimeoutException;
        }

        boolean laterCompletionAccepted = timeoutFuture.complete(7);

        CompletableFuture<Integer> fallbackFuture =
                new CompletableFuture<>();

        fallbackFuture.completeOnTimeout(
                99, 20, TimeUnit.MILLISECONDS);

        System.out.println("Exceptional timeout: " + sawTimeout);
        System.out.println("Later completion accepted: "
                + laterCompletionAccepted);
        System.out.println("Fallback: " + fallbackFuture.join());
    }
}
```

```bash
javac CompletableFutureTimeoutDemo.java
java CompletableFutureTimeoutDemo
```

Stdout chính xác:

```text
Exceptional timeout: true
Later completion accepted: false
Fallback: 99
```

Phân tích:

1. `timeoutFuture` ban đầu chưa được complete bởi bất kỳ producer nào. Sau deadline, nó complete exceptionally.
2. `join()` ném `CompletionException`, trong đó cause là `TimeoutException`.
3. `complete(7)` sau khi future đã complete exceptionally trả `false`: không thể thay kết quả đã hoàn tất bằng normal completion thông thường.
4. `fallbackFuture` cũng không có producer; nó được complete với 99 sau deadline.
5. **Không có worker tính toán thực sự** trong ví dụ này. Đây là cách chủ động tách *future result state* khỏi *task execution state*. Khi có underlying asynchronous task, một timeout của future **không tự chứng minh** task nền đã dừng.

**Lưu ý:** `orTimeout` và `completeOnTimeout` trả về **chính CompletableFuture đó**. Nếu caller khác cũng giữ reference, họ sẽ nhìn thấy trạng thái completion do timeout; đây không đơn thuần là một phép "đợi tạm thời" như `get(timeout)`.

## 12. `CompletableFuture.cancel(true)` khác `FutureTask.cancel(true)`

Dù `CompletableFuture` implement `Future`, cancellation semantics của nó có điểm quan trọng: **tham số `mayInterruptIfRunning` không được dùng để điều khiển underlying computation** theo hợp đồng của `CompletableFuture`.

Ví dụ một `CompletableFuture.supplyAsync(...)` chạy trên executor: việc hủy future có thể đặt future vào trạng thái canceled và các dependent stage có thể nhận exceptional completion, nhưng **không được mặc định** worker đã bị interrupt. Nếu tác vụ cần hợp tác dừng, thiết kế phải có token, handle hoặc cơ chế hủy nguồn công việc tương ứng.

So sánh:

| Cấu trúc | Timeout | Cancellation |
| --- | --- | --- |
| `Future` từ `ExecutorService.submit` | `get(timeout)` hết thời gian đợi, task có thể tiếp tục | `cancel(true)` cố gắng cancel và có thể yêu cầu interrupt running worker |
| `CompletableFuture` | `orTimeout`/`completeOnTimeout` có thể complete chính future | `cancel(...)` chuyển future sang canceled nhưng không dùng boolean để interrupt computation |
| `BlockingQueue` | `poll(timeout)` hoặc `offer(timeout)` giới hạn chờ | Không có khái niệm cancel mọi producer/consumer chỉ từ timeout; điều phối bằng interrupt, close protocol hoặc token |
| `ReentrantLock` | `tryLock(timeout)` giới hạn chờ lock | Không cancel thread khác đang sở hữu lock |

Không dựa vào tên `cancel` chung để suy ra mọi implementation đều tác động lên thread giống nhau.

## 13. `ExecutorService.invokeAll(timeout)` là một ví dụ kết hợp cả hai

Không phải mọi API timeout đều "chỉ ngừng chờ". `ExecutorService.invokeAll(tasks, timeout, unit)` có hợp đồng riêng: thực thi tập task, chờ chúng hoàn tất trong giới hạn thời gian; **khi method trả về, những task chưa hoàn tất sẽ bị cancel**.

Ở đây timeout của **operation tổng thể** được gắn với **chính sách cancellation** mà API quy định. Đừng áp đặt kết luận của `Future.get(timeout)` lên `invokeAll(timeout)`, hoặc ngược lại.

Tương tự, `invokeAny(tasks, timeout, unit)` trả một kết quả thành công theo hợp đồng hoặc có thể ném `TimeoutException` khi hết hạn; những task chưa hoàn tất có chính sách cancellation theo API. Đọc Javadoc về việc hủy các task còn lại và exception trước khi dùng với side effect không idempotent.

**Bài học:** ý nghĩa của timeout luôn phải được giải thích **theo method**, không chỉ theo tên exception.

## 14. Deadlines: tại sao dùng một ngân sách thời gian tổng thể?

Giả sử một request có ba bước:

```text
A: lấy lock       timeout 200 ms
B: đọc queue      timeout 200 ms
C: chờ future     timeout 200 ms
```

Nếu mỗi bước có *một timeout riêng 200 ms*, tổng thời gian có thể gần **600 ms** chưa kể overhead. Điều đó vi phạm yêu cầu "request tổng thể tối đa 200 ms" nếu đó mới là SLA thực sự.

**Deadline** là một mốc thời gian chung, còn **remaining budget** là thời lượng còn lại tại mỗi bước:

```text
start request
    |
    +--> deadline = start + 200 ms
    |
    +--> step A uses remaining time
    |
    +--> step B recomputes remaining time
    |
    +--> step C recomputes remaining time
    |
    +--> timeout/cancellation policy if budget exhausted
```

Với Java SE, `System.nanoTime()` phù hợp để tính **thời lượng đã trôi qua** vì không dựa vào giờ hệ thống có thể bị điều chỉnh. Đừng dùng `System.currentTimeMillis()` để làm đồng hồ đo chính cho duration nhạy với chỉnh giờ.

### Tránh tính deadline ngây thơ khi timeout cực lớn

Một cách viết phổ biến:

```java
long deadline = System.nanoTime()
        + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
```

Đây là mẫu minh họa, không phải class có `main`. Với timeout hữu hạn bình thường, dễ hiểu. Nhưng với khoảng cực lớn, arithmetic trên `long` có thể wrap. Một thiết kế library cần giới hạn ngân sách, dùng **elapsed time** hoặc tính toán an toàn với số nguyên, và định nghĩa rõ timeout 0/âm.

Không thể chỉ tạo deadline rồi bỏ qua nó: **mỗi blocking operation phải được cấp remaining time phù hợp**. Những API chỉ có chờ vô hạn thì không tự trở nên deadline-aware khi caller giữ một biến deadline.

## 15. Mẫu deadline theo thời gian đã trôi qua

Một helper tính ngân sách còn lại mà không lệ thuộc giờ thực:

```java
static long remainingNanos(
        long startNanos, long budgetNanos) {
    long elapsed = System.nanoTime() - startNanos;
    if (elapsed >= budgetNanos) {
        return 0L;
    }
    return budgetNanos - elapsed;
}
```

Đây là phương thức minh họa trong class Java, **chỉ đúng trong phạm vi các duration đủ nhỏ** để phép trừ elapsed theo mô hình `System.nanoTime()` không bị vấn đề wrap dài hạn và `budgetNanos` là số không âm hợp lệ. Với timeout vài mili-giây, giây hay phút trong ứng dụng thông thường, mô hình có thể sử dụng được.

Khi bước A kết thúc, tính lại `remainingNanos` để bước B không được cấp lại toàn bộ ngân sách. Nếu remaining bằng 0, caller có thể báo deadline exceeded thay vì tiếp tục chờ.

Nhưng nhớ rằng **kiểm tra budget** và **hủy task đang chạy** là hai hành động khác nhau. Sau khi budget hết, caller phải **chọn một policy**: chỉ không chờ nữa, trả fallback, yêu cầu cancel, hoặc tiếp tục để phục vụ cache.

## 16. Timeout trong blocking I/O: hãy đọc hợp đồng cụ thể

Với Java network I/O, có nhiều mức timeout:

- **Connection timeout:** giới hạn thời gian thiết lập kết nối; tùy API dùng để connect.
- **Read timeout:** giới hạn một lần chờ đọc dữ liệu; ví dụ socket có thể ném `SocketTimeoutException` theo hợp đồng cấu hình.
- **Write timeout:** không có một thiết lập thống nhất cho mọi kiểu stream/socket truyền thống; phải xem API/channel/client tương ứng.
- **Overall operation deadline:** giới hạn toàn bộ request qua nhiều lần connect, write, read, decode, retry và xử lý; có thể cần policy riêng.

Ví dụ minh họa với `java.net.Socket`:

```java
import java.net.InetSocketAddress;
import java.net.Socket;

Socket socket = new Socket();
socket.connect(new InetSocketAddress("example.org", 80), 2_000);
socket.setSoTimeout(3_000);
// Khi read từ socket input stream theo hợp đồng,
// thời gian chờ đọc có thể kết thúc bằng SocketTimeoutException.
```

Đây là **đoạn minh họa**, không phải chương trình chạy hoàn chỉnh; không thực hiện network request trong bài học. `setSoTimeout` đặt **read timeout**; nó không phải deadline tổng thể cho toàn bộ kết nối, càng không phải lệnh hủy request đã tới server.

Khi client timeout, server có thể **đã nhận và xử lý yêu cầu** nhưng phản hồi bị chậm hoặc mất. Do đó:

- Timeout không chứng minh external side effect **chưa xảy ra**.
- Retry một operation không idempotent có thể tạo giao dịch trùng.
- Cần request ID/idempotency key, transaction status, deduplication hoặc chính sách bù trừ phù hợp với nghiệp vụ.
- Một timeout thường chỉ nói caller **không nhận được kết quả đúng hạn**.

Không dùng `Thread.interrupt()` như cơ chế hủy I/O chung không cần đọc hợp đồng; một số API hỗ trợ interruption rõ, một số không hoặc cần close channel/socket.

## 17. Timeout và cancellation khi có side effect

Giả sử task thanh toán:

```text
Client gửi lệnh thanh toán -> Service đang xử lý
Client hết timeout -> không thấy response
Client retry ngay -> có thể gửi lệnh lần thứ hai
```

Có ba trạng thái phải phân biệt:

1. **Chưa bắt đầu:** có thể hủy an toàn nếu có giao thức chắc chắn công việc chưa chạy.
2. **Đang thực hiện:** có thể tồn tại partial side effect; interrupt/cancel không tự rollback.
3. **Đã commit nhưng response đến muộn:** caller timeout, nhưng nghiệp vụ bên kia đã thành công.

Nếu có khả năng trạng thái thứ ba, một API không nên trả "thanh toán thất bại" chỉ vì client timeout, mà thường trả **"không xác định/đã hết hạn chờ xác nhận"** rồi cho phép truy vấn trạng thái bằng request ID. Điều này là ví dụ nguyên tắc chung, không phụ thuộc framework.

Các giải pháp thường cần:

- **Idempotency token** để nhiều lần retry cùng yêu cầu không tạo nhiều side effect.
- **Deadline propagation** xuống tầng thực thi khi có hỗ trợ.
- **Cooperative cancellation** cho phần công việc có thể dừng an toàn.
- **Result reconciliation** khi status outcome là unknown.
- **Cleanup** và resource release dù caller đã bỏ cuộc.

Cơ chế concurrency trong một JVM không thay được transaction semantics của hệ thống bên ngoài.

## 18. Cancellation token và cooperative checkpoints

Java có `Thread.interrupt()` như một tín hiệu cấp thread. Một số tác vụ cũng dùng **cancellation token** thuộc cấp operation. Ví dụ với `AtomicBoolean`:

```java
import java.util.concurrent.atomic.AtomicBoolean;

final class CancellationToken {
    private final AtomicBoolean canceled = new AtomicBoolean();

    void cancel() {
        canceled.set(true);
    }

    boolean isCanceled() {
        return canceled.get();
    }
}
```

Đây là class minh họa không có `main`. Task hợp tác kiểm tra:

```java
while (!token.isCanceled()) {
    processOneSmallStep();
}
```

Đoạn minh họa giả định `token` và `processOneSmallStep` được khai báo. Token cho phép nhiều bước xử lý nhìn thấy yêu cầu hủy mà không gắn semantics với một thread cụ thể. Tuy nhiên:

- Nếu task đang block trong `BlockingQueue.take()`, token **không tự đánh thức** nó.
- Worker có thể chỉ kiểm tra token giữa các bước, nên **độ trễ hủy** phụ thuộc mỗi bước.
- Một task đã hoàn thành rồi thì token bị set muộn không hoàn tác kết quả.
- Token cần **ownership** và đường completion rõ; caller không nên đồng nhất `isCanceled()` với cleanup done.
- Một token được chia sẻ giữa nhiều task sẽ yêu cầu **tất cả task** hợp tác ở checkpoint riêng.

Khi công việc có blocking call, có thể kết hợp token với interruption, timeout ngắn, close resource hoặc sentinel để worker có cơ hội kiểm tra lại.

## 19. Interruption không phải forced stop

`Thread.interrupt()` là một cơ chế yêu cầu thread hợp tác. Nếu worker đang gọi `Thread.sleep()`, `Object.wait()`, `BlockingQueue.take()` hoặc nhiều API interruptible, nó có thể được đánh thức bằng `InterruptedException`; khi API ném exception, **interrupt flag thường đã được xóa** theo contract của lời gọi đó.

Nếu method không thể truyền checked exception, mẫu tốt thường là:

```java
try {
    performBlockingWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là đoạn minh họa với `performBlockingWork` giả định. Khôi phục flag giúp không nuốt yêu cầu interrupt, còn `return` giúp task hợp tác dừng. **Chỉ khôi phục flag mà sau đó tiếp tục vòng xử lý vô hạn có thể tạo busy loop hoặc làm việc ngoài ý muốn**.

Nếu method được phép `throws InterruptedException`, thường có thể **truyền ngoại lệ lên caller** thay vì catch/restore. Không tự động biến interruption thành lỗi business hoặc bỏ qua chính sách cleanup.

### Cancellation có thể xảy ra trước, trong hoặc sau operation

Một task có thể kiểm tra token rồi bắt đầu side effect; đúng lúc đó caller yêu cầu cancel. Không thể suy ra side effect chắc chắn chưa bắt đầu chỉ vì một flag được set. Nếu cần "đảm bảo không chạy khi đã cancel trước commit", phải đặt **điểm commit/ownership** được đồng bộ đúng, có thể cần lock, compare-and-set trạng thái hoặc transaction protocol.

## 20. Race giữa completion, timeout và cancellation

Ba mốc có thể cạnh tranh:

```text
Task hoàn tất ----+
                  +--> Outcome mà caller quan sát
Timeout xảy ra ---+
                  |
Cancel request ---+
```

Ví dụ `future.get(100ms)`:

- Task hoàn tất trước khi timeout được quan sát: `get` có thể trả kết quả hoặc ném exception từ task.
- Thời gian chờ hết trong khi task còn incomplete: `get` ném `TimeoutException`.
- Task bị cancel trước khi caller lấy kết quả: `get` có thể ném `CancellationException`.
- Caller thread bị interrupt trong lúc đang chờ: `get` có thể ném `InterruptedException`.

**Không hứa thứ tự tuyệt đối khi các sự kiện xảy ra sát nhau** ngoài contract của API. Ví dụ tác vụ hoàn thành gần deadline có thể khiến các lần thử khác nhau quan sát kết quả khác nhau; chương trình đúng phải xử lý cả hai outcome mà không làm hỏng invariant.

Trong thiết kế hệ thống, thường cần một state machine rõ:

```text
NEW -> RUNNING -> SUCCEEDED
              \-> FAILED
              \-> CANCEL_REQUESTED -> STOPPED
              \-> TIMED_OUT (caller outcome, task may still RUNNING)
```

Đây là một mô hình khái niệm. `TIMED_OUT` thường là **trạng thái góc nhìn caller**, không nên tự biến thành trạng thái task đã terminal trừ khi API thực sự áp dụng cancellation/timeout completion contract.

## 21. Timeout là kết quả hay exception?

Không phải timeout nào cũng ném `TimeoutException`:

| API | Khi hết thời gian chờ |
| --- | --- |
| `Future.get(timeout, unit)` | `TimeoutException` nếu chưa có kết quả theo contract |
| `BlockingQueue.poll(timeout, unit)` | `null` khi không lấy được item |
| `BlockingQueue.offer(item, timeout, unit)` | `false` khi không thêm được |
| `CountDownLatch.await(timeout, unit)` | `false` nếu count chưa về 0 |
| `ReentrantLock.tryLock(timeout, unit)` | `false` nếu không lấy được lock |
| `Thread.join(timeout)` | Trả về sau khi đợi, nhưng caller phải kiểm tra `isAlive()` để biết thread còn sống không |
| `Object.wait(timeout)` | Trở lại sau notify, timeout hoặc spurious wakeup; phải kiểm tra lại guarded predicate |
| `CompletableFuture.orTimeout(...)` | Hoàn thành CompletableFuture exceptionally với `TimeoutException` |
| `CompletableFuture.completeOnTimeout(...)` | Hoàn thành CompletableFuture với fallback |
| Socket read với read timeout | Có thể ném `SocketTimeoutException` theo hợp đồng I/O |

Chưa tính **interruption**: các phương thức chờ có thể ném `InterruptedException` khi caller thread bị yêu cầu ngắt. Cần xử lý timeout và interruption là **hai trường hợp khác nhau**, không bắt cả hai rồi luôn coi như "đã cancel task".

## 22. Timeout của `Thread.join(timeout)` không phải kill thread

`Thread.join(timeoutMillis)` chỉ giới hạn việc **caller đợi thread kết thúc**. Khi trở về do timeout, target thread có thể vẫn chạy. Nếu cần biết worker còn sống, kiểm tra `thread.isAlive()` và chấp nhận rằng trạng thái có thể đổi ngay sau lần kiểm tra.

Ví dụ anti-pattern:

```java
worker.join(100);
System.out.println("Task finished successfully");
```

Đây là đoạn minh họa, `worker` giả định. Dòng in không có căn cứ: `join` có thể trở về do timeout, và ngay cả khi thread kết thúc, điều đó không chứng minh công việc thành công về mặt nghiệp vụ.

Cách suy nghĩ đúng:

```java
worker.join(100);
if (worker.isAlive()) {
    // Caller đã chờ đủ, nhưng worker vẫn chạy.
    // Chọn policy: tiếp tục chờ, request interrupt, hoặc return timeout.
} else {
    // Worker đã kết thúc; success/failure vẫn cần kênh kết quả riêng.
}
```

Đây là đoạn minh họa, không phải chương trình độc lập. Nếu muốn báo kết quả và exception, `Future`/`CompletableFuture` thường phù hợp hơn việc tự đọc field sau một khoảng join.

**Không dùng `Thread.stop()`** làm "cancellation cứng"; nó không bảo vệ invariant và đã bị loại khỏi cách lập trình Java an toàn.

## 23. `shutdown()`, `shutdownNow()` và `awaitTermination`

Khi quản lý `ExecutorService`, ba phương thức có vai trò khác nhau:

- `shutdown()`: bắt đầu **orderly shutdown**, không nhận task mới, cho phép các task đã gửi tiếp tục theo hợp đồng executor.
- `shutdownNow()`: **cố gắng** dừng các task đang chạy (thường bằng interruption), không chạy task chưa bắt đầu và trả danh sách task chưa bắt đầu theo contract; không bảo đảm mọi active task dừng ngay.
- `awaitTermination(timeout, unit)`: **đợi có giới hạn** để executor đạt trạng thái terminated; trả `true` nếu terminated, `false` nếu timeout, có thể ném `InterruptedException` nếu thread caller bị ngắt.

Ví dụ:

```java
pool.shutdown();
if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
    pool.shutdownNow();
}
```

Đây là đoạn minh họa với `pool` là `ExecutorService`, trong method có thể truyền/handle `InterruptedException`.

Điểm cần hiểu: `awaitTermination(5s)` trả `false` **không tự tạo shutdownNow**; code đã chủ động chọn bước `shutdownNow()` sau đó. Đây là ví dụ kết hợp **timeout → cancellation attempt** thành **policy của ứng dụng**.

Nếu caller bị interrupt trong lúc `awaitTermination`, cần có nhánh cleanup phù hợp, thường request `shutdownNow` khi chính tầng đó sở hữu executor, rồi khôi phục flag nếu không thể propagate. Không phải mọi tầng gọi đều có quyền tắt executor được chia sẻ.

## 24. Chọn policy khi hết thời gian chờ

Không có một hành động đúng cho mọi timeout:

| Mục tiêu | Policy thường phù hợp |
| --- | --- |
| Caller chỉ muốn UI phản hồi nhanh | Trả timeout/fallback; tác vụ nền có thể tiếp tục nếu có chủ đích |
| Tính toán CPU-only không còn ai cần | Request cancellation; task kiểm tra token/interrupt ở checkpoint |
| Task đọc queue đang block | Interrupt nếu API hỗ trợ; hoặc close/sentinel/timeout theo lifecycle protocol |
| Giao dịch remote có thể đã commit | Trả "outcome unknown", truy vấn trạng thái và dùng idempotency thay vì retry mù |
| Task có dữ liệu mutable đang commit | Không hủy giữa invariant; dùng atomic commit/rollback protocol |
| Task giúp làm nóng cache | Có thể để chạy tiếp sau caller timeout, nhưng giới hạn tài nguyên và stale writes |
| Executor đang shutdown | Đợi trong ngân sách, sau đó request shutdownNow nếu tầng gọi sở hữu executor và policy cho phép |

Luôn xác định **ai sở hữu quyền hủy**. Một tầng helper xử lý timeout của một request không nhất thiết được phép cancel một shared task đang phục vụ nhiều request khác.

Ví dụ cùng một `CompletableFuture` được nhiều caller dùng: caller A hết hạn chờ không nên mặc định cancel future nếu caller B vẫn cần kết quả. Cancel shared future có thể ảnh hưởng tất cả subscribers; thay vào đó mỗi caller có thể giữ một deadline chờ riêng.

## 25. Timeout lồng nhau, retry và nguy cơ khuếch đại tải

Một hệ thống có timeout 200 ms nhưng tự động retry ba lần liên tiếp có thể tiêu thụ 600 ms hoặc nhiều hơn, cộng thêm thời gian queue/network và cleanup. Nếu mỗi retry còn tạo task mới trong khi task cũ chưa dừng, tải bên dưới có thể **tăng** dù caller tưởng đang giới hạn bằng timeout.

Một policy an toàn hơn cần xét:

1. **Tổng ngân sách deadline** cho cả workflow, không tự reset vô hạn.
2. **Số lần retry tối đa** và khoảng backoff phù hợp.
3. **Idempotency** của operation (đặc biệt với I/O hoặc side effect).
4. **Cancellation/cleanup** của những attempt cũ khi không còn cần.
5. **Backpressure** của executor/queue và giới hạn in-flight tasks.
6. **Phân biệt lỗi tạm thời với cancellation:** không retry vì bị interrupt nếu policy yêu cầu dừng.
7. **Outcome unknown:** với remote side effect có thể đã commit, truy vấn tình trạng thay vì gửi thêm operation không idempotent.

Timeout không phải backpressure tự động. Một caller trả nhanh do timeout vẫn có thể để lại nhiều task chạy dài nếu không quản lý lifecycle.

## 26. Khi nào cần trạng thái "canceled", "timed out", "failed"?

Một API kết quả thường nên phân biệt:

- **SUCCEEDED:** có kết quả hợp lệ theo contract.
- **FAILED:** task chạy nhưng gặp lỗi, có exception/cause.
- **TIMED_OUT:** caller hoặc operation không nhận được kết quả đúng hạn; không tự kết luận task đã dừng.
- **CANCEL_REQUESTED:** đã yêu cầu dừng; worker chưa chắc đã xử lý.
- **CANCELED / STOPPED:** một trạng thái terminal phải được **định nghĩa chính xác**: chỉ future canceled hay cả cleanup done?
- **UNKNOWN / PENDING_RECONCILIATION:** tác động bên ngoài chưa thể xác định sau timeout.

Với library Java, `Future` có semantics state riêng của nó. Với API nghiệp vụ, tránh mượn chữ `CANCELED` nếu muốn hứa worker không còn thực thi trong khi implementation chỉ gọi `future.cancel(true)` rồi trả ngay.

Không nên gộp tất cả `TimeoutException`, `InterruptedException`, `ExecutionException` và `CancellationException` vào một nhánh "task thất bại" nếu caller cần policy khác nhau.

## 27. Các lỗi phổ biến

**1. "`Future.get(timeout)` ném `TimeoutException` là task bị hủy."** Sai. Đây là timeout của lần chờ; task có thể còn chạy.

**2. "`cancel(true)` trả `true` thì worker đã dừng."** Sai. Nó có thể chỉ báo yêu cầu cancel được chấp nhận và future chuyển state; worker cần hợp tác.

**3. "`cancel(false)` an toàn vì không động tới task."** Không nên suy như vậy. Nó có thể chuyển future sang canceled dù task vẫn chạy và side effect vẫn xảy ra; cần contract rõ.

**4. "`CompletableFuture.orTimeout` interrupt task nền."** Không có cam kết đó. Nó hoàn thành future exceptionally, underlying computation có thể tiếp tục.

**5. "`CompletableFuture.cancel(true)` giống `FutureTask.cancel(true)`."** Sai. `CompletableFuture` không dùng tham số mayInterruptIfRunning để điều khiển underlying processing.

**6. "Mọi timeout đều ném `TimeoutException`."** Sai. `poll` trả null, `tryLock` trả false, `awaitTermination` trả boolean, socket read có exception riêng.

**7. "Task đã hết thời gian nên server chắc chắn chưa xử lý."** Sai. Remote side effect có thể đã commit nhưng response đến muộn.

**8. "`Thread.interrupt()` luôn dừng network I/O ngay."** Không; phải đọc hợp đồng channel/socket/client cụ thể.

**9. "Để toàn bộ retry dùng timeout như lần đầu là vẫn đúng SLA tổng thể."** Sai; phải tính remaining budget từ deadline chung.

**10. "Task bị cancel rồi có thể bỏ cleanup."** Sai; cần giữ invariant và giải phóng resource theo policy.

**11. "Cờ cancellation tự thức thread đang block."** Sai. Token cần kết hợp signaling/timeout/interruption hoặc close.

**12. "Có `Future.isDone()` là task thành công."** Sai. Done gồm normal completion, exceptional completion hoặc cancellation tùy future.

**13. "`Thread.join(timeout)` trả về nghĩa worker đã chết."** Sai. Phải kiểm tra `isAlive` nếu cần.

**14. "Một request timeout cho phép hủy shared future của mọi caller."** Sai nếu task đang phục vụ người khác; cần quản lý quyền sở hữu và reference/lifecycle.

**15. "Timeout kết thúc một network transaction."** Không. Transaction, idempotency và outcome reconciliation phải được thiết kế riêng.

## 28. Cách kiểm thử timeout và cancellation một cách đáng tin

Đừng thử bằng cách đợi may rủi `Thread.sleep(100)` rồi giả định worker đã sẵn sàng. Dùng **CountDownLatch** hoặc primitive phối hợp để tạo mốc xác định:

- Để kiểm tra timeout của `get`, giữ task chưa thể hoàn tất bằng một latch chưa mở; sau timeout kiểm tra future còn incomplete, rồi mở latch và lấy kết quả.
- Để kiểm tra cancellation, cho worker báo đã vào vùng chờ, gọi `cancel(true)`, rồi quan sát chính worker đã nhận interrupt và gửi completion riêng.
- Để kiểm tra queue timeout, giữ queue chắc chắn trống trong lần poll đầu, sau đó tự đưa item để chứng minh queue còn dùng bình thường.
- Để kiểm tra lock timeout, giữ lock trong holder có latch kiểm soát, rồi thử `tryLock` từ main; chỉ mở latch sau khi lần thử đầu kết thúc.
- Để kiểm tra late completion, dùng version/generation token bảo đảm kết quả từ attempt cũ không ghi đè attempt mới.

Ở test automation, có thể thêm **timeout của test harness** để tránh treo khi code sai; tuy nhiên timeout test không tự động cung cấp cancellation/cleanup cho task bị kẹt. Cần `finally` để giải phóng latch, close resource, shutdown executor hoặc interrupt worker theo quyền sở hữu, với thời gian dọn dẹp hợp lý.

**Stress test không chứng minh tính đúng tuyệt đối**; quan trọng là hợp đồng API, quan hệ happens-before, state transitions và invariant phù hợp.

## 29. Checklist lựa chọn API

Trước khi viết `timeout` hoặc `cancel`, trả lời:

1. **Cái gì cần hết hạn?** Lần chờ của caller, một operation blocking hay toàn bộ workflow?
2. **Khi hết hạn, task có được chạy tiếp không?** Nếu có, tại sao và ai còn cần kết quả?
3. **Ai được quyền cancel?** Caller hiện tại có sở hữu task, executor hoặc shared future không?
4. **Task nhận yêu cầu bằng cách nào?** Interruption, cancellation token, close resource, sentinel hay API đặc thù?
5. **Task có điểm kiểm tra và cleanup không?** Có tiếp tục side effect sau yêu cầu hủy không?
6. **Future state có phản ánh worker lifecycle không?** Đừng nhầm `isCancelled` với resource đã giải phóng.
7. **Có remote side effect không?** Timeout có thể dẫn đến unknown outcome; cần idempotency/truy vấn trạng thái?
8. **Có nhiều bước hoặc retry không?** Truyền remaining deadline thay vì mỗi bước reset budget.
9. **Cần báo kết quả bằng gì?** Return value, `TimeoutException`, `CancellationException`, custom outcome hay future?
10. **Có race completion-vs-cancel không?** Cần chấp nhận các trạng thái hợp lệ và transition atomic?
11. **Có thể mất interruption không?** Catch `InterruptedException` cần propagate, hoặc restore và thoát khi không thể throw.
12. **Có blocking I/O không hỗ trợ interruption?** Cần timeout/close/cancellation policy riêng.
13. **Có đảm bảo bounded concurrency không?** Timeout không thay queue capacity, semaphore hoặc limit in-flight.
14. **Bạn sẽ test ra sao?** Tạo điều kiện bằng latch, kiểm chứng cleanup và late completion chứ không đoán timing.

## 30. Câu hỏi tự kiểm tra

**Câu 1.** `Future.get(100, MILLISECONDS)` ném `TimeoutException`. Task có chắc bị hủy không?

**Không.** Chỉ lần chờ của caller bị timeout. Task có thể vẫn đang chạy, chưa bắt đầu, hoặc hoàn tất muộn. Nếu muốn yêu cầu dừng, cần cancellation policy và thao tác riêng.

**Câu 2.** `Future.cancel(true)` trả `true`. Có thể trả "worker đã cleanup xong" cho người dùng không?

**Không mặc định.** Future có thể canceled nhưng worker còn cần nhận interrupt và cleanup. Nếu cần bảo đảm cleanup hoàn tất, phải có completion signal/contract riêng.

**Câu 3.** `BlockingQueue.poll(timeout)` trả `null` thì producer đã bị cancel chưa?

**Chưa.** Nó chỉ nói poll không nhận được item đúng hạn. Queue và producer khác vẫn có thể hoạt động.

**Câu 4.** `CompletableFuture.orTimeout` khác `Future.get(timeout)` ở điểm nào?

`orTimeout` có thể **hoàn thành chính CompletableFuture exceptionally** sau deadline nếu chưa complete; `get(timeout)` chỉ làm lần chờ của caller kết thúc bằng `TimeoutException`. Không API nào mặc nhiên chứng minh underlying task đã dừng.

**Câu 5.** Vì sao `CompletableFuture.cancel(true)` không nên dùng như cam kết sẽ interrupt worker?

Vì `CompletableFuture` không dùng tham số `mayInterruptIfRunning` để điều khiển underlying computation theo contract của nó. Muốn hủy worker, cần signaling và quản lý task thực thi thích hợp.

**Câu 6.** Nếu một HTTP request timeout, có nên retry lập tức bằng request mới không?

Chỉ khi semantics của operation cho phép. Server có thể đã commit side effect; cần idempotency key hoặc truy vấn/reconciliation để tránh thực thi trùng.

**Câu 7.** Ba bước mỗi bước timeout 100 ms có bảo đảm workflow hoàn tất trong 100 ms không?

**Không.** Tổng thời gian chờ có thể gần 300 ms cộng overhead. Nếu SLA là 100 ms tổng thể, phải dùng deadline chung và remaining budget.

**Câu 8.** `awaitTermination(5s)` trả `false` có tự gọi `shutdownNow()` không?

**Không.** Nó chỉ trả kết quả chờ. Caller phải chủ động chọn policy escalation, và chỉ làm khi sở hữu executor.

**Câu 9.** `Thread.interrupt()` có phải là cancellation với đảm bảo dừng tức thì không?

**Không.** Đây là yêu cầu hợp tác; worker có thể phản hồi ở interruptible blocking call hoặc điểm kiểm tra. Một số I/O/side effect không thể dừng ngay.

**Câu 10.** Nếu caller A timeout nhưng caller B vẫn đợi cùng shared future, A có nên luôn `cancel` future đó không?

**Không.** A có thể chỉ ngừng chờ; hủy shared task sẽ ảnh hưởng B. Quyền hủy phải dựa vào ownership và contract của hệ thống.

## 31. Tổng kết

- **Timeout** chủ yếu là giới hạn thời gian **chờ** hoặc hạn chót của một operation. Nó **không đồng nghĩa** task đang chạy đã dừng.
- **Cancellation** là **yêu cầu hủy công việc**; ngay cả `cancel(true)` cũng không cưỡng bức worker hoàn tất cleanup hoặc rollback side effect.
- `Future.get(timeout)` chỉ timeout **caller wait**; `CompletableFuture.orTimeout` và `completeOnTimeout` có thể complete **future state**; `ExecutorService.invokeAll(timeout)` lại có policy cancel unfinished tasks. **Đọc contract của đúng API.**
- `BlockingQueue.poll(timeout)`, `Lock.tryLock(timeout)`, `awaitTermination(timeout)` và `Thread.join(timeout)` có semantics timeout khác nhau và không tự cancel worker khác.
- Dùng **deadline chung** cho nhiều bước/retry, truyền **remaining budget** và quản lý **backpressure** để tránh các task chạy dài chất chồng sau timeout.
- Khi timeout liên quan I/O hoặc side effect bên ngoài, kết quả có thể **chưa xác định**; phải dùng idempotency, truy vấn trạng thái và quy tắc xử lý late result khi cần.
- Một hệ thống đúng cần tách rõ **caller stopped waiting**, **cancel requested**, **worker observed cancel**, và **cleanup completed**.

Câu hỏi nên đặt ra khi gặp timeout là: **"Ai đã hết thời gian — người chờ hay công việc đang chạy? Nếu tôi muốn dừng công việc, API nào bảo đảm điều đó, theo giao thức nào và khi nào cleanup thật sự hoàn tất?"**. Trả lời được các câu này sẽ tránh phần lớn nhầm lẫn giữa timeout và cancellation trong Java concurrency.