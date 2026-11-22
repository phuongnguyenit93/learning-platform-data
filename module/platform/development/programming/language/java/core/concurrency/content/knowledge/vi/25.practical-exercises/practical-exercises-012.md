# Tổng kết checklist: thread safety, cancellation, observability

> Phạm vi: concurrency trong **Java SE 17+**. Đây là checklist thực hành để thiết kế, rà soát, kiểm thử và vận hành mã chạy đồng thời bằng `Thread`, `ExecutorService`, `Future`, `Lock`, các lớp `java.util.concurrent` và API giám sát JVM. Các khái niệm áp dụng cho Java nói chung, không phụ thuộc vào Spring.

## 1. Mục tiêu: một tác vụ đồng thời được coi là “đúng” khi nào?

Một chương trình có thể cho ra đáp án đúng trong vài lần chạy nhưng vẫn sai về concurrency: kết quả có thể hỏng khi nhiều thread cùng truy cập, tác vụ bị hủy nhưng không dừng, hoặc sự cố xuất hiện mà không có thông tin để truy vết.

Ba trụ cột cần được kiểm tra **cùng lúc**:

| Trụ cột | Câu hỏi phải trả lời | Bằng chứng chấp nhận |
| --- | --- | --- |
| **Thread safety** | Có data race, lost update, đọc trạng thái chưa công bố an toàn hoặc bất biến bị vi phạm không? | Sơ đồ ownership của trạng thái; cơ chế happens-before; test bất biến dưới cạnh tranh |
| **Cancellation** | Ai có quyền hủy, hủy được truyền qua những lớp nào, công việc có ngừng và giải phóng tài nguyên không? | Chính sách interrupt/deadline; test cancel trước, trong và sau khi chạy; tín hiệu hoàn tất cleanup |
| **Observability** | Khi chậm/treo/lỗi có thể biết task đang ở đâu, chờ bao lâu, bị hủy vì sao và worker còn sống không? | Metrics, logs, thread dumps/JFR theo tình huống, có correlation và không lộ dữ liệu nhạy cảm |

**Không đủ** nếu chỉ nói “dùng `AtomicInteger`”, “gọi `future.cancel(true)`” hay “đã có log”. Phải xác minh **toàn bộ vòng đời**: tạo công việc → chấp nhận → xếp hàng → bắt đầu → chạy → hoàn tất/thất bại/hủy → cleanup → ngừng worker/executor.

## 2. Checklist thread safety: xác định trạng thái, người sở hữu và visibility

### 2.1. Nhận diện shared mutable state

- [ ] Liệt kê tất cả dữ liệu có thể được **nhiều thread đọc/ghi**: field, cache, collection, counter, connection/session, hàng đợi, flags.
- [ ] Phân biệt **thread-confined** (chỉ một thread sở hữu), **immutable** (bất biến sau khởi tạo) và **shared mutable**.
- [ ] Mỗi dữ liệu shared mutable đều có chính sách bảo vệ rõ: lock, atomic, concurrent collection, message passing hoặc ownership chuyển giao.
- [ ] Không đưa object mới tạo tới thread khác trước khi object được xây dựng xong và **safe publication** hoàn tất.
- [ ] Mỗi compound action như “kiểm tra rồi cập nhật”, “đọc rồi tăng”, “lấy tiền nếu đủ số dư” được bảo vệ **nguyên khối**, không chỉ từng bước riêng lẻ.
- [ ] Các phương thức gọi callback bên ngoài không chạy dưới lock quá rộng nếu callback có thể chặn hoặc gọi ngược (reentrant).
- [ ] Đã xác định thứ tự lấy nhiều lock để tránh vòng chờ; không giữ lock trong lúc gọi I/O chậm nếu tránh được.

**Ví dụ lỗi lost update:**

```java
// Hai thread cùng thực thi có thể làm mất cập nhật.
private int completed;
void markDone() {
    completed++; // đọc → cộng → ghi, không nguyên tử
}
```

Nếu yêu cầu chỉ là một số đếm độc lập:

```java
private final AtomicInteger completed = new AtomicInteger();
void markDone() {
    completed.incrementAndGet();
}
```

Hai đoạn trên là **mã minh họa bên trong class**, không phải chương trình độc lập. Cần import `java.util.concurrent.atomic.AtomicInteger`. Khi cần cập nhật **nhiều field phải nhất quán với nhau**, không mặc định thay mỗi field bằng một atomic là đủ.

### 2.2. `volatile`, atomic và lock dùng để làm gì?

| Công cụ | Dùng cho | Không tự giải quyết |
| --- | --- | --- |
| `volatile` | Cờ trạng thái, publication/visibility cho một biến; quan hệ happens-before giữa volatile write và read phù hợp | `count++` hoặc bất biến đa trường |
| `AtomicInteger`, `AtomicReference` | CAS, get/set, phép cập nhật nguyên tử trên một biến | Transaction giữa nhiều atomic |
| `synchronized` / `ReentrantLock` | Bảo vệ đoạn tới hạn và invariant nhiều bước | Hiệu năng khi giữ khóa lâu; deadlock nếu thứ tự khóa sai |
| `ConcurrentHashMap` | Truy cập map đồng thời và những thao tác nguyên tử do API cung cấp | Quy trình nhiều bước bên ngoài map mà không có phối hợp |
| `BlockingQueue` | Truyền dữ liệu thread-safe theo producer–consumer và điều khiển số phần tử chờ | Deadline, giới hạn tổng công việc, xử lý lỗi nghiệp vụ |
| `CountDownLatch`, `Semaphore` | Phối hợp vòng đời/số lượng công việc | Thay thế khóa cho mọi bất biến ứng dụng |
| Immutable object | Chia sẻ trạng thái không thể sửa | Safe publication của các object có thể thay đổi được lồng bên trong |

**Happens-before** là quy tắc về thứ tự và visibility của Java Memory Model. Ví dụ: mở khóa monitor happens-before lần khóa tiếp theo của cùng monitor; ghi vào biến `volatile` happens-before lần đọc tiếp theo của biến đó; hành động trước `CountDownLatch.countDown()` được thấy bởi thread vượt qua `await()` tương ứng. Lệnh `Thread.sleep()` **không tạo quan hệ happens-before** chỉ vì đã đợi đủ lâu.

### 2.3. Phân tích ownership ở ranh giới async

Một trường hợp dễ bỏ qua: method chạy trên thread caller tạo object rồi truyền vào `executor.submit(...)`. Theo memory-consistency contract của `ExecutorService`, các hành động trước khi submit happens-before hành động trong task; và hành động của task happens-before code sau `Future.get()` trả kết quả tương ứng. Điều này **không** khiến collection do caller tiếp tục sửa song song tự nhiên an toàn.

Ví dụ anti-pattern:

```java
List<String> shared = new ArrayList<>();
executor.submit(() -> shared.add("worker"));
shared.add("caller"); // có thể chạy đồng thời, ArrayList không thread-safe
```

Đây là đoạn minh họa, cần import `java.util.ArrayList` và `java.util.List` cùng biến `executor` đang hoạt động. Cách sửa tùy yêu cầu: chỉ một thread sở hữu collection, trả về kết quả qua `Future`, dùng concurrent collection phù hợp hoặc bảo vệ **mọi** lần truy cập bằng cùng lock.

## 3. Checklist cancellation: hợp đồng hủy rõ ràng và có giới hạn thời gian

### 3.1. Tách yêu cầu hủy khỏi xác nhận tác vụ đã dừng

- [ ] Định nghĩa ai có thể yêu cầu cancel: caller, supervisor, timeout, shutdown hoặc quy tắc nghiệp vụ.
- [ ] Phân biệt “**đã yêu cầu hủy**”, “**Future được đánh dấu cancelled**” và “**code tác vụ thực sự đã dừng và cleanup xong**”.
- [ ] Nếu cần dừng task đang chạy, dùng `Future.cancel(true)` khi phù hợp, nhưng xem interrupt là **yêu cầu hợp tác**, không phải lệnh kill cưỡng bức.
- [ ] Các vòng lặp dài có điểm kiểm tra cờ hủy / interrupt và các blocking call có đường thoát.
- [ ] Khi bắt `InterruptedException`, thường **thoát hoặc truyền tiếp**; nếu không truyền lại, khôi phục cờ bằng `Thread.currentThread().interrupt()`.
- [ ] Không `catch(Exception)` rồi tiếp tục chạy vô hạn, vô tình nuốt `InterruptedException`.
- [ ] Các resource được giải phóng trong `finally` hoặc `try-with-resources`, kể cả khi exception/cancel xảy ra.
- [ ] Timeout cho *việc chờ kết quả* không tự động hủy công việc đang chạy: có hành động riêng cho task còn sống.
- [ ] Không hứa cancel dừng ngay mọi API I/O: phụ thuộc khả năng interrupt của API và driver cụ thể.
- [ ] Sau shutdown, có chính sách chờ một khoảng hữu hạn, ghi nhận task còn tồn và phương án xử lý an toàn.

**Hợp đồng của `Future`:**

- `cancel(false)` cố hủy task nhưng không yêu cầu interrupt task đang thực thi.
- `cancel(true)` cố hủy task và yêu cầu interrupt thread đang thực thi **nếu đã biết thread**; task có thể bỏ qua interrupt hoặc làm cleanup lâu.
- `isCancelled()` cho biết trạng thái cancellation của `Future`; `isDone()` trả `true` khi kết thúc bình thường, lỗi hoặc bị hủy.
- `get()` trên `Future` đã hủy ném `CancellationException`.
- `get(timeout, unit)` quá hạn ném `TimeoutException`, **không tự động gọi `cancel()`**.
- `cancel(true)` trả về `true` không đủ chứng minh cleanup đã hoàn tất. Cần cơ chế completion/termination cụ thể nếu điều này là yêu cầu của ứng dụng.

### 3.2. Chính sách khi interrupt

Với tác vụ ngủ hoặc chờ `BlockingQueue.take()`, `CountDownLatch.await()`, `Thread.sleep()`, interrupt thường kích hoạt `InterruptedException`. Ngoại lệ này thông thường **xóa interrupt status** trước khi bị bắt. Nếu task không thể `throws InterruptedException`, bắt rồi khôi phục flag và thoát là lựa chọn hợp lý:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đoạn trên là minh họa bên trong một method, với `queue` là `BlockingQueue` hợp lệ. Cần phân biệt trường hợp hủy với trường hợp ứng dụng muốn retry: không retry vô hạn sau interrupt, vì có thể làm task không bao giờ dừng. Với API không hỗ trợ interrupt, thiết kế thêm deadline, close socket/channel nếu được hỗ trợ hoặc cờ hủy có vòng kiểm tra hợp lý.

### 3.3. Dừng executor đúng vòng đời

`ExecutorService.shutdown()` ngừng nhận task mới và cho những task đã nhận tiếp tục xử lý; **không chờ tự động**. `shutdownNow()` cố interrupt các task đang chạy và trả lại danh sách task chưa bắt đầu, nhưng không bảo đảm tất cả task chấm dứt. `awaitTermination(timeout, unit)` có giới hạn thời gian đợi. Với công việc quan trọng, cần quyết định xử lý task chưa bắt đầu: đánh dấu thất bại, lưu lại bền vững, hay báo cho caller, tùy nghiệp vụ.

Bảo đảm cleanup theo một thứ tự dễ hiểu:

```text
Yêu cầu hủy / shutdown
   ↓
Ngừng nhận task mới
   ↓
Truyền interrupt/deadline tới task thích hợp
   ↓
Task thoát vòng lặp, chạy finally, nhả resource
   ↓
Quan sát task đã dừng + executor đã terminate
   ↓
Báo kết quả/cập nhật trạng thái cuối
```

Chính sách không giống nhau cho **graceful shutdown** (ưu tiên hoàn tất việc đã nhận) và **forced cancellation** (ưu tiên dừng càng sớm càng tốt). Chọn rõ trước khi đưa vào vận hành.

## 4. Checklist observability: biết hệ thống đang làm gì

### 4.1. Log có ngữ cảnh

- [ ] Log ít nhất các sự kiện có ý nghĩa: submit/accepted, started, completed, failed, cancel requested, cancel observed, timeout, rejected.
- [ ] Mỗi task quan trọng có **task ID / correlation ID** ổn định từ lúc tạo đến khi kết thúc.
- [ ] Log chỉ rõ **trạng thái** và **lý do** (ví dụ timeout, shutdown, upstream error), thay vì chỉ in `Exception.toString()`.
- [ ] Lỗi có stack trace đúng thời điểm; không bỏ im lặng lỗi khi chạy bất đồng bộ.
- [ ] Đặt tên thread/pool có ý nghĩa; tránh phụ thuộc tên thread làm định danh duy nhất của một task.
- [ ] Không ghi payload nhạy cảm, khóa bí mật hoặc dữ liệu cá nhân vào log và thread name.
- [ ] Giới hạn số log per-item trong tải cao, tránh log trở thành nguyên nhân bão hòa I/O.

Với `ExecutorService.submit()`, ngoại lệ của `Callable`/`Runnable` được giữ trong `Future`; nếu không gọi `get()` hoặc không có đường quan sát thất bại, lỗi có thể bị **bỏ sót** trong monitoring. `execute()` và `submit()` có hành vi truyền lỗi khác nhau, cần chọn đường thu thập phù hợp.

### 4.2. Metrics bắt buộc để phân biệt tắc nghẽn

| Nhóm | Metric | Dùng để trả lời |
| --- | --- | --- |
| Vòng đời | submitted / accepted / started / completed / failed / cancelled / rejected | Công việc bị mất hoặc dừng ở giai đoạn nào? |
| Thời gian | queue wait, execution time, total latency, timeout rate | Chậm do xếp hàng hay do chạy? |
| Pool | active threads, pool size, queue size, completed task count | Worker có bão hòa không? |
| Cạnh tranh | contention/blocked time, deadlock observations | Thread có chờ nhau vì lock? |
| Tài nguyên | CPU, heap, GC, connection/FD usage | Giới hạn phần cứng/runtime hay nghiệp vụ? |

Số đếm phải có **định nghĩa không chồng lấn**. Ví dụ `submitted` đếm yêu cầu gửi đến executor; `accepted` chỉ các task được executor nhận; `rejected` là bị pool từ chối. Một task đã accepted vẫn có thể bị cancelled trước khi chạy. Không suy luận `completed = submitted - rejected - cancelled` nếu chưa định nghĩa rõ thời điểm hoàn tất, retry, chạy ở caller và task bị bỏ bằng discard policy.

Dùng `System.nanoTime()` để đo **duration** bằng cách lấy chênh lệch hai lần đọc, không dùng giá trị tuyệt đối như timestamp hay cộng duration với epoch. Đo p50/p95/p99 thay vì chỉ trung bình; saturation có thể làm tail latency tăng mạnh dù throughput trung bình còn tương đối tốt.

Các getter như `ThreadPoolExecutor.getActiveCount()`, `getQueue().size()` và `getCompletedTaskCount()` là ảnh chụp **gần đúng**, không phải dữ liệu nguyên tử của cùng một thời điểm. Dùng theo xu hướng, không làm điều kiện nghiệp vụ kiểu “nếu queue size còn 1 thì chắc chắn submit sẽ nhận”.

### 4.3. Khi nào lấy thread dump và JFR?

- **Thread dump:** chậm/treo, nhiều thread `BLOCKED`, nghi ngờ deadlock, worker chờ `Future.get()` hoặc task đợi queue. Dùng `jcmd <pid> Thread.print -l -e`; có thể dùng `jstack -l <pid>` trên JDK hỗ trợ.
- **`ThreadMXBean`:** lấy trạng thái platform threads và một số số liệu CPU/blocked time; kiểm tra `isThreadCpuTimeSupported()`, `isThreadContentionMonitoringSupported()` trước khi bật tính năng có overhead.
- **Java Flight Recorder (JFR):** xem xu hướng và các sự kiện theo thời gian để điều tra contention, CPU, allocation hoặc các điểm dừng phù hợp; chọn cấu hình ghi và thời lượng theo chi phí vận hành.
- **Heap/GC metrics:** khi queue kéo dài làm giữ nhiều `Runnable` hoặc object closure, kiểm tra áp lực heap và GC, không chỉ tăng kích thước pool.

Một dump là **snapshot**: `WAITING` có thể chỉ là worker nhàn rỗi, `RUNNABLE` chưa chắc đang sử dụng CPU, `BLOCKED` phản ánh chờ intrinsic monitor chứ không bao trùm toàn bộ contention của `ReentrantLock`. Lấy nhiều mẫu trong khoảng phù hợp và đối chiếu với progress metrics.

**Java 21 và virtual threads:** `ThreadMXBean` chuẩn quản lý platform threads, không liệt kê toàn bộ virtual threads. Vì vậy `getThreadCount()` và `findDeadlockedThreads()` không đủ để chẩn đoán tổng số hoặc các chu kỳ có virtual threads. Khi ứng dụng dùng virtual threads, kiểm tra công cụ dump/JFR tương thích với **phiên bản JDK thực tế**. Ví dụ runnable ở bài này sử dụng Java 17 và platform thread thông thường.

## 5. Ví dụ runnable: hủy an toàn và kiểm chứng cleanup

Bài thực hành sau dùng **một worker**, hai tín hiệu chờ và bộ đếm atomic. Task báo đã bắt đầu, sau đó đợi một latch không được mở. Caller yêu cầu `Future.cancel(true)`. Task nhận interrupt, thực hiện cleanup, cập nhật metrics, rồi kết thúc. Ta chờ `finished` trước khi xác nhận dọn dẹp để tránh kết luận sớm chỉ từ `Future.isDone()`.

Lưu thành **`CancellationObservationDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CancellationObservationDemo {
    static final class BlockingJob implements Runnable {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch waitForRelease = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);
        final AtomicBoolean interruptObserved = new AtomicBoolean();
        final AtomicInteger cleanupCount = new AtomicInteger();

        @Override
        public void run() {
            try {
                started.countDown();
                waitForRelease.await();
            } catch (InterruptedException e) {
                interruptObserved.set(true);
                Thread.currentThread().interrupt();
            } finally {
                cleanupCount.incrementAndGet();
                finished.countDown();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "review-worker"));
        BlockingJob job = new BlockingJob();
        try {
            Future<?> result = executor.submit(job);
            if (!job.started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Job did not start");
            }

            boolean cancellationAccepted = result.cancel(true);
            if (!job.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Job did not clean up");
            }

            System.out.println("cancellationAccepted=" + cancellationAccepted);
            System.out.println("futureCancelled=" + result.isCancelled());
            System.out.println("interruptObserved=" + job.interruptObserved.get());
            System.out.println("cleanupCount=" + job.cleanupCount.get());
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy trên JDK 17+:

```bash
javac CancellationObservationDemo.java
java CancellationObservationDemo
```

Stdout (được kiểm tra với OpenJDK 24, sử dụng chỉ API có trong Java 17):

```text
cancellationAccepted=true
futureCancelled=true
interruptObserved=true
cleanupCount=1
```

### 5.1. Vì sao ví dụ tránh race trong phép kiểm tra?

1. `started.countDown()` báo worker đã bắt đầu. `started.await()` ở caller bảo đảm task đã vào `run()` trước khi caller thử cancel.
2. `waitForRelease.await()` không bao giờ được mở bình thường. Dù interrupt đến ngay trước hoặc trong lời gọi `await()`, task đều có đường thoát qua `InterruptedException`.
3. `cancel(true)` cố interrupt worker. Nếu task còn hoạt động, cờ được nhận trong `catch`; nhánh `finally` chạy và giảm `finished`.
4. Caller đợi `finished.await()` thành công rồi mới đọc `interruptObserved` và `cleanupCount`. Đây là bằng chứng cleanup đã chạy **trong ví dụ**, không suy luận từ `Future.isDone()`.
5. `AtomicBoolean` và `AtomicInteger` biểu diễn metric an toàn khi truy cập khác thread; latch còn tạo quan hệ happens-before qua `countDown`/`await`.
6. `finally` ở `main` thực hiện `shutdownNow()` và đợi kết thúc executor để ngăn rò rỉ worker khi kiểm thử thất bại.

Trong ứng dụng thật, `waitForRelease` là tài nguyên/thao tác chờ có điều kiện hữu hạn; latch đóng vĩnh viễn chỉ dùng để tạo tình huống kiểm thử chắc chắn. Nếu `await()` timeout, chương trình ném lỗi rõ thay vì ghi kết quả như đã thành công. Khi nhiều task cùng chạy, cần quản lý quyền sở hữu cancellation, tránh một caller hủy nhầm task của người khác.

### 5.2. Những gì ví dụ **không** chứng minh

- `Future.cancel(true)` không bảo đảm mọi tác vụ nhận interrupt: task có thể chạy I/O không interruptible hoặc tự nuốt interrupt.
- `cleanupCount=1` không chứng minh resource ngoài ứng dụng đã đóng; phải kiểm tra close/commit/rollback cụ thể.
- Bộ đếm atomic trên từng field không tạo snapshot nhất quán cho hàng chục metrics. Dùng immutable snapshot dưới lock khi cần invariant nhiều trường.
- `newSingleThreadExecutor` dùng queue không giới hạn thực tế: chỉ phù hợp demo nhỏ đã kiểm soát số công việc. Ứng dụng nhận tải liên tục nên cân nhắc queue bounded, admission control và rejection policy có phản hồi.
- Chương trình không tự cung cấp distributed tracing hay log aggregation; đó là trách nhiệm của môi trường vận hành.

## 6. Checklist kiểm thử: từ invariant đến cancellation race

| Tình huống | Cách dựng có kiểm soát | Điều cần assert |
| --- | --- | --- |
| Lost update | Nhiều task cùng tăng counter, chờ `CountDownLatch` start gate | Tổng cuối đúng với số phép tăng |
| Compound invariant | Nhiều thread chuyển giá trị giữa hai field | Tổng bảo toàn và không có trạng thái trung gian sai khi snapshot |
| Safe publication | Task được submit sau khi cấu hình object hoàn chỉnh | Không đọc cấu hình cũ/chưa khởi tạo |
| Cancel trước khi chạy | Giữ worker bận, submit task mới rồi cancel `Future` của task chờ | Task không thực thi body, trạng thái cancelled |
| Cancel trong lúc chờ | Task đang `BlockingQueue.take()`/`await()`, gọi `cancel(true)` | Task ghi nhận interrupt, cleanup và dừng |
| Cancel sau khi hoàn thành | `Future.get()` thành công, sau đó gọi `cancel(true)` | `cancel` không biến task hoàn thành thành cancelled |
| Timeout nhưng không cancel | `get(timeout)` trên task chờ | `TimeoutException`; task vẫn có thể chạy |
| Exception trong task | `Callable` ném exception, caller gọi `get()` | `ExecutionException` chứa nguyên nhân |
| Shutdown | Đóng executor khi đang có task | Không nhận task mới; các task đang chạy có vòng đời và deadline rõ |
| Saturation | Worker bận và queue bounded đầy | Rejection được xử lý/đếm; không mất task âm thầm |
| Observability | Tạo task ID, cố tình lỗi/hủy | Log/metric khớp đường đi, không lộ dữ liệu nhạy cảm |

### 6.1. Làm test concurrency đáng tin cậy

Dùng `CountDownLatch`, `CyclicBarrier`, `Phaser` hoặc các primitive phù hợp để sắp xếp đúng điểm tranh chấp. `Thread.sleep(100)` chỉ tạo độ trễ, **không bảo đảm** hai thread đang chạm cùng dữ liệu. Thêm timeout hữu hạn cho tất cả thao tác đợi trong test; nếu quá hạn, báo thất bại và dọn executor trong `finally`.

Các test phải kiểm tra **invariant và hậu quả thực tế**; chạy 1.000 vòng không thể chứng minh một chương trình không có data race. Test stress có ích để tìm race, nhưng không thay thế lập luận về JMM, ownership, safe publication và tính nguyên tử.

Một chiến lược hiệu quả là thiết kế phần tính toán thuần (pure computation) độc lập khỏi việc lập lịch, sau đó chỉ kiểm thử đồng thời ở ranh giới shared state/cancellation. Tránh làm test phụ thuộc tên thread, số thứ tự scheduling hoặc thứ tự log không có quan hệ happens-before.

### 6.2. Kiểm thử failure path cũng cần observability

Nếu task ném exception khi cleanup, chính sách ứng dụng phải quyết định lỗi cuối nào được trả cho caller và lỗi bổ sung được ghi ở đâu. Không nuốt ngoại lệ chỉ để test kết thúc “xanh”. Khi task bị hủy, phân biệt **cancel requested** và **cleanup completed** ở metric; nếu chỉ nhìn `Future.isCancelled()`, bạn có thể đánh giá sai thời gian tài nguyên còn bị chiếm.

Với `CompletionService` hoặc `CompletableFuture`, xác minh completion handlers có đường xử lý cả kết quả, exception và cancellation. Trong callback async, tránh thực hiện tác vụ chặn kéo dài trên executor dùng chung nếu có thể dẫn đến starvation.

## 7. Checklist review thiết kế trước khi merge

### 7.1. Thread safety — câu hỏi bắt buộc

- [ ] Tôi biết thread nào tạo, đọc, sửa và hủy từng trạng thái.
- [ ] Không có `ArrayList`, `HashMap` hay field mutable được nhiều thread cập nhật không bảo vệ.
- [ ] Các đường xuất bản object, `Future.get()` và synchronization đều có happens-before cụ thể.
- [ ] Mọi invariant nhiều bước được bảo vệ bằng một cơ chế nhất quán.
- [ ] Không giữ lock trong I/O chậm hoặc callback không kiểm soát; thứ tự lấy lock rõ ràng.
- [ ] Không suy luận “thread-safe” chỉ từ việc chạy qua một lần test.

### 7.2. Cancellation — câu hỏi bắt buộc

- [ ] Chủ sở hữu và quyền hủy task/pool được xác định.
- [ ] Có phân biệt timeout, exception, shutdown và explicit cancel.
- [ ] Task hợp tác với interrupt/deadline; lỗi interrupt không bị nuốt.
- [ ] Resource được dọn dù task thành công, thất bại hoặc bị hủy.
- [ ] Caller có thể nhận kết quả cuối cùng hoặc lý do thất bại phù hợp.
- [ ] Nếu yêu cầu xác nhận task đã dừng, có completion signal riêng; không chỉ dựa `Future.isDone()`.
- [ ] Executor được shutdown và await termination với deadline phù hợp.

### 7.3. Observability — câu hỏi bắt buộc

- [ ] Có định danh task, tên pool/thread có ích và log trạng thái đầu/cuối.
- [ ] Có số đếm accepted/completed/failed/cancelled/rejected với định nghĩa rõ.
- [ ] Đo queue wait, execution time, timeout và tail latency khi có tải.
- [ ] Có đường chụp thread dump/JFR và xem lock contention khi có sự cố.
- [ ] Có kiểm soát overhead của metrics/logging và dữ liệu nhạy cảm.
- [ ] Dashboard/alert phân biệt backlog tạm thời và saturation kéo dài.

**Điều kiện chấp nhận:** một reviewer khác có thể mô tả được *trạng thái nào được chia sẻ, hủy bằng cơ chế nào, sau khi hủy phải quan sát tín hiệu gì, và thu thập bằng chứng nào khi hệ thống không tiến triển* mà không cần đoán từ tên phương thức.

## 8. Tình huống áp dụng: worker xử lý công việc từ queue

Giả sử một service Java nhận sự kiện từ producer, đưa vào `ThreadPoolExecutor`, worker cập nhật trạng thái và gọi hệ thống bên ngoài. Ba trụ cột liên hệ trực tiếp:

| Hiện tượng | Thread safety | Cancellation | Observability |
| --- | --- | --- | --- |
| Producer gửi sự kiện trùng | Trạng thái xử lý/idempotency an toàn dưới cạnh tranh | Hủy bản sao không còn giá trị theo chính sách | Đếm duplicate và kết quả bỏ qua |
| Worker giữ lock lúc gọi I/O | Có thể làm thread khác chờ khóa | Interrupt có thể không dừng I/O ngay | Thread dump, blocked time, dependency latency |
| Queue tăng liên tục | Queue đúng cấu trúc nhưng không tạo throughput | Deadline làm task cũ không còn giá trị | Queue wait p95/p99, active count, rejected |
| Caller timeout rồi retry | Có thể xử lý trùng hai lần | Cần quyết định hủy task gốc hay tiếp tục | Correlation ID, timeout, retry count |
| Shutdown đang chạy | Trạng thái closing phải công bố an toàn | Ngừng nhận việc và xử lý task còn sống | Outstanding, cleanup completed, termination |

Một phương án vận hành ban đầu hợp lý gồm queue **bounded**, phản hồi rejection rõ, timeout cho external I/O, trạng thái cancel/shutdown có ownership, và metrics theo từng giai đoạn. Cấu hình thread/queue cụ thể phải qua thử tải; tăng kích thước queue đơn thuần có thể khiến task hoàn tất quá hạn và tăng bộ nhớ bị giữ.

## 9. Những lỗi hay bị bỏ sót trong checklist

**1. “Dùng concurrent collection là mọi quy trình đều an toàn.”** Một `ConcurrentHashMap` bảo vệ các thao tác API riêng lẻ; việc “kiểm tra không tồn tại → gọi I/O → ghi vào map” vẫn có thể chạy lặp. Cần `computeIfAbsent`, lock, single flight, hoặc thiết kế giao dịch/idempotency theo yêu cầu.

**2. “`volatile` làm tăng biến nguyên tử.”** `volatile int count` không biến `count++` thành atomic; dùng `AtomicInteger.incrementAndGet()` hoặc khóa.

**3. “`cancel(true)` có nghĩa task đã thoát.”** Nó yêu cầu hủy và có thể interrupt. `Future` có thể chuyển trạng thái cancelled trước khi `finally` của task kết thúc; muốn chứng minh cleanup cần chờ riêng.

**4. “Timeout của `get` hủy luôn task.”** Không. Caller phải quyết định có gọi `cancel` và cách xử lý task vẫn chạy.

**5. “Bắt mọi `Exception` rồi tiếp tục là chống lỗi.”** Có thể nuốt `InterruptedException`, khiến shutdown treo; catch phải có chính sách retry/exit rõ ràng.

**6. “`shutdownNow()` giết hết thread.”** Nó chỉ nỗ lực interrupt. Nếu task bỏ qua interrupt, không có bảo đảm dừng ngay; cần deadline/resource contract.

**7. “Metrics đã có counter completed là đủ.”** Counter không thấy task đang xếp hàng, timeout, rejected hoặc bị hủy trước khi chạy. Cần quan sát các giai đoạn vòng đời.

**8. “Một thread dump có nhiều `WAITING` là deadlock.”** Thread pool nhàn rỗi có thể chờ queue hoàn toàn bình thường. Deadlock cần phân tích lock ownership/vòng chờ và các mẫu liên tiếp.

**9. “Queue size bằng không tức không overload.”** `SynchronousQueue` không lưu phần tử, nhưng pool vẫn có thể bão hòa và reject nhiều task. Theo dõi thêm active, completion, rejection và caller latency.

**10. “`ThreadMXBean` thấy mọi thread ở mọi JDK.”** Java 21 không giám sát virtual threads qua API chuẩn này; kiểm tra bản JVM và công cụ chẩn đoán hiện có.

## 10. Mini review cuối bài

Hãy tự trả lời trước khi coi tính năng concurrency sẵn sàng:

1. Nếu hai worker cùng thay đổi đối tượng, **cơ chế nào bảo vệ invariant** và bằng chứng happens-before nằm ở đâu?
2. Nếu request timeout nhưng task vẫn đang làm I/O, **ai yêu cầu hủy**, task biết bằng cách nào và khi nào resource được giải phóng?
3. Nếu `Future.isCancelled()` đã `true`, có đủ dữ kiện kết luận `finally` đã chạy chưa?
4. Nếu pool có 8 worker đang bận và 500 task đang chờ, **số nào** dùng để nói về queue length, số nào là active work và lúc nào reject?
5. Nếu hôm nay p99 latency tăng mà throughput giảm, cần **metrics và dump nào** để biết nguyên nhân là queue wait, contention, GC hay downstream?
6. Nếu dùng virtual threads trên JDK 21, tại sao `ThreadMXBean.getThreadCount()` không phải tổng số thread của ứng dụng?
7. Nếu reviewer chỉ có một test ngủ 100 ms rồi assert kết quả, làm sao đổi thành test có đồng bộ điều kiện và timeout rõ?

Một thiết kế đáng tin phải trả lời được cả ba nhóm: **an toàn trạng thái**, **kết thúc tác vụ có kiểm soát** và **bằng chứng quan sát được khi sai**.

## 11. Tài liệu Java chính thức

- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html)
- [ExecutorService — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Future — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [ThreadPoolExecutor — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [CountDownLatch — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [ThreadMXBean — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [jcmd — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
