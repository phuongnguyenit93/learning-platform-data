# Try lock, timeout và phản hồi interrupt trong StampedLock

> **Chủ đề:** Java 8 → StampedLock → Try lock, timeout và phản hồi interrupt. Bài tập trung vào cách **thử lấy khóa không chờ**, **chờ có giới hạn thời gian**, **thoát khi thread bị interrupt**, và **quản lý stamp/giải phóng khóa an toàn**. Các API chính được dùng đã có từ Java 8 và vẫn được hỗ trợ trong các JDK hiện hành.

## 1. Vì sao ba yêu cầu “try”, “timeout”, “interrupt” khác nhau?

Khi nhiều thread chia sẻ trạng thái, một thread có thể phải đợi thread khác hoàn thành thao tác ghi hoặc đọc. Giả sử một service có hai yêu cầu:

- **Request xem thông tin:** nếu dữ liệu đang bị giữ khóa ghi, có thể trả kết quả “bận”, dùng cache hoặc bỏ qua thay vì chặn thread vô thời hạn.
- **Request cập nhật:** có thể chờ khóa ghi tối đa 100 ms; nếu không có khóa thì trả thông báo đang quá tải.
- **Request đã bị hủy:** khi user ngắt request hoặc hệ thống shutdown, thread đang chờ nên có khả năng kết thúc sớm khi nhận tín hiệu `interrupt`.

Ba ý định tương ứng những nhóm API riêng:

1. **Try lock tức thời:** `tryReadLock()`, `tryWriteLock()`. Thử lấy ngay; nếu thất bại trả **`0L`** thay vì chờ.
2. **Try lock có timeout:** `tryReadLock(long,TimeUnit)`, `tryWriteLock(long,TimeUnit)`. Có thể đợi tới thời hạn; nếu hết thời gian mà chưa lấy được khóa, trả **`0L`**; nếu bị interrupt, ném **`InterruptedException`**.
3. **Chờ có thể bị interrupt, không đặt timeout:** `readLockInterruptibly()` và `writeLockInterruptibly()`. Chờ đến khi lấy được khóa hoặc bị interrupt.
4. **Chờ thông thường:** `readLock()` và `writeLock()`. Chờ đến khi lấy được khóa theo hợp đồng thông thường; không có checked `InterruptedException` từ các method này.

**`StampedLock` không reentrant:** cùng một thread có thể tự chặn nếu giữ read stamp rồi gọi `writeLock()` mà không có protocol upgrade/release, hoặc giữ write stamp rồi lại gọi `readLock()`. Thời hạn và interruption là hai công cụ quan trọng để tránh chờ vô hạn, nhưng **không thay thế thiết kế thứ tự khóa đúng**.

### 1.1. Đầu ra của các method là một stamp, không phải boolean

Khác `ReentrantLock.tryLock()` trả `boolean`, `StampedLock.tryWriteLock()` trả `long`.

~~~java
StampedLock lock = new StampedLock();

long stamp = lock.tryWriteLock();

if (stamp == 0L) {
    // Không lấy được khóa.
} else {
    try {
        // Đã giữ write lock; có thể cập nhật trạng thái được bảo vệ.
    } finally {
        lock.unlockWrite(stamp);
    }
}
~~~

Đây là **đoạn minh họa** Java 8, cần import `java.util.concurrent.locks.StampedLock`.

**Quy tắc:** stamp bằng `0L` nghĩa là thao tác thử lấy khóa **không thành công**. Không dùng `unlockWrite(0L)`, `unlockRead(0L)`, hoặc `unlock(0L)`. Chỉ giải phóng khi đã lấy được stamp hợp lệ và đúng mode.

### 1.2. Stamp là khả năng (capability), không phải số đếm hay ID

`StampedLock` dùng một số `long` đại diện cho version/mode của trạng thái khóa. Không tự phân tích bit, tăng/giảm, lưu stamp lâu như identifier nghiệp vụ, hay giả định các stamp luôn tăng 1. Dùng nó làm đối số cho method unlock, convert hoặc validate phù hợp **của đúng instance khóa đã tạo stamp đó**.

Khác một số lớp lock khác, StampedLock **không gắn ownership với thread**; về nguyên tắc, một stamp lấy ở thread này có thể được bàn giao và giải phóng ở thread khác. Tuy nhiên, việc bàn giao phải được đồng bộ hóa đúng, tránh double unlock hoặc mất quyền truy cập trạng thái được bảo vệ. Pattern an toàn mặc định là giữ stamp cục bộ và release trong `finally` của cùng logic đang bảo vệ.

## 2. Bảng API: lấy ngay, chờ, timeout và interrupt

| Method | Mục tiêu | Chờ khi bận? | Hết hạn | Bị interrupt trong lúc chờ |
| --- | --- | --- | --- | --- |
| `tryReadLock()` | Lấy read lock ngay | Không | Không có timeout | Không ném `InterruptedException` |
| `tryWriteLock()` | Lấy write lock ngay | Không | Không có timeout | Không ném `InterruptedException` |
| `tryReadLock(t,unit)` | Read lock có deadline tương đối | Tối đa thời hạn | Trả `0L` | Ném `InterruptedException` |
| `tryWriteLock(t,unit)` | Write lock có deadline tương đối | Tối đa thời hạn | Trả `0L` | Ném `InterruptedException` |
| `readLockInterruptibly()` | Read lock, hủy bằng interrupt | Có, không đặt timeout | Không có deadline | Ném `InterruptedException` |
| `writeLockInterruptibly()` | Write lock, hủy bằng interrupt | Có, không đặt timeout | Không có deadline | Ném `InterruptedException` |
| `readLock()` | Read lock thông thường | Có | Không có deadline | Không chủ động thoát bằng `InterruptedException` |
| `writeLock()` | Write lock thông thường | Có | Không có deadline | Không chủ động thoát bằng `InterruptedException` |
| `tryOptimisticRead()` | Lấy optimistic stamp để kiểm chứng | Không | Không có timeout | Không ném `InterruptedException` |

**Lưu ý:** `tryOptimisticRead()` **không thực sự giữ read lock**. Nó khác hoàn toàn `tryReadLock()`; caller phải kiểm tra `validate(stamp)` sau khi copy các trường phù hợp vào biến cục bộ. Phần 10 trình bày ngắn để tránh nhầm hai method có tên “try”.

### 2.1. Ý nghĩa của t và unit

Các overload có thời hạn nhận:

~~~java
long stamp = lock.tryWriteLock(100, TimeUnit.MILLISECONDS);
~~~

Đây là **đoạn minh họa**; cần import `java.util.concurrent.TimeUnit`. Giá trị `100` là thời gian đợi tối đa theo đơn vị `MILLISECONDS`, không phải timestamp tuyệt đối, không phải 100 nanosecond, và không phải một `Duration` object.

Timeout là **chính sách mức chờ**: hết khoảng thời gian mà lock chưa được cấp thì method trả `0L`. Không nên viết logic phụ thuộc kết quả đo chính xác bằng `100.000000 ms`; scheduling, clock granularity và hệ thống có thể khiến thời điểm method trở về biến động.

### 2.2. Cả timeout và interrupt đều không chứng minh “lỗi khóa”

- `0L` không phải exception. Nó báo lần thử hiện tại **không nhận được stamp**, chưa đủ để kết luận lock bị hỏng.
- `InterruptedException` là tín hiệu **thread đang chờ được yêu cầu ngắt**, không có nghĩa dữ liệu bên trong khóa sai.
- Một lần try thất bại **không chứng minh** thread khác đang giữ write lock ngay tại thời điểm caller xử lý kết quả, vì trạng thái có thể đã đổi.
- Tên API không hứa fairness. Đừng thiết kế business logic dựa vào việc waiter lâu nhất sẽ được chọn trước.

## 3. tryReadLock(): đọc ngay nếu được, không thì đi đường dự phòng

Một read lock cho phép nhiều reader cùng truy cập, nhưng không đồng tồn tại với write lock của cùng StampedLock. Try read tức thời phù hợp với tác vụ ngắn không chấp nhận block.

~~~java
public String tryReadStatus() {
    long stamp = lock.tryReadLock();
    if (stamp == 0L) {
        return "BUSY";
    }
    try {
        return status; // Trạng thái do cùng lock bảo vệ.
    } finally {
        lock.unlockRead(stamp);
    }
}
~~~

Đây là **method minh họa bên trong class** có field `StampedLock lock` và `String status`. Method không phải một file độc lập. Cần xác nhận mọi writer của `status` cũng dùng cùng protocol; một lock không bảo vệ được dữ liệu bị thay đổi bên ngoài protocol.

### 3.1. Khi có writer, thử read thường thất bại

~~~java
StampedLock lock = new StampedLock();
long write = lock.writeLock();

try {
    long read = lock.tryReadLock();
    System.out.println(read == 0L); // true
} finally {
    lock.unlockWrite(write);
}
~~~

Trong đoạn trên, write lock đã được giữ nên read lock không thể được cấp. Vì thử **không chờ**, phương thức trở lại với zero.

### 3.2. Không coi thiếu dữ liệu do bận là dữ liệu thật

Nếu không lấy được khóa, caller nên chọn chính sách tường minh:

- Trả result loại `BUSY` hoặc `RETRY_LATER`.
- Dùng một cache đã được công bố an toàn và chấp nhận staleness.
- Bỏ qua phép lấy metrics không quan trọng.
- Retry sau một khoảng thời gian có giới hạn hoặc dùng timed try.

**Không** tự đọc field đang được bảo vệ khi `tryReadLock()==0L` như thể đã có quyền; đó là vi phạm protocol đồng bộ. Nếu có sẵn một giá trị immutable/volatile snapshot độc lập, phải bảo đảm tính nhất quán của snapshot bằng thiết kế riêng.

## 4. tryWriteLock(): cập nhật ngay nếu không có reader/writer cạnh tranh

Write lock là **exclusive**: khi đã được giữ, một write lock khác và các read lock khác không được cấp.

~~~java
public boolean trySetStatus(String newStatus) {
    long stamp = lock.tryWriteLock();
    if (stamp == 0L) {
        return false;
    }
    try {
        status = newStatus;
        return true;
    } finally {
        lock.unlockWrite(stamp);
    }
}
~~~

Đây là **method minh họa** cùng class ở mục 3. Boolean business trả false chỉ để báo **không nhận được quyền cập nhật**, không đánh đồng với lỗi validation của `newStatus`.

### 4.1. Khi reader đang giữ khóa, write thử ngay trả zero

~~~java
StampedLock lock = new StampedLock();
long read = lock.readLock();
try {
    System.out.println(lock.tryWriteLock() == 0L); // true
} finally {
    lock.unlockRead(read);
}
~~~

Đây là đoạn chạy ngắn Java 8 minh họa. Với read lock còn giữ, writer không thể lấy quyền exclusive.

### 4.2. Đừng retry trong vòng while không giới hạn

~~~java
// PHẢN VÍ DỤ: đốt CPU và không có chính sách dừng.
while (lock.tryWriteLock() == 0L) {
    // Spin vô hạn nếu lock luôn bận.
}
~~~

Còn một vấn đề nghiêm trọng: nếu vòng lặp cuối cùng lấy được stamp, đoạn code phản ví dụ **đánh mất stamp thành công**, không có cách unlock. Đây là lý do không được dùng try lock như một boolean check rồi bỏ kết quả.

Nếu thật sự cần retry, quản lý deadline/backoff/cancellation và **giữ stamp trả về**:

~~~java
long stamp = lock.tryWriteLock();
if (stamp != 0L) {
    try {
        // Thực hiện tác vụ ngắn.
    } finally {
        lock.unlockWrite(stamp);
    }
}
~~~

Với các ứng dụng cần chờ giới hạn, overload timed thường rõ ràng hơn một busy-spin tùy tiện.

## 5. tryReadLock(timeout, TimeUnit): chờ read có giới hạn

Chữ ký Java 8:

~~~java
public long tryReadLock(long time, TimeUnit unit)
        throws InterruptedException
~~~

Nó có thể:

1. **Trả stamp khác zero** nếu lấy được read lock trong khoảng chờ.
2. **Trả `0L`** nếu không lấy được khóa trong giới hạn.
3. **Ném `InterruptedException`** nếu thread bị ngắt trước khi lấy được khóa, theo semantics của `Lock.tryLock(timeout,unit)`.

Một ví dụ method gọi dịch vụ:

~~~java
public String readWithTimeout(long timeoutMillis)
        throws InterruptedException {
    long stamp = lock.tryReadLock(
            timeoutMillis, TimeUnit.MILLISECONDS);
    if (stamp == 0L) {
        return "READ_TIMEOUT";
    }
    try {
        return status;
    } finally {
        lock.unlockRead(stamp);
    }
}
~~~

Đây là **method minh họa** với field `lock` và `status` trong cùng class. Nếu bị interrupt, method ném exception cho caller; nó **không** âm thầm chuyển interrupt thành chuỗi `"READ_TIMEOUT"`.

### 5.1. Timeout và interrupt là hai lối ra riêng

~~~text
       tryReadLock(timeout, unit)
                 |
       +---------+---------+
       |                   |
    được cấp            chưa được cấp
       |                   |
   stamp != 0      +-------+--------+
       |            |               |
     try/finally   hết hạn        bị interrupt
       |            |               |
   unlockRead     trả 0L       InterruptedException
~~~

Nếu xây API HTTP hoặc message processing, hai loại có thể dẫn đến hai response khác:

- **Timeout chờ lock:** trả busy, retryable hoặc metric lock contention.
- **Interrupt:** giữ ý nghĩa cancellation/shutdown, thường phải dừng thao tác và propagate.

### 5.2. Timeout 0/âm không có nghĩa luôn thất bại

Overload timed có thể thử lấy khóa ngay nếu có thể; nếu khóa đã sẵn sàng và thread không bị interrupt, việc nhận stamp thành công có thể xảy ra dù thời gian đợi là 0. Khi timeout không dương, không nên mong có một giai đoạn chờ dài.

Nếu mục tiêu **hoàn toàn không chờ và không có checked exception**, dùng `tryReadLock()` không tham số thay vì dựa vào `tryReadLock(0,unit)`.

### 5.3. Không nên giữ khóa lâu sau khi đã mất thời gian đợi

Khi đã lấy được read lock, caller nên xử lý nhanh phần thực sự cần bảo vệ, copy dữ liệu hoặc tạo snapshot hợp lệ rồi unlock. **Đặt timeout chỉ giới hạn thời gian chờ lấy khóa**, không giới hạn thời gian **công việc bên trong critical section**.

Ví dụ `tryReadLock(100, MILLISECONDS)` thành công không có nghĩa phần code trong `try/finally` sẽ tự dừng sau 100 ms.

## 6. tryWriteLock(timeout, TimeUnit): chờ quyền ghi có giới hạn

Chữ ký:

~~~java
public long tryWriteLock(long time, TimeUnit unit)
        throws InterruptedException
~~~

Mẫu Java 8:

~~~java
public boolean updateWithinBudget(int nextValue, long waitMillis)
        throws InterruptedException {
    long stamp = lock.tryWriteLock(
            waitMillis, TimeUnit.MILLISECONDS);
    if (stamp == 0L) {
        return false;
    }
    try {
        value = nextValue;
        return true;
    } finally {
        lock.unlockWrite(stamp);
    }
}
~~~

Đây là **method minh họa** có fields `lock` và `value`. Trả false ở đây nghĩa là **không cấp được quyền ghi trong thời hạn**, chứ không có nghĩa dữ liệu đã được cập nhật thất bại sau khi ghi.

### 6.1. Không được nhầm thời hạn của lock với deadline nghiệp vụ

Giả sử cả request có ngân sách 250 ms, trong đó dành 150 ms cho I/O và tối đa 100 ms chờ lock. Nếu trước khi tới bước lock request đã mất 240 ms, chờ khóa thêm đủ 100 ms sẽ **vượt ngân sách tổng**.

Nếu ứng dụng cần deadline end-to-end:

- Tính thời gian còn lại theo clock đơn điệu phù hợp cho đo khoảng thời gian.
- Chỉ cấp cho `tryWriteLock` phần **ngân sách còn lại**, không luôn chờ timeout cố định.
- Sau khi lấy lock vẫn phải tự kiểm tra deadline/cancellation khi cần.
- Dùng try/finally để release stamp dù nghiệp vụ phát hiện deadline đã qua.

Không biến timeout của lock thành cam kết SLA toàn request; đó chỉ là một chặng.

### 6.2. Nếu timeout, không thực hiện thao tác ghi

~~~java
long stamp = lock.tryWriteLock(75, TimeUnit.MILLISECONDS);
if (stamp == 0L) {
    // Ghi metric timeout, trả status hoặc retry theo policy.
    return;
}
try {
    sharedValue++;
} finally {
    lock.unlockWrite(stamp);
}
~~~

Đây là **đoạn minh họa bên trong method**, cần field `sharedValue` và `lock`, cùng import `TimeUnit`. Sau khi stamp zero, không được thực hiện update thiếu khóa. Sau khi thành công, unlock ngay cả khi phần tăng ném exception runtime.

## 7. readLockInterruptibly và writeLockInterruptibly

Khi caller muốn **chờ cho tới lúc có khóa** nhưng phải phản hồi cancellation, dùng:

~~~java
long readStamp = lock.readLockInterruptibly();
long writeStamp = lock.writeLockInterruptibly();
~~~

Hai method đều khai báo `throws InterruptedException`. **Không gọi cả hai liên tiếp và giữ stamp đầu** trong code thực khi không có protocol chuyển mode: StampedLock không reentrant, việc lấy write khi đã giữ read có thể tự chờ mãi.

### 7.1. Mẫu read interruptible

~~~java
public int readInterruptibly() throws InterruptedException {
    long stamp = lock.readLockInterruptibly();
    try {
        return sharedValue;
    } finally {
        lock.unlockRead(stamp);
    }
}
~~~

Đây là **method minh họa**. `InterruptedException` xảy ra **trước khi stamp được cấp** và làm lời gọi không nhận lock. Vì vậy, đặt `try/finally` **sau khi** đã nhận stamp, không unlock khi acquisition chưa thành công.

### 7.2. Mẫu write interruptible

~~~java
public void writeInterruptibly(int nextValue)
        throws InterruptedException {
    long stamp = lock.writeLockInterruptibly();
    try {
        sharedValue = nextValue;
    } finally {
        lock.unlockWrite(stamp);
    }
}
~~~

Những method này phù hợp với worker bị cancel, executor shutdown, hoặc một protocol yêu cầu thread ngừng chờ khi đã không còn lý do tiếp tục.

### 7.3. InterruptedException có nghĩa gì?

Khi thread đang chờ trong một thao tác interruptible:

- Một thread khác có thể gọi `waitingThread.interrupt()`.
- Việc chờ có thể dừng bằng `InterruptedException`.
- Theo hành vi của các interruptible waits trong Java, interrupt status thường **được xóa khi exception được ném**.
- Nếu bắt exception và không truyền lên caller, ứng dụng thường cần **khôi phục interrupt flag** để các tầng cao hơn nhận biết tín hiệu.

~~~java
try {
    long stamp = lock.readLockInterruptibly();
    try {
        // Đọc dữ liệu.
    } finally {
        lock.unlockRead(stamp);
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Khôi phục tín hiệu.
    // Trở về hoặc ngừng task, không tiếp tục chờ lặp vô hạn.
}
~~~

Đây là **đoạn minh họa** trong method. Không có một xử lý interruption chung đúng cho mọi ứng dụng; có thể chọn **propagate InterruptedException** lên caller nếu method khai báo throws, hoặc restore flag và thoát nếu không thể throw.

### 7.4. Bắt xong rồi tiếp tục loop là hành vi nguy hiểm

~~~java
// PHẢN VÍ DỤ: làm mất ý nghĩa yêu cầu ngắt.
while (true) {
    try {
        lock.readLockInterruptibly();
        break;
    } catch (InterruptedException ignored) {
        // Nuốt interrupt rồi cứ chờ tiếp.
    }
}
~~~

Ví dụ còn bỏ qua stamp thành công và không unlock, khiến thiết kế càng sai. Nếu hệ thống đang shutdown, loop sẽ chống lại cancellation. **Không** nuốt interrupt, không bỏ stamp, và không tự retry vô hạn.

### 7.5. Đã lấy được khóa rồi, interrupt có tự unlock không?

**Không.** Interruption là cơ chế báo cho thread, không phải cơ chế thu hồi stamp đã cấp. Nếu caller đang làm việc trong critical section rồi bị interrupt, code cần tự xử lý theo contract và vẫn phải chạy `finally` để release stamp.

Nếu có một tác vụ I/O lâu chạy dưới write lock, timeout của lần acquisition **không giới hạn thời gian I/O**. Nên tránh giữ khóa xuyên network I/O khi có thể và tách tính toán ngoài lock khỏi cập nhật trạng thái nhỏ gọn trong lock.

## 8. readLock() và writeLock() thông thường không phải phiên bản interruptible

~~~java
long stamp = lock.readLock();
try {
    // Đọc trạng thái được bảo vệ.
} finally {
    lock.unlockRead(stamp);
}
~~~

`readLock()` có thể chờ nhưng **không khai báo `InterruptedException`**. `writeLock()` tương tự cho ghi. Khi đang cần chờ có thể bị hủy, chọn phiên bản `...Interruptibly()` hoặc timed try.

**Không giả định** gọi `interrupt()` sẽ làm một thread chờ trong `readLock()` hoặc `writeLock()` lập tức ném `InterruptedException` rồi thoát. Hãy xác định đúng method đã sử dụng.

### 8.1. Không reentrant: tự gây deadlock

~~~java
StampedLock lock = new StampedLock();
long read = lock.readLock();
try {
    // PHẢN VÍ DỤ: đừng gọi writeLock() ngay khi vẫn giữ read.
    // long write = lock.writeLock(); // Có thể chờ vô hạn.
} finally {
    lock.unlockRead(read);
}
~~~

Không thể chuyển từ read sang write một cách tùy tiện như reentrant lock. Nếu cần nâng quyền, cân nhắc `tryConvertToWriteLock(stamp)` và xử lý trả `0L`; hoặc release read rồi chờ write **và kiểm tra lại điều kiện** sau khi lấy được khóa.

### 8.2. Chọn ReentrantLock khi cần mô hình khác

Nếu bạn cần:

- Reentrancy.
- `Condition` với giao thức await/signal.
- Lock có ownership của thread theo mô hình `Lock`.
- Chính sách fair mode cụ thể.

Hãy cân nhắc `ReentrantLock` hoặc `ReentrantReadWriteLock`, tùy mục tiêu. **StampedLock không phải thay thế mặc định cho mọi loại Lock**. Nó được thiết kế cho các thuật toán nội bộ với read/write/optimistic modes và đòi hỏi người viết hiểu protocol.

## 9. Phản hồi interrupt trong timed try lock

Hai timed overload đều là **interruptible methods**. Caller phải phân biệt hai nhánh thất bại:

~~~java
public boolean attemptWrite(long timeoutMillis) {
    long stamp = 0L;
    try {
        stamp = lock.tryWriteLock(
                timeoutMillis, TimeUnit.MILLISECONDS);
        if (stamp == 0L) {
            return false; // TIMEOUT/BUSY
        }
        // Nếu chỉ thử lấy khóa, làm việc khi đã giữ quyền ghi ở đây.
        return true;
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return false; // Sản phẩm thật nên biểu diễn CANCEL khác TIMEOUT.
    } finally {
        if (stamp != 0L) {
            lock.unlockWrite(stamp);
        }
    }
}
~~~

Đây là **method minh họa**, không phải mẫu domain API khuyến nghị vì kiểu trả về boolean **không phân biệt timeout với cancellation**. Nên cân nhắc kiểu kết quả có trạng thái tường minh, ví dụ enum `SUCCESS`, `TIMEOUT`, `CANCELLED`, hoặc propagate InterruptedException cho caller.

### 9.1. Mẫu giữ nguyên hai outcome trong Java 8

~~~java
enum AcquireResult {
    SUCCESS, TIMEOUT, INTERRUPTED
}

AcquireResult runTimedRead(StampedLock lock, long waitMillis) {
    long stamp = 0L;
    try {
        stamp = lock.tryReadLock(waitMillis, TimeUnit.MILLISECONDS);
        if (stamp == 0L) {
            return AcquireResult.TIMEOUT;
        }
        try {
            // Copy/read dữ liệu phù hợp trong critical section.
            return AcquireResult.SUCCESS;
        } finally {
            lock.unlockRead(stamp);
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return AcquireResult.INTERRUPTED;
    }
}
~~~

Đây là **đoạn minh họa cần đặt enum và method trong class**, không phải file chạy độc lập. Dù ở đây outcome `SUCCESS` được trả, critical section vẫn chỉ nên đọc field cần bảo vệ; method không giữ lại lock sau return.

### 9.2. Kết hợp với Future và executor

Nếu một worker đang đợi `tryWriteLock(10,SECONDS)` và một thread khác gọi `Future.cancel(true)`, việc interruption **có thể** đánh thức worker đang chờ lock theo contract của timed try. Nhưng `Future.cancel(true)` không bảo đảm một kết quả ứng dụng cụ thể nếu task đã hoàn tất, chưa chạy hoặc xử lý interrupt không hợp tác.

Đừng viết test concurrency kiểu “sleep 50ms rồi cancel thì chắc chắn worker đang chờ”. Dùng synchronization gate/`CountDownLatch` để làm rõ pha bắt đầu và xác minh các bất biến cần thiết.

### 9.3. Nếu thread đã interrupted trước khi gọi timed try

Theo hợp đồng interruptible của `Lock.tryLock(timeout,unit)`, interrupt có thể được ưu tiên làm lời gọi ném `InterruptedException` ngay cả khi lock có thể sẵn. Không dùng timed try để “xóa cờ interruption” hoặc ngầm coi thread bị cancel là một caller bình thường.

Nếu code nghiệp vụ **chủ động xóa interrupt flag** bằng `Thread.interrupted()`, phải hiểu hàm đó trả và **clear** cờ; đừng đưa vào retry loop nếu không có lý do rõ ràng. `Thread.currentThread().isInterrupted()` chỉ kiểm tra trạng thái mà không clear.

## 10. Phân biệt tryOptimisticRead với tryReadLock

`StampedLock` hỗ trợ **optimistic read**, nhưng nó không lấy read lock thật.

~~~java
long stamp = lock.tryOptimisticRead();
if (stamp != 0L) {
    int localX = x;
    int localY = y;
    if (lock.validate(stamp)) {
        // localX/localY có thể dùng theo hợp đồng optimistic read.
    }
}
~~~

Đây là **đoạn minh họa trong class** với fields `lock`, `x`, `y`, giả định các writers cập nhật dưới write lock. Đọc dữ liệu optimistic có thể thấy trạng thái tạm thời không nhất quán; chỉ dùng bản sao cục bộ sau khi `validate(stamp)` thành công.

Nếu cần fallback khi validation thất bại:

~~~java
int localX, localY;
long optimistic = lock.tryOptimisticRead();

localX = x;
localY = y;

if (optimistic == 0L || !lock.validate(optimistic)) {
    long read = lock.readLock();
    try {
        localX = x;
        localY = y;
    } finally {
        lock.unlockRead(read);
    }
}
~~~

Đây là **đoạn minh họa**, và các fields phải có kiểu/biểu diễn cho phép đọc optimistic an toàn theo thiết kế. Với object graph phức tạp, đọc một reference/array chưa được xác thực có thể nguy hiểm; Javadoc nhấn mạnh phải hiểu invariants và không gọi những method không chịu được dữ liệu tạm thời racy.

### 10.1. Optimistic stamp không được unlock như read lock

~~~java
long optimistic = lock.tryOptimisticRead();
// Không gọi lock.unlockRead(optimistic).
// Dùng lock.validate(optimistic) để kiểm tra.
~~~

Optimistic stamp là **token quan sát**, không đại diện cho một read lock thực đang giữ. Khi `tryOptimisticRead()` trả `0L` vì có writer, caller có thể chọn fallback read lock (timed hoặc interruptible) phù hợp.

### 10.2. Timeout không áp dụng trực tiếp cho optimistic read

`tryOptimisticRead()` không có overload `(timeout,TimeUnit)` trong Java 8. Nó không chờ; caller có thể kiểm chứng và fallback. Nếu yêu cầu “chỉ chờ 100ms để đọc dữ liệu an toàn”, timed `tryReadLock(100,MILLISECONDS)` là lựa chọn rõ hơn.

### 10.3. Kết quả validate có thể chuyển từ true sang false

Một stamp optimistic được tạo khi không có writer có thể ban đầu `validate(stamp)==true`. Khi một writer lấy write lock rồi thay đổi trạng thái, `validate(stamp)` cũ về sau sẽ false. Hãy **validate sau khi đã lấy dữ liệu** chứ không chỉ trước, nếu muốn sử dụng optimistic read đúng.

## 11. Convert mode và zero: tránh quên stamp đang giữ

Ngoài try lock trực tiếp, StampedLock có:

- `tryConvertToWriteLock(stamp)`.
- `tryConvertToReadLock(stamp)`.
- `tryConvertToOptimisticRead(stamp)`.

Những method này **thử chuyển mode**, có thể trả **`0L`** khi không làm được. Nếu chuyển thành công, stamp mới phải được dùng cho các thao tác sau và khi unlock. Nếu thất bại, caller phải xử lý đúng stamp/mode cũ.

### 11.1. Upgrade read sang write có thể thất bại

~~~java
long stamp = lock.readLock();
boolean upgraded = false;
try {
    long nextStamp = lock.tryConvertToWriteLock(stamp);
    if (nextStamp != 0L) {
        stamp = nextStamp;
        upgraded = true;
        // Có quyền write lock khi upgraded == true.
    } else {
        // Vẫn đang giữ read lock ban đầu; không được ghi.
    }
} finally {
    lock.unlock(stamp); // Unlock theo mode hiện hành của stamp.
}
~~~

Đây là **đoạn minh họa**. `tryConvertToWriteLock` có thể không thành công vì còn reader khác. Không gọi `writeLock()` trong nhánh thất bại khi vẫn giữ read lock; StampedLock không reentrant, dễ deadlock.

### 11.2. Nếu phải release read rồi lấy write thì đọc lại điều kiện

Giữa lúc release read và lấy write, một thread khác có thể cập nhật dữ liệu. Không dùng kết luận tính dưới read lock cũ để thay đổi trạng thái sau khi lấy write mà **không re-check**.

### 11.3. tryConvert khác timed tryLock

Không có quy tắc “convert sẽ tự chờ 100ms” từ `tryConvertToWriteLock(stamp)`. Nếu muốn thời hạn lấy write sau khi chuyển đổi không thành công, phải thiết kế protocol: giải phóng đúng stamp cũ, thử timed write, kiểm tra lại state sau khi nhận lock, và xử lý timeout/interrupt bằng nhánh riêng.

## 12. Fairness, starvation và hiệu năng

### 12.1. StampedLock không hứa thứ tự phục vụ cụ thể

Javadoc nêu rằng chính sách scheduling không nhất quán ưu tiên reader hoặc writer; các try methods là best-effort, không nhất thiết theo quy tắc fairness. Vì vậy:

- Một caller đến trước có thể không được cấp trước.
- Một thread retry liên tục có thể chiếm cơ hội không công bằng với thread khác.
- `tryWriteLock()==0L` không chứng minh lock sẽ mãi không có.
- Không cam kết writer cuối cùng luôn thắng sau một số lần retry cụ thể.

### 12.2. Timed wait không phải bảo đảm fairness

Một timeout như `tryWriteLock(100,MILLISECONDS)` bảo đảm caller **có đường thoát hữu hạn nếu chưa được cấp khóa trong khoảng chờ**, không bảo đảm caller sẽ được cấp khóa trước những thread đến sau. Bảo đảm này quan trọng cho worker có deadline, nhưng không giải quyết mọi trường hợp starvation.

Nếu fairness là yêu cầu cứng, xem xét primitive có hỗ trợ policy phù hợp như `ReentrantLock(true)` trong những bài toán thích hợp và kiểm tra lại throughput/tradeoff.

### 12.3. Không giữ lock qua network I/O nếu có thể tránh

Một write lock giữ quá lâu có thể khiến nhiều readers/writers timed out. Tách:

1. Chuẩn bị dữ liệu hoặc gọi dịch vụ ngoài lock khi an toàn.
2. Lấy khóa với timeout.
3. Kiểm tra lại điều kiện cần và cập nhật state được bảo vệ.
4. Unlock trong finally.
5. Thực hiện I/O còn lại ngoài lock nếu protocol cho phép.

Không tách một transaction nhiều biến theo kiểu làm hỏng invariant; việc giảm lock hold time phải đi cùng đúng mô hình consistency.

### 12.4. Không benchmark từ một lần chạy demo

StampedLock, ReentrantReadWriteLock và synchronized có tradeoff khác nhau tùy số reader/writer, critical-section length, contention, CPU và JDK. Benchmark phải đo workloads thật (như JMH), không dùng demo có chờ 50ms như thước đo performance.

## 13. Ví dụ hoàn chỉnh Java 8: thử tức thời, timeout, interrupt và unlock

Lưu đoạn sau thành **StampedTryLockDemo.java**. Chương trình dùng một `StampedLock`, giữ write lock trong main để tạo contention có kiểm soát. Bốn worker được thử interrupt khi đang chuẩn bị chờ; dù interrupt đến **trước** hay **sau** lúc worker thực sự vào method, các method interruptible đều xử lý yêu cầu ngắt theo contract.

**Chương trình đã được biên dịch với `javac --release 8` và chạy; stdout được kiểm tra.** Nó không cần hệ thống mạng, DB, timezone hoặc GUI.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.StampedLock;

public final class StampedTryLockDemo {
    private enum WaitMode {
        READ, WRITE, TIMED_READ, TIMED_WRITE
    }

    private static String interruptWhileBlocked(
            StampedLock lock, WaitMode mode) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicReference<String> result = new AtomicReference<>("NOT_INTERRUPTED");
        Thread worker = new Thread(() -> {
            long stamp = 0L;
            try {
                started.countDown();
                switch (mode) {
                    case READ:
                        stamp = lock.readLockInterruptibly();
                        break;
                    case WRITE:
                        stamp = lock.writeLockInterruptibly();
                        break;
                    case TIMED_READ:
                        stamp = lock.tryReadLock(10, TimeUnit.SECONDS);
                        break;
                    case TIMED_WRITE:
                        stamp = lock.tryWriteLock(10, TimeUnit.SECONDS);
                        break;
                    default:
                        throw new IllegalArgumentException("unsupported mode");
                }
                result.set(stamp == 0L ? "TIMED_OUT" : "ACQUIRED");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                result.set(Thread.currentThread().isInterrupted()
                        ? "INTERRUPTED_AND_RESTORED" : "NOT_RESTORED");
            } finally {
                if (stamp != 0L) {
                    lock.unlock(stamp);
                }
            }
        }, "waiting-" + mode);
        worker.start();
        started.await();
        worker.interrupt();
        worker.join(3000);
        if (worker.isAlive()) {
            throw new IllegalStateException("interruptible waiter did not exit");
        }
        return result.get();
    }

    public static void main(String[] args) throws Exception {
        StampedLock lock = new StampedLock();
        long heldWrite = lock.writeLock();
        try {
            System.out.println("immediate read failed = "
                    + (lock.tryReadLock() == 0L));
            System.out.println("immediate write failed = "
                    + (lock.tryWriteLock() == 0L));
            System.out.println("optimistic blocked by writer = "
                    + (lock.tryOptimisticRead() == 0L));
            System.out.println("timed read timeout = "
                    + (lock.tryReadLock(50, TimeUnit.MILLISECONDS) == 0L));
            System.out.println("timed write timeout = "
                    + (lock.tryWriteLock(50, TimeUnit.MILLISECONDS) == 0L));
            System.out.println("interruptible read = "
                    + interruptWhileBlocked(lock, WaitMode.READ));
            System.out.println("interruptible write = "
                    + interruptWhileBlocked(lock, WaitMode.WRITE));
            System.out.println("timed read interrupted = "
                    + interruptWhileBlocked(lock, WaitMode.TIMED_READ));
            System.out.println("timed write interrupted = "
                    + interruptWhileBlocked(lock, WaitMode.TIMED_WRITE));
        } finally {
            lock.unlockWrite(heldWrite);
        }

        long readStamp = lock.tryReadLock(1, TimeUnit.SECONDS);
        if (readStamp == 0L) {
            throw new IllegalStateException("unexpected read timeout");
        }
        try {
            System.out.println("timed read acquired = true");
            System.out.println("write blocked by reader = "
                    + (lock.tryWriteLock() == 0L));
        } finally {
            lock.unlockRead(readStamp);
        }

        long observation = lock.tryOptimisticRead();
        System.out.println("optimistic stamp acquired = "
                + (observation != 0L));
        System.out.println("optimistic initially valid = "
                + lock.validate(observation));

        long writeStamp = lock.tryWriteLock(1, TimeUnit.SECONDS);
        if (writeStamp == 0L) {
            throw new IllegalStateException("unexpected write timeout");
        }
        try {
            System.out.println("timed write acquired = true");
        } finally {
            lock.unlockWrite(writeStamp);
        }
        System.out.println("optimistic invalidated by write = "
                + !lock.validate(observation));

        long finalRead = lock.tryReadLock();
        if (finalRead == 0L) {
            throw new IllegalStateException("unexpected immediate read failure");
        }
        lock.unlockRead(finalRead);
        try {
            lock.unlockRead(finalRead);
            System.out.println("stale stamp rejected = false");
        } catch (IllegalMonitorStateException e) {
            System.out.println("stale stamp rejected = true");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 8 StampedTryLockDemo.java
java StampedTryLockDemo
~~~

**Stdout được xác minh:**

~~~text
immediate read failed = true
immediate write failed = true
optimistic blocked by writer = true
timed read timeout = true
timed write timeout = true
interruptible read = INTERRUPTED_AND_RESTORED
interruptible write = INTERRUPTED_AND_RESTORED
timed read interrupted = INTERRUPTED_AND_RESTORED
timed write interrupted = INTERRUPTED_AND_RESTORED
timed read acquired = true
write blocked by reader = true
optimistic stamp acquired = true
optimistic initially valid = true
timed write acquired = true
optimistic invalidated by write = true
stale stamp rejected = true
~~~

### 13.1. Lời gọi try tức thời trong lúc có write lock

Main giữ `heldWrite` nên hai lời gọi `tryReadLock()` và `tryWriteLock()` không được cấp, trả `0L`. `tryOptimisticRead()` cũng trả zero khi có write lock. Ba dòng đầu đều in true.

### 13.2. Timed try bị buộc hết hạn

Trong lúc main vẫn giữ write lock, chính main gọi `tryReadLock(50,MILLISECONDS)` rồi `tryWriteLock(50,MILLISECONDS)`. Vì main **chưa giải phóng write stamp** trong toàn bộ giai đoạn đó, hai lời gọi không thể được cấp quyền và trả zero sau khi hết thời hạn.

Đây là bài test về semantics của timeout, **không** là bài kiểm tra một method mất chính xác bao nhiêu millisecond.

### 13.3. Interruptible waits

Hàm `interruptWhileBlocked` tạo một worker và một `CountDownLatch`. Main đợi worker thông báo bắt đầu, gọi `interrupt()`, rồi `join(3000)` để xác minh worker dừng. Main vẫn giữ write lock, nên worker không thể lấy read/write lock trước khi thread được interrupt.

Cả bốn mode `READ`, `WRITE`, `TIMED_READ` và `TIMED_WRITE` đều ném `InterruptedException`. Handler tự khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` và kiểm tra lại bằng `isInterrupted()`. Vì vậy chuỗi kết quả là `INTERRUPTED_AND_RESTORED`.

**Không được hiểu đoạn mã bắt buộc interrupt phải xảy ra khi thread đã thực sự nằm trong hàng đợi.** Gate xác nhận worker bắt đầu, còn interrupt có thể đến ngay trước lời gọi acquisition; cả hai trường hợp đều hợp lệ và dự kiến được xử lý bởi method interruptible. Cách viết này tránh sleep hay giả định scheduling.

### 13.4. Thành công sau khi giải phóng write lock

Khi main unlock write:

- Timed read lấy được read stamp, in true.
- Khi còn giữ read stamp, write try tức thời không lấy được exclusive lock, in true.
- Sau khi unlock read, optimistic stamp không zero và ban đầu validate thành công.
- Một timed write lock tiếp theo thành công và được unlock; optimistic stamp cũ không còn valid do đã có write acquisition.

### 13.5. Double-unlock dùng stamp cũ

Đoạn cuối cố gọi `unlockRead(finalRead)` lần thứ hai sau khi stamp đã được giải phóng. Java ném `IllegalMonitorStateException` nên in `stale stamp rejected = true`. Đây là **kiểm tra minh họa lỗi sử dụng API**, không phải luồng production nên lặp lại double-unlock.

### 13.6. Giới hạn chương trình demo

- Không phải benchmark về throughput.
- Không dùng service/network, nên không mô phỏng mọi cách cancellation từ HTTP hay executor.
- Không kiểm thử fairness giữa hàng trăm waiters.
- Không có critical section truy cập dữ liệu nghiệp vụ, bởi mục đích chính là xác minh acquire/release/timeout/interrupt.
- Dùng assert logic và dữ liệu cố định, không đoán thứ tự luồng thắng.

## 14. Thiết kế ứng dụng thực: chính sách timeout và cancellation

### 14.1. Phân biệt ba trạng thái

Nếu API nghiệp vụ chỉ trả `boolean`, `false` có thể bị hiểu sai là “điều kiện cập nhật không hợp lệ” trong khi nguyên nhân thực là lock busy, timeout hoặc request bị cancel.

Một result type gọn:

~~~java
enum LockAttempt {
    ACQUIRED,
    TIMED_OUT,
    INTERRUPTED
}
~~~

Đây là **enum minh họa Java 8**. Một hệ thống lớn có thể cần thêm `VALIDATION_FAILED` hoặc `BUSINESS_REJECTED`, nhưng đó là outcome của **nghiệp vụ sau khi đã có khóa**, không nên gộp vào việc acquire stamp.

### 14.2. Retry khi timeout nên có giới hạn

Một policy retry hợp lý cân nhắc:

- Retry tối đa bao nhiêu lần?
- Tổng deadline còn bao nhiêu?
- Mỗi lần đợi bao lâu?
- Có jitter/backoff tránh thundering herd không?
- Nếu thread bị interrupt, có thoát ngay không?
- Nếu đã lấy lock rồi, critical section có đủ ngắn không?

**Không** viết loop vô hạn liên tục `tryWriteLock()`; nó tiêu CPU và không bảo đảm fairness, đồng thời tăng cạnh tranh khiến throughput tổng giảm.

### 14.3. Ghi metrics để xác định vấn đề contention

Một vài metrics hữu ích:

- Số lần try lock thành công.
- Số lần try lock trả zero.
- Số lần timed try hết hạn.
- Số lần bị interrupt.
- Thời gian chờ lock theo phân phối, không chỉ trung bình.
- Thời gian giữ write/read lock và số lượng người dùng đồng thời.

Không chạy network logging chậm bên trong critical section nếu có thể tránh. Những số liệu này giúp quyết định có thực sự cần StampedLock hay phải cải thiện kích thước critical section.

### 14.4. Không gộp mọi interrupt vào timeout

Đường `InterruptedException` có thể biểu diễn yêu cầu hủy task hoặc shutdown. Nếu chỉ log “lock timeout” sẽ làm hỏng khả năng phân tích. Hãy giữ nguyên thông tin cancellation, trả state phù hợp hoặc propagate exception.

### 14.5. Đảm bảo release trong mọi nhánh thành công

Những thao tác sau nên release stamp nếu đã lấy thành công:

- Return sớm do validation.
- Ném exception do xử lý.
- Phát hiện deadline nghiệp vụ.
- Thread bị interrupt **sau khi đã nhận lock**.
- Nhánh không còn muốn cập nhật.

`try/finally` bao quanh critical section là khuôn đơn giản và dễ kiểm tra nhất.

## 15. Những lỗi phổ biến và cách sửa

### Lỗi 1 — Nghĩ tryReadLock trả boolean

Sai: method trả `long stamp`. **Sửa:** kiểm tra `stamp == 0L`, lưu stamp thành công để unlock đúng.

### Lỗi 2 — Unlock khi stamp bằng zero

Zero là thất bại acquire, không đại diện cho lock. **Sửa:** chỉ unlock khi `stamp != 0L`.

### Lỗi 3 — Unlock sai mode

Dùng `unlockRead(writeStamp)` hoặc `unlockWrite(readStamp)` có thể ném `IllegalMonitorStateException`. **Sửa:** lưu mode hiện hành hoặc dùng `unlock(stamp)` đúng protocol.

### Lỗi 4 — Double unlock

Một stamp đã release không được dùng lần nữa để unlock. **Sửa:** một lần acquire được một nhánh `finally` unlock tương ứng duy nhất.

### Lỗi 5 — Không unlock khi phần xử lý throw

Nếu không có `finally`, lock có thể giữ mãi. **Sửa:** đặt critical section vào `try/finally` ngay sau khi acquire thành công.

### Lỗi 6 — Dùng readLock() rồi tưởng có thể bị interrupt ngay

`readLock()` không phải `readLockInterruptibly()`. **Sửa:** chọn đúng method cho tác vụ có cancellation.

### Lỗi 7 — Dùng writeLock() không deadline cho request ngắn

Nếu writer khác giữ khóa lâu, request có thể chờ ngoài ngân sách. **Sửa:** `tryWriteLock(timeout,unit)` và policy timeout rõ.

### Lỗi 8 — Nghĩ timed try ném exception khi hết hạn

Timeout thông thường trả `0L`. **Sửa:** tách nhánh zero và nhánh `InterruptedException`.

### Lỗi 9 — Nuốt InterruptedException

Catch rồi không propagate/restore khiến shutdown không được đáp ứng. **Sửa:** propagate hoặc `Thread.currentThread().interrupt()` rồi thoát.

### Lỗi 10 — Chỉ restore interrupt rồi tiếp tục retry vô hạn

Flag được khôi phục mà loop tiếp tục chạy không theo cancellation policy có thể tạo lỗi hoặc spin. **Sửa:** thoát sau khi xử lý interrupt, không âm thầm retry.

### Lỗi 11 — Nghĩ interrupt tự unlock một lock đã lấy

Không. **Sửa:** unlock trong finally và điều khiển công việc sau khi nhận interrupt theo contract.

### Lỗi 12 — Nghĩ timeout tự ngắt critical section

Timeout chỉ áp dụng **chờ acquire**. **Sửa:** quản lý thời gian thực thi nghiệp vụ riêng.

### Lỗi 13 — Dùng thời hạn lock như SLA toàn request

Một lần chờ 100ms có thể làm request đã gần deadline quá hạn. **Sửa:** chia ngân sách và tính phần thời gian còn lại.

### Lỗi 14 — Self-deadlock vì StampedLock không reentrant

Giữ read rồi đợi write, hoặc giữ write rồi lại lấy read không theo protocol, có thể chặn chính mình. **Sửa:** thiết kế mode conversions hoặc release/reacquire với recheck.

### Lỗi 15 — Không recheck state sau khi release read rồi lấy write

State có thể bị thay đổi giữa hai khóa. **Sửa:** đọc lại điều kiện dưới write lock mới.

### Lỗi 16 — Nghĩ tryOptimisticRead giữ read lock

Không. **Sửa:** copy giá trị trong local, validate, fallback khóa thật khi thất bại.

### Lỗi 17 — Unlock optimistic stamp bằng unlockRead

Optimistic stamp không đại diện cho read lock. **Sửa:** dùng `validate`; không release kiểu read.

### Lỗi 18 — Validate trước khi đọc rồi không validate sau

Writer có thể can thiệp giữa validate và field reads. **Sửa:** đọc dữ liệu vào locals rồi validate trước khi dùng.

### Lỗi 19 — Retry busy spin bằng tryLock không có backoff

Gây contention/CPU và không có fairness. **Sửa:** timed overload, bounded retries hoặc scheduling phù hợp.

### Lỗi 20 — Giả định fairness của StampedLock

Javadoc không hứa ưu tiên cố định giữa readers/writers. **Sửa:** không phụ thuộc thứ tự cấp khóa; nếu cần fairness, chọn công cụ có contract rõ.

### Lỗi 21 — Lưu stamp rồi dùng ở lock khác

Stamp chỉ có ý nghĩa với instance StampedLock phù hợp. **Sửa:** giữ scope/capability đúng, không dùng stamp làm ID độc lập.

### Lỗi 22 — Gọi method có thể khóa lại trong critical section

StampedLock không reentrant, nên method helper có thể vô tình yêu cầu cùng khóa lần nữa. **Sửa:** phân tách helper đã được bảo vệ hoặc truyền dữ liệu/stamp có kiểm soát.

### Lỗi 23 — Dùng lock khi state còn bị ghi ngoài protocol

Reader có khóa vẫn có thể nhìn dữ liệu không nhất quán nếu writer không lấy đúng khóa. **Sửa:** kiểm soát tất cả access phù hợp với cùng protocol.

### Lỗi 24 — Lạm dụng tryConvertToWriteLock

Conversion có thể trả zero, không bảo đảm upgrade khi có reader khác. **Sửa:** xử lý thất bại, release/re-acquire và recheck state.

### Lỗi 25 — Coi lock zero là bằng chứng data đang hỏng

Zero chỉ báo không acquire trong lần thử. **Sửa:** phản hồi busy/timeout theo ngữ nghĩa, không đánh đồng corruption.

### Lỗi 26 — Test interrupt bằng sleep và kết luận tất cả lịch chạy đều như nhau

Scheduler khác nhau khiến test chập chờn. **Sửa:** dùng latch và assert invariant; không in hoặc assert thứ tự luồng ngẫu nhiên.

### Lỗi 27 — Quên đóng worker/executor

Các thread chờ lock có thể giữ JVM sống hoặc rò tài nguyên. **Sửa:** xác định lifecycle, cancel/interrupt, join/awaitTermination và release locks.

### Lỗi 28 — Giả định StampedLock có Condition như ReentrantLock

StampedLock không trực tiếp implement Lock/ReadWriteLock theo cách cung cấp mọi tính năng Condition; các view chỉ cung cấp tập con phù hợp. **Sửa:** nếu cần condition wait/signal, chọn `ReentrantLock`/`Condition` thích hợp.

## 16. Checklist thiết kế và kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| Không có writer, không có reader | `tryReadLock()` hoặc `tryWriteLock()` có thể nhận stamp hợp lệ |
| Write lock đang giữ | `tryReadLock()` trả 0 |
| Write lock đang giữ | `tryWriteLock()` trả 0 |
| Write lock đang giữ | `tryOptimisticRead()` trả 0 |
| Read lock đang giữ | `tryWriteLock()` trả 0 |
| Timed read dưới write lock giữ xuyên timeout | Trả 0 |
| Timed write dưới write lock giữ xuyên timeout | Trả 0 |
| Timed try bị interrupt trước acquire | Ném `InterruptedException` |
| Read interruptible bị interrupt | Ném `InterruptedException` |
| Write interruptible bị interrupt | Ném `InterruptedException` |
| Catch có restore flag | `Thread.currentThread().isInterrupted()` true sau catch |
| Acquire thành công | Critical section chạy và unlock đúng stamp |
| Acquire không thành công | Không truy cập state cần khóa và không unlock |
| Read stamp đã unlock rồi bị unlock lại | Có thể ném `IllegalMonitorStateException` |
| Optimistic stamp sau write | `validate` không còn chứng nhận snapshot cũ |
| Reader nâng quyền với reader khác | `tryConvertToWriteLock` có thể thất bại |
| Release read rồi acquire write | Phải recheck điều kiện |
| Timeout tổng request | Thời gian chờ lock nằm trong ngân sách còn lại |
| Concurrent access vào protected fields | Mọi writer tham gia protocol |
| Nonreentrancy | Không giữ một mode rồi gọi lại method chờ khóa không phù hợp |
| Fairness | Không assert thứ tự reader/writer cụ thể |

### 16.1. Test “timeout thật” không cần đo chính xác từng ms

Một test có write lock được giữ tới sau lúc timed try hết hạn sẽ khiến timed read/write trả zero. Test nên assert **outcome**, không dùng `System.currentTimeMillis()` để so số milisecond chính xác.

### 16.2. Test interrupt mà không bị kẹt

Một pattern:

1. Main lấy write lock và **chưa** release.
2. Worker chạy method interruptible, báo đã bắt đầu qua latch.
3. Main gọi `interrupt` trên worker.
4. Đợi worker thoát bằng `join(timeout)`.
5. Assert worker đã dừng, exception được bắt/propagate đúng, flag được restore theo policy.
6. Main release write lock trong `finally` ngay cả khi test thất bại.

Bài runnable ở mục 13 dùng đúng pattern này.

### 16.3. Kiểm thử phải xác minh trách nhiệm unlock

Tạo test với một lần thành công và một lần thất bại của từng try API. Với case thất bại, assert **không** có unlock. Với case thành công, assert có unlock trong finally. Những lỗi double-unlock/stale stamp nên được kiểm thử tách biệt, không đưa vào đường production bình thường.

## 17. Bài tập tự kiểm tra và đáp án

**Câu 1.** `tryWriteLock()` trả gì khi lock bận?

**Đáp án:** `0L`, không phải false hoặc `InterruptedException`.

**Câu 2.** `tryReadLock(100, TimeUnit.MILLISECONDS)` hết thời gian mà chưa có lock thì sao?

**Đáp án:** Trả `0L`. Đó là outcome timeout, khác với việc bị interrupt.

**Câu 3.** Nếu thread bị interrupt trong `tryWriteLock(5,SECONDS)` thì trả 0 hay ném exception?

**Đáp án:** Theo hợp đồng interruptible, nó ném `InterruptedException` nếu ngắt trước khi cấp khóa; không dùng zero làm mã hóa cancellation.

**Câu 4.** `writeLockInterruptibly()` khác `writeLock()` ở đâu?

**Đáp án:** Bản interruptible có thể thoát khi thread bị interrupt và khai báo `InterruptedException`, còn bản thường không có checked exception đó.

**Câu 5.** Có thể gọi `unlockRead(0L)` sau timed read timeout không?

**Đáp án:** Không. Zero không là stamp đã cấp; chỉ unlock sau khi acquire thành công.

**Câu 6.** Vì sao phải đặt unlock trong finally?

**Đáp án:** Để bảo đảm release stamp cả khi critical section return sớm hoặc ném runtime exception.

**Câu 7.** `tryReadLock()` có tương đương `tryOptimisticRead()` không?

**Đáp án:** Không. Try read nhận read lock thật nếu thành công; optimistic read là quan sát cần validate và không giữ khóa.

**Câu 8.** Một optimistic stamp được validate trước khi đọc fields có đủ không?

**Đáp án:** Không. Cần copy dữ liệu phù hợp rồi validate **sau**, trước khi sử dụng kết quả.

**Câu 9.** `readLockInterruptibly()` đã cấp stamp rồi thì interrupt có tự giải phóng không?

**Đáp án:** Không. Code giữ stamp vẫn phải unlock trong finally.

**Câu 10.** Vì sao không nên gọi `writeLock()` khi đang giữ read stamp?

**Đáp án:** StampedLock không reentrant; caller có thể tự deadlock khi chờ quyền exclusive. Dùng conversion/release-reacquire đúng protocol.

**Câu 11.** `tryConvertToWriteLock(stamp)` trả zero thì quyền read cũ có tự mất không?

**Đáp án:** Không mặc định. Nếu không chuyển được, caller vẫn cần quản lý stamp cũ đúng mode và release khi phù hợp.

**Câu 12.** Cùng một stamp có thể unlock hai lần?

**Đáp án:** Không. Lần thứ hai với stamp stale có thể gây `IllegalMonitorStateException`.

**Câu 13.** Timed try 100ms có bảo đảm code trong critical section chỉ chạy 100ms không?

**Đáp án:** Không. Timeout chỉ là thời hạn chờ acquire. Sau khi lấy lock, việc giữ khóa do caller kiểm soát.

**Câu 14.** Interrupt có nên coi là timeout và retry tự động vô hạn không?

**Đáp án:** Không. Interrupt thường là cancellation; propagate hoặc restore flag rồi ngừng theo contract.

**Câu 15.** Lấy được stamp có bảo đảm field được bảo vệ nếu writer khác không dùng lock không?

**Đáp án:** Không. Tất cả truy cập chia sẻ phải tham gia protocol phù hợp.

**Câu 16.** `StampedLock` có hứa writer sẽ được ưu tiên sau vài lần retry không?

**Đáp án:** Không. API không bảo đảm fairness ưu tiên readers/writers.

**Câu 17.** Khi thread bị interrupt nhưng method không thể khai báo throws, cần cân nhắc gì?

**Đáp án:** Bắt `InterruptedException`, khôi phục `Thread.currentThread().interrupt()` và thoát hoặc trả trạng thái cancellation tường minh.

**Câu 18.** Một timeout nhỏ có thể giải quyết deadlock do code cố giữ read rồi lấy write không?

**Đáp án:** Nó có thể giúp đường timed thoát khỏi chờ vô hạn, nhưng **không sửa lỗi thiết kế lock order/protocol**. Cần tránh tự re-acquire và recheck sau conversion/release.

**Câu 19.** Vì sao zero trả về không khẳng định writer đang giữ lock ngay lúc hiện tại?

**Đáp án:** Try methods best-effort; trạng thái có thể đổi giữa lần thử và lúc xử lý, và zero không mã hóa nguyên nhân cụ thể.

**Câu 20.** Khi nào nên cân nhắc dùng ReentrantLock thay StampedLock?

**Đáp án:** Khi code cần reentrancy, `Condition`, hoặc fairness policy có hợp đồng rõ hơn, không có lợi thế rõ ràng từ optimistic/stamped read.

## 18. Tổng kết

- **`tryReadLock()` và `tryWriteLock()`** là nonblocking tries, trả **stamp khác zero** khi thành công hoặc **`0L`** khi thất bại.
- **`tryReadLock(timeout,unit)` và `tryWriteLock(timeout,unit)`** cho phép chờ hữu hạn; **zero khi hết hạn**, **`InterruptedException` khi bị interrupt trước acquire**.
- **`readLockInterruptibly()` và `writeLockInterruptibly()`** chờ không giới hạn thời gian nhưng có phản hồi interruption; khác với các bản `readLock()/writeLock()` thông thường.
- **Không unlock zero hoặc stale stamp.** Luôn release đúng mode trong `finally` sau khi lấy khóa thành công.
- **Bắt InterruptedException đúng cách:** propagate hoặc restore interrupt flag rồi ngừng; không tự nuốt tín hiệu và retry mãi.
- **Timeout acquire không tự kết thúc critical section** và không phải deadline end-to-end. Đặt ngân sách chờ phù hợp.
- **StampedLock không reentrant, không bảo đảm fairness**, không phải một thay thế chung cho mọi loại `Lock`.
- **`tryOptimisticRead` không giữ khóa thật**; copy dữ liệu vào locals, validate sau đó và fallback khi cần.
- **Các mode conversion cũng có thể trả zero**; quản lý stamp cũ/mới và recheck state nếu phải release/reacquire.
- **Java 8 runnable demo đã được chạy xác minh** gồm immediate failure, timeout, interruption, successful acquire, optimistic validation và stale stamp detection.
- Những API và quy tắc trên **vẫn còn áp dụng hiện nay**, phù hợp với Special Note tránh kiến thức legacy/lỗi thời.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — StampedLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/StampedLock.html)
- [Oracle Java SE 8 — TimeUnit](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/TimeUnit.html)
- [Oracle Java SE 8 — Lock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/Lock.html)
- [Oracle Java SE 8 — InterruptedException](https://docs.oracle.com/javase/8/docs/api/java/lang/InterruptedException.html)
- [Oracle Java SE 8 — Thread](https://docs.oracle.com/javase/8/docs/api/java/lang/Thread.html)
- [Oracle Java SE 8 — CountDownLatch](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountDownLatch.html)
- [Oracle Java SE 8 — ReentrantLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/ReentrantLock.html)
- [Oracle Java SE 26 — StampedLock (API hiện hành)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
