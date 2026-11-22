# @ManagedResource đặt ObjectName cho bean trong Spring Framework JMX

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích \`ObjectName\` là gì và vì sao MBean cần tên hợp lệ, duy nhất trong một \`MBeanServer\`.
- Dùng \`@ManagedResource(objectName = "...")\` để chỉ định tên JMX cho một Spring bean.
- Phân biệt **bean name trong Spring**, **Java class name** và **JMX ObjectName**.
- Hiểu vai trò của \`MetadataNamingStrategy\`, \`AnnotationJmxAttributeSource\`, \`MBeanExporter\` và cơ chế autodetection.
- Biết cách kiểm tra ObjectName được export thực tế bằng \`MBeanServer\`.
- Thiết kế naming scheme có thể duy trì khi refactor Java code hoặc triển khai nhiều bean/instance.
- Chẩn đoán các lỗi liên quan ObjectName không hợp lệ, trùng tên, sai server và cấu hình exporter.

## 1. ObjectName là danh tính quản trị của MBean

Trong Java Management Extensions (JMX), MBean được đăng ký trong \`MBeanServer\` theo một giá trị \`javax.management.ObjectName\`. JMX client dùng ObjectName để tìm đúng MBean trước khi đọc attribute hoặc gọi operation.

Ví dụ:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

Tên này gồm:

- **Domain:** \`learning.jmx\`.
- **Key properties:** \`type=CacheMonitor\` và \`name=Products\`.

Một ví dụ truy vấn:

\`\`\`java
ObjectName name = new ObjectName(
        "learning.jmx:type=CacheMonitor,name=Products"
);

Object value = server.getAttribute(name, "EntryCount");
\`\`\`

ObjectName tìm **MBean nào**, còn \`EntryCount\` xác định **attribute nào** trên MBean đó.

ObjectName **không phải URL hoặc địa chỉ JMX remote**. Nếu client nằm trong JVM khác, nó vẫn cần một \`MBeanServerConnection\` trỏ đến đúng MBeanServer qua cơ chế kết nối có quyền truy cập.

### Tính duy nhất của ObjectName

Trong một MBeanServer, một ObjectName chỉ có thể gắn với một MBean tại một thời điểm. Hai bean đăng ký cùng tên có thể gây \`InstanceAlreadyExistsException\` hoặc được xử lý theo registration policy đã cấu hình.

Hai JVM khác nhau vẫn có thể có cùng ObjectName mà không xung đột trực tiếp vì mỗi JVM có registry riêng. Khi tập hợp dữ liệu quản trị từ nhiều JVM, phải giữ thêm identity của instance/connection.

## 2. @ManagedResource đặt ObjectName như thế nào?

Spring Framework hỗ trợ annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
\`\`\`

Bạn có thể đặt ObjectName ngay trên class:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor {
    // ...
}
\`\`\`

Khi một exporter dùng metadata strategy tương ứng, \`objectName\` trên \`@ManagedResource\` được sử dụng để đặt tên MBean.

Hình dung:

\`\`\`text
Spring bean: productCacheMonitor
    |
    | class có @ManagedResource(objectName=...)
    v
AnnotationJmxAttributeSource
    |
    v
MetadataNamingStrategy
    |
    | tạo javax.management.ObjectName
    v
MBeanExporter
    |
    | register với MBeanServer
    v
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

Điểm cần hiểu: annotation chỉ **cung cấp metadata tên**. Bean chỉ thực sự có ObjectName trong MBeanServer sau khi exporter được bật, phát hiện hoặc nhận bean và đăng ký thành công.

### Annotation có thay bean name không?

Không. Giả sử Spring bean có tên \`cacheManagerForProducts\`, Java class là \`ProductCacheMonitor\`, còn annotation ghi:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

Ba giá trị phục vụ ba hệ thống:

| Khái niệm | Ví dụ | Công dụng |
|---|---|---|
| Spring bean name | \`cacheManagerForProducts\` | Định danh bean trong ApplicationContext |
| Java class name | \`ProductCacheMonitor\` | Kiểu triển khai trong code |
| JMX ObjectName | \`learning.jmx:type=CacheMonitor,name=Products\` | Định danh MBean được công bố |

Chúng có thể khác nhau mà vẫn hoàn toàn hợp lệ. Một lý do dùng ObjectName cố định là **client JMX không phải đổi cấu hình chỉ vì developer đổi tên Spring bean hoặc Java class**.

## 3. Ví dụ Spring Framework hoàn chỉnh

Ta xây một bean quản trị cache với một attribute và một operation.

### 3.1. Managed resource

Tệp \`ProductCacheMonitor.java\`:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products",
    description = "Product cache monitor"
)
public class ProductCacheMonitor {

    private final AtomicInteger entryCount = new AtomicInteger(20);

    @ManagedAttribute(description = "Current cache entry count")
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedOperation(description = "Clear product cache")
    public void clear() {
        entryCount.set(0);
    }
}
\`\`\`

\`@ManagedResource\` mô tả MBean và tên đăng ký. \`@ManagedAttribute\` mô tả attribute \`EntryCount\`; \`@ManagedOperation\` công bố thao tác \`clear\`.

### 3.2. Cấu hình JMX với @EnableMBeanExport

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean(name = "cacheManagerForProducts")
    ProductCacheMonitor productCacheMonitor() {
        return new ProductCacheMonitor();
    }
}
\`\`\`

Ở đây:

- Spring bean tên \`cacheManagerForProducts\`.
- Java class tên \`ProductCacheMonitor\`.
- JMX ObjectName là \`learning.jmx:type=CacheMonitor,name=Products\`.

Khi ApplicationContext khởi tạo thành công, Spring exporter có thể đọc metadata và export bean vào MBeanServer tương ứng.

### 3.3. Quan sát registration

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxDemo {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxConfiguration.class)) {

            MBeanServer server =
                    ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=Products"
            );

            System.out.println("Registered: "
                    + server.isRegistered(name));

            if (server.isRegistered(name)) {
                System.out.println("EntryCount: "
                        + server.getAttribute(name, "EntryCount"));
            }

            System.out.println("Press Enter to close");
            System.in.read();
        }
    }
}
\`\`\`

**Điều kiện:** Ví dụ đọc platform MBeanServer của JVM. Nếu exporter đã được cấu hình sử dụng MBeanServer khác, phải lấy chính server đó. Việc \`@EnableMBeanExport\` chọn server có thể phụ thuộc cấu hình, bean MBeanServer được cung cấp hoặc phiên bản framework.

Với cấu hình xuất vào platform server, kết quả ví dụ:

\`\`\`text
Registered: true
EntryCount: 20
Press Enter to close
\`\`\`

Trong JConsole, kết nối tới đúng Java process, tìm domain \`learning.jmx\`, rồi chọn MBean có key properties \`type=CacheMonitor,name=Products\`.

## 4. MetadataNamingStrategy đọc objectName từ đâu?

Spring có lớp \`org.springframework.jmx.export.naming.MetadataNamingStrategy\`. Khi được dùng cùng \`AnnotationJmxAttributeSource\`, nó có thể lấy metadata \`@ManagedResource\` của bean và chuyển giá trị \`objectName\` thành \`ObjectName\`.

Ba vai trò thường đi cùng nhau:

1. **AnnotationJmxAttributeSource:** đọc JMX annotations trên managed resource.
2. **MetadataNamingStrategy:** xác định ObjectName theo metadata.
3. **MetadataMBeanInfoAssembler:** xác định attributes, operations và thông tin quản trị.

\`MBeanExporter\` dùng chúng khi export.

Ví dụ cấu hình tường minh:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler mbeanInfoAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy namingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
                new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter mbeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectMode(
                MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }

    @Bean
    ProductCacheMonitor productCacheMonitor() {
        return new ProductCacheMonitor();
    }
}
\`\`\`

Cấu hình này minh họa đường đi từ annotation đến ObjectName khi không dùng \`@EnableMBeanExport\`. Trong ứng dụng thực, chỉ nên chọn một cơ chế cấu hình exporter phù hợp, tránh vô tình đăng ký cùng một managed resource nhiều lần.

### NamingStrategy và assembler khác nhau như thế nào?

- NamingStrategy chỉ quyết định **tên của MBean**.
- Assembler chỉ quyết định **metadata JMX được công bố**.
- Exporter chịu trách nhiệm **đăng ký và dọn dẹp registration**.

Nếu annotation đúng nhưng MBean không xuất hiện, lỗi có thể nằm ở exporter/autodetection; nếu MBean xuất hiện dưới tên khác, cần kiểm tra NamingStrategy; nếu MBean đúng tên nhưng thiếu attribute/operation, cần kiểm tra assembler.

## 5. ObjectName syntax và các quy tắc quan trọng

JMX ObjectName có dạng tổng quát:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Ví dụ:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Cache,name=Products
learning.jmx:type=Scheduler,name=Nightly
\`\`\`

Một số nguyên tắc:

- Domain nằm trước dấu hai chấm, key properties nằm sau.
- Key properties là các cặp \`key=value\` được phân tách bằng dấu phẩy.
- Một ObjectName phải tuân theo cú pháp Java JMX; những ký tự đặc biệt có thể cần quoting.
- Có thể đổi thứ tự key properties trong chuỗi mà vẫn biểu diễn cùng ObjectName khi các key/value tương ứng giống nhau.
- Không có hai MBean cùng ObjectName trong một MBeanServer ở cùng thời điểm.
- Key \`type\` và \`name\` là convention hữu ích, không phải mọi ObjectName đều bắt buộc dùng đúng hai key này.

Ví dụ hai chuỗi:

\`\`\`text
learning.jmx:type=Cache,name=Products
learning.jmx:name=Products,type=Cache
\`\`\`

Có thể biểu diễn cùng tập key properties và cùng ObjectName theo JMX semantics. Đừng dùng so sánh string thô khi có thể tạo \`ObjectName\` và so sánh theo API.

### Cần quoting khi value có ký tự đặc biệt

Một giá trị như tên cache chứa dấu phẩy có thể không hợp lệ nếu đưa trực tiếp vào chuỗi:

\`\`\`java
String cacheName = "Products,Featured";
\`\`\`

Nếu tự tạo ObjectName bằng code, nên dùng API hỗ trợ quote:

\`\`\`java
ObjectName objectName = new ObjectName(
    "learning.jmx:type=Cache,name="
        + ObjectName.quote(cacheName)
);
\`\`\`

Với \`@ManagedResource(objectName = "...")\`, giá trị annotation là compile-time constant; hãy dùng một ObjectName hợp lệ đã được xác minh. Không tự nối runtime value vào annotation.

### ObjectName có thể chứa wildcard không?

JMX hỗ trợ ObjectName patterns để **truy vấn**, ví dụ:

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=Cache,*"
);

Set<ObjectName> names =
        server.queryNames(pattern, null);
\`\`\`

Tuy nhiên **registration** cần một ObjectName cụ thể, không phải pattern để đăng ký nhiều MBean. Không dùng dấu \`*\` với kỳ vọng \`@ManagedResource\` sẽ tự đăng ký nhiều instances.

## 6. Đặt tên ổn định khi refactor code

Giả sử Java class đổi từ \`ProductCacheMonitor\` thành \`ProductCacheManagementFacade\`, và Spring bean name đổi từ \`cacheManagerForProducts\` thành \`productsCacheAdmin\`.

Nếu annotation vẫn giữ:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products"
)
\`\`\`

JMX client tiếp tục truy vấn cùng ObjectName. Đây là một lợi ích quan trọng của việc định danh rõ ràng tại lớp quản trị: contract vận hành có thể ổn định trong khi implementation được refactor.

**Không đổi ObjectName chỉ vì đổi Java class name.** Nếu team cần thay đổi tên quản trị, coi đó là thay đổi contract và lập kế hoạch migration cho scripts, monitoring rules và runbooks phụ thuộc.

### MBean facade giúp giảm phụ thuộc

Thay vì annotate trực tiếp lên service nghiệp vụ thay đổi thường xuyên, có thể tạo một facade:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products"
)
public class ProductCacheManagement {

    private final ProductCacheService service;

    public ProductCacheManagement(ProductCacheService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getEntryCount() {
        return service.estimatedEntryCount();
    }

    @ManagedOperation
    public void clear() {
        service.clear();
    }
}
\`\`\`

Lớp facade giữ JMX contract ổn định, trong khi \`ProductCacheService\` được sửa đổi theo nhu cầu nghiệp vụ. Việc tách ranh giới này còn giúp không vô tình công bố methods nội bộ không cần thiết.

## 7. Đặt ObjectName khi có nhiều instance

Nếu bạn có hai queue monitors:

\`\`\`text
Primary queue
Secondary queue
\`\`\`

Không thể đăng ký cả hai vào cùng MBeanServer dưới một ObjectName. Dùng key property để phân biệt:

\`\`\`text
learning.jmx:type=QueueMonitor,name=Primary
learning.jmx:type=QueueMonitor,name=Secondary
\`\`\`

Khi đó ObjectName của mỗi instance rõ ràng và ổn định.

### Trường hợp annotation trên class được dùng nhiều lần

Giả sử \`QueueMonitor\` có:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {
    // ...
}
\`\`\`

Và Spring tạo hai bean cùng class. Nếu cả hai đều được exporter autodetect với cùng ObjectName lấy từ annotation, có thể gặp trùng tên.

Các cách giải quyết:

1. Chỉ export một bean đại diện khi đó là nhu cầu quản trị.
2. Dùng một lớp facade riêng cho từng resource với ObjectName phù hợp.
3. Dùng \`MBeanExporter\` explicit bean mapping hoặc \`ObjectNamingStrategy\` tùy biến khi cần đặt tên dựa vào bean identity/runtime instance.
4. Thiết kế namespaced ObjectName cho các instance thật sự độc lập.

Đây là giới hạn cần nhớ: annotation trên **class** mang một giá trị ObjectName cố định; không tự biến thành tên khác nhau chỉ vì Spring tạo hai instances.

### Khi triển khai nhiều JVM/pod

Mỗi JVM có thể có một MBeanServer riêng nên cùng ObjectName có thể xuất hiện trên nhiều pod mà không xung đột. Điều này giúp JMX tooling dùng cùng logical name trên mỗi instance.

Nếu một hệ thống tập trung thu thập JMX từ nhiều JVM, hãy giữ cả **instance identity** và ObjectName. Đừng coi ObjectName là ID duy nhất trên toàn bộ cluster.

## 8. RegistrationPolicy: cách xử lý khi trùng ObjectName

MBeanExporter hỗ trợ \`RegistrationPolicy\` để quyết định hành vi khi ObjectName đã tồn tại.

| Chính sách | Tác động | Khi nào cân nhắc |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Báo lỗi nếu tên đã được đăng ký | Muốn phát hiện cấu hình trùng và sai ownership |
| \`IGNORE_EXISTING\` | Bỏ qua đăng ký mới khi tên đã có | Chủ đích giữ MBean cũ, không thay thế |
| \`REPLACE_EXISTING\` | Thay thế MBean đã đăng ký | Chỉ khi chắc chắn sở hữu tên và tác động được kiểm soát |

Đối với bài học về naming, nên bắt đầu bằng \`FAIL_ON_EXISTING\` để nhận biết lỗi sớm.

\`\`\`java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

**Không dùng \`REPLACE_EXISTING\` để che mọi lỗi trùng**; một context mới có thể thay MBean thuộc context đang chạy, khiến JMX client nhìn thấy đối tượng khác dưới tên cũ.

Khi một MBean đã được đăng ký từ exporter khác hoặc bằng code thủ công, việc đặt chính sách \`IGNORE_EXISTING\` cũng không có nghĩa bean mới đã được export thành công.

## 9. Kiểm chứng ObjectName từ MBeanServer

Cách đơn giản nhất là kiểm tra registration trên **đúng MBeanServer**:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "learning.jmx:type=CacheMonitor,name=Products"
);

System.out.println(
    "Registered: " + server.isRegistered(expected)
);
\`\`\`

Nếu chưa chắc tên đăng ký, tìm theo domain:

\`\`\`java
Set<ObjectName> names = server.queryNames(
    new ObjectName("learning.jmx:*"),
    null
);

names.forEach(System.out::println);
\`\`\`

Khi nhận kết quả, kiểm tra ObjectName thực tế và attributes/operations:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(expected);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

Các kiểu cần import:

\`\`\`java
import java.util.Set;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
\`\`\`

**Cảnh báo thực hành:** \`ManagementFactory.getPlatformMBeanServer()\` lấy server của JVM hiện tại. Nếu chạy code kiểm tra từ một process Java khác, nó không tự nhìn thấy MBeans của ứng dụng mục tiêu. Muốn kiểm tra từ xa, cần dùng \`MBeanServerConnection\` qua connector phù hợp.

## 10. Test JMX naming contract

Tên MBean có thể được tham chiếu trong script và hệ thống monitoring. Vì thế có thể viết integration test xác nhận ObjectName sau khi Spring context khởi tạo.

Ví dụ JUnit 5:

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ObjectNameContractTest {

    @Test
    void managedResourceUsesExpectedObjectName()
            throws Exception {

        ObjectName expected = new ObjectName(
            "learning.jmx:type=CacheMonitor,name=Products"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxConfiguration.class)) {

            MBeanServer server =
                    ManagementFactory.getPlatformMBeanServer();

            assertTrue(server.isRegistered(expected));

            assertEquals(
                20,
                server.getAttribute(expected, "EntryCount")
            );
        }
    }
}
\`\`\`

Test này có ý nghĩa khi JmxConfiguration thực sự export vào platform MBeanServer. Nếu muốn isolation tốt hơn, tạo MBeanServer riêng cho test và cấu hình exporter trỏ đúng server đó.

### Cần test điều gì?

Một contract test về naming nên xác nhận:

- Managed resource được đăng ký sau context startup.
- ObjectName bằng tên mong đợi.
- Không có tên thừa ngoài ý muốn nếu dùng naming strategy tùy biến.
- Attributes/operations quan trọng được công bố đúng.
- Sau context close, exporter hủy đăng ký những MBeans mà nó quản lý.
- Các test chạy song song không dùng cùng ObjectName trong một MBeanServer nếu có nguy cơ xung đột.

Không cần viết unit test cho giá trị chuỗi annotation thuần túy. Kiểm tra JMX boundary có giá trị hơn vì phát hiện lỗi cấu hình, exporter, metadata và registry.

## 11. ObjectName khi sử dụng explicit exporter mapping

Một cách khác ngoài annotation metadata là chỉ định tên trong map của MBeanExporter:

\`\`\`java
exporter.setBeans(Map.of(
    "learning.jmx:type=CacheMonitor,name=Products",
    productCacheMonitor
));
\`\`\`

Trong trường hợp này, tên có thể lấy từ mapping explicit thay vì naming strategy đọc \`@ManagedResource.objectName\`.

Không nên suy ra rằng mọi MBean có \`@ManagedResource\` đều chắc chắn được đăng ký với tên trong annotation nếu cấu hình exporter đã override bằng một naming source/registration path khác.

**Nguyên tắc:** Xác định tên cuối cùng bằng cách truy vấn MBeanServer thật, không chỉ đọc source code annotation.

Nếu bạn muốn một nguồn tên duy nhất và dùng annotation-driven export, để naming strategy đọc từ \`@ManagedResource.objectName\` là cách dễ hiểu. Nếu cần tên theo instance hoặc môi trường, explicit mapping/custom strategy có thể phù hợp hơn.

## 12. Các tình huống đặt tên thực tế

### Tình huống A — Đổi tên class nhưng giữ JMX client

Class \`ProductCacheMonitor\` đổi thành \`ProductCacheManagement\`. ObjectName trong annotation vẫn là:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

Kết quả mong đợi: JMX client tiếp tục truy vấn cùng tên sau khi exporter khởi động thành công. Dĩ nhiên attributes/operations cũng phải giữ contract nếu muốn tương thích hoàn toàn.

### Tình huống B — Hai beans cùng class

Hai instance \`QueueMonitor\` được auto-detect nhưng class chỉ có một annotation objectName. Việc dùng cùng tên gây collision. Cần explicit naming theo instance hoặc export một facade đại diện.

### Tình huống C — Sai cú pháp ObjectName

Developer đặt:

\`\`\`text
learning.jmx:type=Cache,name=Products,Featured
\`\`\`

Dấu phẩy trong value có thể làm parser hiểu nhầm key property. Khi đặt name có ký tự đặc biệt, cần quote/escape đúng ObjectName syntax.

### Tình huống D — Nhiều context trong cùng JVM

Parent và child contexts đều có exporter đăng ký cùng một logical MBean. Việc mỗi context có bean name riêng không giải quyết trùng ObjectName trong cùng server. Chỉ một context nên sở hữu registration, hoặc ObjectName phải phản ánh hai resource khác nhau.

### Tình huống E — Monitoring từ nhiều pod

Mỗi pod có cùng ObjectName \`learning.jmx:type=CacheMonitor,name=Products\`. Không xung đột nếu mỗi pod có MBeanServer riêng. Collector cần thêm pod/JVM identity khi tổng hợp.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không thấy MBean dưới ObjectName mong đợi | Exporter chưa chạy, naming strategy khác, sai JVM/server | Dùng \`queryNames\` trên đúng MBeanServer |
| \`MalformedObjectNameException\` | Domain hoặc key properties không hợp lệ | Kiểm tra cú pháp và quoting |
| \`InstanceAlreadyExistsException\` | Hai MBeans trùng ObjectName | Xác định owner, context và registration policy |
| Bean có \`@ManagedResource\` nhưng không được export | Chưa bật exporter/autodetection hoặc bean ngoài context | Kiểm tra \`@EnableMBeanExport\`/\`MBeanExporter\` và Spring bean |
| Đổi Java class name khiến tool mất MBean | Naming strategy sinh tên từ class thay vì tên cố định | Dùng ObjectName ổn định hoặc migration có chủ đích |
| Hai instances cùng class tranh cùng tên | Class-level annotation cố định | Chọn explicit mapping/custom naming |
| MBean đúng tên nhưng thiếu attribute | Metadata assembler không công bố getter/operation | Kiểm tra \`@ManagedAttribute\`, \`@ManagedOperation\`, \`MBeanInfo\` |
| JConsole thấy tên trong JVM khác | Kết nối nhầm process | Kiểm tra PID, instance identity và connector |
| Context đóng nhưng ObjectName còn tồn tại | Một exporter khác hoặc code thủ công sở hữu registration | Truy nguyên nơi register/unregister |
| Công cụ monitoring bị đứt sau rename | ObjectName là một phần contract | Giữ tên cũ hoặc di chuyển consumer theo kế hoạch |

## 14. Checklist khi thiết kế @ManagedResource.objectName

Trước khi export bean mới, hỏi:

1. **Domain:** Có nhất quán với application/module không?
2. **Type:** Có diễn tả loại resource quản trị không?
3. **Key properties:** Có phân biệt các instances cùng loại trong một MBeanServer không?
4. **Stability:** Tên có tồn tại ổn định qua refactor code không?
5. **Ownership:** Context hoặc exporter nào chịu trách nhiệm đăng ký và hủy đăng ký?
6. **Collision:** Có hai bean, hai context hoặc module nào cùng dùng tên không?
7. **Environment:** Các JVM/pod có server riêng hay dùng chung registry?
8. **Security:** ObjectName có tránh đưa bí mật/thông tin nhạy cảm vào metadata không?
9. **Discoverability:** Công cụ quản trị có thể query theo domain/type dễ dàng không?
10. **Compatibility:** Scripts, dashboards hoặc runbooks nào phụ thuộc tên này?

Nếu cần tên thay đổi theo dữ liệu runtime, class-level annotation cố định có thể không phù hợp. Khi đó hãy dùng explicit registration hoặc ObjectNamingStrategy được thiết kế rõ.

## 15. Bài tập thực hành

### Bài tập 1 — Khác biệt ba loại tên

Cho:

\`\`\`java
@Bean(name = "inventoryCacheAdmin")
ProductCacheMonitor productCacheMonitor() {
    return new ProductCacheMonitor();
}
\`\`\`

và:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=Inventory"
)
public class ProductCacheMonitor {
    // ...
}
\`\`\`

Hãy nêu bean name, Java class name và JMX ObjectName. Giải thích vì sao ba tên không cần trùng nhau.

### Bài tập 2 — Xác minh bằng MBeanServer

Khởi chạy context chứa ProductCacheMonitor. Dùng \`isRegistered\`, \`queryNames\` và \`getMBeanInfo\` để tìm đúng ObjectName, attribute \`EntryCount\` và operation \`clear\`.

### Bài tập 3 — Xử lý collision

Tạo hai Spring beans cùng class, cùng \`@ManagedResource.objectName\`. Quan sát lỗi hoặc hành vi registration policy. Hãy thiết kế lại tên để hai instances có thể cùng tồn tại mà không đè nhau.

### Bài tập 4 — ObjectName hợp lệ

Đánh giá:

\`\`\`text
learning.jmx:type=Cache,name=Products
learning.jmx:type=Cache,name=Products,Featured
learning.jmx:type=Cache,name="Products,Featured"
\`\`\`

Tên thứ hai có dấu phẩy không được quote trong value nên dễ sai cú pháp. Tên thứ ba minh họa cách quote một value có ký tự phân tách; cần xác minh bằng \`new ObjectName(...)\` khi áp dụng.

### Bài tập 5 — Refactor không làm gãy client

Một developer đổi class \`QueueMonitor\` thành \`QueueRuntimeInspector\`. Hãy giữ \`ObjectName\` không đổi, xác nhận \`isRegistered\` với tên cũ vẫn true, sau đó kiểm tra operations/attributes có giữ nguyên contract không.

## 16. Ghi nhớ cốt lõi

- \`@ManagedResource(objectName = "...")\` là cách khai báo **định danh JMX** cho Spring-managed bean.
- Annotation không tự mở JMX server hoặc đăng ký bean nếu chưa có exporter.
- \`MetadataNamingStrategy\` có thể đọc objectName từ annotation và cung cấp tên cho MBeanExporter.
- Spring bean name, Java class name và JMX ObjectName là ba khái niệm độc lập.
- ObjectName phải hợp lệ và duy nhất trong từng MBeanServer.
- Đặt tên cố định giúp JMX contract ổn định khi refactor, nhưng nhiều instances cùng class có thể cần naming strategy khác.
- Kiểm chứng registration thực tế bằng \`MBeanServer.isRegistered\`, \`queryNames\` và \`getMBeanInfo\`.
- Khi đổi ObjectName, coi đó là thay đổi management API contract; cần di chuyển client và tooling theo kế hoạch.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework API — MetadataNamingStrategy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — ObjectName: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
