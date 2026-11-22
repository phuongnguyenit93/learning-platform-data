# 9.4 Chẩn đoán synchronized, ReentrantLock, Condition, Object.wait và LockSupport.park

Một ứng dụng Java có thể **vẫn chạy, CPU thấp, không xuất exception nhưng mọi request mới đều timeout**. Trong trường hợp đó, phần khó không phải tìm “có bao nhiêu thread WAITING”, mà là lần theo quan hệ: **thread nào đang giữ tài nguyên**, **thread nào đang chờ để lấy khóa**, **thread nào chờ một điều kiện được báo**, **ai sẽ báo điều kiện** và **điều gì ngăn bước tiếp theo xảy ra**.

Năm API/cơ chế thường xuất hiện trên thread dump liên quan trực tiếp câu hỏi này:

1. `synchronized` — monitor lock nội tại của một Java object.
2. `ReentrantLock` — khóa độc quyền có reentrancy, lựa chọn try/timed/interruptible acquisition và khả năng quan sát queue.
3. `Condition` — hàng chờ điều kiện gắn với một `Lock`, thường là `ReentrantLock`.
4. `Object.wait()` / `notify()` / `notifyAll()` — wait-set trên object monitor, chỉ dùng khi sở hữu monitor.
5. `LockSupport.park()` / `unpark()` — primitive cấp thấp dùng một permit trên mỗi thread, được nhiều cơ chế AQS/pool/condition triển khai ở bên dưới.

**Các cơ chế trên không tương đương.** `synchronized` và `ReentrantLock` điều khiển **mutual exclusion**. `Object.wait` và `Condition.await` dùng để **chờ một điều kiện logic** và *tạm nhả đúng khóa liên quan* khi chờ. `LockSupport.park` chỉ ngừng lập lịch thread cho tới khi có permit, interrupt hoặc spurious wakeup: bản thân nó **không nhả monitor/ReentrantLock đang giữ**, cũng không biết predicate nghiệp vụ.

Bài học tập trung vào **chẩn đoán treo và tranh chấp**, không chỉ vào cách dùng cú pháp. Các ví dụ dùng Java 17+ và tài liệu Java SE 21; thread state, định dạng dump và độ đầy đủ của dữ liệu phụ thuộc JDK/JVM/OS/công cụ, đặc biệt trong môi trường virtual threads.

## 1. Bảng so sánh năm cơ chế trước khi xem thread dump

| Cơ chế | Đối tượng đồng bộ chính | Làm gì khi chờ? | Lock có được nhả khi chờ? | Dấu hiệu thường gặp |
| --- | --- | --- | --- | --- |
| `synchronized(lock)` | Monitor của `lock` | Chờ được vào monitor nếu bị giữ | **Không**, chỉ vào khi lấy được; owner nhả lúc thoát synchronized hoặc thực hiện `wait` trên chính monitor | Contender: `BLOCKED (on object monitor)`, `waiting to lock` |
| `ReentrantLock.lock()` | Ownable synchronizer/AQS của lock | Chờ owner gọi `unlock` | Waiter chưa có lock; owner vẫn giữ tới khi `unlock` | `WAITING/TIMED_WAITING (parking)` và `ReentrantLock$...Sync` |
| `Condition.await()` | Condition và `Lock` gắn kèm | Chờ signal/interrupt/timeout/spurious | **Có**, nhả associated lock rồi reacquire trước khi trả về bình thường hoặc throw theo contract | `WAITING/TIMED_WAITING (parking)` trên `ConditionObject` |
| `Object.wait()` | Wait-set của object monitor | Chờ notify/interrupt/timeout/spurious | **Có**, nhả monitor của **đúng object được wait**, rồi reacquire trước khi trở về | `WAITING/TIMED_WAITING (on object monitor)`, `waiting on` |
| `LockSupport.park()` | Permit của từng thread; blocker object tùy chọn | Chờ `unpark`/interrupt/spurious/timeout | **Không tự nhả** bất cứ monitor hoặc `ReentrantLock` nào | `WAITING/TIMED_WAITING (parking)`, `parking to wait for` nếu có blocker |

*Chú giải:* state là ảnh chụp. `Condition.await()`, `ReentrantLock.lock()` và `LockSupport.park()` có thể cùng hiện `WAITING (parking)`, nhưng **lý do chờ khác nhau**. Phải đọc stack frame và blocker class thay vì gộp thành “thread ngủ”.

### 1.1 Hai loại chờ cần phân biệt ngay

**Chờ khóa để vào critical section**:

- `synchronized`: contender chưa lấy monitor, thường `BLOCKED`.
- `ReentrantLock.lock()`: contender chưa lấy ownable lock, thường park trong AQS.
- Muốn chẩn đoán: **tìm owner** và đo tại sao owner giữ lâu.

**Chờ điều kiện trong khi phối hợp trạng thái**:

- `Object.wait()`: waiter đã vào monitor rồi **nhả monitor đó** khi đợi.
- `Condition.await()`: waiter đã lấy associated `Lock` rồi **nhả khóa** để đợi.
- `LockSupport.park()`: không có quy tắc tự nhả khóa; phải xem code.
- Muốn chẩn đoán: **tìm predicate và bên phát signal/notify/unpark**, kiểm tra vòng đời và happens-before.

Nhầm hai nhóm dẫn đến giải pháp sai: “tăng thread pool” không phá được deadlock, “notifyAll” không giải quyết monitor owner đang bị kẹt I/O, và “unlock” từ thread khác không phải cách sửa `ReentrantLock`.

## 2. Chẩn đoán synchronized: monitor owner và BLOCKED contender

### 2.1 Monitor được lấy ở đâu?

`synchronized` có thể bao một block:

```java
private final Object monitor = new Object();

void update() {
    synchronized (monitor) {
        // Critical section: chỉ một thread giữ monitor này tại một lúc.
        updateSharedState();
    }
}
```

Hoặc một instance method `synchronized` (monitor chính là `this`) hay static synchronized method (monitor là `Class` object của lớp đó). Hai đoạn trên là **code minh họa**, không phải Java file độc lập.

Java monitor là reentrant: thread đã giữ monitor có thể lại vào synchronized trên cùng monitor, tăng độ sâu sở hữu; rời từng cấp tương ứng nhả độ sâu, monitor cuối cùng được nhả khi thoát toàn bộ phần synchronized. Việc ném exception cũng đưa control flow rời synchronized theo semantics của Java, không phải yêu cầu manual unlock.

### 2.2 Khi tranh chấp, đọc cả waiter lẫn owner

Một thread dump **giả định**:

```text
"request-7" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at demo.OrderService.commit(OrderService.java:74)
    - waiting to lock <0x0000000711101000> (a java.lang.Object)

"request-2" ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at demo.OrderService.commit(OrderService.java:79)
    - locked <0x0000000711101000> (a java.lang.Object)
```

Trong **cùng dump**, ID `<0x0000000711101000>` liên kết người chờ với chủ khóa: `request-2` đang giữ monitor, `request-7` muốn vào. Nhưng `request-2` đang sleep trong critical section; `sleep` **không nhả monitor**. Đây là mẫu **long critical section/lock contention**, **chưa tự động là deadlock** nếu owner có thể thức dậy và nhả monitor.

Đừng kết luận thread owner phải là `RUNNABLE`: owner có thể ở `WAITING`, `TIMED_WAITING` hoặc đang gọi native I/O trong khi giữ khóa. Cần tìm **mọi held lock markers** và xem stack owner.

### 2.3 Đọc marker đúng chiều

| Dòng/field | Ý nghĩa | Sai lầm |
| --- | --- | --- |
| `- waiting to lock <L>` | Thread **chưa có** monitor L; đang cố vào | Gọi thread là owner |
| `- locked <L>` | Thread **đang giữ** monitor L | Gọi nó là waiter trên L |
| `getLockInfo()` khi `BLOCKED` | Monitor object contender đang chờ | Nhầm với tất cả locks thread giữ |
| `getLockOwnerId()` | Owner Java thread ID nếu JVM biết | Dùng như OS PID/nid |
| `getLockedMonitors()` | Monitors được chụp là held, nếu yêu cầu capture | Mảng rỗng luôn chứng minh không có lock |
| `getBlockedTime()` | Accumulated monitor contention time khi được bật/hỗ trợ | Chính xác thời gian của blocking event hiện tại |

Nếu có 50 threads cùng chờ một monitor ID, đó có thể là **lock convoy** sau một owner chậm, không nhất thiết 50 deadlocks riêng biệt.

### 2.4 Những cách vô tình giữ monitor quá lâu

- Gọi API mạng/DB hoặc RPC trong synchronized.
- Chạy thuật toán CPU nặng khi giữ mutex.
- Chờ `CountDownLatch.await()`, `Thread.sleep()` hoặc `LockSupport.park()` bên trong synchronized.
- Gọi callback/plugin code không rõ độ trễ trong critical section.
- Bật logging I/O đồng bộ hoặc gọi exporter chậm trong monitor.
- Có hai locks được lấy khác thứ tự giữa các code paths.

Khắc phục phải bảo toàn invariant: chỉ chuyển I/O ra ngoài lock khi dữ liệu được snapshot đúng và không tạo race. Không loại bỏ synchronized chỉ vì thấy nhiều `BLOCKED`.

## 3. Chẩn đoán ReentrantLock: ownership, AQS và khả năng timeout

### 3.1 ReentrantLock khác monitor ở điểm nào?

`ReentrantLock` cung cấp mutual exclusion có reentrancy như synchronized nhưng thêm `tryLock()`, `tryLock(timeout, unit)`, `lockInterruptibly()`, `isHeldByCurrentThread()`, `getHoldCount()` và instrumentation về queue. Cú pháp đúng:

```java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa trong một class có biến `lock`. **Đặt `try` ngay sau `lock()` thành công**, không đặt `unlock()` bên ngoài finally hay gọi khi không sở hữu. Nếu thread khác cố `unlock()` một `ReentrantLock` mà nó không giữ, `IllegalMonitorStateException` có thể xảy ra.

### 3.2 Vì sao ReentrantLock waiter thường WAITING, không BLOCKED?

HotSpot implementation dựa trên AQS có thể dùng `LockSupport.park(...)` khi lock bị tranh chấp. Contender sẽ thường được chụp là:

```text
"worker-lock-waiter" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
    - parking to wait for <0x0000000711202000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

**Không lọc duy nhất `BLOCKED` để tìm lock contention.** Với `ReentrantLock`, tìm AQS/`ReentrantLock.lock` stack và blocker object; owner có thể được liệt kê ở mục `Locked ownable synchronizers` trên một thread khác. Bản dump mô phỏng chỉ để giải thích; phương thức/frame/class có thể khác theo JDK release và fairness mode.

### 3.3 Instrumentation trên ReentrantLock mang tính snapshot/ước lượng

| API | Câu trả lời | Hạn chế |
| --- | --- | --- |
| `isLocked()` | Lock có đang được thread nào giữ ở snapshot không? | Kết quả đổi ngay sau đó |
| `isHeldByCurrentThread()` | Caller hiện có sở hữu lock không? | Chỉ caller, không tìm owner arbitrary |
| `getHoldCount()` | Số lần caller đã lấy lock theo reentrancy | 0 nếu caller không giữ |
| `hasQueuedThreads()` | Có threads đang chờ lock không? | Snapshot, không hứa thứ tự fairness |
| `getQueueLength()` | **Ước lượng** số threads chờ | Không phải độ dài chính xác bất biến |
| `hasWaiters(condition)` | Có threads đang đợi condition liên quan không? | Caller phải giữ lock khi kiểm tra theo contract |
| `getWaitQueueLength(condition)` | Ước lượng số condition waiters | Phụ thuộc caller giữ lock và sự biến động |

`getQueueLength()` tăng có thể chỉ ra contention nhưng không cho biết **mỗi thread đã đợi bao lâu**, cũng không tự cho nguyên nhân. Một lock fairness-enabled không bảo đảm mọi thread được CPU scheduling công bằng; `tryLock()` không timeout còn có semantics fairness đặc biệt.

### 3.4 Khi cần tránh chờ vô hạn

Với yêu cầu nghiệp vụ có deadline, cân nhắc acquisition có timeout:

```java
boolean acquired = lock.tryLock(200, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!acquired) {
    // Trả về lỗi có phân loại hoặc retry có kiểm soát.
    return;
}
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Đây là **mã minh họa** với biến `lock`, method `updateSharedState` và return từ method void. Chọn timeout theo SLO và invariants, không chọn 200 ms như “chuẩn Java”. Khi dùng `lockInterruptibly()` hoặc timed `tryLock`, phải xử lý `InterruptedException` đúng chính sách cancellation; không nuốt interrupt rồi tiếp tục vô hạn.

### 3.5 Fairness không phải thuốc chữa cho mọi contention

`new ReentrantLock(true)` có thể thiên về waiter lâu hơn theo chính sách fairness, nhưng có thể giảm throughput và không bảo đảm công bằng thread scheduling. Nếu root cause là owner giữ lock trong khi chờ DB 30 giây, bật fairness không làm DB nhanh hơn. Cần đo lock hold time, queue và công việc nằm trong critical section.

## 4. Object.wait(): wait-set, notify và điều kiện logic

### 4.1 wait() phải được gọi khi đang giữ đúng monitor

`Object.wait()`, `notify()`, `notifyAll()` đều yêu cầu caller đang sở hữu monitor của **chính object được gọi**. Ví dụ đúng:

```java
private final Object signal = new Object();
private boolean ready = false;

void awaitReady() throws InterruptedException {
    synchronized (signal) {
        while (!ready) {
            signal.wait();
        }
    }
}

void markReady() {
    synchronized (signal) {
        ready = true;
        signal.notifyAll();
    }
}
```

Đây là **mảnh lớp minh họa**. Hai phương thức bảo vệ chung predicate `ready` bằng cùng monitor `signal`. Vì dùng vòng `while`, waiter kiểm tra lại điều kiện sau notify, interrupt/timeout hoặc spurious wakeup. `notifyAll()` chỉ đánh thức các waiter; họ vẫn phải giành lại monitor để thoát `wait`. Caller `markReady` vẫn giữ monitor tới khi rời synchronized, **không tự nhả khóa ngay ở dòng notifyAll**.

### 4.2 wait() nhả khóa nào?

Khi `signal.wait()` thực sự đi vào wait-set, thread **nhả monitor `signal`**, kể cả các mức reentrant monitor ownership tương ứng; nó phải reacquire monitor ấy trước khi trở về/throw theo semantics. Nhưng `wait()` **không tự nhả mọi monitor khác** mà thread còn giữ.

Ví dụ **rủi ro**:

```java
synchronized (lockA) {
    synchronized (lockB) {
        lockB.wait(); // Nhả lockB trong lúc wait, nhưng vẫn giữ lockA.
    }
}
```

Nếu thread phát `lockB.notifyAll()` cần vào `lockA` trước, hệ thống có thể rơi vào chu trình phụ thuộc. Chẩn đoán phải xem **toàn bộ locks held** của waiter, không chỉ monitor mà nó đang chờ notify.

### 4.3 waiting on khác waiting to lock

Thread đang đợi `Object.wait()` có thể hiện:

```text
"condition-waiter" ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(Native Method)
    - waiting on <0x0000000711303000> (a java.lang.Object)
```

Ở đây `waiting on` là **chờ condition notification**, không phải `waiting to lock` để vào synchronized. Thread đã nhả monitor này trong pha wait. Khi được đánh thức, nó có thể tạm thành `BLOCKED` nếu chưa reacquire được monitor.

### 4.4 Lost signal, notify và spurious wakeup

Lỗi điển hình:

```java
// Sai mô hình: không có predicate và lock bảo vệ condition.
if (!ready) {
    signal.wait(); // Còn có thể IllegalMonitorStateException.
}
```

Ngay cả nếu sửa bằng `synchronized` mà chỉ dùng `if`, vẫn có thể sai vì nhiều waiters, thay đổi condition hoặc **spurious wakeup**. Thiết kế đúng là **predicate + lock + vòng while**, không phải chỉ gọi `notify`.

`notify()` chọn một waiter không được chỉ định; nếu có nhiều điều kiện khác nhau trên một wait-set, đánh thức sai waiter có thể gây khó tiến triển. `notifyAll()` thường dễ lập luận hơn khi không có invariant chọn waiter, nhưng có thể gây “thundering herd”. Khi nhiều independent condition queues cần tối ưu, `Condition` có thể phù hợp hơn.

### 4.5 wait timeout không phải tiến độ bảo đảm

`wait(long timeoutMillis)` trả về sau thông báo, interrupt, timeout hoặc spurious wakeup theo contract. Dùng deadline theo clock/điều kiện và kiểm tra vòng while; **không** mặc định “đã wait 5 giây là state chắc chắn ready”. `wait(0)` nghĩa là chờ vô hạn; không nhầm với không chờ.

Một số code chặn indefinitely vì producer không bao giờ `notifyAll` hoặc không thay predicate. Đây thường là **missed signal/protocol bug**, không nhất thiết tạo deadlock cycle mà `ThreadMXBean.findDeadlockedThreads()` phát hiện.

## 5. Condition.await(): condition queue của Lock

### 5.1 Condition gắn chặt với lock

Với `ReentrantLock`:

```java
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();
private final java.util.concurrent.locks.Condition changed =
        lock.newCondition();
private boolean ready = false;

void awaitReady() throws InterruptedException {
    lock.lock();
    try {
        while (!ready) {
            changed.await();
        }
    } finally {
        lock.unlock();
    }
}

void markReady() {
    lock.lock();
    try {
        ready = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}
```

Đây là **mảnh của class**. `await`/`signal` yêu cầu giữ **associated Lock** theo implementation `ReentrantLock`; gọi `signalAll` mà không giữ lock có thể gây `IllegalMonitorStateException`. `Condition` cung cấp **wait-set riêng** cho một lock, thay vì mọi condition dùng chung một object monitor như `Object.wait/notify`.

### 5.2 await nhả rồi lấy lại lock

Khi `changed.await()` bắt đầu chờ, implementation `ReentrantLock` **nhả hoàn toàn associated lock theo hold count** và khi trở về sẽ giành lại trạng thái ownership tương ứng. Vì vậy thread đang park trên `ConditionObject` **không nhất thiết là owner của ReentrantLock** lúc chụp. Khi được `signal`, nó được chuyển để chờ reacquire; nó **không lập tức chạy** nếu signaling thread vẫn giữ lock.

Sơ đồ:

```text
WAITING thread: holds ReentrantLock
   -> while (!ready)
   -> Condition.await() : releases lock, enters condition queue
   -> receives signal / interrupt / timeout / spurious wakeup
   -> competes to reacquire lock
   -> await returns (with lock held)
   -> checks ready again
   -> eventually unlock in finally
```

`signal` đưa waiter ra khỏi condition queue theo semantics của implementation, nhưng **không trực tiếp cấp lock cho waiter ngay lập tức**. Nếu signaler tiếp tục làm việc dài trong lock, waiter vẫn có thể bị kẹt trên acquisition queue.

### 5.3 Nhận diện Condition trong dump

Ví dụ **mô phỏng**:

```text
"order-consumer" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionNode.block(...)
    at java.util.concurrent.ForkJoinPool.unmanagedBlock(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await(...)
    - parking to wait for <0x0000000711404000>
      (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
```

Các stack frames bên trong AQS/ForkJoinPool **thay đổi theo JDK**; mẫu chỉ nói cách nhận diện `ConditionObject.await` và blocker loại condition. **Không** suy owner từ `ConditionObject` như đó là `ReentrantLock$Sync` đang bị thread khác giữ. Điều cần tìm tiếp là **ai sẽ gọi `signal/signalAll`, predicate nào phải đúng và liệu producer có thể chạy không**.

### 5.4 Vì sao Condition không phải Object.wait trên chính object Condition

`condition.await()` khác hoàn toàn `condition.wait()`. `Condition` là interface với operations mang semantics gắn với `Lock`; `Object.wait` trên chính instance Condition chỉ là object monitor riêng, **không có quan hệ xác định** với associated lock/condition queue. Không thay `changed.await()` bằng `changed.wait()` hoặc gọi `changed.notify()`.

### 5.5 Phân biệt các biến thể await

| Method | Khả năng thoát chờ | Kỳ vọng chẩn đoán |
| --- | --- | --- |
| `await()` | Signal, interrupt, spurious wakeup | Có thể WAITING/parking lâu |
| `awaitUninterruptibly()` | Signal/spurious; giữ lại thông tin interrupt theo contract | Một interrupt đơn lẻ không nhất thiết giải phóng waiter |
| `awaitNanos(nanos)` | Signal/interrupt/spurious/timeout, trả remaining nanos | Có thể TIMED_WAITING |
| `await(time,unit)` | Trả boolean báo signal trước deadline theo contract | Không thay cho kiểm tra predicate |
| `awaitUntil(Date)` | Dùng deadline tuyệt đối theo wall-clock | Clock changes cần được hiểu đúng |

Dù chọn biến thể nào, cần **while(predicate)** và quản lý deadline/interrupt/cancellation. Một timed await trả do timeout không có nghĩa điều kiện đã thành công.

## 6. LockSupport.park(): permit cấp thấp và những chiếc bẫy

### 6.1 Mỗi thread chỉ có tối đa một permit

`LockSupport` dùng một permit logic mỗi thread:

- `unpark(thread)` làm permit khả dụng (nếu chưa có).
- `park()` tiêu thụ permit nếu sẵn có rồi trở về ngay.
- Nếu chưa có permit, `park` có thể block đến khi được unpark, bị interrupt, timeout (bản timed) hoặc spurious return.
- Hai lần `unpark` **không tích lũy thành hai permits**.
- `park` có thể trở về “không có lý do”; caller phải **kiểm tra lại predicate**.
- `park` không ném `InterruptedException`; thread có thể ở trạng thái interrupt và trả về ngay. Việc xử lý interrupted flag do logic caller quyết định.

Nhiều primitive như AQS, thread pools và các hệ thống scheduling dùng `park` bên dưới. Vì vậy thấy `Unsafe.park` trong stack **không đủ** kết luận loại bottleneck.

### 6.2 park không tự nhả bất kỳ khóa nào

Ví dụ **dễ gây treo**:

```java
synchronized (monitor) {
    LockSupport.park(blocker);
}
```

Code trên minh họa một lỗi thiết kế: nếu thread khác cần vào `synchronized(monitor)` để gọi `unpark(owner)`, producer có thể bị chặn bởi chính monitor mà owner đang giữ. `park` **không có semantics nhả monitor**, khác `monitor.wait()`.

Tương tự, nếu giữ `ReentrantLock` khi park, owner vẫn là owner cho đến khi gọi `unlock()`. Không nhầm `WAITING (parking)` với việc thread đã thả mọi locks.

### 6.3 Dùng blocker để hỗ trợ chẩn đoán

`LockSupport.park(blocker)` đặt blocker object mà tools có thể xem bằng `LockSupport.getBlocker(thread)` hoặc `ThreadInfo.getLockInfo()` trong một số trường hợp. Ví dụ:

```java
while (!canContinue.get()) {
    LockSupport.park("waiting-for-work");
}
```

Đây là đoạn minh họa với `AtomicBoolean canContinue`; production nên dùng blocker object có identity rõ (thường là chính synchronizer instance), không nhét customer/request/token vào blocker. `getBlocker` là **snapshot**, có thể trả null sau khi thread đã unpark, và blocker không bắt buộc có owner thread.

### 6.4 unpark trước park khác notify trước wait

`unpark(thread)` có thể xảy ra **trước** `park()` mà vẫn để lại một permit cho lần park kế tiếp (nếu thread đã start và permit chưa bị tiêu thụ); đây là điểm khác với `notify` khi không có waiter: notify không được “tích lại” thành một thông báo tương lai.

Nhưng permit có thể bị một `park` khác tiêu thụ, kể cả qua code/framework khác; không dựa vào permit đơn lẻ như một **message queue**. Thiết kế đúng cần **state flag/volatile hoặc atomic + loop**:

```java
// Consumer:
while (!ready.get()) {
    LockSupport.park(blocker);
}
// Producer:
ready.set(true);
LockSupport.unpark(consumerThread);
```

Đây là **hai snippet minh họa** ở hai threads; `ready` là một `AtomicBoolean` dùng chung, `blocker` là object, `consumerThread` là reference thread đã được start. Nếu dùng state không có visibility semantics, loop có thể không quan sát được cập nhật dù đã unpark.

### 6.5 Park có thể bị interrupt mà không ném exception

Một thread bị interrupt khi đang park có thể trở về, nhưng nếu caller chỉ làm:

```java
while (!ready.get()) {
    LockSupport.park();
}
```

và interrupted flag vẫn set, các lần `park()` tiếp theo có thể trả ngay, tạo **busy loop**. Cần quyết định rõ chính sách cancellation (kiểm tra `Thread.currentThread().isInterrupted()`, kết thúc, hoặc xử lý/khôi phục status đúng contract). Không gọi `Thread.interrupted()` bừa bãi vì method đó **xóa interrupt flag** của current thread.

## 7. Thread state: BLOCKED, WAITING và TIMED_WAITING không phải nguyên nhân

| Thread state | Nguyên nhân có thể gặp | Cần quan sát tiếp |
| --- | --- | --- |
| `BLOCKED` | Đợi vào/reenter monitor `synchronized` | Monitor ID, `waiting to lock`, owner và held-lock stack |
| `WAITING` | `Object.wait(0)`, `Condition.await`, `LockSupport.park`, `Thread.join`, pool idle | Stack frame, blocker type, predicate và bên đánh thức |
| `TIMED_WAITING` | `sleep`, `wait(timeout)`, timed await, `parkNanos/Until`, timed join | Deadline, owner locks giữ khi chờ, thời gian chờ thực |
| `RUNNABLE` | Chạy Java, đang làm native call, chờ một số dạng I/O | CPU time, OS state, stack changes, syscall/network |
| `TERMINATED` | Thread đã kết thúc | Không suy quá khứ từ một snapshot sau khi xong |
| `NEW` | Thread chưa được start | Không phải waiter đang tranh monitor |

**WAITING không chứng minh nhàn rỗi.** Một thread có thể WAITING ở `CountDownLatch.await` nhưng vẫn giữ một monitor hoặc `ReentrantLock` mà nhiều threads khác cần. Ngược lại, nhiều worker WAITING trên queue vì không có task có thể là **trạng thái bình thường**.

**RUNNABLE không đồng nghĩa chiếm CPU**. Một thread trong native I/O hoặc scheduling cũng có thể được biểu diễn RUNNABLE từ góc nhìn Java. Cần OS CPU/cgroup metrics hoặc JFR để phân biệt.

## 8. Thu thread dump và chọn đúng thông tin

### 8.1 Sử dụng jcmd trên HotSpot

Trước tiên xác minh đúng PID/JVM instance, JDK tool, quyền và host/container namespace. Sau đó:

```bash
jcmd 4242 help Thread.print
jcmd 4242 Thread.print -l
```

`4242` là **PID minh họa**. Với HotSpot/JDK hiện đại, `Thread.print -l` yêu cầu kèm thông tin `java.util.concurrent` locks/ownable synchronizers; phiên bản và các flags cụ thể cần kiểm tra bằng `help` của JVM. Đừng nhầm `jcmd -l` (liệt kê JVM) với `jcmd PID Thread.print -l` (thread dump chi tiết).

Có thể dùng `jstack -l 4242` nếu công cụ/JDK hiện có và hỗ trợ. Nếu attach bị vô hiệu, JVM đã thoát hoặc PID sai, không tự coi không tạo được dump là deadlock. Thu dump có thể tốn CPU/thời gian và chứa thông tin nhạy cảm; đừng chạy capture loop vô hạn trong production.

### 8.2 Đọc marker theo loại chờ

Một bộ marker giả định:

```text
"blocked-monitor" ... java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <0x0000000711505000> (a java.lang.Object)

"holds-monitor" ... java.lang.Thread.State: TIMED_WAITING (sleeping)
    - locked <0x0000000711505000> (a java.lang.Object)

"waits-notify" ... java.lang.Thread.State: WAITING (on object monitor)
    - waiting on <0x0000000711506000> (a java.lang.Object)

"waits-aqs" ... java.lang.Thread.State: WAITING (parking)
    - parking to wait for <0x0000000711507000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)

"waits-condition" ... java.lang.Thread.State: WAITING (parking)
    - parking to wait for <0x0000000711508000>
      (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
```

Các dòng viết gọn để giải thích **không phải format đầy đủ thực tế**. Tùy implementation/JDK, nội dung marker/stack thay đổi; hãy đọc đúng giá trị trong cùng artifact, không tự regex cứng mọi JDK.

- `waiting to lock` → tranh **intrinsic monitor**.
- `locked` → đang **giữ monitor**.
- `waiting on` → chờ **Object.wait/notify**.
- `parking to wait for ...ReentrantLock$...Sync` → có thể đang chờ **ownable ReentrantLock**.
- `parking to wait for ...ConditionObject` → có thể đang chờ **condition signal**, chưa chắc owner là lock holder đó.

### 8.3 Locked ownable synchronizers

Ở phần cuối mỗi thread block, dump với `-l` có thể hiện:

```text
Locked ownable synchronizers:
    - <0x0000000711507000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

Phần này **khác** `- locked <...>` của object monitors. Khi chẩn đoán `ReentrantLock` contention, tìm owner sở hữu **cùng synchronizer identity** trong cùng dump, và xem thread owner đang làm gì. Không lấy object identity từ JVM restart khác hoặc so hash/address bằng một phép chuyển đổi tùy tiện.

### 8.4 ThreadMXBean: monitor, synchronizer và deadlock

Java API:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
if (mx.isObjectMonitorUsageSupported()
        && mx.isSynchronizerUsageSupported()) {
    ThreadInfo[] infos = mx.dumpAllThreads(true, true);
}
```

Đây là **mảnh minh họa** trong một method có `import java.lang.management.*`. Mảng `ThreadInfo` biểu diễn **platform threads** mà API hỗ trợ; trong Java 21 virtual threads không được kiểm kê/giám sát toàn bộ bằng interface này. Khi không hỗ trợ monitor/synchronizer usage, việc yêu cầu chụp chi tiết có thể ném `UnsupportedOperationException`.

Bảng ánh xạ:

| Java API | Điều muốn biết | Lưu ý |
| --- | --- | --- |
| `ThreadInfo.getThreadState()` | State ở snapshot | Có thể thay đổi ngay |
| `getLockInfo()` | Lock/blocker thread đang chờ nếu có | Blocker không phải lúc nào có owner |
| `getLockOwnerId()` | Java thread ID của owner nếu biết | `-1` nghĩa không có/không biết |
| `getLockedMonitors()` | Monitors đang giữ khi đã thu thông tin này | Mảng rỗng có thể vì không request |
| `getLockedSynchronizers()` | Ownable synchronizers đang giữ | Không liệt kê mọi wait primitive |
| `getBlockedCount()` | Số lần block monitor entry | Không phải thời gian từng event |
| `getBlockedTime()` | Total monitor block time khi contention monitoring bật | Có thể `-1` và cần overhead |
| `getWaitedCount()` | Số lần wait theo semantics API | Không nói liệu thiếu signal |
| `getWaitedTime()` | Time chờ tích lũy khi được bật/hỗ trợ | Không phải latency histogram |

`ThreadMXBean.findMonitorDeadlockedThreads()` tìm cycles chờ object monitors; `findDeadlockedThreads()` còn có thể tìm cycles với **ownable synchronizers** khi JVM hỗ trợ. Nhưng không phương thức nào là công cụ tổng quát phát hiện mọi kiểu stuck/livelock/starvation/queue-wait, và không thay JFR/tracing.

### 8.5 Virtual threads và giới hạn phiên bản

Java 17 chưa có virtual threads ổn định; Java 21 có. Với virtual threads, stack dumps và handling synchronized/monitor pinning/diagnostic support **khác theo JDK release**. `ThreadMXBean` ở Java 21 hướng tới **platform threads**; một thread pool có vài carrier threads không chứng minh chỉ có vài virtual tasks. Không diễn giải `dumpAllThreads(true,true)` như inventory đầy đủ của virtual threads. Nếu hệ thống dùng virtual threads, chọn tool/format/JFR tương ứng JDK đang chạy.

## 9. Đọc code và dựng đồ thị phụ thuộc để tìm nguyên nhân

### 9.1 Mỗi cạnh phải nêu rõ “đang chờ cái gì”

Một graph minh họa:

```text
request-B -- wants intrinsic monitor M --> request-A
request-C -- wants intrinsic monitor M --> request-A
request-A -- waits for DB connection --> DB pool
```

Đây là **lock convoy**, không nhất thiết là Java-level deadlock. Nếu request-A có thể lấy connection và rời monitor, các waiter có thể tiến triển. Chẩn đoán root cause cần xem DB pool, timeouts và lý do critical section bao chứa DB I/O.

Một graph khác:

```text
thread-A -- holds lock-X; waits lock-Y --> thread-B
thread-B -- holds lock-Y; waits lock-X --> thread-A
```

Khi owner and wait edges được xác minh **trong cùng JVM/snapshot**, cycle này phù hợp với deadlock. Cần phân biệt lock-X/Y là monitor hay ownable synchronizer để chọn detector và cách sửa lock order.

### 9.2 Mối phụ thuộc signal không nhất thiết có lock owner

Ví dụ:

```text
consumer -- Condition.await() --> signal by producer
producer -- waits for executor slot --> thread pool
all pool threads -- waiting for consumer result --> consumer
```

Không phải mọi cạnh này có object monitor/ownable owner. Đây có thể là **executor/thread-pool starvation** hoặc protocol chờ vòng, dù `findDeadlockedThreads()` trả `null`. Phải đọc kiến trúc producer/consumer, queue capacity, callbacks và signal conditions. Không dựng một owner giả từ `ConditionObject`.

### 9.3 Câu hỏi chẩn đoán theo thứ tự

1. **Đúng JVM?** PID + process start time, container/host scope, thời điểm UTC.
2. **Mục tiêu bất thường?** p95/p99 request, throughput, queue size, timeouts, resource pressure.
3. **Thread đợi monitor/lock hay đợi condition?** State + stack + blocker.
4. **Nếu đợi lock, owner là ai?** Lock identity, `- locked`, ownable section, owner ID.
5. **Nếu đợi signal, ai chịu trách nhiệm phát?** Predicate, producer, notify/signal/unpark, cancellation.
6. **Owner/producer có tiến triển không?** Nhiều snapshots và application metrics.
7. **Có cycle chắc chắn hay chỉ chain?** Monitor/ownable graph vs DB/executor/event dependencies.
8. **Điều gì thay đổi gần thời điểm sự cố?** Deployment, load, flags, thread pool size, dependency latency.
9. **Giải pháp có giữ invariant và bảo mật không?** Không tùy tiện gọi unlock/notify/interrupt trên JVM production.

## 10. Ví dụ Java 17+ hoàn chỉnh: quan sát năm kiểu chờ trong một JVM

Ví dụ có hai chế độ để phân biệt **kết quả lý thuyết có thể kiểm chứng** và **snapshot runtime không xác định**:

- **Mặc định:** chỉ in sơ đồ semantics, stdout cố định.
- **`--live`:** tạo các platform threads của chính JVM demo. Chúng mô phỏng monitor owner/contender, ReentrantLock owner/contender, Object.wait waiter, Condition.await waiter và LockSupport.park waiter; lấy snapshot bằng `ThreadMXBean` rồi giải phóng tất cả.

**An toàn của ví dụ:** không tạo deadlock cố ý, không attach JVM khác, không gửi notify/unpark cho thread lạ; dùng cờ điều kiện, latches và `finally`. Snapshot vẫn chịu race nên các dòng live không có stdout cố định.

Lưu file `SyncDiagnosticDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.LockSupport;
import java.util.concurrent.locks.ReentrantLock;

public class SyncDiagnosticDemo {
    static void printRules() {
        System.out.println("SYNCHRONIZED_CONTENDER=BLOCKED_ON_MONITOR");
        System.out.println("REENTRANT_LOCK_CONTENDER=USUALLY_PARKING");
        System.out.println("OBJECT_WAIT=RELEASES_ITS_MONITOR");
        System.out.println("CONDITION_AWAIT=RELEASES_ASSOCIATED_LOCK");
        System.out.println("LOCK_SUPPORT_PARK=DOES_NOT_RELEASE_LOCKS");
        System.out.println("WAITING_THREAD=NOT_AUTOMATICALLY_DEADLOCKED");
    }

    static void waitForRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static void printInfo(String alias, ThreadInfo info) {
        if (info == null) {
            System.out.println(alias + ".snapshot=UNAVAILABLE");
            return;
        }
        System.out.println(alias + ".state=" + info.getThreadState());
        System.out.println(alias + ".lock_info_present="
                + (info.getLockInfo() != null));
        System.out.println(alias + ".owner_known="
                + (info.getLockOwnerId() >= 0));
        System.out.println(alias + ".held_monitors="
                + info.getLockedMonitors().length);
        System.out.println(alias + ".held_ownable="
                + info.getLockedSynchronizers().length);
    }

    static void live() throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        if (!mx.isObjectMonitorUsageSupported()
                || !mx.isSynchronizerUsageSupported()) {
            System.out.println("LIVE_LOCK_DETAILS=UNSUPPORTED");
            return;
        }

        Object monitor = new Object();
        Object waitObject = new Object();
        Object parkBlocker = new Object();
        ReentrantLock exclusive = new ReentrantLock();
        ReentrantLock conditionLock = new ReentrantLock();
        Condition changed = conditionLock.newCondition();

        CountDownLatch readyOwners = new CountDownLatch(2);
        CountDownLatch releaseOwners = new CountDownLatch(1);
        CountDownLatch readyWaiters = new CountDownLatch(3);
        AtomicBoolean objectGo = new AtomicBoolean(false);
        AtomicBoolean conditionGo = new AtomicBoolean(false);
        AtomicBoolean parkGo = new AtomicBoolean(false);

        Thread monitorOwner = new Thread(() -> {
            synchronized (monitor) {
                readyOwners.countDown();
                waitForRelease(releaseOwners);
            }
        }, "demo-monitor-owner");

        Thread lockOwner = new Thread(() -> {
            exclusive.lock();
            try {
                readyOwners.countDown();
                waitForRelease(releaseOwners);
            } finally {
                exclusive.unlock();
            }
        }, "demo-lock-owner");

        Thread monitorContender = new Thread(() -> {
            synchronized (monitor) {
                // Chỉ vào khi monitorOwner đã nhả khóa.
            }
        }, "demo-monitor-contender");

        Thread lockContender = new Thread(() -> {
            exclusive.lock();
            try {
                // Chỉ vào khi lockOwner unlock.
            } finally {
                exclusive.unlock();
            }
        }, "demo-lock-contender");

        Thread objectWaiter = new Thread(() -> {
            synchronized (waitObject) {
                readyWaiters.countDown();
                while (!objectGo.get()) {
                    try {
                        waitObject.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            }
        }, "demo-object-waiter");

        Thread conditionWaiter = new Thread(() -> {
            conditionLock.lock();
            try {
                readyWaiters.countDown();
                while (!conditionGo.get()) {
                    try {
                        changed.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            } finally {
                conditionLock.unlock();
            }
        }, "demo-condition-waiter");

        Thread parkWaiter = new Thread(() -> {
            readyWaiters.countDown();
            while (!parkGo.get() && !Thread.currentThread().isInterrupted()) {
                LockSupport.park(parkBlocker);
            }
        }, "demo-park-waiter");

        Thread[] threads = {
            monitorOwner, monitorContender,
            lockOwner, lockContender,
            objectWaiter, conditionWaiter, parkWaiter
        };
        String[] aliases = {
            "MONITOR_OWNER", "MONITOR_CONTENDER",
            "LOCK_OWNER", "LOCK_CONTENDER",
            "OBJECT_WAITER", "CONDITION_WAITER", "PARK_WAITER"
        };

        try {
            monitorOwner.start();
            lockOwner.start();

            if (!readyOwners.await(3, TimeUnit.SECONDS)) {
                System.out.println("LIVE_SETUP=OWNERS_NOT_READY");
                return;
            }

            monitorContender.start();
            lockContender.start();
            objectWaiter.start();
            conditionWaiter.start();
            parkWaiter.start();

            if (!readyWaiters.await(3, TimeUnit.SECONDS)) {
                System.out.println("LIVE_SETUP=WAITERS_NOT_READY");
                return;
            }

            // Best-effort: chờ các state rõ hơn, không tạo atomic snapshot.
            for (int attempt = 0; attempt < 100; attempt++) {
                boolean monitorBlocked =
                        monitorContender.getState() == Thread.State.BLOCKED;
                boolean ownableWait =
                        lockContender.getState() == Thread.State.WAITING
                        || lockContender.getState() == Thread.State.TIMED_WAITING;
                if (monitorBlocked && ownableWait) {
                    break;
                }
                Thread.sleep(10);
            }

            long[] ids = new long[threads.length];
            for (int i = 0; i < threads.length; i++) {
                ids[i] = threads[i].getId();
            }
            ThreadInfo[] info = mx.getThreadInfo(ids, true, true);
            for (int i = 0; i < threads.length; i++) {
                printInfo(aliases[i], info[i]);
            }
        } finally {
            releaseOwners.countDown();

            synchronized (waitObject) {
                objectGo.set(true);
                waitObject.notifyAll();
            }

            conditionLock.lock();
            try {
                conditionGo.set(true);
                changed.signalAll();
            } finally {
                conditionLock.unlock();
            }

            parkGo.set(true);
            LockSupport.unpark(parkWaiter);

            for (Thread thread : threads) {
                if (thread.isAlive()) {
                    thread.interrupt(); // Lối thoát bổ sung nếu demo bị delay.
                    thread.join(2000);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        printRules();
        if (args.length == 1 && "--live".equals(args[0])) {
            live();
        }
    }
}
```

Biên dịch và chạy chế độ mặc định:

```bash
javac SyncDiagnosticDemo.java
java SyncDiagnosticDemo
```

**Stdout chính xác của chế độ mặc định**:

```text
SYNCHRONIZED_CONTENDER=BLOCKED_ON_MONITOR
REENTRANT_LOCK_CONTENDER=USUALLY_PARKING
OBJECT_WAIT=RELEASES_ITS_MONITOR
CONDITION_AWAIT=RELEASES_ASSOCIATED_LOCK
LOCK_SUPPORT_PARK=DOES_NOT_RELEASE_LOCKS
WAITING_THREAD=NOT_AUTOMATICALLY_DEADLOCKED
```

Đây là **khẳng định kiến thức do code in ra**, không phải phép đo thực tế. Để xem threads thật:

```bash
java SyncDiagnosticDemo --live
```

Khi `--live`, chương trình in sáu dòng mô hình trước, sau đó là các dòng `ALIAS.state`, `ALIAS.lock_info_present`, `ALIAS.owner_known`, `ALIAS.held_monitors` và `ALIAS.held_ownable` cho bảy threads. Giá trị thay đổi theo JDK/scheduler và thời điểm snapshot; ví dụ có thể thấy `MONITOR_CONTENDER.state=BLOCKED`, `LOCK_CONTENDER.state=WAITING`, `OBJECT_WAITER.state=WAITING`, `CONDITION_WAITER.state=WAITING`, `PARK_WAITER.state=WAITING`, nhưng **đó là kỳ vọng có điều kiện, không phải stdout đã được xác minh**.

### 10.1 Tại sao demo còn có owner đang WAITING?

`monitorOwner` giữ intrinsic monitor và `lockOwner` giữ ReentrantLock khi chờ `releaseOwners.await()`. Vì họ vẫn giữ khóa, hai contenders phải chờ. Đây là tình huống **WAITING owner gây contention**: dù owner đang WAITING ở latch, nó chưa hề nhả monitor/ReentrantLock. Mục đích là học đọc “owner chờ vì sao”, không phải khuyến nghị giữ mutex khi đợi latch trong production.

### 10.2 Tại sao Object.wait và Condition.await xuất hiện khác nhau?

`objectWaiter` gọi `waitObject.wait()` trong synchronized, nhả monitor `waitObject` trong thời gian đợi. `conditionWaiter` gọi `changed.await()` khi giữ `conditionLock`, nhả associated ReentrantLock rồi reacquire khi thức dậy. `parkWaiter` dùng `LockSupport.park(parkBlocker)` và chỉ tiếp tục khi `parkGo` đã được bật/unpark/interrupt hoặc có spurious return; `park` không tự thao tác lock nào.

### 10.3 Vì sao không in thời gian chờ chính xác?

`ThreadInfo` là ảnh chụp, không phải stopwatch cho một lần chờ. `getBlockedTime()`/`getWaitedTime()` là thời gian tích lũy và có thể `-1` nếu contention monitoring không bật/hỗ trợ. Code demo không thay đổi management flags và không cố tính p95 từ các counters ấy. Khi phân tích latency thực tế, dùng application histogram/JFR/trace đồng bộ thời gian.

### 10.4 Dọn dẹp sau snapshot

Phần `finally` giải phóng latches, đặt predicates, `notifyAll`, `signalAll`, `unpark` và yêu cầu interrupt như đường thoát dự phòng. `join(2000)` giới hạn thời gian chờ join, **không bảo đảm** mọi thread tùy ý trong một ứng dụng đều đã thoát khi deadline hết; ví dụ được thiết kế để chạy xong trong điều kiện bình thường.

Nếu thích dùng mã mẫu để thực nghiệm trên CI, hãy chạy process riêng có timeout tổng, không lặp quá dày trên production. Thread states có race tự nhiên, vì vậy automated tests nên xác minh **invariants/predicate và kết thúc an toàn**, không assert mọi JVM phải in chính xác một trạng thái WAITING tại từng mili giây.

## 11. Ba mẫu lỗi chờ thường gặp và cách chẩn đoán

### 11.1 Mất signal do protocol sai

**Triệu chứng:** consumers `WAITING` ở `Object.wait` hoặc `Condition.await` mãi dù producers từng “gọi notify”.

**Các câu hỏi:**

- Predicate như `queueNotEmpty`, `ready` có thật sự được cập nhật trước signal không?
- Cả producer/consumer có dùng cùng monitor hoặc cùng associated lock?
- Waiter dùng `while (!condition) await()` hay chỉ gọi wait mù?
- Signal xảy ra trước waiter mà **không có state** lưu điều kiện?
- Có exception/early return khiến signal không thực hiện?
- Có đổi lock object sau redeploy/DI khiến hai bên chờ **hai object khác nhau**?

**Cách sửa:** điều kiện phải là state có visibility/happens-before được bảo vệ bởi lock hoặc atomic; signal gắn với cập nhật state; waiter luôn recheck. Không chỉ thêm `notifyAll` ở chỗ bất kỳ để “chữa treo” nếu protocol gốc sai.

### 11.2 Owner giữ mutex trong lúc chờ ngoại lực

**Triệu chứng:** nhiều threads `BLOCKED` cùng một monitor hoặc WAITING/parking trên cùng ReentrantLock; owner lại sleep, chờ DB/network, latch hoặc completion của task pool.

**Giả thuyết:** critical section quá rộng hoặc phụ thuộc vòng. Tìm thời gian giữ lock/queue metrics và owner stack trong nhiều snapshots. Nếu owner cần kết quả từ thread đang bị chính lock đó chặn, có thể là cycle. Nếu owner cần DB response nhưng DB vẫn hoạt động, có thể là long hold/convoy.

**Cách sửa:** thu hẹp critical section, tránh remote I/O trong mutex, đặt timeout và thiết kế transaction/state update an toàn. Không sửa bằng cách gọi `unlock` từ thread khác hoặc restart ngay khi chưa thu bằng chứng.

### 11.3 Lock order inversion

**Triệu chứng:** thread A giữ L1 muốn L2, thread B giữ L2 muốn L1. Có thể là hai monitors hoặc ownable locks.

**Khắc phục mang tính thiết kế:** thống nhất thứ tự lấy khóa trên mọi code path, giảm lồng locks, tách shared-state ownership, dùng timed acquisition có rollback/cancellation phù hợp và test under contention. Chọn một thứ tự toàn cục (ví dụ lock ID/ordering key) nếu domain cho phép; không dùng thứ tự ngẫu nhiên giữa threads.

## 12. Phân biệt deadlock, starvation, livelock và contention dài

| Hiện tượng | Dấu hiệu | Thread dump có thể thấy | Điều cần chứng minh |
| --- | --- | --- | --- |
| **Deadlock** | Chu trình phụ thuộc không có đường thoát | Thread A/B chờ khóa của nhau, hoặc broader dependency cycle | Owner/held-lock edges đúng snapshot, không thể tiến triển |
| **Lock contention** | Nhiều waiter trên cùng lock | `BLOCKED` trên monitor, hoặc AQS park | Owner và thời gian giữ khóa; có tiến triển hay không |
| **Starvation** | Một số threads lâu không được phục vụ/tài nguyên | Pool threads WAITING, queue lớn, executor thiếu worker | Scheduling/resource allocation và thời gian |
| **Livelock** | Threads hoạt động nhưng không hoàn thành công việc | RUNNABLE/churn stacks đổi liên tục | Counter tiến triển giả, retry loop, throughput thấp |
| **Missed signal** | Condition waiter không thức dậy dù business state cần thay đổi | `WAITING (on object monitor)` hoặc `Condition.await` park | Predicate/producer/signal protocol |
| **External I/O hang** | Thread chờ DB/network/disk | WAITING/RUNNABLE/native stack tùy API | Dependency timeouts, TCP/DB health, owner giữ locks? |

`findDeadlockedThreads() == null` chỉ nói không tìm thấy **loại cycles mà detector hỗ trợ ở thời điểm đó**. Không loại trừ hang vì I/O, pool starvation, missing signal hay virtual-thread-related liveness vấn đề ngoài phạm vi API.

## 13. ThreadInfo, monitoring và cách chứng minh thời gian kéo dài

### 13.1 Chụp nhiều snapshots có chủ đích

Một thread dump chỉ là **một ảnh chụp**. Để nói “thread A đã giữ lock 30 giây”, cần chuỗi snapshots có timestamp và identity của **cùng JVM**, hoặc instrumentation đo lock hold duration. Ví dụ:

```text
12:00:00  T1 --holds M--> 25 waiters
12:00:05  T1 --holds M--> 32 waiters
12:00:10  T1 --holds M--> 40 waiters
```

Đây là dữ liệu **minh họa**; gợi ý monitor M là bottleneck kéo dài, nhưng chưa nói lý do T1 giữ lâu. Cần stack/source và ứng dụng metrics. Nếu PID/JVM restart giữa các snapshots, Object ID không còn ý nghĩa xuyên run.

### 13.2 Contention monitoring không miễn phí

Nếu `ThreadMXBean.isThreadContentionMonitoringSupported()` trả true, có thể bật monitoring để lấy accumulated blocked/waited time. Tuy nhiên việc bật `setThreadContentionMonitoringEnabled(true)` thay đổi trạng thái JVM và có overhead. Chỉ thực hiện theo quyền/runbook khi cần, không đưa vào demo read-only như mặc định.

**Số lần BLOCKED không bằng thời gian BLOCKED.** Tổng time chia count chỉ cho một trung bình thô, không phải p95 hoặc max lock wait. Để phân tích tail latency, dùng JFR events, code instrumentation hoặc metrics histogram phù hợp.

### 13.3 Owner ID chỉ có nghĩa trong đúng JVM

`ThreadInfo.getThreadId()` là Java thread ID; `nid` trong HotSpot dump là native thread ID OS ở một số nền tảng. Không lấy `nid=0x...` làm `ThreadInfo.getThreadId()` rồi so trực tiếp. `getLockOwnerId()` là Java thread ID nếu biết, `-1` khi không có/không biết. Một thread park trên condition/latch không bắt buộc có owner riêng; không tự invent owner vì `getLockInfo()!=null`.

### 13.4 Thread dump có thể thiếu dữ liệu

- JVM/VM version không hỗ trợ locked synchronizer usage.
- Output bị cắt vì số lượng threads quá lớn.
- Thread đã kết thúc trước khi capture (`ThreadInfo == null`).
- Tool không có quyền attach hoặc đang ở container PID namespace khác.
- Virtual threads không được bao phủ bởi API/tool đang dùng.
- JVM quá tải làm capture chậm, khiến event đã qua.

Do đó “không thấy owner trong dump” là **thiếu bằng chứng**, không phải chủ chắc chắn không tồn tại.

## 14. Nhật ký, JFR và metrics bổ sung cho thread dump

Một chẩn đoán tốt nối thread dump với những dữ liệu khác:

| Nguồn | Giải đáp | Giới hạn |
| --- | --- | --- |
| Thread dump/ThreadMXBean | Thread state, stack, lock đang chờ/đang giữ, deadlock graph | Snapshot, không có lịch sử event đầy đủ |
| JFR | Monitor enter/park, thread events, CPU, execution sampling khi recording có cấu hình | Event availability/threshold và overhead phụ thuộc JDK/recording |
| Application trace | Request nào đang chờ task/DB/lock, latency path | Cần instrumentation và sampling phù hợp |
| Metrics thread pool/queue | Active threads, queue depth, rejection, completed tasks | Không tự tìm owner hoặc missing signal |
| OS/cgroup CPU | CPU saturation/throttling, scheduling pressure | Không trực tiếp giải thích Java lock semantics |
| DB/network metrics | Pool exhaustion, slow query, timeout, dependency errors | Không cho thấy lock được giữ trong code nếu không đối chiếu stack |
| GC logs/JFR | Pause/GC event trùng thời gian | Không quy mọi WAITING/BLOCKED cho GC |

Khi thu JFR trong incident, kiểm tra recording profile đã bật sự kiện Java monitor enter/park và threshold phù hợp chưa; event thresholds có thể lọc những lần chờ ngắn. Một stack event trên JFR có thể giúp bổ sung timestamp/duration, nhưng không biến mọi loại `LockSupport.park` thành primitive có owner.

### 14.1 Đừng tạo quá nhiều artifacts vô ích

Chụp hàng trăm thread dumps sát nhau trên JVM 10.000 threads có thể tạo overhead và artifact lớn; khi hệ thống vốn đang quá tải, điều này tự làm tình hình xấu hơn. Chọn thời điểm đo có mục tiêu, ví dụ vài snapshots cách nhau vài giây kèm timestamp, hoặc JFR có giới hạn dung lượng/thời gian nếu được phép. Không có cadence mặc định đúng cho mọi JVM.

### 14.2 An toàn thông tin khi chia sẻ dump

Thread name, class/package name, đường dẫn, request/session identifier, URL, credentials trong stack frames/message có thể là thông tin nhạy cảm. Lưu raw artifact trong kho có RBAC/retention thích hợp; bản chia sẻ chỉ giữ alias, lock identity mapping, đoạn stack cần thiết và timeline. Không đổi lock IDs tùy tiện khiến mất khả năng nối owner-wait graph; nếu phải redact, dùng mapping nhất quán **trong một incident**.

## 15. Những lời khuyên sửa lỗi cần tránh

| “Sửa nhanh” thường gặp | Vì sao nguy hiểm/sai | Hướng đúng |
| --- | --- | --- |
| Gọi `notifyAll` ở bất kỳ object nào | Notify đúng wait-set mới có ý nghĩa, còn phải đổi predicate | Tìm đúng shared state + monitor và protocol |
| Gọi `Condition.signal` mà không giữ associated lock | Với ReentrantLock Condition sẽ vi phạm contract | Lấy lock, đổi predicate, signal trong try/finally |
| Tự gọi `unlock` thay owner | `IllegalMonitorStateException`, vi phạm ownership | Sửa owner code, finally và cancellation |
| Thay `await` bằng `park` trực tiếp | Park không tự nhả lock, dễ giữ mutex khi đợi | Giữ abstraction Condition cho wait-set |
| Thêm `Thread.sleep` để “tránh race” | Chỉ che scheduling bug, không có happens-before đúng | Dùng condition/predicate/lock/latch hợp lệ |
| Dùng `if` thay `while` quanh wait/await | Spurious wakeup/competition có thể làm sai invariant | Vòng while kiểm tra predicate |
| Xem `WAITING` là idle | Thread có thể giữ lock hoặc chờ producer không thể chạy | Xem held-locks, owner, dependency graph |
| Tăng thread pool vô hạn | Có thể tăng contention, CPU/context switches | Điều tra queue/owner/blocking dependency |
| Bật ReentrantLock fairness để chữa mọi thứ | Không sửa critical section dài, có thể giảm throughput | Giảm lock scope, đo hold/wait time |
| Dùng `Thread.stop()` để phá lock | Không an toàn, có thể phá invariants | Cancellation hợp lệ, timeout, restart theo runbook |
| Diễn giải `findDeadlockedThreads()==null` là “không treo” | Không bao gồm mọi liveness failure | JFR, traces, queue/protocol analysis |
| Copy lock ID từ dump sau restart | Object identity khác nhau | So trong cùng JVM instance và snapshot |
| Thu `jcmd Thread.print` sai PID | Có thể tác động/sao chép nhầm service | Xác minh PID/start time/namespace |
| Chia sẻ raw dump ra kênh mở | Có thể lộ metadata/identifiers | Redact có kiểm soát và RBAC |

## 16. Quy trình incident: từ triệu chứng đến nguyên nhân và khắc phục

1. **Xác minh target:** service, JVM instance/PID, process start time, JDK release, host/container namespace.
2. **Ghi triệu chứng và window:** request latency, error rate, throughput, thread pool queue, CPU, DB/network metrics.
3. **Thu snapshot hợp lệ:** `jcmd PID Thread.print -l` hoặc `ThreadMXBean` có monitor/synchronizer support; ghi UTC timestamp và option.
4. **Nhóm threads:** `BLOCKED` monitor entry; `WAITING/TIMED_WAITING` trên `Object.wait`, `Condition.await`, AQS/`ReentrantLock`, `LockSupport.park`, pool idle, I/O.
5. **Với lock contention:** tìm lock identity và owner, đọc held monitors/ownable synchronizers, đọc stack owner.
6. **Với condition wait:** tìm predicate, producer, signal/notify/unpark protocol, kiểm tra queue/threads có đủ nguồn lực để producer chạy.
7. **Vẽ đồ thị:** waiter → owner hoặc waiter → signal producer; phân biệt cycle, long hold, queue starvation, missing signal.
8. **Chụp lại có kiểm soát:** xác nhận trạng thái kéo dài, số waiters tăng, owner stack có tiến triển hay không.
9. **Đối chiếu evidence khác:** JFR monitor/park events, application traces, DB pool, GC/CPU/cgroup, deployment changes.
10. **Chọn thay đổi nhỏ nhưng đúng invariant:** giảm scope lock, chuẩn hóa lock order, bổ sung timeouts/cancellation, sửa signal/predicate, tránh blocking I/O dưới mutex.
11. **Kiểm thử dưới tải/tình huống hỏng:** missed signal, spurious wakeup, interrupt, timeout, double unlock, restart, pool exhaustion.
12. **Hậu kiểm:** so p95/p99 latency, throughput, queue, lock wait/hold distribution, deadlock detection và error rate; không tuyên bố fix chỉ vì một dump sau đó ít WAITING.

Nếu không có owner/predicate/stack đủ dữ liệu, báo “chưa xác minh”, không tự suy “Java deadlock” từ một dòng `Unsafe.park`.

## 17. Checklist chẩn đoán từng cơ chế

### synchronized

- [ ] Thread chờ là `BLOCKED` trên monitor entry hay chỉ `WAITING` nơi khác?
- [ ] Marker `waiting to lock` có ID khớp với `- locked` của owner trong cùng dump?
- [ ] Owner giữ monitor trong lúc sleep/I/O/await/CPU dài?
- [ ] Có lock-order inversion hoặc nhiều threads chung một monitor?

### ReentrantLock

- [ ] Có stack AQS/`ReentrantLock.lock` và blocker `...Sync` không?
- [ ] Owner được nhận diện qua `Locked ownable synchronizers`/owner ID?
- [ ] `getQueueLength` chỉ là estimate, không phải bằng chứng tuyệt đối?
- [ ] `tryLock`/`lockInterruptibly`/timeout/cancellation semantics được dùng đúng?
- [ ] Có `unlock` trong `finally` và đúng thread sở hữu?

### Object.wait / notify

- [ ] `wait` được gọi dưới đúng monitor?
- [ ] Predicate chung được đọc/ghi dưới lock và kiểm tra bằng `while`?
- [ ] Producer thực sự đổi predicate, gọi notify/signal đúng object?
- [ ] Waiter đã nhả monitor đang wait nhưng còn giữ monitor khác nào?
- [ ] Có missed signal, spurious wakeup, timeout/interrupt bị xử lý sai?

### Condition

- [ ] `await/signal` dùng đúng Condition của associated Lock?
- [ ] Có `lock.lock()`/`unlock()` đúng phạm vi và `finally`?
- [ ] `await` nhả/reacquire lock; có nhầm waiter thành owner không?
- [ ] Producer gọi `signal/signalAll` sau cập nhật predicate và khi giữ lock?
- [ ] Có nhiều condition queues, signal nhầm queue hay producer không được scheduling?

### LockSupport.park

- [ ] Có blocker object rõ hay chỉ `Unsafe.park` trống?
- [ ] Thread có giữ monitor/ReentrantLock trong lúc park không?
- [ ] `unpark(thread)` được gọi với thread reference đúng và đã start?
- [ ] Có volatile/atomic predicate, while-loop recheck và spurious handling?
- [ ] Interrupt status có làm park trở về liên tục thành spin loop?
- [ ] Không nhầm permit 1-bit với queue nhiều tín hiệu?

## 18. Bài tập tự kiểm tra

**Câu 1.** Thread A `WAITING` trong `CountDownLatch.await()` nhưng có `- locked <M>`; Thread B `BLOCKED` đợi M. Có chắc A đã nhả M vì nó WAITING không?

**Đáp án:** Không. Latch await không tự nhả monitor M. A vẫn là owner của M; B chờ nó. Phải xem ai sẽ countDown latch và có cần monitor M để làm việc đó không.

**Câu 2.** Thread B ở `WAITING (parking)` trong `ReentrantLock.lock()`. Có phải `Thread.State.BLOCKED` mới được gọi là lock contention?

**Đáp án:** Không. `BLOCKED` dành cho monitor entry; ReentrantLock contention thường dùng AQS/park nên biểu diễn WAITING/TIMED_WAITING. Cần xem blocker `...Sync` và owner.

**Câu 3.** Thread gọi `Object.wait()` bên trong `synchronized(lock)`. Nó có giữ `lock` trong khi đợi không?

**Đáp án:** Không, `wait()` nhả monitor của đúng object gọi wait trong thời gian đợi và reacquire trước khi trả về. Nó có thể vẫn giữ các monitor khác.

**Câu 4.** `Condition.await()` có thể được thay bằng `LockSupport.park()` mà giữ nguyên behavior không?

**Đáp án:** Không. Condition await nhả associated lock và reacquire; park chỉ chờ permit/interrupt/spurious và không nhả lock. Thay thẳng có thể khiến producer không bao giờ lấy được khóa để signal.

**Câu 5.** Producer gọi `unpark(consumer)` trước khi consumer gọi park. Điều gì xảy ra?

**Đáp án:** `unpark` có thể làm permit khả dụng, lần park tiếp theo tiêu thụ permit rồi trả về ngay; không tích lũy nhiều permit. Vẫn cần state/predicate vì có thể có spurious return hoặc permit bị chỗ khác tiêu thụ.

**Câu 6.** Một thread `WAITING` ở `ConditionObject.await` nhưng `getLockOwnerId() == -1`. Có nghĩa không có bug?

**Đáp án:** Không. Waiter đang chờ condition signal, object chờ có thể không có owner kiểu mutex. Cần tìm producer/predicate/signal path và khả năng tiến triển.

**Câu 7.** `notifyAll` đã được gọi nhưng waiter không chạy ngay. Vì sao?

**Đáp án:** Signaling thread có thể vẫn giữ monitor; waiter phải reacquire mới trở về `wait()`. Ngoài ra scheduling và predicate có thể khiến nó tiếp tục chờ.

**Câu 8.** Có 100 threads `BLOCKED` cùng một monitor ID, một owner đang chờ DB. Gọi đây là “100 deadlocks” được không?

**Đáp án:** Không. Đây có thể là một lock convoy sau owner giữ critical section quá lâu. Muốn gọi deadlock cần xác minh chu trình phụ thuộc không tiến triển; còn phải xem DB và source code.

**Câu 9.** `findDeadlockedThreads()` trả `null` trong lúc service treo. Nên kết luận?

**Đáp án:** Chưa tìm thấy cycles được detector hỗ trợ trong snapshot. Service vẫn có thể treo do missed signal, executor starvation, I/O hoặc liveness failures khác.

**Câu 10.** `getBlockedTime()` trả `-1`. Có phải JVM không có monitor contention?

**Đáp án:** Không. Có thể contention monitoring chưa bật/không hỗ trợ. `-1` không đồng nghĩa 0 ms. Xem support/configuration và chỉ bật monitoring nếu được phép.

**Câu 11.** Một thread bị interrupt khi park, sau đó vẫn gọi park liên tục mà không xử lý flag. Rủi ro gì?

**Đáp án:** Những lần park tiếp theo có thể trả ngay vì interrupted status, gây busy loop. Phải kiểm tra cancellation/interrupt policy cùng predicate.

**Câu 12.** Vì sao thread dump một lần chưa đủ nói owner giữ khóa 30 giây?

**Đáp án:** Snapshot chỉ cho thấy một thời điểm. Cần nhiều snapshots, timestamps/JVM instance và instrumentation về lock hold/wait duration hoặc JFR events.

## Tài liệu tham khảo

- [Java SE 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): state, lock owner, waiting object, monitors và ownable synchronizers.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread dumps, contention monitoring và deadlock APIs.
- [Java SE 21 — Object](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): `wait`, `notify`, `notifyAll`, monitor ownership, spurious wakeup.
- [Java SE 21 — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock ownership, timed/interruptible acquisition, queue instrumentation, fairness.
- [Java SE 21 — Condition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html): await/release/reacquire, signals, independent condition queues.
- [Java SE 21 — LockSupport](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): permit, park/unpark, blocker, interrupt và spurious wakeups.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print` và các options theo JDK.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): đặc trưng virtual threads và giới hạn công cụ quan sát theo release.

**Ghi nhớ:** khi chẩn đoán đồng bộ Java, đừng hỏi mỗi “thread đang WAITING hay BLOCKED?”. Hãy hỏi **đang chờ monitor hay chờ signal/permit? đang giữ lock nào? bên nào có thể làm điều kiện trở thành true?** `Object.wait` và `Condition.await` nhả **đúng** khóa liên quan trong lúc đợi; `LockSupport.park` không nhả khóa; `ReentrantLock` contention thường hiện parking; `synchronized` contention thường hiện BLOCKED. **Ghép state + stack + lock identity + owner/predicate + thời gian** mới đủ phân biệt contention, missed signal, starvation và deadlock.