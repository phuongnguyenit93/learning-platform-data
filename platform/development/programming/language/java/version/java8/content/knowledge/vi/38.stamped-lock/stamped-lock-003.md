# StampedLock: readLock, writeLock và mở khóa an toàn trong finally

## 1. Mục tiêu và bài toán

Khi nhiều luồng Java cùng truy cập một nhóm dữ liệu có quan hệ với nhau, người lập trình cần kiểm soát **khi nào được đọc đồng thời** và **khi nào phải ghi độc quyền**. Ví dụ một đối tượng lưu hai trường `left`, `right` luôn phải được cập nhật cùng nhau. Nếu một luồng đọc `left` trước khi writer sửa và đọc `right` sau khi writer sửa, nó có thể nhận một cặp không nhất quán.

`java.util.concurrent.locks.StampedLock` là một công cụ đồng bộ trong Java, có từ **Java 8** và vẫn được hỗ trợ trong Java hiện đại. Khi chỉ xét chủ đề bài này, cần hiểu hai chế độ khóa chính:

- **`readLock()`**: giữ một khóa **không độc quyền**; nhiều reader có thể đồng thời giữ read lock nếu không có writer giữ write lock.
- **`writeLock()`**: giữ một khóa **độc quyền**; khi writer nắm write lock thì các read/write lock khác không thể được cấp đồng thời.
- Mỗi lần khóa thành công trả một số **`long stamp`**; phải sử dụng đúng stamp và đúng phương thức **`unlockRead(stamp)`** hoặc **`unlockWrite(stamp)`** để mở khóa.
- Thao tác mở khóa phải được đặt trong **`finally`**, bảo đảm được gọi khi thân `try` kết thúc bình thường hoặc ném exception.

Một lỗi nghiêm trọng không nằm ở cú pháp `StampedLock` mà ở **vòng đời khóa**: nếu quên mở khóa trong luồng thực thi bị lỗi, những luồng khác có thể tiếp tục chờ vô hạn. Ngược lại, mở khóa sai stamp, sai mode hoặc hai lần có thể ném `IllegalMonitorStateException`.

**Phạm vi bài:** “readLock, writeLock và mở khóa trong finally” thuộc mục “StampedLock”. Những phương thức `tryReadLock`, `tryWriteLock`, `readLockInterruptibly`, `writeLockInterruptibly`, `tryConvertToWriteLock` và `tryOptimisticRead` chỉ được đưa vào khi giúp tránh hiểu nhầm cách mở/giữ khóa. Đây không phải bài về triển khai cấu trúc khóa nội bộ hoặc các phương pháp đã lỗi thời.

### Kết quả học tập

Sau khi đọc, bạn sẽ có thể:

1. Giải thích sự khác nhau giữa **shared read** và **exclusive write**.
2. Viết đúng mẫu `long stamp = lock.readLock(); try {...} finally { lock.unlockRead(stamp); }`.
3. Viết đúng mẫu tương đương cho `writeLock`.
4. Hiểu tại sao **phải lấy khóa trước `try`** rồi mới dùng `finally`.
5. Biết `tryReadLock/tryWriteLock` trả **`0L`** khi không lấy được khóa và không được unlock stamp 0.
6. Phân biệt locked read với optimistic read; optimistic stamp **không được unlock như read lock**.
7. Tránh deadlock do `StampedLock` **không reentrant**.
8. Biết exception trong critical section không được làm khóa bị rò rỉ.
9. Hiểu khi nào dùng `unlockRead`, `unlockWrite` hoặc `unlock` sau conversion.
10. Viết test có kiểm soát với `CountDownLatch` và hai reader thực sự chạy đồng thời, không phụ thuộc `Thread.sleep`.
11. Cân nhắc tính công bằng, interruption, thời gian giữ khóa, performance và các lựa chọn thay thế.
12. Đối chiếu hành vi bằng chương trình Java 17+ có stdout chính xác.

## 2. Tư duy về “stamp”: khóa không phải boolean

Khác với `synchronized` (JVM tự quản lý việc rời monitor) hoặc `ReentrantLock.lock()/unlock()` (không truyền token), `StampedLock` dùng **token dạng số nguyên `long`**, gọi là **stamp**. Stamp biểu thị trạng thái/phiên bản và chế độ khóa đã được cấp.

```java
StampedLock lock = new StampedLock();

long readStamp = lock.readLock();
// readStamp là token của một lần giữ read lock thành công.
lock.unlockRead(readStamp);
```

Bên trong StampedLock có trạng thái version/mode; token của thao tác khóa phải phù hợp với trạng thái lock để giải phóng. **Stamp không phải số thứ tự request và không phải password bảo mật**. Không tự sửa bằng phép cộng, XOR, hash, serialize rồi gửi qua mạng hoặc coi nó là định danh có giá trị vĩnh viễn.

Hai bước phải đi liền nhau theo vòng đời:

```text
acquire  ->  lưu stamp  ->  làm việc trong critical section
                               |
                               v
                     finally: unlock đúng stamp/mode
```

Nếu lấy read lock, gọi `unlockRead(stamp)`; nếu lấy write lock, gọi `unlockWrite(stamp)`. Phương thức `unlock(stamp)` tổng quát có thể giải phóng **một stamp khóa hợp lệ** theo mode của nó, hữu ích khi có conversion mà mode cuối thay đổi.

### 2.1. StampedLock có ba mode, nhưng không phải stamp nào cũng cần unlock

| Mode | Phương thức lấy | Kết quả | Cách kết thúc |
| --- | --- | --- | --- |
| Read lock | `readLock()` / `tryReadLock()` | Read stamp khi thành công | `unlockRead(readStamp)` |
| Write lock | `writeLock()` / `tryWriteLock()` | Write stamp khi thành công | `unlockWrite(writeStamp)` |
| Optimistic read | `tryOptimisticRead()` | Observation stamp nếu không có writer tại lúc thử, hoặc 0 | **Không unlock**; dùng `validate(stamp)` |

**Không coi `tryOptimisticRead` là “một dạng readLock nhẹ hơn có thể unlock”**. Nó không thực sự giữ khóa đọc. Nếu gọi `unlockRead(optimisticStamp)` sẽ dùng sai mode và có thể ném `IllegalMonitorStateException`.

### 2.2. Vì sao phải giữ nguyên đúng token?

`unlockRead` và `unlockWrite` đối chiếu stamp với trạng thái/mode hiện tại. Nếu stamp không phù hợp, chúng ném `IllegalMonitorStateException`.

Ví dụ:

```java
long stamp = lock.readLock();
lock.unlockRead(stamp);

// Sai: cùng stamp đã được giải phóng.
lock.unlockRead(stamp);  // IllegalMonitorStateException.
```

Đây là đoạn **cố ý thể hiện lỗi**; không sao chép thành code sử dụng trong production. Khi dùng chuyển mode bằng `tryConvertToWriteLock`, stamp có thể đổi, nên cần cập nhật biến stamp và cách mở khóa tương ứng.

## 3. readLock(): nhiều reader, không writer độc quyền

Hợp đồng:

```java
public long readLock()
```

Nó lấy khóa ở **chế độ đọc không độc quyền**, có thể **block** nếu không thể lấy ngay. Khi thành công, trả một read stamp dùng cho `unlockRead(long)`.

Giả sử ba luồng:

```text
Thời gian --->
Reader A  [=== read lock ===]------------------->
Reader B      [==== read lock ====]------------->
Writer C          (đang chờ)   [write lock]---->
```

Reader A và B có thể đồng thời giữ read lock; writer cần trạng thái đủ điều kiện độc quyền trước khi được cấp write lock.

### 3.1. Mẫu đúng cho một thao tác đọc

```java
private final StampedLock lock = new StampedLock();
private int left;
private int right;

Snapshot snapshot() {
    long stamp = lock.readLock();
    try {
        return new Snapshot(left, right);
    } finally {
        lock.unlockRead(stamp);
    }
}
```

Đây là **đoạn trong class**, giả định `record Snapshot(int left, int right) {}` đã định nghĩa; chương trình hoàn chỉnh có đủ các khai báo ở mục 16.

Điểm mạnh của mẫu:

- Thao tác đọc `left` và `right` diễn ra trong **một critical section**.
- Khi mọi writer cũng dùng write lock tương ứng, reader không thấy tình trạng writer đang sửa dở hai field.
- `finally` chạy **ngay cả khi `return` xảy ra trong `try`**; khóa được giải phóng trước khi method trả về cho caller.
- Nếu code đọc ném exception, `finally` vẫn được thực thi.
- Không cho caller giữ read stamp qua nhiều method nếu không thực sự cần điều đó; giữ scope hẹp giúp giảm contention.

### 3.2. Vì sao read lock không dùng cho mutate?

Một read lock chỉ bảo đảm reader không bị writer độc quyền chen vào theo protocol của StampedLock. Nó **không ngăn những reader khác cùng chạy**. Nếu bạn sửa dữ liệu dưới read lock, hai “reader” thực tế là writer có thể đụng nhau.

Sai:

```java
long stamp = lock.readLock();
try {
    balance++; // Sai mục đích: mutation trong read mode.
} finally {
    lock.unlockRead(stamp);
}
```

Nếu có cập nhật chia sẻ, dùng write lock (hoặc một cơ chế nguyên tử phù hợp với kiểu dữ liệu). **Javadoc khuyến nghị nội dung phần đọc dưới read lock không có side effect**.

### 3.3. Đọc một biến và đọc một nhóm biến

Đối với một biến độc lập, đôi khi `volatile` hoặc `AtomicInteger` đủ để có visibility/atomic update, và StampedLock có thể là chi phí thừa. Nhưng với **nhiều trường có cùng bất biến**, read lock giúp đọc cả nhóm trong một vùng được bảo vệ.

Ví dụ `left==right` phải đúng sau mọi write. Khi writer tăng cả hai trong cùng write lock, reader đọc cả hai dưới read lock sẽ không bị chen giữa bởi writer tuân thủ cùng khóa.

**Không chỉ khóa reader mà để writer cập nhật trực tiếp ngoài khóa.** Thread safety phụ thuộc **toàn bộ các đường đọc/ghi liên quan đều theo cùng protocol**, không riêng một phương thức.

## 4. writeLock(): một writer độc quyền và bất biến dữ liệu

Hợp đồng:

```java
public long writeLock()
```

Nó lấy khóa ở chế độ **độc quyền**; có thể **block** tới khi sẵn sàng. Một write stamp thành công được đưa vào `unlockWrite(stamp)`.

Mẫu:

```java
void addBoth(int delta) {
    long stamp = lock.writeLock();
    try {
        left += delta;
        right += delta;
    } finally {
        lock.unlockWrite(stamp);
    }
}
```

Khi tất cả phương thức quan sát và cập nhật đều dùng đúng một `StampedLock`:

- Hai writer không cập nhật cặp biến cùng lúc.
- Reader giữ read lock không quan sát cặp biến đang bị writer sửa dở.
- Khi writer giữ write lock, các read locks mới không được cấp cho tới khi writer giải phóng.
- Nếu code cập nhật ném exception, `finally` vẫn giải phóng khóa để các luồng khác không kẹt vì chính lỗi đó.

### 4.1. Unlock đúng không đồng nghĩa rollback

`finally` đảm bảo **giải phóng khóa**, không tự khôi phục dữ liệu đã sửa trước khi xảy ra exception.

Giả sử:

```java
long stamp = lock.writeLock();
try {
    left += 1;
    riskyOperation();   // Có thể ném exception.
    right += 1;
} finally {
    lock.unlockWrite(stamp);
}
```

Đây là **anti-pattern minh họa** nếu bất biến yêu cầu `left==right`. Nếu `riskyOperation()` ném exception sau khi left đã tăng nhưng trước khi right tăng, dữ liệu có thể dở dang **dù khóa được giải phóng đúng**.

Với nhiều field phải đồng bộ:

1. **Validate và chuẩn bị dữ liệu trước khi thay đổi state** nếu có thể.
2. Khi giữ write lock, thực hiện phần commit ngắn, có thứ tự an toàn.
3. Với yêu cầu giao dịch phức tạp, thiết kế rollback, immutable replacement hoặc transaction phù hợp.
4. Không cho rằng lock mang transaction semantics; nó chỉ phối hợp quyền truy cập.

### 4.2. Mọi biến được bảo vệ phải tuân thủ cùng khóa

Nếu `addBoth` dùng write lock nhưng một method khác viết `left` trực tiếp, reader vẫn có thể thấy trạng thái không nhất quán. Hãy **đóng gói state làm `private`**, chỉ phơi ra các method có critical section rõ.

Không để caller có thể lấy reference tới object mutable nội bộ rồi sửa nó ngoài khóa. Một `record Snapshot` chứa các giá trị primitive là cách tốt để trả bản chụp nhỏ độc lập.

## 5. finally: nguyên tắc an toàn số một

Đây là mẫu quan trọng nhất của bài:

```java
long stamp = lock.writeLock();
try {
    // Critical section.
} finally {
    lock.unlockWrite(stamp);
}
```

Và cho read:

```java
long stamp = lock.readLock();
try {
    // Chỉ đọc dữ liệu được bảo vệ.
} finally {
    lock.unlockRead(stamp);
}
```

Cấu trúc này có ba thuộc tính quan trọng:

1. **`lock.writeLock()` được thực thi trước `try`:** nếu chưa lấy được khóa, chương trình không đi vào `finally` sẽ unlock một stamp không hợp lệ.
2. **Khi acquisition thành công**, Java bước vào `try`. Đường ra bình thường, `return`, `break` hoặc exception trong thân đều dẫn đến `finally`.
3. **`unlock*` chạy đúng một lần trong `finally`**, giúp giữ vòng đời lock dễ kiểm tra.

### 5.1. Đừng chỉ unlock cuối hàm khi đường thoát có thể thay đổi

Sai:

```java
long stamp = lock.writeLock();
updateState();
lock.unlockWrite(stamp);
```

Nếu `updateState` ném exception, lệnh unlock không chạy. Một luồng khác có thể chờ write/read mãi, khiến dịch vụ treo khó chẩn đoán.

Đúng:

```java
long stamp = lock.writeLock();
try {
    updateState();
} finally {
    lock.unlockWrite(stamp);
}
```

Đây là snippet trong method với `updateState` đã được định nghĩa. `finally` còn đúng khi sau này refactor thân method, thêm `return` hoặc một phép kiểm tra ném exception.

### 5.2. finally không “nuốt” exception

Khi một exception phát sinh trong `try` và `unlockWrite(stamp)` thành công, exception gốc vẫn tiếp tục truyền ra caller. `finally` không phải `catch` và không tự phục hồi lỗi.

Nếu unlock lại **ném exception** (chẳng hạn stamp không hợp lệ), exception mới có thể làm việc chẩn đoán lỗi gốc khó hơn. Vì vậy phải giữ stamp chính xác, tránh double unlock hoặc làm biến stamp bị ghi đè sai.

Một test hữu ích là cố tình ném exception trong read/write critical section, bắt nó ở caller, rồi gọi `tryReadLock/tryWriteLock` để chứng minh khóa đã được giải phóng.

### 5.3. Đừng unlock trước khi công việc được bảo vệ thực sự hoàn tất

Sai:

```java
long stamp = lock.readLock();
try {
    stateRef = sharedMutableObject;
} finally {
    lock.unlockRead(stamp);
}
// Sau khi unlock, đọc nhiều field mutable qua stateRef có thể không nhất quán.
```

Nếu dữ liệu là một nhóm field mutable được bảo vệ, hãy đọc/copy các giá trị cần thiết **trong critical section**, hoặc dùng immutable snapshot an toàn. Không trả reference mutable nội bộ rồi tưởng caller tiếp tục được bảo vệ sau unlock.

### 5.4. Nếu vẫn muốn ghi log trong finally?

Lệnh unlock nên được ưu tiên thực hiện không phụ thuộc vào logic log hoặc callback có thể ném exception. Tránh:

```java
finally {
    logger.sendToNetwork(); // Có thể lỗi/chặn lâu.
    lock.unlockWrite(stamp);
}
```

Nếu `sendToNetwork` lỗi, khóa không được giải phóng. Nên đảm bảo unlock chạy chắc chắn và tách hoạt động có thể thất bại khỏi đoạn bảo vệ. Với log/metric quan trọng cần một chính sách xử lý lỗi riêng, không xếp trước lệnh unlock.

## 6. So sánh readLock và writeLock

| Đặc điểm | `readLock()` | `writeLock()` |
| --- | --- | --- |
| Mode | Shared/read | Exclusive/write |
| Return type | `long` read stamp | `long` write stamp |
| Nếu không lấy được ngay | Có thể chờ | Có thể chờ |
| Được chạy cùng nhiều reader? | Có, khi không có writer | Không, độc quyền |
| Được chạy cùng writer? | Không | Không |
| Thao tác chính | Đọc state được bảo vệ | Cập nhật state/bất biến |
| Mở khóa | `unlockRead(stamp)` | `unlockWrite(stamp)` |
| Dùng trong `finally`? | Có, sau acquisition thành công | Có, sau acquisition thành công |
| Có bảo đảm fairness? | Không | Không |
| Có phải reentrant lock? | Không | Không |
| Biến thể không chờ | `tryReadLock()` | `tryWriteLock()` |
| Biến thể chờ có timeout | `tryReadLock(time,unit)` | `tryWriteLock(time,unit)` |
| Biến thể phản ứng interrupt | `readLockInterruptibly()` | `writeLockInterruptibly()` |

**Đừng suy ra** có read stamp thì chỉ một reader đang giữ khóa; một map hoặc object có thể có nhiều read stamps hợp lệ đồng thời. Ngược lại, write stamp biểu thị writer nắm trạng thái độc quyền.

### 6.1. Tại sao writer phải chờ tất cả readers?

Nếu còn reader đang đọc nhiều field, writer đổi một phần state ngay lúc đó sẽ phá bất biến quan sát. Read/write lock phối hợp để tránh điều này: writer chỉ có thể được cấp khi không xung đột với những read locks đang giữ.

### 6.2. Nhưng “nhiều reader” không hứa throughput tăng trong mọi tình huống

Với critical section đọc cực ngắn, contention nhỏ, hoặc JVM nhiều overhead, `StampedLock` không mặc định nhanh hơn `synchronized`. Ngay cả khi read-heavy, hiệu quả phụ thuộc thời gian giữ lock, số cores, cache coherence và scheduling.

**Chọn theo đúng yêu cầu trước**, rồi đo bằng benchmark có kiểm soát như JMH nếu quyết định về hiệu năng là quan trọng. Không đổi sang StampedLock chỉ vì tên nghe “tối ưu”.

## 7. tryReadLock/tryWriteLock: stamp 0 nghĩa là không lấy được

Các phương thức:

```java
long readStamp = lock.tryReadLock();
long writeStamp = lock.tryWriteLock();
```

cố lấy khóa **ngay lập tức** và trả `0L` khi không thể lấy được theo điều kiện tại thời điểm thử. Chúng **không phải** phiên bản đảm bảo thành công. `0L` còn có thể là kết quả của `tryOptimisticRead()` khi đang có writer.

### 7.1. Mẫu đúng khi tryReadLock có thể thất bại

```java
long stamp = lock.tryReadLock();
if (stamp == 0L) {
    return Optional.empty(); // Theo business policy.
}
try {
    return Optional.of(new Snapshot(left, right));
} finally {
    lock.unlockRead(stamp);
}
```

Đây là đoạn trong một method trả `Optional<Snapshot>`, với `Snapshot` đã định nghĩa. Chỉ bước vào `try/finally` **sau khi biết stamp khác 0**.

Sai:

```java
long stamp = lock.tryReadLock();
try {
    return readSharedData();
} finally {
    lock.unlockRead(stamp);
}
```

Nếu `tryReadLock()` trả 0, code vẫn đọc state không bảo vệ và gọi `unlockRead(0)` có thể ném `IllegalMonitorStateException`. Đây là anti-pattern.

### 7.2. Mẫu đúng khi tryWriteLock có thể thất bại

```java
long stamp = lock.tryWriteLock();
if (stamp == 0L) {
    return false; // Không lấy được ngay.
}
try {
    updateSharedData();
    return true;
} finally {
    lock.unlockWrite(stamp);
}
```

Code minh họa trong method trả `boolean`. Không được thực hiện mutation khi `stamp == 0L` nếu dữ liệu đó yêu cầu write lock.

### 7.3. 0 không phải bằng chứng về số reader/writer đang chờ

Javadoc ghi rõ mọi phương thức “try” là **best effort**; kết quả 0 không mang một kết luận chắc chắn về toàn bộ trạng thái lock hoặc fairness. Cùng một lời gọi tiếp theo có thể thành công.

Không xây thuật toán suy luận “0 tức hiện đang có đúng một writer” hay “0 tức đã deadlock”. Nó chỉ cho biết **lần thử đó không thành công**.

## 8. Timed tryLock và interruptible acquisition

`readLock()` và `writeLock()` có thể chặn mà không trả về cho tới khi lấy được khóa. Trong hệ thống có giới hạn thời gian hoặc chính sách hủy, bạn có thể cần các biến thể khác.

### 8.1. Timed acquisition

```java
long stamp = lock.tryWriteLock(200, TimeUnit.MILLISECONDS);

if (stamp == 0L) {
    return false; // Hết thời gian hoặc không thể lấy khóa.
}
try {
    update();
    return true;
} finally {
    lock.unlockWrite(stamp);
}
```

Đoạn này thuộc một method `throws InterruptedException` (hoặc phải xử lý interruption); `TimeUnit` được import từ `java.util.concurrent`. Nếu không lấy được khóa trong khoảng thời gian quy định, method trả **0**; nếu bị interrupt, nó có thể ném `InterruptedException`.

Một timed `tryReadLock(time,unit)` cũng có cùng mẫu giữ stamp, kiểm tra 0 rồi `unlockRead` trong `finally`.

### 8.2. readLockInterruptibly và writeLockInterruptibly

```java
long stamp = lock.readLockInterruptibly();
try {
    return readState();
} finally {
    lock.unlockRead(stamp);
}
```

Hoặc:

```java
long stamp = lock.writeLockInterruptibly();
try {
    mutateState();
} finally {
    lock.unlockWrite(stamp);
}
```

Hai snippet này ở trong method `throws InterruptedException`. Nếu acquisition **bị interrupt trước khi thành công**, nó ném `InterruptedException`; vì assignment stamp chưa hoàn thành, code **không vào phần `try/finally`** để unlock một khóa chưa lấy được.

Nếu bạn catch `InterruptedException` ở tầng trên, nên tuân thủ chính sách cancellation của ứng dụng; khi không rethrow, thường cần `Thread.currentThread().interrupt()` để khôi phục cờ interrupt. Không nuốt interrupt rồi retry vô hạn.

### 8.3. Đừng dùng readLock/writeLock như timed API

`readLock()` và `writeLock()` không nhận timeout và không tự tuân thủ một deadline bên ngoài. Nếu thread phải phản ứng với cancellation/timeout, dùng biến thể timed/interruptible và thiết kế giới hạn thời gian cho cả critical section lẫn việc chờ lock.

**Lưu ý:** Timeout khi **đợi lấy khóa** không tự giới hạn thời gian chạy trong `try` sau khi khóa đã được cấp. Nếu bạn giữ write lock để gọi HTTP hay cơ sở dữ liệu chậm, timed acquisition không giải quyết được thời gian giữ khóa quá dài.

## 9. StampedLock không reentrant: bẫy nested calls

Theo Javadoc, StampedLock **không reentrant**. Nó không hỗ trợ mô hình “cùng thread đã giữ write lock thì cứ gọi writeLock lần nữa để tăng reentrant hold count” như `ReentrantLock`.

Một ví dụ có thể deadlock:

```java
void outerWrite() {
    long outer = lock.writeLock();
    try {
        innerWrite(); // Nếu innerWrite() cũng gọi writeLock()!
    } finally {
        lock.unlockWrite(outer);
    }
}
```

Đây là anti-pattern nếu `innerWrite` cũng lấy cùng StampedLock. Thread đang giữ write lock lại cố đợi một write lock độc quyền thứ hai mà nó chưa giải phóng; không có tái nhập cho thread sở hữu như ReentrantLock.

### 9.1. Khi giữ read lock mà cần ghi

Cũng không nên:

```java
long readStamp = lock.readLock();
try {
    long writeStamp = lock.writeLock(); // Có thể tự chờ mãi.
    try {
        mutateState();
    } finally {
        lock.unlockWrite(writeStamp);
    }
} finally {
    lock.unlockRead(readStamp);
}
```

Vì read lock còn giữ, write lock không thể được cấp độc quyền. **Đừng tự nâng read → write bằng cách gọi writeLock trong khi vẫn giữ read lock.**

Thay vào đó:

- Dùng `tryConvertToWriteLock(readStamp)` nếu phù hợp; chỉ thành công khi điều kiện chuyển mode cho phép.
- Hoặc **giải phóng read lock**, lấy write lock, rồi **kiểm tra lại điều kiện nghiệp vụ** sau khi đã có write lock.
- Hoặc thiết kế method nhận stamp và không tự lấy lại khóa, với contract rõ và không lộ stamp cho caller tùy tiện.

### 9.2. Phân lớp method “locked” và “unlocked” một cách rõ ràng

Một cách phòng deadlock:

```java
public void update(int delta) {
    long stamp = lock.writeLock();
    try {
        updateUnderWriteLock(delta);
    } finally {
        lock.unlockWrite(stamp);
    }
}

private void updateUnderWriteLock(int delta) {
    left += delta;
    right += delta;
}
```

Method private `updateUnderWriteLock` **không lấy khóa lần nữa**; caller phải bảo đảm đang giữ write lock. Đặt tên rõ và tránh cho code ngoài class gọi nhầm.

### 9.3. Không phải mọi lần gọi readLock lặp đều “đợi mãi”

Tính **non-reentrant** ở đây nghĩa là lock không theo dõi ownership/thread và không cung cấp reentrant semantics. Không nên đơn giản hóa thành “cùng thread gọi readLock lần hai luôn block”: hai read locks có thể cùng được cấp khi không có writer, nhưng chính sách lập lịch và tương tác với writer đang chờ khiến cách sử dụng lồng nhau rủi ro.

Quy tắc an toàn vẫn là **không tự tái lấy khóa trong một critical section đang giữ stamp**, trừ khi bạn hiểu đầy đủ protocol và lý do.

## 10. Chuyển mode và mở khóa bằng stamp cuối cùng

`StampedLock` có `tryConvertToWriteLock(stamp)`, `tryConvertToReadLock(stamp)` và `tryConvertToOptimisticRead(stamp)`. Đó là các phép **chuyển mode có điều kiện**, không phải lệnh luôn thành công.

Khi một phép conversion **thành công**, kết quả trả về có thể là **stamp mới**. Khi đó bạn phải dùng stamp mới và đúng mode để unlock, không tiếp tục unlock stamp read cũ như chưa từng chuyển.

### 10.1. Một lần chuyển read → write không có reader khác

```java
long stamp = lock.readLock();
try {
    long converted = lock.tryConvertToWriteLock(stamp);
    if (converted != 0L) {
        stamp = converted;
        // Từ đây đang giữ write lock.
        left += 1;
        right += 1;
    }
} finally {
    lock.unlock(stamp); // Tự nhận mode của stamp cuối.
}
```

Trong môi trường **không có reader khác** và khóa vẫn ở trạng thái phù hợp, conversion có thể thành công. Nếu thất bại, `converted==0` nhưng **read lock gốc vẫn cần được giải phóng**, vì conversion thất bại không phải là unlock.

Đoạn trên dùng `unlock(stamp)` chung ở `finally` vì stamp có thể là read hoặc write. **Không gọi đồng thời `unlockRead(oldStamp)` và `unlockWrite(newStamp)`**; khi chuyển thành công, quyền giữ lock cũ đã được chuyển theo mode.

### 10.2. Nếu conversion thất bại thì sao?

Một phương án đúng là giải phóng read lock, lấy write lock, **đọc lại điều kiện** trước khi cập nhật:

```java
long stamp = lock.readLock();
boolean converted = false;
try {
    long writeStamp = lock.tryConvertToWriteLock(stamp);
    if (writeStamp != 0L) {
        stamp = writeStamp;
        converted = true;
        // Ghi khi đang giữ write lock.
        updateConditionally();
    }
} finally {
    lock.unlock(stamp);
}

if (!converted) {
    long writeStamp = lock.writeLock();
    try {
        // Kiểm tra LẠI điều kiện do có một khoảng không khóa.
        updateConditionally();
    } finally {
        lock.unlockWrite(writeStamp);
    }
}
```

Snippet giả định `updateConditionally` tự kiểm tra điều kiện hiện thời dưới write lock, và không tự lấy lại lock. Khoảng thời gian giữa unlock read và lấy write lock có thể có writer khác cập nhật state; không dùng kết quả đọc trước đó như sự thật vĩnh viễn.

### 10.3. Không nhầm conversion với tryLock mới

`tryConvertToWriteLock` có thể giữ/chuyển cùng một quyền truy cập đang có. `writeLock` là yêu cầu acquire mới. Nếu đang giữ read lock mà acquire write mới, có thể tự deadlock. Khi conversion thành công, thay đổi mode và stamp phải được xử lý ngay trong mã.

### 10.4. Vì sao `unlock(stamp)` không nên được lạm dụng?

`unlock(stamp)` tiện khi mode cuối có thể thay đổi, nhưng với những method chỉ lấy read hoặc chỉ lấy write, `unlockRead`/`unlockWrite` rõ ràng và dễ phát hiện lỗi hơn. Dùng phương thức chuyên biệt làm nổi bật contract của critical section.

## 11. Optimistic read: không giữ khóa, không unlock

Một trong những tính năng đặc trưng của StampedLock là **optimistic read**. Tuy nhiên, đó **không phải** một read lock đã được cấp.

```java
long stamp = lock.tryOptimisticRead();

int a = left;
int b = right;

if (!lock.validate(stamp)) {
    // Phải đọc lại dưới readLock, không tin hai giá trị vừa lấy.
}
```

Javadoc lưu ý optimistic reads có thể quan sát dữ liệu **không nhất quán ngay trong lúc đang đọc**, đặc biệt khi truy cập cấu trúc object phức tạp. Với ví dụ hai primitive fields, ta có thể sao chép vào local variables, validate rồi chỉ dùng snapshot nếu hợp lệ.

### 11.1. Mẫu fallback sang readLock

```java
Snapshot optimisticSnapshot() {
    long stamp = lock.tryOptimisticRead();
    int a = left;
    int b = right;

    if (!lock.validate(stamp)) {
        stamp = lock.readLock();
        try {
            a = left;
            b = right;
        } finally {
            lock.unlockRead(stamp);
        }
    }
    return new Snapshot(a, b);
}
```

Đoạn này thuộc class giữ `StampedLock lock` cùng hai primitive fields và `Snapshot` record. Khi `validate(stamp)` true, các giá trị đã đọc được chấp nhận theo contract optimistic. Khi false, lấy read lock **thật**, đọc lại và unlockRead trong finally.

**Không viết `finally { unlockRead(optimisticStamp); }`**: optimistic stamp không tương ứng một read lock đang được giữ. Ngoài ra, không đọc/traverse object graph phức tạp trong optimistic section nếu các field/cấu trúc có thể ở trạng thái tạm thời mà code không xử lý được an toàn.

### 11.2. Đừng nói optimistic read “luôn nhanh hơn”

Optimistic read có thể rẻ khi ít write, nhưng cần validate, fallback và phải chịu rủi ro đọc tạm không nhất quán. Với state phức tạp, các bước bổ sung có thể khó đúng và không đáng giá. Dùng `readLock` đơn giản khi cần tính nhất quán và dễ bảo trì.

## 12. Memory visibility và giới hạn bảo đảm

Khóa không chỉ quản lý việc reader/writer đi vào critical section; nó còn đóng vai trò trong **memory synchronization**.

Javadoc StampedLock quy định các phương thức khóa thành công có hiệu ứng đồng bộ bộ nhớ như hành động Lock theo Java Memory Model. Mở write lock thành công có hiệu ứng tương ứng với Unlock action. Khi tất cả các field liên quan được đọc/ghi theo cùng protocol, reader thấy state phù hợp thay vì một tổ hợp dữ liệu do data race.

Tuy nhiên:

- Không gọi `lock.readLock()` chỉ để “ép CPU đọc cache mới nhất” rồi truy cập những đối tượng không được bảo vệ đúng cách ở ngoài vùng khóa.
- Không khẳng định mọi mutable object reference trở thành immutable nhờ lock.
- Không thay `finally` bằng suy luận “JVM tự dọn khóa khi exception”.
- Không coi optimistic read chưa validate có cùng memory guarantee như locked read.
- Không dùng một StampedLock khác để mở khóa đã lấy bằng lock ban đầu.

### 12.1. Dữ liệu immutable và escape khỏi critical section

Nếu bạn tạo immutable snapshot từ các primitive/immutable values trong read lock, caller có thể sử dụng sau khi đã unlock. Nhưng nếu snapshot chỉ chứa reference tới một `ArrayList` mutable nội bộ và caller có thể sửa hoặc đọc ngoài lock, vẫn có vấn đề.

Khi dữ liệu là collections, hãy cân nhắc **defensive copy trong vùng bảo vệ** (với chi phí phù hợp) hoặc thiết kế snapshot immutable. Điều này liên quan tính đúng của dữ liệu, không chỉ chuyện `unlockRead` được gọi.

## 13. Đừng để external IO kéo dài lock scope

Một anti-pattern:

```java
long stamp = lock.writeLock();
try {
    remoteService.call(); // HTTP/network có thể chậm, timeout.
    updateState();
} finally {
    lock.unlockWrite(stamp);
}
```

Nếu remote call mất nhiều giây, tất cả read/write cùng lock có thể phải chờ. Nếu remote client tự gọi callback vào object hiện tại và callback lại cần lock, còn có nguy cơ vòng phụ thuộc/deadlock.

Nên ưu tiên:

1. Chuẩn bị input, validate và gọi IO **ngoài lock** nếu không phá yêu cầu nhất quán.
2. Sau IO, lấy write lock, **kiểm tra lại** version/điều kiện trước khi commit.
3. Commit nội bộ nhanh, giải phóng lock trong finally.
4. Nếu phải giữ một transaction logic qua nhiều hệ thống, dùng một protocol/transaction phù hợp, không cố kéo dài local JVM lock qua network.

**Không có một mẫu chung cho mọi giao dịch**: việc tách IO ra ngoài lock có thể dẫn tới kết quả lỗi thời, nên cần kiểm tra lại state trước khi ghi. Đừng đổi deadlock thành race bằng cách tự ý bỏ khóa mà không giữ bất biến.

## 14. So sánh với synchronized, ReentrantLock và ReentrantReadWriteLock

| Công cụ | Đọc song song? | Có reentrant? | Cách mở khóa | Điểm dùng phù hợp |
| --- | --- | --- | --- | --- |
| `synchronized` | Không đối với cùng monitor | Có | Tự động khi rời monitor/block | Bảo vệ state đơn giản, dễ đọc |
| `ReentrantLock` | Không với cùng lock | Có | `unlock()` trong finally | Lock độc quyền, condition/tryLock/fairness tùy chọn |
| `ReentrantReadWriteLock` | Có nhiều reader | Có | `readLock().unlock()` / `writeLock().unlock()` trong finally | Cần read/write lock với reentrant semantics |
| `StampedLock` | Có nhiều reader | **Không** | `unlockRead(stamp)` / `unlockWrite(stamp)` trong finally | Internal component cần stamped reads/writes và tùy chọn optimistic read |

**Không có “best lock” cho mọi ứng dụng.** `StampedLock` có thêm mode và stamp, yêu cầu quản lý token đúng nên độ phức tạp cao hơn. Nếu hệ thống cần reentrant locking, `Condition` hoặc ownership quen thuộc của Lock, có thể dùng công cụ khác.

### 14.1. StampedLock không trực tiếp implements Lock/ReadWriteLock

`StampedLock` có các adapter:

```java
Lock readView = lock.asReadLock();
Lock writeView = lock.asWriteLock();
ReadWriteLock rwView = lock.asReadWriteLock();
```

Adapter giúp dùng với API chấp nhận `Lock`/`ReadWriteLock`, nhưng không đổi bản chất StampedLock thành reentrant. Các Lock view **không hỗ trợ Condition**; gọi `newCondition()` ném `UnsupportedOperationException` theo Javadoc.

Nếu đã chọn API dùng raw stamp, nên giữ phong cách nhất quán trong class để tránh trộn nhầm vòng đời của view lock và stamp lock. Không gọi `readView.unlock()` thay cho `unlockRead(stamp)` nếu không có lý do và protocol tương ứng.

### 14.2. asReadLock giúp bớt quản lý stamp, nhưng không đổi yêu cầu finally

Với Lock view:

```java
Lock readView = lock.asReadLock();
readView.lock();
try {
    readState();
} finally {
    readView.unlock();
}
```

Đây là snippet trong method. `finally` vẫn quan trọng, chỉ khác là view nhận trách nhiệm quản lý stamp bên dưới. Khi mục tiêu cụ thể là hiểu `StampedLock.readLock()`/`writeLock()`, nên học raw stamp trước.

## 15. Thiết kế unit test concurrency không bị flaky

### 15.1. Không dùng Thread.sleep để đoán thứ tự lấy khóa

Test như:

```java
Thread.sleep(50);
// Mong rằng reader đã lấy khóa.
```

không chứng minh reader đã chạy, bởi scheduler, CPU, GC và CI có thể thay đổi. Thay bằng `CountDownLatch`: mỗi reader đếm xuống **sau khi đã lấy read lock**, test chờ cả hai báo sẵn sàng rồi mới thử write lock.

### 15.2. Test hai read lock đồng thời

Tạo executor hai thread. Cả hai reader chạy:

```java
long stamp = lock.readLock();
try {
    ready.countDown();
    release.await();
} finally {
    lock.unlockRead(stamp);
}
```

Trong test chính:

1. Đợi `ready.await()` sau khi cả hai reader đã lấy khóa.
2. `lock.getReadLockCount()` được dùng như **dữ liệu quan sát** để xác nhận trong fixture rằng có hai read holds.
3. Gọi `tryWriteLock()`; với hai reader đang thực sự giữ lock, lần thử trả 0.
4. Thả `release`.
5. Chờ tasks hoàn tất rồi kiểm tra writer có thể lấy khóa.

**`getReadLockCount()` là API cho monitoring, không nên dùng làm điều kiện điều khiển đồng bộ trong production.** Test này có latch điều khiển state nên phép đọc được giải thích trong phạm vi fixture.

### 15.3. Test finally khi throw

- Có một method lấy write lock rồi ném `IllegalStateException` trong `try`, unlock trong `finally`.
- Caller catch exception, sau đó gọi `tryWriteLock` và kiểm tra stamp khác 0.
- Lặp lại tương tự với read lock rồi `tryReadLock`.
- Đảm bảo lần thử thành công cũng được unlock trong `finally`, tránh test tự rò rỉ lock.

### 15.4. Test sai stamp và double unlock

Sau một lần `unlockRead(stamp)` thành công, gọi `unlockRead(stamp)` lần hai phải bị từ chối trong trạng thái test hiện tại; Javadoc quy định `IllegalMonitorStateException` nếu stamp không khớp trạng thái lock.

Đừng dựa vào chuỗi exception message; kiểm tra kiểu exception. Và đừng tái sử dụng một stamp của lock instance này để mở khóa một lock instance khác.

### 15.5. Test conversion rồi unlock stamp mới

Giữ duy nhất một read lock, thử `tryConvertToWriteLock`. Nếu conversion thành công, cập nhật biến stamp rồi gọi `unlock(stamp)` trong finally. Test này xác minh **quy tắc quản lý token sau chuyển mode**, không phải lời hứa conversion sẽ luôn thành công khi có luồng khác tranh chấp.

## 16. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây minh họa trọn bộ:

- Reader đọc cùng hai field qua `readLock`.
- Writer cập nhật cặp qua `writeLock`.
- Exception trong body của read/write không làm rò rỉ lock vì `finally`.
- Thử write khi đang giữ read và thử read khi đang giữ write đều thất bại ngay bằng phiên bản `try...Lock`.
- Hai luồng thực sự giữ read lock cùng lúc; writer bị từ chối trong trạng thái đó.
- Một writer cập nhật sau khi hai readers kết thúc.
- Double unlock bị báo lỗi.
- Conversion thành công từ read stamp sang write stamp và dùng `unlock(stamp)`.
- Timed tryReadLock trả 0 khi write lock vẫn đang được giữ.
- `ExecutorService` được shutdown, kết quả không phụ thuộc tên thread hoặc race thắng.

Tạo file **`StampedLockFinallyDemo.java`**:

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.*;

public class StampedLockFinallyDemo {
    record Snapshot(int left, int right) {}

    static class Pair {
        final StampedLock lock = new StampedLock();
        private int left, right;

        void addBoth(int delta) {
            long stamp = lock.writeLock();
            try {
                left += delta;
                right += delta;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        Snapshot snapshot() {
            long stamp = lock.readLock();
            try {
                return new Snapshot(left, right);
            } finally {
                lock.unlockRead(stamp);
            }
        }

        void failUnderWriteLock() {
            long stamp = lock.writeLock();
            try {
                throw new IllegalStateException(
                        "demo write failure");
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        void failUnderReadLock() {
            long stamp = lock.readLock();
            try {
                throw new IllegalArgumentException(
                        "demo read failure");
            } finally {
                lock.unlockRead(stamp);
            }
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(error);
        }
    }

    static void reader(
            Pair pair,
            CountDownLatch ready,
            CountDownLatch release) {
        long stamp = pair.lock.readLock();
        try {
            ready.countDown();
            await(release);
        } finally {
            pair.lock.unlockRead(stamp);
        }
    }

    public static void main(String[] args) throws Exception {
        Pair pair = new Pair();
        pair.addBoth(3);
        System.out.println("afterWrite=" + pair.snapshot());

        // Một exception trong write body không giữ khóa mãi.
        boolean writerExceptionCaught = false;
        try {
            pair.failUnderWriteLock();
        } catch (IllegalStateException error) {
            writerExceptionCaught = true;
        }
        check(writerExceptionCaught, "write exception");

        long writeAgain = pair.lock.tryWriteLock();
        check(writeAgain != 0L, "write released on exception");
        try {
            System.out.println("writeAvailableAfterException="
                    + (writeAgain != 0L));
        } finally {
            pair.lock.unlockWrite(writeAgain);
        }

        // Tương tự với read body.
        boolean readerExceptionCaught = false;
        try {
            pair.failUnderReadLock();
        } catch (IllegalArgumentException error) {
            readerExceptionCaught = true;
        }
        check(readerExceptionCaught, "read exception");

        long readAgain = pair.lock.tryReadLock();
        check(readAgain != 0L, "read released on exception");
        try {
            System.out.println("readAvailableAfterException="
                    + (readAgain != 0L));
        } finally {
            pair.lock.unlockRead(readAgain);
        }

        long heldRead = pair.lock.readLock();
        try {
            long blocked = pair.lock.tryWriteLock();
            check(blocked == 0L, "no upgrade");
            System.out.println("writeBlockedByRead="
                    + (blocked == 0L));
        } finally {
            pair.lock.unlockRead(heldRead);
        }

        long heldWrite = pair.lock.writeLock();
        try {
            long blocked = pair.lock.tryReadLock();
            check(blocked == 0L, "no read in write");
            System.out.println("readBlockedByWrite="
                    + (blocked == 0L));
        } finally {
            pair.lock.unlockWrite(heldWrite);
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        try {
            CompletableFuture<Void> first =
                    CompletableFuture.runAsync(
                            () -> reader(pair, ready, release), pool);
            CompletableFuture<Void> second =
                    CompletableFuture.runAsync(
                            () -> reader(pair, ready, release), pool);

            await(ready);
            System.out.println("concurrentReaders="
                    + pair.lock.getReadLockCount());
            long blocked = pair.lock.tryWriteLock();
            check(blocked == 0L, "writer blocked by two readers");
            System.out.println("writerBlockedByTwoReaders="
                    + (blocked == 0L));

            release.countDown();
            CompletableFuture.allOf(first, second).join();
        } finally {
            release.countDown();
            pool.shutdown();
            check(pool.awaitTermination(
                    5, TimeUnit.SECONDS), "pool shutdown");
        }

        pair.addBoth(2);
        System.out.println("afterReadersAndWriter="
                + pair.snapshot());

        // Stamp đã unlock không được sử dụng lần hai.
        long once = pair.lock.readLock();
        pair.lock.unlockRead(once);
        boolean invalidRejected = false;
        try {
            pair.lock.unlockRead(once);
        } catch (IllegalMonitorStateException error) {
            invalidRejected = true;
        }
        check(invalidRejected, "double unlock");
        System.out.println("doubleUnlockRejected="
                + invalidRejected);

        // Conversion có thể thay mode: unlock theo stamp cuối.
        long toConvert = pair.lock.readLock();
        boolean converted = false;
        try {
            long next =
                    pair.lock.tryConvertToWriteLock(toConvert);
            if (next != 0L) {
                toConvert = next;
                converted = true;
            }
        } finally {
            pair.lock.unlock(toConvert);
        }
        check(converted, "conversion");
        System.out.println("conversionUpdatedStamp=" + converted);

        // Khi writer giữ lock, timed tryReadLock trả 0.
        long timedWriter = pair.lock.writeLock();
        try {
            long noRead = pair.lock.tryReadLock(
                    5, TimeUnit.MILLISECONDS);
            check(noRead == 0L, "timed read fails");
            System.out.println("timedReadWhileWriterHeld="
                    + noRead);
        } finally {
            pair.lock.unlockWrite(timedWriter);
        }

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac StampedLockFinallyDemo.java
java StampedLockFinallyDemo
```

**Stdout kỳ vọng chính xác khi các assertion đều qua:**

```text
afterWrite=Snapshot[left=3, right=3]
writeAvailableAfterException=true
readAvailableAfterException=true
writeBlockedByRead=true
readBlockedByWrite=true
concurrentReaders=2
writerBlockedByTwoReaders=true
afterReadersAndWriter=Snapshot[left=5, right=5]
doubleUnlockRejected=true
conversionUpdatedStamp=true
timedReadWhileWriterHeld=0
ALL CHECKS PASSED
```

### 16.1. Giải thích output theo nhóm

**Ghi/đọc ổn định:** `pair.addBoth(3)` tăng hai giá trị từ 0 lên 3. `snapshot()` đọc dưới read lock, nên nhận cặp `Snapshot[left=3,right=3]`.

**Mở khóa sau exception:** Hai method cố ý ném exception trong `try` nhưng vẫn gọi `unlockWrite`/`unlockRead` trong `finally`. Các phương thức `tryWriteLock`/`tryReadLock` sau đó có thể cấp khóa thành công.

**Read và write xung đột:** Trong khi cùng luồng còn giữ read lock, `tryWriteLock` trả 0. Trong khi giữ write lock, `tryReadLock` trả 0. Đoạn test **không gọi writeLock() dạng chờ** trong read critical section, vì sẽ có nguy cơ tự chặn.

**Hai reader đồng thời:** Hai task được chạy trên pool có hai thread và mỗi task chỉ đếm `ready` sau khi đã lấy read lock. Thread chính đợi cả hai, rồi quan sát `getReadLockCount()==2` trong fixture. `tryWriteLock()==0` trong khi cả hai vẫn giữ read lock.

**Sau khi readers mở khóa:** `release.countDown` cho phép hai task thoát, `CompletableFuture.allOf(...).join()` chờ chúng xong; sau đó writer tăng thêm 2, tạo `Snapshot[left=5,right=5]`.

**Double unlock:** Gọi `unlockRead` lần hai với stamp đã giải phóng ném `IllegalMonitorStateException`; test catch đúng loại nên in true.

**Conversion:** Khi chỉ còn một read lock, conversion sang write lock có thể thành công. Mẫu đổi biến `toConvert` thành stamp mới và `unlock(toConvert)` đúng mode cuối.

**Timed read:** Khi write lock đang được giữ, `tryReadLock(5, MILLISECONDS)` không lấy được và trả 0. Nếu không xử lý được việc không cấp khóa, tuyệt đối không dùng stamp 0 để đọc shared state hay unlock.

## 17. Bài toán ứng dụng: repository với state có nhiều field

Giả sử một service giữ bộ ba trường:

```java
private long accepted;
private long rejected;
private long total;
```

Bất biến: `total == accepted + rejected`. Một luồng cập nhật counters, luồng khác đọc để hiển thị.

### 17.1. Nếu không có cùng lock

Writer:

```java
accepted++;
total++;
```

Reader có thể đọc `accepted` mới và `total` cũ nếu không có đồng bộ phù hợp. Việc mỗi phép đọc `long` riêng lẻ diễn ra không đủ đảm bảo **snapshot của bộ ba** phù hợp bất biến.

### 17.2. Có read/write lock bảo vệ nhóm field

```java
void accept() {
    long stamp = lock.writeLock();
    try {
        accepted++;
        total++;
    } finally {
        lock.unlockWrite(stamp);
    }
}

Counters snapshot() {
    long stamp = lock.readLock();
    try {
        return new Counters(accepted, rejected, total);
    } finally {
        lock.unlockRead(stamp);
    }
}
```

Đây là snippet trong class có `lock` và `record Counters(long accepted,long rejected,long total){}`. Cặp critical sections cùng một lock giúp reader nhìn một bộ ba không bị writer chen giữa, miễn mọi mutation của ba field tuân thủ protocol.

Nếu có callback bên ngoài như gửi metric, gửi network hoặc ghi log chậm, đừng tự động giữ lock trong suốt những thao tác ấy. Trước tiên copy snapshot dưới read lock; rồi log/publish ngoài lock nếu nghiệp vụ cho phép.

### 17.3. Nếu cần cập nhật theo trạng thái hiện tại

Một operation kiểu “nếu total chưa vượt max thì accept” cần **đọc điều kiện và cập nhật cùng trong write lock**, không phải đọc với read lock rồi thả ra rồi write mà không kiểm tra lại:

```java
boolean acceptIfRoom(long limit) {
    long stamp = lock.writeLock();
    try {
        if (total >= limit) {
            return false;
        }
        accepted++;
        total++;
        return true;
    } finally {
        lock.unlockWrite(stamp);
    }
}
```

Đây là method trong class với các field đã nêu. Nếu bạn chỉ đọc `total` dưới read lock, unlock, rồi viết sau đó mà không recheck, hai writer có thể cùng dựa trên một điều kiện cũ. Đây là bẫy **TOCTOU**: readLock bảo vệ một phép đọc, nhưng không tự giữ điều kiện đúng sau khi đã mở khóa.

## 18. Các trường hợp ngoại lệ, lỗi và rủi ro phổ biến

### Lỗi 1. Lấy read lock rồi quên unlock khi có return sớm

**Sai:** unlock nằm cuối method, còn `return` ở giữa. **Sửa:** đặt `unlockRead(stamp)` trong `finally` bao quanh toàn bộ critical section.

### Lỗi 2. Lấy write lock rồi exception bỏ qua unlock

**Sai:** `update` có thể ném exception làm writer lock bị giữ. **Sửa:** `unlockWrite(stamp)` trong `finally` ngay sau acquisition.

### Lỗi 3. Dùng unlockWrite cho read stamp

**Sai mode:** read stamp không đại diện write lock. **Sửa:** dùng `unlockRead(readStamp)`; sai stamp/mode có thể ném `IllegalMonitorStateException`.

### Lỗi 4. Dùng unlockRead cho optimistic read stamp

Optimistic read **không giữ read lock**. **Sửa:** dùng `validate(stamp)`; nếu fallback sang readLock, chỉ unlock **read stamp thật**.

### Lỗi 5. Bỏ qua `stamp == 0L` sau try lock

`tryReadLock` và `tryWriteLock` có thể thất bại trả 0. **Sửa:** chỉ vào critical section và `finally` khi có stamp khác 0.

### Lỗi 6. Unlock stamp hai lần

Sau unlock lần đầu, stamp không còn quyền khóa hợp lệ. **Sửa:** mỗi acquisition thành công chỉ có đúng một release tương ứng; tránh nhánh code unlock trước rồi finally lại unlock.

### Lỗi 7. Ghi đè biến stamp sau conversion mà không cập nhật mode

`tryConvertToWriteLock` thành công trả write stamp. **Sửa:** dùng stamp mới và `unlock(stamp)` hoặc chọn unlock method theo mode cuối; không unlockRead stamp cũ.

### Lỗi 8. Gọi writeLock trong lúc đã giữ readLock

Không có reentrant upgrade. **Sửa:** `tryConvertToWriteLock` hoặc release read rồi acquire write và recheck điều kiện.

### Lỗi 9. Một method under write lock gọi method khác cũng lấy write lock

Non-reentrant có thể tự chặn. **Sửa:** tách method nội bộ không lấy khóa, kiểm soát phạm vi gọi rõ.

### Lỗi 10. Sửa dữ liệu dưới read lock

Nhiều readers có thể chạy đồng thời; dữ liệu bị race. **Sửa:** dùng writeLock cho mutation.

### Lỗi 11. Chỉ khóa reader, không khóa writer

Mọi đường đọc/ghi phải tuân thủ một protocol để giữ bất biến. **Sửa:** đóng gói mutable state và chia sẻ cùng StampedLock cho toàn bộ methods liên quan.

### Lỗi 12. Giữ write lock trong khi gọi API mạng

Chậm, dễ contention và có thể tạo vòng phụ thuộc callback. **Sửa:** chuẩn bị bên ngoài, commit ngắn dưới lock, recheck version/điều kiện khi cần.

### Lỗi 13. Lấy return reference tới một collection mutable bên trong

Unlock xong caller vẫn chạm shared object. **Sửa:** defensive copy/immutable snapshot trong read critical section hoặc thiết kế ownership an toàn.

### Lỗi 14. Cho rằng finally tự rollback mutation

`finally` chỉ đảm bảo release. **Sửa:** thiết kế commit có bất biến và rollback/idempotency riêng cho mọi lỗi giữa critical section.

### Lỗi 15. Tin rằng StampedLock luôn fair cho reader/writer

Javadoc không đưa ra chính sách ưu tiên nhất quán. **Sửa:** không giả định starvation-free hoặc FIFO; chọn lock/architecture khác nếu có yêu cầu fairness nghiêm ngặt.

### Lỗi 16. Dùng `getReadLockCount` làm điều kiện cấp quyền ghi

`getReadLockCount()` dành cho monitoring, không phải điều kiện sync. **Sửa:** dựa vào lock acquisition thực tế, không check count rồi tự quyết định.

### Lỗi 17. Dùng readLock() để đợi nhưng muốn cancellation nhanh

`readLock()` là blocking acquisition thông thường. **Sửa:** dùng `readLockInterruptibly()` hoặc timed tryReadLock phù hợp với chính sách hủy/deadline.

### Lỗi 18. Nuốt InterruptedException rồi retry vô hạn

Nếu thread đã bị yêu cầu hủy, bỏ qua signal có thể giữ công việc chờ vô hạn. **Sửa:** propagate hoặc khôi phục cờ interrupt theo contract tầng trên.

### Lỗi 19. Dùng StampedLock như remote/distributed lock

StampedLock phối hợp **trong JVM**, stamps không phải token bảo mật hoặc giao dịch phân tán. **Sửa:** dùng coordination/transaction dịch vụ có contract phù hợp khi có nhiều process.

### Lỗi 20. Dùng chung stamp như một field mutable

Lưu `lastStamp` chung cho nhiều thread có thể khiến luồng A ghi đè stamp của luồng B rồi unlock sai. **Sửa:** giữ stamp trong **biến local** của mỗi acquisition, chỉ truyền qua method theo một protocol rõ khi thật cần.

### Lỗi 21. Dùng tryUnlockRead/tryUnlockWrite thường xuyên thay stamp

Các API không cần stamp được cung cấp cho những ca recovery đặc biệt; chúng **không phải** cách thay thế tiêu chuẩn cho unlock đúng token. **Sửa:** lưu stamp đúng và unlock chuyên biệt trong finally.

### Lỗi 22. Đổi synchronized sang StampedLock mà không đo hiệu năng

Stamp management, mode conversion và contention có chi phí. **Sửa:** chọn theo yêu cầu correctness và benchmark thực với workload có nhiều readers/writers tương ứng.

### Lỗi 23. Trộn adapter `asReadLock()` và raw stamp tùy tiện

Hai phong cách điều khiển vòng đời khác nhau có thể dễ bị nhầm. **Sửa:** thống nhất một protocol cho class; nếu dùng adapter, vẫn `lock()/unlock()` trong finally và không tự đoán stamp nội bộ.

### Lỗi 24. Bắt exception trong critical section rồi tiếp tục mà không giữ invariant

Catch lỗi không tự khôi phục dữ liệu. **Sửa:** phân tích điểm commit, giữ state nhất quán trước unlock, hoặc trả lỗi rõ cho caller khi rollback không thể thực hiện.

## 19. Bài tập thực hành và đáp án

**Bài 1.** `readLock()` trả kiểu gì?

**Đáp án:** `long`; giá trị là **read stamp** của một lần acquisition thành công và phải được chuyển lại cho `unlockRead(stamp)`.

**Bài 2.** `writeLock()` có thể chạy đồng thời với một reader đã giữ read lock không?

**Đáp án:** Không. Write mode đòi độc quyền; nó chờ tới khi những read locks gây xung đột được giải phóng.

**Bài 3.** Có thể có hai reader cùng giữ read lock không?

**Đáp án:** Có, nếu không có writer đang giữ exclusive lock và scheduling cho phép; read mode là non-exclusive.

**Bài 4.** Vì sao unlock phải ở finally?

**Đáp án:** Vì critical section có thể thoát bằng `return` hoặc ném exception. `finally` giúp release dù đường thoát thay đổi.

**Bài 5.** Vì sao nên đặt `long stamp = lock.writeLock()` ngay trước khối try?

**Đáp án:** Để chỉ vào `try/finally` **sau khi acquisition đã thành công**. Nếu acquisition ném exception trước khi có stamp, không được unlock một khóa không tồn tại.

**Bài 6.** `tryWriteLock()` trả 0. Nên gọi `unlockWrite(0)` không?

**Đáp án:** Không. Stamp 0 nghĩa là lần thử không lấy được khóa; không có write critical section để unlock.

**Bài 7.** Nếu một write critical section ném exception, `finally` có tự rollback field đã sửa không?

**Đáp án:** Không. Nó giải phóng lock; tính toàn vẹn dữ liệu/rollback cần được thiết kế riêng.

**Bài 8.** Đang giữ read lock, gọi `writeLock()` để “nâng cấp”, có an toàn không?

**Đáp án:** Không. StampedLock non-reentrant và read lock chưa được thả sẽ ngăn write mode. Dùng conditional conversion hoặc release/reacquire + recheck.

**Bài 9.** `tryConvertToWriteLock` trả 0 khi đang giữ read lock thì phải làm gì với stamp cũ?

**Đáp án:** Read stamp cũ vẫn có nghĩa trong trường hợp conversion thất bại; cần giải phóng bằng `unlockRead`/`unlock(stamp)` theo đúng protocol trước khi đi hướng khác.

**Bài 10.** Conversion thành công nhưng finally vẫn gọi `unlockRead(oldStamp)` có đúng không?

**Đáp án:** Không. Khi conversion thành write mode, phải dùng write stamp mới hoặc `unlock(stamp)` với stamp đã cập nhật.

**Bài 11.** Optimistic stamp từ `tryOptimisticRead` có thể truyền cho `unlockRead`?

**Đáp án:** Không. Optimistic read không nắm read lock. Dùng `validate`; fallback mới lấy read lock thật và unlock nó.

**Bài 12.** Khi giữ write lock, `tryReadLock()` có thể trả gì?

**Đáp án:** Thông thường trả `0L` vì read lock không thể được cấp khi có exclusive writer; trong chương trình test điều kiện này được xác định.

**Bài 13.** Hai luồng cùng giữ read lock, có thể biết chắc writer nào sẽ được cấp tiếp theo khi readers thả khóa?

**Đáp án:** Không. StampedLock không có chính sách ưu tiên reader/writer nhất quán; không dựa vào thứ tự scheduler.

**Bài 14.** Tại sao không nên gọi `Thread.sleep(100)` để “chờ reader lấy khóa” trong unit test?

**Đáp án:** Sleep không chứng minh reader đã chạy. Dùng latch được kích hoạt sau khi acquire thành công, hoặc Future/completion barrier phù hợp.

**Bài 15.** Đang giữ write lock và cần gọi HTTP service tốn 5 giây, có nên giữ khóa hết thời gian đó?

**Đáp án:** Thường không, vì có thể chặn mọi reader/writer, nhưng việc dời IO ra ngoài phải kèm recheck dữ liệu/phiên bản nếu logic yêu cầu nhất quán.

**Bài 16.** Nếu một method public giữ write lock gọi một method private cũng giữ write lock, có thể xảy ra gì?

**Đáp án:** Deadlock tự chờ do StampedLock không reentrant. Nên tách method nội bộ hoạt động dưới khóa đã được cấp mà không acquire thêm.

**Bài 17.** `getReadLockCount()` có nên dùng để quyết định điều kiện synchronized logic không?

**Đáp án:** Không. Nó dành cho monitoring, không làm một thao tác kiểm tra rồi ghi trở thành nguyên tử. Dựa vào acquisition/token thật.

**Bài 18.** StampedLock có bảo đảm thread đã acquire mới là thread được unlock không?

**Đáp án:** Không có thread ownership theo thiết kế; khóa có thể được release/convert từ thread khác nếu mang stamp hợp lệ. Tuy vậy, chuyển stamp giữa threads không phải pattern mặc định nên dùng, vì tăng độ phức tạp và rủi ro quản lý vòng đời.

**Bài 19.** `asReadLock().newCondition()` có hỗ trợ Condition không?

**Đáp án:** Không. Các Lock views của StampedLock không hỗ trợ Condition; gọi `newCondition()` ném `UnsupportedOperationException`.

**Bài 20.** Nếu đã có `ReentrantReadWriteLock`, có nên chuyển sang StampedLock chỉ vì muốn hai reader cùng chạy không?

**Đáp án:** Không nhất thiết. Cả hai đều có read mode cho nhiều reader. Cần xét reentrancy, ownership, fairness, optimistic reads, benchmark và tính dễ bảo trì trước khi chọn.

## 20. Checklist production

- [ ] Mọi thao tác ghi lên state chia sẻ được bảo vệ bởi `writeLock` của đúng một StampedLock.
- [ ] Những thao tác đọc nhiều field cần snapshot nhất quán được bảo vệ bởi `readLock` hoặc một protocol tương đương đã xác minh.
- [ ] Read critical section không có mutation/side effect trên state được bảo vệ.
- [ ] Lưu đúng `long stamp` trong biến local, không lưu stamp dùng chung giữa các threads tùy tiện.
- [ ] Với read lock: `readLock()` → `try` → `unlockRead(stamp)` trong `finally`.
- [ ] Với write lock: `writeLock()` → `try` → `unlockWrite(stamp)` trong `finally`.
- [ ] Nếu tryLock có thể trả 0, code kiểm tra 0 trước khi vào protected region và trước khi unlock.
- [ ] Không gọi unlock cho optimistic stamp; chỉ `validate` và fallback locked read khi cần.
- [ ] Không unlock cùng stamp hai lần, không dùng sai mode hoặc sai StampedLock instance.
- [ ] Sau mode conversion, cập nhật stamp và release theo mode cuối.
- [ ] Không gọi writeLock khi vẫn giữ readLock để “upgrade”; dùng conversion hoặc unlock/reacquire/recheck.
- [ ] Tránh nested methods tự re-acquire StampedLock (non-reentrant).
- [ ] Không giữ lock qua IO/network chậm nếu có thể tách khỏi critical section một cách an toàn.
- [ ] Nếu exception xảy ra giữa nhiều mutations, đã có strategy bảo vệ invariant/rollback phù hợp.
- [ ] Có hỗ trợ timeout/interrupt nếu nghiệp vụ cần giới hạn thời gian chờ acquisition.
- [ ] Không giả định fairness/FIFO hoặc quyền ưu tiên reader/writer.
- [ ] Không dùng `isReadLocked/getReadLockCount` cho điều kiện đồng bộ chính.
- [ ] Không trả mutable internal reference mà caller có thể sửa/đọc sau unlock không an toàn.
- [ ] Unit tests dùng CountDownLatch/Future để phối hợp, tránh sleep mang tính may rủi.
- [ ] Test exception trong read/write body, double unlock, tryLock==0, hai reader đồng thời và conversion nếu dùng.
- [ ] ExecutorService được shutdown/awaitTermination khi component sở hữu pool.
- [ ] Có benchmark theo workload thực nếu StampedLock được chọn vì hiệu năng.
- [ ] Những API và ví dụ dựa trên Java Time/JUC công khai hiện đại, không dùng các kỹ thuật legacy.

## 21. Tài liệu tham khảo chính thức, còn áp dụng

1. [Oracle Java SE 26 — StampedLock: readLock, writeLock, unlockRead, unlockWrite, unlock, conversion, interruptible/timed methods, non-reentrancy và policy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
2. [Oracle Java SE 26 — Lock: hành vi lock/unlock, interruption và memory synchronization](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/Lock.html)
3. [Oracle Java SE 26 — ReentrantReadWriteLock: read/write modes và reentrant semantics để so sánh](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
4. [Oracle Java SE 26 — CountDownLatch: tín hiệu phối hợp test đa luồng](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
5. [Oracle Java SE 26 — CompletableFuture: runAsync, allOf và join dùng trong bài test](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
6. [Oracle Java SE 26 — ExecutorService: quản lý vòng đời và shutdown pool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
7. [Oracle Java SE 26 — IllegalMonitorStateException: lỗi khi mở khóa với stamp không khớp](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/IllegalMonitorStateException.html)
8. [OpenJDK — StampedLock.java: mã nguồn triển khai để tham khảo, không phải API contract](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/concurrent/locks/StampedLock.java)

**Ghi nhớ cốt lõi:** `readLock()` và `writeLock()` trả **stamp** để chứng minh một lần acquisition thành công. Khi đã có stamp, mọi đường thoát khỏi critical section phải chạy đúng **`unlockRead(stamp)` hoặc `unlockWrite(stamp)` trong `finally`**. Với StampedLock, việc giữ đúng token, đúng mode và không tự lấy lại khóa là một phần của tính đúng chương trình; `finally` bảo vệ vòng đời khóa nhưng **không thay thế transaction/rollback** cho dữ liệu.
