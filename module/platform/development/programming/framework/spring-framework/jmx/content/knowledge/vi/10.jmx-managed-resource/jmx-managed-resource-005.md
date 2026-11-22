# Phạm vi @ManagedResource trên proxy và target class trong Spring JMX

## 1. Vì sao annotation trên bean có proxy dễ gây nhầm?

Trong Spring Framework, một bean được khai báo bằng \`@Component\` có thể được bọc bởi AOP proxy để thực hiện transaction, security, caching, tracing hoặc một advice khác. Khi đó đối tượng mà \`ApplicationContext.getBean(...)\` trả về không nhất thiết có class runtime giống class triển khai nghiệp vụ.

Ví dụ class \`InventoryAdminService\` được đánh dấu \`@ManagedResource\`, nhưng lúc chạy Spring đưa ra một JDK dynamic proxy có class tương tự \`jdk.proxy2.$Proxy...\` hoặc một proxy tạo bằng CGLIB. Nếu cơ chế export MBean lấy annotation, method và interface từ các loại class khác nhau, có thể xảy ra:

- Exporter không phát hiện bean có \`@ManagedResource\`.
- \`ObjectName\` không được lấy như kỳ vọng.
- MBean được đăng ký nhưng thiếu attribute hoặc operation.
- Method không được proxy công bố nên không thể được gọi qua proxy.
- Startup báo lỗi về compliance, introspection hoặc reflection.

Cần phân biệt **class được annotate**, **class runtime của bean**, **target class được AOP đại diện**, và **interface mà proxy thực hiện**. \`@ManagedResource\` không làm cho mọi proxy tự động nhìn thấy mọi method của target.

## 2. Bốn lớp cần quan sát

\`\`\`text
Spring ApplicationContext
        |
        v
Bean reference returned to MBeanExporter
        |
        +-- Runtime bean class: JDK Proxy / CGLIB Proxy / plain class
        |
        +-- Target class: implementation có @ManagedResource
        |
        +-- Introduced / implemented interfaces
        |
        +-- Eligible methods visible to the proxy
        |
        v
JMX metadata source + MBeanInfo assembler
        |
        v
ObjectName + attributes + operations
        |
        v
MBeanServer registration
\`\`\`

**Target class** là loại class ứng dụng được proxy bọc. Với JDK dynamic proxy, client thường chỉ gọi được method trên các interface mà proxy triển khai. Với CGLIB class-based proxy, proxy là subclass của target class nhưng có giới hạn với method \`final\`, \`private\` và những method không thể override.

Spring JMX dùng cơ chế metadata của exporter, không chỉ dựa vào Java reflection thô trên \`bean.getClass()\`. Vì vậy không nên khẳng định mọi annotation trên target luôn bị mất khi có JDK proxy. Kết quả cụ thể phụ thuộc metadata source, assembler, cấu hình Spring, kiểu proxy và những method khả dụng qua bean thực tế.

## 3. Ví dụ một class vừa được quản lý JMX vừa được áp dụng AOP

\`\`\`java
package com.example.inventory;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "com.example.inventory:type=InventoryAdmin,name=Primary",
    description = "Inventory management endpoint"
)
public class InventoryAdminService implements InventoryAdminOperations {
    private volatile boolean paused;

    @Override
    @ManagedAttribute(description = "Background import paused")
    public boolean isPaused() {
        return paused;
    }

    @Override
    @Transactional
    @ManagedOperation(description = "Pause background import")
    public void pauseImport() {
        paused = true;
    }
}
\`\`\`

Interface:

\`\`\`java
package com.example.inventory;

public interface InventoryAdminOperations {
    boolean isPaused();
    void pauseImport();
}
\`\`\`

Nếu Spring tạo **JDK proxy** vì transaction advice, proxy có thể chỉ cung cấp hai method của interface. Những method public bổ sung ở implementation nhưng không nằm trên interface sẽ không nhất thiết gọi được qua proxy đó.

Nếu dùng **class-based proxy** (thường gọi là CGLIB proxy), các method public/protected có thể được proxy đại diện khi đáp ứng điều kiện override. Không đồng nhất class-based proxy với việc mọi method đều được intercept: method \`final\` hoặc \`private\` không được override, và self-invocation trong cùng target thường không chạy qua advice của proxy.

Dù annotation JMX có thể được đọc từ target, việc gọi operation sẽ đi qua bean instance mà exporter đăng ký. Cần xác nhận **metadata và khả năng gọi** đều khớp.

## 4. @ManagedResource, @ManagedAttribute và @ManagedOperation có vai trò khác nhau

Spring JMX annotation thường được dùng theo hai lớp:

- \`@ManagedResource\` đánh dấu một bean/class là tài nguyên quản trị, có thể mang \`objectName\`, \`description\`, \`currencyTimeLimit\` và các metadata khác.
- \`@ManagedAttribute\` khai báo getter/setter được trình bày dưới dạng JMX attribute.
- \`@ManagedOperation\` khai báo method được xuất dưới dạng JMX operation.
- \`@ManagedOperationParameter\` cung cấp metadata tham số operation khi cần.

Chỉ có \`@ManagedResource\` trên class không có nghĩa mọi method public đều tự trở thành JMX operation. Khi dùng metadata assembler, method cần được chọn theo annotation và quy tắc tương ứng.

Một bean được proxy vẫn phải được exporter nhận diện là tài nguyên phù hợp; annotation trên target class là nguồn metadata nghiệp vụ, nhưng **khả năng hiển thị annotation khi inspect proxy** là câu hỏi cấu hình/framework. Hãy dùng test thực tế với đúng phiên bản Spring của dự án thay vì dựa hoàn toàn vào \`proxy.getClass().isAnnotationPresent(...)\`.

## 5. JDK dynamic proxy: method nằm trên interface mới khả dụng

Một bean có interface:

\`\`\`java
public interface InventoryAdminOperations {
    boolean isPaused();
    void pauseImport();
}
\`\`\`

Và target có method public ngoài interface:

\`\`\`java
@ManagedOperation
public void forceRebuildInternalIndex() {
    // ...
}
\`\`\`

Nếu exporter đăng ký chính JDK proxy, method \`forceRebuildInternalIndex()\` không thuộc các interface mà proxy thực hiện. Việc metadata assembler phát hiện annotation ở target không tự đảm bảo Java reflection có thể gọi operation qua proxy.

Hướng thiết kế:

1. Chỉ export các method quản trị cần thiết và khai báo chúng trên một interface mà JDK proxy thực hiện nếu muốn dùng proxy-based bean trực tiếp.
2. Hoặc tạo một **adapter quản trị riêng** không bị proxy nghiệp vụ, inject một application service interface và dùng \`@ManagedResource\` trên adapter.
3. Nếu cần class-based proxy, hiểu rõ ảnh hưởng của \`proxyTargetClass=true\` tới toàn ứng dụng và chỉ chọn khi thực sự phù hợp.

Không đổi toàn bộ transaction AOP thành class-based proxy chỉ để chữa một MBean thiếu method nếu có thể tách JMX adapter gọn và ổn định hơn.

## 6. CGLIB proxy và target annotation

Với class-based proxy, runtime class thường là một subclass được sinh ra. Annotation của target có thể được Spring metadata inspection tìm thấy qua user class/target class; tuy nhiên cần xem từng annotation và resolver cụ thể.

Tránh cách kiểm tra duy nhất:

\`\`\`java
boolean present =
    bean.getClass().isAnnotationPresent(ManagedResource.class);
\`\`\`

Kết quả \`false\` trên proxy runtime class **không chứng minh** Spring JMX không thể đọc annotation. Để chẩn đoán, so sánh thêm:

\`\`\`java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.jmx.export.annotation.ManagedResource;

Object bean = context.getBean("inventoryAdminService");

Class<?> runtimeClass = bean.getClass();
Class<?> targetClass = AopUtils.getTargetClass(bean);

boolean runtimeAnnotated =
    AnnotatedElementUtils.hasAnnotation(
        runtimeClass, ManagedResource.class
    );

boolean targetAnnotated =
    AnnotatedElementUtils.hasAnnotation(
        targetClass, ManagedResource.class
    );

System.out.println(runtimeClass.getName());
System.out.println(targetClass.getName());
System.out.println(runtimeAnnotated + " / " + targetAnnotated);
\`\`\`

\`AopUtils.getTargetClass\` giúp xác định target class khi proxy được Spring AOP nhận biết. Khi ứng dụng có các proxy lồng nhau hoặc cơ chế proxy do thư viện ngoài tạo, có thể cần theo dõi nhiều tầng proxy và kiểm tra bean thực tế mà exporter nhận.

## 7. Spring exporter đọc annotation bằng cơ chế nào?

Khi dùng Spring JMX annotation, cấu hình điển hình gồm \`AnnotationJmxAttributeSource\`, \`MetadataMBeanInfoAssembler\` và \`MetadataNamingStrategy\` (hoặc một cấu hình ngắn gọn được framework hỗ trợ):

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {
    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mbeanExporter(
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
\`\`\`

Ví dụ dùng một exporter để minh họa vai trò của ba thành phần. Nếu Spring Boot đã tự cấu hình MBeanExporter, không khai báo thêm exporter trùng trách nhiệm mà chưa kiểm tra auto-configuration. Trong Spring Framework thuần, \`@EnableMBeanExport\` cũng là lựa chọn cấu hình ngắn khi phù hợp.

Cần phân biệt **đọc metadata** với **gọi method**: assembler có thể tìm metadata trên target class, nhưng object đăng ký vẫn phải hỗ trợ lời gọi theo bề mặt được export.

## 8. Phương án ổn định: tách adapter JMX khỏi service nghiệp vụ

Để tránh proxy của transaction/security làm phức tạp cách export MBean, một adapter quản trị riêng thường là ranh giới rõ ràng:

\`\`\`java
package com.example.inventory.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.inventory:type=Import,name=Primary"
)
public final class InventoryJmxAdapter {
    private final InventoryAdminOperations operations;

    public InventoryJmxAdapter(InventoryAdminOperations operations) {
        this.operations = operations;
    }

    @ManagedAttribute(description = "Import processing paused")
    public boolean isPaused() {
        return operations.isPaused();
    }

    @ManagedOperation(description = "Pause import")
    public void pause() {
        operations.pauseImport();
    }
}
\`\`\`

Bean \`InventoryAdminOperations\` có thể là một JDK proxy được Spring tạo vì transaction/security. Adapter chỉ gọi các method đã khai báo trên interface, nên vẫn đi qua advice của proxy một cách bình thường.

Những lợi ích:

- Annotation JMX tập trung ở lớp hạ tầng, không rơi vào domain model.
- Exporter introspect adapter có bề mặt nhỏ, ít thay đổi.
- Business service có thể thay chiến lược AOP mà không đổi contract JMX.
- Dễ kiểm thử adapter bằng fake interface và kiểm thử đăng ký JMX riêng.
- Các operation nguy hiểm có thể thêm chính sách kiểm soát tại cổng quản trị thay vì xuất mọi public method của service.

Một adapter JMX cũng có thể bị proxy nếu chính nó được gắn advice hoặc bị pointcut rộng áp dụng. Khi cần, kiểm tra bean adapter thực tế trong Spring context; không mặc định adapter luôn plain class.

## 9. Không hiểu nhầm proxy với mất transaction hoặc security

Nếu service nghiệp vụ có \`@Transactional\` hoặc \`@PreAuthorize\`, adapter nên inject **Spring-managed proxy**, không tự tạo \`new InventoryAdminService()\` và gọi trực tiếp target. Tự khởi tạo implementation có thể bỏ qua transaction/security advice, dependency injection và lifecycle.

\`\`\`java
@Component
public class InventoryJmxAdapter {
    private final InventoryAdminOperations operations;

    public InventoryJmxAdapter(InventoryAdminOperations operations) {
        this.operations = operations; // Bean/proxy từ Spring container
    }
}
\`\`\`

Lệnh JMX có thể được gọi từ client bên ngoài; xác thực ở JMX connector và kiểm tra ủy quyền của ứng dụng phải được thiết kế rõ. Spring Security method advice đôi khi dựa vào security context của HTTP request, vốn không tự hiện diện trên JMX thread. Cần chính sách quản trị phù hợp thay vì giả định mọi \`@PreAuthorize\` sẽ có cùng thông tin người dùng như web request.

## 10. Cách chẩn đoán bean proxy và target trong ứng dụng

Một probe nhỏ:

\`\`\`java
import org.springframework.aop.support.AopUtils;
import org.springframework.context.ApplicationContext;

public final class ProxyProbe {
    public static void describe(
            ApplicationContext context, String beanName) {
        Object bean = context.getBean(beanName);

        System.out.println("Bean: " + beanName);
        System.out.println("Runtime: " + bean.getClass().getName());
        System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
        System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
        System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
        System.out.println("Target: " +
            AopUtils.getTargetClass(bean).getName());
    }
}
\`\`\`

Sau đó kiểm tra trên đúng \`MBeanServer\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.inventory:type=Import,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    var info = server.getMBeanInfo(name);

    for (var attribute : info.getAttributes()) {
        System.out.println(attribute.getName());
    }

    for (var operation : info.getOperations()) {
        System.out.println(operation.getName());
    }
}
\`\`\`

Nếu exporter đăng ký trên custom server, dùng instance ấy thay cho platform server. \`isRegistered=true\` chứng minh tên MBean tồn tại nhưng không chứng minh mọi method đều gọi được qua proxy; tiếp tục dùng \`getAttribute\` và \`invoke\` trong test tích hợp.

## 11. Ma trận triệu chứng và nguyên nhân

| Triệu chứng | Khả năng cao | Phép kiểm tra |
| --- | --- | --- |
| Annotation hiện trên target nhưng không hiện trên proxy class | Metadata nằm ở implementation | So sánh runtime class và \`AopUtils.getTargetClass\` |
| MBean không được export | Autodetect/annotation metadata/exporter cấu hình sai | Kiểm tra exporter, \`@ManagedResource\`, Spring context |
| MBean có nhưng thiếu operation | Method không nằm trên interface proxy hoặc assembler không thấy annotation | \`getMBeanInfo\`, kiểm tra JDK proxy interfaces |
| \`NotCompliantMBeanException\` | Exporter đăng ký POJO/proxy theo Standard MBean rules | Xem đường registration và assembler |
| \`ReflectionException\` khi gọi operation | Proxy không expose method hoặc signature không khớp | \`invoke\` với signature cụ thể |
| Bật AOP thì JMX hỏng | Loại runtime bean thay đổi khi advice xuất hiện | So sánh class/proxy trước và sau |
| JMX hoạt động nhưng transaction không chạy | Tự gọi target hoặc self-invocation bỏ qua proxy | Kiểm tra nơi inject bean và call path |

Không áp dụng một “thuốc chữa” chung cho mọi triệu chứng. Ví dụ đổi \`proxyTargetClass\` có thể làm hiện method, nhưng không sửa được \`ObjectName\` trùng hoặc exporter bị tắt.

## 12. Kiểm thử annotation trên proxy thực tế

Một integration test có thể lấy bean từ Spring context, xác định proxy và gọi JMX:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.aop.support.AopUtils;

@SpringBootTest(properties = "spring.jmx.enabled=true")
class InventoryJmxIntegrationTest {
    @Autowired
    InventoryAdminOperations operations;

    @Autowired
    MBeanServer mbeanServer;

    @Test
    void exposesManagementOperationThroughMBeanServer()
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.inventory:type=Import,name=Primary"
        );

        assertTrue(mbeanServer.isRegistered(name));
        assertNotNull(operations);

        Object paused = mbeanServer.getAttribute(name, "Paused");
        assertTrue(paused instanceof Boolean);

        mbeanServer.invoke(
            name, "pause", new Object[0], new String[0]
        );
        assertTrue(operations.isPaused());
    }
}
\`\`\`

Đây là khuôn mẫu tích hợp cho ứng dụng có Spring Boot Test, AOP, JMX và bean \`MBeanServer\` phù hợp; cần điều chỉnh cấu hình và package theo dự án. \`AopUtils.isAopProxy(operations)\` có thể được assert khi test được thiết kế cố ý bật advice/proxy; không nên assert proxy bắt buộc trong mọi cấu hình.

Khi dùng platform \`MBeanServer\` trong test chạy song song, các context có cùng \`ObjectName\` có thể đụng nhau. Sử dụng JMX domain hoặc instance key riêng cho test, đồng thời đóng context sau test.

## 13. Unit test adapter không cần JMX server

Để kiểm tra logic mapping độc lập proxy:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class InventoryJmxAdapterTest {
    @Test
    void delegatesToManagementPort() {
        class Fake implements InventoryAdminOperations {
            boolean paused;

            public boolean isPaused() {
                return paused;
            }

            public void pauseImport() {
                paused = true;
            }
        }

        Fake fake = new Fake();
        InventoryJmxAdapter adapter = new InventoryJmxAdapter(fake);

        assertFalse(adapter.isPaused());
        adapter.pause();
        assertTrue(fake.paused);
        assertTrue(adapter.isPaused());
    }
}
\`\`\`

Unit test này xác nhận adapter ủy quyền đúng, không chứng minh exporter nhận annotation hoặc proxy tương thích. Hai câu hỏi cần hai tầng test riêng.

## 14. Những lỗi thiết kế thường gặp

**Đánh dấu annotation JMX ngay trên entity/domain service.** Domain bị ràng buộc vào quản trị và proxy; hãy đưa JMX ra adapter nếu kiến trúc cần tách biệt.

**Kiểm tra annotation bằng \`bean.getClass()\` rồi kết luận không có.** Proxy class có thể khác target class; dùng metadata của Spring và kiểm chứng exporter thực tế.

**Đánh dấu method ở implementation nhưng chỉ expose interface khác.** JDK proxy chỉ trình bày các interface nó thực hiện. Thiết kế interface tương ứng hoặc adapter riêng.

**Bỏ AOP bằng cách gọi \`new TargetService()\`.** Việc này làm mất advice và có thể phá transaction/security. Inject Spring bean qua interface.

**Bật class-based proxy cho toàn dự án để sửa JMX.** Đổi chiến lược AOP có thể tác động nhiều bean; ưu tiên cô lập bề mặt JMX.

**MBean hiện trong UI nên coi như mọi operation hoạt động.** Metadata và invocation cần được kiểm chứng riêng.

**Cho rằng annotation trên interface và class luôn được xử lý giống nhau.** Java annotation inheritance, method resolution và Spring metadata merging có quy tắc riêng. Chọn vị trí annotation nhất quán và xác minh với phiên bản Spring đang triển khai.

## 15. Hướng chọn vị trí annotation

| Vị trí | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| Domain class | Trộn quản trị vào miền | Tránh trong kiến trúc phân tầng |
| Business service implementation | Thuận tiện khi ít lớp, nhưng chịu ảnh hưởng AOP proxy | Chỉ khi scope nhỏ và có integration test |
| Business interface | Có thể ảnh hưởng mọi caller và không phải luôn được metadata source diễn giải như mong đợi | Không dùng làm nơi mặc định chứa JMX metadata |
| Management adapter class | Rõ ranh giới, dễ kiểm soát contract JMX | Lựa chọn ưu tiên |
| Standard MBean interface (\`*MBean\`) | Contract JMX Java chuẩn, không cần Spring annotation | Phù hợp khi dùng Standard MBean |

Điểm then chốt không phải proxy loại nào “tốt hơn”, mà là **MBeanExporter biết đọc annotation ở đâu và object mà nó đăng ký có thực sự hỗ trợ operation được mô tả hay không**.

## 16. Ghi nhớ

\`@ManagedResource\` gắn metadata quản trị với một bean/class, còn Spring AOP có thể làm object runtime trở thành JDK dynamic proxy hoặc CGLIB proxy. Khi có proxy, phải xét riêng **target annotation**, **proxy-exposed methods**, **exporter metadata resolution** và **MBeanServer invocation**. Một JMX adapter riêng, inject application interface qua Spring, giúp tránh phần lớn phụ thuộc vào chi tiết proxy và giữ nghiệp vụ độc lập với giao thức quản trị.
