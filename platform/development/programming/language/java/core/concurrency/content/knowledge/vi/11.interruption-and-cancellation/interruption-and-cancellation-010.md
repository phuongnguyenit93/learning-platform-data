# Đảm bảo finally đóng tài nguyên khi dừng tác vụ trong Java

Một tác vụ Java có thể kết thúc bình thường, ném exception, nhận yêu cầu hủy, bị interrupt giữa lúc chờ hoặc bị timeout ở thread gọi. Trong mọi trường hợp **tác vụ còn có cơ hội thực thi cleanup**, programmer cần đóng các tài nguyên mà nó sở hữu: stream, socket, file handle, lock, transaction/session tự quản, worker phụ và các đối tượng có vòng đời hữu hạn. Công cụ căn bản là khối **`try/finally`** và **`try-with-resources`**.

Tuy nhiên, **`Future.cancel(true)` không phải thao tác giết thread**, và `finally` **không hứa sẽ chạy trong mọi kiểu sự cố** như process bị kill, JVM halt, máy mất điện hoặc thread bị mắc kẹt không thể tiến tới điểm thoát. Muốn cleanup đáng tin cậy, phải thiết kế **cancellation có hợp tác**, điểm chờ có khả năng phản hồi, quyền sở hữu tài nguyên rõ ràng, giới hạn thời gian, báo lỗi và kiểm thử các đường kết thúc.

Bài này nói về **Java concurrency nói chung**, sử dụng các API trong JDK và Java 17+. Các cơ chế concurrency riêng của Spring được dành cho chương khác.

## 1. Ba việc khác nhau: yêu cầu hủy, dừng tác vụ, đóng tài nguyên

| Khái niệm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Cancellation request** | Một bên đề nghị tác vụ dừng | `future.cancel(true)`, `thread.interrupt()` |
| **Task termination** | Mã tác vụ thực sự không còn chạy | Method `run()`/`call()` đã return hoặc ném exception |
| **Resource cleanup** | Thả resource mà tác vụ sở hữu | `close()`, `unlock()`, đóng socket, thu hồi handle |
| **Executor termination** | Executor không còn task chạy và hoàn tất vòng đời | `awaitTermination(...)` trả true |

Ba sự kiện **không đồng nhất**. `cancel(true)` có thể làm `Future` chuyển sang trạng thái cancelled trước khi worker hoàn thành cleanup. Một task không phản hồi interruption vẫn có thể chạy. `shutdownNow()` cũng chỉ **cố** interrupt tasks đang chạy và trả danh sách tasks chưa được bắt đầu; nó không bảo đảm mọi resource đã đóng.

Mục tiêu thiết kế là: sau khi request hủy được gửi, worker **nhận tín hiệu**, rời khỏi vòng nghiệp vụ, đi qua `finally` hoặc `try-with-resources`, đóng tài nguyên rồi thông báo **đã hoàn tất cleanup** cho bên điều phối.

### Quy tắc phân quyền sở hữu

**Ai sở hữu resource thì chịu trách nhiệm đóng resource đúng lúc.** Nếu worker mở file stream riêng trong method, thường worker phải đóng. Nếu worker chỉ **mượn** một shared client/queue do ứng dụng quản lý, worker **không** được tự ý đóng khi bị hủy, vì các task khác còn sử dụng nó.

## 2. `try/finally`: cleanup khi rời vùng bảo vệ

Mẫu cơ bản:

```java
Resource resource = acquire();
try {
    use(resource);
} finally {
    release(resource);
}
```

Đây là **snippet**; `Resource`, `acquire`, `use` và `release` là các tên minh họa. Nếu `acquire()` hoàn tất thành công và chương trình đã vào `try`, khối `finally` được thực thi khi dòng điều khiển rời `try` theo những đường Java thông thường: hoàn thành, `return`, exception, hoặc `InterruptedException` được ném ra từ một lời gọi blocking.

**Không viết theo kiểu sau:**

```java
Resource resource = acquire();
use(resource);
release(resource); // Bị bỏ qua nếu use() ném exception.
```

Trong code có cancellation, khả năng gặp exception thường tăng vì `sleep`/`wait`/`join`/`BlockingQueue.take` có thể ném `InterruptedException`. Nếu đặt `close` ở cuối code mà không có `finally`, đường hủy có thể bỏ qua cleanup.

### Nhưng `finally` không phải phép màu

`finally` không được bảo đảm hoàn thành khi:

- JVM/process bị kill cứng, `Runtime.halt`, crash, mất điện.
- Code bị mắc kẹt mãi bên trong vùng `try` vì vòng lặp không có điểm thoát hoặc API chặn vô hạn không phản hồi interrupt.
- Thread bị ngừng thô bạo bằng cơ chế không an toàn, hoặc ứng dụng không còn cơ hội chạy mã cleanup.
- Chính `close()` bị treo, hỏng hoặc ném exception; mã cleanup tiếp theo có thể không chạy nếu không tổ chức phù hợp.

**Phạm vi “đảm bảo” thực tế:** khi **luồng điều khiển Java trở về qua stack bình thường** và JVM còn thực thi, `finally` được chạy theo semantics ngôn ngữ. Để cleanup trước một deadline hoặc trước khi process kết thúc, cần thêm hợp đồng/điều phối lifecycle ngoài `finally`.

## 3. `try-with-resources` là lựa chọn mặc định cho `AutoCloseable`

Java `try-with-resources` tự gọi `close()` cho resource khai báo trong header khi rời khối, kể cả khi body ném exception:

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

Đây là snippet, cần import `java.io.InputStream` và `java.nio.file.Files`, `path` là một `Path` hợp lệ, `process` là method của chương trình. `InputStream` implements `AutoCloseable`. `try-with-resources` giúp tránh quên close và có xử lý **suppressed exceptions** khi cả body lẫn close đều lỗi.

Một số quy tắc:

- Resource cần implements `AutoCloseable` (hoặc `Closeable`).
- Các resource trong header được đóng theo **thứ tự ngược** lúc khai báo.
- Nếu khai báo resource thứ hai bị lỗi, các resource đã tạo trước đó vẫn được đóng theo semantics `try-with-resources`.
- `close()` vẫn có thể ném exception hoặc chặn; ngôn ngữ không cam kết close luôn thành công hay đáp ứng timeout.
- Tạo resource **trước** rồi dùng try-with-resources với biến final/effectively final có thể đúng cú pháp từ Java 9, nhưng cần xác định rõ **ai thực sự sở hữu** nó. Đừng tự đóng shared resource chỉ vì biến có thể đưa vào header.

**Ưu tiên `try-with-resources`** khi resource có phạm vi lexical rõ: file stream, reader/writer, socket do task tạo, tài nguyên tùy chỉnh implements `AutoCloseable`.

## 4. `InterruptedException`: tín hiệu hủy, không phải yêu cầu nuốt lỗi

Nhiều blocking methods của JDK phản hồi interrupt bằng `InterruptedException`, ví dụ `Thread.sleep()`, `Object.wait()`, `Thread.join()`, `BlockingQueue.take()` và `CountDownLatch.await()`.

Nếu một worker đã có cơ hội dừng, mẫu phù hợp:

```java
try {
    while (true) {
        WorkItem item = queue.take();
        process(item);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Thoát method; finally/try-with-resources sẽ cleanup.
} finally {
    cleanupOwnedResources();
}
```

Đây là **snippet**, với `WorkItem`, `queue`, `process` và `cleanupOwnedResources` được định nghĩa ở nơi khác. Vì `InterruptedException` thường **xóa interrupt flag khi được ném**, ta gọi `Thread.currentThread().interrupt()` nếu bắt exception mà **không ném tiếp**, để caller/lifecycle code còn biết thread đã bị yêu cầu ngắt. Sau đó phải **rời vòng công việc** để cleanup, không tiếp tục như thể không có tín hiệu.

**Nếu method có thể khai báo `throws InterruptedException`**, thường đơn giản nhất là **cho exception lan ra** và đặt cleanup trong `finally`/`try-with-resources`. Không cần restore flag ngay trước khi rethrow nếu policy là để caller xử lý interruption; điều quan trọng là **không nuốt tín hiệu**.

### Phản ví dụ: bắt rồi chạy tiếp

```java
while (true) {
    try {
        doBlockingWork();
    } catch (InterruptedException ignored) {
        // BUG: nuốt tín hiệu, vòng lặp tiếp tục.
    }
}
```

Đây là snippet sai. Một `Future.cancel(true)` có thể được gửi, nhưng worker vẫn chạy mãi, làm `finally` bên ngoài vòng không có cơ hội thực thi. Nếu tác vụ cần hỗ trợ hủy, hãy thoát vòng hoặc chuyển trạng thái một cách có chủ đích.

## 5. Ví dụ Java 17 chạy được: interrupt dẫn tới đóng resource

Chương trình dùng một resource `AutoCloseable` nhỏ, một thread đợi trên `CountDownLatch` chưa bao giờ được mở và main gửi interrupt sau khi thread đã bắt đầu. Worker bắt `InterruptedException`, restore interrupt flag và tự thoát; Java gọi `close()` khi rời try-with-resources. Main chỉ in sau khi `join` hoàn tất nên stdout xác định.

Tạo tệp **`FinallyOnInterrupt.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FinallyOnInterrupt {
    static final class TrackedResource implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public void close() {
            closed.set(true);
        }

        boolean isClosed() {
            return closed.get();
        }
    }

    public static void main(String[] args) throws Exception {
        TrackedResource resource = new TrackedResource();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverOpened = new CountDownLatch(1);
        AtomicBoolean interruptRestored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try (resource) {
                started.countDown();
                neverOpened.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                interruptRestored.set(
                        Thread.currentThread().isInterrupted());
            }
        }, "worker");

        worker.start();
        if (!started.await(5, TimeUnit.SECONDS)) {
            worker.interrupt();
            throw new IllegalStateException("Worker not started");
        }

        worker.interrupt();
        worker.join(5_000);
        if (worker.isAlive()) {
            throw new IllegalStateException("Worker did not finish");
        }

        System.out.println("resourceClosed=" + resource.isClosed());
        System.out.println("interruptRestored=" + interruptRestored.get());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac FinallyOnInterrupt.java
java FinallyOnInterrupt
```

Stdout **khi thread chạy và kết thúc trong deadline**:

```text
resourceClosed=true
interruptRestored=true
```

**Giải thích từng bước:**

1. `resource` được gắn với try-with-resources của worker; object này theo contract bài học thuộc quyền sở hữu của worker, dù main giữ reference chỉ để kiểm tra sau `join`.
2. Worker gọi `started.countDown()` rồi chờ ở `neverOpened.await()`.
3. Main chỉ interrupt sau khi biết worker đã đi vào phần `try`. Nếu interrupt đến trước khi `await` thực sự chờ, `await` vẫn phản hồi bằng exception khi kiểm tra interrupt; nếu interrupt đến trong lúc chờ, nó được đánh thức.
4. Worker bắt `InterruptedException`, khôi phục cờ interrupt và ghi nhận kết quả.
5. **Try-with-resources đóng resource khi thoát vùng `try`, trước khi vào nhánh catch của chính `try`.**
6. `worker.join()` bảo đảm main đọc kết quả sau khi worker đã hoàn thành.

Tác vụ trên không dùng `Thread.stop()`; nó dừng bằng **cooperative interruption**, cho phép cleanup chạy trên đường Java thông thường.

**Giới hạn:** ví dụ chỉ chứng minh resource mẫu được đóng trên đường hủy này. Nó không chứng minh rằng mọi loại I/O hay native call đều phản hồi interrupt; khi thay `neverOpened.await()` bằng I/O khác, phải đọc đúng contract.

## 6. `finally` với mutex: luôn nhả khóa đã lấy thành công

`ReentrantLock` không tự được JVM nhả theo scope. Vì vậy sau khi `lock()` hoặc `lockInterruptibly()` thành công, phải đặt `unlock()` trong `finally`:

```java
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

Đây là snippet; `lock` là `ReentrantLock` hoặc `Lock` và `updateState` là logic được bảo vệ.

### Chú ý vị trí của `lockInterruptibly()`

```java
lock.lockInterruptibly(); // Có thể throw trước khi lấy khóa.
try {
    updateState();
} finally {
    lock.unlock(); // Chỉ chạy khi acquisition đã thành công.
}
```

Snippet này nằm trong method `throws InterruptedException`. **Đừng** đặt `unlock()` vào finally chạy ngay cả khi `lockInterruptibly()` ném exception trước khi lấy khóa. Với `ReentrantLock`, unlock khi không phải owner ném `IllegalMonitorStateException` và có thể che lỗi gốc.

Với intrinsic monitor, `synchronized(lock)` tự nhả monitor khi thoát block, kể cả exception. Nhưng **nhả mutex không đồng nghĩa đóng file/socket** đã được tạo bên trong; resource có vòng đời riêng vẫn cần try-with-resources hoặc finally.

### `Semaphore`, permit và ownership

Nếu đã `semaphore.acquire()` thành công, cần `release()` trong finally. Nhưng nếu `acquire()` bị interrupt **trước khi thành công**, không được release như thể đã sở hữu permit, nếu không sẽ làm tăng số permit sai:

```java
semaphore.acquire();
try {
    useLimitedResource();
} finally {
    semaphore.release();
}
```

Đây là snippet trong method có `throws InterruptedException`. `semaphore`/`useLimitedResource` được định nghĩa ngoài đoạn. Đặc biệt không dùng một finally bao trùm cả acquisition thất bại để luôn release vô điều kiện.

## 7. Hủy `Future`: cancelled không đồng nghĩa cleanup đã xong

`Future.cancel(true)` **yêu cầu** hủy. Với tác vụ đang chạy, implementation như `FutureTask` có thể gọi interrupt lên thread đang chạy. Nhưng:

- Nếu task chưa bắt đầu và cancellation được chấp nhận, task có thể **không chạy**, nên `finally` bên trong task cũng **không chạy**. Tài nguyên cấp phát bên ngoài task vẫn cần owner ngoài xử lý.
- Nếu task đang chạy, cờ cancelled của `Future` có thể được công bố **trước khi code worker thoát khỏi finally**. Đừng dùng `future.isDone()` hay `isCancelled()` làm bằng chứng rằng close hoàn tất.
- Nếu worker bỏ qua interrupt hoặc bị chặn trong API không hỗ trợ hủy, cancellation có thể không làm worker dừng sớm.
- `Future.get()` trên Future đã cancelled thường ném `CancellationException`; nó **không chờ** resource cleanup theo cách bạn có thể mặc định. Cần handshake riêng hoặc chờ executor thực sự terminate.
- `cancel(false)` không gửi interrupt tới task đang chạy; việc dừng còn tùy task và trạng thái scheduling.
- Khi `cancel(true)` trả false, task có thể đã hoàn tất hoặc cancellation không được chấp nhận; phải phân tích kết quả theo contract, không tự đoán.

### Mẫu điều phối hai giai đoạn

**Giai đoạn 1:** gửi request hủy (cancel/interrupt). **Giai đoạn 2:** chờ tín hiệu **worker rời khỏi finally** hoặc chờ executor termination, rồi mới tuyên bố các resource thuộc worker đã đóng.

Nếu chỉ đợi `future.get()` và bắt `CancellationException`, bạn đang quan sát **trạng thái Future**, không nhất thiết là **trạng thái cleanup hoàn tất**.

## 8. Java 17: phân biệt `Future.cancel(true)` và worker đã cleanup

Ví dụ sau có `CountDownLatch finished` được đếm xuống trong **finally ngoài cùng**, sau khi try-with-resources đã đóng resource. Main chỉ in khi đã thấy `finished`, nên không chạy đua với cleanup.

Tạo tệp **`FutureCancelCleanup.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelCleanup {
    static final class TrackedResource implements AutoCloseable {
        private final AtomicBoolean closed;

        TrackedResource(AtomicBoolean closed) {
            this.closed = closed;
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicBoolean closed = new AtomicBoolean(false);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        CountDownLatch neverOpened = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> future = pool.submit(() -> {
                try {
                    try (TrackedResource resource =
                                 new TrackedResource(closed)) {
                        started.countDown();
                        neverOpened.await();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task not started");
            }

            boolean accepted = future.cancel(true);
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Cleanup not completed");
            }

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + future.isCancelled());
            System.out.println("resourceClosed=" + closed.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FutureCancelCleanup.java
java FutureCancelCleanup
```

Stdout khi chương trình hoàn thành bình thường:

```text
cancelAccepted=true
futureCancelled=true
resourceClosed=true
```

**Vì sao test không dựa vào timing may rủi?**

- Worker được submit và chạy trong executor một thread.
- Main chờ `started`, chứng minh worker đã tạo resource và đến checkpoint trong task.
- Worker sau đó chờ `neverOpened.await()`; interruption làm `await` ném `InterruptedException`, kể cả khi interrupt đến ngay trước khi nó thực sự đợi.
- `future.cancel(true)` yêu cầu interrupt worker. Khi worker thoát, try-with-resources đóng resource trước, rồi finally ngoài cùng đếm `finished`.
- Main **chờ `finished` trước khi in**, thay vì thấy `future.isCancelled()` rồi suy luận close đã kết thúc.

**Có một giới hạn đặc biệt:** nếu worker lỗi trước khi đi vào try-with-resources hoặc bị hủy trước khi chạy, không thể dựa vào `finished` trong body sẽ chạy. Trong chương trình này `started` đã được xác nhận nên ta biết task đang hoạt động và đã cấp phát resource. Trong hệ thống thực tế, thiết kế lifecycle phải quản lý cả trạng thái **queued / never started / running / completed**.

**Timeout không cưỡng chế close:** nếu `finished.await(5s)` trả false, main báo lỗi; worker có thể vẫn đang chặn trong một operation không phản hồi interrupt. `shutdownNow()` cố gửi interrupt nhưng không thể bảo đảm giải phóng I/O native hoặc resource ngoại vi.

## 9. `ExecutorService.shutdown()` và `shutdownNow()` không thay cleanup của task

Một executor được shutdown đúng cách giúp không bỏ mặc workers:

```java
pool.shutdown();
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            reportStuckWorkers();
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là **snippet**, `pool` là `ExecutorService` và `reportStuckWorkers()` là method ứng dụng. Ý nghĩa:

1. `shutdown()` không nhận tasks mới, nhưng cho tasks đã nhận cơ hội hoàn thành bình thường.
2. `awaitTermination` đợi một thời lượng giới hạn để executor thực sự kết thúc.
3. Nếu quá thời hạn, `shutdownNow()` cố interrupt tasks đang chạy và trả danh sách tasks chưa bắt đầu.
4. Đợi lần hai để biết worker có thật sự thoát hay không.
5. Nếu chính thread điều phối bị interrupt, nó cố yêu cầu hủy, **khôi phục cờ interrupt** rồi kết thúc đường chờ.

**Điều bắt buộc phải phân biệt:** `shutdownNow()` không đóng hộ mọi resource của task và cũng không cam kết tất cả thread dừng ngay. Nếu có tasks chưa bao giờ chạy, `finally` trong task không được thực thi; những resource chuẩn bị từ trước phải có một owner khác đóng. Với resource chia sẻ, lifetime thường gắn với application/executor owner, không gắn từng task.

## 10. Tài nguyên được mở ở đâu quyết định ai phải đóng

### 10.1. Task mở resource riêng

```java
void runTask(Path path) throws IOException {
    try (InputStream in = Files.newInputStream(path)) {
        readFully(in);
    }
}
```

Snippet cần import `IOException`, `InputStream`, `Files`, `Path` và method `readFully`. Nếu worker tạo input stream cho riêng job đó thì nên đóng ngay trong phạm vi job.

### 10.2. Resource được ứng dụng chia sẻ

```java
void runTask(SharedClient client) {
    client.sendOneRequest();
    // Không đóng client; owner ứng dụng quản lý vòng đời.
}
```

`SharedClient` là type minh họa, không phải class có sẵn của JDK. Task **không sở hữu** resource, nên cancellation của một job không được làm gián đoạn các job khác bằng cách đóng shared client.

### 10.3. Resource được tạo trước khi submit

```java
Resource resource = openResource();
Future<?> f = pool.submit(() -> use(resource));
```

Hai dòng này là snippet có tên minh họa. Nếu `f.cancel(true)` xảy ra **trước khi task bắt đầu**, lambda có thể không chạy, và `finally` đặt **bên trong lambda** không bao giờ có cơ hội đóng `resource`. Hãy thiết kế **ownership transfer rõ ràng**:

- Tốt nhất: mở resource **bên trong task** và dùng try-with-resources, nếu không cần mở trước.
- Nếu buộc mở trước: người tạo giữ trách nhiệm đóng khi task không được nhận/chưa bắt đầu, hoặc dùng một owner object quản lý trạng thái, việc bàn giao quyền sở hữu và đóng đúng một lần.
- Khi nhiều actor có thể cùng cố close, cần chính sách close idempotent/ownership protocol; đừng dựa vào may mắn để tránh double-close.

### 10.4. Task có nhiều resource

```java
try (Reader reader = Files.newBufferedReader(source);
     Writer writer = Files.newBufferedWriter(target)) {
    copy(reader, writer);
}
```

Đây là snippet, cần import `Reader`, `Writer`, `Files`, `Path` và có `source`, `target`, `copy`. Resource được đóng **ngược thứ tự khai báo**: `writer` rồi `reader`. Nếu một close ném lỗi, Java vẫn cố close các resource còn lại theo semantics try-with-resources.

**Không mở resource đắt hoặc có side effect trong constructor rồi giao cho worker mà không nghĩ tới task bị từ chối/hủy trước khi chạy.**

## 11. `close()` có thể thất bại: đừng che exception gốc

Một lỗi tinh vi xảy ra khi body ném exception và `finally` cũng ném exception trong lúc close:

```java
try {
    doWork();
} finally {
    resource.close(); // Nếu close ném, exception gốc có thể bị che.
}
```

Đây là snippet, giả định `doWork`/`resource` đã được định nghĩa. Với `try-with-resources`, nếu **body** ném exception và `close` cũng ném exception, Java giữ exception chính của body và thêm lỗi close vào danh sách **suppressed exceptions**.

### Java 17: minh họa suppressed exception

Tạo **`SuppressedCleanupDemo.java`**:

```java
import java.io.IOException;

public class SuppressedCleanupDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource r = new FailingResource()) {
            throw new IOException("work failed");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            System.out.println(
                    "suppressed=" + e.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac SuppressedCleanupDemo.java
java SuppressedCleanupDemo
```

Stdout chính xác:

```text
primary=work failed
suppressed=close failed
```

**Bài học:** nếu phần việc thất bại và cả thao tác đóng cũng thất bại, cả hai lỗi đều quan trọng. Khi logging, ghi nhận suppressed exceptions (`Throwable.getSuppressed()`) thay vì chỉ in message exception chính.

Đối với cleanup nhiều bước thủ công, nếu bước đầu `close` ném exception, các bước sau có thể bị bỏ qua. Cần thiết kế `finally` lồng, try-with-resources, hoặc thu thập các lỗi close sao cho **mọi resource có cơ hội được giải phóng**. Không ném `return` trong finally vì nó có thể **che exception hoặc kết quả** của phần thân.

## 12. Đóng tài nguyên không phải lúc nào cũng làm I/O dừng ngay

Một số blocking operations phản hồi interruption (ví dụ `BlockingQueue.take`, `CountDownLatch.await`). Nhưng không được suy diễn rằng **mọi blocking I/O** cũng phản hồi `Thread.interrupt()` theo cùng cách.

- **NIO interruptible channels**: hành vi với interrupt/close được mô tả bởi contract của loại channel; một thao tác đang chặn có thể bị kết thúc bằng exception phù hợp khi channel bị interrupt/đóng.
- **`java.net.Socket`/stream I/O**: behavior phụ thuộc API, runtime, timeout và platform. Nên đọc contract và đặt `Socket.setSoTimeout(...)` ở những nơi có ý nghĩa; `Thread.interrupt` không phải nút universal để chấm dứt mọi loại socket read.
- **Một lời gọi native hoặc thư viện ngoài** có thể không kiểm tra interrupt và tiếp tục chặn.
- **`AutoCloseable.close()` có thể chặn** trong quá trình flush, handshake, ghi data hoặc chờ trạng thái khác; không mặc nhiên có deadline.
- **Shutdown hook** cũng không phải nơi bảo đảm cleanup nếu process bị kill cứng hoặc hook bị treo; tránh dựa vào hook làm giao thức duy nhất bảo vệ dữ liệu quan trọng.

Nếu cần hủy I/O đáng tin, thiết kế **timeout ở đúng API**, khả năng đóng channel/socket từ bên quản lý phù hợp với contract, hoặc dùng API có cancellation rõ ràng. Không dùng `Thread.stop()` để buộc thoát — dừng bất ngờ có thể phá invariants và gây corruption.

## 13. Resource cleanup có thể tự cần interrupt policy

Sau khi worker bị interrupt, thread vẫn có interrupt flag bật (nếu đã restore). Nếu `close()` của resource lại dùng một blocking operation phản hồi interrupt, **cleanup có thể bị cắt ngắn**.

Có ba nguyên tắc cần cân nhắc:

1. **Ưu tiên cleanup không blocking và idempotent** khi thiết kế resource wrapper tự quản.
2. Nếu cleanup buộc chặn, định nghĩa **deadline**, fallback, logging và nghĩa vụ của owner; không chỉ gọi close rồi hy vọng hoàn tất.
3. Nếu một implementation cần **tạm hoãn interruption để cleanup**, chỉ điều khiển interrupt flag một cách có chủ đích và **khôi phục trạng thái** sau đó; không xóa interrupt flag vô tình.

Không có một pattern duy nhất đúng cho mọi `close()`. Với file stream đóng nhanh và không ném checked exception, try-with-resources rất rõ. Với network connection có shutdown handshake phức tạp, phải đọc contract và thiết kế vòng đời ngoài task; thậm chí lựa chọn “abort ngay” thay vì “flush/commit mọi thứ” có thể là một quyết định nghiệp vụ.

### Vì sao không swallow exception trong close?

```java
finally {
    try {
        resource.close();
    } catch (Exception ignored) {
        // Sai nếu cần biết resource đóng thất bại.
    }
}
```

Đoạn snippet này bỏ hết thông tin lỗi cleanup. Nếu lỗi close không thể propagate vì cần giữ exception nghiệp vụ chính, ít nhất phải **ghi nhận/attach suppressed exception** hoặc báo trạng thái cleanup không thành công. Tránh log spam khi shutdown nhưng cũng không làm hệ thống báo “đã đóng” khi resource vẫn còn.

## 14. Đảm bảo cleanup cả khi task lỗi không do interrupt

Một worker không chỉ chết vì `InterruptedException`. Có thể ném `IOException`, `RuntimeException`, timeout riêng, validation exception, hoặc trả sớm do điều kiện nghiệp vụ. Vì thế **đặt cleanup tại vùng có cùng ownership** là nguyên tắc vững hơn việc thêm `close()` vào từng nhánh `catch`.

Ví dụ tốt:

```java
try (Resource r = open()) {
    if (skipThisTask()) {
        return;
    }
    doWork(r);
}
```

Đây là snippet; resource được đóng ngay cả trên đường `return` bình thường. Nếu phải đóng nhiều resource thủ công mà chúng không implements `AutoCloseable`, dùng `try/finally` quanh từng acquisition thành công, và sắp xếp thứ tự giải phóng rõ ràng.

**Tránh gọi một callback không tin cậy khi giữ mutex hoặc đang close resource** nếu callback có thể block, reenter, lấy khóa theo thứ tự ngược hoặc ném exception làm ngắt cleanup. Khi có thể, chụp immutable event/snapshot trước rồi callback ngoài critical section theo một giao thức thông báo riêng.

## 15. Cấp phát và đóng tài nguyên đúng thứ tự

Một chu trình an toàn thường là:

1. **Acquire**: lấy resource; nếu acquisition thất bại, chỉ cleanup những phần đã lấy được thành công.
2. **Register ownership**: đảm bảo từ lúc acquisition thành công đã có một scope/owner có trách nhiệm close.
3. **Execute**: thực hiện công việc; có cancellation points, timeout và state kiểm soát.
4. **Cancel**: khi có request hủy, dừng việc nhận thêm công việc và giúp task thoát khỏi các điểm chờ hỗ trợ interrupt.
5. **Cleanup**: chạy `finally`/`try-with-resources`; xử lý lỗi close, cố giải phóng mọi resource liên quan.
6. **Signal completion**: sau khi cleanup thực sự xong, phát tín hiệu `CountDownLatch`/state completion theo happens-before phù hợp.
7. **Coordinator verifies**: chỉ báo "đã đóng" khi có bằng chứng đã hoàn tất, hoặc công khai timeout/cleanup failure.

### Lưu ý về quyền sở hữu của `ThreadLocal`

Một `ThreadLocal` có thể giữ mutable resource trên thread pool worker. Nếu mỗi task `set` nhưng không `remove` ở finally, state có thể còn tồn tại trên **thread tái sử dụng** và rò rỉ sang task khác. Mẫu:

```java
try {
    context.set(taskContext);
    doWork();
} finally {
    context.remove();
}
```

Đây là snippet, `context` là `ThreadLocal<?>` thích hợp và `taskContext` thuộc task. `remove` giải phóng binding của thread đối với value; **không tự gọi `close()` cho object value** nếu nó implements AutoCloseable. Nếu value sở hữu tài nguyên thật, phải có close riêng theo ownership.

## 16. Kiểm thử tình huống hủy: cần có chứng cứ cleanup

### Nhóm tình huống tối thiểu

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Tác vụ return bình thường | `close()` được gọi theo scope |
| Body ném exception | `close()` vẫn được gọi, lỗi gốc không bị bỏ qua |
| Blocking wait ném `InterruptedException` | Worker thoát, cleanup được thực thi |
| `future.cancel(true)` khi task đang chạy | Không coi cancelled Future là bằng chứng cleanup đã xong |
| Hủy task **trước khi bắt đầu** | Resource ngoài task có owner đóng thay |
| Close ném exception | Lỗi cleanup được báo/giữ suppressed phù hợp |
| Task không phản hồi interrupt | Coordinator timeout, không khẳng định resource đã đóng |
| Executor shutdown | Không còn task running trước khi đóng resource dùng chung |
| Nhiều resource, một close lỗi | Các resource còn lại vẫn có cơ hội đóng |
| Shared resource được task mượn | Hủy một task không đóng resource của cả ứng dụng |

### Dùng handshake thay vì `Thread.sleep`

Để test chắc chắn hủy **khi worker đã bắt đầu**, dùng `CountDownLatch started`; để biết đã cleanup, dùng `CountDownLatch finished` trong `finally` sau các bước close. Đừng `sleep(20)` rồi giả định worker đang chờ đúng vị trí; scheduling không có cam kết đó.

### Chỉ assert sau khi cleanup thực sự hoàn tất

Một test chỉ kiểm tra:

```java
future.cancel(true);
assert future.isCancelled();
```

là **chưa đủ** để chứng minh resource đã đóng. `assert` của Java còn có thể bị vô hiệu nếu không bật `-ea`. Nên dùng assertion của test framework hoặc explicit `AssertionError` và một sự kiện `finished`/executor termination có nghĩa đúng với đời sống resource.

## 17. Những lỗi phổ biến

| Ngộ nhận hoặc sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “`cancel(true)` giết ngay worker” | Worker có thể tiếp tục chạy | Cooperative cancellation + timeout |
| “`isCancelled()` nghĩa là close xong” | Cleanup có thể còn đang chạy | Chờ `finished` hoặc termination thực |
| “`finally` luôn chạy kể cả JVM bị kill” | Không có bảo đảm như vậy | Recovery/idempotency ngoài process |
| Bắt `InterruptedException` rồi bỏ qua | Worker không bao giờ rời vòng, finally chưa chạy | Propagate hoặc restore + exit |
| Đặt close sau body không có finally | Exception/return bỏ qua close | Try-with-resources/finally |
| Đóng shared client khi một task bị hủy | Phá các task khác | Xác định resource owner |
| Cấp phát resource trước submit, chỉ close trong task | Hủy trước start làm resource rò rỉ | Owner bên ngoài hoặc tạo trong task |
| `unlock()` khi chưa acquire thành công | Exception mới, sai lock ownership | Chỉ finally sau successful acquire |
| `semaphore.release()` khi acquire thất bại | Tăng sai số permit | Release chỉ sau successful acquire |
| `close()` ném làm che exception gốc | Mất nguyên nhân failure | Try-with-resources, suppressed exceptions |
| Nhiều close trong một finally, close đầu ném | Resource sau có thể không được đóng | TWR hoặc tách catch/lồng finally |
| Tuyên bố mọi I/O đều bị interrupt | Worker có thể vẫn block | API-specific cancel/timeout/close |
| Dùng `Thread.stop()` để ép cleanup | Nguy cơ phá invariant/corruption | Hủy hợp tác |
| Dùng `sleep` để test thời điểm cleanup | Flaky test | Latch/handshake |
| Quên `ThreadLocal.remove()` | State task rò trên thread pool | Cleanup per-task trong finally |
| Suppress hoàn toàn close errors | Báo sai rằng shutdown đã thành công | Ghi nhận và báo trạng thái |

## 18. Checklist thiết kế production

- **Tài nguyên nào task sở hữu độc quyền?** Cái nào chỉ được mượn từ owner ứng dụng?
- Resource được cấp phát **trước hay sau khi task được lên lịch**? Nếu không được chạy thì ai đóng?
- Có **try-with-resources** với `AutoCloseable`? Nếu không, mỗi successful acquisition có đúng finally không?
- Blocking operations có **hỗ trợ interrupt**? Nếu không, có API close/cancel/timeout riêng không?
- Khi bắt `InterruptedException`, code có **thoát** hoặc propagate? Có restore flag khi catch và không rethrow?
- Nếu `close()` ném exception hoặc chặn, có kế hoạch giữ lỗi gốc, log và deadline?
- Sau `future.cancel(true)`, coordinator có **đợi cleanup thực sự** trước khi giải phóng resource dùng chung?
- `ExecutorService.shutdownNow()` có được xem là **request** hủy chứ không phải completion guarantee?
- Các resource mở trước khi task bắt đầu có được owner khác quản lý khi task bị cancelled/never started?
- Nếu có nhiều resource, có đóng theo thứ tự thích hợp và xử lý lỗi của từng close không?
- Trong task có `ThreadLocal` hoặc callback/reference cần giải phóng không?
- Test đã bao phủ **normal return, exception, interrupt, cancel-before-start, cancel-while-running, close failure và shutdown timeout**?
- Nếu process crash trước cleanup, trạng thái nghiệp vụ có cơ chế **recovery/idempotency/lease/transaction** phù hợp không?

## 19. Câu hỏi tự kiểm tra

**1. `Future.cancel(true)` trả true có đảm bảo file đã đóng không?** Không. Nó cho biết cancellation được chấp nhận theo contract, không chứng minh worker đã đi qua finally.

**2. Worker catch `InterruptedException` rồi tiếp tục vòng vô hạn, finally bên ngoài có chạy không?** Chỉ khi worker thật sự rời vùng try; nuốt interrupt có thể khiến nó không thoát, nên cleanup không được thực hiện đúng lúc.

**3. Khi nào dùng try-with-resources thay cho try/finally?** Khi tài nguyên implements `AutoCloseable` và ownership có thể diễn đạt bằng scope rõ ràng; TWR còn xử lý suppressed exception khi cả body và close lỗi.

**4. Một task chưa từng được chạy có thể thực hiện finally trong task không?** Không. Resource mở trước submit phải có owner khác khi task bị hủy trước lúc bắt đầu.

**5. Có nên gọi `unlock` nếu `lockInterruptibly` bị interrupt trước khi acquire?** Không. Lúc đó caller không sở hữu lock.

**6. `shutdownNow()` có cam kết mọi worker dừng không?** Không. Nó cố interrupt task đang chạy; task không phản hồi có thể vẫn hoạt động.

**7. Có thể rely vào `System.exit`/kill để finally chạy không?** Không. Phải thiết kế recovery khi process dừng bất thường.

**8. Tại sao exception của `close()` không nên che exception của body?** Vì lỗi nghiệp vụ gốc cần được giữ; try-with-resources giữ nó làm primary và lỗi close ở suppressed list.

**9. Tại sao đóng shared client trong finally của từng task là sai?** Resource thuộc owner khác và có thể còn được sử dụng bởi các task cùng ứng dụng.

**10. Nếu interrupt flag đang bật khi cleanup dùng blocking API, có nguy cơ gì?** Cleanup có thể bị interrupt ngay hoặc thất bại sớm theo contract; cần policy cleanup và bảo toàn trạng thái hủy.

**11. Muốn test task đã đóng tài nguyên, có đủ nếu `future.isDone()` là true?** Không, nhất là với cancelled Future. Cần xác minh dấu hiệu hoàn tất cleanup hoặc executor termination thật.

**12. Vì sao `ThreadLocal.remove()` nên nằm trong finally?** Thread pool tái sử dụng thread; binding cũ có thể tồn tại qua nhiều task nếu không remove, gây rò trạng thái và tài nguyên gián tiếp.

## 20. Kết luận

**`finally` và `try-with-resources` là hàng rào cleanup trên đường thực thi Java bình thường, không phải lệnh cưỡng chế kết thúc tác vụ.** Muốn đóng tài nguyên đáng tin khi hủy, phải kết hợp:

1. **Ownership rõ ràng** (ai mở, ai đóng, tài nguyên per-task hay shared).
2. **Cooperative interruption** (tác vụ kiểm tra tín hiệu, thoát khỏi blocking points và không nuốt `InterruptedException`).
3. **Cleanup theo scope** (try-with-resources hoặc finally quanh mọi resource đã cấp phát thành công).
4. **Completion handshake** (không nhầm Future cancelled với worker đã close xong).
5. **Failure handling** (suppressed close errors, timeout, API I/O-specific cancellation và recovery sau crash).

Đặt đúng các yếu tố này sẽ khiến đường dừng tác vụ **dự đoán được, dễ kiểm thử và ít rò rỉ resource**, mà không phải dùng cơ chế dừng thread thô bạo.