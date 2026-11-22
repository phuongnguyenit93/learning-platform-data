# Autodetection và cách exporter chọn bean cần phơi bày

## Mục tiêu học tập

Sau bài này, bạn sẽ hiểu cách Spring Framework phát hiện các bean được đánh dấu metadata JMX khi dùng \`AnnotationMBeanExporter\`; phân biệt **phát hiện tự động (autodetection)** với **khai báo xuất thủ công**; biết ảnh hưởng của \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, tên \`ObjectName\`, phạm vi \`ApplicationContext\` và cấu hình exporter; đồng thời biết kiểm tra xem bean nào thực sự xuất hiện trong \`MBeanServer\` và vì sao một bean bị bỏ qua.

## 1. Bối cảnh: Spring bean không tự động là JMX MBean

JMX (Java Management Extensions) cho phép giám sát và điều khiển đối tượng Java tại runtime thông qua \`MBeanServer\`. Để một Spring bean xuất hiện dưới tên JMX như:

\`\`\`text
com.example.orders:type=OrderMetrics,name=primary
\`\`\`

cần có cơ chế đăng ký bean đó vào JMX registry. Spring Framework cung cấp \`MBeanExporter\` và \`AnnotationMBeanExporter\`. Cả hai đều liên quan tới việc quản lý các đối tượng đưa ra JMX, nhưng cách tìm metadata khác nhau.

- \`MBeanExporter\` có thể nhận danh sách các bean cụ thể qua \`setBeans(...)\`, được gắn với các \`ObjectName\` xác định.
- \`AnnotationMBeanExporter\` hỗ trợ xử lý các annotation \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, và có thể tự tìm những bean mang metadata phù hợp trong Spring container.

**Autodetection không có nghĩa mọi Spring bean đều tự được công bố.** Với chiến lược annotation, một bean phải đáp ứng tiêu chí phát hiện mới trở thành ứng viên JMX. Sau đó exporter còn phải đặt được tên, tạo metadata hợp lệ và đăng ký thành công vào server.

Một instance đã có trong \`ApplicationContext\` nhưng không được exporter chọn có thể vẫn hoạt động bình thường trong ứng dụng, chỉ không có entry trong JMX registry.

## 2. AnnotationMBeanExporter làm gì?

\`org.springframework.jmx.export.annotation.AnnotationMBeanExporter\` là exporter thuận tiện cho việc sử dụng Spring JMX annotations. Về mặt ý tưởng, nó kết hợp:

1. Phần export của \`MBeanExporter\`: đưa object vào \`MBeanServer\`.
2. Bộ đọc metadata annotation như \`AnnotationJmxAttributeSource\`.
3. Cơ chế dựng thông tin \`ModelMBean\` từ annotation.
4. Cơ chế chọn \`ObjectName\` theo metadata/naming strategy.
5. Cơ chế autodetection để tìm các Spring bean được đánh dấu \`@ManagedResource\`.

Trong một ứng dụng, bạn có thể đăng ký annotation exporter bằng cấu hình phù hợp; Spring cũng cung cấp \`@EnableMBeanExport\` và cấu hình XML \`<context:mbean-export/>\` để kích hoạt việc xuất MBean dựa trên annotation.

Mô hình khái quát:

\`\`\`text
ApplicationContext
   |
   +-- orderService (không có @ManagedResource)
   +-- orderMetrics (@ManagedResource)
   +-- cacheAdmin   (@ManagedResource)
   +-- internalHelper
   |
   v
AnnotationMBeanExporter
   |
   +-- quét ứng viên Spring bean theo autodetection
   +-- đọc @ManagedResource
   +-- đọc @ManagedAttribute / @ManagedOperation
   +-- xác định ObjectName
   +-- tạo metadata quản lý phù hợp
   |
   v
MBeanServer registry
   |
   +-- com.example.orders:type=OrderMetrics,name=primary
   +-- com.example.cache:type=CacheAdmin,name=primary
   |
   v
JConsole / VisualVM / JMX client
\`\`\`

Các bean không được chọn vẫn tồn tại trong Spring container, nhưng không xuất hiện dưới dạng entry JMX do exporter này đăng ký.

## 3. Điều kiện quan trọng nhất: @ManagedResource

Trong mô hình Spring annotation JMX, \`@ManagedResource\` thường được đặt ở **lớp** cần xuất:

\`\`\`java
package com.example.orders;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.orders:type=OrderMetrics,name=primary",
        description = "Runtime counters for order processing")
public class OrderMetrics {
    private final AtomicLong completed = new AtomicLong();

    public void recordCompleted() {
        completed.incrementAndGet();
    }

    @ManagedAttribute(description = "Completed order count")
    public long getCompletedCount() {
        return completed.get();
    }

    @ManagedOperation(description = "Reset counters")
    public void resetStatistics() {
        completed.set(0);
    }
}
\`\`\`

Ở đây, \`@ManagedResource\` xác định bean là ứng viên có metadata quản lý ở cấp lớp. \`@ManagedAttribute\` và \`@ManagedOperation\` xác định những method được công bố thành attribute/operation. Method \`recordCompleted()\` vẫn \`public\` nhưng không tự động được xuất khi dùng annotation metadata assembler tương ứng.

Chỉ gắn \`@ManagedOperation\` lên một method của class không có metadata cấp lớp chưa đủ để bảo đảm class được cơ chế autodetection của exporter tìm thấy. Cần hiểu rõ quy tắc lựa chọn ứng viên và cách exporter được cấu hình.

## 4. Kích hoạt autodetection bằng @EnableMBeanExport

Đây là cách phổ biến trong ứng dụng Spring Framework dùng Java configuration:

\`\`\`java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {

    @Bean
    public OrderMetrics orderMetrics() {
        return new OrderMetrics();
    }

    @Bean
    public OrderService orderService(OrderMetrics metrics) {
        return new OrderService(metrics);
    }
}
\`\`\`

Ví dụ service sử dụng cùng \`OrderMetrics\` bean:

\`\`\`java
package com.example.orders;

public class OrderService {
    private final OrderMetrics metrics;

    public OrderService(OrderMetrics metrics) {
        this.metrics = metrics;
    }

    public void completeOrder() {
        // Business processing would go here.
        metrics.recordCompleted();
    }
}
\`\`\`

\`@EnableMBeanExport\` kích hoạt support xuất bean được đánh dấu các Spring JMX annotation. Tùy phiên bản Spring và cách cấu hình, exporter có thể tìm \`MBeanServer\` sẵn có hoặc được cung cấp tường minh. Trong ứng dụng có nhiều server, nên chọn rõ server phù hợp để tránh việc công cụ quản trị kết nối đến một server khác.

Ví dụ thiết lập nền tảng server và cấu hình exporter rõ hơn:

\`\`\`java
package com.example.orders;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class MonitoringJmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public OrderMetrics orderMetrics() {
        return new OrderMetrics();
    }
}
\`\`\`

Giá trị \`server = "platformMBeanServer"\` tham chiếu tên bean của \`MBeanServer\` mà annotation support sẽ dùng. Nếu ứng dụng đã có \`MBeanServer\` bean từ cấu hình khác, có thể dùng bean đó thay vì tạo trùng.

Điểm quyết định là \`OrderMetrics\` có \`@ManagedResource\` và được đưa vào \`ApplicationContext\`; \`OrderService\` không mang annotation đó, nên không được autodetection xuất như một MBean riêng chỉ vì nó dùng \`OrderMetrics\`.

## 5. Autodetection diễn ra như thế nào?

Có thể hình dung pipeline khi exporter được khởi tạo:

1. Spring tạo và cấu hình các bean trong \`ApplicationContext\`.
2. Exporter nhận quyền truy cập tới bean factory/context để tìm ứng viên.
3. Autodetection xem xét các bean phù hợp với chiến lược phát hiện đang bật.
4. Với annotation-driven export, metadata \`@ManagedResource\` là dấu hiệu quan trọng để chọn bean.
5. Exporter xác định \`ObjectName\` cho từng ứng viên qua \`objectName\` trên annotation hoặc naming strategy phù hợp.
6. Assembler đọc \`@ManagedAttribute\`, \`@ManagedOperation\` và metadata liên quan để tạo giao diện quản lý.
7. Exporter đăng ký các MBean vào \`MBeanServer\` trong lifecycle khởi tạo.
8. JMX client truy vấn registry theo \`ObjectName\`.

Pipeline trên là mô hình logic. Thứ tự callback nội bộ, cách xử lý các bean lazy/proxy/FactoryBean và điểm xảy ra lỗi phụ thuộc version Spring, cấu hình exporter và bean factory thực tế.

Nếu bean được đăng ký sau khi quá trình autodetection hoàn tất, không nên mặc nhiên cho rằng exporter sẽ tự động phát hiện lại. Cần dùng API đăng ký thủ công phù hợp, cấu hình lifecycle hoặc khởi tạo exporter đúng thời điểm.

## 6. Quy tắc chọn bean theo chiến lược autodetect

\`MBeanExporter\` hỗ trợ chiến lược tự phát hiện qua các hằng như \`AUTODETECT_NONE\`, \`AUTODETECT_MBEAN\`, \`AUTODETECT_ASSEMBLER\` và \`AUTODETECT_ALL\`. Ý nghĩa chung:

| Chiến lược | Đối tượng được xét | Mục đích |
| --- | --- | --- |
| \`AUTODETECT_NONE\` | Không tự động phát hiện bean | Chỉ xuất bean được chỉ định trực tiếp |
| \`AUTODETECT_MBEAN\` | Bean đáp ứng giao diện MBean chuẩn của JMX | Phát hiện Standard MBean, MXBean hoặc MBean phù hợp |
| \`AUTODETECT_ASSEMBLER\` | Bean mà assembler có thể cung cấp metadata quản lý | Phát hiện theo metadata, ví dụ annotation |
| \`AUTODETECT_ALL\` | Kết hợp các cơ chế trên | Phát hiện cả MBean chuẩn và bean do assembler nhận diện |

Hằng và API cụ thể cần dùng đúng phiên bản Spring hiện tại; các cấu hình được dựng tự động có thể lựa chọn chiến lược phù hợp thay vì yêu cầu gọi \`setAutodetectMode\` thủ công.

Khác biệt cần nhớ:

- **MBean convention**: ví dụ \`WorkerPool implements WorkerPoolMBean\`; JMX đọc interface chuẩn.
- **Assembler-based**: ví dụ \`@ManagedResource\` trên \`WorkerPoolAdmin\`; Spring đọc các annotation để dựng metadata.
- **Explicit mapping**: ví dụ \`setBeans(Map.of("domain:type=...", instance))\`; bean được chọn vì người cấu hình nêu rõ, kể cả khi không nằm trong danh sách autodetection.

Đừng kết luận rằng \`@ManagedResource\` luôn làm bean xuất hiện nếu exporter được cấu hình \`AUTODETECT_NONE\` và không có mapping tường minh. Cũng đừng kết luận rằng tất cả bean có tên kết thúc \`MBean\` chắc chắn được xuất: class/interface phải tuân thủ quy tắc MBean hợp lệ và nằm trong phạm vi quét của exporter.

## 7. Ví dụ so sánh các loại bean

Giả sử context có các bean sau:

\`\`\`java
@Bean
public OrderMetrics orderMetrics() {
    return new OrderMetrics(); // Class có @ManagedResource
}

@Bean
public PaymentService paymentService() {
    return new PaymentService(); // Không có metadata JMX
}

@Bean
public ThreadPoolMonitor threadPoolMonitor() {
    return new ThreadPoolMonitor(); // implements ThreadPoolMonitorMBean
}
\`\`\`

Nếu exporter được thiết lập để autodetect theo annotation assembler, \`OrderMetrics\` là ứng viên rõ ràng; \`PaymentService\` không được chọn; \`ThreadPoolMonitor\` có thể không được chọn nếu chính sách chỉ quét metadata annotation.

Nếu exporter hỗ trợ cả autodetect MBean convention và assembler, cả \`OrderMetrics\` và \`ThreadPoolMonitor\` có thể được đăng ký. Khi muốn biết chính xác, cần xem mode cấu hình và metadata thực tế, không dựa trên tên class hoặc việc bean được tiêm dependency thành công.

Đối với service nghiệp vụ không muốn lộ qua quản trị, cách dễ kiểm soát nhất là tách **business service** khỏi **management adapter**: tạo một class được đánh dấu \`@ManagedResource\`, chỉ công bố các metric/operation dự định cho vận hành, và inject service vào adapter nếu cần.

## 8. Cách exporter xác định ObjectName

Sau khi chọn bean, exporter phải gán một \`ObjectName\` duy nhất. Ví dụ:

\`\`\`java
@ManagedResource(
        objectName = "com.example.orders:type=OrderMetrics,name=primary")
public class OrderMetrics {
    // ...
}
\`\`\`

Khi dùng annotation naming strategy được hỗ trợ, \`objectName\` trên \`@ManagedResource\` có thể cung cấp tên JMX cụ thể. Một số cấu hình naming strategy hỗ trợ cơ chế suy ra tên nếu annotation không có \`objectName\`; chi tiết phải kiểm tra cấu hình Spring đang chạy.

Phân biệt:

| Tên | Ví dụ | Phạm vi |
| --- | --- | --- |
| Tên Spring bean | \`orderMetrics\` | Truy xuất object trong bean factory |
| Tên lớp | \`OrderMetrics\` | Java type |
| Metadata annotation | \`@ManagedResource(objectName=...)\` | Gợi ý/khai báo tên JMX cho exporter phù hợp |
| JMX \`ObjectName\` | \`com.example.orders:type=OrderMetrics,name=primary\` | Định danh MBean trong registry |

Nếu hai bean cùng được gán một \`ObjectName\`, mặc định thường xảy ra lỗi đăng ký trùng, trừ khi exporter có chính sách xử lý xung đột khác được cấu hình. Không nên dùng chính sách replace/ignore để che lỗi naming không chủ ý.

Cần đặc biệt chú ý khi nhiều application contexts cùng chia sẻ platform \`MBeanServer\`, hoặc khi nhiều instance Spring Boot/app context dùng domain và name giống nhau trong cùng JVM.

## 9. @ManagedAttribute, @ManagedOperation và khả năng phơi bày

\`@ManagedResource\` giúp chọn managed object, còn **method nào được công bố** được quyết định bởi metadata trên method và assembler tương ứng.

\`\`\`java
package com.example.cache;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.cache:type=CacheAdmin,name=primary")
public class CacheAdmin {
    private volatile boolean enabled = true;
    private int clearedEntries;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute
    public int getClearedEntries() {
        return clearedEntries;
    }

    @ManagedOperation(description = "Clear cached entries")
    public void clearCache() {
        if (!enabled) {
            throw new IllegalStateException("Cache maintenance disabled");
        }

        // Dọn cache thực tế tại đây.
        clearedEntries++;
    }

    public void internalRefresh() {
        // Method công khai nhưng không được đánh dấu để xuất qua JMX.
    }
}
\`\`\`

Ở mô hình annotation này, bạn dự kiến thấy attribute \`Enabled\` (đọc/ghi), \`ClearedEntries\` (chỉ đọc) và operation \`clearCache\`. Method \`internalRefresh()\` không tự động xuất bởi annotation assembler khi không có metadata quản lý tương ứng.

Đây là ranh giới rất quan trọng: **autodetection chọn bean**, còn **metadata assembler chọn các phần tử quản lý trong bean**. Hai quyết định không giống nhau. Cần kiểm tra cả registry và \`MBeanInfo\` để bảo đảm đúng phạm vi phơi bày.

## 10. Đăng ký annotation exporter thủ công

Bên cạnh \`@EnableMBeanExport\`, bạn có thể khai báo \`AnnotationMBeanExporter\` trực tiếp nếu muốn kiểm soát explicit các tham số. Ví dụ:

\`\`\`java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class ManualAnnotationJmxConfig {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer platformMBeanServer) {
        AnnotationMBeanExporter exporter = new AnnotationMBeanExporter();
        exporter.setServer(platformMBeanServer);
        return exporter;
    }

    @Bean
    public OrderMetrics orderMetrics() {
        return new OrderMetrics();
    }
}
\`\`\`

Đây là một ví dụ cấu hình tường minh của Spring Framework thuần. Nếu ứng dụng đã dùng \`@EnableMBeanExport\` hoặc cơ chế auto-configuration tạo exporter, không thêm exporter thứ hai chỉ để “chắc chắn”: điều đó có thể khiến cùng bean được đăng ký hai lần dưới một \`ObjectName\`.

Với annotation exporter, metadata trên class/method được xử lý theo hỗ trợ mặc định của \`AnnotationMBeanExporter\`. Nếu cần naming strategy riêng, chế độ autodetect khác hoặc kiểm soát registration policy, có thể cấu hình exporter theo API Spring đang dùng. Không suy luận một setter có tồn tại ở mọi phiên bản chỉ từ ví dụ chung; xác nhận theo API của phiên bản đã chọn khi triển khai dự án.

## 11. @EnableMBeanExport và Spring Boot: phạm vi cấu hình

\`@EnableMBeanExport\` là tiện ích kích hoạt hỗ trợ xuất MBean qua annotation trong Spring Framework. Trong Spring Boot, cơ chế JMX và trạng thái auto-export có thể được điều khiển bởi cấu hình, ví dụ thuộc tính \`spring.jmx.enabled\` theo phiên bản Boot.

Các hệ quả cần lưu ý:

- Có thể đã tồn tại \`MBeanExporter\` được Boot cấu hình trước khi bạn khai báo exporter thủ công.
- Spring Boot Actuator có thể cung cấp các management endpoint/MBean riêng tùy dependency và cấu hình; không đồng nghĩa mọi bean nghiệp vụ được export.
- Nhiều exporter hoặc nhiều context có thể đăng ký trùng \`ObjectName\`.
- Một bean có annotation vẫn có thể không xuất hiện nếu cơ chế export chưa được bật trong context phù hợp.

Khi bài học tập trung Spring Framework, hãy xác định rõ cách exporter được tạo trước. Trong một ứng dụng Boot cụ thể, kiểm tra version, \`spring.jmx.enabled\`, các bean exporter trong context và kết quả JMX thực tế.

## 12. Kiểm tra bean được xuất bằng JConsole và MBeanServer

Cách nhanh nhất là dùng JConsole:

1. Chạy ứng dụng và xác nhận \`ApplicationContext\` đã khởi tạo.
2. Mở \`jconsole\`, chọn đúng JVM/PID.
3. Mở tab **MBeans**, tìm domain và \`ObjectName\` từ \`@ManagedResource\`.
4. Mở MBean đó, xem \`Attributes\` và \`Operations\`.
5. Đối chiếu danh sách method được xuất với các annotation trên class.
6. Kiểm tra một bean **không có metadata quản lý** không bị lộ ngoài ý muốn.

Nếu muốn kiểm tra tự động, có thể dùng API JMX:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
        "com.example.orders:type=OrderMetrics,name=primary");

boolean exists = server.isRegistered(expected);
System.out.println("Registered: " + exists);

Set<ObjectName> registered = server.queryNames(
        new ObjectName("com.example.orders:*"), null);

for (ObjectName name : registered) {
    System.out.println(name.getCanonicalName());
}

if (exists) {
    MBeanInfo info = server.getMBeanInfo(expected);

    for (var attr : info.getAttributes()) {
        System.out.println("Attribute: " + attr.getName());
    }

    for (var operation : info.getOperations()) {
        System.out.println("Operation: " + operation.getName());
    }
}
\`\`\`

Lưu ý: \`ManagementFactory.getPlatformMBeanServer()\` kiểm tra server **trong JVM thực thi đoạn code**. Nếu đoạn mã chạy từ tiến trình khác, nó sẽ đọc một registry khác. Client bên ngoài cần kết nối tới đúng JVM qua JMX connector hoặc công cụ như JConsole.

Kết quả \`isRegistered(expected)=true\` xác nhận tên đã có trong registry, nhưng để chắc chắn exporter không phơi bày method ngoài dự kiến, cần đọc \`MBeanInfo\` và so sánh attributes/operations.

## 13. Các tình huống một bean không được autodetect

### 13.1. Class không có @ManagedResource

\`@ManagedOperation\` trên một method riêng lẻ có thể chưa đủ để Spring annotation exporter chọn toàn bộ bean. Với annotation autodetection, đánh dấu class bằng \`@ManagedResource\` đúng cách.

### 13.2. Bean không có trong ApplicationContext được exporter quét

Nếu object được tạo bằng \`new OrderMetrics()\` ngoài Spring bean factory, exporter quét Spring beans sẽ không biết đến object đó. Tương tự, nếu object được tạo trong context khác không thuộc phạm vi exporter, nó có thể không được phát hiện.

### 13.3. Exporter không được kích hoạt hoặc bị vô hiệu hóa

Một project có đầy đủ annotation nhưng không có \`@EnableMBeanExport\`, exporter phù hợp hoặc cơ chế Boot tương đương sẽ không tự xuất MBean chỉ nhờ annotation tồn tại trên class.

### 13.4. Autodetect mode không phù hợp

Nếu cấu hình là \`AUTODETECT_NONE\`, exporter không quét tự động. Nếu chỉ chọn \`AUTODETECT_MBEAN\`, một bean thuần annotation chưa chắc được chọn; cần mode assembler hoặc cấu hình annotation exporter tương ứng.

### 13.5. Proxy, FactoryBean hoặc metadata trên loại khác

Spring AOP proxy, \`FactoryBean\`, scoped proxy và class generated có thể khiến lớp thực tế mà exporter introspect khác lớp chứa annotation. Khi gặp sự cố, xác minh runtime bean type, vị trí annotation trên type/interface và cách exporter/assembler đọc metadata theo version Spring đang dùng.

### 13.6. ObjectName không hợp lệ hoặc bị trùng

Exporter có thể đã phát hiện bean nhưng đăng ký thất bại do \`ObjectName\` sai cú pháp hoặc tồn tại trước đó. Khi đó bean không xuất hiện trong registry theo cách dự kiến, và log startup thường chứa nguyên nhân.

### 13.7. Sai MBeanServer hoặc sai JVM

Một ứng dụng có thể có nhiều server hoặc nhiều instance; JConsole nhìn vào sai JVM sẽ khiến bạn cho rằng autodetection thất bại. Đối chiếu PID, server object và full \`ObjectName\` trước khi thay đổi cấu hình.

## 14. Autodetection và nguyên tắc hạn chế phơi bày

Vì JMX cho phép gọi operation có khả năng thay đổi trạng thái ứng dụng, việc **chọn bean để export** là một quyết định vận hành quan trọng.

Hướng tiếp cận thường dễ kiểm soát:

1. Tách component quản trị khỏi service nghiệp vụ nhạy cảm khi cần.
2. Chỉ đánh dấu \`@ManagedResource\` trên các adapter quản trị có mục đích rõ.
3. Chỉ đánh dấu \`@ManagedAttribute\` hoặc \`@ManagedOperation\` trên method thực sự cần công bố.
4. Sử dụng naming convention nhất quán cho \`ObjectName\` để biết module và instance.
5. Kiểm tra metadata và registry sau khi khởi tạo; đừng chỉ tin rằng annotation đã đủ.
6. Bảo vệ JMX endpoint remote bằng xác thực, kiểm soát quyền truy cập và giới hạn network.
7. Với operation có side effect, thực thi kiểm tra trạng thái/điều kiện nghiệp vụ trong implementation; annotation không tự tạo lớp phân quyền cho operation.

Giả sử \`OrderService\` có method \`cancelAllOrders()\`; không nên đưa toàn bộ \`OrderService\` ra JMX vì tiện lợi. Thay vào đó, tạo \`OrderAdmin\` có đúng các method vận hành đã được kiểm soát và tách rõ quyền tác động.

## 15. Bài tập thực hành

**Bài 1 — Phát hiện qua annotation**

Tạo ba bean: \`OrderMetrics\` có \`@ManagedResource\`, \`PaymentService\` không có annotation và \`CacheAdmin\` có \`@ManagedResource\`. Bật \`@EnableMBeanExport\`. Dùng \`MBeanServer.queryNames\` kiểm tra chỉ các bean có metadata quản lý phù hợp được export theo chế độ annotation.

**Bài 2 — Method nào được công bố?**

Trong \`CacheAdmin\`, thêm \`getCacheSize()\` có \`@ManagedAttribute\`, \`clearCache()\` có \`@ManagedOperation\` và \`internalRebuild()\` không có annotation. Kiểm tra \`MBeanInfo\` để xác định method nào được xuất ra JMX.

**Bài 3 — Autodetect mode**

Với cấu hình \`MBeanExporter\` tường minh, lần lượt thử chiến lược \`AUTODETECT_NONE\` và một chiến lược phát hiện theo assembler, sau đó so sánh \`ObjectName\` đã đăng ký. Lưu ý chọn API thực tế của phiên bản Spring dùng trong dự án.

**Bài 4 — Trùng tên**

Tạo hai bean mang \`@ManagedResource(objectName="com.example:type=Duplicate")\`. Quan sát lỗi startup/exporter và thay thành hai \`ObjectName\` khác nhau. Giải thích tại sao trong cùng \`MBeanServer\` không thể có hai MBean cùng full name.

**Bài 5 — Bean nằm ngoài phạm vi quét**

Tạo một instance \`OrderMetrics\` bằng \`new\` nhưng không đăng ký nó làm Spring bean. Xác minh rằng annotation exporter không tự tìm thấy instance này. Sau đó khai báo \`@Bean\` và kiểm tra lại registry.

## Kết luận

\`AnnotationMBeanExporter\` giúp Spring Framework tự tìm những managed bean có metadata phù hợp, nhất là \`@ManagedResource\`, rồi xây dựng thông tin attribute/operation từ các annotation liên quan và đăng ký chúng vào \`MBeanServer\`. **Autodetection chọn object**, **metadata assembler chọn API quản lý được công bố**, còn **ObjectName xác định danh tính trong JMX registry**. Hiểu ba ranh giới này giúp tránh bỏ sót MBean, đăng ký trùng tên hoặc vô tình phơi bày các method nội bộ của ứng dụng.
