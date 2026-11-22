# Quan hệ happens-before qua khóa, volatile, start và join

**Happens-before (HB)** là quan hệ thứ tự được **Java Memory Model (JMM)** định nghĩa để giải thích khi nào những thao tác của một thread phải được quan sát đúng bởi thread khác. Nó đặc biệt quan trọng khi nhiều threads cùng truy cập một trạng thái có thể thay đổi: một thread ghi dữ liệu, thread khác đọc dữ liệu; nếu không có quan hệ đồng bộ cần thiết, chương trình có thể quan sát **giá trị cũ**, thứ tự không như kỳ vọng hoặc kết quả khác nhau giữa những lần chạy.

Bốn cơ chế trọng tâm:

- **Khóa monitor (`synchronized`):** một lần **unlock** trên monitor `m` happens-before mọi lần **lock tiếp theo** trên **cùng monitor** theo synchronization order.
- **`volatile`:** một lần **write** vào biến volatile `v` happens-before các lần **read tiếp theo** của **chính biến `v`** theo synchronization order.
- **`Thread.start()`:** lệnh gọi `start()` trên thread `t` happens-before mọi action trong thread `t` được khởi động.
- **`Thread.join()`:** mọi action của thread `t` happens-before action ở thread khác **phát hiện `t` đã kết thúc**, như khi `join()` hoàn tất thành công do thread đã kết thúc.

Các quy tắc này cộng với **program order** trong từng thread và **tính bắc cầu (transitivity)** tạo thành mạng lưới happens-before. **Happens-before không đồng nghĩa “chạy trước theo đồng hồ”, “tất cả operations tự nguyên tử” hoặc “scheduler sẽ cho thread chạy ngay”.** Nó là hợp đồng về **thứ tự/visibility hợp lệ giữa actions**, không phải lịch thi hành thời gian thực.

Phạm vi bài: Java SE 17+ và Java Memory Model chính thức. Các chi tiết CPU cache, fences, HotSpot/JIT có thể giúp hình dung nhưng **không thay thế luật của JLS**.

## 1. Vì sao cần Java Memory Model?

Ví dụ có hai threads:

```java
// Pseudocode đặt trong cùng một class.
int data = 0;
boolean ready = false;

// Writer thread:
data = 42;
ready = true;

// Reader thread:
if (ready) {
    System.out.println(data);
}
```

Nếu `data` và `ready` là những fields thông thường, có **data race** vì threads truy cập cùng fields, ít nhất một truy cập là write, nhưng thiếu HB ordering giữa những truy cập xung đột. Một lập trình viên chỉ dựa trên thứ tự trong source dễ nghĩ: “Reader thấy `ready == true` thì chắc chắn `data == 42`”. **Kết luận đó không được JMM bảo đảm** cho chương trình racy này.

Điều có thể xảy ra dưới JMM/JIT/runtime:

- Reader chưa thấy `ready` đổi và đi theo nhánh false.
- Reader có thể thấy `ready == true` nhưng vẫn thấy một giá trị `data` không như ý định publish do thiếu đồng bộ.
- Một vòng `while (!ready) {}` không volatile có thể không kết thúc; JIT có thể hoist/cache những reads hợp lệ theo execution thiếu HB.
- Kết quả có thể “đúng hàng triệu lần” trên máy của bạn nhưng vẫn **không an toàn về mặt Java semantics**.

Không nên giải thích đơn giản rằng “CPU luôn chạy đảo đúng hai dòng đó”. JMM cho phép nhiều cách thực thi/quan sát khi thiếu đồng bộ; nguyên nhân có thể liên quan compiler optimizations, memory hierarchy, visibility hoặc reorderings hợp lệ. **Tiêu chuẩn cần kiểm tra là HB**, không chỉ một sơ đồ CPU caches.

### Thuật ngữ nền tảng

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Action** | Một thao tác trong mô hình JMM: read/write, lock/unlock, volatile access, thread actions... |
| **Program order (po)** | Thứ tự actions do một thread thực hiện theo ngữ nghĩa chương trình |
| **Synchronization order (so)** | Thứ tự toàn phần của synchronization actions, nhất quán với program order từng thread |
| **Synchronizes-with (sw)** | Cạnh đồng bộ xuyên threads hoặc giữa những actions được JMM xác định |
| **Happens-before (hb)** | Quan hệ bao gồm program order, synchronizes-with và tính bắc cầu |
| **Data race** | Hai accesses xung đột cùng một biến, ít nhất một write, nhưng không được HB sắp thứ tự |
| **Correctly synchronized program** | Không có data races trong những sequentially consistent executions; JMM bảo đảm tính chất sequential consistency theo định lý liên quan |
| **Safe publication** | Công bố object/state để thread khác nhìn thấy những writes khởi tạo cần thiết theo đúng HB rules |

**Ghi nhớ:** chương trình có data race không nhất thiết crash; nó có thể chạy ra output đúng trong hầu hết thí nghiệm. Điều đó không biến một chương trình không có HB thành chương trình an toàn.

## 2. Quan hệ happens-before được xây dựng thế nào?

Java Language Specification, **JLS `17.4.4–`17.4.5**, định nghĩa các cạnh synchronization và happens-before.

### 2.1. Program order trong cùng thread

Nếu action `A` đứng trước `B` trong program order của một thread thì:

```text
Thread T:
   A  ──program-order──►  B

hb(A, B)
```

Điều này không bắt CPU phải thực hiện mọi machine instruction theo đúng thứ tự trực quan của source. Compiler/CPU có thể reorder khi **bảo toàn ngữ nghĩa theo JMM**. Program order là thành phần của quan hệ HB, không phải bản ghi thời gian từng micro-operation trong hardware.

### 2.2. Synchronizes-with qua hành động đồng bộ

Một số cặp actions được JMM công nhận là có cạnh `synchronizes-with`:

- Monitor **unlock → subsequent lock** của cùng monitor.
- Volatile **write → subsequent read** của cùng volatile variable.
- Thread start action → first action của started thread.
- Final action của thread → action ở thread khác phát hiện thread đã kết thúc (chẳng hạn thông qua `join`/`isAlive`).
- Còn có các trường hợp khác như interrupt detection và default initialization, nhưng bài tập trung bốn cơ chế chính.

Cạnh `synchronizes-with` tạo thành cạnh `happens-before`. Sau đó ghép tiếp với program order và các cạnh HB khác.

### 2.3. Tính bắc cầu

Nếu `hb(A, B)` và `hb(B, C)` thì `hb(A, C)`.

```text
Writer                Synchronization          Reader
data = 42         →   ready = true       →    thấy ready == true
                                                │
                                                ▼
                                             đọc data
```

Sơ đồ này **chỉ có bảo đảm** nếu `ready` được publish/consume qua cơ chế đồng bộ phù hợp, chẳng hạn `volatile` và reader thật sự đọc được giá trị `true` từ một trạng thái đã được publish. Khi đó:

1. `data = 42` program-order trước volatile write.
2. Volatile write synchronizes-with volatile read tiếp theo.
3. Volatile read program-order trước read `data`.
4. Tính bắc cầu đưa write `data` trước read `data` theo HB.

Với **một writer, không có writes cạnh tranh vào `data`**, reader thấy `ready` ở trạng thái đã publish sẽ thấy `data == 42`.

### 2.4. HB là quan hệ thứ tự từng phần

Không phải hai actions của hai threads bất kỳ đều có cạnh HB. Nếu không thể suy ra `hb(A, B)` hoặc `hb(B, A)`, các actions có thể **không được sắp thứ tự bởi HB**. Một kết quả quan sát “A chạy trước B theo log” không tự tạo cạnh HB.

**Chú ý:** `synchronized`, volatile và thread lifecycle là các cơ chế tạo cạnh; `Thread.sleep()` và “hy vọng đã chờ đủ lâu” không tự tạo ra HB.

## 3. Visibility, ordering và atomicity là ba việc khác nhau

| Khía cạnh | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Visibility** | Thread B có thấy giá trị đã được thread A publish hợp lệ không? | Reader thấy `payload == 42` sau volatile flag |
| **Ordering** | Những actions được bảo đảm xuất hiện theo quan hệ cần thiết chưa? | Write payload HB reader read payload |
| **Atomicity** | Operation nhiều bước có được thực hiện như một thao tác nguyên khối đối với threads cạnh tranh không? | `counter++` **không** atomic dù counter volatile |
| **Mutual exclusion** | Có cho phép hai threads vào critical section cùng lúc không? | `synchronized` trên cùng monitor ngăn điều đó |

**Volatile cho visibility/ordering đối với accesses liên quan, không làm một phép read-modify-write (`++`) thành atomic.**

**Monitor lock cung cấp mutual exclusion và HB qua unlock/lock**, nhưng chỉ khi **mọi access cần bảo vệ đều tuân thủ cùng protocol**; một đoạn writer dùng lock còn reader đọc ngoài lock sẽ không tự nhận cùng guarantee.

## 4. Happens-before qua monitor lock (`synchronized`)

`synchronized` dùng **object monitor**. Khi thread vào block synchronized, nó acquire monitor; khi rời block bình thường hoặc do exception, nó release monitor theo JVM semantics.

```java
final class LockedState {
    private final Object monitor = new Object();
    private int value;

    void write(int newValue) {
        synchronized (monitor) {
            value = newValue;
        }
    }

    int read() {
        synchronized (monitor) {
            return value;
        }
    }
}
```

Đây là class Java hợp lệ, chưa có `main`. Nếu thread A hoàn tất `write(42)` trước khi thread B acquire **cùng monitor** để gọi `read()`, thì:

```text
Thread A                          Thread B
lock(m)
value = 42
unlock(m)  ──synchronizes-with──► lock(m)
                                    read value
                                  unlock(m)
```

`unlock(m)` happens-before subsequent `lock(m)`; nhờ program order/transitivity, write tới `value` trước khi unlock xảy ra trước read ở critical section sau. Với không có writer cạnh tranh khác chen giữa, reader sẽ thấy **42**.

### 4.1. Phải là cùng một monitor

Ví dụ **sai**:

```java
void wrong(int newValue) {
    synchronized (new Object()) {
        shared = newValue;
    }
}
```

Đây là method minh họa; `shared` là field trong class giả định. Mỗi lần `new Object()` sinh monitor riêng, **không** có cùng khóa giữa các lần gọi. Writer và reader đồng bộ trên những monitor khác nhau sẽ không tự tạo cặp unlock/lock cần thiết.

Tương tự, một method `synchronized` của instance A dùng monitor `A`, một method `synchronized` của instance B dùng monitor `B`. Hai instances khác nhau **không phải cùng khóa**. `static synchronized` dùng monitor của **Class object**, cũng khác instance monitor trừ khi thiết kế đặc biệt.

### 4.2. Lock không tự bảo vệ field bị đọc ngoài khóa

```java
synchronized (monitor) {
    shared = 42;
}
// Thread khác đọc shared mà không dùng monitor hoặc
// cơ chế đồng bộ hợp lệ khác: thiếu HB cần thiết.
```

Đây là snippet trong class với `monitor` và `shared`. Lock protocol phải được các threads **phối hợp nhất quán**. Không phải cứ một thread dùng `synchronized` thì mọi plain reads của mọi threads khác đều thấy giá trị mới.

### 4.3. `synchronized` hỗ trợ các cập nhật compound

```java
final class SafeCounter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
```

Ở đây `increment()`/`get()` khóa **cùng instance**; two threads không thể đồng thời thực hiện `count++` trên cùng monitor. Vì thế không bị lost updates nếu mọi accesses tuân thủ protocol, và việc đọc `get()` cũng an toàn.

`synchronized` không làm Java code “tuần tự toàn bộ process”; nó chỉ loại trừ những threads cạnh tranh **trên cùng monitor** trong critical sections tương ứng.

### 4.4. Reentrant monitor và exception

Java monitors **reentrant**: thread giữ monitor có thể lock lại monitor đó mà không deadlock chính nó. Monitor tự release khi synchronized block kết thúc vì exception, nhưng **state đã cập nhật một phần không tự rollback**. HB không là cơ chế transaction. Nếu invariants cần cập nhật nhiều fields cùng nhau, thiết kế critical section để reader không quan sát trạng thái giữa chừng.

## 5. Happens-before qua volatile

Một field khai báo `volatile` có các memory-consistency guarantees riêng:

```java
final class Message {
    int number;
    String text;
    volatile boolean ready;
}
```

Một writer:

```java
message.number = 42;
message.text = "OK";
message.ready = true; // volatile write
```

Một reader:

```java
if (message.ready) {  // volatile read
    System.out.println(message.number);
    System.out.println(message.text);
}
```

Các đoạn trên nằm trong methods với biến `message` được truyền/khai báo hợp lệ. Giả sử **một publisher**, reader quan sát `ready == true` và không có concurrent writers sửa `number/text`, thì reader phải quan sát **42 và "OK"**. Lý do không phải vì hai fields đã thành volatile; chúng vẫn là **plain fields**, nhưng được **publish trước volatile write** và **consume sau volatile read**.

### 5.1. Sơ đồ HB cho volatile publication

```text
WRITER THREAD                         READER THREAD

number = 42                            if (ready) {  // volatile read
text = "OK"                                read number
ready = true  // volatile write              read text
                                            }
   │                                       ▲
   └──── volatile synchronizes-with ──────┘

program order + sw + transitivity:
write number/text HB read number/text
```

**Điều kiện:** `ready` phải là **cùng một volatile variable**. Viết `flagA` mà reader đọc `flagB` không tạo cạnh tương ứng chỉ vì cả hai đều volatile.

### 5.2. Đảo thứ tự write có thể làm mất guarantee

**Sai:**

```java
message.ready = true; // công bố quá sớm
message.number = 42;
```

Reader có thể thấy `ready == true` rồi đọc `number` khi writer chưa thực hiện write. Volatile **không đưa một phép ghi ở phía sau nó trong program order quay ngược thời gian** để reader chắc chắn thấy.

**Quy tắc publication:** khởi tạo shared state cần thiết **trước** release action, và consumer đọc release/ready signal **trước** khi đọc các plain fields.

### 5.3. Volatile field không biến object graph thành “volatile mọi nơi”

```java
volatile int[] values = new int[4];
```

Chỉ **reference field `values`** là volatile. `values[0]` không tự trở thành volatile array element. Nếu threads đồng thời update từng phần tử mà không có protocol đồng bộ, vẫn có thể có data race. Thay array reference sau khi khởi tạo bằng volatile write là một cơ chế publication; sửa nội dung array sau khi đã publish cần quy tắc đồng bộ riêng.

### 5.4. Volatile không có mutual exclusion

```java
volatile int counter;

void increment() {
    counter++;
}
```

Đây là snippet trong class. `counter++` gồm logic read → add → write. Hai threads có thể cùng đọc 5, cả hai ghi 6, làm mất một update. Volatile **bảo vệ visibility và các thứ tự theo JMM**, nhưng **không atomically serialize toàn bộ read-modify-write**.

Để đếm an toàn, dùng `synchronized`, `AtomicInteger.incrementAndGet()`, hoặc một cấu trúc phù hợp workload như `LongAdder` khi chỉ cần aggregate counter.

## 6. Happens-before qua `Thread.start()`

`Thread.start()` tạo cạnh HB **từ hành động start tới mọi hành động của thread mới**. Điều quan trọng là các writes **trước** khi gọi start được bảo đảm visibility tới code của child.

```java
final class StartExample {
    static int value;

    public static void main(String[] args) throws InterruptedException {
        value = 17;
        Thread child = new Thread(() -> {
            System.out.println("child sees: " + value);
        });

        child.start();
        child.join();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 StartExample.java
java StartExample
```

**Standard output chính xác:**

```text
child sees: 17
```

Sơ đồ:

```text
MAIN THREAD                  CHILD THREAD

value = 17
child.start()  ────────────► đọc value
                            in 17

main program order + start sw:
write value HB child read
```

**Không cần `value` là volatile trong ví dụ này**, bởi vì publication xảy ra qua **`start()`**. Một thread được khởi động mới không tự có bảo đảm nhìn thấy các plain writes từ main **sau khi** main đã gọi `start()`, trừ khi có cạnh HB khác.

### 6.1. `new Thread(...)` không thay `start()`

Tạo instance `new Thread(...)` và giữ reference trong biến **không** có nghĩa child body đã chạy hoặc đã nhận start edge. Cần thực sự gọi `start()`; gọi `run()` trực tiếp chỉ là một method call bình thường trên thread đang gọi, không khởi động OS/JVM thread mới qua cơ chế Thread.start.

### 6.2. Start là một chiều

```text
MAIN:     x = 1; start(child); x = 2;
CHILD:                       read(x)
```

`x = 1` HB child read nhờ `start`. Nhưng `x = 2` sau start **không tự** HB child read. Nếu cả main và child cùng truy cập plain `x` sau start mà ít nhất một write, có thể có data race. **Không có bảo đảm child thấy 2 hay chỉ thấy 1** nếu thiếu đồng bộ khác.

### 6.3. Đừng nhầm thread object với task submission

`ExecutorService.submit()` có memory-consistency guarantees được document riêng trong `java.util.concurrent`. Không nên diễn giải rằng gọi `run()` trên một `Runnable` tương đương start thread, hay rằng mọi async framework dùng chính cùng cặp `Thread.start/join` trong user code. Với executors/futures, dùng đúng contract của API thay vì đoán scheduler implementation.

## 7. Happens-before qua `Thread.join()`

Khi thread `t` kết thúc và một thread khác **phát hiện việc kết thúc** đó (đặc biệt `join()` hoàn tất thành công), **mọi actions của `t` happen-before** code của thread đã chờ sau điểm phát hiện.

```java
final class JoinExample {
    static int answer;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> answer = 84);
        worker.start();

        worker.join();
        System.out.println("after join: " + answer);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 JoinExample.java
java JoinExample
```

**Standard output chính xác:**

```text
after join: 84
```

Sơ đồ:

```text
WORKER THREAD                 MAIN THREAD

answer = 84
thread terminates
      │                         worker.join() kết thúc
      └── termination detection ───────────► read answer
                                              in 84
```

Không cần `answer` volatile khi **đã chờ thread hoàn tất thành công** và không có writer khác cạnh tranh. `join()` cung cấp cả việc **chờ hoàn thành** (ở dạng không timeout) và **visibility guarantee** cho những writes của worker đã kết thúc.

### 7.1. `join` không làm phép tính của worker atomic khi đang chạy

Nếu hai workers cùng thực hiện `plainCounter++` không có lock/atomic, main gọi `join()` cho cả hai rồi mới đọc, main **thấy được kết quả cuối cùng thực sự đã được viết**, nhưng kết quả đó có thể **thiếu increments** do lost updates. HB từ mỗi worker tới main **không tạo mutual exclusion giữa hai workers**.

### 7.2. `join` có timeout không bảo đảm thread đã chết

```java
worker.join(100); // chờ tối đa khoảng 100 ms
if (!worker.isAlive()) {
    // Đã phát hiện worker kết thúc, có termination HB.
} else {
    // Worker có thể còn chạy; không được đọc plain fields
    // như thể worker chắc chắn đã hoàn tất.
}
```

Đây là snippet trong method; thời lượng chờ thực tế còn chịu scheduler và JVM. **Không được** suy vì `join(100)` return bình thường thì worker đã hoàn thành. Cần xác minh **termination**; gọi `isAlive()` và quan sát `false` phù hợp với quy tắc detection được JLS mô tả.

### 7.3. `InterruptedException` khi chờ

`join()` có thể ném `InterruptedException` khi waiting thread bị interrupt. Khi đó **không được tự coi như worker đã kết thúc**; cần quyết định retry, propagate, cancel hoặc khôi phục interrupt status theo contract ứng dụng. Nếu main bỏ qua exception rồi đọc plain state, không có cơ sở nói `join` đã cung cấp edge termination mà chương trình định dựa vào.

### 7.4. Join là một chiều ngược lại Start

- `start`: những actions **trước start ở starter** được publish tới **started thread**.
- `join`: những actions **trong child trước termination** được publish tới **joiner sau successful detection**.

Kết hợp hai quy tắc, có thể tạo chuỗi HB hai chiều cho một lần trao đổi dữ liệu, nhưng chúng không tạo live, bidirectional communication xuyên suốt vòng đời thread.

## 8. Ví dụ tổng hợp Java 17+: khóa, volatile, start và join

Tạo file duy nhất **`HappensBeforeDemo.java`**:

```java
public class HappensBeforeDemo {
    static final class Box {
        int value;
        String text;
    }

    static final class Publication {
        int payload;
        int checksum;
        int observed;
        volatile boolean ready;
    }

    static final class Counter {
        private final Object monitor = new Object();
        private int value;

        void increment() {
            synchronized (monitor) {
                value++;
            }
        }

        int get() {
            synchronized (monitor) {
                return value;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        // 1) Actions trước start HB actions ở started thread.
        Box fromMain = new Box();
        fromMain.value = 11;
        fromMain.text = "prepared";

        Thread starter = new Thread(() -> {
            if (fromMain.value != 11
                    || !"prepared".equals(fromMain.text)) {
                throw new AssertionError("start visibility");
            }
        });
        starter.start();
        starter.join();
        System.out.println("start: " + fromMain.value
                + " / " + fromMain.text);

        // 2) Actions của worker HB code sau join thành công.
        Box fromWorker = new Box();
        Thread producer = new Thread(() -> {
            fromWorker.value = 22;
            fromWorker.text = "finished";
        });
        producer.start();
        producer.join();
        System.out.println("join: " + fromWorker.value
                + " / " + fromWorker.text);

        // 3) Volatile flag publish hai plain fields.
        Publication publication = new Publication();

        Thread observer = new Thread(() -> {
            while (!publication.ready) {
                Thread.onSpinWait();
            }
            publication.observed =
                    publication.payload + publication.checksum;
        });
        Thread publisher = new Thread(() -> {
            publication.payload = 30;
            publication.checksum = 12;
            publication.ready = true;
        });

        observer.start();
        publisher.start();
        publisher.join();
        observer.join();
        System.out.println("volatile: " + publication.observed);

        // 4) Cùng monitor làm read-modify-write atomic
        // đối với hai writers phối hợp qua khóa.
        Counter counter = new Counter();
        Runnable incrementTask = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(incrementTask);
        Thread second = new Thread(incrementTask);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("lock count: " + counter.get());
        System.out.println("done");
    }
}
```

### Biên dịch/chạy

```bash
javac -encoding UTF-8 HappensBeforeDemo.java
java HappensBeforeDemo
```

**Standard output của chương trình khi các threads được scheduler cho chạy và hoàn tất bình thường:**

```text
start: 11 / prepared
join: 22 / finished
volatile: 42
lock count: 20000
done
```

**Lưu ý tiến độ:** như mọi ví dụ concurrency, Java không đưa ra cam kết fairness của OS scheduler hay deadline để một thread luôn được chạy trong X milliseconds. Vòng đợi volatile này mang tính giảng giải, không phải mẫu thiết kế production (xem mục 14). Khi các threads tiến hành và kết thúc bình thường, kết quả **không phụ thuộc thứ tự interleaving hợp lệ**.

### Giải thích tại sao output ổn định

1. Main đặt `fromMain.value=11` và `text="prepared"` **trước** `starter.start()`. Start HB lần đọc của child; child xác nhận giá trị đã publish. Main join trước khi in nên việc validate không còn đang chạy.
2. Worker ghi `fromWorker.value=22` và `text="finished"` rồi kết thúc. Main gọi `join()` hoàn tất trước khi đọc hai fields. Không cần volatile trong trường hợp này.
3. Publisher ghi **30** và **12** trước volatile write `ready=true`. Observer chờ tới khi một volatile read thấy `true`, rồi đọc hai plain fields. HB thông qua volatile bảo đảm tổng **42**, vì không có writer khác. Main `join()` observer để đọc `observed` sau khi observer kết thúc.
4. Hai writers cùng dùng `counter.increment()` khóa **cùng monitor**. Mỗi increment read-modify-write không thể interleave bên trong critical section, nên **20.000 increments** không bị mất. `join()` chỉ bảo đảm main đợi đủ hai writers; **lock** mới ngăn lost updates.
5. Mỗi phần được chạy lần lượt trong `main`, nên thứ tự các dòng println cũng ổn định.

### Một chi tiết dễ hiểu nhầm trong ví dụ

Ở phần volatile, main cũng gọi `join()`, và `join` có HB riêng tới main. **Điều chứng minh volatile publication nằm ở reader thread**, nơi observer chờ `ready` rồi đọc `payload/checksum`. Nếu bỏ volatile và chỉ dựa vào main join ở cuối, main vẫn có thể thấy writes của publisher sau join, **nhưng observer đọc payload trước đó không có cạnh đồng bộ cần thiết**. Đây là hai thời điểm/cặp reads khác nhau.

Trong production, thay busy-wait bằng `CountDownLatch`, `BlockingQueue`, `Future` hoặc cơ chế notification phù hợp khi không cần low-level spin.

## 9. Tại sao `volatile++` vẫn sai: minh họa lost update

```java
final class BrokenCounter {
    volatile int value;

    void increment() {
        value++;
    }
}
```

Nếu hai threads thực hiện `increment()` đồng thời:

```text
Ban đầu: value=5

Thread A           Thread B
read value=5       read value=5
add 1 → 6          add 1 → 6
write value=6      write value=6

Kỳ vọng hai increments: 7
Kết quả có thể: 6
```

Volatile read/write riêng lẻ có memory-consistency guarantees, nhưng không tạo một **atomic transaction** bao trùm cả ba bước. Một volatile write của A có thể được thứ tự cùng các volatile operations khác mà vẫn không bảo đảm `value++` của A và B tách biệt hoàn toàn.

### Cách 1: synchronized trên cùng monitor

```java
final class SynchronizedCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int get() {
        return value;
    }
}
```

### Cách 2: AtomicInteger

```java
final class AtomicCounter {
    private final java.util.concurrent.atomic.AtomicInteger value =
            new java.util.concurrent.atomic.AtomicInteger();

    void increment() {
        value.incrementAndGet();
    }

    int get() {
        return value.get();
    }
}
```

`AtomicInteger.incrementAndGet()` dùng atomic read-modify-write theo contract API, với memory effects được định nghĩa. Đây là cách phù hợp cho concurrent counter không cần ràng buộc phức tạp giữa nhiều fields. Với thống kê tổng hợp chịu contention rất cao, `LongAdder` có thể là lựa chọn khác nhưng không phải phép thay thế tuyệt đối nếu cần đọc nhất quán mỗi thời điểm.

## 10. Không có HB giữa hai plain fields nếu chỉ “chờ lâu”

Ví dụ:

```java
final class UnsafeFlag {
    int result;
    boolean done;

    void produce() {
        result = 42;
        done = true;
    }

    int consume() {
        while (!done) {
            Thread.onSpinWait();
        }
        return result;
    }
}
```

Đây là class hợp lệ nhưng **thiếu đồng bộ**, không nên chạy như test yêu cầu chắc chắn kết thúc. `Thread.onSpinWait()` là **performance hint cho JVM/CPU**, không tạo happens-before và không làm `done` volatile.

Tương tự:

```java
Thread.sleep(100);
```

**Không phải memory synchronization primitive.** Lời gọi sleep có thể giúp thread khác được CPU chạy, nhưng JMM không định nghĩa “Thread.sleep(100) happens-before đọc plain field từ thread khác” chỉ vì đủ milliseconds.

### Println có thể che bug

`System.out.println()` trên những implementation thông dụng có synchronized I/O internals. Nếu bạn chèn println giữa hai accesses, nó có thể **thay timing hoặc tạo thêm synchronization ngoài ý định**; bug dễ biến mất khi thêm log.

Điều đúng: không dùng output có log như bằng chứng chương trình đã có HB an toàn. Hãy phân tích **protocol mà code thực sự dựa vào**, không các khóa vô tình của diagnostic library.

## 11. Sửa data-race flag đúng cách

### Cách A: volatile flag

```java
final class VolatileFlag {
    int result;
    volatile boolean done;

    void produce() {
        result = 42;
        done = true;
    }

    int consume() {
        while (!done) {
            Thread.onSpinWait();
        }
        return result;
    }
}
```

Với **một writer**, nếu reader nhận ra `done == true` và không có concurrent writes khác vào `result`, volatile HB làm `consume()` trả **42**. Nhưng vòng chờ tiêu thụ CPU, thiếu liveness guarantee về scheduling và không xử lý cancellation/timeouts; đây vẫn **không phải mô hình production mặc định**.

### Cách B: monitor condition

```java
final class MonitorFlag {
    private int result;
    private boolean done;

    synchronized void produce() {
        result = 42;
        done = true;
        notifyAll();
    }

    synchronized int consume() throws InterruptedException {
        while (!done) {
            wait();
        }
        return result;
    }
}
```

`wait()` phải được gọi khi thread giữ đúng monitor; nó release monitor trong thời gian chờ và phải reacquire trước khi return. `notifyAll()` không tự nhường khóa ngay lập tức: producer phải exit synchronized method/monitor, consumer mới có thể reacquire.

**Luôn dùng `while` để kiểm tra lại điều kiện**, do spurious wakeups và sự thay đổi state bởi threads khác. Cặp monitor unlock/lock cũng tạo HB cần thiết.

### Cách C: CountDownLatch

```java
import java.util.concurrent.CountDownLatch;

final class LatchFlag {
    private int result;
    private final CountDownLatch ready = new CountDownLatch(1);

    void produce() {
        result = 42;
        ready.countDown();
    }

    int consume() throws InterruptedException {
        ready.await();
        return result;
    }
}
```

Đây là một class runnable về mặt cú pháp nhưng không có `main`; nó dùng concurrency API cấp cao. Theo API, các actions trước `countDown()` happens-before actions sau một `await()` thành công tương ứng, nên `result` được publish an toàn.

**Không lẫn các cơ chế:** latch có memory-consistency effects riêng; không cần thêm volatile cho `result` chỉ vì nó được một thread khác đọc sau successful await (với điều kiện không có writes cạnh tranh khác).

## 12. Happens-before không có nghĩa “mọi plain read luôn thấy lần write cuối cùng theo đồng hồ”

JMM dùng quan hệ HB và những quy tắc hợp lệ để xác định reads có thể nhìn thấy writes nào. Với nhiều writers:

```java
int data; // shared

// Thread A:
data = 1;

// Thread B:
data = 2;

// Thread C:
int observed = data;
```

Đây là ví dụ khái niệm, không có synchronization mô tả giữa A, B, C. Không thể dùng wall-clock timestamp, việc một logger in trước hay giả định CPU chạy theo thứ tự để đưa ra kết quả portable của `observed`.

Ngay cả khi C có HB từ A, nếu B ghi `data` mà không được ordered hợp lệ với C, chương trình vẫn có conflict/data race khác có thể làm giá trị đọc không được quyết định bởi “A vừa publish 1”. **Cần xét mọi writes xung đột**, không chỉ một cạnh mong muốn.

### Cách suy luận một protocol đúng

1. Xác định **mọi shared variables**.
2. Xác định **mọi writes** vào chúng và thread nào có thể ghi.
3. Xác định action **publication/release**.
4. Xác định action **observation/acquire** thật sự xảy ra.
5. Nối program order + synchronizes-with thành HB path.
6. Kiểm tra có **competing unordered writes** nào phá tính quyết định không.
7. Kiểm tra atomicity nếu code đọc/sửa nhiều fields.
8. Kiểm tra thread có thật sự hoàn tất/chạy theo điều kiện liveness không.

## 13. Happens-before và memory reordering

Ví dụ kinh điển:

```java
int x = 0;
int y = 0;
int r1;
int r2;

// Thread A:
x = 1;
r1 = y;

// Thread B:
y = 1;
r2 = x;
```

Đây là pseudocode các actions trong class hai threads, **không phải chương trình runnable độc lập**. Khi hai threads thực thi không có HB liên kết hai accesses, **kết quả `r1 == 0 && r2 == 0` được JMM cho phép** trong bài toán store buffering điển hình. Điều đó không có nghĩa lần chạy nào cũng sẽ trả 0/0.

### Vì sao kết quả 0/0 không nhất thiết “CPU sai”?

Không có cross-thread HB bắt buộc Thread A phải thấy write của B trước read `y`, cũng không có cross-thread HB buộc B thấy write của A trước read `x`. JMM bảo vệ ngữ nghĩa intra-thread và các điều kiện hợp lệ, nhưng một data-racy execution không tự có sequential consistency.

**Sửa đúng** phụ thuộc yêu cầu logic:

- Nếu mỗi thread cần thấy một event từ thread kia, dùng volatile flags hoặc synchronization protocol.
- Nếu thao tác trao đổi trạng thái cần atomic, dùng lock hoặc atomic class hợp lệ.
- Nếu chỉ cần thu kết quả sau khi cả hai hoàn tất, caller `join()` hai threads và đọc lúc đó; nhưng join không làm các reads trong quá trình họ chạy vốn thiếu HB trở nên safe.

### Volatile làm khác bài toán

Đổi `x` và `y` thành volatile fields sẽ thêm synchronization order/visibility constraints. Với **cả hai biến volatile**, case 0/0 của pattern store-buffering trên không còn phù hợp với thứ tự volatile toàn phần nhất quán theo program order; nhưng còn các interleavings hợp lệ khác, và không nên dùng logic đó để suy một transaction atomic giữa nhiều fields.

## 14. Thread lifecycle và các bẫy tiến độ thực thi

HB nói **nếu một event quan sát hợp lệ xảy ra** thì thứ tự/visibility được bảo đảm. Nó **không cam kết** event sẽ xuất hiện trong 100 ms hay mọi thread được scheduler chạy công bằng.

### 14.1. Busy-wait có vấn đề gì?

```java
while (!ready) {
    Thread.onSpinWait();
}
```

Nếu `ready` volatile, vòng lặp có semantics visibility phù hợp khi writer publish. Nhưng nó có thể:

- Tiêu thụ CPU nếu chờ lâu.
- Không có timeout/cancellation.
- Chạy vô hạn nếu writer không bao giờ publish do lỗi logic.
- Bị chậm do CPU quota/OS scheduling.
- Không phù hợp cho hầu hết I/O-bound services.

Thường ưu tiên `CountDownLatch`, `BlockingQueue`, `Condition`, `CompletableFuture` hoặc blocking primitive phù hợp.

### 14.2. `join(timeout)` vs `join()`

`join()` không timeout sẽ chờ thread kết thúc trừ khi bị interrupt hoặc có lỗi hợp lệ khác. `join(timeout)` **có thể** trả về khi hết thời gian; cần kiểm tra termination trước khi dựa vào edge completion.

Ví dụ:

```java
worker.join(200);
if (worker.isAlive()) {
    // Timeout hoặc worker chưa kết thúc:
    // chưa được coi là đã nhận final state qua join.
} else {
    // Đã phát hiện worker terminated.
}
```

### 14.3. InterruptedException không đồng nghĩa child terminated

Thread gọi `join` hoặc `wait` có thể bị interrupt. Exception signaling có HB semantics riêng liên quan interrupt detection, nhưng **không** làm worker tự động kết thúc. Đừng nuốt exception rồi đọc plain fields như thể đã có successful join.

### 14.4. Deadlock dù có `synchronized`

`synchronized` tạo mutual exclusion và HB edges; nó **không bảo đảm** hệ thống tránh deadlocks:

```text
Thread A giữ lock1, chờ lock2.
Thread B giữ lock2, chờ lock1.
```

Đó là vòng chờ khóa. Quy tắc HB chỉ nói về thứ tự những actions đã có/có thể xảy ra; không tạo progress khi các threads đang deadlock.

## 15. Safe publication của object: không chỉ boolean flag

Một object có nhiều fields cần khởi tạo an toàn trước khi thread khác sử dụng:

```java
final class Config {
    final String host;
    final int port;

    Config(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
```

**Final fields** có initialization safety rules riêng trong JMM nếu object được xây dựng đúng (không cho `this` escape trong constructor), nhưng không nên viện dẫn final fields để biện hộ một protocol truy cập mutable shared state không có đồng bộ.

### Public reference qua volatile

```java
final class Holder {
    private Config config; // plain field

    private volatile boolean ready;

    void publish() {
        config = new Config("localhost", 8080);
        ready = true;
    }

    Config await() {
        while (!ready) {
            Thread.onSpinWait();
        }
        return config;
    }
}
```

Đây là class ví dụ, có thể biên dịch nhưng không có `main`. Sau volatile read thấy `true`, reader có HB từ những actions trước volatile write, nên `config` đã được publish trước đó được nhìn thấy hợp lệ. Không nên biến ví dụ spin-wait này thành thư viện production; dùng primitive cấp cao nếu muốn blocking/cancellation.

### Volatile reference đơn giản hơn flag riêng

```java
final class VolatileConfig {
    private volatile Config config;

    void publish(Config next) {
        config = next;
    }

    Config snapshot() {
        return config;
    }
}
```

Với construction hoàn tất trước volatile write, một reader nhận được non-null `config` qua volatile read có **safe-publication** của state được chuẩn bị trước publish. Tuy nhiên, những **mutable fields được sửa tiếp sau khi publish** vẫn cần đồng bộ riêng.

### Escape khỏi constructor là vấn đề khác

Nếu một constructor publish `this` trước khi khởi tạo hoàn chỉnh, thread khác có thể quan sát object dở dang; **final-field semantics cũng có hạn chế trong tình huống this escape**. Đừng giải quyết bằng việc chỉ thêm `final` mọi nơi mà vẫn publish object quá sớm.

## 16. Double-checked locking và volatile

Mẫu lazy singleton truyền thống:

```java
final class LazyService {
    private static volatile LazyService instance;

    private LazyService() {
    }

    static LazyService get() {
        LazyService local = instance;
        if (local == null) {
            synchronized (LazyService.class) {
                local = instance;
                if (local == null) {
                    local = new LazyService();
                    instance = local;
                }
            }
        }
        return local;
    }
}
```

**Đây là class hợp lệ theo Java 17.** Trong mẫu double-checked locking này, volatile reference đóng vai trò **safe publication** ở fast path không khóa.

Vì sao cần `volatile`?

- Constructor hoàn tất trước volatile write `instance = local` theo program order liên quan.
- Reader đọc non-null `instance` qua volatile read có HB tới những writes đã publish.
- Lock trong slow path bảo vệ tránh nhiều threads cùng tạo instance một cách không kiểm soát.
- Đọc lần đầu vào biến local làm logic rõ, chỉ dùng instance đã đọc được; second check dưới lock ngăn duplicate construction.

**Không có nghĩa** mọi singleton cần DCL: **initialization-on-demand holder idiom** hoặc static initialization thường đơn giản hơn. Và nếu `LazyService` có mutable fields được threads cập nhật sau construction, singleton publication không tự giải quyết races trên các fields ấy.

## 17. ReentrantLock và concurrency utilities tạo memory-consistency edges

Nhiều API trong `java.util.concurrent` cung cấp effects tương tự hoặc xây trên JMM:

| API | Contract memory consistency ở mức khái quát |
| --- | --- |
| `ReentrantLock` / `Lock` | Successful `lock/unlock` có memory synchronization semantics như monitor lock/unlock phù hợp |
| `CountDownLatch` | Actions trước `countDown()` HB actions sau `await()` thành công tương ứng |
| `Future.get()` | Actions thực hiện bởi asynchronous computation HB actions sau successful `get()` phù hợp |
| `ExecutorService` | Actions trước submit task HB actions trong task; task actions HB sau `Future.get` |
| `BlockingQueue` | Actions trước đặt object vào queue HB actions sau khi consumer lấy object tương ứng |
| `ConcurrentHashMap` | Các API có memory effects được document; visibility cho những access patterns cụ thể |
| Atomic classes | Atomic operations và memory effects theo contract (`get`/`set`/CAS...) |

**Luôn đọc contract cụ thể của API**, vì có các method thất bại/timeout/cancel và những access modes yếu hơn như `lazySet`, `getAcquire`, `setRelease`, `getOpaque` trong `VarHandle`/`Atomic*` APIs. Không có câu “tất cả method trên concurrent classes tạo một global happens-before”.

### Lock API so với synchronized

```java
import java.util.concurrent.locks.ReentrantLock;

final class LockCounter {
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

    int snapshot() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
```

Đây là class không có `main` nhưng có thể biên dịch. `try/finally` quan trọng để luôn unlock. Giao thức đúng đòi cả writes/reads truy cập `value` phối hợp cùng một lock; `ReentrantLock` cho thêm khả năng như `tryLock`/`lockInterruptibly` nhưng không “tự tốt hơn” `synchronized` về mọi mặt.

## 18. `wait/notifyAll` không chỉ là “gửi thông báo”

Nhiều người học viết:

```java
synchronized (monitor) {
    monitor.notifyAll();
}
```

và tưởng thread chờ ngay lập tức chạy tiếp. Thực tế:

1. Thread gọi `wait()` phải sở hữu monitor.
2. `wait()` release monitor và chờ theo luật JMM/`Object.wait`.
3. Thread gọi `notify/notifyAll` cũng phải sở hữu monitor.
4. Notification làm một hoặc nhiều waiters **đủ điều kiện thức dậy**, nhưng họ cần **reacquire monitor**.
5. Producer có thể vẫn đang giữ monitor sau notify cho tới khi thoát synchronized block.
6. Waiter phải kiểm tra lại condition trong **vòng `while`**, vì spurious wakeup hoặc state thay đổi.

**Không dựa vào notify mà thiếu condition variable/state**. Notification có thể được gửi trước khi thread bắt đầu wait, dẫn đến mất tín hiệu nếu protocol không giữ state đúng. Với một flag đọc/ghi dưới cùng monitor, cặp unlock/lock và condition loop làm giao thức vững hơn.

## 19. Rủi ro race vẫn còn nếu đồng bộ sai phạm vi

### 19.1. Hai khóa khác nhau

```java
final Object lockA = new Object();
final Object lockB = new Object();
int state;

// Writer:
synchronized (lockA) {
    state = 123;
}

// Reader:
synchronized (lockB) {
    System.out.println(state);
}
```

Đây là snippet minh họa trong class. `unlock(lockA)` **không** synchronizes-with `lock(lockB)` chỉ vì cả hai đều là monitors. Nếu không có HB khác, accesses `state` có thể racy.

### 19.2. Một field volatile, nhiều fields cần invariant

```java
volatile int left;
volatile int right;
```

Nếu writer cập nhật hai fields và reader cần thấy chúng như **một cặp nguyên tử**, volatile **không đủ**. Reader có thể quan sát pair gồm một write mới và một write cũ tại một thời điểm interleaving hợp lệ. Dùng monitor hoặc publish **immutable snapshot** qua một volatile reference khi cần giữ invariant nhiều fields.

### 19.3. CAS bảo vệ một địa điểm, không tự làm toàn object graph atomic

`AtomicReference.compareAndSet(expected, update)` có tính nguyên tử cho reference update theo API, nhưng không biến những writes bất đồng bộ tới fields của object đang được tham chiếu thành một transaction. Thiết kế concurrent state nên phân biệt **atomic publication of reference** với **atomic mutation of contents**.

### 19.4. Locking quanh writer nhưng reader không theo protocol

Writer có thể khóa đúng; reader đọc field trực tiếp mà không khóa và không volatile, vẫn thiếu guarantee dự kiến. Phải vẽ đủ **release-to-acquire chain cho read được hỏi**, không chỉ đánh dấu một chỗ có keyword `synchronized`.

## 20. Một công thức suy luận HB rõ ràng

Khi nhận một đoạn Java concurrency, đừng đoán theo thời gian. Hãy tạo bảng actions:

| Thread | Action | Loại |
| --- | --- | --- |
| T1 | `x = 7` | Plain write |
| T1 | `ready = true` | Volatile write |
| T2 | `if (ready)` | Volatile read |
| T2 | `r = x` | Plain read |

Giả sử T2 thật sự thấy `ready == true` do publication từ T1 (và không có writer khác làm nhiễu):

```text
T1: write x = 7
       │ program order
       ▼
T1: volatile write ready = true
       │ synchronizes-with
       ▼
T2: volatile read ready == true
       │ program order
       ▼
T2: plain read x

Kết luận: hb(write x, read x).
Nếu không có conflicting write khác: r == 7.
```

### Checklist suy luận từng bước

1. Liệt kê **đối tượng và các biến** shared.
2. Xác định **thread nào ghi**, **thread nào đọc**, thời điểm logic.
3. Tìm cạnh **program order** ở từng thread.
4. Tìm cạnh **synchronizes-with**: cùng monitor, cùng volatile variable, `start`, termination detection.
5. Ghép cạnh theo **transitivity**.
6. Kiểm tra **mọi conflicting accesses**: còn một unordered writer nào không?
7. Xác định thứ đang bảo đảm: **visibility**, **ordering**, **atomicity** hay **progress**?
8. Với vòng chờ, kiểm tra **liveness**, interrupt, timeout, cancellation.
9. Không diễn giải kết quả logging hoặc `sleep` thành cạnh JMM không tồn tại.
10. Nếu kết quả phức tạp, dùng stress testing và đối chiếu JLS chính thức.

## 21. JCStress và testing: điều gì có thể kiểm tra được?

**JCStress** là concurrency testing harness của OpenJDK chuyên thử các outcomes của concurrent actors; nó hữu ích khi học JMM litmus tests hoặc tìm race conditions rất nhỏ. Tuy nhiên:

- Một outcome không xuất hiện sau hàng triệu iterations **không chứng minh** JMM cấm nó.
- Một outcome xuất hiện có thể là tín hiệu bug về synchronization/protocol, phải kiểm tra định nghĩa test.
- VM flags, JIT warm-up, OS/CPU/architecture và test structure có thể thay tập outcomes quan sát.
- Không viết unit test phụ thuộc “data race chắc chắn làm sai sau N lần”.
- Không thêm println hay sleep vào critical path rồi coi như vẫn đang đo cùng litmus test.

**Thí nghiệm sai phổ biến:** assert một plain-field spinning loop phải thoát trong 100 ms. Việc nó thoát một lần có thể do timing hoặc compiled code chưa tối ưu, không tạo portability guarantee.

### ThreadSanitizer, profilers và runtime tools

Các công cụ diagnostic/profiler có thể giúp tìm contention, thread states hoặc dữ liệu race tùy JDK/build. Nhưng **JFR, `jstack`, `jcmd Thread.print`** chủ yếu cung cấp góc nhìn runtime, **không thay phân tích JMM**. Race detection support và false positives/negatives phụ thuộc tool; dùng đúng công cụ được hỗ trợ trên environment đang chạy.

## 22. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật |
| --- | --- |
| “Happens-before nghĩa là action A chạy sớm hơn theo đồng hồ.” | Là quan hệ JMM về ordering/visibility, không phải timeline vật lý |
| “Hai actions thuộc hai threads bất kỳ luôn được HB xếp thứ tự.” | HB là partial order; có thể không có cạnh |
| “`Thread.sleep` đủ để publish plain fields.” | Sleep không tạo HB edge |
| “`Thread.onSpinWait` làm field thành volatile.” | Chỉ là hint, không thêm JMM synchronization |
| “`volatile` làm `counter++` atomic.” | Read-modify-write vẫn có thể lost updates |
| “Volatile flag publish chỉ bản thân flag.” | Những writes trước release có thể được publish qua transitivity |
| “Đặt volatile vào array reference khiến mọi phần tử volatile.” | Không; elements cần protocol riêng |
| “Write vào một volatile var HB read của mọi volatile var.” | Quy tắc sw cần **cùng volatile variable** |
| “`synchronized(lockA)` đồng bộ với `synchronized(lockB)`.” | Khác monitor không tạo unlock/lock edge tương ứng |
| “Chỉ writer dùng synchronized cũng đủ.” | Reader phải theo protocol hoặc có HB hợp lệ khác |
| “`start()` publish mọi writes của starter kể cả sau start.” | Start edge bảo đảm writes trước start; sau start cần cơ chế riêng |
| “`new Thread` đồng nghĩa thread đã chạy.” | Phải gọi `start()` |
| “Gọi `run()` trực tiếp tạo thread mới.” | Không, chỉ là method call thông thường |
| “`join(timeout)` return nghĩa child đã chết.” | Có thể timeout; cần phát hiện termination |
| “`join` bảo vệ hai workers khỏi lost increments.” | Join chỉ ordering với joiner sau completion; không serialize workers |
| “Reader thấy `ready=true` dù ready plain thì chắc chắn thấy payload mới.” | Thiếu HB, không portable |
| “`notifyAll` lập tức chuyển quyền monitor cho reader.” | Waiter cần reacquire monitor sau unlock của notifier |
| “`volatile` bảo vệ invariant nhiều fields.” | Không như một transaction; dùng lock/immutable snapshot |
| “Final field đồng nghĩa object luôn published an toàn trong mọi construction.” | Có rules riêng và giới hạn khi `this` escape |
| “Đã thấy đúng output trên x86 là race-free.” | Outcome thường gặp không chứng minh JMM guarantee |
| “HB có thể sửa một chương trình sai về liveness/fairness.” | Ordering không bảo đảm scheduler tiến triển |
| “Có GC/JIT logs giúp suy ra tất cả HB edges.” | Logs không định nghĩa program synchronization protocol |

## 23. Bài tập có đáp án

**Bài 1.** Thread A viết `data=42`, rồi `ready=true` (volatile). Thread B đọc `ready==true` rồi đọc `data`. Một writer, không update khác. B thấy gì?  
**Đáp án:** `42`, vì program order + volatile synchronizes-with + transitivity tạo HB.

**Bài 2.** Writer viết `ready=true` trước rồi mới `data=42`. Reader thấy `ready==true`. Có chắc `data==42`?  
**Đáp án:** Không. Write payload nằm sau volatile publication.

**Bài 3.** Writer dùng `synchronized(lockA)`, reader dùng `synchronized(lockB)`. Có HB unlock/lock không?  
**Đáp án:** Không nếu hai monitors khác và không có cạnh đồng bộ khác.

**Bài 4.** Hai threads cùng `volatileCounter++` 1000 lần, main join cả hai. Kết quả luôn 2000?  
**Đáp án:** Không. Lost updates có thể xảy ra; `join` chỉ chờ và publish kết quả thực tế, không làm increments atomic.

**Bài 5.** `AtomicInteger.incrementAndGet()` có giúp không?  
**Đáp án:** Có, nó cung cấp atomic increment theo contract Java concurrency API.

**Bài 6.** Main ghi `x=5` rồi `child.start()`; child in `x`. Có cần x volatile khi không có writer cạnh tranh?  
**Đáp án:** Không, start HB child actions.

**Bài 7.** Main ghi `x=5` **sau** `child.start()`; child đọc plain `x`. `start` tự publish write này?  
**Đáp án:** Không. Write sau start thiếu edge start HB; cần đồng bộ phù hợp.

**Bài 8.** Worker ghi `result=10`; main gọi `worker.join()` hoàn tất rồi đọc. Có cần result volatile nếu không writer khác?  
**Đáp án:** Không, actions của terminated thread HB code sau successful join.

**Bài 9.** `join(100)` return mà `worker.isAlive()==true`; main có thể coi worker đã publish kết quả cuối cùng?  
**Đáp án:** Không. Worker chưa được phát hiện kết thúc.

**Bài 10.** `join()` ném `InterruptedException`. Có thể bỏ qua và đọc state như đã join thành công?  
**Đáp án:** Không. Chưa có successful termination detection theo logic đang dựa vào.

**Bài 11.** Một thread gọi `run()` trực tiếp trên Thread object. Nó nhận start HB edge?  
**Đáp án:** Không có new-thread start event; đó là lời gọi method thông thường.

**Bài 12.** Field `volatile int[] arr` làm `arr[0]++` atomic?  
**Đáp án:** Không. Volatile áp dụng reference field, không tự áp dụng array elements hoặc composite update.

**Bài 13.** `wait()` có thể return mà condition vẫn false?  
**Đáp án:** Có, vì spurious wakeups hoặc state thay đổi; dùng `while (!condition) wait()`.

**Bài 14.** `notifyAll()` làm waiter chạy ngay lập tức trước khi notifier unlock?  
**Đáp án:** Không. Waiter còn cần reacquire monitor và scheduler tiến hành.

**Bài 15.** Mỗi lần chạy data race test đều in đúng. Có chứng minh đúng JMM?  
**Đáp án:** Không. Cần phân tích HB hoặc kiểm thử stress chỉ để tìm lỗi, không để chứng minh absence of errors.

**Bài 16.** `volatile` cung cấp mutual exclusion như `synchronized`?  
**Đáp án:** Không. Nó có ordering/visibility semantics, không khóa critical section.

**Bài 17.** Cùng monitor bảo vệ writer/reader nhưng reader đọc ngoài lock trong một đường khác. Đường đó an toàn tự động?  
**Đáp án:** Không; cần xét HB với read thực tế.

**Bài 18.** Một object immutable gồm final fields được publish qua volatile reference. Có thể đọc state đã construct sau acquire read?  
**Đáp án:** Có với construction và publication hợp lệ; mutable fields cập nhật sau đó vẫn cần protocol riêng.

**Bài 19.** DCL singleton không có volatile có an toàn theo mô hình Java 17?  
**Đáp án:** Mẫu double-checked locking cổ điển không volatile là không an toàn về publication; dùng volatile hoặc phương án class initialization.

**Bài 20.** Trong `HappensBeforeDemo`, dòng `volatile:` in gì?  
**Đáp án:** `volatile: 42` nếu các threads hoàn tất bình thường; volatile ready đọc true publish 30 và 12.

**Bài 21.** Trong `HappensBeforeDemo`, dòng `lock count:` in gì?  
**Đáp án:** `lock count: 20000` do hai writers mỗi người tăng 10.000 lần dưới cùng monitor.

**Bài 22.** Thread A và B ghi plain `x=1`/`x=2` song song, C đọc không synchronization. Có thể dùng “write nào chạy cuối theo log” để kết luận C thấy gì?  
**Đáp án:** Không; không có cross-thread HB đủ rõ, logging có thể thay timing/protocol.

**Bài 23.** Writer ghi data rồi `CountDownLatch.countDown()`; reader `await()` thành công rồi đọc data. Có HB?  
**Đáp án:** Có, theo memory-consistency contract của CountDownLatch.

**Bài 24.** `Future.get()` trả kết quả task, có phải cần đọc thêm plain ready flag để đảm bảo thấy writes từ task không?  
**Đáp án:** Thường không; Future API có memory-consistency guarantee cho actions của asynchronous computation trước actions sau successful get, theo contract của Future.

## 24. Checklist trước khi kết luận một thiết kế thread-safe

- [ ] Liệt kê các shared mutable fields và tất cả readers/writers.
- [ ] Có **data races** nào không? Nếu có, đã xác định tại sao outcome vẫn hợp lệ?
- [ ] Nếu dùng monitor, mọi critical accesses có khóa **cùng object** không?
- [ ] Nếu dùng volatile publication, writes có đứng **trước** release write và reads sau acquire read không?
- [ ] Có writer cạnh tranh hoặc post-publication mutations làm mất tính quyết định không?
- [ ] Có composite operations như `++`, check-then-act, read-modify-write cần atomicity không?
- [ ] `Thread.start()` đã được gọi thật hay chỉ gọi `run()`?
- [ ] Phép đọc từ child có phụ thuộc đúng actions **trước start** không?
- [ ] Phép đọc từ joiner có diễn ra **sau termination detection thành công** không?
- [ ] Có dùng timed join và kiểm tra child thực sự kết thúc không?
- [ ] Có xử lý `InterruptedException` đúng contract ứng dụng không?
- [ ] Waiter có kiểm tra condition bằng `while` dưới cùng monitor không?
- [ ] Có bounded wait, timeout/cancellation thay vì infinite spin khi phù hợp không?
- [ ] Có dùng utilities cấp cao để tránh tự chế signaling protocol khi không cần?
- [ ] Có phân biệt visibility/ordering với mutual exclusion/atomicity?
- [ ] Có tránh dùng println, sleep hoặc debugger timing làm bằng chứng đúng JMM?
- [ ] Có hiểu final-field construction rules và nguy cơ `this` escape không?
- [ ] Có test correctness theo specification, không chỉ tin vào một stress outcome?
- [ ] Có dùng JLS §17.4.5 làm chuẩn khi tranh luận về HB edge không?

## 25. Tổng kết: bốn đường tạo HB phải nhớ

```text
1) MONITOR
   T1: writes → unlock(m)  ---HB---> lock(m) → reads :T2

2) VOLATILE
   T1: writes → write(v)   ---HB---> read(v) → reads :T2
                 volatile              volatile

3) THREAD.START
   T1: writes → t.start()  ---HB---> actions in thread t

4) THREAD.JOIN / TERMINATION DETECTION
   Thread t: writes → termination  ---HB---> joiner
                                           sau successful join

HB có tính bắc cầu với program order.
Không có HB ≠ chắc chắn thấy giá trị cũ, nhưng
cũng không có bảo đảm visibility như mong muốn.
```

**Happens-before là công cụ chứng minh**, không phải mẹo khiến CPU “flush cache”. Với khóa, volatile, start và join, câu hỏi đúng luôn là **“action nào đồng bộ với action nào, và transitivity đưa writes tới reads nào?”** Khi đã vẽ được đường HB, bạn mới có cơ sở nói về visibility; sau đó vẫn phải kiểm tra atomicity, writers cạnh tranh, progress và resource lifecycle.

### Tài liệu chuẩn để đối chiếu

1. **Java Language Specification, Java SE 17, Chapter 17 — Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
2. **JLS §17.4.4 — Synchronization Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.4
3. **JLS §17.4.5 — Happens-before Order:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
4. **Java SE 17 — Thread API, start/join/isAlive and interruptions:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
5. **Java SE 17 — java.util.concurrent package memory-consistency effects:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
6. **Java SE 17 — CountDownLatch and Future API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html ; https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
7. **Java SE 17 — AtomicInteger:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
8. **OpenJDK JCStress project:** https://github.com/openjdk/jcstress

**Bài học cốt lõi:** `synchronized` tạo HB qua **cùng monitor** và cung cấp mutual exclusion; `volatile` tạo HB qua **cùng biến** nhưng không làm compound operation nguyên tử; `Thread.start()` công bố writes của starter tới child; `Thread.join()` công bố writes của child đã kết thúc tới joiner. Dùng **program order + synchronizes-with + transitivity** để chứng minh, thay vì hy vọng theo timing hay cache behavior.