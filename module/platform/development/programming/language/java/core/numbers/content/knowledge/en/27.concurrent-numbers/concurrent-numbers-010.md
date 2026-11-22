# Chọn mức đồng bộ theo hợp đồng nhất quán cần có

## 1. Bài toán: “đúng” nghĩa là gì khi nhiều luồng cùng cập nhật số?

Trong ứng dụng đa luồng, nhiều worker có thể đồng thời tăng bộ đếm, cộng tổng doanh thu, trừ hàng tồn kho hoặc cập nhật số lượt và tổng giá trị. Cùng là dữ liệu số, nhưng mỗi nghiệp vụ cần **mức nhất quán khác nhau**:

- Một dashboard chỉ cần số request gần đúng *tại thời điểm quan sát* trong lúc các request vẫn đến.
- Một API cấp số thứ tự yêu cầu mỗi lần cấp nhận một giá trị duy nhất, không làm mất lần tăng.
- Một giao dịch đặt chỗ phải bảo đảm không có hai luồng cùng sử dụng một suất cuối cùng.
- Một báo cáo gồm `count` và `total` phải phản ánh **cùng một trạng thái**; không được đọc `count` mới nhưng `total` cũ nếu chúng có ràng buộc với nhau.

Vì thế câu hỏi đúng trước khi chọn `volatile`, `AtomicLong`, `LongAdder` hay `synchronized` là: **Hợp đồng nhất quán cần bảo đảm điều gì và ở thời điểm nào?**

Bài học này tập trung vào chọn cơ chế đồng bộ cho dữ liệu số trong **một tiến trình JVM** với Java 17+. Đồng bộ giữa nhiều JVM, database và dịch vụ phân tán cần một hợp đồng giao dịch/phối hợp khác; các primitive bên dưới không tự giải quyết phạm vi đó.

## 2. Ba vấn đề nền tảng: atomicity, visibility và ordering

### 2.1. Atomicity — phép cập nhật có bị xen kẽ làm mất dữ liệu không?

```java
class UnsafeCounter {
    private long count;

    void increment() {
        count++; // đọc -> cộng 1 -> ghi; không phải thao tác nguyên tử
    }

    long get() {
        return count;
    }
}
```

Nếu hai luồng cùng đọc `count == 5`, rồi cùng ghi `6`, ứng dụng có thể mất một lần tăng. Đây là **race condition**. Ngay cả khi một lần đọc/ghi `long` được thực hiện nguyên tử trên nền tảng/JVM cụ thể, biểu thức `count++` vẫn là chuỗi thao tác đọc–sửa–ghi và không được bảo vệ khỏi mất cập nhật.

### 2.2. Visibility — luồng khác có nhìn thấy thay đổi không?

Không có quan hệ đồng bộ phù hợp, một luồng có thể tiếp tục dùng giá trị cũ hoặc compiler/CPU/JVM sắp xếp thao tác theo những tối ưu được Java Memory Model (JMM) cho phép. `volatile` bảo đảm khả năng quan sát và các quan hệ thứ tự *happens-before* nhất định:

```java
class ShutdownSignal {
    private volatile boolean stopped;

    void stop() {
        stopped = true;
    }

    void work() {
        while (!stopped) {
            // Kiểm tra tín hiệu dừng từ luồng khác.
        }
    }
}
```

Đoạn code minh họa một tín hiệu; vòng bận (*busy spin*) không nhất thiết là thiết kế tốt cho công việc thật. Có thể dùng blocking queue, interruption hoặc cơ chế phối hợp khác để tránh đốt CPU.

Một phép ghi vào biến `volatile` *happens-before* lần đọc tiếp theo của cùng biến đó quan sát theo quy tắc JMM. Tuy nhiên `volatile` **không** biến `count++` thành nguyên tử và **không** làm cả nhóm biến trở thành một giao dịch.

### 2.3. Ordering — các thao tác có xuất hiện theo thứ tự cần thiết không?

JMM cho phép một số tối ưu sắp xếp lại thao tác khi quan sát từ luồng khác, miễn các quy tắc hợp lệ được giữ. `synchronized`, `volatile`, phép toán atomic và các cấu trúc concurrency chuẩn tạo ra các ranh giới thứ tự/visibility theo hợp đồng của chúng.

Chẳng hạn, một luồng ghi các trường dữ liệu rồi phát tín hiệu qua một biến `volatile`, luồng khác đọc tín hiệu phù hợp rồi đọc dữ liệu sẽ có quan hệ happens-before thích hợp. Điều này chỉ đúng khi toàn bộ quy tắc phát hành/đọc được thực hiện đúng; không phải cứ thêm một biến `volatile` bất kỳ là mọi dữ liệu chia sẻ đều an toàn.

## 3. Chọn mức nhất quán trước khi chọn công cụ

| Hợp đồng cần đạt | Cơ chế thường phù hợp | Bảo đảm chủ yếu |
| --- | --- | --- |
| Một cờ trạng thái độc lập được phát hành/đọc giữa các luồng | `volatile` hoặc `AtomicBoolean` | Visibility và thứ tự phù hợp; không có cập nhật ghép |
| Mỗi lần tăng một bộ đếm đơn phải được ghi nhận, cần kết quả tức thời | `AtomicInteger` / `AtomicLong` | Phép toán atomic cho **một biến** |
| Thống kê tổng số sự kiện với rất nhiều luồng ghi, chấp nhận đọc không phải snapshot nguyên tử khi đang cập nhật | `LongAdder`, `DoubleAdder` | Tổng hợp thông lượng tốt; `sum()` không phải snapshot nguyên tử dưới concurrent update |
| Cần chọn max/min/tổng tích lũy bằng phép gộp nhất quán với nhiều writer | `AtomicLong` với CAS/update, `LongAccumulator` khi phù hợp | Atomic update một trạng thái hoặc phép tích lũy song song có quy tắc |
| Phải kiểm tra điều kiện rồi cập nhật như **một hành động** | `compareAndSet` loop hoặc khóa | Điều kiện và thay đổi cùng một điểm quyết định |
| Nhiều trường liên quan phải luôn thỏa bất biến và snapshot nhất quán | `synchronized`, `ReentrantLock` hoặc trạng thái immutable trong `AtomicReference` | Cập nhật và đọc **cả trạng thái** theo một giao thức |
| Nhiều hàng DB hoặc nhiều dịch vụ phải nhất quán | Giao dịch DB, optimistic locking/version, protocol phân tán | Hợp đồng ngoài phạm vi JVM local |

Các lựa chọn trên là **định hướng**, không phải phép thay thế tự động. `AtomicLong` không chữa lỗi khi một nghiệp vụ trải qua nhiều biến; `LongAdder` không phù hợp để cấp mã thứ tự chính xác tại thời điểm tăng; khóa có thể an toàn nhưng làm giảm khả năng chạy song song nếu phạm vi quá rộng.

## 4. Trường hợp 1 — Chỉ cần nhìn thấy một trạng thái

Đối với một cờ độc lập như `enabled`, `stopped` hay `ready`, `volatile boolean` thường đủ nếu tất cả thao tác chỉ là ghi/đọc trạng thái và giao thức phát hành phù hợp.

```java
private volatile boolean enabled = true;

// Luồng điều khiển:
enabled = false;

// Các worker:
if (!enabled) {
    return;
}
```

Đây là các đoạn nhúng của một lớp, không phải một chương trình Java độc lập.

**Phân biệt với điều kiện đọc–rồi–ghi:** nếu hai worker cần “chỉ một người chuyển từ `false` sang `true` và thực thi công việc”, đoạn:

```java
if (!started) {
    started = true;
    startJob();
}
```

vẫn có race ngay cả khi `started` là `volatile`. Hai luồng có thể cùng đọc `false`. Hợp đồng “chỉ một luồng thắng” cần một hành động nguyên tử:

```java
AtomicBoolean started = new AtomicBoolean(false);

if (started.compareAndSet(false, true)) {
    startJob(); // chỉ luồng đổi false -> true thành công chạy
}
```

Đoạn này cần `import java.util.concurrent.atomic.AtomicBoolean;`. `compareAndSet` thực hiện phép đổi có điều kiện atomically trên một biến. Với công việc có thể thất bại, cần thêm thiết kế phục hồi trạng thái `started`/retry phù hợp; CAS chỉ giải quyết quyền bắt đầu một lần, không tự tạo workflow tin cậy.

## 5. Trường hợp 2 — Bộ đếm đơn cần kết quả chính xác tại điểm quan sát

`AtomicInteger` và `AtomicLong` hữu ích khi tất cả thông tin phải bảo vệ nằm trong **một giá trị**:

```java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong count = new AtomicLong(0);

long afterIncrement = count.incrementAndGet();
long beforeIncrement = count.getAndIncrement();
long current = count.get();
```

Mỗi lời gọi atomic cập nhật/đọc trạng thái của biến đó theo thứ tự nhất quán (*linearizable*), không mất tăng nếu mọi worker cùng dùng đúng biến. `getAndIncrement()` trả giá trị cũ; `incrementAndGet()` trả giá trị mới.

Tuy nhiên hai lời gọi liên tiếp **không tạo ra một transaction**. Ví dụ:

```java
if (count.get() < 100) {
    count.incrementAndGet(); // vẫn có thể vượt 100 vì một worker khác xen vào
}
```

Cả `get()` và `incrementAndGet()` đều nguyên tử riêng lẻ, nhưng phép **kiểm tra–rồi–cập nhật** chưa được thực hiện nguyên tử.

### 5.1. Dùng CAS cho cập nhật có điều kiện

Ví dụ một bộ đếm quota có giới hạn `limit`:

```java
static boolean tryClaim(AtomicInteger used, int limit) {
    if (limit < 0) {
        throw new IllegalArgumentException("limit phải không âm");
    }

    while (true) {
        int current = used.get();
        if (current >= limit) {
            return false;
        }
        if (used.compareAndSet(current, current + 1)) {
            return true;
        }
        // Một luồng khác đã đổi used: đọc lại và thử tiếp.
    }
}
```

Đây là **phương thức nhúng** cần `import java.util.concurrent.atomic.AtomicInteger;`. Giả thiết `used` được tạo với số không âm và chỉ được thay đổi theo giao thức hợp lệ. Với giới hạn `int` dương không vượt miền, phép cộng tránh tràn khi `current < limit`. Việc `compareAndSet` thành công là **điểm tuyến tính hóa** cho thao tác nhận một suất; mọi luồng tranh chấp một suất cuối cùng sẽ không thể cùng thắng nếu cùng dùng `used`.

CAS loop có thể thử lại nhiều lần dưới tranh chấp và yêu cầu xử lý đúng state/overflow. Nếu nghiệp vụ gồm nhiều biến, một CAS trên `used` không đủ; cần đưa toàn bộ trạng thái vào cùng một đối tượng immutable cập nhật atomically hoặc sử dụng khóa.

### 5.2. `updateAndGet` và tác dụng phụ

```java
AtomicLong maxSeen = new AtomicLong(0);

long newMax = maxSeen.updateAndGet(
        current -> Math.max(current, 42L));
```

Lambda cập nhật của một số phương thức atomic **có thể được gọi lại** khi tranh chấp. Nó phải không có tác dụng phụ: tránh gọi API thanh toán, ghi DB, gửi email hoặc tăng một bộ đếm khác trong lambda. Chỉ tính trạng thái mới từ trạng thái cũ; thực hiện side effect sau khi xác định kết quả theo thiết kế nghiệp vụ.

`AtomicLong` có thể tràn số như `long` bình thường; tính nguyên tử **không** bổ sung kiểm tra tràn tự động. Nếu lượng đếm không được phép quay vòng, đưa kiểm tra/ngoại lệ tràn vào một cập nhật nguyên tử được thiết kế đúng.

## 6. Trường hợp 3 — Thống kê có rất nhiều writer: `LongAdder`

Với mục tiêu như “đếm số request đã thấy” trong hệ thống có nhiều luồng, `LongAdder` phân tán cập nhật nội bộ để giảm tranh chấp trên một điểm nóng:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();

requests.increment();
requests.add(5L);

long currentlyObserved = requests.sum();
```

**Hợp đồng quan trọng:** `LongAdder.sum()` **không phải snapshot nguyên tử** khi nhiều luồng đang cập nhật. Kết quả có thể không gồm đồng thời mọi cập nhật đang diễn ra. Nếu bạn cần kiểm tra giới hạn quota ở đúng thời điểm mỗi cập nhật hoặc cần một giá trị trả về duy nhất sau mỗi `increment`, hãy dùng cơ chế có hợp đồng atomic phù hợp, không dùng `LongAdder` thay `AtomicLong` một cách máy móc.

Sau khi tất cả writer hoàn tất và có quan hệ đồng bộ xác nhận hoàn tất (chẳng hạn chờ mọi `Future.get()`), `sum()` phản ánh các cập nhật đã kết thúc. Ví dụ ở mục 9 kiểm chứng điều này.

`LongAdder.reset()` và `sumThenReset()` cũng không nên dùng để giả định có **snapshot chính xác khi writer còn đang cập nhật**. Hãy áp dụng chúng khi không có concurrent updates, hoặc khi nghiệp vụ chấp nhận số liệu chỉ mang tính giám sát theo từng khoảng không hoàn toàn sắc nét.

Nếu giá trị là số thực, `DoubleAdder` có ý tưởng tương tự, nhưng do thứ tự cộng dấu phẩy động có thể khác nhau giữa các luồng, kết quả không bảo đảm trùng bit qua những lần chạy.

### 6.1. Bộ đếm theo nhãn trong `ConcurrentHashMap`

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();

counts.computeIfAbsent("success", key -> new LongAdder()).increment();
counts.computeIfAbsent("failure", key -> new LongAdder()).increment();

long success = counts.get("success").sum();
```

`computeIfAbsent` tạo/tra cứu giá trị theo khóa an toàn với concurrent access trên `ConcurrentHashMap`. Mỗi `LongAdder` tiếp tục ghi nhận các lần tăng. Nhưng đọc nhiều nhãn liên tiếp **không tạo thành một snapshot toàn map**; tổng các nhãn quan sát khi cập nhật đang diễn ra có thể không khớp bộ đếm toàn hệ thống tại một thời điểm duy nhất.

Nếu cần “thành công + thất bại = tổng số request” tại cùng một snapshot chuẩn để đối soát, hãy thiết kế cơ chế snapshot nhất quán hoặc lấy kết quả sau khi toàn bộ kỳ ghi đã kết thúc.

## 7. Trường hợp 4 — Nhiều giá trị phải giữ chung một bất biến

Giả sử mỗi giao dịch được chấp nhận làm đồng thời hai việc:

1. Tăng `count` lên 1.
2. Tăng `total` thêm 2 đơn vị.

Bất biến nghiệp vụ yêu cầu một snapshot phải luôn thỏa `total == 2 * count`. Hai `AtomicLong` riêng biệt không đủ để bảo đảm đọc được một cặp trạng thái nhất quán:

```java
AtomicLong count = new AtomicLong();
AtomicLong total = new AtomicLong();

// Writer:
count.incrementAndGet();
total.addAndGet(2);

// Reader:
long seenCount = count.get();
long seenTotal = total.get();
// Hai giá trị trên có thể đến từ hai thời điểm khác nhau.
```

Mỗi biến cập nhật nguyên tử, nhưng **cả cặp không được cập nhật cùng một lúc**. Reader có thể quan sát `count` mới và `total` cũ. `volatile` trên cả hai trường cũng không biến hai lời ghi thành một giao dịch.

### 7.1. `synchronized`: một khóa bảo vệ toàn bộ trạng thái

```java
record Snapshot(long count, long total) {}

final class Ledger {
    private long count;
    private long total;

    synchronized void add(long value) {
        count++;
        total += value;
    }

    synchronized Snapshot snapshot() {
        return new Snapshot(count, total);
    }
}
```

Đây là một ví dụ lớp/record có thể đặt vào chương trình cùng package. Mọi writer gọi `add`, mọi reader lấy cặp bằng `snapshot`, và **không có đường truy cập khác bỏ qua khóa**. Khi đó việc sửa hai trường và việc đọc hai trường được tuần tự hóa qua cùng monitor.

`snapshot()` trả về một record bất biến chứa **cặp giá trị được đọc trong cùng critical section**. Ngay khi monitor được thả, worker khác có thể cập nhật Ledger; snapshot có thể trở nên cũ nhưng vẫn **nhất quán nội tại**. Cũ không đồng nghĩa với bị rách giữa các trường.

Nếu chỉ đánh dấu `add` là `synchronized` nhưng `snapshot` đọc trường trực tiếp không đồng bộ, chưa có hợp đồng đầy đủ cho việc đọc cùng một trạng thái. Tất cả đường truy cập phải tuân thủ cùng giao thức bảo vệ.

### 7.2. Khóa tường minh khi cần điều khiển phức tạp hơn

`ReentrantLock` cũng có thể bảo vệ cùng invariant:

```java
import java.util.concurrent.locks.ReentrantLock;

final class LockedTotal {
    private final ReentrantLock lock = new ReentrantLock();
    private long count;

    void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock();
        }
    }

    long snapshot() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
```

Dùng `try/finally` để bảo đảm giải phóng khóa khi có ngoại lệ. `ReentrantLock` phù hợp nếu cần `tryLock`, khóa có thể bị ngắt khi chờ, nhiều condition hoặc mức điều khiển cao hơn. Với một invariant đơn giản, `synchronized` thường dễ đọc và ít nơi viết sai hơn.

Khi nhiều khóa xuất hiện, phải định nghĩa thứ tự giữ khóa để tránh deadlock; không giữ khóa quá rộng trong khi chờ I/O, gọi dịch vụ chậm hoặc chạy callback không kiểm soát.

`ReadWriteLock` có thể hỗ trợ nhiều reader đồng thời khi đọc chiếm ưu thế và thao tác được tổ chức đúng, nhưng không bảo đảm luôn nhanh hơn monitor; chi phí lock và contention phụ thuộc workload.

### 7.3. State immutable trong một `AtomicReference`

Một lựa chọn khác cho một cặp trạng thái là biểu diễn **toàn bộ invariant thành một đối tượng immutable** và thay cả đối tượng trong một thao tác atomic:

```java
import java.util.concurrent.atomic.AtomicReference;

record State(long count, long total) {}

AtomicReference<State> state =
        new AtomicReference<>(new State(0L, 0L));

state.updateAndGet(previous ->
        new State(previous.count() + 1, previous.total() + 2));

State snapshot = state.get();
```

Đây là đoạn nhúng. Đọc `state.get()` cho một bản snapshot nhất quán của **cả hai trường trong đối tượng immutable**. `updateAndGet` có thể gọi lambda nhiều lần khi tranh chấp; lambda phải thuần túy và không thực hiện side effect. Mỗi bản cập nhật tạo đối tượng mới nên có chi phí cấp phát và retry; không mặc định giải pháp này tốt hơn một khóa cho mọi tải.

Nếu invariant nằm trong nhiều đối tượng hoặc tài nguyên ngoài JVM (tài khoản DB, message broker), atomic publication của một `State` trong JVM không đủ để tạo transaction toàn hệ thống.

## 8. `happens-before`, thời điểm quan sát và ranh giới một phép toán

Một hợp đồng nhất quán cần nêu rõ **khi nào** caller được phép coi dữ liệu là hoàn tất.

Trong Java, các quan hệ happens-before thường gặp gồm:

- Một monitor unlock *happens-before* lần lock tiếp theo trên cùng monitor.
- Một ghi `volatile` *happens-before* một đọc phù hợp sau đó trên biến volatile đó.
- Các lớp atomic và cấu trúc trong `java.util.concurrent` cung cấp các bảo đảm bộ nhớ theo tài liệu API.
- Tác động của một task trong executor xảy ra trước khi một luồng khác nhận kết quả thông qua `Future.get()` theo quy tắc memory consistency của API.

Khi đã đợi **toàn bộ** `Future.get()` hoàn tất, một reader có thể lấy tổng cuối của các bộ đếm mà không còn concurrent writer từ chính nhóm tác vụ đó. Trái lại, đọc giữa chừng từ nhiều cấu trúc riêng biệt có thể không phản ánh một thời điểm chung, dù mỗi cấu trúc riêng lẻ thread-safe.

### Phân biệt ba hợp đồng thường bị nhầm

**An toàn khỏi data race:** Các truy cập được đồng bộ đúng; không bị đọc/ghi sai theo JMM.

**Atomic/linearizable cho một thao tác:** Lời gọi đơn như `AtomicLong.incrementAndGet()` có thể được hiểu như xảy ra tại một điểm giữa lúc bắt đầu và lúc trả về.

**Snapshot nhất quán của nhiều biến:** Tất cả thành phần phải đến từ cùng một trạng thái hợp lệ (chẳng hạn cùng monitor hoặc cùng đối tượng immutable được publish atomically).

Một hệ thống có thể đáp ứng tiêu chí thứ nhất và thứ hai cho từng biến nhưng vẫn vi phạm tiêu chí thứ ba. Đây chính là lý do **chọn mức đồng bộ theo hợp đồng**, thay vì chỉ hỏi “có thread-safe không?”.

## 9. Chương trình Java 17+ hoàn chỉnh: so sánh `AtomicLong`, `LongAdder`, snapshot có khóa

Lưu file **`ConsistencyContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public class ConsistencyContractDemo {
    record Snapshot(long count, long total) {}

    static final class Ledger {
        private long count;
        private long total;

        public synchronized void add(long value) {
            count++;
            total += value;
        }

        public synchronized Snapshot snapshot() {
            return new Snapshot(count, total);
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        int workers = 4;
        int iterations = 10_000;

        AtomicLong atomicCount = new AtomicLong();
        LongAdder adderCount = new LongAdder();
        Ledger ledger = new Ledger();

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        try {
            List<Future<?>> futures = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    for (int j = 0; j < iterations; j++) {
                        atomicCount.incrementAndGet();
                        adderCount.increment();
                        ledger.add(2);
                    }
                }));
            }

            // Chờ mọi writer hoàn tất trước khi đọc số liệu cuối.
            for (Future<?> future : futures) {
                future.get();
            }

            Snapshot snapshot = ledger.snapshot();

            System.out.println("atomic count = " + atomicCount.get());
            System.out.println("adder count = " + adderCount.sum());
            System.out.println("snapshot count = " + snapshot.count());
            System.out.println("snapshot total = " + snapshot.total());
            System.out.println("snapshot invariant = "
                    + (snapshot.total() == 2 * snapshot.count()));
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ConsistencyContractDemo.java
java ConsistencyContractDemo
```

Stdout chính xác khi các tác vụ hoàn tất bình thường:

```text
atomic count = 40000
adder count = 40000
snapshot count = 40000
snapshot total = 80000
snapshot invariant = true
```

**Cơ chế và ý nghĩa kết quả:**

1. Bốn worker, mỗi worker chạy 10.000 vòng. Tổng số vòng là 40.000.
2. `AtomicLong` nhận một phép tăng nguyên tử ở mỗi vòng; nó phù hợp nếu cần đọc một counter chính xác tại một thời điểm quan sát.
3. `LongAdder` cũng nhận 40.000 lần tăng. `sum()` được đọc **sau khi** tất cả `Future.get()` hoàn tất, nên kết quả cuối là 40.000. Đọc khi còn writer sẽ không có hợp đồng snapshot atomic.
4. `Ledger.add(2)` bảo vệ cùng lúc `count++` và `total += 2`; `snapshot()` giữ cùng monitor khi chụp cả hai giá trị. Bất biến `total == 2 * count` được bảo toàn trong snapshot.
5. Mặc dù ba loại bộ đếm cho cùng tổng cuối, **ba lời gọi trong mỗi vòng không phải giao dịch chung**. Nếu đọc đồng thời khi worker còn chạy, `atomicCount`, `adderCount` và `ledger` có thể báo khác nhau vì chúng được cập nhật nối tiếp. Ví dụ minh họa các hợp đồng riêng biệt, không xác nhận ba nguồn luôn đồng nhất tức thời.

Chương trình dùng `try/finally` để gọi `shutdown()` cho executor trong Java 17. Ứng dụng thực tế còn cần chính sách về timeout, hủy task, interruption và chờ shutdown phù hợp; `shutdown()` không có nghĩa chờ tất cả task hoàn tất. Ở đây vòng `Future.get()` đã đợi các task được gửi trước khi đọc.

## 10. Những quyết định có thể làm mất tính nhất quán

### 10.1. Chia một invariant thành nhiều primitive atomic

Nếu `availableSlots` và `reservedSlots` phải cùng nhau thỏa tổng cố định, cập nhật riêng hai `AtomicInteger` có thể tạo ra khoảng thời gian mà reader thấy cặp không hợp lệ. Để bảo vệ trạng thái liên quan, dùng một lock chung hoặc một snapshot immutable duy nhất trong `AtomicReference`.

### 10.2. Đặt `volatile` cho `int` rồi gọi `++`

`volatile int count` vẫn không biến thao tác `count++` thành nguyên tử. Chọn `AtomicInteger.incrementAndGet()` hoặc monitor nếu số đếm phải phản ánh mọi lần tăng.

### 10.3. Dùng `LongAdder.sum()` để quyết định “còn quota không?”

`sum()` trong lúc cập nhật không bảo đảm snapshot tuyến tính hóa; logic “`if(sum() < limit) increment()`” có cả vấn đề snapshot lẫn vấn đề check-then-act. Dùng CAS/lock/giao dịch thiết kế cho reservation.

### 10.4. Bảo vệ writer nhưng bỏ quên reader

`synchronized void update()` không giúp phương thức đọc trực tiếp trường không có đồng bộ trở thành snapshot nhất quán. Phải bảo vệ **tất cả** đường đọc/ghi của state theo cùng giao thức.

### 10.5. Giữ lock trong lúc gọi dịch vụ ngoài

Gọi database, HTTP API hoặc mã callback không kiểm soát trong lock có thể kéo dài critical section, gây contention và rủi ro deadlock. Khi cần tính nguyên tử qua tài nguyên ngoài, không thể đơn thuần “bọc cả API call bằng synchronized” và mong transaction phân tán xuất hiện.

### 10.6. Cho rằng `ConcurrentHashMap` làm nguyên tử mọi thao tác ghép

`ConcurrentHashMap.compute`, `putIfAbsent` và các thao tác theo khóa có hợp đồng đồng thời riêng, nhưng tính thread-safe của map không làm thao tác trên **nhiều khóa** trở thành một transaction. Ví dụ chuyển giá trị giữa hai tài khoản ở hai khóa cần giao thức nhất quán lớn hơn.

### 10.7. Quên tràn số, sai số số thực và định nghĩa chính xác

`AtomicLong` giữ atomicity nhưng không ngăn phép cộng `long` tràn miền. `DoubleAdder` là tổng dấu phẩy động, có thể khác bit vì thứ tự cộng không cố định. Nếu cộng tiền, chọn kiểu số và thiết kế nhất quán phù hợp (chẳng hạn integer minor units trong miền không tràn, hoặc `BigDecimal` sau khi xét yêu cầu hiệu năng); concurrency primitive không tự sửa độ chính xác số học.

## 11. Đo lường và kiểm thử hợp đồng

**Trước khi benchmark**, viết các assertion theo hợp đồng. Ví dụ với trường hợp tổng cuối như bài demo: khi tất cả task đã hoàn tất, `atomicCount.get() == workers * iterations`, `adderCount.sum() == workers * iterations`, `snapshot.total() == 2 * snapshot.count()`.

Nếu reader đọc giữa lúc còn writer, chỉ kiểm tra bất biến **được cơ chế thực sự bảo đảm**. Với `Ledger`, mọi snapshot phải nhất quán nội tại. Không kiểm tra ba cấu trúc độc lập luôn có cùng count tại từng thời điểm vì chương trình chưa hề tạo transaction giữa chúng.

Kiểm thử race nên chạy đủ thread, nhiều vòng và dữ liệu khác nhau, nhưng việc chạy 100 lần không lộ lỗi **không chứng minh** một chương trình thiếu đồng bộ là đúng. Lập luận theo happens-before, atomicity và invariant mới là cốt lõi; công cụ concurrency testing có thể hỗ trợ tìm interleaving khó thấy.

Về hiệu năng, cần xem xét:

- Số writer cạnh tranh, tần suất cập nhật, số lần đọc giá trị.
- Chi phí lock contention, allocation cho immutable state và CAS retry.
- Tỷ lệ read/write và phạm vi critical section.
- Yêu cầu throughput hay latency, môi trường CPU/JVM/JIT cụ thể.
- Giá trị kinh doanh của việc đọc một snapshot chính xác thay vì số liệu giám sát gần đúng.

`LongAdder` có thể cho thông lượng tốt ở điểm nóng nhiều writer, nhưng không có “nhanh hơn N lần” cố định. Dùng benchmark như JMH cho so sánh vi mô, đo workload thật cho quyết định kiến trúc.

## 12. Checklist quyết định cho một dữ liệu số dùng chung

Khi nhận yêu cầu mới, có thể tự trả lời tuần tự:

1. **State nào được chia sẻ?** Một cờ, một số, một cặp số, một map, hay giao dịch giữa dịch vụ?
2. **Phải đúng ở thời điểm nào?** Trong từng lần cập nhật, khi reader gọi API, khi hết một batch hay chỉ cuối kỳ?
3. **Đọc giá trị “gần đúng khi đang ghi” có được không?** Nếu có, bộ đếm thống kê kiểu `LongAdder` có thể phù hợp. Nếu không, cần cơ chế snapshot rõ ràng.
4. **Có bước kiểm tra rồi thay đổi không?** CAS/lock cần bao phủ cả hai, tránh `get` rồi `set` tách biệt.
5. **Có invariant giữa nhiều trường không?** Bảo vệ cùng một critical section hoặc publish immutable state atomically.
6. **Phạm vi chỉ trong một JVM?** Nếu DB hoặc dịch vụ khác cùng tham gia, cần thiết kế transaction/idempotency/version ngoài JVM.
7. **Ai được phép ghi, ai được phép đọc?** Cô lập state, thống nhất giao thức; không để “đường tắt” đọc/ghi bypass synchronization.
8. **Kiểu số có đủ miền và độ chính xác?** Chống tràn số, phân biệt `double` và thập phân chính xác; đồng bộ không thay thế chính sách số học.

Bảng tóm lược nhanh:

| Bạn cần | Ưu tiên xem xét |
| --- | --- |
| Tín hiệu dừng/ready đơn giản | `volatile`/`AtomicBoolean` |
| Mọi lần tăng một giá trị được tính đúng, đọc atomic | `AtomicLong`/`AtomicInteger` |
| Rất nhiều writer cập nhật metric, `sum()` chỉ cần quan sát | `LongAdder`/`DoubleAdder` |
| Cấp suất theo điều kiện | CAS loop hoặc lock bao trọn check–update |
| Nhiều trường có invariant và snapshot | `synchronized`, `ReentrantLock`, hoặc `AtomicReference` tới immutable state |
| Đối soát giữa nhiều JVM hoặc DB | Giao dịch, versioning, giao thức phân tán phù hợp |

## 13. Bài tập tự luyện

1. Tại sao `volatile int count; count++;` vẫn có thể mất lượt tăng? Hãy mô tả hai interleaving của hai worker.
2. Một dịch vụ cần cấp 100 vé và không vượt quá 100. Vì sao `if (atomic.get() < 100) atomic.incrementAndGet()` chưa đúng? Hãy dùng CAS để thiết kế phép claim.
3. Dashboard hiển thị tổng request/s mỗi giây với hàng trăm worker. Có cần snapshot tuyến tính hóa của từng lần đọc hay `LongAdder.sum()` là đủ? Câu trả lời phụ thuộc hợp đồng nào?
4. `successCount` và `failedCount` được tăng trong hai cấu trúc khác nhau. Tại sao đọc hai bộ đếm liên tiếp không chắc tạo cùng snapshot?
5. Nếu thay `Ledger` của bài demo bằng hai `AtomicLong`, invariant `total == 2 * count` còn được bảo đảm tại mọi lần đọc trong lúc cập nhật không? Giải thích.
6. Viết phiên bản `Ledger` dùng `AtomicReference<State>` với `record State(long count, long total)`. Chứng minh lambda update không có side effect.
7. Vì sao `Future.get()` của tất cả worker thay đổi điều có thể khẳng định về tổng cuối, nhưng **không** biến các cập nhật lúc đang chạy thành giao dịch xuyên ba bộ đếm?
8. Một service có hai bản sao JVM và cùng thay đổi một hàng tồn kho trong DB. Vì sao `synchronized` trong mỗi bản sao không đủ? Đề xuất ranh giới transaction thích hợp.

**Gợi ý trả lời:** (1) `++` gồm đọc–tính–ghi; hai luồng có thể cùng đọc giá trị cũ. (2) Cần CAS có điều kiện trên cùng biến. (3) Nếu giám sát chấp nhận số liệu trong lúc writer đang cập nhật không tuyến tính hóa, LongAdder có thể hợp lệ. (4) Mỗi lần đọc xảy ra ở thời điểm khác nhau, không có snapshot chung. (5) Không, các cập nhật và đọc hai biến không nguyên tử như một nhóm. (6) AtomicReference publish cặp immutable trong một lần thay đổi; lambda có thể chạy lại. (7) Sau khi tất cả task xong thì không còn writer từ nhóm đó, nhưng quá trình giữa chừng vẫn có thể khác thời điểm. (8) Khóa JVM chỉ có hiệu lực trong tiến trình; transaction/row lock/version tại DB bảo vệ trạng thái dùng chung.

## 14. Ghi nhớ khi áp dụng

Chọn cơ chế đồng bộ bắt đầu từ **đơn vị bất biến của nghiệp vụ**, rồi mới cân nhắc hiệu năng. Một cờ cần visibility, một bộ đếm cần atomic increment, thống kê có thể chấp nhận phép đọc trong lúc cập nhật không tuyến tính hóa, còn một nhóm biến phải được cập nhật và quan sát theo một giao thức thống nhất. Đảm bảo mỗi caller hiểu trạng thái được hứa hẹn là **một giá trị chính xác**, **một snapshot nội tại nhất quán**, hay **một số liệu giám sát tại thời điểm quan sát**.

Tài liệu Java SE 17:
- [`java.util.concurrent.atomic`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html) (`AtomicLong`, `AtomicReference`, `LongAdder`).
- [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html).
