# Quy tắc lock/unlock của monitor trong Java Memory Model

> **Phạm vi:** quy tắc sở hữu, vào/ra intrinsic monitor, tính loại trừ lẫn nhau (*mutual exclusion*) và bảo đảm *happens-before* khi lock/unlock trong **Java SE/JVM**. Bài tập trung vào Java Memory Model (JMM), `synchronized` và `Object.wait/notify`. Những cơ chế riêng của Spring được trình bày ở phần khác.

## 1. Mục tiêu bài học

Sau khi học, bạn cần trả lời được:

- Một **monitor** gắn với object nào? Các cách `synchronized` lấy và nhả monitor hoạt động ra sao?
- **Một thread cùng lúc giữ monitor**, reentrancy, thời điểm nhả khóa bình thường/khi exception, và trường hợp thread khác phải chờ được hiểu thế nào?
- Quy tắc chính thức **unlock trên monitor m *synchronizes-with* mọi lock sau đó trên chính monitor m** có ý nghĩa gì?
- Vì sao quy tắc đó tạo **visibility/ordering** thông qua quan hệ *happens-before*, ngoài việc ngăn hai thread cùng vào critical section?
- Dùng **cùng một monitor** thế nào để bảo vệ các trường dữ liệu, invariant, một phép read-modify-write và giao thức chờ/thông báo?
- Những giới hạn của `synchronized`: thứ tự cấp khóa không cố định, không tự bảo vệ thao tác ngoài khóa, không tự làm một chuỗi nhiều lần gọi trở thành atomic.

**Điểm cốt lõi:** `synchronized` đem lại **hai loại bảo đảm** khi được dùng nhất quán: (1) mutual exclusion trong critical section trên cùng monitor và (2) quan hệ bộ nhớ giữa **unlock** và **lock tiếp theo của cùng monitor**. Một chức năng đúng cần cả hai khi các thread trao đổi dữ liệu có thể thay đổi.

## 2. Intrinsic monitor là gì?

Mỗi object Java có một monitor dùng cho đồng bộ hóa nội tại (intrinsic lock). Để vào một khối `synchronized (monitor) { ... }`, thread phải giành quyền **sở hữu monitor** của **đúng object tham chiếu bởi biểu thức `monitor`** tại thời điểm đó.

- Nếu monitor chưa do thread khác giữ, thread có thể vào critical section.
- Nếu thread khác đang giữ, thread đang tranh monitor phải đợi; trạng thái Java có thể quan sát là `Thread.State.BLOCKED`.
- Tại một thời điểm, chỉ **một thread** được sở hữu mỗi monitor, nhưng chính thread đó có thể vào lại monitor nhiều lần (*reentrant*).
- Khi rời vùng đồng bộ, số lần sở hữu được giảm tương ứng; monitor chỉ thật sự khả dụng cho thread khác khi mức sở hữu đã trở về 0.
- Monitor là thuộc tính của **object identity**, không phải tên biến, tên method hoặc văn bản giống nhau của biểu thức khóa.

Ví dụ khóa tại cấp instance:

```java
final class Inventory {
    private final Object guard = new Object();
    private int stock = 10;

    void sellOne() {
        synchronized (guard) {
            if (stock > 0) {
                stock--;
            }
        }
    }

    int remaining() {
        synchronized (guard) {
            return stock;
        }
    }
}
```

Đây là class độc lập có thể biên dịch khi đặt trong file `Inventory.java` (class không public). Nếu tất cả đường truy cập `stock` đi qua `guard`, một lần bán và việc đọc snapshot không thể xen kẽ tùy ý *bên trong* critical section. Với nhiều thread gọi `sellOne()`, số lượng không bị bán âm do hai thread cùng quan sát `stock > 0` trước khi trừ. Mỗi lần gọi vẫn có thể đến theo bất kỳ lịch nào; `synchronized` không hứa thứ tự khách hàng được phục vụ.

### Ba dạng synchronized thường dùng

| Dạng Java | Monitor thực sự được dùng | Phạm vi cạnh tranh |
|---|---|---|
| `synchronized (lockObject) { ... }` | Object do `lockObject` trỏ tới | Mọi vùng đồng bộ dùng **cùng object** |
| `synchronized void method() { ... }` trong instance | `this` | Các instance method synchronized khác trên **cùng instance**, hoặc `synchronized(this)` |
| `static synchronized void method() { ... }` | Object `SomeClass.class` tương ứng | Các static synchronized methods cùng Class object |

Một instance synchronized method trên object A **không dùng chung monitor** với cùng method trên object B. Instance synchronized method cũng **không dùng monitor của class** trừ khi lập trình viên chủ động dùng `synchronized (SomeClass.class)`.

`synchronized` là cấu trúc ngôn ngữ: khi vào khối có thể tương ứng với `monitorenter`, khi ra với `monitorexit` trong bytecode; các instance/static synchronized method có thể được biểu diễn bằng cờ `ACC_SYNCHRONIZED` và JVM thực thi semantics tương ứng. Không cần và không thể gọi thủ công một hàm `unlock()` dành cho intrinsic monitor. Khối `synchronized` tự giải phóng khi luồng điều khiển rời khối, kể cả do exception; điều này khác với explicit lock cần `finally { lock.unlock(); }`.

## 3. Mutual exclusion và reentrancy

### Mutual exclusion ngăn interleaving bên trong cùng critical section

Giả sử hai thread cùng gọi:

```java
synchronized (guard) {
    balance = balance + 100;
}
```

Đoạn trên chỉ là **minh họa trong một class**, nơi `guard` và `balance` đã được khai báo. Phép đọc–tính–ghi của một thread không thể bị thread khác cũng đang cố vào **cùng `guard`** chen vào giữa vùng đồng bộ. Trong điều kiện mọi cập nhật/đọc cần bảo vệ đều tuân thủ monitor đó, một phép cộng logic sẽ không bị mất cập nhật như `balance += 100` thiếu khóa.

Tuy nhiên, monitor **không ngăn** code không sử dụng `guard` truy cập biến trực tiếp. Nếu một method khác đọc/ghi `balance` bên ngoài khóa và không có cơ chế HB độc lập phù hợp, vẫn có thể xảy ra data race hoặc vi phạm invariant.

### Cùng thread có thể vào lại monitor (reentrant)

`synchronized` cho phép một thread đã giữ monitor gọi tiếp method cũng cần **chính monitor ấy** mà không tự deadlock:

```java
final class ReentrantExample {
    private int count;

    synchronized void outer() {
        inner(); // outer đã giữ monitor this
    }

    synchronized void inner() {
        count++;
    }

    synchronized int getCount() {
        return count;
    }
}
```

Đây là class độc lập có thể lưu dưới tên `ReentrantExample.java`. Thread gọi `outer()` lấy monitor `this`, `inner()` vào lại đúng monitor đó, rồi hai scope kết thúc và quyền sở hữu được nhả tương ứng. **Reentrancy không có nghĩa nhiều thread được đồng thời sở hữu monitor**: đó vẫn là một thread với mức reentrant depth lớn hơn một.

Khi dùng monitor lồng nhau, cần đặc biệt chú ý **thứ tự lấy các monitor khác nhau**. Reentrancy trên cùng monitor không giải quyết được deadlock do A giữ monitor X đợi Y, còn B giữ Y đợi X.

## 4. Quy tắc lock/unlock trong JMM

Đây là quy tắc **chính thức tại JLS `17.4.4**:

> Một hành động **unlock** trên monitor `m` *synchronizes-with* tất cả hành động **lock** sau đó trên cùng `m`; “sau đó” được xác định trong **synchronization order**.

Chú ý ba thành phần của câu này:

1. **`m` phải là cùng monitor/object**. Unlock `leftLock` không tự tạo cạnh *synchronizes-with* cho lần lock `rightLock`.
2. Quy tắc áp dụng giữa hành động **nhả và lấy monitor**, không phải tự động giữa mọi câu lệnh xảy ra ở hai thread bất kỳ.
3. **Synchronization order** là thứ tự tổng của các synchronization actions trong một execution và nhất quán với program order trong mỗi thread. Nó là khái niệm hình thức của JMM, không phải lời hứa về FIFO, fairness hay thread nào chạy trước trong thực tế.

Trong JMM:

- **Program order** đưa hành động trước–sau trong cùng thread vào quan hệ *happens-before*.
- **Synchronizes-with** tạo các cạnh liên thread, ví dụ unlock→subsequent lock của cùng monitor.
- **Happens-before (HB)** bao gồm program order và synchronizes-with, rồi lấy tính **bắc cầu**.

Vì vậy ta có sơ đồ:

```text
Thread A                          Thread B
--------------------------------  --------------------------------
synchronized (m) {                 synchronized (m) {
    sharedData = 42;                  int seen = sharedData;
} // unlock(m)                    } // unlock(m)
   |                                   ^
   +--- synchronizes-with ------------+
        lock(m) sau unlock(m)

Ghi sharedData = 42  --program order--> unlock(m)
unlock(m)            --synchronizes-with--> lock(m) của B
lock(m) của B        --program order--> đọc sharedData
=> Ghi của A happens-before đọc của B (nếu B lấy khóa sau A nhả).
```

Ở ví dụ trên, không thể suy ra B luôn đọc 42 từ việc hai thread được tạo ra. **Nếu B vào critical section trước A**, B có thể đọc giá trị cũ theo thứ tự thực thi hợp lệ. Điều được bảo đảm là: khi lần lấy monitor của B xảy ra **sau** lần unlock của A theo synchronization order, các ghi trước unlock của A được công bố theo HB cho các thao tác sau lock B, nếu không có các cập nhật hợp lệ khác thay đổi kết quả.

### Ví dụ cụ thể: truyền dữ liệu dưới cùng monitor

```java
final class SharedMessage {
    private final Object monitor = new Object();
    private String message;

    void publish(String value) {
        synchronized (monitor) {
            message = value;
        } // release monitor
    }

    String snapshot() {
        synchronized (monitor) { // acquire same monitor
            return message;
        }
    }
}
```

Đây là class độc lập, có thể đặt trong `SharedMessage.java`. Nếu `snapshot()` lấy monitor sau khi `publish()` đã nhả nó, thay đổi `message` trước unlock có quan hệ HB với lần đọc trong snapshot. **Tuy vậy**, một caller gọi `snapshot()` trước khi có publish có thể nhận `null`, và nhiều publish có thể tạo giá trị khác nhau theo thứ tự được thực thi. Nếu yêu cầu là “consumer phải đợi có thông điệp”, cần thêm predicate và `wait/notify` (phần sau), hoặc một công cụ phù hợp như `BlockingQueue`.

### “Release/acquire” không phải lệnh flush cache thủ công

Mô tả bằng “unlock flush hết cache, lock tải hết RAM” là cách giải thích **sai hoặc quá thô**. JMM là **hợp đồng quan sát/ordering** cho execution; JVM/JIT/CPU có thể dùng barriers hoặc cơ chế khác để thực hiện hợp đồng trên mỗi nền tảng. Người viết Java cần dựa vào HB và atomicity, không dựa vào một sơ đồ cache vật lý giả định.

Điểm đáng nhớ: **mutual exclusion** khiến những thread cùng dùng monitor không thực hiện phần protected code đồng thời; **HB** khiến ghi trước unlock được quan sát đúng bởi các lần lock theo sau. Hai tác dụng bổ sung cho nhau. Trong trường hợp một thread chỉ đọc mà không có cùng khóa, monitor alone không tạo ra cạnh HB từ lần unlock tới lần đọc đó.

## 5. Khi nào lock và unlock thực sự diễn ra?

### Vào/ra khối synchronized

```java
synchronized (m) {        // cố gắng acquire monitor m
    doCriticalWork();
}                         // release monitor m khi ra khối
```

Đây là code minh họa với `m` và `doCriticalWork()` được định nghĩa trong class chứa đoạn. Nếu `doCriticalWork()` ném exception, Java vẫn bảo đảm giải phóng phần sở hữu monitor tương ứng của khối. Trường hợp `m == null`, việc cố vào khối gây `NullPointerException`: chưa có monitor hợp lệ được lấy.

### synchronized method

```java
public synchronized void update() {
    state++;
}
```

Đây là method minh họa trên một instance có trường `state`. Acquire monitor `this` trước khi thực hiện body; unlock khi method kết thúc. Với `static synchronized`, monitor là object `Class`. Thực hiện một cuộc gọi `this.update()` trong khi đã ở `synchronized(this)` là ví dụ **reentrance**.

### Ngoại lệ, return, break

Không phải viết `finally` để nhả intrinsic monitor khi `return` hoặc exception làm rời `synchronized`. Nhưng **logic rollback nghiệp vụ không tự xảy ra**: nếu code thay đổi hai trường rồi exception ở giữa, monitor được nhả, nhưng dữ liệu có thể còn ở trạng thái trung gian. Phải tự thiết kế invariant, exception safety hoặc commit/rollback logic nếu cần.

### Khi đang chờ lấy monitor

Thread khác giữ `m` → contender đi vào `synchronized(m)` → có thể ở `Thread.State.BLOCKED`. Không có hợp đồng rằng contender được lấy khóa theo thứ tự nó bắt đầu chờ. `Thread.interrupt()` **không làm lời gọi monitor entry ném `InterruptedException`**, và không tự biến thao tác vào `synchronized` thành interruptible lock acquisition.

**Không tự đồng nhất các kiểu chờ**: một thread đợi `ReentrantLock.lock()` thường sử dụng cơ chế park và có thể quan sát `WAITING`; đó không phải monitor `BLOCKED` của `Thread.State`. Explicit lock có hợp đồng memory effects tương đương cho acquire/release theo `Lock` API, nhưng đó là một primitive khác với monitor của `synchronized`.

## 6. Một object khóa ổn định cho cùng invariant

Một nguyên tắc thiết kế: **mọi truy cập trạng thái chia sẻ cấu thành cùng invariant phải được điều phối bởi cùng giao thức đồng bộ.**

Ví dụ hai trường cần nhất quán:

```java
final class Account {
    private final Object guard = new Object();
    private long balance;
    private long version;

    Account(long initial) {
        balance = initial;
    }

    void deposit(long amount) {
        if (amount <= 0) throw new IllegalArgumentException();
        synchronized (guard) {
            balance += amount;
            version++;
        }
    }

    String snapshot() {
        synchronized (guard) {
            return "balance=" + balance + ", version=" + version;
        }
    }
}
```

Đây là class độc lập có thể biên dịch trong `Account.java`. Ở ví dụ, `balance` và `version` cập nhật trong cùng critical section, `snapshot()` đọc cả hai dưới cùng monitor nên không quan sát một nửa bước cập nhật đang tiến hành. Mã chỉ minh họa khóa/invariant, **không** bao gồm xử lý tràn số `long`; chương trình tài chính thực tế phải thêm kiểm tra overflow và quy tắc chính xác số tiền.

### Các lựa chọn monitor cần tránh nếu thiếu lý do

- `synchronized (new Object())` bên trong mỗi lần gọi tạo **monitor mới** cho từng lần, không tạo sự loại trừ giữa hai lần gọi.
- Dùng khóa khác nhau cho writer và reader không tạo cùng một quy tắc HB từ unlock tới lock của reader.
- Dùng một tham chiếu lock có thể thay đổi (`lock = anotherObject`) làm các thread có thể đồng bộ trên các object khác nhau.
- `synchronized (this)` trong API công khai cho phép bên ngoài chủ động giữ `this` và làm nghẽn nội bộ; monitor `private final Object guard` thường dễ kiểm soát hơn.
- Đồng bộ trên string literal/interned string, wrapper bị boxing/caching hoặc một object có thể bị chia sẻ ngoài ý muốn tạo contention và rủi ro tương tác với code khác.
- Một khóa toàn cục bảo vệ trạng thái không liên quan có thể làm giảm concurrency; ngược lại, dùng quá nhiều khóa cho một invariant dễ phá tính atomic.

**Lưu ý:** `final` trên biến tham chiếu `guard` chỉ bảo đảm nó không được gán lại theo luồng code bình thường; `final` không làm những trường mutable khác tự thread-safe. Chính việc sử dụng cùng monitor một cách nhất quán và safe publication của object chứa nó tạo nền tảng cho thiết kế đúng.

## 7. Thử nghiệm Java 17+ có kết quả xác định

Chương trình dưới đây minh họa **mutual exclusion** khi hai worker tăng cùng một bộ đếm và **visibility/ordering** khi một producer thông báo cho consumer qua monitor. Đầu ra không phụ thuộc việc worker nào chạy trước.

Tạo file **`MonitorRulesDemo.java`**:

```java
public final class MonitorRulesDemo {
    private static final class Counter {
        private int count;

        synchronized void increment() {
            count++;
        }

        synchronized int get() {
            return count;
        }
    }

    private static final class Mailbox {
        private final Object monitor = new Object();
        private boolean ready;
        private String message;

        void publish(String text) {
            synchronized (monitor) {
                message = text;
                ready = true;
                monitor.notifyAll();
            }
        }

        String awaitMessage() throws InterruptedException {
            synchronized (monitor) {
                while (!ready) {
                    monitor.wait();
                }
                return message;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();
        first.join();
        second.join();
        System.out.println("count=" + counter.get());

        Mailbox mailbox = new Mailbox();
        Thread receiver = new Thread(() -> {
            try {
                System.out.println("message=" + mailbox.awaitMessage());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "receiver");

        receiver.start();
        mailbox.publish("ready");
        receiver.join();
        System.out.println("receiverFinished=" + !receiver.isAlive());
    }
}
```

Từ thư mục chứa `MonitorRulesDemo.java`, biên dịch/chạy:

```bash
javac --release 17 MonitorRulesDemo.java
java MonitorRulesDemo
```

**Stdout đã xác minh:**

```text
count=20000
message=ready
receiverFinished=true
```

**Phân tích tại sao không bị lost update:**

1. Hai worker mỗi thread gọi `increment()` 10.000 lần; method là instance `synchronized` nên **đều lấy monitor của cùng object `counter`**.
2. `count++` bên trong monitor được thực hiện trọn vẹn cho mỗi lần gọi, không có worker nào khác lọt vào method đồng bộ cùng monitor giữa lúc đó.
3. `first.join()` và `second.join()` chờ hai worker hoàn tất. Lúc main gọi `get()` sau đó, không còn tác vụ tăng đang chạy; kết quả chính xác là 20.000. `join()` cũng có quan hệ HB riêng về hoàn tất thread, nhưng **join không thay thế việc lock bảo vệ các phép tăng**.
4. Nếu bỏ synchronized trên `increment()` và giữ `join()`, kết quả có thể mất cập nhật vì hai worker đã chạy đua trước khi main chờ xong.

**Phân tích tại sao thông điệp luôn là “ready”:**

1. `publish()` giữ `mailbox.monitor`, ghi `message`, rồi đặt `ready = true`.
2. `notifyAll()` chỉ thông báo; monitor vẫn do producer giữ đến khi thoát `synchronized`.
3. `awaitMessage()` giữ **cùng monitor** và kiểm tra `ready` trong vòng `while`. Nếu chưa có dữ liệu, `wait()` nhả monitor và đợi. Khi thức dậy, nó **phải lấy lại monitor** trước khi rời `wait()` rồi kiểm tra lại `ready`.
4. Trường hợp producer publish **trước** khi receiver vào `wait()` cũng đúng: receiver đọc được `ready == true` dưới monitor, không đợi nữa. Nhờ predicate, không bị “mất thông báo” theo cách dùng `notify` mà không có trạng thái.
5. Các ghi `message/ready` của producer trước unlock được bảo đảm HB với lần lock/reacquire sau đó của consumer; consumer đọc dữ liệu trong critical section có visibility phù hợp.
6. `receiver.join()` bảo đảm dòng `message=ready` đã thực hiện trước dòng cuối cùng và `receiverFinished=true`.

Mã này cố ý dùng **platform threads** chạy tốt từ Java 17. Scheduler có thể chọn thứ tự nội bộ bất kỳ, nhưng output trên được bảo đảm khi chương trình hoàn thành bình thường. Với production, cấu trúc truyền dữ liệu như `BlockingQueue` thường tiện hơn tự quản lý wait set, nhưng bài này dùng monitor để giải thích semantics của Java.

## 8. `wait()` và `notify()` thay đổi ownership thế nào?

Phần dễ hiểu sai: `Object.wait()` **nhả monitor**, còn `Object.notify()/notifyAll()` **không tự nhả monitor**.

### Quy trình chờ đúng

Khi thread đang giữ monitor của object `m` và gọi `m.wait()`:

1. Thread **phải sở hữu** monitor `m`; nếu không, Java ném `IllegalMonitorStateException`.
2. Thread được đưa vào wait set của `m`, **nhả toàn bộ mức sở hữu trên chính monitor `m`** và chờ được đánh thức.
3. Một sự kiện như `notify`/`notifyAll`, interrupt, timeout (ở overload có timeout) hoặc spurious wakeup có thể kết thúc pha đợi.
4. Thread phải **lấy lại monitor `m`** trước khi `wait()` thực sự trả về bình thường hoặc ném `InterruptedException`; nếu monitor vẫn bận, nó có thể ở `BLOCKED` khi reacquire.
5. Bởi vì điều kiện có thể đổi, **kiểm tra predicate bằng vòng `while`** mỗi khi tiếp tục.

`wait()` **không nhả bất kỳ monitor khác** nào thread cũng đang sở hữu. Do đó lồng nhiều `synchronized` rồi `wait` trên một object mà vẫn giữ object khác có thể gây deadlock.

### Sơ đồ về thứ tự sở hữu

```text
Thread consumer                          Thread producer
---------------------------------------  -----------------------------
lock(m)
while (!ready):
    wait(m): release(m)
            [đang đợi]                 lock(m)
                                       message = "ready"
                                       ready = true
                                       notifyAll(m)
                                       ... vẫn giữ m ...
                                       unlock(m)
    [reacquire(m) thành công]
    đọc message
unlock(m)
```

Việc consumer đọc sau reacquire nhận các ghi được công bố của producer là hệ quả của HB qua monitor (cùng các quy tắc đồng bộ liên quan). **`notifyAll()` tự nó không chuyển ngay quyền sở hữu**. Nếu producer gọi `notifyAll()` rồi xử lý lâu bên trong monitor, waiter đã được đánh thức vẫn phải chờ.

Ví dụ lỗi phổ biến:

```java
// MINH HỌA SAI: không được gọi wait/notify khi chưa sở hữu monitor.
Object m = new Object();
m.notifyAll(); // IllegalMonitorStateException
m.wait();      // IllegalMonitorStateException
```

Đây là các lệnh minh họa không nằm trong chương trình chạy đầy đủ; dòng `m.wait()` còn phải được đặt trong ngữ cảnh method khai báo/xử lý `InterruptedException`. Để dùng đúng: gọi `m.wait()` và `m.notifyAll()` **trong `synchronized(m)`**, và chỉ wait khi predicate chưa thỏa.

### Sự khác nhau với sleep

`Thread.sleep(...)` không nhả monitor mà thread đang nắm giữ; `sleep` cũng không tạo ra cạnh *synchronizes-with* chỉ vì trôi qua thời gian. Nếu muốn đợi điều kiện gắn với monitor, dùng `wait` với predicate hoặc primitive concurrency cấp cao phù hợp; đừng thay bằng `sleep`/`yield` để “đợi thread khác xong”.

## 9. Vì sao locking đơn lẻ vẫn có thể không đủ?

### Check-then-act phải nằm trong **một** critical section

Sai về atomicity nghiệp vụ:

```java
// Giả sử getBalance()/withdraw() mỗi method đều synchronized
if (account.getBalance() >= 100) {
    account.withdraw(100);
}
```

Đây là đoạn mã minh họa và `account` có API giả định. Dù từng method tự khóa đúng, **giữa lần `getBalance()` và `withdraw()` monitor đã được nhả**. Hai thread có thể cùng thấy đủ tiền rồi cùng rút. Cách đúng là một method trên `account` thực hiện **kiểm tra + cập nhật** dưới cùng monitor:

```java
synchronized boolean withdrawIfEnough(long amount) {
    if (amount < 0 || balance < amount) return false;
    balance -= amount;
    return true;
}
```

Đoạn trên là method của một class có trường `long balance`. Lệnh `return` tự rời synchronized method và nhả monitor. Trong hệ thống thực tế còn phải định nghĩa xử lý overflow, transaction, persistence và quyền truy cập, nhưng về Java monitor, kiểm tra và trừ ở đây thuộc cùng một critical section.

### Hai khóa khác nhau không phối hợp qua monitor rule

```java
// Ví dụ minh họa SAI: hai monitor khác nhau cho cùng sharedValue.
private final Object writerLock = new Object();
private final Object readerLock = new Object();
private int sharedValue;

void set(int v) {
    synchronized (writerLock) { sharedValue = v; }
}

int get() {
    synchronized (readerLock) { return sharedValue; }
}
```

Đây là thành viên minh họa của một class. `writerLock` và `readerLock` khác object, nên lần unlock thứ nhất **không** synchronizes-with lần lock thứ hai qua monitor rule. Hơn nữa writer và reader có thể vào vùng “bảo vệ” đồng thời. Sửa bằng **một monitor duy nhất** cho mọi truy cập gây xung đột, hoặc một giao thức khác có memory semantics tương đương được chứng minh.

### volatile khác monitor

`volatile` có quy tắc *synchronizes-with* cho **ghi → đọc** cùng volatile variable theo JMM. Nhưng `volatile int count` vẫn không làm `count++` atomic; nó là đọc–tính–ghi. `synchronized` tạo exclusion qua monitor và HB qua unlock→lock; `AtomicInteger.incrementAndGet()` là thao tác atomic riêng. Chọn theo **invariant**:

| Yêu cầu | Công cụ thường phù hợp |
|---|---|
| Nhiều bước đọc/ghi cần atomic cùng nhau | `synchronized` hoặc `Lock` bảo vệ cả nhóm |
| Cập nhật độc lập một số nguyên bằng phép atomic | `AtomicInteger` / `AtomicLong` |
| Công bố một cờ và dữ liệu có đúng giao thức visibility | `volatile` khi đủ, hoặc monitor/queue |
| Consumer chờ producer bàn giao item | `BlockingQueue`, `Condition` hoặc `wait/notify` đúng predicate |
| Nhiều trường phải nhất quán trong một snapshot | Cùng monitor/lock hoặc thiết kế dữ liệu bất biến |

`ReentrantLock` theo `java.util.concurrent.locks.Lock` quy định hành vi bộ nhớ của lock/unlock tương đương tác dụng của monitor lock/unlock; nó có API khác như timeout và interruptible acquisition. **Không coi `Lock` và `synchronized` là một object monitor giống nhau**. Đổi sang primitive khác cần thay cả acquire/release protocol nhất quán.

## 10. Visibility, liveness và fairness không phải một thứ

Quy tắc HB trả lời: **khi một truy cập đã được ordering tương ứng, các ghi nào phải được thấy đúng?** Nó **không trả lời** thread có chắc chắn được CPU chạy hay được monitor trước đối thủ hay không.

- **Safety:** dữ liệu và invariant không bị phá, chẳng hạn bộ đếm không mất cập nhật.
- **Visibility:** các cập nhật đã được công bố qua cùng monitor được quan sát theo HB.
- **Liveness:** một thread có khả năng tiếp tục hoàn thành, không mắc deadlock/starvation vô hạn.
- **Fairness:** chính sách phân phối quyền tiến triển có thiên vị hay không.

`synchronized` bảo đảm mutex và ordering; **không có cam kết FIFO/fairness** giữa các contender. Giữ monitor khi thực hiện I/O chậm có thể làm throughput giảm và các thread khác chờ lâu. Lấy monitor A rồi B ở một thread, nhưng B rồi A ở thread khác có thể tạo **deadlock**. Các lỗi liveness này cần thiết kế acquisition order, giảm critical section, timeout khi khả thi và đo tải thực tế; HB không tự chữa chúng.

Một pattern tránh deadlock cơ bản khi phải lấy hai monitor là **quy ước thứ tự toàn cục** cho mọi caller. Tuy nhiên, nếu thiết kế không cần giữ hai monitor cùng lúc, chuyển sang một critical section ngắn hoặc truyền message thường dễ kiểm chứng hơn.

## 11. Tại sao lock/unlock còn có ý nghĩa với dữ liệu không volatile?

Ví dụ counter trong `MonitorRulesDemo` là `private int count` bình thường, **không volatile**. Cách này hợp lệ nếu mọi truy cập từ nhiều thread tuân thủ khóa `this` của chính counter:

- Writer gọi `increment()` và giành monitor, thay đổi `count`, nhả monitor.
- Reader gọi `get()` và giành cùng monitor sau unlock đó.
- Thứ tự “ghi count → unlock → lock → đọc count” được nối bằng HB, nên không cần khai báo count là volatile chỉ để cập nhật/đọc theo giao thức ấy.
- Nếu reader bỏ khóa và chỉ `return count;`, không thể lấy sự bảo đảm memory visibility **từ monitor rule** cho lần đọc đó nữa. Các cạnh HB khác đôi khi vẫn tồn tại (chẳng hạn join trong ví dụ), nhưng code thư viện không nên ngầm phụ thuộc vào tình huống gọi rất riêng này.

Tương tự, dùng `private final Object guard` không biến dữ liệu bên trong thành immutable. “final lock” và “lock-protected mutable data” là hai vai trò riêng: final giúp giữ ổn định identity của object monitor; còn mutual exclusion/HB đến từ các lần acquire/release thực tế.

Cũng cần phân biệt **atomicity của truy cập đơn lẻ** với **atomicity của hành vi nhiều bước**. Một phép đọc/ghi reference hay int có tính nguyên tử của access riêng lẻ theo JMM, nhưng không có nghĩa check-then-act được bảo vệ. Kể cả khi đọc một giá trị “không bị xé”, đọc có thể cũ hoặc xen với cập nhật khác nếu thiếu HB.

## 12. Quan sát quy tắc monitor trong thực tế

### Thread dump

Trong khi ứng dụng Java đang chạy, có thể dùng:

```bash
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng process ID thật. Xem stack trace và thông tin monitor để phân biệt:

- Thread `BLOCKED (on object monitor)` đang chờ giành intrinsic monitor (thường là `synchronized`).
- Thread `WAITING (on object monitor)` tại `Object.wait()` đang nằm trong wait set, **đã nhả monitor được wait**.
- Thread `WAITING (parking)` tại `LockSupport.park()` có thể chờ `ReentrantLock`, queue hay synchronizer khác; không nhất thiết chờ `synchronized`.
- Thread `RUNNABLE` chưa chắc đang thực sự dùng CPU; có thể chờ OS scheduling.

Một thread dump chỉ là **ảnh tại một thời điểm**. Không thể suy độ dài contention, tần suất chuyển state, hay logic invariant chỉ từ một dòng `Thread.State`.

### Java Flight Recorder (JFR)

Với workload đủ dài để tạo sự kiện:

```bash
jcmd <PID> JFR.start name=monitor-profile settings=profile duration=60s filename=monitor.jfr
jfr summary monitor.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait monitor.jfr
```

`jdk.JavaMonitorEnter` giúp khảo sát thời gian tranh chấp monitor; `jdk.JavaMonitorWait` giúp xem các hoạt động đợi monitor. Chú ý threshold và event settings: **không thấy event không chứng minh không có lock contention**. Dùng kết hợp thread dump, CPU profiling và application metrics; chạy ví dụ rất ngắn thường không tạo recording hữu ích.

### ThreadMXBean

`java.lang.management.ThreadMXBean` có thể cung cấp thông tin blocked/waited count và time. Muốn đo thời gian contention, kiểm tra `isThreadContentionMonitoringSupported()` trước rồi mới cân nhắc bật `setThreadContentionMonitoringEnabled(true)`, vì đo lường có overhead và có thể bị giới hạn bởi JVM. `getBlockedCount()/getBlockedTime()` gắn với **monitor contention**, không phải tổng thời gian đợi mọi explicit lock hay số lần context switch OS. Dùng số liệu theo thời gian thay vì kết luận từ một snapshot.

### Phương pháp tìm lỗi monitor theo trình tự

1. Xác định **state/invariant** đang sai (lost update, stale read, snapshot không nhất quán, treo).
2. Ghi lại **mọi vị trí đọc/ghi** state và object cụ thể được dùng để khóa.
3. Vẽ đường HB cần có: writer có unlock trên monitor nào? Reader có acquire **cùng monitor** sau đó không? Có primitive khác tạo HB hợp lệ không?
4. Phân biệt **bug atomicity** (hai thao tác xen kẽ) với **visibility bug** (quan sát thiếu HB), và **liveness bug** (không tiến triển).
5. Tái hiện bằng `CountDownLatch`/barrier trong test khi cần; dùng phép kiểm tra invariants, không dựa vào `Thread.sleep()`/`yield()` để “chữa” race.
6. Sau khi sửa, kiểm tra correctness trên nhiều lịch/tải, rồi mới đo throughput/latency/lock contention để quyết định granularity của khóa.

## 13. Các hiểu lầm cần tránh

1. **“`synchronized` chỉ là mutex, không liên quan visibility.”** Sai: unlock và subsequent lock cùng monitor có cạnh *synchronizes-with*, tạo HB.
2. **“Nhả một monitor làm mọi thread đọc thấy dữ liệu ngay, dù không lấy khóa.”** Không có bảo đảm ấy **chỉ từ monitor rule**; cần đúng HB path.
3. **“Hai method đều synchronized là đủ.”** Chưa đủ nếu hai method thuộc **hai instance khác nhau** hoặc các bước check-then-act cần nguyên tử qua nhiều lần gọi.
4. **“`static synchronized` khóa từng instance.”** Sai: dùng monitor `Class` của class đó.
5. **“`synchronized(lock)` và `synchronized(new Object())` giống nhau.”** Sai: object identity quyết định các thread có cạnh tranh cùng monitor hay không.
6. **“Ngoại lệ khiến monitor bị giữ mãi.”** Với khối/method `synchronized`, JVM nhả khi scope rời; nhưng dữ liệu không tự rollback.
7. **“`notifyAll` nhả khóa cho waiter lập tức.”** Sai: caller còn giữ monitor tới khi unlock; waiter phải reacquire.
8. **“`wait` nhả mọi lock thread đang giữ.”** Sai: chỉ nhả monitor của chính object được wait, không phải các monitor khác.
9. **“`Thread.sleep` nhả monitor.”** Sai: ngủ không nhả khóa.
10. **“Có HB thì B luôn chạy sau A theo thời gian.”** HB là ràng buộc ordering/visibility của các action, không cam kết scheduler cho B CPU sau một khoảng thời gian cụ thể.
11. **“`volatile++` tương đương tăng dưới monitor.”** Sai: volatile read/write riêng lẻ không biến read-modify-write thành atomic.
12. **“Monitor cấp quyền công bằng theo FIFO.”** Không có cam kết FIFO/fairness của `synchronized`.
13. **“Nếu synchronized gây overhead, bỏ nó đi rồi dùng join để đọc sau.”** `join` có HB đối với thread hoàn tất, nhưng không ngăn các worker chạy đua khi cùng cập nhật trong thời gian thực thi.
14. **“Java lock luôn thực hiện một lệnh flush toàn bộ cache.”** Không phải mô tả đúng về hợp đồng JMM; dùng quan hệ formal HB để suy luận.

## 14. Bài tập tự kiểm tra có giải đáp

**Câu 1.** A viết `x=17` trong `synchronized(m)` rồi ra khối. B sau đó vào `synchronized(m)` và đọc `x`, không có ghi cạnh tranh khác. B có thể thấy giá trị cũ vì `x` không volatile không?  
**Đáp án:** Không, nếu lần lock của B đứng sau unlock của A trên cùng `m` theo synchronization order. Chuỗi program-order + unlock→lock tạo HB.

**Câu 2.** A nhả monitor `m1`; B lấy monitor `m2` rồi đọc cùng `x`. Có thể viện dẫn quy tắc monitor nói trên để bảo đảm visibility không?  
**Đáp án:** Không. Cạnh unlock→lock này đòi hỏi cùng monitor. Có thể có các HB edges **khác**, nhưng không được suy ra chỉ từ hai monitor khác nhau.

**Câu 3.** A gọi instance synchronized method trên `obj1`, B gọi cùng method trên `obj2`. Hai call có loại trừ lẫn nhau không?  
**Đáp án:** Không, vì monitor lần lượt là `obj1` và `obj2`, trừ khi bên trong còn phối hợp trên shared monitor khác.

**Câu 4.** Vì sao `count++` nằm hoàn toàn trong `synchronized(guard)` cùng mọi access liên quan thì đúng, nhưng hai synchronized method `get()` và `set()` gọi liên tiếp có thể không đủ cho một transaction?  
**Đáp án:** Phép tăng được bảo vệ như một critical section; cặp get-then-set gồm hai lần acquire/release nên thread khác có thể chen vào ở giữa.

**Câu 5.** Một thread đang `synchronized(m)` gọi `m.wait()`. Nó có còn giữ `m` trong lúc chờ không? Khi `wait` trả về thì sao?  
**Đáp án:** Nó tạm nhả monitor `m` khi vào wait set, và phải reacquire `m` trước khi `wait` hoàn tất. Các monitor khác nó giữ không được nhả tự động.

**Câu 6.** A giữ monitor rồi gọi `notifyAll()`. B đang đợi điều kiện có được chạy ngay trong critical section không?  
**Đáp án:** Không. B còn phải được scheduler chạy và giành lại monitor sau khi A nhả. Dùng `while` kiểm tra lại điều kiện.

**Câu 7.** Thread A có thể vào `synchronized(this)` khi nó đang giữ monitor `this` bởi một synchronized method khác không?  
**Đáp án:** Có, vì intrinsic monitor reentrant. Thread B đồng thời sẽ phải đợi đến khi A nhả hết mức sở hữu.

**Câu 8.** Việc gọi `Thread.join()` sau hai worker cùng làm `counter++` thiếu đồng bộ có xóa lost update không?  
**Đáp án:** Không. `join` xác nhận chúng đã kết thúc và tạo HB cho việc main đọc sau đó; lỗi lost update đã có thể xảy ra trước đó giữa hai worker.

**Câu 9.** Vì sao không nên lấy một string literal làm private monitor?  
**Đáp án:** Literal có thể được intern và chia sẻ giữa những phần code không liên quan; vô tình khóa chung gây contention hoặc deadlock ngoài dự kiến. Thường nên dùng `private final Object guard = new Object()`.

**Câu 10.** Một thread giữ monitor quá lâu, nhiều thread khác `BLOCKED`. Java Memory Model có bị vi phạm không?  
**Đáp án:** Chưa chắc. Mutex/HB vẫn có thể đúng, nhưng thiết kế có **vấn đề tiến triển/hiệu năng**. Cần tìm thời gian giữ lock, I/O bên trong critical section và thứ tự lấy khóa.

## Tài liệu tham khảo chính thức

- [JLS Java SE 17 `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): đặc biệt `17.1` về synchronization, `17.4.4` về synchronization order, `17.4.5` về happens-before.
- [JLS Java SE 17 `14.19 — The synchronized Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19): vào/rời synchronized statement và xử lý abrupt completion.
- [JLS Java SE 17 `8.4.3.6 — synchronized Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.6): instance/static method và monitor liên quan.
- [Java SE 17 Object API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `wait()`, `notify()`, `notifyAll()` và quy tắc sở hữu monitor.
- [Java SE 17 Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): start, join, interrupt và thread states.
- [Java SE 17 Lock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): memory synchronization semantics của explicit locks.
- [Java SE 17 ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): số liệu contention khi được hỗ trợ.

**Tổng kết kỹ thuật:** lần **unlock(m)** tạo cạnh *synchronizes-with* tới các lần **lock(m)** sau đó. Khi kết hợp với program order, nó thiết lập *happens-before* để bảo đảm visibility/ordering; còn việc chỉ một thread sở hữu `m` tại một thời điểm bảo vệ atomicity của critical section. Đúng **cùng monitor**, đúng **phạm vi invariant** và đúng **giao thức chờ** mới biến bảo đảm JMM thành correctness cho chương trình.