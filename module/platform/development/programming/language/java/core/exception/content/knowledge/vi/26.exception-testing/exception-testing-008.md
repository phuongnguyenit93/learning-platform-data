# Kiểm thử ngoại lệ qua Future và CompletableFuture trong Java

> **Phạm vi:** Java Core → Exception → Kiểm thử. Bài học hướng dẫn viết test có thể lặp lại cho tác vụ bất đồng bộ: lỗi phát sinh trong worker, cách `Future.get()` bao lỗi bằng `ExecutionException`, cách `CompletableFuture.join()` dùng `CompletionException`, xử lý cancellation, timeout, interrupt và các stage phụ thuộc. Ví dụ chạy độc lập bằng Java 17; các test JUnit 5 được phân biệt rõ là cần thư viện ngoài JDK.

## 1. Vì sao kiểm thử exception bất đồng bộ khác kiểm thử đồng bộ?

Trong mã đồng bộ, ngoại lệ ném trên chính call stack của hàm kiểm thử:

~~~java
// Đoạn minh họa JUnit 5:
assertThrows(IllegalArgumentException.class,
        () -> parseRequired("not-a-number"));
~~~

Nhưng khi một công việc được nộp vào `ExecutorService` hoặc chạy trong `CompletableFuture`, lỗi có thể xảy ra trên **thread khác**. Test phải xác định **kênh mà API dùng để công bố thất bại**. Nếu chỉ bao câu lệnh nộp tác vụ bằng `assertThrows`, test rất có thể không thấy lỗi của worker.

~~~java
// Đoạn minh họa JUnit 5; pool có sẵn:
Future<Integer> task = pool.submit(() -> {
    throw new IllegalStateException("worker failed");
});

// Sai mục tiêu: submit thường trả Future bình thường.
// assertThrows(IllegalStateException.class, () -> pool.submit(...));

// Đúng mục tiêu: đọc kết quả của tác vụ qua get().
ExecutionException wrapper =
        assertThrows(ExecutionException.class, task::get);
assertInstanceOf(IllegalStateException.class, wrapper.getCause());
~~~

Một phép kiểm thử exception bất đồng bộ nên xác minh **ba lớp**: (1) *tác vụ* thực sự thất bại, (2) *cơ chế completion* báo lỗi đúng hợp đồng, (3) *nguyên nhân nghiệp vụ* có đúng loại, message/code, cause và trạng thái dữ liệu hay không.

## 2. Bảng định hướng: nên chờ và bắt loại nào?

| API/đường chạy | Lỗi ở worker thể hiện với caller | Loại exception test thường bắt | Câu hỏi tiếp theo |
|---|---|---|---|
| Gọi `Runnable.run()` trực tiếp | Exception đi lên cùng stack | Kiểu lỗi gốc | Có thực sự dùng thread mới không? |
| `new Thread(...).start()` | Không tự ném lỗi `run()` sang caller | `UncaughtExceptionHandler` hoặc kênh tự thiết kế | `join()` chỉ chờ, không ném lỗi worker |
| `ExecutorService.submit(Callable)` | Lỗi được ghi trong `Future` | `ExecutionException` từ `get()` | `getCause()` có đúng lỗi gốc? |
| `ExecutorService.submit(Runnable)` | Future cũng chứa lỗi task | `ExecutionException` | `Runnable` không cần trả giá trị |
| `CompletableFuture.supplyAsync(...)` | Future hoàn tất bất thường | `CompletionException` từ `join()`; `ExecutionException` từ `get()` | Cause và dependent stage thế nào? |
| `CompletableFuture.failedFuture(ex)` | Future lỗi ngay, không cần chạy worker | `join()`/`get()` như trên | Đừng suy diễn đã tạo thread |
| `CompletableFuture.cancel(...)` | Future được đánh dấu canceled | `CancellationException` với future trực tiếp | Công việc thật có dừng không? |
| `get(timeout, unit)` trên future chưa hoàn tất | Hết thời gian chờ | `TimeoutException` | Task có thể **vẫn đang chạy** |
| `get()` khi thread chờ bị interrupt | Chờ bị ngắt | `InterruptedException` | Không nhầm với lỗi computation |

Cần phân biệt ***đường quan sát*** với ***đường gây lỗi***. Test nhắm vào `get()`/`join()` để quan sát một lỗi đã được giữ trong future. Nó không chứng minh exception tự truyền xuyên qua hai thread.

## 3. Quy tắc cốt lõi của Future.get()

`Future<T>` đại diện cho kết quả có thể chưa sẵn sàng. Với Future từ `ExecutorService.submit()`, nếu `Callable.call()` hay `Runnable.run()` ném exception, framework ghi nhận lỗi. Khi caller gọi `get()`:

- Nếu task thành công, trả về kết quả. Với `submit(Runnable)` thường là `null` nếu không cung cấp result riêng.
- Nếu task thất bại bằng exception, `get()` ném **`ExecutionException`**. `getCause()` cho phép xem exception gốc.
- Nếu Future bị hủy, `get()` ném **`CancellationException`**; không xem đây là `ExecutionException` thông thường.
- Nếu **thread đang chờ** bị interrupt, `get()` có thể ném **`InterruptedException`**, bất kể kết quả cuối của task.
- Với `get(timeout, unit)`, một task chưa xong đúng hạn có thể dẫn đến **`TimeoutException`**. Timeout của người đợi không chứng minh task thất bại hay chấm dứt.

Một test tốt không chỉ assert wrapper:

~~~java
// JUnit 5; future nhận từ pool.submit(...).
ExecutionException ex =
        assertThrows(ExecutionException.class, future::get);

Throwable root = ex.getCause();
assertInstanceOf(IllegalArgumentException.class, root);
assertEquals("invalid amount", root.getMessage());
~~~

Kiểm tra `cause` quan trọng vì mọi lỗi task khác nhau có thể đều đến caller dưới cùng một lớp `ExecutionException`. Trong các API có wrapper domain, có thể cần kiểm tra chuỗi cause theo hợp đồng của chính ứng dụng, nhưng không nên bóc các lớp tùy tiện rồi bỏ bối cảnh hữu ích.

## 4. CompletableFuture.join() và get(): hai cách quan sát một lỗi

`CompletableFuture<T>` vừa là `Future<T>`, vừa triển khai `CompletionStage<T>`. Có hai cách chờ kết quả thường dùng:

- `join()` không khai báo checked exception. Với exceptional completion thông thường, nó ném `CompletionException` có `cause` liên quan tới lỗi computation.
- `get()` tuân hợp đồng `Future`, có `ExecutionException` và `InterruptedException` trong chữ ký; có thể bị hủy bằng `CancellationException`.
- Cả hai có thể báo `CancellationException` **trực tiếp** nếu chính CompletableFuture được hủy. Không nên khẳng định mọi lỗi của `join()` đều là `CompletionException`.
- `getNow(defaultValue)` trả giá trị mặc định khi chưa hoàn tất, nhưng **không** phải cơ chế che lỗi: nếu đã hoàn tất bất thường, nó vẫn có thể ném exception dạng completion.

Ví dụ dùng một nguyên nhân được tạo sẵn:

~~~java
// Đoạn minh họa có thể đặt trong một phương thức Java:
IllegalArgumentException original =
        new IllegalArgumentException("bad payload");

CompletableFuture<Integer> failed =
        CompletableFuture.failedFuture(original);

// join(): CompletionException
try {
    failed.join();
} catch (CompletionException ex) {
    assert ex.getCause() == original;
}

// get(): ExecutionException
try {
    failed.get();
} catch (ExecutionException ex) {
    assert ex.getCause() == original;
}
~~~

Đoạn trên cần các import `java.util.concurrent.*` và phương thức bao khai báo `throws InterruptedException`, hoặc tự catch tương ứng; các câu `assert` thuần Java còn phụ thuộc cờ `-ea`. Phần test JUnit 5 ở dưới dùng `assertThrows` và `assertSame` rõ ràng, không phụ thuộc `-ea`.

**Lưu ý:** với lỗi được bọc qua nhiều dependent stage, số lớp `CompletionException` và cách propagation cụ thể có thể khác đường gốc. Ưu tiên kiểm tra `cause`/loại exception được bảo đảm thay vì giả định mọi stage trả cùng object wrapper.

## 5. Chương trình Java 17 chạy độc lập: lỗi Future và CompletableFuture

Lưu thành **`FutureExceptionTestingDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureExceptionTestingDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> submitted = pool.submit(() -> {
                throw new IllegalArgumentException("invalid amount");
            });

            try {
                submitted.get();
            } catch (ExecutionException ex) {
                System.out.println("Future.get: "
                        + ex.getClass().getSimpleName());
                System.out.println("Future cause: "
                        + ex.getCause().getClass().getSimpleName()
                        + ": " + ex.getCause().getMessage());
            }

            IllegalStateException original =
                    new IllegalStateException("service unavailable");
            CompletableFuture<String> failed =
                    CompletableFuture.failedFuture(original);

            try {
                failed.join();
            } catch (CompletionException ex) {
                System.out.println("CF.join: "
                        + ex.getClass().getSimpleName());
                System.out.println("CF cause: "
                        + ex.getCause().getClass().getSimpleName()
                        + ": " + ex.getCause().getMessage());
            }

            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("CF.get: "
                        + ex.getClass().getSimpleName());
            }

            AtomicInteger transformCalls = new AtomicInteger();
            CompletableFuture<Integer> dependent =
                    failed.thenApply(value -> {
                        transformCalls.incrementAndGet();
                        return value.length();
                    });

            try {
                dependent.join();
            } catch (CompletionException ex) {
                System.out.println("dependent cause: "
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("transform calls: " + transformCalls.get());

            CompletableFuture<String> recovered =
                    failed.exceptionally(ex -> "fallback");
            System.out.println("recovered: " + recovered.join());
            System.out.println("source still exceptional: "
                    + failed.isCompletedExceptionally());

            CompletableFuture<String> cancelled = new CompletableFuture<>();
            cancelled.cancel(true);
            try {
                cancelled.join();
            } catch (CancellationException ex) {
                System.out.println("cancelled.join: "
                        + ex.getClass().getSimpleName());
            }

            CompletableFuture<String> neverCompleted =
                    new CompletableFuture<>();
            try {
                neverCompleted.get(0, TimeUnit.NANOSECONDS);
            } catch (TimeoutException ex) {
                System.out.println("pending.get: "
                        + ex.getClass().getSimpleName());
            } catch (ExecutionException ex) {
                throw new AssertionError("pending task did not run", ex);
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac FutureExceptionTestingDemo.java
java FutureExceptionTestingDemo
~~~

**Stdout chính xác:**

~~~text
Future.get: ExecutionException
Future cause: IllegalArgumentException: invalid amount
CF.join: CompletionException
CF cause: IllegalStateException: service unavailable
CF.get: ExecutionException
dependent cause: IllegalStateException
transform calls: 0
recovered: fallback
source still exceptional: true
cancelled.join: CancellationException
pending.get: TimeoutException
~~~

### Vì sao kết quả xác định?

1. `submitted.get()` chờ tác vụ trong executor kết thúc thất bại rồi mới in; không cần `Thread.sleep()` để đoán thời điểm lỗi xảy ra.
2. `failedFuture(original)` hoàn tất bất thường **ngay khi được tạo**, không cần worker thực thi. `join()` biểu diễn lỗi thành `CompletionException`, còn `get()` biểu diễn thành `ExecutionException`.
3. `thenApply` chỉ chạy ở nhánh thành công. Vì nguồn đã lỗi, `transformCalls` vẫn là `0`; dependent stage báo exceptional completion.
4. `exceptionally` tạo stage có kết quả dự phòng. `recovered.join()` trả `fallback` nhưng **`failed` vẫn lỗi**.
5. Future `cancelled` được hủy trực tiếp nên `join()` ném `CancellationException` thay vì một kết quả.
6. `neverCompleted` không có producer; `get(0, NANOSECONDS)` kiểm tra trạng thái ngay và ném `TimeoutException`. Test này không phụ thuộc máy nhanh/chậm, nhưng **không chứng minh đã có một operation thực tế chạy quá hạn**.
7. `pool.shutdownNow()` dọn executor. Trong test integration có task không tuân interrupt, cần bổ sung timeout shutdown và kiểm tra rò rỉ tài nguyên.

Chương trình này minh họa contract exception. Nó không benchmark performance và không kiểm thử tác dụng phụ/transaction của một worker thực tế.

## 6. assertThrows đúng tầng để tránh false positives

Một lỗi thường thấy:

~~~java
// SAI về phạm vi kiểm thử (JUnit 5, executor có sẵn).
assertThrows(IllegalStateException.class, () -> {
    pool.submit(() -> {
        throw new IllegalStateException("task failed");
    });
});
~~~

Lời gọi `submit` thường chỉ nộp công việc rồi trả `Future`; exception thực thi không tự nhảy vào stack của `assertThrows`. Nếu lambda bên ngoài tình cờ ném `IllegalStateException` do lỗi khác, test có thể **pass sai nguyên nhân**.

Tách rõ điểm nộp và điểm quan sát:

~~~java
Future<?> future = pool.submit(() -> {
    throw new IllegalStateException("task failed");
});

ExecutionException ex =
        assertThrows(ExecutionException.class, future::get);
assertInstanceOf(IllegalStateException.class, ex.getCause());
assertEquals("task failed", ex.getCause().getMessage());
~~~

Tương tự với CompletableFuture:

~~~java
CompletableFuture<String> stage =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid id"));

CompletionException ex =
        assertThrows(CompletionException.class, stage::join);
assertInstanceOf(IllegalArgumentException.class, ex.getCause());
~~~

Khi code trả CompletableFuture đã lỗi ngay từ validation, test vẫn phải gọi `join()` hoặc kiểm tra stage để thấy **exceptional completion**. Nó không nên mặc định kỳ vọng method tạo future ném lỗi đồng bộ, trừ khi **hợp đồng API** công bố fail-fast bằng throw.

## 7. Bộ kiểm thử JUnit 5 hoàn chỉnh: những hợp đồng quan trọng

Đoạn dưới đây là **một lớp test JUnit 5** cần có `junit-jupiter` và JUnit test engine trong dự án; JDK 17 **không** tự kèm JUnit. Lưu tại đường dẫn test tương ứng, tên file **`AsyncExceptionContractTest.java`**. Ví dụ tránh sử dụng thread sleep và kiểm tra cả wrapper lẫn cause.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(5)
class AsyncExceptionContractTest {
    private final ExecutorService pool =
            Executors.newSingleThreadExecutor();

    @AfterEach
    void cleanup() {
        pool.shutdownNow();
    }

    @Test
    void submitWrapsTaskFailureWithExecutionException() {
        Future<Integer> future = pool.submit((Callable<Integer>) () -> {
            throw new IllegalArgumentException("bad row");
        });

        ExecutionException ex =
                assertThrows(ExecutionException.class, future::get);
        assertInstanceOf(IllegalArgumentException.class, ex.getCause());
        assertEquals("bad row", ex.getCause().getMessage());
    }

    @Test
    void completableFutureJoinAndGetExposeDifferentWrappers() {
        IllegalStateException cause =
                new IllegalStateException("repository down");
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(cause);

        CompletionException fromJoin =
                assertThrows(CompletionException.class, failed::join);
        ExecutionException fromGet =
                assertThrows(ExecutionException.class, failed::get);

        assertSame(cause, fromJoin.getCause());
        assertSame(cause, fromGet.getCause());
    }

    @Test
    void failedSourceSkipsSuccessTransform() {
        AtomicInteger calls = new AtomicInteger();
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> derived =
                source.thenApply(value -> {
                    calls.incrementAndGet();
                    return value.length();
                });

        IllegalArgumentException cause =
                new IllegalArgumentException("invalid request");
        assertTrue(source.completeExceptionally(cause));

        CompletionException ex =
                assertThrows(CompletionException.class, derived::join);
        assertSame(cause, ex.getCause());
        assertEquals(0, calls.get());
    }

    @Test
    void exceptionallyRecoversOnlyDependentStage() {
        CompletableFuture<String> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("offline"));

        CompletableFuture<String> recovered =
                source.exceptionally(ex -> "fallback");

        assertEquals("fallback", recovered.join());
        assertTrue(source.isCompletedExceptionally());
        assertFalse(recovered.isCompletedExceptionally());
    }

    @Test
    void cancelledSourceThrowsCancellationDirectly() {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<Integer> derived =
                source.thenApply(String::length);

        assertTrue(source.cancel(true));
        assertTrue(source.isCancelled());
        assertTrue(source.isCompletedExceptionally());

        assertThrows(CancellationException.class, source::join);
        CompletionException ex =
                assertThrows(CompletionException.class, derived::join);
        assertInstanceOf(CancellationException.class, ex.getCause());
    }

    @Test
    void pendingGetTimesOutWithoutFailureCompletion() {
        CompletableFuture<String> pending = new CompletableFuture<>();

        assertThrows(TimeoutException.class,
                () -> pending.get(0, TimeUnit.NANOSECONDS));
        assertFalse(pending.isDone());

        assertTrue(pending.complete("ready"));
        assertEquals("ready", pending.join());
    }

    @Test
    void workerHasStartedBeforeItsFailureIsReleased()
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("interrupted", ex);
                }
                throw new IllegalStateException("expected failure");
            });

            assertTrue(started.await(2, TimeUnit.SECONDS));
            assertFalse(future.isDone());

            release.countDown();
            ExecutionException ex =
                    assertThrows(ExecutionException.class, future::get);
            assertInstanceOf(IllegalStateException.class, ex.getCause());
            assertEquals("expected failure",
                    ex.getCause().getMessage());
        } finally {
            release.countDown();
        }
    }
}
~~~

### Điều đáng học từ bộ test

- `assertThrows` đặt tại lời gọi `future.get()` hoặc `stage.join()`, không phải tại `submit` hoặc `supplyAsync`.
- Test `join` và `get` dùng **cùng một cause** để phân biệt wrapper mà không cần giả định kết quả scheduler.
- Test dependent stage xác nhận **callback nhánh thành công không chạy** và nguyên nhân gốc được giữ.
- Test `exceptionally` xác nhận stage **mới** thành công nhưng stage nguồn vẫn lỗi; tránh hiểu nhầm recovery làm biến đổi quá khứ.
- Test cancellation phân biệt `CancellationException` trực tiếp từ nguồn với ngoại lệ được truyền qua derived stage.
- Test timeout dùng pending future chưa có producer; assert `isDone()==false` để chứng minh timeout chờ **không hoàn tất/cancel future**.
- Test có `CountDownLatch` điều phối trạng thái để biết worker đã chạy nhưng chưa được cho phép ném; không cần `Thread.sleep()`. `@Timeout(5)` làm test không chờ vô hạn trong điều kiện bất thường.
- `@AfterEach` dừng executor. Với test thật, có thể cần chờ termination có hạn hoặc dùng teardown thích hợp để đảm bảo tài nguyên không rò rỉ.

Một lỗi trong test `CountDownLatch` có thể tạo nhánh `IllegalStateException("interrupted", cause)`; test kỳ vọng `"expected failure"` để phát hiện nếu worker đã bị ngắt trước khi được release. Đây là lý do việc chỉ assert loại exception ở mọi đường có thể chưa đủ.

## 8. Kiểm thử checked exception của Callable

`Callable<V>.call()` khai báo `throws Exception`; vì vậy một tác vụ có thể ném `IOException` mà không cần bọc thành unchecked tại nơi thực thi:

~~~java
// JUnit 5; pool đã khởi tạo.
Future<String> future = pool.submit(() -> {
    throw new java.io.IOException("file unavailable");
});

ExecutionException ex =
        assertThrows(ExecutionException.class, future::get);
assertInstanceOf(java.io.IOException.class, ex.getCause());
assertEquals("file unavailable", ex.getCause().getMessage());
~~~

Điều cần kiểm tra không phải “`Callable` ném checked exception xuyên luồng”. Thực chất `submit` lưu `Throwable` do `call()` phát sinh; `get()` ở caller ném một `ExecutionException` có cause là `IOException`.

Với `Runnable.run()`, chữ ký không khai báo checked exception; code trong Runnable phải xử lý hoặc bọc lỗi checked trước khi cho task kết thúc bất thường. Test cần phân loại đúng wrapper mà ứng dụng đã tạo.

## 9. Kiểm thử exception của CompletableFuture chain

Một chain có nhiều điểm có thể thất bại:

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture("12")
                .thenApply(Integer::parseInt)
                .thenApply(n -> n / 0);
~~~

Đoạn này **không chạy tới stage cuối** nếu stage parse lỗi; ở ví dụ cụ thể `"12"` parse thành công, rồi phép chia cho zero trong stage tiếp theo tạo `ArithmeticException`. Test nên kiểm tra đúng stage/cause:

~~~java
CompletionException ex =
        assertThrows(CompletionException.class, result::join);
assertInstanceOf(ArithmeticException.class, ex.getCause());
~~~

Những câu hỏi quan trọng:

1. Khi stage trước thất bại, stage sau chỉ chạy ở nhánh thành công có bị bỏ qua không?
2. `thenApply`/`thenCompose` có thêm wrapper hay đổi nguyên nhân gốc theo hợp đồng không?
3. `exceptionally` có làm kết quả thành công giả ngoài ý định không?
4. `handle` có trả fallback đúng và có làm lộ `null` không?
5. `whenComplete` được dùng để **quan sát** hay tác giả tưởng nó sẽ phục hồi? Nếu nguồn lỗi, stage tạo từ `whenComplete` thường vẫn lỗi.
6. Nếu callback phục hồi tự ném lỗi mới, test cần xác nhận stage phụ thuộc phản ánh **lỗi callback**.
7. Nếu một stage bị cancel, có consumer nào vô tình khôi phục cancellation thành kết quả thành công không?

Không nên chỉ test `source.isCompletedExceptionally()`; điều đó không nói được caller nhận được gì sau composition. Hãy kiểm tra **stage cuối được công bố trong API** và những stage quan trọng ở giữa khi chúng có hợp đồng riêng.

## 10. Kiểm thử failedFuture, completeExceptionally và cạnh tranh hoàn tất

`CompletableFuture.failedFuture(cause)` tạo một future hoàn tất bất thường ngay, tiện cho test logic của consumer mà không cần thread thực:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad id"));
~~~

`completeExceptionally(cause)` dùng cho future **đang tồn tại**. Nó trả boolean thể hiện lần gọi có hoàn tất được future đang pending hay không. Test nên xác minh hoàn tất lần đầu thắng:

~~~java
CompletableFuture<String> promise = new CompletableFuture<>();
IllegalArgumentException cause =
        new IllegalArgumentException("bad input");

assertTrue(promise.completeExceptionally(cause));
assertFalse(promise.complete("late success"));
assertTrue(promise.isCompletedExceptionally());

CompletionException ex =
        assertThrows(CompletionException.class, promise::join);
assertSame(cause, ex.getCause());
~~~

Đừng gọi `completeExceptionally` hai lần và mong lần sau ghi đè lần trước. Trong cạnh tranh giữa `complete`, `completeExceptionally` và `cancel`, trạng thái thắng phụ thuộc thứ tự thực thi. Nếu muốn test race, dùng `CountDownLatch`/`CyclicBarrier` hoặc một executor có kiểm soát, sau đó assert **một kết quả hợp lệ trong tập được phép**, thay vì hard-code luồng nào thắng.

Lưu ý `CompletableFuture.cancel(boolean)` có ngữ nghĩa trả boolean riêng: một future đã canceled có thể tiếp tục trả `true` khi gọi `cancel` lần nữa. Đừng áp dụng kết luận từ `completeExceptionally` cho `cancel` mà không đọc hợp đồng của lớp.

## 11. CancellationException không chứng minh worker đã dừng

`Future.cancel(true)` và `CompletableFuture.cancel(true)` có đặc điểm khác nhau:

- Với `FutureTask` thường được trả từ `ExecutorService.submit`, `cancel(true)` có thể **yêu cầu interrupt** worker đang chạy. Task vẫn phải hợp tác mới dừng.
- Với `CompletableFuture`, tham số `mayInterruptIfRunning` **không dùng để điều khiển computation**; chỉ canceled future không chứng minh supplier bị interrupt.
- `CancellationException` từ `get()`/`join()` báo trạng thái completion bị hủy, **không phải bằng chứng transaction rollback**.
- Nếu có side effect trước khi cancel, tác dụng phụ có thể vẫn tồn tại.

Trong test, cần tách:

1. **Trạng thái future:** `isCancelled()`, `isDone()`, `isCompletedExceptionally()`, exception khi lấy kết quả.
2. **Trạng thái worker:** đã nhận tín hiệu hủy chưa, có kiểm tra flag/token không, có kết thúc không?
3. **Trạng thái nghiệp vụ:** dữ liệu có giữ invariant không, đã commit hay chưa, retry có an toàn không?

Một test chỉ `assertThrows(CancellationException.class, future::join)` không chứng minh được hai mục sau. Nếu yêu cầu hủy thực sự của API, test phải quan sát task qua latch, token hoặc trạng thái được đồng bộ hóa phù hợp.

## 12. TimeoutException và phép đo thời gian

Có hai mục tiêu test khác nhau:

### Test hợp đồng timeout của get

Tạo một future chưa complete và gọi `get(0, TimeUnit.NANOSECONDS)`; ta kiểm tra `TimeoutException` khi chưa có kết quả. Đây là cách **không phụ thuộc scheduler** để kiểm tra hợp đồng chờ.

### Test deadline thật của một service

Nếu cần xác minh hệ thống timeout sau một hạn định, test phải kiểm soát thời gian bằng clock abstraction/scheduler thử nghiệm khi framework cho phép, hoặc dùng timeout ngắn có giới hạn và chấp nhận điều kiện concurrency/integration. Không assert độ chính xác ở mức mili giây chỉ bằng `System.currentTimeMillis()` vì scheduler, GC và tải máy có thể gây sai lệch.

**Rất quan trọng:** `TimeoutException` từ `Future.get(timeout)` **không tự làm Future hoàn tất bất thường**. Nó chỉ cho biết người gọi đã chờ quá lâu. Ngược lại, `CompletableFuture.orTimeout(...)` có thể hoàn tất chính future bằng `TimeoutException` khi quá hạn; test hai API phải khác nhau.

Để kiểm thử `orTimeout` mà không dùng thời gian thực, có thể thiết kế wrapper nhận scheduler/clock có thể fake; `CompletableFuture.orTimeout` của JDK không cung cấp clock injection trực tiếp. Với integration test dùng đồng hồ thực, luôn có timeout test tổng thể và cleanup rõ ràng.

## 13. Interrupt: không nhầm lỗi của thread đang chờ với lỗi task

`InterruptedException` do `Future.get()` được ném tại **thread gọi get** khi thread đó bị ngắt trong lúc chờ. Nó không phải exception gốc của task.

Một test có thể tạo một thread chỉ làm việc chờ:

~~~java
// Trích đoạn Java; waitingFuture là CompletableFuture chưa hoàn tất.
Thread waiter = new Thread(() -> {
    try {
        Thread.currentThread().interrupt();
        waitingFuture.get();
        throw new AssertionError("expected interruption");
    } catch (InterruptedException expected) {
        Thread.currentThread().interrupt();
        // Ghi nhận bằng AtomicBoolean/latch nếu test cần quan sát.
    } catch (ExecutionException unexpected) {
        throw new AssertionError(unexpected);
    }
});
waiter.start();
waiter.join();
~~~

Ví dụ này chủ động đặt interrupt flag cho **chính waiter** trước `get()` và giả định future chưa hoàn tất. Mã chỉ là trích đoạn; test đầy đủ cần assert kênh quan sát và không để exception trong thread con bị bỏ sót.

Khi bắt `InterruptedException` và không thể khai báo `throws` tiếp, thường nên `Thread.currentThread().interrupt()` để phục hồi cờ rồi thoát theo chính sách hủy. Nhưng nếu test cần chứng minh cờ được xóa khi thao tác chặn ném lỗi, phải đo **trước** khi reinterrupt; đừng nhầm giá trị cờ sau khối catch với hành vi nguyên thủy của API.

Test cancellation cũng cần phân biệt `CancellationException` (future bị hủy) và `InterruptedException` (thread chờ bị ngắt). Chúng không thay thế nhau.

## 14. Tránh Thread.sleep để điều phối tác vụ trong test

Một test thiếu ổn định thường viết:

~~~java
// Phản ví dụ; độ tin cậy phụ thuộc tải máy.
Future<?> future = pool.submit(this::doWork);
Thread.sleep(50);
assertTrue(future.isDone());
~~~

50 ms không cam kết worker đã được scheduler chạy hoặc I/O đã xong. Trên máy CI quá tải, test fail ngẫu nhiên. Ngay cả việc tăng lên 500 ms chỉ làm test chậm hơn, không cung cấp một **quan hệ đồng bộ hóa**.

Thay bằng các primitive có ý nghĩa:

- `Future.get()`: đợi completion và nhận failure.
- `CountDownLatch`: báo “đã đến điểm X”, “được phép tiếp tục”.
- `CyclicBarrier` hoặc `Phaser`: điều phối nhiều participant khi thực sự cần.
- `CompletableFuture`: tạo nguồn hoàn tất có kiểm soát bằng `complete`/`completeExceptionally`.
- `AtomicReference<Throwable>`/`AtomicBoolean`: lưu quan sát từ thread khác khi có memory visibility thích hợp.
- `await(timeout, unit)` hoặc test-level timeout: bảo vệ test khỏi treo mãi nếu có bug.

Ví dụ đồng bộ hóa:

~~~java
// Trích đoạn; pool đã khởi tạo.
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

try {
    Future<?> task = pool.submit(() -> {
        started.countDown();
        try {
            release.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("cancelled", ex);
        }
        throw new IllegalArgumentException("bad data");
    });

    if (!started.await(2, TimeUnit.SECONDS)) {
        throw new AssertionError("worker did not start");
    }
    release.countDown();

    ExecutionException ex =
            assertThrows(ExecutionException.class, task::get);
    assertInstanceOf(IllegalArgumentException.class, ex.getCause());
} finally {
    release.countDown();
}
~~~

Đoạn này cần import các kiểu concurrent và JUnit 5. Việc `release.countDown()` trong `finally` tránh để worker kẹt khi test dừng sớm. Đây là **đồng bộ theo sự kiện** thay vì đoán thời gian.

## 15. Test một worker mà không đọc kết quả của Future có thể bỏ sót lỗi

`ExecutorService.submit()` ghi nhận exception vào `Future`. Nếu test nộp task rồi kết thúc khi chưa `get()` hoặc chưa có kênh quan sát failure, nó có thể **pass giả** dù worker đã ném exception.

~~~java
// Không đủ nếu mục tiêu là xác minh exception của task:
pool.submit(() -> {
    throw new IllegalStateException("unexpected failure");
});
// Test có thể kết thúc ở đây mà không assert gì về failure.
~~~

Các cách đúng:

- Giữ Future và gọi `get()`, assert `ExecutionException.getCause()`.
- Nếu API trả CompletableFuture, attach handler hoặc `join()` stage mà caller được công bố.
- Với fire-and-forget, thiết kế error sink/uncaught handler hoặc callback giám sát và test chính kênh đó.
- Với `Thread` trần, cài `UncaughtExceptionHandler` ghi exception vào `AtomicReference`; `Thread.join()` chỉ chờ thread kết thúc, **không ném lại exception**.

Đừng lấy stderr mặc định hay log không được capture làm bằng chứng tự động rằng test đã quan sát thất bại. Một test tự động phải assert kênh có thể đọc/kiểm soát.

## 16. Test exceptional completion không tự chứng minh rollback trạng thái

Nếu task cập nhật một phần dữ liệu rồi ném lỗi, Future báo thất bại chính xác nhưng dữ liệu có thể hỏng:

~~~java
// Mã minh họa về rủi ro, không phải chương trình độc lập.
Future<?> future = pool.submit(() -> {
    accountA.debit(amount);
    failingOperation();
    accountB.credit(amount);
});
~~~

Một test chỉ assert `ExecutionException` mới kiểm tra **kênh exception**, chưa kiểm tra invariant “tổng số dư không đổi”. Với nghiệp vụ cần atomicity, test nên:

1. Chuẩn bị trạng thái ban đầu rõ ràng.
2. Dùng fault injection khiến bước nhạy cảm ném lỗi.
3. Chờ task hoàn tất bằng `get()`/`join()`.
4. Kiểm tra ngoại lệ/cause đúng.
5. Đọc trạng thái qua kênh đồng bộ hóa đúng và assert invariant hoặc strong exception guarantee theo contract.
6. Xác minh side effect ngoài JVM, retry/idempotency khi tương tác DB/network.

Lỗi bất đồng bộ được truyền tốt không tự cho biết thao tác đã rollback. Một `CompletableFuture.cancel(true)` hoặc `orTimeout(...)` cũng không tự đảo ngược side effect. Vì vậy kiểm thử thông báo thất bại và kiểm thử tính nhất quán dữ liệu phải là **hai nhóm assertion độc lập**.

## 17. Những nhầm lẫn thường gặp

1. **`assertThrows` bao `submit` thay vì `get()`:** lỗi task được chuyển qua Future.
2. **Mong `Thread.join()` ném lại lỗi của `run()`:** join chỉ chờ thread kết thúc.
3. **Chỉ assert `ExecutionException`:** quên kiểm tra cause và message/code nghiệp vụ.
4. **Coi `CompletionException` và `ExecutionException` là một:** chúng xuất hiện ở API quan sát khác nhau.
5. **Coi mọi `join()` thất bại là `CompletionException`:** cancellation trực tiếp có thể ném `CancellationException`.
6. **Assert exception bằng regex vào `getMessage()`:** message không phải machine-readable contract; nên assert type/code/cause và chỉ assert message khi nó là yêu cầu của test.
7. **Dùng `Thread.sleep` để đợi worker:** dễ flaky khi chạy CI hoặc scheduler bận.
8. **Thử timeout bằng cách sleep đúng bằng deadline:** race và jitter có thể làm test không ổn định.
9. **Bỏ Future sau khi `submit`:** lỗi task có thể không được test nhìn thấy.
10. **Dùng `exceptionally` rồi tưởng nguồn hết lỗi:** recovery tạo stage phụ thuộc mới.
11. **Dùng `whenComplete` như luôn phục hồi lỗi:** nó chủ yếu quan sát; lỗi nguồn thường vẫn truyền.
12. **Test cancel rồi suy ra thread đã dừng:** `CompletableFuture.cancel(true)` không interrupt supplier theo hợp đồng.
13. **Nuốt `InterruptedException` trong test worker:** che tín hiệu hủy và làm tearDown không đáng tin.
14. **Quên shutdown executor:** test leak thread hoặc làm bộ kiểm thử treo sau khi assertions hoàn tất.
15. **Chỉ assert exception, không assert trạng thái:** thiếu kiểm tra rollback/invariant trong code có side effect.
16. **Kiểm tra stage chưa hoàn tất bằng `get()` không timeout:** test có thể chờ vô hạn.
17. **Assert đúng cause ở một stage nhưng không assert stage public cuối:** caller thực có thể nhận wrapper/fallback khác.
18. **Dùng một test pass làm bằng chứng không có race:** concurrency correctness cần lập luận về synchronization và nhiều kịch bản.

## 18. Checklist xây test đáng tin

Trước khi hoàn thành test exception bất đồng bộ, hãy tự trả lời:

1. **API trả cái gì?** `Future`, `CompletableFuture`, `CompletionStage`, `Thread` hay callback?
2. **Lỗi phát sinh ở stack nào?** Nếu trong worker, caller nhận qua API completion chứ không bắt ở `submit`.
3. **Quan sát lỗi ở đâu?** `get()`, `join()`, handler, callback hay error sink.
4. **Wrapper dự kiến là gì?** `ExecutionException`, `CompletionException`, `CancellationException`, `InterruptedException` hay `TimeoutException`?
5. **Cause nào quan trọng?** Type, code, message trong hợp đồng, business ID, suppressed cause khi cần.
6. **Có stage phụ thuộc không?** Kiểm tra callback thành công không chạy sau lỗi và recovery đúng phạm vi.
7. **Có test trạng thái khi chưa hoàn tất không?** Không chờ vô hạn; timeout có hạn hoặc deterministic.
8. **Worker đã chắc chắn bắt đầu chưa?** Dùng latch/barrier thay vì sleep đoán.
9. **Cancellation có dừng công việc thật không?** Phân biệt completion state với control signal và side effect.
10. **Tài nguyên có được dọn không?** Executor, latch, file, network và dữ liệu được reset trong `finally`/teardown.
11. **Test có bỏ sót failure không?** Future bị bỏ, callback không quan sát hoặc thread exception chỉ in stderr.
12. **Sau khi lỗi, invariant dữ liệu vẫn đúng không?** Kiểm tra riêng theo contract nghiệp vụ.

## 19. Tổng kết

**Kiểm thử ngoại lệ qua Future và CompletableFuture** là kiểm thử **kênh kết quả của tác vụ**, không chỉ kiểm thử câu lệnh tạo/khởi chạy tác vụ. Với `Future.get()`, hãy bắt `ExecutionException` và kiểm tra `getCause()`. Với `CompletableFuture.join()`, hãy bắt `CompletionException` cho exceptional completion thông thường và kiểm tra cause; phân biệt cancellation trực tiếp bằng `CancellationException`. `CompletableFuture.get()` vẫn theo hợp đồng `Future`.

Hãy kiểm thử thêm dependent stages, fallback, cancellation, timeout, interrupt, dữ liệu sau thất bại và lifecycle của executor. Dùng `CountDownLatch`/`Future.get()` thay cho `Thread.sleep()` để kiểm soát thứ tự và tránh flaky tests. Cuối cùng, một test chỉ có giá trị khi nó thực sự **quan sát ngoại lệ từ đúng kênh** và kiểm chứng **loại lỗi, nguyên nhân và trạng thái** mà caller nhận được.

### Tham khảo chuẩn Java và JUnit

- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Java SE 17 — CancellationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [JUnit 5 — Assertions.assertThrows](https://junit.org/junit5/docs/current/user-guide/#writing-tests-assertions)
