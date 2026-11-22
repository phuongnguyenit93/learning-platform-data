# Shared mutable state, coordination và thread confinement trong Java

Khi nhiều thread cùng xử lý công việc, vấn đề khó thường không nằm ở việc **tạo thread** mà ở câu hỏi **ai được quyền đọc, sửa và công bố dữ liệu; các thread chờ nhau theo quy tắc nào**. Ba khái niệm trọng tâm của bài là:

- **Shared mutable state:** trạng thái có thể thay đổi và có thể được nhiều thread truy cập, ví dụ bộ đếm dùng chung, số dư, cache, danh sách công việc.
- **Coordination:** cơ chế phối hợp tiến độ và trao đổi tín hiệu giữa các thread hoặc tác vụ, ví dụ đợi kết quả, báo hoàn thành, chuyển việc qua queue, giới hạn số tác vụ.
- **Thread confinement:** thiết kế để một trạng thái mutable chỉ được một thread sở hữu và thao tác tại một thời điểm, qua đó tránh phải đồng bộ trên trạng thái đó.

Ba khái niệm này liên quan nhưng không thay thế nhau: một `CountDownLatch` có thể khiến worker đợi đúng lúc nhưng **không tự làm phép `counter++` thành atomic**; một `synchronized` bảo vệ trạng thái chung nhưng không tự giải quyết cách dừng một pipeline; còn một biến khai báo bên trong phương thức **không thực sự confined** nếu tham chiếu của nó được chuyển cho thread khác.

> Phạm vi: các cơ chế concurrency của **Java nói chung** (Java Memory Model, `java.lang`, `java.util.concurrent`). Không bàn đến cơ chế xử lý concurrency riêng của Spring Framework.

## 1. Nhận diện shared mutable state

Một dữ liệu trở thành **shared** khi cùng một đối tượng hoặc vị trí nhớ có thể được truy cập từ nhiều thread. Nó là **mutable** khi nội dung có thể bị thay đổi sau khi được tạo. Nếu đồng thời thỏa cả hai điều kiện, thiết kế cần quy định cách truy cập.

Ví dụ:

```java
final class Metrics {
    int processed; // Mutable, có thể shared khi Metrics được dùng ở nhiều thread.
}
```

Biến `processed` không tự an toàn chỉ vì nó nằm trong một đối tượng Java. Nếu cùng một instance `Metrics` được nhiều worker truy cập, mỗi worker có thể đọc và ghi trường này.

Cần phân biệt:

| Trường hợp | Có shared mutable state? | Cách nghĩ đúng |
| --- | --- | --- |
| Mỗi task tạo một `StringBuilder` riêng và không chia sẻ nó | Không | Mỗi task sở hữu dữ liệu của mình |
| Nhiều thread đọc một `String` đã được công bố an toàn | Có shared, nhưng immutable | Không cần khóa để bảo vệ thay đổi của `String` vì nó không đổi |
| Nhiều thread cùng tăng `int count` của một instance | Có | Cần đảm bảo atomicity và visibility |
| Nhiều thread cùng ghi một `ArrayList` | Có | `ArrayList` không tự bảo đảm thread safety |
| Một thread cập nhật `HashMap`, thread khác đọc cùng map | Có | Cần publication, visibility và bảo vệ cấu trúc dữ liệu |
| Nhiều thread nhận cùng tham chiếu `AtomicInteger` và gọi `incrementAndGet()` | Có | Phép tăng trên biến atomic được tuyến tính hóa; logic nhiều bước vẫn cần phân tích |

**Vị trí khai báo không tự quyết định quyền sở hữu.** Một trường `static` thường dễ trở thành shared, nhưng field instance cũng shared nếu instance đi qua nhiều thread. Tham chiếu cục bộ như `List<T> local` có thể trỏ tới một list dùng chung; ngược lại, field thuộc một đối tượng chỉ thread duy nhất dùng có thể hoàn toàn confined.

### Ba nhóm lỗi cần tách biệt

1. **Atomicity (tính nguyên tử):** một thao tác logic có thực hiện như một bước không thể bị xen giữa hay không?
2. **Visibility (khả năng quan sát):** khi thread A cập nhật trạng thái, thread B có được bảo đảm nhìn thấy bản cập nhật theo quy tắc cần thiết không?
3. **Ordering (thứ tự quan sát):** các thao tác đọc/ghi có quan hệ thứ tự được Java Memory Model bảo đảm hay không?

Một cơ chế có thể giải quyết một phần nhưng không giải quyết tất cả. Chẳng hạn `volatile int count` hỗ trợ visibility và thứ tự đối với truy cập volatile, nhưng `count++` vẫn gồm nhiều thao tác logic nên chưa atomic.

## 2. Data race và lost update: vì sao `count++` nguy hiểm?

Giả sử hai thread cùng thực hiện `count++`. Thao tác có thể được hiểu ở mức logic như sau:

```text
count = 10

Thread A                         Thread B
đọc count -> 10
                                 đọc count -> 10
tính 10 + 1
                                 tính 10 + 1
ghi count = 11
                                 ghi count = 11

Kết quả: 11, dù đã có hai lần tăng; kết quả mong muốn: 12.
```

Đây là ví dụ **lost update**: các bước đọc, tính và ghi bị xen kẽ. Lịch thực thi trên chỉ là một lịch có thể xảy ra, không phải lịch Java luôn chọn.

```java
final class UnsafeCounter {
    private int count;

    void increment() {
        count++; // Read-modify-write, không atomic.
    }

    int get() {
        return count; // Không có bảo đảm visibility khi đọc từ thread khác.
    }
}
```

Dù thay `int` thành `volatile int`, hai thread vẫn có thể đọc cùng giá trị trước khi cùng ghi; `volatile` không biến chuỗi read-modify-write thành một thao tác atomic.

Nếu nhiều thread truy cập cùng biến, có ít nhất một thao tác ghi, và các truy cập xung đột thiếu quan hệ **happens-before** cần thiết, chương trình có **data race** theo Java Memory Model. Hệ quả không chỉ là mất lần tăng: chương trình cũng có thể đọc trạng thái cũ hoặc quan sát các trường liên quan theo cách không phù hợp với bất biến (invariant) thiết kế.

**Invariant** là điều kiện phải đúng ở các thời điểm có thể quan sát hợp lệ, ví dụ `balance >= 0` hoặc `available + reserved == capacity`. Bảo vệ từng field riêng lẻ chưa chắc bảo vệ được invariant liên quan nhiều field.

## 3. Java Memory Model: thế nào là nhìn thấy dữ liệu an toàn?

Java Memory Model (JMM) định nghĩa các bảo đảm về thứ tự và visibility giữa những hành động trên các thread. Khái niệm then chốt là **happens-before** (HB): nếu hành động X happens-before hành động Y, các hiệu ứng bộ nhớ của X phải được quan sát tại Y theo quy tắc của mô hình bộ nhớ, với điều kiện không bị các ghi hợp lệ khác thay thế.

Các quan hệ quan trọng:

| Quan hệ | Bảo đảm nổi bật |
| --- | --- |
| Thứ tự chương trình trong cùng thread | Hành động trước theo program order happens-before hành động sau trong thread đó |
| `Thread.start()` | Các hành động trước khi gọi `start()` happens-before hành động trong thread vừa khởi động |
| `Thread.join()` thành công | Các hành động của thread được đợi happens-before việc thread gọi tiếp tục sau `join()` |
| Monitor (`synchronized`) | Unlock trên monitor happens-before một lần lock tiếp theo trên **cùng** monitor |
| Truy cập `volatile` | Một volatile write happens-before volatile read tiếp theo theo synchronization order đối với cùng biến |
| `ExecutorService.submit` và `Future.get` | Hành động trước khi gửi task happens-before hành động trong task; hành động task happens-before các hành động sau khi lấy kết quả bằng `Future.get()` |
| `BlockingQueue` | Hành động trước khi đưa một phần tử vào queue happens-before hành động sau khi thread khác lấy phần tử tương ứng ra khỏi queue |
| `CountDownLatch` | Hành động trước `countDown()` happens-before hành động sau `await()` trả về thành công tương ứng |

Ví dụ: dữ liệu được khởi tạo trước `thread.start()` có quan hệ visibility tới thread con. Nếu thread con tính kết quả và thread chính `join()` thành công, thread chính đọc được kết quả đã công bố qua quan hệ HB đó. Đây là một lý do có thể đọc kết quả của thread sau `join` ngay cả khi giá trị không phải `volatile`, miễn là không có thêm truy cập xung đột từ thread khác.

**HB không đồng nghĩa khóa toàn bộ ứng dụng.** Đây là quan hệ về thứ tự/visibility. Một chương trình có thể tạo quan hệ HB qua khóa, volatile, queue, lifecycle của thread hoặc công cụ đồng bộ phù hợp.

### Safe publication

**Safe publication** nghĩa là đưa tham chiếu đối tượng cho thread khác theo cách bảo đảm thread nhận nhìn thấy trạng thái khởi tạo hợp lệ. Những cách thường dùng gồm công bố qua monitor, volatile reference, cấu trúc concurrent, gửi task đúng lúc qua executor hoặc quan hệ thread start.

Trường `final` có quy tắc khởi tạo đặc biệt khi constructor không để tham chiếu `this` thoát ra ngoài; nhưng **final reference không làm đối tượng được tham chiếu trở thành immutable**:

```java
final class Holder {
    final java.util.List<String> names = new java.util.ArrayList<>();
}
```

Không thể đổi tham chiếu `names`, song vẫn có thể gọi `names.add(...)`. Nếu list được nhiều thread sửa, việc trường là `final` không biến `ArrayList` thành thread-safe.

## 4. Chiến lược ưu tiên: giảm chia sẻ mutable state trước khi dùng khóa

Một thứ tự ra quyết định hữu ích:

1. **Đừng chia sẻ** nếu không có nhu cầu: dùng biến cục bộ, đối tượng riêng cho mỗi task, hoặc mỗi worker giữ trạng thái riêng.
2. **Chia sẻ dữ liệu immutable** qua safe publication khi có thể: ví dụ cấu hình dạng `record` chứa các giá trị immutable.
3. **Trao đổi dữ liệu qua queue/message** thay vì cho nhiều worker cùng sửa một collection.
4. **Dùng thao tác atomic** khi invariant nằm gọn trong một biến và API atomic hỗ trợ đúng thao tác.
5. **Dùng lock hoặc cấu trúc đồng bộ bậc cao** khi nhiều bước, nhiều trường phải cùng thỏa invariant.

Không có thứ tự cứng cho mọi kiến trúc. Quyết định phụ thuộc vào yêu cầu về tính đúng, độ trễ, thông lượng, khối lượng công việc và sự dễ hiểu khi bảo trì.

### Immutable snapshot

Một cách thiết kế là xây dựng kết quả trong một thread rồi tạo giá trị immutable để chuyển cho thread khác:

```java
record Report(String name, long total) {}

static Report createReport(String name, long total) {
    return new Report(name, total);
}
```

Ở đây `String`, `long` và `record` không chứa cấu trúc mutable nội bộ. Nhưng record **không tự deep-immutable**: nếu record chứa `List<String>`, nên tạo snapshot như `List.copyOf(input)` và bảo đảm bản thân các phần tử trong list cũng phù hợp với yêu cầu bất biến.

Khi cần thay toàn bộ cấu hình, thường dễ hiểu hơn nếu thay một **immutable snapshot** qua một tham chiếu được công bố an toàn thay vì sửa tuần tự nhiều field của một đối tượng dùng chung.

## 5. Bảo vệ shared state với `synchronized`

`synchronized` dùng **intrinsic monitor lock** của đối tượng. Tại cùng thời điểm, nhiều nhất một thread giữ được cùng monitor; thread khác cần lock đó phải chờ. Việc unlock rồi lock cùng monitor cũng tạo quan hệ happens-before.

Ví dụ độc lập, chạy được với Java 17+:

Lưu thành `SynchronizedCounterDemo.java`:

```java
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

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(counter.get());
    }
}
```

Biên dịch và chạy:

```bash
javac SynchronizedCounterDemo.java
java SynchronizedCounterDemo
```

Stdout chính xác:

```text
200000
```

Hai thread cùng tăng **một** counter; `increment()` không bị xen kẽ tại bước `value++` vì cả hai cùng phải giữ monitor của `counter`. `get()` cũng dùng monitor đó để đọc trạng thái nhất quán với các thao tác được bảo vệ. Hai `join()` bảo đảm thread chính đợi cả hai worker hoàn tất trước khi in.

**Lock phải bảo vệ toàn bộ invariant**, không chỉ một thao tác ghi đơn lẻ. Ví dụ trừ số dư cần kiểm tra điều kiện và cập nhật **trong cùng critical section**:

```java
final class Wallet {
    private int balance;

    Wallet(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Negative initial balance");
        }
        balance = initialBalance;
    }

    synchronized boolean withdraw(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        if (balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized int balance() {
        return balance;
    }
}
```

Nếu tách `if (balance >= amount)` và `balance -= amount` thành hai lần khóa riêng, thread khác có thể đổi `balance` giữa hai bước, phá invariant. Khóa phải nhất quán: không được có đường truy cập khác sửa `balance` mà bỏ qua cùng quy tắc bảo vệ.

**Lưu ý:** phương thức `synchronized` trên instance khóa `this`; phương thức `static synchronized` khóa đối tượng `Class`. Hai monitor này khác nhau. Khóa nhầm object thì không mang lại mutual exclusion mong muốn.

## 6. `volatile`, atomic variables, locks: chọn đúng công cụ

| Công cụ | Đặc tính thích hợp | Không tự giải quyết |
| --- | --- | --- |
| `volatile boolean stopped` | Flag được một/nhiều thread ghi và thread khác quan sát, với visibility/ordering | Atomicity của phép đọc-sửa-ghi nhiều bước; tính nhất quán của nhiều field |
| `AtomicInteger.incrementAndGet()` | Tăng một biến nguyên theo phép atomic | Giao dịch cập nhật nhiều đối tượng/field |
| `AtomicReference.compareAndSet(...)` | Thay tham chiếu có điều kiện dựa trên giá trị quan sát | Tính đúng của object mutable bên trong nếu vẫn bị sửa trực tiếp |
| `synchronized` | Bảo vệ critical section và invariant nhiều thao tác dưới cùng monitor | Tự động loại bỏ deadlock hoặc công việc blocking kéo dài |
| `ReentrantLock` | Khóa tường minh, có `tryLock`, tùy chọn interruptible lock và `Condition` | Tự nhả khóa nếu quên `unlock()`; bắt buộc dùng `finally` |
| `ConcurrentHashMap` | Truy cập map concurrent, nhiều thao tác atomic theo key/API cụ thể | Atomicity của chuỗi thao tác nhiều key, hoặc an toàn của value mutable |

### Trường hợp stop flag

```java
final class StopSignal {
    private volatile boolean stopped;

    void requestStop() {
        stopped = true;
    }

    boolean shouldStop() {
        return stopped;
    }
}
```

Các worker có thể đọc `shouldStop()` trong vòng lặp, tuy nhiên nếu worker đang block mãi trong `BlockingQueue.take()` hoặc I/O, **flag một mình không đánh thức được thread**. Cần thêm interruption, timeout hoặc giao thức đóng phù hợp. Một vòng lặp chỉ kiểm tra flag liên tục cũng có thể lãng phí CPU.

### Trường hợp counter đơn biến

```java
import java.util.concurrent.atomic.AtomicInteger;

final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    int incrementAndGet() {
        return count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
```

`AtomicInteger` thích hợp nếu logic là tăng/giảm một giá trị. Nếu điều kiện thành công phụ thuộc vào **hai giá trị liên quan**, chỉ gọi riêng hai atomic operations chưa khiến toàn bộ chuỗi thành một giao dịch.

### Khi dùng `ReentrantLock`

```java
import java.util.concurrent.locks.ReentrantLock;

final class GuardedValue {
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

    int get() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
```

Mọi đường truy cập tới `value` phải tuân theo cùng khóa. Dùng `finally` để giải phóng khóa kể cả khi có exception. Không giữ lock qua một tác vụ I/O hoặc callback không kiểm soát nếu có thể tránh, vì điều đó tăng thời gian chờ và nguy cơ deadlock.

## 7. Coordination: bảo vệ dữ liệu và phối hợp tiến độ là hai bài toán

**Mutual exclusion** trả lời: *ai được phép vào critical section?*

**Coordination** trả lời: *tác vụ nào cần chờ sự kiện nào, ai báo hoàn tất, công việc và kết quả đi qua kênh nào, khi nào dừng?*

Ví dụ: nhiều worker cập nhật một giá trị bằng `AtomicInteger` đã giải quyết phép tăng atomic, nhưng thread tổng hợp vẫn phải biết **khi nào mọi worker hoàn thành** để xuất báo cáo cuối. Ngược lại, thread tổng hợp có thể dùng `CountDownLatch.await()` để đợi đủ worker, nhưng điều đó không làm các phép tăng `int count++` giữa worker an toàn.

### Nhóm công cụ phối hợp chính

| Công cụ Java | Mục đích | Đặc tính cần nhớ |
| --- | --- | --- |
| `Thread.join()` | Chờ một thread kết thúc | Caller có thể bị block; không nên dùng sleep để đoán thời điểm hoàn thành |
| `Future.get()` | Chờ và lấy kết quả task | Có thể block và ném `InterruptedException`/`ExecutionException`; `get(timeout, unit)` có giới hạn chờ |
| `CountDownLatch` | Đợi số tín hiệu hoàn thành cố định | One-shot; mỗi `countDown()` giảm bộ đếm; không tự reset |
| `CyclicBarrier` | Cho nhóm worker gặp tại cùng điểm trước khi tiếp tục | Có thể tái sử dụng qua các vòng; cần xử lý barrier bị phá |
| `Phaser` | Đồng bộ theo phase, có thể đăng ký/hủy đăng ký participant | Phù hợp vòng nhiều giai đoạn với số participant linh hoạt |
| `Semaphore` | Giới hạn số permit cho tài nguyên/tác vụ | `acquire()` có thể block; phải `release()` đúng cách |
| `BlockingQueue` | Truyền công việc giữa producer và consumer | `put()` có thể chờ khi queue đầy, `take()` có thể chờ khi rỗng |
| `Condition` trên `Lock` | Đợi và thông báo predicate dưới một lock | Luôn kiểm tra điều kiện bằng vòng `while`, không dựa vào một `signal()` đơn lẻ |
| `wait()/notifyAll()` | Cơ chế điều kiện ở mức monitor | Phải giữ monitor, kiểm tra predicate trong vòng `while`, tránh dùng nếu công cụ bậc cao phù hợp hơn |

`Thread.sleep(...)` chỉ làm thread tạm nghỉ; nó **không bảo đảm** worker khác đã xong, dữ liệu đã được công bố an toàn hoặc điều kiện đã đúng. Dùng `join`, future, latch hay queue khi cần quan hệ hoàn thành cụ thể.

## 8. Ví dụ producer–consumer: coordination qua `BlockingQueue`

Một queue giới hạn dung lượng vừa chuyển dữ liệu vừa tạo **backpressure**: producer phải chờ nếu consumer chưa lấy kịp. Điều này giúp tránh việc nhiều worker sửa trực tiếp cùng một danh sách kết quả.

Ví dụ độc lập sau dùng **một** producer, **một** consumer, và số `0` làm tín hiệu kết thúc (đầu vào hợp lệ chỉ gồm số dương). Lưu thành `BlockingQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockingQueueDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> producer = executor.submit(() -> {
                for (int i = 1; i <= 5; i++) {
                    queue.put(i);
                }
                queue.put(0); // Sentinel: kết thúc luồng dữ liệu.
                return null;
            });

            Future<Integer> consumer = executor.submit(() -> {
                int sum = 0;
                while (true) {
                    int item = queue.take();
                    if (item == 0) {
                        return sum;
                    }
                    sum += item;
                }
            });

            producer.get();
            System.out.println("Tong = " + consumer.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy với Java 17+:

```bash
javac BlockingQueueDemo.java
java BlockingQueueDemo
```

Stdout chính xác:

```text
Tong = 15
```

Điều gì được bảo đảm?

- Producer có thể `put` cùng lúc consumer `take`; queue đảm nhiệm đồng bộ nội bộ nên không cần tự khóa danh sách.
- `ArrayBlockingQueue<>(2)` không giữ quá hai phần tử chờ cùng lúc; `put` có thể block khi đầy, `take` có thể block khi rỗng. Đây là **blocking coordination**, không phải non-blocking I/O.
- Consumer là chủ sở hữu duy nhất của biến `sum`. Không có hai thread cùng sửa biến đó, nên không cần `AtomicInteger` cho `sum`.
- Sentinel `0` chỉ đúng vì dữ liệu thực không chứa `0` và có đúng một consumer. Nếu có nhiều consumer, giao thức kết thúc phải bảo đảm mỗi consumer thoát đúng cách.
- Các thao tác `Future.get()` đợi hoàn tất và công bố kết quả tới caller. `shutdown()` giải phóng vòng đời executor sau các tác vụ đã gửi.

**Điều kiện triển khai thực tế:** cần đường xử lý khi producer thất bại trước khi gửi sentinel, khi consumer thất bại, khi task bị hủy, và khi caller không thể chờ vô hạn. Tùy yêu cầu có thể dùng timeout, cancel, close signal, định nghĩa trạng thái lỗi chung hoặc cơ chế điều phối cao hơn. Ví dụ trên chỉ minh họa luồng thành công.

## 9. Ví dụ coordination khi các worker phải cùng hoàn tất: `CountDownLatch`

`CountDownLatch` hữu ích khi một thread điều phối cần chờ một nhóm công việc độc lập báo xong. Nó **không phải** mutex.

Lưu thành `LatchDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(3);
        AtomicInteger total = new AtomicInteger();

        for (int i = 1; i <= 3; i++) {
            final int contribution = i * 10;
            Thread worker = new Thread(() -> {
                try {
                    total.addAndGet(contribution);
                } finally {
                    finished.countDown();
                }
            });
            worker.start();
        }

        finished.await();
        System.out.println("Tong = " + total.get());
    }
}
```

```bash
javac LatchDemo.java
java LatchDemo
```

Stdout chính xác:

```text
Tong = 60
```

Ở đây `AtomicInteger` bảo đảm phép cộng an toàn khi các worker cập nhật `total`; `CountDownLatch` bảo đảm thread `main` chỉ in sau khi cả ba worker đã hoàn tất và gọi `countDown()`. Hai công cụ giải quyết **hai mối quan tâm khác nhau**. Đặt `countDown()` trong `finally` giúp tránh tình huống một worker lỗi ở đoạn xử lý rồi quên giảm latch. Tuy nhiên, ứng dụng thực tế vẫn cần thu thập và báo lỗi worker, vì một latch về 0 không chứng minh tất cả worker thành công.

Nếu nhóm công việc có nhiều vòng và cần chờ nhau ở cuối **mỗi vòng**, cân nhắc `CyclicBarrier` hoặc `Phaser` thay cho việc tái sử dụng một latch đã về 0. Một `CountDownLatch` không reset được.

## 10. Thread confinement: ai sở hữu trạng thái?

**Thread confinement** nghĩa là một đối tượng mutable được truy cập độc quyền bởi một thread trong một giai đoạn sở hữu, không cho phép các thread khác cùng sửa/đọc trạng thái đó không có phối hợp. Vì không có truy cập xung đột, có thể tránh việc đặt lock quanh từng thao tác.

Các kiểu thường gặp:

1. **Stack/task confinement:** Mỗi lần gọi tạo state riêng, không để tham chiếu thoát ra ngoài; đây là lựa chọn đơn giản nhất.
2. **Actor/event-loop ownership:** Một worker sở hữu map/cache/bộ tích lũy và nhận lệnh qua queue; các thread khác gửi message thay vì chạm vào state.
3. **`ThreadLocal<T>`:** Mỗi thread có một giá trị được gắn với thread đó; hữu ích với một số context hoặc buffer, nhưng phải quản lý vòng đời đặc biệt cẩn thận khi tái sử dụng thread.

### Cách đơn giản nhất: state cục bộ theo task

```java
static String formatForOneTask(String id) {
    StringBuilder buffer = new StringBuilder(); // Mỗi lời gọi có builder riêng.
    buffer.append("job-").append(id);
    return buffer.toString(); // Trả String immutable.
}
```

Hai thread có thể cùng chạy phương thức này mà không chia sẻ `buffer`. Không cần `synchronized` hoặc `ThreadLocal`. Đây là lý do **giảm chia sẻ** thường đơn giản hơn việc dùng thêm công cụ đồng bộ.

Nhưng nếu `buffer` được đặt vào một collection chung hoặc chuyển tham chiếu tới thread khác trước khi hoàn tất, state có thể không còn confined. Quy tắc là **không để mutable reference thoát khỏi quyền sở hữu**.

### Khi thật sự cần `ThreadLocal`

`ThreadLocal` lưu một giá trị riêng theo thread, thường có ích khi một API cũ đòi hỏi context theo thread mà không truyền tham số tường minh thuận tiện. Nó không làm đối tượng bên trong `ThreadLocal` tự thread-safe nếu đối tượng đó bị chuyển tham chiếu sang thread khác.

Ví dụ độc lập minh họa cleanup với thread pool tái sử dụng worker. Lưu thành `ThreadLocalDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalDemo {
    private static final ThreadLocal<StringBuilder> BUFFER =
            ThreadLocal.withInitial(StringBuilder::new);

    private static String process(String id) {
        StringBuilder buffer = BUFFER.get();
        try {
            buffer.append("job-").append(id);
            return buffer.toString();
        } finally {
            BUFFER.remove(); // Xóa state gắn với worker sau task.
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> first =
                    executor.submit(() -> process("A"));
            Future<String> second =
                    executor.submit(() -> process("B"));

            System.out.println(first.get());
            System.out.println(second.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
```

Stdout chính xác:

```text
job-A
job-B
```

Cả hai task chạy trên cùng một worker do `newSingleThreadExecutor()` tái sử dụng thread; `remove()` khiến task sau nhận `StringBuilder` mới thay vì giữ nội dung của task trước. Với state chỉ dùng nội bộ một lời gọi như ví dụ, **biến cục bộ vẫn là lựa chọn ưu tiên**; `ThreadLocal` được dùng ở đây để minh họa chính xác cơ chế và rủi ro vòng đời.

**Các giới hạn quan trọng của `ThreadLocal`:**

- Nó gắn state theo **thread**, không gắn theo **request** hay `CompletableFuture`. Một chuỗi async chạy trên nhiều thread không được tự động mang theo giá trị `ThreadLocal` giữa các stage.
- Thread trong pool có thể sống lâu hơn task; nếu quên `remove()`, task khác trên cùng worker có thể gặp dữ liệu cũ, đồng thời các object được tham chiếu có thể bị giữ trong bộ nhớ lâu hơn mong muốn.
- `ThreadLocal` không phải phương thức bảo mật hay cách đồng bộ state giữa các thread. Nó ngăn chia sẻ qua *đường truy cập ThreadLocal* chứ không ngăn lập trình viên cố tình chia sẻ chính đối tượng mutable.
- Với Java 21+, virtual threads vẫn là thread và có thể dùng `ThreadLocal`, nhưng việc gắn dữ liệu nặng vào số lượng virtual threads rất lớn có thể tốn bộ nhớ. Phần này thuộc Java core; không cần cơ chế riêng của framework.

## 11. Handover ownership: chuyển quyền thay vì chia sẻ tự do

Một thiết kế hiệu quả là chia công việc thành các giai đoạn mà mỗi giai đoạn có **một chủ sở hữu mutable state**:

```text
Nguồn dữ liệu
    |
    v
[Producer - sở hữu state đầu vào]
    |
    | gửi item/snapshot qua BlockingQueue
    v
[Consumer - sở hữu state tích lũy]
    |
    | công bố kết quả immutable qua Future
    v
[Caller - đọc kết quả]
```

Lợi ích:

- Producer không cần lock quanh bộ tích lũy của consumer.
- Queue xác định điểm chuyển giao công việc và cung cấp quy tắc visibility.
- Consumer cập nhật state của nó theo thứ tự nhận message.
- Caller lấy kết quả hoàn tất qua future; không cần đọc một đối tượng đang bị sửa giữa chừng.

Lưu ý: **đưa một tham chiếu mutable vào queue không tự chuyển quyền sở hữu bằng phép màu**. Producer phải ngừng sửa đối tượng sau khi chuyển giao, hoặc gửi một bản sao/immutable snapshot. Nếu producer vẫn sửa chính object đó trong khi consumer đọc thì shared mutable state vẫn tồn tại, dù có queue ở giữa.

Cũng cần xác định ranh giới lỗi và hủy: ai đóng producer, ai gửi tín hiệu kết thúc, ai quyết định khi consumer thất bại và ai chịu trách nhiệm giải phóng tài nguyên.

## 12. Dùng concurrent collections đúng phạm vi bảo đảm

Các collection trong `java.util.concurrent` giúp giảm việc tự viết khóa trên cấu trúc dữ liệu chia sẻ:

- `ConcurrentHashMap`: đọc/cập nhật concurrent trên map. Một số phương thức như `putIfAbsent`, `compute` và `merge` cung cấp thao tác atomic theo chính sách của API. **Không** suy luận hai lệnh `get` rồi `put` là một thao tác atomic.
- `ConcurrentLinkedQueue`: queue concurrent không blocking, không có giới hạn dung lượng mặc định; caller cần giao thức riêng để biết khi nào có dữ liệu và khi nào kết thúc.
- `ArrayBlockingQueue`/`LinkedBlockingQueue`: cung cấp `put/take` chờ và giao tiếp producer–consumer. Với `LinkedBlockingQueue`, cân nhắc cấu hình dung lượng phù hợp để tránh hàng đợi tăng không kiểm soát.
- `CopyOnWriteArrayList`: phù hợp khi đọc nhiều, ghi ít, vì thao tác thay đổi thường tạo bản sao cấu trúc; không tối ưu cho dữ liệu cập nhật liên tục.
- `LongAdder`: có thể hữu ích cho counter thống kê nhiều thread cập nhật; `sum()` trong lúc các thread vẫn cập nhật **không nhất thiết là snapshot atomic**. Nếu phải có một điểm quan sát chính xác và đồng bộ với các cập nhật khác, cần thiết kế phù hợp hơn.

Ví dụ `ConcurrentHashMap<String, Integer>` chỉ bảo vệ thao tác map theo hợp đồng. Nếu value là một `ArrayList` mutable và nhiều thread tự ý gọi `map.get(key).add(...)`, list vẫn có thể bị race. Thread safety của container không tự lan sang nội dung mutable được chứa trong đó.

## 13. Tránh deadlock, starvation và chờ sai điều kiện

### Deadlock khi lấy nhiều lock sai thứ tự

Giả sử thread A giữ lock X rồi chờ lock Y, trong khi thread B giữ Y rồi chờ X:

```text
Thread A: lock X -> chờ Y
Thread B: lock Y -> chờ X
                   |
                 deadlock
```

Cách giảm nguy cơ là quy định **thứ tự lock nhất quán** khi cần lấy nhiều khóa, giảm thời gian giữ khóa, tránh gọi logic không kiểm soát khi đang giữ khóa và dùng `tryLock` có timeout khi yêu cầu hệ thống cho phép. Thứ tự khóa phải áp dụng trên mọi đường code liên quan, không chỉ một phương thức.

**Starvation** xảy ra khi một tác vụ không được cấp tiến độ hợp lý dù các tác vụ khác tiếp tục chạy; không đồng nghĩa deadlock. Fair lock/queue có thể hỗ trợ tính công bằng trong một số trường hợp nhưng không thay thế thiết kế giới hạn tải và quản lý scheduler.

### Chờ điều kiện với monitor

Khi buộc phải dùng `Object.wait/notifyAll`, nguyên tắc là bảo vệ predicate và chờ **trong vòng while dưới cùng monitor**:

```java
final class Gate {
    private boolean open;

    synchronized void awaitOpen() throws InterruptedException {
        while (!open) {
            wait();
        }
    }

    synchronized void open() {
        open = true;
        notifyAll();
    }
}
```

Thread gọi `wait()` phải giữ monitor; thao tác `wait` giải phóng monitor trong khi chờ rồi lấy lại monitor trước khi trả về. Dùng `while` vì có thể thức dậy mà điều kiện vẫn chưa đúng (bao gồm spurious wakeup và thread khác đã thay đổi điều kiện). `notifyAll` thức các waiter phù hợp để kiểm tra lại predicate; nó không tự trao quyền chạy tức thì.

Với producer–consumer hoặc coordination thông thường, `BlockingQueue` và các công cụ bậc cao thường giúp code ít lỗi hơn.

## 14. Cancellation, interruption và quản lý vòng đời

Một thiết kế concurrency đúng không chỉ trả kết quả khi mọi thứ thuận lợi; nó phải xác định **ai có quyền dừng**, **thread đang block được đánh thức thế nào** và **lỗi có truyền về nơi gọi không**.

- `Thread.interrupt()` gửi yêu cầu interruption, không cưỡng bức kết thúc thread. Các thao tác như `sleep`, `wait`, `join`, `BlockingQueue.put/take` có thể phản hồi bằng `InterruptedException`.
- Nếu bắt `InterruptedException` mà không thể xử lý dứt điểm, thường nên kết thúc tác vụ và/hoặc khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`. Không nuốt exception rồi tiếp tục chờ vô hạn.
- `Future.cancel(true)` có thể yêu cầu ngắt task đang chạy, nhưng thành công cuối cùng tùy việc task có hỗ trợ interruption và điểm blocking có đáp ứng không.
- `ExecutorService.shutdown()` không nhận task mới và cho task đã gửi hoàn tất; `shutdownNow()` cố gắng dừng task đang hoạt động và trả các task chờ, nhưng cũng không bảo đảm dừng ngay.
- Khi dùng `Lock` tường minh, đặt `unlock()` trong `finally`. Khi dùng queue, semaphore hoặc latch, lên kế hoạch cleanup và tín hiệu kết thúc trong cả đường lỗi.
- Với `Semaphore`, chỉ `release()` permit mà task thực sự đã `acquire()` thành công. Việc release dư có thể tăng số permit ngoài giới hạn logic.
- Khi báo cáo kết quả, dùng điểm hội tụ rõ ràng (`Future.get`, `join`, latch hoặc signal) và phân biệt **hoàn tất** với **thành công**. Task kết thúc bằng exception vẫn là một kết thúc.

Nếu một request bị hủy trong khi một worker vẫn giữ mutable context, phải bảo đảm context được đóng hoặc dọn theo vòng đời sở hữu; nếu thread được tái sử dụng, hãy kiểm tra những `ThreadLocal` còn tồn tại.

## 15. Chọn thiết kế qua ba bài toán cụ thể

### A. Thống kê số request hoàn tất

**Bài toán:** nhiều worker cùng tăng một số đếm, không có invariant liên quan nhiều biến.

Thiết kế thường phù hợp: `AtomicInteger` hoặc `LongAdder` nếu là thống kê có contention cao và chấp nhận semantics của `sum()`. Không cần khóa lớn quanh toàn bộ xử lý request chỉ để tăng counter. Nếu muốn ảnh chụp thống kê nhất quán tại một mốc, xác định rõ điểm hoàn tất và cách đọc.

### B. Một ví phải bảo đảm số dư không âm

**Bài toán:** cần kiểm tra `balance >= amount` trước khi giảm.

Thiết kế phù hợp: giữ kiểm tra và cập nhật trong **một critical section** (`synchronized` hoặc lock), hoặc dùng vòng CAS thiết kế cẩn thận cho state một biến. `volatile int balance` không đủ, vì phép kiểm tra và trừ là thao tác kết hợp. Nếu chuyển tiền giữa hai ví, cần một thiết kế atomic giữa hai đối tượng và thứ tự khóa tránh deadlock; khóa mỗi ví độc lập rồi cập nhật lần lượt chưa bảo đảm giao dịch tổng thể.

### C. Nhiều nguồn gửi sự kiện, một worker cập nhật trạng thái tổng hợp

**Bài toán:** chỉ một logic tổng hợp cần cập nhật state; producer khác nhau không cần sửa state đó trực tiếp.

Thiết kế phù hợp: dùng `BlockingQueue` có giới hạn; producer gửi event/immutable message, consumer sở hữu map và state mutable của riêng nó. Bảo đảm consumer ngừng đúng cách và thông báo lỗi. Ưu điểm chính là thay đổi **quyền sở hữu dữ liệu**, giúp không phải đặt lock ở từng phép sửa map.

## 16. Những nhầm lẫn thường gặp

1. **"`volatile` giải quyết race condition."** Chỉ đúng với những giao thức cụ thể dựa trên visibility/ordering; `volatile count++` vẫn có thể lost update.
2. **"Có `CountDownLatch` thì dữ liệu worker chia sẻ đã thread-safe."** Latch phối hợp việc đợi và tạo quan hệ HB, không cung cấp mutual exclusion cho các cập nhật concurrent trong lúc chạy.
3. **"Dùng `AtomicInteger` nghĩa là toàn bộ object atomic."** Chỉ những thao tác được định nghĩa trên atomic variable có bảo đảm tương ứng.
4. **"Field `final` biến collection thành immutable."** Nó cố định tham chiếu, không ngăn việc sửa các phần tử trong collection.
5. **"Biến local luôn an toàn."** Biến local chỉ giữ tham chiếu; đối tượng được tham chiếu vẫn có thể bị chia sẻ.
6. **"Concurrent map thì value của map cũng an toàn."** Cần phân tích thread safety của value riêng.
7. **"Một queue bảo đảm không còn data race."** Nếu producer tiếp tục sửa object đã đưa vào queue, data race vẫn có thể xảy ra.
8. **"`ThreadLocal` là dữ liệu theo request."** Nó là dữ liệu theo **thread**; reuse thread và async hop có thể phá giả định đó.
9. **"`Thread.sleep()` là cơ chế đợi worker hoàn thành."** Thời gian ngủ chỉ là khoảng trì hoãn, không chứng minh sự kiện đã xảy ra.
10. **"`notify()` thức một waiter nên có thể bỏ kiểm tra điều kiện."** Waiter vẫn phải kiểm tra predicate trong vòng `while` khi thức dậy và lấy lại monitor.
11. **"Dùng nhiều lock sẽ luôn nhanh hơn một lock."** Tách khóa có thể làm tăng concurrency nhưng cũng tăng rủi ro vi phạm invariant và deadlock.
12. **"`shutdown()` dừng task ngay."** Nó không cưỡng bức chấm dứt task đang chạy; cần thiết kế cancellation phù hợp.

## 17. Checklist khi thiết kế shared state và coordination

Trước khi triển khai, trả lời các câu hỏi theo thứ tự:

1. **State nào mutable?** Ai tạo, ai sở hữu, ai còn giữ tham chiếu?
2. **Có cần chia sẻ không?** Có thể dùng immutable snapshot, state cục bộ hoặc một consumer sở hữu độc quyền không?
3. **Nếu cần chia sẻ, invariant nào phải giữ?** Một biến atomic hay nhiều field cần critical section?
4. **Thread khác nhìn thấy thay đổi bằng cơ chế nào?** Có quan hệ happens-before rõ ràng qua lock, volatile, queue, start/join, future không?
5. **Worker đợi điều kiện gì?** Dùng queue, latch, future, semaphore, barrier hoặc condition phù hợp; tránh đoán bằng sleep.
6. **Hệ thống dừng và báo lỗi thế nào?** Ai gửi tín hiệu kết thúc, ai xử lý interruption, ai hủy và đóng tài nguyên?
7. **Đã kiểm tra ranh giới thread pool chưa?** `ThreadLocal` có cleanup không, dữ liệu task trước có thể lọt sang task sau không?
8. **Đã đo độ trễ và contention chưa?** Hạn chế lock quá rộng và queue không giới hạn, nhưng không đổi tính đúng lấy hiệu năng suy đoán.

Với Java concurrency, điểm xuất phát tốt nhất là **quy định quyền sở hữu trạng thái**, sau đó chọn cơ chế **bảo vệ invariant** và **phối hợp tiến độ** riêng rẽ. Từ đó mới quyết định có cần `synchronized`, atomic variables, concurrent collections, queue hay `ThreadLocal`.