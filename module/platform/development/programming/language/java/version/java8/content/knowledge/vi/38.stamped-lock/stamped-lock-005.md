# StampedLock — Chuyển sang read lock khi kiểm tra thất bại (Java 8+)

## 1. Bài toán và kết luận quan trọng nhất

Một đối tượng Java lưu các trường **x** và **y** phải được nhìn thấy như một cặp nhất quán. Writer thay đổi chúng dưới **StampedLock.writeLock()**, còn reader muốn đọc nhanh bằng **tryOptimisticRead()**. Đọc optimistic không giữ read lock: writer có thể chen vào giữa hai lần đọc.

Khi **validate(optimisticStamp) trả false** hoặc khi tryOptimisticRead trả **0**, đường đọc lạc quan không đủ căn cứ để sử dụng dữ liệu. Lúc đó cần:

1. Bỏ các giá trị đọc optimistic chưa được xác thực.
2. Lấy **readLock()** thật (có thể phải chờ writer).
3. **Đọc lại tất cả các trường cần nhất quán** khi đang giữ read lock.
4. Giải phóng bằng **unlockRead(readStamp)** trong **finally**.
5. Chỉ sau đó mới tính toán, xuất bản hoặc trả kết quả.

Lỗi quan trọng phải tránh là **lấy read lock nhưng vẫn dùng các biến local từ trước khi lấy lock**. Khóa không có tác dụng hồi tố, nên không thể làm những giá trị cũ trở nên nhất quán.

Các API ở bài này vẫn tồn tại trong Java SE hiện hành; **StampedLock được giới thiệu từ Java 8** và không phải API legacy. Bài có chương trình Java 17 và ví dụ chạy được với mã nguồn target Java 8.

## 2. Ba chế độ của StampedLock và ý nghĩa của stamp

**java.util.concurrent.locks.StampedLock** hỗ trợ:

| Chế độ | Phương thức vào | Quyền truy cập | Cách kết thúc |
| --- | --- | --- | --- |
| Write lock | writeLock() | Độc quyền; chặn reader/writer khác muốn giữ lock | unlockWrite(writeStamp) |
| Read lock | readLock() | Chia sẻ với reader khác, loại trừ writer | unlockRead(readStamp) |
| Optimistic read | tryOptimisticRead() | **Không giữ một read lock thật** | validate(stamp); **không unlock** |

Các phương thức cấp lock trả một số **long stamp** đại diện cho trạng thái và mode. Stamp optimistic khác 0 chỉ biểu thị một cơ sở quan sát **có thể bị writer làm mất hiệu lực**; nó không có nghĩa đã khóa dữ liệu.

**tryOptimisticRead()** trả **0** nếu write lock đang được giữ. **validate(0)** luôn false. Khi có optimistic stamp khác 0, **validate(stamp)** kiểm tra có lần writer lấy write lock làm mất hiệu lực stamp kể từ khi lấy stamp hay không.

**Phân biệt:** read stamp đã acquire một read lock thật; optimistic stamp chưa acquire lock. Không gọi unlockRead trên optimistic stamp hoặc trên giá trị 0.

## 3. Công thức chuẩn: đọc optimistic, validate rồi fallback

Đây là method minh họa thuộc class có **int x, y** và **final StampedLock lock**:

~~~java
int readSum() {
    long optimistic = lock.tryOptimisticRead();
    int localX = 0;
    int localY = 0;

    if (optimistic != 0L) {
        localX = x;
        localY = y;
    }

    if (optimistic == 0L || !lock.validate(optimistic)) {
        long readStamp = lock.readLock();
        try {
            localX = x;
            localY = y;
        } finally {
            lock.unlockRead(readStamp);
        }
    }

    return localX + localY;
}
~~~

**Từng bước:**

- Chỉ khi stamp khác 0 mới chép optimistic fields vào locals.
- Không dùng locals cho side effect trước validate.
- Stamp 0 hoặc validate false đều đi vào fallback.
- **readLock() có thể block**, nhưng khi lấy được, writer dùng cùng StampedLock không thể sửa x,y trong thời gian reader đang giữ read lock.
- Đọc **lại cả hai field** dưới read lock; không dùng x mới và y cũ.
- **finally** giải phóng khóa kể cả khi logic đọc có lỗi.
- Optimistic stamp không cần unlock ở nhánh thành công.

**Đường đọc bình thường không cần một vòng retry vô hạn.** Sau validation thất bại, chuyển hẳn sang read lock là cách đơn giản giúp tránh busy-spin dưới writer contention.

## 4. Timeline: tại sao một cặp dữ liệu có thể bị rách về mặt logic?

Giả sử writer luôn thiết lập cặp thỏa **y = x × 10**:

~~~text
Reader                           Writer
------                           ------
stamp = tryOptimisticRead()
localX = x     // thấy x=1
                                 writeLock()
                                 x = 2
                                 y = 20
                                 unlockWrite()
localY = y     // thấy y=20
validate(stamp) == false
readStamp = readLock()
localX = x     // 2
localY = y     // 20
unlockRead(readStamp)
return (2,20)
~~~

Nếu bỏ qua validate hoặc vẫn trả (1,20), reader có thể xuất một cặp không từng được writer công bố thành trạng thái hợp lệ.

Ngay cả nếu writer **đã unlock** trước validate, optimistic stamp vẫn bị vô hiệu. Validate không chỉ hỏi "hiện đang có writer giữ lock hay không" mà còn kiểm tra write acquisition xảy ra từ lúc cấp stamp.

Một lần đọc optimistic phải **ngắn** để giảm cửa sổ writer có thể can thiệp. Nhưng kể cả ngắn, nhánh fallback vẫn phải đúng.

## 5. Không được dùng dữ liệu optimistic chưa xác thực

Mẫu sai:

~~~java
long stamp = lock.tryOptimisticRead();
int a = x;
int b = y;

if (!lock.validate(stamp)) {
    long readStamp = lock.readLock();
    try {
        return a + b; // Sai: vẫn dùng locals cũ.
    } finally {
        lock.unlockRead(readStamp);
    }
}
return a + b;
~~~

Đây là snippet trong một class có lock, x,y.

**Mẫu đúng** là gán lại cả a và b trong critical section của read lock:

~~~java
if (!lock.validate(stamp)) {
    long readStamp = lock.readLock();
    try {
        a = x;
        b = y;
    } finally {
        lock.unlockRead(readStamp);
    }
}
return a + b;
~~~

Đặc biệt tránh:

- Gửi event hoặc log giá trị nghiệp vụ từ optimistic locals trước validate.
- Chọn một nhánh thay đổi trạng thái dựa vào dữ liệu chưa validate.
- Dùng một lần đọc tham chiếu racy để duyệt ArrayList/map mutable đang bị writer sửa rồi hy vọng validate sẽ ngăn exception.
- Chỉ đọc lại một vài field rồi dùng các field optimistic còn lại.

**Validate false không thể hoàn tác side effect hoặc exception đã xảy ra trước đó.** Đường optimistic nên chỉ đọc field đơn giản vào biến local, rồi xử lý giá trị sau khi validate.

## 6. Vì sao chỉ lấy readLock sau validate false?

Đường optimistic hữu ích khi ít writer: một reader đọc một số field không cần chờ đồng thời; sau đó validate true thì dùng được dữ liệu theo hợp đồng.

Khi có writer, retry optimistic nhiều lần có thể liên tục thất bại. **readLock()** cho reader một chế độ bảo vệ rõ ràng: đọc khi writer không thể giữ write lock đồng thời.

**Ưu điểm:** tránh vòng lặp retry không giới hạn và dễ đảm bảo dữ liệu nhiều field nhất quán theo invariant.

**Đánh đổi:** readLock là blocking lock; nó không hứa thời gian hoàn tất. Khi có writer giữ lock lâu, reader có thể phải đợi. StampedLock cũng **không cam kết ưu tiên reader/writer hoặc fairness** theo một lịch cố định.

Nếu yêu cầu deadline chặt, cân nhắc **tryReadLock(timeout,unit)** hoặc **readLockInterruptibly()**, kết hợp policy lỗi/từ chối khi không lấy được khóa. Không trả lại snapshot optimistic đã invalid như một cách "tiết kiệm thời gian".

## 7. Trường hợp tryOptimisticRead() trả 0

Nếu writer đang giữ write lock, tryOptimisticRead trả 0. Tốt nhất **không cố chép dữ liệu unprotected** trong tình huống đó:

~~~java
long stamp = lock.tryOptimisticRead();
if (stamp == 0L) {
    long readStamp = lock.readLock();
    try {
        return x + y;
    } finally {
        lock.unlockRead(readStamp);
    }
}
~~~

Đây là một nhánh minh họa; khi stamp khác 0 phải có nhánh optimistic đọc + validate tương ứng.

**validate(0L) luôn false.** Không "unlock" 0 vì 0 không đại diện một lock đã được acquire. Trong chương trình thử nghiệm ở phần 13, ta cố ý gọi tryOptimisticRead khi đã giữ write lock để chứng minh số 0, **không** gọi readLock lại trong cùng thread đang giữ write lock.

## 8. Cách quản lý stamp và unlock an toàn

| Stamp | Được tạo bởi | Có phải lock thật? | Unlock phù hợp |
| --- | --- | --- | --- |
| optimistic | tryOptimisticRead | Không | Không unlock |
| readStamp | readLock/tryReadLock thành công | Có | unlockRead(readStamp) |
| writeStamp | writeLock/tryWriteLock thành công | Có | unlockWrite(writeStamp) |

Ví dụ writer:

~~~java
void set(int nextX, int nextY) {
    long writeStamp = lock.writeLock();
    try {
        x = nextX;
        y = nextY;
    } finally {
        lock.unlockWrite(writeStamp);
    }
}
~~~

**Dùng đúng stamp từ lần acquire tương ứng.** Một stamp không khớp mode/trạng thái có thể khiến unlockRead/unlockWrite ném **IllegalMonitorStateException**.

Đừng viết một khối finally duy nhất luôn gọi unlockRead(stamp) cho cả nhánh optimistic và read. Trong nhánh optimistic không có read lock để trả.

Đặt tên **optimisticStamp**, **readStamp**, **writeStamp** khi có thể để loại bớt nhầm lẫn.

## 9. tryConvertToReadLock: khi nào hữu ích và khi nào thất bại?

**tryConvertToReadLock(long stamp)** là API hiện hành dùng để **thử chuyển mode** nếu stamp vẫn khớp lock:

- Nếu stamp đang giữ **write lock**, có thể downgrade nguyên tử write → read.
- Nếu đang giữ **read lock**, có thể trả stamp read đang hợp lệ.
- Nếu là **optimistic stamp còn hiệu lực**, có thể lấy read lock không chờ nếu sẵn có.
- Nếu stamp đã lỗi thời hoặc conversion không thực hiện ngay được, kết quả là **0**.

Vì thế khi **validate(optimistic) đã false do writer can thiệp**, không nên coi tryConvertToReadLock là một cách cứu stamp cũ. Nó không thể biến dữ liệu optimistic cũ thành hợp lệ. Với stamp không còn khớp, method trả 0.

~~~java
long optimistic = lock.tryOptimisticRead();
// Writer cập nhật dữ liệu trước lúc validate.
if (!lock.validate(optimistic)) {
    long readStamp = lock.readLock();
    try {
        // PHẢI đọc lại dữ liệu.
    } finally {
        lock.unlockRead(readStamp);
    }
}
~~~

Nếu chủ động dùng conversion, **kiểm tra kết quả có khác 0 hay không**. Khi conversion thành công, dùng **stamp mới** để unlock đúng mode; khi trả 0, chưa có lock mới và không được unlockRead(0).

**Chuyển từ write → read** là một bài toán downgrade khác, không nên nhầm với fallback từ optimistic read đã thất bại.

## 10. StampedLock không reentrant

**StampedLock không hỗ trợ reentrancy theo cách ReentrantLock/ReentrantReadWriteLock làm.** Một method giữ write lock mà gọi method khác cố lấy readLock hoặc writeLock cùng StampedLock có thể tự gây deadlock.

Tương tự, một method giữ read lock mà gọi logic cần write lock không thể cứ chờ writeLock() trong khi vẫn giữ read lock rồi hy vọng upgrade.

Nếu cần chuyển read → write, có API **tryConvertToWriteLock** với điều kiện thành công riêng; nếu thất bại, phải xác định cách nhả read stamp và acquire write mới, đồng thời kiểm tra lại invariant dưới write lock.

**Trong fallback đang học, không upgrade lock.** Ta đi từ quan sát optimistic (không lock) sang một read lock mới khi validation false, đọc lại, release. Giữ flow càng nhỏ càng dễ chứng minh tính đúng.

## 11. Writer bắt buộc tuân theo cùng StampedLock

Read lock chỉ bảo vệ khỏi **những writer dùng cùng StampedLock đúng cách**. Nếu một code path gán x hoặc y trực tiếp mà không giữ write lock, nó vẫn có thể sửa dữ liệu khi reader đang giữ read lock.

~~~java
void updateBoth(int nextX, int nextY) {
    long writeStamp = lock.writeLock();
    try {
        x = nextX;
        y = nextY;
    } finally {
        lock.unlockWrite(writeStamp);
    }
}
~~~

Các reader phải chọn một trong hai đường:

- Giữ read lock trong toàn bộ phần đọc các field.
- Hoặc đọc optimistic **ngắn và an toàn**, rồi validate thành công; nếu không, fallback và **đọc lại** khi giữ read lock.

**Không thể mong lock của object A bảo vệ invariant gồm dữ liệu của object B có lock khác**, trừ khi đã xây giao thức synchronization ở cấp cao hơn.

Nếu value thuộc một object graph mutable, cần xét từng dereference và operation: optimistic read không tự biến ArrayList, HashMap hoặc object mutable thành cấu trúc an toàn cho đọc racy.

## 12. Java Memory Model và lý do validate quan trọng

Tài liệu Oracle mô tả rằng trong optimistic read, các hành động trước lần write-mode unlock gần nhất có quan hệ happens-before phù hợp với hành động sau tryOptimisticRead **nếu một validate sau đó trả true**. Khi validation false, không có bảo đảm snapshot nhất quán cho các lần đọc thực hiện giữa tryOptimisticRead và validate.

Đây không chỉ là câu chuyện "một con số version bị đổi"; nó liên quan **memory ordering và publication**.

Read lock có tác dụng synchronization của lock acquisition. Khi fallback đã acquire read lock, reader có quyền đọc các field đang được writer cập nhật dưới cùng khóa và không bị một writer khác chen vào giữa.

**Không thay validate bằng việc ngủ vài millisecond, in timestamp hoặc kiểm tra một flag tùy ý**. Những thủ thuật đó không cung cấp chính xác hợp đồng memory visibility của StampedLock.

## 13. Chương trình Java 17 hoàn chỉnh: cả fast path, fallback và contention

Chương trình **StampedLockFallbackDemo.java** dùng record **Snapshot** của Java 17. Để kiểm thử nhánh fallback một cách deterministic, method **testForcedInvalidation** chủ động tạo một write giữa copy optimistic và validate. Đây **chỉ là test hook**, không phải cách tổ chức luồng production. Phần cuối dùng 1 writer và 3 reader thực sự chạy đồng thời, kiểm tra invariant **y = x × 10**.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.StampedLock;

public class StampedLockFallbackDemo {
    record Snapshot(int x, int y, boolean fallback) {}

    static final class Point {
        private final StampedLock lock = new StampedLock();
        private int x;
        private int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        void set(int nx, int ny) {
            long writeStamp = lock.writeLock();
            try {
                x = nx;
                y = ny;
            } finally {
                lock.unlockWrite(writeStamp);
            }
        }

        Snapshot readConsistently() {
            long optimistic = lock.tryOptimisticRead();
            int localX = 0;
            int localY = 0;
            if (optimistic != 0L) {
                localX = x;
                localY = y;
            }
            if (optimistic == 0L || !lock.validate(optimistic)) {
                long readStamp = lock.readLock();
                try {
                    localX = x;
                    localY = y;
                } finally {
                    lock.unlockRead(readStamp);
                }
                return new Snapshot(localX, localY, true);
            }
            return new Snapshot(localX, localY, false);
        }

        Snapshot testForcedInvalidation(int nx, int ny) {
            long stamp = lock.tryOptimisticRead();
            int localX = x;
            int localY = y;
            set(nx, ny);
            boolean stillValid = lock.validate(stamp);
            System.out.println("validate after intervening write: " + stillValid);
            if (!stillValid) {
                long readStamp = lock.readLock();
                try {
                    localX = x;
                    localY = y;
                } finally {
                    lock.unlockRead(readStamp);
                }
                return new Snapshot(localX, localY, true);
            }
            return new Snapshot(localX, localY, false);
        }

        boolean invalidStampConversionFails() {
            long oldStamp = lock.tryOptimisticRead();
            set(3, 30);
            return lock.tryConvertToReadLock(oldStamp) == 0L;
        }

        boolean zeroStampWhileWriting() {
            long writeStamp = lock.writeLock();
            try {
                return lock.tryOptimisticRead() == 0L;
            } finally {
                lock.unlockWrite(writeStamp);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Point p = new Point(1, 10);
        System.out.println("fast: " + p.readConsistently());
        System.out.println("fallback: " + p.testForcedInvalidation(2, 20));
        System.out.println("stale conversion fails: " + p.invalidStampConversionFails());
        System.out.println("after stale conversion: " + p.readConsistently());
        System.out.println("zero while writer holds lock: " + p.zeroStampWhileWriting());

        Point shared = new Point(0, 0);
        AtomicBoolean consistent = new AtomicBoolean(true);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<?>> tasks = new ArrayList<>();
        try {
            tasks.add(pool.submit(() -> {
                try {
                    start.await();
                    for (int i = 1; i <= 4000; i++) shared.set(i, i * 10);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException(ex);
                }
            }));
            for (int n = 0; n < 3; n++) {
                tasks.add(pool.submit(() -> {
                    try {
                        start.await();
                        for (int i = 0; i < 4000; i++) {
                            Snapshot snap = shared.readConsistently();
                            if (snap.y() != snap.x() * 10) {
                                consistent.set(false);
                            }
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(ex);
                    }
                }));
            }
            start.countDown();
            for (Future<?> future : tasks) future.get(20, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
        }
        System.out.println("concurrent pair invariant: " + consistent.get());
        System.out.println("final snapshot: " + shared.readConsistently());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StampedLockFallbackDemo.java
java StampedLockFallbackDemo
~~~

**Stdout chính xác đã chạy trên JDK hiện đại với mục tiêu Java 17:**

~~~text
fast: Snapshot[x=1, y=10, fallback=false]
validate after intervening write: false
fallback: Snapshot[x=2, y=20, fallback=true]
stale conversion fails: true
after stale conversion: Snapshot[x=3, y=30, fallback=false]
zero while writer holds lock: true
concurrent pair invariant: true
final snapshot: Snapshot[x=4000, y=40000, fallback=false]
~~~

**Diễn giải:**

- Fast path với giá trị đầu (1,10) không cần fallback.
- Sau một lần writer chen vào, validate false; đọc lại dưới read lock tạo (2,20), fallback=true.
- Stamp cũ không thể chuyển thẳng thành read stamp; tryConvertToReadLock trả 0.
- tryOptimisticRead khi write lock đang được giữ trả 0.
- 1 writer cập nhật 4.000 lần; 3 reader kiểm tra mỗi người 4.000 snapshot. Tất cả snapshot đã trả thỏa y=x×10.
- Main đợi Future.get hoàn tất trước khi in final snapshot. Khi không còn writer của bài mẫu, kết quả cuối là (4000,40000).

**Lưu ý deterministic:** phần test can thiệp chủ động không phải một race ngẫu nhiên. Kiểm thử đồng thời ở cuối chỉ assert invariant, không assert tỷ lệ fallback cụ thể vì scheduling của JVM thay đổi.

## 14. Java 8 runnable: fallback không dùng record

Nếu dự án còn dùng cú pháp Java 8, StampedLock vẫn có đầy đủ các phương thức đang học. Ví dụ **StampedFallbackJava8Demo.java** sau được biên dịch bằng **javac --release 8** và chạy thành công:

~~~java
import java.util.concurrent.locks.StampedLock;

public class StampedFallbackJava8Demo {
    static final class Pair {
        private final StampedLock lock = new StampedLock();
        private int a;
        private int b;

        Pair(int a, int b) {
            this.a = a;
            this.b = b;
        }

        void set(int nextA, int nextB) {
            long ws = lock.writeLock();
            try {
                a = nextA;
                b = nextB;
            } finally {
                lock.unlockWrite(ws);
            }
        }

        String read() {
            long s = lock.tryOptimisticRead();
            int first = 0;
            int second = 0;
            if (s != 0L) {
                first = a;
                second = b;
            }
            if (s == 0L || !lock.validate(s)) {
                long rs = lock.readLock();
                try {
                    first = a;
                    second = b;
                } finally {
                    lock.unlockRead(rs);
                }
            }
            return first + "," + second;
        }

        String readWithForcedInterveningWrite() {
            long optimistic = lock.tryOptimisticRead();
            int first = a;
            int second = b;
            set(2, 20);
            boolean valid = lock.validate(optimistic);
            System.out.println("validation fails: " + !valid);
            if (!valid) {
                long rs = lock.readLock();
                try {
                    first = a;
                    second = b;
                } finally {
                    lock.unlockRead(rs);
                }
            }
            return first + "," + second;
        }

        boolean staleConversionFails() {
            long old = lock.tryOptimisticRead();
            set(3, 30);
            return lock.tryConvertToReadLock(old) == 0L;
        }
    }

    public static void main(String[] args) {
        Pair p = new Pair(1, 10);
        System.out.println("before: " + p.read());
        System.out.println("after fallback: " + p.readWithForcedInterveningWrite());
        System.out.println("tryConvert stale fails: " + p.staleConversionFails());
        System.out.println("after conversion failure: " + p.read());
    }
}
~~~

Lệnh:

~~~bash
javac StampedFallbackJava8Demo.java
java StampedFallbackJava8Demo
~~~

**Stdout:**

~~~text
before: 1,10
validation fails: true
after fallback: 2,20
tryConvert stale fails: true
after conversion failure: 3,30
~~~

Chương trình chỉ dùng API/syntax có từ Java 8. Tên file trùng tên public class. Phần readWithForcedInterveningWrite cố ý thêm write để kiểm chứng fallback; phần production nên dùng method read() thông thường.

## 15. Thêm timeout hoặc interruption cho fallback

**readLock() có thể block**, không có deadline riêng. Nếu xử lý request có thời hạn, cân nhắc phương thức hiện hành:

~~~java
long readStamp = lock.tryReadLock(100, TimeUnit.MILLISECONDS);
if (readStamp == 0L) {
    throw new IllegalStateException("Read lock unavailable");
}
try {
    // Đọc lại dữ liệu nhất quán ở đây.
} finally {
    lock.unlockRead(readStamp);
}
~~~

Đây là snippet trong method có lock và import java.util.concurrent.TimeUnit. **100 ms là số minh họa**; deadline thật do nghiệp vụ quyết định.

Hoặc:

~~~java
long readStamp = lock.readLockInterruptibly();
try {
    // Đọc lại tất cả các field.
} finally {
    lock.unlockRead(readStamp);
}
~~~

Method bao quanh cần khai báo hoặc xử lý **InterruptedException** đúng contract. Không nuốt tín hiệu interrupt một cách máy móc.

**Khi timed try trả 0, bạn chưa có read lock**: không unlockRead(0). Nếu fallback thất bại, đừng tự dùng lại các giá trị optimistic đã không validate. Hãy trả một lỗi/policy hợp lệ.

## 16. Nguyên nhân thường gặp của lỗi và deadlock

**Dùng read lock nhưng không đọc lại:** giá trị optimistic cũ vẫn có thể sai.

**Gọi unlockRead(optimisticStamp):** optimistic stamp không đại diện một read lock.

**Bỏ quên finally:** exception gây rò khóa và chặn writer.

**Writer cập nhật không qua writeLock:** giao thức nhất quán bị phá vỡ dù reader fallback đúng.

**Sử dụng dữ liệu optimistic để gây side effect trước validate:** không thể hoàn tác khi stamp false.

**Duyệt cấu trúc mutable không chịu được race:** validation không thể ngăn exception đã xảy ra trước đó.

**Cố upgrade bằng writeLock khi đang giữ readLock của cùng StampedLock:** có thể tự gây deadlock vì không reentrant.

**Gọi readLock từ method đang giữ writeLock của cùng StampedLock:** có thể tự deadlock.

**Dùng tryConvertToReadLock trên stale stamp mà không kiểm tra 0:** không có lock sau conversion thất bại.

**Retry optimistic vô hạn trong lúc writer cập nhật:** tốn CPU; fallback read lock thích hợp hơn khi đòi tiến triển.

**Giữ read lock khi gọi network, sleep hoặc chờ Future khác:** tăng contention và có thể tạo vòng đợi.

**Cho rằng readLock luôn nhanh:** cần đo workload, tỷ lệ contention và thời gian lock-held; StampedLock không hứa fairness.

## 17. Chọn StampedLock hay giải pháp đơn giản hơn?

**StampedLock optimistic read** có ích khi:

- Workload **đọc nhiều, ghi ít**.
- Dữ liệu đọc ngắn gồm một vài field dễ chép an toàn.
- Writer dùng cùng lock và invariant dễ kiểm chứng.
- Profiling cho thấy giảm read-lock contention mang lại lợi ích.

**Dùng readLock trực tiếp** thường dễ đúng hơn nếu object graph phức tạp, đọc dài, writer thường xuyên hoặc validation thất bại liên tục.

**ReentrantReadWriteLock** phù hợp ở những nơi cần tính reentrant và mô hình Lock/ReadWriteLock quen thuộc; **StampedLock không trực tiếp implements Lock/ReadWriteLock**, dù có các view asReadLock/asWriteLock/asReadWriteLock cho trường hợp phù hợp.

**Immutable snapshot + AtomicReference** có thể giúp reader đọc một reference được publish an toàn và xử lý state không đổi. Đó là kiến trúc khác, đánh đổi allocation/memory với việc giảm lock. Không chuyển sang chỉ vì một lần benchmark thiếu kiểm soát.

**Không mặc định chọn thuật toán phức tạp nhất.** Việc đọc được chứng minh đúng dưới contention quan trọng hơn tối ưu vi mô chưa đo được.

## 18. Kiểm thử nhánh fallback đúng cách

Bộ test tốt phải có:

1. **Không tranh chấp:** stamp khác 0, validate true, kết quả đúng, không fallback.
2. **Writer xen vào:** dùng latches hoặc test hook để bảo đảm write xảy ra giữa optimistic read và validate. Assert validate false và kết quả **đã đọc lại**.
3. **Writer đang giữ write lock:** tryOptimisticRead trả 0; reader biết fallback (không lấy readLock khi vẫn tự giữ writeLock trong cùng thread).
4. **Stamp stale:** tryConvertToReadLock trả 0, không làm chương trình hiểu nhầm đã giữ read lock.
5. **Nhiều reader/writer:** kiểm tra invariant của dữ liệu trả về; không assert số lần fallback cố định.
6. **Exception trong read critical section:** sau khi exception, lock được giải phóng để writer khác có thể tiếp tục.
7. **Timeout/interrupt:** nếu dùng timed/interruptible API, test luôn cả nhánh thất bại không có read stamp.
8. **Giới hạn Java:** code Java 8 không dùng record hoặc tiện ích kiểm tra stamp từ Java 10+.

**Tránh Thread.sleep để "đoán" writer đã xen vào.** Dùng CountDownLatch/Phaser hoặc test hook chủ động, với Future.get(timeout) khi test nhiều thread để tránh chạy mãi nếu có deadlock.

## 19. Checklist production

- **Giao thức:** tất cả writer của các field liên quan đều dùng writeLock của cùng StampedLock chưa?
- **Dữ liệu optimistic:** có chỉ chép field đơn giản vào local và không xử lý tiếp trước validate chưa?
- **Stamp 0:** có xử lý không optimistic trước khi đọc unprotected không?
- **Validation:** có gọi validate **sau lần đọc** và trước khi công bố kết quả không?
- **Fallback:** khi validate false, có đọc lại **toàn bộ** field dưới read lock chưa?
- **Release:** có finally unlockRead với đúng read stamp mới không?
- **Conversion:** có hiểu rằng tryConvertToReadLock có thể trả 0 và không chữa được stale data không?
- **Nonreentrant:** có call graph bất ngờ tái acquire cùng lock không?
- **Deadline:** nếu cần timeout/interruption, đã dùng API có policy phù hợp chưa?
- **Hiệu năng:** đã đo tỉ lệ fallback, lock contention và độ trễ thực tế chưa?
- **Consistency:** read lock bảo vệ đúng một invariant, hay đang nhầm nó bảo đảm snapshot nhiều object/lock khác nhau?
- **Testing:** có nhánh fast, failed validate, stamp=0, conversion=0, nhiều thread và exception safety không?

## 20. Bài tập và đáp án

**1.** validate(optimistic) false, có được trả x,y đã đọc không? — **Không**; phải bỏ locals cũ, lấy readLock và đọc lại.

**2.** tryOptimisticRead trả 0, có cần unlockRead(0) không? — **Không**; chưa hề acquire read lock.

**3.** Acquire readLock sau khi đọc x,y có tự sửa cặp stale không? — **Không**; phải đọc lại bên trong critical section.

**4.** Writer đã unlock trước validate thì stamp có thể false? — **Có**, vì write lock đã được lấy sau lúc optimistic stamp phát hành.

**5.** Vì sao cần finally? — **Để unlockRead cả khi logic đọc ném exception.**

**6.** tryConvertToReadLock(staleStamp) trả gì? — **0** khi stamp không còn khớp; không có read lock để unlock.

**7.** Optimistic read có block writer không? — **Không**; writer có thể cập nhật và làm stamp invalid.

**8.** Dùng readLock của StampedLock có reentrant không? — **Không**; gọi lồng có thể deadlock.

**9.** Nếu y=x×10, reader thấy (2,10), validate false thì sao? — **Không dùng (2,10)**; đọc lại dưới read lock.

**10.** Nếu phải trả kết quả trong 100 ms, readLock thường có deadline không? — **Không**; cân nhắc timed tryReadLock với policy khi không lấy được lock.

**11.** Object graph phức tạp có nên duyệt trong optimistic section rồi validate không? — **Không tự mặc định**; có thể ném lỗi hoặc tạo side effect trước validation.

**12.** Khi nào readLock trực tiếp tốt hơn? — Khi validation thường thất bại, dữ liệu phức tạp hoặc ưu tiên tính dễ review, sau khi đo thực tế.

## 21. Tổng kết và tài liệu chính thức

**Nguyên tắc quyết định:** optimistic read là một dự đoán có kiểm chứng, không phải read lock. Khi **validate false**, cần **đọc lại dưới read lock**, release đúng stamp và chỉ dùng kết quả đã được bảo vệ.

**Tài liệu Oracle Java SE hiện hành:**

- **StampedLock Java SE 25** — ba mode, validate, tryOptimisticRead, readLock, unlockRead, tryConvertToReadLock, cảnh báo dữ liệu racy và mẫu Point chính thức: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/StampedLock.html
- **Lock Java SE 25** — synchronization, interruption, semantics: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html
- **ReentrantReadWriteLock Java SE 25** — giải pháp thay thế theo mô hình reentrant read/write lock: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html
- **Java Language Specification, 17.4** — Java Memory Model và happens-before: https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4

**Phiên bản:** Các API StampedLock được dùng trong hai chương trình đều có từ Java 8 và tiếp tục được hỗ trợ. Chương trình Java 17 dùng record, còn chương trình Java 8 tránh các API/cú pháp mới. Tiện ích isReadLockStamp/isWriteLockStamp chỉ có từ Java 10, không được dùng trong mã target Java 8.

**Kết luận thực hành:** chuyển sang readLock khi validate thất bại là **một lần đọc lại được bảo vệ**, chứ không phải giữ nguyên kết quả optimistic cũ rồi đơn thuần acquire thêm một lock.
