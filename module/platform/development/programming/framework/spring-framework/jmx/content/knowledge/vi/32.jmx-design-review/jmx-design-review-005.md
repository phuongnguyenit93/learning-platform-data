# Xác minh exporter thực sự dùng đúng MBeanServer trong Spring Framework JMX

## 1. Mục tiêu và vấn đề thiết kế

Spring Framework JMX cho phép xuất các Spring-managed beans thành MBeans thông qua `MBeanExporter`. Khi có nhiều `MBeanServer` trong một JVM, trong application server, hoặc khi ứng dụng có dedicated server, việc exporter hoạt động **không tự chứng minh nó đã chọn đúng MBeanServer**. Một bean có thể được đăng ký thành công nhưng nằm ở registry khác với registry mà monitoring, JConsole hoặc `MBeanProxyFactoryBean` đang dùng.

Ví dụ: ứng dụng tạo một `MBeanServer` riêng để cô lập management API, nhưng exporter lại tự tìm platform server. Startup vẫn thành công, song client trỏ tới server riêng không thấy ObjectName. Trường hợp ngược lại, bean có thể vô tình bị expose ở server dùng chung hoặc remote management connector.

**Mục tiêu của bài:** kiểm chứng đường đi từ Spring bean, `MBeanExporter`, server reference, ObjectName đến registry thật. Không chỉ kiểm tra có khai báo `server` trong config, mà xác nhận cùng **instance MBeanServer** hoặc cùng connection được sử dụng ở cả phía export và phía quản trị.

## 2. MBeanServer là registry của JMX

Trong JMX, `MBeanServer` quản lý đăng ký MBeans theo `ObjectName`, hỗ trợ đọc/ghi attributes, gọi operations và quản lý notification listeners.

```text
Spring-managed object
        |
        v
    MBeanExporter
        |
        | register MBean by ObjectName
        v
    MBeanServer
        |
        +-- queryNames
        +-- getMBeanInfo
        +-- getAttribute
        +-- invoke
        +-- notification listener registration
        |
        v
JConsole / local client / remote JMX connector
```

Trong một MBeanServer, ObjectName là duy nhất. Hai MBeanServer khác nhau có thể có cùng một ObjectName nhưng trỏ tới hai đối tượng khác nhau. Vì thế **MBeanServer + ObjectName** là cặp quan trọng để xác định target thực sự.

```text
Server A:
  com.example.jobs:type=Queue,name=Main -> Queue A

Server B:
  com.example.jobs:type=Queue,name=Main -> Queue B
```

Truy vấn thành công trên server A không có nghĩa server B chứa cùng MBean.

## 3. Những kiểu MBeanServer thường gặp

| Loại server | Cách có thể xuất hiện | Vấn đề cần lưu ý |
| --- | --- | --- |
| Platform MBeanServer | `ManagementFactory.getPlatformMBeanServer()` | Thường chứa JVM MBeans như `java.lang:type=Memory` |
| Server mới do JMX tạo | `MBeanServerFactory.createMBeanServer(...)` | Là một registry khác, có default domain riêng |
| Server từ application container | App server hoặc runtime cung cấp | Có thể dùng chung giữa nhiều ứng dụng |
| Server do Spring factory tìm hoặc tạo | `MBeanServerFactoryBean` | Phụ thuộc lựa chọn locate/create và cấu hình |
| Remote connection | `JMXConnector.getMBeanServerConnection()` | Là client view tới server đích; khác với local `MBeanServer` object |

Trong một JVM có thể có nhiều local `MBeanServer` độc lập. Một `MBeanServerConnection` cho phép thao tác quản trị nhưng không nhất thiết là `MBeanServer` local; khi xác minh, phân biệt **identity của local server object** với **server endpoint thông qua connector**.

## 4. MBeanExporter chọn server như thế nào?

`MBeanExporter` có cấu hình `server` kiểu `MBeanServer`. Khi không được cấp một server rõ ràng, hạ tầng Spring có cơ chế tìm MBeanServer phù hợp, tùy cấu hình và môi trường. Không nên suy luận rằng exporter **luôn** chọn platform MBeanServer, server đầu tiên hay server vừa được tạo chỉ vì có một bean `MBeanServer` trong context.

Ví dụ cấu hình explicit:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import javax.management.MBeanServer;

@Configuration
public class ExporterConfig {
    @Bean
    public MBeanExporter exporter(
            MBeanServer managementMBeanServer,
            QueueManagement management) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(managementMBeanServer);
        exporter.addExcludedBean("internalDebugBean");
        exporter.setBeans(java.util.Map.of(
            "com.example.jobs:type=Queue,name=Main", management
        ));
        return exporter;
    }
}
```

Trong đoạn minh họa, `setServer(managementMBeanServer)` là bước ràng buộc rõ ràng. `addExcludedBean` chỉ là ví dụ một lựa chọn liên quan autodetection; không quyết định server được chọn. Điều quan trọng là bean MBeanServer được inject phải chính là server mục tiêu mà vận hành dự kiến sử dụng.

## 5. Chuẩn bị MBean đơn giản để xác minh

Ví dụ Standard MBean:

```java
package com.example.management;

public interface QueueManagementMBean {
    int getQueueDepth();
}
```

```java
package com.example.management;

public class QueueManagement implements QueueManagementMBean {
    @Override
    public int getQueueDepth() {
        return 7;
    }
}
```

Đăng ký bằng `MBeanExporter` với ObjectName xác định:

```java
@Bean
public QueueManagement queueManagement() {
    return new QueueManagement();
}

@Bean
public MBeanExporter queueExporter(
        MBeanServer managementServer,
        QueueManagement queueManagement) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(managementServer);
    exporter.setBeans(java.util.Map.of(
        "com.example.jobs:type=Queue,name=Main",
        queueManagement
    ));
    return exporter;
}
```

Không đăng ký cùng object bằng hai exporter hoặc vừa JMX API thủ công vừa Spring exporter. Ví dụ dùng một exporter làm owner duy nhất của ObjectName.

## 6. Dùng platform MBeanServer rõ ràng

Nếu muốn export vào platform MBeanServer, khai báo nhất quán:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer managementServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
```

Khi đó cả exporter và client local đều nên inject bean `managementServer` thay vì mỗi phần tự tìm một server khác nhau. `ManagementFactory.getPlatformMBeanServer()` trả platform server của JVM hiện tại, phù hợp cho nhiều bài toán giám sát JVM cùng MBeans ứng dụng.

Nhưng application server có thể có chính sách đăng ký MBeans khác; cần xem quản lý connector và nơi các công cụ đang kết nối. Không nên tự động tạo một MBeanServer mới nếu chỉ muốn đọc JVM metrics.

## 7. Khi thực sự cần dedicated MBeanServer

Ví dụ tạo server riêng:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer dedicatedManagementServer() {
    return MBeanServerFactory.createMBeanServer(
        "com.example.management"
    );
}
```

Đây là một registry độc lập. Nó có thể không xuất hiện trong một JConsole connection mặc định trỏ tới platform server; cần cấu hình monitoring/client/connector đúng server. Việc tạo server mới không tự động làm cho nó có remote port hoặc TLS/authentication.

Nếu nhiều bean `MBeanServer` cùng tồn tại trong context, injection theo type có thể mơ hồ. Hãy dùng tên/`@Qualifier` cụ thể:

```java
@Bean
public MBeanExporter queueExporter(
        @Qualifier("dedicatedManagementServer") MBeanServer server,
        QueueManagement queueManagement) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(java.util.Map.of(
        "com.example.jobs:type=Queue,name=Main", queueManagement
    ));
    return exporter;
}
```

Đảm bảo import `org.springframework.beans.factory.annotation.Qualifier`. Việc dùng `@Qualifier` chỉ chọn bean Spring; xác minh runtime vẫn cần để phát hiện các exporter hoặc connector khác có cấu hình riêng.

## 8. Kiểm tra đăng ký trên đúng server

Cách cơ bản nhất là kiểm tra `isRegistered` trên **server mà exporter được kỳ vọng sử dụng**:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.jobs:type=Queue,name=Main"
);

boolean present = managementServer.isRegistered(name);
System.out.println("Present in expected server: " + present);
```

Nếu `present == true`, server đó đang có một MBean ở ObjectName. Tuy nhiên điều này **chưa đủ** chứng minh rằng chính exporter của ứng dụng vừa đăng ký MBean đó: server có thể chứa MBean cũ hoặc một component khác đã đăng ký cùng tên. Cần thêm kiểm tra MBeanInfo, dấu hiệu owner và lifecycle khi có nguy cơ trùng.

Đọc metadata an toàn:

```java
import javax.management.MBeanInfo;

MBeanInfo info = managementServer.getMBeanInfo(name);
System.out.println("MBean class: " + info.getClassName());
for (var attr : info.getAttributes()) {
    System.out.println(
        "Attribute " + attr.getName() + ": " + attr.getType()
    );
}
```

Không nên dump toàn bộ attribute values để kiểm chứng server: getter có thể có side effect, chi phí lớn hoặc lộ secrets. Metadata và identity đã biết của target thường đủ cho bước đầu.

## 9. Đối chiếu hai server bằng một ObjectName

Ví dụ một ứng dụng có `platform` và `dedicated`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer dedicated = dedicatedManagementServer;

ObjectName expectedName = new ObjectName(
    "com.example.jobs:type=Queue,name=Main"
);

System.out.println(
    "platform registered=" + platform.isRegistered(expectedName)
);
System.out.println(
    "dedicated registered=" + dedicated.isRegistered(expectedName)
);
```

Các kết quả có thể là:

| Platform | Dedicated | Diễn giải khả dĩ |
| --- | --- | --- |
| `true` | `false` | Exporter có thể dùng platform hoặc một component khác đã đăng ký ở đó |
| `false` | `true` | Exporter có thể dùng dedicated như mong đợi |
| `true` | `true` | Hai registry đều có một MBean cùng tên; cần đối chiếu owner/metadata |
| `false` | `false` | MBean chưa đăng ký, tên sai, exporter lỗi hoặc thực tế ở server thứ ba |

Không kết luận chỉ dựa vào các cờ boolean khi có nhiều exporters. Cần biết exporter nào sở hữu tên, metadata của MBean và đường lifecycle.

## 10. `queryNames` giúp phát hiện domain hoặc key bị khác

Nếu exact ObjectName không tồn tại, có thể query tập tên theo domain:

```java
import java.util.Set;
import javax.management.ObjectName;

Set<ObjectName> names = managementServer.queryNames(
    new ObjectName("com.example.jobs:*") ,
    null
);

names.stream()
    .map(ObjectName::getCanonicalName)
    .sorted()
    .forEach(System.out::println);
```

Cách này cho biết MBean có thực sự nằm trong domain nhưng khác `type`, `name` hoặc `instance`. `getCanonicalName()` chuẩn hóa thứ tự key properties; hai chuỗi `type=Queue,name=Main` và `name=Main,type=Queue` có cùng danh tính.

Nếu không thấy gì, cần xem exporter có dùng naming strategy khác, annotation ObjectName khác, MBeanServer khác hoặc profile tạo bean khác không. Không tự thay đổi `RegistrationPolicy` để giải quyết lỗi thiếu tên.

## 11. Kiểm chứng bằng Spring integration test

Trong test, tạo **hai server riêng** và ràng buộc exporter vào server được chọn. Điều quan trọng là kiểm tra **positive** ở server mục tiêu và **negative** ở server còn lại.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ExporterServerSelectionTest {
    @Test
    void registersOnlyInChosenServer() throws Exception {
        MBeanServer chosen =
            MBeanServerFactory.createMBeanServer("example-test");
        MBeanServer other =
            MBeanServerFactory.createMBeanServer("example-other");

        ObjectName name = new ObjectName(
            "com.example.test:type=Queue,name=Main"
        );

        try {
            // Khởi tạo Spring context với exporter.setServer(chosen)
            // và bean QueueManagement đã export vào chosen.
            assertTrue(chosen.isRegistered(name));
            assertFalse(other.isRegistered(name));
        } finally {
            // Đóng Spring context trước khi release server.
            MBeanServerFactory.releaseMBeanServer(chosen);
            MBeanServerFactory.releaseMBeanServer(other);
        }
    }
}
```

Đây là **khung test minh họa**; phần khởi tạo Spring context phải được hiện thực để assertions chạy có ý nghĩa. Không coi hai assert trên là test hoàn chỉnh khi chưa có exporter thực sự đăng ký MBean. Ở môi trường test chạy song song, dedicated MBeanServer giúp tránh collision với server production/JVM MBeans.

## 12. Integration test hoàn chỉnh với AnnotationConfigApplicationContext

Ví dụ cụ thể hơn sử dụng một config local và server đã biết:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

class ExactMBeanServerTest {
    @Configuration
    static class Config {
        @Bean
        MBeanServer testServer() {
            return MBeanServerFactory.createMBeanServer("test-domain");
        }

        @Bean
        QueueManagement queueManagement() {
            return new QueueManagement();
        }

        @Bean
        MBeanExporter exporter(
                MBeanServer testServer, QueueManagement target) {
            MBeanExporter exporter = new MBeanExporter();
            exporter.setServer(testServer);
            exporter.setBeans(Map.of(
                "com.example.test:type=Queue,name=Main", target
            ));
            return exporter;
        }
    }

    @Test
    void exporterUsesConfiguredServer() throws Exception {
        MBeanServer chosen;
        ObjectName name = new ObjectName(
            "com.example.test:type=Queue,name=Main"
        );

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            chosen = context.getBean(MBeanServer.class);
            assertTrue(chosen.isRegistered(name));
            assertFalse(
                java.lang.management.ManagementFactory
                    .getPlatformMBeanServer().isRegistered(name)
            );
            assertEquals(
                7, chosen.getAttribute(name, "QueueDepth")
            );
        }
        // Test có thể cần release dedicated server sau khi context đóng.
    }
}
```

`QueueManagement` phải implement `QueueManagementMBean` như ở ví dụ trước. Test kiểm chứng server đăng ký được chọn và server platform không bị xuất cùng MBean đó; nếu có test khác cùng lúc đăng ký trùng trên platform, cần cô lập môi trường tốt hơn. Với `MBeanServerFactory.createMBeanServer`, quản lý release server sau context close để tránh registry references kéo dài trong test suite.

## 13. Kiểm tra client proxy dùng cùng server

Spring `MBeanProxyFactoryBean` cũng cần dùng đúng server/connection. Nếu exporter dùng dedicated server nhưng proxy local lại dùng platform MBeanServer, proxy không tìm thấy MBean.

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Bean
public MBeanProxyFactoryBean queueProxy(
        @Qualifier("dedicatedManagementServer") MBeanServer server)
        throws Exception {
    MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
    proxy.setServer(server);
    proxy.setObjectName(new ObjectName(
        "com.example.jobs:type=Queue,name=Main"
    ));
    proxy.setProxyInterface(QueueManagementMBean.class);
    return proxy;
}
```

Proxy định tuyến theo cặp **server + ObjectName**, còn interface phải khớp MBeanInfo thực tế. Không suy luận rằng chỉ cùng ObjectName thì proxy và exporter đang dùng cùng server.

## 14. Application server và nhiều ApplicationContext

Một JVM có thể chạy nhiều ứng dụng/WAR hoặc nhiều Spring contexts. Trường hợp có shared MBeanServer:

```text
ApplicationContext A -> Exporter A ---+
                                    +--> Shared MBeanServer
ApplicationContext B -> Exporter B ---+
```

Xung đột có thể xảy ra nếu hai exporter chọn cùng ObjectName. Đồng thời, nếu một context vô tình dùng platform server thay vì dedicated server dự kiến, MBeans có thể xuất hiện ở registry dùng chung mà operator không mong muốn.

Khi đánh giá thiết kế:

- Xác định rõ owner của từng MBeanServer.
- Xác định context nào tạo server, context nào chỉ dùng server.
- Không để nhiều exporter tự động tìm server theo mặc định nếu yêu cầu là cô lập.
- Dùng qualifier hoặc explicit references thay vì bean injection mơ hồ.
- Kiểm tra cleanup khi context đóng và redeploy.
- Không tự `unregisterMBean` các tên do module khác sở hữu.

Việc đổi ObjectName để tránh trùng không thay thế việc đảm bảo exporter chọn đúng server.

## 15. Các nguồn nhầm lẫn khi dùng Spring Boot

Trong Spring Boot, có thể có custom Spring Framework MBeans và Actuator JMX endpoints đồng thời. Actuator có cấu hình JMX exposure riêng; điều này không đồng nghĩa custom `MBeanExporter` sẽ dùng chính xác server mà bạn kỳ vọng nếu không explicit config.

Ví dụ cấu hình:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
```

Property này điều khiển Actuator exposure tương ứng, **không phải lệnh chọn MBeanServer cho mọi custom MBeanExporter**. Trong ứng dụng có custom exporters, xác minh từng exporter/server riêng.

Không nhầm cổng HTTP management (`management.server.port`) với remote JMX connector. Đây là các giao diện quản trị khác nhau; ObjectName chỉ định MBean trong một server, không chứa thông tin host/port.

## 16. ObjectName chưa đủ để xác định đúng instance

Ngay cả khi `isRegistered` trả true trên server kỳ vọng, vẫn có thể đã có **một MBean khác** chiếm tên đó. Ví dụ khi dùng `RegistrationPolicy.IGNORE_EXISTING`, exporter mới có thể bỏ qua đăng ký, còn query tiếp tục thấy MBean cũ.

Ba giá trị policy thường gặp:

```java
RegistrationPolicy.FAIL_ON_EXISTING
RegistrationPolicy.IGNORE_EXISTING
RegistrationPolicy.REPLACE_EXISTING
```

`FAIL_ON_EXISTING` giúp phát hiện collision; `IGNORE_EXISTING` không bảo đảm bean mới được export; `REPLACE_EXISTING` có thể thay MBean của ứng dụng khác. Để xác minh owner, dùng deployment metadata không nhạy cảm hoặc test lifecycle với server cô lập.

Không dùng `REPLACE_EXISTING` chỉ để khiến `isRegistered` trở thành true. Điều cần kiểm chứng là đúng **MBean instance, đúng server và đúng owner**.

## 17. Lifecycle và negative assertion

Integration test tốt cần kiểm tra:

1. Trước khi context xuất MBean, server đích chưa có tên dự kiến (test cô lập).
2. Sau khi context startup, server đích có ObjectName.
3. Một server ngoài phạm vi không có ObjectName đó.
4. MBeanInfo đúng thuộc tính/operation dự kiến.
5. Sau khi đóng context, MBean do exporter sở hữu được unregister.

Ví dụ:

```java
ObjectName target = new ObjectName(
    "com.example.test:type=Queue,name=Main"
);

assertTrue(chosen.isRegistered(target));
assertFalse(other.isRegistered(target));

context.close();
assertFalse(chosen.isRegistered(target));
```

Không chạy cleanup bằng cách unregister tất cả tên trong domain, vì có thể xóa MBean không thuộc context test. Chỉ đóng context/owner đã tạo registration và release server do test tạo.

## 18. Cảnh báo về remote JMX

Nếu client truy cập remote, `MBeanServerConnection` được lấy từ `JMXConnector`:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
    MBeanServerConnection connection =
        connector.getMBeanServerConnection();
    System.out.println(connection.getDefaultDomain());
}
```

Địa chỉ chỉ là ví dụ minh họa, không phải cấu hình connector an toàn hoặc bảo đảm có server chạy ở cổng đó. Remote connector yêu cầu network/authentication/authorization/TLS tùy môi trường; không mở remote JMX unauthenticated để debug.

Để xác minh client đang dùng đúng server, có thể so danh sách MBeans dự kiến, server identity metadata hoặc các thuộc tính quản trị an toàn. `getDefaultDomain()` chỉ là dấu hiệu hỗ trợ, **không chứng minh duy nhất server identity** vì nhiều server có thể dùng cùng default domain.

## 19. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân có thể | Xử lý |
| --- | --- | --- |
| Exporter startup OK nhưng client không tìm thấy MBean | Exporter và client khác server | So `isRegistered` trên từng server có liên quan |
| JConsole thấy MBean, code local không thấy | JConsole kết nối JVM/server khác hoặc ObjectName sai | Đối chiếu connection/server/ID, canonical name |
| MBean xuất hiện trên platform nhưng không trên dedicated server | Exporter dùng sai server | Inject explicit server bằng `setServer` |
| Hai server đều có cùng ObjectName | Hai registrations độc lập | Đối chiếu metadata/owner, không tự xóa |
| MBeanInfo khác mong đợi | MBean cũ, exporter khác hoặc assembler khác | Kiểm tra registration owner, profile, MBeanInfo |
| `InstanceAlreadyExistsException` | Hai exporter cùng tên trên cùng server | Sửa ownership/naming, không replace mù |
| `isRegistered` false sau redeploy | Exporter chưa register, unregister sớm hoặc server đổi | Kiểm tra lifecycle/startup logs |
| Proxy local nhận InstanceNotFoundException | Proxy dùng server/ObjectName khác | So cặp server + name |
| Remote JMX timeout | Connector/network/security, không hẳn exporter | Kiểm tra connection path và policies |
| Test qua JConsole PASS nhưng production monitoring FAIL | Hai công cụ kết nối server/connector khác | Test trên đúng endpoint monitoring dùng |

## 20. Checklist đánh giá thiết kế

- [ ] MBeanServer mục tiêu được định nghĩa và sở hữu rõ ràng.
- [ ] Exporter nhận `MBeanServer` explicit, không phụ thuộc lookup mơ hồ khi hệ thống có nhiều server.
- [ ] Nếu có nhiều MBeanServer beans, injection dùng `@Qualifier` hoặc cách xác định tương đương.
- [ ] MBeanServer trong test là server thực sự truyền vào `MBeanExporter.setServer`.
- [ ] `isRegistered` PASS trên server được chọn.
- [ ] Negative assertion xác nhận tên không xuất hiện ở server ngoài phạm vi.
- [ ] `MBeanInfo` khớp contract quản trị dự kiến.
- [ ] Không có MBean cũ chiếm tên do `IGNORE_EXISTING` hoặc stale registration.
- [ ] JMX proxy/monitoring kết nối đúng server/connector.
- [ ] Cleanup/unregister hoạt động khi context shutdown.
- [ ] Không truy vấn raw attributes nhạy cảm để debug.
- [ ] Remote JMX được bảo vệ bằng authentication, authorization và transport/network policy.

## 21. Mô hình tư duy

```text
Spring bean
    |
    v
MBeanExporter
    |
    +-- setServer(expectedServer)
    +-- ObjectNamingStrategy / ObjectName
    +-- MBeanInfoAssembler
    |
    v
Expected MBeanServer <--- isRegistered / getMBeanInfo
    |
    +-- assert MBean present
    |
Other MBeanServer <--- negative assertion
    |
    +-- assert MBean absent
    |
    v
Correct JMX client connection
```

**Kết luận:** xác minh `MBeanExporter` thực sự dùng đúng MBeanServer phải dựa trên **runtime registration và server identity**, không chỉ cấu hình trông hợp lý. Cách đáng tin là cấu hình `setServer` tường minh, kiểm tra ObjectName trên server đích, kiểm tra vắng mặt ở server khác, đối chiếu MBeanInfo/owner và xác nhận unregister khi context đóng. Cuối cùng, bảo đảm JMX proxy và monitoring kết nối tới chính registry đó; ObjectName đúng nhưng server sai vẫn là một thiết kế quản trị không đúng.
