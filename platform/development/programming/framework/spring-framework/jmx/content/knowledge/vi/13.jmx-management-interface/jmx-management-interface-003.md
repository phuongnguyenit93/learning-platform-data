# MetadataMBeanInfoAssembler và nguồn metadata annotation trong Spring JMX

## 1. Mục tiêu

Trong Spring Framework JMX, \`MetadataMBeanInfoAssembler\` là thành phần chuyển **metadata quản trị** của một bean thành phần mô tả giao diện JMX. Nó trả lời câu hỏi: **JMX client sẽ nhìn thấy những attribute, operation và notification nào, cùng tên và mô tả ra sao?**

Với cấu hình annotation-based, Spring thường sử dụng \`AnnotationJmxAttributeSource\` làm nguồn metadata. Annotation như \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, \`@ManagedOperationParameter\` và \`@ManagedNotification\` tạo hợp đồng quản trị ngay bên cạnh mã Java. \`MetadataMBeanInfoAssembler\` đọc hợp đồng đó thông qua \`JmxAttributeSource\` và xây dựng thông tin để \`MBeanExporter\` tạo/đăng ký MBean.

Sau bài này, bạn có thể:

- Phân biệt metadata source, assembler, naming strategy và exporter.
- Giải thích cách annotation từ class, getter/setter và operation trở thành \`MBeanInfo\`.
- Cấu hình \`MetadataMBeanInfoAssembler\` và \`AnnotationJmxAttributeSource\` trong Spring Framework.
- Phân biệt metadata annotation với giao diện quản trị thực tế trên MBeanServer.
- Hiểu ảnh hưởng của bean proxy, method visibility, property conventions và một số trường metadata.
- Kiểm chứng kết quả bằng \`MBeanServer.getMBeanInfo()\` thay vì chỉ nhìn mã nguồn.

## 2. Bản đồ các thành phần

\`\`\`text
          Spring bean class
                |
      @ManagedResource
      @ManagedAttribute
      @ManagedOperation
      @ManagedNotification
                |
                v
    AnnotationJmxAttributeSource
         (JmxAttributeSource)
                |
                v
    MetadataMBeanInfoAssembler
        (MBeanInfoAssembler)
                |
                v
         ModelMBeanInfo
      attributes / operations /
      notifications / descriptor
                |
                v
            MBeanExporter
                |
                v
             MBeanServer
                |
                v
       JConsole / JMX clients
\`\`\`

Một nhánh khác chịu trách nhiệm đặt tên:

\`\`\`text
@ManagedResource(objectName="...")
               |
               v
   AnnotationJmxAttributeSource
               |
               v
      MetadataNamingStrategy
               |
               v
           ObjectName
               |
               v
       MBeanExporter
\`\`\`

**Assembler không phải naming strategy.** Assembler quyết định **giao diện quản trị và metadata**. Naming strategy quyết định **định danh \`ObjectName\`**. Exporter kết hợp hai vai trò đó và thực hiện đăng ký với MBeanServer.

## 3. MBeanInfoAssembler là gì?

\`org.springframework.jmx.export.assembler.MBeanInfoAssembler\` là hợp đồng của Spring dùng để xây dựng metadata cho MBean được export từ bean. Một implementation có thể:

- Chọn method nào là getter/setter của managed attribute.
- Chọn method nào là managed operation.
- Gắn description và descriptor metadata.
- Xác định notification metadata.
- Tạo \`ModelMBeanInfo\` cho Spring JMX infrastructure.

\`MetadataMBeanInfoAssembler\` là implementation đọc dữ liệu từ \`JmxAttributeSource\`. Nó khác với những assembler dựa trên convention hoặc explicit method list vì nó dựa trên metadata nguồn được cung cấp.

### Những chiến lược assembler thường gặp

| Assembler | Cách chọn management interface |
|---|---|
| \`MetadataMBeanInfoAssembler\` | Đọc metadata của \`JmxAttributeSource\`, thường từ annotations |
| \`MethodNameBasedMBeanInfoAssembler\` | Chọn method theo danh sách tên/cấu hình |
| \`MethodExclusionMBeanInfoAssembler\` | Loại trừ method theo cấu hình |
| \`InterfaceBasedMBeanInfoAssembler\` | Chọn method thuộc interface được chỉ định |
| \`SimpleReflectiveMBeanInfoAssembler\` | Dựa trên reflection theo chính sách của assembler |

Không phải mọi loại JMX MBean đều cần Spring assembler. Standard MBean và MXBean đã có cơ chế management interface riêng theo JMX specification. Đặc biệt, khi Spring export một bean đã là compliant MBean, đường đi adaptation có thể khác với một POJO được chuyển thành Model MBean bằng assembler.

## 4. Nguồn metadata: JmxAttributeSource

\`org.springframework.jmx.export.metadata.JmxAttributeSource\` là abstraction giúp assembler không phải biết metadata đến từ đâu. Nó cung cấp các đối tượng metadata tương ứng với:

- Class/resource.
- Attribute.
- Operation.
- Operation parameters.
- Notification declarations.

\`AnnotationJmxAttributeSource\` đọc các annotation của Spring JMX và chuyển chúng thành những metadata object đó.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor {

    private volatile int size;

    @ManagedAttribute(description = "Number of entries")
    public int getSize() {
        return size;
    }

    @ManagedOperation(description = "Clear cache statistics")
    public void resetStatistics() {
        size = 0;
    }
}
\`\`\`

Metadata source cung cấp:

\`\`\`text
Class:
  ManagedResource
    objectName = com.example.monitoring:type=Cache,name=Products
    description = Product cache management

Method getSize:
  ManagedAttribute
    description = Number of entries

Method resetStatistics:
  ManagedOperation
    description = Clear cache statistics
\`\`\`

Assembler biến metadata đó thành giao diện JMX, trong đó \`Size\` là attribute và \`resetStatistics\` là operation.

### Một annotation không tự tạo MBean

Việc có \`@ManagedResource\` trên class không tự làm bean xuất hiện trong \`MBeanServer\`. Cần \`MBeanExporter\` (hoặc cơ chế annotation export tạo exporter) được cấu hình đúng và bean đó phải được export.

Tương tự, một bean được đăng ký qua exporter nhưng assembler không đọc metadata annotation có thể cho management interface khác mong muốn.

## 5. Nhóm annotation và vai trò của từng loại

| Annotation | Vị trí | Metadata chủ yếu |
|---|---|---|
| \`@ManagedResource\` | Class/type | MBean description, \`objectName\`, descriptor metadata |
| \`@ManagedAttribute\` | Getter hoặc setter | Mô tả attribute, đơn vị/giới hạn metadata, khả năng trình bày property |
| \`@ManagedOperation\` | Method | Mô tả operation và metadata quản trị |
| \`@ManagedOperationParameter\` | Khai báo metadata tham số operation (thường bên trong \`@ManagedOperationParameters\`) | Tên và mô tả tham số |
| \`@ManagedNotification\` | Class/type, có thể khai báo nhiều | Notification type và mô tả |
| \`@ManagedOperationParameters\` | Method | Container của parameter metadata khi cần |

Ví dụ kết hợp:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import",
    description = "Import worker monitor"
)
@ManagedNotification(
    name = "com.example.worker.finished",
    notificationTypes = {"com.example.worker.finished"},
    description = "Worker finished"
)
public class ImportWorkerMonitor {

    private volatile String status = "IDLE";

    @ManagedAttribute(description = "Current worker status")
    public String getStatus() {
        return status;
    }

    @ManagedOperation(description = "Change worker status")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "newStatus",
            description = "New status value"
        )
    })
    public void changeStatus(String newStatus) {
        status = newStatus;
    }
}
\`\`\`

Trong ví dụ này:

- Class có tên MBean và description.
- Getter tạo attribute quản trị \`Status\`.
- Method tạo operation \`changeStatus\`, với mô tả tham số.
- Annotation notification **mô tả** loại notification có thể được công bố. Nó không tự phát sự kiện.
- Mọi thao tác thay đổi trạng thái vẫn cần thiết kế validation và phân quyền.

Một management interface chỉ nên expose những hành động cần thiết, đặc biệt nếu MBean có thể được truy cập từ xa.

## 6. Cấu hình thủ công assembler và annotation source

Ví dụ trong một ứng dụng Spring Framework thuần:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {

        MetadataNamingStrategy strategy =
            new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

Ở đây:

1. Một \`AnnotationJmxAttributeSource\` được chia sẻ.
2. Assembler đọc metadata qua source.
3. Naming strategy cũng dùng source để tìm \`ObjectName\`.
4. \`MBeanExporter\` dùng cả hai rồi chọn các bean phù hợp để export.

Cấu hình này minh họa cách các thành phần ghép lại với nhau. Trong một ứng dụng dùng \`@EnableMBeanExport\` hoặc Spring Boot auto-configuration, không nên khai báo exporter bổ sung trùng chức năng nếu không có lý do rõ ràng.

### Cấu hình ngắn gọn

Spring Framework hỗ trợ:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Cách này dùng cơ chế annotation-driven JMX export do Spring cung cấp. Spring sẽ thiết lập những thành phần cần thiết thay vì mỗi dự án phải lặp lại toàn bộ boilerplate.

Cần phân biệt hai cách cấu hình: ví dụ thủ công ở trên và \`@EnableMBeanExport\` là những phương án thay thế; ghép cùng lúc có thể dẫn đến nhiều exporter và xung đột ObjectName.

## 7. Assembler chuyển getter/setter thành JMX attribute như thế nào?

Một managed attribute thường tương ứng JavaBean property.

\`\`\`java
private volatile int maxWorkers = 4;

@ManagedAttribute(description = "Maximum concurrent workers")
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute(description = "Maximum concurrent workers")
public void setMaxWorkers(int value) {
    if (value < 1 || value > 128) {
        throw new IllegalArgumentException(
            "maxWorkers must be between 1 and 128"
        );
    }
    maxWorkers = value;
}
\`\`\`

Khi assembler nhận diện cả getter và setter, JMX attribute có thể có metadata:

\`\`\`text
Name: MaxWorkers
Type: int
Readable: true
Writable: true
Description: Maximum concurrent workers
\`\`\`

Nếu chỉ getter được expose, attribute thường là read-only; nếu setter được expose, writable flag có thể bật. Mỗi bên có thể có annotation metadata riêng nên cần giữ mô tả nhất quán, tránh cấu hình mâu thuẫn.

**Chú ý:** \`@ManagedAttribute\` không tự đặt giới hạn \`1..128\` cho giá trị nghiệp vụ. Setter cần validate. JMX client có thể gửi giá trị không hợp lệ hoặc thao tác đồng thời, nên code quản trị phải bảo vệ invariant.

### Getter naming conventions

Các getter như \`getStatus()\` và \`isReady()\` theo JavaBeans conventions có thể trở thành attributes \`Status\` và \`Ready\`. Nhưng đừng tự đoán tên bằng cách cắt chuỗi thủ công; khi cần xác minh, đọc \`MBeanInfo.getAttributes()\`.

## 8. Assembler chuyển method thành JMX operation

Một method được gắn \`@ManagedOperation\` có thể xuất hiện trong \`MBeanOperationInfo\`:

\`\`\`java
@ManagedOperation(description = "Reload non-sensitive configuration")
public void reloadConfiguration() {
    settings.reload();
}
\`\`\`

Khi operation có tham số, metadata có thể cung cấp tên và mô tả để JMX client hiển thị rõ:

\`\`\`java
@ManagedOperation(description = "Set job processing mode")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "mode",
        description = "SAFE or FAST"
    )
})
public void setProcessingMode(String mode) {
    if (!"SAFE".equals(mode) && !"FAST".equals(mode)) {
        throw new IllegalArgumentException("Unsupported mode");
    }
    this.processingMode = mode;
}
\`\`\`

\`MBeanOperationInfo\` có thể bao gồm name, signature, return type và description. Vẫn cần kiểm tra JMX metadata thực tế để xem client nhận được gì.

**Phân biệt:** Method có \`@ManagedOperation\` không nhất thiết trở thành JavaBean setter hoặc JMX attribute. Operation và attribute là hai dạng management interface khác nhau.

## 9. Assembler và class-level metadata

\`@ManagedResource\` cung cấp metadata cấp resource:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor { }
\`\`\`

\`description\` có thể xuất hiện trong \`MBeanInfo.getDescription()\`. Những thuộc tính khác như \`currencyTimeLimit\`, \`log\`, \`logFile\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, \`persistLocation\` liên quan descriptor của Model MBean, với mức độ tác dụng runtime phụ thuộc implementation.

Đừng suy ra rằng:

- \`currencyTimeLimit\` là timeout của HTTP request.
- \`log=true\` tự bật logging ứng dụng theo SLF4J.
- \`persistPolicy\` tự tạo database persistence.
- \`description\` tự định nghĩa quyền truy cập JMX.

Chúng là metadata quản trị; không thay thế cơ chế runtime tương ứng.

### Nguồn metadata có thể thay thế được

Assembler sử dụng abstraction \`JmxAttributeSource\`. Trong dự án dùng annotation, nguồn thường là \`AnnotationJmxAttributeSource\`. Thiết kế tách rời này cho phép cơ chế lắp ráp không phải hardcode toàn bộ cách đọc annotation.

Nhưng trong ứng dụng cụ thể, hãy chọn **một nguồn metadata có hợp đồng rõ ràng**. Không nên tự tạo nhiều annotation source với quy tắc khác nhau cho naming và assembler nếu có thể dẫn đến ObjectName và interface không đồng bộ.

## 10. Autodetect và vai trò của assembler

Trong \`MBeanExporter\`, autodetect có thể giúp chọn bean để export:

\`\`\`java
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

Chế độ này dựa vào assembler để nhận diện những bean phù hợp. Với \`MetadataMBeanInfoAssembler\` và \`AnnotationJmxAttributeSource\`, những bean có metadata quản trị đúng cấu hình là ứng viên.

Đừng nhầm:

- **Autodetect bean:** quyết định bean nào được chọn.
- **Assemble MBeanInfo:** quyết định những thông tin nào được công bố.
- **Naming strategy:** đặt tên JMX.
- **Register:** exporter thực hiện với \`MBeanServer\`.

Nếu sử dụng \`setBeans\` tường minh, tập bean được export có thể bị giới hạn rõ hơn. Nếu không cần autodetect, tắt autodetect có thể là lựa chọn phù hợp để tránh phơi bày bean ngoài ý muốn.

## 11. Bean đã là MBean và bean Java thông thường

Giả sử:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
}

public class QueueMonitor implements QueueMonitorMBean {
    public int getPendingCount() {
        return 7;
    }
}
\`\`\`

Đây là Standard MBean theo convention nếu đăng ký theo JMX. Trong trường hợp đó, interface \`QueueMonitorMBean\` đã xác định management interface.

Với một POJO không triển khai Standard MBean interface nhưng được gắn Spring JMX annotation, Spring có thể sử dụng Model MBean và assembler để xây dựng giao diện quản trị.

Hai đường đi này có thể cùng được \`MBeanExporter\` hỗ trợ, nhưng không thể kết luận mọi MBean đều được assembler quyết định interface theo cùng cách.

| Mô hình | Nguồn giao diện quản trị |
|---|---|
| Standard MBean | Java interface \`XxxMBean\` |
| MXBean | Java interface MXBean và quy tắc OpenType mapping |
| Spring POJO + annotation | Spring metadata source + assembler |
| Dynamic MBean | Implement \`DynamicMBean\` và trả \`MBeanInfo\` |

Việc chọn cách nào tùy mục tiêu: quản trị bean với Spring annotation hay một management interface chuẩn JMX độc lập với Spring.

## 12. Proxy, AOP và đối tượng đích

Trong ứng dụng thực tế, Spring bean có thể là proxy do \`@Transactional\`, \`@Async\` hoặc Spring AOP tạo ra. Metadata annotation có thể nằm trên implementation class, trong khi runtime object được export là proxy.

Các rủi ro:

- Annotation source không tìm đúng metadata do proxy type khác target class.
- Method được expose không hiện trên proxy interface.
- Naming strategy nhìn type khác kỳ vọng.
- Attribute hoặc operation bị thiếu hoặc không gọi được.

Spring JMX có hỗ trợ xử lý những tình huống proxy trong nhiều cấu hình, nhưng không nên coi mọi loại proxy và mọi annotation layout hoạt động giống nhau.

Cách xử lý:
1. Xác minh bean runtime type và target class.
2. Đặt annotation ở vị trí phù hợp với cơ chế introspection của ứng dụng.
3. Kiểm tra \`MBeanInfo\` sau khi export.
4. Thử \`getAttribute()\` hoặc \`invoke()\` trên MBean thực tế.
5. Nếu phức tạp, tạo bean facade/monitor riêng cho JMX để hợp đồng quản trị ổn định hơn.

## 13. Cách kiểm chứng metadata trên MBeanServer

Để biết management interface thực sự được công bố, hãy dùng \`MBeanServer\`.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s, read=%s, write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s, description=%s%n",
        operation.getName(),
        operation.getDescription()
    );
}
\`\`\`

Đoạn trên giả định sử dụng đúng platform MBeanServer trong cùng JVM. Nếu exporter được gắn một \`MBeanServer\` khác hoặc client ở JVM khác, phải truy cập đúng server qua API/connection thích hợp.

### Kiểm chứng notification metadata

\`\`\`java
for (var notification : info.getNotifications()) {
    System.out.println(notification.getName());
    System.out.println(
        java.util.Arrays.toString(notification.getNotifTypes())
    );
}
\`\`\`

Metadata notification xuất hiện không chứng minh MBean đã thực sự phát notification. Code phát phải được cấu hình qua \`NotificationPublisher\` hoặc \`NotificationBroadcaster\` tương ứng.

### Kiểm chứng theo loại rủi ro

| Biểu hiện | Điểm kiểm tra |
|---|---|
| Không thấy MBean | Exporter, autodetect, ObjectName, target MBeanServer |
| MBean có nhưng description sai | \`AnnotationJmxAttributeSource\` và assembler |
| Thiếu attribute | Getter/setter conventions, annotation, assembler |
| Thiếu operation | \`@ManagedOperation\`, method visibility, proxy, assembler |
| Tên MBean sai | Naming strategy và \`@ManagedResource.objectName\` |
| Thông báo có metadata nhưng không phát | Publisher/broadcaster và logic gửi |
| Xuất trùng | Nhiều exporter hoặc ObjectName trùng |
| Client remote không gọi được | Connection, security, type/serialization |

## 14. Assembler không thay thế bảo mật hoặc runtime behavior

Một giới hạn quan trọng của metadata-based exposure là việc một method xuất hiện trong \`MBeanInfo\` không có nghĩa nó **an toàn để cho mọi caller gọi**.

Ví dụ:

\`\`\`java
@ManagedOperation(description = "Restart worker")
public void restartWorker() {
    workerService.restart();
}
\`\`\`

Operation này có tác động thực tế. Cần:
- Đảm bảo chỉ caller được cấp quyền mới gọi được.
- Xác định behavior khi nhiều caller gọi đồng thời.
- Có validation và logging/audit phù hợp.
- Tránh expose bí mật trong params, return values và exceptions.
- Giới hạn kết nối JMX remote, không mở công khai nếu chưa bảo vệ.

\`@ManagedOperation(description="Admin only")\` không thực thi phân quyền. Assembler chỉ cung cấp metadata cho giao diện quản trị.

## 15. Thiết kế management interface ổn định

Khi sử dụng \`MetadataMBeanInfoAssembler\`, nên xem annotations là một hợp đồng API quản trị:

- Đặt tên ObjectName nhất quán theo domain/type/name.
- Chọn attributes có giá trị chẩn đoán, đọc nhanh và ít side effects.
- Ưu tiên kiểu dữ liệu dễ tiêu thụ bởi JMX clients.
- Mô tả rõ đơn vị đo và semantics của mỗi attribute.
- Tránh expose method nội bộ chỉ vì method có thể truy cập \`public\`.
- Dùng operation cho tác vụ quản trị có hành vi rõ ràng.
- Định nghĩa type và description của notification, nhưng xây dựng cơ chế gửi riêng.
- Kiểm chứng metadata thật khi nâng cấp Spring hoặc thay đổi proxy/AOP.
- Khi đổi interface quản trị, xem xét ảnh hưởng đến monitoring tools và JMX clients đang dùng.

Một contract JMX tốt có tên và loại dữ liệu có ý nghĩa, ít thay đổi tùy tiện, và không làm lộ đối tượng nghiệp vụ không cần thiết.

## 16. Bài tập thực hành

### Bài tập A: Cấu hình annotation source

1. Tạo \`CacheMonitor\` với \`@ManagedResource\`.
2. Gắn \`@ManagedAttribute\` lên getter \`getEntryCount()\`.
3. Gắn \`@ManagedOperation\` lên \`resetStats()\`.
4. Bật Spring JMX export bằng \`@EnableMBeanExport\` hoặc cấu hình exporter thủ công.
5. Lấy \`MBeanInfo\` và xác minh tên, description, attribute, operation.

### Bài tập B: Thay đổi metadata

1. Đổi \`@ManagedResource.description\` và \`@ManagedAttribute.description\`.
2. Khởi động lại context.
3. So sánh \`MBeanInfo\` trước/sau.
4. Giải thích vì sao description thay đổi metadata nhưng không thay đổi hành vi getter.

### Bài tập C: Thử thiếu annotation

1. Gỡ \`@ManagedOperation\` khỏi một method.
2. Khởi động lại context với annotation assembler.
3. Kiểm tra operation có còn trong \`MBeanInfo\` hay không.
4. Khôi phục annotation và xác nhận lại.

### Bài tập D: Proxy

1. Tạo một Spring bean có AOP proxy.
2. Đặt metadata JMX trên implementation.
3. Export bean và kiểm tra \`MBeanInfo\`.
4. Nếu annotation không được nhận hoặc method không gọi được, điều chỉnh proxy/interface hoặc dùng facade dành riêng cho JMX.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** \`MetadataMBeanInfoAssembler\` tạo \`ObjectName\` cho MBean phải không?  
**Trả lời:** Không trực tiếp. Assembler xây dựng metadata/giao diện quản trị; naming strategy xác định ObjectName.

**Câu 2.** Vai trò của \`AnnotationJmxAttributeSource\` là gì?  
**Trả lời:** Đọc Spring JMX annotations và cung cấp metadata theo hợp đồng \`JmxAttributeSource\` cho assembler/naming strategy.

**Câu 3.** Chỉ gắn \`@ManagedAttribute\` lên getter là đủ để JConsole nhìn thấy attribute chưa?  
**Trả lời:** Chưa. Bean phải được export qua JMX với assembler/source phù hợp và đăng ký trên MBeanServer.

**Câu 4.** \`@ManagedNotification\` có tự gửi event?  
**Trả lời:** Không. Nó khai báo notification metadata; logic publisher/broadcaster mới gửi sự kiện.

**Câu 5.** Standard MBean có bắt buộc dùng MetadataMBeanInfoAssembler không?  
**Trả lời:** Không. Standard MBean có management interface riêng theo quy ước JMX.

**Câu 6.** Làm thế nào biết method \`resetStats()\` được expose thực sự?  
**Trả lời:** Đọc \`MBeanInfo.getOperations()\` từ đúng MBeanServer/ObjectName và khi cần thử invoke trong môi trường kiểm soát.

**Câu 7.** \`description\` có phải quy tắc authorization không?  
**Trả lời:** Không. Đó là metadata mô tả, không thực thi quyền.

## 18. Ghi nhớ

- \`MetadataMBeanInfoAssembler\` biến metadata của bean thành \`ModelMBeanInfo\` và management interface được JMX trình bày.
- \`AnnotationJmxAttributeSource\` là nguồn metadata phổ biến khi dùng Spring JMX annotations.
- \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, \`@ManagedOperationParameter\` và \`@ManagedNotification\` mô tả những cấp khác nhau của management API.
- \`MBeanExporter\` thực hiện xuất/đăng ký; \`MetadataNamingStrategy\` quyết định ObjectName; assembler quyết định giao diện.
- Autodetect có thể dựa vào assembler để chọn những bean có metadata.
- Standard MBean/MXBean có hợp đồng management interface riêng, không đồng nghĩa với annotation-based Model MBean.
- Hãy kiểm tra \`MBeanInfo\` thật và đường gọi JMX thay vì chỉ dựa vào annotation trên class.
- Metadata giúp quản lý hợp đồng, nhưng không thay thế validation, security, persistence hoặc cơ chế gửi notification.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Javadoc — \`JmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/metadata/JmxAttributeSource.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 API — \`ModelMBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/modelmbean/ModelMBeanInfo.html
