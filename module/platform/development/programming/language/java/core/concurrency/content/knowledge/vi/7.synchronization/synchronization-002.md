# synchronized method so với synchronized block trong Java

## 1. Mục tiêu và phạm vi

Hai đoạn mã dưới đây có thể dùng **cùng một monitor lock** nhưng cung cấp mức kiểm soát khác nhau:

~~~java
public synchronized void increment() {
    count++;
}

public void increment() {
    synchronized (this) {
        count++;
    }
}
~~~

Khi cả hai là **instance method** và đối tượng `this` giống nhau, phần thân được bảo vệ bởi cùng monitor. Bản `synchronized method` khóa monitor của đối tượng nhận lời gọi cho **toàn bộ thân phương thức**; `synchronized block` cho phép chọn một đối tượng monitor và thu hẹp vùng mã được bảo vệ. Nếu thay `this` bằng một lock object khác, chúng không còn đương nhiên dùng chung monitor.

Sau bài học, bạn sẽ:
- Mô tả chính xác cú pháp, đối tượng khóa, phạm vi và ý nghĩa của `synchronized` trên instance method, static method và code block.
- Giải thích mutual exclusion, reentrancy, visibility và quy tắc happens-before khi mở/đóng cùng monitor.
- Phân tích sự khác nhau giữa khóa cả method và chỉ khóa một critical section; chọn lock granularity mà vẫn bảo vệ trọn bất biến.
- Nhận ra bẫy đồng bộ từng getter/setter nhưng bỏ hở chuỗi check–then–act hoặc read–modify–write.
- Sử dụng `private final Object lock`, xác định tác dụng của `synchronized(this)` và `synchronized(MyClass.class)`, và tránh khóa nhầm đối tượng.
- Chạy các ví dụ Java 17+ với kết quả ổn định, biết khi nào cần dùng `Lock` hoặc công cụ concurrent khác.

Bài học chỉ đề cập **Java SE và JVM concurrency**, không phụ thuộc framework.

## 2. `synchronized` thực sự bảo vệ điều gì?

Mỗi object trong Java có một **intrinsic lock**, còn gọi là **monitor**. Khi một thread thực thi đoạn `synchronized` liên quan đến object đó, thread phải sở hữu monitor trước khi vào critical section. Nếu thread khác đang giữ cùng monitor, thread đến sau phải chờ cho tới khi có thể lấy khóa.

~~~text
             Monitor của đối tượng sharedCounter
                           │
Thread A ─── lock(sharedCounter) ──▶ critical section ──▶ unlock
                           │                  │
Thread B ─────── phải chờ ─┴──────────────────┘
                                            └─▶ lock rồi mới được vào
~~~

**Mutual exclusion chỉ áp dụng cho các đoạn đồng bộ trên đúng cùng monitor.** Không phải mọi mã truy cập một object đều tự bị khóa. Một method thường khác vẫn có thể chạy trong lúc thread giữ monitor nếu method đó không cố acquire monitor ấy.

Ví dụ:

~~~java
class Counter {
    private int count;

    synchronized void increment() { // dùng monitor của this
        count++;
    }

    int readUnsafe() {               // KHÔNG acquire monitor
        return count;
    }
}
~~~

Hai thread gọi `increment()` và `readUnsafe()` đồng thời **không được bảo đảm** readUnsafe quan sát nhất quán theo hợp đồng đồng bộ của increment. Field private không tự biến đường đọc thành an toàn. Nếu nhiều thread cần đọc/ghi giá trị đang thay đổi, tất cả đường truy cập phải tuân thủ cùng một giao thức: ví dụ `synchronized int get()` với cùng monitor, hoặc thiết kế dùng atomic API.

Synchronized còn quan trọng với **Java Memory Model (JMM)**:
- **Unlock** trên monitor `m` synchronizes-with mọi **lock tiếp theo** trên chính monitor `m` theo synchronization order.
- Từ quan hệ đó và program order, những ghi được bảo vệ trước unlock có thể được quan sát đúng bởi một đoạn mã acquire cùng lock sau đó.
- Mối quan hệ bảo đảm visibility/ordering theo happens-before; không cần giải thích bằng giả định “mọi giá trị luôn nằm trực tiếp trong RAM”.

`synchronized` không làm hệ điều hành chạy các thread theo thứ tự cụ thể, không cấp fairness mặc định, không tạo timeout, và không bảo đảm tác vụ sẽ hoàn thành trong thời gian cố định.

## 3. synchronized instance method: khóa toàn bộ thân method

Cú pháp:

~~~java
class Balance {
    private int cents;

    public synchronized void add(int amount) {
        cents += amount;
    }

    public synchronized int getCents() {
        return cents;
    }
}
~~~

Khi gọi `balance.add(100)`, thread phải lấy **monitor của chính instance `balance`** trước khi thực hiện phần thân. Về mặt lock và phạm vi critical section, ý nghĩa tương đương:

~~~java
public void add(int amount) {
    synchronized (this) {
        cents += amount;
    }
}
~~~

Mọi đường cập nhật và đọc đang bảo vệ field `cents` đều dùng monitor của cùng instance. Nhiều thread gọi `add` hoặc `getCents` trên một object sẽ không cùng ở trong các critical sections này.

### Các đặc điểm

- Method modifier `synchronized` chỉ khai báo trên **method**: quyền khóa gắn với toàn bộ thực thi thân phương thức, không chọn lọc từng dòng.
- Với instance method, lock object là `this` của receiver trong lời gọi. Cùng class nhưng **khác instance** thì monitor khác nhau.
- Một method được đồng bộ không tự biến **mọi method khác** của class thành synchronized.
- Thực thi đi vào method phải acquire lock trước khi chạy phần thân; thoát method bình thường hoặc do ngoại lệ đều nhả monitor.
- `synchronized` không phải một phần của chữ ký method để phân biệt overload; khi override, method override **không bắt buộc kế thừa** modifier synchronized. Cần xem implementation thực sự được gọi.
- Synchronized instance method không phải khóa toàn class: nó không ngăn method của instance khác hoặc static method mặc định chạy song song.

### Hai instance, hai monitor

~~~java
Counter first = new Counter();
Counter second = new Counter();

// Một thread có thể khóa first trong khi thread khác khóa second.
~~~

Nếu invariant nằm trong từng instance riêng, đó có thể là điều mong muốn. Nếu cả hai instance thực ra sửa cùng một **static mutable field**, khóa monitor của từng instance là không đủ để bảo vệ static field. Khi đó cần một shared lock/atomic protocol có phạm vi đúng với shared state.

## 4. synchronized block: chọn monitor và giới hạn vùng khóa

Cú pháp:

~~~java
synchronized (lockExpression) {
    // các hành động được bảo vệ bằng monitor lockExpression
}
~~~

`lockExpression` phải có kiểu tham chiếu; biểu thức được đánh giá để lấy **một object monitor** trước khi vào block. Nếu kết quả là `null`, runtime ném `NullPointerException`; không có monitor nào để acquire. Block có thể xuất hiện trong method, constructor, static initializer hoặc một block mã hợp lệ khác.

Ví dụ:

~~~java
class Inventory {
    private final Object quantityLock = new Object();
    private int quantity;

    void add(int delta) {
        if (delta <= 0) {
            throw new IllegalArgumentException("delta must be positive");
        }

        synchronized (quantityLock) {
            quantity += delta;
        }
    }

    int current() {
        synchronized (quantityLock) {
            return quantity;
        }
    }
}
~~~

Đoạn code này bảo vệ field `quantity` bằng `private final Object quantityLock`. Phần kiểm tra tham số `delta <= 0` không phụ thuộc mutable state chung nên có thể làm **trước khi acquire lock**; vùng critical section chỉ bao lấy thay đổi quantity.

Điểm khác biệt lớn nhất với synchronized method là khả năng **chọn monitor khác `this`**. Nếu hai thread gọi `add()` trên cùng Inventory, chúng tranh quantityLock. Nếu code ngoài thực hiện `synchronized(inventory)`, nó **không** khóa quantityLock, nên không trực tiếp chặn `add()`.

### Tại sao thường ưu tiên private final lock?

- **private:** code gọi bên ngoài không biết hoặc không thể vô tình acquire cùng monitor và giữ quá lâu.
- **final:** tất cả lời gọi dùng cùng đối tượng khóa đã xác định; không bị thay lock reference giữa các lời gọi.
- **Object mới dành riêng cho mục đích khóa:** không gắn lock với String literal, Integer cached object, Class object dùng chung hoặc tham số mutable có thể bị caller cũng khóa.

`private final` không biến tất cả state thành thread-safe; nó chỉ giúp **giữ ổn định danh tính monitor**. Mọi method đọc/ghi cùng invariant vẫn phải tuân thủ cùng lock hoặc một protocol tương thích.

### Khi nào lock nguyên method sẽ quá rộng?

~~~java
class ReportService {
    private final Object stateLock = new Object();
    private int completed;

    void process(String input) {
        String formatted = input.strip().toUpperCase(java.util.Locale.ROOT);
        // Tính toán không đụng mutable state chung: không cần giữ lock.

        synchronized (stateLock) {
            completed++;
        }

        System.out.println(formatted);
        // In ra console có side effect riêng, không cần giữ stateLock.
    }

    int completed() {
        synchronized (stateLock) {
            return completed;
        }
    }
}
~~~

Ở đây chỉ thao tác tăng/đọc `completed` cần cùng lock. Nếu đổi `process` thành `synchronized void process(...)` trên `this`, mà các đường cập nhật khác vẫn dùng `stateLock`, sẽ tạo ra **hai giao thức khóa khác nhau** và có thể không bảo vệ đúng invariant. Khi refactor, không chỉ đổi cú pháp: phải kiểm tra mọi đường truy cập state.

Đừng giữ lock qua I/O, sleep, callback hoặc công việc dài **khi không cần**: thời gian giữ monitor lâu làm các thread khác chờ. Tuy nhiên, cũng đừng đưa **một nửa của invariant** ra ngoài lock chỉ để tối ưu. An toàn và tính nguyên tử của thao tác nghiệp vụ là điều kiện trước tiên.

## 5. Bảng so sánh trực tiếp

| Tiêu chí | synchronized instance method | synchronized block |
|---|---|---|
| Cú pháp | `synchronized void method() { ... }` | `synchronized (lock) { ... }` |
| Monitor mặc định | Receiver `this` | Chính object đánh giá từ biểu thức `lock` |
| Phạm vi bảo vệ | Toàn bộ thân method | Chỉ những lệnh trong block |
| Có chọn private lock riêng? | Không bằng modifier instance synchronized; muốn lock khác dùng block | Có, bằng `synchronized (privateLock)` |
| Nơi sử dụng | Method declaration | Trong thân method, constructor, initializer hoặc block hợp lệ |
| Dùng với static? | Có: static synchronized lấy `Class` monitor | Có: `synchronized (SomeClass.class)` hoặc shared lock khác |
| Khi exception thoát critical section | JVM nhả monitor | JVM nhả monitor |
| Tính reentrant | Có | Có |
| Visibility/happens-before | Theo monitor mà method acquire/release | Theo monitor mà block acquire/release |
| Hiệu năng | Phụ thuộc contention, work bên trong và JIT/JVM | Phụ thuộc contention, work bên trong, monitor và thời gian giữ |
| Dễ đọc | Ngắn khi toàn method là một critical section | Rõ biên giới khi chỉ một đoạn cần được bảo vệ |

Không kết luận `synchronized block` luôn nhanh hơn `synchronized method`. Nếu block khóa đúng `this` và ôm trọn toàn bộ method, ngữ nghĩa tương đương; HotSpot/JIT có nhiều tối ưu, hiệu năng thực tế phải đo trên workload. Ưu thế của block là **thiết kế phạm vi và identity của lock** rõ hơn, chứ không phải cú pháp tự sinh “khóa nhanh”.

## 6. static synchronized method sử dụng monitor nào?

Đối với:

~~~java
class GlobalCounter {
    private static int total;

    static synchronized void increment() {
        total++;
    }

    static synchronized int get() {
        return total;
    }
}
~~~

Lock được acquire là **Class object** tương ứng với `GlobalCounter.class` (đối tượng `java.lang.Class` đại diện cho class trong ngữ cảnh class loader liên quan). Về monitor và vùng khóa, có thể viết tương đương:

~~~java
static void increment() {
    synchronized (GlobalCounter.class) {
        total++;
    }
}
~~~

Điều này **khác** `synchronized(this)` trong instance method:

~~~text
new GlobalCounter()             ──▶ instance monitor X
new GlobalCounter()             ──▶ instance monitor Y
GlobalCounter.class             ──▶ class monitor Z

static synchronized method      ──▶ khóa Z
instance synchronized method    ──▶ khóa X hoặc Y (tùy receiver)
~~~

Vì vậy:
- Hai lời gọi static synchronized lên **cùng class monitor** sẽ loại trừ nhau.
- Static synchronized method và instance synchronized method trên một instance **không tự loại trừ nhau**.
- Nếu sửa cùng một static field từ instance method khóa `this` và static method khóa `Class`, vẫn có thể xảy ra race.
- Hai `Class` objects của “cùng tên class” do **hai class loaders khác nhau** định nghĩa không nhất thiết là cùng object; không dùng khóa class làm cơ chế đồng bộ tiến trình khác hoặc classloader khác.

Có thể dùng một `private static final Object LOCK = new Object();` và các block khóa LOCK thay vì khóa Class object, khi muốn tách hẳn khóa nghiệp vụ khỏi monitor mà code khác có thể dùng.

## 7. Ví dụ độc lập 1: cùng monitor, method/block đều đúng

Chương trình chạy với **Java 17+**, cho hai thread cùng tăng một counter instance: một thread dùng synchronized method, thread kia dùng synchronized(this) block. Cả hai dùng monitor của **cùng object**. Phần sau lặp lại đối với static synchronized method và synchronized(Class.class).

Lưu tệp **SynchronizedFormsDemo.java**:

~~~java
public class SynchronizedFormsDemo {
    static final class Counter {
        private int value;
        private static int global;

        synchronized void incrementMethod() {
            value++;
        }

        void incrementBlock() {
            synchronized (this) {
                value++;
            }
        }

        synchronized int value() {
            return value;
        }

        static synchronized void incrementStaticMethod() {
            global++;
        }

        static void incrementStaticBlock() {
            synchronized (Counter.class) {
                global++;
            }
        }

        static synchronized int global() {
            return global;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Thread first = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                counter.incrementMethod();
            }
        }, "method-worker");

        Thread second = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                counter.incrementBlock();
            }
        }, "block-worker");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("instance=" + counter.value());

        Thread third = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                Counter.incrementStaticMethod();
            }
        }, "static-method-worker");

        Thread fourth = new Thread(() -> {
            for (int i = 0; i < 100_000; i++) {
                Counter.incrementStaticBlock();
            }
        }, "static-block-worker");

        third.start();
        fourth.start();
        third.join();
        fourth.join();

        System.out.println("static=" + Counter.global());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SynchronizedFormsDemo.java
java SynchronizedFormsDemo
~~~

Stdout chính xác, nếu không có thread nào khác sửa Counter trong cùng chương trình:

~~~text
instance=200000
static=200000
~~~

**Giải thích:**
1. `first` và `second` cùng dùng instance `counter`. `incrementMethod()` acquire monitor của counter; `incrementBlock()` dùng `synchronized (this)` với `this == counter`.
2. Mỗi bước `value++` được bảo vệ toàn vẹn; các thread có thể xen kẽ theo **lần tăng**, nhưng không thể cùng thực hiện critical section trên counter.
3. `join()` chờ đủ 200.000 lần tăng trước khi main đọc kết quả. Method `value()` cũng đồng bộ trên monitor tương ứng.
4. `incrementStaticMethod()` và `incrementStaticBlock()` cùng khóa `Counter.class`; sau khi hai thread hoàn tất, `global()` đọc 200.000.
5. Việc **cả hai trường đều xuất hiện trong cùng class** không khiến instance lock và class lock giao nhau. Ví dụ dùng hai trường khác nhau, mỗi trường có một giao thức khóa nhất quán riêng.

Chương trình chứng minh **tính đúng của hai hình thức khóa**; nó không đo latency, contention hay mức overhead. Nếu cần benchmark, warm up JVM, đo nhiều lần và thay đổi độ lớn critical section, số thread, CPU quota và tải bên ngoài.

## 8. Synchronized getter + synchronized setter vẫn có thể làm mất cập nhật

Một lỗi thiết kế quan trọng là đặt `synchronized` cho từng method, rồi cho caller phối hợp chúng thành một thao tác nghiệp vụ:

~~~java
class SplitCounter {
    private int count;

    synchronized int get() { return count; }

    synchronized void set(int next) { count = next; }
}

// Caller A, B cùng chạy:
int old = counter.get();
counter.set(old + 1);
~~~

Mỗi method được bảo vệ **riêng lẻ**, nhưng monitor đã nhả khi `get()` trả về; thread khác có thể vào `get()` trước khi caller đầu tiên gọi `set()`. Hai thread đều đọc 0, rồi cùng ghi 1. Các method đều synchronized đúng cú pháp mà phép tăng tổng thể vẫn **không atomic**.

~~~text
A: lock → get()=0 → unlock
B: lock → get()=0 → unlock
A: lock → set(1) → unlock
B: lock → set(1) → unlock

Expected = 2, actual = 1
~~~

**Cách đúng** là di chuyển toàn bộ read–modify–write vào **một phương thức atomic**, hoặc giữ cùng monitor bao trọn cặp lời gọi nếu API thật sự yêu cầu:

~~~java
synchronized void increment() {
    count++;
}
~~~

Tương tự, một nghiệp vụ “nếu số lượng còn trên 0 thì giảm” phải khóa **toàn bộ check + decrement**. Khóa chỉ phần giảm vẫn cho hai thread cùng kết luận là có thể thực hiện tác vụ, tạo sai invariant nghiệp vụ.

### Ví dụ độc lập 2: dàn dựng lỗi và sửa cùng một lock

Lưu tệp **SplitCriticalSectionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class SplitCriticalSectionDemo {
    static final class Counter {
        private int count;

        synchronized int get() {
            return count;
        }

        synchronized void set(int next) {
            count = next;
        }

        void incrementAtomically() {
            synchronized (this) {
                count++;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter split = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable brokenIncrement = () -> {
            int snapshot = split.get();
            bothRead.countDown();
            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            split.set(snapshot + 1);
        };

        Thread a = new Thread(brokenIncrement, "split-a");
        Thread b = new Thread(brokenIncrement, "split-b");
        a.start();
        b.start();
        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("split=" + split.get());

        Counter safe = new Counter();
        Thread c = new Thread(safe::incrementAtomically, "atomic-c");
        Thread d = new Thread(safe::incrementAtomically, "atomic-d");
        c.start();
        d.start();
        c.join();
        d.join();

        System.out.println("atomic=" + safe.get());
    }
}
~~~

Lệnh:

~~~bash
javac SplitCriticalSectionDemo.java
java SplitCriticalSectionDemo
~~~

Stdout trong điều kiện chạy bình thường, không có interrupt ngoài:

~~~text
split=1
atomic=2
~~~

**Vì sao kết quả xác định?**
- `bothRead` buộc cả hai thread của phép tăng sai hoàn tất `split.get()` trước khi có thread nào đi tiếp để `set()`.
- Khi main mở `allowWrite`, cả hai `snapshot` là 0; cả hai gọi `set(1)` (dù có khóa từng setter) nên kết quả cuối là 1.
- Tất cả lời gọi `get()` và `set()` đều dùng chung monitor của split; **chính khoảng hở giữa hai method** khiến mất cập nhật, không phải thiếu khóa trong từng method.
- Ở nhánh safe, toàn bộ `count++` được thực hiện dưới `synchronized (this)` trên cùng Counter. Không có khoảng hở giữa read và write cho thread khác dùng cùng monitor.
- `join()` cho main đọc kết quả sau khi tất cả worker kết thúc; CountDownLatch ở nhánh đầu **dàn dựng lỗi**, không phải biện pháp sửa lỗi.

Nếu một bài toán yêu cầu nhiều field thay đổi nhất quán, đặt toàn bộ thao tác đó dưới một monitor chung hoặc sử dụng state bất biến với một atomic reference swap. Tách critical section quá mịn có thể làm hỏng invariant, dù mỗi field có getter/setter synchronized.

## 9. Monitor identity: cùng code không có nghĩa cùng lock

Xét hai method:

~~~java
class WrongLocks {
    private final Object firstLock = new Object();
    private final Object secondLock = new Object();
    private int value;

    void add() {
        synchronized (firstLock) {
            value++;
        }
    }

    int read() {
        synchronized (secondLock) {
            return value;
        }
    }
}
~~~

Đoạn code này dùng **hai monitor khác nhau** để truy cập một state chung. Mutual exclusion trên firstLock không ngăn read() dùng secondLock chạy trong lúc add() đang cập nhật; đồng thời, unlock firstLock **không tạo** quan hệ synchronizes-with cho lock secondLock. Nếu cần một protocol đọc/ghi nhất quán, cả hai method phải dùng **cùng monitor** hoặc cơ chế đồng bộ tương đương.

Đây là ví dụ ngược lại với việc dùng nhiều lock hợp lệ cho **hai vùng state độc lập**. Nếu hai trường thực sự có invariant độc lập, có thể có two locks, mỗi field được bảo vệ bởi đúng một lock. Nhưng nếu logic cần đọc/tính toán trên cả hai trường thành một snapshot, thiết kế nhiều lock phải xác định rõ cách acquire cùng lúc, thứ tự khóa và khả năng deadlock.

### Lỗi khóa trên object mới cho mỗi lời gọi

~~~java
void broken() {
    synchronized (new Object()) {
        count++;
    }
}
~~~

Đây chỉ là **đoạn trích** trong class có field count. Vì mỗi lần gọi tạo monitor riêng, các thread không dùng chung lock nên không bảo vệ count. Một số JVM có thể loại bỏ lock không tranh chấp này khi tối ưu, nhưng lỗi thiết kế tồn tại độc lập với tối ưu.

### Lỗi khóa trên mutable reference

~~~java
private Object lock = new Object();

void update() {
    synchronized (lock) {
        // ...
    }
}

void replaceLock() {
    lock = new Object();
}
~~~

Nếu lock có thể đổi sang object khác, các thread có thể đồng thời giữ **hai monitor khác nhau** và đều tin rằng đã độc quyền. Vì thế field dùng làm monitor nên ổn định, thường là `private final Object lock`; đừng thay thế lock khi vẫn có thread hoạt động.

### Lỗi dùng String literal hoặc boxed value làm monitor

~~~java
synchronized ("GLOBAL_LOCK") {
    // ...
}
~~~

Các chuỗi literal được intern; code khác không liên quan có thể vô tình khóa cùng String. Boxed values cũng có thể được cache/chia sẻ. Khóa trên object dễ bị alias từ nơi ngoài tạo coupling và nguy cơ contention/deadlock khó chẩn đoán. Ưu tiên object lock riêng, không trỏ ra ngoài.

### Bẫy khóa this làm API bị điều khiển từ ngoài

~~~java
final class Service {
    synchronized void runTask() {
        // ...
    }
}
~~~

Bên ngoài vẫn có thể thực hiện `synchronized(service) { ... }` và giữ cùng monitor, ngăn runTask() vào trong. Không có gì sai về mặt JMM, nhưng nó có thể làm giảm khả năng kiểm soát lock ownership. Với shared service có nhiều caller, một private lock thường giảm coupling hơn; chọn giữa method và block theo ngữ nghĩa public API.

## 10. Lock granularity: khóa rộng hay khóa hẹp?

**Lock granularity** là phạm vi trạng thái và đoạn mã bảo vệ bởi một monitor. Thiết kế cần cân bằng ba yếu tố:

1. **Correctness:** Toàn bộ invariant phải nguyên tử đối với những thao tác có thể cạnh tranh.
2. **Contention:** Giữ monitor quá lâu khiến thread khác chờ lâu, dù đoạn chờ không cần chia sẻ.
3. **Complexity:** Nhiều monitor làm khó kiểm soát lock order, coupling và deadlock.

Ví dụ một method thực hiện tính toán tốn thời gian nhưng chỉ tăng counter dùng chung:

~~~java
class TaskProcessor {
    private final Object counterLock = new Object();
    private long completed;

    void process(byte[] input) {
        long checksum = checksumLocally(input);

        synchronized (counterLock) {
            completed++;
        }

        publishResult(checksum);
    }

    long completed() {
        synchronized (counterLock) {
            return completed;
        }
    }

    private long checksumLocally(byte[] bytes) {
        long sum = 0;
        for (byte b : bytes) sum += b & 0xff;
        return sum;
    }

    private void publishResult(long checksum) {
        // Một side effect bên ngoài critical section,
        // có concurrency contract riêng của nơi nhận kết quả.
    }
}
~~~

Đây là class minh họa, không phải chương trình có main. `checksumLocally()` không sửa shared instance state và chạy ngoài lock. `publishResult()` giả định có giao thức hợp lệ riêng; nếu nghiệp vụ yêu cầu publish kết quả và tăng count là **một transaction**, thì tách chúng ra là không đủ, cần thiết kế atomicity ở đúng phạm vi nguồn dữ liệu.

**Không tùy tiện kéo đọc state ra ngoài lock:** Nếu checksum phụ thuộc mutable shared data mà thread khác có thể sửa, snapshot hoặc phép đọc đó cũng cần được bảo vệ. Chỉ chuyển ra ngoài các phép tính thật sự độc lập hoặc chạy trên immutable input.

### Nếu hai tài nguyên thật sự độc lập

~~~java
final class TwoCounters {
    private final Object leftLock = new Object();
    private final Object rightLock = new Object();
    private int left, right;

    void incrementLeft() {
        synchronized (leftLock) { left++; }
    }

    void incrementRight() {
        synchronized (rightLock) { right++; }
    }
}
~~~

Hai lời gọi có thể chạy đồng thời vì chúng dùng monitor khác nhau và chỉ sửa các trường độc lập. Nếu về sau thêm invariant như `left + right <= capacity`, phải **thiết kế lại** cơ chế khóa, không được dựa vào từng lock độc lập để bảo vệ phép kiểm tra tổng.

## 11. Reentrancy: cùng một thread có thể acquire lại monitor mình đang giữ

Java intrinsic monitors có tính **reentrant**. Khi một thread đã giữ monitor `this`, nó có thể gọi một method synchronized khác của cùng object (hoặc vào `synchronized(this)`) mà không tự deadlock.

~~~java
class ReentrantExample {
    private int count;

    synchronized void incrementTwice() {
        incrementOnce(); // cùng thread acquire lại monitor this
        incrementOnce();
    }

    synchronized void incrementOnce() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
~~~

Khi `incrementTwice()` gọi `incrementOnce()` hai lần, cùng thread có thể vào lại monitor. JVM theo dõi mức acquire/release tương ứng; monitor chỉ tự do cho thread khác khi thread sở hữu đã hoàn tất các mức khóa. Tính reentrant không cho phép **hai thread** đồng thời chiếm cùng monitor.

### Exception và return

Với synchronized method, JVM nhả monitor khi method thoát (dù `return` hay exception). Với synchronized block, việc thoát block cũng nhả monitor, kể cả khi ngoại lệ thoát khỏi block. Không phải viết `finally { unlock(); }` thủ công như khi dùng `ReentrantLock`.

Nhưng nếu một method sửa **một nửa** trạng thái rồi ném exception, monitor được nhả **không có nghĩa** trạng thái tự rollback. Chương trình cần thiết kế exception safety/invariant riêng nếu thao tác nhiều bước có thể thất bại giữa chừng.

## 12. Deadlock vẫn có thể xảy ra với synchronized

`synchronized` bảo đảm mutual exclusion theo monitor, nhưng không tự tránh deadlock khi nhiều monitor được acquire theo thứ tự trái ngược:

~~~text
Thread A: lock(L1) → chờ lock(L2)
Thread B: lock(L2) → chờ lock(L1)

Cả hai giữ một monitor và chờ monitor kia → có thể deadlock.
~~~

Với synchronized block lồng nhau, phải có **lock ordering policy** nhất quán, ví dụ mọi luồng cần cả hai khóa đều acquire L1 rồi L2. Một lựa chọn khác là gộp hai invariant vào một lock nếu phù hợp, tránh việc phải khóa đồng thời nhiều resource.

Đối với synchronized method, deadlock cũng xuất hiện nếu method trên object A khi đang giữ monitor A gọi method synchronized trên B, trong khi luồng khác giữ B rồi gọi ngược A. “Không thấy block lồng nhau” không đủ để kết luận không có deadlock; xem **call graph và lock order**.

### Không giữ monitor khi gọi code không kiểm soát nếu tránh được

Gọi callback, observer hoặc I/O ngoài trong khi giữ monitor có thể làm code gọi vào lại những lock khác, chờ lâu, hoặc block vô thời hạn. Nếu không cần nguyên tử qua callback, nên chụp dữ liệu cần thiết trong lock, thoát lock rồi mới gọi; nhưng bảo đảm snapshot phù hợp với invariant. Khi bắt buộc giữ lock vì correctness, cần kiểm soát lock graph và thời hạn thao tác.

## 13. wait/notify liên quan tới monitor nào?

`Object.wait()`, `notify()` và `notifyAll()` phối hợp bằng **monitor của chính object nhận lời gọi**. Thread phải giữ đúng monitor đó khi gọi, nếu không sẽ bị `IllegalMonitorStateException`.

Ví dụ:

~~~java
class Signal {
    private final Object monitor = new Object();
    private boolean ready;

    void markReady() {
        synchronized (monitor) {
            ready = true;
            monitor.notifyAll();
        }
    }

    void awaitReady() throws InterruptedException {
        synchronized (monitor) {
            while (!ready) {
                monitor.wait();
            }
        }
    }
}
~~~

Đây là class Java 17+ minh họa, không có main. Gọi `wait()` làm thread **tạm nhả monitor** của monitor và chờ; khi được đánh thức, thread phải acquire lại monitor trước khi tiếp tục. Dùng vòng `while` để kiểm tra lại điều kiện sau khi tỉnh dậy, vì có thể có spurious wakeup hoặc các luồng khác đã thay đổi trạng thái.

Nếu `markReady()` dùng `synchronized (monitor)` nhưng `awaitReady()` lại là synchronized instance method dùng monitor của `this`, đó sẽ là **hai monitor khác nhau**, phá vỡ giao thức phối hợp. Muốn dùng wait/notify an toàn, phải chọn đúng một monitor và điều kiện chung.

`Thread.sleep(...)` **không nhả monitor đang giữ**; không nhầm sleep với wait. Trong thiết kế mới, các công cụ mức cao như `CountDownLatch`, `BlockingQueue`, `Condition` hoặc `Future` thường rõ ràng và ít lỗi hơn nếu phù hợp nhu cầu.

## 14. Synchronized không bảo đảm mọi bất biến tự động

Giả sử biến `balance` được bảo vệ bằng synchronized. Điều sau đây chưa đủ nếu hai method đều đồng bộ nhưng caller thực hiện rời rạc:

~~~java
if (account.balance() >= amount) {  // synchronized getter
    account.withdraw(amount);        // synchronized update
}
~~~

Thread khác có thể rút tiền sau khi lần kiểm tra đầu tiên đã trả về, trước khi caller gọi withdraw. Cần một operation duy nhất kiểm tra và cập nhật:

~~~java
class Account {
    private long balance;

    synchronized boolean tryWithdraw(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        if (balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized long balance() {
        return balance;
    }
}
~~~

Đây là class minh họa làm việc với state trong một JVM, không thể thay thế transaction protocol cho tài nguyên ngoài hoặc nhiều process. Nó cho thấy **đơn vị atomic phải là thao tác nghiệp vụ**, không phải từng accessor. Cùng ý tưởng có thể viết:

~~~java
boolean tryWithdraw(long amount) {
    if (amount < 0) throw new IllegalArgumentException("negative amount");
    synchronized (accountLock) {
        if (balance < amount) return false;
        balance -= amount;
        return true;
    }
}
~~~

Ở phiên bản block, `accountLock` là private final lock của instance; cả các đường đọc/ghi balance khác cần dùng cùng lock để bảo đảm tính đúng.

## 15. Khi nào nên dùng synchronized method, synchronized block, Lock hoặc atomic class?

| Yêu cầu | Cách tiếp cận hợp lý | Lưu ý |
|---|---|---|
| Phần lớn thân instance method là critical section và public monitor hợp lý | `synchronized` instance method | Ngắn, dễ đọc, khóa `this` cho toàn body. |
| Chỉ một đoạn của method đụng shared mutable state | `synchronized(privateLock)` block | Giữ lock đúng phạm vi và bảo vệ đủ invariant. |
| Static state được quản lý toàn class | `static synchronized` hoặc block khóa shared static lock | Class monitor khác instance monitor. |
| Một counter nguyên tử đơn giản | `AtomicInteger.incrementAndGet()` / `AtomicLong` | Không cần lock để chỉ tăng một biến; chuỗi check-then-act vẫn cần CAS thích hợp. |
| Nhiều field cần bất biến tổng hợp | Method/block với cùng monitor hoặc `Lock` | Phải bảo vệ toàn bộ operation, kể cả kiểm tra điều kiện. |
| Cần timeout khi lấy khóa hoặc chờ lock interruptibly | `ReentrantLock.tryLock(timeout)` / `lockInterruptibly()` | Lấy/nhả lock thủ công, `unlock()` trong finally sau khi acquire thành công. |
| Nhiều reader, ít writer với cấu trúc phù hợp | `ReadWriteLock` hoặc `StampedLock` tùy thiết kế | Phức tạp hơn, phải đo hiệu quả và hiểu semantics. |
| Tránh hoàn toàn mutable shared state | Immutable data / local variables / thread confinement | Giảm yêu cầu đồng bộ, thường dễ kiểm chứng nhất. |

Không chọn một cơ chế chỉ vì nó “nhanh hơn”. Trước tiên đặt câu hỏi: **bất biến nào cần được bảo vệ, state đó được chia sẻ ở đâu, ai được quyền cập nhật, và khi nào phép đọc phải thấy kết quả?** Sau đó kiểm tra contention và hiệu năng trong workload thật.

### Lưu ý với virtual threads

Trong Java 21, một số thao tác blocking xảy ra khi virtual thread giữ monitor có thể làm carrier thread bị **pinning**, gây tác động đến khả năng mở rộng dưới workload chờ dài; hỗ trợ của JVM đã tiếp tục được cải tiến ở các bản JDK mới. Quy tắc mutex/happens-before của synchronized method và block về cơ bản vẫn là các quy tắc Java giống nhau. Không sử dụng “synchronized block thay vì method” như mẹo tự tránh pinning: **monitor đang giữ và loại thao tác blocking** mới là yếu tố cần xét. Phải đánh giá trên **JDK cụ thể** và không giữ monitor qua blocking dài khi không cần.

## 16. Những câu sai thường gặp trong phỏng vấn và code review

**“synchronized method khóa cả class.”** Sai nếu là **instance method**: nó khóa monitor của receiver. Chỉ `static synchronized` dùng class monitor; các instance có monitor riêng.

**“synchronized(this) khác synchronized instance method ngay cả khi bọc toàn method.”** Không đúng về lock identity và critical section: chúng đều dùng monitor `this`. Khác nhau về cú pháp/khả năng chọn scope, không phải mặc định về tính an toàn.

**“Tôi đã khóa getter và setter nên get rồi set là atomic.”** Sai. Mỗi method nhả monitor khi trả về; một thread khác có thể chen vào giữa hai lời gọi. Gộp read–modify–write hoặc check–then–act vào một critical section.

**“Hai synchronized blocks ở hai method luôn loại trừ nhau.”** Chỉ khi chúng acquire **cùng monitor object**. `lockA` và `lockB` là hai object khác nhau thì không.

**“Khóa nhiều hơn luôn an toàn hơn.”** Khóa nhiều có thể tăng contention hoặc deadlock và vẫn không cứu được protocol sai. Phải bảo vệ đúng **mọi đường truy cập** và đúng **đơn vị nghiệp vụ**.

**“Code bên ngoài một synchronized method sẽ bị ngăn truy cập object đó.”** Không. Chỉ những đoạn code có yêu cầu acquire cùng monitor mới chờ. Một method không synchronized có thể chạy đồng thời, kể cả lúc monitor đang được giữ.

**“Synchronized chỉ lo atomicity, không lo visibility.”** Sai. Unlock và lock tiếp theo trên cùng monitor có quan hệ synchronizes-with, tạo happens-before bảo đảm visibility/ordering theo JMM.

**“Synchronized block luôn nhanh hơn method.”** Không có bảo đảm. Khi chúng khóa cùng monitor và cùng phạm vi, logic đồng bộ tương tự. Khác biệt quan trọng là lựa chọn lock granularity và monitor.

**“Một method synchronized ném exception sẽ giữ khóa mãi.”** Sai. Monitor tự nhả khi thoát method/block, kể cả do exception. Tuy vậy, dữ liệu có thể ở trạng thái dở dang nếu operation không exception-safe.

**“Không có synchronized trong method này nên không thể deadlock.”** Sai. Method có thể gọi method khác đang acquire monitor, hoặc có lock lồng nhau trên call graph.

**“synchronized bảo đảm FIFO fairness.”** Không. JVM không hứa các thread đang tranh monitor sẽ giành khóa theo thứ tự yêu cầu; ứng dụng không được suy ra deadline hay starvation freedom từ modifier này.

## 17. Checklist áp dụng vào code thực tế

1. Liệt kê tất cả **mutable state** mà nhiều thread có thể cùng truy cập.
2. Định nghĩa invariant cần giữ: đơn trường, đa trường, check-then-act hay một sequence dài hơn.
3. Quyết định **một monitor identity nhất quán** cho mọi read/write liên quan.
4. Nếu toàn bộ thân method thật sự là một critical section và khóa receiver là hợp lý, dùng synchronized method.
5. Nếu chỉ một phần cần bảo vệ hoặc cần private lock, dùng synchronized block nhưng giữ **đủ** các bước liên quan.
6. Với static state, kiểm tra lock là class monitor hay một private static final lock; đừng nhầm với instance monitor.
7. Tránh lock mới mỗi lời gọi, lock mutable, String literal và object mà external code có thể giữ lâu.
8. Không gọi code có thể blocking dài hoặc callback trong lock nếu invariant không đòi hỏi.
9. Nếu có nhiều locks, ghi rõ lock ordering và chẩn đoán nguy cơ deadlock.
10. Đảm bảo phép đọc trạng thái được đồng bộ phù hợp; không dựa vào field private/final để bảo vệ mutable state.
11. Viết test đồng thời bằng CountDownLatch/Future/join để kiểm tra correctness. Không coi một stress test thành công là bằng chứng loại trừ mọi race.
12. Đo workload thực tế trước khi kết luận lock granularity nào tối ưu; correctness luôn đi trước hiệu năng.

## 18. Bài tập tự kiểm tra

**Câu 1.** Hai thread gọi `synchronized void add()` trên **hai instance khác nhau** của Counter. Chúng có phải chờ nhau không?

**Đáp án:** Không vì hai instance có monitor khác nhau, trừ khi bên trong add còn dùng thêm một shared lock khác. Nếu hai instance sửa cùng static field, instance-level synchronized không tự bảo vệ field đó.

**Câu 2.** `synchronized void update()` và `void read() { synchronized(this) { ... } }` thuộc **cùng instance**. Hai critical sections có chạy đồng thời trên hai thread không?

**Đáp án:** Không. Cả hai acquire cùng monitor của receiver.

**Câu 3.** `static synchronized void update()` và `synchronized void updateInstance()` thuộc cùng class. Có đương nhiên loại trừ nhau không?

**Đáp án:** Không. Static dùng Class monitor; instance dùng monitor của receiver.

**Câu 4.** Getter và setter đều synchronized trên `this`. Có đủ an toàn cho `set(get()+1)` không?

**Đáp án:** Không. Lock nhả giữa hai method. Cần một operation đồng bộ bao toàn read–modify–write.

**Câu 5.** Vì sao `synchronized(new Object())` thường không giải quyết tranh chấp shared counter?

**Đáp án:** Mỗi lời gọi tạo monitor khác nhau. Các thread không acquire cùng một khóa nên không có mutual exclusion trên counter.

**Câu 6.** Nếu có method xử lý 1 giây I/O nhưng chỉ tăng shared counter một lần, nên dùng synchronized method hay block?

**Đáp án:** Nếu I/O không thuộc invariant cần khóa, dùng block bảo vệ đúng lần tăng với shared lock để tránh giữ monitor suốt I/O. Nếu tài nguyên ngoài cùng tham gia invariant, cần thiết kế giao thức nhất quán ở phạm vi rộng hơn.

## 19. Tài liệu đối chiếu

- **Java Language Specification `8.4.3.6 — synchronized Methods:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.6
- **Java Language Specification `14.19 — The synchronized Statement:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19
- **Java Language Specification `17.1 — Synchronization:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1
- **Java Language Specification `17.4.4 — Synchronization Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4
- **Java Language Specification `17.4.5 — Happens-before Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
- **ReentrantLock API (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **Thread API (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

**Ghi nhớ cốt lõi:** `synchronized instance method` tương đương một `synchronized(this)` ôm trọn thân method; `static synchronized` tương đương dùng monitor `MyClass.class`; `synchronized block` cho phép chọn một monitor khác và thu hẹp vùng giữ khóa. **Cùng monitor và đúng phạm vi atomicity mới quyết định tính đúng**, không phải chỉ việc nhìn thấy từ khóa synchronized.
