# Kiểm soát điều gì được public nhưng không được phơi bày trong MBean giao diện

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **Java API public** với **giao diện quản trị được công bố qua JMX**.
- Xác định chính xác thuộc tính và thao tác nào của MBean có thể được công cụ JMX nhìn thấy và gọi.
- Thiết kế Standard MBean, MXBean hoặc Spring-managed MBean có **hợp đồng quản trị tối thiểu**, tránh xuất các phương thức nội bộ hoặc dữ liệu nhạy cảm.
- Hiểu rằng giới hạn giao diện MBean và cấu hình quyền truy cập JMX là hai lớp kiểm soát bổ sung, cần áp dụng đồng thời.
- Tạo lớp adapter, DTO/snapshot, metadata hoặc annotation phù hợp; kiểm tra khả năng công bố bằng \`MBeanInfo\` thay vì suy đoán.
- Nhận diện những đường rò thông tin thường gặp qua getter, operation, exception, notification, \`ObjectName\` và cấu hình exporter.

## 2. “Public” có ba nghĩa cần phân biệt

Trong Java và JMX, từ *public* dễ gây hiểu nhầm:

1. **Java public:** method hoặc class có thể được mã Java khác truy cập theo quy tắc visibility của ngôn ngữ.
2. **JMX exposed:** thuộc tính hoặc operation thực sự được MBeanServer công bố thông qua giao diện MBean và metadata của nó.
3. **Network accessible:** client bên ngoài có đường kết nối tới JMX connector và được cơ chế xác thực/phân quyền cho phép.

Ba phạm vi này **không đồng nhất**. Một \`public void deleteEverything()\` trong service không tự động trở thành operation JMX chỉ vì method được khai báo public. Ngược lại, nếu developer cố ý đưa method đó vào Standard MBean interface hoặc xuất qua Spring JMX metadata, nó có thể trở thành thao tác quản trị nguy hiểm dù server chỉ chạy nội bộ.

\`\`\`text
Ứng dụng Spring / Java
+--------------------------------------------------+
| Service Java                                      |
| public refreshInternalIndex()                     |
| public loadCredentials()                          |
| public getQueueDepth()                            |
|                                                  |
|     [BỘ LỌC HỢP ĐỒNG QUẢN TRỊ]                    |
|     Chỉ chọn chức năng phục vụ vận hành           |
|                  |                               |
|                  v                               |
| MBean interface / exporter metadata              |
|   getQueueDepth()          [READ]                 |
|   refreshIndexSafely()     [CONTROLLED ACTION]    |
+------------------|-------------------------------+
                   v
             MBeanServer
                   |
             JMX connector
                   |
          [AUTHENTICATION / AUTHORIZATION]
                   |
             JMX client
\`\`\`

**Nguyên tắc:** công bố qua JMX chỉ những năng lực quản trị thực sự cần thiết, với kiểu dữ liệu và tác dụng phụ được kiểm soát rõ ràng. Không lấy “method là public” làm tiêu chí tự động xuất JMX.

## 3. MBean interface là danh sách cho phép

Với **Standard MBean**, interface theo quy ước \`TênClassMBean\` tạo một hợp đồng JMX rõ ràng. Những getter/setter và method trên interface là bề mặt được MBeanServer nhận diện theo quy tắc Standard MBean.

Ví dụ, một service quản lý cache có nhiều method công khai cho ứng dụng:

\`\`\`java
package example.cache;

public final class ProductCacheService {
    public long size() { return 256L; }

    public void clearCacheInternal() {
        // Thao tác nội bộ, có thể đắt hoặc làm thay đổi trạng thái.
    }

    public String loadSecretConfiguration() {
        return "sensitive-value"; // Chỉ minh họa, không dùng trong code thật.
    }
}
\`\`\`

Không nên xuất nguyên service thành giao diện quản trị tùy tiện. Hãy tạo một adapter với interface MBean chỉ cho phép truy cập phần an toàn:

\`\`\`java
package example.cache;

public interface ProductCacheMonitorMBean {
    long getEntryCount();
    boolean isHealthy();
}
\`\`\`

\`\`\`java
package example.cache;

public final class ProductCacheMonitor
        implements ProductCacheMonitorMBean {

    private final ProductCacheService cache;

    public ProductCacheMonitor(ProductCacheService cache) {
        this.cache = cache;
    }

    @Override
    public long getEntryCount() {
        return cache.size();
    }

    @Override
    public boolean isHealthy() {
        return true; // Thay bằng phép kiểm tra sức khỏe thực tế.
    }

    // Method public này không thuộc ProductCacheMonitorMBean.
    // Standard MBean interface không công bố nó thành operation.
    public void internalMaintenance() {
        cache.clearCacheInternal();
    }
}
\`\`\`

Như vậy, client JMX quan sát \`EntryCount\` và \`Healthy\`; nó không thể tự gọi \`internalMaintenance\` qua hợp đồng Standard MBean mặc dù method đó là public trong Java.

Điểm cần nhớ:

- Interface \`ProductCacheMonitorMBean\` chính là danh sách những năng lực cần công bố.
- Tên \`getEntryCount\` tạo thuộc tính JMX \`EntryCount\` chỉ đọc.
- Tên \`isHealthy\` tạo thuộc tính JMX \`Healthy\` chỉ đọc.
- Nếu interface khai báo \`setEntryCount(long)\`, JMX có thể có setter tương ứng; với số liệu đo lường, không nên cho phép sửa như vậy.
- Method \`internalMaintenance\` không có trên interface quản trị nên không trở thành operation thuộc hợp đồng Standard MBean chỉ vì được định nghĩa public.

## 4. Ví dụ hoàn chỉnh: đăng ký và kiểm tra bề mặt công bố

Ví dụ sau chỉ sử dụng JDK chuẩn, giúp chứng minh sự khác biệt giữa các Java public method và MBean interface.

### 4.1. Khai báo lớp

\`\`\`java
package example.jmx;

public interface WorkerMonitorMBean {
    int getActiveWorkers();
    boolean isPaused();
    void resume();
}
\`\`\`

\`\`\`java
package example.jmx;

public final class WorkerMonitor implements WorkerMonitorMBean {
    private volatile boolean paused;
    private volatile int activeWorkers = 4;

    @Override
    public int getActiveWorkers() {
        return activeWorkers;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void resume() {
        paused = false;
    }

    // Java public, nhưng không nằm trong WorkerMonitorMBean:
    public String readInternalConnectionString() {
        return "internal-example"; // Giá trị minh họa, không dùng bí mật thật.
    }

    public void stopAllServicesInternal() {
        // Không công bố qua giao diện quản trị.
    }
}
\`\`\`

\`WorkerMonitorMBean\` cho phép đọc \`ActiveWorkers\`, đọc \`Paused\` và gọi \`resume\`. Nó không công bố operation \`stopAllServicesInternal\` hoặc \`readInternalConnectionString\`.

### 4.2. Đăng ký vào MBeanServer và khám phá metadata

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxExposureDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=WorkerMonitor,name=Primary"
        );

        server.registerMBean(new WorkerMonitor(), name);
        try {
            MBeanInfo info = server.getMBeanInfo(name);

            System.out.println("Attributes:");
            for (MBeanAttributeInfo attribute
                    : info.getAttributes()) {
                System.out.printf(
                    "%s readable=%s writable=%s%n",
                    attribute.getName(),
                    attribute.isReadable(),
                    attribute.isWritable()
                );
            }

            System.out.println("Operations:");
            for (MBeanOperationInfo operation
                    : info.getOperations()) {
                System.out.println(operation.getName());
            }

            System.out.println("ActiveWorkers = " +
                server.getAttribute(name, "ActiveWorkers"));
            server.invoke(
                name,
                "resume",
                new Object[0],
                new String[0]
            );
            System.out.println("Paused = " +
                server.getAttribute(name, "Paused"));
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả quan trọng: metadata cho biết \`ActiveWorkers\` và \`Paused\` là thuộc tính chỉ đọc; \`resume\` là operation. Các public method nội bộ không xuất hiện. Dòng \`import java.util.Arrays;\` không cần thiết cho hành vi ví dụ và có thể bỏ trong triển khai tối giản.

Đây là cách xác minh trực tiếp hợp đồng runtime. Khi đánh giá MBean, không chỉ đọc code rồi kết luận; nên dùng \`getMBeanInfo\` và thử các lệnh được cho phép theo yêu cầu vận hành.

### 4.3. Thử gọi method không được công bố

\`\`\`java
try {
    server.invoke(
        name,
        "stopAllServicesInternal",
        new Object[0],
        new String[0]
    );
} catch (javax.management.ReflectionException expected) {
    System.out.println(
        "Operation không được công bố: " +
        expected.getClass().getSimpleName()
    );
}
\`\`\`

Với Standard MBean trên, operation này không nằm trong hợp đồng JMX nên lệnh \`invoke\` không thể định tuyến như một operation được công bố. Các loại exception cụ thể có thể phụ thuộc implementation và lỗi thực tế; điều cần kiểm tra là metadata không chứa operation và lời gọi không thành công.

## 5. Getter cũng là một hình thức phơi bày

Một sai lầm phổ biến là nghĩ chỉ operation mới nguy hiểm vì operation “thực hiện hành động”. Getter cũng có thể tiết lộ nhiều thông tin.

Ví dụ các phương thức **không nên đưa nguyên vẹn ra JMX**:

\`\`\`java
String getDatabasePassword();
String getBearerToken();
Map<String, String> getAllEnvironmentVariables();
String getJdbcUrlWithCredentials();
List<Customer> getRecentCustomers();
Throwable getLastFailureWithSensitiveContext();
\`\`\`

Ngay cả getter chỉ đọc cũng có thể:

- Làm lộ thông tin xác thực, endpoint nội bộ, token hoặc khóa ký.
- Tiết lộ dữ liệu cá nhân, payload, request header hoặc lịch sử thao tác người dùng.
- Dẫn tới kết quả quá lớn, tốn bộ nhớ và băng thông nếu trả về toàn bộ collection.
- Tạo side effect không rõ ràng nếu getter gọi truy vấn nặng hoặc thay đổi trạng thái.
- Cho phép attacker suy ra cấu trúc nội bộ hoặc thời điểm xử lý tác vụ.

Thay vì công bố dữ liệu thô, hãy xuất **số liệu tổng hợp** hoặc **trạng thái đã giới hạn**:

| Không nên phơi bày | Dạng quản trị an toàn hơn |
| --- | --- |
| Mật khẩu kết nối cơ sở dữ liệu | \`DatabaseConnectionHealthy: boolean\` |
| Toàn bộ biến môi trường | \`ConfigurationLoaded: boolean\` |
| Danh sách khách hàng | \`ActiveCustomerCount: long\` |
| Toàn bộ queue payload | \`QueueDepth: long\`, \`OldestMessageAgeMs: long\` |
| Toàn bộ stack trace có dữ liệu yêu cầu | \`LastErrorCode: String\`, \`ErrorCount: long\` |
| Danh sách token đang hiệu lực | \`ActiveSessionCount: long\` |
| Cấu hình chi tiết có bí mật | \`ConfigVersion: String\`, \`LastReloadStatus: String\` |

Một giá trị như \`LastErrorCode\` cũng cần được thiết kế: mã lỗi do ứng dụng kiểm soát thường an toàn hơn cách xuất trực tiếp exception message từ thư viện hoặc dịch vụ bên ngoài.

## 6. Operation là quyền điều khiển, phải giới hạn có chủ đích

Operation có thể mang tính quan sát hoặc làm thay đổi trạng thái. Cần phân biệt để quyết định có công bố hay không.

| Operation | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| \`getStatus()\` | Thấp nếu dữ liệu đã lọc. | Có thể công bố; ưu tiên attribute khi là phép đọc đơn giản. |
| \`refreshMetrics()\` | Có thể tạo tải. | Công bố nếu có giới hạn tần suất hoặc chi phí hợp lý. |
| \`clearCache()\` | Thay đổi trạng thái, tăng tải downstream. | Chỉ mở cho vận hành cần thiết, có quyền thích hợp. |
| \`reloadConfiguration()\` | Có thể làm thay đổi hệ thống. | Đảm bảo có validation và trạng thái kết quả. |
| \`pauseConsumers()\` | Dừng xử lý nghiệp vụ. | Cần quyền rõ ràng và guardrail. |
| \`deleteAllRecords()\` | Hủy dữ liệu. | Thông thường không nên phơi bày dưới dạng JMX operation. |
| \`executeCommand(String)\` | Bề mặt thực thi lệnh tùy ý. | Không công bố. |
| \`getFileContents(String)\` | Có thể lộ file. | Không công bố dạng tùy ý. |

Hãy đặt câu hỏi trước khi thêm operation:

1. **Ai thực sự cần thao tác này?** Nhóm vận hành có nhu cầu được xác định hay chỉ tiện cho debug?
2. **Có thể làm an toàn hơn không?** Ví dụ “reload một cấu hình đã kiểm tra” thay vì “ghi bất kỳ giá trị cấu hình”.
3. **Thao tác có thể lặp lại không?** Nếu client timeout, lời gọi đã chạy hay chưa?
4. **Có giới hạn chi phí không?** Tránh operation gây tải lớn hoặc khóa vô hạn.
5. **Có cách kiểm tra kết quả không?** Công bố trạng thái, thời điểm gần nhất hoặc mã kết quả giới hạn.
6. **Có cần authorization bổ sung không?** Một quyền đọc toàn bộ MBean không nên tự động suy ra quyền reset/stop.

Không coi JMX là kênh “chỉ dùng nội bộ nên mọi operation đều an toàn”. Về sau connector có thể được bật, công cụ giám sát có thể được cấp quyền và tài khoản có thể bị sử dụng ngoài phạm vi dự định.

## 7. Tách lớp adapter quản trị khỏi service nghiệp vụ

Một thiết kế có thể kiểm soát tốt:

\`\`\`text
JMX client
     |
     v
MBeanServer
     |
     v
Management adapter (API nhỏ, ổn định)
     |
     | Chỉ đọc số liệu tổng hợp
     | Gọi hành động đã được kiểm soát
     v
Service / Repository / Messaging infrastructure
     |
     v
Dữ liệu nghiệp vụ, secrets, cấu hình nội bộ
\`\`\`

### 7.1. Ưu điểm

- **Giảm bề mặt công bố:** interface của adapter chỉ chứa những phần đã chủ động chọn.
- **Giảm phụ thuộc:** MBean không phải hợp đồng Java API toàn bộ của service.
- **Cho phép đổi implementation:** service có thể refactor mà tên thuộc tính JMX vẫn ổn định.
- **Dễ kiểm tra:** metadata JMX là tập hợp nhỏ để so sánh với hợp đồng mong đợi.
- **Kiểm soát chi phí:** adapter có thể snapshot/cache chỉ số thay vì truy vấn trực tiếp dữ liệu lớn.
- **Dễ quản lý vòng đời:** đăng ký và hủy MBean cùng vòng đời ứng dụng.

### 7.2. Ví dụ adapter chỉ đọc và thao tác có kiểm soát

\`\`\`java
public interface ImportJobAdminMBean {
    boolean isRunning();
    long getProcessedCount();
    String getLastRunStatus();
    void requestGracefulStop();
}
\`\`\`

Đừng công bố \`getRawJobPayloads()\`, \`getSchedulerCredentials()\`, \`terminateProcessNow()\` nếu không có nhu cầu vận hành và chính sách kiểm soát cụ thể. Lời gọi \`requestGracefulStop()\` nên chuyển một yêu cầu dừng có điều kiện tới service, thay vì trực tiếp phá hủy tài nguyên.

Trong hệ thống thật, thêm kiểm tra trạng thái (ví dụ chỉ dừng khi job cho phép), ghi nhận audit và đảm bảo lệnh có xử lý idempotency phù hợp.

## 8. Standard MBean, MXBean, DynamicMBean: đường công bố khác nhau

### 8.1. Standard MBean

**Quy tắc chính:** interface \`FooMBean\` xác định những thuộc tính/operation xuất ra JMX. Cách này dễ đọc, đặc biệt phù hợp khi bề mặt quản trị nhỏ và ổn định.

\`\`\`java
public interface OrderQueueMBean {
    long getBacklog();
    void pause();
}
\`\`\`

Các method \`public\` khác trên object implement interface không tự động là operation JMX nếu không thuộc interface hoặc cơ chế xuất tương ứng.

### 8.2. MXBean

MXBean có thể ánh xạ các kiểu Java sang open data chuẩn. Điều này giảm phụ thuộc vào class tùy chỉnh ở client, nhưng **không tự lọc dữ liệu nhạy cảm**. Nếu interface MXBean công bố một getter chứa trường nhạy cảm có thể ánh xạ được, trường đó vẫn có nguy cơ đi qua JMX.

\`\`\`java
import javax.management.MXBean;

@MXBean
public interface PoolHealthMXBean {
    int getActiveConnections();
    int getIdleConnections();
}
\`\`\`

Tối ưu: thiết kế interface MXBean chỉ gồm kiểu và trạng thái công bố có chủ đích, tránh trả nguyên object nghiệp vụ đa trường nếu không kiểm soát schema ánh xạ.

### 8.3. DynamicMBean và Open MBean

Với \`DynamicMBean\`, developer tự hiện thực:

- \`getAttribute\`, \`setAttribute\`.
- \`getAttributes\`, \`setAttributes\`.
- \`invoke\`.
- \`getMBeanInfo\`.

Điều này cho phép kiểm soát tên và metadata khi runtime, nhưng cũng đặt trách nhiệm giữ **metadata nhất quán với lệnh được chấp nhận** vào developer. Nếu \`getMBeanInfo()\` không hiển thị một operation nhưng \`invoke()\` vẫn thực thi nó, một client có thể cố gọi operation ẩn bằng tên; đó không phải cách kiểm soát quyền an toàn. Phải chặn hành vi thực tế ngay tại \`invoke\`, không chỉ giấu khỏi metadata.

**Open MBean** sử dụng metadata kiểu chuẩn như \`OpenType\`, \`CompositeType\` và \`TabularType\`. Nó giúp client hiểu cấu trúc dữ liệu nhưng không cung cấp authorization hay tự động che các field nhạy cảm.

## 9. Spring Framework: @ManagedResource, @ManagedAttribute và @ManagedOperation

Spring JMX hỗ trợ xuất bean qua \`MBeanExporter\` và metadata như:

- \`@ManagedResource\`: mô tả tài nguyên quản trị.
- \`@ManagedAttribute\`: đánh dấu getter/setter được công bố như thuộc tính.
- \`@ManagedOperation\`: đánh dấu method được công bố như operation.
- \`@ManagedOperationParameter\`: mô tả tham số operation.

Ví dụ:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Import",
    description = "Safe import worker management"
)
public class ImportWorkerManagement {

    @ManagedAttribute
    public long getProcessedCount() {
        return 100L; // Lấy số liệu từ service thực tế.
    }

    @ManagedAttribute
    public boolean isRunning() {
        return true; // Lấy trạng thái thực tế.
    }

    @ManagedOperation(description = "Request a safe stop")
    public void requestStop() {
        // Chuyển yêu cầu hợp lệ đến service.
    }

    // Không có @ManagedAttribute/@ManagedOperation:
    public String internalDebugInformation() {
        return "internal";
    }
}
\`\`\`

Với **cấu hình exporter sử dụng metadata annotation** (chẳng hạn \`MetadataMBeanInfoAssembler\` và \`AnnotationJmxAttributeSource\`), chỉ những phần được đánh dấu phù hợp mới được công bố. Không kết luận từ annotation trên code nếu chưa xác nhận exporter được cấu hình thực sự.

### 9.1. Cấu hình exporter tường minh trong Spring thuần

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfig {

    @Bean
    public MBeanExporter managementExporter(
            ImportWorkerManagement managementBean) {
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
        exporter.setBeans(Map.of(
            "importWorkerManagement", managementBean
        ));
        return exporter;
    }
}
\`\`\`

Đoạn này minh họa exporter cấu hình cụ thể và danh sách bean được chọn. Với Spring Boot, các cấu hình tự động về JMX phụ thuộc dependency và thiết lập ứng dụng, nên cần tránh tạo hai exporter quản lý trùng \`ObjectName\`.

### 9.2. Những bẫy khi dùng exporter

1. **Auto-detect quá rộng:** cấu hình phát hiện/exporter không giới hạn có thể đăng ký nhiều bean hơn mong muốn, tùy cơ chế assembler và exporter. Chọn danh sách rõ ràng hoặc quy tắc phát hiện đã kiểm soát.
2. **Xuất cả getter:** một số strategy assembler có thể dùng phản xạ trên public method. Đừng giả định annotation sẽ chặn mọi method nếu config không dùng assembler dựa trên annotation.
3. **Tên ObjectName mang dữ liệu nhạy cảm:** tránh key property chứa user ID, token hoặc thông tin cá nhân.
4. **Trùng exporter hoặc manual register:** cùng một tên JMX không thể đăng ký hai lần trên cùng MBeanServer.
5. **Đổi cấu hình vô tình mở operation:** sau khi thay assembler/exporter, kiểm tra \`MBeanInfo\` thực tế.
6. **Nhầm với HTTP/Actuator:** cấu hình endpoint web và cấu hình xuất JMX là các bề mặt khác nhau; phải đánh giá từng cơ chế riêng.

## 10. Tối thiểu hóa dữ liệu được công bố

Có hai câu hỏi bổ sung:

- **Có cần công bố chức năng này không?** Chỉ giữ các khả năng vận hành cần thiết.
- **Nếu có, dữ liệu cụ thể nào cần rời khỏi ứng dụng?** Chỉ trả về lượng thông tin tối thiểu.

### 10.1. Snapshot đã lọc

Thay vì công bố:

\`\`\`java
public Map<String, String> getRuntimeConfiguration();
\`\`\`

hãy cung cấp:

\`\`\`java
public String getConfigurationVersion();
public boolean isConfigLoaded();
public long getLastSuccessfulReloadEpochMillis();
\`\`\`

Khi cần thông tin lỗi, sử dụng mã lỗi/cấp độ đã được kiểm soát; tránh trả exception message có thể chứa URI, SQL, request payload hoặc token.

### 10.2. Giới hạn kích thước và chi phí

Getter được công cụ giám sát gọi nhiều lần; cần:

- Trả về số liệu tổng hợp, không xuất toàn bộ bản ghi nghiệp vụ.
- Đặt giới hạn số phần tử với collection/table được công bố.
- Không duyệt toàn bộ cơ sở dữ liệu ở mỗi lần đọc.
- Không phát sinh thao tác bất ngờ trong getter.
- Sử dụng snapshot/cache ngắn hạn nếu lấy dữ liệu gốc tốn tài nguyên.
- Xác định rõ thời điểm và mức nhất quán của số liệu.

Một interface có vẻ chỉ đọc vẫn có thể là vector gây tải nếu \`getDetails()\` trả hàng triệu đối tượng hoặc truy vấn quá nặng.

## 11. Metadata không phải tường bảo mật

\`MBeanInfo\` giúp client khám phá interface đã đăng ký, nhưng metadata chỉ mô tả API. Giấu operation khỏi metadata **không thay thế** việc chặn lời gọi.

Với \`DynamicMBean\`:

\`\`\`java
@Override
public Object invoke(
        String action,
        Object[] params,
        String[] signature)
        throws MBeanException, ReflectionException {

    if ("refreshSafeSnapshot".equals(action)) {
        refreshSafeSnapshot();
        return null;
    }

    throw new ReflectionException(
        new NoSuchMethodException(action)
    );
}
\`\`\`

Code cần từ chối mọi tên operation ngoài danh sách cho phép. Tương tự, \`getAttribute\` phải từ chối tên không nằm trong hợp đồng, và \`setAttribute\` phải từ chối thuộc tính không cho ghi. Nếu developer chỉ sửa \`getMBeanInfo()\` mà vẫn để \`invoke()\` gọi bất kỳ method nào qua reflection, MBean có nguy cơ bị điều khiển trái mục đích.

Một kiểm tra phù hợp bao gồm cả **metadata** và **hành vi**: kiểm tra những gì xuất hiện, đồng thời thử gọi một tên không được cấp phép và xác nhận nó không chạy.

## 12. Giới hạn truy cập ở lớp connector và quyền

Ngay cả khi interface MBean được thiết kế tốt, connector JMX còn quyết định ai có thể kết nối và thực hiện lệnh. Một số nguyên tắc vận hành:

- Không bật remote JMX cho mọi môi trường khi không có nhu cầu.
- Khi cần truy cập từ xa, bảo vệ connector bằng xác thực, mã hóa và giới hạn nguồn mạng phù hợp.
- Áp dụng quyền đọc/quản trị theo tính năng mà nền tảng và cơ chế connector hỗ trợ; tài khoản chỉ cần monitoring không nên có quyền gọi operation thay đổi trạng thái.
- Bảo vệ thông tin đăng nhập, cấu hình TLS và secret khỏi log hoặc file không an toàn.
- Xem xét JMX agent, credential store, vận hành container và cách mở port RMI/JMX theo môi trường.
- Audit thao tác tác động trạng thái ở lớp ứng dụng hoặc hạ tầng phù hợp, đặc biệt các operation nguy hiểm.

**Hai lớp kiểm soát:**

\`\`\`text
Lớp 1: Hợp đồng MBean
    Chính xác attribute/operation nào tồn tại?

Lớp 2: Kết nối và authorization
    Ai có thể xem hoặc gọi chúng?

Cả hai cùng quan trọng.
\`\`\`

Nếu interface đã lộ method xóa dữ liệu, phân quyền chặt chỉ giảm mức tiếp cận; giảm bề mặt MBean ngay từ thiết kế vẫn là lựa chọn cần thiết.

## 13. Kiểm tra bề mặt JMX thực tế

Khi triển khai, hãy truy xuất metadata sau khi đăng ký:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s: read=%s, write=%s%n",
        attr.getName(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("operation=" + op.getName());
}
\`\`\`

Sau đó so sánh với hợp đồng đã thiết kế. Một bản ghi ví dụ:

\`\`\`text
Expected attributes:
- ActiveWorkers: readable=true, writable=false
- Paused:        readable=true, writable=false

Expected operations:
- resume():     allowed

Not exposed:
- readInternalConnectionString()
- stopAllServicesInternal()
\`\`\`

Đồng thời kiểm tra trường hợp bị từ chối:

\`\`\`java
try {
    server.getAttribute(name, "InternalConnectionString");
    throw new AssertionError(
        "Sensitive attribute unexpectedly exposed"
    );
} catch (javax.management.AttributeNotFoundException expected) {
    // Đúng: attribute không được công bố.
}
\`\`\`

Với \`DynamicMBean\`, cũng phải xác nhận implementation từ chối cả các lời gọi không có trong metadata. Với ứng dụng có nhiều connector hoặc exporter, thử đúng \`MBeanServer\` và \`ObjectName\` mà client vận hành sử dụng.

## 14. Tổ chức hợp đồng và quy tắc thay đổi

Hợp đồng quản trị có thể ổn định hơn class nội bộ:

\`\`\`text
com.example.orders:type=Queue,name=Import

Attributes:
  Backlog            Long    read-only
  Healthy            Boolean read-only
  LastProcessedAt    Long    read-only

Operations:
  requestPause()     void    state-changing
\`\`\`

Khi muốn thêm khả năng mới, ưu tiên quy trình:

1. Mô tả nhu cầu vận hành và nhóm người sử dụng.
2. Chọn một attribute hoặc operation có tên, kiểu và ngữ nghĩa rõ ràng.
3. Xác định thông tin có thể lộ, side effect và tải tối đa.
4. Thêm vào interface/metadata có chủ đích.
5. Kiểm tra runtime \`MBeanInfo\` và quyền kết nối cần thiết.
6. Ghi nhận tương thích client nếu đổi tên, kiểu hoặc signature.
7. Quan sát sử dụng sau khi triển khai và gỡ những chức năng không còn cần.

Không dùng wildcard hoặc reflection tự động để xuất “mọi public method” khi chưa có cơ chế kiểm soát danh sách cho phép.

## 15. Các tình huống thiết kế và quyết định

### 15.1. Cần biết cache có khỏe không

**Nhu cầu:** công cụ vận hành muốn xem cache hoạt động.

**Thiết kế:** \`Healthy\`, \`EntryCount\`, \`HitRate\` (nếu tính toán ổn định), \`LastRefreshTime\`.

**Tránh:** \`dumpAllEntries()\`, \`getAllKeysWithCustomerIds()\`, \`getBackingStoreCredentials()\`.

### 15.2. Cần reset một worker đang lỗi

**Nhu cầu:** nhân viên vận hành muốn yêu cầu worker tự phục hồi.

**Thiết kế:** \`requestRestart()\` hoặc \`requestGracefulStop()\` với kiểm tra trạng thái, không chấp nhận tham số tùy ý nguy hiểm.

**Tránh:** \`killProcess(int)\`, \`executeShell(String)\`, \`deleteCheckpoint(Path)\`.

Nếu request có tác động bất đồng bộ, công bố \`LastRestartStatus\` hoặc \`CurrentState\` để client kiểm tra kết quả, thay vì ngầm hiểu lệnh đã hoàn tất ngay khi \`invoke\` trả về.

### 15.3. Cần chẩn đoán lỗi cơ sở dữ liệu

**Nhu cầu:** biết mức độ lỗi kết nối.

**Thiết kế:** \`ConnectionPoolActive\`, \`ConnectionPoolIdle\`, \`LastConnectionErrorCode\`, \`ConnectionHealthy\`.

**Tránh:** \`JdbcUrlWithPassword\`, \`LastSqlWithParameters\`, toàn bộ stack trace có dữ liệu nghiệp vụ.

### 15.4. Cần thống kê theo tenant

**Nhu cầu:** số lượng request và queue theo từng tenant.

**Thiết kế:** chỉ số tổng hợp không chứa PII; nếu dùng \`TabularData\`, giới hạn số hàng và cân nhắc định danh tenant ở mức cho phép.

**Tránh:** trả nguyên danh sách người dùng, đơn hàng, token hoặc địa chỉ email làm index của bảng JMX.

## 16. Bài tập thực hành

### Bài tập 1 — Thiết kế interface tối thiểu

Cho một \`PaymentService\` với các public method \`getPendingCount()\`, \`getPaymentById(id)\`, \`refundPayment(id)\`, \`getProviderApiKey()\` và \`getLastRetryStatus()\`.

Hãy thiết kế \`PaymentMonitorMBean\` chỉ gồm những thuộc tính cần thiết để quan sát. Giải thích tại sao không xuất \`getPaymentById\`, \`refundPayment\` và \`getProviderApiKey\` qua JMX.

**Gợi ý:** \`PendingCount\`, \`LastRetryStatus\` là các ứng viên có thể phù hợp sau khi kiểm soát ngữ nghĩa của giá trị trả về.

### Bài tập 2 — Chứng minh interface chặn method

Dùng \`WorkerMonitorMBean\` và \`WorkerMonitor\` ở trên. Đăng ký vào platform MBeanServer, gọi \`getMBeanInfo\` và liệt kê các operation. Thử gọi \`stopAllServicesInternal\` qua \`MBeanServer.invoke\`.

**Mục tiêu:** hiểu khác biệt giữa Java public visibility và operation JMX được công bố.

### Bài tập 3 — Spring annotation

Tạo \`@ManagedResource\` chỉ chứa hai \`@ManagedAttribute\` read-only và một \`@ManagedOperation\` an toàn. Cấu hình exporter dùng annotation-based assembler; xác nhận getter công khai không annotate không xuất hiện trong metadata.

**Mục tiêu:** biết rằng annotation chỉ có ý nghĩa khi exporter áp dụng đúng strategy.

### Bài tập 4 — Negative test

Tạo danh sách các tên **không được công bố** như \`Password\`, \`RawPayload\`, \`ExecuteCommand\`. Kiểm tra metadata không chứa chúng và thử gọi qua API JMX để xác nhận các thao tác bị từ chối.

**Mục tiêu:** hiểu metadata và hành vi runtime phải nhất quán.

### Bài tập 5 — Review một operation tác động trạng thái

Đánh giá việc xuất \`clearCache()\`: ai cần dùng, tần suất tối đa, điều kiện được gọi, rủi ro tải downstream, kết quả sau lời gọi và lớp quyền cần có. Viết đề xuất giao diện an toàn hơn nếu cần.

## 17. Câu hỏi ôn tập

**1. Có phải mọi public method của Java object đều là JMX operation?** Không. Với Standard MBean, hợp đồng interface quyết định thuộc tính và operation được công bố.

**2. Getter chỉ đọc có thể nguy hiểm không?** Có. Getter có thể tiết lộ secret, dữ liệu cá nhân hoặc gây tải lớn.

**3. Nếu giấu một operation khỏi getMBeanInfo nhưng vẫn xử lý nó trong DynamicMBean.invoke thì đã an toàn chưa?** Chưa. Client vẫn có thể thử gọi theo tên. Implementation phải từ chối operation không được cho phép.

**4. Spring @ManagedOperation tự động khiến mọi bean có method đó xuất JMX không?** Không. Cần MBean exporter và cấu hình assembler phù hợp.

**5. Hạn chế JMX connector truy cập có thay thế việc thiết kế interface tối thiểu không?** Không. Cần cả giới hạn chức năng đã xuất lẫn kiểm soát đối tượng có quyền truy cập.

**6. Vì sao nên dùng adapter riêng?** Để tách API quản trị khỏi implementation, lọc dữ liệu, kiểm soát tác dụng phụ và giữ hợp đồng ổn định.

**7. Khi nào cần thêm operation reset/reload?** Khi có nhu cầu vận hành xác định, điều kiện thực thi an toàn, giới hạn quyền, cơ chế quan sát kết quả và khả năng xử lý lỗi.

**8. Vì sao không nên xuất getter toàn bộ cấu hình môi trường?** Vì cấu hình có thể chứa credential, topology, dữ liệu nhạy cảm hoặc nội dung không cần thiết cho monitoring.

## 18. Tổng kết

**MBean interface là ranh giới công bố các năng lực quản trị.** Java visibility, metadata JMX và khả năng truy cập qua mạng là những khái niệm riêng. Với Standard MBean, interface xác định danh sách thuộc tính/operation; với MXBean và DynamicMBean, hợp đồng kiểu dữ liệu và implementation phải kiểm soát tương ứng; với Spring, exporter và assembler quyết định những metadata nào có hiệu lực.

Thiết kế tốt bắt đầu từ danh sách cho phép nhỏ, dữ liệu tổng hợp tối thiểu và operation có kiểm soát. Luôn kiểm tra metadata trên \`MBeanServer\`, đảm bảo implementation thực sự từ chối những thao tác ngoài hợp đồng, rồi bảo vệ connector và quyền truy cập ở lớp vận hành.

## Tài liệu tham khảo

- Java SE 21 — JMX \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — JMX \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`DynamicMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/DynamicMBean.html
- Java SE 21 — JMX specification and API: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html