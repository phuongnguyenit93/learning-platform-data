# Chuyển trạng thái Thread khi vào monitor hoặc chờ lock trong Java

> **Ngữ cảnh:** vòng đời `Thread` và các trạng thái khi thread tranh chấp monitor hoặc chờ khóa. Bài tập trung vào cơ chế **Java SE/JVM**, bao gồm `synchronized`, `Object.wait/notify`, `ReentrantLock`, `Condition` và `LockSupport`; không đi vào concurrency riêng của Spring.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Diễn giải chính xác lúc nào một Java thread thường chuyển giữa `RUNNABLE`, `BLOCKED`, `WAITING` và `TIMED_WAITING`.
- Phân biệt **đợi lấy intrinsic monitor**, **đang đợi một điều kiện trên monitor**, và **đợi khóa tường minh** như `ReentrantLock`.
- Giải thích vì sao `notify()`, `notifyAll()` hoặc `signal()` **chưa có nghĩa** thread được đánh thức đã có thể chạy qua critical section.
- Viết đúng cấu trúc chờ điều kiện, xử lý `InterruptedException`, giải phóng khóa và tránh lost notification.
- Đọc thread dump/JFR theo cơ chế đồng bộ đang dùng, thay vì suy nguyên nhân từ riêng một nhãn `Thread.State`.

Điểm then chốt: **`BLOCKED` là một trạng thái cụ thể của `Thread.State` dành cho việc đợi *intrinsic monitor*; không phải mọi thread “đang bị chặn” bởi một khóa đều mang `BLOCKED`.**

## 2. Thread.State biểu diễn điều gì?

`Thread.getState()` trả về một trong sáu trạng thái của Java. Đây là trạng thái quan sát tại thời điểm lấy mẫu, **không** phải sơ đồ đầy đủ mọi trạng thái lập lịch nội bộ của hệ điều hành, và cũng không mô tả toàn bộ lý do một task chưa hoàn thành.

| Trạng thái | Định nghĩa đáng chú ý | Liên quan đến monitor/lock |
|---|---|---|
| `NEW` | Thread được tạo nhưng chưa `start()`. | Chưa tranh khóa. |
| `RUNNABLE` | Đang chạy hoặc sẵn sàng được chạy trong JVM; có thể còn chờ OS cấp CPU. | Thread có thể đang ở bên trong critical section hoặc chuẩn bị gọi lock. |
| `BLOCKED` | Đợi vào hoặc **vào lại** một intrinsic monitor. | Thường thấy ở `synchronized` và khi `Object.wait()` đã được đánh thức nhưng chưa lấy lại monitor. |
| `WAITING` | Đợi một hành động từ thread khác, không chỉ định timeout. | `Object.wait()` không timeout, `Condition.await()`, `LockSupport.park()`, một số đường đi của `ReentrantLock.lock()`. |
| `TIMED_WAITING` | Đợi trong thời hạn được chỉ định. | `Object.wait(timeout)`, `Condition.awaitNanos()`, `LockSupport.parkNanos()`; cả `Thread.sleep()` cũng ở đây. |
| `TERMINATED` | Hàm `run()` đã kết thúc. | Không còn tranh khóa. |

Một số lưu ý để không đọc sai:

- `RUNNABLE` **không chứng minh** thread đang chạy trên CPU vào thời điểm lấy mẫu.
- `WAITING` **không chứng minh** deadlock: executor worker có thể đang nhàn rỗi đợi queue, hoặc thread đang đợi một điều kiện hợp lệ.
- `BLOCKED` trong API này chỉ nói tới **monitor**, không gộp mọi kiểu I/O, thread pool, database connection hoặc khóa do thư viện tự xây.
- Thread có thể chuyển trạng thái nhanh hơn chu kỳ thu thập dữ liệu. Hai ảnh chụp liên tiếp có thể khác nhau mà không có lỗi.
- Java `Thread.State` không phải `Process State` của Linux/Windows; không suy trực tiếp số lần context switch, CPU time hay thời gian lock chờ từ một ảnh `getState()`.

## 3. Vào `synchronized`: `RUNNABLE → BLOCKED → RUNNABLE`

Một **intrinsic monitor** gắn với từng object Java, và cũng được dùng cho `static synchronized` thông qua đối tượng `Class` tương ứng. Khi một thread vào `synchronized (lock) { ... }`, nó cần **sở hữu monitor** của `lock`.

- Nếu monitor đang rảnh, thread có thể lấy nó và đi tiếp vào critical section mà không phải đi qua một khoảng `BLOCKED` quan sát được.
- Nếu monitor do thread khác nắm giữ, thread đang muốn vào sẽ ở `BLOCKED` trong mô hình trạng thái Java.
- Khi monitor được giải phóng, thread tranh chấp có **cơ hội** lấy lại monitor và tiếp tục `RUNNABLE`; không có bảo đảm thread nào giành được trước, cũng không có bảo đảm lập tức được CPU.
- `synchronized` là **reentrant**: thread đã sở hữu monitor đó có thể vào lồng nhau với cùng monitor mà không tự block chính nó.

Ví dụ:

```java
Object guard = new Object();

// Thread A
synchronized (guard) {
    doWork(); // A giữ guard trong lúc thực hiện
}

// Thread B chạy đồng thời:
synchronized (guard) {
    updateState(); // B phải đợi nếu A chưa nhả guard
}
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập vì `doWork()` và `updateState()` chỉ là tên giả định. Khi A còn giữ `guard`, B có thể ở `BLOCKED`. A thoát khỏi khối `synchronized` (kể cả khi exception làm stack unwinding) thì monitor được nhả. Thread B chỉ tiếp tục cập nhật sau khi nó thực sự vào được monitor.

**Monitor entrance không interruptible:** gọi `contender.interrupt()` không buộc một thread đang `BLOCKED` ở lối vào `synchronized` thoát khỏi chờ khóa và không khiến lệnh `synchronized` ném `InterruptedException`. Cờ interrupt vẫn có thể được đặt để code phía sau xử lý. Muốn một **lock acquisition** có thể hủy bằng interrupt, cân nhắc `ReentrantLock.lockInterruptibly()` khi yêu cầu thiết kế cho phép.

Về hiệu ứng bộ nhớ, việc **unlock** một monitor *happens-before* lần **lock** tiếp theo của cùng monitor. Nhờ đó, thread vào sau quan sát các ghi trước khi thread trước nhả monitor theo quy tắc Java Memory Model. Tuy nhiên, điều này không tự động bảo vệ dữ liệu nếu một luồng đọc/ghi bỏ qua cùng cơ chế đồng bộ.

## 4. `Object.wait()`: từ sở hữu monitor sang WAITING

`Object.wait()` khác hoàn toàn với việc chờ **để vào** `synchronized`.

1. Thread phải **đang sở hữu monitor** của đúng object mà nó gọi `wait()`. Nếu không, Java ném `IllegalMonitorStateException`.
2. `wait()` đưa thread vào wait set của monitor đó và **nhả monitor đó** (bao gồm các lần nắm monitor reentrant tương ứng) trong lúc đợi.
3. Với `wait()` không timeout, thread thường được quan sát là `WAITING`. Với `wait(long timeoutMillis)` (timeout dương), là `TIMED_WAITING`.
4. Một lý do giúp rời wait set có thể là `notify()`, `notifyAll()`, interrupt, timeout (nếu có), hoặc **spurious wakeup**.
5. Trước khi `wait()` thực sự trả về hoặc ném `InterruptedException`, thread phải **lấy lại monitor** của object đó. Nếu monitor còn do thread khác giữ, thread có thể chuyển sang `BLOCKED` khi chờ vào lại.
6. Chỉ sau khi vào lại thành công, thread mới tiếp tục kiểm tra điều kiện và chạy code trong khối `synchronized`.

Luồng thường gặp:

```text
RUNNABLE (đang giữ monitor)
    |
    | gọi Object.wait(), nhả monitor của object đó
    v
WAITING hoặc TIMED_WAITING
    |
    | notify/notifyAll, interrupt, timeout hoặc spurious wakeup
    v
BLOCKED (nếu đang chờ lấy lại monitor)
    |
    | lấy được monitor
    v
RUNNABLE (tiếp tục trong synchronized)
```

Sơ đồ là **một chuỗi chuyển trạng thái điển hình**, không phải khẳng định mọi lần chạy đều quan sát đủ từng trạng thái. Nếu monitor có thể lấy lại ngay, pha `BLOCKED` rất ngắn hoặc không nhìn thấy ở ảnh chụp.

### Tại sao notify chưa phải là tiếp tục chạy?

Xét:

```java
synchronized (guard) {
    available = true;
    guard.notifyAll();
    // Thread vừa được notify vẫn chưa thể thực thi
    // bên trong synchronized(guard) cho tới khi monitor được nhả.
    performMoreWork();
}
```

Đây là **đoạn minh họa đặt bên trong method**; `guard`, `available` và `performMoreWork()` là các thành phần đã được khai báo trong ngữ cảnh giả định. `notifyAll()` làm các waiter đủ điều kiện tranh lấy monitor, nhưng **không tự nhả monitor**. Thread gọi `notifyAll()` vẫn giữ monitor cho tới khi thoát vùng đồng bộ. Vì vậy, kéo dài `performMoreWork()` ngay sau thông báo có thể tăng thời gian các waiter chờ lấy lại khóa.

- `notify()` chọn **một** waiter từ wait set tương ứng, không cam kết chọn “cũ nhất” hay bất kỳ thứ tự công bằng nào.
- `notifyAll()` đánh thức các waiter trong wait set, nhưng họ vẫn phải lần lượt tranh monitor.
- Không phải waiter nào cũng đủ điều kiện xử lý dữ liệu sau khi tỉnh dậy: thông báo không biến điều kiện nghiệp vụ thành đúng cho mọi thread.

### Luôn đợi theo điều kiện (predicate) trong vòng lặp

Mẫu đúng:

```java
private final Object guard = new Object();
private boolean available;

// Producer:
void publish() {
    synchronized (guard) {
        available = true;  // thay đổi predicate trước
        guard.notifyAll(); // thông báo khi đang giữ monitor
    }
}

// Consumer:
void awaitAvailable() throws InterruptedException {
    synchronized (guard) {
        while (!available) {
            guard.wait();
        }
        // available == true và hiện đang giữ guard
    }
}
```

Đây là các method minh họa của **cùng một class**, không phải tệp Java độc lập. Cả ghi `available`, kiểm tra `available` và `wait/notify` đều diễn ra dưới **cùng monitor**, nên không cần `volatile` riêng cho biến này trong mô hình đó.

**Vì sao `while` chứ không phải `if`?** Có thể tỉnh dậy giả (spurious wakeup), nhiều consumer cùng được đánh thức nhưng chỉ một consumer giành được dữ liệu, hoặc điều kiện đã thay đổi trong lúc chờ lấy lại monitor. Thread phải **kiểm tra lại predicate** sau mỗi lần thức dậy.

**Tránh lost notification:** đừng tách thao tác kiểm tra điều kiện khỏi thao tác vào wait set. Nếu một thread kiểm tra điều kiện không đồng bộ rồi mới gọi `wait()`, một `notify` có thể xảy ra ở giữa và bị bỏ lỡ. Predicate được cập nhật và kiểm tra dưới cùng khóa giải quyết trường hợp này: nếu điều kiện đã đúng, thread không gọi `wait`.

`wait()` **chỉ nhả monitor của object được gọi**. Nếu thread đang giữ thêm một monitor khác khi gọi `guard.wait()`, các monitor khác **không tự được nhả**; điều này có thể tạo deadlock hoặc giữ khóa quá lâu. `Thread.sleep()` cũng **không nhả các monitor đang giữ**; ngủ không phải thay thế cho `wait()`.

### Interrupt trong Object.wait

Khi một thread bị interrupt trong lúc `Object.wait()`, `wait()` sẽ ném `InterruptedException` sau khi đã lấy lại monitor theo hợp đồng API; **interrupt status được xóa** khi exception được ném. Việc xử lý nên hoặc truyền exception lên caller, hoặc thoát có kiểm soát và khôi phục interrupt flag:

```java
try {
    guard.wait();  // chỉ gọi khi đã sở hữu monitor guard
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return; // nếu đang ở method void và quyết định hủy công việc
}
```

Đây là **đoạn minh họa trong một method `void` nằm trong `synchronized(guard)`**, không phải chương trình độc lập. Không nuốt interrupt bằng một `catch` trống rồi tiếp tục đợi vô hạn.

## 5. `ReentrantLock`: chờ lock không đồng nghĩa Java BLOCKED

`ReentrantLock` thuộc `java.util.concurrent.locks`. Đây là **explicit lock**, không phải intrinsic monitor do `synchronized` dùng. Khi gọi `lock()` mà khóa chưa khả dụng, triển khai đồng bộ thường dựa trên AQS và có thể dùng `LockSupport.park()` để cho thread chờ. Khi đang được park, thread thường thể hiện `WAITING` (hoặc `TIMED_WAITING` cho cơ chế chờ có timeout). Trong những đoạn thử giành khóa ngắn, nó cũng có thể là `RUNNABLE`. **Không mặc định trạng thái `BLOCKED` cho `ReentrantLock.lock()`.**

Ví dụ mẫu:

```java
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    // Đọc/ghi dữ liệu được bảo vệ bởi lock.
} finally {
    lock.unlock();
}
```

Đây là **đoạn mã trong một method** cần import `java.util.concurrent.locks.ReentrantLock`. `unlock()` phải nằm trong `finally`; nếu công việc ném exception mà không unlock, các thread khác có thể kẹt. Chỉ thread sở hữu mới được `unlock()`; gọi sai gây `IllegalMonitorStateException`.

Khác biệt quan trọng về chờ hủy được:

| Cơ chế | Có thể dừng **đang chờ lấy khóa** bằng interrupt? | Ghi chú |
|---|---|---|
| `synchronized` enter | **Không** | `interrupt()` không làm `synchronized` tự ném exception. |
| `ReentrantLock.lock()` | **Không theo API này** | Giành khóa theo cách mặc định; không phải acquisition có thể hủy. |
| `ReentrantLock.lockInterruptibly()` | **Có** | Có thể ném `InterruptedException` trong lúc đợi lock; caller phải xử lý. |
| `ReentrantLock.tryLock()` | Trả kết quả ngay | Không phải đường chờ; trả `false` nếu khóa chưa lấy được. |
| `ReentrantLock.tryLock(timeout, unit)` | **Có** | Có thể timeout hoặc ném `InterruptedException`. |

Khi viết `lockInterruptibly()`, chỉ vào `finally { unlock(); }` **sau khi khóa được lấy thành công**:

```java
lock.lockInterruptibly(); // có thể ném trước khi sở hữu lock
try {
    // critical section
} finally {
    lock.unlock();
}
```

Đây là **đoạn minh họa trong một method khai báo `throws InterruptedException`**. Một exception xuất phát từ lúc đợi sẽ không đi vào `try/finally` trên, nên không vô tình unlock khóa mình chưa giữ.

### `Condition.await()`: đợi điều kiện trên explicit lock

`Condition` đi cùng một `Lock`, về ý tưởng tương tự việc chờ một predicate dưới monitor nhưng **không dùng** `Object.wait()`:

```java
// Các trường của một class:
private final ReentrantLock lock = new ReentrantLock();
private final Condition changed = lock.newCondition();
private boolean available;

void publish() {
    lock.lock();
    try {
        available = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}

void awaitAvailable() throws InterruptedException {
    lock.lock();
    try {
        while (!available) {
            changed.await();
        }
    } finally {
        lock.unlock();
    }
}
```

Đây là **đoạn mã thành viên của một class**; cần import `ReentrantLock` và `Condition` từ `java.util.concurrent.locks`. `await()` **nhả explicit lock tương ứng** trong khi đợi, rồi **lấy lại khóa trước khi trả về**; nó không nhả những khóa khác mà thread đồng thời giữ. `signal()/signalAll()` yêu cầu sở hữu khóa với `Condition` của `ReentrantLock` này. Cũng như monitor, signal **không tự chuyển quyền sở hữu**: waiter phải tranh lấy lại khóa, và luôn lặp `while` để kiểm tra predicate.

`Condition.await()`/`awaitNanos()` có thể bị interrupt; hàm chờ trả hoặc ném sau khi lấy lại lock theo hợp đồng của `Condition`/`ReentrantLock`. Tùy API chờ và tình huống, signal, timeout, interrupt hoặc thức dậy giả có thể làm vòng đợi kết thúc, nên predicate mới là nguồn chân lý của công việc.

### `LockSupport.park()/unpark()`: chờ ở tầng thấp hơn

`LockSupport.park()` có thể đặt thread vào `WAITING`, `parkNanos()` vào `TIMED_WAITING`. `unpark(thread)` cung cấp một permit để thread đó có thể đi tiếp; permit **không cộng dồn thành hàng đợi vô hạn**. `park()` có thể trả về khi bị interrupt hoặc vì spurious return; vì vậy bộ đồng bộ viết trên `LockSupport` cũng cần kiểm tra điều kiện trong vòng lặp.

**`park()` tự nó không nhả monitor hay `ReentrantLock` nào thread đang giữ.** Đây là điểm khác với `Object.wait()` và `Condition.await()`: các API await cao cấp chỉ nhả đúng lock tương ứng theo quy ước của chúng. Dùng park tùy tiện khi vẫn giữ khóa người khác cần có thể gây deadlock.

`Thread.interrupt()` có thể làm `park()` trở về, nhưng `park()` **không ném `InterruptedException`** và cũng không tự xóa interrupt status. Muốn kiểm tra mà không xóa cờ, dùng `Thread.currentThread().isInterrupted()`; `Thread.interrupted()` là phương thức static kiểm tra **và xóa** cờ của thread đang chạy.

## 6. Thực hành chạy được trên Java 17+

Ví dụ **`MonitorLockTransitions.java`** có ba phần. Hai phần đầu dùng `CountDownLatch` để sắp xếp thời điểm trước khi quan sát trạng thái: thread tranh intrinsic monitor được giữ ở `BLOCKED`; thread chờ `Object.wait()` được quan sát `WAITING` rồi `BLOCKED` khi được thông báo nhưng chưa lấy lại monitor. Phần ba cho thấy giành `ReentrantLock` và giải phóng bằng `finally`, **không giả định một trạng thái cố định** cho explicit lock.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class MonitorLockTransitions {
    private static Thread.State awaitState(
            Thread thread, Thread.State expected) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            Thread.State current = thread.getState();
            if (current == expected) return current;
            Thread.sleep(1);
        }
        throw new IllegalStateException("Cannot observe " + expected);
    }

    private static void monitorEntry() throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch aboutToEnter = new CountDownLatch(1);
        Thread contender = new Thread(() -> {
            aboutToEnter.countDown();
            synchronized (monitor) {
                System.out.println("2. contender entered monitor");
            }
        }, "monitor-contender");

        synchronized (monitor) {
            contender.start();
            aboutToEnter.await();
            System.out.println("1. contender state: " +
                    awaitState(contender, Thread.State.BLOCKED));
        }
        contender.join();
    }

    private static void monitorWait() throws InterruptedException {
        Object monitor = new Object();
        boolean[] ready = {false};
        CountDownLatch entered = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            synchronized (monitor) {
                entered.countDown();
                while (!ready[0]) {
                    try {
                        monitor.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("5. waiter resumed with monitor");
            }
        }, "monitor-waiter");

        waiter.start();
        entered.await();
        System.out.println("3. waiter state before notify: " +
                awaitState(waiter, Thread.State.WAITING));
        synchronized (monitor) {
            ready[0] = true;
            monitor.notifyAll();
            System.out.println("4. waiter state after notify, before unlock: " +
                    awaitState(waiter, Thread.State.BLOCKED));
        }
        waiter.join();
    }

    private static void explicitLock() throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch aboutToLock = new CountDownLatch(1);
        Thread contender = new Thread(() -> {
            aboutToLock.countDown();
            lock.lock();
            try {
                System.out.println("7. explicit lock acquired");
            } finally {
                lock.unlock();
            }
        }, "lock-contender");

        lock.lock();
        try {
            contender.start();
            aboutToLock.await();
            System.out.println("6. main still holds explicit lock");
        } finally {
            lock.unlock();
        }
        contender.join();
    }

    public static void main(String[] args) throws InterruptedException {
        monitorEntry();
        monitorWait();
        explicitLock();
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac --release 17 MonitorLockTransitions.java
java MonitorLockTransitions
```

Kết quả trong lần chạy đã xác minh trên OpenJDK (và là thứ tự được điều khiển bởi monitor/latch trong chương trình này):

```text
1. contender state: BLOCKED
2. contender entered monitor
3. waiter state before notify: WAITING
4. waiter state after notify, before unlock: BLOCKED
5. waiter resumed with monitor
6. main still holds explicit lock
7. explicit lock acquired
```

**Giải thích từng điểm quan sát:**

1. `main` giữ monitor và thread `contender` định vào: trạng thái `BLOCKED` được giữ ổn định cho đến khi `main` rời `synchronized`.
2. Khi `main` nhả monitor, `contender` lấy được nó rồi in dòng 2; `join()` bảo đảm phần này kết thúc trước phần tiếp theo.
3. `waiter` có được monitor rồi gọi `wait()`, nhả monitor và ở `WAITING`.
4. `main` giành monitor, đặt `ready=true` và gọi `notifyAll()` nhưng vẫn giữ monitor. `waiter` đã được thông báo song còn đợi **reacquire**, nên quan sát được `BLOCKED`.
5. Sau khi `main` rời monitor, `waiter` vào lại, kiểm tra `ready` và tiếp tục.
6. Với explicit lock, `main` giữ `ReentrantLock` trong khi contender cố lấy khóa. Dòng 6 không suy đoán state là `BLOCKED`.
7. Sau `unlock()`, contender lấy explicit lock và in dòng 7.

`awaitState()` chỉ dùng để **lấy mẫu trạng thái trong bài thực hành**, không phải giao thức đồng bộ cho nghiệp vụ. Nó polling mỗi 1 ms và có deadline 5 giây để tránh treo vô hạn khi quan sát trạng thái gặp vấn đề. Trong môi trường cực chậm hoặc không được cấp CPU, ví dụ có thể ném `IllegalStateException` vì không quan sát trạng thái kịp thời; không có cam kết về deadline của scheduler. Không dùng polling `getState()` để quyết định khi nào được vào critical section trong sản phẩm thật.

**Lưu ý về sự đúng đắn:** `ready` ở ví dụ là mảng `boolean[]` chỉ để biến local được lambda truy cập; nó được đọc/ghi **dưới cùng monitor** nên không cần `volatile`. Mốc `entered.countDown()` nằm bên trong `synchronized`, còn `main` đọc trạng thái `WAITING` trước khi thông báo. Đây là phối hợp thí nghiệm; ứng dụng thực thường dùng `BlockingQueue`, `CountDownLatch` hoặc `Condition` thay vì tự viết vòng chờ mức thấp khi primitive có sẵn đáp ứng đúng ý định.

## 7. So sánh nhanh các hành vi chờ

| Thao tác | Phải giữ monitor/lock trước khi gọi? | Có nhả khóa trong lúc đợi? | Trạng thái thường quan sát |
|---|---|---|---|
| Vào `synchronized(obj)` khi obj bị giữ | Không, đang cố lấy | Chưa sở hữu khóa này | `BLOCKED` |
| `obj.wait()` | Phải giữ monitor `obj` | **Có**, monitor `obj`; sau đó reacquire | `WAITING` → có thể `BLOCKED` |
| `obj.wait(t>0)` | Phải giữ monitor `obj` | **Có**, monitor `obj` | `TIMED_WAITING` → có thể `BLOCKED` |
| `obj.notify()/notifyAll()` | Phải giữ monitor `obj` | **Không** | Caller tiếp tục chạy; waiter phải reacquire |
| `Thread.sleep(t)` | Không | **Không** nhả khóa đang giữ | `TIMED_WAITING` |
| `ReentrantLock.lock()` khi đang bận | Không | Chưa sở hữu khóa mới | Thường `WAITING` khi park; có thể `RUNNABLE` |
| `Condition.await()` | Phải sở hữu lock liên quan | **Có**, lock liên quan; sau đó reacquire | Thường `WAITING` |
| `Condition.awaitNanos(t)` | Phải sở hữu lock liên quan | **Có**, lock liên quan | Thường `TIMED_WAITING` |
| `LockSupport.park()` | Không | **Không** tự nhả khóa | `WAITING` |
| `LockSupport.parkNanos(t)` | Không | **Không** tự nhả khóa | `TIMED_WAITING` |

Các ô “thường quan sát” mô tả kết quả điển hình ở một thời điểm. **Không** coi bảng là lịch trình bắt buộc hoặc số lần chuyển trạng thái phải xuất hiện. Đặc biệt, sau khi một waiter rời hàng đợi điều kiện, nó vẫn phải đợi scheduler cấp CPU và có thể phải cạnh tranh để lấy lại khóa.

## 8. Deadlock, starvation và blocked không cùng nghĩa

### Deadlock

Giả sử thread A giữ monitor `left` và đợi monitor `right`, trong khi thread B giữ `right` và đợi `left`. Cả hai có thể ở `BLOCKED` vĩnh viễn vì vòng phụ thuộc. Với `ReentrantLock` và các tài nguyên khác, vòng đợi có thể biểu hiện dưới `WAITING` thay vì `BLOCKED`. Deadlock là **vòng phụ thuộc không thể tiến triển**, không phải một nhãn trạng thái.

Biện pháp hữu ích: quy định thứ tự lấy nhiều khóa nhất quán; giảm khóa lồng nhau; dùng timeout khi được phép và có chiến lược rollback; không gọi I/O chậm khi đang giữ monitor nếu có thể bố trí an toàn bên ngoài.

### Starvation

Một thread lâu không được lấy khóa dù các thread khác vẫn tiến triển, do phân phối CPU, cạnh tranh quá cao, hoặc chính sách chọn waiter. Nó có thể đổi trạng thái liên tục, không nhất thiết deadlock. `synchronized` không bảo đảm FIFO. `ReentrantLock(true)` cung cấp chính sách fairness cho acquisition dưới cạnh tranh ở mức API, nhưng không bảo đảm lịch CPU tuyệt đối và thường có đánh đổi throughput; `tryLock()` không thời hạn còn có hành vi barging cần lưu ý. Dùng số liệu chờ và SLA để quyết định, không chỉ bật fairness.

### Waiting hợp lệ

Một thread đang `WAITING` trong `BlockingQueue.take()` khi queue trống có thể chỉ đang nhàn rỗi đúng thiết kế. `Object.wait()` trong producer-consumer cũng có thể là hành vi chính xác. Muốn đánh giá lỗi, cần biết predicate nào chưa đúng, ai chịu trách nhiệm thay đổi predicate, có lệnh signal hay không và công việc có thực sự tiến triển.

## 9. Cách chẩn đoán trong chương trình thực

**Bước 1 — Nhìn đúng thời điểm và đúng thread.** Khi process đang sống, lấy một vài thread dump cách nhau:

```bash
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng process ID thực tế. Tùy JDK/OS, công cụ có thể cần quyền truy cập hoặc môi trường hỗ trợ attach.

**Bước 2 — Đọc trạng thái cùng stack:**

- `BLOCKED (on object monitor)` và dòng “waiting to lock” trỏ về monitor là tín hiệu cần tìm owner, critical section và đường lấy monitor.
- `WAITING (on object monitor)` đi với `Object.wait` gợi ý đợi predicate trên monitor; tìm logic `notify/notifyAll` và predicate.
- `WAITING (parking)` với `LockSupport.park`/AQS gợi ý explicit lock, condition, queue hoặc synchronizer khác; phải đọc stack để phân biệt.
- `TIMED_WAITING (sleeping)` là ngủ có thời hạn; **không** kết luận monitor đang được nhả.

**Bước 3 — Đối chiếu với dữ liệu theo thời gian.** Thread dump có thể bỏ lỡ lock contention rất ngắn. Dùng Java Flight Recorder để xem sự kiện `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, thời lượng, ngưỡng sự kiện, thread và stack trace khi môi trường hỗ trợ:

```bash
jcmd <PID> JFR.start name=lock-check settings=profile duration=60s filename=locks.jfr
jfr summary locks.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark locks.jfr
```

Môi trường phải có hỗ trợ JFR; các event có thể không được bật hoặc bị lọc theo duration/threshold, nên **không thấy event không chứng minh không có contention**. Một file recording chỉ có ý nghĩa khi workload đang tái hiện vấn đề trong khoảng ghi. Với chương trình demo chạy cực nhanh, có thể không kịp ghi lại sự kiện hữu ích.

**Bước 4 — Đo nguyên nhân, không đoán.** Xem lock owner, wait duration, số thread cùng tranh, độ dài critical section, thời gian làm I/O và các công việc đang đợi trong queue. Phân biệt CPU starvation, lock contention, chờ I/O và thread pool saturation; hướng tối ưu sẽ khác nhau.

### Java 21+ và virtual threads (lưu ý phạm vi)

Virtual threads không phải mỗi thread Java đều gắn vĩnh viễn với một OS thread. Các thao tác blocking được hỗ trợ có thể **unmount** virtual thread khỏi carrier; vì vậy không nên lấy số lượng platform threads và quy luật OS scheduling để áp nguyên xi vào mọi phép đo virtual thread. Tuy nhiên, monitor, điều kiện, lock ownership, interruption và invariants vẫn quan trọng. Ví dụ thực hành bên trên chủ đích dùng API phổ biến từ **Java 17+** và tạo **platform threads** để nghiên cứu `Thread.State` dễ quan sát.

## 10. Sai lầm thường gặp và cách sửa

1. **“Thread đợi `ReentrantLock` chắc chắn là `BLOCKED`.”** Nhầm intrinsic monitor với explicit lock. Xem call stack; AQS/park thường hiện `WAITING` hoặc `TIMED_WAITING`.
2. **“`notify()` khiến waiter chạy ngay.”** Nó chỉ chuyển waiter tới cơ hội tranh lại monitor; caller vẫn giữ monitor cho đến khi unlock.
3. **“Gọi `wait()` ở ngoài `synchronized` vẫn được.”** Sẽ ném `IllegalMonitorStateException` nếu không sở hữu đúng monitor.
4. **“`wait()` nhả hết mọi khóa.”** Chỉ nhả monitor của object được gọi; giữ những monitor khác có thể tạo vòng đợi.
5. **“`sleep()` giải phóng lock cho thread khác.”** Không. Nếu đang giữ monitor/explicit lock, thời gian ngủ vẫn giữ khóa đó.
6. **“Có notify rồi thì dùng `if` là đủ.”** Có thể spurious wakeup hoặc điều kiện bị thread khác đổi; dùng `while (!predicate) wait()`.
7. **“Chỉ cần thấy `WAITING` là tìm được deadlock.”** Cần wait graph, owner, stack và bằng chứng không tiến triển; chờ hợp lệ rất phổ biến.
8. **“`interrupt()` sẽ hủy mọi lần lấy khóa.”** Không áp dụng cho monitor entrance hay `ReentrantLock.lock()`; cần `lockInterruptibly()` hoặc `tryLock(timeout, unit)` để kiểm soát việc chờ bằng API phù hợp.
9. **“Lock được nhả khi `notifyAll()`/`signalAll()`.”** Không. Nhả khóa khi thoát `synchronized` hoặc `unlock()` đúng cách.
10. **“`Thread.getState()` có thể thay điều kiện đồng bộ.”** Không. Đây là công cụ quan sát; dùng lock, condition, latch, queue và predicate cho correctness.

## 11. Tự kiểm tra kiến thức

**Câu 1.** A giữ monitor `m`, B đang cố vào `synchronized(m)`. B thường ở trạng thái nào?  
**Đáp án:** `BLOCKED`. B chưa vào critical section, phải đợi monitor `m`.

**Câu 2.** B đang `m.wait()` (không timeout), A lấy được `m` và gọi `m.notifyAll()` nhưng vẫn giữ `m` thêm vài giây. B có thể quan sát trạng thái nào trong thời gian đó?  
**Đáp án:** B rời `WAITING`; khi chờ lấy lại monitor `m` sẽ ở `BLOCKED`. B không thể tiếp tục bên trong synchronized trước khi giành lại `m`.

**Câu 3.** Một thread chờ `ReentrantLock.lock()` xuất hiện `WAITING (parking)` trong dump. Điều này có mâu thuẫn với khái niệm “chờ khóa” không?  
**Đáp án:** Không. `Thread.State.BLOCKED` mô tả chờ intrinsic monitor; explicit lock có đường chờ dựa trên `park`.

**Câu 4.** Vì sao dùng `while (!ready) guard.wait()` tốt hơn `if (!ready) guard.wait()`?  
**Đáp án:** Phải kiểm tra lại predicate sau spurious wakeup, sau cạnh tranh với waiter khác, và khi trạng thái nghiệp vụ có thể thay đổi trong lúc thread reacquire monitor.

**Câu 5.** Thread đang giữ `a` và `b`, rồi gọi `a.wait()`. Khóa nào được nhả trong lúc chờ?  
**Đáp án:** Monitor `a` được nhả trong `wait()`; monitor `b` **không tự nhả**.

**Câu 6.** Đang `BLOCKED` vì monitor thì `interrupt()` có làm `synchronized` ném `InterruptedException` không?  
**Đáp án:** Không. Lối vào monitor không interruptible; nếu cần acquisition có khả năng hủy, thiết kế với `lockInterruptibly()` hoặc timed `tryLock` có kiểm soát.

## Tài liệu tham khảo

- [Java SE 17 — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): định nghĩa chính thức sáu trạng thái.
- [Java SE 17 — Object.wait/notify](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): sở hữu monitor, wait set, notify và reacquire.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): các kiểu acquisition, fairness, unlock.
- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): semantics của await/signal và predicate.
- [Java SE 17 — LockSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): park/unpark và permit.
- [Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): hỗ trợ quan sát thread và contention.

**Ghi nhớ:** khi nhìn một thread “đang chờ khóa”, câu hỏi đầu tiên là **nó đang chờ *monitor entry*, đang đợi một *điều kiện*, hay đang chờ một *explicit lock*?** Chỉ sau khi biết cơ chế đó mới giải thích đúng trạng thái, việc nhả/lấy lại khóa và cách xử lý an toàn.