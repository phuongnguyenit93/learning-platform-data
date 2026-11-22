# Không để tên lớp Java làm hợp đồng quản trị duy nhất

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Naming strategy  
> **Bài học:** Không để tên lớp Java làm hợp đồng quản trị duy nhất

## 1. Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao **tên lớp Java** không nên là hợp đồng quản trị duy nhất của một MBean.
- Phân biệt **Spring bean name**, **Java class name**, **JMX ObjectName** và **management interface**.
- Thiết kế ObjectName có domain, key properties và quy ước phiên bản ổn định.
- Dùng \`@ManagedResource(objectName = "...")\`, \`MetadataNamingStrategy\` hoặc cơ chế đặt tên phù hợp khi export MBean.
- Hiểu việc refactor lớp Java, dùng proxy/AOP, chuyển package, tạo nhiều instance và đổi công nghệ triển khai có thể tác động tới tên MBean nếu định danh bị phụ thuộc implementation.
- Xây dựng hợp đồng quản trị dựa trên **tài nguyên, vai trò, môi trường và tính tương thích**, thay vì chỉ dùng tên class.
- Kiểm tra ObjectName và metadata JMX thực tế để bảo vệ client giám sát khỏi thay đổi vô tình.

## 2. Vấn đề: tên lớp là chi tiết triển khai, ObjectName là điểm truy cập quản trị

Trong JMX, client không tìm Spring bean bằng class Java của implementation. Nó tương tác với một MBean đã được đăng ký trong \`MBeanServer\` thông qua \`javax.management.ObjectName\`.

Một ví dụ ObjectName:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

Một ví dụ class:

\`\`\`text
com.example.cache.RedisBackedCacheService
\`\`\`

Hai chuỗi phục vụ hai mục đích khác nhau:

| Thành phần | Vai trò | Mức ổn định mong muốn |
|---|---|---|
| Java class name | Thể hiện implementation và cấu trúc code | Có thể đổi khi refactor |
| Java package | Phân nhóm mã nguồn, module | Có thể đổi khi tái cấu trúc |
| Spring bean name | Định danh bean trong ApplicationContext | Phụ thuộc cấu hình DI |
| JMX ObjectName | Định danh MBean trong MBeanServer | Nên ổn định nếu client bên ngoài sử dụng |
| Management interface | Hợp đồng attribute/operation/notification | Nên được quản lý tương thích như API |

Nếu tạo ObjectName trực tiếp từ tên lớp:

\`\`\`text
com.example.cache:type=RedisBackedCacheService
\`\`\`

thì đổi sang:

\`\`\`text
com.example.cache:type=CaffeineCacheService
\`\`\`

có thể làm hỏng truy vấn, dashboard hoặc automation vốn đang tìm MBean cũ, dù chức năng “cache chính” của ứng dụng không đổi.

**Quy tắc:** ObjectName nên đại diện cho **tài nguyên quản trị**, không chỉ phản chiếu tên lớp đang thực hiện công việc đó.

## 3. ObjectName là hợp đồng định danh

Cấu trúc ObjectName:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Ví dụ:

\`\`\`text
app.monitoring:type=Cache,name=primary
app.monitoring:type=WorkerPool,name=background
app.monitoring:type=MessageConsumer,name=orders
\`\`\`

Trong đó:

- \`domain\` nhóm MBean theo ứng dụng hoặc không gian quản trị.
- \`type\` mô tả loại tài nguyên, không nhất thiết trùng tên lớp.
- \`name\` mô tả instance hoặc vai trò.
- Các key khác như \`node\`, \`region\` hoặc \`tenant\` có thể bổ sung khi thực sự cần phân biệt nhiều instance.

ObjectName phải duy nhất trong **một MBeanServer**. Hai JVM khác nhau có thể có cùng ObjectName; client chọn JVM/server qua connection, sau đó ObjectName chọn MBean trong server đó.

Đối với client, ObjectName là điểm tìm kiếm:

\`\`\`java
ObjectName name = new ObjectName(
    "app.monitoring:type=Cache,name=primary"
);

Object entries = connection.getAttribute(
    name,
    "EntryCount"
);
\`\`\`

Nếu đổi ObjectName vô tình, client sẽ có thể gặp \`InstanceNotFoundException\`, mặc dù MBean cùng chức năng vẫn đang hoạt động dưới tên khác.

## 4. Ví dụ anti-pattern: tên lớp quyết định toàn bộ API quản trị

Giả sử ban đầu có class:

\`\`\`java
package com.example.cache;

public class RedisCacheManager {
    // ...
}
\`\`\`

Một cơ chế đặt tên tự động tạo:

\`\`\`text
com.example.cache:type=RedisCacheManager
\`\`\`

Sau một đợt refactor, class được đổi thành \`DistributedCacheManager\`. Nếu strategy tự động tạo tên từ class, JMX ObjectName cũng đổi.

\`\`\`text
Trước refactor:
  RedisCacheManager
  -> com.example.cache:type=RedisCacheManager

Sau refactor:
  DistributedCacheManager
  -> com.example.cache:type=DistributedCacheManager
\`\`\`

Hậu quả có thể là:

- JConsole không còn thấy MBean dưới tên quen thuộc.
- Monitoring agent truy vấn ObjectName cũ không nhận kết quả.
- Rule cảnh báo không tìm đúng attribute.
- Automation gọi operation qua MBean proxy thất bại.
- Runbook, tài liệu vận hành và biểu đồ không còn khớp.

Đổi tên class là thay đổi implementation thường xuyên. Nếu một thay đổi nội bộ như vậy phá vỡ client quản trị, nghĩa là thiết kế đã liên kết hợp đồng vận hành quá chặt vào code.

## 5. Thiết kế đúng: tên ổn định theo vai trò

Giữ tên tài nguyên:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

dù implementation đổi:

\`\`\`text
RedisCacheManager
       |
       v
DistributedCacheManager
       |
       v
InMemoryCacheManager
\`\`\`

\`\`\`text
                ObjectName ổn định
      app.monitoring:type=Cache,name=primary
                         |
                         v
                    MBeanServer
                         |
                         v
                   Spring JMX adapter
                         |
                         v
               Cache management facade
                         |
                 +-------+--------+
                 |                |
             Redis impl       Caffeine impl
\`\`\`

Client chỉ cần biết hợp đồng quản trị: tên tài nguyên, attributes và operations. Implementation có thể thay đổi miễn quản lý tương thích phần client thực sự sử dụng.

Tuy nhiên **ổn định tên không đủ**. Nếu giữ cùng ObjectName nhưng xóa attribute \`EntryCount\` hoặc đổi operation \`clear()\` thành \`purge(String)\`, client vẫn có thể lỗi. Hợp đồng quản trị bao gồm cả ObjectName và \`MBeanInfo\`.

## 6. Khai báo tên tường minh bằng @ManagedResource

Spring JMX hỗ trợ chỉ định ObjectName trực tiếp:

\`\`\`java
package com.example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.monitoring:type=Cache,name=primary",
    description = "Primary application cache management"
)
public class CacheManagementFacade {

    private final CacheService cacheService;

    public CacheManagementFacade(
            CacheService cacheService
    ) {
        this.cacheService = cacheService;
    }

    @ManagedAttribute(
        description = "Current number of cache entries"
    )
    public long getEntryCount() {
        return cacheService.entryCount();
    }

    @ManagedOperation(
        description = "Request cache refresh"
    )
    public void refresh() {
        cacheService.refresh();
    }
}
\`\`\`

\`CacheService\` là dependency nghiệp vụ minh họa. Class facade có thể đổi tên mà ObjectName vẫn giữ nguyên vì metadata dùng chuỗi ổn định.

Bật export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Ví dụ giả định component scan đã đưa \`CacheManagementFacade\` vào Spring context và exporter được cấu hình với MBeanServer mong muốn.

### Vì sao nên dùng facade riêng?

Một service nghiệp vụ có thể thay đổi theo nhu cầu implement. Management facade đóng vai trò adapter:

\`\`\`text
JMX contract -> facade -> business service
\`\`\`

Facade cho phép:

- Giữ ObjectName nhất quán.
- Chọn attribute và operation phù hợp với vận hành.
- Không công bố trực tiếp method nội bộ.
- Điều chỉnh implementation mà không buộc client JMX cập nhật.
- Bổ sung kiểm tra input, giới hạn phạm vi và kiểm soát tác dụng phụ.
- Tránh để proxy/AOP class quyết định định danh quản trị.

## 7. MetadataNamingStrategy trong Spring

Trong Spring JMX, việc đặt tên MBean có thể được giao cho \`org.springframework.jmx.export.naming.ObjectNamingStrategy\`. Một implementation là \`MetadataNamingStrategy\`, sử dụng metadata quản trị do \`JmxAttributeSource\` cung cấp, thường cùng \`AnnotationJmxAttributeSource\`.

Với bean có:

\`\`\`java
@ManagedResource(
    objectName = "app.monitoring:type=WorkerPool,name=main"
)
public class WorkerPoolFacade {
}
\`\`\`

metadata naming strategy có thể sử dụng tên này khi exporter đăng ký.

Điều cần phân biệt:

- **\`ObjectNamingStrategy\`** quyết định ObjectName.
- **\`JmxAttributeSource\`** cung cấp metadata annotation/descriptor.
- **\`MBeanExporter\`** đăng ký bean thành MBean.
- **\`MBeanServer\`** chứa registry và thực thi JMX operation.
- **\`MBeanInfo\`** cho client biết attribute/operation/notification đã công bố.

Không phải mọi naming strategy đều ưu tiên \`@ManagedResource.objectName\` theo cùng cách. Nếu thay strategy, hãy đọc hợp đồng của strategy đó và xác thực ObjectName thực tế sau export.

## 8. Naming strategy theo quy tắc riêng

Trong một ứng dụng nhiều module, có thể cần quy tắc ObjectName thống nhất. Spring cho phép cấu hình \`ObjectNamingStrategy\` cho exporter.

Ví dụ một strategy minh họa ánh xạ bean key được định nghĩa trước:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class StableNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey
    ) throws MalformedObjectNameException {

        if ("primaryCacheManagement".equals(beanKey)) {
            return new ObjectName(
                "app.monitoring:type=Cache,name=primary"
            );
        }

        if ("workerPoolManagement".equals(beanKey)) {
            return new ObjectName(
                "app.monitoring:type=WorkerPool,name=main"
            );
        }

        throw new IllegalArgumentException(
            "No managed ObjectName mapping for " + beanKey
        );
    }
}
\`\`\`

Ở đây ánh xạ theo **vai trò quản trị** được quản lý rõ, không theo \`managedBean.getClass().getName()\`. Chọn hành vi fail-fast nếu gặp key không hợp lệ để tránh tự động công bố tên ngoài hợp đồng đã thống nhất.

Lưu ý \`getObjectName\` được gọi trong ngữ cảnh export, và beanKey thực tế phụ thuộc cách cấu hình exporter; nếu code sử dụng bean map explicit, ta có thể kiểm soát key này dễ dàng hơn.

Ví dụ cấu hình \`MBeanExporter\` tường minh:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagementFacade cacheFacade
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "primaryCacheManagement",
            cacheFacade
        ));
        exporter.setNamingStrategy(
            new StableNamingStrategy()
        );

        return exporter;
    }
}
\`\`\`

Đây là một hướng **cấu hình tường minh thay cho annotation-driven exporter mặc định**. Tránh bật đồng thời \`@EnableMBeanExport\` và một exporter khác cùng đăng ký facade vào cùng ObjectName nếu chưa thiết kế xử lý trùng.

Trong trường hợp đơn giản, việc khai báo ObjectName tường minh qua \`@ManagedResource\` thường đủ. Custom naming strategy thích hợp hơn khi muốn enforce convention xuyên nhiều MBean.

## 9. Spring bean name không phải ObjectName

Spring bean có thể có tên:

\`\`\`text
primaryCacheManagement
\`\`\`

JMX ObjectName tương ứng:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

Hai tên không cần giống nhau. Một Spring bean name có thể thay đổi vì cấu hình DI, trong khi hợp đồng JMX vẫn được giữ ổn định.

Cũng cần tránh nhầm \`ObjectName\` với \`javax.management.MBeanInfo.getClassName()\`. MBeanInfo có thể mô tả class JMX adapter hoặc implementation tùy mô hình, nhưng client nên dùng ObjectName và metadata operation/attribute đã công bố để gọi quản trị.

## 10. Tác động của Spring AOP và proxy

Spring bean có thể được bao bọc bởi JDK dynamic proxy hoặc CGLIB proxy vì \`@Transactional\`, \`@Cacheable\`, \`@Async\` hoặc advisor khác.

\`\`\`text
Business implementation
         |
         v
Spring AOP proxy
         |
         v
JMX exporter
\`\`\`

Nếu dùng tên class runtime của proxy làm ObjectName, tên có thể chứa hậu tố động hoặc tên implementation không ổn định:

\`\`\`text
com.example.CacheService$$SpringCGLIB$$...
\`\`\`

Điều này không thích hợp làm giao diện quản trị công khai. Hệ thống JMX nên đặt tên theo tài nguyên ổn định và xác thực metadata được exporter thu thập từ bean/proxy thật.

Đồng thời, không mặc định annotation trên implementation luôn được một exporter tùy biến nhận diện giống nhau khi có JDK proxy. Hãy kiểm tra chiến lược export và MBeanInfo thực tế, đặc biệt khi management interface và implementation phân tách.

## 11. Nhiều instance cùng class

Một class \`WorkerPoolFacade\` có thể quản lý nhiều pool:

\`\`\`text
WorkerPoolFacade (instance A)
WorkerPoolFacade (instance B)
WorkerPoolFacade (instance C)
\`\`\`

Nếu định danh chỉ dựa trên class:

\`\`\`text
app.monitoring:type=WorkerPoolFacade
\`\`\`

thì không phân biệt được các instance. Khi đăng ký nhiều MBean cùng ObjectName trong một MBeanServer, có thể gặp lỗi đăng ký trùng.

Quy ước phù hợp hơn:

\`\`\`text
app.monitoring:type=WorkerPool,name=primary
app.monitoring:type=WorkerPool,name=background
app.monitoring:type=WorkerPool,name=scheduled
\`\`\`

Hoặc khi triển khai nhiều node trong cùng registry:

\`\`\`text
app.monitoring:type=WorkerPool,name=primary,node=n1
app.monitoring:type=WorkerPool,name=primary,node=n2
\`\`\`

Những key như \`node\` chỉ cần khi giải quyết đúng bài toán định danh. Không tự động đưa \`pod UID\` hoặc \`UUID\` thay đổi mỗi lần restart vào ObjectName mà các dashboard cần giữ ổn định, trừ khi monitoring được thiết kế cho instance động.

## 12. Định danh theo vai trò và khả năng mở rộng

Một quy ước có thể gồm các chiều:

\`\`\`text
<domain>:type=<role>,name=<logical-name>,node=<node-id>
\`\`\`

Các ví dụ:

\`\`\`text
myapp.management:type=Queue,name=orders
myapp.management:type=Queue,name=payments
myapp.management:type=Cache,name=catalog
myapp.management:type=WorkerPool,name=ingestion,node=n1
\`\`\`

Chú ý:

- Domain nên nhất quán giữa các phiên bản.
- \`type\` nên là thuật ngữ quản trị bền vững.
- \`name\` nên đại diện logic role/instance.
- Key thêm phải giải quyết nhu cầu phân biệt thực sự.
- Tránh đưa mật khẩu, token hoặc dữ liệu nhận dạng người dùng vào tên.
- Escape giá trị có ký tự đặc biệt bằng API \`ObjectName\` tương ứng.
- Định nghĩa quy tắc thay đổi tên và thời gian chuyển đổi cho client.

## 13. Xây ObjectName an toàn

Các ký tự đặc biệt như dấu phẩy, dấu bằng, dấu hai chấm, dấu nháy hoặc wildcard có ý nghĩa trong ObjectName.

Không nối chuỗi tùy tiện:

\`\`\`java
String rawName = userProvidedName;
String objectName =
    "app.monitoring:type=Queue,name=" + rawName;
\`\`\`

Nếu \`rawName\` có \`,\`, \`=\`, \`*\` hoặc ký tự đặc biệt, kết quả có thể không hợp lệ hoặc bị hiểu là một pattern.

Có thể tạo ObjectName với giá trị được quote:

\`\`\`java
String rawName = "orders,high-priority";

ObjectName name = new ObjectName(
    "app.monitoring:type=Queue,name="
        + ObjectName.quote(rawName)
);
\`\`\`

Nếu dùng user input, ngoài escape còn cần validation và giới hạn độ dài. Một ObjectName hợp lệ vẫn có thể gây ra cardinality quá cao hoặc làm lộ dữ liệu không phù hợp cho hệ thống monitoring.

## 14. Truy vấn theo pattern mà không phụ thuộc class

Monitoring client có thể tìm tất cả queue:

\`\`\`java
ObjectName pattern = new ObjectName(
    "app.monitoring:type=Queue,*"
);

Set<ObjectName> names =
    connection.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Pattern dựa trên **loại tài nguyên**, không cần biết class Java nào thực thi queue. Sau đó client có thể đọc attribute được định nghĩa trong management contract chung.

\`queryNames\` trả snapshot các MBean đang đăng ký; nếu một MBean mới xuất hiện sau đó, client phải query lại hoặc theo dõi lifecycle của registry.

Cần phân biệt:

\`\`\`text
app.monitoring:type=Queue
\`\`\`

là ObjectName chính xác không có property bổ sung, còn:

\`\`\`text
app.monitoring:type=Queue,*
\`\`\`

là property-list pattern có thể khớp các tên có \`name\`, \`node\` hoặc key khác.

## 15. Quản lý hợp đồng operation và attribute

Ổn định ObjectName là bước đầu. Một dashboard cũng có thể đang dùng:

\`\`\`text
Attribute: QueueDepth
Operation: pause()
Notification: app.queue.depth.high
\`\`\`

Nếu đổi \`QueueDepth\` thành \`PendingMessages\` mà không có compatibility plan, dashboard vẫn có thể hỏng dù ObjectName giữ nguyên.

Hợp đồng quản trị gồm:

| Thành phần | Ví dụ | Rủi ro khi đổi |
|---|---|---|
| ObjectName | \`app.monitoring:type=Queue,name=orders\` | Client không tìm MBean |
| Attribute name | \`QueueDepth\` | Polling metrics lỗi |
| Attribute type | \`long\` | Chuyển đổi dữ liệu lỗi |
| Operation name | \`pause\` | Invocation không còn hợp lệ |
| Operation signature | \`setLimit(int)\` | Client gửi signature cũ |
| Notification type | \`app.queue.depth.high\` | Listener filter không nhận event |
| Return type | \`java.lang.String\` | Client không giải mã như kỳ vọng |

Nếu cần thay một hợp đồng đã được bên ngoài sử dụng, có thể hỗ trợ song song tên cũ và tên mới trong một thời gian chuyển tiếp, hoặc phát hành version có tài liệu rõ ràng.

## 16. Quản lý tương thích khi đổi tên

Giả sử quy ước cũ:

\`\`\`text
app.monitoring:type=LegacyQueueManager,name=orders
\`\`\`

và muốn chuyển sang:

\`\`\`text
app.monitoring:type=Queue,name=orders
\`\`\`

Chiến lược chuyển đổi có thể gồm:

1. Kiểm kê client, dashboard, alert, runbook và automation đang dùng tên cũ.
2. Cung cấp MBean mới cùng attribute/operation tương thích.
3. Duy trì tên cũ như một alias hoặc adapter trong giai đoạn chuyển tiếp nếu hạ tầng cho phép.
4. Thông báo lịch ngừng hỗ trợ và cập nhật client.
5. Gỡ tên cũ có kiểm soát sau khi xác minh usage đã chuyển.

JMX MBeanServer không tự tạo alias chỉ từ hai ObjectName. Nếu cần hai tên cùng tồn tại, phải đăng ký adapter hoặc MBean phù hợp dưới từng tên và quản lý lifecycle, registration conflicts và tính nhất quán trạng thái.

Không tự ý unregister MBean đang được công cụ khác dùng chỉ để “dọn tên”.

## 17. Kiểm chứng tên thực tế bằng MBeanServer

Sau khi Spring exporter hoạt động, có thể kiểm tra:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "app.monitoring:type=Cache,name=primary"
);

System.out.println(
    "Registered: " + server.isRegistered(expected)
);
\`\`\`

Ví dụ dùng platform MBeanServer. Nếu exporter cấu hình server riêng, phải truy cập đúng server đó; không thấy MBean trên platform server không chứng minh export thất bại.

Kiểm tra metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(expected);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(
        a.getName() + ": " + a.getType()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        op.getName() + " -> " + op.getReturnType()
    );
}
\`\`\`

Những đoạn code dùng \`MBeanInfo\`, \`MBeanAttributeInfo\`, \`MBeanOperationInfo\` cần import các class tương ứng trong \`javax.management\`.

Đối chiếu cả ObjectName lẫn bề mặt operation/attribute là cách xác thực contract của MBean đã đăng ký.

## 18. Integration test bảo vệ ObjectName ổn định

Có thể viết bài test trên context Spring có JMX export để bảo đảm tên dự kiến tồn tại:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class JmxNamingContractTest {

    private final MBeanServer server;

    JmxNamingContractTest(MBeanServer server) {
        this.server = server;
    }

    @Test
    void stableCacheNameIsRegistered() throws Exception {
        ObjectName expected = new ObjectName(
            "app.monitoring:type=Cache,name=primary"
        );

        assertTrue(server.isRegistered(expected));
    }
}
\`\`\`

Đây là mẫu assertion về naming contract; trong test thực tế, phải bootstrap Spring context và cung cấp \`MBeanServer\` được exporter sử dụng. Không giả định JUnit tự inject MBeanServer vào constructor test trên mọi cấu hình.

Khi service implementation được đổi tên, test này vẫn phải pass nếu hợp đồng JMX giữ nguyên.

Một bài test cao hơn có thể đọc \`MBeanInfo\` để xác nhận các attribute/operation được yêu cầu vẫn tồn tại và có kiểu tương thích.

## 19. Không để Java package trở thành namespace quản trị duy nhất

Ví dụ domain lấy thẳng package:

\`\`\`text
com.example.orders.infrastructure.cache:type=RedisCache
\`\`\`

Có thể phù hợp khi dùng cho công cụ phát triển ngắn hạn, nhưng dễ ràng buộc client vận hành vào cấu trúc module.

Một domain ổn định hơn:

\`\`\`text
com.example.app.management:type=Cache,name=orders
\`\`\`

Domain JMX không bắt buộc phải là Java package. Có thể dùng chuỗi có quy tắc riêng cho tổ chức và ứng dụng, miễn tên hợp lệ và không trùng ngoài ý muốn.

Tránh gắn version triển khai hoặc hash build vào ObjectName nếu mục tiêu là quản trị một logical resource liên tục. Có thể expose phiên bản như attribute \`Version\` nếu cần quan sát; điều đó không buộc thay định danh của tài nguyên.

## 20. Versioning trong hợp đồng quản trị

Khi thay đổi không tương thích thực sự cần thiết, có thể quản lý version theo các cách:

- Domain phiên bản mới, ví dụ \`app.management.v2\`.
- Key property version, ví dụ \`version=2\`.
- Loại MBean mới với hợp đồng tách biệt, ví dụ \`type=QueueControlV2\`.
- Hỗ trợ operation/attribute mới song song nếu tương thích.

Không có một quy tắc versioning duy nhất cho mọi ứng dụng. Quan trọng là client có thể phân biệt hợp đồng cũ/mới, và có kế hoạch chuyển đổi thay vì vô tình đổi tên khi refactor.

Với thay đổi nội bộ không làm đổi hành vi quản trị, **không nên tăng version hoặc đổi ObjectName chỉ vì class đã được rename**.

## 21. Thận trọng với cardinality và vòng đời MBean

Một số ứng dụng tạo MBean động theo mỗi connection, request, tenant hoặc worker. Nếu ObjectName chứa ID ngẫu nhiên hoặc các thuộc tính tăng không giới hạn, MBeanServer có thể có quá nhiều tên và dashboard phải quản lý số lượng instance lớn.

Nên cân nhắc:

- MBean theo logical resource thay vì mọi object ngắn hạn.
- Chỉ thêm key property khi cần phân biệt trên mặt vận hành.
- Register/unregister theo lifecycle rõ ràng.
- Tổng hợp metrics cho các object rất ngắn hạn thay vì xuất riêng từng object.
- Tránh đưa thông tin cá nhân hoặc secret vào domain/key properties.

Nếu cần giám sát hàng chục nghìn đối tượng động, JMX MBean riêng cho từng object có thể không phải thiết kế tốt nhất.

## 22. Những lỗi thường gặp

### MBean biến mất sau refactor

Nguyên nhân có thể là strategy dùng class name, package name, Spring bean name hoặc proxy class. So sánh ObjectName trước/sau và thay bằng contract định danh ổn định.

### MBean bị đăng ký trùng

Hai bean cùng được gán ObjectName sẽ xung đột trong một server. Kiểm tra uniqueness của \`domain + key properties\`, đặc biệt khi nhiều instance dùng cùng class.

### Dashboard không tìm thấy nhưng JConsole vẫn thấy MBean

Có thể MBean đã được đăng ký dưới tên mới. Dùng \`queryNames\` để tìm, rồi xác định xem client đang hardcode tên cũ hay MBeanServer/connection có khác.

### Attribute vẫn tồn tại nhưng client lỗi

Kiểm tra kiểu dữ liệu, readability, signature operation và access rights. Tên ổn định không thay thế compatibility của management interface.

### Dùng tên proxy động trong ObjectName

Thay cách tạo tên bằng metadata hoặc naming strategy theo logical resource, tránh \`getClass().getName()\` của proxy làm contract.

### Giá trị key có dấu phẩy hoặc ký tự đặc biệt

Dùng \`ObjectName.quote\` và input validation thay vì nối chuỗi không được kiểm soát.

## 23. Bài tập thực hành

Giả sử một ứng dụng có ba class:

\`\`\`text
com.example.redis.RedisCacheService
com.example.queue.RabbitMqQueueService
com.example.workers.FixedThreadPoolService
\`\`\`

Đề xuất ObjectName không phụ thuộc tên class:

\`\`\`text
app.management:type=Cache,name=catalog
app.management:type=Queue,name=orders
app.management:type=WorkerPool,name=background
\`\`\`

Sau đó giả sử:

- Redis cache được thay bằng Caffeine.
- RabbitMQ được thay bằng một message transport khác.
- Thread pool thay đổi implementation.

Nếu bề mặt quản trị không đổi, những ObjectName trên vẫn có thể giữ nguyên. Việc thay công nghệ không nhất thiết là breaking change đối với client JMX.

**Bài tập tiếp:** Viết một test truy vấn ObjectName \`app.management:type=Queue,name=orders\`, kiểm tra MBean có attribute \`QueueDepth\` kiểu \`long\`, và xác nhận một operation \`pause()\` có chữ ký rỗng. Nếu method Java nội bộ đổi từ \`pauseQueue\` sang \`stopConsumer\` nhưng operation JMX đã được các client dùng dưới tên \`pause\`, bạn sẽ thiết kế facade như thế nào để giữ hợp đồng?

## 24. Câu hỏi tự kiểm tra

1. Vì sao Java class name không phải định danh đủ ổn định cho client JMX?
2. Spring bean name khác JMX ObjectName ở điểm nào?
3. Trong ObjectName, domain, type và name mang những vai trò gì?
4. Vì sao CGLIB/JDK proxy làm class runtime kém phù hợp cho naming contract?
5. Khi nhiều instance cùng class, cần thêm property nào để tránh xung đột?
6. Vì sao không nên đưa user ID hoặc token vào ObjectName?
7. \`@ManagedResource(objectName = "...")\` giúp tách hợp đồng khỏi implementation như thế nào?
8. Khi nào cần custom \`ObjectNamingStrategy\` thay vì khai báo tên trực tiếp?
9. Giữ ObjectName cũ nhưng đổi signature operation có thể gây lỗi gì?
10. Có nên đổi domain JMX mỗi lần tăng build version không? Vì sao?

## 25. Ghi nhớ

\`\`\`text
Implementation detail:
    Java class / package / proxy / bean name
                    |
                    v
            Có thể đổi khi refactor

Management contract:
    ObjectName + attributes + operations + notifications
                    |
                    v
          Cần ổn định và có versioning
          khi client bên ngoài phụ thuộc
\`\`\`

**Nguyên tắc cốt lõi:** đặt tên MBean theo **tài nguyên và vai trò quản trị**, không chỉ theo class Java. Duy trì ObjectName và metadata như một hợp đồng API, chọn một naming strategy có quy tắc, kiểm tra tên đã đăng ký trong MBeanServer và có kế hoạch tương thích khi thay đổi.