# Kiểm tra cấu hình hiệu lực từ ApplicationContext trong Spring Framework JMX

## 1. Vì sao không nên chỉ đọc file cấu hình?

Trong Spring Framework, cấu hình JMX có thể được khai báo bằng `@Configuration`, `@Bean`, `@EnableMBeanExport`, XML, auto-configuration của Spring Boot hoặc một tập cấu hình được import từ nhiều module. Khi ứng dụng chạy, điều quan trọng không chỉ là **những gì đã viết trong source**, mà là **những bean và thiết lập nào thực sự tồn tại trong ApplicationContext đã khởi tạo**.

Ví dụ, bạn có thể thấy:

```java
@Configuration
@EnableMBeanExport
class JmxConfig {}
```

nhưng JConsole không thấy MBean dự kiến. Hoặc một bean có `@ManagedResource` nhưng vẫn không xuất hiện vì component scan không tìm thấy nó, một context khác đang được truy vấn, ObjectName bị đổi, exporter không chạy, có xung đột đăng ký, hoặc application đã dùng MBeanServer khác.

**Kiểm tra cấu hình hiệu lực** là truy vấn trạng thái Spring và JMX sau khi context refresh để trả lời các câu hỏi có thể kiểm chứng:

1. Có bao nhiêu `MBeanExporter` / `AnnotationMBeanExporter` trong context?
2. Exporter nào thực sự được dùng, và do context nào sở hữu?
3. Bean quản trị có được đăng ký trong Spring không?
4. `MBeanServer` nào được sử dụng: platform server hay một server khác?
5. ObjectName nào tồn tại trong MBeanServer?
6. Attribute, operation và notification nào được công bố?
7. Có cấu hình profile/property/condition nào làm đường export khác đi so với dự kiến không?

Bài này cung cấp một quy trình quan sát từ **ApplicationContext → bean → exporter → MBeanServer → MBeanInfo**, tránh suy đoán chỉ từ annotation.

## 2. Sơ đồ cấu hình khai báo và cấu hình runtime

```text
application.yml / environment / @Configuration / XML
                         |
                         v
                    BeanFactory
                         |
            conditional / profile / imports
                         |
                         v
                ApplicationContext
                  /       |       \
                 /        |        \
        business bean   exporter   MBeanServer
             |             |            |
             +-------------+------------+
                           |
                  registration attempt
                           |
                           v
                       ObjectName
                           |
                        MBeanInfo
                           |
                    JConsole/client
```

Mỗi mũi tên là một bước có thể có lỗi hoặc sai lệch. Một bean được tạo thành công không đồng nghĩa đã được export; exporter tồn tại không đồng nghĩa nó đã đăng ký đúng tên; ObjectName tồn tại không nhất thiết đại diện cho đúng target bean trong một hệ thống nhiều context.

Cần phân biệt ba tập dữ liệu:

| Nơi kiểm tra | Cho biết | Không tự bảo đảm |
|---|---|---|
| `Environment` / property sources | Các giá trị cấu hình được resolve | Bean đã được tạo theo giá trị đó |
| `ApplicationContext` | Bean, type, scope, lifecycle, nguồn định nghĩa | MBean đã đăng ký JMX |
| `MBeanServer` và `MBeanInfo` | Registration, attribute, operation thực tế | Dependency nghiệp vụ đã healthy |

Chúng bổ sung cho nhau, không thay thế nhau.

## 3. Thực hành tối thiểu: tạo MBean từ Spring

Để minh họa, tạo một bean quản trị rõ ràng:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "lab.spring:type=TaskMonitor,name=primary",
    description = "Task monitor"
)
public class TaskMonitor {
    private final AtomicLong completed = new AtomicLong();
    private volatile int warningThreshold = 100;

    @ManagedAttribute(description = "Completed task count")
    public long getCompleted() {
        return completed.get();
    }

    @ManagedAttribute(description = "Warning threshold")
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @ManagedAttribute
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException("Range: 1..1000");
        }
        warningThreshold = value;
    }

    @ManagedOperation(description = "Reset statistics")
    public void reset() {
        completed.set(0);
    }

    public void recordCompleted() {
        completed.incrementAndGet();
    }
}
```

Bean trên có annotation nhưng cần một cơ chế export phù hợp. Trong Spring Framework thuần:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = TaskMonitor.class)
@EnableMBeanExport
public class LabConfiguration {
}
```

`@ComponentScan` giúp bean được phát hiện trong context. `@EnableMBeanExport` bật hạ tầng annotation-based JMX export. Trong ứng dụng Spring Boot, JMX export còn có thể chịu ảnh hưởng của auto-configuration và `spring.jmx.enabled`; không nên copy đồng thời nhiều cơ chế exporter vào một ứng dụng nếu chúng trùng phạm vi.

Mục tiêu của bước này không phải viết REST API hoặc chạy web server. Chỉ cần một Spring `ApplicationContext` có bean, exporter và MBeanServer phù hợp.

## 4. Kiểm tra một bean có mặt trong ApplicationContext không

Sau khi context khởi tạo:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(LabConfiguration.class)) {

    boolean present = context.containsBean("taskMonitor");
    System.out.println("taskMonitor bean present = " + present);

    String[] names = context.getBeanNamesForType(TaskMonitor.class);
    System.out.println("Bean names = " + java.util.Arrays.toString(names));
}
```

Import:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
```

Hai phép kiểm tra khác nhau:

- `containsBean("taskMonitor")` hỏi liệu context có thể resolve bean theo tên đó (bao gồm khả năng tìm trong hierarchy theo API).
- `getBeanNamesForType(TaskMonitor.class)` tìm các tên bean tương ứng với type qua BeanFactory/type lookup, chịu ảnh hưởng của proxy, FactoryBean và các tùy chọn lookup.

Tên bean do `@Component` sinh theo convention thường là `taskMonitor`, nhưng nếu bạn dùng `@Component("customName")`, khai báo `@Bean` khác hoặc cấu hình naming riêng, tên thật có thể khác. **Không đoán tên bean từ tên class rồi coi đó là bằng chứng.**

Nếu bean không có trong context, việc kiểm tra JMX registration chưa giải quyết được nguyên nhân gốc. Cần xem component scan, `@Import`, profile, conditional configuration và cách context được tạo.

## 5. Tìm các exporter JMX đang có hiệu lực

Spring dùng `MBeanExporter` làm thành phần export cơ bản; `AnnotationMBeanExporter` là biến thể phục vụ annotation metadata.

Có thể liệt kê theo type:

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

Map<String, MBeanExporter> exporters =
    context.getBeansOfType(MBeanExporter.class);

System.out.println("MBeanExporter count = " + exporters.size());
exporters.forEach((name, bean) ->
    System.out.println(name + " -> " + bean.getClass().getName())
);

Map<String, AnnotationMBeanExporter> annotated =
    context.getBeansOfType(AnnotationMBeanExporter.class);

System.out.println(
    "AnnotationMBeanExporter count = " + annotated.size()
);
```

Đây là một bước quan trọng vì ứng dụng có thể xuất hiện nhiều exporter do:

- Một `@EnableMBeanExport` trong cấu hình import.
- Một bean `MBeanExporter` được khai báo thủ công.
- Spring Boot auto-configuration.
- Một module phụ tạo exporter riêng.
- Nhiều `ApplicationContext` độc lập hoặc parent/child.

Nếu có hai exporter cùng đăng ký một ObjectName, quá trình refresh có thể gặp collision, hoặc kết quả phụ thuộc registration policy `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, `REPLACE_EXISTING`.

**Lưu ý:** `getBeansOfType` trong một context có ngữ nghĩa tra cứu type nhất định, không tự động là một kiểm kê toàn bộ exporter ở mọi context khác trong JVM. Với parent/child hoặc nhiều context độc lập, cần khảo sát từng context sở hữu cấu hình phù hợp.

## 6. Đừng nhầm bean đã đăng ký với bean đã khởi tạo

Một `BeanDefinition` có thể tồn tại trước khi singleton được tạo. Lazy bean hoặc scoped bean có thể được instantiate muộn. Vì vậy câu hỏi “cấu hình có bean này không?” khác “instance thực tế đã được tạo và khởi tạo chưa?”.

Ví dụ:

```java
@Lazy
@Component
public class LazyMonitor {
    // ...
}
```

Một bean lazy có thể được Spring đăng ký định nghĩa nhưng chưa tạo instance ngay khi context refresh. Việc exporter có chạm tới bean, có kích hoạt khởi tạo hoặc có đăng ký nó không phụ thuộc cơ chế autodetection/export và cách bean được cấu hình.

Cần biết:

- `containsBeanDefinition` / `getBeanDefinitionNames` cho biết các định nghĩa local khi dùng BeanFactory/ConfigurableApplicationContext phù hợp.
- `getBean(...)` thường lấy bean thực tế và **có thể kích hoạt khởi tạo**.
- `getBeansOfType(...)` có thể tác động đến eager initialization tùy API overload và loại FactoryBean.
- Một singleton đã được tạo không đồng nghĩa external dependency của nó đã READY.

Khi chẩn đoán startup, ưu tiên đọc metadata và log lifecycle trước khi chủ động gọi `getBean` với bean lazy vì thao tác điều tra có thể thay đổi trạng thái mà bạn muốn quan sát.

## 7. Xác định đúng MBeanServer đang được dùng

Một trong những nguyên nhân phổ biến khiến JConsole không thấy MBean là exporter đăng ký vào một MBeanServer khác với MBeanServer mà công cụ đang đọc.

JDK cung cấp platform server:

```java
MBeanServer platformServer =
    ManagementFactory.getPlatformMBeanServer();
```

Spring cũng hỗ trợ tạo hoặc tra cứu server qua `MBeanServerFactoryBean`, `MBeanServerFactory` hoặc một bean `MBeanServer` do ứng dụng khai báo.

Liệt kê server beans trong context:

```java
import javax.management.MBeanServer;
import java.util.Map;

Map<String, MBeanServer> servers =
    context.getBeansOfType(MBeanServer.class);

servers.forEach((name, server) -> {
    System.out.println(
        "MBeanServer bean=" + name +
        ", identity=" + System.identityHashCode(server) +
        ", defaultDomain=" + server.getDefaultDomain()
    );
});
```

`System.identityHashCode` là chỉ số phục vụ debug trong process; nó không phải định danh bền vững hoặc bảo đảm độc nhất tuyệt đối. `getDefaultDomain()` cũng không phân biệt tất cả server.

So sánh object reference nếu phù hợp:

```java
boolean same =
    serverBean == ManagementFactory.getPlatformMBeanServer();
System.out.println("Using platform server bean = " + same);
```

**Quan trọng:** việc có một `MBeanServer` bean trong context không chứng minh mọi exporter đều dùng nó. Nếu exporter được cấu hình explicit bằng `setServer(...)`, hoặc tự tìm một server khác, cần kiểm tra cấu hình thực tế và registration tại đúng registry.

## 8. Truy vấn ObjectName: bằng chứng thực tế của registration

Với đúng `MBeanServer`, dùng:

```java
import javax.management.ObjectName;

ObjectName expected = new ObjectName(
    "lab.spring:type=TaskMonitor,name=primary"
);

System.out.println(
    "Registered = " + server.isRegistered(expected)
);
```

Hoặc liệt kê một domain:

```java
for (ObjectName name : server.queryNames(
        new ObjectName("lab.spring:*"), null)) {
    System.out.println("MBean: " + name);
}
```

Dùng `queryNames` tốt hơn suy luận từ bean name, vì ObjectName có thể đến từ:

- `@ManagedResource(objectName = "...")`.
- Explicit bean mapping của `MBeanExporter.setBeans(...)`.
- `ObjectNamingStrategy`.
- Một cách đặt tên theo bean key hoặc domain.
- Một MBean đã được module khác đăng ký.

Một MBean đã tồn tại trong registry cũng **không tự chứng minh exporter mà bạn đang kiểm tra đã đăng ký nó**. Trong hệ thống có nhiều context, một exporter khác có thể đứng sau cùng ObjectName hoặc registration policy đã giữ/thay đối tượng trước đó.

Để kiểm tra danh tính, cần kết hợp registration với metadata, hành vi attribute và log sở hữu exporter.

## 9. Dùng MBeanInfo để đối chiếu hợp đồng quản trị

Sau khi xác nhận ObjectName tồn tại:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(expected);

System.out.println("MBean class: " + info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OP " + operation.getName());
}
```

Với ví dụ `TaskMonitor`, dự kiến thấy các attribute như `Completed`, `WarningThreshold` và operation `reset`, nếu annotation metadata assembler/exporter được cấu hình phù hợp. Phương thức `recordCompleted()` không được đánh dấu để export nên không nằm trong giao diện quản trị annotation-based được dự định.

`MBeanInfo.getClassName()` với Spring ModelMBean có thể phản ánh lớp ModelMBean/wrapper thay vì class nghiệp vụ gốc. Vì vậy không nên dùng riêng className trong metadata để kết luận ownership.

Đọc `MBeanInfo` là một kiểm tra an toàn hơn việc lấy tất cả attribute value, đặc biệt nếu MBean có thể chứa dữ liệu nhạy cảm. **Không dump toàn bộ giá trị JMX chỉ để kiểm kê**, vì điều đó có thể làm lộ token, credential, cấu hình hoặc dữ liệu người dùng.

## 10. Xem cấu hình hiệu lực từ Environment

Spring `Environment` kết hợp các property sources theo thứ tự ưu tiên. Với một property:

```java
import org.springframework.core.env.Environment;

Environment env = context.getEnvironment();

String value = env.getProperty("spring.jmx.enabled");
System.out.println("spring.jmx.enabled = " + value);
```

Đây là ví dụ phù hợp với **Spring Boot** khi ứng dụng sử dụng property đó. Trong Spring Framework thuần, property tên `spring.jmx.enabled` không tự động điều khiển `@EnableMBeanExport` trừ khi bạn viết cấu hình đọc property tương ứng.

Điều cần phân biệt:

- `Environment.getProperty(...)` trả **giá trị đã resolve** theo nguồn property.
- Sự tồn tại của property không chứng minh nó đã được một auto-configuration áp dụng.
- Một property có thể bị bỏ qua do condition/profile/version.
- Một exporter thủ công có thể hoạt động ngay cả khi property auto-configuration không có ý nghĩa với nó.

Vì thế, câu hỏi “JMX đang bật không?” không thể trả lời chỉ bằng một giá trị `Environment`. Phải kiểm tra exporter bean và MBean registry.

### 10.1. Không in secret khi debug property sources

`Environment` có thể chứa password, token, URI có credential hoặc thông tin nội bộ. Tránh in toàn bộ property keys/values vào stdout hoặc một JMX attribute. Khi cần xác định nguồn một property, log tên và nguồn cấu hình không nhạy cảm, dùng masking/redaction phù hợp; không ghi giá trị bí mật.

## 11. Profile và conditional configuration

Spring có thể bật/tắt bean dựa trên `@Profile`, `@Conditional`, `@ConditionalOnProperty` trong Boot hoặc các condition khác.

Ví dụ:

```java
@Configuration
@Profile("ops")
@EnableMBeanExport
public class OpsJmxConfiguration {
}
```

Nếu profile `ops` không active, configuration này không được áp dụng như bạn dự tính. Có thể kiểm tra:

```java
String[] profiles = context.getEnvironment().getActiveProfiles();
System.out.println(
    "Active profiles = " + java.util.Arrays.toString(profiles)
);
```

Nhưng `getActiveProfiles()` chỉ cho biết profile active, không tự xác nhận bean exporter đã được tạo. Phải tiếp tục kiểm tra theo type.

Với Spring Boot, condition evaluation report và Actuator endpoints có thể hỗ trợ chẩn đoán, nếu được cấu hình và bảo vệ đúng cách. Không tự mở endpoints quản trị ra mạng công khai. Trong Spring Framework thuần, hãy dựa vào bean definitions, logs và runtime inspection của context.

## 12. Parent/child ApplicationContext và nhiều context độc lập

Một ứng dụng web Spring truyền thống có thể có root context và child servlet context. Một ứng dụng modular có thể có nhiều context độc lập trong cùng JVM.

```text
Root ApplicationContext
    +-- business services
    +-- exporter A

Child WebApplicationContext
    +-- controllers
    +-- exporter B

Cả hai có thể trỏ tới cùng platform MBeanServer.
```

Kiểm tra một context không có nghĩa đã kiểm tra mọi context. Các bean trong parent có thể được child nhìn thấy theo cơ chế lookup, còn parent không tự nhìn thấy bean child. Hơn nữa, một `getBeansOfType` thông thường không phải luôn là phép tìm kiếm xuyên toàn bộ hierarchy.

Nếu cần liệt kê bean theo hierarchy, Spring có `BeanFactoryUtils.beansOfTypeIncludingAncestors(...)`, với lưu ý về việc bean local có thể che bean parent theo tên. Nhưng khi mục tiêu là ownership exporter, nên kiểm tra **từng context** để biết bean nào thuộc context nào.

Trường hợp nhiều context độc lập, cần có tham chiếu thực tế đến từng context; không có một API global mặc định cho mọi ApplicationContext trong JVM.

Khi cả hai exporter đăng ký cùng `ObjectName` vào một server, registration policy ảnh hưởng kết quả. Vì vậy “JMX hoạt động ở context A” không chứng minh MBean của context B đã export đúng.

## 13. Cấu hình @EnableMBeanExport và exporter thủ công

Spring cho phép bật annotation export:

```java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
```

Hoặc tạo exporter riêng:

```java
@Bean
public MBeanExporter mBeanExporter(
        MBeanServer server,
        TaskMonitor taskMonitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(java.util.Map.of(
        "lab.spring:type=TaskMonitor,name=primary",
        taskMonitor
    ));
    return exporter;
}
```

Hai cách có thể phục vụ nhu cầu khác nhau. Nếu cùng tồn tại và cùng đăng ký một ObjectName, có thể xảy ra collision, bị bỏ qua hoặc thay thế tùy `RegistrationPolicy`.

Kiểm tra hiệu lực phải trả lời:

1. Cơ chế export nào có mặt trong context?
2. Có bao nhiêu exporter thực sự khởi tạo?
3. Mỗi exporter chọn bean bằng annotation, autodetect hay explicit mapping?
4. ObjectName đích có trùng với exporter khác không?
5. Chúng cùng sử dụng MBeanServer nào?

Một bean được export bởi exporter thủ công có thể không cần `@ManagedResource` nếu đó là Standard MBean/JMX-compliant object hoặc được cấu hình assembler phù hợp. Ngược lại, annotation có thể không có tác dụng nếu không có cơ chế metadata export tương ứng.

## 14. MBeanExporter và RegistrationPolicy

Một `ObjectName` phải duy nhất trong một MBeanServer. Spring `RegistrationPolicy` quyết định cách xử lý khi tên đã có:

| Policy | Ý nghĩa chính |
|---|---|
| `FAIL_ON_EXISTING` | Báo lỗi khi registration đụng tên đã tồn tại |
| `IGNORE_EXISTING` | Giữ MBean hiện có, bỏ qua registration mới |
| `REPLACE_EXISTING` | Thay registration hiện có theo cơ chế exporter |

Ví dụ:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Khi `IGNORE_EXISTING`, context có thể start thành công mà MBean đang nhìn thấy thuộc module cũ. Khi `REPLACE_EXISTING`, metadata và state có thể thay đổi dưới cùng ObjectName. Vì vậy, để kiểm tra “cấu hình hiệu lực”, không chỉ đếm bean exporter mà phải đọc registry và hành vi sau registration.

Hãy định nghĩa ownership ObjectName rõ ràng; không dùng policy để che các lỗi đặt tên trong hệ thống nhiều context.

## 15. Mẫu chẩn đoán có thể dùng trong startup

Một cách tiện lợi là tạo component chẩn đoán chạy sau khi context refresh, in **metadata không nhạy cảm**.

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

public final class JmxDiagnostics {

    public static void inspect(ConfigurableApplicationContext context)
            throws Exception {

        System.out.println("Context id: " + context.getId());
        System.out.println("Active profiles: " + Arrays.toString(
            context.getEnvironment().getActiveProfiles()
        ));

        Map<String, MBeanExporter> exporters =
            context.getBeansOfType(MBeanExporter.class);

        System.out.println("Exporters: " + exporters.keySet());

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        for (ObjectName name : server.queryNames(
                new ObjectName("lab.spring:*"), null)) {
            System.out.println("Registered MBean: " + name);
        }
    }
}
```

Gọi sau khi context đã được refresh:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(LabConfiguration.class)) {

    JmxDiagnostics.inspect(context);
}
```

`AnnotationConfigApplicationContext` cần import từ `org.springframework.context.annotation`. Đây là công cụ kiểm tra **platform MBeanServer**; nếu exporter sử dụng một server khác, phải truyền đúng server vào diagnostics thay vì chỉ dùng platform server.

Nếu cần áp dụng trong ứng dụng, nên dùng logger ở mức debug phù hợp, không in quá nhiều thông tin nhạy cảm hoặc danh sách toàn bộ system properties.

## 16. Xác nhận bằng một thao tác JMX thực tế

Khi đã xác định đúng MBean, có thể đọc một attribute vận hành không nhạy cảm:

```java
ObjectName name = new ObjectName(
    "lab.spring:type=TaskMonitor,name=primary"
);

Object completed = server.getAttribute(name, "Completed");
System.out.println("Completed = " + completed);
```

Nếu attribute tồn tại và có thể đọc, bạn xác nhận được nhiều hơn `isRegistered`: JMX thực sự định tuyến lời gọi tới MBean.

Với operation có tác dụng phụ như `reset()`, không nên gọi chỉ để “test” trong production. Có thể thực hiện ở môi trường test hoặc xây dựng một operation đọc/trả trạng thái phù hợp. Mục tiêu kiểm tra cấu hình không phải thay đổi dữ liệu thật.

Nếu `getAttribute` lỗi, cần phân biệt:

- ObjectName sai hoặc MBean bị unregister.
- Attribute không tồn tại/không readable.
- Getter phát exception.
- Bean target chưa READY.
- Caller không có quyền truy cập.
- Đang truy vấn MBeanServer khác.

## 17. Spring Boot: condition report và Actuator

Trong Spring Boot, có thể có thêm công cụ để kiểm tra cấu hình hiệu lực:

- Condition evaluation report cho biết auto-configuration nào match hoặc không match điều kiện.
- `/actuator/beans` có thể giúp xem bean definitions/quan hệ nếu endpoint được bật.
- `/actuator/conditions` có thể giúp xem điều kiện auto-configuration.
- `/actuator/env` hoặc `/actuator/configprops` có thể hiển thị cấu hình nhưng phải được bảo vệ và sanitization đúng.
- `spring.jmx.enabled` là cấu hình thường gặp để điều khiển JMX export của Boot.

Không dựa vào Actuator như nguồn duy nhất. Endpoint có thể bị tắt, khác version, hoặc không phản ánh đầy đủ registration trong MBeanServer. **ApplicationContext inspection và JMX registry inspection phải được kết hợp.**

Actuator chứa khả năng quan sát mạnh; đừng công khai những endpoint có thể tiết lộ môi trường hoặc cấu hình. Nếu tổ chức đã có policy bảo mật, tuân theo policy đó thay vì tự bật mọi actuator endpoint để debug.

## 18. Những lỗi phổ biến khi kiểm tra cấu hình hiệu lực

### 18.1. “Tôi thấy @ManagedResource trong code nên MBean chắc đã có”

Không đúng. Bean có thể không được component scan hoặc exporter metadata chưa hoạt động. Kiểm tra context trước, rồi registry.

### 18.2. “Tôi thấy một MBeanExporter bean nên mọi MBean phải xuất hiện”

Exporter tồn tại không bảo đảm nó chọn đúng bean, naming strategy tạo đúng tên hoặc registration thành công. Đọc `queryNames` và `MBeanInfo`.

### 18.3. “JConsole không thấy MBean nên bean không tồn tại”

Có thể JConsole kết nối nhầm JVM, sai MBeanServer hoặc chưa refresh UI. Tách kiểm tra Spring bean khỏi JMX registration.

### 18.4. “Environment trả spring.jmx.enabled=true là đủ”

Trong Spring Boot, property có thể liên quan auto-configuration; trong Spring Framework thuần nó không tự bật JMX export. Kiểm tra bean exporter và condition thực tế.

### 18.5. “Tôi dùng getBeansOfType nên đã tìm tất cả exporter của mọi context”

Không đúng trong ứng dụng nhiều context. Phải biết context/hierarchy nào đang được kiểm tra, tránh nhầm bean parent/child và module độc lập.

### 18.6. “MBean hiện diện nên service đã READY”

MBean có thể export trước khi background initialization hoàn tất. Getter nên cho biết `STARTING`/`READY` khi cần; operation có side effect phải tự guard.

### 18.7. “MBeanInfo className chính là target bean”

Với ModelMBean/wrapper, className có thể là lớp adapter. Sử dụng kết hợp metadata, ObjectName, nguồn bean và log exporter.

### 18.8. “Tôi sẽ gọi mọi operation để xem có hoạt động không”

Đây là cách kiểm tra nguy hiểm. Operation có thể restart worker, clear cache hoặc reset counter. Chỉ đọc metadata và attribute an toàn trong production.

### 18.9. “Có hai exporter nhưng không có lỗi nên không sao”

Một exporter có thể dùng IGNORE_EXISTING, hoặc hai exporter chọn các MBean khác nhau. Kiểm tra ObjectName thực tế và ownership; không suy luận từ số lượng bean đơn thuần.

## 19. Quy trình kiểm tra từng bước

Áp dụng tuần tự khi một MBean Spring không xuất hiện hoặc hoạt động khác mong đợi:

1. **Xác định JVM và context:** process/PID nào đang chạy, root hay child context nào cần kiểm tra?
2. **Xác định profile/property:** active profiles và property liên quan có đúng không?
3. **Kiểm tra bean quản trị:** bean definition và instance có thuộc context không?
4. **Kiểm tra exporter:** có bean `MBeanExporter`/annotation exporter không, có nhiều exporter không?
5. **Kiểm tra MBeanServer:** exporter dùng registry nào; platform hay server riêng?
6. **Kiểm tra ObjectName:** MBean được đăng ký ở tên nào?
7. **Kiểm tra MBeanInfo:** attribute/operation có khớp contract không?
8. **Đọc một attribute an toàn:** xác minh call runtime đi qua JMX được.
9. **Kiểm tra lifecycle và collision:** có context khác, registration policy, lazy startup hoặc proxy không?
10. **Ghi lại phát hiện:** tên bean, context ID, ObjectName và exception phù hợp; tránh in secret.

Quy trình này giúp thu hẹp nguyên nhân theo từng lớp thay vì thay đổi tùy tiện nhiều cấu hình cùng lúc.

## 20. Bài tập thực hành

**Bài 1 — Context và exporter.** Tạo context với `@EnableMBeanExport` và một bean `@ManagedResource`. In tên các bean `MBeanExporter`, xác nhận ObjectName bằng `isRegistered`, sau đó liệt kê attribute của `MBeanInfo`.

**Bài 2 — Sai component scan.** Đưa `TaskMonitor` ra ngoài package được scan, khởi động context rồi quan sát sự khác nhau giữa “bean không có” và “exporter có nhưng không có resource để xuất”. Sau đó sửa component scan.

**Bài 3 — Hai MBeanServer.** Tạo server A và B trong JVM test; export MBean vào A nhưng truy vấn B. Ghi nhận kết quả, sau đó truyền đúng server vào diagnostics. Giải thích tại sao cùng JVM vẫn có thể có nhiều registry.

**Bài 4 — Profile thay đổi.** Đặt `@Profile("ops")` lên cấu hình JMX. Chạy với và không với profile, so sánh `getActiveProfiles()`, exporter beans và ObjectNames.

**Bài 5 — Duplicate ObjectName.** Tạo hai exporter cùng muốn đăng ký một ObjectName trong môi trường test. Quan sát `FAIL_ON_EXISTING` và `IGNORE_EXISTING`, ghi nhận bean nào thực sự được JMX nhìn thấy.

**Bài 6 — Spring Boot condition.** Trong một ứng dụng Boot có Actuator được bảo vệ, so sánh condition evaluation của JMX export với `spring.jmx.enabled`, bean exporter và `MBeanInfo` thực tế.

**Bài 7 — Metadata thay vì dump values.** Viết diagnostics chỉ log tên và quyền đọc/ghi của attribute. Giải thích tại sao không nên tự động gọi `getAttribute` cho mọi field khi có thể chứa secret.

## 21. Câu hỏi tự kiểm tra

1. Vì sao đọc file `@Configuration` chưa đủ để kết luận JMX hoạt động?
2. `getBeansOfType(MBeanExporter.class)` cho biết điều gì và có giới hạn nào?
3. Một bean có `@ManagedResource` nhưng không có trong context thì có thể được exporter chọn không?
4. `MBeanServer` bean trong context có luôn là registry exporter dùng không?
5. `queryNames` và `isRegistered` cung cấp bằng chứng gì?
6. Vì sao `MBeanInfo.getClassName()` không phải lúc nào cũng là business bean class?
7. Spring Framework thuần có tự hiểu `spring.jmx.enabled` không?
8. Parent/child context ảnh hưởng việc tìm exporter như thế nào?
9. Nếu một ObjectName có MBean rồi, làm sao biết nó đại diện đúng đối tượng dự kiến?
10. Vì sao kiểm tra metadata an toàn hơn gọi thử mọi operation?

## 22. Ghi nhớ

**Cấu hình hiệu lực của Spring JMX là kết quả thực tế của ApplicationContext và MBeanServer sau khi khởi tạo**, không chỉ là annotation hoặc property đã viết. Hãy lần theo chuỗi `Environment → bean → exporter → MBeanServer → ObjectName → MBeanInfo`, kiểm tra đúng context, đúng registry và đúng hợp đồng quản trị.

Một cách chẩn đoán tốt luôn tách việc bean đã tồn tại trong Spring khỏi việc MBean đã được đăng ký trong JMX, tránh dump secret và không gọi operation có tác dụng phụ chỉ để kiểm tra cấu hình. Khi dùng nhiều context hoặc exporter, ownership và registration policy phải được xác định rõ để dữ liệu giám sát phản ánh đúng ứng dụng.
