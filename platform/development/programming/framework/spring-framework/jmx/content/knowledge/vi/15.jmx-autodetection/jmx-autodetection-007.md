# Target-class proxy khi cần giữ metadata JMX

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao proxy của Spring AOP có thể ảnh hưởng đến việc phát hiện \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` khi export JMX.
- Phân biệt **JDK dynamic proxy** và **class-based proxy** (proxy dựa trên lớp đích, thường qua CGLIB).
- Hiểu ý nghĩa của \`proxyTargetClass = true\` và các giới hạn của nó.
- Thiết kế JMX management interface ổn định, kể cả khi service nghiệp vụ dùng \`@Transactional\`, \`@Async\` hoặc Spring AOP.
- Kiểm chứng metadata thực sự được công bố bằng \`MBeanServer.getMBeanInfo(...)\`, thay vì chỉ suy luận từ annotation trong source.
- Phát hiện lỗi khi thay đổi chiến lược proxy khiến MBean mất attribute/operation hoặc không được autodetect.

## 1. Vấn đề: bean Spring ở runtime có thể là proxy

Khi ứng dụng sử dụng Spring AOP, Spring có thể trả về một **proxy** thay vì đối tượng target trực tiếp. Proxy đứng trước target để áp dụng advice như transaction, logging hoặc security.

Ví dụ:

\`\`\`java
@Service
@Transactional
public class PaymentService {
    public void processPayment() {
        // ...
    }
}
\`\`\`

Nếu cấu hình AOP phù hợp, bean mà ApplicationContext cung cấp có thể là proxy. Điều này tạo ra hai lớp khái niệm:

\`\`\`text
Spring ApplicationContext
        |
        v
Proxy object được quản lý
        |
        | method call / advice
        v
Target object: PaymentService
\`\`\`

Trong lúc đó, thông tin JMX có thể được khai báo trên target class:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Payments,name=Primary"
)
public class PaymentService {
    @ManagedAttribute
    public int getPendingPayments() {
        return 0;
    }
}
\`\`\`

Nếu exporter/autodetection hoặc metadata assembler nhìn một kiểu Java khác với kiểu chứa annotation, nó có thể không tìm đúng resource hoặc không công bố các method mong đợi.

**Điểm quan trọng:** Việc class gốc có \`@ManagedResource\` chưa đủ để kết luận MBean được đăng ký và metadata chính xác. Phải hiểu proxy và kiểm chứng MBean thực tế.

## 2. JDK dynamic proxy và class-based proxy

Spring AOP thường có hai nhóm proxy:

| Tiêu chí | JDK dynamic proxy | Class-based proxy |
|---|---|---|
| Cấu trúc | Proxy triển khai một hoặc nhiều interface | Proxy là subclass của target class khi có thể |
| Khi dùng | Thường được chọn khi có interface và cấu hình không buộc class proxy | Khi bật \`proxyTargetClass\` hoặc cần proxy theo lớp |
| Runtime class | Không phải subclass trực tiếp của target implementation | Thường là subclass sinh ra từ target class |
| Method hiện ra | Chủ yếu những method có trên các interface proxy | Những method có thể proxy trên class target |
| Tác động JMX có thể gặp | Annotation trên target class/method không nằm trên interface proxy có thể cần xử lý target metadata | Khả năng nhìn class/method của target trực tiếp hơn trong một số cấu hình |
| Giới hạn | Interface không khai báo method thì proxy không có method đó | Không proxy được final class hoặc final method theo cách subclass |

**Không nên kết luận rằng JDK proxy luôn làm JMX thất bại hoặc class-based proxy luôn giải quyết mọi vấn đề.** Spring Framework có cơ chế nhận diện target class và metadata trên proxy trong nhiều trường hợp. Kết quả cuối cùng còn phụ thuộc exporter, assembler, naming strategy, advisor và cách ứng dụng cấu hình bean.

## 3. Vì sao metadata JMX có thể bị ảnh hưởng?

Xét một target:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=JobService,name=Primary"
)
public class JobServiceImpl implements JobService {

    @ManagedAttribute
    public int getRunningJobs() {
        return 3;
    }

    @ManagedOperation
    public void resetStats() {
        // ...
    }
}
\`\`\`

Interface:

\`\`\`java
public interface JobService {
    void executeJob();
}
\`\`\`

Khi dùng JDK proxy, object proxy thường triển khai \`JobService\`, trong khi \`getRunningJobs()\` và \`resetStats()\` không xuất hiện trên interface đó. Tùy cách Spring JMX xử lý target class và invocable methods, exporter có thể gặp khó khăn khi công bố hoặc gọi các method chỉ có trên implementation.

Nếu dùng class-based proxy, proxy có thể kế thừa các public, non-final methods của target. Điều này giúp giữ bề mặt method theo class trong nhiều tình huống.

Nhưng cần phân biệt ba vấn đề:

1. **Autodetection:** Spring có phát hiện resource có \`@ManagedResource\` hay không?
2. **Metadata assembly:** MBean có công bố đúng attributes và operations không?
3. **Invocation:** Khi client gọi operation hoặc đọc attribute, lời gọi có tới method đúng không?

Thay proxy strategy có thể ảnh hưởng khác nhau đến từng vấn đề. Vì vậy cần kiểm tra đủ ba lớp.

## 4. Target class là gì trong Spring AOP?

Target class là kiểu class được proxy đại diện. Spring cung cấp các API hỗ trợ nhận diện:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("jobService");

Class<?> runtimeClass = bean.getClass();
Class<?> targetClass = AopUtils.getTargetClass(bean);

System.out.println("Runtime: " + runtimeClass.getName());
System.out.println("Target: " + targetClass.getName());
System.out.println("Is proxy: " + AopUtils.isAopProxy(bean));
\`\`\`

Ví dụ kết quả có thể là:

\`\`\`text
Runtime: jdk.proxy...$Proxy...
Target: example.jmx.JobServiceImpl
Is proxy: true
\`\`\`

hoặc với class-based proxy:

\`\`\`text
Runtime: example.jmx.JobServiceImpl$$SpringCGLIB$$...
Target: example.jmx.JobServiceImpl
Is proxy: true
\`\`\`

Tên runtime proxy là chi tiết triển khai có thể thay đổi theo Java/Spring version. Không viết JMX naming scheme dựa vào chuỗi class name sinh ra của proxy.

**Quan trọng:** \`AopUtils.getTargetClass(...)\` giúp chẩn đoán hoặc lấy target type nhưng việc gọi API đó không tự thay đổi cách exporter công bố metadata. Cấu hình export vẫn cần được xác nhận riêng.

## 5. Khi nào cân nhắc target-class proxy?

Target-class proxy hữu ích khi:

- Các method JMX được annotate trên concrete target class và không có trong interface của bean.
- Bạn cần Spring AOP áp dụng lên những method có thể proxy của concrete class.
- Một số cơ chế reflection/metadata discovery trong ứng dụng đang dựa vào class thực tế.
- Chuyển từ JDK proxy sang class proxy giúp exporter nhận diện hoặc gọi đúng method quản trị, và điều này đã được kiểm chứng bằng integration test.

Để buộc class-based proxy, Spring có những cấu hình như:

\`\`\`java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
\`\`\`

Nếu ứng dụng chủ yếu sử dụng transaction AOP, có thể dùng:

\`\`\`java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class TransactionConfiguration {
}
\`\`\`

Lưu ý \`proxyTargetClass\` áp dụng cho cơ chế proxy tương ứng và có thể ảnh hưởng đến nhiều beans trong context. Đừng bật chỉ vì có một warning JMX khi chưa xác định nguyên nhân.

Trong Spring Boot, chiến lược proxy còn bị chi phối bởi auto-configuration và properties liên quan. Hãy kiểm tra runtime proxy thực tế thay vì chỉ dựa vào một annotation có mặt trong source.

## 6. Ví dụ ứng dụng: managed bean có proxy

Ta có interface nghiệp vụ:

\`\`\`java
package example.jmx;

public interface QueueService {
    void submit(String jobId);
}
\`\`\`

Implementation:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "learning.jmx:type=QueueService,name=Primary",
    description = "Queue management"
)
public class QueueServiceImpl implements QueueService {

    private final AtomicInteger pending = new AtomicInteger();

    @Override
    @Transactional
    public void submit(String jobId) {
        pending.incrementAndGet();
    }

    @ManagedAttribute(description = "Pending job count")
    public int getPendingJobs() {
        return pending.get();
    }

    @ManagedOperation(description = "Reset counters")
    public void resetCounters() {
        pending.set(0);
    }
}
\`\`\`

Ở đây \`@ManagedAttribute\` và \`@ManagedOperation\` nằm trên implementation, không phải interface \`QueueService\`.

Nếu ứng dụng sử dụng interface-based proxy, cần kiểm chứng liệu exporter có phát hiện và expose được hai management methods hay không. Cấu hình class-based proxy có thể hữu ích, nhưng một lựa chọn kiến trúc khác là tách hẳn JMX facade để không phụ thuộc proxy strategy của service.

### Cấu hình Spring với class-based proxy

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan("example.jmx")
@EnableMBeanExport
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ApplicationConfiguration {
}
\`\`\`

Để thực sự tạo transaction proxy trong ví dụ sử dụng \`@Transactional\`, ứng dụng cần enable transaction management và có transaction infrastructure phù hợp. \`@EnableAspectJAutoProxy\` riêng lẻ không tự đảm bảo \`@Transactional\` được xử lý.

Bạn có thể thay bằng hoặc bổ sung cấu hình transaction tương ứng trong ứng dụng:

\`\`\`java
@EnableTransactionManagement(proxyTargetClass = true)
\`\`\`

Chỉ cần dùng các annotation/configuration liên quan với AOP features đang sử dụng. Mục tiêu của ví dụ là cho thấy **proxy target class được cấu hình ở tầng AOP/transaction**, còn JMX exporter đọc metadata ở tầng quản trị.

## 7. Cách đáng tin cậy hơn: management facade không bị proxy nghiệp vụ chi phối

Trong những hệ thống lớn, một lựa chọn rõ ràng là tách giao diện quản trị khỏi service nghiệp vụ.

Service:

\`\`\`java
public interface QueueService {
    void submit(String jobId);
    int pendingCount();
}
\`\`\`

Service implementation có thể được proxy:

\`\`\`java
@Service
public class QueueServiceImpl implements QueueService {
    // Business logic; có thể có @Transactional hoặc AOP
}
\`\`\`

Facade:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Queue operational view"
)
public class QueueManagement {

    private final QueueService service;

    public QueueManagement(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void refreshStatus() {
        // Một thao tác quản trị phù hợp, nếu cần.
    }
}
\`\`\`

Cấu hình bean:

\`\`\`java
@Bean
QueueManagement queueManagement(QueueService queueService) {
    return new QueueManagement(queueService);
}
\`\`\`

Với cách này:

- MBean metadata nằm ở một class quản trị riêng, dễ đọc.
- Service bên dưới được proxy theo nhu cầu nghiệp vụ.
- ObjectName và tên JMX attributes/operations ít phụ thuộc vào refactor service.
- Có thể kiểm soát rõ những operation nào được công bố.
- Không cần đổi proxy strategy toàn ứng dụng chỉ để giữ JMX annotations trên service.

Nếu thao tác JMX cần đi qua transactional service, facade gọi service proxy để advice vẫn được áp dụng đúng.

## 8. Kiểm chứng metadata thực tế qua MBeanServer

Dù chọn JDK proxy, class-based proxy hay facade, hãy kiểm tra MBean đã được export:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "learning.jmx:type=QueueService,name=Primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

Kỳ vọng với QueueServiceImpl:

\`\`\`text
Attribute: PendingJobs
Operation: resetCounters
\`\`\`

Kết quả thực tế phụ thuộc exporter, proxy và metadata assembly. Nếu không thấy, kiểm tra logs và runtime configuration thay vì giả định việc có annotation trong source đủ để export.

### Kiểm tra invoke

\`\`\`java
Object value = server.getAttribute(name, "PendingJobs");

server.invoke(
        name,
        "resetCounters",
        new Object[0],
        new String[0]
);
\`\`\`

Đoạn code chỉ nên chạy trên test instance hoặc môi trường kiểm soát; operation resetCounters gây thay đổi state.

**Phân biệt:** \`ManagementFactory.getPlatformMBeanServer()\` lấy server của JVM hiện tại. Một client chạy trong JVM khác phải kết nối bằng JMX connector và sử dụng \`MBeanServerConnection\`. Cũng cần bảo đảm exporter thật sự dùng platform server này.

## 9. Integration test cho chiến lược proxy

Một test có giá trị nên xác nhận **proxy type**, **registration**, **metadata** và **invocation** trong một Spring context thật.

Ví dụ JUnit 5 dạng phác thảo:

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import java.util.Arrays;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class QueueJmxProxyTest {

    @Test
    void exposesManagedMethodsThroughJmx() throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        ApplicationConfiguration.class)) {

            Object bean = context.getBean(QueueService.class);

            System.out.println(
                "Proxy=" + AopUtils.isAopProxy(bean)
            );
            System.out.println(
                "Target=" + AopUtils.getTargetClass(bean)
            );

            MBeanServer server =
                    ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "learning.jmx:type=QueueService,name=Primary"
            );

            assertTrue(server.isRegistered(name));

            boolean hasPendingJobs = Arrays.stream(
                server.getMBeanInfo(name).getAttributes()
            ).anyMatch(a -> "PendingJobs".equals(a.getName()));

            boolean hasResetCounters = Arrays.stream(
                server.getMBeanInfo(name).getOperations()
            ).anyMatch(o ->
                "resetCounters".equals(o.getName())
            );

            assertTrue(hasPendingJobs);
            assertTrue(hasResetCounters);
        }
    }
}
\`\`\`

Nếu cần chắc chắn đây là class-based proxy, có thể dùng:

\`\`\`java
assertTrue(AopUtils.isCglibProxy(bean));
\`\`\`

Nhưng assertion này chỉ hợp lệ khi test **đã cấu hình một advisor thực sự áp dụng cho bean** và có lý do buộc class-based proxy. Nếu không có advice, Spring có thể trả target bean trực tiếp và \`isCglibProxy\` là false dù \`proxyTargetClass=true\` đã được cấu hình.

Đây là lỗi test dễ gặp: \`proxyTargetClass=true\` là chính sách **nếu tạo proxy**, không phải lệnh bắt buộc bọc mọi bean thành proxy.

### Kiểm tra test đầy đủ

Một test tốt nên xác nhận:

1. Bean là Spring-managed bean trong context.
2. Nếu có AOP advisor, kiểm tra proxy type như kỳ vọng.
3. Metadata JMX được nhận diện từ target/interface phù hợp.
4. MBean được đăng ký đúng ObjectName.
5. Attribute và operation có mặt trong \`MBeanInfo\`.
6. Gọi attribute/operation qua JMX thành công.
7. Đóng context, MBean do exporter quản lý được unexport.

## 10. Vì sao proxyTargetClass=true không phải thuốc chữa mọi lỗi?

Một số nguyên nhân khác vẫn khiến MBean không được export:

- Bean không nằm trong ApplicationContext mà exporter quản lý.
- \`@EnableMBeanExport\` hoặc MBeanExporter chưa được bật.
- Exporter dùng autodetect mode không phù hợp.
- Assembler không đọc \`@ManagedResource\`.
- ObjectName bị trùng hoặc sai cú pháp.
- Metadata đặt trên method không hợp lệ với contract.
- MBeanServer mà bạn kiểm tra khác MBeanServer mà exporter đăng ký.
- Method/class final gây giới hạn proxy theo lớp.
- Spring bean có scope, lifecycle hoặc FactoryBean đặc thù.
- Remote JMX client thiếu quyền hoặc không kết nối đúng JVM.

Đổi sang class-based proxy chỉ xử lý một nhóm vấn đề liên quan proxy type/metadata visibility. Nếu nguyên nhân là ObjectName collision hoặc exporter chưa hoạt động, đổi proxy strategy không giải quyết được.

## 11. Final class, final method và proxy theo lớp

Class-based proxy thường dựa trên subclass. Vì vậy:

\`\`\`java
public final class FinalService {
    public void execute() { }
}
\`\`\`

không thể được proxy bằng cách tạo subclass của class final.

Một method final cũng không thể được override để Spring áp dụng advice theo cách subclass thông thường.

Ví dụ:

\`\`\`java
public class QueueService {
    public final void submit(String jobId) {
        // ...
    }
}
\`\`\`

Nếu \`submit\` cần được Spring AOP intercept, một class-based proxy sẽ không có khả năng override method này. Cần cân nhắc interface-based proxy hoặc thay đổi thiết kế, tùy nhu cầu.

Đối với JMX metadata, một method final vẫn có thể là Java method trên target, nhưng quan hệ giữa invocation qua proxy, advice và exporter cần được kiểm tra thực tế. Không suy luận rằng class-based proxy bảo đảm mọi operation chạy advice mong muốn.

## 12. JDK proxy và interface quản trị rõ ràng

Không phải lúc nào cần đổi sang class-based proxy. Nếu service dùng JDK dynamic proxy, có thể thiết kế một management interface phù hợp và cấu hình JMX export để công bố contract đó.

Ví dụ:

\`\`\`java
public interface QueueManagementView {
    int getPendingJobs();
    void resetCounters();
}
\`\`\`

Nếu cần cùng một proxy thực thi các methods này, interface của proxy phải có các methods tương ứng và exporter/assembler được cấu hình phù hợp.

Một cách khác là đăng ký management facade riêng, tránh phức tạp hóa giao diện nghiệp vụ.

**Trade-off thiết kế:**

- JDK dynamic proxy phù hợp khi code đã lấy interface làm boundary và chỉ cần expose methods trong interface.
- Class-based proxy hữu ích khi cần giữ bề mặt concrete class.
- Management facade phù hợp khi JMX contract cần ổn định độc lập với code nghiệp vụ và AOP advice.

Chọn theo yêu cầu vận hành, không chỉ theo việc “JConsole có nhìn thấy method không”.

## 13. Xem metadata khi có AOP advice

Khi debugging, thu thập ba loại thông tin:

**Thông tin bean:**

\`\`\`java
Object bean = context.getBean("queueServiceImpl");

System.out.println(bean.getClass());
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

**Thông tin MBean registration:**

\`\`\`java
System.out.println(server.isRegistered(objectName));
\`\`\`

**Thông tin JMX contract:**

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);
\`\`\`

Nếu bean là JDK proxy và \`MBeanInfo\` thiếu operation mà target có annotation, đó là dấu hiệu cần kiểm tra metadata assembly và invocable method selection.

Nếu MBean không đăng ký, cần đọc exception trong startup logs và kiểm tra exporter trước khi đi sâu vào method metadata.

Nếu MBean đăng ký và MBeanInfo đúng nhưng invocation lỗi, cần xem signature và exception wrapper khi gọi JMX; đồng thời kiểm tra proxy có chuyển lời gọi đúng tới target không.

## 14. Vòng đời và trùng ObjectName trong test

Spring context có thể được tạo nhiều lần trong một JVM, nhất là integration tests.

Khi test cấu hình JMX:

- Dùng một ObjectName ổn định cho mỗi managed resource.
- Tránh để hai context sống đồng thời và đăng ký cùng tên.
- Đóng context sau test để exporter unregister MBean thuộc phạm vi của nó.
- Nếu nhiều test chạy song song, cân nhắc MBeanServer riêng cho test.
- Không đặt \`REPLACE_EXISTING\` chỉ để che xung đột từ test khác.

Một MBeanServer riêng có thể được tạo bằng:

\`\`\`java
MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test.jmx");
\`\`\`

Nếu dùng server này, phải cấu hình exporter tương ứng. Việc tạo server test không tự khiến exporter chuyển đăng ký từ platform server sang nó.

## 15. Vấn đề bảo mật của management methods

Một operation JMX có thể tác động tới trạng thái ứng dụng:

\`\`\`java
@ManagedOperation
public void resetCounters() {
    // ...
}
\`\`\`

Khi dùng proxy và AOP, đừng mặc định mọi advice bảo mật của ứng dụng HTTP hoặc service đều được áp dụng như mong đợi cho một JMX invocation.

Ví dụ một Spring Security HTTP filter không tự động kiểm soát lời gọi trực tiếp qua JMX. Nếu method có method-level security, cần xác minh JMX invocation đi qua proxy/advice đúng. Với class-based proxy, final method cũng có thể làm advice không chạy.

Thiết kế bảo mật theo các lớp:

1. Giới hạn quyền truy cập local/remote JMX connector.
2. Thu hẹp những attributes và operations được export.
3. Kiểm tra tác dụng phụ và xác thực/phân quyền ở tầng phù hợp.
4. Ghi nhận thao tác quản trị nhạy cảm nếu yêu cầu vận hành.
5. Viết integration test xác nhận hành vi thực tế qua JMX, thay vì chỉ kiểm tra method trực tiếp.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Bean có @ManagedResource nhưng MBean không xuất hiện | Exporter/autodetect chưa bật, proxy metadata không được đọc, ObjectName lỗi | Xem exporter, logs và isRegistered |
| MBean xuất hiện nhưng thiếu ManagedAttribute | Getter không được nhận diện qua metadata/proxy | Xem targetClass, assembler và MBeanInfo |
| Operation xuất hiện nhưng invoke thất bại | Method không invocable trên proxy hoặc sai signature | Kiểm tra proxy interfaces/method và exception |
| Bật proxyTargetClass=true mà isCglibProxy vẫn false | Không có advisor áp dụng cho bean | Kiểm tra AOP advice thực sự được tạo |
| JDK proxy chỉ lộ method của interface | Management method chỉ ở implementation | Cân nhắc class proxy, interface phù hợp hoặc facade |
| Class-based proxy không hoạt động | Target class final hoặc cấu hình AOP không phù hợp | Kiểm tra class/method modifiers |
| Transaction advice không chạy qua JMX | Invocation bypass proxy hoặc configuration chưa đúng | Test JMX invocation và transaction boundary |
| MBean đúng nhưng không có quyền remote | JMX connector/auth/network | Kiểm tra connection riêng; không coi là metadata failure |
| Đăng ký trùng ObjectName | Hai context/beans export cùng tên | Kiểm tra owner, lifecycle và naming strategy |
| Đổi Spring bean name làm mất MBean | Naming strategy phụ thuộc bean name | Giữ ObjectName ổn định hoặc migration có chủ đích |

## 17. Bài tập thực hành

### Bài tập 1 — Quan sát proxy type

Tạo một service có interface và một advisor thực sự áp dụng. Chạy hai cấu hình:

- \`proxyTargetClass = false\`
- \`proxyTargetClass = true\`

Dùng \`AopUtils.isJdkDynamicProxy\`, \`AopUtils.isCglibProxy\` và \`AopUtils.getTargetClass\` để so sánh.

Giải thích vì sao không đủ để chỉ kiểm tra class name của bean.

### Bài tập 2 — Annotation nằm trên target class

Đặt \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` trên class triển khai; interface nghiệp vụ chỉ có một method không phải JMX.

Kiểm tra MBean được autodetect và MBeanInfo với hai proxy strategies. Nếu kết quả khác nhau, tìm phần metadata/method đang bị mất rồi thử class-based proxy hoặc management facade.

### Bài tập 3 — Chuyển sang management facade

Tách một managed resource khỏi service nghiệp vụ đã có \`@Transactional\`. Đặt JMX annotations trên facade mới và cho facade gọi service proxy.

So sánh thiết kế này với việc áp dụng \`proxyTargetClass=true\` cho toàn ứng dụng.

### Bài tập 4 — Contract test

Viết integration test xác nhận:

\`\`\`text
ObjectName = learning.jmx:type=QueueService,name=Primary
Attribute  = PendingJobs
Operation  = resetCounters
\`\`\`

Đọc \`MBeanInfo\`, sau đó dùng \`getAttribute\` và \`invoke\` để xác nhận contract.

### Bài tập 5 — Đánh giá rủi ro

Một method JMX quan trọng có \`@ManagedOperation\` và \`@PreAuthorize\`, nhưng khi gọi từ JConsole thì security advice không chạy. Hãy liệt kê các vị trí cần kiểm tra: JMX connector authorization, bean proxy, target method, AOP advisor, final modifiers và call path.

## 18. Checklist khi chọn target-class proxy

Trước khi bật \`proxyTargetClass=true\`, trả lời:

1. Có bằng chứng JDK proxy đang làm metadata/invocation JMX sai không?
2. Annotation nằm trên target class hay interface?
3. Management methods có tồn tại trong interface của JDK proxy không?
4. Runtime bean có thực sự là AOP proxy không?
5. Có final class hoặc final method nào ảnh hưởng đến class proxy không?
6. Thay đổi proxy strategy có tác động đến các beans khác không?
7. MBeanExporter có đúng assembler, naming strategy và autodetect mode không?
8. MBeanServer và ObjectName có đúng không?
9. \`MBeanInfo\` đã thể hiện attributes/operations mong đợi chưa?
10. Có thể dùng management facade để tách JMX contract và business proxy không?

## 19. Ghi nhớ cốt lõi

- **JMX metadata có thể nằm trên target class trong khi Spring bean runtime là proxy.**
- JDK dynamic proxy chủ yếu công bố methods qua interfaces; class-based proxy thường giữ bề mặt concrete class trong những giới hạn của subclass.
- \`proxyTargetClass=true\` chỉ ảnh hưởng cơ chế tạo proxy tương ứng, không tự bật JMX export hoặc tạo proxy khi không có advice.
- Spring JMX có khả năng xử lý target metadata trong nhiều trường hợp; luôn kiểm tra kết quả cuối cùng.
- Muốn giữ contract JMX ổn định, **management facade** là lựa chọn đáng cân nhắc khi service nghiệp vụ có nhiều AOP concerns.
- Dùng \`AopUtils\` để chẩn đoán bean/proxy, \`MBeanServer.isRegistered\` để xác nhận registration và \`MBeanInfo\` để xác nhận attributes/operations.
- Test invocation qua JMX khi thao tác có tác dụng phụ, transaction hoặc security advice.
- Chỉ đổi proxy strategy sau khi xác định nguyên nhân thực tế; proxy không sửa được lỗi ObjectName, exporter hay network.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework API — AopUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework API — EnableAspectJAutoProxy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
