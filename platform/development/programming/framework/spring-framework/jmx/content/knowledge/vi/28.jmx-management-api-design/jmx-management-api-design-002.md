# Đặt tên attribute và operation theo ý nghĩa ổn định trong Spring Framework JMX

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Hiểu vì sao tên của JMX attribute và operation là **hợp đồng quản trị công khai** giữa ứng dụng và JMX client.
- Phân biệt Java method name, JMX attribute name, JMX operation name và MBean ObjectName.
- Đặt tên có ý nghĩa nhất quán về đại lượng, đơn vị, phạm vi, trạng thái và tác dụng.
- Duy trì tính tương thích khi refactor class, phương thức hoặc thay đổi cấu trúc ứng dụng.
- Tránh những tên nhập nhằng như \`Status\`, \`Count\`, \`Run\`, \`Reset\` khi không có ngữ cảnh.
- Thiết kế naming strategy, management facade, alias và migration policy cho thay đổi contract.
- Viết kiểm thử \`MBeanInfo\` để phát hiện tên attribute, operation hoặc signature bị thay đổi ngoài ý muốn.
- Phân biệt nguyên tắc thiết kế tên quản trị với tên biến nội bộ và với tên metric của hệ thống quan sát khác.

## 1. Vì sao tên JMX quan trọng?

Một JMX client có thể gọi:

\`\`\`java
Object count = connection.getAttribute(
    objectName,
    "PendingJobs"
);
\`\`\`

hoặc:

\`\`\`java
Object result = connection.invoke(
    objectName,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

Các chuỗi \`PendingJobs\` và \`pauseProcessing\` được client dùng như **API contract**. Chúng có thể xuất hiện trong:

- JConsole hoặc VisualVM.
- Monitoring collectors.
- Scripts vận hành.
- Automation của SRE.
- Alerts và dashboards.
- Runbooks xử lý sự cố.
- Integration tests.
- Những công cụ quản trị không nằm cùng repository với ứng dụng.

Đổi tên một method Java đã được export có thể làm những consumer này thất bại, ngay cả khi IDE đã tự cập nhật mọi chỗ gọi trong source code.

**Nguyên tắc:** Tên JMX phải phản ánh ý nghĩa quản trị ổn định, không phụ thuộc quá sát vào thuật ngữ implementation đang thay đổi.

## 2. Ba loại tên khác nhau

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueManagement {

    @ManagedAttribute
    public int getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void pauseProcessing() {
        service.pause();
    }
}
\`\`\`

Ta có:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Java class | \`QueueManagement\` | Kiểu trong source code |
| Java accessor | \`getPendingJobs()\` | Method implementation |
| JMX attribute name | \`PendingJobs\` | Chuỗi trong \`getAttribute\` |
| Java management method | \`pauseProcessing()\` | Method được annotate |
| JMX operation name | \`pauseProcessing\` | Chuỗi trong \`invoke\` |
| MBean ObjectName | \`learning.jmx:type=QueueManagement,name=Primary\` | Định danh resource trong MBeanServer |

Java class name không bắt buộc trùng ObjectName. Attribute và operation là những thành phần riêng bên trong MBean.

### Vì sao không nên chỉ dùng tên class?

Một refactor \`QueueManagement\` thành \`QueueAdministration\` không nhất thiết thay đổi điều JMX client cần quan sát. Nếu ObjectName và management contract vẫn ổn định, client không cần biết cách tổ chức code mới.

## 3. Thiết kế attribute name theo đại lượng ổn định

Attribute thường mô tả một **trạng thái hoặc đại lượng có thể quan sát**.

Ví dụ:

\`\`\`text
PendingJobs
ActiveConnections
CompletedRequests
ErrorCount
QueueCapacity
RetryDelayMillis
Paused
LastSuccessfulRefreshEpochMillis
\`\`\`

Một tên attribute tốt thường trả lời được các câu hỏi:

1. **Đại lượng gì?** Job, request, connection hay task?
2. **Trạng thái gì?** Pending, active, completed, failed?
3. **Phạm vi gì?** Queue này, pool này hay toàn ứng dụng?
4. **Đơn vị gì?** Count, bytes, milliseconds, percentage?
5. **Độ mới/nguồn giá trị?** Snapshot hay số liệu thời gian thực?
6. **Semantics có ổn định không?** Một khi công bố, tên có thể được giữ trong nhiều bản phát hành?

Tên \`Count\` trong MBean có nhiều đại lượng dễ gây hiểu nhầm. \`PendingJobs\` diễn đạt rõ hơn.

### Không lạm dụng viết tắt

So sánh:

\`\`\`text
QSz
ReqCnt
ConnAct
\`\`\`

với:

\`\`\`text
QueueDepth
RequestCount
ActiveConnections
\`\`\`

Tên rõ ràng giúp scripts, operators và người mới tiếp cận hệ thống hiểu ý nghĩa mà không cần giải mã viết tắt.

Một số viết tắt được chấp nhận rộng rãi như CPU, JVM, GC có thể giữ nguyên nếu team có naming convention thống nhất. Điều cần tránh là viết tắt mang tính nội bộ và dễ đổi.

## 4. Attribute name và quy tắc accessor

Trong Spring Framework, annotation \`@ManagedAttribute\` thường được đặt trên JavaBeans getter hoặc setter.

Ví dụ:

\`\`\`java
@ManagedAttribute
public long getCompletedRequests() {
    return completed.get();
}
\`\`\`

Attribute được công bố thường là \`CompletedRequests\`.

Với boolean:

\`\`\`java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}
\`\`\`

Attribute thường là \`Paused\`.

Một cặp getter/setter:

\`\`\`java
@ManagedAttribute
public int getMaxConnections() {
    return maxConnections;
}

@ManagedAttribute
public void setMaxConnections(int value) {
    validateLimit(value);
    maxConnections = value;
}
\`\`\`

có thể tạo một attribute \`MaxConnections\` đọc/ghi khi exporter/assembler phù hợp.

**Lưu ý:** Trong Spring \`@ManagedAttribute\` không có phần tử \`name\` dùng để đặt trực tiếp một tên JMX tùy ý. Nếu muốn giữ attribute \`CompletedRequests\`, cách rõ ràng là giữ accessor tương ứng trên management facade hoặc cấu hình metadata strategy phù hợp.

## 5. Đặt tên theo đơn vị và kiểu dữ liệu

Một API quản trị có thể bị hiểu nhầm khi cùng một attribute name nhưng giá trị dùng đơn vị khác.

Ví dụ tên không rõ:

\`\`\`text
Timeout
Latency
Size
Usage
\`\`\`

Có thể rõ hơn:

\`\`\`text
ConnectionTimeoutMillis
RequestLatencyMillis
CacheSizeBytes
CpuUsagePercent
\`\`\`

Tùy convention JMX, tên có thể dùng suffix \`Millis\`, \`Seconds\`, \`Bytes\`, \`Percent\` hoặc mô tả trong metadata. Khi cần compatibility qua nhiều client, việc đặt đơn vị trực tiếp trong tên có lợi.

### Đổi đơn vị là breaking change về semantics

Giả sử:

\`\`\`java
@ManagedAttribute
public long getConnectionTimeoutMillis() {
    return 5000L;
}
\`\`\`

Nếu đổi implementation để trả 5 giây mà vẫn giữ tên \`ConnectionTimeoutMillis\`, client nhận dữ liệu sai về ý nghĩa.

Nếu đổi từ milliseconds sang seconds, nên:

- Giữ attribute cũ trả milliseconds.
- Công bố attribute mới \`ConnectionTimeoutSeconds\` nếu thật sự cần.
- Thông báo và kiểm thử migration.
- Không âm thầm thay đổi đơn vị dưới tên cũ.

Đối với tỷ lệ, cần phân biệt 0–1 và 0–100. \`CpuUsagePercent\` nên có semantics khác với \`CpuUsageRatio\` và metadata phải phản ánh đúng.

## 6. Đặt tên theo trạng thái thực sự

Một attribute boolean nên thể hiện điều kiện có thể kiểm chứng.

Ví dụ tốt:

\`\`\`text
Paused
Healthy
AcceptingRequests
CircuitBreakerOpen
ShutdownRequested
\`\`\`

Ví dụ có thể mơ hồ:

\`\`\`text
Status
Enabled
Active
Ready
\`\`\`

\`Ready\` có thể nghĩa là service đã khởi tạo, sẵn sàng nhận request, đã load cache, hoặc kết nối tới dependencies đầy đủ. Nếu tên ngắn được dùng, cần định nghĩa semantics trong description và giữ nó ổn định.

Ví dụ:

\`\`\`java
@ManagedAttribute(
    description = "Whether this queue accepts new jobs"
)
public boolean isAcceptingJobs() {
    return state.acceptingJobs();
}
\`\`\`

Tên \`AcceptingJobs\` thường có ý nghĩa cụ thể hơn một boolean \`Active\`.

## 7. Operation name cần diễn đạt hành động

Khác với attribute là dữ liệu quan sát, operation thể hiện hành động.

Ví dụ:

\`\`\`text
pauseProcessing
resumeProcessing
clearCache
refreshConfiguration
requestIndexRebuild
resetStatistics
rotateCredentials
\`\`\`

Nên ưu tiên **động từ + đối tượng**:

- \`pauseProcessing\` thay vì \`pause\` nếu MBean có nhiều thành phần.
- \`resetStatistics\` thay vì \`reset\` nếu reset còn có thể áp dụng cho connections hoặc cache.
- \`refreshConfiguration\` thay vì \`update\` không rõ cập nhật gì.
- \`requestIndexRebuild\` nếu operation chỉ gửi yêu cầu bất đồng bộ, không chờ rebuild hoàn thành.

Tên operation phải phản ánh đúng semantics thực thi.

### Tên phải phân biệt request và completion

Giả sử operation:

\`\`\`java
@ManagedOperation
public String startRebuild() {
    executor.execute(indexService::rebuild);
    return "ACCEPTED";
}
\`\`\`

Nếu method chỉ enqueue công việc, tên \`requestRebuild\` hoặc \`startRebuild\` sẽ rõ hơn \`rebuildNow\` nếu \`rebuildNow\` khiến người dùng kỳ vọng kết quả đã hoàn tất khi lời gọi trả về.

Hợp đồng nên nói rõ:

- Kết quả là accepted/rejected hay thành công nghiệp vụ?
- Có job ID không?
- Có trạng thái tiến trình ở attribute khác không?
- Có thể gọi lại khi đang chạy không?
- Timeout client có nghĩa công việc bị hủy không?

## 8. Không đặt tên dựa vào implementation tạm thời

Ví dụ service từng dùng Redis:

\`\`\`java
@ManagedAttribute
public int getRedisQueueSize() {
    return redisQueue.size();
}
\`\`\`

Sau đó team chuyển sang một queue backend khác. JMX clients vẫn cần biết backlog, không nhất thiết cần biết công nghệ lưu trữ.

Nếu contract muốn phản ánh logical backlog, tên \`PendingJobs\` hoặc \`QueueDepth\` ổn định hơn \`RedisQueueSize\`.

Tuy nhiên, nếu attribute thực sự đo **đặc tính cụ thể của Redis** (chẳng hạn số keys hoặc trạng thái connection Redis), tên có công nghệ lại chính xác hơn. Không đổi tên cho “tổng quát” nếu làm mất ý nghĩa thật.

**Nguyên tắc:** Chọn tên theo bản chất dữ liệu hoặc thao tác mà client cần, không theo chi tiết implementation không thuộc contract.

## 9. Management facade giúp giữ naming ổn định

Một cách thiết kế phù hợp là tách management API khỏi business service.

Service:

\`\`\`java
public interface JobService {
    long pendingCount();
    boolean acceptingJobs();
    void suspendNewJobs();
}
\`\`\`

Facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=JobManagement,name=Primary",
    description = "Stable job management API"
)
public class JobManagement {

    private final JobService service;

    public JobManagement(JobService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of waiting jobs")
    public long getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedAttribute(description = "Whether new jobs are accepted")
    public boolean isAcceptingJobs() {
        return service.acceptingJobs();
    }

    @ManagedOperation(description = "Stop accepting new jobs")
    public void pauseProcessing() {
        service.suspendNewJobs();
    }
}
\`\`\`

Lợi ích:

- \`JobService.pendingCount()\` có thể đổi tên mà \`PendingJobs\` không đổi.
- Backend có thể thay mà client vẫn sử dụng logical management contract.
- Operation \`pauseProcessing\` được đặt theo hành vi quản trị.
- ObjectName cố định không phụ thuộc Spring bean name hoặc Java class name.
- Các phương thức nội bộ khác không tự bị công bố thành operations.

Spring configuration:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    JobManagement jobManagement(JobService jobService) {
        return new JobManagement(jobService);
    }
}
\`\`\`

Cấu hình này yêu cầu JobService đã được cung cấp như Spring bean và exporter có MBeanServer phù hợp. Trong ứng dụng đã có Spring Boot JMX auto-configuration, cần tránh tạo exporter trùng cho cùng resource.

## 10. Tránh tên tạo ra từ proxy runtime

Khi Spring AOP hoạt động, một Spring bean có thể là JDK dynamic proxy hoặc class-based proxy.

Không nên thiết kế ObjectName từ:

\`\`\`java
bean.getClass().getSimpleName()
\`\`\`

vì class runtime có thể là class proxy được sinh động và thay đổi theo cấu hình framework.

Hãy đặt ObjectName theo logical resource:

\`\`\`text
learning.jmx:type=JobManagement,name=Primary
\`\`\`

Attribute/operation cũng nên dựa trên management facade hoặc management interface có chủ đích, không dựa vào các methods tình cờ có trên proxy.

Nếu operation phải chạy transaction/security advice, facade nên gọi Spring-managed service proxy; đừng bỏ qua proxy chỉ để đơn giản hóa JMX metadata.

## 11. Khi rename method Java có gây breaking change?

Ví dụ ban đầu:

\`\`\`java
@ManagedAttribute
public long getQueuedTasks() {
    return service.pendingCount();
}
\`\`\`

JMX attribute: \`QueuedTasks\`.

Sau khi refactor:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return service.pendingCount();
}
\`\`\`

JMX attribute có thể thành \`PendingJobs\`, dù giá trị không đổi.

Client cũ:

\`\`\`java
connection.getAttribute(name, "QueuedTasks");
\`\`\`

có thể gặp \`AttributeNotFoundException\` sau khi deploy.

Một method rename trong repository có thể được IDE xử lý, nhưng JMX scripts và monitoring systems bên ngoài không tự đổi theo.

### Các lựa chọn chuyển đổi

**Giữ tên quản trị cũ:**

\`\`\`java
@ManagedAttribute
public long getQueuedTasks() {
    return service.pendingCount();
}
\`\`\`

Đây thường là lựa chọn tốt nhất khi semantics không đổi và client hiện hữu còn phụ thuộc.

**Công bố alias có kiểm soát:**

\`\`\`java
@ManagedAttribute
public long getQueuedTasks() {
    return service.pendingCount();
}

@ManagedAttribute
public long getPendingJobs() {
    return service.pendingCount();
}
\`\`\`

Khi exporter công bố cả hai, client cũ và mới có thể cùng hoạt động. Cần document tên canonical và kế hoạch loại bỏ alias cũ nếu có.

**Breaking change theo kế hoạch:** Nếu semantics đã thay đổi thật sự, tạo attribute mới, thông báo versioning/migration và không giả vờ tên cũ vẫn cùng nghĩa.

## 12. Operation rename cũng là breaking change

Ban đầu:

\`\`\`java
@ManagedOperation
public void clearStatistics() {
    service.resetCounters();
}
\`\`\`

Client gọi:

\`\`\`java
connection.invoke(
    name,
    "clearStatistics",
    new Object[0],
    new String[0]
);
\`\`\`

Nếu rename thành \`resetCounters()\` và chỉ công bố tên mới, client cũ có thể không còn tìm thấy operation.

Có thể giữ compatibility wrapper:

\`\`\`java
@ManagedOperation
public void clearStatistics() {
    service.resetCounters();
}
\`\`\`

và công bố một operation mới theo migration plan nếu cần.

Không nên giữ hai aliases lâu dài mà không ghi rõ semantics, security và audit; hai tên khác nhau có thể dẫn tới cùng tác dụng phụ, khiến monitoring/auditing phức tạp hơn.

## 13. Signature là một phần của operation contract

Tên operation chỉ là một phần. JMX \`invoke\` cũng dùng signature.

Ví dụ:

\`\`\`java
@ManagedOperation
public void setQueueLimit(int limit) {
    service.setLimit(limit);
}
\`\`\`

Client:

\`\`\`java
connection.invoke(
    name,
    "setQueueLimit",
    new Object[] { 200 },
    new String[] { "int" }
);
\`\`\`

Nếu đổi tham số Java từ \`int\` sang \`long\`, tên operation vẫn giữ nhưng signature thay đổi thành \`long\`.

Một số client gửi \`"int"\` theo contract cũ sẽ lỗi. Cần xem type và signature như phần không thể tách khỏi management API.

Với operations cần thay đổi kiểu tham số, cân nhắc tạo tên hoặc overload có migration rõ ràng, và test bằng \`MBeanInfo\`.

## 14. Tên setter và quyền ghi

Một attribute có thể đọc được và cũng có thể ghi qua JMX nếu exporter công bố setter.

Ví dụ:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int newValue) {
    validate(newValue);
    maxWorkers = newValue;
}
\`\`\`

Tên attribute vẫn là \`MaxWorkers\`, nhưng bây giờ contract có writable property.

Thêm setter không chỉ là cải thiện tiện ích. Nó thay đổi bề mặt quản trị và cần authorization. Nếu requirement là chỉ quan sát, nên giữ read-only.

Tránh biến các operation có tác dụng phụ thành getter. Ví dụ \`getRebuiltIndex()\` mà tự rebuild index là một anti-pattern vì monitoring có thể gọi getter nhiều lần.

## 15. Naming convention cho các nhóm thuộc tính

Một hệ thống lớn cần consistency.

Ví dụ nhóm queue:

\`\`\`text
QueueDepth
QueueCapacity
PendingJobs
ProcessedJobs
FailedJobs
AcceptingJobs
LastProcessedAtEpochMillis
\`\`\`

Nhóm connection pool:

\`\`\`text
ActiveConnections
IdleConnections
MaxConnections
ConnectionAcquireTimeoutMillis
ConnectionFailures
\`\`\`

Nhóm cache:

\`\`\`text
EntryCount
HitCount
MissCount
EvictionCount
EstimatedSizeBytes
\`\`\`

Với cùng đại lượng, team nên thống nhất một thuật ngữ. Không nên dùng \`PendingJobs\` trong MBean A nhưng \`WaitingTasks\` trong MBean B nếu cả hai có semantics giống nhau mà không có lý do.

### Không gom mọi số vào Count

\`Count\`, \`Total\` và \`Size\` không hoàn toàn đồng nghĩa:

- Count thường chỉ số lượng.
- Total có thể là số tích lũy từ một thời điểm.
- Size có thể là số phần tử hoặc số byte, tùy ngữ cảnh.
- Rate thường là số trên một đơn vị thời gian.

Tên phải diễn đạt đúng đại lượng. Ví dụ \`RequestCount\` là counter, còn \`RequestsPerSecond\` là rate.

## 16. Đặt tên cho trạng thái theo thời gian

Một attribute \`LastRefresh\` có thể mơ hồ vì nó chứa timestamp, thời gian kể từ refresh hay duration của refresh.

Tên rõ hơn:

\`\`\`text
LastRefreshEpochMillis
SecondsSinceLastRefresh
LastRefreshDurationMillis
\`\`\`

Đồng thời mô tả timezone và reference clock trong documentation.

Nếu dùng timestamp tính bằng epoch milliseconds, cần bảo đảm type đủ lớn (thường \`long\`). Nếu đo duration, đừng đặt tên giống absolute timestamp.

Khi tên không thể diễn đạt hết mọi chi tiết, dùng \`description\` cho semantics cụ thể; nhưng description không nên được dùng để che một tên quá mơ hồ.

## 17. Những điều không nên làm

| Anti-pattern | Vấn đề | Phương án |
|---|---|---|
| Attribute \`Data\` | Không rõ đại lượng | \`QueueDepth\`, \`ProcessedJobs\` |
| Operation \`doIt\` | Không rõ hành động/tác dụng | \`refreshConfiguration\` |
| \`getStatus()\` trả JSON lớn | Vừa mơ hồ vừa tốn kém | Các attributes cụ thể hoặc snapshot có giới hạn |
| \`reset()\` trên MBean nhiều thành phần | Không biết reset cái gì | \`resetStatistics\` |
| Đổi đơn vị nhưng giữ tên | Client hiểu sai dữ liệu | Tên có đơn vị hoặc migration |
| Đổi getter sau refactor | Attribute bị rename ngoài ý muốn | Giữ facade/compatibility getter |
| Dùng tên class proxy làm ObjectName | Tên không ổn định | Logical ObjectName cố định |
| Operation có tên \`rebuildNow\` nhưng chỉ enqueue | Hành vi khác kỳ vọng | \`requestRebuild\` |
| Getter gây side effects | Polling kích hoạt thao tác nguy hiểm | Chuyển thành operation |
| Rename tên cũ không thông báo | Scripts bị hỏng | Deprecation/migration policy |

## 18. Kiểm thử hợp đồng bằng MBeanInfo

JMX client nhìn thấy những gì \`MBeanServer\` công bố, không phải mọi chi tiết source code.

Ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Arrays;

import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "learning.jmx:type=JobManagement,name=Primary"
);

MBeanInfo info = server.getMBeanInfo(name);

boolean pendingJobsExists = Arrays.stream(
    info.getAttributes()
).anyMatch(a ->
    "PendingJobs".equals(a.getName())
    && "long".equals(a.getType())
    && a.isReadable()
);

boolean pauseExists = Arrays.stream(
    info.getOperations()
).anyMatch(o ->
    "pauseProcessing".equals(o.getName())
    && o.getSignature().length == 0
);

if (!pendingJobsExists || !pauseExists) {
    throw new IllegalStateException(
        "Unexpected JMX management contract"
    );
}
\`\`\`

Nếu MBeanExporter sử dụng một MBeanServer tùy biến, phải lấy server đó thay vì mặc định platform server. Trong JVM khác, client cần \`MBeanServerConnection\` qua connector.

### Vì sao MBeanInfo là nguồn đáng tin cậy?

Một getter có annotation nhưng exporter chưa bật thì chưa có JMX attribute.

Một method có tên đúng nhưng assembler không công bố thì client không gọi được.

Một AOP proxy có thể khiến metadata hoặc invocable methods khác kỳ vọng.

MBeanInfo cho phép kiểm chứng ObjectName, names, types, readable/writable semantics và operation signatures thực sự đã được export.

## 19. Versioning và deprecation policy

JMX không mặc nhiên có versioning theo HTTP REST path. Một management API vẫn cần chiến lược tương thích.

Ví dụ một tên cũ:

\`\`\`text
CompletedJobs
\`\`\`

được thay bằng:

\`\`\`text
ProcessedJobs
\`\`\`

Quy trình có thể là:

1. Ghi lại consumer đang dùng tên cũ.
2. Thêm attribute mới nếu semantics thực sự yêu cầu.
3. Trong thời gian chuyển đổi, giữ attribute cũ khi có thể.
4. Đánh dấu tên canonical trong documentation.
5. Cập nhật monitoring rules, alerts và scripts.
6. Test cả tên cũ và tên mới trong compatibility window.
7. Chỉ loại bỏ tên cũ theo một change plan được công bố.

Không nên tạo một ObjectName \`version=2\` cho mọi refactor nhỏ nếu giữ tương thích có thể giải quyết vấn đề. Nhưng nếu contract thay đổi không thể tương thích, versioned MBeans hoặc migration có chủ đích có thể hợp lý.

## 20. Phân biệt JMX naming với metric naming

Micrometer/Prometheus và JMX đều phục vụ observability nhưng có naming models khác nhau.

Ví dụ JMX:

\`\`\`text
ObjectName: learning.jmx:type=QueueMetrics,name=Primary
Attribute: PendingJobs
\`\`\`

Metric có thể có tên và tags/labels theo convention khác.

Không nhất thiết cố ép tên JMX attribute thành metric name giống hệt. Điều quan trọng là **semantics và đơn vị đo nhất quán** để hai nguồn không gây hiểu nhầm.

Nếu JMX getter và metrics gauge cùng đọc state, nên dùng một nguồn dữ liệu nghiệp vụ hoặc snapshot chung, tránh hai phép tính khác định nghĩa.

## 21. Tình huống thực tế

### Tình huống A — Team đổi "jobs" sang "tasks"

Trong code nội bộ, \`pendingJobCount()\` được đổi thành \`waitingTaskCount()\`.

Nếu JMX attribute \`PendingJobs\` đã dùng trong dashboards, vẫn có thể giữ getter \`getPendingJobs()\` trên management facade và gọi implementation mới.

Nếu khái niệm task thật sự khác job, phải thiết kế attribute mới với semantics rõ, không giả định hai tên tương đương.

### Tình huống B — Pool thay đổi đơn vị timeout

Trước đây \`ConnectionTimeout\` trả milliseconds. Sau nâng cấp thư viện, API nội bộ trả seconds.

Không được trả seconds dưới tên cũ mà không chuyển đổi. Tốt hơn dùng \`ConnectionTimeoutMillis\` và giữ giá trị đúng đơn vị, hoặc migration chính thức.

### Tình huống C — Operation chỉ enqueue tác vụ

Operation tên \`rebuildIndex()\` trước kia đồng bộ; phiên bản mới chuyển thành async.

Nên xem xét contract về completion và response. Nếu lời gọi hiện tại chỉ trả accepted, tài liệu phải làm rõ; có thể công bố \`requestIndexRebuild\` và trạng thái công việc thay vì giữ semantics sai.

### Tình huống D — JMX client tự động hóa

Một script gọi \`pauseProcessing\`. Developer đổi thành \`stopProcessing\` trong refactor.

Nếu hai hành vi tương đương, compatibility wrapper có thể bảo vệ script. Nếu stop làm dừng hẳn thay vì pause có thể resume, đây là semantic change và không nên alias vô điều kiện.

### Tình huống E — ObjectName sinh từ Spring proxy

Spring bật transaction AOP và runtime class name thay đổi. Một naming strategy dựa vào runtime class tạo ObjectName mới, khiến JMX collector không thấy tên cũ.

Giữ ObjectName logic cố định và management facade giúp không phụ thuộc proxy implementation.

## 22. Checklist trước khi công bố API quản trị

1. Attribute có tên biểu đạt đại lượng và trạng thái cụ thể không?
2. Có cần suffix đơn vị như Millis, Bytes, Percent không?
3. Kiểu dữ liệu có phù hợp với đơn vị/giá trị không?
4. Semantics có ổn định qua refactor nội bộ không?
5. Getter có read-only hoặc writable đúng yêu cầu không?
6. Getter có tránh side effects và công việc nặng không?
7. Operation name có động từ và đối tượng rõ không?
8. Operation sync/async có đúng theo tên và documentation không?
9. Signature và result semantics có được ghi rõ không?
10. ObjectName có ổn định, không phụ thuộc proxy class không?
11. Có consumer ngoài repository cần compatibility không?
12. Có integration test MBeanInfo cho contract không?
13. Có kế hoạch migration nếu đổi tên hoặc đơn vị không?
14. Có phân quyền với operations/writable attributes không?
15. Có tránh đặt secret hoặc dữ liệu nhạy cảm trong API quản trị không?

## 23. Bài tập thực hành

### Bài tập 1 — Đánh giá tên

Cho một MBean có các attributes:

\`\`\`text
Count
Status
Timeout
Data
Active
\`\`\`

Hãy đề xuất tên cụ thể hơn với ngữ cảnh connection pool. Giải thích mỗi tên biểu đạt gì và đơn vị nào.

### Bài tập 2 — Refactor an toàn

Bạn có \`getWaitingTasks()\` công bố \`WaitingTasks\`. Service đổi tên phương thức nội bộ từ \`waitingCount()\` sang \`pendingCount()\`. Viết một management facade giữ JMX attribute cũ.

### Bài tập 3 — Đặt tên operation

Đổi các tên:

\`\`\`text
run
reset
update
doAction
\`\`\`

thành những tên có mục đích cụ thể đối với cache và scheduler. Nêu khi nào một operation chỉ enqueue cần tiền tố request/start.

### Bài tập 4 — Phát hiện breaking change

Ban đầu client gọi \`setQueueLimit\` với signature \`int\`. Sau refactor operation nhận \`long\`. Hãy viết MBeanInfo test phát hiện signature đổi và nêu cách migrate.

### Bài tập 5 — Hợp đồng read/write

Ban đầu \`MaxWorkers\` chỉ đọc. Một patch thêm setter, biến nó thành writable. Hãy kiểm tra MBeanAttributeInfo.isWritable và mô tả rủi ro quản trị.

## 24. Ghi nhớ cốt lõi

- **Tên attribute và operation là public management API contract.**
- Attribute nên diễn đạt đại lượng/trạng thái; operation nên diễn đạt hành động/tác dụng.
- Đơn vị, kiểu dữ liệu, signature và ngữ nghĩa quan trọng không kém tên.
- Đừng đặt tên theo implementation dễ đổi nếu client cần logical semantics ổn định.
- Refactor Java method được export có thể phá JMX client dùng tên dạng chuỗi.
- Management facade và compatibility aliases giúp tách contract JMX khỏi service nội bộ.
- Kiểm chứng MBeanInfo sau export, không chỉ đọc annotation trong source.
- Nếu cần đổi contract, dùng migration/versioning rõ ràng thay vì rename âm thầm.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 API — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 API — MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
