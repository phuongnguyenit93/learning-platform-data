# Snapshot trạng thái thay cho đọc nhiều attribute rời rạc

## Mục tiêu

Trong Spring Framework JMX, một MBean có thể công bố nhiều attributes như `Queued`, `Processing`, `Completed`, `Failed` và `Paused`. Bài này giải thích vì sao đọc từng attribute riêng lẻ dễ tạo một bức tranh sai thời điểm, cách thiết kế một snapshot nhất quán, ưu nhược điểm về hiệu năng và phương pháp kiểm tra.

Sau bài học, bạn có thể:
- Phân biệt dữ liệu từng getter với một snapshot logic.
- Giải thích tại sao `getAttributes()` không mặc nhiên đảm bảo các giá trị được đọc atomically.
- Thiết kế snapshot bất biến, timestamp và generation.
- Phân biệt atomic publication với atomic capture.
- Công bố snapshot qua `CompositeData`, MXBean hoặc management adapter.
- Kiểm tra tính nhất quán, freshness và chi phí đọc qua JMX.

## 1. Vì sao đọc nhiều attributes có thể sai?

Giả sử lúc T0 một queue có `Queued=10` và `Processing=2`, tức tổng số job đang hoạt động là 12. Một JMX client đọc `Queued=10`. Sau đó một worker lấy một job: queue chuyển sang `Queued=9`, `Processing=3`. Client tiếp tục đọc `Processing=3`. Kết quả kết hợp `10+3=13` không phải trạng thái thực tồn tại đồng thời.

Mỗi giá trị được đọc riêng vẫn đúng tại thời điểm tương ứng; sai sót nằm ở việc ghép các thời điểm khác nhau thành một bức tranh duy nhất. Tình huống này xảy ra khi:
- Workloads ghi counters liên tục.
- Monitoring lấy nhiều getter theo thứ tự.
- Có AOP interceptors, locks hoặc I/O khiến các getter có độ trễ khác nhau.
- Client từ xa cần nhiều network round trips.
- Background refresh cập nhật từng field độc lập.

Dù client gọi `MBeanServerConnection.getAttributes(name, attributes)` để lấy nhiều giá trị trong một lệnh, JMX API không đưa ra bảo đảm tổng quát rằng toàn bộ getters cùng chạy trong một transaction hoặc dưới cùng một khóa. `getAttributes` giúp gom lời gọi, chứ không tự biến một implementation thiếu đồng bộ thành snapshot nguyên tử.

## 2. Các kiểu nhất quán cần phân biệt

| Khái niệm | Ý nghĩa | Giới hạn |
|---|---|---|
| Đọc rời rạc | Mỗi getter trả một giá trị tại lần gọi | Có thể lệch thời điểm |
| Batch attributes | Một API lấy nhiều tên attribute | Không mặc nhiên atomic |
| Immutable snapshot | Một object chứa nhiều trường cố định | Cách capture có thể vẫn sai |
| Atomic publication | Reader thấy trọn một snapshot đã publish | Không đảm bảo dữ liệu đầu vào được lấy cùng lúc |
| Atomic capture | Các trường tuân thủ invariant tại một điểm logic | Cần đồng bộ writers/capture |
| Fresh snapshot | Dữ liệu được lấy gần thời điểm đọc | Tính mới không đảm bảo consistency |
| Consistent snapshot | Trạng thái theo một generation/invariant rõ | Có thể cũ |

Điểm quan trọng: sử dụng `AtomicReference<Snapshot>` đảm bảo publication của reference, nhưng nếu snapshot được tạo bằng cách đọc năm counters rời rạc trong lúc writers cập nhật, nội dung snapshot vẫn có thể pha trộn nhiều thời điểm. Muốn giữ invariant phải kiểm soát cách cập nhật hoặc capture.

## 3. Thiết kế snapshot dữ liệu bất biến

Một Java record có thể biểu diễn snapshot:

```java
public record QueueSnapshot(
        long queued,
        long processing,
        long completed,
        long failed,
        boolean paused,
        long capturedAtEpochMillis,
        long generation) {}
```

Các fields primitive không thay đổi sau khi xây record. Trường `capturedAtEpochMillis` biểu diễn thời gian capture; `generation` là số tăng khi có phiên bản snapshot mới. Nếu một trong các trường chứa collection hoặc object mutable, record không tự khiến những object lồng bên trong bất biến; cần defensive copy.

Dùng `AtomicReference` để publish:

```java
import java.util.concurrent.atomic.AtomicReference;

public final class SnapshotStore {
    private final AtomicReference<QueueSnapshot> latest =
            new AtomicReference<>();

    public QueueSnapshot current() {
        return latest.get();
    }

    public void publish(QueueSnapshot next) {
        latest.set(next);
    }
}
```

Đây là cơ chế reader nhận một object, tránh phải khóa chỉ để lấy reference. Nhưng `current()` có thể trả null khi chưa có lần publish đầu tiên. Code quản trị cần biểu diễn trạng thái `NOT_INITIALIZED` rõ ràng thay vì dùng 0 như số liệu thật.

## 4. Capture nhất quán bằng một state chung

Nếu invariant quan trọng là `queued+processing=activeJobs`, hãy cập nhật các fields cùng nhau. Ví dụ CAS trên một state immutable:

```java
import java.util.concurrent.atomic.AtomicReference;

public final class QueueStateMachine {
    public record State(long queued, long processing, long generation) {}

    private final AtomicReference<State> state =
            new AtomicReference<>(new State(10, 2, 0));

    public void startOneJob() {
        state.updateAndGet(old -> {
            if (old.queued() == 0) return old;
            return new State(
                    old.queued() - 1,
                    old.processing() + 1,
                    old.generation() + 1);
        });
    }

    public State capture() {
        return state.get();
    }
}
```

Vì chuyển trạng thái `queued` và `processing` trong một CAS, reader nhìn thấy một `State` của cùng generation. Hàm truyền vào `updateAndGet` phải không có tác dụng phụ vì nó có thể được gọi lại khi CAS tranh chấp. Nếu tất cả writers không tuân theo state machine này, invariant có thể lại bị phá.

Một lựa chọn khác là `synchronized` với cùng lock cho cả writers và capture:

```java
public final class LockedQueueState {
    private long queued = 10;
    private long processing = 2;
    private long generation;

    public synchronized void startOneJob() {
        if (queued == 0) return;
        queued--;
        processing++;
        generation++;
    }

    public synchronized QueueSnapshot capture() {
        return new QueueSnapshot(
                queued, processing, 0, 0, false,
                System.currentTimeMillis(), generation);
    }
}
```

Giữ critical section ngắn. Không gọi SQL, HTTP hoặc chờ I/O khi đang giữ lock, vì monitoring có thể làm chậm workers. CAS và synchronized đều có tradeoff: CAS có contention và allocations; lock có wait time và chi phí đồng bộ. Đo theo workload.

## 5. Vì sao nhiều getters đọc cùng store vẫn có thể lệch generation?

Giả sử management bean:

```java
@ManagedAttribute
public long getQueued() {
    return snapshotStore.current().queued();
}

@ManagedAttribute
public long getProcessing() {
    return snapshotStore.current().processing();
}
```

Lần gọi đầu có thể đọc generation 20; background refresh publish generation 21; lần gọi thứ hai đọc generation 21. Hai getter đều đọc snapshot đã publish hợp lệ, nhưng client vẫn ghép hai generations.

Để khắc phục, công bố **một attribute `Snapshot` duy nhất** chứa toàn bộ fields và để client đọc nó một lần. Cách này giúp mọi field trong response thuộc cùng một object/generation. Nếu business yêu cầu consistency mạnh, vẫn phải đảm bảo snapshot được capture đúng như phần trước.

## 6. Công bố snapshot qua CompositeData

`CompositeData` và `CompositeType` thuộc JMX Open MBean API, cho phép công bố một cấu trúc có schema rõ. Một Standard MBean có thể định nghĩa:

```java
import javax.management.openmbean.CompositeData;

public interface QueueMonitorMBean {
    CompositeData getSnapshot();
}
```

Helper tạo `CompositeData`:

```java
import javax.management.openmbean.*;

public final class QueueSnapshotOpenData {
    private static final String[] NAMES = {
            "queued", "processing", "completed", "failed",
            "paused", "capturedAtEpochMillis", "generation"
    };
    private static final OpenType<?>[] TYPES = {
            SimpleType.LONG, SimpleType.LONG,
            SimpleType.LONG, SimpleType.LONG,
            SimpleType.BOOLEAN, SimpleType.LONG, SimpleType.LONG
    };
    private static final CompositeType TYPE;

    static {
        try {
            TYPE = new CompositeType(
                    "QueueSnapshot",
                    "Queue diagnostic state",
                    NAMES,
                    new String[]{
                        "Queued jobs", "Processing jobs",
                        "Completed jobs", "Failed jobs",
                        "Paused", "Capture timestamp", "Generation"
                    },
                    TYPES);
        } catch (OpenDataException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private QueueSnapshotOpenData() {}

    public static CompositeData convert(QueueSnapshot snapshot) {
        try {
            return new CompositeDataSupport(
                    TYPE, NAMES, new Object[]{
                        snapshot.queued(),
                        snapshot.processing(),
                        snapshot.completed(),
                        snapshot.failed(),
                        snapshot.paused(),
                        snapshot.capturedAtEpochMillis(),
                        snapshot.generation()
                    });
        } catch (OpenDataException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
```

MBean implementation:

```java
public final class QueueMonitor implements QueueMonitorMBean {
    private final SnapshotStore store;

    public QueueMonitor(SnapshotStore store) {
        this.store = store;
    }

    @Override
    public javax.management.openmbean.CompositeData getSnapshot() {
        QueueSnapshot value = store.current();
        if (value == null) {
            throw new IllegalStateException("No snapshot available");
        }
        return QueueSnapshotOpenData.convert(value);
    }
}
```

Điểm lợi: `value` được đọc đúng một lần và tất cả trường đều lấy từ object đó. JConsole hoặc JMX client có thể truy vấn `CompositeData` thay vì thực hiện nhiều lượt đọc scalar attributes. Schema field names/types cần ổn định vì đổi schema có thể làm client cũ lỗi.

## 7. Đọc snapshot từ MBeanServer

Khi MBean được đăng ký dưới ObjectName hợp lệ:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.shop.orders:type=QueueMonitor,name=outbox");

CompositeData snapshot =
        (CompositeData) server.getAttribute(name, "Snapshot");

long queued = (Long) snapshot.get("queued");
long processing = (Long) snapshot.get("processing");
long generation = (Long) snapshot.get("generation");

System.out.printf(
        "g=%d queued=%d processing=%d%n",
        generation, queued, processing);
```

Ví dụ giả định MBean đã được đăng ký vào chính platform MBeanServer. Nếu Spring exporter dùng MBeanServer khác, phải lấy server đó. `CompositeData.get` sử dụng đúng field names đã định nghĩa trong schema.

## 8. Spring @ManagedResource và management adapter

Trong Spring Framework, có thể tạo management adapter thay vì export trực tiếp service nghiệp vụ:

```java
import javax.management.openmbean.CompositeData;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Snapshot,name=outbox",
    description = "Coherent queue state")
public class QueueSnapshotManagement {
    private final SnapshotStore store;

    public QueueSnapshotManagement(SnapshotStore store) {
        this.store = store;
    }

    @ManagedAttribute
    public CompositeData getSnapshot() {
        QueueSnapshot value = store.current();
        if (value == null) {
            throw new IllegalStateException("Not initialized");
        }
        return QueueSnapshotOpenData.convert(value);
    }
}
```

Một `MBeanExporter` hoặc `AnnotationMBeanExporter` với assembler hiểu `@ManagedResource`/`@ManagedAttribute` phải thực sự export bean. Chỉ gắn annotation không tự tạo MBean. Tránh nhiều exporters cùng đăng ký ObjectName. Nếu adapter bị Spring AOP proxy, kiểm tra metadata/invocation qua MBeanInfo.

Adapter này chỉ đọc snapshot. Business threads hoặc snapshot job duy trì dữ liệu theo lifecycle riêng, tránh để lần đọc JMX trở thành phép truy vấn đắt đỏ.

## 9. MXBean và khả năng ánh xạ dữ liệu

MXBean có cơ chế chuyển đổi Java data types được hỗ trợ thành OpenTypes. Một interface có thể khai báo kiểu snapshot hợp lệ theo MXBean mapping. Tuy nhiên không thể mặc định mọi Java class, record, collection hoặc generic DTO đều tự map sang CompositeData trong mọi JDK.

Nếu cần khả năng tương tác giữa các JMX clients, trả `CompositeData` tường minh hoặc dùng MXBean type mapping đã xác minh. Nếu chỉ cần scalar metrics, tránh phức tạp hóa contract bằng object lớn.

## 10. Snapshot refresh theo lịch

Một snapshot có thể được cập nhật bởi background task:

```java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class QueueSnapshotRefresh {
    private final QueueStateProvider provider;
    private final AtomicReference<QueueSnapshot> current =
            new AtomicReference<>();

    public QueueSnapshotRefresh(QueueStateProvider provider) {
        this.provider = provider;
    }

    @Scheduled(fixedDelayString =
            "\${monitoring.snapshot-refresh-ms:15000}")
    public void refresh() {
        QueueSnapshot fresh = provider.captureSnapshot();
        current.set(fresh);
    }

    public QueueSnapshot current() {
        return current.get();
    }
}
```

`QueueStateProvider` ở đây là abstraction ứng dụng tự định nghĩa. Trong Spring, scheduling cần bật theo cấu hình phù hợp, ví dụ `@EnableScheduling`. Nếu `captureSnapshot()` cần đọc nhiều counters có invariant, provider phải triển khai cơ chế atomic capture thích hợp, không chỉ đọc rời rạc rồi ghép lại.

Với `fixedDelay`, lần chạy sau được lên lịch sau khi lần chạy trước kết thúc, theo scheduler configuration. Đừng để getter JMX tự gọi `refresh()` vì việc polling thường xuyên có thể gây nhiều truy vấn/lock.

## 11. Freshness và failure handling

Snapshot nhất quán vẫn có thể đã cũ. Nên ghi nhận:
- `capturedAtEpochMillis`: thời điểm capture.
- `generation`: thế hệ được publish.
- `lastRefreshDurationMillis`: thời gian refresh.
- `refreshFailures`: số lần refresh thất bại.
- `healthy` hoặc `stale`: trạng thái chất lượng dữ liệu.
- `initialized`: đã có snapshot hợp lệ hay chưa.

Ví dụ chính sách vận hành:
- Refresh interval 15 giây.
- Dữ liệu cũ hơn 45 giây được đánh dấu stale.
- Dữ liệu cũ hơn 120 giây không được dùng để ra quyết định tự động.

Các ngưỡng là ví dụ, không phải Spring defaults. Khi refresh lỗi, có thể giữ bản snapshot hợp lệ cuối cùng và công bố lỗi/freshness rõ ràng. Không lặng lẽ hiển thị số cũ như dữ liệu mới. Khi chưa có snapshot, không dùng `0` nếu nó dễ bị hiểu là giá trị thật.

## 12. Snapshot nhiều nguồn không luôn atomic

Một dashboard tổng hợp:
- Queue depth trong RAM.
- Database pool usage.
- JVM heap used.
- External HTTP service health.
- Error counter.

Các nguồn có clocks và update semantics riêng. Dù đặt tất cả vào một `record` rồi publish bằng `AtomicReference`, bạn chỉ đảm bảo **atomic publication**, không tự tạo **distributed consistent snapshot**. Nếu bắt buộc có consistency giữa nhiều hệ thống, cần transaction hoặc protocol domain-specific. Nếu chỉ cần view chẩn đoán, hãy đặt tên `best-effort snapshot` và thêm per-source timestamps.

## 13. Generation và client correlation

`generation` giúp client phân biệt hai lần capture:
- Nếu hai reads có cùng generation, có thể biết store chưa publish lần mới.
- Nếu generation đứng yên lâu hơn freshness target, cảnh báo stale.
- Nếu ứng dụng restart, generation có thể reset; không tự đồng bộ giữa nhiều replicas.
- Nếu so sánh nhiều JVMs, cần instance identity/boot ID riêng.

Không đặt generation liên tục tăng thành Prometheus label; việc này có thể tạo nhiều time series không cần thiết. Một generation có thể được công bố như value hoặc metadata trong JMX compound attribute.

## 14. Khi nào một snapshot tốt hơn scalar attributes?

Snapshot phù hợp khi:
1. Nhiều fields có invariant liên quan.
2. Một operator cần bức tranh cùng generation.
3. Client cần đọc trạng thái trong một JMX round trip.
4. Dữ liệu nhỏ và schema ổn định.
5. Cần timestamp/version để diễn giải trạng thái.
6. Getter riêng lẻ tốn công tính aggregate giống nhau.

Scalar attributes hoặc metrics phù hợp hơn khi:
1. Mỗi phép đo độc lập.
2. Cần time series/rates/alerts.
3. Monitoring stack thu thập dữ liệu theo labels.
4. Không cần atomic consistency liên trường.
5. Một compound snapshot quá lớn hoặc tốn serialization.

Có thể duy trì cả hai: snapshot JMX cho diagnostics và metrics từ cùng data source cho dashboard. Hãy mô tả semantics để không gây hiểu nhầm khi client đọc ở các thời điểm khác nhau.

## 15. Chi phí hiệu năng

Snapshot có thể giảm số round trips và số lần tính toán lặp lại, nhưng không tự đảm bảo nhanh hơn. Chi phí có thể gồm:
- Allocation tạo DTO hoặc CompositeData.
- CAS contention khi writers cập nhật liên tục.
- Lock contention trong capture.
- Serialization/transport của payload compound.
- Thời gian quét dữ liệu khi snapshot chứa collection lớn.
- Background refresh cần SQL/HTTP.

Tránh xuất full JPA entities, danh sách đơn hàng hoặc object graph không giới hạn qua JMX. Ngoài độ trễ còn có nguy cơ lộ dữ liệu khách hàng, lazy loading và classloader issues.

Đo latency p95/p99, allocations, lock wait, payload size và tác động lên throughput trước khi tối ưu.

## 16. Notifications kết hợp snapshot

Một MBean có thể phát JMX notification khi queue vượt ngưỡng, sau đó listener đọc snapshot để xem trạng thái. Notification không mặc định là durable queue có replay. Vì vậy vẫn cần polling/freshness checks khi client reconnect hoặc bỏ lỡ event.

Ví dụ luồng:
```text
queue.threshold.exceeded notification
    -> listener receives event
    -> connection.getAttribute(name, "Snapshot")
    -> process coherent state, generation and timestamp
```

Đừng cho rằng notification và snapshot capture xảy ra atomically; có thể đã có generation mới giữa lúc phát event và lúc client đọc. Nếu cần correlation chính xác, gắn generation vào notification userData hoặc message metadata phù hợp.

## 17. Kiểm tra tính đúng đắn qua concurrency test

Thiết lập test với state machine có invariant `queued + processing = 12`. Một thread cập nhật state bằng CAS, thread khác liên tục đọc snapshot.

Pseudocode:
```java
for (int i = 0; i < 100_000; i++) {
    QueueStateMachine.State snapshot = stateMachine.capture();
    if (snapshot.queued() + snapshot.processing() != 12) {
        throw new AssertionError("Torn snapshot");
    }
}
```

Cần kiểm tra cả đường JMX thật: register MBean vào một `MBeanServer` cô lập bằng `MBeanServerFactory.createMBeanServer()`, đọc `Snapshot` qua `getAttribute`, xác minh schema/type/invariant, rồi unregister trong `finally`. Test concurrency chạy thành công một lần không chứng minh tuyệt đối không còn race; kết hợp unit tests cho state transitions và lý giải Java Memory Model.

## 18. Checklist thiết kế

- [ ] Các fields nào phải thuộc cùng generation?
- [ ] Invariant nào bắt buộc được giữ?
- [ ] Writers có cập nhật state qua một cơ chế thống nhất không?
- [ ] Capture có atomic hoặc coherent theo contract?
- [ ] Snapshot có immutable và defensive copy cho mutable fields?
- [ ] Publication có memory visibility rõ?
- [ ] JMX getter trả cả object thay vì nhiều readings rời?
- [ ] Timestamp, generation, initialized và stale semantics rõ?
- [ ] Refresh failure có được báo không?
- [ ] Getter có tránh SQL/HTTP và lock dài?
- [ ] Payload có giới hạn?
- [ ] ObjectName và CompositeData schema ổn định?
- [ ] Có integration test MBeanInfo và concurrent updates?
- [ ] Có tránh secrets và dữ liệu cá nhân?
- [ ] Nhiều JVMs có identity riêng và không tự nhận là cluster snapshot?

## 19. Lỗi phổ biến

| Triệu chứng | Nguyên nhân | Giải pháp |
|---|---|---|
| Tổng queued + processing bị lệch | Đọc hai attributes ở hai thời điểm | Một compound snapshot |
| `getAttributes()` vẫn không nhất quán | JMX batch không atomic | Coherent capture ở implementation |
| Immutable snapshot vẫn sai invariant | Fields được đọc từ counters độc lập | CAS/lock/transaction phù hợp |
| Getter JMX chậm | Tạo snapshot trong getter với I/O | Background refresh |
| Snapshot quá cũ | Refresh lỗi hoặc cadence thấp | Timestamp, health và stale indicator |
| `CompositeData` cast lỗi | Contract không khớp | Kiểm tra MBeanInfo và return type |
| Client lỗi sau đổi field name | Schema breaking change | Version và migration |
| Dashboard mất chi tiết history | Snapshot không phải time-series store | Thu thập metrics riêng |
| Nhiều replicas có generation trùng | Generation chỉ local mỗi JVM | Instance identity/boot metadata |
| Snapshot lớn gây GC | Trả entity graph/collection | Aggregate, giới hạn fields |

## 20. Bài tập

**Bài 1.** Với sự kiện chuyển một job từ Queued sang Processing, mô tả một lịch xen kẽ khiến client đọc ra tổng 13 thay vì 12.

**Bài 2.** Viết state immutable và `AtomicReference.updateAndGet` để chuyển đồng thời hai counters. Đảm bảo update function không side effects.

**Bài 3.** Tạo `CompositeData` chứa `queued`, `processing`, `generation`, `capturedAtEpochMillis`; đọc bằng JMX client và xác minh các field.

**Bài 4.** Giả lập refresh lỗi 3 lần. Nêu cách giữ last-known-good snapshot và công bố age/failure metadata để không đánh lừa operator.

**Bài 5.** So sánh yêu cầu dashboard vẽ queue depth 24 giờ với yêu cầu operator xem tất cả counters cùng generation; chọn scalar metric hay compound snapshot cho từng trường hợp.

**Bài 6.** Tạo integration test sử dụng `MBeanServerFactory.createMBeanServer()`, đăng ký MBean, đọc snapshot, assert invariant, cleanup registration.

## 21. Tự kiểm tra

**MBeanServer.getAttributes() có đảm bảo mọi getter cùng thời điểm không?** Không. Nó là batch access API, không có bảo đảm atomic snapshot tổng quát.

**AtomicReference đảm bảo gì?** Một reference được publish/read với visibility phù hợp; không tự đảm bảo atomic capture của nhiều nguồn.

**Snapshot có thể cũ nhưng nhất quán không?** Có. Consistency và freshness là hai đặc tính riêng.

**Vì sao nhiều getters đọc cùng SnapshotStore vẫn lệch?** Vì store có thể publish generation mới giữa hai lần đọc.

**Tại sao dùng CompositeData?** Để công bố một compound attribute với schema JMX rõ ràng mà client có thể lấy trong một lần đọc.

**Snapshot có thay thế metrics time series không?** Không. Snapshot là một view trạng thái; time series dùng để xem trends, rates và alerts.

**Muốn snapshot nhất quán giữa nhiều services chỉ cần AtomicReference không?** Không. Cần protocol hoặc semantics domain-specific nếu yêu cầu distributed consistency.

## 22. Ghi nhớ

- Nhiều JMX attributes rời rạc có thể đúng riêng lẻ nhưng sai khi ghép khác thời điểm.
- `getAttributes()` không mặc định cung cấp atomic snapshot.
- Thiết kế **compound snapshot** khi cần invariant liên trường.
- Phân biệt **atomic capture** với **atomic publication**.
- Dùng immutable state, CAS/lock phù hợp, timestamp và generation.
- Tách background refresh khỏi JMX getter để tránh chi phí lặp lại.
- Xử lý stale, not initialized và failure rõ ràng.
- Không đưa object graph lớn hoặc dữ liệu nhạy cảm qua JMX.
- Kiểm tra bằng MBeanInfo, getAttribute, unit/integration/concurrency tests.
- Scalar metrics và snapshot phục vụ mục đích bổ sung nhau.

## 23. Tài liệu tham khảo

- Java SE 21 — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — CompositeData: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — CompositeDataSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeDataSupport.html
- Java SE 21 — AtomicReference: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
