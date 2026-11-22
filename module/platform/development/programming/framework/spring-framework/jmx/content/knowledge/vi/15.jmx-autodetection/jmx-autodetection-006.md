# Proxy interface che annotation và vì sao Spring JMX autodetection có thể bỏ qua bean

## 1. Hiện tượng cần giải thích

Trong Spring Framework, `MBeanExporter` có khả năng tự tìm các bean có thể export qua JMX thay vì phải khai báo từng entry trong `setBeans`. Một cách phổ biến là dùng `@ManagedResource` để đánh dấu class quản trị, rồi để annotation-based metadata và cơ chế autodetection tìm thấy chúng.

Tình huống khó hiểu xuất hiện khi cùng một bean:

- Chạy bình thường nếu không có AOP.
- Có `@ManagedResource` trên implementation class.
- Khi bật `@Transactional`, method security hoặc advice khác, bean được Spring bọc bởi **JDK dynamic proxy** chỉ phơi bày các interface.
- JMX exporter không thấy bean hoặc không xuất đủ attribute/operation.

Điểm cốt lõi: **annotation được khai báo trên target class không đồng nghĩa annotation xuất hiện trên proxy class hoặc proxy interface**. Khi một thành phần thực hiện autodetection chỉ nhìn vào loại runtime/interface của proxy, nó có thể bỏ qua metadata ở implementation. Spring có những cơ chế nhận diện target class, vì vậy kết quả cụ thể còn phụ thuộc cách cấu hình exporter, metadata assembler, proxy và phiên bản Spring.

Bài này giải thích những lớp cần phân biệt, cách kiểm chứng thực tế và cách thiết kế adapter tránh phụ thuộc vào cách proxy che annotation.

## 2. Autodetection trong Spring JMX là gì?

`MBeanExporter` có thể được cấu hình đăng ký:

1. **Explicit beans**: một map từ key/ObjectName tới bean hoặc bean name.
2. **Autodetected beans**: exporter tìm các bean phù hợp với quy tắc phát hiện, ví dụ theo annotation metadata.
3. **MBean chuẩn**: đối tượng tuân thủ Standard MBean, MXBean hoặc `DynamicMBean`, tùy đường export và chế độ phát hiện.

Ví dụ annotation trên implementation:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;

@Service
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary",
    description = "Billing management"
)
public class BillingService implements BillingOperations {

    @ManagedAttribute(description = "Pending invoices")
    public long getPendingInvoiceCount() {
        return 12;
    }

    @Override
    public void processInvoice(String invoiceId) {
        // Business behavior.
    }
}
```

Nếu exporter dùng đúng `AnnotationJmxAttributeSource`, `MetadataMBeanInfoAssembler` và cơ chế phát hiện phù hợp, bean có thể được công bố với ObjectName khai báo. Nhưng nếu bean được thay bằng JDK proxy và logic phát hiện chỉ nhìn vào interface, `@ManagedResource` của implementation có thể không còn nhìn thấy theo đường đó.

**Không hiểu “autodetection” là thuật toán đảm bảo phát hiện mọi annotation ở mọi lớp target.** Nó là chính sách tìm bean, chịu ảnh hưởng cách introspect của exporter và proxy.

## 3. Java interface và JDK dynamic proxy làm thay đổi cái gì?

Một interface nghiệp vụ:

```java
public interface BillingOperations {
    void processInvoice(String invoiceId);
}
```

Implementation:

```java
@Service
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary"
)
public class BillingService implements BillingOperations {

    @Override
    public void processInvoice(String invoiceId) { }

    @ManagedAttribute
    public long getPendingInvoiceCount() {
        return 12;
    }
}
```

Khi Spring AOP dùng JDK dynamic proxy, object được trả cho caller thường có loại như `jdk.proxy2.$Proxy...`, triển khai `BillingOperations` và các interface hỗ trợ của proxy, **không phải subclass của `BillingService`**.

Hai hệ quả:

- `proxy.getClass()` không phải `BillingService.class`; một phép reflection trực tiếp trên proxy class không mặc nhiên tìm thấy annotation `@ManagedResource` của target.
- Proxy chỉ có các method thuộc những interface được nó triển khai. `getPendingInvoiceCount()` không thuộc `BillingOperations`, nên có thể không thể gọi qua reference proxy dù implementation có method public đó.

Vì thế có hai câu hỏi độc lập:

1. **Detection:** framework có tìm được annotation/class hợp lệ để chọn bean export không?
2. **Invocation:** sau khi chọn, MBean đại diện cho proxy có thực sự gọi được method được khai báo là JMX attribute/operation không?

Sửa được detection chưa chắc giải quyết invocation.

## 4. Annotation trên target class, proxy class và interface

Java annotation có quy tắc kế thừa riêng. Một annotation đặt trên implementation **không tự động được sao chép lên interface**, và JDK dynamic proxy không tự chép toàn bộ annotation của target lên proxy runtime class.

Ví dụ:

```java
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary"
)
public class BillingService implements BillingOperations {
    // ...
}
```

Ngay cả khi annotation có `@Inherited`, cơ chế kế thừa của Java chỉ áp dụng cho subclass theo quy tắc nhất định, không làm interface hoặc JDK proxy tự thừa hưởng annotation từ implementation. Reflection đơn giản sau đây có thể không phù hợp:

```java
boolean marked = bean.getClass()
    .isAnnotationPresent(ManagedResource.class);
```

Với Spring AOP, có thể truy vấn target class:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.jmx.export.annotation.ManagedResource;

Object bean = context.getBean("billingService");
Class<?> runtimeClass = bean.getClass();
Class<?> targetClass = AopUtils.getTargetClass(bean);

System.out.println("runtime=" + runtimeClass.getName());
System.out.println("target=" + targetClass.getName());

boolean targetMarked =
    AnnotatedElementUtils.hasAnnotation(
        targetClass, ManagedResource.class
    );
System.out.println("target annotation=" + targetMarked);
```

`AopUtils.getTargetClass` có thể phát hiện target class của một Spring AOP proxy thông dụng. Không nên sử dụng phép kiểm tra này như bằng chứng exporter chắc chắn dùng cùng thuật toán metadata; nó chỉ giúp quan sát vì sao class của bean nhìn từ bên ngoài khác class đã được annotate.

## 5. Minh họa đường autodetection có thể bỏ qua annotation

```text
Source code:
  @ManagedResource
  class BillingService implements BillingOperations
          |
          v
Spring AOP creates a JDK proxy
          |
          +--> runtime class: $Proxy...
          +--> exposed interface: BillingOperations
          +--> target class: BillingService (holds annotation)
          |
          v
MBeanExporter autodetection / metadata source
          |
          +--> Inspects target metadata correctly?
          |       +--> Yes: candidate may be detected
          |
          +--> Inspects proxy interface/runtime only?
                  +--> No @ManagedResource in that view
                  +--> Candidate may be skipped
```

Trong Spring thực tế, exporter có thể làm việc với bean instance, bean name, target class và metadata source. Đừng khẳng định rằng mọi JDK proxy đều làm autodetection thất bại; hãy xác nhận bằng thực nghiệm trên cấu hình và phiên bản đang chạy.

Đặc biệt chú ý thứ tự tạo bean và post-processing: khi một `BeanPostProcessor` tạo proxy trước lúc exporter kiểm tra bean, exporter có thể chỉ nhận object đã được proxy. Điều này lý giải vì sao bật một aspect có thể làm thay đổi kết quả phát hiện MBean dù source code annotation không đổi.

## 6. Cấu hình annotation-based JMX exporter

Spring JMX dùng các thành phần chính:

- `AnnotationJmxAttributeSource`: đọc metadata của `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
- `MetadataNamingStrategy`: giải quyết ObjectName từ metadata quản trị.
- `MetadataMBeanInfoAssembler`: tạo thông tin attribute và operation từ metadata.
- `MBeanExporter`: tìm bean và đăng ký MBean với `MBeanServer`.

Ví dụ cấu hình Java:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {

    @Bean
    public AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MBeanExporter exporter(
            AnnotationJmxAttributeSource source) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
```

Đây là một cấu hình minh họa cho Spring Framework thuần. Trong Spring Boot, `spring.jmx.enabled=true` và auto-configuration có thể cung cấp exporter; cần kiểm tra cấu hình cuối cùng thay vì thêm exporter thứ hai tùy tiện. Với Spring Framework, `@EnableMBeanExport` cũng là cách khai báo tính năng thuận tiện.

Nếu không có metadata assembler hoặc naming strategy phù hợp, sự có mặt của annotation trong source code chưa chứng minh rằng exporter đang dùng nó.

## 7. Tách lỗi “không phát hiện” khỏi “không đăng ký”

Hai triệu chứng gần giống nhưng khác nhau:

### Không được phát hiện

Spring context có bean `billingService`, nhưng exporter không chọn bean đó để export. Không có exception đăng ký MBean vì thao tác đăng ký chưa xảy ra.

Dấu hiệu:
- `context.containsBean("billingService")` là `true`.
- `MBeanServer.isRegistered(expectedName)` là `false`.
- Không có lỗi `InstanceAlreadyExistsException` hay `NotCompliantMBeanException` liên quan.
- Bean có thể được proxy; annotation nằm trên target nhưng không được autodetection đọc.

### Được phát hiện nhưng đăng ký thất bại

Exporter đã chọn bean, nhưng `registerMBean` không hoàn tất. Log có thể chứa `UnableToRegisterMBeanException` hoặc nguyên nhân sâu hơn:

- `MalformedObjectNameException`: tên sai cú pháp.
- `InstanceAlreadyExistsException`: trùng ObjectName.
- `NotCompliantMBeanException`: bean không tương thích JMX theo đường export.
- Lỗi reflection, mapping, proxy method hoặc lifecycle.

Hãy đọc stack trace thay vì dùng cùng một cách chữa cho cả hai. Gắn annotation thêm vào interface không giải quyết trùng ObjectName.

## 8. Cách quan sát bean proxy và server đăng ký

Một probe trong ứng dụng:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("billingService");

System.out.println("Spring bean class: " + bean.getClass());
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("Target class: " + AopUtils.getTargetClass(bean));

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example:type=BillingMonitor,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(expected));
```

Nếu exporter được cấu hình dùng custom `MBeanServer`, probe phải lấy đúng instance đó thay vì platform server. Một `false` trên server sai không chứng minh exporter bỏ qua bean.

Nếu MBean đã được đăng ký, hỏi metadata:

```java
var info = server.getMBeanInfo(expected);
for (var a : info.getAttributes()) {
    System.out.println("Attribute: " + a.getName());
}
for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}
```

Nếu `PendingInvoiceCount` thiếu, kiểm tra cả annotation method, interface proxy và assembler. Nếu có metadata nhưng `getAttribute` không chạy được, kiểm tra đường invocation qua proxy.

## 9. Giải pháp 1: xuất một adapter quản trị riêng

Phương án rõ ràng nhất là đặt annotation JMX trên class chuyên quản trị, không đặt trực tiếp trên service nghiệp vụ bị proxy.

Management port:

```java
public interface BillingManagement {
    long pendingInvoiceCount();
    void requestReconciliation();
}
```

Adapter:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary",
    description = "Billing management"
)
public class BillingJmxAdapter {
    private final BillingManagement management;

    public BillingJmxAdapter(BillingManagement management) {
        this.management = management;
    }

    @ManagedAttribute
    public long getPendingInvoiceCount() {
        return management.pendingInvoiceCount();
    }

    @ManagedOperation
    public void requestReconciliation() {
        management.requestReconciliation();
    }
}
```

`BillingManagement` có thể được triển khai bởi Spring-managed service proxy. Adapter gọi interface đó và vẫn đi qua transaction/security advice ở chỗ thích hợp.

Lợi ích:

- JMX annotation không bị lẫn vào API nghiệp vụ.
- Exporter inspect một class có bề mặt quản trị nhỏ.
- Lệnh quản trị qua một abstraction có thể kiểm thử và thêm guard.
- Dễ thay JMX bằng admin HTTP/CLI mà không sửa domain.
- Thay đổi AOP cho service ít ảnh hưởng tới quá trình export.

Nếu một pointcut AOP quá rộng cũng proxy `BillingJmxAdapter`, cần kiểm tra lại class runtime của adapter; không mặc định mọi adapter luôn không bị proxy.

## 10. Giải pháp 2: khai báo explicit export thay vì chỉ autodetect

Một cách khác là không dựa hoàn toàn vào tìm kiếm annotation. Khai báo bean cần xuất trong `MBeanExporter.setBeans` với key ObjectName cụ thể:

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

MBeanExporter exporter = new MBeanExporter();

exporter.setNamingStrategy(new KeyNamingStrategy());
exporter.setBeans(Map.of(
    "com.example:type=BillingMonitor,name=Primary",
    billingJmxAdapter
));
```

Ở đây `billingJmxAdapter` là object do Spring quản lý. Explicit export giúp tránh lỗi ở **giai đoạn lựa chọn candidate**, nhưng vẫn cần đảm bảo object được export có interface JMX hợp lệ hoặc có assembler chuyển POJO thành ModelMBean phù hợp.

Không gọi `new BillingService()` để né proxy: như vậy có thể làm mất dependency injection, transaction và security.

Nếu mục tiêu là xuất một service JDK proxy với method không nằm trên interface, explicit export cũng không tự bổ sung method đó vào proxy. Đổi bề mặt management hoặc dùng adapter mới là cách xử lý đúng.

## 11. Giải pháp 3: thiết kế interface proxy có đủ method cần gọi

Nếu dự án có lý do hợp lệ để export trực tiếp service, các method muốn đưa qua JMX phải **thực sự khả dụng** trên object exporter nhận. Với JDK proxy, điều này thường nghĩa là chúng phải có trên một interface do proxy triển khai.

```java
public interface BillingManagement {
    long getPendingInvoiceCount();
}
```

Service thực hiện:

```java
public class BillingService
        implements BillingOperations, BillingManagement {

    @Override
    public long getPendingInvoiceCount() {
        return 12;
    }

    @Override
    public void processInvoice(String invoiceId) {
        // ...
    }
}
```

Tuy nhiên, thêm interface chỉ giải quyết khả năng gọi method. Metadata `@ManagedResource` và `@ManagedAttribute` vẫn phải được exporter tìm thấy đúng vị trí. Annotation đặt trên interface không luôn tương đương với annotation đặt trên target implementation vì các quy tắc metadata và Java annotation inheritance khác nhau.

Khi không chắc, giữ annotation trên class adapter chuyên biệt và kiểm tra `MBeanInfo` sau đăng ký.

## 12. Giải pháp 4: cân nhắc class-based proxy, nhưng không đổi mù

Spring AOP có thể dùng class-based proxy (CGLIB) thay JDK proxy. Loại proxy này là subclass của target, nên thường có bề mặt method khác JDK proxy. Nhưng:

- Phương thức `final` không thể được override để intercept.
- Phương thức `private` không thể proxy theo cơ chế override.
- Self-invocation có thể bỏ qua advice.
- Một số vấn đề annotation discovery phụ thuộc metadata source chứ không chỉ loại proxy.
- Bật `proxyTargetClass` có thể ảnh hưởng toàn bộ cấu hình AOP.

Vì vậy class-based proxy không phải giải pháp tổng quát cho lỗi autodetection. Dùng nó khi có nhu cầu AOP hợp lệ, rồi xác minh JMX registration bằng integration test.

## 13. Kiểm thử chênh lệch giữa proxy và target

Tạo phép thử dùng Spring context đã bật một advice thực sự để bảo đảm bean bị proxy. Một mẫu assertion cho bề mặt JMX:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.aop.support.AopUtils;

void assertBillingJmx(
        Object billingService,
        MBeanServer server
) throws Exception {

    assertTrue(AopUtils.isAopProxy(billingService));

    ObjectName name = new ObjectName(
        "com.example:type=BillingMonitor,name=Primary"
    );

    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);

    boolean found = java.util.Arrays.stream(info.getAttributes())
        .anyMatch(a -> a.getName().equals("PendingInvoiceCount"));

    assertTrue(found);
}
```

Test trên giả định môi trường được cấu hình cố ý tạo AOP proxy. Nó cần test context và exporter đúng instance, không đủ nếu chỉ gọi một class thuần bên ngoài Spring.

Với adapter riêng, có thể test theo hai tầng:

1. Unit test adapter với fake `BillingManagement`: getter/operation ủy quyền đúng.
2. Integration test Spring JMX: adapter được exporter đăng ký, MBeanInfo và invocation có attribute/operation mong đợi.

Đặc biệt nếu dùng Spring Boot auto-configuration, cần bật JMX trong cấu hình test có kiểm soát, ví dụ `spring.jmx.enabled=true`, và tránh ObjectName trùng giữa các test chạy cùng JVM.

## 14. Ma trận nguyên nhân và bằng chứng

| Hiện tượng | Nguyên nhân khả dĩ | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| Bean có trong context nhưng thiếu MBean | Autodetection không chọn bean | `getBean`, `isRegistered`, cấu hình exporter |
| Annotation trên target nhưng runtime class không có | JDK proxy interface che target metadata | `AopUtils.getTargetClass`, metadata trên target |
| MBean có nhưng thiếu attribute | Method không thuộc interface proxy hoặc assembler không chọn | `getMBeanInfo`, method annotation |
| MBean có attribute nhưng đọc thất bại | Proxy method không gọi được hoặc getter lỗi | `getAttribute`, nested exception |
| Khi bật transaction thì MBean biến mất | Proxy strategy/bean lifecycle thay đổi | So sánh proxy type và exporter trước/sau |
| Không có exception khởi động | Bean bị bỏ qua trong autodetect | DEBUG log của exporter, đăng ký thực tế |
| Có `NotCompliantMBeanException` | Bean được chọn nhưng đường export không compliant | Standard MBean/MXBean/assembler |
| Có `InstanceAlreadyExistsException` | Trùng ObjectName | Canonical name, exporter/context khác |

Ma trận này giúp xác định điều cần quan sát, không thay thế việc tái hiện với phiên bản Spring thực tế.

## 15. Nguyên tắc an toàn cho autodetection

Autodetection giúp giảm cấu hình, nhưng cần kiểm soát:

- Không export mọi service nghiệp vụ chỉ vì chúng có public methods.
- Dùng `@ManagedResource` trên thành phần quản trị có bề mặt nhỏ.
- Với POJO, dùng metadata assembler để chỉ xuất method đã đánh dấu.
- Đảm bảo ObjectName duy nhất, ổn định và không lộ dữ liệu nhạy cảm.
- JMX connector phải có security phù hợp; annotation không tạo phân quyền.
- Getter quản trị nên đọc nhanh, không có side effect.
- Operation có tác động cần validation, authorization và audit.
- Có integration test xác nhận `isRegistered`, `MBeanInfo`, `getAttribute` và `invoke`.

Nếu nhiều service dùng proxy do AOP, cân nhắc dùng adapter JMX rõ ràng thay vì phụ thuộc autodetect qua nhiều tầng target/proxy.

## 16. Quy trình điều tra ngắn

```text
@ManagedResource trên implementation
             |
        Bean có trong context?
             |
      Có -> Bean có là proxy?
             |
      Có -> Target class là gì?
             |
  Exporter có đọc target metadata?
             |
       MBean đã đăng ký?
         /          \
        No          Yes
        |            |
  autodetect /     MBeanInfo có
  naming /        attribute?
  registration       |
                    invoke được?
```

Thứ tự chẩn đoán:

1. Kiểm tra bean name và instance từ Spring context.
2. In runtime class, proxy type và target class.
3. Xác nhận annotation nằm ở class nào và metadata source đang dùng.
4. Kiểm tra MBeanExporter có bật autodetection và chọn bean không.
5. Kiểm tra đúng `MBeanServer` và `ObjectName`.
6. Nếu MBean có, kiểm tra bề mặt bằng `getMBeanInfo`.
7. Kiểm tra khả năng gọi getter/operation qua proxy.
8. Nếu cần, chuyển sang explicit export hoặc adapter quản trị riêng.

## 17. Ghi nhớ

**JDK dynamic proxy thường chỉ cho thấy interface của nó; `@ManagedResource` nằm trên target implementation không tự được sao chép lên proxy interface/runtime class.** Bởi vậy một đường autodetection chỉ xem proxy có thể bỏ qua annotation, dù code gốc vẫn đúng. Spring có thể khôi phục target metadata tùy cấu hình, nên hãy xác minh trên thực tế. Phân biệt detection với invocation, sử dụng `AopUtils.getTargetClass` và `MBeanServer.getMBeanInfo` để chẩn đoán, và ưu tiên JMX adapter chuyên biệt khi muốn ranh giới quản trị ổn định.
