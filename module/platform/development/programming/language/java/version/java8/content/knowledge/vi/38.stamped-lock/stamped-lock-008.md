# Giới hạn không tái nhập và nguy cơ deadlock với StampedLock

`java.util.concurrent.locks.StampedLock` là công cụ đồng bộ có từ Java 8, vẫn được hỗ trợ trong các JDK hiện hành. Nó cho phép **write lock độc quyền**, **read lock chia sẻ** và **optimistic read có kiểm chứng**. Nhưng khác với `ReentrantLock`, StampedLock **không tái nhập (non-reentrant)**: một thread đã nắm quyền không được tự giả định có thể xin lại cùng lock từ một method lồng trong call stack.

Sai lầm điển hình là một updater lấy write lock rồi gọi getter mà getter lại lấy read lock, hoặc một reader chờ write lock trong khi vẫn giữ read lock cũ. Trong cả hai trường hợp, lệnh nhả quyền có thể nằm ở phía sau một lời gọi đang chờ, tạo **self-deadlock**. Một nguy cơ khác là nhiều lock được lấy theo thứ tự không nhất quán, khiến hai thread chờ vòng tròn AB–BA.

Mục tiêu: hiểu **tại sao không reentrant**, tránh tự acquire trong helper/callback, chuyển read→write đúng cách bằng `tryConvertToWriteLock`, quản lý stamp, định nghĩa thứ tự khóa, giới hạn thời gian chờ, kiểm thử không làm treo chương trình, chẩn đoán sự cố khi có nhiều luồng. Bài có một chương trình Java **JDK 17+** hoàn chỉnh, kiểm chứng được các kết quả mà không tạo deadlock thật.

## 1. Non-reentrant là gì?

Một lock reentrant nhận ra thread đang sở hữu nó và cho phép thread ấy lấy lại cùng lock, ví dụ `ReentrantLock`. `StampedLock` không cung cấp cơ chế owner hold count như vậy. Mỗi lời gọi `writeLock()` hoặc `readLock()` là một yêu cầu lấy quyền mới.

~~~text
Thread T:
  public update()
    -> writeLock()       [đã giữ quyền write]
    -> helper()
        -> writeLock()   [đợi chính write lock ở trên]
    -> unlockWrite()     [không thể chạy tới khi helper bị kẹt]
~~~

Nếu dùng phương thức acquire có thể chặn, thread có thể kẹt mãi. `finally` nằm sau helper không tự chạy trước khi lời gọi blocking được giải quyết. Đây là lỗi **cấu trúc**, không phải lỗi thiếu thread pool.

### 1.1. StampedLock không có owner thread

Tài liệu Oracle mô tả StampedLock là **capability-based lock**: lệnh lấy quyền trả một **stamp kiểu long**, dùng để unlock hoặc conversion. Lock không gắn ownership chặt với một thread như nhiều loại Lock thông thường. Một stamp có thể được thread khác nhả trong giao thức phối hợp đặc biệt.

Điều này **không có nghĩa reentrant**. StampedLock không dựa vào thread identity để ưu tiên lần acquire thứ hai. Nếu write đang bị giữ, không có read hoặc write lock mới được cấp chỉ vì caller là cùng thread.

| Thuộc tính | StampedLock | ReentrantLock |
|---|---|---|
| Có phép reentry write theo owner | Không | Có |
| Có owner hold count thông thường | Không | Có |
| Lấy quyền thông qua | Stamp theo mode/version | Owner và lock state |
| Unlock | `unlockWrite(stamp)` hoặc `unlockRead(stamp)` | `unlock()` |
| Optimistic read | Có | Không |
| Chuyển mode bằng stamp | Có | Không có cùng API |

**Stamp không phải ID của thread hoặc token bảo mật.** Không hardcode số stamp, không dùng nó để đồng bộ giữa process và không giả định đó là version bất biến vĩnh viễn.

### 1.2. Read lock lồng nhau không phải tái nhập

Có nhiều reader cùng giữ read lock, nên bạn có thể thấy gọi `readLock()` lần nữa vẫn thành công. Nhưng đó là một acquire độc lập, với stamp riêng cần unlock; không có lời hứa reentrancy theo owner. Khi trạng thái lock hoặc scheduling thay đổi, việc xin thêm read lock có thể chờ. Không xây helper lồng nhau dựa vào quan sát may rủi rằng hai lần read luôn đi qua.

## 2. Tự deadlock khi giữ write và xin lại write

Phản ví dụ:

~~~java
class Counter {
    private final StampedLock lock = new StampedLock();
    private int value;

    public void add(int delta) {
        long s = lock.writeLock();
        try { value += delta; }
        finally { lock.unlockWrite(s); }
    }

    public int addAndGet(int delta) {
        long s = lock.writeLock();
        try {
            add(delta); // Sai: lại xin chính write lock!
            return value;
        } finally {
            lock.unlockWrite(s);
        }
    }
}
~~~

Đoạn code này **cố ý sai, không chạy**. Lời gọi `add(delta)` cố lấy write mới trong lúc `addAndGet` vẫn giữ write cũ. Thread đang chờ quyền mà chính nó chưa thể nhả. Thêm retry hoặc nhiều worker không sửa logic.

### 2.1. Write rồi gọi getter có readLock

~~~java
long s = lock.writeLock();
try {
    int current = getValue(); // Getter cũng gọi readLock trên cùng lock.
    applyUpdate(current);
} finally {
    lock.unlockWrite(s);
}
~~~

Đây là mảnh phản ví dụ với hàm ứng dụng giả định. Thread đang giữ write **có thể đọc trực tiếp protected fields**, nhưng gọi API xin read mới vẫn là một acquisition tách biệt. Khi write đang giữ, read không thể được cấp ngay; nếu dùng `readLock()` blocking sẽ có nguy cơ kẹt.

### 2.2. Listener/serializer cũng có thể gọi ngược

~~~java
long s = lock.writeLock();
try {
    updateState();
    notifyListeners(); // Listener gọi lại một public getter có lock.
} finally {
    lock.unlockWrite(s);
}
~~~

Nguy cơ không chỉ ở helper mà còn ở code ngoài không được kiểm soát: event listener, logging formatter, serializer, plugin, `toString()` hoặc interceptor có thể gọi lại API đang khóa. Trong khả năng cho phép của nghiệp vụ, **tạo event/snapshot bất biến dưới lock, nhả lock rồi mới callback**.

## 3. Read rồi chờ write cũng có thể tự kẹt

~~~java
long r = lock.readLock();
try {
    if (mustUpdate()) {
        long w = lock.writeLock(); // Sai: vẫn giữ r.
        try { update(); }
        finally { lock.unlockWrite(w); }
    }
} finally {
    lock.unlockRead(r);
}
~~~

Đây là phản ví dụ **không chạy**. Writer đòi độc quyền, còn chính read stamp r đang giữ là một reader ngăn độc quyền ấy. `writeLock()` chờ cho read được nhả, nhưng code nhả read lại nằm sau lời gọi viết đang chờ.

Không được coi một lời gọi `tryWriteLock(timeout)` khi vẫn giữ read là cách nâng cấp đúng. Nó có thể chỉ đợi tới timeout và trả zero.

### 3.1. Khi nào tryConvertToWriteLock giúp ích?

`tryConvertToWriteLock(readStamp)` thử chuyển quyền read sang write **ngay lập tức**, không ngồi chờ. Khi read stamp hợp lệ và không có reader khác cản, conversion có thể nhả read và lấy write trong một thao tác nguyên tử. Nếu không chuyển được, kết quả là `0L` và **read stamp cũ vẫn được giữ**.

~~~java
long stamp = lock.readLock();
try {
    long converted = lock.tryConvertToWriteLock(stamp);
    if (converted != 0L) {
        stamp = converted;
        updateProtectedState();
    }
} finally {
    lock.unlock(stamp);
}
~~~

Đây là mảnh code với `lock` và `updateProtectedState` do ứng dụng cung cấp. `unlock(stamp)` nhả đúng mode theo stamp hiện tại: read nếu chưa chuyển, write nếu đã chuyển.

### 3.2. Không ghi đè stamp bằng zero

Sai:

~~~java
stamp = lock.tryConvertToWriteLock(stamp);
if (stamp == 0L) {
    return false;
}
~~~

Đây là mảnh phản ví dụ. Nếu conversion thất bại, biến stamp đã bị gán zero dù **read lock ban đầu vẫn giữ**, khiến finally không còn handle hợp lệ để nhả. Dùng biến `converted` riêng và chỉ gán khi khác zero.

### 3.3. Fallback phải nhả read, xin write và kiểm lại

~~~java
long stamp = lock.readLock();
try {
    while (available > 0) {
        long converted = lock.tryConvertToWriteLock(stamp);
        if (converted != 0L) {
            stamp = converted;
            available--;
            return true;
        }
        lock.unlockRead(stamp);
        stamp = 0L;
        stamp = lock.writeLock();
        // Quay đầu while: kiểm available lần nữa dưới write lock.
    }
    return false;
} finally {
    if (stamp != 0L) lock.unlock(stamp);
}
~~~

Mảnh này nằm trong method boolean, field `available` được bảo vệ bằng lock. Khi nhả read rồi lấy write, có **khoảng trống** mà thread khác có thể sửa available. Phải recheck dưới write để không cập nhật theo điều kiện đã lỗi thời.

Không busy-spin `tryConvertToWriteLock` vô hạn khi vẫn giữ read. Nếu có reader khác, bạn vẫn giữ một quyền khiến write khó được cấp và tốn CPU mà không có tiến triển được bảo đảm.

## 4. Giải pháp thiết kế: lock một lần ở ranh giới

Cách an toàn là các **public methods quản lý acquisition**, còn **private helpers được gọi dưới lock không tự xin khóa lại**.

~~~java
final class SafeCounter {
    private final StampedLock lock = new StampedLock();
    private int value;

    private void addUnderWriteLock(int delta) {
        value += delta;
    }

    public int addAndGet(int delta) {
        long s = lock.writeLock();
        try {
            addUnderWriteLock(delta);
            return value;
        } finally {
            lock.unlockWrite(s);
        }
    }
}
~~~

Class minh họa trên cần import StampedLock; program đầy đủ phía dưới dùng cấu trúc tương tự.

Từ tên `addUnderWriteLock`, reviewer có thể thấy precondition: caller phải đang giữ write stamp phù hợp. Đây là **quy ước thiết kế** chứ Java không tự chứng minh bằng kiểu dữ liệu. Không cho caller bên ngoài truy cập helper ấy.

### 4.1. Cấu trúc nên có

| Tầng | Trách nhiệm | Không nên làm |
|---|---|---|
| Public operation | Acquire, validate, call helpers, finally unlock | Gọi public method khác tự acquire cùng lock |
| Private under-lock helper | Xử lý field đang được bảo vệ | Lock lại hoặc dispatch callback |
| Snapshot logic | Copy field vào local, validate/fallback | Duyệt racy mutable graph không an toàn |
| External callback | Thực thi sau khi đã nhả lock | Ngầm gọi lại API dưới lock |
| Coordinator nhiều tài nguyên | Xác định lock order | Lấy lock theo thứ tự tùy caller |

Giữ critical section ngắn. Nếu phải gọi network hoặc DB, thông thường nên copy dữ liệu cần thiết dưới khóa, nhả khóa, gọi I/O ngoài, rồi **recheck state/version** nếu muốn cập nhật tiếp. Cách này không tự tạo giao dịch atomic với remote service; nghiệp vụ cần transaction/outbox riêng nếu có yêu cầu mạnh hơn.

## 5. Dùng try methods để kiểm rủi ro mà không treo test

Những method `tryWriteLock()`, `tryReadLock()` và `tryOptimisticRead()` không chờ. Khi một write stamp đang giữ, chúng không thể cấp quyền mới:

~~~java
StampedLock lock = new StampedLock();
long write = lock.writeLock();
try {
    boolean noSecondWrite = lock.tryWriteLock() == 0L;
    boolean noRead = lock.tryReadLock() == 0L;
    boolean noOptimistic = lock.tryOptimisticRead() == 0L;
} finally {
    lock.unlockWrite(write);
}
~~~

Đây là mảnh code đặt trong method; biến boolean được dùng để kiểm expected behavior. Nếu thay thử bằng `writeLock()` lần hai, test có thể treo; vì vậy đừng chạy một phản ví dụ blocking chỉ để chứng minh khả năng tự deadlock.

| Tình huống | Lời gọi để kiểm | Kết quả mong đợi |
|---|---|---|
| Write đang giữ | `tryWriteLock()` | 0 |
| Write đang giữ | `tryReadLock()` | 0 |
| Write đang giữ | `tryOptimisticRead()` | 0 |
| Read đang giữ | `tryWriteLock()` | 0 |
| Một reader duy nhất | `tryConvertToWriteLock(readStamp)` | Có thể thành công |
| Hai reader đang giữ | `tryConvertToWriteLock(readStamp)` | 0 |
| Writer vừa thay dữ liệu | `validate(optimisticStamp)` | false đối với stamp bị invalidate |

Kết quả zero của phép try không cung cấp thread identity, không có nghĩa lock sẽ luôn ở trạng thái ấy về sau, và không chứng minh deadlock. Nó chỉ nói **lúc thử không nhận được quyền**.

## 6. Hai khóa khác nhau và deadlock AB–BA

Một lỗi khác không đòi acquire cùng lock hai lần. Hai thread có thể lấy hai lock theo thứ tự ngược:

~~~text
T1: giữ lock A, đợi lock B
T2: giữ lock B, đợi lock A
Cả hai đợi lẫn nhau theo một chu trình.
~~~

Với chuyển tiền, nếu thread T1 chuyển A→B và T2 chuyển B→A, cách acquire theo hướng `from` rồi `to` tạo nguy cơ AB–BA. Đây là một **circular wait** thực sự, không khắc phục chỉ bằng dùng `StampedLock` thay `synchronized`.

### 6.1. Lock ordering giải quyết chu trình

Mọi code phải lấy khóa theo **thứ tự toàn cục** như ID của tài nguyên từ nhỏ đến lớn, bất kể hướng transfer:

~~~java
Account first = from.id < to.id ? from : to;
Account second = from.id < to.id ? to : from;

long s1 = first.lock.writeLock();
try {
    long s2 = second.lock.writeLock();
    try {
        // Cập nhật cả hai protected fields.
    } finally {
        second.lock.unlockWrite(s2);
    }
} finally {
    first.lock.unlockWrite(s1);
}
~~~

Đây là mảnh code minh họa; Account nằm trong chương trình đầy đủ. ID cần **duy nhất và bất biến**. Nếu hai Account khác nhau lại cùng ID, quy tắc so sánh không tạo total order; cần từ chối hoặc có cơ chế tie-breaker phù hợp.

Một Account được truyền làm cả from và to phải được xử lý không acquire cùng write lock hai lần; chương trình ví dụ từ chối.

### 6.2. Tính nhất quán của lock ordering

- Áp dụng cùng quy tắc cho **mọi** đường đi, không chỉ method chuyển tiền.
- Không để helper ở sâu tự lấy lock thứ ba theo thứ tự khác.
- Nhả khóa ngược thứ tự acquire trong finally để dễ kiểm chứng.
- Không dùng `System.identityHashCode` mà mặc định nó không bao giờ trùng; hash collision phải được xử lý.
- Khi có nhiều loại khóa, cần xem cả lock graph tổng thể, kể cả synchronized/other Lock.

## 7. Chờ có thời hạn và interruption

`writeLock()` / `readLock()` có thể block khi chưa cấp được quyền. Nếu hệ thống có deadline/hủy, cân nhắc:

- `tryWriteLock()` / `tryReadLock()`: thử tức thời, trả stamp hoặc zero.
- `tryWriteLock(timeout,unit)` / `tryReadLock(timeout,unit)`: có thể chờ có giới hạn và ném `InterruptedException`.
- `writeLockInterruptibly()` / `readLockInterruptibly()`: chờ có thể bị interrupt.
- `tryConvertToWriteLock(stamp)`: chuyển mode ngay, không có overload timeout.

~~~java
long stamp = lock.tryWriteLock(200, TimeUnit.MILLISECONDS);
if (stamp == 0L) return false;
try {
    performUpdate();
    return true;
} finally {
    lock.unlockWrite(stamp);
}
~~~

Đây là mảnh trong một method có `throws InterruptedException`, `lock` và `performUpdate` do ứng dụng định nghĩa. Timeout không làm cơ chế khóa reentrant. Nếu vẫn giữ read rồi gọi timed write trên cùng lock, chính read ấy còn ngăn write; bạn mới chỉ giới hạn thời gian chờ một cấu trúc sai.

Nếu bắt `InterruptedException` và không thể ném tiếp, thường phải khôi phục interrupt flag phù hợp policy; không nuốt interrupt rồi tiếp tục chờ vô hạn.

## 8. Vòng đời stamp và unlock đúng mode

Stamp biểu diễn quyền gắn với **đúng instance lock và trạng thái hiện tại**, không phải ID bền vững.

~~~text
readLock() -> read stamp -> unlockRead(read stamp)
writeLock() -> write stamp -> unlockWrite(write stamp)

read stamp -> tryConvertToWriteLock thành công -> write stamp mới
                                               -> chỉ nhả write stamp mới
~~~

Những lỗi hay gặp:

- Unlock read stamp sau khi đã chuyển thành write: sai mode.
- Unlock write stamp bằng `unlockRead`: sai mode.
- Nhả cùng stamp hai lần: quyền không còn hiệu lực; có thể `IllegalMonitorStateException`.
- Ghi đè read stamp bằng zero khi conversion thất bại: rò read hold.
- Unlock optimistic stamp: optimistic không giữ read/write lock.
- Dùng stamp từ một StampedLock để unlock đối tượng StampedLock khác.

`unlock(stamp)` có ích khi biến stamp hiện tại có thể giữ read hoặc write, nhưng chỉ gọi khi đó là **lock stamp hợp lệ**. Các method `isReadLockStamp` / `isWriteLockStamp` có từ Java 10, giúp phân loại dạng stamp; chúng không xác minh sở hữu thread hoặc stamp chưa bị nhả.

## 9. Optimistic read không giải quyết reentrancy

~~~java
long stamp = lock.tryOptimisticRead();
int localX = x;
int localY = y;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        localX = x;
        localY = y;
    } finally {
        lock.unlockRead(stamp);
    }
}
return localX + localY;
~~~

Đây là mảnh trong một method, x/y là field được bảo vệ nhất quán. Copy field vào local rồi validate; nếu thất bại, đọc lại dưới read lock.

`tryOptimisticRead()` trả zero khi writer đang giữ quyền. `validate(stamp)==true` chỉ xác nhận theo hợp đồng optimistic tại thời điểm kiểm; nó **không giữ lock** và **không cấp quyền ghi**. Writer có thể xuất hiện ngay sau validate.

Không dùng optimistic read để duyệt `ArrayList` mutable đang bị writer sửa nếu các phép đọc racy có thể gây exception hoặc cấu trúc không nhất quán **trước khi validate**. Với dữ liệu phức tạp, read lock hoặc immutable snapshot đáng tin hơn.

## 10. Lock views vẫn không reentrant

`asReadLock()`, `asWriteLock()`, `asReadWriteLock()` cung cấp adapter sang API Lock/ReadWriteLock, nhưng **underlying StampedLock vẫn non-reentrant**. Chuyển kiểu interface không làm nó thành ReentrantLock.

~~~java
Lock writeView = stamped.asWriteLock();
writeView.lock();
try {
    // Không gọi lại writeView.lock() trong block này.
} finally {
    writeView.unlock();
}
~~~

Đây là mảnh minh họa, `stamped` được định nghĩa trước, cần import `Lock`. Các view không hỗ trợ `newCondition()`; dùng Condition ở đây sẽ ném `UnsupportedOperationException`.

Nếu code cần reentrancy, Condition hoặc fair scheduling option, cân nhắc `ReentrantLock` / `ReentrantReadWriteLock`. Nhưng nhớ rằng **reentrant không loại deadlock giữa nhiều lock khác nhau**. ReentrantReadWriteLock cũng không tự cung cấp nâng cấp read→write như `tryConvertToWriteLock` của StampedLock.

## 11. Chương trình Java độc lập đã kiểm thử

Lưu thành file **`StampedDeadlockSafetyDemo.java`**. Ví dụ dùng JDK 17+ (do có `record Snapshot`), không cần thư viện ngoài. Các API StampedLock minh họa có từ Java 8, vẫn còn hiệu lực.

Chương trình làm năm việc:

1. Public method `addAndGet` lấy write lock một lần, gọi private helper `addUnderWriteLock` không acquire lại.
2. `selfAcquisitionChecks` dùng try thay vì blocking calls để kiểm khả năng reentry bị từ chối.
3. `tryConvertToWriteLock` nâng read→write trong tình huống không cạnh tranh.
4. `secondReaderStopsUpgrade` dùng CountDownLatch để ép có reader thứ hai; conversion trả zero và cleanup không rò read hold.
5. Hai Account cùng tuân thủ thứ tự ID cho 2.000 lượt chuyển tiền ngược hướng, kiểm kết quả cuối sau khi Future.get.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.locks.StampedLock;

public class StampedDeadlockSafetyDemo {
    record Snapshot(int value, int updates) {}

    static final class SafeCounter {
        private final StampedLock lock = new StampedLock();
        private int value, updates;

        private void addUnderWriteLock(int delta) {
            value += delta;
            updates++;
        }

        int addAndGet(int delta) {
            long stamp = lock.writeLock();
            try {
                addUnderWriteLock(delta);
                return value;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        Snapshot snapshot() {
            long stamp = lock.tryOptimisticRead();
            int v = value;
            int n = updates;
            if (!lock.validate(stamp)) {
                stamp = lock.readLock();
                try {
                    v = value;
                    n = updates;
                } finally {
                    lock.unlockRead(stamp);
                }
            }
            return new Snapshot(v, n);
        }
    }

    static boolean[] selfAcquisitionChecks() {
        StampedLock lock = new StampedLock();
        boolean[] results = new boolean[5];
        long write = lock.writeLock();
        try {
            results[0] = lock.tryWriteLock() == 0L;
            results[1] = lock.tryReadLock() == 0L;
            results[2] = lock.tryOptimisticRead() == 0L;
        } finally {
            lock.unlockWrite(write);
        }

        long read = lock.readLock();
        try {
            results[3] = lock.tryWriteLock() == 0L;
            long converted = lock.tryConvertToWriteLock(read);
            results[4] = converted != 0L;
            if (converted != 0L) read = converted;
        } finally {
            lock.unlock(read);
        }
        return results;
    }

    static boolean secondReaderStopsUpgrade() throws Exception {
        StampedLock lock = new StampedLock();
        long first = lock.readLock();
        CountDownLatch held = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<?> other = executor.submit(() -> {
            long second = lock.readLock();
            try {
                held.countDown();
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("reader timeout");
                }
            } finally {
                lock.unlockRead(second);
            }
            return null;
        });
        try {
            if (!held.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("reader not ready");
            }
            return lock.tryConvertToWriteLock(first) == 0L;
        } finally {
            lock.unlockRead(first);
            release.countDown();
            try {
                other.get(5, TimeUnit.SECONDS);
            } finally {
                executor.shutdownNow();
                executor.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }

    static final class Account {
        final int id;
        final StampedLock lock = new StampedLock();
        int balance;

        Account(int id, int balance) {
            this.id = id;
            this.balance = balance;
        }

        int readBalance() {
            long s = lock.readLock();
            try {
                return balance;
            } finally {
                lock.unlockRead(s);
            }
        }
    }

    static void transfer(Account from, Account to, int amount) {
        if (from == to || from.id == to.id || amount <= 0) {
            throw new IllegalArgumentException("invalid transfer");
        }
        Account first = from.id < to.id ? from : to;
        Account second = from.id < to.id ? to : from;
        long one = first.lock.writeLock();
        try {
            long two = second.lock.writeLock();
            try {
                if (from.balance < amount) {
                    throw new IllegalStateException("insufficient balance");
                }
                from.balance -= amount;
                to.balance += amount;
            } finally {
                second.lock.unlockWrite(two);
            }
        } finally {
            first.lock.unlockWrite(one);
        }
    }

    public static void main(String[] args) throws Exception {
        SafeCounter count = new SafeCounter();
        count.addAndGet(5);
        System.out.println("Safe nested helper: " + count.addAndGet(2));
        Snapshot snapshot = count.snapshot();
        System.out.println("Snapshot: " + snapshot.value()
                + " / " + snapshot.updates());

        boolean[] probes = selfAcquisitionChecks();
        System.out.println("Write then write try denied: " + probes[0]);
        System.out.println("Write then read try denied: " + probes[1]);
        System.out.println("Write then optimistic denied: " + probes[2]);
        System.out.println("Read then write try denied: " + probes[3]);
        System.out.println("Read conversion success: " + probes[4]);
        boolean blocked = secondReaderStopsUpgrade();
        if (!blocked) throw new AssertionError("conversion should fail");
        System.out.println("Second reader blocks upgrade: " + blocked);

        Account a = new Account(1, 10_000);
        Account b = new Account(2, 10_000);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> f1 = pool.submit(() -> {
                for (int i = 0; i < 1_000; i++) transfer(a, b, 10);
            });
            Future<?> f2 = pool.submit(() -> {
                for (int i = 0; i < 1_000; i++) transfer(b, a, 10);
            });
            f1.get(10, TimeUnit.SECONDS);
            f2.get(10, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
        int aResult = a.readBalance();
        int bResult = b.readBalance();
        if (aResult != 10_000 || bResult != 10_000) {
            throw new AssertionError("balance invariant broken");
        }
        System.out.println("Transfers: 2000");
        System.out.println("Final balances: " + aResult + " / " + bResult);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StampedDeadlockSafetyDemo.java
java StampedDeadlockSafetyDemo
~~~

Stdout đã xác minh:

~~~text
Safe nested helper: 7
Snapshot: 7 / 2
Write then write try denied: true
Write then read try denied: true
Write then optimistic denied: true
Read then write try denied: true
Read conversion success: true
Second reader blocks upgrade: true
Transfers: 2000
Final balances: 10000 / 10000
~~~

### 11.1. Đọc kết quả

`Safe nested helper: 7` và `Snapshot: 7 / 2` nghĩa là hai update thành công. Những dòng `Write then ... denied: true` và `Read then write try denied: true` mô tả điều kiện không thể cấp quyền mới. `Read conversion success: true` cho thấy conversion hợp lệ khi không có reader khác; `Second reader blocks upgrade: true` kiểm nhánh thất bại có thể tái hiện nhờ latch.

`Transfers: 2000` và `Final balances: 10000 / 10000` cho thấy hai worker hoàn tất khi cùng dùng total lock order. Test không in scheduling, nanoseconds hoặc raw stamp vì những giá trị ấy không xác định giữa các lần chạy.

### 11.2. Những giới hạn của demo

Mỗi tài khoản có ID duy nhất, số dư ban đầu 10.000; một chiều có tối đa 1.000 lượt × 10 nên dù chạy trước toàn bộ, số dư không âm. Demo từ chối trùng ID và same-account transfer để tránh việc lấy cùng lock hai lần.

Timeout của `Future.get` / latch giúp test phát hiện tình trạng treo, **nhưng không hứa hủy được** một thread đang kẹt trong `writeLock()` không interruptible; vì vậy code không chủ động tạo self-deadlock thật.

## 12. Kiểm thử deadlock và nguy cơ starvation

| Test | Cách làm | Expected |
|---|---|---|
| Write rồi thử write | `tryWriteLock` dưới write | 0 |
| Write rồi thử read | `tryReadLock` dưới write | 0 |
| Read rồi thử write | `tryWriteLock` dưới read | 0 |
| Conversion không cạnh tranh | `tryConvertToWriteLock` | Có thể khác zero |
| Reader thứ hai đang giữ | Latch + conversion | Trả zero |
| Helper không reenter | Kiểm call graph | Không acquire lồng |
| A→B đồng thời B→A | Hai worker, lock ID tăng | Hoàn tất, đúng số dư |
| Exception trong critical section | Fault injection | Finally unlock |
| Lock timeout | Timed try method | Xử lý zero/interrupt |
| Optimistic bị writer invalidate | `validate` | Fallback read |
| Lock leak | Stress/cleanup | Không giữ stamp bỏ quên |

**Không dùng `Thread.sleep` để tạo race**: nó chỉ tác động lịch chạy, không bảo đảm reader thứ hai đã giữ quyền. CountDownLatch tạo một điểm phối hợp rõ ràng.

### 12.1. Deadlock và starvation khác nhau

**Deadlock:** có chu trình chờ mà các bên không thể tự tiến triển. Self-deadlock là trường hợp một thread tự đợi quyền mà nó chưa thể nhả. AB–BA là hai thread giữ hai khóa theo thứ tự ngược.

**Starvation:** một thread chờ rất lâu dưới cạnh tranh hoặc scheduling; chưa chắc có cycle. StampedLock không cam kết ưu tiên reader/writer cố định. Một `tryWriteLock` trả zero không chứng minh deadlock.

**Long critical section:** một thread giữ lock lâu vì CPU, network hoặc callback; có thể làm hệ thống rất chậm nhưng vẫn có tiến triển.

### 12.2. Debug production

Với quyền quản trị JVM phù hợp, lấy thread dump:

~~~bash
jcmd <PID> Thread.print
~~~

Đây là lệnh minh họa, thay `<PID>` bằng PID thật. Xem thread đang chờ trong `StampedLock.readLock`/`writeLock`, stack gọi helper và các lock khác. Lấy nhiều dump để phân biệt chờ ngắn với kẹt lâu.

Vì StampedLock **không có owner thread thông thường**, một công cụ tự động dò deadlock có thể không phân tích đầy đủ mọi cycle StampedLock. `ThreadMXBean.findDeadlockedThreads` không nên là bằng chứng duy nhất rằng không có deadlock. Phối hợp call graph, lock-order graph, thread dumps và telemetry.

### 12.3. Metrics nên quan sát

Đo thời gian chờ lock, thời gian giữ lock, mode yêu cầu, logical resource ID, tỉ lệ conversion thất bại, deadline/interrupt, p95/p99 latency và số request đang chờ. Không dùng raw stamp làm label metric; stamp không phải ID nghiệp vụ ổn định và cardinality có thể cao.

## 13. Checklist khi review code dùng StampedLock

1. Có public method đang giữ stamp mà gọi tiếp public method khác xin lại cùng lock không?
2. Getter/callback/serializer có thể lấy read/write lock từ trong write critical section không?
3. Có code giữ read rồi chờ writeLock trên cùng StampedLock không?
4. Khi conversion trả zero, code có giữ read stamp cũ để unlock không?
5. Sau khi nhả read rồi xin write, có **recheck điều kiện** không?
6. Sau conversion thành công, có dùng stamp mới và nhả đúng mode không?
7. Mọi early return/exception có đi qua finally unlock không?
8. Có lấy hai hoặc nhiều locks trong cùng call path không?
9. Quy tắc total ordering có bao phủ mọi hướng nghiệp vụ và helper không?
10. Định danh dùng ordering có bất biến và duy nhất không?
11. Có callback/I/O/`Future.join` trong critical section không?
12. Có timeout/interrupt khi request cần giới hạn chờ không?
13. Test có dùng try/latch thay vì gây self-deadlock thật không?
14. Test coordinator có `Future.get(timeout)` để bắt lỗi worker không?
15. Thread dump/metric có đủ stage, lock ID và mode để điều tra không?

## 14. Những sai lầm phổ biến

**1. Coi StampedLock như ReentrantLock.** Không có owner recursion count.

**2. Write→write bằng blocking call.** Thread có thể tự deadlock.

**3. Write→read qua getter.** Read mới không tự được cấp khi đã giữ write.

**4. Read→write bằng writeLock khi read còn giữ.** Read của chính mình cản write.

**5. Gọi public updater từ updater đang khóa.** Dùng private helper under-write.

**6. Callback bên ngoài dưới lock gọi lại API.** Dời callback ra ngoài nếu chính sách cho phép.

**7. Đọc thêm read stamp đôi khi thành công rồi coi là reentrancy.** Mỗi acquire độc lập.

**8. Ghi đè read stamp bằng zero sau convert thất bại.** Gây leak hoặc unlock sai.

**9. Nhả read stamp cũ sau convert thành công.** Sai mode/double unlock.

**10. Không recheck sau release-read/acquire-write.** Dữ liệu có thể thay đổi.

**11. Spin chuyển mode vô hạn khi còn giữ read.** Không có progress guarantee.

**12. Lấy hai lock theo from→to tùy hướng.** Có thể AB–BA deadlock.

**13. Không xử lý same object hoặc ID trùng.** Có thể xin lại cùng lock hoặc phá lock order.

**14. Gọi network/database/`Future.join` khi giữ write.** Tạo chờ kéo dài hoặc dependency cycle.

**15. Dùng timed acquisition như thuốc chữa reentrancy.** Timeout chỉ giới hạn chờ.

**16. Nuốt InterruptedException rồi tiếp tục spin.** Làm mất tín hiệu hủy.

**17. Quên finally.** Exception có thể rò lock.

**18. Unlock optimistic stamp.** Optimistic không nắm read/write hold.

**19. Coi validate(true) là quyền ghi hoặc bảo đảm bất biến mãi mãi.** Không đúng.

**20. Duyệt cấu trúc mutable phức tạp trong optimistic read.** Có thể không nhất quán trước validate.

**21. Coi lock views là reentrant.** Adapter không thay semantics underlying.

**22. Tin deadlock detector báo âm tính là đủ.** StampedLock ownerless cần điều tra thêm.

**23. Test gây deadlock thật không có isolation.** Có thể treo test suite.

**24. Đo throughput nhưng bỏ qua progress.** Tốc độ một case không chứng minh absence of deadlock.

**25. Log stamp numeric làm metric label.** Không có ý nghĩa ID bền vững.

## 15. Bài tập tự luyện

1. Non-reentrant nghĩa là gì?
2. Vì sao StampedLock không có owner nhưng vẫn không reentrant?
3. `tryWriteLock()` trả gì dưới write lock đang giữ?
4. `tryReadLock()` trả gì khi có write lock?
5. Vì sao read→write bằng writeLock blocking có nguy cơ kẹt?
6. `tryConvertToWriteLock` có chờ reader khác nhả lock không?
7. Conversion thất bại thì read stamp cũ cần được xử lý thế nào?
8. Vì sao phải recheck trạng thái sau khi nhả read rồi xin write?
9. Callback có thể tạo self-deadlock gián tiếp thế nào?
10. Hai thread chuyển A→B và B→A có thể tạo AB–BA bằng cách nào?
11. Vì sao ID dùng lock ordering phải unique và immutable?
12. Same Account ở from/to cần xử lý thế nào?
13. Có thể unlock một optimistic stamp không?
14. `validate` trả true có cấp quyền ghi không?
15. Timeout có làm lock reentrant không?
16. Vì sao `Thread.sleep` không phải cách kiểm race xác định?
17. Khi test cần tránh gọi blocking method nào hai lần trên cùng lock?
18. `Future.get(timeout)` ở coordinator giúp gì?
19. Vì sao thread dump không phát hiện cycle tự động chưa chứng minh an toàn?
20. Khi nào chọn `ReentrantReadWriteLock` thay StampedLock?

**Đáp án gợi ý:** (1) Không cho thread tự acquire lại lock theo owner recursion. (2) Stamp là capability theo state, không có owner hold count. (3) Zero. (4) Zero. (5) Chính read cản write mà lệnh nhả nằm sau acquire. (6) Không, thử ngay. (7) Giữ handle và nhả read nếu không còn cần. (8) State có thể đổi trong khoảng trống. (9) Listener gọi lại getter/updater có lock. (10) T1 giữ A đợi B; T2 giữ B đợi A. (11) Tạo một thứ tự toàn cục không nhập nhằng. (12) Từ chối hoặc xử lý no-op phù hợp. (13) Không. (14) Không. (15) Không. (16) Không bảo đảm interleaving. (17) writeLock dưới write hoặc readLock dưới write; read giữ rồi writeLock. (18) Đợi task hoàn thành, nhận exception và phát hiện timeout. (19) Ownerless lock có thể không hiển thị như ownable synchronizer. (20) Khi cần reentrancy, Condition, hoặc giao diện code không phù hợp stamp.

## Tổng kết

`StampedLock` là lock **non-reentrant** dù hỗ trợ cả read và write. Khi đã giữ write, không xin lại read/write từ helper; khi giữ read, không chờ `writeLock` để nâng cấp. Dùng private helper under-lock và `tryConvertToWriteLock` có kiểm kết quả, nhả read rồi **recheck** nếu phải xin write từ đầu. Khi có nhiều StampedLock, mọi thread cần thống nhất lock ordering bất biến để tránh AB–BA; xử lý cùng đối tượng và ID trùng. Quản lý đúng lifetime stamp và finally. Để kiểm thử, dùng try methods, latch, timeout và review call graph thay vì tự gây deadlock thật. Giám sát cả deadlock, starvation và hold time dài, không chỉ xem kết quả một lần chạy.

### Nguồn chính thức vẫn còn hiệu lực

- [Oracle Java SE 26 — StampedLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [Oracle Java SE 26 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java SE 26 — jcmd](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
