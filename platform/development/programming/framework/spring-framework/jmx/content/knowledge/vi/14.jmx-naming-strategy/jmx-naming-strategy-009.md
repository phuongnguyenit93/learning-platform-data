# Kiểm thử tên bằng ObjectName và MBeanServer trong Spring JMX

## 1. Mục tiêu

Trong Spring Framework JMX, chiến lược đặt tên quyết định **ObjectName nào** được dùng khi xuất một bean thành MBean. Một tên sai cú pháp, thiếu khóa định danh hoặc trùng với tên đã đăng ký có thể khiến application context không khởi động, hoặc khiến hệ thống giám sát theo dõi sai thành phần.

Sau bài này, bạn có thể:

- Tạo và kiểm tra `javax.management.ObjectName` đúng cú pháp.
- Phân biệt chuỗi biểu diễn tên với danh tính JMX và canonical name.
- Dùng `MBeanServer` để xác minh MBean đã được đăng ký dưới tên mong đợi.
- Phát hiện xung đột tên, thiếu key property, tên chứa ký tự đặc biệt và thay đổi tên sau restart.
- Viết unit test cho `ObjectNamingStrategy` và integration test cho `MBeanExporter`.
- Kiểm tra đầy đủ vòng đời đăng ký/hủy đăng ký, đồng thời hiểu giới hạn của kiểm thử local so với remote JMX.

## 2. ObjectName là hợp đồng định danh

Tên JMX có dạng:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.orders:type=Queue,name=Payment
com.example.orders:type=Queue,name=Refund
com.example.orders:type=WorkerPool,name=Billing
```

`domain` phân nhóm MBean; các cặp key–value là **key properties**. Toàn bộ `ObjectName` dùng để xác định duy nhất một MBean **trong phạm vi một MBeanServer**.

Một naming strategy của Spring biến bean hoặc metadata thành `ObjectName`. Với hai bean khác nhau, strategy phải tạo tên khác nhau khi chúng cần được đăng ký đồng thời:

```text
Spring bean "paymentQueue" --> com.example.orders:type=Queue,name=Payment
Spring bean "refundQueue"  --> com.example.orders:type=Queue,name=Refund
```

Mục tiêu kiểm thử là bảo đảm tên được tạo **đúng, duy nhất, ổn định và có thể truy cập**, không chỉ bảo đảm kết quả là một chuỗi không rỗng.

## 3. Kiểm tra cú pháp ObjectName

`ObjectName` là kiểu dữ liệu của JMX; hãy dùng API của nó thay vì tự xác minh chuỗi bằng regular expression.

```java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public class ObjectNameDemo {
    public static void main(String[] args)
            throws MalformedObjectNameException {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        System.out.println(name.getDomain());                 // com.example.orders
        System.out.println(name.getKeyProperty("type"));      // Queue
        System.out.println(name.getKeyProperty("name"));      // Payment
        System.out.println(name.getCanonicalName());
    }
}
```

Nếu tên không hợp lệ, constructor có thể ném `MalformedObjectNameException`:

```java
new ObjectName("com.example.orders:type=Queue,name=Payment");
```

Việc constructor chạy thành công **chỉ chứng minh chuỗi hợp lệ theo cú pháp**. Nó chưa chứng minh:

- Tên đúng với chuẩn naming của dự án.
- Tên không trùng với MBean khác.
- Tên có ổn định qua lần khởi động sau.
- MBean đã thực sự được exporter đăng ký.
- Client có quyền truy cập MBean.

Vì vậy, cần các lớp test khác nhau thay vì dừng ở parse thành công.

### Tên có ký tự đặc biệt

Khi key property được sinh từ cấu hình hoặc tên nghiệp vụ, các ký tự như dấu phẩy, dấu hai chấm, dấu bằng, dấu sao, dấu hỏi có thể làm thay đổi cú pháp hoặc ý nghĩa pattern.

```java
String logicalName = "Billing,HighPriority";

ObjectName name = new ObjectName(
    "com.example.jobs:type=Queue,name="
        + ObjectName.quote(logicalName)
);
```

`ObjectName.quote` giúp đưa một giá trị chứa ký tự đặc biệt vào key property an toàn. Nếu cần tạo nhiều key, có thể dùng constructor nhận `Hashtable<String,String>` để tránh tự nối chuỗi theo cách dễ nhầm.

```java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Queue");
properties.put("name", "Payment");
ObjectName name = new ObjectName("com.example.orders", properties);
```

Đừng chỉ kiểm tra rằng tên không ném exception; hãy kiểm tra chính xác các key property kỳ vọng.

## 4. Canonical name và tính tương đương

Hai chuỗi sau có thứ tự key property khác nhau:

```text
com.example.orders:type=Queue,name=Payment
com.example.orders:name=Payment,type=Queue
```

Chúng biểu diễn cùng một ObjectName. JMX so sánh danh tính theo domain và key properties, không dựa vào thứ tự các key trong chuỗi.

```java
import javax.management.ObjectName;

ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=Payment,type=Queue"
);

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName().equals(
    second.getCanonicalName()));          // true
```

`getCanonicalName()` cung cấp biểu diễn chuẩn của ObjectName, hữu ích để lưu log, so sánh output từ nhiều code path và viết assertion dễ đọc.

**Lưu ý:** canonicalization không sửa danh tính sai. Nếu strategy sinh `name=Payment-<random-id>` mỗi lần chạy, canonical name vẫn thay đổi theo ID đó.

## 5. Naming strategy của Spring được kiểm thử ở đâu?

Spring cung cấp giao diện `org.springframework.jmx.export.naming.ObjectNamingStrategy`. Nó xác định `ObjectName` cho một managed bean.

Một số triển khai có sẵn gồm:

- `MetadataNamingStrategy`: dựa vào metadata từ `JmxAttributeSource`, thường phục vụ annotation-driven JMX.
- `KeyNamingStrategy`: dùng key cấu hình và cách ánh xạ tên.
- `IdentityNamingStrategy`: xây tên dựa trên danh tính object/class theo chiến lược của nó; cần cân nhắc tính ổn định khi dùng trong hệ thống quản trị.
- Naming strategy tùy chỉnh của ứng dụng.

Trong Spring export pipeline:

```text
MBeanExporter
  |-- beans / autodetection
  |-- ObjectNamingStrategy --> ObjectName
  |-- MBeanInfoAssembler --> management metadata
  v
MBeanServer.registerMBean(...)
```

Naming strategy quyết định **tên**, trong khi assembler quyết định **giao diện quản trị**. Một MBean có tên đúng vẫn có thể thiếu attributes/operations nếu assembler không cấu hình đúng; ngược lại, metadata đầy đủ vẫn không cứu được tên trùng.

Các test nên tách hai trách nhiệm này rồi kiểm tra việc kết hợp trong integration test.

## 6. Unit test cho hàm tạo ObjectName thuần Java

Một cách đơn giản và kiểm soát tốt là tạo factory tập trung:

```java
package com.example.jmx;

import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName queue(String name)
            throws MalformedObjectNameException {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                "Queue name must not be blank"
            );
        }

        Hashtable<String, String> props = new Hashtable<>();
        props.put("type", "Queue");
        props.put("name", name);

        return new ObjectName("com.example.orders", props);
    }
}
```

Unit test với JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class JmxNamesTest {
    @Test
    void createsExpectedQueueName() throws Exception {
        ObjectName actual = JmxNames.queue("Payment");
        ObjectName expected = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        assertEquals(expected, actual);
        assertEquals("com.example.orders", actual.getDomain());
        assertEquals("Queue", actual.getKeyProperty("type"));
        assertEquals("Payment", actual.getKeyProperty("name"));
        assertFalse(actual.isPattern());
    }

    @Test
    void rejectsBlankResourceName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> JmxNames.queue("  ")
        );
    }

    @Test
    void distinctResourcesHaveDistinctNames() throws Exception {
        assertNotEquals(
            JmxNames.queue("Payment"),
            JmxNames.queue("Refund")
        );
    }
}
```

Những assertion này kiểm tra hợp đồng về tên thay vì so sánh string tùy ý. `assertFalse(isPattern())` đặc biệt hữu ích khi tên sẽ được dùng để đăng ký MBean cụ thể: pattern ObjectName dành cho truy vấn, không phải một tên object cụ thể được đăng ký.

Nếu có yêu cầu key property khác, thêm assertion xác minh cả tập key thay vì chỉ kiểm tra một giá trị.

## 7. Viết một ObjectNamingStrategy tùy chỉnh

Trong ứng dụng Spring có thể triển khai `ObjectNamingStrategy` để sinh tên từ thông tin cấu hình ổn định.

```java
package com.example.jmx;

import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class FixedQueueNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {

        if ("paymentQueue".equals(beanKey)) {
            return JmxNames.queue("Payment");
        }

        if ("refundQueue".equals(beanKey)) {
            return JmxNames.queue("Refund");
        }

        throw new IllegalArgumentException(
            "Unsupported bean key: " + beanKey
        );
    }
}
```

Ở đây, `beanKey` là khóa được exporter truyền cho strategy theo cách cấu hình; nó không nhất thiết là ObjectName cuối cùng. Strategy chuyển một key logic thành tên JMX cụ thể.

Unit test cho strategy:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class FixedQueueNamingStrategyTest {
    private final FixedQueueNamingStrategy strategy =
            new FixedQueueNamingStrategy();

    @Test
    void paymentNameIsStable() throws Exception {
        Object first = new Object();
        Object second = new Object();

        ObjectName name1 =
                strategy.getObjectName(first, "paymentQueue");
        ObjectName name2 =
                strategy.getObjectName(second, "paymentQueue");

        assertEquals(name1, name2);
        assertEquals(
            new ObjectName("com.example.orders:type=Queue,name=Payment"),
            name1
        );
    }

    @Test
    void differentBeanKeysHaveDifferentNames() throws Exception {
        ObjectName payment =
                strategy.getObjectName(new Object(), "paymentQueue");
        ObjectName refund =
                strategy.getObjectName(new Object(), "refundQueue");

        assertNotEquals(payment, refund);
    }
}
```

Đây là test về **định danh logic ổn định**, không phụ thuộc identity hash code hoặc việc hai object Java có khác nhau hay không.

Nếu naming strategy của bạn phải xử lý nhiều tenant/instance, hãy mở rộng test với các tổ hợp tài nguyên thật sự cần phân biệt trong cùng `MBeanServer`.

## 8. Dùng MBeanServer để kiểm tra đăng ký thực tế

Một ObjectName đúng về mặt cú pháp chưa chứng minh resource được đăng ký. `MBeanServer` cung cấp các API như:

- `registerMBean(object, objectName)`
- `isRegistered(objectName)`
- `getMBeanInfo(objectName)`
- `getAttribute(objectName, attributeName)`
- `queryNames(pattern, queryExp)`
- `unregisterMBean(objectName)`

Ví dụ Standard MBean cho test:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
}
```

```java
public final class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 7;
    }
}
```

Đăng ký và xác minh:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = JmxNames.queue("Payment");

server.registerMBean(new QueueMonitor(), name);

try {
    if (!server.isRegistered(name)) {
        throw new IllegalStateException("MBean is not registered");
    }

    Object pending = server.getAttribute(name, "PendingCount");
    System.out.println("Pending jobs: " + pending);
} finally {
    if (server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
```

Đối với ví dụ sử dụng platform server, cần chú ý tên có thể đã được đăng ký bởi ứng dụng hoặc test khác. Trong hệ thống test chạy song song, tốt hơn là dùng MBeanServer riêng hoặc namespace xác định không trùng.

## 9. Tạo MBeanServer riêng để kiểm thử cách ly

Trong unit/integration test, **MBeanServer riêng** giúp tránh tác động đến các MBean sẵn có của JVM và không làm bẩn global platform MBeanServer:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated = MBeanServerFactory.createMBeanServer(
    "test.management"
);
```

Có thể viết test:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.*;
import org.junit.jupiter.api.Test;

class MBeanRegistrationTest {
    @Test
    void registersAndUnregistersExpectedName() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = JmxNames.queue("Payment");
        try {
            assertFalse(server.isRegistered(name));
            server.registerMBean(new QueueMonitor(), name);

            assertTrue(server.isRegistered(name));
            assertEquals(
                7,
                server.getAttribute(name, "PendingCount")
            );

            MBeanInfo info = server.getMBeanInfo(name);
            assertNotNull(info);
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

`releaseMBeanServer` phù hợp khi server được tạo bởi `createMBeanServer`. Nếu sử dụng `newMBeanServer`, server đó không nằm trong danh sách do factory quản lý và không cần release theo cách này.

Cách cách ly này hữu ích khi nhiều test cùng kiểm tra tên cố định. Tuy nhiên, mỗi test phải dùng đúng server instance của mình; tạo server khác không chứng minh exporter production thực sự đăng ký vào platform server.

## 10. Test trùng ObjectName

Một lỗi thường gặp là hai bean có cùng naming strategy result. `MBeanServer` không cho phép đăng ký hai MBean đồng thời dưới cùng `ObjectName`.

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.*;

@Test
void duplicateNameIsRejected() throws Exception {
    MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");
    ObjectName name = JmxNames.queue("Payment");

    try {
        server.registerMBean(new QueueMonitor(), name);

        assertThrows(
            InstanceAlreadyExistsException.class,
            () -> server.registerMBean(new QueueMonitor(), name)
        );
    } finally {
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
        MBeanServerFactory.releaseMBeanServer(server);
    }
}
```

Cách sửa không phải tự động nối `UUID.randomUUID()` vào tên, nếu hai bean đại diện cho **hai tài nguyên logic khác nhau**. Hãy thêm key phân biệt có ý nghĩa, ví dụ:

```text
com.example.orders:type=Queue,name=Payment
com.example.orders:type=Queue,name=Refund
```

Nếu hai exporter cùng đăng ký **cùng một tài nguyên**, hãy xác định một chủ sở hữu registration thay vì đổi tên một cách ngẫu nhiên.

## 11. Kiểm thử Spring MBeanExporter với naming strategy

Integration test nên bao phủ phần exporter sử dụng strategy và đăng ký vào server cụ thể.

Ví dụ cấu hình Spring:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxTestConfig {
    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.management");
    }

    @Bean
    public QueueMonitor paymentQueue() {
        return new QueueMonitor();
    }

    @Bean
    public FixedQueueNamingStrategy queueNamingStrategy() {
        return new FixedQueueNamingStrategy();
    }

    @Bean
    public MBeanExporter exporter(
            MBeanServer testMBeanServer,
            QueueMonitor paymentQueue,
            FixedQueueNamingStrategy queueNamingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setNamingStrategy(queueNamingStrategy);

        // Khóa map dùng làm beanKey cho naming strategy tùy chỉnh.
        exporter.setBeans(java.util.Map.of(
            "paymentQueue", paymentQueue
        ));
        return exporter;
    }
}
```

Trong ví dụ này, `QueueMonitor` là Standard MBean hợp lệ, còn naming strategy ánh xạ `paymentQueue` thành `com.example.orders:type=Queue,name=Payment`.

Test Spring context:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SpringNamingIntegrationTest {
    @Test
    void exporterRegistersUnderExpectedName() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxTestConfig.class)) {

            MBeanServer server =
                    context.getBean("testMBeanServer", MBeanServer.class);

            ObjectName expected = new ObjectName(
                "com.example.orders:type=Queue,name=Payment"
            );

            assertTrue(server.isRegistered(expected));
            assertEquals(
                7,
                server.getAttribute(expected, "PendingCount")
            );
        }
    }
}
```

Test xác nhận kết quả kết nối toàn bộ hệ thống Spring: bean, strategy, exporter và MBeanServer. Test metadata thêm bằng `getMBeanInfo` khi muốn kiểm tra management interface thực tế.

**Lưu ý về cấu hình:** trong các cách export khác nhau, việc key map đã là một `ObjectName` hợp lệ hoặc là bean key logic có thể tác động cách exporter/naming strategy xử lý. Integration test cần dùng đúng cấu hình sẽ chạy trong production, thay vì chỉ test factory `ObjectName` độc lập.

## 12. Kiểm tra tên qua vòng đời Spring context

Naming strategy phải tạo lại cùng tên cho cùng một resource sau khi context restart, trừ khi danh tính logic đã thay đổi.

Một integration test có thể:

1. Tạo context đầu.
2. Lấy tên MBean và xác minh đăng ký.
3. Đóng context đầu để exporter unregister MBean.
4. Tạo context thứ hai với cùng cấu hình.
5. Kiểm tra tên đăng ký giống với tên trước đó.

Ví dụ khái niệm:

```java
ObjectName expected = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

try (var first = new AnnotationConfigApplicationContext(
        JmxTestConfig.class)) {
    MBeanServer server = first.getBean(MBeanServer.class);
    assertTrue(server.isRegistered(expected));
}

try (var second = new AnnotationConfigApplicationContext(
        JmxTestConfig.class)) {
    MBeanServer server = second.getBean(MBeanServer.class);
    assertTrue(server.isRegistered(expected));
}
```

Ví dụ này dùng một MBeanServer mới mỗi context, nên chứng minh rằng naming strategy tạo ra cùng **ObjectName** qua hai lần khởi tạo. Nếu mục tiêu là kiểm tra cleanup trên **cùng MBeanServer**, hãy tạo một server được chia sẻ giữa hai context trong test và xác minh MBean không còn đăng ký sau khi context thứ nhất đóng. Hai loại kiểm thử bổ trợ nhau.

Đừng đưa PID, thời gian start, identity hash hay tên thread ngẫu nhiên vào ObjectName của một resource logic ổn định.

## 13. Query ObjectName bằng pattern

JMX hỗ trợ query theo `ObjectName` pattern để khám phá danh sách MBean:

```java
ObjectName pattern = new ObjectName(
    "com.example.orders:type=Queue,*"
);

for (ObjectName item : server.queryNames(pattern, null)) {
    System.out.println(item.getCanonicalName());
}
```

Điều này phù hợp để tìm toàn bộ queue trong một domain. Nhưng các pattern không phải là tên để đăng ký MBean cụ thể:

```java
ObjectName queryPattern = new ObjectName("com.example.orders:*");
System.out.println(queryPattern.isPattern()); // true
```

Trong test cho naming strategy, hãy kiểm tra `isPattern() == false` nếu strategy dự kiến tạo ra tên đăng ký cụ thể. Pattern là công cụ tìm kiếm, không phải định danh của một đối tượng quản trị duy nhất.

Không dùng kết quả query đầu tiên như một resource chắc chắn đúng nếu query trả nhiều tên; lọc theo key property, target JVM hoặc ObjectName exact trước khi gọi operation có side effect.

## 14. Phân biệt tên trong một JVM và nhiều JVM

Hai JVM có thể đăng ký cùng ObjectName:

```text
JVM A: com.example.orders:type=Queue,name=Payment
JVM B: com.example.orders:type=Queue,name=Payment
```

Điều này hợp lệ vì mỗi MBeanServer có namespace riêng. Nếu một hệ thống quan sát tập trung kết nối nhiều JVM, danh tính toàn hệ thống cần kết hợp endpoint/instance và ObjectName.

Vì vậy:

- Unit test `ObjectName`: xác minh tên local.
- Test `MBeanServer`: xác minh uniqueness trong server.
- Integration test exporter: xác minh Spring đăng ký đúng server.
- End-to-end monitoring: xác minh collector chọn đúng JVM/target và diễn giải tên đúng trong môi trường nhiều replica.

Một chuỗi ObjectName giống nhau không có nghĩa hai JVM sử dụng cùng MBean instance hay cùng dữ liệu.

## 15. Những lỗi phổ biến và cách chẩn đoán

| Lỗi/triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| `MalformedObjectNameException` | Domain/key/value không đúng cú pháp, ký tự đặc biệt chưa quote | Tạo `new ObjectName(...)` trong unit test |
| `InstanceAlreadyExistsException` | Hai bean cùng tên trong cùng MBeanServer | Kiểm tra `isRegistered`, danh sách exporter và naming strategy |
| `InstanceNotFoundException` | Client dùng sai ObjectName hoặc MBean chưa đăng ký/đã hủy | In canonical names và kiểm tra server đích |
| MBean không thấy trong JConsole/JMC | Exporter đăng ký ở MBeanServer khác, hoặc đang kết nối JVM khác | So sánh target/server và `queryNames` |
| Tên thay đổi sau restart | Strategy dùng PID, UUID mới, object identity hoặc thứ tự runtime | So sánh canonical name giữa hai lần khởi tạo |
| Test pass khi chạy một mình, fail khi chạy song song | Dùng platform MBeanServer chung và trùng ObjectName | Dùng server riêng hoặc namespace có owner rõ |
| Tên đúng nhưng thiếu attribute/operation | Assembler/interface không đúng, không phải lỗi naming | Đọc `getMBeanInfo`, xác minh management contract |
| Query match quá nhiều MBean | Pattern rộng | Thêm key property và dùng exact name khi thao tác |

Phân tách lỗi theo lớp giúp tìm nguyên nhân nhanh: cú pháp tên, ánh xạ strategy, đăng ký JMX, rồi metadata và invocation.

## 16. Hướng kiểm thử bằng bảng trường hợp

Một bộ test naming strategy nên bao phủ những trường hợp tiêu biểu:

| Trường hợp | Input | Kết quả mong đợi |
| --- | --- | --- |
| Tài nguyên cơ bản | Queue `Payment` | Domain/type/name đúng |
| Tên khác | Queue `Refund` | ObjectName khác |
| Thứ tự key khác | Cùng tập key–value | `equals == true` |
| Tên rỗng | `""`, khoảng trắng | Reject theo chính sách |
| Ký tự đặc biệt | `Billing,High` | Tạo ObjectName hợp lệ và value không bị tách |
| Tên chứa wildcard | `Billing*Core` | Được quote hoặc reject, không phải pattern ngoài ý muốn |
| Restart | Hai object runtime khác nhau cùng logical ID | ObjectName giống nhau |
| Trùng đăng ký | Hai bean trùng tên trong một server | `InstanceAlreadyExistsException` |
| Đóng context | MBean thuộc exporter kết thúc | Được unregister khi context đóng bình thường |
| Nhiều server | Cùng tên ở hai server riêng | Không xung đột giữa các server |

Không nhất thiết test mọi ký tự Unicode, nhưng cần bao phủ các ký tự mà dự án thực sự cho phép trong tên logic và những ký tự đặc biệt theo cú pháp JMX.

## 17. Bài tập thực hành

1. Viết một `ObjectNamingStrategy` tạo tên `com.example.inventory:type=Cache,name=<logicalName>` và kiểm thử với `ProductCatalog`, `ExchangeRates`.
2. Kiểm tra `ObjectName.equals()` khi hoán đổi thứ tự key property.
3. Tạo hai MBean có cùng ObjectName trong một MBeanServer test và giải thích `InstanceAlreadyExistsException`.
4. Dùng `MBeanServerFactory.newMBeanServer()` để kiểm tra naming không ảnh hưởng platform MBeanServer.
5. Viết Spring integration test khởi tạo `MBeanExporter` với naming strategy tùy chỉnh, xác minh `isRegistered` và `getAttribute`.
6. Khởi tạo context hai lần liên tiếp với cùng cấu hình, xác nhận tên ổn định.
7. Thêm kiểm tra `isPattern()` cho tên sinh từ input chưa được kiểm soát.
8. Sử dụng JConsole/JMC để quan sát domain và key properties sau khi test đăng ký thành công.

## 18. Câu hỏi tự kiểm tra

- Vì sao `new ObjectName(text)` thành công vẫn chưa đủ để kết luận naming strategy đúng?
- Hai chuỗi ObjectName có thứ tự key khác nhau có thể bằng nhau không?
- `MBeanServer.isRegistered` và `getMBeanInfo` xác nhận những điều khác nhau nào?
- Vì sao nên dùng MBeanServer riêng trong test chạy song song?
- Khi nào nên kiểm tra `ObjectName.isPattern()`?
- Làm sao phát hiện tên không ổn định sau restart?
- `ObjectName` có duy nhất giữa hai JVM không?
- Nếu tên đúng nhưng không có operation mong đợi, nên kiểm tra naming strategy hay MBeanInfoAssembler?

**Ghi nhớ:** Kiểm thử naming trong Spring JMX cần nhiều lớp: xác minh `ObjectName` hợp lệ và đúng semantics, xác minh `MBeanServer` đăng ký đúng và không trùng, rồi xác minh `MBeanExporter` dùng naming strategy như mong đợi trong ApplicationContext. Dùng canonical name, `isPattern`, `isRegistered` và `MBeanInfo` để bảo đảm tên vừa ổn định vừa có ích cho các client quản trị.