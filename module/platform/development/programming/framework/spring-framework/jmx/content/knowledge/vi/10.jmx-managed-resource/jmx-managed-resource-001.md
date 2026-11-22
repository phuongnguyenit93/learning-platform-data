# @ManagedResource đánh dấu bean được quản lý qua JMX trong Spring Framework

## 1. Mục tiêu học tập

Trong Spring Framework JMX, annotation `@ManagedResource` đánh dấu một lớp Java là **managed resource** mà Spring có thể xuất (export) sang Java Management Extensions (JMX). Annotation này là điểm bắt đầu của cách cấu hình JMX dựa trên metadata: nó mô tả danh tính và ý nghĩa của một resource, còn những attribute và operation cụ thể được công bố qua annotation tương ứng.

Sau bài học, bạn có thể:

- Giải thích `@ManagedResource` thuộc thành phần nào của Spring và khác gì với `@Component` hay các annotation của Spring Boot Actuator.
- Biết cách khai báo `objectName`, `description` và lựa chọn metadata của managed resource.
- Hiểu vai trò của `MBeanExporter`, `AnnotationJmxAttributeSource` và `MetadataMBeanInfoAssembler`.
- Viết một bean có `@ManagedResource` cùng các attribute/operation cần thiết, đăng ký vào `MBeanServer` và đọc được từ JMX client.
- Phân biệt **đánh dấu resource** với **đăng ký MBean thực tế**, đồng thời nhận biết các tình huống không có MBean sau khi thêm annotation.
- Quản lý ObjectName, phạm vi công khai, lifecycle và bảo mật khi ứng dụng có nhiều bean.

## 2. @ManagedResource là gì?

`@ManagedResource` nằm trong package:

```java
org.springframework.jmx.export.annotation.ManagedResource
```

Annotation này có thể đặt trên lớp được Spring export thành MBean. Nó cung cấp metadata ở cấp resource để Spring xây dựng mô hình `MBeanInfo` và định danh MBean phù hợp với cấu hình exporter.

Ví dụ tối thiểu:

```java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main",
    description = "Runtime cache monitoring resource"
)
public class CacheMonitor {
}
```

Ở đây:

- `objectName` là tên JMX định danh MBean trong một `MBeanServer`.
- `description` là mô tả kỹ thuật cho resource, có thể được công cụ quản trị hiển thị khi đọc `MBeanInfo`.
- Bản thân annotation **không tạo network endpoint**, không mở JMX Remote, không bảo đảm bean được đăng ký và không tự công bố mọi method public.

Để một resource có ích, thường cần đánh dấu các thành phần bên trong bằng `@ManagedAttribute` và `@ManagedOperation`, đồng thời cấu hình Spring JMX để đọc metadata và export bean.

## 3. ManagedResource và các khái niệm liên quan

```text
Spring ApplicationContext
       |
       +-- Bean quản trị (class)
       |       @ManagedResource
       |       @ManagedAttribute
       |       @ManagedOperation
       |
       +-- AnnotationJmxAttributeSource
       |       đọc metadata annotation
       |
       +-- MetadataMBeanInfoAssembler
       |       tạo giao diện quản trị JMX
       |
       +-- MBeanExporter
               |
               | đăng ký với ObjectName
               v
           MBeanServer
               |
               +--> MBeanInfo / attributes / operations
               +--> JMX client: JConsole, code quản trị
```

Các vai trò khác nhau:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `@ManagedResource` | Đánh dấu resource và mô tả metadata cấp lớp |
| `@ManagedAttribute` | Mô tả một thuộc tính quản trị đọc/ghi |
| `@ManagedOperation` | Mô tả một thao tác quản trị có thể gọi |
| `AnnotationJmxAttributeSource` | Đọc annotation JMX của Spring |
| `MetadataMBeanInfoAssembler` | Chuyển metadata thành các thành phần `MBeanInfo` |
| `MBeanExporter` | Đăng ký bean vào một `MBeanServer` |
| `ObjectName` | Định danh MBean trong registry của JMX |
| `MBeanServer` | Server quản lý MBean và nhận yêu cầu quản trị |

Cần tách bạch ba bước: **đánh dấu bằng annotation → Spring đọc metadata → exporter đăng ký vào server**. Một bước thành công không thay thế các bước còn lại.

## 4. Ví dụ bean đầy đủ có @ManagedResource

Giả sử ứng dụng muốn quan sát bộ đệm runtime và hỗ trợ xóa số liệu đếm theo nhu cầu vận hành. Bean sau thể hiện trạng thái quản trị đơn giản:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main",
    description = "Management view of application cache counters"
)
public class CacheMonitor {

    private final AtomicInteger entryCount = new AtomicInteger();
    private volatile boolean enabled = true;

    @ManagedAttribute(
        description = "Current number of recorded cache entries"
    )
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedAttribute(description = "Whether tracking is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Enable or disable tracking")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Reset the entry counter")
    public void resetCounter() {
        entryCount.set(0);
    }

    public void recordEntry() {
        if (enabled) {
            entryCount.incrementAndGet();
        }
    }
}
```

Ý nghĩa của từng annotation:

- `@ManagedResource` áp dụng cho lớp `CacheMonitor`: đây là resource mà JMX metadata có thể mô tả.
- Getter `getEntryCount()` có `@ManagedAttribute`: công bố attribute `EntryCount` chỉ đọc.
- Getter và setter `isEnabled()` / `setEnabled(...)` được đánh dấu: công bố `Enabled` đọc và ghi.
- `resetCounter()` có `@ManagedOperation`: công bố một operation có tác dụng thay đổi trạng thái.
- `recordEntry()` không được đánh dấu: đây là phương thức nghiệp vụ nội bộ, không được assembler dựa trên annotation công bố chỉ vì nó public.

Bề mặt quản trị JMX cần được thiết kế riêng, không nên tương ứng với mọi API công khai trên bean. Đặc biệt với operation thay đổi trạng thái, hãy kiểm soát ai được gọi và kết quả thực hiện.

## 5. Đưa bean vào Spring ApplicationContext

Annotation JMX không đồng nghĩa với Spring component registration. Nếu muốn Spring quản lý bean, có thể khai báo `@Bean`:

```java
package com.example.monitoring;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MonitorBeanConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }
}
```

Hoặc đặt `@Component` trên class và kích hoạt component scanning phù hợp.

```java
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main"
)
public class CacheMonitor {
    // ...
}
```

Hai annotation phục vụ hai hệ thống khác nhau:

- `@Component` giúp Spring phát hiện và tạo bean trong `ApplicationContext`.
- `@ManagedResource` cung cấp metadata JMX để bean có thể được export thành resource quản trị.

Một class chỉ có `@ManagedResource` mà không được tạo thành bean hoặc không được đưa vào `MBeanExporter` thì chưa chắc có đối tượng nào trong JMX registry. Ngược lại, một `@Component` thông thường chưa chắc được công bố thành MBean.

## 6. Cấu hình export dựa trên annotation

### 6.1. Cách khai báo annotation-driven

Spring hỗ trợ cấu hình kích hoạt xuất MBean dựa trên annotation; trong Java configuration có thể dùng `@EnableMBeanExport`:

```java
package com.example.monitoring;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
```

Khi cơ chế này được kích hoạt trong context chứa bean `CacheMonitor`, Spring thiết lập hạ tầng exporter để tìm và xử lý các managed resource đã được đánh dấu. Các chi tiết như lựa chọn server, naming và registration policy có thể được điều chỉnh theo cấu hình của Spring và phiên bản đang sử dụng.

Ví dụ khởi động ứng dụng Spring độc lập:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(
            MonitorBeanConfig.class,
            JmxExportConfig.class
        )) {

    // JMX exporter được khởi tạo cùng ApplicationContext.
    // Có thể kiểm tra MBean trên MBeanServer đã chọn.
}
```

Đây là lựa chọn ngắn gọn cho bài thực hành. Nó chỉ có tác dụng trong `ApplicationContext` nhận được cấu hình; không tự áp dụng cho mọi context khác cùng JVM.

### 6.2. Cấu hình thủ công để thấy rõ vai trò các thành phần

Có thể cấu hình `MBeanExporter` và metadata assembler tường minh:

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

@Configuration
public class ExplicitJmxConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
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
    public MBeanExporter mbeanExporter(
            CacheMonitor cacheMonitor,
            MBeanServer jmxServer,
            MetadataMBeanInfoAssembler assembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=CacheMonitor,name=Main",
            cacheMonitor
        ));
        exporter.setAssembler(assembler);
        return exporter;
    }
}
```

Trong cấu hình này:

1. `CacheMonitor` được Spring tạo.
2. `jmxServer` chọn platform MBeanServer của JVM.
3. `AnnotationJmxAttributeSource` đọc metadata từ annotation trên class/method.
4. `MetadataMBeanInfoAssembler` xây dựng mô hình JMX từ metadata đó.
5. `MBeanExporter` đăng ký bean theo ObjectName cụ thể.

Ví dụ trên chỉ dùng **một** cơ chế exporter. Không nên vừa khai báo `@EnableMBeanExport` vừa tạo exporter thủ công cho cùng bean nếu không có thiết kế rõ ràng, vì có thể đăng ký trùng tên.

### 6.3. Khai báo ObjectName ở đâu?

Ví dụ `@ManagedResource(objectName = "...")` cho thấy định danh mong muốn trong metadata. Khi gọi `MBeanExporter.setBeans(Map.of("...", bean))`, exporter cũng nhận tên đăng ký tường minh.

Hai thông tin cần nhất quán. Nếu muốn ObjectName lấy trực tiếp từ annotation, cần dùng naming strategy hoặc cơ chế annotation-driven có hỗ trợ metadata tương ứng. Nếu muốn dễ kiểm soát khi cấu hình thủ công, có thể giữ tên tường minh trong `setBeans(...)` và dùng cùng chuỗi trong annotation để tránh mâu thuẫn.

## 7. Các thuộc tính quan trọng của @ManagedResource

`@ManagedResource` có những phần metadata phục vụ mô tả và nhận diện MBean, trong đó `objectName` và `description` là hai thông tin thường gặp nhất.

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main",
    description = "Cache counters for operational monitoring"
)
```

### 7.1. objectName

`objectName` mô tả tên JMX, theo cấu trúc:

```text
domain:key=value,key2=value2
```

Ví dụ:

```text
com.example.monitoring:type=CacheMonitor,name=Main
```

ObjectName là khóa JMX, không phải tên class, tên bean Spring hoặc tiêu đề thân thiện của dashboard. Nó cần hợp lệ theo cú pháp `javax.management.ObjectName` và duy nhất trong một MBeanServer.

Nếu có nhiều instance cùng loại, hãy phân biệt bằng key property:

```text
com.example.monitoring:type=CacheMonitor,name=Main,instance=1
com.example.monitoring:type=CacheMonitor,name=Main,instance=2
```

Tên ổn định rất quan trọng vì JConsole, công cụ giám sát, alert rule và script có thể lưu ObjectName để truy cập. Đổi tên có thể làm các client cũ không tìm thấy MBean.

### 7.2. description

Description giúp người vận hành hiểu MBean hoặc thành phần quản trị:

```java
@ManagedResource(
    description = "Runtime management of application cache counters"
)
```

Mô tả có thể được metadata assembler đưa vào `MBeanInfo`. Nó khác với ObjectName: description dành cho người đọc, còn ObjectName phục vụ định tuyến. Một dashboard có thể hiển thị description như trợ giúp, nhưng không nên sử dụng nó làm khóa duy nhất.

### 7.3. Những metadata quản trị bổ sung

Các phiên bản Spring Framework còn hỗ trợ nhiều thuộc tính metadata khác cho resource như `currencyTimeLimit`, `log`, `logFile`, `persistPolicy`, `persistPeriod`, `persistName`, `persistLocation`. Ý nghĩa của chúng liên quan tới mô tả quản trị và mô hình metadata JMX, nhưng **không đồng nghĩa Spring tự cung cấp hệ thống persistence, logging hay giao thức remote** cho mọi resource chỉ vì annotation có trường tương ứng.

Khi cần các thuộc tính này, phải kiểm tra ý nghĩa cụ thể trong Spring version và kiểu MBean/assembler được dùng. Đối với bài toán thông thường, bắt đầu bằng `objectName`, `description` và các `@ManagedAttribute` / `@ManagedOperation` cần thiết là lựa chọn dễ hiểu.

## 8. Đọc MBean sau khi export

Sau khi context khởi tạo, có thể dùng Java JMX API để kiểm tra resource đã được đăng ký và metadata có đúng không.

```java
import java.lang.management.ManagementFactory;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=CacheMonitor,name=Main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean was not exported: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);
System.out.println("MBean: " + name.getCanonicalName());
System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
```

Nếu exporter được cấu hình vào server khác, ví dụ server do container quản lý hoặc `MBeanServerFactoryBean` tạo riêng, thì phải kiểm tra trên **đúng server đó**. Một MBean có thể đăng ký thành công nhưng không xuất hiện trong platform server vì exporter dùng server khác.

Khi metadata được cấu hình như phần 4, kết quả dự kiến gồm:

| Attribute | Đọc | Ghi |
| --- | --- | --- |
| `EntryCount` | Có | Không |
| `Enabled` | Có | Có |

Có thể đọc và ghi:

```java
import javax.management.Attribute;

int entries = (Integer) server.getAttribute(
    name, "EntryCount"
);

server.setAttribute(
    name, new Attribute("Enabled", Boolean.FALSE)
);

boolean enabled = (Boolean) server.getAttribute(
    name, "Enabled"
);
```

Không nên thử ghi `EntryCount` vì metadata chỉ công bố getter, không có setter quản trị. Nếu `getAttribute` hoặc `setAttribute` lỗi, cần phân biệt lỗi tên, quyền đọc/ghi, kiểu dữ liệu và lỗi từ logic bean.

## 9. @ManagedResource và @ManagedAttribute khác nhau thế nào?

Hai annotation có phạm vi khác nhau:

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main"
)
public class CacheMonitor {

    @ManagedAttribute
    public int getEntryCount() {
        return 42;
    }
}
```

- `@ManagedResource` nói **đây là resource được mô tả để quản lý qua JMX**.
- `@ManagedAttribute` nói **phương thức tương ứng được mô tả thành attribute quản trị**.
- `@ManagedOperation` nói **phương thức tương ứng được mô tả thành operation quản trị**.

Một class có `@ManagedResource` không có nghĩa tất cả method public đều trở thành operation hoặc mọi getter đều thành attribute. Khi dùng `MetadataMBeanInfoAssembler`, metadata của từng thành phần quyết định bề mặt được công bố.

Các annotation cũng không có nghĩa mọi thao tác đều an toàn. Nếu annotation đặt trên setter hoặc operation thay đổi cấu hình runtime, cần xem xét bảo mật và quyền sử dụng.

## 10. Quan hệ với @Component, @Bean và Spring Boot

### 10.1. @ManagedResource không phải stereotype của Spring container

`@ManagedResource` đánh dấu vai trò trong JMX. Spring container vẫn cần biết cách tạo instance:

```java
@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main"
)
public class CacheMonitor {
}
```

hoặc:

```java
@Bean
CacheMonitor cacheMonitor() {
    return new CacheMonitor();
}
```

Không nên lẫn cơ chế **phát hiện bean** với cơ chế **export bean**.

### 10.2. Spring Boot Actuator không đồng nghĩa với JMX core

Spring Boot Actuator có cơ chế quản trị và metrics riêng, có thể cung cấp JMX endpoints trong một số cấu hình. Những endpoint đó là chức năng của Spring Boot Actuator và phụ thuộc dependency, cấu hình exposure, phiên bản, bảo mật. Còn `@ManagedResource` và `MBeanExporter` thuộc Spring Framework JMX.

Có thể dùng Spring Framework JMX trong ứng dụng Spring Boot, nhưng không nên suy luận rằng thêm `@ManagedResource` sẽ tự bật mọi endpoint Actuator hay mở HTTP management path.

### 10.3. Spring bean lifecycle và MBean lifecycle

Bean Spring được tạo, cấu hình và tiêu hủy theo `ApplicationContext`. Exporter tham gia vào lifecycle để đăng ký/hủy đăng ký MBean. Khi context đóng, những MBean do exporter sở hữu thường được dọn tương ứng.

Nếu bean được đăng ký trực tiếp bên ngoài Spring, việc hủy đăng ký cần được chủ sở hữu của đăng ký đó quản lý. Tránh tự unregister MBean thuộc container hoặc thành phần khác.

## 11. Những lỗi thường gặp

### 11.1. Có annotation nhưng không thấy MBean

Nguyên nhân thường gặp:

- Class có `@ManagedResource` nhưng chưa tạo bean trong Spring context.
- Chưa kích hoạt hạ tầng export JMX hoặc exporter không được khởi tạo.
- Cấu hình thủ công có exporter nhưng thiếu metadata assembler/attribute source phù hợp.
- Exporter đăng ký vào MBeanServer khác với server công cụ đang kết nối.
- ObjectName không hợp lệ, bị trùng hoặc cấu hình naming không như mong đợi.
- Cấu hình Spring JMX nằm trong context khác với bean cần export.
- Lỗi khởi tạo của bean hoặc lifecycle khiến exporter không đăng ký thành công.

Cách chẩn đoán: kiểm tra Bean có trong `ApplicationContext`; xác minh exporter có chạy; xác nhận server và ObjectName; gọi `isRegistered(name)`; sau đó đọc `MBeanInfo`.

### 11.2. MBean hiện ra nhưng thiếu attribute/operation

Đầu tiên kiểm tra:

1. Getter/setter hoặc operation có annotation phù hợp không?
2. Assembler đang dùng có đọc annotation của Spring không?
3. Method có chữ ký hợp lệ theo mô hình JMX được tạo không?
4. Có cấu hình export khác thay thế cách assembler công bố interface không?
5. Có đang nhìn nhầm một MBean khác có cùng tên ở server khác không?

Nếu `MBeanInfo` không có attribute mong đợi, việc gọi `getAttribute` sẽ không làm nó xuất hiện. Phải sửa contract export/metadata rồi khởi tạo lại theo lifecycle thích hợp.

### 11.3. MBean trùng ObjectName

ObjectName phải duy nhất trong một MBeanServer. Nếu hai exporters hoặc hai resource cùng đăng ký:

```text
com.example.monitoring:type=CacheMonitor,name=Main
```

có thể phát sinh `InstanceAlreadyExistsException` hoặc chính sách registration khác. Cần đặt tên phân biệt instance và kiểm tra ai sở hữu đăng ký. Không tự động thay thế MBean hiện có nếu không hiểu nguồn gốc của nó.

### 11.4. Dùng nhầm tên Spring bean làm ObjectName

Ví dụ tên bean là `cacheMonitor`, nhưng ObjectName là:

```text
com.example.monitoring:type=CacheMonitor,name=Main
```

Client JMX phải dùng ObjectName đã đăng ký. Tên bean Spring là định danh trong container, không phải tên JMX mặc định trong mọi trường hợp.

## 12. Tình huống thực tế và quyết định thiết kế

### 12.1. Resource đọc trạng thái

Một bộ đo số kết nối hiện tại chỉ cần getter:

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=ConnectionStats,name=Primary"
)
public class ConnectionStats {

    @ManagedAttribute(description = "Active connection count")
    public int getActiveConnections() {
        return 0; // Minh họa, ứng dụng thật đọc từ bộ đếm runtime
    }
}
```

Đây là trường hợp tốt cho JMX: interface quản trị chỉ đọc, không phơi bày thao tác can thiệp nguy hiểm.

### 12.2. Resource cho phép thay đổi cấu hình

Một bean có `@ManagedAttribute` trên setter `setEnabled(boolean)` cho phép quản trị viên thay đổi trạng thái. Nhưng hệ thống phải thiết kế:

- Thay đổi có áp dụng ngay hay sau chu kỳ refresh?
- Có điều kiện trạng thái nào khiến setter từ chối?
- Có cần audit ai thay đổi, từ công cụ nào và khi nào?
- Client từ xa có được phép ghi hay chỉ đọc?
- Có cần giới hạn tần suất hoặc thêm operation xác nhận?

Một annotation chỉ mô tả khả năng quản trị, không tự bảo đảm authorization hoặc tính đúng của quy tắc nghiệp vụ.

### 12.3. Nhiều instance cùng loại

Nếu ứng dụng chạy nhiều module hoặc cùng loại bean xuất nhiều instance trong một JVM, hãy dùng ObjectName có key khác nhau:

```text
com.example.monitoring:type=ConnectionStats,name=Primary
com.example.monitoring:type=ConnectionStats,name=Replica
```

Trên nhiều JVM, cùng ObjectName có thể tồn tại ở những MBeanServer khác nhau. Dashboard giám sát nhiều server cần giữ thêm danh tính connection hoặc host, không chỉ lưu ObjectName.

## 13. Bài tập thực hành

Hãy tạo một Spring application chứa bean `CacheMonitor` từ phần 4 và thực hiện:

1. Khởi tạo bean trong `ApplicationContext`.
2. Kích hoạt `@EnableMBeanExport` **hoặc** cấu hình `MBeanExporter` + `MetadataMBeanInfoAssembler` thủ công.
3. Dùng platform MBeanServer trong cùng JVM để kiểm tra ObjectName:
   `com.example.monitoring:type=CacheMonitor,name=Main`.
4. Đọc `MBeanInfo.getDescription()` và danh sách attribute/operation.
5. Gọi `getAttribute(name, "EntryCount")` và `getAttribute(name, "Enabled")`.
6. Ghi `Enabled=false`, đọc lại và quan sát kết quả.
7. Gọi operation `resetCounter()` qua `MBeanServer.invoke(...)` nếu nó đã được công bố.
8. Thử gọi một method nội bộ không có `@ManagedOperation` qua JMX và quan sát kết quả.
9. Đóng Spring context, xác nhận exporter đã thực hiện vòng đời hủy đăng ký đúng với resource mà nó sở hữu.

Ví dụ gọi operation:

```java
server.invoke(
    name,
    "resetCounter",
    new Object[0],
    new String[0]
);
```

Sau đó:

```java
int current = (Integer) server.getAttribute(name, "EntryCount");
System.out.println("Entry count = " + current);
```

Nếu kết quả khác mong đợi, kiểm tra có tiến trình ứng dụng đang đồng thời tăng bộ đếm hoặc một MBean khác được truy cập hay không.

## 14. Câu hỏi tự kiểm tra

**1. `@ManagedResource` thuộc JDK hay Spring Framework?** Nó thuộc `org.springframework.jmx.export.annotation` của Spring Framework.

**2. Thêm `@ManagedResource` trên class có tự đăng ký vào MBeanServer không?** Không. Cần bean instance và hạ tầng exporter xử lý metadata/đăng ký.

**3. Annotation nào công bố một getter thành JMX attribute theo cơ chế metadata?** `@ManagedAttribute`.

**4. Annotation nào dùng để mô tả một operation quản trị?** `@ManagedOperation`.

**5. `objectName` trong `@ManagedResource` có nghĩa gì?** Định danh JMX dự kiến cho resource trong một MBeanServer.

**6. `description` khác ObjectName thế nào?** Description là mô tả hiển thị; ObjectName là khóa định tuyến JMX.

**7. Khi không thấy MBean trong JConsole, có nên kết luận annotation sai ngay không?** Không. Cần kiểm tra bean, exporter, server, ObjectName và đường kết nối của JConsole.

**8. `@ManagedResource` và `@Component` có thay thế nhau không?** Không; một annotation mô tả JMX, annotation còn lại hỗ trợ đăng ký Spring bean.

**9. Có thể dùng JMX annotation trong Spring Boot không?** Có, vì Spring Boot dựa trên Spring Framework; vẫn cần cấu hình export và exposure phù hợp.

**10. Vì sao không nên export tất cả method public?** Vì giao diện JMX là bề mặt quản trị có thể được truy cập từ công cụ vận hành; chỉ nên công bố thành phần cần thiết và an toàn.

## 15. Ghi nhớ

- **`@ManagedResource` đánh dấu lớp** là resource có metadata quản trị qua JMX.
- **`@ManagedAttribute` và `@ManagedOperation`** mô tả các thành phần cụ thể được công bố.
- **`MBeanExporter`** chịu trách nhiệm đưa đối tượng vào `MBeanServer`.
- **`AnnotationJmxAttributeSource` và `MetadataMBeanInfoAssembler`** giúp Spring đọc annotation và tạo JMX metadata.
- **Annotation không thay thế việc tạo Spring bean**, không tự bật remote connector hoặc Actuator.
- **ObjectName phải hợp lệ, duy nhất trong server và ổn định** cho các client quản trị.
- **Chỉ công bố giao diện quản trị cần thiết**, kiểm soát thao tác có side effect và đảm bảo bảo mật khi cho phép truy cập từ xa.

Khi sử dụng `@ManagedResource`, hãy nghĩ theo luồng: **bean Spring → metadata JMX → exporter → MBeanServer → JMX client**. Chính sự tách bạch này giúp cấu hình Spring Framework JMX có chủ đích và dễ chẩn đoán khi một resource chưa xuất hiện hoặc chưa có đúng giao diện quản trị.