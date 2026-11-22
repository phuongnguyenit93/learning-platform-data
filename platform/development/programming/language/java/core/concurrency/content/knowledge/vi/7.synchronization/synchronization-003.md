# Khóa theo instance và theo class trong Java Synchronization

## 1. Cùng là `synchronized` nhưng không nhất thiết cùng một khóa

Trong Java, mỗi đối tượng có một **intrinsic lock**, còn gọi là **monitor**. Khi thread đi vào một phương thức hoặc khối `synchronized`, nó phải chiếm được **monitor tương ứng**. Hai thread chỉ loại trừ lẫn nhau khi chúng cần **cùng một monitor**, không phải chỉ vì hai đoạn code đều viết từ khóa `synchronized`.

Hai kiểu thường gặp:

- **Instance lock (khóa theo đối tượng):** `synchronized` trên một instance method hoặc `synchronized(this)`. Monitor thuộc về **đối tượng cụ thể** đang được gọi.
- **Class lock (khóa theo lớp):** `static synchronized` hoặc `synchronized(MyType.class)`. Monitor thuộc về **đối tượng `Class` đại diện cho `MyType`** trong JVM.

Vì thế, hai đối tượng cùng lớp thường có **hai instance monitor khác nhau**, nhưng những phương thức `static synchronized` khai báo trên cùng một lớp được điều phối qua **cùng một class monitor**.

Ví dụ ý niệm:

```text
Counter a = new Counter()       Counter b = new Counter()
       │                               │
       ▼                               ▼
  monitor của a                  monitor của b
       │                               │
 a.increment()                   b.increment()
       └──── hai monitor khác nhau ────┘

                  Counter.class
                        │
                  class monitor
                        │
                 Counter.reset()
                 Counter.nextId()
           (static synchronized cùng lớp)
```

**Điểm mấu chốt:** đồng bộ là một *giao thức về danh tính khóa*. Từ khóa `synchronized` tự nó không biến mọi hoạt động trong cùng một class thành tuần tự.

Nội dung này thuộc **Java concurrency và synchronization nói chung**; không phụ thuộc framework.

## 2. Bốn hình thức cú pháp và monitor tương ứng

Giả sử lớp tên `Ledger`:

```java
class Ledger {
    synchronized void instanceMethod() {
        // Giữ monitor của this.
    }

    void instanceBlock() {
        synchronized (this) {
            // Giữ đúng monitor của this.
        }
    }

    static synchronized void staticMethod() {
        // Giữ monitor của Ledger.class.
    }

    static void classBlock() {
        synchronized (Ledger.class) {
            // Giữ đúng monitor của Ledger.class.
        }
    }
}
```

Đây là **đoạn định nghĩa lớp minh họa**, không phải chương trình độc lập. Hai cặp tương đương về **danh tính monitor**:

1. `synchronized void instanceMethod()` tương ứng với việc khóa `this` trong một instance method.
2. `static synchronized void staticMethod()` tương ứng với việc khóa `Ledger.class` khi thực thi phần thân static method được khai báo ở `Ledger`.

Tuy vậy, phạm vi giữ khóa trong một phương thức `synchronized` là **toàn bộ lời gọi phương thức**; còn một khối `synchronized(lock)` chỉ giữ khóa ở bên trong khối. Hai hình thức có thể khác nhau về **độ rộng critical section**, dù sử dụng cùng monitor.

Bảng tổng hợp:

| Cú pháp | Monitor cần lấy | Hai lời gọi có thể chạy đồng thời khi nào? |
| --- | --- | --- |
| `synchronized void work()` | `this` | Trên hai instance khác nhau |
| `synchronized (this) { ... }` | `this` | Khi các thread dùng hai instance khác nhau |
| `static synchronized void work()` | `DeclaringClass.class` | Nếu chúng ở hai lớp khai báo khác nhau với class monitor khác nhau |
| `synchronized (Ledger.class) { ... }` | `Ledger.class` | Nếu đoạn code kia dùng monitor khác |
| `synchronized (sharedLock) { ... }` | Chính object được biến `sharedLock` tham chiếu | Nếu `sharedLock` của hai lần gọi là hai object khác nhau |

`Ledger.class` là một đối tượng `java.lang.Class`, vì vậy nó cũng là một object có intrinsic monitor như các object khác. Nó không phải “khóa toàn bộ JVM”. Một class có thể được nạp bởi nhiều class loader khác nhau; mỗi định nghĩa runtime tương ứng có đối tượng `Class` riêng. Thông thường trong một ứng dụng dùng cùng class loader, mọi nơi viết `Ledger.class` đều tham chiếu cùng monitor.

### 2.1. Thực sự có bao nhiêu lock?

Với:

```java
Ledger a = new Ledger();
Ledger b = new Ledger();
```

có ít nhất ba object có thể dùng làm monitor mà bài đang quan tâm:

- `a`: monitor của instance thứ nhất.
- `b`: monitor của instance thứ hai.
- `Ledger.class`: monitor của Class object của `Ledger`.

`a != b` nên giữ monitor `a` không tự khóa `b`. `a` và `Ledger.class` cũng là hai object khác nhau, nên giữ monitor `a` **không** ngăn thread khác lấy `Ledger.class`, trừ khi thread đó phải đợi theo một giao thức khác.

## 3. Ví dụ chạy được: xác định monitor bằng `Thread.holdsLock`

Phương thức static `Thread.holdsLock(object)` cho biết **luồng hiện tại** có đang sở hữu intrinsic monitor của object đó hay không. Có thể dùng nó để xác nhận sự khác biệt mà không phụ thuộc thứ tự lập lịch của các thread.

Tạo tệp `MonitorIdentityDemo.java`:

```java
public class MonitorIdentityDemo {
    synchronized void checkInstance() {
        System.out.println("instance owns this="
                + Thread.holdsLock(this));
        System.out.println("instance owns class="
                + Thread.holdsLock(MonitorIdentityDemo.class));
    }

    static synchronized void checkClass() {
        System.out.println("static owns class="
                + Thread.holdsLock(MonitorIdentityDemo.class));
    }

    void checkExplicitBlocks() {
        synchronized (this) {
            System.out.println("block owns this="
                    + Thread.holdsLock(this));
        }
        synchronized (MonitorIdentityDemo.class) {
            System.out.println("block owns class="
                    + Thread.holdsLock(MonitorIdentityDemo.class));
        }
    }

    public static void main(String[] args) {
        MonitorIdentityDemo demo = new MonitorIdentityDemo();
        demo.checkInstance();
        checkClass();
        demo.checkExplicitBlocks();
    }
}
```

Lệnh chạy với JDK 17+:

```bash
javac MonitorIdentityDemo.java
java MonitorIdentityDemo
```

Kết quả:

```text
instance owns this=true
instance owns class=false
static owns class=true
block owns this=true
block owns class=true
```

Các dòng thể hiện **monitor nào đang thuộc về thread hiện tại**:

- `checkInstance()` là instance synchronized method nên giữ `demo` (`this`), không tự giữ `MonitorIdentityDemo.class`.
- `checkClass()` là static synchronized method nên giữ `MonitorIdentityDemo.class`.
- `checkExplicitBlocks()` chứng minh cả hai monitor cũng có thể lấy bằng khối synchronized.

Ở đây tất cả lời gọi chạy tuần tự trên main để quan sát chính xác; ví dụ không nhằm đo throughput hay số thread chạy đồng thời. Trong một ứng dụng lớn, `Thread.holdsLock` hữu ích cho assertion hoặc chẩn đoán, nhưng không nên dùng nó để “tự kiểm tra rồi khỏi khóa” khi cập nhật state.

## 4. Instance lock: tách sự đồng bộ theo từng đối tượng

Một instance method `synchronized` sử dụng monitor của **receiver** (đối tượng ở bên trái dấu chấm khi gọi). Nếu thread A gọi `a.deposit(...)` và thread B gọi `a.withdraw(...)` mà cả hai method đều synchronized, chúng tranh **cùng monitor `a`**. Không có chuyện cả hai thực thi phần thân đã bảo vệ cùng lúc trên cùng `a`.

Ngược lại, khi thread A gọi `a.deposit(...)` và thread B gọi `b.deposit(...)` với `a != b`, hai thread lấy **hai monitor khác nhau**. Chúng có thể tiến triển đồng thời. Điều này thường là mong muốn nếu `a` và `b` nắm giữ dữ liệu độc lập.

Tạo tệp `PerInstanceCounterDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class PerInstanceCounterDemo {
    private static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter a = new Counter();
        Counter b = new Counter();
        CountDownLatch begin = new CountDownLatch(1);

        Thread first = new Thread(() -> {
            try {
                begin.await();
                for (int i = 0; i < 1_000; i++) {
                    a.increment();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "first");

        Thread second = new Thread(() -> {
            try {
                begin.await();
                for (int i = 0; i < 1_000; i++) {
                    b.increment();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "second");

        first.start();
        second.start();
        begin.countDown();
        first.join();
        second.join();

        System.out.println("a=" + a.get());
        System.out.println("b=" + b.get());
    }
}
```

```bash
javac PerInstanceCounterDemo.java
java PerInstanceCounterDemo
```

Kết quả khi không có interrupt bên ngoài:

```text
a=1000
b=1000
```

Mỗi đối tượng `Counter` bảo vệ **trường `value` của chính nó**. `a.increment()` và `b.increment()` không tranh cùng một monitor, giúp tránh serialize các cập nhật thực sự độc lập. `join()` bảo đảm main đọc kết quả sau khi cả hai worker kết thúc.

Lưu ý: ví dụ không khẳng định hai thread luôn chạy song song trên hai CPU core. Nó chỉ cho thấy chúng **không bị một instance lock chung ép loại trừ lẫn nhau**.

### 4.1. Phạm vi của instance lock phải khớp với phạm vi state

Nếu `value` là một trường instance riêng cho từng `Counter`, việc khóa từng instance là hợp lý. Nhưng nếu nhiều instance thực tế cùng tham chiếu đến một mutable object bên ngoài, ví dụ dùng chung một `HashMap` static, thì hai instance lock khác nhau **không đủ** để bảo vệ cấu trúc chung.

Quy tắc: **khóa cần gắn với dữ liệu/đơn vị bất biến cần bảo vệ**, không chỉ gắn với tên method.

## 5. Class lock: điều phối state dùng chung ở cấp lớp

Một `static` field được chia sẻ bởi các instance thuộc cùng định nghĩa runtime của lớp. Nếu nhiều thread truy cập field này, khóa từng instance có thể không bảo vệ được nó, bởi các thread có thể sử dụng instance khác nhau.

Ví dụ rủi ro:

```java
class TicketIssuer {
    private static int nextId;

    synchronized int issue() {
        return ++nextId;
    }
}
```

Đây là đoạn định nghĩa lớp minh họa. `issue()` là **instance synchronized method**, vì vậy:

- `issuerA.issue()` giữ khóa của `issuerA`.
- `issuerB.issue()` giữ khóa của `issuerB`.
- Cả hai sửa **cùng `TicketIssuer.nextId`** nhưng không dùng chung monitor.
- `++nextId` là read-modify-write, có thể lost update; thread khác có thể quan sát giá trị không đúng nếu thiếu đồng bộ.

Cách đơn giản nếu nghiệp vụ là một bộ cấp ID chung trong JVM:

```java
class TicketIssuer {
    private static int nextId;

    static synchronized int issue() {
        return ++nextId;
    }
}
```

Lúc này các lời gọi `TicketIssuer.issue()` dùng monitor `TicketIssuer.class`. Nếu mọi đường cập nhật và đọc liên quan đều tuân thủ cùng khóa, `nextId` được bảo vệ trong phạm vi JVM/class loader tương ứng.

Hoặc dùng khối:

```java
class TicketIssuer {
    private static int nextId;

    static int issue() {
        synchronized (TicketIssuer.class) {
            return ++nextId;
        }
    }
}
```

Hai cách đều là **mã minh họa lớp**, không phải chương trình Java có `main`. Trong thực tế, nếu chỉ cần bộ đếm nguyên tử có thể dùng `AtomicInteger.incrementAndGet()`, nhưng nếu phải bảo vệ **nhiều trường liên quan** thì phải xác định một critical section hoặc snapshot bao trùm toàn bộ invariant.

### 5.1. Class lock không phải “khóa mọi đối tượng của lớp”

Khi một thread giữ `TicketIssuer.class`, một thread khác vẫn có thể vào `issuer.synchronizedInstanceMethod()` vì method đó cần monitor của `issuer`, không phải `TicketIssuer.class`.

Tương tự, hai static synchronized methods thuộc về **hai lớp khác nhau** sẽ không tự loại trừ nhau chỉ vì chúng cùng chạy trong một JVM. Danh tính class monitor, không phải từ khóa static, quyết định xung đột.

## 6. Minh chứng lost update xác định khi khóa sai phạm vi

Đoạn dưới cho hai thread dùng **hai instance khác nhau**, cùng sửa một trường `static volatile int`. Latch buộc cả hai đọc giá trị cũ trước khi bất kỳ thread nào ghi, qua đó chứng minh việc đặt `synchronized` vào instance method **không bảo vệ shared static state**.

Tạo tệp `WrongScopeLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class WrongScopeLockDemo {
    private static volatile int sharedCounter;

    synchronized void badIncrement(
            CountDownLatch bothRead,
            CountDownLatch allowWrite) {
        int oldValue = sharedCounter;
        bothRead.countDown();
        try {
            allowWrite.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
        sharedCounter = oldValue + 1;
    }

    static synchronized void safeIncrement() {
        sharedCounter++;
    }

    public static void main(String[] args) throws InterruptedException {
        WrongScopeLockDemo a = new WrongScopeLockDemo();
        WrongScopeLockDemo b = new WrongScopeLockDemo();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Thread first = new Thread(
                () -> a.badIncrement(bothRead, allowWrite));
        Thread second = new Thread(
                () -> b.badIncrement(bothRead, allowWrite));

        first.start();
        second.start();
        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();
        System.out.println("wrong lock result=" + sharedCounter);

        sharedCounter = 0;
        Thread safeA = new Thread(WrongScopeLockDemo::safeIncrement);
        Thread safeB = new Thread(WrongScopeLockDemo::safeIncrement);
        safeA.start();
        safeB.start();
        safeA.join();
        safeB.join();
        System.out.println("class lock result=" + sharedCounter);
    }
}
```

```bash
javac WrongScopeLockDemo.java
java WrongScopeLockDemo
```

Kết quả khi không có interrupt bên ngoài:

```text
wrong lock result=1
class lock result=2
```

**Phân tích từng bước:**

1. `first` giữ monitor `a`; `second` giữ monitor `b`. Vì `a != b`, chúng không ngăn nhau vào `badIncrement`.
2. Cả hai đọc `sharedCounter = 0` trước khi main phát `allowWrite`. Latch giúp kết quả này xác định.
3. Mỗi thread lưu lại `oldValue = 0` rồi ghi `oldValue + 1`. Kết quả cuối là `1` dù hai thao tác tăng đã được yêu cầu.
4. Main đợi `join()` rồi đặt `sharedCounter = 0` để bắt đầu phép thử thứ hai.
5. Hai lời gọi `safeIncrement()` cùng tranh **monitor `WrongScopeLockDemo.class`**. Vì toàn bộ read-modify-write nằm trong một class critical section, cả hai phép tăng được giữ, kết quả `2`.

Trường `sharedCounter` là `volatile` trong ví dụ để tránh chuyển trọng tâm sang stale-read, **nhưng volatile không biến phép `x++` thành atomic**. Nếu chuyển `badIncrement` thành một method `static synchronized` trên lớp, hai lời gọi sẽ chờ nhau qua cùng class monitor, không còn lịch xen kẽ mất cập nhật như trên.

Bài học tổng quát không phải “mọi static field đều bắt buộc khóa bằng class monitor”; điều bắt buộc là **mọi thread phải thống nhất cùng một cơ chế đồng bộ bảo vệ shared state**. Một `private static final Object LOCK` riêng hoặc `AtomicInteger` cũng có thể phù hợp tùy invariant.

## 7. Instance lock và class lock độc lập với nhau

Một thread đang giữ khóa của instance **không có nghĩa** nó giữ luôn khóa của class. Điều ngược lại cũng đúng. Có thể chứng minh bằng chương trình không cần suy đoán thứ tự log giữa các thread.

Tạo tệp `IndependentMonitorsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class IndependentMonitorsDemo {
    synchronized void holdInstance(
            CountDownLatch entered,
            CountDownLatch release) {
        entered.countDown();
        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static synchronized void useClassMonitor() {
        System.out.println("class method can enter");
    }

    public static void main(String[] args) throws InterruptedException {
        IndependentMonitorsDemo object = new IndependentMonitorsDemo();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() ->
                object.holdInstance(entered, release));
        holder.start();
        entered.await();

        useClassMonitor();  // Không cần chờ monitor của object.
        release.countDown();
        holder.join();

        System.out.println("holder finished");
    }
}
```

```bash
javac IndependentMonitorsDemo.java
java IndependentMonitorsDemo
```

Kết quả khi không có interrupt bên ngoài:

```text
class method can enter
holder finished
```

Thread `holder` đang giữ monitor của `object` và chờ latch `release`. Main gọi static synchronized method và vào được monitor của `IndependentMonitorsDemo.class` **trước khi** phát `release`. Nếu hai method tranh cùng một monitor, cách sắp xếp này sẽ bị kẹt; nó chạy được vì monitor khác nhau.

Chương trình này là bài thử riêng biệt về danh tính khóa. Không nên tạo vòng chờ latch có nguy cơ deadlock chỉ để “kiểm tra” một hệ thống sản xuất. Trong test có thể dùng `await(timeout)` và báo lỗi rõ ràng nếu không nhận được tín hiệu.

## 8. Một object có thể giữ cả hai monitor, nhưng không tự động

Trong một instance method, bạn được phép viết:

```java
class GlobalLedger {
    private static int total;
    private int local;

    synchronized void addToBoth() {
        synchronized (GlobalLedger.class) {
            local++;
            total++;
        }
    }
}
```

Đây là mã minh họa. Khi gọi `object.addToBoth()`, thread chiếm monitor của `object` trước, rồi cố chiếm monitor của `GlobalLedger.class`. Nó sở hữu **cả hai** trong phần thân bên trong. Khi rời khối bên trong, nó nhả class monitor nhưng vẫn giữ instance monitor cho đến khi instance method trả về.

Điều đó có thể hợp lý nếu thao tác thật sự cần bảo vệ một invariant liên quan giữa state instance và state class, nhưng tạo ra nguy cơ **deadlock vì thứ tự lấy khóa** nếu chỗ khác lấy class monitor trước rồi cố lấy instance monitor.

Ngoài ra, có thể đồng bộ theo **một lock riêng** thay vì giữ hai lock:

```java
class GlobalLedger {
    private static final Object GLOBAL_LOCK = new Object();
    private static int total;
    private int local;

    void addToBoth() {
        synchronized (GLOBAL_LOCK) {
            local++;
            total++;
        }
    }
}
```

Đây vẫn là mã minh họa, nhưng mọi instance cùng dùng `GLOBAL_LOCK` nên bảo vệ phép cập nhật chung. Đổi lại, các cập nhật trên instance khác nhau sẽ bị serialize ngay cả khi có thể tách dữ liệu thành các vùng độc lập. Phải cân nhắc đơn vị invariant và mức contention.

**Không dùng “synchronized mọi method” một cách máy móc:** bảo vệ đúng từng object hoặc một state chung là yêu cầu đúng đắn; giữ khóa rộng hơn mức cần thiết có thể làm chậm ứng dụng.

## 9. Deadlock khi trộn instance và class lock

Giả sử hai đường thao tác:

```text
Thread A: giữ instance lock -> chờ class lock
Thread B: giữ class lock    -> chờ instance lock

A chờ B nhả class lock
B chờ A nhả instance lock
=> vòng chờ, có thể deadlock
```

Một ví dụ cấu trúc nguy hiểm (minh họa, **không phải chương trình độc lập và không nên chạy để tạo deadlock**):

```java
class Risky {
    synchronized void instanceThenClass() {
        synchronized (Risky.class) {
            // Cập nhật chung.
        }
    }

    static void classThenInstance(Risky target) {
        synchronized (Risky.class) {
            synchronized (target) {
                // Cập nhật khác.
            }
        }
    }
}
```

Nếu Thread A đã lấy monitor của `target` trong `instanceThenClass`, còn Thread B lấy `Risky.class` trong `classThenInstance`, mỗi bên có thể chờ monitor mà bên kia giữ.

**Cách phòng tránh:**

1. Hạn chế giữ nhiều monitor cùng lúc khi thiết kế cho phép.
2. Nếu phải giữ nhiều lock, quy định **một thứ tự khóa nhất quán** cho tất cả code, chẳng hạn luôn lấy class lock trước rồi mới đến instance lock.
3. Tránh gọi các callback, plugin hoặc method có thể chạy code không kiểm soát trong khi đang giữ khóa; chúng có thể lấy lock khác theo thứ tự ngược.
4. Không dựa vào `Thread.sleep()` để phòng deadlock. Sleep không nhả monitor.
5. Dùng thread dump, Java Flight Recorder hoặc công cụ chẩn đoán deadlock khi cần. Công cụ chỉ giúp phát hiện; biện pháp chính vẫn là thiết kế thứ tự khóa.

Một deadlock do hai intrinsic monitor không thể sửa bằng cách “thử `synchronized` lại với timeout” vì ngôn ngữ không cung cấp thao tác try-lock cho `synchronized`. Nếu nghiệp vụ cần timeout khi lấy khóa, có thể cân nhắc `ReentrantLock.tryLock(timeout, unit)` cùng giao thức rollback và thứ tự khóa phù hợp.

## 10. Reentrancy: cùng thread được vào lại monitor đang giữ

Intrinsic lock của Java là **reentrant (tái nhập)**. Nếu một thread đã giữ monitor `this`, nó có thể gọi một instance synchronized method khác trên **cùng object** mà không tự chặn chính nó.

```java
class ReentrantCounter {
    private int count;

    synchronized void addTwo() {
        increment();
        increment();
    }

    synchronized void increment() {
        count++;
    }

    synchronized int value() {
        return count;
    }
}
```

Đây là đoạn định nghĩa lớp minh họa. Khi gọi `obj.addTwo()`, thread đã giữ monitor `obj` và có thể gọi `obj.increment()` hai lần. Monitor theo dõi mức tái nhập; chỉ khi các vùng synchronized tương ứng được thoát hết thì monitor mới được nhả cho thread khác.

Tương tự, một static synchronized method của `ReentrantCounter` có thể gọi static synchronized method khác trên cùng `ReentrantCounter.class` mà không tự deadlock.

Nhưng **reentrancy chỉ áp dụng cho cùng monitor và cùng thread**. Việc đang giữ instance monitor không đồng nghĩa “tái nhập” class monitor; nếu method sau cần class monitor, đó vẫn là việc chiếm một **monitor khác** có thể bị thread khác giữ.

Khi một đoạn synchronized ném exception, JVM vẫn nhả monitor khi rời method/block theo cách phù hợp; không phải tự viết `unlock()` cho intrinsic lock. Điều này khác `ReentrantLock`, nơi cần `try/finally` để gọi `unlock()`.

## 11. Java Memory Model: happens-before phải cùng monitor

`synchronized` không chỉ cung cấp mutual exclusion. JMM còn có quy tắc:

> Một hành động **unlock** trên monitor M *happens-before* mọi hành động **lock M** về sau theo synchronization order.

Điều này giúp thread đọc nhìn thấy các thay đổi mà thread ghi đã thực hiện trước khi nhả **chính monitor đó**.

Ví dụ với monitor của instance:

```java
class Status {
    private int value;

    synchronized void set(int next) {
        value = next;
    }

    synchronized int get() {
        return value;
    }
}
```

Nếu cùng object `status`, thread A gọi `status.set(42)` hoàn thành trước khi thread B sau đó chiếm được monitor `status` để gọi `status.get()`, quan hệ đồng bộ hỗ trợ việc B quan sát giá trị được ghi. Nếu nhiều writer khác cập nhật sau đó, B có thể thấy một giá trị khác phù hợp thứ tự thực tế; không thể khẳng định mọi lần `get` đều trả đúng `42` mà bỏ qua các lần ghi khác.

**Sai monitor, thiếu bảo đảm:**

```java
class BadStatus {
    private static int value;

    synchronized void set(int next) {
        value = next;
    }

    synchronized int get() {
        return value;
    }
}
```

Nếu Thread A gọi `a.set(42)` còn Thread B gọi `b.get()` với `a != b`, hai method khóa **hai monitor khác nhau** dù đọc/ghi **cùng static field**. Không có quan hệ unlock/lock trên cùng monitor giữa hai lời gọi này. Cùng một từ khóa `synchronized` không đủ để kết luận rằng static field được công bố đúng.

Cũng không được suy luận rằng `volatile` hoặc `AtomicInteger` bảo vệ nhiều trường liên quan như một transaction. Chúng có thể cung cấp visibility hoặc atomicity theo từng biến/thao tác, nhưng bất biến nhiều trường cần một giao thức chung.

## 12. `wait()`, `notify()` và `notifyAll()` gắn với monitor cụ thể

Mỗi object monitor có tập thread đang chờ riêng. `wait` và `notify/notifyAll` là method của `Object`, không phải “tín hiệu toàn class”.

Ví dụ dùng **instance monitor**:

```java
synchronized (this) {
    while (!ready) {
        this.wait();
    }
}
```

Ví dụ dùng **class monitor**:

```java
synchronized (SignalBus.class) {
    while (!sharedReady) {
        SignalBus.class.wait();
    }
}
```

Đây là **hai đoạn minh họa riêng**, giả sử `ready` và `sharedReady` là các điều kiện được bảo vệ đúng, còn `SignalBus` là class đã khai báo. Mỗi lời gọi `wait()` yêu cầu luồng hiện tại **đang giữ monitor của chính object gọi wait**. Nếu không, nó ném `IllegalMonitorStateException`.

- `this.wait()` nhả và chờ trên monitor **instance `this`**.
- `SignalBus.class.wait()` nhả và chờ trên monitor **Class object `SignalBus.class`**.
- `this.notifyAll()` **không** đánh thức thread đang chờ `SignalBus.class.wait()`, và ngược lại.
- Thread sau khi nhận thông báo phải chiếm lại **đúng monitor tương ứng** trước khi tiếp tục từ `wait`.
- Nên kiểm tra điều kiện trong vòng `while` để xử lý spurious wakeup hoặc thay đổi điều kiện trước lúc thread lấy lại monitor.

Không gọi `wait/notify` trên monitor chỉ vì “cùng tên lớp”; phải khớp **object identity** giữa các thread tham gia. Với nhu cầu producer/consumer, các cấu trúc cao hơn như `BlockingQueue` hoặc `Condition` thường giảm lỗi giao thức.

## 13. Kế thừa, method hiding và `getClass()`: các bẫy ít rõ ràng

### 13.1. Instance synchronized method kế thừa vẫn khóa receiver thực

Nếu lớp `Base` có `synchronized void work()` và `Derived extends Base`, gọi method kế thừa trên `new Derived()` sẽ giữ monitor của **instance Derived đó**, không phải `Base.class`. Monitor của instance không thay đổi chỉ vì method được khai báo trong lớp cha.

Nếu hai method synchronized khác nhau (kế thừa hoặc khai báo tại lớp con) được gọi trên **cùng receiver**, chúng tranh cùng instance monitor `this`.

### 13.2. Static synchronized method thuộc lớp khai báo của method

Xét:

```java
class Base {
    static synchronized void baseGlobal() {
        // Monitor Base.class.
    }
}

class Derived extends Base {
    static synchronized void derivedGlobal() {
        // Monitor Derived.class.
    }
}
```

Đây là mã minh họa. `Base.baseGlobal()` và `Derived.derivedGlobal()` dùng **hai class monitor khác nhau**, nên không tự loại trừ lẫn nhau.

Nếu `Derived` chỉ thừa hưởng tên một static synchronized method khai báo ở `Base` mà không khai báo method mới, method được thực thi vẫn do `Base` khai báo và khóa `Base.class`. Static methods là **hiding** chứ không phải overriding đa hình như instance methods. Điều quan trọng là monitor của **lớp khai báo method static synchronized đang thực thi**.

### 13.3. `this.getClass()` không luôn bằng `DeclaringType.class`

Trong một instance method của `Base`, biểu thức `this.getClass()` có thể trả về `Derived.class` nếu receiver là object subclass. Trong khi đó, `Base.class` luôn chỉ class monitor của `Base`.

Vì vậy, dùng:

```java
synchronized (getClass()) {
    // Với một subclass, khóa Class object của subclass.
}
```

**không tương đương tổng quát** với:

```java
synchronized (Base.class) {
    // Luôn khóa đúng Base.class.
}
```

Hai đoạn trên là minh họa bên trong một instance method của `Base`. Nếu mục tiêu bảo vệ state `static` được khai báo chung ở `Base`, sử dụng `Base.class` hoặc một private static lock được quy định rõ, thay vì `getClass()` làm thay đổi lock theo runtime subclass.

### 13.4. Class loader tạo ranh giới bổ sung

Tên lớp giống nhau chưa chắc cùng một `Class` object nếu được nạp bởi hai class loader khác nhau. `synchronized(MyType.class)` điều phối các thread truy cập **cùng định nghĩa runtime của MyType**, không điều phối mọi process hay mọi class loader có tên đó.

Dữ liệu thật sự dùng chung ngoài một JVM không được bảo vệ chỉ bằng `static synchronized`. Muốn điều phối giữa các JVM/process cần cơ chế tại tầng tài nguyên chia sẻ như giao dịch cơ sở dữ liệu, khóa phân tán hoặc giao thức phù hợp — ngoài phạm vi intrinsic monitor Java.

## 14. Khi nào dùng monitor riêng thay vì khóa trực tiếp `this` hoặc `Class`?

Có thể chọn một lock **private, final và không công bố**:

```java
class Inventory {
    private final Object instanceLock = new Object();
    private static final Object CLASS_LOCK = new Object();

    private int localUnits;
    private static int globalUnits;

    void addLocal(int n) {
        synchronized (instanceLock) {
            localUnits += n;
        }
    }

    static void addGlobal(int n) {
        synchronized (CLASS_LOCK) {
            globalUnits += n;
        }
    }
}
```

Đây là mã minh họa. Ưu điểm:

- `instanceLock` là một object riêng cho từng `Inventory`; nó bảo vệ state của từng instance giống ý định khóa `this`.
- `CLASS_LOCK` là một object duy nhất theo runtime class definition; nó bảo vệ shared static state.
- Caller bên ngoài thường **không thể tự ý chiếm** các private lock này, khác với `synchronized(inventory)` hoặc `synchronized(Inventory.class)`, vốn có thể do code bên ngoài thực hiện. Điều này giảm nguy cơ khóa bị dùng chung ngoài ý muốn.
- Có thể tách nhiều nhóm state độc lập theo những private lock khác nhau để giảm contention, nhưng cần thiết kế rõ invariant xuyên nhóm.

**Bẫy lớn:** không tạo `new Object()` trong mỗi lần gọi method rồi synchronize nó, nếu ý định là các lời gọi phải chặn nhau:

```java
void wrong() {
    Object localLock = new Object();
    synchronized (localLock) {
        // Mỗi lời gọi giữ một lock mới, không bảo vệ state chung.
    }
}
```

Tương tự, nếu muốn tất cả instances chia sẻ một monitor, `private final Object lock` **không đủ** vì mỗi instance sẽ có object lock riêng. Phải dùng `private static final Object LOCK` hoặc một object lock chung được truyền có kiểm soát.

Không dùng `String` literal, object được intern, kiểu boxed số nguyên hoặc các object toàn cục không thuộc quyền sở hữu của bạn làm monitor. Chúng có thể vô tình được chia sẻ ở nơi khác, tạo contention/deadlock khó truy vết. Hãy chọn lock object riêng và có owner rõ ràng.

## 15. Tác động hiệu năng và mức độ cạnh tranh

**Instance locking** thường cho phép concurrency tốt khi mỗi instance chứa state độc lập. Một dịch vụ có 1.000 tài khoản độc lập có thể cập nhật nhiều tài khoản cùng lúc thay vì chờ một class lock chung. Nhưng nếu mỗi thao tác phải cập nhật một tổng chung, vẫn cần một cơ chế bảo vệ tổng đó.

**Class locking** serialize các lời gọi cần cùng class monitor. Nó đơn giản khi các thay đổi tác động tới state toàn cục của class, nhưng có thể trở thành nút thắt nếu code đang giữ khóa thực hiện I/O chậm, `sleep`, chờ Future, gọi callback ngoài hoặc làm việc CPU lớn.

Một số nguyên tắc thực hành:

- **Giữ critical section ngắn nhất có thể nhưng đủ rộng** để bảo vệ toàn bộ invariant; không chia nhỏ quá mức làm hở trạng thái trung gian.
- **Không ngủ trong synchronized** để chờ thread khác cập nhật state được bảo vệ cùng monitor: `Thread.sleep()` không nhả monitor. Nếu chờ condition theo monitor, dùng `wait()` đúng giao thức; thông thường nên cân nhắc các primitive `java.util.concurrent`.
- **Không giả định class lock luôn chậm hơn instance lock.** Tốc độ phụ thuộc contention, kích thước critical section, JVM và workload.
- **Dùng benchmark đúng cách** như JMH khi cần đo throughput/latency; một vài lần `System.nanoTime` có thể bị tác động bởi JIT, warmup và lịch chạy.
- **Chọn theo phạm vi dữ liệu**, không theo cảm giác “global” của một method. Static method có thể làm việc với state riêng được truyền vào; instance method có thể sửa state static. Danh tính khóa phải khớp invariant, không phải modifier của method bằng mọi giá.

## 16. Quy tắc chọn khóa theo bài toán

| Trạng thái cần bảo vệ | Khóa thường hợp lý | Vì sao | Lưu ý |
| --- | --- | --- | --- |
| `balance` thuộc một đối tượng `Account` | Instance monitor `this` hoặc private instance lock | Các thao tác trên cùng account loại trừ nhau; account khác có thể độc lập | Reader cũng phải dùng cùng lock |
| Bộ đếm `static nextId` chia sẻ nhiều instance | Class monitor, private static lock hoặc atomic counter | Tất cả writer thống nhất cùng cơ chế | `synchronized instanceMethod` trên nhiều instances không đủ |
| Hai trường instance phải đổi cùng nhau | Một monitor bảo vệ **cả cập nhật và snapshot đọc** | Không đọc lẫn thế hệ dữ liệu | Không chỉ khóa từng getter riêng |
| Một cache static mutable dùng chung | Private static lock hoặc concurrent collection phù hợp | Phạm vi chia sẻ cấp class | Kiểm tra invariant cần atomic trên nhiều entry hay không |
| State mutable nằm trong một service singleton | Lock của đúng service object có thể đủ | Tất cả callers dùng cùng receiver | Nếu sau này có nhiều instance cùng sửa static field sẽ khác |
| Hai accounts cần chuyển tiền như một giao dịch | Giao thức khóa cả hai accounts theo thứ tự cố định, hoặc một coordinator lock | Phải bảo vệ invariant xuyên accounts | Tránh deadlock và thất bại giữa chừng |
| Config được thay nguyên phiên bản | Immutable snapshot + `volatile`/`AtomicReference` | Reader có thể đọc không cần monitor cho từng field | Reader lấy snapshot một lần; nhiều writer cần CAS/lock |

Không có quy tắc máy móc “mọi static field phải static synchronized” hoặc “mọi instance field chỉ dùng synchronized method”. Cần xác định **đâu là state dùng chung, ai có thể chạm vào nó, invariant nào cần đúng và mọi reader/writer có dùng cùng một giao thức hay không**.

## 17. Lỗi phổ biến và cách nhận diện

### 17.1. Mỗi instance tự khóa, nhưng cùng cập nhật một static field

Dấu hiệu là một method `synchronized` không static chứa `++staticCounter`, và method được gọi trên nhiều receiver khác nhau. Có thể gây lost update. Sửa bằng class lock/private static lock, `AtomicInteger` nếu chỉ là biến đếm, hoặc tái thiết kế owner của state.

### 17.2. Static synchronized method và instance synchronized method được tưởng là chặn nhau

Chúng không chặn nhau chỉ vì thuộc cùng class. Static method khóa `Class` object; instance method khóa receiver. Nếu cả hai sửa cùng state, cần cho chúng dùng **cùng monitor**.

### 17.3. Getter chỉ đồng bộ riêng lẻ khi cần snapshot nhiều trường

Hai getter `synchronized` được gọi liên tiếp vẫn nhả monitor ở giữa. Writer có thể cập nhật giữa hai getter. Cần một method `snapshot()` đọc cả nhóm field dưới **một critical section** hoặc immutable snapshot được công bố nguyên tử.

### 17.4. Khóa object khác với object mà thread khác khóa

`synchronized(this)` trong hai object khác nhau là hai monitor. `synchronized(new Object())` trong từng lời gọi cũng là các monitor khác nhau. Nếu cần cùng lock, hãy bảo đảm **cùng identity**, không chỉ cùng class/type của object.

### 17.5. Khóa quá rộng và gọi code không kiểm soát

Giữ class monitor khi gọi network, database, callback hoặc `join()` lâu có thể chặn mọi thread khác cần cùng monitor. Tính toán tốn kém nên đưa ra ngoài critical section khi không làm hở invariant. Cần kiểm tra thứ tự lock ở mọi đường gọi.

### 17.6. Dùng `getClass()` và nghĩ luôn khóa base class

Với subclass, `getClass()` trả runtime class. Nếu muốn khóa state static của base class, tham chiếu đúng `Base.class` hoặc private static lock của base.

### 17.7. Quên khả năng deadlock khi dùng hai monitor

Thread A lấy instance rồi class, thread B lấy class rồi instance. Cần một thứ tự toàn cục cho việc chiếm nhiều khóa, hoặc giảm về một lock bảo vệ invariant cần thiết.

### 17.8. Nhầm `volatile` với khóa

`volatile` cung cấp visibility/thứ tự đối với biến đó nhưng không khóa một read-modify-write như `counter++`, càng không biến nhiều trường thành transaction. Cần synchronized/atomic operation hoặc cấu trúc khác tương ứng.

## 18. Bài tập tự kiểm tra

**Câu 1.** Hai đối tượng `a` và `b` của cùng lớp có method `synchronized void f()`. Thread A gọi `a.f()`, thread B gọi `b.f()`. Hai thread có buộc phải lần lượt vào method không?

**Trả lời:** Không. Mỗi method lấy monitor của receiver; `a != b` nên hai monitor khác nhau. Chúng có thể chạy đồng thời, trừ khi có cơ chế đồng bộ khác.

**Câu 2.** `static synchronized void g()` khóa object nào?

**Trả lời:** Monitor của đối tượng `Class` đại diện cho lớp **khai báo method `g` đang thực thi**. Ví dụ `Ledger.g()` khai báo ở `Ledger` sẽ khóa `Ledger.class`, không phải một instance của `Ledger`.

**Câu 3.** Thread A ở trong `synchronized(a)`, thread B muốn gọi `static synchronized h()` của lớp `A`. Có tự chặn nhau không?

**Trả lời:** Không nếu `a` là instance `A` bình thường: `a` và `A.class` khác monitor. Nếu code B còn cần một monitor khác đang bị giữ thì nó vẫn có thể chờ vì nguyên nhân riêng.

**Câu 4.** Vì sao `synchronized void inc() { ++sharedStatic; }` có thể sai nếu dùng nhiều instance?

**Trả lời:** Mỗi instance khóa chính nó, nhưng tất cả sửa cùng static field. Hai thread dùng hai instance không chặn nhau, nên read-modify-write có thể mất cập nhật.

**Câu 5.** Một thread giữ `Ledger.class` rồi gọi một synchronized instance method của `ledger`. Có chắc chắn đó là reentrant acquisition không?

**Trả lời:** Không. Đây là hai monitor khác nhau. Reentrancy chỉ áp dụng khi thread lấy lại **cùng monitor** mà nó đã sở hữu.

**Câu 6.** `synchronized(Base.class)` và `synchronized(this.getClass())` có luôn giống nhau trong method của `Base` không?

**Trả lời:** Không. Nếu receiver là `Derived extends Base`, `this.getClass()` có thể là `Derived.class`. Hai class monitors khác nhau.

**Câu 7.** Nếu mọi writer lấy class monitor nhưng reader chỉ lấy instance monitor để đọc static field, có bảo đảm happens-before qua lock không?

**Trả lời:** Không chỉ nhờ hai vùng synchronized đó. Unlock/lock phải thuộc cùng monitor để tạo cạnh đồng bộ tương ứng; reader cần cùng class lock hoặc một cơ chế công bố khác có hợp đồng rõ.

**Câu 8.** Khi cần chuyển tiền giữa hai đối tượng `Account` khác nhau, chỉ khóa account nguồn có đủ không?

**Trả lời:** Thường không nếu thao tác cập nhật cả hai account và cần invariant xuyên chúng. Cần giao thức bảo vệ cả hai object theo thứ tự tránh deadlock, hoặc khóa coordinator và các API đọc/ghi tuân thủ cùng hợp đồng.

## 19. Tổng kết

**Instance lock** là monitor của **một đối tượng cụ thể**: `synchronized instanceMethod()` và `synchronized(this)` khóa receiver. **Class lock** là monitor của **`Class` object**: `static synchronized staticMethod()` và `synchronized(DeclaringClass.class)` khóa một class definition cụ thể. Hai instance có hai monitor khác nhau; instance monitor và class monitor cũng khác nhau.

Sự an toàn không đến từ việc “chỗ nào cũng có synchronized” mà đến từ việc **mọi thao tác liên quan cùng bảo vệ một invariant bằng đúng monitor hoặc cùng một giao thức đồng bộ**. Khi chọn khóa, hãy xác định phạm vi state thực sự chia sẻ, sự tương ứng giữa reader/writer, quan hệ happens-before, mức contention và thứ tự lấy khóa để tránh deadlock. Đó là nền tảng để dùng synchronization chính xác trong Java.
