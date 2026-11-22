# Thiết kế API đọc trạng thái có chi phí chấp nhận được với @ManagedAttribute

## 1. Vấn đề: một getter quản trị cũng là đường thực thi thật

Trong Spring JMX, \`@ManagedAttribute\` cho phép công bố trạng thái của bean dưới dạng MBean attribute. Người vận hành có thể đọc attribute qua JConsole, VisualVM, automation hoặc hệ thống giám sát. Cú pháp rất đơn giản:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queue.size();
}
\`\`\`

Tuy nhiên, lời gọi \`getQueueDepth()\` không chỉ là một dòng hiển thị. Nó chạy trong JVM ứng dụng, có thể tranh chấp lock, truy cập database, gọi network, cấp phát bộ nhớ hoặc ảnh hưởng luồng xử lý nghiệp vụ. Một công cụ giám sát có thể gọi getter nhiều lần mỗi giây, từ nhiều client và đôi khi đồng thời.

Vì thế, API quản trị cần bảo đảm **chi phí đọc có thể dự đoán**, **khả năng chịu tải**, **tính nhất quán phù hợp** và **không gây tác dụng phụ**. Mục tiêu không nhất thiết là mọi số liệu tức thời tuyệt đối; mục tiêu là số liệu đủ hữu ích để vận hành, được công bố an toàn với chi phí chấp nhận được.

## 2. Phân biệt ba nhóm thuộc tính

| Nhóm | Ví dụ | Cách lấy nên ưu tiên | Tính chất |
| --- | --- | --- | --- |
| Trạng thái hiện tại rẻ | \`Paused\`, \`Running\`, \`Healthy\` | \`AtomicBoolean\`, immutable snapshot | Thường O(1) |
| Số liệu tổng hợp | \`ProcessedTotal\`, \`FailureTotal\` | Counter/metrics cập nhật khi có sự kiện | Đọc nhanh, có thể hơi trễ |
| Số liệu phải tính toán | \`PendingTasks\`, \`OldestMessageAge\`, \`ActiveSessions\` | Cache hoặc snapshot do background task tính | Tránh truy vấn/quét dữ liệu khi client đọc |

Một attribute có vẻ đơn giản về kiểu trả về (ví dụ \`int\`) vẫn có thể rất đắt nếu getter thực hiện \`SELECT COUNT(*)\`, quét hàng triệu phần tử, khóa tập dữ liệu lớn hoặc gọi hệ thống khác.

Thiết kế nên bắt đầu bằng câu hỏi: **giá trị này được cập nhật khi nào, đọc tốn bao nhiêu, chấp nhận độ trễ bao nhiêu và ai có thể gọi nó?**

## 3. Nguyên tắc getter quản trị

Một getter được xuất qua JMX nên:

1. **Đọc nhanh** trong đa số tình huống, lý tưởng là O(1) hoặc chi phí nhỏ đã biết.
2. **Không làm thay đổi dữ liệu hoặc trạng thái nghiệp vụ**.
3. **Không phụ thuộc network/database trong đường đọc đồng bộ**, nếu không có lý do đặc biệt.
4. **Không giữ lock lâu** hoặc chặn luồng xử lý nghiệp vụ.
5. **Không trả object mutable nội bộ**, collection lớn hoặc dữ liệu nhạy cảm.
6. **Có cách biểu diễn lỗi và độ cũ của dữ liệu** nếu nguồn snapshot bị lỗi.
7. **Có đơn vị và ý nghĩa rõ ràng**, ví dụ millis, bytes, số message chờ.
8. **Ổn định khi bị polling liên tục** từ nhiều client.

Một getter \`@ManagedAttribute\` có thể chạy trên thread nhận yêu cầu JMX. Nếu nó bị treo, client sẽ chậm và có thể chiếm tài nguyên quản trị của ứng dụng; nhiều getter chậm cùng lúc có thể gây tác động dây chuyền.

## 4. Ví dụ không nên làm: truy vấn DB ngay trong getter

\`\`\`java
@Component
@ManagedResource(objectName = "com.example:type=Orders,name=Primary")
public class OrderManagementBad {
    private final OrderRepository repository;

    public OrderManagementBad(OrderRepository repository) {
        this.repository = repository;
    }

    @ManagedAttribute(description = "Pending order count")
    public long getPendingOrders() {
        return repository.countPendingOrders();
    }
}
\`\`\`

Khi một dashboard đọc attribute mỗi 2 giây từ 10 client, phép truy vấn có thể chạy nhiều lần mà không có kiểm soát. Nếu DB chậm, kết nối cạn hoặc transaction bị khóa, thao tác xem trạng thái sẽ gây thêm tải cho hệ thống đang gặp sự cố.

Phương án tốt hơn là cập nhật số đếm ở luồng nghiệp vụ hoặc trong một background refresh có giới hạn, rồi để getter đọc snapshot.

## 5. Dùng counter cập nhật theo sự kiện

Với số liệu tích lũy, không cần quét dữ liệu mỗi lần đọc:

\`\`\`java
import java.util.concurrent.atomic.LongAdder;

public final class JobMetrics {
    private final LongAdder completed = new LongAdder();
    private final LongAdder failed = new LongAdder();

    public void completed() {
        completed.increment();
    }

    public void failed() {
        failed.increment();
    }

    public long completedTotal() {
        return completed.sum();
    }

    public long failedTotal() {
        return failed.sum();
    }
}
\`\`\`

Adapter JMX:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Metrics,name=Primary",
    description = "Job counters"
)
public class JobMetricsJmx {
    private final JobMetrics metrics;

    public JobMetricsJmx(JobMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Completed jobs since process start")
    public long getCompletedTotal() {
        return metrics.completedTotal();
    }

    @ManagedAttribute(description = "Failed jobs since process start")
    public long getFailedTotal() {
        return metrics.failedTotal();
    }
}
\`\`\`

\`LongAdder\` thường thích hợp khi có nhiều thread cập nhật counter; \`sum()\` không phải snapshot tuyến tính tuyệt đối khi cập nhật đồng thời. Nếu cần số đếm chính xác tại một thời điểm, cần cơ chế đồng bộ phù hợp. Đối với telemetry, chấp nhận một ảnh chụp gần đúng thường có lợi hơn tranh chấp khóa.

Counter tích lũy nên mô tả rõ phạm vi: tính từ khi JVM khởi động, từ khi module được tạo hay từ khi reset gần nhất. Tránh gọi \`Total\` cho một giá trị bị reset âm thầm.

## 6. Immutable snapshot để đọc nhanh nhiều trường

Khi cần nhiều trạng thái có liên hệ, nên công bố một snapshot bất biến:

\`\`\`java
import java.time.Instant;

public record WorkerSnapshot(
    boolean running,
    int queued,
    int active,
    long completed,
    Instant capturedAt
) {}
\`\`\`

Một component giữ snapshot mới nhất:

\`\`\`java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public final class WorkerStateView {
    private final AtomicReference<WorkerSnapshot> current =
        new AtomicReference<>(
            new WorkerSnapshot(false, 0, 0, 0, Instant.EPOCH)
        );

    public WorkerSnapshot snapshot() {
        return current.get();
    }

    public void publish(WorkerSnapshot next) {
        current.set(next);
    }
}
\`\`\`

Các getter JMX chỉ lấy snapshot và trích field:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public class WorkerStateJmx {
    private final WorkerStateView view;

    public WorkerStateJmx(WorkerStateView view) {
        this.view = view;
    }

    @ManagedAttribute(description = "Current active worker count")
    public int getActiveWorkers() {
        return view.snapshot().active();
    }

    @ManagedAttribute(description = "Queued tasks")
    public int getQueuedTasks() {
        return view.snapshot().queued();
    }

    @ManagedAttribute(description = "Snapshot update time")
    public String getSnapshotAt() {
        return view.snapshot().capturedAt().toString();
    }
}
\`\`\`

Mỗi getter đọc một \`AtomicReference\` nên chi phí rất nhỏ. Nhưng khi client đọc ba attribute qua ba lời gọi khác nhau, nó có thể nhận các giá trị từ những snapshot khác nhau nếu có cập nhật giữa các lần đọc. Nếu cần một tập giá trị nhất quán tuyệt đối, expose một snapshot tổng hợp bằng kiểu JMX phù hợp, chẳng hạn \`CompositeData\`, hoặc đặt các trường trong một operation trả về ảnh chụp chung được mapping rõ.

\`AtomicReference\` chỉ bảo đảm công bố nguyên tử **reference của snapshot**. Nó không tự làm nguồn dữ liệu đầu vào nhất quán nếu snapshot được xây từ nhiều bộ đếm thay đổi độc lập.

## 7. Background refresh cho số liệu đắt

Với thống kê phải truy vấn database hoặc hệ thống khác, chuyển việc tính toán sang một tác vụ nền có tần suất và timeout được kiểm soát.

\`\`\`java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PendingOrdersSnapshot {
    public record Value(long count, Instant capturedAt, boolean available) {}

    private final OrderRepository repository;
    private final AtomicReference<Value> latest =
        new AtomicReference<>(new Value(0, Instant.EPOCH, false));

    public PendingOrdersSnapshot(OrderRepository repository) {
        this.repository = repository;
    }

    @Scheduled(fixedDelayString = "\${management.pending.refresh-ms:10000}")
    public void refresh() {
        try {
            long count = repository.countPendingOrders();
            latest.set(new Value(count, Instant.now(), true));
        } catch (RuntimeException ex) {
            Value previous = latest.get();
            latest.set(new Value(
                previous.count(), previous.capturedAt(), false
            ));
            // Ghi log/rate-limit lỗi tại nơi phù hợp, không in dữ liệu nhạy cảm.
        }
    }

    public Value current() {
        return latest.get();
    }
}
\`\`\`

Cần kích hoạt scheduling qua cấu hình Spring phù hợp (\`@EnableScheduling\` khi cần). \`fixedDelay\` đợi lần chạy trước kết thúc rồi mới tính khoảng trễ, nhưng **không tự đặt timeout** cho truy vấn DB; cấu hình timeout ở data source/driver/repository để không bị kẹt vô hạn.

Một adapter đọc snapshot:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.orders:type=Pending,name=Primary"
)
public class PendingOrdersJmx {
    private final PendingOrdersSnapshot snapshots;

    public PendingOrdersJmx(PendingOrdersSnapshot snapshots) {
        this.snapshots = snapshots;
    }

    @ManagedAttribute(description = "Cached pending order count")
    public long getPendingCount() {
        return snapshots.current().count();
    }

    @ManagedAttribute(description = "Last successful refresh in ISO-8601")
    public String getCapturedAt() {
        return snapshots.current().capturedAt().toString();
    }

    @ManagedAttribute(description = "Whether last refresh succeeded")
    public boolean isAvailable() {
        return snapshots.current().available();
    }
}
\`\`\`

Không che giấu độ cũ của dữ liệu: nếu refresh thất bại, giữ số liệu cuối cùng nhưng cung cấp \`Available=false\` và \`CapturedAt\` cũ. Công cụ vận hành sẽ tránh diễn giải một giá trị cũ như trạng thái hiện tại.

## 8. Thiết kế ngưỡng chi phí và freshness

Không có ngưỡng thời gian duy nhất cho mọi hệ thống. Xác định budget theo nhu cầu và đo thực tế:

| Loại đọc | Mục tiêu tham khảo | Cơ chế |
| --- | --- | --- |
| Cờ trạng thái | Dưới vài ms | Atomic/volatile read |
| Counter | Dưới vài ms | Counter cập nhật khi sự kiện xảy ra |
| Queue size | Chi phí ổn định theo implementation | Metric native hoặc snapshot |
| Thống kê DB | Không chạy trên getter đồng bộ | Scheduled cache |
| Aggregate nhiều subsystem | Snapshot có timestamp | Background aggregation |
| Dữ liệu ít khi thay đổi | Cache với invalidation | Refresh theo sự kiện hoặc TTL |

Những con số trên là mục tiêu thiết kế tham khảo, không phải bảo đảm của Spring/JMX. Khi có nhiều client, còn phải tính tổng tần suất đọc:

\`\`\`text
effective reads/second
  = number of clients
    × poll frequency per client
    × attributes polled
\`\`\`

Ví dụ 5 client, mỗi client poll 4 lần/giây và đọc 8 attributes sẽ tạo khoảng 160 lần gọi attribute mỗi giây. Nếu mỗi getter truy vấn DB, hệ thống phát sinh 160 query/giây chỉ để phục vụ quan sát.

Cần đặt **freshness contract**: \`CapturedAt\`, \`LastSuccessfulRefreshAt\`, \`Stale\`, \`Available\` hoặc TTL. Tên thuộc tính phải phản ánh dữ liệu cached hay trực tiếp.

## 9. Không khóa nghiệp vụ để phục vụ getter

Một getter như sau nguy hiểm khi lock dùng chung với tác vụ nghiệp vụ lớn:

\`\`\`java
@ManagedAttribute
public int getActiveCount() {
    synchronized (businessLock) {
        return expensiveCollection.size();
    }
}
\`\`\`

Nếu \`businessLock\` bị giữ trong quá trình xử lý lâu, client JMX phải chờ, đồng thời có thể làm tăng contention. Không nên dùng getter quản trị để gọi thao tác quét hoặc giữ lock qua network.

Thay bằng:

- Atomic counter duy trì khi tác vụ bắt đầu/kết thúc.
- \`LongAdder\` nếu ưu tiên throughput của cập nhật.
- Snapshot được tính trên một đường riêng.
- Bounded \`tryLock\` nếu thật sự cần trạng thái bảo đảm hơn và có cách trả trạng thái unavailable.
- Số liệu mà queue/executor cung cấp sẵn, sau khi hiểu độ phức tạp của implementation.

Ví dụ đọc bounded lock:

\`\`\`java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public Integer tryReadSize(
        ReentrantLock lock, java.util.List<?> records)
        throws InterruptedException {
    if (!lock.tryLock(5, TimeUnit.MILLISECONDS)) {
        return null; // Adapter sẽ biểu diễn unavailable phù hợp.
    }
    try {
        return records.size();
    } finally {
        lock.unlock();
    }
}
\`\`\`

Dù \`tryLock\` có timeout, cách này vẫn có thể không cần thiết nếu snapshot đủ dùng. Hãy tránh giá trị magic như \`-1\` mà client không biết là lỗi hay số liệu thật.

## 10. Getter không được có side effect

Không dùng \`@ManagedAttribute\` getter làm nơi kích hoạt business action:

\`\`\`java
@ManagedAttribute
public String getStatus() {
    refreshFromRemoteSystem(); // Không nên làm
    return status;
}
\`\`\`

Công cụ JMX có thể đọc thuộc tính tự động để hiển thị giao diện. Nếu mỗi lần đọc lại làm refresh, nó vô tình thay đổi hệ thống chỉ vì ai đó mở monitoring tab.

Tách rõ:

\`\`\`java
@ManagedAttribute
public String getStatus() {
    return snapshot.status();
}

@ManagedOperation(description = "Request refresh")
public void requestRefresh() {
    commands.requestRefresh();
}
\`\`\`

Operation có tác dụng thay đổi trạng thái cần xác thực, authorization, audit, rate limiting và semantics khi gọi lặp. Getter giữ nhiệm vụ quan sát.

## 11. Chọn kiểu dữ liệu phù hợp với JMX

Một attribute nên trả kiểu mà JMX client dễ hiểu:

- \`boolean\`, \`int\`, \`long\`, \`double\` cho số liệu và cờ trạng thái.
- \`String\` cho trạng thái ngắn hoặc timestamp chuẩn ISO-8601.
- Các kiểu Open MBean như \`CompositeData\` khi cần một nhóm field nhất quán.
- Tránh trả danh sách hàng nghìn entity hoặc object graph nội bộ qua getter.

Nếu cần hiển thị top-N lỗi, giới hạn số phần tử và độ dài chuỗi. Không phơi dữ liệu cá nhân, token hoặc cấu hình bí mật qua JMX, đặc biệt khi remote connector được bật.

Không trả trực tiếp \`Map\` hoặc custom DTO phức tạp nếu assembler/MXBean mapping chưa rõ; metadata có thể không tương thích client hoặc gây chi phí serialize lớn.

## 12. Kiểm thử chi phí, an toàn và semantics

Một unit test có thể xác nhận getter đọc snapshot mà không gọi repository:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.time.Instant;

class WorkerStateJmxTest {
    @Test
    void getterReadsPublishedSnapshot() {
        WorkerStateView view = new WorkerStateView();
        view.publish(new WorkerSnapshot(
            true, 12, 3, 99, Instant.parse("2026-01-01T00:00:00Z")
        ));

        WorkerStateJmx adapter = new WorkerStateJmx(view);

        assertEquals(3, adapter.getActiveWorkers());
        assertEquals(12, adapter.getQueuedTasks());
        assertEquals("2026-01-01T00:00:00Z", adapter.getSnapshotAt());
    }
}
\`\`\`

Một integration test có thể đăng ký MBean trên \`MBeanServer\` và đọc qua \`getAttribute\`, kiểm tra tên attribute, kiểu dữ liệu và quyền truy cập. Với yêu cầu hiệu năng, đo latency theo percentile và throughput ở môi trường đại diện; test đơn lẻ \`assert elapsed < 5ms\` có thể nhiễu trên CI do JIT/GC/scheduling.

Các trường hợp đáng kiểm thử:

1. Nhiều client đọc đồng thời khi state thay đổi.
2. Background refresh chậm hoặc thất bại.
3. Snapshot đầu tiên chưa có dữ liệu.
4. Giá trị lớn, overflow và conversion sang kiểu JMX.
5. Getter được gọi với tần suất cao.
6. Application shutdown trong lúc client đang đọc.
7. Caller không có quyền nếu kênh JMX có kiểm soát quyền.

## 13. Quan sát chính hệ thống quan sát

Một management API có thể tự gây ảnh hưởng nếu chi phí đọc không được đo. Khi xây dựng dashboard cho production, đo:

- Số lần đọc attribute, nếu cần và có khả năng instrument.
- Latency của đường lấy snapshot/tạo số liệu.
- Thời gian kể từ refresh thành công gần nhất.
- Tỷ lệ refresh thất bại và số lần timeout.
- Kích thước dữ liệu trả về hoặc chi phí serialization.
- Lock contention hoặc lượng thread bị block khi JMX polling.

Tránh tạo vòng lặp quan sát: nếu \`getMetricsReadLatency()\` tự tính lại latency bằng một thao tác nặng, chính việc đo gây thêm tải. Chỉ trả giá trị đã ghi nhận từ instrumentation.

## 14. Những sai lầm hay gặp

| Sai lầm | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Getter gọi \`repository.count()\` | Tạo tải DB theo số client và tần suất poll | Cache/snapshot nền |
| Getter lock cả subsystem | Tăng contention, có thể block | Atomic metric/snapshot |
| Getter đọc toàn bộ collection rồi lọc | O(N), cấp phát bộ nhớ lớn | Duy trì aggregate và top-N riêng |
| Getter gọi remote API | Latency và lỗi phụ thuộc network | Background refresh có timeout |
| Getter tự kích hoạt đồng bộ | Thao tác quan sát có side effect | Dùng \`@ManagedOperation\` rõ ràng |
| Không công bố thời điểm snapshot | Client tưởng số liệu cũ là mới | \`CapturedAt\`, \`Available\`, \`Stale\` |
| Trả custom object lớn | Mapping/serialization chậm hoặc lỗi | Scalar hoặc Open MBean có giới hạn |
| Đo hiệu năng chỉ bằng một lần gọi | Dễ bỏ qua tải đồng thời và tail latency | Load test có workload đại diện |

## 15. Quy trình thiết kế một @ManagedAttribute mới

Trước khi thêm attribute:

1. **Đặt tên và đơn vị:** \`ActiveJobs\` (count), \`OldestJobAgeMillis\` (ms), \`LastSuccessAt\` (ISO-8601).
2. **Xác định dữ liệu nguồn:** atomic state, counter, queue, repository hay remote service.
3. **Định nghĩa cost budget:** độ phức tạp, latency tối đa mong đợi, tần suất polling.
4. **Định nghĩa freshness:** giá trị tức thời, eventual consistency hay cached snapshot.
5. **Chọn cơ chế cập nhật:** write-time metric, event-driven update, scheduled refresh.
6. **Thiết kế lỗi:** unavailable, stale, timestamp; tránh giả mạo 0 khi không có dữ liệu.
7. **Giới hạn dữ liệu trả về:** số field, số phần tử, độ dài và thông tin nhạy cảm.
8. **Kiểm thử:** correctness, concurrency, failure và chi phí dưới polling.
9. **Theo dõi production:** quan sát latency và chất lượng snapshot khi hệ thống tải cao.

Nếu thuộc tính quá đắt nhưng người vận hành vẫn cần dữ liệu theo yêu cầu, hãy tách thành một operation \`requestSnapshotRefresh()\` có kiểm soát, sau đó getter chỉ đọc kết quả gần nhất. Không bắt client chờ hàng chục giây trên một getter.

## 16. Ghi nhớ

\`@ManagedAttribute\` biến getter thành API quản trị có thể bị gọi thường xuyên và đồng thời. **Getter tốt là một phép đọc nhanh, dự đoán được, không có side effect và không làm xấu đi trạng thái hệ thống khi hệ thống đang có sự cố.** Dùng counter cập nhật theo sự kiện cho số liệu tích lũy, immutable snapshot cho trạng thái liên quan, và background refresh cho thống kê đắt. Công bố độ mới và lỗi của snapshot để người vận hành hiểu giới hạn của giá trị nhận được.
