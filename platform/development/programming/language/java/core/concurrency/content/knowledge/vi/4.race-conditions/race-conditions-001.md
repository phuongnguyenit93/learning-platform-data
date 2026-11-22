# Shared mutable state tạo ra tranh chấp (race condition) ra sao trong Java?

Khi nhiều thread cùng truy cập **trạng thái có thể thay đổi** (*shared mutable state*), kết quả có thể phụ thuộc vào thứ tự và thời điểm các thao tác xen kẽ. Nếu thiết kế không có quy tắc đồng bộ phù hợp, ứng dụng có thể mất dữ liệu cập nhật, đọc giá trị cũ, phá vỡ điều kiện bất biến hoặc cho ra kết quả khác nhau giữa các lần chạy. Đây là nguồn gốc của nhiều **race condition** trong Java concurrency.

Bài học tập trung vào Java thuần và Java Memory Model (JMM), không phụ thuộc vào framework. Mục tiêu là hiểu **điều kiện nào khiến một dữ liệu trở nên nguy hiểm khi chia sẻ**, vì sao thao tác tưởng chừng đơn giản như `count++` có thể sai, cách chọn công cụ bảo vệ và cách phát hiện lỗi.

## 1. Ba từ khóa: shared, mutable, concurrent

- **Shared (được chia sẻ):** ít nhất hai thread có thể truy cập cùng một vùng trạng thái. Ví dụ, cùng tham chiếu tới một instance `Counter`, một `static` field, một collection hoặc một đối tượng được đưa vào executor.
- **Mutable (có thể thay đổi):** ít nhất một thread có thể sửa trạng thái đó sau khi tạo. Một tham chiếu `final` không đồng nghĩa nội dung object bên trong là bất biến.
- **Concurrent access (truy cập đồng thời về mặt thời gian):** các thread có thể thực hiện thao tác với trạng thái chia sẻ mà không có một thứ tự hoàn toàn được áp đặt bởi chương trình.

Nếu dữ liệu chỉ nằm trong local variable của một thread và không bị chia sẻ qua object/closure, thông thường không có tranh chấp trên chính local variable đó. Nếu một object được chia sẻ nhưng **thực sự bất biến** và đã được công bố an toàn (*safely published*), nhiều thread có thể đọc mà không cần khóa trên mỗi lần đọc.

Ngược lại, nếu ít nhất một thread ghi dữ liệu mà các thread khác cũng đọc hoặc ghi, ta phải xem xét **tính nguyên tử (atomicity), khả năng nhìn thấy (visibility), thứ tự bộ nhớ (ordering)** và tính nhất quán của **nhiều field liên quan**.

### Ví dụ dễ gặp

```java
class Counter {
    int value;

    void increment() {
        value++;
    }
}
```

Đây là **đoạn minh họa chưa có `main`**. Mỗi thread gọi `increment()` trên **cùng một instance** sẽ tranh chấp trường `value`. Ngay cả khi `value++` viết trên một dòng Java, nó không phải thao tác cập nhật nguyên tử.

## 2. Race condition khác data race thế nào?

**Race condition** là lỗi mà tính đúng đắn phụ thuộc vào thứ tự/timing của những hành động có thể xen kẽ. Khái niệm rộng này bao gồm logic kiểm tra rồi hành động, công bố sự kiện sai thứ tự, hoặc cập nhật trạng thái thiếu một giao thức đồng bộ.

**Data race** trong mô hình bộ nhớ Java xuất hiện khi hai thao tác truy cập cùng một biến, ít nhất một là ghi, mà giữa hai thao tác **không có quan hệ happens-before** bảo đảm thứ tự. Các thao tác đọc/ghi thường trên field chia sẻ không được bảo vệ có thể tạo data race.

Hai khái niệm liên quan nhưng **không đồng nhất**:

- `int count` được hai thread tăng bằng `count++` không đồng bộ: vừa là data race vừa thường là race condition dẫn đến **lost update**.
- Một `ConcurrentHashMap` có thể an toàn cho từng `get`/`put`, nhưng hai thread cùng chạy “kiểm tra chưa có key rồi mới thêm” vẫn có **race ở cấp nghiệp vụ**, dù collection bảo vệ các thao tác đơn lẻ.
- Một giao thức cập nhật gồm nhiều biến có thể vẫn sai về logic dù từng biến được khai báo `volatile` hoặc dùng atomic riêng.
- Hai thread chỉ đọc một object bất biến đã được chia sẻ đúng cách không tạo race chỉ vì chạy đồng thời.

**Không phải mọi thay đổi thứ tự đều là lỗi.** Nếu hệ thống cho phép bất kỳ thứ tự nào và mọi kết quả đều đáp ứng hợp đồng, đó là concurrency hợp lệ. Race condition đáng sửa khi thứ tự xen kẽ có thể làm vi phạm yêu cầu.

## 3. `count++` thực chất là read–modify–write

Ở cấp ý nghĩa, `count++` bao gồm ít nhất ba bước:

1. **Read:** đọc giá trị hiện tại `count`.
2. **Compute:** tính `count + 1`.
3. **Write:** ghi kết quả mới trở lại `count`.

Giả sử hai thread A và B cùng thấy `count = 0`:

| Bước | Thread A | Thread B | Giá trị chia sẻ |
| --- | --- | --- | --- |
| 1 | Đọc `0` | | `0` |
| 2 | | Đọc `0` | `0` |
| 3 | Tính `1` và ghi `1` | | `1` |
| 4 | | Tính `1` và ghi `1` | `1` |

Hai lần tăng hợp lệ về nghiệp vụ phải tạo `2`, nhưng cuối cùng chỉ có `1`. Một lần cập nhật đã bị **ghi đè/mất**. Đây là *lost update*.

Không được giả định compiler/JIT/CPU bắt buộc thực thi đúng ba lệnh máy như mô tả. Bảng là mô hình logic của phép read–modify–write: **Java không bảo đảm `count++` trên một field thường là nguyên tử**, nên kết quả sai có thể xảy ra khi hai thread chạy trên cùng dữ liệu.

### Thí nghiệm Java 17: tạo lost update xác định

Đoạn dưới dùng hai `CountDownLatch` để bảo đảm **cả hai thread đọc `0` trước khi bất kỳ thread nào ghi**. Nhờ đó, minh họa không phụ thuộc vào may rủi của scheduler và có stdout cố định.

Lưu thành `LostUpdateExample.java`:

```java
import java.util.concurrent.CountDownLatch;

public class LostUpdateExample {
    static class Counter {
        int value = 0;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int snapshot = counter.value;
            bothRead.countDown();

            try {
                mayWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            counter.value = snapshot + 1;
        };

        Thread a = new Thread(increment, "worker-A");
        Thread b = new Thread(increment, "worker-B");

        a.start();
        b.start();

        bothRead.await();
        mayWrite.countDown();

        a.join();
        b.join();
        System.out.println("Ket qua: " + counter.value);
    }
}
```

Chạy:

```bash
javac LostUpdateExample.java
java LostUpdateExample
```

Stdout khi chạy bình thường, không bị ngắt từ bên ngoài:

```text
Ket qua: 1
```

**Vì sao kết quả ổn định?** Mỗi worker lưu kết quả đọc vào local variable `snapshot` trước khi báo `bothRead.countDown()`. Main chỉ mở cổng ghi `mayWrite.countDown()` sau khi cả hai đọc xong. Như vậy, mỗi worker dùng lại snapshot bằng `0` rồi ghi `1`. `join()` bảo đảm main đợi cả hai kết thúc trước khi in.

**Lưu ý quan trọng về mẫu thí nghiệm:** các latch đã tạo quan hệ đồng bộ đủ để kiểm soát lịch đọc và ghi, nên không dùng chính ví dụ này để khẳng định có data race theo định nghĩa hình thức của JMM trên từng truy cập `value`. Nó **chứng minh sự thất bại của thao tác cập nhật logic** khi tách read và write, ngay cả khi các bước được sắp thứ tự có chủ đích. Trong code thực tế, gọi `counter.value++` từ nhiều thread mà không đồng bộ là tình huống có data race và lost update có thể xuất hiện không dự đoán được. Thí nghiệm trên cố tình ép thứ tự nguy hiểm để minh họa sự cố.

## 4. Những lỗi còn lại: visibility, ordering và invariant

### 4.1. Visibility: thread không nhất thiết thấy bản ghi mới ngay

```java
class WorkerState {
    boolean stopped = false;
}
```

Nếu thread A đổi `stopped = true` trong khi thread B lặp đọc `stopped` mà không có đồng bộ, JMM **không bảo đảm** B quan sát giá trị mới kịp thời, hoặc thậm chí quan sát trước khi vòng lặp kết thúc. JIT và CPU có thể tối ưu, giữ dữ liệu trong register/cache, hoặc thực hiện các thao tác bộ nhớ theo các thứ tự hợp lệ khi thiếu happens-before. Không nên giải thích lỗi bằng cách khẳng định mọi CPU đều “cache mãi không refresh”; điểm cốt lõi là **thiếu bảo đảm của mô hình bộ nhớ**.

Một giải pháp cho **cờ trạng thái đơn giản**:

```java
class WorkerState {
    volatile boolean stopped = false;
}
```

Một phép ghi `volatile` và phép đọc `volatile` tương ứng tạo các bảo đảm visibility và ordering cần thiết. Nhưng `volatile` **không tự làm `count++` nguyên tử**, cũng không bảo vệ một chuỗi điều kiện và cập nhật trên nhiều field.

### 4.2. Ordering và happens-before

JMM cho phép JVM/CPU sắp xếp lại một số thao tác miễn là vẫn tuân thủ các ràng buộc của mô hình bộ nhớ. Không có happens-before, thread khác có thể quan sát trạng thái không đúng với giả định “mọi dòng lệnh đều xuất hiện theo đúng thứ tự trong source”.

**Happens-before** là quan hệ cho phép suy luận về visibility và thứ tự giữa các hành động:

- **Program order:** trong cùng một thread, hành động trước happens-before hành động sau theo thứ tự chương trình.
- **Monitor:** giải phóng monitor bằng `synchronized` happens-before lần lấy monitor đó sau này.
- **Volatile:** ghi vào một field `volatile` happens-before lần đọc tiếp theo của chính field đó theo quy tắc đồng bộ.
- **Start:** gọi `Thread.start()` happens-before các hành động trong thread được khởi động.
- **Termination/join:** các hành động của thread kết thúc happens-before thread khác phát hiện kết thúc thông qua `join()` hoàn thành thành công.
- **Các tiện ích `java.util.concurrent`:** ví dụ, hành động trước `ExecutorService.submit` có bảo đảm truyền đến hành động của task, và hành động task xảy ra trước việc caller lấy kết quả bằng `Future.get()` theo hợp đồng memory consistency của API.

Happens-before có tính **bắc cầu**. Nó khác thứ tự thời gian trên đồng hồ: “A chạy sớm hơn B” chưa đủ để tạo quan hệ happens-before giữa hai thread.

### 4.3. Invariant: cập nhật nhiều field phải thống nhất

Giả sử object lưu `available` và `reserved` với bất biến `available + reserved == total`. Nếu một thread cập nhật từng field riêng lẻ và thread khác đọc xen vào, reader có thể thấy **trạng thái chuyển tiếp** không thỏa bất biến, ngay cả khi các phép ghi từng field riêng biệt nguyên tử.

Các cách bảo vệ phù hợp gồm: giữ **cùng một khóa** cho toàn bộ thao tác cập nhật và đọc snapshot; đưa các field vào một **immutable snapshot object** rồi công bố bằng một reference an toàn; hoặc thiết kế thao tác atomic có đủ dữ liệu để bảo toàn invariant. Dùng hai `AtomicInteger` độc lập không tự khiến một transaction gồm cả hai field trở thành nguyên tử.

## 5. Sửa lost update bằng `synchronized`

`synchronized` tạo mutual exclusion trên một monitor: tại một thời điểm, chỉ một thread sở hữu monitor đó và chạy critical section được bảo vệ. Việc nhả/lấy monitor đồng thời cung cấp quan hệ happens-before cho visibility.

Lưu thành `SynchronizedCounterExample.java`:

```java
public class SynchronizedCounterExample {
    static class Counter {
        private int value = 0;

        synchronized void increment() {
            value++;
        }

        synchronized int getValue() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("Ket qua: " + counter.getValue());
    }
}
```

```bash
javac SynchronizedCounterExample.java
java SynchronizedCounterExample
```

Stdout:

```text
Ket qua: 200000
```

Ở đây **cả hai thread gọi cùng instance `counter`**, nên cùng sử dụng monitor `this` khi gọi `increment()`. Không thể có hai thread cùng thực hiện `value++` trong critical section tại một thời điểm; 200.000 lần tăng được giữ nguyên. `getValue()` cũng dùng khóa đó; `join()` còn bảo đảm main đã đợi worker kết thúc.

**Các điều kiện cần nhớ:**

- Tất cả đường đọc/ghi tới state đang bảo vệ phải tuân theo **cùng một quy tắc khóa**. Nếu code khác vẫn đọc trực tiếp `value` mà không đồng bộ, thiết kế có thể tiếp tục sai.
- `synchronized` trên **hai instance khác nhau** là hai monitor khác nhau. Không bảo vệ được một `static` mutable field chung nếu mỗi thread khóa một object riêng.
- Hạn chế critical section: không giữ khóa khi gọi HTTP/DB, `sleep` hoặc chờ tác vụ khác nếu không cần; khóa lâu gây contention, latency, có thể dẫn tới deadlock.
- `synchronized` hỗ trợ reentrancy; ra khỏi khối dù ném exception cũng tự nhả monitor, nhưng trạng thái nghiệp vụ đã cập nhật một phần vẫn có thể cần xử lý.

## 6. Sửa counter đơn lẻ bằng `AtomicInteger`

Khi state cần bảo vệ chỉ là một phép tăng/giảm hoặc compare-and-set đơn giản, `AtomicInteger` cung cấp các thao tác cập nhật nguyên tử với memory semantics được quy định, thường phù hợp hơn một monitor do ta tự quản lý.

Lưu thành `AtomicCounterExample.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterExample {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("Ket qua: " + count.get());
    }
}
```

```bash
javac AtomicCounterExample.java
java AtomicCounterExample
```

Stdout:

```text
Ket qua: 200000
```

`incrementAndGet()` thực hiện phép tăng nguyên tử; mỗi lần tăng hợp lệ được tính đúng một lần. Dưới tranh chấp, triển khai có thể phải thử lại cập nhật. `AtomicInteger` không khiến cả một chuỗi “đọc giá trị → gọi API → ghi trạng thái khác” trở thành atomic transaction.

**`volatile int value; value++;` vẫn sai** vì `volatile` bảo đảm visibility/ordering cho từng truy cập field, không gộp read–modify–write thành một hành động nguyên tử.

### `LongAdder` có hợp lý hơn?

Khi rất nhiều thread cùng cộng một bộ đếm thống kê, `LongAdder` có thể cải thiện throughput dưới contention bằng cách phân tán cập nhật. Tuy nhiên, `sum()` **không phải snapshot nguyên tử** đối với các cập nhật đang đồng thời. Dùng nó cho metrics/counters chịu tải cao khi không cần giá trị chính xác tuyến tính hóa tại mọi thời điểm; với điều kiện nghiệp vụ cần “nếu số dư đủ thì trừ”, `LongAdder` không phải giải pháp.

## 7. `Lock`, `ReentrantLock` và điều kiện đồng bộ

`java.util.concurrent.locks.ReentrantLock` có thể thay monitor nội tại khi cần `tryLock`, timeout, khóa interruptible hoặc nhiều `Condition`. Nó cũng cần một quy tắc dùng **cùng lock** cho mọi truy cập cùng state.

Đoạn mã minh họa (không phải chương trình độc lập):

```java
private final ReentrantLock lock = new ReentrantLock();
private int balance = 100;

public boolean withdraw(int amount) {
    if (amount < 0) throw new IllegalArgumentException();
    lock.lock();
    try {
        if (balance < amount) return false;
        balance -= amount;
        return true;
    } finally {
        lock.unlock();
    }
}
```

Thêm import `java.util.concurrent.locks.ReentrantLock` và đặt các field/phương thức trong một class. Điều kiện kiểm tra và việc trừ tiền **phải nằm trong cùng critical section**. Nếu đưa `if (balance < amount)` ra ngoài khóa, hai thread có thể cùng thấy đủ tiền rồi cùng rút.

Với `ReentrantLock`, nhất thiết mở khóa trong `finally`; quên `unlock()` có thể làm thread khác đợi vô hạn. Nếu sử dụng nhiều lock, quy định thứ tự lấy lock thống nhất để giảm nguy cơ deadlock.

## 8. Một collection thread-safe vẫn có thể có race ở cấp nghiệp vụ

Xem ý tưởng sau:

```java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
```

Ngay cả khi `map` là `ConcurrentHashMap`, hai thread vẫn có thể cùng quan sát key chưa tồn tại rồi cùng tính `createValue()`, sau đó ghi đè kết quả của nhau. **Mỗi thao tác riêng an toàn, chuỗi thao tác lại chưa atomic.**

Nếu mục tiêu là tính giá trị theo key khi chưa có, hãy cân nhắc:

```java
Value value = map.computeIfAbsent(key, k -> createValue());
```

Các snippet chỉ minh họa; giả định `map` có kiểu `ConcurrentHashMap<Key, Value>` và `createValue()` trả `Value` hợp lệ. `computeIfAbsent` của `ConcurrentHashMap` thực hiện thao tác cập nhật tương ứng theo bảo đảm atomic của API; hàm mapping nên ngắn, không gây recursion cập nhật cùng map và tránh side effect khó lặp lại. Nếu việc tạo giá trị đòi hỏi gọi mạng/DB dài hoặc tạo side effect bên ngoài, phải thiết kế cẩn thận về khóa, lỗi, retry và idempotency.

Các trường hợp tương tự cần thao tác atomic có chủ đích:

- `if (!list.contains(item)) list.add(item)`: check-then-act có thể trùng phần tử dù dùng `Collections.synchronizedList` mà không giữ khóa quanh cả chuỗi.
- `if (stock > 0) stock--`: kiểm tra và giảm tồn kho phải thống nhất; chỉ `volatile` không đủ.
- `map.get(key)` rồi `map.put(key, transformed)`: là read–modify–write; ưu tiên `compute`/`merge` khi đúng semantics.
- Trạng thái order/booking nhiều bước: một phép atomic trên một field chưa đủ giữ toàn bộ invariant.

## 9. Các cách giảm hoặc tránh shared mutable state từ thiết kế

### 9.1. Thread confinement: không chia sẻ dữ liệu cần sửa

Dữ liệu chỉ thuộc một thread hoặc một task, các phép cập nhật nội bộ không tranh với thread khác:

```java
Runnable job = () -> {
    int localCount = 0;
    for (int i = 0; i < 10; i++) {
        localCount++;
    }
    System.out.println(localCount);
};
```

Đây là đoạn minh họa chưa có `main`. Nếu mỗi task có một `localCount` riêng thì không có data race trên biến đó. **Nhưng các object mà local variable tham chiếu tới vẫn có thể bị chia sẻ**; local reference không biến object chia sẻ thành private.

### 9.2. Immutability và defensive copying

Ưu tiên giá trị bất biến: record với các thành phần bất biến, `String`, cấu trúc value object, immutable collection hoặc immutable snapshot. `List.copyOf(source)` tạo danh sách không cho sửa cấu trúc qua reference được trả về, nhưng **không deep-copy các phần tử mutable bên trong**. `final List<Item>` cũng chỉ ngăn gán lại reference, không ngăn thay đổi list.

Đối tượng bất biến vẫn cần được **công bố an toàn** khi đưa từ thread tạo sang thread dùng. Không để tham chiếu `this` “thoát ra ngoài” constructor trước khi xây dựng hoàn tất; dùng cơ chế chuyển giao có happens-before (queue, synchronized, volatile reference, concurrent collection, hoặc fork/join theo hợp đồng API).

### 9.3. Message passing, ownership và partition

Chia state theo key/shard, giao mỗi phần cho một worker quản lý; các thread khác gửi message qua `BlockingQueue` thay vì cùng sửa một object. Thiết kế này đổi bài toán “ai giữ lock?” thành “ai sở hữu state và message nào được phép cập nhật?”. Mọi giới hạn queue, xử lý shutdown và error recovery vẫn cần được thiết kế.

### 9.4. Immutable snapshot thay cho nhiều field mutable

Nếu UI/readers cần quan sát một nhóm giá trị nhất quán, có thể tạo object snapshot bất biến mới và cập nhật **một reference** với `volatile` hoặc `AtomicReference`. Reader thấy hoặc snapshot trước, hoặc snapshot sau, thay vì trộn hai phần. Khi có nhiều writer cần sửa dựa trên giá trị cũ, `AtomicReference.compareAndSet` hoặc khóa vẫn cần để tránh mất cập nhật.

## 10. Chọn giải pháp cho từng dạng tranh chấp

| Yêu cầu | Giải pháp thường hợp lý | Không nên hiểu nhầm |
| --- | --- | --- |
| Một flag được đọc bởi thread khác | `volatile boolean`, `AtomicBoolean` hoặc cơ chế đồng bộ cao hơn | `volatile` không tự tạo cơ chế chờ/đánh thức hoặc lifecycle |
| Counter số lượng chính xác | `AtomicInteger`/`AtomicLong` hoặc `synchronized` | `volatile int++` không an toàn |
| Counter thống kê rất nhiều writer | `LongAdder` nếu chấp nhận `sum()` không snapshot nguyên tử | Không dùng cho các điều kiện tiền tệ/tồn kho đòi hỏi quyết định atomic |
| Điều kiện và cập nhật trên nhiều field | `synchronized` / `Lock` quanh toàn bộ invariant | Mỗi field là một atomic riêng chưa đủ |
| Map nhiều thread cập nhật từng key | `ConcurrentHashMap` với `compute`, `merge`, `putIfAbsent` đúng hợp đồng | `containsKey` + `put` riêng lẻ vẫn có race |
| Producer/consumer truyền dữ liệu | `BlockingQueue` hoặc cơ chế message passing | Queue thread-safe không tự bảo đảm mọi điều kiện nghiệp vụ |
| Nhiều reader, ít writer và snapshot | Immutable object + safe publication | `final` reference không biến nội dung mutable thành immutable |
| Mỗi task chỉ có dữ liệu cục bộ | Thread confinement/task ownership | Tránh vô tình đưa reference mutable cho thread khác |

Không có “khóa tốt nhất” cho mọi tình huống. Chọn theo **invariant cần bảo vệ**, số writer, mức contention, yêu cầu fairness, latency, khả năng block và cấu trúc code. Sau khi chọn công cụ, hãy chỉ rõ **mọi đường truy cập nào phải tham gia cùng quy tắc**.

## 11. Hai tầng an toàn: atomic operation và atomic workflow

Ví dụ giao dịch trừ tiền:

```java
if (balance.get() >= amount) {
    balance.addAndGet(-amount);
}
```

Giả sử `balance` là `AtomicInteger`; hai thao tác `get` và `addAndGet` đều atomic riêng lẻ, nhưng **cả chuỗi không phải một thao tác nguyên tử**. Hai thread có thể cùng thấy đủ tiền và cùng trừ, khiến số dư âm.

Nếu invariant chỉ dựa trên một số nguyên, có thể dùng vòng compare-and-set (CAS):

```java
boolean withdraw(AtomicInteger balance, int amount) {
    if (amount < 0) throw new IllegalArgumentException();
    while (true) {
        int current = balance.get();
        if (current < amount) return false;
        if (balance.compareAndSet(current, current - amount)) {
            return true;
        }
    }
}
```

Đây là snippet Java 17+ dùng import `java.util.concurrent.atomic.AtomicInteger`, cần đặt trong class. `compareAndSet` chỉ thành công nếu giá trị hiện tại còn đúng `current`; nếu thread khác đã thay đổi, vòng lặp đọc lại và kiểm tra điều kiện. Trên contention cao vòng lặp có thể phải retry nhiều lần.

**Ranh giới của CAS:** nếu transaction liên quan nhiều object, kết nối DB, gọi HTTP hoặc invariant phức tạp, một CAS trên `AtomicInteger` không thể bao trùm tất cả. Nếu function cập nhật trong vòng retry có side effect bên ngoài, nó có thể chạy nhiều lần dẫn đến tác dụng phụ bị lặp. Phải quản lý transaction, idempotency và failure semantics ở tầng thích hợp.

## 12. Happens-before và “đồng bộ đúng chỗ”

Một số suy luận thường bị hiểu sai:

**“Tôi đã gọi `join()` ở cuối, vậy các cập nhật cùng lúc chắc chắn đúng.”** `join()` giúp thread gọi quan sát kết quả sau khi worker kết thúc. Nó **không sửa những lost update xảy ra khi worker tranh nhau sửa state trước đó**.

**“Có `Thread.sleep(10)` giữa hai dòng thì chắc không race.”** Delay không tạo hợp đồng đồng bộ; một lịch chạy khác, máy nhanh/chậm khác hoặc JIT khác sẽ làm kết quả thay đổi.

**“Đặt một field `volatile` thì toàn bộ object thread-safe.”** `volatile` chỉ áp dụng semantics lên trường được khai báo. Tính nguyên tử của các cập nhật ghép và invariant nhiều field vẫn cần khóa, CAS trên snapshot hoặc cơ chế riêng.

**“Tôi khóa trong writer, reader chỉ đọc nên không cần khóa.”** Nếu reader đọc field thường mà không tham gia đồng bộ hoặc cơ chế công bố tương đương, reader có thể thấy dữ liệu cũ hoặc snapshot không nhất quán.

**“Đổi `HashMap` sang `ConcurrentHashMap` là mọi nghiệp vụ đúng.”** Collection bảo đảm theo phạm vi các operation của nó. Giao thức check–then–act hay transaction nhiều map vẫn cần atomic workflow.

**“Race chỉ xảy ra khi thật sự chạy song song trên nhiều CPU.”** Ngay trên một core, scheduler có thể ngắt sau read rồi chuyển sang thread khác, tạo interleaving sai. Parallelism làm interleaving phong phú hơn, nhưng không phải điều kiện cần của race.

## 13. Kiểm thử và tìm race condition

Race condition thường khó tái hiện vì phụ thuộc lịch chạy; một test chạy đúng 1.000 lần **không chứng minh** không có race.

1. **Chỉ ra state được chia sẻ:** field/static field, collection, cache, config object, object đưa vào executor, callback; xác định ai đọc và ai ghi.
2. **Viết invariant:** `completed <= submitted`, `balance >= 0`, `sum == expected`, “mỗi key chỉ được khởi tạo một lần”, “hai field luôn tương ứng cùng phiên bản”.
3. **Kiểm tra mọi lối truy cập:** field thường có được dùng ngoài lock không? Lock có cùng instance không? Có check–then–act hoặc nhiều atomic riêng lẻ không?
4. **Thiết kế test có phối hợp:** `CountDownLatch`, `CyclicBarrier`, `Phaser` giúp đồng thời kích hoạt các nhánh nhạy cảm. Dùng timeouts để test không treo nếu có lỗi.
5. **Chạy stress dưới tải và trên nhiều cấu hình:** nhiều thread, task count lớn, scheduler/CPU khác nhau, lặp lại trong môi trường CI. Theo dõi invariant và log lỗi, không chỉ stdout rời rạc.
6. **Dùng JFR/profiling/thread dumps để tìm lock contention và deadlock:** các công cụ này hữu ích cho tranh chấp và treo nhưng **một thread dump không chứng minh có hoặc không có data race**.
7. **Review theo JMM và hợp đồng API:** thread-safe collection, atomic classes, publication, interrupt/cancellation, visibility. Kiểm thử không thay thế lập luận về happens-before.

### Khi debug, hỏi cụ thể

- Chính xác **biến/object nào được chia sẻ**? Cùng instance hay mỗi thread có bản sao?
- Thread nào ghi? Thread nào đọc? Có ít nhất một truy cập không được bao trong cùng cơ chế đồng bộ?
- Có bước “đọc điều kiện → tính toán → ghi” bị tách rời không?
- Các thread dựa vào thời gian (`sleep`, retry) hay dựa vào một tín hiệu có hợp đồng happens-before?
- Các thao tác cập nhật có thể bị retry? Có side effect không thể chạy hai lần?
- Một giải pháp đã xóa race nhưng gây lock contention, deadlock hay throughput kém chưa?

## 14. Các sai lầm thường gặp

| Sai lầm | Lỗi có thể xảy ra | Cách sửa |
| --- | --- | --- |
| Nhiều thread cập nhật `int count` bằng `count++` | Lost update | `AtomicInteger.incrementAndGet` hoặc khóa chung |
| Khai báo `volatile int count` rồi tiếp tục `count++` | Vẫn lost update | Dùng atomic read–modify–write |
| Mỗi thread đồng bộ trên object khác nhau | Không có mutual exclusion chung | Sở hữu và chia sẻ đúng cùng lock bảo vệ state |
| Writer dùng `synchronized`, reader không dùng | Visibility/invariant không bảo đảm | Reader tham gia cùng giao thức hoặc đọc snapshot an toàn |
| `if (map.get(k) == null) map.put(k, ...)` | Hai thread cùng tạo/ghi đè | Dùng operation atomic phù hợp như `computeIfAbsent` |
| Dùng `Thread.sleep` để “đợi thread kia ghi xong” | Flaky, không có happens-before cần thiết | Dùng `join`, latch, future, queue |
| Chia sẻ mutable object qua field `final` rồi nghĩ nó bất biến | Các field bên trong vẫn bị sửa đồng thời | Immutable design hoặc đồng bộ rõ ràng |
| Khóa rộng bao gồm I/O chậm | Contention, latency hoặc deadlock | Giảm phạm vi khóa, thiết kế ownership và invariant |
| CAS loop chứa thao tác gọi API có side effect | Retry có thể lặp side effect | Tách hiệu ứng khỏi retry, dùng transaction/idempotency |
| Chỉ test bằng một lịch chạy có sẵn | Race ít gặp bị bỏ sót | Stress test + lập luận theo JMM |
| Dùng nhiều `AtomicInteger` cho một invariant nhiều field | Snapshot giữa các field không nhất quán | Khóa chung hoặc immutable state snapshot được công bố atomic |
| Tin “đổi thành thread-safe collection” là xong | Race ở workflow vẫn còn | Chọn operation atomic ở mức nghiệp vụ |

## 15. Bài tập tự kiểm tra

**Câu 1.** Hai thread chỉ đọc cùng một `List<String>` đã tạo xong, nhưng không ai thay đổi list. Có nhất thiết xảy ra race?  
Không; nếu list được công bố an toàn và các phần tử/collection không bị sửa sau đó, các thao tác đọc đồng thời có thể an toàn. Kiểm tra cả việc publication, vì “không sửa sau khi tạo” chưa thay thế việc đưa reference sang thread khác đúng cách.

**Câu 2.** `volatile int x` có làm phép `x = x + 1` atomic?  
Không. Phép đó vẫn là read–modify–write với khả năng hai thread dùng cùng giá trị cũ.

**Câu 3.** Chỉ một writer, nhiều reader thì cần đồng bộ không?  
Có thể cần. Reader phải nhìn thấy thay đổi đúng thời điểm và thấy invariant nhất quán. Tùy yêu cầu, dùng `volatile`, khóa hoặc immutable snapshot.

**Câu 4.** `AtomicInteger` có đảm bảo “số dư không âm” khi hai thread cùng kiểm tra `get()` rồi trừ bằng `addAndGet(-amount)`?  
Không. Hai operation atomic riêng lẻ không bảo vệ điều kiện. Cần compare-and-set loop hoặc khóa quanh cả chuỗi.

**Câu 5.** Vì sao ví dụ `LostUpdateExample` in đúng `1` ở mọi lần chạy bình thường?  
Vì cả hai thread đều bị buộc đọc giá trị `0` rồi mới được ghi; lần ghi sau ghi đè giá trị `1` bằng chính `1`. Cổng đồng bộ khiến ví dụ xác định, không phụ thuộc xác suất interleaving.

**Câu 6.** Có thể giải quyết race chỉ bằng cách tăng thread pool hoặc đổi sang virtual thread?  
Không. Thay đổi mô hình lập lịch có thể làm race xuất hiện thường xuyên hoặc ít thường xuyên hơn nhưng không làm giao thức dữ liệu trở nên an toàn. Virtual thread và platform thread cùng cần tuân thủ JMM.

## 16. Checklist thực hành

Trước khi chia sẻ một mutable object cho nhiều thread, hãy trả lời:

- **Ai sở hữu dữ liệu?** Có thể tránh chia sẻ bằng confinement, immutable snapshots hoặc queue/message passing không?
- **Dữ liệu nào cần atomicity?** Một field, một số nguyên, một map entry hay toàn bộ invariant nhiều field?
- **Giao thức happens-before là gì?** `synchronized`, `volatile`, `Lock`, atomic, thread-safe queue, `Future` hoặc safe publication?
- **Tất cả reader/writer có tham gia cùng giao thức?** Có đường code đọc trực tiếp không khóa, hoặc dùng một khóa khác không?
- **Workflow có check–then–act hoặc read–modify–write không?** Có API atomic cho toàn bộ thao tác hay phải dùng lock/CAS?
- **Test có xác minh invariant và nhiều interleaving không?** Có timeout, log ngữ cảnh và quan sát lock contention không?
- **Giải pháp có tác dụng phụ nào?** Lock quá rộng, deadlock, retry lặp side effect, memory pressure hoặc throughput giảm?

**Ghi nhớ:** vấn đề không nằm ở việc nhiều thread cùng tồn tại, mà ở chỗ **nhiều thread có thể đọc/ghi cùng trạng thái có thể thay đổi mà không có quy tắc phối hợp đủ mạnh cho invariant cần giữ**. Xóa chia sẻ khi có thể; nếu buộc phải chia sẻ, chọn một cơ chế đồng bộ có phạm vi rõ ràng và chứng minh mọi đường truy cập đều tuân thủ.