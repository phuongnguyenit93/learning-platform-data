# Annotation không được nhận diện do proxy interface trong Spring Framework JMX

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Chẩn đoán sự cố  
> **Bài học:** Annotation không được nhận diện do proxy interface

## 1. Mục tiêu bài học

Trong ứng dụng Spring, một bean có thể được gắn \`@ManagedResource\`, \`@ManagedAttribute\` hoặc \`@ManagedOperation\`, nhưng khi mở JConsole thì MBean không xuất hiện, thiếu attribute hoặc thiếu operation. Một nguyên nhân khó nhìn thấy là **bean được thay bằng AOP proxy**, đặc biệt JDK dynamic proxy chỉ công bố các interface mà nó triển khai.

Sau bài học, bạn có thể:

- Phân biệt implementation class, management interface và proxy object thực tế trong Spring ApplicationContext.
- Giải thích vì sao JDK dynamic proxy không expose mọi public method trên target class.
- Xác định annotation JMX đang nằm trên class/method nào và exporter/assembler đang quan sát đối tượng nào.
- Phân biệt **MBean không được đăng ký**, **MBean có mặt nhưng thiếu metadata**, và **metadata có mặt nhưng invocation thất bại**.
- Kiểm tra \`AopUtils\`, \`MBeanInfo\`, \`ObjectName\`, \`MBeanServer\` và cấu hình \`MBeanExporter\`.
- Lựa chọn cách sửa: interface phù hợp, management facade, class-based proxy hoặc cấu hình exporter/metadata assembler có kiểm chứng.
- Viết integration test phòng hồi quy thay vì chỉ dựa vào việc code biên dịch được.

## 2. Biểu hiện thường gặp

Ví dụ Spring bean:

\`\`\`java
public interface JobService {
    void startJob();
}

@Service
@ManagedResource(
    objectName = "app.management:type=JobService,name=main"
)
public class JobServiceImpl implements JobService {

    @Override
    @Transactional
    @ManagedOperation(description = "Start job")
    public void startJob() {
        // Logic nghiệp vụ.
    }

    @ManagedOperation(description = "Internal maintenance")
    public void maintenance() {
        // Method không thuộc JobService interface.
    }
}
\`\`\`

Ứng dụng có AOP tạo JDK dynamic proxy. Người phát triển kỳ vọng MBean chứa hai operation \`startJob\` và \`maintenance\`, nhưng thực tế có thể thấy một trong các tình huống:

1. Không tìm thấy MBean tại \`app.management:type=JobService,name=main\`.
2. MBean tồn tại nhưng không có \`maintenance\`.
3. MBean có operation trong metadata nhưng lời gọi \`invoke\` thất bại.
4. Operation gọi được nhưng AOP advice như transaction/security không hoạt động theo dự kiến.
5. Exporter ném exception tại startup liên quan tới metadata, class/interface hoặc method lookup.

Không nên quy mọi lỗi trên thành một vấn đề. Có trường hợp **annotation không được phát hiện**, có trường hợp **phát hiện đúng annotation nhưng method không thể được gọi qua proxy**, và có trường hợp **exporter sử dụng server/tên khác**.

## 3. Sơ đồ đường đi

\`\`\`text
JobServiceImpl target
  - @ManagedResource
  - @ManagedOperation startJob()
  - @ManagedOperation maintenance()
                 |
                 v
           Spring AOP
                 |
                 v
       JDK dynamic proxy
       implements JobService
       exposes startJob()
       NOT maintenance()
                 |
                 v
      Spring JMX exporter
                 |
                 +--> Annotation metadata lookup
                 +--> Operation/attribute assembly
                 +--> ObjectName registration
                 |
                 v
            MBeanServer
                 |
                 v
        JConsole / JMX client
\`\`\`

Sơ đồ thể hiện rủi ro về **đối tượng exporter nhận và phương thức proxy có thể thực thi**. Nó không khẳng định mọi phiên bản Spring sẽ bỏ qua annotation implementation khi có proxy: Spring có cơ chế tra cứu target class và annotation metadata. Hành vi thực tế còn tùy exporter, assembler, proxy strategy và phiên bản thư viện.

## 4. JDK dynamic proxy là gì?

JDK dynamic proxy là một object được tạo tại runtime để triển khai các interface Java:

\`\`\`java
public interface JobService {
    void startJob();
}
\`\`\`

Proxy có thể được lấy bằng:

\`\`\`java
JobService service = context.getBean(JobService.class);
\`\`\`

Nhưng object runtime không phải instance trực tiếp của \`JobServiceImpl\`. Các method Java có thể gọi qua proxy chủ yếu là những method thuộc interface được proxy triển khai.

\`\`\`text
Proxy API:
  startJob()        OK (nằm trong JobService)
  maintenance()     KHÔNG có trên JobService
\`\`\`

Một method public trên target **không mặc nhiên có mặt trong proxy interface**. Điều này ảnh hưởng management operation nếu exporter/adapter được thiết kế để gọi qua proxy.

### So sánh JDK proxy và CGLIB

| Điểm | JDK dynamic proxy | Class-based/CGLIB proxy |
|---|---|---|
| Dạng đối tượng | Implement các interface | Subclass của target class |
| Phương thức expose qua type | Chủ yếu method trên interface | Method có thể truy cập theo target class |
| Có cần interface? | Có | Không bắt buộc |
| Method chỉ tồn tại trên implementation | Không phải method của proxy interface | Có thể truy cập khi thỏa điều kiện |
| Giới hạn AOP | Self-invocation, advisor matching, interface surface | Self-invocation, final/private method, advisor matching |
| Quan hệ với JMX | Cần đồng bộ interface/metadata/invocation | Không loại bỏ nhu cầu kiểm tra metadata |

Chuyển sang class-based proxy đôi khi khắc phục giới hạn interface nhưng **không phải thuốc chữa cho mọi lỗi annotation JMX**.

## 5. Annotation nằm ở đâu?

Có thể gặp nhiều kiểu khai báo.

### 5.1. Annotation trên implementation

\`\`\`java
@Service
@ManagedResource(
    objectName = "app.management:type=Worker,name=main"
)
public class WorkerServiceImpl implements WorkerService {

    @ManagedOperation
    public void restart() {
        // ...
    }
}
\`\`\`

### 5.2. Annotation trên management interface

\`\`\`java
@ManagedResource(
    objectName = "app.management:type=Worker,name=main"
)
public interface WorkerManagement {

    @ManagedOperation
    void restart();
}
\`\`\`

### 5.3. Annotation trên facade riêng

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Worker,name=main"
)
public class WorkerManagementFacade {

    private final WorkerService workerService;

    public WorkerManagementFacade(
            WorkerService workerService
    ) {
        this.workerService = workerService;
    }

    @ManagedOperation
    public void restart() {
        workerService.restart();
    }
}
\`\`\`

Không có quy tắc Java chung bảo đảm một annotation trên implementation sẽ tự xuất hiện trên JDK proxy interface. Spring JMX metadata handling có thể tìm annotation qua cấu trúc target/interface theo implementation cụ thể; cần kiểm thử đúng phiên bản và đường exporter đang chạy.

**Lựa chọn kiến trúc rõ ràng nhất khi cần ranh giới quản trị ổn định:** management facade riêng, chỉ expose operation được phép và gọi service qua Spring-managed dependency.

## 6. Tách ba tầng lỗi để tránh sửa nhầm

| Tầng | Triệu chứng | Điểm cần kiểm tra |
|---|---|---|
| Registration | MBean không tồn tại | Exporter, ObjectName, MBeanServer, bean discovery |
| Metadata | MBean có nhưng thiếu operation/attribute | Annotation source, assembler, target type, proxy-visible methods |
| Invocation | Metadata có nhưng gọi lỗi | Proxy interface, chữ ký method, runtime object, advice, business exception |

Ví dụ:

\`\`\`java
ObjectName name = new ObjectName(
    "app.management:type=Worker,name=main"
);

boolean registered = server.isRegistered(name);
\`\`\`

Nếu \`false\`, không nên bắt đầu bằng cách sửa \`@ManagedOperation\`. Trước hết xác minh exporter đã đăng ký bean vào đúng server/tên.

Nếu \`true\`, đọc \`MBeanInfo\`:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
\`\`\`

Nếu method có trong metadata, bước kế tiếp là test \`invoke\`, không tiếp tục suy đoán annotation chưa được phát hiện.

## 7. Kiểm tra bean runtime có phải AOP proxy không

Spring cung cấp \`org.springframework.aop.support.AopUtils\`.

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("jobServiceImpl");

System.out.println(
    "Runtime type: " + bean.getClass().getName()
);
System.out.println(
    "Is proxy: " + AopUtils.isAopProxy(bean)
);
System.out.println(
    "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean)
);
System.out.println(
    "CGLIB proxy: " + AopUtils.isCglibProxy(bean)
);
System.out.println(
    "Target class: " + AopUtils.getTargetClass(bean).getName()
);
\`\`\`

Các API này cho phép xác định loại proxy và target class một cách an toàn hơn việc đoán từ chuỗi tên \`$Proxy...\` hoặc \`$$SpringCGLIB$$...\`.

Lưu ý \`AopUtils.getTargetClass\` trả loại target theo metadata có sẵn; nó không phải cơ chế tự lấy instance target bằng reflection. Không sửa cấu hình để unwrap target và gọi thẳng method chỉ nhằm vượt lỗi JMX, vì như vậy có thể bỏ qua advice cần thiết.

## 8. Kiểm tra method thực sự có trên interface nào

Giả sử:

\`\`\`java
Object bean = context.getBean("jobServiceImpl");
Class<?>[] interfaces = bean.getClass().getInterfaces();

for (Class<?> itf : interfaces) {
    System.out.println(itf.getName());
}
\`\`\`

Với JDK proxy, hãy xác định các interface phù hợp, đặc biệt interface chứa management method muốn công bố.

Có thể kiểm tra:

\`\`\`java
for (var method : JobService.class.getMethods()) {
    System.out.println(method);
}
\`\`\`

Nếu \`maintenance\` không thuộc \`JobService\`, một JDK proxy chỉ dựa vào \`JobService\` không thể nhận lời gọi \`maintenance()\` như một method của interface ấy.

Một chú ý: Spring proxy có thể triển khai nhiều interface, bao gồm infrastructure interface. Không dùng việc proxy có nhiều interface làm bằng chứng mọi method implementation đều expose.

## 9. Tại sao annotation có thể bị mất khỏi đường metadata?

Java reflection phân biệt method được khai báo trên:

\`\`\`text
JobService.startJob()
JobServiceImpl.startJob()
\`\`\`

Annotation gắn ở method implementation không tự trở thành annotation của method interface theo quy tắc Java reflection đơn thuần.

Một metadata source dựa trên interface method có thể không thấy annotation đặt trên implementation nếu không có cơ chế tìm kiếm thêm. Ngược lại, Spring Framework có một số tiện ích tìm method cụ thể nhất và annotation theo target type, nên không nên khẳng định “JDK proxy luôn làm mất @ManagedOperation”.

Câu hỏi đúng là:

- Exporter đang lấy metadata từ type nào?
- Assembler đang đọc \`Method\` đại diện cho interface hay target?
- Annotation source có xử lý proxy/interface không?
- MBean registration adapter có thể invoke method được expose không?

Đây là lý do cần **runtime metadata inspection**, không chỉ đọc source code.

## 10. AnnotationJmxAttributeSource và MetadataMBeanInfoAssembler

Trong Spring Framework JMX, annotation-based metadata có thể liên quan tới:

\`\`\`text
AnnotationJmxAttributeSource
    |
    v
MetadataMBeanInfoAssembler
    |
    v
ModelMBeanInfo
    |
    v
Spring MBeanExporter / ModelMBean
\`\`\`

\`AnnotationJmxAttributeSource\` cung cấp metadata từ Spring JMX annotations. \`MetadataMBeanInfoAssembler\` tạo MBeanInfo cho attributes, operations và notifications phù hợp.

Tuy nhiên:

- Assembler không thể tự bảo đảm mọi method bên trong target gọi được qua proxy.
- Metadata có thể bị giới hạn bởi các method mà export adapter xử lý.
- Exporter có thể dùng assembler khác với mặc định.
- Một proxy custom có thể che mất thông tin target type.
- Cấu hình scanner, bean name và object naming strategy cũng ảnh hưởng registration.

Trong một ứng dụng có nhiều exporter, kiểm tra exporter nào thực sự đăng ký ObjectName cần chẩn đoán.

## 11. Ví dụ chẩn đoán đầy đủ

### 11.1. Interface nghiệp vụ

\`\`\`java
package example.jmx;

public interface BillingOperations {
    String settle(String batchId);
}
\`\`\`

### 11.2. Target implementation

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "app.management:type=Billing,name=main"
)
public class BillingService implements BillingOperations {

    @Override
    @Transactional
    @ManagedOperation(description = "Settle a billing batch")
    public String settle(String batchId) {
        return "accepted:" + batchId;
    }

    @ManagedOperation(description = "Reset local diagnostic state")
    public void resetDiagnostics() {
        // Method chỉ nằm trên implementation.
    }
}
\`\`\`

### 11.3. Java configuration

\`\`\`java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@ComponentScan(basePackageClasses = BillingService.class)
@EnableTransactionManagement
@EnableMBeanExport
public class BillingConfig {
}
\`\`\`

Đoạn này minh họa cấu hình proxy/annotation export. \`@EnableTransactionManagement\` cần transaction manager phù hợp để advice có hiệu lực; annotation không tự cung cấp transaction manager.

### 11.4. Inspect bean

\`\`\`java
Object bean = context.getBean("billingService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

Nếu \`isJdkDynamicProxy=true\`, cần kiểm tra interface của proxy và vị trí annotation. Dù method \`settle\` thuộc interface, \`resetDiagnostics\` chỉ có trên target nên có thể không gọi được nếu exporter dùng proxy interface làm invocation surface.

### 11.5. Inspect JMX

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "app.management:type=Billing,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " -> " +
        operation.getReturnType()
    );
}
\`\`\`

Ví dụ sử dụng platform server; nếu exporter dùng server tùy biến, cần truy vấn đúng bean MBeanServer.

## 12. Giải pháp 1: management interface rõ ràng

Thay vì để một method quản trị chỉ xuất hiện trên implementation:

\`\`\`java
public interface BillingManagement {
    String settle(String batchId);
    void resetDiagnostics();
}
\`\`\`

Implementation có thể implement interface:

\`\`\`java
public class BillingService
        implements BillingOperations, BillingManagement {

    @Override
    @ManagedOperation
    public String settle(String batchId) {
        return "accepted:" + batchId;
    }

    @Override
    @ManagedOperation
    public void resetDiagnostics() {
        // ...
    }
}
\`\`\`

Nếu proxy được tạo với cả hai interface, các method quản trị có đường gọi phù hợp qua JDK proxy. Tuy nhiên vẫn cần kiểm tra annotation source/exporter có nhận diện metadata và expose đúng như mong muốn.

Chú ý management interface không nên là bản sao toàn bộ business interface. Chỉ công bố những operation an toàn, có ý nghĩa quản trị và được phép gọi.

## 13. Giải pháp 2: management facade tách biệt

Một thiết kế thường dễ dự đoán hơn:

\`\`\`text
JMX client
    |
    v
BillingManagementFacade @ManagedResource
    |
    v
BillingOperations (Spring AOP proxy)
    |
    v
BillingService target
\`\`\`

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=Billing,name=main"
)
public class BillingManagementFacade {

    private final BillingOperations billingOperations;

    public BillingManagementFacade(
            BillingOperations billingOperations
    ) {
        this.billingOperations = billingOperations;
    }

    @ManagedOperation(
        description = "Settle a billing batch"
    )
    public String settle(String batchId) {
        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("batchId required");
        }
        return billingOperations.settle(batchId);
    }
}
\`\`\`

Facade là một Spring bean độc lập dùng metadata quản trị riêng, trong khi service nghiệp vụ vẫn nhận transaction/logging/security advice qua Spring proxy.

Ưu điểm:

- Exporter có một management class với method public rõ ràng.
- Chỉ expose operation đã được lựa chọn.
- Không để JDK proxy của service quyết định toàn bộ management API.
- Giữ ObjectName ổn định khi implementation đổi.
- Dễ bổ sung validation, authorization, audit và test.

Nếu facade cũng bị proxy bởi AOP, vẫn cần kiểm tra nó được export như thế nào. Facade giảm coupling, không miễn trừ nguyên tắc proxy/metadata của Spring.

## 14. Giải pháp 3: class-based proxy

Spring hỗ trợ class-based proxy khi phù hợp:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

hoặc với transaction infrastructure theo phiên bản:

\`\`\`java
@EnableTransactionManagement(proxyTargetClass = true)
\`\`\`

Với CGLIB proxy, method trên target class thường vẫn là method có thể gọi trên proxy subclass, miễn không bị giới hạn bởi \`final\`, visibility và cách advice áp dụng.

Tuy nhiên:

- Một method \`final\` không thể được subclass override để intercept theo cơ chế này.
- Self-invocation qua \`this\` vẫn thường bypass advice.
- Annotation metadata chưa chắc được export đúng nếu assembler tùy biến.
- Proxy-target-class có thể tác động tới nhiều bean khác, không chỉ một MBean.
- Không nên đổi toàn bộ proxy strategy chỉ để che một thiết kế management API chưa rõ.

Dùng khi phù hợp kiến trúc AOP chung, đồng thời xác minh lại MBeanInfo và invocation.

## 15. Giải pháp 4: cấu hình exporter và assembler có chủ đích

Trong cấu hình thủ công:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

AnnotationJmxAttributeSource source =
    new AnnotationJmxAttributeSource();

MetadataMBeanInfoAssembler assembler =
    new MetadataMBeanInfoAssembler(source);

MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(assembler);
\`\`\`

Đây chỉ là minh họa cấu hình metadata. Một exporter hoàn chỉnh còn cần MBeanServer, bean mapping/ObjectName và lifecycle Spring.

Điều chỉnh assembler chỉ có ý nghĩa nếu lỗi thực sự nằm ở metadata source/assembly. Nó không tạo thêm method vào JDK proxy, không tự xử lý authorization và không sửa lỗi exporter được trỏ tới MBeanServer sai.

Một số trường hợp cần \`InterfaceBasedMBeanInfoAssembler\` hoặc một management interface tường minh thay vì annotation metadata. Khi đó phải hiểu mục tiêu của assembler: chọn những method interface nào được expose; không nên đổi assembler mà không có hợp đồng quản trị rõ ràng.

## 16. Kiểm tra chính xác MBeanInfo

Đọc từng operation cùng signature:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] params = op.getSignature();
    for (int i = 0; i < params.length; i++) {
        if (i > 0) {
            System.out.print(", ");
        }
        System.out.print(params[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

Nếu \`settle(java.lang.String)\` có mặt, client có thể thử:

\`\`\`java
Object result = server.invoke(
    name,
    "settle",
    new Object[] { "batch-001" },
    new String[] { "java.lang.String" }
);
\`\`\`

Nếu operation không có, không nên gọi bừa signature khác; trước hết kiểm tra exporter/assembler và annotation.

Nếu operation có mà invoke lỗi, xem exception chain, runtime proxy và business logic. \`ReflectionException\` thường gợi ý vấn đề reflection/signature nhưng không phải lúc nào cũng do annotation.

## 17. Kiểm tra @ManagedAttribute với JDK proxy

Vấn đề tương tự có thể xảy ra với getter/setter.

\`\`\`java
public interface QueueService {
    int getDepth();
}
\`\`\`

Implementation:

\`\`\`java
@ManagedAttribute
public int getDepth() {
    return 12;
}

@ManagedAttribute
public void setWorkerLimit(int limit) {
    // ...
}
\`\`\`

Nếu JDK proxy chỉ có \`getDepth\`, method \`setWorkerLimit\` không nằm trên proxy interface. Tùy metadata exporter và invocation path, attribute writable có thể không xuất hiện hoặc bị lỗi khi ghi.

Nên:

1. Kiểm tra \`MBeanAttributeInfo.isReadable()\` và \`isWritable()\`.
2. Đối chiếu getter/setter trên proxy interface.
3. Xác định annotation được đặt ở đâu.
4. Thử \`getAttribute\`/\`setAttribute\` trong test.
5. Xem xét management facade nếu cần giới hạn bề mặt JMX.

Không coi Java getter/setter có trong target là bằng chứng client JMX sẽ đọc/ghi được.

## 18. Kiểm tra ObjectName và MBeanServer đúng trước khi đổ lỗi proxy

Một lỗi nhìn giống “annotation không được nhận diện” có thể chỉ là truy vấn sai registry.

Ví dụ:

\`\`\`java
MBeanServer actual =
    context.getBean("managementServer", MBeanServer.class);

ObjectName name = new ObjectName(
    "app.management:type=Billing,name=main"
);

System.out.println(
    actual.isRegistered(name)
);
\`\`\`

Nếu exporter được cấu hình \`setServer(customMBeanServer)\` nhưng JConsole đang quan sát platform MBeanServer, không thấy MBean là hiện tượng đúng.

Cần phân biệt:

- \`@ManagedResource.objectName\` khai báo tên explicit.
- \`ObjectNamingStrategy\` có thể quyết định tên thực tế khác.
- Nhiều exporter có thể đăng ký MBean trên các server khác nhau.
- RegistrationPolicy có thể làm một registration bị bỏ qua hoặc thay thế.

Vì vậy bước đầu chẩn đoán là xác định exporter, server và ObjectName trước khi chỉnh AOP.

## 19. Thứ tự tạo proxy, exporter và metadata

Trong Spring container:

\`\`\`text
Bean definitions
       |
       v
BeanPostProcessors / AutoProxyCreator
       |
       v
Target bean initialized
       |
       v
AOP proxy (nếu áp dụng)
       |
       v
MBeanExporter nhận bean reference
       |
       v
Metadata assembler / naming
       |
       v
MBeanServer registration
\`\`\`

Đây là thứ tự khái quát trong các trường hợp bình thường. Không xem nó là một bảo đảm tuyệt đối cho mọi \`BeanFactoryPostProcessor\`, infrastructure bean và vòng đời phức tạp.

Nếu bean bị tạo quá sớm trước khi đủ auto-proxy infrastructure, exporter có thể nhận target thay vì proxy, khiến kết quả khác mong đợi. Một dấu hiệu là Spring log rằng bean không đủ điều kiện nhận toàn bộ BeanPostProcessor.

Để chẩn đoán:

- Kiểm tra bean/runtime type sau context initialization.
- Xác định exporter bean và dependency của nó.
- Kiểm tra không tự tạo target bằng \`new\` ngoài Spring context.
- Tránh lấy business bean quá sớm từ BeanPostProcessor/infrastructure code.
- Dùng integration test để quan sát ObjectName/metadata/invocation thực tế.

## 20. Aspect advice có chạy khi gọi qua JMX không?

Một operation có \`@Transactional\` có thể được gọi qua:

\`\`\`text
MBeanServer
   |
   +--> Spring AOP proxy -> Transaction advice -> target
   |
   +--> Target trực tiếp -> có thể bypass advice
\`\`\`

Có \`@ManagedOperation\` và \`@Transactional\` trên cùng method **không bảo đảm** transaction interceptor đã chạy khi JMX invoke.

Cần xác minh:

1. Bean được auto-proxy thật.
2. Exporter giữ reference thích hợp.
3. Operation được gọi qua proxy-visible method.
4. Transaction manager tồn tại và advisor áp dụng.
5. Không bị self-invocation bypass.
6. Test kiểm tra tác dụng transaction thật, không chỉ một counter trong memory.

Với operation quản trị quan trọng, management facade gọi business interface proxy có thể làm đường gọi dễ kiểm soát hơn.

## 21. Integration test phòng hồi quy

Một test Spring có thể xác nhận ba mức:

\`\`\`text
A. Bean:
   AopUtils.isJdkDynamicProxy(bean) == true/false theo cấu hình

B. Registration/metadata:
   server.isRegistered(name) == true
   MBeanInfo có operation bắt buộc

C. Invocation:
   server.invoke(...) thực thi thành công
   trạng thái/transaction/advice đúng
\`\`\`

Ví dụ assertion:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

boolean exposed = Arrays.stream(info.getOperations())
    .anyMatch(op ->
        op.getName().equals("settle")
        && op.getSignature().length == 1
        && op.getSignature()[0].getType()
            .equals("java.lang.String")
    );

assertTrue(exposed);

Object result = server.invoke(
    name,
    "settle",
    new Object[] { "batch-001" },
    new String[] { "java.lang.String" }
);

assertEquals("accepted:batch-001", result);
\`\`\`

Đây là đoạn test yêu cầu \`server\`, \`name\` được khởi tạo và các import thích hợp. Khi có effect nghiệp vụ, test cần chạy với fixture an toàn và xác minh state thực.

Không nên chỉ assert \`@ManagedOperation\` tồn tại trong reflection trên class target; điều đó chưa kiểm tra exporter/proxy.

## 22. Một bảng quyết định sửa lỗi

| Quan sát | Nguyên nhân nghi ngờ | Hướng xử lý |
|---|---|---|
| Bean không tồn tại trong context | Scan/configuration | Sửa component scan/bean definition |
| Bean tồn tại, JDK proxy, MBean không có | Exporter annotation detection/naming/lifecycle | Kiểm tra exporter/server/ObjectName và metadata source |
| MBean có nhưng thiếu method chỉ nằm trên target | Proxy interface không expose method hoặc assembler bỏ qua | Management interface/facade |
| MBeanInfo có method nhưng invoke lỗi | Invocation path/signature/business method | Đọc cause và proxy type |
| Annotation trên interface, exporter không thấy | Quy tắc lookup annotation của assembler | Kiểm tra phiên bản/config, dùng facade hoặc metadata phù hợp |
| Sau khi đổi CGLIB thì hoạt động | Giới hạn JDK proxy surface có vai trò | Duy trì test và đánh giá tác động proxy strategy |
| Operation chạy nhưng advice mất | Exporter gọi target hoặc self-invocation | Kiểm tra proxy reference, facade và transaction config |
| Chỉ JConsole không thấy, local server query thấy | Client kết nối khác server | Cấu hình connector cùng MBeanServer |

## 23. Những sai lầm cần tránh

### Sai lầm 1: Chuyển proxy-target-class=true ngay lập tức

Có thể ảnh hưởng nhiều Spring bean và không giải quyết lỗi exporter/server hoặc metadata source.

### Sai lầm 2: Dời mọi annotation lên interface mà không kiểm tra

Không có bảo đảm mọi assembler/phiên bản sẽ diễn giải interface annotation giống nhau. Cần test metadata và invocation.

### Sai lầm 3: Dùng target object trực tiếp để bypass proxy

Có thể làm mất transaction/security/logging advice và tạo đường gọi quản trị khác với đường nghiệp vụ.

### Sai lầm 4: Tưởng thấy annotation trong source là đủ

Cần đọc \`MBeanInfo\` do MBeanServer công bố.

### Sai lầm 5: Chỉ test JConsole

JConsole có giới hạn UI. Nên dùng JMX API để đối chiếu ObjectName, metadata và invoke.

### Sai lầm 6: Thay registration policy để che lỗi

\`REPLACE_EXISTING\` hoặc \`IGNORE_EXISTING\` không giải quyết method bị ẩn khỏi proxy. Xung đột ObjectName là loại lỗi riêng.

### Sai lầm 7: Export mọi public method từ service

Có thể làm lộ service nội bộ hoặc operation nguy hiểm. Nên dùng management API hẹp.

## 24. Checklist chẩn đoán

- [ ] Có đúng Spring bean và bean name không?
- [ ] Bean runtime là target, JDK dynamic proxy hay CGLIB proxy?
- [ ] Target class được xác định bằng \`AopUtils.getTargetClass\`?
- [ ] Management method có trên proxy interface không?
- [ ] Annotation nằm trên interface, implementation hay facade?
- [ ] Exporter được bật và nhận đúng bean?
- [ ] Assembler/annotation source nào đang được sử dụng?
- [ ] ObjectName đúng và MBeanServer đúng?
- [ ] \`isRegistered\` trả true?
- [ ] \`MBeanInfo\` có attribute/operation đúng signature?
- [ ] \`invoke\` hoặc \`getAttribute\` gọi được?
- [ ] AOP advice cần thiết thật sự chạy?
- [ ] Không có exporter trùng hoặc bean tạo quá sớm?
- [ ] Có integration test bảo vệ hợp đồng JMX?

## 25. Bài tập thực hành

**Bối cảnh:** \`OrderService\` interface chỉ khai báo:

\`\`\`java
public interface OrderService {
    void processOrder(String orderId);
}
\`\`\`

Implementation thêm:

\`\`\`java
@ManagedOperation
public void clearTemporaryState() {
    // ...
}
\`\`\`

Ứng dụng dùng JDK dynamic proxy và \`@EnableMBeanExport\`. JConsole không thấy \`clearTemporaryState\`.

**Câu hỏi A:** Vì sao chỉ nhìn \`OrderServiceImpl.class.getDeclaredMethods()\` chưa đủ kết luận?

Vì JMX exporter có thể làm việc với proxy interface, và management surface thực tế nằm trong \`MBeanInfo\`.

**Câu hỏi B:** Có thể sửa thế nào mà không cần mở rộng \`OrderService\` business interface?

Tạo \`OrderManagementFacade\` riêng, dùng \`@ManagedResource\` và chỉ expose \`clearTemporaryState\` nếu hành động này thực sự phù hợp để quản trị. Facade injection một service interface cần thiết.

**Câu hỏi C:** Làm sao chứng minh lỗi đã được sửa?

Xác minh ObjectName có đăng ký, \`MBeanInfo\` có operation \`clearTemporaryState\`, và \`MBeanServer.invoke\` chạy thành công trên fixture an toàn.

## 26. Câu hỏi tự kiểm tra

1. JDK dynamic proxy có expose mọi public method implementation không?
2. Vì sao annotation implementation có thể không hiện ra khi metadata được đọc trên interface method?
3. \`AopUtils.isJdkDynamicProxy\` cung cấp bằng chứng gì?
4. MBean không tồn tại khác gì MBean thiếu operation?
5. CGLIB proxy có giải quyết tất cả vấn đề annotation và invocation không?
6. Vì sao management facade thường phù hợp hơn việc expose toàn bộ service?
7. Khi nào cần đọc \`MBeanInfo\` và khi nào cần thử \`invoke\`?
8. Exporter dùng target trực tiếp có thể ảnh hưởng AOP advice ra sao?
9. ObjectName và MBeanServer sai có thể tạo triệu chứng tương tự lỗi annotation thế nào?
10. Tại sao integration test tốt hơn việc chỉ kiểm tra annotation trong source?

## 27. Ghi nhớ

\`\`\`text
Target implementation
  @ManagedResource / @ManagedOperation
           |
           v
      Spring AOP
           |
     JDK proxy interface
           |
           v
   Exporter + metadata assembler
           |
           v
        MBeanInfo
           |
           v
      MBeanServer
           |
           v
        JMX client
\`\`\`

**Nguyên tắc cốt lõi:** khi annotation JMX “biến mất” trong ứng dụng có AOP, trước tiên xác định bean thực tế là proxy nào, exporter đọc metadata từ đâu và MBeanServer công bố hợp đồng gì. Đừng mặc định JDK proxy luôn xóa annotation hoặc CGLIB luôn giải quyết mọi thứ. Với management API cần ổn định, tách facade rõ ràng, dùng ObjectName cố định và kiểm thử cả registration, metadata lẫn invocation.