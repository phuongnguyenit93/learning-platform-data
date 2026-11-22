# Chọn thông tin quản trị có ích cho vận hành trong Spring JMX

## 1. Bối cảnh

Một ứng dụng Spring có thể có hàng trăm Spring beans và hàng nghìn methods. Nhưng **management API tốt không phải API expose càng nhiều thông tin càng tốt**. Mục tiêu của JMX là giúp người vận hành nhận biết hệ thống đang ở trạng thái nào, xác định dấu hiệu bất thường, tìm nguyên nhân và thực hiện những thao tác quản trị được cho phép một cách an toàn.

Trong Spring Framework JMX, các annotation phổ biến:

- \`@ManagedResource\` mô tả một managed resource và tên JMX.
- \`@ManagedAttribute\` công bố thuộc tính đọc/ghi cho công cụ quản trị.
- \`@ManagedOperation\` công bố thao tác có thể được gọi qua JMX.
- \`@ManagedNotification\` mô tả các loại thông báo mà MBean có thể phát.
- \`@ManagedOperationParameter\` cung cấp mô tả tham số operations.

Việc lựa chọn những gì nên expose là một quyết định **thiết kế management contract**, không chỉ là thao tác thêm annotation.

Bài này giúp bạn:
1. Xuất phát từ câu hỏi vận hành trước khi chọn thuộc tính.
2. Phân biệt trạng thái, chỉ số, thông tin cấu hình và thao tác quản trị.
3. Thiết kế managed attributes dễ hiểu, ít tác động và chi phí đọc thấp.
4. Chọn operations hữu ích nhưng hạn chế rủi ro.
5. Sử dụng notifications cho các chuyển trạng thái quan trọng.
6. Thiết kế ObjectName, descriptions, units và error semantics nhất quán.
7. Tránh expose dữ liệu nhạy cảm và các phương thức nghiệp vụ không cần thiết.
8. Kiểm thử management API bằng \`MBeanServer\` và các tình huống vận hành thực tế.

## 2. Bắt đầu từ câu hỏi của người vận hành

Trước khi viết code, hãy liệt kê những câu hỏi người trực hệ thống cần trả lời:

- Ứng dụng còn hoạt động không?
- Tài nguyên nào đang quá tải?
- Queue nào đang bị backlog?
- Có bao nhiêu công việc đang chạy, thành công hoặc thất bại?
- Kết nối phụ thuộc quan trọng có lỗi không?
- Cấu hình runtime nào đang có hiệu lực?
- Lỗi gần nhất thuộc loại gì và xảy ra khi nào?
- Có thể tạm dừng một worker một cách an toàn không?
- Khi sự cố xảy ra, thao tác nào có thể phục hồi mà không phá dữ liệu?
- Khi cần hỗ trợ, người vận hành có thể xác định chính xác instance nào đang gặp vấn đề không?

Một ví dụ bảng thiết kế:

| Câu hỏi vận hành | Thành phần quản trị đề xuất | Lý do |
|---|---|---|
| Queue đang tồn đọng bao nhiêu? | Read-only \`PendingCount\` | Thấy backlog |
| Worker đang chạy hay tạm dừng? | Read-only \`State\` | Xác định trạng thái |
| Lần hoàn tất gần nhất khi nào? | \`LastSuccessTime\` | Phát hiện ngừng tiến triển |
| Tỷ lệ lỗi có tăng? | Counters và metrics | Phân tích xu hướng |
| Có thể tạm dừng nhận việc mới? | Operation \`pauseIntake()\` | Thao tác có phạm vi rõ |
| Có thể tiếp tục xử lý? | Operation \`resumeIntake()\` | Phục hồi theo quy trình |
| Có lỗi nghiêm trọng mới? | Notification \`worker.failed\` | Báo hiệu tức thời |
| Có cần thấy cấu hình runtime? | Read-only non-secret settings | Chẩn đoán drift |

Không nhất thiết giải quyết mọi câu hỏi qua JMX. Các giải pháp như logs, distributed tracing, metrics backend, health endpoints và dashboards có thế mạnh riêng. JMX nên bổ sung những thông tin **phù hợp với trạng thái trong JVM và management interface của thành phần**.

## 3. Nguyên tắc chọn thông tin quản trị

### 3.1. Hữu ích cho một quyết định

Một attribute tốt phải dẫn tới một hành động hoặc đánh giá rõ ràng:

\`\`\`text
PendingCount = 1250
\`\`\`

thường hữu ích hơn:

\`\`\`text
InternalQueueObject = com.example.queue.QueueImpl@3d01c6
\`\`\`

Thông tin thứ nhất có thể dùng đặt ngưỡng cảnh báo hoặc theo dõi backlog. Thông tin thứ hai là Java object representation khó hiểu và thiếu ổn định.

### 3.2. Có ngữ nghĩa chính xác

Tên \`Count\` chưa đủ. Count của điều gì? Tại thời điểm nào? Giá trị tích lũy hay tức thời?

Nên đặt:
- \`PendingCount\` — số công việc chưa xử lý ở thời điểm đọc.
- \`ProcessedTotal\` — tổng số công việc đã xử lý từ khi reset.
- \`FailuresTotal\` — tổng lần lỗi theo một phạm vi rõ.
- \`LastCompletedAt\` — thời gian lần hoàn tất gần nhất.

Mỗi attribute cần description làm rõ **đơn vị, phạm vi và điều kiện reset**.

### 3.3. Đọc nhanh và ít tác động

JConsole hoặc monitoring collector có thể đọc attribute liên tục. Getter đọc một \`AtomicLong\` thường chấp nhận được; getter thực hiện query toàn bộ database hoặc gọi API bên ngoài có thể gây tải.

Một managed getter nên cố gắng:
- Thời gian thực thi nhỏ và ổn định.
- Không side effect.
- Không làm block hot path.
- Không khóa toàn cục quá lâu.
- Có giá trị mặc định/biểu thị unavailable rõ.
- Có caching/snapshot nếu tính toán tốn kém.

### 3.4. Không expose dữ liệu mật

Tránh expose:
- Passwords, API keys, bearer tokens.
- Connection strings chứa credentials.
- Customer PII, email, địa chỉ.
- Internal raw stack traces chứa bí mật.
- Payload nghiệp vụ chưa được phân loại.
- Các đường dẫn hoặc configuration values nhạy cảm không cần cho vận hành.

Một attribute đọc được qua JMX có thể bị thu thập bởi công cụ ngoài ứng dụng. Không giả định nó chỉ hiện trên máy local.

### 3.5. Hợp đồng ổn định

JMX clients và monitoring scripts có thể phụ thuộc vào ObjectNames, attribute names và operation signatures. Chỉ thay tên vì refactor class Java sẽ làm management interface khó ổn định.

## 4. Phân loại management API

Có thể chia thông tin thành năm nhóm.

| Nhóm | Ví dụ | Thiết kế phù hợp |
|---|---|---|
| Identity | App, instance, version | Read-only attributes |
| Health/state | Running, paused, degraded | Read-only attributes + notifications |
| Metrics | Queue depth, completed count, error rate | Attributes hoặc metrics system |
| Configuration | Current concurrency limit, current mode | Read-only trước; writable khi thật cần |
| Control | Pause, resume, clear cache | Explicit operations, validation và authorization |

Mỗi nhóm có rủi ro khác nhau. Identity và state thường dễ expose hơn, nhưng vẫn cần xem xét dữ liệu nhạy cảm. Control operations có thể ảnh hưởng dữ liệu production nên cần kiểm soát chặt hơn.

## 5. Ví dụ thiết kế một MBean theo use case

Giả sử ứng dụng Spring có worker xử lý đơn hàng. Người vận hành cần biết:
- Worker có nhận việc mới không?
- Backlog bao nhiêu?
- Công việc đang chạy bao nhiêu?
- Khi nào xử lý thành công gần nhất?
- Có thể tạm dừng nhận việc mới trong đợt bảo trì không?

Một managed bean có thể như sau:

\`\`\`java
package com.example.operations;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Worker,name=OrderProcessor",
    description = "Order processing worker management"
)
public class OrderWorkerManagement {

    private final AtomicInteger pendingCount = new AtomicInteger();
    private final AtomicInteger activeCount = new AtomicInteger();
    private final AtomicLong processedTotal = new AtomicLong();

    private volatile boolean intakePaused;
    private volatile Instant lastCompletedAt;

    @ManagedAttribute(description = "Pending orders at read time")
    public int getPendingCount() {
        return pendingCount.get();
    }

    @ManagedAttribute(description = "Orders currently being processed")
    public int getActiveCount() {
        return activeCount.get();
    }

    @ManagedAttribute(description = "Processed orders since counter reset")
    public long getProcessedTotal() {
        return processedTotal.get();
    }

    @ManagedAttribute(description = "Whether new work intake is paused")
    public boolean isIntakePaused() {
        return intakePaused;
    }

    @ManagedAttribute(description = "Last successful completion, ISO-8601 UTC")
    public String getLastCompletedAt() {
        Instant value = lastCompletedAt;
        return value == null ? "" : value.toString();
    }

    @ManagedOperation(description = "Pause intake of new orders")
    public void pauseIntake() {
        intakePaused = true;
    }

    @ManagedOperation(description = "Resume intake of new orders")
    public void resumeIntake() {
        intakePaused = false;
    }
}
\`\`\`

Đây là mô hình minh họa management interface. Trong ứng dụng thật, state/counters nên được lấy từ service chịu trách nhiệm xử lý, không tạo một bản state độc lập dễ lệch với worker thực tế. Hai operations nên delegate sang service có validation và concurrency handling.

### Vì sao không expose mọi method?

Nếu \`OrderWorkerManagement\` có method \`processInternalOrder()\`, \`loadCustomerData()\` hoặc \`deleteAllPendingRecords()\`, chúng không nên được export chỉ vì là public methods. Expose một method là công bố một khả năng quản trị có thể bị gọi qua JMX, bao gồm từ xa nếu connector có quyền.

## 6. Read-only attributes trước tiên

JMX attribute có thể read-only hoặc writable. Khi người vận hành chỉ cần quan sát, chọn read-only.

\`\`\`java
@ManagedAttribute(description = "Number of active jobs")
public int getActiveJobs() {
    return activeJobs.get();
}
\`\`\`

Với writable attribute:

\`\`\`java
@ManagedAttribute(description = "Maximum allowed parallel jobs")
public int getMaxParallelJobs() {
    return maxParallelJobs;
}

@ManagedAttribute(description = "Maximum allowed parallel jobs")
public void setMaxParallelJobs(int value) {
    if (value < 1 || value > 64) {
        throw new IllegalArgumentException("Must be within 1..64");
    }
    maxParallelJobs = value;
}
\`\`\`

Writable attribute cần:
- Ràng buộc min/max và trạng thái hợp lệ.
- Xác định tác động thay đổi có tức thời không.
- Quy tắc persistence qua restart.
- Concurrency safety.
- Phân quyền JMX.
- Logging/audit khi giá trị nhạy cảm.
- Rollback hoặc cách phục hồi nếu thay đổi không hợp lệ.

Nếu thay đổi cấu hình có nhiều điều kiện hoặc tác động lớn, một managed operation có tên rõ ràng đôi khi tốt hơn setter đơn giản.

## 7. Chọn kiểu dữ liệu dễ quản trị

Thuộc tính nên dùng các kiểu có thể hiển thị và truyền qua JMX:

- Primitives và wrappers.
- \`String\`, \`boolean\`, \`long\`, \`double\`.
- Enum với representation có hợp đồng rõ.
- Arrays đơn giản khi cần.
- \`CompositeData\`, \`TabularData\` hoặc MXBean-compatible types cho dữ liệu cấu trúc.

Không nên expose trực tiếp object graph phức tạp:
- Spring ApplicationContext.
- DataSource implementation.
- EntityManager/Session.
- ThreadPoolExecutor object nguyên bản.
- Hibernate/JPA entities hoặc collection lớn.
- DTO nội bộ đòi hỏi remote client có classpath đầy đủ.

Các kiểu phức tạp làm tăng chi phí serialize và nguy cơ không tương thích. Với monitoring, nhiều attributes nhỏ, rõ nghĩa thường thuận tiện hơn trả một object nội bộ tùy ý.

### Biểu diễn thời gian

Nên cung cấp timestamp theo một chuẩn ổn định, ví dụ:
- ISO-8601 UTC string: \`2026-11-11T08:30:00Z\`.
- Epoch milliseconds với mô tả đơn vị rõ ràng.

Tránh trả thời gian theo locale mặc định của máy vì người vận hành ở nhiều múi giờ có thể hiểu nhầm.

## 8. Chọn metrics nào đáng expose?

Không phải số liệu nào có thể tính cũng hữu ích.

### Một số nhóm thường có giá trị

**Throughput**
- ProcessedTotal.
- CompletedPerMinute, nếu có phương pháp tính rõ.
- TasksAcceptedTotal.

**Backlog và saturation**
- PendingCount.
- ActiveCount.
- QueueCapacity.
- RejectedTasksTotal.

**Failures**
- FailedTotal.
- LastFailureAt.
- LastFailureCategory đã được lọc thông tin nhạy cảm.

**Timing**
- LastSuccessAt.
- ProcessingDurationMs có định nghĩa và aggregation rõ.
- QueueWaitDurationMs nếu có instrumentation thích hợp.

**Resource utilization**
- ActiveConnections.
- PoolSize.
- FreePoolSlots.
- CacheEntryCount.

### Tránh metrics thiếu semantics

Ví dụ \`Load=0.8\` không nói rõ:
- 0.8 là 80% hay số tuyệt đối?
- Đo trong thời gian nào?
- Thuộc CPU, pool, queue hay một chỉ số riêng?
- Nguồn dữ liệu nào và độ cập nhật?

Tên tốt hơn có thể là \`WorkerUtilizationRatio\`, description: “Active worker slots divided by configured maximum, range 0.0..1.0”.

### Không biến JMX thành metrics backend

JMX cung cấp runtime management interface; hệ thống metrics thường tốt hơn cho:
- Lưu time series dài hạn.
- Truy vấn tập trung trên nhiều instances.
- Histograms và percentiles.
- Cardinality controls và alerting.
- Dashboard cross-service.

Nếu đã có Micrometer/Prometheus, không nhất thiết expose toàn bộ metrics lần thứ hai bằng custom JMX attributes. Có thể dùng JMX cho các trạng thái chẩn đoán và operations mà metrics không diễn đạt tốt.

## 9. Thiết kế operations theo mức rủi ro

Chọn operation khi người vận hành thực sự cần **hành động**.

Một số ví dụ:
- \`pauseIntake()\`: ngừng nhận việc mới, không làm mất công việc đang chạy.
- \`resumeIntake()\`: tiếp tục.
- \`reloadReadOnlyConfiguration()\`: nạp cấu hình đã kiểm chứng.
- \`resetStatistics()\`: đặt lại counters không ảnh hưởng nghiệp vụ.
- \`triggerHealthCheck()\`: chạy kiểm tra có chi phí được giới hạn.

Một operation nguy hiểm:
- \`deleteAllOrders()\`.
- \`resetProductionDatabase()\`.
- \`drainQueueWithoutAck()\`.

Những operations có tác động lớn nên không được expose qua JMX mặc định. Nếu bắt buộc, cần thiết kế authorization, audit, preconditions, concurrency controls và quy trình vận hành rõ.

### Bảng kiểm operation

| Câu hỏi | Yêu cầu |
|---|---|
| Hành động có idempotent không? | Định nghĩa retry semantics |
| Có thay đổi dữ liệu nghiệp vụ không? | Review rủi ro và quyền |
| Có chạy lâu không? | Tránh block JMX connector |
| Có thể chạy đồng thời không? | Concurrency guard |
| Nếu fail giữa chừng thì sao? | Error/state model |
| Tham số đã validate chưa? | Reject invalid input |
| Có ghi audit không? | Theo mức tác động |
| Có cần rollback/compensation? | Thiết kế rõ |
| Có giới hạn tần suất không? | Rate limiting/operational policy |

### Operations dài nên tạo job bất đồng bộ

Thay vì:

\`\`\`java
@ManagedOperation
public void rebuildAllIndexes() {
    // 30 phút xử lý trong JMX call.
}
\`\`\`

có thể dùng:

\`\`\`java
@ManagedOperation(description = "Request index rebuild and return job ID")
public String requestIndexRebuild() {
    return rebuildService.submit();
}
\`\`\`

và expose \`getRebuildStatus()\` hoặc notification về trạng thái. JMX vẫn là kênh gọi hành động, nhưng không phải đường truyền kết quả lớn kéo dài nhiều phút.

Cần quyết định semantics của request ID, idempotency và retry, đặc biệt khi remote client timeout sau khi server đã nhận request.

## 10. Notifications dùng cho thay đổi quan trọng

Một JMX notification có thể phù hợp khi:
- Worker chuyển sang DEGRADED.
- Queue bị paused/resumed.
- Một tác vụ quản trị hoàn tất.
- Resource pool vượt ngưỡng.
- Configuration reload thành công/thất bại.

\`\`\`java
@ManagedNotification(
    name = "com.example.orders.worker.degraded",
    notificationTypes = {"com.example.orders.worker.degraded"},
    description = "Worker entered degraded state"
)
\`\`\`

Annotation mô tả loại notification mà MBean có thể phát, **không tự tạo event**. Producer cần thực sự phát qua \`NotificationPublisher\` hoặc JMX broadcaster phù hợp.

Không nên phát notification cho từng item xử lý ở hệ thống có throughput lớn; điều đó có thể tạo overload, noise và khó phân biệt sự kiện quan trọng.

### Notification không phải durable event queue

JMX notifications không bảo đảm replay bền vững khi listener chưa đăng ký, mất kết nối hoặc JVM restart. Nếu không được mất event, hãy dùng durable messaging/event store. JMX notification nên là tín hiệu cho dashboard refresh hoặc thông báo quản trị.

## 11. ObjectName: tên có ý nghĩa và ổn định

ObjectName:

\`\`\`text
com.example.orders:type=Worker,name=OrderProcessor
com.example.orders:type=Queue,name=Payments
com.example.orders:type=Cache,name=Products
\`\`\`

Một quy tắc hữu ích:
- Domain theo application.
- type theo loại MBean.
- name theo logical resource.
- instance khi có nhiều MBeans cùng loại trên một server.
- env nếu muốn phân biệt prod/staging/local trong metadata.

Không nhét secrets, request IDs, session IDs hoặc user data vào ObjectName.

Tránh sử dụng tên class runtime làm hợp đồng JMX; Spring AOP proxies và refactor có thể làm class name thay đổi.

### Tên theo môi trường

\`\`\`text
com.example.orders:env=prod,type=Queue,name=Payments
com.example.orders:env=staging,type=Queue,name=Payments
\`\`\`

Cùng tên có thể tồn tại trên các JVM khác nhau mà không conflict. Naming chỉ là một phần của identity; monitoring phải gắn target/connector identity. Key env không tự bảo vệ quyền thao tác.

## 12. Metadata và mô tả management contract

\`@ManagedAttribute(description="...")\` hoặc \`@ManagedOperation(description="...")\` nên được viết như tài liệu ngắn cho operator.

Ví dụ tốt:

\`\`\`java
@ManagedAttribute(
    description = "Number of pending jobs, sampled at read time"
)
public int getPendingCount() { ... }
\`\`\`

Ví dụ kém:

\`\`\`java
@ManagedAttribute(description = "Value")
public int getCount() { ... }
\`\`\`

Nếu một value có đơn vị, nói rõ:
- milliseconds.
- seconds.
- bytes.
- count.
- percentage.
- ratio 0..1.
- epoch milliseconds.

Với counter, nói rõ phạm vi reset:
- Since application start.
- Since last statistics reset.
- Within last minute.

Tên/description không thực thi validation hoặc authorization. Chúng chỉ giúp client hiểu hợp đồng.

## 13. Chỉ expose các thành phần cần thiết

Trong một Spring service lớn có các methods:

\`\`\`java
public class PaymentService {
    public void chargeCustomer(...);
    public void refund(...);
    public void reconcile(...);
    public long countPending(...);
}
\`\`\`

Không nên gắn \`@ManagedOperation\` lên toàn bộ chỉ vì đội vận hành muốn có “nhiều công cụ”.

Một facade quản trị riêng thường rõ ràng hơn:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.payments:type=Operations,name=Reconciliation"
)
public class PaymentManagement {

    private final PaymentService service;

    public PaymentManagement(PaymentService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending reconciliations")
    public long getPendingCount() {
        return service.countPending();
    }

    @ManagedOperation(description = "Request bounded reconciliation job")
    public String requestReconciliation() {
        return service.submitReconciliation();
    }
}
\`\`\`

Lợi ích:
- Management API nhỏ, có owner.
- Dễ review security.
- Tách trạng thái và hành động khỏi service implementation details.
- Dễ kiểm tra JMX metadata.
- Giảm phụ thuộc vào việc AOP proxy expose methods nào.

Tuy nhiên facade vẫn phải validate, giới hạn tần suất và xử lý exception. Tên facade không tự làm operation an toàn.

## 14. Read path cần chú ý hiệu năng

Một JMX client có thể poll \`PendingCount\` mỗi giây. Nếu getter tạo query database rất đắt:

\`\`\`java
@ManagedAttribute
public int getPendingCount() {
    return repository.findAll().size(); // Ví dụ không tốt.
}
\`\`\`

nó có thể làm tăng CPU, allocations, database load và latency ứng dụng.

Phương án tốt hơn:
- Duy trì counter/snapshot do hot path cập nhật.
- Dùng query COUNT được tối ưu nếu cần chính xác.
- Cache kết quả theo TTL.
- Cung cấp timestamp/age cho snapshot.
- Hạn chế polling interval.
- Tách những operation chẩn đoán đắt khỏi getter được poll thường xuyên.

Ví dụ:

\`\`\`java
private final AtomicInteger pendingSnapshot = new AtomicInteger();

@ManagedAttribute(description = "Latest pending count snapshot")
public int getPendingCount() {
    return pendingSnapshot.get();
}
\`\`\`

Counter/snapshot phải có nguồn cập nhật đúng, đặc biệt khi có nhiều producers/consumers và khi restart.

## 15. Consistency của các attributes

Giả sử MBean expose:
- PendingCount.
- ActiveCount.
- CompletedTotal.
- FailedTotal.

JMX client có thể đọc từng attribute ở những thời điểm khác nhau. Vì vậy không nên mặc định tất cả tạo thành một transactionally consistent snapshot.

Nếu cần đọc nhiều giá trị cùng một version:
- Expose một \`CompositeData\` hoặc snapshot operation.
- Thêm \`SnapshotVersion\`/\`SnapshotTime\`.
- Duy trì một immutable snapshot object và thay atomic reference khi cập nhật.
- Chỉ dùng consistency level phù hợp với mục đích vận hành.

Ví dụ:

\`\`\`java
public record WorkerSnapshot(
    int pending,
    int active,
    long completed,
    long capturedAtEpochMillis
) {}
\`\`\`

Trong JavaMXBean/ModelMBean, cần bảo đảm representation có thể chuyển qua JMX client; không mặc định một record tùy ý sẽ luôn được serialize/interoperate như mong muốn. Với client độc lập, OpenTypes hoặc các thuộc tính scalar thường dễ hơn.

## 16. Rủi ro bảo mật của quản trị qua JMX

Một MBean có thể được truy cập local hoặc qua JMX remote connector. Những vấn đề cần kiểm soát:
- Remote connector được mở trên interface nào.
- Authentication, authorization, TLS hoặc bảo vệ kênh.
- Ai có quyền read, write, invoke.
- Operations nào có tác động production.
- Dữ liệu trả về có chứa secrets.
- Có audit cho thao tác nhạy cảm không.
- Có giới hạn concurrency, timeouts và retries không.

\`@ManagedOperation(description="Admin only")\` không tự thực thi authorization.

Trong ứng dụng Spring Boot, các thuộc tính Actuator JMX exposure điều khiển **Actuator endpoints**, không phải đồng nghĩa mọi \`@ManagedResource\` của Spring Framework được bảo vệ cùng cách. Cần kiểm tra từng lớp export/security.

## 17. Kiểm tra giao diện đã công bố

Sau khi bật Spring JMX export:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Worker,name=OrderProcessor"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

var info = server.getMBeanInfo(name);

System.out.println(info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s type=%s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println("Operation=" + op.getName());
}
\`\`\`

Chỉ dùng platform server nếu exporter thực sự đăng ký vào đó. Nếu application dùng custom MBeanServer, phải lấy đúng reference.

Qua \`MBeanInfo\`, xác minh:
- Có đúng attributes được chọn không?
- Getter nào vô tình writable?
- Có operation nguy hiểm không?
- Description có giúp operator hiểu không?
- Notification metadata có đúng loại đã khai báo không?

## 18. Kiểm thử theo use case vận hành

Một bài kiểm thử tốt không chỉ assert MBean đã đăng ký. Nó đặt tình huống thực:

### Trường hợp backlog tăng

1. Tạo 100 jobs giả lập.
2. Kiểm tra \`PendingCount\` tăng theo mong đợi.
3. Bắt đầu xử lý jobs.
4. Kiểm tra \`ActiveCount\` và \`ProcessedTotal\`.
5. Kiểm tra counter reset semantics.

### Trường hợp worker dừng

1. Đưa worker về PAUSED.
2. Kiểm tra \`State\` và \`IntakePaused\`.
3. Gọi \`resumeIntake()\` từ JMX trong test.
4. Xác minh worker thực sự tiếp tục nhận việc.
5. Kiểm tra operation không chạy khi caller thiếu quyền trong cấu hình security test tương ứng.

### Trường hợp dữ liệu quá nhạy cảm

1. Tạo cấu hình chứa secret giả.
2. Query \`MBeanInfo\`.
3. Đọc các exposed attributes.
4. Assert secret không xuất hiện trong output.
5. Kiểm tra exceptions không làm lộ nội dung nhạy cảm.

### Trường hợp truy vấn quá tải

1. Poll getters ở tốc độ gần production.
2. Đo latency và resource usage.
3. Kiểm tra getter không gây query hoặc lock nặng ngoài dự kiến.
4. Điều chỉnh sampling/caching nếu cần.

Đây là những bài test thiết kế management API; chúng khác với việc unit test chính logic nghiệp vụ của worker.

## 19. Cần thông tin chính xác đến mức nào?

Không phải mọi thông tin quản trị phải tuyệt đối chính xác ở từng nanosecond. Một queue count có thể được lấy từ snapshot vài giây trước nếu operator được biết độ trễ.

Có thể phân loại:
- **Exact at read time:** cần cho thao tác kiểm soát chặt.
- **Eventually consistent:** thích hợp với xu hướng và cảnh báo.
- **Sampled:** thích hợp với metrics.
- **Snapshot with timestamp:** giúp đánh giá freshness.

Nếu ứng dụng expose một counter stale, nên có thông tin freshness hoặc mô tả rõ để tránh kết luận sai.

Ví dụ:
- \`PendingCount\`.
- \`PendingCountCapturedAt\`.
- \`PendingCountAgeSeconds\`.

Không để một giá trị cũ được hiểu như số đo realtime nếu có thể ảnh hưởng quyết định vận hành.

## 20. Khi nào dùng notification thay polling?

Polling thích hợp với:
- Counter thường xuyên thay đổi.
- Trạng thái cần cập nhật định kỳ.
- Dashboard phải đồng bộ sau reconnect.

Notification thích hợp với:
- Những chuyển trạng thái hiếm nhưng quan trọng.
- Lỗi nghiêm trọng cần báo sớm.
- Tác vụ quản trị hoàn tất.
- Configuration reload failure.

Một kết hợp phổ biến:
1. Client đăng ký notification.
2. Notification báo state changed.
3. Client đọc lại managed attributes.
4. Client refresh snapshot.
5. Khi reconnect, client đọc snapshot dù không nhận notification trong thời gian offline.

Không dùng notification như durable audit log. Nếu cần lưu mọi sự kiện, dùng event store hoặc messaging bền vững.

## 21. Quy trình thiết kế management API

Một workflow thực dụng:

1. **Liệt kê 5–10 câu hỏi vận hành:** ưu tiên những câu đang gây khó khăn.
2. **Chọn thông tin cần thiết:** không tự expose entire object graph.
3. **Phân loại read/write/operation/notification.**
4. **Định nghĩa semantics:** type, đơn vị, cập nhật, reset, freshness.
5. **Đánh giá chi phí:** tránh getter chậm.
6. **Đánh giá rủi ro:** secrets và operations nguy hiểm.
7. **Chọn ObjectName:** domain, type, name, instance.
8. **Triển khai facade:** tách khỏi business internals nếu phù hợp.
9. **Kiểm chứng runtime:** MBeanServer, MBeanInfo, operations thực tế.
10. **Kiểm thử theo kịch bản:** overload, failure, recovery, unauthorized access.
11. **Tài liệu hóa hợp đồng:** để monitoring scripts và operators dùng đúng.
12. **Review khi thay đổi:** tránh phá compatibility khi refactor.

Bất kỳ mục nào không giúp trả lời câu hỏi hoặc hỗ trợ hành động quản trị đáng giá có thể không cần expose.

## 22. Các anti-pattern

### 22.1. Expose mọi public method

Điều này tạo management surface lớn, khó review bảo mật và dễ làm client phụ thuộc implementation details.

### 22.2. Getter có side effect

Một \`getStatus()\` không nên reset counter, gọi external mutation hoặc gây task execution. Polling getter có thể lặp nhiều lần.

### 22.3. Getter quá đắt

Đọc \`getPendingCount()\` nhưng thực chất scan hàng triệu records làm performance giảm.

### 22.4. Thiếu đơn vị và điều kiện reset

\`getLatency()\` trả 500 nhưng không rõ milliseconds hay microseconds.

### 22.5. Operation đồng bộ quá dài

Remote client timeout mà không biết job đã chạy chưa; retry mù có thể khởi tạo hai jobs.

### 22.6. Dùng notification thay durable event log

Mất connection đồng nghĩa có thể bỏ lỡ sự kiện.

### 22.7. Expose secret trong attribute

JMX client có thể đọc và ghi log thông tin ngoài ý muốn.

### 22.8. ObjectName thay đổi theo class proxy

Spring AOP proxy type và refactor class làm naming contract không ổn định.

### 22.9. Không kiểm thử MBeanInfo

Annotation trên source không chứng minh thực tế exporter đã công bố đúng interface.

### 22.10. Không quản lý ownership

Nhiều Spring contexts/exporters có thể đăng ký cùng ObjectName và gây collision.

## 23. Bài tập thực hành

### Bài A — Chọn thông tin quản trị

Cho một job processing service, liệt kê:
- Ba câu hỏi về trạng thái.
- Ba metrics có ích.
- Hai operations thực sự cần.
- Một notification có giá trị.

Giải thích vì sao những method nghiệp vụ khác không nên expose.

### Bài B — Thiết kế MBean

Tạo \`QueueManagement\`:
- \`@ManagedResource\` có ObjectName rõ.
- Read-only PendingCount, ActiveCount, FailedTotal.
- Operation pauseIntake/resumeIntake.
- Description ghi rõ đơn vị và semantics.
- Không expose database entity hoặc secret.

### Bài C — Kiểm thử runtime

1. Khởi động Spring JMX exporter.
2. Lấy đúng MBeanServer.
3. \`isRegistered()\` theo ObjectName.
4. Đọc \`MBeanInfo\`.
5. Assert danh sách attributes và operations mong đợi.
6. Assert không có writable attribute ngoài danh sách.

### Bài D — Performance

1. Tạo getter thực hiện query nặng.
2. Poll getter lặp trong test load.
3. Đo latency.
4. Thay bằng snapshot/cached attribute.
5. So sánh độ trễ và freshness.

### Bài E — Security

1. Tạo operation có tác động trên state giả.
2. Chỉ expose qua management facade.
3. Validate input và condition.
4. Cấu hình quyền JMX tương ứng trong môi trường test.
5. Kiểm tra caller trái quyền không thực hiện được.
6. Ghi nhận audit cho action.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Management API tốt có nên expose tất cả Spring beans không?  
**Trả lời:** Không. Chỉ expose thông tin và operations phục vụ nhu cầu vận hành rõ ràng.

**Câu 2.** Vì sao read-only attribute thường là lựa chọn đầu tiên?  
**Trả lời:** Nó giảm rủi ro làm thay đổi trạng thái và phù hợp nhu cầu quan sát thường xuyên.

**Câu 3.** Một counter cần mô tả gì?  
**Trả lời:** Đơn vị, phạm vi, chu kỳ reset và thời điểm cập nhật nếu có.

**Câu 4.** Getter chạy query rất nặng có vấn đề gì?  
**Trả lời:** Client có thể poll liên tục, gây tải và làm chậm ứng dụng.

**Câu 5.** Operation chạy lâu nên thiết kế ra sao?  
**Trả lời:** Thường trả job ID và expose trạng thái, tránh giữ remote JMX call quá lâu.

**Câu 6.** JMX notification có bảo đảm replay sau reconnect không?  
**Trả lời:** Không có durable replay mặc định; client nên đọc lại snapshot.

**Câu 7.** \`@ManagedOperation\` có tự cấp quyền admin không?  
**Trả lời:** Không. Quyền cần thực thi tại connector/server hoặc lớp phù hợp.

**Câu 8.** Vì sao cần kiểm tra \`MBeanInfo\`?  
**Trả lời:** Để xác nhận interface thực sự được expose chứ không chỉ annotation trong source.

## 25. Ghi nhớ

- Thiết kế management API bắt đầu từ **câu hỏi vận hành**, không từ số lượng public methods.
- Chọn attributes giúp chẩn đoán trạng thái, metrics, configuration và tiến độ.
- Ưu tiên read-only, đọc nhanh, dữ liệu có semantics rõ và không chứa bí mật.
- Operations phải có mục đích, validation, concurrency và security phù hợp.
- Thao tác dài nên được tổ chức như job có trạng thái.
- Notifications báo tín hiệu quan trọng nhưng không thay durable messaging.
- ObjectName và giao diện quản trị nên ổn định cho scripts và dashboards.
- Dùng management facade để tách quản trị khỏi business internals.
- Kiểm chứng qua \`MBeanServer\`, \`MBeanInfo\` và integration tests.
- Thông tin không có ích cho quyết định vận hành hoặc tạo rủi ro không cần thiết thì không nên expose.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 API — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
