# Lựa chọn theo tỷ lệ đọc, ghi và độ phức tạp kiểm chứng: StampedLock hay công cụ khác?

> **Module:** Java 8 → **StampedLock**. Trọng tâm không phải thuộc lòng một class concurrency mà là **ra quyết định đúng** khi cân nhắc tỷ lệ đọc/ghi, thời gian giữ khóa, contention, chi phí kiểm chứng kết quả optimistic read và độ phức tạp bảo trì. Các API chính được trình bày đã có từ Java 8 và **vẫn được sử dụng trên Java hiện đại**.

## 1. Vấn đề: “đọc nhiều hơn ghi” chưa đủ để chọn StampedLock

Giả sử một ứng dụng có hai field liên quan nhau: `x` và `y`. Hàng trăm luồng thường xuyên đọc cặp giá trị đó; thỉnh thoảng một writer cập nhật cả hai sao cho `x == y`. Bạn có thể dùng:

- `synchronized`: một monitor bảo vệ mọi truy cập; code ngắn và dễ kiểm chứng.
- `ReentrantLock`: một lock tường minh, có `tryLock`, timeout, interruptible lock và `Condition` khi cần.
- `ReentrantReadWriteLock`: cho **nhiều reader cùng đọc**, writer độc quyền; có tính reentrant và các view `Lock`.
- `StampedLock` với `readLock()/writeLock()`: cũng phân biệt mode đọc/ghi, nhưng yêu cầu **giữ stamp** để unlock và không reentrant.
- `StampedLock` với `tryOptimisticRead()/validate()`: đọc một cách lạc quan **không giữ read lock**, rồi kiểm chứng xem có writer nào can thiệp không.
- `AtomicReference<ImmutableSnapshot>`: writer công bố snapshot bất biến mới, reader đọc một reference nguyên tử mà không cần khóa đọc.

Một lựa chọn tốt không chỉ xét tỷ lệ “90% đọc, 10% ghi”. Phải hỏi:

1. Mỗi lần đọc/ghi kéo dài bao lâu?
2. Có bao nhiêu thread cùng truy cập **chính xác một trạng thái**?
3. Đọc nhiều field có cần cùng một snapshot không?
4. Đoạn đọc lạc quan có thể an toàn nếu tạm nhìn thấy dữ liệu không nhất quán không?
5. Có bao nhiêu lần `validate()` thất bại phải đọc lại bằng read lock?
6. Code có gọi lại chính nó, dùng `Condition` hoặc cần fairness không?
7. Độ phức tạp của mode conversion, stamp và fallback có đáng đổi lấy cải thiện đo được không?

**Quy tắc học:** Chọn theo **đúng ngữ nghĩa trước**, đo hiệu năng sau. Một implementation đạt throughput cao nhưng đôi lúc xuất bản kết quả sai vẫn là implementation sai.

## 2. Các công cụ cạnh tranh và hợp đồng của chúng

| Công cụ | Đồng thời khi đọc | Đường ghi | Đọc nhất quán nhiều field | Điểm cần cân nhắc |
| --- | --- | --- | --- | --- |
| `synchronized` | Một thread trong cùng monitor ở một thời điểm | Monitor độc quyền | Có, nếu tất cả writer/reader theo cùng monitor | Ngắn, reentrant, không có API timed acquire chuẩn |
| `ReentrantLock` | Một thread trong critical section | Một lock độc quyền | Có, nếu mọi truy cập theo lock | Reentrant, `Condition`, có thể dùng fairness policy |
| `ReentrantReadWriteLock` | Nhiều reader có thể giữ read lock cùng lúc | Writer độc quyền | Có khi giữ read lock đúng cách | Reentrant, overhead quản lý hai mode, không được upgrade tùy tiện |
| `StampedLock.readLock` | Nhiều readers cùng giữ stamp | Writer độc quyền | Có khi giữ read lock đúng cách | **Không reentrant**, cần quản lý stamp |
| `StampedLock.tryOptimisticRead` | Không giữ read lock; writer không bị ngăn như bởi reader | Writer vẫn dùng write lock | **Chỉ dùng bản sao sau khi validate thành công**, hoặc fallback | Có thể nhanh trong read ngắn nhưng dễ viết sai |
| `AtomicReference<Snapshot>` | Reader `get` rất ngắn | Writer thay toàn reference nguyên tử | Có nếu Snapshot thật sự immutable và được công bố an toàn | Allocation/CAS retry/chi phí sao chép snapshot |
| `volatile` với **một immutable snapshot** | Reader lấy reference volatile | Writer thay reference sau khi dựng hoàn chỉnh | Có đối với một snapshot immutable được publish đúng | Không tự tạo update có điều kiện giữa nhiều writer |
| `ConcurrentHashMap` | Concurrent per-key operations | Per-key update APIs | Không tự cho snapshot toàn map | Thích hợp key/value độc lập, không mặc định cho invariant đa field |

**Đừng đánh đồng các công cụ.** Một `AtomicReference<Snapshot>` có thể là phương án tốt khi object nhỏ và immutable, nhưng không phải thay thế cho lock khi cần cập nhật nhiều nguồn dữ liệu ngoại vi như một giao dịch.

## 3. Hiểu chính xác ba mode của StampedLock

`StampedLock` trong `java.util.concurrent.locks` có ba mode:

### 3.1. Write lock

`writeLock()` lấy quyền ghi độc quyền. Khi giữ write lock, các read lock khác không được cấp và những optimistic read validations từ stamp cũ sẽ thất bại.

~~~java
StampedLock lock = new StampedLock();
long stamp = lock.writeLock();
try {
    x++;
    y++;
} finally {
    lock.unlockWrite(stamp);
}
~~~

Đây là **đoạn minh họa trong class**, giả định hai field `x`, `y` được bảo vệ bởi cùng `lock`.

### 3.2. Read lock

`readLock()` lấy khóa đọc chia sẻ; nhiều reader có thể đọc đồng thời, nhưng writer không được cập nhật giữa lúc các reader giữ khóa.

~~~java
long stamp = lock.readLock();
try {
    int localX = x;
    int localY = y;
    // Sử dụng cả hai trong critical section hoặc trả về immutable snapshot.
} finally {
    lock.unlockRead(stamp);
}
~~~

Đoạn này là **minh họa** có khai báo `lock`, `x`, `y` trong cùng class. Nếu cần giữ snapshot sau khi unlock, nên trả object bất biến chứa cả hai giá trị, không trả tham chiếu tới object mutable đang bị writer sửa.

### 3.3. Optimistic read

`tryOptimisticRead()` không lấy read lock độc quyền hay chia sẻ. Nó trả **stamp khác zero** nếu tại thời điểm thử không có write lock đang được giữ. `validate(stamp)` kiểm tra rằng write lock **không được lấy** kể từ khi stamp được cấp.

~~~java
long stamp = lock.tryOptimisticRead();
int localX = x;
int localY = y;
if (stamp == 0L || !lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        localX = x;
        localY = y;
    } finally {
        lock.unlockRead(stamp);
    }
}
return new PairValue(localX, localY);
~~~

Đây là **đoạn code bên trong một method**, yêu cầu class có `lock`, `x`, `y` và record-like class `PairValue` bất biến; không phải file Java độc lập. Cách viết trên chỉ đọc hai primitive fields trong optimistic segment, sau đó validate, nếu thất bại lấy read lock thực để đọc lại.

**Trọng tâm:** optimistic read **không bảo vệ quá trình đọc trước validate** khỏi việc thấy dữ liệu bị writer thay đổi cùng lúc. Chỉ sau khi validation thành công mới được dùng bản sao theo hợp đồng. Nếu validation thất bại, **bỏ toàn bộ giá trị lạc quan và lấy lại dưới read lock**; không giữ một field cũ rồi đọc field mới như snapshot hợp lệ.

## 4. Tỷ lệ đọc/ghi: định nghĩa đúng trước khi tối ưu

### 4.1. Tỷ lệ theo số lần gọi

Một hệ thống có 95.000 lần đọc và 5.000 lần ghi trong cùng một khoảng quan sát có:

~~~text
Read fraction  = 95_000 / 100_000 = 95%
Write fraction =  5_000 / 100_000 =  5%
Read : write   = 19 : 1
~~~

Đây là một **ví dụ số lượng**, không phải ngưỡng ra quyết định. Không có quy tắc chính thức “nếu read vượt 90% thì luôn dùng StampedLock”.

### 4.2. Thời gian giữ khóa còn quan trọng hơn tỷ lệ số lần

So sánh:

| Kịch bản | Lượt đọc | Thời gian một read | Lượt ghi | Thời gian một write | Đánh giá sơ bộ |
| --- | --- | --- | --- | --- | --- |
| A | Rất nhiều | Copy hai số nguyên rất ngắn | Ít | Ghi hai số rất ngắn | Optimistic read có thể có lợi |
| B | Rất nhiều | Duyệt cây mutable phức tạp | Ít | Sửa cây nhiều bước | Optimistic segment quá rủi ro nếu đọc graph |
| C | Nhiều | Copy một immutable reference | Ít | Tạo object immutable | `AtomicReference`/volatile snapshot có thể đơn giản |
| D | Nhiều | Khối xử lý lâu dưới read lock | Ghi vừa phải | Critical section dài | Writers có thể chờ dù read fraction cao |
| E | Ít | Đọc nhanh | Rất nhiều | Ghi liên tục | Optimistic validation thường thất bại hoặc fallback nhiều |

Tỷ lệ theo **số lượt** không mô tả mức độ trùng lặp thời gian giữa các critical sections. Một writer rất dài cũng có thể chiếm phần lớn wall time dù số lần ghi ít.

### 4.3. Độ dài cửa sổ optimistic read

Khi optimistic reader làm những bước sau:

~~~text
T0: lấy stamp
T1: đọc trường A
T2: đọc trường B
T3: đọc trường C
T4: validate
T5: dùng snapshot nếu hợp lệ
~~~

Khoảng `T0 → T4` là **cửa sổ dễ bị writer làm mất hiệu lực**. Optimistic section dài hơn sẽ tạo thêm cơ hội cho writer chen vào. Với đoạn chỉ đọc hai primitive fields, cửa sổ ngắn. Với việc lặp qua 10.000 phần tử, gọi object methods hoặc tạo JSON, cửa sổ dài và có thể không an toàn từ trước khi validate.

### 4.4. Lợi thế của optimistic mode phụ thuộc xác suất validate thành công

Nếu optimistic read thường xuyên thất bại, công việc đã thực hiện trong nhánh optimistic có thể bị bỏ và phải làm lại dưới read lock. Một mô hình chi phí rất đơn giản, **không phải công thức hiệu năng chính thức**:

~~~text
Chi phí đọc dự kiến ≈ chi phí thử optimistic
                  + chi phí copy cục bộ
                  + chi phí validate
                  + (tỷ lệ fallback × chi phí đọc lại có khóa)
~~~

Mô hình này chưa phản ánh scheduling, cache effects, contention và write delays; mục đích là chỉ ra **tỷ lệ read/write không đủ**. Cần đo cả tỷ lệ validation failure và thời gian đọc lại.

### 4.5. Tỷ lệ đọc/ghi phải đo theo từng điểm tranh chấp

Một ứng dụng có 99% thao tác đọc nhưng mỗi reader truy cập **key khác nhau** trong `ConcurrentHashMap` có đặc điểm rất khác 99% readers cùng tranh chấp **một object mutable duy nhất**. Hãy đo concurrency tại đúng tài nguyên được bảo vệ, không chỉ đếm request tổng toàn hệ thống.

## 5. Vì sao kiểm chứng optimistic read là phần khó nhất?

### 5.1. Validate sau khi copy, trước khi sử dụng

Mẫu an toàn cho fields kiểu primitive:

~~~java
long stamp = lock.tryOptimisticRead();
long localA = a;
long localB = b;
if (stamp == 0L || !lock.validate(stamp)) {
    long read = lock.readLock();
    try {
        localA = a;
        localB = b;
    } finally {
        lock.unlockRead(read);
    }
}
return new Snapshot(localA, localB);
~~~

Đây là **method fragment**; Snapshot là object bất biến có hai field. `return` nằm trong method chứa `lock`, `a` và `b`.

Bằng việc **copy trước, validate sau**, code chỉ chấp nhận cặp đã đọc khi không có write lock acquisition can thiệp giữa stamp và validation. Đừng viết `if(validate(stamp))` **trước** khi đọc fields rồi tin rằng những reads sau đó cũng thuộc snapshot đã kiểm chứng.

### 5.2. Không dùng dữ liệu optimistic chưa được validate để có side effect

Sai:

~~~java
long stamp = lock.tryOptimisticRead();
long count = sharedCount;
sendPayment(count); // PHẢN VÍ DỤ: chưa validate.
if (!lock.validate(stamp)) {
    // Quá muộn để rollback một payment đã gửi.
}
~~~

Đoạn này **không phải chương trình runnable**, `sendPayment` minh họa một side effect nguy hiểm. Writer có thể làm dữ liệu đã đọc không còn hợp lệ trước khi validation; không gửi email, thanh toán, ghi DB hoặc quyết định quota trên giá trị chưa được kiểm chứng.

Đúng hơn là **copy primitives → validate/fallback → tạo immutable result → ra khỏi thủ tục lock → quyết định nghiệp vụ**, rồi vẫn phải dùng transaction/idempotency nếu side effect ngoài JVM cần bảo đảm mạnh hơn.

### 5.3. Không truy cập object graph tùy tiện trong optimistic segment

Một ví dụ nguy hiểm:

~~~java
long stamp = lock.tryOptimisticRead();
int size = mutableList.size();
Object element = mutableList.get(0);
// PHẢN VÍ DỤ: thao tác trên graph mutable đang bị writer sửa.
// validate sau đó không làm cho exception/side effect đã xảy ra biến mất.
~~~

`mutableList` là một object không được bảo vệ trong đoạn minh họa. Nếu writer sửa array backing/list giữa hai lần gọi, bạn có thể gặp `IndexOutOfBoundsException`, dữ liệu tạm thời kỳ lạ hoặc vấn đề khác **trước khi** kịp validate. Không giả định validate cuối cùng “hợp pháp hóa” việc gọi các method không chịu được trạng thái racy.

**Javadoc StampedLock chủ động cảnh báo điều này**. Chỉ viết optimistic reads khi hiểu rõ representation và bảo đảm các phép đọc tạm thời là an toàn. Với graph mutable phức tạp, **dùng read lock** hoặc **immutable snapshot** thường dễ kiểm chứng hơn.

### 5.4. Primitive fields không có nghĩa luôn có snapshot

Hai field `x` và `y` được writer cập nhật nối tiếp trong write lock:

~~~java
long write = lock.writeLock();
try {
    x++;
    y++;
} finally {
    lock.unlockWrite(write);
}
~~~

Một optimistic reader có thể đọc `x` mới, `y` cũ nếu nó chạy xen giữa hai phép cập nhật. Nhưng khi writer đã lấy write lock sau stamp, `validate(stamp)` sẽ thất bại; dữ liệu cục bộ phải bị bỏ đi.

Vì vậy test chỉ assert `x == y` **sau valid/fallback**, không assert invariant trên dữ liệu tạm thời trước validate.

### 5.5. Memory visibility phụ thuộc validation thành công

Với optimistic read, JDK quy định memory synchronization gắn với lần write unlock và việc validate thành công. Không tự gán cho `tryOptimisticRead()` tính chất tương đương một read lock thật; nếu validate thất bại, không có bảo đảm snapshot nhất quán cho các reads giữa đó.

Điểm này đặc biệt quan trọng khi code review: chỉ nhìn thấy `StampedLock` trong class chưa đủ chứng minh dữ liệu đã được đồng bộ. Phải kiểm tra **đúng trình tự copy/validate/fallback** và loại thao tác được phép giữa hai bước.

### 5.6. Một “validate true” không có nghĩa trạng thái không bao giờ thay đổi

Sau khi validate thành công, writer khác vẫn có thể thay đổi object ở thời điểm tiếp theo. Điều mà caller có là một **snapshot đã được xác nhận tại thời điểm đọc**, không phải quyền giữ trạng thái bất biến trong tương lai.

Nếu cần một hành động cập nhật phải có điều kiện “nếu A vẫn bằng 10”, hãy dùng write lock/CAS/transaction, không dựa vào read-only optimistic validation rồi ghi bên ngoài lock.

## 6. Khi chọn StampedLock optimistic read là hợp lý

Một trường hợp tương đối thuận lợi:

- Có một trạng thái nhỏ, ví dụ một tọa độ hai số, vài số đo hoặc một object nội bộ đơn giản.
- Writers luôn cập nhật qua **cùng StampedLock write mode**.
- Reads rất thường xuyên và ngắn; validation failure hiếm trong workload thực.
- Phép đọc optimistic chỉ tải một vài primitive fields vào locals, không gọi method nhạy cảm với race.
- Nếu validation thất bại, code có một **read-lock fallback đúng và dễ kiểm thử**.
- Không cần reentrancy, Condition hoặc fairness.
- Benchmark thấy cải thiện có ý nghĩa so với các lựa chọn đơn giản.

Ví dụ:

~~~java
final class Point {
    private final StampedLock lock = new StampedLock();
    private double x, y;

    double distanceFromOrigin() {
        long stamp = lock.tryOptimisticRead();
        double localX = x;
        double localY = y;
        if (stamp == 0L || !lock.validate(stamp)) {
            stamp = lock.readLock();
            try {
                localX = x;
                localY = y;
            } finally {
                lock.unlockRead(stamp);
            }
        }
        return Math.sqrt(localX * localX + localY * localY);
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

Đây là **class ví dụ độc lập về phương pháp**, cần `import java.util.concurrent.locks.StampedLock;`. `double` cũng có thể dùng ở đây vì phép đọc chỉ sao chép primitive fields. Không có side effect trong optimistic section và chỉ tính `sqrt` sau validate/fallback.

**Quan trọng:** Nếu representation của trạng thái thay đổi thành object graph, không mặc định tái sử dụng optimistic code mà không review lại các thao tác đọc.

## 7. Khi nên dùng readLock của StampedLock thay vì optimistic read

`StampedLock.readLock()` là lựa chọn bảo thủ hơn nếu:

- Reads cần đi qua nhiều fields, array, collection hoặc object có khả năng đổi cấu trúc.
- Không dễ tách thao tác thành **copy primitives vào locals**.
- Validation failures thường xuyên, khiến đọc hai lần tốn công.
- Kết quả đọc cần một quan sát nhất quán trong suốt một critical section ngắn.
- Code đang có StampedLock vì cần mode conversion hoặc write-lock protocol nhưng optimistic read ở chỗ này không đem lợi ích rõ.

~~~java
long stamp = lock.readLock();
try {
    // Đọc dữ liệu được bảo vệ trong đoạn này.
    return computeFromProtectedState();
} finally {
    lock.unlockRead(stamp);
}
~~~

Đây là **method fragment**, `computeFromProtectedState()` là hàm nội bộ biết rằng read lock đang được giữ và **không tự lấy lại chính lock**. StampedLock **không reentrant**: nếu helper gọi lại `readLock()` hoặc `writeLock()` theo một protocol không phù hợp, bạn có thể bị kẹt hoặc gặp khó khăn trong việc quản lý mode.

Chọn read lock thường giúp correctness dễ kiểm chứng hơn optimistic read, nhưng không phải lúc nào cũng tối ưu hiệu năng. Trong tình huống không cần optimistic mode, có thể cân nhắc luôn `ReentrantReadWriteLock` để giảm phức tạp stamp.

## 8. Khi ReentrantReadWriteLock hợp hơn StampedLock

`ReentrantReadWriteLock` phù hợp khi:

- Đã có thiết kế dựa trên interface `Lock`/`ReadWriteLock`.
- Các method có thể gọi lồng nhau và cần reentrancy có kiểm soát.
- Thường xuyên cần bảo vệ một khối đọc/ghi có cấu trúc rõ.
- Không có optimistic segment đủ an toàn và đủ ngắn để đem lại lợi thế.
- Muốn tích hợp với các pattern lock thông thường.
- Cần cân nhắc fairness policy của `ReentrantReadWriteLock`, chấp nhận tradeoff hiệu năng.

Ví dụ:

~~~java
ReentrantReadWriteLock rw = new ReentrantReadWriteLock();

rw.readLock().lock();
try {
    // Đọc dữ liệu được cùng rw bảo vệ.
} finally {
    rw.readLock().unlock();
}
~~~

Đây là **đoạn minh họa**, cần import `java.util.concurrent.locks.ReentrantReadWriteLock`.

### 8.1. Read/write lock không tự làm graph mutable trở thành immutable

Nếu reader nhận reference tới một `ArrayList` và mang nó ra ngoài read lock, một writer vẫn có thể sửa list sau khi reader unlock. Cần **copy snapshot** hoặc trả một object thực sự immutable nếu muốn dùng lâu dài bên ngoài critical section.

### 8.2. Reentrancy có ích nhưng cũng dễ che giấu nested locking

Reentrancy không phải miễn phí về reasoning. Một method nội bộ tự lấy lại lock có thể khiến thời gian giữ khóa kéo dài ngoài dự tính. Khi chọn `ReentrantReadWriteLock`, vẫn phải audit lock order, thời gian giữ khóa, side effects và khả năng reader chặn writer.

### 8.3. Không upgrade read sang write tùy tiện

Dù ReentrantReadWriteLock reentrant, thiết kế read→write upgrade không tự nhiên an toàn. Một thread giữ read lock rồi cố lấy write lock có thể bế tắc trong tình huống phù hợp. Nếu cần upgrade, cân nhắc release/read recheck protocol hoặc thiết kế lại state machine.

### 8.4. Fair mode không phải một “tăng tốc”

Fair policy có thể giảm starvation trong một số tình huống, nhưng thường có chi phí scheduling/throughput. Nếu bạn chọn fair mode, lý do nên là yêu cầu công bằng/latency của workload, không phải niềm tin mọi thread sẽ chạy nhanh hơn.

## 9. Khi synchronized hoặc ReentrantLock là lựa chọn tốt hơn

### 9.1. Critical section rất ngắn và ít contention

Nếu chỉ có vài thread đọc/ghi rất ngắn, `synchronized` có lợi thế lớn về **độ dễ đọc và dễ review**:

~~~java
final class SafeCounter {
    private long count;

    synchronized void add() {
        count++;
    }

    synchronized long get() {
        return count;
    }
}
~~~

Đây là **class Java đơn giản, độc lập**. Nó bảo vệ một biến; trong workload này việc đưa StampedLock vào có thể làm nhiều code hơn mà không có lợi ích đo được.

### 9.2. Cần wait/signal hoặc timeout/interruptible lock

`ReentrantLock` có các API phù hợp như `tryLock()`, `tryLock(timeout,unit)`, `lockInterruptibly()` và `newCondition()`. Nếu logic cần Condition hoặc ownership theo thread, đây là một lựa chọn khác cần xem xét.

StampedLock có timed và interruptible acquire, nhưng không trực tiếp implement `Lock` hoặc `ReadWriteLock`; các lock views có tập tính năng riêng và không biến StampedLock thành một ReentrantLock.

### 9.3. “Đơn giản” cũng là một thuộc tính kỹ thuật

Một đường đọc có hai primitive fields bằng StampedLock optimistic có thể dễ. Một hệ thống có 8 methods lồng nhau, chuyển mode nhiều lần và gọi callback thì complexity của stamp, retry, unlock, conversion có thể lớn hơn lợi ích.

Đánh giá trong code review:

- Có bao nhiêu đường exception/early return cần giải phóng stamp?
- Có cần biết stamp hiện tại là read hay write?
- Có helper nào gọi lại lock không?
- Mọi writer có dùng chung write lock không?
- Optimistic reads có gọi method trên object mutable không?
- Có test ép validation fail không?
- Có ai đang dùng stamp như boolean hoặc ID không?

Nếu không trả lời được dễ dàng, giải pháp đơn giản hơn thường đáng ưu tiên.

## 10. Khi immutable snapshot + AtomicReference là lựa chọn đáng cân nhắc

Nếu dữ liệu đọc thường xuyên gồm một **object nhỏ bất biến**, có thể công bố snapshot qua `AtomicReference<Snapshot>`.

~~~java
final class Snapshot {
    final long left;
    final long right;

    Snapshot(long left, long right) {
        this.left = left;
        this.right = right;
    }
}

AtomicReference<Snapshot> state =
        new AtomicReference<>(new Snapshot(0, 0));

Snapshot before = state.get();
state.updateAndGet(previous ->
        new Snapshot(previous.left + 1, previous.right + 1));

Snapshot after = state.get();
~~~

Đây là **class và đoạn logic minh họa**, cần `import java.util.concurrent.atomic.AtomicReference;`.

### 10.1. Vì sao reader dễ kiểm chứng?

Reader chỉ lấy **một reference** tới object immutable đã được publish an toàn. Nó không cần đọc hai mutable fields có thể được writer thay đổi giữa chừng. Ngay cả nếu writer cập nhật reference sau `get()`, snapshot cũ **vẫn bất biến**, nên reader có thể dùng sau đó mà không cần validate.

### 10.2. Đánh đổi ở phía writer

- Tạo object mới có thể tăng allocation/GC.
- CAS trên một AtomicReference khi có nhiều writers có thể retry.
- Hàm `updateAndGet` có thể được gọi nhiều lần khi contention; nó phải **side-effect-free**.
- Nếu snapshot là graph lớn, sao chép có thể tốn chi phí đáng kể.
- Chỉ một reference update là atomic; cập nhật đồng thời một DB và reference không tự biến thành transaction toàn hệ thống.

### 10.3. Một biến volatile reference cũng có thể đủ

Nếu chỉ có **một writer** hoặc synchronization khác đã đảm bảo quyền cập nhật, một field `volatile Snapshot current` với assignment snapshot mới có thể cung cấp publication đơn giản. Nhưng nếu có **nhiều writers** và mỗi writer cần cập nhật dựa trên state cũ, assignment đơn thuần có thể bị lost update; cần CAS/lock thích hợp.

### 10.4. Khi nào chọn phương án nào?

| Bài toán | Hướng thiết kế |
| --- | --- |
| Hai primitive fields, đọc nhiều, ghi hiếm, fallback dễ | Cân nhắc StampedLock optimistic |
| Immutable config nhỏ, reader cần reference ổn định | Cân nhắc volatile/AtomicReference snapshot |
| Object graph mutable phức tạp | Read lock/lock rõ ràng hoặc immutable redesign |
| Nhiều readers, writer trung bình, không cần optimistic | ReentrantReadWriteLock có thể dễ bảo trì |
| Một counter duy nhất | AtomicLong/LongAdder theo semantics |
| Một state nhỏ với ít concurrency | synchronized thường đủ |

Không có phương án tối ưu trong mọi điều kiện. Hãy chọn dựa trên correctness, thao tác cần thiết và số đo sau đó.

## 11. Cạnh tranh khi ghi làm giảm lợi ích optimistic reads

### 11.1. Writer liên tục khiến validation thất bại

Optimistic read chỉ được chấp nhận khi không có write lock acquisition can thiệp trong cửa sổ từ khi lấy stamp tới validate. Nếu writer lấy write lock liên tục, reader có thể:

1. Lấy stamp.
2. Copy các fields.
3. Thấy `validate(stamp)==false`.
4. Lấy read lock để copy lại.

Khi đó, tổng chi phí có thể cao hơn việc lấy read lock ngay từ đầu. Đừng suy từ tỷ lệ 70/30 hay 90/10 một cách cơ học: quan trọng là **cửa sổ overlap** và thời gian thực.

### 11.2. Validation failure không phải exception

`validate(stamp)` trả boolean; `false` thường là outcome cạnh tranh hợp lệ, không phải dữ liệu hỏng. Không log một stack trace nặng mỗi lần validation thất bại. Đó có thể là chỉ số contention bình thường mà bạn muốn ghi metric tần suất.

### 11.3. Fallback một lần hay retry optimistic nhiều lần?

Một giải pháp đơn giản và dễ kiểm chứng:

~~~text
Thử optimistic -> validate
   |
   +-- true  -> dùng immutable result
   |
   +-- false -> đọc lại có read lock, rồi trả result
~~~

Không tự tạo loop retry optimistic vô hạn nếu writers cập nhật liên tục. Nó có thể gây starvation, lãng phí CPU và vẫn không có fairness guarantee.

Nếu bạn quyết định retry một số lần để tránh lock acquisition, cần giải thích tại sao (đã đo benefit), giới hạn retry, và sau giới hạn có fallback rõ ràng. Thường **một lần optimistic + một read-lock fallback** là điểm khởi đầu dễ kiểm chứng.

### 11.4. Quá nhiều writer sẽ ảnh hưởng ngay cả readers không giữ khóa

Optimistic readers không ngăn writer cập nhật, nhưng writer có thể làm invalid mọi stamp hiện hữu. Nếu toàn bộ hệ thống phải xử lý một luồng write dày, vấn đề không chỉ là lock type mà có thể cần **partition/shard state**, giảm critical-section duration, immutable snapshots hoặc tái thiết kế workload.

## 12. Nonreentrancy, conversion và độ phức tạp của StampedLock

### 12.1. StampedLock không reentrant

Không viết:

~~~java
long write = lock.writeLock();
try {
    callHelperThatAcquiresSameLock(); // PHẢN VÍ DỤ.
} finally {
    lock.unlockWrite(write);
}
~~~

Ở đây `callHelperThatAcquiresSameLock` là tên giả, không phải function thực. Nếu helper lấy lại khóa mà không hiểu stamp đã giữ, code có thể tự chặn. So với `synchronized` hay `ReentrantLock`, StampedLock đòi tổ chức methods cẩn thận hơn.

### 12.2. Stamp không phải token tùy ý

Các acquire methods trả `long`, nhưng stamp có nghĩa với **instance StampedLock và mode cụ thể**. Không sử dụng như ID, lưu vào database, thao tác cộng/trừ, chia sẻ không kiểm soát hay unlock hai lần.

~~~java
long stamp = lock.tryReadLock();
if (stamp != 0L) {
    try {
        // Đã có read lock.
    } finally {
        lock.unlockRead(stamp);
    }
}
~~~

`0L` nghĩa là không acquire thành công. Với optimistic stamp, **không** gọi `unlockRead(stamp)`; nó là token để `validate`, không phải read lock thật.

### 12.3. Conversion read → write có thể thành công hoặc trả zero

~~~java
long stamp = lock.readLock();
boolean writeMode = false;
try {
    long upgraded = lock.tryConvertToWriteLock(stamp);
    if (upgraded != 0L) {
        stamp = upgraded;
        writeMode = true;
        // Ghi dữ liệu được bảo vệ.
    } else {
        // Vẫn có read stamp ban đầu: không được cập nhật!
    }
} finally {
    if (writeMode) {
        lock.unlockWrite(stamp);
    } else {
        lock.unlockRead(stamp);
    }
}
~~~

Đây là **đoạn minh họa trong method**, cần `lock` đã khai báo. Conversion có thể không thành công nếu còn reader khác. Caller giữ stamp cũ trên đường thất bại; trên đường thành công cần dùng **stamp mới và mode mới**.

### 12.4. Nếu release rồi reacquire, phải recheck

Khi cần write sau read mà conversion không được:

1. Unlock read stamp theo đúng mode.
2. Lấy write lock hoặc thử với timeout.
3. **Đọc lại state bên dưới write lock**.
4. Chỉ thực hiện update nếu điều kiện vẫn hợp lệ.

Không mang một kết luận kiểm tra trong read lock cũ qua một khoảng không có khóa rồi coi state vẫn y nguyên.

### 12.5. Không có fairness guarantee cố định

StampedLock không cam kết luôn ưu tiên reader hay writer, và các try methods là best-effort. Không dựa vào thứ tự chờ hoặc việc một thread lâu chắc chắn được cấp tiếp theo. Khi business thật cần fairness, cân nhắc primitive có chính sách cụ thể và đo tradeoff.

## 13. Timeout và interrupt: độ phức tạp mà thiết kế phải trả

StampedLock cung cấp:

~~~java
long read = lock.tryReadLock(100, TimeUnit.MILLISECONDS);
long write = lock.tryWriteLock(100, TimeUnit.MILLISECONDS);
~~~

Đây là **đoạn minh họa**, cần import `TimeUnit` và xử lý checked `InterruptedException` ở method bao ngoài. Timed try có hai outcome thất bại khác nhau:

- Trả `0L` khi không lấy được lock trong thời hạn.
- Ném `InterruptedException` khi thread được yêu cầu ngắt trước acquire.

Khi acquire thành công, **unlock trong finally**. `readLockInterruptibly()`/`writeLockInterruptibly()` cũng hỗ trợ interruption mà không đặt timeout. `readLock()`/`writeLock()` thường không ném checked `InterruptedException`.

### 13.1. Cẩn trọng với SLA

Một timeout 100 ms chỉ giới hạn **thời gian chờ lấy lock**. Sau khi lấy được write lock, thao tác bên trong critical section có thể chạy lâu hơn nhiều. Nếu một API có deadline tổng, cần phân bổ phần thời gian còn lại và quản lý cancellation của nghiệp vụ, không trông chờ timeout lock giải quyết toàn bộ.

### 13.2. Cẩn trọng với interrupt

Khi bắt `InterruptedException` mà không propagate lên caller, thường cần khôi phục flag bằng `Thread.currentThread().interrupt()` và ngừng thao tác. Không nuốt rồi retry mãi; nó có thể phá shutdown/cancellation.

### 13.3. Lựa chọn primitive theo API mong muốn

Nếu code cần Condition, reentrancy, lock ownership theo thread hoặc các abstraction `Lock` thông thường, StampedLock có thể khiến API phức tạp hơn `ReentrantLock` dù đọc nhiều. Hãy đánh giá cả interface/lifecycle chứ không chỉ throughput.

## 14. Hệ thống metrics nên đo gì trước và sau khi đổi khóa?

Một cuộc tối ưu hợp lệ cần telemetry liên quan đúng nơi tranh chấp.

### 14.1. Chỉ số cho đường đọc

1. **Tỷ lệ đọc/ghi** trên đúng object/lock.
2. **Read latency distribution:** trung vị, p95, p99 và tail under load.
3. **Read lock wait time** khi dùng read lock thật.
4. **Optimistic attempts count**.
5. **Validation success/failure count** và tỷ lệ fallback.
6. **Fallback read-lock wait time**.
7. **Read critical-section duration**, nhất là khi có gọi method phức tạp.

Không in log cho mọi lần optimistic fail trong request hot path; telemetry cũng có overhead và thay đổi profile contention.

### 14.2. Chỉ số cho đường ghi

1. Số lần ghi mỗi giây.
2. Wait time và hold time cho write lock.
3. Độ dài phần xử lý dưới write lock.
4. Write timeout và interruption.
5. Starvation/các chu kỳ chờ kéo dài.
6. Tail latency của writer khi reader liên tục.

Một tối ưu cải thiện throughput reader nhưng làm writer p99 không đạt SLA có thể là lựa chọn xấu.

### 14.3. Đếm validation failure có ảnh hưởng hiệu năng

Nếu thêm `AtomicLong.incrementAndGet()` vào **mọi optimistic read**, bạn có thể tạo một hot counter mới. Đo instrumented và uninstrumented builds, hoặc dùng sampling/metrics accumulation phù hợp; không vô tình tạo contention vì công cụ đo.

### 14.4. Không đo hiệu năng bằng stdout trong vòng lặp

`System.out.println` gây I/O đồng bộ và có thể che khuất mọi khác biệt của lock. Tương tự, tạo object, sleep và gọi GC trong mỗi iteration sẽ làm benchmark không còn đo đúng lock.

### 14.5. JMH thay vì một vòng System.nanoTime đơn giản

Cho hiệu năng Java microbenchmark, dùng JMH với warmup, forks, states và concurrency workload mô phỏng production. Cần chạy nhiều tỉ lệ readers/writers, ví dụ read-only, 95:5, 80:20, 50:50 và write-heavy, nhưng **không** diễn giải các tỉ lệ này là ngưỡng chính thức cho StampedLock.

Benchmark nên giữ:

- Cùng dữ liệu và invariant.
- Cùng mức contention.
- Cùng số writers/readers.
- Cùng kiểu operation thực.
- Không dùng random/nội dung I/O quá nặng làm méo kết quả.
- Có đo throughput **và** tail latency, allocation, GC, CPU.
- Có baseline giản đơn (`synchronized`, ReentrantReadWriteLock, immutable snapshot).
- Có stress test correctness độc lập với benchmark.

## 15. Thang quyết định theo “lợi ích so với độ khó kiểm chứng”

| Tiêu chí | Thấp/dễ | Trung bình | Cao/khó |
| --- | --- | --- | --- |
| Số field cần snapshot | 1 primitive | 2–5 primitives | Graph mutable/collections |
| Thời gian đọc | Vài field loads | Tính toán ngắn | Vòng lặp dài, gọi object methods |
| Tần suất ghi | Hiếm | Vừa | Dày, kéo dài |
| Tỷ lệ fallback | Hiếm | Đôi lúc | Liên tục |
| Kiểm chứng invariant | Dễ nêu bằng vài điều kiện | Cần nhiều test | Khó chứng minh hết mọi interleaving |
| Khả năng dùng immutable snapshot | Rất dễ | Cần refactor | Copy tốn kém hoặc khó |
| Reentrancy/Condition | Không cần | Một số helper cần | Bắt buộc |
| Fairness/writer SLA | Không khắt khe | Có deadline vừa phải | Chính sách nghiêm ngặt |

**Diễn giải:** StampedLock optimistic hợp lý hơn khi **đọc cực ngắn**, representation đơn giản và đo được validate success rate cao. Khi độ khó kiểm chứng tăng, lợi ích tối ưu phải đủ lớn để bù cho rủi ro của code phức tạp; nếu không, chọn read lock hoặc immutable snapshot.

### 15.1. Quy trình ra quyết định bảy bước

1. Liệt kê invariant: các trường nào phải nhất quán với nhau?
2. Chọn implementation đơn giản, đúng và có unit tests làm baseline.
3. Đo throughput/latency thật để xác định có contention đáng kể.
4. Đo tỷ lệ đọc/ghi và **thời gian giữ** read/write lock.
5. Xác định optimistic segment có thể chỉ đọc primitives, không gây side effect, rồi validate hay không.
6. Thêm fallback đúng và kiểm thử trong điều kiện writer chen vào.
7. Benchmark đối chứng; chỉ giữ StampedLock nếu lợi ích đo được đáng đánh đổi maintenance.

### 15.2. Không chọn theo “độ mới” của API

`synchronized` không “lỗi thời” chỉ vì nó tồn tại từ trước Java 8. `ReentrantReadWriteLock` cũng không legacy chỉ vì StampedLock xuất hiện sau. Cả ba vẫn có vai trò hiện hành; chất lượng lựa chọn nằm ở semantics và workload.

## 16. Chương trình Java 8 hoàn chỉnh: bốn cách bảo vệ cùng một bất biến

Chương trình dưới đây cho thấy **cùng một yêu cầu correctness**: bốn writer song song cùng tăng hai field `left/right` sao cho `left == right`; hai reader liên tục lấy snapshot để xác minh bất biến.

Bốn implementation:

1. `MonitorStore` bằng `synchronized`.
2. `ReadWriteStore` bằng `ReentrantReadWriteLock`.
3. `StampedStore` dùng optimistic read, validate và read-lock fallback.
4. `ImmutableStore` dùng `AtomicReference<Snapshot>` immutable.

**Đây là kiểm thử độ đúng, không phải benchmark tốc độ.** Chúng có những tradeoff tài nguyên khác nhau, nhưng chương trình cố ý chỉ in các invariants xác định thay vì so thứ tự thread hoặc throughput.

Lưu toàn bộ thành file **ReadWriteChoiceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.concurrent.locks.StampedLock;

public final class ReadWriteChoiceDemo {
    static final class Snapshot {
        final long left;
        final long right;
        Snapshot(long left, long right) {
            this.left = left;
            this.right = right;
        }
        boolean valid() {
            return left == right;
        }
    }

    interface Store {
        void addBoth();
        Snapshot snapshot();
    }

    static final class MonitorStore implements Store {
        private long left, right;
        public synchronized void addBoth() {
            left++;
            right++;
        }
        public synchronized Snapshot snapshot() {
            return new Snapshot(left, right);
        }
    }

    static final class ReadWriteStore implements Store {
        private final ReentrantReadWriteLock lock =
                new ReentrantReadWriteLock();
        private long left, right;
        public void addBoth() {
            lock.writeLock().lock();
            try {
                left++;
                right++;
            } finally {
                lock.writeLock().unlock();
            }
        }
        public Snapshot snapshot() {
            lock.readLock().lock();
            try {
                return new Snapshot(left, right);
            } finally {
                lock.readLock().unlock();
            }
        }
    }

    static final class StampedStore implements Store {
        private final StampedLock lock = new StampedLock();
        private long left, right;
        private final AtomicInteger fallbacks = new AtomicInteger();

        public void addBoth() {
            long stamp = lock.writeLock();
            try {
                left++;
                right++;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        public Snapshot snapshot() {
            long stamp = lock.tryOptimisticRead();
            long x = left;
            long y = right;
            if (stamp == 0L || !lock.validate(stamp)) {
                fallbacks.incrementAndGet();
                stamp = lock.readLock();
                try {
                    x = left;
                    y = right;
                } finally {
                    lock.unlockRead(stamp);
                }
            }
            return new Snapshot(x, y);
        }

        boolean invalidatesOldStamp() {
            long stamp = lock.tryOptimisticRead();
            if (stamp == 0L) {
                throw new IllegalStateException("no optimistic stamp");
            }
            addBoth();
            return !lock.validate(stamp);
        }

        boolean upgradeBlockedBySecondReader() {
            long first = lock.readLock();
            long second = lock.readLock();
            try {
                return lock.tryConvertToWriteLock(first) == 0L;
            } finally {
                lock.unlockRead(second);
                lock.unlockRead(first);
            }
        }

        boolean upgradeSoleReader() {
            long stamp = lock.readLock();
            long converted = 0L;
            try {
                converted = lock.tryConvertToWriteLock(stamp);
                return converted != 0L;
            } finally {
                if (converted == 0L) {
                    lock.unlockRead(stamp);
                } else {
                    lock.unlockWrite(converted);
                }
            }
        }
    }

    static final class ImmutableStore implements Store {
        private final AtomicReference<Snapshot> value =
                new AtomicReference<>(new Snapshot(0, 0));

        public void addBoth() {
            value.updateAndGet(old ->
                    new Snapshot(old.left + 1, old.right + 1));
        }
        public Snapshot snapshot() {
            return value.get();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(error);
        }
    }

    private static void verify(String label, Store store)
            throws Exception {
        final int writers = 4;
        final int readers = 2;
        final int loops = 1000;
        CountDownLatch ready = new CountDownLatch(writers + readers);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger invalidSnapshots = new AtomicInteger();
        ExecutorService pool =
                Executors.newFixedThreadPool(writers + readers);
        List<Future<?>> tasks = new ArrayList<>();
        try {
            for (int i = 0; i < writers; i++) {
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    await(start);
                    for (int j = 0; j < loops; j++) {
                        store.addBoth();
                    }
                }));
            }
            for (int i = 0; i < readers; i++) {
                tasks.add(pool.submit(() -> {
                    ready.countDown();
                    await(start);
                    for (int j = 0; j < loops; j++) {
                        if (!store.snapshot().valid()) {
                            invalidSnapshots.incrementAndGet();
                        }
                    }
                }));
            }
            await(ready);
            start.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
        Snapshot end = store.snapshot();
        System.out.println(label + " count = " + end.left);
        System.out.println(label + " invariant = "
                + (end.valid() && invalidSnapshots.get() == 0));
    }

    public static void main(String[] args) throws Exception {
        verify("monitor", new MonitorStore());
        verify("readWrite", new ReadWriteStore());
        verify("stamped", new StampedStore());
        verify("immutable", new ImmutableStore());

        StampedStore example = new StampedStore();
        System.out.println("old optimistic stamp invalidated = "
                + example.invalidatesOldStamp());
        System.out.println("upgrade with two readers blocked = "
                + example.upgradeBlockedBySecondReader());
        System.out.println("upgrade with sole reader works = "
                + example.upgradeSoleReader());
    }
}
~~~

Biên dịch và chạy với JDK hỗ trợ target Java 8:

~~~bash
javac --release 8 ReadWriteChoiceDemo.java
java ReadWriteChoiceDemo
~~~

**Stdout đã biên dịch và chạy xác minh:**

~~~text
monitor count = 4000
monitor invariant = true
readWrite count = 4000
readWrite invariant = true
stamped count = 4000
stamped invariant = true
immutable count = 4000
immutable invariant = true
old optimistic stamp invalidated = true
upgrade with two readers blocked = true
upgrade with sole reader works = true
~~~

### 16.1. Vì sao cả bốn count đều là 4.000?

Mỗi implementation có 4 writers, mỗi writer gọi `addBoth()` 1.000 lần. Tổng số lần cập nhật là `4 × 1.000 = 4.000`.

- Với `synchronized`, các updates nằm dưới cùng monitor.
- Với `ReentrantReadWriteLock`, updates dùng write lock.
- Với `StampedLock`, updates dùng write stamp.
- Với `AtomicReference`, mỗi update dựng một Snapshot mới và dùng atomic update; callback là một hàm pure, nên CAS retry không gây side effect sai.

Main chỉ in final count **sau khi tất cả `Future.get()` hoàn thành**; không suy thứ tự completion của các writers.

### 16.2. Vì sao invariant đều true?

Reader kiểm tra `left == right` trên mỗi Snapshot trả về. Có 2 readers, mỗi reader đọc 1.000 lần. Nếu phát hiện snapshot vi phạm invariant, biến `invalidSnapshots` tăng và dòng invariant sẽ false.

Bốn implementations sử dụng synchronization phù hợp để **không trả ra một cặp chưa nhất quán**. Ở StampedStore, optimistic fields có thể được đọc giữa hai writes nhưng chỉ được **dùng** khi validate thành công; nếu không thì được đọc lại dưới read lock. Ở ImmutableStore, Snapshot không bị sửa sau publication.

### 16.3. Tại sao không in số lần fallback?

`fallbacks` đếm lần optimistic read phải chuyển sang read lock. Số đó phụ thuộc scheduling và mức overlap, nên có thể khác nhau giữa các lần chạy. Để stdout cố định, chương trình **không** in fallback count; trong production, đây là một metric hữu ích để quyết định optimistic read có đáng giá không.

### 16.4. Stale optimistic stamp bị vô hiệu

`invalidatesOldStamp()` lấy stamp ở trạng thái không có writer, sau đó gọi `addBoth()` lấy write lock rồi release, cuối cùng kiểm tra stamp cũ. `validate(stamp)` trả false, cho thấy optimistic observation trước lần ghi không còn hợp lệ.

### 16.5. Nâng quyền khi hai read stamps cùng tồn tại

`upgradeBlockedBySecondReader()` giữ hai read stamps nên `tryConvertToWriteLock(first)` không thể giành exclusive mode; method trả zero. Mã release cả hai read stamps ở finally.

Trong `upgradeSoleReader()` chỉ có một read stamp; conversion có thể thành công và trả write stamp mới. Mã release đúng mode sau conversion. Cả hai kiểm tra dùng cùng thread và data cố định để minh họa mode protocol, **không phải benchmark**.

### 16.6. Cách kiểm tra sâu hơn

Chương trình minh họa deterministic correctness, không chứng minh mọi JVM/scheduling đều không có bug do stress test hữu hạn. Với production, cần:

- Unit test deterministic cho từng mode và đường fallback.
- Stress test số lần lặp lớn, thay số reader/writer.
- Race tests có latch để ép writer xen đúng giữa copy và validate.
- Kiểm thử timeout/interrupt và shutdown theo lifecycle.
- Benchmark độc lập với JMH nếu mục tiêu là so hiệu năng.

## 17. Kiểm thử bắt buộc trước khi đưa optimistic read vào production

### 17.1. Invariant của dữ liệu

Hãy nêu rõ bất biến như `left == right`, tổng hai fields cố định, hoặc `start <= end`. Không có invariant rõ thì khó biết snapshot nào là hợp lệ hoặc test có phát hiện lỗi không.

### 17.2. Test chèn write giữa stamp và validate

Thiết kế một điểm test điều phối: reader lấy optimistic stamp và copy fields; writer lấy write lock, cập nhật và unlock; reader gọi validate. Phải thấy `validate==false` và thực hiện fallback.

**Không** dùng `Thread.sleep(50)` để “bảo đảm” writer đã can thiệp; sleep không tạo happens-before hoặc thứ tự được cam kết.

### 17.3. Test write xảy ra sau validate

Sau khi reader đã trả immutable snapshot hợp lệ, writer được phép cập nhật state. Snapshot reader đã trả **vẫn immutable**; nó không bắt buộc chứa giá trị mới nhất ở mọi thời điểm trong tương lai.

### 17.4. Test fallback vẫn đúng dưới contention

Cần xác minh mọi đường có thể đi vào fallback đều:

- Lấy một read stamp hợp lệ.
- Đọc lại **toàn bộ** fields cần nhất quán.
- Unlock trong finally dù có exception.
- Không dùng field cũ đã đọc lạc quan.
- Không dùng stamp optimistic để unlock read mode.

### 17.5. Test read-only methods có side effect?

Audit những gì code optimistic thực sự gọi. Một getter trong object graph có thể vô tình đọc data mutable, duyệt collection hoặc cập nhật cache. Nếu có side effect hay không chịu racy state, không nên chạy nó trong optimistic segment.

### 17.6. Test nonreentrant paths

Kiểm tra graph method calls có wrapper/helper cố lấy lại StampedLock trong cùng thread không. Đừng tạo test deadlock vô hạn trên test runner chính; dùng thread riêng với timeout và cơ chế cleanup chắc chắn nếu muốn tái hiện lỗi.

### 17.7. Test có writer không tuân theo lock

Nếu một writer sửa field ngoài write lock, invariant có thể bị phá dù reader validate thành công. Code review và tests phải bảo đảm **mọi writer vào protocol**, không chỉ happy path.

## 18. Những lỗi phổ biến khi lựa chọn theo read/write ratio

### Lỗi 1 — “95% reads” đồng nghĩa StampedLock luôn nhanh nhất

Sai. Độ dài read/write, contention, fallback và memory cũng quyết định. **Sửa:** đo workload trên đúng object và so baseline.

### Lỗi 2 — Dùng optimistic read trên mutable list rồi validate cuối

List methods có thể ném exception hoặc đọc sai cấu trúc trước validate. **Sửa:** read lock hoặc immutable snapshot.

### Lỗi 3 — Validate trước khi copy fields

Writer có thể can thiệp sau validate nhưng trước khi reader đọc. **Sửa:** copy vào locals trước, validate sau, rồi sử dụng.

### Lỗi 4 — Dùng giá trị optimistic chưa xác nhận để ghi DB

Sai side-effect boundary; một validate thất bại không rollback write bên ngoài. **Sửa:** tách copy/validate khỏi side effect và dùng transaction/idempotency phù hợp.

### Lỗi 5 — Bỏ qua stamp bằng zero

`tryOptimisticRead()` có thể trả zero khi writer giữ lock. **Sửa:** kiểm tra zero hoặc validate false rồi dùng fallback.

### Lỗi 6 — Không đọc lại toàn bộ fields khi validate thất bại

Trộn field đọc trước và sau writer có thể tạo trạng thái không tồn tại. **Sửa:** copy lại **toàn bộ** dữ liệu cần thiết dưới read lock.

### Lỗi 7 — Mặc định reader đã có read lock khi gọi tryOptimisticRead

Optimistic mode không giữ read lock. **Sửa:** chỉ đọc những thứ chịu được racy read, validate hoặc fallback.

### Lỗi 8 — Nghĩ validate true biến object mutable thành immutable

Không; writer vẫn có thể sửa sau đó. **Sửa:** trả immutable Snapshot, không để caller giữ reference mutable không bảo vệ.

### Lỗi 9 — Không dùng finally cho unlock

Exception hoặc return sớm khiến lock bị giữ lại. **Sửa:** acquire thành công → try/finally → unlock đúng mode.

### Lỗi 10 — UnlockRead bằng optimistic stamp

Optimistic stamp không đại diện read lock. **Sửa:** dùng nó để validate, không unlock.

### Lỗi 11 — Quên cập nhật stamp sau conversion thành công

`tryConvertToWriteLock` có thể trả stamp mới. **Sửa:** lưu stamp mới và unlock theo mode mới.

### Lỗi 12 — Giữ read stamp rồi gọi writeLock thông thường

StampedLock không reentrant; dễ tự deadlock. **Sửa:** conversion hoặc release/reacquire với recheck.

### Lỗi 13 — Lưu một stamp lâu dài để “tối ưu” nhiều requests

Stamp là capability/version có giới hạn, không phải ID ổn định lâu dài. **Sửa:** lấy stamp trong scope operation, validate/unlock đúng lúc.

### Lỗi 14 — Bảo vệ field chỉ ở readers nhưng writers không dùng cùng lock

Không có synchronization protocol thống nhất, dù validate có thể vẫn true sai ngữ nghĩa. **Sửa:** mọi writer cập nhật dưới write lock của cùng instance.

### Lỗi 15 — Đọc nhiều fields qua hai locks khác nhau và tin có snapshot chung

Dù mỗi lock riêng an toàn, hai lần đọc có thể thuộc hai thời điểm. **Sửa:** một state snapshot/transaction phù hợp.

### Lỗi 16 — Dùng StampedLock thay ReentrantLock khi cần Condition

StampedLock không có cùng mô hình reentrant/Condition. **Sửa:** chọn primitive dựa trên operations cần có.

### Lỗi 17 — Tin StampedLock ưu tiên writers

Không có fairness/reader-writer preference guarantee ổn định. **Sửa:** đo starvation, chọn policy khác nếu cần.

### Lỗi 18 — Spin optimistic retry vô hạn

Writer có thể khiến validate liên tục false. **Sửa:** bounded retry hoặc trực tiếp read-lock fallback.

### Lỗi 19 — Nghĩ timed try lock giới hạn cả critical section

Timeout chỉ giới hạn chờ acquire. **Sửa:** quản lý deadline của nghiệp vụ riêng.

### Lỗi 20 — Nuốt InterruptedException khi shutdown

Thread có thể tiếp tục chạy dù đã bị yêu cầu dừng. **Sửa:** propagate hoặc restore interrupt flag rồi thoát.

### Lỗi 21 — Cho rằng immutable snapshot không có chi phí

Writer tạo object mới và có thể CAS retry/GC. **Sửa:** benchmark update allocation và write throughput.

### Lỗi 22 — Side effect bên trong AtomicReference.updateAndGet

Hàm có thể chạy lại khi CAS thất bại. **Sửa:** giữ pure function và xử lý I/O bên ngoài.

### Lỗi 23 — Đo throughput mà quên tail latency writer

Reader nhanh hơn không bảo đảm writer không bị starvation. **Sửa:** đo p95/p99 writer latency, timeout và throughput cùng lúc.

### Lỗi 24 — Dùng System.out.println bên trong benchmark hot loop

Console I/O che overhead khóa. **Sửa:** dùng JMH hoặc harness không bị I/O thống trị.

### Lỗi 25 — Quyết định chỉ từ benchmark đơn thread

Khác biệt quan trọng nằm ở contention. **Sửa:** thử nhiều mức reader/writer và threads.

### Lỗi 26 — Optimistic read chạy business validation dựa vào state đang biến đổi

Validation nghiệp vụ có thể truy cập object graph hoặc tạo side effect. **Sửa:** chỉ sử dụng dữ liệu snapshot đã xác nhận.

### Lỗi 27 — Trả một reference mutable sau read-lock release

Caller tưởng có snapshot nhưng writer tiếp tục sửa object đó. **Sửa:** copy immutable data trước unlock.

### Lỗi 28 — Dùng isWriteLocked/isReadLocked để thay acquisition

Các trạng thái kiểm tra chỉ là observation và có thể đổi ngay. **Sửa:** dùng acquire/validate thực sự, không viết `if(!lock.isWriteLocked())` rồi đọc thiếu bảo vệ.

## 19. Checklist ra quyết định và triển khai

Trước khi đưa StampedLock optimistic vào hệ thống, trả lời:

1. Có **bất biến** cụ thể cần bảo vệ không?
2. State có chủ yếu là vài primitive fields hay mutable graph?
3. Tất cả writers có cập nhật cùng `StampedLock.writeLock()` không?
4. Reads có thể copy nhanh mọi field cần thiết vào locals không?
5. Có method call hoặc side effect nào trong optimistic section không?
6. `validate` được gọi **sau** copy và **trước** khi dùng?
7. Nếu stamp zero hoặc invalid, có fallback dưới read lock không?
8. Fallback có copy lại tất cả fields không?
9. Có phải trả immutable snapshot ra ngoài critical section không?
10. Code có recursive/nested locking không?
11. Có cần Condition hoặc reentrancy không?
12. Có yêu cầu fairness hay writer latency SLA chặt chẽ không?
13. Tỷ lệ reads/writes đo ở đúng lock hay chỉ đo toàn app?
14. Thời gian giữ read/write lock thực tế bao nhiêu?
15. Tỷ lệ optimistic validation failure là bao nhiêu?
16. Fallback chiếm bao nhiêu phần tổng chi phí đọc?
17. Có cần timeout/interruptible acquisition hay deadline toàn request?
18. Có unit/stress tests ép writer giữa copy và validate?
19. Có thử mutable object mutation ngoài lock để nhận diện protocol gaps?
20. Có benchmark so sánh với baseline đơn giản không?
21. Có đo tail latency, allocation và GC không?
22. Có policy rollback/idempotency cho side effect ngoài JVM không?
23. Có thể thay bằng immutable snapshot cho dễ kiểm chứng không?
24. Lợi ích đo được có đáng độ phức tạp maintain/review không?

### 19.1. Bảng các invariant cần test

| Test | Kết quả hợp lệ |
| --- | --- |
| Chỉ một writer cập nhật cả hai fields dưới write lock | Reader snapshot hợp lệ |
| Nhiều writers cùng cập nhật | Tổng cuối đúng sau barrier |
| Nhiều readers trên StampedLock | Snapshot trả về không vi phạm invariant |
| Writer chen vào sau optimistic stamp | `validate` false |
| Optimistic validation false | Fallback đọc lại dưới read lock |
| Writer cập nhật sau khi snapshot đã trả | Snapshot cũ không đổi |
| Khi có 2 read stamps | `tryConvertToWriteLock` có thể trả 0 |
| Khi chỉ có 1 read stamp và không tranh chấp | Upgrade có thể thành công |
| Stale hoặc sai mode stamp | Bị từ chối khi unlock |
| Timed try không acquire | Trả 0, không unlock |
| Timed try bị interrupt | `InterruptedException` theo contract |
| Nhiều snapshots trong AtomicReference | Không có giá trị đã mutate một phần |
| CAS retry | Update function không side effect |
| Writer chưa qua lock protocol | Test/review phát hiện vi phạm |
| Tốc độ cao khi read-only | Không suy ra write-heavy cũng cao |
| Benchmark | Không làm thay đổi consistency contract |

## 20. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** “95% reads” có đủ để chọn StampedLock không?

**Đáp án:** Không. Cần biết độ dài critical sections, contention, chi phí validate/fallback, độ phức tạp dữ liệu, writer latency và số đo hiệu năng.

**Câu 2.** Optimistic read có giữ read lock thật không?

**Đáp án:** Không. `tryOptimisticRead` chỉ trả stamp để kiểm chứng; writer có thể can thiệp.

**Câu 3.** Vì sao phải validate sau khi đọc fields?

**Đáp án:** Vì writer có thể cập nhật giữa các lần đọc; `validate` xác nhận không có write-lock acquisition làm stamp mất hiệu lực trong cửa sổ đã đọc.

**Câu 4.** Nếu validate false, có thể giữ lại field A cũ rồi chỉ đọc lại B dưới lock không?

**Đáp án:** Không nên. Phải bỏ dữ liệu optimistic chưa đáng tin và đọc lại **tất cả fields thuộc cùng snapshot** dưới read lock.

**Câu 5.** Optimistic read có an toàn để duyệt ArrayList mutable bị writer sửa đồng thời không?

**Đáp án:** Không mặc định. List methods có thể gặp trạng thái racy trước validation; dùng read lock hoặc immutable snapshot khi không chứng minh được an toàn.

**Câu 6.** Nếu validate true thì object đã bất biến vĩnh viễn chưa?

**Đáp án:** Không. Nó cho một snapshot hợp lệ cho khoảng quan sát, nhưng writer vẫn có thể cập nhật tiếp. Nên trả immutable result.

**Câu 7.** Trong workload nhiều write, StampedLock optimistic có chắc nhanh hơn read lock không?

**Đáp án:** Không. Nếu validate thường xuyên fail, việc copy rồi fallback làm tăng chi phí.

**Câu 8.** `StampedLock` có reentrant không?

**Đáp án:** Không. Không giữ read/write stamp rồi tự acquire lại lock theo protocol không an toàn.

**Câu 9.** Vì sao cần cập nhật stamp khi conversion thành công?

**Đáp án:** Vì mode mới có stamp phù hợp mới; unlock theo mode hiện hành để tránh lỗi.

**Câu 10.** Khi nào `ReentrantReadWriteLock` hợp hơn?

**Đáp án:** Khi cần read/write locking rõ ràng, reentrancy và API `Lock`, nhưng optimistic section không đem lợi ích đủ lớn hoặc khó kiểm chứng.

**Câu 11.** Khi nào `synchronized` có thể tốt hơn?

**Đáp án:** Với state nhỏ, ít contention, critical section ngắn, và mong muốn code đơn giản/dễ review.

**Câu 12.** `AtomicReference<ImmutableSnapshot>` giúp gì cho reader?

**Đáp án:** Reader lấy một reference nguyên tử tới snapshot bất biến, không cần copy hai mutable fields rồi validate; đổi lại writer tạo object/CAS và chi phí allocation.

**Câu 13.** Vì sao `AtomicReference.updateAndGet` callback cần pure?

**Đáp án:** Callback có thể được thực thi lại do CAS contention; side effect trong callback không bảo đảm exactly-once.

**Câu 14.** StampedLock có ưu tiên writer cố định không?

**Đáp án:** Không. Scheduling policy không bảo đảm reader/writer preference hoặc fairness cụ thể.

**Câu 15.** Timed `tryWriteLock(100,MILLISECONDS)` có bảo đảm xử lý update xong trong 100ms không?

**Đáp án:** Không. Timeout chỉ giới hạn thời gian chờ lấy khóa, không giới hạn công việc trong critical section.

**Câu 16.** Một snapshot optimistic hợp lệ có thể được dùng để tự quyết định cập nhật state mà không lấy write lock không?

**Đáp án:** Không nếu nghiệp vụ cần atomic check-and-update. Cần write lock/CAS/transaction và recheck điều kiện.

**Câu 17.** Vì sao không dùng `isWriteLocked()==false` làm quyền đọc an toàn?

**Đáp án:** Trạng thái có thể thay đổi ngay sau kiểm tra. Dùng read-lock acquisition hoặc optimistic stamp + validation.

**Câu 18.** Có nên in số lần fallback trong stdout cố định của test concurrency không?

**Đáp án:** Không nếu test không kiểm soát scheduling. Có thể đo fallback như metric hoặc test riêng, nhưng không assert một con số phụ thuộc lịch thread.

**Câu 19.** Lợi ích hiệu năng có thể bù cho một optimistic implementation khó chứng minh không?

**Đáp án:** Chỉ khi implementation **đã đúng**, có test tin cậy, đo được lợi ích rõ và độ phức tạp được quản lý. Không đánh đổi tính đúng lấy throughput.

**Câu 20.** Một phép ghi dưới `StampedLock.writeLock()` có làm invalid optimistic stamp cũ không?

**Đáp án:** Có, nếu stamp cũ còn hiệu lực từ trước lần writer lấy write lock; sau đó `validate` cũ trả false.

## 21. Tổng kết

- **Không chọn StampedLock chỉ bằng tỷ lệ read/write.** Phải xét thời gian giữ khóa, mức overlap, validation failure, fallback cost, writer latency và cách biểu diễn dữ liệu.
- **Optimistic mode chỉ là một quan sát yếu**, không phải read lock. Copy dữ liệu **vào locals**, kiểm tra `stamp != 0L` và **validate sau khi đọc**, nếu không hợp lệ thì đọc lại toàn bộ dưới read lock.
- **Object graph mutable khó kiểm chứng optimistic read hơn primitive fields.** Có thể gặp exception hoặc side effect trước validate.
- **StampedLock không reentrant, không hứa fairness**, và người viết phải quản lý stamp/mode/convert/unlock đúng.
- **ReentrantReadWriteLock** đáng cân nhắc cho read/write locking thuần túy; **synchronized/ReentrantLock** thường đơn giản hơn khi concurrency ít hoặc cần semantics khác.
- **AtomicReference<ImmutableSnapshot>** hữu ích khi readers cần snapshot bất biến và writers chấp nhận allocation/CAS cost.
- **Vị trí tối ưu phải được đo**, nhưng hiệu năng chỉ có ý nghĩa sau khi correctness/invariants được chứng minh và kiểm thử.
- **Java 8 runnable demo** đã chạy xác minh bốn implementation đồng thời giữ bất biến và kiểm chứng conversion/optimistic stamp.
- Những API được đề cập vẫn dùng trên Java hiện hành, phù hợp giới hạn chỉ trình bày kiến thức còn áp dụng.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — StampedLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/StampedLock.html)
- [Oracle Java SE 26 — StampedLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)
- [Oracle Java SE 8 — ReentrantReadWriteLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/ReentrantReadWriteLock.html)
- [Oracle Java SE 8 — ReentrantLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/ReentrantLock.html)
- [Oracle Java SE 8 — AtomicReference](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/AtomicReference.html)
- [Oracle Java SE 8 — CountDownLatch](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountDownLatch.html)
- [Oracle Java SE 8 — Future](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Future.html)
- [Oracle Java SE 8 — Java Memory Model / JLS Chapter 17](https://docs.oracle.com/javase/specs/jls/se8/html/jls-17.html)
