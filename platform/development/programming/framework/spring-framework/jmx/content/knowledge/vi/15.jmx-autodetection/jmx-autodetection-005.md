# Spring Framework JMX — Autodetection trên bean proxied

## 1. Vấn đề cần hiểu

Spring Framework cho phép xuất các bean ra JMX thông qua \`MBeanExporter\`. Một chế độ hữu ích là **autodetection**: exporter tìm các bean phù hợp trong \`ApplicationContext\` thay vì buộc chúng ta liệt kê từng bean trong \`setBeans\`.

Nhưng bean thực tế được Spring quản lý không phải lúc nào cũng chính là một instance của class nghiệp vụ. Spring AOP có thể đặt một **proxy** bên ngoài bean để áp dụng transaction, caching, security, retry hoặc các advice khác. Vì vậy, khi JMX exporter tìm và phân tích bean, nó có thể gặp:

- Object thực thi thuộc class \`OrderService\`.
- Proxy JDK chỉ triển khai interface \`OrderOperations\`.
- Proxy dạng subclass do CGLIB tạo.
- Metadata annotation nằm trên class triển khai nhưng không trực tiếp có trên proxy.
- Phương thức được JMX mô tả bởi target class nhưng gọi thực tế phải đi qua proxy.

Chủ đề “autodetection trên bean proxied” là cách Spring JMX **phát hiện đúng MBean, lấy đúng metadata, gọi đúng phương thức, và không làm mất các interceptor quan trọng** khi bean được proxy.

\`\`\`text
Spring ApplicationContext
       |
       +---- orderService (Spring bean name)
                      |
                 AOP proxy
                 /       \
             JDK proxy   class-based proxy
                 \       /
                  target OrderService
                      |
            @ManagedResource / @ManagedOperation
                      |
             Spring MBeanExporter
            autodetect + assembler
                      |
              ModelMBean / MBeanServer
                      |
                    JConsole
\`\`\`

Bài học phân biệt rõ: **bean có được chọn để export không** và **operation được gọi qua proxy hay qua target** là hai câu hỏi khác nhau. Cả hai cần được giải quyết đúng.

## 2. Những khái niệm cơ bản

| Khái niệm | Ý nghĩa |
|---|---|
| \`MBeanExporter\` | Spring component đăng ký bean vào \`MBeanServer\` |
| Autodetection | Chọn một số bean để export tự động dựa trên cơ chế và metadata cấu hình |
| \`@ManagedResource\` | Annotation Spring đánh dấu resource quản trị |
| \`@ManagedAttribute\` | Đánh dấu getter/setter muốn công bố thành JMX attribute |
| \`@ManagedOperation\` | Đánh dấu phương thức muốn công bố thành JMX operation |
| \`MetadataMBeanInfoAssembler\` | Tạo metadata MBean dựa trên thông tin annotation |
| AOP proxy | Object trung gian nhận lời gọi và chạy interceptor/advice |
| JDK dynamic proxy | Proxy dựa vào interface Java |
| CGLIB class-based proxy | Proxy tạo subclass của class mục tiêu trong các điều kiện hỗ trợ |
| Target class | Class thực thi nghiệp vụ đằng sau proxy |
| \`ObjectName\` | Định danh MBean trong registry của JMX |

Một bean Spring có thể đồng thời có tên \`orderService\`, object thực tế là JDK proxy, và class nghiệp vụ là \`OrderServiceImpl\`. Nếu nhìn chỉ vào \`proxy.getClass()\`, ta có thể bỏ lỡ annotation được khai báo tại class thực thi.

## 3. Autodetection của Spring JMX hoạt động ở đâu?

\`MBeanExporter\` nhận trách nhiệm export MBean. Khi bật autodetection với cấu hình phù hợp, nó duyệt các bean ứng viên và sử dụng chiến lược/assembler để quyết định bean nào có thể công bố làm JMX resource.

Trong Spring, annotation-driven export thường được bật qua:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Lựa chọn này thiết lập infrastructure dựa trên annotation. Các bean được gắn \`@ManagedResource\` cùng metadata thích hợp sẽ là ứng viên được export.

Cách cấu hình tường minh:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetect(true);
\`\`\`

Tuy nhiên, **chỉ bật \`setAutodetect(true)\` không có nghĩa mọi POJO đều được export có chọn lọc theo annotation**. Cần cấu hình \`MBeanInfoAssembler\`, \`ObjectNamingStrategy\` phù hợp nếu muốn dựa trên metadata Spring; đồng thời xem chính xác cơ chế của phiên bản Spring đang sử dụng. Đối với ứng dụng theo annotation, \`@EnableMBeanExport\` thường giảm sự phức tạp này.

MBean exporter cũng có thể nhận \`setBeans(Map)\` để đăng ký các bean cụ thể. Tự động tìm kiếm và explicit mapping là hai hình thức chọn bean khác nhau; nên chủ động xác định phạm vi để tránh đăng ký trùng.

## 4. Tại sao AOP proxy làm autodetection phức tạp?

Giả sử bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderService,name=primary"
)
public class OrderServiceImpl {

    @ManagedOperation(description = "Reprocess failed orders")
    public void reprocessFailedOrders() {
        // ...
    }
}
\`\`\`

Khi Spring tạo bean, một \`BeanPostProcessor\` có thể thay object đó bằng proxy. Ví dụ nếu method có \`@Transactional\` hoặc class bị áp dụng aspect phù hợp, caller nhận proxy thay vì target object trực tiếp.

Với JDK proxy:
- Object runtime thường là một class proxy do JDK tạo, không phải \`OrderServiceImpl\`.
- Proxy chỉ cung cấp phương thức có trong các interface nó triển khai (cùng các method Object phù hợp).
- Annotation \`@ManagedResource\` trên \`OrderServiceImpl\` không tự xuất hiện như annotation trực tiếp trên runtime proxy class.
- Spring cần cơ chế tìm target class/metadata phù hợp để xác định resource.

Với class-based proxy:
- Runtime proxy kế thừa class nghiệp vụ, do đó thường phơi bày nhiều method của class hơn.
- Nhưng annotation resolution, method interception và quy tắc final/private methods vẫn cần được hiểu.
- Không nên cho rằng dùng CGLIB loại bỏ hoàn toàn mọi giới hạn AOP/JMX.

Vì vậy một autodetection tốt phải hiểu **bean trong Spring container** thay vì kiểm tra đơn giản \`bean.getClass().isAnnotationPresent(ManagedResource.class)\`.

## 5. Ví dụ JDK dynamic proxy: interface và implementation

Định nghĩa interface:

\`\`\`java
package com.example.jmx;

public interface OrderMaintenance {
    long getFailedOrders();
    void retryFailedOrders();
}
\`\`\`

Implementation có JMX annotation:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary",
    description = "Runtime order maintenance"
)
public class OrderMaintenanceImpl implements OrderMaintenance {
    private final AtomicLong failedOrders = new AtomicLong();

    @Override
    @ManagedAttribute(description = "Failed order count")
    public long getFailedOrders() {
        return failedOrders.get();
    }

    @Override
    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        // Business call, potentially wrapped in transaction.
    }
}
\`\`\`

Trong Spring config:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class ManagementConfig {

    @Bean
    public OrderMaintenance orderMaintenance() {
        return new OrderMaintenanceImpl();
    }
}
\`\`\`

**Quan trọng:** \`@EnableAspectJAutoProxy\` chỉ bật infrastructure AOP, không tự tạo proxy cho bean nếu không có advisor/aspect áp dụng. Để có JDK proxy thực sự, cần một advice/transactional configuration phù hợp và Spring quyết định dùng proxy theo interface.

Ví dụ có thể gắn \`@Transactional\` trong method business (khi transaction management được bật), hoặc aspect theo \`execution(* ...)\`. Dùng AOP thế nào không thay đổi yêu cầu rằng JMX exporter phải xử lý metadata trên target class và đường gọi trên proxy một cách đúng đắn.

### Câu hỏi thiết kế

Nếu \`retryFailedOrders()\` không được khai báo trong interface \`OrderMaintenance\`, JDK proxy sẽ không có method public đó. Dù target class có annotation \`@ManagedOperation\`, việc gọi qua proxy có thể không hoạt động theo kỳ vọng. Vì vậy, operation quản trị muốn gọi xuyên JDK proxy nên **có mặt trong interface mà proxy expose**, hoặc ứng dụng cần một management facade/cách proxy khác.

## 6. Cách tự kiểm tra proxy thực tế

Một cách đơn giản là sử dụng utility của Spring AOP:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("orderMaintenance");

System.out.println("isAopProxy=" + AopUtils.isAopProxy(bean));
System.out.println("isJdkDynamicProxy="
    + AopUtils.isJdkDynamicProxy(bean));
System.out.println("isCglibProxy="
    + AopUtils.isCglibProxy(bean));
System.out.println("runtimeClass=" + bean.getClass().getName());
System.out.println("targetClass="
    + AopUtils.getTargetClass(bean).getName());
\`\`\`

Các utility này phân loại proxy phổ biến do Spring AOP tạo. Với proxy tùy biến hoặc object không phải Spring AOP proxy, hãy xem tài liệu của cơ chế proxy tương ứng.

Khi \`isJdkDynamicProxy=true\`, kiểm tra các interfaces mà proxy thực sự triển khai và operation JMX cần gọi. Khi \`isCglibProxy=true\`, kiểm tra method có thể override/intercept hay không và annotation có được assembler tìm thấy không.

Không nên ép kiểu proxy JDK sang implementation class:

\`\`\`java
OrderMaintenanceImpl concrete =
    (OrderMaintenanceImpl) applicationContext.getBean("orderMaintenance");
\`\`\`

Điều này có thể ném \`ClassCastException\`. Thay vào đó, dùng interface:

\`\`\`java
OrderMaintenance management =
    applicationContext.getBean(OrderMaintenance.class);
\`\`\`

## 7. Vai trò của metadata assembler và naming strategy

Khi export POJO có annotation, thường có hai phần quan trọng:

- \`MetadataMBeanInfoAssembler\`: tìm metadata JMX để tạo thông tin attributes/operations.
- \`MetadataNamingStrategy\` hoặc naming strategy phù hợp: xác định ObjectName của resource.

Ví dụ cấu hình minh họa:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Bean
AnnotationJmxAttributeSource annotationJmxAttributeSource() {
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

    MetadataNamingStrategy strategy =
        new MetadataNamingStrategy();
    strategy.setAttributeSource(source);
    return strategy;
}

@Bean
MBeanExporter exporter(
        MetadataMBeanInfoAssembler assembler,
        MetadataNamingStrategy namingStrategy) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setAssembler(assembler);
    exporter.setNamingStrategy(namingStrategy);
    exporter.setAutodetect(true);
    return exporter;
}
\`\`\`

Cấu hình trên nhằm minh họa các điểm mở rộng. Nếu ứng dụng cũng dùng \`@EnableMBeanExport\`, có nguy cơ tạo nhiều exporter cùng muốn đăng ký một bean. Trong một ứng dụng, hãy chọn **một cơ chế export chính**, hoặc tách rõ phạm vi bean giữa các exporter.

Khi bean bị proxy, hai thành phần trên cần nhận được metadata hợp lệ; nếu ObjectName có được nhưng operation metadata lại thiếu, phải chẩn đoán assembler/method exposure chứ không chỉ naming.

## 8. AOP và vấn đề chọn target hay proxy để export

Một nhầm lẫn thường gặp là “để JMX thấy annotation trên class thật, ta cứ lấy target và export trực tiếp”. Cách này có thể làm mất hành vi AOP.

Giả sử:

\`\`\`java
@Transactional
public void retryFailedOrders() {
    // Ghi DB, gửi command, thay đổi state.
}
\`\`\`

Trong ứng dụng Spring, transaction interceptor thường nằm ở **proxy invocation path**. Nếu operation JMX gọi trực tiếp target bỏ qua proxy, transactional advice có thể không chạy. Vấn đề tương tự có thể xuất hiện với security checks, metrics, retry và audit advice.

Hướng thiết kế nên là:

1. JMX metadata tìm đúng class/method cần công bố.
2. JMX invoker gọi qua một object có hành vi AOP mong muốn.
3. Operation cần export tương thích với interface khi dùng JDK proxy.
4. Các operation nguy hiểm được validate/authorize ngay tại management boundary, không dựa duy nhất vào assumptions về AOP.
5. Quan sát bằng integration tests hoặc runtime diagnostics khi triển khai hệ thống.

Một giải pháp giảm phụ thuộc proxy internals là tạo **management facade** riêng:

\`\`\`text
JMX ManagementFacade (exported)
        |
        v
OrderMaintenance service interface
        |
        v
Spring AOP proxy (transactions/security)
        |
        v
Business implementation
\`\`\`

Facade được export trực tiếp, nhưng khi gọi business service sẽ đi qua interface/proxy do Spring quản lý. Nhờ vậy đường transaction/security được thể hiện rõ hơn.

## 9. Ví dụ management facade tránh vấn đề method exposure

Service nghiệp vụ:

\`\`\`java
package com.example.jmx;

public interface OrderMaintenance {
    long getFailedOrders();
    void retryFailedOrders();
}
\`\`\`

Management facade:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary",
    description = "Operational control interface"
)
public class OrderMaintenanceJmxFacade {
    private final OrderMaintenance service;

    public OrderMaintenanceJmxFacade(OrderMaintenance service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of failed orders")
    public long getFailedOrders() {
        return service.getFailedOrders();
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        service.retryFailedOrders();
    }
}
\`\`\`

Spring wiring:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxFacadeConfig {

    @Bean
    public OrderMaintenanceJmxFacade orderMaintenanceJmxFacade(
            OrderMaintenance orderMaintenance) {

        return new OrderMaintenanceJmxFacade(orderMaintenance);
    }
}
\`\`\`

Để \`OrderMaintenance\` thực sự là proxy, ứng dụng vẫn cần advice/transactional setup áp dụng cho service bean. Facade nhận bean theo interface, vì vậy nếu Spring inject proxy, lời gọi từ facade sẽ đi qua proxy.

Lợi ích:
- JMX annotations nằm trên một class quản trị ổn định.
- Không cần đưa mọi operation JMX vào interface nghiệp vụ.
- Dễ giới hạn permissions và validation cho đường JMX.
- Business AOP được thực thi qua dependency đã inject.
- Tên và metadata JMX độc lập hơn với refactor implementation.

Nhược điểm là thêm một lớp adapter/facade. Với hệ thống có operation nhạy cảm, chi phí này thường chấp nhận được.

## 10. JDK proxy và CGLIB: khác nhau ở đâu?

### JDK dynamic proxy

JDK proxy hoạt động thông qua interface. Khi bean thực thi nhiều public method nhưng interface chỉ có một phần, proxy thường chỉ expose phần interface đó.

Ví dụ:

\`\`\`java
interface WorkerTasks {
    void execute();
}

class WorkerTasksImpl implements WorkerTasks {
    @Override
    public void execute() {}

    @ManagedOperation
    public void refreshInternalState() {}
}
\`\`\`

Nếu Spring tạo JDK proxy cho \`WorkerTasks\`, method \`refreshInternalState\` không có trên interface, nên không thể gọi nó trực tiếp thông qua proxy được cast sang interface này. JMX adapter cũng có thể gặp vấn đề nếu cố invoke method target không có trên proxy.

Hướng xử lý: thêm operation cần gọi vào interface quản trị phù hợp, dùng class-based proxy nếu hợp lệ, hoặc ưu tiên management facade.

### CGLIB class-based proxy

CGLIB proxy thường là subclass của implementation:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

Nếu có advisor áp dụng, cấu hình này yêu cầu kiểu proxy dựa trên class trong nhiều trường hợp.

Lưu ý:
- \`final\` class không thể subclass theo cơ chế CGLIB thông thường.
- \`final\` method không được override để áp dụng advice theo phương thức đó.
- Private methods không trở thành AOP join points qua proxy-based method interception.
- Không nên kết luận rằng tất cả annotation trên target đều được hiển thị trực tiếp ở runtime proxy subclass.
- \`@EnableAspectJAutoProxy\` vẫn cần actual advisor/aspect để bean được proxy.

Khi chỉ cần export JMX ổn định, đổi toàn bộ ứng dụng sang CGLIB **không nên là lựa chọn mặc định** chỉ để sửa một operation quản trị. Facade hoặc interface rõ thường dễ kiểm soát hơn.

## 11. Spring AOP self-invocation và JMX

Một tình huống quan trọng khác là self-invocation:

\`\`\`java
public class BillingService {

    public void runManualSettlement() {
        settleInternally(); // gọi trên chính this
    }

    @Transactional
    public void settleInternally() {
        // ...
    }
}
\`\`\`

Trong proxy-based Spring AOP, lời gọi \`this.settleInternally()\` thường **không đi qua proxy**, nên transactional advice trên method đó có thể không áp dụng như mong đợi.

Nếu JMX gọi \`runManualSettlement\` qua proxy, điều đó không tự làm lời gọi nội bộ \`settleInternally()\` trở thành lời gọi qua proxy. Cần tổ chức service boundary rõ, ví dụ tách component hoặc gọi qua Spring-managed dependency tương ứng.

Với các operation JMX thay đổi dữ liệu, không nên coi có \`@Transactional\` ở đâu đó trong call chain là bảo đảm transaction thực sự đang chạy. Hãy dùng integration tests để kiểm chứng hành vi cần thiết.

## 12. Khi nào autodetection chọn nhầm hoặc bỏ sót bean?

Các tình huống thường gặp:

1. **Proxy che metadata**: lớp runtime proxy không có annotation trực tiếp, cơ chế dò tùy biến chỉ đọc \`bean.getClass()\`.
2. **Bean không nằm trong context được scan**: exporter thuộc context khác hoặc bean không được tạo.
3. **Annotation nằm trên class/method mà proxy không expose**: operation được mô tả nhưng lời gọi gặp giới hạn interface.
4. **Bean bị export hai lần**: vừa autodetection vừa explicit mapping hoặc nhiều exporter cùng scan.
5. **ObjectName trùng**: nhiều instances cùng \`@ManagedResource(objectName=...)\`.
6. **Assembler không phù hợp**: MBean được register nhưng metadata sai hoặc thiếu operation.
7. **MBeanServer khác nhau**: client nhìn sai registry.
8. **Proxy xuất hiện sau khi exporter đã chọn bean**: thứ tự lifecycle hoặc custom infrastructure bất thường.
9. **Bean đặc biệt/lazy/scoped**: proxy đại diện cho request/session hoặc target chỉ tồn tại khi scope đang active.

Không phải mọi “missing MBean” đều do JDK proxy. Phải tách bước phát hiện bean, tạo ObjectName, đăng ký, khám phá metadata và thực thi operation.

## 13. Quy trình chẩn đoán thực tế

Khi một bean có \`@ManagedResource\` nhưng không xuất hiện, có thể đi theo thứ tự sau.

### Bước 1: Xác định bean và proxy

\`\`\`java
Object bean = ctx.getBean("orderMaintenance");

System.out.println("Bean runtime = " + bean.getClass());
System.out.println("AOP proxy = " + AopUtils.isAopProxy(bean));
System.out.println("Target class = " + AopUtils.getTargetClass(bean));
\`\`\`

### Bước 2: Kiểm tra exporter

- Có \`MBeanExporter\` hay annotation-driven infrastructure trong context không?
- Cơ chế autodetection đã được bật và có metadata assembler thích hợp chưa?
- Có hai exporter cùng xử lý bean này không?
- Bean được export theo name/key nào?

### Bước 3: Kiểm tra ObjectName

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);

boolean registered = mbeanServer.isRegistered(name);
System.out.println("registered = " + registered);
\`\`\`

Nếu không đăng ký, xem log \`InstanceAlreadyExistsException\`, \`MalformedObjectNameException\`, lỗi detection hoặc exporter lifecycle.

### Bước 4: Đọc metadata JMX

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = mbeanServer.getMBeanInfo(name);
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
    for (var parameter : operation.getSignature()) {
        System.out.println("  param: " + parameter.getType());
    }
}
\`\`\`

Nếu operation không nằm trong metadata, khả năng liên quan \`@ManagedOperation\`, assembler hoặc cách Spring nhận diện target class.

### Bước 5: Gọi operation thử ở môi trường phù hợp

\`\`\`java
mbeanServer.invoke(
    name,
    "retryFailedOrders",
    new Object[0],
    new String[0]
);
\`\`\`

**Không chạy thao tác thay đổi dữ liệu trên production chỉ để thử JMX.** Trong test, thay operation có tác dụng phụ bằng một operation vô hại, hoặc dùng test data được kiểm soát.

### Bước 6: Xác nhận advice đã chạy

Có thể dùng:
- Logging trong AOP advice;
- Transaction synchronization hoặc kiểm tra transaction context thích hợp;
- Metrics và tracing;
- Integration test với service fake;
- Assertion về security/authorization boundary.

Chỉ \`invoke\` thành công không có nghĩa AOP advice đã chạy. Nếu target method vẫn được gọi nhưng proxy bị bypass, nghiệp vụ có thể thực thi trong điều kiện khác với lời gọi từ application code.

## 14. Ví dụ kiểm thử hợp đồng JMX với proxied service

Một cách kiểm thử là tạo Spring test context trong đó service bị AOP proxy và management facade được export.

Khung JUnit 5:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(JmxFacadeConfig.class)
class OrderMaintenanceJmxTest {

    @Autowired
    MBeanServer server;

    @Test
    void exportsManagementFacade() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.app:type=OrderMaintenance,name=primary"
        );

        assertTrue(server.isRegistered(name));

        var info = server.getMBeanInfo(name);
        assertTrue(
            java.util.Arrays.stream(info.getOperations())
                .anyMatch(op ->
                    op.getName().equals("retryFailedOrders"))
        );
    }
}
\`\`\`

Đây là **khung minh họa**, không phải test hoàn chỉnh chạy độc lập: test configuration cần định nghĩa một \`MBeanServer\` bean, service mock/fake, JMX exporter, và nếu mục tiêu là kiểm tra proxy thì phải thiết lập advice thực tế.

Trong thực tế, nên có hai nhóm assertion độc lập:
- Bean quản trị được đăng ký và có metadata dự kiến.
- Operation JMX gọi đúng service và kích hoạt AOP concern mong muốn.

Nếu chỉ test \`isRegistered\` thì chưa xác nhận được đường gọi qua proxy.

## 15. Bean scoped hoặc lazy có proxy

Không phải proxy nào cũng là AOP proxy dùng cho transaction. Spring có thể tạo scoped proxy cho bean có request/session/custom scope.

Ví dụ:

\`\`\`java
@Scope(
    value = "request",
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
@Component
class RequestState {
    // ...
}
\`\`\`

Một MBean có vòng đời ứng dụng thường không phù hợp để expose trực tiếp đối tượng cần request scope đang active. Khi JMX client truy cập từ thread không có request context, có thể xảy ra lỗi scope không hoạt động.

Với những state chỉ tồn tại theo request:
- Đừng tự động export mỗi request-scoped bean làm MBean.
- Ưu tiên một application-scoped management facade tổng hợp số liệu.
- Không đặt secrets, request headers hoặc identity user vào JMX ObjectName.
- Hạn chế cardinality của metrics và MBeans.

Bean lazy cũng cần cân nhắc: quá trình autodetection hoặc export có thể kích hoạt initialization tùy cơ chế. Đừng dựa vào giả định rằng mọi bean sẽ luôn được khởi tạo đúng thời điểm hoặc không bao giờ bị khởi tạo bởi JMX infrastructure.

## 16. Proxy và ObjectName: đừng dùng tên runtime class

Một naming strategy kém:

\`\`\`java
public ObjectName getObjectName(Object bean, String beanKey)
        throws MalformedObjectNameException {

    return new ObjectName(
        "com.example.app:type=" + bean.getClass().getSimpleName()
    );
}
\`\`\`

Với JDK proxy, runtime class có thể là class do JVM sinh (tên không biểu đạt nghiệp vụ). Với class-based proxy, tên runtime có thể chứa hậu tố proxy. Những chi tiết này có thể thay đổi khi cấu hình Spring/AOP đổi.

Thay bằng:
- \`beanKey\` ổn định được validate;
- Resource ID do bean quản trị cung cấp;
- Annotation metadata \`@ManagedResource(objectName=...)\`;
- ObjectName explicit mapping.

Ví dụ:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);
\`\`\`

Một JMX client không nên cần biết implementation có dùng JDK proxy hay CGLIB để tìm đúng MBean.

## 17. Bảo mật khi expose proxied bean

Một số ứng dụng dùng AOP để thi hành security hoặc audit. Khi JMX exporter đưa một method thành operation, cần xem đó là một đường gọi quản trị đặc biệt.

- Không giả định remote JMX client tự chịu các ràng buộc của HTTP security filter.
- Nếu dựa trên method security qua AOP, xác nhận operation JMX thật sự đi qua proxy.
- Quản lý authentication/authorization trên JMX connector/server.
- Dùng management facade để validate tham số, giới hạn thao tác và ghi audit.
- Không export các method nội bộ hoặc nhạy cảm chỉ vì chúng public.
- Không đưa password, token, user identity vào ObjectName hoặc dữ liệu notification.
- Với operation nguy hiểm, xác nhận hậu trạng thái và tránh retry mù khi không rõ đã thực thi hay chưa.

Spring AOP proxy là một phần thực thi, không thay thế bảo mật ở biên JMX.

## 18. Bảng vấn đề thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không thấy MBean đã annotate | Exporter/scan/metadata không đúng; ObjectName lỗi | Context, autodetection, log registration |
| Proxy JDK có MBean nhưng thiếu operation | Method không có trên interface hoặc assembler chọn sai | Interfaces, \`MBeanInfo\`, metadata source |
| Operation gọi được nhưng \`@Transactional\` không hoạt động | Target bị gọi trực tiếp hoặc self-invocation | Invocation path, facade, test transaction |
| \`ClassCastException\` khi lấy Spring bean | Cast JDK proxy sang implementation | Inject interface hoặc đổi thiết kế |
| \`InstanceAlreadyExistsException\` | Auto-export trùng hoặc tên tĩnh cho nhiều bean | Ownership, ObjectName, exporter count |
| Tên MBean có chuỗi proxy kỳ lạ | Naming từ \`getClass()\` runtime | Dùng tên logic/annotation |
| Scoped proxy lỗi khi JMX invoke | Scope không active | Application-scope management facade |
| CGLIB không intercept method | Method \`final\`/private hoặc proxy constraints | Method visibility và proxy design |
| JMX client tìm sai server | Exporter dùng server khác | Kiểm tra đúng \`MBeanServer\` |
| Callback/operation chạy ngoài context expected | JMX thread và application execution context khác nhau | Explicit security/context propagation |

## 19. Bài tập thực hành

### Bài 1: Tìm lỗi của JDK proxy

\`\`\`java
interface TaskService {
    int getQueueSize();
}

class TaskServiceImpl implements TaskService {
    @Override
    public int getQueueSize() { return 10; }

    @ManagedOperation
    public void clearQueue() {}
}
\`\`\`

Nếu Spring tạo JDK proxy theo interface \`TaskService\`, vì sao \`clearQueue()\` có thể khó export/invoke qua proxy?

**Gợi ý:** proxy không expose method đó vì nó không nằm trong interface. Nên đưa hành vi quản trị vào interface phù hợp hoặc sử dụng facade.

### Bài 2: Phân biệt annotation và proxy class

\`\`\`java
Object bean = ctx.getBean("taskService");
boolean annotated =
    bean.getClass().isAnnotationPresent(ManagedResource.class);
\`\`\`

Tại sao \`annotated == false\` chưa đủ để kết luận bean không có JMX annotation?

**Gợi ý:** runtime object có thể là proxy, annotation nằm trên target class. Spring metadata discovery cần xét target class.

### Bài 3: Tác động của self-invocation

Một method JMX được gọi qua proxy, sau đó gọi \`this.internalTransactionalMethod()\`. Transaction trên method nội bộ có chắc chắn chạy không?

**Gợi ý:** Với proxy-based AOP, self-invocation có thể bypass transactional advice. Tách boundary hoặc gọi qua Spring-managed collaborator.

### Bài 4: Chọn hướng sửa

Ứng dụng có hai bean cùng implementation class, đều có \`@ManagedResource(objectName="com.example:type=Worker")\`. Autodetection thất bại trên một bean vì tên trùng.

**Gợi ý:** Dùng ObjectName riêng theo role/instance, hoặc explicit mapping/naming strategy. Không đơn giản chuyển từ JDK proxy sang CGLIB để giải quyết lỗi tên.

### Bài 5: Thiết kế facade

Một service có transaction proxy, cần JMX operation \`rebuildIndex()\`. Hãy thiết kế một \`IndexMaintenanceJmxFacade\` có:
- \`@ManagedResource\` với ObjectName ổn định;
- \`@ManagedOperation\` trên \`rebuildIndex\`;
- Dependency vào \`IndexMaintenanceService\` interface;
- Log audit và validation;
- Unit/integration test kiểm tra gọi từ JMX đi qua service proxy.

### Bài 6: Vì sao không export request-scoped object trực tiếp?

**Gợi ý:** Một JMX call có thể chạy trên thread không có request scope; tốt hơn export một application-scoped bean tổng hợp trạng thái.

## 20. Ghi nhớ

Autodetection trong Spring JMX giúp giảm cấu hình thủ công, nhưng AOP proxy tạo ranh giới giữa **bean runtime**, **target class chứa annotation**, và **method thực sự có thể được gọi**. Với JDK proxy, interface là hợp đồng cực kỳ quan trọng; với CGLIB, cần hiểu giới hạn subclass/final methods. \`MBeanExporter\` và metadata assembler phải tìm được resource và công bố đúng contract.

Nếu operation JMX thay đổi dữ liệu, hãy kiểm tra cả **metadata được export** lẫn **đường gọi qua AOP proxy**. Một management facade riêng là lựa chọn dễ bảo trì khi muốn giữ transaction/security advice và giới hạn API quản trị. Tên JMX nên ổn định, không phụ thuộc vào tên class proxy, và kết quả cuối cần được kiểm tra qua \`MBeanServer\`, \`MBeanInfo\` cùng một phép thử invocation an toàn.