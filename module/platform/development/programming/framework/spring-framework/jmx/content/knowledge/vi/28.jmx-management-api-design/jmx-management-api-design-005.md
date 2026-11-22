# Trả về kiểu dữ liệu nhỏ, rõ và dễ quan sát trong Spring Framework JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao API quản trị JMX nên ưu tiên dữ liệu **nhỏ, có ý nghĩa rõ, chi phí đọc thấp và ổn định**.
- Phân biệt một **attribute phục vụ giám sát** với một **operation thực hiện truy vấn hoặc điều khiển**.
- Chọn các kiểu dữ liệu JMX đơn giản như `boolean`, `int`, `long`, `double`, `String` và các loại Open MBean phù hợp khi cần dữ liệu có cấu trúc.
- Biết khi nào dùng `CompositeData`, `TabularData` hoặc MXBean mapping thay vì trả trực tiếp object nghiệp vụ tùy ý.
- Tránh trả về collection khổng lồ, entity JPA, object graph sâu, dữ liệu nhạy cảm hoặc các kiểu khó serialize/khó hiểu đối với JMX client.
- Thiết kế API tách `summary`, `count`, `status`, `jobId` khỏi phần dữ liệu chi tiết lớn.
- Kiểm thử `MBeanInfo`, OpenType, kiểu dữ liệu trả về, tính read-only và hành vi khi dữ liệu rỗng hoặc thay đổi.
- Cân nhắc polling, latency, memory allocation, cardinality, versioning và phân quyền trong ứng dụng Spring Boot hoặc Spring Framework.

## 2. Tại sao dữ liệu trả về quyết định chất lượng management API?

JMX (Java Management Extensions) là giao diện để quan sát và điều khiển JVM/ứng dụng. Người vận hành có thể dùng JConsole, VisualVM, Jolokia, JMX exporter hoặc Java client để xem attributes và gọi operations. Những công cụ này không phải lúc nào cũng có classpath và cách hiển thị object giống code nghiệp vụ của ứng dụng.

Một API trả về đối tượng phức tạp, nhiều tầng hoặc hàng nghìn bản ghi gây một số vấn đề:

1. **Khó hiển thị:** JConsole có thể không biết cách trình bày domain object.
2. **Khó dùng từ xa:** object có thể không serializable hoặc client không có class tương ứng.
3. **Tốn tài nguyên:** getter phải truy vấn dữ liệu lớn, copy collection hoặc serialize object.
4. **Khó polling:** monitoring collector đọc liên tục làm tải tăng.
5. **Khó đặt alert:** số liệu không có tên, đơn vị hoặc trạng thái nhất quán.
6. **Dễ lộ thông tin:** object graph có thể chứa token, thông tin khách hàng, địa chỉ nội bộ.
7. **Dễ phá vỡ tương thích:** thay đổi model nghiệp vụ kéo theo thay đổi hợp đồng JMX.

Nguyên tắc thiết kế:

> **Một management API tốt không chỉ trả về được dữ liệu; nó trả về đúng lượng dữ liệu đủ cho quyết định vận hành.**

Ví dụ, thay vì trả `List<Order>` gồm 50.000 entity, nên trả `PendingOrderCount=154`, `OldestPendingAgeSeconds=27` và `ProcessingState="RUNNING"`.

## 3. Mô hình dữ liệu JMX cần nhớ

JMX hỗ trợ nhiều dạng MBean:

| Loại | Ý nghĩa | Hướng thiết kế kiểu trả về |
| --- | --- | --- |
| Standard MBean | Dựa trên management interface theo quy ước. | Ưu tiên primitive, wrapper, String và kiểu đơn giản, kiểm tra tương thích client. |
| MXBean | Mapping Java types sang Open Types tiêu chuẩn. | Hữu ích với dữ liệu có cấu trúc cần khả năng tương tác JMX tốt hơn. |
| DynamicMBean | Tự định nghĩa metadata và xử lý get/set/invoke. | Phải nhất quán kiểu trả về với MBeanInfo. |
| Model MBean | Metadata/descriptor linh hoạt, Spring thường dùng adapter tương ứng. | Giới hạn surface và kiểm tra metadata runtime. |

JMX standard management API có thể trả về một số Java objects khi phù hợp, nhưng **khả năng client đọc thuận tiện và khả năng serialize từ xa** còn phụ thuộc loại MBean, connector và kiểu. MXBean/Open MBean dùng Open Types giúp giảm phụ thuộc vào class tùy chỉnh.

### 3.1. Những kiểu đơn giản

Thường dễ dùng:

```text
boolean    - running / healthy / enabled
int        - worker count / max concurrency
long       - processed count / queue depth
double     - utilization / latency ratio
String     - status / version / job ID
String[]   - danh sách nhỏ có giới hạn
Date       - thời điểm trong các trường hợp hỗ trợ
```

Tùy implementation, số lớn và thời gian cũng có thể cần semantics rõ hơn: dùng milliseconds/seconds, UTC/ISO-8601 và đơn vị được mô tả. Không chọn một kiểu chỉ vì nó dễ truyền nếu người vận hành sẽ hiểu sai ý nghĩa.

## 4. Thiết kế attribute để giám sát

Ví dụ MBean mô tả worker:

```text
com.example.jobs:type=Worker,name=Importer

Running                     boolean
QueueDepth                  long
ProcessedItemsTotal         long
LastSuccessfulRunTime       String
AverageProcessingMillis     double
```

Mỗi attribute nên trả lời một câu hỏi rõ:

- `Running`: worker còn chạy không?
- `QueueDepth`: bao nhiêu công việc đang chờ tại thời điểm đọc?
- `ProcessedItemsTotal`: tổng số item đã xử lý kể từ thời điểm nào?
- `LastSuccessfulRunTime`: thời điểm thành công cuối theo múi giờ/định dạng nào?
- `AverageProcessingMillis`: trung bình trên cửa sổ hay toàn vòng đời?

Chỉ một con số `42` không đủ để dùng tốt nếu thiếu tên và đơn vị. Với counter, cần nêu rõ có reset khi restart không. Với gauge, cần nêu cách tính và độ trễ cập nhật.

### 4.1. Ví dụ Spring @ManagedResource

```java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Importer",
    description = "Importer status and counters"
)
public class ImporterStatusManagement {

    private final ImporterMetrics metrics;

    public ImporterStatusManagement(ImporterMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Whether importer is running")
    public boolean isRunning() {
        return metrics.isRunning();
    }

    @ManagedAttribute(description = "Queued items (count)")
    public long getQueueDepth() {
        return metrics.getQueueDepth();
    }

    @ManagedAttribute(description = "Items processed since JVM start")
    public long getProcessedItemsTotal() {
        return metrics.getProcessedItemsTotal();
    }

    @ManagedAttribute(description = "Last success timestamp in ISO-8601 UTC")
    public String getLastSuccessfulRunTime() {
        return metrics.getLastSuccessfulRunTime();
    }
}
```

`ImporterMetrics` là interface/service nội bộ do ứng dụng định nghĩa để đọc snapshot các chỉ số. Adapter không cần công bố object metrics hoặc entity nghiệp vụ dưới dạng giá trị JMX.

## 5. Getter JMX phải nhẹ và ít side effect

JMX attribute getter không chỉ là metadata. Mỗi khi client gọi `getAttribute`, code getter thực sự được thực thi.

Thiết kế tốt:

```java
@ManagedAttribute
public long getQueueDepth() {
    return queueDepthGauge.get();
}
```

Antipattern:

```java
@ManagedAttribute
public long getQueueDepth() {
    return repository.findAllPendingOrders().stream().count();
}
```

Ví dụ thứ hai có thể đọc toàn bộ entity từ database rồi đếm trong JVM; nếu monitoring polling mỗi giây, đây là một nguồn tải lớn. Khi cần query database, nên dùng phép đếm có index phù hợp, snapshot được cập nhật theo lịch hoặc một metric gauge đã được quản lý.

Cũng tránh getter:

- Gọi HTTP API downstream trên mỗi lần đọc.
- Tạo file hoặc reset counter.
- Thực hiện transaction ghi.
- Giữ lock lâu.
- Parse hàng megabyte JSON.
- Đợi `Future.get()` không giới hạn.
- Trả collection mutable có thể bị thay đổi đồng thời trong lúc serialize.

**Một getter read-only trên JMX không tự bảo đảm execution là vô hại.** Implementation có thể có side effect hoặc sử dụng nhiều tài nguyên; cần kiểm thử latency và tải.

## 6. Số lượng dữ liệu quan trọng hơn kích thước một phần tử

Một `String[]` có vẻ đơn giản, nhưng nếu chứa hàng trăm nghìn phần tử thì không còn là dữ liệu nhỏ.

Ví dụ không nên dùng:

```java
@ManagedAttribute
public String[] getAllActiveSessionIds() {
    return sessionRepository.findAllSessionIds();
}
```

Vấn đề:

- Payload lớn và tốn bandwidth khi remote JMX.
- Tạo nhiều object/GC pressure.
- Có thể lộ identifiers nhạy cảm.
- Phát sinh snapshot không nhất quán khi tập dữ liệu thay đổi.
- Monitoring tool khó chuyển thành metric hữu ích.

Thiết kế khác:

```java
@ManagedAttribute
public long getActiveSessionCount() {
    return sessionMetrics.activeCount();
}

@ManagedAttribute
public long getOldestSessionAgeSeconds() {
    return sessionMetrics.oldestAgeSeconds();
}
```

Nếu thật sự cần danh sách chi tiết, dùng một API quản trị có phân trang/giới hạn và authorization phù hợp, không biến JMX attribute thành endpoint xuất dữ liệu vô hạn.

## 7. Operation trả về gì?

Operation JMX nên trả kết quả có semantics dễ hiểu. Ví dụ:

```text
requestRefresh() -> String requestId
getRefreshStatus(String requestId) -> String
getLastValidationError() -> String
resetDiagnosticCounters() -> boolean
```

- `requestId` xác nhận đã nhận một yêu cầu.
- `status` cho biết tiến độ/terminal state.
- `boolean` chỉ phù hợp khi định nghĩa true/false rõ ràng.
- Exception phản ánh việc từ chối hoặc lỗi, không nên trộn với dữ liệu hợp lệ.

Đối với tác vụ dài, không trả domain object hoặc `Future` trực tiếp chỉ để mong JMX client đợi. Dùng request ID + trạng thái nhỏ sẽ dễ dùng hơn.

### 7.1. Ví dụ operation bất đồng bộ

```java
@ManagedOperation(
    description = "Submit refresh and return request ID"
)
public String requestRefresh() {
    return refreshCoordinator.submit();
}

@ManagedOperation(
    description = "Return QUEUED, RUNNING, SUCCEEDED or FAILED"
)
public String getRefreshStatus(String requestId) {
    return refreshCoordinator.status(requestId);
}
```

`refreshCoordinator` là service do ứng dụng xây dựng. Nó cần xử lý job lifecycle, idempotency, retention, concurrency, exception và authentication/authorization nếu operation có side effect.

**Không coi request ID là bằng chứng công việc đã thành công.** Nó chỉ cho phép theo dõi.

## 8. Dữ liệu có cấu trúc: khi nào cần CompositeData?

Nếu cần trả một nhóm trường có liên hệ chặt chẽ, một loạt attributes riêng có thể thiếu tính nhất quán snapshot. Ví dụ:

```text
ImportStatus:
  state             RUNNING
  queueDepth        23
  processedTotal    100532
  lastSuccessEpoch  1730000000000
```

JMX Open MBean có `CompositeData` để đại diện dữ liệu có cấu trúc với tập trường và kiểu được mô tả bằng `CompositeType`/`OpenType`.

Ví dụ đơn giản:

```java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public CompositeData getStatusSnapshot() throws Exception {
    String[] keys = { "state", "queueDepth" };
    String[] descriptions = {
        "Current state", "Queued item count"
    };
    OpenType<?>[] types = {
        SimpleType.STRING, SimpleType.LONG
    };

    CompositeType type = new CompositeType(
        "ImportStatus",
        "Importer status snapshot",
        keys, descriptions, types
    );

    return new CompositeDataSupport(
        type,
        keys,
        new Object[] { "RUNNING", 23L }
    );
}
```

Đây là ví dụ JMX OpenData thuần Java. Khi export qua Spring, cần chọn kiểu MBean/assembler cho phép metadata kiểu trả về tương thích; không mặc định mọi phương thức POJO bất kỳ được Spring tự động chuyển sang Open MBean.

### 8.1. Lợi ích

- Các field được đặt tên rõ, có OpenType.
- Client không nhất thiết cần class domain riêng của ứng dụng.
- Có thể truyền snapshot nhỏ có nhiều chỉ số liên quan.
- Dễ hiển thị hơn `Map<String,Object>` tùy ý khi công cụ hỗ trợ OpenData.

### 8.2. Giới hạn

- Schema cần được duy trì ổn định.
- Dữ liệu quá lớn vẫn không phù hợp dù là CompositeData.
- Trường hợp sâu/nhiều tầng có thể khó sử dụng trên JConsole.
- Thay đổi field/type có thể phá vỡ client.
- Không dùng để xuất dữ liệu nhạy cảm không có phân quyền.

## 9. TabularData: chỉ dùng cho bảng nhỏ có giới hạn

`TabularData` biểu diễn bảng có schema dùng `TabularType` và mỗi row là `CompositeData`. Nó có thể phù hợp với một bảng nhỏ như:

```text
Top 5 queues:
  QueueName       Depth
  payments        4
  emails          8
  invoices       11
  retries        17
  notifications  23
```

Nhưng trả hàng triệu bản ghi dưới dạng `TabularData` không phải một API quản trị tốt. Khi cần bảng lớn, dùng hệ thống truy vấn/endpoint chuyên trách với pagination/filter/auth, thay vì biến JMX thành một hệ truy vấn dữ liệu.

Một API JMX có thể chỉ expose:

```text
getTopQueues(int maxRows) -> TabularData
```

và validate `maxRows` ở phạm vi nhỏ đã định nghĩa. Đặt ngưỡng an toàn, không cho client truyền `Integer.MAX_VALUE` rồi buộc server xuất mọi record.

## 10. MXBean và Open Type mapping

MXBean tự động mapping một số Java types sang các Open Types của JMX, hỗ trợ khả năng tương tác giữa JVM/JMX client.

Ví dụ:

```java
public interface ImportMonitorMXBean {
    long getQueueDepth();
    String getState();
}

public final class ImportMonitor
        implements ImportMonitorMXBean {
    public long getQueueDepth() { return 7L; }
    public String getState() { return "RUNNING"; }
}
```

Đối với kiểu phức tạp, MXBean mapping có quy tắc riêng. Không nên giả định mọi Java class đều tự động mapping thành một OpenType hợp lệ. Khi thiết kế dữ liệu cấu trúc, cần xác nhận kiểu được JDK hỗ trợ hoặc dùng DTO tương thích và kiểm tra `MBeanInfo`/`OpenType` runtime.

### 10.1. Standard MBean, MXBean và Spring Model MBean

Ba cơ chế có thể cho trải nghiệm client khác nhau với một kiểu Java:

- Standard MBean có thể expose Java types theo contract interface.
- MXBean có Open Type mapping đặc thù.
- Spring metadata-based exporter tạo metadata từ annotation/assembler và adapter.

Chọn cơ chế dựa trên nhu cầu client, không chỉ vì một annotation thuận tiện.

## 11. Enum, status và versioning

Trả `enum` trực tiếp từ một Standard MBean có thể làm remote client phụ thuộc class của ứng dụng; trong nhiều trường hợp `String` ổn định sẽ dễ tiêu thụ hơn.

Ví dụ:

```java
@ManagedAttribute
public String getProcessingState() {
    return state.name();
}
```

Định nghĩa tập giá trị:

```text
IDLE
RUNNING
PAUSED
FAILED
```

Nếu sau này thêm `DRAINING`, client cần có cách xử lý giá trị chưa biết thay vì crash. Tránh trả chuỗi thông điệp tự do làm status chính nếu nó sẽ được parse bởi monitoring tool.

**Status code** và **human-readable message** nên là hai field riêng khi cần:

```text
StatusCode = FAILED
StatusMessage = Unable to reach downstream service
```

Message có thể thay đổi theo nội dung/language, nên không dùng làm khóa logic hoặc metric label.

## 12. Đơn vị đo phải minh bạch

Ví dụ một attribute `AverageLatency=250` không cho biết là milliseconds, seconds hay microseconds.

Đặt tên rõ:

```text
AverageLatencyMillis = 250.0
UptimeSeconds        = 3600
HeapUsedBytes        = 128000000
CpuUtilizationRatio  = 0.75
```

Đồng thời ghi description:

```java
@ManagedAttribute(
    description = "Average processing latency in milliseconds"
)
public double getAverageLatencyMillis() {
    return metrics.getAverageLatencyMillis();
}
```

Với thời gian tuyệt đối, nên dùng định dạng rõ như ISO-8601 UTC hoặc epoch milliseconds có tên thể hiện đơn vị. Không dùng `LocalDateTime.toString()` mà không nêu timezone khi dữ liệu được quan sát qua nhiều host.

## 13. Số liệu snapshot và sự nhất quán

Giả sử client đọc lần lượt:

```text
ProcessedTotal = 120
FailedTotal    = 5
SuccessTotal   = 116
```

Ba giá trị có thể được đọc ở ba thời điểm khác nhau, nên tổng không còn nhất quán. Không nhất thiết đó là lỗi đồng bộ hay dữ liệu hỏng.

Khi cần snapshot nhất quán, có thể:

- Lấy một immutable snapshot trong code rồi trả nhiều field.
- Dùng `CompositeData` cho một nhóm nhỏ trường.
- Có timestamp/version của snapshot.
- Dùng locking/copy thích hợp với mức tải.
- Giới hạn chi phí snapshot để không block getter.

Ví dụ:

```java
public record QueueSnapshot(
    long processed,
    long failed,
    long success,
    long capturedEpochMillis
) {}
```

Record này là domain DTO của ứng dụng. Nếu đưa qua JMX, cần mapping phù hợp (ví dụ MXBean/open data hoặc chuyển thành các trường đơn giản); không giả định Java record được mọi JMX client diễn giải tự động.

## 14. Tránh dữ liệu bí mật và PII

Management API có thể được đọc bởi công cụ monitoring, operator hoặc remote connector. Không expose:

- Password, OAuth token, API key, private key.
- Full connection strings chứa credentials.
- Dữ liệu cá nhân/khách hàng khi không thực sự cần.
- Session identifiers hoặc request bodies.
- Stack traces chưa sanitize có thể chứa dữ liệu nhạy cảm.
- File paths hoặc topology nội bộ không cần thiết.

Thay vì:

```java
@ManagedAttribute
public String getDatabaseConnectionString() {
    return datasource.getUrl(); // Có thể lộ internal topology.
}
```

nên cung cấp chỉ số tổng hợp:

```java
@ManagedAttribute
public boolean isDatabaseHealthy() {
    return databaseHealthSnapshot.isHealthy();
}
```

Getter vẫn cần chi phí thấp: tránh chạy kiểm tra kết nối đồng bộ tốn thời gian mỗi lần JMX polling; có thể dùng trạng thái health đã được cập nhật theo chu kỳ.

## 15. Khả năng tương thích của MBeanInfo

Một JMX client có thể tự động khám phá attributes/operations qua:

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
```

Đối với API ổn định, test nên bảo vệ:

1. ObjectName đúng.
2. Attribute names và types.
3. Read/write flags đúng.
4. Operation name, signature, return type.
5. Description và units cần thiết.
6. Không có method nhạy cảm bị export.

Một thay đổi `long` → `String` có thể làm client không đọc được giá trị như trước. Đổi tên attribute cũng có thể phá monitoring rules.

## 16. Ví dụ kiểm thử attribute nhỏ, rõ

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;

MBeanAttributeInfo depth = Arrays.stream(info.getAttributes())
    .filter(a -> "QueueDepth".equals(a.getName()))
    .findFirst()
    .orElseThrow(() ->
        new AssertionError("Missing QueueDepth"));

if (!"long".equals(depth.getType())
        || !depth.isReadable()
        || depth.isWritable()) {
    throw new AssertionError("QueueDepth contract mismatch");
}
```

Với return value, đọc giá trị trong test lab để xác nhận kiểu:

```java
Object value = server.getAttribute(name, "QueueDepth");
if (!(value instanceof Long)) {
    throw new AssertionError("Expected long attribute value");
}
```

Cần nhớ Java reflection/JMX có thể boxing primitive `long` thành `Long` ở kết quả, trong khi MBeanInfo type dùng tên `long`.

## 17. Kiểm thử payload size và latency

Đối với getter phục vụ polling, nên có test hiệu năng ở mức phù hợp:

- Mỗi lần đọc không thực hiện full table scan.
- Thời gian đọc đủ ngắn với tần suất polling.
- Collection/array có upper bound.
- Memory allocations không tăng mạnh theo số bản ghi nghiệp vụ.
- Giá trị null/unknown được xử lý ổn định.
- Lỗi downstream không làm MBeanServer thread block vô hạn.

Ví dụ nếu bắt buộc trả danh sách:

```java
@ManagedOperation(
    description = "Return at most 10 recent error codes"
)
public String[] getRecentErrorCodes() {
    return errorRegistry.latestCodes(10)
        .toArray(String[]::new);
}
```

Contract nên giới hạn 10 phần tử và mỗi phần tử cũng có kích thước có giới hạn. `latestCodes(10)` phải là API service được thiết kế không sao chép cả một tập dữ liệu khổng lồ.

### 17.1. Vì sao một getter nhanh trong dev vẫn có thể chậm ở prod?

Ở dev chỉ có vài entity, còn production có hàng triệu. Vì vậy cần test với tải/dữ liệu đại diện, giám sát thời gian thật và tránh thuật toán tuyến tính theo tập dữ liệu khi getter được polling thường xuyên.

## 18. Khi nào chọn metrics thay vì JMX detail

JMX phù hợp cho quản trị/quan sát trực tiếp, nhưng không phải time-series database. Với dashboard và alerting dài hạn:

| Nhu cầu | Cách tiếp cận thường phù hợp |
| --- | --- |
| Đọc trạng thái JVM tức thời | JMX attributes/JConsole |
| Đọc một status nghiệp vụ gọn | Spring JMX MBean |
| Biểu đồ theo thời gian | Micrometer + monitoring backend |
| Alert threshold trên nhiều instance | Metrics collector/time-series system |
| Danh sách bản ghi chi tiết | API quản trị có pagination/filter/auth |
| Tải/export lượng lớn | Job asynchronous và storage chuyên biệt |

Không cần expose cùng một dữ liệu lớn qua cả JMX và HTTP chỉ vì có nhiều công cụ dùng nó. Có thể dùng một nguồn metric nội bộ rồi cung cấp các view nhỏ phù hợp từng transport.

## 19. Mẫu thiết kế đối chiếu

### Antipattern A — Trả toàn bộ entity

```java
@ManagedOperation
public List<Order> getAllPendingOrders() {
    return orderRepository.findAllPending();
}
```

Vấn đề: size không giới hạn, JMX client có thể thiếu class, dữ liệu nhạy cảm, tốn database.

### Cách tốt hơn

```java
@ManagedAttribute
public long getPendingOrderCount() {
    return orderMetrics.pendingCount();
}

@ManagedAttribute
public long getOldestPendingAgeSeconds() {
    return orderMetrics.oldestPendingAgeSeconds();
}
```

### Antipattern B — Trả Future cho job dài

```java
@ManagedOperation
public Future<String> rebuildIndex() {
    return rebuildService.submit();
}
```

Vấn đề: Future không là kiểu result dễ quan sát, client không biết job lifecycle.

### Cách tốt hơn

```java
@ManagedOperation
public String requestIndexRebuild() {
    return rebuildService.submitAndReturnId();
}

@ManagedOperation
public String getIndexRebuildStatus(String id) {
    return rebuildService.status(id);
}
```

### Antipattern C — Dùng message làm status

```text
"Everything looks good at 10:01"
"Maybe busy; try later"
```

Đây là các chuỗi hữu ích cho con người nhưng khó làm rule tự động. Tách `StatusCode=HEALTHY/BUSY/FAILED` khỏi `StatusMessage`.

## 20. Xử lý null, unknown và lỗi

Một management API cần có semantics rõ khi không có dữ liệu:

- Chưa từng chạy: `LastRunTime` rỗng hay `NEVER`?
- Status không xác định: `UNKNOWN` có ý nghĩa gì?
- Counter chưa khởi tạo: 0 có thật là 0 hay missing?
- Job ID không tồn tại: trả `NOT_FOUND` hay ném exception?
- Client thiếu quyền: lỗi security không nên bị đổi thành dữ liệu hợp lệ như 0.

Ví dụ tốt:

```java
@ManagedAttribute
public String getLastSuccessTimeUtc() {
    return lastSuccess == null
        ? "NEVER"
        : lastSuccess.toString();
}
```

Với một public management contract, cần document rằng `NEVER` là sentinel hợp lệ. Nếu dùng MXBean/OpenData, có thể chọn representation structured/nullable theo khả năng mapping và nhu cầu client.

Không trả `null` tùy tiện cho mọi exception: client sẽ không biết khác biệt giữa thiếu dữ liệu và lỗi hệ thống.

## 21. Tính nhất quán và tối thiểu hóa tác dụng phụ

Getter có thể được gọi tự động bởi các monitoring tools. Vì thế:

1. Không ghi database trong getter.
2. Không reset counter khi getter bị đọc.
3. Không khóa lâu hoặc đợi job dài.
4. Không tạo session/connection mới không cần thiết.
5. Không log mỗi lần polling ở mức INFO gây log storm.
6. Không trả mutable collection có thể thay đổi trong lúc đọc.
7. Không dựng object graph lớn chỉ để hiển thị vài số.
8. Không để formatter gọi network bên ngoài.

Nếu cần cập nhật metric phức tạp, dùng asynchronous sampling/cache/snapshot với freshness được định nghĩa rõ.

## 22. Thiết kế trong Spring Boot

Spring Boot có cơ chế JMX auto-configuration và Actuator JMX exposure tùy dependency/version. Property thường gặp:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
```

Điều này không đồng nghĩa tất cả Spring beans đều được export, cũng không tự bật remote JMX connector. `management.endpoints.web.exposure.include` và JMX exposure có thể khác nhau.

Khi dự án dùng `@EnableMBeanExport` hoặc custom `MBeanExporter`, cần tránh nhiều exporter cùng đăng ký một ObjectName. Kiểm tra MBeanInfo thực tế sau khi Spring context sẵn sàng.

Với remote JMX, authentication, TLS và phân quyền của connector là trách nhiệm riêng. Spring Security HTTP không mặc nhiên bảo vệ JMX/RMI.

## 23. Bài tập thực hành

### Bài tập 1 — Thiết kế status MBean

Tạo `ImporterStatusManagement` có `Running`, `QueueDepth`, `ProcessedItemsTotal` và `LastSuccessfulRunTime`. Đặt description đầy đủ, kiểm tra read-only flags.

**Mục tiêu:** dữ liệu nhỏ, rõ và có đơn vị.

### Bài tập 2 — Chuyển API trả list lớn

Cho một method `getAllPendingOrders()`. Đề xuất hai hoặc ba attributes thay thế giúp operator chẩn đoán mà không lấy toàn bộ entity.

**Mục tiêu:** giảm payload và lộ dữ liệu.

### Bài tập 3 — CompositeData

Tạo snapshot `state`, `queueDepth`, `processedTotal` dạng `CompositeData` với OpenType đúng. Đọc metadata và giá trị bằng client Java.

**Mục tiêu:** hiểu Open MBean data structure.

### Bài tập 4 — Bảng nhỏ

Tạo một operation trả top 5 queues dưới dạng TabularData. Thử yêu cầu 5000 rows và xác nhận validation từ chối hoặc giới hạn.

**Mục tiêu:** bounded data, tránh payload không giới hạn.

### Bài tập 5 — Async job status

Thiết kế `requestRefresh()` trả ID và `getRefreshStatus(id)` trả một trong các status ổn định.

**Mục tiêu:** phân biệt accepted và completed.

### Bài tập 6 — Contract test

Kiểm tra `MBeanInfo` về type, writable, signature và description, đồng thời negative assert không có method nội bộ.

**Mục tiêu:** bảo vệ tính tương thích và bảo mật.

### Bài tập 7 — Polling load

Tạo một getter đọc snapshot và một getter dùng full data scan. So sánh latency/allocation khi polling nhiều lần ở môi trường test.

**Mục tiêu:** hiểu chi phí của một management getter.

## 24. Câu hỏi ôn tập

**1. Vì sao không trả toàn bộ domain entity qua JMX?** Vì dữ liệu lớn, phụ thuộc classpath/serialization, khó hiển thị và có thể lộ thông tin.

**2. Kiểu nào thường dễ quan sát nhất?** Primitive, String và những Open Types có cấu trúc nhỏ, rõ ràng.

**3. Khi nào dùng CompositeData?** Khi cần một snapshot nhỏ với nhiều trường có tên và kiểu ổn định.

**4. TabularData có phù hợp để xuất hàng triệu record không?** Không. Nó vẫn chịu chi phí payload/serialization và khó vận hành.

**5. `isWritable` cho biết quyền người dùng không?** Không. Nó là khả năng ghi trong metadata MBean.

**6. Vì sao cần đơn vị trong tên attribute?** Để tránh hiểu nhầm milliseconds/seconds/bytes/ratio.

**7. `requestId` có nghĩa job hoàn tất chưa?** Không; client phải đọc status.

**8. Vì sao getter JMX phải nhẹ?** Vì công cụ giám sát có thể gọi lặp liên tục.

**9. Có nên parse một status message tự do để alert không?** Không. Nên có code trạng thái ổn định.

**10. Khi đổi `long` thành `String` trong MBean, có thể ảnh hưởng gì?** Client và monitoring rules có thể bị phá vỡ.

## 25. Tổng kết

**Trả về kiểu dữ liệu nhỏ, rõ và dễ quan sát** là nguyên tắc nền tảng khi thiết kế Spring Framework JMX management API. Một attribute tốt trả về đúng thông tin để đưa ra quyết định vận hành, với tên, đơn vị, kiểu, độ mới và ý nghĩa ổn định. Một operation tốt trả kết quả gọn, mô tả rành mạch việc yêu cầu đã được nhận hay thực sự hoàn tất.

Ưu tiên primitive/String hoặc Open Types phù hợp; tránh domain objects lớn, entity collections, dữ liệu nhạy cảm và getter nặng. Với dữ liệu nhiều trường, dùng CompositeData/MXBean khi có lợi; với dữ liệu lớn, dùng API chuyên biệt hoặc job async. Luôn xác minh MBeanInfo runtime, kiểm thử latency/payload, bảo vệ quyền JMX và duy trì khả năng tương thích của contract.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `ManagedAttribute`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — `ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `CompositeData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — `TabularData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/TabularData.html
- Java SE 21 — MXBean documentation: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html