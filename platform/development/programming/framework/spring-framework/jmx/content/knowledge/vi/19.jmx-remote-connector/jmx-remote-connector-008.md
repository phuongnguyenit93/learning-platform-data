# Khác biệt giữa local ObjectName và server từ xa trong Spring Framework JMX

## Mục tiêu

Bài học thuộc **Spring Framework JMX → Remote connector**. Sau bài này, bạn có thể:

- Giải thích tại sao `ObjectName` không phải địa chỉ mạng hay định danh toàn cục của MBean.
- Phân biệt tên quản trị trong **MBeanServer local** và `MBeanServerConnection` lấy qua **remote JMX connector**.
- Hiểu chính xác sự kết hợp giữa **JMX endpoint**, **ObjectName** và **MBeanServer** để chọn đúng MBean.
- Thực hành đăng ký MBean trong Spring, kết nối từ xa bằng `JMXConnector` và gọi attribute/operation.
- Chẩn đoán các lỗi như kết nối nhầm JVM, `InstanceNotFoundException`, trùng tên và cấu hình RMI endpoint.
- Thiết kế client tránh thao tác lên nhầm môi trường, đồng thời bảo vệ cổng quản trị JMX.

## 1. Hai lớp định danh: kết nối và ObjectName

Trong JMX, `javax.management.ObjectName` có dạng:

```text
domain:key=value[,key=value...]
```

Ví dụ:

```text
com.example.orders:type=Queue,name=Payment
```

Tên này nhận diện một MBean **bên trong một MBeanServer cụ thể**. Nó không chứa IP, port hay thông tin JVM.

Một client kết nối qua remote JMX cần hai thứ:

1. **Endpoint / kết nối** chỉ tới JVM hoặc MBeanServer đích.
2. **ObjectName** chỉ tới MBean cụ thể bên trong MBeanServer mà endpoint đó phục vụ.

```text
Local process A                          Remote process B
+-----------------------+                +-----------------------+
| MBeanServer A         |                | MBeanServer B         |
| com.example.orders:   |                | com.example.orders:   |
| type=Queue,           |                | type=Queue,           |
| name=Payment          |                | name=Payment          |
+-----------+-----------+                +-----------+-----------+
            ^                                        ^
            | local MBeanServerConnection             | remote JMXConnector
            |                                        |
            +----------------- Client ----------------+
```

Hai process có thể đăng ký **cùng ObjectName** mà không xung đột. Tuy vậy, trạng thái chúng quản lý có thể khác nhau hoàn toàn. Nếu một client dùng sai connection nhưng đúng ObjectName, nó có thể đọc hoặc điều khiển **MBean của JVM khác**.

Công thức nhận diện hữu ích:

```text
JMX resource identity =
    (endpoint / target MBeanServer identity, ObjectName)
```

Trong hệ thống giám sát nhiều JVM, cần thêm nhận diện môi trường, cụm, instance hoặc service để tránh nhầm endpoint.

## 2. Local ObjectName không đồng nghĩa local JVM

“Local” có thể nói tới hai khía cạnh:

- **Local object name:** chuỗi `ObjectName` được tạo trong code, ví dụ `new ObjectName("com.example:type=Queue")`.
- **Local JMX access:** lời gọi trực tiếp tới một `MBeanServer` trong cùng JVM, ví dụ `ManagementFactory.getPlatformMBeanServer()`.

Tạo `ObjectName` ở máy client:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

không có nghĩa MBean tồn tại trên máy client. `ObjectName` chỉ là **giá trị mô tả danh tính**, chưa gắn với server nào.

Để đọc MBean local:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

if (server.isRegistered(name)) {
    Object pending = server.getAttribute(name, "PendingCount");
    System.out.println(pending);
}
```

`server` trong đoạn code là registry của JVM nơi code đang chạy. Nếu MBean chỉ tồn tại ở JVM khác, `isRegistered(name)` trên server local sẽ là `false` dù chuỗi ObjectName hoàn toàn hợp lệ.

## 3. Local MBeanServer và MBeanServerConnection từ xa

JMX có hai interface quan trọng:

- `MBeanServer`: quản lý registry và MBean trong JVM, có khả năng đăng ký/hủy đăng ký MBean.
- `MBeanServerConnection`: interface client sử dụng để query, đọc/ghi attribute và gọi operation. Nó có thể được triển khai bởi local `MBeanServer` hoặc một proxy kết nối từ xa.

Cả hai đường đều dùng các thao tác tương tự:

```java
connection.isRegistered(name);
connection.getMBeanInfo(name);
connection.getAttribute(name, "PendingCount");
connection.invoke(name, "resetStatistics", new Object[0], new String[0]);
```

Vì vậy, code client có thể làm việc với abstraction `MBeanServerConnection`:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class QueueJmxClient {
    private final MBeanServerConnection connection;
    private final ObjectName name;

    public QueueJmxClient(
            MBeanServerConnection connection,
            ObjectName name) {
        this.connection = connection;
        this.name = name;
    }

    public int pendingCount() throws Exception {
        return (Integer) connection.getAttribute(name, "PendingCount");
    }

    public void resetStatistics() throws Exception {
        connection.invoke(
            name,
            "resetStatistics",
            new Object[0],
            new String[0]
        );
    }
}
```

Thay connection bằng local hoặc remote mà không cần đổi logic truy xuất MBean. **Sự khác nhau thực tế nằm ở server mà connection dẫn tới, quyền truy cập, vận chuyển dữ liệu và khả năng lỗi mạng**.

## 4. Ví dụ hai JVM có cùng ObjectName

Giả sử:

```text
JVM A (staging)
  Endpoint: service:jmx:rmi:///jndi/rmi://staging.example.internal:9010/jmxrmi
  ObjectName: com.example.orders:type=Queue,name=Payment
  PendingCount: 12

JVM B (production)
  Endpoint: service:jmx:rmi:///jndi/rmi://prod.example.internal:9010/jmxrmi
  ObjectName: com.example.orders:type=Queue,name=Payment
  PendingCount: 350
```

Hai tên `ObjectName` là bằng nhau về danh tính **trong cấu trúc tên**, nhưng không phải cùng MBean, vì registry/endpoint khác nhau.

```java
ObjectName stagingName = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName productionName = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

System.out.println(stagingName.equals(productionName)); // true
```

Kết quả `true` **không chứng minh hai đối tượng JMX giống nhau**. Nó chỉ chứng minh hai giá trị ObjectName có cùng domain và các key properties.

Với automation hoặc dashboard nhiều môi trường, nên lưu thêm:

```text
environment = staging / production
service     = order-processing
target      = host / pod / JVM instance
objectName  = com.example.orders:type=Queue,name=Payment
```

Không sử dụng chỉ mỗi ObjectName làm khóa dữ liệu cho một hệ thống tổng hợp đa JVM.

## 5. Spring xuất MBean vào server nào?

Spring cung cấp `MBeanExporter` để đăng ký bean với `MBeanServer`.

Ví dụ Standard MBean:

```java
package com.example.orders.jmx;

public interface PaymentQueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}
```

```java
package com.example.orders.jmx;

public class PaymentQueueMonitor
        implements PaymentQueueMonitorMBean {
    private int pendingCount = 10;

    @Override
    public synchronized int getPendingCount() {
        return pendingCount;
    }

    @Override
    public synchronized void resetStatistics() {
        pendingCount = 0;
    }
}
```

Cấu hình Spring:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {
    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            PaymentQueueMonitor monitor,
            MBeanServer platformMBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Payment",
            monitor
        ));
        return exporter;
    }
}
```

Cấu hình này đăng ký MBean vào **platform MBeanServer của JVM đang chạy ứng dụng**. Nó chưa tự tạo remote JMX endpoint. Một client từ xa chỉ truy cập được khi JVM hoặc ứng dụng có JMX connector phù hợp, được bảo vệ và kết nối tới đúng server này.

Nếu Spring exporter được cấu hình dùng MBeanServer tùy biến, endpoint mặc định của platform server có thể **không** thấy MBean. Điều quan trọng là exporter và client phải hướng vào **cùng registry**, không chỉ dùng cùng ObjectName.

## 6. Kết nối remote JMX bằng JMXConnector

Java cung cấp `javax.management.remote.JMXConnectorFactory` để tạo kết nối tới remote JMX endpoint.

Ví dụ URL dạng RMI:

```text
service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi
```

Code kết nối:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteQueueReader {
    public static void main(String[] args) throws Exception {
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

            if (!connection.isRegistered(name)) {
                throw new IllegalStateException(
                    "MBean not registered at selected endpoint: " + name
                );
            }

            Object pending =
                connection.getAttribute(name, "PendingCount");

            System.out.println("PendingCount = " + pending);
        }
    }
}
```

`JMXConnector` là tài nguyên phải được đóng để giải phóng kết nối. Nếu endpoint cần credentials hoặc TLS, hãy truyền cấu hình bảo mật thích hợp qua environment map và connector provider.

**Quan trọng:** `ObjectName` trong đoạn code không khác khi dùng local hay remote; chỉ đối tượng `MBeanServerConnection` dẫn tới registry khác.

## 7. Cấu hình thử nghiệm remote JMX trên JVM

Khi cần lab local, một JVM Java thường có thể được khởi chạy với các system properties quản trị JMX:

```bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -jar order-service.jar
```

Cấu hình này chỉ dành cho **máy thử nghiệm cô lập**. `authenticate=false` và `ssl=false` không phù hợp để phơi bày một endpoint quản trị trong mạng không tin cậy.

Trong production:

- Bật cơ chế xác thực và kiểm soát quyền truy cập.
- Sử dụng TLS và quản lý certificate phù hợp.
- Giới hạn kết nối ở private network, VPN hoặc tunnel bảo mật.
- Không để cổng JMX public trên Internet.
- Theo dõi audit/log đối với operation có tác động nghiệp vụ.
- Không đưa credentials trực tiếp vào source code hoặc URL log.

Một RMI-based connector có thể liên quan tới cổng JNDI registry, cổng RMI server và hostname được quảng bá trong stub. Cổng TCP mở không đồng nghĩa kết nối JMX end-to-end thành công; hãy kiểm tra port/hostname/firewall và network namespace của container.

`127.0.0.1` chỉ phù hợp với kết nối cùng máy hoặc tunnel được cấu hình đúng, không phải hostname public cho remote clients.

## 8. Cùng tên nhưng không cùng kết nối

Hãy xét code:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

Ba khả năng:

### Trường hợp A: server local có MBean

```java
MBeanServerConnection local =
    ManagementFactory.getPlatformMBeanServer();

local.isRegistered(name); // true nếu đã đăng ký
```

### Trường hợp B: remote server không có MBean

```java
MBeanServerConnection remote =
    connector.getMBeanServerConnection();

remote.isRegistered(name); // false nếu chưa đăng ký ở remote registry
```

### Trường hợp C: remote server có MBean khác cùng tên

```java
remote.isRegistered(name); // true
```

Nhưng trường hợp C chưa chứng minh giá trị attribute hay implementation giống trường hợp A. Vì vậy, khi phân tích lỗi, luôn ghi lại **endpoint đích và canonical ObjectName**.

Một lời gọi trực tiếp từ server local không tự tìm MBean trên server remote; tương tự, một remote client không tự tìm tất cả MBean trong mọi JVM có cùng ObjectName.

## 9. Sự khác biệt giữa local proxy và remote proxy trong Spring

Spring có các lớp hỗ trợ truy cập MBean như `MBeanProxyFactoryBean` và `MBeanClientInterceptor`. Proxy dựa trên interface có thể tạo trải nghiệm gọi method Java thay vì viết `getAttribute`/`invoke`.

Với **local proxy**, bạn có thể cấu hình `MBeanServerConnection` là chính `MBeanServer` trong JVM. Khi đó không có network hop.

Với **remote proxy**, Spring client phải có kết nối tới `MBeanServerConnection` từ xa, thường qua cấu hình JMX service URL hoặc connector tương ứng.

Tư duy:

```text
Local proxy
  -> MBeanServerConnection = local MBeanServer
  -> ObjectName

Remote proxy
  -> MBeanServerConnection = remote connection
  -> ObjectName
```

Nếu interface Java giống nhau và metadata MBean tương thích, client có thể gọi những method giống nhau. Nhưng remote proxy có thêm các đặc điểm:

- Độ trễ mạng và kết nối có thể bị gián đoạn.
- Authentication/authorization hoặc TLS có thể khiến lời gọi thất bại.
- Các tham số và giá trị trả về cần phù hợp với khả năng serialization/class loading.
- Invocation có thể timeout hoặc mất kết nối ở thời điểm kết quả chưa được trả về.
- Retry một operation có side effect có thể gây **thực thi lặp** nếu không có idempotency.

Không giả định rằng remote call an toàn để retry chỉ vì syntax giống local method call.

## 10. MBeanServer tùy biến và remote connector

Một JVM có thể chứa nhiều MBeanServer:

```text
JVM
  |
  +-- Platform MBeanServer
  |    +-- java.lang:*
  |    +-- com.example.orders:type=Queue,name=Payment
  |
  +-- Custom MBeanServer
       +-- com.example.orders:type=Queue,name=Payment
```

Hai registry có thể chứa cùng ObjectName. Khi một connector phục vụ platform server, client không tự thấy MBean trên custom server.

Ví dụ tạo custom registry:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer custom =
    MBeanServerFactory.newMBeanServer("orders.management");
```

Nếu muốn remote client truy cập `custom`, cần cấu hình **connector server** phục vụ đúng `custom` và kiểm soát vòng đời của connector đó. Tạo `MBeanServer` riêng **không tự mở endpoint remote**.

Một mô hình Java JMX connector server tổng quát:

```java
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;
import java.util.Map;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

JMXConnectorServer connectorServer =
    JMXConnectorServerFactory.newJMXConnectorServer(
        url, Map.of(), custom
    );

// Cần RMI registry và chính sách mạng/bảo mật tương ứng.
// connectorServer.start();
```

Đây là khung cấu hình minh họa, **không phải cấu hình production có thể chạy nguyên xi**: cần chuẩn bị RMI registry/binding, network ports, authentication, TLS, credentials và cleanup theo môi trường. Không bật connector server không bảo vệ chỉ để “thấy được” MBean.

## 11. Kiểm tra đúng MBean trước khi gọi operation

Một chiến lược client an toàn là kiểm tra target:

```java
MBeanServerConnection connection = /* local hoặc remote */;
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

if (!connection.isRegistered(name)) {
    throw new IllegalStateException(
        "Missing expected MBean at selected endpoint"
    );
}

var info = connection.getMBeanInfo(name);
System.out.println("MBean class = " + info.getClassName());
System.out.println("MBean description = " + info.getDescription());
```

Ngoài ra có thể xác minh các thuộc tính giúp nhận diện instance, chẳng hạn `ApplicationName`, `Environment` hoặc `InstanceId` nếu MBean đó công bố. Những giá trị này nên do ứng dụng kiểm soát và tránh chứa secrets.

Ví dụ:

```java
String application = (String) connection.getAttribute(
    name, "ApplicationName"
);

if (!"order-service".equals(application)) {
    throw new IllegalStateException("Unexpected application target");
}
```

**Đối với operation thay đổi trạng thái**, đặc biệt như `clearCache`, `pauseProcessing`, `shutdown` hoặc `rebuildIndex`, nên xác minh cả endpoint/environment/instance và exact ObjectName trước khi gọi.

Không dựa vào `MBeanInfo.getClassName()` một mình để kết luận đúng ứng dụng: các JVM khác nhau có thể chạy cùng class và cùng metadata.

## 12. Lỗi phổ biến khi truy cập remote JMX

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `isRegistered(name)` false | Client đang dùng nhầm endpoint hoặc MBean chưa đăng ký | In endpoint + ObjectName; query domain trên server đích |
| `InstanceNotFoundException` | ObjectName không tồn tại trên connection hiện tại, hoặc đã bị unregister | Kiểm tra server/registry và lifecycle |
| Kết nối thành công nhưng không thấy app MBeans | Exporter dùng custom server, connector phục vụ server khác | Kiểm tra `setServer` và connector server binding |
| Đọc được MBean nhưng giá trị “sai” | Kết nối tới replica/staging khác với mục tiêu | Xác minh environment và instance identity |
| `IOException` hoặc kết nối đứt | Mạng, connector, timeout, server shutdown | Kiểm tra transport và trạng thái endpoint |
| Lỗi RMI khi registry port mở | Host/port được quảng bá trong RMI stub không tới được | Kiểm tra `java.rmi.server.hostname`, RMI port, firewall |
| Lỗi credentials/TLS | Cấu hình bảo mật hai đầu không tương thích | Kiểm tra access configuration, certificate |
| `ReflectionException` khi invoke | Operation name/signature không đúng | Đọc `MBeanOperationInfo.getSignature()` |
| Serialization/classloading error | Kiểu tham số/giá trị trả về không khả dụng với client | Dùng kiểu đơn giản, MXBean/Open Data khi phù hợp |
| Script gọi nhầm production | Endpoint không được xác minh độc lập trước operation | Dùng cấu hình môi trường riêng và guardrails |

### Quy trình debug ngắn

1. Xác minh endpoint/target và môi trường.
2. Thiết lập kết nối JMX thành công.
3. Query `getDefaultDomain()` hoặc `getDomains()` để định hướng nhưng không dùng chúng làm bằng chứng duy nhất.
4. Query exact ObjectName qua `isRegistered()`.
5. Đọc `getMBeanInfo()` và attribute nhận diện application.
6. Chỉ sau đó mới đọc dữ liệu vận hành hoặc invoke operation cần thiết.

## 13. Query MBean từ xa bằng ObjectName pattern

JMX hỗ trợ truy vấn danh sách MBean cùng domain:

```java
ObjectName pattern = new ObjectName(
    "com.example.orders:type=Queue,*"
);

for (ObjectName found : connection.queryNames(pattern, null)) {
    System.out.println(found.getCanonicalName());
}
```

`queryNames` chỉ quét MBean trên **server mà connection đang trỏ tới**; nó không tự tìm ở các JVM hoặc endpoint khác.

Một pattern như `com.example.orders:*` có thể giúp tìm tất cả resource trong domain, nhưng không nên tự động gọi action lên mọi kết quả mà chưa lọc loại resource và instance. Với thao tác quan trọng, dùng exact ObjectName.

Một ObjectName pattern dùng để query khác với ObjectName concrete dùng để đăng ký resource. Có thể kiểm tra:

```java
System.out.println(pattern.isPattern()); // true
```

## 14. Kiểm thử local và remote theo các lớp

Có thể tổ chức ba lớp test:

### Unit test: ObjectName và client abstraction

Dùng mock `MBeanServerConnection` để xác nhận client gọi `getAttribute`, `invoke` đúng tên, đồng thời không gọi operation khi target validation thất bại.

### Integration test local: MBeanServer thật

Tạo server test cách ly:

```java
MBeanServer server =
    javax.management.MBeanServerFactory.newMBeanServer(
        "test.management"
    );
```

Đăng ký một Standard MBean rồi inject server cho client như `MBeanServerConnection`. Test này xác minh hợp đồng MBean, metadata và invocation trong JVM mà không cần socket.

### Integration test remote: JMXConnector thật

Khởi chạy một connector phục vụ server test với port/registry phù hợp, dùng `JMXConnectorFactory.connect` lấy `MBeanServerConnection`, rồi xác minh đối tượng được đọc đúng và connector đóng sạch.

Không đánh đồng ba lớp này: local test không kiểm tra network, TLS hoặc serialization liên JVM. Ngược lại, một remote connection thành công không chứng minh client dùng đúng ObjectName hoặc đúng application instance.

## 15. Kiểm thử hai server có cùng ObjectName

Ví dụ thuần Java:

```java
import javax.management.*;

MBeanServer first =
    MBeanServerFactory.newMBeanServer("first.management");
MBeanServer second =
    MBeanServerFactory.newMBeanServer("second.management");

ObjectName shared = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

first.registerMBean(new PaymentQueueMonitor(), shared);
second.registerMBean(new PaymentQueueMonitor(), shared);

System.out.println(first.isRegistered(shared));  // true
System.out.println(second.isRegistered(shared)); // true
```

Hai server độc lập nên không xung đột tên. Nếu muốn kiểm tra state khác nhau, tạo hai implementation với giá trị `PendingCount` khác nhau và đọc qua từng `MBeanServerConnection`.

**Bài học:** sự bằng nhau của ObjectName không chứng minh hai object cùng tồn tại trong một registry hoặc cùng đại diện cho một tài nguyên logic.

## 16. Vòng đời, cache và stale connection

Trong hệ thống triển khai/redeploy:

- MBean có thể bị unregister rồi đăng ký lại cùng ObjectName.
- Remote connector có thể ngắt khi JVM restart, dù endpoint text được tái sử dụng.
- Một connection cache có thể vẫn trỏ tới phiên cũ hoặc bị hỏng.
- Client có thể nhận giá trị stale nếu nó tự cache metadata/trạng thái mà không làm mới.
- Khi load balancer/NAT/port-forward thay đổi target, endpoint logic có thể dẫn tới instance khác.

Client nên xử lý reconnect và xác minh target identity lại sau kết nối mới. **Không cache một giả định rằng ObjectName luôn thuộc cùng JVM mãi mãi.**

Đối với operation có side effect, việc lỗi mạng sau lời gọi gây một tình huống khó: operation có thể đã chạy nhưng phản hồi bị mất. Retry mù có thể gây chạy hai lần. Thiết kế operation idempotent hoặc có request ID/trạng thái công việc phù hợp.

## 17. Thiết kế quan sát nhiều JVM và Spring application

Một hệ thống nhiều node có thể dùng cùng ObjectName trên mọi replica:

```text
Replica 1 -> com.example.orders:type=Queue,name=Payment
Replica 2 -> com.example.orders:type=Queue,name=Payment
Replica 3 -> com.example.orders:type=Queue,name=Payment
```

Điều này hợp lệ và thường hữu ích vì hợp đồng JMX thống nhất. Collector phải gắn target identity:

```text
environment=prod
service=orders
instance=orders-1
objectName=com.example.orders:type=Queue,name=Payment
```

Khi tổng hợp metric, phân biệt:

- **Metric local per JVM:** heap, thread count, queue depth theo replica.
- **Metric của cluster:** chỉ có nếu MBean thực sự lấy dữ liệu tổng hợp từ cluster.
- **Control operation:** tác động local hay toàn cluster phải được mô tả rõ.

Không suy diễn rằng một operation ở một replica tự động điều khiển tất cả replica chỉ vì ObjectName giống nhau.

## 18. Bảo mật và khả năng vận hành

Remote JMX là giao diện quản trị có thể truy cập các operation nhạy cảm. Một ObjectName không bao giờ là token bảo mật và việc biết tên MBean không thay thế authentication.

Nguyên tắc:

1. Dùng endpoint quản trị chỉ truy cập được từ mạng tin cậy.
2. Bật authentication/authorization và TLS tương ứng với yêu cầu môi trường.
3. Giới hạn operation được export và validate tham số.
4. Không xuất dữ liệu nhạy cảm qua attributes, notifications hoặc operation results.
5. Đóng `JMXConnector` đúng cách.
6. Audit operation quan trọng và ghi nhận endpoint/instance được tác động.
7. Không sử dụng cùng một cấu hình endpoint mặc định cho staging và production nếu có nguy cơ thao tác nhầm.
8. Không coi `ObjectName`, domain hoặc remote connector address là ranh giới quyền truy cập đầy đủ.

## 19. Bài tập thực hành

1. Tạo hai `MBeanServer` trong cùng JVM, đăng ký hai MBean cùng ObjectName và chứng minh không có xung đột giữa hai server.
2. Tạo local `QueueJmxClient` dùng `ManagementFactory.getPlatformMBeanServer()` và đọc attribute `PendingCount`.
3. Kết nối remote bằng `JMXConnectorFactory.connect`, dùng **cùng ObjectName** để đọc MBean ở JVM khác.
4. Cố tình kết nối sai endpoint, ghi lại kết quả `isRegistered()` và phân tích vì sao tên hợp lệ vẫn không tìm thấy MBean.
5. Cấu hình Spring `MBeanExporter.setServer` dùng custom MBeanServer và giải thích tại sao connector mặc định không thấy MBean.
6. Viết client xác minh `ApplicationName` hoặc `InstanceId` trước khi gọi `resetStatistics()`.
7. Thử một operation bị lỗi mạng sau invocation trong môi trường test; thảo luận vì sao retry không kiểm soát có thể gây tác động lặp.
8. Xây thiết kế định danh cho collector nhiều JVM bằng cặp endpoint/target và ObjectName.

## 20. Câu hỏi tự kiểm tra

- `ObjectName` có chứa địa chỉ IP hoặc port của JVM không?
- Hai JVM có thể đăng ký cùng `ObjectName` mà không bị trùng không?
- Đối tượng nào quyết định client đang truy cập local hay remote MBeanServer?
- Vì sao `ObjectName.equals()` trả `true` không chứng minh hai MBean thuộc cùng instance?
- Tạo custom `MBeanServer` có tự tạo remote endpoint không?
- Nếu remote connection thành công nhưng `isRegistered(name)` false, cần kiểm tra những gì?
- Local proxy và remote proxy có thể dùng cùng interface quản trị không? Những rủi ro nào tăng khi chuyển sang remote?
- Vì sao phải xác minh target identity trước khi gọi operation có side effect?

**Ghi nhớ:** `ObjectName` là danh tính **bên trong một MBeanServer**, không phải địa chỉ hay khóa toàn cục của ứng dụng. Khi làm việc với remote JMX, hãy luôn xác định cả **endpoint/`MBeanServerConnection`** và **ObjectName**. Cùng một tên có thể tồn tại trên nhiều JVM hoặc nhiều server, nhưng chỉ connection đúng mới dẫn tới MBean mong muốn.