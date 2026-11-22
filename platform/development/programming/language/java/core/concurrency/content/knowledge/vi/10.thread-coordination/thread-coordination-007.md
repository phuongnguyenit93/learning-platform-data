# Lock + Condition cho nhiều điều kiện chờ trong Java Concurrency

Trong một cấu trúc đồng thời, nhiều nhóm thread có thể phải chờ **những điều kiện khác nhau trên cùng một trạng thái chia sẻ**. Ví dụ, producer đợi “hàng đợi **chưa đầy**”, consumer đợi “hàng đợi **không rỗng**”, còn những thread khác có thể đợi “hệ thống **đã đóng**”. Nếu dùng một hàng đợi chờ chung và đánh thức sai nhóm, chương trình có thể làm nhiều thread thức dậy vô ích, thậm chí mắc lỗi tiến triển khi sử dụng `notify()` không phù hợp.

**`ReentrantLock` + nhiều `Condition`** cho phép một khóa bảo vệ *toàn bộ trạng thái chung*, đồng thời tạo **các hàng chờ riêng** cho từng predicate (điều kiện logic). Thread đợi trên `notEmpty` chỉ được báo hiệu bởi `notEmpty.signal()` hoặc `notEmpty.signalAll()`; thread đợi `notFull` được báo hiệu trên `notFull`.

Bài học tập trung vào Java core: `java.util.concurrent.locks.Lock`, `ReentrantLock`, `Condition`, cơ chế khóa, chờ/đánh thức và quản lý vòng đời.

## 1. Vì sao cần nhiều Condition?

Hãy xét một hàng đợi có dung lượng cố định:

- **Producer:** chỉ thêm khi `size < capacity`; nếu đầy, phải chờ.
- **Consumer:** chỉ lấy khi `size > 0`; nếu rỗng, phải chờ.
- **Đóng hàng đợi:** tất cả thread đang chờ phải thức dậy để kiểm tra `closed` và hoàn tất/thoát theo hợp đồng.

Nếu dùng một intrinsic monitor và `wait()`/`notify()`, các nhóm cùng nằm trong một wait set. Một lần `notify()` có thể đánh thức một producer khác khi hàng đợi vẫn đầy, trong khi consumer cần thức dậy để lấy dữ liệu. `notifyAll()` thường giải quyết nguy cơ chọn sai nhóm nhưng có thể khiến nhiều thread không đủ điều kiện cũng phải tranh khóa rồi đợi lại.

Với `Condition` ta biểu diễn rõ:

```java
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final Condition notFull = lock.newCondition();
```

Đây là đoạn khai báo trong class, không phải chương trình chạy độc lập. **Hai `Condition` dùng chung một lock** nhưng có **hai condition queues** khác nhau. Khi thêm phần tử: `notEmpty.signal()`; khi lấy phần tử: `notFull.signal()`. Khi đóng và mọi waiter cần tự kiểm tra lại: `signalAll()` trên **cả hai**.

> Quy tắc cốt lõi: *Một lock bảo vệ trạng thái; mỗi Condition đại diện cho một lý do chờ riêng.*

## 2. Phân biệt Lock, Condition và predicate

| Thành phần | Vai trò | Không phải là |
|---|---|---|
| `ReentrantLock lock` | Loại trừ truy cập đồng thời tới state và tạo quan hệ bộ nhớ đúng theo Java Memory Model. | Hàng đợi dữ liệu hoặc cờ điều kiện. |
| `Condition notEmpty` | Hàng chờ của thread cần đợi có dữ liệu. | Biến tự lưu số phần tử hoặc số lần signal. |
| `Condition notFull` | Hàng chờ của thread cần đợi có dung lượng. | Một khóa riêng bảo vệ `size`. |
| Predicate `!queue.isEmpty()` | Sự thật hiện tại quyết định consumer có được lấy phần tử không. | Tín hiệu `signal()`. |
| Predicate `queue.size() < capacity` | Sự thật hiện tại quyết định producer có được thêm không. | Một quyền tiếp tục được “đặt sẵn” bởi signal. |
| `closed` | Trạng thái vòng đời cho phép waiter quyết định thoát hoặc từ chối thao tác. | Tín hiệu hủy tự động tới mọi thread. |

**Predicate là nguồn sự thật; Condition chỉ hỗ trợ chờ để kiểm tra lại predicate.** Một lời `signal()` không gắn payload, không tích lũy permit và không tự đặt điều kiện thành `true`.

Các `Condition` khác nhau có thể chung một `ReentrantLock` vì state `queue/closed` là *một invariant chung*: không được vượt dung lượng, không lấy từ queue rỗng, không nhận thêm sau khi đóng.

## 3. await(): nhả khóa khi chờ và lấy lại khóa trước khi tiếp tục

Đối với `Condition` được tạo bởi `ReentrantLock.newCondition()`, luồng thường đi theo chu trình:

1. `lock.lock()` hoặc `lock.lockInterruptibly()` để sở hữu **associated lock**.
2. Kiểm tra predicate dưới khóa.
3. Nếu predicate sai, gọi `condition.await()`. `await()` nhả associated lock (kể cả hold count nếu đang tái nhập) và đưa thread vào condition queue.
4. Thread khác lấy được lock, sửa state và gọi `condition.signal()`/`signalAll()`.
5. Waiter được báo hiệu chuyển sang cạnh tranh lấy lock; nó **chưa chạy tiếp ngay**.
6. Sau khi lấy lại associated lock, `await()` mới có thể trở về (hoặc xử lý đường interrupt), và waiter **kiểm tra lại predicate trong `while`**.

```text
Producer                              Consumer
--------                              --------
lock.lock()
while (queueFull) {
    notFull.await()
       | nhả lock
       v                              lock.lock()
     WAITING                          remove item
       ^                              notFull.signal()
       |                              lock.unlock()
       +---- tranh lock --------------+
    lấy lại lock
    kiểm tra lại queueFull
}
add item
notEmpty.signal()
lock.unlock()
```

Điểm dễ nhầm là **`signal()` không trao ngay lock cho thread được đánh thức**. Thread phát tín hiệu còn giữ lock cho tới khi unlock; các thread khác cũng có thể tranh lấy lock trước waiter.

`await()` trên `Condition` của `ReentrantLock` hoặc `signal()`/`signalAll()` khi **chưa giữ associated lock** sẽ ném `IllegalMonitorStateException`. Phải dùng đúng lock đã tạo Condition, không chỉ cầm một lock bất kỳ.

## 4. Mẫu chuẩn: nhiều Condition với các vòng while riêng

Mã minh họa sau giả định toàn bộ biến thuộc cùng một class và mọi thao tác lên queue/closed đều dùng cùng lock:

```java
// Producer: đợi còn chỗ.
lock.lockInterruptibly();
try {
    while (queue.size() == capacity && !closed) {
        notFull.await();
    }
    if (closed) {
        throw new IllegalStateException("queue closed");
    }
    queue.addLast(item);
    notEmpty.signal();
} finally {
    lock.unlock();
}
```

```java
// Consumer: đợi có dữ liệu hoặc queue đóng.
lock.lockInterruptibly();
try {
    while (queue.isEmpty() && !closed) {
        notEmpty.await();
    }
    if (queue.isEmpty()) {
        return null; // Quy ước: đã đóng và không còn dữ liệu.
    }
    T item = queue.removeFirst();
    notFull.signal();
    return item;
} finally {
    lock.unlock();
}
```

Đây là các **trích đoạn**, không phải hai chương trình độc lập: cần định nghĩa `lock`, `notFull`, `notEmpty`, `queue`, `capacity`, `closed`, `item`, kiểu `T`, và khai báo `InterruptedException` ở phương thức tương ứng.

Đặc điểm chính:

- **Hai predicate, hai Condition**, nhưng **một khóa chung**.
- Thao tác **đọc predicate → await hoặc thực thi → sửa state → signal** đều được thực hiện dưới khóa.
- `while`, không phải `if`, vì thức dậy giả (*spurious wakeup*), tranh chấp giữa waiter và state thay đổi sau tín hiệu.
- `finally` luôn mở khóa sau khi thực thi thành công, `return` hoặc exception.
- Điều kiện `closed` phải được **xử lý riêng** để thread không mắc kẹt khi queue không còn nhận thêm dữ liệu.

## 5. Ví dụ 1: One-slot queue với notEmpty và notFull

Ví dụ hoàn chỉnh dùng một producer, một consumer và hộp thư chỉ có **một vị trí**. Code minh họa chính xác cách `Condition` chia waiter theo lý do chờ. Một bản queue production cần thêm chính sách timeout, capacity, xử lý lỗi và lifecycle; ở đây mục tiêu là hiểu monitor/condition.

Tạo file **`OneSlotConditions.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class OneSlotConditions {
    static final class Channel {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private Integer value;
        private boolean closed;

        void put(int item) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value != null && !closed) {
                    notFull.await();
                }
                if (closed) {
                    throw new IllegalStateException("closed");
                }
                value = item;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        Integer take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value == null && !closed) {
                    notEmpty.await();
                }
                if (value == null) {
                    return null;
                }
                int result = value;
                value = null;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }

        void close() {
            lock.lock();
            try {
                closed = true;
                notEmpty.signalAll();
                notFull.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Channel channel = new Channel();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 3; i++) {
                    channel.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                channel.close();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                Integer item;
                while ((item = channel.take()) != null) {
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

Lệnh chạy JDK 17+:

```bash
javac OneSlotConditions.java
java OneSlotConditions
```

Đầu ra khi không có interrupt bên ngoài:

```text
Received: 1
Received: 2
Received: 3
Finished
```

**Vì sao chương trình chạy đúng bất kể producer hay consumer được lên lịch trước?**

- Nếu producer chạy trước, nó có thể đặt một item; nếu muốn đặt item tiếp khi slot đầy, `notFull.await()` nhả lock để consumer lấy.
- Nếu consumer chạy trước, nó vào `notEmpty.await()` và nhả lock để producer đặt.
- Producer gọi `notEmpty.signal()` khi chuyển queue từ rỗng thành có item; consumer gọi `notFull.signal()` khi giải phóng slot.
- Producer kết thúc và gọi `close()` trong `finally`: mọi waiter trên hai condition queues đều được đánh thức để xem trạng thái `closed`.
- Consumer có thể lấy item cuối **sau khi** `closed = true`, vì `take()` ưu tiên trả phần tử còn tồn. Chỉ khi queue rỗng và đã đóng thì `null` báo kết thúc.
- Main `join()` đủ hai thread trước khi in `Finished`.

Đoạn này không dùng `volatile` cho `closed` hoặc `value`: mọi đường đọc/ghi hai trường đều dưới **cùng ReentrantLock**, cung cấp mutual exclusion và quan hệ bộ nhớ thích hợp.

## 6. Vì sao signal() đúng nhóm lại quan trọng?

Với một `Condition` duy nhất cho cả producer/consumer, một lời `signal()` không biết người được đánh thức đang chờ queue đầy hay rỗng. Một producer có thể đánh thức producer khác khi hàng đợi vẫn đầy, rồi người đó trở lại chờ, trong khi consumer vẫn ngủ: khả năng tiến triển có thể bị cản trở.

Hai `Condition` giúp:

- Khi producer **thêm** item, chỉ consumer cần xét lại `notEmpty`; đánh thức waiter trên `notEmpty`.
- Khi consumer **lấy** item, chỉ producer cần xét lại `notFull`; đánh thức waiter trên `notFull`.
- Khi **đóng**, cả hai nhóm đều cần kiểm tra trạng thái đóng, nên gọi `signalAll()` cho **cả hai** queues.

Đây là cách giảm những lần thức dậy không cần thiết mà vẫn giữ giao thức dễ chứng minh đúng. **Không phải cứ nhiều Condition là cần nhiều Lock**: tạo hai lock khác nhau để bảo vệ cùng `queue.size()` có thể phá invariant nếu các đường cập nhật thiếu phối hợp.

### signal() và signalAll() không có cùng mục đích

| Phương thức | Tác dụng | Dùng khi |
|---|---|---|
| `notEmpty.signal()` | Báo một waiter trong hàng chờ `notEmpty` nếu có. | Vừa thêm một item và chỉ cần một consumer thức dậy để thử lấy. |
| `notFull.signal()` | Báo một waiter trong hàng chờ `notFull` nếu có. | Vừa giải phóng một chỗ và chỉ cần một producer thử đặt. |
| `notEmpty.signalAll()` | Báo mọi waiter chờ `notEmpty`. | Đóng queue hoặc thay đổi trạng thái cho phép nhiều waiter tiến triển/thoát. |
| `notFull.signalAll()` | Báo mọi waiter chờ `notFull`. | Đóng queue hoặc thay đổi trạng thái cần mọi producer xét lại. |

`signal()` trên `notEmpty` **không tự đánh thức** các waiter trên `notFull`. Nó cũng không lưu tín hiệu cho những waiter đến sau. Nếu producer đặt item khi chưa có consumer đợi, consumer đến sau đọc **predicate queue không rỗng** và tiếp tục, không cần “nhận lại” tín hiệu cũ.

## 7. Vì sao luôn dùng while, kể cả khi signal đúng Condition?

Giả sử producer thêm một item và `notEmpty.signal()`. Consumer C1 được đánh thức, nhưng trước khi C1 lấy lại lock, một consumer C2 không đợi có thể lấy lock, lấy item và mở khóa. C1 sau đó tiếp tục mà queue đã **rỗng trở lại**.

Nếu C1 viết `if (queue.isEmpty()) notEmpty.await();`, nó có thể đi tiếp với giả định cũ và gọi `removeFirst()` trên queue rỗng. Với **`while (queue.isEmpty())`**, C1 kiểm tra lại và đợi tiếp. Ngoài ra `Condition.await()` được phép có *spurious wakeup*: thức dậy dù không nhận signal tương ứng với nghiệp vụ.

Mẫu cần nhớ:

```java
lock.lock();
try {
    while (!predicate()) {
        condition.await();
    }
    actUnderSameLock();
} finally {
    lock.unlock();
}
```

Đây là trích đoạn minh họa với `lock`, `condition`, `predicate()`, `actUnderSameLock()` đã khai báo; phương thức chứa nó phải khai báo/xử lý `InterruptedException`.

Không dùng `Thread.sleep()` trong khi giữ lock để “đợi condition”: `sleep()` **không nhả lock**, nên thread cần lock để cập nhật predicate có thể không vào được. `await()` có chức năng **nhả và lấy lại associated lock** phục vụ phối hợp điều kiện.

## 8. Ví dụ 2: hai nhóm chờ cho hai trạng thái khác nhau

Một ứng dụng không có queue cũng có thể cần nhiều Condition: nhóm A đợi hệ thống **ready**, nhóm B đợi hệ thống **stopped**. Đây là hai predicate độc lập nhưng cùng thuộc một đối tượng trạng thái, được bảo vệ bởi một lock.

Tạo file **`TwoConditionGate.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class TwoConditionGate {
    static final class Lifecycle {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition readyCondition = lock.newCondition();
        private final Condition stoppedCondition = lock.newCondition();
        private boolean ready;
        private boolean stopped;

        void awaitReady() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!ready) {
                    readyCondition.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void awaitStopped() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!stopped) {
                    stoppedCondition.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void setReady() {
            lock.lock();
            try {
                ready = true;
                readyCondition.signalAll();
            } finally {
                lock.unlock();
            }
        }

        void stop() {
            lock.lock();
            try {
                stopped = true;
                stoppedCondition.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Lifecycle lifecycle = new Lifecycle();
        AtomicInteger readyDone = new AtomicInteger();
        AtomicInteger stoppedDone = new AtomicInteger();

        Thread readyWaiter = new Thread(() -> {
            try {
                lifecycle.awaitReady();
                readyDone.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread stoppedWaiter = new Thread(() -> {
            try {
                lifecycle.awaitStopped();
                stoppedDone.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        readyWaiter.start();
        stoppedWaiter.start();

        lifecycle.setReady();
        lifecycle.stop();

        readyWaiter.join();
        stoppedWaiter.join();

        System.out.println("Ready waiters passed: " + readyDone.get());
        System.out.println("Stopped waiters passed: " + stoppedDone.get());
    }
}
```

```bash
javac TwoConditionGate.java
java TwoConditionGate
```

Kết quả khi không có interrupt bên ngoài:

```text
Ready waiters passed: 1
Stopped waiters passed: 1
```

Hai condition queues phục vụ hai sự kiện logic khác nhau; việc `setReady()` **không** signal `stoppedCondition`. Nếu main đặt state trước khi waiter kịp đợi, waiter sẽ quan sát predicate true trong `while` guard và đi tiếp, không phụ thuộc tín hiệu có người nhận hay không.

Đây là ví dụ tối giản của các cờ **một chiều** (false → true). Nếu lifecycle cho phép reset sang false, cần thiết kế lại giao thức để tránh waiter bỏ lỡ các thế hệ sự kiện (*generations*). Chẳng hạn có thể dùng biến `version`/state machine thay vì dựa vào một boolean.

## 9. Nhiều producer/consumer: tranh chấp và tính nhất quán

Một queue thật có thể có **nhiều** producer và consumer. `signal()` một consumer khi thêm một phần tử thường hợp lý vì chỉ một người lấy được phần tử đó. Khi consumer lấy một phần tử, `signal()` một producer nếu vừa có chỗ trống cũng hợp lý. Nhưng tính đúng đắn đòi hỏi:

1. Mọi method cập nhật `queue` và `closed` phải dùng cùng lock.
2. Mọi waiter dùng vòng `while` quanh predicate tương ứng.
3. Mỗi thao tác làm predicate của nhóm nào thay đổi thì báo cho **condition nhóm ấy**.
4. Khi đóng, **mọi waiter trên tất cả Condition liên quan** phải được đánh thức; một lần `signal()` không đủ.
5. Nếu hủy/interrupt xảy ra, tránh để queue rơi vào trạng thái cập nhật một nửa; xử lý ở ranh giới thao tác đúng hợp đồng.

### Ví dụ 3: Bounded queue với nhiều producer và consumer

Ví dụ này dùng dung lượng ba, ba producer mỗi producer phát 100 số và hai consumer cộng các số nhận được. Sau khi tất cả producer hoàn tất, main đóng queue để consumer còn đợi có thể thoát. Các thread nhận việc theo thứ tự không xác định, nhưng **tổng và số lượng** được kiểm tra được.

Tạo file **`MultiProducerConsumer.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class MultiProducerConsumer {
    static final class BoundedQueue {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private final Deque<Integer> queue = new ArrayDeque<>();
        private final int capacity;
        private boolean closed;

        BoundedQueue(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        void put(int value) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.size() == capacity && !closed) {
                    notFull.await();
                }
                if (closed) {
                    throw new IllegalStateException("closed");
                }
                queue.addLast(value);
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        Integer take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.isEmpty() && !closed) {
                    notEmpty.await();
                }
                if (queue.isEmpty()) {
                    return null;
                }
                Integer value = queue.removeFirst();
                notFull.signal();
                return value;
            } finally {
                lock.unlock();
            }
        }

        void close() {
            lock.lock();
            try {
                closed = true;
                notEmpty.signalAll();
                notFull.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BoundedQueue queue = new BoundedQueue(3);
        AtomicInteger count = new AtomicInteger();
        AtomicLong sum = new AtomicLong();

        Thread[] consumers = new Thread[2];
        for (int i = 0; i < consumers.length; i++) {
            consumers[i] = new Thread(() -> {
                try {
                    Integer value;
                    while ((value = queue.take()) != null) {
                        count.incrementAndGet();
                        sum.addAndGet(value);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "consumer-" + i);
            consumers[i].start();
        }

        Thread[] producers = new Thread[3];
        for (int i = 0; i < producers.length; i++) {
            final int base = i * 100;
            producers[i] = new Thread(() -> {
                try {
                    for (int value = base + 1; value <= base + 100; value++) {
                        queue.put(value);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "producer-" + i);
            producers[i].start();
        }

        for (Thread producer : producers) {
            producer.join();
        }
        queue.close();
        for (Thread consumer : consumers) {
            consumer.join();
        }

        System.out.println("Count: " + count.get());
        System.out.println("Sum: " + sum.get());
    }
}
```

```bash
javac MultiProducerConsumer.java
java MultiProducerConsumer
```

Kết quả trong lần chạy bình thường, không có interrupt ngoài:

```text
Count: 300
Sum: 45150
```

**Tại sao không bị mất item?** Mọi `put` và `take` bảo vệ cùng `Deque` bằng một lock. Nếu đầy, producer đợi `notFull`; nếu rỗng, consumer đợi `notEmpty`. Mỗi thread sau khi thức dậy kiểm tra lại predicate; do đó không thể lấy item từ queue rỗng hoặc thêm vượt capacity. Sau khi producer hoàn tất, main gọi `close()`, khiến tất cả consumer đang chờ (nếu có) được đánh thức và thoát khi không còn item. Tổng các số từ 1 đến 300 là `300 * 301 / 2 = 45150`, không phụ thuộc cách phân chia công việc giữa hai consumer.

**Giới hạn:** ví dụ không mô tả toàn bộ hành vi khi một producer bị lỗi, khi có request dừng giữa chừng hoặc khi cần rollback; những tình huống đó cần thêm chính sách lifecycle. Trong ứng dụng thông thường, `ArrayBlockingQueue` đã cung cấp một queue giới hạn dung lượng, được kiểm thử kỹ và thường thích hợp hơn việc tự viết.

## 10. Đóng và hủy: phải đánh thức mọi nhóm cần xem lại state

Một lỗi phổ biến là queue có hai Condition, nhưng khi `close()` chỉ gọi `notEmpty.signalAll()`. Các producer đang chờ `notFull` sẽ không nhận tín hiệu đóng, có thể đợi mãi dù không bao giờ được phép thêm item nữa.

Mẫu đóng đúng khi **cả hai nhóm** cần thoát:

```java
lock.lock();
try {
    closed = true;
    notEmpty.signalAll();
    notFull.signalAll();
} finally {
    lock.unlock();
}
```

Đây là trích đoạn trong class có `lock`, `closed`, `notEmpty`, `notFull`; không phải chương trình độc lập.

Các `while` trong `take()`/`put()` phải xét thêm `closed` để có đường thoát, ví dụ `while (empty && !closed)` hoặc `while (full && !closed)`. Nếu predicate chỉ là `while (empty)`, thread vừa được đánh thức bởi `close()` vẫn quay lại chờ vì queue rỗng. **Signal phải đi kèm thay đổi state cho phép waiter quyết định khác trước.**

Trong ứng dụng thực, hợp đồng đóng cần nói rõ: dữ liệu còn trong queue có được xử lý hết không, producer gặp `closed` ném exception hay trả trạng thái gì, các call đang chờ xử lý interrupt/timeout thế nào, và có cần báo lỗi tới caller hay không.

## 11. InterruptedException và lockInterruptibly()

`Condition.await()` là thao tác có thể bị interrupt. Khi bị interrupt trong lúc đợi, nó ném `InterruptedException` theo hợp đồng; trạng thái interrupt thường đã được xóa khi exception được ném. `Condition.await()` của `ReentrantLock` **lấy lại lock trước khi hoàn tất đường ném exception**, vì vậy `finally { lock.unlock(); }` vẫn đúng.

Hai cách phổ biến:

- **Ném tiếp** `InterruptedException` từ method để caller chịu trách nhiệm cancellation.
- Nếu method không ném tiếp, **khôi phục cờ interrupt** bằng `Thread.currentThread().interrupt()` rồi chấm dứt hoặc chuyển việc dọn dẹp theo hợp đồng.

`lock.lockInterruptibly()` có thể bị interrupt **khi đang đợi chiếm lock**, khác với `lock.lock()` vốn không ném `InterruptedException` do cố lấy lock. Khi `lockInterruptibly()` ném exception trước khi lấy lock thì chưa đi vào vùng try/finally chứa `unlock()`, nên mẫu mã đặt `lock.lockInterruptibly();` **trước** `try`.

Đừng nuốt interrupt rồi mặc nhiên coi predicate đã đúng. Một thread được đánh thức vì cancellation có thể không được phép tiếp tục lấy hoặc tạo dữ liệu.

## 12. Timed await: quản lý thời gian còn lại

Với `Condition`, `awaitNanos(long timeoutNanos)` cho phép chờ theo ngân sách thời gian và trả về phần thời gian còn lại (có thể bằng hoặc dưới 0 khi hết). Nó vẫn có thể thức dậy giả hoặc được signal khi predicate đã đổi, nên **vòng while vẫn bắt buộc**.

Mẫu phương thức chờ cổng với timeout, dạng trích đoạn:

```java
boolean awaitReady(long timeoutNanos) throws InterruptedException {
    long remaining = timeoutNanos;
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0L) {
                return false;
            }
            remaining = readyCondition.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}
```

Đoạn này giả định `ready`, `lock`, `readyCondition` thuộc cùng class. Trên mỗi vòng, dùng `remaining` **thay vì cấp lại nguyên timeout**, tránh kéo dài thời gian chờ do bị signal/spurious wakeup nhiều lần. Giá trị trả về **true** nghĩa là predicate `ready` đã đúng khi giữ lock; **false** nghĩa là ngân sách hết trước khi predicate đúng. Không đánh đồng kết quả trả về của một lần await với trạng thái nghiệp vụ.

Với timeout có giới hạn, cần xử lý các trường hợp số học tràn khi thời gian rất lớn hoặc cấu hình không hợp lệ; dùng `TimeUnit` và API chờ có deadline nếu phù hợp. Nếu không cần viết condition logic tùy biến, API `BlockingQueue.poll(timeout, unit)` đã giải quyết sẵn trường hợp đợi item có timeout.

## 13. Quan hệ bộ nhớ (Java Memory Model)

Quy tắc về Lock trong Java tạo quan hệ đồng bộ bộ nhớ tương đương với monitor: một lần **unlock** trên một lock có quan hệ *happens-before* với lần **lock tiếp theo** trên cùng lock theo contract. Vì mọi thread đều đọc/ghi `queue` và `closed` dưới một `ReentrantLock`, state đã được cập nhật trước unlock sẽ được nhìn thấy đúng khi waiter chiếm lock trở lại.

Với nhiều Condition trên cùng lock:

- Các `Condition` **không sở hữu những bản sao khác nhau của queue**: chúng chỉ phân nhóm waiter.
- Các thay đổi state được công bố nhờ giao thức lock/unlock; bản thân một lời `signal()` **không thay thế** việc bảo vệ predicate.
- Không cần thêm `volatile` cho mọi field đã được bảo vệ nhất quán bằng cùng lock.
- Nếu một getter đọc state **ngoài** giao thức lock, class có thể mất bảo đảm hiển thị và an toàn.
- `Thread.start()` và `Thread.join()` tạo thêm quan hệ ở biên vòng đời thread, nhưng không thay thế lock/condition khi cần phối hợp **trong lúc nhiều thread cùng đang hoạt động**.

`signal()`/ `signalAll()` chỉ quyết định thread nào có cơ hội tranh lấy lock; **thứ tự thực thi thực tế vẫn do lập lịch và tranh chấp lock quyết định**.

## 14. Fairness và việc đánh thức quá nhiều waiter

`new ReentrantLock(true)` có chính sách *fair* khi phân phối lock dưới tranh chấp theo contract, nhưng điều đó **không đảm bảo thứ tự nghiệp vụ FIFO hoàn toàn**, không loại bỏ spurious wakeup và không làm `signal()` trở thành một lần đặt chỗ cho item. Sau signal, waiter vẫn phải cạnh tranh theo quy tắc lock.

Nếu gọi `signalAll()` cho hàng trăm consumer chỉ vì thêm một item, tất cả có thể phải thức dậy và tranh lock, trong khi cuối cùng chỉ một consumer lấy được item — hiện tượng *thundering herd*. Phân chia waiter thành `notEmpty` và `notFull`, sau đó sử dụng `signal()` khi đủ, giúp giảm nhiều lần đánh thức không cần thiết.

Tuy nhiên, **signal ít hơn không đồng nghĩa tốt hơn trong mọi trường hợp**. Đối với sự kiện đóng, thay đổi phiên bản hoặc điều kiện mà nhiều waiter có thể cùng tiến triển, `signalAll()` là lựa chọn cần thiết. Ưu tiên **đúng về safety/liveness** trước rồi mới đo contention và tối ưu.

## 15. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Tạo `notEmpty` từ lock A, nhưng giữ lock B khi `await()` | Với `ReentrantLock.ConditionObject` sẽ ném `IllegalMonitorStateException`. | Condition phải được dùng cùng associated lock. |
| Dùng `if (empty) await()` | Có thể thức dậy giả hoặc item đã bị thread khác lấy. | Luôn `while (predicate false) await()`. |
| Đổi `queue` ngoài lock rồi signal trong lock | Dễ có race và phá invariant. | Tất cả đọc/ghi state liên quan và tín hiệu dùng cùng lock. |
| Tạo hai Condition nhưng dùng chung một predicate mơ hồ | Không tận dụng đúng việc phân nhóm waiter; dễ signal sai. | Định nghĩa rõ từng predicate và nhóm waiter. |
| Sau put lại signal `notFull` | Có thể đánh thức producer không đủ điều kiện; consumer còn ngủ. | Sau put signal `notEmpty`, sau take signal `notFull`. |
| Khi close chỉ signal một trong hai Condition | Nhóm waiter còn lại có thể đợi mãi. | SignalAll tất cả condition queues chịu ảnh hưởng bởi closed. |
| Nghĩ signal truyền ngay lock cho waiter | Waiter vẫn phải đợi notifier unlock và tranh lock. | Giữ critical section ngắn, luôn kiểm tra lại predicate. |
| Dùng `Thread.sleep()` trong khi giữ lock để chờ | Thread thay đổi predicate có thể không vào được. | Dùng await hoặc concurrent abstraction có sẵn. |
| Nuốt `InterruptedException` và tiếp tục thao tác | Mất yêu cầu hủy, có thể sai hợp đồng. | Ném tiếp hoặc khôi phục cờ interrupt, kết thúc theo policy. |
| Reset nguyên timeout sau mỗi wakeup | Có thể chờ lâu hơn thời hạn dự tính. | Dùng `awaitNanos(remaining)` hoặc deadline. |
| Tạo Condition cho từng field không liên quan đến lock chung | Thiết kế phức tạp và nguy cơ deadlock. | Phân tích invariant và ownership trước khi tạo queues. |
| Dùng lock/condition tự viết cho mọi queue | Tăng chi phí kiểm chứng/duy trì. | Ưu tiên `BlockingQueue` khi phù hợp. |

Một lỗi tinh tế: code vẫn có thể làm đúng dữ liệu nhưng **không tiến triển**. Ví dụ producer/consumer đều await theo predicate chính xác, nhưng không ai signal condition cần thiết. Vì vậy phải đánh giá **safety** (không vượt capacity, không lấy queue rỗng) và **liveness** (waiter thích hợp cuối cùng được đánh thức) riêng biệt.

## 16. So sánh với Object.wait/notify và API cấp cao

| Công cụ | Tình huống sử dụng | Đặc điểm |
|---|---|---|
| `Object.wait()/notify()/notifyAll()` | Phối hợp trên intrinsic monitor. | Mỗi object có một wait set; phải dùng `synchronized` và `while`. |
| `ReentrantLock` + nhiều `Condition` | Cấu trúc đồng thời có nhiều predicate trên một state chung. | Nhiều condition queues, `lockInterruptibly`, timed wait; phải dùng cùng lock và `while`. |
| `BlockingQueue` | Producer–consumer cần queue. | Cơ chế chờ/đánh thức và quản lý dung lượng đã được thư viện thiết kế. |
| `Semaphore` | Quản lý số permit, hạn chế số tác vụ đồng thời. | Permit được lưu; khác `signal()` không tích lũy. |
| `CountDownLatch` | Chờ điều kiện one-shot như “N tác vụ đã xong”. | Không reset được; không cần tự quản Condition cho tín hiệu một lần. |
| `CyclicBarrier`/`Phaser` | Phối hợp theo nhiều pha. | Có giao thức pha thay vì tự viết predicate phức tạp. |

Những Condition khác nhau **không phải các lock khác nhau**. Sức mạnh của mô hình là một lock bảo vệ invariant còn nhiều hàng chờ **phản ánh các lý do chờ**. Nếu chỉ cần truyền item giữa worker, nên dùng `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` thay vì tự viết để giảm rủi ro.

## 17. Checklist khi thiết kế nhiều Condition

1. Xác định **state/invariant chung**: ai sở hữu queue, capacity, closed?
2. Chọn **một lock** phù hợp cho tất cả đường truy cập state ấy.
3. Liệt kê các predicate độc lập: `notEmpty`, `notFull`, `closed`, `ready`, `finished`...
4. Chỉ tạo Condition khi thực sự cần hàng chờ riêng cho một nhóm waiter.
5. Trong mỗi method chờ: **lock → while(predicate sai) await → hành động → unlock trong finally**.
6. Trong method cập nhật: **lock → thay state → signal condition thích hợp → unlock**.
7. Nếu một sự kiện ảnh hưởng nhiều nhóm, đặc biệt close/cancel, báo trên **mọi Condition liên quan**; dùng `signalAll()` nếu mọi waiter cần xét lại.
8. Xem xét spurious wakeup, thread khác lấy mất tài nguyên, timeout và interruption.
9. Không giữ thêm những lock không liên quan khi await: await chỉ nhả associated lock, có thể gây deadlock nếu chờ thread cần lock khác.
10. Viết rõ hợp đồng khi đóng và dữ liệu còn trong queue; quyết định method ném exception, trả sentinel hay đợi.
11. Test nhiều producer và consumer, kiểm tra tổng/số item, không chỉ một lượt chạy.
12. Khi chỉ cần bài toán đã có abstraction chuẩn, ưu tiên API cấp cao.

## 18. Tự kiểm tra kiến thức

1. **Vì sao `notEmpty` và `notFull` cùng một lock?** Vì cả hai predicate phụ thuộc cùng state queue; phải bảo vệ invariant bằng một giao thức loại trừ nhất quán.
2. **Sau `put()`, vì sao báo `notEmpty`?** Vì queue mới có thêm item; consumer đang đợi item cần được thức dậy, không phải producer đang đợi chỗ trống.
3. **Sau `take()`, vì sao báo `notFull`?** Vì đã giải phóng capacity để producer có thể đặt tiếp.
4. **Khi close, gọi `notEmpty.signalAll()` đã đủ không?** Không nếu có producer đợi `notFull`; phải báo tất cả nhóm có liên quan.
5. **`signal()` có bảo đảm waiter chạy ngay không?** Không; waiter phải lấy lại lock trước khi `await()` trả về.
6. **Vì sao `while` bắt buộc dù đã dùng hai Condition?** Vì spurious wakeup và predicate có thể thay đổi trước khi waiter lấy lại lock.
7. **`signal()` có lưu permit cho thread đến sau không?** Không; state/predicate phải lưu sự thật, hoặc dùng `Semaphore` nếu cần permit.
8. **Dùng fair `ReentrantLock` có loại bỏ nhu cầu while không?** Không. Fairness không có nghĩa condition luôn đúng khi thức dậy.
9. **`await()` có nhả cả những lock khác thread đang giữ không?** Không; chỉ nhả associated lock của Condition theo contract.
10. **Khi nào nên thay tự viết Condition bằng `BlockingQueue`?** Khi mục tiêu là truyền dữ liệu producer–consumer thông thường và không cần một giao thức điều phối đặc biệt.

**Ghi nhớ:** một `ReentrantLock` bảo vệ **trạng thái chung**, nhiều `Condition` chia các **nhóm waiter theo predicate**, còn `while` bảo đảm mỗi lần thức dậy đều kiểm tra lại sự thật hiện tại. Đổi state và báo đúng condition dưới cùng lock, đồng thời đánh thức tất cả nhóm cần thoát khi đóng/hủy.
