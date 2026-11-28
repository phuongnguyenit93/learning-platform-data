# Synchronized, monitor và bảo vệ bất biến dùng chung

> **Phạm vi:** Java 27 — chương **Nền tảng lập trình đồng thời**. Bài học giải thích intrinsic monitor, từ khóa `synchronized`, Java Memory Model, quan hệ *happens-before* và cách giữ **bất biến (invariant) của trạng thái chia sẻ** khi nhiều thread truy cập. Các ví dụ dùng cú pháp và API Java hiện hành, không cần preview feature. Đặc biệt, những khuyến cáo cũ về virtual-thread pinning được phân biệt rõ với Java 27.

## 1. Vấn đề: nhiều luồng cùng thay đổi một trạng thái

Giả sử một bộ đếm được nhiều luồng cập nhật:

~~~java
public final class UnsafeCounter {
    private int value;

    public void increment() {
        value++;
    }

    public int get() {
        return value;
    }
}
~~~

`value++` **không phải một thao tác nguyên tử**. Về logic, nó gồm đọc giá trị hiện tại, cộng 1 rồi ghi lại. Hai luồng có thể cùng đọc 10, cùng tính 11 và cùng ghi 11. Một lần tăng bị mất dù cả hai đã gọi `increment()`.

~~~text
Ban đầu value = 10

Thread A                 Thread B
   |                        |
đọc 10                  đọc 10
tính 11                 tính 11
ghi 11                  ghi 11
   |                        |
           value = 11
  (đáng lẽ là 12 sau hai lần tăng)
~~~

Đây là **lost update**, một dạng race condition. Không chỉ bộ đếm mới có nguy cơ: một tài khoản phải luôn có số dư không âm; một kho hàng phải bảo đảm `0 <= reserved <= total`; một collection phải giữ cấu trúc nội bộ nhất quán.

Hai vấn đề cần giải quyết riêng nhưng có liên quan:

1. **Mutual exclusion:** ngăn các luồng thực hiện đồng thời một nhóm hành động cần nguyên tử.
2. **Memory visibility / ordering:** bảo đảm một luồng có thể quan sát đúng các giá trị mà luồng khác đã công bố theo quan hệ đồng bộ hóa hợp lệ.

`synchronized` cung cấp cả hai khi mọi truy cập liên quan tuân theo cùng chiến lược khóa.

## 2. Monitor và intrinsic lock là gì?

Theo Java Language Specification, **mỗi object trong Java có một monitor đi kèm**. Một thread có thể cố lấy khóa (*lock*) của monitor đó để vào vùng `synchronized`.

- Một thời điểm chỉ **một thread** có quyền sở hữu monitor của object cụ thể.
- Nếu thread khác muốn vào vùng dùng **cùng monitor** khi khóa đang bị giữ, nó phải chờ.
- Nếu hai vùng `synchronized` dùng **hai object khóa khác nhau**, chúng không chặn lẫn nhau chỉ vì cùng xuất hiện trong chương trình.
- Khi rời vùng `synchronized`, dù bình thường hay ném exception, khóa được tự động nhả.
- Intrinsic monitor là **reentrant**: thread đang sở hữu monitor có thể lấy lại chính monitor đó khi gọi lồng nhau.

Ví dụ:

~~~java
public final class SafeCounter {
    private final Object lock = new Object();
    private int value;

    public void increment() {
        synchronized (lock) {
            value++;
        }
    }

    public int get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

`lock` là một object độc lập chỉ làm nhiệm vụ đồng bộ. Cả hai method phải dùng **cùng lock** để việc đọc và ghi `value` có quan hệ đồng bộ hóa. Nếu chỉ khóa lúc ghi mà đọc trực tiếp không khóa/không có cơ chế memory ordering thích hợp, hợp đồng an toàn luồng chưa được bảo đảm.

### 2.1. Minh họa quyền sở hữu monitor

~~~text
             Monitor của object "lock"
            ┌────────────────────────┐
Thread A ──▶│ vào synchronized(lock) │──▶ giữ lock
            │    critical section    │
            └────────────────────────┘
                        ▲
                        │ phải chờ
Thread B ───────────────┘

Khi A rời synchronized(lock):
  unlock → thread khác có thể lấy lock
  (không cam kết B luôn được chọn đầu tiên)
~~~

Không có quy tắc mặc định bảo đảm thứ tự FIFO hoặc công bằng (*fairness*) khi nhiều thread cùng chờ monitor. Không nên dựa vào thứ tự cụ thể từ một lần chạy thử.

### 2.2. Null không thể là monitor

Biểu thức khóa trong `synchronized(expression)` phải tính ra một **object reference khác null**. Nếu giá trị null, chương trình ném `NullPointerException` trước khi vào vùng tới hạn:

~~~java
Object lock = null;
// synchronized (lock) { } // NullPointerException tại runtime
~~~

Vì vậy, khi cần private lock, dùng:

~~~java
private final Object lock = new Object();
~~~

Không thay thế field này bằng một reference có thể bị gán lại trong quá trình sống của đối tượng.

## 3. Hai dạng synchronized phổ biến

### 3.1. Synchronized statement

Dạng block dùng monitor từ một object cụ thể:

~~~java
private final Object lock = new Object();
private int value;

public void add(int amount) {
    synchronized (lock) {
        value += amount;
    }
}
~~~

Block chỉ bảo vệ các lệnh nằm bên trong nó. Với trạng thái có nhiều field, phải giữ khóa xuyên suốt **toàn bộ bước kiểm tra và cập nhật liên quan**; không thể chỉ khóa dòng ghi cuối.

### 3.2. Instance synchronized method

~~~java
public final class MethodCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
~~~

`synchronized` trên **instance method** dùng monitor của `this`. Về ý nghĩa khóa, tương đương với:

~~~java
public void increment() {
    synchronized (this) {
        count++;
    }
}
~~~

Tuy nhiên, dùng `this` làm monitor đồng nghĩa bất kỳ code nào cầm reference đến instance đều có thể khóa `synchronized(instance)`. Điều này có thể tạo coupling hoặc deadlock ngoài dự kiến. Với thư viện hoặc đối tượng có trạng thái phức tạp, một `private final Object lock` thường giúp giữ quyền sở hữu khóa rõ ràng hơn.

### 3.3. Static synchronized method

~~~java
public final class GlobalCounter {
    private static int count;

    public static synchronized void increment() {
        count++;
    }

    public static synchronized int get() {
        return count;
    }
}
~~~

`static synchronized` dùng monitor của **Class object** tương ứng, tức về khóa tương đương:

~~~java
synchronized (GlobalCounter.class) {
    // thao tác trên static state của GlobalCounter
}
~~~

**Không nhầm hai monitor:**

- `instance.synchronizedMethod()` dùng `instance`.
- `GlobalCounter.staticSynchronizedMethod()` dùng `GlobalCounter.class`.
- Hai instance khác nhau có **hai monitor khác nhau**.
- Instance monitor và Class monitor cũng **khác nhau**.

Đừng dùng một instance lock để bảo vệ static field chia sẻ giữa tất cả instance, trừ khi một thiết kế bổ sung thật sự bảo đảm mọi truy cập dùng cùng một khóa.

## 4. Tính nguyên tử, visibility và happens-before

### 4.1. Mutual exclusion giải quyết gì?

Một thread giữ monitor `lock` thì thread khác không thể đồng thời đi vào bất kỳ block/method nào muốn lấy **cùng monitor đó**. Điều này làm cho chuỗi lệnh bên trong block xuất hiện như một thao tác **không bị thread khác cùng tuân thủ lock chen vào**.

Ví dụ:

~~~java
public void increment() {
    synchronized (lock) {
        value = Math.addExact(value, 1);
    }
}
~~~

`Math.addExact` còn phát hiện tràn số nguyên thay vì âm thầm wraparound. Khóa và kiểm tra tràn giải quyết **hai lỗi khác nhau**: synchronization bảo vệ việc truy cập đồng thời, còn `addExact` bảo vệ miền biểu diễn số.

### 4.2. Visibility giải quyết gì?

Một luồng có thể chạy trên CPU/core khác, và compiler/JIT/hardware có thể tối ưu các thao tác bộ nhớ trong giới hạn Java Memory Model. Vì vậy, không được cho rằng đọc một field thường từ thread khác sẽ luôn thấy ngay lần ghi mới nhất nếu không có quan hệ đồng bộ phù hợp.

Quy tắc trung tâm:

> Một hành động **unlock monitor M** *happens-before* mọi hành động **lock monitor M** xảy ra sau đó theo synchronization order.

Hệ quả: các thao tác đã xảy ra trong thread A trước khi nhả khóa có thể được quan sát theo đúng quan hệ happens-before bởi thread B sau khi B lấy cùng monitor đó.

~~~text
Thread A                         Thread B
    synchronized(lock) {            synchronized(lock) {
        x = 42;                         int seen = x;
    }                                  // thấy ghi tương ứng nếu A
     unlock(lock)                         // đã unlock trước B lock
          |                         }
          | happens-before
          └──────────────────────────▶ lock(lock)
~~~

Điều kiện “**cùng monitor**” rất quan trọng. Khóa một object A để ghi rồi khóa object B để đọc không thiết lập edge này chỉ vì tên biến cùng là `x`.

### 4.3. Không phải mọi phép đọc đều tự được bảo vệ

Ví dụ lỗi:

~~~java
final class IncompleteCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    int get() {
        return value; // không synchronized, có data race
    }
}
~~~

Bản sửa đơn giản:

~~~java
synchronized int get() {
    return value;
}
~~~

Một số API có thể dùng `volatile` hoặc atomics thay cho lock khi mô hình phù hợp, nhưng **đừng phối hợp vô kỷ luật** nhiều cơ chế cho cùng invariant. Hãy viết rõ field nào được khóa nào bảo vệ.

### 4.4. Thread.start và join cũng có memory guarantees

JLS còn quy định:

- Các hành động trước `thread.start()` *happen-before* những hành động trong thread đã khởi động.
- Các hành động trong một thread *happen-before* việc thread khác nhận biết nó kết thúc qua `join()` thành công.

Vì vậy, một demo đơn luồng khởi tạo state rồi start worker và join có thể quan sát đúng kết quả nhờ `start/join`; điều này **không chứng minh** rằng biến shared được cập nhật đồng thời đã an toàn khi các worker còn đang chạy.

## 5. Bảo vệ invariant: khóa phải bao trọn điều kiện và cập nhật

Một **invariant** là điều kiện phải đúng ở các điểm trạng thái được công bố. Với kho hàng:

\`total >= 0\`, \`reserved >= 0\`, \`reserved <= total\`.

Sai lầm là kiểm tra điều kiện bên ngoài khóa rồi chỉ khóa phần ghi:

~~~java
// MÃ SAI: minh họa race condition, không dùng trong chương trình thật.
// if (requested <= total - reserved) {
//     synchronized (lock) {
//         reserved += requested;
//     }
// }
~~~

Hai thread có thể cùng đọc số lượng còn lại, cùng vượt qua kiểm tra rồi cùng tăng `reserved`, làm nó lớn hơn `total`.

### 5.1. Một implementation bảo vệ toàn bộ invariant

~~~java
public final class Inventory {
    private final Object lock = new Object();
    private int total;
    private int reserved;

    public Inventory(int initialTotal) {
        if (initialTotal < 0) {
            throw new IllegalArgumentException("Negative initial stock");
        }
        total = initialTotal;
    }

    public boolean reserve(int quantity) {
        requirePositive(quantity);

        synchronized (lock) {
            int available = total - reserved;
            if (quantity > available) {
                return false;
            }

            reserved = Math.addExact(reserved, quantity);
            return true;
        }
    }

    public void release(int quantity) {
        requirePositive(quantity);

        synchronized (lock) {
            if (quantity > reserved) {
                throw new IllegalArgumentException("Not reserved");
            }
            reserved -= quantity;
        }
    }

    public void restock(int quantity) {
        requirePositive(quantity);

        synchronized (lock) {
            total = Math.addExact(total, quantity);
        }
    }

    public Snapshot snapshot() {
        synchronized (lock) {
            return new Snapshot(total, reserved);
        }
    }

    private static void requirePositive(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }

    public record Snapshot(int total, int reserved) {
        public int available() {
            return total - reserved;
        }
    }
}
~~~

Ví dụ sử dụng:

~~~java
Inventory inventory = new Inventory(10);

System.out.println(inventory.reserve(7));       // true
System.out.println(inventory.reserve(4));       // false
System.out.println(inventory.snapshot().available()); // 3
inventory.release(2);
System.out.println(inventory.snapshot().available()); // 5
~~~

**Vì sao đúng ở mức đồng thời?**

1. Cả `total` và `reserved` là `private`, không lộ reference có thể sửa trực tiếp.
2. Mọi phép đọc/ghi **sau khởi tạo** của hai field đều diễn ra khi giữ **cùng lock**.
3. `reserve()` kiểm tra tồn kho và cập nhật `reserved` trong **một critical section**.
4. `restock()` kiểm tra tràn bằng `Math.addExact` trước khi field được gán; nếu ném exception, giá trị cũ được giữ nguyên.
5. `snapshot()` lấy `total` và `reserved` dưới cùng một lock, rồi trả record chỉ chứa primitive, nên caller có một ảnh chụp nhất quán.

Ví dụ này chỉ quản lý trạng thái **trong một JVM**. Nó không tự tạo transaction xuyên database, nhiều process hoặc nhiều máy. Với nhiều instance ứng dụng, cần transaction/constraint/locking tại nguồn dữ liệu chia sẻ bên ngoài.

### 5.2. Hai getter riêng lẻ không tạo một snapshot nguyên tử

Giả sử API có hai method:

~~~java
public int total() {
    synchronized (lock) {
        return total;
    }
}

public int reserved() {
    synchronized (lock) {
        return reserved;
    }
}
~~~

Mỗi method **riêng** là thread-safe, nhưng caller có thể đọc `total()` tại thời điểm T1 và `reserved()` tại T2 khi thread khác đã cập nhật ở giữa. Hai giá trị có thể đến từ **hai trạng thái khác nhau**.

Nếu nghiệp vụ cần `total - reserved` nhất quán, dùng `snapshot().available()` hoặc một method tính toán dưới cùng một lần giữ lock. **Thread-safe từng method không đồng nghĩa mọi tổ hợp method đều nguyên tử.**

### 5.3. Bất biến dùng chung gồm nhiều object

Nếu invariant bao trùm hai object, chỉ khóa riêng từng object vào thời điểm khác nhau có thể không đủ. Ví dụ chuyển tiền từ tài khoản A sang B đòi một thao tác **trừ A và cộng B** cùng hoàn tất hoặc cùng thất bại. Cần một chiến lược khóa toàn bộ trạng thái liên quan, hoặc một giao dịch ở tầng lưu trữ nếu dữ liệu được quản lý ngoài JVM.

## 6. Chọn đúng lock object và phạm vi khóa

Khuyến nghị phổ biến cho lớp tự quản lý state:

~~~java
public final class Settings {
    private final Object lock = new Object();
    private String mode = "normal";

    public String mode() {
        synchronized (lock) {
            return mode;
        }
    }

    public void setMode(String next) {
        java.util.Objects.requireNonNull(next, "next");
        synchronized (lock) {
            mode = next;
        }
    }
}
~~~

**Ưu điểm của private final lock:**

- Không cho caller dễ dàng khóa cùng monitor từ bên ngoài.
- Không phụ thuộc vào identity của một `String`, wrapper số, record hay object value-based.
- Không có chuyện lock reference bị gán lại giữa những lần dùng.
- Khai báo rõ “monitor này bảo vệ state nào” trong class.

### 6.1. Tránh khóa trên object do caller sở hữu

Không nên:

~~~java
// Không dùng làm lock riêng cho instance:
synchronized (incomingRequest) { ... }
synchronized ("shared-key") { ... }
synchronized (Integer.valueOf(42)) { ... }
~~~

Lý do:

- Caller có thể dùng `incomingRequest` làm lock ở chỗ khác.
- String literal thường được intern, nên code không liên quan có thể dùng **cùng object**.
- Một số wrapper/value-based objects không thích hợp làm monitor; compiler/JVM có thể cảnh báo các kiểu value-based khi bị sử dụng để synchronization.
- Khi lock có thể bị dùng bởi code ngoài ý muốn, nguy cơ deadlock và tranh chấp bất thường tăng.

Không khóa trên `this` cho library class mà bên ngoài có quyền truy cập object nếu bạn muốn **ẩn hoàn toàn cơ chế đồng bộ**. `synchronized method` vẫn là lựa chọn hợp lệ cho các lớp nhỏ có contract rõ ràng; đây là một trade-off về encapsulation chứ không phải API lỗi thời.

### 6.2. Chỉ giữ khóa quanh trạng thái thật sự chia sẻ

~~~java
public String report() {
    Snapshot data;
    synchronized (lock) {
        data = new Snapshot(total, reserved);
    }

    // Format bên ngoài lock: không cần giữ monitor khi tạo chuỗi.
    return "total=" + data.total()
            + ", available=" + data.available();
}
~~~

`Snapshot` là record bất biến đã nêu trong ví dụ `Inventory`. Mục đích là copy trạng thái nhanh, sau đó xử lý tốn thời gian ở ngoài critical section.

Tránh giữ monitor trong khi:

- Gọi mạng, database, ghi file hoặc API có thể chờ lâu.
- Gọi callback do caller cung cấp mà bạn không kiểm soát.
- Chờ một task/thread khác hoàn tất trong khi task đó có thể cần chính lock hiện tại.
- Tính toán lớn không phụ thuộc shared mutable state.

Việc khóa rộng có thể đơn giản hơn và đúng hơn lúc đầu. Tối ưu hẹp hóa sau khi đã chứng minh invariant vẫn được bảo vệ, thay vì hẹp hóa trước rồi tạo race condition.

## 7. Reentrancy: một thread được vào lại cùng monitor

Intrinsic monitor **reentrant**. Khi một thread đã giữ monitor, nó có thể gọi thêm một method hoặc block dùng cùng monitor; JVM quản lý số lần lock/unlock tương ứng.

~~~java
public final class ReentrantCounter {
    private int count;

    public synchronized void addTwo() {
        increment();
        increment();
    }

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
~~~

`addTwo()` giữ monitor của `this` rồi gọi `increment()` cũng yêu cầu cùng monitor. Thread **không tự deadlock với chính mình** vì intrinsic lock cho phép reentrancy.

Reentrancy **không** có nghĩa mọi callback hoặc kế thừa lẫn nhau đều an toàn: gọi method có thể tạo đệ quy vô hạn, gọi code bên ngoài làm thay đổi invariant hoặc tạo vòng chờ qua **monitor khác** vẫn có thể gây lỗi.

### 7.1. Thả khóa khi thoát block

~~~java
synchronized (lock) {
    if (badInput) {
        throw new IllegalArgumentException("Invalid");
    }
    updateState();
}
// Java nhả lock ngay cả khi block kết thúc bằng exception.
~~~

Khác với `Lock.lock()` trong `java.util.concurrent.locks`, intrinsic `synchronized` **không cần viết `unlock()` thủ công**. Dùng `try/finally` riêng chỉ để nhả monitor là không cần thiết.

## 8. So sánh synchronized, volatile và AtomicInteger

Ba công cụ cùng liên quan concurrency nhưng không thay thế hoàn toàn cho nhau:

| Cơ chế | Visibility/order | Đảm bảo atomic read-modify-write | Bảo vệ invariant nhiều field |
| --- | --- | --- | --- |
| `synchronized` dùng cùng monitor | Có | Có, với thao tác bên trong critical section | Có, nếu tất cả truy cập liên quan cùng theo lock |
| `volatile` field | Có các quan hệ memory-ordering của volatile | Không cho `count++` | Không tự bảo vệ nhiều field |
| `AtomicInteger`, `AtomicLong` | Có memory semantics theo API | Có với `incrementAndGet`, `compareAndSet`... | Không tự biến tổ hợp nhiều field thành transaction |
| `ReentrantLock` | Có, theo hợp đồng Lock | Có với critical section | Có, nếu dùng cùng lock đúng cách |

### 8.1. Volatile phù hợp cho một cờ trạng thái độc lập

~~~java
public final class StopSignal {
    private volatile boolean stopRequested;

    public void requestStop() {
        stopRequested = true;
    }

    public boolean isStopRequested() {
        return stopRequested;
    }
}
~~~

`volatile` phù hợp khi đơn vị trạng thái là **một cờ** và hành động đọc/ghi cần visibility rõ ràng. Nhưng:

~~~java
private volatile int count;

// count++ vẫn không nguyên tử:
// count++;
~~~

`volatile` không hợp nhất ba bước đọc–cộng–ghi thành một thao tác atomic.

### 8.2. AtomicInteger cho bộ đếm độc lập

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int get() {
        return count.get();
    }
}
~~~

Đây là một lựa chọn đơn giản khi state chỉ là bộ đếm độc lập và không cần invariant giữa nhiều field. Các phương thức atomic khác có hợp đồng riêng: ví dụ `LongAdder` hữu ích với bộ đếm contention cao nhưng `sum()` **không phải snapshot nguyên tử** nếu cập nhật vẫn đang diễn ra.

### 8.3. Vì sao không dùng hai atomic cho invariant chung?

~~~java
// Hai field atomic không tự bảo vệ invariant reserved <= total.
AtomicInteger total = new AtomicInteger(10);
AtomicInteger reserved = new AtomicInteger(0);
~~~

Nếu logic đọc `total.get()`, so sánh rồi gọi `reserved.addAndGet(...)`, các luồng vẫn có thể thấy snapshot lệch nhau và chấp thuận quá nhiều yêu cầu.

Có thể xây state immutable và dùng một `AtomicReference<State>` cùng CAS loop, nhưng thiết kế sẽ phức tạp hơn. Với trạng thái kết hợp nhiều field, **một private monitor và critical section đúng** thường dễ chứng minh tính đúng đắn hơn.

## 9. wait, notify và notifyAll: phối hợp bằng điều kiện

Intrinsic monitor không chỉ cung cấp mutual exclusion. Mỗi object còn có một **wait set** phục vụ `Object.wait()`, `notify()` và `notifyAll()`.

Ba phương thức này vẫn có trong Java 27 và cần hiểu để đọc code hoặc viết cơ chế phối hợp mức thấp. Tuy nhiên, với hàng đợi, tín hiệu và đồng bộ phức tạp trong ứng dụng mới, thường nên ưu tiên các abstraction rõ hợp đồng trong `java.util.concurrent` như `BlockingQueue`, `CountDownLatch` hoặc `Condition`.

| Thao tác | Hành vi quan trọng |
| --- | --- |
| `lock.wait()` | Thread phải đang sở hữu monitor của `lock`; tạm nhả monitor để chờ, rồi phải lấy lại monitor trước khi trở về |
| `lock.notify()` | Đánh thức một thread đang ở wait set; không cam kết chọn thread nào |
| `lock.notifyAll()` | Đánh thức các thread đang đợi trên monitor đó; chúng phải cạnh tranh lấy lại khóa |
| `Thread.sleep(...)` | Tạm dừng thread nhưng **không tự nhả monitor** mà thread đang giữ |

\`wait\`, \`notify\`, \`notifyAll\` phải được gọi khi thread **đang sở hữu đúng monitor của object nhận lời gọi**. Nếu không, `IllegalMonitorStateException` được ném.

### 9.1. Dùng vòng while để kiểm tra điều kiện

Không viết:

~~~java
// Không dùng if để kiểm tra một lần:
// synchronized (lock) {
//     if (!ready) {
//         lock.wait();
//     }
//     consume();
// }
~~~

Java cho phép **spurious wakeup** và điều kiện có thể đã bị thread khác thay đổi trước khi thread đang chờ lấy lại lock. Dùng `while`:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }

    consume();
}
~~~

Mọi thao tác đọc/ghi `ready` và các trạng thái mà `consume()` phụ thuộc phải tuân theo cùng monitor, hoặc theo hợp đồng đồng bộ tương đương được chứng minh rõ.

### 9.2. Ví dụ đầy đủ: hộp một phần tử

~~~java
import java.util.Objects;

public final class OneSlot<E> {
    private final Object lock = new Object();
    private E item;
    private boolean occupied;

    public void put(E value) throws InterruptedException {
        Objects.requireNonNull(value, "value");

        synchronized (lock) {
            while (occupied) {
                lock.wait();
            }

            item = value;
            occupied = true;
            lock.notifyAll();
        }
    }

    public E take() throws InterruptedException {
        synchronized (lock) {
            while (!occupied) {
                lock.wait();
            }

            E value = item;
            item = null;
            occupied = false;
            lock.notifyAll();
            return value;
        }
    }
}
~~~

Bất biến của lớp: `occupied == true` nghĩa là có một item, và không có thread được đưa vào item thứ hai khi chưa lấy item cũ. Hai method thay đổi `item` và `occupied` dưới cùng monitor.

Diễn biến:

1. `take()` gặp hộp rỗng → `wait()`, **nhả monitor** cho producer.
2. Producer gọi `put()`, cập nhật cả hai field, gọi `notifyAll()` rồi rời synchronized block.
3. Consumer được đánh thức nhưng **phải lấy lại monitor** trước khi tiếp tục.
4. Consumer kiểm tra lại điều kiện trong `while` và chỉ lấy item khi điều kiện đúng.

`notifyAll()` **không nhả monitor ngay lập tức**. Nó đánh thức các thread đang đợi; thread có thể tiếp tục chỉ khi sở hữu được monitor. `InterruptedException` trong ví dụ được truyền lên caller, không bị nuốt.

Trong code sản xuất, nếu nhu cầu chỉ là một queue có sức chứa hữu hạn, nên cân nhắc:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
queue.put("task");
String task = queue.take();
~~~

`BlockingQueue` có sẵn hợp đồng về capacity, block, interruption và thread safety; tránh tự duy trì `wait/notifyAll` trừ khi thực sự cần một abstraction khác.

### 9.3. Tránh nhầm sleep với wait

~~~java
synchronized (lock) {
    Thread.sleep(100);
}
~~~

Trong thời gian `sleep`, thread **vẫn giữ** monitor `lock`. Code trên có thể làm các thread khác chờ không cần thiết. Nếu cần chờ điều kiện, dùng primitive phối hợp phù hợp thay vì giữ monitor rồi ngủ.

## 10. Deadlock: đúng khóa nhưng sai thứ tự

**Deadlock** xảy ra khi các thread chờ nhau theo một vòng mà không thread nào giải phóng được tài nguyên cần thiết.

Ví dụ tình huống không an toàn:

~~~text
Thread A: lock(accountA) → chờ accountB
Thread B: lock(accountB) → chờ accountA

                 accountA    accountB
                    ▲           ▲
                    │           │
                Thread A ─▶ Thread B
                    ▲           │
                    └───────────┘
                  vòng chờ deadlock
~~~

Đoạn mã gây rủi ro (chỉ minh họa, **không chạy** để kiểm thử):

~~~java
// Thread A có thể giữ a rồi đợi b.
// synchronized (a) {
//     synchronized (b) {
//         doWork();
//     }
// }

// Thread B có thể giữ b rồi đợi a.
// synchronized (b) {
//     synchronized (a) {
//         doWork();
//     }
// }
~~~

Không có bảo đảm rằng Java runtime sẽ tự phát hiện và hủy một deadlock. Cách phòng ngừa quan trọng là **đặt một thứ tự khóa thống nhất**, tránh giữ lock khi chờ công việc có thể cần chính lock đó, và giảm số lượng monitor phải giữ đồng thời.

### 10.1. Ví dụ chuyển tiền với thứ tự khóa ổn định

Giả sử ID tài khoản **duy nhất và không thay đổi** trong hệ thống, có thể dùng ID để quyết định thứ tự khóa:

~~~java
import java.util.Objects;

public final class Account {
    private final long id;
    private final Object lock = new Object();
    private long balance;

    public Account(long id, long openingBalance) {
        if (id <= 0 || openingBalance < 0) {
            throw new IllegalArgumentException("Invalid account");
        }
        this.id = id;
        this.balance = openingBalance;
    }

    public long balance() {
        synchronized (lock) {
            return balance;
        }
    }

    public static void transfer(
            Account from, Account to, long amount) {

        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");

        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (from == to) {
            return;
        }
        if (from.id == to.id) {
            throw new IllegalArgumentException(
                    "Account IDs must be unique");
        }

        Account first = from.id < to.id ? from : to;
        Account second = from.id < to.id ? to : from;

        synchronized (first.lock) {
            synchronized (second.lock) {
                if (from.balance < amount) {
                    throw new IllegalArgumentException(
                            "Insufficient balance");
                }

                // Tính trước; không cập nhật nửa chừng nếu overflow.
                long credited = Math.addExact(to.balance, amount);
                from.balance -= amount;
                to.balance = credited;
            }
        }
    }
}
~~~

Ví dụ:

~~~java
Account a = new Account(1L, 1_000L);
Account b = new Account(2L, 500L);

Account.transfer(a, b, 200L);

System.out.println(a.balance()); // 800
System.out.println(b.balance()); // 700
~~~

**Các điều kiện để lập luận an toàn:**

- ID là duy nhất giữa các instance có thể tham gia cùng một giao dịch; đây là một **tiền điều kiện của mô hình**, không được constructor tự bảo đảm ở cấp toàn JVM.
- Mọi đường sửa `balance` phải tuân theo cùng private lock, không được có mutator âm thầm ghi ngoài lock.
- Mọi tác vụ cần khóa cả hai tài khoản phải dùng **cùng quy tắc thứ tự theo ID**; một phương thức khác khóa theo chiều ngược có thể đưa deadlock trở lại.
- Phép cộng vào đích được kiểm tra **trước** khi thay đổi cả hai field. Nếu tràn, giao dịch trong bộ nhớ không bị cập nhật một nửa.
- Đây là **atomicity trong bộ nhớ của một JVM**, không thay thế transaction database, durability, kiểm toán hoặc phối hợp giữa nhiều process.

Nếu ứng dụng không có ID duy nhất và ổn định, phải chọn một chiến lược khóa khác (ví dụ thứ tự được quản lý bởi tầng sở hữu object hoặc một transaction lock dùng chung). Không dùng `System.identityHashCode` như khóa sắp xếp duy nhất rồi giả định nó không thể trùng.

### 10.2. Không gọi bên thứ ba khi giữ nhiều khóa

~~~java
// Rủi ro:
// synchronized (accountLock) {
//     paymentGateway.charge(...); // network có thể chậm, timeout hoặc gọi ngược
// }
~~~

Gọi dịch vụ ngoài trong khi giữ monitor khiến thời gian khóa không dự đoán được và làm tăng rủi ro deadlock nếu có callback. Nhưng cũng không được tùy tiện **đưa kiểm tra/cập nhật invariant ra ngoài lock** chỉ để giảm thời gian chờ. Cần thiết kế lại giao dịch, snapshot, idempotency hoặc cơ chế đặt giữ chỗ phù hợp.

## 11. Exception không rollback trạng thái đã cập nhật

Khóa được tự động nhả khi synchronized block ném exception; tuy nhiên Java **không tự khôi phục các field đã bị thay đổi**.

Sai về tính nhất quán:

~~~java
// Mã không an toàn nếu bước tiếp theo có thể thất bại:
// synchronized (lock) {
//     sourceBalance -= amount;
//     targetBalance = Math.addExact(targetBalance, amount);
// }
~~~

Nếu `Math.addExact` ném exception sau khi đã trừ nguồn, invariant của thao tác chuyển tiền bị phá.

Cách tốt hơn là tính các giá trị mới trước khi commit:

~~~java
synchronized (lock) {
    if (sourceBalance < amount) {
        throw new IllegalArgumentException("Insufficient balance");
    }

    long newTarget = Math.addExact(targetBalance, amount);
    long newSource = sourceBalance - amount;

    sourceBalance = newSource;
    targetBalance = newTarget;
}
~~~

Ví dụ này giả định `lock`, `sourceBalance`, `targetBalance` và `amount` là các biến được định nghĩa trong một lớp điều khiển **cả hai** số dư.

Nếu có nhiều thao tác có thể ném exception sau khi thay đổi state, cần thiết kế cơ chế rollback hoặc bảo đảm mọi bước có khả năng thất bại được thực hiện trước commit. **Mutual exclusion không có nghĩa transaction có rollback.**

## 12. Interruption, BLOCKED và các lựa chọn lock nâng cao

Một thread có thể bị chặn trong lúc chờ lấy monitor của `synchronized`. Việc chờ **lấy intrinsic monitor** không có API timeout và không thể bị hủy ngay chỉ bằng interruption theo cách `Lock.lockInterruptibly()` làm được.

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Bảo vệ state đơn giản với critical section ngắn | `synchronized` |
| Cần thử lấy lock mà không chờ mãi | `ReentrantLock.tryLock()` |
| Cần chờ lock với timeout | `ReentrantLock.tryLock(timeout, unit)` |
| Cần chờ lock và phản hồi interruption | `ReentrantLock.lockInterruptibly()` |
| Nhiều điều kiện chờ riêng trên một lock | `Condition` của `ReentrantLock` |
| Đọc nhiều, ghi ít và workload phù hợp | `ReadWriteLock` hoặc các cấu trúc concurrent phù hợp |
| Các task chờ một tín hiệu hoàn thành | `CountDownLatch` |
| Hàng đợi producer/consumer | `BlockingQueue` |
| Chia sẻ map concurrent | `ConcurrentHashMap` |

Ví dụ khi chọn `ReentrantLock`:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class TimedResource {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    public boolean tryIncrement() {
        if (!lock.tryLock()) {
            return false;
        }
        try {
            value++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Khác với intrinsic monitor, khi dùng `Lock` phải **đảm bảo gọi unlock trong finally** sau khi đã lấy khóa thành công. Không gọi `unlock()` khi thực tế chưa sở hữu lock.

`ReentrantLock` không phải “bản thay thế luôn tốt hơn” của `synchronized`. Hãy dùng nó khi cần timeout, interruptible acquisition, nhiều condition hoặc điều khiển lock cụ thể; với critical section nhỏ, `synchronized` thường rõ ràng và đủ an toàn.

### 12.1. Chờ bằng wait có thể bị interrupt

Khi thread đang thực hiện `Object.wait()`, interruption có thể khiến nó ném `InterruptedException`. Thread phải lấy lại monitor theo ngữ nghĩa wait trước khi exception được trả về.

Nếu method khai báo `throws InterruptedException`, thường nên **truyền exception lên**. Nếu không thể truyền và đang dừng tác vụ:

~~~java
try {
    doInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

`doInterruptibleWork()` là một method đại diện cho tác vụ có thể bị interrupt. Khôi phục interrupt flag giúp caller/tầng điều phối nhận biết yêu cầu hủy. Không catch rồi bỏ qua `InterruptedException` và tiếp tục chờ vô hạn nếu đó không phải contract đã định nghĩa.

### 12.2. notify không đảm bảo thread được chọn hay được chạy ngay

`notify()` có thể chọn một thread trong wait set nhưng không cam kết thread nào. `notifyAll()` khiến nhiều thread đủ điều kiện tỉnh dậy, nhưng họ vẫn phải cạnh tranh monitor và kiểm tra lại điều kiện.

Nếu ứng dụng cần fairness, timeout, scheduling hoặc nhiều hàng chờ độc lập, hãy dùng concurrency utilities có hợp đồng phù hợp thay vì tự phụ thuộc vào thứ tự notify của JVM.

## 13. Virtual threads và synchronized trong Java 27

**Điểm cập nhật quan trọng:** tài liệu JDK 21–23 từng cảnh báo virtual thread có thể bị **pin vào carrier thread** khi thực hiện blocking operation bên trong `synchronized`. Từ **JDK 24**, JEP 491 (*Synchronize Virtual Threads without Pinning*) đã thay đổi triển khai monitor để virtual thread có thể block/unmount thích hợp ngay cả khi đang giữ synchronized monitor. Java 27 kế thừa thay đổi này.

Vì thế, với Java 27 **không nên mặc định khuyên chuyển mọi synchronized block sang ReentrantLock chỉ vì pinning virtual threads**. Khuyến nghị cũ đó không còn áp dụng nguyên trạng.

Tuy nhiên:

- `synchronized` vẫn là cơ chế **mutual exclusion**, có contention và khả năng deadlock.
- Một lock giữ quá lâu vẫn làm các **thread khác phải chờ**; JEP 491 không thay đổi sự thật này.
- Virtual thread vẫn có các trường hợp pinning khác, ví dụ blocking ở native/foreign-function frames.
- Việc thực hiện I/O lớn trong critical section vẫn có thể làm giảm concurrency do lock giữ lâu, dù không còn pinning vì chính `synchronized`.
- Virtual threads không biến mutable state thành thread-safe và không làm `value++` thành atomic.

Ví dụ cập nhật bộ đếm từ nhiều virtual threads vẫn cần synchronization:

~~~java
SafeCounter counter = new SafeCounter();

try (var executor =
             java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 1_000; i++) {
        executor.submit(counter::increment);
    }
}
// ExecutorService.close() chờ các task đã gửi hoàn tất.
System.out.println(counter.get()); // 1000 nếu mọi task chạy thành công
~~~

Ví dụ trên minh họa ý tưởng, nhưng khi cần xác nhận task không lỗi, hãy giữ `Future` và gọi `get()` (ví dụ hoàn chỉnh ở phần kiểm thử). `ExecutorService.close()` đợi task kết thúc; nó không có nghĩa kết quả của mọi task tự được báo về main thread.

## 14. Kiểm thử concurrency: không chỉ chạy một lần thấy đúng

Race condition phụ thuộc lịch thực thi nên có thể không xuất hiện trong một lần chạy. Test nên tạo nhiều tác vụ và **chờ tất cả hoàn tất** trước khi kiểm tra kết quả.

### 14.1. Ví dụ test chạy nhiều task trên virtual threads

Đoạn dưới dùng `SafeCounter` ở phần 2:

~~~java
import java.util.ArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class CounterCheck {
    public static void main(String[] args) throws Exception {
        SafeCounter counter = new SafeCounter();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = new ArrayList<Future<?>>();

            for (int i = 0; i < 10_000; i++) {
                futures.add(executor.submit(counter::increment));
            }
            for (Future<?> task : futures) {
                task.get(); // xác nhận task kết thúc, truyền lỗi qua Future
            }
        }

        if (counter.get() != 10_000) {
            throw new AssertionError("Lost increment: " + counter.get());
        }

        System.out.println("PASS: " + counter.get());
    }
}
~~~

Mẫu này bảo đảm chỉ kiểm tra sau khi các task hoàn tất. Nó không phải bằng chứng toán học rằng code luôn đúng; việc chạy test nhiều lần, test stress và review lock discipline vẫn cần thiết.

### 14.2. Kiểm thử invariant nhiều field

Với `Inventory`:

- Chạy nhiều task `reserve()` cùng lúc với tồn kho hữu hạn.
- Đếm số lần trả `true` và xác nhận tổng số phần tử đã reserve không vượt `total`.
- Gọi `snapshot()` đồng thời và kiểm tra `0 <= reserved <= total` ở mỗi snapshot.
- Thử các đầu vào âm, 0, số lượng vượt tồn kho và tình huống `restock()` tràn `int`.
- Thử nhiều luồng gọi `reserve()`/`release()` theo nghiệp vụ được xác định rõ; không đưa `release()` không hợp lệ rồi đánh giá exception là data race.

Một test có thể dùng `CountDownLatch` để khởi động đồng loạt hoặc `ExecutorService` để chạy nhiều task. Khi task ném exception, phải lấy kết quả qua `Future.get()` hoặc cấu trúc kiểm tra tương đương, không bỏ qua lỗi trong background task.

### 14.3. Debug bằng thread dump và JFR

Khi nghi deadlock hoặc contention:

- Chụp **thread dump** bằng công cụ JDK phù hợp (ví dụ `jcmd <pid> Thread.print`) để xem thread đang `BLOCKED` và monitor đang bị giữ.
- Dùng **Java Flight Recorder (JFR)** khi cần phân tích contention, thời gian block hoặc workload production.
- Kiểm tra lock-order cycle và thời gian trong critical section; không chỉ đo số thread.
- Tránh log quá nhiều trong critical section vì logging cũng có thể làm thay đổi timing hoặc gây blocking.

Khi đánh giá lỗi intermittent, ưu tiên thu thập stack trace, thread state và tình trạng lock cụ thể. **Không** coi việc “thêm sleep cho test dễ fail hơn” là cách sửa lỗi đồng thời.

## 15. Những điều synchronized không tự giải quyết

`synchronized` có hợp đồng mạnh nhưng vẫn có giới hạn:

| Vấn đề | Synchronized có tự giải quyết không? | Cách xử lý phù hợp |
| --- | --- | --- |
| Lost update trên field chia sẻ | Có, nếu mọi cập nhật cùng dùng monitor | Giữ check+update trong một critical section |
| Visibility giữa các thread | Có qua happens-before của cùng monitor | Đọc/ghi theo cùng lock discipline |
| Invariant giữa nhiều field | Có thể, nếu khóa bao trọn giao dịch trên state | Snapshot, state ownership và API nguyên tử |
| Overflow/underflow số học | Không | Kiểm tra miền, `Math.*Exact` khi thích hợp |
| Rollback khi exception giữa nhiều bước | Không | Tính trước khi commit hoặc thiết kế transaction |
| Race xuyên process/JVM | Không | DB transaction, distributed coordination |
| Deadlock giữa nhiều monitor | Không | Lock ordering, giới hạn lock nesting |
| Fairness của thread chờ | Không cam kết | Dùng công cụ có hợp đồng fairness nếu thực sự cần |
| Timeout khi đợi lấy monitor | Không | `ReentrantLock.tryLock(timeout,...)` |
| Thread cancellation khi đợi monitor | Không như `lockInterruptibly()` | Chọn interruptible locking hoặc thiết kế task cancellation |
| I/O trong critical section | Không làm I/O nhanh hơn | Tách chỗ xử lý chậm, tránh giữ lock lâu |
| Immutability của object được tham chiếu | Không | Defensive copy hoặc immutable data |
| An toàn khi callback bên ngoài dùng lại state | Không tự bảo đảm | Không gọi untrusted callbacks dưới lock |

## 16. Publication, encapsulation và bảo vệ object graph

Ngay cả khi field là `private`, object còn có thể lộ trạng thái qua getter:

~~~java
public final class UnsafeRegistry {
    private final Object lock = new Object();
    private final java.util.List<String> names =
            new java.util.ArrayList<>();

    public java.util.List<String> names() {
        synchronized (lock) {
            return names; // NGUY HIỂM: lộ list mutable nội bộ
        }
    }
}
~~~

Caller có thể gọi `registry.names().add("X")` **bên ngoài lock**. Khi đó bất kỳ invariant hoặc cấu trúc collection nào được monitor bảo vệ đều có thể bị thay đổi mà không đồng bộ.

Cách sửa:

~~~java
public java.util.List<String> snapshotNames() {
    synchronized (lock) {
        return java.util.List.copyOf(names);
    }
}
~~~

`List.copyOf` tạo danh sách không cho sửa, tách cấu trúc khỏi list nguồn. Vì `String` immutable, đây là một snapshot phù hợp. Với phần tử mutable, snapshot collection chỉ **shallow copy**, cần cân nhắc sao chép sâu hoặc dùng immutable value object.

### 16.1. Không để this thoát khỏi constructor

Không đăng ký `this` vào nơi thread khác có thể gọi trước khi constructor hoàn thành. Ví dụ không nên:

~~~java
// Anti-pattern trong constructor:
// SomeGlobalRegistry.register(this);
// workerThread.start();
~~~

Khi `this` thoát ra quá sớm, thread khác có thể quan sát object chưa được khởi tạo đầy đủ. Đặt trạng thái cuối cùng một cách rõ ràng trong constructor, sau đó công bố object theo cơ chế an toàn. `final` fields có ngữ nghĩa bộ nhớ đặc biệt khi object được khởi tạo đúng cách; nhưng **final reference không làm object con mutable thành immutable**.

### 16.2. Thread confinement và immutable state là cách giảm nhu cầu khóa

Một phương án tốt hơn việc thêm lock khắp nơi là **tránh chia sẻ mutable state** khi không cần:

- Dữ liệu request chỉ thuộc một task/thread có thể được xử lý không cần khóa.
- Truyền các immutable records hoặc snapshots giữa tasks.
- Dùng message passing/queue để một owner độc quyền cập nhật state.
- Dùng `ConcurrentHashMap`, `BlockingQueue` hoặc nguyên thủy concurrent khác khi hợp đồng phù hợp.

Đây là hướng thiết kế bổ sung, không phủ nhận giá trị của `synchronized`. Nếu object thật sự có shared invariant, một monitor private được dùng nhất quán vẫn là lựa chọn rõ ràng.

## 17. Sai lầm phổ biến khi dùng synchronized

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ synchronize getter hoặc chỉ setter | Có thể còn data race/inconsistent view | Tất cả đường đọc/ghi của shared state dùng lock discipline thống nhất |
| Dùng hai lock khác nhau cho cùng invariant | Check và update bị chen ngang | Khóa toàn bộ invariant bằng cùng monitor |
| Nghĩ `volatile count++` atomic | Lost update | `synchronized` hoặc `AtomicInteger.incrementAndGet` |
| Dùng `static synchronized` để bảo vệ instance state tùy ý | Lock không trùng instance lock, sai mô hình | Chọn đúng monitor theo phạm vi state |
| Khóa trên String literal/boxed Integer | Có thể chia sẻ monitor ngoài ý muốn | Private final lock object |
| Trả thẳng mutable field từ getter | Caller sửa state ngoài monitor | Copy/snapshot/immutable representation |
| Chỉ khóa một method, nhưng ghép nhiều method rồi coi là transaction | Snapshot có thể lệch nhau | Một method thao tác toàn bộ dưới cùng lock |
| Giữ lock khi gọi network/DB hoặc chờ task | Contention, deadlock, latency | Thu gọn critical section và thiết kế transaction |
| Đổi thứ tự khóa giữa hai code paths | Deadlock | Quy tắc lock ordering ổn định |
| Nghĩ exception tự rollback giá trị đã ghi | Invariant bị phá nửa chừng | Tính trước rồi commit, hoặc rollback rõ ràng |
| Dùng `wait()` không trong synchronized | `IllegalMonitorStateException` | Sở hữu đúng monitor trước khi wait |
| Dùng `if` thay vì `while` khi wait condition | Spurious wakeup/điều kiện thay đổi | Kiểm tra trong while |
| Nghĩ `notify()` tự nhả lock | Thread được báo vẫn không chạy được ngay | Nhả lock khi rời synchronized |
| Dùng `sleep` để “chờ nhả lock” | Sleep không nhả monitor | Điều kiện chờ/BlockingQueue thích hợp |
| Cho rằng Java 27 synchronized luôn pin virtual threads | Khuyến nghị lỗi thời | Tham chiếu JEP 491; vẫn đánh giá contention |
| Thử nghiệm chạy đúng một lần rồi kết luận thread-safe | Race có thể không xuất hiện trong test | Stress test + review happens-before/invariant |

## 18. Checklist khi thiết kế và review shared state

- [ ] Đã xác định chính xác những field nào tạo thành shared invariant.
- [ ] Đã biết những thread nào có thể đọc và sửa shared state.
- [ ] Mỗi invariant có một chiến lược khóa hoặc concurrency primitive rõ ràng.
- [ ] Cả đọc và ghi thuộc contract đều dùng monitor phù hợp.
- [ ] Check và update không bị tách thành hai lần giữ khóa nếu chúng cần atomicity.
- [ ] Snapshot gồm nhiều field được tạo dưới cùng một lần giữ lock.
- [ ] Lock object là `private final` khi cần che giấu cơ chế đồng bộ.
- [ ] Không khóa trên String literal, boxed value, object do caller sở hữu mà không có lý do.
- [ ] Không để lộ mutable collection/array nội bộ qua getter.
- [ ] Tránh gọi callback, I/O và chờ task bên ngoài trong critical section nếu có thể.
- [ ] Khi giữ nhiều lock, mọi code path dùng cùng quy tắc thứ tự.
- [ ] Đã kiểm tra trường hợp exception có thể xảy ra giữa nhiều bước update.
- [ ] Đã phân biệt synchronized với volatile, atomic và ReentrantLock.
- [ ] Dùng while với `wait()` và xử lý interruption đúng contract.
- [ ] Không suy diễn fairness hoặc interruptible acquisition từ intrinsic monitor.
- [ ] Đã cập nhật kiến thức virtual threads theo JDK 24+/JEP 491.
- [ ] Đã xét dữ liệu được quản lý ngoài JVM (database, distributed state), không chỉ local lock.
- [ ] Test đủ contention, nhánh lỗi, overflow và các snapshot đồng thời.
- [ ] Có thể lý giải tính đúng bằng lock identity, mutual exclusion và happens-before.

## 19. Tài liệu chính thức

- [JLS Java SE 27 — §17.1 Synchronization](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.1) — monitor, lock/unlock, reentrancy, synchronized method/block.
- [JLS Java SE 27 — §17.2 Wait Sets and Notification](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.2) — wait, notify, notifyAll, spurious wakeups và interruption.
- [JLS Java SE 27 — §17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.4) — data races, synchronization order và happens-before.
- [JLS Java SE 27 — §14.19 synchronized statement](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.19) — ngữ nghĩa vào/ra synchronized block.
- [JLS Java SE 27 — §8.4.3.6 synchronized methods](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.4.3.6) — instance monitor và Class monitor.
- [Java SE 27 API — Object](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html) — wait/notify, monitor ownership.
- [Java SE 27 API — Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html) — thread lifecycle, interruption, virtual threads.
- [Java SE 27 API — java.util.concurrent](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/package-summary.html) — memory-consistency properties và concurrency utilities.
- [Java SE 27 API — ReentrantLock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html) — lockInterruptibly, tryLock và các chính sách khóa.
- [Java SE 27 API — BlockingQueue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/BlockingQueue.html) — producer/consumer coordination.
- [Java SE 27 API — AtomicInteger](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html) — atomic update của một biến.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — thay đổi cơ chế monitor từ JDK 24.
- [Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — mô hình virtual threads, carrier scheduling và pinning còn lại.

**Kết luận:** `synchronized` bảo vệ shared invariant khi các luồng dùng **đúng cùng một monitor** cho toàn bộ bước kiểm tra, đọc và cập nhật. Bên cạnh mutual exclusion, Java Memory Model bảo đảm memory visibility qua *happens-before* của unlock/lock. Chọn lock identity rõ ràng, giữ critical section đúng phạm vi, không để lộ mutable state và kiểm soát thứ tự đa khóa là nền tảng để thiết kế ứng dụng đồng thời chính xác trên Java 27.
