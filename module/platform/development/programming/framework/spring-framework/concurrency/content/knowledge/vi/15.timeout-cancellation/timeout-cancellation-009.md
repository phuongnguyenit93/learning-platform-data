# Kiểm tra hủy trước khi bắt đầu và hủy khi tác vụ đang chạy

Trong ứng dụng Spring Framework xử lý công việc đồng thời, một tác vụ có thể được **đưa vào hàng đợi nhưng chưa chạy**, hoặc **đã được một worker bắt đầu thực thi**. Gọi `Future.cancel(...)` ở hai thời điểm này có ý nghĩa rất khác nhau. Khi chưa chạy, một `FutureTask` bị hủy thành công sẽ không thực thi body tác vụ; khi đã chạy, hủy chỉ là **nỗ lực yêu cầu dừng**, thường thông qua interruption hoặc tín hiệu hợp tác. Việc một `Future` báo `isCancelled() == true` **không đồng nghĩa** rằng code nghiệp vụ đã dừng, một giao dịch đã rollback hay mọi side effect đã được đảo ngược.

Bài học thuộc nhóm **Hết hạn và hủy** trong module **Spring Framework - concurrency**. Trọng tâm là nhận diện ranh giới **trước lúc bắt đầu** và **trong lúc đang chạy**, cách kiểm tra trạng thái chính xác, xử lý race condition, kiểm chứng bằng Java 17+ và tích hợp thực tế với `ThreadPoolTaskExecutor`, `@Async` và `CompletableFuture`.

## 1. Kết quả học tập

Sau khi hoàn thành, bạn có thể:

- Mô tả các trạng thái của task: queued, running, completed, failed, cancellation requested và cancelled; không đồng nhất chúng thành một cờ `isDone`.
- Dùng `Future.cancel(false)` và `Future.cancel(true)` đúng thời điểm, hiểu kết quả boolean cũng như `isCancelled()`, `isDone()` và `get()`.
- Chứng minh bằng kiểm thử xác định rằng task chưa bắt đầu sẽ không chạy body sau khi một `FutureTask` bị hủy thành công.
- Hiểu vì sao task đã chạy vẫn có thể tiếp tục dù Future bị cancel, kể cả khi đã gọi `cancel(true)`.
- Sử dụng `InterruptedException`, `Thread.currentThread().isInterrupted()` và cancellation token cho cooperative cancellation.
- Phân biệt hủy `FutureTask`/`ExecutorService.submit` với hủy `CompletableFuture`, đặc biệt là việc `CompletableFuture.cancel(true)` không điều khiển interruption.
- Thiết kế API hủy trong Spring để tránh báo “đã dừng” khi mới chỉ “đã yêu cầu hủy”.
- Kiểm thử và đo lường queued cancellation, running cancellation, shutdown, timeout và việc xử lý side effect.

## 2. Đặt tên đúng các giai đoạn của công việc

Một `ExecutorService` có thể nhận task qua `submit`, nhưng “đã nhận” không có nghĩa “đã bắt đầu”. Với executor có queue, thời gian sống đơn giản là:

~~~text
SUBMITTED
   |
   v
QUEUED / chờ được worker chọn
   |
   +---- cancel thành công trước khi bắt đầu
   |           |
   |           v
   |       CANCELLED
   |       body không chạy (với FutureTask đã hủy)
   |
   v
RUNNING
   |
   +---- chạy xong --------------------> SUCCEEDED
   +---- ném exception ----------------> FAILED
   +---- nhận yêu cầu hủy --------------+
                                        |
                          có hợp tác dừng?
                            /        \
                          có          không
                           |           |
                           v           v
                      kết thúc sớm    vẫn chạy tiếp
~~~

Sơ đồ này nói về **trạng thái công việc nghiệp vụ**, không phải toàn bộ trạng thái nội bộ của `FutureTask`. Một Future có thể đã được đánh dấu CANCELLED trong khi method body vẫn đang hoàn tất cleanup hoặc tiếp tục chạy vì bỏ qua tín hiệu hủy. Chính vì vậy không thể suy từ `isDone()` sang “worker đã thoát”.

### Phân biệt ba loại sự kiện

| Sự kiện | Ý nghĩa | Có đảm bảo body đã dừng? |
| --- | --- | --- |
| Caller gửi yêu cầu cancel | Caller muốn hủy công việc | Không |
| `Future.cancel(...)` thành công | Handle Future chuyển sang trạng thái hủy theo implementation | Không nếu body đã chạy; có thể chỉ chặn việc bắt đầu |
| Worker xác nhận đã thoát khỏi vùng xử lý | Code thực thi đã dừng hoặc hoàn thành cleanup | Có đối với đoạn code được kiểm soát, nếu dùng tín hiệu hoàn tất đáng tin |

Trong hệ thống có job store, nên lưu ít nhất trạng thái **cancel_requested** tách biệt với **cancelled/stopped**. Nếu một request HTTP gọi cancel, response “đã tiếp nhận yêu cầu hủy” đáng tin hơn “công việc đã dừng” khi bạn chưa có xác nhận của worker.

## 3. Hợp đồng Future.cancel(boolean)

`java.util.concurrent.Future<V>` định nghĩa:

~~~java
boolean cancel(boolean mayInterruptIfRunning);
boolean isCancelled();
boolean isDone();
V get() throws InterruptedException, ExecutionException;
V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

Ý nghĩa của `cancel(...)` theo API:

- Nếu task **chưa bắt đầu** và hủy thành công, task không được thực thi sau đó.
- Nếu task **đã bắt đầu**, tham số `mayInterruptIfRunning` quyết định có nên thử interrupt thread đang chạy **nếu implementation biết thread đó**.
- Nếu task **đã hoàn tất**, đã bị hủy, hoặc không thể hủy, lời gọi mới không làm thay đổi kết quả đã chốt; boolean có thể là `false`.
- Javadoc khuyên kiểm tra `isCancelled()` để xác định trạng thái sau cuộc đua hủy; đừng diễn giải mỗi boolean trả về thành xác nhận worker đã dừng.
- `isDone()` là `true` khi Future đã hoàn thành **bất kỳ cách nào**: thành công, thất bại hoặc hủy. Nó không có nghĩa là thành công.

Khi Future đã cancel, gọi `get()` thông thường ném `CancellationException` (unchecked). Nếu task hoàn thành lỗi không do cancel, `get()` ném `ExecutionException`. `get(timeout, unit)` có thể ném `TimeoutException` chỉ vì người chờ hết hạn; timeout **không tự gọi cancel**.

### Bảng kết quả thường gặp

| Thời điểm gọi | `cancel(false)` | `cancel(true)` |
| --- | --- | --- |
| Task còn chờ, chưa bắt đầu | Có thể ngăn body thực thi nếu hủy thành công | Cũng có thể ngăn body trước khi chạy |
| Task đang chạy với FutureTask | Có thể đánh dấu Future cancelled **mà không interrupt**; body vẫn tiếp tục | Có thể đánh dấu cancelled và thử interrupt worker |
| Task đã hoàn tất trước lời gọi | Không đổi kết quả; thường trả `false` | Không đổi kết quả; thường trả `false` |
| Task đang chạy nhưng bỏ qua interruption | Không yêu cầu interrupt | Interrupt có thể được gửi, nhưng body vẫn có thể tiếp tục |
| Cancellation từ nhiều caller đua nhau | Kết quả từng lời gọi phụ thuộc cuộc đua | Không được suy luận chỉ từ một lần trả boolean |

`cancel(true)` **không giống** `Thread.stop()`; Java hiện đại không có API an toàn để cưỡng bức dừng tùy ý một đoạn code Java. Interruption là tín hiệu hợp tác, không phải sự đảm bảo mọi thao tác I/O, lock hoặc native call sẽ ngừng ngay.

## 4. Hủy trước khi bắt đầu: ngăn body chạy

Giả sử executor chỉ có một worker. Worker đang xử lý job A, còn job B được submit và nằm trong queue:

~~~text
Worker 1:  [job A đang chờ latch]
Queue:     [job B / FutureTask]
Caller:    jobB.cancel(false)
Queue:     [job B đã bị đánh dấu cancelled, có thể vẫn hiện diện]
Worker 1:  khi lấy job B, FutureTask.run() không thực thi body B
~~~

Điều kiện **job B chưa bắt đầu** là cốt lõi. Nếu job B đã rời queue và bắt đầu giữa lúc bạn quan sát và lúc bạn gọi cancel, đó là **cuộc đua** và bạn đang hủy một task đang chạy, không còn tình huống trước khi bắt đầu.

Với `ExecutorService.submit(...)` dựa trên `ThreadPoolExecutor`, task thường được bao vào một `RunnableFuture` như `FutureTask`. `FutureTask.run()` sẽ kiểm tra trạng thái; khi Future đã cancel, body task không được gọi. Như vậy hủy trước khi chạy có thể là phương thức tránh một công việc không còn cần thiết.

### Nhưng job có tự biến mất khỏi queue không?

**Không nhất thiết.** `ThreadPoolExecutor` thường lưu một wrapper trong queue. Khi wrapper được cancel, nó có thể **còn nằm trong hàng đợi vật lý** cho tới khi worker lấy ra hoặc khi có một thao tác dọn dẹp thích hợp. Điều này gây hai hệ quả:

1. `Future.isCancelled() == true` và `getQueue().size() > 0` có thể đồng thời đúng.
2. Số phần tử đang queue không đồng nhất với số job còn cần chạy.

`ThreadPoolExecutor.purge()` cố gắng gỡ những task Future đã bị cancel khỏi queue; đây là biện pháp reclaim bộ nhớ/queue và có chi phí duyệt queue, không nên gọi liên tục như cách điều phối cancellation chính. `remove(Runnable)` có thể không gỡ được wrapper nếu thứ bạn giữ là task gốc chứ không phải Runnable thực tế trong queue.

**Không nhầm API:** `setRemoveOnCancelPolicy(true)` là cấu hình của `ScheduledThreadPoolExecutor`, không phải setter của `ThreadPoolExecutor` thông thường hoặc một tính năng chung của mọi Spring `TaskExecutor`. Kiểm tra loại executor cụ thể trước khi đề xuất cấu hình dọn queue tự động.

### Vì sao cần kiểm tra trước khi bắt đầu?

Nếu ứng dụng tự lưu trạng thái hủy trong token hoặc job store, worker nên kiểm tra **sát trước thao tác có side effect đầu tiên**:

~~~java
if (token.isCancellationRequested()) {
    return; // bỏ qua việc chưa bắt đầu có ích
}
performFirstSideEffect(jobId);
~~~

Đây là **mẫu minh họa** trong method với `token` và `performFirstSideEffect` do ứng dụng cung cấp. Check này tránh được yêu cầu hủy đã tồn tại trước khi worker nhận job, nhưng **không tạo tính nguyên tử** giữa “kiểm tra” và “ghi side effect”. Cancel có thể đến ngay giữa hai dòng. Nếu hợp đồng bắt buộc “cancel thành công đồng nghĩa không ghi gì”, phải dùng trạng thái giao dịch, lock hoặc một admission/state transition được đồng bộ với nơi thực thi side effect.

## 5. Hủy khi đang chạy: interruption chỉ là lời đề nghị

Một task có thể đang chạy trên worker:

~~~text
Caller               Worker
  |                     |
  |                task đang chạy
  |----cancel(true)----->|
  |  Future cancelled    | nhận interrupt (nếu có hỗ trợ)
  |                      | kiểm tra/đáp ứng
  |                      +-- dừng sớm và cleanup
  |                      hoặc
  |                      +-- bỏ qua, tiếp tục chạy
~~~

Với `FutureTask` thông thường:

- `cancel(false)` có thể đánh dấu Future là canceled **nhưng không interrupt**. Body đã bắt đầu vẫn có thể thực thi tới cuối, kể cả sinh side effect.
- `cancel(true)` thử interrupt thread chạy task. Nếu đang chờ ở `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await` hoặc nhiều API interruptible khác, chúng thường ném `InterruptedException`.
- Nếu đang chạy một vòng tính toán CPU không kiểm tra interrupt hoặc token, task có thể bỏ qua yêu cầu và tiếp tục đến khi xong.
- Nếu đang chạy I/O không hỗ trợ interrupt theo kỳ vọng, cần timeout/cancellation API riêng của thư viện, ví dụ client HTTP, driver database hoặc giao thức RPC.
- `cancel(true)` có thể trả `true` **trước khi worker thực sự thoát**. Đừng dùng boolean này để xác nhận mọi tài nguyên đã được giải phóng.

### InterruptedException và cờ interrupt

Khi một API chờ interruptible ném `InterruptedException`, trạng thái interrupt thường đã được xóa khi exception được ném. Nếu method không thể truyền exception lên caller do chữ ký/khung làm việc, mẫu thường dùng là **khôi phục interrupt** rồi kết thúc có kiểm soát:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Hủy việc tiếp theo, thu dọn tài nguyên và return/throw phù hợp.
    return;
}
~~~

Đây là **mã minh họa**, với `blockingOperation()` do ứng dụng định nghĩa. Chỉ gọi `Thread.currentThread().interrupt()` không tự chấm dứt method. Nếu bắt exception rồi tiếp tục vòng lặp như không có gì xảy ra, nhiệm vụ sẽ khó dừng và caller có thể nhầm rằng cancel đã thành công.

### Kiểm tra mà không xóa cờ

~~~java
if (Thread.currentThread().isInterrupted()) {
    // Dừng hợp tác hoặc chuyển sang logic cleanup.
}
~~~

`isInterrupted()` đọc trạng thái mà **không xóa** cờ. Ngược lại, static `Thread.interrupted()` đọc **và xóa** trạng thái interrupt của thread hiện tại; sử dụng tùy tiện trong vòng lặp hoặc thư viện có thể làm mất tín hiệu khiến tầng trên không nhìn thấy. Nếu dùng `Thread.interrupted()` có chủ đích để xử lý một lần, phải hiểu ý nghĩa việc clear flag.

## 6. Demo Java 17+ độc lập: cả ba tình huống hủy

Đây là chương trình hoàn chỉnh minh họa:

1. Hủy một task **đang chờ queue** trước khi body bắt đầu.
2. Hủy một task **đang chạy** bằng `cancel(true)` và xác minh nó quan sát interruption.
3. Hủy một task **đang chạy** bằng `cancel(false)`: Future bị hủy nhưng body vẫn hoàn thành một side effect được mô phỏng.
4. Hủy một `CompletableFuture`: handle hoàn thành ngoại lệ, không suy ra điều gì về interruption.

Tất cả các đường thực thi dùng `CountDownLatch` và timeout chống treo, **không phụ thuộc vào `Thread.sleep()`**.

Tệp **CancellationPhasesDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class CancellationPhasesDemo {

    private static void cancelBeforeStart() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger queuedBodyRuns = new AtomicInteger();

        try {
            Future<?> blocker = executor.submit(() -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Blocker did not start");
            }

            Future<?> queued = executor.submit(() -> {
                queuedBodyRuns.incrementAndGet();
            });

            boolean cancelled = queued.cancel(false);
            release.countDown();

            blocker.get(5, TimeUnit.SECONDS);
            executor.submit(() -> {}).get(5, TimeUnit.SECONDS);

            System.out.println("queuedCancelled=" + cancelled);
            System.out.println("queuedBodyRuns=" + queuedBodyRuns.get());
            System.out.println("queuedIsDone=" + queued.isDone());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void cancelRunningWithInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interruptSeen = new AtomicBoolean();

        try {
            Future<?> running = executor.submit(() -> {
                entered.countDown();
                try {
                    new CountDownLatch(1).await();
                } catch (InterruptedException ex) {
                    interruptSeen.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    exited.countDown();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            boolean cancelled = running.cancel(true);
            if (!exited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not exit");
            }

            System.out.println("runningCancelTrue=" + cancelled);
            System.out.println("interruptSeen=" + interruptSeen.get());

            try {
                running.get();
            } catch (CancellationException ex) {
                System.out.println("runningGet=CancellationException");
            }
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void cancelRunningWithoutInterrupt() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean bodyContinued = new AtomicBoolean();

        try {
            Future<?> running = executor.submit(() -> {
                entered.countDown();
                try {
                    release.await();
                    bodyContinued.set(true);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    exited.countDown();
                }
            });

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            boolean cancelled = running.cancel(false);
            release.countDown();

            if (!exited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not exit");
            }

            System.out.println("runningCancelFalse=" + cancelled);
            System.out.println("bodyContinued=" + bodyContinued.get());
            System.out.println("futureCancelled=" + running.isCancelled());
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void cancelCompletableFuture() {
        CompletableFuture<String> result = new CompletableFuture<>();
        boolean cancelled = result.cancel(true);
        System.out.println("cfCancel=" + cancelled);
        System.out.println("cfIsCancelled=" + result.isCancelled());

        try {
            result.join();
        } catch (CancellationException ex) {
            System.out.println("cfJoin=CancellationException");
        }
    }

    public static void main(String[] args) throws Exception {
        cancelBeforeStart();
        cancelRunningWithInterrupt();
        cancelRunningWithoutInterrupt();
        cancelCompletableFuture();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CancellationPhasesDemo.java
java CancellationPhasesDemo
~~~

Stdout của lần chạy thành công:

~~~text
queuedCancelled=true
queuedBodyRuns=0
queuedIsDone=true
runningCancelTrue=true
interruptSeen=true
runningGet=CancellationException
runningCancelFalse=true
bodyContinued=true
futureCancelled=true
cfCancel=true
cfIsCancelled=true
cfJoin=CancellationException
~~~

### Tại sao kiểm thử này xác định?

**Tình huống trước khi bắt đầu:** `entered.await()` đảm bảo worker đầu đã vào task blocker và đang chờ `release`. Vì executor chỉ có một worker, task thứ hai vẫn chưa thể chạy. `queued.cancel(false)` hủy wrapper này; sau đó giải phóng blocker. Lời gọi submit marker cuối và `get()` của marker bảo đảm worker đã đi qua vị trí của task bị hủy trong hàng đợi FIFO. Kết quả `queuedBodyRuns=0` chứng minh body thứ hai không chạy. `queuedIsDone=true` là trạng thái Future đã hủy, không phải bằng chứng body chạy thành công.

**Tình huống đã chạy + interrupt:** worker ghi `entered` trước khi đi vào một `await()` không được thả. `cancel(true)` thử interrupt thread đang chờ; task bắt `InterruptedException`, ghi `interruptSeen`, khôi phục cờ rồi thoát. `exited.await()` bảo đảm main chỉ in sau khi body đã đi qua cleanup. `running.get()` ném `CancellationException` vì **kết quả Future đã bị hủy**, không phải vì body ném lỗi nghiệp vụ.

**Tình huống đã chạy, không interrupt:** `cancel(false)` đánh dấu Future canceled nhưng không yêu cầu interrupt. Main thả `release`, task vẫn đặt `bodyContinued=true` và thoát. Bởi thế **`futureCancelled=true` và `bodyContinued=true` cùng đúng**. Đây là điểm cần nhớ khi thiết kế side effect.

**Tình huống CompletableFuture:** `cancel(true)` hoàn thành handle ở dạng cancellation; chương trình không tạo tác vụ tính toán nào cho handle đó. Ví dụ chỉ xác nhận semantics của handle, **không phải thí nghiệm gián đoạn worker**.

Nếu chạy trên môi trường có tài nguyên bất thường, timeout bảo vệ test khỏi treo vô hạn, nhưng sẽ khiến chương trình báo lỗi chứ không xuất stdout “thành công” giả.

## 7. Races ở ranh giới QUEUED -> RUNNING

Không có một thao tác “đọc `isDone` rồi chắc chắn task chưa bắt đầu” nào bảo đảm nguyên tử với scheduler. Các sự kiện có thể xen kẽ:

~~~text
Caller                              Worker
  |                                   |
  | đọc trạng thái đang chờ            |
  |                                   | lấy task khỏi queue
  |                                   | bắt đầu body
  |---- cancel(false) ---------------->|
  | Future có thể chuyển cancelled     | body vẫn chạy tiếp
~~~

Đây là **check-then-act race**. Ngay cả khi quan sát `getQueue().contains(task)` vừa trả true, đến lúc gọi `cancel` task có thể đã bị worker lấy ra. Queue size, active count và trạng thái “đang đợi” trong metrics chỉ là snapshot, không phải transaction với `cancel`.

Nếu yêu cầu nghiệp vụ chỉ là *best effort*, thường chấp nhận race và thiết kế task kiểm tra tín hiệu hủy. Nếu yêu cầu cứng rằng một job bị hủy trước mốc X **không được bắt đầu side effect**, cần một protocol đồng bộ:

1. Một **job state** được lưu bền, có ID và version.
2. Worker chuyển `QUEUED -> RUNNING` bằng một thao tác có điều kiện/atomic, ví dụ cập nhật bản ghi với điều kiện status vẫn QUEUED.
3. Người hủy chuyển `QUEUED -> CANCELLED` cũng bằng một thao tác có điều kiện.
4. Chỉ một chuyển trạng thái có thể thắng; nếu worker thắng, hủy trở thành **CANCEL_REQUESTED** và cần hợp tác dừng.
5. Worker kiểm tra trạng thái trước từng vùng side effect nhạy cảm và xác nhận `STOPPED` khi đã ra khỏi vùng xử lý.

Tùy hệ thống có thể dùng lock, CAS, database optimistic concurrency, message broker semantics hoặc lease; lựa chọn phải phù hợp cơ chế storage thật. `AtomicBoolean` chỉ đồng bộ trong **một JVM**, không quản lý các replica khác.

## 8. FutureTask khác CompletableFuture ở điểm cốt lõi

Cả `FutureTask` và `CompletableFuture` đều triển khai `Future`, nhưng hai cơ chế điều khiển khác nhau:

| Đặc tính | `FutureTask` (thường dùng bởi `submit`) | `CompletableFuture` |
| --- | --- | --- |
| Là đối tượng gắn với execution của `Callable/Runnable`? | Có, trực tiếp triển khai `RunnableFuture` | Không nhất thiết; chủ yếu là handle completion |
| `cancel(false)` trước khi chạy | Ngăn body của FutureTask chạy khi hủy thành công | Đánh dấu handle cancelled; không bảo đảm kiểm soát công việc nào phía sau |
| `cancel(true)` trong khi đang chạy | Thử interrupt runner thread nếu biết | Tham số `mayInterruptIfRunning` **không có tác dụng** trong implementation chuẩn |
| Kết quả `isCancelled` | Cho biết Future đã bị hủy | Cho biết CompletableFuture đã hoàn thành dạng cancellation |
| Tác động tới dependent stages | Không có composition chuẩn | Các stage phụ thuộc có thể hoàn thành exceptionally |
| Guarantee task ngừng/rollback side effect | Không | Không |

Theo Javadoc Java 17 của `CompletableFuture`, `cancel(boolean)` có cùng hiệu ứng với `completeExceptionally(new CancellationException())`, và `mayInterruptIfRunning` **không được dùng để điều khiển ngắt thực thi**. Do đó:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();
future.cancel(true); // hủy completion handle, không tự ngắt worker
~~~

Đây là **đoạn Java minh họa**. Nếu một worker đang tính toán thứ sẽ gọi `future.complete(value)` về sau, worker đó có thể tiếp tục chạy; lời gọi `complete(value)` có thể thất bại vì future đã được kết thúc bằng cancellation.

### supplyAsync và cancel không tạo một đường interrupt đáng tin

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> performWork(), pool);
future.cancel(true);
~~~

Đây là **mã minh họa**, `performWork` do ứng dụng cung cấp và phải shutdown pool trong code thực. `CompletableFuture.cancel(true)` **không cam kết interrupt lambda** đang chạy, kể cả khi bạn truyền một `ExecutorService`. Nếu cần dừng công việc thực sự, truyền cancellation token cho body hoặc sở hữu một `FutureTask` có đường interruption kiểm chứng được.

**Không nhầm:** một số framework có thể tạo wrapper riêng quanh CompletableFuture; semantics cancel/propagation có thể phụ thuộc implementation. Với `@Async` trong Spring, hãy xác nhận loại executor và Future trả về, đừng suy từ chữ ký `CompletableFuture<T>` rằng bạn có thể gián đoạn worker bằng `cancel(true)`.

## 9. Hợp tác hủy trong vòng lặp và đoạn blocking

Một task dài nên chia thành **đơn vị công việc nhỏ** và kiểm tra tín hiệu trước mỗi đơn vị:

~~~java
for (int chunk = 0; chunk < chunks.size(); chunk++) {
    if (token.isCancellationRequested()
            || Thread.currentThread().isInterrupted()) {
        return;
    }

    processChunk(chunks.get(chunk));
}
~~~

Đây là **mã minh họa**, các biến/hàm `token`, `chunks` và `processChunk` do ứng dụng cung cấp. Nếu `processChunk` bị chặn vô hạn, check ở đầu vòng lặp không có ích cho đến khi hàm trả về. Cần đặt timeout/cancel API ở chính I/O blocking.

### Cancellation token

Một token đơn giản trong một JVM:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean();

    public boolean request() {
        return requested.compareAndSet(false, true);
    }

    public boolean isCancellationRequested() {
        return requested.get();
    }
}
~~~

Code này **độc lập về mặt Java** nếu lưu trong tệp `CancellationToken.java` và biên dịch với JDK 17+. `AtomicBoolean` cung cấp visibility và atomicity cho trạng thái cancel. Nhưng `request()==true` chỉ có nghĩa **caller đầu tiên chuyển token sang requested**; nó không cho biết worker đã quan sát token hoặc đã dừng.

Nếu task hoạt động trên nhiều JVM, token trong RAM không đủ. Lưu yêu cầu hủy trong job store, gửi event hoặc polling đến các worker theo contract; trạng thái bền vững quan trọng hơn hình thức API.

### Khi task bắt InterruptedException

Một body có thể dùng:

~~~java
try {
    blockingClientCall();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    markCancellationObserved();
    return;
} finally {
    closeLocalResources();
}
~~~

Đây là **mẫu tích hợp** với các hàm do ứng dụng định nghĩa. Dọn tài nguyên trong `finally` nên idempotent và hạn chế block lâu. Không đánh dấu `CANCELLED` ở job store trước khi hoàn tất cleanup nếu hệ thống yêu cầu xác nhận thực sự ngừng; đồng thời không giữ transaction lớn trong lúc cleanup có thể kéo dài tùy ý.

## 10. Tích hợp trong Spring: chọn đúng handle để hủy

Spring `ThreadPoolTaskExecutor` dựa trên `ThreadPoolExecutor` và cũng hỗ trợ `submit(...)`. Nếu cần có quyền gọi `Future.cancel(...)` với các semantics của tác vụ executor, một cách dễ hiểu là **chủ động submit Runnable/Callable** và giữ lại Future. `TaskExecutor.execute(Runnable)` không trả Future nên không cho caller handle hủy qua lời gọi đó.

Tệp **CancellableExecutorConfig.java** của ứng dụng Spring:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class CancellableExecutorConfig {
    @Bean(name = "cancellableExecutor")
    public ThreadPoolTaskExecutor cancellableExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("cancellable-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Đây là **cấu hình Spring**, cần `spring-context`, không chạy một mình bằng lệnh `java`. Các con số thread/queue chỉ minh họa, không phải khuyến nghị sizing production. Bean do Spring quản lý được khởi tạo và đóng theo vòng đời context.

### Dispatcher giữ Future và token

Tệp **CancellableJobDispatcher.java**:

~~~java
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class CancellableJobDispatcher {
    private final ThreadPoolTaskExecutor executor;

    public CancellableJobDispatcher(
            @Qualifier("cancellableExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public JobHandle submit(String jobId) {
        CancellationToken token = new CancellationToken();
        Future<?> future = executor.submit(() -> run(jobId, token));
        return new JobHandle(future, token);
    }

    public boolean requestCancellation(JobHandle handle) {
        boolean firstRequest = handle.token().request();
        handle.future().cancel(true);
        return firstRequest; // KHÔNG đồng nghĩa worker đã dừng
    }

    private void run(String jobId, CancellationToken token) {
        for (int part = 0; part < 10; part++) {
            if (token.isCancellationRequested()
                    || Thread.currentThread().isInterrupted()) {
                return;
            }
            processPart(jobId, part);
        }
    }

    private void processPart(String jobId, int part) {
        System.out.println("Processing " + jobId + " part " + part);
    }

    public record JobHandle(
            Future<?> future, CancellationToken token) { }

    public static final class CancellationToken {
        private final AtomicBoolean requested = new AtomicBoolean();

        public boolean request() {
            return requested.compareAndSet(false, true);
        }

        public boolean isCancellationRequested() {
            return requested.get();
        }
    }
}
~~~

Đây là **một Spring-managed service**, cần Spring dependencies và Spring ApplicationContext. Lớp `CancellationToken` lồng trong `CancellableJobDispatcher` nên **không** dùng đồng thời với tệp `CancellationToken.java` độc lập ở phần trước nếu ứng dụng không chủ đích có hai loại token. Ví dụ tự chứa các class cần thiết để làm rõ API.

Quan trọng:

- `submit` trả handle liên kết với task được giao cho Spring executor. Khi đó có thể thử hủy cả trước và sau khi task bắt đầu.
- `requestCancellation` đặt token trước rồi gọi `future.cancel(true)`. Điều này vừa hỗ trợ cooperative checks vừa thử interrupt đối với underlying Future có hỗ trợ.
- Giá trị trả về của method là **“đây có phải yêu cầu hủy đầu tiên”**, không phải trạng thái `STOPPED`.
- Nếu thread đã bắt đầu `processPart` trước khi thấy token, một phần việc vẫn có thể chạy sau yêu cầu hủy. Với I/O cần timeout/cancel API riêng.
- Trả handle `Future` qua các ranh giới HTTP hoặc serialization không thích hợp; trong production nên lưu một **job ID** và metadata bền vững, còn Future/token chỉ là handle nội bộ trong một JVM.

### Không nhầm rejection và cancellation

Với `AbortPolicy`, nếu executor bão hòa hoặc shutdown khi `submit`, Spring `ThreadPoolTaskExecutor` có thể ném `TaskRejectedException`. **Đây là tác vụ không được chấp nhận**, không phải một Future đã chạy và sau đó bị hủy. Caller phải có đường xử lý overload: phản hồi HTTP phù hợp, queue bền vững hoặc retry có backoff và idempotency.

Nếu dùng `CallerRunsPolicy`, task có thể chạy ngay trên thread gọi khi pool bão hòa; khi đó `submit` có thể chờ đến lúc body hoàn tất rồi mới trả Future. Việc “hủy ngay sau khi submit” có thể đến quá muộn. Chính sách từ chối là một phần của hợp đồng hủy.

## 11. @Async và cancellation: đừng đồng nhất wrapper với worker

Một method `@Async` có thể trả `Future<T>` hoặc `CompletableFuture<T>`. Spring proxy tạo handle cho caller; target method thường tính giá trị trong worker rồi trả một `Future` tạm phù hợp chữ ký:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CancellationException;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncReportService {
    @Async("cancellableExecutor")
    public CompletableFuture<String> render(
            String reportId, CancellableJobDispatcher.CancellationToken token) {
        for (int part = 0; part < 10; part++) {
            if (token.isCancellationRequested()
                    || Thread.currentThread().isInterrupted()) {
                throw new CancellationException("Cancellation requested");
            }
            renderPart(reportId, part);
        }
        return CompletableFuture.completedFuture("done:" + reportId);
    }

    private void renderPart(String reportId, int part) {
        System.out.println("Rendering " + reportId + " part " + part);
    }
}
~~~

Đây là **Spring service** cần lớp token từ ví dụ dispatcher, executor bean và `@EnableAsync` ở cấu hình ứng dụng. Nó không phải một chương trình Java độc lập. Phần `completedFuture` bên trong method là Future tạm ở target; caller qua proxy nhận một handle biểu diễn việc xử lý async.

Nếu caller chỉ làm:

~~~java
CompletableFuture<String> future = reportService.render(id, token);
future.cancel(true);
~~~

thì `CompletableFuture.cancel(true)` tự nó **không phải cơ chế đáng tin để interrupt work**. Worker có thể vẫn chạy, tùy cơ chế proxy/wrapper và code bên trong. Vì thế nếu muốn dừng nghiệp vụ, gọi `token.request()` và đảm bảo method thường xuyên kiểm tra token. Exception kiểu `CancellationException` trong body có thể làm future của proxy hoàn thành exceptionally; **đừng khẳng định `future.isCancelled()==true` trong mọi biến thể chỉ vì body ném loại exception này**. Phải kiểm tra hợp đồng Future và cách Spring/Executor tạo wrapper.

### Tại sao @Async void khó hủy theo lời gọi?

Với `@Async void`, caller không có Future handle nên không thể gọi `cancel` trực tiếp trên kết quả method. Nếu cần hỗ trợ hủy, hãy cung cấp API riêng theo job ID/token, hoặc đổi thiết kế trả Future/công việc bền vững. `AsyncUncaughtExceptionHandler` là đường xử lý exception không bắt của `void`; nó không thay thế state machine cho hủy.

### Self-invocation và cancellation

Trong proxy mode mặc định, `this.render(...)` bên trong cùng bean bỏ qua Spring proxy. Khi đó body chạy trực tiếp trên thread caller, bất kể annotation. Một test cancellation có thể kết luận sai nếu không đảm bảo lời gọi đi qua Spring-managed proxy. Chọn executor và kiểm tra thread identity, đặc biệt khi có policy `CallerRunsPolicy`.

## 12. Cancellation và timeout: hai điều kiện riêng

`get(timeout, unit)` chỉ đặt giới hạn thời gian **cho thread đang chờ kết quả**. Khi `TimeoutException` xảy ra, tác vụ có thể vẫn chạy.

~~~java
Future<?> future = executor.submit(this::doWork);

try {
    future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    boolean cancelRequested = future.cancel(true);
    recordTimeout(cancelRequested);
}
~~~

Đây là **fragment tích hợp**, cần imports `Future`, `TimeoutException`, `TimeUnit` và các method do ứng dụng định nghĩa; code thực cũng phải xử lý `InterruptedException` và `ExecutionException`. `cancel(true)` sau timeout là một **quyết định nghiệp vụ riêng**. Đôi khi kết quả đến quá muộn cho request nhưng tác vụ nền vẫn nên hoàn tất, ví dụ ghi audit; khi đó không nhất thiết cancel.

Với `CompletableFuture`:

- `orTimeout(duration, unit)` có thể hoàn thành **chính CompletableFuture** exceptionally bằng `TimeoutException` nếu chưa xong.
- `completeOnTimeout(fallback, duration, unit)` có thể hoàn thành Future đó bằng giá trị fallback.
- Cả hai **không tự ngắt công việc đang chạy**; background work vẫn có thể tiếp tục tác động lên database hoặc service ngoài.
- Nếu retry sau timeout, phải có idempotency vì lần thực thi đầu có thể chưa dừng.

Cần phân biệt ba deadline: deadline của request HTTP, timeout của lời gọi I/O trong worker, và deadline tổng của job. Chúng cần liên hệ qua một thiết kế chủ động; đơn giản gọi `future.get(2, ...)` không tạo tự động timeout ở mọi tầng.

## 13. Interrupt trong blocking API, I/O và critical section

### Blocking interruptible

Các API như `CountDownLatch.await`, `BlockingQueue.take`, `Thread.sleep` và nhiều thao tác chờ lock interruptible hỗ trợ `InterruptedException`. Khi nhận interrupt, thường nên:

1. Ghi nhận yêu cầu dừng ở mức cần thiết.
2. Giải phóng tài nguyên local trong `finally`.
3. Khôi phục cờ interrupt nếu không thể truyền `InterruptedException` cho tầng trên.
4. Thoát khỏi công việc càng sớm càng phù hợp với tính nhất quán dữ liệu.

### CPU-bound

Với phép tính dài:

~~~java
while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()
            || token.isCancellationRequested()) {
        break;
    }
    computeNextChunk();
}
~~~

Các hàm/biến trong ví dụ là thành phần ứng dụng. Nếu `computeNextChunk()` là vòng tính toán 30 giây không kiểm tra token, độ trễ phản hồi yêu cầu cancel có thể 30 giây hoặc hơn. Chia workload theo checkpoint là cách kiểm soát cancellation latency.

### I/O và tài nguyên bên ngoài

Không phải mọi thao tác I/O đều dừng khi Java thread bị interrupt. Một HTTP client có thể có API cancel request riêng; JDBC driver có `Statement.cancel()` với hành vi tùy driver/database; socket có timeout hoặc cần đóng channel. Không được lấy `cancel(true)` làm bằng chứng một query DB đã rollback. Gắn timeout phù hợp lên HTTP/JDBC, kiểm tra ràng buộc transaction, và có bù trừ/idempotency cho side effect đã commit.

### Critical section

Nếu task đang giữ lock hoặc đang commit, hủy không có nghĩa được phép dừng ở bất kỳ instruction nào. Thiết kế điểm kiểm tra ở **ranh giới an toàn** giữa các bước. Nếu một đơn vị công việc đã ghi partial data, cần transaction, checkpoint hoặc compensation để trạng thái sau hủy không bị dở dang.

## 14. Shutdown và hủy là hai khái niệm khác

`ExecutorService.shutdown()` ngăn nhận tác vụ mới và cho phép các tác vụ đã được submit tiếp tục chạy theo hợp đồng shutdown thông thường. Nó **không đồng nghĩa hủy toàn bộ task đang chạy**.

`shutdownNow()` cố gắng dừng tác vụ đang thực thi qua interruption, ngăn xử lý tác vụ chờ và trả danh sách những `Runnable` chưa bắt đầu. Đây cũng là **best effort**: nếu task bỏ qua interrupt, nó có thể không dừng. Danh sách trả về là các wrapper Runnable, không nhất thiết là chính object nghiệp vụ gốc.

Một cấu trúc shutdown an toàn khi tự quản lý executor:

~~~java
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        executor.awaitTermination(5, TimeUnit.SECONDS);
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là **đoạn Java minh họa** trong method có `executor` kiểu `ExecutorService`, không phải class độc lập. Nếu Spring quản lý `ThreadPoolTaskExecutor` bean dùng chung, để ApplicationContext quản lý lifecycle theo cấu hình; không tự gọi shutdown ngay khi một request kết thúc.

Với job bắt buộc không mất, trước lúc shutdown cần drain hoặc lưu trạng thái bền vững, vì pending work trong queue RAM có thể mất khi JVM dừng.

## 15. Thiết kế job cancellation API đáng tin

Nếu client gửi `POST /jobs/{id}/cancel`, nên diễn đạt kết quả hủy một cách trung thực. Một sơ đồ trạng thái có thể dùng:

~~~text
QUEUED ----- claim/start -----> RUNNING ------> SUCCEEDED
   |                                |               ^
   | cancel trước claim             | cancel request |
   v                                v               |
CANCELLED_BEFORE_START       CANCEL_REQUESTED       |
                                   |               |
                               worker xác nhận      |
                                   |               |
                            STOPPED / CANCELLED     |
                                                   |
                                có thể hoàn thành trước
                                khi thấy yêu cầu hủy
~~~

Các trạng thái phải được thiết kế để tránh cả “CANCELLED và SUCCEEDED” cùng được ghi như kết quả cuối trong job store. Với yêu cầu hủy đến muộn, API có thể trả `ALREADY_COMPLETED` hoặc `CANCELLATION_NOT_GUARANTEED` thay vì cố ghi đè thành công thành cancelled.

### Gợi ý contract

| API / trạng thái | Ý nghĩa |
| --- | --- |
| `202 Accepted` khi yêu cầu cancel | Hệ thống đã ghi nhận yêu cầu hủy, chưa khẳng định worker dừng |
| `QUEUED -> CANCELLED` bằng CAS/transaction | Cancel thắng race với worker claim; chưa bắt đầu side effect theo protocol |
| `RUNNING -> CANCEL_REQUESTED` | Worker phải kiểm tra và hợp tác dừng |
| `RUNNING -> SUCCEEDED` | Worker hoàn thành trước hoặc trong cuộc đua với yêu cầu |
| `CANCEL_REQUESTED -> STOPPED` | Worker xác nhận đã dừng và cleanup |
| `CANCEL_REQUESTED -> FAILED` | Worker dừng do lỗi; cần phân loại nguyên nhân |
| `ALREADY_COMPLETED` | Không thể hủy công việc đã chốt kết quả |

`202` chỉ là ví dụ API cho asynchronous cancellation. Cách chọn HTTP status thật phụ thuộc hợp đồng sản phẩm, authentication và cơ chế lưu bền vững. Đừng lộ job ID của người khác hoặc cho một caller bất kỳ hủy job không thuộc quyền.

### Atomicity và idempotency

Một cancellation endpoint thường cần idempotent: gọi nhiều lần không tạo trạng thái trái ngược. Dùng version/CAS cho state transition và gắn request ID/correlation ID để quan sát. Nếu task có side effect không rollback được (email đã gửi, chuyển tiền đã thực hiện), cancellation chỉ có thể ngăn **bước tiếp theo**, không thể tự rút lại bước đã hoàn tất; cần bù trừ hoặc hợp đồng “không hủy được sau mốc X”.

## 16. Quan sát cancellation đúng cách

Không chỉ đếm `Future.isCancelled()`. Với workload lớn, nên quan sát:

| Metric | Giải thích |
| --- | --- |
| `cancel_requests_total` | Số yêu cầu người dùng/hệ thống muốn hủy |
| `cancel_before_start_total` | Số job hủy thắng trước khi worker claim |
| `cancel_running_requests_total` | Số yêu cầu hủy khi job đã chạy |
| `cancel_acknowledged_total` | Worker đã quan sát yêu cầu và bước vào cleanup |
| `cancel_stopped_total` | Job thực sự dừng sau cleanup |
| `cancel_too_late_total` | Job đã hoàn thành trước khi cancel thắng |
| `cancellation_latency` | Thời gian từ yêu cầu đến xác nhận dừng |
| `interrupted_tasks_total` | Số body thực sự quan sát interrupt, không phải số lần gọi cancel(true) |
| `queued_cancelled_task_count` | Số task bị hủy nhưng còn hiện diện vật lý trong queue nếu có thể đo |
| `partial_side_effects` | Số job bị hủy sau khi đã ghi một phần side effect; cần reconciliation |

Metric phải tránh đếm trùng: một request có thể gửi cancel nhiều lần, nhiều caller cùng gửi, hoặc Future bị cancel vì timeout. Dùng job ID, request ID và phân biệt **requested**, **handle cancelled**, **worker stopped**. Logging thread name hữu ích cho điều tra nhưng không thay thế một trạng thái bền vững.

### Những số đo dễ đánh lừa

- `getQueue().size()` là ảnh chụp tức thời; có thể bao gồm wrapper đã cancel nhưng chưa được dọn.
- `getActiveCount()` là ước lượng, không cho biết bao nhiêu worker đã hợp tác hủy.
- `Future.isDone()` là true cả khi canceled; không phải metric job success.
- `cancel(true)` trả true không phải “interrupted_tasks_total”.
- `CompletableFuture.isCancelled()` có thể true trong khi computation đứng sau handle vẫn chạy.

## 17. Những lỗi phổ biến

1. **Đọc `isDone()==true` và kết luận job thành công.** Future có thể hoàn thành lỗi hoặc hủy.
2. **Đọc `isCancelled()==true` và kết luận worker đã dừng.** Body có thể vẫn đang cleanup hoặc chạy tiếp.
3. **Dùng `cancel(false)` trên task đang chạy rồi kỳ vọng dừng body.** Nó không yêu cầu interruption.
4. **Dùng `cancel(true)` như lệnh cưỡng bức dừng thread.** Interruption cần hợp tác.
5. **Nuốt `InterruptedException` rồi chạy tiếp vô điều kiện.** Mất tín hiệu dừng.
6. **Quên khôi phục interrupt khi không thể truyền exception.** Thư viện/tầng trên có thể không biết đã bị ngắt.
7. **Gọi `Thread.interrupted()` để “kiểm tra” mà không biết nó xóa flag.** Tầng sau có thể bỏ lỡ tín hiệu.
8. **Chỉ check token một lần trước vòng xử lý dài.** Cancel sau check vẫn có thể tới và không được nhìn thấy.
9. **Tin vào `getQueue().contains(task)` như bằng chứng task chưa chạy.** Worker có thể lấy task ngay sau đó.
10. **Nhầm xóa wrapper khỏi queue với rollback side effect.** Hai quá trình độc lập.
11. **Giả định cancel luôn xóa entry queue ngay.** `ThreadPoolExecutor` có thể giữ FutureTask cancelled đến khi dequeue hoặc purge.
12. **Gọi `setRemoveOnCancelPolicy` trên ThreadPoolExecutor thường.** Setter đó thuộc ScheduledThreadPoolExecutor.
13. **Gọi `CompletableFuture.cancel(true)` rồi mặc định worker bị interrupt.** API Java chuẩn không dùng tham số đó để điều khiển interruption.
14. **Dùng `orTimeout` và tưởng nó ngắt CPU/I/O phía sau.** Nó thay đổi completion, không bảo đảm dừng computation.
15. **Dùng `@Async void` rồi tìm Future để cancel.** Cần giao diện job/token khác hoặc kiểu trả về có handle.
16. **Self-invocation bỏ qua proxy `@Async`.** Body chạy trên caller, làm test timing sai.
17. **Không xử lý rejection của executor.** Task bị từ chối không phải task được nhận rồi hủy.
18. **Dùng `CallerRunsPolicy` mà tưởng submit luôn trả về ngay.** Body có thể chạy inline khi bão hòa.
19. **Cancel task sau khi nó đã commit external side effect rồi báo đã rollback.** Cần compensation, không phải chỉ Future.
20. **Không có cleanup trong finally.** Tài nguyên/socket/lock có thể bị giữ khi interruption xảy ra.
21. **Chỉ dùng AtomicBoolean trong một service nhiều replica.** State cancel không được đồng bộ liên JVM.
22. **Đếm mọi Future cancelled là job cancelled thành công.** Có thể báo cáo sai mức độ thực thi.
23. **Test bằng `Thread.sleep()` để đoán task đã start.** Dùng latch/barrier và timeout.
24. **Không giới hạn thời gian shutdown.** Worker không hợp tác có thể giữ process hoặc tài nguyên.
25. **Gọi retry ngay khi cancel trên side effect không idempotent.** Công việc cũ có thể vẫn chạy.

## 18. Quy trình kiểm thử đáng tin cậy

### Kiểm thử trước khi bắt đầu

1. Dùng single-thread executor, giữ worker đầu bằng latch.
2. Đợi latch xác nhận worker đã bắt đầu và bị giữ.
3. Submit task thứ hai; lúc này task thứ hai chắc chắn chưa có worker rảnh.
4. Gọi `cancel(false)` trên Future thứ hai; assert trạng thái hủy.
5. Thả worker đầu, submit marker barrier và chờ marker hoàn thành.
6. Assert body của task thứ hai **chưa từng chạy**. Không dựa vào `Thread.sleep()`.

### Kiểm thử khi đang chạy

1. Task phát tín hiệu `entered` khi đã vào body.
2. Task chờ một latch không được thả, sử dụng API interruptible.
3. Main đợi `entered`, gọi `cancel(true)`.
4. Task bắt `InterruptedException`, ghi nhận và thoát trong `finally`.
5. Main chờ `exited`, assert interrupt thực sự đã được body quan sát và Future bị hủy.

### Kiểm thử running cancel(false)

1. Đưa task vào trạng thái đang chạy và đang chờ latch.
2. Gọi `cancel(false)`, xác minh Future canceled.
3. Thả latch thủ công, xác minh body **vẫn có thể chạy đến sau vùng chờ**.
4. Điều này giúp team hiểu rằng “future canceled” không đồng nhất với “worker stopped”.

### Kiểm thử Spring integration

- Lấy `ThreadPoolTaskExecutor` do Spring quản lý, không quên lifecycle của ApplicationContext.
- Test đường `submit` và đường `@Async` riêng nếu hệ thống có cả hai; wrapper semantics có thể khác.
- Test bằng handle/ID thật và thread context phù hợp, không chỉ gọi trực tiếp `new Service()`.
- Dựng queue bounded và latch để tái hiện rejection và queued cancellation.
- Kiểm tra timeout/cancellation state trong job table; assert side effect thực sự không xảy ra khi cancel thắng race theo contract.
- Trong mọi test có worker bị chặn, giải phóng latch trong `finally`, giới hạn thời gian chờ và đóng executor để tránh CI treo.
- Test kết hợp shutdown/rolling deployment để biết task đang chờ được drain, bị bỏ hay được ghi bền vững.

## 19. Khi nào cần cơ chế mạnh hơn Future.cancel?

| Bối cảnh | Cơ chế nên dùng |
| --- | --- |
| Task ngắn, nội bộ một JVM, có thể bỏ qua nếu chưa chạy | Future cancellation có thể đủ |
| Task dài, có thể dừng giữa các chunk | Future interrupt + cancellation token + checkpoint |
| Task dùng HTTP/DB blocking | Timeout/cancel API của thư viện + token; không chỉ interrupt |
| Task đang chạy có thể tạo side effect quan trọng | Transaction/state machine/idempotency và checkpoint an toàn |
| Nhiều replica, cần hủy qua node khác | Durable job store và trạng thái cancel có thể quan sát |
| Cần ngăn tuyệt đối một task bắt đầu sau hủy | Atomic state transition giữa worker claim và cancel |
| Job đã hoàn thành rồi client mới hủy | Trả trạng thái quá muộn/already completed |
| Nhiều worker chia sẻ một công việc | Cancellation protocol cho từng child task và tổng hợp completion |
| Chỉ cần UI ngừng chờ response | Có thể timeout request mà không hủy job nếu hợp đồng nghiệp vụ yêu cầu |
| Cần bảo đảm job không mất khi restart | Queue bền vững, retry và outbox/idempotency, độc lập với Future |

Đặt ưu tiên theo nghĩa của *cancel*: “không trả kết quả cho tôi nữa”, “không được bắt đầu job”, “dừng sớm nếu có thể”, hay “hủy toàn bộ hiệu ứng nghiệp vụ”. Bốn yêu cầu này khác nhau đáng kể và không thể giải quyết hết bằng một lời gọi `future.cancel(true)`.

## 20. Câu hỏi tự kiểm tra

1. Tại sao một task vừa được `submit` có thể chưa bắt đầu dù đã có Future?
2. Trong tình huống worker bận và task B còn nằm queue, hủy `FutureTask` của B thành công có làm body B chạy sau đó không?
3. Vì sao sau khi `cancel(false)` một task đang chạy, `future.isCancelled()==true` nhưng body vẫn có thể sinh side effect?
4. `cancel(true)` có chắc worker dừng ngay không? Khi nào interruption thực sự hữu ích?
5. Khi bắt `InterruptedException` mà không ném tiếp, vì sao thường nên gọi `Thread.currentThread().interrupt()`?
6. `Thread.interrupted()` khác `Thread.currentThread().isInterrupted()` ở điểm nào?
7. Tại sao đọc `getQueue().size()` hoặc `contains(task)` không thể làm hàng rào đảm bảo task chưa chạy?
8. `CompletableFuture.cancel(true)` có tự interrupt lambda chạy trong `supplyAsync` không?
9. `isDone()` có phân biệt success, failure và cancellation không?
10. `get(timeout)` timeout có tự cancel hoặc ngừng task không?
11. Với Spring `@Async CompletableFuture`, bạn cần thiết kế gì nếu người dùng yêu cầu dừng công việc thực sự?
12. Trong job store nhiều replica, làm sao phân biệt `QUEUED -> CANCELLED` với `RUNNING -> CANCEL_REQUESTED`?
13. Nếu thao tác chuyển tiền đã commit, `Future.cancel(true)` có rollback được không? Điều gì phải được thiết kế thêm?
14. Một cancellation endpoint trả “đã tiếp nhận yêu cầu” khác “worker đã ngừng” ở điểm nào?
15. Trong kiểm thử, làm thế nào chứng minh body chưa chạy mà không dùng sleep ngẫu nhiên?
16. Khi shutdown, `shutdownNow()` có đảm bảo mọi I/O đang chạy dừng tức thì không?

## 21. Tài liệu tham khảo chính thức

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — Thread interruption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Java SE 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — @Async](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/Async.html)

**Ghi nhớ:** hủy khi task **chưa bắt đầu** có thể ngăn body thực thi nếu FutureTask được cancel thành công. Hủy khi task **đang chạy** chủ yếu là yêu cầu dừng hợp tác: `cancel(false)` không gửi interrupt, `cancel(true)` chỉ thử interrupt, còn `CompletableFuture.cancel(true)` không tự điều khiển việc ngắt computation. Muốn bảo đảm nghiệp vụ, phải xác minh **worker thực sự dừng** và quản lý **job state, side effect, deadline** độc lập với trạng thái Future.