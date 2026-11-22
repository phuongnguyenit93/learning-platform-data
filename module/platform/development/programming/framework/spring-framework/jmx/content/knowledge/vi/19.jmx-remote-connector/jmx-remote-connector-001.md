# JSR-160 và mô hình kết nối JMX từ xa

## 1. Mục tiêu

Trong Java Management Extensions (JMX), \`MBeanServer\` quản lý các MBean nằm trong một JVM. Nếu công cụ quản trị chạy ở **JVM khác, máy khác hoặc một service giám sát riêng**, nó cần một cơ chế truy cập từ xa đến MBeanServer.

**JSR-160 (JMX Remote API)** xác định kiến trúc connector client/server và API Java dùng để thực hiện việc này. Những thành phần quan trọng gồm \`JMXConnectorServer\`, \`JMXConnector\`, \`JMXServiceURL\` và \`MBeanServerConnection\`.

Trong Spring Framework JMX, các bean có thể được \`MBeanExporter\` đăng ký vào MBeanServer. Một remote connector sẽ cung cấp **đường truy cập** đến các MBean ấy; nó không tự tạo MBean hoặc quyết định bean nào được export.

Sau bài học, bạn có thể:

1. Mô tả kiến trúc JMX remote theo JSR-160.
2. Phân biệt MBeanServer, connector server, connector client và JMX proxy.
3. Hiểu cấu trúc \`JMXServiceURL\` và cách RMI/JNDI thường được sử dụng.
4. Cấu hình, kết nối và đóng remote JMX connection bằng Java API.
5. Hiểu remote notification, connection lifecycle và giới hạn của giao nhận sự kiện.
6. Phân tích vấn đề network, port, NAT, TLS, authentication và authorization.
7. Kết hợp JMX remote connector với Spring \`MBeanExporter\` và tránh những hiểu lầm vận hành.

## 2. Kiến trúc tổng thể

\`\`\`text
  JVM A: ứng dụng Spring                     JVM B: JMX client
+--------------------------------+       +----------------------------------+
| Spring beans                   |       | JConsole / Java application      |
|     |                          |       |                                  |
|     v                          |       | JMXServiceURL                    |
| MBeanExporter                  |       |     |                            |
|     | register                 |       |     v                            |
|     v                          |       | JMXConnectorFactory.connect()    |
| MBeanServer                    |<----->| JMXConnector                     |
|     |                          |       |     |                            |
|     +-- java.lang:*            |       |     v                            |
|     +-- com.example:type=*     |       | MBeanServerConnection            |
|     |                          |       |     |                            |
|     v                          |       |     +-- queryNames()             |
| JMXConnectorServer             |       |     +-- getAttribute()           |
|     |                          |       |     +-- invoke()                 |
|     +-- RMI / connector        |       |     +-- addNotificationListener()|
+--------------------------------+       +----------------------------------+
\`\`\`

Đọc sơ đồ theo trách nhiệm:

- \`MBeanExporter\` xuất Spring beans thành MBeans.
- \`MBeanServer\` là registry/runtime cung cấp operations quản trị.
- \`JMXConnectorServer\` gắn một giao thức remote vào MBeanServer.
- \`JMXConnector\` ở phía client thiết lập và quản lý connection.
- \`MBeanServerConnection\` là API client dùng để truy vấn/điều khiển MBeans như khi làm việc với server local.
- \`JMXServiceURL\` mô tả điểm kết nối và giao thức.

**Điểm quan trọng:** JMX remote là **cơ chế transport và quản trị từ xa**, không phải cơ chế persistence, message broker hay HTTP REST API.

## 3. JSR-160 bổ sung gì cho JMX?

JMX nền tảng cung cấp:

- \`ObjectName\`: định danh MBean.
- \`MBeanServer\`: đăng ký, tìm kiếm, đọc/ghi attributes, gọi operations.
- Standard MBean, MXBean, Dynamic MBean.
- Notification broadcaster/listener.

JSR-160 bổ sung lớp **remote access** qua các connector APIs:

| API | Vai trò |
|---|---|
| \`JMXConnectorServer\` | Expose một MBeanServer qua connector protocol |
| \`JMXConnectorServerFactory\` | Tạo connector server từ URL, môi trường và MBeanServer |
| \`JMXConnector\` | Client-side connection tới remote server |
| \`JMXConnectorFactory\` | Tạo/kết nối connector client |
| \`JMXServiceURL\` | Địa chỉ và protocol của connector |
| \`MBeanServerConnection\` | API quản trị MBeans qua connection |
| \`JMXConnectionNotification\` | Báo các thay đổi ở vòng đời connector connection |
| \`JMXAuthenticator\` | Interface xác thực caller cho connector server |
| \`JMXPrincipal\` | Principal biểu diễn identity JMX trong ngữ cảnh phù hợp |

Java SE cung cấp một remote connector dựa trên **RMI**. JSR-160 cho phép kiến trúc connector với protocol provider khác, nhưng sự hỗ trợ cụ thể phụ thuộc implementation và classpath.

Không được giả định mọi URL tùy ý như \`service:jmx:http://...\` đều được Java SE hỗ trợ mặc định. Tên giao thức phải có connector provider tương ứng.

## 4. JMXServiceURL: hiểu đúng địa chỉ kết nối

Một \`JMXServiceURL\` tổng quát có cấu trúc dạng:

\`\`\`text
service:jmx:<protocol>://<host>[:<port>][/<url-path>]
\`\`\`

Với RMI, hai dạng thường gặp:

\`\`\`text
service:jmx:rmi:///jndi/rmi://host.example.com:9010/jmxrmi
\`\`\`

và dạng connector RMI trực tiếp theo cấu hình server:

\`\`\`text
service:jmx:rmi://host.example.com:port
\`\`\`

Dạng thứ nhất có hai khái niệm:

1. **RMI connector object** — đối tượng remote để client gọi JMX.
2. **JNDI/RMI registry** — vị trí để client lookup stub của connector.

Phần \`/jndi/rmi://host:9010/jmxrmi\` là nơi lookup stub qua registry. Nó không đảm bảo endpoint cuối cùng chỉ dùng đúng một TCP port.

### Vì sao “mở port 9010” đôi khi vẫn không kết nối được?

Trong nhiều cấu hình RMI, client:
- Kết nối RMI registry ở port được ghi trong URL.
- Nhận stub hoặc thông tin endpoint của RMI connector.
- Tiếp tục kết nối đến host/port mà stub quảng bá.

Nếu connector dùng một port động hoặc quảng bá IP/hostname không thể truy cập từ client, bước thứ hai có thể fail dù registry port mở.

Đây là nguyên nhân phổ biến của tình huống “telnet được registry nhưng JConsole vẫn timeout”.

## 5. Một ví dụ remote client bằng Java

\`\`\`java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteJmxClient {

    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            Set<ObjectName> names = connection.queryNames(
                new ObjectName("java.lang:*"),
                null
            );

            for (ObjectName name : names) {
                System.out.println(name.getCanonicalName());
            }

            ObjectName memory = new ObjectName(
                "java.lang:type=Memory"
            );

            Object heapUsage = connection.getAttribute(
                memory, "HeapMemoryUsage"
            );

            System.out.println(heapUsage);
        }
    }
}
\`\`\`

Đoạn này giả định một JMX connector server đã chạy tại địa chỉ trên. Nó không tự mở server hoặc cấu hình security.

\`try-with-resources\` gọi \`JMXConnector.close()\` khi xong. Đối với chương trình giám sát dài hạn, không nên tạo connection mới cho từng attribute read nếu có thể quản lý connection pooling/lifecycle phù hợp.

### Không nhầm với ManagementFactory trong client

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

trả về platform MBeanServer của **JVM đang chạy lệnh**. Khi gọi từ JVM client, đây là server của client, không phải server của ứng dụng remote.

Phải dùng:

\`\`\`java
MBeanServerConnection remote =
    connector.getMBeanServerConnection();
\`\`\`

để truy vấn remote server.

## 6. MBeanServerConnection: một API, hai môi trường

\`MBeanServerConnection\` cho phép client gọi các phương thức như:

- \`queryNames(ObjectName, QueryExp)\`.
- \`isRegistered(ObjectName)\`.
- \`getMBeanInfo(ObjectName)\`.
- \`getAttribute(ObjectName, String)\`.
- \`setAttribute(ObjectName, Attribute)\`.
- \`invoke(ObjectName, String, Object[], String[])\`.
- \`addNotificationListener(...)\`.
- \`removeNotificationListener(...)\`.

Ví dụ:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Orders"
);

boolean exists = connection.isRegistered(name);

if (exists) {
    Object depth = connection.getAttribute(
        name, "PendingCount"
    );
    System.out.println("Pending: " + depth);
}
\`\`\`

Vì cùng một interface áp dụng cho local/remote access, code quản trị có thể dùng abstraction chung. Tuy nhiên **ngữ nghĩa lỗi** ở remote phức tạp hơn local:

- Network failure hoặc connection timeout.
- Authentication failure.
- Class serialization/deserialization issues.
- MBean unregister trong lúc thực hiện.
- Chậm response hoặc server overload.
- Quyền truy cập không đủ.

Do đó, không thiết kế một remote JMX call như lời gọi getter Java local không thể fail.

## 7. Remote connector server: ví dụ cấu hình programmatic

Có thể tạo một RMI connector server gắn với một \`MBeanServer\` qua JMX APIs.

Ví dụ minh họa trong môi trường thử nghiệm:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.rmi.registry.LocateRegistry;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

public final class LocalRmiJmxServer {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        // Registry phục vụ lookup RMI connector stub.
        LocateRegistry.createRegistry(9010);

        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        JMXConnectorServer connector =
            JMXConnectorServerFactory.newJMXConnectorServer(
                url,
                null,
                server
            );

        connector.start();

        System.out.println(
            "JMX connector listening: " + connector.getAddress()
        );

        // Trong ứng dụng thật: quản lý lifecycle và gọi stop()
        // khi đóng ứng dụng; không kết thúc JVM ngay sau start().
    }
}
\`\`\`

**Cảnh báo:** Ví dụ này không cấu hình authentication, authorization hoặc TLS. Chỉ dùng để minh họa trên môi trường local/isolated. Không đưa nguyên mẫu lên production, đặc biệt không bind rộng ra mạng hoặc Internet.

Trong production, nên dùng cơ chế remote management được JVM/runtime cung cấp hoặc cấu hình connector server có security, port và lifecycle rõ ràng. Khi dùng RMI và firewall/NAT, cần kiểm soát cả registry port và RMI endpoint thực tế.

## 8. Spring Framework và JMX remote

Spring Framework JMX có hai nhóm trách nhiệm độc lập:

\`\`\`text
A. Export management surface
   Spring bean
       -> MBeanExporter
       -> MBeanServer

B. Expose remote transport
   MBeanServer
       -> JMXConnectorServer
       -> network
       -> JMXConnector client
\`\`\`

Ví dụ Spring export MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfig {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MBeanServer server,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(java.util.Map.of(
            "com.example.orders:type=Queue,name=Orders",
            queueMonitor
        ));
        return exporter;
    }
}
\`\`\`

\`QueueMonitor\` cần là một MBean hợp lệ hoặc được Spring adaptation qua assembler phù hợp. Khi server được chỉ định như trên, exporter đăng ký vào platform MBeanServer.

Khi remote connector cũng gắn với platform MBeanServer, client có thể nhìn thấy các MBean ứng dụng và MXBeans nền tảng trên cùng endpoint, tùy quyền của client.

**Không suy ra:** Gắn \`@ManagedResource\` hoặc bật \`MBeanExporter\` là JVM tự mở RMI registry hay remote connector. Hai việc phải được cấu hình riêng.

### Spring Boot lưu ý

Spring Boot có JMX auto-configuration và Spring Boot Actuator endpoints. Một số cấu hình liên quan \`spring.jmx.enabled\` hoặc exposure của Actuator JMX endpoints tùy phiên bản.

Cần tách:
- Bật exporter JMX.
- Cho phép Actuator endpoint nào qua JMX.
- Khởi tạo remote connector của JVM.
- Áp dụng network authentication/authorization.

Không nên tạo exporter thứ hai khi Boot đã cấu hình cùng nhiệm vụ, vì có thể trùng \`ObjectName\`.

## 9. RMI connector và JNDI registry

Nhiều cấu hình JMX remote qua Java SE dùng RMI:

\`\`\`text
Client                           Server
  |                                |
  | lookup rmi://host:9010/jmxrmi  |
  |------------------------------->| RMI registry
  |<-------------------------------| connector stub
  |                                |
  | connect to stub endpoint       |
  |------------------------------->| RMI connector endpoint
  |                                |
  | getAttribute()/invoke()        |
  |------------------------------->| MBeanServer
  |<-------------------------------| response
\`\`\`

Mấu chốt:

- Registry lookup và JMX invocation là các bước logic khác nhau.
- Hostname/port quảng bá trong stub phải reachable.
- \`java.rmi.server.hostname\` có thể ảnh hưởng địa chỉ được quảng bá trong một số triển khai RMI.
- Không phải mọi JVM/runtime dùng chính xác cùng port arrangement.
- RMI có thể phức tạp qua NAT/firewall/containers nếu không kiểm soát endpoint ports.

Ví dụ khi triển khai trong container:

\`\`\`text
Docker container:
  internal hostname = container-abc
  registry port = 9010
  connector endpoint = dynamic port
\`\`\`

Client từ bên ngoài có thể lookup registry nhưng không truy cập được endpoint được stub trả về. Khắc phục cần cấu hình host, ports và network mapping thống nhất cho implementation đang dùng, không chỉ thay URL ở client.

## 10. Kết nối có xác thực

\`JMXConnectorFactory.connect()\` cho phép truyền environment map, ví dụ credentials:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXConnector.CREDENTIALS;

Map<String, Object> environment = new HashMap<>();

environment.put(
    JMXConnector.CREDENTIALS,
    new String[] {username, password}
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, environment)) {

    var connection = connector.getMBeanServerConnection();
    System.out.println(connection.getMBeanCount());
}
\`\`\`

Credentials ở client chỉ có ý nghĩa nếu connector server có authentication phù hợp. Thêm username/password vào environment không tự bảo vệ server đang mở không xác thực.

### Authentication khác Authorization

- **Authentication:** xác minh caller là ai.
- **Authorization:** caller được phép đọc attribute, gọi operation hoặc set attribute nào.

Một connector có thể biết identity nhưng vẫn cần policy cho quyền truy cập. Trong vận hành, đảm bảo:
- Remote endpoints không public.
- Quyền đọc/ghi JMX được giới hạn theo chức năng.
- Có TLS hoặc bảo vệ kênh thích hợp để tránh lộ credentials/truyền dữ liệu.
- Không commit credentials vào repository.
- Không ghi secret trong logs hoặc exceptions.

MBeans có thể có operations nhạy cảm như tắt service, reset state hoặc thay đổi cấu hình. Expose chúng qua remote JMX cần đánh giá tác động như một administrative API.

## 11. Notification qua remote connector

JMX cho phép client đăng ký listener từ xa:

\`\`\`java
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    System.out.printf(
        "type=%s seq=%d%n",
        notification.getType(),
        notification.getSequenceNumber()
    );
};

connection.addNotificationListener(
    targetObjectName,
    listener,
    null,
    null
);
\`\`\`

Khi notification được phát ở server, connector có thể chuyển notification tới client.

Tuy nhiên:
- Listener cần được đăng ký vào connection thích hợp.
- MBean có thể bị unregister hoặc thay thế.
- Network failure có thể làm gián đoạn delivery.
- Client restart/reconnect không tự có replay tất cả notification đã mất.
- \`Notification.sequenceNumber\` có thể hỗ trợ phát hiện bất thường nếu source contract có thứ tự liên tục, nhưng không tự cung cấp queue hoặc persistent history.

Đối với công cụ vận hành, notification nên là **tín hiệu cập nhật**, sau đó client đọc lại snapshot trạng thái của MBean. Nếu nghiệp vụ yêu cầu không mất từng sự kiện, nên sử dụng event store hoặc durable messaging riêng.

## 12. Vòng đời JMXConnector

Một remote client cần quản lý connection lifecycle như một tài nguyên mạng:

\`\`\`text
DISCONNECTED
     |
     | connect
     v
  CONNECTED
     |
     +-- query / read / invoke
     +-- subscribe notifications
     |
     | network error / server restart
     v
DISCONNECTED
     |
     | backoff + reconnect
     v
  CONNECTED
     |
     +-- re-register listeners
     +-- refresh current state
\`\`\`

Cần xử lý:

1. Kết nối ban đầu fail.
2. Connection bị đóng hoặc server restart.
3. MBean name/instance thay đổi sau deploy.
4. Listener không còn đăng ký sau reconnect.
5. Operation được gửi trước khi disconnect nhưng client chưa thấy response.
6. Trạng thái đã thay đổi trong thời gian client offline.

Một connector client có thể phát \`JMXConnectionNotification\` với sự kiện liên quan mở/đóng/lỗi connection. Dùng chúng để theo dõi health của kết nối, nhưng không trông chờ notification thay thế mọi cơ chế phát hiện lỗi.

### Retry có thể nguy hiểm với invoke()

Giả sử client gọi:

\`\`\`java
connection.invoke(
    name,
    "resetStatistics",
    new Object[0],
    new String[0]
);
\`\`\`

Nếu kết nối bị đứt đúng lúc, client có thể không biết server đã thực hiện operation hay chưa. **Retry mù** có thể gây thực thi hai lần.

Với operation không idempotent, cần:
- Xác định idempotency contract.
- Có request identifier hoặc trạng thái để kiểm tra kết quả khi cần.
- Giới hạn retry theo loại thao tác.
- Không dùng connector transport như bằng chứng giao nhận exactly-once.

## 13. Proxy quản trị qua MBeanServerConnection

Client không nhất thiết gọi thủ công \`getAttribute\`/\`invoke\` cho mọi operation. JMX hỗ trợ tạo proxy cho management interface phù hợp.

Ví dụ MXBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import javax.management.MBeanServerConnection;

MemoryMXBean memory = ManagementFactory.newPlatformMXBeanProxy(
    connection,
    ManagementFactory.MEMORY_MXBEAN_NAME,
    MemoryMXBean.class
);

System.out.println(memory.getHeapMemoryUsage().getUsed());
\`\`\`

Đoạn này dùng \`connection\` từ một remote connector. Proxy giúp viết API typed nhưng không làm mất các lỗi mạng hoặc serialization. Nó vẫn thực hiện các lời gọi remote phía sau.

Đối với Standard MBean hoặc MXBean của ứng dụng, có thể dùng \`JMX.newMBeanProxy()\` hoặc \`JMX.newMXBeanProxy()\` theo interface phù hợp.

Cần chú ý:
- ObjectName chính xác.
- Interface client tương thích hợp đồng server.
- Những kiểu Java dùng trong signature có thể truyền qua remote.
- Runtime exceptions do JMX/network cần được xử lý.

## 14. Phát hiện và chẩn đoán lỗi kết nối

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Connection refused | Không có connector/listener ở port | Port, process, bind interface, firewall |
| Registry lookup được nhưng timeout | RMI stub quảng bá host/port không reachable | RMI endpoint, NAT, container mapping |
| Authentication failed | Credentials hoặc server auth config sai | Environment map, credential store, server log |
| Client kết nối được nhưng không thấy app MBean | Exporter và connector gắn hai MBeanServers khác nhau | \`setServer()\`, connector binding, \`queryNames()\` |
| \`InstanceNotFoundException\` | ObjectName sai, bean chưa export hoặc đã unregister | \`isRegistered()\`, lifecycle |
| \`AttributeNotFoundException\` | Management interface không expose attribute đó | \`MBeanInfo\`, assembler/annotations |
| Deserialization exception | Client thiếu class hoặc type bị filter | OpenTypes/MXBean, classpath, filter |
| Notification ngừng sau reconnect | Listener chưa đăng ký lại | Re-subscribe + snapshot |
| \`invoke\` timeout | Operation chậm/network failure | MBean implementation, timeout, server health |
| Port mở nhưng client từ xa không thể vào | Firewall/TLS/RMI secondary port | Server config và network traces |

Đừng chỉ kiểm tra rằng một TCP port đang listening rồi kết luận JMX remote đã hoạt động. Với RMI, kết nối có nhiều giai đoạn và có thể dùng nhiều endpoint.

## 15. So sánh local JMX và remote JMX

| Khía cạnh | Local | Remote |
|---|---|---|
| API | \`MBeanServer\` trực tiếp | \`MBeanServerConnection\` qua connector |
| Network | Không yêu cầu kết nối mạng bên ngoài JVM | Phụ thuộc transport/network |
| Lỗi | Registration/metadata/invocation | Thêm timeout, disconnect, auth, serialization |
| Hiệu năng | Thường nhanh hơn | Có độ trễ mạng và chi phí serialization |
| Vòng đời listener | Trong cùng JVM | Phụ thuộc connection, reconnect |
| Security | Phụ thuộc môi trường Java và code caller | Phải xem rõ connector/network/auth |
| Kết quả invocation | Local return/exception | Client có thể không biết server đã thực hiện khi connection đứt |

Điều này không có nghĩa local JMX luôn an toàn. Một local MBean operation vẫn có thể thay đổi state quan trọng. Sự khác biệt là remote mở thêm một trust boundary và các failure modes của hệ thống phân tán.

## 16. Best practices vận hành

### Thiết kế server

- Chỉ export MBeans cần thiết, không tự động phơi bày toàn bộ Spring beans.
- Dùng ObjectName convention nhất quán, tránh trùng giữa nhiều contexts.
- Tách method chỉ đọc và method thay đổi trạng thái.
- Dùng kiểu attribute thân thiện với remote client: scalar, String, OpenTypes hoặc MXBeans phù hợp.
- Có metrics/log để phát hiện connector failures.
- Quản lý connector lifecycle: startup, shutdown, port binding và cleanup.

### Thiết kế client

- Đặt connect/read timeouts theo khả năng implementation.
- Không retry \`invoke\` không idempotent mù.
- Dùng bounded backoff khi reconnect.
- Re-register listener và refresh trạng thái sau reconnect.
- Đọc \`MBeanInfo\` khi cần xác minh attribute/operation.
- Không coi notification như persistent event log.
- Đóng \`JMXConnector\` khi không dùng.

### An toàn triển khai

- Tránh mở JMX remote ra Internet.
- Bảo vệ đường truyền, credentials và quyền quản trị.
- Kiểm tra RMI registry port lẫn endpoint port thực tế.
- Xác định hostname mà server quảng bá cho client.
- Trong Kubernetes/Docker, cân nhắc network routing, service discovery, NAT và security model.
- Thử kết nối từ đúng mạng/client runtime của production, không chỉ \`localhost\`.

## 17. Ví dụ kiến trúc phù hợp cho Spring application

\`\`\`text
   Spring Boot / Spring Framework application
                    |
               Business beans
                    |
               JMX monitor beans
                    |
                MBeanExporter
                    |
          Platform MBeanServer
             /            \
      JVM MXBeans      App MBeans
             \            /
              JMXConnectorServer
                    |
              Protected network
                    |
              JMXConnector client
                    |
            MBeanServerConnection
                    |
            Admin/monitoring tool
\`\`\`

Đường đi khi đọc một số liệu:

1. Client lấy \`JMXServiceURL\`.
2. Client connect qua \`JMXConnectorFactory\`.
3. Client lấy \`MBeanServerConnection\`.
4. Client truy vấn ObjectName phù hợp.
5. Client đọc attribute qua \`getAttribute()\`.
6. Connector server chuyển lời gọi tới MBeanServer.
7. MBean được gọi, giá trị được serialize về client.
8. Client xử lý result/exception và quản lý connection lifecycle.

Đường đi khi gọi operation có thể tương tự, nhưng cần đặc biệt quan tâm quyền truy cập và idempotency.

## 18. Bài tập thực hành

### Bài tập A — Client remote tối thiểu

1. Bật một JMX connector trong JVM thử nghiệm với cấu hình mạng an toàn.
2. Tạo \`JMXServiceURL\`.
3. Dùng \`JMXConnectorFactory.connect()\`.
4. Truy vấn \`java.lang:type=Memory\`.
5. Đọc \`HeapMemoryUsage\` và in giá trị \`used\`.
6. Đóng connector.

### Bài tập B — Spring bean qua remote

1. Tạo Spring bean \`QueueMonitor\`.
2. Export bằng \`MBeanExporter\` vào platform MBeanServer.
3. Dùng \`isRegistered()\` local xác minh.
4. Kết nối remote vào connector gắn cùng server.
5. Đọc \`PendingCount\` từ JVM khác.
6. So sánh hành vi khi MBean chưa được export và khi client kết nối sai server.

### Bài tập C — RMI và firewall

1. Khởi động connector trong môi trường test.
2. Kiểm tra registry port.
3. Quan sát host/port quảng bá của RMI endpoint.
4. Thử client từ JVM khác.
5. Giải thích vì sao chỉ mở registry port có thể chưa đủ.

### Bài tập D — Mất kết nối

1. Đăng ký listener cho một MBean có notification.
2. Ngắt kết nối.
3. Cho MBean phát notification trong lúc client offline.
4. Tái kết nối, đăng ký lại listener.
5. Đọc snapshot và đối chiếu với kỳ vọng.
6. Giải thích vì sao client không thể tự suy ra lịch sử đầy đủ chỉ từ JMX notification.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** JSR-160 giải quyết vấn đề gì?  
**Trả lời:** Cung cấp JMX Remote API và kiến trúc connector cho phép client quản trị MBeans trên MBeanServer từ xa.

**Câu 2.** \`MBeanExporter\` có tự mở JMX remote port không?  
**Trả lời:** Không. Exporter đăng ký MBeans; connector server mở đường remote access riêng.

**Câu 3.** \`JMXServiceURL\` có phải ObjectName của MBean không?  
**Trả lời:** Không. URL định vị connector; ObjectName định danh MBean trong server.

**Câu 4.** Client remote gọi API nào để đọc MBean?  
**Trả lời:** Lấy \`MBeanServerConnection\` từ \`JMXConnector\`, rồi gọi \`getAttribute()\`, \`queryNames()\`, \`invoke()\`...

**Câu 5.** Tại sao RMI registry port mở nhưng vẫn có thể timeout?  
**Trả lời:** RMI stub có thể quảng bá endpoint hostname/port khác không reachable qua network/NAT/firewall.

**Câu 6.** Reconnect có tự replay toàn bộ notifications cũ không?  
**Trả lời:** Không nên giả định vậy. Cần đăng ký lại listener và đồng bộ trạng thái; nếu cần lịch sử bền vững, phải có event store riêng.

**Câu 7.** Remote \`invoke()\` timeout có chắc operation chưa chạy không?  
**Trả lời:** Không. Server có thể đã thực hiện nhưng response bị mất; retry cần xét idempotency.

## 20. Ghi nhớ

- **JSR-160** xác định JMX Remote API: connector server, connector client, service URL và connection interface.
- \`MBeanServer\` lưu MBeans; \`JMXConnectorServer\` cung cấp lối truy cập; \`JMXConnector\` kết nối client; \`MBeanServerConnection\` thực thi lời gọi quản trị.
- \`MBeanExporter\` của Spring không tự tạo remote connector.
- RMI/JNDI có thể có registry lookup và endpoint invocation riêng, cần cấu hình networking cẩn thận.
- Remote JMX cần authentication, authorization, bảo vệ đường truyền và giới hạn mạng.
- Lỗi mạng làm remote calls có failure semantics khác local calls; đặc biệt không retry operation có tác động phụ một cách mù quáng.
- Notifications remote không cung cấp replay bền vững mặc định.
- Kiểm tra đúng MBeanServer, ObjectName, connector URL và client permissions khi chẩn đoán lỗi.

### Tài liệu tham khảo

- Java SE 21 API — JMX Remote package: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/package-summary.html
- Java SE 21 API — \`JMXServiceURL\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html
- Java SE 21 API — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE 21 API — \`JMXConnectorServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorServer.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- JSR-160 specification page: https://jcp.org/en/jsr/detail?id=160
