# Attribute có tính toán nặng hoặc truy cập I/O trong Spring Framework JMX

## Mục tiêu

Trong Spring Framework JMX, các getter được đánh dấu \`@ManagedAttribute\`, hoặc được đưa vào Standard MBean/MXBean interface, có thể trở thành **JMX attributes**. Một JMX client đọc attribute qua \`MBeanServerConnection.getAttribute()\` hoặc \`getAttributes()\`. Từ góc nhìn người vận hành, đó là việc “đọc trạng thái”; nhưng từ góc nhìn JVM, lời đọc có thể chạy code Java thực sự: truy vấn database, gọi HTTP, đọc file, lấy lock, quét hàng triệu phần tử hoặc tính thống kê phức tạp.

Nếu một getter tốn vài giây, bị gọi nhiều lần bởi JConsole, monitoring agent và dashboard, nó có thể tạo ra tải ngoài dự kiến và làm hệ thống đang gặp sự cố trở nên kém ổn định hơn. Ngay cả một attribute không có side effect nghiệp vụ vẫn có **side effect tài nguyên** như CPU, I/O, lock contention, heap allocation hoặc thread starvation.

Bài học tập trung vào nguyên tắc: **JMX attribute nên là phép đọc nhanh, có giới hạn, dự đoán được và ít tác động**. Với phép tính hoặc I/O nặng, nên chuyển sang cơ chế cập nhật nền, snapshot đã được chuẩn bị, hoặc operation chẩn đoán chủ động có điều kiện.

Sau bài học, bạn có thể:

- Phân biệt getter nhẹ với getter tốn CPU, I/O, lock và allocation.
- Hiểu polling JMX có thể khuếch đại tải từ một getter.
- Thiết kế cached snapshot, scheduled refresh và giới hạn dữ liệu trả về.
- Tách lệnh tính toán/chẩn đoán nặng khỏi attribute đọc thường xuyên.
- Thiết lập timeout, backpressure, concurrency limit và circuit breaker ở đúng tầng.
- Đánh giá consistency, staleness và failure mode của cached attributes.
- Đo chi phí đọc JMX bằng latency, throughput, allocations và dependency load.
- Viết kiểm thử bảo đảm attribute ổn định khi dependency chậm hoặc không sẵn sàng.

## 1. JMX attribute là phương thức được thực thi

Ví dụ Spring annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Queue,name=Orders")
public class QueueMonitor {

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return queueRepository.countPending();
    }
}
\`\`\`

Getter nhìn đơn giản, nhưng nếu \`countPending()\` thực hiện câu SQL tốn nhiều thời gian, mỗi lần client hỏi \`QueueDepth\` có thể chạy truy vấn mới. Điều đó cũng xảy ra với Standard MBean:

\`\`\`java
public interface QueueMonitorMBean {
    long getQueueDepth();
}
\`\`\`

Việc đổi annotation thành interface **không** khiến getter tự được cache hoặc hạn chế chi phí. Metadata JMX chỉ xác định attribute được công bố; hành vi thực thi nằm ở code getter.

Luồng gọi:

\`\`\`text
JConsole / monitoring agent / custom client
                |
                | getAttribute(ObjectName, "QueueDepth")
                v
        MBeanServer / Spring exporter
                |
                v
          getQueueDepth()
                |
                +--> database query
                +--> network request
                +--> lock contention
                +--> object allocation
                +--> computation
                |
                v
          response / error
\`\`\`

Điều cần nhớ: từ góc nhìn client, việc “read-only” không đồng nghĩa rẻ, không chặn luồng hoặc không gây ảnh hưởng. 

## 2. Bốn kiểu chi phí hay bị bỏ qua

### 2.1 CPU-bound

Một getter có thể duyệt hàng trăm nghìn object để tính percentile, checksum hoặc thống kê:

\`\`\`java
@ManagedAttribute
public double getAverageLatencyMs() {
    return allRequests.stream()
        .mapToLong(Request::latencyMillis)
        .average()
        .orElse(0.0);
}
\`\`\`

Nếu \`allRequests\` rất lớn và thay đổi liên tục, mỗi lần đọc lại thực hiện vòng lặp trên toàn bộ tập. Mỗi dashboard với chu kỳ vài giây có thể trở thành nguồn CPU đáng kể. Nếu tập không thread-safe, getter còn có thể bị lỗi concurrent modification.

### 2.2 I/O-bound

Getter thực hiện query SQL, HTTP, file system, JNDI, Redis hoặc RPC. Ví dụ:

\`\`\`java
@ManagedAttribute
public String getRemoteDependencyHealth() {
    return httpClient.callHealthEndpoint();
}
\`\`\`

Khi downstream chậm, JMX call chậm theo. Việc nhiều monitoring agent đồng thời probe có thể khuếch đại sự cố của downstream.

### 2.3 Lock-bound

Getter lấy lock đang được dùng bởi luồng nghiệp vụ:

\`\`\`java
@ManagedAttribute
public int getPendingTasks() {
    synchronized (schedulerLock) {
        return tasks.size();
    }
}
\`\`\`

Nếu cùng lock được giữ khi schedule hoặc xử lý job lớn, monitoring bị treo. Ngược lại, tần suất monitoring cao có thể khiến luồng nghiệp vụ phải tranh lock.

### 2.4 Allocation-bound

Getter tạo danh sách hoặc serialize object graph lớn:

\`\`\`java
@ManagedAttribute
public String getAllSessionsAsJson() {
    return serializeAllSessions();
}
\`\`\`

Có thể dẫn đến heap pressure, GC pauses, lộ thông tin nhạy cảm và overhead truyền remote JMX. Dù computation nhanh, payload lớn vẫn làm connector bận và client chậm.

## 3. Tần suất polling khuếch đại chi phí

Một dashboard có thể có nhiều agent cùng lấy metric. Số lần gọi gần đúng:

\[
N_{\text{calls per second}} =
\sum_{i=1}^{m} \frac{1}{T_i}
\]

Trong đó \`T_i\` là chu kỳ polling (giây) của mỗi client. Nếu có 10 client cùng đọc một attribute mỗi 5 giây, tổng là khoảng 2 lần đọc mỗi giây. Nếu một getter tạo query tốn 500 ms CPU hoặc I/O, chi phí tổng có thể vượt xa kỳ vọng.

Ví dụ:

| Client | Số instance | Chu kỳ | Số lượt đọc gần đúng |
|---|---:|---:|---:|
| Monitoring agent A | 4 | 10 giây | 0,4 lần/giây |
| Dashboard B | 3 | 5 giây | 0,6 lần/giây |
| JConsole thủ công | 2 | 2 giây | 1 lần/giây |
| Tổng | 9 | — | 2 lần/giây |

Đây mới là số lượt gọi logic. Các client có thể gọi nhiều attribute và retry sau timeout. Nếu mỗi lượt đọc kích hoạt truy vấn riêng, downstream có thể nhận tải đáng kể. Một số JMX client còn dùng \`getAttributes\` để lấy nhiều attribute trong một request, nhưng implementation vẫn có thể gọi từng getter.

Đừng đo hiệu năng getter trong isolation rồi kết luận an toàn. Phải đánh giá **số người đọc, tần suất, concurrency và failure mode**.

## 4. Nguyên tắc thiết kế attribute nhẹ

Một attribute tốt thường có các đặc tính:

1. **Bounded work:** thời gian, số lượng và bộ nhớ sử dụng có giới hạn.
2. **Non-blocking hoặc short blocking:** không chờ I/O/network kéo dài.
3. **No surprising side effects:** không tạo job, không sửa dữ liệu và không kích hoạt tác vụ nặng.
4. **Predictable latency:** độ trễ ít biến động ngay cả khi hệ thống quá tải.
5. **Small payload:** trả scalar hoặc summary nhỏ.
6. **Stable schema:** kiểu dữ liệu và ý nghĩa không thay đổi tùy tình huống.
7. **Clear freshness:** nếu cached, công bố tuổi dữ liệu.
8. **Safe on failure:** dependency hỏng không khiến getter treo vô thời hạn.

Ví dụ phù hợp:

\`\`\`java
@ManagedAttribute
public long getCompletedCount() {
    return completedCount.sum();
}
\`\`\`

\`LongAdder.sum()\` có chi phí nhỏ trong phần lớn trường hợp, dù không phải snapshot tuyến tính tuyệt đối khi các thread đang cập nhật. Đối với telemetry, độ chính xác eventual có thể chấp nhận được; với thao tác điều khiển cần precondition chính xác, phải dùng cơ chế đồng bộ khác.

## 5. Anti-pattern: gọi database trực tiếp trong getter

Ví dụ cần tránh:

\`\`\`java
@ManagedAttribute(description = "Number of pending orders")
public long getPendingOrders() {
    return jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE state = 'PENDING'",
        Long.class
    );
}
\`\`\`

Nếu bảng lớn và query không được tối ưu, polling JMX có thể liên tục quét database. Khi database đang quá tải, dashboard lại làm tình hình nặng hơn.

Hướng cải thiện:

- Cập nhật counter trong luồng xử lý nghiệp vụ khi sự kiện xảy ra, nếu tính chính xác và lifecycle phù hợp.
- Chạy query thống kê định kỳ với timeout và tài nguyên riêng.
- Lưu snapshot của kết quả cùng thời điểm cập nhật.
- Đưa operation refresh vào luồng chủ động nếu cần số liệu mới tức thì.
- Dùng metrics backend chuyên dụng nếu yêu cầu thống kê là time-series, không cố biến JMX getter thành BI query.

Không có giải pháp cache nào đúng cho mọi chỉ số. Counter in-memory có thể lệch khi startup/restart hoặc xử lý thất bại. Cần mô tả đơn vị, phạm vi và freshness rõ ràng.

## 6. Cached snapshot: đọc nhanh, cập nhật riêng

Mẫu quan trọng là tách \`refresh\` khỏi \`read\`.

\`\`\`text
Scheduled/background worker
       |
       | query dependency / compute aggregate
       v
  Immutable Snapshot
       |
       | atomic/volatile publication
       v
  JMX getter
       |
       +--> returns simple value quickly
\`\`\`

Ví dụ:

\`\`\`java
import java.time.Instant;

public record QueueSnapshot(
    long depth,
    Instant refreshedAt,
    String status
) { }
\`\`\`

\`\`\`java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "com.example.ops:type=Queue,name=Orders")
public class QueueSnapshotMonitor {

    private final QueueRepository repository;

    private final AtomicReference<QueueSnapshot> latest =
        new AtomicReference<>(
            new QueueSnapshot(-1, Instant.EPOCH, "NOT_READY")
        );

    public QueueSnapshotMonitor(QueueRepository repository) {
        this.repository = repository;
    }

    @Scheduled(fixedDelayString = "\${monitor.queue.refresh-delay-ms:10000}")
    public void refreshSnapshot() {
        try {
            long depth = repository.countPendingWithTimeout();
            latest.set(new QueueSnapshot(
                depth, Instant.now(), "OK"));
        } catch (Exception ex) {
            QueueSnapshot previous = latest.get();
            latest.set(new QueueSnapshot(
                previous.depth(),
                previous.refreshedAt(),
                "STALE"
            ));
        }
    }

    @ManagedAttribute
    public long getQueueDepth() {
        return latest.get().depth();
    }

    @ManagedAttribute
    public String getQueueSnapshotStatus() {
        return latest.get().status();
    }

    @ManagedAttribute
    public long getQueueSnapshotEpochMillis() {
        return latest.get().refreshedAt().toEpochMilli();
    }
}
\`\`\`

Ở đây \`QueueRepository\` và \`countPendingWithTimeout()\` là các thành phần ứng dụng minh họa, cần triển khai bằng repository thực tế với timeout phù hợp. Cần bật scheduling (ví dụ \`@EnableScheduling\`) nếu muốn \`@Scheduled\` hoạt động trong Spring. Cấu hình mặc định ở ví dụ chỉ là minh họa; thời gian thích hợp phụ thuộc nhu cầu monitoring.

Ưu điểm: JMX getter chỉ đọc \`AtomicReference\`, không chờ DB. Cần chú ý bản snapshot là immutable hoặc không được sửa sau khi publish để reader không thấy trạng thái dở dang.

## 7. Freshness và staleness phải được mô tả

Một snapshot không cập nhật có thể trả số liệu cũ mãi mãi. Nếu chỉ công bố \`QueueDepth=120\`, operator có thể nghĩ đó là số liệu hiện tại, dù DB đã mất kết nối 30 phút.

Do vậy, với cached JMX attributes nên công bố thêm:
- \`SnapshotTimestamp\` hoặc \`LastSuccessfulRefreshEpochMillis\`.
- \`SnapshotAgeSeconds\` (tính nhanh từ timestamp).
- \`SnapshotStatus\`: \`OK\`, \`STALE\`, \`NOT_READY\` hoặc \`ERROR\`.
- \`LastRefreshDurationMillis\` nếu có ích.
- \`LastRefreshFailureCount\` hoặc lỗi đã redact.
- TTL hoặc maximum tolerated age được tài liệu hóa.

Ví dụ:

\`\`\`java
@ManagedAttribute
public long getSnapshotAgeSeconds() {
    Instant timestamp = latest.get().refreshedAt();

    if (timestamp.equals(Instant.EPOCH)) {
        return -1L;
    }

    return Math.max(0L,
        Duration.between(timestamp, Instant.now()).getSeconds());
}
\`\`\`

Việc gọi \`Instant.now()\` và tính chênh lệch trong getter này nhẹ, khác với query DB. Nhưng nếu cần consistency tuyệt đối giữa nhiều attribute, dùng một snapshot object/OpenType được công bố có chủ đích thay vì đọc từng getter tại các thời điểm khác nhau.

### 7.1 Chính sách khi refresh thất bại

Có vài lựa chọn:
- **Last known good:** trả dữ liệu cũ kèm trạng thái \`STALE\` và timestamp.
- **Sentinel:** trả \`-1\` hoặc \`UNKNOWN\` với tài liệu ý nghĩa rõ.
- **Exception:** báo lỗi đọc attribute nếu freshness là điều kiện bắt buộc.
- **No update:** tiếp tục giữ snapshot nhưng tăng error counter.

Lựa chọn phụ thuộc consumer. Một dashboard cần số liệu liên tục có thể ưu tiên last known good; một hệ thống điều khiển cần dữ liệu chính xác tuyệt đối có thể không chấp nhận stale snapshot. Đừng để \`0\` được dùng làm fallback nếu \`0\` còn mang ý nghĩa thật là “không có job”.

## 8. Tách operation nặng khỏi attribute

Một thao tác quét sâu không nên nằm trong getter được polling định kỳ:

\`\`\`java
@ManagedAttribute
public String getFullDiagnosticReport() {
    return performSlowFullScan();
}
\`\`\`

Thay bằng hợp đồng chủ động:

\`\`\`java
@ManagedOperation(
    description = "Request bounded diagnostic snapshot")
public String requestDiagnosticSnapshot(int maxItems) {
    // Validate maxItems và tạo tác vụ chẩn đoán.
    return diagnosticService.enqueue(maxItems);
}

@ManagedAttribute
public String getLastDiagnosticStatus() {
    return diagnosticService.cachedStatus();
}
\`\`\`

Ví dụ phụ thuộc \`diagnosticService\` do ứng dụng định nghĩa. Nếu operation bất đồng bộ, nên trả operation ID và có cách đọc trạng thái \`ACCEPTED/RUNNING/SUCCEEDED/FAILED\`. Tránh trả report nhiều MB trong một attribute; có thể dùng link hoặc ID tham chiếu tới storage quản trị an toàn, không đưa URL chứa secret vào JMX.

Operation nặng vẫn phải có quyền, rate limit, timeout, concurrency limit và audit. Việc đổi getter thành operation không tự làm computation rẻ hơn; nó chỉ giúp tách invocation có chủ đích khỏi polling thường xuyên.

## 9. Timeout phải được đặt ở tầng thực hiện I/O

Một JMX client có thể timeout hoặc đóng connection khi getter đang đợi database. Điều đó không nhất thiết dừng query server-side. Vì vậy **đừng xem timeout ở phía client là lớp bảo vệ duy nhất**.

Cần timeout trong dependency call:

\`\`\`java
public long countPendingWithTimeout() {
    // Database query với statement/query timeout được cấu hình.
    // Connection acquisition timeout và network socket timeout phù hợp.
    return repository.countPending();
}
\`\`\`

Những timeout cần cân nhắc:
- Connection acquisition timeout.
- Network connect timeout.
- Read/response timeout.
- Database statement/query timeout.
- Application-level deadline.
- Cancellation behavior khi deadline hết.
- Resource cleanup nếu xảy ra exception.

Các setting phụ thuộc driver, HTTP client, JDBC pool và provider. Không suy luận một property JMX Remote sẽ tự giới hạn thời gian của tất cả getter. Có thể client đã bỏ chờ nhưng server vẫn đang giữ thread hoặc connection.

## 10. Concurrency limit và chống stampede

Khi nhiều JMX client đồng thời đọc một getter nặng, số request có thể chồng lên nhau. Một cache không kiểm soát refresh có thể biến thành **thundering herd**: nhiều reader cùng thấy cache hết hạn và cùng gọi DB.

Hướng thiết kế:
- Một background refresh worker chịu trách nhiệm cập nhật snapshot.
- Getter chỉ trả last known value, không tự refresh blocking.
- Nếu cần refresh on-demand, dùng single-flight hoặc mutex/semaphore.
- Đặt giới hạn số task refresh đồng thời.
- Có timeout và circuit breaker khi dependency đang lỗi.
- Thêm jitter giữa các instance để tránh tất cả node refresh cùng lúc.
- Có backoff sau nhiều lần refresh thất bại.

Ví dụ ý tưởng về giới hạn đồng thời:

\`\`\`java
private final Semaphore refreshSlots = new Semaphore(1);

public boolean tryRefresh() {
    if (!refreshSlots.tryAcquire()) {
        return false; // Một refresh đã chạy.
    }

    try {
        refreshSnapshot();
        return true;
    } finally {
        refreshSlots.release();
    }
}
\`\`\`

Ví dụ cần được tích hợp phù hợp với scheduler và error handling thực tế; nếu chỉ dùng một scheduled task không chồng lấn thì semaphore có thể không cần. Không nên lock toàn bộ JMX getter trong lúc làm I/O.

## 11. Cache có thể làm sai ý nghĩa metric nếu không thiết kế kỹ

Một cached attribute cần xác định:
- Metric có phạm vi JVM, instance, tenant hay cluster?
- Cập nhật theo thời gian hay theo sự kiện?
- Có thể mất event hoặc bị reset khi restart không?
- Snapshot có nhất quán giữa các trường không?
- Staleness tối đa được chấp nhận?
- Khi refresh fail, client có biết dữ liệu cũ không?
- Khi sự kiện chưa được xử lý xong, counter đã tăng chưa?

Ví dụ \`getQueueDepth()\` dựa trên SQL \`COUNT(*)\` và \`getCompletedCount()\` dựa trên in-memory counter có thể thuộc những thời điểm khác nhau. Không nên diễn giải hai giá trị như một transactionally consistent snapshot nếu không có cơ chế đồng bộ.

### 11.1 Volatile publication và immutable data

Nếu dùng:

\`\`\`java
private volatile QueueSnapshot latestSnapshot;
\`\`\`

và \`QueueSnapshot\` là immutable, các reader có thể nhận một snapshot đã publish mà không cần lock nặng. Nếu snapshot chứa mutable map/list rồi producer sửa sau publication, \`volatile\` không làm các collection ấy trở nên thread-safe.

Với dữ liệu phức tạp, tạo bản copy immutable trước khi publish hoặc dùng cấu trúc thread-safe đã được kiểm tra phù hợp.

## 12. Không giữ lock nghiệp vụ khi tính metric

Một anti-pattern:

\`\`\`java
@ManagedAttribute
public int getBacklogSize() {
    synchronized (globalSchedulerLock) {
        return performComplexScan();
    }
}
\`\`\`

Nếu scan lâu, luồng xử lý công việc có thể bị chặn. Tệ hơn, getter có thể gọi dependency khác rồi deadlock do thứ tự lock không rõ.

Các lựa chọn tốt hơn:
- Counter được cập nhật dọc luồng xử lý.
- Snapshot được tạo ngoài critical section.
- Chỉ copy một cấu trúc nhỏ dưới lock, rồi tính ngoài lock.
- Dùng \`LongAdder\`, \`AtomicLong\`, \`StampedLock\` hoặc cấu trúc tương ứng tùy tính nhất quán cần thiết.
- Không gọi remote I/O khi giữ lock của domain service.

Không phải lúc nào \`LongAdder\` cũng thay được \`AtomicLong\`: nếu cần compare-and-set hoặc giá trị chính xác tuyến tính cho quyết định điều khiển, phải chọn primitive phù hợp.

## 13. Giới hạn kích thước payload

JMX client có thể đọc attribute là \`String\`, array, composite data hoặc collection mapping phù hợp. Một getter trả toàn bộ stack traces, sessions hoặc job list có thể gây:

- Heap allocation lớn.
- Serialization/deserialization tốn thời gian.
- RMI network overhead.
- Rủi ro out-of-memory ở server hoặc client.
- Lộ thông tin nhạy cảm.
- Tăng thời gian JConsole render.

Nên công bố summary nhỏ:

\`\`\`java
@ManagedAttribute
public int getPendingJobCount() {
    return cachedPendingCount;
}

@ManagedAttribute
public String getTopFailureCategory() {
    return lastSnapshot.topFailureCategory();
}
\`\`\`

Nếu cần danh sách, áp dụng pagination/bounded diagnostics qua operation thích hợp. JMX không phải lựa chọn mặc định để stream dữ liệu lớn hoặc xuất toàn bộ database.

## 14. Lấy dữ liệu từ metrics thay vì tự truy vấn lại

Nếu ứng dụng đã có Micrometer, Dropwizard Metrics hoặc một metrics backend, nhiều chỉ số đã được cập nhật trong luồng nghiệp vụ hoặc collector tối ưu. Có thể đọc counter/gauge được cập nhật sẵn thay vì chạy query mới cho JMX.

Ví dụ:

\`\`\`java
private final AtomicLong activeJobs = new AtomicLong();

public void onJobStarted() {
    activeJobs.incrementAndGet();
}

public void onJobCompleted() {
    activeJobs.decrementAndGet();
}

@ManagedAttribute
public long getActiveJobs() {
    return activeJobs.get();
}
\`\`\`

Ví dụ đơn giản; trong production phải bảo đảm mọi đường hoàn tất/error/cancel đều cập nhật counter đúng. Số active jobs âm hoặc không trở về 0 có thể là lỗi instrumentation.

Đối với metric cần time-series, alerting hoặc labels nhiều chiều, một backend observability chuyên dụng thường phù hợp hơn JMX getter trả dữ liệu tổng hợp nặng.

## 15. Tách tài nguyên quản trị khỏi tài nguyên nghiệp vụ

Nếu snapshot refresh bắt buộc dùng I/O, nên tránh để nó tiêu thụ vô hạn thread/connection chung với request chính.

Cân nhắc:
- Một executor riêng hoặc bounded scheduler.
- Thread pool nhỏ có queue giới hạn.
- Timeout thấp hơn SLA của nghiệp vụ.
- Rate limit và backoff.
- Không để failures của monitoring làm crash application context.
- Dừng scheduler khi context đóng.
- Không để số task tích lũy vô hạn sau mỗi kỳ polling.

Một background metrics refresh không nên là điều kiện sống còn của toàn hệ thống, trừ khi dữ liệu đó phục vụ một yêu cầu an toàn được thiết kế rõ.

## 16. Vấn đề Spring AOP và @Transactional trong getter

Một getter JMX có thể gọi Spring service sử dụng \`@Transactional\` hoặc bị proxy AOP. Điều này không miễn trừ chi phí I/O. Một JMX invocation có thể mở transaction, lấy database connection và giữ tài nguyên trong thời gian query.

Nếu export raw target thay vì proxy, advice có thể không được áp dụng. Nếu export proxy, metadata JMX phải được assembler nhận diện đúng. Một management adapter riêng gọi service qua Spring proxy thường giúp giữ transaction semantics nhưng tránh phơi bày toàn bộ service.

Không nên gắn \`@Transactional\` lên getter chỉ vì nó truy vấn DB mà không đánh giá transaction isolation, timeout và pool pressure. Đối với monitoring, một service chuyên lấy snapshot có giới hạn thường dễ kiểm soát hơn.

## 17. Xử lý exception trong getter

JMX getter có thể ném exception do dependency lỗi. Client có thể nhận \`MBeanException\`, \`ReflectionException\`, \`IOException\` hoặc exception phù hợp với tầng thực thi.

Cần phân biệt:
- Dependency unavailable.
- Cached snapshot stale.
- Attribute not yet initialized.
- Permission denied.
- Server-side computation failure.
- Remote transport failure.

Nếu tất cả biến thành \`0\`, dashboard có thể nhầm “không có job” với “không đọc được metric”. Nếu mọi exception đều lan ra mà không kiểm soát, monitoring có thể spam error và tăng retry load.

Một mô hình tốt là giữ last known good kèm status và timestamp, đồng thời ghi lỗi đã redact, có rate limit, không chứa query/credentials trong attribute string.

## 18. Đo hiệu năng JMX attribute

Nên đánh giá:
- P50/P95/P99 latency của getter.
- Số lượt đọc mỗi giây.
- Số client đồng thời.
- CPU time và allocation per read.
- Database queries/remote calls được kích hoạt.
- Thread pool hoặc connection pool utilization.
- Lock contention và thời gian chờ.
- Mức độ chậm đi của nghiệp vụ khi tăng polling.
- Staleness và refresh failure rate.
- Kích thước serialized response.

Ví dụ kế hoạch test:

\`\`\`text
Scenario A: Không poll JMX → baseline CPU, DB QPS, latency nghiệp vụ.
Scenario B: 1 client poll 10 giây/lần.
Scenario C: 10 client poll 5 giây/lần.
Scenario D: DB chậm 2 giây và có timeout.
Scenario E: DB unavailable, client retry.
Scenario F: JVM heap pressure, nhiều attributes được đọc.
\`\`\`

Đối chiếu xem polling có tăng DB QPS tuyến tính hay không. Nếu có, attribute còn phụ thuộc I/O trực tiếp. Sau khi chuyển snapshot, kỳ vọng số query do refresh được kiểm soát theo schedule, gần như không phụ thuộc số lượng JMX clients.

## 19. Integration test cho getter nhẹ và snapshot

Một test có thể xác minh việc đọc attribute không gọi repository trực tiếp:

\`\`\`java
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import java.time.Instant;

class QueueSnapshotMonitorTest {

    @Test
    void readingCachedAttributeDoesNotQueryDatabase() {
        QueueRepository repository = mock(QueueRepository.class);
        QueueSnapshotMonitor monitor =
            new QueueSnapshotMonitor(repository);

        long depth = monitor.getQueueDepth();

        assertEquals(-1L, depth);
        verifyNoInteractions(repository);
    }
}
\`\`\`

Nếu test muốn xác minh refresh:

\`\`\`java
when(repository.countPendingWithTimeout()).thenReturn(42L);

monitor.refreshSnapshot();

assertEquals(42L, monitor.getQueueDepth());
assertEquals("OK", monitor.getQueueSnapshotStatus());
verify(repository, times(1)).countPendingWithTimeout();
\`\`\`

Ví dụ cần đặt trong cùng test fixture và khai báo repository interface tương ứng. Kiểm tra chính xác với ứng dụng thật phải có test qua \`MBeanServer.getAttribute\` để chứng minh export path dùng getter đã tối ưu, không phải getter của một bean/proxy khác.

## 20. Kiểm tra JMX contract và latency thực tế

Ví dụ đọc từ MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=Queue,name=Orders");

long start = System.nanoTime();
Object value = server.getAttribute(name, "QueueDepth");
long elapsedNanos = System.nanoTime() - start;

System.out.println("QueueDepth=" + value);
System.out.println("Elapsed ms=" + elapsedNanos / 1_000_000.0);
\`\`\`

Đây là latency của call trong cùng JVM qua server interface, không phải remote latency. Remote client còn có network, serialization, connector scheduling và error handling. Không nên dùng một lần đo để đặt SLO; cần nhiều lượt, warm-up và các tình huống tải phù hợp.

Đối với Spring \`@ManagedAttribute\`, tên attribute phải được xác minh qua \`MBeanInfo\` nếu naming/assembler có tùy biến.

## 21. Khi nào nên dùng operation thay vì attribute?

| Nhu cầu | Hình thức đề xuất |
|---|---|
| Current queue depth được cập nhật sẵn | Attribute nhẹ |
| Counter theo dõi thường xuyên | Attribute |
| Snapshot có refresh mỗi 10 giây | Attribute chứa cached value và timestamp |
| Quét toàn bộ pending jobs | Bounded operation có quyền |
| Xuất diagnostic report lớn | Operation tạo job, trả ID/trạng thái |
| Kết nối thử tới downstream | Operation chủ động, có timeout/rate limit |
| Thay mức log hoặc clear cache | Operation điều khiển với authorization/audit |
| Tính aggregate cần nhiều phút | Background task và trạng thái tiến độ |

Một operation cũng có thể bị nhiều client gọi, nên vẫn cần giới hạn tải. Sự khác biệt quan trọng là operator/script thấy rõ thao tác chủ động thay vì một getter được polling vô thức.

## 22. Những hiểu lầm phổ biến

**“Getter là read-only nên không ảnh hưởng hệ thống.”** Sai: có thể dùng CPU/I/O/lock và làm chậm nghiệp vụ.

**“Client JMX timeout thì server đã dừng truy vấn.”** Không chắc. Getter có thể vẫn chạy và giữ tài nguyên.

**“Đưa @ManagedAttribute vào bean tự tạo cache.”** Không. Spring exporter chỉ công bố metadata, không tối ưu implementation.

**“Lấy nhiều attribute trong một getAttributes là chỉ chạy một lần tính.”** Không bảo đảm; mỗi attribute có thể gọi getter riêng.

**“Mỗi metric phải tuyệt đối mới.”** Tùy contract. Với monitoring, stale vài giây có thể chấp nhận nếu freshness được biểu diễn rõ.

**“Cached metric trả 0 khi DB lỗi là ổn.”** Nguy hiểm nếu 0 là giá trị nghiệp vụ hợp lệ; dùng status/sentinel có tài liệu.

**“Đổi getter thành operation là đủ.”** Operation nặng vẫn cần concurrency/rate limit, timeout và phân quyền.

**“Một số liệu trên JMX phải bao gồm toàn cluster.”** Không mặc định; MBean thường đại diện cho JVM/instance cụ thể.

## 23. Runbook xử lý attribute gây chậm hệ thống

1. Xác định ObjectName và attribute đang bị poll.
2. Đo tần suất từ từng monitoring agent và dashboard.
3. Truy vết getter tới DB, HTTP, file, lock hoặc computation.
4. Đo p95/p99, CPU/heap allocation và downstream load.
5. Kiểm tra timeout server-side, chứ không chỉ client timeout.
6. Giảm tần suất poll tạm thời nếu tải đang nguy hiểm.
7. Chuyển getter sang cached snapshot hoặc counter cập nhật sẵn.
8. Đặt TTL/freshness status và timeout cho refresh worker.
9. Kiểm tra nhiều client poll đồng thời và dependency unavailable.
10. Kiểm tra impact sau thay đổi lên service latency và MBeanInfo.
11. Cập nhật runbook để operator không dùng operation nặng như polling metric.

## 24. Bài tập vận dụng

**Bài 1 — SQL COUNT trong getter.** \`getPendingOrders()\` dùng \`SELECT COUNT(*)\` trên bảng hàng triệu dòng, có 20 client poll mỗi 5 giây. Hãy ước lượng số query/giây và thiết kế cache refresh mỗi 15 giây, có trạng thái stale.

**Bài 2 — Lock contention.** Getter lấy global scheduler lock rồi duyệt toàn bộ queue. Phân tích ảnh hưởng và đề xuất counter/snapshot không giữ lock lâu.

**Bài 3 — Timeout.** DB mất kết nối và getter treo. Hãy liệt kê timeout cần có ở JDBC, pool và application, giải thích vì sao JMX client timeout không đủ.

**Bài 4 — Monitoring stampede.** 15 client cùng đọc cached attribute khi TTL hết; mọi thread tự refresh. Thiết kế single-flight background refresh và last known good.

**Bài 5 — Payload lớn.** Getter trả danh sách 100.000 job cùng metadata. Chuyển thành count/summary và bounded diagnostic operation có request ID.

**Bài 6 — Kiểm thử.** Dùng mock repository chứng minh \`getQueueDepth()\` không gọi DB, \`refreshSnapshot()\` gọi một lần, và trạng thái chuyển thành \`STALE\` khi refresh fail.

## Tổng kết

Trong Spring Framework JMX, attribute thường được đọc tự động và lặp lại bởi nhiều client. Do đó một getter có tính toán nặng hoặc truy cập I/O có thể khuếch đại CPU, DB QPS, network, lock contention và memory pressure vào đúng lúc hệ thống cần được quan sát ổn định. Nên thiết kế getter như một **đường đọc nhanh, bounded và ít phụ thuộc bên ngoài**, chuyển tính toán nặng sang scheduled/background refresh hoặc operation chẩn đoán có kiểm soát. Khi dùng snapshot, công bố thời điểm cập nhật, trạng thái stale và failure behavior. Đo kiểm dưới tải polling thật, đặt timeout ở tầng dependency và quản lý concurrency để chính hoạt động monitoring không trở thành nguyên nhân gây sự cố.
