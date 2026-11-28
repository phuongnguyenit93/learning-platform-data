# ReentrantLock, Condition và khóa đọc ghi

Trong Java 27, các lớp trong `java.util.concurrent.locks` cho phép kiểm soát truy cập trạng thái dùng chung bằng những cơ chế linh hoạt hơn khóa monitor của `synchronized`. Ba khái niệm cần phân biệt:

- **`ReentrantLock`** cung cấp khóa độc quyền (mutual exclusion), cho phép một thread đang giữ khóa lấy lại chính khóa đó.
- **`Condition`** cung cấp hàng đợi chờ một **điều kiện trạng thái** gắn với một khóa, chẳng hạn “hàng đợi chưa rỗng” hoặc “hàng đợi còn chỗ”.
- **`ReentrantReadWriteLock`** cung cấp khóa đọc và khóa ghi: nhiều reader có thể cùng đọc khi không có writer; writer cần quyền truy cập độc quyền.

Bài thuộc chương **Nền tảng lập trình đồng thời** của module **Java 27 và các kiến thức liên quan**. Các API, ví dụ và lưu ý bên dưới áp dụng cho Java SE 27 hiện hành, không cần bật Preview và không sử dụng những nhận định về hành vi runtime đã lỗi thời từ các bản Java cũ.

**Nguyên tắc nền tảng:** khóa chỉ bảo vệ được một invariant khi **mọi đường đọc/ghi trạng thái liên quan** đều tuân thủ cùng một giao thức đồng bộ. Đổi từ `synchronized` sang `ReentrantLock` không tự động làm mã đúng hay nhanh hơn.

## 1. Vì sao cần khóa khi nhiều thread chia sẻ dữ liệu?

### 1.1. Một phép tăng tưởng như đơn giản

~~~java
final class UnsafeCounter {
    private int value;

    void increment() {
        value++; // không phải một thao tác nguyên tử
    }

    int get() {
        return value;
    }
}
~~~

Biểu thức `value++` bao gồm đọc giá trị hiện tại, tính giá trị mới và ghi lại. Nếu hai thread đồng thời thực hiện, chúng có thể cùng đọc một giá trị cũ rồi ghi đè kết quả của nhau. Ngoài việc cập nhật bị mất (*lost update*), truy cập không đồng bộ còn có vấn đề về visibility theo Java Memory Model.

Đây là **data race** nếu những truy cập xung đột vào cùng biến không được sắp xếp bằng quan hệ *happens-before*. Không được mặc định rằng `int` có khả năng đọc/ghi nguyên tử ở mức đơn lẻ thì toàn bộ phép `++` cũng nguyên tử.

### 1.2. Bảo vệ counter bằng ReentrantLock

~~~java
import java.util.concurrent.locks.ReentrantLock;

final class SafeCounter {
    private final ReentrantLock lock = new ReentrantLock();
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
~~~

Trong ví dụ:

1. Cùng một `lock` bảo vệ cả phép tăng lẫn phép đọc.
2. Chỉ một thread tại một thời điểm được thực thi critical section dưới khóa độc quyền đó.
3. `unlock()` được đặt trong `finally` để khóa không bị giữ mãi nếu code trong critical section ném ngoại lệ.
4. `lock` là field `final` để tham chiếu đến đối tượng khóa không bị gán lại trong vòng đời của `SafeCounter`.

`final` không tự làm biến `value` an toàn luồng. An toàn đến từ việc **toàn bộ thao tác với `value` đều nhất quán qua cùng một khóa**, và từ các bảo đảm đồng bộ bộ nhớ của `Lock`.

### 1.3. Khóa bảo vệ cả invariant nhiều biến

Giả sử một tài khoản lưu `balance` và `lastUpdated`. Nếu một thread thay đổi hai trường theo một giao dịch logic, reader cũng cần thấy một trạng thái nhất quán.

~~~java
final class AccountState {
    private final ReentrantLock lock = new ReentrantLock();
    private long balance;
    private long updatedAt;

    void replace(long newBalance, long timestamp) {
        lock.lock();
        try {
            balance = newBalance;
            updatedAt = timestamp;
        } finally {
            lock.unlock();
        }
    }

    long[] snapshot() {
        lock.lock();
        try {
            return new long[] {balance, updatedAt};
        } finally {
            lock.unlock();
        }
    }
}
~~~

Nếu chỉ khóa lúc ghi mà reader đọc hai field ngoài khóa, reader có thể quan sát một tổ hợp không nhất quán. Hãy xác định **invariant** trước, rồi quyết định các vùng code cần khóa theo invariant đó.

## 2. Lock, synchronized và các bảo đảm bộ nhớ

### 2.1. Giống nhau ở mục tiêu bảo vệ trạng thái

~~~java
final class MonitorCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int get() {
        return value;
    }
}
~~~

`synchronized` dùng monitor của một đối tượng, cung cấp mutual exclusion cùng cơ chế đồng bộ bộ nhớ. `ReentrantLock` cũng cung cấp mutual exclusion nhưng có API tường minh để khóa/mở khóa, chờ có thể interrupt, thử khóa có timeout và tạo nhiều `Condition`.

**Không có kết luận tổng quát rằng `ReentrantLock` luôn nhanh hơn `synchronized`.** Chi phí phụ thuộc contention, độ dài critical section, workload, runtime và cách JVM tối ưu hóa.

### 2.2. Memory visibility: lock/unlock tạo happens-before

Theo hợp đồng `java.util.concurrent.locks.Lock`, một lần lấy khóa thành công có hiệu ứng đồng bộ bộ nhớ như lock action; một lần mở khóa thành công có hiệu ứng như unlock action trong Java Memory Model.

Ví dụ, nếu thread A ghi dữ liệu trong critical section rồi mở khóa, thread B lấy **cùng khóa** sau đó sẽ được bảo đảm quan sát những ghi phù hợp đã được publish qua quan hệ happens-before.

~~~text
Thread A                        Thread B
lock.lock()
data = updated
lock.unlock() -- happens-before --> lock.lock()
                                 read data
                                 lock.unlock()
~~~

Khóa không bảo đảm order trên hai đối tượng khóa **không liên quan**. Cũng không thể dựa vào memory visibility nếu một thread cố tình đọc trạng thái bên ngoài giao thức đã định.

### 2.3. Khi nào nên dùng cơ chế nào?

| Cơ chế | Đặc điểm | Tình huống phù hợp |
|---|---|---|
| `synchronized` | Scope tự động giải phóng monitor khi rời khối/phương thức | Critical section ngắn, đơn giản, không cần timed acquisition |
| `ReentrantLock` | Quản lý khóa tường minh; có `tryLock`, `lockInterruptibly`, `Condition` | Cần timeout, cancellation lúc chờ khóa hoặc nhiều condition queues |
| `ReentrantReadWriteLock` | Tách quyền đọc đồng thời và quyền ghi độc quyền | Dữ liệu nhiều lượt đọc, lượt ghi ít và critical section đáng kể |
| `AtomicInteger`, `AtomicLong` | Thao tác nguyên tử với một trạng thái phù hợp | Bộ đếm và những phép cập nhật nhỏ không cần invariant nhiều biến |
| `ConcurrentHashMap`, `BlockingQueue` | Collections có hợp đồng đồng thời sẵn | Nên ưu tiên nếu bài toán khớp API, tránh tự viết giao thức khóa |

Các lựa chọn không loại trừ nhau. Một hệ thống có thể dùng `BlockingQueue` cho luồng công việc và `ReentrantLock` cho một invariant riêng.

## 3. ReentrantLock: khóa độc quyền có khả năng tái nhập

### 3.1. Reentrant nghĩa là gì?

Một thread đã giữ `ReentrantLock` có thể lấy lại khóa đó mà không bị tự deadlock ngay tại lần lấy thứ hai:

~~~java
import java.util.concurrent.locks.ReentrantLock;

final class ReentrantExample {
    private final ReentrantLock lock = new ReentrantLock();

    void outer() {
        lock.lock();
        try {
            inner();
        } finally {
            lock.unlock();
        }
    }

    private void inner() {
        lock.lock();
        try {
            System.out.println("Hold count: " + lock.getHoldCount());
        } finally {
            lock.unlock();
        }
    }
}
~~~

Khi `inner()` được gọi trong `outer()` bởi cùng thread, `getHoldCount()` có thể in `2`. Mỗi lần lấy khóa thành công phải có lần `unlock` tương ứng. Sau khi `inner` mở một mức khóa, `outer` vẫn giữ khóa cho đến khi mở mức còn lại.

`getHoldCount()` trả số lần **thread hiện tại** đang giữ khóa; nó không phải số lượng thread đang chờ. Nếu muốn kiểm tra trong mã chẩn đoán, còn có `isHeldByCurrentThread()`, `isLocked()` và `getQueueLength()`.

### 3.2. Mẫu try/finally bắt buộc trong thực hành

~~~java
lock.lock(); // Chỉ vào try sau khi lấy khóa thành công.
try {
    updateProtectedState();
} finally {
    lock.unlock();
}
~~~

Đoạn trên mang tính khuôn mẫu: `lock` và `updateProtectedState()` giả định đã được khai báo trong phạm vi sử dụng.

Đặt `lock.lock()` **trước** `try` để nếu acquisition thất bại và ném ngoại lệ, chương trình không vô ý chạy `unlock()` trên khóa chưa được giữ. Với `lockInterruptibly()` hoặc `tryLock(...)`, điều này còn quan trọng hơn vì chúng có thể ném `InterruptedException` hoặc trả về `false` trước khi lấy khóa.

~~~java
// Mẫu sai:
try {
    lock.lockInterruptibly();
    // ...
} finally {
    lock.unlock(); // Có thể unlock dù chưa lấy được khóa.
}
~~~

Với `ReentrantLock`, thread không sở hữu khóa mà gọi `unlock()` sẽ gặp `IllegalMonitorStateException`.

### 3.3. Không tự mở khóa khi quên finally

Một ngoại lệ phát sinh trong critical section không làm `ReentrantLock` tự mở như khi ra khỏi `synchronized`. Nếu bỏ `finally`, thread khác có thể bị chặn vô hạn.

Không xem `ReentrantLock` là resource được Java tự động đóng khi `try`-with-resources kết thúc: bản thân `ReentrantLock` không phải `AutoCloseable` theo contract chuẩn. Cách điển hình là `try/finally`.

## 4. Các cách lấy khóa: lock, lockInterruptibly, tryLock

### 4.1. lock(): chờ đến khi lấy được

~~~java
lock.lock();
try {
    doWork();
} finally {
    lock.unlock();
}
~~~

`lock()` đợi quyền sở hữu khóa nếu đang bị thread khác giữ. Với `ReentrantLock`, thao tác này **không trả về bằng `InterruptedException`**. Nếu thread bị interrupt trong lúc chờ, `lock()` không hủy thao tác chỉ vì tín hiệu đó; trạng thái interrupt vẫn cần được ứng dụng xử lý phù hợp sau khi lấy khóa.

Một hệ thống cần dừng việc chờ theo yêu cầu cancellation không nên mặc định dùng `lock()`.

### 4.2. lockInterruptibly(): có thể ngừng chờ

~~~java
static void updateInterruptibly(ReentrantLock lock)
        throws InterruptedException {

    lock.lockInterruptibly();
    try {
        System.out.println("Protected update");
    } finally {
        lock.unlock();
    }
}
~~~

`lockInterruptibly()` ném `InterruptedException` nếu thread bị interrupt khi đang chờ hoặc khi vào thao tác theo contract; trong trường hợp đó nó chưa chiếm khóa nên không được unlock.

Nếu API cho phép, truyền tiếp `InterruptedException` cho caller thường tốt hơn việc bắt rồi bỏ qua. Nếu không thể truyền tiếp và quyết định kết thúc thao tác, cần cân nhắc khôi phục interrupted status bằng `Thread.currentThread().interrupt()`.

### 4.3. tryLock(): thử ngay, không chờ

~~~java
static boolean tryUpdate(ReentrantLock lock) {
    if (!lock.tryLock()) {
        return false;
    }

    try {
        System.out.println("Updated");
        return true;
    } finally {
        lock.unlock();
    }
}
~~~

`tryLock()` không tham gia chờ đến khi khóa được nhả; nó thử tại thời điểm gọi. Một lần trả `false` không nói rằng khóa sẽ tiếp tục bận ở thời điểm sau.

### 4.4. tryLock(timeout, unit): giới hạn thời gian chờ

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

static boolean tryUpdateWithin(ReentrantLock lock)
        throws InterruptedException {

    if (!lock.tryLock(250, TimeUnit.MILLISECONDS)) {
        return false;
    }

    try {
        System.out.println("Updated within deadline");
        return true;
    } finally {
        lock.unlock();
    }
}
~~~

Phiên bản timed acquisition có thể ném `InterruptedException` và trả về `false` nếu quá thời gian. **Chỉ unlock khi `tryLock` đã trả về `true`.**

Timeout chỉ giới hạn thời gian **chờ khóa**. Nếu nội dung critical section có thể treo, timeout ở `tryLock` không tự giới hạn thời gian thực thi của code đã vào khóa.

### 4.5. Bảng tóm tắt

| Phương thức | Có chờ không? | Có thể `InterruptedException`? | Kết quả |
|---|---|---|---|
| `lock()` | Có, cho đến khi lấy khóa | Không | `void` sau khi lấy khóa |
| `lockInterruptibly()` | Có, nhưng cho phép ngắt | Có | `void` sau khi lấy khóa |
| `tryLock()` | Không chờ | Không | `true` nếu lấy được, ngược lại `false` |
| `tryLock(timeout, unit)` | Có, tối đa trong khoảng thời gian yêu cầu | Có | `true`/`false` |

Các dạng lấy khóa có thể có chi phí hoặc chính sách ordering khác nhau; không nên lấy kết quả từ một workload để suy đoán hiệu năng trong mọi workload.

## 5. Fairness, starvation và contention

### 5.1. Non-fair mặc định

~~~java
ReentrantLock defaultLock = new ReentrantLock();
ReentrantLock fairLock = new ReentrantLock(true);
~~~

`new ReentrantLock()` mặc định tạo **non-fair lock**. `new ReentrantLock(true)` bật chính sách công bằng: khi nhiều thread cạnh tranh, khóa cố gắng ưu tiên thread chờ lâu hơn theo điều kiện của implementation.

Fairness có thể giúp giảm sự khác biệt lớn về thời gian chờ hoặc nguy cơ starvation, nhưng thường làm giảm throughput vì hạn chế cơ hội một thread đang chạy lấy khóa nhanh.

### 5.2. Fairness không đảm bảo mọi thread có CPU công bằng

Fair lock chỉ điều phối thứ tự cấp khóa dưới các điều kiện của nó. Nó không bảo đảm lịch chạy thread của OS/JVM công bằng, không bảo đảm thời gian chờ có giới hạn tuyệt đối và không có nghĩa công việc bên trong critical section kết thúc nhanh.

Đặc biệt, `ReentrantLock.tryLock()` **không tuân thủ fairness flag**: nếu khóa đang rảnh, lời gọi có thể lấy khóa ngay dù có thread khác đang chờ. Nếu cần dùng phiên bản tôn trọng chính sách fairness khi có tranh chấp, cân nhắc `tryLock(0, TimeUnit.SECONDS)` với lưu ý rằng phiên bản timed còn kiểm tra interruption.

### 5.3. Quan sát contention

`ReentrantLock` cung cấp các phương thức như `getQueueLength()`, `hasQueuedThreads()` và `hasWaiters(condition)` để đo/quan sát xấp xỉ.

Các giá trị này là **ước lượng thay đổi theo thời gian**, không phải giao thức đúng đắn để quyết định “bây giờ chắc chắn có thể ghi không cần khóa”. Không nên viết:

~~~java
// Không an toàn: số thread chờ không thay thế mutual exclusion.
// if (!lock.hasQueuedThreads()) {
//     updateWithoutLock();
// }
~~~

Muốn quyết định cập nhật dưới khóa, hãy thực sự lấy khóa.

## 6. Deadlock khi dùng nhiều ReentrantLock

### 6.1. Hai khóa lấy theo thứ tự đảo ngược

~~~text
Thread A                         Thread B
lock(X)                          lock(Y)
đợi lock(Y)                      đợi lock(X)
         \                       /
            không thread nào tiến được
~~~

`ReentrantLock` không tự ngăn deadlock giữa hai khóa khác nhau. Reentrancy chỉ giúp một thread lấy lại **chính khóa nó đã sở hữu**, không cứu vòng chờ giữa những khóa khác nhau.

### 6.2. Cách tránh deadlock

Những biện pháp thường dùng:

1. Định nghĩa **global lock ordering** nhất quán, ví dụ luôn lấy khóa tài khoản có ID nhỏ hơn trước.
2. Giữ critical section ngắn, tránh thực hiện I/O chậm, callback tùy ý hoặc khóa khác không rõ thứ tự bên trong.
3. Cân nhắc `tryLock(timeout)` và chính sách bỏ cuộc/khôi phục khi chờ vượt ngưỡng.
4. Không giữ một khóa trong lúc chờ một tác vụ mà tác vụ đó cần lấy lại khóa đang giữ.

Timeout không làm mọi thao tác tự động deadlock-free nếu code bỏ qua quy tắc trả khóa hoặc tiếp tục chờ ở nơi khác.

### 6.3. Mẫu hai khóa với timed acquisition

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

static boolean doWithTwoLocks(ReentrantLock first,
                              ReentrantLock second)
        throws InterruptedException {

    if (first == second) {
        return withOneLock(first);
    }

    if (!first.tryLock(100, TimeUnit.MILLISECONDS)) {
        return false;
    }

    try {
        if (!second.tryLock(100, TimeUnit.MILLISECONDS)) {
            return false;
        }

        try {
            System.out.println("Both locks acquired");
            return true;
        } finally {
            second.unlock();
        }
    } finally {
        first.unlock();
    }
}

static boolean withOneLock(ReentrantLock lock)
        throws InterruptedException {

    if (!lock.tryLock(100, TimeUnit.MILLISECONDS)) {
        return false;
    }

    try {
        return true;
    } finally {
        lock.unlock();
    }
}
~~~

Ví dụ trên có xử lý trường hợp hai tham số tham chiếu cùng một lock, giới hạn thời gian chờ mỗi lần lấy khóa và dùng nested `finally` để mở các khóa đã lấy. Đây không phải một cơ chế transaction hay công thức retry toàn năng; nếu code sửa trạng thái một phần trước khi lấy khóa thứ hai, cần thiết kế rollback riêng.

## 7. Condition: chờ một predicate, không chờ một “tín hiệu” trừu tượng

### 7.1. Condition gắn với Lock cụ thể

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

final class Gate {
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
~~~

Trong `Gate`:

- `isOpen` là **predicate** cần đợi.
- `lock` bảo vệ `isOpen` và những lời gọi `signalAll`/`await` của condition liên quan.
- `opened` là một hàng đợi chờ thuộc `lock`.
- `awaitOpen` chỉ trở về bình thường khi predicate `isOpen` đã đúng trong lúc giữ khóa.

`Condition` không phải một object chứa sẵn trạng thái “đã được báo hiệu”. Một `signal()` trước khi có thread nào đợi **không lưu lại một tín hiệu để thread tương lai nhận**. Trạng thái thật phải nằm trong predicate do ứng dụng quản lý, như `isOpen`.

### 7.2. await() làm gì với khóa?

Khi thread đang giữ khóa gọi `condition.await()`:

1. Nó **nhả khóa gắn với condition một cách nguyên tử với việc chuyển sang chờ**, cho phép thread khác vào critical section.
2. Nó chờ cho tới khi được signal, bị interrupt hoặc xuất hiện *spurious wakeup*.
3. Trước khi `await()` hoàn thành bình thường hoặc ném `InterruptedException` theo contract của implementation, thread phải **lấy lại khóa**.
4. Sau đó code kiểm tra lại predicate trong vòng `while`.

Nếu `await()` không nhả khóa, thread mở cổng không thể lấy khóa để sửa `isOpen` và mọi thread có thể mắc kẹt.

### 7.3. Vì sao bắt buộc kiểm tra bằng while?

~~~java
// Đúng: luôn kiểm tra lại trạng thái.
while (!isOpen) {
    opened.await();
}
~~~

Không viết:

~~~java
// Sai: có thể thức dậy khi isOpen vẫn false.
if (!isOpen) {
    opened.await();
}
~~~

Cần `while` vì:

- **Spurious wakeup** được API cho phép.
- `signal()` chỉ thông báo rằng điều kiện **có thể** đã thay đổi, không bảo đảm predicate sẽ đúng tới lúc thread chờ lấy lại khóa.
- Nhiều thread có thể cùng thức dậy; thread khác có thể tiêu thụ dữ liệu/trạng thái trước.

Predicate phải được đọc dưới cùng khóa bảo vệ việc cập nhật. Một `signal()` không phải “quyền được dùng tài nguyên” có thể chuyển nhượng độc lập.

### 7.4. signal() và signalAll()

- `signal()` đánh thức một thread đang đợi trên **Condition đó**, nếu có.
- `signalAll()` đánh thức tất cả thread đang đợi trên Condition đó.

Thread được đánh thức không tức thời chạy trong critical section. Nó phải cạnh tranh **lấy lại khóa** sau khi thread signal nhả khóa.

`signalAll()` thường đơn giản hơn khi nhiều kiểu thread cùng chờ hoặc thay đổi trạng thái có thể cho phép nhiều waiter tiến lên, nhưng nó có thể tạo nhiều thread thức dậy rồi lại ngủ (*thundering herd*). `signal()` tiết kiệm hơn khi ứng dụng phân đúng hàng đợi chờ theo predicate và một thay đổi trạng thái chỉ cần đánh thức một waiter.

### 7.5. Phải giữ đúng khóa khi await/signal

Với `Condition` được tạo từ `ReentrantLock.newCondition()`, thread gọi `await`, `signal` hoặc `signalAll` phải giữ khóa liên quan. Nếu không, `IllegalMonitorStateException` có thể được ném.

~~~java
// Sai nếu thread chưa giữ lock:
// opened.signal();

// Đúng:
lock.lock();
try {
    opened.signalAll();
} finally {
    lock.unlock();
}
~~~

Không gọi `opened.wait()`, `opened.notify()` hoặc `synchronized(opened)` để thay cho `Condition.await()`/`signal()`. Monitor riêng của object `Condition` **không có giao thức đồng bộ được bảo đảm** với `Lock` mà condition đó gắn vào.

## 8. Nhiều Condition cho một khóa: hàng đợi có giới hạn

Một ứng dụng sản xuất–tiêu thụ có hàng đợi hữu hạn thường cần hai predicate:

- `notFull`: producer được phép chèn thêm khi queue còn chỗ.
- `notEmpty`: consumer được phép lấy khi queue có phần tử.

Đây là trường hợp `Condition` thể hiện lợi thế so với một monitor wait-set chung: có thể tạo nhiều hàng đợi chờ khác nhau cùng gắn với **một** `ReentrantLock`.

### 8.1. Ví dụ Java tự chứa, có thể chạy

Lưu đoạn sau thành `LockConditionDemo.java`. Ví dụ minh họa một buffer chặn có capacity nhỏ và hai virtual thread; những API này ổn định trong Java 27.

~~~java
import java.util.ArrayDeque;
import java.util.Objects;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class LockConditionDemo {

    static final class BoundedBuffer<T> {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notFull = lock.newCondition();
        private final Condition notEmpty = lock.newCondition();
        private final ArrayDeque<T> queue = new ArrayDeque<>();
        private final int capacity;

        BoundedBuffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be > 0");
            }
            this.capacity = capacity;
        }

        void put(T item) throws InterruptedException {
            Objects.requireNonNull(item, "item");
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
    }

    public static void main(String[] args)
            throws InterruptedException {

        var buffer = new BoundedBuffer<Integer>(2);

        Thread producer = Thread.ofVirtual().name("producer").start(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread consumer = Thread.ofVirtual().name("consumer").start(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    System.out.println("Received " + buffer.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        producer.join();
        consumer.join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LockConditionDemo.java
java LockConditionDemo
~~~

Khi không có interruption bên ngoài, chương trình in các giá trị `1` đến `5` theo thứ tự FIFO. Thời điểm các thread chạy xen kẽ là do scheduler quyết định; nội dung in ra vẫn phản ánh thứ tự các phần tử mà producer đã thêm.

### 8.2. Tại sao một khóa nhưng hai condition?

~~~mermaid
flowchart LR
    P[Producer] -->|put| L[ReentrantLock]
    C[Consumer] -->|take| L
    L -->|queue đầy| F[Condition notFull]
    L -->|queue rỗng| E[Condition notEmpty]
    F -->|consumer lấy phần tử| P
    E -->|producer thêm phần tử| C
~~~

Queue và các predicate `queue.size() == capacity`, `queue.isEmpty()` đều được truy cập dưới **một khóa**. Không cần thêm một lock thứ hai cho từng condition: tách hai nhóm chờ giúp producer/consumer được signal có mục đích trong khi vẫn bảo vệ cùng invariant của buffer.

### 8.3. await() không làm mất quyền bảo vệ queue

Trong `put`, khi queue đầy, `notFull.await()` nhả `lock` để consumer có thể gọi `take`. Sau khi một consumer lấy phần tử và `notFull.signal()`, producer sẽ được phép cạnh tranh lấy lại khóa rồi kiểm tra queue có còn đầy không.

Nếu producer không kiểm tra `queue.size()` trong `while` sau khi được đánh thức, nhiều producer có thể vượt quá capacity.

### 8.4. Hạn chế của ví dụ sản xuất

Đây là ví dụ cơ chế Condition, **không** phải một blocking queue hoàn chỉnh cho mọi trường hợp:

- Nó chưa có `close()` hoặc giao thức hủy toàn hệ thống để đánh thức các waiter còn lại khi một thread thất bại.
- Nó không phân biệt “không còn producer” với “queue đang tạm rỗng”.
- Nó chưa có timed `put`/`take`, metrics, chính sách backpressure ngoài capacity hay xử lý lỗi tác vụ hoàn chỉnh.
- Nếu một thread bị interrupt trước khi hoàn thành đủ năm thao tác và thread kia vẫn chờ thao tác tương ứng, chương trình mẫu có thể chờ mãi.

**Trong ứng dụng thật, ưu tiên `ArrayBlockingQueue` hoặc một `BlockingQueue` phù hợp** nếu nhu cầu là hàng đợi chặn thông thường. Chúng đã triển khai một giao thức đồng thời được kiểm thử rộng rãi. Chỉ tự viết `Condition` khi có invariant hoặc chính sách đặc biệt mà abstraction có sẵn không đáp ứng.

## 9. Chờ có timeout, interruption và cancellation

### 9.1. Timed await phải kiểm tra lại predicate

~~~java
import java.util.concurrent.TimeUnit;

boolean awaitOpenWithin(long timeout, TimeUnit unit)
        throws InterruptedException {

    long remaining = unit.toNanos(timeout);

    lock.lockInterruptibly();
    try {
        while (!isOpen) {
            if (remaining <= 0L) {
                return false;
            }
            remaining = opened.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}
~~~

Đoạn này là **method minh họa đặt bên trong lớp `Gate` ở mục 7**, nơi có `lock`, `isOpen` và `opened`. Nó tính lại ngân sách thời gian từ giá trị `awaitNanos` trả về, thay vì đợi đủ timeout lại từ đầu mỗi khi thức dậy rồi predicate chưa đúng.

Tham số `timeout` cần được xác định rõ hợp đồng (ví dụ không âm); code ứng dụng nên xác thực sớm và cân nhắc trường hợp cực lớn khi chuyển đổi đơn vị thời gian.

### 9.2. Interrupt khi đang await

`Condition.await()` và `Condition.awaitNanos()` có thể ném `InterruptedException`. Với `ReentrantLock`, thread đã lấy lại khóa trước khi `await` kết thúc bằng việc ném exception, nên khối `finally` bên ngoài vẫn có thể mở khóa an toàn.

Khi một thread bị interrupt trong khi chờ, **không** nên bắt `InterruptedException` rồi giả vờ predicate đã đúng. Nếu xử lý interruption tại boundary không khai báo checked exception, thông thường nên kết thúc thao tác và khôi phục interrupt flag khi phù hợp:

~~~java
try {
    buffer.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

### 9.3. awaitUninterruptibly không phải lựa chọn mặc định

`awaitUninterruptibly()` không ném `InterruptedException` ra ngoài để hủy chờ. Một hệ thống cần cancellation thường không nên dùng nó trừ khi bắt buộc theo contract và có thiết kế riêng về interruption.

Dù chọn phiên bản chờ nào, predicate vẫn cần được kiểm tra bằng vòng `while`.

## 10. Khóa đọc ghi: nhiều reader, một writer

### 10.1. Giao diện ReadWriteLock

~~~java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
Lock read = rw.readLock();
Lock write = rw.writeLock();
~~~

`ReentrantReadWriteLock` triển khai `ReadWriteLock` và cho hai loại quyền truy cập:

- **Read lock:** nhiều thread có thể giữ đồng thời nếu không có writer khác đang sở hữu write lock.
- **Write lock:** chỉ một writer được sửa dữ liệu và loại trừ reader/writer khác trong lúc giữ khóa, với ngoại lệ về khả năng reentrancy của chính thread đang sở hữu.

Không dùng read lock để ghi trạng thái chia sẻ. Dù không có writer vào cùng lúc, nhiều reader có thể đồng thời ở trong critical section, nên phép ghi dưới read lock tạo race giữa các reader.

### 10.2. Bảng tương thích quyền

| Thread A đang giữ | Thread B muốn | Có thể cùng tiến hành? |
|---|---|---|
| Read lock | Read lock | Có, nếu chính sách fairness và điều kiện chờ cho phép |
| Read lock | Write lock | Không, B phải chờ |
| Write lock | Read lock | Không, nếu B là thread khác |
| Write lock | Write lock | Không, nếu B là thread khác |
| Write lock | Read lock, cùng thread A | Có, hỗ trợ downgrade |
| Read lock | Write lock, cùng thread A | Không thể upgrade trực tiếp theo hợp đồng `ReentrantReadWriteLock` |

Lưu ý cột cuối xét tình huống điển hình; các chi tiết reentrancy và fairness có thể ảnh hưởng thứ tự cấp khóa.

### 10.3. ReentrantReadWriteLock là reentrant

Thread đang sở hữu write lock có thể lấy lại write lock và cũng có thể lấy **read lock**. Reader có thể lấy lại read lock. Nhưng reader **không thể nâng trực tiếp** quyền read lên write bằng cách giữ read lock rồi gọi `writeLock().lock()`.

Không có “upgrade” ngầm định trong API này. Thử upgrade theo cách chờ thông thường có thể khiến thread tự chặn vô hạn, vì read lock mà chính nó giữ ngăn writer lấy quyền độc quyền.

## 11. Ví dụ độc lập: cache dữ liệu có nhiều lượt đọc

Một snapshot store thường có nhiều thread truy vấn nhưng ít lượt cập nhật. `ReentrantReadWriteLock` cho phép các reader đồng thời trong khi vẫn bảo vệ nhất quán giữa những lần cập nhật.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class ReadWriteCatalogDemo {

    static final class Catalog {
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private final Lock read = rw.readLock();
        private final Lock write = rw.writeLock();
        private final Map<String, String> records = new HashMap<>();

        void put(String key, String value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");

            write.lock();
            try {
                records.put(key, value);
            } finally {
                write.unlock();
            }
        }

        Optional<String> find(String key) {
            Objects.requireNonNull(key, "key");

            read.lock();
            try {
                return Optional.ofNullable(records.get(key));
            } finally {
                read.unlock();
            }
        }

        Map<String, String> snapshot() {
            read.lock();
            try {
                return Map.copyOf(records);
            } finally {
                read.unlock();
            }
        }
    }

    public static void main(String[] args) {
        var catalog = new Catalog();

        catalog.put("language", "Java 27");
        catalog.put("topic", "ReadWriteLock");

        System.out.println(catalog.find("language").orElse("missing"));
        System.out.println(catalog.snapshot());
    }
}
~~~

Lưu đoạn mã thành `ReadWriteCatalogDemo.java` rồi chạy:

~~~bash
javac ReadWriteCatalogDemo.java
java ReadWriteCatalogDemo
~~~

Trong `Catalog`, tất cả các thao tác với `HashMap` mutable diễn ra dưới khóa thích hợp. Phương thức `snapshot()` tạo bản sao không sửa được qua API `Map`, nên caller không giữ tham chiếu trực tiếp đến map nội bộ.

Vì key/value ví dụ là `String` bất biến, `Map.copyOf` phù hợp với mục tiêu không rò rỉ trạng thái mutable của map. Nếu giá trị là object mutable, bản sao map vẫn có thể chứa **tham chiếu tới các object đó**; cần kế hoạch sao chép phòng vệ hoặc immutable value riêng.

### 11.1. Vì sao read lock hữu ích?

Nếu hai thread cùng gọi `find`, chúng có thể cùng giữ read lock khi không có writer, trong khi dùng một `ReentrantLock` độc quyền thì chỉ một thread vào critical section.

Tuy nhiên, read/write lock có trạng thái quản lý phức tạp hơn. Nếu read operation rất ngắn, số thread ít hoặc tần suất ghi cao, overhead điều phối reader/writer có thể lớn hơn lợi ích song song. Hãy đo benchmark trên workload thực tế.

### 11.2. Return reference có thể làm thủng giao thức khóa

~~~java
// Nguy hiểm nếu nội dung mutable và caller có thể sửa:
List<String> internalList() {
    read.lock();
    try {
        return sharedList;
    } finally {
        read.unlock();
    }
}
~~~

Trong snippet này, `read` và `sharedList` là các thành viên giả định. Caller nhận tham chiếu `sharedList` sau khi lock được nhả; nếu caller sửa list ngoài khóa, invariant không còn được bảo vệ.

Hãy trả snapshot phù hợp, immutable view đủ an toàn hoặc xây dựng API thao tác đóng gói dưới khóa, thay vì đưa object mutable nội bộ ra ngoài.

## 12. Đọc–ghi: fairness, starvation và vấn đề nâng cấp khóa

### 12.1. Chính sách công bằng

~~~java
ReentrantReadWriteLock nonFair = new ReentrantReadWriteLock();
ReentrantReadWriteLock fair = new ReentrantReadWriteLock(true);
~~~

- **Non-fair (mặc định):** thứ tự cấp quyền đọc/ghi không được bảo đảm; dưới contention liên tục, một số reader hoặc writer có thể chờ rất lâu.
- **Fair:** các thread tranh chấp theo chính sách gần với thứ tự đến; khi nhả khóa, có thể cấp cho writer chờ lâu nhất hoặc nhóm reader chờ trước các writer, tùy tình trạng hàng chờ.

Fairness có thể giảm starvation nhưng không bảo đảm tốc độ tốt nhất hoặc lịch chạy thread công bằng. Đặc biệt, `readLock().tryLock()` và `writeLock().tryLock()` **không nhất thiết tuân thủ** fairness setting khi khóa đang rảnh; theo API `ReentrantReadWriteLock`, các dạng untimed này có thể lấy ngay nếu khả thi.

### 12.2. Không nâng cấp read lock thành write lock

~~~java
// Không đúng cho ReentrantReadWriteLock:
read.lock();
try {
    write.lock(); // Có thể tự chặn vô hạn (upgrade không hỗ trợ).
    try {
        modify();
    } finally {
        write.unlock();
    }
} finally {
    read.unlock();
}
~~~

Muốn sửa dữ liệu sau khi quan sát nó dưới read lock, hãy:

1. Nhả read lock.
2. Lấy write lock.
3. **Kiểm tra lại predicate/trạng thái** vì thread khác có thể đã thay đổi dữ liệu trong khoảng trống.
4. Chỉ sửa nếu điều kiện vẫn đúng.

~~~java
static void updateIfMissing(ReentrantReadWriteLock rw,
                            Map<String, String> map,
                            String key,
                            String value) {

    Lock readLock = rw.readLock();
    Lock writeLock = rw.writeLock();

    boolean missing;

    readLock.lock();
    try {
        missing = !map.containsKey(key);
    } finally {
        readLock.unlock();
    }

    if (!missing) {
        return;
    }

    writeLock.lock();
    try {
        if (!map.containsKey(key)) {
            map.put(key, value);
        }
    } finally {
        writeLock.unlock();
    }
}
~~~

Ví dụ trên giả định **mọi** đường truy cập `map` đều tuân thủ cùng `rw`, và người gọi không sửa map trực tiếp. Việc kiểm tra lại trong write lock là bắt buộc để tránh lỗi *check-then-act*.

### 12.3. Downgrade: từ write lock sang read lock

`ReentrantReadWriteLock` hỗ trợ **downgrade**: thread đang giữ write lock có thể lấy read lock trước, sau đó nhả write lock mà vẫn giữ read lock để quan sát trạng thái mới.

~~~java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

static String writeThenRead(ReentrantReadWriteLock rw,
                            Map<String, String> map) {

    Lock read = rw.readLock();
    Lock write = rw.writeLock();

    write.lock();
    boolean readAcquired = false;
    try {
        map.put("state", "updated");
        read.lock(); // Cùng thread đang giữ write lock.
        readAcquired = true;
    } finally {
        write.unlock();
    }

    if (!readAcquired) {
        throw new IllegalStateException("Read lock not acquired");
    }

    try {
        return map.get("state");
    } finally {
        read.unlock();
    }
}
~~~

Trong thực tế, đoạn `read.lock()` có thể làm code khó bảo trì nếu nhánh lỗi phức tạp; ví dụ tập trung minh họa thứ tự **write → read → unlock write → tiếp tục read → unlock read**. Phần `map` ở đây cũng phải được bảo vệ đồng nhất bằng `rw` ở toàn bộ đường truy cập khác.

Cần dùng downgrade khi cần chuyển từ cập nhật sang đọc nhất quán **mà không cho writer khác chen vào** giữa hai pha. Nếu chỉ cần giá trị sau khi đã cập nhật, giữ write lock để đọc nhanh rồi nhả có thể đơn giản hơn.

## 13. Condition trên khóa đọc/ghi

### 13.1. Condition chỉ được hỗ trợ bởi write lock

Với `ReentrantReadWriteLock`:

~~~java
ReentrantReadWriteLock rw = new ReentrantReadWriteLock();

Condition changed = rw.writeLock().newCondition(); // Hợp lệ.
~~~

Write lock hỗ trợ `Condition` với hành vi tương tự condition từ `ReentrantLock`. Khi chờ `Condition`, thread cần sở hữu write lock theo contract.

**Read lock không hỗ trợ Condition:**

~~~java
// Ném UnsupportedOperationException khi gọi:
Condition unsupported = rw.readLock().newCondition();
~~~

Đây là giới hạn chính thức của `ReentrantReadWriteLock.ReadLock`, không phải lỗi ngẫu nhiên của implementation.

### 13.2. Khi nào cần Condition của write lock?

Nếu trạng thái dùng chung chỉ được cập nhật dưới write lock và một thao tác phải chờ predicate do writer thay đổi, condition gắn với write lock có thể phù hợp.

Tuy nhiên, không cần dùng cả read/write lock lẫn condition chỉ vì chúng cùng tồn tại trong một API. Với producer–consumer đơn giản, `BlockingQueue` hoặc một `ReentrantLock` cùng hai `Condition` thường dễ hiểu hơn.

## 14. So sánh với StampedLock và virtual threads

### 14.1. StampedLock không phải thay thế tương đương

`StampedLock` hiện hành hỗ trợ write lock, read lock và optimistic read bằng stamp. Nhưng **nó không reentrant** theo cách `ReentrantReadWriteLock` reentrant, và optimistic read yêu cầu xác thực stamp/khả năng chịu dữ liệu tạm thời không nhất quán.

~~~java
import java.util.concurrent.locks.StampedLock;

final class Coordinate {
    private final StampedLock lock = new StampedLock();
    private double x;
    private double y;

    double squaredDistance() {
        long stamp = lock.tryOptimisticRead();
        double localX = x;
        double localY = y;

        if (!lock.validate(stamp)) {
            stamp = lock.readLock();
            try {
                localX = x;
                localY = y;
            } finally {
                lock.unlockRead(stamp);
            }
        }

        return localX * localX + localY * localY;
    }

    void move(double dx, double dy) {
        long stamp = lock.writeLock();
        try {
            x += dx;
            y += dy;
        } finally {
            lock.unlockWrite(stamp);
        }
    }
}
~~~

Ví dụ này chỉ đọc hai field kiểu primitive trong optimistic section rồi kiểm tra với `validate`. Không được đem cùng cách làm áp dụng máy móc cho traversal cây object, collection mutable hoặc invariant phức tạp: dữ liệu đọc trong optimistic section có thể nhất thời không nhất quán và không nên được dùng theo cách gây lỗi trước khi validate.

`StampedLock` có thể hữu ích cho một số workload đọc nhiều, nhưng phức tạp hơn về xác minh và quản lý stamp. Nếu cần reentrancy/Condition, `ReentrantReadWriteLock` phù hợp hơn.

### 14.2. Virtual threads có thay đổi quy tắc Lock không?

`Thread.ofVirtual()` là API ổn định từ Java 21 và vẫn hoạt động trong Java 27. Virtual thread sử dụng `ReentrantLock` và `Condition` với các quy tắc ownership, interruption và memory synchronization tương tự về mặt contract.

Không nên nhắc lại một cách máy móc các cảnh báo về “mọi `synchronized` sẽ pin virtual thread khi blocking” từ các giai đoạn JVM cũ: cơ chế monitor liên quan tới virtual threads đã được cải tiến trong các JDK mới. Hãy kiểm tra tài liệu runtime cụ thể trước khi quyết định đổi tất cả `synchronized` thành `ReentrantLock` chỉ vì virtual threads.

Virtual threads cũng **không** làm data race biến mất. Cần giảm tranh chấp và bảo vệ invariant y hệt khi sử dụng platform threads.

## 15. Những lỗi phổ biến khi dùng Lock và Condition

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Bỏ `finally` sau `lock()` | Exception có thể để khóa bị giữ mãi | Luôn unlock trong `finally` |
| Gọi `unlock` khi `tryLock` trả `false` | `IllegalMonitorStateException` hoặc hành vi lỗi | Chỉ unlock sau khi acquisition thành công |
| Lấy hai khóa theo thứ tự không nhất quán | Deadlock | Chuẩn hóa lock ordering hoặc timeout/hủy có kiểm soát |
| Giữ khóa trong khi làm I/O chậm | Tăng contention và độ trễ | Giữ critical section ngắn, tách I/O khi bảo đảm invariant |
| Dùng `await()` trong `if` | Spurious wakeup hoặc tranh chấp làm sai predicate | Đợi trong vòng `while` |
| Gọi `await`/`signal` ngoài lock | Vi phạm giao thức condition | Giữ đúng lock khi thao tác |
| Cho rằng `signal()` chuyển khóa tức thì | Sai về thứ tự chạy | Thread được signal phải tái lấy lock |
| Cho rằng `Condition` tự ghi nhớ signal | Mất thông báo nếu predicate không được quản lý | Lưu trạng thái rõ ràng dưới lock |
| Dùng `readLock` để sửa `HashMap` | Nhiều reader có thể ghi đồng thời | Ghi dưới write lock |
| Giữ read lock rồi `writeLock().lock()` | Upgrade không hỗ trợ; có thể deadlock | Nhả read, lấy write, kiểm tra lại |
| Dùng `readLock().newCondition()` | `UnsupportedOperationException` | Chỉ dùng write-lock Condition hoặc thay cấu trúc |
| Nghĩ `fair=true` đảm bảo thứ tự tuyệt đối | Scheduler và untimed `tryLock` phá giả định | Đừng phụ thuộc fairness để xác minh thuật toán |
| Dùng `getQueueLength` làm điều kiện tính đúng | Chỉ là ước lượng thoáng qua | Dựa vào trạng thái được bảo vệ dưới lock |
| Để lộ object mutable sau khi nhả lock | Caller có thể sửa không đồng bộ | Trả snapshot hoặc immutable value |
| Mặc định read/write lock luôn nhanh hơn mutex | Overhead có thể lớn hơn lợi ích | Benchmark theo tỷ lệ đọc/ghi và contention |
| Dùng `StampedLock` như lock reentrant | Có thể tự deadlock hoặc dùng stamp sai | Chỉ dùng khi hiểu semantics không reentrant |

## 16. Checklist thiết kế đồng bộ

Trước khi đưa một lớp dùng `ReentrantLock`/`Condition`/`ReentrantReadWriteLock` vào hệ thống:

1. **Invariant:** dữ liệu dùng chung là gì, những field nào phải thay đổi/đọc như một đơn vị?
2. **Ownership:** lock nào bảo vệ từng field? Có bất kỳ caller nào giữ tham chiếu mutable để sửa ngoài lock không?
3. **Acquisition:** cần chờ vô hạn, chờ có interruption, thử ngay hay timeout?
4. **Release:** mọi đường thành công, exception, return và timeout đều giải phóng đúng số lần đã lấy khóa chưa?
5. **Ordering:** khi dùng nhiều khóa, có thống nhất thứ tự để tránh deadlock không?
6. **Predicate:** nếu dùng Condition, trạng thái cần đợi là gì và có được cập nhật dưới cùng lock không?
7. **Wait loop:** có dùng `while` quanh `await` và kiểm tra lại sau khi thức dậy không?
8. **Signalling:** thay đổi trạng thái nào cần `signal` hay `signalAll`, và đánh thức đúng condition queue chưa?
9. **Cancellation:** interruption và timeout có được lan truyền/xử lý đúng, không bị nuốt không?
10. **Fairness:** có cần và đã đo ảnh hưởng tới throughput/chờ lâu chưa?
11. **Read/write:** read lock chỉ đọc, write lock sửa; có tránh upgrade trực tiếp không?
12. **Public API:** có trả snapshot phù hợp thay vì mutable state sau khi unlock không?
13. **Alternatives:** `AtomicLong`, `BlockingQueue`, `ConcurrentHashMap` hoặc `synchronized` có đơn giản hơn không?
14. **Testing:** có test tranh chấp, spurious wakeup về logic predicate, interruption, timeout, snapshot và deadlock không?
15. **Observability:** metrics về contention có được dùng chỉ để quan sát, không thay thế giao thức khóa không?

## 17. Câu hỏi tự kiểm tra

1. Vì sao `value++` không an toàn chỉ vì `value` có kiểu `int`?
2. Tại sao cả `increment()` và `get()` của `SafeCounter` đều phải tuân thủ cùng một khóa?
3. `ReentrantLock` reentrant có nghĩa một thread được phép giữ khóa bao nhiêu lần? Cần làm gì trước khi thread khác có thể lấy khóa?
4. Vì sao `lock.lock()` được đặt trước `try` và `unlock` trong `finally`?
5. `lockInterruptibly()` khác `lock()` ở điểm nào về cancellation?
6. `tryLock()` và `tryLock(timeout, unit)` khác nhau thế nào về chờ và interruption?
7. Fair lock có bảo đảm một thread nhất định không bao giờ bị scheduler bỏ đói không?
8. Vì sao `Condition.await()` phải nhả lock khi chờ?
9. Vì sao một lần `signal()` không đủ để bỏ vòng `while`?
10. `notFull` và `notEmpty` trong bounded buffer gắn với bao nhiêu `ReentrantLock`?
11. Nếu producer bị hủy khi consumer đang chờ vô hạn, ví dụ `LockConditionDemo` còn thiếu giao thức gì?
12. Vì sao hai thread có thể cùng `find` dưới read lock nhưng không thể cùng `put` dưới write lock?
13. Tại sao không được giữ read lock rồi gọi write lock để nâng cấp?
14. Downgrade từ write lock xuống read lock có khác upgrade từ read lên write không?
15. `ReentrantReadWriteLock.readLock().newCondition()` có được hỗ trợ không?
16. Khi nào một `ConcurrentHashMap` hoặc `BlockingQueue` là lựa chọn tốt hơn tự viết khóa?
17. Vì sao `StampedLock` không thể dùng như một `ReentrantReadWriteLock` tương đương?
18. Những cải tiến về virtual threads có thay đổi quy tắc data race hoặc phải unlock đúng khóa không?

## 18. Nguồn tham khảo chính thức cho Java SE 27

- [Java SE 27 API — Lock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/Lock.html): API khóa, acquisition interruptible/timed và memory synchronization.
- [Java SE 27 API — ReentrantLock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): reentrancy, fair/non-fair, `lockInterruptibly`, `tryLock`, `newCondition` và quản lý ownership.
- [Java SE 27 API — Condition](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/Condition.html): `await`, `signal`, `signalAll`, spurious wakeups và yêu cầu kiểm tra predicate trong vòng lặp.
- [Java SE 27 API — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): read/write locking, fairness, downgrading, không upgrade trực tiếp và Condition support.
- [Java SE 27 API — ReentrantReadWriteLock.ReadLock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.ReadLock.html): các phương thức read lock và `newCondition` không được hỗ trợ.
- [Java SE 27 API — StampedLock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/StampedLock.html): optimistic read, stamp validation và tính không reentrant.
- [Java SE 27 API — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): blocking queue hữu hạn có sẵn, thay cho tự xây dựng buffer thông thường.
- [Java SE 27 API — BlockingQueue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/BlockingQueue.html): contract put/take, giới hạn dung lượng và chờ phần tử.
- [Java Language Specification, Java SE 27 — Chapter 17: Threads and Locks](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-17.html): data races, synchronization actions và happens-before.
- [JLS Java SE 27 — §17.4.5 Happens-before Order](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-17.html#jls-17.4.5): cơ sở cho visibility và ordering giữa thread.
