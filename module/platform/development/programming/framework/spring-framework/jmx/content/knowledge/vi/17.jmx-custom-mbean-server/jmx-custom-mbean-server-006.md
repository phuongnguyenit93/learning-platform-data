# Domain riêng và tránh trộn MBean không cùng ứng dụng trong Spring JMX

## Mục tiêu

Sau bài này, bạn có thể thiết kế namespace JMX cho ứng dụng Spring, phân biệt **JMX domain** với **MBeanServer riêng**, quyết định khi nào cần sử dụng platform MBeanServer và khi nào cần một MBeanServer tùy biến, cấu hình `MBeanExporter` đăng ký đúng server, đồng thời kiểm tra việc phân tách các MBean của nhiều ứng dụng hoặc module để tránh xung đột tên và nhầm lẫn vận hành.

## 1. Vấn đề khi nhiều ứng dụng dùng chung hệ thống JMX

Một JVM có thể có nhiều Spring `ApplicationContext`, nhiều thư viện và nhiều module tự xuất MBean. Những đối tượng này thường được đăng ký vào một `MBeanServer`.

Ví dụ:

```text
JVM
  |
  +-- ApplicationContext: billing
  |     +-- BillingQueueMonitor
  |     +-- BillingCacheMonitor
  |
  +-- ApplicationContext: inventory
  |     +-- InventoryQueueMonitor
  |     +-- InventoryCacheMonitor
  |
  +-- JVM built-in management MBeans
        +-- java.lang:type=Memory
        +-- java.lang:type=Threading
```

Nếu mọi module tùy tiện sử dụng tên như `app:type=Queue,name=Main`, có thể phát sinh hai nhóm rủi ro:

1. **Xung đột kỹ thuật:** hai MBean cố dùng một ObjectName trong cùng MBeanServer, gây `InstanceAlreadyExistsException` hoặc kích hoạt một registration policy khác.
2. **Nhầm lẫn vận hành:** client hoặc script không biết MBean thuộc ứng dụng nào, dẫn đến đọc sai metrics hoặc gọi operation lên sai đối tượng.

Bài toán “tránh trộn” không chỉ là tránh lỗi startup mà còn là thiết kế **ranh giới định danh, quyền sở hữu và quan sát**.

## 2. JMX domain là gì?

Một `javax.management.ObjectName` có cấu trúc:

```text
domain:key=value[,key=value...]
```

Ví dụ:

```text
com.example.billing:type=Queue,name=Payment
com.example.inventory:type=Queue,name=StockSync
java.lang:type=Memory
```

Domain là phần trước dấu `:`. Nó đóng vai trò namespace cho MBean.

Trong ví dụ trên:

| ObjectName | Domain | Tài nguyên |
| --- | --- | --- |
| `com.example.billing:type=Queue,name=Payment` | `com.example.billing` | Payment queue |
| `com.example.inventory:type=Queue,name=StockSync` | `com.example.inventory` | Stock synchronization queue |
| `java.lang:type=Memory` | `java.lang` | JVM memory |

Một domain riêng giúp client:

- Nhóm các MBean cùng ứng dụng hoặc module.
- Query MBean chính xác bằng `ObjectName` pattern.
- Giảm nguy cơ hai module chọn tên giống nhau.
- Dễ lập dashboard, script và monitoring rule theo namespace.
- Phân biệt MBean ứng dụng với MBean chuẩn của JVM và các thư viện.

**Domain không phải một vùng chứa riêng biệt về bảo mật.** Hai domain khác nhau vẫn có thể thuộc cùng MBeanServer và được truy cập qua cùng một JMX connection nếu client có quyền.

## 3. Domain riêng khác MBeanServer riêng như thế nào?

Đây là khác biệt quan trọng nhất.

### Domain riêng trong cùng một MBeanServer

```text
Platform MBeanServer
  |
  +-- java.lang:type=Memory
  +-- com.example.billing:type=Queue,name=Payment
  +-- com.example.inventory:type=Queue,name=StockSync
```

Các ObjectName có domain khác nhau nhưng cùng tồn tại trên một server.

Lợi ích:

- Dễ quan sát toàn bộ JVM qua cùng một kết nối JMX.
- Không cần thêm MBeanServer hoặc connector.
- Các tool quen thuộc như JConsole/JMC thường có thể xem MBean ứng dụng khi chúng dùng platform MBeanServer.
- Dễ nhóm theo domain.

Giới hạn:

- Các client có quyền truy cập toàn server vẫn có thể thấy MBean nhiều ứng dụng.
- Tên trong cùng server phải duy nhất.
- Domain không bảo đảm rằng một module không thể truy vấn hoặc gọi MBean của module khác.

### MBeanServer riêng

```text
JVM
  |
  +-- Platform MBeanServer
  |     +-- java.lang:*
  |
  +-- Billing MBeanServer
  |     +-- com.example.billing:*
  |
  +-- Inventory MBeanServer
        +-- com.example.inventory:*
```

MBeanServer riêng tạo một registry JMX độc lập. Cùng ObjectName có thể xuất hiện trong hai server khác nhau mà không xung đột vì uniqueness được kiểm tra **trong từng server**.

Lợi ích:

- Tách biệt namespace đăng ký ở mức server.
- Kiểm soát vòng đời registry theo module/context.
- Có thể xây dựng connector/access policy riêng khi thiết kế hạ tầng phù hợp.

Giới hạn:

- JConsole/JMC kết nối tới platform MBeanServer không nhất thiết tự thấy MBean trong server riêng.
- Phải quản lý chính xác server mà exporter và client đang sử dụng.
- Việc tạo nhiều server/connector làm tăng phức tạp vận hành.
- Tách server không tự động tạo bảo mật: quyền truy cập phụ thuộc connector, authentication, authorization và network configuration.

**Quy tắc:** domain riêng là cách tổ chức tên trong một registry; MBeanServer riêng là cách tách registry. Không nên nhầm hai khái niệm.

## 4. Nên chọn domain thế nào?

Một naming convention đơn giản:

```text
<organization>.<application>[.<module>]:type=<type>,name=<logical-name>
```

Ví dụ:

```text
com.acme.billing:type=Cache,name=TaxRate
com.acme.billing:type=Queue,name=Invoices
com.acme.inventory:type=Queue,name=Replenishment
com.acme.inventory:type=WorkerPool,name=StockSync
```

Hướng dẫn:

- Sử dụng namespace có tính sở hữu rõ, chẳng hạn reverse-DNS của tổ chức.
- Đưa tên ứng dụng/module vào domain khi cần tách.
- Dùng `type` để phân loại resource; `name` để xác định tài nguyên logic.
- Nếu một JVM có nhiều instance của cùng module, bổ sung key property ổn định và có nghĩa.
- Không đưa PID, UUID sinh lại mỗi lần chạy hoặc thời điểm khởi động vào ObjectName của resource logic ổn định.
- Không sử dụng domain của JVM như `java.lang` để đặt MBean ứng dụng tùy ý.
- Không dựa vào domain như cơ chế ẩn tài nguyên hoặc cấp quyền.

Tên `com.acme.billing:type=Queue,name=Invoices` nên tiếp tục mang cùng ý nghĩa qua các lần restart, ngay cả khi class implementation đổi.

## 5. ObjectName và sự duy nhất trong cùng server

Hai ObjectName sau khác domain nên không xung đột:

```text
com.acme.billing:type=Queue,name=Main
com.acme.inventory:type=Queue,name=Main
```

Nhưng hai chuỗi sau biểu diễn cùng tên:

```text
com.acme.billing:type=Queue,name=Main
com.acme.billing:name=Main,type=Queue
```

Thứ tự key properties không tạo một danh tính mới.

```java
import javax.management.ObjectName;

ObjectName first = new ObjectName(
    "com.acme.billing:type=Queue,name=Main"
);
ObjectName second = new ObjectName(
    "com.acme.billing:name=Main,type=Queue"
);

System.out.println(first.equals(second)); // true
```

Vì vậy, việc đánh giá xung đột không nên chỉ so sánh chuỗi raw. Dùng `ObjectName.equals()` hoặc `getCanonicalName()` khi cần kiểm tra tên.

Trong cùng server, `MBeanServer.registerMBean` có thể ném `InstanceAlreadyExistsException` khi cố đăng ký trùng. Domain riêng giảm khả năng xung đột nhưng không thay thế việc kiểm soát toàn bộ tên.

## 6. Thiết kế với platform MBeanServer

Trong nhiều ứng dụng Spring chạy một JVM, sử dụng **platform MBeanServer** với domain riêng cho từng module là lựa chọn đơn giản nhất.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer platform =
        ManagementFactory.getPlatformMBeanServer();
```

Với cấu hình này, các MBean chuẩn của JVM và MBean ứng dụng cùng được đăng ký trong một server; client quan sát JVM có thể truy cập theo các domain tương ứng.

### Ví dụ Standard MBean

```java
package com.example.billing.jmx;

public interface BillingQueueMonitorMBean {
    int getPendingJobs();
}
```

```java
package com.example.billing.jmx;

public final class BillingQueueMonitor
        implements BillingQueueMonitorMBean {

    @Override
    public int getPendingJobs() {
        return 12;
    }
}
```

Đăng ký dưới domain của billing:

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.billing:type=Queue,name=Invoices"
);

platform.registerMBean(new BillingQueueMonitor(), name);
```

Việc đăng ký trực tiếp ở ví dụ trên chỉ nhằm minh họa. Trong ứng dụng Spring, nên để `MBeanExporter` quản lý lifecycle để tránh đăng ký/hủy đăng ký rải rác trong code.

## 7. Cấu hình Spring MBeanExporter với domain riêng

Cấu hình Java-based:

```java
package com.example.billing.config;

import com.example.billing.jmx.BillingQueueMonitor;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class BillingJmxConfiguration {

    @Bean
    public BillingQueueMonitor billingQueueMonitor() {
        return new BillingQueueMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter billingExporter(
            BillingQueueMonitor monitor,
            MBeanServer platformMBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.billing:type=Queue,name=Invoices",
            monitor
        ));
        return exporter;
    }
}
```

Ở đây, domain `com.example.billing` là phần của ObjectName trong map `beans`. `setServer` chọn registry đích. Hai quyết định này độc lập: bạn có thể đổi domain mà vẫn dùng cùng server, hoặc dùng cùng domain trên hai server khác nhau.

Nếu còn một `MBeanExporter` khác đang tự động phát hiện cùng bean, cần loại bỏ cấu hình trùng hoặc xác định ownership rõ ràng.

## 8. Cấu hình một MBeanServer tùy biến

Khi có lý do chính đáng để tách registry, Spring hỗ trợ kết nối exporter với một MBeanServer do ứng dụng tạo.

Ví dụ Spring Java configuration:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IsolatedJmxServerConfiguration {

    @Bean
    public MBeanServer billingMBeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "com.example.billing.management"
        );
    }
}
```

`newMBeanServer` tạo một server mới không nằm trong danh sách do `MBeanServerFactory.findMBeanServer` quản lý. Đối với ứng dụng cần cho cơ chế phát hiện server của JMX tìm thấy server, có thể cân nhắc `createMBeanServer` và quản lý vòng đời/release phù hợp. Dù chọn cách nào, client phải biết chính xác endpoint nào phục vụ registry này.

Exporter gắn vào server riêng:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
public MBeanExporter billingExporter(
        BillingQueueMonitor monitor,
        @Qualifier("billingMBeanServer") MBeanServer server) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
        "com.example.billing:type=Queue,name=Invoices",
        monitor
    ));
    return exporter;
}
```

**Quan trọng:** tạo server riêng không tự tạo remote JMX connector. Nếu cần client từ xa, phải xuất bản endpoint quản lý phù hợp và thiết lập bảo mật cho connector; JConsole/JMC kết nối JVM mặc định không đảm bảo thấy server mới.

## 9. Phân tách domain không phải phân tách bảo mật

Một hiểu lầm phổ biến:

> Nếu billing MBean thuộc `com.example.billing` còn inventory MBean thuộc `com.example.inventory`, client billing sẽ không gọi được inventory MBean.

Điều đó **không đúng** nếu cả hai ở cùng MBeanServer và client có quyền toàn server. Domain là cấu trúc tên, không phải access-control list.

Để đạt ranh giới bảo mật, cần thiết kế:

- Authentication khi kết nối JMX, đặc biệt qua remote connector.
- Authorization cho thao tác đọc/ghi/call operation theo quyền phù hợp.
- Network restriction, TLS và quản lý secret đúng chính sách.
- MBean interface nhỏ, chỉ công bố trạng thái và operations cần thiết.
- Kết nối tới đúng MBeanServer/connector, nếu triển khai nhiều server.
- Audit đối với các operation có side effect.

Cũng không nên cho rằng một server riêng đã có isolation tương đương process hoặc classloader: các object trong cùng JVM vẫn chia sẻ tài nguyên tiến trình và chịu ảnh hưởng của các quyết định code/bảo mật khác.

## 10. Khi nào nên tách thành nhiều MBeanServer?

Có thể cân nhắc server riêng nếu:

1. Một JVM nhúng nhiều ứng dụng độc lập và cần registry lifecycle khác nhau.
2. Có hệ thống plugin/multi-tenant trong một tiến trình với cơ chế quản lý rõ ràng.
3. Một subsystem cần chủ động phát hành registry qua connector riêng.
4. Cần cô lập tên đăng ký hoặc tránh việc module của ứng dụng phụ thuộc vào registry global.
5. Các framework có server registry riêng theo kiến trúc đã xác lập.

Nhưng **không nên** tạo server riêng chỉ vì muốn màn hình MBean Browser bớt nhiều mục. Domain đúng và naming convention tốt thường đủ.

Một server riêng làm tăng chi phí cấu hình, phát hiện, connector, giám sát và kiểm thử. Với Spring Boot hoặc Spring Framework thông thường, platform MBeanServer + domain riêng là mô hình dễ vận hành.

## 11. Domain riêng và cấu hình annotation-driven export

Nếu dự án dùng `@ManagedResource`:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.billing:type=Queue,name=Invoices",
    description = "Billing invoice queue monitor"
)
public class AnnotatedBillingMonitor {

    @ManagedAttribute
    public int getPendingJobs() {
        return 12;
    }
}
```

và bật exporter với:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxAnnotationConfiguration {
}
```

Annotation có thể chỉ rõ ObjectName, bao gồm domain và key property. Tuy nhiên, **việc đăng ký** vẫn phụ thuộc exporter và MBeanServer mà exporter dùng.

Các ứng dụng có nhiều context/beans cần thống nhất quy ước để không sinh hai MBean cùng ObjectName trong cùng server. Chỉ một `@ManagedResource` trên class cũng không đảm bảo tên duy nhất nếu nhiều instance cùng dùng metadata tên cố định.

Với nhiều instance, có thể sử dụng naming strategy hoặc các adapter quản trị riêng để tạo tên có giá trị logic khác nhau.

## 12. Kiểm tra domain bằng queryNames

`MBeanServer` hỗ trợ truy vấn `ObjectName` pattern.

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> billing = server.queryNames(
    new ObjectName("com.example.billing:*"), null
);

for (ObjectName name : billing) {
    System.out.println(name.getCanonicalName());
}
```

Pattern `com.example.billing:*` chỉ match MBean có domain `com.example.billing`. Nếu bạn dùng các domain con như `com.example.billing.cache`, pattern trên **không** tự mở rộng sang mọi domain con. Có thể thiết kế pattern phù hợp cú pháp JMX để query theo domain cần thiết, hoặc thống nhất dùng một domain với key `module` để dễ truy vấn.

Ví dụ:

```text
com.example.billing:type=Cache,name=TaxRate,module=Pricing
com.example.billing:type=Queue,name=Invoices,module=Settlement
```

Sau đó có thể query theo key property như:

```java
server.queryNames(
    new ObjectName("com.example.billing:module=Pricing,*"),
    null
);
```

Đây là cách phân nhóm theo module **trong cùng domain**.

Không dùng pattern quá rộng khi gọi operation thay đổi trạng thái: nên lấy danh sách, kiểm tra từng exact ObjectName, rồi mới thao tác.

## 13. Đọc domain đang được quản lý

Để xem các domain hiện tồn tại trong MBeanServer:

```java
String[] domains = server.getDomains();

for (String domain : domains) {
    System.out.println(domain);
}
```

Cần phân biệt:

- `getDomains()` phản ánh các domain đã có MBean đăng ký tại thời điểm gọi.
- Domain không phải cấu hình “được cấp quyền” hoặc “được tạo” trước.
- Không có API chuẩn yêu cầu bạn “create domain” trước khi đăng ký MBean.
- Một domain có thể biến mất khỏi danh sách nếu không còn MBean nào thuộc domain đó.

Vì vậy, muốn tạo domain ứng dụng, bạn đăng ký MBean với ObjectName dùng domain đó.

## 14. Kiểm thử bằng MBeanServer riêng

Trong kiểm thử, nên dùng `MBeanServerFactory.createMBeanServer` hoặc `newMBeanServer` để tránh tác động tới MBean platform đang chạy.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.*;
import org.junit.jupiter.api.Test;

class JmxDomainIsolationTest {

    @Test
    void separatesApplicationDomains() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("test.management");

        ObjectName billingName = new ObjectName(
            "com.example.billing:type=Queue,name=Invoices"
        );
        ObjectName inventoryName = new ObjectName(
            "com.example.inventory:type=Queue,name=StockSync"
        );

        try {
            server.registerMBean(new BillingQueueMonitor(), billingName);
            server.registerMBean(new BillingQueueMonitor(), inventoryName);

            assertTrue(server.isRegistered(billingName));
            assertTrue(server.isRegistered(inventoryName));

            assertEquals(
                1,
                server.queryNames(
                    new ObjectName("com.example.billing:*"), null
                ).size()
            );
            assertEquals(
                1,
                server.queryNames(
                    new ObjectName("com.example.inventory:*"), null
                ).size()
            );
        } finally {
            if (server.isRegistered(billingName)) {
                server.unregisterMBean(billingName);
            }
            if (server.isRegistered(inventoryName)) {
                server.unregisterMBean(inventoryName);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Với test production-like, nên dùng hai implementation MBean của hai module tương ứng, thay vì tái dùng cùng class demo như trên. Test ở đây chứng minh rằng domain khác nhau giúp query đúng tập và không xung đột.

## 15. Kiểm thử hai MBeanServer độc lập

Để thấy rõ domain không giống registry, tạo hai server:

```java
import javax.management.*;

MBeanServer billingServer =
    MBeanServerFactory.newMBeanServer("billing.management");
MBeanServer inventoryServer =
    MBeanServerFactory.newMBeanServer("inventory.management");

ObjectName sameName = new ObjectName(
    "com.example.shared:type=Health,name=Main"
);

billingServer.registerMBean(
    new BillingQueueMonitor(), sameName
);
inventoryServer.registerMBean(
    new BillingQueueMonitor(), sameName
);

System.out.println(billingServer.isRegistered(sameName));   // true
System.out.println(inventoryServer.isRegistered(sameName)); // true
```

Hai đăng ký không xung đột vì nằm ở hai server riêng. Tuy nhiên việc dùng **cùng ObjectName cho hai tài nguyên khác nghĩa** là lựa chọn naming kém nếu client aggregator sẽ hợp nhất dữ liệu mà không ghi lại server/endpoint.

Một định danh đầy đủ trong hệ thống quan sát nhiều nguồn thường gồm:

```text
(target JVM / connector identity, ObjectName)
```

Không nên coi `ObjectName` trên một MBeanServer là định danh toàn cục giữa mọi JVM và server.

## 16. Spring integration test: exporter đăng ký đúng server

Với hai server khác nhau, có thể kiểm tra một exporter chỉ đăng ký MBean ở server được cấu hình.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

class ExporterServerSelectionTest {
    @Test
    void exportsOnlyToConfiguredServer() throws Exception {
        MBeanServer billingServer =
                MBeanServerFactory.newMBeanServer("billing.management");
        MBeanServer otherServer =
                MBeanServerFactory.newMBeanServer("other.management");

        ObjectName name = new ObjectName(
            "com.example.billing:type=Queue,name=Invoices"
        );

        try (GenericApplicationContext context =
                new GenericApplicationContext()) {

            context.registerBean("exporter", MBeanExporter.class, () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(billingServer);
                exporter.setBeans(Map.of(
                    name.toString(), new BillingQueueMonitor()
                ));
                return exporter;
            });

            context.refresh();

            assertTrue(billingServer.isRegistered(name));
            assertFalse(otherServer.isRegistered(name));
        }
    }
}
```

Bài test xác nhận `setServer` có hiệu lực. Với cấu hình dùng `@EnableMBeanExport` hoặc XML namespace, test cũng cần xác minh exporter được tạo bởi cơ chế đó thực sự chọn server dự kiến.

Nếu client không thấy MBean dù test `isRegistered(name)` là true trên server riêng, có thể client đang kết nối platform server hoặc connector khác.

## 17. Phòng tránh trộn MBean khi dùng nhiều Spring context

Nhiều Spring context trong một JVM có thể cùng nhìn thấy platform server:

```text
Root ApplicationContext
  +-- shared infrastructure
  +-- JMX exporter A

Child ApplicationContext (billing)
  +-- billing beans
  +-- JMX exporter B

Child ApplicationContext (inventory)
  +-- inventory beans
  +-- JMX exporter C
```

Nên:

1. Xác định một hoặc nhiều exporter với ownership minh bạch.
2. Quy định domain/key property cho từng module.
3. Tránh để parent exporter autodetect những bean đã được child exporter đăng ký nếu cơ chế visibility cho phép.
4. Dùng một registration policy có chủ đích; đừng để `IGNORE_EXISTING` che giấu việc client đang nhìn thấy MBean cũ.
5. Đảm bảo exporter unregister MBean của mình khi context đóng.
6. Kiểm tra tên ổn định qua restart/redeploy.
7. Có integration test tạo hai context cùng lúc trên một server thử nghiệm và kiểm tra các `queryNames` mong đợi.

Nếu các context là ứng dụng thực sự độc lập với yêu cầu riêng về truy cập/quản trị, cân nhắc server riêng hoặc tiến trình riêng theo kiến trúc vận hành, chứ không chỉ đổi domain.

## 18. Vấn đề về classloader và vòng đời

Trong ứng dụng server nhúng hoặc container quản lý nhiều ứng dụng, có thể xảy ra:

- Classloader của module bị unload nhưng MBean cũ chưa được unregister.
- Context mới cố đăng ký một ObjectName đã bị module cũ giữ.
- Client vẫn đọc một MBean stale hoặc nhận lỗi khi method gọi tới object cũ.
- Spring exporter và một thư viện khác đều tin rằng mình sở hữu cùng một MBean.

Những vấn đề này không được giải quyết chỉ bằng đổi domain. Cần teardown đúng lifecycle và kiểm tra owner đăng ký.

Một naming convention giúp truy vết. Ví dụ domain `com.example.billing` cho biết thành phần nào nên chịu trách nhiệm, nhưng không tự unregister tài nguyên hay enforce ownership.

## 19. Checklist thiết kế và vận hành

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Domain | Domain có thuộc một application/module rõ ràng không? |
| ObjectName | Có `type`, `name` hoặc key phân biệt logic phù hợp không? |
| Tính ổn định | ObjectName có giữ nguyên qua restart của cùng resource không? |
| Registry | Exporter dùng platform server hay một MBeanServer riêng? |
| Client | JConsole/JMC/monitoring agent kết nối đến đúng server chưa? |
| Ownership | Ai đăng ký, ai unregister, khi nào? |
| Xung đột | Có exporter khác đăng ký cùng canonical ObjectName không? |
| Bảo mật | Ai có quyền đọc/ghi/invoke; domain có bị hiểu sai thành ACL không? |
| Multi-context | Context cha/con có đăng ký chồng lên nhau không? |
| Kiểm thử | Có xác nhận `queryNames`, `getMBeanInfo`, vòng đời và server selection không? |

## 20. Bài tập thực hành

1. Đăng ký hai Standard MBean vào cùng server, với domain `com.example.billing` và `com.example.inventory`. Query mỗi domain và xác nhận chỉ trả về MBean tương ứng.
2. Thử đăng ký hai MBean với cùng ObjectName trong cùng server để thấy `InstanceAlreadyExistsException`.
3. Tạo hai MBeanServer riêng và đăng ký cùng ObjectName; giải thích vì sao không trùng.
4. Cấu hình `MBeanExporter.setServer` để sử dụng server riêng, kiểm tra MBean không xuất hiện trong platform server.
5. Dùng `@ManagedResource` công bố MBean dưới domain nghiệp vụ có tên ổn định.
6. Viết integration test chạy hai Spring contexts dùng chung MBeanServer nhưng domain riêng; xác minh lifecycle khi đóng từng context.
7. Trong JConsole/JMC, kết nối đúng JVM rồi tìm domain ứng dụng. Giải thích vì sao MBean trên server tùy biến có thể không hiển thị.
8. Thiết kế naming convention cho ba module Billing, Inventory, Shipping và nêu các key giúp phân biệt resource.

## 21. Câu hỏi tự kiểm tra

- JMX domain có phải một MBeanServer riêng không?
- Domain có tự tạo quyền truy cập hoặc isolation bảo mật không?
- ObjectName có duy nhất giữa các MBeanServer khác nhau không?
- Vì sao platform MBeanServer và domain riêng thường đủ cho một ứng dụng Spring thông thường?
- Điều gì xảy ra nếu exporter đăng ký vào server khác server mà client đang kết nối?
- `getDomains()` có nghĩa “các domain được cấp phép” hay “các domain đang có MBean”?
- Khi ứng dụng redeploy mà gặp ObjectName trùng, đổi domain có phải là giải pháp đúng luôn không?
- Vì sao cần định danh cả target JVM/connector và ObjectName khi giám sát nhiều JVM?

**Ghi nhớ:** **Domain riêng** giúp nhóm và phân biệt MBean trong cùng một MBeanServer; **MBeanServer riêng** tạo registry quản trị độc lập. Hai cơ chế phục vụ mục tiêu khác nhau. Trong Spring JMX, hãy đặt domain theo ứng dụng/module, chọn đúng server cho `MBeanExporter`, kiểm soát ownership và lifecycle, kiểm tra bằng `queryNames` và `isRegistered`, đồng thời không nhầm namespace với bảo mật.