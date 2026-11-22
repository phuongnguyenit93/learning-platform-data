# Chi phí, độ phức tạp và tiêu chí chọn loại lock trong Java

Trong Java Concurrency, câu hỏi “dùng `synchronized`, `ReentrantLock`, `ReadWriteLock` hay `StampedLock`?” không thể trả lời chỉ bằng việc đếm bao nhiêu thread truy cập dữ liệu. Mỗi cơ chế đưa ra một hợp đồng về **mutual exclusion**, **memory visibility**, **cách chờ và hủy**, **mức tranh chấp**, **tính công bằng**, và **độ khó chứng minh chương trình đúng**. Một lock phức tạp hơn không đồng nghĩa nhanh hơn; một lock đơn giản không mặc nhiên là nút thắt.

Cách chọn tốt là xác định **invariant cần bảo vệ**, **sự phối hợp phải diễn ra trong một critical section**, **chi phí nếu thread chờ**, rồi mới đo hiệu năng theo workload thật. Bài học này thuộc nhóm **Locks & Conditions** của **Java Concurrency nói chung**, không xét các cơ chế riêng của Spring.

## 1. Trước hết: lock giải quyết bài toán gì?

Khi nhiều thread cùng đọc/ghi một trạng thái mutable, việc bảo vệ đúng cần hai phương diện:

- **Mutual exclusion / atomicity:** một nhóm bước liên quan invariant diễn ra không bị thread khác chen vào. Ví dụ kiểm tra số dư rồi trừ tiền phải ở cùng transaction logic.
- **Happens-before / visibility:** lần unlock trên cùng monitor xảy ra trước lần lock tiếp theo; các `Lock` tiêu chuẩn có memory semantics tương ứng. Reader tuân thủ cùng protocol mới có cơ sở quan sát cập nhật đã công bố.

Ví dụ:

~~~java
private final Object lock = new Object();
private int available = 100;
private int reserved;

boolean reserve() {
    synchronized (lock) {
        if (available == 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    }
}
~~~

Đây là **mảnh mã của một class**, không phải chương trình chạy độc lập. Invariant ở đây là `available >= 0`, `reserved >= 0` và `available + reserved == 100`. Cả check, decrement và increment nằm trong cùng critical section.

Muốn đọc hai trường **như một snapshot**, reader cũng phải lấy cùng lock và đọc chúng trong một lần sở hữu. Hai getter `synchronized` được gọi lần lượt có thể trả giá trị thuộc hai thời điểm khác nhau nếu một writer chen giữa các lần gọi. Chỉ dùng `volatile` cho mỗi trường không biến hai phép ghi thành một cập nhật nguyên tử.

**Điểm khởi đầu:** chọn **giao thức sở hữu dữ liệu** trước khi chọn class lock. Nếu mỗi getter hoặc callback có thể bỏ qua lock, thay `synchronized` bằng `StampedLock` không sửa được lỗi.

## 2. “Chi phí của lock” gồm những gì?

Không có một con số overhead cố định cho mọi JVM. Chi phí phụ thuộc JDK, CPU, mức tranh chấp, critical section, cache layout và cách chạy benchmark.

| Loại chi phí | Nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| **Acquire / release** | Lệnh và rào cản đồng bộ/atomic operations cần thiết để sở hữu và nhả khóa. | Benchmark path ít tranh chấp, profiler phù hợp. |
| **Contention wait** | Một contender phải đợi holder hiện tại. | Blocked time, lock profiling, thread dumps, JFR. |
| **Scheduling / wake-up** | Một thread bị park/block rồi được đánh thức và schedule lại. | p95/p99 latency, context switching, lock wait time. |
| **Cache coherence** | Nhiều core cập nhật cùng state/metadata lock, gây traffic. | Profiling/CPU counters khi có hỗ trợ. |
| **Serialization** | Critical section ngăn các operation chạy cùng lúc. | Throughput khi tăng số worker; độ dài hold time. |
| **Fairness bookkeeping** | Chính sách xếp hàng/tôn trọng thứ tự có thể làm giảm khả năng “barging” và throughput. | Benchmark fair vs nonfair trên cùng tải. |
| **Read/write coordination** | Read locks có metadata riêng; acquire/release cho mỗi reader vẫn có giá. | So sánh với mutex khi chỉ đọc một vài field. |
| **Optimistic retry** | CAS thất bại hoặc optimistic-read validation thất bại, phải làm lại công việc. | Retry rate, allocation, CPU, tail latency. |
| **Độ phức tạp lập trình** | Dễ quên `unlock()`, quên validate, nhầm condition, deadlock, invariant rải rác. | Code review, stress tests, sự cố production. |

Đừng chỉ đo nanoseconds của một `lock()` rỗng rồi suy ra hiệu năng chương trình. Một critical section dài do network I/O hoặc callback bên ngoài sẽ che khuất chi phí acquire. Ngược lại, hàng triệu phép cập nhật cực nhỏ lên một điểm chia sẻ có thể bị giới hạn bởi cache contention và số lần lấy lock.

**Thông số quan trọng nhất khi contention cao thường là thời gian giữ khóa và tần suất tranh chấp**, không phải tên API.

## 3. Những câu hỏi phải trả lời trước khi chọn

1. **Trạng thái nào phải nhất quán?** Một biến đơn, nhiều field trong cùng invariant, hay nhiều object?
2. **Tỷ lệ đọc/ghi và độ dài thao tác?** Đọc chỉ lấy hai field, hay truy vấn dữ liệu lớn? Ghi thường xuyên đến mức nào?
3. **Số contender thực sự?** Thread hiện hữu không có nghĩa tất cả đều cùng lấy một lock.
4. **Có phải đợi điều kiện?** Cần `await`/`signal` nhiều điều kiện độc lập hay chỉ cập nhật state?
5. **Có deadline/cancellation ở bước lấy khóa?** Nếu cần `tryLock(timeout)` hoặc `lockInterruptibly()`, intrinsic monitor không cung cấp chính sách tương đương cho acquisition.
6. **Cần fairness không?** Fairness có thể ảnh hưởng throughput và latency nhưng không thay thế SLA.
7. **Có cần lấy nhiều lock?** Lock order, reentrancy và khả năng deadlock sẽ quyết định độ phức tạp.
8. **Đọc có cần snapshot tuyến tính hóa (linearizable) không?** Một report có thể chấp nhận gần đúng, nhưng thanh toán/quota thường không thể.
9. **Khi lỗi/interrupt, state còn hợp lệ không?** Lock được giải phóng không đồng nghĩa đã rollback.
10. **Có đo được bottleneck không?** Không tối ưu một lock chỉ vì “nghe nói” class khác nhanh hơn.

Từng yêu cầu phải xuất phát từ hợp đồng của API và invariant, không phải mẹo cấu hình ngẫu nhiên.

## 4. `synchronized`: lựa chọn nền tảng, thường nên thử đầu tiên

`synchronized` dùng **intrinsic monitor** gắn với object. JVM tự acquire khi vào khối/method và release khi thoát, kể cả khi một exception thoát ra. Đây là lựa chọn có nhiều ưu điểm:

- Mã ngắn; không thể quên `unlock()` ở nhánh return/exception thông thường.
- Reentrant: thread đang giữ monitor có thể vào lại monitor đó.
- Hợp đồng Java Memory Model rõ ràng: unlock → lock sau đó trên **cùng monitor**.
- Phù hợp để bảo vệ một nhóm field cùng invariant.
- Không cần object Lock/Condition riêng nếu chỉ cần mutual exclusion.

Những giới hạn quan trọng:

- Chờ **lấy monitor** thông qua `synchronized` không có overload timeout hoặc `lockInterruptibly()`. Thread `BLOCKED` vì monitor không tự bỏ chờ khi bị interrupt.
- Không có chính sách FIFO/fairness được bảo đảm.
- Chỉ một monitor đi cùng mỗi object; có `Object.wait()/notify()/notifyAll()`, nhưng khi nhiều predicate khác nhau, việc tổ chức condition có thể khó.
- Nếu critical section giữ khóa khi gọi I/O, `Thread.sleep()`, `Future.get()` hoặc callback chậm, contention vẫn cao. `sleep()` không nhả monitor.

### 4.1 Chọn object lock nào?

~~~java
final class Counter {
    private final Object lock = new Object();
    private long value;

    void add(long delta) {
        synchronized (lock) {
            value += delta;
        }
    }

    long get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Đây là **mảnh class minh họa**. Private lock tránh code ngoài tự `synchronized` lên cùng object và ảnh hưởng khả năng tiến triển.

Lưu ý:

- `synchronized` instance method lấy monitor của `this`.
- `static synchronized` method lấy monitor của `Class` object.
- Hai instance khác nhau có hai monitor khác nhau, nên chỉ phù hợp nếu state được bảo vệ cũng độc lập.
- Tránh khóa trên chuỗi literal/interned hoặc boxed constant có thể được chia sẻ ngoài ý muốn.
- Không nhầm lẫn `volatile` với một monitor; volatile không bảo vệ check-then-act nhiều bước.

### 4.2 Khi nào synchronized đủ tốt?

Nếu critical section ngắn, ít contention, không cần timed/interruptible acquisition và một private monitor bảo vệ toàn invariant, `synchronized` thường là quyết định **ít rủi ro và dễ review**. Chỉ chuyển sang primitive phức tạp khi có yêu cầu cụ thể hoặc đo đạc chứng minh vấn đề.

## 5. `ReentrantLock`: explicit locking đổi lấy quyền điều khiển

`java.util.concurrent.locks.ReentrantLock` cũng cung cấp mutual exclusion và memory effects như intrinsic monitor khi dùng đúng. Khác biệt nằm ở các operation mở rộng:

| Nhu cầu | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Mutual exclusion | Có | Có |
| Reentrant | Có | Có |
| Tự release khi thoát block vì exception | Có, JVM tự thực hiện | Không; **phải `unlock()` trong `finally`** |
| Thử lấy khóa ngay | Không có API tương đương trực tiếp | `tryLock()` |
| Lấy khóa có timeout | Không có trên acquisition | `tryLock(timeout, unit)` |
| Lấy khóa có thể hủy bằng interruption | Không có trên acquisition | `lockInterruptibly()` |
| Nhiều điều kiện chờ khác nhau trên cùng lock | Một wait set/monitor + `wait/notify` | Nhiều `Condition` từ `newCondition()` |
| Tùy chọn fair | Không có tham số fairness | `new ReentrantLock(true)` |
| Quan sát queue/waiters | Chủ yếu dùng JVM diagnostics | Có một số method giám sát, kết quả có tính thời điểm |

### 5.1 Quy tắc dùng đúng

~~~java
lock.lock();
try {
    // Đọc/ghi state được bảo vệ.
} finally {
    lock.unlock();
}
~~~

Đây là mảnh mã, giả định `lock` có kiểu `ReentrantLock`. Phải gọi `lock()` **trước** `try`, và chỉ `unlock()` sau khi đã lấy được khóa. Nếu `lockInterruptibly()` bị interrupt **trước khi acquire**, không được gọi `unlock()` trên thread không sở hữu khóa.

Vì lock là một object được quản lý thủ công, nguy cơ lỗi tăng nếu:

- Quên unlock trên một nhánh return/exception.
- Acquire/release sai số lần khi dùng reentrancy.
- Expose lock ra bên ngoài, khiến caller tùy ý giữ lâu.
- Giữ lock qua callback/I/O không kiểm soát.
- Gọi `Condition.await()` hoặc `signal()` mà không sở hữu lock theo hợp đồng.

**Không có bảo đảm ReentrantLock luôn nhanh hơn synchronized.** Chúng có thể có các đường tối ưu khác nhau theo JDK và workload; benchmark thực mới quyết định.

## 6. Ví dụ Java 17+: timeout khi đợi khóa

Intrinsic monitor không có timed acquisition. Ví dụ dưới dùng `ReentrantLock.tryLock(timeout)` để tránh một thread phải chờ vô hạn khi holder vẫn sở hữu khóa.

Tạo file `TimedLockChoiceDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class TimedLockChoiceDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch holderEntered = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                holderEntered.countDown();
                releaseHolder.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        }, "holder");

        Thread contender = new Thread(() -> {
            try {
                boolean acquired =
                        lock.tryLock(100, TimeUnit.MILLISECONDS);
                System.out.println("Acquired: " + acquired);
                if (acquired) {
                    try {
                        System.out.println("Critical section");
                    } finally {
                        lock.unlock();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "contender");

        holder.start();
        holderEntered.await();

        contender.start();
        contender.join();
        releaseHolder.countDown();
        holder.join();
        System.out.println("Finished");
    }
}
~~~

Lệnh Java 17+:

~~~bash
javac TimedLockChoiceDemo.java
java TimedLockChoiceDemo
~~~

Stdout trong lần chạy bình thường, không có external interruption:

~~~text
Acquired: false
Finished
~~~

**Vì sao kết quả xác định?** Holder không giải phóng lock trước khi main mở `releaseHolder`; main chỉ mở sau khi contender đã kết thúc. Contender không thể lấy được lock trong thời hạn 100 ms và trả `false`. Không có `sleep()` để phỏng đoán lịch chạy.

Điểm cần nhớ:

- Timeout chỉ giới hạn **thời gian chờ để acquire**, không giới hạn thời gian thực hiện operation sau khi đã lấy lock.
- `tryLock()` không timeout thử ngay và trả boolean; `tryLock(timeout, unit)` có thể ném `InterruptedException`.
- Không dùng nhánh timeout như một “fallback” âm thầm bỏ cập nhật tài chính; phải định nghĩa rõ kết quả API, retry và thông báo caller.
- `unlock()` nằm trong `finally` sau khi acquire thành công, không nhả khóa sai chủ sở hữu.
- Nếu application shutdown/cancellation, phải phối hợp dọn dẹp và mở những latch/condition cần thiết.

## 7. Fairness: chi phí và ngộ nhận

`new ReentrantLock(true)` yêu cầu **fairness policy**: khi nhiều thread tranh nhau, lock có xu hướng trao quyền cho thread chờ lâu hơn theo cơ chế queue của API. `new ReentrantLock(false)` (mặc định) cho phép chính sách nonfair, thường có lợi về throughput trong nhiều workload.

Nhưng fairness không đồng nghĩa:

- mọi task hoàn thành trong một deadline;
- scheduler JVM/OS cấp CPU công bằng;
- thời gian critical section nhỏ lại;
- không còn starvation ở cấp ứng dụng do I/O, pool saturation hay phụ thuộc tác vụ.

Một chi tiết dễ bỏ qua: **`tryLock()` không tham số có thể lấy lock ngay khi nó đang rảnh ngay cả trên fair ReentrantLock**, dù có thread khác đang chờ. Nếu cần tuân thủ fairness hơn trong đường thử khóa, phải hiểu sự khác biệt giữa các overload và contract cụ thể. Không mô tả fair lock như một FIFO tuyệt đối cho mọi API.

Một fair lock có thể làm giảm tính “barging”, nhưng cũng có overhead phục vụ queue và có thể giảm throughput. Hãy chọn khi có yêu cầu có căn cứ về độ công bằng chờ khóa, và đo bằng workload đại diện.

## 8. `Condition`: khi một lock bảo vệ nhiều điều kiện chờ

Nếu thread cần chờ **một predicate** của state được lock bảo vệ, cứ liên tục giải phóng/reacquire lock để poll là không hiệu quả. `Condition` gắn với `Lock` cho phép thread đang sở hữu lock gọi `await()`:

1. Tạm **nhả lock liên kết** trong lúc chờ.
2. Chờ `signal()` / `signalAll()`, interruption hoặc spurious wakeup.
3. Reacquire lock trước khi `await()` trả về bình thường.
4. Phải kiểm tra lại predicate bằng **`while`**, không dùng `if`.

Khác `Object.wait()`, một `ReentrantLock` có thể tạo **nhiều Condition** để phân biệt những nhóm waiter:

- `notEmpty`: consumer đang đợi có phần tử;
- `notFull`: producer đang đợi còn chỗ.

### 8.1 Ví dụ Java 17+: bounded one-slot buffer

Tạo file `ConditionBufferDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class ConditionBufferDemo {
    static final class OneSlotBuffer {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private Integer value;

        void put(int item) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value != null) {
                    notFull.await();
                }
                value = item;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        int take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value == null) {
                    notEmpty.await();
                }
                int item = value;
                value = null;
                notFull.signal();
                return item;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        OneSlotBuffer buffer = new OneSlotBuffer();
        CountDownLatch consumerStarted = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            consumerStarted.countDown();
            try {
                System.out.println("Taken: " + buffer.take());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        consumerStarted.await();

        buffer.put(42);
        consumer.join();
        System.out.println("Finished");
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac ConditionBufferDemo.java
java ConditionBufferDemo
~~~

Stdout khi không có interruption ngoài:

~~~text
Taken: 42
Finished
~~~

**Phân tích:**

- `OneSlotBuffer` chỉ có một chỗ, trạng thái `value == null` nghĩa buffer đang trống.
- Consumer kiểm tra predicate dưới lock; nếu trống, `notEmpty.await()` nhả lock để producer vào `put()`. Nếu producer put trước khi consumer vào, consumer thấy `value != null` và không cần đợi, nên không mất tín hiệu theo protocol này.
- Producer đặt value rồi `notEmpty.signal()` trong khi giữ lock, sau đó unlock. Consumer mới được lấy lại lock và đọc value; có quan hệ bộ nhớ đúng theo lock protocol.
- `while` bảo vệ khỏi spurious wakeup và điều kiện thay đổi trước khi waiter reacquire.
- Chương trình chỉ có một producer và một consumer để stdout đơn giản; class buffer có thể dùng trong nhiều thread nhưng vẫn phải xác định chính sách shutdown/cancellation và fairness theo yêu cầu.

**Không tự viết bounded queue như trên trong production nếu `ArrayBlockingQueue` đã đáp ứng nhu cầu.** Ví dụ nhằm giải thích Condition. Một queue tiêu chuẩn đã xử lý nhiều edge case và có API `put()`/`take()`/timed operations.

## 9. `ReadWriteLock`: cho nhiều reader vào cùng lúc

`java.util.concurrent.locks.ReadWriteLock` mô tả hai lock có vai trò:

- **Read lock:** nhiều reader có thể giữ đồng thời khi không có writer nắm write lock.
- **Write lock:** writer cần độc quyền để cập nhật state, chặn các reader/writer xung đột theo giao thức.

`ReentrantReadWriteLock` là implementation tiêu chuẩn. Nó có thể giúp workload có **đọc nhiều, ghi ít, critical section đọc đủ dài**, nhưng không phải cứ 90% read là chắc chắn tốt hơn mutex.

### 9.1 Chi phí ẩn

- Mỗi reader vẫn cần acquire/release một read lock và cập nhật/kiểm tra trạng thái phối hợp.
- Khi số thread đọc nhiều, metadata lock trở thành một điểm chia sẻ bị tranh chấp.
- Writer phải chờ reader đang giữ lock kết thúc; các reader dài làm tăng write latency.
- Fairness policy ảnh hưởng starvation/throughput, nhưng không tạo deadline bảo đảm.
- Với critical section đọc cực ngắn (chỉ hai getter), overhead read lock có thể đắt hơn một mutex đơn giản trong một số workload.

### 9.2 Upgrade/downgrade

`ReentrantReadWriteLock` hỗ trợ tình huống một thread giữ write lock rồi lấy read lock để **downgrade** có kiểm soát: acquire read khi vẫn giữ write, sau đó release write. Nhưng **read-to-write upgrade không được hỗ trợ một cách tổng quát**: giữ read lock rồi cố lấy write lock có thể dẫn đến chờ vô hạn khi không thể độc quyền.

Hãy làm: đọc/kiểm tra dưới read lock → release read lock → acquire write lock → **kiểm tra lại điều kiện** → commit. Khoảng giữa release và acquire cho phép state thay đổi; không được dựa vào điều kiện cũ như vẫn đúng.

### 9.3 Runnable Java 17+: snapshot dưới read lock

Tạo file `ReadWriteLockChoiceDemo.java`:

~~~java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class ReadWriteLockChoiceDemo {
    private static final class Inventory {
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private int available = 100;
        private int reserved;

        boolean reserve() {
            rw.writeLock().lock();
            try {
                if (available == 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            } finally {
                rw.writeLock().unlock();
            }
        }

        Snapshot snapshot() {
            rw.readLock().lock();
            try {
                return new Snapshot(available, reserved);
            } finally {
                rw.readLock().unlock();
            }
        }
    }

    private record Snapshot(int available, int reserved) {
        int total() {
            return available + reserved;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();
        Runnable task = () -> {
            for (int i = 0; i < 100; i++) {
                inventory.reserve();
            }
        };

        Thread a = new Thread(task, "a");
        Thread b = new Thread(task, "b");
        a.start();
        b.start();
        a.join();
        b.join();

        Snapshot s = inventory.snapshot();
        System.out.println("Available: " + s.available());
        System.out.println("Reserved: " + s.reserved());
        System.out.println("Total: " + s.total());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReadWriteLockChoiceDemo.java
java ReadWriteLockChoiceDemo
~~~

Stdout:

~~~text
Available: 0
Reserved: 100
Total: 100
~~~

Hai writer cạnh tranh để acquire write lock; có đúng 100 lượt reserve thành công. Snapshot được đọc trong một lần read lock, nên không lấy `available` từ phiên bản trước và `reserved` từ phiên bản sau.

Lưu ý, chương trình này **không chứng minh hiệu năng** của read/write lock: nó chủ yếu có writer và chỉ một lần snapshot ở cuối. Benchmark một workload read-heavy thật mới có ý nghĩa để quyết định thay mutex.

## 10. `StampedLock`: nhiều chế độ, thêm nhiều quy tắc

`java.util.concurrent.locks.StampedLock` hỗ trợ **write lock**, **read lock** và **optimistic read** bằng stamp. Nó không phải một `ReentrantLock` có thêm tên gọi mới.

Các đặc điểm quan trọng:

- **Không reentrant:** một method đang giữ write lock mà lại cố lấy write lock theo đường gọi lồng nhau có thể tự chặn mình.
- Stamp là token trả về từ thao tác acquire; phải dùng đúng stamp khi `unlockRead(stamp)` / `unlockWrite(stamp)`.
- `tryOptimisticRead()` trả stamp dùng để **validate** xem có writer làm mất hiệu lực snapshot trong giai đoạn đọc không; không giữ read lock.
- Nếu `validate(stamp)` thất bại, phải đọc lại dưới read lock hoặc retry theo protocol phù hợp.
- Có các operation chuyển chế độ như `tryConvertToWriteLock`, nhưng conversion có thể thất bại; cần kiểm tra kết quả và quản lý stamp/mode cực cẩn thận.
- Không cung cấp hợp đồng Condition như `ReentrantLock.newCondition()`.
- Không bảo đảm fairness; dễ phát sinh starvation nếu dùng không phù hợp với workload.

### 10.1 Optimistic read: đọc rồi validate

Mẫu minh họa:

~~~java
long stamp = lock.tryOptimisticRead();
int x = state.x;
int y = state.y;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        x = state.x;
        y = state.y;
    } finally {
        lock.unlockRead(stamp);
    }
}
return new Snapshot(x, y);
~~~

Đây là **mảnh method minh họa**, giả định `lock` là `StampedLock`, `state` chứa hai primitive field, method trả một `Snapshot` và các kiểu đã khai báo. Nó không chạy độc lập.

Điểm mấu chốt:

1. Optimistic read **có thể nhìn trạng thái trung gian trong lúc writer đang sửa**, trước khi validate.
2. Chỉ sử dụng kết quả sau **`validate(stamp) == true`**. Nếu validation không thành công, đọc lại dưới một read lock thật.
3. Không dùng các giá trị chưa validate để tạo side effect, truy cập dữ liệu ngoài biên mảng, gọi method trên reference có thể đang biến đổi hoặc đưa ra quyết định không thể đảo ngược.
4. Mẫu này đơn giản với primitive fields. Nếu object graph mutable/phức tạp, việc đọc trước validation có thể không an toàn về mặt thao tác hoặc dễ lỗi; cân nhắc dùng read lock từ đầu.
5. Việc stamp không phải “version ID” nghiệp vụ bền vững. Nó là token phục vụ protocol locking/validation.

### 10.2 Khi nào không nên dùng?

Nếu code cần reentrancy, nhiều Condition, các giá trị object mutable phức tạp, hoặc team chưa có test và review tốt cho optimistic protocol, `StampedLock` dễ làm tăng chi phí bảo trì hơn hiệu năng nhận được. Tỷ lệ optimistic validation thành công thấp khiến phải làm lại nhiều lần, vừa tốn CPU vừa phức tạp.

Dùng nó khi profiling và benchmark cho thấy **nhiều phép đọc độc lập, write hiếm và optimistic reads thường thành công**, đồng thời state được trình bày thành snapshot an toàn.

## 11. Không phải mọi bài toán đều cần lock

Một lock là giải pháp tốt cho invariant nhiều bước; với state đơn giản, primitive chuyên dụng có thể ít rủi ro hơn.

| Bài toán | Lựa chọn đáng xem xét | Vì sao |
| --- | --- | --- |
| Cờ/tín hiệu visibility đơn giản, một writer | `volatile` hoặc latch/future tùy giao thức | Không cần mutual exclusion cho nhiều bước. |
| Bộ đếm tăng độc lập cần kết quả chính xác khi đọc | `AtomicInteger`/`AtomicLong` | Atomic read-modify-write cho một biến. |
| Metrics nhiều writer, đọc tổng gần đúng trong lúc cập nhật | `LongAdder` | Phân tán contention; `sum()` không phải atomic snapshot khi concurrent updates. |
| Cập nhật nhiều field như **một immutable value** | `AtomicReference<State>` + CAS | Một reference chứa toàn bộ snapshot, update bằng một CAS. |
| Producer/consumer chờ phần tử | `BlockingQueue` | Tự xử lý phối hợp, không cần tự viết Condition buffer. |
| Chỉ cần một lần báo hoàn tất | `CountDownLatch` | Đợi sự kiện, không phải truy cập mutable state qua lock tự viết. |
| Quản lý đồng thời bao nhiêu task dùng tài nguyên | `Semaphore` | Điều tiết permit; không tự làm các field thành atomic. |
| Nhiều key độc lập, truy cập map đồng thời | `ConcurrentHashMap` | API concurrent chuyên dụng, nhưng operation nhiều key có invariant riêng. |

### 11.1 AtomicReference và CAS cũng có chi phí

Nếu dùng `AtomicReference<ImmutableState>` để giữ một snapshot nhiều field, writer sẽ tạo state mới rồi `compareAndSet(old, next)`. Với contender cùng update, CAS thất bại và phải retry. Chi phí gồm:

- Allocation cho những candidate state có thể bị bỏ đi.
- Retry khi contention cao; không có bảo đảm một thread cụ thể sẽ thành công trong số lần hữu hạn.
- Code khó review nếu có side effect trong phép tính next.
- Khả năng ABA khi algorithm tái sử dụng identity/giá trị theo cách không kiểm tra lịch sử.

Không đặt network call, gửi email hoặc thay đổi external state trong phần tính toán có thể retry. Với state phức tạp, một lock đơn giản có thể dễ đúng và nhanh hơn.

### 11.2 Một biến atomically đúng không có nghĩa nhiều biến nhất quán

Hai `AtomicInteger` riêng biệt không biến `available--` và `reserved++` thành atomic transition. Nếu cần `available + reserved == capacity` trong mọi snapshot, dùng **một critical section** hoặc **một immutable State được publish atomically**.

Mọi quyết định “không dùng lock” cũng phải chứng minh được HB, atomicity và invariant phù hợp. Đừng thay khóa bằng `volatile` chỉ để tránh BLOCKED thread.

## 12. Reentrancy, fairness, cancellation: không thể đổi lock máy móc

Bên cạnh performance, việc đổi primitive có thể thay đổi **ngữ nghĩa của API**.

### 12.1 Reentrant hay không?

- Intrinsic monitors: reentrant.
- `ReentrantLock`: reentrant.
- `ReentrantReadWriteLock`: hỗ trợ reentrancy theo các quy tắc riêng.
- `StampedLock`: **không reentrant**.

Một chuỗi method vốn chạy tốt dưới `synchronized` có thể tự deadlock sau khi đổi sang `StampedLock` nếu helper method lồng nhau lại lấy lock lần nữa. Trước khi thay, kiểm tra call graph và cách acquire nested.

### 12.2 Interruptibility của acquisition

- Thread đang `BLOCKED` để vào `synchronized` không có timed/interruptible acquisition theo cùng kiểu `ReentrantLock.lockInterruptibly()`.
- `ReentrantLock.lockInterruptibly()` và `tryLock(timeout, unit)` có thể ném `InterruptedException`.
- `Condition.await()` là operation chờ điều kiện, không giống chờ acquire lock lần đầu.
- `Object.wait()` có thể ném `InterruptedException` và nhả monitor đang wait trong thời gian chờ; `Thread.sleep()` không nhả monitor đã giữ.

Hãy phân biệt **cancellation của người đang chờ lấy lock** với **cancellation của người đang giữ lock**. Không API nào tự bảo đảm business operation có thể rollback chính xác ở bất kỳ instruction nào.

### 12.3 Fairness và starvation

Một lựa chọn fair có thể hữu ích khi một nhóm contender đợi bất hợp lý, nhưng không sửa code giữ lock quá lâu hoặc dependency graph bị vòng. Fairness còn có chi phí scheduling/throughput; điều cần xác định là policy người dùng mong đợi, không chỉ flag cấu hình.

## 13. Deadlock và thứ tự lấy nhiều lock

Khi phải giữ hai lock, một vòng phụ thuộc có thể xảy ra:

~~~text
Thread A: giữ lock1 -> chờ lock2
Thread B: giữ lock2 -> chờ lock1
~~~

Nếu chỉ có một owner lock bảo vệ toàn invariant, đôi khi thiết kế vừa đơn giản vừa dễ chứng minh hơn. Khi bắt buộc nhiều lock, dùng **thứ tự toàn cục ổn định**, ví dụ theo một ID duy nhất và bất biến của object.

Mảnh minh họa:

~~~java
Account first = left.id < right.id ? left : right;
Account second = left.id < right.id ? right : left;

synchronized (first.lock) {
    synchronized (second.lock) {
        // Kiểm tra và cập nhật state liên quan cả hai account.
    }
}
~~~

Đoạn này **không tự chạy**: cần class `Account` có ID bất biến và duy nhất, lock và state riêng. Trong sản phẩm phải xử lý trường hợp cùng account, ID trùng/không hợp lệ và mọi đường gọi khác cùng thứ tự. Không để lock public hoặc callback bên ngoài lấy lock ngược.

**Cân nhắc chi phí:** chia một lock thành nhiều lock có thể tăng concurrency khi dữ liệu độc lập, nhưng tăng bề mặt deadlock và làm snapshot nhiều object khó hơn. Chỉ shard lock khi chứng minh invariant không bị tách sai và đã có lợi ích đo được.

### 13.1 Đừng chờ completion khi giữ lock mà task cần

~~~java
synchronized (lock) {
    worker.start();
    worker.join();
}
~~~

Mảnh minh họa giả định `worker` trong lúc chạy cần `lock`; khi đó caller giữ lock và chờ worker hoàn tất, worker cần chính lock ấy để hoàn tất, tạo deadlock. `Thread.join()` không nhả monitor đang giữ.

Tránh `Future.get()`, `CountDownLatch.await()` hoặc I/O blocking trong critical section nếu công việc được chờ cần lock/worker đang bị chiếm dụng. Khi thật sự cần đợi điều kiện trên một lock, dùng `Condition`/`Object.wait()` theo protocol, để nhả lock gắn với điều kiện trong lúc đợi.

## 14. Virtual threads và lựa chọn lock

Từ Java 21, **virtual threads** giúp mô hình một thread cho mỗi tác vụ blocking trở nên khả thi với nhiều workload, nhưng **không giải phóng invariant khỏi nhu cầu đồng bộ**:

- Nhiều virtual threads lấy cùng monitor vẫn phải tuần tự trong critical section.
- Giữ lock qua I/O chậm vẫn khiến contender chờ và tăng latency ở cấp ứng dụng.
- `ReentrantLock` không tự nhanh hơn intrinsic monitor chỉ vì chạy trên virtual thread.
- Các vấn đề liên quan virtual-thread pinning khi giữ intrinsic monitor đã thay đổi giữa các phiên bản JDK. Ví dụ JDK 21 có những trường hợp pinning gắn với `synchronized`; các bản JDK sau có cải tiến. Cần xác nhận **JDK cụ thể đang triển khai** và quan sát JFR/profiler, không áp dụng quy tắc của một phiên bản cho mọi runtime.
- `ReentrantLock` với interruptible/timed acquisition hữu ích khi hợp đồng hủy yêu cầu, nhưng việc đổi loại lock vẫn phải giữ đúng thứ tự và invariant.

Nên đánh giá lock **dựa trên workload, version JDK và yêu cầu cancellation thật**, thay vì dùng “virtual threads” như lý do mặc định phải thay tất cả `synchronized`.

## 15. Benchmark đúng trước khi tối ưu

Một microbenchmark về lock rất dễ sai vì compiler/JIT, dead-code elimination, warm-up, false sharing, contention nhân tạo và kết quả bị chi phối bởi việc làm bên ngoài lock.

### 15.1 Các bước thực tế

1. **Thiết lập baseline correctness.** Trước và sau tối ưu phải cho cùng kết quả/invariant khi nhiều thread tranh chấp.
2. **Đo đúng workload.** Số reader, writer, phân bố thời gian critical section, độ lớn state và mức tải phải đại diện production.
3. **Phân biệt throughput và latency.** Một lock tăng throughput trung bình nhưng làm p99 chờ khóa quá cao có thể không phù hợp SLA.
4. **Đo contention.** Thread dump, `ThreadMXBean`, Java Flight Recorder (JFR) và profiler có thể cho biết thread nào chờ monitor/lock, holder đang làm gì, và thời gian chờ.
5. **Đo cả thời gian giữ khóa.** Nhiều contender `BLOCKED` có thể do một holder gọi I/O/sleep chậm trong critical section.
6. **Warm-up và so sánh công bằng.** Dùng cùng JDK, JVM flags, dữ liệu đầu vào, số thread, môi trường; chạy nhiều vòng và xem phân bố kết quả.
7. **Kiểm tra lỗi sau tối ưu.** Không chấp nhận “nhanh hơn” nếu bỏ mất atomic snapshot hoặc update.
8. **Ghi lại trade-off.** Cần biết độ phức tạp code tăng bao nhiêu so với lợi ích đo được.

**JMH** (Java Microbenchmark Harness) phù hợp để làm microbenchmark về JVM. Bài học này không tự đưa số nanosecond cố định, bởi kết quả phụ thuộc hoàn toàn vào cách dựng benchmark và runtime.

### 15.2 Những chỉ số nên ghi

| Metric | Diễn giải |
| --- | --- |
| Operations/second | Throughput hữu ích khi tăng số worker. |
| Median, p95, p99 latency | Thời gian chờ của yêu cầu/operation, đặc biệt đuôi phân bố. |
| Lock acquisition/blocked time | Chi phí các contender phải đợi. |
| Critical section hold time | Thời lượng holder giữ lock. |
| Retry/optimistic validation failure | Chi phí thêm của CAS và StampedLock. |
| CPU, allocation và GC | Retry/immutable candidate/metadata overhead. |
| Read/write proportion | Chứng minh ReadWriteLock hoặc optimistic read có hợp workload. |
| Correctness invariants | Không được mất tính đúng khi đổi primitive. |

Đừng đặt mục tiêu “không còn thread `BLOCKED`”. Một chút blocking có thể hợp lý và tiết kiệm CPU hơn vòng spin. Mục tiêu là correctness cùng hiệu năng đủ đáp ứng yêu cầu, không phải loại bỏ mọi lock.

## 16. Chọn loại lock theo tình huống

| Tình huống | Lựa chọn ban đầu hợp lý | Vì sao / điểm cần xác minh |
| --- | --- | --- |
| Một object mutable, vài field cùng invariant, critical section ngắn | **`synchronized` với private lock** | Dễ đọc, reentrant, tự release; kiểm tra mọi reader/writer cùng protocol. |
| Cần timed/interruptible acquisition | **`ReentrantLock`** | `tryLock(timeout)` / `lockInterruptibly()`; unlock trong finally. |
| Một lock có nhiều predicate cần chờ riêng | **`ReentrantLock + Condition`** hoặc cấu trúc concurrent có sẵn | Phân biệt notEmpty/notFull; kiểm tra predicate bằng while. |
| Nhiều reader, ít writer, read critical section tương đối dài | **`ReentrantReadWriteLock`** để thử nghiệm | Đo overhead read lock và writer latency, không tự động nhanh hơn mutex. |
| Rất nhiều phép đọc đơn giản, ghi hiếm, snapshot dễ validate | **`StampedLock`** nếu benchmark chứng minh lợi ích | Protocol non-reentrant và optimistic validation khó hơn, cần fallback. |
| Một biến counter/flag độc lập | **Atomic/volatile** theo bài toán | Tránh lock không cần thiết; volatile không sửa multi-step invariant. |
| Một immutable snapshot nhiều trường, update không side effect | **`AtomicReference<State>`** | CAS atomically publish state, đổi lấy retry/allocation. |
| Buffer producer–consumer | **`BlockingQueue`** | Ít lỗi hơn tự tổ chức wait/notify/Condition. |
| Nhiều key độc lập trong map | **`ConcurrentHashMap`** | Operation nhiều key vẫn cần protocol riêng. |

**Quy tắc ưu tiên:** correctness → deadline/cancellation → điều kiện chờ → read/write pattern → contention thực tế → độ phức tạp bảo trì. Nếu hai lựa chọn đều đạt yêu cầu, ưu tiên API đơn giản hơn cho đến khi có bằng chứng hiệu năng ngược lại.

## 17. Những lỗi chọn lock thường gặp

**Lỗi 1: “ReadWriteLock có hai loại lock nên luôn nhanh hơn synchronized.”** Sai. Các read lock vẫn có overhead; critical section nhỏ hoặc writer thường xuyên có thể khiến throughput thấp hơn mutex.

**Lỗi 2: “StampedLock optimistic read không chặn nên có thể dùng dữ liệu ngay.”** Sai. Dữ liệu trước validation có thể không nhất quán; chỉ được sử dụng khi validate thành công, hoặc phải fallback dưới read lock.

**Lỗi 3: “Đổi synchronized sang ReentrantLock là performance fix.”** Không có bảo đảm. Nếu holder vẫn gọi I/O chậm dưới lock, contention còn nguyên.

**Lỗi 4: “Lock fair đảm bảo mỗi thread hoàn thành đúng thời hạn.”** Sai. Fairness không thay scheduling, độ dài task và các điểm chờ khác.

**Lỗi 5: “Hai getter dưới read lock từng lần đủ tạo snapshot.”** Nếu có writer chen giữa hai lần gọi, chúng có thể thuộc hai phiên bản khác nhau. Đọc cả invariant dưới **một lần** read lock.

**Lỗi 6: “Một atomic variable cho mỗi field giải quyết invariant tổng.”** Atomic của từng biến không tạo atomic transaction giữa nhiều biến.

**Lỗi 7: “Chỉ cần `unlock()` trong happy path.”** Exception/return có thể làm rò lock; dùng `try/finally` ngay sau acquire.

**Lỗi 8: “Có thể upgrade read lock lên write lock trực tiếp.”** Với `ReentrantReadWriteLock`, read-to-write upgrade không được hỗ trợ như một thao tác tổng quát; phải release và kiểm tra lại sau khi lấy write lock.

**Lỗi 9: “`Condition.signal()` nghĩa waiter chạy ngay.”** Waiter còn phải reacquire lock và có thể thấy predicate thay đổi; luôn kiểm tra bằng while.

**Lỗi 10: “Chờ intrinsic monitor có thể bị interrupt để thoát ngay.”** Chờ acquire monitor không có cơ chế interruptible acquisition tương đương `lockInterruptibly()`.

**Lỗi 11: “JMH hoặc một lần profiling cho kết quả vĩnh viễn.”** Các JDK, máy, tần suất đọc/ghi và đường code khác nhau có thể đảo ngược kết quả.

**Lỗi 12: “Bỏ lock là luôn tốt hơn.”** Nếu thiết kế không còn HB/atomicity thích hợp, hệ thống có thể nhanh hơn nhưng sai dữ liệu.

## 18. Câu hỏi tự kiểm tra

**1.** Một object có ba field cùng invariant; thao tác ghi hiếm và chỉ mất vài instruction. Nên bắt đầu bằng gì?  
**Đáp:** Một private `synchronized` lock cho cả operation và snapshot, trừ khi có yêu cầu đặc biệt. Đo trước khi chọn giải pháp phức tạp.

**2.** Cần giới hạn thời gian chờ để lấy khóa. Intrinsic monitor có API timed acquisition không?  
**Đáp:** Không. `ReentrantLock.tryLock(timeout, unit)` phù hợp hơn, nhưng phải xử lý nhánh timeout và unlock đúng.

**3.** Dùng `ReentrantReadWriteLock` nhưng một writer chạy liên tục; có chắc nhanh hơn mutex không?  
**Đáp:** Không. Writer vẫn độc quyền, reader có overhead và có thể chờ; cần benchmark với tỷ lệ đọc/ghi thực.

**4.** Vì sao `Condition.await()` phải đi cùng vòng `while`?  
**Đáp:** Vì spurious wakeup và vì predicate có thể thay đổi trước khi waiter reacquire lock.

**5.** `StampedLock.tryOptimisticRead()` trả stamp, đọc hai field rồi validate thất bại. Nên làm gì?  
**Đáp:** Retry hoặc lấy read lock, đọc lại cả hai field và chỉ sử dụng snapshot hợp lệ.

**6.** Cần nhiều method gọi lồng nhau, cùng lấy lock. `StampedLock` có phù hợp như thay thế máy móc cho synchronized không?  
**Đáp:** Không. `StampedLock` không reentrant và có thể làm code tự deadlock.

**7.** Hai `AtomicInteger` quản lý available và reserved. Có đủ để giữ `available + reserved == capacity` trong mọi snapshot không?  
**Đáp:** Không. Cần cập nhật và đọc nhóm field theo một protocol atomic chung.

**8.** `tryLock()` không tham số trên một fair ReentrantLock có luôn tôn trọng hàng đợi không?  
**Đáp:** Không; overload này có thể barging khi khóa đang rảnh, bất kể fairness flag.

**9.** Tại sao không giữ lock khi gọi `Future.get()` đợi worker cần lock đó?  
**Đáp:** Có thể tạo vòng chờ khiến worker không hoàn tất; cần đợi ngoài critical section hoặc thiết kế condition protocol.

**10.** Khi nào nên chấp nhận thêm độ phức tạp của `ReadWriteLock` hoặc `StampedLock`?  
**Đáp:** Khi hợp đồng correctness được chứng minh, workload có đặc điểm phù hợp và benchmark/profiling cho thấy lợi ích đủ lớn so với overhead, retry và chi phí bảo trì.

**Ghi nhớ:** Không có “lock mạnh nhất” cho mọi tình huống. **`synchronized` là baseline tốt khi chỉ cần mutual exclusion rõ ràng**; `ReentrantLock` được chọn vì quyền điều khiển acquisition/conditions; `ReadWriteLock` khi đọc song song có lợi; `StampedLock` khi optimistic protocol thực sự đáng giá. Mọi quyết định phải bảo toàn invariant và happens-before, xử lý shutdown/interruption, rồi được xác nhận bằng đo đạc trên workload phù hợp.