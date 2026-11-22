# Phân biệt tính hiển thị và loại trừ tương hỗ trong Java Memory Model

Khi nhiều thread chia sẻ dữ liệu có thể thay đổi, hai yêu cầu thường bị nhầm thành một: **thread đọc có nhìn thấy giá trị mà thread khác đã ghi không?** (*visibility*) và **hai thread có thể cùng sửa một trạng thái tại một thời điểm không?** (*mutual exclusion*). Java cung cấp các công cụ khác nhau cho từng nhu cầu. Hiểu rõ ranh giới này giúp tránh lỗi “đã dùng `volatile` nhưng counter vẫn sai” hoặc “đã khóa writer nhưng reader vẫn thấy dữ liệu không nhất quán”.

Bài này giải thích trên **Java Memory Model (JMM)** và các API Java chuẩn; không phụ thuộc cơ chế đồng thời riêng của framework.

## 1. Bốn khái niệm thường đi cùng nhau

| Khái niệm | Câu hỏi phải trả lời | Ví dụ |
| --- | --- | --- |
| **Visibility — tính hiển thị** | Khi một thread đã ghi, thread khác có bảo đảm quan sát giá trị đó theo quan hệ đồng bộ không? | Writer đặt `ready=true`; reader cần thấy thay đổi |
| **Mutual exclusion — loại trừ tương hỗ** | Có ngăn được nhiều thread cùng đi vào critical section bảo vệ cùng dữ liệu không? | Chỉ một thread được kiểm tra và trừ tồn kho mỗi lần |
| **Atomicity — tính nguyên tử** | Thao tác nghiệp vụ có được nhìn như một bước không bị xen ngang không? | `count++` phải là một lần tăng trọn vẹn |
| **Ordering — thứ tự quan sát** | Các thao tác ghi/đọc có các ràng buộc thứ tự nào đối với thread khác? | Ghi `payload` trước khi công bố `ready` |

**Visibility không kéo theo mutual exclusion.** Hai thread có thể đều đọc được giá trị mới nhất ở điểm chúng đọc nhưng vẫn cùng tính từ một snapshot và ghi đè cập nhật của nhau. **Mutual exclusion đúng cách thường đem lại visibility cần thiết**, bởi đồng bộ monitor/lock có quy tắc happens-before; tuy vậy phải dùng **cùng một khóa** trên tất cả đường đọc/ghi có liên quan.

Atomicity là mục tiêu ở mức thao tác; mutual exclusion là **một cách** đạt atomicity. Một operation `AtomicInteger.incrementAndGet()` cũng nguyên tử mà không cần programmer bao nó trong `synchronized`. Ngược lại, đọc hai field `volatile` riêng lẻ không tạo snapshot nguyên tử của cả cặp.

## 2. Tính hiển thị là gì?

Giả sử object có hai trường:

```java
class Message {
    int payload;
    boolean ready;
}
```

Một thread chạy `payload = 42; ready = true;`. Thread khác chạy vòng lặp cho tới khi `ready` đúng rồi đọc `payload`. Nếu cả hai trường là field thường và không có cơ chế đồng bộ, JMM **không bảo đảm** reader quan sát cập nhật `ready` trong một thời hạn hữu hạn, cũng không bảo đảm nó sẽ thấy `payload=42` khi tự suy luận chỉ từ thứ tự source code của writer.

Lý do: với các truy cập xung đột không có quan hệ happens-before, JVM/JIT và CPU có thể dùng tối ưu, cache/register và các thứ tự thực thi hợp lệ theo JMM; các thread có thể quan sát khác nhau. Đừng nghĩ “CPU luôn đọc lại RAM ở mỗi vòng lặp” hoặc “tăng `sleep` sẽ làm cache đồng bộ”. Cả hai đều không tạo hợp đồng memory visibility của Java.

### `volatile` là một cách công bố tín hiệu

Nếu `ready` được khai báo `volatile`:

```java
class Message {
    int payload;
    volatile boolean ready;
}
```

Writer:

```java
message.payload = 42;
message.ready = true;
```

Reader:

```java
if (message.ready) {
    System.out.println(message.payload);
}
```

Đây là các **mảnh minh họa**, giả sử writer và reader cùng tham chiếu tới một instance `message`. Một lần ghi `volatile` tạo quan hệ *synchronizes-with* đối với lần đọc `volatile` thích hợp theo synchronization order. Nếu reader đọc `ready` và thấy giá trị `true` do writer công bố, các ghi trước đó của writer (gồm `payload=42`) được nhìn thấy đúng theo quan hệ happens-before.

**Giới hạn:** mô hình này giả định không có thread khác sửa `payload` theo cách thiếu đồng bộ hoặc tái sử dụng `ready` sai giao thức. `volatile ready` là cơ chế **công bố** cho một message đã chuẩn bị xong, không làm mọi thao tác tương lai trên `payload` được bảo vệ. Reader phải thực sự quan sát cờ; code `if` ở ví dụ chỉ đi vào body nếu cờ đã đúng.

### Ví dụ Java 17 độc lập: truyền một message bằng `volatile`

Tạo tệp `VolatilePublicationExample.java`:

```java
import java.util.concurrent.locks.LockSupport;

public class VolatilePublicationExample {
    static class Message {
        int payload;
        volatile boolean ready;
    }

    public static void main(String[] args) throws InterruptedException {
        Message message = new Message();
        int[] received = {-1};

        Thread reader = new Thread(() -> {
            while (!message.ready) {
                // Giảm vòng quay bận, không phải cơ chế visibility.
                LockSupport.parkNanos(1_000_000L);
            }
            received[0] = message.payload;
        });

        Thread writer = new Thread(() -> {
            message.payload = 42;
            message.ready = true;
        });

        reader.start();
        writer.start();
        writer.join();
        reader.join();

        System.out.println("payload=" + received[0]);
    }
}
```

Chạy bằng JDK 17+:

```bash
javac VolatilePublicationExample.java
java VolatilePublicationExample
```

Stdout khi chương trình hoàn thành bình thường:

```text
payload=42
```

Tại sao đúng?

1. Writer ghi `payload=42` trước `ready=true` trong cùng thread.
2. Reader liên tục đọc **volatile field** `ready`; khi thấy `true`, quan hệ happens-before bảo đảm writer đã công bố payload.
3. Reader ghi kết quả vào `received[0]`; main chỉ đọc sau `reader.join()`. Việc `join` hoàn thành thành công tạo bảo đảm quan sát hành động của reader.
4. `LockSupport.parkNanos` chỉ giúp tránh spin 100% CPU trong ví dụ; **không thay thế `volatile`**. Mã production thường dùng `BlockingQueue`, `CountDownLatch` hoặc cơ chế chờ có deadline để không phải polling.

Về mặt test, chạy ví dụ thành công không phải phép chứng minh thực nghiệm rằng xóa `volatile` sẽ luôn gây lỗi. Phiên bản không `volatile` thiếu hợp đồng memory visibility; có thể vẫn tình cờ in `42` trên một máy. Lập luận đúng đến từ JMM.

## 3. Loại trừ tương hỗ là gì?

**Mutual exclusion** là bảo đảm tại một thời điểm nhiều nhất một thread được thực thi một vùng mã cần sự độc quyền trên **cùng một tài nguyên/khóa**.

Ví dụ, hàm rút tiền gồm hai thao tác: kiểm tra còn đủ tiền và trừ tiền. Nếu hai thread có thể chen giữa hai bước, cả hai có thể thấy cùng số dư cũ rồi cùng rút. Muốn duy trì bất biến `balance >= 0`, ta cần xem **toàn bộ kiểm tra + cập nhật** là một đơn vị được bảo vệ.

```java
class BankAccount {
    private int balance = 100;

    synchronized boolean withdraw(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount < 0");
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

Đây là **snippet class**, không có `main`. `synchronized` instance method sử dụng monitor của `this`. Với **cùng một instance BankAccount**, hai thread không thể cùng chạy `withdraw` một lúc. `balance()` cũng đi qua cùng monitor, giúp reader quan sát một trạng thái nhất quán theo giao thức khóa.

Mutual exclusion còn giúp visibility: khi thread A nhả monitor, thread B lấy **cùng monitor** sau đó, việc nhả monitor của A *happens-before* lần lấy monitor của B. Nhưng nếu writer khóa `lockA` còn reader khóa `lockB`, không có bảo đảm mutual exclusion hay monitor handoff giữa hai khóa đó.

## 4. `volatile` có visibility nhưng không chặn thread khác đi vào

Một biến `volatile int count` có các truy cập đọc/ghi đơn lẻ với semantics visibility/ordering của volatile. Tuy nhiên, phép tăng:

```java
count++;
```

vẫn là **read–modify–write** ở mức logic. Một lịch thực thi hợp lệ có thể như sau:

| Giai đoạn | Thread A | Thread B | `count` |
| --- | --- | --- | --- |
| Ban đầu | | | `0` |
| 1 | Đọc `0` | | `0` |
| 2 | | Đọc `0` | `0` |
| 3 | Tính và ghi `1` | | `1` |
| 4 | | Tính và ghi `1` | `1` |

Cả hai đọc giá trị có thật khi chúng đọc; không có vấn đề “đọc cache cũ” nào bắt buộc phải xuất hiện. Nhưng **hai lần tăng chỉ được tính một lần**. `volatile` không bảo vệ critical section và không gộp read–modify–write.

### Thí nghiệm Java 17: ép mất cập nhật dù dùng `volatile`

Chương trình sau cố ý tách read và write để đặt một barrier giữa hai bước. Đây là **test điều phối một lịch logic nguy hiểm**, không phải benchmark hay phép chứng minh data race ở mức JMM trong tất cả phiên bản chương trình.

Tạo `VolatileIsNotMutexExample.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;

public class VolatileIsNotMutexExample {
    static class Counter {
        volatile int value;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CyclicBarrier bothRead = new CyclicBarrier(2);

        Runnable increment = () -> {
            int old = counter.value;
            try {
                bothRead.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } catch (BrokenBarrierException e) {
                throw new IllegalStateException(e);
            }
            counter.value = old + 1;
        };

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("expected=2, actual=" + counter.value);
    }
}
```

```bash
javac VolatileIsNotMutexExample.java
java VolatileIsNotMutexExample
```

Stdout trong đường chạy bình thường, khi cả hai worker tới barrier:

```text
expected=2, actual=1
```

Lý do kết quả xác định: cả hai worker đọc `0` trước khi `CyclicBarrier(2)` cho bất kỳ worker nào đi qua và ghi. Sau đó cả hai đều tính `0+1`. Thread nào ghi cuối cùng thì giá trị vẫn bằng `1`. Tình huống thể hiện **việc thao tác trên trạng thái volatile vẫn có thể mất cập nhật ở cấp nghiệp vụ**. Barrier tạo đồng bộ trong test; không suy ra từ riêng test này rằng Java bắt buộc phát sinh data race theo định nghĩa hình thức trên mọi lần chạy.

**Giới hạn test:** ví dụ không đặt deadline ở barrier để tập trung vào ý tưởng. Test suite/production cần dùng `await(timeout, unit)` và truyền exception của worker về thread test bằng `Future.get()`, nhằm tránh treo khi thiếu participant hoặc task lỗi. Không dùng `Thread.sleep` thay barrier để cố tạo một lịch xác định.

## 5. `synchronized` vừa mutual exclusion vừa visibility

`synchronized` có hai hiệu ứng quan trọng:

1. **Loại trừ tương hỗ:** chỉ một thread sở hữu cùng intrinsic monitor trong một thời điểm. Một critical section có thể bảo vệ nhiều field như một bất biến thống nhất.
2. **Memory visibility/ordering:** hành động `unlock` trên monitor happens-before hành động `lock` tiếp theo trên cùng monitor. Writer và reader tuân thủ cùng monitor có thể nhìn thấy trạng thái mà giao thức đồng bộ công bố.

Ví dụ:

```java
class SynchronizedCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
```

Đây là **snippet class**; khi mọi đường đọc và ghi `count` đều qua những method dùng cùng monitor của **cùng instance**, `increment()` không bị xen ngang bởi một `increment()` khác. Thêm `volatile` cho field ở đây thường không cần thiết.

### Chương trình so sánh `synchronized` và atomic operation

Tạo `SafeCounterComparison.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SafeCounterComparison {
    static class LockedCounter {
        private int count;

        synchronized void increment() {
            count++;
        }

        synchronized int get() {
            return count;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        LockedCounter locked = new LockedCounter();
        AtomicInteger atomic = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                locked.increment();
                atomic.incrementAndGet();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("synchronized=" + locked.get());
        System.out.println("atomic=" + atomic.get());
    }
}
```

```bash
javac SafeCounterComparison.java
java SafeCounterComparison
```

Stdout:

```text
synchronized=200000
atomic=200000
```

**Vì sao chính xác?** `locked.increment()` yêu cầu cùng monitor. `atomic.incrementAndGet()` là một operation cập nhật nguyên tử có hợp đồng memory semantics tương ứng; nó không cần programmer giữ monitor bên ngoài. `join()` chờ hai thread hoàn thành trước khi main đọc kết quả, nên không phải “đọc quá sớm”.

Đây **không phải benchmark** chứng minh `AtomicInteger` luôn nhanh hơn `synchronized`. Tốc độ phụ thuộc mức contention, JVM, số core, hotspot và loại workload. Chọn theo tính đúng đắn của thao tác cần bảo vệ trước.

### Những giới hạn quan trọng của `synchronized`

- Một method `synchronized` trên object A **không** ngăn thread khác chạy `synchronized` trên object B. Cùng dữ liệu phải được bảo vệ bởi **cùng lock identity**, không chỉ “cùng từ khóa”.
- `static synchronized` lấy monitor của đối tượng `Class`, khác monitor của instance method `synchronized`.
- Một writer khóa mà reader đọc trực tiếp field không khóa vẫn có thể có vấn đề visibility/consistency. Tất cả đường đọc/ghi thuộc giao thức phải tham gia cùng quy tắc.
- Java monitor là reentrant: một thread có thể lấy lại monitor nó đang giữ; tuy vậy nested lock trên **những monitor khác nhau** vẫn có nguy cơ deadlock.
- Không giữ monitor quá lâu cho I/O, `sleep` hoặc đợi `Future` nếu không cần: các thread khác sẽ `BLOCKED` khi cố vào cùng monitor.
- `Thread.sleep` không nhả monitor. `Object.wait` nhả monitor **của chính đối tượng được gọi `wait`** trong khi chờ và lấy lại trước khi trả về.
- `synchronized` không hứa công bằng (fairness), thứ tự thức dậy hay tối ưu throughput.

## 6. Bảng chọn công cụ theo đúng yêu cầu

| Công cụ | Visibility | Mutual exclusion | Atomic read–modify–write | Phạm vi thường phù hợp |
| --- | --- | --- | --- | --- |
| Field thường `int`/`boolean`, không đồng bộ | Không có bảo đảm liên thread cho dữ liệu race | Không | Không đối với `++`/`--` | Chỉ truy cập cục bộ hoặc có giao thức khác bao quanh |
| `volatile` field | Có, theo volatile happens-before/ordering | **Không** | Các đọc/ghi riêng có semantics volatile; `x++` vẫn không atomic | Cờ dừng, một chiều công bố dữ liệu, reference snapshot |
| `synchronized` cùng monitor | Có, qua unlock → lock | **Có** | Có thể bảo vệ **toàn bộ** thao tác ghép trong critical section | Bất biến nhiều field, check–then–act |
| `ReentrantLock` / `Lock` đúng giao thức | Có, qua lock/unlock theo memory semantics | **Có** | Có thể bảo vệ thao tác ghép | Cần `tryLock`, timed lock, interruptible acquisition, `Condition` |
| `AtomicInteger` / `AtomicLong` | Có theo memory effects của API atomic | **Không khóa cả vùng mã tùy ý** | **Có** cho `incrementAndGet`, `compareAndSet` và các method atomic | Một biến/operation atomic |
| `AtomicReference` với CAS | Có theo memory effects của API atomic | Không khóa các thao tác bên ngoài | Có cho cập nhật **một reference** bằng CAS | Immutable state snapshot, cập nhật versioned |
| `LongAdder` | Có hợp đồng thread-safety phù hợp cho cập nhật | Không | Từng add an toàn, nhưng `sum()` không snapshot nguyên tử khi đang update | Metrics nhiều writer, chấp nhận tổng không tuyến tính hóa từng thời điểm |
| `BlockingQueue`/concurrent collection | Có bảo đảm theo hợp đồng chuyển giao/operation | Phụ thuộc triển khai; không khóa toàn workflow | Theo từng operation đã được API cam kết | Producer–consumer, map theo key |
| Immutable object + safe publication | Đọc ổn định theo cách công bố hợp lệ | Không cần lock để đọc object thực sự immutable | Không có phép cập nhật in-place | Dữ liệu cấu hình, snapshot |

**Đọc hàng “AtomicInteger”:** operation `incrementAndGet` là atomic, nhưng sequence `if (count.get() > 0) count.decrementAndGet()` vẫn có thể sai khi nhiều thread cùng chạy. Atomicity có **phạm vi**: một method atomic không tự làm cả một quy trình trở thành atomic transaction.

**Đọc hàng “volatile”:** Java bảo đảm đọc/ghi volatile đơn lẻ có semantics và atomicity phù hợp với một lần truy cập field; điều **không được bảo đảm** là nhiều phép truy cập cùng tạo một thao tác nguyên tử. Vì vậy đừng viết “volatile hoàn toàn không atomic” một cách thiếu phân biệt.

## 7. `ReentrantLock` và visibility

`java.util.concurrent.locks.ReentrantLock` cung cấp mutual exclusion và memory semantics như lock truyền thống, có thêm `tryLock`, `lockInterruptibly` và các `Condition`. Lấy khóa thành công và nhả khóa có hiệu ứng đồng bộ; các reader/writer **phải dùng cùng một instance lock** cho dữ liệu tương ứng.

Ví dụ class Java 17, dùng được khi đặt vào file Java nhưng **chưa có `main`**:

```java
import java.util.concurrent.locks.ReentrantLock;

class Inventory {
    private final ReentrantLock lock = new ReentrantLock();
    private int stock = 1;

    boolean sellOne() {
        lock.lock();
        try {
            if (stock == 0) {
                return false;
            }
            stock--;
            return true;
        } finally {
            lock.unlock();
        }
    }

    int currentStock() {
        lock.lock();
        try {
            return stock;
        } finally {
            lock.unlock();
        }
    }
}
```

Mọi thao tác cập nhật và đọc stock trong class đều dùng **cùng lock**, nên vừa không bán quá một sản phẩm nếu ban đầu chỉ có một, vừa có visibility khi đọc. Luôn `unlock()` trong `finally` sau khi `lock()` thành công; quên nhả khóa có thể khiến thread khác chờ vô hạn.

**Đừng nhầm `Lock` với `volatile`**: một `volatile boolean available` có thể giúp nhiều thread thấy giá trị cờ mới, nhưng không ngăn cả hai cùng thấy `true` trước khi một trong hai chuyển cờ sang `false`. Nếu điều kiện và cập nhật phải đi cùng nhau, chọn lock hoặc atomic compare-and-set phù hợp.

## 8. Nguyên tử hóa một thao tác mà không khóa cả critical section

Giả sử tồn kho chỉ là một số nguyên. `AtomicInteger` có `compareAndSet(expected, update)`: chỉ thay đổi nếu giá trị thực tế vẫn bằng expected tại thời điểm thao tác atomic được thực hiện. Từ đó có thể xây một vòng CAS để bảo vệ điều kiện trừ kho:

```java
import java.util.concurrent.atomic.AtomicInteger;

class AtomicInventory {
    private final AtomicInteger stock = new AtomicInteger(1);

    boolean sellOne() {
        while (true) {
            int current = stock.get();
            if (current == 0) {
                return false;
            }
            if (stock.compareAndSet(current, current - 1)) {
                return true;
            }
        }
    }

    int currentStock() {
        return stock.get();
    }
}
```

Đây là class minh họa, không có `main`. Hai thread cùng đọc `1`: chỉ một phép CAS thành công khi chuyển `1 → 0`. Thread còn lại thất bại, đọc lại `0` và trả `false`. Như vậy một điều kiện đơn biến vẫn được bảo toàn **không cần explicit mutex**.

**Giới hạn CAS:** nếu cập nhật liên quan nhiều field hoặc external side effect (gửi email, trừ tiền ở remote API), một CAS trên một số nguyên không gộp được mọi hiệu ứng. Vòng CAS có thể retry; **không đặt side effect không idempotent trong callback/logic có thể chạy lại**. Với nhiều biến cùng tạo một invariant, cân nhắc cùng monitor/lock hoặc một immutable aggregate được thay bằng `AtomicReference` theo giao thức đúng.

## 9. Visibility có nghĩa là “luôn thấy giá trị mới nhất” không?

Không nên diễn đạt visibility thành “mọi thread luôn thấy giá trị vừa ghi ngay lập tức theo đồng hồ thực”. JMM định nghĩa các quan hệ thứ tự và đồng bộ cho phép thread quan sát dữ liệu theo hợp đồng. Với `volatile`, các lần đọc/ghi đồng bộ có thứ tự phù hợp; nhưng:

- Reader chỉ biết cờ đã được công bố nếu **thực sự đọc nó**.
- Reader có thể chưa được scheduler chạy, nên không có cam kết độ trễ tuyệt đối.
- Nếu writer liên tục cập nhật một field khác mà không có giao thức tương ứng, một lần đọc cờ không biến các field khác thành snapshot nhất quán vô hạn.
- `volatile` không thay thế quyền sở hữu dữ liệu, bảo đảm liveness, timeout hoặc điều kiện nghiệp vụ.

Ví dụ: writer công bố `payload` rồi đặt `ready=true` là một giao thức handoff đơn giản. Nếu sau đó writer lại sửa `payload` khi reader đang đọc, phải bổ sung điều phối/immutability; lần công bố ban đầu không bảo vệ cuộc cập nhật sau.

## 10. Một số mối quan hệ happens-before cần nhớ

JMM dùng quan hệ *happens-before* để xác định thứ tự và hiệu ứng visibility giữa các hành động. Đây **không chỉ là thời điểm A xảy ra trước B trên đồng hồ**.

1. **Trong cùng thread:** hành động trước happens-before hành động sau theo *program order*.
2. **Monitor:** unlock monitor happens-before lần lock **tiếp theo** trên cùng monitor.
3. **Volatile:** ghi vào field volatile happens-before lần đọc sau đó của chính field volatile theo quy tắc đồng bộ của JMM.
4. **Thread start:** lời gọi `Thread.start()` happens-before các hành động bên trong thread mới.
5. **Thread join:** các hành động của thread hoàn tất happens-before thread khác quan sát thành công việc kết thúc qua `join()`.
6. **Tiện ích đồng thời:** nhiều API trong `java.util.concurrent` mô tả memory-consistency effects, ví dụ `BlockingQueue` chuyển giao object hoặc `Future.get()` sau khi task hoàn tất.
7. **Tính bắc cầu:** nếu A happens-before B và B happens-before C thì A happens-before C.

**Happens-before không phải mutex.** `Thread.join()` có thể giúp main nhìn thấy kết quả của hai worker sau khi hoàn thành, nhưng **không sửa lost update** mà hai worker đã gây ra trong lúc chạy. Tương tự, một signal volatile giữa producer và consumer có thể giúp công bố dữ liệu, nhưng hai producers đồng thời sửa cùng state vẫn cần giao thức chống xen ngang.

## 11. Các thiết kế thường cần visibility mà không cần mutex

### 11.1. Cờ dừng một chiều

`volatile boolean running = true;` phù hợp khi một thread liên tục kiểm tra cờ và thread khác đặt `false` để yêu cầu kết thúc. Cần bảo đảm code xử lý tín hiệu và không bị kẹt ở một blocking call không phản ứng với cờ. Với blocking I/O, thread interruption và API cancellation có thể thích hợp hơn hoặc cần kết hợp.

### 11.2. Công bố immutable snapshot

Writer tạo một object snapshot thực sự bất biến rồi gán vào `volatile` reference. Reader đọc **một reference** và sử dụng trọn snapshot đó. Cách này tránh việc đọc xen phiên bản giữa nhiều field.

```java
record Snapshot(int x, int y) {}

class Holder {
    volatile Snapshot current = new Snapshot(0, 0);

    void publish(int x, int y) {
        current = new Snapshot(x, y);
    }

    Snapshot read() {
        return current;
    }
}
```

Đây là snippet Java 17+ (không có `main`). `record` lưu hai primitive `int`, nên giá trị sau xây dựng không thay đổi. Gán vào `volatile current` công bố snapshot mới; reader lấy đúng **một snapshot** cho cả `x` và `y`. Nhưng nếu **nhiều writer** đều xây snapshot từ current rồi gán, chúng vẫn có thể ghi đè cập nhật của nhau; cần serialization hoặc `AtomicReference` CAS nếu invariant đòi không mất cập nhật.

### 11.3. Safe publication và `final` fields

Field `final` có các bảo đảm đặc biệt khi object được xây dựng đúng cách, nhưng **`final` reference không làm object được tham chiếu trở nên bất biến**. Ví dụ `final List<Item> items` vẫn có thể chứa list mutable và phần tử mutable. Không làm `this` escape trước khi constructor hoàn thành; khi chia sẻ các object có state tiếp tục được cập nhật, dùng giao thức công bố/đồng bộ phù hợp.

### 11.4. Handoff bằng thread-safe queue

Thay vì tự dựng cờ `ready` và field `payload`, producer có thể `queue.put(message)`, consumer `queue.take()` với `BlockingQueue`. Hợp đồng API bảo đảm chuyển giao dữ liệu và cơ chế chờ; vẫn cần limit queue, shutdown/cancellation và giới hạn tài nguyên. Đây thường là thiết kế dễ duy trì hơn một vòng quay chờ volatile.

## 12. Những thiết kế phải có mutual exclusion hoặc atomic workflow

### 12.1. Check–then–act

```java
if (!seat.isBooked()) {
    seat.book();
}
```

Ngay cả khi mỗi method được `synchronized` riêng lẻ, nếu hai thread được phép chạy xen giữa **check** và **book**, cả hai có thể thấy chưa đặt. Cần method atomic kiểu `bookOnce()` chứa cả kiểm tra lẫn cập nhật trong **cùng critical section**, hoặc CAS/trạng thái transactional tương đương.

### 12.2. Read–modify–write

```java
volatile int counter;
// ...
counter = counter + 1;
```

Đây là snippet minh họa field của class; không phải chương trình đầy đủ. Dù field `volatile`, hai thread có thể cùng lấy snapshot cũ. Dùng `AtomicInteger.incrementAndGet()` hoặc khóa bảo vệ toàn bộ read–compute–write.

### 12.3. Invariant nhiều field

Một đơn hàng có `reserved` và `available` với tổng cố định. Nếu writer cập nhật từng field và reader đọc giữa các bước, reader có thể thấy một nửa trạng thái mới. Hai field `volatile` **không tự bảo đảm snapshot atomic**; reader có thể đọc chúng ở hai thời điểm khác nhau. Giải pháp gồm cùng monitor/lock cho toàn bộ update và read, hoặc immutable snapshot thay bằng một reference atomic.

### 12.4. Thao tác ghép trên concurrent collection

`ConcurrentHashMap` bảo vệ từng operation theo hợp đồng API. Nhưng `if (!map.containsKey(k)) map.put(k,v)` vẫn có cửa sổ race ở cấp workflow. Chọn `putIfAbsent`/`computeIfAbsent` hoặc một transaction thích hợp. **Thread-safe object ≠ mọi chuỗi dùng object đó đều thread-safe.**

## 13. Các bẫy thường gặp khi chọn `volatile` hoặc `synchronized`

| Ngộ nhận | Điều sai | Cách chọn đúng |
| --- | --- | --- |
| “`volatile` làm mọi thao tác trên field thành atomic” | `count++` gồm nhiều hành động | `AtomicInteger`/mutex cho update |
| “Hai field đều `volatile` nên cặp luôn nhất quán” | Reader vẫn có thể đọc hai phiên bản | Khóa chung hoặc immutable snapshot qua một reference |
| “Writer dùng `synchronized` là đủ, reader không cần” | Reader thường không tham gia giao thức happens-before của monitor | Đồng bộ cả hai hoặc dùng publication đã chứng minh |
| “Khóa bằng object nào cũng giống nhau” | Lock identity khác → không loại trừ nhau | Dùng đúng cùng monitor/`Lock` |
| “`join()` giúp main thấy đúng mọi phép tăng” | `join` không biến các update worker thành atomic | Đồng bộ ở nơi update diễn ra |
| “`Thread.sleep` làm giá trị được flush ra” | Sleep không tạo visibility hay mutual exclusion cần thiết | `volatile`/lock/queue/latch theo điều kiện |
| “`AtomicInteger.get()` rồi `set()` là atomic workflow” | Hai thao tác riêng có thể bị chen vào | Dùng `compareAndSet`/method atomic |
| “Thread-safe map giúp check–then–put luôn an toàn” | Các bước vẫn có thể xen kẽ | Operation atomic trong API |
| “Bọc khóa lớn mọi nơi sẽ luôn tốt hơn” | Contention, lock convoy, deadlock, latency | Khóa đúng invariant với critical section đủ ngắn |
| “Không có nhiều core thì không race” | Scheduler có thể interleave trên một core | Bảo vệ giao thức độc lập số CPU |
| “Virtual thread tự làm state thread-safe” | Mọi thread Java vẫn phải tuân theo JMM | Đồng bộ/immutability như thường |
| “Một test qua 1.000 lần đủ chứng minh an toàn” | Test chỉ thấy một phần lịch chạy | JMM reasoning + stress/coordinated tests |

## 14. Đọc thread dump và profile: quan sát gì?

**Mutual exclusion có chi phí contention.** Nếu nhiều thread không lấy được cùng intrinsic monitor, chúng có thể xuất hiện ở trạng thái `BLOCKED` trong thread dump. Trên JFR/monitor profiling, xem ai giữ monitor và giữ bao lâu. Nếu dùng `ReentrantLock`, thread có thể park và hiển thị `WAITING`/`TIMED_WAITING` khi chờ lock, chứ không nhất thiết ở `BLOCKED`.

**Visibility bug khó phát hiện chỉ bằng trạng thái thread.** Một thread có thể ở `RUNNABLE` trong vòng lặp đọc cờ thường, mã vẫn không tạo happens-before. Thread dump không chứng minh field đang được đọc đúng giá trị. Muốn kết luận, kiểm tra tất cả đường truy cập và giao thức công bố, kết hợp JFR, logs, stress tests và phân tích JMM.

### Phương pháp chẩn đoán

1. Liệt kê field/object được chia sẻ, xác định thread nào đọc/ghi.
2. Ghi invariant nghiệp vụ: “không bán quá kho”, “counter không mất update”, “reader thấy toàn bộ payload đã công bố”.
3. Hỏi bài toán cần **visibility**, **mutual exclusion**, **atomicity của một operation** hay **atomicity của nhiều field**.
4. Kiểm tra mỗi đường truy cập có dùng cùng monitor/lock, volatile publication hoặc API atomic hợp đồng đúng không.
5. Nếu dùng volatile flag, kiểm tra thứ tự ghi payload → flag và reader thực sự đọc flag trước payload; chú ý lần cập nhật payload sau publication.
6. Nếu dùng monitor, kiểm tra lock identity, thời gian giữ khóa, I/O trong khóa và chuỗi lock acquisition gây deadlock.
7. Nếu dùng CAS, kiểm tra vòng retry, invariant đơn biến và side effects có thể lặp.
8. Viết test đồng thời với start gate/barrier khi muốn tái hiện một interleaving; nhưng nhớ barrier tạo happens-before và **có thể che visibility bug** đang nghiên cứu.
9. Test dưới tải, theo dõi kết quả và profile; không dùng việc “không tái hiện” thay cho chứng minh đúng.

## 15. Bài tập phân biệt nhanh

**1. Một thread đặt `stopped=true` và thread khác kiểm tra liên tục để thoát. Cần loại trừ tương hỗ không?** Nếu đây là cờ dừng một chiều độc lập, thường chỉ cần visibility, chẳng hạn `volatile boolean stopped`. Với thao tác blocking dài hoặc nhiều state liên quan, có thể cần cơ chế khác.

**2. Hai thread cùng gọi `volatileCounter++`, còn test `join()` trước khi in. Có thể mất cập nhật không?** Có. `join` bảo đảm main quan sát sau khi worker kết thúc; nó không bảo vệ read–modify–write giữa hai worker.

**3. Một method `synchronized` ghi field; method khác đọc field trực tiếp. Có chắc reader thấy cập nhật không?** Không. Reader không tham gia cùng monitor và không có bảo đảm visibility do chính khóa đó tạo ra trên đường đọc. Cần cơ chế đồng bộ/volatile/publication thích hợp.

**4. Hai `synchronized` instance methods của hai object khác nhau có ngăn nhau không?** Không. Mỗi instance có monitor riêng. Nếu cùng sửa một `static` mutable field, phải chọn đúng khóa chung.

**5. Nếu `AtomicInteger.compareAndSet` sửa được một field, còn hai field liên quan thì sao?** CAS trên một biến không tự tạo atomic transaction hai biến. Có thể dùng lock chung hoặc immutable aggregate được thay bằng một atomic reference.

**6. Khi nào `volatile Snapshot current` phù hợp?** Khi writer công bố một snapshot bất biến hoàn chỉnh và reader cần thấy nguyên trạng một phiên bản bằng cách đọc một reference. Nếu nhiều writers cần hợp nhất cập nhật dựa trên snapshot cũ, cần thêm CAS hoặc serialization.

**7. `synchronized` có bảo đảm mọi thread luôn vào khóa theo thứ tự FIFO không?** Không. Nó bảo đảm mutual exclusion và monitor memory semantics, không cam kết fairness.

**8. Khi nào cả visibility và mutual exclusion đều cần?** Ví dụ trừ tồn kho: các worker phải không xen ngang phần check–update và các reader phải thấy trạng thái nhất quán. Cùng một lock quanh update/read có thể đáp ứng cả hai.

## 16. Checklist thiết kế trước khi quyết định

- Đang cần **reader thấy thay đổi**, hay **ngăn nhiều writer tác động đồng thời**? Hai yêu cầu có cùng tồn tại không?
- Có một phép gán/cờ đơn giản, một read–modify–write, hay invariant nhiều field?
- Nếu dùng `volatile`, những dữ liệu nào được công bố trước ghi volatile? Có sửa tiếp sau publication không?
- Nếu dùng `synchronized`/`Lock`, mọi truy cập liên quan có dùng **cùng khóa**? Khóa có bị giữ khi đợi I/O không?
- Nếu dùng atomic class, **operation nào** được bảo đảm atomic? Có vô tình tách check và update?
- Có thể thiết kế immutable snapshot, ownership theo thread hoặc `BlockingQueue` để giảm shared mutable state không?
- Có test invariant sau khi thread hoàn tất, stress test và bằng chứng happens-before không?
- Khi chuyển từ platform thread sang virtual thread, giao thức dữ liệu có còn đúng trên mọi lịch chạy không?

**Quy tắc ghi nhớ:** `volatile` giúp **công bố/quan sát** giá trị qua JMM nhưng **không tạo một khu vực độc quyền**; `synchronized`/`Lock` bảo vệ **critical section** và đồng thời tạo bảo đảm memory visibility giữa các lần mở/đóng đúng khóa; atomic classes bảo vệ **những operation cụ thể**. Hãy chọn theo bất biến và phạm vi thao tác mà chương trình cần bảo toàn, thay vì chọn theo từ khóa quen tay.