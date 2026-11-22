# Migration từ interface MBean sang annotation metadata trong Spring Framework JMX

## Mục tiêu học tập

Bài học thuộc nhóm **Tiến hóa và tương thích** của Spring Framework JMX. Trong hệ thống Java đã vận hành lâu năm, nhiều MBean được viết theo quy ước Standard MBean: class \`CacheManager\` implement \`CacheManagerMBean\`. Khi dự án chuyển sang Spring annotation-based JMX, có thể muốn dùng \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` và \`@ManagedOperationParameter\` để mô tả API quản trị ngay trên Java bean.

Sau khi hoàn thành bài này, bạn có thể:

- Phân biệt Standard MBean interface, Spring annotation metadata và ModelMBean được dựng bởi Spring.
- Lập bản đồ migration giữa getter/setter/operation trên interface với các annotation quản trị.
- Cấu hình \`MBeanExporter\`, \`MetadataMBeanInfoAssembler\`, \`AnnotationJmxAttributeSource\` hoặc \`@EnableMBeanExport\`.
- Giữ nguyên \`ObjectName\`, attribute names, operation signatures và các hành vi client phụ thuộc.
- Hiểu tương thích của JConsole, JMX remote clients, local MBean proxies và external automation.
- Thiết kế migration từng bước, tránh đăng ký hai MBean trùng \`ObjectName\`.
- Kiểm thử compatibility qua \`MBeanInfo\`, trạng thái runtime, lời gọi thực tế và lifecycle.

## 1. Hai cơ chế công bố MBean khác nhau

### 1.1. Standard MBean interface

JMX chuẩn quy định một class như \`CacheManager\` có thể cung cấp management interface \`CacheManagerMBean\`. Ví dụ:

\`\`\`java
package com.example.cache;

public interface CacheManagerMBean {
    int getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clearStatistics();
}
\`\`\`

Implementation:

\`\`\`java
package com.example.cache;

public class CacheManager implements CacheManagerMBean {

    private volatile boolean enabled = true;

    @Override
    public int getEntryCount() {
        return 42;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void clearStatistics() {
        // Xóa số liệu thống kê nội bộ.
    }
}
\`\`\`

JMX nhận biết Standard MBean interface theo convention, dựng metadata từ method signatures và công bố:

- Attribute \`EntryCount\`, kiểu \`int\`, đọc được.
- Attribute \`Enabled\`, kiểu \`boolean\`, đọc và ghi được.
- Operation \`clearStatistics()\`.

Trong cách này, **interface là hợp đồng quản trị tường minh**. Thay đổi interface làm thay đổi phần bề mặt JMX được công bố.

### 1.2. Annotation metadata của Spring

Spring Framework JMX cung cấp các annotation để mô tả managed resource và những method cần được công bố:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
\`\`\`

Một class có thể không implement \`*MBean\`, nhưng vẫn được Spring adapt và export thông qua ModelMBean dựa trên metadata. Các annotation không phải là quy tắc JMX Standard MBean của JDK; chúng được Spring JMX infrastructure đọc khi tạo management metadata.

Ví dụ chuyển sang annotation:

\`\`\`java
package com.example.cache;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary",
    description = "Cache management")
public class CacheManager {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Number of cached entries")
    public int getEntryCount() {
        return 42;
    }

    @ManagedAttribute(description = "Whether caching is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Enable or disable cache")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Clear cache statistics")
    public void clearStatistics() {
        // ...
    }
}
\`\`\`

Cú pháp khác nhau nhưng mục tiêu migration là giữ lại **management contract** mà client đã sử dụng. Không chỉ nhìn tên Java method; cần xác minh metadata JMX cuối cùng, cách Spring phân loại getters/setters, invocation behavior và những phần tử không mong muốn có bị lộ ra không.

## 2. Điều gì thay đổi khi bỏ interface *MBean?

| Khía cạnh | Standard MBean interface | Spring annotation metadata |
| --- | --- | --- |
| Nguồn định nghĩa contract | Interface \`ClassNameMBean\` | \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` |
| Cách xác định management methods | Method khai báo trên interface | Method được annotation/assembler chọn |
| Ai dựng metadata | JMX introspection của server | Spring metadata assembler và ModelMBean adapter |
| Phụ thuộc Spring JMX annotation | Không cần | Có |
| MBean class/metadata mô tả | Standard MBean | Thường là ModelMBean hoặc adapter do Spring tạo |
| Có thể bổ sung descriptions | Hạn chế theo metadata mặc định | Có metadata annotation chi tiết |
| Management interface Java ở client | Có thể dùng cùng \`*MBean\` interface | Có thể cần giữ interface client hoặc dùng \`MBeanServerConnection\` |
| Khả năng giữ contract tương đương | Có, nếu không thay đổi | Có, nhưng phải kiểm chứng metadata và behavior |
| Rủi ro mở rộng API vô ý | Thêm method vào interface | Annotation/assembler/autodetection không đúng |
| Rủi ro thay đổi naming | Tên do exporter/server cung cấp | \`@ManagedResource.objectName\` và naming strategy phải đồng bộ |

Không có quy tắc “annotation mode luôn tương thích 100%” chỉ vì Java methods có cùng tên. Metadata của ModelMBean và Standard MBean có thể khác ở class name, descriptors hoặc representation của operation/getter. Một JMX client chỉ phụ thuộc attribute và operation phổ biến thường có thể hoạt động nếu contract được giữ đúng; client kiểm tra sâu metadata có thể cần điều chỉnh.

## 3. Kiểm kê hợp đồng JMX trước khi migration

Trước khi sửa code, lập danh sách những thông tin client thực sự sử dụng.

Ví dụ:

\`\`\`text
ObjectName:
  com.example.cache:type=CacheManager,name=primary

Attributes:
  EntryCount  int      readable=true,  writable=false
  Enabled     boolean  readable=true,  writable=true

Operations:
  clearStatistics() -> void

Notifications:
  none

Clients:
  JConsole
  custom JMX tooling
  monitoring jobs
\`\`\`

Cần phân biệt các nhóm compatibility:

1. **Tên registration:** domain và key properties của \`ObjectName\`.
2. **Tên attributes:** chữ hoa/chữ thường, JavaBean getter mapping.
3. **Kiểu dữ liệu:** primitive/wrapper, Open Types nếu dùng MXBean.
4. **Phương thức:** operation name, parameter count/types, return type và behavior.
5. **Quyền đọc/ghi:** \`isReadable\`, \`isWritable\`.
6. **Metadata ngoài hợp đồng chính:** description, descriptor fields và class name nếu client dùng.
7. **Notification:** types, sequence, source, userData nếu có.
8. **Lifecycle:** registration/unregistration trong \`ApplicationContext\`.
9. **Security:** quyền thao tác và bề mặt operations có side effect.
10. **Client assumptions:** tool có phụ thuộc Java interface cụ thể hay chỉ dùng standard JMX APIs?

Mục tiêu là **so sánh trước/sau**, không đổi interface rồi hy vọng dashboard không bị ảnh hưởng.

## 4. Đọc MBeanInfo trước khi chuyển

\`MBeanInfo\` là dữ liệu nền tảng để xác nhận management contract đang công bố trong JMX registry.

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxContractInspector {

    public static void inspect(
            MBeanServer server,
            ObjectName name) throws Exception {

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                    "MBean not registered: " + name);
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean class: " + info.getClassName());

        for (var attribute : info.getAttributes()) {
            System.out.printf(
                    "ATTR %s type=%s read=%s write=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (var operation : info.getOperations()) {
            System.out.printf(
                    "OP %s returnType=%s%n",
                    operation.getName(),
                    operation.getReturnType());

            for (var parameter : operation.getSignature()) {
                System.out.printf(
                        "  PARAM %s type=%s%n",
                        parameter.getName(),
                        parameter.getType());
            }
        }
    }
}
\`\`\`

Lời gọi:

\`\`\`java
JmxContractInspector.inspect(
        server,
        new ObjectName(
                "com.example.cache:type=CacheManager,name=primary"));
\`\`\`

Chạy inspector với phiên bản cũ và lưu một snapshot có kiểm soát. Sau migration, chạy lại trên server cùng ý nghĩa và so sánh. Trong CI, có thể chuẩn hóa danh sách attributes/operations thay vì so sánh toàn bộ \`toString()\` của descriptors vì một số metadata ngoài hợp đồng có thể khác do chuyển từ Standard MBean sang ModelMBean.

**Không đọc MBeanInfo từ platform server nếu exporter thực tế dùng custom server.** Cần lấy đúng \`MBeanServer\` mà exporter hoặc connector liên kết.

## 5. Migration bước 1 — Giữ nguyên class behavior

Trước khi thay đường export, tránh đồng thời sửa business behavior, tên method và dữ liệu quản trị. Ví dụ:

\`\`\`java
public int getEntryCount() { ... }

public boolean isEnabled() { ... }

public void setEnabled(boolean enabled) { ... }

public void clearStatistics() { ... }
\`\`\`

Nếu cần giữ client tương thích, những method này nên giữ chữ ký và ý nghĩa ban đầu. Việc thay \`clearStatistics()\` thành \`resetMetrics()\` có thể làm các JMX automation gọi \`clearStatistics\` thất bại.

Một cách migration từng bước là **giữ interface \`CacheManagerMBean\` trong code dù Spring annotation đã được thêm**. Điều này cho phép các Java clients cũ còn compile, nhưng cần kiểm soát export path: nếu implementation vẫn là Standard MBean, \`MBeanExporter\` có thể nhận diện và export theo interface chuẩn thay vì sử dụng annotation metadata theo cách bạn mong muốn. Muốn thực sự kiểm nghiệm annotation-based ModelMBean, cần xác nhận cách exporter lựa chọn registration path trong version Spring đang dùng.

Không buộc xóa interface ngay trong đợt đầu. Trước tiên thiết lập compatibility tests, sau đó mới cân nhắc thay đổi Java API.

## 6. Migration bước 2 — Gắn @ManagedResource và method metadata

Ví dụ đối tượng mới không còn implement interface MBean:

\`\`\`java
package com.example.cache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary",
    description = "Primary cache manager")
public class CacheManager {

    private final AtomicInteger entryCount = new AtomicInteger();
    private volatile boolean enabled = true;

    public void addEntry() {
        entryCount.incrementAndGet();
    }

    @ManagedAttribute(
        description = "Current number of cached entries")
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedAttribute(
        description = "Whether cache use is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(
        description = "Enable or disable caching")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(
        description = "Reset cache statistics")
    public void clearStatistics() {
        entryCount.set(0);
    }
}
\`\`\`

Ở đây \`addEntry()\` là method nghiệp vụ không được annotation để export. Nếu sử dụng metadata assembler theo annotation, chỉ những methods được cấu hình hợp lệ mới được công bố theo cơ chế đó.

**Điểm cần chú ý:** một getter/setter có thể được biểu diễn bằng attribute, và ModelMBean metadata có thể chứa operations hỗ trợ accessor. Khi so sánh, hãy phân biệt “operation nghiệp vụ được phép gọi” với metadata getter/setter được assembler dùng để hỗ trợ attributes.

Nếu dự án có những methods tên gần giống hoặc overload, không suy luận khả năng tương thích chỉ từ tên. Phải kiểm tra signature JMX sau khi export.

## 7. Migration bước 3 — Cấu hình @EnableMBeanExport

Với Spring Java Config:

\`\`\`java
package com.example.cache;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class CacheJmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheManager cacheManager() {
        return new CacheManager();
    }
}
\`\`\`

\`@EnableMBeanExport\` kích hoạt annotation-based JMX exporting. Nó phối hợp các cơ chế metadata và naming cần thiết để những Spring beans được đánh dấu \`@ManagedResource\` có thể được xuất.

Điểm quan trọng:

- \`@ManagedResource\` **không tự tạo Spring bean**. Class cần được đưa vào \`ApplicationContext\` qua \`@Bean\`, \`@Component\` hoặc component scanning.
- \`@EnableMBeanExport(server="platformMBeanServer")\` chọn một \`MBeanServer\` bean theo tên; đảm bảo tên đó thực sự tồn tại trong context.
- \`@ManagedResource.objectName\` có thể tham gia naming strategy dựa trên annotation.
- Không bật thêm một \`MBeanExporter\` khác cùng đăng ký chính \`ObjectName\` đã xuất.

Trong Spring Boot, JMX auto-configuration có thể đã tạo exporter tùy version/profile. Khi migration, cần xác định chính xác infrastructure đang hoạt động để tránh đăng ký đôi.

## 8. Migration bước 4 — Cấu hình assembler tường minh khi cần

Một số ứng dụng không dùng \`@EnableMBeanExport\` mà khai báo exporter, assembler và naming strategy riêng. Trong trường hợp này, annotation metadata cần được kết nối đúng các thành phần:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Bean
public AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
public MetadataMBeanInfoAssembler metadataAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
public MetadataNamingStrategy metadataNamingStrategy(
        AnnotationJmxAttributeSource source) {
    MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
    naming.setAttributeSource(source);
    return naming;
}
\`\`\`

Exporter:

\`\`\`java
@Bean
public MBeanExporter cacheExporter(
        CacheManager cacheManager,
        MBeanServer server,
        MetadataMBeanInfoAssembler assembler,
        MetadataNamingStrategy naming) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setAssembler(assembler);
    exporter.setNamingStrategy(naming);
    exporter.setBeans(java.util.Map.of(
            "cacheManager", cacheManager));
    return exporter;
}
\`\`\`

Trong ví dụ này, exporter nhận key \`cacheManager\`, còn naming strategy đọc metadata của \`@ManagedResource\` để tạo \`ObjectName\`. Nếu muốn giữ tên một cách tường minh, bạn cũng có thể truyền full name trong mapping, nhưng cần kiểm tra naming strategy thực sự xử lý key đó như thế nào.

Đây là một cấu hình **thay thế** cho \`@EnableMBeanExport\` trong ví dụ trước, không phải cấu hình nên bật đồng thời cho cùng managed object.

## 9. Mapping getter/setter sang @ManagedAttribute

Một Standard MBean dùng JavaBean conventions:

\`\`\`java
int getEntryCount();
boolean isEnabled();
void setEnabled(boolean value);
\`\`\`

Spring annotation-based JMX có thể dùng:

\`\`\`java
@ManagedAttribute
public int getEntryCount() { ... }

@ManagedAttribute
public boolean isEnabled() { ... }

@ManagedAttribute
public void setEnabled(boolean enabled) { ... }
\`\`\`

Cần kiểm tra sau migration:

| Phần tử | Trước | Sau mong muốn |
| --- | --- | --- |
| \`EntryCount\` | \`int\`, readable | \`int\`, readable |
| \`Enabled\` | \`boolean\`, readable/writable | \`boolean\`, readable/writable |
| Getter name | \`getEntryCount\` | Không thay đổi |
| Boolean accessor | \`isEnabled\` | Không thay đổi |
| Setter parameter | \`boolean\` | Không thay đổi |

Nếu chỉ annotation getter mà bỏ annotation setter, attribute có thể trở thành read-only theo metadata assembler. Nếu client cũ dùng \`setAttribute(...)\`, đó là breaking change.

Một getter có thể trả về primitive hoặc kiểu object; với remote client, phải bảo đảm kiểu dữ liệu được hỗ trợ bởi JMX/transport. Tùy cách export Standard MBean hay ModelMBean, những thông tin mô tả type có thể khác; test thực tế là cơ sở.

## 10. Mapping operations sang @ManagedOperation

Standard MBean:

\`\`\`java
public interface CacheManagerMBean {
    void clearStatistics();
    String reloadRules(String profile);
}
\`\`\`

Annotation metadata:

\`\`\`java
@ManagedOperation(description = "Clear cache counters")
public void clearStatistics() {
    // ...
}

@ManagedOperation(description = "Reload rules from a profile")
@ManagedOperationParameter(
    name = "profile",
    description = "Configuration profile to load")
public String reloadRules(String profile) {
    return "RELOADED:" + profile;
}
\`\`\`

\`@ManagedOperationParameter\` hoặc \`@ManagedOperationParameters\` giúp mô tả tham số, nhưng **không đổi kiểu/chữ ký Java** của operation. Để giữ tương thích với client cũ, method name, số tham số, thứ tự tham số, kiểu và ý nghĩa phải nhất quán.

Ví dụ client cũ:

\`\`\`java
Object result = server.invoke(
        name,
        "reloadRules",
        new Object[]{"blue"},
        new String[]{"java.lang.String"});
\`\`\`

Nếu sau migration method \`reloadRules\` chỉ nhận \`int\` hoặc được đổi thành \`reloadConfiguration\`, lời gọi trên sẽ thất bại dù MBean vẫn đăng ký thành công.

Các parameter descriptions không phải cơ chế validation. Với input không hợp lệ, method cần tự kiểm tra và trả lỗi/trạng thái có ý nghĩa.

## 11. ObjectName phải giữ ổn định

Ví dụ contract cũ:

\`\`\`text
com.example.cache:type=CacheManager,name=primary
\`\`\`

Cấu hình mới cần giữ cùng tên nếu client phụ thuộc vào nó:

\`\`\`java
@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary")
\`\`\`

Các lỗi thường gặp khi migration:

- Đổi domain từ \`com.example.cache\` thành \`com.example\`.
- Bỏ key \`name=primary\`.
- Dùng class name khác làm \`type\` mà không có kế hoạch cập nhật client.
- Có hai instances nhưng cả hai annotation cùng một full \`ObjectName\`.
- Chuyển \`KeyNamingStrategy\` sang \`MetadataNamingStrategy\` mà không kiểm tra tên cuối.
- Có hai exporters cùng quản lý tên cũ.

Một \`ObjectName\` là định danh MBean **trong một \`MBeanServer\`**. Hai JVM khác nhau có thể cùng dùng tên mà không xung đột; client còn phải kết nối tới đúng JVM/server endpoint.

Khi cần đổi tên, có thể thực hiện migration versioned: tạo tên mới dưới domain khác, thông báo tới clients và duy trì compatibility window có kiểm soát. Tuy nhiên không đăng ký hai tên cho cùng object nếu điều đó dẫn tới operation có side effect được gọi lặp hoặc ownership khó kiểm soát mà chưa đánh giá tác động.

## 12. Tránh đăng ký hai MBean cùng tên trong giai đoạn chuyển

Một hệ thống có thể vô tình dùng song song:

\`\`\`text
Legacy MBeanExporter -> Standard MBean -> ObjectName X
AnnotationMBeanExporter -> Annotated bean -> ObjectName X
\`\`\`

Kết quả thường là xung đột registration:

\`\`\`text
InstanceAlreadyExistsException: X
\`\`\`

Các policy của Spring như \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, \`REPLACE_EXISTING\` thay đổi cách xử lý nhưng **không tự chứng minh migration đúng**.

- \`FAIL_ON_EXISTING\`: giúp phát hiện cấu hình chồng chéo.
- \`IGNORE_EXISTING\`: có thể giữ MBean cũ, khiến annotation export mới bị bỏ qua.
- \`REPLACE_EXISTING\`: có thể thay target dưới cùng tên và tạo vấn đề lifecycle ownership.

Quy trình an toàn thường là test hai cấu hình trong **hai môi trường/server cô lập**, sau đó triển khai một cơ chế export chủ động duy nhất trong runtime production.

Nếu cần chạy hai phiên bản song song để so sánh, sử dụng server riêng hoặc tên versioned rõ ràng, không lạm dụng replace policy để chồng lên tên hiện hữu.

## 13. Gắn với Spring AOP proxy

Trong Spring application, managed bean có thể là Spring AOP proxy do \`@Transactional\`, security hoặc aspect khác. JDK dynamic proxy expose interfaces, có thể che implementation class trong quá trình introspection.

Khi migration từ Standard MBean interface sang annotation trên implementation:

1. Annotation có thể nằm trên target class, không nằm trên runtime JDK proxy class.
2. Management methods có thể không được expose qua business interfaces mà proxy implement.
3. Một annotation-aware assembler có thể có hỗ trợ truy cập target metadata, nhưng invocation path vẫn cần phù hợp.
4. Class-based proxy có những đặc điểm khác, nhưng không tự đảm bảo mọi method đều an toàn để export.

Không kết luận tuyệt đối rằng annotation mode “luôn hỏng với JDK proxy” hoặc “luôn xử lý được mọi proxy”. Phải kiểm tra runtime bean type, metadata cuối và lời gọi thực tế qua JMX.

Khi business service phức tạp, tạo **management facade riêng** là một lựa chọn vững chắc:

\`\`\`java
@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary")
public class CacheManagementFacade {

    private final CacheService cacheService;

    public CacheManagementFacade(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @ManagedAttribute
    public int getEntryCount() {
        return cacheService.getEntryCount();
    }

    @ManagedOperation
    public void clearStatistics() {
        cacheService.clearStatistics();
    }
}
\`\`\`

Facade hạn chế bề mặt JMX, giữ service nghiệp vụ không phụ thuộc annotation và có thể xử lý AOP/transaction boundary rõ hơn.

## 14. Vấn đề client dùng Java interface cũ

Một số client remote chỉ làm việc với standard JMX APIs:

\`\`\`java
connection.getAttribute(objectName, "EntryCount");
connection.invoke(
        objectName, "clearStatistics",
        new Object[0], new String[0]);
\`\`\`

Những client đó phụ thuộc vào \`ObjectName\`, attributes và operations. Nếu metadata sau migration giữ contract tương đương, khả năng tương thích thường tốt.

Một số Java clients có thể dùng dynamic proxy kiểu:

\`\`\`java
CacheManagerMBean proxy = JMX.newMBeanProxy(
        connection,
        objectName,
        CacheManagerMBean.class);
\`\`\`

Khi server chuyển sang ModelMBean do Spring xây dựng, client proxy vẫn có thể gọi các method tương ứng nếu hợp đồng JMX match và cơ chế proxy phù hợp. Tuy nhiên, client có thể phụ thuộc vào metadata cụ thể, Standard MBean conventions hoặc interface type; vì vậy phải kiểm tra compatibility trên client thực tế.

**Không vội xóa file \`CacheManagerMBean.java\` khỏi artifact/client library** nếu external tools vẫn compile dựa vào interface. Có thể ngừng dùng interface trên server implementation nhưng giữ interface như client API với versioning/deprecation rõ ràng.

## 15. Metadata MBeanInfo có thể khác dù API tương thích

Sau migration, metadata có thể thay đổi:

- \`getClassName()\` của \`MBeanInfo\` có thể phản ánh một adapter/ModelMBean khác.
- Descriptions có thể được thêm từ annotation.
- Descriptors và impact flags có thể khác.
- Getter/setter có thể xuất hiện trong metadata theo cách khác.
- Constructor/notification metadata có thể khác.

Nếu một monitoring client chỉ đọc \`EntryCount\`, những khác biệt này có thể không ảnh hưởng. Nếu client có logic “chỉ chấp nhận className X” hoặc dựa vào exact operation list, migration có thể gây breaking change.

Một compatibility test tốt có hai tầng:

1. **Contract assertions:** \`ObjectName\`, attribute names/types/access và các operation signatures/return types mong đợi.
2. **Behavior assertions:** đọc trạng thái, ghi attribute, gọi operation và quan sát đúng side effect.

Khi so sánh toàn bộ metadata, hãy xác định những khác biệt được chấp nhận có chủ đích thay vì yêu cầu byte-for-byte equality giữa hai loại MBean khác nhau.

## 16. Test tích hợp cho cấu hình annotation mới

Ví dụ JUnit Jupiter:

\`\`\`java
package com.example.cache;

import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class CacheJmxMigrationTest {

    @Test
    void annotatedMBeanKeepsManagementContract() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.cache:type=CacheManager,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(Arrays.stream(info.getAttributes())
                .anyMatch(a -> "EntryCount".equals(a.getName())
                    && "int".equals(a.getType())
                    && a.isReadable()));

            assertTrue(Arrays.stream(info.getAttributes())
                .anyMatch(a -> "Enabled".equals(a.getName())
                    && a.isReadable()
                    && a.isWritable()));

            assertTrue(Arrays.stream(info.getOperations())
                .anyMatch(o -> "clearStatistics".equals(o.getName())));

            CacheManager manager = context.getBean(CacheManager.class);
            manager.addEntry();

            assertEquals(
                1, server.getAttribute(name, "EntryCount"));

            server.setAttribute(
                name,
                new javax.management.Attribute("Enabled", false));

            assertFalse(manager.isEnabled());

            server.invoke(
                name,
                "clearStatistics",
                new Object[0],
                new String[0]);

            assertEquals(
                0, server.getAttribute(name, "EntryCount"));
        }
    }
}
\`\`\`

Test này kiểm tra registration, metadata, attribute read/write và operation invocation. Nó là ví dụ cho cấu hình annotation đã định nghĩa ở trên, không thay thế bước so sánh với cấu hình cũ nếu mục tiêu là chứng minh tương đương trước/sau migration.

Trong test suite chạy song song, platform \`MBeanServer\` và \`ObjectName\` cố định có thể xung đột. Nên dùng server test riêng hoặc tên domain/instance riêng trong fixture.

## 17. So sánh contract cũ/mới bằng một snapshot có cấu trúc

Thay vì lưu output console dễ đổi thứ tự, có thể chuẩn hóa metadata thành cấu trúc:

\`\`\`text
ObjectName = com.example.cache:type=CacheManager,name=primary

ATTR:
  Enabled|boolean|R|W
  EntryCount|int|R|-

OP:
  clearStatistics|void|()
\`\`\`

Trong Java, lấy \`MBeanAttributeInfo[]\` và \`MBeanOperationInfo[]\` từ \`MBeanInfo\`, map thành records, sort theo name/signature. Với operations có overload, chỉ tên không đủ; cần so sánh đầy đủ signature.

Khi migration sang annotation metadata, việc \`ModelMBeanInfo\` có thể biểu diễn accessor dưới dạng operation metadata cần được xem xét: nếu old Standard MBean không có những entries đó, so sánh exact operation set sẽ khác. Có thể áp dụng một compatibility policy chỉ yêu cầu các business operations quan trọng và xác nhận không xuất thêm operation nhạy cảm.

Đối với một hệ thống đã có client phụ thuộc metadata đầy đủ, không được lược bỏ khác biệt này một cách tùy ý; snapshot test phải phản ánh hợp đồng thực sự mà client sử dụng.

## 18. Lưu ý với MXBean và Open Types

Không phải mọi interface tên \`*MBean\` đều giống MXBean. MXBean có cơ chế mapping Java types sang Open Types, phù hợp remote management clients với các kiểu dữ liệu được chuẩn hóa.

Nếu hệ thống cũ dùng MXBean thay vì Standard MBean, migration sang Spring annotation ModelMBean không mặc nhiên bảo toàn quy tắc mapping đó.

Ví dụ MXBean:

\`\`\`java
public interface CacheMetricsMXBean {
    Map<String, Integer> getCountsByRegion();
}
\`\`\`

Client có thể nhận dữ liệu dạng Open Types. Nếu chuyển implementation sang annotation metadata trên POJO nhưng vẫn trả một kiểu không phù hợp remote serialization, client có thể bị ảnh hưởng.

Vì vậy, với MXBean cần:

1. Kiểm kê return/parameter types và dạng Open Data thực tế.
2. Kiểm tra \`MBeanInfo\` và \`OpenMBeanInfo\` nếu có.
3. Dùng remote JMX connector trong compatibility test.
4. Cân nhắc giữ MXBean contract nếu mục tiêu chỉ là làm mới cách cấu hình Spring.

Không nên chuyển MXBean sang annotation-based ModelMBean chỉ để “thống nhất style” nếu remote data compatibility có rủi ro cao.

## 19. Notification và listener compatibility

Nếu Standard MBean cũ có \`NotificationBroadcaster\`, client có thể đã đăng ký \`NotificationListener\`. Chuyển sang Spring annotation metadata không tự đảm bảo notifications cũ vẫn được phát với cùng type, source, sequence và \`userData\`.

Cần xác định:

- Class hoặc component nào phát notification?
- \`MBeanNotificationInfo\` có công bố types cũ không?
- Client dùng \`addNotificationListener\` trên cùng \`ObjectName\`?
- Listener có bị mất đăng ký khi chuyển exporter?
- Event name, payload và thời điểm có đổi không?

Spring có \`NotificationPublisher\`, \`NotificationPublisherAware\` và metadata thông báo khi sử dụng Spring JMX integration phù hợp. Nếu migration có notifications, cần chuyển riêng phần phát sự kiện và kiểm thử remote/local callback, không chỉ kiểm tra attributes.

Khi thay registration dưới cùng \`ObjectName\`, listener đã đăng ký với MBean cũ có thể không tự theo sang registration mới như mong đợi. Thiết kế rollout để client có thể reconnect/re-subscribe.

## 20. Các lỗi migration thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Context khởi tạo nhưng JConsole không thấy MBean | Annotation exporter chưa bật hoặc bean không trong context | Kiểm tra \`@EnableMBeanExport\`, \`@Bean\`, đúng server |
| \`InstanceAlreadyExistsException\` | Exporter Standard MBean cũ và annotation exporter mới chạy cùng tên | Chỉ một registration owner hoặc tách test servers |
| \`AttributeNotFoundException\` | Quên annotation getter/setter hoặc đổi tên attribute | So sánh \`MBeanInfo\` trước/sau |
| Setter không hoạt động | \`Enabled\` chuyển thành read-only | Annotation setter và test \`setAttribute\` |
| \`ReflectionException\` khi invoke | Method name/signature không khớp | So sánh \`MBeanOperationInfo\` |
| \`NotCompliantMBeanException\` | Exporter chọn không đúng MBean path/type | Kiểm tra Standard MBean vs ModelMBean, assembler |
| Metadata khác kỳ vọng | Spring ModelMBean có descriptors/class name khác | Phân loại breaking vs acceptable differences |
| Java client không compile | Interface \`*MBean\` bị xóa khỏi library | Giữ client API hoặc version migration |
| Remote client không đọc kiểu dữ liệu | Thay đổi MXBean/Open Types hoặc serialization | Test connector remote với real data |
| Operation có side effect thay đổi | Implementation được sửa trong lúc migration | Tách business change khỏi migration |
| Notification không tới | Listener mất khi registration thay hoặc broadcaster khác | Kiểm tra notification contract, re-subscription |
| Spring AOP proxy che method/annotation | JDK proxy chỉ expose interfaces | Facade hoặc export strategy phù hợp |

## 21. Checklist migration có kiểm soát

**Trước migration:**

- Liệt kê exporter và \`ObjectName\` hiện có.
- Xác định các client và use cases.
- Snapshot \`MBeanInfo\`, bao gồm attribute access và operation signatures.
- Xác định Standard MBean, MXBean hay ModelMBean cũ.
- Ghi lại registration policy, server/connector và lifecycle.
- Có integration test cho read/write/invoke/notifications quan trọng.
- Kiểm tra proxy/AOP và nhiều contexts nếu có.

**Trong migration:**

- Thêm annotation metadata với cùng method signatures.
- Cấu hình Spring JMX assembler và naming strategy đúng.
- Không kích hoạt hai exporters cùng một \`ObjectName\` trong môi trường kiểm thử.
- So sánh metadata trên hai server/fixtures cô lập.
- Kiểm tra behavior trên client cũ.
- Bảo toàn notification và security contract.

**Sau migration:**

- Xác minh \`ObjectName\` qua \`queryNames\`.
- Xác minh attribute/operation metadata.
- Kiểm tra JConsole và remote JMX client khi có dùng remote.
- Giám sát registration errors và operation failure.
- Đảm bảo khi context đóng MBeans được unregister đúng owner.
- Chỉ xóa interface cũ khỏi client artifact khi đã kiểm kê tất cả consumers.

## 22. Kế hoạch rollout và rollback

Một migration production không nên dựa vào thay trực tiếp class rồi restart mà không có đường quay lại.

**Giai đoạn 1 — Baseline:** thu snapshot JMX contract và xác minh clients đang sử dụng tên nào.

**Giai đoạn 2 — Code:** gắn annotation nhưng chưa thay exporter ở runtime chính. Chuẩn bị cấu hình mới và tests.

**Giai đoạn 3 — Verification:** chạy cấu hình Standard MBean và annotation metadata trong hai isolated test environments; so sánh contract và functional behavior.

**Giai đoạn 4 — Canary:** triển khai một instance ứng dụng dùng annotation exporter, theo dõi errors, metrics và client compatibility. Những instance khác vẫn dùng config cũ.

**Giai đoạn 5 — Rollout:** chuyển dần các instances với naming/endpoint nhất quán. Không thay đổi remote authentication/network policy cùng lúc nếu không cần thiết.

**Giai đoạn 6 — Cleanup:** sau compatibility window, loại bỏ exporter cũ và interface server-side không còn dùng, nhưng giữ client-facing interface artifact nếu consumers còn phụ thuộc.

**Rollback:** dùng lại config cũ ở một deployment tương thích, bảo đảm chỉ một exporter đang đăng ký từng \`ObjectName\` trong cùng server. Nếu client đã thay đổi, cần xác định backward compatibility trước khi rollback.

Lưu ý trong môi trường nhiều JVM: mỗi JVM có registry riêng; hai versions có thể dùng cùng \`ObjectName\` mà không xung đột toàn cụm. Nhưng các monitoring systems cần nhận biết instance endpoint để không nhầm dữ liệu.

## 23. Bài tập thực hành

**Bài 1 — Standard MBean baseline.** Tạo \`CacheManagerMBean\` và \`CacheManager\`, export dưới \`com.example.cache:type=CacheManager,name=primary\`. Đọc \`MBeanInfo\`, ghi lại attributes và operation.

**Bài 2 — Annotation replacement.** Bỏ interface implementation trong một fixture riêng, gắn \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, bật \`@EnableMBeanExport\`. So sánh \`MBeanInfo\` với baseline.

**Bài 3 — Setter compatibility.** Cố ý bỏ \`@ManagedAttribute\` trên setter \`setEnabled\`, xác minh attribute trở thành read-only hoặc behavior thay đổi theo assembler. Sau đó sửa annotation và chạy lại test.

**Bài 4 — Operation signature.** Thêm \`reloadRules(String profile)\`, định nghĩa \`@ManagedOperationParameter\`. Gọi bằng \`MBeanServer.invoke\` với signature \`java.lang.String\`; thử sai signature rồi giải thích exception.

**Bài 5 — Client interface cũ.** Giữ \`CacheManagerMBean\` trong một module client, dùng \`JMX.newMBeanProxy\` gọi tới ModelMBean mới. Kiểm tra các method còn tương thích và ghi nhận khác biệt metadata.

**Bài 6 — Hai exporters.** Cố tình bật legacy exporter và annotation exporter cùng tên trong test isolated, quan sát lỗi, rồi chỉ giữ một exporter. Giải thích vì sao \`IGNORE_EXISTING\` có thể che migration chưa thực sự diễn ra.

**Bài 7 — AOP.** Bọc service trong JDK proxy theo business interface, thử export annotation metadata, kiểm tra \`AopUtils\` và \`MBeanInfo\`. Thực hiện một biến thể dùng management facade để tách concerns.

**Bài 8 — Remote compatibility.** Tạo JMX remote connector trong môi trường cô lập, đọc attribute và gọi operation từ JVM client khác. Nếu có MXBean/Open Types hoặc notifications, kiểm tra đúng kiểu dữ liệu và callback.

## Kết luận

**Migration từ interface MBean sang annotation metadata** trong Spring Framework JMX là thay cách mô tả hợp đồng quản trị, không nên đồng thời thay hành vi hệ thống ngoài ý muốn. Standard MBean interface và Spring annotation-based ModelMBean có cơ chế tạo metadata khác nhau, nên muốn tương thích phải bảo toàn **\`ObjectName\`, attribute names/types/access, operation signatures/behavior, notifications và client expectations**. Hãy triển khai trong môi trường cô lập, dùng \`MBeanInfo\` và integration tests để so sánh trước/sau, chỉ kích hoạt một exporter cho mỗi registration và giữ đường rollback rõ ràng. Kết quả migration tốt là khi ứng dụng dùng cấu hình mới nhưng các công cụ quản trị cũ vẫn hoạt động đúng contract đã cam kết.
