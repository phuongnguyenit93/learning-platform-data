# Chọn MBeanServer bằng thuộc tính server trong Spring Framework JMX

## Mục tiêu

Bài này giải thích vai trò của thuộc tính `server` trong Spring `MBeanExporter`, cách chọn một `MBeanServer` tùy biến và cách kiểm chứng rằng managed beans thực sự được đăng ký đúng registry.

Bạn sẽ biết cách sử dụng Java configuration, XML, `@EnableMBeanExport`, phân biệt MBeanServer với JMX connector, quản lý vòng đời và tránh xung đột ObjectName trong nhiều Spring contexts.

## 1. MBeanServer là registry của các MBean

JMX cung cấp MBeanServer để đăng ký và quản lý các MBeans. Mỗi đăng ký sử dụng một ObjectName:

```java
ObjectName name = new ObjectName("learning.jmx:type=CacheMonitor,name=Products");
server.registerMBean(cacheMonitor, name);
```

Client tìm MBean trong server bằng `isRegistered`, `getAttribute`, `invoke` và `queryNames`.

Một JVM có thể có nhiều MBeanServers. MBean đăng ký ở server A không tự xuất hiện ở server B. ObjectName chỉ định danh registration trong phạm vi một MBeanServer.

Platform MBeanServer thông thường:

```java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
```

Nhưng Spring có thể export vào server khác nếu được cấu hình.

## 2. Thuộc tính server của MBeanExporter

`MBeanExporter` là thành phần Spring xuất bean thành JMX MBean. Thuộc tính `server` xác định nơi đăng ký:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setServer(chosenMBeanServer);
```

Trong XML:

```xml
<property name="server" ref="managementMBeanServer"/>
```

Thuộc tính này là tham chiếu tới một object MBeanServer, **không phải hostname, port, JMX URL hoặc ObjectName**.

Sơ đồ:

```text
Spring ApplicationContext
  |
  +-- CacheMonitor
  +-- MBeanExporter
         |
         | server = customMBeanServer
         v
     Custom MBeanServer
         |
         +-- learning.jmx:type=CacheMonitor,name=Products
```

Ba quyết định cần tách biệt:

| Quyết định | Cấu hình | Ý nghĩa |
|---|---|---|
| Export bean nào? | `setBeans` hoặc autodetection | Chọn resource |
| Đăng ký tên nào? | ObjectName hoặc naming strategy | Chọn tên MBean |
| Đăng ký tại đâu? | `server` / `setServer` | Chọn MBeanServer |

Một JMX connector là lớp kết nối client tới server và cần cấu hình riêng nếu dùng truy cập từ JVM khác.

## 3. Khi nào nên dùng custom MBeanServer?

Các trường hợp điển hình:

- Integration test cần cô lập khỏi platform server và những test khác.
- Một JVM chạy nhiều ApplicationContext cần registry riêng.
- Framework hoặc container cung cấp MBeanServer cụ thể.
- Một module có nhu cầu quản trị riêng hoặc connector riêng.
- Cần kiểm chứng rõ ranh giới giữa các tập MBeans.

Lưu ý một server riêng có thể khiến MBeans không xuất hiện trong công cụ đang xem platform MBeanServer. Đây không nhất thiết là lỗi đăng ký.

Nếu mục tiêu là quan sát cùng các platform MBeans bằng công cụ tiêu chuẩn, dùng platform MBeanServer thường đơn giản hơn.

## 4. Tạo một Standard MBean

Tệp CacheMonitorMBean.java:

```java
package example.jmx;

public interface CacheMonitorMBean {
    int getEntryCount();
    void clear();
}
```

Tệp CacheMonitor.java:

```java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheMonitor implements CacheMonitorMBean {
    private final AtomicInteger count = new AtomicInteger(12);

    @Override
    public int getEntryCount() {
        return count.get();
    }

    @Override
    public void clear() {
        count.set(0);
    }
}
```

Lớp CacheMonitor và interface CacheMonitorMBean tuân theo Standard MBean convention. Attribute `EntryCount` và operation `clear` có thể được JMX client truy cập sau khi bean được đăng ký.

## 5. Java configuration: chọn custom MBeanServer

```java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class CustomJmxConfiguration {

    @Bean(name = "managementMBeanServer")
    public MBeanServer managementMBeanServer() {
        return MBeanServerFactory.createMBeanServer("learning.management");
    }

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            @Qualifier("managementMBeanServer") MBeanServer server,
            CacheMonitor monitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
                "learning.jmx:type=CacheMonitor,name=Products",
                monitor
        ));
        return exporter;
    }
}
```

Ở đây exporter nhận đúng bean managementMBeanServer. Chỉ tạo MBeanServer nhưng không truyền vào exporter sẽ không bảo đảm exporter dùng server đó.

`Map.of` yêu cầu Java 9 trở lên; với Java 8 có thể dùng một `Map` thông thường.

## 6. Kiểm chứng đúng server

```java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class InspectServer {
    public static void main(String[] args) throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=CacheMonitor,name=Products"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    CustomJmxConfiguration.class)) {

            MBeanServer custom = context.getBean(
                "managementMBeanServer", MBeanServer.class
            );
            MBeanServer platform =
                ManagementFactory.getPlatformMBeanServer();

            System.out.println("Custom: " + custom.isRegistered(name));
            System.out.println("Platform: " + platform.isRegistered(name));
            System.out.println(
                "Entries: " + custom.getAttribute(name, "EntryCount")
            );
        }
    }
}
```

Trong môi trường riêng, không có đăng ký cùng tên trên platform server, kết quả dự kiến:

```text
Custom: true
Platform: false
Entries: 12
```

Nếu platform server đã có MBean độc lập cùng ObjectName, dòng Platform có thể là true. Điều cần xác nhận là exporter đang đăng ký vào **custom server được truyền qua setServer**.

## 7. XML configuration

Spring XML hỗ trợ MBeanServerFactoryBean và property server:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="managementMBeanServer"
          class="org.springframework.jmx.support.MBeanServerFactoryBean">
        <property name="defaultDomain" value="learning.management"/>
        <property name="locateExistingServerIfPossible" value="false"/>
    </bean>

    <bean id="cacheMonitor" class="example.jmx.CacheMonitor"/>

    <bean id="mbeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">

        <property name="server" ref="managementMBeanServer"/>

        <property name="beans">
            <map>
                <entry key="learning.jmx:type=CacheMonitor,name=Products"
                       value-ref="cacheMonitor"/>
            </map>
        </property>
    </bean>
</beans>
```

`ref="managementMBeanServer"` trỏ tới một Spring bean cung cấp MBeanServer. Nó không phải remote endpoint.

MBeanServerFactoryBean có các thuộc tính liên quan tìm hoặc tạo server. Trong môi trường nhiều server, cần cấu hình nhất quán để tránh vô tình dùng một registry khác dự kiến.

## 8. @EnableMBeanExport với thuộc tính server

Nếu sử dụng annotation-based JMX, Spring cho phép chọn MBeanServer bean qua tên:

```java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "managementMBeanServer")
public class AnnotationJmxConfiguration {

    @Bean(name = "managementMBeanServer")
    public MBeanServer managementMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "learning.management"
        );
    }

    @Bean
    public CacheManagement cacheManagement() {
        return new CacheManagement();
    }
}
```

Managed resource:

```java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=Products"
)
public class CacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 12;
    }
}
```

Thuộc tính `server` của `@EnableMBeanExport` nhận tên bean MBeanServer, không nhận hostname hoặc ObjectName. `@ManagedResource` xác định MBean và tên của nó; exporter được kích hoạt bởi annotation configuration.

Chỉ nên bật một exporter phù hợp cho cùng managed resource. Tạo thêm MBeanExporter thủ công có thể gây đăng ký trùng.

## 9. Khi không đặt server tường minh

MBeanExporter có cơ chế phát hiện MBeanServer phù hợp theo cấu hình và môi trường, nhưng chi tiết có thể phụ thuộc phiên bản Spring và những MBeanServers đang tồn tại.

Khi JVM có nhiều servers, không nên mặc định exporter đã chọn server bạn muốn. Dùng cấu hình tường minh:

```java
exporter.setServer(chosenServer);
```

Hoặc:

```java
@EnableMBeanExport(server = "chosenServerBean")
```

Hãy kiểm tra MBeanServer thực sự đang được exporter dùng, không chỉ kiểm tra một class được annotate.

## 10. MBeanServerFactory và MBeanServerFactoryBean

Java API:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("learning.management");
```

Spring FactoryBean:

```xml
<bean id="managementMBeanServer"
      class="org.springframework.jmx.support.MBeanServerFactoryBean"/>
```

Chúng cùng phục vụ việc cung cấp MBeanServer, nhưng vòng đời và lookup chịu ảnh hưởng cấu hình tương ứng.

Một JVM có thể tạo hai MBeanServers:

```java
MBeanServer a = MBeanServerFactory.createMBeanServer("learning.a");
MBeanServer b = MBeanServerFactory.createMBeanServer("learning.b");
```

Sau khi đăng ký MBean ở a:

```java
a.isRegistered(name); // true
b.isRegistered(name); // false
```

Các registry không đồng bộ với nhau.

## 11. JConsole và remote JMX connector

JConsole thường kết nối tới JVM hoặc một JMX connector cụ thể. Nó nhìn thấy registry được connector/local management kết nối đó cung cấp.

Nếu exporter dùng custom MBeanServer nhưng JConsole đang xem platform server, MBean custom có thể không xuất hiện. Điều này không chứng minh exporter thất bại.

Hãy so sánh:

```java
custom.isRegistered(name);
ManagementFactory.getPlatformMBeanServer().isRegistered(name);
```

Tạo MBeanServer không tự mở network endpoint. Nếu muốn JMX client từ xa truy cập custom server, cần một connector gắn với chính server đó.

Ví dụ khái niệm:

```java
JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        serviceUrl,
        connectorEnvironment,
        customServer
    );
```

Chương trình thực tế còn phải cấu hình serviceUrl, transport, authentication, TLS, firewall, quyền truy cập và shutdown lifecycle. Không mở JMX remote không bảo vệ trên mạng chia sẻ.

## 12. Nhiều Spring ApplicationContext

Một JVM có thể có nhiều Spring contexts:

```text
JVM
  +-- Parent context
  +-- Child context A
  +-- Child context B
```

Nếu hai exporters cùng đăng ký một ObjectName lên chung server, có thể xuất hiện InstanceAlreadyExistsException.

Hai hướng giải quyết:

**Chung một server:** dùng ObjectName phân biệt rõ module.

```text
learning.jmx:type=Cache,module=Billing,name=Primary
learning.jmx:type=Cache,module=Shipping,name=Primary
```

**Server riêng:** mỗi exporter trỏ tới MBeanServer tương ứng.

Server riêng tăng isolation nhưng cũng làm client cần biết registry/connector nào. Không dùng nhiều server chỉ để che một thiết kế ObjectName chưa rõ ràng.

## 13. RegistrationPolicy và ObjectName collision

Spring MBeanExporter có các chính sách:

| Chính sách | Hành vi |
|---|---|
| FAIL_ON_EXISTING | Báo lỗi khi ObjectName đã có |
| IGNORE_EXISTING | Bỏ qua đăng ký mới nếu tên đã tồn tại |
| REPLACE_EXISTING | Thay thế registration hiện có theo policy |

Ví dụ:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Trong môi trường nhiều modules, FAIL_ON_EXISTING giúp phát hiện hai thành phần đang sở hữu cùng tên.

Không dùng REPLACE_EXISTING bừa bãi: có thể làm mất registration của một context đang hoạt động. Khi gặp collision, trước hết xác định server nào, ObjectName nào, exporter nào và thành phần nào thực sự phải sở hữu registration.

## 14. Lifecycle export và unregister

Khi MBeanExporter được Spring quản lý, nó đăng ký MBeans khi context khởi tạo và cleanup những registrations thuộc phạm vi của nó khi context đóng.

```text
ApplicationContext refresh
    -> MBeanExporter initialization
    -> register MBean vào chosenServer
    -> ApplicationContext close
    -> MBeanExporter unregister MBean
```

MBeanServer có thể tiếp tục tồn tại sau khi MBean được unregister. Unexport không đồng nghĩa hủy toàn bộ server hoặc đóng JMX connector mà một thành phần khác đang quản lý.

Kiểm tra:

```java
boolean before = chosenServer.isRegistered(name);
context.close();
boolean after = chosenServer.isRegistered(name);
```

Nếu exporter có ownership và cleanup bình thường:

```text
before = true
after = false
```

Nếu ứng dụng đăng ký MBean thủ công ngoài exporter, chính code đó cần quản lý unregister.

### Giải phóng custom server

Khi bạn sở hữu server được tạo qua MBeanServerFactory và không còn consumer, có thể xem xét:

```java
MBeanServerFactory.releaseMBeanServer(chosenServer);
```

Không giải phóng platform MBeanServer hoặc shared server không thuộc quyền test/ứng dụng.

## 15. Integration test kiểm chứng target server

Ví dụ JUnit Jupiter:

```java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class CustomServerExportTest {

    @Test
    void registersIntoChosenServer() throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=CacheMonitor,name=Products"
        );

        MBeanServer platform =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    CustomJmxConfiguration.class)) {

            MBeanServer chosen = context.getBean(
                "managementMBeanServer", MBeanServer.class
            );

            assertTrue(chosen.isRegistered(name));
            assertEquals(
                12,
                chosen.getAttribute(name, "EntryCount")
            );

            // Yêu cầu test cô lập: không có registration
            // cùng tên trên platform server.
            assertFalse(platform.isRegistered(name));
        }
    }
}
```

Một bài test lifecycle:

```java
@Test
void unregistersAfterContextClose() throws Exception {
    AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(
            CustomJmxConfiguration.class
        );

    MBeanServer chosen = context.getBean(
        "managementMBeanServer", MBeanServer.class
    );

    ObjectName name = new ObjectName(
        "learning.jmx:type=CacheMonitor,name=Products"
    );

    try {
        assertTrue(chosen.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(chosen.isRegistered(name));
}
```

Cần chạy trong môi trường test phù hợp. Nếu nhiều tests chạy song song, không dùng một platform server và một ObjectName chung theo cách gây xung đột.

## 16. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| JConsole không thấy MBean | Đăng ký ở custom server, client xem platform server | Xác minh server identity và connector |
| InstanceNotFoundException | ObjectName hoặc server không đúng | Kiểm tra isRegistered trên từng server |
| InstanceAlreadyExistsException | Hai MBeans đăng ký cùng tên trong một server | Xác định ownership và policy |
| MBean đăng ký sai server | Thiếu setServer hoặc wiring sai | Cấu hình tường minh và @Qualifier |
| Có MBeanServer bean nhưng không được dùng | Chưa truyền server vào exporter | Dùng property server, setServer hoặc @EnableMBeanExport(server=...) |
| Không truy cập từ JVM khác | Không có connector tới custom server | Cấu hình remote connector và bảo mật |
| ObjectName hợp lệ nhưng operation không có | Assembler/metadata không export operation | Kiểm tra getMBeanInfo |
| Context đóng nhưng MBean còn | Registration do exporter khác hoặc code thủ công | Kiểm tra ownership và cleanup |
| Test ghi đè MBean khác | Shared server và REPLACE_EXISTING | Tách server hoặc đặt tên riêng |

## 17. Quy trình chẩn đoán

1. Xác định exporter và cấu hình server hiện tại.
2. Xác định MBeanServer bean thực tế, tránh nhầm khi có nhiều beans cùng kiểu.
3. Kiểm tra đúng ObjectName qua chosenServer.isRegistered(name).
4. Dùng chosenServer.queryNames(...) nếu cần khám phá những tên thực tế.
5. Dùng chosenServer.getMBeanInfo(name) để xem attributes/operations.
6. Nếu client không thấy MBean, xác định connector đang phục vụ server nào.
7. Khi có collision, kiểm tra tất cả exporters/contexts cùng đăng ký tên.
8. Khi context đóng, kiểm tra MBean của exporter được unregister.

## 18. Bài tập thực hành

**Bài 1 — Hai server:** Tạo A và B qua MBeanServerFactory. Đăng ký MBean vào A và chứng minh B không thấy ObjectName đó.

**Bài 2 — Thay target:** Đổi exporter.setServer từ platform server sang custom server, giữ nguyên ObjectName và so sánh isRegistered trên cả hai.

**Bài 3 — XML:** Viết MBeanExporter có property server trỏ tới managementMBeanServer. Giải thích vì sao ref không phải hostname.

**Bài 4 — Nhiều contexts:** Hai contexts muốn export CacheMonitor cùng tên. So sánh cách dùng ObjectNames phân biệt trong một server với cách dùng hai servers độc lập.

**Bài 5 — Cleanup:** Khởi tạo context, kiểm tra registration; đóng context, kiểm tra unregister; làm rõ việc giải phóng server nếu là tài nguyên riêng của test.

## 19. Ghi nhớ

- Thuộc tính **server** xác định MBeanServer mà MBeanExporter sử dụng.
- ObjectName chỉ xác định MBean trong registry đã chọn.
- Một JVM có thể chứa nhiều MBeanServers không chia sẻ registrations.
- Java configuration dùng setServer; XML dùng property server; @EnableMBeanExport có tham số server để chọn Spring bean cung cấp MBeanServer.
- MBeanServer bean reference khác với JMX connector URL.
- Server tùy biến không tự xuất hiện trong JConsole hoặc remote client nếu không có đường kết nối tương ứng.
- Chẩn đoán đúng thứ tự: exporter, server, ObjectName, MBeanInfo, connector và lifecycle.
- Với nhiều ApplicationContexts hoặc integration tests, lựa chọn server và ownership cần được thiết kế rõ ràng.

## Tài liệu tham khảo

- Spring Framework JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring MBeanExporter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring MBeanServerFactoryBean API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html
- Spring EnableMBeanExport API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE MBeanServerFactory: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
