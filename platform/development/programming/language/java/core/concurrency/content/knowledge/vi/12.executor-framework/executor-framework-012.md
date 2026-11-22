# Lifecycle: đóng Executor và tránh thread leak trong Java

## 1. Vì sao Executor cần một vòng đời rõ ràng?

`ExecutorService` cho phép nộp các `Runnable` hoặc `Callable` để một nhóm worker thread thực thi. Tạo một executor là **tạo ra một tài nguyên có vòng đời**, không đơn thuần gọi một method để chạy code.

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
executor.submit(() -> performTask());
```

Đây là **mã minh họa**, cần import `java.util.concurrent.*` và định nghĩa `performTask()`. Nếu không bao giờ đóng executor, các worker có thể tiếp tục tồn tại và tiêu tốn thread/stack/tài nguyên; chương trình Java có thể không kết thúc nếu còn các platform thread non-daemon sống. Nếu ứng dụng tạo executor mới theo từng yêu cầu rồi không đóng, số lượng thread có thể tăng không kiểm soát.

**Thread leak** trong ngữ cảnh này không nhất thiết là một vùng nhớ không còn tham chiếu mà GC không thu hồi. Nó thường là tình trạng **thread tiếp tục tồn tại hoặc tài nguyên gắn với thread không được giải phóng dù công việc logic đã kết thúc**. Các nguyên nhân phổ biến:

- Tạo `ExecutorService` mới nhiều lần nhưng không `shutdown()`.
- Worker bị kẹt ở `BlockingQueue.take()`, `Future.get()`, `Lock.lock()` hoặc I/O không có cơ chế đánh thức/hủy.
- Task có vòng lặp vô hạn không phản ứng `interrupt()`.
- Tạo quá nhiều pool với số worker cố định, tổng thread vượt khả năng hệ thống.
- Quên dọn `ThreadLocal` trong pooled worker, khiến dữ liệu gắn với thread tồn tại xuyên nhiều task.
- Task chặn lẫn nhau, deadlock hoặc giữ lock trong lúc chờ công việc khác cùng pool.
- Scheduled task hoặc cơ chế producer tiếp tục nộp việc sau khi một thành phần đáng lẽ đã đóng.

Đích đến của bài là một contract có thể kiểm chứng:

> **Ai tạo executor thì phải xác định rõ ai sở hữu, ai được nộp việc, khi nào ngừng nhận, task còn chạy được xử lý thế nào, và làm sao xác nhận executor đã terminated.**

Bài này thuộc **Executor Framework** của **Java concurrency nói chung**, không phụ thuộc framework.

## 2. Lifecycle gồm những pha nào?

Một executor không chỉ có hai trạng thái “đang chạy” và “đã đóng”. Mô hình sử dụng thường là:

```text
       tạo ExecutorService
               |
               v
        RUNNING / ACCEPTING
        - nhận execute/submit
        - worker chạy và lấy task từ queue
               |
          shutdown()
               |
               v
        SHUTDOWN / DRAINING
        - không nhận tác vụ mới
        - những task đã nhận vẫn được phép hoàn tất
               |
        worker và queue kết thúc
               |
               v
          TERMINATED
        - không còn worker thực thi task
        - awaitTermination có thể trả true
```

Một nhánh khác là:

```text
RUNNING hoặc SHUTDOWN
      |
 shutdownNow()
      |
 yêu cầu dừng ngay / interrupt worker
 lấy pending tasks chưa bắt đầu
      |
 nếu task hợp tác và worker kết thúc
      v
  TERMINATED
```

Với `ThreadPoolExecutor`, JVM có các trạng thái thực thi nội bộ chi tiết hơn, nhưng không nên viết code dựa trên chi tiết implementation. API public cho ta các điểm quan sát:

- `isShutdown()`: executor đã nhận yêu cầu đóng; **không** có nghĩa worker đã xong.
- `isTerminated()`: executor đã kết thúc sau shutdown.
- `awaitTermination(timeout, unit)`: đợi trạng thái terminated hoặc timeout/interrupt.
- `shutdown()`: đóng có trật tự, không chặn caller đợi hoàn tất.
- `shutdownNow()`: cố gắng dừng/cancel, nhưng không phải lệnh cưỡng bức kill thread.

Nếu chỉ gọi `shutdown()` rồi trả về, bạn mới **bắt đầu** lifecycle shutdown. Nếu cần xác nhận cleanup, phải đợi và xử lý trường hợp đợi thất bại.

## 3. Phân biệt shutdown, termination và task completion

Ba khái niệm này không tương đương:

| Sự kiện | Ý nghĩa | Chưa chứng minh điều gì? |
| --- | --- | --- |
| `shutdown()` đã được gọi | Executor từ chối công việc mới; công việc đã nhận có thể tiếp tục | Không chứng minh task đã xong |
| `isShutdown() == true` | Lifecycle đã bước vào shutdown | Không chứng minh worker đã kết thúc |
| `isTerminated() == true` | Executor đã kết thúc các worker theo hợp đồng | Không chứng minh mọi task thành công về nghiệp vụ |
| `awaitTermination(...) == true` | Executor đã terminated trong thời gian đợi | Không trả kết quả hoặc exception từng task |
| `Future.get()` trả thành công | Task tương ứng trả kết quả; có quan hệ bộ nhớ khi nhận kết quả | Không chứng minh các task khác đã hoàn tất |
| `Future.cancel(true)` thành công | Future chuyển sang trạng thái canceled và yêu cầu interrupt nếu thích hợp | Không chứng minh worker đã cleanup xong |

Ví dụ một `Callable` có thể ném exception. Worker vẫn kết thúc, executor vẫn terminated; nhưng business outcome là **FAILED**. Vì vậy, với bài toán cần bảo đảm kết quả, phải giữ `Future`, chờ `get()` hoặc có cơ chế báo lỗi riêng. **Chờ cả pool dừng** và **đọc outcome task** là hai phép kiểm tra khác nhau.

## 4. `shutdown()`: đóng có trật tự

Gọi:

```java
executor.shutdown();
```

sẽ ngăn nhận task mới và cho những task đã được nhận vào executor tiếp tục được xử lý theo hợp đồng. Nó **không chờ** các task đã nộp hoàn thành trước khi trả về.

Những tác vụ bị nộp sau khi shutdown thường bị từ chối thông qua `RejectedExecutionException` khi dùng các executor tiêu chuẩn với rejection policy mặc định. Nếu ứng dụng cấu hình `ThreadPoolExecutor` với một `RejectedExecutionHandler` khác, hành vi có thể khác; không giả định mọi handler đều ném exception.

### Ví dụ 1: graceful shutdown với kết quả xác định

Tạo tệp `GracefulLifecycleDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class GracefulLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Future<Integer> first = executor.submit(() -> {
            bothStarted.countDown();
            release.await();
            return 10;
        });
        Future<Integer> second = executor.submit(() -> {
            bothStarted.countDown();
            release.await();
            return 20;
        });

        bothStarted.await(); // Cả hai task đang đợi release.
        executor.shutdown();

        System.out.println("shutdown=" + executor.isShutdown());
        System.out.println("terminated before release="
                + executor.isTerminated());

        release.countDown();
        boolean stopped = executor.awaitTermination(
                10, TimeUnit.SECONDS);

        System.out.println("terminated=" + stopped);
        System.out.println("sum=" + (first.get() + second.get()));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac GracefulLifecycleDemo.java
java GracefulLifecycleDemo
```

Kết quả khi worker được lập lịch hoàn thành trong thời hạn mười giây:

```text
shutdown=true
terminated before release=false
terminated=true
sum=30
```

**Vì sao kết quả đáng tin:**

1. Main đợi `bothStarted` trước khi shutdown. Hai worker đã vào task và đang chờ `release`.
2. `shutdown()` cấm submit mới, nhưng không interrupt các task này.
3. Vì chưa mở `release`, các task chưa thể hoàn tất; `isTerminated()` tại thời điểm đó là `false`.
4. Main mở latch, các task trả kết quả `10` và `20`.
5. `awaitTermination` chờ executor dừng; `Future.get()` xác nhận kết quả từng task và cung cấp bảo đảm bộ nhớ khi đọc outcome.

Time budget là minh họa: trong môi trường bị trì hoãn bất thường, `awaitTermination` vẫn có thể trả `false`. Code production phải kiểm tra nhánh đó thay vì mặc định mọi executor chắc chắn dừng trong mười giây.

### Lưu ý khi dùng Future

`Future.get()` có thể ném `ExecutionException` khi task thất bại, `InterruptedException` nếu caller bị ngắt, hoặc `CancellationException` nếu task bị hủy. Đừng chỉ gọi `awaitTermination` rồi xem mọi tác vụ đều thành công.

## 5. `shutdownNow()` không phải kill -9 cho Java thread

Gọi:

```java
List<Runnable> notStarted = executor.shutdownNow();
```

yêu cầu executor:

1. Dừng nhận task mới.
2. Cố dừng những task đang chạy (thường bằng `Thread.interrupt()`).
3. Không tiếp tục bắt đầu thực thi những task còn ở queue.
4. Trả về danh sách các `Runnable` chưa bắt đầu được trả lại theo hợp đồng.

**Điểm then chốt:** interrupt là **tín hiệu hợp tác**. Nếu một task không kiểm tra interrupt, không gọi API chờ interruptible và tiếp tục vòng lặp CPU, `shutdownNow()` không cưỡng chế nó kết thúc. Các tác vụ đang chạy cũng **không nằm hết** trong danh sách pending được trả về.

Với `submit(Callable)`, executor thường bọc task bằng một `RunnableFuture`, nên phần tử trong danh sách pending có thể **không phải object ban đầu** caller nộp. Muốn retry, phải kiểm tra tính hợp lệ, idempotency và tránh xử lý lặp.

### Ví dụ 2: phân biệt task đang chạy và task chưa bắt đầu

Tạo tệp `ShutdownNowLifecycleDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownNowLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1));

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);

        executor.execute(() -> {
            started.countDown();
            try {
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            } finally {
                exited.countDown();
            }
        });

        started.await(); // Worker duy nhất đang chờ không thời hạn.
        executor.execute(() ->
                System.out.println("pending should not run"));

        List<Runnable> pending = executor.shutdownNow();
        exited.await();

        boolean terminated = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("pending=" + pending.size());
        System.out.println("saw interrupt=" + interrupted.get());
        System.out.println("terminated=" + terminated);
    }
}
```

```bash
javac ShutdownNowLifecycleDemo.java
java ShutdownNowLifecycleDemo
```

Kết quả khi không có interrupt bất thường dành cho main và executor dừng trong thời hạn:

```text
pending=1
saw interrupt=true
terminated=true
```

Giải thích: pool có **một** worker, task đầu đã chạy và đợi ở latch không mở. Task thứ hai vào queue capacity 1, không thể bắt đầu. `shutdownNow()` cố interrupt task đầu; `await()` phản hồi bằng `InterruptedException` và task thoát. Task thứ hai được trả về dưới dạng pending. `exited.await()` giúp main đợi nhánh cleanup của task đầu trước khi in.

Chương trình dùng latch không bao giờ mở chỉ để **mô phỏng task bị chặn**. Không nên dùng cấu trúc chờ vô thời hạn như vậy trong sản xuất nếu không có đường timeout, cancel hoặc tín hiệu dừng rõ.

## 6. `awaitTermination()`: xác nhận đã kết thúc thật hay chưa

Chữ ký:

```java
boolean awaitTermination(long timeout, TimeUnit unit)
        throws InterruptedException;
```

Đây là phần chữ ký API rút gọn. `awaitTermination`:

- **Trả `true`** nếu executor đã terminated trước khi hoặc trong lúc đợi.
- **Trả `false`** nếu đến hạn mà executor vẫn chưa terminated.
- **Ném `InterruptedException`** nếu thread đang chờ bị interrupt.

Nó **không tự gọi `shutdown()`**. Nếu executor còn RUNNING và không có thread khác đóng nó, `awaitTermination` có thể chỉ chờ hết timeout rồi trả `false`.

Chờ có giới hạn phải luôn có nhánh xử lý `false`. Đừng coi việc log “shutdown requested” như bằng chứng worker đã dọn dẹp xong.

### Ví dụ 3: timeout trước, thành công sau

Tạo tệp `TerminationTimeoutDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TerminationTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        executor.execute(() -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        started.await();
        executor.shutdown();

        boolean before = executor.awaitTermination(
                50, TimeUnit.MILLISECONDS);
        System.out.println("before release=" + before);

        release.countDown();
        boolean after = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("after release=" + after);
    }
}
```

```bash
javac TerminationTimeoutDemo.java
java TerminationTimeoutDemo
```

Kết quả khi không bị interrupt từ ngoài và worker được lên lịch kết thúc trong thời hạn sau:

```text
before release=false
after release=true
```

Task chưa được mở latch ở lần chờ đầu, nên executor chắc chắn chưa terminated tại thời điểm đó. Sau khi main mở `release`, worker có thể kết thúc và executor đi tới terminated. Nếu tài nguyên có yêu cầu thời hạn nghiêm ngặt, code phải kiểm tra `after` và có fallback hợp lý.

## 7. Mẫu đóng hai giai đoạn được khuyến khích

Quy trình thường dùng cho pool do chính ứng dụng sở hữu:

1. `shutdown()` để ngừng nhận công việc mới và ưu tiên graceful completion.
2. `awaitTermination(graceTimeout)` để chờ có giới hạn.
3. Nếu chưa dừng, gọi `shutdownNow()` để yêu cầu cancellation.
4. `awaitTermination(forceTimeout)` thêm một lần để xác nhận worker thực sự đã thoát.
5. Nếu vẫn chưa dừng, **báo lỗi shutdown không hoàn tất**; không tuyên bố thành công.
6. Nếu caller bị interrupt khi chờ, `shutdownNow()` rồi khôi phục cờ interrupt hoặc truyền exception theo hợp đồng.

Một helper Java 17+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class ExecutorStopper {
    private ExecutorStopper() {}

    public static boolean stop(ExecutorService executor) {
        executor.shutdown();
        try {
            if (executor.awaitTermination(5, TimeUnit.SECONDS)) {
                return true;
            }
            executor.shutdownNow();
            return executor.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            return false;
        }
    }
}
```

Lớp này **biên dịch được nhưng không có `main`**; đặt trong `ExecutorStopper.java` và dùng từ code sở hữu executor. Hai timeout `5` giây chỉ là ví dụ. Helper trả `false` nếu không thể xác nhận termination hoặc caller bị interrupt. Trong hệ thống thật, caller còn nên biết danh sách pending từ `shutdownNow()` nếu các job đó cần retry/persist.

**Không nhầm shutdownNow với “force stop”:** nếu task không hợp tác, bước thứ hai vẫn có thể timeout. Không dùng `Thread.stop()` để cưỡng chế cắt ngang worker đang giữ khóa; API đó không an toàn.

## 8. Ownership: ai tạo thì ai đóng?

Đây là nguyên tắc phòng thread leak mạnh nhất:

- Một thành phần **tạo executor** cần có trách nhiệm quản lý lifecycle của nó.
- Thành phần **mượn executor** từ bên ngoài không nên tự ý gọi `shutdown()` lên tài nguyên dùng chung trừ khi hợp đồng cho phép.
- Tạo pool riêng cho mỗi request rất dễ gây quá nhiều thread và khó đóng đúng thời điểm.
- Executor dùng chung nhiều tác vụ thường sống theo vòng đời của service/application, không phải từng lời gọi.
- Nếu một method tạo pool tạm thời cho tác vụ cục bộ, phải có đường `finally` đóng pool ngay cả khi tính toán ném exception.

Ví dụ sở hữu đúng:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    submitKnownTasks(executor);
    collectResults();
} finally {
    stopExecutor(executor);
}
```

Đây là **pseudocode Java minh họa**, các phương thức do ứng dụng định nghĩa; `stopExecutor` triển khai shutdown hai giai đoạn. Nếu `collectResults` ném exception, `finally` vẫn kích hoạt dọn tài nguyên. Tuy nhiên, `finally` không có nghĩa việc dừng chắc chắn thành công: helper phải báo tình trạng khi không thể terminate.

Ví dụ quyền sở hữu sai:

```java
void handleRequest() {
    ExecutorService executor = Executors.newFixedThreadPool(8);
    executor.submit(this::process);
    // Không giữ handle để shutdown.
}
```

Đây là đoạn minh họa. Nếu gọi nhiều lần, số pool và worker có thể tăng lên. GC không phải cơ chế lifecycle đáng tin để đóng executor. Phải quy định một owner quản lý số lượng, thời điểm dừng và các tác vụ đang chờ.

### Trường hợp caller chỉ được gửi việc

Một API tốt có thể chỉ đưa `Executor` thay vì toàn `ExecutorService` cho thành phần cần gọi `execute`. `Executor` không công bố phương thức `shutdown`, giúp tránh caller tùy tiện đóng pool của thành phần khác. Đây không phải ranh giới bảo mật tuyệt đối; nó là một cách **diễn đạt ownership trong thiết kế API**.

## 9. Vì sao pooled thread khác Thread tạo theo từng task?

Với `new Thread(task).start()`, một thread thường kết thúc khi `run()` trả về. Với thread pool, worker có thể tiếp tục sống sau khi một task kết thúc để lấy task mới. Điều đó giúp tái sử dụng thread, nhưng nếu không shutdown, thread có thể chờ công việc mới lâu dài.

`Executors.newFixedThreadPool(n)` tạo pool có khả năng duy trì số worker khi có công việc, thường sử dụng một queue không giới hạn thực tế theo nhu cầu nộp task. Nếu task producer nhanh hơn consumer, backlog có thể tăng đáng kể — **không phải thread leak nhưng vẫn là resource leak/bùng bộ nhớ tiềm tàng**.

`Executors.newCachedThreadPool()` có thể tạo nhiều worker khi lượng công việc tăng, và giữ worker nhàn rỗi một khoảng thời gian trước khi thu hồi. Nó không có nghĩa số worker luôn bị giới hạn thấp. Nếu request đến nhanh và task chặn lâu, số thread có thể tăng rất lớn.

`Executors.newSingleThreadExecutor()` thường giữ worker để tái sử dụng, nên quên shutdown một single-thread executor trong mỗi request vẫn có thể tạo nhiều thread chờ.

### Đừng dùng daemon thread để che việc thiếu shutdown

Một custom `ThreadFactory` có thể tạo daemon thread, nhưng daemon thread **không phải giải pháp dọn dẹp tài nguyên**. JVM có thể thoát khi chỉ còn daemon thread mà không đợi những task đó hoàn tất hoặc flush dữ liệu. Điều cần làm là **quản lý lifecycle và hoàn thành/hủy có kiểm soát**.

Một `ThreadFactory` đặt tên thread rõ ràng rất hữu ích khi chẩn đoán:

```java
ThreadFactory factory = runnable -> {
    Thread thread = new Thread(runnable);
    thread.setName("order-worker-" + thread.getId());
    return thread;
};
ExecutorService executor = Executors.newFixedThreadPool(4, factory);
```

Đoạn này cần import `ExecutorService`, `Executors`, `ThreadFactory`. Thread được tạo theo tên dễ nhận diện trong thread dump. Khi ứng dụng dùng nhiều pool, có thể kết hợp số pool/worker để tránh tên trùng. Không nên cấu hình daemon tùy tiện chỉ để làm process thoát.

## 10. Task không hợp tác interrupt có thể ngăn termination

`shutdownNow()` thông thường gọi interrupt các worker, nhưng `Thread.interrupt()` là **yêu cầu hợp tác**. Task CPU-bound không kiểm tra cờ hoặc task kẹt trong I/O không hỗ trợ interrupt có thể tiếp tục chạy.

Tạo tệp `InterruptIgnoringTaskDemo.java` để minh họa một task cố tình không quan tâm interrupt, nhưng có **cờ dừng riêng** cho phép chương trình hoàn tất:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptIgnoringTaskDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean running = new AtomicBoolean(true);
        CountDownLatch started = new CountDownLatch(1);

        executor.execute(() -> {
            started.countDown();
            while (running.get()) {
                Thread.onSpinWait(); // Cố tình bỏ qua interrupt.
            }
        });

        started.await();
        executor.shutdownNow();

        boolean before = executor.awaitTermination(
                50, TimeUnit.MILLISECONDS);
        System.out.println("terminated while ignoring interrupt=" + before);

        running.set(false);
        boolean after = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("terminated after stop signal=" + after);
    }
}
```

```bash
javac InterruptIgnoringTaskDemo.java
java InterruptIgnoringTaskDemo
```

Kết quả khi task thoát và worker được lập lịch trong thời hạn thứ hai:

```text
terminated while ignoring interrupt=false
terminated after stop signal=true
```

Task không đọc interrupt, nên `shutdownNow()` không làm nó thoát. Phải đặt `running=false`, lúc đó vòng lặp mới kết thúc. `Thread.onSpinWait()` chỉ là gợi ý tối ưu cho spin loop, **không phải cơ chế cancel hay chờ tài nguyên**. Ví dụ chủ đích chứng minh giới hạn của shutdownNow; không tạo busy-loop tương tự trong code thật.

## 11. Task hợp tác với interrupt như thế nào?

Hai trường hợp cơ bản:

**Task đang chờ bằng API interruptible:**

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        process(job);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} finally {
    cleanup();
}
```

Đây là đoạn minh họa, `Job`, `queue`, `process`, `cleanup` là code của ứng dụng. `BlockingQueue.take()` có thể ném `InterruptedException` khi worker bị ngắt. Thread cần rời task hoặc propagate thay vì bắt exception rồi tiếp tục chờ vô hạn.

**Task CPU-bound hoặc chia batch:**

```java
for (Job job : jobs) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    processSafely(job);
}
```

Đây là đoạn minh họa. Phản hồi hủy ở **điểm nhất quán**: nếu xử lý một job có nhiều bước, cần hoàn thành/rollback một đơn vị trạng thái để không để lại invariant sai. Interrupt không tự rollback các thay đổi đã thực hiện.

Đừng mặc định `Thread.sleep()` trong vùng `synchronized` sẽ nhả monitor; sleep **không nhả lock**. Task giữ lock rồi ngủ chờ thành phần khác cũng cần lock có thể gây kẹt. Khi shutdown, cần xem cả lock ownership và các phương thức chờ.

### InterruptedException và cờ interrupted

Nhiều API chờ ném `InterruptedException` và thường xóa cờ interrupt của thread trước khi ném. Nếu method không thể truyền tiếp checked exception (như `Runnable.run()`), cách thông dụng là **khôi phục cờ** bằng `Thread.currentThread().interrupt()` và kết thúc công việc.

`Thread.currentThread().isInterrupted()` chỉ đọc trạng thái, **không xóa cờ**. `Thread.interrupted()` là static method đọc và **xóa cờ hiện tại**. Không vô ý tiêu thụ tín hiệu ngắt rồi lặp lại vô hạn.

## 12. `Future.cancel(true)` khác shutdown toàn executor

Nếu một task riêng không còn cần, `Future.cancel(true)` có thể gửi yêu cầu interrupt tới task tương ứng mà không đóng cả pool. Ngược lại:

- `shutdown()`: đóng admission của **toàn executor**, không chủ động hủy các task đã nhận.
- `shutdownNow()`: yêu cầu dừng **toàn executor** và trả về pending tasks.
- `Future.cancel(true)`: nỗ lực hủy **một task** theo contract Future/executor.

Một `Future` bị đánh dấu cancelled **chưa chứng minh cleanup của worker đã hoàn tất**. Nếu thread đang chạy bị cancel, Future có thể chuyển trạng thái trước khi code `finally` của task chạy xong; `Future.get()` có thể ném `CancellationException` mà không chờ riêng bước cleanup.

Vì vậy, nếu lifecycle của tài nguyên yêu cầu biết cleanup đã xong, có thể dùng `CountDownLatch` trong `finally`, tín hiệu trạng thái hoặc chờ executor termination. Đừng chỉ dựa vào `isCancelled()` để đóng tài nguyên mà task có thể còn dùng.

### Pending tasks sau shutdownNow

`List<Runnable>` trả từ `shutdownNow()` không phải danh sách tất cả công việc thất bại; nó là các tác vụ chưa bắt đầu được executor trả về. Nó có thể chứa wrapper `FutureTask` khi công việc được nộp bằng `submit`. Nếu cần retry, phải xét các task có thể đã bắt đầu, idempotency, deduplication và yêu cầu lưu bền vững. Một pool trong RAM **không thay durable job queue**.

## 13. Tránh thread leak bằng cleanup trong từng task

Một worker của thread pool có thể chạy **nhiều task liên tiếp trên cùng thread**. Vì vậy dữ liệu dạng `ThreadLocal` có thể tồn tại sau khi task kết thúc và xuất hiện trong task tiếp theo nếu không được xóa.

Ví dụ nguy cơ:

```java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

void process(String id) {
    REQUEST_ID.set(id);
    // Nếu quên remove(), thread worker có thể mang id cũ sang task khác.
}
```

Đây là đoạn minh họa. Không chỉ là sai dữ liệu: nếu `ThreadLocal` trỏ tới object lớn, session hoặc resource, pooled worker tồn tại lâu có thể giữ object đó lâu hơn mong muốn, gây **memory retention**.

Dùng `try/finally`:

```java
REQUEST_ID.set(id);
try {
    processRequest();
} finally {
    REQUEST_ID.remove();
}
```

### Ví dụ 4: xác nhận ThreadLocal được dọn

Tạo tệp `ThreadLocalCleanupDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        Future<?> first = executor.submit(() -> {
            CONTEXT.set("request-123");
            try {
                System.out.println("first=" + CONTEXT.get());
            } finally {
                CONTEXT.remove();
            }
        });
        first.get();

        Future<?> second = executor.submit(() ->
                System.out.println("second=" + CONTEXT.get()));
        second.get();

        executor.shutdown();
        boolean terminated = executor.awaitTermination(
                10, TimeUnit.SECONDS);
        System.out.println("terminated=" + terminated);
    }
}
```

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

Kết quả nếu executor kết thúc trong thời hạn:

```text
first=request-123
second=null
terminated=true
```

`newSingleThreadExecutor` chạy task theo thứ tự, tái sử dụng worker để cho thấy context đã được remove; `Future.get()` của task thứ nhất hoàn thành trước khi nộp task thứ hai. Nếu quên `CONTEXT.remove()`, task thứ hai có thể thấy `request-123` thay vì `null`. Điều này có thể rò rỉ thông tin giữa requests.

**Phạm vi:** `ThreadLocal.remove()` dọn phần context do task thiết lập; không thay thế việc đóng socket, stream, connection hoặc executor. Với resource trong task, vẫn cần `try-with-resources`/`finally` tương ứng.

## 14. Shutdown an toàn với exception và try/finally

Một số path thường bỏ sót cleanup:

- Constructor/khởi tạo pool thành công nhưng code sau đó ném exception trước khi gọi `shutdown()`.
- Caller return sớm, hoặc bị cancel khi đang chờ `Future.get()`.
- Lệnh shutdown nằm sau một thao tác có thể ném unchecked exception.
- Worker kết thúc task nhưng quên `close()` resource đã mở.

Mẫu sở hữu tài nguyên:

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    runWorkflow(executor);
} finally {
    boolean stopped = ExecutorStopper.stop(executor);
    if (!stopped) {
        System.err.println("executor still not confirmed terminated");
    }
}
```

Đây là đoạn minh họa dùng helper `ExecutorStopper` ở mục 7 và hàm `runWorkflow` do ứng dụng định nghĩa. `finally` chạy khi rời scope bình thường hoặc bởi exception; nhưng không có phép màu ép thread không hợp tác phải thoát. Chỉ nên coi cleanup thành công khi có tín hiệu terminated.

### Không vô tình ghi đè exception ban đầu

Nếu code cleanup trong `finally` tự ném exception, nó có thể che mất exception chính đã khiến workflow thất bại. Trong code production, cần quyết định cách ghi nhận lỗi shutdown (log, suppressed exception, kết quả tổng hợp) mà không làm mất nguyên nhân gốc. `try-with-resources` có cơ chế suppressed exceptions cho tài nguyên `AutoCloseable`, nhưng trên **JDK 17** việc sở hữu `ExecutorService` thông thường được quản lý bằng shutdown rõ ràng như các ví dụ ở đây.

### Về `ExecutorService.close()` trên JDK mới

Ở các JDK mới hơn, `ExecutorService` có thể được dùng dưới dạng `AutoCloseable` nhờ phương thức `close()` được bổ sung cho giao diện (từ Java 19). Không suy diễn rằng mẫu `try (var executor = ...)` sẽ biên dịch nguyên trạng với **JDK 17**. `close()` trong JDK mới có ngữ nghĩa đóng/đợi riêng; khi yêu cầu deadline và chính sách hủy cụ thể, vẫn phải hiểu hợp đồng API và quản lý interruption/timeout có chủ đích.

## 15. Thread leak và resource leak khác nhau thế nào?

Một số khái niệm gần nhau cần phân biệt:

| Hiện tượng | Dấu hiệu | Nguyên nhân thường gặp |
| --- | --- | --- |
| **Thread leak** | Số thread sống tăng, nhiều worker chờ mãi, JVM không thoát | Tạo pool không shutdown, task bị treo |
| **Thread retention có chủ đích** | Worker thread sống dù chưa có task | Pool được chủ sở hữu giữ để tái sử dụng; không nhất thiết là leak |
| **Queue backlog** | Queue dài, heap tăng, response chậm | Producer nhanh hơn consumer, queue không bị giới hạn |
| **ThreadLocal memory retention** | Heap giữ object theo vòng đời worker | Không gọi `ThreadLocal.remove()` |
| **Resource leak trong task** | Connection/file descriptor không trả lại | Thiếu try-with-resources/finally |
| **Deadlock hoặc starvation** | Worker sống nhưng không tiến triển | Lấy khóa sai thứ tự, tự chờ Future trong pool quá nhỏ |
| **Shutdown chưa hoàn tất** | `isShutdown()==true`, `isTerminated()==false` lâu dài | Task không hợp tác hủy, blocked I/O, vòng chờ |

**Không phải mọi thread đang chờ đều là leak.** Một pool sống suốt lifecycle của dịch vụ có thể hợp lệ. Vấn đề là sự khác biệt giữa **số thread và tài nguyên mà thiết kế dự kiến** với **số thread/resource còn giữ khi owner không còn cần chúng**.

Một worker chờ queue vì sẵn sàng xử lý thêm task là bình thường khi ứng dụng còn RUNNING. Nó trở thành dấu hiệu lỗi nếu thành phần sở hữu đã “đóng” logic nhưng quên dừng executor.

## 16. Khóa và chờ Future có thể làm pool tự kẹt

Một lỗi không hẳn do quên shutdown là **thread-starvation deadlock**: mọi worker trong pool đều chờ một task khác **cũng được nộp vào chính pool đó**, nhưng không còn worker rảnh để thực thi task mới.

Ví dụ ý tưởng (không nên chạy để tạo kẹt):

```java
ExecutorService pool = Executors.newSingleThreadExecutor();

pool.submit(() -> {
    Future<Integer> child = pool.submit(() -> 42);
    return child.get(); // Worker duy nhất đợi child chưa thể chạy.
});
```

Đây là mã minh họa, cần import các lớp executor/Future và xử lý checked exception trong lambda theo kiểu `Callable`. Worker duy nhất đang đợi `child.get()`; child chờ đến lượt được chạy bởi worker đó. `shutdown()` không tự giải quyết vòng chờ; `shutdownNow()` có thể gửi interrupt tới worker, nhưng cần task hợp tác và code xử lý lỗi.

Một deadlock monitor cũng có thể làm termination không đến. Khi debug, hãy xét **thread dump**, stack trace, số worker, queue và phụ thuộc giữa Future/task/lock.

Biện pháp phòng tránh gồm: tránh một task block chờ task con trong cùng pool không đủ worker, tách workload blocking/CPU khi phù hợp, dùng tổ chức task không tạo vòng phụ thuộc, và thiết kế timeout/cancel thay vì đợi vô hạn.

## 17. Monitoring: biết pool thực sự có leak hay chỉ đang bận

Khi cần chẩn đoán `ThreadPoolExecutor`, có thể quan sát các chỉ số như:

- `getPoolSize()`: số worker hiện tại trong pool.
- `getActiveCount()`: số worker **ước tính** đang thực thi task.
- `getQueue().size()`: backlog hiện tại của queue (snapshot, có thể đổi ngay).
- `getCompletedTaskCount()`: số task đã hoàn tất theo thống kê của executor.
- `getLargestPoolSize()`: mức pool size cao nhất ghi nhận.
- `isShutdown()`, `isTerminated()`: mốc lifecycle.

Các giá trị này **không phải transaction snapshot nhiều trường**. Một lần đọc từng metric có thể từ các thời điểm khác nhau, nên dùng để quan sát xu hướng, không làm điều kiện quyết định tính đúng đắn của workflow.

### Công cụ JVM hỗ trợ

- `jcmd <pid> Thread.print`: lấy thread dump để xem worker đang RUNNABLE, WAITING, TIMED_WAITING hay BLOCKED ở đâu.
- Java Flight Recorder (JFR): ghi nhận thread, blocking, allocation và những sự kiện liên quan khi cần.
- `jstack` hoặc công cụ tương đương: hỗ trợ phân tích thread dump trên môi trường phù hợp.
- `ThreadMXBean`: quan sát thread count, deadlock detection và thông tin JVM thread.

Đây là **các công cụ chẩn đoán**, không phải phần code chạy của bài. Tên thread rõ ràng từ `ThreadFactory` giúp nhận biết pool nào chưa dừng. Số thread theo thời gian, trạng thái shutdown và stack trace thường quan trọng hơn một snapshot duy nhất.

### Dấu hiệu cần điều tra

```text
Sau khi một test / request / service lifecycle kết thúc:
  số thread tên "worker-..." vẫn tăng qua mỗi lượt;
  nhiều thread đợi queue.take() dù owner đã đóng;
  isShutdown() == false trên pool đáng lẽ được giải phóng;
  hoặc isShutdown() == true nhưng isTerminated() không trở thành true.
```

Không gọi toàn bộ các trường hợp đó là cùng một lỗi. Pool còn RUNNING là thiếu shutdown; pool đã shutdown nhưng còn task kẹt là vấn đề cancellation/liveness; queue tăng là vấn đề backpressure.

## 18. Rejected execution: race giữa submit và shutdown

Hai thread có thể tranh chấp:

```text
Thread A                              Thread B
--------                              --------
if (!executor.isShutdown()) ...
                                      executor.shutdown()
executor.submit(task) -> REJECTED
```

`isShutdown()` chỉ là quan sát tại một thời điểm, không tạo giao dịch với `submit()`. Vì vậy, code nộp việc phải xử lý `RejectedExecutionException` hoặc hợp đồng của rejection policy.

Ví dụ:

```java
try {
    executor.execute(task);
} catch (RejectedExecutionException e) {
    reportNotAccepted(task);
}
```

Đây là đoạn minh họa, `executor`, `task` và `reportNotAccepted` do ứng dụng định nghĩa. Nếu task cần đảm bảo không mất, đường rejection có thể phải ghi bền vững, retry trên executor khác có kiểm soát hoặc báo lỗi cho caller.

Tránh thiết kế một “cờ custom accepting” tách rời executor mà không có đồng bộ; nó có thể làm nảy sinh race mới. Một giao thức shutdown tốt thường có điểm ngừng nhận ở tầng API/service, và mọi đường nộp task vẫn xử lý rejection như trường hợp hợp lệ.

## 19. ScheduledExecutorService cũng cần shutdown

`ScheduledExecutorService` nhận tác vụ trễ hoặc định kỳ. Nếu tạo `Executors.newSingleThreadScheduledExecutor()` cho mỗi đối tượng/request rồi không shutdown, worker và task đã lên lịch có thể tồn tại lâu hơn cần thiết.

Một số triển khai như `ScheduledThreadPoolExecutor` có chính sách cụ thể về **delayed tasks** và **periodic tasks** khi shutdown. Đừng mặc định rằng mọi scheduled task đã đặt lịch đều chạy hoặc đều bị hủy giống nhau trong mọi implementation.

Những điểm cần kiểm tra:

- Có task định kỳ nào tiếp tục hoặc bị dừng khi gọi `shutdown()`?
- Các delayed tasks đã nộp nhưng chưa đến hạn sẽ được xử lý theo policy nào?
- Khi cancel một scheduled future, queue có giữ wrapper pending cho đến thời điểm chạy dự kiến không?
- Với `ScheduledThreadPoolExecutor`, `setRemoveOnCancelPolicy(true)` có thể hữu ích để các task bị cancel được loại khỏi queue nhanh hơn trong các tình huống phù hợp.
- Chỉ sau khi policy và task kết thúc thì executor mới terminated.

Cũng cần theo dõi resource mà scheduled task dùng: việc cancel timer không tự đóng connection hoặc xóa dữ liệu `ThreadLocal` mà job đã tạo.

## 20. Bounded queue, pool size và tổng tài nguyên

Tránh thread leak không chỉ là đóng pool. Một pool được tạo đúng lifecycle vẫn có thể gặp **tải vượt khả năng xử lý**, dẫn tới nhiều task queued và giữ bộ nhớ.

Ví dụ `Executors.newFixedThreadPool(n)` thường có hàng đợi không giới hạn thực tế. Nếu producer nộp 100.000 task mỗi giây nhưng worker chỉ xử lý 10.000, backlog sẽ tăng. Dù số thread ổn định, heap và độ trễ có thể bị đẩy tới giới hạn.

Khi muốn kiểm soát tải, có thể cấu hình `ThreadPoolExecutor` với bounded queue và rejection policy rõ:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4, 4, 0, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100));
```

Đây là đoạn minh họa, cần import `ThreadPoolExecutor`, `TimeUnit` và `ArrayBlockingQueue`. Khi bốn worker đều bận và queue đã đầy, yêu cầu mới có thể bị từ chối theo rejection policy đã chọn. Phải xử lý **backpressure** thay vì tạo thêm vô hạn task chờ.

Chọn queue capacity, pool size và thời hạn task theo thực tế. Một queue bounded không tự giải quyết task chết kẹt: nếu mọi worker đứng chờ vĩnh viễn, queue sẽ đầy và nộp việc bị từ chối. Cần timeout/cancel và thiết kế liveness đúng.

## 21. Test lifecycle như thế nào?

Một test tốt không dựa vào `Thread.sleep(100)` rồi đoán pool đã dừng. Nên tạo precondition có kiểm soát bằng `CountDownLatch`, `Future` hoặc các primitive đồng bộ thích hợp.

**Những điều nên kiểm tra:**

1. Sau `shutdown()`, việc nộp task mới được xử lý theo rejection policy.
2. Tác vụ đã nộp được hoàn thành trong graceful path nếu task hợp tác.
3. `awaitTermination` trả `false` khi có task cố ý chưa thể hoàn tất.
4. Khi task được mở latch hoặc xử lý interrupt, executor chuyển terminated.
5. `shutdownNow()` gửi interrupt tới task interruptible và trả về pending task chưa chạy (trong tình huống được điều phối).
6. Code cleanup chạy trong `finally`, kể cả khi có exception/cancellation.
7. Sau mỗi lượt test tạo pool, owner **phải đóng** pool, tránh làm bộ test tích lũy worker.

### Mini test bằng assert thông thường

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<Integer> value = executor.submit(() -> 42);
    if (value.get() != 42) {
        throw new AssertionError("wrong result");
    }
} finally {
    executor.shutdownNow();
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        throw new AssertionError("pool did not stop");
    }
}
```

Đây là đoạn minh họa nằm trong method khai báo `throws InterruptedException, ExecutionException` (hoặc `throws Exception`), với các import `ExecutorService`, `Executors`, `Future` và `TimeUnit`. Điều quan trọng là kiểm tra được **outcome task** và **termination** tách biệt.

Trong sản phẩm thật, thay vì `shutdownNow()` ngay trong finally, thường chọn graceful trước rồi fallback theo yêu cầu dữ liệu. Khi test bị interrupt, phải xử lý cờ interrupt và cleanup phù hợp để không gây rò rỉ pool sang test khác.

## 22. Một quy trình đóng service thực tế

Giả sử service có một executor nhận background jobs và một nguồn gửi yêu cầu. Shutdown an toàn cần có thứ tự:

1. **Ngừng nhận yêu cầu mới** ở cổng giao tiếp của service.
2. **Ngừng producer** nộp task mới vào executor; có giao thức báo rejected nếu còn cạnh tranh.
3. **Gọi `shutdown()`** để drain các task đã nhận.
4. **Đợi có deadline** bằng `awaitTermination()`. Chọn thời hạn theo nghiệp vụ, không tùy tiện chờ vô hạn.
5. Nếu deadline graceful hết, **`shutdownNow()`** để yêu cầu cancel phần còn lại và xem xét pending tasks.
6. **Đợi lại có giới hạn**; nếu chưa terminated, ghi nhận shutdown chưa hoàn tất, metric/log và có phương án xử lý của hệ thống điều phối process.
7. **Đóng resource phụ thuộc** (database pool, file, socket...) theo thứ tự owner/task không còn cần chúng, trừ resource cần đóng sớm để phá blocking I/O.
8. Đối chiếu **outcome nghiệp vụ** qua Future, kênh kết quả, idempotency hoặc trạng thái lưu bền vững; termination không thay thế việc xác nhận job đã commit.

**Mấu chốt:** thứ tự đóng phải theo **đồ thị phụ thuộc tài nguyên**. Nếu executor còn task đang dùng database mà đóng database trước, tác vụ có thể thất bại. Nếu task kẹt đọc socket, có thể cần đóng socket để đánh thức nó; không có thứ tự duy nhất cho mọi hệ thống.

### Deadline tổng thể

Nếu gọi `awaitTermination(5s)` rồi thêm `awaitTermination(5s)`, thời gian chờ có thể lên tới khoảng **10 giây** cộng overhead. Nếu yêu cầu đóng toàn service trong một deadline tổng thể, nên phân bổ ngân sách hoặc tính thời gian còn lại bằng `System.nanoTime()`; không cộng vô hạn các timeout độc lập.

Một timeout hết hạn **không phải là lệnh kill**, chỉ là thông tin caller đã chờ đủ lâu. Hãy báo tình trạng chưa hoàn tất thay vì bịa rằng worker đã dừng.

## 23. Checklist chống thread leak

Trước khi đưa một thành phần sử dụng executor vào production, tự kiểm tra:

- **Owner:** Ai tạo pool? Ai được gọi `shutdown()`? Có đóng đúng một lần khi lifecycle kết thúc không?
- **Số lượng:** Có pool mới trong mỗi request, mỗi vòng lặp hoặc mỗi retry không? Giới hạn số thread/queue ở đâu?
- **Admission:** Khi bắt đầu shutdown, nộp task mới có bị từ chối đúng cách không?
- **Task:** Mỗi task có điểm thoát, timeout, hợp đồng interrupt và cleanup hay không?
- **Blocking:** Có task giữ lock chờ task khác trong cùng pool không?
- **Future:** Có kiểm tra task outcome qua `get()` hoặc kênh lỗi không?
- **Queue:** Có backlog vô hạn và thiếu backpressure không?
- **ThreadLocal:** Có `remove()` trong `finally` cho dữ liệu theo request không?
- **Resources:** Có đóng file, socket, stream, connection không?
- **Termination:** Có `awaitTermination()` và xử lý nhánh `false` không?
- **Diagnostics:** Pool có tên thread và metric để truy ra worker bị treo không?
- **Testing:** Có test chắc chắn dọn pool kể cả test thất bại không?

Đó là những kiểm tra theo **lifecycle**; không cần đợi đến khi JVM tăng hàng nghìn thread mới bắt đầu xem xét.

## 24. Tự kiểm tra kiến thức

**Câu 1.** Sau `shutdown()`, executor có chắc chắn đã hết thread chưa?

**Trả lời:** Không. `shutdown()` bắt đầu đóng có trật tự, không đợi. Những task đã nhận có thể tiếp tục chạy.

**Câu 2.** `isShutdown()==true` và `isTerminated()==false` có mâu thuẫn không?

**Trả lời:** Không. Executor đã bước vào shutdown nhưng vẫn có task/worker chưa kết thúc.

**Câu 3.** `shutdownNow()` có “giết” một task CPU-bound không kiểm tra interrupt không?

**Trả lời:** Không bảo đảm. Nó gửi yêu cầu hủy hợp tác; task có thể tiếp tục chạy.

**Câu 4.** `awaitTermination(2, SECONDS)` trả `false` nghĩa là gì?

**Trả lời:** Executor chưa đạt terminated trong hai giây. Không tự suy ra mọi task thất bại, hay mọi worker đã dừng.

**Câu 5.** Một method tạo `newSingleThreadExecutor()` mỗi request mà không shutdown. Vì sao nguy hiểm?

**Trả lời:** Mỗi request có thể để lại worker nhàn rỗi nhưng còn sống; tổng số thread và tài nguyên tăng theo số request.

**Câu 6.** Nếu task đã hoàn thành `Future.get()` với kết quả đúng, có thể bỏ qua đóng executor không?

**Trả lời:** Không. Future task hoàn thành không có nghĩa worker pool đã kết thúc vòng đời. Owner vẫn cần shutdown khi không dùng nữa.

**Câu 7.** Vì sao cần `ThreadLocal.remove()` trong `finally`?

**Trả lời:** Pooled thread có thể chạy nhiều task; dữ liệu request cũ có thể tiếp tục được giữ và bị task sau nhìn thấy, gây memory retention hoặc rò rỉ context.

**Câu 8.** `Future.cancel(true)` có chứng minh worker đã cleanup xong không?

**Trả lời:** Không. Trạng thái Future canceled có thể đến trước khi task hoàn tất cleanup; cần tín hiệu riêng hoặc termination phù hợp.

**Câu 9.** Một task trong single-thread executor nộp task con vào chính pool rồi `get()` chờ task con. Nguy cơ gì?

**Trả lời:** Thread-starvation deadlock: worker duy nhất chờ một task chưa có worker để chạy.

**Câu 10.** Sau `shutdown()`, thread A kiểm tra `!isShutdown()` rồi submit trong khi thread B shutdown. Có chắc submit thành công không?

**Trả lời:** Không. Có race giữa check và submit; caller phải xử lý rejection.

**Câu 11.** `ThreadFactory` tạo daemon thread có thay được shutdown đúng cách không?

**Trả lời:** Không. Daemon có thể khiến process thoát mà không chờ task flush/cleanup; không phải cách quản lý tài nguyên an toàn.

**Câu 12.** Một pool đã terminated, liệu mọi job đã commit database thành công?

**Trả lời:** Không nhất thiết. Task có thể fail, cancel hoặc kết thúc trước commit. Phải kiểm tra outcome và có transaction/recovery ở tầng nghiệp vụ.

## 25. Tổng kết

**ExecutorService là tài nguyên có vòng đời**, không chỉ là một hàm chạy task. Muốn tránh thread leak cần **owner rõ ràng, ngừng nhận việc đúng lúc, shutdown có giới hạn thời gian, task hợp tác cancel, cleanup tài nguyên và xác nhận termination**.

Một mẫu an toàn là **`shutdown()` → `awaitTermination()` → nếu cần `shutdownNow()` → `awaitTermination()` lần nữa**. Nhưng shutdownNow chỉ cố interrupt, không cưỡng chế task dừng; timed wait chỉ báo đã hoặc chưa terminated trong khoảng đợi; và trạng thái terminated không thay thế việc kiểm tra kết quả nghiệp vụ.

Thiết kế tốt bắt đầu từ lúc tạo pool: tái sử dụng ở scope phù hợp, không tạo bừa trong mỗi request, đặt tên worker, giới hạn backlog, dọn `ThreadLocal`/resources, tránh task tự chờ nhau và có test lifecycle. Với Java concurrency nói chung, **đóng executor cũng quan trọng như nộp tác vụ vào executor**.
