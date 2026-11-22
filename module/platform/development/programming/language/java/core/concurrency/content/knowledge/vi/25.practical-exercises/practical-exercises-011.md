# Thiết kế shutdown có hủy, timeout và đóng tài nguyên

Một ứng dụng Java thường có nhiều tác vụ đang chạy cùng lúc: đọc file, truy vấn database, gọi API, xử lý message, tính toán nền và ghi kết quả. Khi cần tắt ứng dụng, chỉ gọi `System.exit()` hoặc `ExecutorService.shutdown()` rồi bỏ mặc các worker có thể dẫn đến mất tác vụ, ghi dữ liệu dở dang, giữ socket/file handle và tiến trình không thoát được. Ngược lại, đóng tài nguyên trước khi worker ngừng dùng nó có thể gây `IOException`, lỗi giao dịch hoặc dữ liệu bị ghi thiếu.

Bài thực hành này yêu cầu thiết kế **một quy trình shutdown có trạng thái rõ ràng**, hỗ trợ:

- Ngừng nhận task mới ngay khi bắt đầu shutdown.
- Cho task đang chạy và đang đợi cơ hội hoàn tất trong **grace period** có giới hạn.
- Khi hết thời gian, yêu cầu hủy task bằng interruption và xử lý task chưa bắt đầu.
- Có **force period** giới hạn riêng để chờ worker phản hồi việc hủy.
- Chỉ đóng tài nguyên được dùng chung **sau khi worker thực sự đã dừng**; nếu không dừng được, báo trạng thái chưa an toàn và để cơ chế điều phối cao hơn xử lý.
- Không biến `cancel(true)`, `shutdownNow()` hay timeout thành lời hứa sai rằng side effect đã được rollback.

Phạm vi là concurrency Java nói chung, dùng API JDK 17; không dựa vào lifecycle hook hoặc cấu hình chuyên biệt của Spring.

## 1. Mô hình và mục tiêu của bài tập

Giả sử dịch vụ xử lý các job nhập dữ liệu. Mỗi job có thể đợi I/O và sử dụng một tài nguyên chung như file writer hoặc connection. Khi có yêu cầu dừng, một bộ điều phối shutdown phải đảm bảo không còn task mới lọt vào executor trong lúc đóng hệ thống.

```text
        RUNNING
     nhận / chạy task
           |
           | nhận tín hiệu dừng
           v
       QUIESCING
     chặn task mới
     executor.shutdown()
           |
           | còn grace time?
           +---------------------------+
           |                           |
     mọi task kết thúc          grace timeout
           |                           |
           v                           v
     TERMINATED                   CANCELLING
                              shutdownNow(), cancel
                                       |
                                chờ force time
                                 /           \
                              dừng          vẫn chạy
                               |               |
                               v               v
                         TERMINATED        NOT_TERMINATED
                               |               |
                               v               v
                         close resources   báo lỗi, không
                         theo thứ tự       đóng tài nguyên
                               |           còn bị worker dùng
                               v
                             CLOSED
```

Ở đây `RUNNING`, `QUIESCING`, `CANCELLING`, `TERMINATED`, `CLOSED` là trạng thái **thiết kế của ứng dụng**, không phải tên state của `ExecutorService`. Executor có `isShutdown()`, `isTerminated()`, nhưng không tự quản lý mọi tài nguyên nghiệp vụ.

**Tiêu chí hoàn thành bài tập:** task mới bị từ chối sau điểm đóng admission; tác vụ hợp tác được ngắt; task còn trong queue không chạy sau escalation; shutdown không chờ vô hạn; tài nguyên được đóng đúng thứ tự; có kết quả phân biệt dừng êm, dừng sau escalation và không dừng được.

## 2. Hiểu đúng các API shutdown và cancellation

| API | Điều đảm bảo / ý nghĩa | Không đảm bảo |
|---|---|---|
| `ExecutorService.shutdown()` | Chuyển executor sang trạng thái không nhận việc mới; thực hiện các task đã nộp trước đó | Không đợi task xong; không ngắt task đang chạy |
| `awaitTermination(timeout, unit)` | Đợi tối đa khoảng cho phép; trả `true` nếu executor đã terminated | `false` không tự hủy task; timeout không dọn tài nguyên |
| `shutdownNow()` | Cố dừng task đang chạy qua `Thread.interrupt()`; ngừng xử lý task đang chờ và trả danh sách task chưa bắt đầu | Không bắt buộc task đang chạy phải dừng; không tự gọi `Future.cancel` cho mọi task trả về |
| `Future.cancel(false)` | Cố hủy task chưa bắt đầu, không yêu cầu interrupt task đang chạy | Không dừng chắc chắn task đã chạy |
| `Future.cancel(true)` | Yêu cầu interrupt thread đang chạy nếu có thể | Không hoàn tác I/O/side effect; task có thể phớt lờ interrupt |
| `Future.get(timeout, unit)` | Giới hạn thời gian **caller đợi kết quả Future** | Không tự giới hạn thời gian CPU/I/O của worker hay tự hủy |
| `AutoCloseable.close()` | Đóng tài nguyên theo hợp đồng của từng lớp | Không tự đảm bảo mọi worker đã ngừng sử dụng tài nguyên |

`shutdown()` là **graceful shutdown** của executor: chờ hoàn thành những gì đã chấp nhận. `shutdownNow()` là **best-effort cancellation**: Java gửi interrupt, nhưng thread chỉ dừng khi tác vụ phản hồi hoặc thao tác blocking bị đánh thức. Một loop bận không kiểm tra cờ interrupted vẫn tiếp tục chạy. Có driver I/O không hỗ trợ interrupt; lúc đó thường cần timeout cụ thể, đóng kênh phù hợp hoặc cơ chế hủy của thư viện đang dùng.

`shutdownNow()` trả các `Runnable` chưa bắt đầu; nếu nộp bằng `submit()`, chúng thường là `RunnableFuture` nên có thể `cancel(false)` để người chờ `Future.get()` không bị treo. Nếu nộp qua `execute()` với `Runnable` thuần, ứng dụng phải có cách riêng để báo trạng thái bị loại. Không giả định các task bị trả về đã hoàn thành.

**Interruption là giao thức hợp tác:** khi một đoạn mã bắt `InterruptedException`, nên kết thúc sớm hoặc ném tiếp. Nếu thật sự phải bắt mà không ném tiếp, đặt lại `Thread.currentThread().interrupt()` để lớp trên vẫn biết tín hiệu hủy. Không nuốt interruption rồi tiếp tục vòng lặp vô hạn.

## 3. Trước khi viết code: thiết kế quyền sở hữu tài nguyên

Một sơ đồ tài nguyên đơn giản:

```text
Shutdown owner
  |
  +-- admission gate (không nhận task mới)
  |
  +-- executor workers
  |       |
  |       +-- sử dụng shared writer / client / connection
  |
  +-- resource owner (đóng sau khi workers dừng)
```

Tài nguyên nào do component tạo thì component đó phải chịu trách nhiệm đóng, hoặc chuyển quyền sở hữu một cách rõ ràng. Nếu mỗi task tự mở một `InputStream` độc lập, dùng `try-with-resources` trong task để đóng đúng scope. Nếu nhiều task cùng dùng chung writer/client, component sở hữu nên chỉ đóng sau khi mọi task đã ngừng dùng.

Khi shutdown nhiều thành phần, thường phải **đóng theo thứ tự phụ thuộc đảo chiều khởi tạo**: dừng nơi sinh công việc trước; cho consumer hoàn tất; flush/commit bản ghi đang chờ theo hợp đồng; sau đó mới đóng writer, client, pool connection và tài nguyên bên dưới. Với logging, giữ logger hoạt động đủ lâu để ghi sự kiện shutdown cuối cùng.

Không nên lấy `finally { resource.close(); }` ở thread quản lý shutdown làm mặc định nếu có thể vẫn còn worker chạy. `finally` hữu ích để giải phóng các tài nguyên chỉ được caller sở hữu, nhưng tài nguyên dùng chung cần **xác nhận không còn người dùng** hoặc có giao thức đóng độc lập an toàn.

## 4. Ví dụ Java 17 hoàn chỉnh: graceful timeout, forced cancellation, resource close

Ví dụ có một executor một worker, một job dài chờ `CountDownLatch`, một job khác đang chờ trong queue và một tài nguyên giả lập dùng chung. Khi bắt đầu shutdown, job đầu không tự hoàn thành trong thời gian grace, nên dịch vụ chuyển sang `shutdownNow()`. Worker hợp tác với interruption; job trong queue bị hủy; khi executor terminated, tài nguyên được đóng. Tên file phải là **`ShutdownPractice.java`**.

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownPractice {
    static final class Resource implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        void checkOpen() {
            if (closed.get()) throw new IllegalStateException("Resource closed");
        }

        boolean isClosed() { return closed.get(); }

        @Override public void close() { closed.set(true); }
    }

    record ShutdownResult(boolean graceful, boolean terminated,
                          int cancelledQueued) {}

    static final class Service {
        private final Object admissionLock = new Object();
        private final Resource resource = new Resource();
        private final ExecutorService workers =
                Executors.newSingleThreadExecutor(r -> new Thread(r, "job-worker"));
        private boolean accepting = true;

        Future<?> submit(Runnable action) {
            synchronized (admissionLock) {
                if (!accepting) throw new RejectedExecutionException("Stopping");
                return workers.submit(() -> {
                    resource.checkOpen();
                    action.run();
                });
            }
        }

        ShutdownResult stop(Duration grace, Duration force)
                throws InterruptedException {
            synchronized (admissionLock) {
                accepting = false;
                workers.shutdown();
            }
            boolean graceful = false;
            int cancelled = 0;
            try {
                graceful = workers.awaitTermination(
                        grace.toNanos(), TimeUnit.NANOSECONDS);
                if (!graceful) {
                    List<Runnable> notStarted = workers.shutdownNow();
                    for (Runnable task : notStarted) {
                        if (task instanceof Future<?> future) {
                            future.cancel(false);
                        }
                        cancelled++;
                    }
                    if (!workers.awaitTermination(
                            force.toNanos(), TimeUnit.NANOSECONDS)) {
                        return new ShutdownResult(false, false, cancelled);
                    }
                }
                resource.close(); // Chỉ đóng sau khi tất cả worker đã dừng.
                return new ShutdownResult(graceful, true, cancelled);
            } catch (InterruptedException e) {
                workers.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }

        boolean resourceClosed() { return resource.isClosed(); }
    }

    public static void main(String[] args) throws InterruptedException {
        Service service = new Service();
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean workerInterrupted = new AtomicBoolean();

        service.submit(() -> {
            started.countDown();
            try {
                new CountDownLatch(1).await(); // Mô phỏng tác vụ dài.
            } catch (InterruptedException e) {
                workerInterrupted.set(true);
                Thread.currentThread().interrupt();
            }
        });
        Future<?> queued = service.submit(() -> {
            throw new AssertionError("Queued task must not run");
        });
        if (!started.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Worker did not start");
        }

        ShutdownResult result = service.stop(
                Duration.ofMillis(100), Duration.ofSeconds(2));
        System.out.println("Graceful: " + result.graceful());
        System.out.println("Terminated: " + result.terminated());
        System.out.println("Queued cancelled: " + queued.isCancelled());
        System.out.println("Worker interrupted: " + workerInterrupted.get());
        System.out.println("Resource closed: " + service.resourceClosed());
        try {
            service.submit(() -> {});
        } catch (RejectedExecutionException e) {
            System.out.println("New task rejected: true");
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac -encoding UTF-8 ShutdownPractice.java
java ShutdownPractice
```

Đầu ra trên đường thực thi bình thường:

```text
Graceful: false
Terminated: true
Queued cancelled: true
Worker interrupted: true
Resource closed: true
New task rejected: true
```

Ví dụ này đã thiết kế các điểm đồng bộ để kết quả có thể kiểm chứng: `started.await()` buộc worker đang thực hiện job chờ vô hạn; queue có job thứ hai; grace hết vì worker chưa hoàn tất; `shutdownNow()` yêu cầu interrupt job đang chạy và trả job chưa chạy; `Future` của job chưa chạy được hủy; `awaitTermination()` xác nhận executor dừng rồi mới đóng `Resource`. Tài nguyên trong ví dụ là **mô phỏng qua `AtomicBoolean`**, không phải file writer hay database connection thật.

Trong code này `Service.stop()` được gọi một lần từ một thread quản lý. Nếu production cho phép nhiều người gọi stop đồng thời, cần thiết kế state/idempotency của shutdown, bảo đảm chỉ một owner điều phối escalation và đóng tài nguyên một lần. `Resource.close()` trong ví dụ đặt flag, còn tài nguyên thật có thể ném `IOException`; cần lưu/báo lỗi đóng theo hợp đồng.

### Vì sao `admissionLock` quan trọng?

Nếu `submit()` chỉ kiểm tra `accepting` bên ngoài khóa, có race:

```text
Thread A: thấy accepting=true
Thread B: set accepting=false; executor.shutdown()
Thread A: executor.submit(...) -> RejectedExecutionException
```

Trong bài thực hành, `submit()` và đoạn `accepting=false; workers.shutdown()` giữ cùng một monitor. Nhờ vậy quyết định nhận việc và bước chuyển sang dừng có một ranh giới đồng bộ rõ. Người gọi vẫn cần nhận diện `RejectedExecutionException` theo hợp đồng, nhất là nếu executor bị shutdown bởi một owner khác hoặc có wrapper bổ sung.

**Không khóa `admissionLock` trong lúc `awaitTermination()`**: chờ dài dưới khóa có thể khiến các đường đi khác cần khóa bị chặn, hoặc deadlock nếu worker cần khóa đó để hoàn tất. Ví dụ chỉ dùng khóa để đổi trạng thái và nộp việc, rồi đợi bên ngoài khóa.

### Tại sao chỉ đóng tài nguyên khi `terminated=true`?

Khi `awaitTermination(force)` trả `false`, có thể vẫn còn worker chạy và còn giữ tham chiếu tới writer/socket/connection. Đóng resource ngay có thể tạo race với ghi dữ liệu, phá transaction hoặc ném lỗi khó hiểu. Demo cố ý trả `ShutdownResult(false, false, ...)` và **không đóng resource** khi worker chưa ngừng. Đây là tín hiệu để tầng quản lý nâng mức xử lý: log sự cố, thu thập stack/thread dump, áp timeout I/O ở layer thực, phối hợp với supervisor hoặc buộc dừng tiến trình theo chính sách vận hành.

Cơ chế này không bảo đảm tất cả trạng thái được flush hay commit thành công: phải xác định rõ với từng job khi nào output có thể coi là bền vững, khi nào cần retry và idempotency để tránh xử lý lặp.

## 5. Task chạy lâu phải hợp tác với cancellation

Một task CPU-bound không blocking phải kiểm tra tín hiệu interruption theo chu kỳ và dừng ở điểm an toàn:

```java
// Đoạn logic minh họa nằm trong Runnable/Callable, không phải file độc lập.
while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()) {
        persistCheckpointIfSafe();
        return;
    }
    processNextChunk();
}
```

Các hàm `hasMoreWork()`, `persistCheckpointIfSafe()`, `processNextChunk()` là placeholder biểu diễn nghiệp vụ, không phải API Java chuẩn. Với blocking API có thể ngắt, ví dụ `BlockingQueue.take()`, `CountDownLatch.await()`, `Thread.sleep()`, `InterruptedException` cho phép thoát. Một pattern phù hợp:

```java
try {
    workBlocking();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} finally {
    releaseTaskOwnedResources();
}
```

Đoạn trên là pseudocode Java có phương thức nghiệp vụ giả định. Nếu tác vụ nhận `InterruptedException` rồi chỉ log và tiếp tục `while(true)`, escalation không có hiệu quả. Không được gọi `Thread.stop()` để ép worker dừng: API này không an toàn, có thể bỏ lock và phá invariant của object.

Cancellation cũng có **ranh giới nghiệp vụ**: một ghi file dở dang cần temp file + rename nguyên tử (nếu filesystem hỗ trợ), hoặc checkpoint/cleanup; một giao dịch database cần rollback/commit đúng chỗ; lời gọi đối tác có thể đã tạo side effect trước khi timeout nên phải có idempotency key và đối soát. Interrupt không thể hoàn tác một khoản thanh toán đã commit.

## 6. Timeout: phân biệt ba lớp

Trong shutdown có ít nhất ba loại timeout:

1. **Grace timeout:** bao lâu cho phép các task đã nhận chạy xong mà không chủ động ngắt.
2. **Force timeout:** bao lâu chờ sau khi gửi yêu cầu cancel/interruption.
3. **Timeout của từng tác vụ/từng I/O:** giới hạn thời gian gọi socket, HTTP, lock hoặc chờ queue ngay cả trước khi có shutdown.

Thời gian grace và force không thay thế timeout I/O. Một task bị kẹt trong thư viện không hỗ trợ interrupt có thể khiến `awaitTermination` tiếp tục trả false. `Future.get(2, SECONDS)` cũng chỉ giới hạn thời gian thread **gọi get** đợi kết quả; worker vẫn có thể chạy sau khi caller hết thời gian. Nếu muốn hủy phải gọi `cancel(true)` và có task hợp tác.

Cân nhắc **deadline tổng** cho shutdown thay vì mỗi bước tự cấp thêm toàn bộ thời gian không giới hạn. Ví dụ ngân sách dừng là 10 giây: 6 giây graceful, 4 giây forced, trừ thời gian đã tiêu; nếu còn nhiều tài nguyên cần đóng, dự trù ngân sách cho flush/close và báo cáo. Đo elapsed time bằng `System.nanoTime()` hoặc API monotonic thích hợp, không dùng `System.currentTimeMillis()` để đo timeout chính xác vì wall clock có thể bị điều chỉnh.

Một điểm tinh tế: `Duration.toNanos()` có thể ném `ArithmeticException` khi duration quá lớn; duration âm cũng không có ý nghĩa cho shutdown. Production nên validate tham số `Duration` ngay từ đầu (không âm, không overflow, hạn mức hợp lý) và chọn precision phù hợp với API.

## 7. Tình huống quan trọng: task vẫn không chịu dừng

Nếu worker bỏ qua interrupt:

```java
// Mã minh họa một tác vụ lỗi; không nên chạy trong demo chính.
while (true) {
    doNonInterruptibleWork();
}
```

Ngay cả `shutdownNow()` cũng chỉ gửi interrupt. `awaitTermination(force)` có thể trả `false`; Java không có cơ chế an toàn để giết riêng một thread đang giữ monitor và dùng shared memory. Trong trường hợp này:

- Đưa trạng thái `NOT_TERMINATED` ra ngoài với số worker/pool còn hoạt động.
- Hạn chế nhận thêm yêu cầu, giữ nguyên tài nguyên còn bị worker dùng để tránh close race.
- Dùng timeout/hủy riêng của downstream nếu API hỗ trợ.
- Thu thập thread dump, stuck-task ID, thread name và elapsed time.
- Nếu quy trình không thể phục hồi, supervisor của tiến trình có thể cần dừng process với deadline và sau đó khởi động lại an toàn.

Không hứa chắc dữ liệu đã được flush khi `close()` chưa hoàn tất hoặc worker vẫn hoạt động. Nếu có task chưa bắt đầu được trả về từ `shutdownNow()`, phân loại task nào có thể bỏ, task nào phải đưa lại vào hàng đợi bền vững. Không tự nộp lại mù quáng: tác vụ bị ngắt có thể đã tạo side effect; retry phải idempotent.

### Nếu chính thread điều phối shutdown bị interrupt

Trong ví dụ, khi `awaitTermination()` ném `InterruptedException`, code gọi `shutdownNow()`, khôi phục interrupt flag và ném tiếp; tài nguyên dùng chung chưa được đóng vì chưa chứng minh worker terminated. Cách này cố tránh close race nhưng **chưa triển khai đầy đủ cơ chế xử lý từng queued Future trong nhánh interrupt**. Một hệ thống production cần supervisor chịu trách nhiệm tiếp quản quá trình đóng, hủy/báo trạng thái cho queued tasks và tiếp tục theo dõi đến khi worker thực sự dừng hoặc tiến trình được dừng bằng chính sách vận hành.

Nếu mục tiêu API không được ném `InterruptedException`, cần quyết định rõ có bỏ qua interruption trong giai đoạn đóng cuối hay không; phải giữ ngân sách thời gian và khôi phục cờ interrupt sau đó. Không nuốt ngoại lệ rồi tuyên bố shutdown hoàn tất.

## 8. Đóng các tài nguyên thật theo đúng thứ tự

| Loại tài nguyên | Ai đóng? | Điều kiện/điểm cần lưu ý |
|---|---|---|
| `ExecutorService` | Owner của executor | `shutdown` → bounded `awaitTermination` → có thể `shutdownNow` |
| `InputStream`, `OutputStream`, `Reader`, `Writer` riêng từng task | Chính task | `try-with-resources`; không chờ manager đóng |
| File writer dùng chung | Owner sau khi worker dừng | Xem xét flush, lỗi close, tính nhất quán khi ghi nhiều thread |
| HTTP client hoặc socket dùng chung | Owner theo lifecycle client | Kiểm tra timeout và close semantics của client cụ thể |
| JDBC `Connection` trong task | Code sở hữu connection | `try-with-resources`; rollback/commit có ý thức |
| Database connection pool | Owner cấp dịch vụ | Ngừng nhận request, đợi in-flight, mới đóng pool |
| `ScheduledExecutorService` | Owner scheduler | Ngừng sinh job mới, xem chính sách hủy periodic/delayed tasks |
| Queue/message consumer | Owner consumer | Stop receiving trước; ack và retry theo delivery semantics |
| Buffer/cache có flush | Owner dữ liệu | Cần thời gian flush riêng và cách xác nhận dữ liệu đã bền vững |

Không phải mọi tài nguyên đều thread-safe khi `close()` cạnh tranh với `use()`. Đọc hợp đồng tài nguyên cụ thể. Một số client cho phép `close()` ngắt kết nối đang chờ, số khác không. Bài này ưu tiên thứ tự **stop producer → drain workers → escalate nếu cần → close downstream** cho tài nguyên có dùng chung.

Với các resource đóng được bằng `AutoCloseable`, dùng `try-with-resources` khi vòng đời lexical phù hợp. Khi shutdown nhiều tài nguyên độc lập, nếu đóng tài nguyên đầu tiên ném exception thì vẫn cần thử đóng những tài nguyên còn lại và gộp/báo lỗi, thay vì bỏ lại mọi connection khác. `try-with-resources` tự quản lý suppressed exceptions theo phạm vi resource khai báo.

## 9. Bài tập mở rộng: thiết kế shutdown ở nhiều thành phần

Giả sử ứng dụng có:

```text
Scheduler -> Producer -> Queue -> Workers -> Database / OutputWriter
                    \-> MetricsExporter
```

Hãy lập thiết kế shutdown với yêu cầu:

1. Khi nhận shutdown signal, scheduler không tạo thêm batch; producer ngừng nhận task.
2. Queue có admission đóng rõ ràng; job đã accepted được xử lý hoặc có trạng thái chưa xử lý để retry an toàn.
3. Workers có `gracePeriod`, được yêu cầu cancel khi hết hạn; mỗi task dùng timeout I/O và interruption.
4. Job cần bền vững có idempotency/receipt để có thể replay sau restart mà không nhân đôi side effect.
5. Chỉ đóng database pool/writer sau khi không còn worker dùng; metrics/logging giữ đủ lâu để ghi kết quả shutdown.
6. Nếu có worker không phản hồi interrupt, ghi nhận trạng thái `NOT_TERMINATED` và để supervisor xử lý theo deadline.
7. Có kiểm thử chứng minh thứ tự đóng, không chỉ dựa trên log nhìn có vẻ hợp lý.

Thiết kế API nên công khai kết quả dạng `ShutdownReport`, ví dụ `graceful`, `terminated`, `cancelledQueued`, `timedOut`, `resourceCloseFailures` và thời gian thực tế. Đặt tên field sao cho `cancelledQueued` chỉ đếm **đã yêu cầu hủy/đã chuyển trạng thái Future** đúng nghĩa; đừng dùng con số đó để kết luận side effect chưa từng xảy ra đối với task đã chạy.

**Bài mở rộng A:** thêm timeout per-job và một trạng thái `CANCEL_REQUESTED` khác với `CANCELLED`. Nếu task đã ghi vào database nhưng bị interrupt trước khi ack, chỉ định cách retry không tạo bản ghi trùng.

**Bài mở rộng B:** thay `Resource` giả lập bằng `BufferedWriter` ghi vào file tạm, mỗi task tự tạo một dòng đã định dạng. Dùng khóa hoặc chiến lược ghi thread-safe phù hợp, và kiểm chứng `close()` không xảy ra trước khi worker cuối cùng kết thúc. Không ghi chung writer từ nhiều thread nếu API không bảo đảm thread safety.

**Bài mở rộng C:** cho nhiều caller cùng gọi stop; thiết kế `AtomicReference<State>` hoặc lock để chỉ một tiến trình shutdown thực hiện escalation/close, những caller khác chờ cùng kết quả. Cần tránh deadlock giữa `submit`, `stop` và worker callback.

## 10. Bộ kiểm thử chấp nhận (acceptance tests)

| Kịch bản | Hành vi đúng |
|---|---|
| Không có task, gọi stop | Executor terminated, tài nguyên đóng |
| Mọi task hoàn tất trong grace | Không cần `shutdownNow`; `graceful=true` |
| Có task đang chờ interruptible | Grace hết, interruption làm worker dừng; resource đóng sau termination |
| Task ở queue chưa bắt đầu | Sau `shutdownNow`, không chạy; Future/receipt thể hiện trạng thái hủy |
| Submit cạnh tranh với stop | Chỉ nhận trước điểm admission đóng; sau đó nhận rejection rõ ràng |
| Worker ném RuntimeException | Không giữ tài nguyên task; shutdown vẫn thực hiện và lỗi được báo |
| Worker phớt lờ interrupt | Force timeout, `terminated=false`; không tuyên bố resource đã đóng an toàn |
| Thread điều phối shutdown bị interrupt | Không coi là completed; có supervisor tiếp tục cleanup |
| Close resource ném exception | Lỗi close được báo, không làm mất thông tin task chưa kết thúc |
| Hai lần stop cạnh tranh | Một quá trình đóng, không double-close/hủy không nhất quán |
| Tác vụ có side effect rồi timeout | Retry có idempotency/reconciliation; cancellation không được hiểu là rollback |
| Có nhiều executor và scheduler | Dừng đúng thứ tự phụ thuộc, không sinh task mới vào executor đã đóng |

Để kiểm thử không phụ thuộc lịch chạy thread, dùng `CountDownLatch`, `CyclicBarrier` hoặc đồng bộ có kiểm soát để tạo tình huống cần kiểm tra. Tránh `Thread.sleep()` tùy ý làm cách duy nhất để “đợi chắc task đã chạy”. Dùng timeout trên tất cả `await()` quan trọng trong test để tránh treo toàn bộ CI.

Theo dõi khi shutdown thực tế: số task accepted, completed, cancelled, queued, active, số task còn chạy lúc timeout; thời gian graceful và forced; tài nguyên đóng thành công hay lỗi; ID job chưa xử lý. Số lượng `Future` đã cancel không tự chứng minh side effect đã rollback; phải kết hợp trạng thái nghiệp vụ và transaction.

## 11. Lỗi thiết kế thường gặp

- **Gọi `shutdown()` rồi cho rằng executor đã dừng:** `shutdown()` chỉ từ chối task mới, không đợi kết thúc.
- **Đợi vô hạn:** một tác vụ kẹt I/O khiến tiến trình không thể dừng theo deadline.
- **Gọi `shutdownNow()` rồi đóng writer ngay:** interrupt chỉ là yêu cầu hợp tác; worker có thể vẫn ghi.
- **Bỏ qua các `Runnable` trả về từ `shutdownNow()`:** job chưa chạy không có kết quả/hợp đồng rõ, `Future.get()` có thể treo.
- **Đóng resource trong `finally` của shutdown owner bất chấp `isTerminated()`:** race với worker chưa dừng.
- **Nuốt `InterruptedException`:** bỏ tín hiệu hủy, khiến escalation không hiệu quả.
- **Chỉ đặt timeout ở `Future.get()`:** thread đợi được giải phóng nhưng worker và I/O vẫn có thể chạy mãi.
- **Không chặn admission trước khi drain:** producer tiếp tục tạo task trong lúc consumer tắt.
- **Dùng `Thread.stop()`:** có thể phá invariant dữ liệu và lock.
- **Không phân biệt cancelled với rolled back:** task đã thực hiện side effect có thể được retry và nhân đôi.
- **Đóng tài nguyên theo thứ tự ngẫu nhiên:** dependency còn đang sử dụng đã bị đóng trước.
- **Không xử lý shutdown đồng thời:** nhiều caller gọi stop có thể lặp close hoặc báo trạng thái mâu thuẫn.

## 12. Kết luận và checklist triển khai

Khi thiết kế shutdown Java an toàn, trả lời đủ các câu hỏi:

1. Ai sở hữu quyền nhận task, ai sở hữu executor và ai sở hữu từng tài nguyên?
2. Điểm nào bảo đảm task mới không thể lọt vào sau khi bắt đầu dừng?
3. Grace timeout và force timeout là bao nhiêu, căn cứ theo workload và SLA nào?
4. Task có hợp tác interruption không; tất cả blocking I/O có timeout phù hợp không?
5. Task nằm trong queue được hủy/báo lỗi như thế nào; có cần bền vững qua restart không?
6. Trạng thái nào xác nhận worker đã dừng trước khi resource close?
7. Khi worker không dừng, ai tiếp quản escalation và đảm bảo tiến trình không treo?
8. Shutdown report có phân biệt graceful, forced, timed out, cancelled và close failure không?
9. Có kiểm thử interleaving và fault injection cho race, exception, cancellation và resource close không?

**Điểm mấu chốt:** shutdown là một **giao thức phối hợp nhiều giai đoạn**, không phải một lệnh đơn lẻ. Chặn công việc mới, cho việc cũ cơ hội hoàn tất, yêu cầu hủy khi hết thời gian, xác minh termination và chỉ sau đó đóng tài nguyên. Khi giới hạn timeout không đủ để dừng một worker, hãy báo đúng trạng thái chưa hoàn tất và dùng chiến lược phục hồi ngoài thread, thay vì đóng tài nguyên sớm hoặc tuyên bố đã dừng an toàn.
