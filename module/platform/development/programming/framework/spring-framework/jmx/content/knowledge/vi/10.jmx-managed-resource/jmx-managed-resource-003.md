# Autodetect bean có @ManagedResource trong Spring Framework JMX

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao annotation \`@ManagedResource\` giúp Spring Framework nhận diện một bean có thể được xuất thành JMX MBean.
- Phân biệt **bean autodetection** với **metadata assembly** và **MBean registration**.
- Cấu hình \`MBeanExporter\` để tự phát hiện Spring beans có \`@ManagedResource\` mà không liệt kê từng bean bằng \`setBeans(...)\`.
- Sử dụng \`AnnotationJmxAttributeSource\`, \`MetadataMBeanInfoAssembler\` và \`MetadataNamingStrategy\` khi cấu hình thủ công.
- Kiểm tra MBean đã đăng ký qua \`MBeanServer\`, nhận diện ObjectName và những thuộc tính/thao tác thực sự được công bố.
- Chẩn đoán tình huống có \`@ManagedResource\` nhưng JConsole không thấy MBean, hoặc việc scan tự động làm phát sinh đăng ký trùng tên.

## 1. Bối cảnh: cần export nhiều Spring bean

Một ứng dụng Spring có nhiều thành phần cần được quản trị: cache, queue, scheduler, job processor, connection pool hoặc bộ điều khiển cấu hình.

Một cách đăng ký thủ công là khai báo từng bean trong \`MBeanExporter\`:

\`\`\`java
exporter.setBeans(Map.of(
    "learning.jmx:type=Cache,name=Products", productsCache,
    "learning.jmx:type=Queue,name=Primary", jobQueue
));
\`\`\`

Cách này tường minh nhưng phải cập nhật cấu hình exporter khi thêm bean mới. Spring Framework JMX cung cấp cách khai báo **metadata quản trị ngay trên bean** bằng các annotation thuộc \`org.springframework.jmx.export.annotation\`. Từ đó, exporter có thể tự tìm bean phù hợp theo một số quy tắc.

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Primary job queue"
)
public class QueueMonitor {
    // ...
}
\`\`\`

**Điểm quan trọng:** \`@ManagedResource\` mô tả resource có thể quản trị. Chỉ đặt annotation lên class **không tự động đăng ký MBean** nếu ứng dụng chưa kích hoạt cơ chế exporter và autodetection tương ứng.

## 2. Autodetect nghĩa là gì?

Trong phạm vi bài này, **autodetect** là việc Spring JMX exporter **tự phát hiện các bean trong ApplicationContext được đánh dấu là JMX-managed resource**, thay vì yêu cầu cấu hình một danh sách tên/instance thủ công cho từng bean.

Ba bước logic:

\`\`\`text
Spring ApplicationContext
        |
        | chứa các bean
        v
MBeanExporter autodetect
        |
        | tìm bean có metadata JMX tương ứng
        v
Metadata assembler + naming strategy
        |
        | xác định attributes, operations, ObjectName
        v
MBeanServer.registerMBean(...)
        |
        v
JConsole / JMX client
\`\`\`

Trong đó:

- **Autodetection:** tìm *bean nào* cần xuất.
- **Metadata assembly:** xác định *thuộc tính và phương thức nào* xuất cho JMX.
- **Naming strategy:** xác định *ObjectName nào* sử dụng.
- **Registration:** đăng ký MBean vào *MBeanServer nào*.

Đừng đánh đồng các nhiệm vụ này. Một bean có thể được phát hiện nhưng export vẫn thất bại nếu thiếu naming strategy phù hợp, ObjectName sai, tên bị trùng hoặc metadata không hợp lệ.

## 3. Các annotation cần biết

Spring Framework định nghĩa một số annotation hỗ trợ JMX:

| Annotation | Cấp áp dụng | Chức năng |
|---|---|---|
| \`@ManagedResource\` | Class | Đánh dấu resource được quản trị, chứa metadata như ObjectName, description |
| \`@ManagedAttribute\` | Getter/setter | Công bố thuộc tính quản trị |
| \`@ManagedOperation\` | Method | Công bố thao tác quản trị |
| \`@ManagedOperationParameter\` | Parameter | Mô tả tham số operation |
| \`@ManagedNotification\` | Class annotation metadata | Khai báo loại notification được hỗ trợ |

Autodetection dựa trên việc class có \`@ManagedResource\` phù hợp. Annotation \`@ManagedAttribute\` hoặc \`@ManagedOperation\` trên một bean bất kỳ không đương nhiên có nghĩa exporter sẽ tự phát hiện bean đó như một managed resource nếu không có marker/configuration phù hợp.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Queue monitor"
)
public class QueueMonitor {
    private volatile boolean paused;

    @ManagedAttribute(description = "Whether queue is paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause queue")
    public void pause() {
        paused = true;
    }
}
\`\`\`

Với cấu hình Spring JMX phù hợp, \`Paused\` trở thành attribute và \`pause()\` trở thành operation. Một method public khác không được annotate không mặc định trở thành JMX operation khi dùng annotation metadata assembler có chính sách công bố theo annotation.

## 4. Cách ngắn gọn: kích hoạt annotation-driven JMX

Spring Framework hỗ trợ \`@EnableMBeanExport\` để kích hoạt cấu hình xuất JMX dựa trên annotation. Đây là cách thuận tiện cho ứng dụng quản lý bằng Java configuration.

Ví dụ:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Spring sẽ thiết lập exporter cần thiết để phát hiện managed resources theo annotation. Bạn không cần viết \`setBeans(...)\` cho từng resource trong cấu hình này.

Bean cần được Spring quản lý, ví dụ:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Queue lifecycle"
)
public class QueueMonitor {

    private volatile boolean paused;

    @ManagedAttribute(description = "Paused state")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause intake")
    public void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Resume intake")
    public void resume() {
        paused = false;
    }
}
\`\`\`

**Điều kiện quan trọng:** class \`QueueMonitor\` phải được đăng ký thành Spring bean, chẳng hạn nhờ component scanning hoặc khai báo \`@Bean\`. \`@ManagedResource\` không tự biến một Java object nằm ngoài ApplicationContext thành Spring-managed bean.

Khi context khởi động, exporter quét/nhận diện managed resources và đăng ký chúng theo ObjectName vào MBeanServer được sử dụng.

### Nếu dùng XML configuration

Trong các ứng dụng Spring cấu hình bằng XML, phần tử \`<context:mbean-export />\` cung cấp cách bật annotation-driven JMX exporter tương ứng.

Ví dụ dạng XML:

\`\`\`xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/context
         https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="example.jmx"/>

    <context:mbean-export/>
</beans>
\`\`\`

Đây là một hướng cấu hình thay thế Java annotation. Thông thường không cần bật đồng thời nhiều exporter cho cùng managed resources trong một context.

## 5. MBeanExporter với autodetect mode

Khi cần điều khiển cấu hình thấp hơn, bạn có thể tạo \`MBeanExporter\` thủ công và thiết lập autodetect mode.

Spring định nghĩa các mode như:

- \`AUTODETECT_NONE\`: không tự phát hiện bean.
- \`AUTODETECT_MBEAN\`: tự phát hiện đối tượng phù hợp chuẩn MBean.
- \`AUTODETECT_ASSEMBLER\`: sử dụng khả năng nhận diện managed resource của assembler.
- \`AUTODETECT_ALL\`: kết hợp các cách phát hiện hỗ trợ.

Với annotation metadata, \`AUTODETECT_ASSEMBLER\` thường thể hiện đúng ý định: tìm bean mà metadata assembler nhận diện được, thay vì chỉ dựa trên interface \`SomethingMBean\`.

Cấu hình tối thiểu để hiểu vai trò các thành phần:

\`\`\`java
import java.lang.management.ManagementFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxConfig {

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
        MetadataNamingStrategy namingStrategy =
                new MetadataNamingStrategy();
        namingStrategy.setAttributeSource(source);
        return namingStrategy;
    }

    @Bean
    public MBeanExporter jmxExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectMode(
                MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

**Ý nghĩa cấu hình:**

1. \`AnnotationJmxAttributeSource\` đọc metadata từ các JMX annotations.
2. \`MetadataMBeanInfoAssembler\` xác định thông tin MBean, attributes, operations theo metadata.
3. \`MetadataNamingStrategy\` tìm ObjectName từ metadata như \`@ManagedResource.objectName\`.
4. \`MBeanExporter\` tự tìm các bean phù hợp và đăng ký chúng vào platform MBeanServer.

Đây là cấu hình học tập mang tính tường minh; trong ứng dụng thông thường \`@EnableMBeanExport\` giúp tránh viết lặp nhiều bean hạ tầng.

### Vì sao cần đúng assembler?

Nếu chỉ viết:

\`\`\`java
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

nhưng không dùng assembler có khả năng nhận diện \`@ManagedResource\`, bạn không nên mặc định annotation marker sẽ được xử lý đúng. Autodetection mode và metadata strategy là hai cấu hình bổ trợ cho nhau.

### Có nên dùng AUTODETECT_ALL?

\`AUTODETECT_ALL\` còn có thể phát hiện Standard MBean bên cạnh các bean được assembler nhận diện. Điều này hữu ích trong một số ứng dụng có cả hai kiểu quản trị, nhưng có thể mở rộng tập bean được export ngoài dự kiến. Khi yêu cầu chỉ là “autodetect bean có @ManagedResource”, chọn mode hẹp và có chủ đích thường dễ kiểm soát hơn.

## 6. ObjectName xuất hiện từ đâu?

Với annotation:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
\`\`\`

MetadataNamingStrategy có thể dùng ObjectName trên annotation để đăng ký bean.

ObjectName có dạng:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

Ví dụ:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Cache,name=Products
learning.jmx:type=Scheduler,name=Daily
\`\`\`

ObjectName phải hợp lệ và duy nhất trong **một MBeanServer**. Nếu hai bean cùng annotate một ObjectName, exporter có thể gặp lỗi đăng ký trùng.

**Không nhầm ObjectName với class name:** Java class \`QueueMonitor\` có thể đăng ký dưới tên \`learning.jmx:type=Queue,name=Primary\`. Class name và ObjectName có trách nhiệm khác nhau.

### Nếu thiếu objectName?

Khả năng sinh tên hoặc fallback phụ thuộc cấu hình naming strategy. Với bài học về autodetect, nên cung cấp ObjectName rõ ràng trên \`@ManagedResource\` hoặc xác định naming strategy chủ đích để giảm nhập nhằng. Không nên suy đoán tên được tạo khi chưa xem cấu hình thực tế.

## 7. Ví dụ thực hành hoàn chỉnh

Ta tạo hai Spring beans có \`@ManagedResource\`, đồng thời một bean nghiệp vụ thông thường.

### 7.1. QueueMonitor

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Primary queue monitor"
)
public class QueueMonitor {
    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void pause() {
        paused = true;
    }

    @ManagedOperation
    public void resume() {
        paused = false;
    }
}
\`\`\`

### 7.2. CacheMonitor

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=Products",
    description = "Product cache monitor"
)
public class CacheMonitor {
    private final AtomicInteger entryCount = new AtomicInteger(10);

    @ManagedAttribute
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedOperation
    public void clear() {
        entryCount.set(0);
    }
}
\`\`\`

### 7.3. Bean không được annotate

\`\`\`java
package example.jmx;

import org.springframework.stereotype.Component;

@Component
public class OrdinaryService {
    public String getStatus() {
        return "READY";
    }
}
\`\`\`

Trong cấu hình dựa trên metadata annotations và assembler autodetection, \`OrdinaryService\` không tự xuất chỉ vì nó là một \`@Component\`. Điều này minh họa ranh giới giữa đăng ký Spring bean và công bố JMX managed resource.

### 7.4. Java configuration

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan("example.jmx")
@EnableMBeanExport
public class ApplicationConfig {
}
\`\`\`

Khi khởi tạo context:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        ApplicationConfig.class)) {

            System.out.println("Context started");
            System.out.println("Press Enter to close");
            System.in.read();
        }
    }
}
\`\`\`

Trong JConsole, kết nối đúng Java process, mở tab MBeans, xem domain \`learning.jmx\` để tìm hai ObjectName. Bean OrdinaryService không được export theo mẫu metadata trên.

### 7.5. Kiểm tra bằng MBeanServer

Cách kiểm tra không phụ thuộc giao diện đồ họa:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName queueName = new ObjectName(
        "learning.jmx:type=Queue,name=Primary"
);
ObjectName cacheName = new ObjectName(
        "learning.jmx:type=Cache,name=Products"
);

System.out.println(server.isRegistered(queueName));
System.out.println(server.isRegistered(cacheName));
\`\`\`

Kết quả mong đợi sau khi context khởi tạo và exporter đã đăng ký:

\`\`\`text
true
true
\`\`\`

Nếu cấu hình \`@EnableMBeanExport\` dùng MBeanServer khác platform server hoặc ứng dụng có cấu hình tùy biến, phải kiểm tra trên **đúng server đang được exporter sử dụng**. Không nên mặc định một Java process mới có thể gọi \`ManagementFactory.getPlatformMBeanServer()\` rồi xem MBean của process khác; MBeanServer là tài nguyên của từng JVM.

## 8. Autodetection có phải scan toàn classpath?

Không. Trong mô hình \`MBeanExporter\`, autodetection chủ yếu làm việc với **beans được quản lý trong Spring ApplicationContext và phạm vi exporter có thể nhìn thấy**.

Điều này khác với component scan:

- \`@ComponentScan\` tìm class thích hợp để đăng ký thành Spring bean.
- \`@ManagedResource\` khai báo metadata JMX của bean đó.
- \`MBeanExporter\` autodetection tìm những bean trong context phù hợp để export.

Nếu một class có \`@ManagedResource\` nhưng chưa được đăng ký thành Spring bean, exporter không tự tìm tất cả class bytecode ở mọi JAR rồi tạo instance thay bạn.

### Tác động của parent-child context

Ứng dụng có parent context và child context có thể có phạm vi bean khác nhau. Nếu nhiều exporter cùng phát hiện một bean/định danh ObjectName, có thể phát sinh xung đột. Cần xác định rõ context nào là chủ thể sở hữu việc export và tránh xuất cùng ObjectName nhiều lần vào một MBeanServer.

## 9. Proxy và bean type: điều gì cần lưu ý?

Spring có thể tạo proxy cho \`@Transactional\`, \`@Async\`, AOP hoặc các tính năng khác. Khi một bean là proxy, runtime class có thể khác class gốc được annotate.

Cơ chế exporter/assembler của Spring có hỗ trợ xử lý nhiều trường hợp proxy, nhưng không nên giả định mọi loại proxy, factory bean hoặc custom wrapper đều được nhận diện theo cùng một cách. Nếu \`@ManagedResource\` có trên target class mà autodetection không thấy bean:

1. Kiểm tra bean có thực sự tồn tại trong ApplicationContext.
2. Kiểm tra exporter có đang dùng AnnotationJmxAttributeSource và assembler phù hợp không.
3. Kiểm tra proxy type, target class và metadata có thể truy cập.
4. Xem log exception lúc export, không chỉ nhìn JConsole.
5. Nếu cần, cấu hình explicit managed bean registration thay cho autodetection.

Trong dự án nhiều AOP proxy, đây là lý do nên thử integration một số bean thực tế và xác nhận metadata được công bố.

## 10. Sự khác nhau giữa Standard MBean convention và @ManagedResource

**Standard MBean convention** dựa vào interface được đặt tên theo lớp triển khai:

\`\`\`text
QueueMonitor -> QueueMonitorMBean
\`\`\`

Còn **annotation-driven JMX exporter** cho phép chọn attributes/operations qua Spring metadata:

\`\`\`java
@ManagedResource(objectName = "learning.jmx:type=Queue,name=Primary")
public class QueueMonitor {

    @ManagedAttribute
    public int getDepth() { return 0; }

    @ManagedOperation
    public void resetStats() { }
}
\`\`\`

Trong mô hình annotation exporter, class không nhất thiết phải implements \`QueueMonitorMBean\`. Spring assembler có thể tạo management interface/metadata để export object theo chiến lược cấu hình.

Đó cũng là lý do cần phân biệt \`AUTODETECT_MBEAN\` và \`AUTODETECT_ASSEMBLER\`: một mode dựa trên quy tắc MBean tự thân, mode kia dựa trên assembler có khả năng nhận diện managed resources.

## 11. Autodetect và @ManagedResource không bảo đảm quyền truy cập

Sau khi bean được export:

- JMX client muốn truy cập từ một JVM khác cần cơ chế kết nối phù hợp.
- Local JConsole/VisualVM vẫn phụ thuộc quyền process/attach.
- Remote JMX connector phụ thuộc network, authentication, TLS và policy.
- MBean operations có thể thay đổi trạng thái ứng dụng và phải được bảo vệ.
- Attribute hoặc operation được annotate không nên tiết lộ secret hay dữ liệu nhạy cảm.

Autodetection chỉ quyết định **đối tượng nào được công bố**, không có nghĩa nó phải truy cập được từ bên ngoài hoặc đã an toàn cho mọi người gọi.

Không bật remote JMX mở rộng chỉ để thử annotation. Khi cần quản trị từ xa, dùng chính sách truy cập và môi trường phù hợp.

## 12. Vòng đời export/unexport

Khi MBeanExporter là bean hạ tầng Spring:

1. ApplicationContext khởi tạo managed beans và exporter.
2. Exporter autodetect những bean đủ điều kiện.
3. MBean được đăng ký vào MBeanServer.
4. JMX client có thể truy vấn những MBean đã đăng ký nếu có kết nối.
5. Khi context đóng và exporter bị destroy, exporter thực hiện cleanup các registration thuộc phạm vi nó quản lý.

MBeanServer của JVM có thể tồn tại lâu hơn Spring context. Vì vậy khi test lifecycle, chỉ kiểm tra những ObjectName của ứng dụng; đừng mặc định mọi MBean trong platform server biến mất sau context.close().

### ObjectName bị trùng

Nếu hai context cùng export \`learning.jmx:type=Queue,name=Primary\` vào một MBeanServer, policy đăng ký quyết định hành vi. Đừng dùng replace/ignore một cách tùy tiện để che việc có hai chủ thể đang công bố cùng tên. Nên thiết kế naming scheme và ownership rõ ràng.

## 13. Lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Có \`@ManagedResource\` nhưng không thấy MBean | Chưa bật exporter/autodetect hoặc chưa đăng ký Spring bean | Kiểm tra \`@EnableMBeanExport\`, \`@Component\`/\`@Bean\`, context |
| Bean có annotation nhưng assembler không nhận diện | Dùng assembler/autodetect mode không phù hợp | Dùng \`AnnotationJmxAttributeSource\` với metadata assembler |
| MBean được đăng ký nhưng ObjectName khác mong đợi | Naming strategy hoặc metadata khác | Kiểm tra \`@ManagedResource.objectName\`, exporter strategy |
| \`InstanceAlreadyExistsException\` | Hai bean/context trùng ObjectName | Xác định ownership, thay naming scheme hoặc cleanup |
| Spring context fail lúc startup | Đăng ký JMX ném exception | Đọc root cause trong startup log |
| JConsole không thấy MBean | Sai JVM, sai MBeanServer, quyền/kết nối | Dùng \`isRegistered\`, xác nhận PID/connector |
| Attribute/operation không xuất hiện | Chưa có \`@ManagedAttribute\`/\`@ManagedOperation\` hoặc assembler không phù hợp | Dùng \`getMBeanInfo\` kiểm chứng |
| Một số bean không được autodetect | Bean ngoài context, proxy, lazy factory, phạm vi scan | Xác minh runtime bean và chiến lược exporter |
| Sau context.close() MBean vẫn còn | Đăng ký từ exporter khác/thủ công hoặc context chưa dừng | Truy nguyên ObjectName và chủ thể quản lý |
| Xuất hiện MBean ngoài mong muốn | AUTODETECT_ALL quá rộng hoặc nhiều exporter | Thu hẹp autodetect mode/bean selection |

### Chuỗi kiểm tra đề xuất

**Bước 1:** Xác nhận class có \`@ManagedResource\` và bean thực sự được đăng ký trong Spring.

**Bước 2:** Xác nhận \`MBeanExporter\` được tạo và chạy (thông qua \`@EnableMBeanExport\`, XML hoặc Java config).

**Bước 3:** Nếu tự cấu hình exporter, kiểm tra autodetect mode cùng attribute source/assembler/naming strategy.

**Bước 4:** Kiểm tra log lúc export để tìm lỗi mapping metadata, ObjectName hoặc registration.

**Bước 5:** Truy vấn \`MBeanServer.isRegistered(objectName)\` hoặc \`queryNames(...)\` trên server đúng.

**Bước 6:** Dùng \`getMBeanInfo\` để xem các attributes/operations thực tế. Chỉ sau đó mới điều tra vấn đề kết nối JConsole hoặc remote JMX.

## 14. Tình huống thực tế

### Tình huống A — Thêm một MBean mới

Một developer thêm \`@Component\` và \`@ManagedResource\` lên \`CacheMonitor\`. Ứng dụng đã có \`@EnableMBeanExport\`. Nếu ObjectName hợp lệ và không trùng, MBean mới có thể được phát hiện và xuất khi context khởi động mà không thêm entry \`setBeans(...)\` thủ công.

### Tình huống B — Class được annotate nhưng không nằm trong context

Một class \`QueueInspector\` có \`@ManagedResource\` nhưng được tạo bằng \`new QueueInspector()\` bên ngoài Spring. Nó không tự được autodetect bởi exporter của context. Cần tạo Spring bean hoặc đăng ký explicit nếu có lý do riêng.

### Tình huống C — Spring bean nhưng thiếu annotation class

Một bean chỉ có \`@ManagedOperation\` ở một method mà không được đánh dấu \`@ManagedResource\`. Không nên mặc định assembler autodetect sẽ coi nó là managed resource. Hãy dùng metadata đầy đủ hoặc explicit registration.

### Tình huống D — Nhiều context trùng ObjectName

Context A và B đều tìm thấy MBean với ObjectName giống nhau. Context thứ hai có thể thất bại vì trùng registration hoặc bị xử lý theo policy. Khắc phục bằng cách chỉ cho một context export, hoặc dùng ObjectName có namespace khác nếu đó là hai instance độc lập.

### Tình huống E — Một bean có nhiều phương thức public

Bean quản lý queue có method public \`pause\`, \`resume\`, \`removeAllJobs\` và \`getDepth\`. Chỉ annotate những operations thực sự cần công bố, tránh biến toàn bộ public API nghiệp vụ thành JMX management surface.

## 15. Bài tập thực hành

### Bài tập 1 — Bật autodetection

Tạo \`@EnableMBeanExport\`, hai beans \`QueueMonitor\` và \`CacheMonitor\` như phần 7. Chạy ApplicationContext và xác nhận cả hai ObjectName bằng \`MBeanServer.isRegistered\`.

Giải thích vì sao không cần gọi \`setBeans\` cho từng đối tượng trong ví dụ này.

### Bài tập 2 — Kiểm tra bean thiếu annotation

Bỏ \`@ManagedResource\` khỏi \`CacheMonitor\` rồi chạy lại. Với cấu hình chỉ autodetect annotation resources, dự đoán ObjectName \`learning.jmx:type=Cache,name=Products\` có còn được đăng ký hay không. Kiểm tra bằng JConsole và \`queryNames\`.

### Bài tập 3 — Dùng assembler mode

Thay cấu hình \`@EnableMBeanExport\` bằng \`ExplicitJmxConfig\` ở phần 5. Xác định vai trò riêng của AnnotationJmxAttributeSource, MetadataMBeanInfoAssembler, MetadataNamingStrategy và MBeanExporter. Giải thích lỗi có thể xảy ra nếu bỏ một thành phần.

### Bài tập 4 — Quan sát ObjectName collision

Tạo hai managed resources có cùng \`@ManagedResource.objectName\` trong cùng MBeanServer. Dự đoán lỗi đăng ký. Sau đó đổi tên theo domain/key properties hợp lý rồi kiểm tra lại.

### Bài tập 5 — Phân biệt Spring và JMX

Trả lời:

1. \`@ManagedResource\` tự tạo Spring bean không?
2. \`@Component\` tự động xuất thành JMX MBean không?
3. \`@ManagedOperation\` tự làm method public được phép gọi từ mọi client không?
4. ObjectName có phải là endpoint URL không?
5. MBean đã register có cần JMX connector để JVM khác truy cập không?

**Đáp án gợi ý:** Không; không; không; không; có đường kết nối JMX phù hợp mới truy cập được từ tiến trình khác.

## 16. Tổng kết mô hình tư duy

Để **autodetect bean có \`@ManagedResource\`** trong Spring Framework JMX, cần đủ ba điều kiện:

1. Bean tồn tại trong phạm vi Spring ApplicationContext mà exporter quản lý.
2. JMX annotation metadata có thể được đọc và xác định managed resource phù hợp.
3. Exporter được bật và cấu hình autodetect, assembler, naming strategy, MBeanServer phù hợp.

Đừng suy luận từ sự hiện diện của annotation rằng MBean đã được đăng ký. Hãy xác minh bằng \`isRegistered\` và \`getMBeanInfo\`.

Khi dùng \`@EnableMBeanExport\`, Spring giúp ghép các thành phần thông thường. Khi cần tùy biến nâng cao, cấu hình \`MBeanExporter\` và các metadata strategy tường minh để kiểm soát chính xác bean nào được export, công bố những gì và dưới ObjectName nào.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — EnableMBeanExport: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework API — AnnotationJmxAttributeSource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework API — MetadataMBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
