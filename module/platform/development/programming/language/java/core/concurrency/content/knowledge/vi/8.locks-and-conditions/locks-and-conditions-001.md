# Lock interface so với intrinsic monitor trong Java

Java có hai cách phổ biến để bảo vệ dữ liệu chia sẻ bằng **loại trừ tương hỗ**: từ khóa `synchronized` sử dụng **intrinsic monitor** của một object, và các đối tượng triển khai `java.util.concurrent.locks.Lock`, thường gặp nhất là `ReentrantLock`. Cả hai đều có thể bảo vệ cùng một invariant và tạo quan hệ bộ nhớ cần thiết giữa các thread, nhưng khác nhau về **cách lấy/nhả khóa, khả năng hủy khi chờ, timeout, điều kiện chờ và quản lý vòng đời khóa**.

Nắm khác biệt này giúp trả lời một câu hỏi thiết kế cụ thể: **critical section của mình chỉ cần độc quyền đơn giản hay còn cần thử lấy khóa, deadline, khả năng interrupt hoặc nhiều nhóm điều kiện chờ?** Bài này áp dụng cho Java concurrency nói chung, không bàn các framework tích hợp.

## 1. Từ “lock” và “monitor” chính xác là gì?

**Intrinsic monitor** (còn gọi là *intrinsic lock* hoặc *object monitor*) gắn với mỗi object Java và được sử dụng khi đi vào `synchronized`. Một thread muốn vào khối đồng bộ phải sở hữu monitor tương ứng. Các thread khác cố lấy monitor ấy phải chờ cho đến khi chủ sở hữu nhả. Một monitor chỉ cho một thread sở hữu tại một thời điểm và có tính **reentrant**: chính thread đang giữ khóa có thể lấy lại nó nhiều lần.

**`Lock` interface** là hợp đồng cấp thư viện trong `java.util.concurrent.locks`, cung cấp các method như `lock()`, `unlock()`, `tryLock()`, `lockInterruptibly()` và `newCondition()`. `ReentrantLock` là triển khai mutual exclusion có tính reentrant với các tính năng bổ sung. Một object `ReentrantLock` vẫn là một Java object có intrinsic monitor riêng, nhưng **hai cơ chế khóa này là độc lập**.

Cả hai bảo vệ được trạng thái chia sẻ khi **mọi đường truy cập liên quan tuân thủ cùng khóa hoặc giao thức đồng bộ**. Chỉ khóa writer trong khi reader đọc trực tiếp field thường, hoặc khóa hai object khác nhau, chưa đủ bảo vệ invariant/visibility.

### Ví dụ rất ngắn

Intrinsic monitor:

```java
private final Object monitor = new Object();
private int count;

void increment() {
    synchronized (monitor) {
        count++;
    }
}
```

Explicit lock:

```java
private final Lock lock = new ReentrantLock();
private int count;

void increment() {
    lock.lock();
    try {
        count++;
    } finally {
        lock.unlock();
    }
}
```

Hai mảnh code là **snippet đặt bên trong class**, không phải chương trình độc lập. Ví dụ thứ hai cần import `java.util.concurrent.locks.Lock` và `ReentrantLock`. Cả hai đều bảo vệ read–modify–write `count++` nếu **mọi** thao tác đọc/ghi cần nhất quán đều sử dụng đúng khóa ấy. Khác biệt dễ thấy: `synchronized` tự nhả monitor khi thoát scope, còn `Lock` bắt buộc lập trình viên gọi `unlock()` sau khi đã lấy được khóa.

## 2. Bảng so sánh tổng quan

| Tiêu chí | `synchronized` / intrinsic monitor | `Lock` / `ReentrantLock` |
| --- | --- | --- |
| Cơ chế | Từ khóa ngôn ngữ và monitor của một Java object | API cấp thư viện, một object triển khai `Lock` |
| Lấy khóa | Vào block/method `synchronized` | `lock()`, `lockInterruptibly()` hoặc `tryLock(...)` |
| Nhả khóa | Tự động khi thoát block/method, kể cả exception | Gọi `unlock()`, thường trong `finally` |
| Thử lấy khóa không chờ | Không có cú pháp chuẩn `synchronized.tryLock()` | `tryLock()` trả `boolean` ngay |
| Giới hạn thời gian chờ lấy khóa | Không có phiên bản timed acquire của `synchronized` | `tryLock(timeout, unit)` |
| Interrupt khi đang chờ **lấy khóa** | Không hủy được việc đợi vào monitor chỉ bằng interrupt | `lockInterruptibly()`, timed `tryLock` hỗ trợ interrupt |
| Cơ chế đợi điều kiện | `Object.wait/notify/notifyAll` trên **monitor đó** | `Condition.await/signal/signalAll` từ `newCondition()` |
| Số nhóm điều kiện | Một wait set gắn với mỗi object monitor | Có thể tạo nhiều `Condition` trên cùng `ReentrantLock` |
| Reentrancy | Có | `ReentrantLock` có; **không phải mọi triển khai `Lock` đều giống vậy** |
| Fairness option | Không có tùy chọn công bằng qua `synchronized` | `ReentrantLock(true)` có chính sách fairness theo hợp đồng, có giới hạn |
| Thread state khi tranh khóa | Thường `BLOCKED` khi chờ lấy monitor | Thường park, thấy `WAITING`/`TIMED_WAITING` tùy API/triển khai |
| Bảo đảm memory ordering | Unlock monitor happens-before lần lock kế tiếp trên cùng monitor | Lock/unlock của `Lock` có memory synchronization tương đương theo hợp đồng |
| Ưu tiên đơn giản, ít cấu hình | Rất phù hợp | Dài hơn, phải quản lý ownership/lifecycle rõ |
| Khóa qua nhiều method/scope | Cần thiết kế `synchronized` theo phạm vi lexical | Có thể giữ explicit lock qua call boundaries, nhưng dễ quên unlock |
| Chi phí | Phụ thuộc JVM/contended/uncontended workload | Phụ thuộc implementation/fairness/contended workload |

**Không có đáp án “`ReentrantLock` luôn nhanh hơn” hoặc “`synchronized` luôn chậm hơn”.** JVM tối ưu monitor và lock library theo nhiều điều kiện. Đo đạc workload, lock contention và latency trước khi chọn vì hiệu năng.

## 3. Intrinsic monitor hoạt động ra sao?

### 3.1. Monitor identity

Ba dạng hay gặp:

```java
class Example {
    private final Object lock = new Object();
    private static int globalCount;
    private int localCount;

    void withBlock() {
        synchronized (lock) {
            localCount++;
        }
    }

    synchronized void withInstanceMonitor() {
        localCount++;
    }

    static synchronized void withClassMonitor() {
        globalCount++;
    }
}
```

Đây là snippet class; chưa có `main`. `withBlock` dùng monitor của object `lock`, `withInstanceMonitor` dùng monitor của `this`, còn `static synchronized` dùng monitor của `Example.class`. **Ba monitor này không phải một.** Nếu hai method cùng sửa `localCount` nhưng dùng các monitor khác nhau, chúng **không** tự loại trừ nhau. Trong ví dụ, nếu người gọi có thể gọi hai method đồng thời trên cùng instance, cần thống nhất **một** khóa cho cả hai đường cập nhật.

Khóa trên `this` có thể bị code bên ngoài làm ảnh hưởng, nếu caller viết `synchronized (instance)`. Khóa bằng một object riêng `private final Object lock` giúp tránh giao thức khóa bị can thiệp ngoài ý muốn. Không khóa trên những object có thể được chia sẻ không chủ đích như string literal hay wrapper được cache.

### 3.2. Nhả monitor theo scope

`synchronized` tự nhả khóa khi đường thực thi rời khỏi khối, kể cả khi có `return` hoặc exception:

```java
synchronized (lock) {
    if (someCondition) {
        return;
    }
    updateState();
}
```

Đây là snippet bên trong method, giả định `lock`, `someCondition` và `updateState()` đã được định nghĩa. Không cần gọi `unlock` thủ công. Tuy vậy, tự nhả khóa **không rollback dữ liệu** đã được sửa một phần trước khi exception; invariant nghiệp vụ vẫn do code bảo vệ.

### 3.3. Reentrancy và sự khác nhau giữa các monitor

Một thread giữ monitor `m` có thể đi vào lại `synchronized(m)`. Điều đó hữu ích khi method synchronized gọi method synchronized khác cùng instance. Nhưng nested acquisition của **hai monitor khác nhau** vẫn có thể deadlock nếu hai thread lấy theo thứ tự ngược nhau.

### 3.4. Chờ để lấy monitor

Nếu thread A đang giữ monitor, thread B cố vào cùng `synchronized` sẽ thường ở `Thread.State.BLOCKED`. `Thread.interrupt()` không khiến B ném `InterruptedException` chỉ vì đang chờ monitor. Sau khi A nhả, B có thể vào dù interrupt flag đã được đặt. Đừng nhầm với `Object.wait()` bên trong monitor: **`wait()` hỗ trợ interrupt** và có semantics riêng.

## 4. `Lock` là hợp đồng gì, `ReentrantLock` bổ sung gì?

Các method cốt lõi của `java.util.concurrent.locks.Lock`:

| Method | Ý nghĩa |
| --- | --- |
| `lock()` | Lấy khóa, có thể phải chờ; xử lý interrupt trong khi chờ tùy hợp đồng triển khai. |
| `lockInterruptibly()` | Cố lấy khóa và cho phép thoát bằng `InterruptedException` khi bị interrupt. |
| `tryLock()` | Cố lấy khóa ngay; trả `true` khi lấy được và `false` nếu chưa lấy được. |
| `tryLock(long time, TimeUnit unit)` | Đợi có giới hạn thời gian để lấy khóa; trả `true/false`; hỗ trợ interruption. |
| `unlock()` | Nhả khóa mà thread đang sở hữu; với `ReentrantLock`, gọi sai owner có thể ném `IllegalMonitorStateException`. |
| `newCondition()` | Tạo đối tượng `Condition` cho phối hợp trên khóa, nếu implementation hỗ trợ. |

`ReentrantLock` cung cấp một implementation reentrant và các thông tin giám sát như `isLocked()`, `isHeldByCurrentThread()`, `getHoldCount()`, `hasQueuedThreads()` và khả năng cấu hình fairness lúc khởi tạo. Một số method quan sát chỉ phản ánh **snapshot**, không nên dùng để tự dựng thuật toán điều phối phụ thuộc timing.

**Không phải bất kỳ object implement `Lock` nào cũng có mọi đặc tính của `ReentrantLock`.** Đọc hợp đồng của implementation cụ thể trước khi giả định nó reentrant, fair hoặc có cách chờ tương tự.

### Cú pháp an toàn bắt buộc cho explicit lock

```java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Snippet giả định `lock` là `Lock` và `updateSharedState()` là operation cần bảo vệ. `lock.lock()` đặt **trước** `try`: nếu acquisition thất bại/throw thì ta không `unlock` một lock chưa sở hữu. Sau khi lấy khóa thành công, phần thay đổi dữ liệu nằm trong `try` và việc nhả luôn trong `finally`.

**Lỗi nghiêm trọng:** gọi `lock.lock()` rồi có `return` hoặc exception trước `unlock()` mà không có `finally`. Mọi thread khác có thể chờ vô hạn; lỗi khó debug hơn `synchronized` vì JVM không tự nhả explicit `Lock` ở cuối method.

## 5. Ví dụ Java 17: hai counter đều đúng, khác cách quản lý khóa

Tạo tệp `MonitorVsLockCounter.java`:

```java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantLock;

public class MonitorVsLockCounter {
    static class MonitorCounter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    static class ExplicitCounter {
        private final Lock lock = new ReentrantLock();
        private int value;

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int get() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        MonitorCounter monitor = new MonitorCounter();
        ExplicitCounter explicit = new ExplicitCounter();

        Runnable task = () -> {
            for (int i = 0; i < 10_000; i++) {
                monitor.increment();
                explicit.increment();
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("monitor=" + monitor.get());
        System.out.println("lock=" + explicit.get());
    }
}
```

Chạy:

```bash
javac MonitorVsLockCounter.java
java MonitorVsLockCounter
```

Stdout xác định:

```text
monitor=20000
lock=20000
```

Mỗi worker chạy `10_000` lần; tổng hai worker tạo `20_000` cập nhật trên mỗi counter. `synchronized` và `ReentrantLock` bảo vệ nguyên tử của phép `value++`, còn `join()` bảo đảm main đợi các worker kết thúc trước khi đọc. Đây là **ví dụ đúng về atomicity và visibility**, **không phải benchmark** tốc độ hai kiểu khóa. Nếu một method đọc trực tiếp `value` mà không dùng cùng giao thức, class có thể không còn thread-safe.

## 6. Điểm mạnh của `Lock`: thử lấy khóa và timeout

Với `synchronized`, một thread muốn vào monitor thường phải chờ tới khi lấy được; không có `synchronized.tryLock` hoặc cú pháp chờ tối đa 200 ms. Khi nghiệp vụ cần “không lấy được khóa thì trả về nhanh, báo busy hoặc dùng phương án khác”, `tryLock` hữu ích:

```java
if (lock.tryLock()) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} else {
    handleBusy();
}
```

Snippet giả định có `lock`, `doWork` và `handleBusy`. `tryLock()` không chờ dài để tranh lock. Nếu dùng:

```java
if (lock.tryLock(200, TimeUnit.MILLISECONDS)) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} else {
    handleTimeout();
}
```

Snippet này phải nằm trong method xử lý `InterruptedException` và cần import `java.util.concurrent.TimeUnit`. Timed `tryLock` có thể chờ tới thời hạn rồi trả `false` nếu không lấy được; thời điểm thực tế còn tùy scheduler. Nếu bị interrupt khi đang chờ, có thể ném `InterruptedException`; phải propagate hoặc restore flag theo chính sách dừng.

### Ví dụ Java 17 chạy được: thử khóa khi thread khác đang giữ

Tạo `TryLockExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockExample {
    public static void main(String[] args) throws Exception {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch acquired = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                acquired.countDown();
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        });

        holder.start();
        try {
            if (!acquired.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Holder did not acquire");
            }

            boolean immediate = lock.tryLock();
            if (immediate) {
                lock.unlock();
            }
            System.out.println("immediate=" + immediate);

            boolean timed = lock.tryLock(50, TimeUnit.MILLISECONDS);
            if (timed) {
                lock.unlock();
            }
            System.out.println("timed=" + timed);
        } finally {
            release.countDown();
            holder.join();
        }

        lock.lockInterruptibly();
        try {
            System.out.println("afterRelease=true");
        } finally {
            lock.unlock();
        }
    }
}
```

```bash
javac TryLockExample.java
java TryLockExample
```

Stdout khi chương trình hoàn thành bình thường:

```text
immediate=false
timed=false
afterRelease=true
```

Main chỉ bắt đầu thử lấy khóa sau khi `holder` báo đã giữ `lock` qua latch `acquired`. Holder chỉ nhả sau khi main mở `release` trong `finally`, nên **cả immediate và timed tryLock đều không lấy được** trên đường chạy bình thường. Sau `holder.join()`, khóa đã được nhả; main lấy thành công bằng `lockInterruptibly()` rồi in dòng cuối.

Timeout `50 ms` ở đây là minh họa API, không phải một benchmark chính xác 50 ms. Trong test/production cần điều chỉnh deadline phù hợp môi trường, xử lý interrupt và không dựa vào một `sleep` để “hy vọng” holder đang giữ khóa. Hai latch cho ta thứ tự điều phối rõ ràng.

### `lockInterruptibly()` cần khi nào?

Nếu một thread đã bắt đầu đợi khóa nhưng yêu cầu của người dùng bị hủy hoặc ứng dụng đang shutdown, `lockInterruptibly()` cho phép chờ khóa có thể dừng theo interrupt. Khi bị interrupt trong lúc chờ, method ném `InterruptedException` và không trả về như thể đã lấy khóa. Caller không được `unlock()` nếu acquisition chưa thành công.

`ReentrantLock.lock()` thông thường không dùng `InterruptedException` làm đường trả về khi đang tranh lock; nếu cần cancellation có kiểm soát hãy chọn `lockInterruptibly()` hoặc timed `tryLock`. Sau khi **đã** lấy khóa, interrupt không tự động nhả khóa của thread: code vẫn chịu trách nhiệm release trong `finally`.

## 7. `Condition` so với `Object.wait/notifyAll`

**Mutual exclusion** trả lời “ai được vào critical section?”. **Condition waiting** trả lời “khi điều kiện nghiệp vụ chưa đúng, làm sao thread đang giữ khóa tạm nhả khóa để người khác thay đổi điều kiện?”. Cả intrinsic monitor lẫn explicit `Lock` đều hỗ trợ cơ chế chờ, nhưng API khác nhau.

### 7.1. Với intrinsic monitor

Một producer/consumer chờ trên chính monitor `monitor`:

```java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    consume();
}
```

Đây là snippet, giả định `ready` và `consume()` được bảo vệ bằng `monitor`. `wait()` yêu cầu caller sở hữu **monitor của object được gọi `wait`**, nếu không ném `IllegalMonitorStateException`. Khi chờ, `wait()` nhả monitor đó; sau khi được đánh thức, thread phải **lấy lại monitor** trước khi `wait()` trở về.

Producer dùng:

```java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
```

`notifyAll()` đánh thức những waiter thuộc wait set của monitor; nó không trao monitor ngay lập tức cho waiter. Producer còn giữ monitor tới khi rời synchronized block. Waiter phải dùng **`while`** để kiểm tra lại predicate do spurious wakeup, có nhiều consumer hoặc predicate đã đổi trước khi nó lấy lại lock.

### 7.2. Với `Lock` và `Condition`

`ReentrantLock.newCondition()` trả một `Condition` gắn với explicit lock:

```java
lock.lock();
try {
    while (!ready) {
        readyCondition.await();
    }
    consume();
} finally {
    lock.unlock();
}
```

Producer:

```java
lock.lock();
try {
    ready = true;
    readyCondition.signalAll();
} finally {
    lock.unlock();
}
```

Đây là hai snippet trong cùng class giả định `lock` là `ReentrantLock`, `readyCondition = lock.newCondition()` và `ready/consume` dùng cùng lock; cần import `java.util.concurrent.locks.Condition`, `ReentrantLock`. `await()` chỉ được gọi khi caller đang giữ lock liên kết; nó **nhả lock trong lúc chờ rồi lấy lại trước khi trở về**. `signal()`/`signalAll()` yêu cầu giữ lock tương ứng đối với `ReentrantLock.ConditionObject`, nếu không ném `IllegalMonitorStateException`.

**Condition không phải một mutex khác:** nó là **hàng đợi chờ điều kiện** liên kết với lock. Cùng lock có thể tạo hai condition khác nhau như `notEmpty` và `notFull`, trong khi một intrinsic monitor có một wait set mặc định.

### 7.3. `await` không giống `sleep`

| Thao tác | Có nhả khóa đang sử dụng để chờ không? | Có nhận tín hiệu không? |
| --- | --- | --- |
| `Object.wait()` | Nhả monitor của đúng object `wait` | `notify/notifyAll`, interrupt, spurious wakeup |
| `Condition.await()` | Nhả **associated Lock**, sau đó lấy lại trước khi return | `signal/signalAll`, interrupt, spurious wakeup |
| `Thread.sleep(ms)` | **Không tự nhả** monitor hay `Lock` đang giữ | Có thể hết thời gian hoặc bị interrupt |
| `LockSupport.park()` | **Không tự nhả** monitor/`Lock` đang giữ | Permit từ `unpark`, interrupt, spurious return |

Nếu sleep khi đang giữ khóa rồi chờ một thread khác thay đổi predicate dưới cùng khóa, thread kia không thể vào để thay đổi dữ liệu. `wait/await` được thiết kế để tạm nhả khóa nhằm tạo cơ hội cho state tiến triển.

## 8. Ví dụ Java 17: một khóa, hai điều kiện `notEmpty` và `notFull`

Một “single-slot buffer” chỉ lưu một phần tử tại một thời điểm. Producer phải chờ khi buffer đầy; consumer phải chờ khi buffer rỗng. `ReentrantLock` cho phép hai queue chờ riêng để phát tín hiệu đúng nhóm:

Tạo `ConditionBufferExample.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionBufferExample {
    static class OneSlotBuffer {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private Integer item;

        void put(int value) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (item != null) {
                    notFull.await();
                }
                item = value;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        int take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (item == null) {
                    notEmpty.await();
                }
                int result = item;
                item = null;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        OneSlotBuffer buffer = new OneSlotBuffer();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Integer> consumer = pool.submit(buffer::take);
            Future<Void> producer = pool.submit(() -> {
                buffer.put(42);
                return null;
            });

            producer.get(5, TimeUnit.SECONDS);
            int received = consumer.get(5, TimeUnit.SECONDS);
            System.out.println("received=" + received);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac ConditionBufferExample.java
java ConditionBufferExample
```

Stdout khi chương trình hoàn thành bình thường:

```text
received=42
```

**Phân tích:**

1. Nếu consumer tới trước, nó lấy `lock`, thấy `item == null` rồi gọi `notEmpty.await()`: **nhả lock** và chờ.
2. Producer lấy lock, đặt `item = 42`, gọi `notEmpty.signal()`, nhả lock. Consumer sau khi lấy lại lock kiểm tra predicate lần nữa rồi đọc 42.
3. Nếu producer tới trước, `item` đã có 42 khi consumer tới; consumer không cần `await()`. Hai thứ tự đều tạo kết quả như nhau.
4. `notFull` sẽ có ích khi producer tiếp theo tới lúc slot đang đầy. Ví dụ chỉ có một phần tử, nên đường chờ `notFull` không nhất thiết xảy ra, nhưng code cài đặt đủ cả hai điều kiện.
5. `producer.get` và `consumer.get` chuyển các exception từ task về main, đồng thời chờ kết quả. Timeout ở caller không tự bảo đảm task đã dừng; `shutdownNow()` thử interrupt các worker nếu chưa hoàn tất.

Vì dùng `Integer` làm marker có/không dữ liệu, `null` được dành riêng cho trạng thái rỗng; nếu bài toán cho phép payload null, cần một cờ `occupied` riêng hoặc cấu trúc biểu diễn khác. Đây là ví dụ học tập; trong ứng dụng thực tế hãy cân nhắc `ArrayBlockingQueue`, vốn đã bao gói quy tắc đồng bộ, bound và signals đúng cách.

**Vì sao hai `Condition` có ích?** Với cùng một intrinsic monitor, `notify()` có thể đánh thức một waiter không thể tiến triển (ví dụ producer trong khi buffer vẫn đầy), nên các triển khai đơn giản thường dùng `notifyAll()` rồi kiểm tra lại predicate. Với `ReentrantLock`, `notEmpty.signal()` hướng đến nhóm consumer, `notFull.signal()` hướng đến nhóm producer; vẫn phải dùng `while` và giữ khóa khi signal.

## 9. Tương đương bằng monitor và khi nào đủ dùng

Nếu chỉ có một condition hoặc tải thấp, intrinsic monitor thường ngắn gọn:

```java
class MonitorOneSlotBuffer {
    private Integer item;

    synchronized void put(int value) throws InterruptedException {
        while (item != null) {
            wait();
        }
        item = value;
        notifyAll();
    }

    synchronized int take() throws InterruptedException {
        while (item == null) {
            wait();
        }
        int result = item;
        item = null;
        notifyAll();
        return result;
    }
}
```

Snippet class Java 17 không có `main`. Ở đây synchronized instance methods dùng monitor của `this`. `wait()` và `notifyAll()` được gọi ngầm trên `this` khi thread đang giữ monitor ấy. Dùng `notifyAll` để thông báo cả các waiter có predicate khác nhau, rồi mỗi thread **tự kiểm tra lại while**; đây là một tradeoff đơn giản nhưng có thể đánh thức thừa người chờ.

Không nên chuyển mọi `synchronized` sang `ReentrantLock` chỉ vì “Lock nhiều tính năng hơn”. Nếu bài toán chỉ là một critical section ngắn, một khóa rõ identity và không cần timeout hay điều kiện riêng, `synchronized` thường dễ đọc và ít rủi ro quên nhả khóa.

## 10. Các bảo đảm Java Memory Model

Khóa bảo vệ **hai thứ**: mutual exclusion tại critical section và memory synchronization giữa các thread tham gia cùng giao thức.

### 10.1. Với monitor

Một thread nhả (unlock) monitor `M` happens-before lần lock tiếp theo của monitor `M`. Do đó:

```java
synchronized (monitor) {
    sharedValue = 42;
}
```

và về sau:

```java
synchronized (monitor) {
    System.out.println(sharedValue);
}
```

Các snippet giả định cùng monitor và biến `sharedValue`, không phải chương trình độc lập. Nếu read thực sự lấy monitor sau khi writer đã nhả và không có writer khác xen vào sửa, nó có thể thấy bản ghi 42 theo memory synchronization. Nếu dùng **hai monitor khác nhau**, không có monitor-happens-before giữa chúng chỉ vì cùng từ khóa `synchronized`.

### 10.2. Với `Lock`

Theo hợp đồng `Lock`, một `unlock` thành công có memory synchronization effects như thao tác nhả monitor; `lock` thành công như thao tác lấy monitor. Vì thế caller không cần thêm `volatile` cho một field thường đã được **mọi** đường đọc/ghi bảo vệ bằng cùng `ReentrantLock`.

Tuy nhiên: **`lock.tryLock()` trả `false` không phải lần acquisition thành công**; nó không bảo vệ critical section và không nên được coi là “đã đồng bộ dữ liệu rồi”. Tương tự, các method trạng thái như `isLocked()` không thay thế thao tác lấy lock thật để đọc state cần bảo vệ.

### 10.3. Với `wait` và `await`

Khi chờ, thread nhả monitor/associated lock và sau đó lấy lại; cùng với quan hệ release/acquire tạo cơ chế publication của producer cho consumer. **Signal chỉ thông báo**; predicate dữ liệu nằm dưới cùng khóa mới là sự thật cần kiểm tra. Không đặt niềm tin vào “có signal thì condition chắc chắn còn đúng” vì các waiter khác có thể đã tiêu thụ tài nguyên trước khi thread vừa tỉnh lấy lại khóa.

### 10.4. Happens-before không đồng nghĩa một workflow atomic

Ví dụ:

```java
if (stock > 0) {
    stock--;
}
```

Nếu hai thread được phép xen giữa check và decrement, cả hai có thể thấy cùng stock cũ. Dùng một `volatile int stock` chưa đủ. Đưa **cả check và decrement** vào cùng `synchronized`/`lock`, hoặc dùng CAS trên một atomic variable là cách bảo vệ invariant. Một thao tác `join()` sau khi worker hoàn thành giúp main quan sát kết quả, **không thể hồi phục cập nhật đã bị mất** trước đó.

## 11. Fairness, starvation và tính reentrant

### 11.1. `ReentrantLock(true)` có ý nghĩa gì?

`new ReentrantLock(true)` yêu cầu chính sách fairness: khi tranh lock, implementation có khuynh hướng nhường cho thread đã chờ lâu hơn theo hợp đồng của lock. Nhưng:

- Không đảm bảo fairness ở cấp **CPU scheduling** hoặc mọi thời điểm lấy lock tuyệt đối.
- `tryLock()` không tham số có thể **barging** và lấy lock nếu đang rảnh ngay, ngay cả với fair lock có thread khác đang xếp hàng.
- Fairness thường có chi phí throughput/latency cao hơn trong nhiều workload; không bật vô điều kiện vì nghe có vẻ công bằng.
- Nếu cần timed acquisition tôn trọng fairness thì đọc rõ semantics của `tryLock(timeout, unit)` đối với `ReentrantLock`.
- Fairness không giải quyết chương trình giữ lock quá lâu, deadlock do thứ tự nhiều lock, hoặc phụ thuộc bên ngoài không hoàn thành.

### 11.2. Reentrancy không có nghĩa là vô hạn hoặc không tốn gì

`ReentrantLock` cho phép cùng thread `lock()` nhiều lần; mỗi lần tăng hold count. Thread phải `unlock()` **cùng số lần đã lấy** trước khi người khác có thể vào. Với `synchronized`, monitor cũng reentrant và nesting được JVM quản lý theo scope.

Ví dụ:

```java
lock.lock();
try {
    lock.lock();
    try {
        // Cùng thread đang giữ lock hai lần.
    } finally {
        lock.unlock();
    }
} finally {
    lock.unlock();
}
```

Snippet giả định `lock` là `ReentrantLock`. Nếu chỉ gọi `unlock` một lần, hold count còn 1 và lock vẫn do thread đó sở hữu. Do đó nested acquisition cần được cân nhắc; thường giữ code theo một discipline đơn giản để tránh lỗi này.

### 11.3. Starvation và priority inversion

Không một mutex nào đảm bảo business request luôn được phục vụ công bằng theo SLA. Khi một thread giữ khóa lâu, các thread khác phải chờ; nếu thread giữ khóa bị scheduler trì hoãn hoặc làm blocking I/O, latency toàn hệ thống tăng. Một fair `ReentrantLock` có thể giúp giảm một số hiện tượng tranh lock không công bằng, nhưng không phải công cụ giải quyết toàn bộ priority inversion hoặc overloading.

## 12. Lựa chọn `lockInterruptibly` và xử lý interruption

Một khía cạnh khác biệt quan trọng giữa monitor và `Lock` là **hủy khi còn đang đợi acquisition**:

| Tình huống | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Đang cố lấy khóa | Interrupt không hủy intrinsic monitor acquisition | `lockInterruptibly()` có thể ném `InterruptedException` |
| Đã giữ khóa, thread bị interrupt | Không tự nhả monitor | Không tự nhả explicit lock |
| Đang chờ condition | `Object.wait()` phản hồi interrupt bằng exception | `Condition.await()` phản hồi interrupt theo hợp đồng |
| Muốn chờ tối đa 250 ms để **lấy** lock | Không có timed intrinsic monitor acquisition | `tryLock(250, TimeUnit.MILLISECONDS)` |
| Muốn thử ngay không chờ | Không có non-blocking monitor try-acquire trong cú pháp `synchronized` | `tryLock()` |

**Đừng nhầm acquisition với condition waiting.** `Object.wait(timeout)` có timeout nhưng nó chỉ được gọi **sau khi thread đã sở hữu monitor**, nhằm chờ một điều kiện; nó **không** khiến thao tác đi vào `synchronized` có timeout. Tương tự `Condition.await(timeout)` khác `lock.tryLock(timeout)`: cái đầu đợi condition trong lúc tạm nhả lock; cái sau đợi để lấy lock.

Khi bắt `InterruptedException` và không ném tiếp, thường khôi phục flag `Thread.currentThread().interrupt()` rồi kết thúc đường công việc phù hợp. Không nuốt interrupt rồi lặp vô hạn. Với `ReentrantLock.lockInterruptibly()`, nếu method ném `InterruptedException` trước khi trả về thành công, caller **chưa có khóa** nên không được `unlock()` như thể đã có.

## 13. Thread dump và công cụ quan sát

Trên HotSpot/OpenJDK, `jcmd <pid> Thread.print -l` hoặc Java Flight Recorder có thể giúp xem lock contention và các thread đang chờ. Ý nghĩa cần phân biệt:

- Thread đợi **intrinsic monitor** của `synchronized` thường hiện `BLOCKED (on object monitor)`.
- Thread đợi `ReentrantLock` thông qua cơ chế `LockSupport.park`/`AbstractQueuedSynchronizer` thường có thể ở `WAITING` hoặc `TIMED_WAITING`, tùy method, timeout và runtime.
- Thread đợi `Object.wait()` trên condition của monitor thường hiện `WAITING`; đợi `Object.wait(timeout)` thường `TIMED_WAITING`.
- Thread đợi `Condition.await()` cũng có thể xuất hiện trong stack qua `LockSupport`/`AbstractQueuedSynchronizer.ConditionObject`.
- Không kết luận có deadlock từ một thread đơn lẻ `BLOCKED` hay `WAITING`; tìm chu trình khóa và owner, kiểm tra nhiều snapshot, thời gian chờ và đường gọi.

Ví dụ command (thay PID thật):

```bash
jcmd <PID> Thread.print -l
```

Không đưa command này vào stdout của chương trình Java ở trên. Nội dung dump phụ thuộc JDK, phiên bản và thời điểm quan sát.

`ThreadMXBean` có API phát hiện một số deadlock liên quan monitors và ownable synchronizers. Nó hữu ích khi kiểm tra `synchronized` và `ReentrantLock`, nhưng không thể chứng minh không có deadlock nghiệp vụ liên quan DB/HTTP/queue hoặc mọi điều kiện chờ khác.

## 14. Các lỗi rất dễ mắc khi chuyển từ monitor sang `Lock`

### 14.1. Quên nhả explicit lock

```java
lock.lock();
doWork();             // Nếu ném exception, unlock bị bỏ qua.
lock.unlock();
```

Sai khi `doWork()` throw. Sửa bằng `try/finally` ngay sau acquisition thành công.

### 14.2. `unlock` khi chưa có khóa

```java
if (lock.tryLock()) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
}
```

Đúng vì chỉ `unlock` nếu `tryLock` trả true. Nếu `tryLock` false hoặc `lockInterruptibly` bị ngắt trước khi lấy khóa, không được `unlock`. Với `ReentrantLock`, thread khác gọi `unlock` sẽ ném `IllegalMonitorStateException`; không có “unlock hộ” owner.

### 14.3. Trộn `synchronized(lock)` với `lock.lock()`

```java
ReentrantLock lock = new ReentrantLock();

// Thread A:
synchronized (lock) {
    update();
}

// Thread B:
lock.lock();
try {
    update();
} finally {
    lock.unlock();
}
```

Đây là snippet minh họa hai đường code, không phải một chương trình chạy độc lập. **Hai thứ không bảo vệ nhau:** đường A lấy *intrinsic monitor của object ReentrantLock*, đường B lấy *trạng thái explicit ReentrantLock*. Vì vậy A và B có thể vào hai vùng đồng thời dù dùng đúng cùng biến reference tên `lock`. Chọn **một cơ chế thống nhất** cho mọi actor truy cập cùng state.

### 14.4. Dùng điều kiện sai lock

```java
Condition condition = lock.newCondition();
// ...
condition.await();
```

Nếu caller chưa giữ đúng `lock`, `ReentrantLock` sẽ ném `IllegalMonitorStateException`. Khi signal cũng vậy: phải giữ lock tương ứng khi gọi `condition.signal()`/`signalAll()`. Khi có hai condition từ cùng lock, cả hai vẫn bảo vệ dữ liệu bằng **chính lock ấy**; condition chỉ phân nhóm người chờ.

### 14.5. Dùng `if` thay `while`

```java
if (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

Sai vì spurious wakeup hoặc một consumer khác có thể lấy mất phần tử trước khi thread vừa thức lấy lại khóa. Dùng:

```java
while (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

Hai snippet giả định `queue`, `notEmpty` và khóa đang được giữ. Với condition waiting, **luôn gắn việc chờ với predicate thật được bảo vệ bởi cùng khóa**.

### 14.6. Signal ngoài critical section

Thao tác sửa predicate và signal cần nằm trong giao thức lock nhất quán. Nếu set `ready` không đồng bộ rồi `signal` ngoài lock, code vừa sai với contract Condition của `ReentrantLock` vừa có thể bỏ lỡ tín hiệu hoặc thấy dữ liệu không đúng. Hãy cập nhật state và phát signal **trong khi giữ lock**, còn việc thread được đánh thức vẫn cần chờ lock được nhả.

### 14.7. Lock quá rộng và I/O trong critical section

Đặt HTTP/DB call, `Thread.sleep` hoặc callback không tin cậy trong khi đang giữ lock có thể khiến thread khác chờ lâu, tăng tail latency, hoặc deadlock khi callback lấy khóa theo thứ tự khác. Cố gắng chỉ giữ lock để chuyển trạng thái bất biến; đưa I/O/callback ra ngoài nếu nghiệp vụ cho phép. Nếu phải giữ khóa để bảo toàn transaction, đặt deadline, kiểm soát lock order và thiết kế failure mode.

## 15. Lock ordering, deadlock và “độc quyền” không đồng nghĩa “không lỗi”

Giả sử A lấy `lock1` rồi `lock2`, còn B lấy `lock2` rồi `lock1`. Cả hai có thể giữ một khóa và đợi khóa còn lại mãi. Điều này xảy ra với **cả intrinsic monitor lẫn `ReentrantLock`**. Một chính sách giúp giảm deadlock là luôn lấy nhiều khóa theo **thứ tự toàn cục nhất quán**. Nếu chỉ có `Lock` và logic cho phép, `tryLock(timeout)` có thể giúp phát hiện/thoát tình huống chờ, nhưng không tự sửa invariant nghiệp vụ hoặc bảo đảm liveness khi retry.

Việc thêm mutex cũng có thể tạo **lock convoy** (nhiều thread xếp hàng sau holder chậm), contention và giới hạn throughput. Khi đã bảo vệ tính đúng đắn, nên đo critical-section duration, queue wait, p95/p99, CPU, thread dumps/JFR và ưu tiên thiết kế giảm shared mutable state hoặc phân vùng ownership nếu cần.

**Đừng dựa vào `Thread.sleep` để “đợi khóa được nhả”**. Trong code đã nắm khóa, sleep không nhả. Ngoài critical section, sleep vẫn không phải tín hiệu đồng bộ; hãy dùng `Condition`, `BlockingQueue`, `CountDownLatch` hoặc hợp đồng khác đúng mục đích.

## 16. Những câu hỏi chọn công cụ trong thực tế

| Yêu cầu | Gợi ý | Tại sao |
| --- | --- | --- |
| Bảo vệ một counter/collection đơn giản với một critical section ngắn | `synchronized`; hoặc atomic class nếu đúng operation | Gọn, tự nhả khóa, dễ review |
| Muốn thử ngay, không chờ nếu tài nguyên bận | `Lock.tryLock()` | Nhận false và xử lý busy |
| Muốn giới hạn thời gian **đợi lấy khóa** | `Lock.tryLock(timeout, unit)` | Hỗ trợ deadline ở acquisition |
| Muốn phản hồi interrupt khi **đang tranh khóa** | `lockInterruptibly()` | Có đường cancel chờ acquisition |
| Cần hai hoặc nhiều nhóm chờ trên cùng state | `ReentrantLock` + nhiều `Condition` | `notEmpty`/`notFull`, tránh đánh thức nhầm nhóm |
| Chỉ một condition đơn giản, chờ theo predicate | `synchronized` + `wait/notifyAll` có thể đủ | Không cần quản lý explicit unlock |
| Cần công bằng hơn khi tranh khóa | Cân nhắc `ReentrantLock(true)` và đo thực tế | Fairness có chi phí, không cam kết lịch CPU tuyệt đối |
| Nhiều reader ít writer trên cấu trúc lớn | Đánh giá `ReadWriteLock` hoặc immutable snapshot | Có thể tăng concurrency đọc, nhưng phức tạp hơn; không tự tốt hơn |
| Dữ liệu cực đơn giản một biến | `AtomicInteger`/`AtomicReference` | Operation cụ thể có thể atomic mà không cần mutex |
| Producer–consumer queue chuẩn | `BlockingQueue` | Có sẵn điều kiện chờ và giao thức thread-safe đã được kiểm chứng |

**`ReadWriteLock`** là interface khác, có `readLock()` và `writeLock()` trả về các `Lock` tương ứng; nó **không tự tương đương** với một `Lock` duy nhất. `StampedLock` cũng là công cụ riêng có API và hợp đồng khác, **không trực tiếp implements `Lock`**. Đừng chuyển thiết kế chỉ vì tên nghe mạnh hơn; chọn theo invariant, đường đọc/ghi, điều kiện chờ, fairness và tải thực tế.

### Java 21+ và virtual threads

Virtual thread vẫn phải bảo vệ shared mutable state theo Java Memory Model như platform thread. `synchronized`, `Lock` và atomic classes vẫn có ý nghĩa; virtual thread **không tự khiến race condition biến mất**. Hành vi blocking/pinning của monitor/lock và khả năng quan sát qua runtime có thể khác giữa các phiên bản JDK; khi triển khai số lượng lớn virtual threads, đo JFR/thread diagnostics theo bản JDK thực tế. Bài học ở đây sử dụng các API ổn định chạy được từ Java 17.

## 17. Bài tập tự kiểm tra

**1. Cả `synchronized` và `ReentrantLock` có bảo đảm visibility không?** Có, khi reader/writer tham gia **cùng monitor hoặc cùng explicit lock** theo hợp đồng unlock→lock. Tự khóa những object khác nhau không tạo bảo đảm chung.

**2. Vì sao `lock.lock()` nên đứng trước `try`?** `unlock()` chỉ được gọi sau acquisition thành công. Đặt acquisition bên trong `try` với `finally { unlock(); }` có thể khiến finally unlock khi chưa có khóa nếu acquisition throw.

**3. Khi thread đợi lấy monitor `synchronized`, gọi `interrupt()` có làm nó thoát khỏi việc chờ monitor và ném `InterruptedException` không?** Không. Muốn interruptible acquisition, dùng `Lock.lockInterruptibly()` hoặc timed `tryLock`. Tuy nhiên `Object.wait()` sau khi đã vào monitor có phản hồi interrupt.

**4. `wait(1000)` có đặt timeout cho việc vào `synchronized` không?** Không. `Object.wait(1000)` là chờ condition với timeout sau khi đang sở hữu monitor; nó nhả monitor trong lúc đợi rồi lấy lại trước khi trả về.

**5. `synchronized (lock)` trên một `ReentrantLock` object có tương đương `lock.lock()` không?** Không. Cái trước lấy intrinsic monitor của object; cái sau dùng explicit lock state.

**6. Vì sao phải dùng `while` quanh `Condition.await()`?** Có thể spurious wakeup, cạnh tranh nhiều consumer, hoặc predicate đã đổi trước khi thread lấy lại khóa. Chỉ predicate đã kiểm tra dưới lock mới quyết định được đi tiếp.

**7. Một buffer có hai condition `notFull` và `notEmpty`; có phải hai mutex khác nhau không?** Không. Chúng là hai wait sets gắn với **một ReentrantLock**, chia nhóm waiter nhưng dữ liệu vẫn được bảo vệ dưới cùng mutex.

**8. Có nên bật `ReentrantLock(true)` cho mọi ứng dụng?** Không. Fairness có tradeoff và không bảo đảm thứ tự scheduling tuyệt đối. Bắt đầu từ tính đúng đắn, theo dõi starvation/latency thực tế, chỉ bật nếu có yêu cầu và số đo chứng minh phù hợp.

**9. `Lock.tryLock()` trả false có nghĩa một thao tác đọc mutable state sau đó an toàn không?** Không. Caller chưa sở hữu lock; không được vào critical section hay coi failure là memory handoff hợp lệ.

**10. Một thread đã `signal()`, waiter có lập tức chạy phần sau `await()` không?** Không. Waiter phải **lấy lại lock** trước khi `await` trở về, và sau đó kiểm tra lại predicate; signal không tự chuyển quyền sở hữu mutex.

## 18. Checklist trước khi lựa chọn hoặc review

- **Invariant cần bảo vệ là gì?** Một phép tăng, check–then–act, nhiều field hay một hàng đợi có condition?
- **Lock identity có đúng không?** Mọi reader/writer dùng cùng monitor hoặc cùng `Lock`, không vô tình trộn hai loại khóa?
- **Có yêu cầu timeout/interrupt khi đợi khóa không?** Nếu có, `Lock.tryLock`/`lockInterruptibly` hữu ích.
- **Nếu dùng `Lock`, mọi đường acquisition thành công có nhả bằng `finally` không?** Có đường `return`/throw quên unlock?
- **Nếu dùng `Condition`, predicate được bảo vệ bằng cùng lock, `await` nằm trong `while` và signal được gọi khi đang giữ khóa chưa?**
- **Nếu dùng `Object.wait`, caller có giữ đúng monitor và kiểm tra lại condition sau khi thức không?**
- **Có giữ khóa khi làm I/O, sleep hoặc gọi callback bất định không?** Xem xét tách việc ra ngoài critical section.
- **Có nhiều khóa cần thứ tự lấy nhất quán không?** Nếu có vòng lock-order, cần thiết kế tránh deadlock.
- **Có cần fairness và đã đo contention/throughput chưa?** Không bật fair lock theo cảm tính.
- **Test có xác minh invariant và nhiều interleaving không?** Có deadline, cancellation và xử lý lỗi worker?
- **Đang dùng virtual threads?** Vẫn phải áp dụng đúng JMM và benchmark trên JDK thực tế.

**Kết luận:** `synchronized` là lựa chọn đơn giản, an toàn theo scope cho monitor mutual exclusion và một wait set gắn với object. `Lock`, đặc biệt `ReentrantLock`, mở thêm quyền kiểm soát acquisition (thử ngay, timeout, interruptible), fairness và nhiều `Condition`. Cả hai chỉ thật sự bảo vệ dữ liệu khi **đúng khóa, đúng phạm vi invariant và đúng giao thức trên mọi đường truy cập**; chọn theo nhu cầu cụ thể và đo hậu quả concurrency thay vì mặc định thay toàn bộ một bên bằng bên kia.