# Bảo vệ connector bằng xác thực và TLS trong Spring Framework JMX

## Mục tiêu

JMX là giao diện quản trị mạnh: client có thể đọc runtime attributes, gọi operation, thay đổi cấu hình, trigger reconnect, pause worker, xóa cache hoặc thực hiện các thao tác chẩn đoán có chi phí lớn. Trong Spring Framework, \`MBeanExporter\` và \`AnnotationMBeanExporter\` đưa bean lên \`MBeanServer\`, nhưng việc **bảo vệ kết nối từ xa** thuộc về JMX connector, JVM management agent, cấu hình mạng và chính sách quyền truy cập.

Một kết nối JMX remote có thể hoạt động nhưng chưa an toàn nếu không xác thực người dùng hoặc truyền credentials qua kênh không được mã hóa. Ngược lại, bật TLS mà không có authorization vẫn có thể cho phép người dùng đã xác thực gọi những operation nguy hiểm. Để vận hành production, cần kết hợp **authentication, TLS, authorization, network isolation, audit và lifecycle**.

Sau bài học, bạn có thể:

- Phân biệt MBeanServer, JMXConnectorServer, JMXConnector và MBeanServerConnection.
- Giải thích vì sao authentication và TLS là hai cơ chế khác nhau, cần cấu hình đồng bộ cả server lẫn client.
- Hiểu các lựa chọn JMX RMI authentication, password/access files, custom authenticator và cách sử dụng credentials.
- Thiết lập mô hình keystore/truststore, kiểm tra chứng chỉ và hostname mà không tắt xác minh bảo mật.
- Nhận diện rủi ro đặc thù của RMI registry, RMI stub, nhiều cổng, firewall và container.
- Tổ chức phân quyền read-only/control, chặn truy cập ngoài mạng quản trị và ghi audit.
- Chẩn đoán authentication failure, TLS handshake failure và kết nối registry thành công nhưng invocation thất bại.
- Xây dựng checklist kiểm thử, rotation và vận hành an toàn cho JMX connector.

## 1. Ranh giới bảo mật của JMX

JMX bao gồm các tầng độc lập:

\`\`\`text
Spring ApplicationContext
    |
    | @ManagedResource / MBeanExporter
    v
MBeanServer
    |
    | JMXConnectorServer (server-side)
    | authentication + TLS + access policy
    v
Network boundary (firewall, VPN, tunnel)
    |
    v
JMXConnectorFactory / JMXConnector (client-side)
    |
    | credentials + TLS trust configuration
    v
MBeanServerConnection
    |
    +-- getAttribute(...)
    +-- queryNames(...)
    +-- invoke(...)
\`\`\`

Trong mô hình này:

| Cơ chế | Câu hỏi nó giải quyết |
|---|---|
| Authentication | Client hoặc người dùng nào đang kết nối? |
| Authorization | Người dùng ấy được đọc/gọi thành phần nào? |
| TLS | Kết nối có được mã hóa và endpoint có được xác minh không? |
| Firewall/network isolation | Ai có thể chạm tới connector ở tầng mạng? |
| Audit | Ai đã làm gì, lúc nào, trên MBean nào? |
| Input validation | Operation có nhận và xử lý tham số an toàn không? |
| Lifecycle management | Connector, certificate và quyền có được quản lý khi thay đổi? |

**Một cơ chế không thay thế các cơ chế còn lại.** TLS không quyết định người dùng được gọi \`clearCache()\`; authentication không đảm bảo gói tin mã hóa; firewall không thay thế kiểm tra người dùng và quyền.

## 2. Vì sao connector JMX là mục tiêu nhạy cảm?

Một connector phục vụ MBeanServer có thể cho phép client đọc nhiều MBean cùng lúc, bao gồm platform MXBean của JVM và những bean ứng dụng được export. Các operation có thể thay đổi trạng thái runtime. Nếu một client không đáng tin cậy có quyền invoke, hậu quả có thể vượt xa việc lộ vài số liệu.

Ví dụ MBean có:

\`\`\`java
@ManagedResource(
    objectName = "com.example.ops:type=Worker,name=Import")
public class WorkerAdministration {

    @ManagedAttribute
    public String getState() {
        return "RUNNING";
    }

    @ManagedOperation
    public void requestPause() {
        // Yêu cầu tạm dừng nhận công việc.
    }
}
\`\`\`

Nếu remote connector mở không xác thực, người ngoài phạm vi vận hành có thể có cơ hội gọi \`requestPause()\` qua \`MBeanServerConnection.invoke()\`. Không nên kỳ vọng annotation Spring tự bảo vệ thao tác này. JMX export là **công bố khả năng**, còn việc ai được sử dụng phải được ràng buộc tại các lớp quản trị.

Quy tắc thiết kế đầu tiên: **không để endpoint JMX remote không được bảo vệ trên mạng công cộng**.

## 3. Authentication là gì?

Authentication xác định danh tính client/người dùng trước khi cho phép truy cập tới MBeanServer. Với JMX RMI, một số JVM management agent hỗ trợ cấu hình password file và access file. Ngoài ra, custom \`JMXAuthenticator\` hoặc tích hợp hệ thống danh tính có thể được áp dụng khi tạo \`JMXConnectorServer\` riêng.

Một client Java thường truyền credentials bằng environment:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi");

Map<String, Object> environment = new HashMap<>();
environment.put(
    JMXConnector.CREDENTIALS,
    new String[]{username, password}
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, environment)) {
    // Lấy MBeanServerConnection và truy vấn MBean.
}
\`\`\`

\`JMXConnector.CREDENTIALS\` là một key chuẩn trong JMX API. Hình thức \`String[]{username,password}\` thường được dùng với JMX RMI management agent khi cơ chế password authentication hỗ trợ. Không phải mọi connector provider đều bắt buộc chấp nhận cùng credentials object; phải hiểu contract của provider triển khai.

**Điều đặc biệt quan trọng:** gửi credentials bằng environment map **không tự động kích hoạt TLS**. Client có thể đã xác thực thành công nhưng vẫn sử dụng kênh không mã hóa nếu server và transport được cấu hình không an toàn.

### 3.1 Password file và access file

Trong mô hình JVM management agent có hỗ trợ các file cấu hình JMX, có thể phân biệt:

- Password file: lưu thông tin credential dùng để xác thực.
- Access file: ánh xạ identity sang quyền như \`readonly\` hoặc \`readwrite\` theo cơ chế runtime.
- Các policy hoặc authenticator khác: có thể cần để áp dụng quyền chuyên biệt hơn.

Không commit password file vào repository, không đưa password vào command line nếu hệ điều hành hoặc hệ thống giám sát có thể đọc process arguments, và kiểm soát permission file theo yêu cầu JVM runtime.

Password/access files là phương án của **JVM management agent**, không phải một tính năng do \`@ManagedResource\` cung cấp. Khi tự tạo \`JMXConnectorServer\`, một số thành phần phải được cấu hình riêng trong environment hoặc factory.

### 3.2 Authentication không đồng nghĩa authorization

Một người đăng nhập hợp lệ chưa chắc có quyền thực hiện operation phá hủy dữ liệu. Nếu access policy chỉ phân biệt hai mức read-only và read-write, nó có thể chưa đủ để định nghĩa quyền theo từng MBean/tenant hoặc từng operation. Khi cần kiểm soát chi tiết, hãy dùng custom authorization layer, management gateway hoặc control plane khác với phân quyền rõ.

## 4. TLS bảo vệ điều gì?

TLS giúp mã hóa lưu lượng trên đường truyền và có thể xác minh server thông qua chứng chỉ. Trong cấu hình có mutual TLS (mTLS), server cũng có thể yêu cầu client trình chứng chỉ để xác thực đầu bên kia, nhưng việc ánh xạ certificate identity sang quyền JMX cần thiết kế riêng.

TLS giải quyết ít nhất ba mục tiêu:

1. **Confidentiality** — giảm nguy cơ bên thứ ba đọc được credentials, attributes và operation parameters.
2. **Integrity** — phát hiện sửa đổi dữ liệu trên đường truyền.
3. **Endpoint authentication** — client có thể xác minh đang kết nối đúng server khi chuỗi chứng chỉ và hostname được kiểm tra.

TLS chỉ có ý nghĩa khi cấu hình được kiểm tra đầy đủ. Một client dùng trust-all certificate manager hoặc tắt hostname verification để “kết nối được” đã làm suy giảm tính xác thực endpoint, tạo nguy cơ man-in-the-middle.

## 5. Keystore, truststore và chứng chỉ

### 5.1 Keystore phía server

Server cần private key và certificate chain để chứng minh danh tính TLS, tùy cách connector/socket factory được cấu hình. Keystore là nơi có thể lưu các thành phần này theo loại định dạng hỗ trợ như PKCS#12.

Không lưu private key hoặc password keystore trong source code. Dùng secret manager hoặc cơ chế quản trị khóa phù hợp, giới hạn quyền đọc file và tránh xuất nội dung keystore vào log.

### 5.2 Truststore phía client

Client cần tin cậy CA hoặc certificate chain của server. Truststore có thể chứa CA certificates dùng để xác minh endpoint. Nếu certificate do tổ chức phát hành, cần phân phối trust anchors theo quy trình chuẩn.

Khi server thay certificate, client có thể gặp TLS handshake failure nếu certificate không được trust, đã hết hạn, thiếu intermediate certificate, sử dụng algorithm bị cấm hoặc hostname không khớp.

### 5.3 Hostname và SAN

Nếu client kết nối đến \`jmx.ops.example.internal\`, chứng chỉ server nên có Subject Alternative Name phù hợp với hostname mà TLS thực sự xác minh. Trong môi trường RMI, host được công bố trong stub có thể khác host trong URL registry. Đây là lý do cần thiết kế endpoint host, DNS, certificates và proxy/tunnel nhất quán.

Không giải quyết lỗi certificate hostname mismatch bằng cách vô hiệu hostname verification trong production. Sửa DNS, certificate SAN hoặc cấu hình endpoint đã công bố cho khớp kiến trúc.

## 6. JMX RMI có thể dùng nhiều kết nối mạng

Với Service URL thường gặp:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi
\`\`\`

Client có thể trải qua hai bước:

\`\`\`text
Client
   |
   | 1. Lookup tại RMI registry, ví dụ port 1099
   v
RMI Registry
   |
   | trả connector stub
   v
Client
   |
   | 2. Kết nối host/port ghi trong stub
   v
RMI ConnectorServer
   |
   v
MBeanServer
\`\`\`

Nếu chỉ registry path được bảo vệ nhưng endpoint RMI thực tế vẫn không được mã hóa hoặc kiểm soát đúng, hệ thống chưa đạt yêu cầu bảo mật. Ngược lại, firewall mở registry port nhưng chặn RMI endpoint khiến JConsole lookup được stub rồi fail khi invoke.

Cần kiểm tra **mọi socket/transport** mà deployment sử dụng: registry, connector endpoint, JNDI provider nếu có và cơ chế callback/notification khi cần. Không suy luận rằng bật một property SSL đơn lẻ luôn tự bảo vệ tất cả thành phần trong mọi kiểu triển khai custom connector.

## 7. Tại sao RMI stub hostname quan trọng?

Một RMI server có thể xuất stub chứa host như \`localhost\`, IP nội bộ container hoặc tên máy không thể phân giải từ client. Khi client nhận stub, bước kết nối tiếp theo có thể thất bại dù lookup registry thành công.

Trong một số thiết lập JVM management agent, property như \`java.rmi.server.hostname\`, \`com.sun.management.jmxremote.port\` và \`com.sun.management.jmxremote.rmi.port\` ảnh hưởng host/port được quảng bá hoặc sử dụng. Những property đó thuộc cấu hình JVM agent/RMI tương ứng, không phải cú pháp phổ quát cho mọi custom JMXConnectorServer.

Với TLS, việc cố định endpoint có giá trị cả cho network policy và certificate verification. Tránh để RMI công bố host không khớp với SAN hoặc hostname trong đường kết nối thực tế.

## 8. Cấu hình JVM management agent an toàn

Một cấu hình JVM management agent có thể bao gồm các property:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=<registry-port>
-Dcom.sun.management.jmxremote.rmi.port=<server-port>
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
\`\`\`

Các dòng chỉ là **khung cấu hình**, không phải lệnh production hoàn chỉnh. Một triển khai thực tế cần password/access files hoặc authenticator, SSL keystore, certificate trust, địa chỉ bind và firewall. Các option, defaults và khả năng SSL registry/connector phụ thuộc JDK distribution và version; phải đối chiếu tài liệu JVM đang vận hành.

Không bật:

\`\`\`text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
\`\`\`

trên endpoint có thể truy cập từ mạng không đáng tin cậy để tiện debug. Điều đó có thể mở quyền quản trị tới nhiều MBean, không chỉ metric mà bạn đang cần xem.

### 8.1 Những điều cần định nghĩa trong deployment

- Cổng registry và cổng RMI server theo JDK/runtime đang dùng.
- Hostname public/internal được RMI stub công bố.
- Bind address/interface thực tế.
- Chính sách truy cập từ network quản trị.
- Cơ chế authentication.
- Certificate, private key, CA trust và rotation.
- Read-only/read-write roles hoặc custom authorization.
- Audit và giới hạn operation có tác dụng phụ.
- Quản lý port, connection và shutdown lifecycle.

## 9. Custom JMXConnectorServer trong Spring application

Một ứng dụng có thể tạo connector server riêng thay vì dùng JVM management agent mặc định.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

JMXServiceURL serviceUrl = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:1099/jmxrmi");

JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        serviceUrl,
        connectorEnvironment,
        server
    );

// connectorEnvironment phải được cấu hình an toàn.
// Phải có registry phù hợp đối với URL dùng /jndi/rmi://...
connector.start();

// Khi shutdown:
// connector.stop();
\`\`\`

Ví dụ là skeleton kiến trúc, không thể đem chạy production khi chưa định nghĩa \`connectorEnvironment\`, SSL socket factories và authentication. Quan trọng là \`MBeanServer\` đã được gắn với connector phải đúng server nơi Spring exporter đăng ký các MBean.

Nếu mỗi Spring context tự start một JMX connector trên cùng port, có thể gây bind failure. Connector nên có một owner rõ, thường thuộc lớp bootstrap/infrastructure thay vì từng domain module.

### 9.1 Custom authenticator

\`JMXConnectorServer.AUTHENTICATOR\` là key dành cho việc cấu hình authenticator ở connector server theo JMX Remote API khi provider hỗ trợ. Một \`JMXAuthenticator\` có thể kiểm tra credential và trả \`Subject\` đại diện identity.

Tuy nhiên custom authenticator không tự áp đặt quyền chi tiết lên mọi operation. Hệ thống cần có chính sách authorization tương ứng, bảo vệ data returned qua MBean và cách ghi audit identity đáng tin cậy.

Nếu dùng một hệ thống danh tính tập trung, không nên viết authenticator tối giản chỉ so sánh hard-coded password rồi trả mọi quyền. Kết hợp secret rotation, chống brute force, logging có redaction và định nghĩa failure modes.

## 10. TLS socket factories và server/client consistency

Với RMI, TLS có thể liên quan đến \`SslRMIClientSocketFactory\` và \`SslRMIServerSocketFactory\` hoặc cấu hình SSL tương đương, tùy agent/provider. Hai phía phải thống nhất transport và trust configuration.

Các điểm cần kiểm chứng:
- Server có cung cấp chứng chỉ hợp lệ không?
- Client có trust certificate chain không?
- Hostname verification có đúng expectation và thực sự được bật không?
- Protocol/cipher suites có tương thích và đáp ứng security baseline không?
- Registry socket và connector socket có được bảo vệ theo kiến trúc không?
- Firewall cho phép các endpoint cần thiết không?
- mTLS (nếu dùng) có ánh xạ certificate identity sang quyền phù hợp không?

Không xem việc client kết nối thành công là bằng chứng chắc chắn mọi hop đã có TLS. Cần xác minh cấu hình và thử nghiệm từ đúng mạng client.

## 11. Spring MBeanServerConnectionFactoryBean phía client

Spring có \`MBeanServerConnectionFactoryBean\` để tạo một \`MBeanServerConnection\` từ Service URL:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class JmxClientConfiguration {

    @Bean
    MBeanServerConnectionFactoryBean remoteConnection() {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi");
        return factory;
    }
}
\`\`\`

Điều này chỉ định nơi kết nối; **không tự bật authentication/TLS**. Khi server yêu cầu credentials hoặc custom SSL socket factories, client phải cung cấp môi trường và trust configuration tương thích. Không lưu password trực tiếp trong Java source hoặc \`application.yml\` commit lên repository.

Nếu JMX remote endpoint có thể tạm unavailable, quyết định rõ việc kết nối xảy ra lúc startup hay được trì hoãn; không để failure giám sát từ xa làm sập luồng nghiệp vụ nếu ứng dụng không yêu cầu điều đó.

## 12. Quyền đọc và quyền điều khiển

Nhiều MBean chứa hai loại khả năng:

\`\`\`text
Read-only:
  getQueueDepth()
  getEffectiveState()
  getHitCount()

State changing:
  requestPause()
  reloadConfiguration()
  clearCache()
  resetStatistics()
\`\`\`

Một tài khoản chỉ cần quan sát không nên có quyền gọi các operation thay đổi trạng thái. Với cơ chế access file của JVM agent, cần xem quyền \`readonly\` và \`readwrite\` theo tài liệu JDK cụ thể. Với yêu cầu phân quyền theo từng domain, operation hoặc tenant, nên có management gateway hoặc custom policy thay vì mặc định một người có quyền write toàn JMX registry.

**Không có annotation Spring nào tự biến một operation JMX thành operation chỉ dành cho administrator.** Security của HTTP controller không tự bảo vệ JMX connector. Quyền cần được thiết kế tại đúng ingress.

## 13. Authentication không đủ nếu MBean lộ dữ liệu nhạy cảm

Ngay cả quyền chỉ đọc cũng có thể nguy hiểm nếu MBean trả:

\`\`\`java
@ManagedAttribute
public String getDatabasePassword() { ... }
\`\`\`

Hoặc trả raw request body, token, customer PII, connection strings chứa secret. Đừng công bố những dữ liệu đó. Thiết kế management interface nhỏ, chỉ gồm summary và metric đã redact.

Ví dụ tốt hơn:

\`\`\`java
@ManagedAttribute
public String getDatabaseConnectionState() {
    return "CONNECTED";
}

@ManagedAttribute
public long getConnectionErrorCount() {
    return 0L;
}
\`\`\`

Việc bảo vệ connector là một lớp, nhưng **giảm bề mặt MBean** là lớp quan trọng khác. Nếu dữ liệu nhạy cảm không được xuất, nguy cơ rò rỉ giảm ngay cả khi credential bị lộ.

## 14. TLS termination và proxy/tunnel

Một số deployment sử dụng VPN, SSH tunnel hoặc network proxy. Không nên mặc định rằng tunnel thay thế hoàn toàn authentication/authorization JMX. Tunnel có thể bảo vệ transport giữa các điểm nhưng endpoint, host được RMI stub công bố và chính sách network vẫn phải được kiểm soát.

Nếu dùng SSH port forwarding tới registry port, RMI stub có thể chỉ đến port/host khác nên client vẫn bị lỗi. Có thể cần cố định RMI port, đảm bảo stub hostname phù hợp đường tunnel và kiểm tra certificate hostname nếu TLS hoạt động ở tầng JMX.

TLS termination trên proxy phải được thiết kế rõ: đoạn từ proxy đến connector có được mã hóa hoặc nằm trong trust boundary phù hợp không? Không bỏ qua một hop không được bảo vệ chỉ vì client nói chuyện HTTPS/TLS với proxy.

## 15. Logging và audit

Một hệ thống quản trị nên có thông tin:
- Thời điểm connection attempt/success/failure.
- Source network hoặc client identity khi đáng tin cậy.
- Authentication outcome (không ghi password).
- Operation invocation có tác dụng phụ.
- ObjectName, operation name, tham số đã được redaction.
- Request ID hoặc correlation ID.
- Kết quả accepted, rejected, succeeded, failed và thời gian.

Ví dụ audit:

\`\`\`text
timestamp: 2026-11-11T08:00:00Z
principal: ops-reader-01
event: jmx.operation.attempt
target: com.example.ops:type=Worker,name=Import
operation: requestPause
result: REJECTED_NOT_AUTHORIZED
\`\`\`

Đây là ví dụ cấu trúc audit; không nên mặc định MBean method tự có trusted principal. Nếu identity chỉ được truyền trong một tham số do caller tự cung cấp, đó không phải bằng chứng xác thực. Identity và quyền nên được nối từ boundary bảo mật thực tế.

## 16. Credential rotation và certificate lifecycle

Một connector an toàn không phải cấu hình một lần rồi bỏ quên. Kế hoạch vận hành cần:
1. Có owner cho credential, keystore và truststore.
2. Có ngày hết hạn certificate và cảnh báo trước hạn.
3. Có quy trình tạo, phân phối và thu hồi credential.
4. Kiểm tra khả năng rotate mà không gián đoạn hoặc có maintenance window rõ.
5. Có cách khôi phục khi truststore không đồng bộ.
6. Có nơi lưu secret an toàn, không đọc từ public config.
7. Ghi lại phiên bản JDK/provider và những property được hỗ trợ.
8. Kiểm thử sau rotation bằng tài khoản thật có quyền tối thiểu.

Với hệ thống nhiều JVM, thay certificate không nhất thiết làm tất cả client cập nhật trust ngay. Có thể cần giai đoạn trust cả CA/certificate cũ và mới có kiểm soát trước khi loại bỏ giá trị cũ. Không kéo dài trạng thái trust rộng hơn cần thiết.

## 17. Chẩn đoán lỗi kết nối có xác thực và TLS

| Triệu chứng | Tầng lỗi có thể | Hướng điều tra |
|---|---|---|
| Connection refused | Port/bind/firewall | Kiểm tra server lắng nghe và đường mạng |
| RMI registry lookup thành công, invoke thất bại | Stub host/port hoặc endpoint TLS | Kiểm tra host/port trong stub và firewall |
| Authentication failed | Credential, authenticator, account policy | Kiểm tra secret và access config |
| \`SSLHandshakeException\` | Certificate chain, protocol, truststore | Kiểm tra TLS logs và trust chain |
| Hostname verification failure | SAN không khớp host | Sửa cert hoặc endpoint naming |
| Client báo unknown protocol/provider | Service URL/provider không hỗ trợ | Kiểm tra JMXServiceURL và JDK modules |
| Connection OK nhưng MBean không thấy | Connector trỏ server khác | So sánh exporter và connector server |
| Read-only client gọi operation thất bại | Authorization hoạt động hoặc policy mismatch | Kiểm tra access role và contract |
| MBean operation timeout | Network/provider hoặc operation lâu | Không retry mù lệnh có side effect |

### Chuỗi kiểm tra đề xuất

\`\`\`text
A. Xác nhận Service URL, DNS, host và port.
B. Kiểm tra registry và RMI endpoint thực tế.
C. Kiểm tra firewall/network policy.
D. Xác minh TLS certificate, trust và hostname.
E. Xác minh authentication và role.
F. Lấy MBeanServerConnection.
G. Query ObjectName expected.
H. Đọc attribute read-only.
I. Chỉ thử operation điều khiển trong môi trường và quyền phù hợp.
\`\`\`

Không khắc phục lỗi handshake bằng cách tắt TLS hoặc cho phép mọi certificate trong production. Cần sửa nguyên nhân thật.

## 18. Test an toàn: positive và negative cases

Một test tích hợp cho connector bảo mật nên kiểm tra:

- Client có credential đúng và truststore đúng kết nối thành công.
- Credential sai bị từ chối.
- Client không có credential bị từ chối nếu server yêu cầu.
- Certificate không đáng tin cậy bị từ chối.
- Hostname không đúng không được chấp nhận khi hostname verification áp dụng.
- Read-only identity không thực thi được operation điều khiển.
- Identity có quyền đúng đọc được MBean expected.
- Không có MBean nhạy cảm ngoài phạm vi công bố.
- Sau khi connector dừng, port/resource được dọn.
- Sau khi certificate hoặc credential được rotate, chính sách mới có hiệu lực.

Không tiến hành thử nghiệm gây side effect trên production chỉ để xác nhận quyền. Dùng MBean thử nghiệm trong môi trường cô lập với operation vô hại.

### Client read-only verification

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;
import java.util.Map;

JMXServiceURL url = new JMXServiceURL(serviceUrl);

try (JMXConnector connector = JMXConnectorFactory.connect(
        url, Map.of(JMXConnector.CREDENTIALS,
                    new String[]{username, password}))) {
    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName expected = new ObjectName(
        "com.example.ops:type=Worker,name=Import");

    if (!connection.isRegistered(expected)) {
        throw new IllegalStateException("Expected MBean not found");
    }

    System.out.println(connection.getAttribute(expected, "State"));
}
\`\`\`

Đây là client skeleton. Nó không tự cấu hình truststore/TLS; giả định môi trường runtime đã cung cấp trust và socket setup tương thích với connector. Không in credentials và không biến read-only connectivity test thành invoke lệnh quản trị nguy hiểm.

## 19. Checklist cho Spring JMX production

### Server

- MBeanServer đích được xác định rõ.
- Connector server có owner và lifecycle.
- Chỉ bind vào network interface cần thiết.
- Authentication bật và có identity management.
- TLS bật theo security baseline.
- Certificate/trust/hostname được xác minh.
- RMI registry/connector ports được giới hạn.
- Không có endpoint JMX không bảo vệ.
- Read-only và control roles phân biệt được theo policy.
- Operation nhạy cảm đã được loại bỏ hoặc kiểm soát.

### Client

- Service URL tới đúng môi trường/JVM.
- Credentials lấy từ secret store, không hard-code.
- Truststore/certificates được cập nhật.
- Không dùng trust-all hoặc bỏ hostname verification.
- Connector đóng khi shutdown.
- Retry/backoff có giới hạn.
- Không retry operation có side effect sau timeout nếu chưa biết kết quả.
- Monitoring và audit đủ để xác định sự cố kết nối.

### Vận hành

- Kiểm tra certificate expiry và credential rotation.
- Giám sát connection failures và auth failures.
- Đánh giá lại quyền khi module/MBean mới được export.
- Kiểm tra JMX access policy sau thay đổi JDK.
- Audit các thao tác có tác dụng phụ.
- Có runbook xử lý lỗi network, RMI stub, TLS, authentication.

## 20. Những hiểu lầm thường gặp

**“Có username/password là connector đã an toàn.”** Chưa đủ; transport cần bảo vệ và server cần authorization phù hợp.

**“Bật TLS nghĩa là mọi client đều được phép gọi operation.”** TLS chỉ bảo vệ transport và xác minh endpoint; quyền là chính sách riêng.

**“@ManagedResource tự dùng Spring Security.”** Không; HTTP security không tự áp dụng lên JMX connector.

**“Chỉ cần mở port registry.”** RMI có thể sử dụng endpoint thứ hai trong stub.

**“Tắt certificate verification để sửa lỗi là chấp nhận được.”** Không phù hợp production; phải sửa trust/hostname/certificate.

**“Chỉ read-only thì không có dữ liệu nhạy cảm.”** Getter vẫn có thể trả secret hoặc PII nếu thiết kế sai.

**“Tách ObjectName domain là phân quyền.”** Domain là namespace, không phải security boundary.

**“Một custom MBeanServer tự tạo isolation hoàn chỉnh.”** Server riêng vẫn có thể cùng JVM và cùng trust boundary; cần connector/access policy phù hợp.

**“Timeout nghĩa là operation chưa chạy.”** Không. Lệnh có thể đã thực thi nhưng response bị mất.

## 21. Bài tập vận dụng

**Bài 1 — Authentication và TLS.** Một service dùng credentials trong \`JMXConnector.CREDENTIALS\` nhưng connector chưa bật TLS. Hãy giải thích rủi ro và những lớp cần bổ sung.

**Bài 2 — RMI trong container.** Client truy cập được registry port 1099 nhưng fail khi gọi MBean. Stub công bố host nội bộ không tới được. Hãy sửa hostname, endpoint port và firewall mà không mở JMX công khai.

**Bài 3 — Chứng chỉ.** Server certificate có SAN cho \`jmx.internal\`, client kết nối tới IP khác. Tại sao hostname verification có thể thất bại và cách sửa hợp lệ là gì?

**Bài 4 — Authorization.** Có hai role: metric-reader và operations-admin. Thiết kế cách chỉ cho metric-reader đọc attributes và operations-admin gọi điều khiển, đồng thời ghi audit.

**Bài 5 — Rotation.** Chứng chỉ JMX sắp hết hạn trên hàng trăm node. Hãy xây dựng thứ tự cập nhật trust, server certificates và client config tránh gián đoạn diện rộng.

**Bài 6 — Security test.** Viết test cho credential đúng/sai, truststore đúng/sai và read-only role không gọi được lệnh reset, dùng MBean vô hại trong môi trường test cô lập.

## Tổng kết

Bảo vệ JMX remote connector là thiết kế nhiều lớp. **Authentication** xác định client, **TLS** bảo vệ dữ liệu và xác minh endpoint, **authorization** giới hạn thao tác, còn **network isolation, audit và lifecycle** giảm rủi ro vận hành. Với JMX RMI, phải chú ý registry lookup và connector stub có thể sử dụng nhiều host/port; tất cả tuyến kết nối cần phù hợp chính sách TLS và firewall. Spring exporter chỉ công bố MBean, không tự bảo vệ remote connector. Một deployment production đáng tin cậy cần thiết lập quyền tối thiểu, quản lý secrets/chứng chỉ, kiểm tra negative security cases và không dùng các cách sửa lỗi như tắt TLS hoặc xác thực.
