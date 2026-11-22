# Kiểm tra ObjectName đã đăng ký trong Spring Framework JMX

## Mục tiêu bài học

Trong Spring Framework JMX, việc khai báo `@ManagedResource`, cấu hình `MBeanExporter` hoặc tạo một `ObjectName` hợp lệ **không tự chứng minh** rằng MBean đã được đăng ký thành công. Muốn xác nhận chính xác một tài nguyên quản trị xuất hiện trong hệ thống JMX, cần kiểm tra **đúng MBeanServer** và **đúng ObjectName** tại runtime.

Bài học thuộc **Spring Framework JMX → Kiểm thử**. Sau khi hoàn thành, bạn có thể:

- Phân biệt ObjectName hợp lệ với ObjectName đã được đăng ký.
- Dùng `MBeanServer.isRegistered(ObjectName)` và `MBeanServerConnection.isRegistered(ObjectName)`.
- Dùng `queryNames`, `getMBeanInfo` và các key properties để xác định đúng tài nguyên.
- Viết unit test cho quy tắc đặt tên và integration test cho `MBeanExporter`.
- Kiểm thử lifecycle: đăng ký khi Spring context khởi động, hủy đăng ký khi context đóng.
- Phát hiện lỗi trùng tên, sai domain, sai MBeanServer, sai JMX endpoint hoặc thay đổi tên ngoài ý muốn.
- Tránh các test không ổn định do dùng platform MBeanServer chung hay chạy song song.

## 1. ObjectName là tên, không phải bằng chứng đăng ký

Một MBean trong JMX được định danh bằng `javax.management.ObjectName`:

```text
domain:key1=value1,key2=value2
```

Ví dụ:

```text
com.example.orders:type=Queue,name=Payment
```

Có thể tạo ObjectName:

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

Nếu constructor thành công, tên hợp lệ về cú pháp. Nhưng nó có thể chưa được đăng ký vào bất kỳ `MBeanServer` nào.

```text
ObjectName hợp lệ
      |
      |  chưa đủ!
      v
MBeanServer cụ thể
      |
      +-- isRegistered(name) == true
      |       -> MBean tồn tại ở thời điểm kiểm tra
      |
      +-- isRegistered(name) == false
              -> không có MBean mang tên đó trong server này
```

Để tránh nhầm lẫn, hãy tách ba điều:

1. **Syntax:** ObjectName có hợp lệ không?
2. **Registration:** MBean có tồn tại dưới tên này trong server đích không?
3. **Contract:** MBean đã đăng ký có attributes/operations đúng kỳ vọng không?

`isRegistered` trả lời điều thứ hai. Nếu cần điều thứ ba, đọc thêm `MBeanInfo`.

## 2. Kiểm tra với MBeanServer.isRegistered

`MBeanServer` có phương thức:

```java
boolean isRegistered(ObjectName name);
```

Ví dụ kiểm tra platform MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxRegistrationCheck {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        boolean registered = server.isRegistered(name);
        System.out.println("Registered: " + registered);
    }
}
```

Lời gọi này xác minh **server object hiện đang sử dụng** có chứa ObjectName đó không.

**Lưu ý:** nếu Spring `MBeanExporter` đăng ký vào MBeanServer tùy biến, dùng `ManagementFactory.getPlatformMBeanServer()` có thể trả `false` dù MBean đã được đăng ký thành công ở server khác. Không kết luận rằng exporter lỗi trước khi kiểm tra `setServer` hoặc server bean mà exporter được inject.

## 3. ObjectName.equals và canonical name

Hai chuỗi có thứ tự key khác nhau vẫn biểu diễn cùng ObjectName:

```text
com.example.orders:type=Queue,name=Payment
com.example.orders:name=Payment,type=Queue
```

JMX coi chúng là cùng danh tính:

```java
ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=Payment,type=Queue"
);

assert first.equals(second);
assert first.getCanonicalName()
            .equals(second.getCanonicalName());
```

Do đó, test nên dùng:

```java
assertEquals(expectedObjectName, actualObjectName);
```

thay vì so sánh raw strings có thể khác thứ tự key.

`getCanonicalName()` hữu ích khi ghi log, xây test failure message và đối chiếu output giữa công cụ quản trị khác nhau.

**Điều cần hiểu:** canonical name chỉ chuẩn hóa cách biểu diễn danh tính JMX, không chứng minh tên đã tồn tại hoặc thuộc đúng server.

## 4. Kiểm tra tên cụ thể hay pattern?

ObjectName dùng cho đăng ký thường là một tên **concrete**:

```java
ObjectName exact = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

Khi cần tìm nhóm MBean, có thể dùng pattern:

```java
ObjectName pattern = new ObjectName(
    "com.example.orders:type=Queue,*"
);
```

Kiểm tra:

```java
assertFalse(exact.isPattern());
assertTrue(pattern.isPattern());
```

Đối với một tên cụ thể, dùng `isRegistered(exact)`. Đối với pattern, sử dụng `queryNames(pattern, null)` để lấy các ObjectName phù hợp.

Không dùng pattern rồi giả định kết quả đầu tiên chính là resource cần thao tác. Nếu test cần MBean chính xác, hãy kiểm tra **exact ObjectName**.

## 5. Tạo Standard MBean để kiểm thử

Ví dụ một MBean quan sát queue:

```java
package com.example.orders.jmx;

public interface PaymentQueueMonitorMBean {
    int getPendingCount();
}
```

Implementation:

```java
package com.example.orders.jmx;

public final class PaymentQueueMonitor
        implements PaymentQueueMonitorMBean {

    private final int pendingCount;

    public PaymentQueueMonitor(int pendingCount) {
        this.pendingCount = pendingCount;
    }

    @Override
    public int getPendingCount() {
        return pendingCount;
    }
}
```

Class có interface tên `PaymentQueueMonitorMBean`, phù hợp Standard MBean convention.

Một MBean được đăng ký dưới tên:

```text
com.example.orders:type=Queue,name=Payment
```

sẽ công bố attribute `PendingCount`. Nhưng trước khi đọc attribute, test cần xác nhận tên đã đăng ký trong server đích.

## 6. Unit/integration test thuần JMX

Để không chạm platform MBeanServer đang dùng bởi JVM và các test khác, tạo server riêng:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.management");
```

JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ObjectNameRegistrationTest {

    @Test
    void registersExpectedObjectName() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        try {
            assertFalse(server.isRegistered(name));

            server.registerMBean(
                new PaymentQueueMonitor(12),
                name
            );

            assertTrue(server.isRegistered(name));

            assertEquals(
                12,
                server.getAttribute(name, "PendingCount")
            );
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Test xác minh đầy đủ ba trạng thái:

1. Trước đăng ký: MBean không có trong server.
2. Sau đăng ký: MBean hiện diện với đúng ObjectName.
3. Sau unregister: server không còn registration đó.

Khi dùng `createMBeanServer`, có thể `releaseMBeanServer` để đưa server ra khỏi danh sách do factory quản lý. Với `newMBeanServer`, server không được factory đăng ký trong danh sách đó và không dùng `releaseMBeanServer` theo cách tương tự.

## 7. Xem MBeanInfo sau khi xác nhận đăng ký

`isRegistered` chỉ cho biết tên tồn tại, không chứng minh đó là MBean có contract mong đợi.

Sau khi xác nhận:

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);
System.out.println(info.getClassName());

for (var attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() + " : " + attribute.getType()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

Một test tốt có thể xác nhận:

- Attribute `PendingCount` tồn tại.
- Kiểu attribute là `int`.
- Attribute có thể đọc.
- Operation nhạy cảm không xuất hiện nếu management interface không cho phép.
- Class hoặc metadata MBean phù hợp kỳ vọng.

Với Model MBean do Spring export từ arbitrary bean, `info.getClassName()` có thể thể hiện lớp ModelMBean/metadata liên quan, không nhất thiết chính xác class nghiệp vụ. Vì vậy, kiểm tra attribute/operation thường hữu ích hơn việc chỉ so sánh tên class.

## 8. Cấu hình Spring MBeanExporter

`MBeanExporter` có thể đăng ký bean vào MBeanServer khi Spring context khởi tạo:

```java
package com.example.orders.config;

import com.example.orders.jmx.PaymentQueueMonitor;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportTestConfiguration {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.management");
    }

    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor(12);
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer testMBeanServer,
            PaymentQueueMonitor paymentQueueMonitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Payment",
            paymentQueueMonitor
        ));
        return exporter;
    }
}
```

Ở đây:

- `testMBeanServer` là một server riêng.
- `paymentQueueMonitor` là Standard MBean implementation.
- `mbeanExporter` đăng ký bean dưới ObjectName xác định.
- Exporter quản lý vòng đời đăng ký theo Spring context.

**Chú ý:** không tự đăng ký cùng bean vào server trước khi exporter khởi tạo nếu muốn test exporter tự thực hiện registration. Làm vậy gây xung đột ObjectName và che mất mục tiêu test.

## 9. Spring integration test kiểm tra ObjectName

JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SpringJmxRegistrationTest {

    @Test
    void exportsBeanWithExpectedObjectName() throws Exception {
        ObjectName expected = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        MBeanServer server;

        try (var context =
                 new AnnotationConfigApplicationContext(
                     JmxExportTestConfiguration.class)) {

            server = context.getBean(
                "testMBeanServer", MBeanServer.class
            );

            assertTrue(
                server.isRegistered(expected),
                "Missing JMX MBean: " + expected.getCanonicalName()
            );

            assertEquals(
                12,
                server.getAttribute(expected, "PendingCount")
            );
        }

        assertFalse(
            server.isRegistered(expected),
            "MBean should be unregistered after context close"
        );
    }
}
```

Đây là cách kiểm tra **Spring wiring + JMX registration** trong một test.

Nếu test dùng `@EnableMBeanExport` và annotation thay vì manual `MBeanExporter`, hãy đảm bảo exporter do annotation tạo ra thực sự dùng server test; không tự cho rằng tất cả exporters đều chọn cùng MBeanServer chỉ vì context có bean cùng kiểu.

## 10. Kiểm tra ObjectName khi dùng @ManagedResource

Cách export dựa trên annotation:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Payment queue management interface"
)
public class AnnotatedQueueAdmin {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

Nếu bật:

```java
@Configuration
@EnableMBeanExport
public class AnnotationJmxConfig {
}
```

thì Spring có thể nhận diện resource và đăng ký vào MBeanServer được cấu hình.

Test cần xác nhận:

```java
assertTrue(server.isRegistered(new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
)));
```

Không dừng ở:

```java
assertNotNull(AnnotatedQueueAdmin.class
    .getAnnotation(ManagedResource.class));
```

Annotation tồn tại trên class chỉ là metadata trong source, không chứng minh exporter đã khởi tạo, scan được bean, đăng ký đúng tên hoặc dùng đúng server.

## 11. queryNames cho kiểm thử nhóm MBean

`MBeanServer.queryNames(ObjectName, QueryExp)` cho phép tìm các MBean hiện có theo pattern:

```java
ObjectName pattern = new ObjectName(
    "com.example.orders:type=Queue,*"
);

var names = server.queryNames(pattern, null);

for (ObjectName item : names) {
    System.out.println(item.getCanonicalName());
}
```

Test có thể xác minh đủ hai resource:

```java
ObjectName payment = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName refunds = new ObjectName(
    "com.example.orders:type=Queue,name=Refund"
);

var names = server.queryNames(
    new ObjectName("com.example.orders:type=Queue,*"),
    null
);

assertTrue(names.contains(payment));
assertTrue(names.contains(refunds));
```

Khi muốn khẳng định **không có resource thừa**, có thể kiểm tra tập tên chính xác trong một **MBeanServer test cách ly**. Trên platform server, các thư viện hoặc test khác có thể đăng ký MBean hợp lệ cùng domain, khiến assertion về số lượng tuyệt đối trở nên mong manh.

## 12. Sai MBeanServer là nguyên nhân thường gặp

Một JVM có thể chứa nhiều MBeanServer:

```text
JVM
  |
  +-- Platform MBeanServer
  |     +-- java.lang:type=Memory
  |
  +-- Custom MBeanServer
        +-- com.example.orders:type=Queue,name=Payment
```

Nếu exporter sử dụng custom server:

```java
exporter.setServer(customServer);
```

nhưng test dùng:

```java
ManagementFactory.getPlatformMBeanServer()
    .isRegistered(name);
```

thì có thể trả `false` dù exporter hoàn toàn hoạt động đúng.

Để tránh sai:

1. Inject hoặc lấy đúng `MBeanServer` bean mà exporter dùng.
2. Kiểm tra `setServer` trong configuration.
3. Ghi ObjectName và server identity trong diagnostic test.
4. Khi dùng remote connector, phải xác minh connector phục vụ đúng server.

Không thay ObjectName bừa bãi chỉ vì `isRegistered` trả false trên sai server.

## 13. Kiểm tra ObjectName ở server từ xa

`MBeanServerConnection` cũng có `isRegistered`, nên có thể kiểm tra từ client:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "com.example.orders:type=Queue,name=Payment"
    );

    boolean registered = connection.isRegistered(name);
    System.out.println("Remote registered: " + registered);
}
```

Một ObjectName có thể được đăng ký ở nhiều JVM khác nhau. Do đó, kiểm tra remote cần định danh cả **endpoint/instance** lẫn ObjectName.

Nếu remote `isRegistered(name)` trả `false`, có thể endpoint sai, MBean chưa được export, hoặc exporter đang dùng server khác server mà connector phục vụ.

## 14. Kiểm tra lỗi trùng ObjectName

Trong cùng MBeanServer, hai MBean không thể được đăng ký đồng thời với cùng ObjectName.

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.InstanceAlreadyExistsException;

server.registerMBean(
    new PaymentQueueMonitor(12), name
);

assertThrows(
    InstanceAlreadyExistsException.class,
    () -> server.registerMBean(
        new PaymentQueueMonitor(99), name
    )
);
```

Nếu dùng `MBeanExporter`, chính sách `RegistrationPolicy` quyết định cách Spring phản ứng khi tên đã tồn tại:

- `FAIL_ON_EXISTING`: báo lỗi.
- `IGNORE_EXISTING`: bỏ qua registration mới.
- `REPLACE_EXISTING`: thay thế theo chính sách Spring.

Test cần đặt đúng expectation tùy policy đang cấu hình. Với fail-on-existing, không được giả định Spring tự đổi tên để tránh trùng.

Một ObjectName được đăng ký không chứng minh **đúng bean** nếu policy ignore cho phép giữ MBean cũ. Đọc thêm attribute/metadata hoặc sử dụng các property nhận diện instance khi cần.

## 15. Kiểm tra ObjectName qua vòng đời context

Một integration test quan trọng cần khẳng định MBean không còn đăng ký sau khi Spring context đóng.

```text
Before refresh:
  registered = false

After refresh:
  registered = true

After close:
  registered = false
```

Điều này phát hiện lỗi như:

- Exporter không cleanup MBean.
- Có exporter khác cùng sở hữu tên.
- Context cũ vẫn còn sống.
- Test reuse platform server mà không dọn dẹp.
- MBean được đăng ký thủ công nhưng không được quản lý lifecycle.

Nếu chỉ test `isRegistered == true` sau startup, chưa chắc phát hiện leak khi redeploy hoặc chạy nhiều test.

Lưu ý rằng một ApplicationContext có thể đóng bình thường nhưng MBean vẫn ở server nếu nó **được đăng ký bởi thành phần khác**. Không tự unregister tài nguyên không thuộc ownership của test.

## 16. Kiểm thử naming strategy

Spring hỗ trợ `ObjectNamingStrategy` để tạo tên cho bean.

Ví dụ naming convention:

```text
com.example.orders:type=Queue,name=Payment
com.example.orders:type=Queue,name=Refund
```

Một unit test naming strategy nên kiểm tra:

- Domain chính xác.
- Key properties `type`/`name`.
- Các bean khác nhau có tên khác nhau.
- Tên ổn định giữa những lần tạo lại object với cùng logical identity.
- Tên không phải pattern nếu dùng để đăng ký.
- Các ký tự đặc biệt được xử lý/quote đúng.

```java
ObjectName first = namingStrategy.getObjectName(
    paymentQueue, "paymentQueue"
);

assertEquals(
    new ObjectName("com.example.orders:type=Queue,name=Payment"),
    first
);
assertFalse(first.isPattern());
```

Sau unit test, cần một integration test Spring để bảo đảm exporter **thực sự dùng** naming strategy đó thay vì đường đặt tên khác.

## 17. Hỗ trợ chẩn đoán qua các thuộc tính JMX

Khi debug, có thể in các thông tin:

```java
System.out.println("Domain: " + name.getDomain());
System.out.println("Canonical: " + name.getCanonicalName());
System.out.println("Properties: " + name.getKeyPropertyList());
System.out.println("Registered: " + server.isRegistered(name));
```

Và nếu đã đăng ký:

```java
var info = server.getMBeanInfo(name);

System.out.println("MBean class: " + info.getClassName());
System.out.println("Attributes: " + info.getAttributes().length);
System.out.println("Operations: " + info.getOperations().length);
```

Đối với production, tránh ghi log dữ liệu nhạy cảm từ attribute values. ObjectName cũng có thể chứa thông tin định danh nội bộ; chỉ đưa các key thật sự cần cho chẩn đoán.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `isRegistered` trả false | Exporter chưa chạy, MBean sai tên hoặc khác server | Kiểm tra context, `setServer`, `ObjectName` |
| `MalformedObjectNameException` | Chuỗi tên không hợp lệ | Dùng `ObjectName` API, quote key property khi cần |
| `InstanceAlreadyExistsException` | Tên đã thuộc MBean khác trong cùng server | Kiểm tra owner, naming strategy, registration policy |
| `InstanceNotFoundException` | Tên không tồn tại khi đọc/invoke hoặc vừa bị unregister | Kiểm tra lifecycle và timing |
| MBean tồn tại nhưng thiếu operation | Metadata assembler/interface không đúng | Đọc `getMBeanInfo` |
| Test pass đơn lẻ nhưng fail song song | Chia sẻ platform MBeanServer với ObjectName cố định | Tạo MBeanServer riêng |
| MBean không bị unregister khi đóng context | Có registration khác hoặc lifecycle chưa cleanup | Kiểm tra owner và context teardown |
| Cùng ObjectName trên hai JVM | Hoàn toàn hợp lệ vì mỗi server có namespace riêng | Kết hợp endpoint + ObjectName để xác định target |

## 19. Bài tập thực hành

1. Tạo `PaymentQueueMonitorMBean` và đăng ký bằng `MBeanServer.registerMBean` vào server test. Xác minh trước/sau đăng ký với `isRegistered`.
2. Dùng `ObjectName` có key properties đảo thứ tự, chứng minh `equals` vẫn trả `true`.
3. Tạo cấu hình Spring `MBeanExporter` xuất bean dưới ObjectName cố định; viết integration test xác minh `isRegistered` sau `context.refresh()`.
4. Đọc `MBeanInfo` và assert attribute `PendingCount` có kiểu `int`.
5. Đóng context rồi assert MBean không còn trên server.
6. Đăng ký hai MBean trùng ObjectName trong server test để quan sát `InstanceAlreadyExistsException`.
7. Cố tình cho exporter dùng custom server nhưng test dùng platform server; giải thích false negative.
8. Query bằng `com.example.orders:type=Queue,*` và xác minh tập ObjectName của hai queue.
9. Viết test cho một annotation-driven MBean dùng `@ManagedResource` thay vì manual exporter.

## 20. Câu hỏi tự kiểm tra

- Vì sao `new ObjectName(...)` thành công vẫn chưa chứng minh MBean đã được đăng ký?
- `isRegistered` xác minh điều gì và còn thiếu điều gì?
- Khi nào nên dùng `queryNames` thay vì `isRegistered`?
- Vì sao tên canonical quan trọng khi thứ tự key property khác nhau?
- Tại sao cần kiểm tra đúng MBeanServer mà exporter dùng?
- Sau `isRegistered == true`, làm sao kiểm tra MBean có attribute mong đợi?
- Một ObjectName có thể cùng tồn tại trên hai JVM khác nhau không?
- Vì sao cleanup sau test giúp tránh `InstanceAlreadyExistsException` ở những lần chạy sau?

**Ghi nhớ:** ObjectName hợp lệ chỉ là **tên**. Để kiểm tra một MBean đã thực sự được Spring xuất, hãy gọi `isRegistered` trên **đúng MBeanServer**, dùng `queryNames` cho nhóm, `MBeanInfo` để xác minh contract và kiểm thử cả cleanup khi ApplicationContext đóng.