# StampedLock: View ReadWriteLock và hợp đồng khóa

## 1. Mục tiêu và tình huống sử dụng

`java.util.concurrent.locks.StampedLock` là bộ khóa có **read mode**, **write mode** và **optimistic read mode**, có từ Java 8 và vẫn được hỗ trợ trong JDK hiện đại. API gốc của nó hoạt động bằng một **stamp kiểu `long`**: `readLock()` và `writeLock()` cấp stamp; `unlockRead(stamp)` và `unlockWrite(stamp)` dùng stamp để giải phóng quyền truy cập.

Nhưng nhiều thư viện, framework hoặc lớp domain được thiết kế theo hai giao diện chuẩn:

- `java.util.concurrent.locks.Lock`: cung cấp `lock()`, `unlock()`, `tryLock()`, `lockInterruptibly()`…
- `java.util.concurrent.locks.ReadWriteLock`: cung cấp **một `Lock` cho người đọc** và **một `Lock` cho người ghi** qua `readLock()` và `writeLock()`.

Khi muốn giữ cơ chế StampedLock nhưng API tiêu thụ chỉ biết hai giao diện chuẩn, bạn có thể tạo **view (adapter)**:

```java
StampedLock stamped = new StampedLock();
ReadWriteLock view = stamped.asReadWriteLock();

Lock read = view.readLock();
Lock write = view.writeLock();
```

Kể từ đây, caller có thể dùng `read.lock()` và `read.unlock()` mà **không trực tiếp quản lý một `long stamp`**. Tương tự, `write.lock()` và `write.unlock()` bao bọc chức năng write mode.

Tuy nhiên, một interface giống nhau **không làm mọi implementation có cùng tính chất**. ReadWriteLock view này vẫn dựa vào **chính StampedLock ban đầu** và giữ các giới hạn quan trọng:

- **Không reentrant**: không được hiểu như một `ReentrantReadWriteLock`.
- **Không hỗ trợ `Condition`** cho cả read view và write view.
- **Không có quyền sở hữu theo thread** như đa số implementation lock reentrant.
- **Không có cam kết fairness/FIFO** cho reader/writer.
- Không cung cấp **optimistic read** hay **chuyển mode bằng stamp** thông qua interface `ReadWriteLock`.
- Phải bảo đảm **`unlock()` trong `finally`** và chỉ unlock sau khi lock đã lấy thành công.

Đây chính là chủ đề **“View ReadWriteLock và hợp đồng khóa”** của mục **“StampedLock”**: hiểu công dụng adapter, các lời hứa thực sự của interface và những khác biệt phải nắm trước khi sử dụng trong code production.

Sau bài này, bạn sẽ thực hành được chương trình Java 17+ kiểm tra hai reader đồng thời, writer độc quyền, timed/interruptible acquisition, Condition không hỗ trợ, state chia sẻ giữa raw StampedLock với các view và việc mở khóa an toàn.

## 2. Ba phương thức tạo view chính thức

Các phương thức public được StampedLock cung cấp:

```java
Lock asReadLock();
Lock asWriteLock();
ReadWriteLock asReadWriteLock();
```

Diễn giải:

| Phương thức trên StampedLock | Kiểu trả về | Chức năng |
| --- | --- | --- |
| `asReadLock()` | `Lock` | View ở **read mode**, `Lock.lock()` tương ứng với `StampedLock.readLock()` |
| `asWriteLock()` | `Lock` | View ở **write mode**, `Lock.lock()` tương ứng với `StampedLock.writeLock()` |
| `asReadWriteLock()` | `ReadWriteLock` | View có hai nửa; `readLock()` ánh xạ đến read view, `writeLock()` ánh xạ đến write view |

Cách dùng đơn giản:

```java
StampedLock core = new StampedLock();

Lock directRead = core.asReadLock();
Lock directWrite = core.asWriteLock();

ReadWriteLock pair = core.asReadWriteLock();
Lock pairRead = pair.readLock();
Lock pairWrite = pair.writeLock();
```

**Tất cả các view lấy từ `core` đều phối hợp qua cùng một trạng thái của StampedLock `core`.** Chúng **không** tạo thêm bốn khóa độc lập. Nếu `pairWrite` đang giữ write lock, lời gọi `directRead.tryLock()` cũng không được cấp read lock.

Điều này tạo điều kiện tích hợp: một module có thể dùng `ReadWriteLock` view, trong khi code sở hữu StampedLock còn biết các phương thức gốc. Nhưng **không nên trộn kiểu quản lý khóa trong cùng một critical section** chỉ để tận dụng tiện ích.

### 2.1. “View” nghĩa là adapter, không phải bản sao

Sơ đồ:

```text
                       Một StampedLock core
                        /        |        \
                       /         |         \
                asReadLock   asWriteLock   asReadWriteLock
                    |            |            /       \
                   Lock         Lock        Lock       Lock
                 read view    write view   read view  write view
                       \         |          /          /
                        \________|_________/__________/
                                     |
                          CÙNG trạng thái khóa của core
```

Nếu bạn tạo hai **StampedLock mới** bằng `new StampedLock()`, đó mới là hai khóa độc lập. Nhưng nhiều view cùng bắt nguồn từ **cùng một StampedLock** vẫn điều khiển cùng tài nguyên.

### 2.2. Không dựa vào identity của object view

Contract đảm bảo **hành vi ánh xạ** và việc gắn với StampedLock, không cần code phụ thuộc `core.asReadLock() == core.asReadWriteLock().readLock()` hay số lượng đối tượng adapter được cache. Dù một JVM hiện tại có trả cùng object, chi tiết identity không nên dùng làm điều kiện nghiệp vụ.

Giữ view trong field cuối cùng khi cần:

```java
private final StampedLock stamped = new StampedLock();
private final ReadWriteLock view = stamped.asReadWriteLock();
```

Sau đó truy cập `view.readLock()` và `view.writeLock()` trong methods. Đừng nhầm **identity của Java object adapter** với **trạng thái khóa mà nó bảo vệ**.

## 3. Hợp đồng của ReadWriteLock: một reader-side Lock và một writer-side Lock

`ReadWriteLock` là **interface**, không phải một implementation có mặc định fairness hoặc reentrancy. Nó định nghĩa:

```java
public interface ReadWriteLock {
    Lock readLock();
    Lock writeLock();
}
```

Đây là hình thức rút gọn để hình dung giao diện; không cần triển khai lại interface trong ứng dụng.

Theo hợp đồng:

- **Read lock có thể được giữ đồng thời bởi nhiều reader** miễn không có writer giữ write lock xung đột.
- **Write lock là độc quyền** đối với các luồng sử dụng cùng cặp khóa.
- Sau khi một writer giải phóng write lock, reader thành công lấy read lock tiếp theo phải thấy các cập nhật trước đó theo bảo đảm memory synchronization của interface.

Sơ đồ:

```text
Reader A: [ ---- read ---- ]
Reader B:    [ ---- read -------- ]
Writer C:             (chờ)        [ ----- write ----- ]
Reader D:                                    (chờ)       [read]
```

Đây là **mô hình về tương thích mode**, không phải lời hứa tất cả các thread luôn được xếp lịch theo đúng thứ tự trong hình.

### 3.1. Thứ tự memory synchronization

`ReadWriteLock` yêu cầu memory effects của write lock/release phải có ý nghĩa đối với read lock liên quan. Nói cách khác, sau khi writer cập nhật state dưới write view và giải phóng, reader lấy read view phù hợp có thể thấy những thay đổi đã được công bố theo protocol.

Nhưng bảo đảm này chỉ hữu ích khi **mọi đường đọc và ghi liên quan thực sự sử dụng cùng một lock**. Một phương thức khác sửa field trực tiếp ngoài khóa có thể vẫn tạo data race.

### 3.2. Interface không quyết định fairness và reentrancy

`ReadWriteLock` không bắt tất cả implementations phải reentrant; `StampedLock.asReadWriteLock()` **không reentrant**. `ReentrantReadWriteLock` là một implementation khác có reentrant semantics. Hai object cùng implement/trả interface `ReadWriteLock` **không thể thay thế hoàn toàn** nếu code dựa vào các tính chất bổ sung như reentrancy, ownership, fairness hoặc Condition.

Nếu một thư viện nhận `ReadWriteLock` nhưng **ngầm đòi khóa reentrant**, bạn phải kiểm tra hợp đồng của thư viện ấy trước khi đưa StampedLock view vào.

## 4. Hợp đồng của Lock: thao tác chuẩn và kiểu trả về

Một `Lock` có các API chính:

| API của `Lock` | Kiểu trả về | Ý nghĩa khi là StampedLock view |
| --- | --- | --- |
| `lock()` | `void` | Chờ rồi lấy read/write mode tương ứng |
| `unlock()` | `void` | Giải phóng một lần giữ read/write mode tương ứng; **không truyền stamp** |
| `tryLock()` | `boolean` | Thử không chờ, `true` nếu lấy được; `false` nếu không |
| `tryLock(time,unit)` | `boolean` | Thử trong thời hạn, `true` nếu lấy được, `false` nếu hết thời hạn |
| `lockInterruptibly()` | `void` | Chờ lấy khóa nhưng cho phép bị ngắt bằng `InterruptedException` |
| `newCondition()` | `Condition` | **Không được hỗ trợ**; ném `UnsupportedOperationException` |

So sánh direct API:

```text
StampedLock raw:
  long stamp = stamped.readLock();
  stamped.unlockRead(stamp);

View Lock:
  Lock read = stamped.asReadLock();
  read.lock();
  read.unlock();
```

Khác biệt quan trọng:

- Với **raw StampedLock**, `readLock()` trả `long stamp`; `tryReadLock()` trả **0L nếu thất bại**.
- Với **view Lock**, `lock()` không trả stamp; `tryLock()` trả **boolean**, không phải long.
- Với **raw StampedLock**, caller quản lý token; với **view**, caller phải giữ đúng cặp `lock()/unlock()` và mode nhưng **không thấy stamp**.
- **Không có phương thức `validate(stamp)` trên `Lock`**, vì optimistic read không thuộc contract của Lock/ReadWriteLock.

Không trộn hai kiểu return trong một ví dụ:

```java
// Sai kiểu: tryLock trên Lock trả boolean, không trả stamp.
Lock view = new StampedLock().asReadLock();
// long stamp = view.tryLock();  // Lỗi biên dịch.
```

## 5. Mẫu đúng: Lock view cho một read-only operation

Trong một class giữ state:

```java
private final StampedLock stamped = new StampedLock();
private final ReadWriteLock view = stamped.asReadWriteLock();
private int left;
private int right;

Snapshot snapshot() {
    Lock read = view.readLock();
    read.lock();
    try {
        return new Snapshot(left, right);
    } finally {
        read.unlock();
    }
}
```

Đây là **đoạn trong class**, giả định `record Snapshot(int left, int right) {}` được khai báo. Chương trình hoàn chỉnh ở mục 16 có mọi khai báo cần thiết.

Cấu trúc:

1. Lấy reference `Lock read` từ view, không phải tạo `new StampedLock`.
2. Gọi `read.lock()` **trước `try`**; khi trả về bình thường nghĩa là đã lấy khóa.
3. Đọc toàn bộ state cần đảm bảo nhất quán **bên trong try**.
4. `finally` gọi `read.unlock()` đúng một lần.
5. Trả một snapshot immutable thay vì phơi reference mutable đang được bảo vệ.

### 5.1. Vì sao finally vẫn bắt buộc dù không có stamp?

Không quản lý `long stamp` **không làm khóa tự giải phóng**. Đoạn code:

```java
read.lock();
return new Snapshot(left, right);
// read.unlock() không được thực hiện.
```

là anti-pattern: nó giữ read lock vô hạn nếu không có cơ chế giải phóng khác, làm write lock có thể chờ mãi.

`finally` chạy ngay cả khi có `return` trong `try` hoặc khi body ném exception. Mẫu khóa đúng của interface vẫn giống nguyên tắc Lock truyền thống:

```java
lock.lock();
try {
    protectedWork();
} finally {
    lock.unlock();
}
```

`protectedWork()` là hàm minh họa và đoạn này cần một `Lock lock` đã được cấp trong ngữ cảnh. **Không** gọi `unlock()` ở bên ngoài `finally` như một cleanup best-effort dễ bị bỏ qua.

### 5.2. Đừng viết trong read critical section

Read lock cho phép các reader đồng thời. Nếu bạn đặt `left++` trong read section, hai reader có thể cùng sửa field và phá invariant. Nếu method thay đổi state chia sẻ, dùng write view hoặc cơ chế nguyên tử phù hợp.

## 6. Mẫu đúng: Lock view cho một write operation

```java
void addBoth(int delta) {
    Lock write = view.writeLock();
    write.lock();
    try {
        left += delta;
        right += delta;
    } finally {
        write.unlock();
    }
}
```

Khi tất cả methods đều dùng cùng StampedLock:

- Writer cập nhật hai field trong một exclusive critical section.
- Reader lấy read view không thấy writer đang sửa dở.
- Hai writers không thể đồng thời giữ exclusive mode.
- `finally` vẫn giải phóng khóa nếu body ném exception.

### 6.1. Finally không phải transaction/rollback

Giả sử:

```java
write.lock();
try {
    left += 1;
    riskyOperation(); // Có thể ném exception.
    right += 1;
} finally {
    write.unlock();
}
```

Đây là anti-pattern nếu yêu cầu `left == right` và `riskyOperation` có thể throw ở giữa. `finally` **chỉ đảm bảo unlock**, không khôi phục `left` đã bị tăng.

Hãy thiết kế **validation trước mutate**, hoặc chuẩn bị một immutable state mới rồi commit dưới write lock; nếu cần transaction đa tài nguyên, dùng protocol riêng. Đúng vòng đời khóa là **điều kiện cần**, không đủ cho mọi invariant dữ liệu.

### 6.2. Đóng gói quyền truy cập

Không trao reference tới các mutable fields cho code ngoài rồi chỉ khóa bên trong các method khác. Các đường truy cập có thể bỏ qua view sẽ phá bảo đảm đồng bộ. Giữ state `private`, expose methods như `snapshot()`/`addBoth()` và có quy ước rõ về dữ liệu trả về.

## 7. Hai cách lấy view khác nhau nhưng cùng một khóa

`asReadLock()`/`asWriteLock()` và `asReadWriteLock()` tạo các cách nhìn vào **cùng StampedLock**.

```java
StampedLock stamped = new StampedLock();
ReadWriteLock combined = stamped.asReadWriteLock();

Lock pairRead = combined.readLock();
Lock pairWrite = combined.writeLock();
Lock directRead = stamped.asReadLock();
Lock directWrite = stamped.asWriteLock();
```

Nếu `pairRead.lock()` đang giữ read mode, thì:

```java
pairRead.lock();
try {
    boolean canWrite = directWrite.tryLock();
    // false: write mode bị read mode đang giữ cản.
} finally {
    pairRead.unlock();
}
```

Nếu `pairWrite.lock()` đang giữ write mode, thì:

```java
pairWrite.lock();
try {
    boolean canRead = directRead.tryLock();
    // false: read mode không thể được cấp khi write mode còn giữ.
} finally {
    pairWrite.unlock();
}
```

Hai snippet này **đã là những phép thử deterministic trong cùng luồng**; vì `StampedLock` non-reentrant, không có quyền "cùng thread thì được vào lại" như một số implementation khác.

### 7.1. Khóa raw vẫn nhìn cùng state

Trong lúc read view giữ khóa:

```java
Lock read = stamped.asReadLock();
read.lock();
try {
    long rawWriteStamp = stamped.tryWriteLock();
    // rawWriteStamp == 0L.
} finally {
    read.unlock();
}
```

Điều đó chứng minh view chỉ là adapter. Nhưng không nên lấy bằng view rồi cố giải phóng bằng raw `unlockRead(stamp)` vì bạn **không có stamp của lần acquisition qua view**. Đối với code dùng view, giữ đúng cặp Lock `lock()/unlock()`.

### 7.2. Cùng StampedLock, không phải các vùng bảo vệ độc lập

Nếu một method dùng `asReadLock` để đọc field A và method khác dùng `asWriteLock` để sửa field B, chúng vẫn đồng bộ trên cùng lock. Để được bảo vệ đúng, mọi field dùng chung phải được khai báo rõ ràng về cùng protocol; nếu nhiều tập state thực sự độc lập và contention cao, có thể chọn những lock riêng có biên bảo vệ rõ.

## 8. Non-reentrant: rủi ro nghiêm trọng nhất khi đổi implementation

`StampedLock` **không reentrant**. Một thread đang giữ write view **không có quyền ưu tiên đặc biệt** để lấy write view lần nữa. Điều này khác rõ với `ReentrantReadWriteLock`.

Ví dụ:

```java
Lock write = stamped.asReadWriteLock().writeLock();

write.lock();
try {
    boolean acquiredAgain = write.tryLock();
    // false trong trạng thái hiện tại, không có reentrant hold count.
} finally {
    write.unlock();
}
```

Đoạn test dùng `tryLock()` **không chờ**, tránh tự deadlock. Nếu thay `tryLock()` thành `lock()` khi đã giữ write lock, thread có thể tự block vô hạn.

### 8.1. Nested method làm tự kẹt

Tình huống thường gặp:

```java
void outerUpdate() {
    Lock write = view.writeLock();
    write.lock();
    try {
        innerUpdate(); // innerUpdate cũng write.lock()!
    } finally {
        write.unlock();
    }
}
```

Nếu `innerUpdate` cố lấy cùng write view, caller đang giữ exclusive lock lại đợi một acquisition mới mà StampedLock không reentrant. Chương trình có thể deadlock mà không có thread nào khác.

**Cách sửa:** tách method công khai có acquisition và method nội bộ **không tự lấy lại khóa**, ví dụ `updateUnderWriteLock`. Caller chỉ gọi method nội bộ khi đã nắm write lock.

### 8.2. Read lock dưới write lock cũng không an toàn

Trong `ReentrantReadWriteLock`, writer có thể lấy read lock theo một số quy tắc downgrading. **Đừng đưa kỳ vọng đó sang StampedLock view**.

```java
Lock write = view.writeLock();
Lock read = view.readLock();

write.lock();
try {
    boolean acquiredRead = read.tryLock();
    // false khi write view còn giữ.
} finally {
    write.unlock();
}
```

Không gọi `read.lock()` trong đoạn này vì có thể chờ chính write lock do thread hiện tại nắm giữ.

### 8.3. Read → write upgrade không được tự động hỗ trợ

Nếu đang giữ read view rồi gọi write view:

```java
Lock read = view.readLock();
Lock write = view.writeLock();

read.lock();
try {
    boolean upgraded = write.tryLock();
    // false khi read lock vẫn được giữ.
} finally {
    read.unlock();
}
```

`tryLock` ở đây không phải phép **nâng cấp mode**; nó là thử lấy write lock mới. Nếu dùng `write.lock()` dạng chờ, có thể tự chặn lâu. Qua interface `ReadWriteLock`, **không có API để lấy lại stamp nhằm gọi `tryConvertToWriteLock`**.

Nếu yêu cầu nghiệp vụ cần upgrade, hãy thiết kế lại protocol:

1. Release read view.
2. Acquire write view.
3. **Kiểm tra lại điều kiện nghiệp vụ** sau khi đã có write lock, vì state có thể thay đổi trong khoảng giữa.
4. Hoặc dùng raw stamped API và conversion trong **một flow riêng** được thiết kế nhất quán, không mix token với view.

### 8.4. Non-reentrant không đồng nghĩa mọi lần đọc lồng đều lập tức block

Không nên đơn giản hóa thành “cùng thread có hai read lock luôn thất bại”: read mode cho phép nhiều readers, và behavior có thể còn phụ thuộc trạng thái writer đang chờ. Điều cần nhớ là **không có bảo đảm reentrant**, không dựa vào nested acquisitions để xây flow. Giữ critical section ngắn, không gọi method bất kỳ có khả năng re-acquire cùng StampedLock.

## 9. Condition không được hỗ trợ

`Lock.newCondition()` có trong interface, nhưng **cả read view và write view** của StampedLock đều không hỗ trợ một `Condition`. Khi gọi, nó ném:

```java
UnsupportedOperationException
```

Ví dụ có thể tự chạy trong method:

```java
ReadWriteLock rw = new StampedLock().asReadWriteLock();

try {
    rw.writeLock().newCondition();
} catch (UnsupportedOperationException expected) {
    System.out.println("not supported");
}
```

Trong `ReentrantReadWriteLock`, **write lock** có thể hỗ trợ Condition, còn read lock không. Đây là một khác biệt khả năng rất quan trọng khi migrate code. Một thư viện chỉ thấy `ReadWriteLock` có thể tưởng write `newCondition()` được hỗ trợ do trước đó dùng `ReentrantReadWriteLock`; thay bằng StampedLock view sẽ lỗi runtime nếu nó gọi API này.

### 9.1. Dùng gì thay Condition?

- Nếu cần hàng đợi chờ dữ liệu, cân nhắc `BlockingQueue`.
- Nếu cần một cờ/phase hoàn tất, cân nhắc `CountDownLatch`, `Phaser` hoặc `CompletableFuture` tùy workflow.
- Nếu cần condition gắn sát với một reentrant lock, cân nhắc `ReentrantLock` hoặc `ReentrantReadWriteLock.WriteLock` nếu đáp ứng yêu cầu.
- Nếu chỉ cần read/write state với scope ngắn, có thể không cần Condition.

Không dùng `Object.wait()`/`notify()` trực tiếp với StampedLock view như thể nó là monitor của `synchronized`. `Lock` và `Condition` có hợp đồng riêng, và không thể “tạo Condition bằng cast” từ adapter không hỗ trợ.

### 9.2. Kiểm tra khả năng theo implementation, không theo tên interface

Java cho phép một `Lock` implementation không hỗ trợ `newCondition`; phương thức đó được phép ném `UnsupportedOperationException`. Vì vậy khi thư viện nhận một Lock/ReadWriteLock từ ngoài, phải xác định **yêu cầu về khả năng**: chỉ cần lock/unlock, cần timeout, cần interruption, hay cần Condition?

Một interface chung giúp liên thông cú pháp, không bảo đảm mọi optional behavior giống nhau.

## 10. tryLock: kiểu boolean và đường đi thất bại phải rõ

`Lock.tryLock()` trả:

- `true`: acquisition thành công; **caller có trách nhiệm unlock**.
- `false`: không lấy được khóa ngay; **không được unlock**.

Mẫu đúng:

```java
Lock read = view.readLock();

if (!read.tryLock()) {
    return Optional.empty();
}
try {
    return Optional.of(new Snapshot(left, right));
} finally {
    read.unlock();
}
```

Đây là đoạn trong một method trả `Optional<Snapshot>`, có fields và record cần thiết. `return` khi không lấy được khóa nằm **ngoài** `try/finally`. Với view, không có khái niệm **stamp=0L** trong caller; biến điều khiển là boolean.

Sai:

```java
Lock read = view.readLock();
boolean acquired = read.tryLock();
try {
    return inspectState(); // Có thể đọc khi chưa có khóa.
} finally {
    read.unlock();         // Có thể unlock dù acquired=false.
}
```

Đây là **anti-pattern**. Nếu `tryLock` thất bại, code vẫn truy cập protected state và gọi `unlock` không tương ứng. Đừng bỏ qua boolean return.

### 10.1. Không dùng tryLock làm cơ chế fairness

`StampedLock` không cam kết reader/writer FIFO; các try-method best effort. Một lần `tryLock` trả false không chứng minh hệ thống bị deadlock, cũng không xác nhận số threads đang chờ. Nó chỉ nói lần acquisition hiện tại không thành công theo điều kiện/implementation.

Nếu không lấy được khóa, bạn cần định nghĩa policy rõ: trả “busy”, retry có giới hạn, dùng timed tryLock, ghi metrics hoặc chuyển sang luồng xử lý khác. Không spin vô hạn với `while(!tryLock()) {}` vì gây hao CPU và có thể làm tình trạng contention tệ hơn.

### 10.2. Khi thử lấy khóa, tránh phát sinh hai lần unlock

Sai:

```java
if (write.tryLock()) {
    try {
        mutate();
        write.unlock(); // Sai: đã unlock trong thân.
    } finally {
        write.unlock(); // Unlock lần hai.
    }
}
```

Mẫu đúng là **chỉ một lần unlock trong finally**, ngay cả khi body có nhiều nhánh return/catch.

## 11. tryLock(timeout, unit) và interruption

Dạng timed API của `Lock`:

```java
boolean acquired = read.tryLock(200, TimeUnit.MILLISECONDS);
```

- Có thể **chờ tối đa** thời hạn theo API.
- Trả `true` nếu lấy được, `false` nếu không lấy được trước thời hạn.
- Có thể ném `InterruptedException` khi thread bị interrupt trong lúc chờ (và tùy trạng thái khi gọi).
- Chỉ được làm protected work và `unlock()` nếu `acquired==true`.

Mẫu:

```java
boolean acquired = write.tryLock(200, TimeUnit.MILLISECONDS);
if (!acquired) {
    return false;
}
try {
    updateState();
    return true;
} finally {
    write.unlock();
}
```

Snippet này ở trong method `throws InterruptedException` và có `write`/`updateState` đã khai báo.

### 11.1. Nếu bị interrupt trước acquisition

Nếu `tryLock(time,unit)` hoặc `lockInterruptibly()` ném `InterruptedException` **trước khi lấy khóa**, caller **không được unlock** như thể đã có acquisition. Thông thường nên propagate interrupt lên tầng điều phối. Nếu bắt và không rethrow, thường cần `Thread.currentThread().interrupt()` theo policy ứng dụng.

Đừng catch `InterruptedException` rồi tự tạo trạng thái “khóa đã lấy thành công”. Đây là lỗi quyền truy cập rất khó truy vết.

### 11.2. Timed acquisition không phải timeout cho cả critical section

Một thread có thể lấy được khóa trong 50 ms nhưng giữ khóa thêm 10 giây để chạy logic. `tryLock(200ms)` chỉ giới hạn **thời gian chờ acquisition**, không tự dừng code sau khi khóa đã được cấp.

Nếu operation có deadline tổng, phải tự thiết kế thời gian xử lý, tránh gọi IO/network blocking chậm khi giữ write view.

## 12. lockInterruptibly: cho phép hủy việc chờ

`Lock.lockInterruptibly()` cố lấy khóa và phản ứng với interrupt:

```java
Lock read = view.readLock();

read.lockInterruptibly(); // Throws InterruptedException.
try {
    return readProtectedData();
} finally {
    read.unlock();
}
```

Đây là snippet trong một method `throws InterruptedException`, và `readProtectedData` được định nghĩa trong class.

Điểm quan trọng:

- Nếu acquisition thành công, body được chạy và finally unlock.
- Nếu bị interrupt **trong lúc chờ**, method có thể ném InterruptedException; vì nó nằm trước try, không unlock khi chưa có khóa.
- Nếu thread bị interrupt **sau khi đã có khóa**, việc giải phóng vẫn là trách nhiệm của finally; Java không tự đóng Lock view khi thread bị interrupt.

### 12.1. Test không cần sleep

Để kiểm tra interrupt một reader đang chờ:

1. Thread chính lấy write view trước.
2. Spawn thread phụ, thread này gọi `read.lockInterruptibly()`.
3. Dùng `CountDownLatch` để biết thread phụ đã bắt đầu thử.
4. Interrupt thread phụ trước khi thread chính thả write.
5. `join` thread phụ có timeout.
6. Assert thread phụ bị interrupt và **chưa acquire read lock**.
7. Thread chính unlock write trong finally.

Chương trình đầy đủ ở mục 16 thực hiện đúng test này. Không dùng `Thread.sleep(100)` để suy đoán reader có đang chờ hay chưa; nó dễ flaky trên CI.

### 12.2. Khác với lock() không interruptible

`Lock.lock()` không có cùng hợp đồng phản ứng với interrupt như `lockInterruptibly()`. Nếu workflow đòi dễ hủy, dùng đúng phương thức interruptible hoặc timed. Cẩn thận: interrupt của Java là tín hiệu hợp tác, không có nghĩa một task IO bên ngoài đã được hủy hoàn toàn.

## 13. Không có notion of ownership theo thread

Javadoc `StampedLock` nêu rõ **không theo dõi owner thread** theo cách nhiều implementation khóa thông thường thực hiện: khóa lấy trong một thread **có thể được giải phóng hoặc convert từ thread khác**, miễn protocol/stamp hợp lệ. Đặc tính này vẫn cần được tính đến khi dùng view.

Nói khác đi, `ReadWriteLock` view **không đột nhiên trở thành ReentrantReadWriteLock có per-thread hold count**. Không suy luận:

- “Java interface `Lock` bảo đảm chỉ thread đã lock mới được unlock.”
- “Thread hiện tại đã giữ write view thì gọi write view lock lần nữa chắc chắn thành công.”
- “Nếu thread hiện tại chưa từng lấy read view, `unlock()` chắc chắn được kiểm tra theo owner thread như ReentrantLock.”

**Khuyến nghị production:** Dù StampedLock có thể hỗ trợ chuyển quyền giữa threads, hãy giữ **một acquisition và release trong cùng lexical scope và cùng luồng** khi không có yêu cầu đặc biệt. Điều này dễ review, test, debug và tránh vô tình giải phóng quyền truy cập của người khác.

### 13.1. Không dùng lack of ownership để “cứu” một lỗi lifecycle

Không nên viết một thread watchdog gọi `view.writeLock().unlock()` khi thấy hệ thống chậm để cố giải phóng khóa của một tác vụ khác. Nó không biết tác vụ sở hữu đã cập nhật state xong chưa và có thể phá bất biến.

Nếu một task có thể treo lâu, thiết kế cancellable operation và critical section ngắn ngay từ đầu; không dùng “unlock từ thread khác” như một cơ chế timeout tổng quát.

### 13.2. Không trả Lock view cho code bên ngoài thiếu kiểm soát

Nếu class domain trả `ReadWriteLock` để plugin ngoài tự gọi lock/unlock, nó mở rộng quyền thao tác đồng bộ ra ngoài component. Một caller có lỗi có thể giữ khóa lâu, unlock sai hoặc phá protocol.

Ưu tiên API đóng gói `snapshot()`, `update(...)`, `withReadLock(...)`/`withWriteLock(...)` với giới hạn quyền và scope rõ nếu thực sự cần callback. Với callback từ bên ngoài, vẫn cân nhắc rủi ro reentrancy và exception.

## 14. Khác biệt quan trọng so với ReentrantReadWriteLock

`ReentrantReadWriteLock` và StampedLock view đều cung cấp kiểu `ReadWriteLock`, nhưng hành vi khác ở nhiều điểm:

| Thuộc tính | `new ReentrantReadWriteLock()` | `new StampedLock().asReadWriteLock()` |
| --- | --- | --- |
| Kiểu dùng ngoài | `ReadWriteLock` | `ReadWriteLock` |
| Nhiều reader đồng thời | Có | Có |
| Một writer độc quyền | Có | Có |
| Reentrant write | **Có** | **Không** |
| Reentrant read | Có theo quy tắc implementation | **Không bảo đảm reentrancy** |
| Writer đang giữ write rồi acquire read | Có thể cho phép downgrading theo quy tắc | **Không** theo kiểu reentrant |
| Condition trên write lock | **Có** | **Không** |
| Condition trên read lock | Không | Không |
| Fairness tùy chọn | Có constructor fairness | Không có fairness guarantee tương đương |
| Track ownership theo thread | Có | Không theo StampedLock |
| Có direct optimistic read API | Không | StampedLock gốc có, nhưng **view không phơi ra** |
| Có raw stamp để convert | Không | StampedLock gốc có, nhưng **view không trả stamp** |
| Timeouts/interruptible Lock methods | Có | Có |

### 14.1. Khi nào có thể thay ReentrantReadWriteLock bằng view?

Có thể cân nhắc nếu code:

- Chỉ sử dụng `readLock().lock()/unlock()`, `writeLock().lock()/unlock()`.
- Không nested acquisition dựa vào reentrancy.
- Không cần `newCondition()`.
- Không dựa vào per-thread ownership/hold counts.
- Không đòi fairness cụ thể.
- Có benchmark cho workload thực tế và lợi ích đủ bù chi phí hiểu đặc tính mới.

**Không thay máy móc** chỉ vì cùng interface. Đặc biệt, một method outer giữ write rồi gọi inner tự lấy read/write có thể đang hợp lệ với ReentrantReadWriteLock nhưng tự deadlock với StampedLock view.

### 14.2. Tại sao docs của ReentrantReadWriteLock nhắc StampedLock?

Javadoc `ReentrantReadWriteLock` gợi ý `StampedLock.asReadWriteLock()` có thể mang lợi ích hiệu năng trong trường hợp **không phụ thuộc reentrancy**. Đây không phải cam kết view luôn nhanh hơn; concurrency benchmark phải phản ánh tỷ lệ read/write, thời gian giữ khóa và contention thật.

### 14.3. Nếu cần Condition hoặc sở hữu theo thread

Hãy chọn implementation đáp ứng nhu cầu ấy. `ReentrantLock` hoặc `ReentrantReadWriteLock` có thể thích hợp hơn nếu code cần các cơ chế đó. Đổi lock phải đi kèm xem lại các assumptions về fairness, interruption, reentrancy, upgrade/downgrade và trạng thái mutable.

## 15. Test contract: tập trung vào thuộc tính được hứa

Bài toán concurrency dễ có test flaky nếu dựa vào thứ tự scheduler hoặc thời gian ngủ. Với view ReadWriteLock, nên kiểm tra:

| Tình huống | Setup | Kỳ vọng |
| --- | --- | --- |
| Writer cập nhật | `write.lock()`, sửa hai field | Snapshot sau đó có hai field mới |
| Reader đọc nhất quán | `read.lock()`, đọc cặp state | Không thấy writer xen giữa khi cùng protocol |
| Hai reader đồng thời | Hai tasks giữ read view bằng latch | Hai readers cùng giữ lock được |
| Writer khi có readers | Khi hai readers chưa thả | `write.tryLock()==false` |
| Raw StampedLock khi view read | `stamped.tryWriteLock()` | `0L` — cùng underlying state |
| Reader khi view write giữ | `read.tryLock()` | false |
| Direct read view khi combined write giữ | `stamped.asReadLock().tryLock()` | false |
| Timed tryLock khi write giữ | `read.tryLock(time,unit)` | false khi hết hạn |
| Interruptible acquisition | Thread đang chờ read, bị interrupt | `InterruptedException`, không acquire |
| `newCondition()` của read view | Gọi trực tiếp | `UnsupportedOperationException` |
| `newCondition()` của write view | Gọi trực tiếp | `UnsupportedOperationException` |
| Lấy write hai lần | Giữ write rồi `write.tryLock()` | false, không reentrant |
| Read khi giữ write | Giữ write rồi `read.tryLock()` | false |
| Double unlock write | Lock → unlock → unlock tiếp | Bị từ chối bằng exception |
| Release sau readers | Readers thả, write lại | Writer lấy được |
| Shutdown executor | Các task hoàn tất | Pool dừng, không còn reader treo |

### 15.1. Dùng latch thay vì sleep

`CountDownLatch` giúp test kiểm soát đúng mốc “reader đã acquire”. Thread reader gọi `ready.countDown()` **sau khi read.lock() thành công**, chứ không phải ngay khi tạo task.

Thread main đợi `ready.await()` rồi thử `write.tryLock()`. Nó không phải “có xác suất reader kịp chạy trong 50 ms”, mà là **đã có bảo đảm xác nhận hai acquisition trước khi thử writer**.

### 15.2. Không assert thứ tự hai reader

Cả hai read tasks có thể được scheduler chạy theo thứ tự bất kỳ. Test không cần assert reader A đến trước B; chỉ assert **cả hai cùng có thể giữ read lock** và write tryLock thất bại khi cả hai chưa release.

### 15.3. Condition và double unlock test phải bắt đúng loại lỗi

Không so sánh chuỗi exception message vì chúng có thể khác theo phiên bản/JVM. Test kiểm tra:

- `UnsupportedOperationException` cho `newCondition()`.
- `IllegalMonitorStateException` cho unlock không phù hợp trong fixture.
- `InterruptedException` cho lockInterruptibly bị hủy trong lúc chờ.

Đừng nuốt mọi `Exception` rồi coi đó là pass; một NullPointerException hoặc AssertionError không liên quan không phải kết quả kỳ vọng.

## 16. Ví dụ Java 17+ hoàn chỉnh: ReadWriteLock view và hợp đồng khóa

Chương trình sau dùng **một StampedLock duy nhất**, expose một `ReadWriteLock` view và minh họa các behavior cần nhớ. Nó không tạo file bên ngoài hay gọi network; output được quyết định bởi việc kiểm soát thứ tự bằng latch, không phụ thuộc thread nào chạy trước.

Tạo file **`ReadWriteLockViewDemo.java`**:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;

public class ReadWriteLockViewDemo {
    record Snapshot(int left, int right) {}

    static final class Ledger {
        final StampedLock stamped = new StampedLock();
        final ReadWriteLock view = stamped.asReadWriteLock();

        private int left, right;

        void add(int delta) {
            Lock write = view.writeLock();
            write.lock();
            try {
                left += delta;
                right += delta;
            } finally {
                write.unlock();
            }
        }

        Snapshot snapshot() {
            Lock read = view.readLock();
            read.lock();
            try {
                return new Snapshot(left, right);
            } finally {
                read.unlock();
            }
        }
    }

    static void check(boolean ok, String what) {
        if (!ok) {
            throw new AssertionError(what);
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

    static void sharedRead(
            Lock read,
            CountDownLatch ready,
            CountDownLatch release) {
        read.lock();
        try {
            ready.countDown();
            await(release);
        } finally {
            read.unlock();
        }
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();
        ledger.add(3);
        System.out.println("initial=" + ledger.snapshot());

        Lock read = ledger.view.readLock();
        Lock write = ledger.view.writeLock();

        // Condition không được hỗ trợ trên CẢ HAI view.
        boolean readConditionUnsupported = false;
        boolean writeConditionUnsupported = false;
        try {
            read.newCondition();
        } catch (UnsupportedOperationException error) {
            readConditionUnsupported = true;
        }
        try {
            write.newCondition();
        } catch (UnsupportedOperationException error) {
            writeConditionUnsupported = true;
        }
        check(readConditionUnsupported && writeConditionUnsupported,
                "conditions unavailable");
        System.out.println("readConditionUnsupported="
                + readConditionUnsupported);
        System.out.println("writeConditionUnsupported="
                + writeConditionUnsupported);

        // Hai read view được giữ trên hai threads cùng lúc.
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        try {
            CompletableFuture<Void> ra =
                    CompletableFuture.runAsync(
                            () -> sharedRead(read, ready, release),
                            pool);
            CompletableFuture<Void> rb =
                    CompletableFuture.runAsync(
                            () -> sharedRead(read, ready, release),
                            pool);

            await(ready);
            System.out.println("twoConcurrentReaders="
                    + (ledger.stamped.getReadLockCount() == 2));

            boolean blocked = !write.tryLock();
            check(blocked, "writer not allowed when readers active");
            System.out.println("writerBlockedByViewReaders=" + blocked);

            long rawWrite = ledger.stamped.tryWriteLock();
            check(rawWrite == 0L, "raw write shares state");
            System.out.println("rawWriterBlockedByViewReaders="
                    + (rawWrite == 0L));

            release.countDown();
            CompletableFuture.allOf(ra, rb).join();
        } finally {
            release.countDown();
            pool.shutdown();
            check(pool.awaitTermination(
                    5, TimeUnit.SECONDS), "reader pool shutdown");
        }

        ledger.add(2);
        System.out.println("afterReaders=" + ledger.snapshot());

        // View write đang giữ; các nested acquisition bị từ chối.
        write.lock();
        try {
            boolean nestedWriteRejected = !write.tryLock();
            boolean nestedReadRejected = !read.tryLock();
            boolean directReadRejected =
                    !ledger.stamped.asReadLock().tryLock();
            boolean timedReadRejected =
                    !read.tryLock(10, TimeUnit.MILLISECONDS);

            check(nestedWriteRejected && nestedReadRejected
                    && directReadRejected && timedReadRejected,
                    "exclusive");

            System.out.println("writeViewHeld="
                    + ledger.stamped.isWriteLocked());
            System.out.println("secondWriteTryRejected="
                    + nestedWriteRejected);
            System.out.println("readTryRejectedByViewWriter="
                    + nestedReadRejected);
            System.out.println("directReadTryRejectedByViewWriter="
                    + directReadRejected);
            System.out.println("timedReadTryRejected="
                    + timedReadRejected);

            // Thread phụ chờ read lock rồi bị interrupt.
            CountDownLatch started = new CountDownLatch(1);
            AtomicBoolean interrupted = new AtomicBoolean(false);
            AtomicBoolean acquired = new AtomicBoolean(false);
            AtomicReference<Throwable> failure =
                    new AtomicReference<>();

            Thread waiter = new Thread(() -> {
                started.countDown();
                try {
                    read.lockInterruptibly();
                    acquired.set(true);
                    try {
                        // Giả sử đọc dữ liệu được bảo vệ.
                    } finally {
                        read.unlock();
                    }
                } catch (InterruptedException error) {
                    interrupted.set(true);
                } catch (Throwable error) {
                    failure.set(error);
                }
            }, "interruptible-view-waiter");

            waiter.start();
            await(started);
            waiter.interrupt();
            waiter.join(5_000);

            check(!waiter.isAlive()
                    && interrupted.get()
                    && !acquired.get()
                    && failure.get() == null,
                    "interruptible read");

            System.out.println("interruptibleReadInterrupted="
                    + interrupted.get());
            System.out.println("interruptibleReadNeverAcquired="
                    + !acquired.get());
        } finally {
            write.unlock();
        }

        // Direct view và combined view dùng cùng underlying lock.
        read.lock();
        try {
            boolean directWriteRejected =
                    !ledger.stamped.asWriteLock().tryLock();
            check(directWriteRejected, "direct write shares lock");
            System.out.println("directWriterBlockedByViewReader="
                    + directWriteRejected);
        } finally {
            read.unlock();
        }

        boolean adapterWriteAcquired =
                ledger.stamped.asWriteLock().tryLock();
        check(adapterWriteAcquired,
                "adapter write acquired after release");
        try {
            System.out.println("directWriteAfterRelease="
                    + adapterWriteAcquired);
        } finally {
            ledger.stamped.asWriteLock().unlock();
        }

        // Không thể unlock một write view khi không còn khóa.
        write.lock();
        write.unlock();
        boolean doubleUnlockRejected = false;
        try {
            write.unlock();
        } catch (IllegalMonitorStateException error) {
            doubleUnlockRejected = true;
        }
        check(doubleUnlockRejected, "double unlock");
        System.out.println("doubleUnlockRejected="
                + doubleUnlockRejected);

        System.out.println("final=" + ledger.snapshot());
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac ReadWriteLockViewDemo.java
java ReadWriteLockViewDemo
```

**Stdout chính xác khi kiểm thử với JDK hiện đại:**

```text
initial=Snapshot[left=3, right=3]
readConditionUnsupported=true
writeConditionUnsupported=true
twoConcurrentReaders=true
writerBlockedByViewReaders=true
rawWriterBlockedByViewReaders=true
afterReaders=Snapshot[left=5, right=5]
writeViewHeld=true
secondWriteTryRejected=true
readTryRejectedByViewWriter=true
directReadTryRejectedByViewWriter=true
timedReadTryRejected=true
interruptibleReadInterrupted=true
interruptibleReadNeverAcquired=true
directWriterBlockedByViewReader=true
directWriteAfterRelease=true
doubleUnlockRejected=true
final=Snapshot[left=5, right=5]
ALL CHECKS PASSED
```

### 16.1. Giải thích phần dữ liệu

`ledger.add(3)` lấy write view để tăng cả hai field thành 3. `snapshot()` lấy read view và trả immutable record. Cả hai method dùng **cùng một StampedLock**, nên cặp dữ liệu được bảo vệ phù hợp.

Sau khi hai read tasks hoàn tất, `ledger.add(2)` cập nhật thành 5. Các output `initial` và `afterReaders`/`final` phản ánh trạng thái đã ổn định ở những điểm không còn writer xen vào.

### 16.2. Giải thích phần Condition

`read.newCondition()` và `write.newCondition()` đều ném `UnsupportedOperationException`. Test kiểm tra riêng từng ngoại lệ, không dùng `catch(Exception)` bao trùm.

Không hiểu nhầm “write lock” trong interface có nghĩa nó hỗ trợ Condition như ReentrantReadWriteLock.WriteLock.

### 16.3. Giải thích phần hai reader đồng thời

Hai thread đều gọi `read.lock()` và báo `ready.countDown()` sau khi acquire. Thread chính chỉ tiếp tục khi cả hai đã acquire, nên `getReadLockCount()==2` trong fixture. Khi ấy `write.tryLock()` trả false và raw `stamped.tryWriteLock()` trả 0, cho thấy các view chia sẻ underlying state.

`getReadLockCount` chỉ được dùng làm quan sát trong test, không làm điều kiện production để quyết định quyền truy cập khóa.

### 16.4. Giải thích phần exclusive writer và non-reentrancy

Trong lúc view write đang giữ, việc thử write lần nữa, thử read view, thử direct read view và timed try read đều thất bại. Đây là đặc tính **non-reentrant**, không phải một writer có quyền tự động đọc/ghi lại.

Test dùng `tryLock` để trả về nhanh thay vì gọi `lock()` có nguy cơ tự chặn.

### 16.5. Giải thích phần interruptible

Thread phụ gọi `read.lockInterruptibly()` khi main vẫn giữ write view. Main gửi interrupt; thread phụ nhận `InterruptedException` và không từng lấy read lock. Nó không gọi `read.unlock()` trên acquisition thất bại.

Ngay cả khi thread phụ bị interrupt, main vẫn phải `write.unlock()` trong finally để không giữ write view mãi.

### 16.6. Giải thích các view chia sẻ state

Khi combined read view giữ read lock, `stamped.asWriteLock().tryLock()` cũng thất bại. Sau release, direct write view lấy khóa được. Đây là ví dụ từ hai API bề ngoài khác nhau nhưng cùng StampedLock.

### 16.7. Giải thích double unlock

Sau `write.lock(); write.unlock();`, một `write.unlock()` nữa khi không còn write hold hợp lệ bị từ chối bằng `IllegalMonitorStateException`. Không dùng exception message để assert.

## 17. Nếu một thư viện đòi ReadWriteLock, hãy kiểm tra những giả định ẩn

Giả sử bạn có interface repository nhận khóa từ caller:

```java
final class Repository {
    private final ReadWriteLock lock;

    Repository(ReadWriteLock lock) {
        this.lock = Objects.requireNonNull(lock);
    }

    void update() {
        Lock write = lock.writeLock();
        write.lock();
        try {
            // Thay đổi state đã được khai báo ở class.
        } finally {
            write.unlock();
        }
    }
}
```

Đây là snippet minh họa trong một class, với `import java.util.Objects;` và `java.util.concurrent.locks.*;`. Nó dùng những thao tác phổ biến trên interface, nhưng để thật sự **cắm StampedLock view**, hãy tự hỏi:

- Có method nào gọi `update()` khi một outer method đã giữ write lock không?
- Có callback/observer nào được gọi dưới lock và lại gọi method của Repository không?
- Có method nào tạo `Condition` từ `lock.writeLock()`?
- Có code giả định `lock.writeLock()` hỗ trợ reentrant hold count hoặc owner-thread debugging không?
- Có được phép thay implementation nếu yêu cầu fairness chưa được nói rõ?
- Có cần đổi read → write mà không thả read mode không?

Nếu bất kỳ câu trả lời nào dựa vào **reentrant, Condition hoặc ownership**, cần xem xét lại trước khi thay.

### 17.1. Không đẩy nguyên ReadWriteLock ra ngoài nếu chỉ cần vài thao tác

Một class exposing:

```java
public ReadWriteLock getLock() {
    return view;
}
```

trao cho caller khả năng tự acquire/release. Điều này có thể hữu ích trong một internal API đã được kiểm soát chặt, nhưng thường tăng coupling và rủi ro caller giữ lock quá lâu hoặc unlock sai.

Với domain state cần bảo vệ, thường an toàn hơn khi expose **hành vi**:

```java
Snapshot snapshot();
void update(Command command);
```

Đoạn này là chữ ký minh họa, cần `Snapshot` và `Command` do domain định nghĩa. Class giữ quyền quản lý lock lifecycle bên trong.

## 18. Các tình huống timeout, contention và hiệu năng

### 18.1. Tránh IO chậm khi đang giữ write view

Không làm:

```java
write.lock();
try {
    callRemoteApi(); // Có thể chặn nhiều giây.
    updateState();
} finally {
    write.unlock();
}
```

Nếu remote call chậm, mọi reader/writer dùng cùng StampedLock có thể phải đợi. Nếu callback từ remote API lại cần lock, còn có nguy cơ deadlock.

Thay vào đó:

1. Chuẩn bị input ngoài lock.
2. Gọi IO ngoài lock khi phù hợp.
3. Acquire write view.
4. **Recheck** điều kiện/state/version, vì dữ liệu có thể đổi từ lúc bắt đầu IO.
5. Commit ngắn trong protected region, finally unlock.

Không phải mọi tác vụ đều có thể tách IO như vậy; cần xác định đúng invariants và transaction boundaries.

### 18.2. Không spin vô hạn với tryLock

Một vòng:

```java
while (!write.tryLock()) {
    // Busy spin vô hạn.
}
```

có thể tiêu tốn CPU dưới contention và làm khó dự đoán độ trễ. Dùng `lock()` khi có thể chờ theo cơ chế khóa; dùng `lockInterruptibly` hoặc timed `tryLock` khi cần hủy/deadline. Nếu retry, thêm giới hạn và policy rõ, không dựa vào yield/sleep như bảo đảm fairness.

### 18.3. Benchmark trước khi chọn view vì tốc độ

Chi phí StampedLock phụ thuộc tỷ lệ read/write, độ dài critical sections, số thread, phân phối dữ liệu và JVM. Chỉ vì `StampedLock` có optimistic mode không có nghĩa **view ReadWriteLock** tự tận dụng optimistic reads: view chỉ exposes **khóa đọc/ghi thông thường**.

Nếu cần test throughput:

- Dùng JMH thay vì đo thủ công một vòng lặp nhỏ.
- Mô phỏng contention, tỷ lệ đọc/ghi và workloads thực.
- Kiểm tra correctness trước latency.
- So sánh với `synchronized` và `ReentrantReadWriteLock` bằng điều kiện cùng cơ sở.
- Xem chi phí maintainability; một API dễ dùng sai có thể đắt hơn lợi ích nhỏ về performance.

### 18.4. Fairness và starvation

StampedLock **không cam kết ưu tiên nhất quán reader hay writer**. Một cuộc đua trong test có thể “thường writer thắng” trên một JVM nhưng đó không phải contract.

Nếu hệ thống cần fairness/FIFO hoặc có SLA chặt về starvation, lựa chọn lock phải dựa vào hợp đồng chính thức, không dựa vào quan sát từ một máy.

## 19. Các lỗi phổ biến và cách sửa

### Lỗi 1. Nghĩ ReadWriteLock view biến StampedLock thành ReentrantReadWriteLock

**Sai:** cùng interface nhưng khác reentrancy, ownership, fairness và Condition. **Sửa:** đọc contract implementation và rà soát nested acquisitions.

### Lỗi 2. Nghĩ asReadWriteLock tạo một lock mới độc lập

**Sai:** view phối hợp qua cùng StampedLock gốc. **Sửa:** kiểm thử xung đột giữa direct views, combined views và raw operations khi cần tích hợp.

### Lỗi 3. Gọi `write.lock()` hai lần vì cùng thread

**Sai:** non-reentrant, có thể tự deadlock. **Sửa:** giữ critical section một tầng, tách method under-lock không acquire lại.

### Lỗi 4. Gọi `read.lock()` khi đang giữ write view để làm downgrade

**Sai:** không có writer-to-read reentrancy như ReentrantReadWriteLock. **Sửa:** thiết kế raw conversion riêng hoặc release/reacquire và recheck.

### Lỗi 5. Đọc dưới read view rồi gọi write view khi chưa unlock

**Sai:** không tự nâng read → write qua interface. **Sửa:** thả read, lấy write, xác thực lại state; hoặc dùng raw stamp conversion trong flow riêng.

### Lỗi 6. Gọi `write.newCondition()` vì có phương thức đó trên Lock

**Sai:** StampedLock views không hỗ trợ Condition. **Sửa:** dùng implementation hỗ trợ Condition hoặc chọn primitive phối hợp phù hợp.

### Lỗi 7. Tưởng `Lock` luôn track thread sở hữu

**Sai:** Lock interface không bắt mọi implementation có cùng ownership semantics; StampedLock không theo dõi owner thread. **Sửa:** không dựa vào per-thread hold count hoặc caller ownership của ReentrantLock.

### Lỗi 8. Quên `unlock()` khi body ném exception

**Sai:** gây rò rỉ khóa/đợi vô hạn. **Sửa:** acquisition trước `try`, một lần unlock trong `finally`.

### Lỗi 9. `tryLock()` trả false nhưng code vẫn đọc/ghi protected state

**Sai:** không lấy được khóa. **Sửa:** chỉ vào critical section khi boolean true; không gọi unlock nếu false.

### Lỗi 10. Gọi unlock hai lần

**Sai:** không có acquisition tương ứng cho lần thứ hai. **Sửa:** chỉ unlock tại finally, không unlock thêm trong thân try.

### Lỗi 11. Dùng raw `unlockRead(stamp)` sau khi acquire bằng view

**Sai:** view không trả stamp của acquisition. **Sửa:** giữ cùng abstraction trong một critical section: view `lock()/unlock()` hoặc raw stamp acquire/unlock riêng.

### Lỗi 12. Dùng `validate(stamp)` như khả năng của ReadWriteLock

**Sai:** interface không có optimistic mode/stamp. **Sửa:** nếu cần optimistic read, làm việc với StampedLock gốc trong một flow được kiểm soát.

### Lỗi 13. Nuốt InterruptedException rồi tiếp tục như đã lấy được lock

**Sai:** code có thể truy cập state không bảo vệ. **Sửa:** kiểm soát acquisition result, propagate/restore interruption theo policy.

### Lỗi 14. Timed tryLock thất bại nhưng finally vẫn unlock

**Sai:** false nghĩa là không có hold hợp lệ. **Sửa:** chỉ unlock khi acquired==true.

### Lỗi 15. Cho rằng timeout acquisition là timeout cả operation

**Sai:** callback trong critical section có thể chạy vô hạn sau khi đã lấy khóa. **Sửa:** tách IO/logic chậm và quản lý deadline tổng.

### Lỗi 16. Bọc read-only work trong write view

Không nhất thiết sai về mutual exclusion nhưng giảm concurrency, khiến nhiều reader phải chờ nhau. **Sửa:** dùng read view cho các phần đọc side-effect-free khi invariant cho phép.

### Lỗi 17. Sửa state trong read view

**Sai:** nhiều reader có thể cùng cập nhật, gây race. **Sửa:** dùng write view cho mutation.

### Lỗi 18. Đưa reference mutable ra ngoài sau khi unlock read

**Sai:** caller có thể truy cập dữ liệu đã đổi không được bảo vệ. **Sửa:** immutable snapshot/defensive copy trong vùng bảo vệ.

### Lỗi 19. Lock đúng nhưng writer khác bỏ qua lock

**Sai:** không còn shared protocol. **Sửa:** encapsulate state, review mọi write path và direct/raw access.

### Lỗi 20. Phụ thuộc thứ tự reader/writer được xếp lịch

**Sai:** StampedLock không cam kết fairness nhất quán. **Sửa:** dùng latch để test các điều kiện chắc chắn, tránh suy luận FIFO từ một kết quả chạy.

### Lỗi 21. Sử dụng `isWriteLocked` hoặc `getReadLockCount` như điều kiện điều khiển truy cập

**Sai:** chúng là dữ liệu quan sát có thể thay đổi ngay sau khi đọc. **Sửa:** dựa vào các thao tác `lock/tryLock` thực sự để bảo vệ state.

### Lỗi 22. Dùng view để giải quyết transaction nhiều field mà không kiểm soát exception giữa mutation

`finally` chỉ release, không rollback. **Sửa:** validate trước commit hoặc có protocol rollback.

### Lỗi 23. Cố “cứu” task bị treo bằng unlock từ thread khác

StampedLock thiếu ownership theo thread không đồng nghĩa unlock hộ là phương pháp an toàn. **Sửa:** design timeout, critical-section boundaries và cancellation rõ.

### Lỗi 24. Dùng StampedLock view cho mọi workload vì nghĩ luôn nhanh hơn

Không có đảm bảo hiệu năng tổng quát. **Sửa:** benchmark và so sánh semantics trước khi quyết định.

### Lỗi 25. Tạo hai StampedLock riêng cho cùng một invariant

Hai views từ **hai StampedLock khác nhau** không phối hợp được với nhau. **Sửa:** xác định ownership của shared state và dùng một lock/protocol nhất quán cho các đường truy cập cần bảo vệ chung.

## 20. Bài tập thực hành và đáp án

**Bài 1.** `StampedLock.asReadWriteLock()` trả kiểu gì?

**Đáp án:** Trả `ReadWriteLock`, có hai `Lock` lấy qua `readLock()` và `writeLock()`, cùng dựa trên một StampedLock gốc.

**Bài 2.** `StampedLock.asReadLock()` trả kiểu gì, khác với `StampedLock.readLock()` ra sao?

**Đáp án:** `asReadLock()` trả `Lock` adapter; `readLock()` trên StampedLock gốc trả `long stamp` cho một acquisition. Hai API có cách mở khóa khác nhau.

**Bài 3.** `Lock.tryLock()` trả gì?

**Đáp án:** `boolean`: true nếu lấy được, false nếu không. Khác với raw `StampedLock.tryReadLock()` trả stamp hoặc 0L.

**Bài 4.** Hai reader giữ `rw.readLock()` có được cùng tồn tại không?

**Đáp án:** Có, read mode non-exclusive, miễn không có writer đang giữ exclusive mode và scheduling cho phép.

**Bài 5.** Nếu một reader giữ read view, `stamped.tryWriteLock()` có thể trả gì?

**Đáp án:** `0L` vì raw StampedLock và view dùng cùng state; writer không thể được cấp khi read mode đang được giữ.

**Bài 6.** Một thread đã giữ write view rồi gọi lại `write.lock()` có chắc thành công không?

**Đáp án:** Không. StampedLock không reentrant và việc reacquire có thể tự block. Đừng áp suy luận từ ReentrantReadWriteLock.

**Bài 7.** Khi giữ write view, gọi `rw.readLock().tryLock()` có thể thành công chỉ vì cùng thread không?

**Đáp án:** Không. Write mode độc quyền của StampedLock không cho read acquisition mới chỉ vì caller là cùng thread.

**Bài 8.** Dùng ReadWriteLock view có lấy được optimistic stamp để validate không?

**Đáp án:** Không. `ReadWriteLock` chỉ expose read/write Lock. Nếu cần optimistic read, dùng StampedLock gốc theo flow raw stamp riêng.

**Bài 9.** Cả read view và write view có tạo Condition được không?

**Đáp án:** Không. `newCondition()` trên các views này ném `UnsupportedOperationException`.

**Bài 10.** Một thư viện trước đây dùng `ReentrantReadWriteLock.WriteLock.newCondition()`. Thay bằng StampedLock view có an toàn không?

**Đáp án:** Không nếu thư viện thực sự cần Condition. Phải giữ implementation có hỗ trợ hoặc đổi design phối hợp.

**Bài 11.** Vì sao `unlock()` cần đặt trong finally?

**Đáp án:** Để giải phóng khóa khi body return hoặc throw. Khác với monitor của `synchronized`, `Lock` cần release tường minh.

**Bài 12.** `read.tryLock()` trả false. Có nên `read.unlock()` trong finally không?

**Đáp án:** Không, vì chưa có acquisition thành công. Chỉ vào try/finally khi đã lấy khóa.

**Bài 13.** `read.tryLock(20,MILLISECONDS)` trả false nghĩa là gì?

**Đáp án:** Không lấy được khóa trước khi hết thời hạn theo operation đó; không cho phép đọc protected state hoặc gọi unlock cho lần thử thất bại.

**Bài 14.** `read.lockInterruptibly()` ném InterruptedException trước khi acquire; cuối cùng có nên unlock không?

**Đáp án:** Không. Cần propagate/handle interruption, không mở khóa một acquisition chưa thành công.

**Bài 15.** `Lock` interface có bắt mọi implementation phải reentrant và track owner-thread không?

**Đáp án:** Không. Những thuộc tính đó phải xét ở implementation; StampedLock view không có reentrancy và StampedLock không theo dõi owner thread.

**Bài 16.** `asReadWriteLock` có làm StampedLock trở thành fair lock không?

**Đáp án:** Không. Adapter không thêm chính sách FIFO/fairness không có trong StampedLock.

**Bài 17.** Một method write đang giữ khóa gọi method read cũng lấy read view, đây là pattern an toàn không?

**Đáp án:** Không. StampedLock view không reentrant; nested acquisition có nguy cơ tự chặn. Tách method nội bộ thực thi dưới lock đã được giữ.

**Bài 18.** Có thể giải phóng read view rồi lấy write view để upgrade không?

**Đáp án:** Có thể thực hiện hai bước nhưng **không atomic**. Sau khi lấy write, phải **kiểm tra lại điều kiện** vì thread khác có thể thay state trong khoảng trống.

**Bài 19.** Một task đọc dưới view rồi trả reference MutableList nội bộ. Caller có được bảo vệ sau khi method return không?

**Đáp án:** Không. Lock đã được release; dùng immutable snapshot hoặc defensive copy.

**Bài 20.** Có thể dùng `getReadLockCount()` để quyết định writer có thể ghi mà không gọi `write.lock()` không?

**Đáp án:** Không. Count có thể thay đổi và không phải một check-and-acquire atomic. Dùng acquire/tryLock theo contract.

**Bài 21.** Khi cần migration từ `ReentrantReadWriteLock` sang view, cần rà soát gì?

**Đáp án:** Reentrancy/nested calls, Condition, per-thread ownership/hold counts, fairness, upgrade/downgrade, interruption, timeout, cách release và mọi đường truy cập protected state.

**Bài 22.** Cùng một StampedLock cho hai direct views và một ReadWriteLock view có nghĩa mỗi view có trạng thái riêng không?

**Đáp án:** Không. Chúng là adapters vào cùng underlying state. Hai StampedLock instance khác nhau mới có trạng thái khóa độc lập.

## 21. Quy trình chọn và tích hợp adapter trong production

**Bước 1 — Xác định hợp đồng của dependency.** Thư viện nhận `ReadWriteLock`, `Lock` hay một loại `ReentrantReadWriteLock` cụ thể? Nó có thực sự cần Condition, reentrancy hoặc ownership không?

**Bước 2 — Chọn nguồn khóa duy nhất cho state.** Tạo `StampedLock stamped = new StampedLock()` trong object sở hữu dữ liệu. Giữ `ReadWriteLock view = stamped.asReadWriteLock()`, không tạo nhiều StampedLock cho cùng một invariant cần phối hợp.

**Bước 3 — Viết contract read/write rõ.** Các phương thức chỉ đọc dùng read view; mutation dùng write view. Tránh side effects/IO dài trong critical section khi có thể thiết kế an toàn hơn.

**Bước 4 — Bảo đảm một acquisition một release.** Dùng `lock(); try {...} finally { unlock(); }`. Với tryLock, chỉ vào protected region khi true. Với interruptible/timed, chỉ unlock sau acquisition thành công.

**Bước 5 — Kiểm tra nested call graph.** Không gọi method có khả năng lấy lại cùng StampedLock từ trong critical section. Đặc biệt tránh write → read, write → write và read → write kiểu reentrant.

**Bước 6 — Xác nhận không cần Condition.** Nếu cần `await/signal`, chọn một primitive khác có semantics đúng hoặc implementation lock có hỗ trợ.

**Bước 7 — Quy định nguồn interrupt/timeout.** Nếu cần phản ứng hủy, dùng `lockInterruptibly` hoặc timed `tryLock`; không giả định `lock()` đáp ứng deadline.

**Bước 8 — Không trộn raw stamp và view release.** Một protected region nên đi trọn flow view hoặc raw. Nếu cần optimistic read hoặc conversion, thiết kế flow riêng với StampedLock gốc và stamp được lưu đúng.

**Bước 9 — Kiểm thử theo contract chứ không theo lịch thread.** Dùng latch xác nhận reader đã acquire, test writer bị chặn, test Condition UnsupportedOperationException, test interruption và double unlock có kiểm soát.

**Bước 10 — Đo thực tế và tài liệu hóa giới hạn.** Thử hiệu năng dưới workload thực; ghi rõ non-reentrant/no Condition/no fairness/per-thread ownership để tránh regression khi code được bàn giao cho team khác.

## 22. Checklist production

- [ ] `asReadWriteLock()` chỉ là **view** của StampedLock, không tạo khóa độc lập.
- [ ] `asReadLock()` và `asWriteLock()` cũng sử dụng cùng underlying state.
- [ ] Biết `ReadWriteLock.readLock()/writeLock()` trả `Lock`, không trả `long stamp`.
- [ ] Mọi `Lock.lock()` thành công đi kèm đúng một `unlock()` trong `finally`.
- [ ] `tryLock() == false` đồng nghĩa **không có lock để unlock**.
- [ ] Với timed tryLock, chỉ unlock khi giá trị boolean true.
- [ ] Với `lockInterruptibly()`, không unlock nếu InterruptedException xảy ra trước acquisition.
- [ ] Đã kiểm tra không có nested acquisition dựa vào reentrancy.
- [ ] Không tự upgrade read → write bằng cách gọi write.lock() khi còn giữ read.
- [ ] Không tự downgrade write → read bằng cách acquire read view trong write section.
- [ ] Không gọi `newCondition()` trên StampedLock views; cả read và write view đều không hỗ trợ.
- [ ] Không giả định một `Lock` interface luôn có owner-thread hold count.
- [ ] Không dựa vào fairness/FIFO của StampedLock.
- [ ] Không dùng raw unlockRead(stamp) cho acquisition tạo bởi view.
- [ ] Nếu cần optimistic read/conversion, dùng raw stamped API theo protocol riêng.
- [ ] Tất cả read/write paths đến shared state đều tuân thủ cùng khóa.
- [ ] Snapshot trả khỏi read critical section là immutable/defensively copied khi cần.
- [ ] `finally` giải phóng khóa, nhưng exception trong mutation còn cần chiến lược giữ invariant/rollback.
- [ ] Không dùng `getReadLockCount/isWriteLocked` làm điều kiện truy cập thay cho acquire.
- [ ] Không giữ write view qua network/DB IO lâu không cần thiết.
- [ ] Có timeout/cancellation policy nếu ứng dụng không thể chờ lock vô hạn.
- [ ] Tests dùng CountDownLatch/barrier, không dựa vào Thread.sleep.
- [ ] Đã kiểm tra hai readers đồng thời, writer exclusion, Condition unsupported, timed/interruptible acquisition, double unlock.
- [ ] ExecutorService/threads do ứng dụng sở hữu được shutdown/terminated rõ ràng.
- [ ] Đã xem xét ReentrantReadWriteLock khi code cần reentrancy, Condition hoặc fairness tùy chọn.
- [ ] Các API được dùng vẫn còn được hỗ trợ trong JDK hiện đại, không dựa vào chi tiết implementation riêng.

## 23. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 26 — StampedLock: asReadWriteLock, asReadLock, asWriteLock, non-reentrancy, lack of ownership, lock mode và memory effects](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
2. [Oracle Java SE 26 — ReadWriteLock: interface readLock/writeLock và memory synchronization](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html)
3. [Oracle Java SE 26 — Lock: lock, unlock, tryLock, timed tryLock, lockInterruptibly và newCondition](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/Lock.html)
4. [Oracle Java SE 26 — ReentrantReadWriteLock: reentrancy, fairness, Condition và gợi ý StampedLock view khi không cần reentrancy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
5. [Oracle Java SE 26 — CountDownLatch: phối hợp tasks trong test concurrency](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
6. [Oracle Java SE 26 — CompletableFuture: runAsync, allOf và join trong ví dụ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
7. [Oracle Java SE 26 — ExecutorService: shutdown và awaitTermination](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
8. [OpenJDK — StampedLock.java: nguồn tham khảo implementation; không dựa vào field nội bộ như API contract](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/concurrent/locks/StampedLock.java)

**Ghi nhớ cuối cùng:** `StampedLock.asReadWriteLock()` đưa **cùng một StampedLock** vào hình thức giao diện `ReadWriteLock` để code có thể gọi `readLock().lock()/unlock()` và `writeLock().lock()/unlock()`. Nó giúp tích hợp API nhưng **không thêm reentrancy, Condition, ownership theo thread hay fairness**. Cách viết an toàn là **acquire → try → finally unlock**, không tự re-acquire, không trộn raw stamp và view release, và chỉ dùng những tính chất được Javadoc bảo đảm.
