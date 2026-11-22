# Điểm chặn hỗ trợ và không hỗ trợ interrupt trong Java

## 1. Vì sao phân biệt các điểm chặn lại quan trọng?

Một thread có thể **bị chặn (blocked/waiting)** khi đợi monitor, lock, dữ liệu queue, tín hiệu từ thread khác, I/O hoặc thời gian trôi qua. Khi hệ thống muốn dừng công việc—chẳng hạn hủy task hoặc đóng ứng dụng—thường dùng `Thread.interrupt()`. Nhưng **không phải điểm chặn nào cũng phản ứng giống nhau với interrupt**.

Có ba nhóm chính:

1. **Điểm chặn interruptible:** thao tác đang chờ có thể thoát bằng `InterruptedException`, ví dụ `Thread.sleep()`, `Object.wait()`, `Thread.join()`, `BlockingQueue.take()`, `CountDownLatch.await()`, `ReentrantLock.lockInterruptibly()`.
2. **Điểm chặn không hủy việc đợi chỉ vì interrupt:** ví dụ thread chờ vào `synchronized` monitor, hoặc `ReentrantLock.lock()`. Interrupt **không cưỡng ép** nhả lock đang do thread khác giữ. Thread có thể tiếp tục phải đợi cho đến khi lock khả dụng.
3. **Điểm chặn có cách phản ứng riêng:** `LockSupport.park()` có thể trở về do interrupt nhưng **không ném `InterruptedException` và không tự xóa cờ**; I/O qua `InterruptibleChannel` có thể đóng channel và ném `ClosedByInterruptException`.

**Thông điệp cốt lõi:** `interrupt()` là một **yêu cầu hợp tác**, không phải `Thread.stop()`, không ép thread khác chấm dứt và không tự động giải phóng mọi tài nguyên mà thread đang giữ. Việc hủy có hiệu quả hay không phụ thuộc thao tác đang chờ, trạng thái interrupt và code của ứng dụng.

Bài này chỉ bàn **Java concurrency nói chung** trên JDK/Java 17+, không phụ thuộc framework.

## 2. Interrupt flag và các API cơ bản

Mỗi thread có **interrupt status** (cờ ngắt). Thread khác có thể gọi:

```java
worker.interrupt();
```

Đây là snippet: `worker` là tham chiếu `Thread` đã được khai báo. Hành động này yêu cầu thread worker chú ý đến interrupt; **không bảo đảm worker dừng ngay**, không làm nó tự phát sinh một exception tại mọi điểm thực thi.

Các API quan trọng:

| API | Tác dụng |
| --- | --- |
| `target.interrupt()` | Gửi tín hiệu interrupt tới thread đích |
| `target.isInterrupted()` | Đọc interrupt status của thread đích, **không xóa cờ** |
| `Thread.currentThread().isInterrupted()` | Đọc cờ của thread hiện tại, **không xóa cờ** |
| `Thread.interrupted()` | Static method đọc **và xóa** interrupt status của **thread hiện tại** |
| `InterruptedException` | Tín hiệu do nhiều thao tác chờ interruptible ném; **thông thường cờ đã được xóa khi ngoại lệ được ném** |

**Không nhầm hai cách kiểm tra:**

```java
boolean keepFlag = Thread.currentThread().isInterrupted();
boolean consumeFlag = Thread.interrupted();
```

Đây là snippet minh họa. `isInterrupted()` giữ nguyên cờ; `Thread.interrupted()` xóa cờ, nên gọi nó vô tình trong vòng lặp có thể khiến lần kiểm tra kế tiếp không còn thấy yêu cầu hủy.

Đối với các thao tác chờ ném `InterruptedException` như `sleep`/`wait`/`join`, khi bắt exception thường cần **truyền tiếp** hoặc **khôi phục cờ** bằng `Thread.currentThread().interrupt()` nếu không thể truyền tiếp. Không phục hồi cờ một cách máy móc trong mọi tình huống: tầng gọi có thể đã chuyển tín hiệu thành trạng thái hủy cuối cùng và không tiếp tục dùng thread. Quan trọng là phải có **hợp đồng xử lý interrupt rõ ràng** và không âm thầm nuốt yêu cầu hủy.

## 3. Bảng phân loại các điểm chặn thường gặp trong JDK

| Điểm chặn / API | Interrupt khi đang đợi | Cần chú ý |
| --- | --- | --- |
| `Thread.sleep(...)` | **Có**: ném `InterruptedException` | Không nhả monitor đang giữ; cờ thường bị xóa khi ném |
| `Object.wait(...)` | **Có**: ném `InterruptedException` | Nhả monitor được wait trong lúc đợi, lấy lại monitor trước khi trở về/ném |
| `Thread.join(...)` | **Có**: ném `InterruptedException` | Ngắt **thread đang join**, không tự ngắt worker được join |
| `BlockingQueue.put()/take()` | **Có** | Chờ dữ liệu/dung lượng; các timed `offer/poll` cũng interruptible |
| `CountDownLatch.await(...)` | **Có** | Timeout `await(timeout)` trả boolean, interrupt là ngoại lệ khác |
| `CyclicBarrier.await(...)` | **Có** | Barrier có thể chuyển sang broken state khi một waiter bị interrupt |
| `Semaphore.acquire(...)` | **Có** | `tryAcquire(timeout, unit)` cũng interruptible |
| `Semaphore.acquireUninterruptibly()` | **Không thoát do interrupt** | Tiếp tục đợi permit; khôi phục interrupt status theo hợp đồng khi hoàn tất |
| `ReentrantLock.lockInterruptibly()` | **Có** | Có thể dừng chờ **trước khi sở hữu khóa** |
| `ReentrantLock.tryLock(timeout, unit)` | **Có** | Trả false khi timeout; ném `InterruptedException` khi bị ngắt |
| `ReentrantLock.lock()` | **Không hủy việc đợi bằng interrupt** | Vẫn đợi lấy khóa; bảo toàn trạng thái interrupt theo hợp đồng |
| `synchronized (monitor)` khi monitor do thread khác giữ | **Không**: không có `InterruptedException` | Thread vẫn phải đợi monitor; cờ interrupt có thể vẫn được đặt |
| `Condition.await()/awaitNanos(...)` | **Có** | Nhả lock liên kết khi chờ; lấy lại lock trước khi tiếp tục |
| `Condition.awaitUninterruptibly()` | **Không thoát vì interrupt** | Vẫn đợi predicate/signal, bảo toàn dấu hiệu interrupt |
| `Future.get()/get(timeout, unit)` | **Có** | TimeoutException là kết quả khác với InterruptedException |
| `CompletableFuture.get(...)` | **Có** | `get()` có thể ném `InterruptedException` |
| `CompletableFuture.join()` | **Không ném `InterruptedException`** | Có thể chờ bất chấp interrupt và bảo toàn cờ; không nhầm với `Thread.join()` |
| `ExecutorService.awaitTermination(...)` | **Có** | Hết hạn trả false; interrupt là đường khác |
| `LockSupport.park()/parkNanos(...)` | **Phản ứng riêng**: có thể trở về khi interrupt | Không tự xóa cờ, không ném `InterruptedException`; có thể trở về không có signal |
| `InterruptibleChannel` đang thực hiện blocking I/O | **Có theo hợp đồng channel** | Có thể đóng channel và ném `ClosedByInterruptException` |
| `Selector.select(...)` | **Có thể đánh thức việc select** | Không phải InterruptedException; interrupt có tác dụng đánh thức selector và trạng thái cờ vẫn cần xử lý |
| Vòng tính toán CPU không kiểm tra cờ | **Không tự dừng** | Phải kiểm tra interrupt hợp tác hoặc dùng cơ chế hủy khác |
| `InputStream.read()` / legacy socket I/O nói chung | **Phụ thuộc implementation và đối tượng I/O** | Không hứa mọi blocking I/O đều interruptible; xem hợp đồng của lớp cụ thể |

**Quan trọng:** cùng một tên “blocking” không đồng nghĩa cùng ngữ nghĩa interrupt. Đọc **chữ ký API và hợp đồng**; một số thao tác thoát bằng `InterruptedException`, một số chặn không ngắt được, một số trả về hoặc ném ngoại lệ I/O riêng.

## 4. Java 17+: `Thread.sleep` phản hồi interrupt và cờ bị xóa

Tạo tệp `InterruptSleepDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class InterruptSleepDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                Thread.sleep(60_000);
                System.out.println("Normal sleep completion");
            } catch (InterruptedException e) {
                System.out.println("Flag in catch: "
                        + Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("Flag restored: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "sleeper");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("Main done");
    }
}
```

Biên dịch và chạy:

```bash
javac InterruptSleepDemo.java
java InterruptSleepDemo
```

Đầu ra trong lần chạy bình thường, không có ngắt ngoài:

```text
Flag in catch: false
Flag restored: true
Main done
```

Lời gọi `started.countDown()` diễn ra trước khi worker vào `sleep`, và `main` gửi `interrupt` sau khi latch mở. Nếu interrupt đến **trước** khi worker thật sự gọi `sleep`, lần sleep kế tiếp vẫn thấy cờ đã đặt và ném `InterruptedException`. Nếu worker đã ngủ, interrupt đánh thức nó. Cả hai trường hợp đều dẫn đến catch; sleep dài chỉ để worker không tự hoàn tất trước khi main gửi interrupt.

`Thread.sleep` khi bị interrupt ném `InterruptedException` và xóa interrupt status theo hợp đồng. Ví dụ **chủ động khôi phục cờ**, để tầng gọi có thể thấy thread đã nhận yêu cầu hủy. Trong ứng dụng thật, worker thường nên thoát một cách có kiểm soát thay vì tiếp tục công việc lớn sau khi bắt interrupt.

**Đừng đặt `sleep` trong `synchronized` rồi nghĩ nó nhả monitor.** Sleep không giải phóng khóa đã giữ, dù nó có thể bị interrupt.

## 5. Điểm chặn không hỗ trợ hủy việc chờ: lấy intrinsic monitor

Điều khác biệt dễ mắc lỗi là **chờ đi vào `synchronized` không interruptible**. Nếu monitor đang bị thread A giữ, thread B cố vào khối `synchronized (monitor)` có thể ở trạng thái JVM `BLOCKED`. Gọi `B.interrupt()` không làm B tự ném `InterruptedException` để bỏ việc lấy monitor.

### Java 17+: interrupt không làm thread bỏ chờ monitor

Tạo file `MonitorWaitInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorWaitInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch attempted = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            attempted.countDown();
            synchronized (monitor) {
                System.out.println("Entered after interrupt: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "monitor-worker");

        synchronized (monitor) {
            worker.start();
            attempted.await();
            worker.interrupt();
            // Main vẫn giữ monitor đến khi ra khỏi synchronized.
        }

        worker.join();
        System.out.println("Main done");
    }
}
```

Chạy:

```bash
javac MonitorWaitInterruptDemo.java
java MonitorWaitInterruptDemo
```

Đầu ra:

```text
Entered after interrupt: true
Main done
```

**Giải thích:**

1. Main giữ `monitor` trước khi khởi động worker.
2. Worker báo đã tới bước sắp yêu cầu monitor bằng `attempted.countDown()`.
3. Main gửi interrupt trong khi **vẫn đang giữ monitor**, nên worker không thể vào khối `synchronized` ngay cả nếu đã chạy đến dòng đó.
4. Khi main nhả monitor, worker lấy được nó và chạy vào khối. Cờ interrupt đã đặt vẫn còn để worker kiểm tra bằng `isInterrupted()`.
5. Worker không ném `InterruptedException` chỉ vì đang chờ monitor; chương trình không có lệnh catch quanh acquisition.

Có thể kiểm tra `Thread.getState()` khi thread thực sự đang chờ monitor để thấy `BLOCKED`, nhưng `getState()` chỉ là **snapshot**, không nên dùng để điều phối hoặc kiểm thử dựa vào timing.

### Phân biệt với `Object.wait()`

Cùng là intrinsic monitor nhưng **`Object.wait()` có thể bị interrupt**:

- Để gọi `monitor.wait()`, thread phải **đang giữ** monitor đó.
- Khi bắt đầu wait, thread **nhả monitor của object được wait**, cho phép thread khác vào sửa điều kiện và `notify/notifyAll`.
- Khi được đánh thức hoặc bị interrupt, thread phải **lấy lại monitor** theo hợp đồng wait trước khi trở về hoặc ném `InterruptedException`.
- Nếu một thread khác giữ monitor quá lâu, thread đang bị interrupt vẫn có thể phải **chờ lấy lại monitor** trước khi catch chạy. Vì thế interrupt không tạo cam kết về độ trễ đáp ứng tức thời.

Khi đợi một điều kiện, luôn dùng `while (!condition) monitor.wait()`, không chỉ `if`, vì có **spurious wakeup** và trạng thái có thể thay đổi trước khi thread giành lại monitor.

## 6. Điểm chặn hỗ trợ interrupt khi lấy khóa: `lockInterruptibly()`

`ReentrantLock.lock()` là thao tác chờ khóa nhưng **không phải interruptible acquisition**. Nếu khóa đang bị giữ, interrupt không khiến `lock()` tự thất bại để thoát. Nếu yêu cầu **có thể hủy trong lúc chờ khóa**, dùng `lockInterruptibly()` hoặc `tryLock(timeout, unit)`.

### Java 17+: dừng chờ trước khi chiếm ReentrantLock

Tạo file `InterruptibleLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempted = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            boolean acquired = false;
            try {
                attempted.countDown();
                lock.lockInterruptibly();
                acquired = true;
                System.out.println("Unexpected lock acquisition");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Interrupted while waiting for lock");
            } finally {
                if (acquired) {
                    lock.unlock();
                }
            }
        }, "lock-worker");

        lock.lock();
        try {
            worker.start();
            attempted.await();
            worker.interrupt();
            worker.join(); // Worker có đường thoát do interrupt.
        } finally {
            lock.unlock();
        }

        System.out.println("Main released lock");
    }
}
```

Chạy:

```bash
javac InterruptibleLockDemo.java
java InterruptibleLockDemo
```

Đầu ra nếu không có interrupt ngoài:

```text
Interrupted while waiting for lock
Main released lock
```

Main giữ `lock` cho đến khi worker kết thúc. Worker không thể lấy lock, nhưng `lockInterruptibly()` kiểm tra interrupt và ném `InterruptedException`. Nếu interrupt đến trước khi worker gọi `lockInterruptibly()`, API cũng nhận biết interrupt status. Vì worker thoát việc đợi, main có thể `join` dù vẫn giữ khóa.

Mẫu này được sắp xếp để chứng minh **khả năng hủy chờ khóa**. Nó không phải khuyến nghị thường xuyên `join` worker trong khi giữ lock. Với `lock()` thường, cấu trúc main giữ lock rồi join worker đợi lock có thể deadlock.

**Điểm phải giữ:** chỉ gọi `unlock()` nếu worker thực sự acquire thành công. `lockInterruptibly()` thất bại bằng exception thì worker **không có quyền unlock**. Nếu code muốn thử trong một khoảng giới hạn, dùng `tryLock(timeout, unit)` và kiểm tra `boolean acquired`.

### `ReentrantLock.lock()` không interruptible thì cờ có mất không?

`ReentrantLock.lock()` vẫn chờ đến khi lấy được khóa, kể cả nếu bị interrupt trong lúc chờ; API duy trì interrupt status theo hợp đồng. Sau khi lấy khóa, code có thể chủ động kiểm tra `Thread.currentThread().isInterrupted()` và quyết định không tiếp tục một thao tác dài.

**Không** dùng `lock()` rồi tưởng có thể catch `InterruptedException` ở chính lời gọi đó. API `lock()` không khai báo ngoại lệ ấy.

## 7. `LockSupport.park`: thức dậy khi interrupt nhưng không ném checked exception

`LockSupport` là primitive cấp thấp cho park/unpark. `park()` có thể trở về vì:

- Một permit được cấp qua `unpark(thread)`;
- Thread đã bị interrupt;
- Một **spurious return** (trở về không do sự kiện mà code dự kiến).

`park()` **không** tự xóa interrupt status và **không** ném `InterruptedException`. Vì vậy, code phải kiểm tra điều kiện thực và cờ ngắt, thường trong vòng lặp có predicate rõ ràng.

### Java 17+: quan sát cờ sau park

Tạo file `ParkInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;

public class ParkInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            ready.countDown();
            while (!Thread.currentThread().isInterrupted()) {
                LockSupport.park();
            }

            System.out.println("Flag after park: "
                    + Thread.currentThread().isInterrupted());
            System.out.println("Clear returned: "
                    + Thread.interrupted());
            System.out.println("Flag after clear: "
                    + Thread.currentThread().isInterrupted());
        }, "park-worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
    }
}
```

Chạy:

```bash
javac ParkInterruptDemo.java
java ParkInterruptDemo
```

Đầu ra:

```text
Flag after park: true
Clear returned: true
Flag after clear: false
```

Vòng `while` xử lý được **spurious return**: dù park trở về sớm, worker không ra khỏi vòng cho đến khi cờ được đặt. Khi interrupt đến, `park()` trở về hoặc vòng lặp thấy cờ đã có. `Thread.interrupted()` đọc và **xóa** cờ; đó là lý do dòng cuối là false.

**Lưu ý:** đây là ví dụ về interrupt flag. Nếu triển khai queue/lock bằng `LockSupport` thật sự, predicate “có thể tiến triển” phải được kiểm tra bằng giao thức đồng bộ phù hợp; việc `park/unpark` đơn độc không làm mọi shared mutable state an toàn.

## 8. Đợi mà “không ngắt được” có phải là luôn xấu?

Không hẳn. Có những thao tác cần giữ invariant ngay cả nếu người dùng đã hủy yêu cầu. Ví dụ một đoạn cập nhật ngắn có thể chờ lấy lock, hoàn thành một commit trong JVM rồi mới phản hồi tín hiệu interrupt. Tuy nhiên, **không interruptible** nghĩa là không thể dùng riêng `interrupt()` để đặt một giới hạn thời gian chờ chắc chắn tại điểm đó.

Một số API được thiết kế để **tiếp tục chờ dù bị interrupt**, đồng thời ghi nhớ cờ:

- `Semaphore.acquireUninterruptibly()`;
- `Condition.awaitUninterruptibly()` (chờ predicate/condition theo giao thức);
- `ReentrantLock.lock()`;
- `CompletableFuture.join()` (khác với `Thread.join()`).

Với các API này, phải có cơ chế **tiến triển**, timeout/giới hạn khác khi cần, hoặc bảo đảm tài nguyên cuối cùng sẽ được giải phóng. `Condition.awaitUninterruptibly()` có thể chờ mãi nếu không có signal/điều kiện thích hợp; interrupt đơn lẻ không phải cách thoát.

**Đừng chọn uninterruptible chỉ để tránh phải xử lý `InterruptedException`.** Làm vậy có thể khiến ứng dụng khó shutdown, các request bị hủy vẫn giữ thread lâu và hệ thống tích tụ việc chờ.

### `CompletableFuture.join()` không giống `Thread.join()`

- `Thread.join()` (bao gồm timed join) có thể ném `InterruptedException` khi **thread đang chờ** bị interrupt.
- `CompletableFuture.join()` trả kết quả hoặc ném `CompletionException`/`CancellationException` tương ứng, không khai báo `InterruptedException`; interrupt không phải đường thoát bình thường khỏi việc chờ của `join()`.
- `CompletableFuture.get()` lại là API chờ **interruptible**, có `InterruptedException`/`ExecutionException`; overload có timeout còn có `TimeoutException`.
- Timeout của caller **không** tự hủy task đang chạy; cần chính sách cancellation riêng.

Vì vậy cần chọn **API cụ thể**, không suy theo từ “join” trong tên phương thức.

## 9. Interrupt đối với Java I/O: luôn xem hợp đồng từng loại

Không thể nói “mọi I/O trong Java đều bị interrupt” hoặc “không I/O nào bị interrupt”. Cách xử lý khác nhau giữa stream truyền thống, socket, NIO channel và selector.

### `java.nio.channels.InterruptibleChannel`

Theo hợp đồng của `InterruptibleChannel`, khi một thread đang bị chặn trong I/O trên channel triển khai giao diện này mà bị interrupt, channel có thể bị đóng và thao tác ném `ClosedByInterruptException`, đồng thời interrupt status được đặt. Nếu một thread khác đóng channel trong khi thao tác đang chặn, nó có thể ném `AsynchronousCloseException`. Đây **không** phải `InterruptedException`.

Điều rất quan trọng: **channel bị đóng** không thể mặc nhiên dùng lại. Code phải xử lý vòng đời và mở lại tài nguyên nếu cần; không chỉ catch exception rồi retry trên cùng channel đã đóng.

### `Selector.select()`

Với selector NIO, interrupt một thread đang trong `select()` có tác dụng tương tự `wakeup()` đối với việc chọn kênh, nhưng không có nghĩa thao tác phải ném `InterruptedException`. Code phải xem kết quả select, trạng thái interrupt và vòng đời selector. Không được tưởng interrupt một selector tự hủy tất cả I/O của mọi channel đăng ký.

### `InputStream.read()` và socket truyền thống

Khả năng phản hồi interrupt **phụ thuộc class và cách tạo tài nguyên**. Một `InputStream` có thể không có hợp đồng hủy blocking read bằng `Thread.interrupt()`. Một số loại socket/channel có cơ chế đóng hoặc interrupt riêng. Ở Java 17 không nên áp đặt hành vi của virtual thread (xuất hiện ở các phiên bản Java mới hơn) cho platform thread chạy JDK 17.

Nếu dùng I/O, hãy đọc hợp đồng của lớp đang dùng, đặt timeout của socket/channel khi có hỗ trợ, hoặc quản lý việc đóng tài nguyên phù hợp. Với socket blocking, cần phân biệt timeout I/O và interrupt status của thread; chúng là các cơ chế khác nhau.

## 10. Interrupt, timeout và cancellation có mối quan hệ thế nào?

Một số thao tác cung cấp cả **interruptible wait** lẫn **timeout**:

| API | Timeout | Interrupt | Kết quả tiêu biểu |
| --- | --- | --- | --- |
| `BlockingQueue.poll(timeout, unit)` | Có | Có | Phần tử / `null` / `InterruptedException` |
| `ReentrantLock.tryLock(timeout, unit)` | Có | Có | `true` / `false` / `InterruptedException` |
| `CountDownLatch.await(timeout, unit)` | Có | Có | `true` / `false` / `InterruptedException` |
| `Future.get(timeout, unit)` | Có | Có | Giá trị / `TimeoutException` / `InterruptedException` / lỗi task |
| `Thread.join(timeout)` | Có | Có | Trả `void`; cần kiểm tra `isAlive()` sau đó |
| `Object.wait(timeout)` | Có | Có | Trở về; phải kiểm tra lại predicate |
| `Condition.awaitNanos(remaining)` | Có | Có | Ước lượng nanos còn lại; kiểm tra predicate |
| `Semaphore.tryAcquire(timeout, unit)` | Có | Có | `true` / `false` / `InterruptedException` |

**Timeout** nghĩa là khoảng chờ của caller đã hết; task hoặc producer **có thể vẫn đang chạy**. **Interrupt** là tín hiệu được gửi tới một thread. **Cancellation** là quyết định ở cấp task; thường có thể dùng interrupt như cơ chế gửi yêu cầu, nhưng không đồng nghĩa “đã hủy thành công mọi side effect”.

Ví dụ `Future.cancel(true)` yêu cầu hủy bằng cách cố interrupt thread chạy task nếu phù hợp. Nó không thể bảo đảm task tuân thủ interrupt hoặc dừng tại I/O/blocking point không hỗ trợ. Trạng thái `Future` có thể đã là cancelled trong khi mã của task vẫn đang thực thi một đoạn chưa phản hồi interrupt. Không được dùng cancellation flag của Future để suy ra tài nguyên ngoài ứng dụng chắc chắn đã rollback.

## 11. Thiết kế worker hợp tác với interrupt

Một vòng xử lý có thể kết hợp **điểm chặn interruptible** và **kiểm tra cờ tại các phần CPU**:

```java
// Snippet về cấu trúc một worker, chưa là file Java độc lập.
while (!Thread.currentThread().isInterrupted()) {
    try {
        Task task = queue.take(); // Interruptible.
        process(task);            // Có thể là CPU/I/O; cần hợp đồng riêng.
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
    }
}
cleanup();
```

Ở đây `Task`, `queue`, `process` và `cleanup` là các thành phần phải được khai báo trong ứng dụng thật. Khi `take()` bị interrupt, worker phục hồi cờ và thoát vòng; các thao tác cleanup thực hiện sau đó. Nếu `process(task)` chạy CPU lâu và không bao giờ kiểm tra interrupt, việc shutdown **vẫn có thể chậm** dù `queue.take()` là interruptible.

Đối với code CPU dài, kiểm tra `Thread.currentThread().isInterrupted()` định kỳ ở các điểm an toàn; xác định **sau bước nào** có thể dừng mà không phá dữ liệu. Đối với I/O, đặt timeout/đóng tài nguyên theo API; đối với lock, cân nhắc `lockInterruptibly`; đối với waiting loops, không nuốt interrupt và tiếp tục đợi vô hạn.

### Khi cần cleanup

Không được để interrupt làm bỏ qua `finally` giải phóng lock, permit, connection, file hoặc các tài nguyên đã acquire. Ngược lại, cũng không được **release khi chưa acquire thành công**:

```java
// Snippet: lock là ReentrantLock đã khai báo.
boolean acquired = false;
try {
    lock.lockInterruptibly();
    acquired = true;
    // Thực hiện công việc dưới lock.
} finally {
    if (acquired) {
        lock.unlock();
    }
}
```

Snippet này thuộc một phương thức khai báo `throws InterruptedException`. Cách viết phân biệt đường thành công và bị ngắt **trước khi lấy khóa**, tránh gọi `unlock()` sai owner.

## 12. Những lỗi phổ biến

1. **“`interrupt()` tương đương kill thread.”** Sai: nó chỉ gửi yêu cầu, code và API quyết định phản hồi.
2. **“Một thread chờ `synchronized` sẽ ném `InterruptedException`.”** Sai: monitor acquisition không interruptible theo cách đó.
3. **“`Object.wait()` và chờ vào monitor là một thứ.”** Sai: wait interruptible và nhả monitor trong lúc đợi; chờ lấy monitor thì không interruptible.
4. **“`ReentrantLock.lock()` sẽ dừng chờ khi bị interrupt.”** Sai: phải dùng `lockInterruptibly()` hoặc timed `tryLock` nếu cần đường thoát.
5. **“Sau khi catch `InterruptedException` cờ chắc chắn vẫn true.”** Sai: nhiều blocking API xóa cờ khi ném; có thể cần restore.
6. **“`Thread.interrupted()` chỉ đọc cờ.”** Sai: nó đọc **và xóa** cờ của thread hiện tại.
7. **“`park()` ném `InterruptedException`.”** Sai: nó trở về với cờ được giữ; còn có thể thức dậy không vì interrupt.
8. **“`Thread.sleep()` nhả monitor.”** Sai: sleep không nhả monitor hoặc lock đã giữ.
9. **“`CompletableFuture.join()` phản hồi interrupt giống `Thread.join()`.”** Sai: semantics khác nhau.
10. **“`Future.cancel(true)` bảo đảm tác vụ đã dừng.”** Sai: đó là yêu cầu hợp tác, có thể chưa được xử lý.
11. **“Mọi `InputStream.read()` đều bị `Thread.interrupt()` đánh thức.”** Không có bảo đảm chung; phải xem loại I/O cụ thể.
12. **“Ngắt một thread đang trong `InterruptibleChannel` chỉ tạo `InterruptedException` và channel không sao.”** Sai: có thể là `ClosedByInterruptException` và channel bị đóng.
13. **“Dùng uninterruptible API tránh được mọi phức tạp.”** Sai: chỉ chuyển vấn đề sang khả năng shutdown, backpressure hoặc deadlock.
14. **“Một khi đã nhận interrupt, không cần dọn dẹp.”** Sai: cleanup, rollback/ack và giải phóng tài nguyên vẫn phải đúng giao thức.
15. **“Gửi interrupt cho thread đang chờ worker sẽ tự interrupt worker.”** Sai: thread bị ngắt và thread được chờ là hai đối tượng khác nhau.

## 13. Checklist chọn blocking point trong Java

1. **Thao tác đang chờ điều gì?** Lock, monitor, dữ liệu queue, permit, tín hiệu, task, CPU hay I/O?
2. **API cụ thể có hỗ trợ interrupt không?** Đọc hợp đồng; không suy từ tên “blocking”.
3. **Phản hồi là gì?** `InterruptedException`, boolean/null, trả từ `park()`, hay ngoại lệ I/O như `ClosedByInterruptException`?
4. **Interrupt status còn hay đã bị xóa?** Kiểm tra và restore/propagate phù hợp; tránh gọi `Thread.interrupted()` vô tình.
5. **Có nên chờ không giới hạn không?** Nếu không, chọn API có timeout và dùng deadline chung nếu nhiều bước chờ.
6. **Có giữ lock/permit/tài nguyên không?** Sắp xếp `try/finally`; chỉ nhả những gì đã acquire.
7. **Công việc CPU/I/O có điểm kiểm tra không?** Nếu không, interrupt chỉ được phản hồi ở điểm chặn tiếp theo hoặc không phản hồi.
8. **Làm sao hủy tác vụ thật sự?** Xem xét `Future.cancel`, interrupt hợp tác, cờ trạng thái, timeout I/O và đóng tài nguyên khi cần.
9. **Hủy giữa chừng có phá invariant không?** Xác định điểm dừng an toàn và xử lý side effect một phần.
10. **Có kiểm thử được các đường ngắt không?** Dùng latch/khóa để đặt thread vào trạng thái chờ có kiểm soát, rồi gửi interrupt và xác minh thời điểm thoát, cờ và cleanup.
11. **Có nhiều loại lock/wait lồng nhau không?** Interrupt ở một điểm chặn không tự tháo vòng deadlock hay làm thread khác nhả khóa.
12. **Ứng dụng shutdown có tiến triển không?** Xem thời hạn kết thúc, số thread còn chờ và khả năng xử lý interrupt dưới tải thật.

**Ghi nhớ:** một số điểm chặn Java **ném `InterruptedException` và thoát chờ**, một số **vẫn đợi dù bị interrupt**, và một số có **cơ chế trả về/ngoại lệ riêng**. Muốn hủy an toàn, phải biết chính xác API đang chờ, xử lý interrupt status đúng cách, thiết kế cleanup trong `finally` và không đánh đồng interrupt với khả năng cưỡng ép chấm dứt task.