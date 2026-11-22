# Xử lý InterruptedException và bảo toàn tín hiệu ngắt phù hợp

## 1. Vì sao InterruptedException quan trọng trong ứng dụng Spring?

Khi một ứng dụng Spring chạy nhiều công việc nền bằng `TaskExecutor`, `ThreadPoolTaskExecutor`, `@Async`, `TaskScheduler` hoặc một `ExecutorService` do ứng dụng sở hữu, nó phải có cách yêu cầu công việc **ngừng sớm**: client không còn cần kết quả, job hết hạn, executor đang shutdown, hoặc một workflow cần hủy các nhánh còn lại.

Trong Java, **interruption** là cơ chế phối hợp: một thread có thể gửi **yêu cầu ngắt** cho thread khác qua `Thread.interrupt()`. Các thao tác blocking có hỗ trợ interruption như `Thread.sleep`, `Object.wait`, `BlockingQueue.take`, `CountDownLatch.await` hoặc `Future.get` có thể phản hồi bằng `InterruptedException`. Đây **không** phải lệnh cưỡng ép giết thread, và cũng không đồng nghĩa tất cả I/O, JDBC query hoặc tác vụ CPU lập tức dừng.

Cách xử lý đúng tùy **ai đang sở hữu vòng đời của công việc**:

- Nếu method **cho phép ném `InterruptedException`**, thường **truyền tiếp (propagate)** ngoại lệ để tầng trên quyết định dừng và cleanup.
- Nếu method **không thể truyền checked exception**, thường **khôi phục interrupt flag** bằng `Thread.currentThread().interrupt()`, rồi **thoát khỏi công việc hoặc chuyển sang hợp đồng hủy có ngữ nghĩa**.
- Nếu code **thực sự sở hữu** tín hiệu và có chính sách xử lý hoàn tất việc hủy, nó có thể tiêu thụ tín hiệu một cách chủ đích; nhưng phải hiểu rõ ranh giới, không được nuốt ngoại lệ rồi tiếp tục nghiệp vụ như chưa có gì xảy ra.

> Quy tắc thực hành: **đừng im lặng nuốt `InterruptedException`**. Truyền tiếp nếu được; nếu phải đổi sang unchecked exception hoặc trả về, khôi phục interrupt flag trước khi rời ranh giới, trừ trường hợp mã đã chủ động xử lý toàn bộ giao thức hủy và được thiết kế để tiêu thụ tín hiệu.

Bài thuộc nhóm **Hết hạn và hủy** của **Spring Framework – concurrency**. Trọng tâm là hiểu status bit, `InterruptedException` và cách viết worker/caller không vô tình phá tín hiệu hủy, đặc biệt với Spring `@Async` và Futures.

## 2. Interrupt là yêu cầu hợp tác, không phải dừng cưỡng bức

### 2.1. Thread có trạng thái interrupted

Mỗi Java thread có một **interrupted status**. API quan trọng:

| API | Ý nghĩa | Có xóa interrupt flag không? |
| --- | --- | --- |
| `someThread.interrupt()` | Yêu cầu ngắt thread được chỉ định, thường đặt trạng thái interrupted hoặc đánh thức một blocking call hỗ trợ ngắt | Không phải API đọc/xóa flag; cách một blocking call phản ứng còn phụ thuộc API |
| `Thread.currentThread().isInterrupted()` | Đọc flag của **thread hiện tại** | **Không** |
| `someThread.isInterrupted()` | Đọc flag của thread tương ứng | **Không** |
| `Thread.interrupted()` | Đọc flag của **thread hiện tại** và **xóa trạng thái đó** | **Có** |
| `Thread.sleep(...)`, `Object.wait(...)`, `CountDownLatch.await()` | Khi bị interrupt trong khi chờ, thường ném `InterruptedException` | **Có**, chúng xóa flag khi ném ngoại lệ |

Cần phân biệt chính xác hai lệnh dễ nhầm:

~~~java
boolean peek = Thread.currentThread().isInterrupted();
// Chỉ quan sát, vẫn giữ trạng thái.

boolean consume = Thread.interrupted();
// Quan sát rồi xóa trạng thái interrupted của current thread.
~~~

Đây là hai **mảnh code minh họa**. `Thread.interrupted()` là method **static**, dù nhìn giống `isInterrupted()`; gọi nó vô tình trong một phương thức trợ giúp có thể làm mất tín hiệu hủy mà những tầng phía sau cần quan sát.

### 2.2. Tại sao bắt InterruptedException lại thấy flag bằng false?

Ví dụ:

~~~java
try {
    Thread.sleep(10_000L);
} catch (InterruptedException ex) {
    System.out.println(Thread.currentThread().isInterrupted());
}
~~~

Khi `sleep` bị interrupt và ném `InterruptedException`, status của thread đã được **xóa theo hợp đồng của sleep**. Vì vậy trong tình huống thường gặp, lệnh `isInterrupted()` trong catch cho `false`, không có nghĩa trước đó không hề có yêu cầu ngắt.

Đây là điểm làm phát sinh lỗi:

~~~java
try {
    queue.take();
} catch (InterruptedException ex) {
    // Chỉ log và tiếp tục vòng lặp — tín hiệu đã bị xóa!
}
~~~

Mảnh code trên cần `queue` phù hợp và không nên được copy làm production pattern. Nếu worker tiếp tục vòng lặp mà không báo cho ai, một shutdown/cancel request có thể bị **bỏ qua**. Người vận hành thấy công việc vẫn chạy dù đã gửi yêu cầu ngắt.

## 3. Ba chiến lược xử lý InterruptedException

### 3.1. Chiến lược A: truyền tiếp ngoại lệ nếu hợp đồng cho phép

Nếu method khai báo `throws InterruptedException`, cách rõ nhất thường là **không bắt** để nó tự truyền lên:

~~~java
public JobResult waitForData(BlockingQueue<JobResult> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

Đây là method hợp lệ khi đặt trong class với import `BlockingQueue` và `JobResult` đã khai báo. Nó không phải chương trình chạy độc lập. Tầng gọi, vốn biết có nên cancel workflow hay không, sẽ nhận được `InterruptedException`.

Nếu có resource cần dọn, dùng `finally` hoặc `try-with-resources`:

~~~java
public void runInterruptibly(BlockingQueue<String> queue)
        throws InterruptedException {
    openResource();
    try {
        String item = queue.take();
        process(item);
    } finally {
        closeResource();
    }
}
~~~

Mảnh code minh họa này cần các method `openResource`, `process`, `closeResource`. Việc `queue.take()` ném `InterruptedException` khiến control đi vào `finally` rồi truyền tiếp exception, trừ khi `closeResource()` ném lỗi khác. Production code cần quyết định cách ưu tiên/ghi nhận lỗi cleanup và có thể dùng `try-with-resources` để giữ suppressed exception.

**Khi truyền tiếp `InterruptedException` đúng như contract, thường không cần tự restore flag trong cùng tầng**. Exception là tín hiệu rõ ràng cho caller; tầng trên chịu trách nhiệm không bỏ mất nó. Nếu mọi tầng chỉ wrap thành một exception khác, cần cân nhắc phục hồi interrupt status trước khi đi qua boundary ấy.

### 3.2. Chiến lược B: không thể ném checked exception, restore rồi thoát

Một `Runnable.run()` không khai báo `throws InterruptedException`. Khi nó cần dùng `sleep`, `take` hoặc `await`, thường chọn:

~~~java
@Override
public void run() {
    try {
        processNextItem();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return; // Dừng vòng đời Runnable này, không tiếp tục xử lý job.
    }
}
~~~

Đây là **mảnh code minh họa**: `processNextItem()` phải được định nghĩa có khả năng ném `InterruptedException`. Nếu cần log hoặc thông báo job cancellation, thực hiện mà không làm hỏng interrupt contract.

Nếu muốn chuyển thành lỗi unchecked để người giám sát/đối tượng gọi thấy thất bại:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Job interrupted", ex);
}
~~~

Cần `blockingOperation()` được định nghĩa. **Cả hai thao tác đều có vai trò riêng**: restore flag để không làm mất tín hiệu của thread, và exception để biểu đạt kết quả tác vụ cho cơ chế giám sát. Chỉ ném `new RuntimeException(ex)` mà không restore có thể khiến tầng quản lý thread không thấy flag từng bị ngắt, dù cause vẫn còn.

### 3.3. Chiến lược C: chuyển thành trạng thái cancelled có chủ đích

Ở một ranh giới điều phối job, một contract có thể định nghĩa rõ `JobResult.cancelled(...)` thay cho exception. Khi đó vẫn phải **dừng việc xử lý tiếp** và cập nhật trạng thái một cách nhất quán:

~~~java
try {
    waitForExternalSignal();
    return JobResult.completed();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return JobResult.cancelled();
}
~~~

Đây là đoạn khái niệm cần `JobResult` và `waitForExternalSignal`. Không nên chỉ trả `JobResult.completed()` trong catch vì caller sẽ tưởng thao tác đã thành công. Nếu phương thức còn chạy các đoạn blocking sau khi restore, nó có thể lại gặp interrupt ngay; vì vậy **restore rồi kết thúc ranh giới** thường dễ hiểu hơn restore rồi tiếp tục chạy.

Trong những framework có **giao thức hủy riêng**, ranh giới sở hữu thread có thể lựa chọn tiêu thụ tín hiệu theo tài liệu, sau khi đã dừng task và ghi trạng thái. Người viết application service không nên tự ý giả định mình là tầng sở hữu toàn bộ vòng đời của thread do Spring quản lý.

## 4. Mẫu sai: nuốt, lặp lại vô hạn, hoặc khôi phục ở sai thời điểm

### 4.1. Nuốt exception rồi tiếp tục

~~~java
while (running) {
    try {
        String job = queue.take();
        process(job);
    } catch (InterruptedException ignored) {
        // Sai: bỏ qua tín hiệu và quay lại queue.take().
    }
}
~~~

Đây là ví dụ **sai có chủ đích**, cần biến `running`, `queue`, `process`. Với `BlockingQueue.take`, khi exception được ném, flag đã xóa; vòng lặp có thể chờ tiếp vô thời hạn, dù hệ thống cần shutdown.

Sửa:

~~~java
while (running) {
    try {
        String job = queue.take();
        process(job);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        break; // Thoát khỏi vòng lặp worker.
    }
}
~~~

Nếu cleanup phải chạy, bao vòng lặp trong `try/finally`. Đừng đặt một vòng lặp khác phía dưới chỉ để worker bắt đầu nhận việc lại sau khi đã break.

### 4.2. Restore flag rồi tiếp tục sleep trong một vòng lặp

~~~java
while (true) {
    try {
        Thread.sleep(1000L);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Sai nếu tiếp tục vòng lặp: sleep sau sẽ lại bị interrupt ngay.
    }
}
~~~

Đây là mảnh anti-pattern. Khôi phục flag **không phải giấy phép để tiếp tục công việc**. Với nhiều blocking API, status đã set làm lần chờ kế tiếp ném ngay `InterruptedException`, gây vòng lặp bận CPU hoặc log spam.

Sửa bằng `break`, `return` hoặc truyền tiếp, tùy hợp đồng. Muốn tiếp tục vì interruption không có ý nghĩa dừng trong một API cụ thể, phải có chính sách rõ ràng để xử lý/tiêu thụ trạng thái — không mặc định làm điều này trong business task.

### 4.3. Dùng Thread.interrupted() chỉ để kiểm tra

~~~java
if (Thread.interrupted()) {
    logCancellation();
}
// Tín hiệu vừa bị xóa! Một hàm phía sau có thể không còn thấy nữa.
~~~

Đây là đoạn minh họa. Nếu chỉ muốn **nhìn** trạng thái, dùng `Thread.currentThread().isInterrupted()`. Nếu muốn dùng `Thread.interrupted()` để chủ động tiêu thụ, chẳng hạn trong loop chuẩn hóa trạng thái của một thành phần quản lý thread, phải biết chính xác vì sao tiêu thụ an toàn.

### 4.4. Catch Exception quá rộng và mất ý nghĩa

~~~java
try {
    future.get();
} catch (Exception ex) {
    logFailure(ex);
    return null;
}
~~~

Đây là ví dụ sai có chủ đích. `Future.get()` có thể báo `InterruptedException`, `ExecutionException` hoặc `CancellationException` với ý nghĩa khác nhau. Bắt tất cả rồi trả `null` vừa nuốt interruption, vừa biến lỗi thành một kết quả dễ bị coi là thành công.

Hãy tách nhánh `InterruptedException` để giữ tín hiệu, phân loại `ExecutionException.getCause()` theo lỗi thực thi và xử lý cancellation/timeouts đúng contract.

## 5. Ví dụ Java 17 độc lập: flag bị xóa rồi được khôi phục

Demo dùng `CountDownLatch` để điều khiển thread, không dựa vào ngủ một thời gian ngẫu nhiên. Nó chứng minh:

1. Sau khi `await()` bị interrupt và ném `InterruptedException`, flag thường bị xóa.
2. `Thread.currentThread().interrupt()` trong catch thiết lập lại status.
3. `Thread.currentThread().isInterrupted()` chỉ quan sát.
4. `Thread.interrupted()` vừa đọc vừa **xóa** status của thread hiện tại.

Tạo tệp **`InterruptFlagDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class InterruptFlagDemo {

    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch keepBlocked = new CountDownLatch(1);

        AtomicBoolean flagInCatch = new AtomicBoolean(true);
        AtomicBoolean flagAfterRestore = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            entered.countDown();
            try {
                keepBlocked.await();
            } catch (InterruptedException ex) {
                // await đã xóa interrupted status trước khi throw.
                flagInCatch.set(Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                flagAfterRestore.set(
                        Thread.currentThread().isInterrupted());
            }
        }, "interruptible-worker");

        worker.start();
        if (!entered.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Worker did not start");
        }

        // Yêu cầu ngắt dù worker vừa mới vào await hay chưa.
        worker.interrupt();
        worker.join(5000L);
        if (worker.isAlive()) {
            throw new IllegalStateException("Worker did not stop");
        }

        System.out.println("caught flag cleared: " +
                !flagInCatch.get());
        System.out.println("flag restored: " +
                flagAfterRestore.get());

        AtomicBoolean peek = new AtomicBoolean(false);
        AtomicBoolean consume = new AtomicBoolean(false);
        AtomicBoolean afterConsume = new AtomicBoolean(true);

        Thread probe = new Thread(() -> {
            Thread.currentThread().interrupt();
            peek.set(Thread.currentThread().isInterrupted());
            consume.set(Thread.interrupted());
            afterConsume.set(Thread.currentThread().isInterrupted());
        }, "flag-probe");

        probe.start();
        probe.join(5000L);
        if (probe.isAlive()) {
            throw new IllegalStateException("Probe did not stop");
        }

        System.out.println("isInterrupted observes: " + peek.get());
        System.out.println("Thread.interrupted observes: " +
                consume.get());
        System.out.println("Thread.interrupted clears: " +
                !afterConsume.get());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac InterruptFlagDemo.java
java InterruptFlagDemo
~~~

**Năm dòng stdout do chương trình tự in khi chạy bình thường:**

~~~text
caught flag cleared: true
flag restored: true
isInterrupted observes: true
Thread.interrupted observes: true
Thread.interrupted clears: true
~~~

Lý do kết quả ổn định:

- `entered` báo thread đã bước vào method, sau đó main gửi interruption. Nếu interruption đến trước `keepBlocked.await()`, `await` vẫn phát hiện flag và ném `InterruptedException`. Nếu đến trong lúc chờ, nó đánh thức method. Cả hai trường hợp đều vào catch.
- Catch thấy status đã bị xóa bởi `await`. Gọi `interrupt()` trên **current thread** sau đó khôi phục status. Ví dụ chỉ quan sát lại flag, rồi worker kết thúc.
- Thread `probe` riêng tự bật flag, dùng `isInterrupted` để quan sát mà không xóa, rồi dùng `Thread.interrupted()` để tiêu thụ. Ta không can thiệp vào interrupt flag của main thread.
- Hai lần `join(5000)` có giới hạn chờ và kiểm tra `isAlive()` để tránh báo kết quả thành công nếu worker không thoát như dự kiến.

Đây là demo về **semantics**, không phải quy trình dùng `interrupt()` tùy tiện với thread production. Trong thực tế, caller thường dùng `Future.cancel(true)` hoặc lifecycle của executor thay vì giữ reference trực tiếp tới worker thread.

## 6. Future.cancel(true) khác gì với InterruptedException?

`Future.cancel(boolean mayInterruptIfRunning)` là **nỗ lực hủy** task:

- `cancel(false)`: cố hủy Future mà **không yêu cầu interrupt** thread đang chạy thông qua cờ tham số; task đã chạy có thể vẫn hoàn tất công việc thực tế tùy implementation.
- `cancel(true)`: nếu task đang chạy và implementation biết worker thread, có thể **yêu cầu interrupt worker** để nó thoát sớm. Đây **không phải bảo đảm** công việc đã dừng, cũng không bảo đảm downstream I/O bị rollback.
- `isCancelled()`: báo trạng thái hủy theo hợp đồng Future, **không phải bằng chứng** mọi side effect bên ngoài đã chấm dứt.
- `isDone()`: true khi Future đã thành công, thất bại hoặc bị hủy. Nó không đồng nghĩa task đã commit thành công.
- `get()` trên Future bị hủy có thể ném `CancellationException`, không phải `InterruptedException` của worker.

**Đừng nhầm hai thread**:

~~~text
Caller / request thread                      Worker thread
-----------------------                      ----------------------
future.cancel(true)  --------------------->  interrupt attempt
                                             |
                                             +-- sleep / await / take
                                                    |
                                                    +-- InterruptedException
                                                    +-- catch, cleanup,
                                                        propagate/restore

future.get() của caller có thể:
    - CancellationException nếu Future đã cancelled;
    - InterruptedException nếu CHÍNH caller bị interrupt trong lúc chờ;
    - ExecutionException nếu computation hoàn tất lỗi (không bị cancel).
~~~

`InterruptedException` trong method worker và `InterruptedException` của caller khi chờ `Future.get()` là **hai sự kiện ở hai thread khác nhau**. Khôi phục flag cần làm trên **thread vừa bắt exception**, không phải trên một thread khác.

### 6.1. CompletableFuture.cancel(boolean) không bảo đảm interrupt worker

`CompletableFuture` của JDK có semantics đặc biệt: tham số `mayInterruptIfRunning` của `CompletableFuture.cancel(boolean)` **không được dùng để điều khiển quá trình thực thi của worker**. Nó chủ yếu hoàn thành Future theo trạng thái cancelled và thông báo cho dependent stages. Vì vậy **không được suy ra** `someCompletableFuture.cancel(true)` sẽ ngắt I/O hoặc thread thực tế đang chạy.

Trong Spring `@Async`, loại Future được trả về và cách Spring/Executor xây dựng handle có ảnh hưởng tới cancellation. `@Async` trả `Future<T>` từ một executor hỗ trợ cancellation có thể cho phép yêu cầu interrupt; `CompletableFuture<T>` và các stage kết hợp không nên bị hiểu nhầm là một nút "kill task" có bảo đảm. **Kiểm tra API/runtime cụ thể và test cancellation**, thay vì chỉ dựa trên kiểu biến hoặc tên method.

Nếu phải có khả năng dừng một job dài, cân nhắc thiết kế **cancellation token**/flag nghiệp vụ riêng, có các điểm kiểm tra định kỳ, deadline rõ ràng và các I/O operations có timeout. Dùng interruption như một trong các tín hiệu hợp tác, không phải nguồn bảo đảm duy nhất.

### 6.2. Timeout chờ không phải lệnh hủy

~~~java
try {
    return future.get(3, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Caller đã chờ quá hạn; job có thể vẫn chạy.
    boolean requested = future.cancel(true);
    throw new TaskTimeoutException(requested, ex);
}
~~~

Đây là mảnh code minh họa, cần `future`, các import và `TaskTimeoutException` ứng dụng. `get(timeout)` ném `TimeoutException` chỉ nói **caller chờ quá thời hạn**; việc có muốn gọi `cancel(true)` hay không là **quyết định nghiệp vụ**. Không phải mọi timeout đều nên hủy job, ví dụ background report được phép tiếp tục và client sẽ poll trạng thái.

## 7. Worker loop: shutdown hợp tác và cleanup

Một worker dạng vòng lặp thường chờ trên `BlockingQueue`. Đây là một thiết kế đúng về interruption nếu **worker do ứng dụng sở hữu**:

~~~java
public void consume(BlockingQueue<Job> queue)
        throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        process(job);
    }
}
~~~

Đoạn code minh họa cần kiểu `Job` và `process(Job)`. Nếu `queue.take()` bị interrupt, nó ném `InterruptedException` và method truyền tiếp, thay vì nuốt. Nếu `process` không interruptible, yêu cầu dừng có thể chỉ được quan sát sau khi `process` trả về.

Một `Runnable` không thể khai báo `throws InterruptedException`, nên phiên bản tương đương:

~~~java
public final class QueueConsumer implements Runnable {
    private final BlockingQueue<String> queue;

    public QueueConsumer(BlockingQueue<String> queue) {
        this.queue = queue;
    }

    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                String message = queue.take();
                handle(message);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            releaseOwnedResources();
        }
    }

    private void handle(String message) {
        // Xử lý một thông điệp. Bản thực tế cần timeout/retry phù hợp.
    }

    private void releaseOwnedResources() {
        // Đóng tài nguyên mà consumer thực sự sở hữu.
    }
}
~~~

Đây là **class minh họa**, cần import `BlockingQueue`; có thể biên dịch sau khi bổ sung import đó nhưng không có `main()` độc lập. Khi `take` ném exception, catch restore flag, finally cleanup, sau đó `run()` kết thúc. Đây là cách không tiếp tục lấy công việc sau khi đã yêu cầu dừng.

**Lưu ý với Spring-managed executor:** nếu một thread thuộc `ThreadPoolTaskExecutor` do Spring quản lý, application task **không sở hữu toàn bộ vòng đời worker thread**. Task nên kết thúc sớm khi nhận yêu cầu ngắt và để executor quyết định tái sử dụng/thay thế worker. Không dùng `Thread.stop()`, không tự thay đổi internal worker state hoặc cố shutdown cả executor bên trong một task không sở hữu nó.

## 8. Ví dụ đầy đủ Spring Framework: Future.cancel(true) và @Async worker

Demo này mô tả đường cancellation có thể quan sát với **`Future<T>` trả về từ một method `@Async`** và bean `ThreadPoolTaskExecutor` do Spring quản lý. Nó sử dụng `CountDownLatch` để xác định task thực sự đã bắt đầu, rồi caller yêu cầu hủy. Worker đang chờ một latch không bao giờ được thả nên có thể phản ứng qua `InterruptedException`.

**Môi trường:** Java 17+, Spring Framework 6.1.14, Gradle 8.5+. Đây là ứng dụng dòng lệnh, không cần Spring Boot.

### 8.1. Cấu trúc

~~~text
spring-interrupt-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SpringInterruptDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-interrupt-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.SpringInterruptDemo'
}
~~~

**src/main/java/demo/SpringInterruptDemo.java**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringInterruptDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            CancelWorker worker = context.getBean(CancelWorker.class);
            CountDownLatch started = new CountDownLatch(1);
            CompletableFuture<Boolean> observed = new CompletableFuture<>();

            Future<String> handle = worker.runInterruptibly(
                    started, observed);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Với Future của ThreadPoolTaskExecutor trong cấu hình này,
            // cancel(true) cố gửi interruption tới worker.
            boolean cancellationAccepted = handle.cancel(true);

            // Future cancellation không phải bằng chứng mọi cleanup đã xong;
            // dùng observer riêng để biết worker đã vào catch.
            boolean workerRestored = observed.get(5, TimeUnit.SECONDS);

            System.out.println("cancel accepted: " +
                    cancellationAccepted);
            System.out.println("worker restored flag: " +
                    workerRestored);
            System.out.println("handle is cancelled: " +
                    handle.isCancelled());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("workerExecutor")
        public ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("cancel-worker-");
            return executor;
        }

        @Bean
        public CancelWorker cancelWorker() {
            return new CancelWorker();
        }
    }

    public static class CancelWorker {

        @Async("workerExecutor")
        public Future<String> runInterruptibly(
                CountDownLatch started,
                CompletableFuture<Boolean> observed) {

            CountDownLatch neverReleased = new CountDownLatch(1);
            started.countDown();

            try {
                neverReleased.await();
                return CompletableFuture.completedFuture("unexpected");
            } catch (InterruptedException ex) {
                // 'await' đã xóa flag.
                Thread.currentThread().interrupt();
                observed.complete(
                        Thread.currentThread().isInterrupted());

                // Không xử lý job tiếp sau khi bị ngắt.
                throw new IllegalStateException("Job interrupted", ex);
            }
        }
    }
}
~~~

**Chạy** từ thư mục `spring-interrupt-demo`:

~~~bash
gradle run
~~~

Nếu project có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

**Stdout của chương trình khi `cancel(true)` của Future được Spring/ThreadPoolTaskExecutor hỗ trợ như dự kiến và hai thao tác chờ không timeout:**

~~~text
cancel accepted: true
worker restored flag: true
handle is cancelled: true
~~~

Đây là ví dụ **kiểm tra một cấu hình cụ thể**, không phải bảo đảm rằng mọi `Future.cancel(true)` hay `CompletableFuture.cancel(true)` trong mọi runtime đều ngắt được worker. Nếu implementation không interrupt worker, `observed.get(timeout)` có thể timeout thay vì in các dòng thành công; trong thực tế phải có fallback và chính sách shutdown. Spring/Gradle có thể in thêm log ngoài ba dòng của chương trình.

### 8.2. Điều demo chứng minh và không chứng minh

- `@EnableAsync` bật xử lý annotation trong context. `CancelWorker` được đăng ký bằng `@Bean`; caller lấy nó từ `ApplicationContext`, nên `@Async("workerExecutor")` có thể qua proxy.
- `@Async` method trả `Future<String>`; phần worker chạy trên pool được đặt tên `cancel-worker-`.
- `started` giúp chắc chắn method đã vào worker trước khi caller hủy; không cần `Thread.sleep` để đoán thời điểm.
- `handle.cancel(true)` yêu cầu hủy Future. Với đường thực thi hỗ trợ ngắt của `ThreadPoolTaskExecutor`, nó gửi interrupt tới worker đang chờ `neverReleased.await()`.
- `InterruptedException` do `await()` ném **xóa flag**, worker gọi `interrupt()` để restore, ghi nhận `true` qua observer rồi thoát bằng exception.
- `handle.isCancelled()` mô tả **Future ở caller**, còn `observed` cho thấy worker đã thật sự xử lý interruption. Không dùng trạng thái Future thay thế cho bằng chứng đã cleanup toàn bộ side effect.
- Không hứa transaction rollback hoặc database driver đã ngừng I/O chỉ vì worker đã nhận interrupt; hủy vẫn là một protocol hợp tác.

Nếu mục tiêu chỉ là quan sát status bit, demo ở mục 5 độc lập với Spring và ít yếu tố runtime hơn. Demo ở mục 8 cho thấy khi đã có Spring proxy, **interrupt vẫn là quy tắc Java**, không có "interrupt flag riêng của Spring".

## 9. Spring @Async: phân biệt lỗi thực thi và lỗi chờ của caller

Khi một caller thực hiện:

~~~java
Future<Report> future = reportWorker.generateAsync();
Report report = future.get();
~~~

Đây là mảnh minh họa cần bean và kiểu `Report`. Có ít nhất ba đường báo lỗi:

1. **Worker bị interrupt:** method đang `sleep`/`await` có thể ném `InterruptedException` trong **worker**. Worker xử lý bằng cách propagate hoặc restore/translate theo contract.
2. **Caller bị interrupt trong lúc chờ `future.get()`:** chính `get()` trên **caller thread** ném `InterruptedException`. Catch ở caller nên restore flag nếu không truyền checked exception, và quyết định có yêu cầu hủy worker hay không.
3. **Worker ném một lỗi và Future hoàn thành lỗi:** `future.get()` thường ném `ExecutionException` bọc nguyên nhân. Nếu Future đã bị cancel, `get()` có thể ném `CancellationException` thay vì ExecutionException.

Đừng phân loại mọi `InterruptedException` thành "worker đã bị hủy"; cần xác định **thread nào** bị ngắt và **operation nào** đang đợi.

### 9.1. Caller chờ Future và bị interrupt

~~~java
try {
    return future.get(5, TimeUnit.SECONDS);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();

    // Đây là quyết định nghiệp vụ, không phải hành vi bắt buộc:
    future.cancel(true);

    throw new JobWaitInterruptedException(ex);
} catch (TimeoutException ex) {
    throw new JobWaitTimeoutException(ex);
} catch (ExecutionException ex) {
    throw mapExecutionFailure(ex.getCause());
} catch (CancellationException ex) {
    throw new JobWasCancelledException(ex);
}
~~~

Đây là **đoạn code minh họa**, cần khai báo `future`, exception ứng dụng và mapping. Nếu muốn worker tiếp tục xử lý dù request caller không còn chờ, đừng tự động gọi `future.cancel(true)`. Nếu task bắt buộc có kết quả cho job store/broker, một caller bị interrupt không nhất thiết có quyền dừng job.

### 9.2. @Async void và exception handler

Method `@Async void` không trả Future cho caller. Nếu một `InterruptedException` bị bắt rồi chuyển thành exception trong worker, lỗi này không thể tự ném đồng bộ sang caller. Spring có `AsyncUncaughtExceptionHandler` để quan sát exception của asynchronous `void` methods.

~~~java
@Async("workerExecutor")
public void doWork() {
    try {
        blockingStep();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Work interrupted", ex);
    }
}
~~~

Đây là method minh họa trong Spring-managed service; cần import và `blockingStep`. Với công việc có hợp đồng hủy rõ ràng, có thể ghi status cancelled và trả về; không nhất thiết phải ném error cho mọi lần hủy bình thường. Điều cần tránh là làm mất tín hiệu và tiếp tục tạo side effects.

## 10. Khi nào không thể dùng interrupt để dừng nhanh?

### 10.1. CPU-bound loop phải tự kiểm tra

Một vòng lặp tính toán không chứa blocking calls có thể tiếp tục chạy dù flag đã được set:

~~~java
public long calculate(long max) {
    long total = 0;
    for (long i = 0; i < max; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new CancellationException(
                    "Calculation interrupted");
        }
        total += (i % 17);
    }
    return total;
}
~~~

Đây là method Java minh họa cần import `CancellationException`. `isInterrupted()` **không xóa flag**, nên lời gọi này phù hợp để kiểm tra hợp tác. Trong vòng lặp cực lớn, kiểm tra mỗi iteration có thể gây overhead; có thể kiểm tra định kỳ, ví dụ mỗi vài nghìn iterations, với mức trễ phản ứng chấp nhận được.

Một `CancellationException` do ứng dụng ném trong worker không đồng nghĩa Future đã chuyển trạng thái cancelled bằng `Future.cancel`; nó có thể được lưu như computation failure tùy loại Future. Nếu nghiệp vụ cần phân biệt cancellation với failure, thiết kế status/job contract rõ ràng, không chỉ dựa vào tên exception.

### 10.2. Một số I/O không đáp ứng interruption như mong đợi

- Một `BlockingQueue.take()`, `CountDownLatch.await()` hoặc `Thread.sleep()` thường phản hồi interrupt bằng `InterruptedException`.
- Một `InterruptibleChannel` có thể đóng channel và báo `ClosedByInterruptException`, chứ không bắt buộc ném `InterruptedException`.
- Các JDBC drivers, HTTP clients, socket APIs, filesystem I/O hoặc native calls khác nhau có **hợp đồng ngắt khác nhau**; có thể không dừng ngay, bỏ qua interrupt hoặc trả lỗi riêng.
- `synchronized` lock acquisition truyền thống không tương đương `Lock.lockInterruptibly()`; muốn chờ lock có thể hủy, cần chọn primitive tương ứng và handle `InterruptedException`.
- Không dùng `Thread.stop()` vì đây là API không an toàn và đã bị deprecated.

**Timeout ở tầng I/O vẫn cần thiết.** Cancellation signal không thay thế socket read timeout, connect timeout, SQL query timeout, deadline hoặc tài nguyên bị giới hạn. Nếu API chỉ có blocking I/O không interruptible, code có thể phải đợi I/O kết thúc mới thực hiện cleanup; hãy thiết kế timeout và shutdown có giới hạn thay vì giả định `cancel(true)` có thể hủy tức thì.

### 10.3. Interruption không tự rollback transaction

Với Spring `@Transactional` chạy trên worker thread, interruption có thể làm method dừng hoặc ném exception; **transaction behavior** còn tùy cách exception được truyền qua proxy, quy tắc rollback và trạng thái database operation. Nếu method bắt `InterruptedException` rồi trả về thành công, transaction có thể **commit** dù một phần công việc chưa hoàn tất.

Khi cần hủy giao dịch, phải xác định contract rollback rõ ràng, thường bằng exception phù hợp được truyền tới transaction interceptor hoặc transaction status được đánh dấu rollback-only. Không suy ra "thread bị interrupt" tự làm JDBC rollback. Nếu task có side effect ngoài database (gửi email, gọi API), interruption cũng không tự hoàn tác chúng; cần thiết kế compensation/idempotency khi cần.

## 11. Shutdown executor, cancel job và lifecycle Spring

Trong Spring, `ThreadPoolTaskExecutor` là bean có lifecycle. Khi context shutdown, Spring và executor có cấu hình điều phối các task đang chạy, task chờ và thời gian chờ kết thúc. Đừng giả định mọi loại shutdown đều lập tức gửi interrupt đến mọi task hoặc mọi task luôn được cho chạy tới khi xong: hành vi còn tùy cấu hình, trạng thái và phiên bản.

Các thao tác JDK liên quan:

| Operation | Mục tiêu chung | Lưu ý |
| --- | --- | --- |
| `ExecutorService.shutdown()` | Ngừng nhận task mới, thường để task đã nhận chạy tiếp | **Không** phải yêu cầu interrupt trực tiếp tất cả task đang chạy |
| `ExecutorService.shutdownNow()` | Cố dừng task đang chạy (thường bằng interrupt) và trả danh sách task chờ chưa bắt đầu | Best-effort; không hứa mọi worker đã kết thúc |
| `Future.cancel(true)` | Cố hủy một task, có thể interrupt worker nếu implementation hỗ trợ | Không mặc nhiên hủy downstream side effects |
| `Future.cancel(false)` | Cố chuyển Future sang cancelled, không yêu cầu interrupt running task qua tham số | Hành vi thực thi phụ thuộc loại Future |
| `awaitTermination(timeout, unit)` | Chờ các worker của executor kết thúc đến giới hạn | Có thể ném `InterruptedException` cho **thread chờ** |

Ví dụ một service sở hữu `ExecutorService` riêng:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
try {
    // Submit và quản lý các task thuộc service này.
} finally {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
        }
    } catch (InterruptedException ex) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là một **mảnh code minh họa**; cần import `ExecutorService`, `Executors`, `TimeUnit`, và xác định nghiệp vụ được phép hủy task nào. Trong nhánh catch, chính **thread đang chờ termination** bị interrupt: code yêu cầu shutdownNow rồi **restore interrupt flag** trước khi thoát ranh giới, thay vì nuốt và tiếp tục chờ vô hạn.

Với **Spring-managed executor bean**, thông thường để Spring quản lý shutdown thay vì service gọi `shutdownNow()` từ bên trong một task. Ứng dụng vẫn cần quyết định deadline, những job nào phải hoàn tất, cơ chế job recovery và điều phối shutdown toàn hệ thống.

## 12. Cancellation, CompletableFuture và điểm chờ

`CompletableFuture.join()` không khai báo `InterruptedException` như `Future.get()`. Nó có thể chặn cho tới khi stage hoàn thành và thường ném `CompletionException` khi stage thất bại. **Đừng kết luận `join()` là non-blocking** hay có cơ chế dừng worker vì caller bị ngắt.

Nếu một caller đang `get()` bị interrupt, chiến lược hợp lệ là:

- **Truyền tiếp `InterruptedException`** khi signature/hợp đồng cho phép.
- **Restore và ném unchecked cancellation** nếu API không cho truyền checked exception.
- **Restore và trả trạng thái cancelled** nếu nghiệp vụ cho phép, không trả thành công giả.
- **Quyết định riêng** có gọi `future.cancel(true)` để yêu cầu dừng worker hay không; caller interruption và worker cancellation không phải một điều.

Với `CompletableFuture`, một pipeline có thể có nhiều stage chạy trên nhiều executors. Hủy Future kết quả không đảm bảo tất cả upstream stages và external requests đều đã dừng. Nếu workflow đòi hủy xuyên nhiều công việc, cần tracking handle, cancellation token, timeout ở downstream và giao thức hoàn tất trạng thái rõ ràng.

### 12.1. Timeout và interruption là hai sự kiện khác nhau

| Sự kiện | Tín hiệu thường thấy | Có tự cancel worker không? |
| --- | --- | --- |
| Caller chờ `get(timeout)` quá lâu | `TimeoutException` | Không |
| Caller bị interrupt khi đang `get()` | `InterruptedException` trên caller | Không tự động theo nghĩa API phải interrupt worker |
| Worker bị interrupt trong `sleep/await/take` | `InterruptedException` trên worker, flag thường bị clear | Worker phải xử lý hợp tác |
| `Future.cancel(true)` thành công về trạng thái | Future cancelled; `get()` có thể ném `CancellationException` | Có thể có interrupt attempt, không phải bảo đảm mọi work đã dừng |
| `CompletableFuture.orTimeout(...)` hết hạn | Future exceptional với `TimeoutException` | Không tự đảm bảo ngắt computation |
| Thread chờ `awaitTermination` bị ngắt | `InterruptedException` trên thread chờ | Không tự quyết định shutdown policy |

Một API có timeout thường có nghĩa "ngừng **đợi** sau deadline", không có nghĩa "ngừng mọi xử lý và rollback". Contract phải thể hiện rõ khác biệt này.

## 13. Lưu ý đặc biệt khi dùng ThreadPoolTaskExecutor, @Scheduled và event listeners

### 13.1. Method @Async không nên lờ interruption

~~~java
@Service
public class ImportWorker {
    @Async("importExecutor")
    public CompletableFuture<String> importAsync() {
        try {
            return CompletableFuture.completedFuture(
                    fetchAndImportInterruptibly());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

Đây là một **class minh họa**, cần import Spring annotations, `CompletableFuture`, method `fetchAndImportInterruptibly()` và bean `importExecutor`. `@Async` chỉ có hiệu lực qua Spring-managed proxy khi bật `@EnableAsync`; self-invocation `this.importAsync()` thường bỏ qua proxy.

Việc trả `failedFuture(ex)` báo lỗi qua Future cho caller, còn khôi phục flag là để **không tiêu thụ im lặng tín hiệu trên thread**. Đừng dùng `failedFuture` để ngụ ý caller đã hủy Future; stage lỗi và stage cancelled có thể có semantics khác nhau.

### 13.2. Scheduled task và callback ở message/event processing

Một `@Scheduled` callback cần quyết định liệu một lần chạy bị interrupt có được đánh dấu failure, aborted, hay retry ở lần lịch kế tiếp. **Đừng đặt catch-all `catch (Exception)` rồi chạy tiếp vòng lặp vô hạn** trong scheduler thread khi cancellation đã được yêu cầu. Nếu scheduler dùng một thread, blocking quá lâu có thể ảnh hưởng các lần trigger khác.

Với message consumer, khi một task bị interrupt **trước khi xử lý thành công**, không được tự động ACK message nếu delivery contract yêu cầu ACK sau thành công. Tùy hệ thống, có thể cần NACK/requeue/durable retry hoặc trạng thái job riêng. Tín hiệu interruption không tự trả lại message đã ack, và code xử lý cleanup có thể cần bảo đảm idempotency.

Với Spring application event listener được đặt vào async executor, caller thường không nhận exception của listener theo cách đồng bộ. Cần quan sát lỗi, quyết định retry và tránh hứa exactly-once delivery khi chỉ có in-memory executor.

### 13.3. Spring bean singleton và ThreadLocal

Worker `@Service` mặc định là singleton; nhiều task có thể gọi chung instance. Interruption không làm mutable fields trở nên thread-safe. Ưu tiên stateless worker, immutable DTO và tránh giữ `currentJobId` hay request-specific state trên field dùng chung.

`ThreadLocal`/MDC/security context/transaction của caller không tự động được mang qua `@Async`. Nếu cần context propagation, dùng mechanism phù hợp hoặc truyền rõ ràng qua tham số, kèm cleanup. Không dùng interrupt flag như một dạng dữ liệu nghiệp vụ liên request; nó thuộc **thread hiện tại**.

## 14. Quan sát và kiểm thử hủy có kiểm soát

### 14.1. Đo các trạng thái riêng biệt

Trong hệ thống sản xuất nên phân biệt:

- **Cancellation requested**: ai yêu cầu hủy, lý do gì, deadline nào.
- **Future cancelled**: trạng thái handle mà caller thấy.
- **Worker observed cancellation**: worker đã thấy flag/ngoại lệ/token.
- **Worker stopped**: worker đã ngừng thực thi code.
- **Cleanup completed**: tài nguyên được đóng, job status được lưu.
- **Downstream side effects**: transaction, email, payment, message ACK thực sự xảy ra đến đâu.

Không gộp các trạng thái này thành `future.cancel(true) == true` rồi kết luận "mọi thứ đã dừng". Đặc biệt với công việc cần survive restart, có thể cần job store, outbox hoặc broker để lưu trạng thái hủy và retry một cách bền vững.

### 14.2. Kiểm thử không lệ thuộc Thread.sleep ngẫu nhiên

Dùng `CountDownLatch` hoặc `Phaser` để kiểm soát trạng thái:

1. Worker báo đã bắt đầu.
2. Caller gửi `interrupt` hoặc `Future.cancel(true)`.
3. Worker quan sát `InterruptedException` ở blocking point.
4. Test kiểm tra trong catch flag đã bị xóa, sau restore flag trở thành true.
5. Test kiểm tra worker **không tiếp tục** xử lý business steps tiếp theo.
6. Tách kiểm tra `Future.isCancelled()` và worker cleanup, không coi là cùng một sự kiện.
7. Luôn đặt timeout cho các bước chờ trong test và cleanup trong `finally` khi có thể.
8. Kiểm tra `cancel(false)` không được hiểu nhầm là interrupt running task.
9. Kiểm tra `CompletableFuture.cancel(true)` với contract đặc thù, tránh giả định như `FutureTask`.
10. Kiểm tra caller bị interrupt khi `get()` và logic khôi phục flag trên caller.
11. Kiểm tra exception mapping không nuốt `InterruptedException` khi bắt `Exception`.
12. Kiểm tra shutdown và retry/idempotency của job có side effects.

### 14.3. Dấu hiệu production code có vấn đề

- Log liên tục `InterruptedException` nhưng worker không kết thúc.
- Thread dump thấy worker vẫn sống sau yêu cầu shutdown, đặc biệt trong loop bắt và nuốt exception.
- Request timeout nhưng task background tiếp tục thực hiện side effect ngoài dự kiến.
- `Future.cancel(true)` trả true, song job status không chuyển hoặc downstream vẫn xử lý.
- Code dùng `Thread.interrupted()` trong helper "peek" nên làm mất flag.
- Method khôi phục flag rồi lại gọi blocking API và nhận exception ngay, tạo vòng lặp bận.
- Có `@Async` nhưng self-invocation khiến code chạy trên caller; `InterruptedException` xuất hiện ở thread không ngờ tới.
- Catch-all ghi log rồi `return null` làm workflow coi việc bị hủy là thành công.
- Bean worker đang shutdown nhưng một producer vẫn tiếp tục gửi task; rejection bị nhầm là interruption.

Khi thấy các triệu chứng này, điều tra **thread nào nhận tín hiệu, API nào ném exception, caller nào sở hữu Future, và job contract yêu cầu điều gì**.

## 15. Những lỗi suy luận thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| "interrupt() luôn giết thread ngay." | Nó là yêu cầu hợp tác, không tự kết thúc mọi công việc |
| "Bắt InterruptedException thì flag vẫn true." | Nhiều blocking API **xóa flag trước khi ném**, nên cần quyết định propagate/restore |
| "Thread.interrupted() giống isInterrupted()." | `Thread.interrupted()` đọc rồi xóa **flag của thread hiện tại** |
| "Luôn restore rồi tiếp tục while(true)." | Có thể khiến blocking API ném liên tục; thường nên dừng hoặc propagate |
| "Chỉ throw new RuntimeException(ex) là đủ." | Nếu không thể propagate checked signal, thường còn phải restore flag |
| "Luôn cần restore dù đã throws InterruptedException." | Khi truyền tiếp checked exception đúng hợp đồng, không nhất thiết restore ở tầng đó |
| "future.cancel(true) bảo đảm worker dừng." | Best-effort, implementation và hoạt động blocking/CPU quyết định |
| "CompletableFuture.cancel(true) chắc chắn interrupt." | JDK CompletableFuture **không dùng** tham số để điều khiển worker |
| "get(timeout) tự cancel job khi timeout." | Nó chỉ giới hạn thời gian caller chờ |
| "Caller get() ném InterruptedException nghĩa là worker đã bị ngắt." | Đó có thể là **caller thread** bị interrupt trong lúc đợi |
| "Future cancelled nghĩa là transaction đã rollback." | Cancellation state và transaction/side effect là các hợp đồng riêng |
| "ThreadPoolTaskExecutor tự biến mọi I/O thành interruptible." | Không; phụ thuộc API, driver và timeout của từng tầng |
| "catch (Exception) rồi log là đủ." | Có thể nuốt interrupt signal, dẫn đến shutdown không hoạt động |
| "Thread.stop() giúp hủy chắc chắn." | API không an toàn, không dùng để giải quyết task cancellation |

## 16. Checklist code review cho Spring concurrency

- [ ] Method có thể **propagate `InterruptedException`** thì không nuốt tín hiệu.
- [ ] Method không thể ném checked exception thì **restore flag và thoát**, hoặc áp dụng giao thức hủy rõ ràng.
- [ ] Không dùng `Thread.interrupted()` để **peek** vô tình xóa status.
- [ ] Không tiếp tục vòng lặp vô hạn sau khi đã restore flag mà không có lý do được tài liệu hóa.
- [ ] `Future.cancel(true)` được hiểu là **nỗ lực hủy**, không phải xác nhận worker dừng/cleanup xong.
- [ ] Không kỳ vọng `CompletableFuture.cancel(true)` tự ngắt mọi work upstream.
- [ ] Dùng timeout ở I/O và downstream, không chỉ timeout khi caller chờ.
- [ ] Phân biệt caller bị interrupt lúc `Future.get()` với worker bị interrupt trong blocking task.
- [ ] Có xử lý riêng `TimeoutException`, `ExecutionException`, `CancellationException` và rejection.
- [ ] `@Async` được gọi qua Spring-managed proxy; executor phù hợp và có giới hạn tài nguyên.
- [ ] Shutdown executor thuộc đúng thành phần sở hữu; task không tự đóng cả pool khi không có quyền.
- [ ] Có cleanup và ghi trạng thái job/ACK phù hợp nếu thao tác đã dừng giữa chừng.
- [ ] Có test hủy bằng latch, bao gồm trường hợp race giữa hoàn thành và cancel.
- [ ] Các side effects có idempotency hoặc compensation khi nghiệp vụ yêu cầu.
- [ ] Không xem interruption là cơ chế security/authorization hay tự động rollback transaction.

## 17. Câu hỏi tự kiểm tra

1. **Interruption có giết thread ngay không?** Không; nó yêu cầu hợp tác và phụ thuộc code/operation quan sát.
2. **Sau khi sleep ném `InterruptedException`, flag thường còn true không?** Không. `Thread.sleep` xóa flag khi ném exception do interrupt.
3. **Nếu method khai báo `throws InterruptedException`, thường nên làm gì?** Truyền tiếp để tầng trên xử lý, đồng thời cleanup qua finally nếu cần.
4. **Nếu `Runnable.run()` bắt `InterruptedException`, nên làm gì?** Thường restore flag, dừng task và cleanup; hoặc chuyển thành trạng thái hủy đã được thiết kế.
5. **Vì sao chỉ `catch (InterruptedException e) { }` là nguy hiểm?** Nó mất tín hiệu và có thể tiếp tục chạy sau shutdown/cancel.
6. **`Thread.interrupted()` khác `isInterrupted()` thế nào?** Method static đầu tiên đọc và xóa flag current thread; method thứ hai chỉ đọc.
7. **Nên restore rồi tiếp tục sleep trong while(true) không?** Thường không. Lần sleep kế có thể ném ngay, tạo busy loop.
8. **`cancel(true)` trên Future có bảo đảm interrupt worker không?** Không; chỉ cố gửi yêu cầu nếu implementation hỗ trợ và worker còn chạy.
9. **`CompletableFuture.cancel(true)` có bảo đảm interrupt task không?** Không. Tham số không điều khiển computation theo contract JDK.
10. **`get(timeout)` bị timeout nghĩa là job đã dừng chưa?** Chưa. Đây là timeout **đợi** của caller.
11. **Caller đang get() ném InterruptedException: phải restore flag của thread nào?** Của **caller thread** đang catch, không phải worker.
12. **Đối với CPU loop không block, làm sao phản hồi hủy?** Kiểm tra `isInterrupted()` hoặc cancellation token ở các điểm hợp lý.
13. **Một `@Async` singleton worker bị interrupt có tự rollback database không?** Không; rollback phụ thuộc transaction boundary và lỗi được truyền qua interceptor.
14. **Vì sao cần quan sát worker cleanup riêng với Future.isCancelled?** Vì Future state không chứng minh side effects đã dừng.
15. **Có nên gọi `shutdownNow()` ngay trong một @Async task bình thường không?** Không nếu task không sở hữu executor; để owner/context quản lý lifecycle.
16. **Một message handler bị interrupt giữa chừng có nên luôn ACK không?** Không; quyết định ACK/NACK dựa trên delivery contract và trạng thái xử lý.
17. **Với `Thread.interrupted()`, nếu cần giữ tín hiệu cho tầng sau thì sao?** Không gọi method chỉ để nhìn; nếu đã tiêu thụ mà contract yêu cầu propagate, restore status phù hợp.
18. **Có trường hợp chủ động tiêu thụ interruption không?** Có, khi một thành phần sở hữu protocol hủy đã xử lý đầy đủ tín hiệu và contract cho phép; không nên làm ngầm trong business task.

**Kết luận:** `InterruptedException` là **tín hiệu hợp tác** của Java khi một thread bị yêu cầu ngừng lúc đang chờ. Trong Spring concurrency, nguyên tắc an toàn là **propagate nếu có thể; nếu không, restore flag bằng `Thread.currentThread().interrupt()` và dừng hoặc báo trạng thái hủy thích hợp**. Đồng thời phân biệt việc hủy `Future` với việc worker thực sự dừng, timeout chờ với timeout công việc, và các thao tác mà interrupt không đủ để dừng.

### Tài liệu chính thức

- [Java 17 — Thread (interrupt, interrupted, isInterrupted)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Java 17 — InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html)
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1 — @Async](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
