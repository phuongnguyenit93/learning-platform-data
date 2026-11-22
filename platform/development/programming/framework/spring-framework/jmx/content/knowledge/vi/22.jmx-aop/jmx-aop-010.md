# Chẩn đoán bean bị bỏ qua sau khi bật auto-proxy trong Spring Framework JMX

## Mục tiêu

Trong Spring Framework, JMX exporter có thể tự phát hiện bean đủ điều kiện và đăng ký chúng vào MBeanServer. Khi bật AOP auto-proxy — ví dụ thông qua \`@EnableAspectJAutoProxy\`, \`@Transactional\`, \`@Async\` hoặc các advisor do thư viện thêm vào — Spring bean mà exporter nhìn thấy có thể không còn là đối tượng implementation gốc. Nó có thể là **JDK dynamic proxy** hoặc **class-based proxy**. Sự thay đổi này ảnh hưởng đến thông tin kiểu, interface được công bố, metadata annotation và cơ chế introspection của JMX.

Hiện tượng thường gặp: trước khi bật auto-proxy, bean xuất hiện trong JConsole; sau khi bật, MBean biến mất hoặc exporter bỏ qua bean. Đôi khi lỗi là \`NotCompliantMBeanException\`, đôi khi không có lỗi rõ vì bean đơn giản không còn thỏa tiêu chí autodetection. Cần chẩn đoán ở đúng tầng: Spring bean, proxy, MBean exporter, MBeanServer, ObjectName và JMX client.

Sau bài này, bạn có thể:

1. Phân biệt target bean, proxy bean và management interface.
2. Giải thích tại sao JDK proxy có thể che mất class hoặc interface mà JMX cần để nhận diện.
3. Hiểu sự khác biệt giữa Standard MBean introspection và annotation-driven export.
4. Dò bean có bị loại ở bước autodetection, metadata assembly hay registration.
5. Dùng \`AopUtils\`, \`AopProxyUtils\`, \`BeanFactory\` và \`MBeanServer\` để khoanh vùng sự cố.
6. Đánh giá khi nào nên chọn class-based proxy, expose interface phù hợp, export target hay management adapter riêng.
7. Kiểm thử startup, contract và cleanup mà không làm mất Spring AOP advice cần thiết.
8. Tránh nhầm việc MBean không thấy trên JConsole với bean thực sự không tồn tại.

## 1. Nhìn đúng luồng tạo bean và export MBean

Một bean thông thường:

\`\`\`text
Bean definition
     |
     v
Instantiate target class
     |
     v
BeanPostProcessor / AutoProxyCreator
     |
     v
Spring bean exposed to container
     |
     v
MBeanExporter autodetection
     |
     v
MBeanServer.registerMBean(...)
\`\`\`

Khi không có AOP proxy, object cuối cùng thường là implementation. Khi có auto-proxy:

\`\`\`text
Target: InventoryMonitor implements InventoryMonitorMBean
     |
     +── JDK dynamic proxy
     |      implements selected interfaces
     |      runtime class: jdk.proxy... / com.sun.proxy...
     |
     +── CGLIB/class-based proxy
            subclass-like proxy with generated class name
\`\`\`

Exporter có thể thấy proxy thay vì target. Việc JMX có nhận diện bean là MBean không tùy thuộc chỉ vào tên bean Spring mà còn vào kiểu và contract JMX của object được export.

Lưu ý: Spring có những khả năng hỗ trợ proxy/target khi export. Không nên khẳng định mọi JDK proxy đều làm JMX thất bại hoặc mọi CGLIB proxy đều khắc phục. Điều kiện thực tế phụ thuộc phiên bản Spring, MBeanInfoAssembler, exporter mode và interface/annotation của bean.

## 2. Các biểu hiện thường gặp

| Triệu chứng | Giả thuyết cần kiểm tra |
|---|---|
| Trước AOP có MBean, sau AOP không thấy | Proxy thay kiểu/metadata được autodetect |
| Bean vẫn inject vào service, nhưng JMX không có | Bean tồn tại, chỉ bị loại khỏi export |
| Log báo không phải compliant MBean | JMX introspection không tìm được contract trên proxy |
| \`@ManagedResource\` đặt trên class nhưng exporter không nhận | Metadata lookup trên target/proxy hoặc cấu hình assembler chưa phù hợp |
| JConsole thấy MBean nhưng operation thiếu | Exposed interfaces hoặc metadata selection thay đổi |
| Một bean có hai ObjectName bất ngờ | Nhiều exporter/naming strategy |
| JMX chỉ lỗi khi bật \`@Transactional\` | Transaction advisor kích hoạt proxy |
| MBean biến mất sau refresh | Registration lifecycle hoặc ObjectName collision |

Một nguyên tắc chẩn đoán: **bean bị bỏ qua khỏi JMX không có nghĩa bean bị bỏ qua khỏi ApplicationContext**. Phải kiểm tra riêng bean registration và JMX registration.

## 3. JDK dynamic proxy và giới hạn interface

JDK dynamic proxy hoạt động thông qua các interface được chọn để proxy. Nếu implementation có nhiều public method nhưng proxy không expose interface chứa chúng, code bên ngoài chỉ thấy tập method của các interface proxy triển khai.

Ví dụ:

\`\`\`java
public interface WorkerServiceApi {
    void process();
}

public interface WorkerStatusMBean {
    String getState();
}

public class WorkerService
        implements WorkerServiceApi, WorkerStatusMBean {

    @Override
    public void process() {
        // Logic nghiệp vụ.
    }

    @Override
    public String getState() {
        return "RUNNING";
    }
}
\`\`\`

Nếu proxy JDK chỉ công bố \`WorkerServiceApi\`, MBeanServer không thể mặc nhiên coi proxy đó là \`WorkerStatusMBean\`. Tùy cấu hình auto-proxy và Spring exporter, JMX detection có thể không nhận ra interface quản trị hoặc không đăng ký được.

Điều cần xác nhận không phải chỉ là target class implement \`WorkerStatusMBean\`, mà là **object exporter thực sự sử dụng có expose contract quản trị hay không**.

Có thể kiểm tra:

\`\`\`java
Object bean = context.getBean("workerService");
System.out.println(bean.getClass());
System.out.println(Arrays.toString(bean.getClass().getInterfaces()));
System.out.println(bean instanceof WorkerStatusMBean);
\`\`\`

\`getInterfaces()\` trực tiếp trên class không hiển thị toàn bộ interface được kế thừa gián tiếp, vì vậy nên dùng \`instanceof\`, \`AopUtils\` và helper introspection phù hợp để xác nhận contract.

## 4. Class-based proxy có khác biệt gì?

Class-based proxy (thường được mô tả là CGLIB proxy trong Spring) tạo subclass proxy đối với target type khi khả thi. Nó có thể bảo toàn nhiều đặc điểm class-based introspection hơn JDK interface proxy, nhưng cũng có giới hạn:

- Class \`final\` không thể được subclass theo cách thông thường.
- Method \`final\` không thể được override để áp dụng advice.
- Self-invocation có thể đi thẳng vào target method mà không qua proxy advice.
- Annotation và metadata có thể cần lookup target class thay vì chỉ proxy generated class.
- Các kiểu Java đặc biệt hoặc constructor/lifecycle có thể làm behavior khác mong đợi.

Ví dụ cấu hình:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
\`\`\`

Cấu hình này yêu cầu ưu tiên class-based proxy trong phạm vi áp dụng, nhưng **không phải giải pháp mặc định nên dùng chỉ để JMX nhận một bean**. Nó có thể tác động toàn bộ chiến lược proxy trong context, bao gồm cả các bean không liên quan. Với một vấn đề JMX riêng lẻ, management adapter chuyên dụng thường ít ảnh hưởng đến kiến trúc hơn.

## 5. Standard MBean: quy ước tên và management interface

Standard MBean thường có interface tên \`<ImplementationClass>MBean\`:

\`\`\`java
public interface CacheMonitorMBean {
    long getHitCount();
    void resetCounters();
}

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public long getHitCount() {
        return 0L;
    }

    @Override
    public void resetCounters() {
        // Reset.
    }
}
\`\`\`

Khi đăng ký object \`CacheMonitor\` đúng contract, JMX có thể công bố \`HitCount\` attribute và \`resetCounters\` operation.

Tuy nhiên sau auto-proxy, runtime class có thể là generated proxy class, không còn cùng tên \`CacheMonitor\`. Nếu exporter/JMX introspection không nhận diện được interface management theo cách dự kiến, bean có thể bị bỏ qua hoặc đăng ký lỗi.

Điểm quan trọng: \`MBeanExporter\` có cơ chế hỗ trợ xuất bean/proxy theo Spring JMX; không nên bỏ qua nó và áp dụng quy tắc Standard MBean của object thuần một cách máy móc. Hãy chẩn đoán **cơ chế export đang dùng**, không chỉ tên runtime proxy.

## 6. Annotation-driven export: @ManagedResource trên target

Với annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Worker,name=Import")
public class ImportWorkerMonitor {

    @ManagedAttribute
    public String getState() {
        return "RUNNING";
    }
}
\`\`\`

Khi một advisor khiến bean được proxy, annotation có thể nằm trên **target class** còn exporter đang nhận một proxy. Spring annotation assembler có thể hỗ trợ tìm metadata ở target, nhưng khả năng thành công phụ thuộc cấu hình và phiên bản framework. Trường hợp bất thường cần kiểm tra \`AnnotationMBeanExporter\`, \`MetadataMBeanInfoAssembler\`, proxy type và object thực tế.

Không nên thêm \`@ManagedResource\` bừa vào JDK proxy generated class — class đó do framework sinh, không phải nơi bạn kiểm soát source. Nếu JMX metadata nằm trên interface hoặc trên target, phải xác định cơ chế assembler có hỗ trợ vị trí annotation ấy hay không.

## 7. Các bước chẩn đoán theo tầng

### Bước 1 — Bean còn tồn tại trong Spring context không?

\`\`\`java
boolean exists = context.containsBean("importWorkerMonitor");
Object bean = context.getBean("importWorkerMonitor");

System.out.println("exists=" + exists);
System.out.println("type=" + bean.getClass().getName());
\`\`\`

Nếu bean không tồn tại, lỗi là bean registration, component scanning, profile/condition hoặc bean name. Nếu bean tồn tại nhưng không có MBean, chuyển sang các bước tiếp theo; không sửa \`@ComponentScan\` khi chưa biết nguyên nhân.

### Bước 2 — Bean có phải AOP proxy?

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("importWorkerMonitor");

System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("target class: " +
    AopUtils.getTargetClass(bean).getName());
\`\`\`

Kiểm tra thời điểm trước/sau khi bật AOP. Nếu target class giống nhưng runtime bean class đổi, proxy là đầu mối cần điều tra. Tuy nhiên correlation không tự chứng minh nguyên nhân: đồng thời có thể thay exporter/bean definition khi thêm configuration.

### Bước 3 — Proxy expose interface gì?

\`\`\`java
Object bean = context.getBean("importWorkerMonitor");

for (Class<?> iface : bean.getClass().getInterfaces()) {
    System.out.println(iface.getName());
}
\`\`\`

Với management interface:

\`\`\`java
System.out.println(bean instanceof ImportWorkerMonitorMBean);
\`\`\`

Nếu interface bị thiếu, kiểm tra \`ProxyFactory\`, introduction advisors, interface filtering và proxy configuration. Không được ép cast proxy sang interface không tồn tại chỉ vì target implement interface đó.

### Bước 4 — Exporter nào đang hoạt động?

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

String[] names = context.getBeanNamesForType(
    MBeanExporter.class, true, false);

System.out.println(Arrays.toString(names));
\`\`\`

Kiểm tra một hay nhiều exporter, kiểu \`AnnotationMBeanExporter\` hay \`MBeanExporter\`, autodetect mode, explicit mappings, naming strategy và assembler. Nếu exporter không bật hoặc không có bean trong scope, đây không phải lỗi proxy introspection.

### Bước 5 — Đúng MBeanServer chưa?

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=Worker,name=Import");

System.out.println(server.isRegistered(name));
\`\`\`

Nếu exporter dùng custom MBeanServer, truy vấn server đó thay vì platform server. JConsole có thể kết nối qua connector tới registry khác. Một MBean không thấy trên JConsole không chứng minh exporter bỏ qua bean.

### Bước 6 — ObjectName thực tế có thay đổi?

Khi exporter dùng naming strategy dựa trên bean name hoặc metadata, proxy hóa hoặc refactor có thể tác động những giả định đặt tên. Hãy query đúng domain:

\`\`\`java
Set<ObjectName> actual = server.queryNames(
    new ObjectName("com.example.ops:*"), null);
actual.forEach(System.out::println);
\`\`\`

Nếu bean xuất với tên khác, vấn đề là naming chứ không phải autodetection. Với những MBean là contract cho monitoring, dùng ObjectName tường minh khi phù hợp.

### Bước 7 — Registration có lỗi hoặc bị rollback?

Xem log startup của exporter và các exception:

- \`NotCompliantMBeanException\`: object không thỏa contract JMX.
- \`InstanceAlreadyExistsException\`: ObjectName đã có trong server.
- \`MalformedObjectNameException\`: tên không hợp lệ.
- \`BeanCreationException\`: Spring configuration/bean initialization lỗi.
- \`JMException\`, \`MBeanRegistrationException\`: registration thất bại.
- \`IOException\`: có thể đến từ remote connector ở tầng client, không đồng nghĩa local registration lỗi.

Đọc stack trace để biết exporter, bean và server nào thực hiện registration. Không chuyển mọi lỗi thành giả thuyết AOP.

## 8. Autodetection mode ảnh hưởng lựa chọn bean

\`MBeanExporter\` có thể dùng explicit mappings hoặc các chế độ autodetection thích hợp theo API/phiên bản:

| Cách chọn | Điểm cần kiểm tra sau proxy hóa |
|---|---|
| Explicit \`setBeans\` | MBean object có compliant contract không? |
| Standard MBean autodetection | Proxy có interface Standard MBean nhận diện được không? |
| MXBean autodetection | Proxy có expose MXBean interface và kiểu dữ liệu hợp lệ không? |
| Assembler-based autodetection | Assembler có xem target/proxy là ứng viên không? |
| Annotation-based autodetection | Annotation metadata có được tìm thấy ở target không? |

Cần phân biệt **bean bị loại khỏi tập ứng viên** với **bean được chọn nhưng register không thành công**. Trường hợp đầu thường không có ObjectName mới; trường hợp sau có exception hoặc log registration. Điều chỉnh export mode mà không biết bước lỗi có thể làm tăng số bean được export không kiểm soát.

## 9. MBeanInfoAssembler và proxy class

Một \`MBeanInfoAssembler\` tạo metadata attributes/operations cho bean. Một số assembler dựa trên reflection, một số dùng annotation, một số giới hạn method theo interface. Nếu assembler nhận proxy type thay vì target type, metadata có thể không chứa những method mong đợi.

Ví dụ interface-based exposure:

\`\`\`java
public interface WorkerMonitorMBean {
    String getState();
    long getCompletedCount();
}
\`\`\`

Khi exporter dùng management interface được chọn rõ ràng, bề mặt quản trị ổn định hơn so với việc suy đoán từ toàn bộ public methods của target class. Nhưng phải bảo đảm object cuối thực sự expose đúng interface hoặc được wrap/adapter phù hợp.

Nếu dùng \`MetadataMBeanInfoAssembler\` của Spring, cần kiểm tra metadata lookup theo target class và annotations trong phiên bản Spring hiện tại. Đừng trộn nhiều assembler hoặc metadata source mà không hiểu cách chúng quyết định inclusion.

## 10. Giải pháp 1: management adapter riêng, không proxy hóa trực tiếp

Giải pháp thường ít gây tác động nhất là tách management adapter khỏi service nghiệp vụ bị proxy.

\`\`\`text
Spring service target
     |
     v
@Transactional / @Async / AOP proxy
     |
     v
Management adapter (được inject service proxy)
     |
     v
MBeanExporter / AnnotationMBeanExporter
     |
     v
MBeanServer
\`\`\`

Ví dụ:

\`\`\`java
public interface WorkerStatusMBean {
    String getState();
    long getCompletedCount();
}
\`\`\`

\`\`\`java
public class WorkerStatus implements WorkerStatusMBean {

    private final WorkerServiceApi service;

    public WorkerStatus(WorkerServiceApi service) {
        this.service = service;
    }

    @Override
    public String getState() {
        return service.currentState();
    }

    @Override
    public long getCompletedCount() {
        return service.completedCount();
    }
}
\`\`\`

Ở đây \`WorkerServiceApi\` cần định nghĩa những method tương ứng. Adapter không công bố các operation nghiệp vụ nhạy cảm. Có thể đăng ký \`WorkerStatus\` như Standard MBean với ObjectName được chọn rõ ràng:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=WorkerStatus,name=Import");
server.registerMBean(new WorkerStatus(service), name);
\`\`\`

Trong ứng dụng thật, nên để Spring exporter quản lý registration/lifecycle hoặc viết cleanup đối xứng nếu đăng ký thủ công. Không để test hoặc một context khác tự unregister ObjectName thuộc exporter này.

Điểm lợi: service tiếp tục nhận transactional/asynchronous advice qua Spring proxy, còn JMX interface không phụ thuộc vào proxy class của service.

## 11. Giải pháp 2: expose management interface qua proxy

Nếu muốn export chính proxy bean, phải kiểm tra proxy có expose interface quản trị:

\`\`\`java
public interface ImportWorkerMBean {
    String getState();
}
\`\`\`

Implementation:

\`\`\`java
public class ImportWorker implements ImportWorkerMBean, WorkerServiceApi {
    @Override
    public String getState() { return "RUNNING"; }

    @Override
    public void process() { /* ... */ }
}
\`\`\`

Khi dùng JDK proxy, Spring có thể expose các interface phù hợp, nhưng cấu hình AOP cụ thể có thể chọn interface subset. Nếu cần, cấu hình proxy theo cách hỗ trợ interface quản trị, rồi xác nhận:

\`\`\`java
Object proxy = context.getBean("importWorker");
assertTrue(proxy instanceof ImportWorkerMBean);
\`\`\`

Không chỉ dựa vào assert target class implement interface. Đồng thời cần chú ý tên Standard MBean theo convention hoặc dùng \`StandardMBean\` wrapper để chỉ rõ management interface.

## 12. Giải pháp 3: StandardMBean wrapper

Một wrapper có thể chỉ rõ contract khi tên implementation/proxy không phù hợp convention.

\`\`\`java
import javax.management.StandardMBean;

WorkerStatusMBean implementation = new WorkerStatus(service);

StandardMBean exposed =
    new StandardMBean(implementation, WorkerStatusMBean.class);

server.registerMBean(exposed,
    new ObjectName("com.example.ops:type=WorkerStatus,name=Import"));
\`\`\`

Wrapper giúp tách tên runtime implementation khỏi tên management interface. Nó không tự chuyển một object không implement interface thành compliant MBean; đối tượng được truyền phải đáp ứng contract. Wrapper cũng không sửa các vấn đề Spring bean không tồn tại, exporter không bật hoặc sai server.

Nếu dùng MXBean, cần sử dụng quy tắc MXBean hoặc wrapper với cờ MXBean đúng, đồng thời bảo đảm kiểu dữ liệu có Open Type mapping hợp lệ.

## 13. Giải pháp 4: thay đổi proxyTargetClass một cách có chủ đích

Một lựa chọn là:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

Cách này có thể khiến class-based proxy giữ được những đặc điểm class/type cần cho exporter. Nhưng nó tác động rộng đến toàn context, có thể thay đổi khả năng proxy các class final hoặc behavior AOP. Không dùng làm giải pháp đầu tiên nếu lỗi chỉ ở một management bean.

Nên so sánh:
- Interface-based proxy hiện tại có expose management interface không?
- Spring exporter có cơ chế unwrap target hoặc tạo model MBean phù hợp không?
- Adapter riêng có giải quyết vấn đề với phạm vi nhỏ hơn không?
- Có operation nào trên management interface cần chạy qua Spring advice hay không?
- Test startup, JMX contract và transactional/async behavior có còn đúng không?

Nếu điều chỉnh chiến lược proxy, kiểm thử các service AOP liên quan, không chỉ kiểm tra JConsole.

## 14. Vì sao không nên export target thay proxy một cách tùy tiện?

Khi một target bean được Spring proxy để áp dụng transaction, audit hoặc security advice, gọi trực tiếp target method qua JMX có thể **bỏ qua advice**. Đặc biệt với operation có tác dụng phụ, sự khác biệt đó nguy hiểm.

Ví dụ service:

\`\`\`java
@Transactional
public void requestRebuild() { ... }
\`\`\`

Nếu JMX export target object và invoke trực tiếp, transaction advice có thể không chạy. Tùy cơ chế Spring proxy và đường gọi, việc gọi qua proxy mới áp dụng advice đúng. Vì vậy trước khi unwrap target, cần hiểu method đó cần advice nào và có một đường gọi an toàn hay không.

Management adapter gọi service qua Spring-injected proxy thường rõ ràng hơn: JMX method là điểm vào adapter, còn nghiệp vụ đi qua service proxy như các consumer khác.

## 15. Nhiều exporter và xung đột registration

Khi thêm cấu hình AOP, ứng dụng có thể đồng thời import configuration khác, làm tạo thêm exporter. Nếu một bean biến mất khỏi JConsole, cần kiểm tra số exporter và ObjectName trùng.

Ví dụ:
- \`@EnableMBeanExport\` ở module chính.
- Spring Boot JMX auto-configuration bật.
- Một library khai báo \`@Bean MBeanExporter\`.

Nếu hai exporter đăng ký cùng ObjectName, kết quả có thể là exception hoặc registration bị thay thế tùy policy. Đừng tự sửa bằng \`REPLACE_EXISTING\`: context A có thể dọn MBean mà B đang sử dụng khi shutdown.

Một MBean mất sau khi bật AOP không nhất thiết do proxy; thay đổi config graph có thể là nguyên nhân thực sự.

## 16. AOP và annotation trên interface

Trong Java, annotation trên class/interface không phải lúc nào được kế thừa theo cách người viết giả định. Spring có những cơ chế merged annotation lookup nhưng không nên mặc định mọi assembler JMX hiểu annotation trên interface giống nhau.

Với \`@ManagedResource\`, đặt metadata tại vị trí được exporter/assembler hỗ trợ rõ ràng trong phiên bản Spring hiện tại. Khi dùng JDK proxy, target class và proxy interfaces khác nhau; hãy kiểm tra metadata thực sự được đọc từ đâu.

Một lựa chọn giảm bất định là adapter class riêng có \`@ManagedResource\` và những \`@ManagedAttribute\` hoặc \`@ManagedOperation\` cần thiết, không phụ thuộc vào nhiều layers interface annotation.

## 17. Chẩn đoán theo log và breakpoint

Khi sự cố khó phát hiện:

1. Bật log phù hợp cho \`org.springframework.jmx\` và \`org.springframework.aop\` trong môi trường dev/test.
2. Xem exporter bean, thời điểm auto-detection, tên MBean và exception.
3. Đặt breakpoint tại bean initialization hoặc \`MBeanExporter\` registration path.
4. Quan sát object runtime đang được exporter xử lý.
5. Xem \`AopUtils.isAopProxy\`, target class, exposed interfaces.
6. Kiểm tra assembler \`includeBean\`/metadata nếu có.
7. Xác định ObjectName được tạo.
8. Gọi \`MBeanServer.isRegistered\` sau khi context hoàn tất startup.

Không nên bật debug log nhạy cảm lâu dài trên production, và không tự log credentials/secret từ bean/connector.

## 18. Integration test khóa hành vi trước và sau auto-proxy

Một test cần kiểm tra bean và MBean cùng tồn tại:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ProxyAndJmxTest {

    @Test
    void managementBeanRemainsVisible() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.ops:type=WorkerStatus,name=Import");

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     AppConfigWithAop.class)) {

            Object bean = context.getBean("workerStatus");

            assertNotNull(bean);
            // Kiểm tra proxy type nếu fixture có advisor tạo proxy.
            System.out.println("AOP proxy=" + AopUtils.isAopProxy(bean));

            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

\`AppConfigWithAop\` phải định nghĩa service, advisor/proxy, adapter, exporter và server đúng theo fixture. Ví dụ là skeleton test, không có ý khẳng định annotation đơn lẻ tự tạo proxy. Trong test song song, dùng server riêng hoặc namespace test duy nhất để tránh collision. Chỉ assert unregister khi context thực sự sở hữu registration.

Mở rộng test:
- Đảm bảo attribute \`State\` tồn tại.
- Xác minh operation nội bộ không bị export.
- Đảm bảo service vẫn được AOP advice khi gọi qua adapter.
- Kiểm tra context refresh và không có duplicate MBean.
- Test cả JDK proxy và class-based proxy nếu ứng dụng hỗ trợ hai kiểu.

## 19. Một bảng quyết định khắc phục

| Dấu hiệu đã xác nhận | Khắc phục ưu tiên |
|---|---|
| Proxy không expose management interface | Chọn proxy interfaces đúng hoặc adapter riêng |
| Annotation nằm trên target nhưng assembler không phát hiện | Cấu hình metadata/export path hoặc adapter annotated |
| MBeanServer không đúng server client đang xem | Đồng bộ exporter/connector server |
| ObjectName được sinh khác trước | Đặt naming strategy/explicit name ổn định |
| Hai exporter cùng register cùng tên | Loại bỏ đường export trùng hoặc phân scope |
| Standard MBean không compliant sau proxy | Dùng management adapter/StandardMBean wrapper |
| Proxy type thay đổi do toàn context | Cân nhắc class-based proxy có test phạm vi rộng |
| Operation cần transaction/security advice | Gọi service qua Spring proxy, không bypass target |
| MBean xuất nhưng thiếu member | Kiểm tra MBeanInfoAssembler và management contract |
| Bean không tồn tại trong context | Sửa bean registration/profiles/conditions, không sửa JMX vội |

## 20. Những nhầm lẫn phổ biến

**“Bật @Transactional làm Spring xóa bean.”** Không. Thường bean vẫn tồn tại nhưng được expose qua proxy, và exporter có thể nhận diện khác.

**“JDK proxy luôn không thể export thành MBean.”** Không. Nếu interface và export mechanism phù hợp, proxy có thể được xuất. Phải kiểm tra contract và registration thực tế.

**“CGLIB chắc chắn sửa mọi lỗi JMX.”** Không. Nó có giới hạn với final class/method và có thể thay đổi behavior trên toàn context.

**“Cứ lấy target từ proxy rồi register.”** Nguy hiểm: JMX có thể gọi target trực tiếp và bỏ qua transaction/security advice.

**“MBean không thấy trên JConsole tức là autodetection bỏ qua.”** Không chắc: có thể sai server, connector, ObjectName hoặc registration thất bại.

**“@ManagedResource tự bảo đảm có exporter.”** Không. Metadata cần một cơ chế export được bật và cấu hình phù hợp.

**“Chỉ cần quan sát class name của proxy.”** Chưa đủ: cần exposed interfaces, target class, assembler và registry.

**“Đổi registration policy sang replace là ổn.”** Không. Điều đó có thể che lỗi duplicate exporter và làm hỏng lifecycle.

## 21. Bài tập vận dụng

### Bài 1 — Kiểm tra proxy

Một \`WorkerService\` implements \`WorkerServiceApi\` và \`WorkerStatusMBean\`, nhưng JDK proxy chỉ expose \`WorkerServiceApi\`. Bạn sẽ viết những assertion nào để chứng minh management interface bị thiếu? Đề xuất adapter hoặc cấu hình proxy interfaces.

### Bài 2 — Không thấy MBean

Sau khi bật AOP, \`context.containsBean("cacheMonitor")\` trả true nhưng \`server.isRegistered(name)\` trả false. Hãy xây dựng quy trình kiểm tra exporter, metadata, ObjectName, exception và server.

### Bài 3 — Spring advice

Một MBean operation \`rebuild()\` phải chạy với \`@Transactional\`. Vì sao register raw target trực tiếp có thể sai? Thiết kế adapter gọi service proxy.

### Bài 4 — CGLIB

Bạn thử bật \`proxyTargetClass=true\`. Nêu những test ngoài JMX cần chạy để đảm bảo proxy change không ảnh hưởng các service khác.

### Bài 5 — Negative contract

Viết test kiểm tra MBean được export đúng nhưng không có operation \`deleteAllData\` ngoài hợp đồng. Giải thích tại sao JMX exposure cần xem như API quản trị có quyền.

## Tổng kết

Khi một bean bị bỏ qua khỏi JMX sau khi bật auto-proxy, trước tiên hãy phân biệt **Spring bean có tồn tại** với **MBean có được đăng ký**. Auto-proxy có thể thay runtime class và exposed interfaces, khiến cơ chế Standard MBean hoặc Spring metadata assembler nhận diện khác trước. Quy trình chẩn đoán đúng là kiểm tra bean/proxy, interface, exporter mode, assembler, ObjectName, MBeanServer và registration logs. Giải pháp bền vững thường là một management adapter có hợp đồng nhỏ, gọi service qua Spring proxy để giữ advice, hoặc cấu hình proxy/assembler có chủ đích. Đừng chọn giải pháp có tác động toàn context trước khi biết tầng nào thực sự lỗi.
