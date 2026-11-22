# Xác định mục tiêu quản trị trước khi tạo MBean trong Spring Framework JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **nhu cầu quản trị thực sự** với việc đơn thuần công bố thêm phương thức Java qua JMX.
- Xác định ai sử dụng MBean, họ cần quan sát hoặc điều khiển điều gì, ở môi trường nào và để giải quyết sự cố nào.
- Phân loại yêu cầu thành **monitoring**, **diagnostics**, **configuration** và **operational control** trước khi thiết kế attributes/operations.
- Viết mục tiêu có thể kiểm chứng, chẳng hạn giảm thời gian chẩn đoán queue backlog hoặc cho phép tạm dừng consumer một cách an toàn.
- Quyết định khi nào nên dùng JMX thay vì Micrometer, Spring Boot Actuator, HTTP management API, log hoặc hệ thống job chuyên trách.
- Đánh giá phạm vi dữ liệu, tần suất đọc, latency, side effect, security, concurrency, lifecycle và khả năng tương thích.
- Chuyển mục tiêu vận hành thành **ObjectName**, attributes, operations, signatures, descriptions và acceptance tests cụ thể.
- Tránh tạo MBean quá lớn, phơi bày service methods không cần thiết hoặc biến interface quản trị thành cổng thực thi tác vụ nguy hiểm.

## 2. Tại sao cần xác định mục tiêu trước khi tạo MBean?

Trong Spring Framework, có thể công bố một bean Java dưới dạng JMX MBean bằng `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute` và `@ManagedOperation`. Nhưng khả năng kỹ thuật không đồng nghĩa mọi bean đều nên được công bố.

Ví dụ một service có các method:

```java
public class OrderService {
    public Order findById(String id);
    public List<Order> findAll();
    public void retryFailedOrders();
    public void clearAllOrders();
    public void updatePaymentToken(String token);
}
```

Nếu export toàn bộ service chỉ để giám sát số đơn chờ, hệ thống vô tình tạo bề mặt quản trị lớn, khó kiểm soát quyền và rủi ro lộ dữ liệu. Trong khi mục tiêu thực tế có thể chỉ là:

> Khi queue tồn đọng, người vận hành cần biết số item chờ, tuổi của item cũ nhất, trạng thái worker và thời điểm lỗi cuối cùng để quyết định có cần can thiệp.

Mục tiêu đó phù hợp với vài attributes nhỏ, read-only; không cần export `findAll()` hay `clearAllOrders()`.

**Nguyên tắc:** bắt đầu từ quyết định mà người vận hành cần đưa ra, rồi xác định dữ liệu/hành động tối thiểu cần thiết. Không bắt đầu từ danh sách public methods của một class.

## 3. Đặt JMX trong bức tranh vận hành

Một hệ thống Spring thường có nhiều cơ chế quan sát và quản trị:

| Nhu cầu | Cơ chế thường phù hợp | Nhận xét |
| --- | --- | --- |
| Theo dõi counter/gauge dài hạn | Micrometer + metrics backend | Có biểu đồ, alert, retention và aggregation. |
| Health/readiness | Spring Boot Actuator hoặc health system | Phù hợp với liveness, readiness và orchestration. |
| Quan sát JVM/runtime tức thời | JMX platform MBeans, JConsole | Threads, memory, GC, class loading. |
| Quan sát state nội bộ gọn | Custom JMX MBean | Hữu ích khi cần giá trị vận hành trong JVM. |
| Điều khiển cục bộ có chủ đích | JMX operation được bảo vệ | Cần authorization, validation và audit. |
| Truy vấn dữ liệu nhiều bản ghi | API có pagination và quyền truy cập | Không nên dùng getter JMX trả object graph lớn. |
| Tác vụ kéo dài, nhiều giai đoạn | Job queue/Spring Batch/scheduler | JMX chỉ có thể gửi lệnh, trả job ID và đọc trạng thái. |
| Điều tra lịch sử sự cố | Structured logs/tracing | JMX thường cho snapshot, không thay thế lịch sử sự kiện. |

Không nhất thiết một nhu cầu phải chọn đúng một công cụ. Một queue depth có thể vừa là metric, vừa là JMX attribute cho chẩn đoán trực tiếp. Tuy nhiên nên có **một nguồn dữ liệu logic** và các view phù hợp thay vì tính lại một phép truy vấn tốn kém ở mỗi kênh.

## 4. Bốn nhóm mục tiêu quản trị

### 4.1. Monitoring — quan sát định kỳ

Ví dụ:

- `QueueDepth`: số item đang chờ.
- `Running`: worker đang hoạt động.
- `ProcessedTotal`: số item đã xử lý kể từ khi khởi động.
- `LastSuccessfulRunEpochMillis`: thời điểm thành công cuối.

Đặc điểm: được đọc thường xuyên, chi phí thấp, ưu tiên read-only, semantics ổn định.

### 4.2. Diagnostics — phân tích nguyên nhân

Ví dụ:

- Lỗi gần nhất theo mã đã sanitize.
- Thời điểm retry gần nhất.
- Số lượng thread bận và queue saturation.
- Trạng thái connector hoặc dependency đã được kiểm tra nền.

Đặc điểm: cần chi tiết hơn metrics, nhưng vẫn hạn chế payload và thông tin nhạy cảm. Nếu cần trace chi tiết hoặc stack trace, nên dẫn operator tới logs/tracing thay vì xuất nguyên văn dữ liệu lớn qua MBean.

### 4.3. Configuration — điều chỉnh thông số

Ví dụ:

- Giới hạn số worker.
- Bật/tắt sampling diagnostics.
- Thay đổi một ngưỡng cảnh báo nội bộ.

Đặc điểm: writable attributes có validation, phạm vi quyền rõ, concurrency control và cơ chế phản ánh giá trị đã áp dụng.

### 4.4. Operational control — thực hiện hành động

Ví dụ:

- `requestPause()`.
- `requestResume()`.
- `requestCacheRefresh()`.
- `requestReindex()`.

Đặc điểm: có side effect, phải xác định actor, quy trình phê duyệt nếu cần, idempotency, trạng thái kết quả, audit và cách khôi phục.

Không nên gộp bốn mục tiêu vào một MBean khổng lồ chỉ vì chúng thuộc cùng service class.

## 5. Bắt đầu từ tình huống vận hành cụ thể

Xem tình huống hệ thống import file bị backlog:

```text
Triệu chứng:
  Thời gian xử lý file tăng từ 1 phút lên 12 phút.

Câu hỏi operator:
  Worker còn chạy?
  Queue còn bao nhiêu item?
  Item cũ nhất chờ bao lâu?
  Lỗi gần nhất thuộc nhóm gì?
  Có thể tạm dừng để kiểm tra downstream không?

Quyết định:
  Theo dõi thêm / tăng capacity / tạm dừng / escalation.
```

Từ đó hình thành một mục tiêu:

> Cho phép operator xác định trong khoảng thời gian ngắn liệu sự chậm trễ do queue saturation, worker dừng hay downstream failure, đồng thời chỉ cung cấp thao tác pause/resume được kiểm soát.

Mục tiêu cần liên kết tới thông tin/hành động cụ thể chứ không chỉ viết chung chung “tăng khả năng giám sát”.

## 6. Bảng câu hỏi thiết kế trước khi code

| Câu hỏi | Ví dụ trả lời | Ý nghĩa thiết kế |
| --- | --- | --- |
| Ai sử dụng? | On-call/SRE | Xác định role và công cụ. |
| Họ cần quyết định gì? | Có pause importer hay không? | Tập trung vào thông tin hành động. |
| Khi nào truy cập? | Khi backlog tăng hoặc alert | Định nghĩa tần suất đọc và SLA. |
| Độ mới dữ liệu cần bao nhiêu? | Snapshot cập nhật mỗi 5 giây | Xác định cache/sampling. |
| Dữ liệu nhạy cảm? | Mã lỗi có thể chứa request ID | Sanitize, không export payload. |
| Thao tác thay đổi gì? | Dừng nhận việc mới, không hủy job chạy | Cần mô tả semantics. |
| Ai có quyền gọi operation? | Chỉ operator được cấp quyền | Security policy và tests. |
| Có thể gọi lặp không? | `requestPause` idempotent | Thiết kế retry an toàn. |
| Nếu operation lỗi? | Trả trạng thái/exception được định nghĩa | Logging và audit. |
| Có cần nhiều instance? | Mỗi Pod tự có worker | Phân biệt local instance và cluster. |
| Nâng cấp phiên bản có ảnh hưởng? | Dashboard phụ thuộc tên attribute | Giữ contract ổn định. |

Trả lời các câu hỏi này trước khi chọn annotation hoặc assembler.

## 7. Chuyển mục tiêu thành yêu cầu có thể kiểm chứng

Một yêu cầu mơ hồ:

```text
Expose worker information through JMX.
```

Một yêu cầu tốt hơn:

```text
REQ-01: Operator đọc được QueueDepth kiểu long trong MBean của importer.
REQ-02: Running kiểu boolean, read-only.
REQ-03: OldestQueuedAgeSeconds kiểu long, không âm.
REQ-04: Các getter không gọi query toàn bộ database và đáp ứng ngân sách latency.
REQ-05: Chỉ nhóm điều khiển được gửi requestPause().
REQ-06: requestPause() không hủy task đang xử lý; trả nhanh.
REQ-07: Không có API đọc full payload hoặc xóa dữ liệu qua JMX.
REQ-08: MBean được unregister khi Spring context đóng.
```

Những tiêu chí này giúp thiết kế, test và review thống nhất. Ngưỡng latency cụ thể nên dựa trên tải môi trường và yêu cầu dự án, không đặt tùy tiện một số đẹp trên giấy.

## 8. Thiết kế ObjectName từ mục tiêu sử dụng

JMX định danh MBean bằng `ObjectName`, ví dụ:

```text
com.example.import:type=Worker,name=Primary
com.example.import:type=Queue,name=Retry
com.example.import:type=Maintenance,name=Index
```

Nên sử dụng quy ước:

- Domain theo application hoặc module.
- `type` mô tả loại resource.
- `name` mô tả instance/resource logic.
- Key properties ổn định, không mang secret hay PII.
- Tránh giá trị phụ thuộc runtime proxy class name.
- Hạn chế số ObjectName động tăng không kiểm soát.

Trong cùng một `MBeanServer`, một ObjectName chỉ đăng ký được một MBean tại một thời điểm. Trong nhiều JVM khác nhau, cùng ObjectName có thể xuất hiện mà không xung đột.

**Thiết kế cho từng instance hay toàn cluster?** Một custom MBean nằm trong JVM chỉ phản ánh trạng thái instance đó trừ khi implementation chủ động tổng hợp dữ liệu cluster. Đặt tên `GlobalStatus` không tự làm số liệu trở thành toàn cụm.

## 9. Chọn attribute hay operation?

### Ưu tiên attribute khi

- Giá trị là trạng thái/số liệu có thể đọc.
- Không cần input parameter.
- Có thể đọc nhiều lần mà không làm thay đổi trạng thái.
- Chi phí đọc nhỏ và ổn định.
- Monitoring tools cần polling.

Ví dụ:

```java
@ManagedAttribute(description = "Queued items (count)")
public long getQueueDepth() {
    return metrics.queueDepth();
}
```

### Ưu tiên operation khi

- Hành động có side effect.
- Cần tham số để kích hoạt một công việc.
- Có trạng thái yêu cầu/kết quả cần quan sát.
- Cần validation và error handling tường minh.

Ví dụ:

```java
@ManagedOperation(
    description = "Request graceful pause; does not cancel running jobs"
)
public void requestPause() {
    controlService.requestPause();
}
```

Không vì muốn lấy một số liệu đơn giản mà biến nó thành operation cần invoke, nhất là khi monitoring account chỉ có quyền readonly tại remote connector. Ngược lại, không biến một hành động thay đổi cấu hình quan trọng thành getter có side effect.

## 10. Quyết định kiểu dữ liệu và độ lớn payload

JMX thường dễ sử dụng khi trả về kiểu nhỏ, rõ:

```text
boolean  Running
long     QueueDepth
long     ProcessedTotal
double   AverageLatencyMillis
String   StatusCode
String   LastErrorType
```

Nếu cần snapshot cấu trúc, cân nhắc Open Types hoặc MXBean mapping khi tương thích client. Không mặc định domain DTO, JPA entity, `Future`, `Stream` hoặc object graph tùy ý là hợp đồng JMX tốt.

Tránh:

```java
@ManagedAttribute
public List<Order> getAllPendingOrders() {
    return repository.findAllPending();
}
```

Thay bằng:

```java
@ManagedAttribute
public long getPendingOrderCount() {
    return metrics.pendingCount();
}
```

Nếu cần danh sách chi tiết, sử dụng API chuyên biệt có pagination/authorization thay vì lấy toàn bộ qua một JMX getter. Các kiểu `CompositeData` và `TabularData` chỉ giúp mô tả cấu trúc, không tự biến payload rất lớn thành an toàn.

## 11. Định nghĩa semantics và đơn vị ngay từ đầu

Những tên thiếu thông tin sẽ gây hiểu nhầm:

```text
Latency = 250
Age = 30
Size = 1024
```

Nên đặt:

```text
AverageLatencyMillis = 250.0
OldestQueuedAgeSeconds = 30
HeapUsedBytes = 1024
```

Đối với counter, cần ghi rõ nó tính từ JVM start hay từ thời điểm reset. Đối với ratio, dùng khoảng `[0,1]` hay phần trăm `[0,100]`. Đối với timestamp, dùng UTC ISO-8601 hoặc epoch milliseconds với tên mô tả đơn vị.

Ví dụ description:

```java
@ManagedAttribute(
    description = "Age of the oldest queued item in seconds"
)
public long getOldestQueuedAgeSeconds() {
    return metrics.oldestQueuedAgeSeconds();
}
```

Description cần phục vụ người vận hành và client tự động, không chỉ là câu trang trí.

## 12. Tính thời gian thực và chi phí đọc

Mỗi lần client gọi `getAttribute`, getter của MBean thực sự được thực thi. Nếu getter query database, gọi downstream hoặc giữ lock lâu, chỉ số giám sát có thể làm giảm hiệu năng ứng dụng.

Một mục tiêu quản trị tốt xác định:

- Tần suất polling dự kiến.
- Ngân sách latency của getter.
- Có cho phép dữ liệu chậm vài giây không.
- Chỉ số được cập nhật theo event hay sampler.
- Chi phí CPU/I/O/GC.
- Hành vi khi downstream không phản hồi.

Một thiết kế an toàn thường lấy **snapshot đã được cập nhật nền**:

```java
@ManagedAttribute(description = "Cached pending count")
public long getPendingCount() {
    return snapshot.get().pendingCount();
}
```

Ví dụ `snapshot` có thể là `AtomicReference<MetricsSnapshot>` do sampler cập nhật. Cần định nghĩa độ mới dữ liệu, không che giấu việc snapshot stale bằng cách trả 0.

## 13. Quy định bề mặt bảo mật trước khi export

Spring JMX annotations như `@ManagedAttribute` hoặc `@ManagedOperation` không tự cấp role. Phải phân biệt:

```text
Export surface:
    Cái gì có mặt trong MBeanInfo?

Authorization:
    Caller nào được getAttribute/setAttribute/invoke?

Transport security:
    Ai có thể kết nối, kết nối được bảo vệ thế nào?
```

Với remote JMX, cần authentication, TLS/network restrictions và authorization phù hợp. Cơ chế access file readonly/readwrite của JDK thường mang tính coarse-grained; khi cần quyền per-ObjectName/per-operation, phải có enforcement riêng như `MBeanServerForwarder` hoặc gateway/service authorization.

**Spring Security HTTP không tự bảo vệ JMX/RMI connector.** Cũng không được coi metadata impact `INFO` là bằng chứng operation an toàn hay là rule phân quyền.

## 14. Tách read-only monitoring khỏi control

Đối với mục tiêu có cả quan sát và điều khiển, một cách tổ chức:

```text
com.example.import:type=Worker,name=PrimaryStatus
  Attributes:
    Running
    QueueDepth
    OldestQueuedAgeSeconds

com.example.import:type=Worker,name=PrimaryControl
  Operations:
    requestPause()
    requestResume()
```

Tách thành hai MBeans giúp review bề mặt quản trị dễ hơn, tạo allowlist rõ và có thể chỉ export control MBean trong môi trường được phép.

Nhưng **tách ObjectName không tự tạo phân quyền** khi connector vẫn cho một tài khoản readwrite thao tác rộng trên toàn server. Policy cần được thực thi tại lớp phù hợp.

## 15. Thiết kế operation có tác động trạng thái

Trước khi tạo operation `requestPause()`, phải trả lời:

1. Pause có nghĩa ngừng nhận job mới hay dừng cả job đang xử lý?
2. Một lời gọi lặp có an toàn (idempotent) không?
3. Trả về khi yêu cầu được nhận hay khi mọi worker đã dừng?
4. Nếu một worker không dừng, operator đọc trạng thái nào?
5. Có timeout và cách khôi phục không?
6. Ai được quyền gọi?
7. Có ghi audit không?
8. Nếu caller mất kết nối ngay sau khi gửi lệnh, có thể kiểm tra kết quả không?

Ví dụ hợp đồng:

```text
requestPause() -> boolean
    true: đã chấp nhận yêu cầu pause
    false: request bị từ chối theo trạng thái nghiệp vụ

getControlState() -> String
    RUNNING | PAUSE_REQUESTED | PAUSED | FAILED
```

Điều quan trọng là định nghĩa boolean rõ, không dùng `true` để ám chỉ đồng thời cả “yêu cầu đã nhận” và “pause hoàn tất”.

## 16. Không chạy công việc dài trên thread JMX

Operation tạo rebuild index, clear large cache, reprocess backlog hoặc export report có thể chạy hàng phút. Nếu code chạy trực tiếp:

```java
@ManagedOperation
public void rebuildIndex() {
    indexService.rebuildAll();
}
```

lời gọi `MBeanServer.invoke(...)` có thể block cho đến khi công việc hoàn tất. Với remote JMX, timeout của client không bảo đảm server đã ngừng chạy.

Một hợp đồng phù hợp hơn:

```text
requestRebuild(String requestKey) -> String requestId
getRebuildStatus(String requestId) -> String
cancelRebuild(String requestId) -> boolean
```

Service điều phối qua executor/queue có giới hạn, trả ID nhanh và ghi trạng thái `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`.

Cần idempotency hoặc deduplication để tránh retry tạo job trùng; cần bounded queue và không dùng `CallerRunsPolicy` nếu nó có thể chạy task nặng trên JMX caller thread.

## 17. Thiết kế một management adapter nhỏ

Trong ứng dụng thực tế, business service có thể có nhiều method không phù hợp để export. Nên tạo một management adapter chỉ công bố API đã chọn.

Ví dụ:

```java
package example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.import:type=Worker,name=Primary",
    description = "Primary import worker management"
)
public class ImportWorkerManagement {

    private final ImportMetricsSnapshot metrics;
    private final ImportControlService control;

    public ImportWorkerManagement(
            ImportMetricsSnapshot metrics,
            ImportControlService control) {
        this.metrics = metrics;
        this.control = control;
    }

    @ManagedAttribute(
        description = "Queued import jobs (count)"
    )
    public long getQueueDepth() {
        return metrics.queueDepth();
    }

    @ManagedAttribute(
        description = "Oldest queued job age in seconds"
    )
    public long getOldestQueuedAgeSeconds() {
        return metrics.oldestQueuedAgeSeconds();
    }

    @ManagedAttribute(
        description = "Current worker state"
    )
    public String getState() {
        return metrics.state();
    }

    @ManagedOperation(
        description = "Request graceful pause; returns accepted flag"
    )
    public boolean requestPause() {
        return control.requestPause();
    }
}
```

`ImportMetricsSnapshot` và `ImportControlService` là abstraction do ứng dụng định nghĩa. Adapter giữ surface JMX rõ và gọi service được Spring quản lý; nó không trực tiếp chứa logic persistence hoặc async phức tạp.

Trong thực tế cần authentication/authorization có tin cậy ở connector/server/service; ví dụ trên tập trung minh họa API shape.

## 18. Cấu hình MBeanExporter theo mục tiêu

Trong Spring Framework, có thể dùng `MBeanExporter` và metadata assembler để chỉ export các bean được chọn:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ManagementConfiguration {

    @Bean
    public MBeanExporter managementExporter(
            ImportWorkerManagement management) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(Map.of("importWorkerManagement", management));
        return exporter;
    }
}
```

Đây là cách export tường minh nhằm giảm nguy cơ công bố nhầm nhiều bean. Cần xác định `MBeanServer` phù hợp với context và tránh tạo exporter trùng khi Spring Boot auto-configuration hoặc `@EnableMBeanExport` đã được dùng.

**Không chọn `IGNORE_EXISTING`/`REPLACE_EXISTING` chỉ để che lỗi trùng ObjectName.** Hãy kiểm soát ownership và naming strategy.

## 19. Metadata là hợp đồng công khai

Sau export, client có thể đọc:

```java
ObjectName name = new ObjectName(
    "com.example.import:type=Worker,name=Primary"
);

MBeanInfo info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() + " : " + attribute.getType()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " : " + operation.getReturnType()
    );
}
```

Một mục tiêu quản trị được diễn đạt tốt phải tạo ra **hợp đồng runtime** phù hợp:

| Yêu cầu | Kiểm tra `MBeanInfo` |
| --- | --- |
| Có QueueDepth | Attribute `QueueDepth` kiểu `long`. |
| Chỉ cho đọc queue depth | `isReadable=true`, `isWritable=false`. |
| Có OldestQueuedAgeSeconds | Attribute kiểu `long`, description có đơn vị. |
| Có State | Attribute `State` kiểu `String`. |
| Có requestPause | Operation không tham số, trả `boolean`. |
| Không công bố method nội bộ | Negative assert absence trong operations. |

Không dựa vào thứ tự attributes/operations trong array; so sánh theo tên và signature. `MBeanInfo` phản ánh capability của MBean, không phải quyền của user hiện tại.

## 20. Bảng đánh giá thiết kế trước khi triển khai

| Tiêu chí | Câu hỏi cần đạt | Bằng chứng |
| --- | --- | --- |
| Mục tiêu | MBean hỗ trợ quyết định nào? | Use case và runbook. |
| Đối tượng | Ai sẽ đọc/gọi? | Operator persona, role. |
| Surface | Chỉ attributes/operations tối thiểu? | MBeanInfo allowlist. |
| Semantics | Tên, đơn vị, giá trị có rõ? | API contract. |
| Hiệu năng | Getter nhẹ, latency bounded? | Measurement/test. |
| Side effects | Operation có validation và idempotency? | Behavior tests. |
| Bảo mật | Identity/quyền/transport được bảo vệ? | Security integration tests. |
| Observability | Có status, error và audit? | Log/metrics/status. |
| Lifecycle | Start/close có register/unregister? | Integration test. |
| Tương thích | Client hiện tại có bị phá? | Contract regression test. |
| Cluster | Số liệu instance hay toàn cụm? | Scope description. |
| Bảo trì | Ai sở hữu tên và tài liệu? | Owner/runbook. |

Bảng này là công cụ thiết kế, không phải một cơ chế chấm điểm tự động. Mục đích là khiến các rủi ro được thảo luận trước khi API được công bố.

## 21. Các phản ví dụ thường gặp

### 21.1. Export mọi public method

```java
public class AccountService {
    public Account findById(String id);
    public void resetPassword(String id);
    public void deleteAllAccounts();
}
```

**Vấn đề:** Bề mặt quản trị quá rộng, operation nguy hiểm, dễ lộ dữ liệu. **Giải pháp:** Management adapter allowlist rất nhỏ.

### 21.2. Getter chạy database scan

```java
@ManagedAttribute
public long getQueueDepth() {
    return repository.findAll().stream().count();
}
```

**Vấn đề:** Monitoring làm tăng tải. **Giải pháp:** Counter/snapshot đã được cập nhật hoặc count query tối ưu với refresh rate rõ.

### 21.3. Operation chạy hàng phút

```java
@ManagedOperation
public void rebuildAll() {
    indexingService.rebuildAll();
}
```

**Vấn đề:** Block JMX caller, khó retry. **Giải pháp:** Request ID + async job status, bounded queue.

### 21.4. Mục tiêu không có đơn vị

```text
Latency=240
Uptime=9000
```

**Vấn đề:** Client không biết milliseconds/seconds. **Giải pháp:** `LatencyMillis`, `UptimeSeconds`, mô tả rõ cách đo.

### 21.5. Dùng profile như security boundary duy nhất

```java
@Profile("!prod")
@ManagedResource
```

**Vấn đề:** Profile chưa được đặt đúng hoặc exporter khác vẫn công bố bean; remote connector có thể không bảo vệ. **Giải pháp:** Điều kiện cấu hình rõ, bảo vệ connector/service, test exposure runtime.

## 22. Khi nào không nên tạo MBean?

Không phải yêu cầu quản trị nào cũng nên giải bằng JMX. Tránh tạo MBean mới nếu:

- Chỉ cần biểu đồ/alert tổng hợp nhiều instance, đã có metrics backend.
- Chỉ cần HTTP health endpoint phục vụ orchestrator.
- Dữ liệu quá lớn và cần pagination, search hoặc filtering.
- Chức năng dành cho người dùng cuối, không phải operator.
- Hành động cần workflow phê duyệt, hàng đợi bền vững hoặc audit nghiệp vụ phức tạp.
- Team chưa có cách bảo vệ quyền JMX mà operation rất nhạy cảm.
- MBean chỉ sao chép một method nội bộ mà không có use case vận hành cụ thể.

JMX có thể vẫn đóng vai trò **thin control surface** gửi request tới hệ thống chuyên trách; không phải nơi chứa mọi logic quản trị.

## 23. Kiểm thử theo mục tiêu thay vì chỉ theo annotation

Những test nên xuất phát từ yêu cầu ở phần 7:

### 23.1. Registration

```java
assertTrue(server.isRegistered(name));
```

Nhưng test này chỉ chứng minh ObjectName tồn tại, không chứng minh đúng metadata hoặc đúng bean owner.

### 23.2. Attribute contract

```java
var depth = Arrays.stream(server.getMBeanInfo(name).getAttributes())
    .filter(a -> "QueueDepth".equals(a.getName()))
    .findFirst()
    .orElseThrow();

assertEquals("long", depth.getType());
assertTrue(depth.isReadable());
assertFalse(depth.isWritable());
```

### 23.3. Operation contract

```java
var pause = Arrays.stream(server.getMBeanInfo(name).getOperations())
    .filter(op -> "requestPause".equals(op.getName()))
    .findFirst()
    .orElseThrow();

assertEquals(0, pause.getSignature().length);
assertEquals("boolean", pause.getReturnType());
```

### 23.4. Negative surface test

```java
boolean dangerous = Arrays.stream(
    server.getMBeanInfo(name).getOperations()
).anyMatch(op -> "deleteAllAccounts".equals(op.getName()));

assertFalse(dangerous);
```

### 23.5. Security integration

Nếu có remote JMX, dùng connector với credential readonly và role điều khiển, kiểm thử denial thực tế và assert không xảy ra side effect. Một local `MBeanServer.invoke` không đi qua remote connector authentication và không chứng minh authorization policy.

### 23.6. Lifecycle

Đóng `ApplicationContext` trong test cô lập và xác minh MBean do exporter quản lý không còn ở registry. Tránh tranh ObjectName khi test chạy song song.

## 24. Tài liệu runbook cho người vận hành

MBean cần được sử dụng đúng sau khi đã triển khai. Một runbook ngắn nên ghi:

```text
ObjectName:
  com.example.import:type=Worker,name=Primary

Purpose:
  Diagnose queue backlog and request graceful pause.

Read attributes:
  QueueDepth, OldestQueuedAgeSeconds, State

Control operation:
  requestPause()

Authorization:
  Read-only operator vs control operator (enforced externally).

Side effects:
  Stops taking new jobs; current jobs may finish.

Verification:
  State -> PAUSE_REQUESTED -> PAUSED

Recovery:
  requestResume() only if permitted and implemented.

Escalation:
  On-call service owner.
```

Không nên hứa `requestResume()` tồn tại nếu nó chưa được triển khai; runbook cần phản ánh đúng `MBeanInfo` và behavior của phiên bản đang chạy.

## 25. Bài tập thực hành

### Bài tập 1 — Từ triệu chứng đến mục tiêu

Một API xử lý message bị chậm. Viết ba câu hỏi mà operator cần trả lời và chuyển chúng thành tối đa năm attributes nhỏ, read-only.

**Mục tiêu:** thiết kế từ nhu cầu, không từ source method list.

### Bài tập 2 — Chọn công cụ

Phân loại các yêu cầu: alert CPU 14 ngày, xem trạng thái worker tức thời, tải 100.000 orders, pause consumer, readiness probe. Chọn JMX, metrics, HTTP API hoặc job system phù hợp và giải thích.

**Mục tiêu:** không lạm dụng JMX.

### Bài tập 3 — Thiết kế ObjectName

Đặt ObjectName cho ba worker khác nhau trong cùng JVM. Chứng minh tên không trùng và không chứa PII.

**Mục tiêu:** namespace ổn định và rõ ownership.

### Bài tập 4 — Giảm surface

Cho một service có 20 public methods, trong đó có xóa dữ liệu và đổi credentials. Thiết kế management adapter chỉ có ba attributes và một operation an toàn.

**Mục tiêu:** dùng allowlist.

### Bài tập 5 — Viết acceptance tests

Viết kiểm tra `MBeanInfo` cho tên, kiểu, read/write flags, signature và operation bị cấm.

**Mục tiêu:** hợp đồng được bảo vệ bằng test.

### Bài tập 6 — Operation dài

Chuyển `rebuildIndex()` đồng bộ sang `requestRebuild(requestKey)`, `getRebuildStatus(id)` và định nghĩa retry/idempotency.

**Mục tiêu:** tách accepted và completed.

### Bài tập 7 — Đánh giá security

Liệt kê quyền viewer/operator, chỉ ra lớp nào enforce quyền, mô tả cách test remote readonly không gọi được operation điều khiển.

**Mục tiêu:** không nhầm metadata với authorization.

## 26. Câu hỏi ôn tập

**1. Bước đầu tiên trước khi tạo MBean là gì?** Xác định nhu cầu, actor, quyết định vận hành và tiêu chí thành công.

**2. Vì sao không export toàn bộ business service?** Dễ lộ dữ liệu, operation nguy hiểm, contract khó ổn định.

**3. Attribute phù hợp với trường hợp nào?** Trạng thái/số liệu đọc nhẹ, không cần tham số và ít side effect.

**4. Khi nào cần operation?** Khi có hành động hoặc truy vấn tham số hóa được kiểm soát.

**5. `MBeanInfo` giúp đánh giá điều gì?** Hợp đồng runtime: attributes, operations, types, signatures, descriptions.

**6. `isWritable=true` có chứng minh caller được ghi không?** Không, đó là metadata capability chứ không phải quyền user.

**7. Vì sao getter phải nhẹ?** Vì monitoring client có thể polling thường xuyên.

**8. Vì sao một operation dài nên trả job ID?** Để JMX caller không chờ lâu, đồng thời theo dõi trạng thái và retry an toàn.

**9. Một ObjectName giống nhau ở hai JVM có xung đột không?** Không nếu registry/MBeanServer tách biệt.

**10. Khi nào không nên dùng JMX?** Khi nhu cầu thực chất là data query lớn, metrics retention, workflow dài hoặc public user API.

## 27. Tổng kết

**Xác định mục tiêu quản trị trước khi tạo MBean** là bước quan trọng nhất để JMX API hữu ích và an toàn. Bắt đầu từ tình huống vận hành, câu hỏi cần trả lời và quyết định của operator; sau đó xác định dữ liệu/hành động tối thiểu, tên, kiểu, đơn vị, tần suất, quyền và side effect.

Trong Spring Framework, `MBeanExporter` và annotations giúp công bố bean, nhưng chúng không thay thế việc thiết kế hợp đồng, phân quyền hoặc kiểm thử. Một MBean tốt có API nhỏ, rõ, ổn định, getter nhẹ, operation có kiểm soát và `MBeanInfo` khớp mục tiêu. Khi nhu cầu là metrics dài hạn, dữ liệu lớn hoặc workflow phức tạp, chọn công cụ phù hợp thay vì cố dồn mọi thứ vào JMX.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `ManagedResource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — `ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Java SE 21 — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html