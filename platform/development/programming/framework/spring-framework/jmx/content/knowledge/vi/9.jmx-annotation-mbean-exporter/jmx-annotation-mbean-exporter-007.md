# AnnotationMBeanExporter: Phân biệt cấu hình exporter tường minh và tự động

## 1. Mục tiêu

Trong Spring Framework, một Java bean chỉ trở thành thành phần quản trị JMX khi có cơ chế **export** đăng ký nó vào \`MBeanServer\`. Nhóm annotation như \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` mô tả *cái gì* được quản trị, còn exporter xác định *bean nào, với ObjectName nào, trong MBeanServer nào* được đăng ký.

Có hai cách tổ chức cấu hình thường gặp:

1. **Tường minh (explicit):** ứng dụng chủ động tạo/cấu hình \`MBeanExporter\`, chỉ định bean, ObjectName, assembler, naming strategy, server và hành vi đăng ký.
2. **Tự động (annotation-driven):** bật cơ chế tìm bean được annotate, thường với \`@EnableMBeanExport\` trong cấu hình Java/Spring, để Spring tạo hạ tầng \`AnnotationMBeanExporter\` cần thiết.

Cả hai vẫn sử dụng Spring JMX exporter và Java JMX chuẩn. Sự khác biệt chính là **ai sở hữu danh sách bean, cách chọn tên và mức kiểm soát đăng ký**.

\`\`\`text
                       Spring ApplicationContext
                                 |
           +---------------------+---------------------+
           |                                           |
     Explicit exporter                         Annotation-driven
     MBeanExporter                              @EnableMBeanExport
     setBeans({...})                           AnnotationMBeanExporter
           |                                           |
           +---------------------+---------------------+
                                 |
                     MBeanServer + ObjectName
                                 |
                 JConsole / VisualVM / JMX client
\`\`\`

Đừng đồng nhất “có annotation” với “đã được export”: một bean được đánh dấu \`@ManagedResource\` không tự xuất hiện trong JMX nếu không có cơ chế exporter hoạt động phù hợp.

## 2. Thành phần nền tảng

| Thành phần | Trách nhiệm |
|---|---|
| \`MBeanServer\` | Đăng ký, tìm và tương tác với các MBean đang chạy |
| \`ObjectName\` | Tên JMX duy nhất trong một MBeanServer |
| \`MBeanExporter\` | Export bean từ Spring sang JMX |
| \`AnnotationMBeanExporter\` | Cấu hình exporter chuyên hỗ trợ annotation-driven JMX |
| \`@EnableMBeanExport\` | Kích hoạt annotation-driven export trong Spring Java configuration |
| \`@ManagedResource\` | Đánh dấu bean là tài nguyên quản trị và có thể đặt ObjectName/description |
| \`@ManagedAttribute\` | Công bố getter/setter thuộc tính |
| \`@ManagedOperation\` | Công bố thao tác quản trị |
| \`MetadataMBeanInfoAssembler\` | Đọc metadata quản trị được mô tả bởi annotations qua nguồn metadata |
| \`AnnotationJmxAttributeSource\` | Cung cấp metadata từ annotation cho assembler |

Cần phân biệt Spring JMX annotation với Java chuẩn \`javax.management\`:

- Java JMX client vẫn gọi \`getAttribute\`, \`setAttribute\`, \`invoke\` bằng \`MBeanServerConnection\`.
- Spring annotation chủ yếu ảnh hưởng thời điểm xuất bean, cách tạo ModelMBean metadata và tên đăng ký.
- \`@ManagedResource\` không biến một lớp thành Standard MBean theo quy ước \`XxxMBean\`; việc export POJO cần adapter/assembler phù hợp.

## 3. Một bean ví dụ dùng cho cả hai phương án

Giả sử ứng dụng có dịch vụ xử lý tác vụ với các member quản trị:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=primary",
    description = "Worker runtime management"
)
public class WorkerControl {
    private volatile int maxThreads = 8;
    private final AtomicLong completed = new AtomicLong();

    @ManagedAttribute(description = "Configured worker limit")
    public int getMaxThreads() {
        return maxThreads;
    }

    @ManagedAttribute(description = "Change configured worker limit")
    public void setMaxThreads(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("maxThreads must be 1..64");
        }
        maxThreads = value;
    }

    @ManagedAttribute(description = "Completed jobs")
    public long getCompleted() {
        return completed.get();
    }

    @ManagedOperation(description = "Reset completed counter")
    public void resetCounter() {
        completed.set(0);
    }

    public void internalDiagnostics() {
        // Không annotate: không được công bố bởi metadata annotation.
    }
}
\`\`\`

Ví dụ sử dụng \`volatile\` và \`AtomicLong\` để tập trung vào giao diện JMX. Trong hệ thống thật, việc chỉnh \`maxThreads\` cần được nối với executor/pool tương ứng: đổi một Java field chưa chắc đã tái cấu hình tài nguyên runtime.

Hợp đồng JMX mong muốn:

\`\`\`text
ObjectName = com.example.app:type=WorkerControl,name=primary

Attributes:
  MaxThreads   int   readable + writable
  Completed    long  read-only

Operations:
  resetCounter()
\`\`\`

\`internalDiagnostics\` không được đưa vào giao diện quản trị chỉ vì public. Việc lựa chọn member sẽ phụ thuộc assembler và metadata thực tế.

## 4. Cấu hình tường minh với MBeanExporter

Khi muốn chỉ rõ từng bean và tên JMX, có thể tạo \`MBeanExporter\` như một Spring bean.

Ví dụ dùng assembler đọc annotation để bảo đảm lớp POJO được xuất theo \`@ManagedAttribute\` và \`@ManagedOperation\`:

\`\`\`java
package com.example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource attributeSource) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(attributeSource);
        return assembler;
    }

    @Bean
    public MBeanExporter workerExporter(
            WorkerControl workerControl,
            MetadataMBeanInfoAssembler jmxAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(jmxAssembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

Trong mô hình này, \`setBeans\` xác định **bean cụ thể** được export và ObjectName tương ứng. Assembler xác định **member được công bố**. Tên ở \`setBeans\` là lựa chọn tường minh của ứng dụng; cần giữ nó nhất quán với metadata annotation để tránh nhầm lẫn khi mở rộng cấu hình.

### 4.1. Lợi ích

- Có danh sách bean và ObjectName rõ ràng để kiểm kê.
- Dễ cấu hình các thành phần có tên động hoặc nhiều instance cùng class.
- Dễ chỉ định một \`MBeanServer\` cụ thể khi có nhiều server.
- Có thể cấu hình assembler, naming strategy, listener, registration policy theo một điểm sở hữu.
- Phù hợp khi cần giới hạn chính xác bề mặt quản trị hoặc tích hợp mô hình JMX hiện hữu.

### 4.2. Chi phí

- Phải cập nhật cấu hình khi thêm hoặc bỏ bean được quản trị.
- Có thể lặp mapping trong những ứng dụng có rất nhiều MBean.
- Nếu đồng thời bật annotation auto-detection khác, nguy cơ đăng ký trùng.
- Người viết cấu hình phải hiểu quan hệ giữa bean Spring, JMX metadata và ObjectName.

**Điểm cần nhớ:** explicit exporter không đồng nghĩa bỏ qua annotation. Ta vẫn có thể dùng \`MetadataMBeanInfoAssembler\` để áp dụng annotation, nhưng lựa chọn bean và đăng ký vẫn là việc chủ động của ứng dụng.

## 5. Cấu hình tự động với @EnableMBeanExport

Với Spring Java configuration, cách gọn hơn là khai báo:

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class AutomaticJmxConfiguration {

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }
}
\`\`\`

\`@EnableMBeanExport\` bật cơ chế export dựa trên annotation. Spring đăng ký hạ tầng \`AnnotationMBeanExporter\`, phát hiện các bean có metadata phù hợp và export chúng vào MBeanServer.

Với \`WorkerControl\` có \`@ManagedResource\`, exporter tự động có thể tìm ra bean và đăng ký ObjectName được mô tả trong annotation:

\`\`\`text
com.example.app:type=WorkerControl,name=primary
\`\`\`

Các member JMX lấy từ \`@ManagedAttribute\` và \`@ManagedOperation\` sẽ được công bố theo metadata của Spring. Bean không được annotate hoặc không phù hợp điều kiện phát hiện sẽ không tự nhiên được xuất chỉ vì tồn tại trong context.

### 5.1. Khi nào nên dùng

- Số lượng tài nguyên quản trị vừa phải.
- Mỗi bean được quản trị có metadata annotation rõ ràng.
- ObjectName ổn định và đơn giản.
- Đội phát triển muốn khai báo contract JMX gần code.
- Không cần tùy biến sâu registration cho từng bean.

### 5.2. Những giới hạn cần hiểu

- Annotation nằm cùng class, nên thay đổi tên JMX có thể yêu cầu thay code hoặc cấu hình liên quan.
- Một class được tạo thành nhiều bean có thể chứa \`objectName\` tĩnh giống nhau, dẫn đến collision trong cùng \`MBeanServer\`.
- Cơ chế tự động không tự giải quyết ownership nếu application tạo thêm exporter thủ công.
- Việc “tự động” chỉ bắt đầu sau khi Spring context khởi tạo và hạ tầng export được cấu hình đúng.

## 6. AnnotationMBeanExporter: tự động cái gì?

Tên \`AnnotationMBeanExporter\` có thể khiến người học hiểu nhầm nó là một server độc lập. Trên thực tế, exporter này là **cấu hình export trong Spring**, sử dụng JMX infrastructure chuẩn.

Nó giảm số lượng cấu hình khi:

1. Phát hiện bean được annotate theo cơ chế export.
2. Dùng nguồn annotation metadata để tạo thông tin MBean.
3. Lấy hoặc suy ra ObjectName theo cấu hình và metadata.
4. Đăng ký MBean với MBeanServer.
5. Quản lý unregister theo lifecycle exporter/context.

Nó không bảo đảm:

- Mỗi annotated bean sẽ có tên không trùng trong mọi cách khởi tạo.
- Mọi phương thức public đều nên được export.
- Quyền truy cập JMX đã được bảo mật tự động.
- Giá trị writable attribute sẽ được lưu xuống cấu hình bền vững.
- Các exporter khác trong cùng JVM sẽ không xung đột.

Như vậy, “tự động” chủ yếu nói về **phát hiện và wiring**, không thay thế thiết kế hợp đồng quản trị.

## 7. So sánh trực tiếp

| Tiêu chí | MBeanExporter tường minh | Annotation-driven exporter |
|---|---|---|
| Ai chọn bean export? | Mapping/cấu hình do ứng dụng chỉ định | Cơ chế phát hiện annotation |
| Ai chọn ObjectName? | \`setBeans\`, naming strategy hoặc cấu hình cụ thể | Annotation/naming strategy và exporter config |
| Cần \`@ManagedResource\`? | Không bắt buộc nếu bean là MBean chuẩn; nếu dùng metadata assembler thì cần metadata phù hợp | Thông thường dùng \`@ManagedResource\` |
| Cần \`@ManagedAttribute\`? | Có nếu chọn annotation assembler; có thể dùng assembler khác | Dùng để công bố thuộc tính |
| Cấu hình từng bean | Nhiều hơn | Ít hơn |
| Tùy biến tên nhiều instance | Dễ chủ động theo mapping | Cần kế hoạch tránh tên tĩnh trùng |
| Kiểm soát bean được export | Rõ qua mapping | Theo annotation và auto-detection |
| Rủi ro đăng ký trùng | Có nếu mapping trùng hoặc exporter khác cùng đăng ký | Có nếu auto-detection và exporter khác cùng đăng ký |
| Phù hợp | Hệ thống cần kiểm soát cấu hình từng MBean | Ứng dụng quản trị theo annotation nhất quán |

Cả hai đường có thể cùng tồn tại trong một hệ thống **nếu phạm vi export không chồng lấn** và ownership được quy định chặt chẽ. Tuy nhiên, một ứng dụng nhỏ thường dễ bảo trì hơn khi chọn một cơ chế làm điểm quản lý chính.

## 8. Dùng MBeanServer nào?

JMX MBean được đăng ký vào một \`MBeanServer\` cụ thể. JVM có thể có platform server và những server khác do ứng dụng tạo.

Trong Spring, có thể cấu hình server bằng bean \`MBeanServer\` hoặc factory phù hợp:

\`\`\`java
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Bean
MBeanServerFactoryBean mbeanServerFactory() {
    MBeanServerFactoryBean factory =
        new MBeanServerFactoryBean();
    factory.setLocateExistingServerIfPossible(true);
    return factory;
}
\`\`\`

Đây là một hướng cấu hình infrastructure, cần kiểm tra thực tế server mà exporter chọn. Nếu client truy vấn platform server nhưng exporter đăng ký sang một server khác, sẽ thấy \`InstanceNotFoundException\` dù export thành công.

Với explicit exporter, có thể đặt server qua \`exporter.setServer(server)\`. Với annotation-driven, các thuộc tính và convention tương ứng của \`@EnableMBeanExport\` cần được dùng đúng phiên bản Spring.

**Không nên tạo MBeanServer mới tùy tiện** chỉ để tránh collision. Nếu nhiều exporter cùng có ý định quản trị một process, nên làm rõ phạm vi và tên MBean trước; các server riêng có thể làm monitoring khó khám phá.

## 9. Tên JMX và nguy cơ trùng ObjectName

Giả sử ta tạo hai bean \`WorkerControl\` cùng class trong một Spring context:

\`\`\`java
@Bean("primaryWorker")
WorkerControl primaryWorker() {
    return new WorkerControl();
}

@Bean("backupWorker")
WorkerControl backupWorker() {
    return new WorkerControl();
}
\`\`\`

Nếu annotation class chứa:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=primary"
)
\`\`\`

thì cả hai có thể muốn dùng cùng tên. Một \`MBeanServer\` không cho hai MBean cùng ObjectName tồn tại đồng thời. Khi đăng ký, có thể xuất hiện \`InstanceAlreadyExistsException\` hoặc exception được Spring bọc lại.

### 9.1. Giải pháp tường minh

Mapping từng bean với tên riêng:

\`\`\`java
exporter.setBeans(Map.of(
    "com.example.app:type=WorkerControl,name=primary",
    primaryWorker,
    "com.example.app:type=WorkerControl,name=backup",
    backupWorker
));
\`\`\`

Khi dùng metadata annotation có ObjectName tĩnh, hãy kiểm tra cách tên từ mapping và metadata được ưu tiên trong exporter đã cấu hình; tốt nhất là giữ một nguồn naming thống nhất.

### 9.2. Giải pháp dựa trên naming strategy

Sử dụng \`ObjectNamingStrategy\` để tạo ObjectName từ bean key hoặc ID runtime:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class WorkerNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String token = beanKey.replaceAll(
            "[^a-zA-Z0-9._-]", "_"
        );

        return new ObjectName(
            "com.example.app:type=WorkerControl,name=" + token
        );
    }
}
\`\`\`

Đây là ví dụ cơ chế, chưa đảm bảo tính duy nhất tuyệt đối vì hai bean key khác nhau có thể normalize thành cùng token. Trong production nên validate naming convention hoặc cấp một ID ổn định, bảo đảm không collision.

### 9.3. Nhiều replica ở các JVM khác nhau

Hai JVM có thể đăng ký cùng \`ObjectName\` vì chúng dùng \`MBeanServer\` riêng. Monitoring cần phân biệt target JVM/endpoint thay vì cố tạo tên global duy nhất bằng UUID ngẫu nhiên. Chỉ thêm \`instance\` vào ObjectName nếu hệ thống cần phân biệt nhiều MBean cùng vai trò trong cùng một server hoặc có yêu cầu vận hành cụ thể.

## 10. Không bật hai exporter lên cùng một bean

Một lỗi cấu hình phổ biến:

\`\`\`java
@Configuration
@EnableMBeanExport
class JmxConfig {

    @Bean
    WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    MBeanExporter extraExporter(WorkerControl workerControl) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

Nếu auto exporter phát hiện \`WorkerControl\` và exporter tường minh cũng đăng ký cùng ObjectName, có thể xảy ra double-registration. Nếu exporter có policy xử lý collision, một registration có thể bị bỏ qua hoặc thay thế, dẫn đến quyền sở hữu MBean không rõ.

Cách xử lý:

- Chọn một nơi sở hữu registration cho mỗi MBean.
- Khi cần kết hợp, đảm bảo hai exporter được cấu hình cho các bean không giao nhau.
- Kiểm tra bean được auto-detect bởi cơ chế nào.
- Không sử dụng \`IGNORE_EXISTING\` hay \`REPLACE_EXISTING\` như cách che việc export trùng mà chưa hiểu ownership.
- Kiểm tra khi shutdown exporter nào unregister ObjectName, tránh một context hủy MBean vẫn được context khác cần dùng.

Nên xử lý **nguyên nhân trùng cấu hình** trước khi thay chính sách xung đột.

## 11. Spring Boot và khác biệt với Spring Framework thuần

Trong ứng dụng Spring Framework thuần, \`@EnableMBeanExport\` là một lựa chọn bật annotation JMX export.

Trong Spring Boot, JMX auto-configuration có thể bị chi phối bởi cấu hình ứng dụng như \`spring.jmx.enabled\`, các annotation exporter và Actuator. Vì vậy, không nên mặc định Boot luôn bật export hoặc luôn tắt trong mọi cấu hình/phiên bản.

Cần kiểm tra:

1. Property JMX trong môi trường thực tế.
2. Những bean \`MBeanExporter\`/\`AnnotationMBeanExporter\` đã có trong context.
3. Có dùng \`@EnableMBeanExport\` thủ công hay không.
4. Có Actuator endpoint hoặc các MBean khác dùng cùng ObjectName/domain không.
5. MBeanServer mà exporter thực sự đăng ký.

Một ứng dụng vừa bật Boot JMX auto-configuration vừa tự tạo exporter chỉ nên làm vậy khi biết rõ phạm vi và cách tránh duplication. Những thuộc tính chi tiết của Boot có thể khác theo phiên bản; đọc reference tài liệu tương ứng với dependency đang chạy.

## 12. Kiểm tra kết quả bằng MBeanServer

Dù dùng explicit hay annotation-driven, kết quả cuối phải được xác nhận trong MBeanServer.

Ví dụ truy vấn:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not exported: " + name);
}

MBeanInfo info = server.getMBeanInfo(name);
System.out.println("Class: " + info.getClassName());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "%s: %s (R=%s W=%s)%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Kiểm tra \`isRegistered(name)\` trả đúng không, attribute/operation có xuất hiện hay không và kiểu dữ liệu có như hợp đồng mong muốn không.

### 12.1. Read/write/invoke để xác nhận

\`\`\`java
Object current = server.getAttribute(name, "MaxThreads");
System.out.println("Before: " + current);

server.setAttribute(
    name,
    new javax.management.Attribute("MaxThreads", 12)
);

Object updated = server.getAttribute(name, "MaxThreads");
System.out.println("After: " + updated);

server.invoke(
    name,
    "resetCounter",
    new Object[0],
    new String[0]
);
\`\`\`

Các lời gọi trên chỉ đúng nếu MBean đã đăng ký và contract JMX có các member tương ứng. Ghi attribute có thể thay đổi trạng thái ứng dụng thật; chỉ chạy với giá trị phù hợp môi trường thực hành.

### 12.2. Khi MBean không xuất hiện

Một quy trình kiểm tra:

\`\`\`text
Không thấy MBean
  |
  +-- Spring context đã khởi tạo thành công?
  |
  +-- Có exporter hoạt động?
  |      |
  |      +-- Explicit: setBeans đúng bean/ObjectName?
  |      +-- Automatic: @EnableMBeanExport có bật?
  |                      bean có @ManagedResource?
  |
  +-- Exporter đăng ký vào đúng MBeanServer?
  |
  +-- ObjectName có hợp lệ và không trùng?
  |
  +-- Bean có được tạo/khám phá trong context?
  |
  +-- Có exception khi export trong startup log?
\`\`\`

Không nên chỉ dựa vào việc có annotation trong source code để kết luận export thành công.

## 13. Lỗi thường gặp và cách nhận diện

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bean có \`@ManagedResource\` nhưng không có MBean | Chưa bật annotation export hoặc bean không nằm trong context | Bật đúng exporter và xác nhận bean lifecycle |
| MBean không có operation mong muốn | Thiếu \`@ManagedOperation\` hoặc metadata assembler khác | Kiểm tra annotation và \`MBeanInfo\` |
| \`InstanceAlreadyExistsException\` | ObjectName bị đăng ký trùng | Xác định mọi exporter và bean chủ sở hữu |
| Client báo \`InstanceNotFoundException\` | Sai tên hoặc sai MBeanServer | Truy vấn ObjectName và server thực tế |
| Cùng bean được export hai lần | Explicit exporter và auto exporter cùng detect | Tách phạm vi hoặc bỏ một đường export |
| Export chỉ thấy vài attribute | Assembler chọn ít member hơn kỳ vọng | Kiểm tra \`MetadataMBeanInfoAssembler\` và annotations |
| Bean có nhiều instance nhưng tên annotation tĩnh | ObjectName collision | Tên theo bean key/instance ID ổn định |
| MBean biến mất lúc context dừng | Exporter unregister theo lifecycle | Kiểm tra shutdown ownership |
| Thấy MBean nhưng quyền JMX không đúng | Connector/server chưa được bảo mật theo yêu cầu | Thiết kế authentication, authorization và network isolation |

Đừng suy diễn rằng mọi lỗi export là do annotation. Một MBean có thể không đăng ký được vì server, tên, loại MBean, lifecycle hoặc conflict giữa các configuration class.

## 14. Định hướng lựa chọn phương án

### Chọn cấu hình tường minh khi:

- Ứng dụng có nhiều loại MBean, bao gồm MBean đã tuân thủ JMX chuẩn và POJO cần assembler riêng.
- Cần kiểm soát ObjectName theo cấu hình deployment hoặc nhiều instance.
- Muốn mapping chỉ một số bean trong context thành MBean.
- Cần gắn notification listeners, chọn server riêng hoặc policy đăng ký một cách chủ động.
- Hệ thống cần khả năng kiểm kê và thay đổi quy tắc export ở một điểm cấu hình tập trung.

### Chọn annotation-driven khi:

- Ứng dụng dùng thống nhất \`@ManagedResource\` trên các thành phần quản trị.
- Mỗi bean có tên JMX rõ ràng, ít nguy cơ trùng.
- Muốn các phương thức quản trị nằm gần code với \`@ManagedAttribute\` và \`@ManagedOperation\`.
- Muốn giảm mapping boilerplate khi thêm các MBean cùng kiểu quy ước.
- Không cần tùy biến đặc thù cho mỗi bean.

Không có một phương án tốt hơn trong mọi trường hợp. Quyết định dựa vào tính ổn định của naming contract, số lượng MBean, cơ chế auto-configuration hiện có và yêu cầu kiểm soát đăng ký.

## 15. Bài thực hành phân biệt

### Bài 1: Annotation nhưng không bật exporter

\`\`\`java
@ManagedResource(objectName = "com.example.app:type=Cache,name=products")
class ProductCacheControl { /* ... */ }
\`\`\`

Nếu context không có cơ chế export thích hợp thì MBean này có tự xuất hiện không?

**Giải thích:** Không. Annotation là metadata; cần exporter chạy để đăng ký MBean.

### Bài 2: Một class, hai bean

Hai bean cùng class có cùng \`@ManagedResource(objectName = "...name=primary")\`. Cách nào kiểm soát tốt hơn?

**Giải thích:** Có thể dùng explicit mapping hoặc naming strategy để bảo đảm ObjectName khác nhau trong cùng server. Tự động phát hiện không giải quyết collision của tên tĩnh.

### Bài 3: Thêm một public method

Có method \`eraseAllData()\` public nhưng không annotate. Nếu dùng annotation metadata assembler và chỉ expose annotated methods, method này có xuất hiện thành operation không?

**Giải thích:** Không. Phải được đưa vào giao diện quản trị theo cấu hình assembler/annotation mới được export.

### Bài 4: Boot có exporter và người dùng bật @EnableMBeanExport

Nếu Boot đã cấu hình exporter và ứng dụng thêm \`@EnableMBeanExport\`, điều gì cần kiểm tra?

**Giải thích:** Kiểm tra số exporter, cơ chế chọn bean, trùng ObjectName và shutdown ownership; không mặc định cả hai cấu hình có thể chạy chồng mà không ảnh hưởng.

### Bài 5: Client không thấy bean dù exporter log thành công

\`MBeanServer\` nào cần kiểm tra?

**Giải thích:** Client phải kết nối đúng server/endpoint mà exporter đã đăng ký. Hai MBeanServer trong cùng JVM có registry độc lập.

### Bài 6: Khi nào dùng explicit exporter dù bean có annotation?

**Giải thích:** Khi cần chỉ định cụ thể bean, naming strategy, server, assembler, callback hoặc phạm vi export. Annotation có thể tiếp tục dùng để mô tả member quản trị.

## 16. Ghi nhớ

**Tường minh** nghĩa là ứng dụng trực tiếp quyết định danh sách bean, ObjectName và cấu hình exporter. **Tự động** nghĩa là Spring annotation infrastructure phát hiện bean và đăng ký JMX dựa trên metadata mà lập trình viên khai báo.

Cả hai đều hội tụ về cùng API JMX ở phía client. Cấu hình thành công cần ba điều kiện: **đúng bean được chọn**, **ObjectName không xung đột trong MBeanServer**, và **metadata JMX mô tả đúng các member được quản trị**. Khi chuyển từ phương án này sang phương án kia, hãy xem đó là thay đổi cấu hình runtime có thể ảnh hưởng script và monitoring, rồi kiểm tra kết quả thực bằng \`MBeanInfo\`.