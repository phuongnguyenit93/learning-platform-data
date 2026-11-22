# Chọn `synchronized`, `Lock` hoặc atomic theo phạm vi bất biến

**Module:** Spring Framework - concurrency  
**Nhóm:** Trạng thái bean  
**Mục tiêu:** Khi một bean Spring được nhiều luồng truy cập, xác định chính xác **bất biến cần bảo vệ**, những thao tác nào phải xảy ra như một đơn vị và ranh giới đồng bộ hóa cần rộng đến đâu; từ đó chọn `synchronized`, `Lock` hay các lớp `Atomic*` đúng ngữ cảnh.

## 1. Bắt đầu từ bất biến, không bắt đầu từ tên công cụ

**Bất biến (invariant)** là điều kiện phải luôn đúng đối với trạng thái được chia sẻ tại những điểm quan sát hợp lệ. Ví dụ:

- Một bộ đếm có thể tăng độc lập: mỗi lần gọi `increment()` tăng đúng một đơn vị, không bị mất cập nhật.
- Số lượng hàng còn có thể đặt không âm: `available >= 0`. Một lần đặt hàng là hành động **kiểm tra đủ hàng và trừ hàng**.
- Hai trường cùng mô tả một kho: `available >= 0`, `reserved >= 0`, `available + reserved == initialTotal`. Một lần đặt hàng phải cập nhật cả `available` và `reserved` trong **cùng một lần chuyển trạng thái logic**.
- Hai tài khoản ở cùng một sổ cái: tổng số dư không đổi khi chuyển tiền; khoản chuyển phải bảo vệ đồng thời cả hai tài khoản. Nếu dữ liệu ở cơ sở dữ liệu/nhiều dịch vụ, một khóa trong JVM không đủ.

Câu hỏi không phải “biến này đã được khóa chưa?” mà là:

1. **Đâu là trạng thái được chia sẻ?** Trường của singleton bean, đối tượng cache, collection, bản ghi DB hay nhiều tài nguyên?
2. **Điều kiện nào bắt buộc đúng?** Viết tiền điều kiện và hậu điều kiện rõ ràng.
3. **Một thao tác nghiệp vụ gồm những bước nào?** Có cần giữ chúng nguyên tử cùng nhau?
4. **Ai có thể đọc/ghi?** Nhiều HTTP request, `@Async`, `@Scheduled`, callback, nhiều instance ứng dụng?
5. **Ranh giới quan sát nằm ở đâu?** Một giá trị, một nhóm trường, nhiều đối tượng, một bản ghi DB hay nhiều hệ thống?
6. **Cần gì ngoài bảo vệ dữ liệu?** Thử lấy khóa không chặn, timeout, hủy khi ngắt, chờ điều kiện, đo độ trễ?

Từ đó mới lựa chọn cơ chế.

### Ví dụ race condition

Giả sử bean giữ `available = 1`. Cách viết sau **không an toàn** khi có hai luồng gọi cùng lúc:

```java
private int available = 1;
private int reserved = 0;

public boolean reserveOne() {
    if (available == 0) {
        return false;
    }
    available--;
    reserved++;
    return true;
}
```

Cả hai luồng có thể cùng quan sát `available > 0`, cùng đi qua nhánh kiểm tra và cùng báo đặt thành công. `available--` và `reserved++` đều là thao tác đọc–tính toán–ghi; bản thân chúng không phải một giao dịch nguyên tử. Có thể xảy ra bán vượt số lượng, mất cập nhật hoặc snapshot giữa chừng. Đặt `volatile` cho hai trường **không** biến ba bước kiểm tra/cập nhật thành một hành động nguyên tử.

## 2. Vì sao trạng thái trong Spring bean cần chú ý?

`@Component`, `@Service` và `@Repository` mặc định có **singleton scope**: một bean instance cho mỗi bean definition trong một Spring IoC container. Nhiều request thread hoặc worker có thể gọi cùng instance. Singleton chỉ mô tả **số lượng instance và vòng đời**, không tự bảo đảm an toàn luồng.

```java
@Service
public class VisitService {
    private int visits;

    public int registerVisit() {
        return ++visits;  // race condition khi nhiều luồng cùng gọi
    }
}
```

Đây là **đoạn minh họa nằm trong ứng dụng Spring** (cần `import org.springframework.stereotype.Service;`). Nhiều lời gọi có thể đọc cùng giá trị cũ và ghi đè kết quả nhau.

Một service **stateless** thường dễ dùng chung: dữ liệu của mỗi request nằm trong local variable, còn dependency là các đối tượng được dùng theo hợp đồng thread-safety của chúng. “Không có trường mutable” là điểm khởi đầu tốt nhưng không đủ nếu service vẫn sửa đổi đối tượng mutable do dependency chia sẻ.

Các scope khác cũng không chữa mọi race:

- `prototype` tạo instance theo lần yêu cầu bean, nhưng nếu một prototype được inject trực tiếp một lần vào singleton thì singleton giữ cùng instance đó.
- `request` tạo trạng thái riêng theo request, nhưng một request có thể gửi công việc sang thread khác; việc truyền context và vòng đời cần xử lý riêng.
- `session` vẫn có thể bị nhiều request đồng thời của **cùng session** truy cập.
- Mỗi replica ứng dụng có singleton bean của **riêng replica đó**; `synchronized` không khóa được một replica khác.

Vì vậy cần xác định trạng thái sống trong **một JVM** hay là dữ liệu nghiệp vụ **dùng chung giữa nhiều JVM và DB** trước khi chọn khóa.

## 3. Phân biệt atomicity, visibility và ordering

Ba thuộc tính liên quan nhưng khác nhau:

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Atomicity** | Thao tác có thể bị luồng khác xen vào giữa các bước logic không? | `if (stock > 0) stock--` phải là một bước nghiệp vụ |
| **Visibility** | Luồng khác có thấy giá trị đã ghi hay vẫn thấy bản cũ? | Cờ dừng được một worker quan sát |
| **Ordering / happens-before** | Một ghi có được công bố đúng thứ tự trước một đọc liên quan? | Trạng thái được cập nhật dưới cùng khóa rồi đọc dưới khóa đó |

Trong Java Memory Model:

- Thoát `synchronized` trên **cùng monitor** có quan hệ happens-before với một lần vào monitor kế tiếp; thao tác dưới cùng monitor có tính loại trừ lẫn nhau.
- `Lock` chuẩn (chẳng hạn `ReentrantLock`) cung cấp hiệu ứng bộ nhớ tương ứng khi `unlock()` rồi `lock()` trên cùng lock.
- `AtomicInteger`, `AtomicLong`, `AtomicReference` cung cấp các thao tác nguyên tử và ngữ nghĩa bộ nhớ đã được tài liệu API định nghĩa; `compareAndSet` có hiệu ứng như truy cập volatile phù hợp.
- `volatile` phù hợp cho việc công bố/đọc **một giá trị** hoặc cờ mà không có thao tác phức hợp; `volatile int count; count++;` vẫn mất cập nhật.
- `final` giúp thiết kế đối tượng bất biến và công bố an toàn khi xây dựng đúng, nhưng không làm một object mutable bên trong trở thành bất biến.

**Nguyên tắc:** mọi đường **đọc và ghi** liên quan đến cùng bất biến phải tuân theo **cùng một giao thức đồng bộ**. Chỉ khóa các phương thức ghi mà để getter đọc nhiều trường trần trụi sẽ tạo snapshot không nhất quán.

## 4. Bảng quyết định nhanh theo ranh giới bất biến

| Bất biến và nhu cầu | Thường chọn | Vì sao | Dễ sai ở đâu? |
| --- | --- | --- | --- |
| Một bộ đếm độc lập, tăng/giảm/get | `AtomicInteger`/`AtomicLong` | Một thao tác cập nhật nguyên tử; không cần monitor | Tách `get()` và `incrementAndGet()` rồi tưởng là nguyên tử |
| Một số có điều kiện, ví dụ quota không âm | `AtomicInteger` + vòng CAS | Điều kiện và phép trừ được thực hiện như **một** cập nhật của **một giá trị** | `if (get() > 0) decrementAndGet()` không an toàn |
| Vài trường cần thay đổi cùng nhau | `synchronized` trên monitor chung | Dễ đọc, khó quên mở khóa; bảo vệ cả invariant và snapshot | Khóa từng field riêng, hoặc getter không khóa |
| Vài trường nhưng cần `tryLock`, timeout, xử lý interrupt, `Condition` | `ReentrantLock` | Điều khiển cách chờ/lấy khóa, cùng bảo vệ vùng tới hạn | Quên `unlock()` trong `finally`; dùng khác lock cho reader/writer |
| Nhiều trường nhưng có thể biểu diễn thành **một snapshot immutable** | `AtomicReference<State>` + CAS | Thay thế nguyên trạng thái logic bằng một thao tác | Mutable object bên trong state; side effect trong vòng CAS |
| Nhiều tác vụ đọc, ít ghi và đã đo contention | Có thể xem xét `ReentrantReadWriteLock` | Đọc đồng thời với nhau khi không có writer | Nhiều cơ chế khóa làm phức tạp; hiệu năng chưa chắc tốt |
| Nhiều JVM/replica hoặc dữ liệu DB phải nhất quán | DB constraint, transaction + conditional update/locking/optimistic version | Phạm vi bất biến vượt quá một JVM | Nhầm `synchronized` của một bean là khóa toàn hệ thống |

**Quy tắc ưu tiên:** Nếu cần khóa thông thường trong một JVM, bắt đầu với `synchronized`. Chọn `ReentrantLock` khi thật sự cần hành vi bổ sung. Dùng atomic khi toàn bộ phép cập nhật có thể biểu diễn đúng bằng **một trạng thái nguyên tử**; atomic không tự động tốt hơn khóa cho mọi bất biến.

## 5. `AtomicInteger`: một biến, có thể có điều kiện

Với thống kê độc lập:

```java
private final java.util.concurrent.atomic.AtomicLong totalRequests =
        new java.util.concurrent.atomic.AtomicLong();

public long onRequest() {
    return totalRequests.incrementAndGet();
}
```

Mỗi lần gọi có một tăng nguyên tử. Tuy vậy, nếu yêu cầu “chỉ tăng khi nhỏ hơn giới hạn”, mã sau vẫn sai:

```java
if (stock.get() > 0) {
    stock.decrementAndGet(); // kiểm tra và trừ là HAI thao tác
}
```

Hai luồng có thể cùng đọc `1` rồi cả hai trừ, làm `stock = -1`. Sửa bằng **compare-and-set (CAS)**:

```java
public boolean takeOne() {
    for (;;) {
        int current = stock.get();
        if (current == 0) {
            return false;
        }
        if (stock.compareAndSet(current, current - 1)) {
            return true;
        }
        // Có luồng khác cập nhật trước: đọc lại và thử tiếp.
    }
}
```

`compareAndSet(expected, update)` chỉ ghi khi giá trị hiện tại vẫn bằng `expected`. Nếu tranh chấp làm CAS thất bại, vòng lặp đọc lại; vì vậy không thể có hai lần trừ thành công từ cùng một đơn vị hàng. Với quota có thể âm do dữ liệu lỗi, nên kiểm tra `current <= 0`, không chỉ `== 0`; đồng thời validate dữ liệu khởi tạo.

**Giới hạn của atomic:** cập nhật một `AtomicInteger` không bảo vệ đồng thời `reserved`, một `Map`, một giao dịch DB hay thao tác gửi email. Khi bất biến kéo dài qua nhiều trường, có thể dùng một khóa chung hoặc gom các trường thành **một giá trị trạng thái bất biến**.

Các hàm `updateAndGet`/`getAndUpdate` có thể thử lại hàm cập nhật khi cạnh tranh CAS. Hàm cung cấp cho chúng phải **không có side effect** (không ghi log nghiệp vụ, gửi email, trừ tiền, gọi HTTP) vì nó có thể được gọi nhiều lần. `LongAdder` phù hợp bộ đếm thống kê nhiều ghi, nhưng `sum()` không đại diện một snapshot nguyên tử đối với các cập nhật đồng thời; tránh dùng nó khi cần điều kiện quota chính xác.

## 6. `synchronized`: bảo vệ nhiều trường bằng **một** monitor

Khi `available` và `reserved` phải giữ `available + reserved == total`, bao toàn bộ thao tác trong cùng một vùng tới hạn:

```java
private final Object mutex = new Object();
private int available = 10;
private int reserved;

public boolean reserveOne() {
    synchronized (mutex) {
        if (available == 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    }
}

public StockSnapshot snapshot() {
    synchronized (mutex) {
        return new StockSnapshot(available, reserved);
    }
}

public record StockSnapshot(int available, int reserved) {}
```

Đây là đoạn thành viên minh họa cho một class/bean; phần `record` cũng thuộc class đó. Khi cả hai số bắt đầu bằng `10` và `0`, sau mỗi `reserveOne()` thành công, tổng luôn là `10`. Getter phải đồng bộ theo **cùng** `mutex` để nhận ảnh chụp nhất quán. Đối tượng `StockSnapshot` bất biến nên có thể trả ra ngoài khóa.

**Đặc tính cần nhớ:**

- `synchronized (mutex)` dùng monitor của **chính đối tượng `mutex`**; mỗi monitor là một vùng loại trừ độc lập. Hai object `new Object()` khác nhau **không** phối hợp với nhau.
- Khi ra khỏi block, kể cả do exception, JVM tự nhả monitor. Đây là lý do `synchronized` thường là lựa chọn dễ bảo trì.
- `synchronized` có tính reentrant: luồng đang giữ monitor có thể vào lại monitor đó; không có API trực tiếp cho `tryLock(timeout)` hoặc chờ lấy khóa có thể bị interrupt.
- `synchronized` trên `this` hoặc method `synchronized` cũng hợp lệ về mặt ngôn ngữ, nhưng `private final Object mutex` giúp tránh việc code ngoài tình cờ sử dụng cùng monitor. Không khóa trên String literal, boxed integer hay đối tượng dùng chung không do mình sở hữu.
- Giữ vùng khóa ngắn: tính toán/chuyển trạng thái trong RAM; tránh giữ khóa khi chờ mạng, cơ sở dữ liệu, sleep hoặc gọi callback không kiểm soát. Khóa quá rộng làm tăng độ trễ và nguy cơ deadlock.
- Nếu bảo vệ hai đối tượng bằng hai khóa khác nhau, cần thứ tự lấy khóa thống nhất để tránh thread A giữ khóa 1 đợi khóa 2 và thread B giữ khóa 2 đợi khóa 1.

Không cần thêm `volatile` cho `available`/`reserved` nếu **tất cả** truy cập liên quan đều diễn ra dưới cùng monitor; giao thức khóa cung cấp cả visibility lẫn atomicity cần thiết.

## 7. `ReentrantLock`: cùng bài toán, thêm khả năng điều khiển chờ

`java.util.concurrent.locks.Lock` là interface; `ReentrantLock` là implementation phổ biến. Với nhiều trường cùng bất biến, cách bảo vệ giống `synchronized`, chỉ khác phải quản lý vòng đời khóa tường minh:

```java
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

private int available = 10;
private int reserved;

public boolean reserveOne() {
    lock.lock();
    try {
        if (available == 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    } finally {
        lock.unlock();
    }
}
```

Đây là một đoạn thành viên Java minh họa, không phải chương trình độc lập. **Luôn** gọi `unlock()` trong `finally` sau khi chắc chắn đã lấy khóa; nếu có lỗi giữa chừng và quên nhả khóa, các yêu cầu khác có thể bị treo.

`Lock` đáng chọn khi cần:

- `tryLock()`: có thể trả về ngay khi hệ thống bận thay vì chờ.
- `tryLock(timeout, unit)`: chờ tối đa một khoảng thời gian và hỗ trợ interrupt trong thời gian đợi.
- `lockInterruptibly()`: cho phép hủy khi luồng đang chờ lấy khóa.
- `Condition`: nhiều hàng chờ điều kiện gắn với cùng `Lock`, dùng `await()`/`signal()` theo giao thức khóa. `await()` nhả khóa trong lúc chờ và lấy lại trước khi tiếp tục.

Ví dụ riêng cho chính sách “không chờ lâu”:

```java
public boolean reserveWithTimeout(
        int quantity, long timeoutMillis) throws InterruptedException {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    if (!lock.tryLock(timeoutMillis, java.util.concurrent.TimeUnit.MILLISECONDS)) {
        return false; // Hết thời gian đợi lấy khóa.
    }
    try {
        if (available < quantity) {
            return false; // Không đủ hàng.
        }
        available -= quantity;
        reserved += quantity;
        return true;
    } finally {
        lock.unlock();
    }
}
```

Ví dụ trên **giả định** có các field `lock`, `available`, `reserved` như đoạn trước; đây không phải class độc lập. Trong API thật, nên phân biệt “hết thời gian đợi khóa” với “không đủ hàng” bằng enum/result type hoặc lỗi có mã, thay vì gộp vào một `false`.

`new ReentrantLock(true)` yêu cầu chính sách fairness khi có tranh chấp, nhưng có thể giảm throughput và không có nghĩa mọi lệnh lấy khóa đều theo thứ tự tuyệt đối (đặc biệt bản `tryLock()` không timeout). **Không** chọn `ReentrantLock` chỉ vì nghĩ nó luôn nhanh hơn `synchronized`; hãy đo đặc tính tải và chọn theo hành vi cần thiết.

## 8. `AtomicReference` khi nhiều field tạo thành một trạng thái immutable

Một bất biến gồm nhiều trường không bắt buộc phải dùng monitor nếu có thể **gói tất cả trường thành một object immutable** và chỉ thay nguyên trạng thái bằng CAS:

```java
import java.util.concurrent.atomic.AtomicReference;

record StockState(int available, int reserved) {}

final class StockCas {
    private final AtomicReference<StockState> current =
            new AtomicReference<>(new StockState(10, 0));

    boolean reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        for (;;) {
            StockState before = current.get();
            if (before.available() < quantity) {
                return false;
            }
            StockState after = new StockState(
                    before.available() - quantity,
                    before.reserved() + quantity);
            if (current.compareAndSet(before, after)) {
                return true;
            }
        }
    }

    StockState snapshot() {
        return current.get();
    }
}
```

Đây là ví dụ Java 17+ độc lập về cú pháp, gồm top-level package-private `StockState` và `StockCas`; để chạy thử cần thêm một class có `main` hoặc đặt vào test. `StockState` là `record` chỉ có hai số nguyên nên bản thân nó bất biến. Cùng một lần CAS thay cả cặp giá trị `available`/`reserved`, bảo vệ tổng và cung cấp snapshot nhất quán.

**Đánh đổi:** khi tranh chấp cao, CAS có thể phải thử lại và cấp phát nhiều snapshot; nên đo trước khi tối ưu. Vòng CAS không được chứa side effect vì có thể chạy lặp. `AtomicReference` chỉ bảo đảm thao tác trên **tham chiếu** là nguyên tử; nếu tham chiếu trỏ tới `List` hoặc object mutable rồi sửa nó tại chỗ, bạn vẫn có race.

## 9. Chương trình Java 17 chạy được: cùng một tải, ba cách bảo vệ

Ví dụ hoàn chỉnh này cố tình chạy 100 lần “lấy một đơn vị” trên một pool có 8 thread, nhưng mỗi kho chỉ có 10 đơn vị. Nó cho thấy kết quả ổn định dù lịch chạy thread không xác định. `AtomicQuota` bảo vệ **một** số lượng; `MonitorLedger` và `LockLedger` bảo vệ **cặp** `available`/`reserved`.

Lưu **nguyên văn** vào `ConcurrencyChoiceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.BooleanSupplier;

public class ConcurrencyChoiceDemo {

    record Snapshot(int available, int reserved) {}

    static final class AtomicQuota {
        private final AtomicInteger available;

        AtomicQuota(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial < 0");
            }
            available = new AtomicInteger(initial);
        }

        boolean takeOne() {
            for (;;) {
                int before = available.get();
                if (before <= 0) {
                    return false;
                }
                if (available.compareAndSet(before, before - 1)) {
                    return true;
                }
            }
        }

        int remaining() {
            return available.get();
        }
    }

    static final class MonitorLedger {
        private final Object mutex = new Object();
        private int available;
        private int reserved;

        MonitorLedger(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial < 0");
            }
            available = initial;
        }

        boolean reserveOne() {
            synchronized (mutex) {
                if (available == 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            }
        }

        Snapshot snapshot() {
            synchronized (mutex) {
                return new Snapshot(available, reserved);
            }
        }
    }

    static final class LockLedger {
        private final ReentrantLock lock = new ReentrantLock();
        private int available;
        private int reserved;

        LockLedger(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial < 0");
            }
            available = initial;
        }

        boolean reserveOne() {
            lock.lock();
            try {
                if (available == 0) {
                    return false;
                }
                available--;
                reserved++;
                return true;
            } finally {
                lock.unlock();
            }
        }

        Snapshot snapshot() {
            lock.lock();
            try {
                return new Snapshot(available, reserved);
            } finally {
                lock.unlock();
            }
        }
    }

    static int compete(int attempts, BooleanSupplier operation) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();

        try {
            for (int i = 0; i < attempts; i++) {
                results.add(pool.submit(() -> {
                    start.await();
                    return operation.getAsBoolean();
                }));
            }

            start.countDown();
            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    accepted++;
                }
            }
            return accepted;
        } finally {
            start.countDown(); // Tránh để các task đang chờ kẹt nếu có lỗi.
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicQuota atomic = new AtomicQuota(10);
        int atomicAccepted = compete(100, atomic::takeOne);
        System.out.printf(
                "atomic: accepted=%d remaining=%d%n",
                atomicAccepted, atomic.remaining());

        MonitorLedger monitor = new MonitorLedger(10);
        int monitorAccepted = compete(100, monitor::reserveOne);
        Snapshot monitorState = monitor.snapshot();
        System.out.printf(
                "synchronized: accepted=%d available=%d reserved=%d%n",
                monitorAccepted, monitorState.available(), monitorState.reserved());

        LockLedger locking = new LockLedger(10);
        int lockAccepted = compete(100, locking::reserveOne);
        Snapshot lockState = locking.snapshot();
        System.out.printf(
                "lock: accepted=%d available=%d reserved=%d%n",
                lockAccepted, lockState.available(), lockState.reserved());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ConcurrencyChoiceDemo.java
java ConcurrencyChoiceDemo
```

**Stdout chính xác khi chương trình hoàn tất bình thường:**

```text
atomic: accepted=10 remaining=0
synchronized: accepted=10 available=0 reserved=10
lock: accepted=10 available=0 reserved=10
```

Vì mỗi phương án có 10 đơn vị và không nạp lại, **đúng 10** trong 100 lần gọi thành công. Lịch chạy 8 worker và thứ tự request thắng quyền đặt hàng không được xác định, nhưng số lần thành công và trạng thái cuối đều xác định. `CountDownLatch` chỉ giúp nhiều task cùng bắt đầu tranh chấp; chính CAS/monitor/lock mới bảo vệ invariant. Dùng `Future.get()` tại chương trình **thử nghiệm** để chờ tất cả task kết thúc trước khi in, không coi nó là kỹ thuật cần đưa vào request thread của API thực.

Điểm học được từ chương trình:

- `AtomicQuota` chỉ cần bảo vệ **một giá trị** `available`.
- `MonitorLedger` cập nhật hai trường cùng một monitor, và `snapshot()` đọc chúng cùng một monitor.
- `LockLedger` đạt cùng tính đúng đắn với khóa tường minh; lợi ích bổ sung sẽ đến khi cần `tryLock`/timeout/interrupt/condition, không phải vì ví dụ này nhất thiết chạy nhanh hơn.

## 10. Đưa quyết định vào một singleton `@Service`

Đây là phiên bản Spring của bài toán hai trường, dùng monitor private. Đặt trong `src/main/java/com/example/inventory/InventoryService.java` của một ứng dụng Spring Boot có dependency Spring Context (chẳng hạn `spring-boot-starter-web`):

```java
package com.example.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final Object mutex = new Object();
    private int available = 10;
    private int reserved;

    public boolean reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        synchronized (mutex) {
            if (available < quantity) {
                return false;
            }
            available -= quantity;
            reserved += quantity;
            return true;
        }
    }

    public Snapshot snapshot() {
        synchronized (mutex) {
            return new Snapshot(available, reserved);
        }
    }

    public record Snapshot(int available, int reserved) {}
}
```

Đây là **file class hoàn chỉnh để đặt trong dự án Spring**, không phải chương trình có `main` tự chạy bằng `javac` không classpath. Với một instance bean trong một JVM, tất cả request thread đi qua bean này và chỉ truy cập trạng thái bằng hai method trên sẽ không thể làm `available` âm hoặc tạo snapshot có tổng khác 10.

Một controller có thể gọi `reserve(quantity)` rồi trả mã lỗi khi không đủ hàng; controller không cần tự khóa nữa vì service giữ ranh giới nghiệp vụ. Nếu một method khác sửa thẳng `available`/`reserved`, dùng khóa khác, hoặc bean có các bản sao không chia sẻ cùng object, cam kết đó bị phá.

Lựa chọn **tốt hơn nếu không cần state trong RAM** là thiết kế singleton service không giữ số hàng trong field mà giao invariant cho repository/DB. Một singleton stateless cùng transaction/SQL đúng thường dễ vận hành hơn khi có nhiều replica.

### Một vài trường hợp Spring dễ nhầm

- `@Async`, `@Scheduled` và request handler có thể cùng chạm singleton; thread được tạo bởi Spring không tự đồng bộ trạng thái của bean.
- `@Transactional` quản lý transaction của cơ sở dữ liệu theo transaction manager; nó **không** biến phép `++` trên field Java thành nguyên tử, cũng không tạo một mutex JVM cho bean.
- `@Transactional` trên một method cập nhật DB không tự giải quyết mọi race kiểm tra-rồi-ghi; cần mức isolation/locking/version/SQL phù hợp với bất biến.
- Nếu một method thực hiện I/O khi đang giữ `synchronized`/`Lock`, nhiều request khác có thể phải chờ lâu; cân nhắc chia nhỏ hoặc chuyển invariant về nơi dữ liệu thực sự sống.

## 11. Ranh giới của khóa trong JVM: database và nhiều instance

Giả sử chạy **ba replica** Spring Boot, mỗi replica có `InventoryService` riêng. `synchronized (mutex)` ở replica A **không biết** đến lock ở B/C. Nếu cả ba cùng đọc số tồn kho trong DB rồi giảm, một monitor local không ngăn được bán vượt kho.

Với **một bản ghi tồn kho trong DB**, có thể dùng cập nhật có điều kiện và kiểm tra số hàng ảnh hưởng (cú pháp SQL minh họa; áp dụng theo dialect/schema thực tế):

```sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity
WHERE id = :id
  AND available >= :quantity;
```

Nếu `quantity > 0` đã được kiểm tra và đúng **một** hàng bị cập nhật, giao dịch DB đã làm chuyển trạng thái của cùng bản ghi theo điều kiện. Nếu **0** hàng, có thể không đủ hàng hoặc không tìm thấy bản ghi; API phải phân biệt theo nghiệp vụ. Bổ sung DB constraints, transaction, isolation hoặc optimistic locking (`@Version`) tùy schema và điều kiện cạnh tranh; xử lý đúng cách khi version conflict hoặc deadlock phát sinh.

Nếu invariant trải qua **nhiều bảng, nhiều bản ghi hoặc nhiều dịch vụ**, cần lựa chọn ranh giới giao dịch, thứ tự khóa DB, cơ chế đồng bộ liên dịch vụ hoặc quy trình bù trừ phù hợp. Không thể giải quyết invariant phân tán chỉ bằng `AtomicInteger`, `ReentrantLock` hay một annotation trên bean.

## 12. Dấu hiệu chọn sai và cách kiểm thử

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| `volatile int count; count++` | Visibility không bao hàm phép tăng nguyên tử | `AtomicInteger.incrementAndGet()` hoặc khóa |
| `if (atomic.get() > 0) atomic.decrementAndGet()` | Kiểm tra và trừ là hai hành động có thể xen kẽ | Vòng CAS hoặc `updateAndGet` thuần |
| Hai `AtomicInteger` riêng cho `available` và `reserved` | Từng trường atomic nhưng tổng có thể bị quan sát sai và chuyển trạng thái bị tách | Một monitor/lock chung hoặc `AtomicReference` chứa một state immutable |
| Ghi trong `synchronized`, đọc getter không khóa | Getter có thể thấy tổ hợp field không nhất quán | Cùng monitor cho mọi đường đọc/ghi thuộc invariant |
| `Lock.lock()` rồi chỉ `unlock()` cuối nhánh bình thường | Exception làm rò khóa, các thread sau bị treo | `try/finally` |
| Khóa trên `this`, chuỗi literal hoặc object người khác sở hữu | Code ngoài có thể tranh cùng monitor bất ngờ | `private final Object mutex` |
| Vòng CAS gọi HTTP, gửi email hoặc ghi DB | CAS có thể thử lại gây side effect lặp | Chỉ tính toán trạng thái thuần trong vòng CAS; side effect có hợp đồng riêng |
| Mỗi bean/replica có lock riêng cho dữ liệu chung | Không có loại trừ lẫn nhau trên toàn nguồn dữ liệu | Đưa invariant về cùng owner/DB |
| Thêm `@Transactional` để chữa race của field Java | Transaction DB không khóa object trong heap | Chọn primitive JVM đúng, hoặc chuyển state vào DB |
| Khóa bao một request mạng dài | Tăng contention, timeout và nguy cơ deadlock | Thu nhỏ critical section; tránh I/O khi giữ khóa |

### Checklist trước khi đưa vào production

1. **Viết invariant:** ví dụ `available >= 0` và `available + reserved = initialTotal`.
2. **Liệt kê tất cả reader/writer:** request, background jobs, scheduler, listeners, test helpers; không được có đường vòng bỏ khóa.
3. **Chọn đúng owner:** một giá trị → atomic/CAS; một nhóm field một JVM → monitor/lock; nhiều replica → nguồn dữ liệu dùng chung và giao dịch phù hợp.
4. **Kiểm tra thời điểm quan sát:** getter cần snapshot đồng bộ, hoặc đọc một immutable state được công bố nguyên tử.
5. **Xử lý lỗi:** validate số lượng dương, overflow của bộ đếm, từ chối khi thiếu tài nguyên, interrupt khi chờ lock, retry CAS có thể tranh chấp.
6. **Đo đạc:** throughput, tail latency, thời gian chờ khóa, số lần CAS retry; không tối ưu bằng trực giác.
7. **Kiểm thử đồng thời:** cho nhiều thread xuất phát qua `CountDownLatch`/`CyclicBarrier`, đợi mọi `Future`, kiểm tra invariant cuối, lặp thử nhiều lần. Test phát hiện race nhưng không thay thế chứng minh mọi đường truy cập đi theo giao thức khóa.

Với dữ liệu quan trọng, còn cần kiểm thử khi **restart, chạy nhiều instance và giao dịch DB thất bại**. Unit test trong một JVM không chứng minh tính đúng đắn phân tán.

## 13. Tự kiểm tra

1. Một singleton chỉ lưu `AtomicLong requestCount`. Có cần thêm `synchronized` cho `incrementAndGet()` không?  
   **Đáp:** Không, nếu invariant chỉ là từng phép tăng của một biến.
2. Vì sao hai `AtomicInteger available/reserved` không đủ để bảo vệ `available + reserved == total` khi có getter đọc cả hai?  
   **Đáp:** Không có một điểm chuyển trạng thái nguyên tử trên **cặp** giá trị; getter có thể xen vào giữa hai cập nhật.
3. Cần thử lấy khóa tối đa 50 ms và hủy khi interrupt. Chọn gì?  
   **Đáp:** `ReentrantLock.tryLock(50, TimeUnit.MILLISECONDS)` và `unlock()` trong `finally` sau khi lấy khóa thành công.
4. Tại sao `@Service` singleton có thể bị race?  
   **Đáp:** Nhiều request/worker cùng dùng một instance; scope không cung cấp mutex.
5. Có hai replica cùng cập nhật một bản ghi tồn kho DB. `synchronized` trên mỗi replica có đủ không?  
   **Đáp:** Không. Ranh giới bất biến nằm tại nguồn dữ liệu chung; cần thao tác DB bảo đảm đồng thời.
6. Khi nào `AtomicReference<StockState>` hợp lý hơn hai atomic độc lập?  
   **Đáp:** Khi cả hai trường thuộc một immutable snapshot và có thể chuyển toàn trạng thái bằng một CAS thuần, chấp nhận chi phí thử lại.

## 14. Điểm cốt lõi và tài liệu

**Chọn công cụ theo phạm vi bất biến cần bảo vệ:**

- **Một giá trị độc lập:** atomic; nếu cập nhật có điều kiện, dùng CAS đúng cách.
- **Một nhóm trường phải nhất quán trong một JVM:** `synchronized` là lựa chọn mặc định đơn giản; `ReentrantLock` khi cần timeout, interrupt, thử lấy khóa hoặc `Condition`.
- **Một nhóm trường có thể thay bằng một snapshot immutable:** có thể cân nhắc `AtomicReference<State>` với CAS.
- **Dữ liệu nhiều JVM/DB:** dùng cơ chế nhất quán ở nơi dữ liệu sống; khóa của singleton không trải qua nhiều tiến trình.

Tài liệu tham khảo chính thức:

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype và các web scope.
- [Oracle Java 17 — Intrinsic Locks and Synchronization](https://docs.oracle.com/javase/tutorial/essential/concurrency/locksync.html): monitor, lock và visibility.
- [Java SE 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): `compareAndSet`, `getAndUpdate`, ngữ nghĩa atomic.
- [Java SE 17 — `Lock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): `lock`, `tryLock`, `lockInterruptibly`, `unlock`.
- [Java SE 17 — `ReentrantLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): điều khiển khóa và fairness.