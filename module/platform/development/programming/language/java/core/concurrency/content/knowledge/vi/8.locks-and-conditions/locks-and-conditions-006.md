# Condition await(), signal(), signalAll() trong Java Concurrency

> **Ngữ cảnh:** Locks & Conditions của Java SE, tập trung vào `java.util.concurrent.locks.Condition`, cách phối hợp thread với `ReentrantLock`, trạng thái điều kiện (*predicate*), giao thức chờ/thông báo, interrupt, timeout và các bảo đảm Java Memory Model. Bài không sử dụng API concurrency riêng của Spring.

## 1. Bài toán: cần đợi một trạng thái, không chỉ lấy được khóa

Một **Lock** giúp các thread thay nhau vào critical section, nhưng không trả lời trực tiếp câu hỏi “đã có dữ liệu chưa?”, “buffer còn chỗ không?” hoặc “công việc đã được mở khóa logic chưa?”. Một thread có thể lấy được lock mà **điều kiện nghiệp vụ chưa đúng**. Nếu giữ lock và liên tục kiểm tra trong vòng lặp, thread khác không vào được để thay đổi trạng thái; nếu nhả lock rồi `Thread.sleep()`, việc phát hiện thay đổi bị trễ và không có một giao thức thông báo đáng tin.

`Condition` là một cơ chế *condition queue / wait set* gắn với `Lock`. Nó cho phép thread:

1. **Nắm lock**, kiểm tra trạng thái được bảo vệ.
2. Nếu predicate chưa đúng, gọi `await()` để **nhả lock và chờ**.
3. Thread khác lấy lock, **thay đổi trạng thái** rồi gọi `signal()` hoặc `signalAll()`.
4. Waiter thức dậy, **phải lấy lại lock** và kiểm tra predicate lần nữa trước khi hành động.

**Ý quan trọng nhất:** `Condition` không chứa “giá trị đúng/sai” của điều kiện, không tự nhớ mọi lần signal, cũng không thay thế biến trạng thái. Điều kiện thực sự là **predicate do chương trình định nghĩa**, ví dụ `!queue.isEmpty()` hoặc `count < capacity`. Các lời gọi `await/signal` chỉ giúp phối hợp khi predicate đó thay đổi.

## 2. Condition thuộc Lock nào?

`Condition` được tạo thông qua `Lock.newCondition()`, thường gặp nhất là `ReentrantLock.newCondition()`:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

final class SimpleGate {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition opened = lock.newCondition();
    private boolean isOpen;

    void open() {
        lock.lock();
        try {
            isOpen = true;
            opened.signalAll();
        } finally {
            lock.unlock();
        }
    }

    void awaitOpen() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (!isOpen) {
                opened.await();
            }
        } finally {
            lock.unlock();
        }
    }
}
```

Đây là **class hoàn chỉnh có thể biên dịch** trong `SimpleGate.java`. Một thread gọi `awaitOpen()` đợi tới khi biến `isOpen` được đặt thành true; thread khác gọi `open()`. Nếu `open()` chạy **trước** `awaitOpen()`, waiter nhìn thấy predicate true dưới lock và **không cần chờ**, nên không bỏ lỡ trạng thái.

Điểm cốt lõi của đoạn code:

- `lock` bảo vệ **mọi** lần đọc/ghi `isOpen`.
- `opened` là Condition được tạo **từ chính `lock`**.
- `await()` nhả lock trong lúc chờ và lấy lại lock trước khi trả về.
- `signalAll()` báo các waiter có thể kiểm tra lại predicate; nó không tự giải phóng lock của thread gọi.
- `finally { lock.unlock(); }` bảo đảm nhả lock dù đang xử lý exception hay return.

**Một lock có thể tạo nhiều Condition khác nhau.** Ví dụ buffer có một Condition cho “không rỗng” và một Condition cho “chưa đầy”. Đây là khác biệt quan trọng so với một wait set monitor qua `Object.wait()/notifyAll()`.

## 3. Tách ba khái niệm: lock, predicate, condition queue

Giả sử có buffer một ô:

- **Lock:** bảo vệ `item` và các thao tác thay đổi `item`.
- **Predicate notEmpty:** `item != null`; consumer cần predicate này true trước khi lấy item.
- **Predicate notFull:** `item == null`; producer cần predicate này true trước khi đặt item.
- **Condition notEmpty:** nơi consumer có thể ngủ khi buffer rỗng.
- **Condition notFull:** nơi producer có thể ngủ khi buffer đầy.

Hai predicate là hai trạng thái logic đối nghịch; hai Condition là **hai hàng đợi waiter** để thông báo đúng nhóm. Bất kỳ một Condition nào cũng **không tự biết** `item` có null hay không; programmer phải sửa state rồi thông báo.

Một số lỗi đến từ việc nhầm chúng:

- Chỉ gọi `notEmpty.signal()` mà **chưa ghi item**: consumer thức dậy vẫn thấy buffer rỗng.
- Đặt item xong nhưng **không signal** khi producer/consumer liên quan đang chờ: waiter có thể ngủ vô hạn dù predicate đúng.
- Đưa consumer vào `notFull.await()`: consumer đang chờ sai event, có thể không tiến triển.
- Dùng `if` thay `while`: sau khi thức dậy, điều kiện có thể đã bị thread khác làm sai lại.
- Thay đổi `item` ngoài `lock`: predicate và signal không còn là một giao thức đồng bộ nhất quán.

## 4. `await()` làm gì với lock?

Đối với Condition do `ReentrantLock.newCondition()` tạo, thread phải **đang sở hữu ReentrantLock** trước khi gọi `await()`. Nếu không giữ lock, nó ném `IllegalMonitorStateException`.

Quá trình thường diễn ra:

```text
Thread consumer                         Thread producer
------------------------------------    ------------------------------------
lock.lock()
kiểm tra predicate: false
condition.await():
    đưa mình vào condition wait queue
    nhả lock
    chờ signal/interrupt/spurious wakeup
                                        lock.lock()
                                        cập nhật state
                                        condition.signal()
                                        ... vẫn đang giữ lock ...
                                        lock.unlock()
    cạnh tranh lấy lại lock
    lock đã được lấy lại
kiểm tra predicate bằng while
xử lý dữ liệu khi predicate true
lock.unlock()
```

**`await()` nhả lock gắn với Condition, chứ không tự nhả mọi khóa khác thread đang giữ.** Với `ReentrantLock` reentrant, implementation của `newCondition()` lưu trạng thái số lần giữ lock, nhả đầy đủ trước khi chờ, rồi khôi phục mức sở hữu khi reacquire. Nếu thread đang giữ cả lock A và B, `conditionOfA.await()` không tự giải phóng B; giữ B trong lúc chờ có thể tạo deadlock.

Khi `await()` trả về bình thường, thread **đang giữ lại lock** và chỉ khi đó mới chạy tiếp lệnh sau `await()`. Nếu bị interrupt, với `ReentrantLock.ConditionObject`, thread cũng phải giành lại lock trước khi `await()` ném `InterruptedException` theo hợp đồng triển khai. Bởi vậy, kết cấu `try/finally` bên ngoài `await()` nhả đúng lock và không tạo đường đi làm quên unlock.

### Đừng hiểu sai `WAITING` và `BLOCKED`

Trong thread dump, một thread đang chờ `Condition.await()` trên `ReentrantLock` thường được quan sát `WAITING (parking)`, hoặc `TIMED_WAITING` với phiên bản có timeout. Nó không nhất thiết là `Thread.State.BLOCKED`, vì `BLOCKED` dành cho việc đợi **intrinsic monitor**. Sau khi signal, waiter có thể còn chờ giành lại `ReentrantLock`; không hứa nó lập tức chạy.

## 5. `signal()` có ý nghĩa gì?

`condition.signal()` thông báo **một waiter** đang chờ trên Condition tương ứng. Với Condition của `ReentrantLock`, một waiter đủ điều kiện được chuyển từ condition queue để **tranh lấy lại associated lock**.

Ví dụ:

```java
lock.lock();
try {
    queue.add(item);       // predicate !queue.isEmpty() trở thành true
    notEmpty.signal();     // báo một consumer đang đợi
} finally {
    lock.unlock();         // waiter chỉ tiếp tục sau khi lấy lại lock
}
```

Đây là **đoạn minh họa trong method** có `lock`, `queue`, `item` và `notEmpty` được khai báo bên ngoài.

Ba điều phải nhớ:

1. **Signal không có nghĩa giao quyền sở hữu lock ngay.** Thread gọi `signal()` vẫn giữ lock đến khi `unlock()`; waiter phải cạnh tranh reacquire sau đó.
2. **Signal không phải “đặt predicate thành true”.** Trạng thái đã được thay đổi bởi `queue.add(item)`; signal chỉ thông báo khả năng có tiến triển.
3. **Signal không phải permit lưu lại vô hạn.** Nếu chưa có waiter, gọi `signal()` không tạo “một lượt đánh thức” được nhớ cho waiter xuất hiện sau. Vì vậy waiter phải luôn **kiểm tra predicate trước**, tránh lost signal.

Với `ReentrantLock`, ConditionObject có chính sách signal theo thứ tự FIFO của những waiter trên condition queue; **thứ tự thật sự giành lại lock** vẫn phụ thuộc chính sách lock và các thread tranh khóa khác. Với interface `Condition` nói chung, không giả định mọi implementation có cùng ordering.

## 6. `signalAll()` có ý nghĩa gì?

`condition.signalAll()` thông báo **tất cả các waiter hiện có** trên **Condition đó**; mỗi waiter vẫn phải lấy lại associated lock rồi tự kiểm tra predicate.

`signalAll()` thích hợp khi:

- Thay đổi trạng thái có thể cho **nhiều waiter** cùng tiến triển, ví dụ một gate mở vĩnh viễn cho tất cả.
- Nhiều waiter đang đợi các điều kiện chi tiết khác nhau trên **cùng Condition**, không biết nên chọn waiter nào cho chính xác.
- Có chuyển trạng thái quan trọng như shutdown/cancel khiến **mọi waiter** phải thức dậy để kiểm tra một cờ chung rồi thoát.
- Bạn không thể chứng minh việc signal một waiter bất kỳ sẽ bảo đảm tiến triển của hệ thống.

Nhược điểm là **thundering herd**: nhiều waiter được đưa vào tranh cùng lock, nhưng chỉ lần lượt một thread có thể lấy lock; nhiều waiter tỉnh dậy rồi nhận predicate false và chờ lại. Nó có thể làm tăng context switching, lock contention và latency.

`signalAll()` **không tự biến một item thành N item**. Nếu chỉ thêm một phần tử vào queue, dù có đánh thức N consumer, chỉ một consumer lấy được phần tử; những người khác phải trở về `await()` qua vòng `while`.

Bảng so sánh:

| API | Đánh thức ai? | Có làm predicate đúng? | Có nhả lock của caller ngay? |
|---|---|---|---|
| `signal()` | Một waiter trên Condition tương ứng (nếu có) | Không | Không |
| `signalAll()` | Tất cả waiter của Condition tương ứng (nếu có) | Không | Không |
| `await()` | Không đánh thức waiter khác; thread hiện tại đi chờ | Không | **Có**: tạm nhả associated lock rồi reacquire trước khi trở về |
| `unlock()` | Nhả quyền sở hữu lock; có thể cho contender giành lock | Không | Có: nhả lock theo contract |

**Không có số waiter cố định nào đủ để kết luận** nên dùng `signalAll()`. Cần nhìn predicate và invariant: một update cho phép đúng một waiter tiến triển hay cho phép nhiều waiter tiến triển? Có nhiều loại waiter chung Condition không? Có shutdown hay state chuyển vĩnh viễn không?

## 7. Vì sao bắt buộc dùng `while`?

Mẫu chuẩn:

```java
lock.lock();
try {
    while (!predicate()) {
        condition.await();
    }
    performOperationWithPredicateTrue();
} finally {
    lock.unlock();
}
```

Đây là **khung method minh họa**, với `lock`, `condition`, `predicate()` và `performOperationWithPredicateTrue()` được định nghĩa ở ngữ cảnh khác, method phải khai báo/xử lý `InterruptedException`.

Có ít nhất bốn lý do cần kiểm tra lại:

1. **Spurious wakeup:** `await()` có thể trả về dù chưa có `signal()` tương ứng, theo hợp đồng `Condition`. Đây là hành vi được phép của các primitive chờ; không được dựa vào “không bao giờ xảy ra trên máy của tôi”.
2. **Cạnh tranh sau signal:** waiter được thông báo phải **reacquire lock**. Trong thời gian đó thread khác có thể giành lock và tiêu thụ dữ liệu trước; predicate trở lại false.
3. **SignalAll đánh thức nhiều waiter:** có thể chỉ một waiter thật sự đủ điều kiện và các waiter còn lại phải tiếp tục chờ.
4. **Thông báo không phải kết quả nghiệp vụ:** thay đổi state có thể không đủ để thỏa tất cả điều kiện, hoặc waiter cần kiểm tra nhiều yếu tố hơn một “đã có sự kiện”.

Dùng `if (!predicate) await()` là lỗi vì sau một lần await trả về thread có thể bước tiếp khi predicate false, gây đọc queue rỗng, ghi quá capacity hoặc vi phạm invariant.

**Cũng không được gọi `await()` vô điều kiện rồi mới kiểm tra predicate**: có thể một producer đã hoàn tất công việc và signal **trước khi** waiter bắt đầu chờ; nếu waiter vẫn đi vào await mặc dù dữ liệu đã có, có thể ngủ mãi khi không còn signal nào tiếp theo. Predicate là **nguồn sự thật**.

## 8. Producer–consumer với hai Condition: `notEmpty` và `notFull`

Một bounded buffer có hai loại thread cần chờ **hai nguyên nhân khác nhau**:

- Producer muốn đặt item khi buffer đầy ⇒ đợi `notFull`.
- Consumer muốn lấy item khi buffer rỗng ⇒ đợi `notEmpty`.

Dùng **một lock** để bảo vệ cùng state và **hai Condition** để tránh đánh thức nhầm nhóm.

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Đặt trong class BoundedBuffer<T> với capacity > 0.
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final Condition notFull = lock.newCondition();
private final Deque<T> queue = new ArrayDeque<>();
private final int capacity;

void put(T item) throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (queue.size() == capacity) {
            notFull.await();
        }
        queue.addLast(item);
        notEmpty.signal();
    } finally {
        lock.unlock();
    }
}

T take() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (queue.isEmpty()) {
            notEmpty.await();
        }
        T item = queue.removeFirst();
        notFull.signal();
        return item;
    } finally {
        lock.unlock();
    }
}
```

Đây là **đoạn code thành viên của một generic class**, **không phải chương trình độc lập**: cần constructor khởi tạo `capacity` và quy định `item != null` nếu chọn `ArrayDeque`, vì nó không chấp nhận null.

Suy luận từng thao tác:

- Khi queue đầy, producer có lock nhưng không thể thêm; `notFull.await()` tạm **nhả lock**, để consumer có thể vào `take()` và lấy bớt item.
- Khi consumer lấy một item, trạng thái “còn chỗ” có thể đúng nên gọi `notFull.signal()`.
- Khi queue rỗng, consumer gọi `notEmpty.await()` và nhả lock; producer có thể đặt item.
- Khi producer đặt một item, trạng thái “có item” có thể đúng nên gọi `notEmpty.signal()`.
- Mỗi bước kiểm tra predicate, thay đổi queue và gửi signal đều nằm dưới **cùng `lock`**, tránh race giữa kiểm tra và chờ.
- `signal()` ở đây thông thường hợp lý vì mỗi lần `put/take` thay đổi khả năng tiến triển cho ít nhất một waiter ở nhóm đối diện; khi thiết kế thay đổi nhiều item, shutdown hoặc có predicate phức tạp, quyết định signal vs signalAll phải đánh giá lại.

Trong ứng dụng Java SE, nếu chỉ cần bounded producer-consumer queue, **`ArrayBlockingQueue` hoặc `LinkedBlockingQueue`** thường thích hợp và đã được kiểm chứng rộng rãi. Tự xây buffer giúp hiểu Condition, nhưng cũng mở thêm lỗi liên quan timeout, cancellation, capacity, shutdown và exception safety.

## 9. Ví dụ Java 17+ chạy độc lập: await, signal và signalAll

Chương trình này minh họa hai kiểu phối hợp:

- **OneSlot** là buffer một ô. `put` chờ `notFull` khi ô đang có item, `take` chờ `notEmpty` khi ô trống; mỗi phía dùng `signal()` để thông báo phía đối diện.
- **Gate** có predicate `isOpen`. Khi mở, tất cả waiter đều có thể đi tiếp, nên `signalAll()` hợp lý.
- `Future.get()` giúp main chờ kết quả, tránh dựa vào `Thread.sleep()` để đoán worker đã hoàn thành.

Tạo tệp **`ConditionLab.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionLab {
    static final class OneSlot {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private String item;

        void put(String value) throws InterruptedException {
            if (value == null) throw new IllegalArgumentException("null not allowed");
            lock.lockInterruptibly();
            try {
                while (item != null) notFull.await();
                item = value;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        String take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (item == null) notEmpty.await();
                String result = item;
                item = null;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }
    }

    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition opened = lock.newCondition();
        private boolean isOpen;

        void awaitOpen() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (!isOpen) opened.await();
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

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            OneSlot slot = new OneSlot();
            Future<String> received =
                pool.submit(() -> slot.take() + "," + slot.take());
            slot.put("alpha");
            slot.put("beta");
            System.out.println("received=" + received.get());

            Gate gate = new Gate();
            Future<Boolean> first = pool.submit(() -> {
                gate.awaitOpen();
                return true;
            });
            Future<Boolean> second = pool.submit(() -> {
                gate.awaitOpen();
                return true;
            });
            gate.open();
            System.out.println("gate=" + first.get() + "," + second.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa source:

```bash
javac --release 17 ConditionLab.java
java ConditionLab
```

**Stdout đã xác minh:**

```text
received=alpha,beta
gate=true,true
```

### Giải thích tính đúng đắn của ví dụ

1. `OneSlot.item` được đọc/ghi chỉ khi đang giữ `OneSlot.lock`. `null` đại diện ô trống; input null bị từ chối để không nhầm với trạng thái “empty”.
2. Hai lệnh `put("alpha")` và `put("beta")` được main gọi nối tiếp. Nếu slot còn đầy khi put thứ hai bắt đầu, main chờ `notFull.await()`, nhả lock cho consumer lấy `alpha` rồi signal. Thứ tự dữ liệu nhận luôn là `alpha,beta`.
3. Consumer nhận bằng hai lần `take()`. Nếu chạy trước producer, consumer đợi `notEmpty`. Nếu producer chạy trước, consumer kiểm tra predicate rồi lấy ngay. Không phụ thuộc một signal đã xảy ra trước khi có waiter.
4. `received.get()` bảo đảm consumer task đã hoàn thành và trả chuỗi; do vậy dòng đầu luôn `received=alpha,beta` khi chương trình hoàn thành bình thường.
5. Hai task ở phần Gate có thể đi vào `awaitOpen()` trước hoặc sau khi `gate.open()`. Nếu đợi trước, `signalAll()` thông báo cả hai. Nếu vào sau, chúng quan sát `isOpen == true` và **không cần đợi**.
6. `Gate.opened.signalAll()` không làm cả hai waiter chạy song song trong critical section; mỗi waiter phải lấy lại lock trước khi return từ `await()`. Sau đó từng task trả `true`.
7. `first.get()`, `second.get()` tạo ranh giới hoàn tất trước khi main in dòng hai, nên kết quả được quyết định bởi predicate, không do lịch CPU.

**Phạm vi demo:** đây là ví dụ educational, không triển khai close/shutdown semantics cho buffer, timeout công việc, telemetry hoặc error propagation theo application contract. Pool gồm hai worker để có thể cho hai Gate waiters chạy cùng lúc; việc gate mở trước lúc cả hai thật sự await vẫn đúng, nhưng một lần chạy như vậy **không chứng minh** cả hai đã nằm trong condition queue khi `signalAll()` được gọi. Để kiểm thử trạng thái “đang chờ” chính xác hơn, cần orchestration và instrumentation thích hợp; correctness của Gate phải dựa trên predicate/lock protocol, không dựa vào giả định về scheduler.

`Future.get()` có thể ném `ExecutionException` nếu task gặp lỗi hoặc `InterruptedException` nếu caller bị interrupt; `main` trong demo khai báo `throws Exception` để tập trung vào cơ chế Condition. Ở ứng dụng thực, cần xử lý lỗi, hủy tác vụ, deadline và shutdown dứt điểm.

## 10. Signal và signalAll không thay thế state

Một **lost signal** thường xảy ra khi code tưởng rằng gọi signal là đủ, mặc dù chưa có predicate:

```java
// Đây là minh họa SAI, không phải giao thức chờ đầy đủ.
lock.lock();
try {
    condition.signal(); // không có waiter -> signal không được tích lũy
} finally {
    lock.unlock();
}

// Rất lâu sau: một thread khác gọi condition.await()
// không có predicate đã đúng để nó bỏ qua việc chờ.
```

Đây là đoạn mô tả lỗi; `lock`/`condition` được khai báo ở nơi khác và `await` phải được thực hiện khi sở hữu associated lock. Sửa bằng cách duy trì **trạng thái bền vững của điều kiện**:

```java
// Các field trong một class:
private boolean ready;
private final ReentrantLock lock = new ReentrantLock();
private final Condition changed = lock.newCondition();

void publishReady() {
    lock.lock();
    try {
        ready = true;
        changed.signalAll();
    } finally {
        lock.unlock();
    }
}

void waitUntilReady() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (!ready) {
            changed.await();
        }
    } finally {
        lock.unlock();
    }
}
```

Các phần trên là **thành viên minh họa của một class** có import `Condition`/`ReentrantLock`. Nếu signal xảy ra trước, `ready` vẫn true nên waiter tới muộn đi tiếp. Nếu waiter đến trước, nó đợi rồi kiểm tra lại `ready` sau khi được thông báo. Đây là giao thức logic, không cần signal tồn tại như permit.

**Nếu cần một permit được lưu để thread đến sau có thể tiêu thụ**, primitive như `Semaphore` có mô hình khác. `Condition` không phải semaphore hay event counter; chọn primitive theo semantics cần thiết.

## 11. Interruptible waiting: cách xử lý hủy công việc

`Condition.await()` là phương thức **có thể bị interrupt** và khai báo `throws InterruptedException`. Với `ReentrantLock.newCondition()`, khi interrupt xảy ra trong thời gian chờ, implementation có thể thoát chờ bằng `InterruptedException` và reacquire lock trước khi ném exception. Theo JavaDoc, khi exception này được ném do interrupt, **interrupt status được xóa**; caller cần quyết định propagate, hủy công việc hoặc khôi phục cờ.

Đoạn mẫu thường dùng nếu method cho phép caller xử lý:

```java
void awaitReady() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (!ready) {
            readyCondition.await();
        }
        useReadyState();
    } finally {
        lock.unlock();
    }
}
```

Đây là **method minh họa** cần các field `lock`, `ready`, `readyCondition` và method `useReadyState()` được khai báo ở class chứa nó.

- `lock.lockInterruptibly()` cho phép cả pha **đang đợi giành lock** bị hủy bằng interrupt.
- `await()` cho phép pha **đang chờ predicate** bị interrupt.
- `finally` bảo đảm release sau khi lock đã lấy; đặt `lockInterruptibly()` **trước** `try` giúp tránh unlock khi acquisition thất bại và thread chưa sở hữu lock.
- Nếu caller nhận `InterruptedException`, nó có thể propagate lên cấp cao hoặc dừng task theo chính sách ứng dụng.

Nếu code ở cuối pipeline buộc phải catch mà không thể rethrow:

```java
try {
    awaitReady();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // khôi phục flag
    return;                              // method void, dừng xử lý
}
```

Đây là **đoạn minh họa trong method void**, với `awaitReady()` là method có thể ném exception. Không được “nuốt” `InterruptedException` rồi tiếp tục vòng chờ vô hạn nếu ứng dụng mong muốn cancellation.

### `awaitUninterruptibly()`

`Condition.awaitUninterruptibly()` chờ mà không ném `InterruptedException`; interrupt có thể được ghi nhận và interrupt status được giữ/khôi phục khi trả về theo semantics API. Nó **vẫn có thể thức dậy giả**, nên luôn dùng vòng kiểm tra predicate. Không nên mặc định chọn nó cho ứng dụng cần graceful shutdown/cancel vì sẽ khó yêu cầu một waiter dừng nhanh.

### Vì sao không thể coi interrupt là signal nghiệp vụ?

Interrupt là cơ chế phối hợp hủy/ngắt thread; signal là thông báo rằng predicate **có thể** đã thay đổi. Một waiter có thể bị interrupt khi đang chờ hoặc đang reacquire; contract của `Condition` cho phép implementation ưu tiên phản ứng interrupt trong một số cuộc đua với signal (đồng thời phải xử lý việc chuyển signal theo ràng buộc thích hợp). Đừng giả định cả hai sự kiện luôn được xử lý theo một thứ tự duy nhất do mã nguồn quy định. Hãy xây API rõ ràng về cancellation, trạng thái và retry.

## 12. Các biến thể timed await và deadline

`Condition` có nhiều overload cho những yêu cầu thời gian:

| API | Hành vi chính | Giá trị trả về |
|---|---|---|
| `await()` | Chờ có thể interrupt, không yêu cầu deadline | `void` |
| `awaitUninterruptibly()` | Chờ không ném InterruptedException | `void` |
| `await(long time, TimeUnit unit)` | Chờ tối đa thời lượng tương đối | `boolean`: thường `false` nếu hết thời gian trước signal |
| `awaitNanos(long nanosTimeout)` | Chờ theo nanoseconds, dùng cho vòng retry | `long`: ước lượng số nanoseconds còn lại; ≤ 0 nghĩa thời gian đã hết |
| `awaitUntil(Date deadline)` | Đợi đến mốc giờ tuyệt đối | `boolean`: false nếu deadline đã qua trước khi được thông báo |

Trong **mọi** timed await, predicate vẫn phải được kiểm tra trong `while`. Đừng suy ra predicate true chỉ vì `await(time, unit)` trả true: return có thể chịu tác động của signal/spurious wakeup, và thread khác có thể thay đổi predicate trong lúc waiter reacquire lock.

### Mẫu timeout dùng `awaitNanos()`

```java
import java.util.concurrent.TimeUnit;

// Method của class chứa lock, notEmpty, queue:
boolean awaitNotEmpty(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (queue.isEmpty()) {
            if (remaining <= 0L) return false;
            remaining = notEmpty.awaitNanos(remaining);
        }
        return true; // queue đang không rỗng khi còn giữ lock
    } finally {
        lock.unlock();
    }
}
```

Đây là **method minh họa trong class**; `lock` và `notEmpty` được tạo bởi cùng ReentrantLock, `queue` là collection được bảo vệ bởi lock đó. Kết quả true ở đây chỉ là snapshot predicate **trước khi nhả lock**; caller khác lấy lock về sau có thể thấy queue đã rỗng, vì thế nếu muốn lấy item, thường phải **thực hiện việc lấy ngay trong cùng critical section** thay vì trả boolean rồi gọi một method khác.

Quan trọng:

- Dùng giá trị `remaining` do `awaitNanos()` trả về để tránh **reset toàn bộ timeout** sau mỗi spurious wakeup.
- Nếu dùng `await(time, unit)` bên trong vòng lặp mà lần nào cũng truyền đủ timeout, tổng thời gian chờ có thể kéo dài hơn deadline mong muốn.
- Với deadline tuyệt đối dựa trên `Date`/wall-clock, cần quan tâm clock adjustment; deadline tương đối đo khoảng thời gian thường phù hợp với monotonic `System.nanoTime()`.
- Timeout là **giới hạn yêu cầu chờ** chứ không phải cam kết thread được scheduler chạy chính xác tại mốc đó.
- Trong phiên bản timed của một bounded buffer, phải trả về “không thêm được/không lấy được” theo contract khi timeout, nhưng **không** được thay đổi state nửa chừng.

## 13. Phân biệt `Condition` và `Object.wait/notify`

Hai cơ chế có ý tưởng tương đồng nhưng có **khóa gắn kèm và API khác nhau**:

| Thuộc tính | `Object.wait()/notify()/notifyAll()` | `Condition.await()/signal()/signalAll()` |
|---|---|---|
| Gắn với | Intrinsic monitor của object | Một `Lock`, thường là `ReentrantLock` |
| Cách sở hữu trước khi wait/signal | Phải đang trong `synchronized(object)` tương ứng | Với `ReentrantLock.newCondition()`, phải giữ associated lock |
| Chờ | `object.wait()` | `condition.await()` |
| Báo một waiter | `object.notify()` | `condition.signal()` |
| Báo mọi waiter | `object.notifyAll()` | `condition.signalAll()` |
| Phân nhóm waiter | Một wait set cho mỗi object monitor | Có thể tạo **nhiều Condition riêng** từ cùng một Lock |
| Khi chờ | Tạm nhả monitor của chính object đó | Tạm nhả lock gắn với Condition |
| Thức dậy | Phải reacquire monitor trước khi wait trả | Phải reacquire associated lock trước khi await trả |
| Interrupt/timeout | Có overload tương ứng | Có nhiều overload, `awaitNanos` và `awaitUninterruptibly` |
| Typical state | `WAITING (on object monitor)` | `WAITING (parking)` tùy JVM/implementation |

**Không hoán đổi lẫn nhau:** `condition.await()` không thay bằng `monitor.wait()` chỉ vì cùng nhìn thấy tên `lock`. Một `ReentrantLock` object không phải monitor đang được sở hữu khi bạn gọi `lock.lock()`; gọi `lock.wait()` khi không đồng bộ trên *intrinsic monitor* của object `lock` vẫn là sai.

`Condition` là interface, triển khai khác có thể quy định semantics bổ sung; bảng mô tả trường hợp chuẩn của `ReentrantLock.newCondition()`. Khi cần fairness/order cụ thể hoặc interrupt semantics chính xác, đọc JavaDoc của implementation.

## 14. Các lỗi phổ biến phải tránh

### 14.1. Gọi await/signal mà chưa giữ associated lock

```java
ReentrantLock lock = new ReentrantLock();
Condition changed = lock.newCondition();

// Sai với Condition do ReentrantLock tạo:
changed.signal();
changed.await();
```

Đoạn là **minh họa lỗi**, không phải chương trình độc lập; `await()` còn yêu cầu xử lý/khai báo `InterruptedException`. Với `ReentrantLock`, cả hai lời gọi khi không sở hữu lock sẽ ném `IllegalMonitorStateException`. Mẫu đúng:

```java
lock.lock();
try {
    changed.signalAll();
} finally {
    lock.unlock();
}
```

Đoạn trên giả định `lock`/`changed` đã tồn tại trong cùng method/class.

### 14.2. Gọi await trong `if`

```java
if (queue.isEmpty()) {
    notEmpty.await();
}
T item = queue.removeFirst(); // có thể rỗng sau spurious wakeup/reacquire
```

Đây là **đoạn mô tả sai** trong critical section của generic class có `queue`, `notEmpty`, `T`. Sửa bằng `while (queue.isEmpty()) notEmpty.await();`; với nhiều consumer, một signal hoặc signalAll không bảo đảm người đang chạy vẫn thấy item.

### 14.3. Signal trước khi cập nhật predicate

```java
// Minh họa một thứ tự dễ gây hiểu sai, nếu điều kiện phải từ false sang true:
lock.lock();
try {
    condition.signal();
    // đổi state sau đó nhưng vẫn giữ lock...
    ready = true;
} finally {
    lock.unlock();
}
```

Đây là **đoạn code minh họa**. Với cùng lock, waiter chưa reacquire được cho đến unlock, nên thứ tự này **không nhất thiết sai về correctness** nếu predicate cuối đã đúng và không có ngoại lệ/nhánh kết thúc bất thường. Tuy nhiên, cách viết rõ ràng và ít rủi ro hơn là **cập nhật predicate trước, signal sau**, vì nó gắn thông báo với sự thay đổi đã thực hiện và thuận lợi khi code lớn hơn. Lỗi thật sự là **không cập nhật predicate**, cập nhật ngoài khóa, hoặc có control flow khiến signal không đi kèm trạng thái hợp lệ.

### 14.4. Lạm dụng `signalAll()`

Một producer thêm đúng một item nhưng đánh thức hàng nghìn consumer: các consumer cùng cạnh tranh lock, phần lớn thấy queue rỗng rồi await lại. Có thể dùng `signal()` nếu có thể chứng minh thông báo một waiter đủ để tiến triển. Ngược lại, dùng `signal()` cho shutdown nhiều waiter mà tất cả phải thoát là thiếu; lúc này `signalAll()` và kiểm tra cờ shutdown cần thiết.

### 14.5. Nhiều Condition nhưng đợi/signal nhầm queue

Consumer đang đợi `notEmpty` nhưng producer chỉ signal `notFull` sẽ không đánh thức consumer. Đặt tên Condition theo **predicate waiter chờ**, không chỉ theo tên method gọi signal; viết test cho buffer rỗng/đầy, nhiều producer/consumer, interrupt và shutdown.

### 14.6. Quên `finally` hoặc unlock quá sớm

`ReentrantLock` không tự nhả khi method ném exception như một scope `synchronized`; phải viết `lock.lock(); try { ... } finally { lock.unlock(); }`. Nhưng cũng không được `unlock()` nếu `lockInterruptibly()` hoặc `tryLock` chưa lấy thành công. Chỉ thiết lập `try/finally` cho đoạn thực sự sở hữu lock.

### 14.7. Giữ thêm khóa khác trong lúc await

`conditionOfA.await()` nhả A nhưng không nhả B. Nếu thread khác cần B để báo điều kiện trên A, hai phía có thể deadlock. Tránh nested locks nếu không cần; nếu cần, quy ước thứ tự lấy và nhả rõ ràng, không đợi event trong lúc giữ các tài nguyên làm event không thể xảy ra.

### 14.8. Sử dụng `Thread.sleep()` làm chờ điều kiện

Sleep không nhả lock đang giữ, không tạo signal và không bảo đảm predicate sẽ đổi đúng trong khoảng thời gian chọn. Dùng `await`, queue, latch hoặc future phù hợp với ý nghĩa nghiệp vụ.

### 14.9. Đồng nhất signal với việc waiter đã hoàn thành

`signalAll()` chỉ đưa waiter tới cơ hội tiến triển. Nếu caller cần tất cả waiter **xử lý xong** trước khi đi tiếp, phải sử dụng `Future.get()`, `CountDownLatch`, `Phaser` hoặc completion protocol riêng, không được suy từ một lần signal.

## 15. Liveness, fairness và hiệu năng

**Mutual exclusion** đảm bảo chỉ một thread giữ ReentrantLock tại một thời điểm. Nó không bảo đảm thread cụ thể sẽ giành lock sau signal trong một thời gian cố định.

- Với **non-fair ReentrantLock** (mặc định), thread mới tới có thể giành lock trước một waiter đã được signal. Chọn fair lock có thể giúp ưu tiên những thread chờ lâu trong cơ chế khóa có contention, nhưng không bảo đảm scheduler fairness tuyệt đối; `tryLock()` không timeout có semantics barging cần chú ý.
- Với `ReentrantLock.ConditionObject`, signal chuyển waiter từ condition queue sang lock queue, nhưng **waiter chưa chạy được** cho tới khi reacquire thành công.
- `signalAll()` có thể tạo thundering herd, tăng lock contention.
- Nếu predicate không bao giờ có thể đúng, `await()` có thể chờ mãi dù không có data race. Cần thiết kế shutdown, timeout và error propagation.
- Nếu thread đang sở hữu lock gọi I/O chậm hoặc xử lý CPU dài sau `signal()`, waiter phải chờ khóa lâu hơn. Nên giữ critical section đủ nhỏ để bảo vệ invariant, nhưng không tách những bước cần atomic.
- Với queue bounded, producer nhanh hơn consumer tạo backpressure và tăng wait time. Phân biệt chờ predicate có chủ đích với starvation do scheduler hoặc bottleneck ở lock.

Không phải bài toán nào cũng cần tự viết Condition. Với pipeline producer-consumer, `BlockingQueue` cung cấp giao thức chờ tiêu chuẩn, capacity và memory consistency đã được đóng gói. Với “một lần mở gate”, `CountDownLatch` có thể phù hợp hơn. Với số permits, `Semaphore` phù hợp hơn. `Condition` đặc biệt hữu ích khi bạn **đã có shared invariant dưới Lock** và cần những nhóm chờ phụ thuộc predicate.

## 16. Chẩn đoán bằng thread dump và JFR

Khi chương trình bị treo hoặc có độ trễ lớn, cần tìm:

1. Thread nào **giữ ReentrantLock**, thread nào đang đợi Condition nào?
2. Predicate nào còn false? Ai có trách nhiệm làm nó true?
3. Thread đổi predicate có **signal đúng Condition** không?
4. Waiter có giữ thêm lock khác, khiến producer không tiến triển được không?
5. Có shutdown/cancel mà không signalAll để wake những thread chờ dài hạn không?
6. Có timeout bị reset sau mỗi wakeup không?
7. Có exception khiến thread quên unlock hoặc mất signal cần thiết không?

Có thể lấy một số thread dump:

```bash
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng PID Java process đang chạy. Với `Condition.await()` trên `ReentrantLock`, stack có thể đi qua `AbstractQueuedSynchronizer.ConditionObject.await` và `LockSupport.park`. Đó thường là `WAITING (parking)`, không phải `WAITING (on object monitor)` của `Object.wait()`.

JFR (khi JVM hỗ trợ) có thể cung cấp sự kiện `jdk.ThreadPark` và thông tin về thời gian/stack thread đợi:

```bash
jcmd <PID> JFR.start name=condition-profile settings=profile duration=60s filename=conditions.jfr
jfr summary conditions.jfr
jfr print --events jdk.ThreadPark conditions.jfr
```

Không có event không nhất thiết chứng minh không có chờ: recording quá ngắn, event threshold, profiling settings hoặc workload không kích hoạt có thể làm không ghi nhận được. Thread dump/JFR là bằng chứng quan sát, **không thay thế kiểm chứng giao thức predicate và lock**.

## 17. Checklist review code dùng Condition

Khi kiểm tra một implementation dùng `Condition`, nên trả lời rõ:

1. **Lock được chia sẻ thế nào?** Các reader/writer của state có dùng đúng một ReentrantLock?
2. **Predicate là gì?** Có phát biểu bằng một biểu thức logic kiểm tra dưới lock hay không?
3. **Waiter luôn dùng while?** Có kiểm tra lại sau signal, spurious wakeup và cạnh tranh không?
4. **await được gọi trong khi sở hữu lock?** Associated lock có được tạm nhả trong khi chờ không?
5. **State được cập nhật trước signal?** Tất cả lần đọc/ghi predicate có nằm trong cùng critical section?
6. **signal hay signalAll?** Việc thức dậy một/nhiều waiter có phù hợp với thay đổi state và yêu cầu shutdown?
7. **Unlock luôn ở finally?** Có đường exception/cancel bỏ quên unlock hoặc unlock khi chưa acquire không?
8. **Interrupt policy?** API propagate `InterruptedException`, restore flag hay hỗ trợ cancellation thế nào?
9. **Timeout có deadline đúng?** Spurious wakeup có khiến thời gian chờ bị kéo dài không?
10. **Có lock khác đang giữ?** Chờ condition có thể chặn thread chịu trách nhiệm làm predicate true?
11. **Hệ thống kiểm tra completion riêng?** Signal không được dùng thay thế `Future.get()` hoặc latch khi cần xác nhận công việc hoàn tất.
12. **Có sẵn primitive cấp cao phù hợp hơn?** Không viết lại BlockingQueue/CountDownLatch nếu không cần custom predicate.
13. **Đã test race/close/interrupt?** Không chỉ test một lịch chạy thành công; stress với nhiều producer, consumer, timeout và shutdown.

## 18. Tự kiểm tra kiến thức và đáp án

**Câu 1.** Thread A gọi `condition.await()` khi đang giữ associated `ReentrantLock`. Nó còn giữ lock trong lúc chờ không?  
**Đáp án:** Không. Với Condition của ReentrantLock, await nhả lock tương ứng trong lúc chờ và reacquire trước khi trả về/hoàn tất qua đường interrupt.

**Câu 2.** Thread B gọi `signal()` rồi vẫn giữ lock thêm 5 giây. A có thể tiếp tục vào critical section ngay sau signal không?  
**Đáp án:** Không. A cần lấy lại lock. Trong lúc B chưa unlock, A chưa thể tiếp tục code được bảo vệ.

**Câu 3.** Producer signal trước khi consumer đến; có bị mất thông báo không?  
**Đáp án:** Signal không được giữ thành permit, nên thông báo đơn lẻ có thể không có waiter nhận. Giao thức đúng dựa trên **predicate được lưu**: consumer đến sau kiểm tra state true và không gọi await.

**Câu 4.** Vì sao `if (!ready) condition.await()` không an toàn?  
**Đáp án:** Await có thể trả sau spurious wakeup hoặc predicate đổi lại trước khi reacquire; dùng `while (!ready)`.

**Câu 5.** Khi thêm một item vào buffer rỗng, nên `signal()` hay `signalAll()`?  
**Đáp án:** Nếu consumer đều chờ cùng predicate “có item” và chỉ một item được thêm, `signal()` thường đủ; nhiều predicate cùng Condition, trạng thái mở rộng hoặc shutdown có thể đòi signalAll. Cần xét invariant và progress guarantee cụ thể.

**Câu 6.** `signalAll()` có làm tất cả waiter chạy đồng thời bên trong vùng khóa không?  
**Đáp án:** Không. Chúng cạnh tranh reacquire lock; chỉ một thread sở hữu lock tại một thời điểm.

**Câu 7.** `notFull.await()` có thể thay bằng `notEmpty.await()` trong producer được không?  
**Đáp án:** Không nếu hai Condition tương ứng với các nhóm waiter khác nhau. Producer phải chờ điều kiện “còn chỗ”, consumer mới chờ “có item”.

**Câu 8.** Khi có `InterruptedException` từ `await()`, có thể bỏ qua rồi tiếp tục đợi vô hạn không?  
**Đáp án:** Không nên nếu thread cần hỗ trợ hủy. Propagate exception, hủy task hoặc khôi phục interrupt flag nếu catch ở biên thích hợp.

**Câu 9.** Với vòng lặp timeout, tại sao cần cập nhật thời gian còn lại qua `awaitNanos()`?  
**Đáp án:** Vì có thể thức dậy nhiều lần mà predicate vẫn sai. Nếu reset full timeout mỗi lần, tổng thời gian có thể vượt deadline yêu cầu.

**Câu 10.** Thread giữ lock B rồi `conditionOfA.await()`; await có tự nhả B không?  
**Đáp án:** Không. Nó chỉ nhả associated lock A; B vẫn đang giữ, có thể khiến producer kẹt và gây deadlock.

**Câu 11.** `Condition` có tự giữ giá trị `ready` không?  
**Đáp án:** Không. `Condition` chỉ quản lý chờ/thông báo; boolean `ready` hoặc predicate khác phải được quản lý dưới lock.

**Câu 12.** Nếu tất cả chỉ cần đợi một sự kiện “hoàn tất một lần”, có bắt buộc dùng Condition không?  
**Đáp án:** Không. `CountDownLatch` thường diễn tả điều này rõ hơn. Condition hữu ích khi cần chờ các predicate tùy biến dưới cùng lock.

## 19. Tài liệu tham khảo

- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): API `await()`, `awaitNanos()`, `awaitUntil()`, `signal()`, `signalAll()`, spurious wakeup và interruption.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): `newCondition()`, associated lock, fairness và ownership.
- [Java SE 17 — Lock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): `lock()`, `lockInterruptibly()`, `unlock()` và memory synchronization.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): chờ producer-consumer, API bounded queue và memory consistency.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot gate và quy tắc chờ completion.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): chờ kết quả task và memory consistency.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model và happens-before.

**Ghi nhớ cuối cùng:** **predicate quyết định được đi tiếp hay không; lock bảo vệ predicate; `await()` nhả rồi lấy lại lock; `signal()`/`signalAll()` chỉ thông báo cơ hội kiểm tra lại.** Viết `while`, giữ đúng associated lock, cập nhật state trước khi signal, dùng `finally` để unlock và thiết kế cancellation/timeout rõ ràng. Khi những điều này được chứng minh, lịch chạy có thể không xác định mà chương trình vẫn đúng.