# Đánh giá ReentrantLock cho điểm nghẽn đã đo được trên JDK 21

`ReentrantLock` là một cơ chế khóa tường minh trong `java.util.concurrent.locks`. Trên JDK 21, nó đáng được đánh giá khi dữ liệu profiling cho thấy virtual thread bị pin trong vùng `synchronized` có thao tác blocking, hoặc khi ứng dụng cần các khả năng mà intrinsic monitor không cung cấp như chờ khóa có thể interrupt, timeout, `tryLock()` hay nhiều `Condition`.

Không nên thay mọi `synchronized` bằng `ReentrantLock` chỉ vì ứng dụng sử dụng virtual thread. `synchronized` vẫn là lựa chọn đơn giản và đúng đắn cho nhiều vùng bảo vệ trạng thái ngắn. Việc đổi khóa chỉ có ý nghĩa khi đã xác định được điểm nghẽn, có thể giữ nguyên tính đúng đắn của đồng bộ hóa và benchmark chứng minh cải thiện trên tải đại diện.

## Vì sao ReentrantLock đáng được xem xét với virtual thread trên JDK 21?

Trong JDK 21, virtual thread có thể bị pin vào carrier khi nó thực hiện thao tác blocking trong lúc đang chạy bên trong `synchronized` block hoặc method, hoặc khi thực hiện native call. Khi bị pin, virtual thread không thể unmount khỏi carrier trong khoảng blocking đó. Carrier bị giữ lại và không thể chạy virtual thread khác trong thời gian này.

`ReentrantLock` triển khai cơ chế chờ dựa trên các primitive như `LockSupport.park()`. Khi một virtual thread phải chờ lấy khóa hoặc chờ trên `Condition`, cơ chế park được tích hợp với scheduler virtual thread, nên virtual thread thường có thể unmount và nhường carrier. Điều này giúp tránh kiểu pinning do chờ monitor trong trường hợp tương ứng.

| Tình huống | `synchronized` trên JDK 21 | `ReentrantLock` |
| --- | --- | --- |
| Virtual thread bị block trong synchronized block/method | Có thể bị pin vào carrier | Chờ khóa qua cơ chế park có thể unmount khỏi carrier |
| Virtual thread thực hiện blocking khi đang ở trong vùng được khóa | Có thể bị pin vào carrier | Bản thân việc giữ `ReentrantLock` không tạo monitor pinning; thao tác blocking vẫn phải được đánh giá riêng |
| Cần thử lấy khóa ngay hoặc chờ có timeout | Không có API tương đương trực tiếp | Có `tryLock()` và `tryLock(timeout, unit)` |
| Cần chờ khóa có thể interrupt | Không có thao tác chờ monitor tương đương `lockInterruptibly()` | Có `lockInterruptibly()` |
| Quản lý khóa | JVM tự giải phóng monitor khi thoát block/method | Mã phải gọi `unlock()` đúng cách |

Điều này không có nghĩa `ReentrantLock` loại bỏ mọi pinning. Nếu virtual thread gọi native code hoặc bước vào một `synchronized` block khác trong lúc blocking, các nguyên nhân pinning đó vẫn tồn tại. Hơn nữa, một virtual thread có thể unmount khi chờ I/O trong lúc vẫn giữ `ReentrantLock`, nhưng khóa vẫn bị giữ; các tác vụ khác cần khóa đó vẫn phải chờ. Carrier được giải phóng không đồng nghĩa với tài nguyên được giải phóng hoặc throughput tăng.

## Trước tiên phải xác định đúng loại điểm nghẽn

Có ít nhất ba vấn đề dễ bị gọi chung là “lock chậm”, nhưng cần cách xử lý khác nhau:

1. **Pinning carrier:** virtual thread bị giữ trên carrier khi blocking trong `synchronized` hoặc native code. JFR có thể giúp xác định sự kiện pinning.
2. **Contention trên khóa:** nhiều tác vụ cạnh tranh cùng một vùng dữ liệu. Dù dùng `ReentrantLock`, tại một thời điểm chỉ một chủ sở hữu được vào critical section; đổi loại khóa không tự tăng mức song song của vùng đó.
3. **Critical section quá dài:** khóa được giữ trong lúc làm I/O, gọi dịch vụ hoặc thực hiện tính toán lâu. Cần xem xét giảm phạm vi khóa và tách công việc bên ngoài ra, thay vì chỉ đổi API khóa.

Trước khi thay đổi, hãy ghi nhận thời gian chờ khóa, thời gian giữ khóa, số virtual thread bị pin, số carrier bận và tác động đến latency/throughput. Nếu không có bằng chứng cho thấy monitor pinning hoặc lock contention ảnh hưởng mục tiêu vận hành, giữ `synchronized` thường là lựa chọn dễ bảo trì hơn.

## Ví dụ: vùng synchronized có thao tác blocking

Giả sử một cache bảo vệ dữ liệu bằng monitor, nhưng trong cùng vùng khóa lại gọi một dịch vụ bên ngoài:

```java
record Customer(String id) {}

interface CustomerService {
    Customer fetch(String customerId) throws InterruptedException;
}

final class CustomerCache {
    private final CustomerService customerService;
    private Customer cached;

    CustomerCache(CustomerService customerService) {
        this.customerService = customerService;
    }

    synchronized Customer load(String customerId) throws InterruptedException {
        if (cached != null && cached.id().equals(customerId)) {
            return cached;
        }

        // Giả sử lời gọi này có thể chờ I/O lâu.
        cached = customerService.fetch(customerId);
        return cached;
    }
}
```

Nếu virtual thread bị block trong lời gọi `fetch()` khi vẫn đang thực thi bên trong synchronized method, nó có thể bị pin vào carrier trên JDK 21. Ngoài pinning, monitor còn bị giữ trong toàn bộ thời gian gọi dịch vụ, khiến các yêu cầu khác không thể vào vùng đó.

Có thể đánh giá `ReentrantLock` nếu không thể bỏ đồng bộ hóa và việc pinning đã được đo thấy. Tuy nhiên, bước đầu tiên nên là kiểm tra xem có thể đưa I/O ra ngoài vùng khóa hay không. Ví dụ, dùng khóa để kiểm tra/cập nhật trạng thái ngắn, còn thao tác mạng thực hiện ngoài khóa; cách này thường giảm cả thời gian giữ khóa lẫn nguy cơ pinning.

## Dùng ReentrantLock đúng cách

Khác với `synchronized`, `ReentrantLock` yêu cầu giải phóng khóa tường minh. Mẫu cơ bản luôn đặt `unlock()` trong `finally`:

```java
import java.util.concurrent.locks.ReentrantLock;

final class Inventory {
    private final ReentrantLock lock = new ReentrantLock();
    private int available;

    Inventory(int initialQuantity) {
        this.available = initialQuantity;
    }

    boolean reserve(int quantity) throws InterruptedException {
        lock.lockInterruptibly();
        try {
            if (quantity <= 0 || available < quantity) {
                return false;
            }

            available -= quantity;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
```

`lockInterruptibly()` chờ lấy khóa nhưng cho phép hủy việc chờ bằng interruption. Nếu thread bị interrupt trước hoặc trong lúc chờ, phương thức ném `InterruptedException` và không cấp khóa cho lần gọi đó. Khi đã lấy được khóa, mọi đường thoát trong `try` đều đi qua `finally` để gọi `unlock()`.

Không gọi `unlock()` nếu chưa lấy được khóa. Không đặt `unlock()` sau `return` trong khối `try`, vì khi đó nó có thể không được thực hiện. Chỉ thread đang sở hữu `ReentrantLock` mới được mở khóa; gọi sai chủ sở hữu sẽ ném `IllegalMonitorStateException`.

## Chọn lock, lockInterruptibly hay tryLock

`ReentrantLock` cung cấp nhiều cách chờ khác nhau. Chọn API theo chính sách của tác vụ:

| API | Hành vi | Khi phù hợp |
| --- | --- | --- |
| `lock()` | Chờ đến khi lấy được khóa; không hủy việc chờ chỉ vì interrupt | Critical section bắt buộc phải thực hiện và interruption không phải điều kiện dừng lúc chờ |
| `lockInterruptibly()` | Chờ lấy khóa nhưng có thể ném `InterruptedException` | Task cần phản hồi cancellation trong lúc đang chờ khóa |
| `tryLock()` | Thử lấy khóa ngay, trả `false` nếu chưa lấy được | Có thể bỏ qua, thử lại hoặc chọn đường xử lý khác khi bận |
| `tryLock(timeout, unit)` | Chờ tối đa thời gian chỉ định; có thể bị interrupt | Cần giới hạn thời gian chờ khóa |

Ví dụ giới hạn thời gian chờ:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

final class TimedInventory {
    private final ReentrantLock lock = new ReentrantLock();
    private int available = 10;

    boolean reserve(int quantity) throws InterruptedException {
        if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false; // Không lấy được khóa trong thời hạn.
        }

        try {
            if (quantity <= 0 || available < quantity) {
                return false;
            }
            available -= quantity;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
```

`tryLock()` không chờ có thể hữu ích cho đường xử lý không bắt buộc. Nhưng nếu liên tục thử lại trong vòng lặp không có backoff, nó có thể gây busy-wait và tiêu thụ CPU. `tryLock(timeout, unit)` phù hợp hơn khi cần một deadline rõ ràng.

## Fairness và khả năng tái nhập

Mặc định, `new ReentrantLock()` tạo khóa không công bằng (non-fair). Khi khóa được mở, thread nào được scheduler chọn có thể lấy khóa tiếp theo; một thread chờ lâu có thể bị trì hoãn bởi thread khác. Có thể yêu cầu chế độ fair:

```java
ReentrantLock fairLock = new ReentrantLock(true);
```

Fair lock ưu tiên thread chờ lâu nhất theo hàng đợi của khóa khi xảy ra cạnh tranh. Điều này có thể giảm nguy cơ một thread bị đói, nhưng thường làm giảm throughput và không đảm bảo thứ tự lập lịch CPU của hệ điều hành. `tryLock()` không tham số vẫn có thể lấy khóa ngay cả khi có thread khác đang chờ trên fair lock; nếu cần tuân theo fairness, hãy xem xét overload có timeout.

`ReentrantLock` là khóa tái nhập (reentrant). Thread đang sở hữu khóa có thể gọi `lock()` thêm lần nữa mà không tự deadlock; số lần khóa phải được cân bằng bằng cùng số lần `unlock()`. Đây là tính chất tương tự khả năng tái nhập của intrinsic monitor.

## Dùng Condition để chờ một điều kiện nghiệp vụ

`ReentrantLock` có thể tạo nhiều `Condition`, cho phép các nhóm thread chờ những điều kiện khác nhau trên cùng một khóa. Đây là khả năng linh hoạt hơn một monitor chỉ có một wait set.

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

final class MessageQueue {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition notEmpty = lock.newCondition();
    private final Deque<String> messages = new ArrayDeque<>();

    void put(String message) {
        lock.lock();
        try {
            messages.addLast(message);
            notEmpty.signal();
        } finally {
            lock.unlock();
        }
    }

    String take() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (messages.isEmpty()) {
                notEmpty.await();
            }
            return messages.removeFirst();
        } finally {
            lock.unlock();
        }
    }
}
```

`await()` chỉ được gọi khi thread đang sở hữu lock. Nó tạm thời giải phóng lock khi chờ và lấy lại lock trước khi tiếp tục hoặc ném `InterruptedException`. Điều kiện phải được kiểm tra trong `while`, không phải `if`, vì thread có thể thức dậy khi điều kiện không còn đúng hoặc do một lần thức dậy không đáp ứng predicate. `signal()` đánh thức một waiter; `signalAll()` đánh thức tất cả waiter trên condition đó.

Với virtual thread, việc chờ trên `Condition` dựa trên cơ chế park có thể cho phép unmount khỏi carrier. Tuy vậy, critical section trước và sau `await()` vẫn phải ngắn và bảo vệ đúng trạng thái dùng chung.

## ReentrantLock không thay thế việc rút ngắn critical section

Một lỗi thiết kế phổ biến là giữ khóa trong khi gọi HTTP, truy vấn database hoặc chờ một tài nguyên bên ngoài. `ReentrantLock` có thể cho virtual thread unmount khi nó chờ một thao tác blocking được hỗ trợ, nhưng khóa vẫn thuộc về thread đó. Những tác vụ khác cần khóa sẽ tiếp tục chờ.

Ưu tiên chụp dữ liệu cần thiết trong vùng khóa ngắn, thực hiện I/O ngoài khóa, rồi quay lại cập nhật trạng thái nếu cần:

```java
CustomerSnapshot snapshot;

lock.lock();
try {
    snapshot = currentCustomer.snapshot();
} finally {
    lock.unlock();
}

RemoteResult result = customerService.fetchDetails(snapshot.id());

lock.lock();
try {
    currentCustomer.apply(result);
} finally {
    lock.unlock();
}
```

Ví dụ này chỉ phù hợp nếu dữ liệu có thể thay đổi trong lúc I/O và ứng dụng có cách kiểm tra phiên bản hoặc xử lý xung đột. Không thể tùy tiện tách một critical section nếu điều đó phá vỡ invariant nghiệp vụ. Cần thiết kế lại giao dịch hoặc dùng version check khi có cập nhật đồng thời.

## Chi phí và rủi ro khi chuyển từ synchronized

`ReentrantLock` đem lại tính năng bổ sung, nhưng cũng tạo thêm trách nhiệm cho người viết mã:

- Phải giải phóng lock đúng số lần và đúng thread; quên `unlock()` có thể làm các tác vụ khác chờ vô hạn.
- `tryLock()` hoặc `lockInterruptibly()` buộc ứng dụng quyết định rõ cách xử lý timeout và cancellation.
- Fairness có thể làm giảm throughput; không bật chỉ vì nghe có vẻ công bằng hơn.
- `Condition` cần quản lý predicate, `await()` và `signal()` đúng cách; sai thứ tự có thể tạo lỗi mất tín hiệu hoặc chờ vô hạn.
- Lock ordering không nhất quán giữa nhiều khóa có thể tạo deadlock.
- Đổi khóa không giải quyết contention do critical section quá dài hoặc thuật toán cần tuần tự hóa.

`synchronized` có ưu điểm tự động giải phóng monitor khi thoát block, kể cả khi có exception. Với vùng bảo vệ trạng thái ngắn, không có pinning được đo thấy và không cần tính năng nâng cao, giữ `synchronized` thường dễ đọc và ít lỗi hơn.

## Quy trình đánh giá bằng số liệu trên JDK 21

1. **Tạo baseline.** Chạy đúng workload đại diện và ghi lại throughput, p95/p99 latency, CPU, số tác vụ đồng thời và thời gian chờ khóa.
2. **Tìm bằng chứng pinning.** Dùng Java Flight Recorder, kiểm tra sự kiện `jdk.VirtualThreadPinned` và stack trace để xác định virtual thread bị pin ở đâu. Phân biệt pinning với lock contention thông thường.
3. **Xác định nguyên nhân gốc.** Kiểm tra thao tác blocking trong synchronized region, native call, thời gian giữ khóa và số thread cạnh tranh.
4. **Thử thay đổi nhỏ.** Nếu cần API chờ interruptible/timeout hoặc tránh monitor pinning, thay đúng vùng liên quan bằng `ReentrantLock`; giữ invariant và cleanup bằng `finally`.
5. **Benchmark cùng điều kiện.** So sánh hai cách với cùng critical section, số tác vụ, dữ liệu và mức tải. Có thể dùng JMH cho phép đo cô lập, đồng thời dùng load test/JFR để đánh giá hành vi end-to-end.
6. **Đánh giá trade-off.** So sánh latency, throughput, CPU, số lần pinning, thời gian chờ và mức phức tạp mã. Kiểm tra cả trường hợp contention thấp và cao.
7. **Giữ hoặc hoàn tác dựa trên kết quả.** Chỉ giữ `ReentrantLock` nếu cải thiện đo được có ý nghĩa và chi phí bảo trì chấp nhận được.

Không dùng một microbenchmark đơn lẻ để kết luận mọi workload sẽ nhanh hơn. Kết quả phụ thuộc vào số core, mức contention, thời gian critical section, fairness, loại I/O và cách ứng dụng triển khai.

## Khi nào nên chọn ReentrantLock?

| Dấu hiệu đã quan sát | Hướng xử lý nên cân nhắc |
| --- | --- |
| JFR cho thấy virtual thread bị pin khi blocking bên trong synchronized region | Xem có thể đưa blocking ra ngoài khóa; nếu không, benchmark `ReentrantLock` cho đúng vùng đó |
| Task cần hủy trong lúc chờ khóa | Cân nhắc `lockInterruptibly()` |
| Chờ khóa phải có thời hạn | Cân nhắc `tryLock(timeout, unit)` và định nghĩa rõ fallback |
| Cần nhiều nhóm điều kiện chờ trên cùng một lock | Cân nhắc `Condition` |
| Cần giữ code đơn giản cho vùng bảo vệ ngắn, không có vấn đề đo được | Giữ `synchronized` |
| Thời gian giữ khóa dài do I/O hoặc công việc ngoài | Rút ngắn critical section hoặc thay đổi thiết kế trước khi đổi loại khóa |

`ReentrantLock` là công cụ hữu ích trên JDK 21 khi có bằng chứng về pinning hoặc cần điều khiển việc chờ khóa. Nó cho phép virtual thread chờ bằng cơ chế park có thể unmount, đồng thời cung cấp timeout, interruption và condition linh hoạt. Quyết định sử dụng phải dựa trên profiling và benchmark, vì lock vẫn tuần tự hóa vùng dữ liệu được bảo vệ và yêu cầu quản lý mở khóa tường minh.
