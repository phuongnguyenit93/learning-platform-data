# StampedLock trong Java: khóa đọc, khóa ghi và đọc lạc quan

## 1. `StampedLock` giải quyết bài toán gì?

`java.util.concurrent.locks.StampedLock` được giới thiệu trong **Java 8** và vẫn được duy trì trên các JDK hiện đại. Nó hỗ trợ phối hợp nhiều thread cùng truy cập một trạng thái có thể thay đổi: **nhiều người đọc** có thể cùng làm việc, nhưng **người ghi** cần quyền độc quyền. Điểm khác biệt quan trọng so với khóa đọc–ghi truyền thống là **đọc lạc quan** (*optimistic reading*), một cách thử đọc dữ liệu mà không giữ read lock thực sự, sau đó kiểm tra có writer nào can thiệp hay không.

Ba chế độ chính:

1. **Write lock (ghi độc quyền):** `writeLock()` chặn các read/write lock khác trong lúc writer cập nhật trạng thái, và làm các lượt optimistic read có phiên bản trước khi ghi trở nên không hợp lệ.
2. **Read lock (đọc chia sẻ):** `readLock()` bảo vệ dữ liệu khỏi writer trong thời gian đọc; nhiều reader có thể cùng giữ read lock.
3. **Optimistic read (đọc lạc quan):** `tryOptimisticRead()` trả một **stamp quan sát** khi không có write lock đang giữ; reader sao chép những trường thích hợp vào biến local và **bắt buộc `validate(stamp)` trước khi tin kết quả**. Nó không hề khóa writer.

Sử dụng thích hợp: một đối tượng trạng thái nhỏ có **đọc rất thường xuyên, ghi tương đối ít**, ví dụ tọa độ `(x,y)`, thống kê vài trường hoặc cấu hình số học đơn giản. Nó không phải giải pháp mặc định tốt nhất cho mọi chương trình đồng thời: mã dễ sai khi optimistic read chạm tới cấu trúc mutable phức tạp hoặc bỏ qua kiểm tra phiên bản.

### 1.1. Bảng quyết định nhanh

| Yêu cầu | API | Có giữ khóa? | Có chặn writer trong thời gian đọc? |
| --- | --- | --- | --- |
| Cập nhật nhiều trường nhất quán | `writeLock()` + `unlockWrite(stamp)` | Có, độc quyền | Có |
| Đọc nhiều trường cần snapshot ổn định | `readLock()` + `unlockRead(stamp)` | Có, chia sẻ | Có |
| Đọc vài trường đơn giản, chấp nhận đọc lại nếu có writer | `tryOptimisticRead()` + `validate(stamp)`; fallback `readLock()` | **Không** ở bước optimistic | **Không** |
| Không được chờ khóa | `tryReadLock()`, `tryWriteLock()` | Chỉ khi thành công | Tùy mode |
| Muốn chờ tối đa một khoảng và hỗ trợ interrupt | `tryReadLock(timeout,unit)` / `tryWriteLock(timeout,unit)` | Chỉ khi thành công | Tùy mode |
| Muốn thay đổi mode đang giữ | `tryConvertToWriteLock`, `tryConvertToReadLock`, `tryConvertToOptimisticRead` | Có thể chuyển hoặc nhả | Phụ thuộc stamp trả về |

**Phân biệt quan trọng:** StampedLock **không triển khai trực tiếp `Lock` hoặc `ReadWriteLock`**, dù có các adapter như `asReadLock()`/`asWriteLock()`/`asReadWriteLock()`. Nó dùng một cơ chế **stamp** với quy tắc riêng, và **không reentrant** như `ReentrantReadWriteLock`.

## 2. Stamp là gì? Vì sao không thể bỏ qua?

Mọi phương thức lấy khóa/đọc lạc quan đều trả **`long stamp`**: một mã đại diện cho **phiên bản + chế độ** của trạng thái lock. Các hàm nhả khóa và chuyển mode nhận lại stamp để xác nhận thao tác tương ứng.

```java
StampedLock lock = new StampedLock();

long stamp = lock.readLock();
try {
    // Đọc những trường được bảo vệ.
} finally {
    lock.unlockRead(stamp);
}
```

Đây là snippet trong method; cần `import java.util.concurrent.locks.StampedLock;`. Không dùng `unlockRead()` không có tham số như một hình thức thông thường: **chính stamp đã nhận** là capability để nhả đúng chế độ.

Các ý nghĩa cần nhớ:

- Stamp thành công của `readLock()`/`writeLock()` là stamp để nhả đúng mode.
- Các hàm `tryReadLock()`, `tryWriteLock()` có thể trả **`0L`** nếu không lấy được khóa; trong trường hợp này **không được unlock**.
- `tryOptimisticRead()` cũng có thể trả **`0L`** khi writer đang giữ write lock; stamp 0 không thể được validate thành công.
- **Không tự tạo, tăng, so sánh số học hoặc tái sử dụng stamp cũ**. Ý nghĩa số bit là chi tiết triển khai; không coi giá trị stamp là ID thread hay timestamp.
- Khi chuyển khóa thành công, dùng **stamp mới** trả về để tiếp tục và unlock. Stamp cũ không còn đúng hợp đồng cho lock đã chuyển mode.
- `unlockRead(stamp)`, `unlockWrite(stamp)` hoặc `unlock(stamp)` có thể ném `IllegalMonitorStateException` nếu stamp không khớp mode/trạng thái cần nhả.

### 2.1. Stamp không phải “người sở hữu khóa”

Khác các khóa `Lock` phổ biến, `StampedLock` không gắn quyền sở hữu vào một thread nhất định. Một thread có thể nhận stamp, sau đó chuyển khả năng nhả/chuyển lock cho thread khác theo một giao thức ứng dụng được thiết kế cẩn thận. Nhưng tính năng này **không có nghĩa việc chia sẻ stamp tùy tiện là an toàn**. Nếu hai thread cùng giữ bản sao stamp và đều cố unlock, một thread có thể nhả thành công còn thread kia gặp lỗi; hoặc protocol sẽ cho kết quả sai.

**Quy tắc thực tế:** giữ stamp trong phạm vi thao tác nhỏ, chỉ một đường chịu trách nhiệm nhả và dùng `try/finally`. Không lưu stamp như một token có thể dùng mãi hay một mật khẩu để trao đổi qua mạng.

### 2.2. StampedLock không reentrant

Một thread đã giữ write lock mà tiếp tục gọi `writeLock()` hoặc `readLock()` có thể **tự chờ vô hạn**, vì lock này không theo dõi ownership theo thread và không tự cấp lại khóa đang giữ.

```java
long stamp = lock.writeLock();
try {
    // KHÔNG gọi một method khác cũng gọi lock.writeLock()
    // hoặc lock.readLock() trên chính lock này.
} finally {
    lock.unlockWrite(stamp);
}
```

Đây là snippet minh họa, không chạy lời gọi nested lock nguy hiểm. Với mã có method lồng nhau, tách helper **không tự khóa** để gọi dưới khóa đã giữ, hoặc chọn cơ chế reentrant nếu thiết kế thật sự cần.

Việc có thể có nhiều read stamp trong hệ thống **không biến StampedLock thành khóa reentrant**. Không phụ thuộc vào hành vi lấy khóa lặp từ chính thread đang giữ khóa.

## 3. Ghi độc quyền: `writeLock()` và `unlockWrite(stamp)`

Bất kỳ đoạn mã nào **thay đổi trạng thái chung cần nhất quán** phải tuân theo giao thức write lock tương ứng. Ví dụ đối tượng có hai trường `x`/`y` đại diện một vị trí: cập nhật cả hai cần thực hiện trong **cùng một vùng bảo vệ**.

```java
final class MutablePoint {
    private final StampedLock lock = new StampedLock();
    private double x;
    private double y;

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
```

Đây là snippet class, không có `main`; chương trình hoàn chỉnh ở mục 12. Dưới write lock, reader đang giữ read lock phải hoàn tất mới đến lượt writer; khi writer giữ write lock thì một lời gọi `tryReadLock()` tức thời thường trả `0L`, và `tryOptimisticRead()` trả `0L`.

### 3.1. Write lock không tự bao phủ các đường ghi bỏ qua giao thức

Nếu một thread khác thực hiện `point.x = ...` trực tiếp mà **không lấy cùng khóa**, `StampedLock` không thể ngăn nó. Tất cả method sửa dữ liệu được bảo vệ phải đi qua cùng giao thức, hoặc giữ dữ liệu `private` trong object có API nhất quán.

Có một writer dùng khóa, trong khi một writer khác không dùng khóa, có thể khiến optimistic validation vẫn trả true dù đã có ghi không được bảo vệ. Vì vậy **`validate` không phải thiết bị tự phát hiện mọi phép ghi vào bộ nhớ** — nó chỉ phát hiện thay đổi chế độ write lock tương ứng.

### 3.2. `try/finally` là bắt buộc trong vùng khóa thông thường

Nếu phép cập nhật ném `RuntimeException`, dùng `finally` giúp nhả khóa và tránh chặn mọi reader/writer khác.

```java
long stamp = lock.writeLock();
try {
    updateSharedState();
} finally {
    lock.unlockWrite(stamp);
}
```

Snippet dùng method `updateSharedState` do ứng dụng định nghĩa. Nếu phép cập nhật nhiều bước ném lỗi giữa chừng, việc nhả khóa **không tự rollback dữ liệu**. Khóa chỉ quản lý truy cập đồng thời; tính toàn vẹn nghiệp vụ khi lỗi cần cách thiết kế update/transaction phù hợp.

### 3.3. Write lock là độc quyền, không bảo đảm công bằng

`StampedLock` không có một chính sách nhất quán luôn ưu tiên reader hoặc writer. Các thread có thể chờ lâu nếu có contention hoặc starvation. Đừng dùng lớp này như giải pháp fairness hay deadline chính xác nếu chưa đo và thiết kế các điều kiện hủy/chờ tương ứng.

## 4. Đọc có khóa: `readLock()` và `unlockRead(stamp)`

`readLock()` cho phép các reader cùng đọc, nhưng không cho writer thay đổi trạng thái được bảo vệ trong lúc reader giữ khóa.

```java
double distanceWithReadLock() {
    long stamp = lock.readLock();
    try {
        return Math.hypot(x, y);
    } finally {
        lock.unlockRead(stamp);
    }
}
```

Snippet này là method bên trong một class có các trường `x`, `y` và `lock`. Không dùng nó đứng riêng ngoài class. Phép `Math.hypot` chỉ tiêu thụ hai giá trị `double`; với code đọc một cấu trúc mutable phức tạp, cần bảo vệ cả những bước đọc/copy liên quan trong cùng read-lock.

### 4.1. Đọc phải giữ cùng khóa đủ lâu để tạo kết quả nhất quán

Cách làm dễ sai:

```java
double readX() {
    long stamp = lock.readLock();
    try {
        return x;
    } finally {
        lock.unlockRead(stamp);
    }
}

double readY() {
    long stamp = lock.readLock();
    try {
        return y;
    } finally {
        lock.unlockRead(stamp);
    }
}

// Nếu caller gọi readX() rồi readY(), writer có thể
// thay đổi cả hai trường giữa hai lời gọi.
```

Đây là các method snippet. Mỗi method đọc đúng một trường, nhưng **hai lời gọi tách biệt không tạo snapshot nguyên tử của cặp x/y**. Nếu business cần hai giá trị thuộc một trạng thái, hãy cung cấp một method chụp chúng **trong cùng read lock** hoặc một optimistic read **được validate**.

### 4.2. Đọc có khóa an toàn hơn đọc lạc quan cho object graph phức tạp

Khi đọc `Map`, `List`, array có thể được thay cấu trúc, hoặc điều hướng object mutable nhiều cấp, phương pháp read-lock rõ ràng hơn. Chỉ chuyển sang optimistic read khi bạn hiểu rõ giới hạn an toàn của từng bước copy và đã đo được lợi ích trong workload thật.

## 5. Đọc lạc quan: `tryOptimisticRead()` rồi `validate(stamp)`

Điểm đáng học nhất của `StampedLock` là một lần đọc **không lấy read lock**:

```java
double distanceOptimistic() {
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
    return Math.hypot(localX, localY);
}
```

Đây là method snippet trong class có `x`, `y`, `lock`. Các bước:

1. `tryOptimisticRead` lấy **một dấu phiên bản quan sát**, không giữ khóa.
2. **Sao chép trực tiếp** các trường đơn giản vào biến local; **không dùng chúng để tạo side effect** trong lúc chưa validate.
3. `validate(stamp)` kiểm tra writer có nhận write lock kể từ stamp đó hay không.
4. Nếu **true**, dùng dữ liệu đã copy; writer có thể chạy **sau khi validate**, nhưng không làm thay đổi các biến local đã chụp.
5. Nếu **false**, **bỏ dữ liệu optimistic đã đọc** và **đọc lại** dưới `readLock()` thật.
6. Chỉ khi đã có snapshot hợp lệ mới dùng `Math.hypot`.

### 5.1. `tryOptimisticRead() != 0` chưa chứng minh dữ liệu đúng

`tryOptimisticRead()` trả stamp khác 0 khi tại thời điểm gọi không có write lock đang giữ. Sau đó writer **có thể lập tức lấy write lock** và sửa nhiều trường trước hoặc giữa các phép đọc của reader.

```text
Reader                         Writer
------                         ------
s = tryOptimisticRead()
read x = x_old
                               writeLock()
                               x = x_new
                               y = y_new
                               unlockWrite()
read y = y_new
validate(s) -> FALSE
bỏ x_old/y_new
readLock(), đọc lại x/y
unlockRead(), dùng snapshot mới
```

Việc dữ liệu x/y bị pha trộn là **lý do phải validate**. Không hợp thức hóa dữ liệu bằng cách chỉ kiểm tra `stamp != 0`.

### 5.2. Nếu writer đang giữ write lock, stamp optimistic có thể bằng 0

Khi `writeLock` đang được giữ, `tryOptimisticRead()` trả `0L`; `validate(0L)` luôn trả `false`. Mẫu `if (!validate(stamp)) { readLock ... }` nêu trên đã tự xử lý cả tình huống này.

Có thể tối ưu tránh copy khi `stamp == 0L`, nhưng trong mọi trường hợp vẫn cần đường fallback. Không dùng `unlockRead(stamp)` cho stamp optimistic: **optimistic read không lấy read lock nên không có gì để unlock**.

### 5.3. Tại sao đặt `validate` sau các phép đọc?

Nếu validate **trước** khi đọc, writer có thể can thiệp ngay sau validate. Ví dụ:

```java
// SAI: xác thực phiên bản trước khi chụp dữ liệu.
long stamp = lock.tryOptimisticRead();
boolean seemsValid = lock.validate(stamp);
double a = x;
double b = y;
// seemsValid không chứng minh a,b là một snapshot nhất quán.
```

Với đọc lạc quan, thứ tự đúng là **stamp → copy vào locals → validate → sử dụng**. Nếu sau validate vẫn tiếp tục đọc object shared, các bước đọc thêm đó chưa được bảo vệ bằng validation cũ; cần copy hết dữ liệu cần dùng **trước** kiểm tra hoặc thiết kế vòng kiểm tra mới phù hợp.

### 5.4. Khi `validate` trả true, có được xem đó là khóa đang giữ không?

**Không.** `validate(stamp)` chỉ xác nhận không có writer lấy write lock trong khoảng cần kiểm tra; nó **không cấp read lock** và không bảo đảm ngăn writer tiếp theo. Phương pháp đúng là **chụp dữ liệu cần thiết** vào locals rồi kiểm tra, không trả một tham chiếu mutable và giả định dữ liệu sẽ không đổi khi consumer sử dụng sau đó.

## 6. Giới hạn an toàn bộ nhớ của optimistic read

Javadoc hiện hành nhấn mạnh các lượt đọc lạc quan có thể thấy dữ liệu **không nhất quán mạnh** nếu writer đang chạy. Phương pháp này chỉ thích hợp khi bạn hiểu rõ biểu diễn dữ liệu và có thể kiểm chứng tính hợp lệ.

### 6.1. An toàn hơn với trường primitive đơn giản

Ví dụ hai trường `double x, y` được cập nhật cùng write lock:

```java
long stamp = lock.tryOptimisticRead();
double localX = x;
double localY = y;
if (!lock.validate(stamp)) {
    // Bỏ cả hai giá trị và lấy lại dưới readLock().
}
```

Kết quả chưa được sử dụng trước khi validate; nếu có writer xen vào, reader không được coi hai biến local như một điểm hợp lệ. Kế hoạch fallback chịu trách nhiệm khôi phục snapshot nhất quán.

### 6.2. Cẩn thận dereference và gọi method trên object mutable

Ví dụ **không nên** làm dưới optimistic read nếu `list` có thể bị writer thay thế hoặc sửa cấu trúc:

```java
long stamp = lock.tryOptimisticRead();
// Có thể ném exception do list thay đổi đồng thời:
// int result = list.get(index).getSomething();
// if (lock.validate(stamp)) use(result);
```

Đây là snippet minh họa anti-pattern, không phải code chạy độc lập. `validate` ở cuối **không thể đảo ngược** `NullPointerException`, `IndexOutOfBoundsException` hoặc một side effect đã xảy ra trong quá trình dereference. Đặc biệt, đừng gọi method **có tác dụng phụ** hoặc duyệt một cấu trúc mutable phức tạp dưới optimistic read rồi hy vọng validate sẽ “rollback”.

Giải pháp thường an toàn hơn:

- Dùng `readLock()` cho toàn bộ thao tác có nhiều dereference liên tiếp.
- Dùng một **immutable snapshot object** và cập nhật tham chiếu snapshot có kiểm soát; reader chỉ dùng một bản immutable.
- Nếu cần optimistic read với nhiều trường/reference, thiết kế quy trình từng bước, kiểm tra phù hợp và chỉ tính toán sau validation theo hợp đồng dữ liệu.

### 6.3. Khóa chỉ bảo vệ các ghi tuân thủ giao thức

Một writer bỏ qua `writeLock()` vẫn có thể làm dữ liệu thay đổi mà `validate` không biết. Toàn bộ truy cập shared state phải được thống nhất một kỷ luật: giá trị mutable mà nhiều thread sửa trực tiếp không được bảo vệ chỉ bởi một số reader dùng StampedLock.

## 7. Phương thức `tryReadLock` và `tryWriteLock`

Đôi khi caller **không muốn bị chặn vô hạn**. Dùng:

```java
long stamp = lock.tryWriteLock();
if (stamp == 0L) {
    // Không lấy được write lock ngay; thử lại/sắp lịch xử lý khác.
} else {
    try {
        updateSharedState();
    } finally {
        lock.unlockWrite(stamp);
    }
}
```

Đây là snippet với method `updateSharedState` do ứng dụng định nghĩa. Không được gọi `unlockWrite(0L)` vì không giữ write lock.

### 7.1. Bản chờ có thời hạn và hỗ trợ interrupt

```java
long stamp = lock.tryReadLock(200, TimeUnit.MILLISECONDS);
if (stamp == 0L) {
    // Không lấy được read lock trong cửa sổ 200ms.
} else {
    try {
        inspectSharedState();
    } finally {
        lock.unlockRead(stamp);
    }
}
```

Đây là snippet trong method có `throws InterruptedException` hoặc bắt `InterruptedException` phù hợp; cần import `TimeUnit`. Cặp API `tryReadLock(timeout,unit)` và `tryWriteLock(timeout,unit)` chờ tối đa theo hợp đồng, và **có thể bị interrupt**.

- `readLock()` và `writeLock()` thường chờ theo dạng **không interruptible**.
- `readLockInterruptibly()` và `writeLockInterruptibly()` cho phép dừng chờ nếu thread bị interrupt.
- `tryReadLock()`/`tryWriteLock()` không tham số **thử ngay**; thất bại trả 0.
- `tryReadLock(timeout,unit)`/`tryWriteLock(timeout,unit)` có thể chờ và ném `InterruptedException`.

Nếu đang xử lý interruption, chọn chính sách lan truyền hoặc khôi phục interrupt flag phù hợp; không lặng lẽ nuốt `InterruptedException` rồi tiếp tục chờ vô hạn.

### 7.2. `0L` không chỉ ra một nguyên nhân duy nhất

Một lời gọi `try...` trả 0 có nghĩa **thử lần này không lấy được khóa/không chuyển được mode**. Nó không chứng minh writer nhất định đang giữ khóa ở mọi trường hợp hay cam kết retry ngay lập tức sẽ thành công. `StampedLock` không có fairness guarantee; thiết kế retry cần giới hạn, backoff hoặc timeout phù hợp.

## 8. Chuyển mode: nâng hoặc hạ cấp với `tryConvertTo...`

`StampedLock` cho phép **thử chuyển** một stamp giữa các mode mà không nhất thiết phải nhả rồi lấy lại khóa. Ba API chính:

- `tryConvertToWriteLock(stamp)`: thử lấy write stamp từ write/read/optimistic stamp nếu điều kiện cho phép.
- `tryConvertToReadLock(stamp)`: thử lấy read stamp từ một stamp phù hợp; dùng để **downgrade** write → read.
- `tryConvertToOptimisticRead(stamp)`: thử đổi read/write lock thành một dấu quan sát, **nhả khóa đang giữ** nếu chuyển thành công.

Mỗi phép chuyển **có thể trả `0L` khi thất bại**. Khi thành công, cập nhật biến stamp thành **giá trị mới** và unlock theo **mode mới**. Khi thất bại, xử lý trạng thái cũ theo hợp đồng; không giả định phương thức tự chờ đến lúc chuyển được.

### 8.1. Nâng read → write không phải lúc nào thành công

Một reader muốn thay đổi shared state có thể thử:

```java
long stamp = lock.readLock();
try {
    long writeStamp = lock.tryConvertToWriteLock(stamp);
    if (writeStamp != 0L) {
        stamp = writeStamp;  // chuyển mode thành công
        modifySharedState();
    } else {
        // Vẫn giữ read lock cũ; cần thiết kế đường fallback.
    }
} finally {
    lock.unlock(stamp);
}
```

Đây là **snippet minh họa** với `modifySharedState` do ứng dụng định nghĩa. `unlock(stamp)` tự nhả mode mà stamp đại diện. Nếu chuyển thành công thì stamp là write; nếu thất bại, stamp vẫn là read.

**Quan trọng:** Không gọi `writeLock()` trong lúc vẫn giữ read lock và chờ nó “tự nâng cấp” — có nguy cơ chặn vì chính read lock đang giữ ngăn writer.

### 8.2. Nếu chuyển thất bại, nhả read rồi lấy write phải kiểm tra lại điều kiện

Ví dụ chỉ muốn đặt tọa độ nếu còn ở gốc `(0,0)`:

```java
boolean moveIfAtOrigin(double newX, double newY) {
    long stamp = lock.readLock();
    try {
        while (x == 0.0 && y == 0.0) {
            long writeStamp = lock.tryConvertToWriteLock(stamp);
            if (writeStamp != 0L) {
                stamp = writeStamp;
                x = newX;
                y = newY;
                return true;
            }
            lock.unlockRead(stamp);
            stamp = lock.writeLock();
            // Bắt buộc kiểm tra lại x,y trong vòng while
            // vì writer khác có thể cập nhật giữa nhả và lấy.
        }
        return false;
    } finally {
        lock.unlock(stamp);
    }
}
```

Đây là method trong class có `x`, `y`, `lock`; đã được đưa vào chương trình runnable ở mục 12. Sau khi nhả read lock và lấy lại write lock, **không được tin điều kiện đã đọc trước đó**. Vòng `while` kiểm tra lại dữ liệu dưới stamp hiện tại. Mọi đường đi đều nhả đúng stamp cuối bằng `unlock(stamp)`.

### 8.3. Hạ write → read mà không mở khoảng trống ghi

```java
long writeStamp = lock.writeLock();
long readStamp = lock.tryConvertToReadLock(writeStamp);
if (readStamp == 0L) {
    lock.unlockWrite(writeStamp);
    throw new IllegalStateException("Cannot downgrade");
}
try {
    // Giữ read lock mới, writer khác chưa được phép ghi.
} finally {
    lock.unlockRead(readStamp);
}
```

Snippet này minh họa **chuyển thành công** và xử lý nhánh fail. Đổi từ write sang read giúp tiếp tục đọc sau khi sửa, trong khi cho phép các reader khác tham gia. Đây không phải cấp phát một **read lock bổ sung** song song với write lock cũ: chuyển mode thành công làm stamp cũ không còn thích hợp để unlock.

### 8.4. Chuyển thành optimistic read sẽ nhả khóa

`tryConvertToOptimisticRead(stamp)` có thể giải phóng read/write lock và trả một stamp quan sát. Sau khi chuyển, không được gọi `unlockRead`/`unlockWrite` với stamp cũ. Cũng không có gì để unlock cho stamp optimistic. Muốn dùng dữ liệu đọc tiếp theo, vẫn phải theo quy trình **copy → validate**.

## 9. Non-reentrant, không Conditions và các adapter

`StampedLock` không phải một biến thể drop-in của mọi lock khác:

- **Không reentrant:** method đang giữ khóa không được gọi lồng vào method cũng lấy chính khóa đó theo giả định có ownership.
- **Không hỗ trợ `Condition` trên các view lock:** đừng dùng nó làm thay thế trực tiếp cho một `ReentrantLock` cần `newCondition()/await()/signal()`.
- **Không đảm bảo fairness:** với contention, reader hoặc writer có thể bị đói.
- **Không có thread ownership:** stamp là capability, không phải một cặp “thread này đã khóa” được runtime theo dõi như `ReentrantLock`.
- **Có adapter `asReadLock()`, `asWriteLock()`, `asReadWriteLock()`**, nhưng chúng vẫn kế thừa các giới hạn của StampedLock và không tự thêm reentrancy hay fairness.

Nếu codebase đã thiết kế sâu xung quanh `Lock`/`Condition`, hoặc cần đệ quy/reentrant locking, hãy xem lại yêu cầu trước khi đưa `StampedLock` vào.

## 10. Đồng bộ bộ nhớ và giới hạn của `validate`

Trong Java Memory Model, lấy/nhả khóa thành công cung cấp các bảo đảm đồng bộ tương ứng với thao tác lock/unlock. Với optimistic read, bảo đảm về quan hệ **happens-before** từ writer trước đó tới reader chỉ được xác lập theo hợp đồng khi việc `validate(stamp)` thành công. Nếu validation thất bại, các giá trị đọc tạm **không thể coi là snapshot nhất quán** và phải bị bỏ.

### 10.1. Vì sao writer sau validate không làm “hỏng” local copy?

Nếu `localX` và `localY` là các số nguyên thủy đã được chụp trước validation, sau `validate(stamp) == true` ta tính từ các locals ấy. Writer có thể đổi `x/y` gốc **sau khi** validation, nhưng không đổi được nội dung hai biến local đã chụp; kết quả ứng với một quan sát hợp lệ vào thời điểm kiểm tra.

Điều này **không** có nghĩa chúng đại diện trạng thái mới nhất ở thời điểm caller cuối cùng nhận response. Nếu ứng dụng yêu cầu một trạng thái ổn định **trong suốt** thao tác dài hoặc cần quyết định write dựa trên read, dùng khóa phù hợp và cập nhật có điều kiện; optimistic snapshot chỉ hợp với **đọc ngắn**.

### 10.2. Không làm side effect trong khoảng optimistic trước validation

```java
long stamp = lock.tryOptimisticRead();
double a = x;
double b = y;

// SAI: updateDatabase(a, b) trước khi validate.
// Sau đó validate(false) không thể hoàn tác updateDatabase.

if (lock.validate(stamp)) {
    // Bây giờ mới được phép dùng a,b như dữ liệu đã xác thực.
}
```

Đây là snippet minh họa, `updateDatabase` là tên method giả định. Đọc lạc quan có thể buộc **chạy lại phép đọc**, nên những bước chưa được xác thực phải là **read-only**, ngắn, an toàn để lặp; không phát email, cập nhật DB, trừ tiền hoặc gọi API ngoài trên dữ liệu chưa được validate.

## 11. Chiến lược chọn giữa lạc quan và đọc có khóa

Mô hình optimistic không miễn phí: mỗi lần có thể tạo stamp, đọc các trường, gọi `validate` và khi invalid phải lấy `readLock` rồi đọc lại. Nếu writer rất thường xuyên, nhánh fallback xảy ra nhiều và lợi ích sẽ giảm hoặc kém hơn đọc khóa thông thường.

| Đặc trưng | Đọc lạc quan phù hợp? | Lý do |
| --- | --- | --- |
| 2–5 trường primitive, đọc nhiều, write ít | Thường **có thể** | Snapshot ngắn, chi phí đọc lại thấp |
| Cấu trúc mutable nhiều cấp; getter có logic | Thường **không** | Rủi ro đọc nửa cấu trúc trước validation |
| Đọc cần giữ bất biến suốt quá trình xử lý dài | **Không** | Optimistic không giữ lock |
| Lượng ghi cao, contention nhiều | Chỉ sau benchmark | Nhiều invalidation/fallback |
| Cần Condition/reentrancy | **Không** | StampedLock không hỗ trợ |
| Cần truyền quyền đọc cho nhiều thread trong JVM | Đánh giá riêng | Stamp không gắn owner; protocol phức tạp |
| Có thể thay immutable snapshot nguyên tử | Có thể không cần StampedLock | Dùng immutable object + volatile/AtomicReference dễ hơn |
| Đọc một counter | Thường không cần | `AtomicLong`/`LongAdder` hoặc `volatile` tùy ngữ nghĩa |

**Không chọn StampedLock chỉ vì tên “optimistic” nghe nhanh.** Chọn vì thuộc tính dữ liệu, tần suất cập nhật, phương án validation an toàn và kết quả đo hiệu năng thực tế.

## 12. Chương trình Java 8 chạy độc lập: đọc, ghi, optimistic, conversion

Chương trình dưới đây dùng **chỉ API Java 8 vẫn được hỗ trợ hiện nay**. Nó kết hợp một class `Point`, các thao tác lấy/nhả khóa, conversion và một bài kiểm thử thực sự dùng **hai thread** để chứng minh writer làm stamp quan sát trở nên không hợp lệ.

Để stdout có thể kiểm tra **chính xác**, các bước có thứ tự được kiểm soát bằng `CountDownLatch` và `Future.get()`; chương trình không dự đoán thứ tự scheduling hay dùng `Thread.sleep()`.

Tạo file **StampedLockModesDemo.java**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.StampedLock;

public class StampedLockModesDemo {
    static final class Point {
        private final StampedLock lock = new StampedLock();
        private double x;
        private double y;

        void move(double dx, double dy) {
            long stamp = lock.writeLock();
            try {
                x += dx;
                y += dy;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        String snapshot() {
            long stamp = lock.readLock();
            try {
                return "(" + x + "," + y + ")";
            } finally {
                lock.unlockRead(stamp);
            }
        }

        double distance() {
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
            return Math.hypot(localX, localY);
        }

        boolean moveIfAtOrigin(double newX, double newY) {
            long stamp = lock.readLock();
            try {
                while (x == 0.0 && y == 0.0) {
                    long writeStamp = lock.tryConvertToWriteLock(stamp);
                    if (writeStamp != 0L) {
                        stamp = writeStamp;
                        x = newX;
                        y = newY;
                        return true;
                    }
                    lock.unlockRead(stamp);
                    stamp = lock.writeLock();
                }
                return false;
            } finally {
                lock.unlock(stamp);
            }
        }

        long optimisticStamp() {
            return lock.tryOptimisticRead();
        }

        boolean validate(long stamp) {
            return lock.validate(stamp);
        }
    }

    public static void main(String[] args) throws Exception {
        Point point = new Point();
        System.out.println("moveIfAtOrigin first: " +
            point.moveIfAtOrigin(3.0, 4.0));
        System.out.println("moveIfAtOrigin again: " +
            point.moveIfAtOrigin(9.0, 9.0));
        System.out.println("snapshot: " + point.snapshot());
        System.out.println("distance: " + point.distance());

        long before = point.optimisticStamp();
        System.out.println("optimistic stamp available: " + (before != 0L));
        System.out.println("validate before writer: " + point.validate(before));
        point.move(1.0, 1.0);
        System.out.println("validate after writer: " + point.validate(before));
        System.out.println("snapshot after move: " + point.snapshot());
        System.out.println("rounded distance: " +
            Math.round(point.distance() * 1000.0) / 1000.0);

        StampedLock lock = new StampedLock();
        long write = lock.writeLock();
        try {
            System.out.println("write acquired: " + (write != 0L));
            System.out.println("tryRead while writing fails: " +
                (lock.tryReadLock() == 0L));
            System.out.println("optimistic while writing fails: " +
                (lock.tryOptimisticRead() == 0L));
            System.out.println("tryWrite while writing fails: " +
                (lock.tryWriteLock() == 0L));
        } finally {
            lock.unlockWrite(write);
        }

        long read = lock.readLock();
        try {
            System.out.println("read acquired: " + (read != 0L));
            System.out.println("tryWrite while reading fails: " +
                (lock.tryWriteLock() == 0L));
        } finally {
            lock.unlockRead(read);
        }

        long writeForDowngrade = lock.writeLock();
        long downgraded = lock.tryConvertToReadLock(writeForDowngrade);
        if (downgraded == 0L) {
            lock.unlockWrite(writeForDowngrade);
            throw new IllegalStateException("downgrade failed");
        }
        try {
            System.out.println("write-to-read conversion: true");
            System.out.println("tryWrite under downgraded read fails: " +
                (lock.tryWriteLock() == 0L));
        } finally {
            lock.unlockRead(downgraded);
        }

        long readForUpgrade = lock.readLock();
        long upgraded = lock.tryConvertToWriteLock(readForUpgrade);
        if (upgraded == 0L) {
            lock.unlockRead(readForUpgrade);
            throw new IllegalStateException("upgrade failed");
        }
        try {
            System.out.println("read-to-write conversion: true");
        } finally {
            lock.unlockWrite(upgraded);
        }

        long optimisticForUpgrade = lock.tryOptimisticRead();
        long upgradedOptimistic =
            lock.tryConvertToWriteLock(optimisticForUpgrade);
        System.out.println("optimistic-to-write conversion: " +
            (upgradedOptimistic != 0L));
        if (upgradedOptimistic != 0L) {
            lock.unlockWrite(upgradedOptimistic);
        }

        boolean rejected = false;
        try {
            lock.unlockWrite(write);
        } catch (IllegalMonitorStateException expected) {
            rejected = true;
        }
        System.out.println("stale write stamp rejected: " + rejected);

        ExecutorService worker = Executors.newSingleThreadExecutor();
        CountDownLatch sampled = new CountDownLatch(1);
        CountDownLatch releaseValidation = new CountDownLatch(1);
        try {
            Future<Boolean> result = worker.submit(new Callable<Boolean>() {
                @Override
                public Boolean call() throws Exception {
                    long stamp = point.optimisticStamp();
                    sampled.countDown();
                    if (!releaseValidation.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "validation not released");
                    }
                    return point.validate(stamp);
                }
            });
            if (!sampled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("sample not ready");
            }
            point.move(1.0, 0.0);
            releaseValidation.countDown();
            System.out.println("concurrent writer invalidates stamp: " +
                !result.get(5, TimeUnit.SECONDS));
        } finally {
            releaseValidation.countDown();
            worker.shutdownNow();
        }
        System.out.println("snapshot after concurrent writer: " +
            point.snapshot());
    }
}
```

Biên dịch và chạy từ thư mục chứa file, trên JDK có hỗ trợ `--release`:

```bash
javac --release 8 -encoding UTF-8 StampedLockModesDemo.java
java StampedLockModesDemo
```

Trên chính JDK 8, biên dịch bằng `javac -encoding UTF-8 StampedLockModesDemo.java` (không có `--release`). **Stdout chính xác** của chương trình:

```text
moveIfAtOrigin first: true
moveIfAtOrigin again: false
snapshot: (3.0,4.0)
distance: 5.0
optimistic stamp available: true
validate before writer: true
validate after writer: false
snapshot after move: (4.0,5.0)
rounded distance: 6.403
write acquired: true
tryRead while writing fails: true
optimistic while writing fails: true
tryWrite while writing fails: true
read acquired: true
tryWrite while reading fails: true
write-to-read conversion: true
tryWrite under downgraded read fails: true
read-to-write conversion: true
optimistic-to-write conversion: true
stale write stamp rejected: true
concurrent writer invalidates stamp: true
snapshot after concurrent writer: (5.0,5.0)
```

### 12.1. Giải thích kết quả và lựa chọn kiểm thử

- `moveIfAtOrigin(3,4)` đầu tiên lấy read lock và **chuyển được sang write lock**, nên thay đổi điểm từ gốc. Lần thứ hai nhận `false` vì điểm đã khác gốc; không có update thứ hai.
- `snapshot()` dùng read lock nên đọc được `(3,4)` thuộc một trạng thái hợp lệ. `distance()` dùng optimistic read có validate/fallback và cho `5.0`.
- Stamp quan sát trước một lần `move(1,1)` **hợp lệ trước write**, sau write bị invalid. Vì vậy ba kết quả `optimistic available`, `validate before writer` và `validate after writer` lần lượt là `true`, `true`, `false`.
- Sau `move(1,1)`, tọa độ thành `(4,5)` và độ dài Euclid xấp xỉ `6.403` (làm tròn ba chữ số sau dấu thập phân).
- Khi giữ write lock, thử lấy read hoặc write lock tiếp bằng dạng `try` trả 0, và optimistic stamp cũng trả 0. Chương trình **không gọi lại `writeLock()` dạng blocking** khi đã giữ write, để tránh tự chờ vô hạn.
- Khi giữ read lock, `tryWriteLock()` không lấy được khóa; phép kiểm tra không yêu cầu thread scheduling cụ thể.
- `tryConvertToReadLock` hạ một write stamp xuống read stamp; khi read vẫn đang giữ, writer mới không lấy được khóa bằng `tryWriteLock`.
- `tryConvertToWriteLock` nâng read stamp lên write stamp trong tình huống không còn reader khác. Một optimistic stamp mới cũng được chuyển thành write stamp khi khóa đang rảnh.
- Cố `unlockWrite(write)` với **stamp cũ đã nhả** bị từ chối bằng `IllegalMonitorStateException`; code bắt ngoại lệ và chỉ in cờ boolean.
- Trong kiểm thử đa thread, worker lấy optimistic stamp trước khi signal `sampled`, main thực hiện write sau đó rồi mới signal `releaseValidation`. Worker xác minh stamp **sau write**, vì vậy kết quả invalid **không phụ thuộc thứ tự scheduling ngẫu nhiên**.
- `worker.shutdownNow()` đóng executor thử nghiệm. Chương trình không giữ thread nền sau khi hoàn tất.

## 13. Khi nào `StampedLock` mang lại lợi ích thực tế?

### 13.1. Workload đọc nhiều, ghi ít

Với hàng triệu lần đọc một cặp số và chỉ một tỷ lệ nhỏ thao tác ghi, optimistic read có thể giảm số lần cần đọc-lock và tranh chấp giữa các reader. Tuy vậy, lợi ích thực tế phụ thuộc phiên bản JVM, core count, CPU cache, tần suất writer, độ dài critical section và cách code được tối ưu.

### 13.2. Ghi nhiều hoặc đọc quá phức tạp có thể phản tác dụng

Nếu writer xuất hiện thường xuyên, nhiều lượt optimistic copy sẽ không hợp lệ và phải đọc lại dưới read lock. Nếu reader chạm một object graph lớn, rủi ro dữ liệu nửa cập nhật có thể không được xử lý an toàn. Một `ReentrantReadWriteLock` hoặc một snapshot bất biến có thể dễ hiểu và ổn định hơn.

### 13.3. Không chọn chỉ vì một benchmark micro đơn giản

Để so sánh `StampedLock` với `synchronized`, `ReentrantReadWriteLock` hoặc copy-on-write, đo **workload thật**: nhiều tỷ lệ read/write, kích thước critical section, mức contention, p99 latency, chi phí fallback, allocation và số thread.

JMH có thể dùng cho benchmark Java. Không suy ra “StampedLock luôn nhanh hơn” từ một lần `System.nanoTime()` trong vòng lặp không có contention.

## 14. So sánh `StampedLock` với các lựa chọn khác

| Công cụ | Điểm mạnh | Khi phù hợp hơn |
| --- | --- | --- |
| `synchronized` | Đơn giản, tự nhả khi rời monitor, reentrant | Critical section nhỏ, tính đúng quan trọng hơn tối ưu |
| `ReentrantLock` | Reentrant, timeout/interrupt, `Condition` | Cần điều phối điều kiện và ownership theo thread |
| `ReentrantReadWriteLock` | Phân biệt read/write, reentrant, có chế độ fairness | Cần nested lock/read-write protocol rõ |
| `StampedLock` | Read/write lock + optimistic read + mode conversion | Nhiều đọc ngắn, ít ghi, snapshot đơn giản, benchmark tốt |
| `volatile`/`AtomicReference<ImmutableState>` | Đọc tham chiếu snapshot đơn giản | Có thể thay nguyên trạng thái bất biến |
| `AtomicInteger`/`AtomicLong` | Biến đơn lẻ atomic, API cập nhật mạnh | Chỉ cần một giá trị |
| `LongAdder` | Cộng số dưới contention tốt | Counter thống kê không cần snapshot nguyên tử từng lần |
| `ConcurrentHashMap` | Truy cập/cập nhật từng key concurrent | Dữ liệu có cấu trúc key-value, không phải một object nhỏ nhiều trường cần đọc cùng lúc |

Không thay `ConcurrentHashMap` bằng `HashMap` rồi nghĩ chỉ thêm một `StampedLock` là luôn đúng: mọi đường cập nhật/duyệt, snapshot và API trả view đều phải tuân thủ cùng khóa. Với map có truy cập theo key, `ConcurrentHashMap` thường là lựa chọn phù hợp hơn.

### 14.1. Immutable snapshot có thể đơn giản hơn optimistic read

Một cách khác với dữ liệu nhỏ:

```java
final class Coordinates {
    final double x;
    final double y;
    Coordinates(double x, double y) {
        this.x = x;
        this.y = y;
    }
}

private volatile Coordinates current = new Coordinates(0, 0);
```

Đây là **snippet class + field**; field `current` phải nằm trong một class chứa thích hợp, không đặt tự do ngoài class. Nếu writer thay toàn bộ object tham chiếu theo một giao thức cập nhật đã định nghĩa, reader đọc **một tham chiếu immutable** rồi dùng hai trường thuộc cùng snapshot. Cách này tránh `validate`, nhưng nếu nhiều writer đồng thời phải update dựa trên giá trị trước đó, dùng `AtomicReference.compareAndSet` hoặc lock để tránh lost update. Không chỉ thêm `volatile` là đã giải quyết mọi phép cập nhật nhiều bước.

## 15. Thiết kế API và bảo trì production

### 15.1. Đóng gói tất cả shared state cùng khóa

Một thiết kế tốt giữ fields private, không để caller tùy ý sửa `x/y`; cung cấp method `move`, `snapshot`, `distance`, `moveIfAtOrigin`. Mỗi method thể hiện một **giao dịch trên bộ nhớ** với mode thích hợp.

```text
Public API:
  move(dx,dy)          -> writeLock
  snapshot()           -> readLock
  distance()           -> optimistic + validate + fallback
  moveIfAtOrigin(x,y)  -> read -> convert write / retry
```

Dùng StampedLock đòi hỏi developer duy trì hợp đồng nhất quán mỗi khi thêm method mới. Nếu một method mới ghi `x` không lấy write lock, các bảo đảm có thể sụp đổ ngay cả khi những method cũ đúng.

### 15.2. Tránh trả đối tượng mutable thoát khỏi vùng khóa

Nếu method dưới read lock trả một `List` mutable nội bộ, caller có thể đọc list **sau khi lock đã nhả** trong lúc writer sửa. Cần trả bản immutable copy/snapshot hoặc giữ dữ liệu ở kiểu có thread-safety phù hợp. Với optimistic read, càng phải tránh trả tham chiếu tới object đang được writer thay đổi.

### 15.3. Giữ critical section ngắn

Không gọi I/O mạng, truy vấn DB, ngủ hoặc chờ `Future.join()` trong khi giữ write lock trừ khi contract thật sự yêu cầu và đã đánh giá deadlock/latency. Khóa dài làm mọi reader có read lock phải chờ, khiến hệ thống kém phản hồi. Đọc lạc quan nên ngắn và chỉ copy những trường an toàn.

### 15.4. Chú ý starvation và độ trễ tail

Javadoc không đưa ra fairness guarantee cho StampedLock. Nếu workload có writer dày đặc hoặc hàng dài reader, khả năng chờ kéo dài cần được đo và kiểm soát. Nếu deadline có ý nghĩa, dùng timed try-lock/interruptible API hoặc cân nhắc khóa công bằng của giải pháp khác; không dùng loop retry bận không có giới hạn.

### 15.5. Serializing lock không lưu trạng thái “đang khóa”

`StampedLock` có thể serializable theo API, nhưng khi deserialize thì trở lại **trạng thái unlocked ban đầu**. Không dùng serialize stamp hoặc serialize StampedLock như một cơ chế **distributed lock** hay bảo đảm ownership xuyên tiến trình; giao thức distributed coordination cần giải pháp riêng.

## 16. Lỗi thường gặp và cách sửa

### 16.1. Đọc lạc quan mà quên `validate`

**Sai:** `stamp = tryOptimisticRead(); a=x; b=y; return a+b;`.  
**Đúng:** chụp vào locals, `validate(stamp)` và fallback read lock khi false.

### 16.2. Validate trước khi đọc

**Sai:** validate ngay rồi mới đọc các trường.  
**Đúng:** lấy stamp → copy → validate → dùng local copy.

### 16.3. Tưởng optimistic read ngăn writer

**Sai:** writer không thể thay dữ liệu cho đến khi reader xong.  
**Đúng:** optimistic mode **không giữ khóa**; writer có thể ghi ngay, khiến validation false.

### 16.4. Đọc object graph phức tạp rồi mới validate

**Sai:** gọi getter/duyệt array mutable có thể bị writer sửa cấu trúc, rồi mong `validate` sau đó sửa mọi lỗi.  
**Đúng:** dùng read lock cho hoạt động phức tạp hoặc immutable snapshot đã thiết kế an toàn.

### 16.5. Dùng `unlockRead` cho optimistic stamp

**Sai:** không có read lock nào được lấy; unlock sẽ sai mode.  
**Đúng:** optimistic stamp chỉ dùng để `validate`/conversion phù hợp; không phải unlock.

### 16.6. Unlock stamp 0 hoặc stamp cũ

**Sai:** `tryWriteLock()==0` nhưng vẫn gọi `unlockWrite(0)`; hoặc chuyển mode xong vẫn dùng stamp trước để nhả.  
**Đúng:** chỉ unlock khi thực sự giữ lock; dùng stamp mode hiện tại.

### 16.7. Thiếu `finally` sau khi có khóa

**Sai:** exception làm khóa không được nhả.  
**Đúng:** cấu trúc `try/finally` quanh vùng bảo vệ.

### 16.8. Gọi một method khóa lồng nhau

**Sai:** trong `writeLock` lại gọi method `readLock`/`writeLock` cùng StampedLock như thể nó reentrant.  
**Đúng:** tách helper không khóa hoặc chọn lock reentrant nếu nhu cầu thực sự cần.

### 16.9. Chuyển read→write bằng cách gọi writeLock trong lúc giữ read

**Sai:** đang giữ read stamp, gọi `writeLock()` và chờ nâng cấp tự động.  
**Đúng:** dùng `tryConvertToWriteLock`; khi thất bại nhả read, lấy write và **kiểm tra lại điều kiện**.

### 16.10. Tưởng conversion không bao giờ thất bại

**Sai:** dùng stamp trả 0 rồi tiếp tục sửa state hoặc unlock như write.  
**Đúng:** kiểm tra `converted != 0L`, phân nhánh thất bại chính xác và giữ mode hợp lệ.

### 16.11. Chỉ một số method ghi dùng lock

**Sai:** một writer sửa trực tiếp field không lấy write lock, nhưng reader tin `validate` bảo vệ.  
**Đúng:** thống nhất mọi đường ghi dùng cùng giao thức.

### 16.12. Dùng StampedLock làm distributed lock

**Sai:** serializing stamp rồi gửi qua service khác để bảo đảm tài nguyên chỉ có một writer toàn hệ thống.  
**Đúng:** StampedLock chỉ bảo vệ dữ liệu trong một JVM/đối tượng; dùng cơ chế coordination phân tán thích hợp nếu cần.

### 16.13. Cho rằng read lock bảo đảm tác vụ khác hoàn tất

**Sai:** kiểm tra tọa độ dưới read lock rồi nhả, sau đó ra quyết định ghi một nơi khác và kỳ vọng trạng thái không đổi.  
**Đúng:** cần giữ quyền thích hợp tới hết quyết định hoặc dùng cơ chế cập nhật có điều kiện/versioning.

### 16.14. Lấy `try...()==0` làm bằng chứng chắc chắn ai đang giữ khóa

**Sai:** suy ra một thread cụ thể đang sở hữu lock.  
**Đúng:** kết quả 0 chỉ phản ánh lần thử thất bại; Javadoc không cam kết lý do duy nhất.

### 16.15. Cố tối ưu trước khi đo

**Sai:** thay `synchronized` dễ hiểu bằng optimistic read phức tạp ở mọi nơi.  
**Đúng:** ưu tiên tính đúng, benchmark với workload thực và chỉ tối ưu khi lợi ích đủ lớn để bù rủi ro bảo trì.

## 17. Checklist kiểm thử cho code có `StampedLock`

- [ ] Có test ghi nhiều trường và đọc snapshot thuộc cùng một phiên bản?
- [ ] Có test stamp optimistic hợp lệ khi không có writer?
- [ ] Có test writer xen giữa stamp/copy/validate khiến `validate` trả false?
- [ ] Có test fallback dưới read lock sau validation false?
- [ ] Khi writer đang giữ khóa, `tryOptimisticRead` trả 0 và không được dùng như stamp hợp lệ?
- [ ] Có test `tryReadLock`/`tryWriteLock` trả 0 khi bị khóa khác chặn?
- [ ] Có test `tryConvertToWriteLock` thành công và thất bại với reader khác?
- [ ] Khi conversion thất bại, nhả read rồi lấy write có kiểm tra lại dữ liệu không?
- [ ] Sau conversion thành công, mọi đường `finally` nhả đúng stamp mới/mode mới?
- [ ] Có test lỗi trong critical section vẫn nhả lock?
- [ ] Có test nested method không tự lấy cùng khóa rồi gây self-block?
- [ ] Có test không dùng `try...` stamp 0 để unlock?
- [ ] Có test timeout/interrupt khi chờ khóa nếu nghiệp vụ yêu cầu?
- [ ] Có kiểm tra tất cả writer đều đi qua cùng khóa?
- [ ] Có kiểm tra snapshot không trả object mutable chưa được bảo vệ?
- [ ] Có benchmark nhiều tỷ lệ reader/writer, p99 latency và tác động fallback?

Đối với bài kiểm thử concurrency, ưu tiên **`CountDownLatch`**, `ExecutorService`, `Future.get(timeout, unit)` để điều khiển thứ tự quan sát. Dùng `Thread.sleep(100)` rồi hy vọng writer sẽ chạy “đúng lúc” khiến test dễ flake. Đối với framework kiểm thử hiện đại, có thể bổ sung stress test và công cụ kiểm tra race phù hợp nếu ứng dụng có rủi ro đồng thời cao.

## 18. Bảng quyết định cho dự án thực

| Bài toán | Khuyến nghị | Điều cần tránh |
| --- | --- | --- |
| Chỉ đọc hai số `x,y`, ghi rất hiếm | `tryOptimisticRead` + locals + `validate` + fallback | Bỏ qua validation |
| Đọc một list mutable có cấu trúc đổi thường xuyên | `readLock` hoặc thiết kế data immutable | Dereference chưa được validate |
| Cập nhật cặp số nhất quán | `writeLock` + `try/finally` | Chỉ khóa một trường |
| Đọc snapshot phải ổn định đến hết giao dịch | Giữ read lock theo giao thức | Optimistic read không giữ khóa |
| Chuyển từ đọc điều kiện sang ghi | `tryConvertToWriteLock`; nếu fail retry/recheck | Gọi blocking writeLock khi vẫn giữ read |
| Chỉ muốn bỏ khóa ghi nhưng giữ quyền đọc | `tryConvertToReadLock` | Unlock write cũ sau convert |
| Chuyển thành quan sát không khóa | `tryConvertToOptimisticRead` | Cố unlock stamp optimistic |
| Lấy khóa không được chờ | `tryReadLock`/`tryWriteLock` | Dùng blocking lock không timeout |
| Đường chờ cần hủy | Bản Interruptibly hoặc timed try-lock | Nuốt interrupt |
| Cần reentrancy và `Condition` | `ReentrantLock`/`ReentrantReadWriteLock` | Cố mô phỏng Condition bằng stamp |
| Chỉ cần một counter | `AtomicLong`/`LongAdder` | Dùng StampedLock chỉ để cộng 1 |
| Cập nhật immutable state trọn gói | `AtomicReference<ImmutableState>` | Nhiều field mutable không nhất quán |
| Map nhiều key cập nhật concurrent | `ConcurrentHashMap` | Dùng `HashMap` không tuân thủ giao thức lock |
| Cần distributed ownership | Database/coordination service | Gửi stamp qua mạng |
| Nhiều write, optimistic invalid liên tục | Benchmark lại, có thể dùng read lock khác | Coi optimistic luôn nhanh |

## 19. Câu hỏi tự kiểm tra và đáp án

**1. StampedLock có những chế độ nào?**  
Có **ghi độc quyền**, **đọc chia sẻ** và **đọc lạc quan**.

**2. `tryOptimisticRead()` có thực sự lấy read lock không?**  
Không. Nó lấy một dấu quan sát phiên bản, writer vẫn có thể ghi.

**3. Vì sao phải gọi `validate(stamp)` sau khi copy trường?**  
Để xác nhận không có writer lấy write lock giữa lúc lấy stamp và kiểm tra; nếu invalid, bỏ dữ liệu tạm và đọc lại dưới read lock.

**4. `tryOptimisticRead()` trả 0 khi nào?**  
Khi write lock đang giữ tại thời điểm thử; `validate(0)` luôn false.

**5. `validate(stamp) == true` có chặn writer sau lời gọi không?**  
Không. Nó chỉ xác thực những dữ liệu **đã copy trước đó** theo hợp đồng; không giữ khóa tương lai.

**6. Có được gọi `unlockRead(stamp)` sau optimistic read không?**  
Không. Không có read lock nào đã được lấy.

**7. `readLock()` và `writeLock()` trả gì?**  
Một stamp `long` tương ứng mode đã lấy, dùng để unlock/convert.

**8. `tryWriteLock() == 0L` phải làm gì?**  
Không được unlock; chọn retry/backoff/return theo chính sách, không suy diễn nguyên nhân quá cụ thể.

**9. StampedLock có reentrant không?**  
Không. Nested acquisition trên chính lock có thể tự chờ, cần thiết kế helper hoặc chọn khóa reentrant khác.

**10. `tryConvertToWriteLock` thất bại có tự nhả read lock không?**  
Không nên giả định nó tự làm như vậy. Khi trả 0, lập trình viên phải xử lý stamp read hiện có, nhả theo hợp đồng rồi lấy write nếu cần.

**11. Vì sao phải kiểm tra lại điều kiện sau khi nhả read rồi lấy write?**  
Vì thread khác có thể cập nhật trạng thái trong khoảng giữa hai lần lấy khóa.

**12. Nếu chuyển write→read thành công, có nên `unlockWrite(oldStamp)` không?**  
Không. Dùng read stamp mới để unlock read; write stamp cũ không còn đại diện cho mode hiện tại.

**13. Có nên dùng optimistic read để gọi nhiều method trên object mutable đang thay đổi không?**  
Thường không; có thể ném exception hoặc tạo side effect trước khi validate. Dùng read lock/immutable snapshot.

**14. `StampedLock` bảo đảm fairness không?**  
Không. Scheduler không cam kết luôn ưu tiên reader hay writer.

**15. StampedLock có `Condition` và thread ownership như `ReentrantLock` không?**  
Không. Stamp là capability, không gắn với owner thread; các lock-view cũng không tự thêm Condition.

**16. Chỉ một thread ghi không dùng write lock có ảnh hưởng gì?**  
Có. Nó phá giao thức và có thể làm optimistic validation báo true cho dữ liệu thực tế đã bị sửa ngoài khóa.

**17. Khi nào nên chọn `AtomicReference<ImmutableState>`?**  
Khi có thể đóng gói trạng thái thành một object bất biến và thay tham chiếu trọn gói, khiến việc đọc snapshot đơn giản hơn.

**18. `CountDownLatch` trong ví dụ giúp ích gì?**  
Nó bảo đảm worker lấy stamp trước khi main cập nhật, và worker validate sau writer, giúp test không phụ thuộc vào race ngẫu nhiên.

## 20. Tài liệu API chính thức và kiến thức còn áp dụng

- [`StampedLock` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html): ba mode, stamp/validate, non-reentrancy, conversion, weak fairness, optimistic-read memory semantics và ví dụ `Point`.
- [`StampedLock` — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/StampedLock.html): đối chiếu API có từ Java 8.
- [`ReentrantReadWriteLock` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): so sánh reentrancy, read/write locking và fairness.
- [`ReentrantLock` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): mô hình thread ownership, `Condition`, timed/interruptible lock.
- [`AtomicReference` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): thay snapshot bất biến với CAS.
- [`ConcurrentHashMap` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): lựa chọn concurrent cho dữ liệu dạng key-value.
- [`CountDownLatch` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): kiểm soát thời điểm giữa các thread khi test.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): benchmark có warm-up, measurement và forks theo phương pháp phù hợp với Java.

Các API trình bày ở đây vẫn được hỗ trợ trên JDK hiện đại; code runnable cố ý giới hạn ở các API Java 8 để phù hợp module học tập. Tránh suy diễn theo những chi tiết cài đặt của một JDK cụ thể thay cho hợp đồng công khai.
