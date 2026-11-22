# Transaction proxy trên bean có @ManagedResource trong Spring JMX

## 1. Mục tiêu

Trong Spring Framework, \`@Transactional\` thường được thực hiện thông qua **Spring AOP proxy**. Trong khi đó, \`@ManagedResource\` và các annotation như \`@ManagedAttribute\`, \`@ManagedOperation\` được sử dụng để mô tả giao diện quản trị JMX cho một Spring bean.

Khi **cùng một bean vừa có metadata JMX vừa được Spring bọc bằng transaction proxy**, việc đăng ký và gọi MBean có thêm một tầng gián tiếp. Nếu thiếu hiểu biết về proxy, ứng dụng có thể gặp các triệu chứng như:

- Bean có \`@ManagedResource\` nhưng không được tự động phát hiện để export.
- ObjectName có hoặc không có đúng như mong đợi.
- JMX attribute/operation không xuất hiện dù method đã được annotate.
- JMX operation xuất hiện nhưng gọi bị lỗi do method không có trên proxy interface.
- Method gọi được nhưng transaction không bắt đầu như mong đợi.
- Tự gọi method nội bộ (\`self-invocation\`) làm \`@Transactional\` không có hiệu lực ở proxy mode.
- MBean exporter và transaction infrastructure khởi tạo không đúng lớp đối tượng hoặc gặp xung đột lifecycle.

**Tư duy cốt lõi:** JMX metadata nằm trên class/method được khai báo, còn object mà \`MBeanExporter\` thực sự nhận có thể là **AOP proxy**. Transaction có hiệu lực khi lời gọi đi qua proxy được Spring quản lý, không chỉ vì annotation tồn tại trong source.

Sau bài này, bạn có thể:

1. Giải thích tương tác giữa \`@ManagedResource\` và \`@Transactional\`.
2. Phân biệt target object, Spring bean reference, JDK dynamic proxy và class-based proxy.
3. Xác định tình huống JMX metadata reader phải tìm annotation trên target class.
4. Hiểu điều kiện để JMX operation đi qua transaction interceptor.
5. Chọn thiết kế management facade ổn định cho JMX.
6. Chẩn đoán lỗi method không thể invoke qua proxy, self-invocation và transaction bất thường.
7. Viết integration test xác minh registration, MBeanInfo và transaction boundary thực tế.

## 2. Hai cơ chế độc lập cần phân biệt

### Spring JMX export

\`\`\`text
@ManagedResource / @ManagedOperation / @ManagedAttribute
                       |
                       v
             AnnotationJmxAttributeSource
                       |
              MetadataMBeanInfoAssembler
                       |
                 MBeanExporter
                       |
                   MBeanServer
                       |
                    JMX client
\`\`\`

JMX exporter quyết định bean nào xuất hiện và giao diện quản trị có những gì. Nó **không tự tạo database transaction** chỉ vì operation được expose.

### Spring transaction AOP

\`\`\`text
Caller --> Spring proxy --> TransactionInterceptor --> Target method
                                   |
                            begin / join transaction
                                   |
                            commit / rollback
\`\`\`

\`@Transactional\` cần transaction management được bật và có \`PlatformTransactionManager\` hoặc transaction manager phù hợp. Trong proxy mode, lời gọi phải đi qua proxy để transaction interceptor có cơ hội áp dụng.

### Hai cơ chế gặp nhau

\`\`\`text
                    Spring ApplicationContext
                            |
                      Transaction proxy
                            |
                      Target service
                  @ManagedResource
                  @ManagedOperation
                  @Transactional
                            |
                       MBeanExporter
                            |
                       MBeanServer
                            |
                     JMX client invoke()
\`\`\`

Ở sơ đồ này, Spring có thể cung cấp proxy làm bean object. Exporter cần nhận diện metadata trên target class và tạo interface JMX có thể gọi được qua proxy.

**Không thể kết luận chung rằng mọi cách đặt annotation, mọi proxy type và mọi phiên bản Spring đều hoạt động giống nhau.** Cần xét loại proxy và thực sự kiểm tra đường gọi.

## 3. Target object và AOP proxy

Giả sử có bean:

\`\`\`java
@Service
@ManagedResource(
    objectName = "com.example.monitoring:type=Payment,name=Settlement"
)
public class SettlementService {

    @Transactional
    @ManagedOperation(description = "Reconcile settlement records")
    public void reconcile() {
        // Ghi dữ liệu trong transaction.
    }
}
\`\`\`

Nếu transaction advice được áp dụng, \`ApplicationContext.getBean(SettlementService.class)\` có thể trả về một object proxy thay vì một instance thuần. Proxy đó chuyển tiếp lời gọi hợp lệ tới target, nhưng có thể có kiểu runtime và tập method expose khác.

| Khái niệm | Ý nghĩa |
|---|---|
| **Target class** | Class triển khai phương thức và chứa các annotation |
| **Proxy object** | Object được Spring trả về để áp dụng advice |
| **JDK dynamic proxy** | Proxy triển khai một hoặc nhiều interface |
| **CGLIB/class-based proxy** | Proxy dựa trên subclass của target class |
| **MBeanExporter** | Đăng ký đối tượng được chọn thành MBean |
| **JMX metadata** | Thông tin dùng để mô tả tên, attributes và operations |

Trong một số tình huống Spring AOP/JMX có hỗ trợ xác định target class và target methods. Tuy nhiên nếu management operation không khả dụng qua proxy được export, client có thể gặp lỗi \`ReflectionException\`, \`MBeanException\` hoặc exception khác tùy implementation.

## 4. JDK dynamic proxy và giới hạn interface

### 4.1. Ví dụ service interface

\`\`\`java
public interface SettlementOperations {
    void reconcile();
}
\`\`\`

Implementation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "com.example.monitoring:type=Payment,name=Settlement"
)
public class SettlementService implements SettlementOperations {

    @Override
    @Transactional
    @ManagedOperation(description = "Reconcile payments")
    public void reconcile() {
        // Business work.
    }

    @ManagedOperation(description = "Read internal diagnostic details")
    public String diagnostics() {
        return "OK";
    }
}
\`\`\`

Khi Spring tạo **JDK proxy**, đối tượng proxy công khai các method của interface được proxy. \`reconcile()\` có trong \`SettlementOperations\`; \`diagnostics()\` chỉ nằm trên implementation và không có trên interface.

Điều này có thể dẫn đến tình huống:

\`\`\`text
JMX metadata:
  reconcile()              -> managed operation
  diagnostics()            -> managed operation

JDK proxy type:
  reconcile()              -> có
  diagnostics()            -> không có
\`\`\`

Nếu assembler xây dựng operation từ target class nhưng invoker cố gọi method trực tiếp trên JDK proxy, operation không có trên proxy có thể không thể thực thi.

**Nguyên tắc:** Với JDK proxy, management methods nên nằm trong interface mà proxy thực sự expose, hoặc tách một bean quản trị riêng. Không chỉ dựa vào annotation trên implementation method mà bỏ qua proxy interface.

### 4.2. Khi interface không phù hợp cho JMX

Một service interface lớn có thể chứa nhiều method nghiệp vụ không nên được expose. Không nên thêm mọi management method vào service interface chỉ để chiều theo JDK proxy.

Một giải pháp tốt hơn là tạo **management facade** có API JMX nhỏ, chỉ gồm các operations phục vụ vận hành. Facade được Spring quản lý và gọi service được inject, nhờ vậy service transaction proxy vẫn được sử dụng.

## 5. Class-based proxy (CGLIB) và các giới hạn

Class-based proxy tạo một subclass runtime để intercept lời gọi qua những method có thể override.

Ví dụ bật class-based proxy trong cấu hình transaction:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class TransactionConfiguration {
}
\`\`\`

Hoặc trong Spring Boot, cách chọn proxy type có thể chịu ảnh hưởng của auto-configuration và property \`spring.aop.proxy-target-class\`; cần xem phiên bản Boot thực tế.

Ưu điểm class-based proxy:
- Không bắt buộc method xuất hiện trong service interface như JDK proxy.
- Nhiều public methods của target class có thể được gọi qua proxy.

Giới hạn:
- \`final\` class không thể được subclass theo cơ chế này.
- \`final\` methods không thể bị override để advice.
- \`private\` methods không thể được intercept theo proxy-based AOP.
- Vẫn có vấn đề self-invocation.
- Metadata và proxy invocation vẫn cần được kiểm tra trên runtime.

Đừng kết luận “đổi sang CGLIB là xong mọi vấn đề”. Nó có thể giải quyết vấn đề phương thức không có trên JDK proxy interface, nhưng không thay đổi bản chất proxy-based transaction hay thay thế việc thiết kế management API rõ ràng.

## 6. Gọi JMX operation có đi qua @Transactional không?

Câu trả lời phụ thuộc **đường lời gọi thực tế** và việc object được đăng ký là proxy hay target.

### Trường hợp A: JMX gọi qua Spring transaction proxy

\`\`\`text
JMX client
   |
   v
MBeanServer.invoke()
   |
   v
Spring-exported proxy
   |
   v
TransactionInterceptor
   |
   v
Target method @Transactional
\`\`\`

Nếu exporter đăng ký/adapt proxy đúng, operation trên JMX được ánh xạ tới method có thể gọi qua proxy và transaction management có hiệu lực, transaction có thể bắt đầu như lời gọi Spring thông thường.

### Trường hợp B: JMX gọi thẳng target, bỏ qua proxy

\`\`\`text
JMX client
   |
   v
MBeanServer.invoke()
   |
   v
Raw target object
   |
   v
@Transactional method
   |
   v
Không có transaction interceptor từ Spring proxy
\`\`\`

Annotation \`@Transactional\` ở source code **không tự tạo transaction** nếu đường gọi không đi qua transaction interceptor. Điều này cũng xảy ra khi code tự tạo object bằng \`new\` hoặc khi exporter đăng ký trực tiếp một instance không phải Spring proxy.

### Trường hợp C: Transaction advice không được cấu hình

Nếu project không có transaction manager thích hợp hoặc transaction management không được bật, có annotation cũng chưa đủ để bảo đảm transaction trong runtime.

**Không nên suy đoán giao dịch có hoạt động chỉ bằng cách kiểm tra class có \`@Transactional\` hay không.** Cần xác minh đường gọi và trạng thái transaction trong integration test.

## 7. Self-invocation: bẫy phổ biến

Ví dụ:

\`\`\`java
@Service
@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import"
)
public class ImportService {

    @ManagedOperation
    public void runNow() {
        importBatch(); // gọi qua this, không qua Spring proxy
    }

    @Transactional
    public void importBatch() {
        // Database writes.
    }
}
\`\`\`

Trong Spring AOP proxy mode, \`runNow()\` gọi \`importBatch()\` trên cùng target (\`this\`) thường **không đi qua transaction proxy**. Vì vậy \`@Transactional\` trên \`importBatch()\` có thể không được áp dụng cho lời gọi nội bộ này.

Cần phân biệt:
- Nếu \`runNow()\` được annotate \`@Transactional\` và JMX gọi qua proxy, transaction có thể bao bọc toàn method.
- Nếu chỉ \`importBatch()\` được annotate và gọi từ \`runNow()\` bằng \`this\`, advice ở \`importBatch()\` không được áp dụng bởi proxy.
- Nếu \`runNow()\` gọi method transactional trên **bean khác được inject** thì call qua proxy của bean đó có thể kích hoạt advice.

### Giải pháp tách service

\`\`\`java
@Service
public class ImportTransactionalService {

    @Transactional
    public void importBatch() {
        // Database work.
    }
}
\`\`\`

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import"
)
public class ImportManagement {

    private final ImportTransactionalService service;

    public ImportManagement(ImportTransactionalService service) {
        this.service = service;
    }

    @ManagedOperation(description = "Request an import batch")
    public void runNow() {
        service.importBatch(); // gọi qua injected Spring bean
    }
}
\`\`\`

Mô hình này giúp tách rõ:
- **Management facade:** API quản trị JMX.
- **Transactional service:** logic nghiệp vụ và transaction boundary.
- **Spring proxy:** nằm trên injected service reference nếu transaction advice có hiệu lực.

Đây thường là lựa chọn dễ kiểm chứng và bảo trì hơn việc export trực tiếp một service lớn vừa có AOP vừa có JMX methods.

## 8. Cấu hình Spring JMX và transaction

Ví dụ Spring Framework dùng Java configuration:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMBeanExport
@EnableTransactionManagement
public class AppConfiguration {
}
\`\`\`

\`@EnableMBeanExport\` bật annotation-driven JMX export. \`@EnableTransactionManagement\` bật transaction annotation processing trong context.

Nhưng các annotation cấu hình này không tự:
- Tạo database hoặc \`DataSource\`.
- Cấp \`PlatformTransactionManager\` phù hợp.
- Cài security cho JMX remote.
- Xác định đầy đủ nghiệp vụ rollback/commit.
- Chuyển mọi Spring bean thành MBean.

Cần có \`DataSource\`, repositories và transaction manager phù hợp theo stack thực tế. Với Spring Boot, nhiều phần có thể được auto-configured, nhưng phải kiểm tra runtime.

### XML configuration

Với dự án Spring XML:

\`\`\`xml
<tx:annotation-driven/>

<context:mbean-export/>
\`\`\`

Cần khai báo các XML namespaces và schema locations cho \`tx\` và \`context\` tương ứng. Hai phần tử này làm hai nhiệm vụ khác nhau: transaction proxy và JMX export.

Một ví dụ đầy đủ:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd">

    <context:component-scan base-package="com.example"/>

    <tx:annotation-driven/>

    <context:mbean-export/>

    <!-- DataSource / transaction manager còn phải được cấu hình phù hợp. -->
</beans>
\`\`\`

Nếu transaction manager không được cấu hình/auto-wired đúng theo context, \`<tx:annotation-driven/>\` không tự tạo một transaction boundary hợp lệ cho mọi công nghệ persistence.

## 9. Vị trí annotation trên class và method

Một bean có thể vừa được annotate:

\`\`\`java
@ManagedResource(...)
@Transactional
public class PaymentService { ... }
\`\`\`

hoặc chỉ từng method:

\`\`\`java
@ManagedOperation
@Transactional
public void reconcile() { ... }
\`\`\`

Điều cần hiểu:

- \`@ManagedResource\` là metadata cấp class cho Spring JMX.
- \`@ManagedOperation\` là metadata của method được expose qua JMX.
- \`@Transactional\` là metadata cho transaction advice.
- Chúng được đọc bởi **những cơ chế khác nhau**.
- Không có quy tắc chung rằng đặt hai annotations trên cùng method sẽ luôn đảm bảo JMX invocation qua proxy ở mọi cấu hình.

Với JDK proxy, interface methods và annotation lookup cần được kiểm tra. Với CGLIB, subclass behavior và visibility quyết định khả năng intercept.

Nếu JMX metadata reader tìm đúng method trên target class nhưng actual JMX invocation gọi một object/method khác, có thể xảy ra chênh lệch giữa **metadata công bố** và **khả năng thực thi**.

## 10. MBeanExporter, metadata assembler và proxy

Trong Spring JMX annotation-based export, các thành phần liên quan:

- \`AnnotationJmxAttributeSource\`: đọc \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`.
- \`MetadataMBeanInfoAssembler\`: xây dựng giao diện quản trị từ metadata.
- \`MetadataNamingStrategy\`: lấy \`ObjectName\` từ metadata cấp class.
- \`MBeanExporter\`: chọn bean, đăng ký MBean trên \`MBeanServer\`.
- Spring AOP infrastructure: tạo proxy để áp dụng transaction advice.

Một số tình huống cần chú ý:

1. **Autodetection:** exporter phải phát hiện đúng bean có metadata dù bean runtime là proxy.
2. **Naming:** strategy phải đọc ObjectName từ target class nếu annotation không nằm trên proxy class.
3. **Assembly:** assembler phải xác định những getter/method management thực sự có thể được gọi.
4. **Invocation:** lời gọi phải đi qua proxy thích hợp nếu cần transaction.
5. **Lifecycle:** exporter phải đăng ký/unregister đúng object, không làm phá vỡ bean references.

Spring Framework có cơ chế hỗ trợ AOP proxies trong một số tuyến JMX export, nhưng hành vi cụ thể phụ thuộc loại proxy, interface, annotations và version. **Đừng thay thế integration test bằng giả định rằng infrastructure tự xử lý mọi trường hợp.**

## 11. Transaction proxy không đồng nghĩa MBean proxy

Trong JMX còn có khái niệm **MBean proxy** ở phía client:

\`\`\`java
MyMonitorMBean proxy = JMX.newMBeanProxy(
    connection,
    objectName,
    MyMonitorMBean.class
);
\`\`\`

Đây là client-side proxy chuyển method calls thành JMX requests.

Spring transaction proxy lại là server-side AOP proxy xử lý cross-cutting advice như transaction.

\`\`\`text
JMX Client
  MBean proxy (optional)
       |
       v
  MBeanServerConnection
       |
       v
  JMX MBeanServer
       |
       v
  Spring transaction proxy (if exported/called through it)
       |
       v
  Target business method
\`\`\`

Hai proxy tồn tại ở hai tầng khác nhau:
- MBean proxy giúp client gọi JMX bằng typed Java interface.
- Transaction proxy giúp Spring áp dụng transaction boundaries.
- MBean proxy không tự đảm bảo transaction trên target.
- Transaction proxy không tự bật JMX remote connector.

## 12. Chẩn đoán: bean có trong Spring nhưng không thấy MBean

Nếu application khởi động thành công nhưng không thấy MBean:

1. Xác minh Spring bean tồn tại trong \`ApplicationContext\`.
2. Kiểm tra \`@ManagedResource.objectName\` có hợp lệ không.
3. Kiểm tra \`@EnableMBeanExport\`, XML \`<context:mbean-export/>\` hoặc Boot JMX auto-config.
4. Kiểm tra transaction proxy type và target class.
5. Kiểm tra metadata reader/naming strategy có đọc đúng annotation không.
6. Kiểm tra exporter đã chọn bean chưa.
7. Kiểm tra target MBeanServer.
8. Kiểm tra ObjectName collision hoặc lỗi registration.
9. Dùng \`queryNames()\` hoặc \`isRegistered()\` để xác minh.

Không suy ra rằng \`@Transactional\` tự động làm MBean không thể export. Vấn đề là sự tương thích của đường discovery, metadata và invocation trong cấu hình cụ thể.

### Kiểm tra bean có phải Spring AOP proxy

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("settlementService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

Đây là thông tin chẩn đoán về proxy runtime, không phải bằng chứng cuối cùng rằng transaction thực sự bắt đầu ở lời gọi JMX.

## 13. Kiểm tra MBeanInfo và invoke operation

Giả sử MBean đã được đăng ký:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Payment,name=Settlement"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var operation : info.getOperations()) {
    System.out.println(
        "Operation: " + operation.getName()
    );
}
\`\`\`

Sau đó gọi trong môi trường thử nghiệm:

\`\`\`java
server.invoke(
    name,
    "reconcile",
    new Object[0],
    new String[0]
);
\`\`\`

Việc \`invoke()\` trả về thành công chứng minh operation chạy theo JMX interface, nhưng **chưa tự chứng minh transaction bắt đầu**. Cần quan sát transaction active state hoặc kết quả commit/rollback.

Nếu exporter dùng MBeanServer khác platform server, phải truy vấn đúng server. Nếu gọi remote, cần \`MBeanServerConnection\` và xử lý lỗi mạng.

## 14. Kiểm chứng transaction boundary trong runtime

Trong một service dùng transaction proxy, có thể kiểm tra transaction active bên trong method bằng API Spring:

\`\`\`java
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Transactional
public void reconcile() {
    boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

    System.out.println("Active transaction: " + active);

    // Logic nghiệp vụ...
}
\`\`\`

Trong integration test, tốt hơn là assert:

\`\`\`java
if (!TransactionSynchronizationManager
        .isActualTransactionActive()) {

    throw new IllegalStateException(
        "Expected an active transaction"
    );
}
\`\`\`

**Lưu ý:** \`isActualTransactionActive()\` là trạng thái thread-bound transaction của Spring, không phải bằng chứng duy nhất cho mọi kiểu transaction/reactive model. Với reactive transactions dùng Reactor context, cách kiểm chứng khác. Bài học này chủ yếu nói về proxy-based imperative transaction management.

### Thử rollback

Một integration test đáng tin cậy có thể:
1. Gọi JMX operation thông qua MBeanServer.
2. Operation đi qua Spring service.
3. Service ghi một bản ghi vào database rồi ném unchecked exception.
4. Sau lời gọi, truy vấn database để xác minh bản ghi được rollback.
5. Lặp lại với thiết kế self-invocation sai để so sánh (trong môi trường test độc lập).

Không nên dùng database production để thử rollback hoặc gọi operation có tác động thật chỉ nhằm kiểm tra proxy.

## 15. Mẫu thiết kế tốt: JMX management facade

Đây thường là giải pháp dễ vận hành khi bean nghiệp vụ có transaction/AOP phức tạp.

### Service nghiệp vụ

\`\`\`java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SettlementService {

    @Transactional
    public void reconcile() {
        // Database transaction.
    }

    @Transactional(readOnly = true)
    public long countPending() {
        return 12;
    }
}
\`\`\`

### Facade quản trị

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Payment,name=Settlement",
    description = "Settlement administration"
)
public class SettlementManagement {

    private final SettlementService service;

    public SettlementManagement(SettlementService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of pending settlements")
    public long getPendingCount() {
        return service.countPending();
    }

    @ManagedOperation(description = "Request settlement reconciliation")
    public void reconcile() {
        service.reconcile();
    }
}
\`\`\`

Ưu điểm:
- MBean có giao diện JMX nhỏ, rõ ràng.
- \`@ManagedResource\` nằm trên facade không nhất thiết bị transaction proxy bọc.
- Service nghiệp vụ vẫn được inject qua Spring bean reference.
- Lời gọi từ facade sang service đi qua transaction proxy trong cấu hình bình thường.
- Dễ test ObjectName, MBeanInfo và rollback riêng biệt.
- Có thể kiểm soát validation và authorization ở lớp management trước khi gọi nghiệp vụ.

Hạn chế:
- Thêm một lớp facade và một số phương thức delegate.
- Nếu facade truy vấn dữ liệu quá nặng trong getter, vẫn có thể ảnh hưởng hiệu năng JMX.
- Operation có tác động phải được bảo vệ bằng JMX security, không chỉ vì đã có facade.

## 16. Kịch bản transaction proxy và JMX

| Kịch bản | Điều có thể xảy ra | Khuyến nghị |
|---|---|---|
| Bean dùng \`@ManagedResource\` và không có AOP proxy | Export annotation tương đối trực tiếp | Kiểm tra MBeanInfo và ObjectName |
| Bean dùng JDK proxy; operation nằm trong interface | Operation có thể invoke qua proxy | Test transaction active và method visibility |
| Bean dùng JDK proxy; operation chỉ nằm trên implementation | Operation có thể thiếu hoặc không gọi được | Đưa method vào interface phù hợp hoặc dùng facade |
| Bean dùng CGLIB proxy | Nhiều method class có thể intercept | Tránh final/private và self-invocation |
| JMX đăng ký raw target thay vì proxy | \`@Transactional\` có thể bị bypass | Đăng ký Spring-managed proxy hoặc tách facade |
| Facade JMX inject transactional service | Service call có thể đi qua transaction interceptor | Thiết kế thường dễ bảo trì |
| Operation JMX tự gọi method transactional bằng \`this\` | Self-invocation bỏ qua advice của method được gọi | Chuyển logic sang bean khác |
| Reactive transaction | Thread-bound check có thể không phù hợp | Dùng reactive transaction APIs/tests |

Đừng quy mọi lỗi JMX+AOP về \`@Transactional\`. Có thể là lỗi naming, metadata, MBeanServer, exporter, proxy method exposure hoặc configuration của transaction manager.

## 17. Xử lý ngoại lệ và rollback khi gọi JMX

Một method \`@Transactional\` có thể rollback hoặc commit tùy:
- Loại exception.
- Quy tắc \`rollbackFor\`/\`noRollbackFor\`.
- Propagation behavior.
- Transaction manager.
- Exception có bị catch trước khi vượt qua interceptor không.

Ví dụ:

\`\`\`java
@Transactional(rollbackFor = Exception.class)
public void reconcile() throws Exception {
    repository.save(...);

    if (validationFailed()) {
        throw new Exception("Cannot reconcile");
    }
}
\`\`\`

Nếu exception đi qua transaction interceptor, Spring áp dụng rollback rules đã cấu hình. Ở tầng JMX, ngoại lệ có thể được wrapping thành \`MBeanException\` hoặc các exception JMX phù hợp; client cần xem cause để biết lỗi nghiệp vụ.

**Không nên dựa vào exception wrapping của JMX để suy đoán commit/rollback.** Transaction decision diễn ra ở Spring transaction layer; kết quả cần được kiểm tra theo hợp đồng nghiệp vụ.

### Retry remote JMX

Với operation thay đổi database, network disconnect có thể xảy ra sau khi server đã commit nhưng trước khi client nhận response. Nếu client retry mù, transaction mới có thể chạy thêm lần nữa.

Khi dùng remote JMX operation:
- Thiết kế idempotent nếu có thể.
- Có operation/request ID để đối chiếu nếu cần.
- Tránh dùng JMX remote như API nghiệp vụ giao dịch chính.
- Không cho phép operation nhạy cảm chạy trùng chỉ vì client timeout.

## 18. Khi nào nên dùng @Transactional ngay trên management method?

Có thể dùng trực tiếp \`@Transactional\` trên method JMX nếu:
- Method quản trị thật sự cần transaction.
- Spring transaction proxy được tạo.
- Exporter thực sự gọi qua proxy.
- Method có thể được intercept trong proxy mode.
- Đã có integration test chứng minh boundary và rollback.

Ví dụ:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Admin"
)
public class CacheAdmin {

    @ManagedOperation
    @Transactional
    public void refreshDatabaseBackedCache() {
        // Transactional refresh.
    }
}
\`\`\`

Đây không phải thiết kế sai mặc định. Nhưng với JMX management interface có nhiều operations hoặc nghiệp vụ phức tạp, tách facade và transactional service thường tạo ranh giới rõ ràng hơn.

Không nên thêm \`@Transactional\` lên mọi JMX getter. Một getter gọi database trong transaction có thể tạo overhead và locks; nếu chỉ cần số liệu giám sát, hãy tối ưu và cân nhắc snapshot/cached metrics.

## 19. Bảo mật JMX transaction operations

Một JMX operation có thể mở transaction và thay đổi dữ liệu sản xuất. Điều này khiến nó có rủi ro tương đương administrative API:

- Chỉ export các operations thật sự cần thiết.
- Bảo vệ authentication/authorization của JMX remote connector.
- Hạn chế quyền \`invoke\` và \`setAttribute\`.
- Không expose credentials, token hoặc thông tin cá nhân trong attributes/exceptions.
- Ghi audit cho operations quan trọng.
- Validate tham số, giữ idempotency hoặc điều kiện chống chạy trùng.
- Có giới hạn concurrency và timeout phù hợp.
- Tránh long-running transactions được kích hoạt không kiểm soát qua JMX.
- Dùng cơ chế quản trị nghiệp vụ khác nếu cần workflow, approvals hoặc độ tin cậy giao nhận cao.

\`@ManagedOperation(description="Admin only")\` không tự cấp hay kiểm tra quyền. Description là metadata, không phải authorization policy.

## 20. Bài tập thực hành

### Bài tập A — Kiểm tra proxy type

1. Tạo Spring service có \`@Transactional\`.
2. Bật transaction management.
3. Dùng \`AopUtils.isAopProxy()\` và \`getTargetClass()\` kiểm tra bean.
4. Chuyển giữa JDK dynamic proxy và class-based proxy trong môi trường test.
5. Ghi lại methods nào thực sự có thể gọi trên proxy.

### Bài tập B — Expose service trực tiếp

1. Đặt \`@ManagedResource\` trên transactional service.
2. Annotate một method với \`@ManagedOperation\`.
3. Bật JMX export.
4. Xác minh ObjectName và MBeanInfo.
5. Gọi \`MBeanServer.invoke()\`.
6. Kiểm tra transaction active bên trong method.
7. Nếu fail, phân biệt lỗi discovery/metadata/invocation/transaction.

### Bài tập C — Self-invocation

1. Tạo method \`runNow()\` gọi \`this.importBatch()\`.
2. Chỉ annotate \`importBatch()\` bằng \`@Transactional\`.
3. Gọi \`runNow()\` từ JMX.
4. Quan sát transaction active bên trong \`importBatch()\`.
5. Chuyển \`importBatch()\` sang một injected Spring service.
6. Chạy lại test và so sánh.

### Bài tập D — Facade JMX

1. Tạo \`SettlementService\` với \`@Transactional\`.
2. Tạo \`SettlementManagement\` với \`@ManagedResource\`.
3. Inject \`SettlementService\` vào facade.
4. Expose một getter read-only và một operation.
5. Kiểm tra \`MBeanInfo\` và rollback behavior.
6. Thử network timeout giả lập (chỉ môi trường test) và thảo luận về idempotency.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** \`@ManagedResource\` có tự bật transaction không?  
**Trả lời:** Không. Nó cung cấp metadata JMX; transaction do Spring transaction infrastructure quản lý.

**Câu 2.** Vì sao method có \`@Transactional\` đôi khi không chạy trong transaction khi được gọi qua JMX?  
**Trả lời:** Lời gọi có thể không đi qua Spring transaction proxy, method không được intercept hoặc transaction management chưa cấu hình phù hợp.

**Câu 3.** JDK proxy ảnh hưởng gì đến JMX methods?  
**Trả lời:** JDK proxy chủ yếu expose methods thuộc interface được proxy; method chỉ có trên implementation có thể không gọi được qua proxy.

**Câu 4.** CGLIB proxy có giải quyết self-invocation không?  
**Trả lời:** Không. Lời gọi nội bộ từ target không qua proxy vẫn có thể bypass advice.

**Câu 5.** Khi dùng management facade gọi một transactional service được inject, lợi ích là gì?  
**Trả lời:** Ranh giới quản trị và nghiệp vụ tách biệt; facade có thể gọi service qua Spring proxy để transaction advice hoạt động.

**Câu 6.** Có thể chứng minh transaction active chỉ bằng việc \`MBeanServer.invoke()\` trả về không?  
**Trả lời:** Không. Cần kiểm tra trạng thái transaction hoặc commit/rollback trong integration test.

**Câu 7.** Remote JMX invoke timeout có chứng minh transaction chưa commit không?  
**Trả lời:** Không. Server có thể đã commit nhưng response mất; cần idempotency và đối chiếu state trước khi retry.

## 22. Ghi nhớ

- Spring JMX và Spring transaction AOP là hai cơ chế độc lập nhưng tương tác khi cùng một bean có \`@ManagedResource\` và \`@Transactional\`.
- JMX metadata có thể nằm trên target class, trong khi Spring bean runtime là proxy.
- Với JDK proxy, management methods cần khả dụng trên interface; class-based proxy có các giới hạn final/private.
- \`@Transactional\` trong proxy mode chỉ có hiệu lực khi lời gọi đi qua transaction interceptor.
- Self-invocation là nguyên nhân thường gặp làm transaction annotation trên method nội bộ không chạy.
- Đăng ký raw target thay vì Spring proxy có thể bỏ qua transaction advice.
- **Management facade inject transactional service** là một thiết kế thường phù hợp để giảm phụ thuộc vào proxy type.
- Luôn kiểm chứng cả JMX interface (\`MBeanInfo\`) và transaction boundary (active transaction, rollback/commit).
- JMX remote invoke có failure semantics của lời gọi phân tán; không retry mù operations có side effects.
- Bảo vệ quyền gọi operations quản trị như mọi administrative API nhạy cảm.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Reference — Understanding the Spring Framework’s Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Javadoc — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`AopUtils\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
