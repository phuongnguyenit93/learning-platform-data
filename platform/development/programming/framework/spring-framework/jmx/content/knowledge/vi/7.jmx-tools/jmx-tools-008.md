# Quyền truy cập của công cụ đối với JMX connector

## 1. Mục tiêu và phạm vi

JMX (Java Management Extensions) cho phép một công cụ quản trị như JConsole, VisualVM hoặc một JMX client tự viết truy cập các MBean đã đăng ký trong MBeanServer. Công cụ có thể đọc thuộc tính, ghi thuộc tính, gọi operation và nhận notification nếu kết nối cùng chính sách bảo mật cho phép.

**JMX connector** là điểm truy cập đưa các thao tác quản trị tới MBeanServer. Quyền của công cụ phụ thuộc vào cách connector được cấu hình, thông tin xác thực của phiên kết nối, lớp phân quyền trên server và khả năng mà từng MBean công bố. Việc thấy một MBean trong danh sách không đồng nghĩa mọi thao tác trên MBean đều được phép.

Bài này tập trung vào các câu hỏi vận hành:

- Công cụ kết nối local hay remote vào JVM?
- Ai được phép mở kết nối JMX?
- Công cụ được đọc dữ liệu, sửa attribute, gọi operation hay chỉ nhận notification?
- Phân biệt quyền kết nối với quyền thực hiện thao tác trên MBean như thế nào?
- Cấu hình và kiểm chứng nguyên tắc **least privilege** ra sao?
- Spring Framework JMX tác động đến bề mặt quản trị và quyền truy cập thế nào?

Các ví dụ minh họa dùng JMX/JDK tiêu chuẩn và Spring Framework; thuộc tính cấu hình, cơ chế xác thực, mô hình phân quyền cụ thể có thể khác giữa JDK, connector provider, application server và nền tảng chạy.

## 2. Mô hình kiến trúc quyền truy cập

\`\`\`text
             JConsole / VisualVM / JMX client
                            |
                   credentials / TLS
                            |
                            v
                  JMX connector server
                            |
                 authentication policy
                            |
                 authorization / access
                            |
                            v
                        MBeanServer
                            |
              +-------------+--------------+
              |             |              |
        ObjectName A   ObjectName B   ObjectName C
              |             |              |
         attributes     operations   notifications
              |             |              |
              +------ Spring-managed MBeans -+
\`\`\`

Các lớp kiểm soát cần tách bạch:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Network | Client có thể tiếp cận cổng connector? | Firewall, allowlist, VPN, private network |
| Transport | Đường truyền có được bảo vệ? | TLS, cấu hình remote connector |
| Authentication | Client là ai? | Username/password, cơ chế xác thực của connector/provider |
| Authorization | Danh tính đó được làm gì? | Read-only hoặc read-write, chính sách theo operation nếu hạ tầng hỗ trợ |
| MBean contract | Từng MBean công bố chức năng nào? | \`@ManagedAttribute\`, \`@ManagedOperation\`, Standard MBean interface |
| Application validation | Một thao tác có hợp lệ và an toàn? | Giới hạn tham số, trạng thái cho phép, audit |

**Nguyên tắc:** một lớp không thay thế lớp khác. Ví dụ, firewall giới hạn nguồn kết nối không có nghĩa client được phân quyền đúng; interface chỉ expose một operation không có nghĩa operation đó được bảo vệ bởi role-specific authorization.

## 3. Local JMX và remote JMX

### 3.1. Kết nối local

Công cụ chạy trên cùng máy có thể dùng cơ chế local attach để khám phá và truy cập JVM, tùy JDK, hệ điều hành, quyền người dùng và chính sách attach. JConsole/VisualVM thường hỗ trợ chọn local process khi môi trường cho phép.

Lưu ý:

- Truy cập local thường chịu kiểm soát của hệ điều hành, quyền process và chính sách attach.
- Không nên mặc định rằng mọi người dùng máy đều có thể attach vào mọi JVM, hoặc local connector luôn có cấu hình xác thực giống remote RMI.
- Một số môi trường container, hardened JVM, JDK hoặc policy bảo mật vô hiệu hóa/hạn chế attach.
- Không nên dựa duy nhất vào “chỉ local” khi nhiều người có quyền shell trên cùng host.

### 3.2. Kết nối remote

Remote JMX tạo bề mặt quản trị trên mạng. Với JDK JMX management agent dùng RMI, ứng dụng có thể dùng các system properties như \`com.sun.management.jmxremote.port\`, \`com.sun.management.jmxremote.authenticate\`, \`com.sun.management.jmxremote.ssl\` và các cấu hình liên quan.

Bật remote connector không tự động đồng nghĩa nó được bảo vệ đầy đủ: phải xét xác thực, mã hóa, giao thức RMI, địa chỉ bind và cổng bổ sung. Remote JMX là giao diện quản trị có quyền cao; không nên public trực tiếp lên Internet.

Một cách triển khai an toàn hơn thường là giữ endpoint trong mạng quản trị riêng hoặc sử dụng đường hầm bảo mật có kiểm soát danh tính và truy cập. Việc dùng SSH tunnel chỉ thay đổi đường đi mạng; quyền ở tầng JMX vẫn cần phù hợp.

## 4. Quyền read-only và read-write của JDK management agent

Với cấu hình JMX remote agent của JDK có sử dụng password/access files, file \`jmxremote.access\` có thể gán access level cho từng principal. Hai mức thường thấy là:

- \`readonly\`: cho phép các thao tác quan sát được policy coi là đọc.
- \`readwrite\`: cho phép thao tác thay đổi như ghi attribute hoặc invoke operation, tùy chính sách và tùy chọn được cấu hình.

Ví dụ minh họa file access:

\`\`\`text
monitorRole  readonly
operatorRole readwrite
\`\`\`

Và file password tương ứng (chỉ mô tả cấu trúc, không dùng mật khẩu mẫu trong production):

\`\`\`text
monitorRole  <secret-from-secure-deployment>
operatorRole <another-secret-from-secure-deployment>
\`\`\`

Giá trị trong dấu ngoặc góc là chỗ giữ chỗ; khi cấu hình thực tế phải có credentials hợp lệ, không bao gồm dấu ngoặc. Những file này cần quyền đọc file bị giới hạn theo yêu cầu JDK và không được commit vào repository.

Ví dụ properties dạng khái niệm:

\`\`\`properties
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmxremote.access
-Dcom.sun.management.jmxremote.ssl=true
\`\`\`

Các dòng trên thể hiện các system property JVM riêng lẻ; chúng không phải nội dung một file \`.properties\` thông thường nguyên dạng với tiền tố \`-D\`. Khi chạy JVM, truyền các tham số \`-D...\` vào command startup hoặc cấu hình runtime tương ứng. Nếu dùng cấu hình khác (application server, custom \`JMXAuthenticator\`, custom connector), cách thiết lập có thể không giống ví dụ này.

Mức \`readwrite\` rất rộng: một operation được expose có thể restart subsystem, clear cache hoặc thay đổi trạng thái ứng dụng. Vì vậy cần giới hạn những ai có quyền này và hạn chế chính bề mặt MBean được export.

### Giới hạn của mô hình hai mức

Mô hình \`readonly\`/\`readwrite\` của JDK management agent là một điểm khởi đầu, không phải hệ thống RBAC chi tiết cho từng ObjectName hoặc từng operation. Một số cấu hình có thêm quyền liên quan MBean creation/unregister hoặc registration; khả năng cụ thể phụ thuộc access-file syntax và JDK. Để triển khai chính sách granular theo role/operation cần cơ chế authorization bổ sung hoặc connector/provider có hỗ trợ.

Không nên khẳng định rằng chỉ cần khai báo hai dòng \`monitorRole readonly\`, \`operatorRole readwrite\` là đã có chính sách đầy đủ cho một hệ thống multi-tenant.

## 5. Authentication không giống authorization

**Authentication** xác minh danh tính client, ví dụ username/password hoặc cơ chế khác. **Authorization** quyết định danh tính đã xác minh được thực hiện những JMX request nào.

Ví dụ:

\`\`\`text
monitorRole
   |
   +-- authenticated = true
   |
   +-- queryNames(...)        -> được phép nếu policy read-only cho phép
   +-- getAttribute(...)      -> được phép nếu policy read-only cho phép
   +-- setAttribute(...)      -> bị từ chối
   +-- invoke(...)            -> thường bị hạn chế trong read-only
\`\`\`

Một công cụ có thể đăng nhập thành công nhưng nhận \`SecurityException\` khi gọi một operation, và đó là kết quả có thể đúng theo chính sách. Ngược lại, lỗi không kết nối được có thể xảy ra trước authentication do firewall, DNS, TLS, RMI port hoặc service URL.

Trong logging và vận hành, nên phân biệt:

1. **Connection refused/timeout:** endpoint chưa đến được hoặc connector không hoạt động.
2. **SSL handshake failed:** TLS/certificate/protocol không khớp.
3. **Authentication failed:** credentials hoặc cơ chế xác thực không hợp lệ.
4. **Authorization denied:** đã kết nối nhưng thao tác bị policy chặn.
5. **InstanceNotFound/AttributeNotFound:** MBean/attribute không tồn tại, không nhất thiết là lỗi quyền.
6. **MBeanException/ReflectionException:** lời gọi tới operation hoặc logic implementation có lỗi.

## 6. Tác động của quyền tới thao tác trong công cụ

Bảng sau mô tả kỳ vọng thông dụng; quyết định cuối cùng thuộc policy cụ thể của connector/MBeanServer:

| Thao tác | Ý nghĩa | Chính sách nên cân nhắc |
| --- | --- | --- |
| Liệt kê domain, ObjectName | Khám phá bề mặt quản trị | Có thể tiết lộ cấu trúc ứng dụng; chỉ cấp người cần quan sát |
| \`getMBeanInfo\` | Đọc schema attribute/operation/notification | Metadata có thể tiết lộ tên hệ thống hoặc loại tài nguyên |
| \`getAttribute\` | Đọc dữ liệu vận hành | Read-only nhưng dữ liệu vẫn có thể nhạy cảm |
| \`setAttribute\` | Đổi trạng thái/cấu hình | Quyền ghi; validation và audit riêng |
| \`invoke\` | Chạy operation quản trị | Có thể có side effect lớn, phải kiểm soát chặt |
| \`addNotificationListener\` | Đăng ký nhận notification | Notification payload cũng có thể tiết lộ thông tin |
| \`createMBean\`, \`unregisterMBean\` | Thay đổi registry | Quyền quản trị cao; không cấp mặc định |

Một công cụ như JConsole có thể hiển thị nút Operation hoặc ô nhập Attribute dựa trên metadata, dù policy hiện tại không cho thực hiện. **UI hiển thị chức năng không phải bằng chứng đã được cấp quyền**. Cần thực sự kiểm chứng kết quả request và lỗi trả về.

## 7. Spring Framework JMX và bề mặt quản trị

Spring bổ sung \`MBeanExporter\`, annotation như \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, chiến lược đặt tên và JMX client proxy. Spring giúp khai báo những gì ứng dụng muốn export, nhưng **không tự triển khai một hệ thống RBAC cho remote JMX connector** chỉ vì MBean mang annotation.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=JobControl,name=Main",
    description = "Trạng thái và thao tác quản trị job"
)
public class JobControl {
    private volatile boolean paused;

    @ManagedAttribute(description = "Trạng thái tạm dừng")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Tạm dừng nhận job mới")
    public void pauseNewJobs() {
        paused = true;
    }
}
\`\`\`

Kích hoạt JMX annotation export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
\`\`\`

Ở MBean này, \`Paused\` là attribute quan sát; \`pauseNewJobs()\` là operation thay đổi trạng thái. Một monitoring principal chỉ nên cần đọc \`Paused\`. Principal vận hành được phép thay đổi trạng thái có thể cần invoke operation, nhưng phải được phân quyền ở tầng connector/policy phù hợp.

Nếu ứng dụng chỉ muốn monitoring, nên **không export operation có side effect** chỉ để tiện dùng khi debug. Bỏ operation khỏi management contract thường giảm nguy cơ hơn là công bố nó rồi phụ thuộc hoàn toàn vào một policy rộng.

## 8. Vì sao read-only vẫn có rủi ro?

Ngay cả client chỉ đọc vẫn có thể nhìn thấy:

- Tên host, environment, instance, cấu trúc cluster qua ObjectName.
- Thông tin heap, thread count, JVM arguments và cấu hình runtime.
- Các system properties, đường dẫn và thông tin cấu hình có thể chứa dữ liệu nhạy cảm.
- Metadata của MBean hoặc notification message do ứng dụng tự phát.
- Dữ liệu từ custom MBean nếu developer expose quá nhiều thông tin.

Do đó quyền “readonly” không đồng nghĩa “public”. Không nên đưa token, password, credential hoặc dữ liệu khách hàng vào \`@ManagedAttribute\`, ObjectName, notification hoặc description. Khi cần quan sát, hãy cung cấp số liệu đã tổng hợp, identifier không nhạy cảm và mô tả an toàn.

Đối với dữ liệu đặc biệt nhạy cảm, loại bỏ khỏi MBean contract; việc ẩn một field khỏi UI không phải biện pháp bảo vệ vì JMX client khác vẫn có thể gọi API nếu server cho phép.

## 9. Truy cập remote JMX từ Java client

Một client tiêu chuẩn dùng \`JMXServiceURL\` và \`JMXConnectorFactory\`:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXConnector.CREDENTIALS;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxReader {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        Map<String, Object> environment = new HashMap<>();
        environment.put(
            JMXConnector.CREDENTIALS,
            new String[] {
                System.getenv("JMX_USER"),
                System.getenv("JMX_PASSWORD")
            }
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, environment)) {
            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName memory =
                new ObjectName("java.lang:type=Memory");

            System.out.println(
                connection.getAttribute(memory, "HeapMemoryUsage")
            );
        }
    }
}
\`\`\`

Trong ví dụ chỉ dùng \`JMXConnector.CREDENTIALS\`; import \`javax.management.remote.JMXConnector.CREDENTIALS\` là không cần thiết và một dự án thực tế chỉ cần import \`JMXConnector\`. Các credentials lấy từ môi trường là ví dụ minh họa, không phải cơ chế lưu secrets hoàn chỉnh. Với SSL, cần cấu hình truststore/certificate và lựa chọn connection setup tương ứng với connector của server; không bỏ qua xác thực chứng chỉ để “sửa nhanh” kết nối.

Nếu client có credentials read-only, lời gọi đọc có thể thành công nhưng một lệnh \`invoke\` hoặc \`setAttribute\` có thể bị từ chối. Hành vi cụ thể phụ thuộc access policy thực tế trên server.

## 10. Cấu hình Spring client với MBeanServerConnectionFactoryBean

Spring có \`MBeanServerConnectionFactoryBean\` để tạo kết nối JMX thông qua IoC. Ví dụ cấu hình service URL:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXServiceURL;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class JmxClientConfiguration {
    @Bean
    public MBeanServerConnectionFactoryBean remoteConnection()
            throws Exception {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();

        factory.setServiceUrl(
            new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
            )
        );
        return factory;
    }
}
\`\`\`

Với môi trường có authentication, cần truyền các environment properties của JMX connector vào factory theo API/configuration được Spring hỗ trợ ở phiên bản sử dụng; cấu hình secrets nên lấy từ cơ chế quản lý bí mật phù hợp. Tránh hard-code password trong Java source hoặc file cấu hình version-control.

Client nhận \`MBeanServerConnection\` rồi dùng các API JMX tiêu chuẩn:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class JmxStatusClient {
    private final MBeanServerConnection connection;

    public JmxStatusClient(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public Object readPaused() throws Exception {
        ObjectName name =
            new ObjectName("com.example.jobs:type=JobControl,name=Main");
        return connection.getAttribute(name, "Paused");
    }
}
\`\`\`

Spring giúp quản lý vòng đời và dependency của connection, nhưng **quyền của client vẫn do JMX server quyết định**. Nếu một MBean proxy được tạo qua \`MBeanProxyFactoryBean\`, proxy cũng không vượt qua authorization ở connector.

## 11. Thiết kế role theo nguyên tắc least privilege

Một bảng role vận hành có thể như sau:

| Nhóm sử dụng | Nhu cầu | Hướng phân quyền |
| --- | --- | --- |
| Dashboard monitoring | Đọc metric/trạng thái | Principal chỉ đọc, mạng hạn chế |
| On-call diagnostics | Khám phá MBean, thread/heap metrics | Principal chỉ đọc; xem xét hạn chế dữ liệu nhạy cảm |
| Operator được ủy quyền | Một số operation thay đổi trạng thái | Identity riêng, audit; authorization đủ chi tiết |
| Admin nền tảng | Thay đổi registry hoặc JVM management | Quyền đặc biệt; không cấp mặc định |

Trong hệ thống yêu cầu phân quyền chi tiết “operator chỉ được gọi \`pauseNewJobs\` nhưng không được gọi operation khác”, access file read/write đơn giản có thể không đáp ứng. Phương án là dùng custom connector/forwarder/authorization layer, quản trị qua API khác có RBAC, hoặc tách MBean/endpoint theo phạm vi cho phép. Chính sách phải được kiểm thử trực tiếp; không nên giả định mọi JMX provider hỗ trợ cùng tập quyền.

Thông thường nên cấp credentials riêng cho công cụ thay vì chia sẻ admin password. Có thể thu hồi hoặc xoay vòng từng identity khi một hệ thống monitoring bị xâm phạm hoặc không còn dùng.

## 12. Kiểm chứng quyền bằng ca thử thực tế

Để biết quyền đã hoạt động, cần thử bằng chính danh tính công cụ sẽ sử dụng, không chỉ đọc file cấu hình.

Ví dụ tình huống:

1. Kết nối với monitoring account qua cùng service URL mà dashboard sử dụng.
2. Gọi \`queryNames\` cho domain mục tiêu để xác nhận phạm vi MBean được nhìn thấy.
3. Gọi \`getMBeanInfo\` và \`getAttribute\` cho attribute quan sát dự kiến.
4. Trong môi trường test cô lập, thử một thao tác ghi an toàn để xác nhận account read-only **không** được phép; không dùng operation phá dữ liệu cho bài test.
5. Kết nối bằng operator account và xác nhận duy nhất những quyền đã thiết kế hoạt động (nếu hạ tầng có granular authorization).
6. Kiểm tra log/audit phía server và các lỗi trả về.

Cần đo cả yêu cầu bị từ chối lẫn yêu cầu thành công. Đối với production, hạn chế thử operation có tác động thật; ưu tiên kiểm thử trên staging với MBean an toàn.

### Ví dụ xử lý lỗi authorization

\`\`\`java
import java.io.IOException;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class AttributeReader {
    public static Object read(
            MBeanServerConnection connection,
            ObjectName name,
            String attribute) throws Exception {
        try {
            return connection.getAttribute(name, attribute);
        } catch (SecurityException denied) {
            throw new IllegalStateException(
                "JMX principal is not allowed to read this attribute",
                denied
            );
        } catch (IOException disconnected) {
            throw new IllegalStateException(
                "JMX connector communication failed",
                disconnected
            );
        }
    }
}
\`\`\`

Một môi trường JMX remote có thể đưa lỗi chính sách trong exception wrapper khác; ghi nhận exception chain thực tế để chẩn đoán. Không ghi credentials hoặc toàn bộ connection environment vào log.

## 13. Kết nối RMI: network port và hostname

JMX remote trên RMI có thể dùng một cổng registry và một cổng RMI server khác. Vì vậy mở một cổng TCP nhưng công cụ vẫn timeout không nhất thiết là lỗi quyền. Trong deployment có firewall, container hoặc NAT, cần cấu hình đúng:

- Cổng connector/registry.
- Cổng RMI server nếu management agent hỗ trợ cố định qua \`com.sun.management.jmxremote.rmi.port\`.
- Hostname/RMI advertised address mà client có thể truy cập.
- TLS, certificate và network ACL.
- Xác thực và authorization của JMX.

Có thể cấu hình \`java.rmi.server.hostname\` theo kiến trúc mạng, nhưng không nên dùng điều này để vô tình quảng bá một địa chỉ public không được bảo vệ. Các chi tiết cần khớp JDK và mạng triển khai; không có một chuỗi RMI URL hoạt động cho mọi deployment.

## 14. Những cấu hình không nên sử dụng làm mặc định

\`\`\`properties
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
\`\`\`

Kết hợp này tắt xác thực và mã hóa ở remote JMX, đặc biệt nguy hiểm nếu connector tiếp cận được qua mạng không tin cậy. Không dùng làm mặc định production. Nếu một môi trường phát triển cô lập cần cấu hình đơn giản, vẫn phải giới hạn kết nối nghiêm ngặt và không sao chép nguyên cấu hình sang môi trường khác.

Không nên:

- Expose remote JMX trực tiếp lên Internet.
- Dùng một credential readwrite chung cho dashboard và operator.
- Đưa mật khẩu JMX vào Git, command history, log hoặc tài liệu công khai.
- Tắt TLS certificate validation để bỏ qua lỗi cấu hình.
- Công bố operation nguy hiểm vì cho rằng không ai biết ObjectName của nó.
- Dùng “read-only” như lý do để export mọi thông tin nội bộ.

## 15. Phân biệt JMX với Spring Boot Actuator

Spring Framework JMX cung cấp \`MBeanExporter\`, annotation export, naming strategy, MBean proxy và notification integration. Spring Boot Actuator có các endpoint quản trị có thể exposure qua JMX hoặc HTTP tùy cấu hình; các endpoint này có mô hình enablement/exposure riêng.

Không nên áp dụng một kết luận như “HTTP endpoint được Spring Security bảo vệ, vậy mọi JMX operation cũng tự động được Spring Security bảo vệ”. Hai đường truy cập có thể có cơ chế bảo mật khác nhau. Cần kiểm tra exposure, connector configuration và authorization thực tế của từng đường.

Nếu ứng dụng không cần remote JMX, có thể giữ JMX local hoặc tắt exposure không cần thiết, đồng thời dùng hệ thống metrics/health khác phù hợp với yêu cầu vận hành.

## 16. Tình huống tổng hợp

Giả sử ứng dụng Spring export:

\`\`\`text
com.example.jobs:type=JobControl,name=Main
  Attribute: Paused (read-only)
  Operation: pauseNewJobs() (changes runtime state)

java.lang:type=Memory
  Attribute: HeapMemoryUsage
\`\`\`

Nhóm monitoring muốn quan sát \`Paused\` và heap usage. Nhóm operator thỉnh thoảng cần \`pauseNewJobs()\`.

Thiết kế:

1. Monitoring chỉ có account quan sát và chỉ kết nối từ monitoring network.
2. Operator có identity riêng và chỉ được phép thay đổi điều cần thiết theo policy sẵn có; nếu JMX policy quá rộng, dùng lớp quản trị có granular authorization thích hợp.
3. \`pauseNewJobs\` có validation, log audit và được thiết kế để gọi lặp không gây trạng thái bất ngờ.
4. Không đưa secrets, request payload hoặc dữ liệu khách hàng vào JMX attributes.
5. Remote connector dùng mã hóa và xác thực thích hợp, cổng không công khai.
6. Kiểm tra bằng client thật rằng read-only principal không thể thực hiện thao tác ghi.

Đây là cách phân quyền đi từ nhu cầu quản trị, thay vì cấp một kết nối readwrite cho mọi công cụ chỉ vì thuận tiện.

## 17. Mô hình tư duy

\`\`\`text
Công cụ có kết nối được không?
    |
    +-- Không -> kiểm tra network / service URL / TLS
    |
    +-- Có
         |
         v
Danh tính đã được xác thực?
    |
    +-- Không -> credentials / authenticator
    |
    +-- Có
         |
         v
Thao tác có được authorization policy cho phép?
    |
    +-- Không -> SecurityException / access denied
    |
    +-- Có
         |
         v
MBean có công bố attribute/operation tương ứng?
    |
    +-- Không -> MBeanInfo / AttributeNotFound / ReflectionException
    |
    +-- Có
         |
         v
Kiểm tra validation, trạng thái và tác động thực tế
\`\`\`

**Ghi nhớ:** JMX connector là ranh giới truy cập vào MBeanServer; quyền công cụ cần được bảo vệ ở nhiều lớp gồm network, transport, authentication, authorization, bề mặt MBean và kiểm tra nghiệp vụ. Spring giúp export MBean và kết nối JMX, nhưng không tự cấp hay giới hạn quyền theo vai trò cho mọi công cụ. Hãy cấp quyền tối thiểu, ưu tiên read-only cho monitoring, hạn chế operations có side effect và kiểm chứng quyền bằng đúng danh tính của công cụ.
