# Monitor của đối tượng và tính tái nhập của synchronized

## 1. Tổng quan và mục tiêu học tập

Trong Java, **synchronized** giúp nhiều thread phối hợp quyền truy cập vào dữ liệu dùng chung thông qua một **monitor** gắn với **một object cụ thể**. Một thread phải có quyền sở hữu monitor tương ứng mới được vào vùng mã đồng bộ hóa do monitor đó bảo vệ. Khi một thread đã sở hữu monitor, nó có thể **tái nhập (reenter)** cùng monitor nhiều lần, thay vì tự chặn chính mình. Khả năng này gọi là **reentrant synchronization**.

Ba ý tưởng quan trọng nhất:

1. **Monitor gắn với object identity, không gắn với tên phương thức.** Hai khối synchronized chỉ loại trừ lẫn nhau nếu đang dùng **chính cùng một monitor object**.
2. **Synchronized là reentrant.** Thread đang giữ monitor có thể vào lại synchronized method/block sử dụng cùng object, ngay cả qua chuỗi gọi methods hoặc đệ quy. JVM theo dõi số lần vào chưa được cân bằng bằng số lần thoát.
3. **Khóa monitor không chỉ là mutual exclusion.** Theo Java Memory Model (JMM), thao tác **unlock monitor M happens-before mọi lần lock M tiếp theo**; đây là một cơ chế visibility/ordering quan trọng đối với shared mutable state.

Sau bài này, bạn sẽ biết:

- Monitor là gì và tại sao mọi Java object đều có thể dùng làm monitor.
- **Owner thread**, **reentrancy/entry count**, cách acquire và release monitor.
- Phân biệt **synchronized instance method**, **static synchronized method** và **synchronized(lock)**.
- Vì sao một synchronized method có thể gọi một synchronized method khác của cùng object mà không deadlock.
- Cách Java compiler/JVM biểu diễn **monitorenter/monitorexit** và cờ **ACC_SYNCHRONIZED**.
- Sự khác biệt giữa **BLOCKED** khi chờ vào monitor và **WAITING/TIMED_WAITING** trong Object.wait().
- Tại sao **wait()** nhả toàn bộ số lần vào monitor đích rồi **reacquire** trước khi trả về, còn notify()/notifyAll() **không tự nhả** monitor của thread đang phát tín hiệu.
- Hậu quả của IllegalMonitorStateException, NullPointerException, exception exits và những hiểu nhầm thường gặp.
- Mô hình happens-before, visibility, atomicity, lock identity, deadlock và nguyên tắc thiết kế lock scope.
- Biết dùng Java 17+, Thread.holdsLock, jcmd, jstack và JFR để quan sát, phân tích sự cố monitor contention.

**Phạm vi:** ngữ nghĩa Java SE/JLS/JVMS 17. Những chi tiết tối ưu hóa monitor của **HotSpot** như object header, lock records, monitor inflation, spin hay biased locking là implementation details và có thể đổi giữa các JDK versions. Không xem chúng là giao diện ổn định được Java language bảo đảm.

## 2. Monitor là gì?

Một object Java có **một monitor liên kết với chính object identity ấy**. Monitor có cơ chế khái niệm:

- **Owner:** thread hiện đang giữ monitor, hoặc chưa có owner.
- **Entry/hold count:** số lần owner đã acquire monitor nhưng chưa release tương ứng.
- **Entry contention:** các threads khác muốn acquire cùng monitor có thể phải chờ.
- **Wait set:** tập các threads đã gọi Object.wait() hợp lệ trên object đó và đang chờ notification/interrupt/timeout/spurious wakeup theo quy tắc Java.

Mô hình:

~~~text
                Monitor liên kết với object LOCK
              +--------------------------------------+
 Thread T1 -->| Owner: T1                            |
              | Entry count: 2                       |
              | Wait set: {...}                      |
              +--------------------------------------+
                   ^
                   |
 Thread T2 --------+-----> BLOCKED nếu T2 muốn lock LOCK

T1 gọi synchronized(LOCK) tiếp:
   T1 đã là owner -> entry count 2 -> 3, không tự block.

T1 thoát một synchronized:
   entry count 3 -> 2, vẫn giữ monitor.

T1 thoát đủ số lần:
   entry count 1 -> 0, không còn owner.
   Các thread khác mới có thể tranh quyền vào.
~~~

**Entry count là mô hình ngữ nghĩa**, không phải một trường int có public getter trên java.lang.Object. Các JVM có thể biểu diễn monitor ownership/reentrancy khác nhau ở native data structures; Java chỉ cung cấp behavior đúng.

### 2.1. Monitor gắn với object, không tự động gắn với “dữ liệu quan trọng”

~~~java
// Mã minh họa trong method:
Object a = new Object();
Object b = new Object();
synchronized (a) {
    // Sở hữu monitor của a; chưa hề sở hữu monitor b.
}
~~~

Cùng loại **Object**, nhưng **a != b** nên là hai monitor độc lập. Nếu một thread đồng bộ trên a còn thread khác đồng bộ trên b, chúng không chặn lẫn nhau chỉ vì dùng keyword synchronized.

Điều này rất quan trọng khi thiết kế private lock fields và khi đánh giá synchronized instance/static methods.

### 2.2. Mỗi monitor chỉ có một owner tại một thời điểm

Khi T1 đang sở hữu monitor M với hold count dương, T2 không thể đồng thời trở thành owner của M. Nhưng T1 vẫn có thể reenter M. Quy tắc này tạo **mutual exclusion cho critical sections dùng cùng M**.

Không có nghĩa mọi dữ liệu của object sẽ được tự động bảo vệ. Nếu thread khác truy cập một mutable field **không qua cùng monitor hoặc cơ chế synchronization tương đương**, có thể có data race.

## 3. Ba dạng synchronized trong Java

### 3.1. Instance synchronized method

~~~java
final class Counter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
~~~

Monitor được sử dụng là **this**, tức instance Counter cụ thể. Với:

~~~java
Counter first = new Counter();
Counter second = new Counter();
~~~

Thread khóa first và thread khác khóa second có thể chạy đồng thời vì đây là hai object monitors khác nhau. Hai threads cùng gọi first.increment() thì phải tranh monitor của first.

**Synchronized instance method không tự bảo vệ static field bằng một global class lock.** Nó dùng monitor **this**.

### 3.2. Static synchronized method

~~~java
final class GlobalCounter {
    private static int value;

    public static synchronized void increment() {
        value++;
    }
}
~~~

Monitor được sử dụng là **GlobalCounter.class**, tức Class mirror object biểu diễn runtime class **GlobalCounter** được định nghĩa bởi class loader tương ứng.

Vì vậy **static synchronized** không tranh chính monitor của một instance GlobalCounter thông thường. Một instance synchronized method và một static synchronized method của cùng class sử dụng **hai monitor khác nhau**; chúng không bảo vệ lẫn nhau chỉ do cùng có synchronized.

**Lưu ý class loaders:** hai runtime classes có cùng binary name nhưng do hai defining class loaders khác nhau định nghĩa có thể có hai Class objects, hai static states và hai monitors riêng biệt.

### 3.3. Synchronized statement/block

~~~java
final class Ledger {
    private final Object lock = new Object();
    private long balance;

    void add(long amount) {
        synchronized (lock) {
            balance += amount;
        }
    }

    long balance() {
        synchronized (lock) {
            return balance;
        }
    }
}
~~~

Ở đây lock object là **private final lock**, không phải Ledger.this. Đây thường là cách tốt để hạn chế code bên ngoài vô tình acquire monitor bảo vệ internal state. Tất cả truy cập balance liên quan phải tuân cùng synchronization policy.

**final chỉ cố định tham chiếu lock field**, không biến những fields khác thành thread-safe. Mọi reads/writes của state được bảo vệ cần phối hợp đúng monitor.

### 3.4. Bảng so sánh

| Cú pháp | Monitor thực sự acquire | Loại code | Ghi nhớ |
| --- | --- | --- | --- |
| **synchronized void m()** | this | Instance method | Mỗi instance có monitor riêng |
| **static synchronized void m()** | DefiningClass.class | Static method | Không phải monitor của instance |
| **synchronized (this) { ... }** | this | Statement/block | Có thể reenter với instance synchronized method |
| **synchronized (lock) { ... }** | object được biểu thức lock tham chiếu | Statement/block | Phải dùng cùng object identity |
| **synchronized (SomeClass.class) { ... }** | Class mirror object | Statement/block | Có thể phối hợp với static synchronized của class ấy |

## 4. Synchronized là reentrant: quy tắc vào/ra monitor

Giả sử T1 đang ở:

~~~java
synchronized (lock) {
    // Lần acquire đầu tiên.
    synchronized (lock) {
        // T1 lại acquire đúng cùng monitor.
    }
}
~~~

T1 không cần chờ chính nó release lock lần đầu. Một mô hình entry count:

~~~text
Ban đầu:                owner = none; count = 0

T1 vào outer block:      owner = T1;   count = 1
T1 vào inner block:      owner = T1;   count = 2
T1 thoát inner block:    owner = T1;   count = 1
T1 thoát outer block:    owner = none; count = 0
~~~

Chỉ khi **count về 0**, T1 mới nhả quyền sở hữu hoàn toàn. Không có semantic guarantee về fairness hoặc thứ tự thread tiếp theo nhận monitor.

### 4.1. Reentrancy qua chuỗi lời gọi phương thức

~~~java
final class BankAccount {
    private long balance;

    public synchronized void deposit(long amount) {
        validate(amount);
        applyDeposit(amount);
    }

    private synchronized void applyDeposit(long amount) {
        balance += amount;
    }

    private synchronized void validate(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
    }

    public synchronized long getBalance() {
        return balance;
    }
}
~~~

**deposit**, **validate** và **applyDeposit** cùng lock **this**. Khi deposit đang sở hữu monitor, nó có thể gọi validate rồi applyDeposit vì **chính thread ấy là owner**. Mỗi lần vào một synchronized method có accounting entry/exit theo ngữ nghĩa, nhưng không deadlock chỉ vì gọi nested synchronized methods trên cùng receiver.

**Không hiểu nhầm:** reentrancy chỉ miễn block cho **chính owner thread trên cùng monitor**. Thread T2 vẫn phải chờ.

### 4.2. Reentrancy khác recursion

**Recursion** nghĩa là method tự gọi lại; **reentrancy của lock** nghĩa là cùng thread có thể acquire lại cùng lock. Có thể xảy ra một cái mà không có cái kia:

- Hai synchronized methods khác nhau trên cùng object gọi nhau: **lock reentrancy**, không phải recursion.
- Recursive pure function không dùng synchronized: recursion nhưng không dùng monitor.
- Recursive synchronized method: cả recursion và lock reentrancy.
- Hai lock objects khác nhau trong nested blocks: nested locking nhưng không reenter **cùng** monitor.

## 5. Java 17 runnable demo #1: chứng minh tái nhập

Tạo file **ReentrantMonitorDemo.java**:

~~~java
public class ReentrantMonitorDemo {
    static final class Service {
        private int count;

        synchronized void outer() {
            inner(); // Reenter this monitor.
            synchronized (this) {
                inner(); // Another nested reentrance.
            }
        }

        private synchronized void inner() {
            if (!Thread.holdsLock(this)) {
                throw new AssertionError("monitor not held");
            }
            count++;
        }

        synchronized int getCount() {
            return count;
        }
    }

    public static void main(String[] args) {
        Service service = new Service();

        System.out.println("before="
                + Thread.holdsLock(service));

        synchronized (service) {
            System.out.println("inside="
                    + Thread.holdsLock(service));
            service.outer();
        }

        System.out.println("after="
                + Thread.holdsLock(service));
        System.out.println("count=" + service.getCount());
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ReentrantMonitorDemo.java
java ReentrantMonitorDemo
~~~

**Stdout chính xác:**

~~~text
before=false
inside=true
after=false
count=2
~~~

Đường đi:

1. Ở main trước block, thread chưa sở hữu Service monitor.
2. Vào synchronized(service), owner main, count khái niệm = 1.
3. Gọi **service.outer()** là synchronized instance method, reenter cùng service monitor.
4. **outer()** gọi **inner()**, tiếp tục reenter monitor; Thread.holdsLock(this) trả true.
5. Vào synchronized(this) ngay trong outer, sau đó lại gọi inner(): vẫn là owner thread, không bị tự khóa.
6. Những scopes/methods thoát theo thứ tự ngược; ngoài block main không còn giữ monitor.
7. inner được gọi đúng hai lần, count=2.

**Thread.holdsLock(Object obj)** chỉ trả **boolean** thread hiện tại có giữ monitor obj không; nó không trả hold count, không kiểm tra monitor owner của thread khác và không phải tool đo lock contention.

## 6. Một monitor dùng cho nhiều phương thức, nhưng không tự khóa toàn bộ object

Một bug điển hình:

~~~java
final class Box {
    private int value;

    synchronized void increment() {
        value++;
    }

    int unsafeRead() {
        return value;
    }
}
~~~

**increment** khóa this nhưng **unsafeRead** không khóa hoặc dùng visibility mechanism khác. Nếu một thread đọc trong khi thread khác ghi, đây có thể là **data race**. Synchronized không tự áp dụng bảo vệ cho mọi access tới fields của object.

Sửa một cách đơn giản:

~~~java
synchronized int safeRead() {
    return value;
}
~~~

Đây là **một đoạn method để thêm vào Box**, không phải file Java độc lập. Cả increment và safeRead đều acquire monitor của cùng Box instance.

### 6.1. Một field protected bởi hai locks khác nhau không đủ

~~~java
private final Object writeLock = new Object();
private final Object readLock = new Object();
private int value;

void update() {
    synchronized (writeLock) {
        value++;
    }
}

int read() {
    synchronized (readLock) {
        return value;
    }
}
~~~

Dù cả hai methods đều có synchronized blocks, **writeLock != readLock**. Chúng không thiết lập mutual exclusion/happens-before qua cùng monitor. Đây là code **minh họa bug**, không phải một class độc lập hoàn chỉnh. Cần sử dụng **cùng lock** hoặc một chiến lược Java concurrency đúng khác.

## 7. Java 17 runnable demo #2: an toàn tăng đếm với nhiều threads

Tạo file **SynchronizedCounterDemo.java**:

~~~java
public class SynchronizedCounterDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            doIncrement(); // Reentrant synchronized call.
        }

        private synchronized void doIncrement() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();
        Thread[] threads = new Thread[4];

        for (int t = 0; t < threads.length; t++) {
            threads[t] = new Thread(() -> {
                for (int i = 0; i < 5_000; i++) {
                    counter.increment();
                }
            });
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("count=" + counter.get());
        System.out.println("expected=" + (4 * 5_000));
        System.out.println("correct="
                + (counter.get() == 4 * 5_000));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 SynchronizedCounterDemo.java
java SynchronizedCounterDemo
~~~

**Stdout chính xác nếu chương trình hoàn thành bình thường:**

~~~text
count=20000
expected=20000
correct=true
~~~

Giải thích:

- Bốn threads, mỗi thread gọi 5.000 lần increment.
- **increment()** acquire Counter.this và reenter khi gọi **doIncrement()**; cùng owner thread được phép thực thi.
- Phép **value++** được bảo vệ bởi một monitor duy nhất nên không có hai threads cùng sửa biến theo hai critical sections chồng nhau.
- **Thread.join()** chờ tất cả worker kết thúc; theo JMM, hoạt động trong thread được join happens-before thread khác phát hiện việc join hoàn thành thành công.
- **counter.get()** còn acquire monitor tương ứng, nên đọc sau completion an toàn.
- Thứ tự chạy threads không xác định, nhưng tổng kết quả sau join là xác định.

**Không dùng code này để chứng minh monitor scheduling công bằng.** Thread order, số lần bị BLOCKED và elapsed runtime thay đổi qua các lần chạy.

## 8. Synchronized method vs monitorenter/monitorexit trong class file

Có hai cách mã hóa đồng bộ hóa quan trọng trong JVMS.

### 8.1. Synchronized statement

~~~java
void work(Object lock) {
    synchronized (lock) {
        System.out.println("work");
    }
}
~~~

Java compiler thông thường sinh bytecode có **monitorenter** và **monitorexit**, cùng **exception handler** để đảm bảo thoát monitor khi exception đi qua block. Conceptually:

~~~text
aload lock
monitorenter
  ...
monitorexit
goto end

exceptionHandler:
  monitorexit
  athrow

end:
  return
~~~

Sơ đồ lược bỏ stack/locals chính xác, offsets và exception tables; không phải javap output cố định. Điều đúng theo JVMS là **monitorenter** tăng entry count nếu thread đã own monitor, còn **monitorexit** giảm count; khi về 0 owner được nhả.

### 8.2. Synchronized method

~~~java
synchronized void task() {
    System.out.println("task");
}
~~~

Một synchronized method trong class file mang flag **ACC_SYNCHRONIZED**. JVM xử lý monitor acquire/release **implicitly** khi invoke/return/abrupt completion của method; không nhất thiết sinh monitorenter và monitorexit trong bytecode method body.

**Điểm rất hay bị dạy sai:** “Mọi synchronized method sẽ có cặp monitorenter/monitorexit trong javap -c”. Với synchronized method thông thường, hãy nhìn **ACC_SYNCHRONIZED**, không đòi phải thấy hai opcodes trong method instructions.

### 8.3. Cách quan sát bytecode

Sau khi biên dịch file ReentrantMonitorDemo.java:

~~~bash
javap -c -v 'ReentrantMonitorDemo$Service'
~~~

Cú pháp quotes phù hợp terminal Unix-like. Trên PowerShell, single quote quanh class name có dấu $ cũng giúp tránh variable expansion. Xem phần **flags: ACC_SYNCHRONIZED** cho methods outer/inner/getCount và **monitorenter/monitorexit** quanh explicit synchronized(this) block.

**Lưu ý:** javap chỉ cho thấy Java bytecode/class-file metadata, không tiết lộ nguyên trạng HotSpot native lightweight lock records hay CPU-level locking instructions do JIT sinh.

## 9. Java Memory Model: monitor không chỉ loại trừ lẫn nhau

Theo JLS §17.4.5, một **unlock action trên monitor M synchronizes-with mỗi lock action tiếp theo trên M**, tạo quan hệ **happens-before**.

Ví dụ:

~~~java
final class SharedState {
    private final Object lock = new Object();
    private int data;

    void publish() {
        synchronized (lock) {
            data = 42;
        } // unlock lock
    }

    int observe() {
        synchronized (lock) { // lock cùng object
            return data;
        }
    }
}
~~~

Nếu thread T1 hoàn thành **publish()** trước khi thread T2 acquire cùng lock để chạy **observe()**, T2 có quan hệ happens-before thích hợp để nhìn cập nhật 42, giả định không có mutation khác và object được sử dụng/publication phù hợp.

### 9.1. Acquire và release semantics

Trực giác:

- **Unlock/release**: publish những writes đã xảy ra trước đó qua synchronization ordering.
- **Subsequent lock/acquire trên cùng M**: sau khi acquire, thread tiếp theo có visibility phù hợp của các writes trước unlock.
- Những accesses phải thực sự được tổ chức theo **cùng monitor object**.
- Synchronization còn đặt constraints lên compiler/CPU reordering để giữ đúng JMM.

**Happens-before không đồng nghĩa “mọi writes trong mọi threads tức thời visible khi synchronized bất kỳ object nào”.** Nếu writer dùng lockA, reader dùng lockB, chỉ hai locks khác nhau chưa cho quan hệ monitor happens-before giữa hai thao tác.

### 9.2. Synchronized có tính chất atomicity ở critical section

Khi **value++** diễn ra trong synchronized(lock) và mọi threads khác cũng theo cùng lock để truy cập state, mutual exclusion làm cho read-modify-write không bị xen kẽ với critical section khác trên cùng monitor.

Nhưng một synchronized method bảo vệ một thao tác **không tự biến chuỗi hai lần gọi riêng rẽ thành transaction**:

~~~java
if (account.getBalance() > 0) {
    account.withdraw(1);
}
~~~

Ngay cả khi getBalance và withdraw từng là synchronized, một thread khác có thể xen giữa hai lời gọi. Nếu cần atomic check-then-act, gộp cả hai trong **một vùng synchronized dùng cùng monitor**, hoặc định nghĩa method nghiệp vụ atomic.

### 9.3. Reentrant monitor không phải distributed lock

Monitor của Java process chỉ điều phối threads trong cùng runtime object model. Nó không tự bảo vệ một bản ghi trong DB khỏi process khác, không thay transaction isolation và không phải hệ distributed locking.

## 10. Khi nào một thread bị BLOCKED?

Giả sử T1 đã acquire monitor lock:

~~~text
T1: synchronized(lock) {
        // xử lý kéo dài
    }

T2: synchronized(lock) {
        // phải chờ T1 release hoàn toàn
    }
~~~

T2 muốn vào critical section sử dụng cùng monitor có thể được quan sát ở trạng thái Java **Thread.State.BLOCKED**. Một thread đang **BLOCKED** chờ monitor entry **không phải** thread đã acquire monitor.

Các điểm khác:

- T1 có thể reenter trong khi count dương.
- T2 chỉ có thể acquire khi monitor hoàn toàn free, không phải khi T1 chỉ thoát một nested block.
- JVM không bảo đảm FIFO fairness.
- Java intrinsic monitor entry không cung cấp cùng public **tryLock(timeout)**/**lockInterruptibly()** như ReentrantLock.
- **Thread.interrupt()** không bảo đảm khiến một thread đang chờ enter intrinsic monitor ngay lập tức ném InterruptedException rồi bỏ việc acquire.

### 10.1. Object.wait() khác BLOCKED-to-enter

**BLOCKED:** muốn vào synchronized region nhưng monitor hiện do thread khác sở hữu.

**WAITING:** sau khi đã sở hữu monitor, thread có thể gọi **wait()** hợp lệ, **nhả monitor ấy** rồi ở wait set cho đến notification/interrupt/spurious wakeup.

**TIMED_WAITING:** có thể xảy ra khi gọi **wait(timeout)** hoặc **sleep(timeout)**; nhưng sleep **không nhả monitor** mà thread đang giữ.

Thread state là **snapshot**; nó có thể thay đổi rất nhanh. Không định nghĩa thuật toán correctness bằng việc lặp getState() và chờ đúng tên state.

## 11. wait()/notify()/notifyAll(): phối hợp trên cùng monitor

Java cung cấp các instance methods trong **Object**:

- **wait()**, **wait(long)**, **wait(long,int)**.
- **notify()**.
- **notifyAll()**.

Thread gọi các phương thức này phải **đang sở hữu monitor của chính receiver object**. Nếu không, thường ném **IllegalMonitorStateException**.

Ví dụ:

~~~java
final Object lock = new Object();

synchronized (lock) {
    lock.wait();
}
~~~

Đây là mã **minh họa**, không phải ví dụ nên chạy nguyên xi: nếu không có tín hiệu/interrupt và không spurious wakeup, có thể chờ vô hạn. Phương thức cũng cần xử lý **InterruptedException**.

### 11.1. wait() thật sự làm gì?

Theo JLS §17.2:

1. Nếu thread không sở hữu monitor receiver, ném IllegalMonitorStateException.
2. Thread được đưa vào **wait set** của receiver object.
3. JVM thực hiện số lần **unlock phù hợp với mọi lần acquire chưa cân bằng trên chính monitor receiver**.
4. Thread chờ đến notification/interrupt/timeout/spurious wakeup theo ngữ nghĩa.
5. Khi được remove khỏi wait set, thread phải **reacquire cùng monitor với số lần sở hữu trước đó** trước khi việc wait hoàn tất/trả về hoặc ném InterruptedException thích hợp.

**Đặc biệt:** nếu thread sở hữu monitor m hai lần do nested synchronized(m), gọi **m.wait()** giải phóng **cả hai levels** cho m. Nó không chỉ giảm count 2→1, nếu thế notifier thread sẽ không thể acquire m và mô hình wait/notify dễ deadlock.

### 11.2. wait() không nhả những monitor khác

~~~java
synchronized (lockA) {
    synchronized (lockB) {
        lockB.wait();
    }
}
~~~

Thread có thể tạm nhả các acquisition của **lockB**, nhưng vẫn giữ **lockA** khi wait. Do đó có thể gây deadlock nếu notifier phải acquire lockA trước khi có thể notify lockB.

**Quy tắc thiết kế:** tránh giữ một lock không liên quan qua lời gọi wait trên monitor khác, trừ khi đã phân tích lock ordering rất kỹ.

### 11.3. notify()/notifyAll() không nhả monitor ngay

~~~text
T1 owns monitor M:
  synchronized(M) {
      condition = true;
      M.notifyAll();        // đưa waiters khỏi wait set
      doMoreWork();         // T1 vẫn là owner
  }                        // T1 unlock ở đây

T2 đang chờ M:
  M.wait() không thể hoàn tất return
  cho đến khi T2 reacquire M sau khi T1 release.
~~~

Notify là **tín hiệu**, không phải thao tác chuyển giao monitor tức thời. Sau notifyAll(), các waiters vẫn phải **tranh lại quyền acquire** cùng monitor. Java không đảm bảo thread cụ thể nào nhận lock trước.

### 11.4. Luôn wait trong vòng while kiểm tra điều kiện

~~~java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Chỉ tiếp tục nếu condition thực sự đúng.
}
~~~

Vì:

- **Spurious wakeups** có thể xảy ra.
- notifyAll có thể đánh thức nhiều threads nhưng chỉ một thread lấy resource.
- Condition có thể đã thay đổi trước khi waiter reacquire lock.
- notify() chỉ chọn một waiter bất kỳ, không hứa waiter mong muốn.
- InterruptedException cần được xử lý đúng theo contract ứng dụng.

**Không** dùng if thay while khi correctness phụ thuộc predicate. Cũng không dùng Thread.sleep() thay wait() trong critical section: sleep không release monitor.

## 12. Java 17 runnable demo #3: wait giải phóng hết reentrant holds

Tạo file **ReentrantWaitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class ReentrantWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        boolean[] ready = {false};
        boolean[] reacquired = {false};

        Thread waiter = new Thread(() -> {
            synchronized (lock) {
                synchronized (lock) {
                    entered.countDown();
                    while (!ready[0]) {
                        try {
                            lock.wait();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            return;
                        }
                    }
                    reacquired[0] = Thread.holdsLock(lock);
                }
            }
        });

        waiter.start();
        entered.await();

        synchronized (lock) {
            ready[0] = true;
            lock.notifyAll();
        }

        waiter.join();
        System.out.println("condition=" + ready[0]);
        System.out.println("reacquired=" + reacquired[0]);
        System.out.println("completed=" + !waiter.isAlive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 ReentrantWaitDemo.java
java ReentrantWaitDemo
~~~

**Stdout chính xác trong lần chạy bình thường, không external interrupt:**

~~~text
condition=true
reacquired=true
completed=true
~~~

Lý do:

1. Waiter acquire cùng **lock** hai lần bằng nested synchronized blocks.
2. Waiter gọi entered.countDown() khi đang sở hữu lock, rồi kiểm tra ready=false và gọi lock.wait().
3. **wait() tạm release toàn bộ 2 reentrant holds** của lock. Main có thể acquire lock, thiết lập ready=true và notifyAll().
4. Main phải thoát synchronized(lock) để thực sự release; notifier **không trao monitor ngay** ở notifyAll().
5. Waiter reacquire monitor đến đúng depth cần thiết, kiểm tra vòng while; ready=true nên ghi nhận Thread.holdsLock(lock)==true.
6. Waiter thoát nested blocks, rồi main join chờ waiter hoàn tất.
7. Không cần dùng Thread.sleep để phối hợp timing; CountDownLatch chỉ giúp main biết waiter đã đến vị trí cần thiết.

**Nếu có spurious wakeup:** waiter kiểm tra lại while, tiếp tục wait khi ready=false nên không sai. Nếu bị thread khác interrupt bất thường, demo có nhánh return; stdout được mô tả cho môi trường thông thường không external interruption.

**Lưu ý:** CountDownLatch không thay thế monitor protocol trong demo. Chính wait() nhả monitor để main có thể acquire và phát điều kiện; latch chỉ là điểm đồng bộ bảo đảm thứ tự bắt đầu thí nghiệm.

## 13. IllegalMonitorStateException và null monitor

### 13.1. wait/notify không giữ đúng monitor

~~~java
Object lock = new Object();
lock.notifyAll(); // Không sở hữu lock monitor -> IllegalMonitorStateException.
~~~

Nếu code chỉ đang giữ **monitor khác**:

~~~java
Object a = new Object();
Object b = new Object();

synchronized (a) {
    b.notifyAll(); // Vẫn sai: chưa sở hữu monitor của b.
}
~~~

Phải gọi wait/notify trên **chính object mà thread đã acquire**. Giữ monitor a không cho quyền gửi notification trên b.

### 13.2. synchronized(null)

~~~java
Object lock = null;

synchronized (lock) {
    // Không được vào: NullPointerException.
}
~~~

Theo JVMS, **monitorenter** với null object reference ném NullPointerException. Đây không phải tình huống “lock rỗng thì cứ chạy không đồng bộ”.

### 13.3. Exception trong synchronized có làm rò monitor?

Java bảo đảm synchronized statement/method thực hiện monitor release phù hợp khi kết thúc **bình thường hoặc abrupt**, bao gồm exception propagation. Compiler tạo exception path cho synchronized block; method có ACC_SYNCHRONIZED được VM xử lý implicit release.

~~~java
void fail(Object lock) {
    synchronized (lock) {
        throw new IllegalStateException("boom");
    } // monitor được thoát trong quá trình exception propagation.
}
~~~

Mã minh họa; một runtime exception không tự “khoá monitor vĩnh viễn”. Tuy nhiên một thread bị treo vô hạn **bên trong** synchronized (không thoát block/method) vẫn có thể giữ lock rất lâu.

### 13.4. Thread.stop() và các unsafe threading APIs

Không dùng các API lịch sử như **Thread.stop()** để “ép thread đang giữ monitor nhả lock”. Cơ chế dừng thô bạo có thể bỏ qua object invariants và làm shared state hỏng. Dùng cancellation/cooperative interruption với lifecycle rõ ràng.

## 14. Java 17 runnable demo #4: static lock và instance lock là khác nhau

Tạo **MonitorIdentityDemo.java**:

~~~java
public class MonitorIdentityDemo {
    static synchronized boolean classOwned() {
        return Thread.holdsLock(MonitorIdentityDemo.class);
    }

    synchronized boolean instanceOwned() {
        return Thread.holdsLock(this);
    }

    public static void main(String[] args) {
        MonitorIdentityDemo instance =
                new MonitorIdentityDemo();

        System.out.println("classMethod="
                + classOwned());
        System.out.println("instanceMethod="
                + instance.instanceOwned());

        synchronized (MonitorIdentityDemo.class) {
            System.out.println("classBlock="
                    + Thread.holdsLock(MonitorIdentityDemo.class));
            System.out.println("instanceInClassBlock="
                    + Thread.holdsLock(instance));
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 MonitorIdentityDemo.java
java MonitorIdentityDemo
~~~

**Stdout:**

~~~text
classMethod=true
instanceMethod=true
classBlock=true
instanceInClassBlock=false
~~~

Giải thích:

- classOwned() là **static synchronized**, nên method giữ **MonitorIdentityDemo.class** khi gọi holdsLock.
- instanceOwned() giữ **this**, là instance monitor.
- Main acquire Class monitor; điều đó không tự acquire instance monitor.
- Thí nghiệm chỉ dùng một thread để chứng minh **object identity** của monitor; nó không chứng minh thứ tự scheduling giữa threads.

## 15. Những vấn đề về fairness, scheduling và interruption

**Intrinsic monitors không có hợp đồng công bằng FIFO** cho tất cả waiters. Khi monitor được release, JVM/OS có thể chọn thread nào acquire tiếp theo dựa trên scheduling/implementation.

Những điều không được giả định:

- Thread T2 chờ trước T3 thì chắc chắn T2 sẽ nhận lock trước.
- notify() sẽ chọn thread đã wait lâu nhất.
- Thread.interrupt() sẽ luôn làm một thread đang BLOCKED chờ monitor entry dừng chờ và ném InterruptedException.
- Thread.yield() sẽ làm monitor bị release.
- Thread.sleep() bên trong synchronized sẽ nhả monitor.
- Synchronized block có built-in timeout parameter tương đương tryLock(timeout).

### 15.1. ReentrantLock khác intrinsic synchronized

**java.util.concurrent.locks.ReentrantLock** cũng tái nhập được nhưng có các API bổ sung:

- **lock()** và **unlock()**.
- **tryLock()** và **tryLock(timeout)**.
- **lockInterruptibly()**.
- Có thể tạo fair-mode lock theo API, dù fairness policy có trade-offs.
- Condition objects hỗ trợ nhiều wait sets logic.
- **getHoldCount()** và một số introspection capabilities.

Ngược lại intrinsic synchronized có cú pháp ngắn, release tự động theo lexical scope và monitor wait/notify tích hợp. **Không coi ReentrantLock luôn hiệu năng hơn synchronized**; JVM có nhiều tối ưu intrinsic monitors.

Ví dụ dùng ReentrantLock đúng cách:

~~~java
// Mã minh họa, đã khai báo Lock lock:
lock.lock();
try {
    // Critical section.
} finally {
    lock.unlock();
}
~~~

Với ReentrantLock, **unlock() là thao tác lập trình viên phải gọi**, nên nếu quên finally có thể gây leak lock ownership. Intrinsic synchronized tự exit khi block kết thúc.

## 16. Deadlock: reentrancy không chữa được khóa chéo

Reentrancy ngăn **self-deadlock khi cùng owner thread acquire lại cùng monitor**, nhưng không ngăn **deadlock giữa nhiều monitors**.

Ví dụ kịch bản:

~~~text
T1:
  acquire monitor A
  attempt acquire B -> BLOCKED vì T2 giữ B

T2:
  acquire monitor B
  attempt acquire A -> BLOCKED vì T1 giữ A

Kết quả:
  T1 chờ B do T2 giữ
  T2 chờ A do T1 giữ
  -> Circular wait / deadlock
~~~

Đây là ví dụ conceptual, không nên cố chạy một chương trình deadlock vô hạn trên môi trường dùng chung.

### 16.1. Nested synchronized khác lock reentrancy

~~~java
synchronized (a) {
    synchronized (b) {
        // Giữ hai monitors a và b.
    }
}
~~~

Nếu a và b là hai objects khác nhau, đây là **nested multi-locking**, không phải **reenter cùng lock**. T2 khóa b rồi a có thể tạo lock-order inversion.

### 16.2. Cách phòng tránh deadlock

1. Thiết lập **thứ tự khóa toàn cục** và luôn acquire nhiều monitors cùng thứ tự.
2. Giữ critical sections ngắn, tránh I/O/blocking operations kéo dài trong synchronized.
3. Không gọi code bên ngoài không kiểm soát trong khi giữ monitor nếu callback có thể acquire các locks khác.
4. Giảm số monitors phải giữ đồng thời.
5. Nếu yêu cầu có timeout hoặc interruptible acquisition, cân nhắc ReentrantLock.tryLock/lockInterruptibly thay vì intrinsic monitor.
6. Dùng thread dump/JFR để xác định actual ownership, không đoán từ một source snippet.

### 16.3. Wait() trên monitor B khi vẫn giữ A có thể gây deadlock

~~~java
synchronized (a) {
    synchronized (b) {
        b.wait();
    }
}
~~~

Thread sẽ release B khi wait nhưng **vẫn giữ A**. Nếu notifier cần acquire A trước mới có thể notify B, hai threads có thể kẹt. Đây là một failure mode khác với việc owner reenter cùng monitor.

## 17. Khả năng visibility không mở rộng qua lock khác

Ví dụ thiết kế sai:

~~~java
final class WrongLockExample {
    private final Object writeLock = new Object();
    private final Object readLock = new Object();
    private int value;

    void set(int newValue) {
        synchronized (writeLock) {
            value = newValue;
        }
    }

    int get() {
        synchronized (readLock) {
            return value;
        }
    }
}
~~~

Dù cả hai methods dùng synchronized, chúng khóa **khác objects**. Java Memory Model không có monitor happens-before edge giữa unlock writeLock và lock readLock chỉ do cả hai là synchronized.

Sửa:

~~~java
final class RightLockExample {
    private final Object lock = new Object();
    private int value;

    void set(int newValue) {
        synchronized (lock) {
            value = newValue;
        }
    }

    int get() {
        synchronized (lock) {
            return value;
        }
    }
}
~~~

Với mọi thread tuân cùng lock discipline, get() đọc state được đồng bộ đúng. Nếu có code khác đọc value trực tiếp không đồng bộ, bảo đảm thread-safety tổng thể vẫn có thể bị phá.

### 17.1. synchronized trên String literal, boxed Integer, public lock

~~~java
synchronized ("LOCK_NAME") {
    // Không nên dùng interned public String làm private lock.
}
~~~

String literals có thể được interned/chia sẻ giữa code không liên quan; các thành phần khác có thể vô tình lock cùng monitor. Tương tự boxed values như Integer.valueOf(1) có thể được cache; các locks công khai tạo nguy cơ lock coupling khó kiểm soát.

Ưu tiên **private final Object lock = new Object()** cho dữ liệu nội bộ. Không dùng một object tạo mới **ngay trong mỗi lần method call** như synchronized(new Object()) nếu mục tiêu là phối hợp giữa các callers; mỗi object identity là monitor khác nhau.

### 17.2. Lock trên this: tiện nhưng public exposure

Instance synchronized method dùng **this**, nên bất kỳ code nào giữ được reference tới instance cũng có thể cố tình hoặc vô tình synchronized(instance). Khi thiết kế library/service internals, private lock object cho phép tránh lock bị chia sẻ bất ngờ giữa thành phần nội bộ và bên ngoài.

Tuy nhiên private lock chỉ có giá trị nếu mọi reads/writes relevant đều sử dụng đúng cùng lock; không phải một dấu hiệu magic thread-safe.

## 18. Hiệu năng của synchronized và JVM implementation

Trên HotSpot, monitor có thể được tối ưu hóa để uncontended locking rẻ. Những terms có thể gặp trong diagnostics/historical explanations:

- **Thin/lightweight locking**: cơ chế tối ưu uncontended monitor entry/exit tùy phiên bản.
- **Inflated monitor/ObjectMonitor**: implementation có thể sử dụng cấu trúc monitor nặng hơn khi contention/waiting hoặc conditions khác.
- **Lock coarsening/elision**: compiler có thể tối ưu synchronized operations khi chứng minh hợp lệ.
- **Biased locking**: tối ưu lịch sử của HotSpot, đã bị tắt mặc định và deprecate từ JDK 15 theo JEP 374; không dạy nó là default behavior cho JDK 17.

**Không cố định** độ rộng object header bits, Monitor owner pointer hoặc thin-lock encoding theo một sơ đồ duy nhất cho JDK 17 và JDK 25. Những nội bộ này có thể thay đổi do cải tiến lightweight locking hoặc virtual-thread monitors.

### 18.1. Contention có thể tốn CPU và làm giảm scalability

Nếu 32 worker threads liên tục gọi synchronized trên **một global lock**, chỉ một thread có thể thực thi critical section tại thời điểm nhất định. Thời gian chờ có thể lớn ngay cả khi operation là một phép cộng nhỏ. Mục tiêu tuning hợp lý:

- Giảm contention bằng partition/sharding locks theo dữ liệu độc lập.
- Rút ngắn critical section.
- Tránh I/O/DB calls trong lock.
- Cân nhắc concurrent collections, atomics hoặc LongAdder cho counters theo semantics phù hợp.
- Benchmark throughput/tail latency trước và sau.

**Không thể tối ưu bằng cách bỏ synchronized** nếu yêu cầu mutual exclusion/visibility vẫn tồn tại. Hãy thay bằng một chiến lược đồng bộ hóa tương đương, không tạo data races.

### 18.2. Monitor reentrancy không có nghĩa mọi nested synchronized là miễn phí

Khi reenter cùng monitor trong code đã được JIT tối ưu, VM có thể tối ưu nhiều thao tác; nhưng vẫn có cost semantic/safepoint/deoptimization/monitor bookkeeping ở những điều kiện khác. Đừng giả định reentrant entry luôn có zero CPU cost hoặc luôn đắt như contended acquisition.

## 19. Quan sát monitor bằng Thread.holdsLock, jcmd, jstack và JFR

### 19.1. Thread.holdsLock

~~~java
Object lock = new Object();
System.out.println(Thread.holdsLock(lock)); // false ở thread chưa lock.
synchronized (lock) {
    System.out.println(Thread.holdsLock(lock)); // true.
}
~~~

Đoạn này chạy trong một method, đúng với thread hiện tại. API chỉ cho biết current thread owns object monitor hay không, **không trả recursion depth** và không trả thông tin về thread khác.

### 19.2. jcmd Thread.print

Trên HotSpot JDK 17, khi process đang chạy:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> Thread.print
~~~

Thay **<PID>** bằng PID thực; output có thể liệt kê Java thread states, monitor ownership/blocked-on details và thông tin deadlock theo tool/build. Dùng quyền phù hợp; output chứa stack traces và thông tin ứng dụng cần xử lý an toàn.

### 19.3. jstack

~~~bash
jstack <PID>
jstack -l <PID>
~~~

**-l** yêu cầu thêm lock-related information theo jstack implementation. Tùy JDK và cơ chế attach, jstack có thể không dùng được; trên JDK mới hơn, **jcmd Thread.print** thường là điểm bắt đầu thuận tiện.

Một thread dump có thể mô tả:

~~~text
Thread-1: BLOCKED (on object monitor)
    - waiting to lock <...> (a java.lang.Object)

Thread-2: RUNNABLE
    - locked <...> (a java.lang.Object)
~~~

Đây là **format minh họa**, không phải output cố định của một đoạn code. Khi thấy BLOCKED, tìm đúng object monitor và owner thread, rồi đối chiếu call stacks của cả hai.

### 19.4. Java Flight Recorder

JFR có những events phù hợp để quan sát monitor contention và wait durations khi được bật, ví dụ **jdk.JavaMonitorEnter**, **jdk.JavaMonitorWait** tùy JDK/recording profile.

Khởi chạy một ứng dụng thực có main:

~~~bash
java -XX:StartFlightRecording=filename=monitors.jfr,duration=30s,settings=profile MyMain
~~~

Dùng jfr CLI:

~~~bash
jfr summary monitors.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait monitors.jfr
~~~

**MyMain** và file name là ví dụ; ứng dụng có thể kết thúc trước duration. Event có thể vắng do recording settings/thresholds, không có contention đáng kể hoặc JVM configuration. Không nói “không có JavaMonitorEnter event” đồng nghĩa chương trình không bao giờ synchronized.

### 19.5. ThreadMXBean

Java management API **java.lang.management.ThreadMXBean** có phương thức lấy thread information, deadlock detection và monitor information ở những VM hỗ trợ. Ví dụ đọc toàn bộ stack traces có thể có overhead; nhớ rằng trạng thái thread/monitor là snapshots thay đổi liên tục.

### 19.6. Đo latency: chỗ nghẽn có phải monitor?

Nếu request latency tăng, hãy hỏi:

1. Có thread dump/JFR cho thấy nhiều threads **BLOCKED trên cùng object monitor** không?
2. Owner thread đang thực hiện công việc gì trong critical section?
3. Có owner đang chờ I/O, lock khác, hay gọi callback không kiểm soát?
4. Có monitor contention nhiều vì dùng một global singleton lock?
5. Có deadlock thực (circular waits) hay chỉ contention ngắn?
6. Có nhiều WAITING vì condition không được signal đúng?
7. Liệu vấn đề là GC/safepoint/CPU throttle chứ không phải monitor?
8. Có cần throughput optimization hay correctness bug fix?

Không chẩn đoán thread-safety chỉ từ việc đọc một file có keyword synchronized. Cần biết **object identity** và paths runtime.

## 20. Monitor và virtual threads: ghi chú phiên bản

**Java 17 chưa có virtual threads là tính năng chính thức**. Java 21 đưa virtual threads thành production feature theo JEP 444. Trong các JDK 21–23, virtual thread thực thi synchronized code có thể dẫn tới **carrier-thread pinning** khi blocking, giảm khả năng scale trong những tình huống nhất định.

**JDK 24 / JEP 491** cải thiện cơ chế monitor để virtual threads có thể **unmount** trong nhiều tình huống synchronized/monitor waiting thay vì bị pin như trước. Vì vậy:

- Không suy rằng mọi JDK dùng virtual threads đều có cùng synchronized pinning behavior.
- Không áp advice JDK 21–23 “tránh mọi synchronized để tránh pinning” nguyên xi cho JDK 24+.
- Vẫn cần giữ critical sections ngắn và tránh lock contention dù có virtual threads.
- Ngữ nghĩa **monitor ownership/reentrancy/JMM** dành cho Java code vẫn phải được bảo toàn qua những thay đổi implementation.

Thông tin này nhằm tránh diễn giải sai khi học tài liệu cũ; nó **không thay thế** nguyên lý synchronized của Java 17.

## 21. Những hiểu lầm phổ biến

1. **“synchronized khóa method name.”** Sai: nó acquire monitor cụ thể, thường là this hoặc Class object.
2. **“Mọi method synchronized trong cùng class dùng một lock duy nhất.”** Sai nếu instance methods trên các instances khác nhau hoặc static vs instance.
3. **“Thread gọi synchronized method rồi gọi synchronized method khác trên cùng object sẽ deadlock.”** Sai: monitor reentrant.
4. **“Monitor vào lại không cần track số lần sở hữu.”** Sai: phải cân bằng reentrant acquisitions.
5. **“Thoát inner synchronized nhả toàn bộ monitor.”** Sai nếu còn outer hold count.
6. **“Một thread khác có thể chen vào giữa hai nested synchronized của cùng owner.”** Không khi owner vẫn giữ monitor.
7. **“Thread.holdsLock trả recursion count.”** Sai: chỉ boolean current thread.
8. **“synchronized instance bảo vệ static field với global class monitor.”** Sai: khóa this.
9. **“static synchronized khóa mọi instances cùng class.”** Nó khóa Class monitor, không tự acquire instance monitors.
10. **“synchronized trên lockA bảo vệ reads dùng lockB.”** Sai: thiếu cùng-monitor synchronization.
11. **“Synchronized dùng một Object mới mỗi invocation sẽ làm các callers chặn nhau.”** Sai: object identities khác nhau.
12. **“Có synchronized keyword thì mọi field trong class luôn thread-safe.”** Sai: các accesses khác có thể data race.
13. **“unlock monitor A happens-before lock monitor B.”** Không chỉ vì hai monitors đều có synchronized; cần matching monitor hoặc HB edges khác.
14. **“Synchronized bảo đảm fairness FIFO.”** Sai: intrinsic monitor không có fairness guarantee.
15. **“Thread.sleep trong synchronized sẽ nhả monitor.”** Sai: sleep không nhả monitor.
16. **“Object.wait không nhả monitor.”** Sai: nhả **toàn bộ acquisitions của receiver monitor**.
17. **“wait trên B nhả tất cả monitors A/B mà thread đang giữ.”** Sai: chỉ receiver B.
18. **“notifyAll chuyển lock ngay cho waiter.”** Sai: notifier vẫn giữ monitor tới khi unlock.
19. **“notify() luôn chọn waiter chờ lâu nhất.”** Sai: không có lựa chọn thứ tự được bảo đảm.
20. **“if(condition) wait là đủ.”** Sai: dùng while predicate vì spurious wakeup/state race.
21. **“wait/notify có thể gọi khi không giữ monitor receiver.”** Sai: IllegalMonitorStateException.
22. **“synchronized(null) là no-op.”** Sai: NullPointerException.
23. **“Exception ném khỏi synchronized block làm monitor bị leak.”** Sai: release trên abrupt exit theo ngữ nghĩa.
24. **“Một synchronized method luôn sinh monitorenter/exit trong bytecode.”** Sai: dùng ACC_SYNCHRONIZED method flag.
25. **“monitorenter chỉ dùng cho non-reentrant locking.”** Sai: reentrant count là phần của instruction semantics.
26. **“Reentrancy tự ngăn deadlock trên hai monitors.”** Sai: A→B/B→A vẫn có thể deadlock.
27. **“Thread.interrupt sẽ bỏ chờ synchronized monitor entry ngay.”** Không theo quy tắc intrinsic lock.
28. **“Thread.State.WAITING và BLOCKED là một.”** Sai: waiting on condition vs monitor acquisition.
29. **“JIT implementation lock encoding là một phần Java SE API.”** Sai: VM implementation details.
30. **“Biased locking luôn mặc định bật trên Java 17.”** Sai: đã disabled-by-default từ JDK15.
31. **“GC/HotSpot cải tiến lock làm happens-before không cần nữa.”** Sai: JMM semantics giữ nguyên.
32. **“Bỏ synchronized sẽ luôn làm chương trình nhanh hơn.”** Sai nếu gây data races/corruption hoặc phải dùng cơ chế đồng bộ hóa khác tốn hơn.
33. **“Monitor là distributed lock bảo vệ DB qua nhiều JVMs.”** Sai.
34. **“Class loaders định nghĩa cùng binary name chia sẻ một Class monitor.”** Không nhất thiết; runtime class identity phụ thuộc defining loader.
35. **“wait sẽ trả về ngay khi nhận notify kể cả monitor còn bị notifier giữ.”** Sai: phải reacquire monitor trước.
36. **“Virtual threads ở Java 21 và Java 25 luôn có monitor pinning giống nhau.”** Sai: JDK24/JEP491 thay đổi đáng kể.

## 22. Bài tập có lời giải

**Câu 1.** Hai thread cùng gọi synchronized instance method trên **hai instances khác nhau**. Có tự chặn nhau không?

**Đáp án:** Không chỉ vì method cùng tên. Mỗi instance có monitor riêng.

**Câu 2.** Thread T1 vào synchronized(lock) rồi nested synchronized(lock). Entry count logic biến đổi thế nào?

**Đáp án:** 0→1→2, rồi thoát inner còn 1, thoát outer về 0.

**Câu 3.** synchronized static method lock gì?

**Đáp án:** DefiningClass.class, tức Class mirror object của runtime class.

**Câu 4.** synchronized instance method lock gì?

**Đáp án:** this, tức monitor của receiver instance.

**Câu 5.** Một static synchronized và một instance synchronized method cùng class có thể chạy song song không?

**Đáp án:** Có thể, vì Class monitor khác instance monitor, trừ khi code dùng thêm locks khác.

**Câu 6.** Khi đang sở hữu monitor lock, gọi another synchronized method của cùng object có bị tự deadlock không?

**Đáp án:** Không; monitor tái nhập được với owner thread ấy.

**Câu 7.** Thread.holdsLock(lock) trả gì nếu current thread đã reenter lock 3 lần?

**Đáp án:** true, không trả 3.

**Câu 8.** Synchronized block nào được biểu diễn bằng monitorenter/monitorexit? Synchronized method dùng gì?

**Đáp án:** Synchronized statement dùng monitorenter/exit; synchronized method dùng ACC_SYNCHRONIZED và VM implicit monitor entry/exit.

**Câu 9.** T1 giữ M hai lần rồi gọi M.wait(). T1 tạm nhả mấy lần?

**Đáp án:** Tạm release toàn bộ hai acquisitions trên M; khi returning, reacquire tới cùng hold depth.

**Câu 10.** T1 giữ A và B rồi gọi B.wait(). Monitor A có được nhả không?

**Đáp án:** Không; chỉ B được release bởi wait trên B.

**Câu 11.** T1 gọi notifyAll() trong synchronized(lock). T2 có lập tức chạy trong critical section trước khi T1 thoát không?

**Đáp án:** Không; T2 phải reacquire monitor khi T1 release đủ holds.

**Câu 12.** Tại sao while (!condition) lock.wait() tốt hơn if?

**Đáp án:** Vì spurious wakeups hoặc condition thay đổi trước khi waiter reacquire; cần kiểm tra lại predicate.

**Câu 13.** Gọi Object.notify() khi không giữ monitor của receiver dẫn tới gì?

**Đáp án:** IllegalMonitorStateException.

**Câu 14.** synchronized(null) dẫn tới gì?

**Đáp án:** NullPointerException trên monitor entry.

**Câu 15.** synchronized block ném RuntimeException có luôn giữ monitor mãi không?

**Đáp án:** Không. Ngữ nghĩa synchronized bảo đảm unlock trên normal/abrupt completion.

**Câu 16.** Thread đang BLOCKED chờ monitor khác gì WAITING sau wait()?

**Đáp án:** BLOCKED chưa acquire monitor; WAITING sau wait() đã release receiver monitor và chờ event/notification.

**Câu 17.** Dùng synchronized(lockA) viết state, synchronized(lockB) đọc state. Có HB monitor edge trực tiếp không?

**Đáp án:** Không nếu lockA và lockB khác identity, và không có synchronization khác bảo đảm.

**Câu 18.** Một luồng giữ A chờ B và luồng khác giữ B chờ A. Reentrancy giải được không?

**Đáp án:** Không; deadlock do hai owners và circular wait trên hai monitors khác nhau.

**Câu 19.** Vì sao synchronized("shared") không phải lock private tốt?

**Đáp án:** String literal có thể interned/share; các phần code khác có thể lock cùng object ngoài ý muốn.

**Câu 20.** Khi nào nên dùng private final Object lock?

**Đáp án:** Khi muốn che giấu lock identity để chỉ code nội bộ sử dụng cùng monitor bảo vệ một state.

**Câu 21.** JDK17 biased locking có còn mặc định bật không?

**Đáp án:** Không, JEP374 đã disable-by-default và deprecate từ JDK15.

**Câu 22.** Java 21–23 virtual threads có khả năng pin carrier với synchronized. JDK24 thay đổi gì?

**Đáp án:** JEP491 cải thiện khả năng unmount virtual threads khi monitor blocked/waiting, giảm pinning.

**Câu 23.** Tại sao Thread.join() giúp demo counter có output xác định?

**Đáp án:** Main chờ bốn threads thực hiện đủ operations; thread completion/join cung cấp HB phù hợp.

**Câu 24.** Có thể dùng một synchronized method để bảo vệ DB transaction giữa hai JVM processes không?

**Đáp án:** Không; monitor chỉ điều phối threads theo một JVM runtime, cần database/distributed coordination riêng.

**Câu 25.** ReentrantWaitDemo chứng minh điều gì vượt quá Thread.holdsLock?

**Đáp án:** Cho thấy thread giữ cùng monitor hai lần vẫn có thể wait, notifier acquire monitor rồi phát tín hiệu, waiter reacquire trước khi tiếp tục. holdsLock chỉ xác nhận owner, không đo được depth.

## 23. Quy trình thiết kế và debug monitor

1. **Xác định state cần bảo vệ** và những threads nào có thể truy cập đồng thời.
2. **Chọn đúng lock identity**: this, Class monitor hoặc private final Object, và dùng nhất quán.
3. **Thiết kế critical sections nhỏ**: bảo vệ bất biến, tránh I/O/blocking không cần thiết khi giữ monitor.
4. **Xét reentrancy** cho nested calls/recursion: same owner thread có thể acquire lại, nhưng cần release cân bằng.
5. **Đảm bảo visibility qua cùng lock** hoặc một synchronization scheme khác đúng JMM.
6. **Với wait/notify**, có explicit condition predicate, dùng while, xử lý interruption, và không nhầm notify với immediate unlock.
7. **Hạn chế multi-lock nested ordering**; nếu phải dùng nhiều monitors, đặt global order.
8. **Không expose lock object tùy tiện** cho code ngoài class; tránh interned Strings/boxed caches.
9. **Kiểm thử correctness** với nhiều threads và assertions; đừng viết tests dựa vào Thread.sleep/scheduling trùng hợp.
10. **Quan sát thực tế** bằng jcmd Thread.print, jstack/JFR ThreadMXBean khi contention/deadlock xuất hiện.
11. **Tách bug và performance**: mutex contention cao khác race condition, deadlock khác wait-set chờ condition hợp lệ.
12. **Khi dùng virtual threads**, xác nhận JDK version và các cải tiến monitor.
13. **Khi tối ưu**, xem data structures/lock granularity trước khi thay implementation; giữ semantics chính xác.
14. **Phân biệt source vs JVM bytecode**: ACC_SYNCHRONIZED của method khác monitorenter/exit của statement.
15. **Viết tài liệu rõ lock owner/state lifecycle**, giúp maintainers không vô tình thêm method truy cập state ngoài lock discipline.

### Tài liệu chính thức

- **Java Language Specification SE 17 — §17.1 Synchronization:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1
- **Java Language Specification SE 17 — §17.2 Wait Sets and Notification:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2
- **JLS SE 17 — §17.4.5 Happens-before Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
- **JVMS SE 17 — §2.11.10 Synchronization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.10
- **JVMS SE 17 — monitorenter/monitorexit instructions:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.monitorenter
- **Java SE 17 API — Object.wait/notify:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- **Java SE 17 API — Thread.holdsLock:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)
- **Java SE 17 API — Thread.State:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Java SE 17 API — ReentrantLock:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **Oracle Java SE 17 — jcmd:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **OpenJDK JEP 374 — Disable and Deprecate Biased Locking:** https://openjdk.org/jeps/374
- **OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning:** https://openjdk.org/jeps/491

**Kết luận:** Monitor của Java gắn với **object identity**. Một thời điểm chỉ một thread sở hữu monitor, nhưng **chính owner đó có thể reenter bao nhiêu lần cần thiết**, và lock thực sự được nhả khi số lần thoát cân bằng số lần vào. Instance synchronized lock **this**, static synchronized lock **Class object**, explicit synchronized lock object được chỉ định. **wait()** tạm nhả toàn bộ reentrant holds của receiver rồi reacquire trước khi hoàn tất; **notify() không chuyển giao lock ngay**. Để code concurrent đúng, phải nhất quán lock identity, dùng while-predicate cho condition waits và tận dụng happens-before trên **cùng monitor**.
