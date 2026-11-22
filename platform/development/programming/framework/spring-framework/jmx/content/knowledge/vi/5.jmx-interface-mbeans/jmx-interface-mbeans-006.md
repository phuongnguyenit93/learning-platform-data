# Thiết kế management interface nhỏ và ổn định cho MBean trong Spring Framework JMX

## 1. Mục tiêu

**Management interface** là hợp đồng quản trị mà một MBean công bố cho JMX client. Nó xác định các thuộc tính có thể đọc hoặc ghi, các thao tác có thể gọi và đôi khi những thông báo có thể phát ra. Một interface quản trị tốt chỉ đưa ra những khả năng vận hành thật sự cần thiết, có tên và ngữ nghĩa dễ hiểu, giữ tính tương thích khi phần triển khai nội bộ thay đổi.

Trong ứng dụng Spring, service nghiệp vụ có thể có rất nhiều phương thức, nhưng người vận hành chỉ cần xem một vài trạng thái và thực hiện một số thao tác có kiểm soát. **Không nên expose nguyên vẹn API nghiệp vụ như API quản trị.** Một management interface nhỏ giúp giảm bề mặt tấn công, hạn chế thao tác nhầm, ổn định các dashboard/script và giúp triển khai độc lập với cách tổ chức class bên trong.

Ví dụ một service cache có các phương thức nghiệp vụ `get`, `put`, `evict`, `loadFromDatabase`, `clear`, `refresh` và các thông tin nội bộ. Interface JMX có thể chỉ cần:

- Trạng thái cache: đang bật không, kích thước hiện tại, số lần refresh.
- Một thao tác vận hành đã xác định: yêu cầu refresh.
- Có thể thay đổi trạng thái bật/tắt nếu nghiệp vụ thực sự cho phép.
- Không công bố API lấy mọi dữ liệu cache, sửa từng bản ghi hay lộ cấu hình nhạy cảm.

## 2. Management interface nằm ở đâu trong mô hình JMX?

JMX dựa trên `MBeanServer`, nơi MBean đăng ký dưới `ObjectName`. JMX client tìm tên, đọc thuộc tính và gọi operation được công bố trong `MBeanInfo`.

```text
JConsole / JMX client / automation
               |
               | ObjectName + management contract
               v
          MBeanServer
               |
               v
    Management interface (ổn định)
       | attribute   | operation
       v             v
    Adapter / MBean implementation
               |
               v
      Spring service nghiệp vụ
      (có thể thay đổi nội bộ)
```

Có hai cách phổ biến để biểu diễn management contract:

1. **Standard MBean:** Java interface được đặt tên theo quy ước `<ClassName>MBean`; implementation cung cấp các getter/setter và operation tương ứng.
2. **Spring-exported MBean:** Spring `MBeanExporter` có thể expose POJO dựa trên interface đã chọn hoặc annotation `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` thông qua assembler thích hợp. Có thể dùng một adapter chuyên biệt để giữ service nghiệp vụ độc lập với JMX.

Không phải mọi Java interface đều tự động trở thành MBean. JMX cần implementation tương ứng và cơ chế đăng ký, hoặc Spring cần cấu hình exporter/assembler phù hợp.

## 3. Chọn bề mặt quản trị tối thiểu

Trước khi viết interface, hãy liệt kê các tình huống thực sự cần quản trị:

| Nhu cầu | Hợp đồng quản trị đề xuất | Không nên expose |
| --- | --- | --- |
| Kiểm tra tình trạng | `getStatus()`, `isEnabled()` | Toàn bộ object graph, cấu hình chứa secrets |
| Đo trạng thái tức thời | `getQueueDepth()`, `getActiveWorkers()` | Collection lớn hoặc dữ liệu từng khách hàng |
| Quan sát kết quả hành động | `getLastRefreshTime()`, `getLastErrorSummary()` | Exception nguyên bản, stack trace nhạy cảm |
| Tác vụ vận hành có kiểm soát | `requestRefresh()` | Mọi CRUD hoặc command tùy ý |
| Cấu hình điều chỉnh runtime | `setEnabled(boolean)` khi cần | Setter cho mọi field cấu hình |

Một số câu hỏi trước khi công bố mỗi method:

- Người vận hành hoặc automation có thực sự cần method này không?
- Gọi method có thể làm gián đoạn dịch vụ, gây tác động ngoài ý muốn hoặc xóa dữ liệu không?
- Tên method, kiểu dữ liệu và ngữ nghĩa có giữ ổn định qua các đợt nâng cấp không?
- Có thể trả dữ liệu đơn giản, giới hạn kích thước và không nhạy cảm không?
- Nếu lời gọi mất kết nối, client có thể biết tác vụ đã thực hiện chưa?

Đưa vào interface những thành phần có câu trả lời rõ ràng; giữ phần còn lại trong code nội bộ.

## 4. Ví dụ: Standard MBean với interface chuyên dụng

Hợp đồng nhỏ cho một bộ xử lý job:

```java
package com.example.management;

public interface JobMonitorMBean {
    boolean isEnabled();
    int getActiveJobs();
    long getCompletedJobs();
    String getStatus();
    void requestRefresh();
}
```

Implementation có thể ủy quyền cho một Spring service:

```java
package com.example.management;

import com.example.jobs.JobService;

public class JobMonitor implements JobMonitorMBean {
    private final JobService service;

    public JobMonitor(JobService service) {
        this.service = service;
    }

    @Override
    public boolean isEnabled() {
        return service.isEnabled();
    }

    @Override
    public int getActiveJobs() {
        return service.activeJobCount();
    }

    @Override
    public long getCompletedJobs() {
        return service.completedJobCount();
    }

    @Override
    public String getStatus() {
        return service.statusSummary();
    }

    @Override
    public void requestRefresh() {
        service.requestRefresh();
    }
}
```

Ở đây `JobMonitorMBean` là hợp đồng công khai cho JMX; `JobService` là dịch vụ nội bộ có thể phát triển độc lập. Người vận hành không được nhìn thấy các method nghiệp vụ như `cancelJob(id)`, `getCustomerPayload(id)`, `executeSql(...)`.

Đăng ký bằng JMX thuần:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name =
    new ObjectName("com.example.jobs:type=JobMonitor,name=Primary");

server.registerMBean(new JobMonitor(jobService), name);
```

Để ví dụ này hoạt động, `jobService` là instance `JobService` đã tạo/inject. Interface và class public nên đặt ở các file Java tương ứng theo quy ước Standard MBean. Khi dùng Spring, có thể để `MBeanExporter` đăng ký adapter qua `ObjectName`, gắn lifecycle với application context.

### Getter là JMX attribute, operation là hành động

Theo quy ước Standard MBean:

- `isEnabled()` tạo attribute boolean `Enabled` chỉ đọc.
- `getActiveJobs()` tạo attribute `ActiveJobs` chỉ đọc.
- `getCompletedJobs()` tạo attribute `CompletedJobs` chỉ đọc.
- `getStatus()` tạo attribute `Status` chỉ đọc.
- `requestRefresh()` được công bố như một operation.

Nếu thêm `setEnabled(boolean)`, attribute `Enabled` có thể trở thành thuộc tính ghi được. Chỉ thêm setter khi việc thay đổi runtime được cho phép và được kiểm soát rõ ràng. Không dùng getter cho hoạt động tốn thời gian, làm thay đổi trạng thái hoặc có side effect.

## 5. Ví dụ: Spring MBean với annotation chọn lọc

Spring hỗ trợ mô hình gần với service/POJO thông qua các annotation JMX. Chỉ đánh dấu method muốn expose:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=JobMonitor,name=Primary",
    description = "Trạng thái và thao tác quản trị job"
)
public class JobManagementEndpoint {
    private final JobService service;

    public JobManagementEndpoint(JobService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Số job đang chạy")
    public int getActiveJobs() {
        return service.activeJobCount();
    }

    @ManagedAttribute(description = "Trạng thái tóm tắt")
    public String getStatus() {
        return service.statusSummary();
    }

    @ManagedOperation(description = "Yêu cầu làm mới dữ liệu job")
    public void requestRefresh() {
        service.requestRefresh();
    }
}
```

Kích hoạt annotation export qua cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
```

Trong cấu hình này, annotation xác định bề mặt được export thông qua metadata assembler do Spring thiết lập. Nếu ứng dụng đã có exporter thủ công, tránh bật nhiều exporter cùng đăng ký một `ObjectName`.

**Lưu ý:** `@ManagedResource` không tự cung cấp authentication/authorization. Quyền JMX connector, policy bảo mật ứng dụng và xác thực các thao tác có tác động lớn vẫn là trách nhiệm triển khai.

## 6. Đặt tên method và thuộc tính có ngữ nghĩa ổn định

Management API thường được dùng bởi script, hệ thống monitoring, JConsole, dashboard và các client chạy lâu hơn vòng đời của một bản release. Vì vậy tên và ngữ nghĩa cần ổn định hơn API nội bộ.

Ví dụ tên tốt:

```java
int getQueueDepth();
boolean isAcceptingRequests();
long getFailedJobCount();
String getHealthSummary();
void requestReload();
```

Tên mơ hồ, khó dùng:

```java
Object getEverything();
void execute(String command);
String getData();
void reset();
```

`reset()` không cho biết reset cái gì và hậu quả ra sao. `requestReload()` nêu rõ đây là yêu cầu, khác với cam kết đã hoàn thành trước khi method trả về.

Tên attribute JMX được suy ra từ getter/setter hoặc cấu hình metadata. Một khi client dùng `QueueDepth`, đổi method `getQueueDepth` thành `getPendingItems` có thể đổi tên attribute thành `PendingItems`, làm hỏng client cũ. Nên cố định tên quản trị như một contract được version hóa.

## 7. Ưu tiên kiểu dữ liệu JMX đơn giản và rõ nghĩa

Các kiểu thông dụng:

- `boolean`: trạng thái bật/tắt, cờ read-only.
- `int`/`long`: số lượng, bộ đếm; ưu tiên `long` cho bộ đếm tích lũy.
- `String`: trạng thái tóm tắt, nhãn, tên tài nguyên.
- `double`: tỉ lệ hoặc metric dạng số thực, phải mô tả đơn vị.
- `CompositeData`, `TabularData`: cấu trúc Open MBean có schema; cân nhắc khi nhiều trường có liên hệ chặt chẽ.
- MXBean có khả năng ánh xạ nhiều kiểu Java vào Open Types của JMX, thuận lợi cho client tương tác qua remote connector.

Hạn chế trả về các class nghiệp vụ tùy biến hoặc collection phức tạp làm client phải phụ thuộc vào JAR và classpath của server. Với Standard MBean dùng qua remote JMX, các kiểu serialize không có ở client có thể gây lỗi classloading/deserialization; Open MBean/MXBean là lựa chọn dễ tương tác hơn nếu cần dữ liệu có cấu trúc.

Đơn vị nên rõ ràng:

```java
long getUptimeMillis();
long getLastRefreshEpochMillis();
int getQueueDepth();
double getCpuLoadRatio();
```

Không đổi đơn vị của `getUptimeMillis()` từ mili giây sang giây mà giữ nguyên tên; đây là breaking change dù kiểu trả về vẫn là `long`. Với số liệu không khả dụng, mô tả quy ước trả về `-1`, `NaN` hoặc trạng thái khác nếu phù hợp; đừng thay đổi ngầm giữa các phiên bản.

## 8. Tính ổn định khi thay đổi implementation

Có hai tầng cần phân biệt:

1. **Implementation contract nội bộ:** class, service, repository, cấu trúc cache, thuật toán và dependency có thể thay đổi.
2. **JMX management contract:** `ObjectName`, tên attribute, kiểu attribute, quyền đọc/ghi, operation name, signature, ý nghĩa và notification type mà client phụ thuộc.

Ví dụ trước đây `JobService` dùng thread pool, sau này chuyển sang scheduler bất đồng bộ. Management interface vẫn có thể giữ `getActiveJobs()`, `getCompletedJobs()`, `requestRefresh()` nếu semantics giữ nguyên.

Những thay đổi dễ phá client:

| Thay đổi | Tác động |
| --- | --- |
| Đổi domain hoặc key property của `ObjectName` | Client không tìm được MBean theo tên cũ |
| Đổi `ActiveJobs` thành `RunningTasks` | Script đọc attribute cũ thất bại |
| Đổi `long getCompletedJobs()` thành `String` | Client ép kiểu không tương thích |
| Thay `requestRefresh()` thành `refresh(boolean force)` | Operation name/signature thay đổi |
| Biến attribute read-only thành writable | Thay đổi bề mặt quản trị và quyền thao tác |
| Đổi đơn vị từ milliseconds sang seconds | Dữ liệu client diễn giải sai dù method vẫn trả số |
| Đổi thao tác bất đồng bộ thành đồng bộ chờ hoàn tất | Thay đổi độ trễ và timeout của client |

Có thể mở rộng bằng cách **thêm** attribute/operation mới, giữ tên cũ trong giai đoạn chuyển tiếp, công bố deprecation và có kế hoạch di chuyển script/client. Nhưng việc thêm operation overload cũng cần thận trọng: client gọi `invoke` phải cung cấp signature rõ ràng khi overload, và một số công cụ vận hành hiển thị kém trực quan.

## 9. Điều chỉnh quyền ghi và tác động phụ

Không phải tất cả thông số nên ghi được. Attribute dùng quan sát nên read-only theo mặc định; các thay đổi runtime chỉ nên có trong contract nếu cần trong vận hành và có ràng buộc.

Ví dụ một setter hợp lệ cần validation:

```java
public interface ThrottleControlMBean {
    int getMaxConcurrentJobs();
    void setMaxConcurrentJobs(int maxConcurrentJobs);
}
```

Implementation:

```java
@Override
public void setMaxConcurrentJobs(int value) {
    if (value < 1 || value > 200) {
        throw new IllegalArgumentException(
            "maxConcurrentJobs must be between 1 and 200"
        );
    }
    service.updateConcurrencyLimit(value);
}
```

Phân biệt **hợp lệ về nghiệp vụ** và **được phép về bảo mật**. Validation giới hạn giá trị nhưng không tự xác định người gọi có quyền điều chỉnh limit. Khi expose remote JMX, cần cấu hình authentication/authorization, mã hóa kênh phù hợp, giới hạn network access và ghi audit cho operation nhạy cảm nếu hệ thống yêu cầu.

Các thao tác có tác động lớn như `shutdown()`, `deleteAll()` hoặc `executeCommand(String)` thường không phù hợp với interface quản trị thông dụng. Nếu không thể tránh, cần thiết kế quyền riêng và cơ chế kiểm soát thao tác rõ ràng, thay vì expose vì chúng đã có trong service.

## 10. Thiết kế operation bền vững trong môi trường phân tán

Operation JMX có thể được gọi từ xa qua `MBeanServerConnection`. Lời gọi có thể gặp latency, timeout hoặc ngắt mạng. Client có thể không biết operation đã thực hiện hay chưa nếu kết nối mất sau khi server nhận lệnh.

Với tác vụ tốn thời gian, nên cân nhắc API dạng **request + quan sát trạng thái**:

```java
public interface ReindexManagementMBean {
    String requestReindex();
    String getLastReindexState();
    long getLastReindexStartedAtMillis();
}
```

Nếu cần đối chiếu nhiều request, thiết kế thêm request ID và khả năng đọc trạng thái theo ID, nhưng phải giới hạn số lượng ID được lưu hoặc có thời hạn tồn tại. `requestReindex()` nên nêu rõ yêu cầu được chấp nhận chứ không hứa job đã hoàn thành. Đối với operation có thể retry, cần xác định tính idempotent hoặc một idempotency token khi cần.

Không nên tạo một JMX getter mà mỗi lần đọc lại tải hàng triệu record hoặc chờ database vài phút; JConsole và monitoring có thể đọc thường xuyên. Phần quan sát nên nhanh, có giới hạn tài nguyên và side effect tối thiểu.

## 11. Chọn ObjectName ổn định

Ngay cả khi management interface không thay đổi, client vẫn thất bại nếu ObjectName thay đổi tùy tiện.

Ví dụ:

```text
com.example.jobs:type=JobMonitor,name=Primary
```

Domain `com.example.jobs` và các key `type`, `name` tạo định danh có thể ghi trong dashboard hoặc file cấu hình. Không đưa PID ngẫu nhiên hoặc timestamp vào ObjectName trừ khi thực sự cần phân biệt instance động và client có discovery thích hợp.

Nếu một MBeanServer chứa nhiều instance:

```text
com.example.jobs:type=JobMonitor,name=Primary,instance=worker-1
com.example.jobs:type=JobMonitor,name=Primary,instance=worker-2
```

Client có thể query pattern `com.example.jobs:type=JobMonitor,*`. Nếu chỉ cần quản trị một endpoint ứng dụng, một tên cố định thường đơn giản hơn. Lựa chọn này phải phù hợp topology triển khai: MBeanServer trong từng JVM vốn phân biệt theo kết nối server, nên không tự động cần instance key cho mọi deployment.

## 12. Ví dụ truy cập contract từ client

Client JMX dùng `ObjectName` và tên thuộc tính/operation, không phụ thuộc vào class implementation nội bộ:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name =
    new ObjectName("com.example.jobs:type=JobMonitor,name=Primary");

int active = (Integer) server.getAttribute(name, "ActiveJobs");
long completed = (Long) server.getAttribute(name, "CompletedJobs");

server.invoke(
    name,
    "requestRefresh",
    new Object[0],
    new String[0]
);
```

Ví dụ giả định `JobMonitor` đã được đăng ký trong cùng MBeanServer. Trong remote JMX, dùng `MBeanServerConnection` thay `MBeanServer`, còn `ObjectName`, attribute name và operation signature vẫn có cùng ý nghĩa.

Client cũng có thể dùng `JMX.newMBeanProxy` hoặc Spring `MBeanProxyFactoryBean` để gọi interface Java thay cho thao tác trực tiếp bằng chuỗi; điều này vẫn yêu cầu hợp đồng phía client khớp với MBean được công bố.

## 13. Kiểm tra mức hợp đồng trước khi phát hành

Khi thiết kế interface, các câu hỏi kiểm tra thực tế gồm:

- Có thể đọc `MBeanInfo` và thấy đúng danh sách attribute/operation dự kiến hay không?
- Có operation, getter hoặc setter nào được expose ngoài chủ ý không?
- Các tên, kiểu, đơn vị và mô tả có rõ ràng đối với người không biết code nội bộ không?
- Các getter có hoàn tất nhanh và không tạo tác dụng phụ không?
- Operation có giới hạn tham số, thông báo lỗi và hành vi khi retry rõ ràng không?
- Nếu client đang dùng phiên bản trước, những lời gọi cũ còn hoạt động sau release không?
- Nếu có nhiều Spring application context hoặc nhiều instance, tên MBean có còn duy nhất trên đúng MBeanServer không?

Có thể khám phá interface ở runtime:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s: %s (read=%s, write=%s)%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

Việc xem `MBeanInfo` giúp xác nhận giao diện đã đăng ký thực tế, vì code annotation/interface có thể khác nội dung được exporter/assembler công bố nếu cấu hình không như dự kiến.

## 14. Mô hình tư duy và kết luận

```text
Nhu cầu vận hành
      |
      v
Chọn ít thuộc tính/operation thực sự cần
      |
      v
Định nghĩa Management Contract
  - ObjectName ổn định
  - Tên attribute/operation rõ ràng
  - Kiểu và đơn vị dễ hiểu
  - Quyền ghi hạn chế
  - Hành vi operation được mô tả
      |
      v
Adapter MBean / Spring JMX annotations
      |
      v
Service nghiệp vụ có thể thay đổi độc lập
```

**Nguyên tắc chính:** Một management interface tốt **nhỏ, tập trung, ổn định và có giới hạn tác động**. Nó cho phép quan sát trạng thái và thực hiện một vài thao tác cần thiết, đồng thời che giấu implementation và dữ liệu nghiệp vụ. Trong Spring Framework JMX, hãy dùng interface MBean chuyên dụng hoặc annotation chọn lọc trên adapter; giữ `ObjectName`, tên, kiểu dữ liệu, đơn vị và ngữ nghĩa operation ổn định để các công cụ vận hành và client không bị phá vỡ mỗi khi ứng dụng nâng cấp.
