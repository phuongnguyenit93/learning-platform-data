# Service URL và cấu hình connector client trong Spring Framework JMX

## Mục tiêu

JMX cho phép một ứng dụng Java quản lý MBean trong JVM và cho phép client truy cập từ xa qua **JMX connector**. Để kết nối, client không chỉ cần biết hostname/port: nó cần một **JMXServiceURL** hợp lệ, connector provider phù hợp, thông tin xác thực, cấu hình SSL/TLS khi áp dụng, timeout, chính sách xử lý lỗi và hiểu server đích đang chứa MBean nào.

Trong ứng dụng Spring Framework, \`MBeanServer\` chứa các MBean được export, còn \`JMXConnectorServer\` xuất một đường truy cập từ xa tới server. Bên client, \`JMXConnectorFactory\` hoặc \`MBeanServerConnectionFactoryBean\` có thể tạo kết nối. Việc cấu hình URL và connector đúng đặc biệt quan trọng ở môi trường nhiều JVM, nhiều context Spring, mạng có firewall, NAT, container hoặc các yêu cầu bảo mật production.

Sau bài này, bạn có thể:

1. Phân biệt \`MBeanServer\`, \`JMXConnectorServer\`, \`JMXConnector\`, \`MBeanServerConnection\` và \`JMXServiceURL\`.
2. Đọc cấu trúc Service URL, đặc biệt dạng JMX RMI phổ biến.
3. Viết client Java kết nối, đọc attribute, gọi operation và đóng connector.
4. Cấu hình Spring \`MBeanServerConnectionFactoryBean\` khi cần quản lý kết nối như một bean.
5. Hiểu vai trò của environment map, credentials, TLS, JNDI và connector provider.
6. Chẩn đoán lỗi port, hostname, RMI stub, firewall, SSL, classloader, authentication và timeout.
7. Định nghĩa retry, lifecycle, monitoring và giới hạn rủi ro khi gọi operation quản trị từ xa.

## 1. Mô hình kết nối JMX từ xa

Trong cùng JVM, code có thể gọi trực tiếp:

\`\`\`java
MBeanServer localServer = ManagementFactory.getPlatformMBeanServer();
\`\`\`

Nhưng từ một JVM khác, client thường dùng connector:

\`\`\`text
Spring application JVM
 ┌───────────────────────────────────────────────────────┐
 │ Spring context                                        │
 │   ├─ MBeanExporter / AnnotationMBeanExporter          │
 │   │        │                                          │
 │   │        v                                          │
 │   └── MBeanServer  <────── JMXConnectorServer          │
 │          │                     │                      │
 │          └── MBeans            │                      │
 └────────────────────────────────┼──────────────────────┘
                                  │ JMX connector protocol
                                  │ (ví dụ RMI)
                                  ▼
Remote JVM / operations client
   JMXServiceURL
      │
      ▼
   JMXConnectorFactory.connect(...)
      │
      ▼
   JMXConnector
      │
      ▼
   MBeanServerConnection
      │
      ├─ queryNames(...)
      ├─ getAttribute(...)
      ├─ invoke(...)
      └─ addNotificationListener(...)
\`\`\`

Các thành phần khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| \`MBeanServer\` | Lưu registry MBean, thực thi thao tác quản trị |
| \`JMXConnectorServer\` | Cho phép client tiếp cận MBeanServer qua transport |
| \`JMXServiceURL\` | Mô tả endpoint và transport mà client cần sử dụng |
| \`JMXConnectorFactory\` | Tìm connector provider và thiết lập kết nối |
| \`JMXConnector\` | Đại diện kết nối client, có lifecycle và \`close()\` |
| \`MBeanServerConnection\` | Giao diện thực hiện JMX operations từ client |
| Environment map | Các tùy chọn cho provider: credentials, socket factory, timeout tùy cơ chế |

**Đăng ký thành công một MBean không đồng nghĩa remote client đã kết nối đúng server.** Connector phải được gắn vào MBeanServer phù hợp và network/bảo mật phải cho phép truy cập.

## 2. JMXServiceURL là gì?

Lớp \`javax.management.remote.JMXServiceURL\` chứa thông tin cần thiết để connector client tìm dịch vụ JMX.

Hình thức khái quát của JMX Service URL:

\`\`\`text
service:jmx:<protocol>://<host>[:<port>][<url-path>]
\`\`\`

Các phần:

- \`service:jmx:\`: tiền tố chuẩn.
- \`protocol\`: loại connector, ví dụ \`rmi\` trong Java RMI connector.
- \`host\` và \`port\`: ý nghĩa phụ thuộc protocol và cấu hình cụ thể.
- \`url-path\`: có thể chứa thông tin connector-specific như một JNDI lookup path.

Một Service URL có thể biểu diễn endpoint theo cách phức tạp hơn một socket TCP duy nhất. Đặc biệt với RMI, URL lookup vào registry **không nhất thiết là endpoint cuối cùng** mà client dùng để gọi MBean.

### 2.1 Dạng RMI JMX hay gặp

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.example.internal:1099/jmxrmi
\`\`\`

Diễn giải:

\`\`\`text
service:jmx:rmi:
      \___ dùng RMI connector

///jndi/rmi://jmx.example.internal:1099/jmxrmi
      \___ đi qua JNDI để tìm RMI connector stub
            registry host: jmx.example.internal
            registry port: 1099
            binding: jmxrmi
\`\`\`

Trong một số deployment, URL có dạng:

\`\`\`text
service:jmx:rmi://localhost:9000/jndi/rmi://localhost:1099/jmxrmi
\`\`\`

Đừng suy ra ý nghĩa của mọi port chỉ từ một ví dụ. Với RMI, endpoint được công bố trong stub có thể sử dụng port/host khác với registry lookup. Vì vậy client có thể lấy stub thành công rồi vẫn thất bại khi kết nối kênh thực tế tới connector.

### 2.2 URL dạng có connector stub

JMX RMI cũng hỗ trợ các dạng URL chứa connector stub đã được mã hóa theo cơ chế provider. Đây thường không phải cấu hình người vận hành muốn tự tạo thủ công. Với ứng dụng triển khai thực tế, một URL JNDI/RMI được công bố có kiểm soát và thông số mạng nhất quán sẽ dễ vận hành hơn.

### 2.3 URL không chứa credentials

\`JMXServiceURL\` dùng để định vị dịch vụ và xác định provider. Không đưa username/password hoặc token vào phần host/path rồi hy vọng connector tự xác thực đúng. Thông tin bảo mật phải đi qua cơ chế phù hợp của connector provider và secret management.

## 3. Client Java: kết nối bằng JMXConnectorFactory

Ví dụ cơ bản:

\`\`\`java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;
import javax.management.remote.JMXConnectorFactory;

public final class JmxClientExample {

    public static void main(String[] args) throws Exception {
        String endpoint =
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:1099/jmxrmi";

        JMXServiceURL url = new JMXServiceURL(endpoint);

        Map<String, Object> env = new HashMap<>();
        // Chỉ thêm credentials khi endpoint yêu cầu, lấy từ secret store.
        // env.put(JMXConnector.CREDENTIALS, new String[]{user, password});

        try (JMXConnector connector = JMXConnectorFactory.connect(url, env)) {
            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            System.out.println(
                "Default domain: " + connection.getDefaultDomain());
            System.out.println(
                "Registered MBeans: " + connection.getMBeanCount());
        }
    }
}
\`\`\`

\`JMXConnector\` có thể được đóng bằng \`close()\`; trong Java hỗ trợ \`AutoCloseable\` qua \`Closeable\`. Dùng try-with-resources hoặc lifecycle tương đương để không giữ RMI connection/resource sau khi client kết thúc.

**Lưu ý nhập khẩu:** trong code dự án, chỉ cần import \`JMXConnectorFactory\` một lần; ví dụ trên minh họa các class cần dùng, còn IDE có thể tối ưu import trùng khi chỉnh sửa.

Không nên mở connector mới cho mỗi metric nếu hệ thống poll thường xuyên. Có thể quản lý một connector theo phiên làm việc, theo dõi trạng thái và tạo lại khi kết nối thật sự hỏng.

## 4. Đọc MBean bằng MBeanServerConnection

Sau khi lấy \`MBeanServerConnection\`, client sử dụng hầu hết các thao tác quản trị quen thuộc:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.inventory:type=Cache,name=Catalog");

boolean present = connection.isRegistered(name);

if (!present) {
    throw new IllegalStateException(
        "Expected MBean not registered: " + name);
}

Object value = connection.getAttribute(name, "HitCount");
System.out.println("Cache hits: " + value);
\`\`\`

Điểm quan trọng: \`MBeanServerConnection\` là interface được dùng cho cả local và remote access, nhưng remote call có thêm khả năng lỗi \`IOException\`, latency và mất kết nối. Client không nên coi mọi method là thao tác Java memory cực nhanh.

Để liệt kê:

\`\`\`java
Set<ObjectName> names = connection.queryNames(
    new ObjectName("com.example.inventory:*"), null);
names.forEach(System.out::println);
\`\`\`

Cần giới hạn query khi JMX registry rất lớn để tránh quét/serialize dữ liệu không cần thiết, và không để người dùng nhập wildcard không giới hạn nếu một application API public chuyển tiếp truy vấn JMX.

## 5. Gọi operation từ xa: chữ ký và tác dụng phụ

Ví dụ:

\`\`\`java
Object result = connection.invoke(
    name,
    "requestRefresh",
    new Object[]{"catalog"},
    new String[]{"java.lang.String"}
);
\`\`\`

Mảng \`signature\` dùng **tên kiểu tham số khai báo** của operation theo metadata JMX, không phải kiểu suy luận từ chuỗi JSON hoặc input CLI. Primitive \`int\` thường dùng \`"int"\`, dù \`Object[]\` chứa \`Integer\`.

Một operation remote có thể có side effect lớn. Nếu mất kết nối sau khi gửi \`invoke\`, không thể kết luận lệnh chưa chạy. Trước khi retry, đọc effective state/operation status hoặc dùng request ID được hệ thống thiết kế để tránh double execution.

Khi client gọi nhiều JVM, cần gắn rõ target instance và ObjectName. Cùng một ObjectName trên hai JVM là hai MBean khác nhau.

## 6. Environment map của JMXConnectorFactory

Lệnh kết nối có overload:

\`\`\`java
JMXConnector connector =
    JMXConnectorFactory.connect(url, environment);
\`\`\`

\`environment\` là map các property được connector provider hiểu. Một số key chuẩn được định nghĩa bởi JMX API; nhiều key khác phụ thuộc vào provider, JNDI, RMI hoặc cấu hình socket factory.

Ví dụ credentials:

\`\`\`java
import java.util.Map;
import javax.management.remote.JMXConnector;

Map<String, Object> env = Map.of(
    JMXConnector.CREDENTIALS,
    new String[]{username, password}
);
\`\`\`

Việc truyền \`String[]{username,password}\` là hình thức credentials thông dụng của RMI JMX khi server được cấu hình password authentication. Nó **không tự mã hóa đường truyền**. Nếu không có TLS hoặc transport được bảo vệ, credentials có thể gặp rủi ro khi truyền qua mạng. Bảo mật connector phải được thiết lập từ server đến client.

Không in env map ra log vì có thể chứa secret. Không hard-code password vào source hoặc build artifact.

### 6.1 JNDI-specific properties

Một số URL RMI/JNDI dùng naming service để tra cứu stub. Tùy provider, environment map có thể có thuộc tính về JNDI hoặc socket factory. Các key không chuẩn JMX cần được kiểm tra theo tài liệu provider và JDK đang chạy; tránh dùng các key “connect.timeout” hoặc “read.timeout” tự sáng tạo rồi tin rằng connector sẽ thực thi.

### 6.2 Connector provider khác RMI

JMX API cho phép connector provider theo protocol. Nếu URL sử dụng một protocol không có provider tương ứng trên classpath/module path, client có thể gặp \`MalformedURLException\`, lỗi provider không hỗ trợ hoặc exception khi tạo connector. Không nên áp dụng các setting RMI trực tiếp cho mọi provider.

## 7. Tạo Service URL phía server và công bố endpoint

Một ứng dụng có thể tự tạo connector server theo cấu hình riêng:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

MBeanServer mbeanServer = ManagementFactory.getPlatformMBeanServer();

JMXServiceURL serviceUrl =
    new JMXServiceURL("service:jmx:rmi:///jndi/rmi://localhost:1099/jmxrmi");

JMXConnectorServer connectorServer =
    JMXConnectorServerFactory.newJMXConnectorServer(
        serviceUrl,
        null,
        mbeanServer
    );

// Với dạng /jndi/rmi://..., cần có RMI registry phù hợp đang chạy.
connectorServer.start();

// Sau khi hoàn tất lifecycle:
// connectorServer.stop();
\`\`\`

Ví dụ thể hiện ý tưởng nhưng **không đủ để triển khai production**: nó không cấu hình authentication, TLS, network binding hay ownership. Với URL có JNDI registry, registry phải sẵn sàng và các cổng RMI phải thông nhau. Chỉ dùng ví dụ trên trong môi trường thử nghiệm cô lập, không công bố endpoint chưa bảo vệ trên mạng.

Spring cung cấp các bean/factory chuyên cho JMX connector trong những cấu hình nhất định, nhưng nguyên tắc vẫn là tách rõ \`MBeanServer\`, connector server và Service URL. Không để nhiều Spring context cùng cố start connector trên một port.

## 8. RMI hai chặng: registry và endpoint thực tế

Đây là nguyên nhân phổ biến nhất của trường hợp “telnet được port nhưng JConsole vẫn lỗi”.

\`\`\`text
Remote client
   |
   | ① lookup RMI registry (ví dụ TCP 1099)
   v
RMI Registry
   |
   | trả về connector stub với host/port thực tế
   v
Remote client
   |
   | ② kết nối tới endpoint trong stub (có thể port khác)
   v
JMX RMI Connector
   |
   v
MBeanServer
\`\`\`

Trong container hoặc sau NAT, server có thể công bố hostname không thể truy cập từ client (chẳng hạn \`localhost\` hoặc hostname nội bộ của container). Khi đó registry lookup thành công nhưng bước kết nối tiếp theo thất bại.

Các biện pháp phổ biến:

- Cố định và công bố đúng host RMI mà client có thể truy cập.
- Cấu hình port registry và RMI server port theo runtime/JDK đang dùng.
- Mở đúng những port cần thiết trên firewall.
- Tránh dùng \`localhost\` trong URL/stub nếu client ở máy khác.
- Kiểm tra DNS và NAT mapping.
- Ưu tiên tunnel/VPN hoặc quản lý endpoint qua mạng nội bộ được bảo vệ.

Trong nhiều cấu hình JVM management agent, các system property như \`com.sun.management.jmxremote.port\`, \`com.sun.management.jmxremote.rmi.port\` và \`java.rmi.server.hostname\` có ảnh hưởng đến các endpoint JMX/RMI tương ứng. Đây là property của cơ chế JVM management agent/RMI, không phải cú pháp URL phổ quát cho mọi custom \`JMXConnectorServer\`. Khi dùng server tự tạo, cần cấu hình phù hợp riêng.

## 9. Cấu hình client trong Spring Framework

Thay vì tự tạo connector trong từng service, có thể dùng \`org.springframework.jmx.support.MBeanServerConnectionFactoryBean\` để có một \`MBeanServerConnection\` được quản lý trong Spring context.

Ví dụ cấu hình:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class RemoteJmxClientConfiguration {

    @Bean
    public MBeanServerConnectionFactoryBean remoteMBeanServerConnection() {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();

        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:1099/jmxrmi");

        // Chỉ dùng khi server yêu cầu auth và transport được bảo vệ.
        // factory.setEnvironmentMap(Map.of(
        //     JMXConnector.CREDENTIALS, new String[]{user, password}));

        factory.setConnectOnStartup(false);
        return factory;
    }
}
\`\`\`

\`MBeanServerConnectionFactoryBean\` tạo kết nối tới remote MBeanServer thông qua JMX connector và có thể được quản lý bởi Spring lifecycle. \`connectOnStartup\` được sử dụng để quyết định có kết nối trong giai đoạn startup hay trì hoãn, tùy API/phiên bản Spring. Cần hiểu hành vi khôi phục kết nối và exception propagation trước khi dùng trong ứng dụng lâu dài.

Việc truy cập remote connector nên được tách khỏi critical path của các request nghiệp vụ: nếu JMX endpoint tạm unavailable, ứng dụng không nên mặc định thất bại toàn bộ startup trừ khi đó là yêu cầu vận hành đã được thiết kế.

### 9.1 Dùng bean kết nối để tạo JMX proxy

Spring cũng cung cấp \`MBeanProxyFactoryBean\` và các phương thức proxy MBean để truy cập như Java interface:

\`\`\`java
public interface QueueMonitorMBean {
    int getDepth();
    String getState();
}
\`\`\`

Có thể cấu hình một proxy được gắn với \`ObjectName\` của remote MBean, nhưng cần chú ý interface và kiểu dữ liệu tương thích với remote MBean metadata. Proxy không xóa đi lỗi mạng: lời gọi Java trông giống local vẫn có thể timeout, mất kết nối hoặc ném exception.

Đối với operation điều khiển quan trọng, dùng proxy không có nghĩa được retry tự động sau mọi lỗi.

## 10. Cấu hình URL theo môi trường mà không hard-code

Các môi trường dev, test, staging và production có thể dùng endpoint khác nhau:

\`\`\`yaml
management:
  jmx:
    service-url: \${JMX_SERVICE_URL:}
    username: \${JMX_USERNAME:}
    password: \${JMX_PASSWORD:}
\`\`\`

Đây là **cấu hình ứng dụng ví dụ**, không phải property Spring Boot tự động hỗ trợ để tạo JMX connector client. Bạn phải tự bind các key vào cấu hình Java của dự án hoặc dùng cơ chế configuration properties tương ứng.

Ví dụ qua Spring \`@Value\`:

\`\`\`java
@Configuration
class JmxClientConfig {

    @Bean
    MBeanServerConnectionFactoryBean remoteConnection(
            @Value("\${management.jmx.service-url}") String serviceUrl) {

        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(serviceUrl);
        return factory;
    }
}
\`\`\`

Nếu credentials cần thiết, lấy qua secret manager hoặc environment an toàn. Không commit password, không log URL nếu URL chứa thông tin nhạy cảm do cấu hình sai, và phân quyền người có thể sửa endpoint.

### 10.1 Không nhầm server URL với MBean ObjectName

\`\`\`text
JMXServiceURL:
  service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi

ObjectName:
  com.example.jobs:type=Worker,name=Import

Operation:
  requestPause()
\`\`\`

Ba giá trị tương ứng với **nơi kết nối**, **MBean đích** và **hành động**. Đổi ObjectName không chuyển connection sang JVM khác. Đổi Service URL có thể khiến cùng ObjectName trỏ tới một instance khác.

## 11. Bảo mật connector client

JMX remote là bề mặt quản trị nhạy cảm vì có thể đọc runtime state và gọi operation thay đổi trạng thái. Cần thiết kế bảo mật từ đầu.

### 11.1 Authentication

- Cấu hình server yêu cầu xác thực.
- Client dùng đúng credentials theo connector provider.
- Đặt secret trong secret store, không ở source hoặc log.
- Xem xét rotate và revoke quyền.
- Không giả định user của HTTP/Spring Security cũng tự động có quyền JMX.

### 11.2 Encryption

Username/password trong \`JMXConnector.CREDENTIALS\` không đồng nghĩa dữ liệu đã được mã hóa. Với RMI, xác định rõ RMI SSL socket factories hoặc tunnel bảo mật và cách client trust server certificate.

Một connection đã xác thực mà không mã hóa có thể không đủ đáp ứng yêu cầu mạng production. Cần xác minh chứng chỉ và hostname phù hợp, tránh tắt kiểm tra TLS để “sửa lỗi kết nối”.

### 11.3 Authorization

Quyền xem metric và quyền gọi \`clearCache()\` hoặc \`pauseWorker()\` là hai việc khác. Chính sách JMX access control tùy connector/runtime và có thể không đủ chi tiết cho từng business operation. Với điều khiển rủi ro cao, dùng control plane có identity/audit và kiểm tra server-side phù hợp.

### 11.4 Network scope

- Ưu tiên mạng nội bộ quản trị, VPN hoặc SSH tunnel được kiểm soát.
- Không public JMX port trực tiếp ra Internet.
- Chỉ mở port thực sự cần và theo dõi truy cập.
- Trong container/Kubernetes, cân nhắc hostname RMI trong stub; port-forward có thể không hoạt động nếu stub trả về host/port không phù hợp.
- Không dựa vào ObjectName domain để phân quyền: domain là namespace, không phải security boundary.

## 12. Timeout và retry: không có một setting chung cho mọi connector

Rất nhiều ví dụ trên Internet sử dụng các key như:

\`\`\`text
jmx.remote.x.client.connection.check.period
sun.rmi.transport.tcp.responseTimeout
com.sun.jndi.rmi.connect.timeout
com.sun.jndi.rmi.read.timeout
\`\`\`

Các key này có phạm vi và mức hỗ trợ khác nhau, nhiều key phụ thuộc vào implementation Oracle/OpenJDK hoặc tầng JNDI/RMI. Không nên copy một property rồi giả định nó áp dụng cho toàn bộ \`connect()\`, mọi lời gọi \`getAttribute()\` và \`invoke()\`.

Phân biệt ít nhất:

1. **DNS resolution**: lookup hostname có thể chậm hoặc lỗi.
2. **RMI registry lookup**: tìm stub tại registry.
3. **Transport connect**: tạo socket tới endpoint trong stub.
4. **Remote invocation**: gửi yêu cầu và chờ phản hồi.
5. **Connection monitoring**: phát hiện connector đã chết trong nền.
6. **Application deadline**: thời hạn do code client tự kiểm soát.

Nếu yêu cầu deadline chặt, cần thiết kế với provider/socket factory có hỗ trợ timeout thực sự và xử lý tình huống tác vụ remote vẫn có thể chạy sau khi client ngừng chờ. Việc hủy Java Future hoặc thread chờ không phải bảo đảm huỷ operation server-side.

Không tự động retry operation có side effect sau \`IOException\` hoặc timeout. Với metric read-only, retry có giới hạn và exponential backoff có thể hợp lý nếu không gây overload.

## 13. Vòng đời kết nối trong ứng dụng Spring

Client JMX có thể chạy dưới dạng:

- CLI một lần: mở connection, đọc/gọi, đóng ngay.
- Long-running monitoring agent: giữ kết nối lâu hơn, theo dõi health và reconnect khi cần.
- Một Spring bean chia sẻ connection: cần hiểu FactoryBean/lifecycle và tính thread-safe của client usage.
- Một job scheduler poll định kỳ: giới hạn concurrency để không mở quá nhiều connector cùng lúc.

Một chiến lược vận hành:

\`\`\`text
START
  |
  v
RESOLVE URL / CONFIG
  |
  v
CONNECT
  |
  +-- failure --> backoff --> CONNECT
  |
  v
CONNECTED
  |
  +-- read-only poll --> result / bounded retry
  |
  +-- operation with side effect --> requestId + post-check
  |
  +-- connection broken --> close --> backoff --> CONNECT
  |
  v
SHUTDOWN --> close()
\`\`\`

Thời gian backoff cần có giới hạn và jitter nếu nhiều client reconnect cùng lúc. Không để polling thread giữ lock nghiệp vụ trong khi chờ JMX network.

### 13.1 Đóng connector để không rò rỉ resource

\`JMXConnector.close()\` cần được gọi khi client shutdown hoặc thay kết nối. Trong Spring, \`MBeanServerConnectionFactoryBean\` có cơ chế lifecycle liên quan đến connector; khi tự viết wrapper, \`@PreDestroy\` hoặc \`DisposableBean\` có thể được dùng để close.

Lưu ý không đóng connection mà một component khác vẫn đang sử dụng nếu bạn chia sẻ connector. Khi quản lý nhiều consumer, nên quy định owner riêng cho connector và cơ chế mượn connection phù hợp.

## 14. Chẩn đoán lỗi kết nối

| Triệu chứng | Khả năng | Hướng kiểm tra |
|---|---|---|
| Không kết nối tới registry port | Firewall, DNS, bind port, server chưa chạy | Host/port reachability, log registry |
| Lookup được registry nhưng invocation lỗi | Stub công bố host/port không truy cập được | RMI hostname, server port, NAT |
| \`SecurityException\`/auth failure | Sai credentials hoặc server yêu cầu cơ chế khác | Auth config, secret, policy |
| SSL handshake failed | Chứng chỉ, truststore, protocol mismatch | TLS config hai phía |
| \`MalformedURLException\` | Service URL sai cú pháp/protocol | Parse URL, provider support |
| \`IOException\` sau một thời gian | Network reset, server restart, idle timeout | Reconnect/backoff, heartbeat |
| \`InstanceNotFoundException\` | MBean không tồn tại theo ObjectName | Query registry, đúng JVM/server |
| \`AttributeNotFoundException\` | Tên attribute sai hoặc metadata khác | \`getMBeanInfo\` |
| \`ReflectionException\` | Operation name/signature sai | \`MBeanOperationInfo\` |
| Connection đúng nhưng không thấy app MBean | Connector trỏ MBeanServer khác | So sánh server reference và registry |

Đừng sửa lỗi bằng việc tắt authentication/TLS hoặc mở rộng firewall ra mọi mạng. Cần định vị chính xác tầng nào thất bại.

### 14.1 Phép kiểm tra có thứ tự

\`\`\`text
A. URL có đúng prefix/protocol không?
B. Client DNS resolve được host không?
C. Registry/connector port có reachable không?
D. Stub có chứa host/port mà client tới được không?
E. Auth/TLS có phù hợp không?
F. Kết nối trả về MBeanServerConnection được không?
G. Default domain/MBean count có đúng JVM đích không?
H. ObjectName có tồn tại không?
I. Attribute/operation metadata có đúng không?
\`\`\`

Các bước G-I giúp tránh nhầm “đã kết nối thành công” với “đã kết nối đúng ứng dụng/MBean”.

## 15. Chẩn đoán nhiều Spring ApplicationContext hoặc nhiều server

Một JVM có thể có:

\`\`\`text
Platform MBeanServer
   ├── JVM MXBeans
   └── App MBeans

Custom MBeanServer
   └── Internal-only MBeans
\`\`\`

Nếu \`JMXConnectorServer\` được gắn với custom server, remote client không tự nhìn thấy MBean đã export vào platform server. Ngược lại, một connector vào platform server không nhìn thấy MBean ở custom server.

Các thông số cần đối chiếu:

- Exporter \`setServer(...)\` hoặc \`@EnableMBeanExport(server=...)\`.
- Connector server được khởi tạo với \`MBeanServer\` nào.
- Client đang dùng Service URL nào.
- ObjectName mà client query có trùng tên registration không.
- Nếu context restart, MBean đã unregister/re-register đúng lifecycle chưa.

\`defaultDomain\` của exporter chỉ ảnh hưởng naming strategy khi thích hợp; nó không thay registry hoặc endpoint của connector.

## 16. Test client kết nối JMX một cách kiểm soát

Một integration test nên có server thực sự được khởi động trong test environment cô lập và dùng URL được server công bố, thay vì phụ thuộc port cố định có thể xung đột với máy CI.

Ví dụ skeleton:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServerConnection;
import javax.management.remote.*;

class RemoteJmxIntegrationScenario {

    void verify(JMXServiceURL url) throws Exception {
        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            assertNotNull(connection.getDefaultDomain());
            assertNotNull(connection.getMBeanCount());
        }
    }
}
\`\`\`

Để hoàn chỉnh, fixture phải start/stop connector server và registry theo URL/port riêng của test, có authentication/TLS nếu chính sách yêu cầu. Không dùng JMX production endpoint cho unit/integration test. Với test remote có timeout, xử lý cleanup mọi resources và không retry tác vụ thay đổi trạng thái ngoài kiểm soát.

### 16.1 Kiểm thử contract thay vì chỉ TCP reachability

Một test có ý nghĩa hơn nên kiểm tra:

\`\`\`java
ObjectName expected = new ObjectName(
    "com.example.ops:type=Worker,name=Import");

assertTrue(connection.isRegistered(expected));

MBeanInfo info = connection.getMBeanInfo(expected);
assertNotNull(info);
\`\`\`

Kết nối thành công nhưng \`isRegistered=false\` thường cho thấy sai server, sai ObjectName hoặc exporter chưa đăng ký.

## 17. Mẫu cấu hình client production

Tối thiểu nên định nghĩa:

\`\`\`yaml
jmxClient:
  enabled: true
  serviceUrl: "service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi"
  connectPolicy:
    maxConcurrentConnections: 2
    retryReadOnly: true
    maxAttempts: 3
    backoffMillis: 500
  security:
    credentialSource: "secret-manager"
    tlsRequired: true
  expected:
    objectName: "com.example.ops:type=Worker,name=Import"
\`\`\`

Đây là schema **do ứng dụng tự thiết kế**, không phải các property Spring Framework/Boot mặc định. Nên tách secrets khỏi config và đảm bảo code thực thi đúng policy được khai báo. \`tlsRequired\` ở YAML không tự bật TLS; phải có socket factories/trust configuration và server TLS tương ứng.

Một client ổn định nên có:
- Logging có redaction, không ghi credentials.
- Metrics cho connection attempts, failures, latency và reconnect count.
- Circuit breaker/backoff để tránh overload registry.
- Giới hạn số connection đồng thời.
- Deadline được xác nhận hỗ trợ bởi provider thực tế.
- Post-check cho operation điều khiển.
- Shutdown cleanup rõ ràng.

## 18. Những hiểu lầm phổ biến

**“JMX Service URL chỉ có một host:port.”** Không nhất thiết, đặc biệt RMI có registry lookup và endpoint trong stub.

**“Mở port 1099 là đủ.”** Không chắc: endpoint RMI thứ hai có thể dùng host/port khác.

**“JMXConnectorFactory.connect() tự bảo mật.”** Không. Authentication, TLS và quyền phải được cấu hình ở server/client.

**“Có thể để username/password trong URL.”** Không phải cách cấu hình chuẩn của JMX RMI connector; credentials thường truyền bằng environment map theo cơ chế provider.

**“Kết nối thành công đồng nghĩa thấy mọi MBean trong JVM.”** Không. Connector chỉ phục vụ MBeanServer được gắn với nó.

**“Spring @EnableMBeanExport bật remote JMX.”** Không. Nó phục vụ export MBean; connector remote là thành phần khác.

**“MBeanServerConnection là local, không cần xử lý IOException.”** Interface có thể đại diện remote connection; lỗi mạng là bình thường.

**“Lỗi timeout cho phép retry mọi operation.”** Không. Operation có side effect có thể đã chạy.

**“Một setting timeout tự áp dụng mọi protocol.”** Không. Hỗ trợ timeout phụ thuộc connector provider và transport.

## 19. Bài tập vận dụng

### Bài 1 — Đọc URL

Cho URL:

\`\`\`text
service:jmx:rmi:///jndi/rmi://ops.example.internal:1999/jmxrmi
\`\`\`

Xác định protocol, registry host, registry port và binding. Giải thích vì sao không được suy ra toàn bộ kết nối chỉ dùng một TCP port.

### Bài 2 — Code client

Viết client nhận URL từ cấu hình, kết nối bằng \`JMXConnectorFactory\`, kiểm tra \`ObjectName\` tồn tại và đọc một attribute. Đảm bảo connector được đóng trong \`finally\` hoặc try-with-resources.

### Bài 3 — RMI trong container

Client kết nối được registry nhưng không thể invoke. Stub trả hostname \`127.0.0.1\` hoặc hostname nội bộ container. Đề xuất cách cấu hình RMI hostname/port và bảo vệ đường truyền mà không mở port ra Internet.

### Bài 4 — Bảo mật

Một đoạn code đặt \`JMXConnector.CREDENTIALS\` nhưng không bật TLS. Giải thích vì sao đây không phải bảo đảm mã hóa; đề xuất kiểm tra auth/TLS/truststore và giới hạn mạng.

### Bài 5 — Timeout

Một script gọi \`resetCounters()\` qua JMX và gặp \`IOException\` ngay sau khi gửi. Có nên gọi lại ngay không? Vì sao cần kiểm tra metric/state hoặc request ID trước khi retry?

### Bài 6 — Multi-server

Spring exporter đăng ký MBean vào custom server X, connector phục vụ platform server Y. Client gọi \`isRegistered=false\`. Sửa cấu hình nào để registry và endpoint thống nhất?

## Tổng kết

**JMXServiceURL** mô tả cách client tìm dịch vụ JMX; **JMXConnectorFactory** tạo kết nối, còn **MBeanServerConnection** là giao diện để truy cập MBean. Với RMI, phải phân biệt registry lookup và endpoint trong stub, đặc biệt qua firewall/NAT/container. Trong Spring Framework, \`MBeanServerConnectionFactoryBean\` hỗ trợ quản lý kết nối client, nhưng không thay thế việc thiết kế bảo mật, timeout, reconnect và lifecycle. Một kết nối đúng cần đồng thời thỏa mãn URL/provider, network, authentication/TLS, MBeanServer đích và ObjectName/operation contract. Khi thao tác từ xa có side effect, hãy xem lỗi mạng là trạng thái bất định và xác minh hiệu ứng trước khi retry.
