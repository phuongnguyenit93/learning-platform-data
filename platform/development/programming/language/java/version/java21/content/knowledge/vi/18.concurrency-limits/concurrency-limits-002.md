# Semaphore để giới hạn số tác vụ đồng thời theo tài nguyên

## 1. Semaphore giải quyết vấn đề gì?

`Semaphore` trong `java.util.concurrent` quản lý một số lượng **permit** (giấy phép) hữu hạn. Một tác vụ phải lấy được permit trước khi đi vào vùng cần giới hạn; khi hoàn tất, tác vụ trả permit để tác vụ khác có thể tiếp tục.

Đây là cách giới hạn số thao tác đang sử dụng cùng một tài nguyên tại một thời điểm. Ví dụ:

- Chỉ cho phép tối đa 20 truy vấn đồng thời đến một database.
- Giới hạn số request đang gọi một dịch vụ bên ngoài.
- Hạn chế số tác vụ cùng đọc một thiết bị hoặc một tài nguyên có dung lượng hữu hạn.
- Giới hạn số công việc đồng thời sử dụng một API có quota theo số request đang chạy.

Ví dụ, nếu tạo `Semaphore` với 5 permit, tối đa 5 tác vụ có thể giữ permit cùng lúc. Tác vụ thứ sáu phải chờ, thử lại sau hoặc bị từ chối tùy cách chương trình chọn API.

```java
Semaphore permits = new Semaphore(5);

permits.acquire();
try {
    callLimitedService();
} finally {
    permits.release();
}
```

`Semaphore` không tự tạo thread, không tự gọi dịch vụ và cũng không sở hữu tài nguyên. Nó chỉ phối hợp quyền đi vào vùng được bảo vệ. Ứng dụng phải đặt thao tác lấy và trả permit đúng quanh phần công việc cần giới hạn.

## 2. Tạo Semaphore và ý nghĩa của permit

Constructor thông dụng nhận số permit ban đầu:

```java
Semaphore databaseSlots = new Semaphore(20);
```

Số `20` biểu thị số permit ban đầu có sẵn. Mỗi lần `acquire()` thành công làm số permit khả dụng giảm đi một; mỗi lần `release()` làm số permit khả dụng tăng lên một.

Nếu không còn permit, `acquire()` chờ cho đến khi có permit hoặc thread bị interrupt. Khi một tác vụ gọi `release()`, một hoặc nhiều thread đang chờ có thể được đánh thức để cạnh tranh lấy permit.

Có thể yêu cầu nhiều permit cùng lúc:

```java
Semaphore capacity = new Semaphore(10);

capacity.acquire(3); // Lấy đồng thời 3 permit
try {
    processBatch();
} finally {
    capacity.release(3);
}
```

Các overload nhận số permit hữu ích khi một công việc tiêu thụ nhiều đơn vị dung lượng. Cần trả đúng số permit đã lấy sau khi hoàn tất.

## 3. Luôn trả permit trong `finally`

Một lỗi phổ biến là chỉ gọi `release()` ở cuối phần thân xử lý. Nếu công việc ném exception hoặc trả về sớm, permit sẽ không được trả và dung lượng khả dụng giảm dần theo thời gian.

Hãy đặt phần công việc sau `acquire()` trong khối `try` và trả permit trong `finally`:

```java
static Customer loadCustomer(String id, Semaphore databaseSlots)
        throws InterruptedException {

    databaseSlots.acquire();
    try {
        return repository.findById(id);
    } finally {
        databaseSlots.release();
    }
}
```

Nếu `acquire()` bị interrupt trước khi lấy được permit, chương trình chưa đi vào khối `try` nên không gọi `release()`. Khi đã lấy được permit, `finally` bảo đảm permit được trả kể cả khi `repository.findById` ném exception.

Không gọi `release()` khi chưa lấy permit. `Semaphore` không gắn permit với thread đã lấy nó; một thread khác vẫn có thể gọi `release()`. Vì vậy, kỷ luật sở hữu permit phải được thực hiện trong code ứng dụng.

## 4. Chờ, thử ngay hoặc chờ có thời hạn

`Semaphore` cung cấp nhiều cách lấy permit để phù hợp với chính sách tải và thời gian chờ của ứng dụng.

| Method | Hành vi | Khi phù hợp |
|---|---|---|
| `acquire()` | Chờ đến khi lấy được một permit; có thể bị interrupt | Tác vụ có thể chờ và cần được thực hiện |
| `acquire(int permits)` | Chờ đến khi lấy đủ số permit yêu cầu | Tác vụ cần nhiều đơn vị dung lượng cùng lúc |
| `tryAcquire()` | Trả về ngay `true` nếu lấy được, ngược lại `false` | Muốn từ chối nhanh khi tài nguyên đang bận |
| `tryAcquire(timeout, unit)` | Chờ tối đa thời gian chỉ định; trả về `false` nếu hết thời gian | Muốn cho phép chờ trong một ngân sách thời gian |
| `tryAcquire(int permits, timeout, unit)` | Chờ tối đa thời gian để lấy đủ số permit | Công việc cần nhiều permit nhưng không thể chờ vô hạn |

Ví dụ từ chối nhanh:

```java
static Response callService(Semaphore slots) {
    if (!slots.tryAcquire()) {
        throw new ServiceBusyException("Service is at capacity");
    }

    try {
        return remoteService.call();
    } finally {
        slots.release();
    }
}
```

Nếu không lấy được permit, method trả lỗi hoặc trạng thái phù hợp ngay. Đây là chính sách *fail fast*; caller có thể thử lại sau, trả HTTP 429/503 hoặc đưa công việc vào hàng đợi theo hợp đồng của hệ thống.

Ví dụ chờ tối đa 300 mili giây:

```java
import java.util.concurrent.TimeUnit;

static Response callService(Semaphore slots) throws InterruptedException {
    boolean acquired = slots.tryAcquire(300, TimeUnit.MILLISECONDS);
    if (!acquired) {
        throw new ServiceBusyException("Timed out waiting for a slot");
    }

    try {
        return remoteService.call();
    } finally {
        slots.release();
    }
}
```

Timed `tryAcquire` ném `InterruptedException`. Caller nên giữ đúng chính sách interruption của ứng dụng; không nuốt exception rồi tiếp tục xử lý như thể permit đã được cấp.

## 5. Giới hạn số truy vấn database đồng thời

Giả sử ứng dụng có thể nhận nhiều request hơn số kết nối database cho phép sử dụng đồng thời. Có thể dùng một semaphore dùng chung để giới hạn số tác vụ đi vào phần truy vấn.

```java
import java.util.concurrent.Semaphore;

final class CustomerService {
    private final Semaphore databaseSlots = new Semaphore(12, true);
    private final CustomerRepository repository;

    CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    Customer findCustomer(String id) throws InterruptedException {
        databaseSlots.acquire();
        try {
            return repository.findById(id);
        } finally {
            databaseSlots.release();
        }
    }
}
```

Trong ví dụ này, mọi request dùng cùng instance `CustomerService`, nên cùng chia sẻ 12 permit. Tối đa 12 lời gọi `findById` được thực hiện đồng thời qua service này. Permit được trả ngay sau khi thao tác truy vấn hoàn tất.

Điểm quan trọng là semaphore phải có phạm vi chia sẻ tương ứng với tài nguyên cần bảo vệ. Nếu tạo một semaphore mới cho từng request, mỗi request sẽ có bộ permit riêng và tổng số truy vấn không bị giới hạn như dự định.

Semaphore ở tầng service cũng không thay thế connection pool. Connection pool quản lý vòng đời và cấp phát connection thực tế; semaphore là cơ chế admission control bổ sung nếu ứng dụng cần giới hạn số thao tác ở một phạm vi cụ thể. Cần cấu hình hai giới hạn có chủ đích để tránh giữ permit trong lúc chờ connection mà không mang lại lợi ích.

## 6. Tích hợp với virtual thread trong Java 21

Virtual thread làm cho việc chờ permit có chi phí thấp hơn so với việc giữ một platform thread trong lúc chờ. Vì vậy, có thể kết hợp `Semaphore` với executor tạo virtual thread để giới hạn số tác vụ đang sử dụng tài nguyên, trong khi nhiều tác vụ khác chờ permit.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;

Semaphore remoteSlots = new Semaphore(8);

try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 100; i++) {
        int requestId = i;
        executor.execute(() -> {
            boolean acquired = false;
            try {
                remoteSlots.acquire();
                acquired = true;
                callRemoteService(requestId);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RuntimeException("Interrupted while waiting for a remote slot", e);
            } finally {
                if (acquired) {
                    remoteSlots.release();
                }
            }
        });
    }
}
```

Executor tạo một virtual thread cho mỗi task được submit, còn semaphore giới hạn tối đa 8 task cùng giữ permit trong lúc gọi dịch vụ. Các virtual thread còn lại có thể chờ permit. Khi khối try-with-resources đóng executor, `close()` chờ các task đã submit hoàn tất.

Semaphore phải được chia sẻ giữa các task như trong ví dụ. Đừng tạo `new Semaphore(8)` bên trong lambda, vì khi đó mỗi task có 8 permit riêng và không còn giới hạn toàn cục.

Virtual thread không làm cho tài nguyên downstream có dung lượng vô hạn. Database, HTTP service, file descriptor và giới hạn kết nối vẫn cần được kiểm soát. Semaphore là một trong các công cụ để giữ số thao tác đang hoạt động trong giới hạn phù hợp.

## 7. Fairness: thứ tự cấp permit

Mặc định, semaphore không đảm bảo thứ tự FIFO giữa các thread đang chờ. Một thread mới đến có thể lấy permit trước một thread đã chờ lâu hơn, tùy thời điểm lập lịch và cạnh tranh.

Có thể tạo semaphore công bằng:

```java
Semaphore fairSlots = new Semaphore(10, true);
```

Tham số `true` yêu cầu fairness. Các thread chờ được cấp permit theo thứ tự FIFO tại các điểm xếp hàng nội bộ của semaphore. Điều này giảm nguy cơ một thread bị bỏ đói khi có nhiều thread cạnh tranh.

Fairness có thể làm giảm throughput trong một số tình huống vì phải giữ thứ tự chờ. Không nên bật fairness theo thói quen; hãy cân nhắc yêu cầu về độ công bằng, độ trễ và thông lượng của hệ thống.

Lưu ý: `tryAcquire()` không tham gia chính sách fairness. Ngay cả khi semaphore được tạo với fairness `true`, lời gọi `tryAcquire()` không chờ vẫn có thể lấy permit đang rảnh trước thread khác đang chờ. Nếu cần kiểm tra không chờ nhưng vẫn tôn trọng fairness, API timed `tryAcquire(0, TimeUnit.SECONDS)` có quy tắc fairness; method này có thể ném `InterruptedException`.

Fairness điều phối thứ tự lấy permit, không bảo đảm thứ tự hoàn tất công việc hoặc thứ tự xử lý ở dịch vụ bên ngoài.

## 8. Lấy và trả nhiều permit

Khi mỗi tác vụ tiêu thụ số đơn vị tài nguyên khác nhau, có thể lấy nhiều permit bằng `acquire(int)` và trả bằng `release(int)`.

```java
Semaphore workerUnits = new Semaphore(12);

static void processBatch(int size, Semaphore workerUnits)
        throws InterruptedException {
    if (size < 1 || size > 4) {
        throw new IllegalArgumentException("size must be between 1 and 4");
    }
    int permitsNeeded = size;
    workerUnits.acquire(permitsNeeded);
    try {
        processWithCapacity(size);
    } finally {
        workerUnits.release(permitsNeeded);
    }
}
```

Trong ví dụ, mỗi batch có từ 1 đến 4 đơn vị và lấy đúng số permit tương ứng. Cần xác định đơn vị permit rõ ràng trong thiết kế, chẳng hạn một permit tương ứng với một connection, một worker slot hoặc một đơn vị tải đã quy ước.

Tránh để một tác vụ giữ một phần permit rồi chờ thêm permit trong khi các tác vụ khác cũng làm tương tự; cách lấy permit theo từng phần có thể gây deadlock hoặc giảm khả năng tiến triển. Nếu công việc cần nhiều permit, thường nên lấy đủ trong một lần `acquire(n)`.

## 9. `release()` không kiểm tra quyền sở hữu

Khác với `Lock`, `Semaphore` không ghi nhận thread nào đã lấy permit. Một thread có thể gọi `release()` để tăng số permit, kể cả khi thread đó chưa từng gọi `acquire()`.

Điều này hữu ích trong một số mô hình producer/consumer, nhưng cũng dễ gây lỗi. Nếu gọi `release()` nhiều hơn số permit đã lấy, số permit khả dụng có thể vượt quá giới hạn ban đầu. `Semaphore` không có mức trần tự động tương ứng với số permit ban đầu.

Vì vậy:

- Chỉ release sau khi acquire thành công.
- Với `acquire(n)`, trả đúng `n` permit.
- Đặt `release()` trong `finally` để tránh rò rỉ permit khi có exception.
- Không để nhiều nhánh code cùng chịu trách nhiệm release cho một lần acquire.
- Nếu cần xác minh quyền sở hữu tài nguyên cụ thể, hãy dùng abstraction quản lý tài nguyên phù hợp thay vì dựa riêng vào semaphore.

## 10. Semaphore khác rate limiter, queue và connection pool

Các cơ chế này thường xuất hiện cùng nhau nhưng giải quyết vấn đề khác nhau.

| Cơ chế | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| `Semaphore` | Số thao tác đang giữ permit cùng lúc | Tối đa 8 request đang gọi dịch vụ |
| Rate limiter | Tần suất hoặc số request trong một khoảng thời gian | Tối đa 100 request mỗi giây |
| Bounded queue | Số công việc đang chờ xử lý | Tối đa 500 task chờ trong hàng đợi |
| Connection pool | Số connection thực tế và vòng đời connection | Tối đa 12 database connection đang được cấp |

Semaphore không giới hạn số request mỗi giây. Nếu mỗi request chỉ mất vài mili giây, cùng một số permit có thể phục vụ rất nhiều request trong một giây. Muốn giới hạn tần suất, cần rate limiter.

Semaphore cũng không giới hạn số virtual thread đã được tạo hoặc số task đã submit. Ví dụ executor virtual thread có thể tạo 100.000 virtual thread, trong đó chỉ 8 thread giữ permit và phần còn lại đang chờ. Nếu cần giới hạn cả số công việc chờ hoặc lượng request được nhận, cần thêm bounded queue, backpressure hoặc chính sách từ chối ở tầng tiếp nhận.

Connection pool là nơi quản lý connection thực tế. Nếu pool đã giới hạn số connection, một semaphore có cùng kích thước có thể không cần thiết; nếu semaphore nhỏ hơn pool, nó có thể chủ động giới hạn tải ở mức thấp hơn. Hãy hiểu rõ điểm mà permit được lấy và trả để tránh giữ permit trong khi chờ một tài nguyên khác không cần thiết.

## 11. Theo dõi trạng thái mà không tạo race condition

`availablePermits()` trả về số permit đang có tại thời điểm đọc. Giá trị này hữu ích cho metrics và quan sát, nhưng có thể thay đổi ngay sau khi method trả về do thread khác acquire hoặc release.

Không nên viết logic đồng bộ kiểu:

```java
if (semaphore.availablePermits() > 0) {
    semaphore.acquire();
}
```

Giữa hai lời gọi, thread khác có thể lấy permit cuối cùng. Hãy dùng `tryAcquire()` để thực hiện kiểm tra và lấy permit trong một thao tác nguyên tử:

```java
if (semaphore.tryAcquire()) {
    try {
        performWork();
    } finally {
        semaphore.release();
    }
} else {
    rejectOrRetry();
}
```

Tương tự, `hasQueuedThreads()` và số thread chờ chỉ nên dùng cho mục đích giám sát, không phải để quyết định chắc chắn rằng một permit sẽ có sẵn.

## 12. Memory consistency

`Semaphore` cũng định nghĩa hiệu ứng nhất quán bộ nhớ. Các hành động trong một thread trước khi gọi `release()` xảy ra trước các hành động sau một lần `acquire()` thành công ở thread khác theo quan hệ *happens-before* được quy định trong API.

Điều này cho phép dùng semaphore như một phần của cơ chế phối hợp và công bố trạng thái giữa các thread. Tuy nhiên, permit không tự bảo vệ mọi dữ liệu dùng chung khỏi truy cập đồng thời. Nếu nhiều thread cùng sửa một cấu trúc dữ liệu, vẫn cần thiết kế đồng bộ phù hợp, chẳng hạn lock, concurrent collection hoặc atomic variable.

## 13. Checklist sử dụng Semaphore an toàn

Trước khi dùng semaphore để giới hạn tài nguyên, hãy xác định:

1. Permit đại diện cho đơn vị tài nguyên nào?
2. Số permit được chọn dựa trên giới hạn thực tế nào của database, service hoặc thiết bị?
3. Semaphore có được chia sẻ ở đúng phạm vi cần giới hạn không?
4. Permit được acquire trước vùng tài nguyên và release trong `finally` chưa?
5. Khi hết permit, tác vụ nên chờ, thử lại, timeout hay bị từ chối?
6. Có cần fairness hay throughput là ưu tiên chính?
7. Có đang giới hạn số thao tác đồng thời hay thực sự cần rate limit/hàng đợi giới hạn?
8. Executor virtual thread có thể tạo nhiều tác vụ chờ hơn khả năng hệ thống tiếp nhận không?
9. Các giới hạn khác như connection pool, timeout và downstream quota đã được tính đến chưa?

## 14. Tài liệu tham khảo chính thức

- [Java SE 21 API — `Semaphore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): permit, fairness, acquire/release, timed tryAcquire và memory consistency.
- [Java SE 21 API — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý vòng đời executor.
- [Java SE 21 API — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): executor tạo virtual thread theo từng task.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread chính thức trong Java 21.

`Semaphore` phù hợp để giới hạn số tác vụ cùng sử dụng một tài nguyên tại một thời điểm. Hãy chia sẻ đúng một semaphore cho phạm vi tài nguyên cần bảo vệ, lấy permit trước vùng xử lý và trả permit trong `finally`. Kết hợp `tryAcquire` hoặc timed acquire với chính sách chờ/từ chối rõ ràng; dùng rate limiter, bounded queue hoặc connection pool khi yêu cầu thực tế là giới hạn tần suất, số việc đang chờ hoặc số connection.
