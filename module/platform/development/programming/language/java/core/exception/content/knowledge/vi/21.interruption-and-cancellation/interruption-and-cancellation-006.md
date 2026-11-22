# Dừng xử lý và cleanup sau khi nhận tín hiệu ngắt

Trong Java, **interrupt** là tín hiệu hợp tác để yêu cầu một luồng ngừng hoặc thay đổi công việc đang làm. Nó không phải lệnh cưỡng chế giết luồng, không tự rollback giao dịch và không tự đóng tất cả tài nguyên. Khi mã nhận tín hiệu ngắt, trách nhiệm của nó thường gồm **ngừng tiếp nhận hoặc thực hiện công việc theo chính sách**, **dọn dẹp những tài nguyên mình sở hữu**, **bảo toàn trạng thái và thông tin ngắt**, rồi **kết thúc hoặc truyền tín hiệu lên tầng điều phối**.

Đây là phần quan trọng của thiết kế exception: `InterruptedException` có thể làm luồng điều khiển rời khỏi thao tác blocking bất kỳ lúc nào. Một chương trình chỉ xử lý đường thành công mà không cleanup trên đường interruption có thể rò rỉ stream/kết nối, giữ lock hoặc registration, bỏ dở cập nhật trạng thái, hay làm ứng dụng không thể shutdown đúng cách.

Bài tập trung vào Java 17+ với thread, tác vụ trong executor và các API blocking. Cách dừng cụ thể phụ thuộc hợp đồng của mỗi thư viện; không có một câu lệnh `catch (InterruptedException)` duy nhất giải quyết mọi tình huống.

## 1. Hiểu tín hiệu ngắt trước khi cleanup

Mỗi `Thread` có một **interrupted status** (cờ ngắt). Một luồng khác có thể gọi `worker.interrupt()` để yêu cầu nó lưu ý đến việc hủy/dừng. Khi đó:

- Nếu worker đang chạy mã tính toán bình thường, Java **không tự ném `InterruptedException` ở mỗi câu lệnh**. Worker phải chủ động kiểm tra trạng thái hoặc đi vào thao tác interruptible.
- Nếu worker đang chờ bằng API interruptible như `Thread.sleep`, `Object.wait`, `Thread.join`, `BlockingQueue.take`, `CountDownLatch.await`, `Future.get` hoặc `Lock.lockInterruptibly`, thao tác có thể thoát ra bằng `InterruptedException`.
- Khi những phương thức chờ thông dụng này ném `InterruptedException` vì interrupt, trạng thái interrupt của thread thường đã được **xóa** theo hợp đồng API. Muốn tầng cao hơn tiếp tục biết yêu cầu ngắt, cần truyền tiếp checked exception hoặc **phục hồi cờ** khi chuyển nó thành dạng khác.
- Với I/O hoặc thao tác thư viện không bảo đảm phản hồi interrupt, `interrupt()` có thể không khiến worker dừng ngay. Cần xét timeout, `close()`, cancellation API riêng hoặc cơ chế dừng hợp tác của thư viện đó.

`Thread.interrupt()` được gọi từ phía khác chỉ gửi yêu cầu. Quyền và nghĩa vụ xử lý yêu cầu nằm ở **mã đang thực thi và quản lý vòng đời** của worker. Khi nhận interrupt, worker có thể rời vòng lặp, cleanup và kết thúc; hoặc một API cụ thể có thể chọn tiếp tục nếu việc ngắt được tài liệu hóa là không áp dụng tại đó.

### Ba thao tác với cờ interrupt

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| `thread.interrupt()` | Đặt/yêu cầu trạng thái ngắt của thread đích, có thể khiến thao tác chờ interruptible thức dậy bằng exception | Không bảo đảm thread dừng ngay. |
| `thread.isInterrupted()` | Đọc cờ của thread đích, **không xóa** | Dùng kiểm tra trong vòng lặp hợp tác. |
| `Thread.interrupted()` | Đọc **và xóa** cờ của thread **hiện tại** | Không dùng như phép kiểm tra vô hại nếu code phía sau vẫn cần tín hiệu. |

`Thread.currentThread().interrupt()` thường dùng trong `catch (InterruptedException ex)` để **phục hồi cờ của chính luồng hiện tại** sau khi không thể truyền tiếp checked exception.

## 2. Tín hiệu ngắt và exception xảy ra ở những nơi khác nhau

Xét một worker đang chờ công việc:

```java
while (!Thread.currentThread().isInterrupted()) {
    Job job = queue.take();
    process(job);
}
```

Đây là đoạn **minh họa**, giả định `Job`, `queue` và `process` đã được định nghĩa. `queue.take()` có thể ném `InterruptedException` nên đoạn này chưa đầy đủ để biên dịch riêng. Dù điều kiện `while` kiểm tra cờ interrupt, một yêu cầu ngắt vẫn có thể đến **trong lúc `take()` đang chờ**. Vì thế vòng lặp cần xử lý đường exception:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        process(job);
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Rời vòng lặp để cleanup tài nguyên thuộc quyền sở hữu.
} finally {
    releaseOwnedResources();
}
```

Đây cũng là **mảnh minh họa**, không phải chương trình Java độc lập. `releaseOwnedResources()` cần có hợp đồng riêng về exception và quyền sở hữu.

Nếu `process(job)` có side effect và không thể dừng giữa chừng an toàn, chính sách có thể yêu cầu hoàn tất đơn vị công việc hiện tại rồi mới ngừng nhận job tiếp theo. Đừng tự ý chen một phép `interrupt` vào giữa thao tác cần tính nhất quán mà không có thiết kế rollback/idempotency.

## 3. Quy trình xử lý khi nhận interrupt

Một luồng xử lý hợp tác thường làm các bước sau:

1. **Nhận biết tín hiệu** qua `InterruptedException` hoặc kiểm tra cờ `isInterrupted()`; nhận diện đúng loại lỗi để không nhầm với exception nghiệp vụ.
2. **Chuyển sang trạng thái stopping** nếu worker có lifecycle (ví dụ ngừng lấy job mới, báo cho coordinator); tránh tiếp tục vòng lặp vô thời hạn.
3. **Dừng hoặc hoàn tất phần việc đang dang dở** theo hợp đồng. Nếu tác vụ có điểm commit, cần bảo đảm không ghi một phần không mong muốn.
4. **Cleanup tài nguyên thuộc quyền sở hữu** trong `finally`/`try-with-resources`: đóng stream/connection riêng, trả permit, unlock đúng lock, unsubscribe listener, đóng registration handle...
5. **Bảo toàn thông tin**: truyền tiếp `InterruptedException` nếu chữ ký cho phép, hoặc khôi phục interrupt flag khi chuyển nghĩa/thoát.
6. **Báo hoàn tất shutdown** cho chủ sở hữu nếu cần: latch, trạng thái lifecycle hoặc completion stage. Điều này khác với thông báo “đã gửi yêu cầu cancel”.

Các bước trên là trách nhiệm logic, không nhất thiết theo một thứ tự cứng cho mọi API. Đặc biệt, **thời điểm khôi phục cờ interrupt so với cleanup blocking** cần cân nhắc như mục 7.

Không dùng `Thread.stop()` để ép luồng dừng: API cũ này không an toàn vì có thể phá invariant và làm giải phóng monitor khi trạng thái đang bị cập nhật dở.

## 4. Try-with-resources: cleanup ngay cả khi await bị ngắt

Tài nguyên của worker nên được đóng theo một cấu trúc có bảo đảm cleanup trong đường thoát bình thường và đường exception.

Với `AutoCloseable`:

```java
try (InputStream input = Files.newInputStream(path)) {
    consume(input);
}
```

Đây là snippet minh họa, giả định `path` và `consume` đã có và `consume` phù hợp kiểu exception. `InputStream` mở bởi phạm vi này được đóng khi khối `try` thoát, bao gồm khi phần thân ném exception. Nhưng việc một tài nguyên được đưa vào `try-with-resources` có nghĩa là **phạm vi đó sẽ gọi `close()` lên nó**: chỉ làm khi có quyền sở hữu.

Trường hợp body ném `InterruptedException`:

```java
try (OwnedResource resource = openOwnedResource()) {
    awaitInterruptibly();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Đã đi qua resource.close() trước khi chạy catch này.
}
```

Đây là **mã minh họa chưa độc lập**, với `OwnedResource`, `openOwnedResource` và `awaitInterruptibly` giả định. Cấu trúc đặt `catch` **bên ngoài** khối try-with-resources có điểm hay: trình tự đóng tài nguyên của khối `try` diễn ra trước khi bắt và phục hồi interrupt. Nếu `close()` cần thực hiện một bước cleanup interruptible, nó không bị cờ interrupt vừa khôi phục ngay lập tức gây gián đoạn một cách vô ý.

Nếu `close()` tự ném exception, phải xét ngoại lệ chính và các suppressed exceptions. Đừng giả định rằng cleanup chắc chắn thành công chỉ vì đã gọi `close()`.

### Đóng theo đúng quyền sở hữu

Một parser nhận `InputStream` do caller truyền vào có thể chỉ **mượn** stream. Khi bị ngắt, parser không nên tự đóng stream của caller nếu hợp đồng không chuyển giao quyền sở hữu. Caller có thể có một `try-with-resources` ở phạm vi bao ngoài chịu trách nhiệm đóng.

Tương tự, một request sử dụng shared `HttpClient` hoặc shared database connection pool không được tùy tiện đóng toàn bộ client/pool của ứng dụng khi request bị hủy. Chỉ giải phóng những handle/tài nguyên **thuộc request đó**, theo hợp đồng API.

## 5. Ví dụ chạy độc lập Java 17: dừng worker và cleanup trước khi kết thúc

Ví dụ dùng `CountDownLatch` để kiểm soát thứ tự giữa main và worker, tránh phải dựa vào `Thread.sleep` để hy vọng worker đã bắt đầu. Worker mở resource của riêng mình, chờ trên một latch không được giải phóng và sau đó nhận interrupt từ main. Khi `await()` ném `InterruptedException`, try-with-resources đóng resource, `catch` phục hồi interrupt flag và cuối cùng worker kết thúc.

Tạo tệp `InterruptCleanupDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptCleanupDemo {

    private static final class OwnedResource implements AutoCloseable {
        private final List<String> events;
        private boolean closed;

        OwnedResource(List<String> events) {
            this.events = events;
            events.add("resource: opened");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                events.add("resource: closed");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        List<String> events = new CopyOnWriteArrayList<>();
        CountDownLatch enteredWait = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean flagRestored = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            try (OwnedResource resource = new OwnedResource(events)) {
                events.add("task: waiting");
                enteredWait.countDown();
                neverReleased.await();
                events.add("task: completed"); // Không chạy trong ví dụ.
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                flagRestored.set(Thread.currentThread().isInterrupted());
                events.add("task: interrupted");
            } finally {
                events.add("task: finished");
            }
        }, "resource-owner");

        worker.start();
        enteredWait.await();
        worker.interrupt();
        worker.join();

        events.forEach(System.out::println);
        System.out.println("main: flag restored = " + flagRestored.get());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 InterruptCleanupDemo.java
java InterruptCleanupDemo
```

Stdout:

```text
resource: opened
task: waiting
resource: closed
task: interrupted
task: finished
main: flag restored = true
```

Giải thích hành vi:

- `enteredWait.countDown()` chỉ báo worker đã tạo resource và đến vùng chờ. Main có thể gọi `interrupt()` ngay trước hoặc trong `neverReleased.await()`; cả hai trường hợp đều dẫn đến `InterruptedException` ở `await()` theo hợp đồng của latch.
- Java rời khối try-with-resources và gọi `OwnedResource.close()` **trước** khi vào `catch` bên ngoài. Dòng `resource: closed` vì thế đứng trước `task: interrupted`.
- `catch` gọi `Thread.currentThread().interrupt()` để bảo toàn yêu cầu hủy cho code phía trên trong cùng worker (nếu có), sau đó ghi nhận trạng thái interrupt đã được phục hồi. `finally` ghi nhận thoát lifecycle.
- Main `join()` để đợi worker kết thúc mới in toàn bộ nhật ký. Danh sách `CopyOnWriteArrayList` bảo đảm chia sẻ dữ liệu an toàn giữa hai thread; vì worker là tác giả duy nhất của các dòng sự kiện nên thứ tự được giữ nguyên.
- `task: completed` không xuất hiện vì latch không được giải phóng. Đó là dấu hiệu worker **dừng theo ngắt**, không phải hoàn thành tác vụ như bình thường.
- `OwnedResource.close()` của ví dụ không blocking và không ném checked exception. Trong ứng dụng thực, cleanup có thể bị lỗi hoặc mất thời gian; cần chính sách riêng.

Ví dụ sử dụng `throws InterruptedException` trong `main` vì chính main có các thao tác `await()/join()` interruptible. Đây là lỗi có thể xảy ra ở **luồng main**, tách biệt với exception mà worker vừa nhận.

## 6. Vì sao không nên nuốt InterruptedException?

Một lỗi phổ biến:

```java
try {
    queue.take();
} catch (InterruptedException ex) {
    // Bỏ qua và tiếp tục làm việc.
}
```

Đây là snippet minh họa với `queue` giả định. Sau khi `take()` ném `InterruptedException`, cờ interrupt có thể đã bị xóa. Nếu không truyền tiếp, không phục hồi và không rời công việc, caller hoặc bộ phận shutdown có thể **mất tín hiệu hủy**, khiến worker tiếp tục lấy job và hệ thống không thể dừng đúng.

Những cách xử lý thông thường:

**Truyền tiếp checked exception** khi API cho phép:

```java
public static String waitForMessage(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

Đây là phương thức có thể đặt trong class với import `java.util.concurrent.BlockingQueue`. Quyết định dừng và cleanup được giao cho caller có thông tin về lifecycle cao hơn.

**Phục hồi cờ và kết thúc** khi ở `Runnable.run()` (không khai báo checked exception):

```java
try {
    waitForMessage(queue);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return; // finally/try-with-resources bao ngoài vẫn cleanup.
}
```

Mảnh minh họa này giả định `queue` và `waitForMessage` đã có. Trả về khỏi `run()` không thể bỏ qua `finally` của các phạm vi đang hoạt động, nhưng tài nguyên phải được khai báo trong `try-with-resources` hoặc cleanup có cấu trúc.

**Chuyển thành exception của API nhưng giữ interrupt**:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationInterruptedException("Đã ngắt xử lý", ex);
}
```

`OperationInterruptedException` và `blockingOperation` là thành phần giả định của ứng dụng. Khi chuyển nghĩa, giữ `cause` để chẩn đoán; không biến tín hiệu ngắt thành `IllegalArgumentException` hay “input invalid”.

Một số framework/caller **trực tiếp trông đợi checked `InterruptedException`**. Nếu có thể truyền tiếp, không cần bọc nó chỉ vì muốn “chuẩn hóa” exception.

## 7. Cleanup có thể blocking: đặt thời điểm phục hồi cờ cho đúng

Khôi phục interrupt sớm thường là đúng sau khi bắt `InterruptedException`, nhưng hãy để ý cleanup tiếp theo có thao tác **cũng phản ứng với interrupt**.

Ví dụ nguy cơ:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} finally {
    // Nếu cleanup sử dụng phương thức interruptible, cờ đã được đặt.
    waitForCleanupAcknowledgement();
}
```

Đây là snippet minh họa, `waitForCleanupAcknowledgement` có thể ném exception hoặc nhận cờ interrupt. Nếu chờ cleanup dùng `CountDownLatch.await()`, cờ interrupt đã được phục hồi có thể khiến lệnh `await()` lập tức ném `InterruptedException` thay vì đợi thực hiện cleanup. Nếu cleanup là điều bắt buộc để bảo toàn trạng thái, thứ tự này có thể sai.

Một cách là tổ chức cleanup vào **try-with-resources nằm bên trong** và catch ở ngoài như ví dụ đầy đủ tại mục 5. Một cách khác là giữ thông tin yêu cầu ngắt trong biến cục bộ khi cần chạy cleanup blocking có giới hạn, rồi phục hồi cờ sau cleanup:

```java
boolean interrupted = false;
try {
    blockingOperation();
} catch (InterruptedException ex) {
    interrupted = true;
} finally {
    try {
        cleanupWithinDeadline();
    } catch (InterruptedException duringCleanup) {
        interrupted = true;
        // Ghi nhận việc cleanup bị ngắt; xem xét trạng thái còn lại.
    } finally {
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là đoạn **minh họa**, với `blockingOperation` và `cleanupWithinDeadline` chưa định nghĩa. Biến `interrupted` chỉ ghi nhận tín hiệu; việc không tái ném exception có phù hợp hay không phụ thuộc contract của phương thức bao ngoài. `cleanupWithinDeadline` phải thật sự có giới hạn chờ/hủy rõ ràng; không chờ vô hạn trong shutdown.

**Không được tùy tiện gọi `Thread.interrupted()` để xóa cờ** chỉ nhằm ép cleanup chạy mà không lưu và phục hồi trạng thái. Nếu dùng cơ chế xóa có chủ đích, phải hiểu ai là owner của tín hiệu hủy và không làm tầng gọi mất yêu cầu dừng.

Lưu ý thêm: nếu cleanup ném `IOException`, `RuntimeException` hoặc một exception khác, đoạn `finally` có thể tác động đến exception trước đó. Cần đọc hợp đồng và dùng cấu trúc bảo toàn lỗi (mục 9), không chỉ phục hồi interrupt flag.

## 8. Dừng vòng lặp mà vẫn giữ bất biến trạng thái

Một vòng lặp xử lý job nên có **ranh giới an toàn** để ngừng:

```java
while (!Thread.currentThread().isInterrupted()) {
    Job job = acquireNextJob();
    processOneJob(job);
}
```

Đây là mảnh minh họa thiếu định nghĩa `Job`, `acquireNextJob` và `processOneJob`. `acquireNextJob` có thể interruptible; cần catch/cleanup cho exception. Nhưng ngay cả khi không có exception, interrupt flag có thể được đặt **sau điều kiện `while`**. Nếu yêu cầu ngừng ngay trước khi lấy job mới, có thể cần kiểm tra thêm tại biên thích hợp.

Với tác vụ có trạng thái:

- Trước khi bắt đầu job mới, kiểm tra tín hiệu dừng và không nhận thêm công việc.
- Khi đang xử lý một đơn vị cần nguyên tử, chọn rollback, hoàn tất đến checkpoint an toàn hoặc ghi nhận trạng thái có thể resume.
- Trong `finally`, cleanup những tài nguyên đã thực sự được acquire. Không cleanup một tài nguyên chưa tạo thành công hoặc do thành phần khác sở hữu.
- Sau khi cleanup, báo kết quả **stopped/cancelled** riêng với **completed successfully**, nếu API cho phép caller phân biệt.

Nếu dùng lock, lưu ý:

```java
lock.lockInterruptibly();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Đoạn này minh họa với `lock` và `updateSharedState` giả định. `lock.lockInterruptibly()` nằm **trước** `try` vì nó có thể ném `InterruptedException` khi chưa acquire lock. Chỉ gọi `unlock()` khi đã acquire thành công. Nếu bao `lockInterruptibly()` vào `try` rồi `finally` luôn `unlock()`, có thể gây `IllegalMonitorStateException` khi nhận interrupt trước lúc nắm lock.

Bảo toàn trạng thái không đồng nghĩa mọi interrupt đều rollback tự động. Nếu đã gửi một request mạng hoặc đã ghi dữ liệu, ngắt việc chờ không chứng minh remote service chưa xử lý yêu cầu. Với thao tác có side effect, cần idempotency, transaction hoặc bước đối soát riêng.

## 9. Nếu vừa bị ngắt vừa lỗi trong close thì sao?

Một thao tác blocking có thể ném `InterruptedException` đúng lúc resource `close()` cũng gặp lỗi. Với try-with-resources:

- Exception của phần thân `try` là lỗi **chính**.
- Exception trong `close()` được gắn dưới dạng **suppressed exception**.
- Caller có thể truy cập qua `Throwable.getSuppressed()`.
- Nếu phần thân hoàn thành bình thường nhưng `close()` ném exception, exception lúc đóng có thể trở thành lỗi chính.

Ví dụ Java 17 chạy độc lập, cố ý ném exception trong `close()`:

Tạo `InterruptedAndCloseFailureDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.CountDownLatch;

public class InterruptedAndCloseFailureDemo {

    private static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try (FailingClose resource = new FailingClose()) {
                entered.countDown();
                neverReleased.await();
            } catch (InterruptedException ex) {
                System.out.println("primary: " + ex.getClass().getSimpleName());
                System.out.println(
                    "suppressed: " + ex.getSuppressed().length
                );
                System.out.println(
                    "cleanup: " + ex.getSuppressed()[0].getMessage()
                );
                Thread.currentThread().interrupt();
            } catch (IOException ex) {
                System.out.println("close-only: " + ex.getMessage());
            }
        }, "close-failure-worker");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 InterruptedAndCloseFailureDemo.java
java InterruptedAndCloseFailureDemo
```

Stdout:

```text
primary: InterruptedException
suppressed: 1
cleanup: close failed
```

Vì `neverReleased` không bao giờ được mở, worker rời `await()` qua `InterruptedException` sau khi main gọi `interrupt()`. `FailingClose.close()` tiếp tục ném `IOException("close failed")`. Try-with-resources bảo toàn `InterruptedException` làm exception chính, còn `IOException` trở thành một suppressed exception.

Không phải mọi exception khi đóng đều vô hại. Ví dụ với stream ghi được buffer, lỗi lúc `flush/close` có thể báo dữ liệu chưa thực sự được ghi. Cần ghi nhận và đánh giá hậu quả cleanup, không chỉ gọi `close()` rồi xem việc giải phóng là thành công.

Trong logging, giữ cả primary, cause và suppressed exceptions nếu chúng có ý nghĩa chẩn đoán. Tránh in thông điệp có thông tin nhạy cảm ra client cuối nếu lỗi bên dưới chứa đường dẫn nội bộ, token hoặc dữ liệu riêng tư.

## 10. Future.cancel(true): tín hiệu hủy và thời điểm cleanup hoàn thành

Trong `ExecutorService`, caller thường nhận `Future`. Nếu caller gọi `future.cancel(true)`, implementation có thể yêu cầu interrupt worker đang thực hiện task. Nhưng **`Future.isCancelled() == true` không chứng minh `finally` trong task đã chạy xong**.

Đây là hai mốc khác nhau:

1. **Yêu cầu/trạng thái cancellation:** Future được đánh dấu canceled; caller không còn nhận kết quả bình thường qua `get()`.
2. **Task đã ngừng và cleanup hoàn tất:** Worker thực sự đi qua các nhánh dừng, đóng tài nguyên và thoát.

Nếu caller cần đợi cleanup, phải có cơ chế chờ completion/acknowledgement riêng, hoặc hợp đồng của một abstraction cao hơn bảo đảm điều đó. `Future.get()` sau khi Future đã canceled sẽ ném `CancellationException`; nó không thay thế việc chờ tín hiệu “đã cleanup” từ task.

### Ví dụ Java 17 hoàn chỉnh: hủy rồi đợi cleanup

Tạo `CancelAndCleanupDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CancelAndCleanupDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        List<String> events = new CopyOnWriteArrayList<>();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch cleaned = new CountDownLatch(1);

        try {
            Future<?> future = executor.submit(() -> {
                try {
                    events.add("task: started");
                    started.countDown();
                    neverReleased.await();
                    events.add("task: completed");
                } catch (InterruptedException ex) {
                    events.add("task: interrupt received");
                    Thread.currentThread().interrupt();
                } finally {
                    events.add("task: cleanup");
                    cleaned.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);

            // Chờ task xác nhận đã đi qua finally;
            // chỉ kiểm tra isCancelled() là chưa đủ.
            cleaned.await();

            events.forEach(System.out::println);
            System.out.println("cancel accepted: " + accepted);
            System.out.println("future cancelled: " + future.isCancelled());
            System.out.println("cleanup confirmed: true");
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CancelAndCleanupDemo.java
java CancelAndCleanupDemo
```

Stdout:

```text
task: started
task: interrupt received
task: cleanup
cancel accepted: true
future cancelled: true
cleanup confirmed: true
```

Tại sao đầu ra xác định?

- `started.await()` bảo đảm worker đã khởi chạy trước khi main yêu cầu hủy.
- Worker đang ở trước/đang chờ `neverReleased.await()`. `cancel(true)` đối với `FutureTask` do executor chuẩn tạo sẽ yêu cầu interrupt thread của task đang thực hiện.
- `CountDownLatch.await()` phản hồi interrupt bằng `InterruptedException`; worker ghi lại, phục hồi cờ và đi vào `finally`.
- `cleaned.countDown()` là tín hiệu xác nhận cleanup của **ví dụ này** đã chạy. Main đợi `cleaned.await()` trước khi in kết quả; vì thế có thể xác nhận độc lập trạng thái Future và trạng thái cleanup.
- `neverReleased` không được giải phóng nên không có dòng `task: completed`.
- `shutdownNow()` trong `finally` là yêu cầu shutdown executor khi rời demo; trong đường thành công, task đã cleanup trước đó.

**Giới hạn cần nhớ:** một task thực dùng I/O hoặc thư viện không phản hồi interrupt có thể không bao giờ đạt đến `cleaned.countDown()`; việc đợi vô hạn là không phù hợp với nhiều đường shutdown production. Thiết kế thực nên dùng deadline cho chờ cleanup và cơ chế giám sát/escalation phù hợp. Ví dụ chỉ dùng latch interruptible của JDK nên có đường dừng được xác định rõ.

`CompletableFuture.cancel(true)` có semantics khác với `FutureTask`: `mayInterruptIfRunning` không được dùng để điều khiển interruption của một task chạy nền theo cách trên. Không lấy ví dụ `FutureTask` áp dụng máy móc cho mọi implementation `Future`.

## 11. Cleanup không bảo đảm rollback

Một nguồn nhầm lẫn khác: “Đã catch interrupt và close xong” không có nghĩa trạng thái nghiệp vụ được khôi phục như trước tác vụ.

| Việc cần làm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Dừng nhận công việc | Không tạo thêm side effect sau yêu cầu ngừng | Ngừng poll queue, ngăn đăng ký request mới. |
| Cleanup tài nguyên | Không giữ tài nguyên/registration thuộc owner | `close` stream riêng, `removeListener`, trả permit. |
| Bảo toàn invariant | Đối tượng không ở trạng thái nửa khởi tạo hoặc nửa đóng | Đặt trạng thái rõ ràng `STOPPING`/`STOPPED`, đồng bộ cập nhật. |
| Rollback/compensation | Khôi phục hoặc bù những thay đổi nghiệp vụ đã thực hiện | Transaction rollback, xóa dữ liệu tạm, thao tác bù. |
| Báo kết quả | Caller biết canceled khác với failed và completed | Future/callback/event/trạng thái job. |

Với một tác vụ gửi thanh toán, interrupt khi chờ response HTTP **không chứng minh** server chưa xử lý thanh toán. Không tự retry hay rollback giả nếu thiếu thông tin idempotency hoặc khả năng kiểm tra trạng thái.

Với ghi file, `close()` có thể flush dữ liệu đã đẩy vào buffer nhưng không làm thao tác ghi trở lại trạng thái ban đầu. Nếu cần cập nhật nguyên tử file, có thể ghi vào tệp tạm, flush/sync phù hợp và chuyển đổi có bảo đảm phù hợp với filesystem; quyết định này thuộc thiết kế tính nhất quán, không do interrupt tự mang lại.

## 12. Cleanup đúng thứ tự và không đóng tài nguyên của người khác

Một worker có thể đồng thời giữ:
- File stream do chính nó mở.
- Permit của semaphore đã acquire thành công.
- Connection đã checkout từ pool.
- Listener registration handle đã tạo.
- Reference đến shared executor hoặc shared HTTP client.

Tại đường interruption:

1. Dọn resources thuộc phạm vi của worker theo thứ tự phù hợp với dependency. Try-with-resources đóng nhiều tài nguyên theo thứ tự **ngược thứ tự khai báo**.
2. Chỉ giải phóng permit/lock sau khi **acquire thành công**. Ví dụ `Semaphore.acquire()` có thể ném `InterruptedException` trước khi nhận permit; `finally { semaphore.release(); }` vô điều kiện sẽ làm sai số permit.
3. Chỉ `unlock()` khi thread thực sự nắm lock. Với `lock.lockInterruptibly()`, một interrupt trước acquisition không cho phép gọi `unlock()`.
4. Chỉ hủy subscription mà worker sở hữu. Hủy registration chung có thể làm subscriber khác mất sự kiện.
5. Không shutdown shared executor/pool chỉ vì một request/caller bị ngắt, trừ khi worker đó thực sự quản lý lifecycle của thành phần chia sẻ.

Ví dụ minh họa xử lý permit:

```java
boolean acquired = false;
try {
    semaphore.acquire();
    acquired = true;
    doWork();
} finally {
    if (acquired) {
        semaphore.release();
    }
}
```

Đây là snippet chưa độc lập; `semaphore` và `doWork` giả định được khai báo, và phương thức phải xử lý/khai báo `InterruptedException`. Biến `acquired` bảo đảm không release permit chưa sở hữu nếu bị ngắt trong lúc chờ `acquire()`.

Với `Lock`:

```java
lock.lockInterruptibly();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Snippet này minh họa rằng `unlock()` chỉ được cài sau điểm acquire thành công, không gọi bừa khi `lockInterruptibly()` bị ngắt trước khi nắm lock.

## 13. Khởi tạo một phần và nhiều thao tác cleanup

Nếu quá trình khởi tạo acquires A, rồi B, sau đó gặp interrupt trước khi acquire C, chỉ A/B cần cleanup. Sai lầm phổ biến là viết code tạo tài nguyên ở ngoài `try` rồi chỉ cleanup khi mọi bước tạo hoàn tất.

Với `AutoCloseable`, cấu trúc:

```java
try (Resource first = openFirst();
     Resource second = openSecond(first)) {
    runInterruptibleOperation(second);
}
```

là snippet minh họa. Nếu `openSecond` ném exception hoặc nhận interrupt, Java đóng `first` đã tạo thành công. Nếu cả hai được tạo, Java đóng `second` rồi `first` khi thoát.

Nhưng nếu `openSecond` **tạo được một phần tài nguyên bên trong rồi ném trước khi trả object**, caller chưa nhận object để đóng. Chính implementation của `openSecond` phải cleanup tài nguyên nội bộ đã acquire.

Với nhiều registration/listener, tương tự: lưu handle ngay khi subscribe thành công; nếu subscribe tiếp theo thất bại, hủy các handle đã tạo. Lúc gặp interrupt, cleanup không được bỏ sót những registration đã thành công trước đó.

Nếu cleanup nhiều tài nguyên thủ công, đừng để lỗi từ resource A ngăn việc đóng resource B còn độc lập; dùng try-with-resources khi phù hợp hoặc cấu trúc thu thập lỗi cleanup để vẫn cố đóng các tài nguyên còn lại.

## 14. Interrupt trong ExecutorService.shutdown và awaitTermination

Một owner của executor thường có các bước:
- Dừng nhận job mới bằng `shutdown()`.
- Đợi job đang thực hiện kết thúc bằng `awaitTermination(timeout, unit)`.
- Nếu quá thời hạn và chính sách cho phép, yêu cầu hủy công việc còn lại qua `shutdownNow()` hoặc cancel handles.
- Đảm bảo task tự cleanup và ghi nhận job nào hoàn thành/chưa hoàn thành.

`shutdown()` **không chờ** các task kết thúc; `shutdownNow()` là nỗ lực dừng task đang chạy bằng interrupt và trả danh sách job chưa bắt đầu, không bảo đảm task đã dừng. `awaitTermination(...)` có thể ném `InterruptedException` nếu **luồng điều phối shutdown** bị ngắt khi chờ. Điều đó không đồng nghĩa mọi worker đã lỗi.

Mẫu sau là **mảnh minh họa** cho một component thật sự sở hữu executor:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Ở đây owner chọn chính sách: nếu người điều phối shutdown bị ngắt, yêu cầu workers dừng và phục hồi interrupt flag của chính coordinator. Không sao chép chính sách này vào code chỉ **mượn** executor do framework quản lý.

Tài nguyên của task vẫn phải cleanup gần task. Owner executor có thể giám sát/quy định deadline, nhưng không nên dựa vào `shutdownNow()` như bảo đảm mọi `finally` đã thực thi. Với công việc quan trọng, cần một kênh xác nhận tác vụ thực sự đã dừng hoặc cơ chế shutdown có timeout và xử lý tình trạng không đáp ứng.

## 15. Khi interrupt đến trong lúc chính cleanup đang diễn ra

Cleanup có thể bao gồm close socket, flush buffer, chờ callback dừng, dừng producer hoặc trả kết nối. Một số thao tác blocking sẽ nhận thêm interrupt. Chính sách cần trả lời:

- Cleanup tối thiểu nào **phải cố hoàn tất** để không rò rỉ tài nguyên hoặc giữ invariant sai?
- Cleanup nào có thể bỏ qua hoặc thực hiện bất đồng bộ sau khi yêu cầu dừng?
- Có deadline không? Nếu cleanup vẫn không xong, ai nhận cảnh báo/escalation?
- Có cần bảo lưu cả exception của công việc chính lẫn exception trong cleanup?
- Sau khi cleanup thất bại, thành phần nên là `FAILED` hay `STOPPED_WITH_ERRORS` thay vì tuyên bố dừng sạch?

Đừng dùng vòng lặp:

```java
while (true) {
    try {
        waitUntilClean();
        break;
    } catch (InterruptedException ignored) {
        // Bỏ qua vô hạn.
    }
}
```

Đây là snippet minh họa cách làm **không nên áp dụng**: nó có thể chờ mãi, che tín hiệu shutdown và gây deadlock khi component khác chờ thread kết thúc. Nếu bắt buộc cleanup có chờ, dùng deadline/giới hạn, giữ thông tin interrupt và có đường thoát có ý nghĩa.

Không có bảo đảm JVM luôn chạy `finally` trong mọi tình huống: tiến trình có thể bị cưỡng chế dừng, JVM crash hoặc tài nguyên ở tầng hệ điều hành bị mất. Phần mềm yêu cầu độ bền cao cần thêm recovery khi khởi động lại, transaction hoặc lease có hạn.

## 16. Phân biệt ngắt ở worker và ngắt ở caller

Đối với `ExecutorService.submit`, worker có thể ném `InterruptedException` ra khỏi `Callable.call()`; task hoàn thành exceptionally và `Future.get()` ở caller nhận **`ExecutionException` với cause là `InterruptedException`**. Caller không vì thế tự bị ngắt.

Ngược lại, nếu **caller** bị ngắt khi chờ `future.get()`, nó nhận `InterruptedException` trực tiếp. Task có thể tiếp tục chạy bình thường.

| Vị trí ngắt | Cách quan sát | Nghĩa vụ cleanup |
| --- | --- | --- |
| Worker bị ngắt khi xử lý | Worker catch/truyền exception, hoặc Future chứa thất bại | Worker cleanup tài nguyên do worker sở hữu. |
| Caller bị ngắt khi `Future.get()` | `InterruptedException` ở caller | Caller cleanup tài nguyên do caller sở hữu; có thể quyết định cancel task nếu là owner. |
| `get(timeout)` chỉ hết hạn chờ | `TimeoutException` của waiter | Không mặc nhiên bắt worker cleanup; policy có thể tiếp tục chờ hoặc yêu cầu cancel. |
| `Future.cancel(true)` được chấp nhận | Future có trạng thái canceled, worker có thể bị interrupt | Worker vẫn phải hợp tác và cleanup; caller muốn biết cleanup xong cần cơ chế riêng. |

Không gọi `Thread.currentThread().interrupt()` trên caller **chỉ vì** `ExecutionException.getCause() instanceof InterruptedException`. Interrupt status thuộc **thread hiện tại**, không phải một “biến toàn cục đại diện cho lỗi task”.

## 17. Checklist kiểm thử interruption và cleanup

Test dùng `CountDownLatch` để điều khiển trạng thái thay vì chỉ `Thread.sleep(10)` rồi hy vọng worker đang chờ.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Thread được interrupt trước khi vào thao tác blocking | Blocking API nhận cờ interrupt và worker vẫn đi qua cleanup đúng. |
| Thread bị interrupt trong khi `await/take/sleep` | `InterruptedException` được xử lý, worker ngừng theo contract. |
| Tài nguyên mở thành công trước khi bị ngắt | `close()` của tài nguyên thuộc owner được gọi. |
| Interrupt trong khi acquisition thứ hai | Resource đầu tiên đã mở được đóng; tài nguyên chưa acquire không bị release sai. |
| Cleanup cũng ném exception | Exception chính và suppressed exception được giữ để chẩn đoán. |
| Task sở hữu permit/lock | Chỉ release/unlock khi acquisition thành công. |
| `Future.cancel(true)` trả kết quả | Không nhầm Future canceled với task cleanup complete. |
| Caller đợi `get()` bị ngắt | Kiểm tra chính caller có thể truyền tiếp/khôi phục cờ; task không tự động bị gán thất bại. |
| Task xử lý dữ liệu có side effect | Invariant, transaction/compensation và idempotency đáp ứng hợp đồng. |
| Cleanup không phản hồi interrupt | Hệ thống có deadline, metrics và chính sách escalation, không treo vô hạn ngoài ý muốn. |

Các test nên xác nhận **trạng thái quan sát được**: resource closed, subscription removed, permit không rò rỉ, worker không nhận job mới, acknowledgment đã phát. Không cần so khớp chính xác stack trace hoặc phụ thuộc vào timing tình cờ nếu hợp đồng không hứa thứ tự đó.

## 18. Những lỗi thường gặp và cách sửa

**Nuốt `InterruptedException` rồi tiếp tục vòng lặp.** Cờ có thể đã bị xóa, tín hiệu ngắt bị mất. Truyền tiếp, hoặc phục hồi cờ và kết thúc có chủ đích.

**Gọi `Thread.interrupted()` để kiểm tra rồi vô tình xóa cờ.** Dùng `isInterrupted()` khi chỉ cần đọc; chỉ clear khi có lý do và phải giữ/khôi phục tín hiệu nếu contract yêu cầu.

**Phục hồi cờ trước cleanup blocking mà không xem xét hậu quả.** Lệnh chờ trong cleanup có thể nhận interrupt ngay lập tức. Tổ chức cleanup trước catch ở ngoài try-with-resources, hoặc hoãn restoration có kiểm soát rồi phục hồi đúng lúc.

**Đặt `close()` chỉ ở cuối happy path.** Exception hoặc `return` sớm khiến cleanup bị bỏ qua. Dùng try-with-resources hoặc `finally` có cấu trúc.

**Đóng tài nguyên được mượn.** Quyền sở hữu không phải tên biến; không đóng shared pool/client/stream của caller ngoài hợp đồng.

**Release permit hoặc unlock khi acquire chưa thành công.** Nếu `Semaphore.acquire` hoặc `Lock.lockInterruptibly` bị ngắt trước acquisition, thao tác release/unlock vô điều kiện sẽ gây sai trạng thái.

**Coi cancel thành công là cleanup hoàn tất.** `cancel(true)` chỉ yêu cầu/đánh dấu cancellation theo implementation. Dùng completion/ack riêng nếu cần đợi xác nhận.

**Retry ngay khi bị ngắt.** Lý do interruption có thể là shutdown; retry có thể chống lại chính sách hủy, tạo side effect trùng và trì hoãn dừng.

**Nuốt lỗi `close()` hoặc để nó che exception chính.** Cần giữ primary/cause/suppressed và có chính sách khi dọn dẹp thất bại.

**Dùng `Thread.stop()` hay cưỡng bức thread theo cách làm hỏng invariant.** Thiết kế cooperative cancellation, timeout và điểm dừng an toàn.

**Dùng một kiểu trạng thái cho completed, failed và cancelled.** Caller cần phân biệt kết quả thành công, lỗi nghiệp vụ và kết thúc do hủy để quyết định đúng.

## 19. Bài tập tự kiểm tra

**Câu 1.** Worker chạy `queue.take()`, được gọi `interrupt()` rồi bắt `InterruptedException`. Nếu method không thể khai báo checked exception, có nên để catch rỗng?

**Trả lời:** Không. Thông thường cần phục hồi `Thread.currentThread().interrupt()` và kết thúc/đi vào nhánh dừng; cleanup tài nguyên thuộc owner theo cấu trúc phù hợp.

**Câu 2.** Code nhận `InterruptedException` rồi gọi `Thread.currentThread().interrupt()` trước khi cleanup bằng `latch.await()`. Điều gì có thể xảy ra?

**Trả lời:** `await()` có thể ném `InterruptedException` ngay vì cờ interrupt đã đặt. Nếu cần cleanup blocking có giới hạn, cân nhắc tổ chức cleanup trước điểm restoration hoặc lưu tín hiệu rồi khôi phục sau.

**Câu 3.** Worker được cấp connection bởi pool, và caller dùng shared executor. Khi bị ngắt, worker có nên `executor.shutdownNow()` và `pool.close()` không?

**Trả lời:** Không nếu worker chỉ mượn cả executor và pool. Worker trả connection/đóng handle do mình checkout theo hợp đồng; lifecycle executor/pool thuộc owner chung.

**Câu 4.** `Future.cancel(true)` trả `true` và `future.isCancelled()` trả `true`. Có khẳng định được `finally` của task đã chạy xong không?

**Trả lời:** Không. Task có thể còn đang phản hồi interrupt hoặc làm cleanup. Muốn biết xong phải dựa vào một tín hiệu/abstraction hoàn tất riêng.

**Câu 5.** Worker đang giữ một permit semaphore khi bị ngắt; một worker khác bị ngắt ngay tại `semaphore.acquire()` trước khi có permit. Hai worker có giống nhau về cleanup không?

**Trả lời:** Không. Chỉ worker đã acquire mới được release permit. Dùng cấu trúc đảm bảo biến trạng thái acquisition hoặc đặt `try/finally` sau điểm acquire thành công.

**Câu 6.** Body ném `InterruptedException`, `AutoCloseable.close` ném `IOException`. Try-with-resources làm gì?

**Trả lời:** `InterruptedException` từ body là primary; `IOException` từ close bị suppressed. Caller có thể đọc `getSuppressed()` để chẩn đoán cả hai, rồi phục hồi/lan truyền tín hiệu ngắt theo contract.

## 20. Ghi nhớ để áp dụng

Nhận interrupt nghĩa là ứng dụng được yêu cầu **hợp tác chuyển sang trạng thái dừng phù hợp**. Đối với code sở hữu tài nguyên, hãy đặt cleanup vào phạm vi được bảo đảm bởi `try-with-resources` hoặc `finally`, rời vòng lặp ở điểm an toàn, giữ thông tin interruption và phân biệt yêu cầu cancel với việc thực sự hoàn tất cleanup.

Quy tắc kiểm tra nhanh: **Ai sở hữu tài nguyên? Khi interrupt đến, tác vụ dừng ở đâu? Cleanup có chạy cả đường exception không? Cờ interrupt và lỗi cleanup có được bảo toàn không? Caller biết khi nào dừng xong bằng cách nào?** Trả lời rõ năm câu hỏi ấy giúp giảm rò rỉ tài nguyên, giữ invariant và làm shutdown có thể kiểm chứng.