# Thực hành đặt ObjectName bằng naming strategy trong Spring Framework JMX

## 1. Mục tiêu của bài thực hành

Trong Java Management Extensions (JMX), mỗi MBean được đăng ký vào `MBeanServer` dưới một `ObjectName`, ví dụ `com.example.orders:type=Queue,name=Primary`. ObjectName là khóa mà JConsole, VisualVM, JMX clients, monitoring collector và Spring `MBeanProxyFactoryBean` dùng để tìm đúng tài nguyên quản trị.

Spring Framework hỗ trợ xuất MBean từ Spring-managed beans thông qua `MBeanExporter`. Thay vì hard-code mọi ObjectName ngay tại từng bean, ta có thể triển khai hoặc cấu hình một **`ObjectNamingStrategy`** để sinh tên theo quy tắc nhất quán. Bài thực hành này tạo hai management beans, khai báo map của exporter, áp dụng naming strategy và kiểm chứng các tên thực tế trên MBeanServer.

Bạn sẽ nắm được:

- Cấu trúc `domain:key=value` và cách ObjectName phân biệt các MBean.
- Khác biệt giữa Spring bean name, map key của exporter và JMX ObjectName.
- Cách dùng interface `org.springframework.jmx.export.naming.ObjectNamingStrategy`.
- Cách kết nối strategy với `MBeanExporter.setNamingStrategy(...)`.
- Cách thiết kế domain và key properties theo ứng dụng, loại tài nguyên và instance.
- Cách xử lý ký tự đặc biệt và collision khi nhiều MBean cùng tên.
- Cách kiểm chứng kết quả bằng `MBeanServer.queryNames`/`getMBeanInfo`.

**Kết quả mong muốn:** ứng dụng đăng ký hai MBean với tên ổn định và dễ đọc:

```text
com.example.ordering:type=Queue,name=Primary
com.example.ordering:type=Cache,name=Primary
```

## 2. Tại sao cần ObjectNamingStrategy?

Không có strategy tập trung, application có thể dùng nhiều kiểu đặt tên rời rạc:

```text
app:type=Queue
com.example.cache:name=main
myModule:bean=cacheManagement
```

Những tên này có thể hợp lệ nhưng khó quản lý ở hệ thống lớn. Nếu mỗi team dùng một quy ước, JMX collector phải query nhiều domain/key khác nhau và có thể bị lỗi sau khi refactor bean name.

`ObjectNamingStrategy` giải quyết câu hỏi **“Đối tượng quản trị này phải được đăng ký bằng ObjectName nào?”**. Nó không quyết định method nào được export; phần đó thuộc JMX MBean convention, `MBeanInfoAssembler` hoặc annotation metadata.

```text
Spring beans
    |
    v
MBeanExporter
    |
    +-- Bean selection: setBeans / autodetection
    +-- ObjectNamingStrategy: ObjectName của mỗi bean
    +-- MBeanInfoAssembler: attributes / operations
    v
MBeanServer
    |
    v
JMX clients
```

## 3. ObjectName và quy tắc duy nhất

JMX ObjectName có cấu trúc:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.ordering:type=Queue,name=Primary
```

- `com.example.ordering`: domain.
- `type=Queue`: phân loại MBean.
- `name=Primary`: định danh một instance.

Trong **một MBeanServer**, mỗi ObjectName phải là duy nhất. Hai MBean có cùng ObjectName không được đồng thời đăng ký; việc này có thể tạo `InstanceAlreadyExistsException` hoặc hành vi tương ứng với `RegistrationPolicy`.

Thứ tự các key properties không ảnh hưởng định danh:

```java
ObjectName a = new ObjectName(
    "com.example.ordering:type=Queue,name=Primary"
);
ObjectName b = new ObjectName(
    "com.example.ordering:name=Primary,type=Queue"
);
System.out.println(a.equals(b)); // true
```

Không dùng việc đổi thứ tự `type`/`name` để tránh collision. Cần thay domain hoặc giá trị key property thực sự khi hai tài nguyên khác nhau.

## 4. Phân biệt ba loại tên

| Loại | Ví dụ | Vai trò |
| --- | --- | --- |
| Spring bean name | `queueManagement` | Định danh bean trong `ApplicationContext` |
| Exporter map key | `Queue:Primary` | Đầu vào do người cấu hình đưa vào exporter |
| JMX ObjectName | `com.example.ordering:type=Queue,name=Primary` | Tên thực tế đăng ký trong `MBeanServer` |

Map key có thể chứa ObjectName đầy đủ hoặc định danh logic. Khi dùng custom strategy, key trở thành dữ liệu đầu vào của phương thức `getObjectName(managedBean, beanKey)`. Vì vậy cần document format của key và kiểm tra lỗi định dạng tại startup.

**Lưu ý:** nếu bean export qua annotation-based naming strategy thay vì strategy bạn tạo, ObjectName có thể được lấy từ `@ManagedResource`. Cách chọn strategy phải phù hợp loại exporter và đường cấu hình; không giả định mọi annotation sẽ override custom naming strategy.

## 5. Tạo hai management beans minh họa

Đầu tiên tạo một MBean quản trị queue theo Standard MBean convention:

```java
package com.example.management;

public interface QueueMonitorMBean {
    int getPendingCount();
    void requestRefresh();
}
```

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicInteger pending = new AtomicInteger(5);

    @Override
    public int getPendingCount() {
        return pending.get();
    }

    @Override
    public void requestRefresh() {
        // Chỉ minh họa; ứng dụng thật nên dùng task có giới hạn.
        pending.set(0);
    }
}
```

Tiếp theo tạo cache management bean:

```java
package com.example.management;

public interface CacheMonitorMBean {
    long getEntryCount();
}
```

```java
package com.example.management;

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public long getEntryCount() {
        return 42L;
    }
}
```

Đây là hai Standard MBeans hợp lệ theo quy ước class `QueueMonitor` implements `QueueMonitorMBean`, class `CacheMonitor` implements `CacheMonitorMBean`. Khi MBeanExporter nhận các object này, nó có thể đăng ký theo contract JMX tiêu chuẩn. Ví dụ không đòi hỏi reflection assembler để expose toàn bộ public methods.

Trong ứng dụng thực, management beans nên delegate tới services và trả những thông tin vận hành an toàn, thay vì chứa business logic hoặc secrets.

## 6. Tạo custom ObjectNamingStrategy

Ta chọn map key có dạng `type:name`, chẳng hạn `Queue:Primary` và `Cache:Primary`. Strategy sẽ phân tích key rồi tạo ObjectName.

```java
package com.example.management;

import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class ApplicationObjectNamingStrategy
        implements ObjectNamingStrategy {

    private final String domain;

    public ApplicationObjectNamingStrategy(String domain) {
        if (domain == null || !domain.matches("[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException("Invalid JMX domain");
        }
        this.domain = domain;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        if (beanKey == null) {
            throw new IllegalArgumentException("beanKey is required");
        }
        int delimiter = beanKey.indexOf(':');
        if (delimiter <= 0 || delimiter == beanKey.length() - 1) {
            throw new IllegalArgumentException(
                "Expected bean key type:name, got " + beanKey
            );
        }

        String type = beanKey.substring(0, delimiter);
        String name = beanKey.substring(delimiter + 1);
        if (!type.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid type: " + type);
        }

        return new ObjectName(
            domain + ":type=" + type + ",name=" + ObjectName.quote(name)
        );
    }
}
```

Giải thích:

1. Constructor nhận domain cấu hình và kiểm tra cú pháp theo quy ước ứng dụng.
2. `getObjectName(Object managedBean, String beanKey)` là phương thức contract của Spring naming strategy.
3. Phần trước dấu `:` là loại MBean; phần sau là tên instance.
4. `ObjectName.quote(name)` bảo vệ các ký tự như dấu phẩy hoặc dấu hai chấm trong property value.
5. `ObjectName` kiểm tra cú pháp JMX, và `MBeanExporter` dùng kết quả để đăng ký.

Regex trong ví dụ là **quy ước nội bộ**, không phải toàn bộ ngữ pháp hợp lệ của JMX. Giá trị `type` được giới hạn để không trở thành wildcard hoặc chuỗi làm thay đổi cấu trúc key. Trong production, định danh gửi vào strategy cần được kiểm soát và không chứa thông tin nhạy cảm.

## 7. Kết nối strategy với MBeanExporter

```java
package com.example.config;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import com.example.management.ApplicationObjectNamingStrategy;
import com.example.management.CacheMonitor;
import com.example.management.QueueMonitor;

@Configuration
public class JmxManagementConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            QueueMonitor queueMonitor, CacheMonitor cacheMonitor) {
        Map<String, Object> beans = new LinkedHashMap<>();
        beans.put("Queue:Primary", queueMonitor);
        beans.put("Cache:Primary", cacheMonitor);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(beans);
        exporter.setNamingStrategy(
            new ApplicationObjectNamingStrategy("com.example.ordering")
        );
        return exporter;
    }
}
```

Với thiết kế này, exporter sẽ xin ObjectName của từng bean qua strategy khi đăng ký. Kết quả mong muốn:

```text
Queue:Primary -> com.example.ordering:type=Queue,name="Primary"
Cache:Primary -> com.example.ordering:type=Cache,name="Primary"
```

**Chi tiết quan trọng:** `ObjectName.quote("Primary")` tạo representation có dấu nháy cho key value, tức tên thực tế của ví dụ là `name="Primary"`. Trong JMX, value được quote và value không quote có thể tạo sự khác biệt về biểu diễn/semantics nên khi viết client exact ObjectName phải dùng đúng canonical name do strategy trả về, thay vì tự gõ phiên bản không quote.

Nếu muốn tên hiển thị đúng chuỗi không quote `name=Primary` với dữ liệu luôn an toàn, có thể xây ObjectName bằng `Hashtable<String,String>` từ các value đã kiểm soát theo quy tắc JMX. Trong bài này dùng quote nhất quán để minh họa xử lý value tự do và sẽ kiểm tra đúng ObjectName được tạo.

## 8. Dùng cùng tên ở phía client

Để tránh lỗi hard-code khác biệt giữa server và client, có thể trích quy tắc sinh tên thành một hàm chung:

```java
ObjectNamingStrategy naming =
    new ApplicationObjectNamingStrategy("com.example.ordering");

ObjectName queueName = naming.getObjectName(
    queueMonitor,
    "Queue:Primary"
);

ObjectName cacheName = naming.getObjectName(
    cacheMonitor,
    "Cache:Primary"
);
```

Client có thể dùng `MBeanServer.getAttribute(queueName, "PendingCount")`. Nếu client là remote, nên có một contract ổn định về domain và keys, hoặc discovery theo pattern rồi chọn MBean chính xác. Không yêu cầu client instantiate mọi application bean chỉ để sinh tên; ví dụ minh họa reuse strategy ở nội bộ, còn module client độc lập nên dùng một class naming contract nhỏ không phụ thuộc business object.

## 9. Kiểm tra các MBean đã đăng ký

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.ordering:*"
);

Set<ObjectName> registered = server.queryNames(pattern, null);
registered.stream()
    .map(ObjectName::getCanonicalName)
    .sorted()
    .forEach(System.out::println);
```

Nếu exporter đăng ký vào platform MBeanServer, bạn sẽ thấy các ObjectName do strategy sinh ra. Nếu đã cấu hình dedicated MBeanServer, phải query đúng server đó thay vì gọi platform server mặc định.

Kiểm tra tên exact:

```java
ObjectName queueName = new ApplicationObjectNamingStrategy(
    "com.example.ordering"
).getObjectName(queueMonitor, "Queue:Primary");

System.out.println(server.isRegistered(queueName));
System.out.println(server.getMBeanInfo(queueName).getClassName());
System.out.println(server.getAttribute(queueName, "PendingCount"));
```

Đoạn code giả định có `queueMonitor` là instance dùng trong cấu hình. Khi debug lỗi tên, in `getCanonicalName()` của ObjectName thực tế thay vì đoán theo Spring bean name.

## 10. Thử nghiệm bằng JUnit 5

Có thể kiểm tra naming strategy thuần mà không khởi động Spring context:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ApplicationObjectNamingStrategyTest {
    private final ApplicationObjectNamingStrategy naming =
        new ApplicationObjectNamingStrategy("com.example.ordering");

    @Test
    void namesQueueAndCacheDifferently() throws Exception {
        ObjectName queue = naming.getObjectName(null, "Queue:Primary");
        ObjectName cache = naming.getObjectName(null, "Cache:Primary");

        assertNotEquals(queue, cache);
        assertEquals("com.example.ordering", queue.getDomain());
        assertEquals("Queue", queue.getKeyProperty("type"));
    }

    @Test
    void handlesSpecialCharactersInName() throws Exception {
        ObjectName name = naming.getObjectName(
            null, "Queue:payments,west"
        );
        assertFalse(name.isPattern());
        assertEquals("com.example.ordering", name.getDomain());
        assertNotNull(name.getKeyProperty("name"));
    }

    @Test
    void rejectsMalformedKey() {
        assertThrows(IllegalArgumentException.class,
            () -> naming.getObjectName(null, "QueueOnly"));
    }
}
```

Ở đây implementation không sử dụng managedBean nên truyền null trong unit test là hợp lệ cho riêng strategy minh họa. Với strategy khác dựa trên target class hoặc annotation, cần truyền đối tượng thật.

Test cấu trúc MBean sau Spring startup cũng quan trọng, vì unit test trên strategy không chứng minh exporter thực sự đã đăng ký bean hoặc chọn đúng MBeanServer.

## 11. Cấu hình domain theo environment

Thay vì hard-code domain trong `@Bean`, đọc từ property:

```properties
jmx.management.domain=com.example.ordering.dev
```

Trong production:

```properties
jmx.management.domain=com.example.ordering
```

Cấu hình:

```java
import org.springframework.beans.factory.annotation.Value;

@Bean
public MBeanExporter exporter(
        QueueMonitor queue, CacheMonitor cache,
        @Value("${jmx.management.domain}") String domain) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "Queue:Primary", queue,
        "Cache:Primary", cache
    ));
    exporter.setNamingStrategy(
        new ApplicationObjectNamingStrategy(domain)
    );
    return exporter;
}
```

Thuộc tính `jmx.management.domain` là **property tùy biến của ví dụ**, không phải property đặc biệt mà Spring Framework tự động áp dụng cho mọi exporter. Việc truyền giá trị vào naming strategy mới làm nó có tác dụng.

Đừng đổi domain giữa các môi trường chỉ để tránh collision nếu các môi trường chạy ở các JVM riêng. Tên ổn định có thể giúp reuse dashboards. Khi các module chia sẻ cùng server, app/module identity mới là thông tin cần phân biệt nhất.

## 12. Những naming strategy sẵn có trong Spring

Không phải lúc nào cũng cần tự viết class. Spring JMX có các chiến lược đặt tên như:

- `KeyNamingStrategy`: sử dụng key hoặc mapping cấu hình để tìm ObjectName.
- `MetadataNamingStrategy`: dùng JMX annotation metadata, đặc biệt `@ManagedResource` kết hợp `JmxAttributeSource`.
- `IdentityNamingStrategy`: sinh định danh dựa trên class và identity của instance.

Tùy phiên bản Spring Framework và nhu cầu, nên chọn strategy có sẵn khi nó đáp ứng quy tắc đặt tên. Custom strategy hữu ích khi yêu cầu domain/module/instance naming của tổ chức không thể biểu diễn trực tiếp bằng mapping/annotation.

**Cảnh báo:** chiến lược dựa trên identity có thể cho tên thay đổi theo instance và restart, khiến dashboard/proxy khó sử dụng tên cố định. Với MBeans được giám sát lâu dài, naming ổn định thường tốt hơn.

## 13. Annotation-based naming khác gì custom strategy?

Với annotation-based exporter:

```java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.ordering:type=Queue,name=Main"
)
public class QueueManagement {
    // @ManagedAttribute, @ManagedOperation...
}
```

`MetadataNamingStrategy` có thể lấy ObjectName từ annotation. Ngược lại, custom strategy của bài này sinh tên từ map key `Queue:Primary`. Không nên vừa cung cấp nhiều nguồn tên mâu thuẫn, vừa mong exporter tự chọn “tên đúng” theo ý muốn mà không biết thứ tự xử lý.

Nếu organization dùng annotation-based export rộng, có thể áp dụng convention trong annotations và viết test kiểm tra ObjectName. Nếu có một nhóm nhỏ endpoint cần tên được cấu hình ở một nơi, map explicit và custom strategy dễ kiểm soát hơn.

## 14. Xử lý trùng ObjectName

Nếu strategy trả cùng ObjectName cho hai bean khác nhau, exporter có thể gặp lỗi registration:

```text
javax.management.InstanceAlreadyExistsException:
  com.example.ordering:type=Queue,name="Primary"
```

Nguyên nhân có thể:

- Hai map keys khác nhau nhưng strategy làm mất thông tin phân biệt.
- Hai instances có cùng `type`/`name` trên cùng MBeanServer.
- Một exporter khác đã đăng ký cùng ObjectName.
- MBean cũ chưa unregister sau redeploy.
- Spring profile/config tạo duplicate beans.

Giải pháp ưu tiên là **sửa naming để mỗi resource có tên duy nhất**, ví dụ thêm `instance` hoặc `application` key đúng nơi cần thiết.

Spring cung cấp `RegistrationPolicy`:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

`FAIL_ON_EXISTING` giúp phát hiện collision; `IGNORE_EXISTING` bỏ qua MBean mới nếu đã có; `REPLACE_EXISTING` có thể thay MBean của module khác. Không dùng `REPLACE_EXISTING` mặc định để che lỗi naming.

## 15. Tránh nhầm các key values với thông tin nhạy cảm

ObjectName thường hiển thị trong JConsole và queryNames, vì vậy không đưa:

- Password, access token, session token hoặc API key.
- Email, số điện thoại, account/customer identifier nhạy cảm.
- Database connection string có credential.
- Các business payload dài hoặc object-specific secrets.

Ví dụ anti-pattern:

```text
com.example.auth:type=Session,token=eyJhbGciOiJI...
```

Nên dùng ID opaque không nhạy cảm hoặc MBean tổng hợp:

```text
com.example.auth:type=SessionMetrics,name=Global
```

`ObjectName.quote` chỉ escape ký tự cú pháp, không mã hóa hoặc che dữ liệu. Quản lý quyền JMX connector và giới hạn nội dung metadata vẫn cần thiết.

## 16. Naming ổn định cho nhiều instance

Nếu hai `QueueMonitor` cùng server:

```text
com.example.ordering:type=Queue,name=Primary,instance=worker-a
com.example.ordering:type=Queue,name=Primary,instance=worker-b
```

Strategy có thể được mở rộng để sinh `instance` từ cấu hình deployment. Nên dùng identifier ổn định nếu client phụ thuộc vào tên; tránh PID hoặc timestamp ngẫu nhiên trừ khi thực sự cần theo dõi các MBeans tạm thời.

Nếu hai replica chạy trên **hai JVM khác nhau** với MBeanServer riêng, cùng ObjectName không xung đột trực tiếp. Trong trường hợp này, client phân biệt bằng connection/instance metadata bên ngoài JMX.

## 17. Common pitfalls và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| MBean không xuất hiện đúng tên | Exporter không dùng strategy dự kiến | Kiểm tra `setNamingStrategy` và đường export |
| JConsole thấy key có dấu nháy | Strategy dùng `ObjectName.quote` | Dùng exact canonical name; thống nhất client/server |
| `MalformedObjectNameException` | Key/domain không hợp lệ | Validate và quote value đúng cách |
| `InstanceAlreadyExistsException` | Strategy sinh duplicate name | Thêm identity rõ ràng, sửa owner/exporter |
| MBean có tên khác sau restart | Identity/bean name/instance ID biến động | Dùng domain/keys ổn định |
| Client proxy không tìm thấy MBean | ObjectName proxy khác tên được export | Share naming contract và kiểm tra queryNames |
| Chỉ có class name thay vì type mong muốn | Đang dùng default/Identity naming strategy | Cấu hình custom/Metadata/KeyNamingStrategy đúng |
| Bật autodetection rồi tên bị trùng | Bean mới được phát hiện nhưng name không đủ phân biệt | Tách scope hoặc bổ sung key properties |
| Thay domain khiến monitoring lỗi | ObjectName là management API | Cập nhật dashboard/proxy theo migration plan |

## 18. Checklist thực hành

1. Định nghĩa namespace domain rõ ràng theo app/module.
2. Quyết định key properties như `type`, `name`, `application`, `instance`.
3. Tránh giá trị bí mật/PII trong ObjectName.
4. Chọn format map key có schema ổn định hoặc dùng annotation mapping.
5. Viết `ObjectNamingStrategy` và validate đầu vào.
6. Quote values động có ký tự JMX đặc biệt; nhất quán với client.
7. Cấu hình `MBeanExporter.setBeans` và `setNamingStrategy` cùng một nơi.
8. Xác nhận target beans thực sự JMX-compliant hoặc có assembler phù hợp.
9. Kiểm tra `MBeanServer.queryNames` sau startup.
10. Thêm unit test naming và integration test MBeanInfo.
11. Chọn `RegistrationPolicy` để phát hiện collision thay vì che lỗi.
12. Document ObjectName như một API ổn định cho monitoring và JMX proxy.

## 19. Mô hình tư duy kết luận

```text
Spring ApplicationContext
       |
       +-- QueueMonitor bean
       +-- CacheMonitor bean
       |
       v
MBeanExporter.setBeans
       |
       +-- Queue:Primary
       +-- Cache:Primary
       |
       v
ApplicationObjectNamingStrategy
       |
       +-- domain: com.example.ordering
       +-- type/name properties
       |
       v
ObjectName
       |
       v
MBeanServer register
       |
       v
JConsole / collector / JMX proxy
```

**Kết luận:** dùng `ObjectNamingStrategy` là cách thiết kế tên JMX **nhất quán, kiểm chứng được và ổn định**. Hãy xác định rõ input key, domain, key properties và chính sách quote/validation, rồi kết nối strategy với `MBeanExporter`. Sau đó xác nhận ObjectName thực tế trên MBeanServer, kiểm tra collision/lifecycle và giữ naming contract ổn định cho clients. Naming strategy quyết định **MBean được gọi bằng tên nào**, không quyết định MBean expose những operations nào hoặc quyền truy cập JMX.
