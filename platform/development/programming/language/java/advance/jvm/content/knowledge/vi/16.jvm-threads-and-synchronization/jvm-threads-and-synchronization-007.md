# Tính nguyên tử, khả năng nhìn thấy và thứ tự thao tác giữa các luồng

## 1. Cùng truy cập bộ nhớ không có nghĩa cùng nhìn thấy một thứ

Trong Java đa luồng, nhiều threads có thể truy cập cùng một object/field trên heap, nhưng điều đó **không tự động** bảo đảm chương trình đúng. Một thread có thể cập nhật một field; thread khác có thể thấy giá trị cũ, hoặc các bước tạo thành một phép cập nhật có thể bị xen kẽ với bước của thread khác.

Ba nhóm tính chất cần phân biệt:

- **Atomicity (tính nguyên tử):** một **thao tác hoặc tổ hợp thao tác được đặc tả** diễn ra như một đơn vị không thể bị những thao tác cạnh tranh quan sát ở trạng thái trung gian theo atomicity contract.
- **Visibility (khả năng nhìn thấy):** các ghi từ thread A trở nên quan sát được trong thread B theo quy tắc **Java Memory Model (JMM)** khi có quan hệ đồng bộ thích hợp.
- **Ordering (thứ tự):** compiler/CPU/runtime có thể sắp xếp/tối ưu lệnh miễn hành vi hợp lệ theo JMM được bảo toàn; những quan hệ như **happens-before** đặt ràng buộc cho thứ tự quan sát liên luồng.

**Tóm tắt quan trọng:** một thao tác **atomic** chưa chắc cung cấp thứ tự/visibility cần thiết cho **những thao tác khác**; một biến `volatile` có visibility/ordering guarantees nhưng `count++` vẫn **không atomic**; một `synchronized` block có thể đồng thời bảo vệ atomicity của critical section và cung cấp happens-before giữa các lần lock/unlock **cùng monitor**.

### Ví dụ tối giản

~~~java
class Counter {
    int count;

    void increment() {
        count++;
    }
}
~~~

Đây là class minh họa, chưa có `main`. Nếu hai threads cùng gọi `increment()` trên **cùng instance** mà không đồng bộ, bạn không được bảo đảm kết quả bằng tổng số lần gọi. Câu lệnh `count++` gồm đọc giá trị, cộng 1, ghi lại — không phải một thao tác read-modify-write atomic theo JMM.

Ba vấn đề có thể song hành:

1. Hai threads có thể cùng đọc 5, cùng tính 6, cùng ghi 6: **lost update** (thiếu atomicity).
2. Một thread đọc giá trị không được đồng bộ từ thread kia: **visibility/data race**.
3. Compiler/CPU có thể cho phép các thao tác không được đồng bộ có thứ tự quan sát khiến code tưởng hợp lý theo source nhưng sai trong đa luồng: **ordering**.

Bài này giải thích chính xác ba thuộc tính, quan hệ giữa chúng và cách viết Java 17+ an toàn.

## 2. Mô hình Java Memory Model (JMM)

JMM được định nghĩa chủ yếu tại **Java Language Specification, Chapter 17 — Threads and Locks, §17.4**. Nó nói **những hành vi đọc/ghi nào hợp lệ** của một chương trình nhiều threads, không hứa mỗi Java source line tương ứng một machine instruction hay một lần “đồng bộ cache” vật lý.

Các thuật ngữ cốt lõi:

| Thuật ngữ | Diễn giải |
| --- | --- |
| **Action** | Read/write variables, lock/unlock, volatile accesses, thread-start/join-related synchronization actions… |
| **Program order** | Thứ tự các actions trong một thread theo ngữ nghĩa của thread ấy |
| **Synchronization order** | Một thứ tự toàn phần của synchronization actions trong một execution phù hợp JMM |
| **Synchronizes-with** | Quan hệ giữa những actions đồng bộ, ví dụ unlock monitor với lock sau trên cùng monitor |
| **Happens-before (HB)** | Bao đóng bắc cầu của **program order** và **synchronizes-with** |
| **Data race** | Hai conflicting accesses tới cùng variable từ các threads khác nhau, ít nhất một ghi, không có happens-before sắp thứ tự chúng |
| **Correctly synchronized** | Chương trình không có data races trong những sequentially consistent executions theo JLS; JMM bảo đảm các execution có vẻ sequentially consistent |

**Happens-before không chỉ có nghĩa A “xảy ra trước theo đồng hồ”.** Đây là **quan hệ quy tắc** khiến kết quả ghi của A được ràng buộc về visibility/ordering ở B; hai threads chạy trên cùng một CPU hoặc nhìn timestamps theo thời gian thực chưa đủ chứng minh HB.

### Cách suy luận bằng đồ thị HB

~~~text
Thread A                           Thread B
---------                          ---------
data = 42
    |
    v (program order)
volatile ready = true
    |
    | synchronizes-with (khi reader quan sát write phù hợp)
    +---------------------------------------+
                                            |
                                    if (ready)  // volatile read
                                            |
                                            v (program order)
                                     print(data)
~~~

Nếu `ready` là `volatile`, writer ghi `data=42` trước volatile write, và reader đọc `ready=true` theo synchronization order phù hợp, quy tắc HB bắc cầu buộc reader thấy `data=42` (giả sử không có cạnh tranh ghi `data` khác).

**Không suy** rằng mọi đọc `data` từ bất kỳ thread nào sẽ thấy giá trị mới **chỉ vì có volatile field khác trong cùng class**. Reader phải đi qua đúng synchronization edge hoặc một edge tương đương.

## 3. Atomicity: một read/write khác một read-modify-write

### 3.1. Những thao tác đơn lẻ

JLS quy định các read/write của **references** và primitive variables có kích thước **không quá 32 bit** là atomic ở cấp truy cập biến phù hợp. Với `long`/`double` **không volatile**, JLS `17.7` cho phép triển khai một read/write thành hai thao tác 32-bit theo quy tắc, nên không được dựa vào atomicity portable của plain 64-bit access trong trường hợp này. **Volatile `long`/`double` reads/writes là atomic.**

Điều này **không** biến chuỗi thao tác thành atomic. Một phép assignment atomic của `int` không có nghĩa hai lệnh `x = x + 1` trên hai threads được kết hợp đúng.

| Truy cập | Atomic theo semantics portable? | Đồng bộ liên luồng khác? |
| --- | --- | --- |
| Plain read/write `int` | Có, ở cấp read/write đơn lẻ | Không |
| Plain read/write reference | Có, ở cấp read/write reference đơn lẻ | Không |
| Plain read/write `long`/`double` | Không được bảo đảm 64-bit nguyên khối bởi JLS | Không |
| `volatile long` read/write | Có | Có volatile ordering/visibility |
| `volatile int` read/write | Có | Có volatile ordering/visibility |
| `volatile int++` | **Không**, vì nhiều bước | Có volatile accesses riêng lẻ nhưng không bảo vệ toàn bộ RMW |
| `AtomicInteger.incrementAndGet()` | **Có**, update atomic theo API | Có memory effects của atomic operation |
| `synchronized(lock) { count++; }` | Critical section được bảo vệ với cùng lock | Có monitor HB khi release/acquire đúng |

### 3.2. Lost update

~~~text
Ban đầu count = 5

Thread A                         Thread B
--------                         --------
read count -> 5
                                 read count -> 5
calculate 6
                                 calculate 6
write count = 6
                                 write count = 6

Kết quả: 6, dù đã có hai lần increment -> kỳ vọng logic: 7
~~~

Một **interleaving như trên** đủ giải thích vì sao hai reads cộng hai writes không phải nguyên tử. Với plain unsynchronized field, thực tế JMM còn cho phép thêm những hành vi visibility/ordering phức tạp; sơ đồ chỉ minh họa một failure mode.

### 3.3. Volatile không cứu `++`

~~~java
class VolatileCounter {
    volatile int count;

    void increment() {
        count++;
    }
}
~~~

**`volatile` không biến expression `count++` thành atomic read-modify-write.** JIT có thể tạo volatile read, add và volatile write với memory ordering phù hợp, nhưng vẫn có thể xen giữa thread khác. Đối với shared counter, dùng `AtomicInteger.incrementAndGet()`, `LongAdder.increment()` khi chấp nhận semantics cộng dồn phù hợp, hoặc `synchronized`/`Lock` nếu cần bảo vệ nhiều biến cùng lúc.

## 4. Visibility: vì sao dữ liệu đã ghi có thể chưa quan sát được?

Ví dụ:

~~~java
class StopFlag {
    boolean running = true;

    void work() {
        while (running) {
            // công việc
        }
    }

    void stop() {
        running = false;
    }
}
~~~

Đây là class minh họa **có data race nếu hai threads gọi `work`/`stop` không đồng bộ**, và không nên dùng nguyên xi trong ứng dụng. Một thread ghi `running=false` không tạo HB edge tới thread khác chỉ bằng plain assignment.

**Lỗi có thể gặp:** reader tiếp tục thấy stale value hoặc compiler/JIT tối ưu đường loop theo giả định không có synchronized modification phù hợp. JLS `17.4` có ví dụ về loop không terminating khi biến không được đồng bộ.

Không được kết luận từ việc chương trình “luôn dừng trên máy tôi” rằng nó đúng theo JMM: CPU cache, compiler tier, workload và timing có thể khiến bug chỉ xuất hiện lúc khác.

### `volatile` cung cấp gì?

~~~java
class StopFlag {
    volatile boolean running = true;

    void stop() {
        running = false;
    }
}
~~~

Đọc/ghi volatile có **ordering/visibility effects** theo JMM. Một volatile write tới `running` **synchronizes-with** các volatile reads tiếp theo của **cùng variable** trong synchronization order.

Điều đó cho phép flag protocol đúng về visibility nếu các actions khác được đặt đúng trước/sau. Tuy nhiên:

- JMM không hứa một thread chắc chắn được scheduler cho CPU trong một deadline.
- `volatile` không khóa nhiều statements lại thành transaction.
- Nếu chương trình cần wait/notify, blocking hoặc cancellation, ưu tiên `Interrupt`, `BlockingQueue`, `CountDownLatch` hay API concurrency phù hợp thay busy spin không giới hạn.

**Đừng giải thích volatile đơn giản là “mỗi lần đọc bắt buộc lấy từ RAM, không dùng CPU cache”.** Cơ chế vật lý có thể là cache coherence, barriers, compiler scheduling và CPU ISA; điều Java bảo đảm là **observable ordering/visibility semantics**, không chi tiết cache truy cập.

## 5. Ordering: code đúng trong một thread có thể sai khi suy liên luồng

Compiler/JIT và CPU có thể thực hiện transformations/reorderings **miễn giữ intra-thread semantics và hành vi được JMM cho phép**. Câu “Java chạy lệnh từ trên xuống dưới” chỉ an toàn khi nói **hành vi một thread như được quan sát theo quy tắc**; nó không dựng thứ tự toàn phần chung của plain unsynchronized accesses giữa tất cả threads.

Một litmus test nổi tiếng:

~~~java
// Ban đầu x = 0, y = 0
// Thread A                     // Thread B
x = 1;                           y = 1;
r1 = y;                          r2 = x;
~~~

Đây là **pseudocode concurrent litmus**, không phải Java class độc lập. Nếu `x`/`y` là plain shared `int` không đồng bộ, kết quả `r1 = 0` **và** `r2 = 0` là một behavior hợp lệ trong mô hình có data race ở tình huống này.

**Không cần giả định hai threads đã “du hành thời gian”.** Hai writes/reads không có HB edges nên JMM có thể cho phép những quan sát không tương ứng trực giác tuần tự của người đọc source.

Nếu cả `x` và `y` là `volatile` và các actions như trên, ordering đồng bộ làm cấu hình “cả hai reads đều 0” không phù hợp: mỗi thread có volatile write trước volatile read, nên synchronization order toàn phần không thể xếp cả hai reads trước writes tương ứng mà vẫn tôn trọng program order.

**Điểm quan trọng:** không nên dùng `Thread.sleep` hoặc `Thread.yield` để “chữa reordering”. Chúng không thiết lập cạnh HB thông thường giữa các plain writes/reads của hai threads.

## 6. Happens-before: cách hợp thức hóa visibility và ordering

JLS `17.4.5` xác định HB từ:

1. **Program order:** nếu action A trước B trong cùng thread thì A happens-before B.
2. **Synchronizes-with:** những cặp synchronization actions mà JLS quy định.
3. **Transitivity:** nếu A HB B và B HB C thì A HB C.

Những synchronization edges đáng nhớ:

| Nguồn (release) | Đích (acquire) | HB quan trọng |
| --- | --- | --- |
| `unlock` monitor M | `lock` sau trên **cùng monitor M** | Writes trong critical section trước được nhìn thấy phù hợp |
| `volatile write` field V | `volatile read` tiếp theo của **V** theo synchronization order | Các ordinary writes trước release có thể được publish |
| `Thread.start()` từ thread A | Những actions của thread được start | Dữ liệu chuẩn bị trước start được publish |
| Thread T hoàn tất | Actions ở thread khác phát hiện termination (`join` thành công, v.v.) | Kết quả do T ghi có thể đọc sau join |
| `interrupt` tới thread | Action nhận biết interrupt theo JLS | Ordering liên quan interruption |
| Class initialization theo JLS | Những accesses cần thấy class initialized | Các bảo đảm class-init synchronization |
| `CountDownLatch.countDown` | `await` return tương ứng | Memory consistency guarantee theo `java.util.concurrent` API |

**Cẩn thận:** `Thread.join()` có thể hoàn tất không bình thường qua `InterruptedException`/timeout; chỉ suy HB từ đúng semantics phát hiện thread termination. `await` cũng phải thành công theo contract để suy action relationship tương ứng.

### Release/acquire và transitive visibility

~~~text
Thread A                         Thread B
data = 42
ready = true   [volatile write] --sw--> [volatile read] ready == true
                                                |
                                                v
                                         print(data) => 42

data write --program order--> volatile write
volatile read --program order--> data read

=> data write happens-before data read.
~~~

Đây là **message-passing pattern** khi `data` chỉ được writer publish trước `ready`, không có competing writers ngoài protocol. Nếu reader chỉ xem `ready` như plain variable, không có synchronization edge và suy luận trên không còn đúng.

### HB không đồng nghĩa “real-time before”

Ngay cả khi log timestamp từ thread A nhỏ hơn timestamp từ thread B, không có đồng bộ thì log order không xây dựng HB cho shared field bạn muốn kiểm chứng. Logger/I/O có thể có locking riêng, vô tình đổi timing và che race.

## 7. Runnable Java 17+: AtomicInteger và synchronized counter

Tạo file **`AtomicityDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicityDemo {
    private static final Object LOCK = new Object();

    private static int protectedCount;
    private static final AtomicInteger atomicCount = new AtomicInteger();

    private static void runIncrements() {
        for (int i = 0; i < 100_000; i++) {
            synchronized (LOCK) {
                protectedCount++;
            }
            atomicCount.incrementAndGet();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread first = new Thread(AtomicityDemo::runIncrements);
        Thread second = new Thread(AtomicityDemo::runIncrements);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("synchronized=" + protectedCount);
        System.out.println("atomic=" + atomicCount.get());
    }
}
~~~

Chạy:

~~~bash
javac -g AtomicityDemo.java
java AtomicityDemo
~~~

**Stdout xác định nếu threads hoàn tất bình thường:**

~~~text
synchronized=200000
atomic=200000
~~~

Vì:

- Hai threads, mỗi thread chạy **100.000** increments.
- Cả hai truy cập `protectedCount` trong **cùng monitor LOCK**; increments không xen vào critical section đồng thời.
- `AtomicInteger.incrementAndGet()` là atomic update operation.
- Main gọi `join()` cả hai threads trước khi in, nên các actions trước completion được bảo đảm quan sát thích hợp theo HB.
- Chỉ main thread in stdout, nên thứ tự hai dòng cố định.

**Không đồng nhất semantics tổng thể:** synchronized bảo vệ được nhiều fields nếu cùng nằm trong protocol lock; `AtomicInteger` cung cấp atomic operations trên giá trị của riêng nó. Nếu muốn cập nhật **hai trường như một transaction**, chỉ hai `AtomicInteger` độc lập thường không đủ.

### Vì sao không đưa plain `count++` vào kết quả kỳ vọng?

Nếu thêm một plain `int racyCount++` bên cạnh, giá trị có thể nhỏ hơn 200.000, đôi khi bằng 200.000 do scheduling; **không có output cố định đáng tin**. Bài này không đo race bằng câu lệnh `println` mà chứng minh những cách triển khai đúng.

## 8. Runnable Java 17+: Volatile publication và message passing

Một ví dụ dùng volatile làm **cờ công bố dữ liệu**:

Tạo file **`VolatileMessage.java`**:

~~~java
public class VolatileMessage {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("payload=" + payload);
        });

        reader.start();

        Thread writer = new Thread(() -> {
            payload = 42;
            ready = true;
        });

        writer.start();
        writer.join();
        reader.join();

        System.out.println("ready=" + ready);
    }
}
~~~

Chạy:

~~~bash
javac -g VolatileMessage.java
java VolatileMessage
~~~

**Stdout khi các threads được lên lịch và hoàn tất bình thường:**

~~~text
payload=42
ready=true
~~~

Lý do `payload=42`:

1. Writer ghi plain `payload = 42` trước volatile write `ready=true`.
2. Reader kiểm tra `ready` bằng volatile read và thoát loop khi thấy true.
3. Volatile write/read cùng biến thiết lập synchronization/HB edge.
4. Theo transitivity, ghi `payload` happens-before đọc `payload` trong reader.
5. Main `join()` cả threads, sau đó đọc `ready` và in kết quả.

**Điều kiện thực tế:** JMM không cam kết thread sẽ luôn được scheduler cấp CPU trong một khoảng thời gian cụ thể; vòng spin không có deadline. Ví dụ phù hợp để hiểu visibility, không phải cách chờ production tốt cho hiệu suất. Với application thật, sử dụng `CountDownLatch`, `BlockingQueue`, `Condition` hoặc `CompletableFuture` để chờ thay vì busy spin; `Thread.onSpinWait` chỉ là hint cho CPU/JVM, không tự tạo memory synchronization edge.

**Không nhầm:** `payload` không cần khai báo volatile trong protocol này vì **volatility của cờ ready** đã đủ publish ordinary write trước cờ nếu protocol được tuân thủ. Nhưng nếu một thread khác vẫn sửa `payload` không đồng bộ, bài toán thay đổi.

## 9. `synchronized`: mutual exclusion đồng thời tạo HB

Một block:

~~~java
synchronized (lock) {
    balance = balance + amount;
    transactionCount++;
}
~~~

Là **đoạn code minh họa**, cần `lock`/`balance`/`transactionCount` và class thích hợp.

Nếu **mọi threads** dùng **cùng object monitor `lock`** để đọc/ghi các fields liên quan, monitor bảo đảm:

- **Mutual exclusion:** hai threads không chạy phần critical section của **cùng monitor** tại cùng thời điểm.
- **Visibility/ordering:** một monitor unlock **synchronizes-with** một lock tiếp theo của monitor đó.
- **Compound invariant:** có thể bảo vệ cả `balance` và `transactionCount` để chúng được cập nhật/quan sát thành một đơn vị logical transaction dưới lock.

**Sai phổ biến:** writer dùng `synchronized(lockA)`, reader dùng `synchronized(lockB)` và nghĩ vì “cả hai đều synchronized” nên đã có HB. Không — locks khác nhau không tạo edge unlock→lock của **cùng monitor**.

### Instance synchronized vs static synchronized

- `synchronized void f()` lock trên `this`.
- `static synchronized void g()` lock trên `YourClass.class`.
- `synchronized(otherObject)` lock trên `otherObject`.

Vì vậy `f()` của hai instances khác nhau không khóa cùng monitor. Dùng một shared lock cố định hoặc cùng instance theo ownership thực tế.

### Lock ở mọi đường đọc lẫn ghi

Nếu writer bảo vệ field dưới lock nhưng reader đọc field plain ngoài lock, không thể mặc định reader được synchronized-with writer. Thread safety cần **protocol đồng nhất** trên mọi accesses đến shared mutable state.

## 10. `volatile`: visibility/ordering không phải multi-field transaction

Xét:

~~~java
class PairState {
    volatile int x;
    volatile int y;

    void setBoth(int a, int b) {
        x = a;
        y = b;
    }

    int sum() {
        return x + y;
    }
}
~~~

Hai writes là **hai volatile writes riêng**, và hai reads là **hai volatile reads riêng**. Reader có thể đọc cặp giá trị từ **hai trạng thái khác nhau** khi writer xen vào. `volatile` không làm hai writes/tham chiếu thành một atomic snapshot.

Giải pháp tùy bài toán:

- Dùng `synchronized`/`Lock` quanh cả set/read.
- Dùng **immutable snapshot** được publish qua **một volatile reference**:
  
~~~java
record Snapshot(int x, int y) {}

volatile Snapshot current = new Snapshot(0, 0);
~~~

Đây là đoạn minh họa trong một class, không phải file độc lập. Khi writer gán một **new immutable Snapshot** vào `current` và reader đọc `current` **một lần** rồi lấy cả `x`/`y`, reader có snapshot nhất quán, không bị trộn fields giữa hai object versions.

**Cẩn thận:** nếu reader viết `current.x() + current.y()` mà gọi `current` hai lần, hai volatile reads có thể thấy hai snapshots khác nhau. Nên dùng:

~~~java
Snapshot snapshot = current;
int total = snapshot.x() + snapshot.y();
~~~

Đây là đoạn tiếp nối minh họa và cần context class. **Volatile reference không biến object được trỏ tới thành immutable**. Nếu object mutable bên trong bị sửa sau publish không đồng bộ, vẫn có race.

## 11. Atomic classes và Compare-And-Set (CAS)

`AtomicInteger`, `AtomicLong` và `AtomicReference` cung cấp atomic operations và memory effects được API ghi rõ, thường dựa trên VarHandle primitives/các machine-level synchronization instructions phù hợp.

### Compare-and-set

~~~java
AtomicInteger value = new AtomicInteger(10);

boolean ok = value.compareAndSet(10, 20);
int now = value.get();
~~~

Là đoạn minh họa cần import `java.util.concurrent.atomic.AtomicInteger`, kết quả `ok == true` và `now == 20` nếu không có thread khác can thiệp.

**CAS** kiểm tra giá trị hiện hành so với expected và chỉ cập nhật khi phù hợp như một thao tác atomic. Nó là building block cho lock-free algorithms, nhưng:

- **CAS failure** có thể do concurrent interference.
- Những **weak CAS** variants có thể **spuriously fail** theo API.
- `compareAndSet` một field **không tạo transaction** đồng thời trên nhiều fields.
- Nếu logic retry tính toán có **side effects**, gọi lại lambda trong `updateAndGet` có thể lặp side effects nhiều lần — API khuyến cáo function không có side effects.
- **ABA problem:** giá trị A→B→A khiến CAS so A vẫn thành công dù state thay đổi trong khoảng đó; với cấu trúc lock-free phức tạp cần version/stamps/algorithms phù hợp.

### `LongAdder` và snapshot consistency

`LongAdder` thích hợp cho counters có contention cao và `sum()` có thể tổng hợp nhiều cells, nhưng **`sum()` không phải atomic snapshot khi updates chạy đồng thời**. Không dùng `LongAdder` nếu mọi đọc phải mang tính linearizable như `AtomicLong.get()` trong một protocol cần atomic state.

## 12. Runnable Java 17+: toàn bộ state dưới cùng monitor

Tạo file **`LockedAccount.java`**:

~~~java
public class LockedAccount {
    private int balance;
    private int operations;

    public synchronized void deposit(int amount) {
        balance += amount;
        operations++;
    }

    public synchronized String snapshot() {
        return balance + ":" + operations;
    }

    public static void main(String[] args) throws InterruptedException {
        LockedAccount account = new LockedAccount();

        Thread a = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                account.deposit(2);
            }
        });
        Thread b = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                account.deposit(3);
            }
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("balance:operations=" + account.snapshot());
    }
}
~~~

Chạy:

~~~bash
javac -g LockedAccount.java
java LockedAccount
~~~

**Stdout chính xác nếu cả hai threads hoàn tất bình thường:**

~~~text
balance:operations=25000:10000
~~~

Giải thích:

- A đóng góp `5000 * 2 = 10000`, B đóng góp `5000 * 3 = 15000`, tổng **25000**.
- Tổng số lần `deposit` là **10000**.
- `deposit` và `snapshot` là **instance synchronized** trên **cùng `account`**, nên critical sections loại trừ nhau; main `join` bảo đảm hai threads đã hoàn tất trước snapshot.
- Đây là ví dụ nhiều fields phải nhất quán với nhau, khác với một `AtomicInteger` counter.

**Giới hạn:** ví dụ không kiểm soát amount âm hoặc overflow; nếu viết một tài khoản ngân hàng thực tế cần validation, semantics tiền tệ, transaction storage và domain rules riêng. Bài chỉ tập trung vào JMM.

## 13. Thread.start, Thread.join và safe handoff

Không phải chỉ `volatile`/`synchronized` mới tạo HB; lifecycle của threads cũng có synchronization rules.

### `Thread.start()`

~~~java
class StartExample {
    int data;

    void runExample() throws InterruptedException {
        data = 42;
        Thread worker = new Thread(() -> {
            System.out.println(data);
        });
        worker.start();
        worker.join();
    }
}
~~~

Đây là class minh họa, không có `main`. Ghi `data=42` trong parent thread xảy ra trước `start()` theo program order; `start()` tạo synchronizes-with edge tới thread worker. Vì thế worker thấy dữ liệu được publish phù hợp nếu không có competing writes.

### `Thread.join()`

Khi main thành công phát hiện worker đã kết thúc qua `join()`, actions của worker xảy ra trước việc main quan sát dữ liệu sau join theo JMM. Trong hai demos `AtomicityDemo` và `LockedAccount`, `join()` là phần quan trọng khiến main đọc kết quả sau khi mọi increments hoàn tất.

**Đừng suy** rằng `Thread.sleep(100)` thay thế `join()`. Sleep chỉ tạm dừng một thread, không đợi chính xác worker completion và không có cùng HB guarantee.

### Publication qua concurrent utilities

`java.util.concurrent` định nghĩa **memory consistency effects** cho nhiều utilities:

- Actions trước `CountDownLatch.countDown()` happen-before actions sau một `await()` tương ứng trả về thành công.
- Actions trước khi submit task cho `ExecutorService` happen-before task actions theo documented contract.
- Task actions happen-before actions sau `Future.get()` nhận kết quả thành công theo documented contract.
- Enqueue/dequeue trong concurrent collections có memory consistency guarantees theo từng API.

**Không phải cứ “dùng một method trong concurrent package” là mọi fields tự động thread-safe**. Luôn đọc contract của đúng operation và xây protocol phù hợp.

## 14. Runnable Java 17+: CountDownLatch thay busy spin

Tạo file **`LatchHandoff.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LatchHandoff {
    private static int payload;
    private static final CountDownLatch READY = new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            try {
                READY.await();
                System.out.println("payload=" + payload);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();

        Thread producer = new Thread(() -> {
            payload = 42;
            READY.countDown();
        });

        producer.start();
        producer.join();
        consumer.join();
        System.out.println("completed");
    }
}
~~~

~~~bash
javac -g LatchHandoff.java
java LatchHandoff
~~~

**Stdout trong lần chạy bình thường, không bị interrupt:**

~~~text
payload=42
completed
~~~

Ở đây `payload` **không cần volatile** vì producer ghi trước `countDown()`, consumer đọc sau `await()`; API `CountDownLatch` cung cấp HB, còn main `join` bảo đảm thứ tự in hai dòng.

Đây là pattern thích hợp hơn một vòng spin dài vì consumer **chờ có blocking mechanism**. Nếu consumer bị interrupt, code khôi phục interrupt flag và không in `payload`; output phía trên được nêu rõ chỉ cho normal execution.

**Không dùng `CountDownLatch` như resettable event:** count đã về 0 không reset. Nếu cần repeated signaling, cân nhắc `Phaser`, `Condition` hoặc API phù hợp.

## 15. Final fields và safe publication

JLS `17.5` đưa ra semantics đặc biệt cho **final fields**, rất hữu ích với immutable objects.

~~~java
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

Đây là class minh họa. Nếu constructor được thực hiện đúng, không để `this` escape trước khi hoàn tất, final-field semantics giúp những threads nhận reference thấy các final values được khởi tạo đúng trong những điều kiện JLS quy định.

**Không suy rằng toàn bộ object graph tự động thread-safe chỉ vì một reference là final.** Ví dụ:

~~~java
final class Holder {
    final int[] values = {1, 2, 3};
}
~~~

Reference field `values` là final, nhưng **các phần tử array vẫn mutable**. Nếu một thread sửa `values[0]` và thread khác đọc không đồng bộ, vẫn có race đối với phần tử.

### Safe publication hữu ích

Các lựa chọn an toàn để publish object mới:

- Chia sẻ thông qua **volatile reference** đúng protocol.
- Publish trong monitor/lock và đọc dưới cùng monitor/lock.
- Put/take qua một concurrent collection có memory consistency effects.
- Dùng thread-start/handoff và join theo documented HB.
- Xây object immutable và dùng **final fields** đúng, tránh `this` escape trong constructor.

**Final-field guarantees không phải license công bố mọi mutable state không đồng bộ**. Một object có final fields có thể an toàn hơn về initialization, nhưng mutable nested objects và việc publish reference vẫn cần cân nhắc protocol.

### Double-checked locking

Khi viết lazy singleton theo double-checked locking, trường `instance` phải dùng cơ chế publication thích hợp (thường **`volatile`**) để ngăn nguy cơ đọc instance chưa được publish đúng. Cách đơn giản và dễ kiểm chứng hơn là **static holder idiom** hoặc `enum` singleton khi phù hợp.

## 16. Reordering không đồng nghĩa chương trình được trả giá trị “tùy ý”

Một hiểu nhầm khác: nếu thiếu `volatile` thì Java “có thể trả bất kỳ bit pattern nào”. JMM **không** cho phép tùy tiện tạo các giá trị từ hư vô; nó có quy tắc well-formed executions và causality (§17.4.7–§17.4.8). Tuy vậy chương trình có data race có thể có hành vi không trực giác mà programmer không được phép bỏ qua.

Cách học đúng:

- Với **data-race-free design**, bạn có một mô hình để suy luận nhất quán theo synchronization/HB.
- Với **racy design**, đừng thay mô hình bằng những suy luận “CPU chắc chạy theo source” hoặc “trên x86 cache coherence sẽ cứu tôi”.
- Với **volatile**, dùng đúng release/acquire communication pattern hoặc atomic update methods, không xem nó như một lock.
- Với **locks**, bảo vệ mọi accesses cùng dữ liệu theo cùng protocol.

### Data race freedom và sequential consistency

JLS nói chương trình **correctly synchronized** có các executions trông như **sequentially consistent**. Nhưng sequential consistency **không tự làm một phép nhiều bước thành atomic**: nếu logic yêu cầu đọc/sửa/ghi như một transaction, bạn vẫn cần mutual exclusion hoặc atomic RMW. Đừng đồng nhất “không có data race” với “mọi invariant của nghiệp vụ chắc chắn đúng”.

## 17. VarHandle: Plain, Opaque, Acquire/Release, Volatile

Từ Java 9, `java.lang.invoke.VarHandle` cung cấp các access modes với những memory-ordering guarantees khác nhau, hữu ích khi xây primitives/concurrent structures cấp thấp.

| Mode | Ví dụ operations | Ý nghĩa khái quát |
| --- | --- | --- |
| **Plain** | `get`, `set` | Như truy cập non-volatile field, ít ordering; không tự giải quyết race |
| **Opaque** | `getOpaque`, `setOpaque` | Atomic/coherent đối với cùng variable theo API, ordering yếu hơn acquire/release |
| **Acquire** | `getAcquire` | Ngăn các accesses sau bị reorder lên trước theo semantics acquire; phối hợp với release |
| **Release** | `setRelease` | Publish các accesses trước theo semantics release; phối hợp với acquire |
| **Volatile** | `getVolatile`, `setVolatile` | Có volatile ordering guarantees mạnh hơn |
| **Atomic RMW** | `compareAndSet`, `getAndAdd` | Atomic update với memory semantics tương ứng mode |

**Mỗi access mode có hợp đồng riêng**; không được nói tất cả acquire/release/opaque/volatile đều tương đương hoặc mọi thao tác plain 64-bit là bitwise atomic. Java SE 17 `VarHandle` tài liệu hóa chi tiết differences, bao gồm spurious failures của weak CAS.

### Cẩn thận khi dùng fences

`VarHandle.fullFence()`, `acquireFence()`, `releaseFence()` và các methods liên quan hỗ trợ đặt ordering constraints, nhưng **không tự biến mọi plain variable access thành thread-safe protocol**. Fences không chữa một phép `count++` non-atomic thành atomic.

**Ưu tiên** `volatile`, `AtomicInteger`, `synchronized`, `Lock` hoặc concurrent utilities trước; chỉ dùng VarHandle/fences khi thật sự cần low-level algorithm và có khả năng kiểm chứng.

## 18. Java Memory Model và CPU memory model

CPU có cache coherence, store buffers và instruction reordering; compiler JIT còn tối ưu machine code theo target architecture. **JMM đặt contract ở tầng Java**, còn HotSpot/CPU phải triển khai bằng instructions/barriers/phần cứng phù hợp.

~~~text
Java code + JMM promises
          |
          v
Compiler (interpreter, C1, C2, etc.)
          |
          v
Architecture-specific machine code
          |
          v
CPU caches, store buffers, memory ordering
          |
          v
Observable Java behavior phải phù hợp JMM
~~~

Trên x86-64, một số ordering guarantees của CPU mạnh hơn trên kiến trúc yếu hơn; trên ARM/AArch64 có instructions acquire/release và memory barriers phù hợp. Tuy nhiên **không viết Java code dựa vào thói quen “x86 thường có vẻ đúng”**: JIT và runtime được phép tối ưu theo JMM, và ứng dụng có thể chạy trên hardware/JVM khác.

**`volatile` không đồng nghĩa “mỗi lần phải đưa dữ liệu ra DRAM”**. Cache lines có thể ở cache nhưng được quản lý coherence/ordering đúng; điều cần đo hoặc chứng minh là Java-level HB semantics.

## 19. Chọn công cụ đúng với yêu cầu

| Nhu cầu | Cách phù hợp | Tránh hiểu nhầm |
| --- | --- | --- |
| Một cờ báo hoàn thành/publish một lần | `volatile boolean` hoặc `CountDownLatch` | `volatile` không hứa scheduler wake deadline |
| Một counter atomic đơn giản | `AtomicInteger` / `AtomicLong` | `volatile int++` không atomic |
| Counter thống kê contention cao | `LongAdder` | `sum` không phải snapshot atomic khi updates chạy |
| Bất biến nhiều fields | `synchronized` hoặc `Lock` | Nhiều volatile fields không thành transaction |
| Trao thông điệp giữa threads | `BlockingQueue` / concurrent collection | Plain shared list không đủ an toàn |
| Wait for completion/result | `join()` / `Future.get()` / latch | `sleep()` không thay synchronization |
| Shared immutable snapshot | Immutable record/object + volatile publication | Volatile reference không làm object mutable trở thành immutable |
| Lock-free primitive algorithm | CAS/VarHandle + thiết kế kiểm chứng | CAS một field không atomic nhiều fields |
| Tạm dừng/cancel worker | Interrupt/protocol phù hợp | Plain boolean loop có visibility risk |
| Chỉ thread-local state | Không cần shared lock cho dữ liệu không chia sẻ | Đừng đồng bộ hóa thừa nhưng phải xác nhận không escape |

**Đối với code doanh nghiệp**, bắt đầu từ abstractions cao như executors, queues, structured handoff, immutable values và locks đúng protocol. Chỉ hạ xuống memory modes yếu hơn khi có benchmark và kiểm chứng về correctness.

## 20. Những ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Một source statement tương đương một thao tác atomic.” | `count++` gồm read-modify-write, không atomic tự thân. |
| “Một `volatile int++` là atomic.” | Sai; volatile read/write đơn lẻ không tạo RMW atomic. |
| “Atomicity tự kéo theo ordering của mọi fields khác.” | Không; xét memory effects của operation và HB edges. |
| “Mọi thread luôn đọc giá trị ghi gần nhất theo wall clock.” | JMM xét synchronization/HB, không chỉ thời gian thực. |
| “`volatile` nghĩa không dùng CPU cache.” | JMM quy định observable semantics, không phương thức truy cập DRAM. |
| “`Thread.sleep` giúp flush cache/happens-before.” | Không tạo HB giữa plain shared accesses. |
| “`Thread.yield` sửa visibility.” | Không; chỉ là scheduling hint. |
| “Hai blocks `synchronized` với locks khác nhau đồng bộ được.” | Unlock→lock HB cần đúng **cùng monitor**. |
| “Một method instance synchronized khóa mọi instances.” | Nó khóa `this` instance đang gọi. |
| “`static synchronized` khóa trên instance.” | Khóa trên Class object tương ứng. |
| “Volatile reference khiến object được trỏ tới thread-safe.” | Không; mutable fields cần protocol riêng. |
| “Hai volatile fields luôn là snapshot nhất quán.” | Không; các accesses là riêng lẻ. |
| “`AtomicInteger` tự tạo transaction nhiều biến.” | Không, bảo vệ atomic operations của giá trị đó. |
| “`LongAdder.sum()` atomic khi updates đang chạy.” | Không bảo đảm snapshot atomic dưới concurrent updates. |
| “Một lần chạy không tái hiện race nghĩa code đúng.” | Không; timing/JIT/architecture có thể che bug. |
| “`Thread.join()` chỉ chờ và không liên quan visibility.” | Thành công quan sát termination có HB theo JMM. |
| “Data-race-free nghĩa mọi logic tự động đúng.” | Cần cả invariant và atomic grouping đúng. |
| “`final List` nghĩa list immutable.” | Final reference không làm object được trỏ tới immutable. |
| “`volatile long` có thể bị tearing như plain long.” | Volatile 64-bit read/write atomic theo JLS. |
| “`VarHandle.fullFence` khiến `x++` atomic.” | Fence không thay thế atomic RMW. |
| “Cứ dùng volatile/atomic là không cần xét thứ tự thao tác.” | Vẫn phải thiết kế đúng protocol. |
| “Java Memory Model chỉ là quy tắc cho HotSpot.” | JMM là contract Java language, mọi implementation hợp lệ phải đáp ứng. |

## 21. Câu hỏi tự kiểm tra (có đáp án)

**1.** Atomicity, visibility và ordering khác gì?  
**Đáp án:** Atomicity nói về thao tác được thực hiện như đơn vị không thể bị xen ngang theo hợp đồng; visibility nói về giá trị ghi thread khác được phép nhìn thấy; ordering nói về quan hệ thứ tự quan sát giữa các actions.

**2.** Vì sao `count++` không atomic?  
**Đáp án:** Nó đọc, tính toán rồi ghi; hai threads có thể cùng đọc giá trị cũ và ghi một kết quả, gây lost update.

**3.** `volatile int count; count++;` có đúng cho shared counter không?  
**Đáp án:** Không; dùng atomic RMW như `AtomicInteger.incrementAndGet` hoặc critical section với cùng lock.

**4.** Volatile publication `payload=42; ready=true` yêu cầu reader gì?  
**Đáp án:** `ready` phải volatile và reader phải đọc flag thấy giá trị được publish theo đồng bộ phù hợp trước khi đọc payload, đồng thời không có competing writes phá protocol.

**5.** `sleep()` có bảo đảm thread A thấy writer update không?  
**Đáp án:** Không. Sleep không tạo required HB edge.

**6.** Tại sao `synchronized(lockA)` và `synchronized(lockB)` không đồng bộ nhau?  
**Đáp án:** Chúng bảo vệ các monitors khác nhau, không có unlock(lockA)→lock(lockB) synchronizes-with rule.

**7.** `AtomicityDemo` in gì khi hoàn tất?  
**Đáp án:** `synchronized=200000` và `atomic=200000`, nhờ atomic/synchronized increments và join.

**8.** Tại sao thread main cần `join()` trước khi in?  
**Đáp án:** Đợi completion và có HB từ thread actions tới việc quan sát sau join.

**9.** `VolatileMessage` có thể khiến reader thấy ready=true nhưng payload cũ không?  
**Đáp án:** Không theo protocol bài với một writer, không competing writes: volatile HB publish payload=42.

**10.** Hai volatile fields `x`/`y` có là snapshot atomic không?  
**Đáp án:** Không; dùng lock hoặc immutable object được publish qua một volatile reference.

**11.** Plain `long` read/write luôn portable 64-bit atomic không?  
**Đáp án:** Không được bảo đảm theo JLS `17.7`; volatile long read/write được bảo đảm atomic.

**12.** Một `final int[]` có làm array elements immutable không?  
**Đáp án:** Không, reference không đổi nhưng contents vẫn có thể mutable và racy.

**13.** CAS có hoàn toàn loại ABA problem không?  
**Đáp án:** Không; A→B→A có thể khiến CAS so expected A vẫn thành công.

**14.** Acquire/release và plain VarHandle modes có cùng semantics không?  
**Đáp án:** Không; release/acquire cung cấp ordering mà plain không có.

**15.** Câu “mọi executions của correctly synchronized program có vẻ sequentially consistent” có biến multi-step invariant thành atomic không?  
**Đáp án:** Không; logic multi-step cần critical section/atomic grouping riêng.

## 22. Tài liệu tham khảo chính thức

- [Java Language Specification SE 17 — Chapter 17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): đặc biệt **§17.4** JMM, §17.4.4 synchronization order, §17.4.5 happens-before, §17.5 final-field semantics, §17.7 non-atomic treatment of double/long.
- [Java SE 17 — `java.util.concurrent` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): concurrent utility memory consistency effects.
- [Java SE 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic increment/CAS và memory effects.
- [Java SE 17 — `AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic 64-bit values.
- [Java SE 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): high-contention counters và non-atomic `sum()` under concurrent updates.
- [Java SE 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): blocking handoff và memory consistency effect.
- [Java SE 17 — `Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join`, `interrupt` và `onSpinWait`.
- [Java SE 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): Plain/Opaque/Acquire/Release/Volatile access modes, CAS và fences.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): task execution và memory consistency after `get()`.
- [Java SE 17 — `ReentrantLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): explicit lock với memory synchronization semantics.
- [OpenJDK JSR 133 — Java Memory Model FAQ](https://www.cs.umd.edu/~pugh/java/memoryModel/jsr-133-faq.html): tài liệu nền tảng mang tính giải thích, nên ưu tiên JLS hiện hành khi cần xác định rule chính xác.

**Ghi nhớ:** Khi nhiều threads dùng chung mutable state, **atomicity** quyết định thao tác có bị xen kẽ không, **visibility** quyết định một thread quan sát dữ liệu của thread khác như thế nào, và **ordering** quyết định những giới hạn tái sắp xếp/quan sát thao tác. Java kết nối chúng bằng **happens-before**. `volatile` phù hợp cho publication flags và independent reads/writes có ordering, nhưng **không biến `++` thành atomic**. `synchronized`/`Lock` bảo vệ critical sections và invariants; atomic classes/CAS cung cấp atomic operations; `start`/`join`/latches/queues có memory-consistency effects. Thiết kế protocol đúng và đọc contract API quan trọng hơn phỏng đoán thứ tự CPU thực thi.