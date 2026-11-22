# Sắp xếp lại thao tác, data race và những bảo đảm mà `Thread.sleep` không cung cấp

## 1. Mục tiêu: phân biệt “trông có vẻ theo thứ tự” và “được Java bảo đảm”

Java chạy trên nhiều CPU, JVM và bộ tối ưu JIT khác nhau. Nếu hai threads cùng truy cập trạng thái mutable mà không đồng bộ đúng, chương trình có thể quan sát kết quả **khác trực giác đọc source từ trên xuống**, dù từng thread vẫn hoạt động đúng theo các quy tắc của Java Memory Model (JMM).

Ba khái niệm cần phân biệt:

1. **Reordering (sắp xếp lại thao tác):** compiler, JVM hoặc CPU có thể tổ chức thực thi theo thứ tự khác thứ tự câu lệnh nhìn thấy, miễn các quan sát hợp lệ mà mô hình bộ nhớ yêu cầu vẫn được bảo toàn.
2. **Data race:** hai thao tác truy cập cùng một shared variable, ít nhất một là **write**, nhưng không có quan hệ **happens-before** sắp thứ tự chúng. Các kết quả racy có thể khó dự đoán và không được mô hình sequential consistency thông thường bảo vệ.
3. **`Thread.sleep` không phải synchronization:** ngủ làm thread ngừng chạy tạm thời theo scheduler, **không tạo cạnh happens-before, không bắt JVM flush/reload shared data, không thả intrinsic monitors đang giữ**.

Bài sử dụng **Java 17**, dựa trực tiếp trên **JLS `17.3`, `17.4`, `17.5`** và API `Thread`. Các ví dụ đã tách rõ **chương trình chạy được với stdout xác định** và **litmus test có kết quả không xác định**. Không suy luận hiệu năng hoặc bảo đảm bộ nhớ từ một lần thực thi may mắn trên một máy.

## 2. Ba loại “thứ tự” thường bị nhầm

Khi đọc:

```java
int a = 1;
int b = 2;
System.out.println(a + b);
```

Đây là fragment chạy tuần tự. Compiler có thể tối ưu phép toán hoặc giữ values trong registers, nhưng kết quả phải tương đương một chương trình đúng: in `3`. Với **một thread**, Java tôn trọng **intra-thread semantics**: kết quả có thể quan sát của thread phải phù hợp cách chạy riêng của nó theo thứ tự chương trình (`as-if-serial` về trực giác).

Ở chương trình **nhiều threads**, cần phân biệt:

| Thuật ngữ | Vai trò |
| --- | --- |
| **Source order** | Thứ tự code được trình bày trong `.java`; không luôn là thứ tự machine instructions |
| **Program order** | Quan hệ thứ tự các actions trong **một thread** theo mô hình JMM |
| **Synchronization order** | Một total order trên các **synchronization actions** trong một execution, nhất quán với program order từng thread |
| **Synchronizes-with** | Các cạnh đồng bộ đặc thù: volatile write→read, monitor unlock→lock, thread start/join, v.v. |
| **Happens-before (HB)** | Quan hệ thứ tự được sinh từ program order và synchronizes-with (có tính bắc cầu) |
| **Wall-clock order** | Thời gian thực tế scheduler cho threads chạy; tự nó không định nghĩa HB |

Một câu “A chắc chắn chạy trước B trong thế giới thật vì tôi gọi `sleep(100)`” **không phải** bằng chứng memory-ordering. Thứ tự wall-clock dự đoán từ delays không được thay thế bằng một quan hệ HB.

### HB không chỉ là đồng hồ

Viết `hb(A, B)` nghĩa là action A xảy ra **trước theo quan hệ JMM** B: những yêu cầu visibility/ordering thích hợp được áp dụng. Có thể tạo chuỗi:

```text
Trong Thread 1:
    A -> B (program order)

B synchronizes-with C ở Thread 2

Trong Thread 2:
    C -> D (program order)

Suy ra:
    hb(A, D) theo tính bắc cầu.
```

Nếu không có cạnh kết nối hai threads, chỉ riêng việc một thread được `sleep` lâu hơn thread kia không xây được đường HB ấy.

## 3. Bộ nhớ dùng chung: biến nào có thể rơi vào data race?

JLS `17.4.1` xem **instance fields, static fields và array elements** là shared variables có thể được nhiều threads truy cập. Local variables nằm trong frame riêng của thread không trực tiếp là shared variables theo nghĩa đó; tuy nhiên local references có thể trỏ tới một **object shared**.

Ví dụ:

```java
static int counter;

static void increment() {
    counter++;
}
```

Đây là fragment. Nếu hai threads cùng gọi `increment` mà không có synchronization:

- Cả hai có thể đọc cùng giá trị ban đầu.
- Mỗi thread tính cộng 1.
- Cả hai ghi kết quả, làm **lost update**.

Phép `counter++` gồm logic **read-modify-write**, không phải phép toán nguyên tử được đảm bảo bởi JMM chỉ vì nó là một Java statement.

### Định nghĩa data race chặt chẽ hơn “hai threads cùng chạy”

Hai accesses **conflict** nếu cùng variable và ít nhất một là write. Có data race khi các accesses conflict ấy **không được sắp thứ tự bởi happens-before**.

Không phải cứ có hai threads chạm một object là data race:

- Cả hai chỉ **đọc** một field immutable/safely published: không conflict write.
- Mọi truy cập shared state được bảo vệ nhất quán bằng **cùng intrinsic monitor**: có synchronization thích hợp.
- Một thread ghi trước `Thread.start()` và thread mới đọc sau khi start: có HB edge đặc thù.
- Một thread hoàn tất, thread khác `join()` thành công rồi đọc: có HB edge.

Ngược lại, việc code “thực tế có vẻ không bao giờ xảy ra đồng thời” nhờ `sleep` **không** tự đưa ra một synchronization protocol đúng.

## 4. Reordering: khác thứ tự câu lệnh nhưng vẫn hợp lệ

JLS nêu ví dụ mô hình với hai biến ban đầu bằng 0:

```text
Khởi tạo: A = 0, B = 0

Thread 1:            Thread 2:
    r2 = A;              r1 = B;
    B = 1;               A = 2;
```

Khi không có synchronization giữa các threads, có thể có kết quả khiến người đọc nghĩ các ghi/đọc “đảo thứ tự”. Các compiler và CPU được phép tối ưu nếu vẫn tuân thủ JMM, trong đó **happens-before và causality constraints** ngăn một số execution bất hợp lệ.

**Không cần có một dòng assembly move thật sự** để quan sát kết quả bất ngờ. Nhiều lý do có thể góp phần: JVM optimizer hoán đổi thứ tự operations khi không ảnh hưởng single-thread behavior, hardware store buffers, visibility delays và scheduler interleavings.

### Không đánh đồng source instruction với machine instruction

Một phép `int x = obj.value` ở Java source có thể tương ứng các bytecode actions và machine instructions thay đổi theo JIT tier. Compiler có thể inline, constant-fold hoặc giữ dữ liệu ở registers khi được phép. Ngược lại, một volatile access có thể buộc machine-level constraints phù hợp mà source `volatile` không thể hiện thành “một dòng fence” cố định.

Vì vậy đọc `javap -c` chỉ biết **class-file bytecode**, chưa chứng minh machine operations đã chạy theo một order nhất định.

## 5. Litmus nổi tiếng: hai threads đều thấy 0

Giả sử `x = y = 0` và mỗi thread chạy:

```text
Thread A:            Thread B:
    x = 1;               y = 1;
    r1 = y;              r2 = x;
```

**Kết quả `r1 == 0 && r2 == 0` là một outcome được JMM cho phép** trong litmus không đồng bộ này. Nó có thể xảy ra dù mỗi thread thấy chương trình mình chạy “đúng”, vì **không có HB** buộc mỗi thread thấy ghi của thread kia đúng lúc.

Không được suy ra:

- Cứ chạy là nhận `(0, 0)`.
- Nếu thử một triệu lần không thấy `(0, 0)` thì đoạn code đã an toàn.
- JVM nhất thiết đã đảo thứ tự hai statements trong generated machine code.
- Tất cả cặp số tùy tiện đều được phép. JMM có constraints về source values, well-formed executions và causality.

### Java 17 hoàn chỉnh: một lần thử nhưng output không cố định

Tạo file **`ReorderingLitmus.java`**:

```java
public class ReorderingLitmus {
    static int x, y;
    static int r1, r2;

    public static void main(String[] args)
            throws InterruptedException {
        x = y = r1 = r2 = 0;

        Thread a = new Thread(() -> {
            x = 1;
            r1 = y;
        }, "A");

        Thread b = new Thread(() -> {
            y = 1;
            r2 = x;
        }, "B");

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("r1=" + r1 + ",r2=" + r2);
    }
}
```

```bash
javac --release 17 ReorderingLitmus.java
java ReorderingLitmus
```

**Stdout không xác định duy nhất**; ví dụ có thể là:

```text
r1=0,r2=1
```

Một execution khác có thể in `r1=1,r2=0`, `r1=1,r2=1`, hoặc outcome `r1=0,r2=0` mà JMM cho phép. Dòng ví dụ **không phải một lần chạy đã được đo**. Chạy test này nhiều lần không đủ làm phép chứng minh formal; frequency của từng outcome phụ thuộc machine/JVM/scheduler/JIT.

### Vì sao `join()` không “sửa” race giữa A và B?

`join` bảo đảm khi main đọc `r1,r2` sau khi hai threads kết thúc, những writes đã xảy ra trong A/B được main quan sát thích hợp. Nhưng nó **không tạo cạnh HB** từ `x = 1` của A sang `r2 = x` của B hay từ `y = 1` của B sang `r1 = y` của A. Hai worker threads vẫn có racy accesses.

## 6. Happens-before: thứ cần tìm thay vì đoán CPU timing

Các nguồn HB quan trọng trong JLS 17:

| Tình huống | Cạnh đồng bộ và điều được bảo đảm |
| --- | --- |
| Một thread tự thực hiện `A` rồi `B` | `hb(A, B)` bởi program order |
| Thread A `unlock(M)`, thread B `lock(M)` tiếp theo theo synchronization order | Unlock **synchronizes-with** subsequent lock của **cùng M** |
| A `volatileField = value`, B đọc `volatileField` sau đó theo synchronization order | Volatile write **synchronizes-with** subsequent reads cùng variable |
| A gọi `t.start()` | `start` synchronizes-with first action của thread t |
| A `join()` thread t và phát hiện t terminated | Actions của t happen-before continuation của A sau successful join |
| Thread A `interrupt` B và B phát hiện interrupt | Có synchronization edge được JLS quy định |
| Đối tượng được khởi tạo mặc định | Default-initialization writes có HB đến các actions thích hợp |
| `final` field initialization | Có quy tắc freeze đặc thù ở `17.5` khi construction hợp lệ |

**Không thuộc danh sách bảo đảm synchronization tự động:** `Thread.sleep`, `Thread.yield`, gọi `System.nanoTime`, `println` ở các đoạn không được thiết kế làm protocol, busy-wait đọc plain field, `Thread.onSpinWait`.

Một API thư viện có thể định nghĩa memory-consistency effects riêng (ví dụ `CountDownLatch`, `BlockingQueue`, `Future`). Hãy dựa vào **contract API**, không phỏng đoán việc bên trong API có dùng lock hay không.

## 7. Vì sao `sleep` KHÔNG tạo happens-before?

JLS Java SE 17 **`17.3 Sleep and Yield`** nêu rõ:

- `Thread.sleep` làm thread hiện tại **ngưng thực thi tạm thời** theo khoảng thời gian yêu cầu, chịu giới hạn độ chính xác của timers/scheduler.
- Sleep **không nhả monitors** mà thread đang sở hữu.
- `Thread.sleep` và `Thread.yield` **không có synchronization semantics**.
- JVM không bắt buộc flush writes từ registers ra shared memory trước sleep hoặc reload values từ shared memory sau sleep.

Hệ quả: code kiểu sau **không đúng**:

```java
// Fragment KHÔNG an toàn (chỉ minh họa, không nên chạy vô hạn)
class BrokenWorker {
    boolean done; // KHÔNG volatile

    void waitUntilDone() throws InterruptedException {
        while (!done) {
            Thread.sleep(100);
        }
    }
}
```

Thread khác có thể viết `done = true`, nhưng waiter **không được bảo đảm quan sát thay đổi**. JLS minh họa compiler có thể tái sử dụng giá trị đã đọc trong loop. Sleep **không phải polling-with-visibility guarantee**.

Một chương trình chạy thành công 100 lần chỉ cho thấy một nhóm interleavings, không tạo contract cross-thread.

### `sleep(0)` hoặc `yield()` càng không giúp

`Thread.sleep(0)` không phải `VarHandle.fullFence`; `Thread.yield()` chỉ là scheduling hint và có thể bị scheduler bỏ qua. Không có quy tắc JMM biến việc “nhường CPU” thành release–acquire hay memory fence công khai.

### `sleep` không phải cơ chế đảm bảo thứ tự

```java
Thread worker = new Thread(() -> {
    // doSomething();
});
worker.start();
Thread.sleep(100);
 // Không được mặc định worker đã hoàn tất.
```

Đây là fragment trong method throws/catch `InterruptedException`. Nếu cần chờ thread **hoàn thành**, dùng `join`, `Future.get` hoặc cơ chế completion tương đương. Nếu cần chờ một **điều kiện mutable**, dùng `volatile` đúng cách, `wait/notify`, `CountDownLatch`, `BlockingQueue` hoặc abstraction concurrency phù hợp.

## 8. Sleep cũng không nhả monitor: minh họa chạy được

Tạo file **`SleepKeepsMonitorDemo.java`**:

```java
public class SleepKeepsMonitorDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object lock = new Object();

        synchronized (lock) {
            System.out.println("beforeSleep="
                    + Thread.holdsLock(lock));
            Thread.sleep(20);
            System.out.println("afterSleep="
                    + Thread.holdsLock(lock));
        }

        System.out.println("afterBlock="
                + Thread.holdsLock(lock));
    }
}
```

```bash
javac --release 17 SleepKeepsMonitorDemo.java
java SleepKeepsMonitorDemo
```

**Stdout chính xác nếu không bị interrupt ngoài:**

```text
beforeSleep=true
afterSleep=true
afterBlock=false
```

Sleep có thể kéo dài **khác chính xác 20 ms** và thread có thể không được chạy lại ngay sau mốc timer. Nhưng nó **không thả monitor** trong lúc chờ; `Thread.holdsLock` vẫn true trước và sau sleep bên trong block. Khi ra khỏi synchronized block, ownership mới được release.

**Cảnh báo thực hành:** giữ monitor trong lúc ngủ làm thread khác đang cần monitor ấy phải chờ. Không dùng `Thread.sleep` để “giảm tranh chấp” ngay trong critical section; thường nó **kéo dài** contention.

## 9. `volatile` sửa bài toán visibility của flag như thế nào?

Khai báo một flag `volatile` khiến các accesses tới flag tham gia **synchronization order**. Một volatile write (release-like) trước một volatile read (acquire-like) tiếp theo của **chính field đó** tạo quan hệ synchronizes-with; từ đó transitive HB có thể chuyển các writes trước publish tới reader.

```java
class Signal {
    int payload;
    volatile boolean ready;
}
```

Mô hình:

```text
Writer thread:                 Reader thread:

payload = 42                  while (!ready) ...
ready = true  --sw--->         read ready == true
                               read payload == 42

Các writes vào payload trước volatile write được sắp
trước các reads của reader sau volatile read tương ứng.
```

**Không có nghĩa `payload` tự biến thành volatile.** Chúng được order nhờ protocol publish/read qua **cùng volatile ready** và không có các writes khác gây race lên payload trong lúc sử dụng.

### Java 17 runnable: volatile publication

Tạo file **`VolatileSignalDemo.java`**:

```java
public class VolatileSignalDemo {
    private int payload;
    private volatile boolean ready;

    private void publish() {
        payload = 42;
        ready = true;
    }

    private int awaitValue() {
        while (!ready) {
            Thread.onSpinWait();
        }
        return payload;
    }

    public static void main(String[] args)
            throws InterruptedException {
        VolatileSignalDemo signal = new VolatileSignalDemo();
        Thread producer = new Thread(signal::publish, "producer");
        producer.start();

        int result = signal.awaitValue();
        producer.join();
        System.out.println("payload=" + result);
    }
}
```

```bash
javac --release 17 VolatileSignalDemo.java
java VolatileSignalDemo
```

**Stdout sau khi cả hai threads tiến triển và không gặp sự cố runtime:**

```text
payload=42
```

Reader chỉ đọc `payload` sau khi quan sát `ready=true` từ volatile. Vì `payload=42` theo program order trước volatile write và reader đọc ready trước payload, có HB qua volatile.

**Đây là demo spin-wait để giải thích JMM, không phải mẫu waiting production**: nó đốt CPU, JVM/scheduler không cam kết một deadline mà thread producer phải được chạy, và có thể kéo dài vô hạn nếu producer không được scheduling. `Thread.onSpinWait` chỉ là hint cho CPU/runtime; **nó không thay thế volatile** và không tự tạo HB. Trong production, cân nhắc `CountDownLatch`, `BlockingQueue` hoặc `CompletableFuture`.

## 10. `volatile` không biến `count++` thành atomic

Sai lầm thường gặp:

```java
volatile int count;

void increment() {
    count++; // vẫn là read + add + write
}
```

Đây là fragment. `volatile` áp đặt các quy tắc visibility/ordering và atomicity của **từng volatile read/write**, nhưng phép read–modify–write không trở thành transaction nguyên tử.

Hai threads vẫn có thể:

```text
count ban đầu = 7
A read count => 7
B read count => 7
A write 8
B write 8

Kết quả = 8, dù có hai increment operations.
```

Nếu nhiều threads cùng tăng counter, dùng `synchronized`/`ReentrantLock` hoặc `AtomicInteger.incrementAndGet()` theo yêu cầu. `LongAdder` phù hợp một số thống kê throughput cao nhưng semantics của `sum()` dưới concurrent updates khác với một atomic snapshot.

### Ví dụ `AtomicInteger` có kết quả xác định

Tạo file **`AtomicIncrementDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicIncrementDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger count = new AtomicInteger();
        Runnable job = () -> {
            for (int i = 0; i < 10_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread a = new Thread(job, "A");
        Thread b = new Thread(job, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("count=" + count.get());
    }
}
```

```bash
javac --release 17 AtomicIncrementDemo.java
java AtomicIncrementDemo
```

**Stdout khi threads kết thúc bình thường:**

```text
count=20000
```

`incrementAndGet` cung cấp atomic read-modify-write; `join` còn cho main biết hai worker threads đã kết thúc và mọi updates được quan sát đúng.

## 11. `synchronized`: mutual exclusion và happens-before

`synchronized(lock)` không chỉ làm hai threads không thể cùng sở hữu **một monitor**. Theo JMM, **unlock của monitor M** synchronizes-with **mọi lock tiếp theo** của chính M trong synchronization order.

```java
class Box {
    int value;

    synchronized void write(int x) {
        value = x;
    }

    synchronized int read() {
        return value;
    }
}
```

Cả hai instance methods dùng monitor **`this`**. Khi reader chạy sau writer đã unlock **cùng instance** và không có write khác, reader thấy update phù hợp. Nếu gọi methods trên **hai Box objects khác nhau**, không có chung monitor để bảo vệ một shared state chung.

### Mẫu dùng synchronized không cần volatile riêng

Tạo file **`MonitorStateDemo.java`**:

```java
public class MonitorStateDemo {
    static final class Box {
        private int value;

        synchronized void set(int v) {
            value = v;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Box box = new Box();
        Thread writer = new Thread(() -> box.set(42));
        writer.start();
        writer.join();

        System.out.println("value=" + box.get());
    }
}
```

```bash
javac --release 17 MonitorStateDemo.java
java MonitorStateDemo
```

**Stdout:**

```text
value=42
```

Ví dụ có **hai nguồn HB**: writer unlock→main get lock của cùng Box, và writer completion→main successful `join`. Vì vậy không dùng nó để chứng minh riêng synchronized là cạnh duy nhất; nó cho thấy pattern hợp lệ và kết quả xác định.

Muốn kiểm chứng locking correctness không dựa vào sleeps, có thể thêm nhiều readers/writers cùng dùng Box, dùng barrier khởi động và assertions về invariants, nhưng scheduling và throughput sẽ không xác định.

## 12. `Thread.start` tạo HB mà sleep không tạo được

JLS `17.4.4–17.4.5` xác định gọi `t.start()` synchronizes-with action đầu tiên trong thread `t`. Tất cả actions được thực hiện bởi thread khởi chạy **trước start** theo program order có đường HB tới actions của thread mới.

Ví dụ:

```java
int[] data = {1, 2, 3};
Thread worker = new Thread(() ->
        System.out.println(data[0] + data[1] + data[2]));
worker.start();
```

Đây là fragment. Mảng `data` được tạo và điền trước `start`, thread mới được bảo đảm thấy initialization phù hợp. **Không cần sleep để “đợi mảng xuất hiện trong RAM”**.

Tuy nhiên `start()` **không** tự đồng bộ các writes xảy ra **sau** `start` từ parent sang worker. Nếu parent còn sửa `data` sau start trong khi worker đọc mà không có synchronization, vẫn có thể có data race.

### `join` tạo chiều ngược lại

Khi main gọi `worker.join()` và thành công trở lại sau khi worker kết thúc, actions của worker happen-before những actions tiếp theo trong main.

```text
Main:  initialize input
       start(worker) --sw---> Worker đọc input
                                   |
                                   | tính result = 42
                                   v
Main:  join(worker) thành công <-- thread termination
       read result (đảm bảo visibility)
```

`Thread.sleep` không có vai trò đồng bộ trong cả hai hướng ấy.

## 13. Java 17: `join` giải quyết đúng thứ tự completion

Tạo file **`JoinVisibilityDemo.java`**:

```java
public class JoinVisibilityDemo {
    private static int result;

    public static void main(String[] args)
            throws InterruptedException {
        int input = 21;
        Thread worker = new Thread(() -> result = input * 2);

        worker.start();
        worker.join();

        System.out.println("result=" + result);
    }
}
```

```bash
javac --release 17 JoinVisibilityDemo.java
java JoinVisibilityDemo
```

**Stdout:**

```text
result=42
```

Field `result` không volatile nhưng main đọc **sau successful join**: JMM cung cấp HB qua termination/join. Viết `Thread.sleep(100)` thay cho `join` sẽ **không** có cùng bảo đảm, kể cả nếu trên máy thử worker thường hoàn tất trong vài milliseconds.

### `join(timeout)` cần thêm điều kiện

Nếu dùng `worker.join(100)`, lời gọi có thể trở lại khi hết thời hạn dù worker còn chạy. Không thể chỉ vì `join(timeout)` returned mà giả định thread đã terminated. Kiểm tra `isAlive()`/completion condition phù hợp và semantics của API. Thực hành đơn giản nhất khi cần đợi kết thúc chắc chắn là `join()` không timeout, có chiến lược interruption/cancellation phù hợp.

## 14. CountDownLatch: thay sleep bằng một tín hiệu có contract

`CountDownLatch` có định nghĩa **memory consistency effects**: những actions trong thread trước khi gọi `countDown()` happen-before actions của một thread khác sau khi `await()` tương ứng thành công.

Tạo file **`LatchPublicationDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class LatchPublicationDemo {
    private static int payload;
    private static String label;

    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            payload = 42;
            label = "prepared";
            ready.countDown();
        }, "writer");
        writer.start();

        ready.await();

        System.out.println("payload=" + payload);
        System.out.println("label=" + label);
        writer.join();
    }
}
```

```bash
javac --release 17 LatchPublicationDemo.java
java LatchPublicationDemo
```

**Stdout khi writer hoàn tất bình thường:**

```text
payload=42
label=prepared
```

Vì writer ghi `payload`, `label` rồi `countDown()`, main `await()` thành công trước khi đọc: **HB đã được thư viện concurrency cam kết**, dù hai fields thông thường không volatile.

Điểm khác biệt với sleep:

| Sleep | CountDownLatch |
| --- | --- |
| Chờ một khoảng thời gian tương đối | Chờ một **sự kiện** count đạt 0 |
| Không biết producer đã chuẩn bị xong chưa | `await()` thành công xác nhận latch đã mở |
| Không cung cấp HB do chính sleep | Có memory-consistency edge được API quy định |
| Không đảm bảo scheduler chạy producer | Cũng không hứa deadline, nhưng protocol sự kiện là đúng khi producer tiến triển |
| Không có kết quả điều kiện nghiệp vụ | Có completion signal hợp lệ |

`CountDownLatch` dùng một lần; nếu cần barrier lặp lại qua nhiều phases, dùng `CyclicBarrier`/`Phaser` hoặc thiết kế workflow khác.

## 15. `wait/notify`: khác `sleep` ở quyền sở hữu monitor

Một thread đang trong `synchronized(lock)` có thể gọi `lock.wait()` khi giữ monitor:

- `wait()` **nhả monitor của chính object `lock`** và chuyển thread sang wait set theo quy tắc API.
- Khi thức dậy (notification, interruption, timeout/spurious wakeup theo semantics), nó phải **tái acquire monitor** trước khi tiếp tục/throw phù hợp.
- `notify()`/`notifyAll()` cần caller đang sở hữu monitor; việc notify không tự nhả monitor ngay lập tức.
- Luôn dùng `while (!condition) lock.wait()`, vì thức dậy không đảm bảo business condition đã đúng.

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    consumePayload();
}
```

Đây là fragment trong method có `throws InterruptedException` hoặc catch phù hợp, và `lock`, `ready`, `consumePayload` được khai báo.

**`sleep` khác hoàn toàn:** ngủ bên trong synchronized giữ monitor, không tạo event-notification protocol và không bảo đảm field plain `ready` sẽ được reload.

## 16. Java 17: wait/notifyAll có điều kiện và output ổn định

Tạo file **`WaitConditionDemo.java`**:

```java
public class WaitConditionDemo {
    static final class Mailbox {
        private boolean ready;
        private int data;

        synchronized void publish(int value) {
            data = value;
            ready = true;
            notifyAll();
        }

        synchronized int receive() throws InterruptedException {
            while (!ready) {
                wait();
            }
            return data;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Mailbox box = new Mailbox();
        Thread writer = new Thread(() -> box.publish(42));
        writer.start();

        int observed = box.receive();
        writer.join();
        System.out.println("observed=" + observed);
    }
}
```

```bash
javac --release 17 WaitConditionDemo.java
java WaitConditionDemo
```

**Stdout khi hoàn tất bình thường:**

```text
observed=42
```

- Nếu writer publish trước, `ready` đã true và reader không cần wait.
- Nếu reader tới trước, nó `wait` và nhả monitor cho writer, rồi tái acquire sau notify.
- `data` plain field vẫn an toàn theo **monitor ordering**: cả writes và reads được thực hiện trong synchronized methods của **cùng Mailbox instance**.
- `writer.join()` sau `receive` không phải lý do duy nhất reader thấy data; điều kiện và monitor protocol đã xử lý an toàn.

Đừng dùng `if (!ready) wait()`: phải chịu **spurious wakeups** và kiểm tra lại điều kiện sau khi reacquire.

## 17. Vậy một “data-race-free” chương trình được bảo đảm điều gì?

JLS `17.4.5` nêu nguyên tắc nổi bật: một chương trình **correctly synchronized** (không có data races trong các executions theo sequential consistency) cho kết quả có thể hiểu theo **sequential consistency**. Nói thực dụng: nếu mọi shared mutable state có synchronization protocol đúng, bạn không cần đoán compiler/CPU đã hoán đổi machine instructions nào để suy ra các giá trị racy bất ngờ.

**Sequential consistency** nghĩa tồn tại một total order các actions của nhiều threads mà mỗi thread vẫn giữ program order của nó và reads thấy các writes phù hợp với thứ tự đó.

Nhưng tránh ba nhầm lẫn:

- **Không** có nghĩa thread A chạy toàn bộ trước thread B; actions từ nhiều threads có thể interleave.
- **Không** có nghĩa scheduler công bằng hoặc không thể deadlock; JMM là mô hình memory behavior, không bảo đảm liveness.
- **Không** có nghĩa mọi method call bất kỳ tự atomic; critical section/atomic operations phải bao đúng invariant.

Một program data-race-free vẫn có thể có **logical race** (ví dụ hai clients đặt hàng cuối cùng khi nghiệp vụ không đặt đủ lock/transaction), hoặc deadlock vì thứ tự locks ngược, dù riêng memory visibility có thể tuân theo JMM.

## 18. Data race trong Java không có nghĩa “mọi thứ đều có thể xảy ra”

Không nên lấy định nghĩa `undefined behavior` của C/C++ để áp máy móc lên Java. JMM vẫn giới hạn tập executions hợp lệ:

- Compiler phải bảo toàn intra-thread semantics phù hợp.
- Các reads có ràng buộc về writes mà chúng có thể quan sát theo JMM.
- Volatile, locks, thread start/join và các synchronization actions phải tuân thủ ordering.
- `final` field initialization có các quy tắc đặc biệt.
- **Causality requirements** ngăn một số giá trị “out of thin air”.

Tuy nhiên, **không có HB** cho conflicting plain accesses khiến kết quả có thể khác một sequentially consistent trace và ứng dụng không được dựa vào sự “thường thấy” trên phần cứng.

Đừng thiết kế correctness dựa vào chuyện “x86 có strong memory ordering nên plain field chắc ổn”, hoặc “JDK HotSpot của tôi vẫn đọc lại biến sau mỗi `sleep`”. JVM phải portable qua compiler optimizations, CPU architectures và updates.

## 19. Safe publication: xuất bản object graph đúng cách

Một shared object có thể được dựng đúng bên thread A nhưng thread B cần **một sự kiện publish** hợp lệ để nhận những writes trước đó.

Mẫu volatile reference:

```java
final class Config {
    final int port;
    final String host;

    Config(int port, String host) {
        this.port = port;
        this.host = host;
    }
}

class Holder {
    volatile Config current;

    void publish() {
        Config cfg = new Config(8080, "localhost");
        current = cfg;
    }
}
```

Đây là fragments, không có `main`. Khi thread khác đọc `holder.current` qua volatile và thấy reference được publish, các writes trước volatile write có các HB guarantees phù hợp. **Không sửa `cfg` sau publish** nếu muốn giữ một immutable snapshot ổn định, trừ khi có synchronization khác.

Ngoài volatile, safe publication có thể đạt bằng:

- Khởi tạo trước `Thread.start` rồi truyền object cho worker.
- Guard publication và consumption bằng cùng monitor.
- Thread-safe concurrent collections/queues với API memory-consistency effects.
- `CountDownLatch`/`Future`/`CompletableFuture` theo đúng contract.
- Class initialization: JVM bảo đảm initialization synchronization phù hợp.
- Final field semantics khi object được xây dựng đúng và `this` không thoát sớm.

### Safe publication không tự làm object mutable thread-safe vĩnh viễn

Sau khi một reference được publish an toàn, nếu nhiều threads vẫn sửa non-final fields của object mà không có protocol mới, **data races vẫn có thể xảy ra**. Safe publication giúp người đọc thấy trạng thái **tại thời điểm publish** trong những điều kiện phù hợp; các mutations sau đó cần synchronization thích hợp.

## 20. `final` fields và constructor: lợi ích nhưng có giới hạn

JLS `17.5` quy định **final field semantics** đặc biệt: khi object được constructed đúng và `this` không escape khỏi constructor, các final fields có những bảo đảm initialization ngay cả khi reference được chuyển tới thread khác mà không có synchronization đầy đủ.

```java
final class Message {
    final int code;
    final String text;

    Message(int code, String text) {
        this.code = code;
        this.text = text;
    }
}
```

Đây là class fragment, không có `main`. `final` giúp bảo vệ trạng thái đã xây dựng đúng nhưng không đồng nghĩa mọi mutable object con sâu trong graph **tự động thread-safe** hoặc mọi hành vi sau initialization là an toàn.

Đặc biệt tránh **this escape**:

```java
// Sai thiết kế: xuất bản this trong constructor.
class BadPublication {
    static BadPublication shared;
    final int number;

    BadPublication() {
        shared = this;
        number = 42;
    }
}
```

Đây là snippet minh họa **cách làm không an toàn**, không phải chương trình được khuyến nghị. Nếu reference thoát trước khi final fields được gán/constructor hoàn thành, các bảo đảm initialization mong muốn có thể bị phá.

Không viết rằng “đọc một final field luôn thấy 0 nếu race”; cũng không viết rằng “final thay được synchronized cho mọi mutable state”. Hãy đọc đúng `JLS 17.5`.

## 21. `volatile` và compound invariants: visibility không đủ

Giả sử:

```java
class Range {
    volatile int min;
    volatile int max;

    void update(int low, int high) {
        min = low;
        max = high;
    }
}
```

Hai fields `volatile` bảo đảm các reads/writes riêng có ordering, nhưng reader có thể quan sát **min mới, max cũ** nếu thread khác đọc giữa hai writes. Nếu cần invariant `min <= max` luôn được quan sát theo một snapshot nhất quán, thiết kế phải dùng synchronized, immutable snapshot qua **một volatile reference**, hoặc atomic protocol cho toàn bộ trạng thái.

### Sửa bằng immutable snapshot

```java
record RangeSnapshot(int min, int max) {}

class RangeHolder {
    private volatile RangeSnapshot snapshot =
            new RangeSnapshot(0, 0);

    void set(int low, int high) {
        snapshot = new RangeSnapshot(low, high);
    }

    RangeSnapshot get() {
        return snapshot;
    }
}
```

Đây là fragment Java 17. Một volatile reference update publish **cả object immutable snapshot** theo một hành động read/write reference nguyên tử; reader dùng một local `RangeSnapshot r = holder.get()` rồi đọc cả `r.min()` và `r.max()` để có values thuộc **cùng snapshot**.

Nếu caller gọi `holder.get()` **hai lần khác nhau**, nó có thể đọc hai versions khác nhau; không biến composite read thành snapshot nếu không dùng cùng local reference.

## 22. `sleep` không bảo đảm deadline, fairness hay thread completion

Ngoài memory visibility, `Thread.sleep` không có các guarantees sau:

| Mong muốn | `sleep` có đảm bảo? | Thay bằng gì khi cần |
| --- | --- | --- |
| Thread khác đã chạy tới một statement cụ thể | **Không** | `CountDownLatch`/barrier/handshake |
| Thread khác đã kết thúc | **Không** | `join`/`Future.get` |
| Các writes trong thread khác đã visible | **Không chỉ vì sleep** | HB qua volatile/locks/latch/join |
| Nhả monitor trong lúc ngủ | **Không** | `Object.wait`/`Condition.await` khi phù hợp |
| Ngủ chính xác N milliseconds | **Không** | Scheduler/timer có giới hạn; xử lý timeout bằng deadlines/clock |
| Nhường CPU cho thread được chọn | **Không** | Scheduler quyết định; `yield` chỉ hint |
| Đảm bảo một thread cuối cùng được schedule | **Không** | Liveness fairness không phải contract của sleep |
| Đảm bảo composite operation atomic | **Không** | Atomic API/lock/transaction |
| Bảo vệ queue và tránh mất notifications | **Không** | BlockingQueue/Condition/monitor protocol |
| Tránh deadlock khi đang giữ locks | **Không** | Lock ordering, timeouts, quản lý critical section |

Trong test concurrency, `Thread.sleep(100)` “để thread A chạy trước B” thường là **flaky test pattern**. Trên CI chậm, thread B có thể chưa được CPU cho tới sau 100 ms; trên máy nhanh, B có thể vượt A ngay lập tức. Thiết kế test phải dùng latch/barrier để đặt đúng interleaving hoặc điều kiện cần quan sát.

## 23. Hai ví dụ kiểm thử: race condition và đồng bộ sự kiện

### Sai: ngủ để chắc producer đã ghi xong

```java
// Mã minh họa sai, KHÔNG có output cố định.
static int result;

static void broken() throws InterruptedException {
    new Thread(() -> result = 42).start();
    Thread.sleep(100); // không chứng minh writer finished
    System.out.println(result);
}
```

Thread có thể chưa được schedule, nên main có thể thấy `0`; kể cả trong runs writer đã thực hiện write trước khi main đọc theo wall-clock, vẫn thiếu HB cho field plain `result` nếu không có synchronization.

### Đúng: chờ producer hoàn thành

```java
static int result;

static void corrected() throws InterruptedException {
    Thread t = new Thread(() -> result = 42);
    t.start();
    t.join();
    System.out.println(result); // 42 nếu thread completed bình thường
}
```

Đây là fragments. `join` tạo HB từ actions của producer tới main sau successful join. Nếu producer throw exception trước assignment hoặc bị cancel, phải xử lý completion/failure theo business protocol; `join` không tự bảo đảm business work thành công.

### Đúng: chờ event “dữ liệu đã sẵn sàng” thay vì cả thread kết thúc

Dùng `CountDownLatch` khi producer còn có công việc khác sau khi dữ liệu ready; dùng `BlockingQueue` nếu producer/consumer trao nhiều messages; dùng `CompletableFuture`/`Future` nếu cần truyền value hoặc failure.

## 24. Thread interruption: sleep bị interrupt khác synchronization protocol

`Thread.sleep` có thể ném `InterruptedException` nếu thread bị interrupt. Khi ném exception đó, **interrupted status được clear** theo API `Thread.sleep`. Nhưng hành động `interrupt` và phát hiện interrupt có thể tham gia **synchronizes-with** theo JLS. Đây là synchronization từ **interrupt protocol**, **không phải bản thân sleep**.

Hai ý cần tách:

1. **`Thread.sleep` không có synchronization semantics** riêng.
2. Một event khác như `interrupt()/InterruptedException` có những semantics được JMM quy định.

Nếu bắt `InterruptedException` nhưng không thể xử lý, thường nên khôi phục trạng thái interrupt:

```java
try {
    Thread.sleep(100);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là fragment. Khôi phục interrupt là một quyết định về **cancellation contract**; trong code có API ném `InterruptedException` ra caller, nhiều khi tốt hơn là propagate. Không dùng loop nuốt exception rồi tiếp tục sleep vô hạn khiến worker không thể shutdown sạch.

## 25. Busy-wait, `Thread.onSpinWait` và backoff không thay JMM

Một loop:

```java
while (!ready) {
    Thread.onSpinWait();
}
```

là fragment **chỉ đúng visibility nếu `ready` đã được đồng bộ phù hợp**, chẳng hạn volatile. `Thread.onSpinWait()` là **performance hint** cho ngắn hạn spin-wait loops, không tự đặt memory fence/happens-before giữa producer và consumer.

Các kỹ thuật khác như exponential backoff và `LockSupport.parkNanos` phục vụ scheduling/CPU usage nhưng **không thay thế protocol truyền trạng thái**. Khi dùng `park/unpark` cần tuân thủ semantics cấp phép của API; không suy mọi plain field write xung quanh bất kỳ sleep/park đều visible một cách phổ quát.

Một busy-wait với non-volatile flag có thể bị JIT tối ưu làm hoist field read ra ngoài loop khi các constraints cho phép. Thêm sleep vào giữa không bắt compiler phải reload theo JLS.

## 26. Lưu ý về `long`/`double` và atomicity của một access

JLS `17.7` cho phép những **non-volatile `long`/`double` reads/writes** được xử lý như hai 32-bit halves trong những trường hợp mà specification mô tả; vì vậy portability code không nên mặc định mọi nonvolatile 64-bit primitive access đều atomic như volatile.

Đồng thời:

- **Volatile `long` và `double`** có atomicity được JMM đảm bảo cho các accesses đơn lẻ phù hợp.
- Atomicity của **một write/read** khác với atomicity của `counter++`.
- Một số HotSpot/hardware configurations thực tế thực hiện nonvolatile 64-bit access atomically, nhưng không thể lấy điều đó làm universal Java SE guarantee.
- Thêm volatile không làm operations gồm nhiều fields thành transaction nguyên tử.

Không dùng mô hình “tất cả races chỉ có stale reads” — còn có lost updates, inconsistent snapshots và các reordering effects.

## 27. Khi nào memory barrier/fence thật sự cần được nắm?

`volatile`, intrinsic locks, atomics và thư viện concurrency được JVM hiện thực bằng tập cơ chế thấp hơn, có thể gồm compiler barriers, CPU fences, atomic read-modify-write instructions và cache-coherence behavior. Nhưng JMM là **semantic contract**, không phải danh sách instruction assembly cố định.

Ví dụ:

- Trên một CPU architecture, compiler có thể cần machine fence để đáp ứng volatile ordering.
- Trên architecture khác, một số ordering có thể tự được bảo đảm bởi instruction/store model, nên codegen khác.
- JIT có thể gộp, di chuyển hoặc loại các barriers không cần thiết nếu vẫn giữ Java semantics.
- Bytecode `monitorenter`/`monitorexit` là cơ chế synchronization ở class-file level; JIT code có thể dùng fast paths hoặc lock elimination trong điều kiện hợp lệ.
- VarHandle modes (`getAcquire`, `setRelease`, `getVolatile`, `setVolatile`) có contracts riêng, không phải mọi mode tương đương full volatile.

Vì vậy **đừng đọc JVM assembly từ một máy rồi viết kết luận universal về Java ordering**. Khi cần correctness, chọn public abstraction đúng (`volatile`, synchronized, atomic, concurrent collections). Khi cần tối ưu low-level, nghiên cứu `VarHandle` memory-order modes và đo theo JDK/hardware cụ thể.

## 28. Một lỗi phổ biến: giữ lock khi `sleep` gây starvation

Giả sử:

```java
synchronized (lock) {
    updateState();
    Thread.sleep(500);
}
```

Đây là fragment trong method throws/catch `InterruptedException`. Sleep **không thả monitor**, nên thread khác cần `lock` có thể bị block suốt 500 ms hoặc lâu hơn. Nếu lặp lại nhiều lần dưới lock, throughput giảm và tail latency tăng.

Sửa hướng thiết kế nếu invariant cho phép:

```java
synchronized (lock) {
    updateState();
}
Thread.sleep(500);
```

Nhưng **không di chuyển sleep ngoài lock chỉ theo cảm tính** nếu business protocol đòi một thao tác atomic hoặc condition waiting; khi đó có thể dùng `wait/notify` hoặc `Condition.await`. Điều phải xác định trước là **cái gì cần mutual exclusion** và **khi nào release lock an toàn**.

## 29. Điều gì `System.out.println` có thể che giấu trong race demo?

Một số demo concurrency dùng `System.out.println` liên tục giữa threads và kết luận “không race” vì output có vẻ tuần tự. Thực tế, implementation của `PrintStream` và I/O có thể có synchronization hoặc scheduling side effects, làm interleavings thay đổi.

Không dựa vào nó để suy plain field accesses ở những paths khác đã được đồng bộ đúng. Ngược lại, println chỉ trong **main sau join** như `ReorderingLitmus` không sửa data race giữa hai worker threads.

Thực hành benchmark/race tests:

- Tách sampling/output khỏi hot critical path.
- Dùng tests stress có barriers để tạo concurrency, không sleep cố đoán.
- Không đồng nhất “stress test không fail” với proof.
- Dùng formal JMM reasoning hoặc công cụ concurrency testing chuyên dụng cho cases nhạy cảm.
- Đối chiếu interpreter/JIT/hardware configurations mà không dựa vào một CPU duy nhất.

## 30. Checklist code review về sleep, ordering và race

Trước khi merge code nhiều threads, trả lời các câu sau:

1. **Biến nào shared?** Instance field, static field, array element, hoặc object graph được publish?
2. Có **conflicting accesses** không (ít nhất một write)?
3. Hai accesses có HB edge qua **cùng volatile variable**, **cùng monitor**, `start`/`join` hay API concurrency contract không?
4. Có phép `count++`, `check-then-act` hoặc hai writes cùng tạo invariant cần **atomicity** không?
5. Có dùng `Thread.sleep` để “đợi worker xong” thay vì `join`/`Future`?
6. Có dùng `Thread.sleep` trong synchronized block khiến thread khác chờ lâu?
7. Có spin-loop trên **plain boolean** và tưởng sleep/onSpinWait sẽ flush cache?
8. Có một `volatile` flag publish các payload writes **trước** signal, reader chỉ đọc sau acquire không?
9. Reader có còn đọc fields **trước** khi kiểm tra flag không?
10. Có writers khác sửa payload mà không đồng bộ dù đã publish?
11. Có test flaky vì dùng sleep để sắp xếp threads?
12. Có object bị **this-escape trong constructor**, phá safe-final-field publication không?
13. Có **join(timeout)** hoặc `await(timeout)` bị hiểu lầm là đã thành công dù hết hạn?
14. Có xử lý `InterruptedException` phù hợp cancellation contract?
15. Concurrent API được dùng có memory-consistency effects gì theo Java 17 docs?
16. Đã phân biệt **thread-safety**, **progress/liveness**, **fairness** và performance chưa?

## 31. Các hiểu lầm thường gặp

| Nhận định sai | Điều đúng |
| --- | --- |
| “Sleep 1 giây thì thread khác chắc đã chạy” | Scheduler/timer không bảo đảm thứ tự hoặc completion |
| “Sleep tự flush CPU caches” | JLS `17.3` nói sleep/yield **không có synchronization semantics** |
| “Sleep nhả synchronized lock” | Sleep **giữ** monitors; `Object.wait` có release/reacquire monitor đang wait |
| “Yield là memory fence” | `yield` chỉ hint scheduling, không tạo JMM HB |
| “Hai threads có thứ tự wall-clock là có HB” | Cần program-order/synchronizes-with edges thích hợp |
| “Không nhìn thấy race khi test thì không có data race” | Một lịch chạy thành công không phải proof |
| “Data race chỉ làm kết quả chậm” | Có thể gây sai giá trị, stale reads, lost updates, nontermination |
| “Java data race cho phép mọi giá trị bất kỳ” | JMM vẫn ràng buộc executions và causality |
| “volatile làm ++ nguyên tử” | Chỉ các accesses riêng; increment là read–modify–write |
| “Volatile reference làm toàn bộ object graph bất biến” | Mutations sau publication cần protocol riêng |
| “Mỗi volatile field đều tạo snapshot nguyên tử cho cả object” | Cần atomic composition hoặc immutable snapshot |
| “join chỉ chờ lịch scheduler, không giúp visibility” | Successful join tạo HB tới caller |
| “Thread.start chỉ schedule, không publish writes trước đó” | `start` có synchronizes-with edge |
| “CountDownLatch giống sleep vì đều chờ” | Latch có event protocol và memory-consistency effects |
| “wait() và sleep() giống nhau” | `wait` release/reacquire monitor; `sleep` không |
| “onSpinWait giúp plain boolean luôn được reload” | Hint CPU, không thay volatile |
| “x86 thấy ổn thì portable Java đúng” | JMM phải đúng trên JVM/hardware khác |
| “JIT tối ưu reorder tức vi phạm Java” | Reorder hợp lệ nếu vẫn tuân JMM/inter-thread constraints |
| “println làm các plain shared fields thread-safe” | I/O implementation side effects không thay protocol thích hợp |
| “Data-race-free nghĩa không bao giờ deadlock” | Deadlock/liveness khác memory consistency |
| “Chỉ cần final fields thì mọi graph mutable an toàn” | Final initialization rules có giới hạn và yêu cầu construction đúng |

## 32. Câu hỏi tự kiểm tra

**Câu 1.** Thread A ghi `done = true` vào field plain; B loop `while(!done) Thread.sleep(100)`. Có chắc B dừng?

**Không.** Không có HB/visibility guarantee; sleep không tạo synchronization, compiler có thể tái dùng giá trị cũ theo JLS.

**Câu 2.** Vì sao hai threads ghi mỗi thread một biến rồi đọc biến của nhau có thể cùng đọc 0?

Thiếu synchronization, JMM cho phép outcome `(0,0)` trong litmus ấy; việc này không chứng minh một reorder cụ thể đã xảy ra trong machine code.

**Câu 3.** Thread A gọi `t.start()` sau khi tạo mảng. Thread t có thấy giá trị đã gán trước start không?

**Có**, do HB từ actions trước start đến actions trong thread mới.

**Câu 4.** Main dùng `Thread.sleep(500)` thay `worker.join()`. Có được bảo đảm worker hoàn tất và data visible?

**Không**. Dùng successful `join` hoặc một completion primitive.

**Câu 5.** `volatile int count; count++;` có làm increment atomic không?

**Không**. Dùng `AtomicInteger.incrementAndGet` hoặc lock.

**Câu 6.** Writer ghi `payload=42` rồi `ready=true` volatile; reader quan sát ready true rồi đọc payload. Vì sao reader có thể tin payload?

Volatile write/read tạo synchronizes-with; HB bắc cầu nối payload write tới payload read, với điều kiện không có competing writes làm data race.

**Câu 7.** Sleep bên trong `synchronized(lock)` có thả lock để thread khác vào không?

**Không.** Thả khi monitor exit; `Object.wait` mới tạm release monitor được wait khi gọi đúng điều kiện.

**Câu 8.** Vì sao `while(!condition) wait()` tốt hơn `if(!condition) wait()`?

Vì spurious wakeups và cạnh tranh sau notification; phải kiểm tra lại predicate dưới cùng monitor.

**Câu 9.** `join(timeout)` return có luôn nghĩa thread đã terminated?

**Không.** Timeout có thể hết trước completion; kiểm tra trạng thái/kết quả.

**Câu 10.** Một chương trình đã data-race-free có thể deadlock không?

**Có.** Memory ordering correctness không đảm bảo progress/fairness.

**Câu 11.** `Thread.onSpinWait` có biến plain field thành volatile không?

**Không.** Nó là runtime hint, không tạo required memory consistency.

**Câu 12.** Tại sao `final` field tốt nhưng không sửa được mọi unsafe publication?

Constructor không được làm `this` escape sớm; và mutable state sau construction vẫn cần synchronization hợp lệ.

## 33. Tài liệu tham chiếu Java SE 17

- [JLS 17 `17.3` — Sleep and Yield](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.3): giải thích trực tiếp **không có synchronization semantics**, không flush/reload guarantees và sleep không thả monitors.
- [JLS 17 `17.4.1` — Shared Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.1): instance fields, static fields, array elements.
- [JLS 17 `17.4.3` — Program Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.3): actions trong mỗi thread.
- [JLS 17 `17.4.4` — Synchronization Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4): volatile, monitor, thread start/termination, interrupts.
- [JLS 17 `17.4.5` — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): HB, data races, correctly synchronized programs và sequential consistency.
- [JLS 17 `17.4.8` — Executions and Causality](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.8): ràng buộc causality, không suy mọi giá trị đều hợp lệ trong race.
- [JLS 17 `17.5` — Final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): constructor, final initialization, this-escape.
- [JLS 17 `17.7` — Non-Atomic Treatment of double and long](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.7): phân biệt nonvolatile và volatile 64-bit accesses.
- [Java SE 17 `Thread.sleep`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#sleep(long)): timeout, interrupted status, không thả monitors.
- [Java SE 17 `Thread.onSpinWait`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#onSpinWait()): performance hint, không phải volatile.
- [Java SE 17 `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): memory consistency effects của `countDown`/`await`.
- [Java SE 17 `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic read–modify–write operations.
- [Java SE 17 `Object.wait/notify`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): wait sets, monitor release/reacquisition.
- [Java SE 17 `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): các memory-ordering modes khi cần nghiên cứu cấp thấp.

**Ghi nhớ:** Java cho phép các phép biến đổi/reordering miễn giữ đúng **JMM**, nên một chương trình có **data race** không được bảo vệ bởi trực giác “các dòng source sẽ đến từng thread theo cùng thứ tự”. `Thread.sleep` chỉ là công cụ trì hoãn scheduler: **không đồng bộ memory, không bảo đảm worker đã chạy xong, không thả monitor, không làm plain flag thành volatile**. Muốn chương trình đúng, hãy xây dựng **happens-before** bằng `volatile`, intrinsic locks, `Thread.start/join` và concurrency APIs có contract rõ ràng; dùng atomic operations khi cần cả visibility **và** read–modify–write atomicity.
