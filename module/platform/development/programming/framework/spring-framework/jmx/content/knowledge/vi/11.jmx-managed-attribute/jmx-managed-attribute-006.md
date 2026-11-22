# Đặt tên attribute ổn định khi refactor phương thức trong Spring Framework JMX

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Hiểu cách JMX xác định tên **attribute** từ các accessor method được công bố bằng \`@ManagedAttribute\` trong Spring Framework.
- Phân biệt tên method Java, tên attribute JMX và \`ObjectName\` của MBean.
- Nhận ra một thay đổi tưởng như chỉ refactor code có thể làm thay đổi contract mà JMX client đang sử dụng.
- Giữ tên attribute ổn định khi đổi tên method nghiệp vụ bằng một lớp adapter quản trị hoặc accessor tương thích.
- Xây dựng quy trình refactor, kiểm chứng \`MBeanInfo\` và chuyển đổi client để tránh đứt gãy khi triển khai.
- Biết giới hạn của \`@ManagedAttribute\` và không dựa vào một tham số đổi tên attribute không tồn tại trong annotation này.

## 1. Vấn đề: tên method là một phần của JMX contract

Trong Java, refactor đổi tên method thường được xem là thao tác nội bộ, nhất là khi IDE cập nhật mọi chỗ gọi trong cùng repository. Nhưng khi một method được export qua JMX, tên của nó có thể góp phần xác định **tên attribute mà JConsole, monitoring tool hoặc custom JMX client nhìn thấy**.

Ví dụ:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queue.size();
}
\`\`\`

Trong mô hình JMX metadata assembly của Spring, getter trên thường được công bố thành attribute:

\`\`\`text
QueueDepth
\`\`\`

Một client có thể gọi:

\`\`\`java
connection.getAttribute(objectName, "QueueDepth");
\`\`\`

Nếu developer đổi method thành:

\`\`\`java
@ManagedAttribute
public int getPendingTasks() {
    return queue.size();
}
\`\`\`

thì attribute được công bố có thể đổi từ \`QueueDepth\` sang \`PendingTasks\`. Client vẫn gọi \`QueueDepth\` sẽ nhận lỗi liên quan attribute không tồn tại, dù nghiệp vụ trả về cùng một số lượng.

**Bài học chính:** Khi public JMX attribute, tên được công bố là một phần của giao diện quản trị, phải được quản lý giống API contract.

## 2. Ba loại tên không được nhầm lẫn

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Java method name | \`getQueueDepth()\` | Phương thức trong code Java |
| JMX attribute name | \`QueueDepth\` | Tên client truyền vào \`getAttribute\` |
| MBean ObjectName | \`learning.jmx:type=QueueMonitor,name=Primary\` | Định danh MBean trong một MBeanServer |

Đây là các phần riêng:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueMonitor,name=Primary"
);

Object depth = connection.getAttribute(
    name,
    "QueueDepth"
);
\`\`\`

ObjectName tìm MBean cần truy cập. Chuỗi \`"QueueDepth"\` tìm attribute thuộc MBean đó. Việc đổi \`getQueueDepth()\` thành \`getPendingTasks()\` không nhất thiết đổi ObjectName, nhưng có thể đổi attribute được expose.

Một MBean có nhiều attributes cùng thuộc một ObjectName. ObjectName ổn định không đủ nếu tên attributes đã thay đổi.

## 3. Spring @ManagedAttribute công bố điều gì?

\`@ManagedAttribute\` thuộc:

\`\`\`java
org.springframework.jmx.export.annotation.ManagedAttribute
\`\`\`

Nó đánh dấu getter hoặc setter quản trị trong mô hình annotation-driven JMX của Spring. Một Spring JMX exporter có \`AnnotationJmxAttributeSource\` và assembler tương ứng đọc annotation để hình thành \`MBeanInfo\`.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {

    private volatile int depth = 0;

    @ManagedAttribute(description = "Current queue depth")
    public int getQueueDepth() {
        return depth;
    }
}
\`\`\`

Khi exporter đăng ký MBean thành công, client đọc attribute \`QueueDepth\`.

### Một thuộc tính không phải là một biến Java

Tên attribute JMX thường xuất phát từ accessor naming convention, không nhất thiết trùng Java field:

\`\`\`java
private int pendingCount;

@ManagedAttribute
public int getQueueDepth() {
    return pendingCount;
}
\`\`\`

Attribute được công bố vẫn là \`QueueDepth\`. Đây là lợi thế: có thể refactor field và implementation mà không đổi getter quản trị.

### Getter và setter

Ví dụ:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int maxWorkers) {
    if (maxWorkers < 1 || maxWorkers > 256) {
        throw new IllegalArgumentException("Invalid maxWorkers");
    }
    this.maxWorkers = maxWorkers;
}
\`\`\`

Một attribute \`MaxWorkers\` có thể đọc/ghi khi metadata exporter công bố cả getter và setter. Nếu chỉ cần quan sát, không annotate setter để tránh mở quyền sửa trạng thái qua JMX.

### Boolean getter

\`\`\`java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}
\`\`\`

Tên attribute thường là \`Paused\`, không phải \`IsPaused\`.

Khi refactor giữa \`isPaused()\` và \`getPaused()\`, cần kiểm tra metadata thực tế; cả hai có thể theo convention boolean nhưng các quy tắc và tình huống getter trùng có thể ảnh hưởng kết quả.

## 4. Điều gì xảy ra khi đổi tên accessor?

Giả sử ban đầu code là:

\`\`\`java
@ManagedAttribute
public long getCompletedJobs() {
    return completedJobs.get();
}
\`\`\`

Các công cụ JMX đọc:

\`\`\`text
CompletedJobs
\`\`\`

Sau refactor:

\`\`\`java
@ManagedAttribute
public long getProcessedJobs() {
    return completedJobs.get();
}
\`\`\`

Tên attribute mới có thể là:

\`\`\`text
ProcessedJobs
\`\`\`

Đây là thay đổi có thể ảnh hưởng tới:

- JConsole hoặc VisualVM đang hiển thị attributes theo tên.
- Custom JMX client dùng \`MBeanServerConnection.getAttribute(...)\`.
- Script vận hành gọi JMX qua library hoặc command-line tooling.
- Hệ thống JMX exporter có mapping rule tham chiếu attribute name.
- Dashboard/alert pipeline lấy dữ liệu từ JMX và dựa vào attribute hoặc tên metric được sinh từ attribute.
- Runbook sự cố hoặc automation ghi rõ ObjectName và attribute.

Thay đổi Java method name có thể được IDE sửa hết trong repository nhưng **client JMX ngoài repository** vẫn giữ chuỗi tên cũ. Đây là nguồn gốc của breaking change âm thầm.

## 5. Cách tốt nhất: tách management facade khỏi implementation

Khi định nghĩa giao diện JMX ổn định, nên coi accessor quản trị là một **adapter** nhỏ chuyển thông tin từ service nội bộ sang contract JMX.

Ví dụ service nghiệp vụ:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueService {
    private final AtomicInteger pendingTasks = new AtomicInteger();

    public int pendingTaskCount() {
        return pendingTasks.get();
    }

    public void recordPendingTask() {
        pendingTasks.incrementAndGet();
    }
}
\`\`\`

Management facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary",
    description = "Stable JMX management view for queue"
)
public class QueueManagement {

    private final QueueService queueService;

    public QueueManagement(QueueService queueService) {
        this.queueService = queueService;
    }

    @ManagedAttribute(description = "Queue depth")
    public int getQueueDepth() {
        return queueService.pendingTaskCount();
    }
}
\`\`\`

Ở đây developer có thể refactor \`pendingTaskCount()\`, thay đổi thuật toán hay tên field trong QueueService mà vẫn giữ \`getQueueDepth()\` là management API.

Ví dụ cấu hình Spring:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {

    @Bean
    public QueueService queueService() {
        return new QueueService();
    }

    @Bean
    public QueueManagement queueManagement(QueueService queueService) {
        return new QueueManagement(queueService);
    }
}
\`\`\`

Spring sẽ quản lý QueueManagement và exporter phù hợp khi annotation export được kích hoạt. ObjectName và getter quản trị được giữ ổn định, trong khi implementation phía sau có thể thay đổi.

**Tư duy:** Java service API và JMX management API có thể phát triển theo nhịp khác nhau. Không cần ép một tên method nghiệp vụ tồn tại mãi chỉ vì client quản trị đã dùng tên JMX cũ.

## 6. Có thể đặt tên attribute tùy ý ngay trong @ManagedAttribute không?

Đây là điểm dễ nhầm vì nhiều annotation và framework khác hỗ trợ tham số \`name\`.

Trong Spring Framework, \`@ManagedAttribute\` thông thường hỗ trợ metadata như description, currencyTimeLimit, defaultValue, persistPolicy, persistPeriod. **Không có một thuộc tính \`name\` để đổi trực tiếp tên JMX attribute thành chuỗi tùy ý.**

Ví dụ sau là **không hợp lệ**:

\`\`\`java
// Sai: @ManagedAttribute không có phần tử name.
@ManagedAttribute(name = "QueueDepth")
public int getPendingTasks() {
    return queueService.pendingTaskCount();
}
\`\`\`

Không dùng ví dụ này như code chạy được.

Nếu muốn giữ JMX attribute \`QueueDepth\` trong khi đổi tên method nội bộ, hãy giữ một getter quản trị \`getQueueDepth()\`, dùng facade/adapter hoặc cấu hình management metadata qua chiến lược phù hợp thay vì giả định annotation có rename alias.

### Vì sao không nên dựa vào cấu hình tùy biến quá sớm?

Spring JMX có \`MBeanInfoAssembler\`, \`AbstractReflectiveMBeanInfoAssembler\`, \`MetadataMBeanInfoAssembler\` và các cơ chế khác, nhưng tùy biến cách ánh xạ tên attribute có thể làm contract khó đọc và khó bảo trì. Giữ một getter rõ tên trên facade thường là lựa chọn minh bạch hơn.

Nếu bài toán thật sự yêu cầu ánh xạ tên khác convention, cần thiết kế và kiểm tra assembler/custom MBeanInfo hoặc DynamicMBean có contract tường minh.

## 7. Giữ tên cũ bằng compatibility accessor

Nếu hiện tại method đang bị đổi tên trong chính class được export, có thể giữ accessor cũ làm adapter:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {

    private final QueueService service;

    public QueueMonitor(QueueService service) {
        this.service = service;
    }

    // Public JMX contract ổn định:
    @ManagedAttribute(description = "Current queue depth")
    public int getQueueDepth() {
        return service.pendingTaskCount();
    }

    // Method nội bộ mới, không công bố qua JMX:
    public int getPendingTasks() {
        return service.pendingTaskCount();
    }
}
\`\`\`

Hai method có thể cùng trả giá trị nhưng chỉ một được annotate. Điều này giúp refactor code nội bộ mà không thay đổi JMX attribute.

### Có nên annotate cả hai getter?

Có thể hỗ trợ giai đoạn chuyển đổi nhưng cần chủ ý:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return service.pendingTaskCount();
}

@ManagedAttribute
public int getPendingTasks() {
    return service.pendingTaskCount();
}
\`\`\`

Khi đó exporter có thể công bố hai attributes \`QueueDepth\` và \`PendingTasks\`. Tình huống này phù hợp nếu muốn client cũ và mới cùng hoạt động trong giai đoạn migration.

Nhưng cần tài liệu hóa:

- Tên nào là canonical.
- Tên nào là compatibility alias.
- Thời điểm dự kiến ngừng hỗ trợ tên cũ.
- Các monitoring rules và scripts nào phải được cập nhật.
- Đảm bảo hai getter cùng ngữ nghĩa, đơn vị, kiểu dữ liệu.

Không nên vô tình công bố hai thuộc tính chỉ vì refactor thiếu kiểm soát.

## 8. Kiểm chứng contract bằng MBeanInfo

Chỉ dựa vào việc \`@ManagedAttribute\` có trên method là chưa đủ; contract thật sự được JMX client nhìn thấy nằm trong metadata của MBean đã đăng ký.

Ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectAttributes {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueMonitor,name=Primary"
        );

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                "MBean not registered: " + name
            );
        }

        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "name=%s type=%s read=%s write=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }
    }
}
\`\`\`

Khi chạy trong **đúng JVM có MBean đăng ký**, kết quả có thể bao gồm:

\`\`\`text
name=QueueDepth type=int read=true write=false
\`\`\`

Lưu ý: nếu tạo một Java process độc lập và gọi \`ManagementFactory.getPlatformMBeanServer()\`, bạn đang đọc MBeanServer của process mới, không tự nhìn thấy MBeans trong JVM của ứng dụng. Để kiểm chứng từ process khác, sử dụng \`MBeanServerConnection\` qua JMX connector vào đúng target JVM.

### Contract test nên kiểm tra gì?

Đối với JMX attribute quan trọng, kiểm tra:

1. ObjectName mong đợi đã được đăng ký.
2. Attribute tên cũ còn tồn tại.
3. Attribute có type đúng.
4. Quyền đọc/ghi đúng ý định.
5. Giá trị đọc phản ánh state đúng.
6. Nếu migration có alias, cả tên cũ và mới đều có hành vi nhất quán.

Một test có thể kiểm tra metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

boolean hasQueueDepth = java.util.Arrays.stream(
        info.getAttributes()
    ).anyMatch(a ->
        "QueueDepth".equals(a.getName())
        && "int".equals(a.getType())
        && a.isReadable()
    );

if (!hasQueueDepth) {
    throw new AssertionError(
        "JMX attribute QueueDepth contract changed"
    );
}
\`\`\`

Đây là kiểm thử contract có ích vì phát hiện một thay đổi tên có thể phá vỡ client mà Java compiler không thể nhìn thấy.

## 9. Ví dụ refactor an toàn theo từng bước

Giả sử phiên bản hiện tại của ứng dụng công bố:

\`\`\`text
ObjectName: learning.jmx:type=WorkerPool,name=Primary
Attribute: ActiveThreads
Type: int
Readable: true
Writable: false
\`\`\`

Code hiện tại:

\`\`\`java
@ManagedAttribute
public int getActiveThreads() {
    return executor.getActiveCount();
}
\`\`\`

Bạn muốn đổi cách biểu diễn trong service thành \`getRunningTaskCount()\`.

### Bước 1 — Chốt JMX contract đang được dùng

Ghi lại ObjectName, attribute name, type, read/write semantics, đơn vị và ý nghĩa của giá trị. Tìm các consumer: scripts, monitoring configurations, alert rules, dashboards, runbooks.

### Bước 2 — Refactor implementation

\`\`\`java
public int runningTaskCount() {
    return executor.getActiveCount();
}
\`\`\`

### Bước 3 — Giữ getter quản trị

\`\`\`java
@ManagedAttribute(description = "Currently executing tasks")
public int getActiveThreads() {
    return runningTaskCount();
}
\`\`\`

### Bước 4 — Nếu cần API mới, tạo alias có chủ đích

\`\`\`java
@ManagedAttribute(description = "Currently executing tasks")
public int getRunningTaskCount() {
    return runningTaskCount();
}
\`\`\`

### Bước 5 — Kiểm tra MBeanInfo

Bảo đảm attribute \`ActiveThreads\` vẫn tồn tại. Nếu có alias, \`RunningTaskCount\` cũng phải đúng kiểu và cùng ý nghĩa.

### Bước 6 — Triển khai và chuyển client

Cho client mới sử dụng tên chuẩn mới, nhưng giữ tên cũ trong thời hạn hỗ trợ đã công bố. Sau khi xác nhận tất cả consumer đã chuyển, việc loại bỏ alias cũ là một **breaking change được quản lý**, không phải refactor thuần túy.

## 10. Những thay đổi khác có thể phá contract

Tên attribute là một phần quan trọng, nhưng không phải duy nhất.

### Đổi kiểu trả về

Từ:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() { ... }
\`\`\`

sang:

\`\`\`java
@ManagedAttribute
public long getQueueDepth() { ... }
\`\`\`

giữ tên \`QueueDepth\` nhưng thay type từ \`int\` sang \`long\`. Một số client ép kiểu \`Integer\` sẽ lỗi dù tên vẫn tồn tại.

### Đổi đơn vị

Từ \`getRetryDelay()\` trả mili giây sang trả giây mà không đổi tên hoặc tài liệu là thay đổi ngữ nghĩa nguy hiểm. Nên giữ đơn vị cũ hoặc đặt tên mới có đơn vị rõ ràng, ví dụ \`RetryDelaySeconds\`, và migration có chủ đích.

### Đổi read-only thành writable

Thêm:

\`\`\`java
@ManagedAttribute
public void setQueueDepth(int value) { ... }
\`\`\`

có thể mở quyền điều chỉnh trạng thái qua JMX. Đây là thay đổi bảo mật/vận hành, cần kiểm soát quyền và tính hợp lệ, không phải refactor vô hại.

### Đổi ObjectName

Từ:

\`\`\`text
learning.jmx:type=WorkerPool,name=Primary
\`\`\`

sang:

\`\`\`text
learning.jmx:type=Executor,name=Primary
\`\`\`

là thay đổi identity MBean và có thể làm client cũ không tìm được MBean, ngay cả khi attribute \`ActiveThreads\` không thay đổi.

### Đổi writable/readable semantics

Một getter bị bỏ hoặc một setter được thêm có thể thay đổi quyền đọc/ghi của attribute. Hãy kiểm tra \`MBeanAttributeInfo.isReadable()\` và \`isWritable()\`.

## 11. @ManagedAttribute với interface/proxy và cấu hình exporter

Trong Spring Framework, JMX metadata thường được xử lý bởi:

- \`AnnotationJmxAttributeSource\`: đọc annotations.
- \`MetadataMBeanInfoAssembler\`: tạo metadata MBean.
- \`MetadataNamingStrategy\`: chọn ObjectName khi dùng annotation metadata.
- \`MBeanExporter\`: đăng ký MBeans vào server.
- \`@EnableMBeanExport\` hoặc \`<context:mbean-export />\`: kích hoạt cấu hình annotation-driven.

Nếu một bean có proxy do AOP, Transactional hoặc các cơ chế khác, exporter cần nhận diện metadata từ class/target phù hợp. Khi refactor class hoặc interface, cần kiểm tra hiệu lực của annotation qua metadata thực tế, đặc biệt nếu chuyển \`@ManagedAttribute\` giữa interface và implementation.

Không nên chỉ kiểm tra Java reflection trên class mà bỏ qua cách Spring assembler xử lý proxy.

**Nguyên tắc:** Contract JMX cần được xác nhận từ \`MBeanInfo\` sau khi Spring đã export, vì đó là kết quả cuối cùng mà client tiêu thụ.

## 12. Trường hợp nên duy trì accessor cũ lâu dài

Giữ một accessor quản trị tên cũ thường hợp lý khi:

- Tên đã được công bố trong runbook hoặc hệ thống giám sát quan trọng.
- Nhiều team/đơn vị tiêu thụ JMX và không thể nâng cấp đồng thời.
- Attribute đang dùng trong alerting, automation hoặc SRE playbook.
- Tên cũ dù không còn khớp cách gọi nội bộ nhưng vẫn ổn định và không sai ngữ nghĩa.
- Chi phí giữ wrapper getter rất nhỏ so với rủi ro phá compatibility.

Ví dụ service đã đổi terminology từ “job” sang “task”, nhưng \`CompletedJobs\` vẫn là một metric quản trị phổ biến. Nếu ý nghĩa không thay đổi, giữ tên quản trị cũ có thể là lựa chọn tốt.

Nếu ngữ nghĩa thực sự thay đổi, không nên đánh tráo nội dung dưới tên cũ. Hãy công bố attribute mới và migration minh bạch.

## 13. Anti-pattern: refactor class và đổi JMX contract cùng lúc

Một thay đổi như sau có thể gây lỗi:

**Trước:**

\`\`\`java
@ManagedAttribute
public int getActiveSessions() { ... }
\`\`\`

**Sau:**

\`\`\`java
@ManagedAttribute
public int getOpenConnections() { ... }
\`\`\`

Nếu consumer đang đọc \`ActiveSessions\`, toàn bộ dashboard hoặc script có thể ngừng lấy dữ liệu ngay khi deploy.

Cách an toàn khi cùng giá trị:

\`\`\`java
@ManagedAttribute
public int getActiveSessions() {
    return countOpenConnections();
}

public int countOpenConnections() {
    // Implementation có thể được refactor riêng.
    return connectionRegistry.activeCount();
}
\`\`\`

Trong quá trình chuyển đổi tên, nếu muốn công bố cả hai, annotate accessor mới với ý thức rằng đây là mở rộng management API.

**Cần phân biệt:** Khi hai thuật ngữ không còn tương đương về nghiệp vụ, tạo alias trá hình có thể dẫn đến dữ liệu sai. Trong trường hợp đó cần xác định lại contract và tiến hành versioned migration hoặc thông báo breaking change.

## 14. Kiểm tra khi refactor ManagedAttribute

Bảng kiểm chứng:

| Câu hỏi | Cách kiểm tra |
|---|---|
| ObjectName có thay đổi không? | So sánh tên trước/sau export |
| Attribute tên cũ còn tồn tại không? | \`getMBeanInfo().getAttributes()\` |
| Type có giữ nguyên không? | \`MBeanAttributeInfo.getType()\` |
| Readable/writable có giữ nguyên không? | \`isReadable()\`, \`isWritable()\` |
| Semantics và đơn vị có giữ nguyên không? | Đọc giá trị với dữ liệu kiểm chứng |
| Có client ngoài repository sử dụng chuỗi tên cũ không? | Tra monitoring rules, scripts, runbooks |
| Có alias mới không? | Kiểm tra metadata và documentation |
| Có proxy/assembler thay đổi do refactor không? | Quan sát MBeanInfo sau khi khởi động Spring context |
| Có thao tác quản trị nhạy cảm mới xuất hiện không? | Review surface JMX và quyền truy cập |

Với thay đổi chỉ nằm trong code nội bộ, nếu tất cả yếu tố trên vẫn ổn định, JMX contract không thay đổi.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| \`AttributeNotFoundException\` sau deploy | Getter được rename khiến attribute đổi tên | Giữ compatibility getter hoặc cập nhật consumer theo migration |
| JConsole hiển thị attribute mới nhưng mất tên cũ | Refactor trực tiếp accessor annotated | Đặt accessor adapter tên cũ |
| Dashboard mất series | JMX exporter mapping tham chiếu attribute cũ | Khôi phục contract hoặc cập nhật mapping có kiểm soát |
| Client ép kiểu lỗi | Getter đổi \`int\` sang \`long\` hoặc Open Type khác | Kiểm tra type/semantics trong MBeanInfo |
| Attribute thành writable ngoài ý muốn | Setter mới được annotate | Review read/write metadata và phân quyền |
| Getter được annotate nhưng không hiện | Bean chưa export, annotation bị mất qua refactor/proxy hoặc assembler khác | Kiểm tra MBeanExporter và MBeanInfo |
| Đổi \`@ManagedAttribute(name=...)\` không compile | Annotation không có phần tử \`name\` | Dùng accessor ổn định hoặc metadata strategy tùy biến |
| Client dùng đúng tên nhưng sai MBean | ObjectName đổi hoặc kết nối sai JVM | Kiểm tra ObjectName, MBeanServer và connector |
| Hai attributes cùng nghĩa nhưng kết quả khác | Alias được thực hiện không đồng nhất | Cho cả hai gọi chung một nguồn dữ liệu, kiểm tra semantics |
| Xóa alias quá sớm | Consumer chưa được di chuyển | Dùng kế hoạch deprecation/migration rõ |

## 16. Bài tập thực hành

### Bài tập 1 — Dự đoán attribute name

Cho các phương thức:

\`\`\`java
@ManagedAttribute
public int getPendingJobs() { return 10; }

@ManagedAttribute
public boolean isPaused() { return false; }

@ManagedAttribute
public long getTotalErrors() { return 5L; }
\`\`\`

Hãy dự đoán tên attributes.

**Đáp án:** \`PendingJobs\`, \`Paused\`, \`TotalErrors\`.

### Bài tập 2 — Refactor không phá compatibility

Ban đầu có:

\`\`\`java
@ManagedAttribute
public int getCurrentConnections() {
    return pool.getActiveCount();
}
\`\`\`

Yêu cầu đổi interface service để gọi \`activeConnectionCount()\` nhưng JMX client vẫn đọc \`CurrentConnections\`.

**Hướng làm:** Giữ \`getCurrentConnections()\` làm compatibility accessor, bên trong gọi method service mới. Không cần đổi tên attribute.

### Bài tập 3 — Phát hiện breaking change

Một patch đổi:

\`\`\`java
@ManagedAttribute
public long getRequestCount() { ... }
\`\`\`

thành:

\`\`\`java
@ManagedAttribute
public long getProcessedRequests() { ... }
\`\`\`

Hãy mô tả ảnh hưởng với client đang gọi \`getAttribute(name, "RequestCount")\`. Đề xuất hai phương án chuyển đổi:

1. Giữ getter \`getRequestCount()\` làm compatibility layer.
2. Trong giai đoạn migration, công bố cả \`RequestCount\` và \`ProcessedRequests\`; thông báo thời hạn loại bỏ tên cũ.

### Bài tập 4 — Test contract

Viết một phép kiểm chứng từ \`MBeanInfo\` để bảo đảm \`QueueDepth\` vẫn là attribute \`int\` chỉ đọc. Sau đó cố tình rename getter và quan sát test thất bại; sửa bằng adapter.

### Bài tập 5 — Phân tích thiết kế

Một team muốn đổi \`getCpuUsagePercent()\` thành \`getCpuUsage()\` và đồng thời đổi giá trị trả về từ 0–100 sang 0–1.

Hãy trả lời: vì sao đây không chỉ là rename? Bạn sẽ giữ tên cũ, giới thiệu attribute mới và tài liệu hóa đơn vị thế nào để client không hiểu nhầm?

## 17. Kết luận

- **Tên JMX attribute là một phần của management API contract.**
- Trong Spring \`@ManagedAttribute\`, tên thường được suy ra từ getter/setter method theo quy tắc JavaBeans/JMX.
- Refactor method được annotate có thể làm đổi attribute name dù business logic không đổi.
- \`@ManagedAttribute\` không cung cấp tham số \`name\` để đổi tên attribute tùy ý.
- Giữ một **management facade/compatibility accessor** giúp refactor code nội bộ mà vẫn duy trì tên JMX ổn định.
- Khi muốn đổi contract, dùng migration có chủ đích thay vì đổi tên âm thầm.
- Kiểm chứng thật sự bằng \`MBeanInfo\` sau khi Spring exporter đã chạy và đối chiếu các client phụ thuộc.

## Tài liệu tham khảo

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework ManagedAttribute API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework MetadataMBeanInfoAssembler API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Java SE 21 MBeanAttributeInfo API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 MBeanServer API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
