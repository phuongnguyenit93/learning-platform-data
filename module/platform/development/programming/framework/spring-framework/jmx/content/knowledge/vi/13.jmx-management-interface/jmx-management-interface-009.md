# Ẩn phương thức không thuộc giao diện quản trị trong Spring Framework JMX

## Mục tiêu

Một class Java có thể có nhiều phương thức \`public\`, nhưng không phải mọi phương thức \`public\` đều nên được người vận hành gọi qua JMX. Trong ứng dụng Spring Framework, bề mặt quản trị thường cần **nhỏ, ổn định, dễ hiểu và giới hạn tác động** hơn API nội bộ của một service. **Management interface** là một kỹ thuật cốt lõi để tạo ranh giới này: định nghĩa riêng những attribute và operation được phép công bố, trong khi các method khác của implementation vẫn phục vụ nội bộ Java/Spring mà không tự biến thành operation JMX.

Bài này tập trung vào việc **ẩn các phương thức không thuộc giao diện quản trị**, không chỉ bằng cách đặt method thành \`private\`, mà bằng cách thiết kế một hợp đồng JMX có giới hạn, chọn đúng cơ chế export và xác minh metadata thực tế trên MBeanServer.

Sau bài học, bạn có thể:

- Phân biệt Java public API với JMX management API.
- Giải thích cơ chế Standard MBean/MXBean chỉ công bố thành viên của management interface.
- Thiết kế interface riêng cho quan sát/chẩn đoán/điều khiển thay vì export toàn bộ service.
- Hiểu vai trò của \`StandardMBean\` wrapper khi tên interface không theo quy ước.
- Phân biệt interface-based export với Spring \`@ManagedResource\` và metadata assembler.
- Cẩn trọng với Spring AOP proxy, nhiều exporter, ObjectName, lifecycle và khả năng công bố nhầm.
- Kiểm chứng danh sách attribute/operation thực sự bằng \`MBeanInfo\`.
- Nhận diện giới hạn bảo mật: không được export qua JMX khác với cấm truy cập mọi đường khác.

## 1. Vấn đề: public method không đồng nghĩa được phép quản trị

Xét một bean nghiệp vụ:

\`\`\`java
public class PaymentProcessor {
    public long getProcessedCount() { /* ... */ return 0; }
    public String getHealthSummary() { /* ... */ return "OK"; }
    public void reprocessPayment(String paymentId) { /* ... */ }
    public void deletePayment(String paymentId) { /* ... */ }
    public void changeAccountLimit(String accountId, long amount) { /* ... */ }
}
\`\`\`

Trong Java, các method \`public\` có thể được code khác gọi nếu có reference phù hợp. Nhưng bề mặt JMX không nên mặc nhiên gồm tất cả:

\`\`\`text
Java public API của PaymentProcessor
├── getProcessedCount()         [quản trị: phù hợp]
├── getHealthSummary()          [quản trị: có thể phù hợp]
├── reprocessPayment(id)        [nghiệp vụ: cần hạn chế]
├── deletePayment(id)           [nghiệp vụ: rất nhạy cảm]
└── changeAccountLimit(id, n)   [nghiệp vụ: không export tùy tiện]

JMX management API mong muốn
├── ProcessedCount (read-only)
└── HealthSummary (read-only)
\`\`\`

Nếu export nhầm method thay đổi trạng thái, JMX client có quyền invoke có thể thực hiện tác động lớn mà không đi qua workflow nghiệp vụ chuẩn. Vì vậy cách tiếp cận tốt là **whitelist qua hợp đồng quản trị**, không phải hi vọng mọi developer sẽ nhớ tránh viết các method nguy hiểm.

Một management interface định nghĩa chính xác nhóm method cần xuất. Implementation có thể chứa thêm public method, nhưng Standard MBean introspection dựa trên interface quản trị không tự phơi bày các public method ngoài interface đó.

## 2. Phân biệt ba tầng API

| Tầng | Người dùng | Mục đích |
|---|---|---|
| Java internal API | Các class/service cùng JVM | Thực thi nghiệp vụ, thao tác dữ liệu và phối hợp dependency |
| Management interface | MBeanServer và JMX client | Quan sát, chẩn đoán, điều khiển đã được thiết kế |
| Remote JMX access | Công cụ quản trị qua connector | Tiếp cận management API theo quyền và mạng |

Một method không nằm trong management interface có thể vẫn là \`public\` cho các bean Java khác dùng. Điều đó **không tạo thêm JMX operation** nếu MBean được đăng ký đúng theo Standard MBean contract. Ngược lại, thêm method vào management interface có thể khiến bề mặt JMX thay đổi ngay sau lần đăng ký/export tiếp theo.

Đừng nhầm việc “ẩn khỏi JMX” với bảo mật toàn cục. Nếu cùng hành vi được công bố qua REST endpoint, message handler hay một MBean khác, nó vẫn có thể được gọi qua những kênh đó. Mỗi boundary phải có cơ chế kiểm soát riêng.

## 3. Standard MBean: interface là danh sách công bố

JMX Standard MBean dựa trên một interface có hậu tố \`MBean\` theo quy ước. Ví dụ:

\`\`\`java
package com.example.inventory;

public interface InventoryWorkerMBean {
    String getState();
    long getCompletedCount();
    int getQueueDepth();
    void requestPause();
}
\`\`\`

Implementation:

\`\`\`java
package com.example.inventory;

import java.util.concurrent.atomic.AtomicLong;

public class InventoryWorker implements InventoryWorkerMBean {

    private volatile String state = "RUNNING";
    private final AtomicLong completed = new AtomicLong();

    @Override
    public String getState() {
        return state;
    }

    @Override
    public long getCompletedCount() {
        return completed.get();
    }

    @Override
    public int getQueueDepth() {
        return 0; // Demo: đọc từ queue adapter trong ứng dụng thực tế.
    }

    @Override
    public void requestPause() {
        state = "PAUSE_REQUESTED";
    }

    // Public cho code Java gọi, nhưng KHÔNG nằm trong InventoryWorkerMBean.
    public void rebuildInternalIndex() {
        // Công việc nội bộ có thể tốn tài nguyên.
    }

    // Public nhưng không phải giao diện JMX được công bố.
    public void deleteInternalCheckpoint(String checkpointId) {
        // Thao tác nhạy cảm: không đưa vào management interface.
    }

    protected void refreshLocalState() {
        // Implementation detail.
    }
}
\`\`\`

Khi đăng ký một \`InventoryWorker\` như Standard MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.inventory:type=Worker,name=Sync");

server.registerMBean(new InventoryWorker(), name);
\`\`\`

JMX introspection nhận diện \`getState()\`, \`getCompletedCount()\` và \`getQueueDepth()\` như các attribute read-only, cùng \`requestPause()\` như operation. Các method \`rebuildInternalIndex()\` và \`deleteInternalCheckpoint(String)\` không có mặt trong management interface, do đó không tự xuất hiện thành JMX operation trong mô hình Standard MBean này.

**Quan trọng:** quy ước tên class/interface phải được thỏa mãn hoặc sử dụng wrapper/API đăng ký tương ứng. Nếu không, \`registerMBean\` có thể ném \`NotCompliantMBeanException\` thay vì tự đoán interface bạn muốn công bố.

## 4. Getter, setter và operation: không chỉ method name

Trong Standard MBean:

\`\`\`java
public interface CacheMetricsMBean {
    long getHits();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    String inspect(String key);
}
\`\`\`

Khi introspect theo quy tắc JavaBean/JMX:

- \`getHits()\` trở thành attribute \`Hits\`, read-only.
- \`isEnabled()\` cùng \`setEnabled(boolean)\` có thể tạo attribute \`Enabled\` đọc/ghi phù hợp.
- \`inspect(String key)\` là operation vì có tham số và không theo mẫu getter attribute không tham số.

Việc **không đưa setter vào interface** có thể khiến attribute chỉ đọc, dù implementation có method setter public phục vụ nội bộ.

Ví dụ:

\`\`\`java
public interface ThrottleStatusMBean {
    int getMaxConcurrency(); // Chỉ công bố getter.
}

public class ThrottleStatus implements ThrottleStatusMBean {
    private volatile int maxConcurrency = 12;

    @Override
    public int getMaxConcurrency() {
        return maxConcurrency;
    }

    public void setMaxConcurrency(int value) {
        // Chỉ là Java method public; không được expose qua interface này.
        maxConcurrency = value;
    }
}
\`\`\`

Đây là một công cụ để giới hạn việc thay đổi cấu hình runtime qua JMX. Nhưng chỉ ẩn setter không thay cho authentication/authorization; JMX connector và các kênh API khác vẫn cần được bảo vệ.

## 5. StandardMBean wrapper khi tên interface không khớp convention

Một interface có thể được dùng chung cho nhiều implementation hoặc được đặt tên mang tính nghiệp vụ, không khớp hậu tố của concrete class. Trong trường hợp đó, có thể chỉ rõ management interface bằng \`StandardMBean\`:

\`\`\`java
public interface QueueAdminMBean {
    int getDepth();
    String getState();
}
\`\`\`

\`\`\`java
public class KafkaQueueAdmin implements QueueAdminMBean {

    @Override
    public int getDepth() {
        return 42;
    }

    @Override
    public String getState() {
        return "RUNNING";
    }

    public void commitOffsetsForRepair() {
        // Không thuộc QueueAdminMBean.
    }
}
\`\`\`

Đăng ký:

\`\`\`java
import javax.management.StandardMBean;
import javax.management.ObjectName;

KafkaQueueAdmin implementation = new KafkaQueueAdmin();
StandardMBean exposed = new StandardMBean(
    implementation,
    QueueAdminMBean.class
);

server.registerMBean(
    exposed,
    new ObjectName("com.example.queue:type=Admin,name=Kafka")
);
\`\`\`

Wrapper làm rõ \`QueueAdminMBean\` là hợp đồng quản trị. Điều này hữu ích khi muốn ổn định management interface trong lúc thay concrete implementation. Nó cũng giúp tránh việc thay tên class vô tình thay đổi quy tắc Standard MBean.

Cần lưu ý interface phải mô tả đầy đủ những thành viên hợp lệ theo quy tắc Standard MBean. Đối với kiểu phức tạp cần tương thích tốt qua remote client, nên xem xét MXBean thay vì đưa object đồ sộ vào signature.

## 6. MXBean cũng giới hạn bề mặt bằng interface

MXBean là một dạng management interface có quy tắc mapping dữ liệu sang Open Types. Ví dụ:

\`\`\`java
public interface QueueRuntimeMXBean {
    long getMessagesProcessed();
    int getActiveConsumers();
    String getEffectiveState();
}
\`\`\`

Một implementation:

\`\`\`java
public class QueueRuntime implements QueueRuntimeMXBean {

    @Override
    public long getMessagesProcessed() {
        return 0L;
    }

    @Override
    public int getActiveConsumers() {
        return 4;
    }

    @Override
    public String getEffectiveState() {
        return "RUNNING";
    }

    public void purgeDeadLetters() {
        // Public Java method nhưng không thuộc MXBean interface.
    }
}
\`\`\`

MBeanServer có thể công bố interface \`QueueRuntimeMXBean\` theo quy ước MXBean hoặc theo wrapper \`StandardMBean\` được cấu hình MXBean mode. Tương tự Standard MBean, chỉ những thành viên thuộc interface MXBean mới là hợp đồng quản trị được công bố.

MXBean khác ở chỗ mapping dữ liệu ra các kiểu có thể trao đổi giữa JMX client tốt hơn, thường được biểu diễn qua Open MBean types. Dù vậy, không phải mọi loại Java object đều tự tương thích; cần tuân thủ các quy tắc mapping và xem xét kích thước payload.

## 7. Management interface như một bề mặt tối thiểu

Thiết kế tốt thường tách:

\`\`\`text
Business service
├── processBatch()
├── retryFailedPayment()
├── deleteTransaction()
├── changePolicy()
├── getHealthSnapshot()
└── getProcessedCount()

               |
               | adapter gọi các method được phép
               v

Management adapter implements WorkerStatusMXBean
├── getHealthState()
├── getProcessedCount()
└── getPendingCount()
\`\`\`

Lợi ích:

1. Không làm domain service phụ thuộc trực tiếp vào khái niệm JMX.
2. Tách ý nghĩa quản trị khỏi workflow nghiệp vụ.
3. Tránh bề mặt có các operation nguy hiểm do developer tiện tay đưa vào.
4. Dễ kiểm tra contract JMX khi refactor implementation.
5. Có thể dùng một management contract cho nhiều triển khai backend.
6. Cho phép áp dụng validation, rate limit, redaction và cấu trúc response riêng.

**Một interface riêng không bắt buộc phải được implement trực tiếp bởi domain service.** Có thể dùng adapter:

\`\`\`java
public interface ProcessingStatusMBean {
    long getCompletedCount();
    String getState();
}
\`\`\`

\`\`\`java
public final class ProcessingStatus
        implements ProcessingStatusMBean {

    private final ProcessingService service;

    public ProcessingStatus(ProcessingService service) {
        this.service = service;
    }

    @Override
    public long getCompletedCount() {
        return service.completedCount();
    }

    @Override
    public String getState() {
        return service.safeStateSummary();
    }
}
\`\`\`

Ở đây \`ProcessingService\` là service nghiệp vụ của ứng dụng, còn \`ProcessingStatus\` chỉ công bố hai method cần thiết. Vì \`ProcessingStatusMBean\` không theo convention \`ProcessingStatusMBean\`? Trong ví dụ này tên khớp, nên có thể dùng Standard MBean trực tiếp. Nếu tên implementation khác, \`StandardMBean\` wrapper giúp chỉ định interface rõ ràng.

## 8. Spring Framework JMX: interface và exporter

Spring có nhiều con đường JMX export:

- Đăng ký trực tiếp Standard MBean/MXBean qua \`MBeanServer.registerMBean\`.
- Dùng Spring \`MBeanExporter\` để quản lý registration/lifecycle của những bean đã chọn.
- Dùng \`AnnotationMBeanExporter\` cùng \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`.
- Dùng một \`MBeanInfoAssembler\` hoặc metadata assembler với chiến lược export phù hợp.

Điều cốt lõi: **phải hiểu cơ chế export thực tế dùng tiêu chí nào để chọn method**. Standard MBean management interface là một whitelist do JMX introspection nhận diện. Annotation export dùng annotation/metadata, không đơn thuần dựa trên interface Standard MBean. Nếu bạn cấu hình một assembler công bố nhiều method hơn, kết quả có thể khác với kỳ vọng “chỉ method trong interface”.

### 8.1 Dùng MBeanExporter với một Standard MBean adapter

Ví dụ Java configuration:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ManagementExportConfiguration {

    @Bean
    public InventoryWorker inventoryWorker() {
        return new InventoryWorker();
    }

    @Bean
    public MBeanExporter managementExporter(InventoryWorker worker) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setBeans(Map.of(
            "com.example.inventory:type=Worker,name=Sync",
            worker
        ));
        return exporter;
    }
}
\`\`\`

Trong cấu hình này, bean \`InventoryWorker\` tuân theo Standard MBean convention thông qua \`InventoryWorkerMBean\`. Spring exporter đăng ký bean và quản lý lifecycle của registration mà nó sở hữu. Các method public ngoài interface không vì thế tự được công bố nếu JMX xuất bean theo contract Standard MBean.

Khi dùng một phiên bản Spring có cấu hình autodetection/assembler khác, cần kiểm tra metadata xuất thực tế. Không đồng thời đăng ký cùng \`ObjectName\` qua code thủ công và exporter nếu không có cơ chế ownership rõ ràng.

### 8.2 Không đánh đồng @ManagedResource với Standard MBean interface

Ví dụ annotation:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.inventory:type=Metrics,name=Sync")
public class InventoryMetrics {

    @ManagedAttribute
    public long getCompletedCount() {
        return 0L;
    }

    @ManagedOperation
    public void resetCounters() {
        // Một operation có side effect.
    }

    public void dangerousInternalRepair() {
        // Không được annotation.
    }
}
\`\`\`

Khi \`AnnotationMBeanExporter\` dùng metadata annotation tương ứng, \`dangerousInternalRepair()\` không tự xuất hiện chỉ vì là public method. Nhưng đây là **quy tắc của annotation-driven export**, không phải kết quả do interface Standard MBean lọc. Nếu exporter sử dụng một assembler khác hoặc export cùng bean dưới đường khác, cần xác minh lại.

Một hệ thống có thể sử dụng cả hai cách, nhưng đừng đặt cùng một bean vào hai đường export trùng \`ObjectName\`.

## 9. Vì sao chỉ đổi method từ public thành private chưa đủ?

Một yêu cầu thường gặp: “Không muốn JMX thấy method \`purge()\`, đổi nó thành \`private\` có được không?” Nếu method là implementation detail và không cần được gọi từ nơi khác, giảm Java visibility là hợp lý. Nhưng điều đó không giải quyết toàn bộ bài toán thiết kế management API:

- Một method public mới có thể được thêm sau này.
- Proxy/AOP, các interface khác hoặc exporter config có thể thay đổi cách introspection.
- Các operation nguy hiểm có thể nằm trong method được phép xuất nhưng có phạm vi quá rộng.
- Không có hợp đồng riêng giúp reviewer biết điều gì được phép công bố.

Management interface giúp giữ một danh sách rõ ràng:

\`\`\`java
public interface CacheStatusMBean {
    long getEntryCount();
    long getEvictionCount();
    String getHealthSummary();
}
\`\`\`

Ngay cả khi implementation có các method public \`clearAll()\` hay \`rebuildIndex()\`, chúng không được công bố trong Standard MBean contract này. Điều đó giúp giới hạn bề mặt **theo kiến trúc**, thay vì phụ thuộc hoàn toàn vào modifier của từng method trong class.

## 10. Java interface không phải cơ chế authorization

Đây là khác biệt quan trọng:

| Câu hỏi | Management interface giải quyết? |
|---|---|
| Method nào được JMX công bố trong contract này? | Có |
| Một JMX client có thể thấy operation nào? | Có, với export đúng |
| Client đã xác thực hay chưa? | Không |
| Operator có quyền gọi operation hay không? | Không tự động |
| Tham số có hợp lệ, có thể gây hại không? | Không |
| Invocation có được ghi audit? | Không |
| Thao tác có idempotent hoặc rollback được không? | Không |
| Cùng method có được gọi qua API khác không? | Không kiểm soát |

Một interface nhỏ là **giới hạn bề mặt**, không phải kiểm soát truy cập. Nếu operator có quyền invoke operation \`requestPause()\`, nó vẫn có thể làm thay đổi trạng thái runtime. Cần bảo vệ JMX connector, authentication/authorization, TLS/mạng quản trị, audit và logic kiểm tra trạng thái theo mức rủi ro.

Các operation chỉ đọc cũng có thể gây chi phí cao nếu chúng quét dữ liệu lớn hoặc truy vấn downstream. Hãy giữ getters nhẹ và có giới hạn dữ liệu.

## 11. Spring AOP proxy và việc xuất interface

Spring bean có thể bị wrap bởi JDK dynamic proxy hoặc CGLIB proxy do \`@Transactional\`, \`@Async\`, AOP advice và cơ chế khác. Điều này ảnh hưởng cách exporter và JMX introspection nhìn class/interface.

Ví dụ:

\`\`\`text
Target: InventoryWorker implements InventoryWorkerMBean
        |
        v
Spring JDK Proxy
        |
        v
Bean mà exporter nhìn thấy
\`\`\`

Proxy JDK chỉ implement những interface được chọn để proxy, nên cần xác nhận management interface có thực sự được phơi bày trên proxy và exporter có cách phát hiện nó. Proxy CGLIB có đặc tính khác. Nếu introspection không tìm được Standard MBean interface, có thể xuất hiện \`NotCompliantMBeanException\` hoặc tên/metadata khác kỳ vọng, tùy export path.

Một thiết kế giảm coupling là tạo **management adapter riêng**:

\`\`\`text
Service bị Spring AOP proxy
         |
         | dependency injection
         v
ManagementAdapter implements ManagementAdapterMBean
         |
         v
MBeanExporter / MBeanServer
\`\`\`

Adapter gọi service qua đúng Spring proxy nếu muốn advice có hiệu lực, nhưng không cần export toàn bộ class nghiệp vụ. Điều này thường làm management contract ổn định khi service refactor hay thêm method mới.

## 12. Có thể có nhiều management interface không?

Một class Java có thể implement nhiều interface. Tuy nhiên Standard MBean có quy tắc xác định **một management interface cho đăng ký cụ thể** hoặc cần cấu hình/wrapper rõ ràng. Không được giả định mọi interface mà class implement đều được JMX gộp vào một MBean tự động.

Ví dụ:

\`\`\`java
interface HealthView {
    String getState();
}

interface AdminControl {
    void requestPause();
}
\`\`\`

Nếu muốn phơi bày một tập cụ thể, nên tạo contract quản trị có chủ đích:

\`\`\`java
public interface WorkerAdminMBean {
    String getState();
    void requestPause();
}
\`\`\`

Hoặc export các adapter riêng với \`ObjectName\` khác nhau, nếu thật sự cần phân tách bề mặt read-only và control. Hãy lưu ý rằng tách MBean về mặt giao diện không tự tạo ranh giới quyền nếu cùng connector cho phép mọi client invoke bất kỳ operation nào.

## 13. Metadata MBeanInfo là bằng chứng thực tế

Không chỉ đọc code rồi đoán. Sau khi đăng ký, hỏi chính MBeanServer:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("ATTRIBUTE: " + attribute.getName()
        + ", readable=" + attribute.isReadable()
        + ", writable=" + attribute.isWritable());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OPERATION: " + operation.getName());
}
\`\`\`

Nếu bạn kỳ vọng \`deleteInternalCheckpoint\` bị ẩn, hãy assert **không** có operation đó trong \`info.getOperations()\`. Đồng thời kiểm tra không có attribute write được ngoài dự kiến, vì một public setter có thể biến thành write access khi được công bố trong interface hoặc assembler.

### 13.1 Test negative contract

Một integration test có thể đảm bảo method nội bộ không bị xuất:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.*;

import org.junit.jupiter.api.Test;

class InventoryWorkerVisibilityTest {

    @Test
    void onlyManagementContractIsVisible() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.test:type=InventoryWorker,name=Sample");

        InventoryWorker worker = new InventoryWorker();
        boolean registeredHere = false;

        try {
            server.registerMBean(worker, name);
            registeredHere = true;

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(
                Arrays.stream(info.getOperations())
                    .anyMatch(op -> op.getName().equals("requestPause"))
            );

            assertFalse(
                Arrays.stream(info.getOperations())
                    .anyMatch(op -> op.getName().equals(
                        "deleteInternalCheckpoint"))
            );

            assertFalse(
                Arrays.stream(info.getOperations())
                    .anyMatch(op -> op.getName().equals(
                        "rebuildInternalIndex"))
            );

        } finally {
            if (registeredHere) {
                server.unregisterMBean(name);
            }
        }
    }
}
\`\`\`

Ở test thật, nên dùng namespace riêng hoặc \`MBeanServer\` riêng để tránh tranh chấp \`ObjectName\` khi chạy song song. Cờ \`registeredHere\` trong ví dụ giúp chỉ cleanup mục do test này đăng ký, không xóa một MBean thuộc test/process khác.

Test theo hướng phủ định rất quan trọng: kiểm tra không chỉ “có metric cần xem”, mà còn “không có lệnh ngoài hợp đồng”.

## 14. Chẩn đoán khi method ngoài interface vẫn xuất hiện

Nếu JConsole vẫn hiển thị method mà bạn không đưa vào management interface, có thể do:

1. **MBean được export bằng cơ chế khác**: Spring metadata assembler hoặc dynamic MBean có thể quyết định danh sách member theo quy tắc khác.
2. **Đăng ký không sử dụng StandardMBean wrapper mong muốn**: implementation class/management interface khác điều bạn nghĩ.
3. **Có nhiều MBean cùng bản chất resource**: client đang nhìn một \`ObjectName\` khác hoặc một exporter khác.
4. **ObjectName trùng hoặc registration bị thay thế**: MBean thực tế không phải instance bạn vừa đọc code.
5. **Spring AOP proxy hoặc class scanning**: exporter phát hiện target/proxy interface không như dự kiến.
6. **Metadata cũ trong JMX client**: UI có thể cache view, cần kiểm tra trực tiếp \`MBeanServer.getMBeanInfo\` tại đúng server và instance.
7. **Interface kế thừa method**: method nằm trong superinterface của management interface, nên vẫn thuộc contract dù không được khai báo trực tiếp trong file đang nhìn.

Cách điều tra:

\`\`\`text
Xác định đúng JVM / JMX connector
    ↓
Xác định MBeanServer đích
    ↓
Xác định ObjectName thực tế
    ↓
Đọc MBeanInfo từ server đó
    ↓
Xác định exporter/assembler hoặc StandardMBean wrapper
    ↓
Xác định interface quản trị được nhận diện
    ↓
Sửa contract hoặc registration path
\`\`\`

Không nên “ẩn” method bằng cách đổi tên lẻ tẻ nếu root cause là exporter khác đang công bố toàn bộ bean.

## 15. Method inherited và default method trên interface

Một management interface có thể mở rộng interface khác:

\`\`\`java
public interface BasicStatus {
    String getState();
}

public interface WorkerStatusMBean extends BasicStatus {
    long getCompletedCount();
}
\`\`\`

Phương thức \`getState()\` được kế thừa vẫn là một phần của contract \`WorkerStatusMBean\` theo Java interface inheritance. Khi đánh giá bề mặt JMX, không chỉ xem các method được khai báo trực tiếp; cần xem toàn bộ inheritance tree.

Tương tự, nếu đưa default method vào management interface, cần cân nhắc hành vi introspection tương ứng và tương thích các phiên bản JMX/Spring đang dùng. Đừng dùng inheritance từ một interface nghiệp vụ rất lớn chỉ để tái sử dụng một getter quản trị, vì điều đó có thể vô tình kéo theo thêm nhiều method vào JMX contract.

Một interface quản trị tốt thường nhỏ, ổn định và ít inheritance phức tạp.

## 16. Dữ liệu và method nhạy cảm không nên xuất qua interface

Ngoài operation điều khiển, cũng cần cân nhắc getter trả thông tin nhạy cảm:

\`\`\`java
public interface InternalDebugMBean {
    String getDatabasePassword(); // Không nên công bố.
    String getAccessToken();      // Không nên công bố.
    String getRawRequestBody();   // Có thể chứa PII/secret.
}
\`\`\`

Dù là getter read-only, công bố dữ liệu nhạy cảm trên JMX vẫn là rủi ro. Hợp đồng phù hợp hơn:

\`\`\`java
public interface SafeRuntimeStatusMBean {
    String getDatabaseConnectionState();
    long getFailedRequestCount();
    long getLastSuccessfulSyncEpochMillis();
}
\`\`\`

Chỉ báo trạng thái tổng hợp không nhạy cảm. Kiểu dữ liệu nên đơn giản và có kích thước giới hạn, đặc biệt cho JMX remote client. Không trả bộ sưu tập không giới hạn hoặc object nội bộ có classloader phụ thuộc quá sâu.

## 17. Quy trình thiết kế interface quản trị

### Bước 1: liệt kê nhu cầu vận hành thật

Thay vì export toàn bộ service rồi cố ẩn một vài method, hãy bắt đầu từ câu hỏi:

- Người vận hành cần đọc trạng thái nào?
- Cần chẩn đoán gì khi sự cố xảy ra?
- Có thực sự cần lệnh điều khiển hay có control plane tốt hơn?
- Ai là consumer, dùng JConsole, monitoring agent hay script?
- API này có phải ổn định qua nhiều release không?

### Bước 2: chọn interface nhỏ

\`\`\`java
public interface ImportWorkerStatusMXBean {
    String getEffectiveState();
    long getBacklog();
    long getCompletedCount();
}
\`\`\`

Nếu cần control, cân nhắc một interface/adapter khác với security boundary phù hợp. Chỉ tách interface không đủ phân quyền nếu mọi người dùng cùng JMX connector.

### Bước 3: chọn export path duy nhất

Quyết định:
- Standard MBean theo convention?
- MXBean?
- \`StandardMBean\` wrapper?
- Spring \`MBeanExporter\`?
- Annotation-driven export?

Tránh để hai cơ chế cùng đăng ký cùng bean/ObjectName mà không rõ owner.

### Bước 4: quản lý ObjectName và vòng đời

ObjectName phải duy nhất trong MBeanServer, không chứa secret, và ổn định cho client. Component đăng ký phải unregister khi context đóng, nếu nó sở hữu đăng ký đó. Không release platform MBeanServer chỉ vì một Spring context bị destroy.

### Bước 5: kiểm tra cả sự có mặt lẫn vắng mặt

Đọc \`MBeanInfo\` và xác minh:
- Attribute cần thiết có tồn tại, read/write đúng không?
- Operation cần thiết có tồn tại, signature đúng không?
- Method không thuộc hợp đồng có bị ẩn thực sự không?
- Không có dữ liệu nhạy cảm hoặc operation ngoài ý muốn?

### Bước 6: duy trì contract

Mỗi thay đổi interface là thay đổi bề mặt quản trị có thể làm dashboard/script hỏng. Với thay đổi breaking, cần quản lý version và migration có chủ đích. Nếu chỉ refactor implementation mà interface không đổi, client JMX không cần biết chi tiết nội bộ.

## 18. Bài tập vận dụng

**Bài 1 — Standard MBean.** Cho class \`CacheControl\` có các method \`getHitCount()\`, \`getMissCount()\`, \`clearAll()\`, \`deleteByKey(String)\`, \`rebuildIndex()\`. Hãy viết \`CacheControlMBean\` chỉ công bố hai counter. Giải thích vì sao những method còn lại có thể vẫn là public trong Java nhưng không trở thành JMX operation của Standard MBean.

**Bài 2 — Setter ẩn.** \`WorkerPool\` có \`getConcurrency()\` và \`setConcurrency(int)\`. Management interface chỉ khai báo \`getConcurrency()\`. Hỏi attribute \`Concurrency\` trên JMX có write được không theo Standard MBean contract? Không, nếu không có setter tương ứng được công bố bởi interface/assembler.

**Bài 3 — Interface đặt tên khác.** \`RabbitQueueAdmin\` implements \`QueueAdminMBean\` thay vì \`RabbitQueueAdminMBean\`. Hãy dùng \`StandardMBean\` wrapper để chỉ rõ interface quản trị khi đăng ký.

**Bài 4 — Spring proxy.** Một service \`@Transactional\` bị JDK dynamic proxy. Exporter không nhận diện management interface mong muốn. Đề xuất một adapter \`WorkerStatus\` độc lập, inject service proxy rồi export adapter, để tránh phụ thuộc vào kiểu proxy của domain service.

**Bài 5 — Negative test.** Viết assertion trên \`MBeanInfo\` chứng minh có operation \`requestPause\` nhưng không có operation \`deleteAllData\`. Giải thích vì sao test vắng mặt quan trọng ngang với test có mặt.

**Bài 6 — Security.** Method \`resetStatistics()\` thuộc management interface. Nó có tự an toàn vì được whitelist không? Không: vẫn cần quyền, audit, precondition và xác minh hiệu ứng.

## Tổng kết

Management interface là cách thiết lập ranh giới rõ ràng giữa **API Java nội bộ** và **API quản trị qua JMX**. Trong Standard MBean và MXBean, chỉ những thành viên thuộc interface quản trị được chọn mới được công bố; các public method khác của implementation không tự trở thành JMX operation. Spring \`MBeanExporter\` có thể quản lý đăng ký/lifecycle, còn annotation-driven export có quy tắc chọn member khác, vì vậy cần xác định export path thực tế. Thiết kế tốt là dùng interface nhỏ hoặc management adapter, giữ ObjectName và ownership rõ ràng, kiểm chứng danh sách công bố bằng \`MBeanInfo\` và bảo vệ connector/operation bằng quyền thích hợp. Đó là nền tảng để ẩn phương thức không thuộc giao diện quản trị một cách có chủ đích, lâu dài và có thể kiểm chứng.
