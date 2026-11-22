# StampedLock: tryOptimisticRead, sao chép dữ liệu và validate

`StampedLock` thuộc `java.util.concurrent.locks`, được giới thiệu ở **Java 8** và vẫn được hỗ trợ trong Java hiện nay. Ngoài `readLock()` và `writeLock()`, nó có cơ chế **optimistic read** (đọc lạc quan) thông qua `tryOptimisticRead()` và `validate(stamp)`, nhằm giảm chi phí khóa trong trường hợp rất nhiều lượt đọc ngắn, ít lượt ghi.

Nhưng optimistic read **không phải “đọc không khóa mà luôn an toàn”**. Quy trình đúng là: **lấy stamp → sao chép đủ các trường vào biến cục bộ → validate → chỉ dùng bản sao hợp lệ**; nếu validation thất bại thì **bỏ toàn bộ bản cũ, lấy read lock, sao chép lại rồi unlock trong finally**.

Bài tập trung đúng vào `tryOptimisticRead, sao chép dữ liệu và validate`: hợp đồng JavaDoc, tính nhất quán nhiều trường, memory visibility, object và mảng mutable, immutable snapshot, giao thức writer, kiểm thử interleaving, những cạm bẫy thực tế và bảy chương trình Java 17+ độc lập với stdout được kiểm tra. API chính của StampedLock có từ Java 8; ví dụ dùng `record` sẽ ghi chú rõ yêu cầu Java 17.

## 1. Một cặp giá trị có thể bị đọc “rách”

Giả sử ứng dụng lưu tọa độ `x` và `y`. Writer cập nhật cặp theo từng lần di chuyển; reader muốn tính khoảng cách từ **một vị trí thực sự**. Nếu chỉ đọc hai biến mà không có đồng bộ, reader có thể thu được:

```text
Trước khi ghi: (x=1, y=1)
Reader đọc x=1
Writer cập nhật (x=9, y=9)
Reader đọc y=9
Kết quả reader giữ: (1,9) — cặp không từng được publish
```

Với trạng thái logic gồm nhiều trường, **mỗi lần đọc field riêng** không phải một transaction. Kể cả các field riêng là primitive hoặc volatile, không thể suy rằng tổng hợp chúng sẽ đại diện cho cùng một thời điểm.

Có thể giải quyết bằng `readLock`: reader giữ khóa trong suốt việc sao chép, writer phải chờ. Nhưng khi truy cập đọc xảy ra dày đặc mà write hiếm, nhiều lần lấy và nhả read lock có thể tạo tranh chấp không cần thiết. `tryOptimisticRead` cho phép một đường nhanh hơn **nếu bản sao thu được thực sự vượt qua validate**.

## 2. Ba chế độ StampedLock

| Chế độ | Lấy bằng | Có giữ khóa thực sự? | Kết thúc |
| --- | --- | --- | --- |
| Write | `writeLock()` | Có, độc quyền | `unlockWrite(writeStamp)` |
| Read | `readLock()` | Có, không độc quyền giữa readers | `unlockRead(readStamp)` |
| Optimistic read | `tryOptimisticRead()` | **Không**; writer vẫn có thể vào | Không unlock; gọi `validate(stamp)` |

Cả ba chế độ đều dùng một giá trị `long` gọi là **stamp**. Nó là token khóa/quan sát, **không phải UTC timestamp, thread ID, số phiên bản nghiệp vụ hoặc khóa mật mã**. Đừng lưu stamp trong database hay chuyển qua một StampedLock khác để validate.

`StampedLock` là tiện ích dành cho các thành phần thread-safe, **không reentrant**. Nó không cam kết một chính sách fairness cố định giữa readers/writers và không trực tiếp triển khai `Lock`/`ReadWriteLock`. Có các view `asReadLock()`, `asWriteLock()` và `asReadWriteLock()` nếu chỉ cần các thao tác khóa tương ứng.

## 3. Hợp đồng `tryOptimisticRead()`

```java
long stamp = lock.tryOptimisticRead();
```

- Trả `0L` nếu write lock đang bị giữ tại thời điểm gọi.
- Trả một stamp khác 0 để kiểm tra về sau nếu không có writer đang giữ write lock lúc đó.
- Không chặn đợi như `readLock()`.
- Không **ngăn** writer khác lấy write lock ngay sau đó.
- Không đảm bảo các lần đọc field tiếp theo đồng nhất khi chưa validate.
- Không cấp một read stamp có thể đưa vào `unlockRead`.

Phản ví dụ:

```java
long stamp = lock.tryOptimisticRead();
return new Snapshot(x, y); // Không validate: SAI!
```

Đây là snippet trong class đã khai báo `lock`, `x`, `y` và kiểu `Snapshot`. Stamp khác zero chỉ có nghĩa **tại thời điểm cấp stamp** không có write lock đang giữ; các lần đọc có thể trùng một lần cập nhật.

## 4. Sao chép dữ liệu **trước** khi validate

Mẫu chuẩn cho hai primitive fields:

```java
long stamp = lock.tryOptimisticRead();
double a = x;
double b = y;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        a = x;
        b = y;
    } finally {
        lock.unlockRead(stamp);
    }
}

return new Snapshot(a, b);
```

Đây là method body minh họa. Chỉ khi `validate` true, **các local copies a và b đã được lấy trước validate** mới được sử dụng. Nếu false, **bỏ cả a lẫn b**; đọc lại đủ fields trong read lock, không giữ lại một phần dữ liệu trước đó.

Có thể tránh cả việc tải field khi stamp đã bằng zero:

```java
long stamp = lock.tryOptimisticRead();
double a = 0.0, b = 0.0;

if (stamp != 0L) {
    a = x;
    b = y;
}
if (stamp == 0L || !lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        a = x;
        b = y;
    } finally {
        lock.unlockRead(stamp);
    }
}
// Chỉ dùng a, b sau một trong hai đường thành công.
```

Các số zero ban đầu chỉ là local tạm; không được đem trả về khi validation chưa thành công.

## 5. `validate(stamp)` thực sự kiểm tra điều gì?

Với optimistic stamp hợp lệ do **chính StampedLock ấy** phát, `validate` trả true nếu **không có write lock được lấy kể từ khi stamp được cấp**. Nó **luôn false** với stamp 0.

| Tình huống | Optimistic snapshot có dùng được? |
| --- | --- |
| Không writer nào lấy write lock trong lượt đọc, validate true | Có, dùng bản copy đã tải |
| Writer lấy **và đã nhả** write lock trước khi validate | Không: validate false |
| Writer đang giữ write lock khi validate | Không: validate false |
| Stamp đầu tiên bằng zero | Không: validate false |
| Writer mới xuất hiện **sau** validation thành công | Bản copy trước đó vẫn là kết quả đã xác thực; shared fields có thể đổi tiếp |

Điểm quan trọng: validate không chỉ hỏi “có writer đang giữ khóa **bây giờ** không?”. Writer chen vào giữa stamp và validate vẫn làm stamp invalid **ngay cả khi đã nhả write lock**.

**Validation không phải business validation** như “x >= 0” hay “price được phép âm”. Nếu input sai theo nghiệp vụ, phải kiểm tra riêng sau khi có snapshot đúng.

## 6. Memory visibility và happens-before

JavaDoc mô tả hợp đồng đồng bộ hóa của `StampedLock`. Các thao tác lock/unlock thích hợp có memory effects như các khóa Java. Đối với optimistic read, những hành động xảy ra trước write-lock release liên quan được bảo đảm có quan hệ happens-before phù hợp với hành động sau `tryOptimisticRead` **khi validate thành công**.

```text
Writer:
  writeLock -> update x,y -> unlockWrite
                                   |
Reader:
  tryOptimisticRead -> copy x,y -> validate == true
                                   |
                               dùng local data
```

Đây là logic API, không phải mô tả thứ tự CPU instructions cứng. Nếu validate false, **bản copy không khóa không được đảm bảo nhất quán** và phải bỏ đi hoặc dùng một protocol khác đã được chứng minh.

**Tất cả writers phải tuân thủ cùng khóa.** Một thread sửa x hoặc y mà **không lấy writeLock của object ấy** sẽ không được validate phát hiện như writer theo giao thức này, kể cả khi bạn thêm vài biến volatile.

## 7. Sai lầm: validate trước, rồi mới đọc

Phản ví dụ:

```java
long stamp = lock.tryOptimisticRead();
if (lock.validate(stamp)) {
    return new Snapshot(x, y); // SAI
}
```

Nếu writer vào **sau** validate và trước khi reader tải cả x/y, bản copy có thể rách. Validation chỉ xét giai đoạn **đã qua**.

Phản ví dụ thứ hai:

```java
long stamp = lock.tryOptimisticRead();
double a = x, b = y;
if (lock.validate(stamp)) {
    return Math.hypot(x, y); // SAI: đọc shared fields lần nữa.
}
```

Cách đúng là `Math.hypot(a,b)`. Sau validate, dùng local values hoặc immutable snapshot; **không đọc lại shared fields** như thể validate đã tạo một read lock cho tương lai.

Nếu phép tính nặng, nên thực hiện **sau validation** để không phải tính xong rồi bỏ vì writer chen vào. Tránh I/O, logging và callbacks có side effects trong vùng optimistic chưa được kiểm tra.

## 8. Ví dụ hoàn chỉnh: Point đọc tọa độ lạc quan

Tạo `PointSnapshotDemo.java`:

```java
import java.util.concurrent.locks.StampedLock;

public class PointSnapshotDemo {
    record Snapshot(double x, double y, boolean optimistic) {}

    static final class Point {
        private final StampedLock lock = new StampedLock();
        private double x;
        private double y;

        Point(double x, double y) {
            this.x = x;
            this.y = y;
        }

        void set(double a, double b) {
            long stamp = lock.writeLock();
            try {
                x = a;
                y = b;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        Snapshot snapshot() {
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
                return new Snapshot(
                        localX, localY, false);
            }

            return new Snapshot(
                    localX, localY, true);
        }

        double distance() {
            Snapshot s = snapshot();
            return Math.hypot(s.x(), s.y());
        }
    }

    public static void main(String[] args) {
        Point p = new Point(3.0, 4.0);
        Snapshot s = p.snapshot();

        System.out.println(
                "initial = " + s.x() + "," + s.y());
        System.out.println(
                "initial optimistic = " + s.optimistic());
        System.out.println("distance = " + p.distance());

        p.set(6.0, 8.0);
        Snapshot after = p.snapshot();

        System.out.println(
                "after move = " +
                        after.x() + "," + after.y());
        System.out.println(
                "after distance = " + p.distance());
    }
}
```

```bash
javac -encoding UTF-8 PointSnapshotDemo.java
java PointSnapshotDemo
```

```text
initial = 3.0,4.0
initial optimistic = true
distance = 5.0
after move = 6.0,8.0
after distance = 10.0
```

Ví dụ này không có writers đồng thời, nên optimistic thành công. Trong thực tế, cần chấp nhận trường hợp fallback. `distance` chỉ tính toán từ `Snapshot` đã được xác thực.

**Phiên bản:** `record` là tính năng Java 16+, ví dụ được viết cho Java 17+. Nếu dùng Java 8, thay record bằng class immutable với final fields và getter; `StampedLock` và protocol copy/validate vẫn có sẵn.

## 9. Một writer chen giữa hai field reads

Để quan sát sự khác biệt, cố định trình tự:

1. Reader lấy stamp và đọc x=1.
2. Writer chạy trong writeLock, đổi cả x và y thành 9.
3. Reader chờ writer hoàn tất rồi đọc y=9.
4. Bản copy lạc quan trở thành (1,9).
5. `validate(stamp)` trả false.
6. Reader lấy readLock và copy lại (9,9).

Chương trình sẽ dùng `Future.get(timeout)` để bảo đảm writer đã hoàn tất trước khi reader đọc y. Không dùng `Thread.sleep(100)` để đoán scheduling. Đây là **kiểm thử interleaving cố định**, bổ sung cho stress test ngẫu nhiên.

## 10. Ví dụ hoàn chỉnh: invalidation rồi fallback

Tạo `WriterInterferenceDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.locks.StampedLock;

public class WriterInterferenceDemo {
    static final class Pair {
        final StampedLock lock = new StampedLock();
        int x = 1;
        int y = 1;

        void write(int value) {
            long stamp = lock.writeLock();
            try {
                x = value;
                y = value;
            } finally {
                lock.unlockWrite(stamp);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Pair p = new Pair();
        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            long stamp = p.lock.tryOptimisticRead();
            int localX = p.x;

            Future<?> write =
                    pool.submit(() -> p.write(9));
            write.get(2, TimeUnit.SECONDS);

            int localY = p.y;
            boolean valid = p.lock.validate(stamp);

            System.out.println(
                    "unvalidated pair = " +
                            localX + "," + localY);
            System.out.println(
                    "optimistic valid = " + valid);

            if (!valid) {
                long r = p.lock.readLock();
                try {
                    localX = p.x;
                    localY = p.y;
                } finally {
                    p.lock.unlockRead(r);
                }
            }

            System.out.println(
                    "validated pair = " +
                            localX + "," + localY);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 WriterInterferenceDemo.java
java WriterInterferenceDemo
```

```text
unvalidated pair = 1,9
optimistic valid = false
validated pair = 9,9
```

`unvalidated pair` chỉ xuất hiện trong **đoạn minh họa lỗi**, không phải giá trị được phép công bố trong ứng dụng thực. Một operation như ghi log, gọi service hoặc tính toán có side effects **không được dùng bản copy chưa validate**. Nếu validation thất bại, bản copy phải bị loại toàn bộ.

Cần chú ý writer **đã nhả** writeLock trước khi validate, nhưng stamp vẫn invalid. Hợp đồng `validate` xét mọi write lock được lấy kể từ khi cấp stamp.

## 11. Stamp bằng zero: một trường hợp bình thường

Nếu writer đang giữ write lock, `tryOptimisticRead()` trả 0 và `validate(0L)` false. Đừng làm:

```java
long stamp;
while ((stamp = lock.tryOptimisticRead()) == 0L) {
    // PHẢN VÍ DỤ: busy-spin, không bảo đảm tiến triển.
}
```

Đây là snippet trong method có `StampedLock lock`. Nếu cần snapshot, fallback `readLock()` thường tốt hơn. Nếu không được blocking, chọn design có deadline/tryReadLock hoặc immutable snapshot riêng.

Tuyệt đối không gọi `unlockRead(0L)` hay `unlockRead(optimisticStamp)`. Không có read lock nào được giữ bởi `tryOptimisticRead`.

## 12. Ví dụ hoàn chỉnh: zero stamp và readLock

Tạo `ZeroStampDemo.java`:

```java
import java.util.concurrent.locks.StampedLock;

public class ZeroStampDemo {
    public static void main(String[] args) {
        StampedLock lock = new StampedLock();

        long writeStamp = lock.writeLock();
        long optimistic;

        try {
            optimistic = lock.tryOptimisticRead();

            System.out.println(
                    "stamp zero while writer holds = " +
                            (optimistic == 0L));
            System.out.println(
                    "validate zero = " +
                            lock.validate(optimistic));
        } finally {
            lock.unlockWrite(writeStamp);
        }

        long r = lock.readLock();
        try {
            System.out.println(
                    "fallback read acquired = " + (r != 0L));
        } finally {
            lock.unlockRead(r);
        }

        long optimisticAfter = lock.tryOptimisticRead();

        System.out.println(
                "stamp nonzero afterwards = " +
                        (optimisticAfter != 0L));
        System.out.println(
                "validate afterwards = " +
                        lock.validate(optimisticAfter));
    }
}
```

```bash
javac -encoding UTF-8 ZeroStampDemo.java
java ZeroStampDemo
```

```text
stamp zero while writer holds = true
validate zero = false
fallback read acquired = true
stamp nonzero afterwards = true
validate afterwards = true
```

Chương trình giữ writeLock rồi chỉ **thử optimistic** trong cùng thread (không block). Sau đó nhả writeLock trước khi lấy readLock; nếu cố lấy readLock khi vẫn giữ writeLock của chính thread đó có thể tự deadlock vì StampedLock **không reentrant**.

## 13. Vì sao object/array mutable nguy hiểm hơn primitive?

JavaDoc `StampedLock` cảnh báo optimistic read chưa validate có thể quan sát dữ liệu rất bất nhất (*wildly inconsistent*). Nếu đọc một object reference rồi dereference vào field/method hoặc array element, lỗi có thể xảy ra **trước validate**:

```java
long stamp = lock.tryOptimisticRead();
Node local = head;
int nextValue = local.next.value; // NGUY HIỂM!
if (lock.validate(stamp)) {
    return nextValue;
}
```

Đây là phản ví dụ với `Node` và `head` thuộc class. Writer có thể thay `head`/`next` trong khi reader đang duyệt, gây `NullPointerException` hoặc một trạng thái cấu trúc tạm không hợp lệ. Nếu exception xảy ra trước validate, validate false không thể “thu hồi” exception.

Tương tự, gọi `list.size()` rồi `list.get(index)` trên ArrayList mutable trong optimistic region có thể không an toàn khi writer thay đổi list. Đừng mặc định “sau đó validate sẽ sửa được”.

Giải pháp:
- **Optimistic copy chỉ một reference tới immutable snapshot**, validate, rồi mới truy cập nội dung.
- **Read lock thật** trong khi clone/duyệt mutable array, list, map hay object graph.
- Chỉ dùng phương pháp optimistic cho cấu trúc phức tạp khi đã chứng minh từng thao tác có thể chịu được trạng thái chưa nhất quán.

## 14. Immutable snapshot: copy reference rồi validate

Một pattern hữu ích là writer tạo object **bất biến sau publication** và thay reference bên trong writeLock:

```java
record Config(String name, int lower, int upper) {}

Config snapshot() {
    long stamp = lock.tryOptimisticRead();
    Config local = current;

    if (!lock.validate(stamp)) {
        stamp = lock.readLock();
        try {
            local = current;
        } finally {
            lock.unlockRead(stamp);
        }
    }
    return local;
}
```

Đây là snippet thuộc class có `Config current` và `StampedLock lock`. Trong khoảng optimistic, chỉ **copy reference**, không gọi method trên object. Sau validation thành công, dùng fields của Config bất biến là an toàn đối với cập nhật tương lai vì object cũ không bị mutate nữa.

**Điều kiện quan trọng:** nếu Config có member mutable array/list và để nó thoát ra ngoài, record chỉ immutable nông. Bạn cần defensive copy hoặc loại thực sự immutable.

Nếu toàn bộ state được thay bằng **một immutable reference duy nhất** và không cần khóa nhiều thao tác khác, `volatile Config current` hoặc `AtomicReference<Config>` có thể là giải pháp đơn giản hơn StampedLock.

## 15. Ví dụ hoàn chỉnh: published immutable Config

Tạo `ImmutableConfigDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.locks.StampedLock;

public class ImmutableConfigDemo {
    record Config(String name, int lower, int upper) {}

    static final class Store {
        private final StampedLock lock =
                new StampedLock();
        private Config current =
                new Config("v1", 1, 3);

        Config snapshot() {
            long stamp = lock.tryOptimisticRead();
            Config local = current;

            if (!lock.validate(stamp)) {
                stamp = lock.readLock();
                try {
                    local = current;
                } finally {
                    lock.unlockRead(stamp);
                }
            }
            return local;
        }

        void publish(Config next) {
            Objects.requireNonNull(next);
            long stamp = lock.writeLock();
            try {
                current = next;
            } finally {
                lock.unlockWrite(stamp);
            }
        }
    }

    public static void main(String[] args) {
        Store s = new Store();
        Config old = s.snapshot();
        s.publish(new Config("v2", 2, 6));
        Config current = s.snapshot();

        System.out.println(
                "old = " + old.name() + ":" +
                        old.lower() + ".." + old.upper());
        System.out.println(
                "current = " + current.name() + ":" +
                        current.lower() + ".." + current.upper());
        System.out.println(
                "old unchanged = " +
                        old.name().equals("v1"));
        System.out.println(
                "new object = " + (old != current));
    }
}
```

```bash
javac -encoding UTF-8 ImmutableConfigDemo.java
java ImmutableConfigDemo
```

```text
old = v1:1..3
current = v2:2..6
old unchanged = true
new object = true
```

`old` và `current` cùng tồn tại: writer thay reference chứ không sửa object cũ. Java 17 record chỉ là cách biểu diễn ngắn; trên Java 8 dùng final class và final fields với cùng discipline. Không gọi getter của object mutable trong optimistic section trước validate.

## 16. Sao chép mảng: phải copy **nội dung**, không chỉ reference

Sai:

```java
long stamp = lock.tryOptimisticRead();
int[] copy = values;
if (lock.validate(stamp)) {
    return copy; // Lộ array nội bộ!
}
```

`int[] copy = values` chỉ copy reference, không copy elements. Nếu caller sửa array đã trả, người này đã thay đổi state **không qua writeLock**, khiến mọi giả định của StampedLock sai. Ngay cả khi validate true, writer có thể sửa array sau validate.

Với một mutable array, cách dễ kiểm chứng nhất là copy **dưới read lock**:

```java
int[] safeCopy() {
    long stamp = lock.readLock();
    try {
        return values.clone();
    } finally {
        lock.unlockRead(stamp);
    }
}
```

Đây là method minh họa có fields `lock`/`values`. Cũng nên defensive copy khi **nhận** array từ caller, nếu không caller vẫn giữ tham chiếu và có thể mutate object nội bộ từ bên ngoài.

Mảng của primitive có clone giá trị từng phần tử. Với array chứa object mutable, clone chỉ **shallow copy**, vẫn cần immutable elements/deep-copy hoặc một protocol khác.

## 17. Ví dụ hoàn chỉnh: defensive copy hai chiều

Tạo `DefensiveArrayDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.locks.StampedLock;

public class DefensiveArrayDemo {
    static final class Store {
        private final StampedLock lock = new StampedLock();
        private int[] nums = {1, 2, 3};

        int[] copy() {
            long stamp = lock.readLock();
            try {
                return nums.clone();
            } finally {
                lock.unlockRead(stamp);
            }
        }

        void replace(int[] values) {
            int[] safe = values.clone();
            long stamp = lock.writeLock();
            try {
                nums = safe;
            } finally {
                lock.unlockWrite(stamp);
            }
        }
    }

    public static void main(String[] args) {
        Store s = new Store();
        int[] snap = s.copy();
        snap[0] = 99;

        System.out.println(
                "caller copy = " + Arrays.toString(snap));
        System.out.println(
                "internal after edit = " +
                        Arrays.toString(s.copy()));

        int[] src = {5, 6};
        s.replace(src);
        src[0] = 77;

        System.out.println(
                "internal after source edit = " +
                        Arrays.toString(s.copy()));
    }
}
```

```bash
javac -encoding UTF-8 DefensiveArrayDemo.java
java DefensiveArrayDemo
```

```text
caller copy = [99, 2, 3]
internal after edit = [1, 2, 3]
internal after source edit = [5, 6]
```

Việc chọn `readLock` cho clone là có chủ đích. **Không ép optimistic read cho mọi cấu trúc**: nếu dereference mutable array hoặc duyệt collection trước validate có thể không chịu được state trung gian, readLock rõ ràng và an toàn hơn.

## 18. Validate true không bảo vệ dereference **sau** đó

Phản ví dụ:

```java
long stamp = lock.tryOptimisticRead();
List<Item> local = sharedList;

if (lock.validate(stamp)) {
    return local.get(0); // Có thể race với writer SAU validate.
}
```

Đây là snippet không độc lập với `Item` và `sharedList` thuộc class. Validate true chỉ kiểm tra rằng giai đoạn **trước validate** không có writer lấy writeLock. Writer vẫn có thể mutate list **ngay sau validate**; việc gọi `list.get(0)` không còn được bảo vệ.

Vì vậy chỉ có:
- Primitive copies từ trước validate.
- Reference tới object **thật sự immutable** đã publish đúng protocol.
- Dữ liệu được bảo vệ bằng read lock đang giữ hoặc một cơ chế thread-safety riêng.

mới thích hợp dùng trong kết quả snapshot. Không lẫn “đã kiểm tra reference” với “mọi thao tác trên object mutable từ nay đều an toàn”.

## 19. Writer phải cập nhật trọn invariant trong **một** write lock

Mẫu đúng:

```java
void updatePair(int nextX, int nextY) {
    long stamp = lock.writeLock();
    try {
        x = nextX;
        y = nextY;
    } finally {
        lock.unlockWrite(stamp);
    }
}
```

Đây là method minh họa. Nếu writer lấy writeLock để sửa x, **nhả**, rồi lấy writeLock lần hai để sửa y, một reader có thể lấy optimistic stamp **ở giữa hai lần khóa**. Tại thời điểm đó, state có thể chỉ được sửa một nửa nhưng `validate` lại true nếu không có writeLock mới chen vào trong lượt quan sát reader.

Vì thế StampedLock bảo vệ **các critical sections được thiết kế**, không tự biết invariant nghiệp vụ nào cần atomic. Phải gộp toàn bộ cập nhật logic vào một write-lock section.

Tương tự, không để một code path mutate x/y trực tiếp ngoài khóa; validation không bảo vệ nổi writer ngoài protocol.

## 20. Test concurrency nên kiểm tra invariant, không chỉ thông lượng

Một test hữu ích cần:
- Writer cập nhật hai field dưới cùng writeLock.
- Hai hoặc nhiều readers thử optimistic snapshot và fallback.
- Mỗi snapshot đã trả phải thỏa invariant, ví dụ `a == b`.
- Các tasks được chờ bằng `Future.get` để không bỏ sót exception worker.
- Không assert số lượt validate success/fallback cố định vì scheduling có thể đổi.

Stress test làm tăng khả năng phát hiện bug, nhưng **không phải chứng minh hình thức** về mọi interleaving. Test `WriterInterferenceDemo` còn cần thiết vì nó đảm bảo writer can thiệp đúng khoảng mục tiêu, không phụ thuộc may rủi.

## 21. Ví dụ hoàn chỉnh: writer và hai readers

Tạo `ConcurrentInvariantDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.StampedLock;

public class ConcurrentInvariantDemo {
    static final class Pair {
        private final StampedLock lock = new StampedLock();
        private int a;
        private int b;

        void update(int n) {
            long stamp = lock.writeLock();
            try {
                a = n;
                b = n;
            } finally {
                lock.unlockWrite(stamp);
            }
        }

        int[] snapshot() {
            long stamp = lock.tryOptimisticRead();
            int a0 = a;
            int b0 = b;

            if (!lock.validate(stamp)) {
                stamp = lock.readLock();
                try {
                    a0 = a;
                    b0 = b;
                } finally {
                    lock.unlockRead(stamp);
                }
            }
            return new int[] {a0, b0};
        }
    }

    public static void main(String[] args) throws Exception {
        Pair p = new Pair();
        ExecutorService pool =
                Executors.newFixedThreadPool(3);
        CountDownLatch go = new CountDownLatch(1);
        AtomicInteger invalid = new AtomicInteger();

        try {
            Future<?> writer = pool.submit(() -> {
                try {
                    go.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException(ex);
                }

                for (int i = 1; i <= 10_000; i++) {
                    p.update(i);
                }
            });

            List<Future<?>> readers = new ArrayList<>();

            for (int j = 0; j < 2; j++) {
                readers.add(pool.submit(() -> {
                    try {
                        go.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(ex);
                    }

                    for (int i = 0; i < 15_000; i++) {
                        int[] v = p.snapshot();

                        if (v[0] != v[1]) {
                            invalid.incrementAndGet();
                        }
                    }
                }));
            }

            go.countDown();
            writer.get(5, TimeUnit.SECONDS);

            for (Future<?> reader : readers) {
                reader.get(5, TimeUnit.SECONDS);
            }

            System.out.println(
                    "invariant violations = " +
                            invalid.get());

            int[] last = p.snapshot();
            System.out.println(
                    "final values = " +
                            last[0] + "," + last[1]);
        } finally {
            go.countDown();
            pool.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 ConcurrentInvariantDemo.java
java ConcurrentInvariantDemo
```

```text
invariant violations = 0
final values = 10000,10000
```

Writer cập nhật từ 1 tới 10000. Hai readers chạy 15000 snapshot mỗi người. Số lần fallback không cố định, nhưng cả hai đường đều trả dữ liệu nhất quán theo lock contract. Output cuối ổn định sau khi đã đợi mọi futures.

Kết quả trả là `new int[]{a0,b0}` — array mới từ locals, không expose shared mutable array. Nếu muốn tối ưu allocation, có thể dùng immutable result record thay vì array, nhưng không thay đổi protocol.

## 22. Quản lý read/write stamps đúng cách

`readLock()` và `writeLock()` trả stamps khác chế độ. Phải trả khóa trong `finally`:

```java
long readStamp = lock.readLock();
try {
    // Read fields under lock.
} finally {
    lock.unlockRead(readStamp);
}
```

```java
long writeStamp = lock.writeLock();
try {
    // Mutate all related fields.
} finally {
    lock.unlockWrite(writeStamp);
}
```

Đây là snippets trong phương thức. **Optimistic stamp không cần unlock**; `validate` không làm nhiệm vụ unlock vì không có read lock nào được giữ. Không được đưa optimistic stamp vào `unlockRead`.

Dù StampedLock không có ownership theo thread giống một số lock khác, ứng dụng vẫn cần đúng quy tắc sử dụng stamp và lifecycle. Không dùng lại stamp đã unlock, không tự chế stamp hoặc chuyển stamp giữa các lock.

## 23. Non-reentrant: tránh tự deadlock

**StampedLock is non-reentrant**, tức **không tái nhập**. Một method đang giữ write lock mà gọi method khác cũng lấy writeLock của cùng đối tượng có thể tự chờ mãi. Một thread giữ readLock rồi gọi writeLock trực tiếp cũng có nguy cơ tự deadlock.

Có `tryConvertToWriteLock(stamp)` để **thử** chuyển từ read/optimistic sang write mode theo điều kiện hiện hành. Nếu không thể đổi, phương thức trả zero. Khi đã nắm readLock mà cần ghi, một pattern là thử convert; nếu thất bại, thả read lock, lấy writeLock và **kiểm tra lại điều kiện nghiệp vụ** vì state có thể thay đổi trong khoảng hai lần khóa.

Không chạy callback, logging tùy ý hoặc method không rõ có tự lấy khóa trong một vùng đang giữ khóa. Với chức năng snapshot đơn giản, **không cần lock conversion**; chỉ dùng optimistic validate/fallback.

## 24. Ví dụ hoàn chỉnh: unlock trong finally và convert

Tạo `StampReleaseDemo.java`:

```java
import java.util.concurrent.locks.StampedLock;

public class StampReleaseDemo {
    static final class Counter {
        final StampedLock lock = new StampedLock();
        int count = 2;

        int readEvenOnError() {
            long stamp = lock.readLock();
            try {
                throw new IllegalArgumentException("bad");
            } finally {
                lock.unlockRead(stamp);
            }
        }

        void setAtLeast(int min) {
            long stamp = lock.readLock();
            try {
                while (count < min) {
                    long next =
                            lock.tryConvertToWriteLock(stamp);

                    if (next != 0L) {
                        stamp = next;
                        count = min;
                        break;
                    }

                    lock.unlockRead(stamp);
                    stamp = lock.writeLock();
                }
            } finally {
                lock.unlock(stamp);
            }
        }
    }

    public static void main(String[] args) {
        Counter c = new Counter();

        try {
            c.readEvenOnError();
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "exception = " +
                            ex.getClass().getSimpleName());
        }

        System.out.println(
                "read lock released = " +
                        !c.lock.isReadLocked());

        c.setAtLeast(5);
        c.setAtLeast(3);

        System.out.println("counter = " + c.count);
        System.out.println(
                "write lock released = " +
                        !c.lock.isWriteLocked());
    }
}
```

```bash
javac -encoding UTF-8 StampReleaseDemo.java
java StampReleaseDemo
```

```text
exception = IllegalArgumentException
read lock released = true
counter = 5
write lock released = true
```

Khi `tryConvertToWriteLock` thành công, stamp mới phải được giữ trong biến `stamp` để unlock đúng chế độ. Nếu thất bại, code thả read lock trước khi lấy write lock và kiểm tra lại điều kiện của vòng while.

Khi một critical section ném exception, finally vẫn chạy để trả khóa. Trong production cần phân tích thêm interruption/deadline/ownership; ví dụ này chỉ minh họa API stamp.

## 25. Volatile, snapshot consistency và writer discipline

`volatile int x` và `volatile int y` bảo đảm một số điều kiện về visibility **riêng từng field**, nhưng không tạo một **atomic pair snapshot**. Writer vẫn có thể cập nhật x rồi y, reader đọc hai thời điểm khác nhau.

Ngược lại, nếu mọi writer dùng writeLock và reader dùng optimistic validate hoặc readLock như mô tả, **không bắt buộc đánh dấu mọi primitive field volatile** chỉ để pattern có memory visibility phù hợp. Chính contract đồng bộ của StampedLock cung cấp điều đó khi dùng đúng.

Không được bỏ qua writeLock ở một code path rồi hy vọng `validate` vẫn phát hiện. Điều kiện của validate nói về **write lock acquisition**, không về mọi thay đổi bộ nhớ có thể xảy ra ngoài protocol.

Nếu trạng thái chỉ là một immutable reference đơn, cân nhắc `AtomicReference`/`volatile` thay thế để giảm độ phức tạp, nhưng vẫn phải đảm bảo đối tượng bên trong **thực sự immutable**.

## 26. Blocking fallback và hiệu năng

`tryOptimisticRead` không chặn, nhưng **`readLock()` fallback có thể chờ** khi writer giữ write lock. Nếu code chạy trên một event loop hoặc thread không được phép block:
- Có thể thiết kế API thử nhanh, trả trạng thái “busy”.
- Dùng `tryReadLock(timeout, TimeUnit)` với timeout hợp lệ.
- Dùng `readLockInterruptibly()` nếu cần chờ có thể phản ứng với interruption.
- Ưu tiên immutable snapshot reference nếu mô hình phù hợp.
- Không retry/spin vô hạn khi writer liên tục hoạt động.

`StampedLock` không bảo đảm fairness cụ thể; tác vụ có thể chờ tùy lịch. Cần xác định performance goal rồi benchmark thay vì mặc định optimistic luôn tốt hơn.

So sánh thực tế với `synchronized`, `ReentrantReadWriteLock`, `AtomicReference` hoặc một concurrent collection. Đo latency, throughput, tỷ lệ fallback, CPU và read/write contention theo workload đại diện. Với microbenchmark JVM nên dùng JMH để tránh JIT warmup, dead-code elimination và scheduling gây sai kết luận.

## 27. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Copy x/y rồi trả ngay không validate | Dữ liệu có thể rách | Copy → validate |
| Validate trước khi copy | Writer có thể xuất hiện sau validate | Validate **sau** copy cuối |
| Validate true rồi đọc lại x/y shared | Không được khóa future reads | Chỉ dùng locals |
| Validate false mà giữ một field cũ | Snapshot pha trộn | Copy lại **toàn bộ** trong readLock |
| Stamp zero vẫn dùng optimistic data | Không có stamp hợp lệ | Fallback |
| Gọi unlockRead trên optimistic stamp | Chưa nắm read lock | Không unlock optimistic |
| Dùng stamp từ StampedLock khác | Không có contract | Stamp phải cùng lock |
| Dereference mutable Node trước validate | Có thể NPE/trạng thái bất nhất | ReadLock hoặc immutable object |
| Sao chép reference array rồi cho là copy dữ liệu | Array vẫn mutable | Clone dưới readLock |
| Trả mutable list/array nội bộ cho caller | Caller bypass lock | Defensive copy |
| Tin record chứa int[] tự immutable hoàn toàn | Mutable member không được bảo vệ | Copy member / immutable |
| Validate true rồi truy cập mutable object | Writer có thể sửa ngay sau đó | Immutable ref hoặc giữ read lock |
| Một writer sửa field ngoài khóa | Validate không phát hiện | Dùng cùng writeLock |
| Writer cập nhật invariant trong hai critical sections | Reader có thể validate trạng thái nửa cập nhật | Cập nhật nhóm dưới một writeLock |
| Cho rằng volatile x/y là atomic snapshot | Từng field độc lập | Lock/immutable aggregate |
| Quên unlock trong finally | Exception khiến khóa bị giữ | try/finally |
| Reentrant call vào StampedLock | Có thể tự deadlock | Không tái nhập, convert hợp lý |
| Busy-spin cho đến khi stamp khác zero | Tốn CPU, có thể kẹt | Fallback hoặc bounded policy |
| Dùng StampedLock cho mọi object | Complexity cao, lợi ích chưa chắc | So benchmark |
| Test chỉ một thread | Không phát hiện writer interference | Test controlled interleaving |
| Đòi số lần fallback cố định trong stress test | Lịch thread thay đổi | Assert invariant |
| Dùng log/I/O trước validate | Side effect không hoàn tác được | Chỉ dùng data sau validation |

## 28. Checklist code review

1. Những field nào thuộc **một** snapshot logic?
2. Có mọi writer nào bỏ qua writeLock không?
3. Writer có cập nhật toàn bộ invariant **trong một write lock** không?
4. Stamp được lấy trước khi copy?
5. Tất cả fields cần thiết có được copy **trước validate**?
6. Có kiểm tra stamp 0 và validation false?
7. Có đọc lại **đầy đủ** fields trong readLock fallback?
8. Có `try/finally` để thả read lock?
9. Sau validate có đọc shared fields lần nữa không?
10. Có dereference mutable object/array **trước** validate không?
11. Có trả mutable object/array nội bộ cho caller không?
12. Nếu dùng immutable reference, object có thực sự deep immutable hoặc được phòng vệ không?
13. Có nguy cơ method tái nhập cùng StampedLock?
14. Có dùng đúng stamp, đúng unlock mode?
15. Nếu fallback có thể block, có chính sách deadline/interruption phù hợp?
16. Có test writer can thiệp giữa các reads một cách deterministic?
17. Có stress test invariant nhiều readers/writers?
18. Có benchmark lợi ích so với cách đơn giản hơn?

Nếu câu trả lời ở phần structure/object graph không rõ, **chọn readLock hoặc immutable publication** thay vì cố tối ưu bằng optimistic traversal.

## 29. Câu hỏi tự kiểm tra

**1. `tryOptimisticRead` có giữ read lock không?** Không. Nó chỉ cấp stamp quan sát.

**2. Stamp 0 nghĩa là gì?** Writer đang giữ write lock khi thử, không có optimistic stamp hợp lệ.

**3. Stamp khác zero có đủ để dùng x/y ngay không?** Không. Phải validate **sau** khi copy đầy đủ.

**4. Writer lấy rồi nhả writeLock giữa stamp và validate có làm validate false không?** Có, dù không còn đang giữ khóa khi reader gọi validate.

**5. Validate true rồi đọc y trực tiếp có an toàn không?** Không. Writer có thể chen vào sau validate; chỉ dùng local copies đã tải trước.

**6. Validation thất bại cần làm gì?** Bỏ toàn bộ optimistic data và copy lại dưới readLock.

**7. Optimistic stamp cần unlock không?** Không, nó không phải read stamp.

**8. Vì sao dereference Node mutable trước validate nguy hiểm?** Có thể ném lỗi hoặc gặp cấu trúc trung gian trước khi kịp loại bỏ bản copy.

**9. Copy reference tới `int[]` có phải snapshot phần tử không?** Không; cần defensive copy trong vùng bảo vệ thích hợp.

**10. Record chứa array có chắc immutable không?** Không; record immutable nông, array vẫn có thể bị mutate.

**11. Khi nào copy Config reference đủ?** Khi Config thật sự bất biến, được publish đúng protocol và chỉ dereference sau validate.

**12. Writer update x và y dưới hai lần writeLock khác nhau có an toàn cho invariant không?** Không. Reader có thể thấy một trạng thái nửa cập nhật hợp lệ theo khóa.

**13. `volatile x,y` có tạo snapshot nguyên tử của cặp?** Không, mỗi field riêng rẽ.

**14. Có thể lấy writeLock trong khi giữ readLock không?** Không nên; StampedLock không reentrant, cần convert hoặc thả/recheck.

**15. Vì sao `readLock` vẫn cần khi đã có optimistic read?** Đây là fallback khi validation false và là cách an toàn để duyệt/copy cấu trúc mutable.

**16. Có nên busy-spin đến khi optimistic stamp khác 0?** Không; có thể tốn CPU, không bảo đảm tiến triển.

**17. Output test nào cho thấy cặp bị rách?** `unvalidated pair = 1,9`, validate false, fallback nhận `validated pair = 9,9`.

**18. Test stress có cần assert số lần optimistic success không?** Không, nó phụ thuộc scheduler; assert invariant và kết quả cuối.

**19. Có cần StampedLock nếu mọi state là một immutable reference?** Có thể không; AtomicReference/volatile reference đơn giản hơn.

**20. StampedLock có từ phiên bản nào?** Java 8; các method cốt lõi vẫn hiện hành.

## 30. Tổng kết

- `tryOptimisticRead()` **không giữ read lock**; nó trả optimistic stamp có thể được kiểm tra.
- **Copy vào locals → validate → dùng chính locals**. Không đọc lại shared fields sau validation.
- Nếu `stamp == 0` hoặc `validate(stamp)` false, **đọc lại tất cả dữ liệu dưới readLock** và thả khóa ở finally.
- Object graph, array và collection mutable cần thận trọng: **không dereference trạng thái không nhất quán trước validate**; dùng readLock hoặc immutable snapshot phù hợp.
- Sao chép reference không phải sao chép nội dung array. Không expose mutable internal state.
- Tất cả writers phải dùng cùng writeLock và cập nhật trọn invariant trong một critical section.
- StampedLock **non-reentrant**; optimistic stamp không unlock, read/write stamps phải được thả đúng chế độ.
- Validation thành công không bảo vệ những **lần đọc tương lai**; nó xác thực bản sao đã đọc.
- Không tối ưu trước khi benchmark. Với nhiều state immutable, có thể chọn AtomicReference đơn giản hơn.
- Đây là kiến thức API từ **Java 8** nhưng còn áp dụng hiện nay.

### Tài liệu chính thức

- [Oracle Java SE 26 — StampedLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/StampedLock.html): optimistic read, validate, memory synchronization, read/write locks và conversion.
- [Oracle Java SE 8 — StampedLock](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/locks/StampedLock.html): xác nhận API có từ Java 8.
- [Oracle Java SE 26 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): khóa đọc/ghi thường.
- [Oracle Java SE 26 — AtomicReference](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): immutable snapshot publication.
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html) và [Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): đồng bộ hóa và kiểm thử đa luồng.
