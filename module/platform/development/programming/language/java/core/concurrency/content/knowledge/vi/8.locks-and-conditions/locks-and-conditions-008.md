# ReadWriteLock cho read-heavy workload trong Java

> **Ý chính:** `ReadWriteLock` có hai chế độ khóa liên kết: **nhiều reader** có thể cùng giữ read lock, còn **writer** cần write lock độc quyền. Nó hữu ích cho một số workload đọc nhiều/ghi ít, nhưng **không có bảo đảm luôn nhanh hơn** `synchronized` hoặc `ReentrantLock`. Độ dài critical section, tỉ lệ đọc/ghi, contention, fairness và đặc tính dữ liệu quyết định.

Bài này thuộc **Locks & Conditions**, chỉ tập trung Java SE concurrency, dùng API Java 17+. Các vấn đề của Spring được dành cho chương riêng, không nằm trong phạm vi bài.

## 1. Vì sao cần read/write lock?

Giả sử một cấu trúc từ điển có hàng nghìn mục, nhiều thread đọc tìm kiếm và hiếm khi sửa. Dùng một monitor `synchronized(lock)` bảo vệ mọi thao tác thì dù chỉ đọc, các thread vẫn phải xếp hàng lần lượt. Với read/write lock, nhiều lần **đọc thuần túy** có thể cùng thực hiện, trong khi một lần ghi tạm chặn các reader/writer khác để cập nhật state nhất quán.

~~~text
Không có writer:
  Reader A -- READ lock --┐
  Reader B -- READ lock --+-- có thể cùng ở critical section
  Reader C -- READ lock --┘

Khi writer cần sửa:
  Writer -- WRITE lock ------- độc quyền khi đã lấy được
  Reader/Writer khác --------- đợi theo chính sách acquire
~~~

Đây là khả năng concurrent access về mặt hợp đồng khóa, **không bảo đảm CPU thực sự chạy các reader song song** hay writer được lấy khóa trước một deadline.

| Ai đang giữ khóa? | Reader mới | Writer mới |
| --- | --- | --- |
| Không ai | Có thể lấy read | Có thể lấy write |
| Một hoặc nhiều reader | Có thể cùng lấy read nếu chính sách chờ cho phép | Phải chờ các reader nhả |
| Một writer | Không được vào, trừ reentrant read của chính writer | Không được vào, trừ reentrant write của chính writer |

Đừng hiểu sai rằng “cứ thấy còn reader thì reader mới luôn được vào”: khi một writer đang chờ, fairness/acquisition policy có thể yêu cầu reader mới đợi để tránh writer bị đói.

## 2. Interface và implementation trong Java

`ReadWriteLock` là interface ở `java.util.concurrent.locks`. Mỗi instance trả về **một cặp liên kết** qua `readLock()` và `writeLock()`. `ReentrantReadWriteLock` là implementation Java SE thông dụng, hỗ trợ reentrancy và tùy chọn fairness.

~~~java
// Snippet minh họa cách khai báo; chưa phải chương trình độc lập.
ReadWriteLock rw = new ReentrantReadWriteLock();
Lock read = rw.readLock();
Lock write = rw.writeLock();
~~~

Hai critical section chuẩn:

~~~java
read.lock();
try {
    // Chỉ đọc dữ liệu chung và tạo snapshot nếu cần.
} finally {
    read.unlock();
}

write.lock();
try {
    // Kiểm tra invariant và cập nhật dữ liệu chung.
} finally {
    write.unlock();
}
~~~

Luôn dùng `try/finally` sau khi acquire thành công. `Lock` không có cấu trúc giải phóng tự động khi ra khỏi một block như `synchronized`. Khi có exception hoặc `return` sớm, `finally` vẫn giải phóng lock. Nếu gọi `unlock()` từ thread không sở hữu lock, hoặc unlock nhiều hơn số hold hợp lệ, sẽ gây lỗi.

**Mọi reader/writer bảo vệ cùng state phải dùng cùng instance `rw`.** Một thread lấy `rwA.readLock()` và thread khác lấy `rwB.writeLock()` thì hai khóa không có quan hệ loại trừ, bất kể tên biến giống nhau.

### Cơ chế happens-before

`ReadWriteLock` yêu cầu hiệu ứng memory synchronization của write lock cũng áp dụng với read lock liên kết. Sau khi một writer cập nhật dữ liệu và nhả write lock, các reader lấy read lock theo sau có cơ sở quan sát những cập nhật đó theo Java Memory Model. Vì vậy một `int` thường có thể được đọc/ghi đúng dưới protocol khóa này; không cần thêm `volatile` cho từng field nếu tất cả truy cập cạnh tranh đều tuân theo protocol.

Một đường ghi không khóa hoặc một reader đọc trực tiếp ngoài read lock đủ phá tính đúng đắn của thiết kế.

## 3. Khi nào read-heavy thực sự có lợi?

Một ứng viên phù hợp thường có: rất nhiều lần đọc; rất ít lần cập nhật; nhiều reader tranh cùng cấu trúc; đọc có thời lượng đáng kể; writer giữ write lock ngắn; thiết kế data và invariant rõ ràng.

Ngược lại, `ReentrantReadWriteLock` quản lý số lượng reader, write ownership và hàng đợi phức tạp hơn exclusive lock. Nếu mỗi lần đọc chỉ lấy một biến hoặc lookup cực ngắn, overhead có thể vượt lợi ích. Với tỉ lệ ghi cao, write lock độc quyền thường xuyên khiến shared reads hiếm khi cùng được thực hiện.

Tài liệu `ReadWriteLock` của JDK lưu ý hiệu quả phụ thuộc tỉ lệ read/write, thời lượng thao tác, contention và số bộ xử lý thực. Vì vậy **read-heavy là điều kiện gợi ý để benchmark, không phải chứng minh tốc độ**.

| Loại workload | Khả năng phù hợp |
| --- | --- |
| Map lớn với tra cứu dài, sửa ít, nhiều reader | Có thể hợp lý |
| Immutable configuration thay mới vài lần mỗi giờ | `volatile` reference tới immutable snapshot thường đơn giản hơn |
| Một biến đếm cập nhật rất thường xuyên | `AtomicLong`/`LongAdder` hoặc công cụ khác phù hợp hơn |
| Mỗi request get/put một key độc lập | `ConcurrentHashMap` có thể hiệu quả hơn khóa toàn map |
| Mỗi thao tác đọc thực ra cập nhật LRU/hit count | Không còn là read-only; cần protocol mutation |
| Critical section luôn rất ngắn và tranh chấp thấp | Exclusive lock có thể dễ hiểu và nhanh hơn |

## 4. Ví dụ 1: từ điển đọc nhiều, ghi ít

`HashMap` tự nó không được dùng để read/write đồng thời khi có mutation. Nhưng ta có thể **đóng gói hoàn toàn** nó và chỉ truy cập dưới read/write lock tương ứng.

Tạo `ReadMostlyDictionary.java` (Java 17+):

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadMostlyDictionary {
    private final Map<String, String> values = new HashMap<>();
    private final ReadWriteLock rw = new ReentrantReadWriteLock();

    public String get(String key) {
        rw.readLock().lock();
        try {
            return values.get(key);
        } finally {
            rw.readLock().unlock();
        }
    }

    public void put(String key, String value) {
        rw.writeLock().lock();
        try {
            values.put(key, value);
        } finally {
            rw.writeLock().unlock();
        }
    }

    public int size() {
        rw.readLock().lock();
        try {
            return values.size();
        } finally {
            rw.readLock().unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ReadMostlyDictionary dictionary = new ReadMostlyDictionary();
        dictionary.put("language", "Java");

        Thread firstReader = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                String value = dictionary.get("language");
                if (!"Java".equals(value) && !"Java 17".equals(value)) {
                    throw new AssertionError(value);
                }
            }
        });
        Thread secondReader = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                dictionary.size();
            }
        });
        Thread writer = new Thread(
                () -> dictionary.put("language", "Java 17"));

        firstReader.start();
        secondReader.start();
        writer.start();
        firstReader.join();
        secondReader.join();
        writer.join();

        System.out.println("size = " + dictionary.size());
        System.out.println("language = " + dictionary.get("language"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ReadMostlyDictionary.java
java ReadMostlyDictionary
~~~

Stdout bình thường:

~~~text
size = 1
language = Java 17
~~~

Trong lúc chạy, reader có thể nhìn thấy `Java` hoặc `Java 17` tùy lịch xen kẽ; **không có thứ tự quan sát cố định**. Nhưng vì đọc/ghi map dùng khóa đúng, reader không thao tác vào cấu trúc map trong lúc writer đang mutate. Sau `join()` writer, giá trị cuối cùng là `Java 17`.

`String` là immutable. Nếu map trả về một `MutableValue` mà thread khác sửa object ấy sau khi `get()` trả về, khóa chỉ bảo vệ **tra cứu map**, không bảo vệ mutation của object được trả về. Nên dùng immutable values, defensive copy, hoặc protocol khóa bảo vệ cả state bên trong.

Đừng phơi trực tiếp `values` qua getter; người gọi có thể sửa map mà không khóa và khiến cả mô hình sai.

## 5. Ví dụ 2: hai reader cùng vào, writer phải chờ

Để chứng minh khả năng nhiều reader cùng giữ read lock, hãy điều phối bằng `CountDownLatch` thay vì `Thread.sleep`.

Tạo `ReadLockCoordination.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadLockCoordination {
    public static void main(String[] args) throws InterruptedException {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        CountDownLatch bothInside = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean writerEntered = new AtomicBoolean(false);

        Runnable reader = () -> {
            rw.readLock().lock();
            try {
                bothInside.countDown();
                release.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                rw.readLock().unlock();
            }
        };

        Thread a = new Thread(reader, "reader-a");
        Thread b = new Thread(reader, "reader-b");
        a.start();
        b.start();

        bothInside.await(); // Cả hai reader đang giữ khóa đọc.
        System.out.println("both readers inside = true");

        Thread writer = new Thread(() -> {
            rw.writeLock().lock();
            try {
                writerEntered.set(true);
            } finally {
                rw.writeLock().unlock();
            }
        }, "writer");
        writer.start();

        System.out.println("writer before release = "
                + writerEntered.get());

        release.countDown();
        a.join();
        b.join();
        writer.join();

        System.out.println("writer after release = "
                + writerEntered.get());
    }
}
~~~

Chạy:

~~~bash
javac ReadLockCoordination.java
java ReadLockCoordination
~~~

Stdout nếu không có interruption từ bên ngoài:

~~~text
both readers inside = true
writer before release = false
writer after release = true
~~~

`bothInside.await()` chỉ hoàn tất khi **cả hai reader** đã lấy read lock và giảm latch; nếu read lock loại trừ reader khác, reader thứ hai không thể vào trong khi reader thứ nhất chờ release. Dòng `writer before release = false` là bảo đảm vì cả hai reader vẫn nắm read lock; writer chưa thể vào write critical section. Sau `release.countDown()` và `join()` cả ba thread, writer đã có cơ hội cập nhật cờ.

Đây là thí nghiệm để học lock semantics; **không giữ read lock qua một wait/blocking operation như vậy trong ứng dụng thật** nếu công việc phát tín hiệu cần write lock của chính nó. Một chu trình chờ có thể gây deadlock.

## 6. Một phương thức tên `get()` có thể là write operation

“Read” trong read lock có nghĩa **không thay đổi shared state được bảo vệ**, không có nghĩa “phương thức có tên getter”.

Các ví dụ read có side effect:

- `LinkedHashMap` được khởi tạo với `accessOrder=true`: một lần `get()` có thể thay đổi thứ tự node nội bộ.
- Bộ nhớ đệm tự khởi tạo khi đọc (`computeIfAbsent` hoặc lazy load).
- LRU eviction, cập nhật `lastAccess`, cache hit/miss metrics lưu trong field thường.
- Getter tạo memoized value hoặc sửa object con.
- Iteration có remove hoặc sửa phần tử mutable.

~~~java
// Snippet minh họa; lru là access-order map.
java.util.Map<String, String> lru =
        new java.util.LinkedHashMap<>(16, 0.75f, true);
String value = lru.get("key"); // Có thể thay đổi access order.
~~~

Nếu map này được nhiều thread chia sẻ, thao tác `get` có tính **mutation** nên không được tùy tiện gọi dưới shared read lock. Có thể phải dùng write lock hoặc một cấu trúc cache chuyên dụng. Khi mỗi “read” đều cập nhật state, giá trị của ReadWriteLock sẽ giảm đáng kể.

## 7. Snapshot nhất quán khi state có nhiều field

Giả sử một ledger có `total` và `version`, invariant là mỗi lần tăng total thì tăng version đúng một lần. Writer phải cập nhật cả hai **trong cùng write lock**, reader phải lấy cả hai **trong cùng read lock**.

Tạo `ReadWriteSnapshot.java` (Java 17+):

~~~java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadWriteSnapshot {
    private record Snapshot(long total, long version) {}

    private static final class Ledger {
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private long total;
        private long version;

        void addOne() {
            rw.writeLock().lock();
            try {
                total++;
                version++;
            } finally {
                rw.writeLock().unlock();
            }
        }

        Snapshot snapshot() {
            rw.readLock().lock();
            try {
                return new Snapshot(total, version);
            } finally {
                rw.readLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();
        Runnable writer = () -> {
            for (int i = 0; i < 1_000; i++) {
                ledger.addOne();
            }
        };
        Thread first = new Thread(writer);
        Thread second = new Thread(writer);
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot snapshot = ledger.snapshot();
        System.out.println("total = " + snapshot.total());
        System.out.println("version = " + snapshot.version());
        System.out.println("consistent = "
                + (snapshot.total() == snapshot.version()));
    }
}
~~~

Chạy:

~~~bash
javac ReadWriteSnapshot.java
java ReadWriteSnapshot
~~~

Stdout:

~~~text
total = 2000
version = 2000
consistent = true
~~~

`snapshot()` tạo record bất biến ngay trong critical section nên caller dùng snapshot bên ngoài khóa vẫn có cùng cặp field. Không nên đọc hai field trong **hai lần** read lock riêng biệt: writer có thể chen vào giữa và làm snapshot pha hai phiên bản.

Nếu snapshot chứa list hay object mutable, cần tạo immutable/defensive copy của phần cần bảo vệ. Chỉ sao chép reference của collection đang được mutate không làm bản sao đó thread-safe.

## 8. Không upgrade trực tiếp từ read lock sang write lock

Với `ReentrantReadWriteLock`, reader đang giữ read lock **không được** lấy thêm write lock để “nâng cấp”. Write lock chỉ được cấp khi không còn reader khác; chính read lock của caller vẫn đang tồn tại, có thể khiến caller tự chờ vô hạn.

~~~java
// MÃ SAI: không chạy thử nếu không có timeout và phương án thoát.
rw.readLock().lock();
try {
    if (missing) {
        rw.writeLock().lock(); // Không hỗ trợ upgrade.
        try {
            initialize();
        } finally {
            rw.writeLock().unlock();
        }
    }
} finally {
    rw.readLock().unlock();
}
~~~

Đúng hơn là:

1. Đọc cache và điều kiện dưới read lock.
2. **Thả read lock** trước khi cố lấy write lock.
3. Acquire write lock.
4. **Kiểm tra lại** điều kiện vì trong khoảng trống giữa hai lock, thread khác có thể đã làm xong.
5. Chỉ thực hiện cập nhật nếu điều kiện vẫn còn đúng.
6. Nhả write lock trong `finally`.

Điểm rất quan trọng: read-unlock → write-lock **không phải upgrade nguyên tử**. Recheck là điều kiện correctness, không phải bước thừa.

### Ví dụ 4: double-check một cache miss

Tạo `ReadWriteCache.java` (Java 17+):

~~~java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadWriteCache {
    private final Map<String, String> values = new HashMap<>();
    private final ReentrantReadWriteLock rw =
            new ReentrantReadWriteLock();

    public String getOrLoad(String key) {
        rw.readLock().lock();
        try {
            String existing = values.get(key);
            if (existing != null) {
                return existing;
            }
        } finally {
            rw.readLock().unlock();
        }

        // Tính toán thuần túy, có thể làm ngoài lock.
        String loaded = key.toUpperCase(Locale.ROOT);

        rw.writeLock().lock();
        try {
            // Có thể đã được thread khác nạp trong lúc ta không giữ lock.
            String existing = values.get(key);
            if (existing != null) {
                return existing;
            }
            values.put(key, loaded);
            return loaded;
        } finally {
            rw.writeLock().unlock();
        }
    }

    public int size() {
        rw.readLock().lock();
        try {
            return values.size();
        } finally {
            rw.readLock().unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ReadWriteCache cache = new ReadWriteCache();
        String[] result = new String[2];

        Thread a = new Thread(() -> result[0] = cache.getOrLoad("java"));
        Thread b = new Thread(() -> result[1] = cache.getOrLoad("java"));
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("same = " + result[0].equals(result[1]));
        System.out.println("value = " + result[0]);
        System.out.println("size = " + cache.size());
    }
}
~~~

Chạy:

~~~bash
javac ReadWriteCache.java
java ReadWriteCache
~~~

Stdout:

~~~text
same = true
value = JAVA
size = 1
~~~

Hai thread có thể cùng thấy miss và **tính `loaded` nhiều lần**; logic tính uppercase thuần túy nên không có vấn đề. Nhưng chỉ một thread cần đặt value vào map vì bước recheck xảy ra dưới write lock. Nếu loader có side effect (gọi mạng, ghi DB, gửi email), không được tự suy ra loader được gọi đúng một lần; cần cơ chế single-flight, futures per key hoặc protocol khác.

Nếu computation ngoài lock phụ thuộc shared state đang thay đổi, phải bảo vệ consistency bằng version/retry hoặc chuyển phần quyết định quan trọng vào write section. Không thể chỉ release-read/acquire-write mà vẫn tin snapshot cũ là mới nhất.

## 9. Downgrade từ write lock xuống read lock được hỗ trợ

`ReentrantReadWriteLock` **cho phép** thread đã giữ write lock acquire thêm read lock (reentrant), sau đó nhả write lock nhưng vẫn giữ read lock. Nhờ đó writer vừa cập nhật có thể tiếp tục quan sát state dưới read lock **mà không có writer khác chen vào trong lúc chuyển chế độ**.

~~~text
acquire WRITE
update state
acquire READ khi WRITE vẫn held
release WRITE
đọc/tiếp tục xử lý dưới READ
release READ
~~~

Tạo `DowngradeExample.java` (Java 17+):

~~~java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class DowngradeExample {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        Lock read = rw.readLock();
        Lock write = rw.writeLock();
        String[] state = {"old"};

        write.lock();
        try {
            state[0] = "new";
            read.lock();  // Writer lấy thêm read lock.
        } finally {
            write.unlock();
        }

        try {
            System.out.println("state = " + state[0]);
        } finally {
            read.unlock();
        }
    }
}
~~~

Chạy:

~~~bash
javac DowngradeExample.java
java DowngradeExample
~~~

Stdout:

~~~text
state = new
~~~

Đoạn này tập trung vào **đường chạy thành công**. Khi thực hiện nhiều lần acquire với code phức tạp có thể ném exception, cần kiểm soát chính xác khóa nào đã acquire trước khi unlock. Việc downgrade không biến mọi thao tác thành atomic hay thay thế bảo vệ cho object mutable được trả ra ngoài khóa.

| Trường hợp | Hỗ trợ |
| --- | --- |
| Read lock reentrant (cùng reader) | Có |
| Write lock reentrant (cùng writer) | Có |
| Writer giữ write rồi lấy read | Có |
| Reader giữ read rồi lấy write | **Không hỗ trợ upgrade** |
| Downgrade write → read không để writer chen ngang | Có, lấy read trước khi nhả write |

## 10. Fairness và nguy cơ writer starvation

Mặc định:

~~~java
ReentrantReadWriteLock regular = new ReentrantReadWriteLock();
ReentrantReadWriteLock fair = new ReentrantReadWriteLock(true);
~~~

Đây là snippet API. `regular` dùng **non-fair mode**; `fair` dùng chính sách **approximately arrival order** khi tranh quyền lấy lock.

- **Non-fair:** thứ tự cấp read/write lock không cố định theo FIFO; thường throughput cao nhưng trong contention liên tục một reader hoặc writer có thể bị trì hoãn rất lâu, thậm chí vô hạn.
- **Fair:** có chính sách gần thứ tự yêu cầu, chọn writer đang đợi lâu hoặc nhóm reader theo thứ tự phù hợp. Có thể giảm nguy cơ starvation nhưng thường phải trả giá về throughput. Fair không đồng nghĩa bảo đảm deadline hoặc fairness tuyệt đối của OS scheduler.
- **Ngoại lệ:** `readLock().tryLock()` và `writeLock().tryLock()` không tuân theo fair setting; nếu lock có thể lấy ngay, `tryLock()` có thể lấy dù còn thread khác đợi.

Khi một writer phải chờ nhiều reader nhả khóa, **writer latency** có thể bị ảnh hưởng dù read throughput tốt. Đọc trong read lock nên tập trung vào việc cần protected state; I/O, callback, render, parse nặng độc lập có thể thực hiện sau khi copy snapshot và thả khóa.

## 11. Condition: write lock có, read lock không

`ReentrantReadWriteLock` hỗ trợ `Condition` ở **write lock**:

~~~java
ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
java.util.concurrent.locks.Condition changed =
        rw.writeLock().newCondition();
~~~

`rw.readLock().newCondition()` ném `UnsupportedOperationException`; không có Condition trên read lock.

Để dùng `Condition.await()/signalAll()` đúng, thread phải nắm write lock liên kết và dùng protocol predicate; `await` thả write lock trong lúc chờ rồi lấy lại trước khi trả về. Mẫu minh họa (không độc lập):

~~~java
rw.writeLock().lock();
try {
    while (!ready) {
        changed.await();
    }
    // Đọc/thay đổi state theo invariant.
} finally {
    rw.writeLock().unlock();
}
~~~

Ở ví dụ thật, một thread khác phải thay `ready` dưới write lock đó và `signalAll()` khi điều kiện đổi. `while` quan trọng vì spurious wakeups và vì predicate có thể đã đổi khi thread thức dậy. Với queue producer-consumer, `BlockingQueue` có thể diễn đạt điều phối đơn giản hơn.

## 12. Interrupt, timeout và tryLock

Các lock implement `Lock` nên hỗ trợ các thao tác acquire khác nhau:

| API | Cách dùng |
| --- | --- |
| `lock()` | Chờ lấy lock; dùng `try/finally` để nhả |
| `lockInterruptibly()` | Có thể bị ngắt trong khi chờ; ném `InterruptedException` |
| `tryLock()` | Thử ngay; trả `true` nếu lấy được, `false` nếu không |
| `tryLock(timeout, unit)` | Chờ tới giới hạn; trả boolean hoặc ném `InterruptedException` |
| `unlock()` | Chỉ gọi khi thread hiện tại thực sự đã lấy lock |

~~~java
// Snippet phương thức có trả boolean, không độc lập.
if (!rw.writeLock().tryLock(100,
        java.util.concurrent.TimeUnit.MILLISECONDS)) {
    return false;
}
try {
    updateState();
    return true;
} finally {
    rw.writeLock().unlock();
}
~~~

Nếu timeout, không được `unlock()` vì chưa có lock. Timeout này chỉ giới hạn **thời gian chờ acquire**, không giới hạn thời gian làm việc bên trong write section. Khi bị `InterruptedException`, có chính sách dừng/propagate phù hợp; đừng nuốt tín hiệu rồi đợi mãi.

## 13. So sánh các lựa chọn cho read-heavy

### A. `synchronized` hoặc `ReentrantLock`

Nếu critical section cực ngắn và contention thấp, exclusive lock có thể vừa đơn giản vừa hiệu quả. Cần đo trước khi thay bằng RW lock. Exclusive lock cũng dễ quản lý hơn khi nhiều bước check-then-act và invariant đòi hỏi cả read/write đồng bộ.

### B. `ConcurrentHashMap`

Thích hợp nếu đa số operation là đọc/ghi từng key độc lập và không cần một snapshot toàn map. `get`, `put`, `compute` và `merge` có contract riêng; **chuỗi `get` rồi `put` không tự atomic**. Nếu cần một transaction nhiều key hoặc snapshot nhất quán của toàn bộ map, một protocol khác có thể cần thiết.

### C. `volatile` reference tới immutable snapshot

Cấu hình nhỏ thay ít nhưng đọc rất thường xuyên có thể được biểu diễn bằng:

~~~java
// Snippet mô tả fields/methods trong một class.
record Settings(String host, int port) {}

private volatile Settings current = new Settings("primary", 8080);

// Writer: xây mới đầy đủ, rồi gán reference.
current = new Settings("backup", 9090);

// Reader: lấy snapshot vào local.
Settings snapshot = current;
~~~

Ở đây không cần giữ read lock mỗi lần đọc; volatile write/read publish các ghi khởi tạo. Nhưng nếu nhiều writer đọc current → tính mới → gán current thì vẫn có thể mất cập nhật. Nếu `Settings` có component trỏ tới object mutable, record không làm nó bất biến sâu.

### D. `AtomicReference<ImmutableState>`

Hữu ích khi nhiều writer muốn thay **toàn state** bằng CAS/`updateAndGet`. Hàm update nên thuần vì có thể chạy lại. Atomicity áp dụng cho reference được thay thế, không làm side effect bên ngoài thành atomic.

### E. `StampedLock`

Có optimistic reads (`tryOptimisticRead`/`validate`), nhưng là loại lock khác, **không reentrant**, có quy tắc validate/visibility phức tạp. Đừng đổi sang `StampedLock` chỉ vì muốn nhanh hơn khi chưa hiểu code và chưa benchmark.

**Kết luận lựa chọn:** RW lock phù hợp khi ta muốn **nhiều reader của cùng cấu trúc lớn** cùng vào protected area, nhưng vẫn muốn writer cập nhật độc quyền và reader lấy snapshot nhất quán.

## 14. Đo hiệu năng đúng cách

Một benchmark hữu ích phải so **cùng logic và cùng semantics** giữa `synchronized`, `ReentrantReadWriteLock`, `ConcurrentHashMap` hoặc immutable snapshot. Không so những thiết kế khác nhau về độ an toàn mà chỉ nhìn throughput.

Nên biến thiên:

1. **Read/write ratio**: ví dụ 99/1, 90/10, 50/50.
2. **Số reader/writer, CPU cores**: có nhiều read thực sự chạy cùng lúc không?
3. **Thời gian giữ read lock**: chỉ đọc 1 primitive hay tạo snapshot từ map lớn?
4. **Thời gian giữ write lock**: cập nhật nhanh hay I/O chậm?
5. **Fairness**: throughput non-fair so với p95/p99 write waiting latency.
6. **GC/allocation**: snapshot copy có tạo áp lực heap?
7. **Load thực tế**: peak, burst writer, số thread, contention, starvation.

Dùng benchmark như JMH có warmup, nhiều lần chạy, kết quả thống kê; không kết luận từ một lần chạy ngắn với `System.nanoTime()` trong main. Với production hãy theo dõi read latency, write latency, queue wait time và lock contention.

Các API instrumentation như `getReadLockCount()`, `getQueueLength()` hoặc `isWriteLocked()` chỉ phục vụ monitoring; một giá trị đo tại thời điểm t **không phải cơ sở đồng bộ** để quyết định truy cập state không lock ở thời điểm t+1.

## 15. Các lỗi triển khai phổ biến

| Lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng read lock cho một getter có mutation | Concurrent writers/readers gây race | Xác định đọc thuần hay ghi thực tế |
| Quên `unlock` trên exception | Lock không được nhả, thread khác treo | `try/finally` |
| Read lock và write lock lấy từ hai `rw` khác nhau | Không có mutual exclusion giữa chúng | Một instance chung cho state |
| Reader giữ read rồi đòi write | Có thể tự kẹt | Nhả read, acquire write, recheck |
| Không recheck sau chuyển read→write | Ghi đè dữ liệu mới, tính từ snapshot cũ | Kiểm tra lại điều kiện dưới write |
| Reader giữ read lock qua HTTP/log chậm | Writer phải chờ lâu | Copy snapshot, xử lý ngoài lock |
| Trả về mutable object rồi sửa ngoài lock | Bỏ qua protection | Immutable value/copy hoặc lock protocol |
| Snapshot nhiều field ở hai lần read khác nhau | Trộn phiên bản | Một read section chung |
| Bật fair rồi nghĩ không còn starvation/deadline issue | Sai hợp đồng scheduling | Benchmark, timeout, monitoring |
| `tryLock` được tưởng là FIFO trong fair mode | Barge trước thread đợi | Đọc hợp đồng `tryLock` |
| Tạo `Condition` từ read lock | Unsupported operation | Condition của write lock |
| Coi mọi cache `get` là read-only | LRU/lazy mutation khiến reader xung đột | Phân loại thao tác theo side effect |
| Tự tạo ReadWriteLock cho một `AtomicInteger` | Overhead không cần thiết | Dùng atomic operation đúng scope |
| Chọn RW lock không benchmark | Có thể chậm hơn simple exclusive lock | Đo trên workload đại diện |

## 16. Câu hỏi kiểm tra kiến thức

**1.** Vì sao 10 reader cùng giữ read lock được mà một writer phải đợi?  
**Đáp án:** Vì các đọc thuần không thay đổi shared state, còn write cần exclusivity để bảo vệ invariant. Chính sách acquire có thể khiến reader mới chờ khi writer đang đợi.

**2.** `HashMap` được bảo vệ bằng RW lock; một getter trả reference đến `ArrayList` nội bộ rồi caller sửa list ngoài lock. An toàn không?  
**Đáp án:** Không. Protection chỉ có hiệu lực khi caller tuân thủ protocol cho state mutable; cần copy hoặc lock cho cả mutation của object con.

**3.** Tại sao không được giữ read lock khi gọi `writeLock().lock()`?  
**Đáp án:** `ReentrantReadWriteLock` không hỗ trợ upgrade. Write cần các read locks biến mất, bao gồm read lock của chính thread đang đợi.

**4.** Sau khi thả read và lấy write lock, có cần kiểm tra lại trạng thái miss của cache?  
**Đáp án:** Có. Thread khác có thể điền cache trong khoảng chuyển lock.

**5.** Hạ write→read khác nâng read→write như thế nào?  
**Đáp án:** Writer có thể lấy read lock trong lúc vẫn nắm write rồi nhả write; reader không thể đòi write khi giữ read.

**6.** `readLock().newCondition()` có hoạt động không?  
**Đáp án:** Không, ném `UnsupportedOperationException`. Condition thuộc write lock.

**7.** Fair mode có bắt `tryLock()` tuân thứ tự hàng đợi không?  
**Đáp án:** Không. `tryLock()` không tuân fairness setting.

**8.** Một ứng dụng 99% đọc nhưng mọi read chỉ lookup một key ngắn. RW lock chắc chắn nhanh nhất không?  
**Đáp án:** Không. Overhead cao, ít contention hoặc `ConcurrentHashMap`/volatile snapshot có thể hợp lý hơn.

**9.** Đọc `total` và `version` ở hai lần read lock riêng có luôn nhất quán không?  
**Đáp án:** Không. Writer có thể chen giữa; chụp hai field trong một read critical section.

**10.** Nên đo chỉ throughput read thôi để quyết định triển khai?  
**Đáp án:** Không. Còn writer latency, starvation, tail latency, memory và correctness.

## Tài liệu tham khảo chính thức

- [`ReadWriteLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html): shared readers, exclusive writer, memory synchronization, tradeoff hiệu năng.
- [`ReentrantReadWriteLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): reentrancy, fairness, lock downgrading, không hỗ trợ upgrading, Condition.
- [`Lock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): acquisition, `tryLock`, interruption, `unlock`.
- [`Condition` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): waiting/signal theo predicate.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent map operations.
- [`StampedLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/StampedLock.html): alternative với optimistic reads.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before và đồng bộ.

**Ghi nhớ:** Nhiều reader có thể cùng giữ read lock; writer cần write lock độc quyền. Chỉ dùng read lock cho **read-only critical section**, luôn nhả khóa trong `finally`, không upgrade trực tiếp, và benchmark để chứng minh lợi ích với workload thật.