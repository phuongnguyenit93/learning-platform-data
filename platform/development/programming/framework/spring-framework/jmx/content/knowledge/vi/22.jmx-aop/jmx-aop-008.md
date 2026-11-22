# Tránh export proxy thay vì target khi hợp đồng JMX cần ổn định

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích vì sao Spring AOP có thể khiến một Spring bean tại runtime là proxy thay vì instance target trực tiếp.
- Phân biệt **proxy object**, **target object**, **target class**, **JMX MBean registration**, **management interface** và **ObjectName**.
- Nhận biết rủi ro khi cấu hình export dựa trên runtime proxy class hoặc giao diện proxy thay vì một contract quản trị được thiết kế ổn định.
- Chọn giữa export target, export proxy có kiểm soát, Standard MBean, annotation-based MBean và một management facade riêng.
- Hiểu vì sao việc “bỏ qua proxy” có thể làm mất AOP advice như transaction, security hoặc audit.
- Sử dụng Spring AOP utilities, JMX metadata và integration test để xác minh contract được công bố qua MBeanServer.
- Thiết kế management boundary không bị thay đổi ngoài ý muốn khi refactor code hoặc đổi chiến lược JDK dynamic proxy/CGLIB.

## 1. Vì sao vấn đề xuất hiện?

Trong Spring Framework, bean có thể được tạo dưới dạng proxy khi các tính năng như transaction management, security, caching, asynchronous execution hoặc custom aspects được áp dụng.

Mô hình:

\`\`\`text
Spring ApplicationContext
      |
      | getBean("paymentService")
      v
Spring AOP proxy
      |
      | advice: transaction / security / logging
      v
Target object: PaymentServiceImpl
\`\`\`

Ví dụ:

\`\`\`java
@Service
@Transactional
public class PaymentServiceImpl implements PaymentService {
    // ...
}
\`\`\`

Nếu Spring tạo proxy, câu lệnh:

\`\`\`java
Object bean = context.getBean("paymentServiceImpl");
System.out.println(bean.getClass());
\`\`\`

có thể in ra một class sinh động, chẳng hạn JDK dynamic proxy hoặc subclass do Spring CGLIB tạo. Tên class proxy thường là chi tiết runtime, không phải API quản trị ổn định.

Trong khi đó, JMX client mong đợi những thứ có tên và cấu trúc rõ ràng:

\`\`\`text
ObjectName  = learning.jmx:type=PaymentService,name=Primary
Attribute   = PendingPayments
Operation   = refreshStatus
\`\`\`

Một lần đổi proxy strategy không nên vô tình làm JMX client mất các attributes hoặc operations trên.

**Thông điệp chính:** Hãy export một **management contract ổn định**, không để runtime proxy class trở thành nguồn định danh hoặc metadata ngoài ý muốn.

## 2. Proxy, target và MBean khác nhau như thế nào?

| Khái niệm | Ý nghĩa | Có nên dùng làm contract JMX? |
|---|---|---|
| Target object | Object chứa logic thật | Có thể là nguồn dữ liệu; không nhất thiết phải đăng ký trực tiếp |
| Target class | Class nghiệp vụ ban đầu | Có thể chứa annotations JMX, nhưng vẫn chịu thay đổi do refactor |
| Spring AOP proxy | Object thay mặt target và thực thi advice | Không nên lấy tên class proxy làm tên MBean |
| Management facade | Adapter nhỏ thiết kế riêng cho JMX | Thường phù hợp để giữ contract rõ, ổn định |
| ObjectName | Định danh registration trong MBeanServer | Là một phần contract quản trị |
| MBeanInfo | Danh sách attributes/operations/types được công bố | Là contract thực tế mà JMX client nhìn thấy |

Proxy không đồng nghĩa với MBean. Một proxy có thể được Spring exporter đăng ký hoặc được Spring phân tích để nhận diện target metadata, nhưng việc nó có thể xuất được không tự bảo đảm contract đã ổn định.

### JDK dynamic proxy

JDK proxy triển khai những Java interfaces đã được cấu hình. Nó thường không là subclass của concrete target class.

Nếu method quản trị chỉ tồn tại trên implementation mà không có trong các proxy interfaces, cần xem exporter có thể tìm và gọi method đó qua proxy hay không.

### Class-based proxy

Class-based proxy thường là subclass của concrete target class, nên có thể bảo toàn nhiều public methods của target trong những điều kiện phù hợp.

Tuy vậy, final class, final method và các giới hạn proxy vẫn tồn tại. Dùng CGLIB không tự giải quyết mọi vấn đề JMX metadata và invocation.

## 3. “Export proxy thay vì target” có nghĩa gì?

Trong một ứng dụng, \`MBeanExporter\` có thể được cấp Spring bean mà \`getBean(...)\` trả về là proxy.

Ví dụ:

\`\`\`java
Object bean = context.getBean("orderService");
exporter.setBeans(Map.of(
    "learning.jmx:type=OrderService,name=Primary",
    bean
));
\`\`\`

Nếu \`bean\` là proxy, exporter phải làm việc với proxy object và có thể phải xác định target class, metadata và methods có thể gọi được.

Rủi ro xuất hiện khi developer:

- Dùng \`bean.getClass().getSimpleName()\` làm cơ sở đặt ObjectName.
- Dựa vào các interface tình cờ có trên proxy thay vì interface quản trị chủ đích.
- Refactor interface nghiệp vụ rồi vô tình thay đổi JMX operation surface.
- Chuyển từ JDK proxy sang class-based proxy hoặc ngược lại mà không kiểm thử metadata.
- Tưởng \`@ManagedResource\` trên target chắc chắn được nhận diện trong mọi cơ chế exporter.
- Đăng ký proxy trực tiếp với JMX như Standard MBean mà không xem tuân thủ convention.
- Bỏ proxy để dễ export nhưng làm mất transaction/security advice ở đường JMX invocation.

Điểm cuối rất quan trọng: **không phải lúc nào export target trực tiếp cũng an toàn hơn export proxy**. Khi advice là một phần hành vi quan trọng, đi thẳng vào target có thể bỏ qua chúng.

## 4. Phân biệt ba lớp cần kiểm chứng

Một bài toán proxy + JMX có ba câu hỏi riêng:

1. **Discovery:** exporter có tìm thấy bean là managed resource không?
2. **Metadata:** MBean có công bố đúng ObjectName, attributes, operations và signatures không?
3. **Invocation:** khi JMX client gọi operation, lời gọi có đến đúng implementation với những advice cần thiết không?

Ví dụ, MBean có thể được đăng ký thành công nhưng thiếu operation; hoặc metadata đúng nhưng invocation không đi qua security advisor.

Không nên chỉ nhìn việc MBean xuất hiện trong JConsole rồi kết luận hợp đồng đã ổn định.

## 5. Ví dụ: service nghiệp vụ được AOP proxy

Service interface:

\`\`\`java
package example.jmx;

public interface InventoryService {
    int availableItems();
    void refreshInventory();
}
\`\`\`

Implementation:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryServiceImpl implements InventoryService {

    private final AtomicInteger available = new AtomicInteger(100);

    @Override
    public int availableItems() {
        return available.get();
    }

    @Override
    @Transactional
    public void refreshInventory() {
        // Ví dụ: đồng bộ dữ liệu từ một nguồn được quản lý.
        // Ở production, thao tác này cần permission và audit phù hợp.
        available.set(120);
    }
}
\`\`\`

Khi transaction management được bật và có transaction manager thích hợp, Spring có thể tạo proxy để áp dụng transaction advice.

Nếu bạn annotate luôn \`InventoryServiceImpl\` với \`@ManagedResource\` và những operations JMX, thay đổi runtime proxy strategy có thể khiến cần kiểm tra lại cách metadata được phát hiện và method được gọi.

Một thiết kế khác là tách quản trị thành facade.

## 6. Giải pháp khuyến nghị: management facade ổn định

Management facade là một Spring bean chuyên trình bày contract quản trị, không phải service nghiệp vụ.

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=Inventory,name=Primary",
    description = "Stable inventory management interface"
)
public class InventoryManagement {

    private final InventoryService inventoryService;

    public InventoryManagement(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ManagedAttribute(description = "Available item count")
    public int getAvailableItems() {
        return inventoryService.availableItems();
    }

    @ManagedOperation(description = "Refresh inventory data")
    public void refresh() {
        inventoryService.refreshInventory();
    }
}
\`\`\`

Ưu điểm:

- **ObjectName ổn định:** không phụ thuộc tên runtime proxy class.
- **Attribute name ổn định:** \`AvailableItems\` không thay đổi chỉ vì service đổi tên method nội bộ.
- **Operation name ổn định:** client tiếp tục gọi \`refresh\`.
- **Bề mặt nhỏ:** chỉ công bố thứ thật sự cần quản trị.
- **Advice được giữ lại:** facade gọi qua \`InventoryService\` bean, có thể là proxy áp dụng transaction/security.
- **Dễ kiểm thử:** facade có contract JMX riêng và có integration test qua MBeanServer.

Spring configuration:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    InventoryManagement inventoryManagement(
            InventoryService inventoryService) {
        return new InventoryManagement(inventoryService);
    }
}
\`\`\`

Nếu service implementation đã được đăng ký qua component scanning, không cần tạo một service instance khác chỉ để facade dùng. Đảm bảo facade nhận **Spring-managed service proxy**, không gọi trực tiếp \`new InventoryServiceImpl()\` nếu transaction advice là yêu cầu.

## 7. Vì sao không chỉ unregister proxy rồi register target?

Một cách xử lý vội có thể là lấy object target đằng sau proxy rồi đăng ký nó trực tiếp:

\`\`\`java
// Ý tưởng có rủi ro: bỏ qua proxy để export trực tiếp.
Object target = ...;
server.registerMBean(target, name);
\`\`\`

Cách này có những vấn đề:

- Target không nhất thiết là một Standard MBean hợp lệ.
- Phải tự quản lý ObjectName, registration và lifecycle.
- Lời gọi JMX có thể bỏ qua advice trên proxy.
- Một số target được quản lý bởi proxy/factory/scope phức tạp, lấy target thô không luôn an toàn.
- Có thể bypass security, transaction, auditing hoặc các interceptor khác.
- Nếu target thay đổi giữa các lần gọi, đăng ký instance cũ trở nên không phù hợp.

**Không tự động lấy target object rồi register như một giải pháp chung.** Ưu tiên facade hoặc cấu hình exporter có contract rõ ràng và test invocation thực tế.

## 8. Các cách export cần phân biệt

### Cách A — Spring annotation-driven exporter

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Inventory,name=Primary"
)
public class InventoryManagement {
    @ManagedAttribute
    public int getAvailableItems() { ... }

    @ManagedOperation
    public void refresh() { ... }
}
\`\`\`

Kết hợp với \`@EnableMBeanExport\` hoặc exporter có annotation metadata assembler tương ứng. Đây là cách rõ ràng cho management facade.

### Cách B — Standard MBean interface

\`\`\`java
public interface InventoryManagementMBean {
    int getAvailableItems();
    void refresh();
}

public class InventoryManagement implements InventoryManagementMBean {
    // ...
}
\`\`\`

Lớp và interface tuân theo Standard MBean convention, hoặc bạn có thể dùng \`StandardMBean\` wrapper để chỉ định management interface rõ ràng nếu không muốn phụ thuộc tên lớp triển khai.

Khi dùng một interface quản trị riêng, contract được xác định tường minh hơn so với việc lấy mọi methods của runtime proxy.

### Cách C — Explicit exporter mapping

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setBeans(Map.of(
    "learning.jmx:type=Inventory,name=Primary",
    inventoryManagement
));
\`\`\`

Map xác định ObjectName tường minh. Nhưng nếu object được map là một service proxy mà metadata/interface không hợp lệ, explicit mapping không tự khắc phục vấn đề JMX compliance.

### Cách D — Export proxy có chủ đích

Một proxy có thể được export nếu exporter và metadata mapping có thể xử lý đúng nó. Trong trường hợp này, cần bảo đảm:

- ObjectName không suy ra từ proxy class name không ổn định.
- Management interface/metadata được định nghĩa có chủ đích.
- JMX operation invocation đi qua advice cần thiết.
- MBeanInfo và integration tests xác nhận contract.
- Thay đổi proxy strategy có kiểm thử hồi quy.

Mục tiêu không phải cấm hoàn toàn việc proxy xuất hiện ở ranh giới JMX, mà là **không để proxy implementation vô tình định nghĩa public management contract**.

## 9. Cách Spring AOP chọn proxy

Spring AOP thường dùng:

- **JDK dynamic proxy** khi tạo proxy cho interfaces.
- **Class-based proxy** khi cấu hình target-class proxy hoặc theo cơ chế/framework tương ứng.

Ví dụ bật class-based proxy:

\`\`\`java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
\`\`\`

Với transaction proxy:

\`\`\`java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class TransactionConfiguration {
}
\`\`\`

Nhưng \`proxyTargetClass=true\` chỉ điều khiển **cách tạo proxy khi có advice**, không bắt buộc mọi Spring bean đều được proxy.

Ngoài ra, class-based proxy có giới hạn: final class không thể được subclass; final method không thể bị override để áp dụng advice theo kiểu subclass.

Nếu thay đổi proxy strategy trên toàn ứng dụng, có thể ảnh hưởng đến cách các bean được inject/cast, method intercept và cách exporter thấy runtime type. Không nên đổi toàn bộ AOP configuration chỉ để làm một custom MBean xuất hiện nếu có thể dùng facade.

## 10. Dùng AopUtils để chẩn đoán runtime bean

Spring AOP có utility:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("inventoryServiceImpl");

System.out.println(
    "Runtime class: " + bean.getClass().getName()
);
System.out.println(
    "Target class: " + AopUtils.getTargetClass(bean)
);
System.out.println(
    "Is AOP proxy: " + AopUtils.isAopProxy(bean)
);
System.out.println(
    "Is JDK proxy: " + AopUtils.isJdkDynamicProxy(bean)
);
System.out.println(
    "Is class proxy: " + AopUtils.isCglibProxy(bean)
);
\`\`\`

Kết quả có thể minh họa:

\`\`\`text
Runtime class: jdk.proxy...$Proxy...
Target class: class example.jmx.InventoryServiceImpl
Is AOP proxy: true
Is JDK proxy: true
Is class proxy: false
\`\`\`

Tên runtime proxy có thể thay đổi theo JDK, Spring version, advisor và việc tạo proxy. Không dùng những chuỗi này như một ObjectName cố định.

\`AopUtils.getTargetClass\` giúp xác định target type; nó không tự thay đổi exporter configuration hay “gỡ proxy”.

## 11. Tách JMX contract khỏi Java class name

Một lỗi naming phổ biến:

\`\`\`java
String objectName =
        "learning.jmx:type=" + bean.getClass().getSimpleName();
\`\`\`

Khi bean là proxy, \`getClass().getSimpleName()\` có thể là một tên sinh động hoặc thay đổi sau refactor.

Nên dùng ObjectName rõ ràng:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=Inventory,name=Primary"
);
\`\`\`

hoặc:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Inventory,name=Primary"
)
\`\`\`

Một naming strategy được thiết kế theo logical resource identity cũng phù hợp nếu phải đăng ký nhiều instances.

**ObjectName là contract quản trị**: script, dashboards và JMX clients có thể tham chiếu chính xác tên đó. Đổi JDK proxy sang class-based proxy không nên làm đổi ObjectName.

## 12. Contract của attributes và operations cũng phải ổn định

Một class có getter:

\`\`\`java
@ManagedAttribute
public int getAvailableItems() {
    return service.availableItems();
}
\`\`\`

JMX attribute thường có tên \`AvailableItems\`.

Nếu refactor getter thành:

\`\`\`java
@ManagedAttribute
public int getAvailableInventory() {
    return service.availableItems();
}
\`\`\`

attribute có thể đổi thành \`AvailableInventory\`, khiến client dùng tên cũ thất bại.

Tương tự:

\`\`\`java
@ManagedOperation
public void refresh() {
    service.refreshInventory();
}
\`\`\`

Nếu đổi thành \`rebuild()\`, tên operation có thể thay đổi. JMX clients gọi \`invoke(name, "refresh", ...)\` có thể không còn hoạt động.

Management facade giúp giữ tên quản trị ổn định ngay cả khi service API thay đổi.

## 13. Kiểm chứng từ MBeanServer thay vì chỉ đọc source

Một exporter có thể đăng ký MBean thành công nhưng contract thực tế không như kỳ vọng. Hãy kiểm tra \`MBeanServer\`.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "learning.jmx:type=Inventory,name=Primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(
        "Attribute: " + attribute.getName()
        + ", type=" + attribute.getType()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "Operation: " + operation.getName()
    );
}
\`\`\`

Kỳ vọng khi management facade đã được export phù hợp:

\`\`\`text
Attribute: AvailableItems, type=int
Operation: refresh
\`\`\`

Phải dùng đúng MBeanServer mà exporter đang đăng ký. Nếu ứng dụng dùng custom server, platform server không nhất thiết có MBean này. Client từ JVM khác phải dùng JMX connector và \`MBeanServerConnection\`.

## 14. Kiểm thử invocation: bảo toàn advice cần thiết

Metadata đúng chưa đủ nếu operation quan trọng phải đi qua transaction/security/audit advice.

Giả sử facade gọi:

\`\`\`java
@ManagedOperation
public void refresh() {
    inventoryService.refreshInventory();
}
\`\`\`

Nếu \`inventoryService\` là Spring proxy, lời gọi từ facade sẽ đi qua proxy và có thể kích hoạt advice. Ngược lại, nếu facade giữ \`new InventoryServiceImpl()\` tự tạo, Spring AOP advice trên bean có thể không chạy.

Một integration test có thể:

1. Khởi tạo Spring ApplicationContext có AOP và JMX exporter.
2. Lấy đúng MBeanServer.
3. Xác nhận ObjectName đã đăng ký.
4. Dùng \`MBeanServer.invoke(...)\` gọi operation.
5. Quan sát tác dụng phụ và assertion về advice cần thiết trong test fixture.
6. Kiểm tra access-denied path nếu có security policy.
7. Đóng context, xác minh unexport.

Đừng thử operation gây thay đổi dữ liệu thật trên production chỉ để chứng minh nó được export.

## 15. Mẫu integration test giữ contract ổn định

Ví dụ JUnit 5:

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import java.util.Arrays;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class InventoryJmxContractTest {

    @Test
    void managementContractDoesNotDependOnProxyName()
            throws Exception {

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxConfiguration.class)) {

            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "learning.jmx:type=Inventory,name=Primary"
            );

            assertTrue(server.isRegistered(name));

            boolean hasAvailableItems = Arrays.stream(
                server.getMBeanInfo(name).getAttributes()
            ).anyMatch(a ->
                "AvailableItems".equals(a.getName())
                && "int".equals(a.getType())
            );

            boolean hasRefresh = Arrays.stream(
                server.getMBeanInfo(name).getOperations()
            ).anyMatch(o -> "refresh".equals(o.getName()));

            assertTrue(hasAvailableItems);
            assertTrue(hasRefresh);
        }
    }
}
\`\`\`

Điều kiện để ví dụ chạy: exporter phải sử dụng platform MBeanServer và InventoryManagement phải được đăng ký thành Spring bean; nếu \`JmxConfiguration\` chỉ có facade mà thiếu component scanning/service bean, context sẽ không tạo thành công. Trong dự án thực, import configuration đầy đủ và nếu có nhiều test chạy song song, dùng MBeanServer riêng hoặc ObjectName phân vùng.

Quan trọng hơn là nguyên tắc kiểm thử contract qua \`MBeanInfo\`, không phải kiểm tra tên Java class proxy.

## 16. Khi export proxy là lựa chọn có chủ đích

Có trường hợp cần export một proxy để giữ hành vi AOP khi JMX client gọi method.

Để làm an toàn:

- Không dùng proxy class name làm ObjectName.
- Chọn management interface rõ ràng hoặc metadata assembler hiểu proxy/target class.
- Đảm bảo management methods thực sự callable trên proxy.
- Kiểm tra AOP advice thực thi đúng khi gọi qua JMX.
- Kiểm chứng MBeanInfo qua integration test.
- Tài liệu hóa các proxy interfaces và constraints.
- Kiểm thử hồi quy sau khi thay version Spring hoặc thay proxy strategy.

Khi mọi điều kiện trên được thỏa mãn, export proxy không phải lúc nào cũng sai. Vấn đề là **export proxy một cách tình cờ và cho phép nó định nghĩa contract ngoài ý muốn**.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| MBean mất sau khi bật @Transactional | Bean runtime trở thành proxy, exporter/metadata thay đổi | Kiểm tra target class, exporter và MBeanServer |
| ObjectName chứa tên proxy sinh động | Naming dựa vào bean.getClass() | Dùng ObjectName logic cố định |
| Operation biến mất khi chuyển sang JDK proxy | Method chỉ có ở implementation, không nằm trên proxy interface | Dùng management facade, interface phù hợp hoặc exporter strategy được kiểm chứng |
| MBean tồn tại nhưng invoke lỗi | Metadata có method nhưng proxy không expose/invocable | Kiểm tra MBeanInfo và call path |
| Chuyển sang CGLIB không giải quyết lỗi | Nguyên nhân ở exporter, ObjectName hoặc advisor | Debug từng lớp, không đoán |
| Transaction advice không chạy qua JMX | JMX gọi target thô hoặc self-invocation bypass advice | Cho management facade gọi Spring proxy và test |
| Security annotation không ngăn JMX operation | Method-level advice không chạy hoặc connector quá rộng | Kiểm tra cả proxy path và JMX authorization |
| Final method không được advice | Class-based proxy không override final method | Đổi thiết kế hoặc proxy strategy thích hợp |
| Client báo AttributeNotFoundException sau refactor | Getter JMX bị đổi tên | Giữ management contract và compatibility accessor |
| Hai contexts đè MBean của nhau | Trùng ObjectName/RegistrationPolicy | Phân vùng naming hoặc ownership |
| JConsole không thấy MBean | Sai MBeanServer/JVM hoặc export lỗi | Dùng isRegistered trên server đích |

## 18. Quy trình debug theo từng lớp

**Bước 1: Xác định bean/proxy thực tế.** Dùng \`AopUtils.isAopProxy\`, \`isJdkDynamicProxy\`, \`isCglibProxy\` và \`getTargetClass\`.

**Bước 2: Xác định registration.** Kiểm tra \`MBeanServer.isRegistered(ObjectName)\` trên đúng server.

**Bước 3: Kiểm tra metadata.** Dùng \`getMBeanInfo\` để xem attribute, operation và signature thực tế.

**Bước 4: Kiểm tra invocation.** Dùng \`getAttribute\` và \`invoke\` qua JMX, xác nhận kết quả và tác dụng phụ.

**Bước 5: Kiểm tra advice.** Với transaction hoặc security, xác định call path đi qua Spring proxy và advisor đúng.

**Bước 6: Kiểm tra naming/lifecycle.** Đảm bảo ObjectName không phụ thuộc runtime proxy name và exporter cleanup đúng khi context đóng.

**Bước 7: So sánh trước/sau refactor.** Test hợp đồng, không chỉ Java unit tests.

## 19. Bài tập thực hành

### Bài tập 1 — Quan sát proxy

Tạo \`InventoryServiceImpl\` có interface và một advisor thực sự hoạt động. Sử dụng \`AopUtils\` để kiểm tra class runtime, target class và kiểu proxy.

Hãy giải thích vì sao không nên lấy \`bean.getClass().getSimpleName()\` làm ObjectName.

### Bài tập 2 — Xây management facade

Tạo \`InventoryManagement\` chứa:

\`\`\`java
@ManagedAttribute
public int getAvailableItems() { ... }

@ManagedOperation
public void refresh() { ... }
\`\`\`

Facade nhận \`InventoryService\` bằng constructor injection. Export facade qua Spring JMX và kiểm tra ObjectName.

### Bài tập 3 — Đổi proxy strategy

Trong môi trường test, chuyển từ JDK dynamic proxy sang class-based proxy. Giữ nguyên management facade và kiểm tra JMX contract không đổi.

### Bài tập 4 — Kiểm chứng AOP advice

Một operation JMX phải gọi method nghiệp vụ có transaction advice. Viết integration test chứng minh invocation qua JMX đi qua proxy service thay vì target được tạo thủ công.

### Bài tập 5 — Phân tích anti-pattern

Một developer export trực tiếp object được trả về từ \`context.getBean("service")\` và lấy tên runtime class làm ObjectName. Hãy nêu những rủi ro về naming, method surface, metadata và refactor. Đề xuất cách thay bằng management facade có ObjectName cố định.

## 20. Checklist khi muốn giữ contract JMX ổn định

1. ObjectName có được xác định theo logical resource thay vì proxy runtime class?
2. Management interface có ít attributes/operations, được tài liệu hóa?
3. Metadata được export từ class/interface đúng?
4. Có kiểm tra JDK proxy vs class-based proxy khi thay đổi AOP?
5. Management methods có thể được gọi qua đường JMX?
6. Transaction/security/audit advice có được áp dụng đúng?
7. Có getter hoặc operation nào đổi tên sau refactor?
8. Có test MBeanInfo, attribute types và signatures?
9. Có test ObjectName và MBeanServer đích?
10. Có tách facade nếu service proxy thay đổi thường xuyên?
11. Có tránh đăng ký thủ công target thô ngoài lifecycle Spring?
12. Có kiểm tra remote JMX authorization cho thao tác nhạy cảm?

## 21. Ghi nhớ cốt lõi

- Runtime Spring AOP bean có thể là proxy, không phải target class nguyên bản.
- Không nên để proxy class name hoặc proxy interfaces ngẫu nhiên quyết định JMX contract.
- **Mục tiêu là export một management contract ổn định**, không nhất thiết luôn phải bỏ proxy.
- Đăng ký target trực tiếp có thể làm mất advice quan trọng; hãy hiểu invocation path trước khi làm.
- Management facade cung cấp ObjectName, attribute và operation names ổn định, đồng thời gọi service proxy để giữ AOP behavior.
- Kiểm chứng qua MBeanServer và MBeanInfo, không chỉ Java reflection hoặc JConsole.
- Thay proxy strategy là thay đổi đáng kiểm thử đối với JMX integration và security.

## Tài liệu tham khảo

- Spring Framework JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework AOP Proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework AopUtils API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework ManagedResource API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework MBeanExporter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 MBeanServer API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
