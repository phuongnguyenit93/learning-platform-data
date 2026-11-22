# StampedLock với optimistic read trong Java

## 1. Vấn đề: đọc thường xuyên, ghi ít nhưng vẫn phải nhất quán

Giả sử nhiều thread thường xuyên đọc tọa độ của một điểm, trong khi một thread khác thỉnh thoảng cập nhật cả `x` và `y`. Ta muốn giảm tranh chấp khi đọc, nhưng phải tránh lấy `x` của lần cập nhật mới và `y` của lần cập nhật cũ.

`java.util.concurrent.locks.StampedLock` là một cơ chế đồng bộ của JDK hỗ trợ **ba chế độ**: khóa đọc (*read lock*), khóa ghi (*write lock*) và đọc lạc quan (*optimistic read*). Điểm đặc biệt là optimistic read **không giữ một read lock thực sự**. Reader lấy một **stamp**, đọc dữ liệu vào biến cục bộ rồi gọi `validate(stamp)` để xem một writer có làm mất hiệu lực bản đọc hay không. Nếu validation thất bại, reader phải **đọc lại dưới read lock thực sự** trước khi sử dụng kết quả.

Mẫu chuẩn:

```java
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
// Chỉ dùng localX, localY sau bước validate hoặc fallback.
```

Đây là **snippet minh họa** trong một class đã có `lock`, `x`, `y`, không phải chương trình độc lập. Phần ví dụ bên dưới có đầy đủ class và `main` để chạy bằng Java 17+.

### Lợi ích và giới hạn

- **Lợi ích có thể có:** khi writer hiếm, reader optimistic không phải đăng ký chiếm read lock và có thể giảm overhead/tranh chấp so với một read lock truyền thống.
- **Giới hạn:** nếu writer đang hoặc vừa thay đổi dữ liệu, validation có thể thất bại; reader phải đọc lại và chịu thêm chi phí.
- **Không phải phép màu:** optimistic read không tự đồng bộ toàn bộ object, không khóa writer, không bảo đảm luôn nhanh hơn, không cấp quyền truy cập một cấu trúc mutable tùy ý mà không kiểm tra.
- **Chỉ nên dùng khi dữ liệu đọc thử an toàn:** ưu tiên các trường primitive hoặc tham chiếu được xử lý thận trọng, sao chép vào biến cục bộ và **không thực hiện tác dụng phụ dựa trên dữ liệu chưa xác minh**.

Đây là kiến thức Java concurrency nói chung, sử dụng API JDK, không gắn với bất kỳ framework nào.

## 2. Ba chế độ của `StampedLock`

| Chế độ | API lấy stamp | Điều nó bảo đảm | Cách kết thúc |
| --- | --- | --- | --- |
| **Write lock** | `writeLock()` | Loại trừ writer khác và reader dùng read lock; bảo vệ cập nhật trạng thái | `unlockWrite(stamp)` |
| **Read lock** | `readLock()` | Có thể nhiều reader cùng giữ; ngăn writer lấy write lock trong lúc còn giữ | `unlockRead(stamp)` |
| **Optimistic read** | `tryOptimisticRead()` | Lấy một dấu hiệu phiên bản để xác minh bản đọc; **không khóa writer** | `validate(stamp)`; **không unlock optimistic stamp** |

`StampedLock` dùng giá trị `long` làm **stamp**. Stamp nhận được từ các thao tác khóa là một **khả năng (capability) đại diện cho lần lấy khóa đó**, không chỉ là số đếm mà chương trình được phép tùy ý sửa.

- `readLock()` và `writeLock()` có thể chặn cho đến khi lấy được khóa; khi đã lấy thành công, caller phải nhả đúng chế độ bằng stamp phù hợp.
- `tryOptimisticRead()` **không chặn** để chờ writer; nó có thể trả về `0L` nếu write lock đang được giữ.
- `validate(stamp)` trả về `false` khi stamp không còn hợp lệ theo trạng thái đồng bộ của lock, kể cả trường hợp optimistic stamp bằng 0. Một lần writer lấy write lock có thể làm stamp lạc quan cũ mất hiệu lực.
- Không gọi `unlockRead` hoặc `unlockWrite` với optimistic stamp: nó **không đại diện cho một lock đã được giữ**.

**Một nguyên tắc khó nhầm:** một optimistic read thành công không có nghĩa reader “giữ” thứ gì để ngăn writer. Writer có thể bắt đầu cập nhật bất cứ lúc nào; reader chỉ chấp nhận những giá trị đã sao chép **sau khi** việc xác minh stamp thành công. Mọi truy cập tiếp theo với state chung cần giao thức đồng bộ mới.

## 3. Quy trình optimistic read đúng từng bước

1. **Nhận stamp:** `long stamp = lock.tryOptimisticRead()`. Đây không phải `readLock()`.
2. **Đọc thử vào local:** đọc các trường cần thiết (ví dụ `x`, `y`) và không để các giá trị ấy điều khiển side effect.
3. **Xác minh:** `lock.validate(stamp)` kiểm tra tính hợp lệ của thời điểm đọc lạc quan. Nếu writer đã làm mất hiệu lực stamp, không được sử dụng snapshot đọc thử.
4. **Fallback:** khi validation là `false`, lấy `readLock()`, đọc lại các trường **bên trong critical section**, rồi `unlockRead(stamp)` trong `finally`.
5. **Sử dụng snapshot:** sau khi xác minh/fallback, chỉ sử dụng các giá trị **local đã chụp**, hoặc một immutable snapshot đã tạo từ chúng. Không đọc tiếp trường chia sẻ ngoài lock rồi coi đó là một phần của snapshot cũ.

**Lỗi điển hình:** làm phép tính trên shared fields **sau** khi validate:

```java
// Sai về mặt ý tưởng: tính lại từ shared state sau validate.
long stamp = lock.tryOptimisticRead();
int localX = x;
int localY = y;
if (lock.validate(stamp)) {
    return x + y; // Đã đọc lại x, y sau validate.
}
```

Đây là snippet minh họa, không có phương thức/class bao quanh. Sau `validate`, một writer có thể đã bắt đầu; lần đọc `x`/`y` mới không thuộc snapshot được kiểm tra. Sửa bằng `return localX + localY` hoặc trả immutable value từ **các local đã xác minh**.

### Tại sao phải giữ local?

Nếu trước khi validate writer sửa `x` rồi `y`, reader có thể tạm thấy tổ hợp chưa nhất quán. Validation thất bại yêu cầu **bỏ** những local ấy và đọc lại dưới lock. Nếu validation thành công, bản đọc được chấp nhận theo giao thức optimistic read của `StampedLock`. Kể cả khi writer đến **ngay sau** validation, snapshot local vẫn đại diện cho dữ liệu đã được đọc trong một giai đoạn hợp lệ; nó không cần phản ánh bản cập nhật tương lai.

Tránh dereference sâu một chuỗi object mutable trong giai đoạn optimistic read: nếu tham chiếu thay đổi đồng thời, có thể gặp `NullPointerException`, index không hợp lệ, hoặc thao tác trên object đang được sửa **trước cả khi kịp validate**. Khi state phức tạp, dùng read lock thực sự hoặc thiết kế dữ liệu bất biến an toàn để đọc thử.

## 4. Ví dụ Java 17+ hoàn chỉnh: tọa độ với optimistic snapshot

Tạo file `StampedPoint.java`:

```java
import java.util.concurrent.locks.StampedLock;

public class StampedPoint {
    record Position(int x, int y) {}

    private final StampedLock lock = new StampedLock();
    private int x;
    private int y;

    public void moveTo(int newX, int newY) {
        long stamp = lock.writeLock();
        try {
            x = newX;
            y = newY;
        } finally {
            lock.unlockWrite(stamp);
        }
    }

    public Position snapshot() {
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
        return new Position(localX, localY);
    }

    public static void main(String[] args) {
        StampedPoint point = new StampedPoint();
        point.moveTo(4, 6);

        Position position = point.snapshot();
        System.out.println(position);
        System.out.println("Sum: " + (position.x() + position.y()));
    }
}
```

Biên dịch và chạy:

```bash
javac StampedPoint.java
java StampedPoint
```

Đầu ra xác định:

```text
Position[x=4, y=6]
Sum: 10
```

Giải thích:

- `moveTo` lấy write lock, thay đổi **cả hai trường** trong cùng critical section, và nhả khóa trong `finally`.
- `snapshot` lấy optimistic stamp, chụp `x` và `y` vào local. Nếu stamp đã bị writer làm mất hiệu lực, nó chuyển sang **read lock** để đọc lại cho nhất quán.
- Kết quả là `record Position` bất biến theo hai trường primitive, không lộ state mutable của object.
- Ví dụ `main` tuần tự nên kết quả cố định. Trong chương trình concurrent, snapshot có thể là tọa độ trước hoặc sau một lần `moveTo`, nhưng **không được chấp nhận cặp x/y bị trộn** nếu mọi writer đều dùng write lock của cùng `StampedPoint` và reader tuân thủ giao thức trên.

**Không được gộp hai bước “đọc dưới write lock” với “kiểm tra stamp” thành một suy đoán về tốc độ:** chỉ benchmark workload thực tế mới cho biết đọc optimistic có hiệu quả hơn `readLock` thông thường hay không.

## 5. Ví dụ Java 17+: bảo vệ invariant khi đọc/ghi đồng thời

Chúng ta có hai số dư nội bộ với bất biến `left + right == 100`. Writer liên tục chuyển một đơn vị từ left sang right; reader liên tục chụp snapshot. Một snapshot hợp lệ không được lấy left của một lần chuyển và right của lần khác.

Tạo file `StampedTransfer.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.StampedLock;

public class StampedTransfer {
    record Balances(int left, int right) {
        int total() {
            return left + right;
        }
    }

    private final StampedLock lock = new StampedLock();
    private int left = 100;
    private int right = 0;

    public void moveOne() {
        long stamp = lock.writeLock();
        try {
            if (left > 0) {
                left--;
                right++;
            }
        } finally {
            lock.unlockWrite(stamp);
        }
    }

    public Balances snapshot() {
        long stamp = lock.tryOptimisticRead();
        int observedLeft = left;
        int observedRight = right;

        if (!lock.validate(stamp)) {
            stamp = lock.readLock();
            try {
                observedLeft = left;
                observedRight = right;
            } finally {
                lock.unlockRead(stamp);
            }
        }
        return new Balances(observedLeft, observedRight);
    }

    public static void main(String[] args) throws InterruptedException {
        StampedTransfer book = new StampedTransfer();
        AtomicBoolean valid = new AtomicBoolean(true);

        Thread writer = new Thread(() -> {
            for (int i = 0; i < 100; i++) {
                book.moveOne();
            }
        }, "writer");

        Thread reader = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                if (book.snapshot().total() != 100) {
                    valid.set(false);
                }
            }
        }, "reader");

        writer.start();
        reader.start();
        writer.join();
        reader.join();

        System.out.println("Consistent snapshots: " + valid.get());
        System.out.println("Final balances: " + book.snapshot());
    }
}
```

Chạy:

```bash
javac StampedTransfer.java
java StampedTransfer
```

Đầu ra khi hai worker hoàn tất bình thường:

```text
Consistent snapshots: true
Final balances: Balances[left=0, right=100]
```

**Tại sao ví dụ có kết quả xác định dù scheduling bất định?**

- Mỗi lần `moveOne` giữ write lock từ lúc đọc `left` đến hết khi cập nhật `right`, nên không có hai writer hoặc read-lock reader nào xen vào đoạn sửa.
- Optimistic reader có thể đọc giữa hai phép ghi; khi một writer đã bắt đầu lấy write lock sau khi reader nhận stamp, `validate` không chấp nhận snapshot đó. Reader sẽ **đọc lại cả hai trường dưới read lock**.
- Snapshot là `record Balances` gồm hai số nguyên bất biến; phép tính total chỉ chạy trên hai local đã xác minh hoặc đọc dưới read lock.
- Writer thực hiện đủ 100 lần chuyển khi ban đầu `left == 100`. Vì vậy cuối cùng `left == 0`, `right == 100`, không phụ thuộc lịch chạy.
- `join()` làm main đợi đủ hai worker. `AtomicBoolean` ghi lại một cách an toàn việc có phát hiện snapshot sai hay không.

Nếu writer không sử dụng **cùng `StampedLock`**, bảo đảm trên không còn. Một direct write vào `left` hoặc `right` không tuân thủ khóa phá vỡ hợp đồng dù phần reader vẫn dùng validate.

**Phạm vi:** đây là trạng thái trong **một instance trong một JVM**. Nó không tự giải quyết cập nhật dữ liệu đến từ process/JVM hoặc dịch vụ khác.

## 6. Tại sao `validate` quan trọng với Java Memory Model?

Đọc optimistic **không giống** một read lock đầy đủ. Trong giai đoạn đọc thử, reader không giữ monitor/read lock để buộc writer đứng ngoài. Những lần đọc từng trường có thể quan sát giá trị ở các thời điểm khác nhau.

Giao thức của `StampedLock` dùng stamp/validation để xác định có thể chấp nhận bản đọc hay phải fallback. Bởi vậy:

- Chỉ **chụp các giá trị cần thiết**, không công bố chúng trước khi xác minh.
- Không dựa vào việc các trường riêng lẻ đều là `int` nguyên tử để kết luận cặp `(x,y)` nhất quán.
- Không để writer sửa state **ngoài write lock** của cùng object.
- Không tự thực hiện side effect như gửi sự kiện, trừ tiền hoặc cập nhật map dựa trên giá trị **chưa validate**.
- Nếu validation thất bại, đọc lại **từ đầu** dưới read lock, thay vì kết hợp trường mới với trường cũ.

Với các trường tham chiếu, một lần đọc tham chiếu rồi dereference object phức tạp có thể gây lỗi **trước khi** đến được `validate` nếu object thay đổi và cấu trúc nội bộ không an toàn. Đó là lý do các ví dụ trong bài chủ động dùng các trường primitive đơn giản và công bố snapshot dưới dạng immutable record.

`validate(stamp)` không “đóng băng” state sau khi trả true. Sau khi validate thành công, dữ liệu chung có thể lại thay đổi. **Chỉ snapshot local đã chụp** là dữ liệu ta có thể dùng như kết quả của lần đọc; một phép đọc bổ sung từ shared fields là thao tác mới và cần bảo vệ riêng.

## 7. Đọc lạc quan không phải là optimistic locking cho mọi tình huống

Dễ nhầm hai loại “optimistic”:

1. **`StampedLock.tryOptimisticRead()`:** cho phép đọc thử các trường mà không giữ read lock, sau đó dùng `validate` để xem có thể tin vào snapshot không. Nếu không, đọc lại dưới read lock.
2. **Optimistic update/CAS:** đọc giá trị, chuẩn bị giá trị mới và dùng `compareAndSet` để bảo đảm trạng thái chưa đổi trước khi cập nhật. Đây là **phép cập nhật có điều kiện**, khác với xác minh một snapshot chỉ đọc.
3. **Optimistic concurrency trên hệ thống lưu trữ:** có thể dùng version hoặc conditional update tại nguồn chân lý; nó không tự liên quan đến stamp của `StampedLock` trong JVM.

**Không được** dùng `tryOptimisticRead()` → `validate()` → sau đó sửa field như thể đã lấy write lock. Writer khác có thể chen vào ngay sau validate, và bản thân optimistic stamp **không trao quyền ghi**. Muốn sửa state được bảo vệ, phải lấy `writeLock()` (hoặc chuyển đổi từ một lock hiện có theo API đúng) rồi **kiểm tra lại điều kiện dưới write lock**.

## 8. `StampedLock` không reentrant: bẫy rất quan trọng

Khác với intrinsic monitor của `synchronized` và `ReentrantLock`, **`StampedLock` không có tính tái nhập**.

Tình huống nguy hiểm:

```java
// Snippet nguy hiểm: cùng thread đã giữ write lock.
long stamp = lock.writeLock();
try {
    helper();
} finally {
    lock.unlockWrite(stamp);
}

// helper() lại gọi lock.writeLock() trên chính lock đó.
```

Đây là snippet minh họa một thiết kế nguy hiểm, không phải chương trình có thể chạy độc lập. Nếu `helper` gọi `writeLock()` lần nữa trong khi thread hiện tại đang giữ write lock, nó có thể **tự chặn vô thời hạn**. `StampedLock` không theo dõi owner theo cách cho phép reentry.

Các bẫy tương tự:

- Giữ write lock rồi gọi một getter tự lấy read lock của cùng `StampedLock`.
- Giữ read lock rồi gọi setter yêu cầu write lock mà không giải phóng/chuyển đổi hợp lệ.
- Giữ read lock rồi chờ worker cần write lock mới có thể hoàn tất.
- Một helper nội bộ luôn tự lấy lock dù caller đã giữ một stamp hợp lệ.

**Cách thiết kế:** chia rõ public methods chịu trách nhiệm lấy khóa và private helpers yêu cầu caller đã có khóa. Có thể truyền state/snapshot hoặc thao tác trực tiếp bên trong vùng đang khóa, nhưng phải quy định tiền điều kiện của helper. Không gọi lại public getter/setter có thể tự chặn khi một stamp còn đang được giữ.

## 9. Chuyển đổi stamp bằng `tryConvertToWriteLock`

`StampedLock` hỗ trợ thử chuyển đổi giữa các chế độ thông qua `tryConvertToWriteLock(stamp)`, `tryConvertToReadLock(stamp)` và `tryConvertToOptimisticRead(stamp)` theo điều kiện hợp lệ của stamp và trạng thái lock.

**Quan trọng:** `tryConvertToWriteLock(stamp)` có thể trả về **`0L` nếu thất bại**. Không được giả định chuyển đổi luôn thành công. Khi thành công, phải dùng **stamp được trả về** cho các thao tác tương ứng; khi thất bại, **stamp gốc không tự được nhả**, và caller phải xử lý việc giải phóng hoặc thử lại theo giao thức của mình.

Ví dụ tình huống: cần đảm bảo cache được khởi tạo đúng một lần. Bắt đầu dưới read lock để kiểm tra `initialized`; nếu chưa, thử chuyển sang write lock; nếu thất bại thì nhả read lock, lấy write lock và **kiểm tra lại điều kiện** vì thread khác có thể đã khởi tạo trong khoảng chuyển khóa.

### Java 17+: khởi tạo một lần bằng conversion có fallback

Tạo file `StampedInitialize.java`:

```java
import java.util.concurrent.locks.StampedLock;

public class StampedInitialize {
    private final StampedLock lock = new StampedLock();
    private boolean initialized;
    private int value;
    private int initializationCount;

    public int getOrInitialize() {
        long stamp = lock.readLock();
        try {
            while (!initialized) {
                long writeStamp = lock.tryConvertToWriteLock(stamp);
                if (writeStamp != 0L) {
                    stamp = writeStamp;
                    value = 42;
                    initializationCount++;
                    initialized = true;
                    break;
                }

                lock.unlockRead(stamp);
                stamp = lock.writeLock();
                // Phải kiểm tra lại initialized khi đã có write lock.
            }
            return value;
        } finally {
            lock.unlock(stamp);
        }
    }

    public int initializationCount() {
        long stamp = lock.readLock();
        try {
            return initializationCount;
        } finally {
            lock.unlockRead(stamp);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        StampedInitialize cache = new StampedInitialize();
        int[] results = new int[2];

        Thread a = new Thread(() -> results[0] = cache.getOrInitialize());
        Thread b = new Thread(() -> results[1] = cache.getOrInitialize());
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Values: [" + results[0] + ", " + results[1] + "]");
        System.out.println("Initialization count: "
                + cache.initializationCount());
    }
}
```

Chạy:

```bash
javac StampedInitialize.java
java StampedInitialize
```

Đầu ra khi chương trình hoàn tất bình thường:

```text
Values: [42, 42]
Initialization count: 1
```

**Giải thích vòng lặp:**

- Nếu read stamp chuyển sang write stamp thành công, thread đó có quyền cập nhật và đánh dấu `initialized = true`.
- Nếu chuyển đổi thất bại, thread nhả **read lock** trước, sau đó lấy **write lock**. Khoảng chuyển có thể cho thread khác khởi tạo; vì vậy điều kiện `while (!initialized)` phải được đánh giá lại **sau** khi đã có write lock.
- Nếu đã lấy write lock nhưng `initialized` vẫn false, lần gọi `tryConvertToWriteLock` với write stamp hợp lệ cho phép tiếp tục với write mode. Nếu thread khác đã khởi tạo, vòng lặp bỏ qua bước ghi.
- `lock.unlock(stamp)` trong `finally` dùng **stamp hiện hành**, cho dù lúc đó đang ở read mode hay write mode; API `unlock(stamp)` hỗ trợ nhả lock theo stamp hợp lệ của chế độ đang giữ. Chỉ nhả đúng một lần cho acquisition còn hiệu lực.

Đây là một ví dụ có chủ đích để giới thiệu conversion. Khi nhu cầu khởi tạo một lần đơn giản, `synchronized` hoặc một immutable holder có thể dễ bảo trì hơn. Conversion không phải lựa chọn mặc định cho mọi getter có thể ghi.

## 10. Các API đọc/ghi liên quan và cách dùng stamp an toàn

`StampedLock` còn có `tryReadLock()`, `tryWriteLock()`, các overload timeout, `readLockInterruptibly()` và `writeLockInterruptibly()`. Các API này phục vụ **lấy khóa thực**; đừng nhầm với `tryOptimisticRead()` là phép lấy dấu hiệu đọc không khóa.

Các nguyên tắc thực hành:

- **Lock acquisition trả stamp dùng một lần theo vòng đời giữ khóa.** Không lưu stamp lâu dài vào cache để dùng lại sau khi nhả.
- `unlockRead(stamp)` chỉ dùng với read stamp đang giữ; `unlockWrite(stamp)` chỉ dùng với write stamp đang giữ. Dùng stamp không hợp lệ/không phù hợp có thể ném `IllegalMonitorStateException`.
- `unlock(stamp)` dùng được với read hoặc write stamp hợp lệ đang giữ, nhưng **không** dùng để nhả optimistic stamp.
- Không dùng stamp như số version nghiệp vụ, ID transaction hoặc token an toàn xuyên process.
- `StampedLock` không theo dõi ownership theo cách giống `ReentrantLock`; việc chuyển stamp qua thread khác về mặt API không giống một khóa reentrant theo thread. Trừ khi thiết kế thật sự cần và được kiểm chứng, nên để thành phần lấy khóa chịu trách nhiệm nhả nó trong cấu trúc `try/finally` rõ ràng.
- Nếu một thread bị interrupt khi đang giữ khóa, lock **không tự nhả**; đoạn code phải bảo đảm `finally` chạy. Các phương thức interruptible acquisition khai báo `InterruptedException` cần được xử lý hoặc truyền tiếp.
- Khi conversion thất bại (trả 0), **không** gọi unlock theo mode mà chưa lấy được; phải quản lý stamp đang giữ trước đó theo hợp đồng API.

## 11. Khi nào `StampedLock` có thể hiệu quả hơn?

**Thường đáng cân nhắc khi** số lần đọc rất lớn, ghi hiếm, snapshot gồm vài trường đơn giản, nội dung đọc thử rẻ và khả năng validate thành công cao. Vì optimistic read không phải tranh read lock với writer, nó có thể giảm chi phí ở một số hệ thống.

**Thường không phù hợp khi:**

- Writer thường xuyên cập nhật: validation thất bại nhiều, reader phải làm hai lần đọc và thêm fallback.
- Snapshot cần duyệt/đọc một collection mutable phức tạp: bản đọc thử có thể không an toàn **trước khi validate**.
- Các phương thức gọi lồng nhau cần reentrancy: `StampedLock` có thể tự chặn.
- Có nhiều thao tác cần điều kiện chờ: `StampedLock` không cung cấp trực tiếp `Condition` giống `ReentrantLock`.
- Khóa đọc/ngắn ít tranh chấp: overhead triển khai optimistic read có thể không đáng giá.
- Yêu cầu fairness hoặc giới hạn thời gian phản hồi nghiêm ngặt: `StampedLock` không cam kết chính sách fairness và có thể xuất hiện starvation khi contention; hãy đo và thiết kế timeout/cancellation phù hợp.
- State chỉ có một giá trị đơn có thể cập nhật bằng `AtomicReference` hoặc snapshot immutable: một thiết kế atomic có thể đơn giản hơn.

### So sánh với các cách đồng bộ khác

| Cách | Điểm mạnh | Giới hạn chính |
| --- | --- | --- |
| `synchronized` | Đơn giản, reentrant, tự nhả monitor khi thoát scope | Mọi reader cùng monitor có thể loại trừ nhau |
| `ReentrantReadWriteLock` | Nhiều reader song song, writer độc quyền, lock reentrant | Reader phải lấy read lock thực; writer có thể bị cạnh tranh |
| `StampedLock` read/write | Nhiều reader hoặc một writer, hỗ trợ conversion | Không reentrant; quản lý stamp thủ công |
| `StampedLock` optimistic read | Đọc thử không khóa; validate rồi fallback | Dữ liệu đọc thử cần an toàn, writer có thể gây retry |
| Immutable snapshot + `AtomicReference` | Reader lấy reference bất biến nhất quán, dễ reasoning | Writer có thể cần xây snapshot mới và CAS/retry |

**Không mặc định “StampedLock nhanh hơn”:** tốc độ còn tùy độ dài critical section, số reader/writer, core CPU, chi phí validation, tỷ lệ fallback, cấu trúc dữ liệu và chính JVM. Hãy benchmark với JMH hoặc workload đo thực tế; quan sát latency, throughput, lock contention và tỷ lệ validation thất bại.

## 12. Những lỗi phổ biến cần tránh

1. **“Optimistic read đã giữ khóa.”** Sai: nó không ngăn writer; bắt buộc validate.
2. **“`tryOptimisticRead()` luôn cho stamp hợp lệ.”** Sai: có thể trả `0L` khi write lock đang được giữ; validate sẽ không xác nhận stamp ấy.
3. **“Validate trước rồi mới đọc field.”** Sai: cần đọc dữ liệu vào local **trước**, validate **sau**, rồi chỉ dùng local đã kiểm tra.
4. **“Validate thành công thì field chia sẻ không thể thay đổi nữa.”** Sai: writer có thể bắt đầu sau validation; không đọc lại shared fields như phần của snapshot cũ.
5. **“Validation thất bại thì dùng tạm dữ liệu đã đọc.”** Sai: phải bỏ snapshot thử và fallback/read lại theo giao thức đúng.
6. **“Mọi object mutable đều có thể truy cập sâu rồi validate.”** Sai: dereference/index/duyệt collection có thể lỗi hoặc gây side effect trước khi validate.
7. **“StampedLock là ReentrantLock có thêm optimistic mode.”** Sai: `StampedLock` **không reentrant**.
8. **“Chuyển read → write luôn thành công.”** Sai: `tryConvertToWriteLock` có thể trả `0L`; nhả lock đúng và kiểm tra lại state sau khi lấy write lock.
9. **“Optimistic stamp cũng phải unlock.”** Sai: stamp này không biểu thị lock đang giữ.
10. **“Lấy hai lần read/write lock rồi unlock một lần là được.”** Không có reentrancy theo kiểu monitor; có thể kẹt hoặc làm sai vòng đời stamp.
11. **“Chỉ writer bên trong StampedLock là đủ.”** Sai nếu có code path khác đọc/ghi state bỏ qua policy bảo vệ.
12. **“Tăng số thread là benchmark chứng minh hiệu quả.”** Chưa đủ: cần so sánh cùng workload, có warm-up, tỉ lệ đọc/ghi đại diện và độ tin cậy thống kê.

## 13. Checklist khi áp dụng vào class Java thực tế

1. **Xác định invariant:** các trường nào phải nhất quán trong cùng một snapshot?
2. **Đóng gói state:** biến và `StampedLock` nên là private; mọi writer cùng sử dụng `writeLock()`.
3. **Quy định cách đọc:** đọc thử local, `validate(stamp)` và fallback `readLock()` nếu cần.
4. **Không side effect trước validate:** không in log quyết định nghiệp vụ, không sửa state hay gọi callback từ dữ liệu chưa hợp lệ.
5. **Kiểm soát tham chiếu mutable:** ưu tiên primitive và immutable snapshot, không duyệt collection mutable chưa được bảo vệ.
6. **Nhả đúng stamp:** write/read lock phải được unlock trong `finally`; optimistic stamp không unlock.
7. **Không giả định reentrancy:** xem lại helper gọi lồng nhau và các đường nâng cấp read → write.
8. **Conversion phải có đường thất bại:** nếu nhận `0L`, xử lý stamp cũ, lấy lock thích hợp rồi kiểm tra lại điều kiện.
9. **Xử lý lỗi/interrupt/timeout:** không để stamp bị thất lạc hoặc thread khác chờ vô hạn.
10. **Đo trước và sau:** tỷ lệ validation thành công, số lần fallback, contention, throughput và latency dưới tải đọc/ghi thực.

**Ghi nhớ:** `StampedLock.tryOptimisticRead()` cho phép **đọc thử không giữ read lock**, sau đó dùng `validate(stamp)` để xác minh snapshot. Nếu validation thất bại, hãy **đọc lại từ đầu dưới `readLock()`**. Luôn quản lý đúng stamp của write/read lock, tránh reentrancy và chỉ chọn optimistic read khi dữ liệu thử an toàn cùng workload thực tế cho thấy lợi ích.