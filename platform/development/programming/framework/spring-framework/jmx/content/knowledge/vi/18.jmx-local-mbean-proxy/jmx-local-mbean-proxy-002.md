# ProxyInterface và hợp đồng Java phía người gọi trong Spring JMX local MBean proxy

## 1. Mục tiêu: gọi MBean như một Java interface

JMX cung cấp `MBeanServerConnection` để đọc attribute và gọi operation của MBean thông qua `ObjectName`. API gốc yêu cầu caller làm việc với tên thuộc tính, danh sách tham số, chữ ký kiểu dữ liệu và exception của JMX.

Ví dụ đọc trực tiếp:

```java
ObjectName name =
    new ObjectName("com.example.jobs:type=Worker,name=Primary");

boolean paused = (Boolean) mbeanServer.getAttribute(
    name, "Paused"
);

mbeanServer.invoke(
    name, "pause", new Object[0], new String[0]
);
```

Cách này đúng nhưng làm mã gọi phụ thuộc string và API hạ tầng. Spring Framework hỗ trợ **local MBean proxy**: định nghĩa một **Java interface phía client** rồi dùng `MBeanProxyFactoryBean` để ánh xạ lời gọi trên interface sang JMX.

`proxyInterface` là hợp đồng mà object proxy triển khai để phía caller có thể gọi `getQueueDepth()` hoặc `pause()` như một phương thức Java bình thường. Nó **không phải tên MBean**, cũng không phải switch tự động export một bean thành JMX.

Bài này giúp phân biệt:

- Management interface ở **phía server**: những attribute/operation thực sự được MBean export.
- `proxyInterface` ở **phía caller**: những lời gọi Java mà Spring proxy chấp nhận.
- `ObjectName`: xác định MBean đích trong một `MBeanServer`.
- `MBeanServerConnection`: kênh thực thi JMX, có thể local hoặc remote.
- Cách xác minh hai bên đồng ý về tên, kiểu tham số, kiểu kết quả và ngữ nghĩa.

## 2. Luồng lời gọi qua local proxy

```text
Business/operations caller
         |
         v
WorkerManagementClient (Java interface)
         |
         v
Spring MBeanProxyFactoryBean
         |
         v
MBeanClientInterceptor
         |
         v
MBeanServerConnection (local server)
         |
         v
ObjectName -> exported MBean
         |
         v
Attribute / operation / exception
```

Proxy giúp loại bỏ string mapping khỏi phần lớn mã gọi, nhưng không bỏ qua JMX. Thời điểm gọi method, proxy vẫn phải tra tên MBean, chuyển getter/setter thành attribute access, gửi operation và xử lý kết quả hoặc lỗi.

**Local** nghĩa là caller và `MBeanServer` chạy trong cùng JVM. Nó không có chi phí mạng như JMX remote, nhưng vẫn có chi phí reflection, metadata, kiểm tra type và xử lý JMX. Lời gọi cũng vẫn có thể thất bại nếu MBean chưa được đăng ký, bị unregister hoặc có hợp đồng khác với interface client.

## 3. Tạo MBean phía server

Để minh họa, dùng một Standard MBean Java SE:

```java
package com.example.jobs.jmx;

public interface WorkerControlMBean {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
```

Implementation:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class WorkerControl implements WorkerControlMBean {
    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicInteger queued = new AtomicInteger(7);

    @Override
    public int getQueueDepth() {
        return queued.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pause() {
        paused.set(true);
    }

    @Override
    public void resume() {
        paused.set(false);
    }
}
```

Đăng ký:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName objectName = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

server.registerMBean(new WorkerControl(), objectName);
```

Ở ví dụ này, `WorkerControlMBean` là hợp đồng JMX chuẩn; các method public nằm ngoài interface này không tự xuất hiện chỉ vì chúng tồn tại trên implementation.

Trong ứng dụng Spring thực, việc đăng ký và unregister nên do một exporter hoặc component hạ tầng có ownership rõ ràng quản lý, tránh đăng ký trùng hoặc để lại MBean khi context đóng.

## 4. Thiết kế proxyInterface phía caller

Client có thể dùng một Java interface riêng mang tên khác interface server, miễn chữ ký quản trị khớp với bề mặt JMX thực tế:

```java
package com.example.jobs.client;

public interface WorkerManagementClient {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
```

Interface này thể hiện những gì caller được phép sử dụng. Nó không cần kế thừa `WorkerControlMBean`, và cũng không cần annotation `@ManagedResource`.

Một số lợi ích:

1. **Typed calls**: compiler kiểm tra tên method và kiểu Java được khai báo.
2. **Giảm coupling**: caller không cần tự tạo `ObjectName`, `AttributeList` hay mảng signature mỗi lần gọi.
3. **Giới hạn bề mặt**: chỉ đưa những method người gọi cần lên interface client.
4. **Dễ thay adapter**: caller có thể dùng fake implementation của interface trong unit test.
5. **Hợp đồng có thể version hóa**: thay đổi bên server phải cân nhắc khả năng tương thích với những client đã triển khai.

Dù hai interface có thể giống chữ ký, chúng **không tự động đồng bộ**. Nếu server đổi `getQueueDepth()` thành `getPendingCount()` mà client chưa sửa, Java code ở client vẫn compile nhưng lời gọi JMX có thể thất bại lúc runtime.

## 5. Spring MBeanProxyFactoryBean với proxyInterface

Ví dụ Java configuration:

```java
package com.example.jobs.config;

import com.example.jobs.client.WorkerManagementClient;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class LocalJmxClientConfig {

    @Bean
    public MBeanServer localMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanProxyFactoryBean workerManagementClient(
            MBeanServer localMBeanServer) throws Exception {

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(localMBeanServer);
        factory.setObjectName(new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        ));
        factory.setProxyInterface(WorkerManagementClient.class);
        return factory;
    }
}
```

`MBeanProxyFactoryBean` là Spring `FactoryBean`. Spring container khởi tạo factory và công bố object proxy của kiểu `WorkerManagementClient` cho bean khác sử dụng:

```java
package com.example.jobs.application;

import com.example.jobs.client.WorkerManagementClient;
import org.springframework.stereotype.Component;

@Component
public class OperationsConsole {
    private final WorkerManagementClient worker;

    public OperationsConsole(WorkerManagementClient worker) {
        this.worker = worker;
    }

    public void inspectAndPause() {
        int pending = worker.getQueueDepth();

        if (pending > 0 && !worker.isPaused()) {
            worker.pause();
        }
    }
}
```

Trong ví dụ này, không gọi `new WorkerManagementClient()`; Spring cung cấp dynamic proxy cho interface ấy. Tên bean factory ở container là `workerManagementClient`, còn `ObjectName` xác định MBean đích là `com.example.jobs:type=Worker,name=Primary`. Hai tên phục vụ hai registry khác nhau.

Điều kiện thực tế: MBean phải được đăng ký trên đúng `MBeanServer`. Nếu `WorkerControl` chưa được đăng ký khi client proxy được khởi tạo hoặc gọi, cấu hình kết nối và lựa chọn thời điểm lookup có thể dẫn tới lỗi khởi động hoặc lỗi runtime. Không giả định mọi proxy luôn chờ đến lời gọi đầu tiên mới kiểm tra server.

## 6. Tại sao phải thiết lập proxyInterface?

`proxyInterface` cho Spring biết object proxy phải **triển khai interface nào**. Interface ấy cung cấp danh sách method có thể gọi từ mã Java và kiểu trả về mà caller kỳ vọng.

Nếu thiếu hoặc chỉ định sai interface, factory có thể không tạo được proxy đúng kiểu, hoặc ứng dụng không thể inject bean theo interface kỳ vọng. Nếu interface được chọn chứa method không tồn tại dưới dạng attribute/operation của MBean đích, proxy có thể được tạo nhưng lời gọi sẽ thất bại khi thực thi.

Ví dụ một interface sai:

```java
public interface IncorrectWorkerClient {
    String getQueueDepth(); // Server attribute thực tế là int.
    void resetEverything(); // MBean không export operation này.
}
```

Những method trên nhìn hợp lệ đối với Java compiler, nhưng không hợp lệ với **contract runtime của MBean**:

- `getQueueDepth` cần đọc attribute `QueueDepth` có kiểu phù hợp.
- `resetEverything` cần operation JMX tên `resetEverything`, với chữ ký tham số tương ứng, hiện không có.

Dạng lỗi thường gặp là exception khi proxy thực hiện JMX invocation, không phải lỗi compile-time trong caller. Vì thế cần integration test gọi qua chính proxy.

## 7. Ánh xạ getter, setter và operation

Một interface client có thể có:

```java
public interface CacheManagementClient {
    int getSize();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clearExpired();
}
```

Theo quy ước JavaBeans và mô hình JMX:

| Method phía caller | Thành phần phía MBean cần có | Chú ý |
| --- | --- | --- |
| `getSize()` | Readable attribute `Size` | Kiểu trả về phải tương thích |
| `isEnabled()` | Readable boolean attribute `Enabled` | Dạng `is...` phù hợp với boolean |
| `setEnabled(boolean)` | Writable attribute `Enabled` | MBean phải cho phép ghi và nhận kiểu phù hợp |
| `clearExpired()` | Operation `clearExpired` | Cần chữ ký operation đúng |

Tùy contract và Spring MBean client interceptor, method getter/setter được ánh xạ sang JMX attribute, còn method khác được ánh xạ sang operation. Không phải mọi method bắt đầu bằng `get` đều tự tạo attribute trong MBean nếu server không export thuộc tính đó.

Nếu MBean xuất `Size` read-only, `setSize(int)` trong interface client không thể biến nó thành writable attribute. `proxyInterface` **không thay đổi quyền hay khả năng của server**, chỉ mô tả mong đợi của caller.

## 8. ObjectName và proxyInterface là hai trục độc lập

Một factory có hai cấu hình chính:

```java
factory.setObjectName(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);
factory.setProxyInterface(WorkerManagementClient.class);
```

- `objectName` trả lời: **đang gọi MBean nào?**
- `proxyInterface` trả lời: **Java caller được gọi những method nào?**

Bạn có thể tạo hai proxy cùng interface nhưng nhắm vào hai MBean khác nhau:

```java
ObjectName primary = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

ObjectName secondary = new ObjectName(
    "com.example.jobs:type=Worker,name=Secondary"
);
```

Ngược lại, có thể tạo các client interface nhỏ khác nhau cho cùng MBean (ví dụ interface chỉ đọc và interface có thao tác quản trị), nhưng phân chia interface **không phải cơ chế bảo mật JMX**. Caller có quyền truy cập `MBeanServerConnection` vẫn có thể gọi operation khác nếu không bị kiểm soát ở server/connector.

Trong hệ thống có nhiều JVM, cùng một `ObjectName` có thể tồn tại ở mỗi JVM. Muốn gọi đúng MBean, còn cần kết nối tới đúng `MBeanServer`.

## 9. Local proxy khác remote proxy

`MBeanProxyFactoryBean` hoạt động trên nền một `MBeanServerConnection`. Một `MBeanServer` cục bộ cũng triển khai interface kết nối này, nên có thể dùng trực tiếp:

```java
factory.setServer(
    java.lang.management.ManagementFactory
        .getPlatformMBeanServer()
);
```

Khi dùng remote JMX, client thường có `JMXConnector` và lấy kết nối:

```java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();

factory.setServer(connection);
```

`connector` ở đây là `JMXConnector` đã tạo, kết nối và được quản lý lifecycle ở hạ tầng. Với remote, cần xử lý xác thực, SSL/TLS, kết nối bị ngắt, reconnect và đóng connector. Với local, không có network hop nhưng cần quan tâm đến thứ tự startup/shutdown và tên MBean.

**Không xem Java interface proxy như lời hứa tự động xử lý mọi lỗi remote**. Nếu kết nối mất, method Java vẫn có thể ném exception runtime từ Spring JMX hoặc hạ tầng kết nối. Retry cần phù hợp ngữ nghĩa operation; lặp lại lệnh có side effect có thể gây thay đổi trạng thái hai lần.

## 10. Phân biệt MBeanProxyFactoryBean với JDK dynamic proxy cho Spring AOP

Một ứng dụng Spring có thể chứa hai loại proxy mang mục tiêu khác nhau:

1. **AOP proxy** bọc service để thêm transaction, security hoặc caching.
2. **JMX client proxy** do `MBeanProxyFactoryBean` tạo để chuyển lời gọi Java sang JMX.

Chúng đều có thể dùng dynamic proxy và interface nhưng cơ chế, đích gọi và failure modes khác nhau.

```text
JMX caller
   |
   +--> JMX proxy -> MBeanServer -> MBean
                                   |
                                   +--> Có thể là Spring-managed bean
                                        hoặc adapter quản trị
```

Một MBean server-side có thể export từ Spring bean bị AOP proxy. Khi đó phải bảo đảm bề mặt JMX được xác định đúng qua target/interface/assembler. `proxyInterface` phía client không giải quyết được việc server-side AOP proxy che method hoặc annotation.

Tách rõ hai câu hỏi khi chẩn đoán:

- Client có interface tương thích với MBeanInfo không?
- Server đã thực sự đăng ký MBean với attribute/operation đúng không?

## 11. Thiết kế hợp đồng client nhỏ và ổn định

Không nên dùng interface nghiệp vụ lớn làm `proxyInterface` chỉ để tiện inject. Ví dụ:

```java
public interface OrderService {
    String placeOrder(String customerId);
    void cancelOrder(String orderId);
    long getPendingTotal();
    void pauseBackgroundWorker();
}
```

Nếu MBean server chỉ quản lý worker, để client JMX phụ thuộc `OrderService` khiến caller trông đợi những business operation không được export.

Tạo interface riêng:

```java
public interface OrderWorkerAdmin {
    long getPendingTotal();
    boolean isPaused();
    void pause();
    void resume();
}
```

Những lợi ích của contract nhỏ:

- Không vô tình phơi bày business action qua công cụ quản trị.
- Giảm số lượng method cần giữ tương thích.
- Dễ định nghĩa read-only attributes và operation có tác động.
- Giảm phụ thuộc vào domain types khó mapping qua JMX.
- Dễ tạo fake trong unit test và kiểm thử tích hợp bằng MBeanInfo.

Hạn chế đưa `ObjectName`, `MBeanInfo`, `AttributeList` hoặc `JMException` vào một interface dùng chung toàn ứng dụng nếu caller không cần biết hạ tầng JMX. Nếu cần tách sạch hoàn toàn, định nghĩa application port độc lập JMX rồi tạo một adapter dùng proxy để hiện thực port.

## 12. Kiểu dữ liệu và signature cần khớp

JMX hỗ trợ các kiểu đơn giản như `boolean`, `int`, `long`, `String` và một số kiểu phức tạp qua MXBean/Open MBean mapping. Một Java interface client nên dùng các kiểu mà phía MBean thực sự công bố và client có thể chuyển đổi.

Ví dụ operation có tham số:

```java
public interface WorkerTuningClient {
    int getConcurrencyLimit();
    void setConcurrencyLimit(int value);
    void requestDrain(String reason);
}
```

Phía MBean phải có `ConcurrencyLimit` readable/writable nếu muốn dùng getter/setter, cùng operation `requestDrain` nhận `java.lang.String`.

Nếu server chỉ có `requestDrain()` không tham số, lời gọi `requestDrain("maintenance")` không hợp lệ. Java overload và type promotion không tự áp dụng trên JMX theo cách gọi method cục bộ thông thường: JMX xác định operation bằng tên và danh sách signature.

Khi có overload, kiểm tra `MBeanOperationInfo.getSignature()` để biết chính xác parameter types, thứ tự tham số và return type.

## 13. Lỗi khi gọi và cách xử lý

Một số tình huống:

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| Proxy bean không tạo được | `proxyInterface` không đúng loại hoặc thiếu cấu hình | Xem exception lúc tạo factory |
| `InstanceNotFoundException` / wrapped exception | `ObjectName` chưa đăng ký hoặc đã unregister | `isRegistered`, lifecycle exporter |
| Attribute không thấy | Getter client không khớp MBean attribute | `getMBeanInfo` và tên attribute |
| Attribute read-only | Client cố gọi setter nhưng MBean không cho ghi | `isWritable` trong MBeanInfo |
| Operation không tồn tại | Tên hoặc signature khác | `getOperations()`, parameter signature |
| Kiểu trả về không đúng | MBeanInfo type khác client interface | Chuẩn hóa contract và JMX mapping |
| Proxy hoạt động rồi lỗi sau restart | Server unregister/re-register khi context thay đổi | Kiểm tra ObjectName và thời điểm call |
| Local test chạy nhưng prod remote thất bại | Đúng contract nhưng kết nối khác | Kiểm tra connector, TLS, authentication |

Exception được Spring JMX interceptor bọc hoặc chuyển dịch theo tình huống; không nên dựa vào một lớp exception duy nhất cho mọi lỗi. Khi log, ghi ObjectName và operation/attribute đang gọi nhưng tránh lộ tham số nhạy cảm.

Một client quản trị nên có timeout/chính sách failure phù hợp nếu sử dụng kết nối remote. Không tự retry các operation làm thay đổi trạng thái mà chưa thiết kế idempotency hoặc cơ chế xác minh kết quả.

## 14. Đọc MBeanInfo để kiểm tra interface thực tế

Trước khi kết luận lỗi nằm ở proxy, hỏi server:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("operation=" + operation.getName());
}
```

`server` phải là chính `MBeanServer` mà exporter dùng; nếu export vào custom server thì đọc platform server có thể không thấy. MBeanInfo là nguồn xác nhận contract mà JMX client thực tế nhìn thấy.

Với `WorkerManagementClient`, mong đợi:

- `QueueDepth`: readable integer.
- `Paused`: readable boolean.
- `pause`: operation không tham số.
- `resume`: operation không tham số.

Cần test cả việc gọi qua Spring proxy, vì chỉ khớp metadata chưa bảo đảm adapter server-side thực hiện operation mà không ném lỗi.

## 15. Kiểm thử local proxy bằng JUnit và một MBeanServer riêng

Kiểm thử không cần cổng mạng hoặc JConsole. Dùng một server test riêng và cùng `ObjectName` cho hai phía:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

class WorkerLocalProxyTest {

    @Test
    void proxyCallsTheRegisteredMBean() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("jmx-test");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        try {
            server.registerMBean(new WorkerControl(), name);

            MBeanProxyFactoryBean factory =
                new MBeanProxyFactoryBean();

            factory.setServer(server);
            factory.setObjectName(name);
            factory.setProxyInterface(WorkerManagementClient.class);
            factory.afterPropertiesSet();

            WorkerManagementClient client =
                (WorkerManagementClient) factory.getObject();

            assertNotNull(client);
            assertEquals(7, client.getQueueDepth());
            assertFalse(client.isPaused());

            client.pause();
            assertTrue(client.isPaused());

            client.resume();
            assertFalse(client.isPaused());
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Đây là kiểm thử local JMX qua object proxy thực, không phải mock. Cần đặt các class/interface vào package và source set phù hợp, đồng thời có Spring JMX và JUnit dependencies. Với những phiên bản Spring khác nhau, callback lifecycle hoặc API cấu hình có thể có khác biệt; khi chạy trong container, `FactoryBean` thường được Spring khởi tạo hộ.

Để tránh rò giữa các test song song, tạo server riêng hoặc ObjectName có namespace riêng; luôn unregister MBean thuộc test. Không xóa toàn bộ MBean khỏi platform server.

## 16. Unit test người gọi không cần MBeanServer

Caller nên phụ thuộc interface chứ không tự lấy `MBeanServer`. Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OperationsConsoleTest {

    @Test
    void pausesOnlyWhenWorkExists() {
        class Fake implements WorkerManagementClient {
            int queued = 3;
            boolean paused = false;

            public int getQueueDepth() {
                return queued;
            }

            public boolean isPaused() {
                return paused;
            }

            public void pause() {
                paused = true;
            }

            public void resume() {
                paused = false;
            }
        }

        Fake fake = new Fake();
        OperationsConsole console = new OperationsConsole(fake);

        console.inspectAndPause();
        assertTrue(fake.paused);
    }
}
```

Unit test này chứng minh logic của caller, nhưng không chứng minh `proxyInterface` khớp MBean server. Vì vậy nên có **cả hai tầng**:

1. Test caller với fake để kiểm tra quyết định của application.
2. Test integration trên MBeanServer thật để kiểm tra JMX mapping và lifecycle.

## 17. Những giới hạn quan trọng

### 17.1. Type-safe ở Java không đồng nghĩa contract-safe ở runtime

Compiler chỉ biết `WorkerManagementClient`. Nó không thể xác minh lúc build rằng JVM khác hoặc một context khác đang export MBean có attribute/operation tương ứng. Cần integration test, runtime health check và quản trị version.

### 17.2. Client interface không tạo quyền

Một interface chỉ có getter không ngăn caller có JMX connection truy cập operation khác. Quyền truy cập do connector/server và chính sách hạ tầng quyết định. Operation có tác động phải được bảo vệ và audit.

### 17.3. Local không đồng nghĩa luôn nhanh

MBean getter có thể truy vấn database, giữ lock hoặc gọi network; vì vậy local proxy vẫn có thể block caller. Thiết kế getter trả snapshot ngắn, operation có giới hạn và không đặt các lệnh nguy hiểm trong đường request quan trọng.

### 17.4. Đừng nhầm Spring bean name với ObjectName

`workerManagementClient` là tên bean proxy trong Spring container; `com.example.jobs:type=Worker,name=Primary` là tên MBean. Cấu hình đúng proxyInterface nhưng ObjectName sai vẫn thất bại.

### 17.5. Lifecycle phải có chủ sở hữu

Khi context xuất MBean đóng, MBean có thể bị unregister. Client proxy tồn tại sau thời điểm đó sẽ không thể gọi tiếp, trừ khi MBean được đăng ký lại dưới tên phù hợp. Cần quyết định caller phải fail, chờ sẵn sàng hay khởi tạo lại proxy tùy kiến trúc.

## 18. Checklist trước khi đưa local MBean proxy vào ứng dụng

- [ ] Đã xác định chính xác MBeanServer được exporter sử dụng.
- [ ] `ObjectName` đúng domain và key properties, không có wildcard ngoài ý muốn.
- [ ] `proxyInterface` là Java interface đủ nhỏ, phù hợp caller.
- [ ] Getter/setter map đúng JMX attributes và read/write flags.
- [ ] Operation names, parameter types và return types khớp MBeanInfo.
- [ ] Không nhầm JMX client proxy với AOP proxy của service nghiệp vụ.
- [ ] Đã định nghĩa hành vi khi MBean chưa có hoặc bị unregister.
- [ ] Lệnh có tác động có validation/authorization/audit phù hợp.
- [ ] Có unit test caller và integration test qua MBeanServer.
- [ ] Test dọn registration/server/connector đúng ownership.

## 19. Ghi nhớ

**`proxyInterface` là hợp đồng Java ở phía người gọi**, còn `ObjectName` chọn MBean đích và `MBeanServerConnection` thực hiện lời gọi JMX. `MBeanProxyFactoryBean` giúp caller viết code theo interface, nhưng không thay đổi khả năng thật của MBean, không tự tạo security và không loại bỏ lỗi runtime. Muốn proxy tin cậy, giữ interface nhỏ, đối chiếu trực tiếp với `MBeanInfo`, kiểm thử getter/operation trên server thật và quản lý lifecycle một cách rõ ràng.
