# Xác thực, TLS và quyền truy cập Remote JMX Connector trong Spring Framework

## 1. Mục tiêu

Java Management Extensions (JMX) cho phép client quan sát hoặc điều khiển JVM thông qua MBeanServer. Khi client ở ngoài JVM, remote connector trở thành một bề mặt quản trị nhạy cảm: client có quyền phù hợp có thể đọc thông tin runtime và gọi những operation làm thay đổi ứng dụng.

Bài học này trình bày ba trụ cột bảo vệ remote connector:

1. **Authentication (xác thực):** xác minh client được kết nối là ai.
2. **TLS:** mã hóa dữ liệu truyền, xác thực endpoint và có thể dùng client certificate.
3. **Authorization (phân quyền):** quyết định client được thực hiện những thao tác nào sau khi xác thực.

Chúng phải được kết hợp với giới hạn mạng, quản lý bí mật, kiểm soát phạm vi MBean export và giám sát hoạt động. Việc Spring export bean thành MBean **không** đồng nghĩa JMX remote connector đã được bảo vệ.

## 2. Kiến trúc và các ranh giới tin cậy

~~~text
JConsole / Java management client / collector
                  |
                  | JMXServiceURL
                  v
           Remote connector
          /        |         \
 Authentication   TLS      Authorization
          \        |         /
                  v
             MBeanServer
             /    |     \
       java.lang  App MBeans  Framework MBeans
~~~

- **Server:** JVM đăng ký các MBean dưới `ObjectName` và mở connector cho client được phép.
- **Client:** sử dụng `JMXConnector` và `MBeanServerConnection`.
- **Spring exporting:** `MBeanExporter` hoặc `AnnotationMBeanExporter` công bố Spring bean.
- **Spring accessing:** `MBeanServerConnectionFactoryBean` và `MBeanProxyFactoryBean` có thể cung cấp kết nối/proxy phía client.

Ba bước cần xác minh riêng: client kết nối được tới endpoint; client chứng minh danh tính; client có quyền đối với MBean và method cụ thể.

## 3. Authentication, TLS và authorization khác nhau thế nào?

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang truy cập? | User/password hoặc client certificate |
| TLS encryption | Đường truyền có được bảo vệ? | TLS socket |
| Server identity | Có đúng máy chủ mong đợi? | Kiểm tra certificate và tên máy |
| Authorization | Được đọc/ghi/gọi operation nào? | `readonly`, `readwrite`, policy riêng |
| Network control | Ai có thể mở kết nối tới endpoint? | Firewall, private subnet, VPN |
| Audit | Ai đã truy cập/thay đổi gì? | Nhật ký kết nối, operation và kết quả |

**TLS không tự tạo phân quyền.** TLS chỉ ở chế độ xác thực server không xác định ai là client. Ngược lại, chỉ dùng password mà không mã hóa kênh truyền có thể làm lộ thông tin đăng nhập. Quyền `readwrite` cũng không đồng nghĩa mọi operation đều an toàn để gọi.

## 4. Đặc điểm của JMX Remote qua RMI

JDK thường cung cấp JMX remote thông qua Java RMI. Một URL có dạng:

~~~text
service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi
~~~

Cần phân biệt ít nhất hai điểm trong hành trình kết nối:

1. **RMI registry:** client tìm binding của connector.
2. **RMI connector endpoint:** client dùng stub để thực hiện lời gọi tới MBeanServer.

Registry port và connector endpoint port có thể khác nhau. Vì vậy mở cổng 9010 ở firewall chưa chắc đã đủ nếu stub quảng bá endpoint khác hoặc hostname không thể truy cập.

Các thông số phải kiểm tra: registry port, RMI server port, advertised hostname, DNS, NAT, firewall và cách TLS áp dụng ở các chặng. Với management agent của những phiên bản JDK hỗ trợ, `com.sun.management.jmxremote.rmi.port` có thể dùng để ấn định cổng RMI server.

## 5. Xác thực với password và access files

Cơ chế JMX management agent truyền thống của JDK hỗ trợ password file và access file. Ví dụ các JVM properties để hình dung cấu trúc:

~~~text
-Dcom.sun.management.jmxremote=true
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmxremote.access
~~~

Đường dẫn là ví dụ; cần thay bằng vị trí bí mật thực sự do nền tảng quản lý, theo hệ điều hành và JDK đang dùng.

Password file minh họa:

~~~text
monitorRole  <secret-managed-password>
operatorRole <secret-managed-password>
~~~

Access file minh họa:

~~~text
monitorRole  readonly
operatorRole readwrite
~~~

Trong triển khai chuẩn:

- Tài khoản quan sát nên dùng `readonly`.
- Tài khoản cần gọi operation/ghi attribute phải được cân nhắc cấp quyền cao hơn.
- `readwrite` là quyền khá rộng, không phải RBAC chi tiết theo từng nghiệp vụ.
- Password file phải có quyền file system chặt chẽ; trên Unix thường chỉ owner được đọc.
- Không commit password file hoặc secret thật vào repository, container image hoặc log.

**Không nên đặt mật khẩu thật ở tài liệu hoặc command-line flags.** Command line có thể xuất hiện trong process inspection; chọn cơ chế secret provisioning phù hợp môi trường.

## 6. TLS và xác thực danh tính server

Một kết nối TLS hợp lệ cần đảm bảo:

- Server có certificate và private key đúng.
- Client tin tưởng certificate chain thông qua truststore/CA phù hợp.
- Tên DNS kết nối phù hợp certificate theo cơ chế xác minh endpoint của connector.
- Phiên bản TLS/cipher được phép theo policy.
- Certificate và key được luân chuyển theo lịch trước khi hết hạn.

Ví dụ tính năng JVM management agent:

~~~text
-Dcom.sun.management.jmxremote.ssl=true
-Djavax.net.ssl.keyStore=/secure/jmx-server.p12
-Djavax.net.ssl.keyStoreType=PKCS12
~~~

Keystore password và truststore phải được cấp phát bằng phương thức phù hợp thay vì copy giá trị secret vào command line mẫu.

**Đặc biệt với RMI:** không tự suy ra bật `com.sun.management.jmxremote.ssl=true` bảo vệ được cả registry và mọi endpoint tùy biến. Kiểm tra tùy chọn SSL registry, socket factory, cơ chế khởi tạo connector và JDK đang chạy.

Ở phía client, truststore có thể được cấu hình bằng JVM properties:

~~~text
-Djavax.net.ssl.trustStore=/secure/jmx-client-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Chỉ đặt truststore chưa đủ nếu connector không thực sự dùng TLS. Đừng vô hiệu hóa xác minh certificate hoặc sử dụng trust-all để vượt qua lỗi handshake trong production.

## 7. Mutual TLS (mTLS)

mTLS yêu cầu client cung cấp certificate để server kiểm tra, bên cạnh bước client xác thực server:

~~~text
Client --certificate--> Server
Client <--certificate-- Server
~~~

Lợi ích: xác thực máy/dịch vụ bằng chứng chỉ; giảm nhu cầu dùng chung password; tích hợp PKI tổ chức. Đánh đổi: phải cấp phát, thu hồi, gia hạn chứng chỉ; cấu hình truststore/keystore cho cả hai phía; ánh xạ certificate identity sang quyền truy cập.

Một số JDK có các tùy chọn về client authentication khi bật SSL, chẳng hạn `com.sun.management.jmxremote.ssl.need.client.auth`. Cần xác nhận theo phiên bản JDK và thiết lập cụ thể. **mTLS không tự định nghĩa quyền read-only/read-write của principal.** Với yêu cầu chi tiết, cần cơ chế authorization bổ sung.

## 8. Phân quyền sau khi đăng nhập

Giả sử MBean công bố:

~~~text
ObjectName: com.example.orders:type=Queue,name=payments

Attributes:
  PendingCount       long     read-only
  ProcessingEnabled boolean  read/write

Operations:
  pause()
  resume()
  clearQueue()
~~~

Một collector chỉ đọc `PendingCount` không cần quyền `readwrite`. Một người vận hành có quyền `readwrite` vẫn không nhất thiết nên có quyền gọi `clearQueue()` trên mọi hệ thống.

Với access file truyền thống, phân biệt `readonly` và `readwrite` chưa đủ cho các quy tắc như “được pause nhưng không được clear”. Cần xem xét:

- Không export method nguy hiểm nếu không cần.
- Tách MBean quan sát khỏi MBean điều khiển.
- Dùng policy ở tầng connector hoặc `MBeanServerForwarder` khi phù hợp.
- Cung cấp API quản trị chuyên biệt cho tác vụ cần audit/phê duyệt.
- Kiểm tra điều kiện nghiệp vụ ngay trong service, thay vì coi JMX authorization là toàn bộ lớp bảo vệ.

Việc tách hai MBean **không tự tách quyền** nếu connector cho mọi client quyền truy cập giống nhau.

## 9. Spring @ManagedResource không cấu hình bảo mật remote connector

Một Spring bean quản trị có thể khai báo:

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue management"
)
public class PaymentQueueManagement {
    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause queue processing")
    public void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Resume queue processing")
    public void resume() {
        paused = false;
    }
}
~~~

Bean chỉ là một ví dụ minh họa trạng thái; trong ứng dụng thật phương thức phải điều khiển tài nguyên thực.

`AnnotationMBeanExporter` có thể export bean khi được kích hoạt đúng. Nhưng `@ManagedOperation`, `@ManagedAttribute` hay `@ManagedResource` **không bật TLS, xác thực hay phân quyền**. Các lớp đó thuộc connector/platform và logic authorization khác.

Điều này cũng có nghĩa Spring bean name, JMX ObjectName, user đăng nhập connector và quyền operation là các khái niệm tách biệt.

## 10. Client Java kết nối với credentials

Một client kết nối bằng hằng `JMXConnector.CREDENTIALS`:

~~~java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class JmxRemoteClient {
    public static void main(String[] args) throws Exception {
        String username = System.getenv("JMX_USERNAME");
        String password = System.getenv("JMX_PASSWORD");
        if (username == null || password == null) {
            throw new IllegalStateException("Missing JMX credentials");
        }

        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi"
        );

        Map<String, Object> environment = new HashMap<>();
        environment.put(
            JMXConnector.CREDENTIALS,
            new String[] { username, password }
        );

        JMXConnector connector =
            JMXConnectorFactory.connect(url, environment);

        try {
            MBeanServerConnection connection =
                connector.getMBeanServerConnection();
            System.out.println(connection.getDefaultDomain());
        } finally {
            connector.close();
        }
    }
}
~~~

Chỉ dùng ví dụ khi server đã được cấu hình TLS và client có khả năng xác minh certificate server. `JMXConnector.CREDENTIALS` là một hằng String trên interface `JMXConnector`; không import nó như một nested Java type.

Mặc dù ví dụ đọc credentials từ biến môi trường, tổ chức có thể yêu cầu cơ chế secret manager khác. Luôn tránh log các giá trị này.

## 11. Spring client với connection factory và typed proxy

Spring hỗ trợ tạo kết nối bằng `MBeanServerConnectionFactoryBean`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
class RemoteJmxConfiguration {
    @Bean
    MBeanServerConnectionFactoryBean remoteConnection() {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi"
        );
        return factory;
    }
}
~~~

Trong hệ thống thật, connection factory phải được cấp thông số môi trường kết nối, credentials và TLS phù hợp với API Spring phiên bản đang dùng. Sau khi có `MBeanServerConnection`, `MBeanProxyFactoryBean` có thể tạo proxy theo interface:

~~~java
MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
proxy.setServer(connection);
proxy.setObjectName(
    "com.example.orders:type=Queue,name=payments"
);
proxy.setProxyInterface(PaymentQueueControl.class);
~~~

`connection` và `PaymentQueueControl` là các thành phần giả định được cung cấp bởi ứng dụng.

Typed proxy chỉ làm cho lời gọi Java thuận tiện hơn; **nó không làm client có thêm quyền**. Nếu account chỉ được đọc, lời gọi operation qua typed proxy vẫn phải bị từ chối.

## 12. Rủi ro đặc thù khi triển khai trong container và Kubernetes

Trong môi trường container, JMX/RMI có thêm thách thức:

- RMI stub quảng bá hostname nội bộ không truy cập được từ client.
- Registry dùng cổng cố định nhưng RMI endpoint lại dùng cổng động.
- Port-forward có thể đổi hostname thực tế, làm lệch certificate identity.
- Network policy chỉ mở một cổng trong khi JMX cần endpoint khác.
- Secret volumes có đường dẫn hoặc quyền file không đúng.
- Nhiều replica có cùng ObjectName nhưng collector không giữ nhãn target.
- JMX remote bị expose nhầm ra Internet qua Service/Ingress.

Giải pháp là xác định rõ đường đi của client qua DNS, firewall, Service và connector endpoint; ấn định cổng phù hợp nếu cần; xác minh TLS theo đúng đường truy cập; và cấp secret chỉ cho thành phần sử dụng.

Không mặc định rằng port-forward hay mạng nội bộ thay thế hoàn toàn authentication và TLS. Nếu mục tiêu chỉ là thu thập metric, nên cân nhắc một kênh giám sát read-only thay vì cấp remote JMX rộng.

## 13. Xác minh quyền một cách an toàn

Một kế hoạch thử nghiệm hợp lý trong staging:

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Client không có credentials | Bị từ chối |
| Client dùng password sai | Bị từ chối |
| Client không tin certificate server | TLS handshake thất bại |
| Client chỉ có role monitor | Đọc được metric cho phép |
| Role monitor thử operation thay đổi trạng thái trên MBean test | Bị từ chối |
| Client role operator | Chỉ thực thi thao tác được phê duyệt |
| Client từ mạng không được phép | Không truy cập được connector |
| Certificate được thay hợp lệ | Client mới kết nối theo trust policy |
| Secret hết hạn/đã thu hồi | Không còn được chấp nhận |

Không dùng `clearQueue`, xóa dữ liệu hay operation rủi ro trên production chỉ để kiểm tra quyền. Một MBean test có operation vô hại phù hợp hơn.

## 14. Chẩn đoán lỗi theo từng tầng

| Triệu chứng | Nhóm lỗi có thể có | Bước kiểm tra |
| --- | --- | --- |
| Không mở được TCP | Network/firewall/listener | DNS, port, routing |
| Truy cập registry nhưng connection thất bại | RMI endpoint | Advertised host/port và NAT |
| Lỗi handshake | TLS | Chain, truststore, hostname, protocol |
| Server yêu cầu client certificate | mTLS | Client key material và trust policy |
| Authentication failed | Credentials | Secret source, password file, role |
| Đăng nhập được nhưng invoke bị chặn | Authorization | Access policy và permission |
| Kết nối được nhưng thiếu MBean | Registry/ObjectName | Đúng JVM và MBeanServer chưa |
| Proxy lỗi kiểu dữ liệu | JMX contract | MXBean mapping, classpath |
| Lỗi sau rotation | Secret/certificate lifecycle | Đồng bộ hai phía |

Quy trình điều tra nên đi từ transport → TLS → authentication → authorization → MBean metadata → business operation. Việc tắt TLS hoặc authentication để chữa lỗi connection thường vừa không giải quyết đúng nguyên nhân, vừa mở thêm rủi ro.

## 15. Audit, monitoring và quản lý bí mật

Connector dùng trong production nên có khả năng quan sát:

- Ai đã kết nối và kết nối lúc nào (theo thông tin platform có thể cung cấp).
- Endpoint và source của kết nối.
- Những operation quản trị nhạy cảm được gọi.
- Kết quả thành công/thất bại và lỗi.
- Authentication failures bất thường.
- Thời hạn certificate, trạng thái rotation.
- Khả năng kết nối của collector sau deployment.

JMX **không mặc định cung cấp audit log hoàn chỉnh theo business identity**. Có thể cần tích hợp logging ở connector, MBeanServer hoặc service layer. Không ghi password, token, private key hoặc dữ liệu cá nhân nhạy cảm vào log.

Quy trình rotation cần xem xét connector có tự reload file secret/certificate không. Không được giả định thay file trên đĩa sẽ khiến JVM cập nhật ngay. Nếu phải restart connector/JVM, lên kế hoạch bảo đảm monitoring không bị gián đoạn kéo dài.

## 16. Anti-patterns cần tránh

**Tắt authentication và TLS trên endpoint có thể truy cập rộng:**

~~~text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
~~~

Đây là lựa chọn không phù hợp cho một management endpoint có thể truy cập từ mạng không tin cậy.

**Cấp `readwrite` cho monitoring collector:** làm tăng khả năng gọi operation không mong muốn.

**Bật TLS nhưng không kiểm tra certificate:** có thể cho phép client kết nối tới endpoint không phải server đáng tin cậy.

**Lưu password thật trong Git:** tạo rủi ro rò rỉ kéo dài, khó thu hồi đầy đủ.

**Export toàn bộ nghiệp vụ như operation:** làm tăng bề mặt quản trị; chỉ nên xuất tập method đã được lựa chọn.

**Chữa lỗi RMI bằng cách đổi ObjectName:** ObjectName định danh MBean bên trong server, không quyết định địa chỉ kết nối.

**Dùng cùng credential cho mọi tool:** không thể áp dụng quyền tối thiểu và khó truy vết người dùng.

**Tin rằng Spring annotation tự bảo vệ access:** annotation quản trị tạo metadata chứ không cung cấp policy connector.

## 17. Checklist production

Trước khi mở JMX remote:

1. Có nhu cầu remote JMX thật sự, hay chỉ cần metric?
2. Connector chỉ có thể truy cập từ mạng tin cậy?
3. Registry port và RMI endpoint port đã được xác định?
4. RMI advertised hostname phù hợp với đường truy cập của client?
5. TLS được bật, trust chain và server identity đã được xác nhận?
6. Có cần client certificate và ánh xạ quyền hay không?
7. Authentication được cấu hình với bí mật an toàn?
8. Vai trò read-only được tách khỏi quyền điều khiển?
9. Những MBean/operation công bố đã được kiểm tra phạm vi?
10. Không có password/private key trong repository, image hoặc log?
11. Quyền file của password/keystore đúng chính sách?
12. Client được kiểm tra với credential đúng và sai?
13. Hệ thống có logging/audit phù hợp thao tác rủi ro?
14. Certificate và secret rotation có quy trình cụ thể?
15. Collector có timeout/reconnect hợp lý?
16. Operation từ xa xử lý retry và kết quả chưa chắc chắn?
17. Có người chịu trách nhiệm bảo trì connector và MBean export?
18. Có kế hoạch tắt connector khi không còn cần?

## 18. Câu hỏi tự kiểm tra

**1. TLS có thay thế phân quyền không?** Không. TLS bảo vệ transport và endpoint identity; authorization quyết định hành động được phép.

**2. Vì sao mở một cổng RMI registry có thể vẫn không kết nối thành công?** Client còn phải truy cập RMI connector endpoint do stub quảng bá.

**3. `readonly` khác `readwrite` thế nào?** Một role chỉ quan sát, role kia có quyền quản lý rộng hơn theo policy JMX; đây không phải RBAC chi tiết theo operation.

**4. Spring `@ManagedOperation` có tự xác thực client không?** Không. Nó chỉ công bố method qua JMX.

**5. Khi nào nên dùng mTLS?** Khi muốn xác thực danh tính client bằng certificate và có hạ tầng quản lý PKI, nhưng vẫn cần xác định policy authorization.

**6. Vì sao nên tránh đặt credentials trong JVM command line?** Chúng có thể lộ qua process inspection hoặc nhật ký triển khai.

**7. Vì sao không tắt TLS khi gặp lỗi handshake?** Cần sửa trust, certificate, hostname hoặc socket configuration thay vì vô hiệu hóa cơ chế bảo vệ.

**8. Vì sao mọi collector không nên có quyền read-write?** Vì chúng thường chỉ đọc số liệu và quyền điều khiển tăng tác động khi bị lạm dụng.

## 19. Tổng kết

Remote connector mở đường vào MBeanServer của JVM, nơi có thể có cả metric chỉ đọc lẫn operation điều khiển ứng dụng. Muốn sử dụng an toàn, cần triển khai **authentication, TLS và authorization** như các lớp độc lập nhưng bổ trợ nhau, đồng thời bổ sung giới hạn mạng, kiểm soát phạm vi export, audit và quản lý secret.

Đối với JMX/RMI, luôn xác minh **registry, RMI connector endpoint và hostname quảng bá** trước khi kết luận connector lỗi bảo mật. Trong Spring Framework, `MBeanExporter` và annotation giúp công bố MBean nhưng **không thay thế cấu hình bảo mật của JMX remote connector**.

### Tài liệu tham khảo

- Oracle Java Management Agent: https://docs.oracle.com/javase/8/docs/technotes/guides/management/agent.html
- Java SE API — JMXConnectorFactory: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html
- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring API — MBeanServerConnectionFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerConnectionFactoryBean.html
