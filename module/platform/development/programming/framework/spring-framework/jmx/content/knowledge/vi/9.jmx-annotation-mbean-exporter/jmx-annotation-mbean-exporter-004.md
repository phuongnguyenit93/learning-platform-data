# Liên hệ giữa AnnotationMBeanExporter và phần tử `<context:mbean-export>` trong XML

## Mục tiêu

Sau bài học, bạn có thể giải thích cách `<context:mbean-export/>` kích hoạt cơ chế export MBean dựa trên annotation của Spring Framework, vai trò của `AnnotationMBeanExporter`, các annotation `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, cách cấu hình tương đương bằng Java, và các yếu tố cần kiểm tra khi chuyển đổi cấu hình XML sang Java hoặc khi ứng dụng có nhiều cơ chế xuất JMX.

## 1. Bức tranh tổng quan

JMX (Java Management Extensions) cho phép ứng dụng Java công bố trạng thái và thao tác quản trị qua các MBean trong `MBeanServer`. Spring Framework giúp đơn giản hóa bước xuất Spring bean sang JMX: thay vì tự gọi `MBeanServer.registerMBean`, bạn có thể gắn annotation cho các bean cần quản trị rồi để Spring đăng ký.

Trong ứng dụng Spring cấu hình XML, phần tử:

```xml
<context:mbean-export/>
```

thuộc **Spring context namespace** và kích hoạt hạ tầng export JMX dựa trên annotation. Nó liên quan trực tiếp đến `org.springframework.jmx.export.annotation.AnnotationMBeanExporter`, một lớp exporter có sẵn các thành phần cần thiết để nhận diện metadata JMX trên Spring bean.

Hình dung luồng:

```text
Spring ApplicationContext
  |
  |-- @ManagedResource trên bean
  |-- @ManagedAttribute / @ManagedOperation trên method
  |
  v
<context:mbean-export/>
  |
  v
AnnotationMBeanExporter
  |-- Đọc metadata từ annotation
  |-- Xác định ObjectName
  |-- Đăng ký MBean với MBeanServer
  v
JMX clients: JConsole / JMC / monitoring agents
```

Điểm quan trọng: **`<context:mbean-export/>` là cấu hình khai báo trong XML; `AnnotationMBeanExporter` là thành phần Java thực hiện cơ chế export**. Khi đọc XML, cần hiểu phía sau phần tử ngắn gọn này có cả việc phát hiện bean, phân tích metadata và đăng ký MBean.

## 2. Cấu hình tối thiểu trong XML

Ví dụ tập tin `applicationContext.xml`:

```xml
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
```

Hai dòng cốt lõi có trách nhiệm khác nhau:

- `<context:component-scan>` phát hiện các class/bean theo cấu hình component scanning. Bản thân nó không xuất MBean.
- `<context:mbean-export/>` bật hạ tầng export MBean dựa trên annotation cho các bean được quản lý trong context đó.

Không phải mọi bean được scan đều trở thành MBean. Thông thường, bean cần có metadata JMX phù hợp, như `@ManagedResource`; các method quản trị cần được đánh dấu `@ManagedAttribute` hoặc `@ManagedOperation`.

Có thể không dùng component scanning và khai báo bean bằng XML:

```xml
<bean id="queueMonitor" class="com.example.monitoring.QueueMonitor"/>
<context:mbean-export/>
```

Điều kiện là `QueueMonitor` có metadata annotation thích hợp và exporter được cấu hình hoạt động.

## 3. Ví dụ @ManagedResource, @ManagedAttribute và @ManagedOperation

Tạo Spring bean có trạng thái và thao tác quản trị:

```java
package com.example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Payment queue management"
)
public class QueueMonitor {
    private volatile int pendingCount = 12;
    private volatile boolean paused;

    @ManagedAttribute(description = "Current pending messages")
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedAttribute(description = "Whether queue is paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedAttribute
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @ManagedOperation(description = "Clear local counters")
    public void resetPendingCount() {
        pendingCount = 0;
    }
}
```

Khi context có `<context:mbean-export/>`, exporter đọc metadata và đăng ký bean theo `ObjectName` đã khai báo:

```text
com.example.orders:type=Queue,name=Payment
```

Client JMX có thể nhìn thấy:

```text
Attributes:
  PendingCount : int      read-only
  Paused       : boolean  read-write

Operations:
  resetPendingCount() : void
```

JMX chỉ công bố các khả năng theo metadata mà exporter xây dựng, không nhất thiết mọi method public của class. Việc kiểm tra `MBeanInfo` sau đăng ký là cách xác định chính xác hợp đồng thực tế.

Nếu `objectName` được định nghĩa rõ trong `@ManagedResource`, script quản trị và dashboard có thể dùng một tên ổn định xuyên restart. Cần tránh đưa PID, timestamp hoặc UUID mới mỗi lần chạy vào tên tài nguyên logic.

## 4. AnnotationMBeanExporter làm gì phía sau XML?

`AnnotationMBeanExporter` chuyên hỗ trợ export MBean theo annotation và kế thừa khả năng đăng ký MBean của `MBeanExporter`. Nó kết hợp các thành phần dùng để lấy metadata và đặt tên, thường liên quan đến:

- `AnnotationJmxAttributeSource`: đọc annotation JMX của Spring.
- `MetadataMBeanInfoAssembler`: xây dựng metadata quản trị dựa trên thông tin annotation.
- `MetadataNamingStrategy`: lấy hoặc suy ra `ObjectName` từ metadata theo quy tắc cấu hình.
- Cơ chế autodetection: tìm các bean thích hợp trong `ApplicationContext`.
- Hạ tầng đăng ký/hủy đăng ký MBean theo vòng đời Spring.

Vì vậy phần tử XML tương đương về ý nghĩa với việc dựng và cấu hình exporter chuyên cho annotation, thay vì phải tự ghép từng thành phần metadata.

Một số khái niệm cần phân biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| `<context:mbean-export/>` | Bật annotation-driven JMX export qua XML |
| `AnnotationMBeanExporter` | Exporter Java có cấu hình phục vụ annotation |
| `@ManagedResource` | Đánh dấu bean là tài nguyên quản trị; có thể khai báo ObjectName |
| `@ManagedAttribute` | Công bố getter/setter dưới dạng JMX attribute |
| `@ManagedOperation` | Công bố phương thức như JMX operation |
| `MBeanServer` | Lưu các MBean đã đăng ký và phục vụ JMX client |

XML không tạo ra dữ liệu quản trị. Dữ liệu vẫn đến từ các method của bean và được truy xuất khi JMX client gọi tới.

## 5. So sánh XML với Java configuration

Spring Framework hỗ trợ Java configuration thay cho XML. Cơ chế thường dùng là:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

`@EnableMBeanExport` bật hạ tầng export theo annotation trong context Java configuration, tương tự ý nghĩa của `<context:mbean-export/>` trong XML.

So sánh:

```xml
<!-- XML configuration -->
<context:mbean-export/>
```

```java
// Java configuration
@Configuration
@EnableMBeanExport
class JmxConfiguration {}
```

Hai cách cấu hình dùng cùng mô hình JMX: Spring bean được đánh dấu annotation, exporter phát hiện metadata và đăng ký trong MBeanServer. Sự khác biệt chính là nơi khai báo hạ tầng.

Khi di chuyển từ XML sang Java configuration, không nên vô tình giữ **cả hai** cơ chế bật exporter trong cùng một context nếu chúng tạo các exporter độc lập và cùng cố gắng đăng ký một `ObjectName`.

## 6. Cấu hình MBeanServer và Registration Policy

Các môi trường khác nhau có thể có nhiều `MBeanServer`. JMC hoặc JConsole kết nối vào một server cụ thể; nếu exporter đăng ký vào server khác, người vận hành có thể không thấy bean.

Trong XML, `<context:mbean-export>` có thuộc tính cấu hình liên quan đến `MBeanServer` và quy tắc đăng ký tùy phiên bản/schema Spring. Ví dụ cấu hình một `MBeanServer` được cung cấp bởi Spring:

```xml
<bean id="mbeanServer"
      class="org.springframework.jmx.support.MBeanServerFactoryBean">
    <property name="locateExistingServerIfPossible" value="true"/>
</bean>

<context:mbean-export server="mbeanServer"/>
```

Cấu hình này minh họa việc tham chiếu một bean server thay vì chỉ dựa vào lựa chọn mặc định của exporter. Tùy triển khai, ứng dụng có thể sử dụng platform `MBeanServer` của JVM bằng `ManagementFactory.getPlatformMBeanServer()` và cung cấp server đó qua Spring bean, để công cụ JVM quan sát cùng nơi đăng ký.

Ví dụ bean platform server bằng Java:

```java
@Bean
public javax.management.MBeanServer platformMBeanServer() {
    return java.lang.management.ManagementFactory
            .getPlatformMBeanServer();
}
```

Khi sử dụng `@EnableMBeanExport`, các tham số annotation và cơ chế chọn server phải được cấu hình thống nhất với context. Đừng suy đoán exporter sẽ luôn dùng platform server nếu ứng dụng đã chỉ định một server khác.

### Xung đột ObjectName

Một `MBeanServer` không cho phép hai MBean khác nhau đăng ký đồng thời dưới cùng `ObjectName`. Nếu exporter khác hoặc context khác đã đăng ký tên đó, có thể xuất hiện `InstanceAlreadyExistsException`.

Spring hỗ trợ các chính sách như:

- `FAIL_ON_EXISTING`: báo lỗi để xử lý trùng đăng ký.
- `IGNORE_EXISTING`: giữ MBean đang tồn tại, bỏ qua đăng ký mới.
- `REPLACE_EXISTING`: thay thế MBean hiện có theo chính sách của exporter.

Với Java configuration, các chính sách này liên quan đến `org.springframework.jmx.support.RegistrationPolicy`. Khi dùng XML namespace, kiểm tra thuộc tính và giá trị hợp lệ theo schema/version Spring đang sử dụng. Không tự đặt giá trị enum Java vào XML nếu namespace yêu cầu cú pháp khác.

Không nên dùng replace chỉ để che lỗi thiết kế ownership, vì MBean đang tồn tại có thể thuộc một context hoặc component khác.

## 7. XML namespace và các bean do parser đăng ký

Phần tử `<context:mbean-export/>` không phải một class Java có cùng tên. Nó là một phần tử XML được parser của Spring context namespace chuyển thành các bean definition của hạ tầng JMX khi ApplicationContext xử lý tài liệu.

```text
applicationContext.xml
    |
    v
Spring XML Namespace Parser
    |
    v
Bean definitions for JMX export infrastructure
    |
    v
AnnotationMBeanExporter
    |
    v
MBeanServer.registerMBean(...)
```

Điều này giải thích vì sao:

1. Bạn không cần khai báo đầy đủ `<bean class="...AnnotationMBeanExporter">` khi đã dùng phần tử namespace thích hợp.
2. Metadata từ `@ManagedResource` và các annotation method được xử lý khi exporter hoạt động.
3. Các bean cần export phải nằm trong phạm vi context mà exporter có khả năng phát hiện hoặc được cấu hình rõ.
4. Lỗi namespace/schema trong XML có thể khiến ApplicationContext không khởi tạo, tức exporter không tồn tại.

Một XML tối thiểu cần có khai báo namespace `context` và cặp `schemaLocation` đúng. Nếu bỏ `xmlns:context` hoặc schema tương ứng, phần tử `context:mbean-export` không được hiểu như cấu hình Spring hợp lệ.

## 8. So sánh với MBeanExporter cấu hình thủ công

Nếu dùng `MBeanExporter` thủ công, bạn có thể ánh xạ bean tới ObjectName:

```xml
<bean id="monitor" class="com.example.monitoring.QueueMonitor"/>

<bean id="jmxExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.orders:type=Queue,name=Payment"
                   value-ref="monitor"/>
        </map>
    </property>
</bean>
```

Cấu hình map beans cho phép chọn chính xác bean và tên xuất. Khi dùng `<context:mbean-export/>`, cơ chế annotation phát hiện và đặt tên quản trị theo metadata.

| Tiêu chí | XML `<context:mbean-export/>` | `MBeanExporter` explicit beans |
| --- | --- | --- |
| Phát hiện bean | Annotation-driven | Theo map `beans` cấu hình |
| Nguồn ObjectName | Metadata/naming strategy | Thường là key của map |
| Metadata quản trị | Annotation `@Managed*` | Standard MBean hoặc assembler đã cấu hình |
| Sự tiện lợi | Ít XML khi nhiều bean annotation | Rõ ràng từng bean được xuất |
| Rủi ro | Autodetection ngoài ý muốn nếu annotation quá rộng | Trùng key, trùng exporter, lệch interface |

Có thể kết hợp metadata annotation với mapping thủ công, nhưng phải cấu hình assembler thích hợp và đảm bảo ownership của mỗi MBean. Nếu XML namespace đã kích hoạt exporter, tránh thêm một exporter khác chỉ để thay đổi tên mà không kiểm tra việc đăng ký trùng.

## 9. Proxy Spring AOP và annotation-driven export

Trong ứng dụng Spring, bean có thể bị proxy bởi AOP, transaction, security hoặc interceptor. Class runtime mà exporter nhận có thể khác class gốc chứa `@ManagedResource`.

Ví dụ:

```text
JMX client
   |
   v
AnnotationMBeanExporter
   |
   v
Spring AOP proxy
   |
   v
@ManagedResource target
```

Tùy loại proxy (JDK dynamic proxy hoặc class-based proxy) và cấu hình export, exporter có thể cần truy cập annotation trên target class, trong khi các method được công bố phải gọi được qua object thực tế.

Một số tình huống đáng lưu ý:

- Annotation nằm trên target, nhưng proxy không expose method theo interface đã chọn.
- JDK proxy chỉ triển khai interface nghiệp vụ và không có interface MBean.
- Đăng ký target trực tiếp khiến các advice quan trọng không tham gia lời gọi từ JMX.
- Cùng một bean được quản lý bởi auto-export và exporter thủ công.

Cách thiết kế rõ ràng là cung cấp **JMX adapter** có API quản trị nhỏ, gọi qua Spring service proxy khi cần giữ transaction/security. Khi gặp lỗi, lấy `MBeanInfo` thực tế sau đăng ký để xác định attributes/operations, thay vì chỉ dựa vào annotation của class nguồn.

## 10. Kiểm tra sau khi bật context:mbean-export

Sau khi context khởi tạo, dùng platform `MBeanServer` nếu đó là server mà exporter đã đăng ký vào:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("MBean class: " + info.getClassName());

    for (var a : info.getAttributes()) {
        System.out.println(
            "Attribute: " + a.getName() + " / " + a.getType()
        );
    }

    for (var operation : info.getOperations()) {
        System.out.println("Operation: " + operation.getName());
    }

    Object pending = server.getAttribute(name, "PendingCount");
    System.out.println("PendingCount: " + pending);
}
```

Nếu `isRegistered(name)` trả về `false`, cần xác minh exporter đang dùng server nào trước khi kết luận bean không được export. JConsole và JMC có thể hiển thị MBean dưới domain `com.example.orders`.

Lệnh query theo domain:

```java
for (ObjectName item : server.queryNames(
        new ObjectName("com.example.orders:*"), null)) {
    System.out.println(item.getCanonicalName());
}
```

`queryNames` hỗ trợ khám phá nhưng không thay thế tên chính xác cho các thao tác quản trị nhạy cảm.

## 11. Lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| XML không parse được `context:mbean-export` | Thiếu namespace `xmlns:context`, schemaLocation sai | Sửa khai báo namespace/schema |
| Context khởi động nhưng MBean không xuất hiện | Exporter không hoạt động, bean không có `@ManagedResource`, scan không tới bean | Kiểm tra cấu hình, annotation, log |
| MBean ở một JVM không thấy trong JConsole/JMC | Đang kết nối sai JVM hoặc exporter dùng server khác | Kiểm tra process, `MBeanServer`, ObjectName |
| `MalformedObjectNameException` | `objectName` không hợp lệ hoặc value chứa ký tự đặc biệt | Xây ObjectName đúng cú pháp, quote value |
| `InstanceAlreadyExistsException` | Hai exporter/context đăng ký cùng ObjectName | Chọn một exporter sở hữu MBean |
| `NotCompliantMBeanException` | Bean không tuân giao diện JMX hoặc proxy/metadata không phù hợp | Kiểm tra assembler, annotation, proxy, StandardMBean/MXBean |
| MBean có nhưng thiếu attribute/operation | Method chưa gắn annotation hoặc exporter đọc sai metadata | Kiểm tra `@ManagedAttribute`, `@ManagedOperation`, `MBeanInfo` |
| Thao tác gọi qua JMX không đi qua aspect | Đăng ký target thay proxy | Dùng adapter/delegate phù hợp |
| Thêm XML exporter sau khi có Java exporter thì lỗi | Hai đường cấu hình export cùng một bean | Hợp nhất cấu hình và kiểm tra vòng đời |

Lưu ý: ngoại lệ cụ thể có thể được Spring bọc trong exception khi khởi tạo context. Đọc root cause trong stack trace để biết lỗi thuộc XML parser, đăng ký MBean hay invocation.

## 12. Chuyển đổi ứng dụng XML sang Java configuration

Một quy trình chuyển đổi có kiểm soát:

1. Xác định context XML nào đang chứa `<context:mbean-export/>`.
2. Liệt kê các class có `@ManagedResource` và ObjectName đang công bố.
3. Thêm Java configuration có `@EnableMBeanExport` vào đúng ApplicationContext thay thế XML.
4. Bảo đảm cách chọn `MBeanServer` và registration policy vẫn tương thích.
5. Chỉ giữ một cơ chế export chịu trách nhiệm đăng ký từng MBean.
6. Kiểm tra `MBeanServer.isRegistered`, `MBeanInfo`, attribute và operation trước/sau chuyển đổi.
7. Kiểm tra dashboard và script JMX sử dụng ObjectName cũ vẫn truy cập được.

Ví dụ chuyển:

```xml
<!-- trước -->
<context:mbean-export/>
```

```java
// sau
@Configuration
@EnableMBeanExport
public class MonitoringJmxConfig {}
```

Nếu XML còn được import bởi context mới, đừng vô tình để cùng một MBean được phát hiện và đăng ký hai lần. Cũng cần kiểm tra parent/child contexts trong ứng dụng web: một exporter ở parent và một exporter ở child có thể cùng nhận diện bean tùy cơ chế cấu hình.

## 13. Lựa chọn thực tế trong dự án Spring

**Dùng `<context:mbean-export/>` khi:**

- Dự án chủ yếu dùng XML configuration.
- Bạn muốn annotation `@ManagedResource` là nguồn metadata quản trị.
- Nhiều component có MBean riêng và bạn muốn bật export tập trung bằng một dòng XML.
- Không có nhu cầu kiểm soát tường minh mọi ánh xạ qua map.

**Dùng `@EnableMBeanExport` khi:**

- Dự án dùng Java `@Configuration`.
- Muốn biểu diễn cơ chế export theo cách Java-based, thống nhất với cấu hình context khác.
- Đang chuyển dần khỏi XML nhưng vẫn giữ hợp đồng JMX đã công bố.

**Dùng `MBeanExporter` explicit mapping khi:**

- Chỉ muốn export một tập bean rất cụ thể.
- ObjectName cần đặt tập trung, độc lập với annotation trên class.
- Nhiều instance cùng class cần tên quản trị riêng.
- Cần adapter quản trị rõ ràng thay cho service bean trực tiếp.

Không có cơ chế nào thay thế nhu cầu bảo mật remote JMX. Việc Spring export thành công chỉ có nghĩa MBean có thể được client JMX tương thích truy cập theo quyền kết nối đã cấp.

## 14. Bài tập thực hành

1. Tạo `QueueMonitor` có `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`. Bật `<context:mbean-export/>` trong XML và quan sát MBean trong JConsole.
2. Xóa cấu hình `<context:mbean-export/>` khỏi một context không còn exporter khác; xác định điều gì thay đổi trong danh sách MBean được đăng ký.
3. Thay XML export bằng Java `@EnableMBeanExport`. Xác nhận canonical ObjectName, attribute và operation giống nhau.
4. Thêm hai bean cùng khai báo một ObjectName để quan sát xung đột đăng ký trong môi trường thử nghiệm; sửa bằng cách đặt tên logic riêng cho từng tài nguyên.
5. Tạo bean Spring AOP proxy và kiểm tra liệu method được gắn `@ManagedOperation` có xuất hiện và có đi qua advice khi client gọi qua JMX.
6. So sánh explicit `MBeanExporter.setBeans` với annotation-driven export để thấy sự khác nhau giữa cấu hình tên và cấu hình metadata.

## 15. Câu hỏi tự kiểm tra

- `<context:mbean-export/>` thuộc namespace XML nào của Spring?
- Vì sao nói phần tử XML này liên quan đến `AnnotationMBeanExporter`?
- `@ManagedResource` và `@ManagedAttribute` có vai trò khác nhau thế nào?
- Khi nào nên thay `<context:mbean-export/>` bằng `@EnableMBeanExport`?
- Điều gì xảy ra nếu hai exporter cùng đăng ký một `ObjectName`?
- Vì sao một Spring bean có annotation JMX vẫn có thể không xuất hiện trong MBean Browser?
- Tại sao cần giữ `ObjectName` và hành vi quản trị tương thích khi chuyển từ XML sang Java configuration?

**Ghi nhớ:** `<context:mbean-export/>` là cú pháp XML ngắn gọn của Spring để bật annotation-driven JMX export. Nó thiết lập hạ tầng `AnnotationMBeanExporter`, đọc `@ManagedResource` và các annotation liên quan, rồi đăng ký MBean vào `MBeanServer`. Trong Java configuration, `@EnableMBeanExport` phục vụ mục đích tương đương. Khi vận hành, hãy giữ một cơ chế export rõ ràng cho mỗi MBean và xác minh kết quả bằng JMX metadata thực tế.