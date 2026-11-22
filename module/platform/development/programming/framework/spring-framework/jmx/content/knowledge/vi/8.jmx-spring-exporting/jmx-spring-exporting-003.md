# Cấu hình map beans giữa ObjectName và bean trong Spring JMX

## Mục tiêu

Sau bài học, bạn có thể dùng Spring Framework để cấu hình ánh xạ giữa **JMX `ObjectName`** và **Spring bean** thông qua `MBeanExporter`; hiểu cách các entry trong map trở thành MBean được đăng ký với `MBeanServer`; lựa chọn cơ chế đăng ký rõ ràng; xác định sự khác biệt giữa khóa map, tên Spring bean và tên JMX; xử lý xung đột tên, vòng đời, proxy và chính sách thay thế MBean; đồng thời kiểm tra kết quả bằng API JMX.

## 1. Vì sao cần ánh xạ ObjectName và bean?

Trong Spring Framework, service hoặc component thường được tạo và quản lý bởi `ApplicationContext`. JMX lại nhận diện đối tượng quản trị bằng `javax.management.ObjectName` trong một `MBeanServer`.

Hai tên này phục vụ hai nhiệm vụ khác nhau:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Spring bean name | `paymentQueueMonitor` | Tìm và quản lý object trong IoC container |
| JMX ObjectName | `com.example.payment:type=Queue,name=Primary` | Định danh MBean trong `MBeanServer` |
| Java type | `PaymentQueueMonitor` | Xác định implementation và khả năng quản trị |
| MBean interface/metadata | `PaymentQueueMonitorMBean` hoặc `@ManagedResource` | Chỉ ra attributes và operations được công bố |

Ánh xạ tường minh cho phép bạn nói với Spring:

> Đăng ký **bean này** dưới **ObjectName kia** trong MBeanServer.

Đây là nhiệm vụ chính của thuộc tính `beans` trên `org.springframework.jmx.export.MBeanExporter`.

Ví dụ mục tiêu:

```text
Spring ApplicationContext
  paymentQueueMonitor  ------> com.example.payment:type=Queue,name=Primary
  refundQueueMonitor   ------> com.example.payment:type=Queue,name=Refund
  workerMonitor        ------> com.example.payment:type=Worker,name=Retry
                               |
                               v
                         JMX MBeanServer
```

Bạn kiểm soát được tên quản trị, tránh phải dựa vào suy luận từ class name hoặc tên bean tự động.

## 2. Map beans của MBeanExporter là gì?

`MBeanExporter` có thuộc tính `beans` dùng để xác định những đối tượng cần xuất sang JMX. Khóa map có thể là chuỗi `ObjectName`; giá trị thường là bean object hoặc tham chiếu tên bean theo cơ chế mà exporter hỗ trợ.

Dạng khái niệm:

```java
Map<String, Object> beans = Map.of(
    "com.example.payment:type=Queue,name=Primary", paymentQueueMonitor,
    "com.example.payment:type=Queue,name=Refund", refundQueueMonitor
);
exporter.setBeans(beans);
```

Tại bước đăng ký, exporter chuyển mỗi entry thành một MBean được quản lý bởi `MBeanServer`.

**Không nhầm khóa map với tên bean.** Khóa `com.example.payment:type=Queue,name=Primary` là tên xuất hiện trước JMX client, trong khi `paymentQueueMonitor` là object/bean do Spring tạo.

Cơ chế `setBeans` là **đăng ký tường minh**. Nó khác với:

- `setAutodetect(true)`: Spring phát hiện bean phù hợp theo quy tắc autodetection và exporter/assembler.
- `@ManagedResource` cùng cơ chế quét/metadata: cung cấp metadata JMX để exporter sử dụng, nhưng không tự bảo đảm mọi bean được đăng ký nếu không có exporter phù hợp.
- Đăng ký trực tiếp bằng `MBeanServer.registerMBean(...)`: bạn tự quản lý toàn bộ việc đăng ký và hủy đăng ký.

Trong một ứng dụng nên chọn chiến lược có chủ đích để tránh cùng một bean bị export hai lần.

## 3. Ví dụ hoàn chỉnh: Standard MBean được map rõ ràng

Tạo interface Standard MBean:

```java
package com.example.payment.jmx;

public interface PaymentQueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void setPaused(boolean paused);
    void resetPending();
}
```

Implementation:

```java
package com.example.payment.jmx;

public class PaymentQueueMonitor implements PaymentQueueMonitorMBean {
    private volatile int pendingCount = 20;
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @Override
    public void resetPending() {
        pendingCount = 0;
    }
}
```

Cấu hình Java-based Spring:

```java
package com.example.payment.config;

import com.example.payment.jmx.PaymentQueueMonitor;
import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class PaymentJmxConfiguration {
    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor();
    }

    @Bean
    public MBeanExporter paymentMBeanExporter(
            PaymentQueueMonitor paymentQueueMonitor) {
        MBeanExporter exporter = new MBeanExporter();

        Map<String, Object> registrations = new HashMap<>();
        registrations.put(
            "com.example.payment:type=Queue,name=Primary",
            paymentQueueMonitor
        );

        exporter.setBeans(registrations);
        return exporter;
    }
}
```

Spring tạo `PaymentQueueMonitor` như singleton bean, sau đó truyền object vào cấu hình exporter. Khi exporter khởi tạo, nó đăng ký bean vào `MBeanServer` theo ObjectName đã đặt. Trong trường hợp một Standard MBean hợp lệ, interface `PaymentQueueMonitorMBean` quyết định thuộc tính và thao tác mà client JMX nhìn thấy.

Một JMX client có thể thấy:

```text
com.example.payment:type=Queue,name=Primary

Attributes
  PendingCount : int      read-only
  Paused       : boolean  read-write

Operations
  resetPending() : void
```

**Điểm cần hiểu:** tên `Primary` không được Spring suy ra từ `PaymentQueueMonitor`; nó đến từ khóa map. Đổi tên Spring bean nhưng giữ ObjectName và hợp đồng MBean ổn định có thể giúp client JMX tiếp tục tìm đúng tài nguyên.

## 4. Map nhiều bean sang các ObjectName khác nhau

Giả sử có hai queue với vai trò riêng:

```java
@Bean
public PaymentQueueMonitor primaryMonitor() {
    return new PaymentQueueMonitor();
}

@Bean
public PaymentQueueMonitor refundMonitor() {
    return new PaymentQueueMonitor();
}

@Bean
public MBeanExporter queueExporter(
        @Qualifier("primaryMonitor") PaymentQueueMonitor primary,
        @Qualifier("refundMonitor") PaymentQueueMonitor refund) {
    MBeanExporter exporter = new MBeanExporter();

    Map<String, Object> registrations = new LinkedHashMap<>();
    registrations.put(
        "com.example.payment:type=Queue,name=Primary", primary
    );
    registrations.put(
        "com.example.payment:type=Queue,name=Refund", refund
    );

    exporter.setBeans(registrations);
    return exporter;
}
```

Các import bổ sung:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
```

Map cho phép đăng ký nhiều đối tượng khác nhau, nhưng **mỗi `ObjectName` trong cùng `MBeanServer` phải duy nhất**. Hai object có thể có cùng Java class nhưng phải dùng key khác nhau nếu là hai tài nguyên riêng biệt.

Ví dụ nên dùng:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:type=Queue,name=Refund
```

Tránh tạo tên bằng ID ngẫu nhiên phát sinh mỗi restart nếu danh tính tài nguyên vẫn là `Primary` hoặc `Refund`. Tên logic ổn định giúp dashboard, script quản trị và alert không phải đổi theo phiên chạy.

## 5. Định dạng khóa: chuỗi ObjectName hợp lệ

Khóa trong map cần tuân theo cú pháp `ObjectName`:

```text
domain:key=value[,key=value...]
```

Ví dụ:

```text
com.example.billing:type=ConnectionPool,name=Main
com.example.billing:type=Cache,name=Product
com.example.billing:type=JobScheduler,name=Nightly
```

Không dùng tùy tiện ký tự đặc biệt trong value. Khi tên logic được lấy từ cấu hình, nên dùng `ObjectName` constructor hoặc `ObjectName.quote` để tránh dấu phẩy, dấu bằng hay wildcard làm thay đổi cấu trúc tên.

```java
import javax.management.ObjectName;

String queueName = "High,Priority";
ObjectName objectName = new ObjectName(
    "com.example.payment:type=Queue,name="
        + ObjectName.quote(queueName)
);
```

Nếu dùng `ObjectName` làm khóa nội bộ, nhiều API Spring có thể nhận các dạng tên/metadata khác nhau tùy phương thức cấu hình. Với `MBeanExporter.setBeans`, cách rõ ràng nhất là chuỗi tên JMX hoàn chỉnh, đúng cú pháp, và giữ quy tắc tạo tên tập trung.

**Đặc điểm quan trọng:** thứ tự key property không làm thay đổi danh tính theo `ObjectName.equals()`. `com.example:type=Queue,name=Main` và `com.example:name=Main,type=Queue` là cùng ObjectName. Vì vậy, đừng dựa vào sự khác nhau về thứ tự string để tránh trùng tên.

## 6. Giá trị map là object nào?

Trong Java configuration, phổ biến nhất là truyền chính object Spring bean:

```java
Map<String, Object> registrations = Map.of(
    "com.example:type=Cache,name=Product", productCacheMonitor
);
exporter.setBeans(registrations);
```

Cần chú ý object có thể là **Spring AOP proxy**, không phải class đích. JDK dynamic proxy có thể chỉ triển khai interface nghiệp vụ; CGLIB proxy là subclass động. Điều này ảnh hưởng việc JMX nhận diện Standard MBean/MXBean và các operation được công bố.

Nếu bean đã triển khai `CacheMonitorMBean` nhưng exporter gặp lỗi `NotCompliantMBeanException`, có thể dùng **adapter MBean** hoặc bọc interface tường minh:

```java
import javax.management.StandardMBean;

CacheMonitorMBean exposed = cacheMonitorProxy;
StandardMBean adapter = new StandardMBean(
    exposed,
    CacheMonitorMBean.class
);

Map<String, Object> registrations = Map.of(
    "com.example:type=Cache,name=Product", adapter
);
exporter.setBeans(registrations);
```

Điều kiện là `cacheMonitorProxy` thực sự triển khai `CacheMonitorMBean`. Nếu không, cần một adapter quản trị gọi tới service proxy bằng interface tương thích. Tránh trực tiếp đưa target object vào JMX nếu việc đó bỏ qua security/transaction advice quan trọng.

Cũng cần nhớ `MBeanExporter` có thể xử lý bean thông qua các cơ chế metadata/assembler tùy cấu hình. Vì vậy, chọn cách đăng ký và interface một cách chủ đích rồi kiểm tra `MBeanInfo` sau khi Spring khởi tạo.

## 7. Đăng ký bean qua annotation và MBeanExporter

Spring còn hỗ trợ `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.payment:type=Queue,name=Primary",
    description = "Primary payment queue monitor"
)
public class AnnotatedQueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 20;
    }

    @ManagedOperation
    public void resetPending() {
        // Reset queue statistics
    }
}
```

Nếu muốn exporter sử dụng annotation metadata, cần cấu hình assembler phù hợp, ví dụ `MetadataMBeanInfoAssembler` và `AnnotationJmxAttributeSource`, hoặc dùng `@EnableMBeanExport` trong cấu hình Spring tương ứng.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxAnnotationConfig {
}
```

Đây là cách khác để tổ chức export. Không nên đồng thời tự động export một bean có `@ManagedResource` và khai báo map `beans` khác cho cùng ObjectName mà chưa kiểm soát rõ việc đăng ký. Kết quả có thể là trùng tên MBean, lỗi hoặc xử lý theo registration policy.

### Khi nào dùng map tường minh?

- Muốn chọn **chính xác** một số bean được export.
- Cần quy tắc ObjectName chung, khác với tên Spring bean.
- Muốn một lớp cấu hình chịu trách nhiệm naming độc lập với implementation.
- Cần xuất nhiều instance cùng class dưới các tên khác nhau.
- Muốn dễ tìm toàn bộ các registration trong một nơi.

### Khi nào dùng annotation/auto-detection?

- Dự án quy định metadata JMX đặt cùng class.
- Số lượng component quản trị nhiều và dùng cơ chế scan được quản lý nhất quán.
- Muốn khai báo `@ManagedAttribute`/`@ManagedOperation` ngay trên method.

Hai cách có thể kết hợp trong một chiến lược có kiểm soát, nhưng tránh duplicate registration và đảm bảo exporter sử dụng đúng naming/metadata source.

## 8. Dùng ObjectNamingStrategy khi naming có quy tắc chung

Khi có nhiều MBean và tên phải được sinh theo quy ước, Spring cho phép dùng `ObjectNamingStrategy`. Một số chiến lược phổ biến thuộc `org.springframework.jmx.export.naming`, ví dụ `MetadataNamingStrategy`, `KeyNamingStrategy`, `IdentityNamingStrategy`.

Trong trường hợp ánh xạ tường minh, map key đã là ObjectName hoàn chỉnh thì không cần chiến lược phức tạp. Khi muốn tên được tạo từ class, annotation hoặc key nội bộ, cần hiểu thứ tự ưu tiên và cơ chế naming của exporter.

Quy ước tốt thường gồm domain do tổ chức quản lý và các key property có ý nghĩa:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:type=Queue,name=Refund
com.example.payment:type=Cache,name=ExchangeRates
```

Tránh dựa vào `System.identityHashCode` hoặc tên class proxy khi cần danh tính ổn định qua restart.

## 9. Chọn MBeanServer: local hay shared

`MBeanExporter` phải đăng ký vào một `MBeanServer`. Nếu không đặt cụ thể, exporter có thể dùng cơ chế tìm/chọn MBeanServer theo cấu hình và môi trường Spring.

Trong ứng dụng dùng platform MBeanServer, có thể tạo bean tham chiếu rõ ràng:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer platformMBeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
```

Sau đó cấu hình exporter:

```java
@Bean
public MBeanExporter exporter(
        MBeanServer platformMBeanServer,
        PaymentQueueMonitor paymentQueueMonitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(platformMBeanServer);
    exporter.setBeans(Map.of(
        "com.example.payment:type=Queue,name=Primary",
        paymentQueueMonitor
    ));
    return exporter;
}
```

Hãy đảm bảo tham số inject đúng `MBeanServer` dự định dùng, đặc biệt trong môi trường có nhiều server. Việc JConsole/JMC không thấy MBean có thể do exporter đăng ký ở server khác với server mà công cụ đang kết nối.

Khi không cần bean `MBeanServer` riêng, bạn có thể cấu hình/đăng ký trực tiếp với platform server trong một chỗ. Không nên tạo nhiều MBeanServer tùy ý chỉ để tránh xung đột tên.

## 10. Registration policy khi ObjectName đã tồn tại

Nếu một MBean đã được đăng ký với cùng `ObjectName` trong cùng `MBeanServer`, JMX mặc định không cho phép đăng ký một object thứ hai cùng tên.

Các nguyên nhân phổ biến:

- Hai exporter đăng ký cùng bean.
- Bean được đưa vào map và cũng được phát hiện qua auto-detection.
- Hai context Spring dùng cùng platform MBeanServer.
- MBean cũ chưa unregister ở lần refresh/redeploy cùng JVM.
- Hai entry map có các chuỗi tên khác thứ tự key nhưng cùng canonical ObjectName.

Spring `MBeanExporter` có registration policy, chẳng hạn `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, `REPLACE_EXISTING` (tên enum trong `org.springframework.jmx.support.RegistrationPolicy`).

Ví dụ:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

- `FAIL_ON_EXISTING`: báo xung đột để người phát triển sửa ownership.
- `IGNORE_EXISTING`: bỏ qua đăng ký mới nếu đã có MBean cùng tên.
- `REPLACE_EXISTING`: có thể thay thế MBean tồn tại, cần hiểu ai sở hữu và lifecycle của nó.

Đối với hệ thống nhiều context, `REPLACE_EXISTING` phải được dùng thận trọng vì có thể làm mất MBean do component khác quản lý. Khi ưu tiên cấu hình rõ ràng, để lỗi trùng tên xuất hiện thường giúp tìm đúng nguyên nhân.

## 11. Vòng đời MBeanExporter

`MBeanExporter` tích hợp với vòng đời Spring:

1. Context tạo bean được quản lý.
2. Exporter nhận cấu hình map.
3. Exporter đăng ký MBean vào MBeanServer trong giai đoạn khởi tạo phù hợp.
4. JMX client truy cập các attribute/operation.
5. Khi context đóng bình thường, exporter hủy đăng ký những MBean do nó quản lý theo cơ chế lifecycle.

Trong quá trình ứng dụng đang chạy, không nên coi map `beans` là cơ chế tự động đồng bộ mọi thay đổi runtime sau khởi tạo. Nếu cần thêm/hủy MBean động, dùng API đăng ký riêng của exporter hoặc MBeanServer có quản lý ownership và đồng bộ thích hợp.

Nếu một MBean cùng tên cần được đăng ký lại, hãy đảm bảo lifecycle cũ đã kết thúc hoặc xử lý rõ registration policy; không gắn suffix ngẫu nhiên vào ObjectName để bỏ qua lỗi.

## 12. Kiểm chứng mapping bằng MBeanServer và MBeanInfo

Sau khi ApplicationContext khởi tạo, kiểm tra trực tiếp:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.payment:type=Queue,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("Class: " + info.getClassName());

    Object pending = server.getAttribute(name, "PendingCount");
    System.out.println("Pending: " + pending);

    for (var operation : info.getOperations()) {
        System.out.println("Operation: " + operation.getName());
    }
}
```

Điều kiện là exporter đăng ký trên **platform MBeanServer**. Nếu ứng dụng cấu hình server khác, phải dùng reference tới đúng server đó.

Bạn cũng có thể query theo mẫu:

```java
for (ObjectName registered : server.queryNames(
        new ObjectName("com.example.payment:type=Queue,*"), null)) {
    System.out.println(registered.getCanonicalName());
}
```

Wildcard query giúp khám phá MBean nhưng không thay thế việc dùng tên chính xác trong script cần đối tượng cụ thể.

Nếu `isRegistered(name)` trả về `true` nhưng thiếu attribute, kiểm tra contract của Standard MBean, MXBean, Spring metadata assembler và proxy thực sự được exporter nhận.

## 13. Một bài kiểm tra integration trong Spring

Có thể viết test tạo context, cấu hình exporter, rồi xác nhận MBean thực tế:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class PaymentJmxConfigurationTest {
    @Test
    void exportsMonitorWithExpectedObjectName() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.payment:type=Queue,name=Primary"
        );

        try (var context = new AnnotationConfigApplicationContext(
                PaymentJmxConfiguration.class)) {
            assertTrue(server.isRegistered(name));
            assertEquals(20, server.getAttribute(name, "PendingCount"));
        }

        assertFalse(server.isRegistered(name));
    }
}
```

Test giả định không có MBean cùng tên tồn tại trước đó, exporter dùng platform server và context đóng thành công. Với test chạy song song, nên dùng ObjectName namespace riêng ổn định theo test để tránh tranh chấp trong cùng JVM; dọn dẹp đúng lifecycle thay vì `unregisterMBean` bừa bãi.

## 14. Phân tích lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `MalformedObjectNameException` hoặc lỗi parse naming | Chuỗi ObjectName sai cú pháp, ký tự đặc biệt không được quote | Dùng `ObjectName`, `ObjectName.quote`, chuẩn hóa key |
| `NotCompliantMBeanException` | Bean không phải MBean hợp lệ theo quy ước hoặc proxy làm mất interface | Kiểm tra MBean interface, MXBean, adapter/`StandardMBean` |
| `InstanceAlreadyExistsException` | ObjectName đã đăng ký | Kiểm tra exporter trùng, lifecycle và registration policy |
| JMC/JConsole không thấy MBean | Exporter chưa hoạt động, server khác hoặc tên không đúng | Kiểm tra `MBeanServer`, domain, `isRegistered` |
| Thấy MBean nhưng thiếu attribute/operation | Metadata assembler hoặc interface quản trị không công bố method | Kiểm tra `MBeanInfo` và cấu hình Spring |
| Method JMX chạy nhưng aspect không có hiệu lực | Exporter nhận target thay proxy | Đảm bảo adapter gọi đúng Spring proxy hoặc cấu hình exposure đúng |
| Giá trị attribute lỗi khi đọc | Getter ném exception, kiểu dữ liệu không phù hợp | Kiểm tra log, kiểu Java/Open Data, tránh getter nặng |
| Không thấy cập nhật sau khi đổi map trong code | Context/exporter chưa được tái khởi tạo | Khởi động lại context hoặc đăng ký/hủy đăng ký theo lifecycle |

## 15. Lựa chọn cấu hình XML

Với một dự án Spring Framework dùng XML, map có thể khai báo trong `MBeanExporter`:

```xml
<bean id="queueMonitor" class="com.example.payment.jmx.PaymentQueueMonitor"/>

<bean id="jmxExporter" class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.payment:type=Queue,name=Primary"
                   value-ref="queueMonitor"/>
        </map>
    </property>
</bean>
```

Ở đây, `key` là chuỗi `ObjectName`, còn `value-ref` tham chiếu tới Spring bean theo ID. XML làm rõ quan hệ giữa tên quản trị và object, thích hợp khi dự án vẫn duy trì cấu hình XML.

Nếu cần nhiều MBean, bổ sung các `entry` với key duy nhất. Tránh để hai context đăng ký trùng key trong cùng MBeanServer khi chúng cùng hoạt động.

## 16. Nguyên tắc thiết kế thực tế

- Đặt domain theo namespace tổ chức hoặc module, ví dụ `com.example.payment`, `com.example.inventory`.
- Dùng key property có ý nghĩa vận hành: `type`, `name`, `component`, `tenant` khi cần.
- Giữ danh tính logic ổn định qua restart; PID, UUID sinh mới, số thread hoặc thời gian khởi động nên là attribute.
- Xuất interface quản trị nhỏ, không công bố toàn bộ API nội bộ của Spring bean.
- Quy định rõ component nào chịu trách nhiệm đăng ký và unregister MBean.
- Đảm bảo các operation JMX nhạy cảm có kiểm soát truy cập phù hợp; Spring AOP không thay thế bảo mật của remote JMX.
- Thống nhất cơ chế export để tránh một bean vừa được explicit map vừa bị autodetect.
- Kiểm tra trên client thực như JConsole hoặc JMC, ngoài API `MBeanServer` trong test.

## 17. Bài tập

1. Tạo hai bean `PaymentQueueMonitor` và ánh xạ chúng tới `name=Primary`, `name=Refund`. Đọc hai giá trị `PendingCount` bằng `MBeanServer`.
2. Đổi tên Spring bean `primaryMonitor` thành `paymentPrimaryMonitor` nhưng giữ nguyên ObjectName. Giải thích ảnh hưởng tới client JMX.
3. Cố tình đăng ký cùng ObjectName từ hai exporter khác nhau để quan sát lỗi xung đột. Sửa bằng cách xác định một exporter sở hữu MBean.
4. Thay map object bằng adapter `StandardMBean` khi bean nghiệp vụ là JDK proxy, rồi so sánh `MBeanInfo`.
5. Đọc metadata của một bean annotation-driven và một bean explicit map để hiểu cách interface/assembler quyết định attribute và operation.
6. Viết test integration kiểm tra cả `isRegistered` và `getAttribute`, sau đó đóng context và xác minh MBean không còn đăng ký.

## 18. Câu hỏi tự kiểm tra

- Trong `MBeanExporter.setBeans`, khóa map đại diện cho gì và giá trị đại diện cho gì?
- Vì sao cùng một Java class có thể được xuất thành hai MBean khác nhau?
- Điều gì xảy ra nếu hai exporter đăng ký cùng canonical `ObjectName`?
- Khi nào `@ManagedResource` và `@EnableMBeanExport` có thể tạo xung đột với explicit mapping?
- Khi MBean không xuất hiện trong JMC, cần kiểm tra tên, exporter hay MBeanServer trước?
- Vì sao đăng ký target thay proxy có thể ảnh hưởng bảo mật hoặc transaction advice?
- Tại sao cần giữ ObjectName ổn định dù tên bean và class implementation thay đổi?

**Ghi nhớ:** `MBeanExporter.setBeans` là cầu nối tường minh từ **ObjectName JMX** tới **Spring bean/object**. Khóa map xác định danh tính quản trị, giá trị là object được export. Hãy giữ tên duy nhất và ổn định, chọn đúng server và cơ chế exporter, kiểm tra hợp đồng thực tế bằng `MBeanInfo`, và quản lý vòng đời đăng ký rõ ràng.