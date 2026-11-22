# Chẩn đoán MBean biến mất sau khi bật AOP hoặc transaction trong Spring Framework JMX

## 1. Tình huống và mục tiêu

Một ứng dụng Spring Framework có bean quản trị xuất hiện bình thường trên JConsole. Sau khi thêm \`@Transactional\`, \`@Async\`, \`@Cacheable\` hoặc advice AOP, MBean biến mất, đổi tên, hoặc chỉ còn một số attributes/operations. Business method vẫn chạy, nhưng công cụ JMX không còn thấy resource dưới ObjectName quen thuộc.

Ví dụ:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.orders:type=OrderService,name=Primary")
public class OrderService {

    @ManagedAttribute
    public int getPendingOrders() {
        return 7;
    }

    @ManagedOperation
    public void refreshCache() {
        // Reload a cache used by the service.
    }

    @Transactional
    public void placeOrder() {
        // Business transaction.
    }
}
\`\`\`

Trước khi bật transaction, exporter có thể phát hiện bean và expose getter/operation. Sau khi thêm AOP, Spring có thể đưa **proxy** vào ApplicationContext. Nếu exporter/metadata assembler chỉ quan sát một interface hoặc type khác với type ban đầu, annotation và các method quản trị có thể không còn được phát hiện đúng. Cũng có trường hợp MBean vẫn tồn tại nhưng **ObjectName khác**, hoặc exporter đã đăng ký vào một MBeanServer không phải nơi client đang quan sát.

Bài học này giúp bạn:

1. Phân biệt MBean thật sự không được đăng ký với trường hợp client tìm nhầm tên/server.
2. Hiểu JDK dynamic proxy và class-based proxy (CGLIB) ảnh hưởng đến type và method visibility như thế nào.
3. Giải thích tương tác giữa autodetection, \`AnnotationMBeanExporter\`, \`MBeanExporter\`, metadata assembler và Spring AOP.
4. Kiểm tra target class, proxy interfaces, annotations và \`MBeanInfo\` của MBean đã đăng ký.
5. Thiết kế các bước sửa cấu hình ít rủi ro, không vội tắt transaction hoặc AOP.
6. Viết integration test bảo vệ hợp đồng JMX trước và sau khi bật proxy.

## 2. Không bắt đầu bằng giả định “MBean đã biến mất”

Khi JConsole không hiển thị một MBean dưới tên cũ, có nhiều khả năng:

\`\`\`text
Không thấy MBean?
       |
       +-- Exporter chưa khởi động / bean chưa được chọn
       |
       +-- Exporter đăng ký lỗi, collision ObjectName
       |
       +-- Exporter dùng MBeanServer khác
       |
       +-- ObjectName thay đổi do naming strategy/proxy type
       |
       +-- MBean tồn tại nhưng interface quản trị thay đổi
       |
       +-- JConsole/JMX client kết nối JVM khác hoặc cache giao diện cũ
       |
       +-- Spring context đã đóng, exporter unregister
\`\`\`

Điểm đầu tiên phải xác định là MBean có tồn tại trong server **thực sự được exporter sử dụng** hay không.

Ví dụ trong cùng JVM:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=OrderService,name=Primary");

System.out.println(server.isRegistered(name));
\`\`\`

Đoạn này chỉ có ý nghĩa nếu exporter dùng platform MBeanServer. Với custom \`MBeanServer\`, cần lấy chính server được inject vào exporter.

Nếu \`isRegistered(name) == false\`, chưa đủ để kết luận MBean biến mất: tên có thể được sinh khác sau khi proxy được áp dụng.

## 3. Chuỗi hoạt động của Spring JMX autodetection

Spring JMX có thể xuất các bean theo metadata hoặc quy tắc autodetection. Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| \`MBeanExporter\` | Đăng ký và quản lý vòng đời MBean |
| \`AnnotationMBeanExporter\` | Hỗ trợ annotation-based exporting và autodetection |
| \`@ManagedResource\` | Mô tả resource được quản trị |
| \`@ManagedAttribute\` | Mô tả getter/setter quản trị |
| \`@ManagedOperation\` | Mô tả operation quản trị |
| \`MBeanInfoAssembler\` | Tạo metadata cho interface được expose |
| \`ObjectNamingStrategy\` | Chọn ObjectName |
| Spring AOP proxy | Đối tượng được client của Spring container nhìn thấy sau khi áp dụng advice |

Có thể hình dung:

\`\`\`text
Bean definition
      |
      v
Spring instantiates target
      |
      v
BeanPostProcessors may create proxy
      |
      v
Bean retrieved from container
      |
      v
JMX autodetection / exporter
      |
      +--> inspect target/proxy/metadata
      |
      +--> choose ObjectName
      |
      +--> build MBean interface
      |
      v
MBeanServer.registerMBean(...)
\`\`\`

Một thay đổi AOP có thể ảnh hưởng **kiểu bean được quan sát tại thời điểm exporter chạy** hoặc metadata assembler. Vì vậy việc Spring vẫn tạo được bean không chứng minh exporter có thể expose MBean theo cấu hình hiện tại.

### 3.1. Autodetection không có nghĩa mọi bean đều được export

Exporter thường chỉ nhận những object phù hợp quy tắc và metadata mà nó dùng. Một class có \`@ManagedResource\` không tự tạo MBean nếu chưa có exporter phù hợp. Nếu cấu hình \`@EnableMBeanExport\` ở ApplicationContext khác hoặc bị loại khỏi context hiện tại, exporter có thể không thấy bean, bất kể AOP.

### 3.2. Các điều kiện khác nhau dẫn đến triệu chứng giống nhau

- Không có MBean trong registry: lỗi chọn bean hoặc đăng ký.
- Có ObjectName nhưng attributes thiếu: lỗi metadata/exposure.
- Có attributes nhưng invocation thất bại: lỗi proxy method dispatch hoặc target invocation.
- Có tên nhưng JConsole không hiển thị: lỗi kết nối/caching hoặc UI.
- Có MBean trong server riêng nhưng không có trong platform server: lỗi chọn server, không phải AOP.

## 4. Proxy JDK và CGLIB: điều gì thay đổi?

### 4.1. JDK dynamic proxy

Khi bean có interface và cấu hình proxy theo interface, Spring có thể tạo JDK dynamic proxy. Khi đó:

\`\`\`text
OrderServiceImpl implements OrderServiceApi
             |
             v
     JDK dynamic proxy
     implements OrderServiceApi
\`\`\`

Bean được lấy từ context có thể là proxy class chỉ expose các methods trên interface. Annotation \`@ManagedOperation\` đặt trên method chỉ có ở implementation có thể không được một introspection path nhìn thấy như mong đợi.

Ví dụ:

\`\`\`java
public interface OrderServiceApi {
    void placeOrder();
}

@ManagedResource(
    objectName = "com.example.orders:type=OrderService,name=Primary")
public class OrderServiceImpl implements OrderServiceApi {

    @Override
    @Transactional
    public void placeOrder() {}

    @ManagedAttribute
    public int getPendingOrders() {
        return 7;
    }
}
\`\`\`

Nếu \`getPendingOrders\` không nằm trên interface, một JDK proxy không trực tiếp cung cấp method ấy theo interface công khai. Spring có cơ chế xử lý metadata/target class trong một số đường export, nhưng **không nên mặc định mọi exporter/assembler tùy chỉnh sẽ xử lý chính xác**. Cần quan sát type, metadata và MBeanInfo thực tế.

### 4.2. Class-based proxy (CGLIB)

Class-based proxy tạo subclass của target class. Phần lớn public methods có thể vẫn hiện diện trên proxy class, nhưng các giới hạn Java vẫn áp dụng:

- Final class không thể được subclass để proxy kiểu này.
- Final method không thể được override/advised.
- Private method không được proxy thông qua override.
- Self-invocation thường không đi qua proxy khi dùng Spring proxy-based AOP.

Class-based proxy có thể giúp một số trường hợp cần expose method không có trên interface, nhưng không phải cách sửa mặc định cho mọi lỗi JMX. Nó thay đổi semantics AOP và có thể không phù hợp với class hiện tại.

### 4.3. Transaction có nhất thiết gây proxy không?

Với Spring proxy-based transaction management, \`@Transactional\` thường làm method phù hợp được gọi qua proxy để áp dụng transaction advice. Tuy nhiên phương thức thực tế được proxy và cơ chế proxy phụ thuộc cấu hình transaction, interface, visibility và phiên bản Spring.

**Không nên tắt transaction chỉ để MBean xuất hiện.** Đầu tiên xác định proxy và introspection path thực tế. Nếu cần sửa, ưu tiên cấu hình exporter/interface/naming phù hợp thay vì bỏ một cơ chế nghiệp vụ quan trọng.

## 5. Bước chẩn đoán 1: kiểm tra bean và proxy thực tế

Trong ApplicationContext đang chạy:

\`\`\`java
import org.springframework.aop.support.AopUtils;
import org.springframework.aop.framework.Advised;
import org.springframework.context.ApplicationContext;

Object bean = context.getBean("orderService");

System.out.println("Bean class: " + bean.getClass().getName());
System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("Target class: " +
    AopUtils.getTargetClass(bean).getName());
\`\`\`

Để sử dụng \`AopUtils\`, project cần module Spring AOP phù hợp. Kết quả dự kiến sau khi AOP bật có thể là \`isAopProxy=true\`. Tên class proxy có thể là class JDK proxy hoặc subclass có hậu tố được framework sinh ra; không xây dựng logic sản xuất dựa trên chuỗi tên class sinh tự động.

### 5.1. Kiểm tra proxy interfaces

\`\`\`java
for (Class<?> type : bean.getClass().getInterfaces()) {
    System.out.println(type.getName());
}
\`\`\`

Nếu dùng JDK proxy, xác định interface nào thực sự được expose, đặc biệt các getter/operation quản trị. Không nên chỉ nhìn implementation source rồi giả định proxy có cùng public API.

### 5.2. Kiểm tra target metadata một cách có kiểm soát

\`\`\`java
Class<?> targetType = AopUtils.getTargetClass(bean);
ManagedResource annotation =
    org.springframework.core.annotation.AnnotationUtils
        .findAnnotation(
            targetType,
            org.springframework.jmx.export.annotation.ManagedResource.class);

System.out.println(annotation != null);
\`\`\`

Đoạn này giúp biết target type có metadata \`@ManagedResource\` hay không. Nó **không chứng minh exporter đã nhận metadata**, vì exporter có thể dùng một metadata assembler khác hoặc cấu hình autodetection khác.

Đừng unwrap proxy để gọi target trực tiếp trong production chỉ nhằm “làm JMX hoạt động”; cách đó có thể bỏ qua security, transaction hoặc advice khác.

## 6. Bước chẩn đoán 2: tìm đúng MBeanServer

Với Spring, exporter có thể được cấu hình \`setServer(customMBeanServer)\` hoặc nhận server qua context.

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Nếu ứng dụng có bean server riêng:

\`\`\`java
MBeanServer configured =
    context.getBean(MBeanServer.class);
\`\`\`

Chỉ gọi \`getBean(MBeanServer.class)\` nếu context thực sự có bean phù hợp và không bị ambiguous. Trong môi trường nhiều server, dùng qualifier/bean name tường minh.

So sánh:

\`\`\`java
System.out.println(
    platform.isRegistered(expectedObjectName));
System.out.println(
    configured.isRegistered(expectedObjectName));
\`\`\`

Nếu exporter dùng server riêng, JConsole local thường đang nhìn vào platform server của JVM chứ không tự động duyệt mọi server tạo trong process.

### 6.1. Truy vấn tên thay vì chỉ kiểm tra tên cũ

\`\`\`java
Set<ObjectName> found =
    configured.queryNames(
        new ObjectName("com.example.orders:*"),
        null);

for (ObjectName name : found) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Nếu tên được tạo qua naming strategy dựa trên class/proxy identity, ObjectName có thể thay đổi sau khi AOP được bật. Trong trường hợp đó, MBean **không biến mất** mà chỉ đổi định danh.

Trên hệ thống lớn, ưu tiên domain pattern hẹp thay vì \`*:* \` để tránh lấy toàn bộ JMX registry.

## 7. Bước chẩn đoán 3: xác minh registration và metadata

Nếu tìm được ObjectName, đọc \`MBeanInfo\`:

\`\`\`java
MBeanInfo info = configured.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OP " + op.getName());
}
\`\`\`

Phân tích:

- \`MBeanInfo\` trả thành công, attributes/operations đúng: vấn đề có thể nằm ở client/console hoặc việc tìm nhầm tên.
- Attributes thiếu: kiểm tra annotation trên method, interface và metadata assembler.
- Operations thiếu: kiểm tra \`@ManagedOperation\`, proxy interfaces và assembler.
- MBeanInfo khác trước: có khả năng exporter đang expose một interface khác vì proxy.

### 7.1. Trường hợp chỉ còn Standard MBean interface

Nếu implementation trực tiếp tuân theo \`XxxMBean\` interface nhưng JDK proxy chỉ implement business interface, exporter có thể không còn nhìn thấy đối tượng theo cùng tiêu chí JMX compliance. Dùng Standard MBean adapter hoặc explicit exposure phù hợp khi cần; không tự động kết luận annotation-only export sẽ giải quyết mọi trường hợp.

## 8. Bước chẩn đoán 4: xem log đăng ký và lỗi khởi tạo

Một MBean có thể không xuất hiện vì exporter thử đăng ký rồi thất bại. Các lỗi hữu ích:

| Exception / triệu chứng | Có thể liên quan đến |
|---|---|
| \`NotCompliantMBeanException\` | Object/proxy không đáp ứng hợp đồng MBean theo đường export |
| \`InstanceAlreadyExistsException\` | ObjectName bị trùng, có nhiều exporter hoặc context |
| \`MalformedObjectNameException\` | Naming strategy sinh tên sai cú pháp |
| \`BeanCreationException\` | Exporter hoặc bean phụ thuộc không khởi tạo được |
| \`IllegalArgumentException\` từ assembler | Metadata/method exposure không hợp lệ |
| Không có lỗi nhưng thiếu MBean | Autodetection không chọn bean, sai server hoặc tên |

Trong quá trình chẩn đoán có kiểm soát, tăng log cho khu vực Spring JMX export, chẳng hạn \`org.springframework.jmx\`, và xem exception chain. Cách bật log cụ thể tùy framework logging của ứng dụng.

Không bật logging debug toàn bộ Spring ở production lâu dài nếu nó gây tải và lộ dữ liệu nhạy cảm.

### 8.1. Vì sao lỗi có thể bị che?

Một số cấu hình registration policy có thể bỏ qua ObjectName đã tồn tại. Nếu có \`RegistrationPolicy.IGNORE_EXISTING\`, exporter mới có thể không đăng ký bean đang mong đợi mà server vẫn giữ MBean cũ. Điều này dễ bị hiểu nhầm là AOP khiến bean “biến mất” hoặc “không cập nhật”.

Để chẩn đoán, xác nhận MBean hiện có thuộc exporter/context nào và không dùng \`REPLACE_EXISTING\` chỉ để che collision.

## 9. Bước chẩn đoán 5: kiểm tra ranh giới ApplicationContext

Ứng dụng Spring có thể có nhiều context:

\`\`\`text
RootContext:
  - Service + Transaction AOP
  - Exporter R

ChildContext:
  - Controller + Exporter C
\`\`\`

Parent không tự enumerate child beans. Một exporter thuộc root không nhất thiết thấy bean chỉ tồn tại trong child. Nếu AOP configuration được chuyển sang context khác hoặc bean được khai báo lại, nơi exporter hoạt động có thể không còn phù hợp.

Kiểm tra:

1. Bean được định nghĩa trong context nào?
2. Exporter thuộc context nào?
3. Các exporter có cùng server không?
4. Annotation export được bật tại context nào?
5. Có bean bị tạo lặp giữa parent và child không?
6. Context đã đóng hoặc refresh lại chưa?

Một thay đổi transaction có thể đồng thời thay đổi cấu trúc cấu hình, scan package hoặc context hierarchy. Không quy mọi lỗi phát sinh sau thay đổi đó cho proxy nếu chưa kiểm chứng.

## 10. Ví dụ tái hiện JDK proxy và getter quản trị

### 10.1. Interface nghiệp vụ

\`\`\`java
public interface PaymentService {
    void pay();
}
\`\`\`

### 10.2. Implementation có metadata quản trị

\`\`\`java
import org.springframework.jmx.export.annotation.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "training.proxy:type=PaymentService,name=Primary")
public class PaymentServiceImpl implements PaymentService {

    private volatile int processed;

    @Override
    @Transactional
    public void pay() {
        processed++;
    }

    @ManagedAttribute
    public int getProcessed() {
        return processed;
    }

    @ManagedOperation
    public void resetProcessed() {
        processed = 0;
    }
}
\`\`\`

Khi Spring tạo JDK proxy chỉ implement \`PaymentService\`, getter \`getProcessed()\` và operation \`resetProcessed()\` không nằm trên business interface. Tùy exporter và cơ chế metadata, kết quả JMX có thể khác so với khi bean không proxy.

### 10.3. Các hướng điều chỉnh

**Hướng A — Thiết kế management interface rõ ràng**

\`\`\`java
public interface PaymentManagement {
    int getProcessed();
    void resetProcessed();
}
\`\`\`

Nếu JDK proxy cần expose management interface, target class có thể implement interface này và proxy được cấu hình giữ interface đó. Đồng thời đảm bảo assembler/exporter công bố các methods mong muốn.

**Hướng B — Class-based proxy khi phù hợp**

Có thể cấu hình proxy theo class trong một ứng dụng được thiết kế cho cách đó. Ví dụ \`@EnableTransactionManagement(proxyTargetClass = true)\` khi dùng Spring proxy-based transaction management:

\`\`\`java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TransactionConfig {
}
\`\`\`

Cách này có thể giữ khả năng introspection các methods của class, nhưng phải kiểm tra final classes/methods, các proxy khác và semantics transaction. Không đổi proxy strategy trên toàn ứng dụng khi chưa đánh giá ảnh hưởng.

**Hướng C — Xuất một adapter quản trị riêng**

Thay vì export trực tiếp bean có nhiều AOP advice, tạo một management facade đơn giản:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.proxy:type=PaymentManagement,name=Primary")
public class PaymentManagementFacade {
    private final PaymentService paymentService;
    private final PaymentStatistics statistics;

    public PaymentManagementFacade(
            PaymentService paymentService,
            PaymentStatistics statistics) {
        this.paymentService = paymentService;
        this.statistics = statistics;
    }

    @ManagedAttribute
    public int getProcessed() {
        return statistics.processedCount();
    }

    @ManagedOperation
    public void resetStatistics() {
        statistics.reset();
    }
}
\`\`\`

Facade tách hợp đồng JMX khỏi chi tiết proxy của business service. Trong ví dụ, \`PaymentStatistics\` là một service/component cần được định nghĩa trong dự án thực tế. Các operation thay đổi trạng thái vẫn cần authorization và audit nếu phù hợp.

## 11. Kiểm tra nội dung annotation và metadata assembler

Một bean có thể được đăng ký nhưng thiếu metadata vì cơ chế assembler được chọn không đọc \`@ManagedAttribute\` và \`@ManagedOperation\`.

Với Spring annotation export, thường sử dụng hạ tầng annotation metadata như \`AnnotationJmxAttributeSource\` và assembler thích hợp. Nếu dự án override \`MBeanInfoAssembler\` bằng \`MethodNameBasedMBeanInfoAssembler\` hoặc một custom assembler, annotation có thể không còn là nguồn quyết định exposure.

Cần kiểm tra:

- \`MBeanExporter\` đang dùng assembler nào?
- Annotation exporter có còn được bật không?
- Target class hoặc interface nào được assembler inspect?
- Method được annotate có public và có signature hợp lệ không?
- \`@ManagedResource\` có được phát hiện từ type thích hợp không?
- Một ObjectName tường minh có bị ghi đè bởi naming strategy không?

**Không chỉ thêm annotation lên cả interface và implementation một cách mù quáng.** Phương án đặt annotation phải phù hợp cơ chế Spring JMX metadata của phiên bản dự án; kiểm thử đầu ra JMX thực tế là cách xác nhận.

## 12. Chẩn đoán nhanh bằng chương trình Java

Đoạn helper dưới đây sử dụng một \`MBeanServer\` có sẵn trong JVM. Có thể đặt nó vào một đoạn code test hoặc diagnostic nội bộ.

\`\`\`java
import javax.management.*;
import java.util.Set;

public final class JmxDiagnostic {
    public static void inspect(
            MBeanServer server,
            String domainPattern) throws Exception {

        ObjectName pattern =
            new ObjectName(domainPattern + ":*");

        Set<ObjectName> names =
            server.queryNames(pattern, null);

        System.out.println("MBeans found: " + names.size());

        for (ObjectName name : names) {
            System.out.println("NAME " +
                name.getCanonicalName());

            MBeanInfo info = server.getMBeanInfo(name);

            for (MBeanAttributeInfo a : info.getAttributes()) {
                System.out.printf(
                    "  ATTR %s %s read=%s write=%s%n",
                    a.getName(), a.getType(),
                    a.isReadable(), a.isWritable());
            }

            for (MBeanOperationInfo op : info.getOperations()) {
                System.out.println(
                    "  OP " + op.getName());
            }
        }
    }
}
\`\`\`

Gọi:

\`\`\`java
JmxDiagnostic.inspect(server, "training.proxy");
\`\`\`

Những bằng chứng này trả lời “MBean có thực sự biến mất?” và “metadata có thay đổi?” mà không cần đoán từ UI. Nếu không có server phù hợp trong cùng JVM, dùng \`MBeanServerConnection\` từ JMX connector được cấp quyền.

## 13. Kiểm thử regression trước và sau khi bật AOP

Viết một integration test dùng cùng cấu hình exporter nhưng thay đổi cách áp dụng proxy, sau đó xác minh **contract JMX**, không chỉ business logic.

Các assertions quan trọng:

\`\`\`java
ObjectName name = new ObjectName(
    "training.proxy:type=PaymentService,name=Primary");

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);

// Kiểm tra tên và kiểu attribute cần thiết.
// Kiểm tra getProcessed readable.
// Kiểm tra resetProcessed operation đã được expose.
// Gọi operation rồi xác minh giá trị.
\`\`\`

Với Spring context chứa transaction/AOP, cần test thực thi qua chính proxy mà container cung cấp. Nếu chỉ tạo implementation bằng \`new PaymentServiceImpl()\`, test sẽ không tái hiện proxy.

### 13.1. Ma trận test gợi ý

| Tình huống | Mục tiêu |
|---|---|
| Không AOP | Baseline interface MBean |
| JDK proxy | Đảm bảo annotation/method exposure không mất |
| Class-based proxy | Kiểm tra visibility và limitations |
| Custom assembler | Bảo đảm metadata nhất quán |
| Nhiều contexts | Tránh duplicate/unregister sai |
| Context restart | MBean được đăng ký lại đúng tên |
| Remote client | Xác minh kết nối tới server thực tế |

Nếu sử dụng \`MBeanServerFactory.newMBeanServer()\` làm server fixture, nhớ inject server vào exporter. Test chỉ đọc platform server có thể thất bại giả nếu exporter đăng ký vào fixture server riêng.

### 13.2. Assertion thực tế về metadata

\`\`\`java
import java.util.Arrays;

boolean hasProcessed =
    Arrays.stream(info.getAttributes())
        .anyMatch(a -> a.getName().equals("Processed")
            && a.isReadable());

boolean hasReset =
    Arrays.stream(info.getOperations())
        .anyMatch(op -> op.getName().equals("resetProcessed"));

assertTrue(hasProcessed);
assertTrue(hasReset);
\`\`\`

Khi tester đổi JDK proxy sang CGLIB proxy, cả hai assertions vẫn phải đại diện cho một management contract ổn định nếu tính năng JMX được cam kết hỗ trợ.

## 14. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
|---|---|---|
| Trước AOP có MBean, sau AOP không | Autodetection không nhận proxy hoặc metadata bị che | Kiểm tra \`AopUtils\`, exporter, logs |
| MBean còn nhưng thiếu getter quản trị | Getter không có trên JDK proxy interface | Xem proxy interfaces và \`MBeanInfo\` |
| MBean có ObjectName lạ | Naming strategy dùng identity/proxy type | Query domain và canonical names |
| Lỗi \`NotCompliantMBeanException\` | Proxy không tuân hợp đồng MBean | Xem adapter/assembler và exported object |
| Không thấy bean trong JConsole | Exporter dùng custom server | Kiểm tra server identity |
| Lỗi \`InstanceAlreadyExistsException\` | Nhiều exporter/context trùng tên | Xem registration policy và ownership |
| Bean tồn tại nhưng JMX metadata rỗng | Annotation assembler không hoạt động | Kiểm tra exporter config |
| Transaction chạy không đúng sau sửa JMX | Đã bypass proxy hoặc self-invocation | Khôi phục proxy boundary, dùng facade |
| Chỉ remote client lỗi | Connector/auth/network hoặc server khác | Tách tầng transport khỏi export |

Đừng chọn cách “fix” bằng việc lấy target object qua \`Advised.getTargetSource().getTarget()\` rồi gọi trực tiếp nếu mục tiêu là giữ transaction/security advice. Đây có thể là cách debug có kiểm soát, nhưng gọi target trực tiếp có thể bỏ qua semantics của AOP proxy.

## 15. Quy trình xử lý sự cố có thứ tự

### Giai đoạn 1 — Xác nhận triệu chứng

1. Ghi lại ObjectName và attributes/operations trước khi bật AOP nếu có dữ liệu baseline.
2. Xác nhận JVM và MBeanServer hiện tại.
3. Query danh sách ObjectNames theo domain.
4. Phân biệt không đăng ký, đổi tên hay metadata thay đổi.

### Giai đoạn 2 — Xác nhận proxy

5. In \`AopUtils.isAopProxy\`, \`isJdkDynamicProxy\`, \`isCglibProxy\`.
6. Xem target class và interfaces.
7. Kiểm tra annotations trên target/interface theo cấu hình thực tế.
8. Xem exporter và assembler nào đang hoạt động.

### Giai đoạn 3 — Sửa cấu hình phù hợp

9. Nếu naming thay đổi: chọn ObjectName logic ổn định.
10. Nếu JDK proxy thiếu management methods: cân nhắc management interface hoặc management facade.
11. Nếu assembler không nhận metadata: cấu hình annotation assembler thích hợp.
12. Nếu collision: sửa namespace/ownership, không che lỗi bằng replace policy.
13. Nếu khác server: inject đúng MBeanServer và kết nối đúng endpoint.
14. Nếu proxy strategy cần đổi: kiểm tra tác động tới transaction và các advice khác.

### Giai đoạn 4 — Bảo vệ kết quả

15. Bổ sung integration test cho ObjectName, metadata và invocation.
16. Kiểm tra lifecycle context restart/unregister.
17. Chạy test với cấu hình AOP/transaction thực tế.
18. Với remote JMX, kiểm tra connector/security riêng khỏi lỗi export.

## 16. Lưu ý bảo mật và vận hành

JMX là giao diện quản trị. Một thay đổi proxy đôi khi khiến người phát triển cố export trực tiếp implementation hoặc mở rộng metadata quá mức để tìm lại method cũ. Cần tránh:

- Expose toàn bộ public methods vì tiện debug.
- Công khai credentials, token hoặc dữ liệu cá nhân trong attributes.
- Bypass AOP security/transaction để operation “chạy được”.
- Dùng \`RegistrationPolicy.REPLACE_EXISTING\` để ghi đè bean của module khác.
- Mở remote JMX không bảo vệ để kiểm chứng MBean tồn tại.
- Gọi operation phá hủy dữ liệu trên hệ thống production chỉ để thử.

Một management facade rõ ràng thường dễ ổn định hơn so với việc phụ thuộc vào chi tiết proxy của business service.

## 17. Bài tập thực hành

### Bài tập A — Quan sát proxy

Tạo service có \`@Transactional\`, in kết quả \`AopUtils.isAopProxy\` và \`AopUtils.getTargetClass\`. Đổi cấu hình JDK/CGLIB proxy trong môi trường lab và so sánh. Giải thích vì sao cùng một bean definition có thể trả về object class khác.

### Bài tập B — Getter không có trên interface

Tạo \`PaymentService\` chỉ có \`pay()\`, còn implementation thêm \`@ManagedAttribute getProcessed()\`. Bật JDK proxy và kiểm tra MBeanInfo. Sau đó đưa \`getProcessed()\` vào một interface phù hợp hoặc dùng management facade, rồi kiểm tra lại contract.

### Bài tập C — ObjectName thay đổi

Thử một naming strategy dựa trên identity, rồi bật AOP. Query ObjectNames trong server trước và sau. Giải thích vì sao một dashboard hard-code generated name có thể báo MBean biến mất dù MBean vẫn được đăng ký.

### Bài tập D — Hai ApplicationContext

Tạo parent/child contexts và đặt exporter ở root. Đăng ký management bean chỉ trong child. Kiểm tra có được autodetect hay không. Di chuyển exporter hoặc cấu hình explicit registration với ownership phù hợp, rồi kiểm tra lại.

### Bài tập E — Contract regression

Viết JUnit test xác minh cùng một ObjectName, \`Processed\` attribute và \`resetProcessed\` operation tồn tại trước/sau khi kích hoạt transaction advice. Chỉ kết luận đã giải quyết khi test truy cập qua \`MBeanServerConnection\` thành công.

## 18. Câu hỏi tự kiểm tra

1. Vì sao thêm \`@Transactional\` có thể thay đổi class mà Spring trả về?
2. JDK dynamic proxy khác class-based proxy ở khả năng expose methods như thế nào?
3. Tại sao việc \`isRegistered(oldName) == false\` chưa chứng minh MBean đã mất?
4. Làm sao xác định exporter dùng đúng MBeanServer?
5. \`MBeanInfo\` giúp phân biệt những dạng lỗi nào?
6. Vì sao không nên tắt AOP chỉ để sửa lỗi JMX?
7. Khi nào management facade tốt hơn export trực tiếp business bean?
8. \`RegistrationPolicy.IGNORE_EXISTING\` có thể che lỗi gì?
9. Vì sao parent exporter không nhất thiết phát hiện bean ở child context?
10. Làm thế nào bảo vệ contract JMX trước một thay đổi proxy strategy?

## 19. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — \`AnnotationMBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework API — \`AopUtils\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html

**Ghi nhớ:** sau khi bật AOP hoặc transaction, “MBean biến mất” có thể là thay đổi proxy, metadata, naming strategy, server hoặc context lifecycle. Chẩn đoán theo bằng chứng từ ApplicationContext, MBeanServer và MBeanInfo trước khi sửa cấu hình. Ưu tiên giữ hợp đồng JMX ổn định mà không phá transaction và security semantics.
