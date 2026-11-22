# Giới hạn của volatile với compound actions trong Java

Một field `volatile` có quy tắc đọc/ghi đặc biệt trong Java Memory Model (JMM): những thread khác có thể dựa vào cơ chế **visibility** và **ordering** để quan sát dữ liệu được công bố theo đúng giao thức. Tuy nhiên, `volatile` **không biến nhiều bước thành một thao tác nguyên tử**. Vì thế, dù `counter` được khai báo `volatile`, các biểu thức `counter++`, `counter += 2` hay `if (!claimed) claimed = true` vẫn có thể cho kết quả sai khi nhiều thread cùng chạy.

Bài này nói về **Java concurrency nói chung, trên Java 17+**, tập trung vào các giới hạn của volatile khi dùng với **compound actions** (thao tác ghép). Các cơ chế riêng của Spring nằm ngoài phạm vi.

Mục tiêu: hiểu đúng bảo đảm của volatile; nhận diện read–modify–write, check–then–act và bất biến nhiều field; chứng minh lost update; chọn Atomic*/CAS, `synchronized` hoặc `Lock` đúng yêu cầu; kiểm chứng bằng ví dụ và test có kiểm soát.

## 1. Volatile bảo đảm visibility và ordering, không bảo đảm compound atomicity

Cần tách ba khái niệm:

| Thuộc tính | Câu hỏi cần trả lời | Cơ chế liên quan |
| --- | --- | --- |
| **Visibility** | B có nhìn thấy ghi của A sau điểm công bố đúng không? | Volatile write/read, lock/unlock, join, Future... |
| **Ordering** | A và B có cạnh happens-before nào không? | Program order, synchronizes-with, bắc cầu |
| **Atomicity** | Một nhóm bước có được thực hiện như một đơn vị không bị thread khác xen vào không? | Atomic RMW, CAS, khóa, transaction phù hợp |

Một lần **ghi vào field volatile** *synchronizes-with* các lần **đọc field volatile đó tiếp sau theo synchronization order**. Nhờ program order và tính bắc cầu, thao tác ghi dữ liệu trước lần công bố có thể happens-before việc đọc dữ liệu sau khi reader thấy trạng thái đã được công bố.

Các phép **đọc/ghi đơn lẻ trên volatile field** có ngữ nghĩa nguyên tử của chính phép truy cập (kể cả `volatile long` và `volatile double`); điều đó khác hẳn với việc nguyên tử hóa một câu lệnh gồm đọc, tính toán rồi ghi. Volatile cũng không tự khóa một đoạn code.

### Ví dụ sử dụng đúng volatile để công bố dữ liệu

~~~java
// VolatilePublicationDemo.java
public class VolatilePublicationDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("Payload: " + payload);
        });

        reader.start();
        payload = 42;
        ready = true;
        reader.join();
    }
}
~~~

~~~bash
javac VolatilePublicationDemo.java
java VolatilePublicationDemo
~~~

Khi các thread được lập lịch và chương trình hoàn thành bình thường, stdout:

~~~text
Payload: 42
~~~

Main thực hiện `payload = 42` trước `ready = true`. Reader quan sát `ready == true` qua volatile read rồi mới đọc `payload`. Chuỗi **program order → volatile synchronizes-with → program order**, kết hợp tính bắc cầu của happens-before, bảo đảm reader thấy dữ liệu đã công bố. Không có ghi cạnh tranh khác vào `payload`.

`Thread.onSpinWait()` chỉ là gợi ý cho vòng spin, **không tạo thêm cạnh đồng bộ** và không bảo đảm fairness/liveness. Ví dụ dùng spin để làm rõ JMM; ứng dụng thực tế thường dùng latch, queue hoặc future để tránh chờ bận.

## 2. Compound action gồm những gì?

**Compound action** là thao tác logic được xây từ nhiều hành động mà bất biến yêu cầu phải nhất quán. Các mẫu chính:

- **Read–modify–write:** `counter++`, `count += delta`, `balance -= amount`. Cần đọc giá trị, tính giá trị mới, rồi ghi.
- **Check–then–act:** `if (!reserved) { reserved = true; }`. Điều kiện có thể đổi sau khi kiểm tra và trước khi hành động.
- **Check–update:** `if (stock > 0) stock--;`. Hai thread có thể cùng thấy còn một món rồi cùng bán.
- **Cập nhật nhiều field:** `available--` và `sold++` cần giữ bất biến `available + sold == capacity`.
- **Read–compute–replace:** đọc một object/version, tính object mới rồi gán lại reference. Bản thân phép gán reference có thể atomic, nhưng chuỗi này vẫn có thể lost update.

Một lỗi phổ biến là thấy từng lần đọc/ghi volatile có bảo đảm visibility rồi suy ra **toàn bộ câu lệnh** đã an toàn. Hãy tìm **điểm nguyên tử của cả thao tác logic**, chứ không chỉ của field.

## 3. Volatile counter++ vẫn có lost update

Giả sử `counter = 0`. Hai thread T1 và T2 đều muốn tăng đúng một lần:

| Thứ tự logic | T1 | T2 |
| --- | --- | --- |
| 1 | Đọc `counter = 0` | |
| 2 | | Đọc `counter = 0` |
| 3 | Tính `0 + 1` | |
| 4 | | Tính `0 + 1` |
| 5 | Ghi volatile `counter = 1` | |
| 6 | | Ghi volatile `counter = 1` |

Kết quả **1 thay vì 2**. Mỗi truy cập volatile đơn lẻ vẫn đúng JMM; lỗi là hai thread đều tính từ phiên bản cũ rồi ghi đè nhau.

### Ví dụ Java 17+ tái hiện xác định

Dùng `CountDownLatch` chỉ để điều phối cho **cả hai thread đều đọc trước khi ghi**:

~~~java
// VolatileLostUpdateDemo.java
import java.util.concurrent.CountDownLatch;

public class VolatileLostUpdateDemo {
    private static volatile int counter;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int oldValue = counter;
            bothRead.countDown();
            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            counter = oldValue + 1;
        };

        Thread a = new Thread(increment);
        Thread b = new Thread(increment);
        a.start();
        b.start();

        bothRead.await();
        allowWrite.countDown();
        a.join();
        b.join();

        System.out.println("Expected: 2");
        System.out.println("Actual: " + counter);
    }
}
~~~

~~~bash
javac VolatileLostUpdateDemo.java
java VolatileLostUpdateDemo
~~~

Stdout:

~~~text
Expected: 2
Actual: 1
~~~

`bothRead.await()` chỉ hoàn thành khi cả hai thread đã lưu `0` trong `oldValue`. Sau đó, cả hai ghi `oldValue + 1`, tức `1`. Main `join()` cả hai rồi mới đọc kết quả. Trong code thật không có latch ép lịch chạy, lỗi có thể hiếm gặp; hiếm gặp **không phải an toàn**.

Tương tự, `++counter`, `counter += 3` hoặc `counter = counter * 2` đều có read–modify–write. `++counter` và `counter++` khác giá trị của biểu thức, nhưng **không khác về tính nguyên tử**.

## 4. Dùng AtomicInteger cho một phép read–modify–write nguyên tử

`AtomicInteger` cung cấp `incrementAndGet()`, `getAndIncrement()`, `addAndGet(delta)`, `compareAndSet(expected, update)` và các phương thức cập nhật nguyên tử khác.

~~~java
// AtomicCounterDemo.java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable increment = () -> count.incrementAndGet();
        Thread a = new Thread(increment);
        Thread b = new Thread(increment);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Atomic count: " + count.get());
    }
}
~~~

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Stdout:

~~~text
Atomic count: 2
~~~

Hai lần tăng được thực hiện như hai cập nhật nguyên tử trên **cùng instance** `AtomicInteger`. `incrementAndGet()` trả giá trị **sau tăng**; `getAndIncrement()` trả giá trị **trước tăng**. Chọn đúng phương thức theo nhu cầu.

**Tuy nhiên, các phương thức atomic riêng lẻ không làm mọi chuỗi gọi của bạn nguyên tử.** Ví dụ:

~~~java
// Mã minh họa: seats là AtomicInteger đã khai báo.
if (seats.get() > 0) {
    seats.decrementAndGet();
}
~~~

Nếu `seats == 1`, cả hai thread có thể cùng đọc `1` và đều giảm, khiến kết quả `-1`. `get()` và `decrementAndGet()` đều có bảo đảm riêng nhưng điều kiện **không được gắn nguyên tử với update**.

Một CAS loop phù hợp hơn nếu chỉ cần quản lý số ghế:

~~~java
// Phương thức minh họa trong class có field AtomicInteger seats.
boolean reserve() {
    while (true) {
        int current = seats.get();
        if (current <= 0) {
            return false;
        }
        if (seats.compareAndSet(current, current - 1)) {
            return true;
        }
        // Có writer khác vừa thay đổi: đọc lại, kiểm tra lại.
    }
}
~~~

`compareAndSet` kiểm tra giá trị dự kiến và ghi giá trị mới **trong một bước nguyên tử**. Nếu thất bại do cạnh tranh, đoạn code đọc lại trạng thái và đánh giá lại điều kiện. Đây là **mã minh họa**, không phải file Java chạy độc lập.

## 5. Check–then–act: volatile boolean không đủ để claim một lần

Ví dụ chỉ cho một thread nhận một tài nguyên:

~~~java
// Minh họa trong class, chưa thread-safe về mặt logic:
private volatile boolean claimed;

boolean claim() {
    if (!claimed) {
        claimed = true;
        return true;
    }
    return false;
}
~~~

Có lịch chạy T1 đọc false, T2 cũng đọc false; sau đó cả hai cùng ghi true và cùng trả true. Không cần lỗi cache: tại **thời điểm đọc**, cả hai thực sự có thể đọc false.

Dùng `AtomicBoolean.compareAndSet(false, true)`:

~~~java
// AtomicClaimDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicClaimDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicBoolean claimed = new AtomicBoolean();
        AtomicInteger winners = new AtomicInteger();
        CountDownLatch begin = new CountDownLatch(1);

        Runnable attempt = () -> {
            try {
                begin.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (claimed.compareAndSet(false, true)) {
                winners.incrementAndGet();
            }
        };

        Thread a = new Thread(attempt);
        Thread b = new Thread(attempt);
        a.start();
        b.start();
        begin.countDown();
        a.join();
        b.join();

        System.out.println("Successful claims: " + winners.get());
    }
}
~~~

~~~bash
javac AtomicClaimDemo.java
java AtomicClaimDemo
~~~

Stdout:

~~~text
Successful claims: 1
~~~

Ở đây điểm nguyên tử là việc **đọc trạng thái hiện tại và chuyển false → true** như một thao tác. Chỉ một CAS thắng khi không có code khác đặt lại trạng thái. Khi có reset, cần thiết kế thêm hợp đồng sở hữu/trạng thái và tránh ABA nếu giá trị có thể thay đổi rồi quay lại như ban đầu.

## 6. Nhiều field: volatile không tạo snapshot hay transaction

Giả sử có hai field:

~~~java
// Mã minh họa trong class:
private volatile int available = 10;
private volatile int sold;

// Writer:
available--;
sold++;

// Reader:
int a = available;
int s = sold;
~~~

Bất biến cần giữ là `available + sold == 10`. Reader có thể nhìn thấy `available == 9`, `sold == 0` ở giữa hai lần ghi. Ngoài ra, nếu nhiều writer cùng dùng `--` và `++`, còn có khả năng mất cập nhật.

Một giải pháp trực tiếp là đặt **đoạn kiểm tra–cập nhật và đoạn đọc snapshot** dưới **cùng monitor**:

~~~java
// SynchronizedInventoryDemo.java
public class SynchronizedInventoryDemo {
    static class Inventory {
        private int available = 1;
        private int sold;

        synchronized boolean sell() {
            if (available <= 0) {
                return false;
            }
            available--;
            sold++;
            return true;
        }

        synchronized String snapshot() {
            return "Available: " + available + ", sold: " + sold;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory stock = new Inventory();

        Thread a = new Thread(stock::sell);
        Thread b = new Thread(stock::sell);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println(stock.snapshot());
    }
}
~~~

~~~bash
javac SynchronizedInventoryDemo.java
java SynchronizedInventoryDemo
~~~

Stdout:

~~~text
Available: 0, sold: 1
~~~

Mỗi `sell()` lấy monitor của **cùng object `stock`** và bảo vệ toàn bộ check–update. `snapshot()` dùng monitor đó, vì thế không thể đọc ở giữa hai lần cập nhật. Các field không cần volatile nếu mọi truy cập chia sẻ đều tuân thủ đúng giao thức.

Với `ReentrantLock`, có thể tổ chức tương tự, nhưng phải giải phóng khóa trong `finally` sau khi lấy khóa thành công:

~~~java
// Mã minh họa: lock là ReentrantLock đã khai báo, các field đã khai báo.
lock.lock();
try {
    if (available > 0) {
        available--;
        sold++;
    }
} finally {
    lock.unlock();
}
~~~

Khóa đem lại cả mutual exclusion và hiệu ứng bộ nhớ lock/unlock. **Mọi đường đọc và ghi liên quan đến bất biến phải dùng cùng cơ chế.** Chỉ khóa writer rồi để reader đọc hai field riêng ngoài khóa vẫn có thể quan sát trạng thái trung gian.

## 7. Volatile reference: công bố snapshot khác với cập nhật snapshot

Một reference `volatile` có thể giúp **công bố một object bất biến**:

~~~java
// Mã minh họa trong class Java 17+:
record Inventory(int available, int sold) {}

private volatile Inventory current = new Inventory(10, 0);

Inventory snapshot() {
    return current;
}
~~~

Reader chỉ cần đọc `current` một lần rồi sử dụng cả hai thành phần trên **cùng một instance**. Tuy nhiên, nếu hai writer cùng làm:

~~~java
// Không an toàn với nhiều writer:
Inventory old = current;
current = new Inventory(old.available() - 1, old.sold() + 1);
~~~

họ có thể cùng đọc một phiên bản cũ và ghi đè kết quả của nhau. Volatile reference là một **điểm publication**, không tự tạo atomic read–modify–write.

### AtomicReference với immutable state

~~~java
// AtomicSnapshotDemo.java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Inventory(int available, int sold) {}

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Inventory> state =
            new AtomicReference<>(new Inventory(2, 0));

        Runnable sell = () -> state.updateAndGet(old ->
            old.available() == 0
                ? old
                : new Inventory(old.available() - 1, old.sold() + 1)
        );

        Thread a = new Thread(sell);
        Thread b = new Thread(sell);
        a.start();
        b.start();
        a.join();
        b.join();

        Inventory result = state.get();
        System.out.println("Available: " + result.available());
        System.out.println("Sold: " + result.sold());
        System.out.println("Total: " +
            (result.available() + result.sold()));
    }
}
~~~

~~~bash
javac AtomicSnapshotDemo.java
java AtomicSnapshotDemo
~~~

Stdout:

~~~text
Available: 0
Sold: 2
Total: 2
~~~

`AtomicReference.updateAndGet` cập nhật **một reference** nguyên tử; nhờ object bất biến, lần đọc `state.get()` trả về snapshot nhất quán. Hàm updater **có thể được gọi nhiều lần khi CAS retry**. Không đặt side effect như gửi email, thu tiền, ghi database trong lambda rồi giả định nó thực thi đúng một lần. Khi dữ liệu nằm ở database hoặc hệ thống ngoài JVM, CAS trong bộ nhớ không thay thế transaction của hệ thống đó.

Record dùng các thành phần `int` nên bản thân snapshot ở ví dụ là bất biến. Nếu chứa mảng/list mutable, cần xét **deep immutability**, không kết luận an toàn chỉ từ tên `record`.

### Volatile array không làm từng element atomic

~~~java
// Mã minh họa trong class:
private volatile int[] counters = new int[2];
~~~

Volatile áp dụng cho **field reference `counters`**, không khiến `counters[0]++` thành nguyên tử và không tự gắn ngữ nghĩa volatile cho từng phần tử. `volatile Settings settings` cũng không làm mọi field mutable trong `Settings` tự nhiên thread-safe. Nếu muốn cập nhật phần tử nguyên tử, cân nhắc `AtomicIntegerArray` hoặc khóa phù hợp.

## 8. CAS và các giới hạn cần biết

CAS (*compare-and-set*) cho phép kiểm tra giá trị dự kiến và cập nhật tại một điểm nguyên tử, nhưng:
- **Contention:** CAS có thể thất bại khi giá trị thay đổi; retry nhiều lần có thể tốn CPU.
- **Nhiều biến:** CAS một biến không tạo transaction cho các biến hoặc tài nguyên khác.
- **Updater lambda:** `updateAndGet`/`getAndUpdate` có thể tính lại, vì vậy hàm tính nên thuần, tránh side effect.
- **ABA:** trạng thái chuyển A → B → A, CAS chỉ so sánh thấy A và không biết đã có thay đổi trung gian. Khi việc nhận biết phiên bản quan trọng, có thể dùng phiên bản/stamp như `AtomicStampedReference`.
- **Liveness:** vòng retry không giới hạn có thể khiến một thread bị starvation dưới contention; cần cân nhắc yêu cầu thời gian chờ và tiến triển.

Không phải mọi CAS đơn giản đều gặp ABA; vấn đề cần xem xét khi **logic dựa vào việc giá trị không từng thay đổi**, chứ không chỉ vào giá trị hiện tại.

## 9. So sánh và chọn công cụ phù hợp

| Công cụ | Phù hợp | Không tự bảo đảm |
| --- | --- | --- |
| `volatile` | Flag/publication của dữ liệu với happens-before rõ ràng | Compound atomicity, multi-field transaction |
| `AtomicInteger`, `AtomicLong` | Tăng/giảm/CAS nguyên tử cho một biến | Chuỗi `get()` rồi `set()` không tự atomic |
| `AtomicBoolean` | Chuyển một trạng thái bằng CAS | Giao thức nhiều trạng thái hoặc reset phức tạp |
| `AtomicReference<T>` | CAS/swap một immutable snapshot | Các sửa đổi mutable bên trong object; I/O bên ngoài |
| `synchronized` | Check–update, invariant nhiều bước/nhiều field | Phải dùng đúng một monitor cho tất cả đường truy cập |
| `ReentrantLock` | Tương tự khóa, thêm `tryLock`/timeout/interruptible acquisition | Phải unlock trong finally, xem xét deadlock |
| `LongAdder` | Tổng số liệu thống kê tăng nhiều dưới contention | `sum()` không phải snapshot nguyên tử lúc cập nhật đồng thời |

Nguyên tắc:
1. Viết ra **bất biến** (ví dụ không oversell, tổng tiền không đổi, một winner).
2. Xác định **điểm cập nhật nguyên tử** cần có.
3. Chọn một atomic operation, CAS loop, hoặc lock giữ bất biến qua các bước.
4. Đảm bảo **reader** dùng cùng giao thức hoặc đọc một immutable snapshot nhất quán.
5. Sau khi đúng, mới đánh giá contention, độ trễ và cách dừng/retry.

## 10. Happens-before không thay thế atomicity

Một chương trình có thể dùng toàn bộ truy cập volatile và không mắc *data race* kiểu truy cập thường không có happens-before, nhưng vẫn mắc **race condition logic**. Ví dụ hai thread làm `volatile counter++`: từng volatile access có quy tắc ordering của JMM, song hai chuỗi đọc–tính–ghi vẫn bị xen kẽ.

Tương tự, main gọi `join()` sau khi hai worker làm phép tăng lỗi chỉ được bảo đảm **nhìn thấy kết quả cuối do chúng tạo ra**. Nếu chúng làm mất một lần tăng, `join()` không thể biến kết quả sai thành đúng.

Đừng dùng `Thread.sleep(...)`, `Thread.yield()` hoặc `Thread.onSpinWait()` để “sửa” phép tăng. Chúng không tạo atomicity cho hành động ghép. Thực nghiệm chạy đúng nhiều lần cũng không chứng minh mọi lịch xen kẽ hợp lệ đều đúng.

## 11. Checklist chẩn đoán và kiểm thử

1. **Xác định bất biến:** `count == số lần tăng`, `stock >= 0`, `available + sold == capacity`, hoặc chỉ một claim thành công.
2. **Tách thành từng hành động:** đọc giá trị, kiểm tra, tính toán, ghi; có khoảng trống để thread khác chen vào không?
3. **Vẽ lịch xấu nhất:** cả hai thread cùng thấy giá trị cũ trước lần ghi nào.
4. **Kiểm tra primitive:** nếu `AtomicInteger`, có gọi `get` rồi `set` riêng không? Nếu khóa, có dùng cùng monitor và cùng protocol không?
5. **Kiểm tra reader:** có thể thấy nửa trạng thái cũ, nửa mới không?
6. **Dùng bài test có điều phối:** `CountDownLatch`/barrier giúp ép lịch đọc–ghi xấu. Kiểm tra kết quả bằng assertion, không suy luận từ log/timing.
7. **Kiểm tra retry và side effect:** CAS loop có thể quay nhiều lần; updater có idempotent/pure không?
8. **Đo sau khi sửa:** đánh giá contention và throughput nhưng không bỏ bảo đảm tính đúng.

### Lỗi thường gặp

- “`volatile counter++` an toàn vì tất cả read/write là volatile.” → Sai; phép tăng ghép vẫn bị chen vào.
- “`AtomicInteger.get()` và `decrementAndGet()` đều atomic nên cả hai lời gọi atomic.” → Sai; không có transaction quanh cặp lời gọi.
- “Hai field volatile luôn có snapshot nhất quán.” → Sai; reader có thể đọc trạng thái trung gian.
- “Volatile reference làm object được trỏ tới thread-safe.” → Sai nếu object vẫn bị sửa mutable cạnh tranh.
- “`join()` sau cùng sửa được lost update.” → Sai; chỉ chờ và cung cấp visibility/ordering.
- “CAS updater được thực thi đúng một lần.” → Sai; có thể chạy lại khi retry.
- “Thêm `sleep` làm hết race.” → Không có bảo đảm JMM như vậy.

## 12. Tự kiểm tra

**1.** Hai thread gọi `counter++` trên `volatile int counter` từ 0. Kết quả có thể là 1 không? **Có.** Hai thread cùng đọc 0 rồi cùng ghi 1.

**2.** `if (seats.get() > 0) seats.decrementAndGet()` với `AtomicInteger` có an toàn khi stock=1 không? **Không.** Kiểm tra và giảm là hai thao tác riêng, cần CAS loop hoặc lock.

**3.** Hai thread cùng làm `if (!claimed) claimed = true` trên volatile boolean. Có thể cả hai cùng tin rằng claim thành công không? **Có.** Dùng `compareAndSet(false, true)` cho transition nguyên tử.

**4.** Dùng `volatile Inventory current` với immutable record là đủ cho nhiều writer làm read–compute–replace không? **Chưa đủ.** Publication của từng reference atomic nhưng compound update có thể lost update; dùng CAS hoặc khóa.

**5.** `AtomicReference.updateAndGet` có thể gọi updater nhiều lần? **Có**, khi tranh chấp và phải retry CAS.

**6.** Tại sao volatile flag dùng được để công bố một payload, nhưng volatile ++ không đủ? **Vì** flag cung cấp cạnh happens-before cho việc công bố đã hoàn thành, còn phép ++ cần **atomicity của cả read–modify–write**.

**Ghi nhớ:** `volatile` giải quyết **visibility và ordering của các truy cập cụ thể**; compound actions cần **atomicity tương ứng với bất biến**. Dùng phương thức atomic/CAS hoặc một giao thức khóa đủ phạm vi, và kiểm chứng cả đường đọc lẫn đường ghi.

### Tài liệu tham khảo

- Java Language Specification 17, `17.4 Java Memory Model: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- JDK 17 `AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- JDK 17 `AtomicBoolean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html
- JDK 17 `AtomicReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html