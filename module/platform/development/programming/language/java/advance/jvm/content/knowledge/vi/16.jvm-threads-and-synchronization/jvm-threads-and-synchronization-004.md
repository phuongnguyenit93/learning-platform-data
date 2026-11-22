# `monitorenter`, `monitorexit` và phương thức có cờ `ACC_SYNCHRONIZED`

## 1. Bức tranh tổng quan: Java `synchronized` được JVM thực thi thế nào?

Java cung cấp hai dạng cú pháp đồng bộ nội tại (intrinsic synchronization):

- **Khối lệnh:** `synchronized (lock) { ... }` — khóa monitor gắn với **object reference do biểu thức `lock` tạo ra** trong thời gian chạy block.
- **Phương thức:** `synchronized void method() { ... }` hoặc `static synchronized void method() { ... }` — khóa monitor được xác định ngầm bằng **receiver `this`** (instance method) hoặc **đối tượng `Class`** của class khai báo (static method).

Cả hai đều tuân theo một **monitor model**: một thread sở hữu monitor tại một thời điểm, có khả năng **tái nhập (reentrant)**, và unlock–lock trên **cùng monitor** có hiệu ứng memory-ordering theo Java Memory Model (JMM).

Nhưng chúng **khác cách thể hiện trong class file**:

| Java source | Biểu diễn bytecode/class file điển hình | Ai lo enter/exit? |
| --- | --- | --- |
| `synchronized (obj) { body(); }` | `monitorenter`, `monitorexit` và exception handler thích hợp trong `Code` | Instructions và control-flow do `javac` phát sinh |
| `public synchronized void action()` | `method_info.access_flags` chứa `ACC_SYNCHRONIZED`; thường **không** có `monitorenter`/`monitorexit` vì riêng việc khai báo method | JVM tự enter khi invoke, exit khi method complete |
| `public static synchronized void action()` | Cũng là `ACC_SYNCHRONIZED` | JVM dùng monitor của đối tượng `Class` đại diện class khai báo |
| `new ReentrantLock()` và `lock()/unlock()` | Thông thường các lời gọi method thư viện; **không** có `monitorenter` chỉ vì là lock | Thư viện `java.util.concurrent.locks` và các nguyên thủy JVM/OS mà nó dùng |

Đây là điểm chính để đọc `javap`: **không thấy opcode `monitorenter` trong một `synchronized` method không có nghĩa method ấy không được đồng bộ**. Bản thân cờ `ACC_SYNCHRONIZED` là cách JVM nhận biết và áp dụng khóa ngầm.

Bài theo **JVMS Java SE 17**, cùng những ghi chú riêng về HotSpot Java 17. Java/JVMS định nghĩa hiệu ứng và cấu trúc class file; việc HotSpot tối ưu monitor bằng fast path, spinning, inflation, JIT lock elimination… là chi tiết triển khai có thể đổi theo phiên bản.

## 2. Monitor là gì?

Một monitor là một cơ chế đồng bộ gắn với một object, có thể được mô hình hóa qua:

- **Owner:** thread đang sở hữu monitor hoặc không có owner.
- **Entry count (reentrancy depth):** số lần owner đã enter trừ số lần exit phù hợp.
- **Entry contention:** những thread khác đang cố acquire monitor phải chờ monitor có thể được lấy.
- **Wait set:** những thread đã gọi `Object.wait()` hợp lệ trên monitor và đang chờ được đánh thức/tái giành lock theo điều kiện của `wait`.

```text
                 Object L / monitor(L)
                 +--------------------+
Thread A ------> | owner = A          |
                 | entry count = 2    |
Thread B --X-->  | B đang chờ enter   |
                 | wait set: ...      |
                 +--------------------+

A đã enter hai lần => phải exit hai lần mới thả ownership.
B không thể enter trong lúc monitor vẫn do A sở hữu.
```

Các trường ở sơ đồ là **mô hình ngữ nghĩa**, không phải một Java object literal có các fields `owner` và `entryCount` mà ứng dụng được phép đọc. JVM có thể quản lý monitor object/metadata theo nhiều cách.

### Sở hữu monitor là theo object identity, không theo tên biến

```java
Object first = new Object();
Object alias = first;
synchronized (first) {
    synchronized (alias) {
        // Tái nhập cùng một monitor.
    }
}
```

Đây là một **fragment Java**, có thể đặt trong một method. Hai reference khác tên nhưng `first == alias`, nên hai synchronized statements là reentry vào **cùng monitor**.

Ngược lại, hai object khác nhau dù `equals` trả `true` vẫn có **monitor riêng**, vì khóa nội tại dựa trên **reference identity**, không dựa vào `equals` hoặc `hashCode`. `System.identityHashCode` cũng không phải địa chỉ monitor/raw memory address.

## 3. Cơ chế `monitorenter`

Trong JVMS 17, `monitorenter` là một opcode JVM instruction:

| Đặc tính | Nội dung |
| --- | --- |
| Mnemonic | `monitorenter` |
| Opcode | `194`, hexadecimal `0xC2` |
| Operand stack trước | `..., objectref` |
| Operand stack sau | `...` |
| Tác dụng | Thử acquire monitor của `objectref`; pop reference khỏi operand stack |

Mô hình hoạt động:

1. Nếu `objectref == null`, instruction ném `NullPointerException`.
2. Nếu monitor đang không có owner, thread hiện tại acquire; entry count thành 1.
3. Nếu thread hiện tại **đã** sở hữu monitor ấy, đây là reentrant enter; entry count tăng.
4. Nếu một thread khác đang là owner, thread hiện tại phải chờ để có thể acquire monitor theo cơ chế VM; không có đảm bảo FIFO.

```text
Operand stack trước:
  [..., objectref L]
                  ^
                  top

monitorenter

Operand stack sau:
  [...]

Monitor(L):
  entry count 0 -> owner T, count 1
  hoặc T đã owner -> count tăng
  hoặc thread khác owner -> T chờ acquire
```

Không nên hiểu “bytecode pop `objectref`” nghĩa GC không còn giữ reference tới lock trong thời gian synchronized block. Compiler/JVM phải quản lý đúng **root/lifetime** và exception exit path; `javac` thường lưu lock reference vào một **local variable ẩn** trước `monitorenter` để dùng lại khi `monitorexit`.

## 4. Cơ chế `monitorexit`

`monitorexit` là opcode đối ứng:

| Đặc tính | Nội dung |
| --- | --- |
| Mnemonic | `monitorexit` |
| Opcode | `195`, hexadecimal `0xC3` |
| Operand stack trước | `..., objectref` |
| Operand stack sau | `...` |
| Tác dụng | Pop reference, decrement entry count của monitor đang thuộc sở hữu thread |

Nếu decrement làm entry count về 0, thread **không còn là owner** và thread khác có thể thử acquire monitor.

Các exception quan trọng theo JVMS:

- `monitorexit` với `objectref == null` → `NullPointerException`.
- Nếu thread đang chạy **không sở hữu monitor** của object ấy → `IllegalMonitorStateException`.
- Một JVM thực thi kiểm tra **structured locking** có thể ném `IllegalMonitorStateException` khi các quy tắc structured locking bị vi phạm trong trường hợp mà specification mô tả.

```text
Thread T đã enter L hai lần:
  owner = T, entryCount = 2

monitorexit(L):
  owner = T, entryCount = 1
  (chưa thả monitor cho thread khác)

monitorexit(L):
  entryCount = 0
  owner = none
  (thread khác có thể acquire)
```

**Không được exit “một lần cho đủ”** khi đã nested synchronized vào cùng monitor nhiều lần. Compiler và VM phải bảo toàn độ sâu tái nhập ở những execution paths hợp lệ.

### Tính structured locking

JVMS `2.11.10` mô tả **structured locking**: trong một invocation, các lần monitor exit phải tương ứng với các lần enter, không exit nhiều hơn enter; trạng thái phải cân bằng khi invocation hoàn thành bình thường hoặc bất thường. JVM **được phép nhưng không bắt buộc** cưỡng chế mọi quy tắc này theo cách mà specification nêu đối với bytecode tổng quát.

Trong Java source hợp lệ, `synchronized` block/method có sự đảm bảo enter/exit tương ứng do compiler và JVM. **Không tự viết bytecode làm `monitorexit` trên monitor chưa sở hữu**; điều đó có thể ném `IllegalMonitorStateException`, không phải cách quản lý lock “chuyên sâu” hợp lệ.

## 5. Vì sao compiler phải tạo `try/finally` dạng bytecode?

Giả sử:

```java
void work(Object lock) {
    synchronized (lock) {
        doWork();
    }
}
```

Đây là **method fragment**, phụ thuộc `doWork()` được định nghĩa bên ngoài. Ngữ nghĩa Java yêu cầu monitor được thả **dù `doWork()` kết thúc bình thường hay ném exception**. Vì vậy bytecode của synchronized block có:

1. Đọc và giữ reference của object dùng làm lock.
2. `monitorenter` trước body.
3. `monitorexit` trên normal path.
4. **Exception handler** để thực hiện `monitorexit` rồi ném lại throwable trên abrupt path.

Sơ đồ mô phỏng (các BCIs không phải offset `javap` thật của một file cụ thể):

```text
aload lock
dup
astore monitorLocal
monitorenter

  [protected region]
  invoke doWork

aload monitorLocal
monitorexit
goto NORMAL_END

CATCH_ALL:
  astore thrown
  aload monitorLocal
  monitorexit
  aload thrown
  athrow

NORMAL_END:
  return
```

Exception table trong class file định tuyến throwable từ body tới handler phù hợp. `javac` cũng có thể phát sinh một handler bổ sung cho các trường hợp ngoại lệ xảy ra trong cleanup path tùy bytecode version/control flow.

### Vì sao không “nhét một monitorexit vào cuối method” là đủ?

Bởi vì body có thể:

- `return` sớm.
- `break` hoặc `continue` ra khỏi block.
- `throw` trực tiếp.
- Gặp exception từ method call, array access, field access, cast…
- Hoàn thành qua một nhánh điều kiện khác.

Đường thoát hợp lệ nào cũng phải giữ semantics monitor exit. Ở class-file level, compiler giải quyết bằng các branches, handlers và exit instructions phù hợp; không thể chỉ nhìn một dòng `return` ở Java source và suy lock bị kẹt.

## 6. Phương thức `synchronized`: cờ `ACC_SYNCHRONIZED`, không cần opcode tường minh

Một method được khai báo:

```java
public synchronized int read() {
    return count;
}
```

Đây là **fragment** trong một class có field `count`.

Thông thường `javac` không chèn `monitorenter`, `monitorexit` vào phần `Code` chỉ do modifier `synchronized` của method. Thay vào đó, `method_info.access_flags` có bit:

```text
ACC_SYNCHRONIZED = 0x0020
```

Khi thực hiện lời gọi method mang cờ này, JVM **tự** enter monitor trước khi thực thi method và **tự** exit khi method hoàn thành **bình thường hoặc bất thường**. Nếu method ném exception ra ngoài, monitor vẫn được thả khi invocation kết thúc.

### Method flag khác field hoặc class flag

- `ACC_SYNCHRONIZED` là một **method access flag** trong `method_info` (JVMS §4.6), không phải annotation Java.
- `ACC_SYNCHRONIZED` không có nghĩa “mọi method trong class dùng chung một global monitor”.
- Flag này không biến nested object fields thành thread-safe.
- JVM có một số cơ chế flags/locking ngoài class file; chúng không thay đổi ý nghĩa public bytecode method flag.

### Dùng monitor nào?

| Khai báo | Monitor gắn với | Ví dụ tương đương về ý nghĩa |
| --- | --- | --- |
| `synchronized void inc()` | `this` receiver object | `synchronized (this) { body }` |
| `static synchronized void reset()` | `Class` object đại diện cho class khai báo | `synchronized (Counter.class) { body }` |

**Khác nhau:** hai instances `Counter a` và `Counter b` có monitor riêng cho `a.inc()` và `b.inc()`. Trong khi đó `Counter.reset()` sử dụng monitor của `Counter.class`, không tự giành monitor của `a` hay `b`.

Nếu một class không `final` được kế thừa, hãy chú ý khi tự viết `getClass()`: đối tượng class runtime có thể là subclass khác so với class **khai báo static synchronized method**. Đừng tùy tiện thay `Counter.class` bằng `getClass()` khi diễn giải static monitor semantics.

## 7. Java 17 chạy được: xem block, instance method và static method

Tạo file **`MonitorBytecodeDemo.java`**:

```java
public class MonitorBytecodeDemo {
    private int count;

    public synchronized void incrementMethod() {
        count++;
    }

    public void incrementBlock() {
        synchronized (this) {
            count++;
        }
    }

    public synchronized int getCount() {
        return count;
    }

    public static synchronized String staticMarker() {
        return "class-monitor";
    }

    public static void main(String[] args) {
        MonitorBytecodeDemo counter = new MonitorBytecodeDemo();

        counter.incrementMethod();
        counter.incrementBlock();

        boolean holds;
        synchronized (counter) {
            holds = Thread.holdsLock(counter);
            counter.incrementMethod(); // Reentrant: cùng thread đã giữ monitor.
        }

        System.out.println("count=" + counter.getCount());
        System.out.println("holdsInside=" + holds);
        System.out.println("holdsOutside=" + Thread.holdsLock(counter));
        System.out.println("static=" + staticMarker());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 MonitorBytecodeDemo.java
java MonitorBytecodeDemo
```

**Stdout chính xác:**

```text
count=3
holdsInside=true
holdsOutside=false
static=class-monitor
```

Giải thích:

- `incrementMethod` và `incrementBlock` đều bảo vệ cùng field `count` bằng monitor của receiver.
- Khi vào `synchronized(counter)`, thread giữ monitor của `counter`; gọi `counter.incrementMethod()` vẫn hợp lệ vì intrinsic locks **reentrant**.
- `Thread.holdsLock(counter)` trả `true` trong vùng do chính thread hiện tại giữ monitor, và `false` sau khi thoát vùng (không có khóa nào khác ở thread ấy).
- `staticMarker` là static synchronized method nên dùng `MonitorBytecodeDemo.class`; nó không tham gia khóa riêng của `counter`.

### Xem bằng `javap`

```bash
javap -c -v -p MonitorBytecodeDemo
```

Ở `incrementMethod`, `getCount` và `staticMarker`, hãy tìm dòng method flags có **`ACC_SYNCHRONIZED`**. Trong `incrementBlock`, hãy tìm các instruction **`monitorenter`**, **`monitorexit`** và phần **Exception table**.

Một trích đoạn **mang tính cấu trúc, không phải output nguyên văn với offsets/indices đã đo**:

```text
public synchronized void incrementMethod();
  flags: (0x0021) ACC_PUBLIC, ACC_SYNCHRONIZED
  Code:
    ... getfield count ...
    ... putfield count ...
    return

public void incrementBlock();
  flags: (0x0001) ACC_PUBLIC
  Code:
    ... aload_0 ...
    ... monitorenter ...
    ... getfield count ...
    ... putfield count ...
    ... monitorexit ...
    ... monitorexit ...
    ... athrow ...
  Exception table:
    ... any ...
```

Các `...` là **chú thích lược bỏ**, không phải opcode Java hợp lệ hoặc dump đầy đủ. Class-file constant pool indexes, BCI offsets, stack map frames và exception-table boundaries phải xem trực tiếp bằng `javap`. Điều đáng tin là **mẫu phân biệt flag versus opcodes**.

## 8. Đọc method_info và Code attribute đúng thứ tự

Một method trong class file có thông tin như:

```text
method_info:
  access_flags: ACC_PUBLIC | ACC_SYNCHRONIZED
  name_index
  descriptor_index
  attributes:
    Code {
      max_stack, max_locals
      code[]
      exception_table
      ...
    }
```

Đây là sơ đồ, không phải dữ liệu binary class file được giải mã thực. Những điều cần kiểm:

1. `ACC_SYNCHRONIZED` nằm ở **method_info.access_flags**.
2. `Code` chứa bytecode nghiệp vụ, nhưng không bắt buộc chứa `monitorenter`/`monitorexit` tương ứng method-level lock.
3. Với `synchronized` block, compiler phát sinh instructions rõ ràng **trong `code[]`**.
4. Các exception handlers trong `Code.exception_table` của block bảo vệ việc thả monitor khi body ném exception.
5. Nếu một method vừa mang `ACC_SYNCHRONIZED` vừa chứa block `synchronized(other)`, có thể có **hai monitor khác nhau** đang được giữ (method monitor + block monitor).

### Opcode và flags không giống nhau

- `monitorenter = 0xC2`, `monitorexit = 0xC3` là **1-byte opcodes** trong JVM instruction stream.
- `ACC_SYNCHRONIZED = 0x0020` là **bitmask trong cấu trúc metadata của method**.
- Không tìm bit `0x0020` trong `Code` rồi kết luận đó là lệnh lock.
- Không tìm `monitorenter` trong mọi method marked synchronized rồi báo bytecode bị lỗi.

## 9. Exception trong synchronized block: vì sao lock vẫn được thả?

Tạo file **`MonitorExceptionDemo.java`**:

```java
public class MonitorExceptionDemo {
    private final Object lock = new Object();

    public void failInBlock() {
        synchronized (lock) {
            throw new IllegalStateException("block");
        }
    }

    public synchronized void failInMethod() {
        throw new IllegalStateException("method");
    }

    public synchronized String recover() {
        return "recovered";
    }

    public static void main(String[] args) {
        MonitorExceptionDemo demo = new MonitorExceptionDemo();

        try {
            demo.failInBlock();
        } catch (IllegalStateException e) {
            System.out.println("caughtBlock=" + e.getMessage());
        }

        synchronized (demo.lock) {
            System.out.println("blockReentered="
                    + Thread.holdsLock(demo.lock));
        }

        try {
            demo.failInMethod();
        } catch (IllegalStateException e) {
            System.out.println("caughtMethod=" + e.getMessage());
        }

        System.out.println("methodReentered=" + demo.recover());
    }
}
```

```bash
javac --release 17 MonitorExceptionDemo.java
java MonitorExceptionDemo
```

**Stdout xác định:**

```text
caughtBlock=block
blockReentered=true
caughtMethod=method
methodReentered=recovered
```

Mã trình bày hai cơ chế:

- `failInBlock` có monitor được acquire qua block; compiler tạo đường release kể cả khi `IllegalStateException` thoát ra.
- `failInMethod` mang method flag `ACC_SYNCHRONIZED`; VM đảm bảo implicit exit khi method kết thúc bất thường.
- Có thể acquire lại monitor sau exception; không bị kẹt vĩnh viễn vì exception ấy.

**Giới hạn thử nghiệm:** ví dụ chạy một thread, nên `blockReentered=true` tự nó chưa chứng minh một thread khác sẽ không bao giờ bị block nếu có lỗi. Bằng chứng chính về release trên mọi control path là **quy tắc ngôn ngữ/JVMS và bytecode cleanup logic**. Không dùng “chạy được một lần” để khẳng định code concurrent luôn không có race/deadlock.

## 10. Lệnh `athrow`, return và release ngầm khác gì?

Với method có `ACC_SYNCHRONIZED`:

- Trước khi method body chạy, VM enter monitor tương ứng.
- Khi method **normal return**, VM đảm bảo exit monitor của invocation.
- Khi method **abrupt completion** do exception chưa được xử lý trong method, VM đảm bảo exit trước khi truyền exception ra caller.
- Bytecode body có thể chứa `ireturn`, `areturn`, `return` hoặc `athrow`, nhưng **method lock không cần được thể hiện bằng opcode `monitorexit` tường minh ở mỗi điểm**.

Với synchronized block:

- Có `monitorenter` trước body.
- `monitorexit` trên normal exit.
- `monitorexit` qua bytecode exception-handling path trên abrupt exit.
- Java compiler phải lo **đúng lock object** được thả; nếu biểu thức `lock` bị đổi giá trị ở Java variable ngoài block, monitor object đã lấy vẫn là object được lưu tại thời điểm enter.

Ví dụ:

```java
Object lock = new Object();
Object original = lock;
synchronized (lock) {
    lock = new Object();
    System.out.println(Thread.holdsLock(original)); // true
}
```

Đây là **fragment** trong method. Biến `lock` đã trỏ object khác nhưng block vẫn đang sở hữu monitor của **`original`** cho tới khi kết thúc. Không đồng nghĩa “reassign reference mở khóa ngay”.

## 11. Reentrancy chi tiết: một thread vào cùng monitor nhiều lần

Intrinsic locks của Java là **reentrant**. Giả sử:

```java
class Nested {
    synchronized void outer() {
        inner();
    }

    synchronized void inner() {
        // Cùng receiver this, nên tái nhập cùng monitor.
    }
}
```

Đây là class minh họa, không có `main`.

Timeline:

```text
T gọi outer() trên obj
  enter monitor(obj): depth 0 -> 1

outer() gọi inner() cùng obj
  enter monitor(obj): depth 1 -> 2

inner() return
  implicit exit: depth 2 -> 1

outer() return
  implicit exit: depth 1 -> 0

Monitor của obj sẵn sàng cho thread khác.
```

**Reentrancy không phải fairness.** Java intrinsic monitor không cam kết thread nào chờ sẽ được chọn kế tiếp, không cho `tryLock(timeout)` kiểu `ReentrantLock`, và việc enter monitor theo cú pháp `synchronized` không cung cấp cơ chế interruptible lock acquisition giống `lockInterruptibly()`.

Tránh code giả định một thread đang `BLOCKED` chờ intrinsic monitor sẽ tự động ngừng chờ vì thread bị `interrupt()`. **Interrupt của `Object.wait` là chuyện khác**: waiting thread có thể ném `InterruptedException` sau khi reacquire monitor.

## 12. Instance synchronized vs static synchronized: không khóa nhau mặc định

Xét:

```java
class Ledger {
    private int instanceCount;
    private static int globalCount;

    synchronized void incrementInstance() {
        instanceCount++;
    }

    static synchronized void incrementGlobal() {
        globalCount++;
    }
}
```

Đây là class fragment. Monitor của `ledger.incrementInstance()` là object `ledger`; monitor của `Ledger.incrementGlobal()` là **`Ledger.class`**.

Hai thread có thể:

- Thread A sở hữu monitor của `ledger`.
- Thread B đồng thời sở hữu monitor của `Ledger.class`.
- Cả hai thực thi những method tương ứng mà không chặn nhau **vì khác monitor**, nếu không có synchronization khác.

Đừng dùng một instance synchronized method để bảo vệ static shared mutable field mà các thread khác có thể sửa qua static synchronized method — chúng **không tự dùng cùng lock**.

### Hai instance khác nhau cũng là hai monitors

```text
Ledger a   -> monitor(a)
Ledger b   -> monitor(b)
Ledger.class -> monitor(Ledger.class)

a.incrementInstance() và b.incrementInstance() có thể song song.
a.incrementInstance() và Ledger.incrementGlobal() có thể song song.
```

Để bảo vệ trạng thái chung, chọn **một lock strategy nhất quán** và đảm bảo mọi reads/writes liên quan đều tuân theo strategy đó.

## 13. Java Memory Model: monitor exit có nghĩa về visibility

`synchronized` không chỉ bảo vệ **mutual exclusion**. Nó còn tạo quan hệ thứ tự bộ nhớ theo JMM.

Với **cùng monitor M**, một **unlock của M** trong thread A **synchronizes-with** một **lock của M** tiếp theo trong thread B; từ các quy tắc happens-before, những writes trong A trước unlock có thể trở nên visible đúng cho reads của B sau lock khi truy cập dữ liệu được đồng bộ phù hợp.

```text
Thread A                          Thread B

lock(M)
sharedValue = 42
unlock(M) -------- sync-with ----> lock(M)
                                  read sharedValue => thấy writes
                                  unlock(M)

Điều kiện: cùng M và có thứ tự phù hợp.
```

**Không phải “mọi unlock ở A synchronizes-with mọi lock ở B”**. Monitor identity phải giống nhau, và thứ tự các synchronization actions phải phù hợp. Khóa không sửa **một data race** nếu có thread khác đọc/ghi cùng mutable state bên ngoài cơ chế đồng bộ ấy.

### `volatile` khác `synchronized`

- `volatile` cung cấp visibility/order semantics trên một biến cụ thể; một biểu thức như `count++` không được tự biến thành atomic chỉ vì `count` volatile.
- `synchronized` cung cấp mutual exclusion **và** monitor-based happens-before nếu threads dùng cùng lock.
- `AtomicInteger` thực hiện các operations atomic qua API riêng.
- `ReentrantLock` có memory synchronization effects được Java concurrency API định nghĩa, nhưng không triển khai bằng hai bytecode opcodes `monitorenter`/`monitorexit` cho lock API ấy.

Đừng đồng nhất GC write barriers/JIT memory barriers với Java source `synchronized` statements: chúng có mục đích/semantics khác nhau.

## 14. Java 17: hai threads tăng một counter an toàn

Tạo file **`MonitorCounterDemo.java`**:

```java
public class MonitorCounterDemo {
    private int counter;

    public synchronized void increment() {
        counter++;
    }

    public synchronized int value() {
        return counter;
    }

    public static void main(String[] args)
            throws InterruptedException {
        MonitorCounterDemo shared = new MonitorCounterDemo();

        Runnable job = () -> {
            for (int i = 0; i < 10_000; i++) {
                shared.increment();
            }
        };

        Thread a = new Thread(job, "worker-A");
        Thread b = new Thread(job, "worker-B");

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("expected=20000");
        System.out.println("actual=" + shared.value());
    }
}
```

```bash
javac --release 17 MonitorCounterDemo.java
java MonitorCounterDemo
```

**Stdout chính xác nếu threads hoàn thành bình thường:**

```text
expected=20000
actual=20000
```

Mỗi call `increment` cần acquire/release monitor của **cùng object `shared`**; vì vậy `counter++` (đọc, cộng, ghi) nằm trong critical section mutually exclusive. `value` cũng dùng monitor ấy, dù ở ví dụ `join()` đã đảm bảo các workers kết thúc trước khi main đọc.

Nếu bỏ `synchronized` khỏi `increment`, `counter++` không còn atomic và có thể **lost updates**; nhưng **không đảm bảo** mỗi lần chạy sẽ in dưới 20.000 — race có thể không lộ ra ở một lần thử. Điều đúng là chương trình khi ấy không có synchronization thích hợp để bảo đảm luôn được 20.000.

### Một số yêu cầu code review

- Guard **cả reads lẫn writes** của shared mutable state bằng cùng monitor hoặc một synchronization strategy hợp lệ.
- Không gọi `counter++` “atomic” chỉ vì Java có một opcode cộng; bytecode thường tách load/compute/store.
- Nếu lock lâu, throughput có thể giảm vì contention; chọn granularity phù hợp.
- Không tối ưu xóa synchronized một cách thủ công trên shared state.

## 15. `Object.wait`, `notify` và `notifyAll` liên hệ với monitor thế nào?

Ngoài việc enter/exit, Java monitor liên quan **wait sets**. Khi thread đang sở hữu monitor của object `lock`, nó có thể gọi:

- `lock.wait()`: tạm **nhả ownership của monitor của lock**, chờ notification/interruption/timeout theo overload/semantics; trước khi return hoặc throw phù hợp, thread **tái acquire monitor**.
- `lock.notify()`: chọn một thread đang chờ trên wait set của **cùng lock** để đánh thức theo quy tắc VM; **không nhả monitor ngay**.
- `lock.notifyAll()`: đánh thức toàn bộ threads trong wait set của object ấy để chúng tranh quyền reacquire.
- Các operations này yêu cầu thread hiện tại đang sở hữu monitor phù hợp; nếu không → `IllegalMonitorStateException`.

**Không có riêng một opcode JVM `wait` hoặc `notify` tương ứng**. Chúng là methods của `java.lang.Object` với implementation phối hợp monitor support của JVM.

### Vì sao luôn dùng `while` chứ không dùng `if` quanh `wait`?

Một thread được đánh thức không có nghĩa điều kiện nghiệp vụ đã trở thành đúng: có thể là **spurious wakeup**, thread khác đã thay đổi state, hoặc `notifyAll` đánh thức nhiều threads cùng lúc. Luôn kiểm tra điều kiện ở trong vòng lặp **khi đang giữ monitor**.

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // ready đúng tại thời điểm đang giữ lock
}
```

Đây là fragment nằm trong method khai báo/propagate `InterruptedException`, có field `ready` và object `lock` thích hợp.

### `Thread.sleep` khác `Object.wait`

`Thread.sleep(...)` **không tự thả monitors** đang được thread sở hữu. Ngủ 1 giây trong `synchronized` block có thể giữ thread khác chờ vào cùng monitor suốt thời gian ấy. `Object.wait()` thì release **monitor được wait**, rồi reacquire trước khi tiếp tục; nó không tự thả mọi monitor khác mà thread cũng đang giữ.

## 16. Java 17: ví dụ wait/notifyAll không phụ thuộc thứ tự khởi chạy

Tạo file **`MonitorWaitDemo.java`**:

```java
public class MonitorWaitDemo {
    static final class Gate {
        private boolean open;

        synchronized void await() throws InterruptedException {
            while (!open) {
                wait();
            }
        }

        synchronized void signal() {
            open = true;
            notifyAll();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();
        Thread worker = new Thread(() -> {
            try {
                gate.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            System.out.println("worker=passed");
        }, "waiter");

        worker.start();
        gate.signal();
        worker.join();

        System.out.println("main=done");
    }
}
```

```bash
javac --release 17 MonitorWaitDemo.java
java MonitorWaitDemo
```

**Stdout trong trường hợp không có interruption bên ngoài:**

```text
worker=passed
main=done
```

- Nếu worker chưa vào `await()` khi main gọi `signal()`, field `open` đã được đặt true; worker vào sau vẫn vượt qua, **không bị mất tín hiệu**.
- Nếu worker đã `wait()`, main có thể acquire monitor của Gate sau khi waiter release, đặt `open=true` rồi `notifyAll()`; worker phải reacquire monitor mới return từ `wait()`.
- `signal()` và `await()` là instance synchronized methods; monitor là `gate` (receiver).
- `join()` khiến dòng main in **sau** dòng worker ở đường chạy bình thường.

**Chú ý:** đây là demo synchronization correctness; không dùng nó để lập luận một sự kiện `notifyAll` chính xác tương ứng với một JVM opcode. Thread scheduling có thể thay đổi mà hai dòng output vẫn có thứ tự xác định nhờ `join()`.

## 17. `IllegalMonitorStateException` và `NullPointerException`

Hai lỗi hay bị nhầm:

### Không giữ monitor mà gọi wait/notify

```java
Object lock = new Object();
try {
    lock.notify();
} catch (IllegalMonitorStateException expected) {
    System.out.println("not-owner");
}
```

Fragment này chạy được khi đặt trong `main`. Kết quả là `not-owner` vì caller chưa giữ monitor của `lock`. Để đúng, gọi:

```java
synchronized (lock) {
    lock.notifyAll();
}
```

### Biểu thức lock là null

```java
Object lock = null;
synchronized (lock) {
    System.out.println("never");
}
```

Đây là fragment. Lúc monitor enter trên null, runtime ném `NullPointerException`; body không chạy. Không có một monitor đặc biệt đại diện cho `null`.

### `IllegalMonitorStateException` khác lock contention

Một thread hợp lệ đang chờ acquire một monitor do thread khác giữ **không mặc định ném `IllegalMonitorStateException`** chỉ vì chờ. Exception này liên quan các operations/monitor ownership không hợp lệ, như `notify()` ngoài synchronized và `monitorexit` khi không phải owner.

## 18. Synchronized method không tương đương khóa mọi state bên trong object graph

Giả sử class:

```java
class Basket {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    synchronized void add(String item) {
        items.add(item);
    }

    java.util.List<String> rawItems() {
        return items;
    }
}
```

Đây là class fragment. Dù `add` synchronized, method `rawItems` trả trực tiếp một mutable list. Caller có thể sửa list mà **không giữ monitor Basket**, phá dữ liệu hoặc tạo race.

**Khóa monitor chỉ bảo vệ các hành động phối hợp dùng chính monitor đó.** Nó không tự đổi tính thread-safe của mọi object tham chiếu bên trong, không ngăn code bên ngoài giữ reference mutable và sử dụng sai.

Một API tốt có thể:

- Không phơi trực tiếp mutable internal representation.
- Trả immutable snapshot/copy phù hợp.
- Yêu cầu mọi thao tác vào state được đồng bộ đúng.
- Dùng collections hoặc concurrent abstractions phù hợp thay vì phức tạp hóa monitor protocol.

## 19. Deadlock: hai monitors khóa ngược thứ tự

Mỗi `synchronized` có thể đúng cục bộ nhưng hệ thống vẫn bị **deadlock** nếu hai threads giữ lock theo thứ tự ngược:

```text
Thread A:
  synchronized(L1) {
    synchronized(L2) { ... }
  }

Thread B:
  synchronized(L2) {
    synchronized(L1) { ... }
  }

A giữ L1, chờ L2.
B giữ L2, chờ L1.
=> cycle of wait-for dependencies.
```

Đây là ví dụ ý niệm, **không phải chương trình được tạo để cố tình treo JVM**.

Biện pháp:

- Định nghĩa và tuân thủ **global lock ordering** nhất quán.
- Giữ critical sections ngắn; tránh gọi vào callbacks, external code hoặc I/O lâu khi đang giữ locks.
- Không lấy lock trên objects public như string interned/class literals trừ khi chính sách ownership rõ ràng.
- Dùng `ReentrantLock.tryLock` hoặc abstractions cấp cao nếu bài toán cần timeouts/interruptible acquisition.
- Dùng thread dumps để xác minh owner và blocked dependencies.

**Reentrant không có nghĩa “không thể deadlock”**. Reentrancy chỉ cho phép cùng thread vào lại **cùng monitor**, không xử lý cycles giữa **hai monitors khác nhau**.

## 20. Thread dumps: BLOCKED khác WAITING như thế nào?

Khi một Java thread cố enter một intrinsic monitor đã do thread khác giữ, nó có thể xuất hiện trong trạng thái **`BLOCKED`**. Khi nó đã gọi `Object.wait()` và đang chờ trên wait set, thường thấy trạng thái **`WAITING`** (hoặc **`TIMED_WAITING`** với timeout), tùy thực tế.

Bảng khái quát:

| Tình huống | State thường thấy | Vai trò monitor |
| --- | --- | --- |
| Chờ vào `synchronized(lock)` vì thread khác giữ lock | `BLOCKED` | Đang chờ acquire ownership |
| Gọi `lock.wait()` không timeout | `WAITING` | Đã release monitor của lock và chờ được tái acquire theo quy tắc |
| Gọi `lock.wait(timeout)` | `TIMED_WAITING` | Timed wait |
| Gọi `Thread.sleep(timeout)` | `TIMED_WAITING` | **Không release** locks đang giữ |
| `LockSupport.park` | `WAITING` | Parking khác monitor wait set |
| Chạy code không chờ monitor | Có thể `RUNNABLE` | Không kết luận không có contention chỉ từ một snapshot |

Thread state là **ảnh chụp**; thread có thể đổi trạng thái rất nhanh. Dùng nhiều thread dumps và timeline nếu điều tra production.

### Công cụ Java 17

```bash
jcmd <PID> Thread.print -l
jstack -l <PID>
```

`<PID>` là placeholder của một Java process thực đang chạy và có quyền attach. `jcmd`/`jstack` có thể in monitor ownership, blocked/waiting threads và deadlock information tùy build/options. Một thread dump thường hiển thị `- locked <...>` hoặc `- waiting to lock <...>`; các object IDs trong diagnostic output **không phải Java API identity** ổn định để làm logic application.

Nếu gặp lỗi **Java-level deadlock**, dùng nhiều snapshots, xem threads đang giữ và chờ monitors nào, rồi tìm thứ tự acquire trái ngược trong source. Không kết luận mọi thread `WAITING` đều deadlock; thread pool idle, `Object.wait` và `LockSupport.park` hợp lệ cũng có WAITING.

## 21. Tại sao `synchronized` có thể nhanh hơn kỳ vọng?

HotSpot có các optimizations và implementation techniques khác nhau tùy release:

- Fast paths cho uncontended monitor acquisition.
- JIT inlining và compiler optimizations quanh monitor regions.
- **Escape analysis / lock elimination** khi compiler chứng minh một lock object không thể được thread khác quan sát trong compiled graph.
- Cơ chế quản lý monitor metadata, inflation/deflation và đường slow path khi contention.
- Tối ưu các trường hợp nested/reentrant locking hoặc code motion khi vẫn bảo toàn Java semantics.

Trên **HotSpot Java 17**, không được bê nguyên mô tả locking của JDK 8 hoặc JDK 25 áp như layout chắc chắn: biased locking đã **bị tắt mặc định trong các release trước Java 17**, các thuật toán monitor và object header có thể thay đổi giữa các versions.

### Lock elimination khác bỏ synchronized khỏi source

```java
static int localOnly(int a) {
    Object privateLock = new Object();
    synchronized (privateLock) {
        return a + 1;
    }
}
```

Method fragment này có private lock không thoát theo source; C2 **có thể** loại bỏ monitor operations và thậm chí allocation nếu đủ điều kiện. Nhưng compiler vẫn phải bảo toàn semantics; **không có guarantee** lock sẽ được eliminate trên mọi path/JDK build.

Điều này không trao quyền xóa `synchronized` thủ công trong application shared-state logic. Với object thật sự được chia sẻ, bỏ monitor có thể gây data race.

## 22. `monitorenter`/`monitorexit` trong bytecode có nghĩa JIT luôn thực hiện lock/unlock vật lý?

Không. Bytecode xác định **ngữ nghĩa JVM**; HotSpot interpreter/JIT được phép tối ưu implementation:

- Interpreter có thể thực hiện entry/exit qua VM/runtime mechanisms thích hợp.
- C1/C2 sinh machine code tương đương về hành vi, không phải lúc nào cũng một call runtime cho mỗi monitorenter.
- C2 có thể eliminate monitor nếu chứng minh thread-confined/no observable synchronization effect, hoặc dùng fast path.
- Một số monitors có thể được inflated khi contention/special operations; trạng thái lock bên trong không phải điều Java source được phép phụ thuộc.
- Deoptimization phải bảo tồn logical monitor ownership/state khi chuyển execution representation.

Vì vậy `javap -c` có `monitorenter` không chứng minh native instructions thực tế luôn gồm một lệnh hardware lock đúng tại BCI ấy. Để xem máy mã cần công cụ JIT diagnostics, profiling và build phù hợp, không dùng `javap` như native disassembler.

### Đừng nhầm `monitorexit` với memory reclamation

`monitorexit` chỉ liên quan monitor ownership/synchronization. Nó **không xóa object, không gọi GC, không close file/socket**, và không tự release mọi resources bên trong critical section. `synchronized` không thay thế `try-with-resources` cho I/O resources.

## 23. Tại sao giữ lock khi gọi method khác có thể nguy hiểm?

Ví dụ:

```java
synchronized (lock) {
    callback.run();
}
```

Đây là fragment. Bạn vẫn sở hữu monitor `lock` trong thời gian `callback.run()`. Nếu callback:

- Chờ một lock khác theo thứ tự nguy hiểm.
- Thực hiện blocking I/O hoặc network call.
- Gọi code có thể quay lại cùng object theo một protocol phức tạp.
- Gọi `wait` trên một monitor khác khi vẫn đang giữ `lock`.
- Giữ lock trong một tác vụ kéo dài.

thì tăng contention hoặc deadlock risk. **Callback re-enter cùng lock** tự nó hợp lệ do reentrancy, nhưng một protocol có nhiều locks vẫn có thể deadlock.

Thiết kế tốt thường:

1. Thu thập snapshot dưới lock.
2. Thả lock.
3. Gọi external callback ngoài vùng bảo vệ nếu business invariant cho phép.
4. Dùng immutable messages/queues cho async processing khi phù hợp.

Không tự động “đưa mọi callback ra ngoài synchronized” nếu state invariants yêu cầu thao tác nguyên tử; hãy xác định đúng atomicity contract rồi refactor.

## 24. Java 17: static monitor và instance monitor thật sự độc lập

Tạo file **`ClassMonitorDemo.java`**:

```java
public class ClassMonitorDemo {
    private int instanceValue;
    private static int classValue;

    public synchronized void updateInstance() {
        instanceValue++;
    }

    public static synchronized void updateClass() {
        classValue++;
    }

    public static void main(String[] args) {
        ClassMonitorDemo obj = new ClassMonitorDemo();

        boolean instanceHeld;
        boolean classHeld;
        synchronized (obj) {
            instanceHeld = Thread.holdsLock(obj);
            classHeld = Thread.holdsLock(ClassMonitorDemo.class);
        }

        obj.updateInstance();
        updateClass();

        System.out.println("instanceHeld=" + instanceHeld);
        System.out.println("classHeld=" + classHeld);
        System.out.println("instanceValue=" + obj.instanceValue);
        System.out.println("classValue=" + classValue);
    }
}
```

```bash
javac --release 17 ClassMonitorDemo.java
java ClassMonitorDemo
```

**Stdout:**

```text
instanceHeld=true
classHeld=false
instanceValue=1
classValue=1
```

Trong `synchronized(obj)`, thread giữ monitor của `obj` nhưng **không** vì thế sở hữu `ClassMonitorDemo.class`. Hai `update...` methods sau đó lần lượt cập nhật những fields riêng. Ví dụ giúp phân biệt monitors; nó **không phải stress test concurrency**, không chứng minh bản thân tất cả fields/static state đã thread-safe khi có nhiều methods không đồng bộ cùng truy cập.

## 25. Không phải mọi method đều có thể khai báo synchronized tùy ý

Java language có các quy tắc về modifier:

- **Constructors không được khai báo `synchronized`** trong Java source. Có thể dùng synchronized block bên trong constructor khi thật sự phù hợp, nhưng constructor escape/this publication cần được xem xét kỹ.
- Abstract methods không có body để thực thi monitor theo cách synchronized method thông thường; khai báo `abstract synchronized` không hợp lệ ở Java source.
- Interface default/static methods với body có các giới hạn về modifier `synchronized` trong Java source, dù có thể chứa synchronized blocks bên trong.
- Một method có `synchronized` modifier là một class-file method với `ACC_SYNCHRONIZED`; không xem nó như wrapper tự động sinh `synchronized(this)` ở source-level metadata.

**Không tự viết/mutate class file flags không hợp lệ** rồi suy rằng JVM phải chấp nhận. Các ràng buộc flags theo JVMS §4.6, language rules và verifier liên quan đến version class file cụ thể.

## 26. So sánh `synchronized`, `ReentrantLock` và atomic operations

| Nhu cầu | `synchronized` | `ReentrantLock` | `AtomicInteger` |
| --- | --- | --- | --- |
| Mutual exclusion cho critical section | Có, bằng intrinsic monitor | Có, qua explicit lock API | Chỉ operation atomic trên giá trị/kiểu của nó |
| Reentrancy | Có | Có theo class implementation | Không áp dụng như monitor lock |
| Auto unlock khi block/method hoàn thành | Có | Cần `unlock()` trong `finally` | Không cần unlock |
| Timeout khi acquire | Không có cú pháp `synchronized` timeout | Có `tryLock(timeout, unit)` | Không áp dụng |
| Interruptible acquisition API | Không có tương đương `lockInterruptibly` | Có | Không áp dụng |
| Condition waiting | `wait/notify/notifyAll` | `Condition.await/signal` | Không tự cung cấp Condition |
| Fairness policy cấu hình | Không | Có constructor fair mode (có giới hạn semantics) | Không áp dụng |
| JVM `monitorenter`/`monitorexit` bytecode | Block có; method dùng method flag | Không phải biểu diễn chủ yếu của API | Không |
| Bảo vệ nhiều invariants một cách nguyên tử | Được nếu dùng cùng monitor đúng | Được nếu dùng cùng lock đúng | Cần thiết kế khác hoặc CAS protocol |

Đừng chọn API chỉ vì nghĩ “bytecode monitorenter chậm hơn lock API”. Performance phụ thuộc contention, JDK, fast paths, operating system, workload và độ dài critical section. Chọn contract đúng (timeout, fairness, interruptibility, composability) rồi đo.

## 27. Các lỗi thường gặp khi đọc `javap`

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Không có `monitorenter` trong synchronized method nên nó không khóa” | `ACC_SYNCHRONIZED` buộc JVM xử lý implicit enter/exit |
| “Một block phải chỉ có một `monitorexit`” | Compiler có thể có normal và exception cleanup paths, nên nhiều instruction sites |
| “Mỗi `monitorexit` trong file chạy mỗi lần vào block” | Chỉ control-flow path thực tế được thực thi |
| “`ACC_SYNCHRONIZED` = opcode 0x20” | Đây là method access flag; opcodes là 0xC2/0xC3 |
| “Static synchronized dùng monitor của một instance bất kỳ” | Dùng `Class` object tương ứng |
| “`javap` không thấy lock object local nên không có reference” | Compiler có thể lưu monitor reference ở local ẩn |
| “Block exception handler nghĩa exception bị nuốt” | Handler thường cleanup monitor rồi `athrow` lại |
| “`return` trong block bỏ qua release” | Compiler phải đưa mọi normal exit qua cleanup hợp lệ |
| “Nested synchronized cùng object gây tự deadlock” | Intrinsic monitors reentrant |
| “Synchronized bảo vệ mọi field dù code ngoài bỏ qua lock” | Các truy cập phải đồng bộ nhất quán |
| “Monitor exit chỉ giúp thread khác vào, không ảnh hưởng visibility” | Unlock/lock trên cùng monitor tạo JMM happens-before phù hợp |
| “`notify()` thả monitor ngay” | Thread gọi notify vẫn giữ monitor tới khi exit |
| “`wait()` không thả lock” | Wait nhả monitor của object được wait và reacquire trước khi tiếp tục |
| “`sleep()` thả tất cả locks” | Sleep không release intrinsic monitors |
| “`IllegalMonitorStateException` xảy ra chỉ vì lock đang bận” | Nó báo ownership/monitor operation không hợp lệ |
| “`Thread.State.BLOCKED` giống `WAITING`” | Blocked for monitor entry khác waiting on wait set/park |
| “Bật GC sẽ giải phóng monitor đang có owner” | GC không được phá synchronization semantics của live objects |
| “Lock elimination nghĩa source synchronized không cần thiết” | JIT chỉ bỏ khi chứng minh semantics an toàn trong một context cụ thể |

## 28. Quy trình thực hành giải thích một đoạn synchronized trên HotSpot

**Bước 1 — Chốt mục tiêu.** Bạn đang hỏi compiler phát sinh opcode nào, thread vì sao BLOCKED, hay vì sao synchronized code chậm? Mỗi câu dùng công cụ khác nhau.

**Bước 2 — Xem source form.** Đây là `synchronized(lock)` block hay `synchronized` modifier của method? Instance hay static?

**Bước 3 — Xác định lock identity.** Lock có thể là `this`, `SomeClass.class`, field `private final Object lock` hoặc một object được truyền vào. Tên variable không quan trọng bằng **reference identity**.

**Bước 4 — Biên dịch Java 17:**

```bash
javac --release 17 MonitorBytecodeDemo.java
javap -v -c -p MonitorBytecodeDemo
```

**Bước 5 — Với block:** tìm `monitorenter`, `monitorexit` trên normal path và exception handler. Đừng nhầm số opcode sites với số lần runtime lock/unlock.

**Bước 6 — Với method:** xem method flags có `ACC_SYNCHRONIZED`. JVM xử lý implicit monitor enter/exit tại invocation/return, không đòi `Code` có opcode monitor tường minh.

**Bước 7 — Đọc Java semantics:** mọi control flow phải release monitor; reentry cùng thread được phép; null lock ném NPE; caller phải sở hữu monitor nếu gọi `wait/notify`.

**Bước 8 — Xác nhận JMM:** những threads đọc/ghi shared state có thực sự dùng **cùng monitor**? Có code đọc ngoài synchronized làm mất happens-before không?

**Bước 9 — Điều tra runtime contention:** xem `jcmd <PID> Thread.print -l`, JFR Java Monitor Blocked events khi có trên build/settings, CPU/latency timeline. Một thread dump là snapshot, không phải thống kê dài hạn.

**Bước 10 — Nếu cần tuning:** giảm độ dài critical section, tránh blocking I/O và external callbacks trong lock, xem lock ordering. Không xóa synchronized chỉ vì profiler báo contention.

**Bước 11 — Chỉ khi nghiên cứu codegen:** dùng compiler diagnostics/assembly tools phù hợp đúng JDK/CPU và biết rằng JIT có thể thay bytecode monitor operations bằng fast paths hoặc lock elimination, trong khi semantics vẫn giữ nguyên.

## 29. Câu hỏi tự kiểm tra

**Câu 1.** Khối `synchronized(obj)` xuất hiện trong bytecode bằng những instruction nào?

**Đáp:** `monitorenter` và `monitorexit`, với exception-handling path đảm bảo exit.

**Câu 2.** Một instance method có `ACC_SYNCHRONIZED` mà `javap -c` không in `monitorenter`. Có lỗi không?

**Không.** Method monitor enter/exit được JVM xử lý ngầm qua invocation/return semantics.

**Câu 3.** Static synchronized method dùng monitor của ai?

**Đối tượng `Class` đại diện class khai báo method**, ví dụ `Counter.class`, không phải monitor của một instance.

**Câu 4.** `monitorenter` nhận operand gì và để lại gì?

Pop `objectref` từ operand stack rồi thực hiện acquire; các phần tử stack trước đó vẫn còn.

**Câu 5.** Thread đã enter cùng object hai lần; sau một `monitorexit`, thread khác có thể vào chưa?

**Chưa** nếu entry count vẫn còn 1; thread hiện tại vẫn sở hữu monitor.

**Câu 6.** Khi body trong synchronized block ném exception, điều gì xảy ra?

Compiler/JVM thực hiện cleanup để exit monitor trước khi exception được truyền ra (trừ những exceptional VM termination semantics ngoài luồng ứng dụng thông thường).

**Câu 7.** Vì sao `lock.notifyAll()` cần ở trong synchronized?

Caller phải sở hữu monitor của `lock`; nếu không có thể ném `IllegalMonitorStateException`.

**Câu 8.** `lock.wait()` và `Thread.sleep()` khác gì về monitor?

`wait` release monitor của `lock` và reacquire trước khi tiếp tục; `sleep` không tự thả monitors.

**Câu 9.** Tại sao `if (!ready) wait()` chưa đủ an toàn?

Có spurious wakeups và condition có thể thay đổi trước khi reacquire; dùng `while (!ready) wait()`.

**Câu 10.** Một thread vào `synchronized(a)` rồi gọi instance synchronized method của `b`, khi `a != b`. Có phải reentry cùng lock?

**Không.** Hai monitors khác nhau; thread có thể giữ **đồng thời** hai locks, làm phát sinh nguy cơ deadlock nếu lock order không nhất quán.

**Câu 11.** `monitorexit` có tự xóa object khỏi heap không?

**Không.** Nó thả ownership/reentrancy depth và tạo synchronization effects, không trực tiếp reclaim memory.

**Câu 12.** `synchronized` dùng cùng monitor trong hai threads mang lại điều gì ngoài mutual exclusion?

Quan hệ memory ordering **unlock synchronizes-with later lock**, tạo happens-before phù hợp cho reads/writes bảo vệ đúng.

**Câu 13.** Một phương thức được JIT tối ưu loại monitor operation, vậy class file `ACC_SYNCHRONIZED` có biến mất không?

**Không nhất thiết và không được suy vậy.** JIT có thể loại runtime work khi chứng minh an toàn mà không sửa Java-level method declaration/class-file flag.

**Câu 14.** Lệnh nào giúp xem cờ method và bytecode trên Java 17?

`javap -v -c -p ClassName`. `-v` hiển thị flags, `-c` hiển thị bytecode; compiler/native machine code là phạm vi công cụ khác.

## 30. Nguồn tài liệu chuẩn

- [JVMS Java SE 17 2.11.10 — Synchronization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.10): implicit monitor handling, structured locking và quyền của JVM implementation.
- [JVMS Java SE 17 3.14 — Synchronization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-3.html#jvms-3.14): cách Java source synchronized block được biên dịch, exception handler và phân biệt synchronized method.
- [JVMS Java SE 17 4.6 — Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.6): `method_info` và `ACC_SYNCHRONIZED` (0x0020).
- [JVMS Java SE 17 6.5 — monitorenter](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.monitorenter): operand stack, owner/entry count, NPE và reentrancy.
- [JVMS Java SE 17 6.5 — monitorexit](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.monitorexit): operand stack, exit count, IllegalMonitorStateException, exception path.
- [JLS Java SE 17 17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1) và [17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): monitor, unlock/lock và memory ordering.
- [Java SE 17 `Object.wait`, `notify`, `notifyAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): ownership, wait set, re-acquisition và spurious wakeups.
- [Java SE 17 `Thread.holdsLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)): kiểm tra current thread đang sở hữu monitor.
- [Java SE 17 `javap` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem class-file flags, Code attribute, exception tables.
- [Java SE 17 `jcmd` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print` và VM diagnostics.
- [Java SE 17 `ReentrantLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): so sánh intrinsic lock với explicit lock APIs.
- [OpenJDK JEP 374 — Disable and Deprecate Biased Locking](https://openjdk.org/jeps/374): bối cảnh khác biệt giữa các bản HotSpot trong monitor implementations.

**Ghi nhớ:** **synchronized block** được `javac` biểu diễn bằng **`monitorenter`/`monitorexit`** cộng với cleanup paths; **synchronized method** được đánh dấu bằng **`ACC_SYNCHRONIZED`** để JVM enter/exit ngầm. Cả hai dùng **monitor theo object identity**, hỗ trợ **reentrancy**, **mutual exclusion** và **happens-before trên cùng monitor**, nhưng không tự bảo đảm fairness, không xóa deadlock và không tự làm dữ liệu an toàn nếu có đường đọc/ghi bỏ qua lock. Muốn hiểu đúng mã Java 17, hãy nối **source → class-file flags/bytecode → exception handling → monitor ownership → JMM** rồi mới nghiên cứu những tối ưu nội bộ HotSpot.
