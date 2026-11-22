# Đợi monitor bằng wait() và đánh thức bằng notify()/notifyAll()

Trong Java, mọi đối tượng đều có một **intrinsic monitor** (khóa nội tại). Từ khóa `synchronized` cho phép một thread giữ monitor để bảo vệ trạng thái chia sẻ. Nhưng đôi khi giữ khóa rồi liên tục hỏi “điều kiện đã đúng chưa?” sẽ tốn CPU hoặc ngăn thread khác cập nhật dữ liệu. Java cung cấp ba phương thức của `java.lang.Object` để **phối hợp theo điều kiện** trên một monitor: `wait()`, `notify()` và `notifyAll()`.

Hãy hình dung một hộp thư chỉ chứa một thông điệp: producer phải chờ khi hộp đầy, consumer phải chờ khi hộp rỗng. `wait()` cho thread **nhả monitor và chờ**, để thread khác vào vùng `synchronized` thay đổi điều kiện. Sau khi điều kiện thay đổi, thread cập nhật có thể gọi `notify()` hoặc `notifyAll()` để đánh thức waiter.

Điều quan trọng nhất: **đánh thức không đồng nghĩa điều kiện đã đúng**; waiter phải lấy lại monitor rồi **kiểm tra lại điều kiện**.

## 1. Ba phương thức hoạt động trên monitor của đối tượng

Các phương thức này nằm trong `Object` (không riêng `Thread`), và thao tác trên **wait set** gắn với đối tượng nhận lời gọi:

| Phương thức | Ý nghĩa | Lưu ý chính |
|---|---|---|
| `lock.wait()` | Thread hiện tại nhả monitor **của `lock`** rồi vào trạng thái chờ một tín hiệu/gián đoạn. | Phải đang giữ monitor của `lock`; có thể thức dậy giả (*spurious wakeup*). |
| `lock.wait(millis)` | Tương tự nhưng có giới hạn chờ; có thể trả về khi hết thời gian. | Với overload `wait(long)`, `millis == 0` nghĩa là chờ không thời hạn. |
| `lock.notify()` | Chọn **một** thread đang chờ trong wait set của `lock` (nếu có) để đánh thức. | Không chọn theo FIFO, không bảo đảm chọn đúng điều kiện cần xử lý. |
| `lock.notifyAll()` | Đánh thức **mọi** thread đang chờ trong wait set của `lock` tại thời điểm đó. | Chúng vẫn phải tranh monitor và tự kiểm tra lại điều kiện. |

`notify()`/ `notifyAll()` **không lưu tín hiệu** cho thread bắt đầu đợi sau đó. Nếu lúc gọi không có waiter, lời notify không có người nhận. Một thiết kế đúng lưu **trạng thái điều kiện** trong biến được bảo vệ, sau đó đợi bằng vòng `while` dưới cùng monitor.

### Điều kiện sở hữu monitor

Thread phải sở hữu monitor của **đúng đối tượng** gọi `wait()`/`notify()`/`notifyAll()`. Nếu không, Java ném `IllegalMonitorStateException`. Ví dụ đúng:

```java
Object lock = new Object();

synchronized (lock) {
    lock.wait(); // Thread đang giữ monitor của lock.
}
```

Đây là **trích đoạn**, phải nằm trong phương thức khai báo hoặc xử lý `InterruptedException`. Không chạy độc lập như trên vì chờ không có thread nào đánh thức sẽ gây treo.

Trích đoạn dưới đây sai vì khóa một monitor nhưng gọi `wait()` trên đối tượng khác:

```java
Object first = new Object();
Object second = new Object();

synchronized (first) {
    second.wait(); // IllegalMonitorStateException.
}
```

Kể cả khi có `synchronized`, **đúng monitor** mới quan trọng. `synchronized(this)` không trao quyền gọi `someLock.wait()` nếu thread chưa giữ monitor của `someLock`.

## 2. wait() nhả khóa nào, giữ khóa nào?

Khi thread đang giữ monitor của đối tượng `lock` và gọi `lock.wait()`:

1. JVM đưa thread vào wait set của `lock` và nhả monitor của **chính `lock`** như một thao tác phối hợp.
2. Thread tạm dừng thực thi tại `wait()`, để thread khác có thể vào `synchronized(lock)` cập nhật trạng thái chung.
3. Khi được thông báo, bị interrupt, hết timeout hoặc tự thức dậy giả, nó phải **lấy lại monitor `lock`** trước khi `wait()` có thể hoàn tất/nhảy sang xử lý exception.
4. Sau khi lấy lại monitor, thread tiếp tục ở vùng `synchronized` và kiểm tra điều kiện.

Nếu thread giữ đồng thời monitor khác, `lock.wait()` **không tự nhả những monitor khác đó**. Điều này có thể dẫn đến deadlock nếu thread cập nhật cần monitor mà waiter vẫn giữ.

Sơ đồ dòng chảy:

```text
Thread consumer                         Thread producer
---------------                         ---------------
synchronized(lock)
  while (empty) {
    lock.wait()
       | nhả monitor lock
       v                               synchronized(lock)
    WAITING                                add item
       ^                                  lock.notifyAll()
       | được đánh thức                    | vẫn giữ lock đến khi thoát block
       +-----------------------------------+
    chờ lấy lại monitor
    kiểm tra lại empty
    lấy item
  }
thoát synchronized(lock)
```

Không có bảo đảm producer nhả khóa ngay lúc `notifyAll()`. Nó chỉ nhả khi thoát vùng `synchronized(lock)` hoặc bằng một cơ chế nhả monitor hợp lệ khác. Vì vậy câu “notify gọi xong là waiter chạy ngay” là **sai**.

## 3. Quy tắc bắt buộc: condition predicate + while + cùng monitor

Mẫu an toàn cơ bản:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Thực hiện thao tác chỉ khi condition hiện tại là true.
}
```

Đây là trích đoạn minh họa: `lock` và `condition` được giả định đã khai báo, `InterruptedException` được xử lý ở phương thức chứa nó. Để hoàn chỉnh giao thức, thread thay đổi `condition` cũng phải dùng **cùng monitor**:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
}
```

**Vì sao không dùng `if`?**

- **Spurious wakeup:** Java cho phép `wait()` trở về dù không có notify theo cách mà ứng dụng trông đợi.
- **Nhiều waiter tranh cùng tài nguyên:** một thread vừa được đánh thức có thể lấy monitor **sau** thread khác; dữ liệu đã bị thread khác tiêu thụ.
- **Sai điều kiện sau notifyAll:** nhiều thread được đánh thức nhưng chỉ một thread có điều kiện phù hợp.
- **Timeout hoặc interruption:** cần quyết định theo trạng thái và mục tiêu chờ; việc chờ kết thúc không tự chứng minh điều kiện hợp lệ.

Dùng `while` đảm bảo mọi lần thức dậy đều kiểm tra lại điều kiện dưới khóa. Cần đặt kiểm tra điều kiện và `wait()` **trong cùng một vùng `synchronized`**: nếu tách khóa, có thể xảy ra tình huống thread khác thay đổi điều kiện và notify ở khe giữa *check* và *wait*; sau đó waiter ngủ vô hạn.

Điều kiện phải là trạng thái có ý nghĩa (ví dụ `hasItem`, `closed`, `available > 0`), **không** phải “có một lời notify nào đó”. Notification là lời nhắc để kiểm tra lại trạng thái; chính predicate mới quyết định khi nào được tiếp tục.

## 4. Ví dụ 1: một waiter và notify()

Ví dụ đầu cho thấy mẫu guard bằng `while`. `CountDownLatch` chỉ giúp main biết worker đã khởi động, không dùng để truyền điều kiện `opened`.

Tạo tệp **`MonitorSignal.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorSignal {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        boolean[] opened = {false};
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                started.countDown();
                while (!opened[0]) {
                    try {
                        lock.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
            }
            System.out.println("Worker passed the gate");
        }, "worker");

        worker.start();
        started.await();

        synchronized (lock) {
            opened[0] = true;
            lock.notify();
        }

        worker.join();
        System.out.println("Main finished");
    }
}
```

```bash
javac MonitorSignal.java
java MonitorSignal
```

Kết quả:

```text
Worker passed the gate
Main finished
```

Có hai lịch chạy hợp lệ:

- Worker đã vào `wait()` trước khi main khóa monitor để mở cổng. Main cập nhật `opened[0] = true` rồi notify; worker thức dậy, lấy lại monitor, thấy điều kiện đúng và đi tiếp.
- Main lấy monitor ngay sau worker gọi `started.countDown()` nhưng **trước khi worker gọi `wait()`**. Main phải chờ worker nhả monitor mới vào được synchronized; worker thấy `opened` vẫn false và chuyển vào wait (nhả monitor), rồi main mở cổng/notify. Nếu main mở cổng trước khi worker lần đầu vào synchronized trong một biến thể không có latch, worker sẽ thấy predicate true và bỏ qua wait.

Cả hai tình huống đều an toàn do việc **kiểm tra điều kiện và đợi dùng cùng monitor**. Không có “thông báo bị thất lạc” khiến worker đợi mãi trong giao thức này. Dữ liệu `boolean[]` không đánh dấu `volatile` vì mọi lần đọc/ghi `opened[0]` đều nằm dưới `lock`; unlock/lock cùng monitor cung cấp quan hệ bộ nhớ cần thiết.

Khi chỉ có **một waiter** cần được đánh thức và một điều kiện đơn giản, `notify()` đủ. Với nhiều waiter và nhiều loại điều kiện, `notifyAll()` thường dễ lập luận đúng hơn.

## 5. notify() và notifyAll(): chọn một hay đánh thức tất cả?

`notify()` chọn một waiter bất kỳ trong wait set của monitor. Nó không bảo đảm FIFO, không ưu tiên thread chờ lâu hơn và không biết “thread nào đang đợi điều kiện phù hợp”. Nếu monitor dùng để đợi **nhiều loại điều kiện** (chẳng hạn *not-empty* cho consumer và *not-full* cho producer), `notify()` có thể đánh thức một waiter mà predicate của nó vẫn sai. Waiter ấy quay lại `wait()`, trong khi waiter khác cần tiến triển vẫn ngủ. Một lịch xen kẽ như vậy có thể dẫn đến **mất tiến triển**, dù mọi phép truy cập dữ liệu đều synchronized.

`notifyAll()` đánh thức tất cả waiter trong cùng wait set, khiến mỗi thread lần lượt tranh khóa rồi kiểm tra predicate riêng. Nó thường là lựa chọn **an toàn về tính đúng đắn** cho giao thức dùng một monitor với nhiều điều kiện và khi thay đổi trạng thái có thể cho nhiều waiter tiếp tục.

| Tình huống | Cân nhắc |
|---|---|
| Chính xác một waiter, một điều kiện | `notify()` có thể đủ. |
| Nhiều waiter, thay đổi trạng thái cho phép tất cả tiếp tục | `notifyAll()` cần thiết để không bỏ sót waiter còn hợp lệ. |
| Một monitor dùng nhiều predicate khác nhau | `notifyAll()` thường an toàn hơn `notify()`, kết hợp vòng `while` ở mỗi waiter. |
| Rất nhiều waiter, chỉ một người có thể tiến triển | `notifyAll()` có thể gây nhiều lần tranh monitor (*thundering herd*); vẫn đúng nhưng có chi phí. |
| Muốn đánh thức chính xác một nhóm điều kiện | Cân nhắc `ReentrantLock` với nhiều `Condition` riêng hoặc abstraction cấp cao. |

**Lưu ý:** ngay cả với `notifyAll()`, không phải mọi waiter đều được tiếp tục hành động. Mỗi thread phải kiểm tra lại predicate; thread nào vẫn không đủ điều kiện sẽ chờ tiếp. `notifyAll()` cũng **không bảo đảm fairness** hoặc thứ tự lấy khóa.

## 6. Ví dụ 2: notifyAll() mở cổng cho nhiều waiter

Bài toán: nhiều thread cùng chờ cổng mở. Khi cổng mở vĩnh viễn, tất cả đều được phép tiếp tục. Nếu chỉ `notify()` một lần, ít nhất một waiter có thể không được đánh thức (nếu chúng đang thực sự đợi); `notifyAll()` phù hợp hơn.

Tạo tệp **`MonitorBroadcast.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class MonitorBroadcast {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen() throws InterruptedException {
            while (!open) {
                wait();
            }
        }

        synchronized void open() {
            open = true;
            notifyAll();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        AtomicInteger passed = new AtomicInteger();

        Runnable waiter = () -> {
            try {
                gate.awaitOpen();
                passed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(waiter, "A");
        Thread b = new Thread(waiter, "B");
        Thread c = new Thread(waiter, "C");
        a.start();
        b.start();
        c.start();

        gate.open();

        a.join();
        b.join();
        c.join();
        System.out.println("Workers passed: " + passed.get());
    }
}
```

```bash
javac MonitorBroadcast.java
java MonitorBroadcast
```

Kết quả khi không có external interrupt:

```text
Workers passed: 3
```

`Gate.open()` đặt trạng thái `open = true` và gọi `notifyAll()` trong cùng synchronized method. Nếu một waiter đã chờ, nó được đánh thức và sẽ kiểm tra `open` sau khi lấy lại khóa. Nếu một waiter chưa kịp đi vào `awaitOpen()`, nó sẽ thấy `open == true` và **không chờ**. Vì vậy kết quả không phụ thuộc vào việc có waiter nào thực sự ngủ lúc `notifyAll()` được gọi. `join()` bảo đảm main đợi đủ ba thread trước khi in.

## 7. Ví dụ 3: producer–consumer với hộp thư một phần tử

Ví dụ hoàn chỉnh sử dụng **cùng một monitor** để bảo vệ hộp một slot, hai predicate và cờ đóng. Producer đợi `notFull`, consumer đợi `notEmpty`. `notifyAll()` phù hợp vì các waiter có thể chờ **các điều kiện khác nhau** trên cùng monitor.

Tạo tệp **`MonitorMailbox.java`**:

```java
public class MonitorMailbox {
    static final class Mailbox {
        private Integer value;
        private boolean closed;

        public synchronized void put(int item) throws InterruptedException {
            while (value != null && !closed) {
                wait();
            }
            if (closed) {
                throw new IllegalStateException("mailbox is closed");
            }
            value = item;
            notifyAll();
        }

        // null nghĩa là mailbox đã đóng và không còn dữ liệu.
        public synchronized Integer take() throws InterruptedException {
            while (value == null && !closed) {
                wait();
            }
            if (value == null) {
                return null;
            }
            int item = value;
            value = null;
            notifyAll();
            return item;
        }

        public synchronized void close() {
            closed = true;
            notifyAll();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox mailbox = new Mailbox();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 3; i++) {
                    mailbox.put(i);
                }
                mailbox.close();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                mailbox.close();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                Integer item;
                while ((item = mailbox.take()) != null) {
                    System.out.println("Received: " + item);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();

        producer.join();
        consumer.join();
        System.out.println("Finished");
    }
}
```

```bash
javac MonitorMailbox.java
java MonitorMailbox
```

Kết quả:

```text
Received: 1
Received: 2
Received: 3
Finished
```

**Đọc kỹ giao thức:**

1. Toàn bộ state `value` và `closed` là private và chỉ được truy cập trong synchronized method của **cùng đối tượng Mailbox**.
2. Producer gọi `put()`: nếu slot còn giá trị, nó vào `wait()` và nhả monitor để consumer có thể gọi `take()`; khi slot trống, nó ghi một item và `notifyAll()`.
3. Consumer gọi `take()`: nếu slot rỗng và chưa đóng, nó nhả monitor bằng `wait()`; khi có item, nó lấy item, làm trống slot và `notifyAll()` cho producer.
4. Producer gửi lần lượt 1, 2, 3; vì chỉ có một producer và một consumer, consumer nhận đúng thứ tự đó. Sau khi gửi xong, producer gọi `close()`.
5. `close()` đặt `closed = true` rồi `notifyAll()` để mọi waiter kiểm tra lại; consumer vẫn lấy item còn trong slot trước khi nhận `null` báo kết thúc.
6. Main `join()` cả hai thread trước khi in `Finished`, do đó output không phụ thuộc lịch lập lịch cụ thể trong trường hợp chương trình chạy bình thường, không bị external interrupt.

Nếu cần xử lý nhiều producer/consumer, chính giao thức `while` và `notifyAll()` vẫn có ý nghĩa; tuy vậy nên xác định rõ hợp đồng `close()`, dữ liệu còn lại, việc hủy tác vụ, và tránh dùng `null` làm dữ liệu thật. Đây là một ví dụ học về monitor, không phải implementation đầy đủ cho một queue sản xuất.

Trong ứng dụng Java thường ngày, `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` cung cấp cơ chế chờ/đánh thức và chính sách dung lượng đã được thư viện thiết kế, kiểm thử. Thường nên ưu tiên abstraction như `BlockingQueue` thay vì tự viết monitor khi mục tiêu chỉ là truyền dữ liệu giữa producer và consumer.

## 8. InterruptedException: đợi có thể bị ngắt

`Object.wait()` ném `InterruptedException` nếu thread bị interrupt khi đang chờ (hoặc có interrupt trước khi bắt đầu chờ theo quy tắc API). Khi exception được ném, **trạng thái interrupt của thread bị xóa**; nếu phương thức không ném tiếp mà muốn tầng gọi còn biết yêu cầu hủy, thường cần khôi phục bằng `Thread.currentThread().interrupt()`.

Một điểm quan trọng: `wait()` phải **lấy lại monitor của đối tượng** trước khi hoàn tất do thức dậy hay do interrupt. Vùng `synchronized` vẫn có tính loại trừ hỗ trợ dọn state sau lời gọi.

Ví dụ xử lý interrupt đúng khi không cần đợi nữa:

Tạo tệp **`MonitorInterrupt.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorInterrupt {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                ready.countDown();
                try {
                    lock.wait();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("Wait interrupted");
                }
            }
        }, "waiter");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("Interrupt restored: "
                + worker.isInterrupted());
    }
}
```

```bash
javac MonitorInterrupt.java
java MonitorInterrupt
```

Kết quả:

```text
Wait interrupted
Interrupt restored: true
```

`ready.countDown()` báo worker đã vào vùng khóa, nhưng tại thời điểm main gọi `interrupt()` worker **có thể vừa vào `wait()` hoặc chưa kịp gọi `wait()`**. Cả hai cách xen kẽ đều dẫn tới nhánh `InterruptedException` của lời gọi `wait()` trong ví dụ. Worker khôi phục interrupt, thoát khỏi `synchronized`; main đợi `join()` xong rồi quan sát cờ interrupt còn đặt. Việc gọi `worker.interrupt()` **không đồng nghĩa** cưỡng bức dừng thread hoặc làm `notifyAll()` trên monitor: đó là tín hiệu hủy hợp tác tới thread đích.

Không “nuốt” exception rồi tiếp tục như thể điều kiện đã đúng. Có thể ném tiếp `InterruptedException`, khôi phục cờ và kết thúc công việc, hoặc thực hiện cleanup rồi chuyển trách nhiệm hủy cho tầng gọi theo hợp đồng.

## 9. Timed wait và cách sử dụng deadline

`wait(long millis)` và `wait(long millis, int nanos)` cho phép một giới hạn thời gian. Kết quả trở về **không khẳng định điều kiện đã đúng**: có thể do notify, timeout hoặc thức dậy giả. Vì vậy guard `while` vẫn cần thiết.

Nếu chỉ chờ đến một deadline cụ thể, tính **thời gian còn lại** mỗi vòng bằng nguồn thời gian đo khoảng như `System.nanoTime()`; không gọi lại `wait(timeout)` với toàn bộ thời gian gốc sau mỗi lần thức dậy, vì tổng thời gian có thể vượt dự định. Ví dụ thuật toán (trích đoạn, không phải class chạy độc lập):

```java
long timeoutNanos = 1_000_000_000L; // 1 giây.
long deadline = System.nanoTime() + timeoutNanos;

synchronized (lock) {
    while (!condition) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            break; // Hết thời hạn; kiểm tra/đánh dấu thất bại.
        }
        long ms = remaining / 1_000_000L;
        int ns = (int) (remaining % 1_000_000L);
        lock.wait(ms, ns);
    }
}
```

Ở đây `lock`, `condition` được giả định đã khai báo, và phương thức chứa mã phải xử lý `InterruptedException`. Trong các hệ thống cần chống tràn số với timeout rất lớn, cần thêm chính sách giới hạn/kiểm soát overflow; ví dụ dùng timeout ngắn để minh họa. `wait(0)` theo overload chỉ millisecond là **chờ vô hạn**, nên khi còn thời gian nhỏ hơn 1 ms cần dùng overload có nanos như trên.

Tránh dùng `Thread.sleep()` như sự thay thế cho `wait()`: `sleep()` **không nhả monitor đang giữ**, do đó thread khác cần chính monitor đó có thể không vào được để sửa điều kiện. `wait()` được thiết kế để nhả monitor của object mà nó chờ.

## 10. wait() khác sleep(), join(), Condition và BlockingQueue

| Công cụ | Nhả monitor nào khi chờ? | Mục đích |
|---|---|---|
| `Object.wait()` | Nhả **monitor của đối tượng nhận `wait()`**, không nhả các monitor khác. | Đợi predicate của trạng thái được bảo vệ bởi monitor. |
| `Thread.sleep(...)` | Không nhả intrinsic monitor nào do thread đang giữ. | Tạm dừng tối thiểu một khoảng thời gian; không phải condition wait. |
| `Thread.join()` | Nội bộ có cơ chế chờ thread hoàn tất; không nhả các monitor không liên quan do caller giữ. | Đợi một thread kết thúc, không dùng để đánh thức theo điều kiện nghiệp vụ. |
| `ReentrantLock.newCondition()` | `Condition.await()` nhả/reacquire **associated lock** theo hợp đồng của `Condition`. | Đợi có cấu trúc với nhiều condition queues, `signal()`/`signalAll()`. |
| `CountDownLatch.await()` | Không tự nhả một intrinsic monitor bất kỳ mà caller đang giữ. | Đợi đếm tín hiệu giảm tới 0; thường là one-shot. |
| `BlockingQueue.take()/put()` | Cơ chế khóa/chờ nội bộ do collection quản lý. | Trao đổi dữ liệu producer–consumer thuận tiện và đã có contract. |

Với `ReentrantLock`, luôn giữ lock phù hợp lúc gọi `Condition.await()`/`signal()` theo contract và mở khóa trong `finally`. `Condition` cũng yêu cầu kiểm tra predicate trong vòng `while` vì thức dậy không tự làm điều kiện đúng.

Một mô hình khác thường phù hợp hơn nếu nhu cầu chỉ là chờ một sự kiện hoặc kết quả:

- `CountDownLatch` cho tín hiệu hoàn thành một lần;
- `Semaphore` cho số permit;
- `CompletableFuture`/`Future` cho kết quả tác vụ;
- `BlockingQueue` cho truyền dữ liệu;
- `Condition` với lock nếu phải điều phối nhiều predicate trong một cấu trúc dữ liệu tự viết.

## 11. Happens-before và tính hiển thị dữ liệu

Java Memory Model quy định việc **unlock một monitor** synchronizes-with lần **lock sau đó trên cùng monitor**. Khi producer đổi `value` dưới `synchronized(lock)`, sau đó waiter lấy lại monitor và đọc `value` dưới cùng khóa, các hiệu ứng được nhìn thấy theo quan hệ happens-before thích hợp.

Tương ứng, `wait()` nhả monitor để thread khác có thể thay đổi shared state, và reacquire monitor trước khi waiter kiểm tra lại. Một `notify()` đơn lẻ **không phải cơ chế thay thế** cho việc bảo vệ predicate; quan hệ bộ nhớ của vùng monitor và việc kiểm tra trạng thái dưới monitor mới là cách lập luận đầy đủ.

Không tự thêm `volatile` cho mọi field chỉ vì thấy nhiều thread: nếu **mọi đường đọc/ghi** field đều nằm trong cùng giao thức synchronized thì monitor đã cung cấp cả visibility lẫn mutual exclusion cần thiết. Nhưng nếu một nơi đọc field ở ngoài vùng synchronized và không có quy tắc đồng bộ bổ sung, class có thể không còn thread-safe.

Trong một chương trình nhiều thread, `start()` giúp công bố các hành động trước khi khởi động worker, và `join()` cho phép thread chờ kết quả sau khi worker kết thúc. Hai API đó có vai trò khác với monitor condition wait: `wait()` cho phép **phối hợp khi cả hai thread vẫn đang sống**.

## 12. Những lỗi phổ biến và hậu quả

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Gọi `wait()`/ `notify()` ngoài monitor của object nhận lời gọi | `IllegalMonitorStateException`. | Khóa đúng đối tượng bằng `synchronized(lock)` hoặc synchronized method trên `this`. |
| Dùng `if (!ready) wait()` | Có thể tiếp tục khi predicate vẫn sai. | Dùng `while (!ready) wait()` và kiểm tra lại dưới khóa. |
| Đổi điều kiện ngoài khóa rồi `notify()` trong khóa | Có thể có race/visibility bug. | Bảo vệ predicate và notification bằng cùng giao thức monitor. |
| Giữ khóa rồi `Thread.sleep()` chờ điều kiện | Thread cập nhật có thể không lấy được khóa. | `wait()` nhả monitor; hoặc dùng abstraction concurrent thích hợp. |
| Nghĩ `notify()` chuyển khóa ngay cho waiter | Waiter vẫn phải tranh và lấy lại monitor. | Thoát synchronized sớm sau khi cập nhật trạng thái khi hợp lý. |
| Dùng `notify()` với nhiều loại waiter | Có thể đánh thức sai waiter và khiến tiến triển bị kẹt. | Cân nhắc `notifyAll()` hoặc `Condition` riêng cho từng predicate. |
| Coi một lời notify là trạng thái “sự kiện đã xảy ra” | Notify trước khi có waiter không được lưu. | Lưu predicate trong state được bảo vệ; kiểm tra trước khi wait. |
| Đợi vô hạn mà không có đường đóng/hủy | Thread có thể chờ mãi. | Thiết kế tín hiệu đóng, notifyAll, interruption và timeout đúng hợp đồng. |
| Nuốt `InterruptedException` rồi tiếp tục công việc như bình thường | Hủy bỏ không được tôn trọng; có thể sai nghiệp vụ. | Ném tiếp hoặc khôi phục cờ interrupt rồi kết thúc hợp tác. |
| Gọi callback hoặc I/O kéo dài trong synchronized | Monitor bị giữ lâu, tăng contention và nguy cơ deadlock. | Giữ critical section ngắn; trao dữ liệu qua queue/abstraction cấp cao. |

**Không dùng `wait()` làm “hàng đợi thông điệp” trực tiếp.** Wait set không lưu payload, không lưu số lượt notify, không có cam kết FIFO. Hãy quản lý trạng thái rõ ràng hoặc dùng các cấu trúc đồng thời có contract phù hợp.

## 13. Cách thiết kế một giao thức monitor đúng

Trước khi viết code, hãy trả lời:

1. **Monitor nào sở hữu trạng thái?** Chọn một đối tượng lock ổn định (thường `private final Object lock` hoặc monitor instance `this` được đóng gói tốt).
2. **Predicate là gì?** Ví dụ `!queue.isEmpty()`, `queue.size() < capacity`, `closed`. Đặt tất cả đọc/ghi predicate trong giao thức đồng bộ phù hợp.
3. **Làm gì khi chưa đủ điều kiện?** Trong synchronized, `while (!predicate) lock.wait()`, với interruption/timeout được xử lý rõ.
4. **Ai đổi predicate và báo tin?** Thread thay đổi state rồi gọi `notifyAll()` (hoặc `notify()` nếu chứng minh được đủ) khi giữ đúng monitor.
5. **Có nhiều loại waiter không?** Nếu có, `notifyAll()` thường dễ bảo đảm tiến triển hơn; hoặc dùng nhiều `Condition`.
6. **Có trạng thái đóng/hủy không?** Phải đánh thức những waiter không thể tiếp tục để họ thoát, tránh giữ tiến trình sống vô hạn.
7. **Có kết quả hay dữ liệu cần truyền không?** Lưu trong state được bảo vệ hoặc dùng `BlockingQueue`/`Future`, không coi một lần notify là payload.
8. **Có nhiều monitor lồng nhau không?** `wait()` chỉ nhả monitor được gọi; tránh giữ các khóa khác khiến thread thông báo không thể tiến triển.

Đối với code học tập nhỏ, monitor rất hữu ích để hiểu JMM và condition synchronization. Với ứng dụng xử lý hàng đợi, pool, tín hiệu một lần hoặc tác vụ bất đồng bộ, các API trong `java.util.concurrent` thường mô tả nhu cầu chính xác hơn và giảm khả năng viết sai giao thức chờ/đánh thức.

## 14. Câu hỏi tự kiểm tra

1. **Vì sao `wait()` phải nằm trong `synchronized` của đúng đối tượng?** Vì nó thao tác trên wait set/monitor của đối tượng đó; không giữ monitor sẽ ném `IllegalMonitorStateException`.
2. **Khi gọi `lock.wait()`, thread có nhả mọi khóa đang giữ không?** Không. Nó nhả monitor của `lock`, không nhả các monitor khác đang giữ.
3. **`notify()` có bảo đảm thread được đánh thức chạy ngay không?** Không. Thread phải chờ lấy lại monitor; notifier vẫn giữ khóa cho tới khi nhả.
4. **Vì sao dùng `while` thay `if`?** Vì spurious wakeup, tranh chấp tài nguyên và thay đổi trạng thái có thể khiến predicate sai sau thức dậy.
5. **`notify()` khi chưa có waiter có được lưu để dùng về sau không?** Không. Phải lưu trạng thái/predicate, không dựa vào notification.
6. **Khi nào `notifyAll()` thường tốt hơn `notify()`?** Khi có nhiều waiter, nhất là nhiều predicate, hoặc một thay đổi cho phép nhiều thread cùng tiến triển.
7. **`Thread.sleep()` có nhả monitor hiện đang giữ không?** Không.
8. **`wait(timeout)` trả về có chứng minh điều kiện đúng không?** Không; phải kiểm tra lại predicate dưới khóa.
9. **`InterruptedException` từ `wait()` ảnh hưởng cờ interrupt thế nào?** Cờ bị xóa khi exception được ném; nếu không ném tiếp có thể cần khôi phục cờ.
10. **Vì sao các field không cần `volatile` trong `Mailbox`?** Vì mọi đường đọc/ghi state đều dùng cùng monitor, tạo mutual exclusion và quan hệ happens-before thích hợp.

**Ghi nhớ:** `wait()` = *nhả monitor và đợi predicate*; `notify()` = *đánh thức một waiter bất kỳ*; `notifyAll()` = *đánh thức toàn bộ waiter hiện tại*. Mọi waiter phải **lấy lại monitor, kiểm tra lại điều kiện trong `while`, và chỉ hành động khi predicate thực sự đúng**.
