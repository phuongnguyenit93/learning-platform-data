# Giữ invariant khi chờ và sau khi thức dậy trong Java Synchronization

## Mục tiêu và phạm vi

Khi nhiều thread phối hợp qua một trạng thái chia sẻ, một thread có thể phải **chờ điều kiện** trước khi tiếp tục. Ví dụ consumer đợi buffer có dữ liệu, producer đợi còn chỗ trống, hoặc worker đợi một cờ `ready`. Gọi `wait()` hay `Condition.await()` chỉ là một phần nhỏ của bài toán: trước khi nhả khóa, trạng thái phải **nhất quán**; sau khi được đánh thức và lấy lại khóa, thread phải **kiểm tra lại điều kiện**, vì một tín hiệu không bảo đảm điều kiện vẫn đúng.

Bài này giúp bạn:
- Phân biệt **invariant** của đối tượng với **condition predicate** của thao tác đang chờ.
- Hiểu giao thức **giữ khóa → kiểm tra predicate → chờ và nhả khóa → lấy lại khóa → kiểm tra lại → hành động**.
- Biết vì sao phải dùng `while` thay vì `if` quanh `wait()/await()`, kể cả khi có `notifyAll()/signalAll()`.
- Tránh lỗi lost notification, trạng thái trung gian sai invariant, đánh thức nhầm nhóm waiter, timeout được tính lại sai và bỏ qua `InterruptedException`.
- Sử dụng monitor `synchronized` và `ReentrantLock` + `Condition`, nhận biết lúc nào nên dùng `BlockingQueue` hoặc `CountDownLatch`.
- Tự chạy các ví dụ **Java 17+** với kết quả, lập luận invariant và giới hạn của demo được nêu rõ.

**Phạm vi:** các primitive đồng bộ của Java và Java Memory Model nói chung. Không sử dụng annotation, executor hoặc tính năng riêng của Spring vì đã có chương riêng về Spring.

## 1. Invariant và predicate không phải cùng một điều

**Invariant (bất biến)** mô tả quan hệ phải đúng khi một đối tượng chia sẻ ở trạng thái có thể được các thread khác quan sát theo giao thức của đối tượng.

Với bounded buffer có sức chứa `capacity` và `size` là số phần tử:

~~~text
0 <= size <= capacity
size == số phần tử đang thực có trong buffer
các phần tử được lấy theo đúng thứ tự FIFO nếu buffer cam kết FIFO
~~~

Đối với producer và consumer, **predicate** để một thao tác được phép tiến lên lại khác:

~~~text
Producer đưa một phần tử: notFull  = (size < capacity)
Consumer lấy một phần tử: notEmpty = (size > 0)
~~~

Một buffer rỗng **vẫn thỏa invariant**, nhưng predicate của consumer đang sai nên consumer phải chờ. Một buffer đầy **vẫn thỏa invariant**, nhưng producer cần chờ. Khi các thread thay đổi buffer, chúng phải luôn giữ invariant đúng tại những điểm **nhả lock, đi vào wait hoặc công bố trạng thái**; một predicate đang chờ có thể đổi từ đúng sang sai mà invariant vẫn luôn đúng.

Ví dụ buffer capacity=1, đang chứa `A`:

| Thời điểm | `size` | Invariant | `notEmpty` | `notFull` |
| --- | ---: | --- | --- | --- |
| Trước khi lấy A | 1 | Đúng | Đúng | Sai |
| Sau khi lấy A | 0 | Đúng | Sai | Đúng |
| Sau khi thêm B | 1 | Đúng | Đúng | Sai |

**Nguyên tắc:** invariant bảo vệ **sự hợp lệ của state**; predicate quyết định **quyền thực hiện thao tác tiếp theo**. Một signal chỉ nói “trạng thái có thể đã thay đổi”; nó không trực tiếp thay cho predicate.

## 2. Vì sao cần kiểm tra và đợi trong cùng giao thức khóa?

Sai lầm kinh điển:

~~~java
// Minh họa logic sai: check và wait không được phối hợp.
if (!ready) {
    waitForSignal();
}
~~~

Nếu thread A nhìn thấy `ready=false`, thread B đổi `ready=true` và phát tín hiệu, rồi A mới bắt đầu đợi, tín hiệu đã qua. A có thể chờ mãi dù trạng thái đã sẵn sàng. Đây là dạng **missed notification / lost signal**.

Với monitor, mẫu đúng:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    // Chỉ tiến lên khi predicate đúng dưới monitor.
    consumeProtectedState();
}
~~~

Đây là **đoạn minh họa trong method**, giả định `monitor`, `ready`, `consumeProtectedState()` đã khai báo và `InterruptedException` được xử lý/khai báo. Thread sửa state phải sử dụng **cùng monitor**:

~~~java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
~~~

Trình tự:
1. Thread chờ lấy monitor rồi đọc predicate.
2. Nếu predicate sai, nó gọi `monitor.wait()` **khi vẫn đang giữ monitor đó**.
3. `wait()` đặt thread vào wait set và **nhả monitor của `monitor`** để thread khác có thể lấy lock, thay đổi trạng thái và phát signal.
4. Khi `wait()` trở về bình thường, thread đã **lấy lại monitor**; nó lặp qua `while` để kiểm tra predicate mới.
5. Chỉ khi predicate đúng, thread mới thực hiện thao tác và cập nhật trọn invariant trong vùng lock cần thiết.

Việc kiểm tra và bắt đầu chờ được phối hợp thông qua cùng monitor nên producer không thể chen vào “khoảng giữa” và khiến một lần cập nhật hợp lệ bị bỏ lỡ. Nếu producer cập nhật **trước** khi consumer lấy monitor, consumer quan sát predicate đúng và **không chờ**. Ta không cần đếm các `notify` đã gửi: **state mới là sự thật**.

### Wait nhả lock nào?

`Object.wait()` chỉ nhả **monitor của đối tượng gọi `wait()`**; nó không tự nhả những monitor/`ReentrantLock` khác mà thread đang giữ. Trước khi quay về hoặc ném `InterruptedException`, thread phải lấy lại monitor được dùng để chờ. Nếu code giữ thêm lock B trong khi `wait()` trên A, các thread cần B vẫn có thể bị kẹt: đây là một nguồn deadlock cần tránh.

`Thread.sleep()` **không nhả monitor**. Vì vậy, gọi `Thread.sleep(100)` bên trong `synchronized` không thể thay cho một condition wait hợp lệ.

## 3. Giữ invariant trước khi nhả khóa

Xét một số lượng `total` được chia thành `available` và `reserved`:

~~~text
available >= 0
reserved >= 0
available + reserved == total
~~~

Đoạn sau sai về nguyên tắc:

~~~java
synchronized (lock) {
    available--; // Invariant available + reserved == total bị sai tạm thời.
    lock.wait(); // Nhả lock khi trạng thái chưa nhất quán.
    reserved++;  // Có thể chưa bao giờ đến đây.
}
~~~

Đây là **đoạn cố ý sai**, chỉ minh họa lỗi, không phải class chạy độc lập. Khi `wait()` nhả monitor, các thread khác lấy được `lock` sẽ có thể nhìn thấy `available + reserved == total - 1`. Nếu thread bị interrupt, phần tăng `reserved` có thể không chạy. `synchronized` tự nhả lock khi ra khỏi khối nhưng **không rollback dữ liệu**.

Đúng hơn là **chờ trước khi bắt đầu thay đổi invariant**, rồi cập nhật đầy đủ dưới lock:

~~~java
synchronized (lock) {
    while (available == 0) {
        lock.wait();  // State vẫn hợp lệ trước khi nhả lock.
    }

    available--;
    reserved++;       // Hoàn tất một chuyển đổi hợp lệ.
}
~~~

Đây cũng là đoạn trong method có `throws InterruptedException` và các field được khai báo. Đường trả lại tài nguyên phải sửa hai field dưới **cùng `lock`** rồi `notifyAll()` khi có thể khiến `available > 0`.

Trong một critical section có thể có trạng thái trung gian khi thread vẫn nắm lock, nhưng phải cẩn thận với callback, phương thức synchronized reentrant và exception. Một phương thức khác có thể được gọi trong khi state chưa hoàn chỉnh và quan sát sai invariant. Tốt nhất là **validate trước, commit trạng thái ngắn và liền mạch, khôi phục invariant trước bất kỳ lệnh wait/unlock/return nào**.

## 4. Vì sao sau khi thức dậy phải dùng while?

`Object.wait()` và `Condition.await()` có thể kết thúc chờ **khi predicate vẫn sai**. Có ít nhất ba lý do:

1. **Spurious wakeup:** Java cho phép wait/await trở về dù không có tín hiệu ứng với predicate. Vì vậy phải viết code chịu được trường hợp này.
2. **Nhiều waiter tranh tài nguyên:** Hai consumer cùng được `notifyAll()`, nhưng consumer đầu tiên lấy phần tử duy nhất; consumer thứ hai lấy lại lock sau đó thì buffer đã rỗng.
3. **State đổi sau signal:** Producer phát tín hiệu, rồi một thread khác có thể chiếm lock và tiêu thụ tài nguyên trước waiter cũ.

~~~text
Hai consumer C1, C2 đang đợi notEmpty.
Producer thêm đúng một item X và notifyAll().

C1 lấy monitor trước --> lấy X, size=0, nhả monitor.
C2 lấy monitor sau  --> size vẫn bằng 0.

if (!queue.isEmpty()) { wait(); }  // SAI: sau wakeup có thể remove rỗng.
while (queue.isEmpty()) { wait(); } // ĐÚNG: kiểm tra lại trước khi remove.
~~~

Mẫu đúng của consumer là:

~~~java
synchronized (monitor) {
    while (queue.isEmpty()) {
        monitor.wait();
    }
    return queue.removeFirst();
}
~~~

Đây là đoạn minh họa bên trong method có `throws InterruptedException`. **Lần kiểm tra cuối cùng và `removeFirst()` nằm dưới cùng monitor**. Nếu bỏ lock giữa hai bước, race check-then-act quay lại.

Không được dùng một biến kiểu `receivedNotify` làm nguồn sự thật rồi bỏ qua predicate của queue. `notify()/notifyAll()` không chứa phần tử, không tự bảo đảm số lượng tài nguyên, và tín hiệu không được tích lũy cho những waiter sẽ bắt đầu chờ về sau.

## 5. Object.wait(), notify() và notifyAll() đúng hợp đồng

| API | Vai trò | Quy tắc quan trọng |
| --- | --- | --- |
| `monitor.wait()` | Chờ không giới hạn thời gian | Caller phải giữ monitor; nhả monitor khi chờ và lấy lại trước khi trở về |
| `monitor.wait(timeoutMillis)` | Chờ có giới hạn | `wait(0)` nghĩa là không giới hạn; timeout không bảo đảm predicate đúng |
| `monitor.notify()` | Đánh thức **một** waiter bất kỳ trong wait set | Không chọn theo nghiệp vụ, không bảo đảm fairness; caller phải giữ monitor |
| `monitor.notifyAll()` | Đánh thức mọi waiter trong wait set | Mỗi waiter phải tranh monitor và kiểm tra lại predicate |
| `Thread.sleep(duration)` | Tạm ngừng theo thời gian | **Không nhả monitor**, không phải cơ chế condition synchronization |

Cả `wait`, `notify` và `notifyAll` yêu cầu thread gọi đang giữ **chính monitor đó**. Nếu không có `synchronized(monitor)` hoặc quyền sở hữu monitor tương đương, chúng ném `IllegalMonitorStateException`. Giữ monitor của **object khác** không hợp lệ.

### Tín hiệu không chuyển lock ngay lập tức

~~~java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
    // Thread hiện tại vẫn giữ monitor đến khi rời block.
}
~~~

Các waiter được đánh thức chưa thể chạy code sau `wait()` cho tới khi đã lấy lại monitor. Nếu thread phát tín hiệu giữ lock rất lâu sau `notifyAll()`, latency thức dậy cũng dài.

### Khi nào notifyAll() hợp lý?

Nếu cùng một monitor có nhiều loại waiter, ví dụ producers đợi `notFull` còn consumers đợi `notEmpty`, `notify()` có thể chọn một waiter **đang đợi predicate chưa đúng**. Nó thức dậy, tự chờ lại, trong khi waiter thuộc nhóm cần chạy vẫn ngủ. Trong giao thức monitor chung, `notifyAll()` thường dễ chứng minh tiến triển hơn. Đổi lại, đánh thức nhiều waiter có thể gây thêm contention.

`Condition` với `ReentrantLock` giúp mỗi predicate có một wait set riêng (`notFull`, `notEmpty`), nên có thể `signal()` đúng nhóm. Ngay cả khi signal đúng nhóm, **predicate vẫn phải được kiểm tra lại trong while**.

## 6. Ví dụ chạy được 1: bounded buffer dùng wait/notifyAll

Một bounded buffer có hai predicate, `queue.size() < capacity` cho producer và `!queue.isEmpty()` cho consumer. Ta giữ cùng monitor cho **kiểm tra**, **cập nhật queue**, **tín hiệu** và **snapshot size**.

Tạo file **`MonitorBufferDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class MonitorBufferDemo {
    static final class BoundedBuffer<T> {
        private final ArrayDeque<T> queue = new ArrayDeque<>();
        private final int capacity;

        BoundedBuffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        synchronized void put(T value) throws InterruptedException {
            Objects.requireNonNull(value);
            while (queue.size() == capacity) {
                wait();
            }
            queue.addLast(value);
            notifyAll();
        }

        synchronized T take() throws InterruptedException {
            while (queue.isEmpty()) {
                wait();
            }
            T value = queue.removeFirst();
            notifyAll();
            return value;
        }

        synchronized int size() {
            return queue.size();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BoundedBuffer<Integer> buffer = new BoundedBuffer<>(2);
        List<Integer> received = new ArrayList<>();

        Thread consumer = new Thread(() -> {
            try {
                for (int i = 0; i < 6; i++) {
                    received.add(buffer.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 6; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        consumer.start();
        producer.start();

        producer.join();
        consumer.join();

        System.out.println("received=" + received);
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Biên dịch và chạy Java 17+:

~~~bash
javac MonitorBufferDemo.java
java MonitorBufferDemo
~~~

Stdout khi không có interruption:

~~~text
received=[1, 2, 3, 4, 5, 6]
remaining=0
~~~

**Vì sao đúng?**

- Một producer đưa lần lượt số 1–6, một consumer lấy lần lượt sáu phần tử, và queue cam kết FIFO. Thứ tự được giữ dù thread nào được chạy trước.
- `put()` chỉ thêm khi `queue.size() < capacity`; `take()` chỉ lấy khi `!queue.isEmpty()`.
- Không thread nào truy cập trực tiếp `ArrayDeque` từ bên ngoài buffer. **Mọi đường truy cập** đều qua monitor của đối tượng buffer.
- `wait()` chỉ được gọi trong lúc queue vẫn hợp lệ; nó nhả monitor để phía kia có thể thay đổi queue.
- Sau wakeup, `while` lặp kiểm tra lại predicate. `notifyAll()` được phát **sau khi state đổi**, giúp phía đối diện thử tiến lên.
- `join()` khiến main đọc `received` sau khi consumer đã kết thúc. List `received` chỉ được consumer ghi; main không đọc song song với nó.

**Giới hạn:** Demo biết trước số lần truyền và nhận, không có hủy công việc, shutdown bất thường hoặc timeout. Nếu producer dừng sớm vì lỗi, consumer có thể chờ vô hạn; code production cần protocol `close`/end-of-stream, timeout hoặc cancellation rõ ràng. `ArrayDeque` không thread-safe khi dùng trực tiếp; sự an toàn ở đây đến từ monitor bảo vệ buffer. Đối với producer–consumer thông thường, cân nhắc `BlockingQueue` chuẩn thay vì viết tay.

### Phân tích invariant qua một lần chờ

~~~text
Consumer giữ monitor:
  size == 0 => chưa thể take, invariant vẫn đúng
     |
     v
  wait() nhả monitor
     |
     v
Producer lấy monitor, put(X), size == 1, notifyAll(), nhả monitor
     |
     v
Consumer lấy lại monitor, kiểm tra size > 0
     |
     +-- true: lấy X, size == 0, invariant vẫn đúng
     |
     +-- false: tiếp tục wait nếu consumer khác đã lấy X
~~~

Giữa kiểm tra predicate cuối và thao tác lấy phần tử, **không nhả monitor**. Do đó không có interleaving gây remove-from-empty ở chính critical section đó.

## 7. Ví dụ chạy được 2: Gate giữ trạng thái, không phụ thuộc notify

Một `Gate` ban đầu đóng; mọi thread gọi `awaitOpen()` phải đợi đến khi `open()` được gọi. Trạng thái open **được lưu lại**; waiter đến sau vẫn đi qua mà không đòi hỏi một notification mới.

Tạo file **`GateInvariantDemo.java`**:

~~~java
public class GateInvariantDemo {
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

        synchronized boolean isOpen() {
            return open;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        Thread[] workers = new Thread[3];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    gate.awaitOpen();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "waiter-" + i);
            workers[i].start();
        }

        gate.open(); // Có thể xảy ra trước khi một waiter thật sự chờ.

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("open=" + gate.isOpen());
        System.out.println("completed=3");
    }
}
~~~

Chạy:

~~~bash
javac GateInvariantDemo.java
java GateInvariantDemo
~~~

Stdout bình thường:

~~~text
open=true
completed=3
~~~

Dù main mở gate rất sớm, những thread bắt đầu sau vẫn kiểm tra `open==true` và **không gọi wait**. Nếu một waiter đã ở wait set, `notifyAll()` giúp nó tỉnh dậy để kiểm tra predicate. Main không khẳng định thứ tự thực thi workers, chỉ đợi chúng kết thúc bằng `join()`. Đây là mẫu cho **điều kiện một chiều**. Nếu mở/đóng gate nhiều lần hoặc có các pha, phải định nghĩa generation/phase; `CountDownLatch` (one-shot), `CyclicBarrier` hoặc `Phaser` thường phù hợp hơn.

## 8. Condition.await(): cùng nguyên tắc, nhiều wait set

`ReentrantLock` kết hợp `Condition` cũng có giao thức **predicate dưới lock**. Nó giúp phân nhóm producer và consumer theo hai điều kiện riêng.

Mẫu:

~~~java
lock.lockInterruptibly();
try {
    while (!ready) {
        condition.await();
    }
    useState();
} finally {
    lock.unlock();
}
~~~

Đây là đoạn minh họa trong method có `lock`, `condition`, `ready` và `useState` đã khai báo. Những quy tắc cần giữ:
- Caller phải đang giữ đúng `ReentrantLock` liên kết với `Condition`.
- `await()` nhả lock trong khi chờ, rồi **lấy lại lock trước khi trở về** hoặc ném `InterruptedException`.
- `signal()`/`signalAll()` phát tín hiệu cho đúng condition; thread phát signal vẫn giữ lock cho tới khi unlock.
- Waiter kiểm tra lại predicate bằng `while`, kể cả khi có signal hoặc spurious wakeup.
- `unlock()` luôn ở `finally`; lock phải bao trọn phần đổi invariant.

### Ví dụ chạy được 3: buffer có notFull và notEmpty

Tạo file **`ConditionBufferDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionBufferDemo {
    static final class Buffer<T> {
        private final ArrayDeque<T> items = new ArrayDeque<>();
        private final int capacity;
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();

        Buffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity <= 0");
            }
            this.capacity = capacity;
        }

        void put(T item) throws InterruptedException {
            Objects.requireNonNull(item);
            lock.lockInterruptibly();
            try {
                while (items.size() == capacity) {
                    notFull.await();
                }
                items.addLast(item);
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        T take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (items.isEmpty()) {
                    notEmpty.await();
                }
                T result = items.removeFirst();
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }

        int size() {
            lock.lock();
            try {
                return items.size();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Buffer<Integer> buffer = new Buffer<>(2);
        List<Integer> received = new ArrayList<>();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread consumer = new Thread(() -> {
            try {
                for (int i = 0; i < 5; i++) {
                    received.add(buffer.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        producer.start();

        producer.join();
        consumer.join();

        System.out.println("received=" + received);
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Chạy:

~~~bash
javac ConditionBufferDemo.java
java ConditionBufferDemo
~~~

Stdout trong đường thực thi bình thường:

~~~text
received=[1, 2, 3, 4, 5]
remaining=0
~~~

Buffer dùng một `ReentrantLock` bảo vệ **tất cả** truy cập `items`. Producer chỉ `await` trên `notFull`; consumer chỉ `await` trên `notEmpty`. Mỗi cập nhật thành công phát signal cho phía đối diện khi predicate có thể đã đúng, nhưng waiter vẫn kiểm tra lại `while`. `signal()` cho một waiter phù hợp với kiểu buffer này; với protocol phức tạp, cần xem xét liveness và khả năng phải dùng `signalAll()`.

**Chú ý:** một `Condition` không tự khiến tất cả thao tác với một data structure an toàn. Nếu code bên ngoài trực tiếp sửa `items` mà không giữ `lock`, invariant vẫn có thể bị phá.

## 9. Timeout: thức dậy vì hết hạn không phải predicate đúng

`Object.wait(long millis)` hỗ trợ thời gian chờ; `wait(0)` nghĩa là chờ vô hạn. `Condition.await(long, TimeUnit)` có kết quả theo tín hiệu/timeout, và `Condition.awaitNanos` trả thời gian còn lại. Nhưng trong mọi trường hợp, khi quay về từ wait:
- Timeout **không** biến false thành true.
- Signal **không** chứng minh predicate vẫn true khi waiter giữ lại lock.
- Spurious wakeup **không** thay đổi invariant nghiệp vụ.

Cách sai:

~~~java
while (!ready) {
    monitor.wait(1000);
}
~~~

Nếu cứ dùng lại nguyên một giây sau mỗi lần thức dậy, tổng thời gian có thể kéo dài vượt một giây nhiều lần. Ngoài ra, nếu thực sự cần hard deadline, phải tính cả thời gian đợi lock.

### Mẫu Condition.awaitNanos để quản lý ngân sách chờ

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Các field và method trong một class, không phải file độc lập:
private final ReentrantLock lock = new ReentrantLock();
private final Condition changed = lock.newCondition();
private boolean ready;

public boolean awaitReady(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0) {
                return false;
            }
            remaining = changed.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}

public void publishReady() {
    lock.lock();
    try {
        ready = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}
~~~

`awaitNanos` nhả lock rồi lấy lại trước khi quay về; mỗi lần tỉnh thread lặp kiểm tra predicate, và `remaining` được giảm theo hợp đồng API để không “cấp lại” nguyên timeout. Nếu timeout, method trả `false` mà không sửa trạng thái, và `finally` nhả lock.

**Giới hạn:** ngân sách trên áp dụng cho **thời gian chờ condition**; `lockInterruptibly()` lúc đầu có thể đợi lâu mà chưa trừ vào `remaining`. Nếu cần deadline cho toàn bộ hành trình bao gồm cả lock acquisition, tính deadline từ `System.nanoTime()` và sử dụng `tryLock(remaining, unit)` hoặc giao thức tương đương. Không tuyên bố một timed wait riêng là deadline end-to-end của cả request.

## 10. Interrupt và exception phải bảo toàn state

### 10.1. InterruptedException khi đang wait/await

Khi bị interrupt, `Object.wait()`/`Condition.await()` có thể ném `InterruptedException`. Với monitor wait, thread phải lấy lại monitor trước khi exception được ném theo hợp đồng. **Interruption không có nghĩa điều kiện đã đúng**.

Trong buffer:
- `put` bị interrupt khi đang đợi chỗ trống: vì chưa gọi `addLast`, lần put đó chưa thêm phần tử.
- `take` bị interrupt khi đợi có dữ liệu: vì chưa gọi `removeFirst`, lần take đó chưa lấy phần tử.
- Các thread khác vẫn có thể đã thay đổi buffer trong lúc thread này chờ; không nên hiểu “không có cập nhật từ thao tác bị ngắt” thành “buffer không đổi”.

Nếu phương thức có thể ném tiếp exception, thường nên `throws InterruptedException` để caller quyết định cancellation. Nếu không thể ném lên và cần thoát:

~~~java
try {
    doInterruptibleWait();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Khôi phục cờ interrupt.
    return;
}
~~~

Đây là đoạn minh họa trong một method `void`. Không nuốt interruption rồi chờ mãi nếu ứng dụng có quy trình shutdown.

### 10.2. Lock được nhả không có nghĩa thay đổi được rollback

~~~java
synchronized (monitor) {
    available--;
    operationThatMayThrow();
    reserved++;
}
~~~

Đoạn trên minh họa lỗi: nếu method giữa chừng ném exception, `synchronized` tự nhả monitor khi thoát, nhưng invariant `available + reserved == total` có thể sai. Cần **validate trước khi commit**, thực hiện thay đổi nhất quán dưới lock, hoặc có rollback chính xác khi exception xảy ra. Giảm phạm vi side effect có thể ném trong lúc invariant tạm chưa đúng.

Với `ReentrantLock`, dùng:

~~~java
lock.lock();
try {
    // Kiểm tra predicate và cập nhật invariant trọn vẹn.
} finally {
    lock.unlock();
}
~~~

Đây là đoạn minh họa, giả định `lock` đã khởi tạo. Không bỏ `unlock()` trong nhánh exception; cũng không cố unlock khi chưa thực sự lấy được lock.

### 10.3. Shutdown và điều kiện sẽ không bao giờ đúng

Nếu producer ngừng vĩnh viễn mà consumer đợi `notEmpty` không thời hạn, chương trình có thể treo dù invariant vẫn đúng. Một protocol thực phải mô tả điều kiện **closed/cancelled** và đánh thức waiter:

~~~java
synchronized (monitor) {
    while (queue.isEmpty() && !closed) {
        monitor.wait();
    }
    if (queue.isEmpty() && closed) {
        // Kết thúc theo hợp đồng, ví dụ trả Optional.empty().
    } else {
        // Lấy phần tử đang có.
    }
}
~~~

Đây là **pseudocode Java** minh họa control flow với `monitor`, `queue`, `closed` được bảo vệ cùng lock, không phải method chạy độc lập. Đường `close` cần đặt `closed=true` và `notifyAll()` khi giữ monitor. Khi có nhiều loại waiter, phải xem xét shutdown có đánh thức **mọi nhóm đang chờ** không. Nếu dùng queue chuẩn, có thể dùng sentinel/poison pill hoặc cancellation protocol thích hợp, bảo đảm không nhầm sentinel với dữ liệu hợp lệ.

## 11. Happens-before và memory visibility

Giao thức monitor vừa tránh lost notification vừa đảm bảo visibility:

~~~java
// Producer:
synchronized (monitor) {
    data = prepared;
    ready = true;
    monitor.notifyAll();
}

// Consumer:
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    use(data);
}
~~~

Đây là hai đoạn minh họa dùng các biến và method khai báo ở phạm vi bên ngoài. Theo Java Memory Model, các ghi trước **unlock** một monitor happens-before các hành động sau **lock** tiếp theo trên cùng monitor. Vì vậy consumer sau khi lấy lại monitor có cơ chế để thấy dữ liệu producer công bố. Chỉ gọi `notifyAll()` mà không bảo vệ predicate/dữ liệu chia sẻ theo một giao thức memory visibility thì chưa đủ.

`Condition.await()` đi kèm `ReentrantLock` cũng nhả/lấy lại đúng lock và hưởng memory semantics tương ứng. Các lớp `BlockingQueue`, `CountDownLatch`, `Semaphore`, `Future` có hợp đồng memory consistency riêng; khi dùng đúng abstraction có thể tránh rất nhiều lỗi chứng minh thủ công.

**Không** thay vòng chờ bằng cách nhìn `thread.getState() == WAITING` hoặc dựa vào `Thread.sleep`. `Thread.State` chỉ là một snapshot tại thời điểm đọc, không thể quyết định an toàn điều kiện nghiệp vụ, và không cung cấp mutual exclusion.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `if (!ready) wait()` | Spurious wakeup hoặc waiter khác làm predicate sai | Dùng `while (!ready) wait()` |
| Kiểm tra ready ở ngoài lock rồi mới wait | Có khoảng trống mất tín hiệu | Kiểm tra và wait dưới cùng monitor |
| Gọi wait/notify mà không giữ monitor đúng | `IllegalMonitorStateException` | Giữ đúng monitor khi gọi |
| Wait trong lúc invariant đang bị phá dở | Nhả monitor cho thread khác đọc state sai | Khôi phục invariant trước wait/unlock |
| Tin rằng notifyAll làm waiter chạy ngay | Thread còn phải lấy lại monitor | Giữ critical section ngắn, check predicate |
| Chỉ notify với nhiều loại waiter khác nhau | Có thể đánh thức thread không tiến triển | `notifyAll` hoặc nhiều `Condition` |
| Dùng sleep trong synchronized để chờ | Không nhả monitor, không theo predicate | `wait/await` hoặc primitive cấp cao |
| Timed wait tính lại nguyên timeout mỗi vòng | Nhiều lần tỉnh kéo dài vượt mục tiêu | Deadline hoặc remaining time |
| Bỏ qua InterruptedException | Hủy/shutdown có thể bị treo | Propagate hoặc restore interrupt rồi thoát |
| Exception giữa hai bước cập nhật invariant | Lock nhả nhưng state không tự rollback | Commit nguyên tử/rollback có cấu trúc |
| Chờ vô hạn không có protocol close | Thread có thể đợi không bao giờ xong | Closed flag, signal, timeout/cancel |
| Đọc state ngoài lock đã thống nhất | Visibility hoặc snapshot không nhất quán | Cùng lock hoặc safe published snapshot |
| Gắn quyết định notify với getState() | Snapshot có race, không là predicate | Dựa vào state được bảo vệ |
| Giữ lock khác khi gọi wait | Wait không nhả mọi lock; có thể deadlock | Kiểm soát lock ordering và phạm vi lock |

## 13. Hướng thiết kế và kiểm chứng

**Bước 1 — Viết invariant:** mô tả điều phải luôn đúng khi đối tượng nhả lock. Với buffer: `0 <= size <= capacity`, size bằng số phần tử thực.

**Bước 2 — Viết predicate của từng kiểu waiter:** producer chờ `size < capacity`, consumer chờ `size > 0`. Nếu có trạng thái closed hoặc nhiều pha, kết hợp nó vào điều kiện một cách rõ ràng.

**Bước 3 — Chọn một khóa bảo vệ trạng thái:** mọi đường đọc/ghi liên quan invariant phải dùng cùng monitor/lock, hoặc một giao thức ownership khác có bảo đảm tương ứng. Không để callback sửa state trực tiếp ngoài khóa.

**Bước 4 — Kiểm tra invariant tại điểm nhả lock:** trước khi `wait()`, `await()`, return hoặc exception làm rời critical section, state phải nhất quán.

**Bước 5 — Khi thức dậy, kiểm tra lại predicate:** luôn dùng `while`; đừng suy ra predicate đúng từ việc có signal.

**Bước 6 — Signal sau khi thay đổi state:** phát tín hiệu dưới đúng monitor/lock, đúng loại waiter, và đừng quên shutdown/closed. Signal không làm thay predicate.

**Bước 7 — Thiết kế lỗi và timeout:** mỗi waiter có đường ra khi producer không còn tiếp tục, khi bị interrupt hoặc khi deadline hết; không để trạng thái nửa cập nhật rò ra.

**Bước 8 — Chọn abstraction cấp cao khi phù hợp:** `BlockingQueue` cho producer/consumer, `CountDownLatch` cho one-shot readiness, `Semaphore` cho permits, `Phaser` cho nhiều pha. Tự viết monitor protocol khi invariant thực sự đặc biệt.

**Bước 9 — Test các interleaving quan trọng:** signal tới trước khi waiter bắt đầu chờ; hai waiter thức dậy tranh một phần tử; timeout trước/sau signal; interrupt trong wait; exception ở giữa cập nhật; close khi queue trống. Dùng `CountDownLatch`/barrier để điều phối test, **không coi `Thread.sleep` là bằng chứng ordering**.

**Bước 10 — Quan sát liveness và performance:** kiểm tra không deadlock, không starvation bất thường, không tăng queue vô hạn; đo queue wait, lock contention, successful throughput, p95/p99 latency và lỗi. Một trạng thái luôn thỏa invariant nhưng các thread chờ mãi vẫn là thiết kế không đạt yêu cầu hoạt động.

## 14. Câu hỏi tự kiểm tra

1. Buffer trống có vi phạm invariant `0 <= size <= capacity` không? **Không**, nhưng consumer có predicate `size > 0` đang sai.
2. Vì sao không gọi `wait` trong lúc hai trường chưa được cập nhật đồng bộ? **Vì wait nhả monitor, để thread khác nhìn trạng thái trung gian sai.**
3. Vì sao `while` cần thiết sau `notifyAll`? **Có spurious wakeup và tranh chấp khiến predicate vẫn sai.**
4. Nếu signal đến trước khi waiter vào wait set, làm sao tránh lost notification? **Ghi và đọc một predicate dưới cùng monitor; waiter sẽ bỏ qua wait khi đã đúng.**
5. `Object.wait()` nhả mọi lock thread đang giữ không? **Không, chỉ monitor của object gọi wait.**
6. `Thread.sleep()` bên trong synchronized có nhả monitor không? **Không.**
7. Vì sao `notifyAll()` không bảo đảm waiter chạy ngay? **Waiter còn phải lấy lại monitor sau khi thread phát tín hiệu nhả nó.**
8. Vì sao `wait(0)` không phải timeout ngay? **Giá trị 0 nghĩa là chờ không thời hạn.**
9. Khi `Condition.awaitNanos()` trả về nhưng predicate vẫn sai, cần làm gì? **Kiểm tra remaining và tiếp tục vòng while hoặc trả timeout.**
10. Có thể xem `InterruptedException` là predicate đã đúng không? **Không**, đó là đường hủy riêng.
11. Khi một method ném exception giữa cập nhật, synchronized tự rollback không? **Không, nó chỉ đảm bảo nhả monitor.**
12. Một consumer có thể chờ mãi nếu producer ngừng không? **Có**, nên cần giao thức close, cancellation, timeout hay sentinel.
13. Khi nào dùng `BlockingQueue` thay vì tự viết wait/notify? **Khi yêu cầu chính chỉ là chuyển phần tử từ producer sang consumer.**
14. Có thể dùng `thread.getState()` để quyết định condition đã đúng không? **Không**, đó là snapshot của thread, không phải trạng thái nghiệp vụ có lock.
15. Invariant và predicate khác nhau ở đâu? **Invariant nói đối tượng hợp lệ hay không; predicate nói một thao tác đã được phép tiến lên hay chưa.**

## Kết luận

**Invariant phải đúng ở các thời điểm quyền truy cập được bàn giao**, đặc biệt trước khi `wait()/await()` nhả lock, trước khi unlock hoặc một exception khiến method rời critical section. **Predicate phải được kiểm tra lại sau khi thread thức dậy và lấy lại lock**. Notification không lưu trạng thái nghiệp vụ, không bảo đảm waiter chạy ngay, và không chứng minh điều kiện đúng.

Một giao thức an toàn là **giữ khóa → kiểm tra predicate → chờ và nhả khóa nếu sai → lấy lại khóa → kiểm tra lại trong while → cập nhật trọn invariant → signal khi cần → nhả khóa**. Cần thêm lối thoát cho timeout, interruption và shutdown, cùng cách khôi phục invariant khi exception xảy ra.

## Tài liệu Java SE 17

- [Object.wait/notify/notifyAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): monitor, wait set, spurious wakeup, interruption.
- [Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): await, awaitNanos, signal, signalAll.
- [ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock, lockInterruptibly, unlock.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): take/put/offer/poll và memory consistency.
- [Java Language Specification, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Threads and Locks; happens-before.
