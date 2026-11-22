# Kiểm chứng đọc lạc quan bằng StampedLock trong Java 8+

> **Chủ đề cha:** Thực hành. `StampedLock` trong `java.util.concurrent.locks` có từ Java 8 và hỗ trợ ba chế độ: read lock, write lock và optimistic read. Optimistic read cho phép reader copy dữ liệu mà không giữ read lock, rồi dùng `validate(stamp)` để kiểm tra xem có writer xen vào hay không. Kỹ thuật này phù hợp với snapshot ngắn, chỉ đọc, trong cấu trúc read-heavy; candidate trước validation có thể không nhất quán và phải được loại bỏ nếu validation thất bại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt read lock, write lock và optimistic read.
2. Dùng `tryOptimisticRead()` và `validate(stamp)` đúng cách.
3. Copy field vào local variables và chỉ sử dụng chúng sau validation.
4. Fallback sang `readLock()` khi stamp bằng 0 hoặc validation thất bại.
5. Cập nhật bằng `writeLock()` và giải phóng đúng stamp trong `finally`.
6. Hiểu `tryConvertToWriteLock()` là phép chuyển đổi best-effort, có thể thất bại.
7. Xử lý object/array mutable, stamp, reentrancy, fairness và ownership.
8. So sánh `StampedLock` với `synchronized`, `ReentrantReadWriteLock` và immutable snapshot.
9. Kiểm thử một interleaving có writer/reader thực sự bằng latch và xác minh snapshot fallback.
10. Biết benchmark và giới hạn trước khi dùng trong production.

## 2. Vì sao cần optimistic read?

Một cấu trúc có thể được nhiều thread đọc nhưng chỉ ít thread cập nhật: tọa độ, cấu hình runtime, trạng thái hiển thị hoặc snapshot metadata. Read lock cho phép nhiều reader chạy song song, nhưng writer vẫn phải đợi reader đang giữ khóa kết thúc.

`StampedLock` bổ sung optimistic read. Reader lấy một stamp quan sát trạng thái lock, đọc những giá trị cần thiết mà không giữ read lock, rồi xác thực stamp. Nếu không có writer lấy write lock trong khoảng đó, snapshot được chấp nhận. Nếu writer xen vào, reader bỏ candidate và đọc lại dưới read lock.

| Chế độ | API | Writer có thể chạy đồng thời? | Kết thúc |
| --- | --- | --- | --- |
| Read lock | `readLock()` | Không | `unlockRead(stamp)` |
| Write lock | `writeLock()` | Không có reader/writer khác | `unlockWrite(stamp)` |
| Optimistic read | `tryOptimisticRead()` | Có thể bắt đầu bất cứ lúc nào | `validate(stamp)`; không unlock |

Optimistic read **không phải read lock nhẹ**. Nó không giữ khóa và không ngăn writer bắt đầu. Stamp chỉ giúp kiểm tra sau đó xem quan sát có bị write lock làm mất hiệu lực hay không.

### 2.1. API Java 8

`StampedLock` được giới thiệu từ Java 8. Các method cốt lõi có sẵn trong Java 8:
- `tryOptimisticRead()`, `validate(long)`.
- `readLock()`, `writeLock()`, `unlockRead(long)`, `unlockWrite(long)`, `unlock(long)`.
- `tryReadLock()`, `tryWriteLock()` và các overload có timeout.
- `tryConvertToReadLock(long)`, `tryConvertToWriteLock(long)`, `tryConvertToOptimisticRead(long)`.
- `readLockInterruptibly()` và `writeLockInterruptibly()`.

Các helper `StampedLock.isReadLockStamp`, `isWriteLockStamp`, `isLockStamp` và `isOptimisticReadStamp` chỉ có từ Java 10. Ví dụ Java 8 trong bài không dùng chúng.

## 3. Stamp là gì?

Mỗi thao tác acquire/conversion thành công trả về một giá trị `long` gọi là *stamp*. Stamp đại diện cho trạng thái/chế độ lock mà thao tác đó tạo ra. Khi unlock hoặc convert, truyền đúng stamp tương ứng.

```java
StampedLock lock = new StampedLock();

long stamp = lock.writeLock();
try {
    updateSharedState();
} finally {
    lock.unlockWrite(stamp);
}
```

Nguyên tắc:
- `readLock()` và `writeLock()` trả stamp để giải phóng lock.
- Các method `tryReadLock()`/`tryWriteLock()` trả 0 nếu không acquire được ngay.
- `tryOptimisticRead()` trả stamp khác 0 nếu tại thời điểm gọi không có writer giữ write lock; nếu writer đang giữ khóa, trả 0.
- `validate(0)` luôn false.
- Optimistic read không acquire read lock, vì vậy không gọi `unlockRead` hoặc `unlock` cho optimistic stamp.
- Không tự tạo stamp, không lưu stamp thành token nghiệp vụ dài hạn và không dùng nó để xác thực bảo mật.

Stamp không phải thread ID hay bằng chứng ownership. `StampedLock` không theo dõi thread sở hữu; một thread có thể giải phóng lock bằng stamp do thread khác lấy. Giữ stamp cục bộ theo operation để tránh dùng nhầm.

## 4. Luồng optimistic read

Các bước đúng:

1. Gọi `tryOptimisticRead()`.
2. Copy các field cần thiết vào local variables.
3. Gọi `validate(stamp)`.
4. Nếu true, dùng các local values. Nếu false, bỏ chúng và copy lại dưới `readLock()`.

```text
Reader                                  Writer
  |                                       |
  |-- tryOptimisticRead() ----------------|
  |-- copy x, y vào locals                |-- writeLock()
  |                                       |-- cập nhật x, y
  |-- validate(stamp)                     |-- unlockWrite()
  |   false                               |
  |-- loại candidate                      |
  |-- readLock() -------------------------|
  |   đợi writer kết thúc                 |
  |-- copy lại x, y                       |
  |-- unlockRead()                        |
  |-- dùng snapshot đã kiểm chứng         |
```

Writer có thể cập nhật giữa lúc reader copy hai field. Reader có thể tạm thấy `x` từ trạng thái cũ và `y` từ trạng thái mới. Khi validation thất bại, phải loại candidate; fallback lấy read lock, đợi writer kết thúc rồi copy lại.

### 4.1. Mẫu code

```java
long stamp = lock.tryOptimisticRead();

double currentX = x;
double currentY = y;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        currentX = x;
        currentY = y;
    } finally {
        lock.unlockRead(stamp);
    }
}

return new Snapshot(currentX, currentY);
```

Nếu writer đang giữ write lock ngay khi gọi `tryOptimisticRead()`, stamp là 0. Reader có thể đọc candidate vào locals nhưng `validate(0)` false, nên phải fallback. Nếu writer bắt đầu sau khi stamp được cấp, validation cũng thất bại.

### 4.2. Validation bảo đảm điều gì?

`validate(stamp)` trả true khi lock không bị acquire ở write mode kể từ lúc stamp được cấp. Khi validation thành công, các thao tác trước lần write unlock gần nhất được bảo đảm happens-before những thao tác sau lần `tryOptimisticRead()` theo memory-consistency contract của API.

Validation **không giữ khóa cho tương lai**. Writer có thể bắt đầu ngay sau khi validate trả true. Local primitive values đã copy không tự thay đổi, nhưng reference tới object mutable vẫn có thể trỏ tới object tiếp tục bị sửa. Hãy copy đủ dữ liệu hoặc dùng object immutable.

### 4.3. Không tính toán trên candidate chưa validate

Đoạn sau sai về mặt thiết kế:

```java
long stamp = lock.tryOptimisticRead();
double distance = Math.hypot(x, y);
if (!lock.validate(stamp)) {
    // distance đã được tính từ dữ liệu có thể trộn phiên bản.
}
```

Thay vào đó, copy local, validate, fallback nếu cần, rồi mới tính:

```java
long stamp = lock.tryOptimisticRead();
double currentX = x;
double currentY = y;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        currentX = x;
        currentY = y;
    } finally {
        lock.unlockRead(stamp);
    }
}
double distance = Math.hypot(currentX, currentY);
```

Không gọi callback, I/O, method không rõ tính chất hoặc thực hiện side effect trong optimistic section. Chỉ đọc và giữ local candidate cho đến khi validation hoàn tất.

## 5. Object reference, array và dữ liệu mutable

Vấn đề phức tạp hơn khi field chứa reference:

```java
Config config = currentConfig;
int timeout = config.getTimeout();
String endpoint = config.getEndpoint();
```

Nếu writer có thể thay đổi object hoặc các field bên trong, reader có thể quan sát nhiều phiên bản khác nhau. Một lần validate không biến object mutable thành immutable.

Các lựa chọn an toàn:

1. **Immutable snapshot:** writer tạo object cấu hình mới hoàn chỉnh rồi publish reference dưới write lock; reader copy reference, validate, rồi dùng object immutable.
2. **Copy field:** reader copy mọi field cần thiết vào locals, validate, nếu thất bại thì đọc lại dưới read lock.
3. **Read lock:** nếu cần duyệt collection, gọi method trên object mutable hoặc đọc nhiều cấp object graph, giữ read lock trong toàn bộ khoảng đọc.
4. **Cấu trúc chuyên biệt:** dùng immutable data structure hoặc atomic reference nếu mô hình cập nhật phù hợp.

Không lặp qua array hoặc collection mutable trong optimistic section nếu quá trình truy cập phụ thuộc vào tính nhất quán hoặc có thể vượt giới hạn. Nếu không thể copy an toàn và validate trước khi sử dụng, dùng read lock.

**Không giả định các field đọc trong optimistic section luôn nhất quán.** Tài liệu API cảnh báo chúng có thể tạm thời không nhất quán; chỉ dùng optimistic read khi hiểu representation và biết cách xác thực.


## 6. Ghi dữ liệu bằng write lock

Mọi writer của cùng cấu trúc phải dùng cùng `StampedLock`. Write lock độc quyền:

```java
final class Point {
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

`writeLock()` có thể block. Luôn release bằng đúng stamp trong `finally`. Nếu exception xảy ra giữa hai cập nhật, finally giải phóng khóa nhưng **không rollback** field đã thay đổi. Nếu invariant phải được giữ ngay cả khi có lỗi, hãy tính trạng thái mới trước rồi publish một lần, hoặc dùng immutable state object.

### 6.1. Không có writer được bỏ qua lock

Nếu một method ghi `x` hoặc `y` mà không lấy write lock, `validate` không biết lần ghi đó xảy ra. Stamp chỉ phản ánh trạng thái của **StampedLock cụ thể**, không theo dõi mọi write trong heap. Không trộn writer dùng StampedLock với writer dùng một synchronized lock khác nếu không có giao thức đồng bộ cao hơn.

### 6.2. Không reentrant

`StampedLock` **không reentrant**. Một thread đang giữ write lock không được gọi method khác cố lấy lại cùng lock; nó có thể tự block chờ chính lock mình đang giữ. Tránh gọi callback hoặc code ngoài không rõ implementation trong critical section. Có thể tách public method acquire/release lock khỏi private helper có tên rõ, chỉ được gọi khi lock đã được giữ.

## 7. Fallback sang read lock

Fallback là phần bắt buộc. Nếu stamp bằng 0 hoặc validate false, lấy read lock rồi copy lại toàn bộ dữ liệu cần thiết.

```java
Snapshot snapshot() {
    long stamp = lock.tryOptimisticRead();
    double currentX = x;
    double currentY = y;

    if (!lock.validate(stamp)) {
        stamp = lock.readLock();
        try {
            currentX = x;
            currentY = y;
        } finally {
            lock.unlockRead(stamp);
        }
    }
    return new Snapshot(currentX, currentY);
}
```

Đừng retry bằng cách đọc không khóa trong vòng lặp vô hạn. Nếu writer liên tục cập nhật, optimistic read có thể liên tục bị invalidated. Fallback read lock tạo một đoạn đọc được bảo vệ; tuy vậy StampedLock không cam kết fairness tuyệt đối giữa reader và writer.

Có thể bỏ qua optimistic copy nếu stamp bằng 0:

```java
long stamp = lock.tryOptimisticRead();
double currentX;
double currentY;

if (stamp == 0L) {
    stamp = lock.readLock();
    try {
        currentX = x;
        currentY = y;
    } finally {
        lock.unlockRead(stamp);
    }
} else {
    currentX = x;
    currentY = y;
    if (!lock.validate(stamp)) {
        stamp = lock.readLock();
        try {
            currentX = x;
            currentY = y;
        } finally {
            lock.unlockRead(stamp);
        }
    }
}
```

Mẫu đọc local trước rồi validate cũng hợp lệ nếu mọi candidate bị loại khi stamp 0. Chọn một mẫu thống nhất, dễ review.

### 7.1. Trả về snapshot bất biến

```java
static final class Snapshot {
    final double x;
    final double y;

    Snapshot(double x, double y) {
        this.x = x;
        this.y = y;
    }
}
```

Caller có thể dùng hai giá trị độc lập với cập nhật sau đó của Point. Nếu trả về reference tới object mutable dùng chung, snapshot không còn giữ ý nghĩa đó.

## 8. Chuyển đổi giữa các chế độ

StampedLock có các method `tryConvertTo...`. Đây là conversion **best-effort, không block**; nếu không thể thực hiện ngay, method trả 0.

| Method | Ý nghĩa |
| --- | --- |
| `tryConvertToWriteLock(stamp)` | Thử chuyển stamp sang write lock |
| `tryConvertToReadLock(stamp)` | Thử chuyển sang read lock |
| `tryConvertToOptimisticRead(stamp)` | Thử nhả lock đang giữ và chuyển thành optimistic observation |

### 8.1. Optimistic read rồi muốn cập nhật

```java
long stamp = lock.tryOptimisticRead();
double currentX = x;
double currentY = y;

if (!lock.validate(stamp)) {
    return; // Candidate không hợp lệ: đọc lại hoặc bắt đầu lại.
}

if (currentX == 0.0 && currentY == 0.0) {
    long writeStamp = lock.tryConvertToWriteLock(stamp);
    if (writeStamp != 0L) {
        try {
            x = 1.0;
            y = 1.0;
        } finally {
            lock.unlockWrite(writeStamp);
        }
    } else {
        long retryStamp = lock.writeLock();
        try {
            // Điều kiện ban đầu có thể đã thay đổi.
            if (x == 0.0 && y == 0.0) {
                x = 1.0;
                y = 1.0;
            }
        } finally {
            lock.unlockWrite(retryStamp);
        }
    }
}
```

Nếu conversion thất bại, stamp trả về là 0 và không có write lock mới được cấp. Khi acquire write lock theo đường khác, điều kiện ban đầu có thể đã thay đổi; phải kiểm tra lại dưới write lock trước khi ghi.

### 8.2. Chuyển read lock sang write lock

Không block chờ write lock trong khi vẫn giữ read lock; nhiều reader cùng chờ nâng cấp có thể làm nhau kẹt. Thử conversion ngay; nếu thất bại, nhả read lock, lấy write lock rồi recheck:

```java
long stamp = lock.readLock();
try {
    while (conditionStillTrue()) {
        long writeStamp = lock.tryConvertToWriteLock(stamp);
        if (writeStamp != 0L) {
            stamp = writeStamp;
            updateWhileWriteLocked();
            break;
        }

        lock.unlockRead(stamp);
        stamp = lock.writeLock();
        // Vòng lặp kiểm tra lại điều kiện dưới write lock.
    }
} finally {
    lock.unlock(stamp);
}
```

Chỉ dùng pattern này khi hiểu chính xác mode mà stamp đang đại diện. Không gọi `writeLock()` trong khi vẫn giữ read lock.

## 9. So sánh với các cơ chế khác

| Cơ chế | Đọc đồng thời | Optimistic read | Reentrant | Fairness |
| --- | --- | --- | --- | --- |
| `synchronized` | Một thread trong monitor | Không | Có | Không có fairness option |
| `ReentrantReadWriteLock` | Nhiều reader | Không có optimistic stamp | Có | Có constructor tùy chọn fair mode |
| `StampedLock` | Nhiều reader | Có | Không | Không bảo đảm ưu tiên reader/writer |

`StampedLock` không implement trực tiếp `Lock` hoặc `ReadWriteLock` vì nó cần stamp cho acquire/release/conversion. Nó có các view `asReadLock()`, `asWriteLock()` và `asReadWriteLock()` khi cần API kiểu Lock, nhưng không cung cấp mọi khả năng của ReentrantReadWriteLock; ví dụ Condition không được hỗ trợ.

### 9.1. Khi nào đáng dùng?

Cân nhắc khi workload read-heavy rõ rệt, đoạn optimistic read ngắn, chỉ copy vài giá trị, có thể validate/fallback dễ dàng và benchmark cho thấy contention thực sự giảm. Không chọn chỉ vì tên "optimistic" nghe nhanh hơn. Nếu writer thường xuyên invalidated reader hoặc snapshot phức tạp, retry có thể tốn hơn read lock.

### 9.2. Khi nào chọn giải pháp khác?

- `synchronized` cho critical section nhỏ và code đơn giản.
- `ReentrantReadWriteLock` khi cần reentrancy hoặc fairness option.
- Immutable snapshot + `AtomicReference` khi writer tạo state object mới rồi publish một reference.
- Concurrent collections khi vấn đề nằm ở collection thay vì invariant gồm nhiều field.

## 10. Giới hạn và lưu ý

- **Không reentrant:** tránh nested acquisition trên cùng instance.
- **Không ownership:** stamp không gắn với thread.
- **Không fairness guarantee:** scheduling không luôn ưu tiên reader hay writer; method try là best-effort.
- **Không phải security token:** stamp hữu hạn, không cryptographically secure và có thể tái sử dụng sau thời gian vận hành dài.
- **Không bảo vệ writer bỏ qua lock:** mọi thao tác ghi phải dùng cùng instance.
- **Không giữ stamp lâu:** dùng cho một operation ngắn rồi validate/unlock/convert.
- **Không side effect trong optimistic read:** không gửi dữ liệu ra ngoài hoặc thay đổi state dựa trên candidate chưa validate.
- **Không dùng monitoring thay synchronization:** `isReadLocked()`, `isWriteLocked()`, `getReadLockCount()` và `toString()` chỉ phản ánh trạng thái quan sát; không thay thế acquire/validate.



## 11. Chương trình Java 8 hoàn chỉnh

Demo dùng một điểm có invariant `x == y` để tạo tình huống kiểm thử xác định. Writer lấy write lock, cập nhật `x` rồi tạm dừng trước khi cập nhật `y`. Reader lấy optimistic stamp trong lúc writer vẫn giữ khóa, copy candidate `(2,1)`, sau đó validation thất bại. Reader bỏ candidate này, đợi read lock rồi copy lại `(2,2)`.

Lưu thành `StampedLockOptimisticReadDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.StampedLock;

public class StampedLockOptimisticReadDemo {
    static final class Snapshot {
        final double x;
        final double y;
        final boolean retriedUnderReadLock;
        final boolean optimisticStampWasZero;
        final boolean mixedCandidateDiscarded;

        Snapshot(double x, double y, boolean retriedUnderReadLock,
                 boolean optimisticStampWasZero,
                 boolean mixedCandidateDiscarded) {
            this.x = x;
            this.y = y;
            this.retriedUnderReadLock = retriedUnderReadLock;
            this.optimisticStampWasZero = optimisticStampWasZero;
            this.mixedCandidateDiscarded = mixedCandidateDiscarded;
        }

        @Override
        public String toString() {
            return "x=" + x + ", y=" + y;
        }
    }

    static final class Point {
        private final StampedLock lock = new StampedLock();
        private double x;
        private double y;

        Point(double x, double y) {
            this.x = x;
            this.y = y;
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

        Snapshot snapshot() {
            return snapshot(null);
        }

        private Snapshot snapshot(CountDownLatch copiedForTest) {
            long stamp = lock.tryOptimisticRead();
            boolean stampWasZero = stamp == 0L;

            double currentX = x;
            double currentY = y;
            boolean mixedCandidate = copiedForTest != null
                    && currentX != currentY;

            // Test hook: signal after copying, before validation.
            if (copiedForTest != null) {
                copiedForTest.countDown();
            }

            boolean valid = lock.validate(stamp);
            boolean retried = !valid;
            if (!valid) {
                stamp = lock.readLock();
                try {
                    currentX = x;
                    currentY = y;
                } finally {
                    lock.unlockRead(stamp);
                }
            }

            return new Snapshot(currentX, currentY, retried,
                    stampWasZero, mixedCandidate);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        Point point = new Point(1.0, 1.0);
        Snapshot initial = point.snapshot();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch writerPaused = new CountDownLatch(1);
        CountDownLatch allowWriterToFinish = new CountDownLatch(1);
        CountDownLatch readerCopied = new CountDownLatch(1);

        Snapshot recovered;
        Future<?> writer = null;
        Future<Snapshot> reader = null;

        try {
            writer = pool.submit(() -> {
                long stamp = point.lock.writeLock();
                try {
                    // The invariant in this demo is x == y.
                    point.x = 2.0;
                    writerPaused.countDown();
                    if (!allowWriterToFinish.await(2, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("writer gate timed out");
                    }
                    point.y = 2.0;
                } finally {
                    point.lock.unlockWrite(stamp);
                }
                return null;
            });

            require(writerPaused.await(2, TimeUnit.SECONDS),
                    "writer did not reach the controlled pause");

            reader = pool.submit(() -> point.snapshot(readerCopied));
            require(readerCopied.await(2, TimeUnit.SECONDS),
                    "reader did not copy its optimistic candidate");

            // The reader copied x=2 and y=1 while the writer owns
            // the write lock. Let the writer finish so the reader can
            // fall back to readLock and copy the consistent pair.
            allowWriterToFinish.countDown();

            recovered = reader.get(2, TimeUnit.SECONDS);
            writer.get(2, TimeUnit.SECONDS);
        } finally {
            allowWriterToFinish.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("executor did not terminate");
            }
        }

        point.move(1.0, 1.0);
        Snapshot afterMove = point.snapshot();

        System.out.println("initial snapshot: " + initial);
        System.out.println("optimistic stamp was zero: "
                + recovered.optimisticStampWasZero);
        System.out.println("mixed candidate was discarded: "
                + recovered.mixedCandidateDiscarded);
        System.out.println("fallback used read lock: "
                + recovered.retriedUnderReadLock);
        System.out.println("validated snapshot: " + recovered);
        System.out.println("after normal write: " + afterMove);

        require(initial.x == 1.0 && initial.y == 1.0,
                "initial snapshot mismatch");
        require(recovered.optimisticStampWasZero,
                "expected zero stamp while writer held the lock");
        require(recovered.mixedCandidateDiscarded,
                "expected a mixed candidate during the controlled write");
        require(recovered.retriedUnderReadLock,
                "reader did not fall back to read lock");
        require(recovered.x == 2.0 && recovered.y == 2.0,
                "fallback did not return a consistent snapshot");
        require(afterMove.x == 3.0 && afterMove.y == 3.0,
                "write lock update was not applied consistently");
        System.out.println("Checks passed.");
    }
}
```

Phần `snapshot(CountDownLatch)` là test hook private, chỉ để báo cho test biết reader đã copy candidate trước khi writer được phép hoàn tất. API dùng trong ứng dụng là `snapshot()`; không thêm latch hoặc chờ trong optimistic section của production code.

### 11.1. Biên dịch và chạy

Trên JDK 9+ dùng `--release 8` để kiểm tra source/API Java 8:

```bash
javac --release 8 StampedLockOptimisticReadDemo.java
java StampedLockOptimisticReadDemo
```

Trên JDK 8 dùng `javac StampedLockOptimisticReadDemo.java` rồi `java StampedLockOptimisticReadDemo`.

**Stdout thực tế đã kiểm thử trên JDK 24:**

```text
initial snapshot: x=1.0, y=1.0
optimistic stamp was zero: true
mixed candidate was discarded: true
fallback used read lock: true
validated snapshot: x=2.0, y=2.0
after normal write: x=3.0, y=3.0
Checks passed.
```

### 11.2. Giải thích từng bước

1. Snapshot ban đầu lấy optimistic stamp hợp lệ và trả về `(1,1)`.
2. Writer lấy write lock, đổi `x` thành 2 và giữ lock trong lúc chờ latch; `y` vẫn là 1.
3. Reader gọi `tryOptimisticRead()` khi writer đang giữ lock, vì vậy nhận stamp 0. Reader copy candidate `(2,1)`.
4. Test mở latch cho writer hoàn tất, writer cập nhật `y=2` rồi unlock.
5. `validate(0)` trả false. Reader loại candidate `(2,1)`, lấy read lock và copy lại `(2,2)`.
6. Sau đó một lần `move(1,1)` bình thường cho snapshot `(3,3)`.
7. Các assertion xác nhận cả invalidation lẫn fallback đều đã xảy ra; `Checks passed` chỉ in khi mọi điều kiện đúng.

Đây là test interleaving có điều khiển bằng CountDownLatch, không dựa vào Thread.sleep hoặc hy vọng scheduler tạo đúng race. Writer/reader đều chạy trên executor và Future có timeout để test không chờ vô hạn.

## 12. Kiểm thử StampedLock trong ứng dụng

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Không có writer trong lúc đọc | Optimistic stamp được validate, snapshot đúng |
| Writer giữ write lock trước optimistic read | Stamp 0, validation false, fallback read lock |
| Writer bắt đầu sau khi lấy stamp | Validation false, candidate bị loại |
| Writer cập nhật nhiều field trong cùng critical section | Reader không trả snapshot trộn phiên bản |
| Writer ném exception | Write lock vẫn được giải phóng trong finally |
| Optimistic read liên tục bị invalidated | Có fallback/retry hữu hạn hoặc policy rõ |
| Conversion sang write lock thất bại | Không ghi khi chưa có write lock; recheck sau khi acquire |
| Nhiều reader đồng thời | Không có dữ liệu bị thay đổi bởi reader |
| Có writer bỏ qua StampedLock | Test phải phát hiện giao thức bảo vệ bị phá |
| Lock được dùng lồng nhau | Không deadlock do giả định reentrant |

Test interleaving nên dùng latch/barrier thay vì sleep. Nếu cần kiểm chứng memory-model ở nhiều JVM/CPU hoặc tìm race khó tái hiện, dùng stress test/JCStress phù hợp. Một unit test chạy qua không chứng minh mọi interleaving đều đúng.

## 13. Đo hiệu năng trước khi chọn

Optimistic read có thể giảm contention trong read-heavy workload, nhưng hiệu quả phụ thuộc tỷ lệ read/write, thời gian giữ write lock, số field cần copy, chi phí validate, tỷ lệ fallback, số thread và chi phí tạo snapshot.

Benchmark với workload đại diện, có warm-up và nhiều lần đo; JMH là công cụ phù hợp cho microbenchmark JVM. So sánh `synchronized`, `ReentrantReadWriteLock`, `StampedLock` và immutable snapshot/AtomicReference nếu mô hình dữ liệu cho phép. Đo throughput, latency percentile, số lần fallback và thời gian writer chờ. Nếu writer thường xuyên làm reader invalidated, optimistic path có thể không có lợi.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng candidate trước validate | Snapshot không nhất quán | Chỉ dùng local values sau validation |
| Nghĩ tryOptimisticRead giữ read lock | Writer vẫn chạy đồng thời | Stamp là observation, không phải lock |
| Không fallback khi stamp bằng 0 | Snapshot không được xác thực | validate false thì readLock và copy lại |
| Gọi unlockRead cho optimistic stamp | Sai trạng thái lock | Optimistic read không cần unlock |
| Đọc field nhiều lần sau validation | Các lần đọc có thể thuộc nhiều phiên bản | Copy đủ field vào locals |
| Đọc object mutable rồi dùng sau validate | Object có thể đổi sau validation | Immutable snapshot hoặc read lock |
| Có writer bỏ qua cùng StampedLock | validate không phát hiện write đó | Mọi writer dùng cùng lock instance |
| Giữ lock trong I/O/callback | Contention, nguy cơ deadlock | Critical section ngắn |
| Giả định StampedLock reentrant | Có thể tự block | Tránh nested acquisition |
| Nâng read lock bằng writeLock khi vẫn giữ read | Có thể deadlock | tryConvert hoặc release/reacquire/recheck |
| Bỏ qua kết quả tryConvert | Ghi khi chưa có write lock | Kiểm tra stamp trả về khác 0 |
| Không recheck sau khi reacquire write | Quyết định dựa trên state cũ | Kiểm tra predicate trong write lock |
| Dùng stamp như security token | Không có tính mật mã | Authentication riêng |
| Dùng isReadLocked để quyết định đồng bộ | Trạng thái đổi ngay sau khi đọc | Dùng acquire/validate thật |
| Chọn chỉ vì tên "optimistic" | Có thể chậm hơn khi write contention | Benchmark workload thực tế |

## 15. API Java 8 và các phiên bản mới hơn

Các thành phần trong demo có từ Java 8: `StampedLock`, `tryOptimisticRead`, `validate`, `readLock`, `writeLock`, `unlockRead`, `unlockWrite`, `CountDownLatch`, `ExecutorService` và `Future.get(timeout)`.

Một số helper `isReadLockStamp`, `isWriteLockStamp`, `isLockStamp` và `isOptimisticReadStamp` chỉ có từ Java 10. Không dùng chúng trong source cần biên dịch bằng Java 8. Chương trình ở trên chỉ dùng API Java 8.

## 16. Tài liệu chính thức

- [Oracle Java SE 8 — StampedLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/StampedLock.html): API Java 8, optimistic read, validate, stamp và conversion.
- [Oracle Java SE 26 — StampedLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html): semantics hiện hành, memory synchronization, non-reentrant behavior, scheduling và giới hạn stamp.
- [Java Language Specification — Chapter 17: Threads and Locks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html): Java Memory Model và happens-before.
- [Oracle Java SE 26 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): đối chiếu read/write locking và fair mode.
- [OpenJDK — StampedLock source](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/concurrent/locks/StampedLock.java): implementation và ghi chú về optimistic reads.

**Ghi nhớ:** Optimistic read không khóa writer. Reader copy dữ liệu vào local variables rồi validate stamp; nếu validation thất bại hoặc stamp bằng 0, phải bỏ candidate và đọc lại dưới read lock. Mọi writer phải dùng cùng StampedLock. Chọn cơ chế này cho snapshot ngắn, read-heavy và có thể kiểm chứng; benchmark trước khi đưa vào production.
