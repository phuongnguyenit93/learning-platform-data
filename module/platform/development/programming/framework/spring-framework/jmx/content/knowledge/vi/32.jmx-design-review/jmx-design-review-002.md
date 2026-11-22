# Chọn Standard MBean, MXBean, annotation hay assembler trong Spring Framework JMX

## 1. Mục tiêu bài học

Bài học này giúp bạn ra quyết định kiến trúc khi muốn đưa trạng thái và thao tác quản trị của ứng dụng Spring Framework ra Java Management Extensions (JMX). Sau khi học, bạn có thể:

- Phân biệt **Standard MBean**, **MXBean**, **Spring annotation-driven JMX** và **MBeanInfoAssembler**.
- Giải thích vì sao “annotation” và “assembler” không hoàn toàn là hai loại MBean độc lập ngang hàng với Standard MBean/MXBean.
- Đánh giá các lựa chọn dựa trên client, kiểu dữ liệu, tính ổn định của management API, phạm vi công bố, bảo mật, AOP proxy và chi phí vận hành.
- Hiểu ranh giới giữa \`MBeanExporter\`, \`MBeanServer\`, \`ObjectName\`, metadata assembler, naming strategy và JMX connector.
- Lựa chọn cấu hình rõ ràng cho Spring Framework thuần và Spring Boot mà không tạo exporter trùng.
- Xây dựng thử nghiệm \`MBeanInfo\` và runtime invocation để xác minh phương án được chọn.

## 2. Trước tiên: đây không phải bốn cơ chế loại trừ lẫn nhau

Câu hỏi “Chọn Standard MBean, MXBean, annotation hay assembler?” rất dễ dẫn đến nhầm lẫn vì bốn thuật ngữ nằm ở **hai tầng khác nhau**:

| Thuật ngữ | Tầng | Chức năng |
|---|---|---|
| Standard MBean | Hợp đồng quản trị JMX | Định nghĩa attributes/operations bằng interface theo convention |
| MXBean | Hợp đồng quản trị JMX | Định nghĩa interface và dùng quy tắc ánh xạ Java types sang Open MBean types |
| Spring JMX annotations | Metadata khai báo | Dùng \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` để mô tả API quản trị |
| \`MBeanInfoAssembler\` | Cơ chế tạo metadata trong Spring | Xây dựng \`MBeanInfo\` để Spring exporter công bố bean qua JMX |

Vì vậy **annotation-driven export thường sử dụng assembler**. Bạn có thể chọn Standard MBean thuần, MXBean thuần, hoặc công bố Spring bean bằng annotation metadata assembler; cũng có thể tạo một custom assembler cho convention riêng. Không nên xem “assembler” là một kiểu dữ liệu JMX ngang hàng với MXBean.

Sơ đồ:

~~~text
                        Spring bean / Java object
                                  |
                   +--------------+---------------+
                   |              |               |
                   v              v               v
            Standard MBean      MXBean      Spring metadata
             interface          interface   @ManagedResource
                   |              |               |
                   |              |               v
                   |              |         MBeanInfoAssembler
                   |              |               |
                   +--------------+---------------+
                                  |
                                  v
                             MBeanExporter
                                  |
                                  v
                              MBeanServer
                                  |
                                  v
                          ObjectName / MBeanInfo
                                  |
                                  v
                           JMX client / tools
~~~

Sơ đồ mang tính logic: Java code có thể đăng ký Standard MBean/MXBean trực tiếp vào \`MBeanServer\` mà không cần Spring \`MBeanExporter\`. Với Spring exporter, framework có thể sử dụng những cơ chế exposure khác nhau tùy bean và cấu hình. Không phải mọi đường trong sơ đồ đều bắt buộc đi qua một assembler giống nhau.

## 3. Những câu hỏi phải trả lời trước khi chọn

Trước khi viết interface hoặc annotation, hãy xác định:

1. **Ai là client?** JConsole/JMC, Java client proxy, JMX exporter, APM agent hay script?
2. **Kiểu dữ liệu nào?** Chỉ scalar \`int\`, \`long\`, \`boolean\`, \`String\`, hay DTO/collections/snapshot có cấu trúc?
3. **Có remote JMX không?** Nếu có, classloading, serialization và bảo mật quan trọng hơn.
4. **Có cần một management interface Java tường minh không?** API này có được nhiều module/chương trình Java dùng chung không?
5. **Có muốn gắn metadata lên Spring bean hiện hữu?** Hay tách management adapter khỏi business service?
6. **Bean có Spring AOP proxy không?** JDK dynamic proxy hoặc CGLIB có thể ảnh hưởng interface visibility/annotation discovery.
7. **Có cần mô tả attribute và operation chi tiết?** Ví dụ description, units và các metadata mở rộng.
8. **Có cần kiểm soát tập bean được autodetect?** Hay muốn explicit allowlist?
9. **Management contract cần sống qua bao nhiêu phiên bản?** Có dashboard/scripts phụ thuộc ObjectName và types không?
10. **Rủi ro của write operations là gì?** Ai được phép pause worker, clear cache hoặc đổi configuration?

Trả lời các câu hỏi này thường giúp loại ngay một số phương án không phù hợp mà không cần thử ngẫu nhiên nhiều kiểu exporter.

## 4. Standard MBean: hợp đồng Java rõ, quy ước đơn giản

Một Standard MBean có interface quản trị theo convention.

Ví dụ:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

Implementation:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicInteger pending = new AtomicInteger(12);
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pending.get();
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
~~~

Quy ước:

- \`getPendingCount()\` tạo attribute \`PendingCount\`.
- \`isPaused()\` tạo boolean attribute \`Paused\`.
- \`pause()\` và \`resume()\` là JMX operations.

Đăng ký trực tiếp:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.shop.jobs:type=QueueMonitor,name=primary");

server.registerMBean(new QueueMonitor(), name);
~~~

Trong demo, cần cleanup khi kết thúc:

~~~java
server.unregisterMBean(name);
~~~

### Điểm mạnh

- Management contract được biểu diễn bằng Java interface rõ ràng.
- Dễ đọc, dễ tổ chức và dễ review.
- Không yêu cầu Spring annotations trên implementation.
- Phù hợp với các JMX clients có management interface tương thích.
- Phù hợp cho MBeans nhỏ, ít metadata đặc thù.
- Có thể dùng \`JMX.newMBeanProxy()\` để gọi thông qua interface.

### Hạn chế

- Cần tuân thủ JMX naming/compliance rules.
- Interface có thể bị gắn chặt với một implementation nếu thiết kế không tách biệt.
- Custom DTO returns ở Standard MBean có thể gây phụ thuộc classpath/classloader khi remote.
- Việc chỉ có interface không tự quản lý authorization, TLS, audit hoặc registration lifecycle.
- Metadata descriptions nâng cao có thể cần thêm cơ chế khác.

**Khi nên chọn:** Một MBean độc lập, API quản trị nhỏ, kiểu dữ liệu đơn giản, cần Java interface rõ và không muốn phụ thuộc Spring-specific annotations.

## 5. StandardMBean wrapper khi implementation/interface không theo convention

Đôi khi bạn có một interface không tên \`QueueMonitorMBean\` đúng convention hoặc muốn tránh để implementation phải theo tên bắt buộc. Java cung cấp \`StandardMBean\`.

Ví dụ:

~~~java
public interface QueueManagementApi {
    int getPendingCount();
}
~~~

~~~java
public class QueueManagementAdapter implements QueueManagementApi {
    @Override
    public int getPendingCount() {
        return 12;
    }
}
~~~

Có thể bọc:

~~~java
import javax.management.StandardMBean;

QueueManagementApi implementation = new QueueManagementAdapter();

StandardMBean mbean = new StandardMBean(
        implementation,
        QueueManagementApi.class);

server.registerMBean(mbean, name);
~~~

Điều này giúp bạn chủ động chọn management interface mà không phụ thuộc hoàn toàn vào tên implementation. Nếu ứng dụng dùng Spring, vẫn cần một registration owner rõ ràng và có thể giao registration cho Spring exporter thay vì thao tác trực tiếp.

Đừng coi \`StandardMBean\` wrapper là một tính năng versioning tự động. Khi interface thay đổi, client compatibility vẫn cần kiểm tra.

## 6. MXBean: ưu tiên interoperability và OpenType mapping

MXBean cũng dùng management interface nhưng có quy tắc ánh xạ types để tương tác thuận tiện hơn qua JMX, nhất là với clients không có custom application classes.

Một ví dụ:

~~~java
import javax.management.MXBean;

@MXBean
public interface QueueStatsMXBean {
    long getPendingCount();
    String getState();
}
~~~

Implementation:

~~~java
public class QueueStats implements QueueStatsMXBean {

    @Override
    public long getPendingCount() {
        return 12L;
    }

    @Override
    public String getState() {
        return "RUNNING";
    }
}
~~~

MXBean đặc biệt hữu ích khi management API cần các kiểu dữ liệu có thể được chuyển thành Open MBean types như:

- Primitive và boxed primitives theo quy tắc mapping.
- \`String\`.
- Một số arrays và enums.
- Những cấu trúc có thể được biểu diễn bởi \`CompositeData\` hoặc \`TabularData\` theo MXBean mapping.
- Các Java types khác trong phạm vi được JDK hỗ trợ.

**Quan trọng:** Không phải mọi custom class, Java record hoặc generic collection đều tự map thành OpenType hợp lệ trong mọi phiên bản Java. Phải kiểm tra quy tắc MXBean mapping cho type cụ thể và thử registration/runtime access.

Client có thể dùng:

~~~java
QueueStatsMXBean proxy = javax.management.JMX.newMXBeanProxy(
        server,
        name,
        QueueStatsMXBean.class);
~~~

### Điểm mạnh

- Phù hợp cho management APIs cần interoperability qua JMX.
- Open-type representation giúp clients hạn chế phụ thuộc Java application DTO class.
- Tốt cho những snapshot có schema được định nghĩa rõ và mapping hợp lệ.
- Java MXBean proxy có thể xử lý các chuyển đổi type tương ứng.

### Hạn chế

- Quy tắc type mapping có thể gây lỗi khi class không phù hợp.
- Schema của composite data cũng là hợp đồng cần versioning.
- Tùy type, mapping và unmarshalling có thể phát sinh chi phí.
- Không miễn trừ security/authentication/authorization của JMX remote.
- Không tự giải quyết vấn đề một getter thực hiện SQL hoặc I/O nặng.

**Khi nên chọn:** Cần kiểu phức tạp có thể portable, đa dạng Java/JMX clients hoặc muốn giảm sự phụ thuộc vào DTO application bên phía remote client.

## 7. Spring annotation-driven JMX: metadata gần management bean

Spring Framework cung cấp các annotations như:

- \`@ManagedResource\`.
- \`@ManagedAttribute\`.
- \`@ManagedOperation\`.
- \`@ManagedOperationParameter\`.
- \`@ManagedMetric\`.
- \`@ManagedNotification\`.

Ví dụ:

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.jobs:type=WorkerControl,name=primary",
    description = "Worker pool management")
public class WorkerControlManagement {

    private final WorkerPoolMetrics metrics;

    public WorkerControlManagement(WorkerPoolMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Current active workers")
    public int getActiveWorkers() {
        return metrics.activeWorkers();
    }

    @ManagedOperation(description = "Reset diagnostic counters")
    public void resetDiagnosticCounters() {
        metrics.resetDiagnosticCounters();
    }
}
~~~

Ở đây:

1. \`@Component\` đưa class vào Spring ApplicationContext.
2. \`@ManagedResource\` mô tả resource và ObjectName.
3. \`@ManagedAttribute\` mô tả getter trở thành JMX attribute.
4. \`@ManagedOperation\` mô tả operation được công bố.
5. Exporter và assembler phù hợp mới thực hiện registration.

### Điểm mạnh

- Thuận tiện trong Spring application.
- Metadata được khai báo gần code của management adapter.
- Có thể mô tả descriptions và các thuộc tính quản trị khác.
- Dễ kết hợp dependency injection.
- Có thể chọn những methods được công bố thay vì toàn bộ public API.
- Tích hợp với \`AnnotationMBeanExporter\` và metadata assembler.

### Hạn chế

- Phụ thuộc vào Spring JMX export pipeline.
- Chỉ thêm annotation không tự đăng ký MBean.
- Nếu annotation được gắn trực tiếp trên business service, management surface có thể bị trộn với nghiệp vụ.
- Proxy và annotation discovery cần được kiểm tra.
- Cấu hình nhiều exporters có thể gây ObjectName collision.
- Annotations không tự tạo access controls hoặc bảo vệ operations.

**Khi nên chọn:** Ứng dụng Spring có management adapters nhỏ, muốn mô tả API bằng annotations và tận dụng IoC container.

## 8. Assembler thực sự là gì?

\`MBeanInfoAssembler\` trong Spring có nhiệm vụ tạo \`MBeanInfo\` biểu diễn attributes, operations và metadata quản trị. Một assembler có thể dựa trên:

- Interface được chỉ định.
- Naming conventions.
- Source code reflection theo một policy.
- Metadata annotations từ \`JmxAttributeSource\`.
- Custom rules của tổ chức.

Các assembler thường gặp gồm:

| Assembler | Ý tưởng sử dụng |
|---|---|
| \`InterfaceBasedMBeanInfoAssembler\` | Chọn management methods theo interfaces |
| \`MethodNameBasedMBeanInfoAssembler\` | Chọn methods theo tên cho phép |
| \`MethodExclusionMBeanInfoAssembler\` | Công bố methods trừ những tên bị loại |
| \`MetadataMBeanInfoAssembler\` | Dùng management metadata từ \`JmxAttributeSource\` |

Tên class/API và cấu hình chi tiết cần đối chiếu Spring Framework version đang dùng. Không phải mọi assembler đều hỗ trợ autodetection; nếu exporter dùng \`AUTODETECT_ASSEMBLER\`, assembler cần có khả năng đánh giá bean được đưa vào discovery qua \`AutodetectCapableMBeanInfoAssembler\`.

### Khi nào dùng assembler?

Một assembler phù hợp nếu:
- Muốn định nghĩa whitelist attributes/operations tập trung.
- Nhiều beans cùng tuân thủ một convention.
- Không muốn annotate mọi implementation.
- Cần kiểm soát interface/naming-based management contract.
- Muốn dùng \`@Managed...\` metadata trong Spring export pipeline.

**Một assembler không phải public JMX data type.** Nó là một phần của tầng tạo metadata phía Spring, có thể được kết hợp với những approaches khác theo cấu hình cụ thể.

## 9. Cấu hình annotation assembler theo Spring Framework

Đây là một cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ApplicationJmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter jmxExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
~~~

Cấu hình trên làm rõ vai trò từng thành phần. \`AnnotationJmxAttributeSource\` là nguồn metadata; assembler tạo \`MBeanInfo\` và có thể tham gia chọn beans; naming strategy tạo ObjectName; exporter đưa beans vào server.

Đây là **một phương án cấu hình**. Nếu ứng dụng đã dùng \`@EnableMBeanExport\`, \`AnnotationMBeanExporter\` hoặc Spring Boot auto-configuration tạo exporter phù hợp, không tự thêm exporter khác cùng quét resources. Phải xác định một owner cho mỗi ObjectName.

## 10. Annotation so với interface-based assembler

Giả sử business service interface:

~~~java
public interface PaymentStatistics {
    long getSuccessfulPayments();
    long getFailedPayments();
    void resetStatistics();
}
~~~

Bạn có thể tạo management adapter annotate riêng hoặc dùng assembler chọn methods theo interface. Khác biệt:

**Annotation-driven**
- Metadata nằm trên methods/class.
- Có \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` giúp thể hiện ý định rõ.
- Thay đổi API quản trị thường theo class annotations.
- Có thể làm interface nghiệp vụ độc lập JMX nếu dùng adapter.

**Interface-based assembler**
- Tập methods được chọn dựa trên một interface được cấu hình.
- Dễ tách implementation khỏi declaration của management surface.
- Có thể tận dụng interfaces hiện có mà không thêm annotations.
- Vẫn cần naming/exporter/registration configuration.
- Phải kiểm tra getters nào được diễn giải thành attributes và methods nào thành operations.

Nếu business interface có các methods nguy hiểm như \`refundPayment\` hoặc \`deleteAccount\`, không chọn nguyên interface đó làm management interface chỉ vì nó đã tồn tại. Hãy định nghĩa interface chỉ chứa management methods cần thiết.

## 11. Method-name-based assembler: linh hoạt nhưng dễ giòn

Ví dụ bạn muốn công bố:

~~~text
getActiveWorkers
getQueueDepth
resetStatistics
~~~

Một method-name-based assembler có thể dùng allowlist những tên này. Nhưng thiết kế phụ thuộc vào exact method names:

- Rename Java method có thể làm mất JMX attribute.
- Overloaded methods gây cần chú ý signatures.
- Nếu cấu hình theo bean name và nhiều beans dùng một convention, việc thay bean naming có thể làm policy sai.
- Metadata descriptions có thể kém giàu thông tin hơn annotations.
- Client vẫn phụ thuộc vào ObjectName và MBeanInfo cuối cùng.

Cách này phù hợp cho legacy code khi không được thay source để thêm annotations hoặc interface. Với hệ thống mới, một management adapter/interface tường minh thường dễ kiểm toán hơn.

## 12. Chọn phương án theo bảng quyết định

| Tiêu chí | Standard MBean | MXBean | Annotation + metadata assembler | Custom/interface assembler |
|---|---|---|---|---|
| Java management interface tường minh | Bắt buộc theo convention/wrapper | Có | Không bắt buộc | Tùy policy |
| Dễ dùng với Spring IoC | Có, qua exporter | Có, qua exporter | Rất thuận tiện | Có |
| Metadata đặt trên methods | Theo interface/convention | Theo interface/mapping | Dùng annotations | Theo policy |
| Kiểu scalar | Tốt | Tốt | Tốt | Tốt |
| Kiểu phức tạp portable | Cần cân nhắc DTO/classpath | Mạnh nếu open-type mapping hợp lệ | Phụ thuộc type/assembler | Phụ thuộc metadata/type |
| Ít Spring-specific | Tốt | Tốt | Thấp hơn | Thấp hơn |
| Reuse legacy beans | Có thể | Có thể | Cần annotations hoặc adapter | Thường linh hoạt |
| Kiểm soát chọn methods | Interface | Interface | @Managed annotations | Policy/interface/method names |
| Tính ổn định API | Do design/test quyết định | Do design/test quyết định | Do design/test quyết định | Do policy/test quyết định |
| Nguy cơ lộ methods | Nếu interface thiết kế rộng | Nếu interface rộng | Nếu annotate quá rộng | Nếu policy quá rộng |
| Công cụ client đa dạng | Tốt với types phù hợp | Tốt với open types | Phụ thuộc metadata và types | Phụ thuộc metadata và types |
| Độ phức tạp config | Thấp đến vừa | Thấp đến vừa | Vừa | Vừa đến cao |

Không có “mức an toàn” hoặc “hiệu năng” mặc định tuyệt đối cho một cột. Các vấn đề lớn thường đến từ management API cụ thể, chi phí getter, network exposure, naming và security, không phải chỉ từ lựa chọn interface/annotation.

## 13. Quy tắc chọn nhanh

**Chọn Standard MBean** nếu:
- Contract Java nhỏ, các types đơn giản.
- Có interface quản trị rõ.
- Dùng JMX tương đối độc lập với Spring.
- Không cần MXBean open-type mapping.

**Chọn MXBean** nếu:
- Muốn JMX interface dễ tương tác với nhiều clients.
- Cần dữ liệu cấu trúc mà MXBean có thể map sang OpenTypes.
- Muốn hạn chế phụ thuộc custom DTO ở client remote.
- Sẵn sàng kiểm thử mapping/schema.

**Chọn Spring annotations** nếu:
- Ứng dụng đang dùng Spring IoC.
- Muốn viết một management adapter ngắn, rõ.
- Cần metadata attribute/operation mô tả bằng annotation.
- Đã có một annotation-aware exporter phù hợp.

**Chọn custom/interface assembler** nếu:
- Có legacy classes không thể annotate.
- Cần policy nhất quán cho một tập beans lớn.
- Muốn centralize whitelisting/naming conventions.
- Đội ngũ hiểu rõ rủi ro maintenance của metadata rules.

Một dự án có thể dùng Standard MBeans cho platform integration, MXBeans cho structured data và annotation-driven adapters cho application-specific management, miễn mỗi ObjectName được đăng ký đúng một lần và contracts được quản trị rõ.

## 14. Ví dụ tình huống 1 — Chỉ cần QueueDepth

Yêu cầu:
- JConsole đọc queue depth.
- Java client dùng một interface.
- Không cần DTO phức tạp.
- Operation surface rất nhỏ.

Phương án thường phù hợp: **Standard MBean** với \`QueueMonitorMBean\` có \`int getQueueDepth()\`.

Nếu ứng dụng thuần Spring, vẫn có thể dùng annotation adapter để giảm boilerplate; việc lựa chọn Standard MBean hay annotation phụ thuộc tiêu chuẩn codebase và nhu cầu interface client. Không cần tạo custom assembler chỉ cho một getter nhỏ.

Một contract tối giản giúp tránh sự phụ thuộc vào toàn bộ business service.

## 15. Ví dụ tình huống 2 — Một snapshot có nhiều trường

Yêu cầu:
- Client đọc \`queued\`, \`processing\`, \`completed\`, \`failed\` và timestamp cùng một generation.
- Có Java/JMX clients ngoài ứng dụng.
- Muốn hạn chế phụ thuộc DTO classes riêng.

Phương án: **MXBean** với type mapping phù hợp hoặc Standard MBean trả \`CompositeData\` tường minh.

Không nên ghép các getters rời rồi gọi đó là atomic snapshot. MBean implementation cần coherent capture và publication. \`MXBean\` không tự biến nhiều state sources thành một snapshot nguyên tử.

Nếu dữ liệu phức tạp không map được, hãy dùng Open MBean types tường minh hoặc đơn giản hóa schema. Không trả trực tiếp JPA entities qua JMX.

## 16. Ví dụ tình huống 3 — Spring service có @Transactional

Yêu cầu:
- Service hiện có nhiều business methods, dùng transaction và caching.
- Muốn công bố \`getPendingCount()\` và \`getLastErrorCode()\`.
- Không được công bố \`cancelOrder()\` hoặc \`refundPayment()\`.

Phương án: **Spring management adapter riêng**, dùng \`@ManagedResource\` và \`@ManagedAttribute\`, inject service qua interface Spring proxy.

~~~java
@Component
@ManagedResource(
        objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderMonitorManagement {

    private final OrderService orderService;

    public OrderMonitorManagement(OrderService orderService) {
        this.orderService = orderService;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return orderService.pendingCountSnapshot();
    }

    @ManagedAttribute
    public String getLastErrorCode() {
        return orderService.lastErrorCode();
    }
}
~~~

Adapter giữ business API tách khỏi management API. Sử dụng snapshot rẻ để hạn chế SQL polling. Nếu adapter bị AOP proxy do pointcut rộng, phải kiểm tra metadata discovery và invocation với Spring version cụ thể.

## 17. Ví dụ tình huống 4 — Legacy bean không thể chỉnh source

Yêu cầu:
- Một thư viện nội bộ cung cấp class Java nhưng không thể thêm annotations.
- Chỉ muốn công bố \`getActiveWorkers()\` và \`getQueueDepth()\`.
- Cần giữ library APIs không bị thay đổi.

Phương án:
1. Tạo wrapper/management adapter riêng; hoặc
2. Dùng interface-based hay method-name-based assembler để chọn methods cụ thể.

Nếu chỉ có một bean, adapter thường dễ hiểu hơn. Nếu nhiều beans có cùng convention và người phụ trách kiểm soát được rules, assembler có thể giảm boilerplate.

Không dùng method exclusion policy quá rộng rồi kỳ vọng mọi future public method đều an toàn. Một method mới được thêm vào library có thể vô tình xuất hiện ở JMX nếu policy cho phép theo mặc định.

## 18. Ví dụ tình huống 5 — Client từ xa không có DTO classes

Yêu cầu:
- JMX remote client chạy ngoài application classpath.
- Dữ liệu cần trả nhiều fields, có schema rõ.
- Không muốn deployment client phụ thuộc custom entity/DTO jars.

Phương án thường hợp: **MXBean/OpenType** hoặc \`CompositeData\`/\`TabularData\` được định nghĩa tường minh.

Cần nhớ:
- Java serialization/classloader vẫn có thể ảnh hưởng những API không tuân OpenTypes.
- JMX/RMI remote cần authentication, authorization và mã hóa phù hợp.
- Không phải mọi generic class/record đều map tự động.
- Metadata/schema là một hợp đồng có phiên bản.

Không tắt TLS chỉ vì một client bị lỗi class loading; đó là hai loại sự cố khác nhau.

## 19. AOP proxy và management interface

Khi một Spring bean có \`@Transactional\`, security advice hoặc caching, Spring có thể dùng JDK dynamic proxy hoặc CGLIB.

JDK proxy thường expose interface methods, không bắt buộc expose public methods của concrete class. Nếu annotation chỉ có ở implementation class, cần xem assembler có tìm đúng target metadata không và proxy có thực hiện được method không.

Kiểm tra:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("orderMonitorManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
~~~

Đừng tự unwrap target rồi export trực tiếp nếu điều đó bỏ qua transaction hoặc security advice. Một management adapter nhỏ giúp giảm rủi ro nhưng vẫn phải test khi pointcuts rộng.

Với Standard MBean interface và JDK proxy, cần đảm bảo management interface thật sự được proxy expose và JMX registration path chấp nhận đối tượng đó. Các kết quả có thể khác giữa cấu hình/version, nên \`MBeanInfo\` và call tests là bắt buộc.

## 20. Lifecycle và ObjectName

Bất kể chọn phương án nào, JMX vẫn cần một \`ObjectName\` duy nhất trong một \`MBeanServer\`.

Ví dụ:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox
~~~

Các quy tắc thiết kế:
- Domain phản ánh application/module.
- Key properties định danh type và instance logic.
- Không nhầm Spring bean name với ObjectName.
- Không đưa secrets hoặc dữ liệu cá nhân vào ObjectName.
- Giữ tên ổn định nếu dashboards/scripts phụ thuộc.
- Một registration owner rõ cho từng tên.
- Cleanup khi context/application shutdown.
- Tránh exporter trùng dẫn tới \`InstanceAlreadyExistsException\`.

Spring \`RegistrationPolicy\` có \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\` và \`REPLACE_EXISTING\`. Những lựa chọn này xử lý conflict, không phải cơ chế versioning hay security.

Khi không rõ ai sở hữu tên, thường nên phát hiện conflict và sửa architecture hơn là tự replace MBean của component khác.

## 21. Bảo mật: lựa chọn MBean type không quyết định an toàn

Standard MBean, MXBean và Spring annotation-driven management đều có thể công bố operations thay đổi trạng thái. Vì vậy bảo mật phải được xem như bài toán riêng.

Ví dụ operation có rủi ro:

~~~java
@ManagedOperation
public void pauseConsumers() {
    service.pause();
}
~~~

Cần cân nhắc:
- Có thực sự cần công bố trên production không?
- Monitoring collector có cần quyền invoke không?
- JMX remote có xác thực và mã hóa không?
- Quyền operator và quyền read-only có được tách không?
- Có audit/logging hoạt động quan trọng không?
- Có rollback/recovery nếu operation gây side effects không?
- Có rate limiting hoặc guardrails phù hợp không?

Không dùng annotations hoặc interface naming như một cơ chế ACL. \`MBeanInfo\` chỉ mô tả management surface; quyền đọc/ghi của client được kiểm soát bởi connector/security và application guardrails.

## 22. Hiệu năng: getter vẫn có thể là bottleneck

Một getter JMX có thể bị client đọc thường xuyên. Ví dụ:

~~~java
@ManagedAttribute
public long getPendingCount() {
    return repository.countPending();
}
~~~

Nếu mỗi lần đọc chạy SQL, monitoring có thể gây thêm tải DB. Tương tự, MXBean mapping tạo \`CompositeData\` lớn hoặc Standard MBean trả collection không giới hạn cũng có overhead đáng kể.

Nguyên tắc:
- Getter nên nhẹ, không side effects.
- Dùng counters, cached snapshots hoặc refresh theo lịch cho dữ liệu đắt đỏ.
- Công bố freshness timestamp nếu snapshot có thể cũ.
- Không trả full entity graph hoặc secrets.
- Giới hạn payload và chi phí serialization.
- Đo latency/CPU/allocations nếu hệ thống có nhiều clients.

Không thể khẳng định Standard MBean “nhanh nhất”, MXBean “chậm hơn” hay annotations “không có overhead” nếu chưa đo implementation cụ thể.

## 23. Kiểm tra kết quả thật qua MBeanInfo

Dù chọn phương án nào, MBeanServer là nơi xem contract thực tế:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class MBeanContractInspector {

    public static void inspect(ObjectName name) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                    "MBean not registered: " + name);
        }

        MBeanInfo info = server.getMBeanInfo(name);
        System.out.println("Class: " + info.getClassName());

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                    "%s : %s readable=%s writable=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.printf(
                    "operation=%s returns=%s%n",
                    op.getName(),
                    op.getReturnType());
        }
    }
}
~~~

Đoạn code này dùng platform MBeanServer làm ví dụ. Khi exporter dùng custom server, phải truy vấn đúng server đã đăng ký.

\`MBeanInfo\` giúp xác minh:
- Tên và kiểu của attributes.
- Quyền đọc/ghi.
- Danh sách operations.
- Signature của operations.
- Metadata mà client có thể quan sát.

Nhưng metadata không tự bảo đảm getter không query DB hay operation an toàn; cần invocation tests và review semantics riêng trong quy trình phát triển.

## 24. Integration test cho lựa chọn thiết kế

Một integration test có thể dựng context/server cô lập và xác minh:

1. Đúng MBean được đăng ký.
2. ObjectName theo convention mong muốn.
3. Attributes và operations đúng contract.
4. Không có business methods bị expose ngoài ý muốn.
5. Return types phù hợp JMX client.
6. \`getAttribute\` trả giá trị có kiểu đúng.
7. \`invoke\` đúng signature và side effects dự kiến trong test environment.
8. Spring AOP proxy không làm hỏng management metadata.
9. Không có duplicate exporter registration.
10. Context shutdown unregister các MBeans do nó sở hữu.

Một test MBeanServer riêng:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test");
~~~

Truyền \`testServer\` vào exporter của Spring test context. Đừng chỉ tạo test server nhưng exporter vẫn sử dụng platform server rồi kết luận MBean không tồn tại.

### Pseudocode assert

~~~java
ObjectName name = new ObjectName(
    "com.example.shop.jobs:type=WorkerControl,name=primary");

assertTrue(testServer.isRegistered(name));

MBeanInfo info = testServer.getMBeanInfo(name);

assertTrue(
    java.util.Arrays.stream(info.getAttributes())
        .anyMatch(a -> "ActiveWorkers".equals(a.getName())
                    && "int".equals(a.getType())));
~~~

Đoạn này cần JUnit assertions và context/test dependencies phù hợp; nó minh họa cách kiểm tra runtime contract, không phải một class standalone hoàn chỉnh.

## 25. Versioning management API

Một JMX contract có thể được dùng lâu dài bởi scripts và monitoring rules. Những thay đổi sau có thể breaking:

- Đổi ObjectName.
- Đổi attribute name hoặc return type.
- Đổi operation signature.
- Thay đơn vị milliseconds thành seconds nhưng giữ tên cũ.
- Đổi \`CompositeData\` schema.
- Thay semantics của operation.
- Gỡ notification type đang được listener sử dụng.

Nếu chỉ thêm attribute mới và giữ old contract, việc mở rộng thường dễ tương thích. Khi cần breaking change, cân nhắc giữ v1 và công bố v2 ở ObjectName khác với migration window.

Chọn MXBean thay Standard MBean không tự giải quyết contract versioning. Chọn annotation cũng không tự làm management API backward-compatible. Phải có chính sách deprecation, tests và lộ trình chuyển consumers.

## 26. Tình huống Spring Boot và Actuator

Spring Boot có thể tạo JMX export infrastructure theo version và cấu hình; Actuator có thể expose endpoints qua JMX technology. Tuy nhiên:

- JVM platform MBeans là thành phần riêng.
- Spring custom \`@ManagedResource\` MBeans có registration path riêng.
- Actuator JMX endpoints thuộc Actuator management infrastructure.
- \`management.endpoints.jmx.exposure.include\` không phải allowlist áp dụng cho mọi custom MBean.
- \`spring.jmx.enabled\` không tự cấu hình remote JMX connector.
- \`management.server.port\` liên quan management HTTP server port, không mặc định là remote JMX port.

Trước khi thêm \`MBeanExporter\` thủ công, kiểm tra exporter hiện có, domain/naming, Spring Boot version và phạm vi registration.

## 27. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| \`NotCompliantMBeanException\` | Standard/MXBean contract không hợp lệ | Sửa interface/wrapper/type mapping |
| MBean không xuất hiện | Spring bean hoặc exporter không hoạt động | Kiểm tra context, export mode |
| Annotation không có tác dụng | Assembler/source không đọc annotations | Cấu hình metadata pipeline |
| Có attribute nhưng không có operation | Metadata selection khác dự đoán | Đọc MBeanInfo và contract |
| \`ClassCastException\` ở remote client | DTO/type mapping không phù hợp | Dùng MXBean/OpenType hoặc shared DTO đúng |
| \`InstanceAlreadyExistsException\` | Hai owners cùng ObjectName | Sửa naming/ownership |
| JConsole thấy MBean sai domain | Naming strategy khác convention | Query ObjectNames và sửa naming |
| Getter khiến DB load tăng | Query đắt trong getter | Snapshot/cache/refresh |
| AOP proxy làm method không hiện | Interface/proxy metadata không tương thích | Test AOP, tách adapter |
| MXBean mapping lỗi | Type không hợp open-type rules | Đổi type, test mapping |
| Management operation không được phép | Connector authorization | Cấu hình quyền đúng, không mở remote bừa |
| Dashboard bị mất metric sau refactor | Contract đổi tên/type | Versioning và migration |

## 28. Bài tập đánh giá thiết kế

### Bài 1 — MBean có ba scalar attributes

Một library cần cung cấp \`ThreadCount\`, \`QueueDepth\`, \`Paused\`. Client là Java/JConsole; không cần metadata mở rộng.

Hãy đề xuất Standard MBean interface và giải thích vì sao custom assembler có thể không cần thiết.

### Bài 2 — Snapshot có schema

Một ứng dụng muốn trả trạng thái worker gồm \`active\`, \`idle\`, \`failed\`, \`capturedAt\` cho remote JMX clients. Hãy so sánh MXBean open-type mapping và Standard MBean trả \`CompositeData\`. Nêu giới hạn custom DTO.

### Bài 3 — Spring service có AOP

Một service có \`@Transactional\` và public methods \`getPending()\`, \`refundOrder()\`, \`deleteOrder()\`. Hãy thiết kế một management adapter annotate \`@ManagedResource\` chỉ công bố \`getPending()\`, tránh các operations nguy hiểm.

### Bài 4 — Legacy class không sửa được

Bạn không được thay class của thư viện nhưng muốn expose hai getters. So sánh wrapper adapter với interface/method-name assembler; nêu tradeoff maintenance.

### Bài 5 — Contract tests

Chọn một phương án, triển khai MBean và kiểm tra \`MBeanInfo\`, \`getAttribute\`, \`invoke\`, \`isRegistered\` và lifecycle cleanup. Đồng thời assert một method không mong muốn không được expose.

### Bài 6 — Chiến lược nhiều modules

Ứng dụng có queue monitor, database pool monitor và cache statistics. Hãy quyết định nên dùng một phương pháp nhất quán hay kết hợp Standard MBean/MXBean/annotations. Đặt một ObjectName convention và registration owner rõ cho từng MBean.

## 29. Câu hỏi tự kiểm tra

**1. Annotation và assembler có phải hai loại MBean ngang hàng Standard MBean và MXBean không?**  
Không. Annotation là nguồn metadata; assembler là cơ chế tạo metadata trong Spring export pipeline.

**2. Khi nào MXBean phù hợp hơn Standard MBean?**  
Khi cần interoperability qua OpenType mapping cho data types được hỗ trợ, đặc biệt với clients không cùng application classpath.

**3. Standard MBean có bắt buộc ứng dụng sử dụng Spring không?**  
Không. Có thể đăng ký trực tiếp qua Java MBeanServer.

**4. Chỉ đặt \`@ManagedResource\` trên class có đảm bảo xuất hiện trong JConsole không?**  
Không. Cần Spring bean và exporter/assembler thích hợp, registration đúng server/ObjectName.

**5. Một assembler có quyền chọn bean nào được autodetect không?**  
Nếu assembler triển khai khả năng autodetect phù hợp, nó có thể tham gia quyết định include qua interface tương ứng.

**6. Có nên export nguyên business service interface chứa destructive operations không?**  
Không nên. Tạo management contract/adapter tối thiểu và kiểm soát quyền.

**7. Nếu Java record không map được ở MXBean thì sao?**  
Chọn type/schema được hỗ trợ hoặc trả Open MBean structure tường minh, rồi kiểm thử.

**8. Có phương án nào tự đảm bảo JMX remote an toàn không?**  
Không. Authentication, authorization, TLS, network isolation và audit là các quyết định bổ sung.

## 30. Ghi nhớ

- Standard MBean và MXBean là những mô hình management interface của JMX.
- Spring annotations là cách khai báo management metadata; assembler là tầng tạo \`MBeanInfo\`, thường phối hợp với annotations.
- Standard MBean hợp với Java interface đơn giản, contract nhỏ và ít phụ thuộc Spring.
- MXBean hữu ích khi cần OpenType interoperability với client đa dạng.
- Annotation-driven adapter hợp khi ứng dụng dùng Spring IoC và muốn API quản trị khai báo rõ.
- Custom/interface assembler hợp với legacy code hoặc policy chọn methods tập trung.
- Đừng export rộng business services hoặc dựa vào method exclusion thiếu kiểm soát.
- Mọi phương án cần ObjectName ổn định, registration owner rõ và \`MBeanInfo\` tests.
- Proxy, type mapping, remote security, performance và API versioning có thể quan trọng hơn cách khai báo management interface.
- Không có “một phương án đúng cho mọi trường hợp”; chọn theo yêu cầu client, contract, lifecycle và mức kiểm soát cần thiết.

## 31. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — MBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MBeanInfoAssembler.html
- Spring Framework Javadoc — MetadataMBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Java SE 21 — StandardMBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Java SE 21 — MXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Java SE 21 — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
