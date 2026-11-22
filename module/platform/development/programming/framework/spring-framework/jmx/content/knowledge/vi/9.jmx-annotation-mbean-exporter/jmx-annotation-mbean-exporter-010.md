# Giới hạn khi dùng annotation nhưng proxy che khuất target class

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một Spring bean có annotation JMX trên **target class** vẫn có thể export sai hoặc không được export khi bean được bao bởi **Spring AOP proxy**.
- Phân biệt target object, JDK dynamic proxy, CGLIB proxy, management interface và metadata JMX.
- Hiểu vai trò của \`AnnotationMBeanExporter\`, \`MetadataMBeanInfoAssembler\`, \`AnnotationJmxAttributeSource\` và \`MBeanServer\`.
- Nhận diện các biểu hiện: thiếu \`@ManagedAttribute\`/\`@ManagedOperation\`, \`NotCompliantMBeanException\`, sai \`ObjectName\`, hoặc exporter chọn nhầm metadata từ proxy.
- Chọn cách cấu hình ổn định: tách bean quản trị, dùng interface phù hợp, kiểm soát export path và xác minh MBean thật qua \`MBeanInfo\`.
- Hiểu rủi ro khi cố gỡ proxy hoặc thay proxy strategy chỉ để annotation JMX có hiệu lực.

## 2. Bối cảnh: annotation nằm ở đâu, bean thực tế là gì?

Trong Spring Framework, một bean có thể được khai báo:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=OrderMonitor,name=primary")
public class OrderMonitor {

    private int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation
    public void resetStatistics() {
        pendingCount = 0;
    }
}
\`\`\`

Nhìn vào source, ta thấy \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\`. Nhưng nếu bean chịu tác động bởi transaction, security, cache, retry hoặc advice của Spring AOP thì instance được nhận từ application context có thể là **proxy**, không phải instance target nguyên gốc.

\`\`\`text
ApplicationContext
      |
      v
  bean "orderMonitor"
      |
      v
  [Spring AOP proxy] ------------> [OrderMonitor target]
         |                                  |
         |                                  +-- @ManagedResource
         |                                  +-- @ManagedAttribute
         |                                  +-- @ManagedOperation
         |
         +-- đối tượng mà một exporter có thể nhận được
\`\`\`

Khi một component quản trị phân tích **class của proxy** hoặc danh sách method chỉ hiện diện trên proxy, thông tin annotation của target không phải lúc nào cũng được nhìn thấy như kỳ vọng. Hiệu ứng phụ thuộc loại proxy và các cơ chế Spring exporter/assembler sử dụng.

**Điểm cốt lõi:** Java annotation không có nghĩa metadata sẽ tự động hiện diện y hệt trên mọi proxy class hay trên mọi interface method. Exporter cần xác định đúng type/method và chính sách tìm annotation phù hợp.

## 3. AnnotationMBeanExporter làm gì?

\`AnnotationMBeanExporter\` là một thành phần hỗ trợ export Spring beans thành JMX MBeans dựa trên metadata annotation. Trong hệ Spring JMX, các annotation quan trọng gồm:

- \`@ManagedResource\`: mô tả tài nguyên quản lý, có thể chỉ định ObjectName và description.
- \`@ManagedAttribute\`: mô tả getter/setter được đưa ra thành JMX attribute.
- \`@ManagedOperation\`: mô tả operation có thể gọi qua JMX.
- \`@ManagedOperationParameter\`, \`@ManagedOperationParameters\`, \`@ManagedMetric\`, v.v. dùng khi cần metadata phong phú hơn.

Một annotation-driven exporter thường phối hợp **attribute source** đọc metadata và **MBeanInfo assembler** biến metadata ấy thành \`MBeanInfo\`.

Luồng khái quát:

\`\`\`text
Spring bean instance
       |
       v
AnnotationMBeanExporter / MBeanExporter
       |
       +-- phát hiện @ManagedResource
       +-- tìm @ManagedAttribute, @ManagedOperation
       +-- dựng MBeanInfo qua assembler
       +-- chọn ObjectName
       |
       v
MBeanServer.registerMBean(...)
       |
       v
JConsole / JMX client
\`\`\`

Từng bước có thể bị ảnh hưởng bởi proxy. Ví dụ lúc tìm annotation trên bean type, exporter có thể cần xác định class của target; lúc gọi operation, proxy phải thực sự expose method tương ứng; lúc xác định object name, naming strategy phải xử lý đúng target type.

### Phân biệt “export được” và “expose đúng”

Có ít nhất ba tình huống khác nhau:

1. **Không có MBean:** không phát hiện \`@ManagedResource\`, không register, hoặc register thất bại.
2. **Có MBean nhưng thiếu attribute/operation:** export thành công nhưng metadata JMX không phản ánh các method đã annotate.
3. **Có metadata nhưng gọi operation lỗi:** metadata được tạo nhưng method không gọi được qua proxy/interface hoặc logic target ném exception.

Các triệu chứng này có nguyên nhân và cách kiểm tra khác nhau. Không thể kết luận nguyên nhân chỉ từ việc thấy bean đã có annotation.

## 4. JDK dynamic proxy: chỉ expose các interface

Một **JDK dynamic proxy** thường triển khai một hoặc nhiều Java interfaces. Proxy class không kế thừa trực tiếp concrete target class. Nếu Spring tạo proxy theo interface, method của implementation không nằm trên interface có thể không được gọi qua proxy như method của concrete class.

Ví dụ:

\`\`\`java
public interface OrderService {
    int currentPendingCount();
}
\`\`\`

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=OrderService,name=primary")
public class DefaultOrderService implements OrderService {

    @Override
    @ManagedAttribute
    public int currentPendingCount() {
        return 7;
    }

    // Không được khai báo trong OrderService.
    public void resetInternalCounters() {
        // ...
    }
}
\`\`\`

Nếu \`DefaultOrderService\` được proxied bằng JDK dynamic proxy triển khai \`OrderService\`, phía ngoài thường làm việc qua \`OrderService\`, không phải trực tiếp với \`DefaultOrderService\`. Điều này tạo giới hạn rõ:

- \`currentPendingCount()\` tồn tại trên interface, nên proxy có thể chuyển lời gọi tới target.
- \`resetInternalCounters()\` không thuộc interface, nên một JDK proxy chỉ triển khai \`OrderService\` không cung cấp method này cho lời gọi trực tiếp.
- Annotation nằm trên implementation method không tự biến nó thành annotation của interface method trong Java reflection thông thường.
- Cơ chế tìm annotation của Spring có thể hỗ trợ đi ngược về target, nhưng **có tìm được metadata** và **có invoke được method trên proxy** là hai câu hỏi khác nhau.

Trong thực tế, đừng cố giải quyết bằng cách chỉ đổi \`@ManagedOperation\` cho \`resetInternalCounters()\` rồi kỳ vọng proxy lập tức có method ấy. Hãy xác định export contract và proxy exposure.

## 5. CGLIB proxy: subclass không có nghĩa không còn rủi ro

CGLIB proxy (class-based proxy) thường là subclass của target type. Do đó nó có thể thấy nhiều method của concrete class hơn JDK dynamic proxy.

Nhưng vẫn có giới hạn:

- Method \`final\` không được CGLIB override để áp dụng advice.
- Class \`final\` không thể được CGLIB subclass.
- Method \`private\` không thể được proxy override như một public method.
- Annotation tìm theo proxy class hay theo target class có thể tạo hành vi khác nhau.
- Metadata reader, naming strategy và Spring version có thể khác nhau về khả năng xử lý proxy.

CGLIB **không tự bảo đảm** mọi annotation ở target đều được exporter nhận diện. Nó cũng không giải quyết mọi vấn đề visibility, lifecycle, metadata và invocation.

Đặc biệt không nên bật \`proxyTargetClass=true\` cho toàn ứng dụng chỉ nhằm xử lý JMX. Điều đó có thể làm thay đổi cách proxy hoạt động ở transaction/security/cache và cách bean được inject/cast, gây tác động rộng hơn mục tiêu quản trị.

## 6. Java annotation và proxy: vì sao metadata không tự sao chép?

Java có những quy tắc reflection quan trọng:

- Annotation của class không mặc nhiên xuất hiện trên Java interface.
- \`@Inherited\` nếu có chỉ liên quan một số tình huống inheritance ở cấp **class**, không áp dụng cho method annotations như một phép sao chép tổng quát.
- Method của interface và method implementation là hai đối tượng reflection khác nhau.
- JDK proxy class được sinh động; nó không phải một subclass chứa toàn bộ annotation của target.
- CGLIB subclass có quan hệ kế thừa, nhưng method metadata và cách framework giải quyết overridden method vẫn cần xem xét.

Vì vậy, với annotation JMX nằm trên target class, cần biết exporter có dùng cơ chế như **target-class resolution**, **merged annotation lookup** hoặc **AOP utility** thích hợp hay không. Cách Spring xử lý thay đổi theo phiên bản và cấu hình; không nên tuyên bố mọi \`AnnotationMBeanExporter\` đều thất bại với proxy, cũng không nên mặc định mọi proxy đều trong suốt.

## 7. Kiểm tra bean thực tế: proxy hay target?

Dưới đây là đoạn debug chỉ dùng trong môi trường phát triển để nhận diện bean được Spring trả về:

\`\`\`java
import org.springframework.aop.support.AopUtils;

public final class BeanInspection {

    public static void inspect(Object bean) {
        System.out.println("runtime class = " + bean.getClass());
        System.out.println("isAopProxy = " + AopUtils.isAopProxy(bean));
        System.out.println("isJdkProxy = " + AopUtils.isJdkDynamicProxy(bean));
        System.out.println("isCglibProxy = " + AopUtils.isCglibProxy(bean));
        System.out.println("target class = " + AopUtils.getTargetClass(bean));
    }
}
\`\`\`

Dùng trong context:

\`\`\`java
Object bean = applicationContext.getBean("orderService");
BeanInspection.inspect(bean);
\`\`\`

Ví dụ một JDK proxy có runtime class dạng:

\`\`\`text
jdk.proxy2.$Proxy...
\`\`\`

và target class có thể là \`DefaultOrderService\`.

Các tên generated proxy class chỉ mang tính minh họa và phụ thuộc JDK/Spring. Đừng viết logic kiểm tra dựa trên chuỗi \`$Proxy\` hoặc \`$$SpringCGLIB$$\`; dùng API như \`AopUtils\`.

**Lưu ý:** \`AopUtils.getTargetClass\` cố suy ra target class theo khả năng Spring AOP cung cấp; trong trường hợp proxy đặc biệt/custom \`TargetSource\`, kết quả và khả năng nhận target cụ thể có thể khác nhau.

## 8. Kiểm tra JMX metadata sau export

Điểm kiểm chứng khách quan nhất là \`MBeanInfo\` từ \`MBeanServer\`, vì đây là API client thật sự nhìn thấy.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxMetadataInspection {
    public static void inspect() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName objectName = new ObjectName(
                "com.example.shop:type=OrderService,name=primary");

        if (!server.isRegistered(objectName)) {
            System.out.println("MBean chưa đăng ký");
            return;
        }

        MBeanInfo info = server.getMBeanInfo(objectName);

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf("ATTR %s read=%s write=%s%n",
                    attribute.getName(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.println("OP " + operation.getName());
        }
    }
}
\`\`\`

Đây là bước **kiểm tra hành vi xuất thực tế**, không chỉ tìm annotation trong source. Với Spring, cần bảo đảm đang kết nối tới đúng \`MBeanServer\` mà exporter sử dụng; một ứng dụng có thể cấu hình server tùy chỉnh thay vì platform server.

### Phân tích kết quả

- Nếu \`isRegistered\` trả \`false\`: kiểm tra exporter có chạy, bean có được quét và ObjectName có đúng không.
- Nếu có MBean nhưng attribute thiếu: kiểm tra attribute source/assembler, phương thức annotated, interface và proxy.
- Nếu metadata có operation nhưng \`invoke\` thất bại: kiểm tra method signature, khả năng gọi qua proxy, quyền truy cập và lỗi từ target.
- Nếu \`ObjectName\` không như kỳ vọng: kiểm tra \`@ManagedResource\`, naming strategy, cấu hình exporter và naming convention.

Không dùng một trường hợp thành công ở local để kết luận mọi mode proxy đều tương đương. Một bean chưa được AOP áp dụng có thể hoạt động trực tiếp nhưng sau khi thêm \`@Transactional\` hoặc \`@Cacheable\` lại đổi type runtime.

## 9. MBeanExporter và assembler: ranh giới cần hiểu

Trong Spring JMX, \`MBeanExporter\` có thể phối hợp các thành phần như:

| Thành phần | Vai trò |
|---|---|
| \`AnnotationMBeanExporter\` | Export bean được annotate theo cơ chế dựa trên annotation |
| \`AnnotationJmxAttributeSource\` | Đọc metadata từ các annotation \`@Managed...\` |
| \`MetadataMBeanInfoAssembler\` | Tạo metadata attributes/operations từ nguồn metadata |
| \`MetadataNamingStrategy\` | Suy ra ObjectName từ metadata resource |
| \`MBeanServer\` | Registry và runtime API JMX |

Lưu ý tên class và API cấu hình cụ thể có thể thay đổi tùy version Spring. Khi triển khai, kiểm tra tài liệu API tương ứng phiên bản đang chạy.

Cách đọc lỗi thường gặp:

\`\`\`text
Annotation có trên target
           |
           +-- exporter không tìm được annotation?
           |
           +-- assembler nhìn vào proxy method?
           |
           +-- naming strategy không thấy @ManagedResource?
           |
           +-- proxy không expose operation?
           |
           +-- registration trùng ObjectName?
\`\`\`

Đừng giải quyết mọi trường hợp bằng một cấu hình proxy toàn cục. Hãy xác định **điểm nào trong pipeline** làm thất lạc metadata hoặc invocation.

## 10. Giải pháp ưu tiên: tách management bean khỏi service có AOP

Một thiết kế đơn giản và ổn định là dùng **management adapter** chuyên cho JMX. Service nghiệp vụ vẫn có thể được AOP proxy, còn management bean định nghĩa API quản trị nhỏ, có chủ đích.

Ví dụ:

\`\`\`java
public interface OrderProcessingService {
    int pendingCount();
    void retryFailed();
}
\`\`\`

Service triển khai và có thể dùng transaction:

\`\`\`java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DefaultOrderProcessingService
        implements OrderProcessingService {

    @Override
    public int pendingCount() {
        return 12; // Thay bằng số liệu thực.
    }

    @Override
    @Transactional
    public void retryFailed() {
        // Thao tác nghiệp vụ có transaction.
    }
}
\`\`\`

Management bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderManagement {

    private final OrderProcessingService service;

    public OrderManagement(OrderProcessingService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending order count")
    public int getPendingCount() {
        return service.pendingCount();
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        service.retryFailed();
    }
}
\`\`\`

Ưu điểm:

1. \`OrderManagement\` chỉ có trách nhiệm công bố management contract.
2. \`DefaultOrderProcessingService\` có thể chịu proxy AOP và vẫn được inject qua interface.
3. Annotation JMX được đặt trên type quản trị dễ kiểm soát.
4. Người vận hành chỉ thấy các attributes/operations đã chọn.
5. Lời gọi từ management bean đi qua Spring proxy của service, giữ cơ chế transaction/advice cần thiết.

**Lưu ý:** Tách adapter giảm độ phức tạp nhưng không bảo đảm nó không bao giờ bị proxy; nếu có pointcut AOP rộng áp dụng cả adapter, hãy kiểm tra runtime class và metadata của chính management bean.

Operation \`retryFailedOrders\` có tác động nghiệp vụ thật; chỉ công bố nếu được phép về bảo mật/vận hành. Đây là ví dụ minh họa, không phải khuyến nghị mở thao tác nhạy cảm qua JMX không kiểm soát.

## 11. Giải pháp theo interface: thiết kế management contract rõ ràng

Nếu muốn Standard MBean theo Java JMX thuần, có thể tạo interface:

\`\`\`java
public interface OrderMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}
\`\`\`

và class:

\`\`\`java
public class OrderMonitor implements OrderMonitorMBean {
    @Override
    public int getPendingCount() {
        return 0;
    }

    @Override
    public void resetStatistics() {
        // Reset các counter chỉ phục vụ quan sát.
    }
}
\`\`\`

\`OrderMonitorMBean\` chính là **management interface** theo convention Standard MBean. Với trường hợp dùng \`StandardMBean\` wrapper, bạn cũng có thể chỉ định interface tường minh khi tên không theo convention.

Thiết kế này khác annotation-driven export: contract được xác định bởi interface thay vì metadata annotation. Nó có thể giảm sự phụ thuộc vào việc tìm annotation trên concrete target class, nhưng vẫn cần đảm bảo exporter nhận đúng object/target và cách invocation hợp lệ nếu bean được proxy.

Một JDK proxy chỉ expose interfaces mà nó triển khai. Vì vậy nếu muốn JMX operation chỉ ở concrete class nhưng không có trong interface mà proxy expose, bạn vẫn có thể gặp vấn đề. Cách đáng tin là định nghĩa management API trên một adapter/bean phù hợp và thử qua MBeanServer.

## 12. Giải pháp có kiểm soát: cấu hình export tường minh

Một số dự án chọn đăng ký bean qua \`MBeanExporter\` với ObjectName cố định, thay vì phụ thuộc hoàn toàn vào tự động quét annotation.

Ví dụ định hướng:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    MBeanExporter orderMonitorExporter(OrderMonitorMBean monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "com.example.shop.orders:type=OrderMonitor,name=primary",
                monitor));
        return exporter;
    }
}
\`\`\`

Đoạn trên minh họa cách khai báo mapping ObjectName → bean. Nó giả định ứng dụng có một bean \`OrderMonitorMBean\` phù hợp và cấu hình export không trùng với một exporter khác.

**Quan trọng:** Chỉ cấu hình \`setBeans\` không tự biến mọi proxy thành compliant MBean. Nếu proxy không phù hợp với JMX metadata/invocation, hãy dùng management adapter hoặc \`StandardMBean\` được thiết kế đúng, rồi kiểm tra registration và \`MBeanInfo\`.

Không đăng ký cùng ObjectName từ hai exporter hoặc từ Spring exporter và code thủ công, vì \`InstanceAlreadyExistsException\` có thể xảy ra.

## 13. Không nên gỡ proxy một cách tùy tiện

Một cách xử lý vội thường thấy là lấy target object phía sau proxy rồi export trực tiếp nó. Điều này có rủi ro:

- Bỏ qua advice của \`@Transactional\`, \`@Secured\`, \`@Cacheable\`, retry hoặc các interceptor khác.
- Thay đổi lời gọi quản trị thành lời gọi không có transaction/security context mong muốn.
- Với proxy dùng custom target source, target instance có thể không cố định hoặc không an toàn để giữ tham chiếu lâu dài.
- Vòng đời registration/unregistration và dependency initialization có thể trở nên phức tạp.

Nếu bắt buộc phải inspect target cho **metadata**, không có nghĩa nên **invoke target trực tiếp**. Metadata discovery và invocation là hai trách nhiệm khác nhau.

Cũng không nên tự động chuyển toàn ứng dụng từ JDK proxy sang CGLIB hoặc ngược lại chỉ để giải quyết annotation lookup. Thay đổi proxy mode có thể ảnh hưởng method interception và khả năng inject type trên toàn application context.

## 14. Tương tác với @Transactional, @Cacheable và @Async

### @Transactional

\`\`\`java
@Service
public class OrderServiceImpl implements OrderService {
    @Transactional
    public void updateOrderStatus() {
        // ...
    }
}
\`\`\`

Nếu JMX operation gọi thẳng target và bỏ qua Spring proxy, transaction advice có thể không chạy. Đặt management adapter gọi qua injected service proxy thường là cách rõ ràng hơn.

### @Cacheable

Bean bị proxy do caching có thể khiến class runtime khác target class. Annotation JMX trên target method cần được metadata reader nhận ra đúng. Không nên gắn \`@ManagedOperation\` lên method nghiệp vụ cache nếu nó không có ý nghĩa quản trị.

### @Async

Operation JMX gọi một phương thức \`@Async\` trên service proxy có thể trở về trước khi công việc kết thúc. Điều này ảnh hưởng semantics của operation quản trị: người vận hành cần biết lệnh “được chấp nhận” hay “đã hoàn thành”. Nên công bố trạng thái job qua attribute hoặc metric riêng nếu operation bắt đầu tác vụ bất đồng bộ.

Một điểm quan trọng của Spring AOP là **self-invocation**: lời gọi method từ một method khác của cùng target instance thường không đi qua proxy; advice có thể không được áp dụng. Nếu management adapter gọi qua service proxy thì dễ duy trì boundary rõ ràng hơn.

## 15. MBeanInfo và phương thức gọi: ví dụ chẩn đoán thực tế

Giả sử bean \`PaymentService\` được annotated:

\`\`\`java
@ManagedResource(objectName =
        "com.example.shop.payments:type=PaymentService,name=primary")
public class PaymentServiceImpl implements PaymentService {

    @ManagedAttribute
    public int getPendingCount() {
        return 8;
    }

    @ManagedOperation
    public void resetMetrics() {
        // ...
    }
}
\`\`\`

nhưng \`PaymentService\` interface chỉ khai báo:

\`\`\`java
public interface PaymentService {
    int getPendingCount();
}
\`\`\`

và Spring tạo JDK dynamic proxy.

Phân tích:

1. Nếu \`AnnotationMBeanExporter\` không lấy được \`@ManagedResource\` từ target, bean có thể bị bỏ qua.
2. Nếu exporter tìm được annotation nhưng chỉ xem method public trên proxy/interface, \`resetMetrics\` có thể không được expose như kỳ vọng.
3. Nếu metadata vẫn mô tả \`resetMetrics\` nhưng lời gọi không thể đi qua proxy, JMX invocation có thể lỗi.
4. Nếu interface được bổ sung \`resetMetrics\`, proxy có thể expose method nhưng vẫn cần xác minh annotation metadata và chính sách bảo mật.
5. Tách \`PaymentManagement\` bean chỉ có các API quản trị, gọi \`PaymentService\` qua interface, thường làm mục tiêu export rõ ràng hơn.

Đây là **các khả năng chẩn đoán**, không khẳng định một phiên bản Spring cụ thể chắc chắn có hành vi lỗi này. Hãy đọc stack trace/exporter log và \`MBeanInfo\` thực tế để xác định.

## 16. Checklist cấu hình và quan sát trong ứng dụng Spring

Khi một MBean annotation-driven không hoạt động như mong muốn, hãy kiểm tra theo thứ tự hợp lý:

1. Bean có thực sự tồn tại trong \`ApplicationContext\` và đã được khởi tạo chưa?
2. Bean có phải AOP proxy? \`AopUtils.isAopProxy(bean)\` trả gì?
3. Proxy loại JDK hay CGLIB? Target class là gì?
4. \`@ManagedResource\` nằm trên class/interface nào? Method annotations nằm ở đâu?
5. Exporter thực sự nào được cấu hình? Có trùng nhiều exporter không?
6. MBeanServer nào được dùng? Có đúng server bạn đang kiểm tra bằng JConsole/client không?
7. ObjectName được chọn là gì? Có conflict với MBean đã tồn tại không?
8. \`MBeanInfo\` có các attributes và operations được mong đợi không?
9. Nếu \`invoke\` thất bại, method signature có khớp và proxy có expose method ấy không?
10. Nếu JMX gọi method của service, advice transaction/security/cache có chạy qua proxy không?

Checklist này dùng cho quá trình điều tra kỹ thuật, không phải yêu cầu thay đổi mọi cấu hình nếu hiện tại đang hoạt động đúng.

## 17. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Annotation nằm trên target nhưng MBean không xuất hiện | Annotation lookup nhận proxy type, exporter không scan bean hoặc exporter chưa bật | Kiểm tra export config, target class resolution và ObjectName |
| Có MBean nhưng thiếu attribute | Metadata assembler chỉ thấy interface/proxy methods hoặc annotation đặt sai chỗ | Kiểm tra \`MBeanInfo\`, getter/setter và annotation source |
| \`NotCompliantMBeanException\` | Bean/proxy không phù hợp Standard MBean hoặc export path | Dùng adapter/interface phù hợp, xác định assembler và wrapper |
| Operation không gọi được | Method không expose trên proxy, sai signature hoặc target ném lỗi | Tách management adapter hoặc bổ sung interface đúng, đọc exception |
| Transaction không chạy khi gọi JMX | Bỏ qua AOP proxy để invoke target | Gọi service qua proxy được inject |
| Runtime type khác source class | Spring tạo JDK/CGLIB proxy | Dùng \`AopUtils\` thay vì kiểm tra class name thủ công |
| Trùng ObjectName | Hai exporter cùng đăng ký một tên | Chỉ định một owner export, thống nhất lifecycle |
| Metadata đúng ở local nhưng sai ở staging | Môi trường bật advice/auto config khác | Kiểm tra proxy mode và cấu hình triển khai thực tế |
| Bật CGLIB nhưng không khắc phục | Vấn đề metadata/registration không do JDK proxy | Chẩn đoán pipeline export thay vì đổi proxy mode |
| Đổi naming strategy gây mất dashboard | ObjectName thay đổi ngoài dự kiến | Giữ contract naming ổn định, cập nhật client có kế hoạch |

## 18. Thực hành

### Bài tập A — Đọc cấu trúc proxy

Cho interface \`InventoryService\` gồm method \`int availableCount()\` và implementation \`InventoryServiceImpl\` có thêm \`resetInternalCache()\`. Giả sử Spring dùng JDK proxy. Hãy giải thích:

- Interface method nào proxy có thể expose.
- Vì sao \`resetInternalCache()\` không tự trở thành method của proxy.
- Annotation ở implementation method có tự xuất hiện khi gọi Java reflection trên interface method không.

**Gợi ý:** Phân biệt proxy method surface và annotation lookup.

### Bài tập B — Thiết kế management adapter

Tạo \`InventoryManagement\` với:

\`\`\`java
@ManagedResource(objectName =
        "com.example.shop.inventory:type=InventoryMonitor,name=primary")
public class InventoryManagement {
    private final InventoryService inventoryService;

    public InventoryManagement(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ManagedAttribute
    public int getAvailableCount() {
        return inventoryService.availableCount();
    }
}
\`\`\`

Giải thích vì sao management bean chỉ expose attribute cần thiết và vẫn gọi service qua proxy.

### Bài tập C — Kiểm tra metadata

Sau khi export \`InventoryManagement\`, dùng \`MBeanServer.getMBeanInfo(ObjectName)\` và in danh sách attributes. Hãy xác nhận \`AvailableCount\` có thực sự được công bố. Sau đó thử chạy trong cấu hình có AOP proxy cho service, so sánh kết quả quan sát.

### Bài tập D — Chọn giải pháp

Bạn có một bean service được \`@Transactional\`, có \`@ManagedOperation\` trên method không thuộc service interface, và exporter không tìm ra operation. Nêu hai phương án:

1. Bổ sung management contract được proxy expose và cấu hình export hợp lệ.
2. Tách JMX management bean gọi service proxy qua interface.

Giải thích rủi ro nếu gỡ proxy rồi register target trực tiếp.

### Bài tập E — Phân biệt lỗi

Một MBean đã xuất hiện trong JConsole nhưng tab Operations rỗng. Có nên đổi sang CGLIB ngay không?

Không. Trước tiên cần đọc \`MBeanInfo\`, xác nhận \`@ManagedOperation\`, xem exporter/assembler đang sử dụng, kiểm tra runtime proxy type và method accessibility. Chỉ sau khi có bằng chứng mới chọn thay đổi cấu hình liên quan.

## 19. Câu hỏi tự kiểm tra

**1. Annotation \`@ManagedResource\` trên target class có chắc chắn được mọi proxy class nhìn thấy không?**

Không. Tùy cơ chế proxy, Java reflection thông thường và chiến lược lookup của framework.

**2. JDK dynamic proxy có expose mọi public method của implementation không?**

Không. Nó expose methods của interfaces mà proxy triển khai.

**3. CGLIB proxy có loại bỏ mọi giới hạn của annotation-driven JMX không?**

Không. Vẫn có ràng buộc về subclass/final methods, annotation lookup và export configuration.

**4. Vì sao quản trị viên nên đọc \`MBeanInfo\`?**

Vì đây là metadata JMX mà client thực tế nhìn thấy, gồm attributes, operations và notifications được công bố.

**5. Có nên bỏ qua Spring proxy để JMX gọi thẳng target?**

Không nên làm mặc định. Có thể bỏ qua transaction, security hoặc advice khác.

**6. Một management adapter có bảo đảm không bao giờ bị proxy không?**

Không. Pointcut rộng vẫn có thể áp dụng; cần kiểm tra cấu hình.

**7. Spring bean name và ObjectName có giống nhau không?**

Không. Bean name phục vụ Spring container, còn ObjectName định danh MBean trong MBeanServer.

## 20. Ghi nhớ

- Annotation-driven JMX phụ thuộc vào **metadata discovery**, **naming** và **invocation**; proxy có thể ảnh hưởng từng bước theo cách khác nhau.
- JDK proxy chủ yếu expose interface methods; CGLIB proxy subclass target nhưng không loại bỏ mọi giới hạn.
- Annotation nằm trên implementation không tự chuyển thành annotation của interface method bằng Java reflection thông thường.
- Không suy diễn lỗi từ proxy chỉ bằng cách nhìn class source; kiểm tra \`AopUtils\`, exporter và \`MBeanInfo\`.
- Tách management adapter là thiết kế dễ quản lý khi service nghiệp vụ có AOP, transaction, caching hoặc security.
- Không tự ý unwrap target để gọi trực tiếp qua JMX, vì có thể bỏ qua advice quan trọng.
- Giữ ObjectName ổn định và kiểm tra quyền khi công bố operations có side effect.
- Muốn biết đúng hành vi của ứng dụng, kiểm tra **MBean đăng ký và metadata thực tế** thay vì chỉ đếm annotation.

## 21. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`AnnotationMBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework Javadoc — \`AopUtils\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
