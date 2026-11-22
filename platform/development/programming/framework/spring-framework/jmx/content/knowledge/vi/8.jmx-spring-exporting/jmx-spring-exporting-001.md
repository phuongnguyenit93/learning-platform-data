# MBeanExporter là trung tâm xuất bean Spring sang MBeanServer

## 1. Mục tiêu và bối cảnh

Trong Spring Framework, một đối tượng do IoC container quản lý được gọi là **Spring bean**. Nhưng để các công cụ quản trị JMX như JConsole hoặc VisualVM nhìn thấy và thao tác với đối tượng đó, nó cần được đăng ký vào **JMX MBeanServer** theo một tên JMX hợp lệ.

**\`org.springframework.jmx.export.MBeanExporter\` là thành phần trung tâm thực hiện việc nối hai thế giới này.** Nó chọn những bean cần xuất bản, xác định \`ObjectName\`, tạo/adapt giao diện quản trị khi cần, đăng ký vào \`MBeanServer\`, và quản lý việc hủy đăng ký tương ứng với vòng đời Spring.

Sau bài này, bạn có thể:

- Giải thích ranh giới giữa \`ApplicationContext\`, \`MBeanExporter\`, \`ObjectName\` và \`MBeanServer\`.
- Tạo ví dụ Spring Framework thuần để export một Spring bean thành MBean.
- Hiểu cách \`MBeanExporter\` xử lý bean đã là JMX MBean so với bean Java thông thường có metadata quản trị.
- Sử dụng \`beans\`, \`assembler\`, \`namingStrategy\`, \`server\`, \`registrationPolicy\` và các cơ chế autodetect đúng mục đích.
- Phân biệt đăng ký JMX với expose HTTP endpoint và metrics.
- Chẩn đoán các lỗi thường gặp: sai ObjectName, không có exporter, không đúng MBeanServer, trùng tên hoặc metadata không hợp lệ.

**Mô hình tư duy:**

\`\`\`text
                Spring ApplicationContext
                  |      |      |
                  v      v      v
               Bean A  Bean B  Bean C
                  |            |
                  +------------+
                       |
                       v
                 MBeanExporter
          +------------+-------------+
          |            |             |
     chọn bean     chọn tên       chọn giao diện
                    ObjectName      quản trị
          +------------+-------------+
                       |
                 registerMBean()
                       |
                       v
                   MBeanServer
                       |
                       v
           JConsole / JMX client / JMX API
\`\`\`

Không phải mọi Spring bean đều tự trở thành MBean. **MBeanExporter đóng vai trò export/registration có chủ đích**, và một bean vẫn có thể hoạt động bình thường trong Spring dù không được export sang JMX.

## 2. Những thành phần cần phân biệt

| Thành phần | Vai trò |
|---|---|
| **Spring bean** | Đối tượng được Spring container tạo hoặc quản lý; được inject vào các bean khác |
| **ApplicationContext** | Registry và vòng đời của Spring beans |
| **MBeanExporter** | Cầu nối đưa bean được chọn sang hệ thống quản trị JMX |
| **ObjectName** | Định danh có cấu trúc của một MBean, ví dụ \`com.example:type=Worker,name=Import\` |
| **MBeanServer** | Registry và runtime quản trị MBean qua JMX |
| **MBeanInfoAssembler** | Quyết định attributes/operations/constructors/notifications được trình bày với JMX |
| **ObjectNamingStrategy** | Xác định ObjectName cho bean khi export |
| **JMX client** | Truy cập MBeanServer để duyệt tên, đọc thuộc tính, gọi operation và nhận notification |

Spring bean name (như \`orderMonitor\`) không phải là JMX ObjectName. \`ApplicationContext.getBean("orderMonitor")\` và \`MBeanServer.getAttribute(objectName, "QueueSize")\` đi qua hai API khác nhau.

MBeanExporter **không** phải là một HTTP router, metrics registry, message broker hay JVM monitoring agent. Nó làm nhiệm vụ đăng ký và trình bày tài nguyên quản trị theo chuẩn JMX.

## 3. Luồng export từ Spring bean đến MBeanServer

Một quy trình điển hình có các bước:

1. Spring khởi tạo \`ApplicationContext\` và tạo các bean theo cấu hình.
2. \`MBeanExporter\` nhận danh sách bean cần export hoặc tự phát hiện những bean phù hợp theo cấu hình.
3. Exporter xác định \`ObjectName\` cho từng bean bằng map tên tường minh hoặc naming strategy.
4. Exporter kiểm tra loại bean: bean đã tuân thủ JMX management interface hay cần lớp model MBean/adaptation dựa trên metadata.
5. Exporter đăng ký đối tượng quản trị với \`MBeanServer\`.
6. Client JMX truy cập MBean đã đăng ký bằng \`ObjectName\`.
7. Khi \`ApplicationContext\` đóng, exporter xử lý hủy đăng ký những MBean mà nó chịu trách nhiệm theo chính sách vòng đời.

**Đăng ký thành công** và **client remote truy cập được** là hai điều khác nhau. MBean có thể tồn tại trong platform MBeanServer của JVM nhưng không có remote connector được bật. Cần kiểm tra riêng cấu hình truy cập JMX remote.

### Vì sao cần exporter?

Một Spring bean Java thông thường không nhất thiết triển khai giao diện MBean theo quy ước JMX. \`MBeanExporter\` cho phép Spring áp dụng cơ chế ánh xạ metadata, naming và registration để đưa chức năng quản trị của bean ra JMX mà không bắt tất cả bean nghiệp vụ phải tự gọi \`registerMBean()\`.

Điều này tách mã nghiệp vụ khỏi mã quản lý MBeanServer. Spring quản lý lifecycle còn JMX client nhìn thấy giao diện quản trị.

## 4. Ví dụ 1: Xuất một Standard MBean đã có sẵn

JMX Standard MBean dùng một interface có hậu tố \`MBean\` theo quy ước. Trước hết, tạo interface:

\`\`\`java
package com.example.jmx;

public interface QueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}
\`\`\`

Tạo implementation:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicInteger pendingCount = new AtomicInteger();

    @Override
    public int getPendingCount() {
        return pendingCount.get();
    }

    @Override
    public void resetStatistics() {
        pendingCount.set(0);
    }

    public void updatePendingCount(int count) {
        pendingCount.set(count);
    }
}
\`\`\`

Cấu hình Spring Framework thuần:

\`\`\`java
package com.example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanExporter mBeanExporter(QueueMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example.monitoring:type=Queue,name=Orders",
            monitor
        ));

        return exporter;
    }
}
\`\`\`

Trong ví dụ này:

- \`QueueMonitor\` là Spring bean vì được tạo trong \`@Bean\`.
- \`QueueMonitorMBean\` khai báo interface quản trị cho Standard MBean.
- \`setBeans(...)\` chỉ định đối tượng cần export và tên JMX.
- \`MBeanExporter\` thực hiện đăng ký JMX.
- \`ObjectName\` là \`com.example.monitoring:type=Queue,name=Orders\`.
- Sau khi context khởi động, có thể truy vấn MBean từ đúng MBeanServer.

Thông qua JMX client, \`PendingCount\` xuất hiện như attribute có thể đọc; \`resetStatistics\` xuất hiện như operation. Phương thức \`updatePendingCount\` không nằm trong giao diện \`QueueMonitorMBean\`, do đó không tự động trở thành một JMX operation trong Standard MBean interface trên.

**Điểm cần hiểu:** Nếu bean đã là một Standard MBean hợp lệ, Spring có thể export trực tiếp bean đó. Không cần tạo thêm một HTTP controller để JMX nhận biết MBean.

## 5. Ví dụ 2: Export bean thông thường bằng annotation quản trị

Một bean không triển khai interface \`...MBean\` vẫn có thể được xuất qua metadata Spring JMX.

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import",
    description = "Import worker administration"
)
public class ImportWorkerMonitor {
    private final AtomicInteger activeJobs = new AtomicInteger();

    @ManagedAttribute(description = "Number of active jobs")
    public int getActiveJobs() {
        return activeJobs.get();
    }

    @ManagedOperation(description = "Reset administrative statistics")
    public void resetStatistics() {
        activeJobs.set(0);
    }

    public void setActiveJobs(int value) {
        activeJobs.set(value);
    }
}
\`\`\`

Annotation chỉ cung cấp metadata. **Cần có \`MBeanExporter\` được cấu hình để đọc metadata ấy và đăng ký bean.**

Một cấu hình tường minh:

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class AnnotatedJmxConfiguration {
    @Bean
    public MBeanExporter mBeanExporter() {
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

        // Cấu hình cụ thể bean được export hoặc autodetect
        // cần thống nhất với ApplicationContext.
        exporter.setAutodetectMode(
                MBeanExporter.AUTODETECT_ASSEMBLER
        );

        return exporter;
    }
}
\`\`\`

\`AUTODETECT_ASSEMBLER\` sử dụng assembler để xác định bean đủ điều kiện autodetect. Với metadata assembler như ở trên, các bean có metadata quản trị phù hợp là ứng viên export.

Trong Spring Framework còn có cách gọn hơn bằng \`@EnableMBeanExport\` hoặc XML \`<context:mbean-export />\`, tùy phong cách cấu hình. Các cơ chế này giúp khai báo exporter và các hỗ trợ annotation tương ứng, tránh phải lặp toàn bộ cấu hình thủ công.

Ví dụ:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Khi đã dùng \`@EnableMBeanExport\`, không nên tạo thêm một \`MBeanExporter\` trùng chức năng nếu không có mục đích rõ ràng. Duplicate exporter có thể dẫn đến xung đột ObjectName hoặc đăng ký trùng.

## 6. MBeanExporter lựa chọn bean để export bằng cách nào?

Có hai nhóm cách tiếp cận chính.

### 6.1. Khai báo tường minh với \`setBeans(...)\`

\`\`\`java
Map<String, Object> beans = Map.of(
    "com.example.monitoring:type=Queue,name=Orders",
    queueMonitor,
    "com.example.monitoring:type=Worker,name=Import",
    importWorkerMonitor
);
exporter.setBeans(beans);
\`\`\`

Cách này phù hợp khi cần:

- Biết chính xác những bean nào được phép expose.
- Kiểm soát từng ObjectName, tránh naming bất ngờ.
- Có danh sách MBean nhỏ, phục vụ vận hành rõ ràng.
- Hạn chế vô tình export các bean nội bộ không dành cho quản trị.

Trong thực tế, \`setBeans\` có thể được dùng với reference/name theo các hợp đồng cấu hình mà API hỗ trợ; ví dụ trên truyền trực tiếp object để thể hiện ý tưởng.

### 6.2. Autodetect các bean phù hợp

Exporter có thể được cấu hình để tự tìm những bean thỏa điều kiện JMX/assembler. Các chế độ quan trọng:

- \`AUTODETECT_NONE\`: không tự phát hiện, chỉ export những gì được chỉ định.
- \`AUTODETECT_MBEAN\`: phát hiện các bean đã tuân thủ giao diện JMX MBean.
- \`AUTODETECT_ASSEMBLER\`: dựa vào \`MBeanInfoAssembler\` được cấu hình để chọn ứng viên.
- \`AUTODETECT_ALL\`: kết hợp các cơ chế tự phát hiện.

Autodetect giúp giảm cấu hình khi có nhiều MBean, nhưng phạm vi export phải được kiểm soát. **Đừng mặc định rằng mọi \`@Component\` sẽ xuất thành MBean**, cũng đừng kết luận chỉ cần \`@ManagedResource\` là đủ nếu cơ chế export chưa được bật.

Đối với dữ liệu nhạy cảm hoặc thao tác quản trị có tác động lớn, việc kiểm soát tập MBean và metadata được phơi bày quan trọng hơn sự tiện lợi của autodetect.

## 7. ObjectName và naming strategy

JMX MBean được định danh bởi \`javax.management.ObjectName\`, ví dụ:

\`\`\`text
com.example.monitoring:type=Queue,name=Orders
\`\`\`

Cần phân biệt:

- **Spring bean name:** \`queueMonitor\`.
- **ObjectName:** \`com.example.monitoring:type=Queue,name=Orders\`.
- **Java class:** \`com.example.jmx.QueueMonitor\`.

Một tên bean trong Spring không tự động là ObjectName hoàn chỉnh. \`ObjectNamingStrategy\` xác định tên JMX thích hợp khi exporter không có mapping rõ ràng.

Spring cung cấp những chiến lược như:

- \`KeyNamingStrategy\`: dùng key trong mapping và metadata cấu hình để quyết định ObjectName.
- \`MetadataNamingStrategy\`: đọc thông tin như \`@ManagedResource(objectName=...)\`.
- \`IdentityNamingStrategy\`: tạo tên dựa trên identity/type của đối tượng trong những tình huống phù hợp.

Với tên động có dấu phẩy, dấu bằng, dấu sao hoặc dấu hỏi, nên dùng \`ObjectName\` API và \`ObjectName.quote(value)\` để tránh biến dữ liệu thành cú pháp key properties hoặc pattern ngoài ý muốn.

Ví dụ:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Worker");
properties.put("name", ObjectName.quote("Import,Asia=East"));

ObjectName objectName = new ObjectName(
    "com.example.monitoring",
    properties
);
\`\`\`

Naming strategy chỉ giải quyết **cách đặt tên**. Nó không thay thế quyết định **bean nào được export**, **thuộc tính/phương thức nào được expose** hay **ai có quyền truy cập**.

## 8. MBeanInfoAssembler: kiểm soát bề mặt quản trị

Đối với bean Java không triển khai interface MBean chuẩn, exporter cần xác định phương thức nào trở thành JMX attribute/operation. \`MBeanInfoAssembler\` đảm nhận phần lớn công việc mô tả metadata quản trị.

Ví dụ annotation:

\`\`\`java
@ManagedAttribute
public int getActiveJobs() {
    return activeJobs.get();
}

@ManagedOperation
public void resetStatistics() {
    activeJobs.set(0);
}
\`\`\`

Có ý nghĩa rằng:

- \`getActiveJobs()\` là getter cho JMX attribute \`ActiveJobs\`.
- \`resetStatistics()\` là một JMX operation.
- Các method không được chọn bởi assembler không vì thế tự động trở thành API quản trị.

Một số assembler trong Spring hỗ trợ chọn method theo annotation, interface hoặc quy tắc khác. Chọn assembler phù hợp giúp giảm việc vô tình expose logic nội bộ.

Không nên coi việc một method là \`public\` trong Java đồng nghĩa với việc nó an toàn để gọi từ JMX. Một operation như \`deleteAllData()\` nếu vô tình bị expose có thể gây hậu quả nghiêm trọng, nhất là khi JMX remote được mở rộng quyền truy cập.

## 9. MBeanServer mà exporter sử dụng

\`MBeanExporter\` phải đăng ký MBean vào một \`MBeanServer\`. Có thể chỉ định server bằng \`setServer(...)\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ServerConfiguration {
    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter exporter(
            MBeanServer server,
            QueueMonitor queueMonitor
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(java.util.Map.of(
            "com.example.monitoring:type=Queue,name=Orders",
            queueMonitor
        ));
        return exporter;
    }
}
\`\`\`

Trong một ứng dụng thực tế, chọn **một cấu hình exporter thống nhất**; các ví dụ khác nhau trong bài là các lựa chọn, không nên ghép tất cả thành nhiều exporter độc lập cùng đăng ký ObjectName giống nhau.

Khi không cấp server, Spring có cơ chế tìm MBeanServer thông qua hạ tầng JMX. Tuy nhiên, nếu ứng dụng chạy nhiều MBeanServer hoặc môi trường có cấu hình riêng, nên chỉ định rõ để tránh tình huống “Spring báo export thành công nhưng client đang nhìn sai server”.

Có thể xác minh trực tiếp:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Queue,name=Orders"
);

boolean present = server.isRegistered(name);
System.out.println("Registered: " + present);
\`\`\`

**Lưu ý:** \`isRegistered(name)\` chỉ kiểm tra MBeanServer đã chọn, tại thời điểm gọi. Nó không bảo đảm remote connector đã bật hoặc caller từ bên ngoài có quyền thao tác.

## 10. Registration policy và xung đột ObjectName

Mỗi MBeanServer có thể có **một MBean cho một ObjectName cụ thể**. Khi một ObjectName đã được đăng ký, exporter cần biết cách ứng xử.

Spring cung cấp các registration policy thông dụng:

| Policy | Ý nghĩa |
|---|---|
| \`FAIL_ON_EXISTING\` | Báo lỗi nếu tên đã đăng ký; thích hợp khi đăng ký trùng là lỗi cấu hình |
| \`IGNORE_EXISTING\` | Bỏ qua MBean đã tồn tại tại tên đó |
| \`REPLACE_EXISTING\` | Thay thế đăng ký hiện hữu theo chính sách exporter |

Ví dụ:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Nên cân nhắc:

- **Fail** có thể giúp phát hiện cấu hình sai sớm.
- **Ignore** có thể khiến MBean cũ vẫn được dùng, gây bất ngờ nếu bạn tưởng exporter mới đã thay thế.
- **Replace** có thể ảnh hưởng MBean do thành phần khác đăng ký; không dùng tùy tiện trong JVM chia sẻ MBeanServer.

Vòng đời hủy đăng ký cũng liên quan đến ownership và policy. Không nên giả định mọi MBean có cùng prefix sẽ bị exporter gỡ khi context đóng. Exporter cần quản lý đúng các đăng ký mà nó đã tạo/theo dõi.

### Race khi đăng ký

Hai context hoặc hai exporter có thể cùng cố đăng ký một ObjectName. Kiểm tra trước \`server.isRegistered(name)\` rồi gọi register không loại bỏ hoàn toàn race. Chính thao tác đăng ký phải xử lý xung đột theo API/policy của JMX. Nếu kiến trúc có nhiều context, hãy thiết kế naming và ownership tránh trùng ngay từ đầu.

## 11. Vòng đời export và unregister

Một đặc điểm quan trọng của \`MBeanExporter\` là nó tích hợp với Spring lifecycle. Khi bean exporter được khởi tạo và các phụ thuộc cần thiết sẵn sàng, exporter thực hiện đăng ký. Khi Spring application context đóng bình thường, exporter xử lý dọn dẹp đăng ký của mình.

Một luồng điển hình:

\`\`\`text
Start ApplicationContext
        |
        v
Create managed beans
        |
        v
Initialize MBeanExporter
        |
        v
Register MBeans in server
        |
        v
Runtime: JMX clients read/invoke/listen
        |
        v
Close ApplicationContext
        |
        v
MBeanExporter cleans up registrations
\`\`\`

Đây là lifecycle bình thường, không phải cam kết dọn dẹp khi JVM bị kill đột ngột. Nếu MBeanServer cũng kết thúc cùng JVM thì trạng thái registry biến mất theo tiến trình. Nếu có thiết kế server riêng hoặc context sống khác nhau, phải xét ownership của từng đăng ký.

Khi dùng Spring refresh/redeploy/restart, cần tránh tên cố định bị đăng ký đồng thời giữa context cũ và mới hoặc nhiều module cùng JVM. Đặt ObjectName nhất quán và dùng policy phù hợp.

## 12. Khác biệt giữa export JMX, endpoint và metric

Một hệ thống có thể cung cấp cả ba:

\`\`\`text
                    Spring service
                         |
              +----------+----------+
              |          |          |
         MBeanExporter  Controller  Micrometer
              |          |          |
         MBeanServer   HTTP API   Metric registry
              |          |          |
           JConsole    REST client Dashboard
\`\`\`

- **MBeanExporter:** đăng ký đối tượng quản trị qua JMX.
- **HTTP endpoint:** expose chức năng qua URL/route, ví dụ \`GET /actuator/health\` hoặc \`GET /api/orders\`.
- **Metric:** số liệu như current queue length hoặc request duration, do instrumentation/registry quản lý.

Không phải Spring bean nào cũng là MBean. Không phải MBean nào cũng tạo HTTP endpoint. Một attribute số học của MBean có thể phản ánh cùng đại lượng với metric gauge, nhưng **attribute và metric không phải một thực thể**.

Spring Boot Actuator có các cơ chế quản trị riêng, gồm endpoint qua JMX và HTTP tùy cấu hình. Khi dùng Boot, cần xem cấu hình JMX export (ví dụ \`spring.jmx.enabled\`) cùng Actuator exposure; tránh suy luận việc bật HTTP Actuator tự xuất tất cả \`@ManagedResource\` thành MBean, hoặc bật JMX MBeanExporter sẽ tự xuất mọi Actuator HTTP endpoint.

## 13. Cấu hình Spring Boot: điểm cần lưu ý

Trong Spring Boot, cơ chế JMX export có thể được cấu hình tự động, nhưng trạng thái mặc định và điều kiện phụ thuộc phiên bản/cấu hình. Với Boot, hãy xem tài liệu phiên bản đang sử dụng và các property tương ứng, tiêu biểu \`spring.jmx.enabled\`.

Nếu ứng dụng dùng auto-configuration:

1. Xác định Boot có đang tạo/export MBeans hay không.
2. Kiểm tra các \`@ManagedResource\` hoặc Standard MBean mà bạn muốn expose.
3. Tránh khai báo \`@EnableMBeanExport\` hoặc \`MBeanExporter\` thứ hai nếu cùng nhiệm vụ đã được Boot xử lý.
4. Kiểm tra xung đột ObjectName và cách Boot chọn domain naming/context id.
5. Xác minh trên đúng MBeanServer và đúng JVM.

Đừng coi mọi hành vi Spring Framework thuần và Spring Boot giống hệt nhau. \`MBeanExporter\` vẫn là khái niệm lõi của Spring JMX, trong khi Boot đóng vai trò tự cấu hình một số chi tiết.

## 14. Cách kiểm tra exporter có hoạt động không

Một quy trình kiểm tra kỹ thuật:

**Bước 1 — Xác định target MBean.**  
Ghi rõ ObjectName mong đợi, ví dụ \`com.example.monitoring:type=Queue,name=Orders\`.

**Bước 2 — Xác minh Spring configuration.**  
Có \`MBeanExporter\`, \`@EnableMBeanExport\` hoặc auto-configuration phù hợp? Bean đích có được exporter chọn không?

**Bước 3 — Xác minh loại bean và metadata.**  
Bean đã triển khai interface Standard MBean/MXBean hợp lệ hay cần \`MBeanInfoAssembler\`? Annotation \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` có được assembler nhận diện không?

**Bước 4 — Xác minh tên.**  
Dùng \`new ObjectName(...)\` để parse; kiểm tra domain/key và wildcard; với tên động, dùng \`ObjectName.quote()\` thay vì nối dữ liệu chưa escape.

**Bước 5 — Xác minh MBeanServer.**  
Gọi \`server.isRegistered(objectName)\` trong đúng JVM/server; có thể dùng \`queryNames()\` để tìm trong domain.

**Bước 6 — Xác minh metadata.**  
Dùng \`server.getMBeanInfo(objectName)\` để xem attributes/operations có xuất đúng dự kiến không.

**Bước 7 — Xác minh client.**  
Mở JConsole hoặc client JMX, kết nối đúng process/connector. Remote access yêu cầu server/port và bảo mật riêng.

Ví dụ introspection:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Queue,name=Orders"
);

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    for (var attribute : info.getAttributes()) {
        System.out.println("Attribute: "
                + attribute.getName());
    }

    for (var operation : info.getOperations()) {
        System.out.println("Operation: "
                + operation.getName());
    }
}
\`\`\`

Nếu \`isRegistered\` trả false, cần xem lại exporter/target server, không suy ra rằng Java object không tồn tại trong Spring container.

## 15. Những lỗi thường gặp

### 15.1. Có \`@Component\` nhưng không thấy MBean

**Nguyên nhân thường gặp:** Spring bean được tạo, nhưng exporter không chọn nó hoặc JMX export chưa bật.

**Hướng xử lý:** Kiểm tra \`setBeans\`, autodetect mode, \`@EnableMBeanExport\` hay cấu hình Boot, đồng thời kiểm tra metadata cần thiết.

### 15.2. \`@ManagedResource\` có rồi nhưng không có attribute

**Nguyên nhân thường gặp:** Assembler không đọc annotation, hoặc method chưa có \`@ManagedAttribute\`/\`@ManagedOperation\` phù hợp.

**Hướng xử lý:** Cấu hình \`MetadataMBeanInfoAssembler\` và \`AnnotationJmxAttributeSource\` hoặc dùng cơ chế annotation export chuẩn.

### 15.3. \`InstanceAlreadyExistsException\` hoặc lỗi trùng ObjectName

**Nguyên nhân thường gặp:** Hai exporter/context đăng ký cùng tên, một MBean đã tồn tại, hoặc naming strategy trả tên trùng.

**Hướng xử lý:** Chỉnh naming và ownership; cân nhắc registration policy theo mục đích. Không dùng \`REPLACE_EXISTING\` chỉ để che lỗi cấu hình.

### 15.4. MBean có mặt trong platform server nhưng JConsole remote không thấy

**Nguyên nhân thường gặp:** Client kết nối sai JVM/connector, remote JMX chưa mở hoặc phân quyền/network không phù hợp.

**Hướng xử lý:** Kiểm tra đúng \`MBeanServer\`, đúng process, cấu hình remote và bảo mật.

### 15.5. Bean đã export nhưng method mong muốn không xuất hiện

**Nguyên nhân thường gặp:** Method không nằm trong Standard MBean interface hoặc chưa được chọn bởi assembler.

**Hướng xử lý:** Xem \`MBeanInfo\` và hợp đồng exposure; không tự động expose mọi method public.

### 15.6. Exporter làm chậm khởi động hoặc thất bại khi register

**Nguyên nhân thường gặp:** Metadata không hợp lệ, ObjectName sai cú pháp, bean initialization lỗi, xung đột đăng ký hoặc target server không sẵn sàng.

**Hướng xử lý:** Đọc exception gốc, xác định bean và ObjectName gây lỗi, xử lý ở cấu hình/nguồn. Tránh nuốt lỗi làm cho hệ thống “khởi động thành công nhưng thiếu MBean”.

### 15.7. Export trùng do Spring Boot và cấu hình thủ công

**Nguyên nhân thường gặp:** Boot auto-configuration đã tạo exporter, ứng dụng lại khai báo thêm một exporter hoặc \`@EnableMBeanExport\`.

**Hướng xử lý:** Chỉ định rõ bên chịu trách nhiệm và kiểm tra cấu hình thực tế. Không nhân đôi cơ chế đăng ký cùng tài nguyên.

## 16. Thiết kế an toàn cho MBeanExporter

JMX là bề mặt quản trị. Hãy áp dụng các nguyên tắc:

- Chỉ export **những khả năng cần thiết** cho vận hành.
- Không expose operation làm thay đổi nghiệp vụ khi không có chính sách bảo vệ rõ ràng.
- Không trả bí mật, token, credentials hoặc thông tin cá nhân qua JMX attributes.
- Đặt ObjectName dễ hiểu và ổn định; không đưa dữ liệu định danh không giới hạn trực tiếp vào key properties.
- Nếu mở JMX remote, quản lý authentication, authorization, mạng, kênh truyền và giám sát truy cập.
- Giữ logic quản trị nhẹ; operation dài cần có kiểm soát timeout, concurrency và phản hồi trạng thái.
- Khi exporter có trách nhiệm unregister, chú ý vòng đời context và các thành phần đăng ký cùng MBeanServer.
- Theo dõi lỗi export ngay khi ứng dụng khởi động và xác minh MBean thực sự xuất hiện trên server mong muốn.

**Một MBean có thể hiện ra rất tiện lợi trong JConsole, nhưng một operation JMX vẫn là lời gọi có quyền tác động vào process.** Không nên coi nó là đường debug vô hại.

## 17. Bài tập thực hành

### Bài tập A — Export MBean tối thiểu

1. Tạo \`CounterMonitorMBean\` với \`getCount()\` và \`reset()\`.
2. Viết class \`CounterMonitor\` triển khai interface.
3. Đăng ký class thành Spring bean.
4. Cấu hình \`MBeanExporter.setBeans(...)\` với ObjectName \`com.example.training:type=Counter,name=Demo\`.
5. Khởi động Spring context.
6. Dùng \`MBeanServer.isRegistered()\` kiểm tra tên.
7. Dùng \`getMBeanInfo()\` xác minh \`Count\` và \`reset\` được expose.
8. Đóng context và kiểm tra trạng thái unregister trong điều kiện lifecycle bình thường.

### Bài tập B — Annotation-driven export

1. Tạo bean \`@ManagedResource\`.
2. Đánh dấu một getter bằng \`@ManagedAttribute\`.
3. Đánh dấu một method quản trị bằng \`@ManagedOperation\`.
4. Bật \`@EnableMBeanExport\` trong Spring Framework thuần.
5. Dùng JConsole xem ObjectName, attribute và operation.
6. Xóa annotation operation để thấy khác biệt metadata được expose sau khi khởi động lại context.

### Bài tập C — Xung đột đăng ký

1. Tạo hai MBean có cùng ObjectName.
2. Thử \`FAIL_ON_EXISTING\` và quan sát lỗi.
3. Chỉ sau khi hiểu ownership, thử các policy khác trong môi trường thử nghiệm.
4. Ghi lại khác biệt về object được nhìn thấy và lifecycle.

### Bài tập D — Phân biệt server và client

1. Export một MBean vào platform MBeanServer của một JVM.
2. Dùng \`isRegistered()\` trong JVM ấy để xác minh.
3. Mở JConsole gắn vào đúng process.
4. So sánh với một JConsole kết nối vào JVM khác.
5. Kết luận vì sao “đã export” không đủ để khẳng định “mọi JMX client đều nhìn thấy”.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Có một \`@Service\` tên \`OrderService\`. Nó tự động là MBean chưa?  
**Đáp án:** Chưa. Spring bean cần cơ chế export/registration sang JMX, thường qua \`MBeanExporter\`.

**Câu 2.** \`MBeanExporter\` và \`MBeanServer\` có vai trò giống nhau không?  
**Đáp án:** Không. Exporter là cầu nối chọn và đăng ký bean; MBeanServer là registry/runtime JMX lưu các MBean đã đăng ký.

**Câu 3.** Dùng \`@ManagedResource\` nhưng không có cơ chế annotation export phù hợp thì điều gì xảy ra?  
**Đáp án:** Annotation không tự bảo đảm bean được đăng ký. Cần exporter và cơ chế metadata/naming tương ứng.

**Câu 4.** Vì sao hai Spring beans có tên khác nhau vẫn có thể xung đột khi export?  
**Đáp án:** Chúng có thể được gán cùng \`ObjectName\` trên cùng \`MBeanServer\`.

**Câu 5.** \`MBeanInfoAssembler\` giải quyết vấn đề gì?  
**Đáp án:** Quyết định phần giao diện quản trị được trình bày từ bean, như attributes/operations, thay vì tự expose mọi phương thức.

**Câu 6.** Một MBean đã đăng ký có tự có REST endpoint không?  
**Đáp án:** Không. JMX registration và HTTP endpoint là hai cơ chế khác nhau.

**Câu 7.** Tại sao cấu hình \`RegistrationPolicy.REPLACE_EXISTING\` cần cân nhắc kỹ?  
**Đáp án:** Có thể thay thế MBean của một exporter/context khác, gây tác động đến ownership và quan sát vận hành.

## 19. Ghi nhớ

- **\`MBeanExporter\` là cầu nối xuất Spring bean sang JMX MBeanServer.**
- Spring container quản lý đối tượng Java; MBeanServer quản lý biểu diễn JMX được đăng ký bằng \`ObjectName\`.
- \`setBeans\` kiểm soát các bean tường minh; autodetect chọn bean phù hợp theo chế độ cấu hình.
- \`MBeanInfoAssembler\` quyết định giao diện quản trị; \`ObjectNamingStrategy\` quyết định tên MBean.
- Exporter thực hiện registration và quản lý lifecycle/unregistration theo cấu hình.
- \`@ManagedResource\` và các annotation quản trị cần exporter/metadata support để có tác dụng.
- MBean export không đồng nghĩa với HTTP endpoint, metric hay cấu hình kết nối JMX remote.
- Kiểm tra kết quả bằng \`MBeanServer.isRegistered()\` và \`getMBeanInfo()\` trên đúng server.
- Cấu hình registration policy, tên JMX và quyền truy cập phù hợp để tránh xung đột và bề mặt quản trị không an toàn.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Exporting Your Beans to JMX: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`@EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Spring Framework Javadoc — \`MBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MBeanInfoAssembler.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
