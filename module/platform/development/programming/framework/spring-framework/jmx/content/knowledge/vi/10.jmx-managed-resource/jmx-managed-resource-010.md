# Khi nên chọn interface thay cho @ManagedResource trong Spring Framework JMX

## Mục tiêu

Spring Framework cung cấp nhiều cách xuất Java object thành JMX MBean. Hai cách thường được đặt lên bàn cân là **khai báo giao diện quản trị riêng** (Standard MBean/MXBean interface) và **đánh dấu trực tiếp lớp Spring bean bằng \`@ManagedResource\` cùng các annotation liên quan**. Cả hai đều có thể tạo bề mặt quản trị qua JMX, nhưng chúng dẫn đến những quyết định khác nhau về hợp đồng công khai, sự phụ thuộc vào Spring, tính tương thích, khả năng test và kiểm soát những method được phép xuất.

Câu hỏi “khi nào nên chọn interface thay cho \`@ManagedResource\`?” thực chất là hỏi: **giao diện quản trị có phải một hợp đồng độc lập cần được thiết kế và duy trì dài hạn hay chỉ là khả năng quan sát/phụ trợ cho một Spring bean?**

Sau bài học, bạn có thể:

- Phân biệt Standard MBean interface, MXBean interface và Spring \`@ManagedResource\`.
- Nhận biết khi nào cần hợp đồng API quản trị ổn định, độc lập với implementation.
- Đánh giá hiệu quả của interface đối với giới hạn bề mặt quản trị, giảm coupling và định nghĩa kiểu dữ liệu JMX.
- Thiết kế Standard MBean hoặc MXBean và đăng ký đúng qua MBeanServer/Spring exporter.
- Chọn annotation khi mục tiêu là expose vài thuộc tính hoặc operation thuộc một Spring bean cụ thể.
- Xử lý xung đột tên, kế thừa interface, proxy Spring, điều khiển runtime và vấn đề bảo mật.
- Xây dựng checklist ra quyết định phù hợp với kiến trúc và vòng đời ứng dụng.

## 1. Hai con đường xuất MBean

### 1.1 Giao diện JMX tường minh

Standard MBean dùng quy ước tên interface \`<ClassName>MBean\`. Ví dụ:

\`\`\`java
package com.example.operations;

public interface ImportWorkerMBean {
    String getState();
    long getCompletedJobs();
    void requestPause();
    void requestResume();
}
\`\`\`

\`\`\`java
package com.example.operations;

public class ImportWorker implements ImportWorkerMBean {
    private volatile String state = "RUNNING";
    private volatile long completedJobs;

    @Override
    public String getState() {
        return state;
    }

    @Override
    public long getCompletedJobs() {
        return completedJobs;
    }

    @Override
    public void requestPause() {
        state = "PAUSE_REQUESTED";
    }

    @Override
    public void requestResume() {
        state = "RESUME_REQUESTED";
    }
}
\`\`\`

Khi object được đăng ký dưới một \`ObjectName\` vào \`MBeanServer\`, JMX Standard MBean introspection nhận diện những attribute/operation được định nghĩa trong \`ImportWorkerMBean\`. Một method public khác nằm trong \`ImportWorker\` nhưng không được khai báo trên interface quản trị thường **không tự trở thành thành viên JMX** theo cách export Standard MBean.

Điểm giá trị nhất: **interface trở thành danh sách được phép công bố**. Người đọc chỉ cần xem hợp đồng để biết bề mặt quản trị bao gồm những gì.

### 1.2 Annotation của Spring

Với cách annotation, lớp Spring bean trực tiếp mô tả những thành phần cần xuất:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.operations:type=Worker,name=Import")
public class ImportWorkerMonitor {

    private volatile String state = "RUNNING";

    @ManagedAttribute
    public String getState() {
        return state;
    }

    @ManagedOperation
    public void requestPause() {
        state = "PAUSE_REQUESTED";
    }

    // Không được đánh dấu để xuất qua annotation.
    public void internalReconcile() {
        // Logic nội bộ.
    }
}
\`\`\`

Spring exporter dùng metadata annotation để xây dựng MBean phù hợp. \`@ManagedResource\` thường đi cùng \`@ManagedAttribute\`, \`@ManagedOperation\` và các annotation mô tả parameter. Cách này thuận tiện khi bean đã thuộc Spring context và số mục quản trị cần công bố tương đối ít.

Cả hai cách đều có thể cho JConsole hoặc công cụ quản trị nhìn thấy attribute và operation. **Khác biệt chủ đạo nằm ở cách biểu diễn và quản lý hợp đồng**: interface riêng hay metadata nằm cùng implementation.

## 2. Bảng so sánh định hướng lựa chọn

| Tiêu chí | Interface MBean/MXBean | Spring annotation \`@ManagedResource\` |
|---|---|---|
| Vị trí hợp đồng | Một interface riêng | Trực tiếp trên implementation/bean |
| Phụ thuộc Spring ở API | Có thể không cần | Phụ thuộc annotation của Spring |
| Khả năng tái sử dụng ngoài Spring | Tốt | Cần Spring exporter hoặc chuyển đổi metadata |
| Kiểm soát thành viên được công bố | Rõ qua chữ ký interface | Rõ qua các method được annotation |
| Tài liệu API | Tập trung tại interface, có thể có Javadoc | Phân tán cùng code implementation và annotation |
| Phát triển nhiều implementation | Tự nhiên | Phải đồng bộ annotation/metadata qua các lớp |
| Tương thích phiên bản và consumer lâu dài | Dễ quản lý như public contract | Có thể làm tốt, nhưng phụ thuộc cách quản lý annotation |
| Cấu hình ObjectName | Trong cơ chế register/naming | Có thể khai báo ở \`@ManagedResource\` |
| Dữ liệu cấu trúc từ remote client | MXBean có Open Type mapping | Phụ thuộc kiểu được export và assembler |
| Độ dài code ban đầu | Thêm interface và implementation | Ngắn gọn khi có vài member |
| Ứng dụng điển hình | Shared management contract, library, API ổn định | Monitoring nội bộ một Spring bean |

Không có quy tắc “interface luôn tốt hơn annotation” hoặc ngược lại. Chọn theo **mức ổn định và quyền sở hữu của giao diện quản trị**.

## 3. Khi nào nên chọn interface?

### 3.1 Khi JMX là hợp đồng công khai hoặc cần duy trì nhiều phiên bản

Nếu nhiều dashboard, script, agent giám sát hoặc nhóm vận hành phụ thuộc vào API JMX, nên thiết kế nó giống một hợp đồng phần mềm:

\`\`\`java
public interface CacheOperationsMBean {
    long getHitCount();
    long getMissCount();
    String getEffectiveMode();
    boolean requestRefresh(String cacheName);
}
\`\`\`

Một interface độc lập cho phép kiểm tra chữ ký trong code review. Đổi \`getHitCount()\` thành \`getHits()\` có thể làm client quản trị hỏng; đổi \`requestRefresh(String)\` thành \`requestRefresh(long)\` thay đổi signature JMX. Khi hợp đồng được định nghĩa riêng, thay đổi này trở nên dễ nhận thấy hơn, và người dùng API có thể triển khai kiểm thử tính tương thích.

Với annotation, cùng sự thay đổi vẫn nguy hiểm nhưng có thể bị che giữa các refactor của service nếu nhóm phát triển xem annotation là chi tiết implementation.

**Dấu hiệu nên chọn interface:** bộ JMX được tài liệu hóa, được script khác gọi và có yêu cầu ổn định giữa các đợt deploy.

### 3.2 Khi cần tách API quản trị khỏi implementation hoặc framework

Một thư viện Java có thể cần chạy trong Spring, plain Java hoặc runtime khác. Nếu interface quản trị không nhập các annotation Spring, thư viện dễ dùng hơn:

\`\`\`java
package com.example.library.management;

public interface SchedulerStatusMXBean {
    int getActiveTasks();
    int getQueuedTasks();
    String getCurrentMode();
}
\`\`\`

Implementation có thể dùng công cụ nội bộ, còn ứng dụng tích hợp quyết định đăng ký vào MBeanServer nào. Đối với MXBean, giao diện có thể tuân theo quy ước hậu tố \`MXBean\` hoặc đánh dấu bằng \`@MXBean\` trong Java Management API. Khi dùng loại dữ liệu hỗ trợ MXBean mapping, remote client có thể đọc Open Type mà ít phụ thuộc vào class implementation riêng.

Điểm cần lưu ý: **Standard MBean interface không đồng nghĩa MXBean**. Standard MBean cho phép chữ ký Java thông thường, nhưng những DTO tùy biến có thể gây khó khăn với remote JMX client. Nếu tính tương tác từ xa là tiêu chí lớn, đánh giá MXBean và Open MBean types.

### 3.3 Khi có nhiều implementation của cùng một hợp đồng

Ví dụ ứng dụng có nhiều engine thực hiện xử lý công việc:

\`\`\`java
public interface WorkerControlMXBean {
    String getState();
    int getConcurrency();
    boolean requestPause();
    boolean requestResume();
}
\`\`\`

Các lớp \`KafkaWorkerControl\`, \`DatabasePollerControl\` hoặc \`FileImportWorkerControl\` có thể cùng triển khai interface. Operator nhìn thấy một bộ operation giống nhau, dù cách xử lý bên trong khác nhau.

Khi dùng MXBean convention hoặc chuẩn đăng ký phù hợp, tên implementation không cần trùng tên interface theo quy tắc Standard MBean cụ thể. Với Standard MBean, nếu interface không theo tên \`ImplementationClassNameMBean\`, có thể đăng ký qua \`StandardMBean\` wrapper và chỉ rõ interface.

\`\`\`java
import javax.management.StandardMBean;

WorkerControl implementation = new WorkerControl();
StandardMBean mbean =
    new StandardMBean(implementation, WorkerControlMBean.class);
server.registerMBean(mbean, objectName);
\`\`\`

Trong ví dụ, \`WorkerControl\` là implementation của \`WorkerControlMBean\`; wrapper giúp JMX biết chính xác interface quản trị cần dùng, kể cả khi tên lớp không theo quy ước thông thường.

### 3.4 Khi muốn bảo đảm bề mặt quản trị không mở rộng vô tình

Một service có thể có hàng chục method public nhưng chỉ một vài method được phép gọi qua JMX. Một interface nhỏ giúp thể hiện giới hạn rõ:

\`\`\`java
public interface InvoiceProcessorMBean {
    long getProcessedCount();
    String getState();
}
\`\`\`

Các method như \`reprocessPayment\`, \`deleteInvoice\` và \`alterAccount\` không nằm trong hợp đồng MBean. Cần kiểm tra chính sách export thực tế để bảo đảm chỉ interface này được công bố. Bản thân interface giúp giảm nguy cơ công bố ngoài ý muốn, nhưng không tự thay thế authentication/authorization của JMX connector.

### 3.5 Khi cần code review tập trung vào thay đổi API quản trị

Ở một số dự án, thay đổi domain service và thay đổi JMX API có vòng đời duyệt khác nhau. Interface riêng hỗ trợ:

- Đối chiếu diff của management contract.
- Bổ sung Javadoc về ý nghĩa, tiền điều kiện và đơn vị số liệu.
- Bảo trì script hoặc test client dựa trên signature.
- Đặt chính sách versioning cho operation và attribute.
- Giảm áp lực giữ annotation cũ trong domain class khi refactor nội bộ.

Điều này đặc biệt hữu ích nếu interface có thay đổi hiếm, còn implementation liên tục được tối ưu.

## 4. Khi nào @ManagedResource phù hợp hơn?

Annotation thường hợp lý khi:

1. Bề mặt JMX nhỏ và chỉ phục vụ việc theo dõi một bean Spring.
2. Không có consumer bên ngoài đòi hỏi hợp đồng quản trị dùng chung.
3. Bean chỉ chạy bên trong Spring application, không cần reuse ngoài container.
4. Việc bổ sung description, attribute và operation qua annotation giúp code dễ hiểu ngay tại chỗ.
5. Dự án đã thống nhất một cơ chế Spring JMX exporter và có kiểm soát naming/lifecycle rõ ràng.

Ví dụ một cache monitor chỉ có vài metric:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.cache:type=Monitor,name=Catalog",
    description = "Catalog cache monitoring")
public class CatalogCacheMonitor {

    private final AtomicLong hits = new AtomicLong();
    private final AtomicLong misses = new AtomicLong();

    @ManagedAttribute(description = "Cache hits since start")
    public long getHitCount() {
        return hits.get();
    }

    @ManagedAttribute(description = "Cache misses since start")
    public long getMissCount() {
        return misses.get();
    }

    public void hit() {
        hits.incrementAndGet();
    }

    public void miss() {
        misses.incrementAndGet();
    }
}
\`\`\`

Không cần thêm interface chỉ để chứa hai getter nếu mục tiêu là monitoring nội bộ và class không có yêu cầu tương thích riêng. Tuy nhiên nếu script vận hành dùng những tên này lâu dài, annotation vẫn phải được quản lý như public contract.

## 5. Standard MBean, MXBean và Spring annotation khác nhau như thế nào?

### 5.1 Standard MBean

Standard MBean dựa trên interface có hậu tố \`MBean\` theo tên implementation, hoặc wrapper \`StandardMBean\` với interface tường minh.

\`\`\`java
public interface JobMonitorMBean {
    int getRunningJobs();
    void resetStatistics();
}
\`\`\`

\`\`\`java
public class JobMonitor implements JobMonitorMBean {
    @Override public int getRunningJobs() { return 0; }
    @Override public void resetStatistics() { }
}
\`\`\`

Quy tắc thông thường:
- Getter \`getRunningJobs()\` trở thành attribute \`RunningJobs\`.
- \`resetStatistics()\` là operation.
- MBeanServer nhận tên ObjectName khi \`registerMBean\`.

### 5.2 MXBean

MXBean phù hợp khi hợp đồng quản trị cần kiểu dữ liệu có thể ánh xạ theo Open Type. Ví dụ:

\`\`\`java
public interface QueueStatusMXBean {
    String getName();
    int getDepth();
    boolean isPaused();
}
\`\`\`

Lớp implement \`QueueStatusMXBean\` có thể được xuất như MXBean theo quy tắc Java Management API; với kiểu phức tạp, cần bảo đảm mapping được hỗ trợ. MXBean không tự khiến mọi custom DTO đều tương thích; quy tắc ánh xạ phải được tuân thủ.

### 5.3 Spring annotation

Spring \`@ManagedResource\` mô tả MBean ở cấp lớp; \`@ManagedAttribute\` và \`@ManagedOperation\` chỉ rõ member cần xuất. \`AnnotationMBeanExporter\` sử dụng metadata đó cùng naming strategy.

Ví dụ cùng khái niệm nhưng khác cơ chế:

\`\`\`text
Standard MBean:
  interface + implementation
  └── MBeanServer / exporter đăng ký

MXBean:
  MXBean interface + implementation
  └── JMX Open Type mapping

Spring annotation:
  @ManagedResource + @ManagedAttribute/@ManagedOperation
  └── AnnotationMBeanExporter xử lý metadata
\`\`\`

Quan trọng: interface và annotation không nhất thiết loại trừ nhau. Spring có thể export object đã implement Standard MBean/MXBean qua cơ chế phù hợp; một hệ thống cũng có thể dùng interface làm hợp đồng, còn annotation ở adapter riêng cho mục đích khác. Tuy vậy, đừng để **hai cơ chế cùng đăng ký cùng ObjectName** vào một MBeanServer mà không có ownership rõ ràng.

## 6. Ví dụ thực tế: tách WorkerService khỏi JMX interface

Trong ứng dụng có nhiều logic nghiệp vụ, một thiết kế tốt là giữ service tập trung xử lý nghiệp vụ, còn adapter công bố một giao diện quản trị nhỏ.

### 6.1 Service nội bộ

\`\`\`java
import java.util.concurrent.atomic.AtomicBoolean;

public final class WorkerService {

    private final AtomicBoolean pauseRequested = new AtomicBoolean();

    public boolean isPauseRequested() {
        return pauseRequested.get();
    }

    public void requestPause() {
        pauseRequested.set(true);
    }

    public void requestResume() {
        pauseRequested.set(false);
    }

    public long getCompletedJobs() {
        return 0L; // Minh họa, giá trị thật lấy từ thống kê worker.
    }

    // Các operation nghiệp vụ không thuộc API JMX.
    public void processNextBatch() {
        // xử lý công việc
    }
}
\`\`\`

### 6.2 Interface quản trị

\`\`\`java
public interface WorkerAdminMBean {
    boolean isPauseRequested();
    long getCompletedJobs();
    void requestPause();
    void requestResume();
}
\`\`\`

### 6.3 Adapter triển khai interface

\`\`\`java
public final class WorkerAdmin implements WorkerAdminMBean {

    private final WorkerService worker;

    public WorkerAdmin(WorkerService worker) {
        this.worker = worker;
    }

    @Override
    public boolean isPauseRequested() {
        return worker.isPauseRequested();
    }

    @Override
    public long getCompletedJobs() {
        return worker.getCompletedJobs();
    }

    @Override
    public void requestPause() {
        worker.requestPause();
    }

    @Override
    public void requestResume() {
        worker.requestResume();
    }
}
\`\`\`

### 6.4 Đăng ký adapter

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

WorkerService worker = new WorkerService();
WorkerAdmin admin = new WorkerAdmin(worker);

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.workers:type=WorkerAdmin,name=Import");

server.registerMBean(admin, name);
\`\`\`

Sau khi đăng ký, client JMX có thể đọc attribute \`PauseRequested\`, \`CompletedJobs\` và gọi operation \`requestPause\`, \`requestResume\`, nhưng không có đường JMX để gọi \`processNextBatch\` chỉ vì method này public trong service.

Trong ứng dụng Spring thật, hãy dùng cơ chế lifecycle phù hợp để đăng ký và unregister. Nếu service hoặc adapter được tạo như Spring bean, \`MBeanExporter\` có thể quản lý registration; nếu đăng ký thủ công như trên, component tự chịu trách nhiệm cleanup.

## 7. Interface không có nghĩa phải expose cả domain service

Một thiết kế dễ mắc lỗi:

\`\`\`java
public interface FullPaymentServiceMBean {
    void chargeCard(String accountId, long amount);
    void refund(String paymentId);
    void deletePayment(String paymentId);
    long getProcessedCount();
}
\`\`\`

Dù là interface riêng, nó vẫn xuất các operation có tác động nghiệp vụ rất lớn. Kỹ thuật tách interface giúp nhìn rõ rủi ro, nhưng không tự bảo đảm an toàn.

Hợp đồng quản trị tốt thường giới hạn ở:
- Quan sát trạng thái, chỉ số và health summary.
- Chẩn đoán có giới hạn.
- Điều khiển runtime với phạm vi rõ và quyền hạn phù hợp.

Không nên dùng JMX thay thế API nghiệp vụ chuẩn cho thanh toán, sửa dữ liệu hoặc các thao tác cần kiểm soát giao dịch. Nếu buộc phải có operation thay đổi trạng thái, cần xác thực, phân quyền, audit, tiền điều kiện và khả năng quan sát kết quả.

## 8. Tương thích JMX và versioning khi dùng interface

Một interface quản trị là API công bố ra bên ngoài. Thay đổi Java method có thể tác động đến:
- Tên JMX attribute: \`getCurrentState()\` thành \`getState()\` có thể đổi \`CurrentState\` thành \`State\`.
- Tên operation: \`pause()\` thành \`requestPause()\`.
- Signature: \`setLimit(int)\` thành \`setLimit(long)\`.
- Return type: client đang cast \`Integer\` nhưng nay nhận \`Long\`.
- ObjectName: dashboard trỏ vào domain hoặc key properties cũ.
- Phạm vi dữ liệu: metric đổi đơn vị từ milliseconds sang seconds dù tên không đổi.

Một cách quản lý:
1. Định nghĩa interface riêng với Javadoc về đơn vị, nullability và tác dụng phụ.
2. Có integration test đọc \`MBeanInfo\` để xác minh thuộc tính/operation được công bố.
3. Tránh đổi nghĩa lặng lẽ của attribute.
4. Với thay đổi phá vỡ tương thích, cân nhắc interface/ObjectName version mới hoặc giai đoạn chuyển đổi có chủ đích.
5. Phối hợp cập nhật monitoring, script và runbook.

Annotation vẫn có thể đạt mức ổn định này nếu được quản lý có kỷ luật, nhưng interface riêng làm ranh giới hợp đồng dễ kiểm tra hơn.

## 9. Spring AOP proxy và Java interface

Trong Spring, bean có thể bị proxy vì \`@Transactional\`, \`@Async\`, AOP advice hoặc cơ chế khác. Điều đó ảnh hưởng cách exporter nhìn thấy class và interface.

Ví dụ:
\`\`\`text
WorkerService (target)
    ^
    |
JDK dynamic proxy (implements WorkerServiceApi)
    |
Spring bean được export
\`\`\`

Nếu chỉ dùng interface JMX trên implementation, cần kiểm tra proxy thực tế có expose đúng interface hay không. JDK dynamic proxy chỉ công bố các interface đã được proxy triển khai; CGLIB subclass proxy có thể có đặc tính khác. Spring \`MBeanExporter\` hỗ trợ các chiến lược export, nhưng không nên suy luận mọi proxy đều tương thích với mọi quy ước Standard MBean.

Thiết kế adapter quản trị riêng, ít bị proxy phức tạp, thường làm hợp đồng JMX ổn định hơn:

\`\`\`text
Spring service (có transactional/AOP)
      ^
      |
WorkerAdmin implements WorkerAdminMBean
      |
MBeanServer
\`\`\`

Adapter gọi service nội bộ qua dependency, thay vì xuất trực tiếp service chứa nhiều advice. Nếu service operation cần transactional boundary, nó vẫn được gọi qua Spring proxy đúng cách khi dependency injection đưa đúng proxy vào adapter.

## 10. Các kiểu dữ liệu trên interface: dùng cho remote JMX

Interface quản trị không chỉ cần “compile được”, mà còn cần dữ liệu mà JMX client có thể hiểu.

Nên ưu tiên:
- \`String\`, \`boolean\`, \`int\`, \`long\`, \`double\` và các array/collection được MXBean mapping hỗ trợ.
- \`CompositeData\`, \`TabularData\` khi cần dữ liệu cấu trúc theo Open MBean.
- Thông tin trạng thái rõ đơn vị, giới hạn và timestamp.

Cần thận trọng với:
- Entity/DTO nội bộ có vòng đời thay đổi.
- Stream, object chứa executor hoặc tài nguyên không serialize được.
- Graph lồng sâu hoặc collection không giới hạn.
- Payload có password, token hay thông tin khách hàng.
- Interface trả \`Object\` không xác định schema.

Ví dụ một MXBean công bố trạng thái đơn giản:

\`\`\`java
public interface ConnectionPoolStatusMXBean {
    int getActiveConnections();
    int getIdleConnections();
    int getMaxConnections();
    String getPoolName();
}
\`\`\`

Với một remote client, các kiểu này ổn định hơn việc phải load \`ConnectionPoolImpl\` hoặc DTO đặc thù. Nếu cần trường phức tạp, thiết kế Open Type contract có chủ đích.

## 11. Test contract JMX theo interface

Một integration test có thể kiểm tra interface quản trị khi đăng ký:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.*;

import org.junit.jupiter.api.Test;

class WorkerAdminMBeanTest {

    @Test
    void exposesExpectedManagementContract() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.test:type=WorkerAdmin,name=Sample");

        WorkerAdmin adapter =
            new WorkerAdmin(new WorkerService());

        try {
            server.registerMBean(adapter, name);
            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(server.isRegistered(name));
            assertTrue(
                java.util.Arrays.stream(info.getAttributes())
                    .anyMatch(a -> a.getName().equals("CompletedJobs")));
            assertTrue(
                java.util.Arrays.stream(info.getOperations())
                    .anyMatch(o -> o.getName().equals("requestPause")));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }
    }
}
\`\`\`

Trong test thật, cần tránh chạy song song với test khác có cùng \`ObjectName\`; nên dùng MBeanServer riêng hoặc namespace test được kiểm soát. Đừng cleanup MBean chỉ dựa trên tên nếu test không sở hữu registration ấy. Ví dụ này minh họa test contract; các điều kiện ownership cần áp dụng trước khi dùng trong môi trường có shared server.

Có thể mở rộng test để xác minh operation signature qua \`MBeanOperationInfo.getSignature()\` và kiểu trả về qua \`getReturnType()\`, giúp phát hiện các thay đổi ảnh hưởng đến automation.

## 12. Mẫu ra quyết định

Trước khi chọn giao diện hoặc annotation, hãy hỏi:

| Câu hỏi | Nếu câu trả lời là “có” |
|---|---|
| Có script, agent hoặc dashboard ngoài ứng dụng phụ thuộc API này không? | Nghiêng về interface |
| Có cần dùng cùng management contract trong nhiều implementation không? | Nghiêng về interface |
| Thư viện cần chạy ngoài Spring không? | Nghiêng về interface |
| Có yêu cầu giữ hợp đồng ổn định qua nhiều release không? | Nghiêng về interface |
| Có dữ liệu quản trị phức tạp cần Open Type mapping không? | Xem xét MXBean |
| Chỉ cần vài metric trên một Spring bean duy nhất? | Annotation thường gọn |
| Management code thuộc một component rất nhỏ và nội bộ? | Annotation có thể đủ |
| Bean bị proxy AOP phức tạp hoặc chứa nhiều API nghiệp vụ? | Nghiêng về adapter + interface |
| Người vận hành cần nhận diện rõ tập lệnh có thể gọi? | Interface tường minh có lợi |
| ObjectName và quyền truy cập là yêu cầu quan trọng? | Cả hai phương pháp đều phải thiết kế cẩn thận |

### 12.1 Quy tắc quyết định thực tế

**Chọn interface** nếu bề mặt JMX có tính chất của **API hợp đồng**: sống lâu, có nhiều consumer, cần tích hợp ngoài Spring hoặc cần interface được kiểm soát chặt. **Chọn annotation** nếu nó là một phần cấu hình quản trị cục bộ của một bean Spring, ít member và không tạo ra phụ thuộc lâu dài ở bên ngoài. Khi cần kiểu dữ liệu remote client dễ sử dụng, cân nhắc **MXBean** riêng thay vì Standard MBean có các DTO tùy ý.

Quy tắc này không phụ thuộc việc “interface có nhiều dòng code hơn”. Chi phí bảo trì từ một API thiếu ranh giới thường lớn hơn vài lớp interface/adapter bổ sung.

## 13. Các nhầm lẫn phổ biến

### “Có @ManagedResource thì không thể dùng interface”

Sai. Một ứng dụng có thể vừa dùng interface để định nghĩa contract, vừa dùng Spring để quản lý lifecycle đăng ký. Tuy nhiên cần chọn một registration path rõ ràng, tránh đồng thời xuất cùng một object dưới cùng ObjectName bằng hai cơ chế khác nhau.

### “Interface tự đăng ký MBean”

Sai. Interface chỉ định nghĩa hợp đồng. Cần có implementation và bước đăng ký qua MBeanServer hoặc exporter tương ứng; \`ObjectName\` phải hợp lệ và duy nhất trong server.

### “MXBean chỉ là Standard MBean đổi tên”

Sai. MXBean áp dụng những quy tắc mapping kiểu Java sang Open Types để cải thiện khả năng tương tác từ xa. Không phải mọi kiểu Java đều được ánh xạ tự do.

### “Mọi public method trên class implement interface đều hiện ở JMX”

Sai trong mô hình Standard MBean dựa trên management interface. Những thành viên có mặt trong interface quản trị mới là bề mặt chính của hợp đồng MBean. Tuy nhiên luôn kiểm tra exporter thực tế và \`MBeanInfo\` vì các cơ chế dynamic/annotation khác có quy tắc riêng.

### “Tách interface là đủ an toàn”

Sai. Cần security ở JMX connector hoặc layer quản lý, giới hạn network, quyền operation, audit và input validation. Interface tách bề mặt công bố nhưng không phải access control.

### “Bất kỳ Spring bean nào cũng nên được export trực tiếp”

Sai. Các service nghiệp vụ thường có quá nhiều phương thức và phụ thuộc. Một management adapter nhỏ giúp kiểm soát hành vi công bố tốt hơn.

## 14. Bài tập vận dụng

**Bài 1 — Chọn cách export.** Một \`CacheStats\` bean chỉ có hai counter, không có external script. Bạn chọn annotation hay interface? Giải thích. Gợi ý: annotation thường đơn giản, miễn là exporter được cấu hình rõ.

**Bài 2 — Contract dài hạn.** Một scheduler có nhiều implementation, dùng chung dashboard vận hành qua 3 năm. Chọn interface vì hợp đồng quản trị cần ổn định và test được; cân nhắc MXBean nếu client từ xa cần dữ liệu cấu trúc.

**Bài 3 — Xử lý AOP proxy.** Một \`PaymentService\` bị proxy bởi \`@Transactional\` và có hàng chục public method. Thiết kế \`PaymentMonitorMBean\` adapter chỉ chứa trạng thái, queue và một operation điều khiển có quyền; không export toàn bộ PaymentService.

**Bài 4 — Versioning.** Client cũ gọi \`resetStatistics()\` nhưng interface mới thay thành \`clearCounters()\`. Hãy giải thích vì sao đây là breaking change và đề xuất cách chuyển đổi có kiểm soát.

**Bài 5 — Remote data.** Interface trả \`List<InternalJobEntity>\` với entity chứa lazy loading và thông tin nhạy cảm. Hãy thay bằng summary bounded hoặc cấu trúc MXBean/OpenType an toàn và giải thích lựa chọn.

## Tổng kết

**Nên chọn interface thay cho \`@ManagedResource\` khi JMX cần trở thành một hợp đồng quản trị độc lập, được nhiều consumer sử dụng và duy trì lâu dài.** Standard MBean interface làm rõ danh sách attribute/operation được công bố; MXBean bổ sung cơ chế ánh xạ Open Type hữu ích cho remote client; adapter quản trị giúp tách bề mặt JMX khỏi domain service và tránh coupling với proxy/framework. \`@ManagedResource\` vẫn phù hợp khi chỉ cần vài member quản trị nội bộ trên Spring bean. Trong mọi trường hợp, ObjectName, ownership, lifecycle, bảo mật và kiểm tra MBeanInfo vẫn là những yêu cầu thiết kế riêng cần được thực hiện.
