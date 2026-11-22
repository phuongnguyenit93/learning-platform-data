# Đặt defaultDomain theo môi trường triển khai trong Spring Framework JMX

## 1. Mục tiêu

JMX (Java Management Extensions) định danh mỗi MBean bằng một `ObjectName` có cấu trúc `domain:key=value`. Trong ứng dụng Spring Framework, `MBeanExporter` lựa chọn những bean cần export và đăng ký vào `MBeanServer`; cơ chế đặt tên có thể xuất phát từ map explicit, annotation `@ManagedResource`, `ObjectNamingStrategy` hoặc quy tắc JMX.

**defaultDomain** thường được hiểu là domain mặc định dùng khi một tên MBean không chỉ định domain đầy đủ. Đây là một thiết lập có tác động tới tên đăng ký cuối cùng, do đó ảnh hưởng trực tiếp tới JConsole, VisualVM, JMX proxy, monitoring và script vận hành.

Đề bài này cần làm rõ:

- Default domain của **MBeanServer** khác gì với domain do **Spring naming strategy** tạo?
- Vì sao có thể cần domain khác nhau giữa local, development, staging và production?
- Cách lấy giá trị từ environment và áp dụng nhất quán cho exporter/MBeanServer.
- Khi nào **không nên** đưa tên môi trường vào domain?
- Cách tránh xung đột ObjectName và tránh phá vỡ dashboard/client đang dùng tên cũ.

**Nguyên tắc trước tiên:** không có một thuộc tính `defaultDomain` duy nhất, có thể áp dụng tùy ý cho mọi `MBeanExporter`, mọi naming strategy và mọi MBeanServer mà không cần xét cấu hình. Phải xác định **thành phần nào thực sự sở hữu default domain** và ObjectName cuối cùng được sinh ra theo đường nào.

## 2. Domain và ObjectName

Cú pháp chuẩn:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.orders:type=Queue,name=Pending
com.example.cache:type=CacheMonitor,name=Primary
java.lang:type=Memory
```

Trong `com.example.orders:type=Queue,name=Pending`:

- `com.example.orders` là domain, tạo namespace logic.
- `type=Queue` mô tả loại MBean theo quy ước của ứng dụng.
- `name=Pending` phân biệt một MBean cụ thể.
- Toàn bộ ObjectName phải duy nhất trong **một** MBeanServer tại thời điểm đăng ký.

Domain là **namespace logic**, không phải hostname, địa chỉ mạng, Spring profile hay tên ApplicationContext. Chúng ta có thể dùng thông tin môi trường để đặt domain, nhưng đó là một quyết định thiết kế naming contract, không phải ngữ nghĩa bắt buộc của JMX.

Ví dụ các môi trường:

```text
com.example.orders.dev:type=Queue,name=Pending
com.example.orders.staging:type=Queue,name=Pending
com.example.orders.prod:type=Queue,name=Pending
```

Cách khác là domain ổn định, môi trường nằm ở key property:

```text
com.example.orders:environment=dev,type=Queue,name=Pending
com.example.orders:environment=staging,type=Queue,name=Pending
com.example.orders:environment=prod,type=Queue,name=Pending
```

Hai chiến lược có thể cùng hợp lệ; chọn một và duy trì nhất quán. Không đổi ngầm giữa hai chiến lược sau khi dashboard/client đã bắt đầu dùng.

## 3. Default domain của MBeanServer

`MBeanServer` có một default domain. API `getDefaultDomain()` trả về chuỗi domain mặc định của server:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

System.out.println(server.getDefaultDomain());
```

Default domain được sử dụng trong một số trường hợp tên đối tượng được đăng ký có domain rỗng. Với tên chỉ định domain đầy đủ, ví dụ `com.example.orders:type=Queue`, server không tự thay domain thành giá trị mặc định.

Ví dụ tư duy:

```text
Server default domain: com.example.management

ObjectName explicit:
  com.example.orders:type=Queue
  -> Giữ com.example.orders

ObjectName empty domain:
  :type=Queue
  -> Khi đăng ký, server có thể áp dụng default domain của mình
```

Điều này phân biệt **default domain của JMX server** với việc bạn tự viết code sinh ObjectName từ một prefix cấu hình. `MBeanServer.getDefaultDomain()` không phải một property mà việc sửa Spring environment sau startup sẽ tự thay đổi được.

### Tạo MBeanServer với default domain riêng

JMX API cho phép tạo server và chỉ định default domain:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server = MBeanServerFactory.createMBeanServer(
    "com.example.orders.dev"
);

System.out.println(server.getDefaultDomain());
// com.example.orders.dev
```

Hoặc trong Spring, `MBeanServerFactoryBean` có khả năng tạo mới hoặc tìm một server phù hợp. Cần hiểu rõ cấu hình tạo/tìm server thực tế và không mặc định rằng `setDefaultDomain` sẽ sửa một **platform MBeanServer đã tồn tại**.

## 4. Vì sao defaultDomain cần xem xét theo môi trường?

Một số hệ thống chạy nhiều application context hoặc module trong cùng JVM/MBeanServer. Nếu chúng đăng ký các MBean tên chung:

```text
app:type=Cache,name=Main
```

thì hai module có thể xung đột. Một domain có ngữ nghĩa rõ ràng giúp tách namespace:

```text
com.example.billing.dev:type=Cache,name=Main
com.example.shipping.dev:type=Cache,name=Main
```

Tuy nhiên môi trường dev/staging/prod thường chạy ở **các JVM khác nhau**. Hai JVM độc lập có thể dùng cùng ObjectName mà không xung đột. Trong trường hợp này, việc thay domain theo profile không phải yêu cầu để tránh trùng; nó chỉ phục vụ quản trị, truy vấn hoặc phân biệt khi công cụ tập trung dữ liệu từ nhiều kết nối.

Vì vậy cần hỏi:

1. Những ứng dụng nào thực sự **chia sẻ một MBeanServer**?
2. Monitoring có dùng ObjectName cố định cho nhiều môi trường không?
3. Tên domain được dùng để phân biệt app, module hay deployment?
4. Có cần một dashboard chung chạy không đổi query giữa dev/staging/prod không?
5. Hạ tầng đã có nhãn `environment`, `instance`, `cluster` ở bên ngoài JMX chưa?

Nếu telemetry pipeline đã gắn environment từ kết nối/collector, giữ domain JMX ổn định có thể giúp dashboard tái sử dụng thuận lợi hơn.

## 5. Default domain và ObjectName trong Spring

Spring có nhiều đường tạo tên:

```text
Spring bean
   |
   +-- MBeanExporter.setBeans(...)
   |     -> map key / naming strategy
   |
   +-- @ManagedResource(objectName = "...")
   |     -> Annotation metadata + MetadataNamingStrategy
   |
   +-- KeyNamingStrategy / custom ObjectNamingStrategy
   |     -> sinh ObjectName từ key, class hoặc metadata
   |
   v
ObjectName cuối cùng
   |
   v
MBeanServer.registerMBean
```

Nếu `@ManagedResource(objectName=...)` đã chỉ rõ domain, default domain của server không ghi đè tên đó. Tương tự, nếu map `beans` chứa key là ObjectName đầy đủ, server vẫn dùng domain explicit.

Vì vậy khi muốn đặt domain theo môi trường, **nên thiết kế naming strategy sinh ObjectName theo môi trường hoặc chủ động cấu hình tên đầy đủ**. Chỉ thay default domain của MBeanServer sẽ không ảnh hưởng các ObjectName explicit.

## 6. Cấu hình môi trường với Spring Environment

Giả sử ứng dụng chọn tên domain theo environment. Một cấu hình có thể đặt property:

```properties
# application-dev.properties
management.jmx.domain=com.example.orders.dev
```

```properties
# application-staging.properties
management.jmx.domain=com.example.orders.staging
```

```properties
# application-prod.properties
management.jmx.domain=com.example.orders.prod
```

Đây là **property ứng dụng do ví dụ tự định nghĩa**, không phải tên property mặc định được Spring Framework tự động dùng để đổi domain của mọi JMX MBean. Đừng nhầm với các thuộc tính JMX/Actuator riêng của Spring Boot.

Trong Java config có thể đọc từ `Environment`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class JmxDomainConfig {
    @Bean
    public JmxDomainSettings jmxDomainSettings(Environment env) {
        String domain = env.getRequiredProperty(
            "management.jmx.domain"
        );
        return new JmxDomainSettings(domain);
    }
}

public record JmxDomainSettings(String domain) {}
```

Đoạn trên chỉ lấy domain và đóng gói cấu hình. Cần thêm bước đưa giá trị đó vào **cơ chế sinh ObjectName** hoặc việc tạo mới MBeanServer. Nếu chỉ tạo `JmxDomainSettings` mà không dùng ở exporter/naming strategy, tên MBean sẽ không thay đổi.

## 7. Phương án 1: sinh ObjectName đầy đủ từ property

Đây là cách đơn giản, dễ dự đoán khi quản lý một số MBean explicit:

```java
import java.util.Map;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ExplicitJmxNamesConfiguration {
    @Bean
    public MBeanExporter mbeanExporter(
            QueueManagement queueManagement,
            JmxDomainSettings settings) throws Exception {

        ObjectName name = new ObjectName(
            settings.domain() + ":type=Queue,name=Pending"
        );

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(name.toString(), queueManagement));
        return exporter;
    }
}
```

Trong ví dụ, `QueueManagement` là management adapter do ứng dụng cung cấp, có hợp đồng JMX phù hợp. Domain lấy từ property triển khai, và ObjectName được tạo trước khi đăng ký. Cách này cho phép fail-fast nếu chuỗi domain không hợp lệ.

Cần lưu ý: nối domain từ property chỉ an toàn khi giá trị property đã được kiểm soát. `ObjectName.quote` chỉ dùng cho **value của key property**, không dùng để quote toàn bộ domain. Domain cần được validate theo chính sách naming của tổ chức (ví dụ chỉ cho phép chữ, số, dấu chấm hoặc dấu gạch dưới theo quy ước).

### Dùng `@Value` cho cấu hình ngắn

```java
@Bean
public MBeanExporter exporter(
        QueueManagement queueManagement,
        @Value("${management.jmx.domain}") String domain)
        throws Exception {
    ObjectName name = new ObjectName(
        domain + ":type=Queue,name=Pending"
    );
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(name.toString(), queueManagement));
    return exporter;
}
```

Đây cũng là **naming explicit**: không nhất thiết thay default domain của `MBeanServer`. Nó thường là điều ứng dụng thực sự cần khi nói “đặt domain JMX theo môi trường”.

## 8. Phương án 2: custom ObjectNamingStrategy

Khi có nhiều MBean, thay vì ghép chuỗi ở mỗi `setBeans`, có thể viết `ObjectNamingStrategy` để tập trung quy ước:

```java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class EnvironmentObjectNamingStrategy
        implements ObjectNamingStrategy {

    private final String domain;

    public EnvironmentObjectNamingStrategy(String domain) {
        this.domain = domain;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        return new ObjectName(
            domain + ":type=Component,name=" + ObjectName.quote(beanKey)
        );
    }
}
```

Giả sử các key của exporter là `queuePrimary` và `cachePrimary`, naming strategy sinh:

```text
com.example.orders.dev:type=Component,name="queuePrimary"
com.example.orders.dev:type=Component,name="cachePrimary"
```

Value được quote sẽ là literal quoted value; nếu cần pattern query, client phải tương thích với biểu diễn value đó. Đặt `type=Component` chỉ là ví dụ, trong production nên chọn key `type` phản ánh loại MBean rõ hơn.

Cấu hình:

```java
@Bean
public MBeanExporter exporter(
        QueueManagement queueManagement,
        CacheManagement cacheManagement,
        JmxDomainSettings settings) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "queuePrimary", queueManagement,
        "cachePrimary", cacheManagement
    ));
    exporter.setNamingStrategy(
        new EnvironmentObjectNamingStrategy(settings.domain())
    );
    return exporter;
}
```

Ưu điểm: quy tắc tập trung và dễ đảm bảo tất cả MBean do exporter này đăng ký theo cùng namespace. Giới hạn: naming strategy này áp dụng cho các bean do exporter tương ứng xử lý; nó không tự đổi tên MBean được subsystem khác đăng ký.

## 9. Phương án 3: tạo MBeanServer với default domain riêng

Nếu thực sự cần default domain cấp server, có thể tạo mới `MBeanServer`:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DedicatedMBeanServerConfiguration {
    @Bean
    public MBeanServer dedicatedMBeanServer(
            JmxDomainSettings settings) {
        return MBeanServerFactory.createMBeanServer(settings.domain());
    }
}
```

Và inject **chính MBeanServer đó** vào exporter:

```java
@Bean
public MBeanExporter exporter(
        MBeanServer dedicatedMBeanServer,
        QueueManagement queueManagement) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(dedicatedMBeanServer);
    exporter.setBeans(Map.of(
        ":type=Queue,name=Pending", queueManagement
    ));
    return exporter;
}
```

Trong ví dụ, key có domain rỗng để minh họa cách server default domain được áp dụng khi đăng ký. Nhưng cần xác nhận `ObjectNamingStrategy` và exporter thực tế xử lý key theo cách dự kiến; với cấu hình thực tiễn, explicit ObjectName đầy đủ thường dễ kiểm soát hơn.

Không mặc định một MBeanServer mới sẽ xuất hiện trong JConsole kết nối platform server. Nếu dùng server riêng, cần thiết lập client/proxy/connector trỏ đúng server. Việc thêm server làm tăng độ phức tạp, nên chỉ chọn khi có nhu cầu cô lập registry hoặc đặc tính server-level rõ ràng.

## 10. Spring Boot: phân biệt cấu hình của Framework và Boot

Trong hệ sinh thái Spring, cần phân biệt:

- **Spring Framework JMX**: `MBeanExporter`, `@EnableMBeanExport`, `ObjectNamingStrategy`, `MetadataNamingStrategy`, `@ManagedResource`.
- **Spring Boot**: auto-configuration/Actuator có thể có các properties JMX riêng để điều khiển exposure, domain của endpoint hoặc ứng dụng, tùy version.

Không nên lấy một property từ tài liệu Spring Boot rồi suy ra Spring Framework thuần cũng tự đọc property đó. Ví dụ `management.jmx.domain` trong bài này được trình bày như **property ứng dụng tự định nghĩa**; trước khi dùng key trùng với một property được Spring Boot hiểu đặc biệt, cần kiểm tra version và cấu hình đang hoạt động.

Nếu Boot Actuator cùng một exporter riêng đều tạo MBean, cũng cần tránh xung đột ObjectName và đảm bảo domain của các endpoint khác nhau được thiết kế có chủ đích. Việc có HTTP Actuator endpoints không đồng nghĩa các endpoint JMX được bảo vệ bởi cùng cơ chế security.

## 11. Environment khác domain: chọn quy ước nào?

### A. Đưa môi trường vào domain

```text
com.example.billing.dev:type=Queue,name=Main
com.example.billing.prod:type=Queue,name=Main
```

Ưu điểm: dễ phân nhóm trong cây domain của JConsole. Nhược điểm: dashboard query `com.example.billing:type=Queue,*` không khớp khi domain thay đổi.

### B. Giữ domain ổn định, thêm key environment

```text
com.example.billing:environment=dev,type=Queue,name=Main
com.example.billing:environment=prod,type=Queue,name=Main
```

Ưu điểm: có thể tìm nhiều môi trường với domain chung; rõ rằng môi trường là thuộc tính định danh. Nhược điểm: thêm key sẽ đổi ObjectName; một JMX proxy hard-code tên cũ phải cập nhật.

### C. Giữ ObjectName ổn định, gắn nhãn môi trường ngoài JMX

```text
com.example.billing:type=Queue,name=Main
```

Collector sử dụng nhãn môi trường từ deployment, ví dụ `environment=dev` hoặc `environment=prod`. Ưu điểm: cùng một JMX query tái sử dụng giữa các môi trường; thích hợp nếu mỗi deployment có MBeanServer riêng. Nhược điểm: client chỉ nhìn ObjectName có thể thiếu ngữ cảnh môi trường nếu kết nối bị gắn nhãn không rõ ràng.

**Khuyến nghị thiết kế:** nếu mục tiêu là tránh trùng ObjectName trong một shared server, thêm identity ứng dụng/module là quan trọng nhất. Nếu mục tiêu chỉ là phân biệt staging và production vốn ở hai JVM độc lập, cân nhắc giữ domain ổn định để tooling và script dễ tái sử dụng.

## 12. Xác thực domain cấu hình

Domain đến từ environment variable, profile hoặc config server có thể sai. Nên xác thực trước khi dùng:

```java
import javax.management.ObjectName;

public static String checkedDomain(String domain) throws Exception {
    if (domain == null || !domain.matches(
            "[A-Za-z0-9_.-]+")) {
        throw new IllegalArgumentException(
            "Invalid management domain"
        );
    }
    // Parser JMX kiểm tra cú pháp ObjectName cuối cùng.
    new ObjectName(domain + ":type=Validation");
    return domain;
}
```

Regex chỉ là quy ước ví dụ cho một tổ chức, không phải toàn bộ grammar JMX. Tùy yêu cầu naming có thể cần dấu khác, nhưng domain production nên có quy ước đủ hạn chế để tránh wildcard và các tên bất ngờ.

Không dùng `ObjectName.quote(domain)` vì API quote áp dụng cho **key property value**. Với domain và key name phải dùng validator phù hợp hoặc template được cấu hình tin cậy.

## 13. Tránh tên thay đổi mỗi lần khởi động

Không nên tạo domain như:

```text
com.example.orders.dev.20261111_103001
com.example.orders.dev.pid12345
```

nếu dashboard hoặc proxy cần truy cập ObjectName ổn định. Tên chứa timestamp/PID có thể hữu ích khi quản lý nhiều instance trong cùng một shared server, nhưng nó làm tên thay đổi liên tục sau restart.

Nếu nhiều instance thực sự cùng MBeanServer, thêm `instance` key lấy từ một ID ổn định:

```text
com.example.orders.dev:type=Queue,name=Main,instance=worker-a
com.example.orders.dev:type=Queue,name=Main,instance=worker-b
```

Đồng thời phải xác định quy tắc discovery của monitoring và cleanup khi instance biến mất. Nếu mỗi instance nằm ở JVM riêng, cùng ObjectName trên mỗi server là hợp lệ và thường đơn giản hơn.

## 14. Ảnh hưởng tới các JMX client và proxy

Giả sử trước đây client dùng:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Main"
);
```

Sau khi đổi domain thành `com.example.orders.prod`, ObjectName cũ không còn tìm được MBean mới. Các thành phần có thể phải cập nhật:

- Script và JConsole bookmarks sử dụng ObjectName.
- `MBeanProxyFactoryBean.setObjectName(...)` trong Spring client.
- `MBeanServerConnection.queryNames` và monitoring filters.
- Alert rules/dashboards dùng query domain cụ thể.
- Notification listener registrations dựa trên ObjectName.
- Các integration test quản trị.

Vì vậy thay domain là **thay đổi management contract**. Cần có kế hoạch đồng bộ cấu hình client và server; nếu có nhiều bản ứng dụng chạy đồng thời, cân nhắc khoảng chuyển tiếp hoặc sử dụng discovery pattern phù hợp.

## 15. Kiểm tra domain và ObjectName sau khi khởi động

Đọc thông tin server và registry:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

System.out.println("Default domain: " + server.getDefaultDomain());

ObjectName pattern = new ObjectName(
    "com.example.orders.*:*"
);

Set<ObjectName> names = server.queryNames(pattern, null);
for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
```

Ví dụ dùng platform MBeanServer; nếu exporter đăng ký vào một server riêng, phải lấy đúng server đó. Pattern `com.example.orders.*:*` khớp các domain kiểu `com.example.orders.dev` hoặc `com.example.orders.prod`, không khớp `com.example.orders` nếu wildcard ở đó chỉ đứng sau dấu chấm.

Để kiểm tra một tên exact:

```java
ObjectName expected = new ObjectName(
    "com.example.orders.dev:type=Queue,name=Pending"
);
System.out.println(server.isRegistered(expected));
```

Không chỉ dựa vào default domain được in ra. Khi MBean dùng ObjectName explicit, default domain của server có thể hoàn toàn khác domain của MBean mà vẫn hợp lệ.

## 16. Xử lý lỗi cấu hình và va chạm tên

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `MalformedObjectNameException` | Domain chứa ký tự không hợp lệ hoặc chuỗi ghép sai | Validate property và tạo ObjectName trước export |
| `InstanceAlreadyExistsException` | Hai MBean cùng ObjectName trong một server | Bổ sung app/module/instance identity hoặc một owner duy nhất |
| `isRegistered` trả false | Tên dự kiến khác tên thực tế hoặc server sai | Query ObjectName canonical trên đúng server |
| JConsole không thấy MBean | Exporter đăng ký vào server khác, connector khác hoặc chưa export | Kiểm tra server binding và lifecycle |
| `getDefaultDomain()` không giống domain của MBean | MBean sử dụng domain explicit | Đây không nhất thiết là lỗi |
| Dev hoạt động nhưng prod không thấy | Profile/property chưa được nạp, naming config khác | Đọc property hiệu lực và registry thật |
| Dashboard hỏng sau đổi domain | Client hard-code ObjectName cũ | Đồng bộ query/proxy, quản lý migration |
| Thêm `@ManagedResource` nhưng domain config không có tác dụng | Annotation objectName explicit ghi đè kỳ vọng naming | Điều chỉnh annotation hoặc naming strategy đúng đường export |

**RegistrationPolicy** như `FAIL_ON_EXISTING`, `IGNORE_EXISTING` và `REPLACE_EXISTING` chỉ quy định hành vi khi một ObjectName đã có. Chúng không thay thế việc thiết kế namespace. Dùng `REPLACE_EXISTING` để tránh lỗi tên trùng có thể làm ứng dụng khác mất MBean và gây sai số liệu giám sát.

## 17. Quy tắc vận hành và bảo mật

1. Domain phải có chủ sở hữu, quy ước tên và nguồn cấu hình rõ ràng.
2. Chỉ thêm môi trường vào domain khi có lợi ích thực tế cho registry hoặc tooling.
3. Không đưa token, mật khẩu, customer identifier nhạy cảm vào domain/keys.
4. Tránh domain ngẫu nhiên khiến JMX proxy và dashboards mất tính ổn định.
5. Khi nhiều context chia sẻ server, tên cần phân biệt ứng dụng/module; khi các JVM riêng, trùng tên trên hai server thường không phải lỗi.
6. Không lẫn lộn default domain server với naming strategy của exporter.
7. Kiểm tra ObjectName thật bằng `queryNames` và canonical name.
8. Không tự public remote JMX connector chỉ để quản lý domain: kết nối JMX cần network policy, TLS, authentication và authorization thích hợp.
9. Giữ getters nhẹ và operations có quyền/validation phù hợp, vì chọn domain không làm API quản trị an toàn hơn.
10. Khi đổi domain, cập nhật client, script và runbook như một thay đổi API quản trị.

## 18. Mô hình tư duy

```text
Deployment environment
     |
     +-- property: management.jmx.domain
             |
             +-- explicit ObjectName -> domain đã chỉ định
             |
             +-- ObjectNamingStrategy -> domain do strategy sinh
             |
             +-- new MBeanServer -> server default domain
                      |
                      v
               MBeanServer registry
                      |
               JMX client/query/proxy
```

**Kết luận:** Đặt `defaultDomain` theo môi trường chỉ có ý nghĩa khi xác định đúng tầng cấu hình. Nếu mục tiêu là thay domain của các MBean trong Spring, cách rõ nhất thường là tạo ObjectName tường minh từ cấu hình hoặc sử dụng `ObjectNamingStrategy` nhất quán. Nếu mục tiêu là default domain cấp JMX server, cần tạo/quản lý đúng `MBeanServer` và hiểu cách xử lý ObjectName có domain rỗng. Không nên đổi tên MBean tùy tiện theo profile nếu client, dashboard hoặc script phụ thuộc vào tên ổn định.
