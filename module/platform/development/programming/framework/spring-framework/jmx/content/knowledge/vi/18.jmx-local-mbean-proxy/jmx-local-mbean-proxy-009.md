# Kiểm thử proxy MBean local bằng MBeanServer giả hoặc thật

## Mục tiêu

Bài học thuộc **Spring Framework JMX → Proxy MBean local**, tập trung vào cách kiểm thử client proxy do Spring tạo để truy cập một MBean trong cùng JVM. Sau bài này, bạn có thể:

- Hiểu `MBeanProxyFactoryBean` tạo proxy dựa trên management interface và `ObjectName`.
- Phân biệt mock `MBeanServerConnection` với `MBeanServer` thật khi kiểm thử.
- Viết test đọc attribute, gọi operation, kiểm tra chữ ký tham số và propagation của lỗi JMX.
- Tạo một MBeanServer cách ly, đăng ký Standard MBean, kiểm thử end-to-end và cleanup an toàn.
- Nhận biết các rủi ro khi dùng platform server, naming không ổn định, test chạy song song và giả định sai về lời gọi proxy.

## 1. Proxy MBean local là gì?

JMX hoạt động qua một `MBeanServer`. Một client có thể gọi trực tiếp các phương thức JMX:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

Object count = server.getAttribute(name, "PendingCount");

server.invoke(
    name, "resetStatistics",
    new Object[0], new String[0]
);
```

Spring cho phép sử dụng một **proxy kiểu Java interface** để code client không cần lặp lại lời gọi `getAttribute`, `setAttribute`, `invoke`.

```text
Spring client
  |
  v
QueueAdminMBean interface
  |
  v
MBeanProxyFactoryBean
  |
  v
MBeanServerConnection (local)
  |
  v
MBeanServer -> MBean đã đăng ký dưới ObjectName
```

Lập trình viên có thể gọi:

```java
QueueAdminMBean proxy = ...;
int count = proxy.getPendingCount();
proxy.resetStatistics();
```

Proxy chuyển lời gọi interface thành thao tác JMX tương ứng. Vì có thêm lớp ánh xạ interface → JMX metadata → MBean implementation, test chỉ gọi trực tiếp target class **không đủ** để xác nhận proxy hoạt động đúng.

## 2. Các thành phần cần xác minh

| Thành phần | Vai trò trong kiểm thử |
| --- | --- |
| `MBeanProxyFactoryBean` | Tạo proxy và giữ cấu hình `ObjectName`, management interface, connection |
| `MBeanServerConnection` | API client dùng để lấy thuộc tính và gọi operation |
| `MBeanServer` | Registry JMX thật; cũng triển khai `MBeanServerConnection` |
| `ObjectName` | Định danh MBean mà proxy phải truy cập |
| Management interface | Hợp đồng Java phía client |
| MBean implementation | Hành vi thực tế trả kết quả và xử lý operation |
| `MBeanInfo` | Metadata cho biết thuộc tính/operation được công bố |

Điểm then chốt: **local proxy vẫn đi qua JMX API**, dù không có network hop. Đó không phải một Spring AOP proxy gọi trực tiếp target trong mọi trường hợp.

## 3. Chuẩn bị management interface và Standard MBean

Để demo, định nghĩa một interface quản trị:

```java
package com.example.jmx;

public interface QueueAdminMBean {
    int getPendingCount();
    boolean isPaused();
    void setPaused(boolean paused);
    void resetStatistics();
}
```

Tạo implementation:

```java
package com.example.jmx;

public class QueueAdmin implements QueueAdminMBean {
    private int pendingCount = 17;
    private boolean paused;

    @Override
    public synchronized int getPendingCount() {
        return pendingCount;
    }

    @Override
    public synchronized boolean isPaused() {
        return paused;
    }

    @Override
    public synchronized void setPaused(boolean paused) {
        this.paused = paused;
    }

    @Override
    public synchronized void resetStatistics() {
        pendingCount = 0;
    }
}
```

`QueueAdmin` triển khai `QueueAdminMBean` nên có thể đăng ký theo quy ước Standard MBean của JMX. Phương thức `getPendingCount` và cặp `isPaused`/`setPaused` được biểu diễn dưới dạng attributes, còn `resetStatistics` là operation.

Ví dụ ObjectName:

```text
com.example.orders:type=Queue,name=Payment
```

Trong test, đừng coi class name và ObjectName là tương đương: **tên quản trị** do server đăng ký có thể khác hoàn toàn tên Spring bean hoặc tên class.

## 4. Tạo proxy bằng MBeanProxyFactoryBean

Một cấu hình Spring Java minh họa:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class QueueClientJmxConfiguration {

    @Bean
    public MBeanProxyFactoryBean queueProxyFactory(
            MBeanServer mbeanServer) throws Exception {

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(mbeanServer);
        factory.setObjectName(
            new ObjectName("com.example.orders:type=Queue,name=Payment")
        );
        factory.setProxyInterface(QueueAdminMBean.class);
        return factory;
    }
}
```

Các thuộc tính cần kiểm tra:

- `server`: đối tượng `MBeanServerConnection` mà proxy giao tiếp. Với local proxy có thể dùng `MBeanServer` thật.
- `objectName`: MBean cụ thể được gọi.
- `proxyInterface`: management interface mà ứng dụng sẽ nhìn thấy.
- Các cấu hình khác, nếu dùng, phải phù hợp Spring version và cơ chế khởi tạo factory.

Khi bean factory được Spring quản lý, vòng đời `FactoryBean` giúp cung cấp proxy theo interface được chỉ định. Nếu tạo thủ công trong unit test, cần gọi bước khởi tạo tương ứng trước khi lấy `getObject()`.

## 5. Chiến lược test: mock hay server thật?

Hai cấp kiểm thử bổ trợ nhau:

| Khía cạnh | Mock `MBeanServerConnection` | `MBeanServer` thật |
| --- | --- | --- |
| Chi phí | Nhẹ, không đăng ký MBean | Cần setup/teardown registry |
| Kiểm tra mapping lời gọi | Tốt, xác minh `getAttribute`/`invoke` | Tốt, dùng metadata JMX thực |
| Kiểm tra Standard MBean compliance | Không | Có |
| Kiểm tra `ObjectName` đăng ký thật | Không | Có |
| Kiểm tra lỗi từ connector/JMX API | Có thể mô phỏng | Có thể quan sát lỗi thật |
| Kiểm tra JavaBeans attribute mapping | Cần stub phù hợp | Tự nhiên hơn, đúng protocol |
| Nguy cơ ảnh hưởng test khác | Thấp | Thấp nếu tạo server riêng |
| Mức tin cậy integration | Giới hạn bởi hành vi stub | Cao hơn đối với đường JMX local |

**Khuyến nghị:** mock để test mapping và nhánh lỗi thật nhanh; dùng một số integration test với server thật để đảm bảo hợp đồng interface, metadata, định danh và lifecycle khớp nhau.

Không nên chỉ có unit test mock rồi kết luận rằng một MBean thật chắc chắn export được.

## 6. Unit test với mock MBeanServerConnection

Có thể mock API JMX client bằng Mockito. Ví dụ này giả định phiên bản Spring hỗ trợ `MBeanProxyFactoryBean.setServer(MBeanServerConnection)` và cơ chế khởi tạo bean thông thường.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

class QueueProxyMockTest {
    @Test
    void readsAttributeThroughConnection() throws Exception {
        MBeanServerConnection connection =
            mock(MBeanServerConnection.class);

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        when(connection.getAttribute(name, "PendingCount"))
            .thenReturn(42);

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(connection);
        factory.setObjectName(name);
        factory.setProxyInterface(QueueAdminMBean.class);
        factory.afterPropertiesSet();

        QueueAdminMBean proxy =
            (QueueAdminMBean) factory.getObject();

        assertEquals(42, proxy.getPendingCount());

        verify(connection).getAttribute(name, "PendingCount");
    }
}
```

Trong một số phiên bản hoặc cấu hình, factory có thể kiểm tra `MBeanInfo` hoặc tình trạng MBean khi khởi tạo. Nếu xảy ra, mock phải mô phỏng các lời gọi metadata đó bằng fixture nhất quán, hoặc nên dùng server thật để tránh tạo một mock thiếu ngữ nghĩa.

Test không gọi implementation `QueueAdmin`: nó chỉ xác minh cách proxy trao đổi với `MBeanServerConnection`.

### Kiểm tra gọi operation

```java
@Test
void invokesOperationThroughConnection() throws Exception {
    MBeanServerConnection connection =
        mock(MBeanServerConnection.class);
    ObjectName name = new ObjectName(
        "com.example.orders:type=Queue,name=Payment"
    );

    MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
    factory.setServer(connection);
    factory.setObjectName(name);
    factory.setProxyInterface(QueueAdminMBean.class);
    factory.afterPropertiesSet();

    QueueAdminMBean proxy =
        (QueueAdminMBean) factory.getObject();

    proxy.resetStatistics();

    verify(connection).invoke(
        eq(name),
        eq("resetStatistics"),
        aryEq(new Object[0]),
        aryEq(new String[0])
    );
}
```

Tùy cách factory thực hiện introspection và cách Mockito match các mảng, hãy xác minh signature thực mà client gửi. Với operation có tham số, JMX yêu cầu signature là mảng tên kiểu, ví dụ `"int"`, không phải `"java.lang.Integer"` nếu method dùng primitive.

## 7. Vì sao mock quá đơn giản có thể đánh lừa?

Mock chỉ trả đúng giá trị mà test cung cấp. Nó không tự thực thi các quy tắc của JMX:

- Không xác nhận target class là Standard MBean hợp lệ.
- Không tự kiểm tra tên attribute được công bố.
- Không biết `setPaused` là writable attribute nếu bạn chưa stub hành vi liên quan.
- Không chứng minh operation signature tương thích với MBean thật.
- Không bảo đảm target ObjectName đã đăng ký.
- Không mô phỏng chính xác exception wrapping nếu stubbing sai.

Ví dụ mock:

```java
when(connection.getAttribute(name, "PendingCount"))
    .thenReturn(42);
```

vẫn pass dù trong server thật attribute có tên `PendingJobs`. Nếu không có integration test, mismatch có thể chỉ xuất hiện khi triển khai.

Đối với các factory/client có metadata validation, mock cũng cần `getMBeanInfo` trả về `MBeanInfo` phù hợp với interface. Đừng tắt validation để làm test xanh nếu production có bật validation.

## 8. Integration test dùng MBeanServer thật và cách ly

JMX cung cấp factory tạo server để test:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.management");
```

Server tạo theo cách này không phải platform MBeanServer mặc định của JVM. Bạn có thể đăng ký MBean của test mà không ảnh hưởng MBean hệ thống.

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

class QueueProxyIntegrationTest {

    @Test
    void proxiesRealLocalMBean() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        try {
            QueueAdmin target = new QueueAdmin();
            server.registerMBean(target, name);

            MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
            factory.setServer(server);
            factory.setObjectName(name);
            factory.setProxyInterface(QueueAdminMBean.class);
            factory.afterPropertiesSet();

            QueueAdminMBean proxy =
                (QueueAdminMBean) factory.getObject();

            assertEquals(17, proxy.getPendingCount());
            assertFalse(proxy.isPaused());

            proxy.setPaused(true);
            assertTrue(proxy.isPaused());

            proxy.resetStatistics();
            assertEquals(0, proxy.getPendingCount());

        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Test này bao phủ đầy đủ:

1. Đăng ký MBean thật trong MBeanServer.
2. Tạo proxy theo interface JMX.
3. Đọc attribute `PendingCount`.
4. Đọc/ghi attribute `Paused`.
5. Gọi operation `resetStatistics`.
6. Xác minh state thực sự thay đổi.
7. Hủy đăng ký và giải phóng test server.

**Không nên dùng `ManagementFactory.getPlatformMBeanServer()` trong mọi test** nếu có thể tạo server riêng. Platform server được chia sẻ bởi nhiều framework/test trong cùng JVM, dễ gây xung đột và làm rò rỉ MBean khi cleanup thiếu.

## 9. Kiểm thử với Spring ApplicationContext

Ngoài kiểm thử factory trực tiếp, có thể khởi tạo context để xác minh wiring thực tế của exporter và proxy.

Ví dụ cấu hình:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.export.MBeanExporter;
import java.util.Map;

@Configuration
public class QueueJmxTestConfig {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.management");
    }

    @Bean
    public QueueAdmin queueAdmin() {
        return new QueueAdmin();
    }

    @Bean
    public MBeanExporter queueExporter(
            MBeanServer testMBeanServer, QueueAdmin queueAdmin) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Payment",
            queueAdmin
        ));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean queueClientFactory(
            MBeanServer testMBeanServer) throws Exception {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
        proxy.setServer(testMBeanServer);
        proxy.setObjectName(new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        ));
        proxy.setProxyInterface(QueueAdminMBean.class);
        return proxy;
    }
}
```

Test context:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class QueueJmxContextTest {

    @Test
    void clientProxyReadsBeanExportedBySpring() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueJmxTestConfig.class)) {

            QueueAdminMBean proxy =
                context.getBean(QueueAdminMBean.class);

            assertEquals(17, proxy.getPendingCount());

            MBeanServer server = context.getBean(MBeanServer.class);
            assertTrue(server.isRegistered(
                new ObjectName(
                    "com.example.orders:type=Queue,name=Payment"
                )
            ));
        }
    }
}
```

Trong code thật, method test cần khai báo `throws Exception` hoặc xử lý checked exception khi tạo `ObjectName`. Ngoài ra, thứ tự khởi tạo proxy và exporter có thể ảnh hưởng đến việc kiểm tra metadata lúc startup: nếu factory kiểm tra MBean tại khởi tạo, cần thiết lập phụ thuộc khởi tạo để exporter hoàn tất đăng ký trước.

Ví dụ thêm `@DependsOn("queueExporter")` cho bean `queueClientFactory`, hoặc cấu trúc bean dependencies rõ ràng. Đừng phụ thuộc ngẫu nhiên vào thứ tự khai báo phương thức `@Bean`.

## 10. Tạo metadata fixture cho mock

Khi code proxy cần kiểm tra MBean metadata, mock phải trả dữ liệu hợp lệ cho `getMBeanInfo`.

Ví dụ phác thảo:

```java
import javax.management.*;

MBeanAttributeInfo countAttribute = new MBeanAttributeInfo(
    "PendingCount", "int", "Pending queue entries",
    true, false, false
);

MBeanOperationInfo resetOperation = new MBeanOperationInfo(
    "resetStatistics",
    "Resets queue statistics",
    new MBeanParameterInfo[0],
    "void",
    MBeanOperationInfo.ACTION
);

MBeanInfo info = new MBeanInfo(
    QueueAdmin.class.getName(),
    "Queue admin",
    new MBeanAttributeInfo[] { countAttribute },
    null,
    new MBeanOperationInfo[] { resetOperation },
    null
);

when(connection.getMBeanInfo(name)).thenReturn(info);
```

Fixture metadata phải phản ánh interface mà proxy đang expose. Nếu test còn dùng `isPaused` và `setPaused`, cần bổ sung attribute `Paused` (kiểu boolean, readable/writable) để mock không tự mâu thuẫn.

## 11. Kiểm thử lỗi khi ObjectName không tồn tại

Một local proxy có thể được tạo với tên không tồn tại. Tùy chế độ initialization/validation của factory, lỗi có thể xuất hiện ngay khi proxy khởi tạo hoặc khi method được gọi.

Sử dụng MBeanServer thật:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.management");

ObjectName missing = new ObjectName(
    "com.example.orders:type=Queue,name=Missing"
);

assertFalse(server.isRegistered(missing));
```

Sau đó cấu hình proxy với `missing` và kiểm tra exception ở đúng thời điểm do phiên bản/configuration Spring quy định. Không nên viết test giả định rằng exception lúc nào cũng là `InstanceNotFoundException` trực tiếp: proxy có thể bọc lỗi JMX trong một Spring `JmxException` hoặc runtime exception tương ứng.

Thực hành kiểm tra exception chain và ObjectName liên quan sẽ bền vững hơn so với hardcode toàn bộ message.

## 12. Kiểm thử lỗi khi metadata không khớp interface

Giả sử client interface mong đợi:

```java
int getPendingCount();
void retryFailed(int maxCount);
```

nhưng MBean server chỉ công bố `PendingCount` và `resetStatistics()`. Khi proxy gọi `retryFailed`, server không tìm thấy operation tương ứng.

Có thể kiểm tra `MBeanInfo` trước:

```java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
    for (MBeanParameterInfo param : op.getSignature()) {
        System.out.println(param.getType());
    }
}
```

Nếu operation `retryFailed(int)` không có trong `MBeanInfo`, lỗi thuộc hợp đồng JMX, không phải mạng.

Với method overload, signature có vai trò quyết định. Primitive `int` cần signature `"int"`, không phải `"java.lang.Integer"`. Mock có thể bỏ qua sự khác biệt này nếu stubbing quá rộng.

## 13. Kiểm thử hành vi ngoại lệ từ operation

Một operation có thể ném exception nghiệp vụ:

```java
public void resetStatistics() {
    throw new IllegalStateException("Reset is currently blocked");
}
```

Khi gọi qua JMX, server và proxy có thể bọc exception. Mục tiêu test là:

- Xác minh ngoại lệ thực sự được chuyển đến client ở dạng có thể xử lý.
- Tìm nguyên nhân gốc, thay vì giả định client nhận đúng loại exception của implementation.
- Kiểm tra trạng thái dữ liệu không bị thay đổi ngoài dự kiến.
- Không để test làm rò rỉ MBean sau khi exception xảy ra.

Khi mock `MBeanServerConnection`, có thể mô phỏng `MBeanException`, `ReflectionException`, `InstanceNotFoundException` hoặc `IOException` theo API thực, rồi xác minh cách proxy wrap các lỗi đó.

Không viết assertion dựa vào phần message thay đổi theo JDK hay phiên bản Spring nếu điều quan trọng là loại lỗi và ngữ cảnh ObjectName.

## 14. Test đồng thời và tính ổn định

MBeanServer riêng giúp giảm rủi ro cross-test interference nhưng vẫn phải chú ý:

- Dùng `ObjectName` duy nhất trong từng server.
- Cleanup trong `finally` hoặc `@AfterEach`.
- Không chạy test dùng chung global platform server với cùng ObjectName song song.
- Không dựa vào PID, timestamp hoặc thứ tự test để đặt tên MBean nếu không có lý do.
- Đảm bảo không có Spring context/connector còn giữ reference và tiếp tục gọi MBean sau teardown.
- Nếu test tạo `MBeanProxyFactoryBean` theo lifecycle Spring, đóng context đúng cách.
- Không gọi `releaseMBeanServer` đối với server không được tạo bởi `createMBeanServer`.

Ví dụ:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("test.management");
```

`newMBeanServer` tạo một server không đăng ký vào danh sách do factory quản lý, phù hợp khi không cần discovery và không cần gọi `releaseMBeanServer`.

## 15. Khi nào nên dùng MBeanServer mock hoàn toàn?

Không phải lúc nào cũng cần tạo MBeanServer thật. Mock phù hợp khi yêu cầu cần kiểm tra:

1. Proxy chuyển getter thành `getAttribute` đúng tên.
2. Setter trở thành `setAttribute` với `Attribute` đúng.
3. Operation dùng `invoke` và signature chính xác.
4. Khi JMX API báo lỗi, ứng dụng client không làm mất context lỗi.
5. Client không gọi operation nếu input validation fail trước đó.

Nếu bạn chỉ test logic nghiệp vụ của `QueueAdmin`, hãy unit-test class trực tiếp. Nếu bạn cần biết implementation có tuân Standard MBean contract và proxy có gọi được nó hay không, dùng MBeanServer thật.

**Mock không nên thay thế hoàn toàn integration test**, vì lỗi tên, chữ ký, metadata, đăng ký và compliance của MBean có thể bị bỏ sót.

## 16. Kiểm thử với MBeanServerConnection thay vì server cụ thể

Một lợi ích của API JMX là local và remote đều có thể xuất hiện với cùng interface `MBeanServerConnection`.

```java
MBeanServerConnection local = server;
```

Khi kiểm thử code có dependency `MBeanServerConnection`, có thể inject một mock hoặc server local thật mà không cần socket/RMI.

Nếu ứng dụng dùng remote `JMXConnector`, test với MBeanServer local không bao phủ:

- Authentication và authorization của connector.
- TLS/certificate và cổng mạng.
- Serialization/classloader giữa hai JVM.
- Timeout, disconnect và retry của kết nối.
- RMI hostname/port, firewall hoặc service URL.

Đó là các yêu cầu integration/e2e riêng. **Local MBeanServer thật** xác minh hợp đồng JMX, không xác minh toàn bộ remote transport.

## 17. Mô hình test được đề xuất

Một suite thử nghiệm cân bằng có thể gồm:

| Lớp test | Cần xác minh | Công cụ |
| --- | --- | --- |
| Unit test implementation | Logic của queue admin | JUnit, không cần JMX |
| Proxy mapping test | Getter/setter/operation chuyển sang API JMX | Mockito + `MBeanServerConnection` |
| JMX compliance test | MBean đăng ký đúng, metadata chính xác | `MBeanServer` thật |
| Spring wiring test | Exporter và proxy trong context dùng cùng server/name | `AnnotationConfigApplicationContext` |
| Fault test | MBean missing, metadata mismatch, operation exception | Mock hoặc server thật |
| Remote connectivity test | Auth/TLS/network và serialization | JMX connector được cấu hình riêng |

Không cần tất cả mọi lớp cho một demo nhỏ, nhưng nên có ít nhất một test end-to-end local với server thật khi MBean proxy là phần quan trọng của hệ thống.

## 18. Bài tập thực hành

1. Tạo Standard MBean `QueueAdmin` và proxy `QueueAdminMBean` qua `MBeanProxyFactoryBean`; kiểm tra `getPendingCount()`.
2. Mock `MBeanServerConnection`, xác nhận proxy gọi `getAttribute(name, "PendingCount")`.
3. Thêm `setPaused(boolean)`, kiểm tra proxy tạo `Attribute("Paused", true)` khi ghi.
4. Thêm operation `retryFailed(int maxCount)`; xác nhận `invoke` truyền signature `"int"`.
5. Tạo server riêng, đăng ký MBean rồi thử client proxy thực thi operation và kiểm tra state.
6. Cố tình đặt sai `ObjectName` để quan sát lỗi khi khởi tạo hoặc invocation.
7. Dùng interface khác metadata của MBean thật, đọc `MBeanInfo` rồi sửa mismatch.
8. Viết Spring integration test có `MBeanExporter` và `MBeanProxyFactoryBean` trong một context; thiết lập dependency để exporter khởi tạo trước proxy.
9. Đảm bảo cleanup và chạy toàn bộ test nhiều lần để phát hiện lỗi trùng tên hoặc leak.

## 19. Câu hỏi tự kiểm tra

- Vì sao kiểm thử implementation trực tiếp không chứng minh proxy MBean hoạt động?
- Mock `MBeanServerConnection` kiểm tra điều gì tốt nhất?
- Những lỗi nào chỉ dễ phát hiện khi dùng `MBeanServer` thật?
- `MBeanProxyFactoryBean` sử dụng `ObjectName` và management interface để làm gì?
- Khi nào proxy thất bại vì MBean chưa được đăng ký?
- Vì sao test dùng platform MBeanServer có thể bị ảnh hưởng bởi test chạy song song?
- Việc dùng MBeanServer local có xác minh được TLS hoặc authentication remote JMX không?
- Vì sao phải đóng context và unregister MBean sau test?

**Ghi nhớ:** Proxy MBean local của Spring cho phép client thao tác với MBean bằng Java interface nhưng vẫn đi qua API JMX. Dùng mock `MBeanServerConnection` để kiểm tra mapping lời gọi và các nhánh lỗi, kết hợp `MBeanServer` thật để kiểm tra đăng ký, metadata và execution. Luôn kiểm soát ObjectName, thứ tự khởi tạo, lỗi JMX và cleanup để test ổn định, độc lập.