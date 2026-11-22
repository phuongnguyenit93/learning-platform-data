# Interface-based proxy che target class trong Spring Framework JMX và AOP

## Mục tiêu học tập

Trong Spring Framework, một bean có thể được bọc bởi **Spring AOP proxy**. Nếu proxy được tạo theo giao diện (interface-based proxy, thường là JDK dynamic proxy), kiểu object mà bên ngoài quan sát được có thể chỉ thể hiện các interface, trong khi lớp triển khai (target class) bị che khỏi các thao tác dựa trên runtime type. Điều này đặc biệt quan trọng khi \`MBeanExporter\` hoặc annotation-based JMX exporter cần tìm các method, \`@ManagedResource\` hay hợp đồng MBean từ target.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa target object, JDK dynamic proxy và class-based proxy.
- Nhận ra vì sao một Spring bean hoạt động bình thường nhưng JMX exporter có thể không đọc được metadata trên implementation class.
- Phân biệt **giao diện Spring AOP** và **management interface của JMX**.
- Chọn cách export phù hợp: interface quản lý tường minh, annotation metadata trên target, assembler, hoặc class-based proxy khi có lý do chính đáng.
- Dùng \`AopUtils\`, \`AopProxyUtils\`, \`MBeanInfo\` và \`MBeanServer\` để chẩn đoán.
- Viết integration test tái hiện vấn đề và xác minh cách xử lý.

## 1. Bối cảnh: hai hệ thống proxy khác nhau

Spring AOP và JMX đều có thể dùng ý tưởng “proxy”, nhưng chúng giải quyết hai vấn đề khác nhau:

- **Spring AOP proxy** chặn lời gọi Java tới Spring bean để áp dụng advice: transaction, logging, security, metrics hoặc các concern cắt ngang.
- **JMX ModelMBean/Standard MBean** công bố một management contract cho công cụ quản trị qua \`MBeanServer\`.
- **MBean client proxy**, ví dụ \`MBeanProxyFactoryBean\`, biến một Java method call ở phía client thành thao tác JMX tới \`ObjectName\`.

Bài này tập trung vào trường hợp **MBeanExporter nhận một Spring AOP interface-based proxy làm bean cần export**.

Mô hình:

\`\`\`text
Spring ApplicationContext
    |
    +-- Target object: OrderProcessor
    |       implements OrderOperations
    |       @ManagedResource trên implementation
    |
    +-- Spring AOP JDK proxy
            implements OrderOperations
            runtime class = com.sun.proxy... / jdk.proxy...
            |
            +-- advice (logging, transaction, ...)
            +-- delegate -> target OrderProcessor

MBeanExporter / JMX annotation discovery
    |
    +-- nhận bean reference từ ApplicationContext
    +-- cần xác định type, metadata, management API
    |
    v
MBeanServer registry
\`\`\`

Nếu framework introspect **proxy class** như thể đó là implementation gốc, annotation ở \`OrderProcessor\` có thể không xuất hiện trên proxy class. Ngoài ra, các method public chỉ có trên target class nhưng không nằm trong các interface được proxy implement sẽ không callable trực tiếp qua biến reference kiểu proxy.

Spring JMX có nhiều hỗ trợ dành cho AOP proxies, nhưng mức độ tự xử lý phụ thuộc Spring version, cách assembler/naming strategy được cấu hình, proxy type và đường exporter sử dụng. Do đó cần dựa vào runtime inspection, không kết luận tuyệt đối rằng mọi JDK proxy đều làm JMX hỏng.

## 2. JDK dynamic proxy che lớp triển khai thế nào?

Giả sử có giao diện nghiệp vụ:

\`\`\`java
package com.example.orders;

public interface OrderOperations {
    void processOrder(String orderId);
}
\`\`\`

Implementation:

\`\`\`java
package com.example.orders;

public class OrderProcessor implements OrderOperations {

    @Override
    public void processOrder(String orderId) {
        System.out.println("Processing " + orderId);
    }

    public int getPendingCount() {
        return 12;
    }

    public void resetStatistics() {
        System.out.println("Reset statistics");
    }
}
\`\`\`

Nếu Spring AOP dùng **JDK dynamic proxy**, object reference mà container trả ra có thể có dạng:

\`\`\`text
jdk.proxy2.$Proxy...
  implements OrderOperations
\`\`\`

Điểm quan trọng:

1. Proxy implement \`OrderOperations\` và có thể gọi \`processOrder\`.
2. Proxy thường không phải là subclass của \`OrderProcessor\`.
3. Vì vậy, \`proxy instanceof OrderProcessor\` có thể là \`false\`.
4. Method \`getPendingCount\` và \`resetStatistics\` không nằm trong \`OrderOperations\`, nên không thể được gọi qua interface này.
5. Annotation đặt trên implementation class không mặc nhiên trở thành annotation trên runtime class của proxy.

Ví dụ:

\`\`\`java
OrderOperations service = context.getBean(OrderOperations.class);

System.out.println(service.getClass());
System.out.println(service instanceof OrderProcessor);

// service.getPendingCount(); // Không biên dịch: interface thiếu method.
\`\`\`

Nếu lấy theo \`OrderProcessor.class\` thay vì \`OrderOperations.class\`, dependency lookup cũng có thể thất bại nếu exposed proxy type không assignable tới class đó.

Đây là một **vấn đề type visibility và contract**, không phải bằng chứng target đã biến mất. Target vẫn có thể tồn tại phía sau proxy và tiếp tục thực thi logic.

## 3. Interface-based proxy được tạo khi nào?

Spring AOP có thể tạo JDK dynamic proxy nếu target có interface phù hợp và cấu hình chọn proxy theo interface. Class-based proxy (thường được gọi là CGLIB proxy trong ngữ cảnh Spring) tạo subclass của target, vì vậy type và method visibility khác.

Những tình huống thường tạo Spring AOP proxy:

- \`@Transactional\` kết hợp transaction infrastructure.
- \`@Aspect\` chứa advice như \`@Around\`, \`@Before\`, \`@After\`.
- Các interceptor thông qua \`ProxyFactory\`.
- Một số cơ chế method security hoặc custom \`BeanPostProcessor\`.

**Lưu ý quan trọng:** Trong Spring Boot hoặc các phiên bản/framework setup khác nhau, chế độ class-based proxy có thể được bật mặc định hoặc được cấu hình tự động. Vì vậy không suy luận loại proxy chỉ từ việc nhìn thấy \`@Transactional\`.

Cần kiểm tra runtime:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderProcessor");

System.out.println("Runtime class: " + bean.getClass().getName());
System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
\`\`\`

Những kiểm tra này xác định lớp wrapper mà Spring đang cung cấp, không tự kết luận metadata JMX cuối cùng có đúng hay không. Phần đó cần xem \`MBeanInfo\` sau khi đăng ký.

## 4. Management interface khác business interface

Giả sử một ứng dụng dùng \`OrderOperations\` cho nghiệp vụ, nhưng muốn quản trị số đơn đang chờ qua JMX.

Bạn có thể tạo một hợp đồng quản lý riêng:

\`\`\`java
package com.example.orders;

public interface OrderAdminMBean {
    int getPendingCount();
    void resetStatistics();
}
\`\`\`

Sau đó implementation có thể implement cả hai:

\`\`\`java
package com.example.orders;

public class OrderProcessor
        implements OrderOperations, OrderAdminMBean {

    @Override
    public void processOrder(String orderId) {
        System.out.println("Processing " + orderId);
    }

    @Override
    public int getPendingCount() {
        return 12;
    }

    @Override
    public void resetStatistics() {
        System.out.println("Reset statistics");
    }
}
\`\`\`

Tuy nhiên, chỉ có interface \`OrderAdminMBean\` **chưa tự đảm bảo** một JDK proxy được tạo cho bean sẽ expose interface đó. Một proxy có thể chỉ được cấu hình để implement \`OrderOperations\`. Nếu exporter cần tìm/call management methods trên proxy, phải xem proxy thực sự implement những interface nào và exporter có cơ chế unwrap/adapter phù hợp hay không.

Ngoài ra, với Standard MBean theo JMX convention, interface \`OrderProcessorMBean\` mới khớp class \`OrderProcessor\`. Tên \`OrderAdminMBean\` ở ví dụ là **management interface tùy chọn** và cần adapter, assembler hoặc cấu hình phù hợp; không thể suy luận chỉ từ hậu tố \`MBean\` rằng JMX tự động nhận nó làm Standard MBean interface cho \`OrderProcessor\`.

Đây là lý do cần phân biệt *business API*, *Java proxy interfaces* và *JMX management API*.

## 5. Vấn đề annotation trên target class

Spring JMX cung cấp các annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
\`\`\`

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "com.example.orders:type=OrderAdmin,name=primary")
public class OrderProcessor implements OrderOperations {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation
    public void resetStatistics() {
        // ...
    }

    @Override
    public void processOrder(String id) {
        // ...
    }
}
\`\`\`

Khi Spring AOP bọc \`OrderProcessor\` trong JDK dynamic proxy:

- Annotation \`@ManagedResource\` vẫn nằm trên target class.
- Runtime proxy class không nhất thiết kế thừa annotation đó.
- Các management methods ngoài \`OrderOperations\` có thể không được expose trên proxy interfaces.
- Quá trình phát hiện bean dựa vào type/metadata cần có khả năng tìm target class và contract phù hợp.

\`AnnotationMBeanExporter\`, \`MetadataMBeanInfoAssembler\` và Spring AOP utilities có thể hỗ trợ xử lý metadata cho AOP proxies. Tuy nhiên, nếu bạn dùng assembler tùy biến đọc đơn giản \`bean.getClass().getAnnotation(...)\`, kết quả có thể khác hẳn vì lúc đó \`bean.getClass()\` là lớp proxy.

Không được tự “sửa” bằng cách ép kiểu:

\`\`\`java
OrderProcessor target = (OrderProcessor) context.getBean("orderProcessor");
\`\`\`

Với JDK proxy, phép cast có thể ném \`ClassCastException\`. Nếu cần thao tác với implementation type trong một thành phần nội bộ, thiết kế bean/proxy và interface injection đúng từ đầu sẽ an toàn hơn.

## 6. Tái hiện JDK proxy bằng ProxyFactory

Ví dụ độc lập sau tạo interface-based proxy một cách chủ động.

\`\`\`java
package com.example.orders;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;

public class JdkProxyExample {

    public static void main(String[] args) {
        OrderProcessor target = new OrderProcessor();

        ProxyFactory factory = new ProxyFactory();
        factory.setTarget(target);
        factory.setInterfaces(OrderOperations.class);
        factory.setProxyTargetClass(false);

        factory.addAdvice((MethodInterceptor) invocation -> {
            System.out.println("AOP before " +
                    invocation.getMethod().getName());
            return invocation.proceed();
        });

        Object proxy = factory.getProxy();

        System.out.println("proxyType = " + proxy.getClass().getName());
        System.out.println("isJdkProxy = "
                + AopUtils.isJdkDynamicProxy(proxy));
        System.out.println("isOrderProcessor = "
                + (proxy instanceof OrderProcessor));
        System.out.println("isOrderOperations = "
                + (proxy instanceof OrderOperations));

        ((OrderOperations) proxy).processOrder("A-123");
    }
}
\`\`\`

Trong cấu hình này, ta chủ động yêu cầu proxy implement \`OrderOperations\`, không phải class target. Nhờ vậy, khác biệt về type visibility trở nên rõ ràng.

Khi kiểm thử JMX, đừng chỉ nhìn vào việc object proxy có cùng \`getClass()\` với target hay không. Điều kiện cần là exporter có thể đăng ký object quản trị với metadata đúng, rồi client có thể truy cập attributes/operations dự kiến.

## 7. Đăng ký MBeanExporter: điều gì xảy ra khi truyền proxy?

Một \`MBeanExporter\` có thể nhận mapping giữa \`ObjectName\` và Spring bean:

\`\`\`java
@Bean
public MBeanExporter exporter(
        OrderOperations orderProcessor,
        MBeanServer mBeanServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(mBeanServer);
    exporter.setBeans(Map.of(
        "com.example.orders:type=OrderAdmin,name=primary",
        orderProcessor
    ));
    return exporter;
}
\`\`\`

Ở đây, \`orderProcessor\` có thể là một JDK proxy. MBeanExporter cần quyết định xem object có hợp đồng Standard MBean/MXBean hợp lệ hay cần dùng ModelMBean adapter và assembler.

Điều có thể xảy ra tùy cấu hình:

1. Exporter có thể sử dụng hỗ trợ nội bộ để xác định managed target type/metadata.
2. Assembler được cấu hình có thể nhìn proxy interfaces thay vì implementation.
3. Management methods không thuộc các interface mà proxy expose có thể không truy cập được bằng cách gọi thông thường.
4. Registration có thể thành công nhưng MBean thiếu attribute/operation mà người viết mong đợi.
5. Registration cũng có thể thất bại nếu metadata/type không tạo được một MBean contract hợp lệ.

Không nên diễn đạt lỗi này như một quy tắc tuyệt đối rằng “JDK proxy không thể xuất qua JMX”. Bản thân Spring có những cơ chế xử lý proxy; vấn đề thực tế là **khớp giữa object exporter nhận được, metadata assembler đọc và method mà proxy có thể gọi**.

## 8. Kiểm tra bean và target type bằng Spring AOP utilities

Một số API hữu ích:

\`\`\`java
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderProcessor");

Class<?> runtimeClass = bean.getClass();
Class<?> targetClass = AopUtils.getTargetClass(bean);
Class<?> ultimateTargetClass =
        AopProxyUtils.ultimateTargetClass(bean);

System.out.println("runtimeClass = " + runtimeClass.getName());
System.out.println("targetClass = " + targetClass.getName());
System.out.println("ultimateTargetClass = "
        + ultimateTargetClass.getName());
\`\`\`

Ý nghĩa:

- \`bean.getClass()\`: runtime class đang được injection cung cấp.
- \`AopUtils.isJdkDynamicProxy(bean)\`: xác định object có là JDK proxy theo cơ chế Spring AOP.
- \`AopUtils.getTargetClass(bean)\`: cố xác định target type phía sau AOP proxy khi có thông tin.
- \`AopProxyUtils.ultimateTargetClass(bean)\`: cố tìm ultimate target class qua các lớp proxy theo cơ chế Spring hỗ trợ.

Những utilities này phục vụ introspection. Chúng **không biến** JDK proxy thành instance có thể cast sang target class, cũng không tự động bổ sung các management methods thiếu trong proxy interface.

Không lạm dụng \`Advised.getTargetSource().getTarget()\` để bypass AOP rồi gọi trực tiếp target. Với scoped/dynamic target sources, việc lấy target có thể liên quan lifecycle và yêu cầu release. Hơn nữa, bypass AOP có thể bỏ qua transaction, security hoặc logging advice mà ứng dụng dựa vào.

## 9. Lựa chọn 1 — Xuất một management facade riêng

Đây thường là thiết kế ít bất ngờ nhất khi service nghiệp vụ có nhiều AOP advice.

\`\`\`java
package com.example.orders;

public interface OrderMetricsView {
    long getPendingCount();
}
\`\`\`

Service nghiệp vụ:

\`\`\`java
package com.example.orders;

public class OrderService implements OrderOperations, OrderMetricsView {
    private volatile long pendingCount = 12;

    @Override
    public void processOrder(String id) {
        // Business logic
    }

    @Override
    public long getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

Facade quản trị:

\`\`\`java
package com.example.orders;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=OrderMetrics,name=primary")
public class OrderMetricsAdmin {

    private final OrderMetricsView metrics;

    public OrderMetricsAdmin(OrderMetricsView metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return metrics.getPendingCount();
    }
}
\`\`\`

Java Config:

\`\`\`java
@Configuration
@EnableMBeanExport
public class OrderJmxConfiguration {

    @Bean
    public OrderMetricsAdmin orderMetricsAdmin(
            OrderMetricsView orderMetrics) {
        return new OrderMetricsAdmin(orderMetrics);
    }
}
\`\`\`

Cấu hình giả định đã có Spring bean \`OrderMetricsView\` tương ứng trong context. Nếu \`OrderService\` được AOP proxy theo \`OrderOperations\` mà không expose \`OrderMetricsView\`, bạn cần đảm bảo interface \`OrderMetricsView\` cũng được proxy expose hoặc tạo adapter đọc metric từ một dependency khác. Không dùng ví dụ này như phép màu khắc phục proxy interface bị thiếu.

**Ưu điểm của facade** là chỉ class chuyên quản trị mang \`@ManagedResource\`, tách management contract ra khỏi implementation nghiệp vụ bị AOP bọc. Việc exporter introspect facade đơn giản hơn và bề mặt JMX được giới hạn rõ ràng.

## 10. Lựa chọn 2 — Đưa management interface vào proxy interfaces

Nếu muốn exporter đăng ký trực tiếp bean đang được AOP proxy, có thể thiết kế một interface chứa các management methods và đảm bảo JDK proxy implement interface đó.

\`\`\`java
package com.example.orders;

public interface OrderManagement {
    int getPendingCount();
    void resetStatistics();
}
\`\`\`

Implementation:

\`\`\`java
public class OrderProcessor
        implements OrderOperations, OrderManagement {
    @Override
    public void processOrder(String id) { /* ... */ }

    @Override
    public int getPendingCount() { return 12; }

    @Override
    public void resetStatistics() { /* ... */ }
}
\`\`\`

Nếu tạo proxy thủ công:

\`\`\`java
ProxyFactory factory = new ProxyFactory();
factory.setTarget(new OrderProcessor());
factory.setInterfaces(OrderOperations.class, OrderManagement.class);
factory.setProxyTargetClass(false);

Object proxy = factory.getProxy();
\`\`\`

Khi đó, proxy có thể được cast sang \`OrderManagement\` và gọi hai method quản trị qua AOP layer. Tuy nhiên **JMX exporter vẫn cần assembler hoặc contract phù hợp**. \`OrderManagement\` không đương nhiên là Standard MBean interface vì tên không theo convention \`OrderProcessorMBean\` và runtime proxy class cũng không phải \`OrderProcessor\`.

Một cách cấu hình quản lý là \`InterfaceBasedMBeanInfoAssembler\` để chọn các method từ \`OrderManagement\` rồi dùng \`MBeanExporter\` export proxy. Cần kiểm tra metadata và dispatch thực tế của proxy trong version Spring đã chọn.

## 11. Lựa chọn 3 — Class-based proxy (proxyTargetClass)

Spring hỗ trợ class-based proxy để tạo subclass của target, thường hữu ích khi cần gọi method không nằm trong interface.

Ví dụ cấu hình Spring AOP:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
\`\`\`

Hoặc với \`ProxyFactory\`:

\`\`\`java
ProxyFactory factory = new ProxyFactory(new OrderProcessor());
factory.setProxyTargetClass(true);
Object proxy = factory.getProxy();
\`\`\`

Class-based proxy thường assignable tới target class, nên một số vấn đề type visibility của JDK proxy được giảm bớt. Tuy nhiên:

- Final class không thể được subclass; final method không thể được override để advice.
- Private methods không được advice theo cơ chế subclass proxy.
- Annotation introspection vẫn cần xác định đúng target class/method.
- Chọn class-based proxy không đảm bảo mọi method đều nên được xuất qua JMX.
- Thay đổi proxy strategy có thể ảnh hưởng toàn bộ ứng dụng; không nên bật toàn cục chỉ để chữa một MBean nếu management facade đáp ứng yêu cầu.

Đối với sản phẩm có nhiều module, lựa chọn mức proxy cụ thể phải xét transaction, security, performance và compatibility, không chỉ JMX.

## 12. Lựa chọn 4 — Dùng assembler tường minh thay vì suy đoán annotation

\`MBeanExporter\` có thể sử dụng \`MBeanInfoAssembler\` để kiểm soát management interface. Với interface-based assembler:

\`\`\`java
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

@Bean
public InterfaceBasedMBeanInfoAssembler managementAssembler() {
    InterfaceBasedMBeanInfoAssembler assembler =
            new InterfaceBasedMBeanInfoAssembler();
    assembler.setManagedInterfaces(OrderManagement.class);
    return assembler;
}
\`\`\`

Gắn assembler:

\`\`\`java
@Bean
public MBeanExporter orderExporter(
        OrderManagement orderManagement,
        MBeanServer server,
        InterfaceBasedMBeanInfoAssembler managementAssembler) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setAssembler(managementAssembler);
    exporter.setBeans(Map.of(
        "com.example.orders:type=OrderAdmin,name=primary",
        orderManagement
    ));
    return exporter;
}
\`\`\`

Ở đây, \`OrderManagement\` phải thật sự là interface được bean/proxy expose. Assembler tạo metadata từ các method quản trị thay vì đưa mọi public method lên JMX. Điều này phù hợp khi cần bảo đảm service bị JDK proxy vẫn có một management contract có thể gọi.

Nếu đang dùng annotation-based \`@ManagedResource\` và \`MetadataMBeanInfoAssembler\`, cần phối hợp naming strategy và attribute source tương ứng. Đổi assembler có thể thay đổi tập attributes/operations. Khi thiết kế, không kết hợp nhiều exporters cho cùng \`ObjectName\` mà không có chủ đích.

## 13. Minh họa lỗi do custom introspection chỉ nhìn bean.getClass()

Một lỗi điển hình trong custom integration:

\`\`\`java
Class<?> type = bean.getClass();

ManagedResource resource =
        type.getAnnotation(ManagedResource.class);

if (resource == null) {
    // Kết luận nhầm là bean không có JMX annotation.
}
\`\`\`

Nếu \`bean\` là JDK proxy, \`type\` sẽ là proxy class, và annotation trên \`OrderProcessor\` có thể không được nhìn thấy.

Một cách tìm type có khả năng phù hợp hơn trong Spring:

\`\`\`java
Class<?> targetType = AopUtils.getTargetClass(bean);

ManagedResource resource =
        org.springframework.core.annotation.AnnotatedElementUtils
                .findMergedAnnotation(
                        targetType, ManagedResource.class);
\`\`\`

Đây là ví dụ về **metadata lookup** có hiểu AOP, không phải toàn bộ quy trình tạo MBean. Đối với exporter tùy biến, bạn còn phải bảo đảm method được metadata chọn thực sự có thể gọi trên object nhận registration.

Nếu target class có \`@ManagedOperation\` trên một method không có trong proxy interfaces, tìm đúng annotation chưa đủ; JMX ModelMBean vẫn cần một target/invocation path phù hợp.

## 14. Kiểm tra metadata JMX sau khi exporter đăng ký

Một cách quan trọng để phân biệt vấn đề proxy và vấn đề đăng ký là đọc \`MBeanInfo\`:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.orders:type=OrderAdmin,name=primary");

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    System.out.println("Class: " + info.getClassName());

    for (var attr : info.getAttributes()) {
        System.out.println(
                "Attribute: " + attr.getName()
                + " / " + attr.getType());
    }

    for (var op : info.getOperations()) {
        System.out.println(
                "Operation: " + op.getName());
    }
}
\`\`\`

\`isRegistered(name)=true\` chỉ xác nhận tên đã có trong registry, không chứng minh các methods mong đợi được công bố. Cần kiểm tra danh sách attributes, operations, signatures và behavior của việc gọi nếu muốn biết proxy/assembler hoạt động đúng.

Chẳng hạn, nếu \`getPendingCount\` không xuất hiện, hãy xác định:

- Bean đã được export như Standard MBean hay ModelMBean?
- Exporter đã nhận raw target, JDK proxy hay class-based proxy?
- Assembler đang đọc proxy interfaces hay target class?
- Có một MBean khác đã đăng ký dưới cùng \`ObjectName\` trước đó không?
- Proxy có expose method cần gọi không?

## 15. Lời gọi qua MBeanServer và direct bean có thể khác

Giả sử direct bean là interface \`OrderOperations\`:

\`\`\`java
OrderOperations direct = context.getBean(OrderOperations.class);
direct.processOrder("123");
\`\`\`

Lời gọi này đi qua Spring AOP proxy và sau đó tới target, áp dụng advice được cấu hình. Một JMX operation như:

\`\`\`java
server.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);
\`\`\`

sẽ đi qua \`MBeanServer\` và adapter/registration, rồi tới object được exporter đăng ký.

Nếu exporter đăng ký chính Spring AOP proxy và invocation đi qua interface được expose, advice có thể tiếp tục hoạt động. Nếu exporter đăng ký target khác hoặc cách adapter tương tác bypass advice, kết quả có thể khác.

Vì vậy không khẳng định rằng “JMX luôn bypass AOP” hoặc “JMX luôn có transaction”. Cần test hành vi theo đối tượng registration thực tế.

## 16. Cách tạo integration test phát hiện vấn đề

Một bài test nên kiểm tra ít nhất ba phần:

1. Spring bean thực sự là JDK proxy.
2. MBeanServer có \`ObjectName\` mong đợi.
3. \`MBeanInfo\` và operation behavior khớp hợp đồng quản trị.

Ví dụ kiểm tra proxy type bằng JUnit Jupiter:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ProxyVisibilityTest {

    @Test
    void beanUsesJdkProxyAndHidesImplementationType() {
        try (var context = new AnnotationConfigApplicationContext(
                ProxyTestConfiguration.class)) {

            Object bean = context.getBean("orderProcessor");

            assertTrue(AopUtils.isJdkDynamicProxy(bean));
            assertTrue(bean instanceof OrderOperations);
            assertFalse(bean instanceof OrderProcessor);
        }
    }
}
\`\`\`

Ở đây \`ProxyTestConfiguration\` là test fixture tự tạo, cấu hình một \`OrderProcessor\` bị proxy theo interface. Assertions này chỉ hợp lệ khi fixture chủ động yêu cầu JDK proxy; chúng không mặc nhiên đúng với mọi Spring Boot application.

Phần kiểm tra JMX cần đọc metadata từ server đã được exporter dùng:

\`\`\`java
@Test
void jmxExportsOnlyExpectedManagementOperations() throws Exception {
    try (var context = new AnnotationConfigApplicationContext(
            ProxyJmxTestConfiguration.class)) {

        MBeanServer server = context.getBean(MBeanServer.class);
        ObjectName name = new ObjectName(
            "com.example.orders:type=OrderAdmin,name=primary");

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(
            java.util.Arrays.stream(info.getOperations())
                .anyMatch(op -> "resetStatistics".equals(op.getName())));

        assertFalse(
            java.util.Arrays.stream(info.getOperations())
                .anyMatch(op -> "processOrder".equals(op.getName())));
    }
}
\`\`\`

Đoạn kiểm thử này giả định \`ProxyJmxTestConfiguration\` đã đăng ký exporter, server và managed object hợp lệ. Nếu muốn cô lập các test chạy song song, dùng \`MBeanServer\` riêng hoặc \`ObjectName\` riêng thay vì chung platform registry.

### Fixture thực hành với một proxy có hai interface

\`\`\`java
@Configuration
public class ProxyJmxTestConfiguration {

    @Bean
    public OrderManagement orderManagement() {
        OrderProcessor target = new OrderProcessor();

        ProxyFactory factory = new ProxyFactory();
        factory.setTarget(target);
        factory.setInterfaces(
                OrderOperations.class,
                OrderManagement.class);
        factory.setProxyTargetClass(false);

        return (OrderManagement) factory.getProxy();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return java.lang.management.ManagementFactory
                .getPlatformMBeanServer();
    }

    @Bean
    public InterfaceBasedMBeanInfoAssembler assembler() {
        InterfaceBasedMBeanInfoAssembler assembler =
                new InterfaceBasedMBeanInfoAssembler();
        assembler.setManagedInterfaces(OrderManagement.class);
        return assembler;
    }

    @Bean
    public MBeanExporter exporter(
            OrderManagement orderManagement,
            MBeanServer mBeanServer,
            InterfaceBasedMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.orders:type=OrderAdmin,name=primary",
            orderManagement));
        return exporter;
    }
}
\`\`\`

Fixture này minh họa cách đảm bảo proxy expose management interface và assembler chỉ công bố những method quản trị. Các import tương ứng đến từ \`javax.management\`, \`org.springframework.aop.framework\`, \`org.springframework.context.annotation\`, \`org.springframework.jmx.export\` và \`org.springframework.jmx.export.assembler\`.

Khi triển khai project thật, bảo đảm \`OrderProcessor\` implement \`OrderManagement\` đúng kiểu trả về/chữ ký, và tránh đồng thời tạo một bean \`OrderProcessor\` riêng được service nghiệp vụ sử dụng — nếu làm vậy có thể tạo hai instances khác nhau, dẫn tới JMX đọc sai trạng thái.

## 17. Chẩn đoán qua log và loại proxy

Một quy trình điều tra thực tế:

| Bước | Câu hỏi | Cách xác minh |
| --- | --- | --- |
| 1 | Bean có thực sự tồn tại? | \`context.containsBean\`, \`getBean\` |
| 2 | Runtime object là AOP proxy? | \`AopUtils.isAopProxy\` |
| 3 | Proxy theo interface hay class? | \`isJdkDynamicProxy\`, \`isCglibProxy\` |
| 4 | Target type là gì? | \`getTargetClass\`, \`ultimateTargetClass\` |
| 5 | Proxy expose interface nào? | \`bean.getClass().getInterfaces()\` / \`instanceof\` |
| 6 | Exporter đang đăng ký object nào? | Cấu hình \`setBeans\`, bean references |
| 7 | ObjectName có trong server? | \`server.isRegistered\` |
| 8 | Attributes/operations có đúng? | \`getMBeanInfo\` |
| 9 | Operation invoke có đi qua advice? | Test instrumentation/logging quanh method |
| 10 | Có exporter khác cùng tên? | Kiểm tra registration ownership và naming |

Phân biệt hai nhóm lỗi:

- **Discovery/metadata error**: exporter không thấy annotation hoặc methods vì introspection nhầm runtime proxy type.
- **Invocation/contract error**: metadata có thể được dựng nhưng object nhận lời gọi không expose method tương ứng hoặc contract JMX không hợp lệ.

Cách khắc phục khác nhau. Thay naming strategy không giải quyết được missing method; thay proxy mode không giải quyết được \`ObjectName\` trùng.

## 18. Khi nào chọn giải pháp nào?

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Business service có nhiều method không nên phơi bày | Management facade riêng | Hạn chế bề mặt JMX |
| Cần giữ JDK proxy và quản trị một tập method nhỏ | Interface quản trị được proxy expose + assembler | Contract rõ ràng |
| Dự án đã dùng annotation JMX trên implementation | Kiểm tra annotation-aware exporter + target introspection | Giữ metadata, tránh lookup proxy class trực tiếp |
| Class-based proxy vốn đã cần cho ứng dụng | Class-based proxy + test metadata | Giảm hạn chế interface visibility |
| Client chỉ cần metric read-only | Facade/attribute read-only | Tránh operations có side effect |
| Cần gọi management method từ module khác trong cùng JVM | Local MBean proxy hoặc direct interface tùy mục đích | Phân biệt quản trị với nghiệp vụ |

Không có một thay đổi cấu hình duy nhất phù hợp mọi hệ thống. Mục tiêu là để **Spring AOP contract, JMX management metadata và runtime invocation path nhất quán**, đồng thời giữ bề mặt quản trị nhỏ nhất cần thiết.

## 19. Lỗi thường gặp

### Lỗi 1 — Cast JDK proxy sang implementation class

\`\`\`java
OrderProcessor processor =
        (OrderProcessor) context.getBean("orderProcessor");
\`\`\`

Nếu bean là JDK dynamic proxy, phép cast có thể thất bại. Inject qua interface được proxy expose hoặc thiết kế class-based proxy có chủ đích.

### Lỗi 2 — Chỉ tìm @ManagedResource trên runtime proxy class

\`\`\`java
bean.getClass().getAnnotation(ManagedResource.class);
\`\`\`

Kết quả có thể \`null\` dù target class có annotation. Dùng introspection hiểu Spring AOP và xác minh exporter thực tế.

### Lỗi 3 — Có @ManagedOperation nhưng proxy không expose method

Annotation trên target không đồng nghĩa JDK proxy có method đó. Cân nhắc đưa method vào management interface mà proxy implement, hoặc dùng facade.

### Lỗi 4 — Bật proxyTargetClass chỉ để sửa JMX mà không xét hệ quả

Class-based proxy có giới hạn đối với final methods và có thể thay đổi type/injection behavior. Không đổi toàn cục mà thiếu integration test.

### Lỗi 5 — Đăng ký raw target để tránh proxy nhưng làm mất AOP advice

Nếu exporter bypass Spring proxy và đăng ký target riêng, JMX operation có thể không đi qua transaction/security advice. Xác minh runtime behavior và tránh làm mất lớp bảo vệ nghiệp vụ.

### Lỗi 6 — Dùng cùng ObjectName cho nhiều exporters

Khi hai exporters cùng đăng ký tên, lỗi \`InstanceAlreadyExistsException\` hoặc policy ignore/replace có thể che target sai. Giữ owner và tên JMX rõ ràng.

## 20. Bài tập thực hành

**Bài 1 — Nhận diện JDK proxy:** tạo \`OrderProcessor implements OrderOperations\`, dùng \`ProxyFactory.setInterfaces(OrderOperations.class)\`, gọi \`AopUtils.isJdkDynamicProxy\` và thử cast sang \`OrderProcessor\`. Giải thích kết quả.

**Bài 2 — Metadata ẩn:** đặt \`@ManagedResource\` trên target class. So sánh \`bean.getClass().getAnnotation(ManagedResource.class)\` với \`AopUtils.getTargetClass(bean)\` và Spring merged annotation lookup.

**Bài 3 — Management interface:** bổ sung \`OrderManagement\` và đảm bảo JDK proxy implement cả \`OrderOperations\`, \`OrderManagement\`. Dùng \`InterfaceBasedMBeanInfoAssembler\` để chỉ export methods quản trị.

**Bài 4 — Facade:** tạo \`OrderMetricsAdmin\` chỉ có \`getPendingCount\`, inject service thông qua \`OrderMetricsView\`. Export facade bằng annotation JMX và xác minh không có \`processOrder\` trong \`MBeanInfo\`.

**Bài 5 — AOP advice:** thêm logging advice quanh method quản trị, gọi trực tiếp interface rồi gọi qua \`MBeanServer.invoke\`. Kiểm tra lần gọi nào chạy advice và giải thích dựa trên object exporter thực sự đăng ký.

**Bài 6 — Đổi proxy mode:** chạy cùng fixture với JDK proxy và class-based proxy, so sánh \`getClass()\`, \`instanceof\`, list interfaces và JMX metadata. Không sử dụng kết luận từ một mode cho mode còn lại.

## Kết luận

**Interface-based proxy có thể che target class** vì JDK dynamic proxy expose các interface thay vì trở thành subclass của implementation. Trong Spring Framework JMX, điều này có thể khiến metadata \`@ManagedResource\` trên target khó được phát hiện bởi custom introspection, hoặc khiến các management methods không thuộc proxy interfaces không thể được gọi qua đường proxy. Cách xử lý là phân biệt rõ Spring AOP proxy, JMX management contract và target object; sử dụng facade, management interface/assembler phù hợp hoặc class-based proxy khi có cơ sở. Luôn kiểm tra runtime proxy type và \`MBeanInfo\` để xác nhận những methods thực sự được công bố qua JMX.
