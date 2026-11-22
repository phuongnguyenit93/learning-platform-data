# Tránh khóa trên String literal hay public object trong Java

`synchronized` sử dụng **monitor gắn với một object cụ thể**. Nếu object khóa có thể được các thành phần khác truy cập, chúng cũng có thể lấy đúng monitor đó và chặn mã của mình. Hai lỗi thiết kế thường gặp là khóa trên **String literal**, vốn có thể được intern và chia sẻ, hoặc khóa trên **public object**, vốn cho phép caller chủ động giữ monitor nội bộ.

Bài này thuộc mục **Synchronization** trong **Java concurrency nói chung (Java 17+)**. Chỉ đề cập ngôn ngữ Java và thư viện chuẩn, không đi vào cơ chế riêng của Spring.

Mục tiêu: hiểu monitor identity, lý do String literal bị chia sẻ, rủi ro của public lock và `this`/class monitor; tạo khóa `private final Object` đúng phạm vi; nhận diện contention/deadlock, bảo đảm mọi reader/writer dùng cùng lock và tránh sửa một API hiện có mà phá hợp đồng đồng bộ.

## 1. Monitor của synchronized là identity của object

Một khối đồng bộ trong Java có dạng:

~~~java
// Mã minh họa: lock đã được khai báo trước.
synchronized (lock) {
    // Critical section dùng monitor của object mà lock tham chiếu.
}
~~~

Khi thread đi vào khối, nó **lấy monitor** của object. Khi ra khỏi khối, kể cả vì exception, monitor được **nhả**. Thread khác muốn vào một khối `synchronized` dùng **đúng cùng object** sẽ phải đợi monitor được nhả.

Khóa được phân biệt theo **reference identity** (`==`), không theo `equals()`, hash code hoặc tên biến. Hai reference trỏ cùng object thì dùng cùng monitor; hai object khác nhau dù nội dung giống nhau thì không tự dùng chung monitor.

~~~java
Object a = new Object();
Object b = a;
Object c = new Object();

System.out.println(a == b); // true
System.out.println(a == c); // false
~~~

Đây là đoạn mã minh họa các identity, không phải file chạy độc lập.

### Vì sao khóa quan trọng về bộ nhớ?

Nếu toàn bộ truy cập một bất biến dùng **cùng monitor**:

- **Mutual exclusion:** chỉ một thread giữ monitor tại một thời điểm, nên hai critical sections dùng cùng monitor không chen vào nhau.
- **Visibility và ordering:** lần unlock monitor `m` *synchronizes-with* lần lock sau trên cùng monitor `m` theo Java Memory Model. Kết hợp program order và tính bắc cầu của *happens-before*, thread vào khóa sau có thể dựa vào các ghi mà thread trước thực hiện trong phạm vi được đồng bộ.

Dùng hai monitor khác nhau sẽ **không bảo vệ cùng một bất biến** nếu hai thread cập nhật cùng dữ liệu. Ngược lại, vô tình dùng **một monitor chung** cho hai nghiệp vụ độc lập có thể gây tranh chấp không cần thiết.

## 2. String literal có thể trỏ tới cùng object toàn cục

String literal trong Java được **intern**; những literal cùng nội dung có thể trỏ đến cùng một instance `String`, kể cả nằm trong các class không liên quan. Chuỗi là immutable nhưng vẫn là một object có monitor; **bất biến của nội dung không làm nó trở thành khóa riêng tư**.

Ví dụ Java 17+ chạy độc lập:

~~~java
// StringLiteralIdentityDemo.java
public class StringLiteralIdentityDemo {
    public static void main(String[] args) {
        String first = "shared-lock";
        String second = "shared-lock";
        String constantExpression = "shared-" + "lock";
        String distinct = new String("shared-lock");

        System.out.println("same literal: " + (first == second));
        System.out.println("constant expression: " +
            (first == constantExpression));
        System.out.println("new String same object: " +
            (first == distinct));
        System.out.println("intern returns literal: " +
            (first == distinct.intern()));
    }
}
~~~

~~~bash
javac StringLiteralIdentityDemo.java
java StringLiteralIdentityDemo
~~~

Stdout:

~~~text
same literal: true
constant expression: true
new String same object: false
intern returns literal: true
~~~

Giải thích:
- Hai literal giống nhau trỏ tới cùng interned object.
- Phép nối hằng `"shared-" + "lock"` là constant expression, được biên dịch thành literal tương ứng.
- `new String(...)` tạo một object String riêng, dù nội dung bằng nhau.
- `intern()` trả về reference chuẩn cho chuỗi đã intern.

### Hai class không liên quan vẫn có thể chặn nhau

~~~java
// Hai đoạn mã minh họa ở hai class khác nhau.
// Class A:
synchronized ("CACHE_LOCK") {
    updateCache();
}

// Class B:
synchronized ("CACHE_LOCK") {
    writeAuditLog();
}
~~~

Hai khối cùng literal `"CACHE_LOCK"` có thể **tranh chấp cùng monitor**, dù `updateCache()` và `writeAuditLog()` độc lập. Nếu B giữ khóa lâu, A phải đợi. Nếu có các khóa khác đang được giữ, cạnh chờ ngoài ý muốn còn có thể góp phần tạo deadlock.

**Sai lầm dễ bỏ sót:** khai báo `private static final String LOCK = "CACHE_LOCK";` **không đủ**. Field là private nhưng **object String mà nó trỏ tới vẫn là interned literal có thể lấy bằng cùng chuỗi**. `final` chỉ làm reference của field không bị gán lại.

Không nên chữa bằng `new String("CACHE_LOCK")` như một khuôn mẫu: object mới có identity riêng trong tình huống đơn giản, nhưng kiểu String không nói lên ý định khóa, có thể bị gán cho nơi khác và dễ khiến người đọc hiểu nhầm giữa equality với identity. Dùng `private final Object` hoặc `private static final Object` làm monitor chuyên biệt dễ kiểm soát hơn.

## 3. Public object cho mã ngoài quyền giữ monitor nội bộ

Cấu trúc nên tránh:

~~~java
// Mã minh họa API thiếu đóng gói:
public class Counter {
    public static final Object LOCK = new Object();
    private static int value;

    public static void increment() {
        synchronized (LOCK) {
            value++;
        }
    }
}
~~~

Code ngoài có thể làm:

~~~java
synchronized (Counter.LOCK) {
    // Công việc chậm hoặc chờ một điều kiện bất kỳ.
}
~~~

Từ thời điểm code ngoài giữ monitor cho tới khi nó nhả, mọi `Counter.increment()` sẽ phải chờ. `public static final` giữ identity ổn định nhưng **không ngăn caller lấy được object**. Lộ monitor là một phụ thuộc API về tiến độ và có thể tạo lock contention, DoS ở mức ứng dụng hoặc vòng chờ.

Các cách lộ tương tự: một field `public`/`protected` chứa lock, getter trả reference lock, truyền lock vào callback hay thành phần không kiểm soát, hoặc dùng object instance công khai của lớp làm monitor.

### Ví dụ xác định: mã ngoài can thiệp vào tiến độ

Chương trình dưới cố ý cung cấp public lock. Hai `CountDownLatch` tạo thứ tự rõ ràng, tránh `Thread.sleep` để cố đoán lịch chạy.

~~~java
// PublicLockInterferenceDemo.java
import java.util.concurrent.CountDownLatch;

public class PublicLockInterferenceDemo {
    static class UnsafeCounter {
        public final Object lock = new Object();
        private int value;

        void increment() {
            synchronized (lock) {
                value++;
            }
        }

        int valueAfterCoordination() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        UnsafeCounter counter = new UnsafeCounter();
        CountDownLatch outsideHasLock = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread outside = new Thread(() -> {
            synchronized (counter.lock) {
                outsideHasLock.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        });

        outside.start();
        outsideHasLock.await();

        Thread worker = new Thread(counter::increment);
        worker.start();

        System.out.println("Before release: " +
            counter.valueAfterCoordination());
        release.countDown();

        outside.join();
        worker.join();
        System.out.println("After release: " +
            counter.valueAfterCoordination());
    }
}
~~~

~~~bash
javac PublicLockInterferenceDemo.java
java PublicLockInterferenceDemo
~~~

Stdout:

~~~text
Before release: 0
After release: 1
~~~

Điểm bảo đảm: main chỉ khởi động worker **sau khi** thread ngoài xác nhận đã lấy monitor. Worker không thể cập nhật `value` trước khi monitor được nhả. Main đọc `value == 0` trước khi mở latch; sau khi `outside.join()` và `worker.join()`, giá trị là 1. Các `join()` cũng tạo bảo đảm visibility cho lần đọc cuối.

Đây là **ví dụ cố tình để lộ khóa**, không phải API gợi ý dùng trong production. Getter `valueAfterCoordination()` chỉ được đọc tại các điểm phối hợp này; trong code thực tế, thao tác đọc và cập nhật bất biến phải được đồng bộ bằng cùng giao thức.

## 4. synchronized(this) và synchronized instance method

Một phương thức:

~~~java
public synchronized void update() {
    // ...
}
~~~

dùng monitor của `this`, tương đương về monitor với:

~~~java
public void update() {
    synchronized (this) {
        // ...
    }
}
~~~

Hai đoạn trên là mã minh họa **hai cách viết**, không phải chương trình độc lập. Nếu object instance đã được đưa cho caller, caller cũng có thể gọi `synchronized(instance)`. Như vậy một **public synchronized method** có thể bị caller bên ngoài chặn bằng việc giữ monitor của object.

Điều này **không phải luôn sai**: có API cố ý công bố giao thức đồng bộ qua object instance. Nhưng nếu việc lấy khóa chỉ là **implementation detail** bảo vệ dữ liệu private, nên dùng một object lock riêng và không trả nó cho caller.

Cũng đừng hiểu `final class` là monitor private: `final` ngăn kế thừa class, không ngăn mã ngoài giữ monitor của instance đã được công bố.

## 5. Cách thiết kế thường phù hợp: private final Object

Đối với trạng thái gắn với một instance:

~~~java
private final Object lock = new Object();
~~~

Đối với trạng thái `static` chung một class:

~~~java
private static final Object LOCK = new Object();
~~~

Ba yếu tố đều có ý nghĩa:
- `private`: code ngoài không thể lấy lock thông qua API thông thường.
- `final`: field không bị gán lại reference, giúp mọi chỗ khóa trên **cùng identity ổn định**.
- `new Object()`: tạo object chuyên dùng làm monitor, không bị vô tình chia sẻ do interning hay singleton chung.

### Ví dụ Java 17+: Counter an toàn với private lock

~~~java
// PrivateLockCounterDemo.java
public class PrivateLockCounterDemo {
    static final class Counter {
        private final Object lock = new Object();
        private int value;

        void increment() {
            synchronized (lock) {
                value++;
            }
        }

        int getValue() {
            synchronized (lock) {
                return value;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        Runnable add = () -> {
            for (int i = 0; i < 1000; i++) {
                counter.increment();
            }
        };

        Thread a = new Thread(add);
        Thread b = new Thread(add);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Count: " + counter.getValue());
    }
}
~~~

~~~bash
javac PrivateLockCounterDemo.java
java PrivateLockCounterDemo
~~~

Stdout:

~~~text
Count: 2000
~~~

Từng instance `Counter` có monitor riêng. Cả `increment()` lẫn `getValue()` dùng **cùng monitor** để bảo vệ `value`. Caller có reference `Counter` vẫn không thể giữ monitor private bằng API thông thường. Main `join()` hai worker rồi in kết quả chính xác 2000.

Nếu có một đường truy cập `value` không dùng lock hoặc dùng lock khác, thiết kế vẫn có thể sai. Private lock không tự xử lý mọi race condition.

### Vì sao không nên gán lại khóa?

Nếu `lock` không final và bị thay bằng object mới, thread A có thể giữ monitor cũ trong lúc thread B lấy monitor mới. Khi đó hai thread cùng lọt vào critical section tưởng như bảo vệ cùng dữ liệu. Giữ identity ổn định và không thay reference là điều kiện thiết kế cơ bản.

## 6. static synchronized và khóa Class object

Một `static synchronized` method dùng monitor của **class object** tương ứng (`MyClass.class`), khác với monitor của instance:

~~~java
// Minh họa trong class MyClass:
public static synchronized void refresh() {
    // Khóa MyClass.class
}
~~~

Tương đương về monitor với:

~~~java
public static void refresh() {
    synchronized (MyClass.class) {
        // ...
    }
}
~~~

Class object được mã khác truy cập bằng class literal; do đó code ngoài cũng có thể `synchronized(MyClass.class)` và chặn static synchronized method. Các static synchronized methods cùng class dùng chung class monitor, kể cả khi chúng bảo vệ trạng thái độc lập.

Nếu chỉ cần khóa bảo vệ static state nội bộ, `private static final Object LOCK = new Object()` giúp tránh công bố monitor. Instance synchronized methods thường khóa `this`; chúng **không tự đồng bộ** với static synchronized methods.

**Chọn lock theo phạm vi bất biến:**

| Phạm vi trạng thái | Lock gợi ý | Vì sao |
| --- | --- | --- |
| Instance fields không chia sẻ giữa object | `private final Object lock` | Mỗi object có monitor riêng |
| Static fields dùng chung trong class | `private static final Object LOCK` | Một monitor ổn định cho static state |
| Nhiều field cùng một bất biến | Một lock chung cho tất cả field liên quan | Không cho reader thấy nửa trạng thái |
| Hai nhóm trạng thái độc lập | Có thể dùng hai lock khác nhau | Tránh contention, nhưng kiểm soát thứ tự nếu có lồng lock |

Đừng tách lock khi bất biến cần cập nhật nhiều field nguyên tử; cũng đừng khóa toàn bộ ứng dụng bằng một lock static chỉ vì cách đó viết đơn giản.

## 7. Các loại đối tượng không nên dùng làm monitor tùy tiện

Nguyên tắc tổng quát là: **không sử dụng một object mà quyền sở hữu, identity hoặc vòng đời nằm ngoài phạm vi đồng bộ của mình**.

| Đối tượng khóa | Rủi ro chính |
| --- | --- |
| `"string literal"` | Interned String có thể được code khác dùng |
| `String.intern()` trên input động | Monitor bị chia sẻ theo nội dung với code khác, không có ownership rõ |
| `Boolean.TRUE` / `Boolean.FALSE` | Singleton được dùng rộng rãi |
| Boxed values như `Integer.valueOf(1)` | Có cache/identity chia sẻ; wrapper dạng value-based không phải lock đáng tin |
| `SomeClass.class` | Class object công khai |
| `this` khi instance được đưa ra ngoài | Caller có thể giữ monitor instance |
| `public final Object LOCK` | Người khác biết chính identity khóa |
| Object do thư viện bên ngoài cung cấp | Thư viện có thể có giao thức monitor khác |
| Một reference khóa mutable bị gán lại | Các thread có thể dùng những monitor khác nhau |

Với boxed primitives, Java/JDK còn có cảnh báo liên quan việc đồng bộ trên **value-based classes**. Không nên dùng một giá trị số/boolean làm monitor cho trạng thái riêng.

### Có nên khóa theo chuỗi key?

Ví dụ:

~~~java
// Mã minh họa nên tránh:
synchronized (userKey.intern()) {
    updateAccount(userKey);
}
~~~

Các key có nội dung giống nhau bị khóa chung, kể cả đến từ code không liên quan; interning chuỗi đầu vào còn gây khó khăn khi quản lý việc chia sẻ monitor và vòng đời dữ liệu. **Không dùng intern làm mặc định để tạo per-key lock.**

Nếu thật sự cần khóa theo key, hãy xây dựng registry object lock với **atomic creation, ownership, lifecycle/eviction** rõ ràng, hoặc dùng thao tác nguyên tử của `ConcurrentHashMap` (ví dụ `compute`/`computeIfAbsent` khi phù hợp với bất biến). Một `new Object()` mới trong mỗi lần gọi sẽ **không** giúp hai request cùng key đồng bộ nhau. Registry lock tự viết cũng cần tránh race khi thêm/xóa khóa và tránh giữ lock lâu cho I/O.

## 8. Những hệ quả về liveness và khả năng chẩn đoán

### Contention không mong đợi

Một literal hoặc public monitor bị chia sẻ khiến nhiều tác vụ không liên quan **xếp hàng** trên cùng monitor, tăng latency và giảm throughput. Một thư viện mới thêm `synchronized("CACHE_LOCK")` có thể vô tình làm chậm code cũ cùng dùng chuỗi ấy.

Trong thread dump, thread chờ lấy monitor intrinsic thường ở trạng thái `BLOCKED`. Nhưng **BLOCKED không tự chứng minh deadlock**: chờ một đoạn khóa bình thường là hợp lệ. Cần kiểm tra chủ monitor, stack trace, thời gian chờ và tiến triển của tác vụ.

### Deadlock do vòng chờ

Giả sử T1 giữ monitor A và chờ B, còn T2 giữ B và chờ A:

~~~text
T1: giữ A -> chờ B
T2: giữ B -> chờ A
=> Cả hai có thể chờ vô hạn.
~~~

Một monitor công khai giúp mã ngoài thêm những cạnh chờ mà thành phần bên trong không kiểm soát. Private lock giảm sự can thiệp bất ngờ, nhưng **không loại bỏ deadlock** nếu code của mình vẫn lấy nhiều khóa theo thứ tự không nhất quán. Nên xác định lock ordering, giữ đoạn tới hạn ngắn và tránh gọi callback/I/O kéo dài trong lúc giữ khóa khi có thể.

### wait/notify trên monitor bị lộ

`Object.wait()`, `notify()`, `notifyAll()` liên quan tới monitor của object. Nếu đối tượng condition monitor bị lộ, mã ngoài có thể gửi thông báo không đúng giao thức. Ngay cả với monitor private, `wait()` có thể **spurious wakeup**, nên việc chờ predicate phải đặt trong vòng `while` kiểm tra lại điều kiện.

### Giới hạn về bảo mật

Private lock là **đóng gói và kiểm soát đồng bộ**, không phải cơ chế bảo mật tuyệt đối với mọi mã chạy trong cùng JVM. Nếu mã không tin cậy có quyền reflection/bytecode instrumentation hay truy cập đặc quyền vào nội bộ, cần biện pháp cách ly thích hợp ở cấp ứng dụng/hệ thống. Bài toán chính ở đây là giảm phụ thuộc monitor ngầm giữa những thành phần thông thường.

## 9. ReentrantLock vẫn cần đóng gói tương tự

`ReentrantLock` không phải monitor intrinsic của `synchronized`, nhưng một reference `ReentrantLock` công khai cũng cho code ngoài khả năng gọi `lock()` và giữ khóa. Cùng nguyên tắc: nếu lock là implementation detail, dùng `private final ReentrantLock` và không trả reference qua API.

~~~java
// PrivateReentrantLockDemo.java
import java.util.concurrent.locks.ReentrantLock;

public class PrivateReentrantLockDemo {
    static final class Counter {
        private final ReentrantLock lock = new ReentrantLock();
        private int value;

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int getValue() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        Thread a = new Thread(counter::increment);
        Thread b = new Thread(counter::increment);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Value: " + counter.getValue());
    }
}
~~~

~~~bash
javac PrivateReentrantLockDemo.java
java PrivateReentrantLockDemo
~~~

Stdout:

~~~text
Value: 2
~~~

Với `ReentrantLock` phải `unlock()` trong `finally` **sau khi đã lấy thành công**. Nếu dùng `tryLock()`, chỉ unlock khi nó trả `true`. `tryLock`/timeout có thể giúp xây dựng giao thức chờ thích hợp, nhưng không tự sửa sai phạm vi khóa hoặc mọi khả năng deadlock.

## 10. Review code và refactor an toàn

Một quy trình kiểm tra:

1. **Tìm expression khóa** trong mọi `synchronized(x)` và các method `synchronized`. Xác định object thật mà `x` trỏ tới.
2. **Kiểm tra identity:** có String literal, `intern`, boxed cache, class literal, singleton hoặc object public không? Hai tên khác nhau có thể tham chiếu cùng object không?
3. **Kiểm tra ownership:** lock có bị lộ qua field/getter/callback không? Caller hoặc thư viện khác có thể giữ lock không?
4. **Xác định bất biến:** lock bảo vệ những field nào? Mọi đường đọc/ghi có cùng giao thức không?
5. **Đảm bảo identity ổn định:** ưu tiên `private final`/`private static final`; không gán lại khóa.
6. **Đánh giá nested locking:** có thứ tự lấy khóa rõ ràng không? Có giữ khóa khi gọi mã ngoài, chờ network hoặc lock khác không?
7. **Kiểm tra API contract trước khi đổi monitor:** một public synchronized method hoặc object monitor được công bố **cố ý** có thể đã là phần hợp đồng người dùng đang dựa vào. Chuyển sang private lock có thể phá đồng bộ của caller.
8. **Kiểm chứng sau sửa:** dùng kiểm thử đồng thời, invariant assertions, thread dump và số liệu contention khi cần; kết quả stress test không thay thế phân tích ownership.

| Mẫu cần cân nhắc tránh | Lựa chọn thường rõ ràng hơn | Mục đích |
| --- | --- | --- |
| `synchronized("LOCK")` | `private final Object lock = new Object()` | Monitor không trùng với literal interned |
| `private static final String LOCK = "LOCK"` | `private static final Object LOCK = new Object()` | Field private **và** identity riêng |
| `public static final Object LOCK` | `private static final Object LOCK` | Không lộ monitor nội bộ |
| `public synchronized void update()` khi object dùng công khai | Khối `synchronized(privateLock)` trong phương thức thường | Không bị code ngoài khóa trực tiếp instance |
| `synchronized(MyClass.class)` | `synchronized(PRIVATE_STATIC_LOCK)` | Không dùng class monitor rộng rãi |
| `synchronized(key.intern())` | Registry lock được quản lý hoặc atomic operation theo key | Tránh va chạm ngoài ý muốn |

Đổi khóa từ `this` sang private lock không phải refactor máy móc: nếu consumer cũ dựa vào `synchronized(instance)` để điều phối, cần xem xét tương thích và cập nhật giao thức nhất quán.

## 11. Những sai lầm phổ biến

- **“Hai biến String khác tên là hai khóa khác nhau.”** Sai: nếu trỏ cùng interned literal thì cùng monitor.
- **“Private String literal là private monitor.”** Sai: private chỉ áp dụng cho field, còn object vẫn chia sẻ.
- **“Có final nên public Object LOCK an toàn.”** Sai: caller vẫn lấy được identity dù không gán lại được field.
- **“synchronized(this) luôn riêng tư.”** Sai: caller giữ instance cũng có thể giữ monitor ấy.
- **“static synchronized khóa một instance.”** Sai: nó khóa class object.
- **“Hai String bằng equals thì synchronized cùng khóa.”** Sai nếu identity khác; monitor dựa trên `==`.
- **“Private lock bảo đảm không deadlock.”** Sai: nested locks trong nội bộ vẫn có thể tạo vòng chờ.
- **“Mọi thread BLOCKED đều deadlock.”** Sai: có thể chỉ chờ monitor đang được giữ hợp lệ.
- **“Dùng new String để tạo lock là giải pháp tốt nhất.”** Không cần; object monitor chuyên dụng rõ ràng hơn.

## 12. Tự kiểm tra

**1.** Hai class độc lập cùng dùng `synchronized("CACHE")`. Vì sao chúng có thể chặn nhau?  
**Đáp án:** Vì cùng String literal được intern và hai đoạn synchronized giữ cùng monitor.

**2.** Vì sao `private static final String LOCK = "X"` vẫn có rủi ro?  
**Đáp án:** Bất kỳ đoạn code nào dùng literal `"X"` tương ứng đều có thể lấy cùng interned object.

**3.** `public final Object lock = new Object()` có bảo đảm chỉ lớp sở hữu giữ monitor không?  
**Đáp án:** Không. `final` chỉ cố định reference; field public tiết lộ khóa.

**4.** `public synchronized void increment()` dùng monitor nào?  
**Đáp án:** Monitor của `this`; caller có instance có thể `synchronized(instance)`.

**5.** `static synchronized` và `synchronized(this)` có tự cùng monitor không?  
**Đáp án:** Không. Cái đầu dùng class object, cái sau dùng instance object.

**6.** Nếu object khóa bị gán lại khi chương trình đang chạy thì vấn đề gì?  
**Đáp án:** Những thread có thể giữ các monitor khác nhau, phá mutual exclusion dù chúng tưởng cùng bảo vệ một field.

**7.** Khi nào `private final Object` chưa đủ để an toàn?  
**Đáp án:** Khi code có đường truy cập không dùng lock, lock ordering sai, bất biến trải nhiều lock, hoặc tài nguyên không cùng phạm vi sở hữu.

**8.** Với `ReentrantLock`, khi nào unlock?  
**Đáp án:** Trong `finally` sau khi đã lấy khóa thành công; `tryLock` thất bại thì không được unlock.

**Ghi nhớ:** Monitor của `synchronized` được nhận diện theo **object identity**. Chọn khóa có identity riêng, ổn định và không bị lộ khi nó chỉ bảo vệ implementation detail. Tránh literal/interned String và public object; đồng thời phải giữ giao thức đồng bộ nhất quán trên mọi đường đọc/ghi và tôn trọng hợp đồng API hiện có.

### Tài liệu tham khảo chuẩn

- Java Language Specification 17, `17.1 (Locks), `17.4 (Memory Model): https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- Java Language Specification 17, `3.10.5 String Literals: https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5
- JDK 17 `String.intern()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#intern()
- JDK 17 `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html