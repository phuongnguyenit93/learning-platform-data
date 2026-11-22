# ObjectName, description và class-level metadata trong @ManagedResource

## 1. Mục tiêu bài học

Trong Spring Framework JMX, annotation \`@ManagedResource\` mô tả **một bean được quản trị** ở cấp lớp. Những thông tin quan trọng nhất là \`objectName\` (định danh JMX) và \`description\` (mô tả cho công cụ quản trị), cùng một số thuộc tính metadata như \`currencyTimeLimit\`, \`log\`, \`logFile\`, \`persistPolicy\`, \`persistPeriod\` và \`persistName\`.

Điểm cốt lõi: annotation là **metadata khai báo**. Để metadata có hiệu lực trong JMX, Spring phải có cơ chế export thích hợp, thường là \`MBeanExporter\` cùng bộ đọc annotation, assembler và naming strategy được cấu hình đồng bộ. Annotation không tự gọi \`MBeanServer.registerMBean()\`.

Sau bài này, bạn có thể:
- Giải thích vai trò của \`@ManagedResource\` ở cấp lớp và phân biệt với \`@ManagedAttribute\`, \`@ManagedOperation\`.
- Đặt và kiểm tra \`ObjectName\` theo cú pháp JMX.
- Hiểu ý nghĩa \`description\` và các trường metadata khác, cũng như giới hạn tác dụng thực tế của chúng.
- Cấu hình Spring export để metadata được phản ánh trong \`MBeanInfo\`.
- Tránh các lỗi thường gặp về tên trùng, wildcard, giá trị động, cấu hình exporter và nhầm lẫn giữa metadata với hành vi runtime.

## 2. Bức tranh tổng thể

\`\`\`text
Spring bean
   |
   | @ManagedResource(objectName=..., description=..., ...)
   | @ManagedAttribute / @ManagedOperation
   v
AnnotationJmxAttributeSource
   |
   +--> MetadataNamingStrategy ------> ObjectName
   |
   +--> MetadataMBeanInfoAssembler --> MBeanInfo
   |
   v
MBeanExporter
   |
   | register / adapt bean
   v
MBeanServer
   |
   v
JConsole / VisualVM / JMX client
\`\`\`

Các vai trò:

| Thành phần | Trách nhiệm |
|---|---|
| \`@ManagedResource\` | Cung cấp metadata quản trị cấp lớp; đặc biệt \`objectName\`, \`description\` |
| \`AnnotationJmxAttributeSource\` | Đọc annotation và tạo metadata nội bộ mà Spring JMX sử dụng |
| \`MetadataNamingStrategy\` | Dựa vào metadata để xác định tên MBean |
| \`MetadataMBeanInfoAssembler\` | Chuyển metadata quản trị thành thông tin MBean được công bố |
| \`MBeanExporter\` | Xuất Spring bean sang \`MBeanServer\`, áp dụng naming và assembly |
| \`MBeanServer\` | Registry của JMX MBeans; truy vấn bằng \`ObjectName\` |
| \`MBeanInfo\` | Mô tả MBean và giao diện quản trị (attributes, operations, notifications...) |

Không phải mọi \`@Component\` đều tự được export; không phải mọi \`@ManagedResource\` đều tự động xuất hiện trong JConsole nếu cơ chế JMX export chưa được kích hoạt.

## 3. @ManagedResource là annotation cấp lớp

Ví dụ:

\`\`\`java
package com.example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache administration"
)
public class ProductCacheMonitor {
    private volatile int entryCount;

    @ManagedAttribute(description = "Current cached entries")
    public int getEntryCount() {
        return entryCount;
    }

    @ManagedOperation(description = "Clear cached entries")
    public void clear() {
        entryCount = 0;
    }
}
\`\`\`

Trong ví dụ này:

- \`@Component\` khiến đối tượng trở thành Spring bean khi được component scan.
- \`@ManagedResource\` mô tả bean là một đối tượng quản trị ở mức lớp, với JMX name và description.
- \`@ManagedAttribute\` chỉ ra getter \`getEntryCount()\` cần được expose như một JMX attribute.
- \`@ManagedOperation\` chỉ ra \`clear()\` cần được expose như một JMX operation.
- Cần bật exporter phù hợp thì client JMX mới nhìn thấy MBean.

**Phạm vi annotation:** \`@ManagedResource\` áp dụng cho kiểu/lớp; metadata ở mức phương thức hoặc thuộc tính quản trị được khai báo bằng những annotation riêng. Không coi \`@ManagedResource\` là chỉ thị công bố toàn bộ method public.

## 4. objectName: định danh JMX của MBean

### 4.1. Cú pháp và ý nghĩa

JMX \`ObjectName\` thường có dạng:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Ví dụ:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
com.example.monitoring:type=Worker,name=Import
java.lang:type=Memory
\`\`\`

Một \`ObjectName\` gồm:
- **Domain:** vùng tên như \`com.example.monitoring\`.
- **Key properties:** danh sách cặp key/value, ví dụ \`type=Cache\`, \`name=Products\`.
- **Concrete name hoặc pattern:** wildcard \`*\`/\`?\` có thể biến tên thành mẫu truy vấn. Khi đăng ký một MBean riêng lẻ, cần concrete name.

ObjectName là **định danh JMX**, không phải:
- tên Spring bean trong \`ApplicationContext\`;
- Java package/class name;
- URI hoặc HTTP endpoint;
- tên metric Micrometer.

Spring bean \`productCacheMonitor\` có thể được export bằng ObjectName \`com.example.monitoring:type=Cache,name=Products\`; chúng sống trong hai namespace khác nhau.

### 4.2. Vì sao objectName quan trọng?

\`ObjectName\` là khóa định danh dùng trong \`MBeanServer\`. Client gọi:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);
boolean exists = server.isRegistered(name);
\`\`\`

để truy vấn MBean ở **MBeanServer cụ thể**.

Nếu hai exporter cố đăng ký hai MBean khác nhau với cùng \`ObjectName\` trên cùng server, sẽ có xung đột đăng ký. Chính sách của exporter quyết định việc fail, ignore hoặc replace, nhưng không nên dùng policy để che một lỗi đặt tên.

### 4.3. ObjectName không phụ thuộc thứ tự key

Hai tên có thể tương đương:

\`\`\`java
ObjectName first = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

ObjectName second = new ObjectName(
    "com.example.monitoring:name=Products,type=Cache"
);

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
\`\`\`

Dùng \`ObjectName.equals()\` hoặc \`getCanonicalName()\` để so sánh theo quy tắc JMX; tránh dựa vào thứ tự chuỗi gốc.

### 4.4. Không ghép giá trị động tùy tiện vào annotation

Giá trị \`objectName\` trong annotation được khai báo tĩnh khi biên dịch:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
\`\`\`

Không thể đặt một biến Java runtime vào attribute annotation theo cách thông thường:

\`\`\`java
// Không hợp lệ nếu runtimeName là biến tính tại runtime:
// @ManagedResource(objectName = "com.example:type=Cache,name=" + runtimeName)
\`\`\`

Nếu ObjectName cần dựa vào tenant, instance hoặc cấu hình runtime, hãy lựa chọn naming strategy/registration programmatic phù hợp và tạo \`ObjectName\` qua Java API.

Ví dụ:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

String dynamicName = "Products,EU=West";

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Cache");
properties.put("name", ObjectName.quote(dynamicName));

ObjectName name =
    new ObjectName("com.example.monitoring", properties);
\`\`\`

\`ObjectName.quote(dynamicName)\` bảo vệ ý nghĩa literal của dữ liệu có dấu phân cách hoặc wildcard. Không áp dụng \`quote()\` cho toàn bộ ObjectName; chỉ quote **giá trị property** theo nhu cầu.

### 4.5. Tránh ObjectName pattern trong đăng ký

Ví dụ:

\`\`\`java
ObjectName pattern =
    new ObjectName("com.example.monitoring:type=Cache,*");

System.out.println(pattern.isPattern()); // true
\`\`\`

Tên này phù hợp cho \`queryNames()\` nhưng không phải một tên cụ thể dùng để đăng ký MBean. Nếu \`@ManagedResource.objectName\` được cấu hình thành pattern ngoài ý muốn, việc export có thể thất bại.

## 5. description: metadata giúp công cụ quản trị hiểu MBean

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache administration"
)
\`\`\`

\`description\` cung cấp mô tả ở mức MBean. Khi assembler đọc annotation và tạo \`MBeanInfo\`, mô tả có thể được client xem qua API hoặc giao diện như JConsole.

Để đọc bằng Java:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

MBeanInfo info = server.getMBeanInfo(name);
System.out.println(info.getDescription());
\`\`\`

**Điều quan trọng:** \`description\` là thông tin cho người vận hành và client, không tự:
- tạo JMX attribute/operation;
- bảo đảm một operation an toàn;
- bật authentication/authorization;
- cấu hình log hoặc metrics;
- thay đổi nghiệp vụ của bean.

Chọn mô tả ngắn, rõ ràng và bám đúng mục đích quản trị của MBean. Ví dụ \`"Product cache administration"\` có ích hơn \`"My Bean"\`.

### 5.1. Description cấp lớp và cấp method

\`\`\`java
@ManagedResource(description = "Product cache administration")
public class ProductCacheMonitor {

    @ManagedAttribute(
        description = "Current number of cache entries"
    )
    public int getEntryCount() {
        return 42;
    }
}
\`\`\`

Mô tả cấp lớp nằm ở \`MBeanInfo.getDescription()\`. Mô tả của attribute được trình bày trong metadata thuộc tính, chẳng hạn \`MBeanAttributeInfo.getDescription()\`.

Không dùng \`@ManagedResource.description\` để thay cho metadata ở mọi attribute hoặc operation; mỗi cấp có ý nghĩa riêng.

## 6. Các trường metadata cấp lớp khác

\`@ManagedResource\` còn khai báo những trường liên quan đến metadata quản trị JMX:

| Thuộc tính | Ý nghĩa | Điểm cần nhớ |
|---|---|---|
| \`objectName\` | Tên JMX của MBean | Là định danh; cần tên hợp lệ và tránh trùng |
| \`description\` | Mô tả MBean | Dành cho client/operator; không tự thay đổi hành vi |
| \`currencyTimeLimit\` | Gợi ý giới hạn thời gian hiệu lực của thông tin quản trị trong metadata/model MBean | Không phải HTTP timeout hoặc retry policy |
| \`log\` | Metadata liên quan tính năng logging của Model MBean | Không tự bảo đảm có log ứng dụng |
| \`logFile\` | Thông tin đường dẫn log cho tính năng Model MBean | Không đồng nghĩa cấu hình SLF4J/Logback |
| \`persistPolicy\` | Metadata gợi ý chính sách persistence của Model MBean | Không tự tạo database transaction |
| \`persistPeriod\` | Tham số thời gian của persistence policy | Có ý nghĩa khi cơ chế tương ứng hỗ trợ |
| \`persistName\` | Tên liên quan tài nguyên persistence | Không thay thế kho lưu trữ ứng dụng |
| \`persistLocation\` | Vị trí persistence trong metadata | Không tự triển khai durable storage |

Các trường ngoài \`objectName\` và \`description\` liên quan khả năng và descriptor của JMX Model MBean. **Đừng suy luận rằng chỉ cần gắn annotation thì ứng dụng tự bật ghi file, định kỳ lưu trạng thái hoặc áp dụng cache theo thời gian.** Tác dụng runtime phụ thuộc exporter, assembler, Model MBean implementation và cấu hình vận hành.

### Ví dụ metadata mở rộng

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache administration",
    currencyTimeLimit = 15,
    log = false
)
public class ProductCacheMonitor {
    // ...
}
\`\`\`

Ở đây \`currencyTimeLimit\` là metadata quản trị được đưa vào descriptor theo khả năng hỗ trợ, không phải timeout 15 giây cho mỗi method Java hay TTL của cache nghiệp vụ. Mọi tác dụng phụ như cache kết quả MBean hoặc cập nhật descriptor cần được kiểm tra với JMX implementation được dùng.

Đối với hệ thống thực tế, chỉ khai báo các trường Model MBean mà bạn hiểu rõ tác dụng và có nhu cầu vận hành. Khi chỉ cần tên và mô tả, cấu hình tối giản thường dễ bảo trì hơn.

## 7. Spring đọc và áp dụng metadata như thế nào?

Một Spring bean có \`@ManagedResource\` chưa tự trở thành MBean. Có thể dùng annotation-driven export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Cần kết hợp với component scanning hoặc \`@Bean\` để tạo bean đích.

Hoặc cấu hình \`MBeanExporter\` tường minh:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public MBeanExporter mBeanExporter() {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

Hai đoạn cấu hình là **hai cách thay thế**; trong một context không nên tạo nhiều exporter trùng trách nhiệm. Khi dùng Spring Boot, kiểm tra auto-configuration JMX và property như \`spring.jmx.enabled\` trước khi thêm cấu hình thủ công.

### Thứ tự trách nhiệm

1. Spring tạo bean \`ProductCacheMonitor\`.
2. Exporter chọn bean, trực tiếp hoặc qua autodetect.
3. \`AnnotationJmxAttributeSource\` lấy class-level metadata từ \`@ManagedResource\`.
4. \`MetadataNamingStrategy\` lấy ObjectName phù hợp.
5. \`MetadataMBeanInfoAssembler\` mô tả attribute/operation và descriptor.
6. \`MBeanExporter\` đăng ký MBean vào \`MBeanServer\`.
7. JMX client đọc \`MBeanInfo\`, attribute hoặc gọi operation.

Nếu exporter không được kích hoạt, chuỗi xử lý này không diễn ra chỉ nhờ có annotation trên class.

## 8. Phân biệt class-level metadata với member-level metadata

\`@ManagedResource\` được gắn lên lớp và mô tả toàn bộ tài nguyên quản trị.

Các annotation thường đi kèm:

- \`@ManagedAttribute\` trên getter/setter được expose như JMX attribute.
- \`@ManagedOperation\` trên method được expose như JMX operation.
- \`@ManagedOperationParameter\` trên metadata tham số của một operation trong ngữ cảnh phù hợp.
- \`@ManagedNotification\` khai báo notification metadata cho MBean.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import",
    description = "Import worker administrator"
)
@ManagedNotification(
    name = "com.example.import.failed",
    description = "Import failed",
    notificationTypes = {"com.example.import.failed"}
)
public class ImportWorkerMonitor {

    @ManagedAttribute(description = "Current state")
    public String getState() {
        return "IDLE";
    }

    @ManagedOperation(description = "Request a state refresh")
    public void refresh() {
        // Request refresh from business component.
    }
}
\`\`\`

Tương ứng:

\`\`\`text
@ManagedResource
  -> mô tả MBean và ObjectName cấp lớp

@ManagedAttribute
  -> mô tả một JMX attribute

@ManagedOperation
  -> mô tả một JMX operation

@ManagedNotification
  -> mô tả loại notification có thể được công bố
\`\`\`

**Khai báo notification metadata** không đồng nghĩa ứng dụng đã phát notification. Để thực sự gửi notification, cần có publisher/broadcaster và code phát tương ứng.

## 9. Kiểm chứng ObjectName và MBeanInfo bằng API

Kiểm tra kỹ thuật sau khi application context khởi động:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxInspector {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.monitoring:type=Cache,name=Products"
        );

        System.out.println("Pattern? " + name.isPattern());
        System.out.println("Canonical: " + name.getCanonicalName());

        if (!server.isRegistered(name)) {
            System.out.println("MBean has not been registered");
            return;
        }

        MBeanInfo info = server.getMBeanInfo(name);
        System.out.println("Description: " + info.getDescription());

        for (var attribute : info.getAttributes()) {
            System.out.println("Attribute: " + attribute.getName()
                + " | " + attribute.getDescription());
        }

        for (var operation : info.getOperations()) {
            System.out.println("Operation: " + operation.getName()
                + " | " + operation.getDescription());
        }
    }
}
\`\`\`

Đoạn \`main\` chỉ hoạt động đúng khi chạy trong bối cảnh cùng JVM và đúng \`MBeanServer\` với ứng dụng đã export MBean. Nếu chạy một tiến trình Java riêng, \`ManagementFactory.getPlatformMBeanServer()\` trả về platform server **của tiến trình mới**, thường không có MBean của ứng dụng cần kiểm tra.

Trong kiểm thử tích hợp, gọi inspector trên MBeanServer đã cấu hình cho application context hoặc lấy server qua bean tương ứng. Khi truy cập JVM khác, dùng \`JMXConnector\` và \`MBeanServerConnection\` với kết nối được cấu hình.

### Kiểm tra metadata thực tế

- Tên \`ObjectName\` đã parse hợp lệ?
- \`name.isPattern()\` có bằng \`false\` khi đăng ký?
- \`server.isRegistered(name)\` có bằng \`true\`?
- \`MBeanInfo.getDescription()\` có đúng kỳ vọng?
- Attribute và operation mong muốn có trong MBeanInfo?
- Nếu dùng Model MBean descriptor, các trường metadata tương ứng có được trình bày theo implementation?

Một khai báo annotation là **ý định cấu hình**; \`MBeanInfo\` của đối tượng đã đăng ký là bằng chứng client JMX thực sự nhìn thấy gì.

## 10. Class-level metadata và kế thừa

Trong hệ thống Spring, bean có thể được tạo qua subclass, proxy hoặc các cơ chế AOP. Điều này đặt ra một câu hỏi: exporter đọc metadata trên **class nào**?

Cần lưu ý:

- Annotation được đặt trên kiểu được quản lý hoặc kiểu mà Spring JMX metadata reader có thể nhận diện.
- Nếu bean được bọc bằng JDK dynamic proxy, class runtime có thể không giống class triển khai nghiệp vụ.
- Spring có cơ chế hỗ trợ nhận diện target class trong nhiều trường hợp, nhưng không nên mặc định mọi kiểu proxy đều cho kết quả giống nhau.
- Khi metadata không được đọc, ObjectName hoặc exposed methods có thể không như dự kiến.

Giải pháp thực tế là kiểm tra ObjectName và MBeanInfo sau khi export, nhất là với bean có \`@Transactional\`, \`@Async\`, Spring AOP hoặc các proxy factory.

Khi tên và metadata quản trị quan trọng, việc có một interface/monitor bean riêng dành cho JMX thường giúp giữ hợp đồng rõ hơn là export trực tiếp một service quá lớn có nhiều cross-cutting proxies.

## 11. Khi nào dùng objectName tĩnh và khi nào dùng naming strategy?

| Bối cảnh | Cách tiếp cận |
|---|---|
| Một MBean cố định trong ứng dụng | \`@ManagedResource(objectName="...")\` rõ ràng |
| Nhiều MBean cùng loại với instance khác nhau | Factory/naming strategy tính tên theo instance và quote value |
| Multi-tenant hoặc nhiều module trong một JVM | Domain/key phản ánh cấu trúc thực sự, tránh trùng |
| Framework/library được nhiều ứng dụng nhúng | Chính sách naming có prefix/domain cấu hình và quy tắc ownership |
| Cần tương thích với tên JMX legacy | Duy trì ObjectName hiện hữu hoặc có kế hoạch di trú client |

Ví dụ có thể dùng \`type\`, \`name\`, \`instance\` để tránh trùng:

\`\`\`text
com.example.monitoring:type=Worker,name=Import,instance=node01
com.example.monitoring:type=Worker,name=Import,instance=node02
\`\`\`

Không nên thêm tenant ID/user ID không giới hạn vào tên nếu gây bùng nổ số MBean hoặc làm lộ thông tin nhạy cảm. Đặt tên JMX cũng là một quyết định về vận hành, quyền truy cập và khả năng khám phá của client.

## 12. Lỗi thường gặp và cách xử lý

### 12.1. Annotation có rồi nhưng JConsole không thấy MBean

**Nguyên nhân có thể:** JMX exporter chưa bật, bean không được tạo trong Spring context, autodetect không chọn bean, tên không hợp lệ hoặc client đang kết nối sai JVM.

**Cách xử lý:** Xác minh Spring context, cấu hình \`@EnableMBeanExport\` hoặc \`MBeanExporter\`, kiểm tra log registration và gọi \`isRegistered()\` trên đúng server.

### 12.2. Description không hiện như mong muốn

**Nguyên nhân có thể:** Assembler không đọc annotation, bean được export theo kiểu không sử dụng metadata như mong đợi, hoặc client trình bày MBeanInfo khác nhau.

**Cách xử lý:** Kiểm tra \`MBeanInfo.getDescription()\` trực tiếp, sau đó xem \`AnnotationJmxAttributeSource\` và \`MetadataMBeanInfoAssembler\`.

### 12.3. Trùng ObjectName

**Nguyên nhân:** Hai managed resources dùng cùng domain và key/value trên cùng MBeanServer.

**Cách xử lý:** Chọn chiến lược naming có định danh instance phù hợp. Nếu cần policy fail/ignore/replace, chọn theo ownership và vòng đời, không dùng replace bừa bãi.

### 12.4. Dùng wildcard trong objectName khai báo

**Nguyên nhân:** Có \`*\` hoặc \`?\` không được escape trong phần name, hoặc khai báo property-list pattern.

**Cách xử lý:** Dùng concrete ObjectName cho registration; kiểm tra \`isPattern()\`, dùng \`quote()\` cho giá trị động.

### 12.5. Nhầm description với tài liệu bảo mật

**Nguyên nhân:** Cho rằng mô tả “admin only” trong annotation tự bảo vệ operation.

**Cách xử lý:** Thiết lập authentication/authorization và giới hạn kết nối JMX remote riêng. Description chỉ là metadata.

### 12.6. Tưởng persistPolicy tự lưu state vào database

**Nguyên nhân:** Hiểu nhầm descriptor của Model MBean thành chính sách persistence nghiệp vụ Spring.

**Cách xử lý:** Nếu cần lưu bền, thiết kế repository/transaction, database hoặc storage thật; kiểm tra khả năng Model MBean implementation trước khi dựa vào trường metadata.

### 12.7. Chỉ kiểm tra annotation, bỏ qua trạng thái export

**Nguyên nhân:** Unit test xem reflection thấy annotation nhưng không chạy MBeanExporter.

**Cách xử lý:** Thêm kiểm thử tích hợp có Spring context và MBeanServer để xác minh ObjectName/MBeanInfo trên MBean thực tế.

## 13. Bảo mật và thiết kế metadata

Các nguyên tắc thực hành:

1. **Đặt domain nhất quán:** ví dụ \`com.example.monitoring\`; định nghĩa tên cụ thể theo loại tài nguyên và instance.
2. **Giữ mô tả hữu ích:** mô tả mục đích quản trị; tránh tiết lộ token, mật khẩu, dữ liệu cá nhân.
3. **Chỉ export phần cần thiết:** thao tác có tác dụng phụ như reset, clear, reload phải được đánh giá cẩn thận.
4. **Không coi metadata là kiểm soát quyền:** việc mô tả MBean không thay thế security policy.
5. **Không đưa dữ liệu động chưa escape vào ObjectName:** dùng Java API để giữ đúng nghĩa key/value.
6. **Kiểm tra từ góc nhìn client:** đọc MBeanInfo của đối tượng đã đăng ký.
7. **Giới hạn JMX remote:** cấu hình network, authentication và các bảo vệ phù hợp nếu cho phép truy cập ngoài JVM.

## 14. Bài tập thực hành

### Bài tập A: MBean tối giản

1. Tạo bean \`SystemStatusMonitor\` có \`@Component\`.
2. Gắn:
   \`\`\`java
   @ManagedResource(
       objectName = "com.example.training:type=Status,name=System",
       description = "Application status for administrators"
   )
   \`\`\`
3. Thêm getter \`getState()\` với \`@ManagedAttribute(description="Current state")\`.
4. Bật annotation-driven JMX export.
5. Dùng \`MBeanServer.isRegistered()\` kiểm tra tên.
6. Dùng \`getMBeanInfo()\` xác minh description cấp lớp và attribute.

### Bài tập B: Kiểm tra trùng tên

1. Tạo hai bean có cùng \`@ManagedResource.objectName\`.
2. Khởi động context trong môi trường thử nghiệm.
3. Quan sát lỗi đăng ký hoặc policy được cấu hình.
4. Thay đổi key \`name\`/\`instance\` để hai ObjectName khác nhau.
5. Kiểm tra cả hai qua \`queryNames()\`.

### Bài tập C: Metadata và runtime

1. Gắn \`description\` rõ ràng lên class và một operation.
2. Đọc lại \`MBeanInfo\` của MBean đã export.
3. Thêm \`currencyTimeLimit\` nếu implementation hỗ trợ.
4. Phân biệt dữ liệu descriptor với hành vi thực tế bằng quan sát runtime, không chỉ nhìn annotation.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** \`@ManagedResource\` đảm nhiệm vai trò chính nào?  
**Trả lời:** Khai báo metadata quản trị cấp lớp cho một bean, bao gồm ObjectName, description và một số metadata Model MBean.

**Câu 2.** \`@ManagedResource\` có tự đăng ký MBean vào MBeanServer không?  
**Trả lời:** Không. Cần cơ chế export JMX, thường là MBeanExporter hoặc cấu hình annotation export tương ứng.

**Câu 3.** \`description\` có làm một method trở thành JMX operation không?  
**Trả lời:** Không. Operation được quyết định bởi metadata thành viên và MBeanInfoAssembler.

**Câu 4.** Vì sao \`com.example:type=Cache,name=A\` và \`com.example:name=A,type=Cache\` có thể bằng nhau?  
**Trả lời:** ObjectName định danh bằng domain và tập key/value, không phụ thuộc thứ tự key trong biểu diễn.

**Câu 5.** Vì sao \`objectName="com.example:type=Cache,name=*"\` không thích hợp cho một MBean cụ thể?  
**Trả lời:** Nó là ObjectName pattern, phù hợp để truy vấn nhưng không làm tên đăng ký concrete.

**Câu 6.** \`persistPolicy\` có tự triển khai persistence cho Spring service không?  
**Trả lời:** Không. Nó là metadata trong ngữ cảnh Model MBean và phụ thuộc cơ chế hỗ trợ; persistence nghiệp vụ cần thiết kế riêng.

**Câu 7.** Cần kiểm tra ở đâu để biết mô tả MBean thực sự được export?  
**Trả lời:** Đọc \`MBeanInfo.getDescription()\` từ đúng \`MBeanServer\` và ObjectName sau registration.

## 16. Ghi nhớ

- \`@ManagedResource\` là metadata cấp lớp cho Spring JMX.
- \`objectName\` là khóa định danh JMX; cần concrete, hợp lệ và không trùng trong cùng MBeanServer.
- \`description\` mô tả toàn bộ MBean cho công cụ quản trị, không thay thế annotation attribute/operation.
- Metadata mở rộng như \`currencyTimeLimit\`, \`log\` và \`persistPolicy\` **không tự tạo** caching, logging hay persistence nghiệp vụ.
- \`AnnotationJmxAttributeSource\`, \`MetadataNamingStrategy\`, \`MetadataMBeanInfoAssembler\` và \`MBeanExporter\` phối hợp chuyển khai báo annotation thành MBean đăng ký.
- Tên Spring bean và ObjectName là hai định danh khác nhau.
- Luôn phân biệt annotation đã khai báo với thông tin MBean thực tế; xác minh bằng \`MBeanServer.isRegistered()\` và \`MBeanInfo\`.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`MetadataNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
