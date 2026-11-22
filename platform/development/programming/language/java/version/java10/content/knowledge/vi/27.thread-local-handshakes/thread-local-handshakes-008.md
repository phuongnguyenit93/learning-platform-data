# Java 10 — Handshake theo luồng: phân biệt cơ chế nội bộ JVM với API đồng bộ cho mã Java

## 1. Mục tiêu bài học

**Thread-Local Handshakes** là một cải tiến **bên trong HotSpot JVM**, được đưa vào Java 10 qua **JEP 312 — Thread-Local Handshakes**. Mục đích chính là cho phép JVM thực hiện một số thao tác liên quan đến **một JavaThread cụ thể**, hoặc phối hợp các JavaThreads theo từng luồng, **không luôn phải đưa tất cả Java threads vào cùng một global safepoint**.

Đây **không phải** một API Java mới để đồng bộ các biến dùng chung trong ứng dụng.

Hai mệnh đề cần ghi nhớ ngay từ đầu:

- **JVM-side handshake:** cơ chế phối hợp giữa những phần của **JVM** và JavaThreads để thực hiện các thao tác nội bộ khi thread ở trạng thái an toàn cho VM.
- **Java application synchronization:** lập trình viên dùng `synchronized`, `Lock`, `volatile`, `AtomicInteger`, `CountDownLatch`, `Future` và các API `java.util.concurrent` để bảo đảm tính đúng đắn khi các tác vụ Java chạy đồng thời.

Không có public method `Thread.handshake(Runnable)` trong Java SE. `ThreadLocal<T>` cũng **không phải** Thread-Local Handshake.

Sau bài này, bạn sẽ:

1. Hiểu JEP 312 và tại sao HotSpot cần cơ chế handshake theo luồng.
2. Phân biệt **global safepoint**, **thread-local handshake**, **Java monitor**, **lock** và **task-completion signal**.
3. Hiểu handshake callback là **JVM operation**, không phải một `Runnable` tùy ý trong ứng dụng.
4. Phân biệt atomicity, visibility, ordering/happens-before và coordination.
5. Chọn `synchronized`/`ReentrantLock`/atomics/volatile đúng với từng loại shared state.
6. Dùng `CountDownLatch`, `Future.get` và `Thread.join` để chờ đúng, không dùng `Thread.sleep` như một phép đồng bộ.
7. Hiểu các giới hạn khi xem thread dump, safepoint log và handshake log.
8. Tránh các suy luận sai về virtual threads trên Java 21+.
9. Chạy ba chương trình Java 17+ và đối chiếu stdout thật.
10. Áp dụng checklist code review cho những lỗi concurrency liên quan.

**Special Note:** chỉ sử dụng các kiến thức **vẫn còn áp dụng trên Java hiện đại**. Vì đây là tính năng nội bộ JVM, không coi tên hàm C++ hoặc một diagnostic flag cũ là Java SE public API ổn định. Các ví dụ dùng Java 17+ thay cho lệnh/technique đã legacy.

## 2. Thread-Local Handshake thực chất là gì?

Trong JVM, một số nhiệm vụ liên quan đến thread cần quan sát hoặc thay đổi trạng thái JVM theo cách **an toàn**. Ví dụ khái niệm: VM muốn xử lý một số thông tin liên quan đến **JavaThread A**.

Theo phương án sử dụng global safepoint, JVM phải phối hợp để **tất cả JavaThreads liên quan** đạt một trạng thái đồng bộ toàn cục trước khi tiến hành VM operation.

JEP 312 bổ sung hạ tầng để:
- Nhắm thao tác VM tới **một target JavaThread**;
- Hoặc lên lịch một thao tác cho **nhiều JavaThreads**, mỗi luồng tham gia theo cơ chế riêng;
- Hoàn tất từng thao tác khi target ở trạng thái được coi là **handshake-safe**;
- Tránh phải dùng một global safepoint cho **mọi** thao tác nhỏ cần dữ liệu một luồng.

### 2.1. JVM callback khác Java application callback

JEP 312 mô tả **handshake operation** là một callback do hạ tầng JVM quản lý, được thực hiện khi target ở trạng thái an toàn theo quy tắc VM.

Callback này có thể được thực hiện:
- Bởi **chính target JavaThread** khi nó tới một điểm kiểm tra/an toàn;
- Hoặc bởi **VM thread/handshaker thích hợp** khi target đã ở trạng thái an toàn và bị giữ lại để không thay đổi trạng thái cần quan sát.

**Không suy rằng callback nhất thiết chạy trong target JavaThread.** Việc ai thực hiện phụ thuộc thiết kế HotSpot và target state. Quan trọng hơn, callback này **không** phải `Consumer<Thread>` hoặc `Runnable` do ứng dụng gọi trực tiếp.

### 2.2. “An toàn cho VM” khác “thread-safe cho shared Java object”

Một target JavaThread đang **handshake-safe** chỉ có nghĩa **JVM có thể xử lý một loại VM operation phù hợp trong điều kiện đó**. Nó không chứng minh:

- Một đối tượng `Order` đang được khóa;
- Một chuyển tiền giữa hai tài khoản đã hoàn tất;
- Mọi shared fields đều được publish theo Java Memory Model;
- Không có data race ở `counter++`;
- Các Java threads khác đã chờ cùng một `CountDownLatch`;
- Tất cả locks của ứng dụng đã được giải phóng.

**VM internal safety** và **application data safety** phục vụ hai bài toán khác nhau.

## 3. Global safepoint và thread-local handshake

### 3.1. Global safepoint

Một global safepoint phối hợp các JavaThreads để thực hiện VM operation cần trạng thái toàn cục thích hợp.

```text
Thời gian ---------------------------------------------------->

JavaThread A: [RUN] ----- | VM-SAFE / WAIT | ----- [RUN]
JavaThread B: [RUN] ----- | VM-SAFE / WAIT | ----- [RUN]
JavaThread C: [RUN] ----- | VM-SAFE / WAIT | ----- [RUN]

VM operation:              [ GLOBAL OP ]
                           <----------->
                           Global safepoint
```

Sơ đồ khái niệm, không phải timeline thực tế chính xác của một GC. Những JVM/VM threads nhất định vẫn có thể làm việc khi Java mutators đã ở safepoint.

### 3.2. Handshake cho một thread

```text
Thời gian ---------------------------------------------------->

JavaThread A: [RUN] ---- | HANDSHAKE | --------- [RUN]
JavaThread B: [RUN] ---------------------------- [RUN]
JavaThread C: [RUN] ---------------------------- [RUN]

VM request:          [operation for A]
                      không bắt B/C vào
                      cùng global safepoint
```

Nếu chỉ cần thao tác lên A, B/C **không phải đồng loạt dừng chỉ vì handshake này**. Tuy nhiên, B/C vẫn có thể bị tạm dừng vì:
- Một global safepoint khác;
- GC/VM operation độc lập;
- Đang chờ một Java monitor hoặc lock;
- OS scheduler hoặc I/O;
- Các nguyên nhân riêng của mỗi thread.

Do đó không nói “handshake bảo đảm mọi thread khác luôn chạy không gián đoạn”.

### 3.3. Handshake cho nhiều threads

JEP 312 cũng cho phép phối hợp trên nhiều threads mà mỗi thread **hoàn tất thao tác riêng và có thể tiếp tục**, không phải buộc tất cả cùng chờ tại một global barrier giống toàn bộ global safepoint.

Điều này giúp JVM linh hoạt hơn trong những hoạt động liên quan thông tin per-thread. Nhưng nó không loại bỏ nhu cầu sử dụng **global safepoints** khi một VM operation thật sự cần tính nhất quán toàn cục.

### 3.4. Polling và trạng thái handshake-safe

HotSpot có những cơ chế **polling/safepoint checks** được thực thi tại các điểm thích hợp. Khi có handshake request, VM phải xác định target đã ở trạng thái phù hợp trước khi xử lý operation.

Một JavaThread có thể:
- Tự đạt điểm polling khi chạy Java code;
- Đang ở trạng thái blocked/native mà VM xác định có thể xử lý an toàn;
- Chưa đạt điều kiện xử lý ngay; handshake phải chờ thích hợp.

**Không được coi** handshake như việc CPU bắt đầu chạy một đoạn mã tùy ý chen vào bất kỳ bytecode nào. Đây là cơ chế phối hợp có điều kiện an toàn do HotSpot kiểm soát.

## 4. JEP 312 cải thiện điều gì và không cải thiện điều gì?

### Có thể cải thiện

- Giảm nhu cầu global safepoint ở những VM operations chỉ cần một số threads.
- Giảm mức độ phối hợp không cần thiết với threads không liên quan.
- Hỗ trợ những công việc VM/tooling cần truy cập thread state phù hợp.
- Cho phép các threads đã xử lý xong handshake tiếp tục theo chính sách VM, thay vì nhất thiết chờ tất cả cùng vào một trạng thái global.

### Không tự động làm được

- Loại bỏ mọi STW GC pause.
- Bảo đảm handshake luôn xong trong thời gian cố định.
- Thay đổi Java Memory Model.
- Biến `int counter++` thành atomic.
- Tạo ra một public `Thread.handshake` API.
- Bảo vệ invariants của đối tượng nghiệp vụ.
- Đảm bảo ứng dụng không còn deadlock.
- Khiến mọi lệnh đọc thread state mặc nhiên là handshake.
- Cho phép người dùng tự gọi các hàm HotSpot C++ nội bộ trong Java thông thường.

Một HotSpot version có thể thay đổi cách các subsystems dùng handshake. Kiến thức cần giữ lâu dài là **phân biệt mục tiêu và ranh giới của VM-side protocol với Java-level synchronization**.

## 5. Bảng phân biệt trực tiếp

| Tiêu chí | JVM Thread-Local Handshakes | `synchronized`, `Lock`, atomics và synchronizers |
|---|---|---|
| Tầng hệ thống | **HotSpot VM internals** | **Java language/Java SE APIs** |
| Ai yêu cầu? | VM internal subsystems | Application code |
| Đối tượng | JavaThread/VM thread state | Shared Java objects, variables, tasks |
| Điều kiện an toàn | Handshake-safe theo VM implementation | Mutual exclusion, memory ordering, completion contract |
| Có Java public API? | **Không có public `Thread.handshake`** | Có `synchronized`, `ReentrantLock`, `AtomicInteger`... |
| Bảo vệ `counter++`? | Không | Lock/atomic thích hợp có thể |
| Tạo happens-before cho user fields? | Không phải contract của application | Theo JMM và `java.util.concurrent` |
| Có thể nhắm một thread? | Có, ở JVM level | Lock/task orchestration theo thiết kế code |
| Liên quan global safepoint? | Có thể tránh global stop cho một số work | Không phải safepoint API |
| Portability | Phụ thuộc JVM implementation | API Java SE có contract tương thích |
| Cách kiểm tra | JVM logs/source/JFR/JVMTI phù hợp | Unit/concurrency tests và code review |

**Câu cần nhớ:** “Java có Thread-Local Handshakes nên không cần lock” là **sai**. JVM cần handshake để an toàn khi **JVM** thực hiện công việc; ứng dụng cần synchronization để an toàn khi **ứng dụng** đọc/ghi shared state.

## 6. Java Memory Model: những gì code Java thực sự cần

**Java Language Specification `17.4** định nghĩa *happens-before* và các memory effects cho tương tác giữa threads. Khi chọn công cụ đồng bộ, cần trả lời ba câu hỏi:

1. **Atomicity:** Một cập nhật phức hợp có bị xen vào giữa không?
2. **Visibility:** Thread B có thấy những giá trị A đã ghi không?
3. **Ordering / happens-before:** Những actions nào được bảo đảm xảy ra trước/được thấy theo contract?

### 6.1. Atomicity

```java
counter++;
```

Đây là biểu thức Java trong method, không phải thao tác tăng nguyên tử chỉ vì biến là `int`. Nó là phép đọc → tính toán → ghi. Nếu hai threads cùng tăng một biến không bảo vệ, các increments có thể bị mất.

Giải pháp theo yêu cầu:
- `synchronized` bảo vệ critical section;
- `ReentrantLock` khi cần các đặc tính lock bổ sung;
- `AtomicInteger.incrementAndGet()` cho bộ đếm đơn giản;
- Cấu trúc immutable/CAS khi invariant phức tạp và thiết kế phù hợp.

**Không** có cách “gọi JEP 312” từ Java application để tự động bảo vệ `counter++`.

### 6.2. Visibility

Thread A có thể ghi `data=42`, thread B cần đọc một giá trị chính xác sau khi được báo “ready”.

`volatile` có thể bảo đảm visibility/ordering:
- A ghi dữ liệu thường;
- A ghi `volatile ready = true`;
- B đọc `ready == true`;
- B đọc dữ liệu.

Quan hệ volatile write/read tương ứng thiết lập **happens-before** theo JMM. Việc thấy dữ liệu đã công bố đến từ **memory model**, không phải vì JVM handshake có chạy hay không.

### 6.3. Ordering

Những bảo đảm tiêu biểu:

| Tình huống | Happens-before |
|---|---|
| Cùng một thread | Action trước trong program order trước action sau |
| `synchronized` | Unlock của monitor trước lần lock tiếp theo của **cùng monitor** |
| `volatile` | Volatile write trước volatile read tương ứng sau đó |
| `Thread.start()` | Actions trước khi start xảy ra trước actions của thread được start |
| `Thread.join()` | Actions của worker đã kết thúc trước actions sau `join()` thành công |
| `CountDownLatch` | Actions trước `countDown()` trước actions sau `await()` thành công |
| `Executor` | Actions trước submit theo các bảo đảm `java.util.concurrent` trước execution task |
| `Future.get()` | Actions của asynchronous task trước actions sau lấy kết quả bằng get |
| `Lock` | Release/acquire của cùng lock theo contract lock |

Không có quy tắc “JVM handshake occurred, therefore every field in every Java object becomes synchronized”.

## 7. Khi nào chọn `synchronized`?

`synchronized` thích hợp nếu nhiều threads cùng sửa **shared mutable state** và cần bảo vệ critical section.

Ví dụ mảnh class:

```java
final class Counter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int read() {
        return count;
    }
}
```

Cả hai methods dùng **monitor của cùng Counter instance**:
- Không có hai threads cùng chạy phần thân `increment()` trên cùng instance một lúc;
- Đọc/ghi trong lock có memory-order semantics thích hợp;
- Một monitor release trước lock tiếp theo tạo happens-before theo JMM.

### 7.1. Chọn đúng cùng lock

Anti-pattern:

```java
synchronized (new Object()) {
    sharedCounter++;
}
```

Mỗi lần thực thi tạo một monitor mới, **không** bảo vệ shared variable khỏi threads khác dùng các monitor khác.

Mẫu phù hợp trong class:

```java
private final Object lock = new Object();

void increment() {
    synchronized (lock) {
        sharedCounter++;
    }
}
```

Mọi code paths truy cập `sharedCounter` phải tuân thủ chính sách lock tương ứng.

### 7.2. Khóa ứng dụng không phải JVM safepoint

`synchronized(lock)` là Java monitor operation, không có ý nghĩa “đề nghị HotSpot dừng tất cả Java threads” hoặc “gửi một thread-local handshake đến target thread”.

Một JVM có thể thực hiện các công việc nội bộ ở những thời điểm liên quan đến monitor, nhưng **contract public của `synchronized`** vẫn là mutual exclusion và memory ordering, không phải một internal handshake protocol.

## 8. Ví dụ Java đầy đủ 1 — synchronized counter

Tệp **`SynchronizedCounterDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class SynchronizedCounterDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                    for (int j = 0; j < 10_000; j++) {
                        counter.increment();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workers[i].start();
        }

        start.countDown();
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("expected=40000");
        System.out.println("actual=" + counter.get());
        System.out.println("correct=" +
                (counter.get() == 40_000));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SynchronizedCounterDemo.java
java SynchronizedCounterDemo
```

**Stdout đã kiểm thử:**

```text
expected=40000
actual=40000
correct=true
```

### 8.1. Vì sao kết quả chắc chắn đúng trong lần chạy bình thường?

- Bốn worker threads, mỗi thread tăng `value` 10.000 lần.
- `CountDownLatch start` giúp các worker đợi một tín hiệu để bắt đầu; nó **không** tự khóa biến `value`.
- `synchronized` trên cùng Counter instance bảo vệ phép tăng.
- `Thread.join()` giúp main chỉ tiếp tục sau khi từng worker kết thúc.
- `get()` cũng sử dụng cùng monitor.
- Tổng đúng là `4 × 10000 = 40000`.

Nếu bỏ `synchronized` khỏi các accesses, code có **data race** và có thể mất increments. **Một lần test vẫn in 40.000 không chứng minh code không khóa là đúng**: concurrency scheduling biến động.

### 8.2. Demo này không mô phỏng Handshake::execute

Không có public `Handshake::execute` trong Java SE. Chương trình này chỉ kiểm chứng **contract của Java synchronization**. Không gán kết quả `correct=true` cho một JVM handshake vô hình.

## 9. Khi nào chọn `ReentrantLock`?

`java.util.concurrent.locks.ReentrantLock` cung cấp mutual exclusion tương tự monitor nhưng có thêm:

- `tryLock()` nếu muốn thử lấy lock;
- `tryLock(timeout, unit)` nếu cần timeout;
- `lockInterruptibly()` khi cần xử lý interruption trong lúc đợi;
- `Condition` để phối hợp đợi/signaling với lock cụ thể;
- Một fairness policy tùy chọn (có throughput trade-off).

Mẫu mảnh code trong class:

```java
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

private int stock = 10;

void reserve() {
    lock.lock();
    try {
        if (stock <= 0) {
            throw new IllegalStateException("out of stock");
        }
        stock--;
    } finally {
        lock.unlock();
    }
}
```

`unlock()` phải nằm trong `finally`. Mọi phương thức khác sửa/đọc `stock` cần tuân thủ cùng lock policy.

**Không nhầm `ReentrantLock.lock()` với JVM thread-local handshake**. Một cái bảo vệ shared application state, cái kia phục vụ VM internal coordination.

### 9.1. Deadlock vẫn là trách nhiệm ứng dụng

A giữ `lock1` chờ `lock2`, B giữ `lock2` chờ `lock1`: đây là nguy cơ **deadlock** của application. JVM handshake không làm hai locks tự động được sắp đúng thứ tự.

Các biện pháp đúng:
- Chọn lock ordering nhất quán;
- Giữ critical section ngắn;
- Dùng timeout/cancellation khi phù hợp;
- Giảm số lượng shared mutable invariants;
- Dùng concurrent collections/immutable data khi phù hợp.

## 10. `volatile` bảo đảm gì và không bảo đảm gì?

`volatile` hỗ trợ **memory visibility và ordering** cho một số shared state, nhưng **không tạo mutual exclusion**.

Mẫu:

```java
final class Publication {
    int payload;
    volatile boolean ready;
}
```

Nếu producer ghi `payload=42` rồi `ready=true`, consumer thấy `ready==true` bằng volatile read rồi đọc `payload`, JMM cung cấp happens-before phù hợp.

**Không đúng:** cho rằng `volatile int counter; counter++;` là phép tăng atomic. Phép tăng vẫn gồm nhiều bước.

Các API khác:
- `AtomicBoolean` cho một số flags cập nhật atomically;
- `AtomicInteger` cho counters;
- `AtomicReference<T>` để công bố một immutable snapshot hoặc cập nhật CAS;
- `VarHandle` cho các memory access modes có semantics chính thức.

Không có API nào ở đây yêu cầu “gửi HotSpot handshake” từ user code.

### 10.1. `Thread.onSpinWait()` cũng không phải handshake

`Thread.onSpinWait()` là **CPU/runtime hint** cho vòng chờ bận. Nó không đảm bảo visibility, không tự xác nhận producer đã publish và không cung cấp mutex.

Chỉ dùng busy-spin khi có lý do rất rõ về latency/CPU. Với tác vụ đợi dữ liệu, thường nên dùng `CountDownLatch`, `Future`, `BlockingQueue` hoặc synchronizer thích hợp.

## 11. `AtomicInteger` xử lý increment; không tự bảo vệ invariant đa biến

`AtomicInteger.incrementAndGet()` là atomic update của **một biến số nguyên**.

```java
java.util.concurrent.atomic.AtomicInteger total =
        new java.util.concurrent.atomic.AtomicInteger();

total.incrementAndGet();
int result = total.get();
```

Mảnh code trong method. Những phương thức này được Java SE đặc tả, không cần JVM handshake công khai.

Nếu cần duy trì invariant `available + reserved == 100`:
- Tăng/giảm **hai AtomicInteger khác nhau** không tạo một giao dịch atomic trên cả hai;
- Thread khác có thể nhìn thấy trạng thái giữa hai updates;
- Nên bảo vệ invariant bằng **một critical section**, hoặc dùng **immutable aggregate** được publish atomically qua `AtomicReference` nếu thiết kế phù hợp.

Đừng dùng số lượng handshakes/JVM safepoints làm tiêu chí kết luận invariant đã được đảm bảo.

## 12. Ví dụ Java đầy đủ 2 — volatile publication và atomic counter

Tệp **`VolatileAtomicDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class VolatileAtomicDemo {
    static final class Shared {
        int payload;
        volatile boolean ready;
    }

    public static void main(String[] args)
            throws InterruptedException {
        Shared shared = new Shared();
        Thread producer = new Thread(() -> {
            shared.payload = 42;
            shared.ready = true;
        });
        producer.start();

        long deadline =
                System.nanoTime() + 5_000_000_000L;
        while (!shared.ready &&
                System.nanoTime() < deadline) {
            Thread.onSpinWait();
        }
        if (!shared.ready) {
            throw new IllegalStateException(
                    "producer did not publish");
        }

        System.out.println(
                "publishedPayload=" + shared.payload);
        producer.join();

        AtomicInteger total = new AtomicInteger();
        Thread a = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                total.incrementAndGet();
            }
        });
        Thread b = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                total.incrementAndGet();
            }
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("atomicCounter=" + total.get());
        System.out.println("atomicCorrect=" +
                (total.get() == 10_000));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 VolatileAtomicDemo.java
java VolatileAtomicDemo
```

**Stdout đã kiểm thử:**

```text
publishedPayload=42
atomicCounter=10000
atomicCorrect=true
```

### 12.1. Vì sao thấy payload 42?

Producer thực hiện:
1. `shared.payload = 42`;
2. `shared.ready = true` (volatile write).

Consumer chỉ đọc payload **sau khi** thấy volatile flag là true. Theo JMM, volatile write/read theo thứ tự tương ứng **tạo happens-before** cho dữ liệu trước đó. Không có nhu cầu gọi JVM handshake từ Java.

### 12.2. Vì sao tổng atomic là 10.000?

Hai threads cùng tăng `AtomicInteger` 5.000 lần; phương thức tăng là atomic. Main dùng `join()` để đợi cả hai kết thúc trước khi đọc giá trị. Kết quả là 10.000.

### 12.3. Vì sao có deadline?

Vòng lặp spin được dùng **chỉ để minh họa visibility** và có deadline tránh chờ mãi. Nếu producer bị scheduler trì hoãn quá mức, ví dụ có thể ném timeout. Ứng dụng thật nên sử dụng blocking synchronizers nếu không có yêu cầu latency chuyên biệt.

**Không suy:** `Thread.onSpinWait()` là thread-local handshake. Từ “spin” trong ứng dụng không nói gì về cách JVM phối hợp với JavaThreads ở cấp VM.

## 13. `CountDownLatch` dùng khi nào?

`CountDownLatch` là synchronizer một lần (*one-shot*):

- Tạo với count N;
- `countDown()` giảm count;
- `await()` chờ count về zero;
- Sau khi zero, những `await()` tiếp theo trả ngay;
- **Không** reset count để dùng lại như `CyclicBarrier`.

Theo Javadoc, actions trước `countDown()` happens-before actions sau `await()` thành công trong thread khác.

Ví dụ use case:
- N worker tasks bắt đầu sau một tín hiệu;
- Một main thread chờ nhiều workers chuẩn bị resource;
- Đợi một nhóm asynchronous tasks kết thúc.

**Lưu ý:** latch **phối hợp completion/ordering**, không tự mutual-exclude một phép ghi vào `int counter` nếu các workers vẫn cùng tăng biến thường mà không khóa.

## 14. `Future.get()` và `Thread.join()` là completion synchronization

`Thread.join()` chờ thread **kết thúc**.

`Future.get()` chờ result của asynchronous computation, hoặc có thể ném `ExecutionException` nếu task lỗi. Nó tạo memory consistency guarantee cho các actions của task trước retrieval.

`ExecutorService` cho phép submit tasks và quản lý pool.

Phân biệt:
- `submit()`: task đã được đưa vào thực thi/queue, **chưa chắc đã hoàn thành**;
- `future.get()`: đợi task có kết quả, nhận exception qua contract;
- `shutdown()`: yêu cầu pool không nhận task mới;
- `isShutdown()`: pool đã nhận yêu cầu shutdown;
- `isTerminated()`: mọi tasks hoàn tất và pool kết thúc theo contract.

**Không thay `join/get` bằng `Thread.sleep(100)`** vì ngủ 100 ms không chứng minh worker đã xong.

## 15. Ví dụ Java đầy đủ 3 — CountDownLatch + ExecutorService + Future

Tệp **`LatchExecutorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class LatchExecutorDemo {
    public static void main(String[] args)
            throws Exception {
        ExecutorService executor =
                Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= 4; i++) {
                final int n = i;
                Callable<Integer> job = () -> {
                    start.await();
                    return n * n;
                };
                futures.add(executor.submit(job));
            }

            start.countDown();
            int sum = 0;
            for (Future<Integer> future : futures) {
                sum += future.get();
            }

            System.out.println("tasks=" + futures.size());
            System.out.println("sumOfSquares=" + sum);
        } finally {
            start.countDown();
            executor.shutdown();
        }

        System.out.println("shutdownRequested=" +
                executor.isShutdown());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LatchExecutorDemo.java
java LatchExecutorDemo
```

**Stdout đã kiểm thử:**

```text
tasks=4
sumOfSquares=30
shutdownRequested=true
```

Bốn tasks tính bình phương của 1, 2, 3, 4. Tổng là `1 + 4 + 9 + 16 = 30`.

### 15.1. Vì sao `Future.get` quan trọng?

Main không giả định workers hoàn tất trong một thời gian tùy ý. Nó **đợi kết quả thật** của từng task qua `get()`.

`CountDownLatch` chỉ quyết định khi nào tasks được phép bắt đầu; nó không bảo vệ các shared mutable variables bên trong mỗi task nếu task có ghi chung.

### 15.2. Vì sao `shutdownRequested=true`?

Pool đã nhận `shutdown()` trong `finally`. `isShutdown()` trả true, nhưng không đồng nghĩa `isTerminated()` ngay lập tức true. Đây là hai trạng thái khác nhau.

**Tất cả đều là API Java SE**, không phải một wrapper của HotSpot handshake mà người dùng có thể điều khiển.

## 16. `ThreadLocal` không phải Thread-Local Handshakes

Hai khái niệm chỉ trùng chữ “thread-local”.

### `ThreadLocal<T>`

```java
ThreadLocal<String> requestContext =
        ThreadLocal.withInitial(() -> "none");

requestContext.set("request-123");
String id = requestContext.get();
requestContext.remove();
```

Mảnh code trong method, cần `java.lang.ThreadLocal`. Mỗi thread có giá trị thread-local riêng, thay vì tự chia sẻ một field duy nhất.

Dùng để giữ request context hoặc dữ liệu gắn với thread cần hiểu:
- Thread pools **tái sử dụng threads**, có thể làm context leak nếu không `remove()` đúng lúc;
- `ThreadLocal` không phải synchronization giữa threads;
- Một `ThreadLocal` không tạo mutex cho shared object;
- Nó không khiến VM chạy handshake operation.

### Thread-Local Handshakes

HotSpot dùng handshake để **phối hợp VM operation với JavaThread**. Không có đối tượng `ThreadLocal<String>` nào là cách đăng ký VM callback. Bạn không thể thêm `ThreadLocal` rồi kỳ vọng global safepoint không còn xảy ra.

## 17. `Thread.sleep()`, `interrupt()` và `LockSupport.park()` khác handshake ra sao?

| API | Ý nghĩa trong ứng dụng | Không nên hiểu thành |
|---|---|---|
| `Thread.sleep(...)` | Chờ một khoảng thời gian | Completion guarantee hoặc JVM handshake |
| `Thread.join()` | Chờ thread kết thúc | VM callback trên thread khác |
| `Thread.interrupt()` | Yêu cầu interruption, với behavior tùy operation | Kill thread ngay hoặc VM handshake |
| `Thread.onSpinWait()` | Hint trong vòng lặp chờ bận | Memory barrier tự bảo vệ shared state |
| `LockSupport.park()` | Primitive parking cho synchronizers | JVM global safepoint |
| `Object.wait()/notifyAll()` | Chờ/tín hiệu với monitor | Thread-local handshake |
| `CountDownLatch.await()` | Đợi count hoàn thành | JVM internal handshake callback |

Một anti-pattern thường gặp:

```java
while (!done) {
    Thread.sleep(10);
}
```

Đây là **mảnh code minh họa lỗi**, giả định `done` có thể được ghi từ thread khác; cần xử lý `InterruptedException`. Nếu `done` không có synchronization/volatile phù hợp, việc sleep không tạo một happens-before guarantee tổng quát để B thấy cập nhật của A.

Nếu cần wait cho completion, dùng `join`/`Future.get`/`CountDownLatch`. Nếu cần visibility của trạng thái, dùng `volatile`, lock hoặc primitive thích hợp. Hai mục đích có thể kết hợp nhưng không trùng nhau.

## 18. Thread dump, ThreadMXBean, JFR và JVMTI

Trong JVM hiện đại, lập trình viên hoặc công cụ có thể xem trạng thái thread bằng:

- `Thread.getState()` hoặc `Thread.getStackTrace()`;
- `java.lang.management.ThreadMXBean`;
- `jcmd` thread dump / các lệnh diagnostics;
- Java Flight Recorder (JFR);
- Java Virtual Machine Tool Interface (JVMTI) cho native agents.

Những công cụ này giúp **quan sát hoặc chẩn đoán**, không phải bảo đảm ứng dụng đã khóa dữ liệu.

**Không khẳng định** mỗi lần gọi `Thread.getStackTrace()` hay `ThreadMXBean.dumpAllThreads` đều kích hoạt **đúng một thread-local handshake**. Public Java API không hứa một mapping 1:1 sang implementation HotSpot nào; cách JVM thu thập thông tin có thể thay đổi.

Thread dump cho biết một thread `BLOCKED` có thể là do đang chờ monitor. Điều đó **không tự chứng minh** một handshake JEP 312 đã xảy ra. Cần phân biệt:

- **Thread state** của ứng dụng;
- **VM safepoint/handshake events**;
- **Lock contention**;
- **Race conditions**;
- **Lifecycle/completion**.

Không dùng một diagnostic command để “ép JVM đồng bộ mọi biến Java”.

## 19. Quan sát handshake bằng HotSpot Unified Logging

Trên OpenJDK 24.0.2 đã kiểm chứng `java -Xlog:help` có **tag `handshake`**. Để tìm các tags hợp lệ trên runtime hiện tại:

```bash
java -Xlog:help
```

Với HotSpot/JDK hỗ trợ, có thể bật log diagnostic trong môi trường test:

```bash
java -Xlog:handshake=debug -cp . MyApp
```

**Lưu ý:** `MyApp` là main class đã có sẵn; đây là **lệnh minh họa**, không phải chương trình độc lập.

Điều kiện:
1. Không phải mọi lần chạy đều có log handshake rõ ràng.
2. Không thấy log **không chứng minh** hạ tầng handshake không được dùng.
3. `-Xlog:safepoint=info` và `-Xlog:handshake=debug` là hai góc nhìn **khác nhau**.
4. Format/tag levels có thể thay đổi giữa các bản HotSpot.
5. Bật `trace/debug` quá nhiều có overhead, không nên giữ trong production khi chưa đánh giá.
6. Không lấy sự xuất hiện của handshake log làm bằng chứng `counter++` đã atomic hoặc dữ liệu Java đã được publish đúng.

Một global safepoint có thể có log riêng; một thread-local handshake không nhất thiết cần global safepoint. **Quan sát JVM internal events** và **kiểm thử business concurrency correctness** là hai việc khác nhau.

## 20. Java 21+ virtual threads có làm thay đổi sự phân biệt này không?

**Không.** Virtual threads (Java 21+) giúp chương trình có nhiều tác vụ đồng thời với chi phí thread thấp hơn trong những workload phù hợp. Chúng thường được runtime thực thi trên platform carrier threads.

Nhưng:
- Virtual threads **không bỏ Java Memory Model**;
- `synchronized`/`Lock` vẫn có contract;
- `volatile`/atomics vẫn cần khi shared state yêu cầu;
- `CountDownLatch`/`Future` vẫn cần khi cần completion;
- `ThreadLocal` là abstraction cho dữ liệu theo thread, **không** phải Java 10 JEP 312 handshake;
- Chi tiết target JavaThread/carrier và handshake của HotSpot có thể khác nhau theo JDK version.

**Không suy rằng** gọi một API `Thread` trên virtual thread sẽ gửi một HotSpot handshake tương ứng với một JavaThread nội bộ; đó không phải public API contract.

Với virtual threads, cần tiếp tục xem xét lock contention, blocking, cancellation và resource management. Không áp một mô tả cơ chế JVM 2018 cho mọi implementation mới mà không kiểm chứng.

## 21. Tình huống thực tế: invariant đa biến

Giả sử ứng dụng quản lý tồn kho:

```java
int available = 100;
int reserved = 0;

void reserveOne() {
    available--;
    reserved++;
}
```

Đây là **mảnh code không thread-safe**. Giả định nghiệp vụ yêu cầu `available + reserved == 100` trong mỗi snapshot mà reader quan sát.

Hai phép cập nhật riêng lẻ không phải một atomic transaction. Tăng/giảm các biến dùng chung không được bảo vệ có thể tạo **lost updates** hoặc reader thấy trạng thái trung gian.

Giải pháp hợp lệ:
- Một monitor/`ReentrantLock` chung cho cả update và đọc snapshot;
- Một immutable state tổng hợp được publish qua `AtomicReference` với CAS;
- Một thiết kế tránh shared mutable state.

**Không giải quyết** bằng:
- Đặt `ThreadLocal` cho vài trường rồi kỳ vọng shared state đồng bộ;
- Gọi `Thread.sleep()` giữa hai phép gán;
- Chạy `jcmd` để lấy thread dump;
- Bật `-Xlog:handshake`;
- Tin rằng VM handshake đã tạm dừng đúng thread và ngăn reader.

## 22. Sai lầm phổ biến

| Khẳng định sai | Sửa lại |
|---|---|
| “JEP 312 thêm public `Thread.handshake` API.” | Không, đó là HotSpot internal mechanism. |
| “Thread-Local Handshake chính là `ThreadLocal`.” | Không, `ThreadLocal` lưu dữ liệu per-thread. |
| “Handshake là một monitor lock.” | Không, VM internal coordination khác Java mutual exclusion. |
| “VM handshake giúp `counter++` thread-safe.” | Không, cần lock/atomic. |
| “Có handshake sẽ không bao giờ có global safepoints.” | Không, các global VM operations phù hợp vẫn cần safepoint. |
| “Mọi handshake callback do target tự chạy.” | Không, VM có thể xử lý khi target ở trạng thái an toàn. |
| “Không có safepoint log nghĩa không có handshake.” | Không, logging categories và events khác nhau. |
| “Gọi thread dump đồng bộ mọi biến Java.” | Không, đó là diagnostic. |
| “`volatile int x` làm `x++` atomic.” | Không, volatile không đủ cho compound update. |
| “`Thread.sleep(100)` bảo đảm worker đã hoàn tất.” | Không, dùng join/future/latch. |
| “`CountDownLatch` tự bảo vệ mutable counter.” | Không, latch điều phối thời điểm; counter vẫn cần synchronization. |
| “`ExecutorService.shutdown` nghĩa mọi tasks đã done.” | Không, shutdown request khác termination. |
| “AtomicInteger bảo vệ invariant gồm nhiều fields.” | Không tự động. |
| “`ReentrantLock` là API gọi handshake trong HotSpot.” | Không, nó là Java mutual exclusion API. |
| “Virtual threads nghĩa không còn cần happens-before.” | Không, JMM vẫn áp dụng. |
| “Một lần concurrency test PASS chứng minh không có data race.” | Không, cần thiết kế và test đúng semantics. |
| “JEP 312 bảo đảm latency luôn giảm.” | Không có mức bảo đảm; phụ thuộc workload/VM. |

## 23. Checklist trước khi review hoặc merge

- [ ] Có nêu đúng JEP 312 được đưa vào **Java 10** và là **JVM internal improvement**?
- [ ] Có phân biệt global safepoint với thread-targeted handshake?
- [ ] Có tránh khẳng định mọi callback luôn chạy trực tiếp trên target thread?
- [ ] Có tránh khẳng định handshakes loại bỏ mọi STW pauses?
- [ ] Không tạo ra API `Thread.handshake(...)` không tồn tại?
- [ ] Shared mutable state có lock/atomic/happens-before đúng không?
- [ ] Các methods truy cập shared fields có dùng **cùng monitor**?
- [ ] `volatile` có bị lạm dụng cho compound increments không?
- [ ] Những invariants đa biến có được bảo vệ theo một policy nhất quán?
- [ ] `ReentrantLock.unlock()` có nằm trong `finally` không?
- [ ] Completion dùng `join`/`Future.get`/`CountDownLatch` thay vì sleep-based guessing?
- [ ] Có xử lý interruption/timeout khi chờ lâu?
- [ ] `ExecutorService.shutdown` có bị nhầm với `isTerminated` không?
- [ ] `ThreadLocal` có được dọn đúng khi dùng thread pools?
- [ ] Diagnostic log/JFR/JVMTI có được dùng để **quan sát**, không thay synchronization?
- [ ] Java 21+ virtual threads có được phân biệt với HotSpot internal JavaThread?
- [ ] Các Java examples có biên dịch/chạy và stdout được kiểm chứng?
- [ ] Các kiến thức vẫn đúng với Java hiện đại, không dùng API legacy để “dừng” threads?

Một nhận xét code review tốt:

> “JEP 312 giúp HotSpot phối hợp với một target JavaThread khi cần VM operation. Nó **không làm `counter++` an toàn**. Nếu nhiều threads cập nhật cùng counter, hãy chọn `AtomicInteger.incrementAndGet()` hoặc monitor bảo vệ shared state.”

Nhận xét khác:

> “Đừng dùng `Thread.sleep` để đợi tác vụ. Nó không xác nhận completion và không bảo đảm visibility. Dùng `Future.get`, `CountDownLatch` hoặc `join`, có xử lý timeout/cancellation hợp lý.”

## 24. Câu hỏi ôn tập và đáp án

**1.** Thread-Local Handshakes được thêm trong Java nào?

**Đáp án:** **Java 10**, qua **JEP 312**.

**2.** Đây là public Java API hay HotSpot VM internal mechanism?

**Đáp án:** **HotSpot internal mechanism**.

**3.** Có Java SE `Thread.handshake(Runnable)` không?

**Đáp án:** **Không**.

**4.** Global safepoint khác handshake cho một thread ở điểm nào?

**Đáp án:** Global safepoint phối hợp nhiều JavaThreads theo điều kiện toàn cục; một thread-local handshake có thể phối hợp với một target mà không cần tất cả threads vào cùng safepoint.

**5.** Handshake callback luôn chạy bởi target JavaThread?

**Đáp án:** **Không**; VM có thể xử lý khi target đã ở trạng thái an toàn.

**6.** JVM handshake có làm `counter++` atomic không?

**Đáp án:** **Không**; dùng synchronization/atomic operation phù hợp.

**7.** Vì sao `synchronized` hữu ích?

**Đáp án:** Nó cung cấp mutual exclusion của cùng monitor và memory-ordering guarantees.

**8.** `volatileCounter++` có phải atomic không?

**Đáp án:** **Không**, vì đó là read–modify–write gồm nhiều bước.

**9.** `AtomicInteger.incrementAndGet()` bảo đảm gì?

**Đáp án:** Tăng nguyên tử một giá trị với memory effects được Java SE quy định.

**10.** `ThreadLocal<T>` có phải Thread-Local Handshakes không?

**Đáp án:** **Không**.

**11.** `Thread.sleep` có bảo đảm một task hoàn tất?

**Đáp án:** **Không**; dùng `join`/`Future.get`/latch.

**12.** Khi nào `CountDownLatch.await()` trả thành công?

**Đáp án:** Khi count bằng zero theo contract, hoặc đã zero từ trước.

**13.** `Future.get()` cung cấp điều gì?

**Đáp án:** Chờ task result và memory consistency guarantees cho task actions.

**14.** `ExecutorService.shutdown` có làm `isTerminated()` lập tức true?

**Đáp án:** Không nhất thiết.

**15.** `-Xlog:handshake=debug` có phải API đồng bộ business data không?

**Đáp án:** **Không**, nó chỉ bật VM diagnostic logging.

**16.** Thread dump có `BLOCKED` có chứng minh JEP 312 handshake không?

**Đáp án:** **Không**, có thể là monitor contention.

**17.** Virtual threads có cho phép bỏ locks và JMM?

**Đáp án:** **Không**; shared mutable state vẫn cần đúng synchronization.

**18.** Vì sao không dùng JVM handshakes để bảo vệ invariant tồn kho?

**Đáp án:** Handshakes xử lý VM operations; invariant phải được bảo vệ ở application level bằng lock/atomic snapshot/thiết kế không chia sẻ state.

## 25. Tài liệu chính thức

- [OpenJDK JEP 312 — Thread-Local Handshakes](https://openjdk.org/jeps/312): đặc tả mục đích và giới hạn thiết kế trong Java 10.
- [OpenJDK HotSpot `handshake.hpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.hpp): ví dụ nội bộ HotSpot hiện đại; **không phải Java SE API**.
- [OpenJDK HotSpot `safepoint.hpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.hpp): cơ chế global safepoint trong VM.
- [JLS `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html): Java Memory Model và happens-before.
- [Oracle Java SE 25 — `java.util.concurrent` package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html): memory consistency effects.
- [Oracle Java SE 25 — `Thread`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): platform/virtual threads, join/start/interruption.
- [Oracle Java SE 25 — `ReentrantLock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock semantics và cách dùng.
- [Oracle Java SE 25 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic access.
- [Oracle Java SE 25 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): task coordination và happens-before.
- [Oracle Java SE 25 — `ExecutorService`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/shutdown/lifecycle.
- [Oracle Java SE 25 — `Future`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html): completion và result visibility.
- [Oracle Java SE 25 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html): per-thread variables.
- [Oracle Java SE 25 — The `java` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): Unified Logging options như `-Xlog:help`.

**Tóm tắt:** **Java 10 JEP 312** cho HotSpot phối hợp nội bộ với một số JavaThreads ở trạng thái an toàn mà không phải lúc nào cũng yêu cầu global safepoint. Nó **không** thêm API đồng bộ Java. Với chương trình đa luồng, hãy tiếp tục bảo vệ shared state bằng **`synchronized`, `ReentrantLock`, `volatile`, `AtomicInteger` và các synchronizers** dựa trên **Java Memory Model**.