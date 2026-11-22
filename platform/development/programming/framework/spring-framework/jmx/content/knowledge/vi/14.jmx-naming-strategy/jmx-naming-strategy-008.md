# Xử lý nhiều instance cùng một loại bean trong Spring JMX

## Mục tiêu học tập

Khi ứng dụng Spring Framework tạo nhiều instance cùng một lớp Java, bạn cần phân biệt chúng trong JMX bằng các `ObjectName` duy nhất. Sau bài này, bạn có thể giải thích phạm vi định danh MBean, thiết kế naming strategy cho nhiều instance, cấu hình `MBeanExporter` đăng ký nhiều bean cùng loại, tránh xung đột tên và xác minh registry bằng `MBeanServer` hoặc JConsole.

Bài học thuộc nhóm **Naming strategy** của Spring Framework JMX, tập trung vào câu hỏi: làm thế nào để những đối tượng cùng kiểu như `CacheMonitor`, `DataSourceMonitor` hoặc `WorkerPoolMonitor` có thể cùng xuất hiện trong một JMX registry mà vẫn dễ nhận biết và quản trị riêng biệt?

## 1. Một class Java có thể có nhiều MBean instance

Giả sử ứng dụng phục vụ hai tenant và có hai cache riêng:

```text
cacheMonitorPrimary   -> CacheMonitor(instance A)
cacheMonitorSecondary -> CacheMonitor(instance B)
```

Hai đối tượng đều thuộc class `CacheMonitor`, cùng có các attribute và operation quản lý. Tuy nhiên, chúng chứa **trạng thái độc lập**. Nếu bộ đếm hit của cache A là 120 và cache B là 450, JMX cần công bố hai đối tượng khác nhau để công cụ quản trị không nhầm số liệu.

Một `MBeanServer` đăng ký MBean theo `javax.management.ObjectName`. Trong **cùng một server**, mỗi `ObjectName` chỉ định danh được một registration tại một thời điểm. Do đó, hai instance cùng class không thể đồng thời dùng chính xác một tên:

```text
com.example.cache:type=CacheMonitor
com.example.cache:type=CacheMonitor
```

Ngược lại, hai tên có property khác nhau là hợp lệ:

```text
com.example.cache:type=CacheMonitor,name=primary
com.example.cache:type=CacheMonitor,name=secondary
```

Đây không phải yêu cầu đổi tên class hoặc tạo hai interface `*MBean`. Cả hai instance có thể thực hiện cùng một hợp đồng quản lý. Khác biệt nằm ở định danh của từng đối tượng đăng ký trong registry.

## 2. Phân biệt Java class, Spring bean name và JMX ObjectName

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Class Java | `CacheMonitor` | Định nghĩa behavior và các method |
| Management interface | `CacheMonitorMBean` | Định nghĩa API quản lý chuẩn |
| Spring bean name | `primaryCacheMonitor` | Phân biệt bean trong `ApplicationContext` |
| Spring bean name khác | `secondaryCacheMonitor` | Một bean khác có cùng Java type |
| JMX `ObjectName` | `com.example.cache:type=CacheMonitor,name=primary` | Định danh instance A trong MBean server |
| JMX `ObjectName` khác | `com.example.cache:type=CacheMonitor,name=secondary` | Định danh instance B trong cùng server |

Tên bean trong Spring không tự động trở thành `ObjectName` trong JMX. Tên Java class cũng không đủ để phân biệt nhiều instance.

Spring có thể dùng naming strategy để suy ra tên quản lý, nhưng cần hiểu **strategy cụ thể đang được cấu hình**. Nếu tên sinh ra chỉ dựa trên class mà không chứa identity của instance, hai bean cùng type có nguy cơ trùng tên.

Một naming convention dễ vận hành thường gồm domain ổn định và những key có ý nghĩa:

```text
com.example.cache:type=CacheMonitor,name=primary
com.example.cache:type=CacheMonitor,name=secondary
com.example.cache:type=CacheMonitor,tenant=tenant-a,name=local
com.example.cache:type=CacheMonitor,tenant=tenant-b,name=local
```

Các key là lựa chọn thiết kế, không phải danh sách bắt buộc của JMX. Một `ObjectName` có dạng `domain:key=value,key=value`; domain và key properties cần tạo ra tổ hợp duy nhất cho từng registration.

## 3. Ví dụ Standard MBean dùng chung hợp đồng

Tạo interface quản lý cho tất cả instance `CacheMonitor`:

**CacheMonitorMBean.java**

```java
package com.example.jmx;

public interface CacheMonitorMBean {
    String getLogicalName();
    long getHitCount();
    void resetStatistics();
}
```

**CacheMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class CacheMonitor implements CacheMonitorMBean {
    private final String logicalName;
    private final AtomicLong hits = new AtomicLong();

    public CacheMonitor(String logicalName) {
        this.logicalName = logicalName;
    }

    public void recordHit() {
        hits.incrementAndGet();
    }

    @Override
    public String getLogicalName() {
        return logicalName;
    }

    @Override
    public long getHitCount() {
        return hits.get();
    }

    @Override
    public void resetStatistics() {
        hits.set(0);
    }
}
```

Cả hai instance dùng `CacheMonitorMBean` và có cùng danh sách attribute/operation. Thuộc tính `LogicalName` giúp người vận hành nhận diện object đang quan sát, nhưng **không thay thế việc đặt `ObjectName` duy nhất**: JMX tra cứu registration bằng `ObjectName`, không dùng giá trị attribute để phân giải tên trùng.

Sử dụng `AtomicLong` để phép tăng số đếm và reset có ngữ nghĩa thread-safe ở mức biến đếm. Tuy nhiên, nếu yêu cầu xử lý đồng thời phức tạp hơn, cần thiết kế synchronization hoặc snapshot phù hợp.

## 4. Cấu hình MBeanExporter xuất hai instance cùng loại

Một cách tường minh là tạo hai Spring beans và đưa vào `MBeanExporter.setBeans(...)` với hai tên JMX khác nhau.

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MultiInstanceJmxConfiguration {

    @Bean("primaryCacheMonitor")
    public CacheMonitor primaryCacheMonitor() {
        return new CacheMonitor("primary");
    }

    @Bean("secondaryCacheMonitor")
    public CacheMonitor secondaryCacheMonitor() {
        return new CacheMonitor("secondary");
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter cacheExporter(
            @Qualifier("primaryCacheMonitor") CacheMonitor primary,
            @Qualifier("secondaryCacheMonitor") CacheMonitor secondary,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.cache:type=CacheMonitor,name=primary",
                primary,
                "com.example.cache:type=CacheMonitor,name=secondary",
                secondary
        ));
        return exporter;
    }
}
```

Điểm chính:

1. `@Bean("primaryCacheMonitor")` và `@Bean("secondaryCacheMonitor")` tạo hai singleton Spring bean độc lập.
2. `@Qualifier` xác định chính xác bean nào được inject khi có nhiều bean cùng Java type.
3. `Map.of` liên kết mỗi instance với một `ObjectName` riêng.
4. `MBeanExporter` đăng ký cả hai vào **cùng platform `MBeanServer`**.
5. Management interface không cần nhân bản. Cả hai dùng contract `CacheMonitorMBean`.
6. JConsole có thể xem, đọc và invoke riêng từng instance theo tên đã đăng ký.

Trong ứng dụng Spring Boot có auto-configuration JMX, cần xem exporter nào đã được tạo và chọn cơ chế cấu hình phù hợp để tránh đăng ký trùng.

## 5. Chứng minh hai MBean có trạng thái độc lập

Chạy `ApplicationContext` rồi thay đổi hai bean theo cách khác nhau:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class MultiInstanceDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                MultiInstanceJmxConfiguration.class)) {

            CacheMonitor primary = context.getBean(
                    "primaryCacheMonitor", CacheMonitor.class);
            CacheMonitor secondary = context.getBean(
                    "secondaryCacheMonitor", CacheMonitor.class);

            primary.recordHit();
            primary.recordHit();
            secondary.recordHit();

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName primaryName = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=primary");
            ObjectName secondaryName = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=secondary");

            System.out.println(
                    "Primary registered: " + server.isRegistered(primaryName));
            System.out.println(
                    "Secondary registered: " + server.isRegistered(secondaryName));

            System.out.println(
                    "Primary hits: " + server.getAttribute(primaryName, "HitCount"));
            System.out.println(
                    "Secondary hits: " + server.getAttribute(secondaryName, "HitCount"));

            server.invoke(
                    primaryName,
                    "resetStatistics",
                    new Object[0],
                    new String[0]);

            System.out.println(
                    "Primary after reset: "
                    + server.getAttribute(primaryName, "HitCount"));
            System.out.println(
                    "Secondary after primary reset: "
                    + server.getAttribute(secondaryName, "HitCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.in.read(); // Giữ context để xem trong JConsole.
        }
    }
}
```

Nếu mọi thứ đăng ký đúng, trước khi reset bạn sẽ thấy `primary=2` và `secondary=1`. Gọi `resetStatistics` với `primaryName` chỉ reset bộ đếm của primary; secondary vẫn có `HitCount=1`.

Ví dụ cho thấy **ObjectName quyết định object nào nhận lời gọi JMX**. Hai instance dùng chung method signature nhưng được điều khiển độc lập.

## 6. Naming strategy trong MBeanExporter

Trong ví dụ trước, exporter nhận sẵn các `ObjectName` cụ thể qua `setBeans`. Khi nhiều bean cần được xuất tự động, naming strategy giúp thiết lập quy tắc đặt tên thay vì ghi thủ công mọi `ObjectName`.

Spring Framework cung cấp các cơ chế đặt tên như `ObjectNamingStrategy` và những implementation liên quan, gồm `KeyNamingStrategy`, `MetadataNamingStrategy` và `IdentityNamingStrategy`, phù hợp các tình huống khác nhau.

| Strategy | Ý tưởng sử dụng | Điểm cần cân nhắc |
| --- | --- | --- |
| `KeyNamingStrategy` | Dùng key hoặc mapping được cấu hình để tạo `ObjectName` | Cần bảo đảm key phân biệt instance |
| `MetadataNamingStrategy` | Đọc tên từ metadata, ví dụ `@ManagedResource(objectName=...)` | Hai bean cùng metadata cố định có thể bị trùng |
| `IdentityNamingStrategy` | Dùng thông tin identity để phân biệt các instance | Tên có thể thay đổi theo instance/lần khởi chạy, kém ổn định cho dashboard |

Khi bạn cần monitoring automation dựa trên tên ổn định, naming có key nghiệp vụ (`tenant`, `pool`, `name`) thường dễ vận hành hơn các tên phụ thuộc identity runtime.

Không nên cho rằng mọi naming strategy tự động tạo tên ổn định và duy nhất. Hãy kiểm tra strategy được chọn trong exporter, giá trị key truyền vào và `ObjectName` kết quả trong registry.

## 7. Dùng KeyNamingStrategy để phân biệt instance

Khi cần cấu hình tên một cách có kiểm soát, có thể dùng `KeyNamingStrategy` với mapping. Một ví dụ Java configuration:

```java
import java.util.Properties;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

@Bean
public KeyNamingStrategy cacheNamingStrategy() {
    KeyNamingStrategy naming = new KeyNamingStrategy();

    Properties mappings = new Properties();
    mappings.setProperty(
            "primaryCacheMonitor",
            "com.example.cache:type=CacheMonitor,name=primary");
    mappings.setProperty(
            "secondaryCacheMonitor",
            "com.example.cache:type=CacheMonitor,name=secondary");

    naming.setMappings(mappings);
    return naming;
}
```

Nếu exporter sử dụng logical bean keys tương ứng, gắn naming strategy:

```java
exporter.setNamingStrategy(cacheNamingStrategy);
```

Cách này hữu ích khi cấu hình có nhiều key cần ánh xạ sang tên JMX khác nhau. **Tên key mà strategy nhận được phụ thuộc cách exporter chọn và nhận diện bean** (explicit mapping hoặc autodetection); cần đảm bảo cấu hình dùng đúng key tương ứng, thay vì giả định mọi bean sẽ tự sử dụng đúng Spring bean name trong mọi mode.

Với ví dụ chỉ có hai instance, cung cấp `ObjectName` hoàn chỉnh trong `setBeans` vẫn là cách trực quan để học và kiểm soát kết quả.

## 8. Annotation-based export với nhiều instance

Một lớp có thể được đánh dấu `@ManagedResource` để Spring xây dựng metadata quản trị:

```java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(description = "Cache monitor")
public class AnnotatedCacheMonitor {
    private final String name;

    public AnnotatedCacheMonitor(String name) {
        this.name = name;
    }

    @ManagedAttribute
    public String getName() {
        return name;
    }
}
```

Giả sử tạo hai Spring beans:

```java
@Bean("firstAnnotatedMonitor")
public AnnotatedCacheMonitor firstAnnotatedMonitor() {
    return new AnnotatedCacheMonitor("first");
}

@Bean("secondAnnotatedMonitor")
public AnnotatedCacheMonitor secondAnnotatedMonitor() {
    return new AnnotatedCacheMonitor("second");
}
```

Nếu cả hai được annotation exporter phát hiện, exporter phải tạo **hai `ObjectName` khác nhau**. Vì hai instance cùng class và metadata giống nhau, nếu naming strategy chỉ dựa trên tên class hoặc một `objectName` annotation cố định, xung đột có thể xảy ra.

Một cách kiểm soát rõ ràng là xuất tường minh từng object với các tên phân biệt qua exporter cấu hình phù hợp. Một cách khác là dùng naming strategy có định danh bean/instance trong key. Khi dùng annotation metadata và custom naming, đảm bảo assembler và naming strategy được cấu hình đồng bộ.

**Không thể giải quyết trùng `ObjectName` chỉ bằng cách đổi tên `@Bean` nếu naming strategy hoàn toàn bỏ qua tên Spring bean.** Cần kiểm tra tên JMX cuối cùng.

## 9. Một số mô hình đặt tên cho ứng dụng thực tế

### Theo tenant

```text
com.example.platform:type=CacheMonitor,tenant=alpha
com.example.platform:type=CacheMonitor,tenant=beta
```

Thích hợp khi mỗi tenant có một đối tượng độc lập. Nếu tenant identifier có ký tự đặc biệt, phải tạo `ObjectName` hợp lệ và xử lý quote/escape đúng chuẩn.

### Theo pool

```text
com.example.worker:type=ThreadPoolMonitor,pool=io
com.example.worker:type=ThreadPoolMonitor,pool=cpu
com.example.worker:type=ThreadPoolMonitor,pool=scheduler
```

Thích hợp cho các thread pool có cùng API quản trị nhưng khác số lượng thread đang chạy và queue depth.

### Theo datasource

```text
com.example.db:type=DataSourceMonitor,name=primary
com.example.db:type=DataSourceMonitor,name=analytics
```

Thích hợp khi ứng dụng dùng nhiều nguồn dữ liệu và cần phân biệt các pool kết nối.

### Theo role và instance

```text
com.example.messaging:type=ConsumerMonitor,role=orders,instance=0
com.example.messaging:type=ConsumerMonitor,role=orders,instance=1
```

Dùng khi nhiều consumer cùng role tồn tại trong một JVM. Các tên này không mặc định duy nhất trên toàn bộ hệ thống nhiều JVM: `ObjectName` có phạm vi uniqueness theo từng `MBeanServer`, còn kết nối đến JVM nào là trách nhiệm của client hoặc hệ thống giám sát.

Với hệ thống có nhiều replica JVM, dashboard cần bổ sung identity của JVM/host/service ở tầng thu thập metrics, vì hai JVM hoàn toàn có thể đăng ký cùng `ObjectName` mà không xung đột.

## 10. Xử lý xung đột ObjectName

Nếu hai object cùng được đăng ký dưới tên:

```text
com.example.cache:type=CacheMonitor,name=primary
```

MBean server không thể giữ cả hai registration đồng thời. Theo mặc định, exporter thường báo lỗi khi tên đã tồn tại. Các chính sách đăng ký mà Spring cung cấp bao gồm:

- `REGISTRATION_FAIL_ON_EXISTING`: báo lỗi nếu tên đã đăng ký.
- `REGISTRATION_IGNORE_EXISTING`: bỏ qua đăng ký mới khi tên tồn tại.
- `REGISTRATION_REPLACE_EXISTING`: thay thế registration hiện có.

Ví dụ cấu hình:

```java
import org.springframework.jmx.support.MBeanRegistrationSupport;

exporter.setRegistrationBehavior(
        MBeanRegistrationSupport.REGISTRATION_FAIL_ON_EXISTING);
```

Khi ứng dụng cần hai instance đồng thời, **IGNORE** và **REPLACE** không giải quyết nhu cầu giữ hai entry; chúng chỉ thay đổi kết quả xung đột. Cách đúng là tạo tên phân biệt cho từng instance.

Dùng `REPLACE_EXISTING` có thể thay MBean của một thành phần khác mà người vận hành đang theo dõi. Trong các ứng dụng Spring có nhiều `ApplicationContext` dùng chung server, cần xác định owner của từng `ObjectName` và vòng đời unregister.

## 11. Cấu hình nhiều instance bằng XML

Spring Framework hỗ trợ XML bean definitions. Ví dụ sau khai báo hai instance cùng class và một exporter:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="primaryCacheMonitor"
          class="com.example.jmx.CacheMonitor">
        <constructor-arg value="primary"/>
    </bean>

    <bean id="secondaryCacheMonitor"
          class="com.example.jmx.CacheMonitor">
        <constructor-arg value="secondary"/>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">
        <property name="beans">
            <map>
                <entry
                    key="com.example.cache:type=CacheMonitor,name=primary"
                    value-ref="primaryCacheMonitor"/>
                <entry
                    key="com.example.cache:type=CacheMonitor,name=secondary"
                    value-ref="secondaryCacheMonitor"/>
            </map>
        </property>
    </bean>
</beans>
```

Cấu hình này dùng mapping tường minh. Nếu không khai báo `server`, exporter sẽ áp dụng cơ chế tìm `MBeanServer` theo Spring configuration và runtime hiện hành. Khi cần dùng chính platform server để JConsole quan sát, nên cấu hình/inject server rõ ràng.

Cả Java configuration lẫn XML đều cho phép xuất nhiều Spring bean cùng Java type, miễn mỗi registration có `ObjectName` duy nhất.

## 12. Kiểm tra nhiều MBean bằng MBeanServer

Một cách đáng tin cậy để xác minh là truy vấn registry theo pattern:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.cache:type=CacheMonitor,*"),
        null
);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
    System.out.println("LogicalName: "
            + server.getAttribute(name, "LogicalName"));
    System.out.println("HitCount: "
            + server.getAttribute(name, "HitCount"));
}
```

Pattern `type=CacheMonitor,*` cho phép khớp các tên có thêm key properties ngoài `type`, phù hợp khi ứng dụng phân biệt bằng `name` hoặc `tenant`.

Dữ liệu trả về là một tập `ObjectName`; không dựa vào thứ tự iteration để xác định instance primary hay secondary. Dùng property:

```java
String instanceName = name.getKeyProperty("name");
```

để phân biệt hoặc xây dựng mapping cụ thể. Khi in để log/audit, `getCanonicalName()` hữu ích cho hiển thị ổn định các key theo thứ tự chuẩn hóa.

**Lưu ý:** `getPlatformMBeanServer()` trả registry của JVM đang chạy đoạn mã. Nếu gọi từ một JVM client riêng, bạn sẽ thấy registry của client chứ không phải của server ứng dụng. Với remote client, kết nối qua `JMXConnector` để lấy `MBeanServerConnection` đến JVM mục tiêu.

## 13. Kiểm tra bằng JConsole

Sau khi khởi chạy Spring application:

1. Mở JConsole và kết nối đúng JVM theo PID.
2. Chọn tab **MBeans**.
3. Tìm domain `com.example.cache`.
4. Mở cây chứa `type=CacheMonitor,name=primary` và `type=CacheMonitor,name=secondary`.
5. Đọc `LogicalName` và `HitCount` của từng MBean; xác minh hai instance có dữ liệu riêng.
6. Trong môi trường thử nghiệm, gọi `resetStatistics` của primary.
7. Đọc lại `HitCount` ở cả primary và secondary; chỉ primary bị reset.

Nếu hai entry không cùng xuất hiện, kiểm tra xem cả hai bean có được exporter chọn hay không, tên JMX có trùng không, exporter có gặp lỗi khi context khởi tạo không và JConsole có đang kết nối tới đúng server/JVM không.

Một JMX client có thể tổ chức các key thành cây theo thứ tự khác; không suy luận rằng một entry bị thiếu chỉ vì không thấy đúng thứ tự node như ví dụ.

## 14. Kiểm thử tích hợp hai instance trong ApplicationContext

Có thể dùng JUnit Jupiter để xác nhận các đăng ký độc lập:

```java
package com.example.jmx;

import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class MultiInstanceJmxTest {

    @Test
    void registersTwoCacheMonitorsWithSeparateState() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                MultiInstanceJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName primary = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=primary");
            ObjectName secondary = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=secondary");

            assertTrue(server.isRegistered(primary));
            assertTrue(server.isRegistered(secondary));
            assertNotEquals(primary, secondary);

            CacheMonitor first = context.getBean(
                    "primaryCacheMonitor", CacheMonitor.class);
            CacheMonitor second = context.getBean(
                    "secondaryCacheMonitor", CacheMonitor.class);

            first.recordHit();
            first.recordHit();
            second.recordHit();

            assertEquals(2L, server.getAttribute(primary, "HitCount"));
            assertEquals(1L, server.getAttribute(secondary, "HitCount"));

            server.invoke(
                    primary, "resetStatistics",
                    new Object[0], new String[0]);

            assertEquals(0L, server.getAttribute(primary, "HitCount"));
            assertEquals(1L, server.getAttribute(secondary, "HitCount"));

            Set<ObjectName> names = server.queryNames(
                    new ObjectName("com.example.cache:type=CacheMonitor,*"),
                    null);
            assertEquals(Set.of(primary, secondary), names);
        }
    }
}
```

Test này kiểm tra việc exporter đăng ký cả hai instance, đồng thời xác nhận lời gọi JMX tác động đúng object. Khi chạy suite có nhiều test song song, không nên chia sẻ platform MBean server với cùng `ObjectName`. Có thể dùng server riêng cho fixture hoặc domain/instance name riêng của từng test để giảm xung đột.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Chỉ thấy một MBean | Hai bean có cùng `ObjectName`, một bean không được export, hoặc exporter ignore/replace | Kiểm tra mapping, log và `queryNames` |
| `InstanceAlreadyExistsException` | Cùng tên JMX trong cùng server | Bổ sung key phân biệt `name`, `tenant` hoặc `pool` |
| Hai MBean có số liệu giống nhau ngoài ý muốn | Mapping trỏ tới cùng instance Spring | Kiểm tra `@Qualifier` và đối tượng truyền vào `setBeans` |
| `NoUniqueBeanDefinitionException` | Inject theo type khi có nhiều bean cùng class | Dùng `@Qualifier` hoặc inject theo bean name |
| ObjectName hiển thị khác mong đợi | Naming strategy thay tên hoặc chuẩn hóa key order | Đọc `queryNames`, `getCanonicalName` |
| Thêm Spring bean name nhưng vẫn trùng | Strategy dựa trên class/annotation cố định | Sửa naming strategy hoặc mapping JMX |
| MBean biến mất sau khi restart context | Exporter unregister khi đóng context | Hiểu lifecycle, xác minh context đang hoạt động |
| JConsole không tìm thấy cả hai | Sai JVM, MBean server hoặc domain | Đối chiếu PID, `isRegistered`, danh sách server |

## 16. Nguyên tắc thiết kế naming strategy bền vững

1. **Chọn domain rõ ràng:** theo application hoặc subsystem, ví dụ `com.example.cache`.
2. **Chọn type mô tả vai trò:** `type=CacheMonitor`, `type=ThreadPoolMonitor`.
3. **Thêm key phân biệt instance:** `name`, `tenant`, `pool`, `role`, tùy nghiệp vụ.
4. **Dùng identity ổn định khi cần dashboard lâu dài:** tránh phụ thuộc hashcode hoặc instance ID thay đổi qua mỗi lần chạy nếu không có yêu cầu rõ.
5. **Không đưa bí mật hoặc PII vào ObjectName:** tên thường hiển thị trong công cụ quản trị và hệ thống giám sát.
6. **Escape property value đúng chuẩn JMX:** khi giá trị chứa dấu phẩy, dấu bằng, dấu hai chấm hoặc ký tự đặc biệt, dùng API tạo `ObjectName` phù hợp.
7. **Xác định phạm vi uniqueness:** JMX name duy nhất theo từng `MBeanServer`, không tự duy nhất trên nhiều JVM.
8. **Kiểm tra kết quả sau đăng ký:** dùng `isRegistered`, `queryNames` và metadata để xác nhận mỗi instance được export chính xác.

## 17. Bài tập thực hành

**Bài 1 — Hai thread pools.** Tạo `WorkerPoolMonitor` có hai Spring bean `ioPoolMonitor` và `cpuPoolMonitor`. Đăng ký chúng dưới `com.example.worker:type=WorkerPoolMonitor,pool=io` và `pool=cpu`. Xác minh attribute `ActiveCount` độc lập.

**Bài 2 — Xung đột tên.** Cố ý đăng ký hai monitor dưới cùng `com.example.worker:type=WorkerPoolMonitor` trong môi trường test. Ghi nhận lỗi và sửa bằng key `pool`.

**Bài 3 — Naming strategy.** Thay explicit mapping bằng `KeyNamingStrategy` có mappings theo bean keys. Quan sát tên cuối cùng qua `queryNames` rồi so sánh lợi ích và độ phức tạp.

**Bài 4 — Annotation cùng class.** Tạo hai instance của class có `@ManagedResource`. Kiểm tra chúng được exporter chọn như thế nào, thử một tên annotation cố định và giải thích vì sao phải giải quyết trùng `ObjectName`.

**Bài 5 — Nhiều JVM.** Chạy hai tiến trình Java riêng có cùng `ObjectName` và kết nối lần lượt bằng JConsole. Giải thích vì sao không có xung đột nếu hai tiến trình có `MBeanServer` riêng.

## Kết luận

Khi Spring Framework xuất nhiều instance cùng loại bean ra JMX, mỗi object cần **`ObjectName` duy nhất trong cùng `MBeanServer`**. Java class và management interface có thể dùng chung, nhưng Spring bean name và JMX name cần được phân biệt rõ. Sử dụng naming strategy hoặc `MBeanExporter.setBeans` với domain/key properties ổn định giúp các công cụ quản trị nhận diện và gọi chính xác từng instance. Kiểm tra bằng `MBeanServer` và JConsole để xác nhận cả danh tính lẫn trạng thái độc lập của các MBean.
