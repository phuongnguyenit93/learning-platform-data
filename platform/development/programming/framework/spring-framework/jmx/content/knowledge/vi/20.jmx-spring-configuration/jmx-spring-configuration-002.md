# Cấu hình JMX bằng XML namespace context trong Spring Framework

## 1. Mục tiêu bài học

Spring Framework hỗ trợ xuất Spring beans thành JMX MBeans bằng cấu hình Java, annotation hoặc XML. Với dự án sử dụng Spring XML application context, cách cấu hình ngắn gọn và phổ biến là khai báo **namespace \`context\`** rồi dùng phần tử:

\`\`\`xml
<context:mbean-export/>
\`\`\`

Phần tử này kích hoạt cơ chế xuất bean có **Spring JMX annotation metadata** thành MBean và giúp thiết lập các thành phần cần thiết như exporter, nguồn metadata, assembler và chiến lược đặt tên. Nó không biến tất cả bean trong container thành MBean theo cách tùy tiện và cũng không tự mở cổng JMX remote.

Sau bài học, bạn có thể:

1. Khai báo namespace \`context\` và XSD tương ứng trong XML.
2. Hiểu vai trò của \`<context:mbean-export/>\` trong annotation-driven JMX.
3. Phân biệt \`context:mbean-export\` với \`context:component-scan\`, \`MBeanExporter\` thủ công và JMX remote connector.
4. Viết bean với \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` rồi export bằng XML.
5. Chỉ định \`MBeanServer\` khi ứng dụng có nhiều server hoặc cần dùng platform server cụ thể.
6. Kiểm tra \`ObjectName\`, \`MBeanInfo\`, lỗi trùng tên và khác biệt giữa Spring Framework XML và Spring Boot.
7. Đánh giá rủi ro bảo mật khi các MBean được expose.

## 2. Mô hình hoạt động

\`\`\`text
               applicationContext.xml
               +---------------------+
               | <context:component-scan/>
               | <context:mbean-export/>
               +----------+----------+
                          |
                Spring ApplicationContext
                          |
               +----------+-----------+
               |                      |
          Spring beans        JMX export support
               |                      |
               |              Annotation metadata
               |                      |
               |                MBeanExporter
               |                      |
               +----------------------+
                          |
                   MBeanServer
                          |
                       ObjectName
                          |
                      JMX clients
\`\`\`

**Hai việc khác nhau:**
- \`<context:component-scan/>\` tạo hoặc phát hiện Spring beans từ các class có stereotype annotations.
- \`<context:mbean-export/>\` cấu hình cơ chế export những Spring beans có JMX management metadata phù hợp sang \`MBeanServer\`.

Nếu bean được khai báo bằng \`<bean>\` thay vì component scan, nó vẫn có thể được export khi có annotation JMX phù hợp và exporter phát hiện được. Không bắt buộc phải dùng component scan để JMX export hoạt động.

## 3. Namespace context và XML schema

Một cấu hình XML cơ bản:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="com.example.monitoring"/>

    <context:mbean-export/>

</beans>
\`\`\`

Trong đó:

- \`xmlns\` mặc định là namespace \`beans\`, cho phép khai báo \`<bean>\`, \`<property>\` và những thành phần Spring container.
- \`xmlns:context\` khai báo prefix \`context\` cho các phần tử bổ sung của Spring, bao gồm \`mbean-export\`.
- \`xsi:schemaLocation\` ánh xạ namespace URIs đến vị trí XSD để parser/IDE nhận diện cú pháp.
- \`<context:component-scan>\` quét package \`com.example.monitoring\` và đăng ký các class có stereotype annotations.
- \`<context:mbean-export/>\` bật annotation-driven JMX export.

Các URI namespace thường dùng dạng \`http://www.springframework.org/schema/...\` làm **namespace identifier**; URL XSD có thể dùng HTTPS. Parser Spring có cơ chế ánh xạ schema nội bộ theo dependency Spring tương ứng; không nên suy luận rằng mỗi lần khởi động phải tải XSD qua Internet.

### Ví dụ thiếu prefix

\`\`\`xml
<!-- Sai nếu chưa khai báo xmlns:context -->
<context:mbean-export/>
\`\`\`

Nếu XML chưa định nghĩa \`xmlns:context\` và schema location phù hợp, parser không nhận diện được phần tử.

### Tại sao gọi là "XML namespace context"?

Đây là XML namespace của Spring Framework, không phải tên một class Java \`Context\` hay một JMX domain. Nó là cách Spring XML cấu hình các tính năng như component scanning, annotation configuration và JMX export.

## 4. Managed bean với annotation JMX

Tạo một bean đơn giản:

\`\`\`java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders",
    description = "Order queue administration"
)
public class OrderQueueMonitor {

    private final AtomicInteger pending = new AtomicInteger();

    @ManagedAttribute(description = "Current pending jobs")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedOperation(description = "Reset queue counter")
    public void resetCounter() {
        pending.set(0);
    }

    public void recordPending(int count) {
        pending.set(count);
    }
}
\`\`\`

Khi ứng dụng nạp XML ở mục 3:

1. Component scan phát hiện \`OrderQueueMonitor\` và tạo Spring bean.
2. JMX export support đọc \`@ManagedResource\`.
3. Tên JMX được lấy từ \`objectName\`.
4. \`getPendingCount()\` được expose làm JMX attribute \`PendingCount\`.
5. \`resetCounter()\` được expose làm JMX operation.
6. \`recordPending(int)\` không tự động thành operation chỉ vì nó là method public.

**Quan trọng:** \`@ManagedResource\` cung cấp metadata cấp lớp; \`@ManagedAttribute\` và \`@ManagedOperation\` mô tả bề mặt quản trị ở cấp phương thức. Không gắn annotation mà mong toàn bộ public methods tự xuất hiện theo cùng cơ chế.

## 5. Kiểm tra kết quả sau khi load XML

Giả sử XML nằm trong classpath tại \`applicationContext.xml\`:

\`\`\`java
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class JmxXmlDemo {
    public static void main(String[] args) throws Exception {
        try (ClassPathXmlApplicationContext context =
                 new ClassPathXmlApplicationContext(
                     "applicationContext.xml"
                 )) {

            // Ứng dụng giữ context hoạt động trong vòng đời sử dụng.
            var server =
                java.lang.management.ManagementFactory
                    .getPlatformMBeanServer();

            var name = new javax.management.ObjectName(
                "com.example.monitoring:type=Queue,name=Orders"
            );

            System.out.println(
                "Registered: " + server.isRegistered(name)
            );

            if (server.isRegistered(name)) {
                var info = server.getMBeanInfo(name);

                System.out.println(
                    "MBean description: " + info.getDescription()
                );

                for (var attribute : info.getAttributes()) {
                    System.out.println(
                        "Attribute: " + attribute.getName()
                    );
                }

                for (var operation : info.getOperations()) {
                    System.out.println(
                        "Operation: " + operation.getName()
                    );
                }
            }
        }
    }
}
\`\`\`

Đây là minh họa kiểm tra từ cùng JVM. Nếu exporter sử dụng một \`MBeanServer\` khác với platform server, hãy lấy đúng server do Spring cấu hình thay vì giả định \`ManagementFactory.getPlatformMBeanServer()\` luôn là đích.

Để kiểm chứng trên môi trường thật, có thể kết nối JConsole vào đúng JVM, chọn tab **MBeans**, duyệt domain \`com.example.monitoring\` và kiểm tra attributes/operations.

### Tại sao có thể đọc được MBeanInfo?

\`MBeanInfo\` mô tả giao diện quản trị của MBean:
- Description của MBean.
- Danh sách attributes và kiểu dữ liệu.
- Readable/writable flags.
- Danh sách operations và chữ ký.
- Notification metadata nếu có.

Đó là dữ liệu JMX client thực sự nhìn thấy, khác với việc chỉ soi annotation bằng reflection trong source.

## 6. Phần tử context:mbean-export làm gì?

\`<context:mbean-export/>\` thiết lập annotation-driven MBean export trong application context.

Về mặt khái niệm:

\`\`\`text
<context:mbean-export/>
        |
        v
AnnotationJmxAttributeSource
        |
        +--> MetadataMBeanInfoAssembler
        |          |
        |          v
        |    Attributes/operations
        |
        +--> MetadataNamingStrategy
                   |
                   v
                ObjectName
        |
        v
     MBeanExporter
        |
        v
     MBeanServer
\`\`\`

Đây là sơ đồ vai trò, không phải cam kết từng phiên bản Spring luôn tạo bean với cùng tên nội bộ. Cấu hình namespace giúp gom phần boilerplate exporter, assembler, metadata reader và naming support.

### Điều nó không làm

\`<context:mbean-export/>\` không tự:
- Mở remote RMI connector hoặc JMX TCP port.
- Tạo JMX client.
- Đăng ký mọi \`@Component\` không có metadata quản trị phù hợp.
- Chuyển các \`@RestController\` endpoints thành JMX operations.
- Thay thế Spring Boot Actuator configuration.
- Cài đặt authentication/authorization cho remote JMX.
- Tạo metrics registry hoặc lưu lịch sử notification bền vững.

Việc export MBean là một vấn đề; cách client tiếp cận MBeanServer là vấn đề khác.

## 7. Tùy chỉnh MBeanServer trong XML

Khi có nhiều MBeanServers hoặc cần dùng platform server một cách tường minh, có thể định nghĩa server bean và tham chiếu từ \`mbean-export\` theo thuộc tính \`server\` được hỗ trợ trong Spring XML namespace.

Một cách khai báo platform MBeanServer bằng factory method:

\`\`\`xml
<bean id="platformMBeanServer"
      class="java.lang.management.ManagementFactory"
      factory-method="getPlatformMBeanServer"/>

<context:mbean-export server="platformMBeanServer"/>
\`\`\`

Ví dụ này có thể đặt bên trong \`<beans>\` cùng namespace declarations ở mục 3.

Ý nghĩa:
- Bean \`platformMBeanServer\` là reference tới platform MBeanServer hiện tại.
- \`server="platformMBeanServer"\` hướng cơ chế export đến MBeanServer đó.
- Cách này tránh phụ thuộc vào lựa chọn tự động khi JVM có nhiều MBeanServer.

Nếu môi trường Spring Framework cụ thể có cấu hình XML khác hoặc namespace schema phiên bản không hỗ trợ thuộc tính cần dùng, dùng \`MBeanExporter\` tường minh với property \`server\` là phương án khác.

### Vì sao nên xác định server?

Một JVM có thể chứa:
- Platform MBeanServer.
- Custom MBeanServer của embedded container.
- Server do application server cung cấp.
- Server riêng của module kiểm thử.

MBean đăng ký vào một server không tự xuất hiện trong server khác. Nếu JConsole hoặc connector đang nhìn platform server nhưng exporter lại dùng custom server, bạn có thể tưởng ứng dụng không export.

## 8. XML bean definition mà không dùng component scan

Không bắt buộc phải dùng \`@Component\` nếu muốn tạo bean qua XML:

\`\`\`xml
<bean id="orderQueueMonitor"
      class="com.example.monitoring.OrderQueueMonitor"/>

<context:mbean-export/>
\`\`\`

Miễn là class có metadata JMX được exporter/assembler nhận diện, bean được tạo bằng XML cũng là ứng viên export.

Do đó:
- \`context:component-scan\` phục vụ **bean discovery**.
- \`context:mbean-export\` phục vụ **JMX management export**.

Có thể dùng một trong hai cách tạo bean:
- Khai báo \`<bean>\` tường minh.
- Quét \`@Component\` bằng \`context:component-scan\`.

Tùy dự án, có thể phối hợp nhưng cần tránh đăng ký hai Spring beans khác nhau mang cùng ObjectName.

## 9. Đăng ký tường minh bằng XML với MBeanExporter

Trong trường hợp muốn kiểm soát chính xác những bean nào được export, có thể cấu hình \`MBeanExporter\` tường minh thay vì dùng annotation autodetection.

Ví dụ một Standard MBean:

\`\`\`java
package com.example.monitoring;

public interface CacheMonitorMBean {
    int getEntryCount();
    void resetStats();
}
\`\`\`

\`\`\`java
package com.example.monitoring;

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public int getEntryCount() {
        return 42;
    }

    @Override
    public void resetStats() {
        // Cập nhật số liệu theo logic ứng dụng.
    }
}
\`\`\`

XML:

\`\`\`xml
<bean id="cacheMonitor"
      class="com.example.monitoring.CacheMonitor"/>

<bean id="jmxExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.monitoring:type=Cache,name=Products"
                   value-ref="cacheMonitor"/>
        </map>
    </property>
</bean>
\`\`\`

Ở cách này:
- Exporter nhận danh sách bean tường minh.
- Tên JMX được chỉ ra bằng key trong map.
- Một Standard MBean có interface \`CacheMonitorMBean\` xác định các methods quản trị.
- Không cần annotation trên class nếu compliant Standard MBean interface được dùng.

Nếu muốn export POJO annotation-based bằng \`MBeanExporter\` tường minh, phải cấu hình metadata source/assembler/naming strategy phù hợp; chỉ khai báo \`setBeans\` không tự bảo đảm mọi annotation sẽ được áp dụng.

### Không khai báo hai exporter trùng nhau

Ví dụ cấu hình cần tránh:

\`\`\`xml
<context:mbean-export/>

<bean id="jmxExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <!-- Cấu hình thêm một exporter cùng một tập MBean -->
</bean>
\`\`\`

Có thể có trường hợp cần nhiều exporter với ownership tách biệt, nhưng không nên thêm exporter thứ hai khi đã có namespace export hoạt động mà chưa xác định rõ từng tập bean và server.

Nếu hai exporter cố đăng ký cùng ObjectName trên cùng server, sẽ xảy ra registration collision tùy policy.

## 10. Naming: ObjectName và Java bean name

Trong XML:

\`\`\`xml
<bean id="orderQueueMonitor"
      class="com.example.monitoring.OrderQueueMonitor"/>
\`\`\`

\`orderQueueMonitor\` là Spring bean name.

Trong annotation:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
\`\`\`

\`com.example.monitoring:type=Queue,name=Orders\` là JMX ObjectName.

Một ObjectName thường có cấu trúc:

\`\`\`text
domain:key=value,key=value
\`\`\`

Ví dụ:

\`\`\`text
com.example.monitoring:type=Queue,name=Orders
\`\`\`

Không nên đặt ObjectName thành một chuỗi tùy ý chỉ có Spring bean name nếu nó không phù hợp cú pháp JMX.

### ObjectName có wildcard

\`\`\`java
ObjectName query = new ObjectName(
    "com.example.monitoring:type=Queue,*"
);
\`\`\`

Đây là pattern để query nhiều MBeans. Một MBean cụ thể cần concrete ObjectName.

### Giá trị động

Nếu tên cần chứa dấu phẩy hoặc dấu bằng từ cấu hình:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Queue");
properties.put("name", ObjectName.quote("Orders,EU=West"));

ObjectName name = new ObjectName(
    "com.example.monitoring",
    properties
);
\`\`\`

Với ObjectName động theo tenant/instance, annotation có giá trị compile-time constant thường không đủ linh hoạt; cần naming strategy hoặc explicit mapping/programmatic registration.

## 11. Bean lifecycle và đăng ký JMX

Khi Spring context được khởi động bình thường:

\`\`\`text
Read XML config
      |
      v
Create Spring beans
      |
      v
Initialize JMX export support
      |
      v
Register MBeans
      |
      v
JMX clients use ObjectNames
      |
      v
Close ApplicationContext
      |
      v
Exporter unregisters MBeans it owns
\`\`\`

Cần quan tâm:
- Không phải mọi Spring bean đều được export.
- Một MBean có thể đã tồn tại ở server trước khi context khởi động.
- Nếu context đóng bình thường, exporter dọn dẹp những đăng ký thuộc trách nhiệm của mình theo lifecycle/policy.
- Nếu JVM bị kill hoặc crash, không thể trông chờ logic shutdown hoàn tất.
- Nhiều Spring contexts có thể cùng dùng platform MBeanServer và tranh chấp tên.

Một ObjectName ổn định giúp tooling quản trị dễ tìm MBean nhưng có thể gây collision khi nhiều instance của cùng class được export vào một server.

## 12. XML schema và phiên bản Spring

Khi làm việc với cấu hình XML, có ba lớp tương thích cần phân biệt:

1. **Spring Framework version:** namespace parser và các thuộc tính của \`context:mbean-export\`.
2. **JDK version:** JMX API và module \`java.management\`.
3. **Application dependencies:** các Spring jars cung cấp context và JMX support.

Spring 5/6 đều có cơ chế JMX export, nhưng một số API hoặc property có thể thay đổi theo phiên bản. Với Spring 6/7 cần dùng dependency và Java version tương ứng.

Nếu XML parser báo:

\`\`\`text
Cannot locate BeanDefinitionParser for element [mbean-export]
\`\`\`

hoặc lỗi XSD:
- Kiểm tra \`spring-context\` dependency có mặt.
- Kiểm tra namespace URI và schema location đúng.
- Kiểm tra phiên bản Spring jars đồng bộ.
- Kiểm tra thuộc tính đang dùng có được schema của phiên bản hỗ trợ không.

Không nên sửa lỗi bằng cách trộn nhiều phiên bản Spring jars hoặc thay namespace thành một URL tùy ý.

## 13. Khác biệt với Spring Boot auto-configuration

Một dự án Spring Framework XML truyền thống thường nạp:

\`\`\`java
new ClassPathXmlApplicationContext("applicationContext.xml");
\`\`\`

Spring Boot thường sử dụng \`@SpringBootApplication\` và auto-configuration. Boot có cơ chế JMX export riêng, phụ thuộc các property như \`spring.jmx.enabled\` và cấu hình Actuator.

Nếu tích hợp XML legacy vào Boot bằng \`@ImportResource\`:

\`\`\`java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ImportResource;

@SpringBootApplication
@ImportResource("classpath:legacy-jmx.xml")
public class Application {
}
\`\`\`

cần kiểm tra xem Boot đã tạo exporter chưa. Nếu XML cũng có \`<context:mbean-export/>\`, có thể xảy ra duplicate registration.

Để kiểm soát, cần quyết định một đường cấu hình chính:
- Spring XML namespace export.
- Java \`@EnableMBeanExport\`.
- Spring Boot auto-configuration.
- \`MBeanExporter\` cấu hình tường minh.

Việc dùng nhiều đường chỉ nên có chủ đích, ownership và ObjectNames không trùng.

## 14. Kiểm tra lỗi khi XML export không thành công

### 14.1. MBean không xuất hiện

Nguyên nhân có thể:
- XML context chưa được nạp.
- Chưa khai báo \`context:mbean-export\`.
- Bean đích chưa được tạo hoặc package scan sai.
- Annotation metadata không phù hợp.
- Exporter sử dụng MBeanServer khác.
- ObjectName sai hoặc xung đột.

Quy trình:
1. Xác minh Spring bean tồn tại trong context.
2. Kiểm tra XML namespace parser hoạt động.
3. Xác minh exporter đã khởi tạo.
4. Kiểm tra log registration.
5. Truy vấn đúng \`MBeanServer\` bằng \`isRegistered()\`.
6. Đọc \`MBeanInfo\` khi MBean đã xuất hiện.

### 14.2. Xung đột ObjectName

Hai bean có thể cùng khai báo:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
\`\`\`

Nếu cả hai được export vào cùng server, JMX không cho cùng một ObjectName đăng ký hai MBeans đồng thời.

Giải pháp:
- Đặt \`instance\` hoặc \`name\` phân biệt.
- Giảm phạm vi autodetection.
- Tránh nhiều exporters trùng một tập MBean.
- Chọn registration policy có chủ đích nếu cần, không dùng replace bừa bãi.

### 14.3. Attribute hoặc operation thiếu

Nếu tên MBean đã có nhưng giao diện sai:
- Kiểm tra \`@ManagedAttribute\`/\`@ManagedOperation\`.
- Kiểm tra getter/setter conventions.
- Kiểm tra metadata assembler.
- Kiểm tra Spring proxy/AOP có làm thay đổi object được export không.
- Dùng \`MBeanInfo.getAttributes()\`/\`getOperations()\`.

### 14.4. JConsole không kết nối được

Cấu hình \`<context:mbean-export/>\` không bật JMX remote. Muốn kết nối từ máy khác, cần JMX connector và security/network configuration.

Nếu JConsole local attach được nhưng remote không, nguyên nhân thường nằm ở remote connector/RMI port, firewall, hostname hoặc xác thực, không phải thiếu XML namespace.

## 15. Bảo mật: Export không đồng nghĩa cấp quyền

MBeans có thể cung cấp:
- Read-only metrics hoặc status.
- Writable configuration attributes.
- Operations thay đổi state.
- Thông tin JVM và ứng dụng.

Một ví dụ nhạy cảm:

\`\`\`java
@ManagedOperation(description = "Clear all queued jobs")
public void clearAllJobs() {
    queueService.clearAll();
}
\`\`\`

Nếu exporter expose operation ấy, người dùng có quyền JMX tương ứng có thể gọi nó. Vì vậy:
- Không expose method nhạy cảm chỉ để debug thuận tiện.
- Hạn chế quyền \`invoke\` và \`setAttribute\`.
- Bảo vệ remote connector, đặc biệt khi qua mạng công cộng.
- Tránh trả secrets và dữ liệu cá nhân qua managed attributes.
- Ghi log/audit các thao tác có tác động lớn khi cần.
- Review mỗi annotation quản trị như thay đổi một administrative API.

\`<context:mbean-export/>\` chỉ cấu hình cơ chế export; nó không tự cấp/cấm quyền theo từng method.

## 16. XML namespace và các lựa chọn thay thế

| Cách cấu hình | Phù hợp khi | Đặc điểm |
|---|---|---|
| \`<context:mbean-export/>\` | Ứng dụng Spring XML có JMX annotations | Ngắn gọn, tự thiết lập annotation export |
| \`@EnableMBeanExport\` | Java \`@Configuration\` | Tương đương về ý tưởng annotation-driven export |
| \`MBeanExporter\` bean tường minh | Muốn kiểm soát bean list, assembler, server | Linh hoạt nhưng nhiều boilerplate |
| Spring Boot JMX auto-config | Ứng dụng Boot và cấu hình bằng properties | Cần hiểu cơ chế Boot/Actuator hiện hành |

Không nên chọn “cái nào hiện đại nhất” mà bỏ qua cấu trúc dự án. Với ứng dụng XML legacy, \`context:mbean-export\` thường là cách ngắn gọn, dễ duy trì. Khi dự án đang chuyển dần sang Java config, có thể dùng \`@EnableMBeanExport\`. Với yêu cầu bảo mật chặt và allowlist, exporter tường minh có thể thích hợp hơn.

## 17. Thực hành tổng hợp

### Bài tập A — Export bean bằng XML namespace

1. Tạo \`OrderQueueMonitor\` có \`@Component\`, \`@ManagedResource\`, \`@ManagedAttribute\`.
2. Tạo \`applicationContext.xml\` gồm \`context:component-scan\` và \`context:mbean-export\`.
3. Khởi tạo \`ClassPathXmlApplicationContext\`.
4. Truy vấn \`com.example.monitoring:type=Queue,name=Orders\`.
5. Kiểm tra attribute và operation qua \`MBeanInfo\`.
6. Đóng context.

### Bài tập B — Không dùng component-scan

1. Gỡ \`@Component\`.
2. Khai báo bean bằng \`<bean id="..." class="..."/>\`.
3. Giữ \`@ManagedResource\` và namespace export.
4. Khởi động lại context.
5. Xác minh MBean vẫn có thể được export.

### Bài tập C — Chỉ định platform MBeanServer

1. Tạo factory bean từ \`ManagementFactory.getPlatformMBeanServer()\`.
2. Cấu hình \`server\` cho namespace export.
3. Kiểm tra platform MBeanServer trực tiếp.
4. So sánh với custom server nếu môi trường test hỗ trợ.

### Bài tập D — Tạo xung đột để quan sát

1. Tạo hai beans có cùng ObjectName.
2. Cho exporter xét cả hai.
3. Quan sát exception/collision.
4. Sửa naming hoặc phạm vi export.
5. Xác minh lại bằng \`isRegistered()\`.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** \`<context:mbean-export/>\` được dùng để làm gì?  
**Trả lời:** Bật annotation-driven JMX export trong Spring XML application context.

**Câu 2.** \`<context:component-scan/>\` có tự export MBeans không?  
**Trả lời:** Không. Nó đăng ký Spring beans; JMX export là cơ chế khác.

**Câu 3.** Có \`@ManagedResource\` nhưng không khai báo exporter thì MBean có xuất hiện không?  
**Trả lời:** Không thể trông chờ. Annotation chỉ là metadata, cần cơ chế export.

**Câu 4.** XML namespace export có tự mở remote JMX RMI port không?  
**Trả lời:** Không. Remote connector phải được cấu hình riêng.

**Câu 5.** Muốn đảm bảo MBeans nằm trong platform server phải làm gì?  
**Trả lời:** Chỉ định \`ManagementFactory.getPlatformMBeanServer()\` cho exporter nếu cần chắc chắn, rồi xác minh trên đúng server.

**Câu 6.** Tại sao không nên đồng thời bật namespace export và khai báo exporter thứ hai trùng tập beans?  
**Trả lời:** Có thể dẫn đến registration collision cùng ObjectName.

**Câu 7.** Nếu MBean đã có nhưng thiếu operation, kiểm tra ở đâu?  
**Trả lời:** Xem annotation/assembler và \`MBeanInfo.getOperations()\` của MBean đã đăng ký.

## 19. Ghi nhớ

- \`<context:mbean-export/>\` là cách cấu hình annotation-driven JMX export bằng XML namespace \`context\`.
- XML phải khai báo \`xmlns:context\` và schema location phù hợp.
- \`context:component-scan\` tạo Spring beans; \`context:mbean-export\` quản lý xuất những bean có metadata JMX thích hợp.
- \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` định nghĩa hợp đồng quản trị được exporter đọc.
- Cần phân biệt Spring bean name, JMX ObjectName và MBeanServer.
- Có thể cấu hình target MBeanServer khi môi trường có nhiều server.
- Namespace export không tự bật JMX remote connection hay authorization.
- Tránh nhiều exporter trùng nhiệm vụ và trùng ObjectName.
- Kiểm chứng hiệu lực bằng \`MBeanServer.isRegistered()\` và \`getMBeanInfo()\` trên server thực tế.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — XML Schema-based Configuration: https://docs.spring.io/spring-framework/reference/core/appendix/xsd-schemas.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`@EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
