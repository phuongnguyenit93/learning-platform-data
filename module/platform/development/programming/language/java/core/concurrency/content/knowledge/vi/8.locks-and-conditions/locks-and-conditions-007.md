# Vì sao await() luôn cần vòng lặp kiểm tra điều kiện?

Khi dùng **`ReentrantLock`** và **`Condition`** của `java.util.concurrent.locks`, một thread thường cần đợi một điều kiện nghiệp vụ: “hàng đợi có phần tử”, “đã mở cổng”, “còn dung lượng”, “đã có kết quả”, v.v. Phương thức **`Condition.await()`** giúp thread tạm nhả lock để thread khác có thể thay đổi trạng thái, sau đó được đánh thức và lấy lại lock để tiếp tục.

Nhưng **được đánh thức không đồng nghĩa điều kiện đang đợi chắc chắn đúng**. Vì vậy mẫu chuẩn là:

```java
lock.lock();
try {
    while (!conditionIsTrue()) {
        condition.await();
    }
    // Chỉ thực hiện khi predicate hiện tại đúng, dưới cùng lock.
} finally {
    lock.unlock();
}
```

Đây là trích đoạn minh họa, giả định `lock` là một `ReentrantLock`, `condition` là `Condition` được tạo bằng `lock.newCondition()`, còn `conditionIsTrue()` đọc trạng thái được bảo vệ bởi chính lock đó. Phương thức chứa đoạn mã phải khai báo hoặc xử lý `InterruptedException`.

**Vòng `while` không phải chi tiết trang trí.** Nó là một phần của giao thức đúng: kiểm tra điều kiện (*predicate*) → chờ khi chưa đúng → thức dậy → **kiểm tra lại** → chỉ hành động khi điều kiện đang đúng.

## 1. Condition.await() hoạt động thế nào?

`Condition` là cơ chế chờ theo điều kiện gắn với một `Lock`. Thông thường:

```java
ReentrantLock lock = new ReentrantLock();
Condition readyCondition = lock.newCondition();
```

`Condition.await()` vận hành theo logic:

1. Thread đang giữ **associated lock** khi gọi `await()`. Với `Condition` tạo từ `ReentrantLock`, gọi mà không giữ lock sẽ bị `IllegalMonitorStateException`.
2. `await()` **nhả lock** (bao gồm độ sâu giữ lock của ReentrantLock theo hợp đồng) và đưa thread vào hàng chờ điều kiện.
3. Thread khác lấy được lock, cập nhật trạng thái chung, rồi có thể gọi `signal()` hoặc `signalAll()`.
4. Waiter được phép thức dậy vì tín hiệu, interrupt hoặc *spurious wakeup*. Nó vẫn cần **lấy lại lock** trước khi `await()` trở về bình thường hoặc hoàn tất đường ném `InterruptedException`.
5. Sau khi có lock, waiter tiếp tục từ sau `await()`. Lúc này trạng thái chung có thể đã thay đổi thêm, nên nó phải kiểm tra lại predicate.

Sơ đồ:

```text
Thread consumer                       Thread producer
---------------                       ---------------
lock.lock()
while (queueEmpty) {
    notEmpty.await()
      | nhả lock
      v                                lock.lock()
   WAITING                             queue.add(item)
      ^                                notEmpty.signal()
      |                                lock.unlock()
      +---- thức dậy, tranh lock -----+
    lấy lại lock
    kiểm tra lại queueEmpty
}
remove item
lock.unlock()
```

**`signal()` không trao lock ngay lập tức.** Thread phát tín hiệu thường vẫn đang giữ lock đến khi `unlock()`. Waiter đã được đánh thức vẫn phải chờ đến lượt chiếm lock. Và `signal()` không tự biến điều kiện `queueEmpty == false` thành đúng: code thay đổi state mới có trách nhiệm đó.

## 2. Ba lý do phải dùng while thay vì if

### Lý do 1: Spurious wakeup — thức dậy không có tín hiệu mong đợi

Hợp đồng `Condition.await()` **cho phép thức dậy giả** (*spurious wakeup*). JVM/runtime có thể cho waiter trở về mà không có `signal()` trực tiếp từ thread khác như ứng dụng dự tính. Một phép đợi có timeout cũng có thể hết thời hạn trước khi predicate đúng.

Nếu viết:

```java
// KHÔNG an toàn với spurious wakeup.
if (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

thì waiter có thể thức dậy khi queue vẫn rỗng, và `remove()` ném exception hoặc phá giao thức. Chuyển thành:

```java
while (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

Hai trích đoạn giả định code đã giữ lock bảo vệ `queue` và condition `notEmpty`; chúng không phải chương trình độc lập. Mỗi lần thức dậy, `while` đọc **trạng thái hiện tại**, bất kể nguyên nhân thức dậy là gì.

### Lý do 2: Tín hiệu chỉ cho cơ hội kiểm tra, không dành sẵn tài nguyên

Giả sử hai consumer C1 và C2 đang đợi vì queue rỗng. Producer thêm **một** phần tử rồi gọi `signalAll()`.

- C1 và C2 đều được đánh thức và có thể tranh lock.
- C1 lấy lock trước, lấy phần tử cuối cùng, rồi mở khóa.
- C2 lấy lock sau. Queue **đã rỗng trở lại**.

Nếu C2 dùng `if`, nó đi thẳng qua câu lệnh sau `await()` mà **không kiểm tra lại** rồi cố lấy phần tử không tồn tại. Với `while`, C2 phát hiện queue rỗng và đợi lại.

Ngay cả với `signal()` (chỉ một waiter), một thread khác **không nằm trong hàng chờ** vẫn có thể lấy lock trước waiter được đánh thức và tiêu thụ tài nguyên. Vì vậy dùng `signal()` cũng **không cho phép bỏ `while`**.

### Lý do 3: Điều kiện có thể đổi trước khi waiter lấy lại lock

Producer có thể đặt `ready = true`, `signal()`, rồi có thread khác đặt `ready = false` **trước khi waiter lấy lại lock**. Tín hiệu chỉ phản ánh trạng thái tại một thời điểm cũ. Waiter phải quyết định từ **predicate đang có**, không dựa vào “mình vừa nhận signal”.

Quy tắc tổng quát: **notification = lời nhắc kiểm tra lại; predicate = nguồn sự thật**.

## 3. Tư duy đúng về predicate, lock và condition

| Thành phần | Trách nhiệm |
|---|---|
| **State/predicate** | Biểu thị điều kiện nghiệp vụ thật, ví dụ `!queue.isEmpty()`, `open`, `remaining > 0`. |
| **Lock** | Bảo vệ mọi đường đọc/ghi state liên quan và bảo đảm không bị chen giữa kiểm tra–đợi hoặc kiểm tra–thao tác. |
| **Condition** | Cung cấp chỗ chờ và tín hiệu cho những thread đang đợi predicate; nó **không lưu trữ sự thật nghiệp vụ**. |
| **await()** | Nhả associated lock, chờ, sau đó lấy lại lock trước khi trả về hoặc xử lý interrupt. |
| **signal()/signalAll()** | Cho waiter cơ hội được đánh thức; không bảo đảm predicate đúng hoặc waiter chạy ngay. |
| **while** | Kiểm tra lại invariant sau mọi đường thức dậy. |

Một giao thức cơ bản:

```java
// Bên chờ: dùng lock bảo vệ state.
lock.lock();
try {
    while (!ready) {
        readyCondition.await();
    }
    consumeReadyState();
} finally {
    lock.unlock();
}

// Bên phát tín hiệu: cùng lock và cùng state.
lock.lock();
try {
    ready = true;
    readyCondition.signalAll();
} finally {
    lock.unlock();
}
```

Đây là trích đoạn minh họa, cần các biến `lock`, `readyCondition`, `ready`, `consumeReadyState()` và xử lý `InterruptedException`. Nếu điều kiện là một sự kiện chỉ xảy ra một lần, predicate `ready` có thể giữ nguyên true. Nếu điều kiện liên quan tới một tài nguyên bị tiêu thụ, predicate phải được cập nhật sau mỗi lần lấy tài nguyên.

**Điểm chống lost signal:** kiểm tra điều kiện rồi gọi `await()` dưới **cùng lock**. Thread thay đổi điều kiện không thể chen vào khoảng giữa lúc waiter vừa kiểm tra false và lúc nó đã nhả lock để đợi. Nếu tín hiệu xảy ra trước khi waiter bắt đầu, waiter sẽ thấy predicate true khi nó có lock và **không đợi**. Không dùng `signal()` như một biến cờ tự động lưu tín hiệu.

## 4. Ví dụ 1: Condition Gate — tín hiệu trước hoặc sau waiter đều đúng

Tạo file **`ConditionGateDemo.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionGateDemo {
    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition opened = lock.newCondition();
        private boolean isOpen;

        void awaitOpen() throws InterruptedException {
            lock.lock();
            try {
                while (!isOpen) {
                    opened.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                isOpen = true;
                opened.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("Worker entered");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "gate-worker");

        worker.start();
        gate.open();
        worker.join();
        System.out.println("Main finished");
    }
}
```

```bash
javac ConditionGateDemo.java
java ConditionGateDemo
```

Kết quả khi không có interrupt từ bên ngoài:

```text
Worker entered
Main finished
```

Có thể `gate.open()` chạy **trước** khi worker vào `awaitOpen()`: khi lấy được lock, worker thấy `isOpen = true` và bỏ qua `await()`. Nếu worker đã chờ, `signalAll()` đánh thức nó để kiểm tra lại trạng thái sau khi lấy lock. **Hai lịch đều đúng** nhờ lưu predicate và dùng `while`.

Các trường `isOpen` không cần thêm `volatile` trong giao thức này: tất cả truy cập đều dùng cùng `ReentrantLock`, và unlock/lock thiết lập quan hệ *happens-before* phù hợp theo Java Memory Model. `join()` giúp dòng `Main finished` xuất hiện sau khi worker đã hoàn thành.

## 5. Ví dụ 2: if sai một cách tái hiện được — signalAll cho hai waiter, một permit

Ví dụ sau **cố tình viết sai** với `if` để minh họa tại sao một tín hiệu không dành riêng tài nguyên cho waiter. Hai worker cùng chờ một permit; sau khi cả hai đã vào đường chờ, main phát một permit và đánh thức tất cả. Sai lầm là hai waiter cùng tiếp tục qua `if` mà không kiểm tra lại permit.

Tạo file **`BrokenIfAwaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class BrokenIfAwaitDemo {
    static final class BrokenPermit {
        final ReentrantLock lock = new ReentrantLock();
        final Condition changed = lock.newCondition();
        final CountDownLatch bothArrived = new CountDownLatch(2);
        boolean available;

        void takeIncorrectly(AtomicInteger accepted)
                throws InterruptedException {
            lock.lock();
            try {
                if (!available) { // Sai: chỉ kiểm tra một lần.
                    bothArrived.countDown();
                    changed.await();
                }
                available = false;
                accepted.incrementAndGet();
            } finally {
                lock.unlock();
            }
        }

        void publishOnePermit() {
            lock.lock();
            try {
                available = true;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BrokenPermit permits = new BrokenPermit();
        AtomicInteger accepted = new AtomicInteger();

        Runnable task = () -> {
            try {
                permits.takeIncorrectly(accepted);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();

        permits.bothArrived.await();
        permits.publishOnePermit();
        a.join();
        b.join();

        System.out.println("Published permits: 1");
        System.out.println("Accepted requests: " + accepted.get());
    }
}
```

```bash
javac BrokenIfAwaitDemo.java
java BrokenIfAwaitDemo
```

Kết quả trong thực thi bình thường, không bị interrupt:

```text
Published permits: 1
Accepted requests: 2
```

`bothArrived` giảm đếm khi mỗi worker giữ lock và chuẩn bị chờ. Main chỉ phát permit sau khi cả hai đã đi tới điểm đó. Nếu worker thứ hai chưa nhả lock để `await()`, main vẫn phải chờ lấy lock trước khi `publishOnePermit()` có thể chạy; vậy khi main gọi `signalAll()`, hai worker đã ở đường đợi hoặc đã tự thức dậy theo quy tắc API. Với `if`, cả hai có thể đi qua câu lệnh sau await mà **không xác minh permit còn tồn tại**; kết quả hai yêu cầu được chấp nhận dù chỉ phát một permit.

**Cách sửa:** thay `if (!available)` bằng `while (!available)`, rồi đặt `available = false` dưới cùng lock. Khi đó chỉ một thread tiêu thụ permit; thread còn lại sẽ `await()` tiếp. Nhưng nếu trong ví dụ này chỉ có một permit **và không có lần phát/đóng tiếp theo**, thread còn lại sẽ đợi vô hạn và `join()` cũng không kết thúc. Muốn demo bản sửa đầy đủ, phải cung cấp thêm permit hoặc cơ chế đóng/hủy để đánh thức và cho waiter còn lại thoát. Ví dụ hàng đợi ở mục sau thể hiện giao thức đóng rõ ràng.

Ví dụ trên là **phản ví dụ cố ý không an toàn**, không được dùng như code sản xuất.

## 6. Ví dụ 3: một hàng đợi một slot dùng hai Condition

Trong producer–consumer, có hai predicate khác nhau:

- **`notEmpty`:** consumer được lấy khi slot có item, hoặc thoát nếu đã đóng.
- **`notFull`:** producer được đặt khi slot trống, hoặc dừng nếu đã đóng.

Dùng hai `Condition` gắn với **cùng một `ReentrantLock`** giúp phát tín hiệu đúng nhóm waiter và tránh đánh thức tất cả thread không liên quan. Mọi lần `await()` vẫn **cần vòng `while`**.

Tạo file **`OneSlotConditionQueue.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class OneSlotConditionQueue {
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
                    throw new IllegalStateException("channel closed");
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
                    return null; // Đã đóng và không còn item.
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
                for (int item = 1; item <= 3; item++) {
                    channel.put(item);
                }
                channel.close();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
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

```bash
javac OneSlotConditionQueue.java
java OneSlotConditionQueue
```

Kết quả trong lần chạy bình thường, không bị interrupt:

```text
Received: 1
Received: 2
Received: 3
Finished
```

**Vì sao đúng?**

1. `value` và `closed` là state private chỉ được đọc/ghi dưới cùng `lock`.
2. Producer kiểm tra `value != null && !closed` trong `while`; nếu slot đầy, `notFull.await()` nhả lock để consumer lấy item.
3. Consumer kiểm tra `value == null && !closed` trong `while`; nếu slot rỗng, `notEmpty.await()` nhả lock để producer đặt item.
4. Khi producer đặt xong, nó `notEmpty.signal()`; khi consumer lấy xong, nó `notFull.signal()`. Vì có một producer và một consumer, signal một waiter phù hợp với phạm vi ví dụ.
5. `close()` đặt `closed = true` rồi `signalAll()` **cả hai condition queues**, vì các waiter phải kiểm tra lại việc đóng. Consumer vẫn lấy item còn trong slot trước khi nhận `null` báo hoàn tất.
6. `join()` bảo đảm chương trình in `Finished` sau khi cả hai thread kết thúc.

Nếu mở rộng nhiều producer và consumer, cần xác định rõ tính chất đóng, thứ tự, fairness, interrupt và xử lý lỗi; `signal()` đúng hay không phụ thuộc protocol. Đây là implementation tối giản để học về condition, không thay thế queue thực tế nhiều tính năng. Với ứng dụng thường gặp, **`ArrayBlockingQueue`** hoặc `LinkedBlockingQueue` đã quản lý locking/await/signal và có API `put()`/`take()` rõ ràng.

## 7. signal(), signalAll() không thay thế kiểm tra predicate

`Condition.signal()` thông báo cho **một** waiter trên condition queue tương ứng; `signalAll()` chuyển **tất cả** waiter đang chờ trên condition đó sang trạng thái có thể cạnh tranh lấy lock. Với `ReentrantLock` và Condition từ `newCondition()`, phải sở hữu lock khi `signal()`/`signalAll()`.

Phân biệt với `Object.notify()`/`notifyAll()`:

| `Object.wait()` | `Condition.await()` |
|---|---|
| Gắn với intrinsic monitor của một đối tượng. | Gắn với một `Lock` và đối tượng `Condition` do lock tạo. |
| Chờ bằng `synchronized(lockObj)` rồi `lockObj.wait()`. | Chờ bằng `lock.lock()` rồi `condition.await()`. |
| Phát tín hiệu `notify()`/`notifyAll()` trên cùng đối tượng monitor. | Phát tín hiệu `signal()`/`signalAll()` trên đúng `Condition`. |
| Một object có một wait set nội tại. | Một `ReentrantLock` có thể có nhiều condition queues (`notEmpty`, `notFull`). |
| Phải đợi trong `while` kiểm tra predicate. | **Cũng phải đợi trong `while` kiểm tra predicate.** |

Hai nhóm API không hoán đổi trực tiếp: `condition.signal()` không đánh thức thread đang `object.wait()`; `object.notify()` không đánh thức thread đang `condition.await()` trên một condition khác.

`signal()` **không tích lũy permit**: tín hiệu gửi khi không có waiter trên condition queue đó không được tự lưu lại để đánh thức một thread đến sau. Nếu giao thức cần nhớ có “còn 3 quyền tiếp tục”, hãy lưu một **counter state** hoặc cân nhắc `Semaphore`, không giả định 3 lần `signal()` tương đương 3 permit.

## 8. Interrupt: vòng lặp vẫn phải tuân theo đường hủy

`await()` là thao tác chờ có thể bị interrupt. Khi thread bị interrupt trong lúc đợi, nó có thể ném `InterruptedException` theo hợp đồng; cờ interrupt được xóa khi exception được ném. Trước khi hoàn tất đường ném exception, `Condition.await()` của `ReentrantLock` **lấy lại lock**, nên `finally { lock.unlock(); }` vẫn đúng.

Cách xử lý:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    // Trạng thái ready thật sự đúng.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Kết thúc hợp tác hoặc chuyển trách nhiệm hủy.
} finally {
    lock.unlock();
}
```

Đây là trích đoạn minh họa, giả định các biến đã khai báo. Trong API cho phép ném `InterruptedException`, cách đơn giản hơn là **ném tiếp** để caller quyết định. Không nuốt exception rồi thực hiện hành động như thể điều kiện đã đúng.

Tạo tệp **`InterruptibleConditionDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleConditionDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        Condition changed = lock.newCondition();
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            lock.lock();
            try {
                entered.countDown();
                boolean ready = false;
                while (!ready) {
                    changed.await();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Waiting interrupted");
            } finally {
                lock.unlock();
            }
        }, "waiter");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("Worker finished");
    }
}
```

```bash
javac InterruptibleConditionDemo.java
java InterruptibleConditionDemo
```

Kết quả:

```text
Waiting interrupted
Worker finished
```

`entered.countDown()` báo main rằng worker đã vào vùng lock; main có thể interrupt trước hoặc sau lời gọi `changed.await()`. Trường hợp trước, await phát hiện cờ interrupt theo hợp đồng và ném; trường hợp sau, await bị ngắt trong lúc chờ. Cả hai đều chạy nhánh catch, phục hồi cờ, mở khóa và cho worker kết thúc. `join()` đợi worker trước khi in dòng cuối. Đây là một ví dụ về **cancellation hợp tác**, không phải dùng `interrupt()` để cưỡng bức thay đổi predicate.

## 9. awaitUninterruptibly() có bỏ nhu cầu while không?

**Không.** `awaitUninterruptibly()` không ném `InterruptedException` khi đang chờ, nhưng vẫn có thể thức dậy giả hoặc được signal khi predicate chưa đúng. Nó vẫn phải nằm trong vòng `while`:

```java
lock.lock();
try {
    while (!ready) {
        condition.awaitUninterruptibly();
    }
} finally {
    lock.unlock();
}
```

Trích đoạn minh họa; `condition`, `lock`, `ready` đã được giả định khai báo. Khi được interrupt trong lúc đợi, `awaitUninterruptibly()` tiếp tục đợi thay vì trả về vì interrupt; trạng thái interrupt được bảo toàn theo hợp đồng. Hãy chọn API này **chỉ khi giao thức thực sự cần bỏ qua yêu cầu ngắt trong thời gian chờ**. Ứng dụng cần shutdown/cancel thường phù hợp hơn với `await()` có thể interrupt.

## 10. Timed await(): hết thời gian cũng không chứng minh điều kiện đúng

Các biến thể `Condition.awaitNanos(long nanosTimeout)`, `await(long time, TimeUnit unit)` và `awaitUntil(Date deadline)` cho phép chờ có thời hạn. Sau khi chúng trở về, chương trình vẫn phải **kiểm tra lại predicate**. Một lần timeout không có nghĩa điều kiện đã đúng; một lần được signal cũng không nghĩa điều kiện vẫn đúng.

Mẫu dùng `awaitNanos`:

```java
long remaining = timeoutNanos;
lock.lock();
try {
    while (!ready) {
        if (remaining <= 0L) {
            return false; // Hết thời hạn mà điều kiện chưa đúng.
        }
        remaining = condition.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
```

Đây là đoạn code **bên trong một method trả `boolean`** có thể ném `InterruptedException`, không phải chương trình Java độc lập. Các biến `lock`, `condition`, `ready`, `timeoutNanos` được giả định đã khai báo. `awaitNanos()` trả về thời lượng còn lại ước tính theo hợp đồng, có thể không dương nếu timeout. Việc đưa `remaining` trở lại vòng lặp bảo đảm tổng ngân sách chờ được quản lý thay vì đặt lại toàn bộ timeout sau mỗi lần thức dậy.

Đối với `await(time, unit)`, kết quả boolean **chỉ cho biết tình trạng chờ tín hiệu so với timeout**, không thay thế predicate. Nếu cần xử lý điều kiện trước/sau timeout một cách chính xác, thiết kế API nên ghi rõ “thành công khi predicate đúng” và kiểm tra dưới lock. Nếu cần timeout theo thời gian hệ thống, hãy chú ý clock changes; với đo khoảng, `System.nanoTime()` thường phù hợp hơn `currentTimeMillis()`.

## 11. Fair lock, signal order và starvation

`new ReentrantLock(true)` tạo fair lock theo chính sách của `ReentrantLock` cho việc cấp khóa, nhưng **không loại bỏ nhu cầu while**. Fairness không biến signal thành đặt chỗ cho tài nguyên, và không ngăn predicate đổi giữa lúc signal và lúc waiter có lock.

`signal()` có thể có quy tắc chọn waiter theo thứ tự trong implementation `ReentrantLock.ConditionObject`, nhưng thứ tự cuối cùng các thread **nhận được lock và thực hiện hành động** còn phụ thuộc tranh chấp và chính sách khóa. Không xây dựng correctness từ một giả định “waiter được signal đầu tiên sẽ là người xử lý dữ liệu đầu tiên” trừ khi contract API thực sự bảo đảm toàn bộ điều đó.

Nhiều waiter thức dậy rồi lại chờ có thể làm tăng contention hoặc *thundering herd*, nhất là khi dùng `signalAll()`. Cách tối ưu thường là sử dụng nhiều condition queues cho các predicate khác nhau, chọn `signal()` khi chứng minh được đủ và giữ vùng lock ngắn. Nhưng **tối ưu hiệu năng phải đến sau tính đúng đắn của predicate + while**.

## 12. Các lỗi hay gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `if (!ready) await()` | Spurious wakeup hoặc thread khác lấy mất tài nguyên khiến hành động sai. | Dùng `while (!ready) await()`. |
| Gọi `await()` không sở hữu associated lock | `IllegalMonitorStateException` với Condition của ReentrantLock. | Giữ lock bằng `lock()`/`lockInterruptibly()`, mở trong `finally`. |
| Gọi `signal()` ngoài lock | `IllegalMonitorStateException` với Condition của ReentrantLock. | Cập nhật state và signal dưới cùng lock. |
| Cho rằng `signal()` đảm bảo predicate đúng | Predicate có thể đổi trước khi waiter lấy lại lock. | Kiểm tra lại trong while. |
| Dựa vào signal như trạng thái lưu trữ | Signal khi không có waiter bị bỏ qua. | Lưu boolean/counter/queue state; signal chỉ hỗ trợ thông báo. |
| Dùng `Thread.sleep()` trong khi giữ lock để chờ | Thread cần lock để thay đổi điều kiện không thể vào, gây nghẽn. | Dùng `await()` nhả lock theo hợp đồng. |
| Kiểm tra predicate ngoài lock rồi mới await trong lock | Race giữa kiểm tra và đợi, có thể lost signal. | Guard predicate và await trong cùng vùng lock. |
| Dùng `signalAll()` rồi `if` | Nhiều waiter vượt qua guard cũ và cùng tiêu thụ một tài nguyên. | Mỗi waiter phải while; cập nhật predicate sau tiêu thụ. |
| Nuốt `InterruptedException` | Mất tín hiệu hủy và có thể tiếp tục trái nghiệp vụ. | Ném tiếp hoặc khôi phục cờ và kết thúc hợp tác. |
| Reset timeout đầy đủ sau mỗi thức dậy | Có thể chờ lâu hơn ngân sách dự định. | Tính thời gian còn lại bằng `awaitNanos()`/deadline. |
| Gọi `signal()` rồi chờ waiter chạy trước khi unlock | Waiter không thể hoàn tất await trước khi chiếm lại lock. | Thoát vùng lock ngay sau khi cập nhật/tín hiệu khi hợp lý. |
| Chỉ đợi một predicate mà không có đường đóng/hủy | Thread có thể treo mãi nếu điều kiện không bao giờ đúng. | Thiết kế trạng thái `closed`, `signalAll()` và xử lý interrupt. |

## 13. Cách chứng minh một await-loop đúng

Khi review một class tự dùng `Condition`, hãy đặt các câu hỏi sau:

1. **Predicate là gì?** Ví dụ `!queue.isEmpty()`, `capacityAvailable`, `closed || ready`. Nó có phản ánh chính xác điều kiện để thực hiện hành động không?
2. **Ai có thể sửa predicate?** Tất cả đường truy cập liên quan có dùng cùng `ReentrantLock` không?
3. **Đã dùng `while` thay `if` chưa?** Có kiểm tra lại sau mọi wakeup không?
4. **Việc kiểm tra và await có chung lock không?** Nếu không, có khe lost-signal giữa check và wait.
5. **Hành động sau loop có làm predicate đổi không?** Nếu có, nó cũng phải nằm dưới lock và có tín hiệu tới waiter phù hợp.
6. **Trường hợp close/interrupt/timeout thì sao?** Loop có thể kết thúc hoặc hủy một cách có kiểm soát, không chờ vô hạn ngoài ý muốn.
7. **Signal chọn đúng condition queue chưa?** Với nhiều predicate, `notEmpty` và `notFull` cần được phân biệt để tránh đánh thức sai nhóm.
8. **Có nguy cơ deadlock không?** `await()` nhả associated lock nhưng không nhả những khóa khác thread đang giữ. Tránh giữ nhiều lock lồng nhau thiếu thứ tự.
9. **Có thể đơn giản hóa không?** Nếu chỉ cần queue, `BlockingQueue` thường dễ dùng đúng hơn; nếu chỉ cần tín hiệu one-shot, `CountDownLatch` có thể phù hợp; nếu cần permit, cân nhắc `Semaphore`.

## 14. Khi nào không cần tự viết await-loop?

`Condition` là công cụ thấp cấp cần thiết để thiết kế các cấu trúc đồng bộ hóa tùy biến, nhưng nhiều bài toán đã có abstraction cao hơn:

| Bài toán | Công cụ Java thường phù hợp |
|---|---|
| Producer–consumer có queue | `ArrayBlockingQueue`, `LinkedBlockingQueue`. |
| Một cổng mở một lần | `CountDownLatch`. |
| Chờ kết quả tác vụ | `Future.get()`, `CompletableFuture`. |
| Đếm tài nguyên có permit | `Semaphore`. |
| Nhiều pha cùng rendezvous | `CyclicBarrier`, `Phaser`. |
| Điều phối tùy biến với nhiều predicate | `ReentrantLock` + nhiều `Condition`; dùng `while` trong mọi waiter. |

Không nên tự viết queue nhiều thread nếu không cần: bên cạnh await-loop còn phải xử lý fairness, capacity, cancellation, shutdown, deadlock, thời hạn chờ và performance. Nhưng việc hiểu **vì sao while bắt buộc** giúp đọc, debug và sử dụng các concurrent abstractions đúng cách.

## 15. Câu hỏi tự kiểm tra

1. **`await()` được signal thì predicate có chắc đúng không?** Không. Thread khác có thể lấy tài nguyên trước hoặc predicate bị đổi; waiter phải kiểm tra lại.
2. **Spurious wakeup là gì?** Waiter có thể thức dậy dù không có tín hiệu tương ứng với điều kiện nghiệp vụ; được hợp đồng API cho phép.
3. **Tại sao không thể thay while bằng if nếu chỉ có một waiter?** Spurious wakeup và thay đổi predicate vẫn có thể xảy ra; không có bảo đảm tổng quát cho if.
4. **Tại sao check predicate phải cùng lock với await?** Để tránh thread khác thay đổi điều kiện và phát signal ở khe giữa check và wait.
5. **`signalAll()` có làm mọi waiter đủ điều kiện hành động không?** Không. Tất cả phải tranh lock và tự kiểm tra predicate; có thể chỉ một người được tiến triển.
6. **`signal()` có lưu một permit để thread tương lai sử dụng không?** Không; muốn lưu khả năng tiếp tục phải có state/counter, hoặc dùng `Semaphore`.
7. **`await()` có nhả lock liên quan không?** Có, theo hợp đồng của Condition/ReentrantLock, và phải lấy lại lock trước khi trở về. Nó không tự nhả các lock khác.
8. **Khi await bị interrupt và ném exception, có nên tiếp tục như điều kiện đúng không?** Không. Nên chuyển yêu cầu hủy cho caller hoặc khôi phục cờ và kết thúc theo protocol.
9. **Timed await kết thúc có đồng nghĩa predicate đúng không?** Không; phải kiểm tra lại predicate và ngân sách timeout.
10. **Đã dùng fair lock có cần while không?** Vẫn cần. Fairness không loại bỏ spurious wakeup và không đặt trước trạng thái tài nguyên cho waiter.

**Ghi nhớ:** `Condition.await()` chỉ nói *“hãy nhả lock và đợi cơ hội kiểm tra lại”*; không nói *“điều kiện giờ chắc chắn đúng”*. Vì thế mẫu đáng tin cậy luôn là **giữ đúng lock → `while (!predicate) await()` → thực hiện hành động dưới lock**, với xử lý timeout, interruption và tín hiệu phù hợp.
