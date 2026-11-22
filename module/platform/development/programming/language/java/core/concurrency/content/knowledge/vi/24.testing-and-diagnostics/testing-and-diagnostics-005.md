# Kiểm thử shutdown khi task đang chờ hoặc đang chạy trong Java concurrency

## 1. Mục tiêu và tình huống cần chứng minh

Khi một ứng dụng Java sử dụng `ExecutorService`, thao tác dừng executor có thể xảy ra đúng lúc một task **đang chạy**, **đang chờ tài nguyên** hoặc **đã xếp hàng nhưng chưa bắt đầu**. Một test chỉ gọi `shutdown()` rồi kiểm tra `isShutdown()` không chứng minh được các task được xử lý đúng.

Bài này tập trung vào **kiểm thử hành vi shutdown của Java SE concurrency**, không dựa vào vòng đời của framework. Sau bài học, bạn sẽ biết cách:

1. Tạo trạng thái “một task đang chạy và một task nằm trong hàng đợi” một cách xác định.
2. Phân biệt shutdown có trật tự (`shutdown()`) và yêu cầu dừng gấp (`shutdownNow()`).
3. Kiểm tra task đã được nhận có hoàn tất hay bị hủy/ngắt, task mới có bị từ chối, và executor có thật sự kết thúc.
4. Viết test không phụ thuộc may rủi của `Thread.sleep()`, có timeout và luôn giải phóng thread sau test.

**Thuật ngữ cần phân biệt:** “task đang chờ” có thể là (a) task **chưa được chạy**, nằm trong work queue, hoặc (b) task **đã chạy nhưng đang block**, chẳng hạn tại `CountDownLatch.await()`, `BlockingQueue.take()` hay một lời gọi I/O. Hai trường hợp cho kết quả khác nhau khi `shutdownNow()` được gọi; test cần chỉ rõ trạng thái nào đang kiểm chứng.

## 2. Hợp đồng vòng đời của `ExecutorService`

| Lệnh / trạng thái | Ý nghĩa cần kiểm thử |
|---|---|
| `shutdown()` | Ngừng nhận task mới. Task đã nhận trước đó, bao gồm task đang chạy và đang xếp hàng, được phép tiếp tục đến khi hoàn tất. Lệnh **không đợi** mọi task kết thúc. |
| `shutdownNow()` | Cố gắng ngừng task đang chạy (thường bằng `Thread.interrupt()`), dừng xử lý task đang chờ và trả về danh sách `Runnable` chưa bắt đầu thực thi. Đây là **best effort**. |
| `isShutdown()` | Cho biết executor đã được yêu cầu shutdown; **không đồng nghĩa** mọi worker đã dừng. |
| `isTerminated()` | `true` khi toàn bộ task đã kết thúc **sau** khi executor được shutdown. |
| `awaitTermination(timeout, unit)` | Chờ tối đa khoảng thời gian cho phép: trả `true` nếu executor đã kết thúc, `false` nếu hết hạn; có thể ném `InterruptedException`. |
| `submit(...)` sau shutdown | Thông thường bị từ chối với `RejectedExecutionException`; chính sách `RejectedExecutionHandler` của implementation có thể ảnh hưởng cách báo từ chối. |

Lưu ý quan trọng:

- `shutdown()` **không chủ động interrupt** các task đang chạy. Nó cũng không tự động cancel mọi `Future` đã được nộp.
- `shutdownNow()` là **yêu cầu cố gắng dừng**. Một task không phản hồi interrupt có thể tiếp tục chạy, khiến `awaitTermination` hết hạn. Danh sách trả về chỉ đại diện các task **chưa bắt đầu**, không phải các task đã dừng thành công.
- `Future.cancel(true)` nhằm hủy **một** task và có thể gửi interrupt tới worker đang chạy task đó; `shutdownNow()` là thao tác ở cấp **executor**. Chúng không đồng nghĩa.
- `ExecutorService` trong Java 17 phải được đóng rõ ràng bằng `shutdown`/`shutdownNow`; không viết `try-with-resources` cho một biến kiểu `ExecutorService` với mục tiêu chạy trên JDK 17.
- `isTerminated() == false` ngay sau `shutdown()` thường là điều bình thường. Chỉ kết luận shutdown đã hoàn tất sau khi có bằng chứng trạng thái và tín hiệu hoàn thành tương ứng.

## 3. Thiết kế test trước khi viết code

Dùng **`Executors.newSingleThreadExecutor()`** để dễ kiểm soát: chỉ một worker. Cho task A báo tín hiệu “đã bắt đầu”, rồi chờ ở một `CountDownLatch` chưa mở. Khi task A còn giữ worker, task B được `submit` chắc chắn chưa thể bắt đầu.

```text
Executor (1 worker)
          |
          +--> Task A: bắt đầu -> CountDownLatch.await() -> đang block
          |
          +--> Work queue: [ Task B ] -> chưa chạy

Test thread:
  1. Nộp A; đợi A thông báo đã bắt đầu.
  2. Nộp B khi A vẫn bị chặn.
  3. Gọi shutdown() HOẶC shutdownNow().
  4. Kiểm tra trạng thái, thứ tự xử lý và cleanup.
```

`CountDownLatch` là **điểm đồng bộ xác định**, tránh viết “sleep 100 ms và hy vọng task A đã vào đúng chỗ”. Dù vậy, tất cả lệnh chờ trong test đều nên có timeout để lỗi đồng bộ làm test **thất bại hữu hạn**, không làm cả test suite treo.

Bảng mong đợi:

| Trạng thái tại thời điểm shutdown | Với `shutdown()` | Với `shutdownNow()` |
|---|---|---|
| A đã chạy, đang block tại `await()` | A tiếp tục chờ; sau khi latch mở, A có thể hoàn tất bình thường. | Executor cố gắng interrupt A; nếu A đang chờ interruptible, `await()` ném `InterruptedException`. |
| B nằm trong queue, chưa chạy | B vẫn được thực hiện sau A nếu A hoàn tất. | B thường xuất hiện trong danh sách các task chưa bắt đầu do `shutdownNow()` trả về; B không được chạy bởi executor nữa. |
| Task C được nộp **sau** shutdown | Không được chấp nhận theo chính sách từ chối thông thường. | Không được chấp nhận theo chính sách từ chối thông thường. |
| `awaitTermination` khi A còn chờ | Trả `false` khi hết timeout. | Có thể trả `false` nếu A chưa phản hồi interrupt hoặc chưa kết thúc; trả `true` khi tất cả worker đã dừng. |

Mọi assertion phải dựa trên sự kiện quan sát được: `Future.get(timeout)`, giá trị cờ, latch, số task chưa chạy, `isShutdown()`, `isTerminated()` và kết quả `awaitTermination`.

## 4. Chương trình test đầy đủ, chạy trực tiếp bằng Java 17

Ví dụ dưới đây có **hai test độc lập** trong cùng một lớp Java:

- `testGracefulShutdown()`: A đang block và B đang chờ; `shutdown()` vẫn cho cả A và B hoàn tất, nhưng từ chối task mới.
- `testImmediateShutdown()`: A đang block ở thao tác có thể bị interrupt và B đang chờ; `shutdownNow()` yêu cầu ngắt A, thu hồi task B chưa bắt đầu, rồi test tự hủy `Future` của B để người chờ `Future.get()` không phải đợi vô hạn.

Tệp **`ShutdownLifecycleTest.java`**:

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownLifecycleTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void testGracefulShutdown() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> active = executor.submit(() -> {
                started.countDown();
                release.await(); // Task A đang chạy nhưng chờ latch
                return "ACTIVE_DONE";
            });

            check(started.await(2, TimeUnit.SECONDS),
                    "A did not start");

            // Một worker đang bận với A: B chỉ nằm trong queue.
            Future<String> queued = executor.submit(
                    () -> "QUEUED_DONE");

            executor.shutdown();
            check(executor.isShutdown(), "Not shutdown");
            check(!executor.isTerminated(),
                    "Terminated while A is blocked");

            // Task A chưa được release: executor chưa thể kết thúc.
            check(!executor.awaitTermination(100, TimeUnit.MILLISECONDS),
                    "Unexpected termination");

            boolean rejected = false;
            try {
                executor.submit(() -> "NEW_TASK");
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            check(rejected, "Submission was not rejected");

            // Cho A hoàn tất, sau đó worker tiếp tục xử lý B.
            release.countDown();
            check("ACTIVE_DONE".equals(
                    active.get(2, TimeUnit.SECONDS)),
                    "A did not finish");
            check("QUEUED_DONE".equals(
                    queued.get(2, TimeUnit.SECONDS)),
                    "B did not finish");

            check(executor.awaitTermination(2, TimeUnit.SECONDS),
                    "Executor did not terminate");
            check(executor.isTerminated(),
                    "isTerminated() is false");
            System.out.println("graceful: PASS");
        } finally {
            release.countDown(); // Không để A mắc kẹt nếu assertion lỗi.
            executor.shutdownNow();
            executor.awaitTermination(2, TimeUnit.SECONDS);
        }
    }

    private static void testImmediateShutdown() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean queuedRan = new AtomicBoolean(false);

        try {
            Future<String> active = executor.submit(() -> {
                started.countDown();
                try {
                    release.await(); // Có thể bị interrupt.
                    return "RELEASED";
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return "INTERRUPTED";
                }
            });

            check(started.await(2, TimeUnit.SECONDS),
                    "A did not start");

            Future<?> queued = executor.submit(
                    () -> queuedRan.set(true));

            // Với một worker vẫn giữ A, B chưa thể bắt đầu.
            List<Runnable> neverStarted = executor.shutdownNow();

            check(executor.isShutdown(), "Not shutdown");
            check(neverStarted.size() == 1,
                    "Expected exactly one queued task");

            // Các task được submit thường được bao bởi FutureTask.
            // shutdownNow() trả task chưa chạy nhưng không bắt buộc
            // đánh dấu Future của chúng là cancelled.
            for (Runnable task : neverStarted) {
                if (task instanceof Future<?> future) {
                    future.cancel(false);
                }
            }

            check("INTERRUPTED".equals(
                    active.get(2, TimeUnit.SECONDS)),
                    "A did not react to interrupt");
            check(queued.isCancelled(), "B future not cancelled");
            check(!queuedRan.get(), "B unexpectedly ran");

            check(executor.awaitTermination(2, TimeUnit.SECONDS),
                    "Executor did not terminate");
            check(executor.isTerminated(),
                    "isTerminated() is false");
            System.out.println("immediate: PASS");
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(2, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        testGracefulShutdown();
        testImmediateShutdown();
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac ShutdownLifecycleTest.java
java ShutdownLifecycleTest
```

Stdout kỳ vọng khi hai test đều thành công:

```text
graceful: PASS
immediate: PASS
```

Nếu assertion thất bại, chương trình ném `AssertionError`; nếu một mốc đồng bộ/hoàn tất không đến trong thời gian cho phép, test thất bại qua `check(...)` hoặc `Future.get(timeout)` với `TimeoutException`. Các giá trị 2 giây/100 ms là **giới hạn dành cho môi trường test**, không phải bảo đảm về tốc độ của JVM; khi chạy trên CI rất tải, có thể cần điều chỉnh timeout tổng thể nhưng không thay chúng bằng `sleep` đoán trạng thái.

### Vì sao đây là test có tính xác định?

1. `started.await(...)` xác nhận A đã vào thân task trước khi nộp B.
2. Worker chỉ có một, còn A không thể thoát khỏi `release.await()` trừ khi được release hoặc bị interrupt. B vì thế không có cơ hội bắt đầu trước lệnh shutdown.
3. Với shutdown có trật tự, test chủ động giữ A chưa hoàn tất để kiểm tra `awaitTermination(...)` trả `false`; rồi giải phóng A và chờ cả hai `Future` trả kết quả.
4. Với shutdown gấp, test kiểm tra **phản hồi interrupt của A** và **B chưa chạy**, thay vì giả định `shutdownNow()` phải giết mọi thread ngay lập tức.
5. `finally` luôn mở latch và yêu cầu dừng executor, giảm nguy cơ test thất bại để lại non-daemon worker sống mãi.

Ví dụ sử dụng executor một thread có hàng đợi mặc định không giới hạn vì mục tiêu là **kiểm thử shutdown**, không đo throughput hay thiết kế pool production. Nếu thay bằng `ThreadPoolExecutor` có `RejectedExecutionHandler` tùy biến, kết quả submit bị từ chối có thể được biểu diễn khác; test phải khớp chính sách thực của executor.

## 5. Phân tích từng assertion: không nhầm trạng thái yêu cầu với trạng thái hoàn tất

### `isShutdown()` chỉ chứng minh đã có yêu cầu dừng

Ngay khi `shutdown()` trả về, `isShutdown()` là `true`, nhưng A vẫn block và B còn chờ. Điều cần kiểm chứng bổ sung là B thật sự chạy sau A và cuối cùng `isTerminated()` là `true`.

Một test như sau là **thiếu**:

```java
executor.shutdown();
assert executor.isShutdown();
```

Đây chỉ là mảnh minh họa, không phải chương trình đầy đủ. Ngay cả khi bật Java assertions bằng `-ea`, nó không chứng minh cleanup hay task completion; muốn kiểm tra lifecycle cần `Future.get(timeout)` hoặc `awaitTermination(...)`.

### `shutdownNow()` và `Future` của task chưa chạy

Trong ví dụ dùng `submit`, executor có thể lưu các `FutureTask` trong hàng đợi. `shutdownNow()` trả danh sách các `Runnable` **chưa bắt đầu**, nhưng không đồng nghĩa tất cả `Future` tương ứng đã chuyển sang `isCancelled() == true`. Nếu bên ngoài vẫn giữ `Future`, hãy xác định chính sách đối với task bị rút khỏi queue: hủy các `Future` chưa chạy, đánh dấu trạng thái thất bại ở hệ thống nghiệp vụ, hoặc chuyển giao cho nơi thực thi khác (nếu thiết kế cho phép). Ví dụ trên chủ động `cancel(false)` để trạng thái `queued` hữu hạn.

**Không được lấy `neverStarted.size()` để khẳng định đã ngắt thành công bao nhiêu task đang chạy.** Nó chỉ đếm task chưa bắt đầu tại thời điểm lấy khỏi queue. Task A phản hồi interrupt được kiểm riêng qua kết quả `active.get(...)`.

### `InterruptedException` là tín hiệu hợp tác

Java interrupt **không ép buộc** thread chấm dứt. Với các thao tác chờ có thể interrupt như `CountDownLatch.await()`, thread đang chờ sẽ nhận `InterruptedException`. Với vòng lặp tính CPU, code thường cần tự kiểm tra trạng thái interrupt:

```java
// Mảnh minh họa nằm bên trong một task, không phải lớp đầy đủ.
while (!Thread.currentThread().isInterrupted()) {
    processOneUnit();
}
// Ra khỏi vòng lặp và dọn tài nguyên.
```

Nếu task bắt `InterruptedException` rồi lờ đi, tiếp tục chờ vô hạn, `shutdownNow()` có thể không làm executor kết thúc được. Khi muốn propagating interrupt mà phương thức không khai báo `throws InterruptedException`, thường gọi `Thread.currentThread().interrupt()` rồi thoát có kiểm soát. Không biến `Thread.stop()` thành giải pháp shutdown: phương thức này đã bị loại bỏ khỏi thực hành an toàn vì có thể phá hủy bất biến của đối tượng.

## 6. Kiểm thử khi task đang chờ khóa, I/O hoặc kết quả task khác

`CountDownLatch` là công cụ đồng bộ test lý tưởng, nhưng task production có thể chờ trên nhiều primitive khác nhau:

| Task đang chờ ở đâu? | Phản ứng có thể có với interrupt | Cách kiểm thử |
|---|---|---|
| `CountDownLatch.await()`, `Thread.sleep()`, `BlockingQueue.take()` | Ném `InterruptedException` khi bị interrupt (theo hợp đồng API). | Dùng latch đảm bảo đã vào nhánh chờ; assert task ghi nhận interrupt và kết thúc. |
| `ReentrantLock.lockInterruptibly()` | Có thể bị interrupt trong lúc chờ lock. | Giữ lock ở test thread, cho worker báo đã sẵn sàng rồi chờ lock; interrupt và assert đường thoát. |
| `synchronized` đang đợi monitor | `Thread.interrupt()` không khiến việc đợi vào monitor tự ném `InterruptedException`. | Test phải **thả monitor** để worker có thể tiếp tục; không giả định shutdownNow kết thúc được ngay. |
| Tính toán CPU trong vòng lặp dài | Không tự động ném exception do interrupt. | Cho task kiểm tra `isInterrupted()` hoặc cơ chế hủy được thiết kế rõ. |
| I/O blocking | Phản ứng phụ thuộc loại API, channel và cơ chế I/O đang dùng. | Thiết kế tài nguyên có timeout/close thích hợp; test dựa trên API cụ thể, không giả định mọi I/O đều được interrupt như latch. |
| `Future.get()` | Có thể ném `InterruptedException` nếu thread gọi đang chờ bị interrupt. | Tránh dependency cycle giữa các task; cần timeout hoặc cơ chế đồng bộ rõ. |

**Test khác nhau cho từng primitive.** Ví dụ `Lock.lockInterruptibly()` và `synchronized` không thể bị coi như nhau, dù cả hai có thể biểu hiện là thread đang ở trạng thái chờ.

### Trường hợp task phớt lờ interrupt

Nếu muốn kiểm chứng rằng shutdown có timeout khi task không hợp tác, có thể tạo task thử nghiệm chỉ kết thúc khi latch được mở, đồng thời **ghi nhận nhưng bỏ qua interrupt**. Test cần:

1. Đảm bảo task thực sự đã bắt đầu trước khi shutdown.
2. Gọi `shutdownNow()` và chứng minh `awaitTermination(shortTimeout)` trả `false`.
3. **Bắt buộc mở latch trong `finally`** để task thoát, rồi `awaitTermination` lần nữa.

Đây là loại negative test phải có cleanup rõ ràng: nếu thiếu tín hiệu giải phóng cuối cùng, một thread không daemon có thể giữ JVM chạy mãi sau khi test đã báo lỗi.

## 7. Kiểm thử race condition và trạng thái biên

Test shutdown thường không chỉ chạy một happy path. Những tình huống sau rất đáng kiểm tra riêng trong một suite đầy đủ:

### 7.1. Nộp task cạnh thời điểm shutdown

Khi một thread gọi `submit` đồng thời với thread khác gọi `shutdown`, không thể chỉ dựa vào hai lệnh “gần nhau” để khẳng định một task chắc chắn được nhận hoặc bị từ chối. Test nên phối hợp bằng barrier/latch để xác định rõ hai lịch xảy ra:

- **Nộp xong trước shutdown:** task được nhận và `shutdown()` không tự bỏ task đó.
- **Shutdown hoàn tất trước khi submit:** task mới bị từ chối theo chính sách executor thông thường.
- **Race thật sự:** kết quả chấp nhận hoặc từ chối có thể tùy thứ tự thực thi; assert **các bất biến hợp lệ** (không chạy hai lần, không mất kết quả đã được nhận, không chạy task mới sau khi shutdown đã có hiệu lực) thay vì ép một lịch ngẫu nhiên.

### 7.2. Gọi shutdown nhiều lần

`shutdown()` và `shutdownNow()` được thiết kế cho vòng đời chấm dứt executor, nên test có thể gọi lặp để xác nhận không có task mới được chấp nhận và không phát sinh tác vụ ngoài ý muốn. Gọi `shutdown()` sau `shutdownNow()` không “mở lại” executor. Không có API restart một `ExecutorService` đã shutdown.

### 7.3. Task ném exception

Một task được `submit` có thể kết thúc bằng exception. `Future.get()` khi đó ném `ExecutionException` bao bọc lỗi. Điều này không đồng nghĩa executor chưa thể terminate; test nên tách bạch **task thất bại** và **executor đã shutdown hoàn toàn**. Không chỉ assert `isTerminated()` rồi bỏ qua kết quả `Future`.

### 7.4. Hủy bằng `Future.cancel(true)`

Với một task đang block ở điểm có thể interrupt, `cancel(true)` có thể khiến `Future.isCancelled()` thành `true` và `Future.get()` ném `CancellationException`. Tuy nhiên, trạng thái canceled của `Future` **không phải bằng chứng worker đã lập tức dừng** nếu code task không hợp tác. Muốn chứng minh cleanup phải kiểm tra tín hiệu từ task và thời điểm executor terminate.

### 7.5. Task kẹt vì deadlock

Nếu A đang giữ lock và chờ kết quả B, còn B cần chính lock A giữ, shutdown không tháo deadlock. Một executor một worker cũng dễ tự khóa nếu task A chờ `Future` của task B được nộp vào cùng pool. Trước khi đổ lỗi cho shutdown, kiểm tra dependency cycle, stack trace và thread dump. Test có timeout giúp phát hiện biểu hiện kẹt; nó không tự xác định nguyên nhân.

## 8. Thực hành tổ chức test trong dự án Java

Một test tốt nên tách **arrange → act → assert → cleanup**:

```text
Arrange
    tạo executor cô lập cho từng test
    tạo latch báo task đã bắt đầu
    giữ task A ở một điểm chờ xác định
    nộp task B và xác lập B chưa bắt đầu

Act
    gọi shutdown() hoặc shutdownNow()

Assert
    xác nhận isShutdown()
    kiểm tra kết quả Future, task bị từ chối,
    interrupt/cancel/queue behavior
    xác nhận awaitTermination(...) và isTerminated()

Cleanup (finally)
    mở mọi latch còn khóa
    yêu cầu shutdownNow() nếu cần
    awaitTermination(timeout) và báo lỗi cleanup nếu không dừng
```

Khi chuyển sang JUnit, có thể tách hai phương thức trên thành các test method độc lập, dùng assertion của JUnit và fixture cleanup ở `@AfterEach`. Chương trình đầy đủ ở mục 4 **không phụ thuộc JUnit hay thư viện bên ngoài**, nên có thể chạy ngay bằng JDK 17.

### Kiểm tra timeout một cách có trách nhiệm

- **Timeout ngắn để quan sát**: ví dụ `awaitTermination(100, MILLISECONDS)` khi biết A chắc chắn đang chờ latch chưa mở.
- **Timeout đủ rộng để chờ sự kiện hợp lệ**: ví dụ `Future.get(2, SECONDS)`, `started.await(2, SECONDS)`. Con số cụ thể phụ thuộc môi trường và tải máy.
- **Không dùng delay để tạo thứ tự**: `Thread.sleep(100)` không bảo đảm B đã vào queue hay A đã đến đoạn chờ.
- **Không làm test phụ thuộc vào thứ tự hai task không có quan hệ đồng bộ**: thứ tự có thể thay đổi với nhiều worker.
- **Không bỏ qua `InterruptedException` ở test thread**: nếu test thread bị interrupt trong lúc chờ, cần xử lý như một test failure hoặc truyền tiếp exception; trong logic cleanup phức tạp có thể cần khôi phục interrupt flag theo chính sách của framework.

Một nguyên tắc đặc biệt quan trọng là phân biệt **timeout của test** với **timeout của hệ thống production**. Test được thiết kế để kết thúc hữu hạn và dễ phát hiện lỗi; production cần deadline và chiến lược graceful shutdown phù hợp mức độ an toàn dữ liệu.

## 9. Quy trình shutdown thực tế và điều cần xác minh

Một mẫu thường gặp khi đóng executor trong chương trình Java:

```java
// Mảnh minh họa trong phương thức có khai báo throws InterruptedException.
executor.shutdown();
if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
    executor.shutdownNow();
    if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
        System.err.println("Executor still running");
    }
}
```

Đoạn này **không phải lớp Java chạy độc lập**. Nó thể hiện trình tự: ngừng nhận việc mới → đợi việc đã nhận → yêu cầu ngắt nếu quá deadline → đợi thêm và báo nếu vẫn chưa kết thúc. `shutdownNow()` không thay thế cơ chế quản lý timeout/hủy của từng công việc, và cách xử lý task còn tồn đọng phải theo yêu cầu dữ liệu của ứng dụng.

Trong code có chính sách phục hồi khi test thread bị interrupt, thường cần:

```java
// Mảnh minh họa với executor đã được khai báo.
try {
    executor.shutdown();
    if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Việc khôi phục interrupt flag thông báo cho lớp gọi rằng thread hiện tại đã nhận yêu cầu interrupt. Không bắt `InterruptedException` rồi tiếp tục như chưa có chuyện gì xảy ra.

Ở production, nếu có task đang ghi dữ liệu, đang giữ giao dịch hoặc có nguồn I/O, cần xác định **công việc nào được phép hủy**, **công việc nào phải hoàn tất**, cách đóng tài nguyên và cách xử lý request đang chờ. Các chính sách đó độc lập với việc chỉ gọi đúng hai method shutdown.

## 10. Những lỗi test dễ đánh lừa

| Cách test sai | Vì sao sai | Thay bằng |
|---|---|---|
| Gọi `shutdown()`; assert `isShutdown()`; coi như xong. | Executor có thể còn A đang chạy và B đang chờ. | Chờ `Future` và `awaitTermination`, kiểm tra task trước/sau shutdown. |
| Dùng `Thread.sleep(50)` để “đảm bảo A bắt đầu”. | Phụ thuộc scheduler, máy CI và timing. | `CountDownLatch` báo chính xác mốc đã bắt đầu. |
| Dùng pool 4 thread nhưng chỉ nộp A, B rồi bảo B đang queued. | B có thể chạy trên worker thứ hai. | Pool 1 worker hoặc bảo đảm mọi worker đều bận trước khi nộp B. |
| Khẳng định `shutdownNow()` đã dừng mọi task. | Interrupt chỉ là yêu cầu; task có thể không hợp tác. | Xác nhận hành vi task, kết quả `Future`, deadline và `isTerminated()`. |
| Gọi `Future.get()` không timeout trong test. | Một lỗi deadlock khiến test suite kẹt vô hạn. | Dùng `get(timeout, unit)` và cleanup ở `finally`. |
| Không hủy `Future` bị rút khỏi queue sau `shutdownNow()`. | Người giữ `Future` có thể chờ mãi một task không còn được chạy. | Xác định và hủy/hoàn trả trạng thái của task chưa bắt đầu. |
| Quên release latch khi assertion thất bại. | Thread không daemon có thể sống vô hạn. | Release ở `finally`, yêu cầu shutdown và kiểm tra termination. |
| Chỉ kiểm tra task B không in log. | Không in log chưa chứng minh task không chạy. | Dùng `AtomicBoolean`, `Future` và danh sách neverStarted; tạo quan hệ đồng bộ. |
| Dùng kết quả của test đo hiệu năng để kết luận shutdown đúng. | Benchmark không chứng minh thứ tự và lifecycle. | Test lifecycle có assertion cụ thể; benchmark là bài toán khác. |

## 11. Bài tập áp dụng

**Bài 1 — graceful shutdown:** Nếu task A giữ worker tại `CountDownLatch.await()`, task B đã submit, và gọi `shutdown()`, điều gì xảy ra với task B? **Đáp án:** B vẫn nằm trong hàng chờ hợp lệ. Khi A được giải phóng và hoàn tất, worker có thể thực hiện B; sau tất cả task được nhận đã hoàn tất, executor mới terminate.

**Bài 2 — immediate shutdown:** Nếu A bị block ở `BlockingQueue.take()` và có code bắt `InterruptedException` rồi thoát, `shutdownNow()` có bảo đảm executor terminate *ngay tại thời điểm method trả về* không? **Không.** Nó yêu cầu ngắt nhưng worker vẫn cần thời gian phản hồi và cleanup. Cần kiểm tra `awaitTermination`.

**Bài 3 — queued Future:** Một task do `submit()` tạo ra vẫn nằm trong queue lúc `shutdownNow()` rút ra. Tại sao `Future.get()` có thể tiếp tục đợi? Vì việc rút task khỏi queue **không tự động bảo đảm** `Future` đã hoàn thành/cancel. Nếu chính code quản lý lifecycle, hãy chủ động xử lý `Future` chưa chạy.

**Bài 4 — robustness:** Nếu thay `newSingleThreadExecutor()` bằng `newFixedThreadPool(3)`, cần làm gì để chắc chắn B ở queue khi shutdown? **Đáp án:** giữ đủ 3 worker bận trên các latch trước khi nộp B, hoặc sử dụng một executor tùy chỉnh cho phép kiểm chứng trạng thái hàng đợi. Không dựa vào `sleep`.

**Bài 5 — phản hồi interrupt:** Vì sao test không nên kỳ vọng `shutdownNow()` giết một task đang chờ `synchronized` monitor ngay? Vì việc chờ vào intrinsic monitor **không interruptible theo cách `CountDownLatch.await()` hay `lockInterruptibly()` hoạt động**. Muốn kết thúc task, cần làm rõ cơ chế giải phóng tài nguyên và điều kiện thoát.

## 12. Checklist khi review test shutdown

- Test tạo được trạng thái **đang chạy**, **đang block** và **đang queued** mà không dựa vào lịch chạy ngẫu nhiên.
- Assertions phân biệt `shutdown()` với `shutdownNow()`, cả hành vi task **đã nhận** và task **nộp mới**.
- Có bằng chứng về interrupt hoặc cancellation, thay vì chỉ xem `isShutdown()`.
- Tất cả thao tác chờ có timeout, và `finally` đảm bảo mở tín hiệu chờ, dọn executor.
- `Future` của task không được chạy sau `shutdownNow()` có chính sách rõ ràng.
- Test độc lập, không chia sẻ executor mutable giữa các test, không để lại thread.
- Test chạy trên JDK mà dự án hỗ trợ, ví dụ Java 17+, với đầu ra và điều kiện thất bại có thể quan sát.

**Kết luận:** Shutdown test đúng phải kiểm chứng *vòng đời thực* của task trước và sau khi đóng executor: task đã được nhận có được hoàn tất, task đang chờ có phản hồi interrupt đúng, task chưa bắt đầu có bị giữ lại, task mới có bị từ chối và pool có thật sự terminate không. `CountDownLatch`, `Future.get(timeout)`, `awaitTermination` và cleanup trong `finally` giúp biến những race khó đoán thành test kiểm soát được.

### Tham khảo Java SE 17

- [`ExecutorService`: shutdown, shutdownNow, awaitTermination](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [`ThreadPoolExecutor`: quản lý task và trạng thái worker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [`CountDownLatch`: đồng bộ hóa thời điểm bắt đầu/giải phóng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [`Future`: chờ, cancel, trạng thái kết quả](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [`Thread.interrupt()` và interrupted status](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
