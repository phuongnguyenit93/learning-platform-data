# MBeanProxyFactoryBean dùng để tạo proxy typed trong Spring JMX

## 1. Bài toán: gọi MBean như một Java interface

Trong Java Management Extensions (**JMX**), ứng dụng có thể xuất các thuộc tính và thao tác quản trị qua **MBeanServer**. Một client JMX truyền thống phải biết `ObjectName`, tên attribute, operation, kiểu tham số và cách sử dụng `MBeanServerConnection`.

Ví dụ gọi một operation qua JMX thuần:

```java
ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerManager,name=background"
);

connection.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
```

Cách này hoạt động nhưng khiến code nghiệp vụ hoặc code quản trị phải thao tác với API JMX, chuỗi tên operation và chữ ký tham số. Nếu đổi tên một method, lỗi có thể chỉ được phát hiện lúc chạy.

Spring Framework cung cấp **`MBeanProxyFactoryBean`**, một `FactoryBean` tạo ra **proxy Java theo interface được khai báo**. Code gọi proxy nhìn giống đang sử dụng một Java object bình thường:

```java
workerAdmin.pause();
boolean paused = workerAdmin.isPaused();
```

Trong khi đó, lời gọi thực sự được chuyển tới MBean đã đăng ký trong một MBeanServer. Đây là một cách giảm coupling giữa caller và các chi tiết của JMX protocol.

**Mục tiêu của bài học:** hiểu cách cấu hình `MBeanProxyFactoryBean`, xác định vai trò của interface, ObjectName và MBeanServerConnection, kiểm tra proxy typed local, đồng thời biết giới hạn và các lỗi phổ biến.

## 2. Kiến trúc của typed MBean proxy

```text
Spring ApplicationContext
     |
     +-- WorkerAdmin interface
     |       |
     |       v
     +-- MBeanProxyFactoryBean
             |
             +-- proxyInterface = WorkerAdmin
             +-- objectName = com.example.jobs:type=WorkerManager,name=background
             +-- server = MBeanServerConnection
             |
             v
          Typed proxy
             |
             | workerAdmin.pause()
             v
       MBeanServerConnection
             |
             v
          MBeanServer
             |
             +-- ObjectName
                    |
                    +-- WorkerManager MBean
                            |
                            +-- real worker resource
```

Các khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| **Proxy interface** | Hợp đồng Java mà caller dùng để gọi method. |
| **`MBeanProxyFactoryBean`** | Tạo proxy theo interface và chuyển lời gọi tới JMX. |
| **`ObjectName`** | Định danh MBean mục tiêu trong MBeanServer. |
| **`MBeanServerConnection`** | API chuẩn để đọc attribute, ghi attribute hoặc gọi operation. |
| **MBeanServer** | Registry JMX chứa MBean đã đăng ký. |
| **Target MBean** | Thực thi các attribute/operation, có thể được Spring export. |

**Local proxy không có nghĩa phương thức được gọi trực tiếp trên Java object.** Proxy vẫn đi qua JMX layer và phải tuân theo MBean metadata. Nó mang lại trải nghiệm typed Java API nhưng không xóa bỏ quy tắc JMX.

## 3. Vì sao cần một interface?

`MBeanProxyFactoryBean` cần biết Java interface mà proxy triển khai. Interface mô tả các method caller được quyền gọi ở cấp Java:

```java
package com.example.management;

public interface WorkerAdmin {
    boolean isPaused();
    int getActiveWorkers();
    void pause();
    void resume();
}
```

Caller có thể lập trình trực tiếp theo interface:

```java
public final class OperationsController {
    private final WorkerAdmin admin;

    public OperationsController(WorkerAdmin admin) {
        this.admin = admin;
    }

    public void ensurePaused() {
        if (!admin.isPaused()) {
            admin.pause();
        }
    }
}
```

Lợi ích:

- IDE biết tên method, kiểu tham số và kiểu kết quả.
- Java compiler phát hiện caller dùng sai method hoặc kiểu.
- Code gọi không cần import `javax.management.ObjectName` hay `MBeanServerConnection`.
- Có thể mock interface trong unit test.
- Có thể dùng dependency injection để thay proxy bằng một implementation khác trong kiểm thử.

**Giới hạn:** interface không tự bảo đảm MBean mục tiêu có method tương ứng. Proxy được tạo thành công không nhất thiết chứng minh mọi lời gọi runtime sẽ thành công. Vì vậy phải kiểm tra metadata và integration behavior.

## 4. MBean server-side để thử nghiệm

Để minh họa rõ ràng, xây một **Standard MBean** đơn giản. Khi class có tên `WorkerManager`, interface quản trị theo quy ước JMX là `WorkerManagerMBean`.

```java
package com.example.management;

public interface WorkerManagerMBean {
    boolean isPaused();
    int getActiveWorkers();
    void pause();
    void resume();
}
```

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class WorkerManager implements WorkerManagerMBean {
    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicInteger activeWorkers = new AtomicInteger(4);

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public int getActiveWorkers() {
        return activeWorkers.get();
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

Đây là một resource minh họa. `pause()` chỉ đặt cờ trạng thái, chưa tự dừng scheduler thật. Trong ứng dụng production, cần gắn method quản trị vào logic kiểm soát worker một cách thread-safe và an toàn.

### Đăng ký Standard MBean bằng Java thuần

```java
package com.example.management;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LocalMBeanServerDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=WorkerManager,name=background"
        );

        server.registerMBean(new WorkerManager(), name);

        System.out.println("Registered " + name);
        Thread.sleep(10 * 60 * 1000L);
    }
}
```

Server đăng ký `WorkerManager` thành MBean với ObjectName cố định. Nếu chạy app và mở JConsole đúng JVM, có thể tìm domain `com.example.jobs` và các attribute/operation:

```text
Attributes:
  Paused         boolean
  ActiveWorkers  int

Operations:
  pause()
  resume()
```

## 5. Cấu hình MBeanProxyFactoryBean bằng Java configuration

Giả sử Spring context quản lý một MBeanServer mà MBean mục tiêu đã được đăng ký.

Một cấu hình minh họa:

```java
package com.example.management;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class LocalJmxProxyConfiguration {

    @Bean
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    MBeanProxyFactoryBean workerAdminProxyFactory(
            MBeanServer mbeanServer
    ) {
        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();

        factory.setServer(mbeanServer);
        factory.setObjectName(
            "com.example.jobs:type=WorkerManager,name=background"
        );
        factory.setProxyInterface(WorkerAdmin.class);

        return factory;
    }
}
```

Ý nghĩa cấu hình:

1. `mbeanServer()` trỏ tới platform MBeanServer trong JVM.
2. `setObjectName(...)` xác định MBean đích.
3. `setProxyInterface(WorkerAdmin.class)` chọn hợp đồng mà caller dùng.
4. Spring khởi tạo factory và cung cấp proxy theo interface thay vì yêu cầu caller tự gọi `getAttribute` hoặc `invoke`.

Trong thực tế, **MBean phải được đăng ký trước khi proxy thực sự tương tác**; nếu proxy được khởi tạo trước MBean, hành vi có thể phụ thuộc cấu hình kiểm tra/khởi tạo của Spring và lỗi có thể xuất hiện lúc setup hoặc lúc gọi.

### Tránh hiểu nhầm về @Bean trả FactoryBean

`MBeanProxyFactoryBean` là một `FactoryBean`. Khi được đăng ký như Spring bean, việc lấy bean theo tên thường trả **sản phẩm proxy**, không phải instance FactoryBean. Có thể truy cập chính factory thông qua quy ước `&beanName` của Spring nếu cần thao tác hạ tầng.

Vì vậy, code tiêu thụ nên inject **interface proxy**:

```java
@Component
public class WorkerOperations {
    private final WorkerAdmin workerAdmin;

    public WorkerOperations(WorkerAdmin workerAdmin) {
        this.workerAdmin = workerAdmin;
    }

    public void pauseWork() {
        workerAdmin.pause();
    }
}
```

Tùy tên bean và kiểu FactoryBean mà container công bố, cấu hình injection có thể cần qualifier để phân biệt nếu có nhiều proxy cùng interface.

## 6. Cấu hình bằng XML theo phong cách Spring truyền thống

Trong các dự án Spring XML, `MBeanProxyFactoryBean` có thể được khai báo:

```xml
<bean id="workerAdmin"
      class="org.springframework.jmx.access.MBeanProxyFactoryBean">
    <property name="objectName"
              value="com.example.jobs:type=WorkerManager,name=background"/>
    <property name="proxyInterface"
              value="com.example.management.WorkerAdmin"/>
    <property name="server" ref="mbeanServer"/>
</bean>

<bean id="mbeanServer"
      class="org.springframework.jmx.support.MBeanServerFactoryBean">
    <property name="locateExistingServerIfPossible" value="true"/>
</bean>
```

Đoạn XML minh họa ý tưởng gắn `objectName`, `proxyInterface` và MBeanServer. Một ứng dụng thực nên đảm bảo chính xác server đó cũng là nơi target MBean được đăng ký; không được ngẫu nhiên tạo MBeanServer mới rồi mong nhìn thấy bean trong platform MBeanServer.

Khi thiết kế hệ thống hiện đại, Java configuration thường dễ type-check hơn, nhưng nguyên lý kết nối giống nhau.

## 7. Proxy typed chuyển getter và operation ra sao?

Giả sử interface proxy:

```java
public interface WorkerAdmin {
    boolean isPaused();
    int getActiveWorkers();
    void pause();
    void resume();
}
```

Các method tương ứng với MBean metadata:

| Java interface method | JMX hành vi | Tên JMX |
| --- | --- | --- |
| `isPaused()` | Đọc attribute | `Paused` |
| `getActiveWorkers()` | Đọc attribute | `ActiveWorkers` |
| `pause()` | Gọi operation | `pause` |
| `resume()` | Gọi operation | `resume` |

Một phương thức setter cũng có thể ánh xạ thành thao tác ghi attribute:

```java
public interface QueueSettings {
    int getMaxParallelism();
    void setMaxParallelism(int value);
}
```

Công cụ proxy cần dựa vào thông tin metadata JMX hoặc quy ước nhận diện accessor phù hợp. Với MBean chuẩn, `getMaxParallelism()` và `setMaxParallelism(int)` tạo attribute `MaxParallelism`.

### Interface không cần đặt tên giống server-side MBean interface trong mọi thiết kế

Client-side interface `WorkerAdmin` được dùng làm **hợp đồng proxy**. Server-side có thể là `WorkerManagerMBean`, miễn là các method/attributes cần dùng thực sự tương thích.

Đây là lợi ích của proxy: client không cần biết class server thật. Nhưng sự tương thích phải được kiểm chứng, không được suy luận chỉ từ việc hai interface có tên gần giống.

## 8. Trường hợp Spring export MBean từ một POJO

Ứng dụng Spring có thể dùng `MBeanExporter` và annotation để export plain bean mà không implement interface JMX.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=WorkerManager,name=background"
)
public class SpringWorkerManagement {
    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void pause() {
        paused = true;
    }

    @ManagedOperation
    public void resume() {
        paused = false;
    }
}
```

Khi dùng `AnnotationMBeanExporter` hoặc exporter cùng assembler tương ứng, các method được công bố thành metadata của MBean.

Client proxy `WorkerAdmin` ở ví dụ trước chỉ thành công khi **toàn bộ các method caller dùng đều có trong giao diện JMX**, trong đó `getActiveWorkers()` chưa được class này công bố. Nếu gọi method đó, lỗi runtime là điều có thể xảy ra.

Do đó, nếu server-side bean chỉ có `isPaused`, `pause`, `resume`, hãy dùng interface proxy khớp:

```java
public interface WorkerControl {
    boolean isPaused();
    void pause();
    void resume();
}
```

**MBeanProxyFactoryBean không tự phát minh attribute/operation chưa được server export.**

## 9. Cách kiểm tra metadata trước khi dùng proxy

MBeanServer có thể cho biết target MBean công bố gì:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class WorkerMBeanInspector {
    public static void inspect(
            MBeanServerConnection connection,
            ObjectName name
    ) throws Exception {
        MBeanInfo info = connection.getMBeanInfo(name);

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "ATTRIBUTE %s: type=%s, read=%s, write=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.println(
                "OPERATION " + operation.getName()
            );
        }
    }
}
```

Với `WorkerAdmin`, cần ít nhất:

```text
Paused: boolean, readable=true
ActiveWorkers: int, readable=true
pause(): void
resume(): void
```

Ngoài tên operation, cần đối chiếu chữ ký tham số và kiểu trả về. Một overload `pause(String)` không phải `pause()`; client proxy muốn gọi phiên bản nào phải có contract tương ứng.

Kiểm tra metadata đặc biệt quan trọng sau nâng cấp Spring/JVM hoặc thay schema quản trị vì interface typed chỉ được compiler kiểm tra ở phía client.

## 10. Proxy local và proxy remote có gì giống và khác?

**Local:**

```text
Caller bean -> typed proxy -> local MBeanServer -> target MBean
```

**Remote:**

```text
Caller bean -> typed proxy -> MBeanServerConnection
                               |
                               +-- JMX connector/RMI
                                      |
                                      v
                                  remote MBeanServer
```

Cả hai dùng:

- ObjectName của MBean mục tiêu.
- Giao diện proxy Java.
- Hợp đồng metadata về attributes và operations.

Khác biệt:

| Khía cạnh | Local proxy | Remote proxy |
| --- | --- | --- |
| Kết nối | MBeanServer trong JVM | JMXConnector tạo connection tới JVM khác |
| Mạng | Không cần mạng | Có network, TLS, authentication, firewall |
| Lỗi phổ biến | Target chưa register, sai ObjectName | Thêm timeout, connection failure, RMI endpoint |
| Serialization | Gọi qua JMX nhưng trong JVM | Cần dữ liệu tương thích qua ranh giới JVM |
| Lifecycle | Cùng process, vẫn cần order đăng ký | Cần reconnect và xử lý trạng thái remote |
| Identity | ObjectName trong server local | ObjectName trong server remote |

Không nên đổi ObjectName chỉ vì client chạy ở máy khác. ObjectName quyết định MBean trong server đã kết nối; host/port thuộc cấu hình kết nối.

## 11. Kết nối remote với MBeanServerConnection

Khi chuyển từ local sang remote, có thể lấy connection từ connector JMX:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

JMXConnector connector = JMXConnectorFactory.connect(url);

try {
    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    // Use connection in a JMX proxy or direct client.
} finally {
    connector.close();
}
```

Đây là ví dụ connector cho endpoint đã được bật trước; không mặc định ứng dụng nào cũng mở port 9010. Trong production cần cấu hình authentication, TLS, network ACL và RMI hostname/port phù hợp.

Spring có thể tạo connection qua hạ tầng như `MBeanServerConnectionFactoryBean`, sau đó cung cấp connection cho `MBeanProxyFactoryBean`:

```java
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Bean
MBeanServerConnectionFactoryBean remoteConnection() throws Exception {
    MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
    factory.setServiceUrl(
        "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
    );
    return factory;
}

@Bean
MBeanProxyFactoryBean remoteWorkerProxy(
        MBeanServerConnection connection
) {
    MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
    factory.setServer(connection);
    factory.setObjectName(
        "com.example.jobs:type=WorkerManager,name=background"
    );
    factory.setProxyInterface(WorkerControl.class);
    return factory;
}
```

Các bean và import trong cấu hình phải được đồng bộ với phiên bản Spring thực tế và cách Spring expose `FactoryBean`. Đoạn minh họa nhằm làm rõ: **proxy không trực tiếp sở hữu transport**, mà gọi qua connection đã cấu hình.

## 12. Khi nào cần proxy typed và khi nào gọi JMX API trực tiếp?

### Proxy typed phù hợp khi

- Client Java sử dụng thường xuyên một tập MBean có hợp đồng ổn định.
- Muốn inject interface vào Spring service mà không đưa ObjectName vào logic gọi.
- Muốn IDE và compiler kiểm tra tên method, kiểu tham số.
- Muốn mock/stub các thao tác quản trị trong unit test.
- Muốn tách cấu hình kết nối/naming khỏi code caller.

### JMX API trực tiếp phù hợp khi

- Công cụ là generic JMX explorer, không biết interface của các MBean trước.
- Cần liệt kê domain và MBean động bằng `queryNames`.
- Muốn đọc metadata không có hợp đồng Java cố định.
- Các MBean có interface khác nhau theo runtime.
- Client không phải Java hoặc cần điều khiển bằng giao thức riêng.

Typed proxy không thay thế khả năng introspect động của JMX. Trong hệ thống vận hành, có thể dùng cả hai: proxy typed cho thao tác thường ngày và JMX API để diagnostics/monitoring.

## 13. Không nhầm proxy MBean với Spring AOP proxy

Hai khái niệm đều có chữ “proxy”, nhưng mục đích khác nhau:

| Loại proxy | Mục tiêu chính | Nguồn lời gọi |
| --- | --- | --- |
| Spring AOP proxy | Áp dụng advice như transaction, logging, security | Method trên Spring bean |
| MBean proxy | Chuyển method Java thành lệnh JMX tới MBeanServer | Method trên Java interface proxy |
| Remote RMI proxy | Đại diện cho đối tượng/dịch vụ qua mạng | Giao thức RMI hoặc abstraction khác |

Một MBean proxy có thể được Spring AOP bọc tiếp, nhưng đừng suy luận rằng `MBeanProxyFactoryBean` tự cấp transaction hoặc authorization cho operation JMX.

Nếu target bean được Spring AOP proxy trước khi export, MBeanServer có thể nhìn thấy metadata khác tùy cách exporter xử lý proxy. Luôn kiểm tra giao diện thực đã đăng ký.

## 14. ObjectName và tên bean trong Spring

Spring bean name, ví dụ `workerAdminProxyFactory`, không phải ObjectName.

```text
Spring bean name: workerAdminProxyFactory
JMX ObjectName:   com.example.jobs:type=WorkerManager,name=background
```

`MBeanProxyFactoryBean` cần ObjectName của **MBean ở server**, chứ không phải tên bean Java trong ApplicationContext.

Nếu nhiều target cùng loại:

```text
com.example.jobs:type=WorkerManager,name=background
com.example.jobs:type=WorkerManager,name=interactive
```

có thể tạo hai proxy, cùng Java interface nhưng khác `ObjectName`. Lúc inject cần dùng bean names hoặc qualifier để phân biệt.

Một ObjectName ổn định giúp client không phụ thuộc tên lớp server hoặc proxy Spring runtime. Không nên đặt `type` dựa trên tên proxy class thay đổi theo AOP.

## 15. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `InstanceNotFoundException` | Target MBean chưa đăng ký hoặc sai ObjectName | `isRegistered`, `queryNames`, server thực |
| Proxy bean không được tạo | Thiếu `proxyInterface` hoặc cấu hình sai | Bean definition, type, initialization log |
| Inject interface không tìm thấy bean | Spring không expose type kỳ vọng hoặc sai qualifier | FactoryBean product type, bean name |
| Attribute không đọc được | Getter không được export hoặc read permission thiếu | `MBeanInfo.getAttributes()` |
| `AttributeNotFoundException` | Tên attribute khác quy ước method | So sánh attribute name trong metadata |
| `ReflectionException` | Operation thiếu hoặc signature không khớp | `MBeanInfo.getOperations()` |
| `MBeanException` | Logic MBean ném lỗi | Root cause, log của resource |
| Proxy call thành công nhưng trạng thái không đổi | Method chỉ thay cờ chưa áp dụng resource | Implementation thực của target |
| Local ổn, remote lỗi | Kết nối mạng, TLS, auth, RMI endpoint | Test connection rồi metadata |
| Client lỗi deserialize | Kiểu trả về không tương thích client classpath | MXBean/Open Types hoặc kiểu đơn giản |
| Method Java thêm mới nhưng proxy lỗi | Interface client mới hơn target MBean | Đồng bộ version và contract |
| Cùng interface nhưng gọi nhầm MBean | `ObjectName` trỏ resource khác | Log canonical name và target |

### Chẩn đoán có hệ thống

1. Xác nhận kết nối đúng `MBeanServerConnection`.
2. Kiểm tra target `ObjectName` được đăng ký.
3. Đọc `MBeanInfo` để xác nhận attribute và operation.
4. Kiểm tra proxy interface và chữ ký method.
5. Thử đọc attribute chỉ đọc trước khi gọi operation có side effect.
6. Xem exception gốc và Spring initialization log.
7. Nếu remote, kiểm tra connector/security/serialization.
8. Nếu lỗi sau nâng cấp, so sánh hợp đồng server và interface client.

## 16. Những giới hạn quan trọng của typed proxy

### 16.1. Proxy không biến JMX thành lời gọi Java trực tiếp

Dù syntax `workerAdmin.pause()` giống gọi object, lời gọi vẫn đi qua MBeanServerConnection. Có thể phát sinh exception runtime và chi phí quản trị JMX.

### 16.2. Type safety chỉ ở phía client

Compiler đảm bảo caller truyền đúng kiểu theo interface. Nhưng nếu server đăng ký một MBean khác hợp đồng, lỗi vẫn xuất hiện khi gọi.

### 16.3. Proxy không tự tạo MBean

`MBeanProxyFactoryBean` tạo **client** cho một MBean đã đăng ký. Việc export/register MBean là trách nhiệm khác, thường do `MBeanExporter`, `AnnotationMBeanExporter` hoặc code JMX trực tiếp.

### 16.4. Proxy không tự xử lý business concurrency

Nếu nhiều client gọi `pause()`, `resetStatistics()`, `rebuildIndex()`, target phải bảo đảm operation an toàn. Type-safe method invocation không đồng nghĩa idempotent hoặc thread-safe.

### 16.5. Proxy không thay authorization

Quyền kết nối JMX, access control và kiểm soát nghiệp vụ vẫn áp dụng. Một method có mặt trong interface không bảo đảm caller được phép gọi.

### 16.6. Proxy không loại bỏ chi phí remote

Với remote JMX, network latency, timeout, retry và khả năng kết nối gián đoạn ảnh hưởng đến mỗi lời gọi. Không nên dùng proxy remote cho method được gọi với tần suất cực cao trong luồng xử lý request nghiệp vụ.

## 17. Thiết kế interface proxy bền vững

Một hợp đồng proxy tốt:

```java
public interface PaymentQueueAdmin {
    long getPendingCount();
    boolean isProcessingEnabled();
    void pauseProcessing();
    void resumeProcessing();
}
```

Các đặc tính nên có:

- **Tên method rõ ràng:** tránh một method `execute()` mơ hồ.
- **Kiểu tham số đơn giản:** `String`, primitive, wrapper hoặc MXBean-compatible types khi cần remote.
- **Getter ít tác dụng phụ:** phù hợp polling và diagnostics.
- **Operation có mục tiêu trạng thái:** `pause`/`resume` dễ retry hơn `toggle`.
- **Hợp đồng phiên bản ổn định:** thay tên hoặc kiểu method cần đánh giá consumer.
- **Mục tiêu ObjectName rõ ràng:** đặt trong config và không phát sinh từ runtime proxy class.
- **Không expose cả service API:** chỉ method quản trị thực sự cần.

### Khi API đổi phiên bản

Nếu server xóa `pauseProcessing()` và thay bằng `setProcessingEnabled(boolean)`, proxy client cũ sẽ lỗi. Nên coi việc thay hợp đồng MBean là breaking change trừ khi có cơ chế tương thích rõ.

Một cách triển khai chuyển tiếp là duy trì operation cũ tạm thời hoặc dùng ObjectName versioned cho API mới. Tùy quy mô hệ thống, cũng có thể thêm integration test giữa server MBean metadata và proxy interface.

## 18. Unit test caller bằng mock proxy interface

Một lợi ích quan trọng của typed proxy là caller không phụ thuộc vào cơ chế JMX khi unit test.

```java
public class FakeWorkerAdmin implements WorkerAdmin {
    private boolean paused;

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public int getActiveWorkers() {
        return paused ? 0 : 4;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
```

Caller test:

```java
WorkerAdmin admin = new FakeWorkerAdmin();
OperationsController controller = new OperationsController(admin);

controller.ensurePaused();

assert admin.isPaused();
```

Unit test này không cần JMX hoặc Spring context. Nó chỉ xác nhận logic của caller theo hợp đồng Java.

Ngược lại, cần **integration test riêng** để xác nhận proxy factory thực sự gọi đúng MBean qua MBeanServer.

## 19. Integration test local với MBeanServer

Một bài test nên tạo MBeanServer tách biệt và đăng ký target MBean trong đó:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.createMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerManager,name=background"
);

server.registerMBean(new WorkerManager(), name);
```

Sau đó khởi tạo `MBeanProxyFactoryBean` trỏ tới `server` và interface `WorkerAdmin`.

Ví dụ minh họa ngoài Spring container:

```java
import org.springframework.jmx.access.MBeanProxyFactoryBean;

MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
factory.setServer(server);
factory.setObjectName(
    "com.example.jobs:type=WorkerManager,name=background"
);
factory.setProxyInterface(WorkerAdmin.class);

factory.afterPropertiesSet();

WorkerAdmin proxy = (WorkerAdmin) factory.getObject();
proxy.pause();

assert proxy.isPaused();
```

Ở cuối test, hủy đăng ký MBean và giải phóng MBeanServer nếu test quản lý lifecycle đó. Khi test chạy nhiều lần, dùng ObjectName không xung đột với test khác.

**Điểm kiểm tra:** proxy có thể gọi getter và operation đúng metadata. Đây mới là bằng chứng kết nối typed client và MBean target hoạt động thực tế.

## 20. FactoryBean và vòng đời khởi tạo

`MBeanProxyFactoryBean` là thành phần được Spring container khởi tạo trong lifecycle của context.

Những điều cần chú ý:

1. Target MBean phải có trên server khi proxy cần gọi.
2. ObjectName phải hợp lệ.
3. Interface được khai báo phải là interface Java phù hợp.
4. Nếu server MBean bị replace hoặc unregister, proxy có thể gặp lỗi cho đến khi target xuất hiện lại.
5. Khi đóng context, các connection remote do factory khác tạo cần được đóng/giải phóng.
6. Có thể cần khai báo quan hệ khởi tạo nếu exporter và proxy cùng nằm trong một context nhưng có dependency order không được đảm bảo.

### Nếu exporter và proxy cùng một ApplicationContext

Khi cần đảm bảo exporter đăng ký MBean trước proxy, có thể dùng dependency rõ ràng, ví dụ quan hệ `@DependsOn` giữa bean factory và exporter. Tuy nhiên, cần đặt đúng bean name và chú ý vòng đời `FactoryBean`; kiểm tra integration thực thay vì giả định order tạo bean ngẫu nhiên sẽ luôn đúng.

## 21. Local proxy không phải bản sao của MBean

Một proxy local không lưu một bản sao độc lập của MBean. Nó đại diện cho một ObjectName/connection:

```text
Proxy A -> ObjectName X -> Current MBean at X
Proxy B -> ObjectName X -> Current MBean at X
```

Hai proxy khác nhau có thể tác động tới cùng resource. Khi MBean được thay thế dưới ObjectName X, proxy có thể tiếp tục gọi vào MBean mới nếu hợp đồng còn tương thích.

Vì vậy:

- Tránh dùng proxy như snapshot state.
- Không coi proxy identity bằng resource identity bất biến.
- Khi cần snapshot, gọi getter và lưu dữ liệu kết quả một cách có chủ đích.
- Khi cần phát hiện thay MBean, có thể quan sát registration hoặc attribute version nếu hệ thống hỗ trợ.

## 22. Ví dụ thực tế: dùng proxy để điều khiển queue

Giả sử hệ thống có MBean:

```text
com.example.orders:type=PaymentQueue,name=primary
```

Giao diện typed:

```java
public interface PaymentQueueControl {
    long getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
```

Một Spring service sử dụng proxy:

```java
public class QueueSupervisor {
    private final PaymentQueueControl queue;

    public QueueSupervisor(PaymentQueueControl queue) {
        this.queue = queue;
    }

    public void pauseWhenBacklogTooHigh(long threshold) {
        if (queue.getPendingCount() > threshold) {
            queue.pause();
        }
    }
}
```

Đoạn code giúp minh họa cách dependency vào interface làm đơn giản caller. Tuy nhiên, việc **tự động pause hệ thống khi backlog cao** có thể khiến hàng đợi càng tăng; đây chỉ là ví dụ cú pháp, không phải chính sách vận hành được khuyến nghị. Trong production, logic điều khiển cần được thiết kế theo metric, capacity và quy trình vận hành thích hợp.

## 23. Checklist triển khai MBeanProxyFactoryBean

Trước khi đưa typed proxy vào ứng dụng:

1. **Đã đăng ký target MBean?** Dùng `isRegistered(ObjectName)`.
2. **Đúng MBeanServer?** Proxy và exporter trỏ tới cùng server (hoặc connection remote tới server đích).
3. **ObjectName ổn định?** Dùng đầy đủ domain và key properties.
4. **Interface phù hợp?** Getter, setter, operation khớp MBeanInfo.
5. **Kiểu dữ liệu tương thích?** Đặc biệt với remote client.
6. **Thứ tự khởi tạo ổn?** Target có sẵn khi proxy bắt đầu tương tác.
7. **Có nhiều proxy cùng interface?** Dùng bean name/qualifier rõ ràng.
8. **Có quản lý lỗi runtime?** Lỗi target, network, security và MBean exception.
9. **Operation có an toàn?** Không nhầm typed invocation với idempotency.
10. **Có integration test?** Test toàn bộ đường proxy → MBeanServer → target.
11. **Tách local/remote config?** ObjectName giữ ổn định, transport cấu hình riêng.
12. **Bảo mật phù hợp?** Remote JMX cần authentication, TLS và giới hạn mạng.

## 24. Câu hỏi tự kiểm tra

**1. MBeanProxyFactoryBean tạo ra MBean hay tạo client cho MBean?**

Nó tạo **client proxy** để gọi một MBean đã được đăng ký. Exporter hoặc mã JMX khác chịu trách nhiệm đăng ký target.

**2. Tại sao cần proxyInterface?**

Để Spring tạo object thực thi một Java interface, giúp caller gọi method typed và giảm phụ thuộc vào API JMX.

**3. Proxy typed có bảo đảm method tồn tại trên server không?**

Không tuyệt đối. Compiler kiểm tra interface phía client; MBean thực tế vẫn phải công bố metadata tương thích.

**4. Local proxy có đi qua MBeanServer không?**

Có. Nó chuyển lời gọi qua MBeanServerConnection, không nhất thiết gọi trực tiếp vào Java resource.

**5. Spring bean name có phải ObjectName không?**

Không. Bean name là định danh trong ApplicationContext; ObjectName là định danh MBean trong registry JMX.

**6. Khi server-side thay ObjectName, điều gì xảy ra?**

Client proxy dùng tên cũ có thể gặp `InstanceNotFoundException` hoặc lỗi tương ứng cho đến khi cấu hình được cập nhật.

**7. Dùng proxy typed có thay authentication hay authorization không?**

Không. Quyền truy cập JMX và kiểm soát nghiệp vụ vẫn được áp dụng.

**8. Khi nào nên chọn API JMX trực tiếp?**

Khi client cần khám phá MBean động, đọc metadata đa dạng hoặc không có interface ổn định.

## 25. Tổng kết

**`MBeanProxyFactoryBean`** của Spring Framework giúp biến thao tác JMX thành các lời gọi qua **Java interface typed**, làm code caller dễ đọc, dễ test và ít gắn với `ObjectName`, `MBeanServerConnection` hoặc chuỗi tên operation.

Ba cấu hình quan trọng là:

```text
server         -> MBeanServerConnection chứa MBean mục tiêu
objectName     -> tên đầy đủ của MBean đã đăng ký
proxyInterface -> hợp đồng Java mà caller sử dụng
```

Local proxy phù hợp khi các thành phần trong cùng JVM cần gọi giao diện quản trị JMX một cách có cấu trúc. Tuy nhiên, proxy không tự tạo MBean, không bảo đảm metadata server luôn tương thích với interface client và không thay thế bảo mật hoặc kiểm soát concurrency của operation.

**Cách kiểm chứng đáng tin cậy nhất** là một integration test đăng ký MBean cụ thể, cấu hình `MBeanProxyFactoryBean` trỏ tới đúng ObjectName rồi xác nhận getter và operation thực hiện qua proxy đúng như mong đợi.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — JMX proxy: https://docs.spring.io/spring-framework/reference/integration/jmx/proxy.html
- Spring Framework API — `MBeanProxyFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — `MBeanServerConnectionFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerConnectionFactoryBean.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
