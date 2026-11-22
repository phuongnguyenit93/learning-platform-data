# Test timeout, interruption và cancellation trong Java Concurrency

## 1. Mục tiêu và ranh giới bài học

Một chương trình có thể chờ kết quả quá lâu, bị yêu cầu hủy, hoặc nhận tín hiệu ngắt từ một thread khác. Các tình huống này **khác nhau về ý nghĩa và hợp đồng API**, dù cùng biểu hiện rằng người gọi không nhận được kết quả như mong đợi.

Sau bài này, bạn có thể:

- Phân biệt **timeout** (hết thời gian chờ), **interruption** (tín hiệu ngắt thread), **cancellation** (yêu cầu hủy task) với thành công và thất bại của task.
- Viết test Java kiểm soát được thứ tự sự kiện bằng `CountDownLatch`, không phụ thuộc `Thread.sleep` để đoán scheduler.
- Test được `Future.get(timeout)`, `Future.cancel(false/true)`, `Thread.interrupt()` và `CompletableFuture.cancel(true)`.
- Xác minh riêng **trạng thái Future** và **việc worker thực sự kết thúc**, kể cả cleanup sau khi test thất bại.
- Thiết kế deadline, xử lý đúng `InterruptedException`, kiểm tra executor termination và hạn chế test flaky.

Phạm vi là **Java chuẩn (Java 17+)**, không bàn cơ chế chạy task và transaction đặc thù của Spring.

## 2. Timeout, interruption và cancellation khác nhau thế nào?

**Timeout**: bên chờ đã tiêu hết ngân sách thời gian mà chưa có kết quả. Ví dụ `future.get(100, TimeUnit.MILLISECONDS)` ném `TimeoutException` khi chưa hoàn thành. Điều này **chỉ kết thúc lần chờ**, không tự dừng computation.

**Interruption**: `Thread.interrupt()` gửi tín hiệu cho một thread. Tín hiệu được thể hiện bằng cờ interrupt hoặc bằng `InterruptedException` từ các lời gọi chờ có hỗ trợ interrupt. Đây là giao thức **hợp tác**: thread phải dừng/cleanup hoặc truyền tín hiệu theo policy của nó. Không có bảo đảm mọi mã CPU/I/O lập tức thoát.

**Cancellation**: yêu cầu ngừng một công việc hoặc đánh dấu kết quả là không cần nữa. Một `Future` có thể chuyển sang trạng thái cancelled trước khi worker giải phóng tài nguyên; `cancel(true)` cố interrupt worker, còn `cancel(false)` không yêu cầu interrupt.

| API | Hành vi có thể quan sát | Có dừng công việc đang chạy? |
|---|---|---|
| `Future.get(timeout, unit)` | Ném `TimeoutException` nếu hết thời gian chờ | Không |
| `CountDownLatch.await(timeout, unit)` | Trả `false` nếu chưa nhận đủ tín hiệu; cũng có thể ném `InterruptedException` | Không |
| `Thread.join(timeoutMillis)` | Trả về sau khi thread kết thúc hoặc hết hạn; cần kiểm tra `isAlive()` | Không |
| `Thread.interrupt()` | Đặt cờ ngắt, một số thao tác blocking ném `InterruptedException` | Best effort, phụ thuộc task |
| `Future.cancel(false)` | Có thể đánh dấu Future cancelled | Không interrupt worker |
| `Future.cancel(true)` | Có thể đánh dấu cancelled và cố interrupt worker | Best effort, phụ thuộc task |
| `CompletableFuture.cancel(true)` | Hoàn tất future với cancellation | `mayInterruptIfRunning` không interrupt computation |
| `CompletableFuture.orTimeout(...)` | Complete exceptionally với `TimeoutException` khi hết hạn | Không bảo đảm dừng task nguồn |
| `CompletableFuture.completeOnTimeout(...)` | Complete với kết quả fallback nếu quá hạn | Không bảo đảm dừng task nguồn |
| `ExecutorService.shutdownNow()` | Cố interrupt task đang chạy, trả về task chờ chưa khởi chạy | Không bảo đảm mọi task đã thoát |

Vì thế, mỗi test nên trả lời hai câu riêng: **người gọi nhận outcome gì** và **worker đang ở trạng thái nào**.

`TimeoutException` do một phép chờ có deadline không giống `CancellationException` khi lấy kết quả Future đã hủy. `ExecutionException` từ `Future.get` bọc lỗi của task; `InterruptedException` thông báo thread **đang đợi** nhận interruption.

### Hai cuộc đời của cùng một tác vụ

Giả sử worker chạy lời gọi I/O chậm, còn thread gọi chạy:

```java
try {
    return future.get(200, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    // Caller hết thời gian chờ.
    // Callable có thể vẫn đang chạy trên worker.
    throw ex;
}
```

Đây là đoạn minh họa trong phương thức có `future` phù hợp, kiểu trả về thích hợp và khai báo/handle các checked exception cần thiết; không phải một chương trình độc lập.

Sau khi caller ném `TimeoutException`, worker vẫn có thể hoàn tất một thay đổi bên ngoài. Do đó timeout không đồng nghĩa rollback hay hủy side effect. Nếu cần yêu cầu ngừng, caller phải thiết kế policy `cancel(true)`, resource timeout, hoặc một cơ chế hủy do API nền hỗ trợ.

## 3. Cách viết test concurrency có thể tái hiện

**Không dùng thời gian ngủ để chứng minh thứ tự.** Mã `Thread.sleep(50)` trong test chỉ trì hoãn thread gọi; nó không bảo đảm worker đã bắt đầu, đã lấy lock hay đã tới nhánh cần test. Máy CI, GC và scheduler có thể thay đổi thứ tự.

Dùng các mốc đồng bộ:

1. Worker gọi `started.countDown()` ngay trước đoạn được kiểm tra.
2. Test gọi `started.await(3, SECONDS)` để biết worker đã tới mốc đó; sử dụng thời hạn nhằm bảo vệ test khỏi treo.
3. Worker đợi `release.await()` để không chạy vượt khỏi điểm test muốn quan sát.
4. Test phát tín hiệu cancel/interrupt hoặc cố lấy kết quả với timeout.
5. Worker gọi `finished.countDown()` trong `finally`; test đợi mốc này để xác minh công việc đã rời phần thực thi.
6. Cleanup trong `finally` luôn mở latch và shutdown executor; sau đó kiểm tra executor termination.

`CountDownLatch` là đồng bộ một lần. Nếu cần chạy nhiều vòng với nhiều participant, `CyclicBarrier` hoặc `Phaser` có thể phù hợp hơn. Với test một task, latch thường đủ rõ ràng.

Một test tốt dùng timeout **làm van an toàn**, chứ không assert “phải chạy trong đúng 10 ms”. Khi cần xác minh rằng một phép chờ bị timeout, hãy giữ task tại một latch đang đóng và chờ với timeout đủ rõ. Điều kiện bị khóa là yếu tố tạo ra kết quả, còn timeout ngắn chỉ là hạn chờ của phép quan sát.

## 4. Chương trình test Java 17 chạy được

Ví dụ này gồm năm tình huống dùng đúng Java chuẩn: timeout không hủy task, hủy task trong hàng đợi, hủy task đang chạy với interrupt, interrupt trực tiếp, và cancellation của `CompletableFuture`.

Tạo tệp **`LifecycleTests.java`**:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class LifecycleTests {
    public static void main(String[] args) throws Exception {
        testTimeoutDoesNotCancel();
        testQueuedCancellation();
        testRunningCancellation();
        testDirectInterruption();
        testCompletableFutureCancellation();
        System.out.println("ALL TESTS PASSED");
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void await(CountDownLatch latch, String stage)
            throws InterruptedException {
        check(latch.await(3, TimeUnit.SECONDS), "Wait timed out: " + stage);
    }

    static void stop(ExecutorService executor) throws InterruptedException {
        executor.shutdownNow();
        check(executor.awaitTermination(3, TimeUnit.SECONDS),
                "Executor failed to terminate");
    }

    static void testTimeoutDoesNotCancel() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            Future<String> task = executor.submit(() -> {
                started.countDown();
                release.await();
                return "done";
            });
            await(started, "timeout worker started");

            boolean timeout = false;
            try {
                task.get(100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timeout = true;
            }
            check(timeout, "Expected get timeout");
            check(!task.isDone(), "Timed get must not finish task");

            release.countDown();
            check("done".equals(task.get(3, TimeUnit.SECONDS)),
                    "Worker should complete after release");
            System.out.println("PASS timeout");
        } finally {
            release.countDown();
            stop(executor);
        }
    }

    static void testQueuedCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean secondRan = new AtomicBoolean(false);
        try {
            Future<?> first = executor.submit(() -> {
                firstStarted.countDown();
                release.await();
                return null;
            });
            await(firstStarted, "first task started");

            Future<?> second = executor.submit(() -> {
                secondRan.set(true);
                return null;
            });
            check(second.cancel(false), "Cannot cancel queued task");
            check(second.isCancelled(), "Task not marked cancelled");

            release.countDown();
            first.get(3, TimeUnit.SECONDS);
            try {
                second.get();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException expected) {
                // No result is available from cancelled task.
            }
            check(!secondRan.get(), "Cancelled queued task ran");
            System.out.println("PASS queued cancellation");
        } finally {
            release.countDown();
            stop(executor);
        }
    }

    static void testRunningCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch interrupted = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            Future<?> task = executor.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(TimeUnit.MINUTES.toMillis(10));
                } catch (InterruptedException ex) {
                    interrupted.countDown();
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
            await(started, "running task started");
            check(task.cancel(true), "Cancellation failed");
            check(task.isCancelled(), "Task not marked cancelled");

            // isCancelled() alone does not prove worker has stopped.
            await(interrupted, "worker received interrupt");
            await(finished, "worker finally finished");
            try {
                task.get();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException expected) {
                // Future result has been cancelled.
            }
            System.out.println("PASS running cancellation");
        } finally {
            stop(executor);
        }
    }

    static void testDirectInterruption() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch handled = new CountDownLatch(1);
        AtomicBoolean restored = new AtomicBoolean(false);
        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                Thread.sleep(TimeUnit.MINUTES.toMillis(10));
            } catch (InterruptedException expected) {
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            } finally {
                handled.countDown();
            }
        }, "interrupt-test");
        worker.start();
        try {
            await(started, "thread started");
            worker.interrupt();
            await(handled, "thread handled interrupt");
            worker.join(3_000);
            check(!worker.isAlive(), "Interrupted thread still alive");
            check(restored.get(), "Interrupted flag not restored");
            System.out.println("PASS direct interruption");
        } finally {
            worker.interrupt();
            worker.join(3_000);
        }
    }

    static void testCompletableFutureCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        try {
            CompletableFuture<String> task =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "done";
                        } catch (InterruptedException ex) {
                            interrupted.set(true);
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            finished.countDown();
                        }
                    }, executor);
            await(started, "CompletableFuture worker started");
            check(task.cancel(true), "CompletableFuture cancel failed");
            check(task.isCancelled(), "Future not marked cancelled");
            check(finished.getCount() == 1,
                    "Underlying work unexpectedly finished");

            release.countDown();
            await(finished, "underlying work finished");
            check(!interrupted.get(),
                    "CompletableFuture cancel should not interrupt worker");
            try {
                task.join();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException expected) {
                // Cancellation is visible to future consumers.
            }
            System.out.println("PASS CompletableFuture cancellation");
        } finally {
            release.countDown();
            stop(executor);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LifecycleTests.java
java LifecycleTests
```

Kết quả kỳ vọng:

```text
PASS timeout
PASS queued cancellation
PASS running cancellation
PASS direct interruption
PASS CompletableFuture cancellation
ALL TESTS PASSED
```

### Giải thích từng test

**Timeout:** worker chỉ có thể trả `"done"` sau khi `release` được mở. Khi test gọi `get(100, MILLISECONDS)`, task vẫn bị giữ tại latch; ta xác minh `TimeoutException` và `!isDone()`, rồi mở latch và lấy kết quả thành công. Đây là bằng chứng trực tiếp rằng **timeout của lời gọi chờ không hủy task**.

**Cancel trước khi chạy:** single-thread executor đang chạy blocker; task thứ hai nằm trong queue. `cancel(false)` đánh dấu task chưa chạy là cancelled. Sau khi thả blocker, test xác minh lambda thứ hai không được thực thi. Lưu ý `cancel(false)` trên một task **đang chạy** có thể vẫn thay đổi trạng thái Future tùy implementation nhưng không yêu cầu interrupt worker.

**Cancel task đang chạy:** test chờ `started`, rồi gọi `cancel(true)`. Worker ở `Thread.sleep` có thể nhận `InterruptedException` ngay cả khi interrupt đến trước lúc gọi `sleep`. Ngoài `task.isCancelled()`, test còn đợi `interrupted` và `finished`; điều này xác minh worker đã đi qua code xử lý interrupt và `finally`.

**Interrupt trực tiếp:** `worker.interrupt()` là tín hiệu trên thread, không yêu cầu một Future. Khi `Thread.sleep` ném `InterruptedException`, cờ interrupt bị xóa; worker chủ động đặt lại cờ bằng `Thread.currentThread().interrupt()`. Test ghi nhận điều đó trong `AtomicBoolean` và kiểm tra worker đã kết thúc.

**CompletableFuture:** ở Java 17, `CompletableFuture.cancel(true)` có tham số giống `Future` nhưng tham số `mayInterruptIfRunning` **không được dùng để ngắt computation**. Test giữ work ở `release.await()` trong executor riêng, cancel future, sau đó tự mở latch. Task tiếp tục và kết thúc; kết quả future vẫn là cancelled.

Lưu ý: những chờ có giới hạn 3 giây là *safety timeout*. Nếu máy CI quá tải, test có thể fail do deadline bảo vệ; tăng timeout hợp lý theo môi trường nhưng không thay latch bằng sleep. Bộ test xác minh các interleaving được điều khiển cụ thể, không phải chứng minh thuật toán chính xác trong mọi lịch thực thi.

## 5. Xử lý interruption đúng hợp đồng

### Đọc và khôi phục cờ interrupt

- `thread.isInterrupted()` đọc cờ mà **không xóa**.
- `Thread.interrupted()` (static) đọc **và xóa** cờ interrupt của **thread hiện tại**, dù gọi qua cú pháp đối tượng.
- Khi một số blocking API như `Thread.sleep`, `Object.wait`, `CountDownLatch.await`, `BlockingQueue.take`, `Future.get` ném `InterruptedException`, cờ đã được xóa theo hợp đồng của API.
- Nếu phương thức cho phép `throws InterruptedException`, thường truyền tiếp ngoại lệ. Nếu bắt ở tầng ngoài không thể truyền, thường khôi phục cờ và kết thúc/đi theo nhánh hủy phù hợp; đừng nuốt tín hiệu rồi chạy tiếp như chưa có gì xảy ra.

Ví dụ một callable có điểm kiểm tra interruption (đoạn minh họa cần `import java.util.concurrent.Callable;`):

```java
Callable<Long> work = () -> {
    long processed = 0;
    try {
        while (!Thread.currentThread().isInterrupted()) {
            Thread.sleep(100); // Thay bằng thao tác interruptible thực tế.
            processed++;
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Dừng vòng lặp; xử lý kết quả dở dang theo policy của ứng dụng.
    }
    return processed;
};
```

Đoạn này minh họa giao thức hủy, **không phải** worker nghiệp vụ hoàn chỉnh. Một tác vụ trả kết quả dở dang sau interrupt chỉ đúng khi API chấp nhận partial result; nếu không, nên truyền lỗi hoặc biểu diễn trạng thái canceled rõ ràng.

### Task tính toán CPU-bound

`cancel(true)` không tự sinh `InterruptedException` từ phép tính số học. Task tính toán kéo dài cần kiểm tra cờ định kỳ:

```java
// Đoạn minh họa trong một phương thức throws InterruptedException.
for (long i = 0; i < totalSteps; i++) {
    if (Thread.currentThread().isInterrupted()) {
        throw new InterruptedException("Requested to stop");
    }
    // Tính một bước; totalSteps phải được định nghĩa ở phạm vi ngoài.
}
```

Không nhất thiết kiểm tra trong mọi vòng lặp nếu quá tốn chi phí; nhưng khoảng kiểm tra phải đủ thường xuyên so với mục tiêu cancellation latency. Các API block tùy loại có thể phản hồi interruption khác nhau; kiểm tra tài liệu API/driver đang dùng thay vì mặc định mọi I/O đều interruptible.

Đừng dùng `Thread.stop()` để “hủy cưỡng bức”: API này không an toàn và đã deprecated, có thể phá vỡ invariant của dữ liệu dùng chung.

### Chờ lock có interrupt được hay không?

Khi một thread chờ vào `synchronized` monitor, `interrupt()` không lập tức giúp nó thoát khỏi việc chờ lấy monitor. Với `ReentrantLock.lockInterruptibly()` hoặc `tryLock(timeout, unit)`, thread có thể nhận `InterruptedException` hay timeout khi chờ lock. Cần test đúng primitive mà production thực sự dùng.

## 6. Viết timeout ở nơi có deadline, không chỉ chỗ gọi get

Khi người gọi hết thời gian và task không còn hữu ích, có thể yêu cầu hủy:

```java
// Đoạn minh họa của một phương thức có khai báo checked exceptions phù hợp.
Future<Result> future = executor.submit(() -> doWork());
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true); // Best effort; worker có thể chưa dừng.
    throw timeout;
}
```

`Result`, `executor` và `doWork` chỉ là tên minh họa, không phải chương trình độc lập. Nếu caller bị `InterruptedException`, phải quyết định có yêu cầu hủy task hay không rồi truyền tiếp tín hiệu, thay vì tự động bỏ qua interruption. Với side effect không thể đảo ngược, cần xác định outcome thật của task trước khi retry.

Một **deadline chung** tránh trường hợp request gọi ba bước, mỗi bước lại được cấp toàn bộ 2 giây (khi đó tổng có thể lên đến 6 giây). Dùng đồng hồ đơn điệu để đo elapsed:

```java
// Đoạn minh họa trong phương thức throws TimeoutException.
long startNanos = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(2);

// Sau một bước tốn thời gian:
long remaining = budgetNanos - (System.nanoTime() - startNanos);
if (remaining <= 0) {
    throw new TimeoutException("Overall deadline exceeded");
}
// Cấp remaining cho bước chờ tiếp theo hỗ trợ timeout.
```

`System.nanoTime()` dành cho đo khoảng thời gian, không phải biểu diễn ngày giờ. Phép trừ thích hợp với các khoảng nhỏ hơn giới hạn biểu diễn `long`; cần kiểm soát overflow khi nhận các duration tùy ý.

### Những timeout có semantics riêng

- `Thread.join(millis)` hết hạn thì có thể trả về trong khi thread vẫn sống. Test phải kiểm tra `isAlive()` và có đường cleanup.
- `CountDownLatch.await(timeout, unit)` trả `false` nếu chưa đủ signal; không tự ngắt task phía khác.
- `Lock.tryLock(timeout, unit)` có thể trả `false` do không lấy được lock hoặc ném `InterruptedException`; đây là hai ca khác nhau.
- `CompletableFuture.orTimeout` hoàn tất exceptional future khi hết hạn; `completeOnTimeout` đặt kết quả fallback. Cả hai đều không bảo đảm worker thực tế dừng.
- `ExecutorService.awaitTermination(timeout, unit)` trả `false` khi executor chưa kết thúc; không tự gọi `shutdownNow()` thêm lần nữa.
- Timeout của HTTP, socket, JDBC hoặc filesystem tùy API; một timeout của phép chờ ở Java không tự tạo transaction rollback hay close resource của lời gọi bên dưới.

## 7. Ma trận các tình huống cần kiểm thử

| Tình huống | Cách dựng trạng thái trước trigger | Assertion quan trọng |
|---|---|---|
| Timeout khi chờ result | Worker giữ ở `release.await()` | `TimeoutException`, `!future.isDone()`, vẫn hoàn thành sau release |
| Cancel queued task | Single-thread executor bị task đầu chiếm | Task sau không chạy, `isCancelled()`, `get()` ném `CancellationException` |
| Cancel running task | Worker báo `started` trước khi chờ interruptible | `cancel(true)`, `InterruptedException`, `finally` hoàn tất |
| Direct interrupt | Thread đã vào vùng chờ | Worker xử lý interruption, khôi phục/truyền tiếp tín hiệu, kết thúc |
| Cancel non-cooperative CPU work | Task không kiểm tra cờ | Không giả định `cancel(true)` dừng được task; đánh giá cần bổ sung điểm cancel |
| CompletableFuture cancel | Computation bị giữ bởi latch trong executor riêng | Future cancelled nhưng computation không bị cancel interrupt |
| Failure khác cancellation | Callable cố ý ném lỗi | `Future.get()` ném `ExecutionException`; task khác không tự bị cancel |
| Timeout tranh chấp với interrupt | Hai tín hiệu có thể xảy ra gần nhau | Chấp nhận outcomes theo API, không suy ra thứ tự chưa được đồng bộ |
| Cleanup sau assertion fail | Latch chưa được mở khi test ném lỗi | `finally` luôn release, shutdown, xác nhận termination có hạn |
| Executor không dừng | Worker không phản hồi cancel hoặc chờ sai API | `awaitTermination` trả false; ghi rõ worker còn sống |
| Deadline tổng | Nhiều thao tác chờ kế tiếp | Tất cả bước dùng **ngân sách thời gian còn lại**, không reset timeout mỗi bước |

### Cạnh tranh giữa các tín hiệu

Khi `cancel`, `interrupt` và timeout xảy ra gần nhau, scheduler có thể khiến thread quan sát các sự kiện theo thứ tự khác nhau. Test **một nhánh cụ thể** phải điều khiển thứ tự bằng latch/barrier. Test **race thật** nên kiểm tra tập outcome được phép và invariant cuối cùng; không assert lịch chạy duy nhất nếu không có quan hệ happens-before xác định.

## 8. Áp dụng trong JUnit 5 khi dự án có framework

Dùng JUnit Jupiter, có thể đổi các phép `check` thành `assertTrue`, `assertFalse`, `assertThrows`, `assertEquals`. Ví dụ sau là **method minh họa**, cần import JUnit 5 và `java.util.concurrent` cùng các annotation trong test class:

```java
@Test
void timedGetDoesNotCancelRunningTask() throws Exception {
    ExecutorService pool = Executors.newSingleThreadExecutor();
    CountDownLatch started = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    try {
        Future<String> future = pool.submit(() -> {
            started.countDown();
            release.await();
            return "ok";
        });
        assertTrue(started.await(3, TimeUnit.SECONDS));
        assertThrows(TimeoutException.class,
                () -> future.get(100, TimeUnit.MILLISECONDS));
        assertFalse(future.isDone());

        release.countDown();
        assertEquals("ok", future.get(3, TimeUnit.SECONDS));
    } finally {
        release.countDown();
        pool.shutdownNow();
        assertTrue(pool.awaitTermination(3, TimeUnit.SECONDS));
    }
}
```

Phân biệt hai assertion thời gian của JUnit:

- `assertTimeout(Duration, executable)` chạy executable rồi đánh giá thời lượng, không dùng để dừng tác vụ khi quá hạn.
- `assertTimeoutPreemptively(Duration, executable)` chạy executable trên một thread khác và thử ngắt thread khi timeout; không bảo đảm công việc không hợp tác sẽ dừng. Thread-local context và tác vụ side effect cũng có thể tiếp tục không như dự định.

Với test concurrency, kiểm tra **outcome + tín hiệu + cleanup** thường cho chẩn đoán hữu ích hơn chỉ bao một đoạn bằng assert-timeout. Timeout ở cấp framework test runner cũng khác timeout của method đang test.

## 9. Chẩn đoán test treo và test flaky

**Nếu chỉ timeout ở CI:** xem test đang chờ mốc `started`, mốc `finished`, hay kết quả `Future.get`; log tên mốc và nới ngân sách an toàn theo CI. Đừng dùng `Thread.sleep` để “sửa” lỗi thứ tự.

**Nếu `isCancelled` true nhưng tiến trình chưa thoát:** task có thể chưa nhận interrupt, không chặn tại API interruptible, hoặc nuốt `InterruptedException`. Dùng latch trong `finally` để kiểm chứng. `Future.isDone()` cũng có thể true do exception trước khi mọi tài nguyên ứng dụng đóng xong.

**Nếu JVM không thoát sau test:** còn non-daemon thread của executor, latch chưa release, task vẫn chờ lock/I/O, hoặc `shutdown()` mà không có interrupt với task bị chặn. Dọn dẹp đúng thứ tự: release mọi latch test kiểm soát, `shutdownNow()` nếu policy cho phép, `awaitTermination` có hạn, kiểm tra false như một thất bại cụ thể.

**Nếu kết quả thay đổi theo lịch chạy:** xem test có đang giả định `submit` đồng nghĩa “task đã chạy”, `cancel` đồng nghĩa “worker đã kết thúc”, hoặc dùng thứ tự dòng log làm chứng cứ. Thêm mốc đồng bộ và kiểm tra invariant cuối.

**Nếu lỗi có vẻ là timeout nhưng thực ra là interrupt:** `InterruptedException` nói thread test đang chờ bị ngắt; kiểm tra ai gọi `interrupt`, và đừng vô tình xóa cờ bằng `Thread.interrupted()` ở một helper.

Có thể dùng thread dump/JDK diagnostics để xác định thread đang WAITING/BLOCKED/RUNNABLE và stack tương ứng. Quan sát trạng thái thread chỉ là một snapshot; cần đối chiếu với lock, queue và điểm đồng bộ của bài test.

## 10. Những lỗi thường gặp và checklist review

1. **Timeout = cancel?** Sai. `get(timeout)` không tự cancel task; sau timeout có thể cân nhắc `cancel(true)` theo ý nghĩa nghiệp vụ.
2. **`cancel(true)` luôn giết worker?** Sai. Interrupt là hợp tác, có API không nhận interrupt hoặc code phớt lờ cờ ngắt.
3. **`cancel(false)` luôn thất bại nếu task chạy?** Không nên mặc định. Tùy `Future` implementation, task có thể được đánh dấu canceled nhưng vẫn chạy; API không yêu cầu interrupt trong trường hợp này.
4. **`CompletableFuture.cancel(true)` giống `FutureTask.cancel(true)`?** Sai. Với `CompletableFuture`, tham số có tác dụng khác: nó không interrupt computation.
5. **Nuốt `InterruptedException` là ổn?** Sai. Nếu caller cần biết công việc bị ngắt, phải truyền tín hiệu/khôi phục cờ và thoát theo contract.
6. **`Thread.interrupted()` chỉ đọc cờ?** Sai. Nó xóa cờ của thread hiện tại; `isInterrupted()` mới là phép đọc không xóa.
7. **`Thread.sleep` giúp test xác định thứ tự?** Sai. Dùng `CountDownLatch` hoặc primitive đồng bộ phù hợp.
8. **`isDone()` chứng minh worker đã cleanup?** Sai. Một `Future` bị cancel có thể đã done về mặt state khi worker còn chạy.
9. **`shutdown()` chắc chắn dừng mọi task?** Sai. Nó không tự interrupt task đã chạy; dùng `awaitTermination` và policy cleanup phù hợp.
10. **Retry sau timeout luôn an toàn?** Sai. Công việc nền có thể đã tạo side effect trước khi caller mất kết quả; thiết kế idempotency/đối soát nếu cần.

Khi review một bài test, hãy xác định rõ: actor nào phát tín hiệu, worker chắc chắn đã tới mốc nào, kỳ vọng nào thuộc hợp đồng API, outcome nào được phép nếu xảy ra race, và mọi worker có được kết thúc sau cả nhánh pass lẫn fail không.

## Kết luận

**Timeout giới hạn thời gian chờ; interruption yêu cầu thread hợp tác; cancellation đánh dấu/hủy kết quả và có thể gửi interruption tùy API.** Test tốt xác minh riêng outcome của caller, phản ứng của worker và việc giải phóng tài nguyên. Dùng latches để tạo thứ tự có kiểm soát, phép chờ hữu hạn để bảo vệ test suite, và kiểm tra trạng thái thực thay vì dựa vào `sleep` hay `isDone()` đơn lẻ.