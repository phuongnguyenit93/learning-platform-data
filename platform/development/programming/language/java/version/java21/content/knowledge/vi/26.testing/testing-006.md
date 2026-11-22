# Kiểm thử task chạy trên virtual thread theo hành vi cần bảo đảm

## Mục tiêu

Virtual thread trong Java 21 cho phép chạy nhiều task với chi phí thread thấp hơn, đặc biệt khi task thường chờ I/O. Khi kiểm thử, điều quan trọng là xác nhận hành vi mà ứng dụng cần bảo đảm: kết quả đúng, lỗi được truyền về caller, task có thể phối hợp đồng thời và phản ứng với yêu cầu hủy.

Nếu hợp đồng của thành phần yêu cầu task phải chạy trên virtual thread, test cũng cần xác nhận loại thread thực thi. Tuy nhiên, test không nên phụ thuộc vào số carrier, tên thread nội bộ, thứ tự scheduler hoặc thời điểm lập lịch chính xác. Bài học này sử dụng JUnit Jupiter, `Future`, `CountDownLatch` và API thread ổn định của Java 21 để viết các kiểm thử xác định và ít phụ thuộc timing.

## 1. Kiểm thử hợp đồng quan sát được

Một test tốt tập trung vào kết quả hoặc hiệu ứng có ý nghĩa với caller. Với task chạy trên virtual thread, các hợp đồng thường cần xác nhận gồm:

- Task trả về kết quả đúng hoặc tạo side effect đúng.
- Exception của task được truyền qua cơ chế lấy kết quả.
- Các task độc lập có thể tiến triển đồng thời khi thiết kế yêu cầu concurrency.
- Task có thể phản ứng với interrupt khi caller yêu cầu hủy.
- Nếu kiến trúc yêu cầu virtual thread, phần xử lý thực sự chạy trên virtual thread.
- Tài nguyên và trạng thái task được dọn đúng khi task hoàn tất hoặc thất bại.

Không nên viết test yêu cầu scheduler phải chọn một carrier cụ thể, virtual thread phải chạy theo thứ tự cố định, hoặc số platform thread phải bằng một giá trị chính xác. Những chi tiết đó không phải hợp đồng của `newVirtualThreadPerTaskExecutor()`.

## 2. Kiểm thử task thực thi trên virtual thread

`Thread.currentThread().isVirtual()` cho biết thread hiện tại có phải virtual thread hay không. Nếu một API nội bộ hoặc thành phần hạ tầng cam kết thực thi task trên virtual thread, có thể kiểm tra điều kiện này ngay bên trong task.

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class VirtualThreadExecutionTest {
    @Test
    void taskRunsOnVirtualThread() throws Exception {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            boolean virtual = executor.submit(
                    () -> Thread.currentThread().isVirtual())
                    .get(2, TimeUnit.SECONDS);

            assertTrue(virtual);
        }
    }
}
```

Assertion nằm bên trong task nên kiểm tra đúng thread thực thi. Đọc `Thread.currentThread().isVirtual()` trong test thread JUnit chỉ cho biết test runner đang chạy trên loại thread nào; điều đó không chứng minh task được submit đã chạy trên virtual thread.

Chỉ nên assert `isVirtual()` khi loại thread là một phần của hợp đồng cần kiểm thử. Nếu ứng dụng chỉ yêu cầu kết quả nghiệp vụ đúng và không công khai loại thread, test nên tập trung vào kết quả, không khóa implementation vào virtual thread.

## 3. Kiểm thử virtual thread tạo trực tiếp

Khi code sử dụng `Thread.startVirtualThread()` hoặc builder, có thể kết hợp `FutureTask` để lấy kết quả và exception một cách rõ ràng:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class DirectVirtualThreadTest {
    @Test
    void unstartedVirtualThreadRunsTaskAfterStart() throws Exception {
        FutureTask<Boolean> task = new FutureTask<>(
                () -> Thread.currentThread().isVirtual());

        Thread worker = Thread.ofVirtual()
                .name("test-worker")
                .unstarted(task);

        worker.start();

        assertTrue(task.get(2, TimeUnit.SECONDS));
        worker.join();
    }
}
```

`FutureTask` giữ kết quả của callable, còn `Thread` chịu trách nhiệm thực thi nó. `get()` có timeout để test không chờ vô hạn nếu task không hoàn tất. `join()` đợi thread kết thúc trước khi test thoát.

Không cần assert tên thread hoặc ID của worker. Tên trong ví dụ chỉ hỗ trợ đọc log khi điều tra lỗi.

## 4. Kiểm thử kết quả nghiệp vụ, không chỉ kiểm tra loại thread

Loại thread chỉ là một thuộc tính thực thi. Test quan trọng hơn thường là task có trả kết quả đúng và giữ đúng quy tắc nghiệp vụ hay không.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class VirtualTaskResultTest {
    @Test
    void taskReturnsExpectedBusinessResult() throws Exception {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var result = executor.submit(() -> calculateTotal(120, 30));

            assertEquals(150, result.get(2, TimeUnit.SECONDS));
        }
    }

    private static int calculateTotal(int subtotal, int fee) {
        return subtotal + fee;
    }
}
```

Trong ứng dụng thực tế, thay `calculateTotal()` bằng thao tác nghiệp vụ cần kiểm tra. Nếu logic không phụ thuộc thread, hãy tách phần nghiệp vụ để có thể test trực tiếp; chỉ cần thêm test executor ở nơi cần xác nhận cách chạy task.

## 5. Phối hợp task đồng thời mà không dựa vào `Thread.sleep()`

Không nên dùng `Thread.sleep()` để giả định task A đã chạy trước task B hoặc scheduler đã chuyển sang một thread khác. Sleep chỉ trì hoãn thread trong một khoảng thời gian; nó không tạo ra bảo đảm đồng bộ.

`CountDownLatch` giúp test đợi đến khi các task đã tới một điểm xác định. Ví dụ sau xác nhận hai task đều bắt đầu trước khi test cho phép chúng đi tiếp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;

class VirtualTaskConcurrencyTest {
    @Test
    void independentTasksCanReachWorkPointConcurrently() throws Exception {
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> first = executor.submit(() -> awaitRelease("first", bothStarted, release));
            Future<String> second = executor.submit(() -> awaitRelease("second", bothStarted, release));

            try {
                assertTrue(bothStarted.await(5, TimeUnit.SECONDS),
                        "Cả hai task cần đạt điểm đồng bộ trước khi được giải phóng");
            } finally {
                release.countDown();
            }

            assertEquals("first", first.get(2, TimeUnit.SECONDS));
            assertEquals("second", second.get(2, TimeUnit.SECONDS));
        }
    }

    private static String awaitRelease(String value,
                                       CountDownLatch bothStarted,
                                       CountDownLatch release)
            throws InterruptedException, TimeoutException {
        bothStarted.countDown();
        if (!release.await(30, TimeUnit.SECONDS)) {
            throw new TimeoutException("Test không giải phóng task đúng hạn");
        }
        return value;
    }
}
```

Nếu executor chạy task tuần tự trên một worker duy nhất, task đầu sẽ chờ ở `release` và task thứ hai không thể giảm latch xuống 0; test sẽ thất bại sau timeout. Với virtual-thread-per-task executor, hai task có thể cùng tiến đến điểm đồng bộ.

Timeout trong test chỉ là giới hạn an toàn để test không treo. Nó không khẳng định scheduler phải hoàn tất trong đúng một khoảng thời gian xác định trên mọi máy. Điều test bảo đảm là cả hai task có cơ hội tiến triển trước khi test giải phóng latch.

## 6. Kiểm thử exception từ task

Khi submit một `Callable`, exception phát sinh trong task được lưu trong `Future`. Caller nhận `ExecutionException` khi gọi `get()`; nguyên nhân gốc có thể được đọc qua `getCause()`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class VirtualTaskExceptionTest {
    @Test
    void taskFailureIsReportedThroughFuture() {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var failed = executor.submit(() -> {
                throw new IllegalArgumentException("invalid input");
            });

            ExecutionException exception = assertThrows(
                    ExecutionException.class,
                    () -> failed.get(2, TimeUnit.SECONDS));

            assertInstanceOf(IllegalArgumentException.class, exception.getCause());
            assertEquals("invalid input", exception.getCause().getMessage());
        }
    }
}
```

Test xác nhận lỗi được truyền về caller qua `Future`, không giả định exception tự động ném trên thread JUnit. Nếu ứng dụng có lớp chuyển đổi exception sang lỗi nghiệp vụ, hãy kiểm tra cả loại lỗi và thông tin cần giữ lại.

## 7. Kiểm thử cancellation theo cơ chế interrupt hợp tác

`Future.cancel(true)` yêu cầu hủy task và có thể gửi interrupt đến thread thực thi. Nó không cưỡng chế dừng mọi đoạn code. Task cần gọi API blocking có thể phản ứng với interrupt hoặc tự kiểm tra trạng thái interrupt tại các điểm an toàn.

Test sau xác nhận task đã vào vùng chờ, nhận yêu cầu cancellation và quan sát được `InterruptedException`:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class VirtualTaskCancellationTest {
    @Test
    void taskRespondsToCancellationInterrupt() throws Exception {
        CountDownLatch enteredWait = new CountDownLatch(1);
        CountDownLatch interruptObserved = new CountDownLatch(1);

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<?> task = executor.submit(() -> {
                enteredWait.countDown();
                try {
                    new CountDownLatch(1).await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    interruptObserved.countDown();
                }
            });

            assertTrue(enteredWait.await(2, TimeUnit.SECONDS));
            assertTrue(task.cancel(true));
            assertTrue(interruptObserved.await(2, TimeUnit.SECONDS),
                    "Task cần quan sát interrupt trước khi kết thúc");
        }
    }
}
```

Test dùng latch để biết task đã vào vùng chờ trước khi gọi `cancel(true)`. Latch thứ hai xác nhận task thực sự quan sát interrupt; chỉ kiểm tra `cancel()` trả về `true` là chưa đủ để chứng minh code task đã chạy cleanup.

Trong production, phần `catch (InterruptedException)` thường cần dọn tài nguyên trong `finally`, truyền exception lên tầng gọi hoặc kết thúc theo hợp đồng hủy. Việc khôi phục interrupt status là phù hợp khi code không truyền tiếp `InterruptedException` nhưng muốn giữ tín hiệu cho tầng trên.

## 8. Kiểm thử task cleanup khi hoàn tất hoặc thất bại

Task chạy trên virtual thread thường có vòng đời riêng, nhưng tài nguyên mà task sử dụng vẫn cần được đóng đúng cách: stream, socket, transaction, lock hoặc context. Hãy kiểm tra hiệu ứng cleanup thay vì chỉ kiểm tra thread đã kết thúc.

Ví dụ dùng `try-with-resources` để bảo đảm tài nguyên được đóng khi task thành công hoặc ném lỗi:

```java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class VirtualTaskCleanupTest {
    @Test
    void resourceIsClosedWhenTaskFails() {
        AtomicBoolean closed = new AtomicBoolean();

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var task = executor.submit(() -> {
                try (TestResource resource = new TestResource(closed)) {
                    throw new IllegalStateException("work failed");
                }
            });

            ExecutionException failure = assertThrows(
                    ExecutionException.class,
                    () -> task.get(2, TimeUnit.SECONDS));
            assertInstanceOf(IllegalStateException.class, failure.getCause());
        }

        assertTrue(closed.get());
    }

    private static final class TestResource implements AutoCloseable {
        private final AtomicBoolean closed;

        private TestResource(AtomicBoolean closed) {
            this.closed = closed;
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }
}
```

Trong dự án thực tế, thay `TestResource` bằng abstraction tài nguyên cần kiểm tra hoặc mock/fake có thể quan sát được. Assertion nên xác nhận resource được đóng, transaction được rollback hoặc context được xóa theo đúng hợp đồng.

## 9. Không kiểm thử chi tiết triển khai của scheduler

Virtual-thread scheduler là thành phần runtime của JDK. Test ứng dụng không nên khóa vào các chi tiết có thể thay đổi theo JDK, cấu hình hoặc môi trường:

- Số carrier thread chính xác.
- Tên hoặc ID của carrier thread.
- Thứ tự chính xác giữa các task đồng thời.
- Thời gian task phải được scheduler đưa lên CPU.
- Một virtual thread cụ thể phải luôn chạy trên cùng carrier.
- Số virtual thread đang sống phải bằng số platform thread.

Nếu cần kiểm tra performance, khả năng chịu tải hoặc số lượng task lớn, hãy dùng benchmark/load test riêng với môi trường kiểm soát được. Unit test nên kiểm tra tính đúng đắn và đồng bộ bằng latch, barrier, future hoặc các primitive phù hợp.

## 10. Khi nào nên assert `isVirtual()`?

Không phải mọi test có virtual thread đều cần gọi `isVirtual()`:

| Loại thành phần | Có nên assert `isVirtual()`? | Lý do |
|---|---|---|
| Hạ tầng được thiết kế để luôn chạy task trên virtual thread | Có | Loại thread là một phần của hợp đồng thực thi |
| Business service chỉ cần kết quả đúng | Thường không | Loại thread là chi tiết triển khai của caller |
| Code dùng `ExecutorService` được inject từ bên ngoài | Chỉ khi cấu hình executor là hợp đồng | Test nên tôn trọng abstraction được inject |
| Adapter chọn platform hay virtual thread theo cấu hình | Có, trong test cho từng cấu hình | Xác nhận cấu hình được áp dụng đúng |
| Benchmark throughput hoặc latency | Không dùng unit assertion đơn giản | Cần đo trong workload và môi trường phù hợp |

Nếu loại thread là cấu hình, hãy test cả hai nhánh hoặc kiểm tra wiring ở composition root. Tránh đưa điều kiện `isVirtual()` vào business logic chỉ để làm test pass.

## 11. Những lỗi kiểm thử thường gặp

| Lỗi | Vì sao không đáng tin cậy | Cách làm phù hợp |
|---|---|---|
| Dùng `Thread.sleep()` để chờ task bắt đầu | Không bảo đảm task đã đến điểm cần kiểm tra | Dùng `CountDownLatch`, `Phaser` hoặc `Future` |
| Chỉ kiểm tra `Future.cancel(true)` trả về `true` | Chưa chứng minh task đã quan sát interrupt hoặc cleanup | Dùng tín hiệu đồng bộ từ task để xác nhận hành vi |
| Assert số carrier thread cố định | Scheduler có thể thay đổi theo runtime và cấu hình | Assert kết quả task hoặc metric có scope rõ ràng |
| Assert thứ tự output của các task đồng thời | Thứ tự lập lịch không được bảo đảm | Kiểm tra tập kết quả hoặc điều kiện đồng bộ cụ thể |
| Chỉ assert `isVirtual()` | Không xác nhận kết quả nghiệp vụ | Kiểm tra cả kết quả, exception và side effect |
| Chờ `Future.get()` không timeout trong test | Test có thể treo vô hạn khi lỗi | Dùng timeout hợp lý cho thao tác chờ |
| Nghĩ `Future` bị cancel nghĩa là code đã dừng | Task có thể chưa phản ứng với interrupt | Quan sát điểm kết thúc hoặc cleanup riêng |
| Chạy load test lớn trong unit test | Kết quả phụ thuộc máy và gây test suite chậm/flaky | Tách benchmark và load test khỏi unit test |

## 12. Checklist cho test virtual-thread task

Trước khi hoàn tất bộ test, hãy xác nhận:

1. Test đang kiểm tra hành vi công khai hoặc hợp đồng thực thi cần bảo đảm chưa?
2. `isVirtual()` chỉ được assert khi loại thread là yêu cầu của thành phần chưa?
3. Kết quả và exception của task có được lấy qua `Future` hoặc cơ chế tương ứng không?
4. Đồng bộ giữa test thread và task có dùng latch/barrier thay vì sleep không?
5. Mọi thao tác chờ trong test có timeout để tránh treo suite không?
6. Cancellation test có xác nhận task thực sự quan sát interrupt hoặc chạy cleanup không?
7. Tài nguyên có được đóng khi task thành công, lỗi hoặc bị hủy không?
8. Test có tránh phụ thuộc số carrier, thread ID, tên thread và thứ tự scheduler không?
9. Benchmark và kiểm thử tải có được tách khỏi unit test không?

## Kết luận

Kiểm thử task chạy trên virtual thread nên tập trung vào hành vi mà ứng dụng cần bảo đảm: kết quả, exception, phối hợp đồng thời, cancellation và cleanup. Chỉ kiểm tra `Thread.currentThread().isVirtual()` khi loại thread là một phần của hợp đồng. Dùng `Future` để lấy kết quả, `CountDownLatch` để đồng bộ tại điểm xác định và timeout để test không chờ vô hạn. Tránh dựa vào sleep, số carrier hoặc thứ tự scheduler. Các nguyên tắc này giúp test ổn định trên Java 21 và ít phụ thuộc chi tiết triển khai của runtime.
