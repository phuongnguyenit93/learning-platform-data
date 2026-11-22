# Interleaving và tính không xác định của kết quả trong Java Concurrency

> **Phạm vi:** race conditions trong Java nói chung: thứ tự xen kẽ thao tác của các thread, kết quả phụ thuộc lịch thực thi, cách Java Memory Model (JMM) ảnh hưởng đến quan sát, và cách tạo tính đúng đắn bằng đồng bộ hóa. Không đi vào các cơ chế concurrency riêng của Spring.

## 1. Học xong bài này, bạn cần nắm được gì?

- Giải thích **interleaving** (xen kẽ các bước thực thi) và vì sao thứ tự thực thi giữa các thread không được mặc định cố định.
- Phân biệt **thứ tự không xác định** với **kết quả sai do race condition**; một chương trình đồng thời có thể cho thứ tự khác nhau nhưng vẫn bảo toàn mọi yêu cầu.
- Phân tích một phép `counter++` thành nhiều bước, chỉ ra lịch thực thi dẫn đến **lost update**.
- Hiểu giới hạn của mô hình xen kẽ đơn giản: Java Memory Model cho phép những quan sát liên quan visibility và reorderings nếu thiếu ràng buộc *happens-before*.
- Nhận biết và sửa các lỗi check-then-act, read-modify-write, không giữ invariant và lệ thuộc vào `sleep/yield`.
- Tạo ví dụ tái hiện race một cách có kiểm soát, rồi xác minh giải pháp bằng `synchronized`, `Lock`, atomic classes hoặc cơ chế truyền dữ liệu thích hợp.

**Ý tưởng trung tâm:** concurrency cho phép nhiều thread tiến triển trong những khoảng thời gian giao nhau. *Scheduler* quyết định thread nào có cơ hội chạy, nhưng **tính đúng đắn** phải được thiết kế bằng các quy tắc chia sẻ trạng thái và thứ tự có thể chứng minh được, không dựa vào việc “thường thấy thread A chạy trước B”.

## 2. Interleaving là gì?

Giả sử hai thread thực hiện những chuỗi bước logic riêng:

- Thread A: `A1 → A2 → A3`.
- Thread B: `B1 → B2 → B3`.

Nếu không có quan hệ đồng bộ buộc thứ tự chéo, một cách mô tả để học là: các bước của A và B có thể xen kẽ theo nhiều lịch khác nhau, **trong khi thứ tự phụ thuộc bắt buộc bên trong từng thread vẫn được tôn trọng theo ngữ nghĩa chương trình**.

Ví dụ các lịch trừu tượng:

```text
Lịch 1: A1 A2 A3 B1 B2 B3
Lịch 2: A1 B1 A2 B2 A3 B3
Lịch 3: B1 A1 B2 B3 A2 A3
```

Không có nghĩa máy luôn chạy một bước rồi dừng để chuyển thread; đây là **mô hình suy luận**. Trên máy nhiều CPU, các thao tác thực tế có thể diễn ra đồng thời. JIT, CPU và hệ thống bộ nhớ còn có thể làm thứ tự quan sát các truy cập dữ liệu **khác với cách đọc đơn giản từng dòng mã nguồn** nếu thiếu đồng bộ phù hợp. Một interleaving “hợp lý” để minh họa lost update chưa phải tập hợp đầy đủ mọi hành vi JMM cho chương trình có data race.

Vì sao lịch khác nhau giữa các lần chạy?

1. Hệ điều hành có thể preempt hoặc xếp lịch các platform thread ở những thời điểm khác nhau.
2. Số CPU khả dụng, tải hệ thống, GC, thời điểm xử lý I/O và contention thay đổi.
3. Các phép đồng bộ như lock acquisition, park/unpark hoặc đợi queue tác động đến thứ tự tiến triển.
4. Java không có hợp đồng rằng thứ tự gọi `start()` quyết định thứ tự thread vào `run()` hay hoàn thành.

**Non-determinism** nghĩa là không thể suy ra một thứ tự hoặc kết quả quan sát duy nhất từ các bảo đảm đang có. Nó không đồng nghĩa với “ngẫu nhiên phân phối đều”: một lịch có thể xuất hiện thường xuyên trên máy của bạn nhưng **vẫn không được đảm bảo**.

## 3. Lost update: hai thread cùng tăng một biến

Đoạn sau là **mã minh họa nằm trong một class**, giả sử `counter` là một trường `int` được nhiều thread chia sẻ:

```java
counter++;
```

Về ý nghĩa read-modify-write, hãy tách nó thành:

```text
R: đọc counter vào giá trị tạm
C: cộng thêm 1
W: ghi giá trị mới về counter
```

Trên Java, `counter++` **không tự động là một thao tác nguyên tử**. Hai thread có thể cùng đọc giá trị cũ, tính riêng rồi ghi đè kết quả của nhau.

Giả sử ban đầu `counter=0`, A và B đều thực hiện một lần tăng:

| Bước của lịch (mô hình tuần tự nhất quán) | Thread A | Thread B | Giá trị chia sẻ |
|---|---|---|---|
| 1 | Đọc `0` vào `a` | — | `0` |
| 2 | — | Đọc `0` vào `b` | `0` |
| 3 | Tính `a+1` và ghi `1` | — | `1` |
| 4 | — | Tính `b+1` và ghi `1` | `1` |

**Kết quả = 1, dù có hai lần tăng.** Đó là *lost update*: cập nhật của một thread bị cập nhật dựa trên dữ liệu cũ của thread khác ghi đè. Nếu A hoàn thành đầy đủ trước khi B đọc, kết quả có thể là 2.

Ở mô hình đơn giản mỗi thread gồm **đọc (R) rồi ghi (W)**, có 6 lịch giữ nguyên thứ tự R-before-W của từng thread. Hai lịch tuần tự `A_R A_W B_R B_W` và `B_R B_W A_R A_W` cho kết quả 2; bốn lịch còn lại đều có cả hai lần đọc trước lần ghi cuối và cho kết quả 1. Đây là cách đếm **chỉ của mô hình 4 bước ấy**; không phải xác suất mất dữ liệu “4/6” của JVM, vì scheduler không chọn đều các lịch và JMM rộng hơn giả định này.

Một lỗi tương tự xảy ra khi nhiều thread cập nhật số dư, bộ đếm tồn kho, sequence ID, số lượng chỗ trống, trạng thái đặt chỗ hoặc các trường có invariant liên quan nhau. Đọc đúng một giá trị ở thời điểm nào đó không đảm bảo thao tác **kiểm tra rồi cập nhật** sẽ đúng khi thread khác cùng thay đổi dữ liệu.

## 4. Phân biệt nondeterministic order, race condition và data race

Ba khái niệm dễ bị trộn lẫn:

| Khái niệm | Định nghĩa thực dụng | Có nhất thiết là lỗi? |
|---|---|---|
| **Interleaving** | Các bước/thao tác của nhiều thread được sắp xen kẽ theo một lịch thực thi. | Không. |
| **Nondeterministic order** | Thứ tự completion/print/giành lock có thể khác nhau giữa các lần chạy. | Không; nhiều ứng dụng chỉ cần invariant và kết quả tập hợp đúng. |
| **Race condition** | Kết quả hoặc hành vi đúng/sai phụ thuộc vào quan hệ thời gian/thứ tự giữa các hoạt động đồng thời chưa được phối hợp đúng. | Thường là lỗi correctness. |
| **Data race** theo JMM | Hai truy cập xung đột tới cùng biến (ít nhất một ghi), không có thứ tự *happens-before* thích hợp giữa chúng và không được phối hợp bằng các bảo đảm đồng bộ cần thiết. | Là dấu hiệu nghiêm trọng của chia sẻ trạng thái không an toàn, nhưng không đồng nhất với mọi race ở mức nghiệp vụ. |

Ví dụ một chương trình cho phép task A và B hoàn tất theo bất kỳ thứ tự nào nhưng ghi kết quả riêng vào hai vị trí độc lập, sau đó `join()` và tính tổng: **lịch có thể không xác định, tổng vẫn đúng**.

Ngược lại, ví dụ “nếu chưa có thì tạo” có thể sai ngay cả khi dùng cấu trúc dữ liệu thread-safe cho từng lệnh:

```java
// Đoạn minh họa: seen là một ConcurrentHashMap<String, Boolean>
// Hai lệnh riêng lẻ an toàn, nhưng cặp kiểm tra + thêm không là một thao tác nguyên tử.
if (!seen.containsKey(key)) {
    seen.put(key, Boolean.TRUE);
    performSideEffect();
}
```

Hai thread cùng thấy “chưa có”, rồi cả hai thực hiện side effect. Giải pháp khi muốn **chỉ một thread thắng việc thêm key**:

```java
if (seen.putIfAbsent(key, Boolean.TRUE) == null) {
    performSideEffect();
}
```

Đây vẫn là **đoạn mã minh họa**, không phải chương trình đầy đủ: `seen`, `key` và `performSideEffect()` được khai báo trong ngữ cảnh bên ngoài. `putIfAbsent` giúp quyết định duy nhất một thread nhận “quyền làm” trong bộ nhớ, nhưng nếu side effect thất bại thì còn phải có **chính sách retry/rollback/idempotency**; không suy ra thao tác bên ngoài trở thành giao dịch nguyên tử với map. Nếu map có thể đã chứa key với value `null` thì cần xét lại API; `ConcurrentHashMap` không cho phép null key/value.

## 5. Vì sao thay đổi một dòng code có thể làm bug biến mất?

Nhiều race condition chỉ lộ ra dưới những lịch “hiếm”:

- Thêm `System.out.println` khiến thay đổi thời gian thực thi và bản thân `PrintStream` có đồng bộ ở nhiều đường đi; biểu hiện race có thể đổi.
- Debugger, logging, profiler, độ dài vòng lặp hoặc tốc độ CPU làm thread chạm vào vùng nguy hiểm ở thời điểm khác.
- Gọi `Thread.sleep(10)` có thể làm một lịch thường gặp hơn nhưng không tạo quy tắc ordering cho dữ liệu chia sẻ.
- `Thread.yield()` chỉ là gợi ý, không buộc scheduler cấp lượt cho thread cụ thể; không bảo đảm fairness hay tính đúng đắn.
- Chạy cùng binary nhiều lần không nhất thiết thấy tất cả lịch có thể xảy ra; nhiều test chạy thành công **không chứng minh** chương trình race-free.

Đừng “sửa” race bằng cách chèn thời gian ngủ tùy tiện. Hãy xác định biến chung, những lệnh đọc/ghi cần được xem như một giao dịch logic, và quan hệ đồng bộ nào phải thiết lập giữa chúng.

## 6. Java Memory Model: xen kẽ các lệnh chưa đủ để giải thích mọi thứ

Một **interleaving tuần tự nhất quán** (*sequential consistency*) tưởng tượng tất cả memory operation xảy ra theo một thứ tự tổng, vẫn tôn trọng thứ tự chương trình của mỗi thread. Mô hình đó hữu ích để thấy lost update, nhưng **Java không hứa rằng mọi chương trình chứa data race đều quan sát như một lịch xen kẽ đơn giản các dòng Java**.

Java Memory Model (JLS `17.4) phân biệt các quan hệ quan trọng:

- **Program order:** thứ tự các action theo thực thi của một thread, dùng để định nghĩa `happens-before`; các tối ưu vẫn có thể sắp xếp lại thao tác vật lý miễn đáp ứng những bảo đảm quan sát cần thiết.
- **Synchronization order:** thứ tự các synchronization actions như volatile access và lock/unlock theo JMM.
- **Synchronizes-with:** quan hệ được quy định giữa các action, ví dụ nhả monitor rồi một thread khác lấy cùng monitor.
- **Happens-before (HB):** quan hệ bắc cầu tạo từ program order và các cạnh *synchronizes-with*. Nếu A HB B, B phải chịu các ràng buộc nhất định về visibility/ordering do A tạo ra.

Một số quan hệ thực dụng cần nhớ:

1. Các action trong một thread có program order theo mô hình JMM.
2. **Unlock** monitor `m` *synchronizes-with* lần **lock** tiếp theo trên chính monitor `m`.
3. **Ghi** vào biến `volatile` *synchronizes-with* các lần **đọc** sau đó của cùng biến theo synchronization order.
4. Gọi `Thread.start()` HB các action của thread mới. Mọi action của một thread HB việc thread khác phát hiện thread đó đã kết thúc bằng cách như `join()` trả về thành công.
5. Các API `java.util.concurrent` có hợp đồng memory-consistency riêng (ví dụ `CountDownLatch`, `BlockingQueue`, `Future.get()`); đọc đúng tài liệu của primitive đang sử dụng.

**Ví dụ visibility:**

```java
// Đoạn minh họa là các trường/method thuộc cùng class.
private int value;
private volatile boolean ready;

void publish() {
    value = 42;
    ready = true;  // volatile write
}

void consume() {
    if (ready) {   // volatile read
        System.out.println(value);
    }
}
```

Nếu `consume` đọc được `ready == true` từ thao tác publish tương ứng, các ghi trước volatile write (bao gồm `value=42`) được công bố tới luồng đọc theo HB. Tuy nhiên, nếu consumer đọc `ready == false` thì nó không in gì; không có bảo đảm consumer được scheduler chạy *sau* publish. Nếu có thêm ghi vào `value/ready` theo một giao thức khác, phải phân tích lại cụ thể. Đây là đoạn minh họa **không độc lập biên dịch** và không thay thế giao thức phối hợp cho nhiều lần publish.

**Sai lầm quan trọng:** khai báo `volatile int counter` **không khiến `counter++` nguyên tử**. Volatile cung cấp quy tắc visibility/ordering cho các access riêng lẻ, nhưng phép tăng vẫn là chuỗi đọc–tính–ghi; hai thread có thể cùng đọc rồi ghi đè. Khi cần tăng nguyên tử, dùng atomic operation hoặc lock bảo vệ toàn bộ read-modify-write.

**Data-race-free → dễ suy luận hơn:** nếu toàn bộ truy cập chia sẻ gây xung đột được đồng bộ đúng theo JMM, execution được bảo đảm nhất quán theo mô hình tuần tự thích hợp (*sequentially consistent for correctly synchronized programs*). Điều này **không làm lịch chạy thành cố định**; có thể có nhiều thứ tự hợp lệ và nhiều output hợp lệ, nhưng không phá vỡ invariant đã thiết kế.

## 7. Thực hành Java 17+: buộc xuất hiện một lịch mất cập nhật

Ví dụ dưới đây cố tình dùng `CyclicBarrier` để ép **hai thread đều đọc giá trị 0 trước khi bất kỳ thread nào ghi**. Điều này làm lỗi lost update có thể quan sát nhất quán trong bài thực hành; nó **không** ngụ ý mọi lần tăng thiếu đồng bộ đều mất cập nhật.

Phần thứ hai thay bằng `AtomicInteger.incrementAndGet()`. Phần cuối dùng `StringBuffer` (mỗi lần append được đồng bộ) để cho thấy **thứ tự A/B không cố định nhưng dữ liệu không hỏng**.

Tạo file **`InterleavingLab.java`**:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class InterleavingLab {
    private static int counter;

    private static void runPair(Runnable task) throws InterruptedException {
        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();
        first.join();
        second.join();
    }

    private static void awaitBarrier(CyclicBarrier barrier) {
        try {
            barrier.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at barrier", e);
        } catch (BrokenBarrierException e) {
            throw new IllegalStateException("Barrier broken", e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        counter = 0;
        CyclicBarrier bothRead = new CyclicBarrier(2);
        runPair(() -> {
            int snapshot = counter;
            awaitBarrier(bothRead);
            counter = snapshot + 1;
        });
        System.out.println("lostUpdate=" + counter);

        AtomicInteger atomicCounter = new AtomicInteger();
        runPair(() -> atomicCounter.incrementAndGet());
        System.out.println("atomic=" + atomicCounter.get());

        StringBuffer completionOrder = new StringBuffer();
        Thread a = new Thread(() -> completionOrder.append('A'));
        Thread b = new Thread(() -> completionOrder.append('B'));
        a.start();
        b.start();
        a.join();
        b.join();
        System.out.println("order=" + completionOrder);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 InterleavingLab.java
java InterleavingLab
```

Một lần chạy đã xác minh:

```text
lostUpdate=1
atomic=2
order=AB
```

**Những gì có thể khẳng định khi thực thi bình thường:**

- `lostUpdate=1`: hai worker đều đọc `counter=0` rồi chờ nhau ở barrier. Cả hai đều ghi `1`, nên cuối cùng chỉ thấy một lần tăng. Đó là một lịch được ép có kiểm soát.
- `atomic=2`: mỗi `incrementAndGet()` là một phép tăng atomic. Hai phép được áp dụng thành công, `join()` trả về rồi mới đọc, nên tổng là 2.
- Dòng thứ ba là **`order=AB` hoặc `order=BA`**; thứ tự phụ thuộc lịch chạy. `StringBuffer.append` làm từng append an toàn trong bối cảnh này, và `join()` chờ hai thread hoàn thành. Không có bảo đảm bạn sẽ quan sát cả hai thứ tự trên một máy.

**Vì sao cần barrier?** Nếu chỉ viết hai thread cùng `counter++` rồi chạy vài lần, nhiều lần bạn sẽ thấy đúng 2 và tưởng code an toàn. `CyclicBarrier(2)` ép điểm đồng bộ **sau bước đọc, trước bước ghi**, mô phỏng chính lịch gây mất cập nhật. Nó không phải giải pháp sửa biến `counter`, vì ý định ở phần đầu là minh họa lỗi.

**Vì sao dùng `join()`?** Nếu main in kết quả ngay sau hai lệnh `start()`, nó có thể đọc biến trước khi worker chạy xong; đây là một vấn đề ordering bổ sung làm phép thử khó hiểu. `join()` thành công bảo đảm worker kết thúc trước khi main kiểm tra tổng và thiết lập quan hệ HB phù hợp.

**Chú ý giới hạn demo:** vòng `awaitBarrier()` dùng interrupt và broken-barrier exception để báo lỗi môi trường; trong tình huống thread chết/trễ bất thường, các worker có thể không hoàn tất. Không dùng barrier để bù cho một điều kiện đồng bộ nghiệp vụ chưa được định nghĩa. Việc sử dụng `StringBuffer` ở phần ba phục vụ minh họa order; hệ thống thật có thể dùng queue hoặc cấu trúc data phù hợp.

## 8. Làm sao tạo kết quả đúng khi lịch chạy vẫn thay đổi?

### Cách 1: `synchronized` bảo vệ **toàn bộ** thao tác

```java
private int counter;
private final Object guard = new Object();

void increment() {
    synchronized (guard) {
        counter++; // read-modify-write nằm trong cùng critical section
    }
}

int snapshot() {
    synchronized (guard) {
        return counter;
    }
}
```

Đây là các **thành viên minh họa trong một class**. Mọi thread cập nhật/đọc trạng thái được bảo vệ phải tuân thủ cùng monitor `guard`. `synchronized` tạo mutual exclusion và các cạnh HB giữa unlock/lock. Hai lần tăng cho kết quả 2 sau khi cả hai hoàn thành; thread nào lấy monitor trước vẫn có thể khác nhau. Nếu nhiều trường cần invariant chung, bảo vệ toàn bộ nhóm kiểm tra/cập nhật bằng cùng lock.

### Cách 2: `AtomicInteger` cho một state độc lập

```java
private final AtomicInteger counter = new AtomicInteger();

void increment() {
    counter.incrementAndGet();
}

int snapshot() {
    return counter.get();
}
```

Đây là các thành viên minh họa trong một class có import `java.util.concurrent.atomic.AtomicInteger`. `incrementAndGet()` thực hiện phép tăng atomically với memory semantics của volatile read/write tương ứng. Đúng khi mục tiêu là cập nhật một biến nguyên tử. **Không** tự bảo vệ invariant liên quan hai atomic khác nhau, ví dụ “`balanceA + balanceB` phải bất biến” qua hai phép trừ/cộng tách biệt.

### Cách 3: `ReentrantLock` khi cần điều khiển acquisition

```java
private final ReentrantLock lock = new ReentrantLock();
private int counter;

void increment() {
    lock.lock();
    try {
        counter++;
    } finally {
        lock.unlock();
    }
}
```

Đây là đoạn mã thành viên class, cần import `java.util.concurrent.locks.ReentrantLock`. Tương tự `synchronized`, cả thao tác logic được đưa vào critical section. `ReentrantLock` còn có `tryLock()`, `lockInterruptibly()` và `Condition`; dùng khi thiết kế thực sự cần các tính năng đó, không mặc định nhanh hơn intrinsic monitor.

### Cách 4: Thay cách chia sẻ dữ liệu

Không phải bài toán nào cũng cần tất cả worker cùng viết một biến:

- **Thread confinement:** mỗi worker tích lũy kết quả cục bộ, sau `Future.get()`/`join()` thì một nơi gộp kết quả.
- **Immutable data / message passing:** đẩy message qua `BlockingQueue` và chỉ một consumer sở hữu/mutate trạng thái đích.
- **Partition theo key:** mỗi nhóm key được xử lý bởi một owner riêng; cần quy tắc khi phối hợp giữa partitions.
- **Concurrent collections:** dùng thao tác atomic ở cấp API (`putIfAbsent`, `compute`, `merge`) khi cần chính xác một chuyển đổi trạng thái, thay vì nối nhiều lệnh đọc–ghi riêng lẻ.

Mục tiêu là thiết lập một **linearization point** hoặc critical section có thể chỉ ra để biết phép cập nhật logic xảy ra như một đơn vị. “Mỗi method thread-safe” không đồng nghĩa một **chuỗi nhiều method** đã atomic.

## 9. Determinism của kết quả và determinism của thứ tự

**Deterministic result**: với cùng input và điều kiện cam kết của chương trình, output có thể được bảo đảm là như nhau, dù lịch bên trong khác. Ví dụ hai worker cộng những phần khác nhau vào `AtomicInteger` và main đọc sau `join()`.

**Nondeterministic order nhưng hợp lệ**: hai task độc lập lần lượt append A hoặc B vào một buffer đồng bộ; chuỗi có thể `AB` hoặc `BA`. Nếu yêu cầu hệ thống là “có đúng một A và một B”, cả hai đều đúng.

**Nondeterministic result do thiết kế thiếu ordering**: hai worker cùng update shared mutable data không đồng bộ, nên kết quả phụ thuộc lịch và có thể vi phạm invariant.

**Muốn kết quả phải theo thứ tự?** Hãy mô tả ràng buộc rõ ràng:

- A phải hoàn thành trước B xử lý kết quả của A: dùng `Future.get()`, `join()`, `CountDownLatch` hoặc phối hợp thông điệp phù hợp.
- Các sự kiện phải được ghi theo sequence: gán sequence bằng cơ chế nguyên tử/lock, rồi sắp xếp theo sequence (nhớ rằng “thứ tự cấp số” và “thứ tự hiệu ứng bên ngoài hoàn thành” có thể khác nhau).
- Cập nhật cơ sở dữ liệu/tài nguyên ngoài JVM phải có giao dịch, điều kiện ghi, idempotency hoặc cơ chế phối hợp riêng. Java lock trong một process không tự bảo vệ nhiều process.

**Đừng ép thứ tự khi không cần:** đồng bộ quá mức biến chương trình gần như tuần tự, tăng contention và giảm throughput. Thiết kế đồng thời tốt thường **cho phép nhiều lịch**, nhưng bảo đảm mọi lịch được phép đều giữ invariant.

## 10. Kiểm thử race condition theo cách có bằng chứng

Chỉ chạy mã một lần rồi thấy đúng không chứng minh thread safety. Một chiến lược phù hợp:

1. **Xác định invariant.** Ví dụ sau khi N worker hoàn thành đúng K phép tăng mỗi worker, tổng phải là `N × K`; dữ liệu không được âm; mỗi event chỉ được xử lý một lần.
2. **Xác định điểm chia sẻ.** Liệt kê thao tác read/write, nguồn phát sự kiện, lock và quan hệ HB; tách rõ biến độc lập với invariant liên quan nhiều biến.
3. **Tạo điểm giao tranh có kiểm soát.** `CountDownLatch` để đồng thời bắt đầu, `CyclicBarrier` để buộc chạm một checkpoint; đừng dùng `sleep()` như tín hiệu chính xác.
4. **Kiểm tra kết quả và khả năng tiến triển.** Assertion về giá trị, số lần xử lý, data integrity; timeout cho bài test để nhận ra deadlock/hang.
5. **Stress ở cấu hình khác nhau.** Thay số worker, số vòng lặp, số lõi khả dụng, JDK/JIT và tốc độ tải. Chạy nhiều lần để tăng khả năng gặp lịch nguy hiểm; thất bại là bằng chứng bug, thành công không phải chứng minh toán học.
6. **Dùng công cụ đúng chức năng.** [OpenJDK jcstress](https://github.com/openjdk/jcstress) giúp thiết kế litmus tests về các outcome được phép theo JMM. JFR, thread dump và profiler giúp xác định contention/timing; **chúng không tự chứng minh chương trình race-free**.
7. **Khóa hành vi bằng contract.** Nếu dùng một primitive cấp cao, đọc bảo đảm memory consistency của nó; không thay bằng API khác chỉ vì benchmark nhanh hơn.

**Lưu ý benchmark:** số lần chạy hoặc `System.nanoTime()` không đo “mức độ an toàn” của concurrency. Một thực thi sai có thể nhanh hơn vì đã bỏ đồng bộ cần thiết. Chỉ so tốc độ giữa các phiên bản **đều đúng** trên invariant và workload tương đương.

### Ví dụ lịch kiểm tra rất ngắn

Với mô hình `counter++` ban đầu bằng 0:

| Lịch trừu tượng | Thứ tự đọc/ghi | Kết quả mong đợi trong mô hình |
|---|---|---|
| A xong rồi B | `A_R A_W B_R B_W` | `2` |
| Hai thread cùng đọc trước ghi | `A_R B_R A_W B_W` | `1` |
| B xong rồi A | `B_R B_W A_R A_W` | `2` |

Tác dụng của bảng này là **lập luận ra tình huống lỗi**, không dự đoán xác suất lịch hay tập hợp chính xác mọi quan sát dưới mọi tối ưu JMM. Với dữ liệu có race, chỉ mã nguồn “đọc rồi ghi” không đủ làm chứng cứ về visibility.

## 11. Những hiểu lầm phổ biến

1. **“Có hai thread nên chắc chắn chạy song song.”** Concurrency không đồng nghĩa chạy cùng lúc; một CPU cũng có thể xen kẽ tiến trình.
2. **“Gọi `start` của A trước B thì A sẽ chạy trước.”** Sai: `start()` không áp đặt thứ tự completion hay mọi action giữa hai thread.
3. **“`counter++` là một dòng nên atomic.”** Sai: là read-modify-write, có thể mất cập nhật.
4. **“Đặt `volatile` là hết lost update.”** Sai: volatile không gộp phép đọc/tính/ghi thành một phép nguyên tử.
5. **“Chương trình in AB nhiều lần chứng minh không thể in BA.”** Sai: lịch quan sát được phụ thuộc thực thi; absence of evidence không phải cam kết về thứ tự.
6. **“Thứ tự output biến đổi nghĩa là có race bug.”** Sai: order không cố định có thể là yêu cầu hợp lệ, miễn các invariant và visibility được bảo đảm.
7. **“Dùng `ConcurrentHashMap` thì mọi chuỗi contains/put/side effect đã atomic.”** Sai: mỗi lời gọi an toàn riêng lẻ không tạo giao dịch cho cả chuỗi.
8. **“`sleep` hoặc `yield` là synchronization.”** Sai: chúng không tạo HB thích hợp cho các cập nhật chia sẻ chỉ vì đã trì hoãn thread.
9. **“`join` làm một phép tăng trước đó trở nên atomic.”** Sai: join giúp main nhìn thấy kết quả sau khi worker kết thúc, nhưng không ngăn hai worker ghi đè nhau trong lúc chạy.
10. **“Test pass nhiều lần là đủ chứng minh thread safety.”** Sai: chỉ là bằng chứng của những lịch đã được quan sát; cần suy luận invariants, HB và atomicity.
11. **“Lock mọi thứ là tốt nhất.”** Không nhất thiết: lock quá rộng có thể gây contention, deadlock hoặc latency cao; phải bảo vệ chính xác invariant và đo hiệu năng.
12. **“JMM chỉ là scheduler luân phiên các dòng source.”** Sai: JMM quy định visibility/ordering của memory actions; tối ưu và hành vi data race khiến mô hình source-line interleaving không đầy đủ.

## 12. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** A và B mỗi thread gọi `counter++` một lần trên biến `int` chia sẻ bắt đầu bằng 0, không có synchronization. Trong mô hình xen kẽ đọc/ghi tuần tự, có thể được 1 và 2 không?  
**Đáp án:** Có. Cả hai cùng đọc 0 rồi ghi 1 gây lost update; nếu một thread hoàn tất trước khi thread kia đọc thì được 2. Phân tích đầy đủ theo JMM cần xét quan hệ đồng bộ/visibility, không chỉ lịch đọc mã nguồn.

**Câu 2.** Thay `int counter` bằng `volatile int counter` rồi tiếp tục dùng `counter++` có bảo đảm 2 không?  
**Đáp án:** Không. Các access volatile có ordering/visibility, nhưng biểu thức tăng vẫn gồm đọc rồi ghi riêng biệt.

**Câu 3.** Hai task độc lập ghi A/B vào `StringBuffer` và main đọc sau `join()`. Có thể `AB` và `BA` không? Đó có nhất thiết là bug không?  
**Đáp án:** Có hai thứ tự hợp lệ; không phải bug nếu contract chỉ cần đủ hai ký tự mà không yêu cầu thứ tự.

**Câu 4.** Sau khi thread A gọi `start()` trước thread B, có thể B hoàn thành trước A không?  
**Đáp án:** Có. Thứ tự gọi start không quyết định lịch CPU và thời điểm kết thúc.

**Câu 5.** Vì sao gọi `join()` trước khi đọc kết quả từ worker là quan trọng nhưng chưa đủ sửa lost update?  
**Đáp án:** Join tạo trật tự worker hoàn tất trước reader và visibility phù hợp; các cập nhật không atomic giữa hai worker vẫn có thể ghi đè nhau.

**Câu 6.** Một chương trình dùng `ConcurrentHashMap.containsKey`, nếu chưa có thì `put` và gửi email. Tại sao có thể gửi hai email?  
**Đáp án:** Hai thread cùng qua nhánh “chưa có”. Thao tác điều kiện phải được atomically quyết định, và side effect ngoài map cần idempotency/retry policy tương ứng.

**Câu 7.** Nếu một race chỉ xuất hiện trên máy production, có nên thêm log/sleep để tái hiện rồi coi đó là bản sửa không?  
**Đáp án:** Không. Log/sleep thay đổi timing, có thể che mất lỗi. Hãy mô hình hóa invariant, ép checkpoint có kiểm soát và bổ sung synchronization đúng.

**Câu 8.** Cần tăng một bộ đếm độc lập từ nhiều thread: chọn `AtomicInteger` hay `synchronized`?  
**Đáp án:** Cả hai có thể đúng. `AtomicInteger.incrementAndGet` thường gọn cho một phép tăng độc lập; `synchronized` phù hợp khi phải bảo vệ nhiều thao tác/trường như một invariant. Quyết định theo semantics và đo tải thực tế.

## Tài liệu tham khảo

- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): thread actions, data races, `happens-before`, correctly synchronized programs.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start()`, `join()`, semantics và vòng đời thread.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic read-modify-write.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): rendezvous, barrier action và memory consistency.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp các giai đoạn và memory consistency.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thao tác map hỗ trợ concurrent access.
- [OpenJDK jcstress](https://github.com/openjdk/jcstress): bộ công cụ thực nghiệm và litmus tests về tính đồng thời/JMM.

**Kết luận học tập:** đừng cố dự đoán một lịch chạy duy nhất. Hãy xác định mọi kết quả mà contract cho phép, các invariant cần bất biến, và các quan hệ atomicity/happens-before bắt buộc. Khi đó chương trình vẫn được lập lịch linh hoạt mà kết quả vẫn đúng.