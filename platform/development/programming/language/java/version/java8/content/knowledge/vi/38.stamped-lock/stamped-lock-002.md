# Stamp và vòng đời một lần giữ khóa trong StampedLock (Java 8)

## Mục tiêu bài học

`StampedLock` trong `java.util.concurrent.locks` cung cấp ba chế độ: **write lock** (ghi độc quyền), **read lock** (đọc chia sẻ) và **optimistic read** (đọc lạc quan). Khác nhiều cơ chế khóa quen thuộc, phương thức lấy quyền truy cập trả về **`long stamp`**, còn việc giải phóng/chuyển chế độ cần truyền chính stamp phù hợp với trạng thái lock hiện tại.

Trong một lần giữ khóa:

```java
long stamp = lock.writeLock();
try {
    // Chỉ tại đây mới được truy cập dữ liệu dưới write lock.
} finally {
    lock.unlockWrite(stamp);
}
```

Nhưng không phải mọi stamp đều là một lock hold. Stamp do `tryOptimisticRead()` tạo ra chỉ dùng để **xác thực** bản đọc bằng `validate(stamp)`; không có read lock nào cần unlock. Ngược lại, `tryWriteLock()` và `tryReadLock()` có thể trả **0L**, nghĩa là không lấy được khóa, vì thế cũng không được gọi unlock.

Bài này làm rõ **vòng đời của stamp từ acquire đến release**, ba chế độ khóa, các quy tắc `try...`, chuyển đổi mode và cập nhật stamp, double unlock, lỗi stamp cũ, non-reentrancy, interruption, đặc tính capability-based và cách kiểm thử. Tất cả API được nêu thuộc Java 8, vẫn được hỗ trợ hiện nay. Sáu chương trình đầy đủ đã được biên dịch với `javac --release 8`, chạy và đối chiếu stdout.

**Kết luận nền tảng:** mỗi stamp phải được sử dụng đúng **lock, mode và vòng đời**. Khi thành công trong việc chuyển mode, cập nhật stamp; khi thất bại, không được làm mất stamp cũ đang giữ; khi đã thả khóa, không dùng lại stamp.

## 1. Stamp là gì?

Theo JavaDoc, trạng thái của `StampedLock` chứa **version** và **mode**. Khi acquire, API trả một stamp dạng `long` dùng để kiểm tra hoặc điều khiển quyền truy cập phù hợp với trạng thái đó. Đây là một cơ chế **capability-based**: có stamp hợp lệ là có một khả năng thao tác với lock tương ứng.

| Phương thức | Kết quả |
| --- | --- |
| `writeLock()` | Stamp write hợp lệ sau khi đã lấy quyền ghi, có thể phải chờ |
| `readLock()` | Stamp read hợp lệ sau khi đã lấy quyền đọc, có thể phải chờ |
| `tryWriteLock()` | Stamp write nếu thành công; **0L** nếu không lấy được ngay |
| `tryReadLock()` | Stamp read nếu thành công; **0L** nếu không lấy được ngay |
| `tryOptimisticRead()` | Stamp dùng quan sát nếu không đang có write lock; **0L** nếu đang giữ write lock |
| `tryConvertToWriteLock(stamp)` | Stamp write mới nếu chuyển thành công; **0L** nếu thất bại |
| `tryConvertToReadLock(stamp)` | Stamp read mới nếu chuyển thành công; **0L** nếu thất bại |
| `tryConvertToOptimisticRead(stamp)` | Stamp quan sát nếu chuyển thành công; **0L** nếu thất bại |

Không coi stamp là thread ID, transaction ID, khóa bí mật, số phiên bản nghiệp vụ hoặc token có thể serialize cho hệ thống khác. Không suy đoán bit pattern hay trị số cụ thể: API chỉ hứa các hành vi của các phương thức nhận/trả stamp.

**Một lần giữ khóa** bắt đầu khi `readLock`/`writeLock` (hoặc biến thể try) trả stamp khóa hợp lệ, và kết thúc khi `unlockRead`/`unlockWrite` tương ứng thành công hoặc được chuyển thành một mode khác theo hợp đồng conversion.

## 2. Phân biệt read, write và optimistic

| Mode | Quyền truy cập | Có giữ lock không? | Kết thúc đúng |
| --- | --- | --- | --- |
| Write | Độc quyền với các participant cùng tuân giao thức khóa | Có | `unlockWrite(writeStamp)` hoặc conversion hợp lệ |
| Read | Nhiều reader có thể đồng thời; ngăn writer lấy write lock | Có | `unlockRead(readStamp)` hoặc conversion hợp lệ |
| Optimistic read | Quan sát không khóa, có thể bị writer làm vô hiệu | **Không** | `validate(observationStamp)`, không unlock |

**Write lock** nên dùng khi cập nhật state được bảo vệ. **Read lock** dùng khi phải đọc trạng thái nhất quán qua một vùng truy cập. **Optimistic read** dùng khi đọc ngắn và có thể copy các field trước khi xác thực. Nếu dữ liệu không cho phép đọc an toàn trong trạng thái nhất thời thiếu nhất quán (ví dụ cấu trúc mutable phức tạp), chọn read lock thật.

StampedLock không thể bảo vệ code **không dùng lock**. Những trường mà lock bảo vệ nên được giữ private trong component có API đọc/ghi rõ ràng. Mọi thao tác truy cập liên quan phải theo cùng giao thức để các đảm bảo có ý nghĩa.

## 3. Vòng đời write stamp

```text
writeLock()
  |
  v
stamp ghi hợp lệ (đã có write hold)
  |
  v
try { đọc/ghi state }
  |
  v
finally { unlockWrite(stamp) }
  |
  v
lần giữ khóa kết thúc; stamp cũ không còn quyền release
```

Mẫu Java 8:

```java
// Đoạn minh họa trong class có lock và count.
void add(int value) {
    long stamp = lock.writeLock();
    try {
        count += value;
    } finally {
        lock.unlockWrite(stamp);
    }
}
```

**Tại sao finally?** Nếu phần cập nhật ném exception, lock vẫn được thả. Nếu quên unlock, các luồng tiếp theo có thể không lấy được read/write lock và ứng dụng bị treo.

**Tại sao không unlock hai lần?** Mỗi lần giữ chỉ có một trách nhiệm release. Sau lần release đầu, stamp không còn đại diện cho một write hold đang tồn tại. Lần gọi unlock thứ hai có thể ném `IllegalMonitorStateException`.

**Tại sao acquire nằm ngoài try?** Chỉ sau khi lấy lock thành công mới có stamp cần thả. Các phương thức interruptible/timed try có thể thất bại hoặc ném exception trước acquire, nên không thể blindly unlock trong finally quanh toàn bộ lời gọi acquire.

## 4. Vòng đời read stamp

```java
// Đoạn minh họa trong class có lock và count.
int current() {
    long stamp = lock.readLock();
    try {
        return count;
    } finally {
        lock.unlockRead(stamp);
    }
}
```

Read mode chỉ cung cấp **quyền đọc**, không phải quyền ghi. Nếu sửa field được bảo vệ khi chỉ có read stamp, các reader khác có thể nhìn thấy trạng thái dở dang.

Đừng dùng `unlockWrite(readStamp)` hoặc `unlockRead(writeStamp)`. Những phương thức giải phóng có kiểm tra mode/stamp so với state, không phải “unlock bất kỳ” theo ý người lập trình.

`unlock(stamp)` có thể release một read hoặc write hold phù hợp stamp, hữu ích khi code quản lý mode động sau conversion. Với code chỉ có một mode cố định, `unlockRead`/`unlockWrite` rõ nghĩa hơn.

## 5. Java 8 Demo 1 — acquire, release và double-unlock

Tệp **`BasicStampDemo.java`** minh họa hai phương thức dùng lock đúng, thử lấy write lock khi có read lock và cố tình unlock bằng stamp cũ một lần nữa.

```java
import java.util.concurrent.locks.*;

public class BasicStampDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    static final class Counter {
        private final StampedLock lock = new StampedLock();
        private int value;

        void add(int delta) {
            long stamp = lock.writeLock();
            try {
                value += delta;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        int current() {
            long stamp = lock.readLock();
            try {
                return value;
            } finally {
                lock.unlockRead(stamp);
            }
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.add(7);
        counter.add(5);
        check(counter.current() == 12, "counter");

        StampedLock lock = new StampedLock();
        long readStamp = lock.readLock();
        boolean tryWriteFailed;
        try {
            tryWriteFailed = lock.tryWriteLock() == 0L;
        } finally {
            lock.unlockRead(readStamp);
        }

        boolean staleStampRejected = false;
        try {
            lock.unlockRead(readStamp);
        } catch (IllegalMonitorStateException ex) {
            staleStampRejected = true;
        }

        check(tryWriteFailed && staleStampRejected, "stamp lifetime");

        System.out.println("value=" + counter.current());
        System.out.println("tryWriteWhileReadIsZero=" + tryWriteFailed);
        System.out.println("doubleUnlockRejected=" + staleStampRejected);
        System.out.println("PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BasicStampDemo.java
java BasicStampDemo
```

Để bảo đảm mã chỉ sử dụng API Java 8 trên một JDK mới:

```bash
javac --release 8 -encoding UTF-8 BasicStampDemo.java
java BasicStampDemo
```

**Stdout đã kiểm chứng:**

```text
value=12
tryWriteWhileReadIsZero=true
doubleUnlockRejected=true
PASS
```

Phân tích:

- `Counter.add` lấy write stamp rồi thả trong finally đúng một lần.
- `Counter.current` lấy read stamp mới cho mỗi lần đọc.
- `tryWriteLock()` khi có read hold trả 0L.
- Cố `unlockRead(readStamp)` lần thứ hai bị từ chối; đây là lỗi được tạo **cố ý để kiểm thử**, không phải cách dùng thực tế.
- Không in giá trị số của stamp vì nó không có ngữ nghĩa nghiệp vụ ổn định.

## 6. try...Lock và nhánh không lấy được khóa

`tryReadLock()` và `tryWriteLock()` không chờ, trả **0L** khi không lấy được ngay. Vòng đời chỉ bắt đầu với stamp **khác 0**:

```java
// Snippet minh họa.
long stamp = lock.tryWriteLock();
if (stamp == 0L) {
    // Không giữ write lock; không được unlock.
} else {
    try {
        // Đã giữ write lock.
    } finally {
        lock.unlockWrite(stamp);
    }
}
```

Biến thể có timeout:

```java
// Bên trong method throws InterruptedException.
long stamp = lock.tryReadLock(100, TimeUnit.MILLISECONDS);
if (stamp == 0L) {
    // Không lấy được quyền đọc trước thời hạn.
    return;
}
try {
    // Đọc state.
} finally {
    lock.unlockRead(stamp);
}
```

`tryReadLock(long, TimeUnit)` và `tryWriteLock(long, TimeUnit)` có thể ném `InterruptedException`. Nếu bị ngắt **trước khi acquire thành công**, không có stamp mới để unlock.

**Không suy nguyên nhân quá mức từ 0L:** các phép `try` là best-effort. 0 chỉ nói thử ngay/try conversion không thành công trong điều kiện đó, không chứng minh thread nào là người giữ khóa hay lần thử tiếp theo cũng sẽ thất bại.

### Giá trị 0 với optimistic read

`tryOptimisticRead()` trả 0 khi write lock đang được giữ. `validate(0L)` luôn trả false. Stamp 0 không phải read stamp, không có lệnh `unlockRead(0L)` hợp lệ.

## 7. Optimistic stamp không giữ khóa: copy rồi validate

Với dữ liệu ngắn, có thể thử đọc lạc quan:

```java
// Snippet trong class Point có field x, y, lock.
double distance() {
    long stamp = lock.tryOptimisticRead();
    double localX = x, localY = y;

    if (!lock.validate(stamp)) {
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
```

Luồng:

1. Lấy stamp quan sát, **không giữ read lock**.
2. Copy các trường cần thiết sang biến cục bộ.
3. Validate sau khi copy.
4. Nếu validate thành công, dùng các bản copy.
5. Nếu thất bại, lấy read lock thực, copy lại, thả read stamp trong finally rồi tính toán.

Đừng gọi `unlockRead` cho optimistic stamp. Nó chưa bao giờ là read hold.

**Tại sao validate phải đứng sau copy?** Nếu validate trước, writer có thể sửa dữ liệu **sau** validate nhưng **trước** khi bạn đọc field. Chỉ validate sau khi đã lấy đủ các field cần thiết mới kiểm được bản đọc đã hoàn tất.

**Hạn chế quan trọng:** optimistic read có thể nhìn thấy các field ở những trạng thái tạm không nhất quán trước khi validate. Đừng gọi các phương thức có side effect hoặc duyệt dữ liệu mutable có thể ném exception/đụng dữ liệu sai trước khi validate. Với array, linked structure hay object có invariant phức tạp, dùng read lock thật hoặc publish immutable snapshot có thể phù hợp hơn.

## 8. Java 8 Demo 2 — validate stamp cũ sau một writer

Tệp **`OptimisticReadDemo.java`** kiểm optimistic read hợp lệ, writer làm stamp cũ mất hiệu lực và trường hợp write lock khiến `tryOptimisticRead` trả 0.

```java
import java.util.concurrent.locks.*;

public class OptimisticReadDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    static final class Point {
        final StampedLock lock = new StampedLock();
        double x = 3.0, y = 4.0;

        double distance() {
            long stamp = lock.tryOptimisticRead();
            double localX = x, localY = y;

            if (!lock.validate(stamp)) {
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

        void moveTo(double nextX, double nextY) {
            long stamp = lock.writeLock();
            try {
                x = nextX;
                y = nextY;
            } finally {
                lock.unlockWrite(stamp);
            }
        }
    }

    public static void main(String[] args) {
        Point point = new Point();

        long oldStamp = point.lock.tryOptimisticRead();
        double startDistance = point.distance();
        boolean initiallyValid = point.lock.validate(oldStamp);

        point.moveTo(6.0, 8.0);

        boolean oldValid = point.lock.validate(oldStamp);
        double currentDistance = point.distance();

        long writeStamp = point.lock.writeLock();
        boolean zeroDuringWrite, zeroValid;
        try {
            long impossibleOptimistic = point.lock.tryOptimisticRead();
            zeroDuringWrite = impossibleOptimistic == 0L;
            zeroValid = point.lock.validate(impossibleOptimistic);
        } finally {
            point.lock.unlockWrite(writeStamp);
        }

        check(startDistance == 5.0 && initiallyValid, "initial");
        check(!oldValid && currentDistance == 10.0, "updated");
        check(zeroDuringWrite && !zeroValid, "zero stamp");

        System.out.println("initialDistance=" + startDistance);
        System.out.println("initialStampValid=" + initiallyValid);
        System.out.println("oldStampValidAfterWrite=" + oldValid);
        System.out.println("currentDistance=" + currentDistance);
        System.out.println("optimisticStampZeroDuringWrite=" + zeroDuringWrite);
        System.out.println("validateZero=" + zeroValid);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 OptimisticReadDemo.java
java OptimisticReadDemo
```

**Stdout đã kiểm chứng:**

```text
initialDistance=5.0
initialStampValid=true
oldStampValidAfterWrite=false
currentDistance=10.0
optimisticStampZeroDuringWrite=true
validateZero=false
PASS
```

Trước update, Point (3,4) có distance 5.0. Sau writeLock cập nhật Point thành (6,8), stamp quan sát cũ không còn hợp lệ và distance mới là 10.0. Trong lúc write lock đang giữ, optimistic stamp nhận 0L, validate trả false.

JavaDoc nói stamp dùng representation hữu hạn, về lâu dài có thể được tái sử dụng sau thời gian hoạt động rất dài. Vì thế stamp không phải version ID bền vững để cache hay gửi qua service khác. Hãy giữ vòng đời stamp **ngắn trong một lần truy cập**.

## 9. tryConvertToWriteLock: cập nhật stamp khi thành công

`tryConvertToWriteLock(stamp)` có thể thử chuyển từ:

- Write sang write (đã giữ write phù hợp, trả stamp).
- Read sang write nếu điều kiện cho phép, ví dụ không có reader khác.
- Optimistic sang write nếu write lock có thể lấy ngay.

Nếu thành công, trả một **write stamp hợp lệ**. Khi chuyển từ read sang write, read hold cũ được chuyển/giải phóng như một phần của thao tác, do đó **không được unlockRead bằng stamp cũ**.

Mẫu:

```java
// Minh họa, stamp đang là read stamp hợp lệ.
long candidate = lock.tryConvertToWriteLock(stamp);
if (candidate != 0L) {
    stamp = candidate; // bây giờ đại diện cho write hold
    // Có quyền cập nhật state.
}
```

**Không so giá trị số giữa read stamp và write stamp để suy luận đã chuyển mode.** Chỉ dựa trên hợp đồng: giá trị trả về khác 0 là conversion thành công, và dùng stamp trả về cho mode mới.

### Chuyển thất bại: lỗi dễ gây rò rỉ read lock

Đoạn sau **sai**:

```java
// Sai: nếu convert trả 0, mất read stamp cũ.
stamp = lock.tryConvertToWriteLock(stamp);
```

Vì nếu conversion thất bại, biến stamp bị thay bằng 0 dù bạn vẫn còn read hold. Sau đó finally không thể unlock đúng read stamp ban đầu; những writer khác có thể bị kẹt.

Sửa bằng một biến tạm:

```java
long candidate = lock.tryConvertToWriteLock(stamp);
if (candidate != 0L) {
    stamp = candidate;
} else {
    // Stamp read cũ vẫn phải được giữ/giải phóng.
}
```

Khi thất bại, đừng gọi `writeLock()` blocking **trong khi vẫn giữ read lock** rồi mong nó tự upgrade. StampedLock **không reentrant**, có nguy cơ tự chờ không kết thúc. Nếu cần fallback, hãy thả read lock, lấy write lock mới, **kiểm lại điều kiện** vì state có thể thay trong khoảng không khóa.

## 10. tryConvertToReadLock và tryConvertToOptimisticRead

`tryConvertToReadLock(stamp)` có thể:

- Chuyển write→read (*downgrade*) và thả write mode.
- Giữ read mode nếu input đã là read stamp hợp lệ.
- Chuyển optimistic→read nếu có thể lấy read lock ngay.

`tryConvertToOptimisticRead(stamp)` có thể:

- Chuyển write→optimistic, **giải phóng write hold**.
- Chuyển read→optimistic, **giải phóng read hold**.
- Trả stamp quan sát hợp lệ khi input đã là optimistic.
- Trả 0 nếu không thể chuyển đúng hợp đồng.

Sau conversion read/write→optimistic **không còn lock hold để unlock**. Stamp optimistic mới chỉ cần validate nếu dùng để kiểm bản đọc. Đây là khác biệt quan trọng so với một lần downgrade write→read, vốn vẫn còn read hold cần unlock.

### Quản lý một biến stamp qua nhiều mode

Với code có conversion, có thể dùng:

```java
long stamp = lock.readLock();
try {
    long ws = lock.tryConvertToWriteLock(stamp);
    if (ws != 0L) {
        stamp = ws;
        // write mode.
    }
} finally {
    lock.unlock(stamp); // chỉ khi stamp đang là read/write hold hợp lệ
}
```

**Không đưa stamp optimistic vào finally gọi `unlock(stamp)`.** Cần thiết kế cleanup dựa trên mode/ownership thực tế. Nếu convert sang optimistic thành công, phải đánh dấu rằng read/write hold đã được thả.

## 11. Java 8 Demo 3 — read → write → read → optimistic

Tệp **`ConversionLifecycleDemo.java`** kiểm toàn bộ chuỗi conversion thành công. Mỗi lần chuyển, stamp hiện tại được cập nhật. Khi chuyển cuối cùng sang optimistic, biến stamp đại diện cho *lock hold cần unlock* được đặt về 0.

```java
import java.util.concurrent.locks.*;

public class ConversionLifecycleDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        StampedLock lock = new StampedLock();
        int[] value = {3};

        long stamp = lock.readLock();
        boolean upgraded = false, downgraded = false;
        boolean releasedToOptimistic = false;
        long observation = 0L;

        try {
            long writeStamp = lock.tryConvertToWriteLock(stamp);
            check(writeStamp != 0L, "single reader can upgrade");
            stamp = writeStamp;
            upgraded = true;
            value[0] += 4;

            long readStamp = lock.tryConvertToReadLock(stamp);
            check(readStamp != 0L, "write to read");
            stamp = readStamp;
            downgraded = true;
            check(value[0] == 7, "read under downgraded lock");

            observation = lock.tryConvertToOptimisticRead(stamp);
            check(observation != 0L, "read to optimistic");
            stamp = 0L; // old read lock already released
            releasedToOptimistic = true;
        } finally {
            if (stamp != 0L) lock.unlock(stamp);
        }

        boolean observationValid = lock.validate(observation);
        boolean lockFree = !lock.isReadLocked() && !lock.isWriteLocked();
        check(observationValid && lockFree, "optimistic state");

        System.out.println("upgradedToWrite=" + upgraded);
        System.out.println("downgradedToRead=" + downgraded);
        System.out.println("convertedToOptimistic=" + releasedToOptimistic);
        System.out.println("optimisticValidated=" + observationValid);
        System.out.println("lockFree=" + lockFree);
        System.out.println("value=" + value[0]);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 ConversionLifecycleDemo.java
java ConversionLifecycleDemo
```

**Stdout đã kiểm chứng:**

```text
upgradedToWrite=true
downgradedToRead=true
convertedToOptimistic=true
optimisticValidated=true
lockFree=true
value=7
PASS
```

Giải thích:

1. Lấy read hold.
2. Chuyển thành write hold, thay stamp read bằng write stamp.
3. Cập nhật từ 3 thành 7.
4. Downgrade write→read, tiếp tục giữ read hold.
5. Chuyển read→optimistic, read hold được thả. `observation` giữ optimistic stamp để validate.
6. `stamp=0L` trong demo là **quy ước cục bộ chỉ rằng không còn hold để unlock trong finally**, không phải stamp do conversion đã trả về; stamp optimistic thực là `observation`.
7. Không có writer chen vào nên validate true. Mọi kết quả đúng trong fixture một thread; khi có concurrency, conversion có thể thất bại và phải xử lý.

## 12. Khi có nhiều reader: chuyển read sang write có thể thất bại

Có nhiều read holds đồng thời thì một reader thường không thể trở thành writer độc quyền bằng conversion ngay. `tryConvertToWriteLock` trả 0 mà không tự hoàn tất một lần chuyển mode.

Hậu quả:

- Không sửa state nếu chưa thực sự có write stamp.
- Không vứt read stamp hiện tại.
- Nếu không cần giữ read nữa, gọi `unlockRead(readStamp)` đúng một lần.
- Nếu vẫn muốn ghi, acquire write mới và **kiểm lại điều kiện** sau khi có quyền ghi.
- Không đợi `writeLock()` trong khi vẫn giữ read hold có thể gây chặn chính mình.

Ví dụ thực tế: nhiều luồng cùng đọc một trạng thái “chưa khởi tạo”, một luồng muốn khởi tạo. Khi đã thả read và lấy write, luồng khác có thể đã khởi tạo xong. Vì thế condition “chưa khởi tạo” phải được **kiểm lại dưới write lock** để tránh tạo hai lần hoặc ghi đè giá trị.

## 13. Java 8 Demo 4 — conversion trả 0 và release read stamp gốc

Tệp **`FailedConversionDemo.java`** điều phối hai reader bằng CountDownLatch để tạo conversion thất bại một cách có kiểm soát.

```java
import java.util.concurrent.*;
import java.util.concurrent.locks.*;
import java.util.concurrent.atomic.*;

public class FailedConversionDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        StampedLock lock = new StampedLock();
        CountDownLatch otherHasRead = new CountDownLatch(1);
        CountDownLatch releaseOther = new CountDownLatch(1);
        AtomicBoolean otherReleased = new AtomicBoolean(false);

        Thread other = new Thread(() -> {
            long stamp = lock.readLock();
            try {
                otherHasRead.countDown();
                try {
                    releaseOther.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new AssertionError(ex);
                }
            } finally {
                lock.unlockRead(stamp);
                otherReleased.set(true);
            }
        }, "other-reader");

        other.start();
        otherHasRead.await();

        long stamp = lock.readLock();
        boolean conversionFailed;
        boolean oldReadReleased = false;
        try {
            conversionFailed =
                lock.tryConvertToWriteLock(stamp) == 0L;
        } finally {
            lock.unlockRead(stamp);
            oldReadReleased = true;
        }

        releaseOther.countDown();
        other.join();

        long writeStamp = lock.tryWriteLock();
        boolean newWriteAcquired = writeStamp != 0L;
        if (newWriteAcquired) lock.unlockWrite(writeStamp);

        check(conversionFailed && oldReadReleased
              && otherReleased.get() && newWriteAcquired,
              "failed upgrade");

        System.out.println(
            "upgradeReturnedZero=" + conversionFailed);
        System.out.println(
            "originalReadReleased=" + oldReadReleased);
        System.out.println(
            "otherReadReleased=" + otherReleased.get());
        System.out.println(
            "newWriteAcquired=" + newWriteAcquired);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 FailedConversionDemo.java
java FailedConversionDemo
```

**Stdout đã kiểm chứng:**

```text
upgradeReturnedZero=true
originalReadReleased=true
otherReadReleased=true
newWriteAcquired=true
PASS
```

Demo cho thấy khi có reader khác, chuyển read→write trả 0; read stamp gốc **vẫn được giải phóng** bằng unlockRead. Sau khi cả hai reader thả, write lock mới có thể được lấy. Đây không phải bằng chứng conversion “mất read lock”; read hold vẫn tồn tại đến khi code tự giải phóng.

## 14. Interruption và timeout trong vòng đời acquire

Ngoài các phương thức blocking thông thường, Java 8 có:

- `readLockInterruptibly()`.
- `writeLockInterruptibly()`.
- `tryReadLock(long, TimeUnit)`.
- `tryWriteLock(long, TimeUnit)`.

Các biến thể trên có thể ném `InterruptedException` khi luồng đang chờ bị ngắt. Nếu chưa trả stamp thành công, **không có lock hold mới**.

**Đừng nhầm StampedLock.readLock() với một phương thức phản ứng interruption giống bản interruptible.** Các phương thức blocking tiêu chuẩn không khai báo InterruptedException. Nếu hệ thống cần hủy request/shutdown, chọn API phù hợp và xử lý cờ interrupt/exception theo contract service.

### Không reentrant

StampedLock **không reentrant**. Code sau có nguy cơ tự deadlock:

```java
// Pseudocode: cố tình minh họa lỗi.
void outer() {
    long stamp = lock.writeLock();
    try {
        inner(); // inner cũng gọi writeLock() cùng StampedLock.
    } finally {
        lock.unlockWrite(stamp);
    }
}
```

Thread đang giữ write lock không được đặc cách lấy lại cùng write lock chỉ vì là cùng thread. Một helper đã được gọi trong critical section nên thao tác trên state **mà không tự acquire lại lock**, hoặc phải có hợp đồng truyền quyền rõ ràng trong phạm vi nội bộ. Nested read acquisitions cũng không nên được sử dụng dựa trên giả định reentrancy.

## 15. Java 8 Demo 5 — tryLock khi có writer và readLockInterruptibly

Tệp **`TryAndInterruptDemo.java`** giữ write lock, kiểm các lần thử acquire khác trả 0 và đánh dấu interruption của reader đang chờ.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;

public class TryAndInterruptDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        StampedLock lock = new StampedLock();
        long writeStamp = lock.writeLock();

        boolean tryReadZero, tryWriteZero, timedTryReadZero;
        AtomicBoolean interrupted = new AtomicBoolean(false);
        Thread waiter = null;

        try {
            tryReadZero = lock.tryReadLock() == 0L;
            tryWriteZero = lock.tryWriteLock() == 0L;
            timedTryReadZero =
                lock.tryReadLock(0, TimeUnit.MILLISECONDS) == 0L;

            CountDownLatch waiting = new CountDownLatch(1);
            waiter = new Thread(() -> {
                waiting.countDown();
                try {
                    long readStamp = lock.readLockInterruptibly();
                    try {
                        throw new AssertionError("must be interrupted");
                    } finally {
                        lock.unlockRead(readStamp);
                    }
                } catch (InterruptedException expected) {
                    interrupted.set(true);
                }
            }, "interruptible-reader");

            waiter.start();
            waiting.await();
            waiter.interrupt();
            waiter.join();
        } finally {
            lock.unlockWrite(writeStamp);
        }

        check(tryReadZero && tryWriteZero && timedTryReadZero,
              "try methods fail under write");
        check(interrupted.get(),
              "interruptible read responds");

        System.out.println("tryReadZero=" + tryReadZero);
        System.out.println("tryWriteZero=" + tryWriteZero);
        System.out.println(
            "timedTryReadZero=" + timedTryReadZero);
        System.out.println(
            "readInterruptObserved=" + interrupted.get());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 TryAndInterruptDemo.java
java TryAndInterruptDemo
```

**Stdout đã kiểm chứng:**

```text
tryReadZero=true
tryWriteZero=true
timedTryReadZero=true
readInterruptObserved=true
PASS
```

**Giải thích:** các phép try không lấy được quyền trong khi writer đang giữ lock, nên trả 0. Reader đang chờ bằng phương thức interruptible bị interrupt, và code ghi nhận InterruptedException. Chỉ nhánh **thực sự đã lấy được read stamp** mới có finally unlockRead. Write stamp ban đầu vẫn được mở trong finally của main.

## 16. Capability-based: stamp không xác nhận chủ sở hữu theo thread

Một điểm quan trọng: StampedLock **không gắn quyền release với thread chủ sở hữu** như `synchronized` hoặc `ReentrantLock`. Nó dùng **stamp hợp lệ và lock state** để xác định việc unlock. Vì thế một thread khác có thể dùng stamp hợp lệ do thread trước truyền sang để release.

Điều này **không có nghĩa nên chia sẻ stamp**. Nếu thread khác mở khóa quá sớm trong khi thread ban đầu vẫn đang sửa dữ liệu, invariant có thể bị phá. Quy tắc thiết kế là stamp nên private/local và một phạm vi có trách nhiệm rõ ràng quản lý acquire–release.

Stamp cũng không phải credential hay một ID version bền vững; các giá trị hữu hạn có thể được tái sử dụng sau thời gian vận hành rất dài, và StampedLock không hữu ích cho remote locking.

## 17. Java 8 Demo 6 — release từ thread khác

Tệp **`StampCapabilityDemo.java`** cố ý thực hiện cross-thread release **chỉ để kiểm chứng cơ chế capability-based**. Không sao chép mẫu truyền stamp này vào code production nếu không có giao thức ownership đặc biệt.

```java
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;

public class StampCapabilityDemo {
    static void check(boolean yes, String label) {
        if (!yes) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        StampedLock lock = new StampedLock();
        long stamp = lock.readLock();

        AtomicBoolean releasedByOtherThread =
            new AtomicBoolean(false);

        Thread other = new Thread(() -> {
            lock.unlockRead(stamp);
            releasedByOtherThread.set(true);
        }, "receiver-of-stamp");

        other.start();
        other.join();

        boolean afterReleaseFree = !lock.isReadLocked();
        boolean reusedRejected = false;
        try {
            lock.unlockRead(stamp);
        } catch (IllegalMonitorStateException expected) {
            reusedRejected = true;
        }

        long writeStamp = lock.tryWriteLock();
        boolean writeAcquired = writeStamp != 0L;
        if (writeAcquired) lock.unlockWrite(writeStamp);

        check(releasedByOtherThread.get() && afterReleaseFree,
              "stamp permits cross-thread release");
        check(reusedRejected && writeAcquired,
              "old stamp is invalid");

        System.out.println(
            "otherThreadReleasedReadLock=" +
                releasedByOtherThread.get());
        System.out.println("readLockFree=" + afterReleaseFree);
        System.out.println("staleStampRejected=" + reusedRejected);
        System.out.println("newWriteAcquired=" + writeAcquired);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 StampCapabilityDemo.java
java StampCapabilityDemo
```

**Stdout đã kiểm chứng:**

```text
otherThreadReleasedReadLock=true
readLockFree=true
staleStampRejected=true
newWriteAcquired=true
PASS
```

Đọc kết quả: thread khác có thể dùng stamp phù hợp để release read hold; stamp cũ không còn dùng release lần nữa. Việc write lock mới được lấy sau đó cho thấy read hold đã hết. Đây là **cảnh báo về ownership**, không phải đề xuất để mỗi thread gửi stamp cho thread khác bằng message queue.

## 18. IllegalMonitorStateException và những lỗi release thường gặp

`unlockRead(stamp)`, `unlockWrite(stamp)` và `unlock(stamp)` có thể ném `IllegalMonitorStateException` nếu stamp không khớp lock state. Các nguyên nhân điển hình:

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Unlock hai lần cùng một hold | Stamp cũ bị từ chối | Unlock đúng một lần |
| `unlockWrite(readStamp)` | Mode không phù hợp | Đúng unlockRead |
| `unlockRead(writeStamp)` | Mode không phù hợp | Đúng unlockWrite |
| `unlockRead(optimisticStamp)` | Optimistic không giữ read lock | Chỉ validate |
| `unlockWrite(0L)` | Không có quyền ghi đã acquire | Kiểm nonzero trước |
| Unlock bằng stamp thuộc StampedLock khác | Stamp không khớp state | Không chia sẻ stamp giữa lock |
| Dùng stamp cũ sau conversion thành công | Mode/hold đã chuyển | Dùng stamp mới |
| Ghi đè stamp read bằng 0 sau conversion fail | Rò rỉ read hold | Giữ stamp cũ đến khi release |
| Truyền stamp cho thread khác không kiểm soát | Release sớm hoặc double unlock | Giữ ownership rõ |
| Thoát phương thức không finally | Có thể rò rỉ khóa | Always finally |

Không nên bắt IllegalMonitorStateException rồi **bỏ qua** như thể đó là lỗi vô hại. Thường nó cho thấy giao thức locking sai. Nếu finally tự ném do stamp sai trong lúc try đã có exception, exception unlock có thể che nguyên nhân ban đầu, làm lỗi khó chẩn đoán hơn.

### Những điều KHÔNG nên làm với stamp

- Không in/log stamp như một transaction ID để làm khóa tra cứu.
- Không cất stamp trong database hoặc gửi sang service khác.
- Không suy mode bằng thao tác bit hoặc so stamp theo thứ tự lớn nhỏ.
- Không dùng `isReadLocked()` hay `isWriteLocked()` như một thay thế cho acquire; giá trị trạng thái có thể thay đổi ngay sau khi kiểm tra.
- Không gọi `unlockRead/Write` sau khi acquire trả 0 hoặc ném InterruptedException.
- Không có “unlock tất cả” từ một stamp. Release đúng hold của nó.
- Không dùng optimistic stamp cho truy cập viết.

## 19. Snapshot và tính nhất quán của dữ liệu

Trong cùng StampedLock, khi code dùng read/write lock đúng cách, một reader có khóa sẽ không đọc state giữa vùng cập nhật của writer có write lock. Với optimistic read, reader có thể thấy state trung gian **trước validate**. Vì thế:

- Chép field primitive vào biến local, validate sau.
- Khi validate false, đọc lại dưới read lock.
- Đừng làm I/O, publish giá trị hoặc gây side effect bằng dữ liệu optimistic chưa validate.
- Nếu dùng mutable array/linked structure có thể gây exception trước validate, đừng áp optimistic read mù quáng.
- Một immutable aggregate được publish atomically có thể là lựa chọn dễ đúng hơn cho dữ liệu phức tạp.

**StampedLock không phải database transaction.** Critical section không tự rollback mutation nếu giữa chừng có exception, không tạo durability sau process crash và không cung cấp distributed lock giữa JVM. Nếu cần atomic commit nhiều bản ghi cùng persistence, phải chọn transaction đúng với datastore.

## 20. Thiết kế component và lựa chọn công cụ

Một cấu trúc an toàn thường có:

```text
Component
  private final StampedLock lock
  private fields cần bảo vệ

  writeMethod()
    writeLock -> try update -> finally unlockWrite

  readMethod()
    readLock -> try copy -> finally unlockRead

  optimisticMethod()
    tryOptimisticRead -> copy -> validate
      nếu invalid: readLock -> copy -> unlockRead
```

Nên tránh lộ lock/stamp ra ngoài component. Nếu một helper được gọi khi đã giữ lock, helper đó **không tự lấy lại StampedLock**, vì không reentrant. Nếu phải chuyển mode, quản lý biến stamp và nhánh cleanup tường minh.

StampedLock không trực tiếp triển khai `Lock` hay `ReadWriteLock`. Nó có các view `asReadLock()`, `asWriteLock()` và `asReadWriteLock()` khi ứng dụng cần interface đó, nhưng view không xóa bản chất không reentrant và không biến optimistic mode thành một Lock interface.

StampedLock cũng không bảo đảm scheduling ưu tiên reader/writer nhất quán, hay fairness tuyệt đối. Các đường đọc optimistic có thể giảm contention với workload đọc ngắn, ít writer, nhưng cũng có chi phí validate/fallback. Hãy benchmark nhu cầu thực tế; nếu component không cần optimistic read/conversion, `synchronized` hoặc `ReentrantReadWriteLock` đôi khi đơn giản và dễ bảo trì hơn.

## 21. Ma trận kiểm thử đúng vòng đời stamp

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Write acquire rồi release trong finally | Write hold chấm dứt |
| Read acquire rồi release trong finally | Read hold chấm dứt |
| Try write khi read lock đang giữ | Trả 0L |
| Try read khi write lock đang giữ | Trả 0L |
| Try timed read không lấy được lock | Trả 0L hoặc Interruption theo contract |
| Double unlock cùng stamp | IllegalMonitorStateException |
| Unlock sai mode | IllegalMonitorStateException |
| Optimistic stamp khi writer đang giữ | 0L |
| `validate(0L)` | false |
| Optimistic stamp sau một write lock mới | validate false |
| Optimistic stamp không bị writer can thiệp | validate có thể true |
| Conversion read→write với một reader | Có thể thành công |
| Conversion read→write với reader khác | Có thể trả 0L |
| Conversion thất bại | Read stamp cũ vẫn cần quản lý |
| Conversion thành công | Cập nhật stamp và không unlock mode cũ |
| Convert write→read | Thu được read hold hợp lệ |
| Convert read→optimistic | Read hold cũ được thả |
| Interruptible read đang chờ | Bị ngắt và ném InterruptedException |
| Nested writeLock cùng StampedLock | Không được giả định reentrant |
| Cross-thread release với stamp hợp lệ | Có thể thành công; là rủi ro ownership |
| Callback throw trong vùng giữ lock | finally vẫn giải phóng |
| Writer chen giữa các field optimistic | validate invalid, fallback |
| Snapshot mutable phức tạp | Dùng read lock hoặc immutable snapshot |
| Benchmark read-heavy | Đo throughput, latency, số lần fallback |
| Fairness dưới contention | Không tự giả định thứ tự nhận lock |

### Cách kiểm thử concurrency đáng tin

Dùng `CountDownLatch` hoặc phương thức đồng bộ phù hợp để tạo thứ tự xử lý, không đoán bằng `Thread.sleep`. Có test cả đường thành công, timeout, interruption, conversion failure, exception trong vùng critical section và đảm bảo không còn lock hold sau cleanup. Đừng chỉ assert “không bị lỗi”; hãy kiểm kết quả state và invariant.

## 22. Bài tập có đáp án

**Bài 1 — đúng một lần unlock.**  
Bạn gọi `writeLock()`, sau đó cập nhật hai field. Nếu field thứ hai ném exception, làm gì?  
**Đáp án:** dùng `finally { unlockWrite(stamp); }`. Không unlock hai lần hoặc lờ lỗi unlock.

**Bài 2 — try trả 0.**  
`tryReadLock()` trả 0L; cần cleanup gì?  
**Đáp án:** không có lock hold, nên không unlockRead.

**Bài 3 — optimistic.**  
Bạn đọc x, validate true rồi đọc y. Bản đọc đã được kiểm chứng hoàn chỉnh chưa?  
**Đáp án:** chưa. Phải copy cả x/y trước validate; writer có thể thay đổi sau validate.

**Bài 4 — conversion thành công.**  
Chuyển read→write, biến `writeStamp` nonzero. Có unlockRead bằng readStamp cũ không?  
**Đáp án:** không. Mode cũ đã được chuyển; chỉ release write hold bằng stamp hợp lệ hiện tại.

**Bài 5 — conversion thất bại.**  
`tryConvertToWriteLock(readStamp)` trả 0. Có nên gán `readStamp=0`?  
**Đáp án:** không; sẽ mất token để unlockRead. Giữ read stamp, release khi thích hợp rồi re-acquire write nếu cần.

**Bài 6 — condition cũ.**  
Bạn kiểm một field dưới read lock, release read, sau đó lấy write. Có thể dùng luôn condition đã kiểm?  
**Đáp án:** không. Phải kiểm lại dưới write lock vì state có thể thay trong lúc không giữ khóa.

**Bài 7 — không reentrant.**  
Một helper tự gọi writeLock trong khi caller đã giữ writeLock của cùng StampedLock. Có sao không?  
**Đáp án:** có thể tự deadlock. Tách helper không khóa và API lấy khóa ở outer boundary.

**Bài 8 — stamp và thread.**  
Thread B nhận được stamp read hợp lệ do A truyền sang. Lock có luôn từ chối B unlock vì B không acquire không?  
**Đáp án:** không. StampedLock capability-based, không theo ownership thread; tránh truyền stamp tùy tiện.

**Bài 9 — cần interruption.**  
Một thread chờ read lock và phải phản ứng khi bị cancel. Dùng API nào?  
**Đáp án:** `readLockInterruptibly()` hoặc `tryReadLock(timeout,unit)`; nếu ném InterruptedException trước acquire thì không unlock.

**Bài 10 — dữ liệu array đang mutate.**  
Optimistic read duyệt array, writer có thể đổi cấu trúc giữa chừng. Validate cuối đã đủ an toàn?  
**Đáp án:** không nhất thiết; trước validate có thể đọc dữ liệu không nhất quán hoặc ném exception. Dùng read lock hoặc immutable snapshot.

**Bài 11 — stamp như transaction ID.**  
Có nên serialize stamp vào database để một request khác dùng tiếp?  
**Đáp án:** không, stamp chỉ gắn với trạng thái local StampedLock, không phải ID transaction/remote lease.

**Bài 12 — fairness.**  
Có chắc StampedLock ưu tiên writer đang chờ trước mọi reader mới không?  
**Đáp án:** không. Không có chính sách ưu tiên reader/writer nhất quán được bảo đảm như một quy tắc tuyệt đối.

## 23. Câu hỏi tự đánh giá

**1.** StampedLock hỗ trợ mấy mode? — Ba: write, read, optimistic.

**2.** Kiểu dữ liệu của stamp? — `long`.

**3.** Khi nào phải unlockRead? — Khi đã lấy read hold thực sự, dùng stamp tương ứng, thường trong finally.

**4.** Optimistic stamp có cần unlock không? — Không; chỉ validate sau khi đọc.

**5.** Giá trị 0 từ tryWriteLock có nghĩa gì? — Không lấy được write lock trong lần thử; không có hold để thả.

**6.** validate(0L) trả gì? — false.

**7.** Có thể dùng lại stamp sau unlock không? — Không cho hold đã kết thúc.

**8.** Conversion thành công yêu cầu gì? — Cập nhật stamp/cleanup theo mode mới.

**9.** Conversion thất bại yêu cầu gì? — Giữ stamp hiện có, không làm mất quyền cleanup.

**10.** StampedLock có reentrant? — Không.

**11.** Có gắn ownership với thread? — Không theo kiểu monitor/reentrant lock; stamp là capability.

**12.** Có dùng StampedLock cho transaction xuyên database? — Không; nó chỉ đồng bộ state trong một JVM.

**13.** Điểm rủi ro của optimistic read? — Dữ liệu trước validate có thể không nhất quán.

**14.** Vì sao nên kiểm bằng latch thay vì sleep? — Latch kiểm soát interleaving, giúp test ít phụ thuộc scheduling.

**15.** Những API nào dùng khi cần interruption? — Các biến thể interruptible hoặc timed try.

**16.** Vì sao không nên in stamp làm mã nghiệp vụ? — Nó không có ngữ nghĩa ID/version bền vững.

## Tài liệu chính thức

- [Java SE 8 — StampedLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/StampedLock.html): ba mode, stamp, tryAcquire, validate, unlock, conversion, non-reentrancy.
- [Java SE 26 — StampedLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html): xác minh API tiếp tục hiện hành.
- [Java SE 8 — Lock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/Lock.html): hợp đồng lock và phương thức interruptible.
- [Java SE 8 — ReentrantReadWriteLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/ReentrantReadWriteLock.html): phương án khác để so sánh.
- [Java SE 8 — CountDownLatch](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountDownLatch.html): test thứ tự các luồng.
- [Java SE 8 — TimeUnit](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/TimeUnit.html): đơn vị timeout của tryLock.
- [Java SE 8 — IllegalMonitorStateException](https://docs.oracle.com/javase/8/docs/api/java/lang/IllegalMonitorStateException.html): lỗi thả lock sai trạng thái.

**Ghi nhớ cuối cùng:** stamp đọc/ghi phải có vòng đời rõ **acquire → try sử dụng → finally unlock đúng một lần**; stamp optimistic chỉ là **token validate**, không giữ lock. Khi conversion thành công hãy thay stamp bằng token mode mới; khi conversion thất bại đừng làm mất stamp cũ. Không dùng stamp đã thả, không dùng giá trị 0 như hold, không lồng cùng StampedLock vì nó không reentrant và không coi stamp là quyền sở hữu gắn với một thread hay một transaction.