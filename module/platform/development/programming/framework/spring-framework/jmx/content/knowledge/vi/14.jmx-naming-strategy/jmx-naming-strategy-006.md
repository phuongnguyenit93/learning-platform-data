# defaultDomain và namespace của ứng dụng trong Spring Framework JMX Naming Strategy

## 1. Bối cảnh

Khi Spring Framework export một bean thành JMX MBean, client cần một **ObjectName** để xác định resource trong `MBeanServer`. ObjectName chứa domain và một hoặc nhiều key property. Ví dụ:

```text
com.example.orders:type=OrderWorker,name=Primary
```

Trong đó `com.example.orders` là domain, còn `type=OrderWorker,name=Primary` là tập key property giúp định danh resource. Domain có thể được xem như một phần của **namespace quản trị** của ứng dụng: nó giúp phân nhóm MBean, giảm khả năng đụng tên và tạo cấu trúc dễ khám phá cho JConsole, dashboard và automation.

Spring JMX cung cấp **naming strategy** để quyết định ObjectName khi export. Thuộc tính **defaultDomain** có thể xuất hiện trong cấu hình `MBeanServer`, `MBeanServerFactoryBean` hoặc một số naming strategy. Nhưng các “default” này không đồng nghĩa, không bảo đảm tự thay thế domain được viết tường minh trong ObjectName.

Bài học tập trung vào cách thiết kế domain ổn định, hiểu phạm vi tác dụng của defaultDomain và phân biệt chiến lược đặt tên ở Spring với quy tắc ObjectName của JMX.

## 2. Mục tiêu

Sau bài học, bạn có thể:

- Đọc cú pháp ObjectName và giải thích domain khác key property như thế nào.
- Phân biệt `MBeanServer.getDefaultDomain()` với domain do naming strategy của Spring tạo ra.
- Dùng `MBeanServerFactoryBean` khi cần server riêng với default domain có chủ đích.
- Dùng `MetadataNamingStrategy`, `ObjectNamingStrategy` hoặc tên đăng ký tường minh khi export.
- Thiết kế namespace ứng dụng theo module, loại MBean và instance mà không gây trùng tên.
- Kiểm tra ObjectName đã đăng ký trên đúng MBeanServer và xử lý lỗi naming.
- Hiểu các giới hạn của domain khi giám sát nhiều JVM, triển khai đa tenant và truy cập remote.

## 3. ObjectName: domain và key property

JMX định nghĩa `javax.management.ObjectName` dưới dạng:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.orders:type=OrderWorker,name=Primary,region=ap-southeast
```

| Thành phần | Giá trị | Vai trò |
| --- | --- | --- |
| Domain | `com.example.orders` | Nhóm namespace của MBean |
| `type` | `OrderWorker` | Loại resource quản trị |
| `name` | `Primary` | Tên một instance trong loại resource |
| `region` | `ap-southeast` | Thông tin phân biệt instance |

Các key `type`, `name` và `region` là **quy ước ứng dụng**, không phải những key bắt buộc cho mọi MBean. Tuy nhiên, dùng `type` cho loại và `name` cho instance giúp việc tìm kiếm trực quan hơn.

Đọc các thành phần:

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=OrderWorker,name=Primary,region=ap-southeast"
);

System.out.println(name.getDomain());              // com.example.orders
System.out.println(name.getKeyProperty("type"));   // OrderWorker
System.out.println(name.getKeyProperty("name"));   // Primary
System.out.println(name.getCanonicalName());
```

`getCanonicalName()` trả một biểu diễn chuẩn hóa về thứ tự key property. Khi so sánh hai ObjectName, nên dùng `equals()` hoặc biểu diễn canonical, không dựa vào thứ tự key trong chuỗi ban đầu.

Ví dụ hai tên tương đương:

```text
com.example.orders:type=OrderWorker,name=Primary
com.example.orders:name=Primary,type=OrderWorker
```

Thứ tự key property khác nhau không làm đổi đối tượng định danh. Trong cùng một MBeanServer, hai đăng ký có cùng ObjectName theo nghĩa JMX sẽ xung đột.

## 4. Namespace của ứng dụng nhằm giải quyết việc gì?

Namespace được thiết kế để con người và các công cụ dễ tìm resource. Nó còn giúp giảm xung đột khi nhiều framework, module hoặc thư viện dùng chung MBeanServer.

Một số lựa chọn:

```text
com.example.orders:type=OrderWorker,name=Primary
com.example.orders:type=OrderQueue,name=Async
com.example.inventory:type=StockSynchronizer,name=Main
com.example.payments:type=PaymentMetrics,name=Gateway
```

Cấu trúc này cho thấy:

- Domain phân tách miền quản trị theo ứng dụng hoặc module.
- Key `type` thể hiện dạng thành phần.
- Key `name` phân biệt instance trong cùng loại.
- Các key khác được thêm khi có nhu cầu nhận diện thực tế.

Domain **không phải cơ chế phân quyền hay sandbox bảo mật**. Hai domain trong cùng server vẫn có thể được nhìn thấy bởi cùng một JMX client nếu quyền truy cập cho phép. Nếu cần isolation, phải thiết kế connector, policy, quyền và network phù hợp.

### 4.1. Domain giúp truy vấn MBean

```java
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName pattern = new ObjectName(
    "com.example.orders:type=OrderWorker,*"
);

Set<ObjectName> workers = server.queryNames(pattern, null);

for (ObjectName worker : workers) {
    System.out.println(worker.getCanonicalName());
}
```

`queryNames` nhận ObjectName pattern và trả các ObjectName thực tế đang đăng ký. Dùng wildcard phục vụ truy vấn; một pattern khớp nhiều MBean không phải một đích duy nhất để tự động gọi `getAttribute` hoặc `invoke`.

### 4.2. Domain không thay cho key instance

Nếu mọi worker trong một module đều dùng:

```text
com.example.orders:type=OrderWorker
```

thì bạn chỉ có thể đăng ký một MBean với tên đó trong cùng server. Muốn có nhiều worker, thêm key:

```text
com.example.orders:type=OrderWorker,name=Primary
com.example.orders:type=OrderWorker,name=Backup
```

Không nên tạo nhiều server chỉ để né xung đột ObjectName nếu thiết kế một namespace có cấu trúc đã giải quyết được nhu cầu.

## 5. defaultDomain trong MBeanServer

JMX `MBeanServer` có phương thức:

```java
String getDefaultDomain();
```

Ví dụ:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

System.out.println(server.getDefaultDomain());
```

Kết quả phụ thuộc server. Default domain là tên miền mặc định của **MBeanServer**, có ý nghĩa trong một số trường hợp ObjectName không chỉ định domain tường minh.

JMX cho phép `ObjectName` với phần domain rỗng, chẳng hạn dạng:

```text
:type=OrderWorker,name=Main
```

Trong tình huống phù hợp, server có thể áp dụng default domain khi đăng ký hoặc diễn giải ObjectName. Tuy nhiên:

- Không nên dựa vào domain ngầm nếu cần tên ổn định, dùng lại giữa nhiều môi trường.
- Default domain của server không bắt buộc mọi MBean phải mang domain đó.
- ObjectName có domain tường minh vẫn giữ domain tường minh.
- Default domain của MBeanServer khác với default domain được cấu hình ở một naming strategy.

Ví dụ:

```java
ObjectName explicit = new ObjectName(
    "com.example.orders:type=OrderWorker,name=Main"
);
```

Tên này đã chỉ rõ `com.example.orders`. Không có lý do để tự thay nó thành default domain của server.

## 6. Tạo MBeanServer với default domain riêng

Nếu ứng dụng cần một server mới, Spring có `MBeanServerFactoryBean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class PrivateJmxServerConfig {

    @Bean
    public MBeanServerFactoryBean privateMBeanServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();

        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        factory.setRegisterWithFactory(false);

        return factory;
    }
}
```

Giải thích:

- `setDefaultDomain(...)` chọn domain mặc định của server mới.
- `setLocateExistingServerIfPossible(false)` thể hiện ý định không tìm server có sẵn trước khi tạo mới.
- `setRegisterWithFactory(false)` cấu hình tạo server mà không đăng ký nó vào danh sách tra cứu của `MBeanServerFactory`.
- `MBeanServerFactoryBean` là Spring `FactoryBean`, vì vậy bean sản phẩm có kiểu `MBeanServer`.

Một server riêng **không tự tạo JMX Remote connector**. Nếu muốn JConsole hoặc client ở JVM khác truy cập, cần cấu hình connector hướng tới server đó. Default domain cũng không phải cấu hình hostname, port, authentication hay TLS.

### 6.1. Kiểm tra default domain trên server thật

```java
import javax.management.MBeanServer;

public void inspect(MBeanServer server) {
    System.out.println("Server default domain: "
        + server.getDefaultDomain());
}
```

Nên kiểm tra trực tiếp server được inject vào exporter, đặc biệt trong hệ thống có nhiều MBeanServer. Chỉ gọi `ManagementFactory.getPlatformMBeanServer()` sẽ không phản ánh server riêng mà Spring có thể đang sử dụng.

## 7. defaultDomain trong naming strategy của Spring

Spring sử dụng `ObjectNamingStrategy` để lấy ObjectName từ bean và bean key. Một triển khai thường gặp là `MetadataNamingStrategy`, có thể khai thác `@ManagedResource(objectName = "...")` và cấu hình default domain.

Ví dụ cấu hình:

```java
import org.springframework.jmx.export.naming.MetadataNamingStrategy;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

AnnotationJmxAttributeSource source =
    new AnnotationJmxAttributeSource();

MetadataNamingStrategy namingStrategy =
    new MetadataNamingStrategy(source);

namingStrategy.setDefaultDomain("com.example.orders");
```

Default domain trong naming strategy dùng khi chiến lược cần **sinh ObjectName** mà metadata không đưa ra một tên tường minh. Đó là quy tắc đặt tên ở phía Spring, không phải lệnh thay đổi default domain của `MBeanServer`.

Điểm quan trọng:

```text
MBeanServer.getDefaultDomain()
    -> Cấu hình của JMX registry

MetadataNamingStrategy.setDefaultDomain(...)
    -> Quy tắc sinh tên từ bean/metadata trước khi đăng ký
```

Hai giá trị có thể giống nhau vì lựa chọn thiết kế, nhưng không cần thiết giống nhau và không tự đồng bộ.

### 7.1. Tên tường minh có ưu tiên

Nếu metadata của resource công bố:

```java
@ManagedResource(
    objectName = "com.example.orders:type=OrderWorker,name=Main"
)
public class OrderWorker {
    // ...
}
```

thì tên tường minh này là chỉ dẫn đặt tên cụ thể. Không nên giả định `defaultDomain` của naming strategy sẽ ghi đè `com.example.orders`.

Nếu bạn muốn thống nhất namespace theo cấu hình triển khai, có thể không hard-code ObjectName ở lớp và thiết kế naming strategy riêng hoặc dùng explicit bean-name mapping. Tùy cấu hình, cách này giúp cùng một class được export dưới những ObjectName khác nhau cho các instance khác nhau.

## 8. MBeanExporter và ObjectNamingStrategy

Một cấu hình đầy đủ có thể dùng naming strategy của Spring:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxNamingConfig {

    @Bean
    public OrderWorker orderWorker() {
        return new OrderWorker();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationJmxAttributeSource jmxSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
            new MetadataNamingStrategy(source);
        naming.setDefaultDomain("com.example.orders");
        return naming;
    }

    @Bean
    public MBeanExporter mBeanExporter(
            OrderWorker orderWorker,
            MBeanServer mBeanServer,
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setBeans(Map.of(
            "orderWorker", orderWorker
        ));
        return exporter;
    }
}
```

Với bean được đánh dấu:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(description = "Order processing worker")
public class OrderWorker {
    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether processing is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Change processing state")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Ý nghĩa cấu hình:

1. `MBeanExporter` nhận một bean và một key `orderWorker`.
2. `MetadataNamingStrategy` đọc metadata và có default domain `com.example.orders`.
3. `MetadataMBeanInfoAssembler` dùng metadata để tạo giao diện JMX.
4. Exporter đăng ký bean vào platform MBeanServer được inject.

ObjectName cuối cùng là kết quả quy tắc của naming strategy trên metadata, bean key và trạng thái cấu hình của Spring. Nếu code vận hành cần biết chính xác tên, hãy truy vấn đăng ký thực tế trên server thay vì dựa vào suy đoán từ bean name.

### 8.1. Khi muốn ObjectName hoàn toàn tường minh

Cách đơn giản là cấu hình trực tiếp:

```java
exporter.setBeans(Map.of(
    "com.example.orders:type=OrderWorker,name=Main",
    orderWorker
));
```

Với cấu hình phù hợp, key này là ObjectName tường minh để đăng ký. Khi dự án cần một hợp đồng tên bất biến và chỉ có vài MBean, cách này thường dễ đọc hơn một chiến lược sinh tên phức tạp.

Không nên trộn nhiều nơi đặt tên mà không xác định quyền ưu tiên: annotation `objectName`, key trong `setBeans`, naming strategy và cấu hình server cần nhất quán.

## 9. Quy ước domain cho ứng dụng và module

Một quy ước tốt phải ổn định, không phụ thuộc thời gian chạy và có đủ key để phân biệt instance.

### 9.1. Lựa chọn domain

Các kiểu domain thường thấy:

```text
com.example.app
com.example.orders
com.example.orders.worker
org.example.platform.cache
```

Dùng reversed DNS hoặc namespace tổ chức là một cách phổ biến để giảm trùng tên với thư viện. Chẳng hạn `com.example.orders` không có nghĩa có URL `https://com.example.orders`; đó là tên miền JMX logic.

Không nên đưa hostname, IP hay deployment ID có thể thay đổi vào domain nếu không có nhu cầu thực sự. Những thông tin này có thể phù hợp hơn ở key property hoặc identity của connection trong công cụ giám sát.

### 9.2. Quy ước key property

```text
com.example.orders:type=OrderWorker,name=Primary
com.example.orders:type=OrderWorker,name=Backup
com.example.orders:type=OrderQueue,name=Outbound
```

Quy ước nên trả lời:

- `type`: loại MBean, thường gắn với thành phần.
- `name`: instance hoặc role.
- `tenant`, `shard`, `region`: chỉ thêm khi phân biệt tài nguyên thật.
- Key nào ổn định qua restart?
- Key nào có thể đổi khi rollout? Nếu đổi, dashboard/alert có cần cập nhật không?

Một key duy nhất như `instance=1` có thể đủ cho local JVM nhưng không đủ để chỉ duy nhất resource trong hệ thống đa JVM. Monitoring đa server thường cần thêm kết nối/host/environment ngoài ObjectName.

### 9.3. Không đưa dữ liệu nhạy cảm vào tên

ObjectName thường xuất hiện trong log, màn hình JConsole, metric labels hoặc hệ thống quan sát. Không đưa access token, mật khẩu, customer email hoặc dữ liệu cá nhân vào domain/key property. Nếu cần phân biệt tenant, dùng định danh nội bộ an toàn và áp dụng quyền đọc tương ứng.

## 10. Tạo ObjectName an toàn khi có ký tự đặc biệt

Các key property value có thể chứa ký tự cần quoting. Khi dựng tên từ dữ liệu động, không nên nối chuỗi ngây thơ:

```java
String instance = "Primary, East";
String rawName = "com.example.orders:type=OrderWorker,name=" + instance;
```

Giá trị có dấu phẩy có thể làm sai cú pháp ObjectName. Dùng `ObjectName.quote(...)` để quote giá trị:

```java
import javax.management.ObjectName;

String instance = "Primary, East";

ObjectName safeName = new ObjectName(
    "com.example.orders:type=OrderWorker,name="
        + ObjectName.quote(instance)
);
```

Lưu ý `ObjectName.quote` tạo biểu diễn quoted value, không tự quyết định liệu value đó phù hợp với thiết kế namespace hoặc bảo mật hay không. Khi đọc lại key property ở dạng được quote, có thể dùng `ObjectName.unquote(...)` trên giá trị được quote hợp lệ nếu cần văn bản gốc.

Với giá trị động, nên còn có bước validation: giới hạn độ dài, ký tự và khả năng trùng tên. Một tên kỹ thuật ổn định thường hữu ích hơn một display label do người dùng tự nhập.

## 11. Default domain và truy cập JMX Remote

Domain của ObjectName **không** quyết định endpoint mạng. Giả sử có:

```text
com.example.orders:type=OrderWorker,name=Main
```

Để truy cập qua JMX Remote, client vẫn cần địa chỉ connector, ví dụ `JMXServiceURL`, credentials và chính sách bảo mật. Một MBeanServer riêng có default domain `com.example.orders` không tự bật RMI registry hay cổng remote.

```text
JMX Client
   |
   | JMXConnector / JMXServiceURL
   v
MBeanServerConnection
   |
   | ObjectName domain:key=value
   v
MBeanServer
   |
   v
MBean
```

Trong hệ thống nhiều JVM, cùng ObjectName có thể xuất hiện trên nhiều server. Vì vậy khóa điều hướng thực tế ở dashboard thường là:

```text
(connection-id, object-name-canonical)
```

Domain giúp nhóm MBean trong từng server, nhưng **không làm identity toàn cục cho mọi kết nối**.

## 12. Tìm và kiểm tra ObjectName đã đăng ký

Dùng `queryNames` để khám phá domain trong đúng server:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;

import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName pattern =
    new ObjectName("com.example.orders:*");

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
```

Nếu exporter đang dùng private MBeanServer, phải dùng instance đó thay vì platform server.

### 12.1. Kiểm tra một tên cụ thể

```java
ObjectName expected = new ObjectName(
    "com.example.orders:type=OrderWorker,name=Main"
);

if (server.isRegistered(expected)) {
    System.out.println("MBean exists on selected server");
}
```

Khi không tìm thấy:

1. Spring bean đã được tạo chưa?
2. `MBeanExporter` đã khởi tạo chưa?
3. Exporter dùng MBeanServer nào?
4. Naming strategy cuối cùng có tạo đúng ObjectName này không?
5. Metadata có ObjectName tường minh khác không?
6. Có lỗi đăng ký do trùng tên không?
7. Có đang kiểm tra sai thời điểm hoặc sai context không?

`MBeanServer.getDomains()` giúp liệt kê những domain có các MBean đang đăng ký. Nó không thay thế việc xác minh ObjectName cụ thể.

## 13. Trùng tên và registration policy

Trong **một MBeanServer**, mỗi ObjectName chỉ có thể định danh một MBean đang đăng ký. Nếu hai bean cùng một ObjectName, có thể có `InstanceAlreadyExistsException` hoặc hành vi theo chính sách registration đã cấu hình trong Spring exporter.

Ví dụ:

```text
com.example.orders:type=OrderWorker,name=Main
com.example.orders:type=OrderWorker,name=Main
```

Không thể giả định hai đăng ký trên cùng server sẽ tự hợp nhất. Cần đặt tên phân biệt instance, hoặc xác định quy tắc thay thế/bỏ qua có chủ đích. Không nên tự động replace MBean mà một thành phần khác đang sở hữu chỉ để tránh lỗi lúc khởi động.

Khi domain lấy từ default và bean key bị dùng lại giữa nhiều module, nguy cơ trùng tên càng dễ xảy ra. Vì vậy trong ứng dụng lớn, hãy có convention toàn dự án cho domain, type và name.

## 14. Default domain có thể gây những nhầm lẫn nào?

| Nhầm lẫn | Thực tế |
| --- | --- |
| `MBeanServer.getDefaultDomain()` quyết định domain của mọi MBean | ObjectName có domain tường minh không bị bắt buộc đổi domain |
| `MetadataNamingStrategy.setDefaultDomain()` đổi cấu hình MBeanServer | Nó thuộc bước sinh tên của Spring |
| Domain là URL hoặc endpoint JMX Remote | Domain là phần định danh JMX, không phải mạng |
| Domain khác nhau là có quyền truy cập khác nhau | Domain tự nó không phải security boundary |
| ObjectName giống nhau trên hai JVM là một MBean duy nhất | Mỗi MBeanServer có registry riêng |
| Spring bean name luôn là ObjectName | Naming strategy và cách export quyết định tên JMX |
| Đổi domain chỉ là đổi nhãn hiển thị | Đổi domain làm đổi ObjectName, có thể làm client mất đường truy cập |
| Default domain server bằng default domain naming strategy một cách tự động | Hai lớp cấu hình độc lập và có thể khác nhau |

### 14.1. Thay đổi domain có hệ quả gì?

Ví dụ đổi:

```text
com.example.orders:type=OrderWorker,name=Main
```

thành:

```text
com.example.core:type=OrderWorker,name=Main
```

Đây là thay đổi identity. Các dashboard, JMX proxy, cảnh báo và script lưu ObjectName cũ có thể không còn truy cập MBean. Nên quản lý việc đổi tên như thay đổi hợp đồng quản trị, có kế hoạch cập nhật consumer hoặc giai đoạn chuyển tiếp thích hợp.

## 15. Thiết kế naming strategy tùy biến

Khi naming convention phụ thuộc module hoặc role triển khai, có thể viết một `ObjectNamingStrategy` riêng:

```java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class ApplicationNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String type = managedBean.getClass().getSimpleName();
        String safeKey = ObjectName.quote(beanKey);

        return new ObjectName(
            "com.example.orders:type=" + ObjectName.quote(type)
                + ",name=" + safeKey
        );
    }
}
```

Trong Spring, `beanKey` có thể là tên bean hoặc key từ cấu hình exporter. Ví dụ này minh họa ý tưởng dùng domain cố định và phân biệt loại/instance; ứng dụng thật cần xem xét proxy class, giá trị key ổn định và các quy tắc quoter. Đặc biệt nếu bean là Spring AOP proxy, `getClass().getSimpleName()` có thể là tên proxy thay vì tên business class: chiến lược thực tế nên lấy class đích hoặc metadata thích hợp.

Đăng ký chiến lược:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setNamingStrategy(new ApplicationNamingStrategy());
```

Chỉ dùng custom strategy khi convention mặc định không đủ. Tên tường minh thường dễ vận hành hơn nếu số lượng MBean ít và cố định.

## 16. Bài tập thực hành

Tạo hai Spring MBean cho cùng một module:

```text
com.example.orders:type=OrderWorker,name=Primary
com.example.orders:type=OrderWorker,name=Backup
```

Yêu cầu:

1. Tạo bean `OrderWorker` có `@ManagedResource` và một `@ManagedAttribute` đọc trạng thái.
2. Export hai instance bằng `MBeanExporter` với ObjectName tường minh.
3. Dùng `queryNames("com.example.orders:*")` để liệt kê những MBean trong domain.
4. Dùng `getDomain()` và `getKeyProperty("name")` để phân biệt domain với instance key.
5. Thử tạo server mới có default domain `com.example.management`, sau đó đăng ký ObjectName có domain `com.example.orders` và quan sát domain tường minh vẫn được dùng.
6. Dùng `getDefaultDomain()` trên server mới để đọc domain mặc định thực tế.
7. Thử đăng ký cùng ObjectName hai lần vào cùng server, quan sát xung đột.
8. Thử đăng ký cùng ObjectName vào hai MBeanServer độc lập và giải thích vì sao chúng có thể cùng tồn tại.
9. Đổi domain của một MBean và xác định những phần của dashboard/automation cần cập nhật.

Một tình huống kiểm tra nhỏ:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer isolated =
    MBeanServerFactory.newMBeanServer(
        "com.example.management"
    );

System.out.println(isolated.getDefaultDomain());

ObjectName explicit = new ObjectName(
    "com.example.orders:type=OrderWorker,name=Primary"
);

System.out.println(explicit.getDomain());
// com.example.orders; không tự đổi thành default domain.
```

Khi thực hành, để kiểm tra một MBean đã đăng ký, cần có MBean instance thích hợp và gọi `registerMBean` hoặc export qua Spring. Việc chỉ tạo ObjectName chưa đăng ký MBean.

## 17. Câu hỏi tự kiểm tra

**1. ObjectName có cấu trúc tổng quát thế nào?** Domain và các key property, ví dụ `domain:type=Worker,name=Main`.

**2. Domain giúp giải quyết vấn đề gì?** Nhóm namespace MBean và giảm xung đột tên trong server.

**3. Default domain của MBeanServer có bắt mọi ObjectName đổi domain không?** Không, ObjectName có domain tường minh giữ domain đó.

**4. `MetadataNamingStrategy.setDefaultDomain(...)` có thay đổi server default domain không?** Không, nó ảnh hưởng quy tắc sinh ObjectName ở Spring.

**5. ObjectName có duy nhất giữa các JVM không?** Không, nó duy nhất trong từng MBeanServer.

**6. Nếu exporter dùng server riêng, vì sao JConsole kết nối platform server không thấy MBean?** Vì đó là hai registry khác nhau, trừ khi connector/client được trỏ tới server riêng.

**7. Domain có tự bảo vệ MBean khỏi client không?** Không, bảo mật phụ thuộc vào connector và authorization.

**8. Khi nên dùng ObjectName tường minh?** Khi hợp đồng đặt tên cố định, ít MBean và cần người vận hành dễ đoán chính xác tên.

**9. Tại sao phải cẩn thận khi dùng class name trong naming strategy tùy biến?** Proxy và đổi tên class có thể thay đổi identity một cách không mong muốn.

**10. Đổi domain có phải chỉ là đổi mô tả không?** Không, nó đổi ObjectName và có thể ảnh hưởng consumer.

## 18. Ghi nhớ

- **Domain là một phần của ObjectName**, còn key property phân biệt loại và instance.
- **Namespace JMX của ứng dụng** nên ổn định, rõ ràng và không chứa dữ liệu nhạy cảm.
- **`MBeanServer.getDefaultDomain()`** mô tả domain mặc định của server; không ghi đè những ObjectName đã có domain tường minh.
- **`MetadataNamingStrategy.setDefaultDomain(...)`** hỗ trợ sinh tên từ metadata phía Spring và khác cấu hình server.
- **`MBeanServerFactoryBean`** có thể tạo server với default domain riêng, nhưng không tự bật JMX Remote.
- **`MBeanExporter` + naming strategy** quyết định ObjectName cuối cùng được đăng ký.
- Cùng ObjectName có thể tồn tại trên các MBeanServer khác nhau; client đa server phải giữ thêm danh tính kết nối.
- Thay đổi domain hoặc key property là thay đổi **định danh quản trị**, không chỉ thay đổi nhãn hiển thị.

Hiểu rõ defaultDomain và namespace giúp Spring JMX có hệ thống tên dễ tìm kiếm, giảm đụng độ đăng ký và giữ các công cụ quản trị hoạt động ổn định qua nhiều lần triển khai.