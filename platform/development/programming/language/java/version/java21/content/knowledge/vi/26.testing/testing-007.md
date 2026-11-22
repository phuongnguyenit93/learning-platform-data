# Kiểm thử timeout, cancellation, interruption và cleanup

Các tác vụ bất đồng bộ và xử lý đồng thời cần có hành vi xác định khi hết thời gian chờ, khi caller hủy công việc hoặc khi thread nhận interrupt. Một bài test tốt phải xác minh cả kết quả quan sát được lẫn việc tài nguyên được giải phóng: task có dừng hay không, executor có kết thúc không, khóa hoặc kết nối có được nhả không và trạng thái interrupt có được giữ đúng không.

Trong Java 21, có thể kiểm thử những hành vi này bằng JUnit Jupiter, `Future`, `ExecutorService`, `CountDownLatch`, `Thread`, `CompletableFuture` và các API timeout của thư viện I/O. Nguyên tắc quan trọng là tạo đồng bộ xác định bằng latch hoặc barrier, đặt giới hạn chờ cho chính bài test và luôn có cleanup ngay cả khi assertion thất bại.

## 1. Phân biệt timeout, cancellation và interruption

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Điều cần kiểm thử |
|---|---|---|
| Timeout | Một thao tác hoặc caller đã chờ quá thời gian cho phép | API trả hoặc ném kết quả timeout đúng thời điểm |
| Cancellation | Có yêu cầu hủy một task hoặc computation | Task nhận yêu cầu hủy và kết thúc nếu có thể |
| Interruption | Một thread được yêu cầu dừng chờ hoặc phản hồi việc hủy qua interrupt flag | Code phản hồi interrupt đúng hợp đồng |
| Cleanup | Giải phóng tài nguyên và trạng thái sau khi thành công, lỗi, timeout hoặc cancel | Tài nguyên được đóng/nhả đúng một lần và không để task mồ côi |

Ví dụ, `Future.get(timeout, unit)` ném `TimeoutException` khi caller chờ quá thời hạn. Việc đó không tự động hủy task. Nếu muốn yêu cầu task dừng, caller phải gọi `future.cancel(true)` hoặc sử dụng cơ chế cancellation riêng của tác vụ.

Tương tự, `cancel(true)` yêu cầu interrupt thread đang chạy task nếu implementation có thể làm điều đó. Interrupt không phải lệnh cưỡng chế kết thúc thread; task phải hợp tác và phản hồi.

## 2. Kiểm thử timeout bằng Future.get

`Future.get(timeout, unit)` cho phép giới hạn thời gian caller chờ kết quả. Khi hết thời gian, nó ném `TimeoutException`, nhưng task có thể vẫn đang chạy.

Ví dụ JUnit Jupiter kiểm tra timeout mà không giả định task tự dừng:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class FutureTimeoutTest {
    @Test
    void getTimesOutWhileTaskKeepsRunning() throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                release.await();
                return "done";
            });

            assertTrue(started.await(1, TimeUnit.SECONDS));

            assertThrows(
                    TimeoutException.class,
                    () -> future.get(50, TimeUnit.MILLISECONDS)
            );

            // Timeout của get không tự hủy task.
            assertFalse(future.isDone());

            release.countDown();
            assertEquals("done", future.get(1, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(
                    1, TimeUnit.SECONDS));
        }
    }
}
```

Hai latch giúp test điều khiển thời điểm task bắt đầu và thời điểm task được phép hoàn tất. Test không cần dùng `Thread.sleep()` để phỏng đoán task đã chạy đến đâu.

Trong test thực tế, timeout 50 ms ở đây chỉ minh họa một khoảng chờ ngắn. Trên CI hoặc máy tải cao, nên chọn khoảng chờ đủ rộng để giảm flaky test, đồng thời luôn giữ một giới hạn tổng thể để test không treo vô hạn.

## 3. Kiểm thử cancel(true) và task phản hồi interrupt

Khi gọi `future.cancel(true)`, Future yêu cầu hủy task và gửi interrupt tới thread đang thực thi nếu task đã bắt đầu. Task phải phản hồi interrupt bằng cách thoát, ném lại `InterruptedException` hoặc chuyển tiếp tín hiệu hủy theo hợp đồng.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class FutureCancellationTest {
    @Test
    void cancelInterruptsRunningTaskAndRunsCleanup()
            throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch cleaned = new CountDownLatch(1);

        try {
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                } finally {
                    cleaned.countDown();
                }
            });

            assertTrue(started.await(1, TimeUnit.SECONDS));
            assertTrue(future.cancel(true));

            assertTrue(cleaned.await(1, TimeUnit.SECONDS));
            assertTrue(future.isCancelled());
            assertThrows(
                    CancellationException.class,
                    future::get
            );
        } finally {
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(
                    1, TimeUnit.SECONDS));
        }
    }
}
```

Test xác minh ba điều riêng biệt:

- Yêu cầu cancel được chấp nhận.
- Task đi qua khối `finally`, nghĩa là cleanup của task đã chạy.
- Future chuyển sang trạng thái cancelled và `get()` ném `CancellationException`.

Không nên chỉ kiểm tra `future.isCancelled()` rồi kết luận thread đã dừng. Trạng thái Future phản ánh trạng thái của Future; để kiểm tra tác vụ đã cleanup, cần một tín hiệu độc lập như latch hoặc trạng thái tài nguyên.

### 3.1. cancel(false) khác cancel(true)

- `cancel(false)` không yêu cầu interrupt thread đang chạy. Nếu task chưa bắt đầu, nó có thể bị ngăn không cho chạy; nếu đã chạy, task thường tiếp tục.
- `cancel(true)` yêu cầu interrupt thread đang chạy nếu có thể.
- Nếu task đã hoàn thành, `cancel` thường trả về `false` vì không còn gì để hủy.
- Khi Future đã bị hủy, gọi `get()` ném `CancellationException`.

Kết quả `cancel(true)` trả về `true` cho biết Future đã chuyển sang trạng thái cancelled; không phải bằng chứng rằng mọi side effect của task đã được thu hồi hoặc thread đã kết thúc ngay lập tức.

## 4. Kiểm thử code phản hồi InterruptedException

Các thao tác như `Thread.sleep`, `Object.wait`, `Thread.join` và nhiều API chờ trong `java.util.concurrent` có thể ném `InterruptedException`. Khi exception này được ném, interrupt status của thread thường đã bị xóa.

Nếu phương thức có thể truyền `InterruptedException` lên caller, nên khai báo và truyền tiếp:

```java
void awaitWork() throws InterruptedException {
    blockingOperation();
}
```

Nếu không thể truyền exception lên, cần khôi phục interrupt status trước khi kết thúc hoặc chuyển tiếp lỗi:

```java
void process() {
    try {
        blockingOperation();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

Test nên kiểm tra hành vi ở ranh giới phù hợp. Ví dụ sau xác minh một worker nhận interrupt, đi qua cleanup và khôi phục interrupt status khi nó xử lý exception tại chỗ:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class InterruptionTest {
    @Test
    void workerRestoresInterruptStatusAndCleansUp()
            throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch cleaned = new CountDownLatch(1);
        AtomicBoolean interruptRestored = new AtomicBoolean();

        Thread worker = Thread.ofPlatform().unstarted(() -> {
            try {
                started.countDown();
                new CountDownLatch(1).await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                interruptRestored.set(
                        Thread.currentThread().isInterrupted());
            } finally {
                cleaned.countDown();
            }
        });

        worker.start();
        try {
            assertTrue(started.await(1, TimeUnit.SECONDS));

            worker.interrupt();
            worker.join(1_000);

            assertFalse(worker.isAlive());
            assertTrue(cleaned.await(1, TimeUnit.SECONDS));
            assertTrue(interruptRestored.get());
        } finally {
            worker.interrupt();
            worker.join(1_000);
        }
    }
}
```

Test dùng `isInterrupted()` để đọc trạng thái mà không xóa nó. Ngược lại, `Thread.interrupted()` là phương thức static kiểm tra và xóa interrupt status của thread hiện tại; gọi nó trong code production hoặc test có thể làm thay đổi hành vi cần kiểm tra.

Nếu phương thức đang test khai báo `throws InterruptedException`, test có thể kiểm tra rằng exception được truyền lên mà không yêu cầu phương thức tự khôi phục cờ interrupt. Việc khôi phục thường thuộc về tầng bắt exception nếu tầng đó quyết định không truyền tiếp.

## 5. Không nuốt interrupt

Một lỗi phổ biến là bắt `InterruptedException` rồi bỏ qua:

```java
try {
    blockingOperation();
} catch (InterruptedException ignored) {
    // Sai: tín hiệu hủy bị bỏ qua.
}
```

Khi đó task có thể tiếp tục làm việc dù caller đã yêu cầu dừng. Nếu phương thức không thể truyền exception, hãy khôi phục cờ interrupt hoặc chuyển thành exception phù hợp nhưng giữ nguyên trạng thái interrupt.

Vòng lặp xử lý task cũng nên kiểm tra interruption:

```java
void processItems(Iterable<Item> items)
        throws InterruptedException {
    for (Item item : items) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Task bị yêu cầu dừng");
        }

        process(item);
    }
}
```

Không phải mọi thao tác đều tự động dừng khi interrupt. Một đoạn tính toán CPU dài cần chủ động kiểm tra cờ interrupt định kỳ; một thư viện hoặc native call có thể có quy tắc hủy riêng. Test cần mô phỏng đúng loại công việc mà ứng dụng thực sự sử dụng.

## 6. Phân biệt assertTimeout và assertTimeoutPreemptively

JUnit Jupiter cung cấp hai cách kiểm tra thời gian thực thi:

| API | Cách hoạt động | Hệ quả |
|---|---|---|
| `assertTimeout(duration, executable)` | Chạy executable trên thread gọi test và kiểm tra thời gian sau khi nó kết thúc | Không cưỡng chế dừng executable khi quá hạn |
| `assertTimeoutPreemptively(duration, executable)` | Chạy executable trên thread khác và ngắt khi hết thời gian | Có thể interrupt tác vụ, nhưng tác vụ phải phản hồi |

Ví dụ với `assertTimeout`:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class TimeoutAssertionTest {
    @Test
    void operationCompletesWithinBudget() {
        assertTimeout(Duration.ofSeconds(1), () -> {
            calculateResult();
        });
    }
}
```

Cách này phù hợp khi thao tác dự kiến kết thúc và muốn kiểm tra tổng thời gian. Nếu thao tác bị treo, assertion chỉ có thể báo vượt thời gian sau khi executable trả về; nó không phải watchdog có thể dừng code.

Ví dụ với `assertTimeoutPreemptively`:

```java
@Test
void interruptibleOperationHasAnUpperBound() {
    assertTimeoutPreemptively(
            Duration.ofSeconds(1),
            () -> interruptibleOperation()
    );
}
```

Cách này hữu ích khi cần giới hạn thời gian test, nhưng chỉ nên dùng với code có thể chịu được việc chạy trên thread khác và phản hồi interruption. Nó có thể gây vấn đề nếu code dựa vào `ThreadLocal`, transaction gắn với thread, security context hoặc các cơ chế lưu trạng thái theo thread. Nếu executable bỏ qua interrupt, thread thực thi có thể tiếp tục chạy sau khi assertion đã thất bại.

Với test concurrency phức tạp, thường tốt hơn khi điều khiển worker bằng latch, giới hạn thời gian chờ ở từng bước và cleanup rõ ràng, thay vì dựa hoàn toàn vào preemptive timeout.

## 7. Kiểm thử CompletableFuture timeout

`CompletableFuture.orTimeout(timeout, unit)` làm cho future hoàn tất exceptionally bằng `TimeoutException` nếu nó chưa hoàn thành trước thời hạn. `completeOnTimeout(value, timeout, unit)` hoàn tất future bình thường bằng giá trị fallback khi hết thời gian.

Hai phương thức này không tự động bảo đảm computation hoặc I/O nguồn đã dừng. Nếu future được nối với một task đang chạy, cần thiết kế cancellation cho task nguồn riêng.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class CompletableFutureTimeoutTest {
    @Test
    void orTimeoutCompletesFutureExceptionally() {
        CompletableFuture<String> future =
                new CompletableFuture<>();

        assertThrows(
                CompletionException.class,
                () -> future.orTimeout(30, TimeUnit.MILLISECONDS)
                             .join()
        );

        assertTrue(future.isCompletedExceptionally());
    }

    @Test
    void completeOnTimeoutUsesFallback() {
        CompletableFuture<String> future =
                new CompletableFuture<>();

        String result = future.completeOnTimeout(
                "fallback", 30, TimeUnit.MILLISECONDS
        ).join();

        assertEquals("fallback", result);
    }
}
```

Các test này xác minh trạng thái của CompletableFuture. Nếu future đại diện cho một hoạt động I/O thực, cần thêm test xác minh hoạt động nền được hủy hoặc đóng theo đúng API mà ứng dụng sử dụng.

## 8. Kiểm thử cleanup khi thành công, lỗi và timeout

Tài nguyên như stream, socket, file handle, lock hoặc connection cần được giải phóng trong mọi đường đi. Với tài nguyên triển khai `AutoCloseable`, ưu tiên try-with-resources:

```java
String readConfig() throws IOException {
    try (var input = Files.newInputStream(configPath)) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
```

Test có thể dùng fake resource để xác minh `close()` được gọi kể cả khi thao tác ném exception:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class ResourceCleanupTest {
    static class FakeResource implements AutoCloseable {
        final AtomicBoolean closed = new AtomicBoolean();

        void use() throws IOException {
            throw new IOException("simulated failure");
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    @Test
    void resourceIsClosedWhenOperationFails() {
        FakeResource resource = new FakeResource();

        assertThrows(IOException.class, () -> {
            try (resource) {
                resource.use();
            }
        });

        assertTrue(resource.closed.get());
    }
}
```

Với resource được truyền vào try-with-resources như ví dụ, biến phải là final hoặc effectively final. Nếu test cần dùng lại resource sau khối try để kiểm tra trạng thái, cách viết trên phù hợp.

Đối với tài nguyên không triển khai `AutoCloseable`, đặt thao tác release trong `finally`. Tránh chỉ cleanup ở cuối đường chạy thành công vì timeout hoặc exception sẽ bỏ qua phần giải phóng.

## 9. Cleanup ExecutorService trong test

Executor cần được shutdown sau khi test kết thúc để không để worker hoặc task chờ tồn tại ngoài phạm vi test.

Một cách cleanup tường minh:

```java
static void stopExecutor(ExecutorService executor)
        throws InterruptedException {
    executor.shutdown();

    if (!executor.awaitTermination(1, TimeUnit.SECONDS)) {
        executor.shutdownNow();

        if (!executor.awaitTermination(1, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Executor không kết thúc sau shutdownNow");
        }
    }
}
```

Ý nghĩa:

- `shutdown()` ngừng nhận task mới nhưng cho phép task đã submit hoàn tất.
- `awaitTermination` chờ executor kết thúc trong thời hạn cho phép.
- `shutdownNow()` yêu cầu dừng các task đang chạy bằng interrupt và trả về các task đang chờ chưa được chạy; nó không bảo đảm task đang chạy sẽ dừng.
- Nếu executor không kết thúc, test nên báo lỗi thay vì âm thầm để worker tồn tại.

Java 21 cho phép dùng `ExecutorService` trong try-with-resources vì interface này triển khai `AutoCloseable`. `close()` thực hiện orderly shutdown và chờ task hoàn tất. Đây là lựa chọn tiện lợi cho task hữu hạn và hợp tác; nếu task có thể treo, cần thiết kế cancellation và giới hạn chờ trước khi đóng executor.

Trong test timeout, nên dùng `finally` để release latch và yêu cầu shutdown ngay cả khi assertion thất bại. Không dựa vào thứ tự chạy test hoặc việc JVM tự kết thúc để che giấu thread leak.

## 10. Kiểm thử cleanup của lock và trạng thái dùng chung

Khi code dùng `ReentrantLock`, phải bảo đảm unlock trong `finally`. Test có thể kiểm tra thread khác lấy được lock sau khi thao tác đầu tiên thất bại.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import java.util.concurrent.locks.ReentrantLock;
import org.junit.jupiter.api.Test;

class LockCleanupTest {
    @Test
    void lockIsReleasedWhenOperationThrows() throws Exception {
        ReentrantLock lock = new ReentrantLock();

        assertThrows(IllegalStateException.class, () -> {
            lock.lock();
            try {
                throw new IllegalStateException("failure");
            } finally {
                lock.unlock();
            }
        });

        assertTrue(lock.tryLock(1, TimeUnit.SECONDS));
        lock.unlock();
    }
}
```

Test này xác minh lock đã được nhả sau exception. Với intrinsic monitor từ `synchronized`, JVM tự nhả monitor khi thoát block, kể cả khi có exception; vẫn cần kiểm thử rằng trạng thái nghiệp vụ không bị cập nhật dở dang.

Không nên chỉ kiểm tra `isLocked()` trong lúc thread khác có thể đồng thời thay đổi lock. Dùng `tryLock` với timeout hoặc một giao thức đồng bộ xác định sẽ cho assertion đáng tin cậy hơn.

## 11. Kiểm thử với virtual thread trong Java 21

Virtual thread vẫn tuân theo interruption và cancellation của Java. Có thể dùng `Executors.newVirtualThreadPerTaskExecutor()` để chạy task test:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class VirtualThreadCancellationTest {
    @Test
    void virtualThreadRespondsToCancellation() throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch cleaned = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);

            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } finally {
                    cleaned.countDown();
                }
            });

            try {
                assertTrue(started.await(1, TimeUnit.SECONDS));
                assertTrue(future.cancel(true));
                assertTrue(cleaned.await(1, TimeUnit.SECONDS));
                assertTrue(future.isCancelled());
            } finally {
                release.countDown();
                future.cancel(true);
            }
        }
    }
}
```

Ví dụ dùng try-with-resources để đóng executor sau test. Task đang chờ latch sẽ thoát khi nhận interrupt và chạy khối finally.

Không nên giả định mọi thư viện I/O hoặc native call đều phản hồi interrupt giống `CountDownLatch.await()`. Hãy kiểm tra hợp đồng cancellation của API thực tế và bổ sung test tích hợp cho driver, client hoặc resource liên quan.

## 12. Tránh flaky test do thời gian và scheduling

Test đồng thời dễ không ổn định nếu phụ thuộc vào thời gian scheduling của máy. Những nguyên tắc sau giúp giảm flaky test:

- Dùng `CountDownLatch`, `CyclicBarrier` hoặc `Phaser` để xác định thời điểm thread đã đến một điểm cụ thể.
- Dùng timeout ở mọi thao tác chờ trong test, kể cả `await`, `get`, `join` và `awaitTermination`.
- Tránh dùng `Thread.sleep()` để giả định một task đã bắt đầu hoặc đã bị interrupt.
- Không kiểm tra thời gian thực thi bằng ngưỡng quá sát với thời gian lý thuyết.
- Đảm bảo mọi latch có đường release trong `finally`.
- Không dùng chung executor hoặc mutable state giữa các test nếu không có cơ chế cô lập.
- Khi kiểm tra deadline, dùng đồng hồ đơn điệu như `System.nanoTime()` để đo elapsed time.

Một test timeout nên có hai mức bảo vệ: timeout của thao tác đang kiểm tra và timeout tổng thể của test suite. Nếu thao tác bị lỗi và không phản hồi cancellation, giới hạn ngoài giúp phát hiện test bị treo thay vì chiếm worker vô hạn.

## 13. Kiểm tra interruption của chính test thread

Test framework hoặc môi trường chạy có thể interrupt thread thực thi test khi dừng hoặc hết thời gian. Không nên xóa interrupt status một cách vô tình.

Nếu test bắt `InterruptedException` chỉ để cleanup rồi tiếp tục truyền lỗi, hãy khôi phục interrupt status khi phù hợp:

```java
try {
    worker.join(1_000);
} catch (InterruptedException ex) {
    worker.interrupt();
    Thread.currentThread().interrupt();
    throw ex;
}
```

Trong test thực tế, nếu phương thức test khai báo `throws InterruptedException`, có thể để exception truyền lên sau khi cleanup cần thiết đã được thực hiện. Không nên bắt rồi bỏ qua exception chỉ để test tiếp tục.

Phân biệt thread đang test với thread worker: interrupt thread test không tự động interrupt worker. Nếu test bị gián đoạn, hãy chủ động hủy Future hoặc gọi `worker.interrupt()` trong cleanup.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `Future.get(timeout)` tự hủy task | Task có thể tiếp tục chạy sau timeout | Gọi `cancel(true)` khi chính sách yêu cầu hủy |
| Nghĩ `cancel(true)` cưỡng chế dừng thread | Task có thể bỏ qua interrupt | Viết task hợp tác và kiểm tra cleanup |
| Bắt rồi bỏ qua `InterruptedException` | Mất tín hiệu cancellation | Truyền tiếp hoặc khôi phục interrupt status |
| Dùng `Thread.sleep` để đồng bộ test | Phụ thuộc scheduler, dễ flaky | Dùng latch/barrier và bounded wait |
| Chỉ kiểm tra Future đã cancelled | Không chứng minh task đã cleanup | Kiểm tra latch, resource state hoặc executor termination |
| Dùng `assertTimeout` cho code có thể treo | Assertion không dừng code khi quá hạn | Dùng preemptive timeout có cân nhắc hoặc tự điều khiển task/cancellation |
| Dùng `assertTimeoutPreemptively` với transaction/thread-local | Code chạy trên thread khác, ngữ cảnh có thể mất | Dùng timeout không preemptive hoặc thiết kế test phù hợp |
| Không shutdown executor | Thread và task rò rỉ sang test khác | Cleanup trong finally hoặc try-with-resources |
| Nghĩ `shutdownNow()` bảo đảm executor kết thúc | Task có thể không phản hồi interrupt | Chờ termination có giới hạn và báo lỗi nếu không kết thúc |

## 15. Quy trình thiết kế test cho timeout và cancellation

Khi kiểm thử một thao tác có thể timeout hoặc bị hủy, hãy đi theo trình tự:

1. Xác định hợp đồng: timeout trả exception, fallback hay kết quả một phần.
2. Xác định timeout chỉ giới hạn caller chờ hay phải yêu cầu hủy task nền.
3. Tạo tín hiệu xác định để biết task đã bắt đầu, chẳng hạn latch.
4. Chờ bằng API có timeout để test không bị treo vô hạn.
5. Gửi cancellation hoặc interrupt theo đúng API production sử dụng.
6. Xác minh task phản hồi, cleanup chạy và trạng thái Future/thread đúng mong đợi.
7. Đóng resource và executor trong `finally` hoặc try-with-resources.
8. Chạy test nhiều lần trên môi trường CI đại diện để phát hiện phụ thuộc scheduling.

Một bài test đáng tin cậy kiểm tra cả hành vi trước và sau khi hủy: caller nhận đúng timeout/cancellation, worker phản hồi theo hợp đồng, và tài nguyên không bị giữ lại. Chỉ kiểm tra exception mà bỏ qua cleanup có thể để lọt lỗi nghiêm trọng trong ứng dụng.

## Tài liệu tham khảo

- [JUnit 5 User Guide — Assertions and Timeout Assertions](https://junit.org/junit5/docs/current/user-guide/)
- [Oracle Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Oracle Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 21 API — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Oracle Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 21 API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
