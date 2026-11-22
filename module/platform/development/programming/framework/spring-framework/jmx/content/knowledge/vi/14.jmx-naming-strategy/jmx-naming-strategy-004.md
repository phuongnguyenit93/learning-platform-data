# MetadataNamingStrategy lấy tên từ metadata nguồn

## 1. Bối cảnh và mục tiêu

Trong Spring Framework JMX, việc đưa một Spring bean ra hệ thống quản trị cần giải quyết hai câu hỏi riêng biệt:

- **Bean được đặt tên như thế nào trong JMX?** Kết quả phải là một \`javax.management.ObjectName\` hợp lệ, duy nhất trong \`MBeanServer\` đang dùng.
- **Bean expose thuộc tính và thao tác nào?** Đây là nhiệm vụ của cơ chế xây dựng management interface, thường thông qua \`MBeanInfoAssembler\`.

\`org.springframework.jmx.export.naming.MetadataNamingStrategy\` giải quyết câu hỏi thứ nhất. Nó là một \`ObjectNamingStrategy\` lấy thông tin định danh MBean từ **nguồn metadata** (\`JmxAttributeSource\`), thường là \`AnnotationJmxAttributeSource\` đọc annotation \`@ManagedResource\` trên class.

Bài học hướng dẫn cách hoạt động, cấu hình và kiểm chứng chiến lược đặt tên này, đồng thời làm rõ ranh giới với \`MBeanExporter\`, \`MetadataMBeanInfoAssembler\` và tên bean trong Spring.

Sau bài học, bạn có thể:

1. Giải thích vai trò của \`ObjectNamingStrategy\` và \`MetadataNamingStrategy\`.
2. Phân biệt tên bean Spring, Java class name và JMX \`ObjectName\`.
3. Khai báo \`@ManagedResource(objectName=...)\` và cấu hình nguồn annotation tương ứng.
4. Hiểu những gì metadata naming strategy lấy từ metadata và giới hạn khi metadata thiếu hoặc không hợp lệ.
5. Sử dụng \`ObjectName\` API để kiểm tra tên, wildcard và tính tương đương.
6. Chẩn đoán lỗi không đăng ký được MBean vì naming strategy hoặc trùng ObjectName.
7. Lựa chọn giữa metadata-based naming và cách đặt tên khác khi có instance động.

## 2. Mô hình tổng quan

\`\`\`text
Spring bean: ProductCacheMonitor
          |
          | @ManagedResource(
          |   objectName="com.example.monitoring:type=Cache,name=Products"
          | )
          v
AnnotationJmxAttributeSource
          |
          | metadata resource
          v
MetadataNamingStrategy
          |
          | getObjectName(bean, beanKey)
          v
javax.management.ObjectName
          |
          v
      MBeanExporter
          |
          | registerMBean
          v
       MBeanServer
          |
          v
    JConsole / JMX client
\`\`\`

Một luồng song song:

\`\`\`text
@ManagedAttribute / @ManagedOperation
          |
          v
AnnotationJmxAttributeSource
          |
          v
MetadataMBeanInfoAssembler
          |
          v
     Management interface
\`\`\`

Hai nhánh cùng dùng nguồn metadata nhưng làm việc khác nhau. Naming strategy quyết định **đối tượng được gọi tên gì**; assembler quyết định **đối tượng cho phép xem và gọi những gì**.

## 3. ObjectName là gì và tại sao cần chiến lược đặt tên?

JMX \`ObjectName\` thường có cú pháp:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Ví dụ:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
com.example.monitoring:type=Worker,name=Import
java.lang:type=Memory
\`\`\`

Một ObjectName có:

- **Domain:** nhóm định danh, chẳng hạn \`com.example.monitoring\`.
- **Key properties:** ví dụ \`type=Cache\`, \`name=Products\`.
- **Canonical representation:** dạng chuẩn hóa thứ tự key properties khi cần so sánh/ghi log.
- **Pattern semantics:** wildcard \`*\`, \`?\` có thể được dùng cho query nhưng không phù hợp khi đăng ký một MBean cụ thể.

Ví dụ hai tên sau biểu diễn cùng một ObjectName:

\`\`\`java
ObjectName first = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

ObjectName second = new ObjectName(
    "com.example.monitoring:name=Products,type=Cache"
);

System.out.println(first.equals(second)); // true
\`\`\`

Dùng \`ObjectName.equals()\` hoặc \`getCanonicalName()\` khi cần so sánh. Không phụ thuộc thứ tự key trong chuỗi đầu vào.

### Spring bean name khác ObjectName

Một class:

\`\`\`java
@Component("productCacheMonitor")
public class ProductCacheMonitor {
}
\`\`\`

có Spring bean name \`productCacheMonitor\`. Tên đó dùng để định danh bean trong \`ApplicationContext\`.

Ngược lại:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
\`\`\`

là JMX ObjectName dùng trong \`MBeanServer\`. \`MetadataNamingStrategy\` giúp xác định tên JMX dựa trên metadata quản trị, không đơn giản lấy bean name rồi dùng nguyên làm ObjectName.

## 4. ObjectNamingStrategy là hợp đồng nào?

Spring định nghĩa \`ObjectNamingStrategy\` để các exporter có thể thay đổi quy tắc xác định tên MBean mà không thay đổi logic đăng ký.

Ý tưởng:

\`\`\`java
ObjectName getObjectName(Object managedBean, String beanKey)
        throws MalformedObjectNameException;
\`\`\`

- \`managedBean\`: đối tượng được export.
- \`beanKey\`: khóa hoặc tên tương ứng trong cấu hình export.
- Kết quả: một \`ObjectName\` hợp lệ.

Tùy implementation, naming strategy có thể sử dụng class, bean key, metadata hoặc một quy ước riêng.

Một số implementation trong Spring:

| Strategy | Nguồn tên chính | Khi hữu ích |
|---|---|---|
| \`MetadataNamingStrategy\` | Metadata quản trị từ \`JmxAttributeSource\` | Bean dùng \`@ManagedResource(objectName=...)\` |
| \`KeyNamingStrategy\` | Khóa mapping hoặc cấu hình mapping | Cần định danh tường minh từ exporter configuration |
| \`IdentityNamingStrategy\` | Danh tính/type của object theo chính sách strategy | Khi muốn tên gắn với identity của instance |
| Custom \`ObjectNamingStrategy\` | Quy tắc do ứng dụng định nghĩa | Tên động, multi-instance, convention riêng |

\`MetadataNamingStrategy\` phù hợp khi ObjectName là một phần của **hợp đồng quản trị khai báo ngay trên class**.

## 5. Nguồn metadata: JmxAttributeSource

\`JmxAttributeSource\` là abstraction của Spring JMX để tra metadata quản trị của một class/method.

Với annotation-driven JMX, source thường là:

\`\`\`java
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

AnnotationJmxAttributeSource source =
    new AnnotationJmxAttributeSource();
\`\`\`

Nó đọc các annotation như:

- \`@ManagedResource\` ở cấp class.
- \`@ManagedAttribute\` trên getter/setter.
- \`@ManagedOperation\` trên method.
- \`@ManagedOperationParameter\` cho mô tả tham số.
- \`@ManagedNotification\` cho metadata notification.

**Đối với naming**, dữ liệu quan trọng chủ yếu là resource metadata cấp class, đặc biệt \`@ManagedResource.objectName\`.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor {
}
\`\`\`

Source nhận biết resource metadata, naming strategy lấy thông tin tên JMX phù hợp, rồi exporter đăng ký bean.

\`description\` mô tả MBean cho client; nó không phải một thành phần của ObjectName. Tương tự \`currencyTimeLimit\` hoặc các thuộc tính descriptor của \`@ManagedResource\` không tự thay thế giá trị \`objectName\`.

## 6. Ví dụ đầy đủ với Spring Framework thuần

### 6.1. Managed bean

\`\`\`java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;
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

    private final AtomicInteger entryCount = new AtomicInteger();

    @ManagedAttribute(description = "Current cached entries")
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedOperation(description = "Reset cached entry count")
    public void resetStatistics() {
        entryCount.set(0);
    }
}
\`\`\`

### 6.2. Cấu hình MetadataNamingStrategy

\`\`\`java
package com.example.monitoring;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

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
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {

        MetadataNamingStrategy strategy =
            new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

Giải thích:

1. \`ProductCacheMonitor\` được Spring đăng ký vì có \`@Component\` và component scan.
2. \`AnnotationJmxAttributeSource\` đọc metadata quản trị.
3. \`MetadataNamingStrategy\` lấy tên từ \`@ManagedResource\`.
4. \`MetadataMBeanInfoAssembler\` xây dựng thuộc tính và thao tác quản trị.
5. \`MBeanExporter\` nhận hai thành phần rồi đăng ký bean vào MBeanServer.
6. Client sẽ tìm được MBean theo \`com.example.monitoring:type=Cache,name=Products\` nếu export thành công và đang kết nối đúng server.

Cấu hình thực tế cần có component scan hoặc một \`@Bean\` tương ứng để tạo \`ProductCacheMonitor\`. Ví dụ trình bày riêng cấu hình JMX, không bao gồm bootstrap ứng dụng.

### 6.3. Cách annotation-driven ngắn gọn

Nếu không có yêu cầu tùy chỉnh assembler/naming strategy, Spring Framework cung cấp:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class SimpleJmxConfiguration {
}
\`\`\`

Spring tự cài đặt các phần hỗ trợ export annotation phù hợp. Đây là **phương án thay thế** cho cấu hình exporter thủ công phía trên.

Trong Spring Boot, cần kiểm tra JMX auto-configuration và \`spring.jmx.enabled\` của phiên bản đang dùng trước khi tạo exporter bổ sung. Hai exporter cùng export một ObjectName có thể xung đột.

## 7. MetadataNamingStrategy thực sự làm gì?

Khi exporter yêu cầu một tên cho bean, strategy đọc metadata resource thông qua source đã cấu hình rồi xác định \`ObjectName\`.

Với metadata:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
\`\`\`

kết quả mong đợi:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
\`\`\`

Điều quan trọng:

- Strategy **không tự lựa chọn bean** cần export.
- Strategy **không đăng ký MBean** vào server.
- Strategy **không tạo JMX attributes/operations**.
- Strategy **không tự mở JMX remote port**.
- Strategy **không biến annotation thành dữ liệu runtime** nếu exporter và metadata source chưa được kết nối.

Nó cung cấp một \`ObjectName\` để \`MBeanExporter\` sử dụng.

### Khi metadata không có ObjectName

Không nên giả định chiến lược luôn có thể tìm một tên hữu ích cho mọi class. Nếu resource metadata bị thiếu hoặc \`objectName\` không được xác định, hành vi cụ thể phụ thuộc implementation và cấu hình exporter/naming. Hãy xem lỗi thực tế và contract của phiên bản Spring đang dùng.

Trong kiến trúc cần tên ổn định, cách an toàn là khai báo \`objectName\` rõ ràng hoặc cung cấp naming strategy có fallback do ứng dụng thiết kế, thay vì dựa vào suy đoán về tên được tự tạo.

## 8. MetadataNamingStrategy khác MetadataMBeanInfoAssembler

Một cặp dễ nhầm là:

\`\`\`text
MetadataNamingStrategy
MetadataMBeanInfoAssembler
\`\`\`

Cả hai có thể nhận cùng \`AnnotationJmxAttributeSource\`, nhưng khác nhiệm vụ:

| Tiêu chí | MetadataNamingStrategy | MetadataMBeanInfoAssembler |
|---|---|---|
| Câu hỏi | MBean có tên gì? | MBean có giao diện quản trị nào? |
| Kết quả | \`ObjectName\` | \`ModelMBeanInfo\`/metadata quản trị |
| Nguồn chính | Class-level resource metadata | Resource, attribute, operation, notification metadata |
| Ví dụ annotation | \`@ManagedResource.objectName\` | \`@ManagedAttribute\`, \`@ManagedOperation\`, description |
| Dùng bởi | \`MBeanExporter\` | \`MBeanExporter\` |
| Tác động trực tiếp | Định danh trong MBeanServer | Nội dung client nhìn thấy/gọi được |

Một bean có thể được đặt đúng ObjectName nhưng thiếu attribute do assembler không đọc annotation. Ngược lại, assembler có thể tìm đủ operation nhưng exporter thất bại đăng ký do ObjectName trùng.

Do đó khi debug JMX, nên tách lỗi **naming** và lỗi **interface assembly**.

## 9. Kiểm tra ObjectName bằng Java API

Sau khi khai báo annotation hoặc tự xây tên từ metadata, có thể kiểm tra:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

System.out.println(name.getDomain());
System.out.println(name.getKeyProperty("type"));
System.out.println(name.getKeyProperty("name"));
System.out.println(name.getCanonicalName());
System.out.println(name.isPattern()); // false
\`\`\`

Các API quan trọng:

| API | Ý nghĩa |
|---|---|
| \`new ObjectName(text)\` | Parse và kiểm tra cú pháp tên |
| \`getDomain()\` | Lấy domain |
| \`getKeyProperty(key)\` | Lấy giá trị key được chỉ định |
| \`getKeyPropertyList()\` | Lấy key/value đã parse |
| \`getCanonicalName()\` | Dạng canonical để đối chiếu |
| \`equals(other)\` | So sánh định danh ObjectName |
| \`isPattern()\` | Kiểm tra wildcard/pattern |
| \`ObjectName.quote(value)\` | Escape giá trị property động |

Mục tiêu của \`MetadataNamingStrategy\` là sinh ra một tên có thể dùng để **đăng ký một MBean cụ thể**. Vì vậy, cấu hình ObjectName không nên chứa wildcard ngoài ý muốn.

Ví dụ:

\`\`\`java
ObjectName pattern =
    new ObjectName("com.example.monitoring:type=Cache,*");

System.out.println(pattern.isPattern()); // true
\`\`\`

Tên đó thích hợp cho \`MBeanServer.queryNames()\`, không thích hợp cho registration của một MBean cụ thể.

## 10. Tên động: giới hạn của annotation cố định

\`@ManagedResource(objectName=...)\` là annotation attribute và phải dùng giá trị hợp lệ theo quy tắc compile-time constant của Java.

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import"
)
\`\`\`

Phù hợp khi instance có tên cố định. Nhưng nếu một ứng dụng có nhiều worker cùng class:

\`\`\`text
Worker name = ImportEast
Worker name = ImportWest
\`\`\`

thì **không thể dùng cùng một ObjectName cố định** cho cả hai instance trên cùng MBeanServer.

Không nên cố nối runtime variable trực tiếp vào annotation:

\`\`\`java
// Không thể dùng biến runtime làm annotation value:
// @ManagedResource(objectName = DOMAIN + ":type=Worker,name=" + workerName)
\`\`\`

Với nhiều instance động, giải pháp thường là:

- Tạo ObjectName từ dữ liệu runtime bằng \`ObjectName\` API.
- Chọn custom naming strategy phù hợp.
- Hoặc tạo mapping export programmatic cho từng instance.
- Đảm bảo mỗi instance có key property phân biệt (\`name\`, \`instance\`, ...).

Ví dụ tạo tên an toàn:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

String workerName = "Import,Region=East";

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Worker");
properties.put("name", ObjectName.quote(workerName));

ObjectName objectName =
    new ObjectName("com.example.monitoring", properties);
\`\`\`

\`ObjectName.quote(workerName)\` giữ dấu phân cách trong tên worker thành dữ liệu, không thành key mới. Nếu domain/key cũng đến từ dữ liệu bên ngoài, cần validate chúng riêng.

Cần phân biệt việc dùng \`MetadataNamingStrategy\` cho tên khai báo tĩnh và việc dùng một chiến lược khác để đặt tên động theo instance. Không bắt buộc mọi bài toán naming phải dựa vào annotation.

## 11. MBeanServer và ObjectName collision

\`MBeanServer\` chỉ có thể chứa một đăng ký với một ObjectName cụ thể tại một thời điểm.

Ví dụ hai bean:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
class ProductCacheMonitorA { }

@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
class ProductCacheMonitorB { }
\`\`\`

Nếu cả hai được exporter chọn trên cùng MBeanServer, có thể xảy ra xung đột đăng ký.

Các phương án xử lý:

1. Đặt ObjectName riêng theo phạm vi/instance.
2. Giới hạn bean được export.
3. Xem \`RegistrationPolicy\` phù hợp nếu có lý do nghiệp vụ rõ ràng.
4. Tránh cấu hình nhiều exporter trùng một tập MBean.
5. Thống nhất naming convention toàn ứng dụng.

Spring hỗ trợ những registration policies như \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, \`REPLACE_EXISTING\`. Không nên chọn \`REPLACE_EXISTING\` chỉ để che lỗi; nó có thể thay MBean do thành phần khác đăng ký.

### Lưu ý khi nhiều Spring ApplicationContext

Trong cùng JVM có thể có nhiều application contexts (parent/child hoặc nhiều module). Mỗi context có thể khai báo exporter nhưng cùng đăng ký vào một MBeanServer. Do đó một ObjectName chỉ duy nhất trong phạm vi một Spring context chưa chắc duy nhất trong toàn MBeanServer.

Naming convention cần tính đến module, application hoặc instance nếu nhiều ứng dụng dùng chung server.

## 12. Kiểm chứng tên trên MBeanServer

Sau khi khởi động application context với JMX exporter, kiểm tra:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

System.out.println(server.isRegistered(name));
\`\`\`

Nếu \`true\`, tên đó đã đăng ký trên server được chỉ định tại thời điểm gọi.

Có thể đọc \`MBeanInfo\`:

\`\`\`java
var info = server.getMBeanInfo(name);

System.out.println(info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.println(
        attr.getName() + ": " + attr.getType()
    );
}
\`\`\`

Để tra cứu toàn bộ tên trong domain:

\`\`\`java
ObjectName query = new ObjectName(
    "com.example.monitoring:*"
);

for (ObjectName registered : server.queryNames(query, null)) {
    System.out.println(registered.getCanonicalName());
}
\`\`\`

**Quan trọng:** \`ManagementFactory.getPlatformMBeanServer()\` trả về platform MBeanServer **của JVM đang chạy đoạn code**. Nếu exporter dùng MBeanServer khác hoặc client ở JVM khác, phải kiểm tra đúng server qua reference/connection tương ứng.

## 13. Debug lỗi MetadataNamingStrategy

### 13.1. Có @ManagedResource nhưng không thấy MBean

Khả năng:

- Spring bean chưa được tạo hoặc component scan không bao phủ class.
- JMX export chưa bật.
- Autodetect chưa chọn bean.
- Metadata source không được nối vào naming strategy.
- ObjectName không hợp lệ, trùng hoặc đang đăng ký ở server khác.
- Client đang kết nối sai JVM.

Kiểm tra theo chuỗi: Spring bean có tồn tại → exporter có hoạt động → source có đọc metadata → naming strategy trả tên gì → đăng ký thành công chưa → client đang nhìn server nào.

### 13.2. Bean có trên MBeanServer với tên không kỳ vọng

Khả năng:

- Exporter đang dùng naming strategy khác.
- Một mapping tường minh được ưu tiên bởi cấu hình exporter.
- Có nhiều exporter hoặc cơ chế auto-configuration.
- Annotation không được đọc do target class/proxy.
- Có fallback naming hoặc naming convention của implementation.

Nên xem cấu hình thực tế và danh sách \`queryNames()\`, không chỉ nhìn annotation trong source.

### 13.3. Invalid ObjectName

Nếu tên chứa ký tự đặc biệt sai cú pháp hoặc wildcard dùng không đúng ngữ cảnh, JMX parser/registration có thể báo lỗi.

\`\`\`java
new ObjectName("com.example:type=Worker,name=Import,East");
\`\`\`

Đây là ví dụ key property list sai cấu trúc vì \`East\` không phải cặp \`key=value\` hợp lệ. Nếu \`Import,East\` là một tên người dùng, phải quote value khi xây tên động.

### 13.4. Trùng tên sau khi thêm bean mới

Đừng chỉ đổi \`description\` hoặc tên class. Hai MBean vẫn có thể có ObjectName giống nhau. Kiểm tra **domain và toàn bộ tập key properties**.

### 13.5. Annotation có nhưng proxy gây khác biệt

Spring AOP có thể biến runtime bean thành JDK proxy hoặc CGLIB proxy. Metadata đặt trên target implementation đôi khi cần cơ chế nhận diện target class/proxy đúng cách. Nếu xuất hiện lỗi, dùng test tích hợp kiểm tra tên đã đăng ký; có thể tách một management facade bean dành riêng cho JMX.

### 13.6. MBean đã đăng ký nhưng JConsole không hiển thị

Có thể client đang kết nối sai process hoặc remote connector chưa bật. \`MetadataNamingStrategy\` không tự mở remote JMX hoặc cấu hình quyền mạng.

## 14. Kiểm thử naming strategy

Một kiểm thử nhỏ có thể xác minh ObjectName kỳ vọng từ metadata class:

\`\`\`java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

class MetadataNamingStrategyTest {

    @Test
    void readsObjectNameFromManagedResource() throws Exception {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        ProductCacheMonitor bean = new ProductCacheMonitor();

        ObjectName actual = naming.getObjectName(
            bean, "productCacheMonitor"
        );

        ObjectName expected = new ObjectName(
            "com.example.monitoring:type=Cache,name=Products"
        );

        assertEquals(expected, actual);
        assertFalse(actual.isPattern());
    }
}
\`\`\`

Kiểm thử này xác nhận naming strategy đọc annotation theo cấu hình đã tạo. Nó **không** chứng minh MBean đã được export vì không có \`MBeanExporter\` hay \`MBeanServer\` tham gia.

Để xác minh toàn bộ pipeline, dùng integration test với Spring context và MBeanServer rồi kiểm tra \`server.isRegistered(expected)\`.

### Bộ trường hợp hữu ích

| Trường hợp | Kỳ vọng |
|---|---|
| Class có \`@ManagedResource.objectName\` hợp lệ | Strategy trả ObjectName mong đợi |
| Key properties đảo thứ tự | \`ObjectName.equals()\` vẫn cho kết quả tương đương |
| Hai bean cùng ObjectName | Exporter/server báo xung đột theo registration policy |
| ObjectName là pattern | Không chấp nhận làm concrete registration name |
| Không có metadata nguồn thích hợp | Phải xử lý theo contract/error của strategy và cấu hình |
| Bean là AOP proxy | Cần xác minh source nhận đúng annotation và tên |
| Dùng tên động có dấu phẩy | Quote property value qua Java ObjectName API |

Không nên chỉ dùng \`toString()\` để so định danh hoặc tự viết regex mô phỏng toàn bộ JMX grammar.

## 15. Khi nào chọn MetadataNamingStrategy?

Nên chọn khi:

- MBean có identity ổn định và có thể khai báo ngay trên class.
- Dự án đã dùng Spring JMX annotations để mô tả management contract.
- Muốn nguồn metadata đồng nhất giữa tên MBean và metadata giao diện.
- Số lượng loại MBean vừa phải, naming convention có thể duy trì trực tiếp.
- Mong muốn cấu hình annotation-driven đơn giản.

Cân nhắc cách khác khi:

- Có rất nhiều instance cùng class nhưng mỗi instance cần ObjectName khác.
- Tên phụ thuộc tenant, node, dynamic configuration hoặc lifecycle runtime.
- Một thư viện được nhúng vào nhiều context với domain naming khác nhau.
- Cần giữ tương thích với ObjectName legacy nằm ngoài class.
- Cần quản lý mapping tên tập trung bởi hạ tầng.

Trong những trường hợp đó, có thể chọn \`KeyNamingStrategy\`, custom \`ObjectNamingStrategy\`, hoặc ánh xạ explicit tại exporter. Việc chọn phụ thuộc **nguồn dữ liệu định danh nào mới là source of truth**.

## 16. Bảo mật và thiết kế tên JMX

Một ObjectName không phải credential hoặc bằng chứng người gọi có quyền. Dù tên hợp lệ, cần giới hạn ai được:

- Kết nối tới JMX remote.
- Duyệt và đọc MBeans.
- Gọi operations.
- Thay đổi writable attributes.
- Truy cập dữ liệu chẩn đoán nhạy cảm.

Quy tắc thực hành:

- Dùng domain ổn định theo application/module.
- Đặt \`type\`, \`name\`, \`instance\` có ý nghĩa.
- Tránh dữ liệu cá nhân, mật khẩu, token trong ObjectName.
- Không đưa chuỗi untrusted trực tiếp vào domain/key/value.
- Không tạo số lượng MBean không kiểm soát theo user/session.
- Có chiến lược tránh trùng cho multi-instance và multi-context.
- Kiểm tra việc đổi ObjectName có ảnh hưởng tới script giám sát hoặc JMX client hiện có không.

Nếu MBean đổi tên, client đang query ObjectName cũ có thể không còn tìm thấy đối tượng. Vì vậy định danh JMX là một phần của hợp đồng vận hành cần quản lý thay đổi.

## 17. Bài tập thực hành

### Bài tập A — Metadata naming cơ bản

1. Tạo Spring bean \`QueueMonitor\`.
2. Gắn \`@ManagedResource(objectName="com.example.training:type=Queue,name=Orders")\`.
3. Tạo \`AnnotationJmxAttributeSource\`.
4. Tạo \`MetadataNamingStrategy\`, set source.
5. Gọi \`getObjectName(bean, "queueMonitor")\`.
6. Kiểm tra domain, key properties và \`isPattern()\`.

### Bài tập B — Tích hợp exporter

1. Tạo \`MetadataMBeanInfoAssembler\` dùng cùng source.
2. Cấu hình \`MBeanExporter\` với assembler và naming strategy.
3. Bật autodetect phù hợp.
4. Khởi động Spring context.
5. Kiểm tra \`MBeanServer.isRegistered(expectedObjectName)\`.
6. Đọc \`MBeanInfo\` xác minh interface quản trị.

### Bài tập C — Xử lý trùng tên

1. Tạo hai bean sử dụng cùng ObjectName metadata.
2. Quan sát lỗi hoặc registration policy khi export vào một MBeanServer.
3. Đặt key \`instance\` riêng.
4. Đăng ký lại và xác minh cả hai được tìm thấy qua \`queryNames()\`.

### Bài tập D — Tên động

1. Giả sử có hai worker tên \`Import,East\` và \`Import,West\`.
2. Tạo ObjectName bằng constructor và \`ObjectName.quote()\`.
3. So sánh với cách ghép chuỗi không escape.
4. Giải thích vì sao tên động nên được quản lý bằng factory/naming strategy thay vì annotation cố định dùng chung.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** MetadataNamingStrategy có nhiệm vụ gì?  
**Trả lời:** Xác định ObjectName cho bean từ metadata do JmxAttributeSource cung cấp.

**Câu 2.** Annotation nào chứa ObjectName tĩnh cho resource?  
**Trả lời:** \`@ManagedResource(objectName="...")\`.

**Câu 3.** MetadataNamingStrategy có đăng ký bean vào MBeanServer không?  
**Trả lời:** Không. \`MBeanExporter\` thực hiện registration.

**Câu 4.** MetadataMBeanInfoAssembler và MetadataNamingStrategy có thể dùng chung nguồn nào?  
**Trả lời:** \`AnnotationJmxAttributeSource\`.

**Câu 5.** Nếu hai bean có Spring bean name khác nhưng cùng ObjectName thì sao?  
**Trả lời:** Chúng có thể xung đột khi export vào cùng MBeanServer vì JMX dùng ObjectName làm định danh.

**Câu 6.** Có nên dùng \`com.example:type=Queue,*\` làm tên đăng ký một MBean?  
**Trả lời:** Không, đó là ObjectName pattern để truy vấn.

**Câu 7.** Với nhiều instance cùng class nhưng mỗi instance có tên runtime khác nhau, nên làm gì?  
**Trả lời:** Dùng naming/mapping programmatic tạo ObjectName riêng theo instance, xử lý giá trị động an toàn.

## 19. Ghi nhớ

- \`MetadataNamingStrategy\` là \`ObjectNamingStrategy\` đọc **tên MBean từ resource metadata**.
- \`AnnotationJmxAttributeSource\` đọc \`@ManagedResource.objectName\` và có thể được chia sẻ với \`MetadataMBeanInfoAssembler\`.
- Naming strategy quyết định **ObjectName**, assembler quyết định **management interface**, exporter thực hiện **registration**.
- Spring bean name không đồng nghĩa JMX ObjectName.
- ObjectName cần hợp lệ, concrete và không trùng trong cùng MBeanServer.
- Annotation phù hợp với tên ổn định; tên động theo instance cần quy tắc naming khác hoặc mapping programmatic.
- Kiểm tra \`ObjectName\` bằng API JMX và xác minh registration trên đúng MBeanServer.
- Thiết kế tên JMX như một hợp đồng vận hành có tính ổn định và giới hạn bảo mật rõ ràng.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`MetadataNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Spring Framework Javadoc — \`ObjectNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
