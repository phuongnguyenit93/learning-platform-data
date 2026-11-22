# tryConvertToWriteLock và chuyển chế độ với StampedLock trong Java

`java.util.concurrent.locks.StampedLock` hỗ trợ ba chế độ truy cập dữ liệu dùng chung: **write lock độc quyền**, **read lock chia sẻ** và **optimistic read**. Các phương thức `tryConvertToWriteLock`, `tryConvertToReadLock`, `tryConvertToOptimisticRead` cho phép **thử chuyển giữa những chế độ này**, đôi khi không cần nhả một lock rồi lấy lock khác. Đây là một lợi ích quan trọng khi thao tác thường bắt đầu bằng đọc nhưng cần sửa trạng thái nếu thỏa một điều kiện.

Tuy nhiên, chuyển chế độ không giống thao tác nâng cấp lock luôn thành công. `tryConvertToWriteLock(stamp)` chỉ thành công nếu stamp phù hợp và **có thể lấy quyền ghi ngay tại thời điểm thử**. Phương thức trả `0L` nếu không chuyển được. Khi chuyển thất bại, phải xử lý đúng **stamp cũ**, việc nhả/giữ lock và **đọc lại điều kiện nghiệp vụ** nếu phải nhả read lock trước khi xin write lock.

Bài này giải thích ngữ nghĩa ba chế độ, ma trận chuyển đổi, điều kiện thành công/thất bại, vòng đời stamp, cách viết fallback an toàn, vấn đề deadlock vì StampedLock **không reentrant**, dùng optimistic read và `validate`, các phép downgrade, trường hợp cạnh tranh, test xác định bằng latch và ví dụ Java 17+ có stdout đã kiểm chứng. Các API sử dụng **vẫn được hỗ trợ trong Java hiện hành**; bài không dựa vào các giả định triển khai cũ hoặc kỹ thuật legacy.

## 1. StampedLock là gì và vì sao cần chuyển chế độ?

Một đối tượng `StampedLock` quản lý phiên bản và chế độ truy cập. Người gọi nhận **stamp kiểu long** từ thao tác lấy lock hoặc optimistic read, rồi dùng stamp đó để chuyển mode, validate hoặc nhả lock.

~~~java
StampedLock lock = new StampedLock();

long stamp = lock.readLock();
try {
    // Đọc trạng thái được bảo vệ bằng read lock.
} finally {
    lock.unlockRead(stamp);
}
~~~

Mảnh code cần `import java.util.concurrent.locks.StampedLock;`. `readLock()` có thể chặn trong lúc đang có writer. Tương tự, `writeLock()` trả write stamp cho quyền ghi độc quyền.

Nếu chỉ muốn đọc một trạng thái, read lock là đủ. Nếu muốn “đọc số lượng tồn rồi giảm đi một khi còn hàng”, ta cần **đọc điều kiện rồi ghi**, trong khi điều kiện phải được kiểm dưới bảo vệ lock thích hợp. Cách đọc rồi nhả read, sau đó xin write để cập nhật có một **khoảng trống** mà thread khác có thể thay đổi dữ liệu. `tryConvertToWriteLock` có thể tránh khoảng trống này nếu việc chuyển mode thành công.

### 1.1. Ba mode

| Mode | Cách lấy | Quyền và hạn chế |
|---|---|---|
| Write lock | `writeLock()` hoặc `tryWriteLock()` | Một writer độc quyền, không có read lock đồng thời |
| Read lock | `readLock()` hoặc `tryReadLock()` | Nhiều reader có thể cùng giữ lock; không được sửa trạng thái bảo vệ |
| Optimistic read | `tryOptimisticRead()` | Không khóa reader thật; cần `validate(stamp)` sau khi copy các field |
| Không giữ lock | Sau khi unlock hoặc convert thành optimistic | Không được đọc/ghi trạng thái như đang có lock |

**Optimistic read không phải một read lock thực sự.** Nó chỉ cung cấp khả năng kiểm sau rằng writer có xuất hiện trong khoảng quan sát hay không. Trong lúc copy field, writer **vẫn có thể thay đổi dữ liệu**, nên các giá trị tạm đọc có thể không nhất quán. Cách dùng đúng: copy các field đơn giản vào biến local, `validate`, nếu sai thì fallback sang read lock và đọc lại.

### 1.2. Stamp không phải boolean hoặc thread ID

`readLock` và `writeLock` trả một stamp khác `0L` khi lấy được lock. Những phương thức `tryReadLock`/`tryWriteLock` có thể trả `0L` nếu không lấy được quyền. `tryOptimisticRead()` trả stamp quan sát khác 0 nếu không có write lock tại thời điểm đó, hoặc 0 khi không thể lấy stamp.

- Stamp là **capability** gắn với trạng thái cụ thể của **đúng đối tượng StampedLock**.
- Một stamp không phải tên thread, cũng không phải token bảo mật để chuyển giữa service.
- Không hardcode hoặc diễn giải các bit của stamp: dùng các API chính thức.
- Khi chuyển mode thành công, **stamp trả về mới là handle cần dùng tiếp**.
- Không dùng một stamp đã nhả lock để unlock lần nữa.

StampedLock không ràng buộc ownership vào thread như nhiều lock khác; một stamp hợp lệ có thể được trao cho luồng khác theo thiết kế, nhưng điều này làm lifecycle phức tạp. Với hầu hết code ứng dụng, nên giữ việc lấy, chuyển và nhả stamp trong một phạm vi rõ ràng.

## 2. tryConvertToWriteLock(long stamp): hợp đồng cốt lõi

Phương thức:

~~~java
long writeStamp = lock.tryConvertToWriteLock(stamp);
~~~

Nếu trạng thái của lock phù hợp với stamp nhận vào, nó thử thực hiện một trong các thao tác atomically:

1. **Stamp đã là write lock hợp lệ:** trả lại write stamp đó.
2. **Stamp là read lock hợp lệ:** khi write lock đang khả dụng, nó **nhả read lock tương ứng và chuyển sang write lock** trong một thao tác nguyên tử.
3. **Stamp là optimistic read hợp lệ:** thử lấy write lock ngay lập tức nếu khả dụng.
4. **Mọi trường hợp khác:** trả `0L`.

Chữ **try** rất quan trọng: phương thức **không đứng chờ** reader khác trả lock hoặc writer khác kết thúc. Nếu không chuyển được, trả zero để người gọi chủ động chọn hướng xử lý.

### 2.1. Tại sao read → write có thể thất bại?

Read lock cho phép nhiều reader cùng giữ quyền. Một writer cần quyền **độc quyền**. Nếu thread A đang giữ read stamp và thread B cũng đang đọc, A không thể tự chuyển ngay thành writer vì B vẫn nắm quyền đọc. Do đó lời gọi `tryConvertToWriteLock` từ A trả `0L`.

~~~text
A: readLock() -----[ giữ read ]----- tryConvertToWriteLock(A) => 0
B:       readLock() -----[ giữ read ]--------------- unlockRead(B)
A: vẫn giữ read stamp A sau khi conversion không thành công
~~~

Không có nghĩa StampedLock bị hỏng. Đây là sự từ chối **nâng cấp độc quyền khi điều kiện chưa cho phép**.

### 2.2. Thành công khi chỉ còn một reader

Nếu một read stamp hợp lệ đang nắm read lock và không có reader khác cùng cản trở, conversion **có thể thành công ngay**:

~~~java
long stamp = lock.readLock();
try {
    long converted = lock.tryConvertToWriteLock(stamp);
    if (converted != 0L) {
        stamp = converted; // Hiện giữ write lock.
        // Cập nhật trạng thái được bảo vệ.
    }
} finally {
    lock.unlock(stamp);
}
~~~

Đây là mảnh code minh họa; phải có `lock` đã khởi tạo. `unlock(stamp)` phù hợp vì nó nhả **mode tương ứng với stamp hiện hành** (read hoặc write). Nếu dùng `unlockRead(stamp)` sau khi đã chuyển thành write, đó là sai mode và có thể ném `IllegalMonitorStateException`.

Một lần try thất bại **không bảo đảm** lock đang ở một trạng thái cụ thể trong tương lai. `try` là best effort, không phải phép kiểm để quyết định toàn bộ tương lai của những thread khác.

### 2.3. Stamp đã là write → write

Nếu stamp truyền vào vốn là write stamp hợp lệ, `tryConvertToWriteLock` trả write stamp đó; không thêm một lần khóa độc lập. StampedLock **không reentrant**, nên không dùng logic này để mô phỏng việc tăng số lần giữ write lock như một `ReentrantLock`.

### 2.4. Optimistic → write

~~~java
long optimistic = lock.tryOptimisticRead();
if (optimistic != 0L) {
    long writeStamp = lock.tryConvertToWriteLock(optimistic);
    if (writeStamp != 0L) {
        try {
            // Đã có độc quyền ghi.
        } finally {
            lock.unlockWrite(writeStamp);
        }
    }
}
~~~

Đây là mảnh minh họa của một nhánh không có thao tác đọc dữ liệu. Nếu optimistic stamp đã bị writer làm vô hiệu hoặc không thể lấy write lock tức thời, conversion trả zero. **Không viết dữ liệu chỉ vì optimistic stamp khác 0**: phải kiểm writeStamp và nắm quyền độc quyền.

Nếu logic nghiệp vụ đã copy một trạng thái trước khi thử conversion, hãy xác nhận rằng dữ liệu và điều kiện còn phù hợp khi đã có write lock; cách an toàn là **kiểm lại** các điều kiện quan trọng dưới quyền ghi trước khi thay đổi.

## 3. Ma trận chuyển mode và ý nghĩa stamp

| Mode ban đầu | Phương thức thử | Nếu thành công | Nếu trả 0 |
|---|---|---|---|
| Write | `tryConvertToWriteLock` | Vẫn giữ write | Stamp không phù hợp/trạng thái không hợp lệ |
| Read | `tryConvertToWriteLock` | Nhả read atomically, lấy write | Vẫn giữ read lock gốc |
| Optimistic | `tryConvertToWriteLock` | Lấy write lock | Không có write; cần kiểm lại trạng thái |
| Write | `tryConvertToReadLock` | Hạ cấp nguyên tử sang read | Với stamp không phù hợp, không có conversion |
| Read | `tryConvertToReadLock` | Giữ read mode | Stamp không phù hợp |
| Optimistic | `tryConvertToReadLock` | Lấy read lock nếu sẵn ngay | Không lấy được read |
| Write | `tryConvertToOptimisticRead` | Nhả write, có observation stamp | Không thể chuyển |
| Read | `tryConvertToOptimisticRead` | Nhả một read hold, có observation stamp | Không thể chuyển |
| Optimistic | `tryConvertToOptimisticRead` | Giữ stamp nếu còn hợp lệ | Quan sát cũ không hợp lệ |

Một nguyên tắc thực thi duy nhất: **chỉ thay biến stamp quản lý bằng giá trị conversion khi kết quả khác 0**. Nếu conversion thất bại và stamp đầu vào là read lock còn hợp lệ, người gọi **vẫn có nghĩa vụ nhả read lock đó**.

Không lưu stamp cũ với ý định unlock hai lần: conversion thành công đã thay thế quyền giữ lock bằng mode mới. Với optimistic stamp, không có lock thực để unlock; nếu chuyển optimistic thành write thành công, chỉ write stamp mới cần unlock.

### 3.1. Phân biệt 0 và stamp thật

~~~java
long next = lock.tryConvertToWriteLock(stamp);
if (next != 0L) {
    stamp = next;
    // Có write lock.
} else {
    // Chưa được quyền ghi; stamp gốc vẫn cần quản lý.
}
~~~

Không viết `stamp = lock.tryConvertToWriteLock(stamp)` **rồi mới kiểm zero** khi stamp gốc đang là read lock. Nếu kết quả bằng 0, chương trình đã ghi đè mất handle hợp lệ, không thể nhả read lock bằng stamp cũ, dễ gây leak lock.

### 3.2. Kiểm mode bằng API chính thức

Từ **Java 10**, `StampedLock` có:

- `isWriteLockStamp(long)`;
- `isReadLockStamp(long)`;
- `isLockStamp(long)`;
- `isOptimisticReadStamp(long)`.

Ví dụ:

~~~java
if (StampedLock.isWriteLockStamp(stamp)) {
    lock.unlockWrite(stamp);
} else if (StampedLock.isReadLockStamp(stamp)) {
    lock.unlockRead(stamp);
}
~~~

Những method kiểm **hình thức của stamp** rất hữu ích khi control flow phức tạp, nhưng không phải lệnh xác minh stamp vẫn là quyền hợp lệ cho cùng lock tại thời điểm hiện tại. Các phương thức này **không có từ Java 8**, dù vẫn được hỗ trợ trên JDK hiện đại. Nếu muốn ví dụ chạy từ Java 8, có thể theo dõi mode bằng biến logic do ứng dụng quản lý hoặc dùng `unlock(stamp)` cho stamp khóa còn hợp lệ.

## 4. Fallback đúng khi read → write không thành công

Tình huống thường gặp: đọc xem kho còn hàng, nếu có thì giảm một. Nếu conversion thất bại vì có reader khác, phải chọn một trong hai chính sách: **thử lại sau** hoặc **nhả read rồi xin write**.

Mẫu an toàn:

~~~java
long stamp = lock.readLock();
try {
    while (available > 0) {
        long writeStamp = lock.tryConvertToWriteLock(stamp);
        if (writeStamp != 0L) {
            stamp = writeStamp;
            available--;
            return true;
        }

        lock.unlockRead(stamp);
        stamp = 0L;
        stamp = lock.writeLock();
        // Quay lại đầu vòng: kiểm available dưới write lock.
    }
    return false;
} finally {
    if (stamp != 0L) {
        lock.unlock(stamp);
    }
}
~~~

Đây là **mảnh code trong một phương thức**, giả định `available` là field được bảo vệ bởi `lock` và phương thức trả boolean. Chương trình đầy đủ ở phần 11 dùng đúng cấu trúc này.

**Vì sao có while thay vì if?** Sau khi nhả read lock, một thread khác có thể lấy write lock và giảm số lượng. Khi ta lấy write lock trở lại, điều kiện `available > 0` **phải được đọc lại**. Nếu vẫn tin vào giá trị thấy trước khi nhả read, ứng dụng có thể bán vượt lượng tồn.

### 4.1. Hai đường đi

**Đường chuyển thành công:**

~~~text
readLock -> kiểm available -> tryConvertToWriteLock thành công
          -> tiếp tục dưới write lock -> available-- -> unlock write
~~~

Không có khoảng trống giữa read và write; conversion là nguyên tử. Điều kiện được kiểm trong thời gian giữ read lock và writer không thể chen ngang trước khi lấy write lock.

**Đường chuyển thất bại:**

~~~text
readLock -> kiểm available -> tryConvertToWriteLock = 0
          -> unlock read  [CÓ KHOẢNG TRỐNG]
          -> writeLock (có thể chờ)
          -> kiểm available LẠI
          -> available-- nếu còn hàng -> unlock write
~~~

Không có cách tự biến một conversion thất bại thành nâng cấp nguyên tử bằng việc gọi `writeLock()` khi vẫn còn giữ read lock cũ. Cần nhả quyền cũ trước rồi xử lý khả năng state đổi.

### 4.2. Vì sao phải đặt stamp = 0L giữa unlock và writeLock?

Trong ví dụ, `stamp` biểu diễn **quyền giữ lock hiện còn hiệu lực**. Ngay sau `unlockRead(stamp)`, read stamp cũ không còn đại diện cho lock đang giữ. Gán 0 trước khi gọi `writeLock()` giúp `finally` không unlock lại stamp cũ nếu `writeLock()` hoặc đoạn code phụ được thay đổi làm phát sinh lỗi giữa hai bước.

`writeLock()` không throw `InterruptedException`, nhưng không nên dựa vào điều đó để bỏ qua quản lý stamp. Nếu dùng `writeLockInterruptibly()` hoặc timed `tryWriteLock`, việc gán 0 trước khi xin lock càng quan trọng vì có nhánh gián đoạn.

### 4.3. Vì sao không gọi writeLock khi còn giữ read?

Đây là anti-pattern:

~~~java
long stamp = lock.readLock();
try {
    if (shouldWrite()) {
        long writeStamp = lock.writeLock(); // Có thể tự kẹt.
        // ...
    }
} finally {
    lock.unlockRead(stamp);
}
~~~

Đây là **mảnh mã cố ý sai**, với `shouldWrite()` do ứng dụng định nghĩa. StampedLock **không reentrant**. Thread đang giữ read lock trở thành một reader ngăn cản write lock; gọi writeLock và đợi có thể tạo self-deadlock vì read stamp chỉ được nhả sau khi lời gọi chặn đã trở về.

Dùng `tryConvertToWriteLock` hoặc nhả read rồi lấy write theo protocol có recheck. Không chạy mảnh phản ví dụ trên trong chương trình demo.

## 5. tryConvertToReadLock: hạ quyền write thành read

Khi đã cập nhật xong nhưng còn cần đọc trạng thái nhiều bước, có thể hạ write lock xuống read lock **một cách nguyên tử**:

~~~java
long stamp = lock.writeLock();
try {
    updateState();

    long readStamp = lock.tryConvertToReadLock(stamp);
    if (readStamp == 0L) {
        throw new IllegalStateException("Cannot downgrade");
    }

    stamp = readStamp;
    inspectState();
} finally {
    lock.unlock(stamp);
}
~~~

Đây là **mảnh minh họa** với các hàm `updateState`/`inspectState` thuộc ứng dụng. Khi từ write stamp hợp lệ, downgrade chuyển quyền ghi thành quyền đọc mà không mở khoảng trống writer khác có thể chen vào giữa. Không cố giữ write lock trong khi chạy một thao tác dài chỉ cần đọc.

### 5.1. Điều kiện thành công khác nhau theo mode

- **Write → read:** nhả write atomically và lấy read.
- **Read → read:** giữ mode read, trả stamp tương ứng.
- **Optimistic → read:** thử lấy read lock ngay lập tức, có thể trả 0 nếu không khả dụng.

Trong tất cả trường hợp, chỉ dùng stamp được trả về khi **khác 0**. Khi hạ từ write sang read, **không được ghi protected state** sau điểm chuyển, vì hiện không còn độc quyền.

### 5.2. Downgrade không giống unlock rồi readLock

Nếu nhả write rồi gọi readLock, writer khác có thể xen vào giữa và thay dữ liệu. Convert write→read thành công **đóng khoảng trống đó**, phù hợp khi cần tiếp tục đọc snapshot trạng thái vừa cập nhật trong lúc không cần giữ quyền ghi lâu.

Dù đã có read lock, những phép đọc liên quan đến cấu trúc **không được bảo vệ bằng cùng lock** vẫn có thể thay đổi bởi cơ chế khác; phải biết chính xác phạm vi đối tượng do lock bảo vệ.

## 6. tryConvertToOptimisticRead: chuyển sang quan sát

`tryConvertToOptimisticRead(stamp)` làm giảm mức đồng bộ còn mạnh hơn:

- Từ **write lock** hợp lệ: nhả quyền ghi và trả một observation stamp.
- Từ **read lock** hợp lệ: nhả một read hold và trả observation stamp.
- Từ **optimistic stamp**: trả stamp nếu còn hợp lệ theo điều kiện API.
- Nếu stamp không phù hợp: trả zero.

Ví dụ hạ read→optimistic:

~~~java
long stamp = lock.readLock();
try {
    int copied = available;
    long optimistic = lock.tryConvertToOptimisticRead(stamp);

    if (optimistic != 0L) {
        stamp = 0L;  // Không còn giữ read lock.
        if (lock.validate(optimistic)) {
            return copied;
        }
    }
    // Nếu không thể validate, cần fallback đọc có khóa.
} finally {
    if (stamp != 0L) {
        lock.unlockRead(stamp);
    }
}
~~~

Đây là **mảnh minh họa giải thích lifecycle**, không phải phương thức hoàn chỉnh: nhánh fallback cần được cài đặt trước khi đem vào production. Hãy xem chương trình runnable phía dưới cho cách đọc optimistic có fallback rõ ràng.

### 6.1. Observation stamp không được unlock

Sau khi conversion thành optimistic thành công, **không còn read/write lock để nhả**. Vì thế không gọi `unlockRead(oldStamp)` hoặc `unlockWrite(oldStamp)` nữa; và cũng không gọi `unlock(optimisticStamp)` vì đó không phải lock stamp.

Nếu muốn chuyển lại từ optimistic sang read/write, phải gọi `tryConvertToReadLock`/`tryConvertToWriteLock` và kiểm kết quả. Không giả định conversion chắc chắn thành công sau khi một writer mới xuất hiện.

### 6.2. Khi nào nên sử dụng?

Ví dụ cập nhật dữ liệu, sau đó cần làm phần tính toán/format không còn sửa shared state nhưng muốn có khả năng kiểm rằng không writer nào chen vào. Convert sang optimistic giúp **nhả quyền độc quyền sớm**. Tuy nhiên, việc kiểm `validate` không phải khóa giữ trạng thái bất biến trong suốt một callback bất kỳ. Nếu công việc sau đó cần snapshot ổn định liên tục (ví dụ duyệt collection mutable), một read lock thực sự có thể phù hợp hơn.

## 7. Optimistic read, validate và ranh giới an toàn bộ nhớ

Cách đọc thông dụng:

~~~java
long stamp = lock.tryOptimisticRead();
int local = available;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        local = available;
    } finally {
        lock.unlockRead(stamp);
    }
}
return local;
~~~

Đây là mảnh trong phương thức, field `available` phải được quản lý nhất quán qua cùng lock. Nếu có writer đang giữ quyền ghi, `tryOptimisticRead()` có thể trả 0, khi đó `validate(0)` trả false và fallback readLock là phù hợp.

**Điều kiện quan trọng:**

1. Các field được copy sang biến local trước khi validate.
2. Nếu validation thất bại, **bỏ bản sao đọc trước đó** và đọc lại dưới read lock.
3. Tất cả writer phải dùng cùng lock/protocol để bảo đảm ý nghĩa version stamp.
4. Không đọc object graph mutable phức tạp theo cách có thể gặp rủi ro chỉ trong lúc đọc optimistic mà chưa validate.

Tài liệu chính thức cảnh báo các đọc optimistic chưa validate có thể rất không nhất quán, đặc biệt khi lần theo reference, array hoặc collection; không dùng nó như một read lock có bảo vệ hoàn chỉnh.

### 7.1. validate(true) có bảo đảm gì?

Với optimistic stamp hợp lệ, `validate(stamp)` đúng khi không có writer giành write lock kể từ lúc lấy stamp theo quy tắc API. Nó cung cấp bảo đảm memory ordering được tài liệu hóa đối với những writer hoàn tất trước đó. Nhưng nó **không giữ khóa sau khi validate**; một writer khác có thể bắt đầu ngay sau phép kiểm.

Ví dụ:

~~~text
T1: optimistic = tryOptimisticRead()
T1: copy x, y
T1: validate(optimistic) => true
T2: writeLock() rồi sửa x, y
T1: dùng bản sao x, y đã validate
~~~

Dùng **bản sao local**, không đọc lại các field trực tiếp sau validate rồi cho rằng chúng vẫn ở cùng phiên bản.

### 7.2. Không dùng validate trước khi viết

Nếu cần sửa trạng thái, phải thật sự có write stamp. `validate(optimistic) == true` chỉ cho biết một quan sát không bị invalidate đến điểm kiểm; nó **không cấp quyền ghi**. Dùng `tryConvertToWriteLock` thành công hoặc `writeLock` để được độc quyền.

## 8. Xử lý thất bại khi chuyển mode và quản lý stamp

Một số lỗi dễ gặp trong code có nhiều nhánh return/throw:

### 8.1. Ghi đè stamp cũ bằng zero

Sai:

~~~java
long stamp = lock.readLock();
try {
    stamp = lock.tryConvertToWriteLock(stamp);
    if (stamp == 0L) {
        return false;
    }
    // ...
} finally {
    lock.unlock(stamp);
}
~~~

Đây là **phản ví dụ**, trong một phương thức boolean. Nếu conversion trả 0, read lock ban đầu **vẫn được giữ** nhưng handle đã bị ghi đè. `unlock(0L)` không thể nhả nó, gây exception và rò quyền đọc.

Đúng:

~~~java
long converted = lock.tryConvertToWriteLock(stamp);
if (converted != 0L) {
    stamp = converted;
}
~~~

Nếu thất bại, biến `stamp` vẫn là read stamp hợp lệ, nên có thể nhả bằng `unlockRead(stamp)` hoặc `unlock(stamp)`.

### 8.2. Double unlock sau chuyển thành công

Sai:

~~~java
long readStamp = lock.readLock();
long writeStamp = lock.tryConvertToWriteLock(readStamp);
if (writeStamp != 0L) {
    lock.unlockRead(readStamp); // Không còn read lock này.
    lock.unlockWrite(writeStamp);
}
~~~

Đây là phản ví dụ. Conversion đã nhả quyền read cũ atomically và chuyển sang write. `unlockRead(readStamp)` sau đó là sai và có thể ném `IllegalMonitorStateException`. Trong code có finally, theo dõi duy nhất **stamp đang quản lý**.

### 8.3. Unlock sai mode

`unlockRead(writeStamp)` hoặc `unlockWrite(readStamp)` sai mode. `unlock(stamp)` có thể tiện khi variable lần lượt giữ read rồi write, nhưng chỉ gọi khi chắc chắn là lock stamp còn hợp lệ. Nếu đang giữ optimistic stamp, **không unlock**.

### 8.4. Stamp không hợp lệ và stamp không thuộc lock

Các thao tác unlock yêu cầu stamp phù hợp **đúng StampedLock** và trạng thái hiện tại; nếu không, `IllegalMonitorStateException`. Không lưu stamp trong database, không truyền stamp cho một StampedLock khác, không dùng stamp numeric cố định trong test.

Stamp có thể được tái sử dụng sau rất lâu theo hợp đồng; không xem nó như version bất biến vĩnh viễn hoặc token xác thực. `StampedLock` dù triển khai Serializable, trạng thái lock khi deserialize được khởi tạo lại, không dùng để đồng bộ phân tán.

## 9. Reentrancy, chờ và starvation

`StampedLock` **không reentrant**. Một thread đang giữ write lock không được kỳ vọng có thể tự gọi `readLock()` hoặc `writeLock()` lần nữa như ReentrantReadWriteLock. Một thread đang giữ read và cố chờ write trong khi chưa nhả read có thể tự kẹt.

### 9.1. Callback không được ngầm xin lại cùng lock

~~~java
long stamp = lock.writeLock();
try {
    helperThatAlsoCallsWriteLock();
} finally {
    lock.unlockWrite(stamp);
}
~~~

Đây là **phản ví dụ** nếu helper xin write lock trên **chính lock đó**: hàm helper có thể chặn mãi, vì lock không reentrant. Nên thiết kế các helper “under lock” rõ ràng, không tự xin lại lock, hoặc cân nhắc cơ chế khác nếu cấu trúc gọi thực sự đòi reentrancy.

### 9.2. Fairness không được bảo đảm

StampedLock không cam kết một chính sách luôn ưu tiên reader hay writer. Các phương thức `tryXxx` là **best effort**, và liên tục retry một conversion không bảo đảm tiến triển. Nếu hệ thống thường xuyên có reader mới, writer có thể bị trì hoãn.

Đừng spin không giới hạn:

~~~java
while (lock.tryConvertToWriteLock(readStamp) == 0L) {
    // Vòng busy-wait có thể giữ read lock và tốn CPU.
}
~~~

Đây là phản ví dụ. Giữ read lock trong lúc đợi writer càng làm điều kiện nâng cấp khó thành công khi còn reader khác. Thường nên nhả read rồi lấy write có timeout/interrupt phù hợp và **recheck**.

### 9.3. Các phương thức có thể chặn và interrupt

- `readLock()` và `writeLock()` có thể chặn, không khai báo `InterruptedException`.
- `readLockInterruptibly()` và `writeLockInterruptibly()` cho phép chờ có thể bị interrupt.
- `tryReadLock(timeout,unit)` và `tryWriteLock(timeout,unit)` chờ tối đa theo thời gian và có thể bị interrupt.
- `tryConvertToWriteLock` không có overload timeout; nó thử ngay và trả stamp hoặc 0.

Nếu nghiệp vụ có deadline/hủy, nên cân nhắc logic timed acquisition **sau khi đã nhả read lock** khi cần nâng lên write, luôn kiểm lại điều kiện sau khi lấy quyền mới.

## 10. Khi nào chuyển đổi giúp ích?

### 10.1. Đọc phần lớn, thỉnh thoảng cập nhật

Một cache hoặc cấu trúc nội bộ thường chỉ đọc. Nếu một trường đã đạt ngưỡng cần cập nhật, conversion read→write có thể nhanh hơn so với nhả read rồi xin write trong tình huống ít reader khác. Nhưng lợi ích thực tế phụ thuộc tranh chấp và workload; **không khẳng định luôn nhanh hơn** mà chưa đo.

### 10.2. Viết xong cần quan sát ổn định

Sau một cập nhật, bạn muốn đọc trạng thái bảo vệ trong lúc cho phép reader khác đọc. `tryConvertToReadLock` hạ quyền write atomically sang read. Nó giữ ngữ nghĩa không có writer chen vào giữa thao tác cập nhật và phần đọc.

### 10.3. Viết xong không cần giữ read lock

`tryConvertToOptimisticRead` nhả write/read, giữ lại stamp cho phép validate. Nó phù hợp thao tác copy đơn giản rồi xác thực, nhưng **không** phù hợp khi cần một cấu trúc mutable được bảo vệ liên tục trong quá trình duyệt.

### 10.4. Thao tác nhiều dữ liệu liên quan

Nếu một nghiệp vụ cần đảm bảo invariant giữa nhiều field như `balance` và `version`, read lock/write lock cho phép thao tác nhất quán trong critical section. Optimistic read chỉ thích hợp khi có thể copy các field **một cách an toàn** rồi validate. Nếu cần gọi code bất định (I/O, callback ngoài), hãy thiết kế lại để không giữ lock quá lâu.

## 11. Chương trình Java hoàn chỉnh đã kiểm chứng

Lưu thành file **`StampedModeDemo.java`**. Chương trình chỉ dùng JDK, có thể biên dịch với **JDK 17+** và dùng các API StampedLock còn được hỗ trợ. Nó minh họa:

1. Đọc số hàng qua optimistic read với validate và fallback read lock.
2. Đặt hàng qua read→write, cập nhật dưới write lock.
3. Xử lý khi không còn hàng.
4. Hạ write→read khi vừa cập nhật xong.
5. Chuyển read→optimistic và xác minh stamp.
6. Chuyển optimistic→write trong tình huống không có cạnh tranh.
7. Phát hiện optimistic stamp đã cũ khi có writer mới.
8. Ép thất bại read→write bằng **một reader khác thực sự đang giữ lock**, dùng CountDownLatch, không phụ thuộc may rủi scheduler.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.locks.*;

public class StampedModeDemo {
    static final class Inventory {
        private final StampedLock lock = new StampedLock();
        private int available;

        Inventory(int available) {
            this.available = available;
        }

        boolean reserveOne() {
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
                }
                return false;
            } finally {
                if (stamp != 0L) lock.unlock(stamp);
            }
        }

        int snapshot() {
            long stamp = lock.tryOptimisticRead();
            int value = available;
            if (!lock.validate(stamp)) {
                stamp = lock.readLock();
                try {
                    value = available;
                } finally {
                    lock.unlockRead(stamp);
                }
            }
            return value;
        }

        int setAndDowngrade(int newValue) {
            long stamp = lock.writeLock();
            try {
                available = newValue;
                long readStamp = lock.tryConvertToReadLock(stamp);
                if (readStamp == 0L) throw new AssertionError("Downgrade failed");
                stamp = readStamp;
                return available;
            } finally {
                lock.unlock(stamp);
            }
        }

        boolean readToOptimistic() {
            long stamp = lock.readLock();
            try {
                long observation = lock.tryConvertToOptimisticRead(stamp);
                if (observation == 0L)
                    throw new AssertionError("Expected read to optimistic");
                stamp = 0L;
                return lock.validate(observation);
            } finally {
                if (stamp != 0L) lock.unlockRead(stamp);
            }
        }

        boolean optimisticToWrite(int newValue) {
            long observation = lock.tryOptimisticRead();
            if (observation == 0L) return false;
            long stamp = lock.tryConvertToWriteLock(observation);
            if (stamp == 0L) return false;
            try {
                available = newValue;
                return true;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        void setExclusive(int newValue) {
            long stamp = lock.writeLock();
            try {
                available = newValue;
            } finally {
                lock.unlockWrite(stamp);
            }
        }
    }

    static boolean failedUpgradeWithSecondReader() throws Exception {
        StampedLock lock = new StampedLock();
        CountDownLatch secondHeld = new CountDownLatch(1);
        CountDownLatch releaseSecond = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        long first = lock.readLock();
        Future<?> second = pool.submit(() -> {
            long stamp = lock.readLock();
            try {
                secondHeld.countDown();
                if (!releaseSecond.await(5, TimeUnit.SECONDS))
                    throw new IllegalStateException("Other reader timed out");
            } finally {
                lock.unlockRead(stamp);
            }
            return null;
        });
        try {
            if (!secondHeld.await(5, TimeUnit.SECONDS))
                throw new IllegalStateException("Other reader did not start");
            long converted = lock.tryConvertToWriteLock(first);
            if (converted != 0L) {
                first = converted;
                throw new AssertionError("Unexpected conversion success");
            }
            return converted == 0L;
        } finally {
            lock.unlock(first);
            releaseSecond.countDown();
            try {
                second.get(5, TimeUnit.SECONDS);
            } finally {
                pool.shutdownNow();
                pool.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Inventory i = new Inventory(2);
        System.out.println("Initial: " + i.snapshot());
        System.out.println("Reserve #1: " + i.reserveOne());
        System.out.println("Reserve #2: " + i.reserveOne());
        System.out.println("Reserve #3: " + i.reserveOne());
        System.out.println("After reserves: " + i.snapshot());
        System.out.println("Write to read, value: " + i.setAndDowngrade(7));
        System.out.println("Read to optimistic valid: " + i.readToOptimistic());
        System.out.println("Optimistic to write: " + i.optimisticToWrite(8));
        System.out.println("After optimistic conversion: " + i.snapshot());
        long stale = i.lock.tryOptimisticRead();
        i.setExclusive(9);
        System.out.println("Stale optimistic stamp valid: " + i.lock.validate(stale));
        System.out.println("Read to write blocked by second reader: "
                + failedUpgradeWithSecondReader());
        System.out.println("Final inventory: " + i.snapshot());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StampedModeDemo.java
java StampedModeDemo
~~~

Stdout đã được chạy và kiểm tra:

~~~text
Initial: 2
Reserve #1: true
Reserve #2: true
Reserve #3: false
After reserves: 0
Write to read, value: 7
Read to optimistic valid: true
Optimistic to write: true
After optimistic conversion: 8
Stale optimistic stamp valid: false
Read to write blocked by second reader: true
Final inventory: 9
~~~

### 11.1. Tại sao kết quả có thể xác định?

Đối với các bước update liên tiếp trong `main`, không có writer cạnh tranh. `reserveOne()` giảm từ 2 xuống 1 rồi 0; lần gọi thứ ba trả false. `setAndDowngrade(7)` cập nhật dưới write lock và hạ sang read trước khi đọc. `optimisticToWrite(8)` chuyển thành write trong tình huống không có đối thủ.

Để kiểm lỗi conversion, `failedUpgradeWithSecondReader` tạo **một reader thứ hai** và đợi latch xác nhận reader ấy đã giữ lock. Chỉ sau đó mới gọi `tryConvertToWriteLock(first)`, nên conversion phải trả zero vì còn reader khác. Hàm cuối trả boolean xác nhận thất bại đã được chứng kiến, đồng thời nhả cả hai read lock trong các khối cleanup.

Không in số nguyên của stamp: stamp là chi tiết nội bộ/lifecycle, không phải giá trị ổn định để test. Không in thời gian chạy vì scheduler và tải máy khác nhau.

### 11.2. Vì sao một lần validate trả false?

`main` lấy optimistic stamp, sau đó gọi `setExclusive(9)` bằng write lock. Writer đã xuất hiện sau lúc lấy stamp; khi gọi `validate(stale)`, kết quả là false. Điều này minh họa lý do optimistic read phải có nhánh xử lý bị invalidate, không được dùng như quyền khóa giữ dữ liệu không đổi.

### 11.3. Vì sao đoạn reserveOne phải có while?

Nếu conversion từ read sang write thành công, điều kiện vừa đọc được bảo vệ xuyên qua lần chuyển. Nếu thất bại, mã nhả read rồi lấy write; **một writer khác có thể xen vào**. Vòng while tái kiểm `available > 0` dưới stamp mới, tránh giảm số lượng khi hết hàng.

Chương trình có một phần demo kiểm thất bại conversion độc lập; nó không giả vờ rằng chỉ kiểm `tryConvertToWriteLock` thất bại là đủ cho mọi giao thức cập nhật. Phần fallback trong `reserveOne` mới cho thấy cấu trúc phải dùng khi muốn cập nhật đúng.

## 12. Kiểm thử contention và bất biến

| Test | Tình huống | Điều cần assert |
|---|---|---|
| Không có reader khác | Một read stamp đang giữ lock | Conversion read→write có thể thành công |
| Có reader thứ hai | B giữ read khi A muốn write | Conversion từ read của A trả 0 |
| Conversion thất bại | Vẫn đang giữ read stamp cũ | Có thể unlock read cũ, không bị leak |
| Conversion thành công | Đã chuyển sang write stamp | Chỉ unlock theo stamp hiện hành |
| Không có hàng | `available == 0` | `reserveOne` trả false |
| Writer xen giữa release/reacquire | State thay đổi trong khoảng trống | Điều kiện được recheck dưới write |
| Write→read | Writer vừa cập nhật | Downgrade giữ được read bảo vệ không có writer chen |
| Read→optimistic | Read hold được nhả sau convert | Không còn unlock read lần nữa |
| Optimistic→write | Không cạnh tranh | Chỉ ghi nếu writeStamp != 0 |
| Optimistic bị writer invalidate | Write lock được lấy sau stamp | `validate` trả false |
| Optimistic stamp = 0 | Writer đang giữ lock | Fallback read lock |
| Stamp dùng sai lock | Stamp không thuộc lock | Unlock bị từ chối theo contract |
| Non-reentrant call | Trong lock lại xin chính lock | Tránh self-deadlock |
| Nhiều reader/writer | Tải thật cao | Đúng invariant, không leak |
| Reader starvation | Reader liên tục xuất hiện | Ghi nhận latency và fairness policy |

### 12.1. Đo đạc không chỉ nhìn throughput

Với read-heavy workload, có thể benchmark:

- `readLock` so với `tryOptimisticRead` + `validate` + fallback.
- Tỷ lệ conversion read→write thành công trong các mức reader count khác nhau.
- Tail latency p95/p99 khi có writer liên tục.
- CPU/parking, lock contention, số lần fallback.
- Độ dài critical section và lượng copy dữ liệu optimistic.
- Nhiều writer contention để nhận diện starvation.

Không cho rằng StampedLock luôn hơn `ReentrantReadWriteLock` hoặc `synchronized`. Nếu yêu cầu **reentrancy, fairness, Condition, hoặc API Lock tiêu chuẩn**, cơ chế khác có thể phù hợp hơn. Chọn bằng **semantics và benchmark đúng workload**.

### 12.2. Latch thay cho sleep

Để tái hiện conversion thất bại, chỉ `Thread.sleep(10)` rồi gọi convert **không bảo đảm** lúc đó reader thứ hai đang nắm lock. Dùng `CountDownLatch` để chờ tín hiệu sau khi readLock được lấy. Các phép `await`/`get(timeout)` có giới hạn giúp test thất bại rõ ràng thay vì treo vô hạn.

Coordinator của test được phép chờ worker ở ranh giới kiểm thử. Không dùng một thread pool quá nhỏ khiến các task đang chờ latch chiếm hết worker và ngăn task còn lại tiến triển.

## 13. Mẫu dùng sai và cách sửa

### 13.1. Dùng optimistic read để duyệt cấu trúc mutable phức tạp

Sai về mặt thiết kế:

~~~java
long stamp = lock.tryOptimisticRead();
for (Item item : mutableList) {
    inspect(item);
}
if (lock.validate(stamp)) {
    return result;
}
~~~

Đây là **mảnh phản ví dụ** với kiểu/hàm ứng dụng. Trước khi validate, writer có thể đồng thời thay list khiến việc duyệt throw exception hoặc đọc cấu trúc không nhất quán. Việc validate sau đó **không sửa được những lỗi đã phát sinh trong khi duyệt**. Với kiểu dữ liệu như vậy, dùng read lock hoặc immutable snapshot.

### 13.2. Giữ write lock trong khi gọi I/O

~~~java
long stamp = lock.writeLock();
try {
    sendHttpRequestSynchronously();
} finally {
    lock.unlockWrite(stamp);
}
~~~

Đây là phản ví dụ, hàm HTTP giả định. Lời gọi mạng có thể chờ lâu, khiến mọi reader/writer bị trì hoãn. Nên chia phase: thu thập data cần thiết dưới lock, nhả lock, thực hiện I/O bên ngoài, và nếu cần cập nhật lại, xin lock mới rồi **recheck version/condition**.

### 13.3. Spin conversion trong khi còn giữ read

Sai:

~~~java
while (lock.tryConvertToWriteLock(stamp) == 0L) {
    // Busy retry không giải phóng read lock.
}
~~~

Nếu reader khác tiếp tục giữ quyền, không có tiến triển; vòng lặp chỉ tốn CPU và có thể ảnh hưởng scheduling. Thường cần nhả read rồi xin write, timeout, retry có kiểm soát hoặc thiết kế lại giao thức.

### 13.4. Nhầm mode sau conversion

Sau khi write→read, việc tiếp tục ghi protected state là vi phạm giao thức. Sau read→optimistic, việc gọi `unlockRead` trên stamp cũ là sai. Sau optimistic→write, việc chỉ `validate` mà không `unlockWrite` là rò write lock. Quản lý vòng đời stamp nhất quán quan trọng hơn sự ngắn gọn của cú pháp.

### 13.5. Tin rằng mọi conversion thành công nếu lock “có vẻ rảnh”

`try` là best effort, không hứa fairness hoặc đợi đến khi khả dụng. Một lần trả zero không chứng minh có writer đang giữ lock ngay tại đúng lúc bạn log. Không xây business logic dựa vào suy diễn từ zero mà không có đồng bộ.

## 14. Phân biệt với ReentrantReadWriteLock và các lựa chọn khác

| Tiêu chí | StampedLock | ReentrantReadWriteLock |
|---|---|---|
| Có stamp xác định mode/version | Có | Không |
| Optimistic read | Có | Không |
| Chuyển read→write bằng tryConvert | Có, thành công có điều kiện | Không có cùng API conversion trực tiếp |
| Write→read downgrade | Có qua tryConvertToReadLock | Có thể giữ read rồi nhả write theo mẫu của lock reentrant |
| Reentrant | Không | Có đối với các mode được định nghĩa |
| Fairness tùy chọn | Không có policy đảm bảo như fair constructor | Có constructor fair/nonfair |
| Condition trên write view | Không hỗ trợ kiểu đó theo StampedLock | WriteLock cung cấp Condition |
| API Lock/ReadWriteLock trực tiếp | Không trực tiếp; có adapter views | Có |

Chọn StampedLock khi có **dữ liệu nội bộ đơn giản, nhiều đọc, optimistic read có thể validate an toàn, và conversion phù hợp**. Nếu code có nhiều lời gọi đan nhau cần reentrancy, hoặc cần Condition, cân nhắc loại lock khác. Không tối ưu quá sớm: `synchronized` vẫn đúng và phù hợp cho nhiều critical section ngắn.

### 14.1. Views không đem lại chuyển mode

`asReadLock()`, `asWriteLock()` và `asReadWriteLock()` cung cấp các adapter theo interface Lock/ReadWriteLock ở những trường hợp chỉ cần thao tác mode tương ứng. Chúng không biến StampedLock thành reentrant và không thay thế các method có stamp. Nếu cần conversion, dùng API StampedLock trực tiếp.

## 15. Lỗi thường gặp

**1. Coi StampedLock reentrant.** Có thể tự deadlock khi xin lại lock trong critical section.

**2. Coi tryConvertToWriteLock luôn nâng cấp được read.** Có reader khác thì không thể có write độc quyền ngay.

**3. Ghi đè stamp cũ bằng 0 khi conversion thất bại.** Gây leak read lock và unlock sai.

**4. Unlock read sau khi đã đổi thành write.** Stamp cũ không còn đại diện read hold.

**5. Dùng unlockWrite cho read stamp.** Sai mode, có thể ném IllegalMonitorStateException.

**6. Unlock một optimistic stamp.** Optimistic là observation chứ không phải lock hold.

**7. Đọc điều kiện trước khi nhả read rồi không kiểm lại sau khi xin write.** Writer khác có thể chen trong khoảng trống.

**8. Gọi writeLock trong khi vẫn giữ read.** Tự làm kẹt nếu writer cần đọc lock cũ được giải phóng.

**9. Busy spin conversion vô hạn.** Không có fairness, tốn CPU và có thể không tiến triển.

**10. Không kiểm zero từ tryOptimisticRead.** Nếu writer đang giữ quyền, stamp bằng 0 phải fallback.

**11. Dùng validate(true) như một read lock còn giữ.** Writer có thể xuất hiện ngay sau validation.

**12. Dùng optimistic read để duyệt mutable collection không an toàn.** Code có thể gặp trạng thái “wildly inconsistent” trước khi validate.

**13. Ghi dữ liệu chỉ sau validate.** Cần write stamp thật, không chỉ observation.

**14. Giữ write lock khi gọi network/database.** Kéo dài thời gian chặn mọi reader/writer.

**15. Không đặt unlock trong finally.** Exception giữa chừng có thể rò lock.

**16. Dùng một stamp cho hai StampedLock.** Stamp có hiệu lực với đúng lock và trạng thái.

**17. Hiểu isReadLockStamp là xác nhận runtime ownership.** Chỉ phân loại stamp, không phải kiểm quyền chưa bị nhả.

**18. Cho rằng tryConvertToWriteLock có timeout.** API thử ngay; timed acquisition là method khác.

**19. Không xử lý InterruptedException khi dùng interruptible read/write.** Có thể rò stamp cũ nếu nhả/đổi không đúng nhánh.

**20. Tin StampedLock công bằng giữa reader và writer.** Không có chính sách ưu tiên cố định.

**21. Tự in/ghi stamp số để dự đoán version.** Giá trị stamp là chi tiết API, không phải ID business.

**22. Quên rằng isXxxStamp helpers có từ Java 10.** Nếu build thực sự nhắm Java 8, không sử dụng helper chưa tồn tại; dùng unlock logic khác.

**23. Không giữ cùng một lock để bảo vệ tất cả writer.** Optimistic validate không còn bảo vệ được invariant nếu dữ liệu bị sửa ngoài protocol.

**24. Không kiểm thử nhánh conversion thất bại.** Code chạy trong môi trường ít reader thường chỉ đi qua nhánh thành công; fallback có thể chứa race/lock leak chưa thấy.

## 16. Bài tập thực hành

1. StampedLock có mấy mode? Optimistic read có phải read lock thật không?
2. `tryConvertToWriteLock` trả gì khi read stamp hợp lệ và không có reader khác?
3. Khi reader thứ hai còn giữ lock, conversion read→write trả gì và stamp cũ thế nào?
4. Vì sao không thể gọi writeLock chờ trong lúc vẫn giữ read?
5. Nêu lỗi khi viết `stamp = tryConvertToWriteLock(stamp)` mà không giữ bản cũ.
6. Sau read→write thành công, phải unlock bằng mode nào?
7. Sau write→read, còn được thay protected state không?
8. Sau read→optimistic thành công, có cần unlockRead cũ không?
9. Khi optimistic stamp đã bị writer invalidate, phải làm gì nếu cần đọc?
10. `validate(stamp)==true` có cho phép ghi không?
11. Vì sao phải kiểm điều kiện sau fallback unlockRead rồi writeLock?
12. `tryConvertToWriteLock` có chờ đến khi reader khác nhả không?
13. Khi cần timeout/interrupt để xin write, dùng API nào?
14. Vì sao `isWriteLockStamp` không thể thay `validate` cho optimistic observation?
15. Khi đọc mutable ArrayList, optimistic read có thể nguy hiểm thế nào?
16. Trong test, làm sao ép conversion thất bại đáng tin mà không dùng sleep?
17. Khi nào write→read downgrade hơn nhả write rồi lấy read?
18. Vì sao StampedLock không phù hợp để giữ lock trong lúc gọi callback tùy ý?
19. Chọn StampedLock hay ReentrantReadWriteLock nếu cần reentrancy/Condition?
20. Nếu một optimistic stamp hợp lệ rồi writer mới lấy lock sau validate, bản sao dữ liệu đã đọc còn dùng được không?

**Gợi ý đáp án:** (1) Write/read/optimistic; optimistic không khóa. (2) Có thể trả write stamp khác 0 khi khả dụng. (3) Trả 0; read stamp cũ vẫn giữ read. (4) Không reentrant, có thể tự deadlock. (5) Mất handle để unlock read khi conversion trả 0. (6) Write stamp mới, dùng unlockWrite hoặc unlock(stamp). (7) Không, hiện chỉ giữ read. (8) Không, read hold đã được nhả. (9) Dùng readLock rồi đọc lại/validate theo giao thức. (10) Không, phải có write lock. (11) Writer có thể chen vào khoảng trống. (12) Không, đó là try ngay. (13) writeLockInterruptibly hoặc tryWriteLock(timeout,TimeUnit) sau khi xử lý read stamp. (14) Nó chỉ phân loại stamp; optimistic cần validate version. (15) Có thể gặp dữ liệu không nhất quán hoặc exception trước validation. (16) Dùng CountDownLatch cho reader thứ hai. (17) Tránh writer khác chen giữa. (18) Callback có thể tự xin lock/call I/O chặn. (19) ReentrantReadWriteLock hoặc cơ chế phù hợp khác. (20) Có thể dùng bản sao local đã validate, nhưng không đọc lại protected state và cho rằng không đổi sau validate.

## Tổng kết

`tryConvertToWriteLock` là phép **nâng cấp có điều kiện**, không phải lệnh đợi đến khi có write lock. Thành công tạo write stamp mới và thay quyền giữ read/optimistic theo mode đầu; thất bại trả 0 và **không cấp write lock**. Đối với read stamp thất bại, phải tiếp tục quản lý và nhả quyền read cũ. Nếu nhả read rồi xin write, **luôn đọc lại điều kiện** dưới write vì dữ liệu có thể đổi ở khoảng trống. `tryConvertToReadLock` giúp downgrade write→read nguyên tử; `tryConvertToOptimisticRead` nhả lock thành observation stamp, phải validate trước khi dùng dữ liệu đọc optimistic. StampedLock không reentrant và không cam kết fairness, nên vòng đời stamp, finally, kiểm contention và chọn đúng cơ chế đồng bộ quan trọng hơn việc viết ngắn vài dòng code.

### Tài liệu chính thức (API còn hiệu lực)

- [Oracle Java SE 26 — StampedLock (conversion, optimistic read, API và ví dụ chính thức)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
- [Oracle Java SE 26 — ReadWriteLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html)
- [Oracle Java SE 26 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java Language Specification — Memory Model](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html)
