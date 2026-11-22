# Thứ tự tạo proxy, exporter và metadata assembler trong Spring JMX và AOP

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** JMX và AOP  
> **Bài học:** Thứ tự tạo proxy, exporter và metadata assembler

## 1. Mục tiêu bài học

Khi một Spring bean vừa sử dụng AOP vừa được xuất bản qua JMX, kết quả không chỉ phụ thuộc vào việc class có \`@ManagedResource\`. Thời điểm Spring tạo bean, áp dụng \`BeanPostProcessor\`, tạo AOP proxy, xác định metadata và đăng ký MBean vào \`MBeanServer\` đều ảnh hưởng bề mặt quản trị mà client nhìn thấy.

Sau bài học, bạn có thể:

- Mô tả thứ tự khái quát giữa khởi tạo bean, AOP proxy, \`MBeanExporter\` và \`MetadataMBeanInfoAssembler\`.
- Phân biệt **target object**, **AOP proxy**, **exporter** và **ModelMBean**.
- Hiểu vì sao annotation trên implementation đôi khi khó được phát hiện khi exporter nhìn thấy JDK dynamic proxy.
- Phân biệt metadata của Spring JMX với method thật sự có thể được gọi thông qua proxy.
- Kiểm tra \`MBeanInfo\`, bean runtime type, advisor và \`ObjectName\` để chẩn đoán lỗi export.
- Biết cách tổ chức cấu hình để tránh sử dụng bean quá sớm, tạo exporter trùng hoặc vô tình bypass AOP advice.

## 2. Bối cảnh: một bean có nhiều lớp đại diện

Giả sử Spring service:

\`\`\`java
@Service
@ManagedResource(
    objectName = "app.management:type=Billing,name=main"
)
public class BillingService {

    @Transactional
    @ManagedOperation
    public void reconcile() {
        // Thực hiện xử lý nghiệp vụ.
    }
}
\`\`\`

Ứng dụng đồng thời bật Spring AOP hoặc transaction proxy và bật JMX export.

Trong một cấu hình phổ biến, đối tượng được công bố có thể đi qua:

\`\`\`text
BillingService implementation (target)
                   |
                   v
           Spring AOP proxy
                   |
                   v
      MBeanExporter / JMX adapter
                   |
                   v
              MBeanServer
                   |
                   v
        JConsole / JMX client
\`\`\`

Tuy nhiên đây là **mô hình khái quát**, không phải cam kết rằng mọi phiên bản Spring luôn tạo mọi loại proxy trước một thời điểm cố định. Điều quan trọng là xác định những bean/proxy mà exporter thực tế nhận được khi nó tạo \`ModelMBeanInfo\` và đăng ký MBean.

Nếu proxy đứng giữa client và target, invocation có thể đi qua AOP advice như transaction, logging, validation hoặc security. Nếu exporter bị cấu hình trực tiếp với target object khác, đường gọi JMX có thể bypass proxy và không đi qua advice mong muốn.

## 3. Các thành phần cần phân biệt

| Thành phần | Vai trò |
|---|---|
| Spring target bean | Implementation chứa logic thực tế |
| \`BeanPostProcessor\` | Có thể tham gia vào giai đoạn tạo/wrap bean |
| AOP \`AutoProxyCreator\` | Tạo proxy áp dụng interceptor/advice theo cấu hình |
| JDK dynamic proxy | Proxy dựa trên interface Java |
| CGLIB/class-based proxy | Proxy dạng subclass của class target |
| \`MBeanExporter\` | Xuất bean phù hợp dưới dạng MBean |
| \`AnnotationMBeanExporter\` | Hạ tầng export MBean dựa trên annotation |
| \`MetadataMBeanInfoAssembler\` | Đọc metadata JMX và xây \`ModelMBeanInfo\` |
| \`AnnotationJmxAttributeSource\` | Nguồn metadata từ annotation Spring JMX |
| \`ObjectNamingStrategy\` | Xác định \`ObjectName\` cho MBean |
| \`MBeanServer\` | Registry và endpoint thực thi JMX |
| \`MBeanInfo\` | Hợp đồng attributes, operations, notifications client thấy |

Một \`ObjectName\` ví dụ:

\`\`\`text
app.management:type=Billing,name=main
\`\`\`

Nó là định danh quản trị trong \`MBeanServer\`, **không phải class name** của proxy hoặc target.

## 4. Trình tự khởi tạo khái quát

Trong một \`ApplicationContext\` thông thường:

\`\`\`text
[1] Đọc @Configuration / bean definitions
                      |
[2] Đăng ký BeanFactoryPostProcessor/BeanPostProcessor
                      |
[3] Khởi tạo singleton beans theo dependency và lifecycle
                      |
[4] BeanPostProcessor có thể wrap bean thành AOP proxy
                      |
[5] Exporter lấy bean tham chiếu / phát hiện bean
                      |
[6] Assembler tạo metadata quản trị cho MBean
                      |
[7] Exporter chọn ObjectName và đăng ký MBean
                      |
[8] Client truy vấn MBeanInfo / invoke operation
\`\`\`

Các bước [3] đến [7] có thể phụ thuộc thứ tự dependency, \`SmartInitializingSingleton\`, vòng đời exporter, bean post-processing và phiên bản Spring. Không xem sơ đồ này là một total order bất biến với mọi ứng dụng.

Đặc biệt, trong Spring container, các \`BeanPostProcessor\` được đăng ký trước quá trình khởi tạo thông thường của nhiều application beans, nhưng một số bean infrastructure có thể được tạo sớm và không nhận mọi loại post-processing. Đây là lý do tránh lấy bean nghiệp vụ từ một infrastructure component quá sớm.

## 5. Vì sao phải nghĩ đến proxy trước exporter?

Giả sử service có interface:

\`\`\`java
public interface BillingOperations {
    void reconcile();
}
\`\`\`

Implementation:

\`\`\`java
@Service
public class BillingService implements BillingOperations {

    @Override
    @Transactional
    public void reconcile() {
        // Logic cần transaction.
    }
}
\`\`\`

Khi sử dụng JDK dynamic proxy, object mà một client lấy từ context có thể chỉ triển khai \`BillingOperations\` và một số interface proxy khác, thay vì trực tiếp là instance của class \`BillingService\`.

\`\`\`text
Bean name "billingService"
             |
             v
JDK dynamic proxy (BillingOperations)
             |
             v
BillingService target
\`\`\`

Nếu JMX exporter giữ reference đến bean proxy, lời gọi qua interface có thể đi qua advice. Nếu exporter cố gọi một method chỉ có trên implementation nhưng không nằm trên interface của JDK proxy, invocation có thể không khả dụng theo cách bạn mong đợi.

Với CGLIB proxy, subclass proxy thường expose nhiều method public của class target hơn, nhưng không có nghĩa mọi method được advise hoặc export tự động. Method \`final\`, \`private\` và self-invocation có giới hạn AOP riêng.

## 6. Metadata assembler đọc gì?

Spring JMX annotation model thường dùng:

\`\`\`java
@ManagedResource(...)
@ManagedAttribute(...)
@ManagedOperation(...)
\`\`\`

Khi exporter chuẩn bị MBean, \`MetadataMBeanInfoAssembler\` dựa vào \`JmxAttributeSource\` để tạo metadata mô tả tài nguyên quản trị.

\`\`\`text
Target class / proxy-visible methods
                 |
                 v
      AnnotationJmxAttributeSource
                 |
                 v
      MetadataMBeanInfoAssembler
                 |
                 v
      ModelMBeanInfo: attributes,
      operations, notifications
                 |
                 v
          ModelMBean registered
\`\`\`

Điểm quan trọng là **metadata** và **khả năng thực thi method** phải khớp nhau. Một method có annotation trên target nhưng exporter hoặc proxy không expose đúng method signature có thể dẫn đến kết quả thiếu operation hoặc lỗi invocation.

Không giả định việc thêm annotation vào class chắc chắn làm operation xuất hiện; hãy kiểm tra \`MBeanInfo\` từ server thực tế.

## 7. Ví dụ Spring JMX kết hợp AOP

### 7.1. Management interface

\`\`\`java
package example.jmx;

public interface JobControl {
    int getPendingJobs();
    String requestDrain(int maxBatch);
}
\`\`\`

### 7.2. Implementation có annotation

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "app.management:type=JobControl,name=main",
    description = "Queue job management"
)
public class JobControlService implements JobControl {

    private volatile int pendingJobs = 10;

    @Override
    @ManagedAttribute(description = "Pending job count")
    public int getPendingJobs() {
        return pendingJobs;
    }

    @Override
    @Transactional
    @ManagedOperation(description = "Request batch drain")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxBatch",
            description = "Maximum jobs to drain"
        )
    })
    public String requestDrain(int maxBatch) {
        if (maxBatch < 1 || maxBatch > 100) {
            throw new IllegalArgumentException(
                "maxBatch must be 1..100"
            );
        }

        // Trong ứng dụng thật gọi service xử lý tác vụ.
        pendingJobs = Math.max(0, pendingJobs - maxBatch);
        return "accepted";
    }
}
\`\`\`

Annotation trên implementation thể hiện metadata quản trị và transaction advice. Đoạn mã minh họa dùng field đếm đơn giản; trong ứng dụng đa luồng nên thiết kế state/concurrency thích hợp.

### 7.3. Cấu hình export

\`\`\`java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@ComponentScan(basePackageClasses = JobControlService.class)
@EnableTransactionManagement
@EnableMBeanExport
public class JmxAndAopConfiguration {
}
\`\`\`

Cấu hình \`@EnableTransactionManagement\` kích hoạt hạ tầng transaction interception khi có transaction manager và các điều kiện phù hợp. Chỉ gắn annotation không tự tạo database hoặc transaction manager.

### 7.4. Truy vấn hợp đồng đã export

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "app.management:type=JobControl,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var op : info.getOperations()) {
    System.out.println(
        op.getName() + " -> " + op.getReturnType()
    );
}
\`\`\`

Ví dụ giả định exporter dùng platform MBeanServer. Nếu exporter được cấu hình MBeanServer riêng, cần lấy connection đến server thực tế.

## 8. JDK proxy và CGLIB proxy

| Tiêu chí | JDK dynamic proxy | CGLIB/class-based proxy |
|---|---|---|
| Cơ chế | Implement các interface | Tạo subclass của target class |
| Method thấy qua proxy | Các method thuộc interface được proxy implement | Các method có thể override/expose theo class |
| Phụ thuộc interface | Rõ ràng | Không bắt buộc |
| Giới hạn AOP | Method ngoài proxy interface không gọi qua proxy được | Final/private/self-invocation vẫn là vấn đề |
| Tác động JMX | Management methods cần có đường gọi phù hợp qua interface | Có thể dễ tìm method trên class hơn, nhưng metadata vẫn phải khớp |

Với Spring AOP proxy, type runtime có thể khác target class:

\`\`\`java
Object bean = context.getBean("jobControlService");

System.out.println(bean.getClass().getName());
\`\`\`

Kết quả có thể là tên JDK proxy hoặc CGLIB-generated class. Không dùng runtime proxy class name làm hợp đồng \`ObjectName\` bền vững cho client.

Có thể dùng Spring AOP utilities để quan sát:

\`\`\`java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(bean);
boolean jdk = AopUtils.isJdkDynamicProxy(bean);
boolean cglib = AopUtils.isCglibProxy(bean);
Class<?> targetType = AopUtils.getTargetClass(bean);
\`\`\`

Đây là quan sát kiểu/proxy trong process, không phải một cơ chế để tự động sửa mọi lỗi JMX.

## 9. Annotation trên interface hay implementation?

Một câu hỏi thường gặp: gắn \`@ManagedOperation\` trên interface, implementation hay cả hai?

Các metadata annotation có thể được framework tra cứu trên method/interface/class theo quy tắc cụ thể. Quy tắc này còn phụ thuộc exporter, assembler, proxy và phiên bản Spring. Vì vậy không nên tuyên bố rằng một vị trí annotation luôn hoạt động trong mọi cấu hình.

Một chiến lược dễ bảo trì:

1. Tạo management interface hẹp định nghĩa các method cần expose.
2. Bảo đảm proxy thực thi được những method đó.
3. Đặt metadata trên lớp/method mà exporter thực tế hỗ trợ và nhận diện.
4. Dùng \`MBeanInfo\` để xác minh attribute và operation đã xuất hiện.
5. Kiểm tra invocation qua MBeanServer trong integration test.

Nếu ứng dụng có JDK proxy và annotation chỉ nằm trên method không xuất hiện trên interface, một hướng là đổi management design để method được expose qua interface phù hợp, hoặc dùng facade riêng.

## 10. Export một management facade riêng

Khi service nội bộ có AOP phức tạp, thiết kế facade có thể giảm phụ thuộc vào chi tiết proxy:

\`\`\`text
JMX client
    |
    v
Management facade @ManagedResource
    |
    v
Business service interface
    |
    v
Spring AOP proxy
    |
    v
Business implementation
\`\`\`

Ví dụ:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=JobControl,name=main"
)
public class JobManagementFacade {

    private final JobControl jobControl;

    public JobManagementFacade(JobControl jobControl) {
        this.jobControl = jobControl;
    }

    @ManagedAttribute
    public int getPendingJobs() {
        return jobControl.getPendingJobs();
    }

    @ManagedOperation
    public String requestDrain(int maxBatch) {
        return jobControl.requestDrain(maxBatch);
    }
}
\`\`\`

Ưu điểm:

- JMX annotation tập trung ở facade.
- Service vẫn nhận AOP advice qua interface injection.
- Không expose các method nghiệp vụ khác.
- \`ObjectName\` ổn định khi implementation đổi.
- Dễ quan sát/kiểm thử hợp đồng riêng.

Tuy nhiên facade vẫn phải dùng reference đến **Spring proxy** của service nếu muốn advice áp dụng. Nếu facade tự tạo \`new JobControlService()\` thay vì injection từ context, các interceptor Spring AOP sẽ không tự tham gia.

## 11. Thứ tự khởi tạo bean và exporter

Một nguy cơ là exporter hoặc một bean liên quan khiến service được tạo **trước khi** tất cả post-processor/proxy infrastructure cần thiết sẵn sàng.

Các dấu hiệu:

- Bean runtime không phải proxy dù bạn kỳ vọng AOP.
- Transaction advice không chạy cho lời gọi JMX.
- Log Spring có thông tin bean không đủ điều kiện cho mọi \`BeanPostProcessor\`.
- Exporter có thể nhận target hoặc reference khác với bean mà module khác injection.
- Metadata MBean khác những annotation developer nhìn thấy trong source.

Cách xử lý:

1. Tránh khởi tạo business service từ constructor/static initializer của infrastructure bean.
2. Để Spring quản lý lifecycle và dependency injection.
3. Không gọi JMX operation trong constructor hoặc quá sớm ở \`@PostConstruct\`.
4. Hạn chế tùy biến \`BeanFactoryPostProcessor\`/\`BeanPostProcessor\` nếu không cần thiết.
5. Đọc proxy type và metadata sau khi context khởi tạo.
6. Dùng integration test thay vì chỉ unit test trực tiếp target object.

Không tạo một thứ tự khởi tạo bằng \`@DependsOn\` một cách máy móc khi chưa xác định dependency thật. \`@DependsOn\` có thể ảnh hưởng bean initialization order nhưng không giải quyết mọi xung đột AOP/metadata.

## 12. Proxy tự gọi method nội bộ: self-invocation

Spring AOP dựa trên proxy. Một method trong target gọi method khác qua \`this.method()\` thường **không đi qua proxy**.

\`\`\`java
@Service
public class JobControlService {

    @Transactional
    public void drainTransactional() {
        // ...
    }

    public void drainAll() {
        this.drainTransactional();
    }
}
\`\`\`

Nếu JMX gọi \`drainAll()\` qua proxy, lời gọi ban đầu có thể đi qua proxy; nhưng call từ \`drainAll\` đến \`drainTransactional\` là self-invocation bên trong target và thường không kích hoạt một interceptor transaction mới.

Vì thế không suy luận “đã export qua AOP proxy thì mọi method bên trong đều được advise”. Thiết kế service boundaries và invocation paths đúng với mô hình proxy.

## 13. Lựa chọn proxy-target-class

Spring AOP có thể được cấu hình để dùng class-based proxy:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

Hoặc cấu hình transaction proxy phù hợp theo phiên bản:

\`\`\`java
@EnableTransactionManagement(proxyTargetClass = true)
\`\`\`

Việc chọn CGLIB có thể làm các method trên class target dễ tiếp cận hơn, nhưng không nên dùng nó làm biện pháp duy nhất để “sửa” metadata JMX.

Những rủi ro vẫn còn:

- Method \`final\` không thể được subclass override để advice theo cách thông thường.
- \`private\` method không được advise như public method trên proxy.
- Self-invocation không tự đi qua proxy.
- Exporter/assembler vẫn cần đọc annotation đúng.
- Bean có thể có nhiều advisor/interceptor với thứ tự khác nhau.

Management facade tách biệt thường là lựa chọn dễ dự đoán khi bề mặt JMX cần ổn định lâu dài.

## 14. Metadata assembler và proxy-visible method

Một \`MetadataMBeanInfoAssembler\` cần kết hợp:

- Những method mà MBean có thể expose.
- Annotation mô tả attribute/operation.
- Kiểu tham số và kiểu trả về.
- Tên/description/impact của operation.
- Attribute read/write access.
- Notification metadata nếu có.

Nếu method có annotation nhưng không có đường gọi phù hợp qua bean đang export, có thể phát sinh lỗi khi đăng ký hoặc invocation.

Vì vậy cần kiểm chứng hai lớp:

\`\`\`text
Lớp metadata:
  MBeanInfo có operation mong muốn?

Lớp thực thi:
  MBeanServer.invoke có thực thi operation
  và có chạy advice cần thiết không?
\`\`\`

Đọc \`MBeanInfo\` chỉ chứng minh operation được công bố; nó không tự chứng minh transaction, logging, security hoặc retry advice đã thực thi.

## 15. Cấu hình assembler tường minh khi cần

Với \`MBeanExporter\` thủ công, Spring cho phép cung cấp \`MBeanInfoAssembler\` để điều khiển metadata của MBean.

Ví dụ ý tưởng:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

AnnotationJmxAttributeSource attributeSource =
    new AnnotationJmxAttributeSource();

MetadataMBeanInfoAssembler assembler =
    new MetadataMBeanInfoAssembler(attributeSource);

MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(assembler);
\`\`\`

Đây là phần cấu hình minh họa, chưa đầy đủ một exporter chạy độc lập. Cần cấu hình bean cần export, ObjectName, MBeanServer và lifecycle thích hợp.

Tránh đồng thời cấu hình nhiều exporter cho cùng bean/ObjectName. Khi có annotation exporter tích hợp, nên dùng cơ chế đó nếu không thật sự cần customize assembler.

## 16. Sai lệch giữa metadata và runtime type

Giả sử interface:

\`\`\`java
public interface Operations {
    void start();
}
\`\`\`

Implementation:

\`\`\`java
public class OperationsImpl implements Operations {
    @Override
    public void start() { ... }

    @ManagedOperation
    public void internalReset() { ... }
}
\`\`\`

Nếu Spring tạo JDK proxy chỉ implement \`Operations\`, phương thức \`internalReset()\` không nằm trong proxy interface. Một assembler đọc implementation method rồi expose nó mà runtime proxy không cung cấp đường gọi thích hợp có thể gây lỗi.

Cách giảm rủi ro:

- Đừng đánh dấu method nội bộ nếu không muốn expose.
- Nếu cần operation, đưa nó vào management interface rõ ràng hoặc facade.
- Đối chiếu metadata với loại proxy thực tế.
- Test \`MBeanServer.invoke\` và kiểm tra tác dụng/exception.
- Không ép unwrap proxy hay dùng reflection vào target chỉ để bypass thiết kế AOP.

## 17. Kiểm tra thứ tự advice và hành vi operation

Một method được nhiều advice bao quanh:

\`\`\`text
JMX invocation
    |
    v
Proxy
    |
    +--> Security advice
    +--> Logging advice
    +--> Transaction advice
    |
    v
Target method
\`\`\`

Thứ tự advice ảnh hưởng hành vi. Ví dụ security cần thực thi trước một operation có tác dụng phụ; transaction boundary có thể cần bao toàn bộ logic cập nhật trạng thái.

Spring AOP có \`@Order\`, \`Ordered\` và quy tắc infrastructure advisor cụ thể để điều khiển thứ tự, nhưng không nên suy đoán từ thứ tự annotation trong source code.

Ví dụ \`@Transactional\` nằm ngay trên \`@ManagedOperation\` không tự xác định interceptor nào chạy trước. Cần xem advisor configuration và cách Spring proxy thực tế được tạo.

## 18. Kiểm chứng proxy trong ApplicationContext

Sau khi context khởi tạo:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("jobControlService");

System.out.println(
    "Runtime type: " + bean.getClass().getName()
);
System.out.println(
    "Is AOP proxy: " + AopUtils.isAopProxy(bean)
);
System.out.println(
    "Target class: " +
        AopUtils.getTargetClass(bean).getName()
);
\`\`\`

Nếu muốn xem advisor, khi bean phù hợp với \`Advised\`:

\`\`\`java
import org.springframework.aop.framework.Advised;

if (bean instanceof Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
\`\`\`

Không tự cho rằng mọi AOP proxy đều implement \`Advised\` hoặc cho phép truy cập đầy đủ target; một số proxy có thể dùng thiết lập opaque hoặc cơ chế khác.

## 19. Kiểm chứng MBeanInfo thực tế

Dùng đúng MBeanServer mà exporter đã đăng ký:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "app.management:type=JobControl,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "Attribute %s (%s) readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "Operation " + op.getName() +
        " -> " + op.getReturnType()
    );
}
\`\`\`

Với ví dụ \`JobControlService\`, mong muốn có attribute \`PendingJobs\` và operation \`requestDrain(int)\` khi metadata exporter hỗ trợ đúng.

Nếu một operation không có trong \`MBeanInfo\`, đừng kết luận AOP advice không chạy; trước hết xác định metadata assembler có công bố method hay không.

## 20. Kiểm chứng invocation và advice

Khi \`requestDrain(int)\` đã xuất hiện:

\`\`\`java
Object result = server.invoke(
    name,
    "requestDrain",
    new Object[] { 3 },
    new String[] { "int" }
);

System.out.println(result);
\`\`\`

Để xác minh transaction advice trong ứng dụng thật, nên dùng một integration test với transaction manager và dependency thích hợp, ghi nhận hành vi commit/rollback hoặc log interceptor test được kiểm soát.

Không dùng \`@Transactional\` trên một ví dụ chỉ cập nhật field trong memory rồi kết luận transaction chắc chắn chạy: transaction hiệu lực với tài nguyên phù hợp và invocation path qua proxy.

## 21. Những lỗi thường gặp

### 21.1. Annotation có nhưng MBean không xuất hiện

Kiểm tra:

1. Bean có được Spring tạo và scan không?
2. Exporter đã bật chưa?
3. ObjectName có hợp lệ và không trùng không?
4. Exporter dùng MBeanServer nào?
5. Có exception trong quá trình export không?
6. Có class/interface/proxy nào làm metadata detection thay đổi không?

### 21.2. MBean xuất hiện nhưng thiếu operation

Kiểm tra annotation location, proxy-visible methods, assembler, overload/signature và metadata thực tế trong \`MBeanInfo\`.

### 21.3. Operation gọi được nhưng transaction advice không chạy

Kiểm tra exporter có trỏ tới proxy hay target, Spring bean có thực sự được auto-proxy không, self-invocation, advisor selection và transaction manager.

### 21.4. Exporter bị lỗi vì method không tồn tại trên proxy

Trường hợp này thường gặp khi metadata được xây từ implementation trong khi runtime object là JDK proxy với interface hẹp. Chọn interface/facade quản trị tương thích hoặc cấu hình export theo cách phù hợp, không bypass proxy tùy tiện.

### 21.5. Tên MBean thay đổi khi đổi proxy

Đừng tạo ObjectName chỉ từ \`bean.getClass().getName()\`, vì proxy class có thể khác implementation. Dùng \`@ManagedResource(objectName = "...")\` hoặc naming strategy ổn định.

### 21.6. Nhiều exporter cùng một bean

\`@EnableMBeanExport\`, Spring Boot auto-configuration và \`MBeanExporter\` thủ công có thể dẫn tới export trùng khi cấu hình chồng chéo. Kiểm kê exporter và xác định quyền sở hữu ObjectName thay vì dùng \`REPLACE_EXISTING\` để che lỗi.

## 22. Ví dụ trình tự kiểm chứng từng lớp

\`\`\`text
Step A: Spring context
  - Có bean hay không?
  - Bean runtime là target hay AOP proxy?
  - Advisors có được áp dụng không?

Step B: Exporter
  - Exporter nào được khởi tạo?
  - MBeanServer nào được sử dụng?
  - NamingStrategy / assembler nào?

Step C: Metadata
  - MBeanInfo có attribute và operation dự kiến?
  - Signature đúng Java types?

Step D: Invocation
  - Client gọi được operation?
  - AOP advice cần thiết chạy?
  - Business state thay đổi như mong đợi?

Step E: Lifecycle
  - MBean được register/unregister đúng?
  - Proxy và client không gọi trước khi exporter sẵn sàng?
\`\`\`

Quy trình này tách lỗi metadata khỏi lỗi proxy/invocation, giảm việc thử thay AOP configuration khi nguyên nhân thật là sai ObjectName hoặc sai MBeanServer.

## 23. Khi nào dùng management facade?

Nên cân nhắc facade riêng khi:

- Service nghiệp vụ có nhiều interface và advisor.
- JDK proxy không expose hết method quản trị mong muốn.
- Muốn giữ ObjectName ổn định dù implementation bị refactor.
- Muốn bảo vệ service khỏi phơi bày quá nhiều method.
- Cần tách quản trị khỏi transaction/security của tầng nghiệp vụ mà vẫn gọi qua đúng service proxy.
- Có client JMX dài hạn phụ thuộc metadata rõ ràng.
- Cần kiểm thử bề mặt quản trị độc lập với AOP internals.

Mẫu thiết kế:

\`\`\`text
JMX -> ManagementFacade -> BusinessInterfaceProxy -> Target
\`\`\`

Không có một thứ tự proxy/exporter duy nhất giải quyết mọi dự án; management facade giúp ranh giới rõ và bền vững hơn.

## 24. Câu hỏi tự kiểm tra

1. Vì sao một Spring bean có \`@ManagedOperation\` chưa chắc xuất hiện như mong đợi khi dùng AOP proxy?
2. JDK dynamic proxy khác CGLIB proxy ở cách expose method nào?
3. \`MetadataMBeanInfoAssembler\` và \`MBeanServer\` đảm nhiệm hai trách nhiệm gì khác nhau?
4. Vì sao phải kiểm chứng cả \`MBeanInfo\` và invocation thực tế?
5. Khi JMX gọi operation qua Spring proxy, advice có thể được áp dụng thế nào?
6. Self-invocation ảnh hưởng ra sao tới transaction advice?
7. Vì sao không nên dùng class name của proxy làm ObjectName?
8. Trường hợp nào khiến exporter nhận bean trước khi post-processing hoàn tất?
9. Management facade giúp giảm coupling với AOP/proxy như thế nào?
10. Vì sao \`@EnableTransactionManagement\` không tự đảm bảo transaction hoạt động khi thiếu transaction manager?

## 25. Ghi nhớ

\`\`\`text
Spring bean definition
      |
      v
Bean initialization / BeanPostProcessors
      |
      v
AOP proxy (nếu được tạo)
      |
      v
MBeanExporter
      |
      +--> naming strategy -> ObjectName
      |
      +--> metadata assembler -> MBeanInfo
      |
      v
MBeanServer registration
      |
      v
Client attribute access / operation invoke
      |
      v
Proxy/advice/target theo đường gọi thực tế
\`\`\`

**Nguyên tắc quan trọng:** khi JMX và AOP cùng xuất hiện, hãy kiểm tra **object thực tế được exporter dùng**, **metadata được assembler tạo** và **đường gọi qua proxy**. Một annotation có trong source không đủ chứng minh operation đã được expose hoặc advice sẽ chạy. Thiết kế management facade và dùng integration test trên MBeanServer thật giúp giữ bề mặt quản trị ổn định.