# Spurious wakeup và kiểm tra lại invariant trong Java

## 1. Vấn đề: được đánh thức không có nghĩa điều kiện đã đúng

Khi phối hợp nhiều luồng, một thread thường phải chờ một **điều kiện nghiệp vụ**: hàng đợi có phần tử, buffer còn chỗ trống, tác vụ đã hoàn thành, hoặc một trạng thái đã chuyển sang `READY`. Java cung cấp `Object.wait()`/`notify()`/`notifyAll()` và `Condition.await()`/`signal()`/`signalAll()` để chờ và thông báo giữa các thread.

**Spurious wakeup** là trường hợp một lời gọi chờ có thể **trở về dù không có thông báo, interrupt hoặc timeout đủ để giải thích việc trở về**, như đặc tả Java cho phép. Chương trình đúng không được giả định mỗi lần `wait()` hoặc `await()` trở về đều có nghĩa điều kiện mong muốn đã thỏa.

Quan trọng hơn, **ngay cả khi không có spurious wakeup**, điều kiện vẫn có thể sai khi thread được đánh thức:

- Một thread khác gọi `notifyAll()`/`signalAll()`, nhưng chỉ một số waiter có thể tiêu thụ tài nguyên.
- Tín hiệu liên quan một loại thay đổi trạng thái khác, không phải điều kiện thread này đang chờ.
- Thread đã được signal nhưng phải **lấy lại khóa**; một thread khác có thể thay đổi trạng thái trước khi nó reacquire.
- Waiter được đánh thức sau một biến cố nhưng predicate bị thay đổi trở lại trước khi tiếp tục.
- Có timeout hoặc interrupt; mỗi lý do thức dậy phải được xử lý theo hợp đồng tương ứng.

**Quy tắc nền tảng: mọi lời chờ có điều kiện phải nằm trong vòng `while` kiểm tra lại predicate dưới cùng khóa bảo vệ trạng thái.**

~~~java
// Mẫu đúng, không phải chương trình độc lập.
// Thread phải đang giữ monitor của lock.
synchronized (lock) {
    while (!conditionSatisfied()) {
        lock.wait();
    }
    // Tại đây predicate đúng và ta vẫn giữ đúng monitor.
    consumeOrUpdateState();
}
~~~

Đối với `Condition`:

~~~java
// Mẫu đúng, không phải chương trình độc lập.
// state được bảo vệ bởi cùng ReentrantLock.
lock.lock();
try {
    while (!conditionSatisfied()) {
        condition.await();
    }
    consumeOrUpdateState();
} finally {
    lock.unlock();
}
~~~

Không tự thay `while` bằng `if` chỉ vì “đã chắc chắn bên phát tín hiệu gọi notify”. **Tín hiệu thông báo là gợi ý rằng có thể đã thay đổi trạng thái; predicate dưới lock mới là nguồn sự thật.**

Bài này thuộc phạm vi **phối hợp luồng Java nói chung**, sử dụng các API sẵn có trong JDK. Các cơ chế dành riêng cho framework không nằm trong phạm vi bài.

## 2. Invariant và condition predicate là gì?

### 2.1. Phân biệt invariant, predicate và signal

Một **invariant** là thuộc tính phải luôn đúng tại những thời điểm được bảo vệ bởi giao thức đồng bộ. Ví dụ buffer có `capacity` phần tử phải giữ:

~~~text
0 <= size <= capacity
~~~

Để chờ được đọc, consumer dùng **predicate** `!queue.isEmpty()`. Để chờ được ghi, producer dùng predicate `queue.size() < capacity`. Các predicate này được suy ra từ trạng thái mà khóa bảo vệ; không phải từ số lần `signal()` đã xảy ra.

Một **signal** chỉ cho phép một hoặc nhiều waiter được đánh thức để kiểm tra lại điều kiện. Nó không tự “cấp một phần tử”, không giữ chỗ trong queue và không cam kết predicate vẫn đúng khi waiter chạy.

| Khái niệm | Câu hỏi | Ví dụ buffer |
| --- | --- | --- |
| Invariant | Hệ thống luôn phải bảo toàn điều gì? | `0 <= size <= capacity` |
| Predicate | Waiter phải kiểm tra điều kiện cụ thể nào? | `size > 0` để take |
| State transition | Biến cố nào có thể khiến predicate đổi từ sai sang đúng? | Producer thêm phần tử |
| Signal | Ai cần được đánh thức để kiểm tra lại? | `notEmpty.signal()` |
| Lock | Ai bảo vệ quá trình kiểm tra và thay đổi state? | Một monitor/`ReentrantLock` chung |

Dùng **cùng một khóa** cho đọc predicate, thay đổi state và đi vào chờ ngăn tình huống kiểm tra trạng thái ở ngoài lock rồi bỏ lỡ thông báo trong lúc chuyển sang chờ.

### 2.2. Vì sao phải dùng while?

Giả sử hàng đợi ban đầu trống, hai consumer C1, C2 đều chờ. Producer thêm **một** phần tử rồi `signalAll()`:

~~~text
Ban đầu: queue = []
C1: await() vì queue trống
C2: await() vì queue trống

Producer: put(X), signalAll(), unlock()
C1: reacquire, thấy X, lấy X, unlock()
C2: reacquire, queue đã trống trở lại
~~~

C2 **đã được signal hợp lệ**, nhưng khi nó reacquire, predicate `!queue.isEmpty()` là **false**. Nếu chỉ dùng `if (empty) await()` rồi chạy tiếp `remove()`, C2 có thể đọc từ queue trống và lỗi. Với `while`, C2 quay lại chờ một phần tử khác.

Đây là ví dụ của **predicate không còn đúng sau tín hiệu**, không nhất thiết là spurious wakeup. Hai lý do khác nhau nhưng cùng dẫn đến yêu cầu dùng `while`.

## 3. Object.wait(): cơ chế và điều kiện sử dụng

### 3.1. wait thuộc object monitor

`Object.wait()`, `notify()` và `notifyAll()` hoạt động trên **monitor** của đúng object đó. Thread gọi phải đang giữ monitor tương ứng; cách rõ ràng nhất là dùng `synchronized(lock)`.

~~~java
// Mẫu dùng đúng monitor; không phải chương trình độc lập.
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

Khi gọi `lock.wait()` hợp lệ:

1. Thread **tạm nhả monitor của chính `lock`** và chuyển vào hàng chờ liên quan đến monitor đó.
2. Thread có thể được đánh thức do notify/notifyAll, interrupt, hoặc spurious wakeup; với biến thể có timeout, còn có timeout.
3. Trước khi `wait()` trở về bình thường hoặc ném `InterruptedException`, thread phải **lấy lại monitor của `lock`**.
4. Thread tiếp tục bên trong vùng `synchronized` và có thể kiểm tra predicate trong khi giữ monitor.

`wait()` không nhả **mọi khóa khác** mà thread đang sở hữu. Nếu một thread giữ thêm monitor B rồi gọi `lockA.wait()`, nó vẫn có thể giữ B trong lúc chờ, gây deadlock khi thread muốn thay đổi predicate cũng cần B.

Gọi `wait()` hoặc `notify()`/`notifyAll()` mà **không giữ monitor** của receiver sẽ ném `IllegalMonitorStateException`. Không dùng `Thread.sleep(...)` để thay thế `wait()`: sleep **không nhả khóa**, không đợi predicate và không tạo thông báo phối hợp.

### 3.2. notify, notifyAll và số lượng waiter

- `notify()` chọn **một** thread trong tập waiter trên monitor để đánh thức, nếu có. Không có bảo đảm bạn sẽ chọn đúng loại waiter của predicate hiện tại.
- `notifyAll()` đánh thức **tất cả** waiter trong tập tương ứng. Họ vẫn phải cạnh tranh lấy lại monitor và kiểm tra predicate.
- Chỉ gọi `notify`/`notifyAll` khi giữ monitor không có nghĩa waiter chạy ngay: thread đang giữ monitor còn phải nhả nó, và scheduler mới quyết định thời điểm waiter tiếp tục.
- Nếu **không có waiter**, notify không lưu “credit” chờ được nhận sau. Đây là lý do cần giữ trạng thái như `ready` hoặc `queue.size()` và luôn kiểm tra trước khi đi vào wait.

Trong ví dụ đơn giản, `notifyAll()` dễ tránh chọn sai loại waiter, nhưng đánh thức nhiều thread có thể gây **thundering herd** (nhiều waiter thức dậy chỉ để thấy predicate vẫn sai). Khi có nhiều loại predicate, `Condition` với các condition queue riêng đôi khi rõ ràng hơn.

### 3.3. Ví dụ 1 — Gate an toàn với while (Java 17+)

Tạo tệp `ObjectWaitGateDemo.java`:

~~~java
public class ObjectWaitGateDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen()
                throws InterruptedException {
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

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("worker passed");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "gate-waiter");

        worker.start();
        gate.open();
        worker.join();

        System.out.println("open = " + gate.isOpen());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ObjectWaitGateDemo.java
java ObjectWaitGateDemo
~~~

Stdout khi không có interrupt ngoài ý muốn:

~~~text
worker passed
open = true
~~~

Tình huống race quan trọng: nếu `gate.open()` xảy ra **trước** khi worker kịp vào `awaitOpen()`, worker thấy `open == true` ngay khi giữ monitor nên không cần wait. Nếu worker đi vào wait trước, `open()` đổi trạng thái và notifyAll dưới cùng monitor, nên worker sẽ kiểm tra lại và đi tiếp.

Với một spurious wakeup khi `open` còn false, `while` buộc worker quay lại `wait()`; không có dòng “worker passed” sai. Kết quả không phụ thuộc việc scheduler chạy worker trước hay thread main trước.

Đoạn này dùng `synchronized` ở tất cả đường đọc/ghi `open`, nên còn có bảo đảm visibility/happens-before qua monitor. `join()` giúp main chờ worker hoàn tất trước khi in dòng cuối.

## 4. Phân biệt spurious wakeup với thông báo không phù hợp

### 4.1. Spurious wakeup không phải “notify sai”

Một spurious wakeup là việc wait/await có thể trở về mà **không có nguyên nhân thông báo/timeout/interrupt cần thiết**. Nó được đặc tả cho phép. Không nên viết code hoặc test dựa vào kỳ vọng JVM **phải** tạo spurious wakeup trong một lần chạy.

Mặt khác, thread có thể được gọi `notifyAll()` một cách **hoàn toàn hợp lệ** nhưng predicate của nó vẫn sai. Trường hợp này có thể tái hiện có kiểm soát bằng Java để chứng minh `if` không đủ, mà **không phải giả vờ rằng đã tạo được spurious wakeup thực sự**.

### 4.2. Ví dụ 2 — lỗi if với thông báo không thay đổi predicate (Java 17+)

Ví dụ sau **cố ý sai**, dùng để hiểu vì sao phải sửa bằng `while`. Một thread được thông báo nhưng điều kiện `ready` vẫn false, nên nó không được tiếp tục công việc.

Tạo tệp `WrongIfWaitDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class WrongIfWaitDemo {
    static final class Gate {
        private boolean ready;
        private final CountDownLatch aboutToWait =
            new CountDownLatch(1);

        synchronized boolean awaitOnce()
                throws InterruptedException {
            if (!ready) { // SAI: phải là while (!ready).
                aboutToWait.countDown();
                wait();
            }
            return ready;
        }

        void waitUntilEntered() throws InterruptedException {
            aboutToWait.await();
        }

        synchronized void unrelatedNotify() {
            notifyAll(); // Không thay đổi ready.
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                boolean result = gate.awaitOnce();
                System.out.println("predicate = " + result);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "incorrect-waiter");

        worker.start();
        gate.waitUntilEntered();
        gate.unrelatedNotify();
        worker.join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac WrongIfWaitDemo.java
java WrongIfWaitDemo
~~~

Stdout khi worker không bị interrupt:

~~~text
predicate = false
~~~

Vì sao kết quả xác định được?

1. `aboutToWait.countDown()` xảy ra **bên trong monitor của Gate**, ngay trước `wait()`.
2. Thread main chỉ gọi `unrelatedNotify()` sau khi latch mở; `unrelatedNotify()` cũng phải lấy **monitor của Gate**.
3. Nếu worker vẫn chưa gọi `wait()`, main chưa thể lấy monitor để notify. Do đó khi main vào `unrelatedNotify()`, worker đã nhả monitor để chờ, hoặc đã tự thức dậy rồi đi tiếp.
4. `unrelatedNotify()` đánh thức waiter nếu nó còn đang chờ, nhưng **không đặt `ready = true`**.
5. Vì code dùng `if`, worker không kiểm tra lại predicate sau khi `wait()` trở về và in `false`.

Ví dụ này không phụ thuộc spurious wakeup: chính một thông báo có thật, nhưng không phù hợp, đã phơi bày lỗi. Nếu thay `if (!ready)` bằng `while (!ready)`, worker sẽ **tiếp tục chờ**, vì chưa có code nào đặt ready thành true. Khi sửa thành ứng dụng thực, phải bổ sung một lệnh chuyển trạng thái hợp lệ và notify để worker hoàn thành, không được chỉ đổi `if` rồi để test treo.

## 5. Condition.await(): cùng nguyên tắc, API linh hoạt hơn

`java.util.concurrent.locks.Condition` thường được tạo từ `ReentrantLock.newCondition()`. Một lock có thể tạo **nhiều condition queue**, ví dụ `notEmpty` và `notFull`, giúp tách loại waiter.

Khung đúng:

~~~java
// Mẫu Condition, không phải chương trình độc lập.
lock.lock();
try {
    while (!predicate()) {
        condition.await();
    }
    processSharedState();
} finally {
    lock.unlock();
}
~~~

Khi `await()` được gọi trong lúc thread giữ khóa phù hợp:

- Nó **nhả lock liên kết** với condition trong khi chờ; với `ReentrantLock`, trạng thái số lần giữ khóa được quản lý khi nhả và reacquire.
- Nó có thể trở về vì `signal()`/`signalAll()`, spurious wakeup, hoặc bị gián đoạn theo hợp đồng của overload.
- Trước khi trở về bình thường, waiter **lấy lại lock**, rồi tiếp tục trong cùng vùng bảo vệ trạng thái.
- `signal()` không chuyển ngay quyền sở hữu lock sang waiter; thread đang signal vẫn giữ lock đến khi unlock.
- Với `ConditionObject` do `ReentrantLock` tạo, gọi `await()` hoặc `signal()` khi không giữ lock phù hợp là sai; có thể ném `IllegalMonitorStateException`.

### 5.1. Điều kiện không phải một biến Boolean

Một `Condition` không tự lưu trữ predicate “ready”. Nó chứa cơ chế xếp hàng và đánh thức. State thực sự cần được giữ trong trường dữ liệu được lock bảo vệ: `count`, `queue`, `closed`, `ready`, v.v.

Sai khi suy luận: “Đã gọi `signal()`, vậy người chờ sau này sẽ nhận tín hiệu đó.” Signal không tích lũy credit cho waiter chưa bắt đầu chờ. Nếu cần lưu sự kiện hoặc permit, dùng trạng thái rõ ràng hay primitive có semantics tích lũy như `Semaphore`, `BlockingQueue`, khi phù hợp.

### 5.2. Condition có thể thức dậy giả

Theo API `Condition`, các triển khai cho phép spurious wakeup và lập trình viên **luôn phải giả định nó có thể xảy ra**. Một implementation cụ thể có thể ít hoặc không tạo wakeup giả trên đường thực tế; điều đó không đổi hợp đồng viết code.

Vòng `while` còn giúp xử lý việc một thread khác giành lại lock và thay đổi predicate trước waiter. Có hoặc không có spurious wakeup, điều kiện vẫn phải được kiểm tra **trong vùng khóa**.

## 6. Ví dụ 3 — bounded buffer với hai predicate (Java 17+)

Một buffer có dung lượng hữu hạn cần hai điều kiện:

- Consumer chờ `!queue.isEmpty()` trước khi lấy phần tử.
- Producer chờ `queue.size() < capacity` trước khi thêm phần tử.

Cả hai được bảo vệ bằng **một `ReentrantLock`**, nhưng có **hai Condition** tách biệt để báo đúng nhóm waiter.

Tạo tệp `BoundedBufferConditionDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class BoundedBufferConditionDemo {
    static final class Buffer {
        private final Deque<Integer> queue = new ArrayDeque<>();
        private final int capacity;
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();

        Buffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException(
                    "Capacity must be positive"
                );
            }
            this.capacity = capacity;
        }

        void put(int value) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.size() == capacity) {
                    notFull.await();
                }
                queue.addLast(value);
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        int take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (queue.isEmpty()) {
                    notEmpty.await();
                }
                int result = queue.removeFirst();
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }

        int size() {
            lock.lock();
            try {
                return queue.size();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Buffer buffer = new Buffer(1);

        Thread producer = new Thread(() -> {
            try {
                buffer.put(10);
                buffer.put(20);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();

        System.out.println("taken = " + buffer.take());
        System.out.println("taken = " + buffer.take());
        producer.join();
        System.out.println("remaining = " + buffer.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BoundedBufferConditionDemo.java
java BoundedBufferConditionDemo
~~~

Stdout khi không có interrupt ngoài dự kiến:

~~~text
taken = 10
taken = 20
remaining = 0
~~~

**Vì sao kết quả xác định?**

- Producer chỉ ghi các phần tử 10 rồi 20 theo thứ tự trong cùng một thread.
- Buffer dùng FIFO `ArrayDeque` nên consumer sẽ nhận 10 trước 20.
- Capacity bằng 1 nên khi producer muốn ghi 20 trong lúc vẫn có 10, nó đi vào `while (queue.size() == capacity)` để chờ.
- Consumer lấy 10 sẽ `notFull.signal()`; producer reacquire lock, kiểm tra lại còn chỗ trống và thêm 20. Consumer có thể phải chờ `notEmpty` trước đó hoặc sau đó, nhưng không ảnh hưởng thứ tự dữ liệu.
- `size()` và mọi đường đọc/ghi `queue` đều dùng cùng lock; `join()` khiến phép đọc cuối chạy sau khi producer hoàn tất.
- Không có dòng in trong producer, do đó thứ tự scheduler giữa các thread không làm thay đổi thứ tự stdout của main.

**Không có bảo đảm điều phối công bằng tuyệt đối:** `notEmpty.signal()` đánh thức một waiter, nhưng không cam kết waiter đó được CPU chạy ngay hoặc nhận phần tử trước mọi thread khác. Với nhiều producer/consumer, các `while` bảo vệ invariant khi nhiều thread tranh chấp.

### 6.1. Vì sao không dùng if trong buffer?

Nếu consumer chỉ kiểm tra `if (queue.isEmpty()) notEmpty.await();`, rồi không kiểm tra lại, nó có thể đi tới `removeFirst()` khi queue đã trống do waiter khác tiêu thụ. Với producer, `if (queue.size() == capacity) notFull.await()` có thể cho phép vượt capacity sau khi một producer khác thêm phần tử trước khi nó reacquire. Dùng `while` ở **cả hai đầu**.

### 6.2. Tránh signal quá sớm hoặc ngoài lock

Trạng thái cần được thay đổi trong khi giữ lock, rồi signal các waiter tương ứng trước khi release. Với `Condition` của `ReentrantLock`, việc gọi `signal()` ngoài lock không chỉ sai về mặt logic mà còn có thể ném `IllegalMonitorStateException`.

Cần chú ý một ứng dụng thực tế sẽ phải thiết kế thêm **đóng buffer**, xử lý producer/consumer bị hủy, khả năng shutdown và báo lỗi cho waiter đang chờ vô hạn. Nếu chỉ cần hàng đợi chuẩn, `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` có thể giảm code tự quản lý condition và lỗi phối hợp.

## 7. Timeout: thức dậy do hết hạn vẫn cần kiểm tra invariant

Một overload như `Condition.awaitNanos(long nanosTimeout)` trả về số nanosecond còn lại theo ước tính. Trong vòng lặp, phải **cập nhật ngân sách còn lại**, không chờ lại toàn bộ timeout ở mỗi lần thức dậy.

Mẫu đúng:

~~~java
// Mẫu Java, không phải chương trình độc lập.
long remaining = unit.toNanos(timeout);
lock.lockInterruptibly();
try {
    while (!ready) {
        if (remaining <= 0L) {
            return false;
        }
        remaining = readyChanged.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
~~~

Lý do:

1. Mỗi lần `awaitNanos` có thể trở về bởi signal/spurious wakeup, nhưng `ready` vẫn false.
2. Nếu lặp lại một timeout nguyên vẹn sau mỗi wakeup, tổng thời gian đợi có thể vượt nhiều lần ngân sách ban đầu.
3. Trả về `false` khi ngân sách đã hết **và predicate vẫn false**; nếu predicate đã true, trả `true` dù vừa trải qua một lần chờ dài.
4. Thời điểm lấy được lock cũng có thể tốn thời gian. Nếu yêu cầu deadline **tính từ khi bắt đầu gọi**, phải đưa cả thời gian lấy lock vào tính toán, chẳng hạn dùng `tryLock(timeout, unit)` và deadline thống nhất.
5. Timeout không tự thay đổi state nghiệp vụ hoặc hủy một producer đang hoạt động. Caller phải quyết định xử lý timeout rõ ràng.

### Ví dụ 4 — timeout và predicate đã đúng (Java 17+)

Tạo tệp `TimedConditionDemo.java`:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class TimedConditionDemo {
    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition changed = lock.newCondition();
        private boolean ready;

        boolean awaitReady(long timeout, TimeUnit unit)
                throws InterruptedException {
            long remaining = unit.toNanos(timeout);
            lock.lockInterruptibly();
            try {
                while (!ready) {
                    if (remaining <= 0L) {
                        return false;
                    }
                    remaining = changed.awaitNanos(remaining);
                }
                return true;
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                ready = true;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();

        System.out.println(
            "before = " + gate.awaitReady(0, TimeUnit.NANOSECONDS)
        );

        gate.open();

        System.out.println(
            "after = " + gate.awaitReady(0, TimeUnit.NANOSECONDS)
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TimedConditionDemo.java
java TimedConditionDemo
~~~

Stdout chính xác:

~~~text
before = false
after = true
~~~

Giới hạn 0 nanosecond làm lần chờ đầu trả `false` ngay vì predicate chưa đúng. Sau `open()`, predicate là true nên lần gọi thứ hai trả `true` ngay, **không cần chờ hoặc dựa vào một signal đã phát trong quá khứ**. Ví dụ minh họa đúng nghĩa kiểm tra trạng thái; nó không được dùng để ước tính thời gian chờ của các thread cạnh tranh.

## 8. Interrupt: không được gộp tất cả trường hợp thức dậy làm một

### 8.1. `InterruptedException` là kênh riêng

`Object.wait()` và `Condition.await()` thông thường có thể ném `InterruptedException` nếu thread bị interrupt. Đây **không phải** một lần trả về thành công từ `await`. Caller phải xử lý theo hợp đồng: truyền exception lên, hủy task hoặc trả trạng thái thất bại được thiết kế rõ ràng.

Khi thread bị interrupt trong lời chờ ném `InterruptedException`, cờ interrupt thường bị xóa trong quá trình ném. Nếu không thể truyền exception lên, một mẫu phổ biến là **khôi phục** cờ bằng `Thread.currentThread().interrupt()` trước khi kết thúc tác vụ.

~~~java
// Mẫu xử lý trong Runnable; không phải chương trình độc lập.
try {
    gate.awaitOpen();
    doUsefulWork();
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Không được bắt `InterruptedException` rồi tiếp tục làm như predicate đã đúng. Đồng thời, không mặc định việc interrupt một thread đang chờ sẽ làm mọi tài nguyên và side effect của nó tự động được hủy.

### 8.2. `awaitUninterruptibly` và vòng chờ

`Condition.awaitUninterruptibly()` đợi mà không ném `InterruptedException` theo cùng cách `await()`. Nhưng nó **vẫn cho phép spurious wakeup**, vì vậy cũng phải được đặt trong `while (!predicate)`. Nó không thích hợp nếu ứng dụng cần chấp hành cancellation/interrupt nhanh; thường ưu tiên `await()` và xử lý ngắt hợp lý.

### 8.3. Object.wait với timeout

`Object.wait(long timeoutMillis)` và `wait(long millis, int nanos)` cho phép chờ có thời hạn. Quy tắc `while` và tính lại deadline vẫn giữ nguyên. Cẩn thận ý nghĩa `wait(0)`: với overload `wait(long)`, số 0 nghĩa là **chờ vô thời hạn**, không phải trả về ngay. Điều đó khác với một số API timeout 0 như mẫu `awaitReady` ở trên.

## 9. Visibility và happens-before: vì sao khóa phải nhất quán?

Java Memory Model quy định việc **nhả monitor** của một object và **lấy monitor đó** sau này tạo quan hệ synchronizes-with/happens-before thích hợp. Tương tự, `Lock` và `Condition` theo hợp đồng của chúng cho phép các thao tác cập nhật state được công bố khi thread khác reacquire cùng lock.

Cơ chế đúng thường theo thứ tự:

~~~text
Producer:
  lock
  cập nhật state (predicate có thể chuyển false -> true)
  notify/signal đúng condition
  unlock

Consumer:
  lock
  while (!predicate) wait/await (tạm unlock)
  reacquire lock
  kiểm tra predicate lần nữa
  đọc/cập nhật state
  unlock
~~~

Tín hiệu không phải “phép thuật làm mọi biến nhìn thấy mới”. **Việc truy cập state dưới cùng khóa** mới cung cấp đồng bộ hóa cần thiết cho các đường đọc/ghi. Nếu producer thay đổi một biến thông thường **ngoài** giao thức khóa còn consumer đọc nó dưới khóa, bảo đảm có thể không đủ.

### 9.1. Tại sao check rồi wait ở ngoài lock là lỗi?

~~~java
// Sai nếu ready bị cập nhật ở thread khác và không có giao thức chung.
if (!ready) {
    synchronized (lock) {
        lock.wait();
    }
}
~~~

Có một khoảng trống giữa kiểm tra `ready` và việc wait thật sự. Thread khác có thể đặt `ready = true` và notify trong khoảng đó. Notification không được lưu cho tương lai, nên waiter có thể đi vào wait **sau khi tín hiệu đã mất**, rồi chờ vô hạn dù trạng thái sẵn sàng.

Cách đúng là **kiểm tra predicate và vào wait trong cùng critical section**. `wait()` nhả monitor nguyên tử theo cơ chế wait-set, cho phép thread thay đổi state lấy khóa và báo hiệu đúng trình tự.

### 9.2. Không dùng Thread.sleep để “đợi tín hiệu”

`Thread.sleep(...)` không tạm nhả monitor đang giữ, không tự tạo happens-before và không phản ứng với `notify`/`signal`. Nếu giữ lock rồi sleep để chờ thread khác làm cho predicate đúng, bạn có thể ngăn chính thread kia lấy khóa cần thiết để thay đổi trạng thái.

`Thread.yield()` và `Thread.onSpinWait()` cũng không thay thế được condition waiting hoặc giao thức đồng bộ; chúng chỉ ảnh hưởng gợi ý lập lịch/tối ưu.

## 10. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `if (!ready) wait()` | Thức dậy nhưng ready vẫn false; tiếp tục sai | `while (!ready) wait()` |
| `if (queue.isEmpty()) await()` | Nhiều consumer tranh chấp, một consumer có thể đọc queue rỗng | Kiểm tra `while` dưới lock |
| Gọi `notifyAll()` rồi giả định mỗi waiter có một item | Một tín hiệu không tương ứng số permit/item | Lưu state và kiểm tra lại predicate |
| Chỉ đọc `ready` ngoài `synchronized` | Data race, có thể bỏ lỡ notification | Cùng monitor cho check, wait và update |
| Gọi `wait()` ngoài monitor | `IllegalMonitorStateException` | Đồng bộ hóa trên đúng object receiver |
| Gọi `Condition.signal()` ngoài associated lock | Không đáp ứng hợp đồng, có thể lỗi runtime | Signal khi đang giữ lock tương ứng |
| Dùng `Thread.sleep` thay cho wait | Không nhả monitor hoặc chờ signal | Dùng monitor/Condition/queue |
| Không xử lý `InterruptedException` | Mất cancellation hoặc tiếp tục sai | Propagate hoặc restore flag và thoát |
| Chờ timeout lặp lại bằng toàn bộ thời lượng ban đầu | Tổng thời gian có thể vượt deadline | Tính lại ngân sách còn lại |
| Lặp `await()` nhưng predicate chỉ kiểm tra ở nơi khác | Không bảo đảm predicate đúng lúc tiếp tục | Kiểm tra ở chính vòng `while` cùng lock |
| Cố thử tạo spurious wakeup bằng cách gọi `notify` | Lẫn tín hiệu thật với wakeup giả | Dùng notification không phù hợp để demo `if` sai; hiểu hợp đồng wakeup giả riêng |
| Tin `signal()` trao ngay lock cho waiter | Dự đoán sai thứ tự | Waiter phải reacquire lock |
| Dùng `notify()` với nhiều kiểu predicate trên cùng wait-set | Có thể đánh thức waiter không phù hợp | `notifyAll` khi cần hoặc tách Condition |
| Giữ thêm lock B khi `lockA.wait()` | Vẫn giữ B, có thể gây vòng chờ | Tránh chờ khi giữ nhiều khóa, thiết kế lại thứ tự |
| Giữ lock khi gọi I/O hoặc callback không kiểm soát | Contention/deadlock/latency | Thu hẹp critical section |
| Dùng `awaitUninterruptibly` mà quên kiểm tra predicate | Spurious wakeup vẫn có thể xảy ra | Vẫn dùng `while` |

## 11. Từ wait/notify sang primitive cấp cao

Trong code ứng dụng, không phải bài toán nào cũng cần tự viết vòng `wait/notify`. Các primitive `java.util.concurrent` có thể mã hóa giao thức tương ứng rõ ràng hơn:

| Mục đích | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Chờ item từ producer | `BlockingQueue.take()` | Queue tự quản lý trạng thái rỗng/có phần tử |
| Hạn chế số task được vào tài nguyên | `Semaphore.acquire()` | Permit được lưu/cấp theo hợp đồng |
| Đợi một số tác vụ hoàn tất | `CountDownLatch.await()` | Count là trạng thái phối hợp rõ ràng |
| Các thread cùng đạt điểm đồng bộ lặp lại | `CyclicBarrier` hoặc `Phaser` | Giao thức pha thay vì tự tạo flags |
| Đợi kết quả task | `Future.get()` / `CompletableFuture` | Có cả kết quả/exception và hoàn tất |
| Chờ một predicate phức tạp trong object đồng bộ | `Condition.await()` | Vẫn phải dùng vòng predicate dưới lock |
| Bài tập cơ chế monitor cơ bản | `Object.wait/notifyAll` | Hiểu rõ nguyên tắc, nhưng nhiều chi tiết dễ sai |

Ngay cả khi dùng primitive cấp cao, vẫn cần hiểu cancellation, timeout, liveness và invariant. Ví dụ `BlockingQueue` giải quyết chờ phần tử, nhưng không tự định nghĩa quy tắc “producer đã đóng và sẽ không còn item nào nữa”; phần đóng/kết thúc vẫn cần giao thức riêng nếu ứng dụng yêu cầu.

## 12. Kiểm thử correctness mà không phụ thuộc wakeup giả ngẫu nhiên

Vì spurious wakeup có thể không xuất hiện trong một số JVM/lần chạy, một test chỉ lặp `wait()` nhiều lần rồi chờ wakeup giả không phải phép chứng minh đáng tin.

### 12.1. Các tình huống nên kiểm tra

1. **Tín hiệu đến trước waiter:** state đã đúng, waiter vào sau phải **không chờ**. Ví dụ Gate ở phần trên xử lý điều này.
2. **Tín hiệu không làm predicate đúng:** waiter phải **tiếp tục chờ**; ví dụ `WrongIfWaitDemo` cho thấy code dùng if sai bằng một notify có thật.
3. **Nhiều waiter, ít tài nguyên:** khi có một item và nhiều consumer được đánh thức, chỉ consumer lấy được item mới đi tiếp; những thread khác quay lại chờ.
4. **Predicate đổi lại trước reacquire:** signal xảy ra, một thread khác tiêu thụ tài nguyên trước waiter, và waiter phải kiểm tra lại.
5. **Interrupt khi đang chờ:** task truyền lỗi/ngắt đúng hợp đồng, không xử lý nghiệp vụ khi predicate false.
6. **Timeout:** task trả kết quả timeout đúng khi hết ngân sách, không làm kéo dài toàn bộ deadline vì nhiều wakeup.
7. **Shutdown/cancellation:** mọi waiter biết khi nào nên kết thúc thay vì chờ mãi trên predicate không thể thành true.
8. **Bất biến dữ liệu:** trong buffer, size luôn trong khoảng 0 đến capacity; không lấy phần tử khi queue rỗng hoặc thêm khi đầy.

### 12.2. Kỹ thuật kiểm thử

- Dùng `CountDownLatch` hoặc `CyclicBarrier` để sắp đặt các interleaving cần kiểm tra, thay vì `Thread.sleep(...)` như một cách phỏng đoán.
- Mọi test có khả năng block cần timeout và thu thập thread dump khi lỗi, tránh để test suite treo vô hạn.
- Dùng future/exception channel để không âm thầm bỏ qua lỗi của worker; `Thread.join()` chỉ cho biết thread đã kết thúc, không có nghĩa nghiệp vụ đã thành công.
- Chạy stress test với nhiều producer/consumer và so sánh số phần tử tạo–tiêu thụ; kết quả test thành công chỉ là bằng chứng hỗ trợ, không thay thế lập luận về giao thức.
- Khi debug thread đang `WAITING`, xem nó đang `Object.wait`, `Condition.await` hay một primitive khác; nhiều thread đang WAITING là bình thường nếu chúng thực sự chờ tài nguyên chưa sẵn sàng.

### 12.3. Không biến lỗi test thành kết luận sai về spurious wakeup

Nếu test minh họa `if` sai vì ta cố ý gọi `notifyAll` khi state vẫn false, hãy ghi rõ đây là **tín hiệu thật không phù hợp**. Nó chứng minh vòng `while` là cần thiết nhưng **không phải** bằng chứng rằng JVM đã tạo spurious wakeup.

Nếu test timeout đôi lúc thất bại vì máy quá tải, điều tra deadline, scheduling và điều kiện chờ; không tự động kết luận nguyên nhân là spurious wakeup.

## 13. Checklist review trước khi đưa vào sản phẩm

- Mọi waiter có một **predicate rõ ràng** gắn với trạng thái dùng chung chưa?
- Việc kiểm tra predicate và thực hiện `wait/await` có nằm trong **cùng lock/monitor** không?
- Mọi lời chờ predicate được đặt trong **`while (!predicate)`** chưa, kể cả khi chỉ có một waiter?
- Sau khi thức dậy, thread có reacquire lock và **kiểm tra lại invariant** trước khi sử dụng dữ liệu không?
- Writer có đổi state dưới lock rồi mới notify/signal phù hợp không?
- Có khả năng signal đến trước waiter? State có đủ để waiter đến sau không bỏ lỡ sự kiện không?
- Có nhiều waiter/các loại predicate khác nhau? `notify` hay `signal` đơn lẻ có nguy cơ chọn nhầm nhóm không?
- Có cơ chế timeout, interrupt, shutdown để tránh chờ vô hạn khi điều kiện không còn khả thi không?
- Có đường nào giữ nhiều lock rồi wait/await gây deadlock không?
- Có test cho thông báo không phù hợp, tranh chấp consumer, timeout và interrupt không?
- Nếu dùng `Condition`, code có release đúng lock trong `finally` và tránh làm I/O chặn dài trong critical section không?
- Có thể thay cơ chế tự viết bằng `BlockingQueue`, `Semaphore` hoặc `CountDownLatch` để đơn giản hóa không?

### Câu hỏi tự kiểm tra

**1.** Thread vừa trở về từ `Object.wait()` sau khi được gọi `notifyAll()`. Có được suy ra ngay `queue.isEmpty() == false` không?

Không. Một waiter khác có thể đã tiêu thụ item trước khi thread này reacquire monitor; cũng có thể notification không tương ứng với predicate đó. Phải kiểm tra lại dưới khóa.

**2.** Spurious wakeup có phải được tạo bởi lời gọi `notify()` “không đúng lúc” không?

Không. `notify()` là **tín hiệu thật**. Spurious wakeup là khả năng một wait/await trở về không có sự kiện thông báo/timeout/interrupt cần thiết. Cả hai đều cho thấy phải dùng `while`.

**3.** Nếu producer notify trước khi consumer gọi wait thì notification có được lưu lại không?

Không. Monitor notification không lưu permit cho waiter đến sau. Predicate phải được giữ trong state bảo vệ bởi cùng monitor; consumer kiểm tra state trước khi chờ.

**4.** Sau `condition.signal()`, waiter đã sở hữu `ReentrantLock` ngay chưa?

Chưa. Nó phải reacquire lock sau khi thread đang signal nhả lock; predicate có thể thay đổi trong khoảng thời gian đó.

**5.** Timeout của `awaitNanos` trở về nhưng predicate vẫn false. Có được thực hiện công việc như khi predicate đã true không?

Không. Phải kiểm tra predicate và ngân sách chờ; nếu hết thời gian mà điều kiện chưa đạt, trả kết quả timeout.

**6.** Gọi `Object.wait()` có nhả mọi lock mà thread đang giữ không?

Không. Nó nhả monitor của object receiver dùng để wait; các lock khác đang giữ không được tự động nhả.

**7.** Vì sao vòng `while` phải nằm **bên trong** khóa chứ không phải kiểm tra một lần ở ngoài rồi mới gọi wait?

Để việc kiểm tra predicate và chuyển vào wait được phối hợp nguyên tử với bên thay đổi state, tránh khoảng trống “check xong, notification xảy ra, rồi mới đi ngủ” gây lost notification.

**Ghi nhớ:** Thức dậy **không phải** là điều kiện đã đúng. Dù là spurious wakeup, signal không phù hợp, tranh chấp giữa nhiều waiter hay timeout, chương trình đúng phải **giữ và kiểm tra predicate cùng khóa**, lặp `while` khi chưa thỏa, và chỉ sử dụng trạng thái sau khi invariant được xác nhận.