# Kiểm thử hủy tác vụ, dừng bộ thực thi và lỗi từ chối việc

## 1. Ba vòng đời cần được kiểm tra riêng

Khi dùng executor, có ba đối tượng dễ bị gộp nhầm:

| Thành phần | Điều cần biết |
| --- | --- |
| `Future` | Kết quả đã thành công, thất bại hay bị hủy? |
| Thân tác vụ | Mã của tác vụ đã thực sự thoát và dọn tài nguyên chưa? |
| Executor | Đã ngừng nhận việc, còn việc đang chạy/chờ hay đã kết thúc hoàn toàn? |

Một `Future` có thể chuyển sang trạng thái hủy trước khi thân tác vụ đã thoát. Một executor đã nhận `shutdown()` vẫn có thể đang chạy các việc cũ. Một yêu cầu mới có thể bị từ chối trước khi có `Future` trả về cho bên gọi.

Bài thực hành dùng `ThreadPoolExecutor` có giới hạn rõ ràng, `Future` từ `submit()` và tác vụ hợp tác với ngắt. Không suy rộng mọi chi tiết của ví dụ sang tất cả triển khai bất đồng bộ khác.

## 2. Hủy Future là yêu cầu hợp tác, không phải lệnh cưỡng bức kết thúc

`cancel(true)` cố hủy và có thể ngắt luồng đang thực hiện tác vụ theo khả năng triển khai. `cancel(false)` không yêu cầu ngắt tác vụ đang chạy. Nếu tác vụ đã hoàn tất thì yêu cầu hủy không thể đảo ngược kết quả đã hoàn tất. Cần kiểm tra trạng thái thay vì coi lời gọi hủy luôn thành công. [API Future.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean)).

Với tác vụ đã bị hủy, `get()` báo `CancellationException`. `isDone()` cũng có thể đúng do thành công, ngoại lệ hoặc hủy; không phải tín hiệu riêng của thành công.

Tác vụ muốn dừng kịp thời cần có điểm hợp tác: thoát khi nhận `InterruptedException`, kiểm tra cờ ngắt ở vòng tính toán hoặc dùng API I/O có cơ chế hủy/thời hạn phù hợp. Ngắt không tự hoàn tác dữ liệu đã ghi và không bảo đảm mọi lời gọi chặn đều dừng.

Nếu một tầng bắt `InterruptedException` mà không thể truyền tiếp, thường cần phục hồi trạng thái ngắt trước khi kết thúc/đưa lỗi lên trên. Trong tác vụ `Callable` của bài, ngoại lệ được truyền tiếp; không bị nuốt để tiếp tục chờ.

## 3. shutdown, shutdownNow và awaitTermination có ý nghĩa khác nhau

| Phương thức/trạng thái | Ý nghĩa cần kiểm chứng |
| --- | --- |
| `shutdown()` | Ngừng nhận việc mới; cho việc đã nhận tiếp tục thực hiện |
| `shutdownNow()` | Cố dừng việc đang chạy, ngừng khởi chạy việc đang chờ và trả danh sách việc chưa bắt đầu |
| `awaitTermination(...)` | Chờ có giới hạn cho executor kết thúc sau yêu cầu dừng |
| `isShutdown()` | Đã có yêu cầu dừng |
| `isTerminated()` | Đã kết thúc, không còn tác vụ đang chạy hoặc đang chờ |

`shutdown()` và `shutdownNow()` không tự chờ mọi tác vụ thoát. `shutdownNow()` chỉ cố gắng dừng, thường qua ngắt; tác vụ không hợp tác có thể tiếp tục chạy. `awaitTermination()` không thay cho lệnh khởi đầu dừng executor. [API ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Do đó, một ca kiểm thử chỉ gọi `shutdownNow()` rồi kiểm tra “không ném lỗi” chưa kiểm chứng đã dọn xong tài nguyên. Cần quan sát tác vụ và chờ kết thúc theo thời hạn phù hợp.

## 4. Dùng đồng bộ để dựng tình huống, không đoán bằng sleep

Muốn kiểm thử hủy tác vụ **đang chạy**, trước hết phải biết nó đã chạy. Muốn kiểm thử hàng đợi đầy, phải biết luồng làm việc đang bị giữ và có đúng một việc đang xếp hàng.

Bài dùng ba latch cho tác vụ bị giữ:

- `started`: tác vụ đã bắt đầu thân xử lý.
- `release`: cửa cho phép tác vụ kết thúc bình thường.
- `exited`: tín hiệu từ `finally` sau khi tác vụ rời phần chờ.

`CountDownLatch` cung cấp điểm phối hợp và quan hệ hiển thị dữ liệu giữa các luồng khi chờ thành công. Chỉ `sleep(100)` không tạo ra bằng chứng tác vụ đã vào trạng thái cần kiểm tra. [API CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Các lần chờ trên luồng kiểm thử có timeout. Con số 5 giây trong chương trình là giới hạn phát hiện treo của bài học, không phải cam kết hiệu năng hay deadline của sản phẩm. Trên môi trường chậm, chọn giới hạn phù hợp nhưng vẫn có điểm thất bại hữu hạn.

## 5. Ba ca kiểm thử sẽ chứng minh điều gì?

| Ca | Cách dựng tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| Hủy tác vụ đang chạy | Đợi `started`, rồi `cancel(true)` | Future bị hủy, `get()` báo hủy, tác vụ đã quan sát ngắt và thoát |
| Dừng có trật tự | Một việc đang bị giữ, một việc đã xếp hàng, gọi `shutdown()` | Việc mới bị từ chối; việc cũ hoàn thành; executor kết thúc |
| Hết khả năng tiếp nhận và dừng ngay | Một luồng, một ô hàng đợi, thêm việc thứ ba | `AbortPolicy` báo từ chối; `shutdownNow()` trả việc chờ; xử lý Future của việc ấy |

Chọn rõ `AbortPolicy` để việc bị từ chối báo `RejectedExecutionException`. Đây là hành vi của handler đã chọn, không phải mọi chính sách từ chối đều ném ngoại lệ. [API ThreadPoolExecutor.AbortPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html).

## 6. Chương trình Java 17+ chạy đầy đủ

Lưu thành `ExecutorLifecycleDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExecutorLifecycleDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void await(CountDownLatch latch) throws InterruptedException {
        check(latch.await(5, TimeUnit.SECONDS), "Latch timeout");
    }

    static ThreadPoolExecutor pool() {
        return new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1), new ThreadPoolExecutor.AbortPolicy());
    }

    static Callable<Integer> blockedTask(CountDownLatch started,
            CountDownLatch release, CountDownLatch exited, AtomicBoolean interrupted) {
        return () -> {
            started.countDown();
            try {
                release.await();
                return 7;
            } catch (InterruptedException ex) {
                interrupted.set(true);
                throw ex;
            } finally {
                exited.countDown();
            }
        };
    }

    static void cancelPending(List<Runnable> pending) {
        for (Runnable task : pending) {
            if (task instanceof Future<?> future) future.cancel(false);
        }
    }

    static void cleanup(ThreadPoolExecutor executor, CountDownLatch release)
            throws InterruptedException {
        release.countDown();
        cancelPending(executor.shutdownNow());
        check(executor.awaitTermination(5, TimeUnit.SECONDS), "Cleanup timeout");
    }

    static void cancellation() throws Exception {
        ThreadPoolExecutor executor = pool();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        try {
            Future<Integer> future = executor.submit(
                    blockedTask(started, release, exited, interrupted));
            await(started);
            check(future.cancel(true), "Cancellation was not accepted");
            check(future.isCancelled(), "Future not cancelled");
            System.out.println("cancelled=true");
            try {
                future.get(5, TimeUnit.SECONDS);
                throw new AssertionError("Expected cancellation");
            } catch (CancellationException expected) {
                System.out.println("cancelGet=CancellationException");
            }
            await(exited);
            check(interrupted.get(), "Task did not observe interruption");
            System.out.println("taskExited=true");
        } finally {
            cleanup(executor, release);
        }
    }

    static void orderlyShutdown() throws Exception {
        ThreadPoolExecutor executor = pool();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        try {
            Future<Integer> running = executor.submit(
                    blockedTask(started, release, exited, interrupted));
            await(started);
            Future<Integer> queued = executor.submit(() -> 42);
            executor.shutdown();
            check(executor.isShutdown(), "Shutdown not recorded");
            check(!executor.isTerminated(), "Blocked task should still be active");
            try {
                executor.submit(() -> 99);
                throw new AssertionError("Expected shutdown rejection");
            } catch (RejectedExecutionException expected) {
                System.out.println("shutdownReject=true");
            }
            release.countDown();
            check(running.get(5, TimeUnit.SECONDS) == 7, "Running result mismatch");
            check(queued.get(5, TimeUnit.SECONDS) == 42, "Queued result mismatch");
            check(!interrupted.get(), "Orderly shutdown interrupted task");
            System.out.println("queuedResult=42");
            check(executor.awaitTermination(5, TimeUnit.SECONDS), "Orderly timeout");
            System.out.println("orderlyTerminated=true");
        } finally {
            cleanup(executor, release);
        }
    }

    static void rejectionAndShutdownNow() throws Exception {
        ThreadPoolExecutor executor = pool();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        try {
            Future<Integer> running = executor.submit(
                    blockedTask(started, release, exited, interrupted));
            await(started);
            Future<Integer> queued = executor.submit(() -> 99);
            try {
                executor.submit(() -> 100);
                throw new AssertionError("Expected saturation rejection");
            } catch (RejectedExecutionException expected) {
                System.out.println("saturatedReject=true");
            }
            List<Runnable> pending = executor.shutdownNow();
            check(pending.size() == 1, "Unexpected pending count");
            System.out.println("pendingFromShutdownNow=" + pending.size());
            cancelPending(pending);
            check(queued.isCancelled(), "Queued future must be completed by cancellation");
            System.out.println("queuedFutureCancelled=true");
            await(exited);
            check(interrupted.get(), "Running task missed interruption");
            try {
                running.get(5, TimeUnit.SECONDS);
                throw new AssertionError("Expected interrupted task failure");
            } catch (ExecutionException expected) {
                check(expected.getCause() instanceof InterruptedException,
                        "Unexpected task failure");
            }
            check(executor.awaitTermination(5, TimeUnit.SECONDS), "Forced timeout");
            System.out.println("forcedTerminated=true");
        } finally {
            cleanup(executor, release);
        }
    }

    public static void main(String[] args) throws Exception {
        cancellation();
        orderlyShutdown();
        rejectionAndShutdownNow();
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ExecutorLifecycleDemo.java
java ExecutorLifecycleDemo
```

Stdout khi các kiểm tra thành công:

```text
cancelled=true
cancelGet=CancellationException
taskExited=true
shutdownReject=true
queuedResult=42
orderlyTerminated=true
saturatedReject=true
pendingFromShutdownNow=1
queuedFutureCancelled=true
forcedTerminated=true
```

`check()` chủ động ném `AssertionError` khi điều kiện sai, nên không cần cờ `-ea`. Mọi dòng stdout được in trên luồng kiểm thử theo thứ tự; tác vụ nền không tranh nhau in. Chương trình không cần JUnit hoặc thư viện ngoài.

Trong tác vụ nền, `release.await()` được dùng như một cửa chặn có chủ đích. Nó được mở trong dọn dẹp hoặc bị ngắt khi dừng; các lần đợi ở luồng điều khiển đều có giới hạn để phát hiện tình huống không tiến triển.

## 7. Đọc ca hủy: Future hủy và thân tác vụ thoát là hai bằng chứng

Trình tự của `cancellation()` là:

```text
Submit tác vụ
  -> đợi started
  -> yêu cầu cancel(true)
  -> kiểm tra isCancelled và CancellationException
  -> đợi exited
  -> kiểm tra tác vụ đã quan sát InterruptedException
```

Latch `started` loại bỏ lỗi kiểm thử “tưởng đang hủy việc chạy nhưng thực ra việc chưa được khởi chạy”. Dù luồng kiểm thử gửi ngắt ngay trước khi tác vụ đi vào `await()`, thao tác chờ vẫn quan sát trạng thái ngắt và thoát.

Không dùng riêng `future.get()` sau hủy để kết luận thân tác vụ đã chạy xong phần `finally`. Với `FutureTask`, hủy làm trạng thái Future hoàn tất theo nghĩa giao diện, trong khi mã đang chạy vẫn cần cơ hội thoát. Tín hiệu `exited` kiểm tra riêng điều đó. [API FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

Trong một tác vụ thực, đặt tín hiệu “đã dọn xong” sau phần giải phóng tài nguyên mà ca kiểm thử cần chứng minh. Nếu báo tín hiệu trước khi đóng tài nguyên, kiểm thử có thể vượt qua quá sớm.

## 8. Đọc ca shutdown: việc đã nhận vẫn phải được giải quyết

`orderlyShutdown()` giữ việc thứ nhất đang chạy rồi xếp việc thứ hai. Sau `shutdown()`:

- `isShutdown()` phải đúng.
- `isTerminated()` chưa thể đúng vì việc đầu vẫn bị giữ.
- Yêu cầu submit mới bị handler từ chối.
- Khi mở cửa, việc đang chạy trả `7`, việc trong hàng đợi trả `42`.
- `awaitTermination()` thành công xác nhận pool đã kết thúc.

Kiểm tra `interrupted` ở ca này xác nhận dừng có trật tự không ngắt tác vụ của ví dụ. Nếu chỉ kiểm tra việc mới bị từ chối, ca kiểm thử chưa chứng minh những việc cũ được xử lý.

Đừng dùng executor dùng chung của toàn ứng dụng trong một kiểm thử nhỏ rồi gọi shutdown lên nó. Ca kiểm thử phải sở hữu executor mình tạo và chịu trách nhiệm dọn nó, tránh phá phần việc không thuộc phạm vi.

## 9. Đọc ca từ chối: tạo trạng thái bão hòa có kiểm soát

Pool trong bài có một luồng làm việc và hàng đợi dung lượng một. Khi tác vụ đầu bị giữ và việc thứ hai đã vào hàng đợi, không còn luồng mới được tạo hoặc chỗ xếp hàng cho việc thứ ba. Vì vậy, `submit` thứ ba bị `AbortPolicy` từ chối một cách có thể tái lập. Cách xếp hàng và giới hạn luồng phối hợp theo hợp đồng `ThreadPoolExecutor`. [API ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

Không chọn một hàng đợi không giới hạn rồi kỳ vọng kiểm tra bão hòa bằng cách gửi ba tác vụ. Nếu hàng đợi còn nhận được, tình huống từ chối chưa được dựng đúng.

Ngoại lệ từ `submit()` ở đây xuất hiện trên luồng gửi việc, trước khi nhận một Future cho việc bị từ chối. Nó khác ngoại lệ do mã tác vụ ném sau khi đã được nhận; ngoại lệ của tác vụ submit được quan sát qua `Future.get()`.

Nếu ứng dụng dùng handler khác, viết kỳ vọng theo handler ấy. Chẳng hạn, một handler có thể chạy công việc trên luồng gửi hoặc bỏ công việc thay vì báo lỗi. Những lựa chọn đó ảnh hưởng độ trễ, luồng thực thi và cách hoàn tất kết quả; không đổi handler chỉ để một ca kiểm thử “không còn ném lỗi”.

## 10. shutdownNow trả việc chờ không đồng nghĩa mọi Future đã bị hủy

Trong `rejectionAndShutdownNow()`, danh sách trả về có một việc chưa bắt đầu. Với pool và `submit()` mặc định của ví dụ, phần tử là wrapper tác vụ có giao diện `Future`, không nhất thiết chính đối tượng `Callable` ban đầu.

Hàm `cancelPending()` chủ động hủy các phần tử triển khai `Future`. Nhờ đó, người đợi Future của việc không chạy nhận được một trạng thái kết thúc rõ ràng thay vì tiếp tục đợi một kết quả sẽ không được tạo.

Không áp đặt rằng mọi executor hoặc lớp trang trí tác vụ đều trả wrapper giống nhau. Trong hệ thống có wrapper riêng, cần theo dõi liên hệ với Future/đơn vị công việc và có chính sách hoàn tất cho việc bị lấy ra. Danh sách từ `shutdownNow()` là trách nhiệm cần xử lý, không chỉ là một con số để log. [ExecutorService.shutdownNow](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#shutdownNow()).

Với việc đang chạy trong ca này, chương trình không gọi `running.cancel(true)`. Pool ngắt luồng trong quá trình dừng; tác vụ truyền tiếp `InterruptedException`, nên `running.get()` nhận `ExecutionException` với nguyên nhân ấy. Đây là một kết quả khác ca hủy Future trực tiếp, vốn báo `CancellationException`.

`shutdownNow()` không tự hoàn tác tác động bên ngoài của một tác vụ đã bắt đầu. Nếu đã ghi dữ liệu hoặc gọi dịch vụ khác, thiết kế nghiệp vụ cần xử lý trạng thái đó riêng.

## 11. Phân biệt các lỗi khi kiểm thử

| Kết quả/ngoại lệ | Điều nó biểu thị trong ngữ cảnh này |
| --- | --- |
| `RejectedExecutionException` | Executor/handler từ chối nhận việc |
| `CancellationException` | Future được quan sát đã bị hủy |
| `ExecutionException` | Tác vụ đã được nhận nhưng kết thúc bằng lỗi; xem `getCause()` |
| `InterruptedException` khi luồng kiểm thử đang đợi | Chính luồng đang chờ bị ngắt |
| `TimeoutException` từ `Future.get(timeout, unit)` | Chờ kết quả quá hạn, không tự chứng minh tác vụ đã bị hủy |
| `awaitTermination(...) == false` | Executor chưa kết thúc trong thời gian chờ |

Timeout của `get()` chỉ kết thúc lần chờ ấy. Nếu chính sách yêu cầu hủy công việc sau timeout, phải gửi yêu cầu hủy riêng và quan sát kết thúc theo hợp đồng. Không bắt `TimeoutException` rồi cho rằng tài nguyên của tác vụ đã được trả lại. [API Future.get](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

Khi kỳ vọng một loại lỗi, kiểm tra đúng loại và nguyên nhân cần thiết. Đừng bắt `Exception` quá rộng rồi in “PASS”, vì một lỗi khởi tạo hoặc lỗi lập trình cũng có thể làm ca ấy vượt qua sai.

## 12. Dọn tài nguyên và giới hạn của ví dụ

Mỗi ca có `finally` gọi `cleanup()` để mở cửa chặn, yêu cầu dừng pool, xử lý việc còn chờ và kiểm tra kết thúc. Mục đích là không để lỗi kiểm thử tạo ra luồng nền sống vô hạn.

Tác vụ của bài hợp tác với ngắt hoặc cửa mở; không dùng một vòng lặp vô hạn cố tình phớt lờ mọi tín hiệu. Kiểm thử một tác vụ không hợp tác cần có chiến lược cô lập và thời hạn ở mức phù hợp, vì một lỗi “không dừng được” có thể giữ cả JVM kiểm thử sống.

Không tăng timeout vô hạn để che lỗi điều phối. Ngược lại, timeout quá ngắn có thể chỉ phản ánh máy thử bị chậm. Latch xác định thứ tự cần thiết; timeout là giới hạn thất bại, không phải cách tạo thứ tự.

Ví dụ dùng quản lý shutdown tường minh để tương thích Java 17. Không thay nó bằng API mới hơn rồi vẫn giữ hướng dẫn biên dịch `--release 17` mà không kiểm tra mức hỗ trợ.

## 13. Bài tập mở rộng và bằng chứng cần giữ

1. **Hủy việc chưa chạy:** giữ tác vụ đầu, xếp tác vụ thứ hai có tín hiệu riêng nếu thân được gọi; hủy Future thứ hai trước khi mở cửa. Xác nhận Future bị hủy và thân việc ấy không thực hiện.
2. **Hủy không yêu cầu ngắt:** chạy một tác vụ có cửa điều khiển, gọi `cancel(false)`, rồi mở cửa để nó thoát. Quan sát riêng trạng thái Future và việc không nhận yêu cầu ngắt từ thao tác hủy.
3. **Timeout khi đợi kết quả:** giữ một tác vụ chưa xong, dùng `get` có giới hạn, quan sát timeout rồi thực hiện bước hủy/dọn riêng. Không dùng việc timeout như bằng chứng tác vụ đã dừng.
4. **Tác vụ lỗi độc lập:** submit một `Callable` ném lỗi đã định nghĩa và kiểm tra `ExecutionException.getCause()`, phân biệt với từ chối việc.
5. **Dừng hai giai đoạn:** cho thời gian hoàn thành bình thường bằng `shutdown()`, rồi chuyển sang `shutdownNow()` khi hết hạn; xác định cách hoàn tất các việc chờ bị trả về.

Một báo cáo kiểm thử tốt nên chỉ ra trạng thái đã dựng, tín hiệu đồng bộ đã quan sát, kết quả Future, tín hiệu thân tác vụ thoát và trạng thái executor cuối. Những dữ kiện ấy giúp phân biệt “đã gửi yêu cầu hủy” với “đã dừng và dọn xong” một cách có thể kiểm chứng.
