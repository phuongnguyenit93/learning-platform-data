# Bean không xuất hiện trong MBeanServer — Chẩn đoán Spring Framework JMX

## Mục tiêu học tập

Bài này hướng dẫn chẩn đoán trường hợp một Spring bean hoặc một MBean dự kiến xuất hiện trong JMX nhưng không thể tìm thấy trên JConsole hay bằng MBeanServer API. Sau bài học, bạn có thể:

- Phân biệt Spring bean nằm trong ApplicationContext với MBean được đăng ký bằng ObjectName.
- Khoanh vùng lỗi ở component scanning, bean lifecycle, JMX exporter, assembler, naming strategy, registration policy, AOP proxy, MBeanServer hoặc JMX client.
- Sử dụng isRegistered, queryNames, getMBeanInfo và getAttribute để kiểm tra kết quả thực tế.
- Hiểu sự khác biệt giữa Standard MBean, MXBean, DynamicMBean và annotation-driven Spring JMX.
- Viết integration test chống tái phát và giữ access/security của JMX remote ở mức phù hợp.

## 1. Triệu chứng cần làm rõ

Giả sử ứng dụng Spring có class:

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=QueueMonitor,name=outbox")
public class QueueManagement {
    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
~~~

Ứng dụng vẫn khởi động, nhưng JConsole không hiển thị MBean com.example.shop.orders:type=QueueMonitor,name=outbox.

Chỉ từ triệu chứng đó chưa thể khẳng định lỗi nằm ở annotation. Có nhiều khả năng:

1. Class không được Spring tạo thành bean.
2. Bean được tạo nhưng không có exporter chọn nó.
3. Exporter không hiểu annotation hoặc không tự phát hiện resource.
4. Bean không tuân theo JMX management contract đang sử dụng.
5. ObjectName được tạo khác với tên người dùng tìm.
6. Hai exporter đăng ký trùng ObjectName và registration thất bại hoặc bị bỏ qua.
7. Exporter sử dụng MBeanServer khác với client đang quan sát.
8. MBean được đăng ký nhưng đã unregister khi context đóng.
9. Spring AOP proxy khiến metadata hay method không được xử lý như dự đoán.
10. JMX remote connector, quyền truy cập hoặc kết nối sai JVM khiến client không thấy resource.

Điều cần làm là kiểm tra theo thứ tự từ nơi tạo bean đến nơi client truy vấn.

## 2. Phân biệt Spring bean và MBean

Spring ApplicationContext quản lý objects, dependencies, scopes và lifecycle. JMX MBeanServer là registry cho các management objects, được truy vấn qua ObjectName.

~~~text
@Configuration / @Component / XML definition
        |
        v
Spring ApplicationContext
        |
        v
Spring bean / AOP proxy
        |
        v
MBeanExporter + assembler + naming
        |
        v
MBeanServer.registerMBean(...)
        |
        v
ObjectName trong JMX registry
        |
        v
JConsole / custom client
~~~

Một Spring bean có thể tồn tại mà chưa được đăng ký qua JMX. Ngược lại, JVM platform MBeans như java.lang:type=Memory có thể được Java runtime đăng ký độc lập với component scanning của ứng dụng.

Tên Spring bean, chẳng hạn queueManagement, không phải ObjectName. ObjectName là định danh JMX như com.example.shop.orders:type=QueueMonitor,name=outbox. Hai tên phục vụ hai namespace khác nhau.

## 3. Bước đầu tiên: đang nhìn đúng JVM chưa?

Khi trên máy có nhiều Java processes hoặc Kubernetes có nhiều pods, việc kết nối nhầm tiến trình là nguyên nhân rất dễ bị bỏ qua.

~~~text
orders-service JVM    -> QueueMonitor có thể tồn tại
payment-service JVM   -> Không có QueueMonitor của orders
IDE test runner JVM   -> MBeanServer riêng
~~~

Hãy xác định PID, tên ứng dụng, pod/container và management connector thực sự được client dùng. Cùng một ObjectName có thể tồn tại ở nhiều JVM độc lập mà không trùng registration, vì registry thuộc từng MBeanServer.

Nếu đang kiểm tra JConsole, xác nhận nó kết nối tới JVM phù hợp. Nếu kiểm tra remote, xác nhận địa chỉ, cổng, host advertised qua RMI và danh tính client theo cấu hình được cho phép.

Không tắt authentication hoặc TLS chỉ để làm kết nối thành công. Sự cố quyền hoặc network cần xử lý ở đúng lớp, không bằng cách giảm bảo mật.

## 4. Kiểm tra trực tiếp MBeanServer

Nếu có quyền chạy đoạn code chẩn đoán trong JVM, bắt đầu bằng platform MBeanServer:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.shop.orders:type=QueueMonitor,name=outbox");

System.out.println("Registered: " + server.isRegistered(name));
~~~

Kết quả false chỉ có nghĩa ObjectName chưa được đăng ký trong server đang được hỏi. Nó không chứng minh không có MBean ở một MBeanServer khác.

Spring có thể được cấu hình sử dụng một custom MBeanServer:

~~~java
@Bean
MBeanExporter exporter(MBeanServer server, QueueMonitor monitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    // Configured export mapping / assembler is required.
    return exporter;
}
~~~

Đoạn trên chỉ minh họa việc inject đúng server; một exporter thực sự cần được cấu hình thêm mapping hoặc autodetection phù hợp. Khi debug, hãy lấy chính MBeanServer bean đã được exporter sử dụng thay vì tự giả định platform server luôn là nơi đăng ký.

## 5. Liệt kê ObjectNames thay vì đoán tên

ObjectName có domain và key properties. Nếu tên do naming strategy tạo ra khác dự kiến, việc kiểm tra một ObjectName cố định có thể trả false dù MBean tồn tại dưới tên khác.

~~~java
import java.util.Set;
import javax.management.ObjectName;

Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.shop.*:*"), null);

names.stream()
        .map(ObjectName::getCanonicalName)
        .sorted()
        .forEach(System.out::println);
~~~

Pattern com.example.shop.*:* tìm domain có tiền tố com.example.shop. và không bao gồm domain chính xác com.example.shop. Nếu chưa biết domain, có thể dùng queryNames(null, null) rồi lọc kết quả, nhưng hạn chế in nhiều MBeans không liên quan.

Những sai lầm hay gặp:
- Nhầm com.example.shop với com.example.shop.orders.
- Nhầm Spring bean name với JMX ObjectName.
- Bỏ hoặc đổi một key property như name hay type.
- Tên được xây dựng bằng naming strategy thay vì lấy từ annotation.
- Truy vấn ObjectName trong custom MBeanServer khác.

ObjectName phải có cú pháp hợp lệ. Nếu giá trị chứa ký tự đặc biệt, cân nhắc ObjectName.quote hoặc builder thích hợp. Lỗi tên có thể gây MalformedObjectNameException trước khi registration.

## 6. Bean có nằm trong ApplicationContext không?

Xác minh bean đã được Spring tạo:

~~~java
import org.springframework.context.ApplicationContext;

public final class SpringBeanInspector {
    public static void inspect(ApplicationContext context) {
        for (String name :
                context.getBeanNamesForType(QueueManagement.class)) {
            System.out.println(name);
        }
    }
}
~~~

Nếu danh sách rỗng, kiểm tra:
- Class có @Component, @Service hoặc @Bean definition phù hợp không.
- Component scan có bao gồm package chứa bean không.
- @Profile hoặc @Conditional có loại bean theo cấu hình hiện tại không.
- Configuration class chứa @Bean có được import không.
- Bean được tạo bằng new ngoài Spring thay vì container quản lý không.
- Bean thuộc parent hay child context nào.
- Bean khởi tạo thất bại hoặc chưa được tạo ở lifecycle thời điểm kiểm tra không.

Ví dụ sai phạm vi:

~~~java
@SpringBootApplication(scanBasePackages = "com.example.shop.web")
public class ShopApplication {}
~~~

Nếu QueueManagement ở com.example.shop.orders.management thì scan package com.example.shop.web không bao phủ nó.

Một điểm tinh tế: getBeanNamesForType của concrete class có thể bị ảnh hưởng khi bean được JDK dynamic proxy. Nếu nghi ngờ AOP, tìm theo bean name hoặc interface có sẵn rồi kiểm tra target class. Không kết luận bean vắng mặt chỉ từ một lookup theo concrete type.

## 7. Có exporter hoặc registration mechanism chưa?

Annotation chỉ khai báo metadata. Việc xuất hiện trong MBeanServer cần registration.

Các đường đi phổ biến:

| Cơ chế | Ý nghĩa |
|---|---|
| MBeanExporter.setBeans | Export mappings tường minh |
| AnnotationMBeanExporter | Export annotation-driven Spring resources |
| MetadataMBeanInfoAssembler | Tạo MBeanInfo từ metadata source |
| AnnotationJmxAttributeSource | Đọc @ManagedResource và method annotations |
| MBeanServer.registerMBean | Registration thủ công |
| Spring Boot JMX integration | Tùy version/auto-configuration |
| JVM platform management | Runtime tự đăng ký platform MBeans |

Nếu ứng dụng có annotation nhưng không cấu hình exporter phù hợp, bean không tự động biến thành MBean. Nếu thêm exporter mới khi một exporter khác đã tồn tại, có nguy cơ đăng ký trùng.

Trước khi sửa, xác định exporter bean nào hiện chạy, autoconfiguration nào được bật, nó dùng MBeanServer nào và mode nào.

## 8. Ví dụ đăng ký Standard MBean bằng Spring

Management interface:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
}
~~~

Implementation:

~~~java
public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 12;
    }
}
~~~

Nếu QueueMonitor là Spring bean, có thể export instance đó:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
MBeanExporter queueExporter(QueueMonitor monitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.shop.orders:type=QueueMonitor,name=outbox",
        monitor));
    return exporter;
}
~~~

Không tạo new QueueMonitor() thứ hai trong exporter nếu ứng dụng nghiệp vụ dùng một singleton khác. Hai objects khác nhau sẽ có state khác nhau khiến người vận hành hiểu sai.

Standard MBean theo convention có interface ClassNameMBean. Nếu object không đáp ứng contract, có thể gặp NotCompliantMBeanException. MXBean và DynamicMBean có những quy tắc riêng.

## 9. Exporter có thực sự chọn bean?

Một exporter có thể chỉ được cấu hình explicit mapping:

~~~java
exporter.setBeans(Map.of(
    "com.example.shop.orders:type=QueueMonitor,name=outbox",
    monitor));
~~~

Khi đó bean khác không tự xuất hiện chỉ vì có @ManagedResource, trừ khi có một cơ chế autodetection phù hợp đang hoạt động.

Spring JMX hỗ trợ các ý tưởng mode:

~~~text
AUTODETECT_NONE
AUTODETECT_MBEAN
AUTODETECT_ASSEMBLER
AUTODETECT_ALL
~~~

AUTODETECT_ASSEMBLER cho phép AutodetectCapableMBeanInfoAssembler quyết định Spring bean nào có managed-resource metadata thích hợp. MetadataMBeanInfoAssembler với AnnotationJmxAttributeSource là cấu hình phổ biến.

Một method gắn @ManagedAttribute nhưng class thiếu @ManagedResource có thể không được chọn bởi metadata-based resource detection. Điều kiện thực tế phụ thuộc assembler; cần kiểm tra config/version đang dùng.

Nếu bean không được chọn, sửa mapping hoặc selection criteria; việc đổi domain không làm exporter bỗng phát hiện bean.

## 10. Annotation và assembler

Một annotation-driven management bean:

~~~java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox",
    description = "Order queue monitor")
public class QueueManagement {
    @ManagedAttribute(description = "Pending jobs")
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation
    public void resetStatistics() {
        // Reset diagnostic counters only.
    }
}
~~~

Các thành phần cần tương thích:
- @ManagedResource: resource-level metadata.
- @ManagedAttribute: getter/setter metadata.
- @ManagedOperation: operation metadata.
- AnnotationJmxAttributeSource: nhận annotation.
- MetadataMBeanInfoAssembler: tạo metadata JMX.
- MetadataNamingStrategy: suy ra ObjectName.
- MBeanExporter: đăng ký.

Nếu bean có mặt nhưng không thấy MBean, hãy kiểm tra resource annotation và exporter. Nếu MBean có mặt nhưng attribute/operation thiếu, hãy kiểm tra metadata assembler, interface, proxy và MBeanInfo.

Đừng khẳng định mọi export path sẽ tự hợp nhất management interface và annotation. Standard MBean interface, MXBean contract và Spring annotation metadata có thể mang những surface khác nhau; cần chọn một contract chính cho mỗi MBean.

## 11. Ví dụ annotation-aware configuration

Một cấu hình minh họa với Spring Framework:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy namingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter mbeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
~~~

Đây là một cách minh họa nối nguồn metadata, assembler, naming và exporter. Kiểm tra Spring API/version; không thêm cấu hình này khi ứng dụng đã có AnnotationMBeanExporter/auto-config cung cấp cùng chức năng. Chỉ dùng một registration owner cho một ObjectName.

## 12. Registration có bị xung đột không?

Một ObjectName chỉ được một MBean sử dụng trong cùng server. Hai exporters cố đăng ký cùng tên có thể gây InstanceAlreadyExistsException.

~~~text
Exporter A --> com.example.shop.orders:type=Queue,name=outbox
Exporter B --> com.example.shop.orders:type=Queue,name=outbox
                                            |
                                            v
                                      conflict
~~~

Spring RegistrationPolicy có những lựa chọn:

| Policy | Khi tên đã tồn tại | Ý nghĩa |
|---|---|---|
| FAIL_ON_EXISTING | Báo lỗi | Dễ phát hiện trùng |
| IGNORE_EXISTING | Giữ MBean cũ | Bean mới có thể không được đăng ký |
| REPLACE_EXISTING | Thay MBean cũ | Có thể gây gián đoạn và mất metadata cũ |

Nếu IGNORE_EXISTING đang hoạt động, isRegistered(name)==true không chứng minh bean mới là object đã đăng ký. Cần so sánh MBeanInfo, operations và startup logs.

Đừng bật REPLACE_EXISTING để che conflict; nó có thể thay registration thuộc component khác và không mặc định rollback nguyên tử khi thất bại.

## 13. Spring AOP proxy có làm khác contract không?

Bean chịu @Transactional, @Cacheable hoặc security advice có thể là JDK dynamic proxy hoặc CGLIB proxy. JDK proxy chỉ expose các interface methods; concrete method có annotation JMX nhưng không ở interface có thể không invoke được qua proxy.

Kiểm tra runtime:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("queueManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
~~~

Không unwrap target để export trực tiếp nếu điều đó bỏ qua transaction, security hay caching advice.

Một management adapter tách biệt thường giúp giữ API quản trị rõ:

~~~java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderManagement {
    private final OrderService service;

    public OrderManagement(OrderService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return service.pendingCount();
    }
}
~~~

Adapter gọi service qua interface Spring proxy. Tuy nhiên chính adapter cũng có thể bị proxy nếu pointcut rộng, nên phải kiểm tra runtime và MBeanInfo. Nếu getter gọi SQL nặng, JMX polling có thể tạo tải; nên dùng snapshot/counter rẻ khi phù hợp.

## 14. MBean từng xuất hiện rồi biến mất?

Một MBean có thể được unregister khi:
- ApplicationContext đóng.
- Exporter cleanup registrations do nó sở hữu.
- Hot reload/devtools thay context.
- Test context teardown.
- Module/component shutdown.
- Mã application gọi unregisterMBean.
- Exporter khác thay registration.

Nếu sự cố chỉ xuất hiện sau restart hoặc shutdown/redeploy, tập trung vào lifecycle. Đừng chỉ lấy một snapshot isRegistered tại startup rồi coi MBean tồn tại suốt vòng đời.

Kiểm tra logs khởi tạo/đóng context, số MBeanServers, các exporters có cùng ObjectName và quy tắc cleanup. Trong tests nên dùng server riêng và unregister sau mỗi case.

## 15. JConsole không thấy nhưng server đã có MBean

Khi code nội bộ xác nhận isRegistered(name)==true mà JConsole vẫn không thấy:

1. JConsole có đúng PID/JVM không?
2. Server mà exporter đăng ký có phải server JConsole đọc không?
3. Domain/ObjectName có đúng không?
4. Tab MBeans đã cập nhật chưa?
5. Remote connector có kết nối thành công không?
6. Client có quyền đọc metadata/attribute không?
7. MBean đã unregister giữa hai lần quan sát chưa?

Nếu JMX remote không kết nối, điều tra authentication, TLS, RMI registry/server port và advertised hostname. Bật JMX export trong Spring không tự mở remote connector; quản lý remote là việc độc lập.

Không sửa source annotation khi lỗi thực tế thuộc network hoặc client identity.

## 16. Spring Boot và Actuator

Trong Spring Boot có thể cùng tồn tại:
- JVM platform MBeans.
- Custom Spring @ManagedResource MBeans.
- Library MBeans.
- Actuator endpoints exposed via JMX.

Các cấu hình management.endpoints.jmx.exposure.* chủ yếu điều khiển Actuator JMX endpoints, không trực tiếp là allowlist cho toàn bộ custom MBeans. HTTP /actuator/health hoạt động không có nghĩa custom QueueManagement đã được export.

Thuộc tính spring.jmx.enabled và export auto-configuration phải được hiểu theo Spring Boot version. Trước khi thêm exporter thủ công, kiểm tra exporter đã được framework tạo chưa. Hai exporters cùng đăng ký một ObjectName thường là lỗi cấu hình.

## 17. Đọc MBeanInfo để xác định contract thực

Khi isRegistered(name) đã true:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class MetadataInspector {
    public static void inspect() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=Queue,name=outbox");

        if (!server.isRegistered(name)) {
            System.out.println("No MBean");
            return;
        }

        MBeanInfo info = server.getMBeanInfo(name);
        System.out.println(info.getClassName());

        for (MBeanAttributeInfo a : info.getAttributes()) {
            System.out.printf("%s type=%s readable=%s%n",
                    a.getName(), a.getType(), a.isReadable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.println("OP " + op.getName());
        }
    }
}
~~~

Đây là metadata thật mà JMX client quan sát. Có MBean nhưng thiếu PendingCount nghĩa là cần kiểm tra annotation assembler, interface, getter naming hoặc proxy, không còn là lỗi hoàn toàn không có registration.

Nếu getAttribute ném exception dù metadata có attribute, điều tra lỗi trong getter, Spring AOP, data source hoặc type mapping.

## 18. Bảng quyết định chẩn đoán

| Kiểm tra | Nếu đúng | Nếu sai |
|---|---|---|
| Đúng JVM | Kiểm tra server | Chọn đúng process/pod |
| Bean có trong context | Kiểm tra exporter | Sửa scan/profile/@Bean |
| Exporter có hoạt động | Kiểm tra selection | Cấu hình một exporter phù hợp |
| Bean được chọn | Kiểm tra metadata | Sửa mapping/autodetection |
| Contract compliant | Kiểm tra ObjectName | Sửa Standard/MXBean/assembler |
| ObjectName hợp lệ | Kiểm tra conflict | Sửa naming |
| Không có duplicate conflict | Kiểm tra registration | Sửa owner/policy |
| MBeanServer.isRegistered true | Đọc MBeanInfo | Xem logs/registration |
| Metadata đúng | Kiểm tra invocation | Sửa annotation/interface |
| JConsole đúng server | Xem client auth/UI | Sửa connection/permissions |

Tập trung vào chứng cứ runtime, tránh thay nhiều cấu hình cùng lúc khiến nguyên nhân bị che.

## 19. Thường gặp những exception nào?

| Exception | Gợi ý |
|---|---|
| NotCompliantMBeanException | Bean/proxy không hợp management contract |
| InstanceAlreadyExistsException | ObjectName đã đăng ký |
| MalformedObjectNameException | Cú pháp tên không hợp lệ |
| InstanceNotFoundException | Client gọi tên chưa đăng ký hoặc đã unregister |
| AttributeNotFoundException | MBean có nhưng attribute không tồn tại |
| ReflectionException | JMX operation method/signature không phù hợp |
| MBeanException | Logic MBean ném lỗi |
| Spring BeanCreationException | Bean/exporter/dependency không tạo được |

Đọc nguyên nhân gốc và context của stack trace; không suy luận chỉ từ một dòng exception. Ví dụ, NotCompliantMBeanException không được giải bằng đổi domain; InstanceAlreadyExistsException không được giải bằng thêm @ManagedAttribute.

## 20. Kiểm thử integration để tránh lỗi tái xuất hiện

Một test cần dựng Spring context đúng configuration, dùng MBeanServer riêng để không va chạm tests khác và kiểm tra:

1. Spring bean mong đợi tồn tại.
2. ObjectName mong đợi được đăng ký.
3. MBeanInfo có attribute/operation dự kiến.
4. getAttribute trả kiểu dữ liệu phù hợp.
5. Internal bean không bị expose ngoài ý muốn.
6. Không có duplicate exporter/registration.
7. Context close cleanup đúng MBeans mà nó sở hữu.
8. AOP proxy hoạt động theo contract nếu service có advice.

Ví dụ tạo isolated MBeanServer:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test");
~~~

Để test có ý nghĩa, phải inject server này vào exporter của test context. Chỉ tạo server riêng rồi kiểm tra nó khi exporter vẫn dùng platform server sẽ cho false negative.

Ví dụ assertion sau khi Spring context khởi động:

~~~java
ObjectName name = new ObjectName(
        "com.example.shop.orders:type=Queue,name=outbox");

if (!testServer.isRegistered(name)) {
    throw new AssertionError("MBean missing");
}

Object count = testServer.getAttribute(name, "PendingCount");

if (!(count instanceof Integer)) {
    throw new AssertionError("Unexpected type: " + count);
}
~~~

Cuối test, đóng context và chỉ unregister những registrations thuộc test. Không xóa tùy tiện MBeans do thư viện khác sở hữu.

## 21. Debug logs có kiểm soát

Nếu cần, bật logging cho Spring JMX trong môi trường phù hợp:

~~~yaml
logging:
  level:
    org.springframework.jmx: DEBUG
~~~

Dùng logs để tìm exporter initialization, bean selection, ObjectName, registration errors và cleanup. Message cụ thể có thể thay đổi giữa phiên bản Spring. Không bật DEBUG lâu dài nếu volume lớn hoặc có thông tin nhạy cảm.

## 22. Những sai lầm cần tránh

- Tạo thêm exporter mà chưa biết exporter hiện hữu.
- Đổi proxy strategy toàn ứng dụng khi chỉ sai ObjectName.
- Bật IGNORE_EXISTING để che duplicate.
- Bật REPLACE_EXISTING để chiếm MBean của thành phần khác.
- Nhầm Spring bean name với JMX ObjectName.
- Chỉ kiểm tra platform MBeanServer dù exporter dùng server khác.
- Tin rằng @ManagedResource tự đăng ký MBean không cần exporter.
- Dùng getBeanNamesForType(concrete class) để kết luận bean vắng mặt dù có JDK proxy.
- Dùng HTTP Actuator exposure để sửa lỗi custom JMX MBean.
- Vô hiệu hóa JMX remote authentication để debug.
- Chỉ kiểm tra isRegistered mà không đọc MBeanInfo.
- Đọc các getters nặng thường xuyên để “xác nhận” registration khi hệ thống đang quá tải.

## 23. Bài tập thực hành

**Bài 1 — Không có bean.** Tạo class @Component ở package ngoài component scanning. Xác nhận Spring context chưa có bean; sửa scan và kiểm tra lại. Đừng kết luận JMX thành công chỉ vì bean đã có.

**Bài 2 — Không có exporter.** Tạo @ManagedResource và @ManagedAttribute, xác nhận annotations không tự register. Thêm đúng một annotation-aware exporter rồi query ObjectName.

**Bài 3 — Trùng ObjectName.** Trong test, đăng ký hai MBeans cùng tên và quan sát conflict. So sánh FAIL_ON_EXISTING với IGNORE_EXISTING và đọc MBeanInfo để biết implementation nào còn được expose.

**Bài 4 — Sai server.** Export bean vào custom test MBeanServer, thử isRegistered trên test server và platform server; giải thích kết quả khác nhau.

**Bài 5 — AOP proxy.** Cho bean quản trị bị JDK dynamic proxy; kiểm tra AopUtils, interface methods và MBeanInfo. Thảo luận phương án adapter.

**Bài 6 — Lifecycle.** Khởi động rồi đóng Spring context. Kiểm tra registration biến mất đúng theo owner, không ảnh hưởng MBeans khác.

## 24. Câu hỏi tự kiểm tra

**Có @ManagedResource là chắc chắn đã register?** Không. Cần Spring bean và exporter phù hợp.

**isRegistered false trên platform server chứng minh mọi server đều không có MBean?** Không. Có thể dùng custom MBeanServer.

**Có MBean nhưng thiếu PendingCount là lỗi gì?** Thường phải kiểm tra management metadata/interface/assembler và getter.

**JDK proxy có thể ảnh hưởng JMX?** Có. Interface method exposure và annotation lookup có thể khác target implementation.

**Vì sao IGNORE_EXISTING dễ gây hiểu nhầm?** Vì nó có thể giữ MBean cũ mà bỏ qua bean mới dưới cùng ObjectName.

**Spring Boot Actuator JMX exposure điều khiển tất cả custom MBeans?** Không. Đây là cấu hình cho Actuator JMX endpoints.

**Có cần test MBeanInfo?** Có. Nó cho biết contract client thực sự nhìn thấy.

## 25. Ghi nhớ

- Bắt đầu từ đúng JVM, MBeanServer và ObjectName.
- Xác nhận Spring bean tồn tại, sau đó xác nhận exporter có chọn bean.
- Phân biệt metadata annotation, Standard/MXBean interface và registration.
- Kiểm tra duplicate, AOP proxy và lifecycle trước khi sửa cấu hình diện rộng.
- Đọc MBeanInfo để xác minh attribute/operation.
- Viết integration tests cho sự hiện diện, absence, kiểu dữ liệu và cleanup.
- Giữ remote JMX được bảo vệ; không mở rộng exposure chỉ để chẩn đoán.

## 26. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — AnnotationMBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — ObjectName: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
