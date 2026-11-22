# Timeout khi chờ dữ liệu hoặc tài nguyên trong Java

## 1. Timeout giải quyết bài toán gì?

Trong chương trình đa luồng, một thread thường phải **chờ một sự kiện**: dữ liệu xuất hiện trong queue, một lock được giải phóng, một permit còn trống, worker hoàn tất hoặc một điều kiện trạng thái trở thành đúng. Nếu chờ vô hạn, một tác vụ bị treo, producer chết hoặc tài nguyên luôn bị tranh chấp có thể khiến thread chờ mãi.

**Timeout** là giới hạn thời gian thread **sẵn sàng dành cho thao tác chờ**, giúp ứng dụng có thể tiếp tục xử lý khi sự kiện chưa xuất hiện. Đây không phải lời cam kết rằng công việc sẽ hoàn thành trong thời hạn đó.

Ví dụ: một consumer chỉ được chờ tối đa 200 ms để lấy dữ liệu. Nếu chưa có, nó có thể trả về kết quả “chưa có dữ liệu”, ghi nhận retry hoặc chuyển sang một tác vụ khác. **Không được** tự giả định producer đã dừng, dữ liệu không bao giờ tới, hoặc queue đã hỏng chỉ vì `poll(timeout)` hết hạn.

Hai yêu cầu cần tách biệt:

- **Bounded waiting:** không chờ mãi một điều kiện hoặc tài nguyên.
- **Cancellation / deadline của tác vụ:** yêu cầu công việc đang chạy ngừng hoặc không bắt đầu sau một hạn chót. Timeout khi *đợi kết quả* thường **không tự hủy** tác vụ cung cấp kết quả.

Bài học tập trung vào Java concurrency nói chung, sử dụng API của JDK (Java 17+), không gắn với framework.

## 2. Bốn điều cần phân biệt: timeout, deadline, interruption, cancellation

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Timeout** | Khoảng thời gian tối đa muốn dành cho một thao tác chờ | `queue.poll(200, MILLISECONDS)` |
| **Deadline** | Mốc kết thúc chung cho nhiều giai đoạn; mỗi giai đoạn chỉ dùng **thời gian còn lại** | Hai lần chờ queue và lock dùng cùng ngân sách 500 ms |
| **Interruption** | Tín hiệu hợp tác gửi tới một thread để yêu cầu thoát thao tác chờ/dừng công việc | `waitingThread.interrupt()` |
| **Cancellation** | Quyết định không tiếp tục một task; mức độ hiệu lực phụ thuộc API và code task | `future.cancel(true)` gửi interrupt khi phù hợp |

Một thread có thể ngừng chờ vì **thành công**, **hết thời gian**, **interrupt**, hoặc **lỗi khác**. Thiết kế đúng phải phân biệt các trường hợp đó bằng return value/exception và không biến mọi thất bại thành “timeout”.

### Một phép chờ có hạn có chấm dứt đúng thời điểm không?

**Không bảo đảm chính xác từng mili-giây.** Scheduler, timer và tải CPU ảnh hưởng thời điểm thread thức dậy. Phương thức có timeout thường bảo đảm về cách sử dụng ngân sách chờ theo hợp đồng API, không phải đáp ứng hard real-time. Việc thực thi mã sau khi thức dậy cũng có thể bị scheduler trì hoãn.

Ngoài ra, một thread đã lấy được lock/permit hoặc nhận dữ liệu **trước thời điểm kiểm tra kết quả** vẫn phải xử lý việc đó, kể cả khi thời hạn tổng của ứng dụng vừa trôi qua. Timeout là một phần của giao thức, không thay cho việc kiểm tra state và xử lý trường hợp tranh chấp.

## 3. Nhận dữ liệu với `BlockingQueue.poll(timeout, unit)`

`BlockingQueue` phù hợp cho producer–consumer. Các API thường gặp:

- `take()`: chờ đến khi có phần tử, không đặt timeout; có thể ném `InterruptedException`.
- `poll()`: kiểm tra ngay, không chờ; nếu rỗng, trả `null`.
- `poll(long timeout, TimeUnit unit)`: đợi tối đa khoảng timeout khi queue rỗng; trả phần tử nếu có, hoặc `null` nếu hết thời gian mà vẫn chưa nhận được.
- `put(element)`: chờ nếu queue có giới hạn và đang đầy.
- `offer(element, timeout, unit)`: đợi một khoảng có giới hạn để thêm vào queue đầy; trả `boolean`.

**Ý nghĩa của `null`:** đối với `BlockingQueue` tiêu chuẩn, phần tử null không được phép đưa vào. Vì vậy `poll(timeout) == null` là một tín hiệu không lấy được dữ liệu trong khoảng đợi, không phải “đọc được bản ghi null”.

### Ví dụ Java 17+: thử lấy dữ liệu có thời hạn

Tạo file `TimedQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        String missing = queue.poll(0, TimeUnit.MILLISECONDS);
        System.out.println("Initially empty: " + (missing == null));

        queue.put("job-1");
        String received = queue.poll(1, TimeUnit.SECONDS);

        System.out.println("Received: " + received);
        System.out.println("Queue empty: " + queue.isEmpty());
    }
}
```

Biên dịch/chạy:

```bash
javac TimedQueueDemo.java
java TimedQueueDemo
```

Đầu ra:

```text
Initially empty: true
Received: job-1
Queue empty: true
```

Trong ví dụ này, `poll(0, ...)` được gọi khi queue chắc chắn rỗng nên trả null ngay, còn lần `poll(1, SECONDS)` thực thi khi đã có `job-1`, nên lấy được phần tử mà không cần chờ. Ví dụ cố ý tạo đầu ra **xác định**, không giả vờ rằng lịch scheduling hay độ trễ luôn cố định.

Nếu có producer/consumer thật chạy trên các thread khác nhau, `poll(200, MILLISECONDS)` có thể trả dữ liệu ngay, sau một phần của khoảng chờ hoặc trả null. Không hứa bất kỳ thứ tự/timing nào trừ khi có cơ chế đồng bộ khác.

### Queue đầy cũng là bài toán “chờ tài nguyên”

Với queue bounded, producer cần chính **dung lượng trống**, không chỉ consumer cần dữ liệu. Dùng `offer(element, timeout, unit)` để tránh producer bị treo vô hạn vì consumer đã ngừng lấy dữ liệu.

`offer` trả `false` khi không chèn được trong khoảng thời gian cho phép. Đó **không** chứng minh queue vĩnh viễn đầy. Ứng dụng phải có chiến lược rõ ràng: retry có giới hạn, backpressure, trả tín hiệu quá tải hoặc từ chối có kiểm soát; không âm thầm đánh mất bản ghi quan trọng.

## 4. Chờ lock với `ReentrantLock.tryLock(timeout, unit)`

`ReentrantLock.lock()` đợi cho đến khi lấy được khóa, không đặt timeout. `tryLock()` không tham số **chỉ thử ngay**. `tryLock(long timeout, TimeUnit unit)` chờ tối đa một khoảng cho lock khả dụng và trả `true` nếu lấy được, `false` nếu không lấy được trong giới hạn.

**Quy tắc đặc biệt quan trọng:** chỉ `unlock()` khi **đã thật sự lấy được lock**. Nếu `tryLock` trả `false` hoặc bị `InterruptedException` trước khi acquire, thread đó không phải owner.

Mẫu sử dụng:

```java
// Snippet: lock đã là một ReentrantLock.
boolean acquired = lock.tryLock(200, TimeUnit.MILLISECONDS);
if (!acquired) {
    return; // Tùy hợp đồng của phương thức bao quanh.
}
try {
    // Xử lý trạng thái được lock bảo vệ.
} finally {
    lock.unlock();
}
```

Snippet trên **không phải chương trình độc lập**: `lock` và phương thức bao quanh chưa được khai báo.

### Ví dụ Java 17+: timeout khi lock đang bị giữ

Tạo file `TimedLockDemo.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TimedLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        lock.lock(); // Thread main giữ lock trong suốt lúc worker thử.

        try {
            Thread worker = new Thread(() -> {
                boolean acquired = false;
                try {
                    acquired = lock.tryLock(50, TimeUnit.MILLISECONDS);
                    System.out.println("Worker acquired: " + acquired);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("Worker interrupted");
                } finally {
                    if (acquired) {
                        lock.unlock();
                    }
                }
            }, "worker");

            worker.start();
            worker.join(); // Main vẫn giữ lock, worker chỉ được đợi 50 ms.
        } finally {
            lock.unlock();
        }

        System.out.println("Main released lock");
    }
}
```

Chạy:

```bash
javac TimedLockDemo.java
java TimedLockDemo
```

Đầu ra nếu không có thread bên ngoài interrupt worker:

```text
Worker acquired: false
Main released lock
```

Main cố ý giữ khóa trong khi đợi worker kết thúc. Worker **không thể** lấy khóa do main giữ, nên `tryLock(50, MILLISECONDS)` trả false sau khi hết khoảng chờ (không cần đúng chính xác 50 ms). Nhờ worker **có timeout**, `join()` của main có thể hoàn tất. Nếu worker dùng `lock()` không timeout thì chương trình mẫu có thể deadlock: main chờ worker, worker chờ lock do main giữ.

Đây là ví dụ kiểm soát thời gian chờ, **không phải** mẫu khuyến nghị “vừa giữ lock vừa join worker” trong ứng dụng thật. Thực tế nên tránh giữ khóa trong lúc chờ công việc khác cần khóa đó.

### Fairness và interrupt

`tryLock(timeout, unit)` của `ReentrantLock` có thể bị ngắt và ném `InterruptedException`. Với fair lock, cơ chế chờ có xét chính sách ưu tiên người chờ lâu của lock, nhưng fairness không bảo đảm scheduler công bằng tuyệt đối. `tryLock()` không timeout có những khác biệt về barging trên fair lock; không dùng kết quả thử khóa để chứng minh thứ tự nghiệp vụ.

## 5. Chờ permit bằng `Semaphore.tryAcquire(timeout, unit)`

`Semaphore` thường biểu diễn số slot/tài nguyên có thể dùng đồng thời, ví dụ tối đa 4 kết nối. `acquire()` chờ permit khi chưa có; `tryAcquire(timeout, unit)` cho phép chờ có giới hạn.

```java
// Snippet: permits là Semaphore đã khai báo.
if (!permits.tryAcquire(100, TimeUnit.MILLISECONDS)) {
    // Không có permit trong ngân sách chờ.
    return;
}
try {
    // Dùng slot tài nguyên.
} finally {
    permits.release();
}
```

Khác `ReentrantLock`, `Semaphore` không gắn permit với owner thread theo cùng mô hình; code cần thiết kế ai chịu trách nhiệm release. **Không release khi chưa acquire thành công**, vì có thể làm tăng sai số permit và phá giới hạn tài nguyên.

### Ví dụ Java 17+: giới hạn hai tài nguyên

Tạo file `TimedSemaphoreDemo.java`:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class TimedSemaphoreDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);

        boolean first = slots.tryAcquire(0, TimeUnit.MILLISECONDS);
        boolean second = slots.tryAcquire(0, TimeUnit.MILLISECONDS);
        boolean third = slots.tryAcquire(0, TimeUnit.MILLISECONDS);

        System.out.println("First acquired: " + first);
        System.out.println("Second acquired: " + second);
        System.out.println("Third acquired: " + third);

        if (first) {
            slots.release();
        }
        if (second) {
            slots.release();
        }
        System.out.println("Available permits: "
                + slots.availablePermits());
    }
}
```

Chạy:

```bash
javac TimedSemaphoreDemo.java
java TimedSemaphoreDemo
```

Đầu ra:

```text
First acquired: true
Second acquired: true
Third acquired: false
Available permits: 2
```

Không có scheduling tranh chấp trong ví dụ nên kết quả được xác định. Mã chỉ minh họa permit; thực tế cần tính cả **vòng đời của tài nguyên vật lý**. Nếu acquire permit nhưng không mở được kết nối, `finally` vẫn phải nhả permit khi appropriate; nếu đã mở kết nối thì phải đóng kết nối theo hợp đồng riêng của nó.

## 6. Chờ tín hiệu với `CountDownLatch.await(timeout, unit)`

`CountDownLatch` chờ một **mốc sự kiện**, không đợi một giá trị queue. Các API:

- `await()`: chờ vô hạn đến khi count về 0 hoặc thread bị interrupt.
- `await(timeout, unit)`: trả về **`true`** nếu latch đạt 0 trước khi kết thúc chờ, **`false`** nếu timeout khi count chưa về 0.
- `countDown()`: giảm count nếu lớn hơn 0; latch đã về 0 sẽ giữ trạng thái mở, không dùng lại để đếm chu kỳ khác.

```java
// Snippet: latch đã khai báo là CountDownLatch.
boolean ready = latch.await(300, TimeUnit.MILLISECONDS);
if (!ready) {
    // Chưa thấy sự kiện hoàn tất trong thời gian được phép chờ.
}
```

**Lỗi thường gặp:** gọi `await(timeout)` rồi mặc định code sau đó có quyền dùng dữ liệu đã chuẩn bị. Phải kiểm tra `true/false`. `false` không có nghĩa producer sẽ không bao giờ hoàn tất; một thread khác có thể gọi `countDown()` ngay sau đó.

Dùng latch để biểu diễn “tất cả worker đã tới mốc sẵn sàng”, “cấu hình đã được nạp xong”, hoặc “N phần việc đã hoàn tất”. Nhưng nếu một worker chết trước khi `countDown()`, latch có thể không về 0; nên đặt countDown trong `finally` nếu ngữ nghĩa của latch là “worker đã kết thúc dù thành công hay thất bại”, hoặc công bố trạng thái lỗi riêng nếu cần phân biệt thành công.

## 7. `Condition.awaitNanos` và vòng lặp điều kiện

Khi tự quản lý một queue/điều kiện dùng `Lock` và `Condition`, cần cẩn thận với:

1. **Spurious wakeup:** một lần `await` có thể thức dậy mà điều kiện chưa đúng.
2. **Signal không đồng nghĩa điều kiện đã đúng:** có thể có nhiều thread chờ, thread khác đã tiêu thụ dữ liệu.
3. **Timeout tổng:** sau một lần thức dậy, không được **reset** ngân sách chờ về giá trị ban đầu nếu người dùng chỉ cấp một khoảng chờ chung.

`Condition.awaitNanos(long nanosTimeout)` trả về **ước lượng số nano-giây còn lại**; có thể không dương khi đã hết hạn. Để xử lý đúng, phải giữ lock khi kiểm tra predicate, đợi trong `while` và dùng số còn lại cho lần đợi tiếp theo.

### Java 17+: mailbox một phần tử với timeout

Tạo tệp `TimedMailbox.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class TimedMailbox {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition hasMessage = lock.newCondition();
    private String message;

    public void put(String value) {
        lock.lock();
        try {
            if (message != null) {
                throw new IllegalStateException("Mailbox full");
            }
            message = value;
            hasMessage.signal();
        } finally {
            lock.unlock();
        }
    }

    public String receive(long timeout, TimeUnit unit)
            throws InterruptedException {
        long remaining = unit.toNanos(timeout);
        lock.lockInterruptibly();
        try {
            while (message == null) {
                if (remaining <= 0L) {
                    return null;
                }
                remaining = hasMessage.awaitNanos(remaining);
            }

            String received = message;
            message = null;
            return received;
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        TimedMailbox box = new TimedMailbox();
        System.out.println("Empty: "
                + (box.receive(0, TimeUnit.MILLISECONDS) == null));
        box.put("hello");
        System.out.println("Received: "
                + box.receive(1, TimeUnit.SECONDS));
    }
}
```

Biên dịch/chạy:

```bash
javac TimedMailbox.java
java TimedMailbox
```

Đầu ra:

```text
Empty: true
Received: hello
```

**Giải thích:**

- `message` chỉ được truy cập khi giữ **cùng một lock**; không đọc/ghi ngoài đồng bộ.
- `while (message == null)` kiểm tra lại predicate sau mỗi lần tỉnh dậy, kể cả spurious wakeup.
- `remaining` được cập nhật từ `awaitNanos` nên nếu thức dậy nhiều lần, thời gian đợi **không bắt đầu lại từ đầu**.
- `lockInterruptibly()` cho phép thread bị interrupt trong lúc chờ lấy lock; `awaitNanos` cũng có thể bị interrupt.
- `finally` bảo đảm nhả lock dù nhận được dữ liệu, timeout hoặc exception.
- Demo gọi lần đầu với timeout bằng 0 (queue rỗng), lần sau khi dữ liệu đã được đặt vào mailbox, nên không phụ thuộc timing của thread khác.

**Một giới hạn có chủ đích:** `put` ở đây từ chối khi mailbox đang đầy thay vì chờ có slot; mục tiêu ví dụ là **chờ dữ liệu với một Condition**. Nếu producer cũng cần chờ cho tới khi mailbox trống, phải thiết kế thêm điều kiện `notFull`, predicate và timeout phù hợp, hoặc dùng `ArrayBlockingQueue` có sẵn để tránh tự viết một concurrent queue đầy đủ.

### Timeout khi lấy lock và khi đợi condition

`receive()` ở trên dùng `lockInterruptibly()`, nghĩa là **thời gian chờ để giành lock chưa được tính vào timeout của `awaitNanos`**. Nếu API nghiệp vụ hứa **toàn bộ lời gọi receive không quá một ngân sách**, cần dùng `tryLock(remaining, unit)` để tính cả thời gian chờ khóa, sau đó truyền **thời gian còn lại** tới `awaitNanos`.

Đây là khác biệt quan trọng giữa “timeout của **một bước chờ**” và “deadline của **toàn bộ thao tác**”.

## 8. `Future.get(timeout, unit)`: chờ kết quả không có nghĩa hủy task

Khi gửi một `Callable` qua `ExecutorService`, ta có thể đợi kết quả bằng `Future.get(timeout, unit)`. Nếu task chưa hoàn tất khi hết thời gian, lệnh ném `TimeoutException`. **Future vẫn có thể đang chạy.** Chỉ `cancel(...)` theo chính sách ứng dụng mới gửi yêu cầu hủy, và ngay cả `cancel(true)` cũng không bảo đảm task lập tức dừng nếu code không hợp tác với interrupt.

### Java 17+: timeout được tạo có kiểm soát

Tạo file `FutureTimeoutDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch gate = new CountDownLatch(1);

        try {
            Callable<String> task = () -> {
                gate.await();
                return "done";
            };
            Future<String> future = executor.submit(task);

            try {
                future.get(20, TimeUnit.MILLISECONDS);
                System.out.println("Unexpected completion");
            } catch (TimeoutException expected) {
                System.out.println("Timed out while waiting");
            }

            gate.countDown(); // Cho phép task thực sự kết thúc.
            System.out.println("Result after release: " + future.get());
        } finally {
            gate.countDown(); // Tránh kẹt worker khi main rời try sớm.
            executor.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
```

Đầu ra khi không có interrupt ngoài và executor hoạt động bình thường:

```text
Timed out while waiting
Result after release: done
```

Vì `gate` chưa mở trong khoảng chờ đầu tiên, task **không thể** trả về kết quả trước khi main gọi `gate.countDown()`. Vì vậy lần `get(20, MILLISECONDS)` đầu phải timeout; sau khi mở gate, `get()` tiếp theo lấy kết quả. Lệnh `get` không tự hủy task.

Các tình huống khác:

- Task ném exception: `get` có thể ném `ExecutionException` và chứa nguyên nhân của task.
- Task bị cancel: `get` ném `CancellationException`.
- Thread gọi `get` bị interrupt: `get` có thể ném `InterruptedException`.
- Hết thời gian nhưng task còn chạy: `get` ném `TimeoutException`; caller phải quyết định retry, cancel hoặc tiếp tục xử lý khác.

Nếu sử dụng `cancel(true)`, hãy làm cho task **hợp tác với interrupt**, chẳng hạn thoát khi thao tác chờ ném `InterruptedException` hoặc kiểm tra cờ interrupt trong vòng xử lý phù hợp. Không dùng `Thread.stop()` để cưỡng ép hủy.

## 9. `Thread.join(timeout)`: chờ thread kết thúc có giới hạn

`Thread.join()` không timeout sẽ chờ thread đích kết thúc. `Thread.join(long millis)` hoặc overload có nano-giây cho phép chờ một khoảng có giới hạn, nhưng **trả `void`**, không trả true/false. Sau timed join, phải kiểm tra `worker.isAlive()` nếu muốn biết worker còn chạy không.

Các bẫy:

- `join(0)` **là chờ vô hạn**, không phải thử ngay.
- `join(100)` không làm worker bị hủy khi 100 ms trôi qua.
- `join(timeout)` có thể trở về vì worker đã kết thúc hoặc vì thời gian chờ hết.
- `worker.isAlive()` là snapshot trạng thái; sau khi kiểm tra, worker có thể kết thúc ngay.
- `join` có thể ném `InterruptedException` khi **thread đang chờ** bị interrupt; nó không tự interrupt worker.

Dùng `Future` thường tự nhiên hơn khi cần quản lý kết quả, exception, timeout và cancellation của task, thay vì thao tác trực tiếp với vòng đời `Thread`.

## 10. Một deadline chung cho nhiều lần chờ

Giả sử API cho **500 ms để lấy dữ liệu và lấy lock**. Nếu gọi `queue.poll(500ms)` rồi `lock.tryLock(500ms)`, tổng thời gian **có thể vượt xa 500 ms**, vì mỗi lời gọi nhận **ngân sách riêng**. Nếu tiếp tục retry với 500 ms mỗi lần, thời gian tổng còn có thể kéo dài không giới hạn.

Cần tính **thời gian còn lại**:

```java
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(500);
long started = System.nanoTime();

// Sau mỗi giai đoạn:
long elapsed = System.nanoTime() - started;
long remaining = budgetNanos - elapsed;

if (remaining <= 0L) {
    // Đã hết ngân sách; không bắt đầu thêm một lần chờ dài.
}
```

Đây là snippet về cách tính ngân sách; chưa có phương thức xử lý được khai báo. `System.nanoTime()` phù hợp để đo **thời gian trôi qua** trong một JVM, vì nó là đồng hồ đơn điệu tương đối cho việc đo khoảng thời gian, không dùng để suy ra ngày giờ thực tế.

**Tại sao không dùng `System.currentTimeMillis()`?** Wall clock có thể bị chỉnh bởi NTP, quản trị viên hoặc đồng bộ thời gian; chênh lệch của nó không phải lựa chọn tối ưu để đo deadline tương đối.

**Lưu ý về overflow:** phép trừ `now - start` với `nanoTime` thích hợp để đo khoảng cách khi ngân sách nhỏ hơn khoảng 2^63 ns (xấp xỉ 292 năm). Với timeout rất lớn, cần giới hạn hợp lý và tránh làm tràn phép cộng `start + timeout`. Các API `TimeUnit` và `Duration` nên được dùng nhất quán về đơn vị; không tự nhân milliseconds × 1_000_000 khi giá trị có thể lớn đến mức overflow.

### Java 17+: chung một ngân sách cho queue và lock

Tạo file `SharedDeadlineDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class SharedDeadlineDemo {
    static boolean processWithinBudget(
            ArrayBlockingQueue<String> queue,
            ReentrantLock lock,
            long budget,
            TimeUnit unit) throws InterruptedException {
        long allowed = unit.toNanos(budget);
        long start = System.nanoTime();

        if (allowed <= 0L) {
            return false;
        }

        String message = queue.poll(allowed, TimeUnit.NANOSECONDS);
        if (message == null) {
            return false;
        }

        long remaining = allowed - (System.nanoTime() - start);
        if (remaining <= 0L) {
            return false;
        }

        if (!lock.tryLock(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }

        try {
            System.out.println("Processed: " + message);
            return true;
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ArrayBlockingQueue<String> queue =
                new ArrayBlockingQueue<>(1);
        ReentrantLock lock = new ReentrantLock();

        System.out.println("Empty: " + !processWithinBudget(
                queue, lock, 1, TimeUnit.MILLISECONDS));

        queue.put("task-1");
        boolean processed = processWithinBudget(
                queue, lock, 1, TimeUnit.SECONDS);
        System.out.println("Success: " + processed);
    }
}
```

Chạy:

```bash
javac SharedDeadlineDemo.java
java SharedDeadlineDemo
```

Một đầu ra có thể gặp:

```text
Empty: true
Processed: task-1
Success: true
```

**Điều nào được bảo đảm?**

- Lời gọi đầu tiên xử lý queue rỗng: `poll` hết thời gian và trả null, nên in `Empty: true`.
- Lời gọi thứ hai đã có dữ liệu và lock không bị tranh chấp, nhưng **đầu ra thành công vẫn phụ thuộc** việc thread có thể được scheduler trì hoãn bất thường giữa `poll` và phép tính `remaining`. Với tải bình thường sẽ thường thành công; không được khẳng định `Processed`/`Success: true` là tất yếu với mọi lịch.
- Nếu ngân sách đã hết trước khi lấy lock, phương thức trả false. **Trong ví dụ này, phần tử đã được lấy ra khỏi queue** trước khi thử lock: nếu xử lý thất bại, có nguy cơ dữ liệu bị bỏ mất. Đây là **giới hạn nghiệp vụ quan trọng**, không phải mẫu queue processing đầy đủ cho production.

**Sửa ở mức thiết kế:** nếu lấy dữ liệu đồng nghĩa “nhận trách nhiệm xử lý”, phải có cơ chế acknowledgment, đưa lại queue có kiểm soát, lease/visibility timeout, hoặc thiết kế lấy tài nguyên **trước** khi dequeue để không đánh mất item. Thứ tự lấy tài nguyên cũng phải tránh deadlock và tắc nghẽn. Không xem một hàm trả false là đủ nếu nó đã tạo tác dụng phụ một phần.

### “Hard deadline” của toàn bộ công việc còn khó hơn

Cùng một time budget cho các lần **blocking** vẫn không biến mọi đoạn code thành hard real-time. CPU có thể trì hoãn thread sau khi lấy lock; xử lý tác vụ hoặc I/O không hỗ trợ timeout có thể vượt hạn. Cần truyền deadline xuống từng tầng, đặt timeout ở các API có hỗ trợ và xác định quy tắc kiểm tra kết quả khi thời hạn đã qua.

## 11. Xử lý `InterruptedException` đúng cách

Các thao tác blocking như `queue.poll(timeout, unit)`, `lock.tryLock(timeout, unit)`, `latch.await(timeout, unit)`, `Condition.awaitNanos` và `Future.get(timeout, unit)` có thể ném `InterruptedException`.

Có hai cách xử lý phổ biến:

1. **Truyền tiếp:** khai báo `throws InterruptedException` để caller quyết định dừng công việc và giải phóng các tài nguyên liên quan.
2. **Bắt ở tầng không thể truyền:** hoàn tất dọn dẹp cần thiết, gọi `Thread.currentThread().interrupt()` để phục hồi interrupt status nếu không tiếp tục ném ngoại lệ, rồi trả kết quả phù hợp.

```java
// Snippet: worker là Thread khác, trả false nếu bị interrupt.
static boolean waitUntilDone(Thread worker) {
    try {
        worker.join();
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Snippet là helper trong class khác, không phải chương trình độc lập. `false` chỉ nói **không hoàn tất việc chờ**, không chứng minh worker đã kết thúc hoặc đã bị hủy.

Đừng nuốt `InterruptedException` rồi tiếp tục chờ vô hạn theo cùng chính sách mà không giải thích. Khi một API có timeout trả `false` hoặc `null`, điều đó khác với `InterruptedException`: một bên là hết ngân sách chờ, bên kia là tín hiệu interrupt; hệ thống có thể cần xử lý khác nhau.

## 12. Những lỗi thường gặp

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `Thread.sleep(100)` để “chờ dữ liệu” | Không xác minh dữ liệu đã có; không thiết lập giao thức đồng bộ | Dùng `BlockingQueue`, latch, Future hoặc Condition phù hợp |
| `poll(timeout) == null` thì kết luận producer đã chết | Timeout chỉ nói chưa nhận được phần tử trong khoảng chờ | Theo dõi trạng thái producer/lỗi qua kênh riêng |
| `tryLock` trả false nhưng vẫn `unlock()` | Chưa sở hữu lock; có thể ném `IllegalMonitorStateException` | Dùng biến `acquired`, unlock chỉ trong nhánh thành công |
| `Semaphore.tryAcquire` thất bại vẫn `release()` | Tăng permit sai, phá giới hạn tài nguyên | Release đúng số permit đã acquire thành công |
| `Future.get(timeout)` hết hạn thì task đã bị hủy | Task có thể vẫn đang chạy | Xác định cancellation policy, `cancel(true)` nếu phù hợp |
| `Thread.join(0)` là non-blocking | `join(0)` chờ vô hạn | Dùng `isAlive()` để quan sát trạng thái, hoặc timed join dương |
| Dùng `if` thay `while` quanh `Condition.await` | Có spurious wakeups và signal không bảo đảm predicate | Kiểm tra predicate trong vòng `while` |
| Reset timeout sau mỗi lần wakeup | Có thể chờ tổng thời gian dài hơn ngân sách | Dùng `awaitNanos` hoặc tính thời gian còn lại |
| Hai bước chờ mỗi bước dùng toàn bộ timeout | Tổng thời gian chờ có thể gần gấp đôi | Truyền chung deadline/remaining |
| Dùng `currentTimeMillis` để đo elapsed | Wall clock có thể thay đổi | Dùng `System.nanoTime()` cho khoảng thời gian |
| Timeout được coi là lỗi dữ liệu | Có thể là tranh chấp/tải tạm thời | Thiết kế retry, backpressure, cảnh báo phù hợp |
| Hết timeout sau khi lấy dữ liệu thì bỏ item | Tạo mất dữ liệu hoặc xử lý không nhất quán | Thiết kế ownership, ack và rollback/requeue phù hợp |
| Nuốt interrupt | Thread có thể không dừng khi được yêu cầu | Propagate hoặc restore interrupt status |
| Timeout nhỏ được xem là cam kết hard real-time | Scheduling và các bước non-blocking khác vẫn tốn thời gian | Thiết kế SLA, đo tail latency và deadline cuối-đến-cuối |

## 13. Lựa chọn API theo điều kiện đang chờ

| Đang chờ gì? | API JDK phổ biến | Kết quả khi timeout |
| --- | --- | --- |
| Một **phần tử dữ liệu** trong queue | `BlockingQueue.poll(timeout, unit)` | `null` |
| **Dung lượng trống** của queue | `BlockingQueue.offer(e, timeout, unit)` | `false` |
| Một **lock** | `ReentrantLock.tryLock(timeout, unit)` | `false` |
| Một hay nhiều **permit** | `Semaphore.tryAcquire(timeout, unit)` | `false` |
| Một **mốc đồng bộ** | `CountDownLatch.await(timeout, unit)` | `false` |
| Một **predicate dưới lock** | `Condition.awaitNanos(remaining)` | Ước lượng remaining không dương nếu hết thời gian; luôn kiểm tra predicate |
| Kết quả từ **task** | `Future.get(timeout, unit)` | Ném `TimeoutException` |
| **Thread** kết thúc | `Thread.join(timeout)` | Trả `void`; kiểm tra `isAlive()` |
| Kết quả bất đồng bộ theo pipeline | `CompletableFuture.orTimeout(...)` / `completeOnTimeout(...)` | Hoàn tất future theo chính sách timeout của API, không mặc nhiên dừng side effect nguồn |

**Lưu ý về `CompletableFuture`:** `orTimeout` làm future hoàn tất ngoại lệ nếu chưa xong đúng hạn; `completeOnTimeout` hoàn tất với giá trị dự phòng khi hết hạn. Cả hai áp dụng lên **trạng thái của future**, không phải cách cưỡng ép ngừng mọi tác vụ thực thi bên dưới. `CompletableFuture.get(timeout, unit)` là timeout riêng cho thao tác đợi của caller, không tự biến future thành kết quả timeout.

## 14. Checklist cho thiết kế có timeout

1. **Xác định điều kiện thật:** cần dữ liệu, permit, lock, tín hiệu, thread đã kết thúc hay kết quả task?
2. **Chọn API có timeout tương ứng:** `poll`, `tryLock`, `tryAcquire`, `await`, `Future.get` hoặc timed join.
3. **Đọc đúng kết quả:** `null`/`false`/`TimeoutException`/`void` có ý nghĩa khác nhau.
4. **Định nghĩa tổng ngân sách:** timeout của một thao tác hay deadline cho toàn bộ workflow? Truyền thời gian **còn lại** qua các bước.
5. **Dùng `nanoTime` cho elapsed**, không tính deadline tương đối bằng wall clock nếu tránh được.
6. **Cân nhắc spurious wakeup:** kiểm tra predicate bằng `while`; không reset ngân sách vô hạn.
7. **Giải phóng tài nguyên chính xác:** `finally` cho lock, permit và tài nguyên đã acquire; không release khi thất bại.
8. **Phân biệt timeout và cancellation:** nếu không nhận kết quả, task/producer có còn chạy không? Có cần gửi tín hiệu hủy hợp tác?
9. **Bảo vệ dữ liệu đã lấy/đã ghi:** khi timeout ở bước sau, item hoặc side effect trước đó phải được xử lý đúng, không tự động biến mất.
10. **Xử lý interrupt riêng:** propagate hoặc phục hồi cờ nếu bắt; tránh swallowing.
11. **Kiểm thử cả thành công và hết hạn:** tạo điều kiện test có kiểm soát bằng latch/lock, không dựa vào sleep tình cờ.
12. **Đo dưới tải thực:** tỉ lệ timeout, queue latency, lock contention, tail latency, số lần retry và khả năng hệ thống hồi phục sau quá tải.

**Ghi nhớ:** timeout chỉ **giới hạn nỗ lực chờ** một điều kiện, không bảo đảm tác vụ nguồn đã hoàn tất hay đã bị hủy. Java cung cấp các API chờ có thời hạn cho queue, lock, semaphore, latch, condition, future và thread. Sử dụng đúng return value/exception, một ngân sách thời gian chung khi cần, cleanup trong `finally` và giao thức cancellation/ownership phù hợp sẽ giúp tránh treo vô hạn mà không làm mất tính đúng đắn của chương trình đồng thời.