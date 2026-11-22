# Chẩn đoán lỗi không thấy MBean trong giao diện JMX

## 1. Vấn đề và mục tiêu

Bạn đã tạo MBean trong ứng dụng Spring, log báo khởi động thành công nhưng khi mở **JConsole**, **VisualVM** hoặc một công cụ JMX khác, cây MBeans không hiện đối tượng mong đợi. Lỗi có thể nằm ở nhiều lớp độc lập: ứng dụng chưa đăng ký MBean, đăng ký trên một \`MBeanServer\` khác, \`ObjectName\` không đúng, JMX connector kết nối sai JVM, quyền truy cập bị chặn, hoặc giao diện chưa refresh.

Cách chẩn đoán hiệu quả là đi từ **bằng chứng trong JVM** ra **kênh kết nối** rồi mới tới **giao diện**. Đừng thay đổi cổng, tắt xác thực hoặc sửa hàng loạt annotation trước khi xác định MBean có thực sự được đăng ký hay chưa.

Mục tiêu của bài:

1. Xác nhận Spring có thực sự export MBean.
2. Xác định server nào lưu registration.
3. Tìm chính xác \`ObjectName\`, kể cả domain, property keys và giá trị đã quote.
4. Kiểm tra connection tới đúng JVM/\`MBeanServer\`.
5. Phân biệt lỗi đăng ký, lỗi kết nối, lỗi quyền và lỗi hiển thị.
6. Có cách kiểm tra tự động bằng Java, Spring test và công cụ JMX.

## 2. Mô hình đường đi của MBean

\`\`\`text
Application bean / Management adapter
                  |
              MBeanExporter
                  |
       registerMBean(ObjectName)
                  |
              MBeanServer
                  |
       JMX local attach / connector
                  |
          JMX client connection
                  |
        JConsole / VisualVM / UI
\`\`\`

Mỗi mũi tên là một ranh giới cần có bằng chứng riêng. Nếu \`MBeanServer.isRegistered(name)\` trả \`false\`, việc refresh giao diện sẽ không giải quyết được. Nếu trả \`true\` nhưng client vẫn không thấy, hãy kiểm tra **instance server** mà client được kết nối tới.

**MBeanServer khác JMX connector**: \`MBeanServer\` là registry quản trị bên trong JVM; connector chuyển các thao tác từ client tới một server cụ thể. Mở kết nối remote không tự làm MBean xuất hiện nếu exporter đăng ký nó ở server khác.

## 3. Bảng nhận diện triệu chứng

| Triệu chứng | Nguyên nhân nên kiểm tra trước | Bằng chứng cần lấy |
| --- | --- | --- |
| Tab MBeans hoàn toàn trống | Kết nối tới JVM sai hoặc client không có khả năng truy cập management | PID, JMX URL, trạng thái connection |
| Có \`java.lang\` nhưng thiếu MBean ứng dụng | Exporter chưa đăng ký hoặc tên domain khác | \`queryNames\`, cấu hình exporter |
| MBean hiện trong Java test nhưng không hiện trong công cụ | Test dùng server khác, connector khác hoặc khác process | \`MBeanServer\` identity, PID |
| Chỉ thiếu một MBean | ObjectName trùng/sai, bean không được scan hoặc đăng ký thất bại | Startup exception, \`isRegistered\` |
| Có MBean nhưng không thấy attribute/operation | Interface Standard MBean, MXBean mapping hoặc annotation metadata sai | \`getMBeanInfo\` |
| MBean biến mất sau khi khởi động | Spring context đóng, exporter unregister, bean lifecycle thay đổi | Shutdown logs và registration theo thời gian |
| Remote kết nối thất bại | Host/port, RMI, firewall, authentication/TLS | Connection error và network configuration |
| Tìm bằng tên không khớp | Quote/canonical name hoặc pattern sai | \`ObjectName.getCanonicalName()\` |

## 4. Bước đầu: xác định đúng ứng dụng và JVM

Ở máy có nhiều JVM, JConsole có thể hiển thị nhiều process cùng tên class hoặc cùng tên jar. Hãy đối chiếu PID, command line và thời điểm khởi động.

Các lệnh chẩn đoán thường dùng khi JDK cho phép:

\`\`\`bash
jps -lv
jcmd <PID> VM.command_line
jcmd <PID> VM.system_properties
\`\`\`

\`jps\` hoặc \`jcmd\` có thể bị giới hạn theo quyền OS, container, namespace PID hoặc cấu hình attach. Không suy luận rằng không tìm thấy PID nghĩa là ứng dụng không tồn tại.

Trong môi trường container/Kubernetes:

- Một pod có thể chứa nhiều process hoặc một sidecar riêng; công cụ host phải nhắm đúng process namespace.
- \`localhost\` từ laptop là máy người dùng, không tự trỏ tới container.
- Nếu dùng port-forward, phải cấu hình đúng cổng giao tiếp mà JMX/RMI thực sự sử dụng.
- Không giả định tên service DNS hoặc HTTP port cũng là JMX endpoint.

Ghi nhận trước: **PID/JVM**, **instance/deployment**, **JMX connection URL** và **ObjectName mong đợi**.

## 5. Kiểm tra trực tiếp platform MBeanServer

Trước khi đụng giao diện, dùng mã trong chính JVM ứng dụng để đọc registry:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationProbe {
    public static void printStatus() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName expected = new ObjectName(
            "com.example.orders:type=Worker,name=Primary"
        );

        System.out.println("MBean count = " + server.getMBeanCount());
        System.out.println("Registered = " + server.isRegistered(expected));
        System.out.println("Canonical name = " +
                expected.getCanonicalName());

        ObjectName pattern = new ObjectName("com.example.orders:*");
        for (ObjectName name : server.queryNames(pattern, null)) {
            System.out.println("Found: " + name.getCanonicalName());
        }
    }
}
\`\`\`

Chạy probe **bên trong process cần kiểm tra** (ví dụ qua đoạn startup diagnostics hoặc integration test); chạy một Java process khác sẽ đọc platform server của process khác, vì mỗi JVM có registry riêng.

Kết quả:

- \`isRegistered(expected) == true\`: tên cụ thể đã có trong platform server, chuyển sang kiểm tra connector/client.
- \`false\` nhưng \`queryNames(pattern)\` có tên tương tự: khả năng cao tên không khớp do key, value, quote hoặc domain.
- \`false\` và không có MBean trong domain: kiểm tra exporter và bean discovery; đồng thời xác minh có đang dùng server riêng thay vì platform server.

Có thể liệt kê tạm \`queryNames(null, null)\` để hiểu registry nhưng tránh in vô hạn và tránh đưa tên chứa dữ liệu nhạy cảm ra log production.

## 6. MBeanServer nào đang được sử dụng?

Java cho phép có **nhiều \`MBeanServer\` trong cùng JVM**. Platform server phổ biến:

\`\`\`java
MBeanServer platform =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
\`\`\`

Ứng dụng hoặc framework có thể tạo server mới:

\`\`\`java
MBeanServer custom =
        javax.management.MBeanServerFactory.createMBeanServer(
            "com.example.custom"
        );
\`\`\`

Đăng ký vào \`custom\` không khiến MBean tự xuất hiện ở \`platform\`. Một client local attach thông thường nhìn thấy platform management interface theo cấu hình JVM; còn custom server cần connector phù hợp nếu muốn client ngoài nhìn thấy.

Trong Spring, \`MBeanExporter\` có thể được chỉ định server:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setServer(platform);
\`\`\`

Khi có hơn một server, cách chắc chắn nhất là inject đúng \`MBeanServer\` vào exporter. Nếu có nhiều \`MBeanExporter\`, cần xác định exporter nào chịu trách nhiệm cho bean cụ thể và tránh đăng ký hai lần cùng tên.

Một probe có thể liệt kê server mà \`MBeanServerFactory\` theo dõi:

\`\`\`java
for (MBeanServer server :
        javax.management.MBeanServerFactory.findMBeanServer(null)) {
    System.out.printf("DefaultDomain=%s, count=%d%n",
            server.getDefaultDomain(), server.getMBeanCount());
}
\`\`\`

Danh sách này không nhất thiết bao gồm mọi server được tạo bằng \`newMBeanServer()\`; đừng dựa riêng vào nó để chứng minh không có server khác.

## 7. Kiểm tra cấu hình Spring và Spring Boot

Với Spring Framework thuần, MBean thường được export qua \`MBeanExporter\`. Spring JMX annotation cần được exporter đọc bằng metadata assembler/naming strategy phù hợp. Ví dụ adapter:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Worker,name=Primary"
)
public class WorkerJmxAdapter {
    @ManagedAttribute
    public int getQueueDepth() {
        return 5;
    }
}
\`\`\`

Có \`@Component\` và \`@ManagedResource\` không bảo đảm registration nếu package không được component scan, JMX export không bật, hoặc exporter không nhận diện metadata. Kiểm tra:

1. Bean \`WorkerJmxAdapter\` có xuất hiện trong Spring \`ApplicationContext\` không?
2. Có \`MBeanExporter\` phù hợp không? Nó sử dụng server nào?
3. Các annotation có được assembler đọc không?
4. \`objectName\` thực tế là gì?
5. Có exception từ đăng ký MBean trong startup log không?

Với Spring Boot, \`spring.jmx.enabled=true\` thường bật xuất MBean theo auto-configuration phù hợp phiên bản. Ví dụ:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Kiểm tra cấu hình cuối cùng của môi trường triển khai, vì profile, biến môi trường hoặc command-line arguments có thể ghi đè file properties. Nếu đã tự khai báo exporter, phải xem cách nó tương tác với auto-configuration thay vì mặc định Boot sẽ quản lý tất cả như nhau.

Một số bean được quản lý bởi actuator/metrics có quy trình export riêng; thiếu MBean ứng dụng không nhất thiết nghĩa là tất cả cơ chế giám sát Spring đều hỏng.

## 8. ObjectName: đúng tên mới tìm đúng MBean

Ví dụ hai tên này tương đương vì chỉ khác thứ tự key-property:

\`\`\`text
com.example:type=Worker,name=Primary
com.example:name=Primary,type=Worker
\`\`\`

Nhưng các tên sau có thể khác nhau đáng kể:

\`\`\`text
com.example:type=Worker,name=Primary
com.example:type=Worker,name="Primary"
com.example:type=Worker,name=primary
com.example:type=Workers,name=Primary
\`\`\`

\`ObjectName\` giữ sự khác biệt về value quoted/unquoted và chữ hoa/chữ thường. Khi một value được tạo qua \`ObjectName.quote\`, hãy tạo probe theo cùng quy tắc.

\`\`\`java
String rawName = "Order,Priority";
ObjectName expected = new ObjectName(
    "com.example:type=Queue,name=" + ObjectName.quote(rawName)
);
\`\`\`

Để tìm rộng hơn:

\`\`\`java
ObjectName pattern = new ObjectName("com.example:*");
java.util.Set<ObjectName> found =
        platform.queryNames(pattern, null);
\`\`\`

Không đưa \`*\` vào tên registration một cách vô ý, vì đó có thể là pattern thay vì tên cụ thể. Nếu nhiều MBean có cùng domain, hãy dùng \`getCanonicalName()\` để so sánh ổn định.

## 9. Phân biệt Standard MBean, MXBean và Spring-managed MBean

Một class Java có tên \`CacheMonitor\` không tự động được JMX chấp nhận chỉ vì nó có method \`getSize()\`. Với **Standard MBean**, thông thường cần interface \`CacheMonitorMBean\` công khai, được implementation thực hiện:

\`\`\`java
public interface CacheMonitorMBean {
    int getSize();
    void clear();
}

public class CacheMonitor implements CacheMonitorMBean {
    public int getSize() { return 7; }
    public void clear() { }
}
\`\`\`

Nếu muốn đăng ký một implementation có tên/interface không khớp quy ước, có thể dùng \`javax.management.StandardMBean\` để truyền interface quản trị một cách tường minh:

\`\`\`java
CacheMonitor monitor = new CacheMonitor();

javax.management.StandardMBean wrapped =
    new javax.management.StandardMBean(
        monitor, CacheMonitorMBean.class
    );

platform.registerMBean(
    wrapped,
    new ObjectName("com.example:type=Cache,name=Primary")
);
\`\`\`

MXBean có quy tắc mapping kiểu dữ liệu riêng. Spring annotation-driven export có thể dùng assembler để biểu diễn bean thành MBean mà không phải luôn khai báo interface đặt tên theo Standard MBean. Chọn đúng mô hình đăng ký, kiểm tra startup exception như \`NotCompliantMBeanException\`, rồi xác minh \`MBeanInfo\`.

## 10. MBean có tồn tại nhưng thiếu attribute hoặc operation

Đây là lỗi khác với “không thấy MBean”. Truy vấn metadata:

\`\`\`java
javax.management.MBeanInfo info =
        platform.getMBeanInfo(expected);

System.out.println(info.getClassName());

for (javax.management.MBeanAttributeInfo attr :
        info.getAttributes()) {
    System.out.println("Attribute: " + attr.getName());
}

for (javax.management.MBeanOperationInfo op :
        info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}
\`\`\`

Nếu metadata không có attribute/operation, nguyên nhân có thể là method không nằm trong MBean interface, annotation bị bỏ qua, kiểu dữ liệu không mapping được hoặc bean được export dưới một mô hình khác dự kiến.

Nếu metadata có nhưng thao tác đọc thất bại, kiểm tra quyền truy cập, exception trong getter và kiểu dữ liệu trả về. Một getter chậm hoặc ném lỗi thường khiến giao diện hiển thị không đầy đủ nhưng không làm mất bản thân registration.

## 11. Kiểm tra JConsole và VisualVM

Với **JConsole**, quy trình cơ bản:

1. Mở đúng Java process ở local list, hoặc nhập đúng JMX service URL từ xa.
2. Mở tab MBeans (nếu công cụ/connection hỗ trợ).
3. Mở rộng domain của ứng dụng.
4. Kiểm tra \`type\`, \`name\` và các key khác thay vì chỉ nhìn class name.
5. Reconnect hoặc refresh khi ứng dụng vừa đăng ký MBean sau thời điểm client kết nối.

Với **VisualVM**, khả năng duyệt MBeans có thể phụ thuộc phiên bản và plugin hỗ trợ MBeans. Một công cụ không hiển thị tab MBeans không chứng minh server thiếu registration; dùng JConsole hoặc client JMX khác để kiểm tra chéo.

Để tách lỗi giao diện khỏi lỗi server, dùng một JMX client đọc \`queryNames\` và \`getMBeanInfo\` trực tiếp. Nếu API trả dữ liệu nhưng giao diện không hiển thị, vấn đề nằm ở client/plugin, bộ lọc hoặc thời điểm refresh.

## 12. Remote JMX: kiểm tra connector và RMI

Với remote JMX qua RMI, một cấu hình thường gặp dùng thuộc tính JVM:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=<reachable-host>
\`\`\`

Ví dụ này chỉ minh họa các biến liên quan đến endpoint, **chưa phải cấu hình triển khai bảo mật hoàn chỉnh**. Cần cấu hình authentication, SSL/TLS và network access phù hợp. Không dùng \`authenticate=false\` hoặc \`ssl=false\` như cách chữa lỗi nhanh trong production.

RMI có thể liên quan nhiều endpoint nếu chưa cố định RMI port. Tình trạng kết nối tới registry port thành công nhưng sau đó treo/thất bại có thể do server trả hostname không thể truy cập hoặc firewall chặn cổng thứ hai.

Khi client remote báo lỗi:

- **Connection refused:** kiểm tra host, port listener và process.
- **Timeout:** kiểm tra định tuyến, NAT, container port mapping và firewall.
- **Authentication failed:** kiểm tra credentials và chính sách connector.
- **TLS handshake failure:** kiểm tra truststore/certificate và giao thức được cho phép.
- **Kết nối được nhưng thiếu domain:** kiểm tra server mà connector đang trỏ tới và các quyền truy vấn.

**Tách rõ lỗi mạng khỏi lỗi MBean**: nếu chưa tạo được JMX connection, không thể kết luận registration có hay không từ giao diện.

## 13. Kiểm tra bằng JMXConnector client

Để xác định client thực sự nhìn thấy gì, dùng đoạn mã Java đọc qua \`MBeanServerConnection\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxProbe {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName pattern = new ObjectName("com.example:*");

            for (ObjectName name :
                    connection.queryNames(pattern, null)) {
                System.out.println(name.getCanonicalName());
            }
        }
    }
}
\`\`\`

Chạy probe từ **cùng nơi mà giao diện JMX đang chạy** để tái hiện đường mạng và quyền truy cập. Với môi trường cần credentials/TLS, truyền environment map cho \`JMXConnectorFactory.connect\` theo cấu hình thực, tránh hard-code password trong nguồn.

Nếu probe remote thấy MBean còn giao diện không thấy, tập trung vào client UI. Nếu probe trong-process thấy nhưng remote không thấy, kiểm tra connector, MBeanServer mà connector export và quyền truy cập.

## 14. Trường hợp Spring proxy và vòng đời

Một bean có thể được bọc bởi AOP proxy, scoped proxy hoặc bị điều kiện cấu hình loại bỏ. Điều này tác động tới cách exporter nhận diện annotation, interface hoặc tên bean. Nếu lỗi xuất hiện chỉ khi bật transaction, security hoặc caching, hãy kiểm tra loại proxy thực tế và các interface mà exporter thấy.

Đối với lifecycle:

- Spring context khởi tạo exporter sau khi bean quản trị sẵn sàng.
- Khi context đóng, exporter có thể unregister MBean đã đăng ký.
- DevTools restart, test context, hot reload và container redeploy có thể làm MBean xuất hiện rồi biến mất.
- Tạo hai context cùng dùng platform server và cùng ObjectName có thể gây collision.
- Một MBean được đăng ký thủ công ngoài Spring có thể không được exporter dọn tự động.

Không xử lý va chạm bằng cách bật chế độ ghi đè MBean vô điều kiện; hãy xác định ai sở hữu registration và khi nào phải unregister.

## 15. Kiểm thử tích hợp cho tình huống "không thấy MBean"

Một integration test nên tạo Spring context, lấy đúng \`MBeanServer\` và xác minh registration:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;

class JmxRegistrationAssertions {
    static void assertWorkerExposed(MBeanServer server)
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Worker,name=Primary"
        );

        assertTrue(server.isRegistered(name));
        var info = server.getMBeanInfo(name);

        assertTrue(
            java.util.Arrays.stream(info.getAttributes())
                .anyMatch(a -> "QueueDepth".equals(a.getName()))
        );
    }
}
\`\`\`

Test này không cần mở JConsole, giúp phát hiện lỗi cấu hình Spring sớm. Nếu yêu cầu của hệ thống bao gồm remote JMX, thêm một test với connector thử nghiệm trên môi trường cô lập và xác minh \`queryNames\` qua \`MBeanServerConnection\`; không mở remote management trên môi trường production chỉ để chạy test.

## 16. Chuỗi quyết định chẩn đoán

\`\`\`text
Không thấy MBean trên UI
  |
  +-- Kết nối đúng JVM/PID chưa?
  |       +-- Không --> chọn đúng process/endpoint
  |
  +-- In-process isRegistered(ObjectName) == true?
  |       |
  |       +-- Không --> bean tồn tại trong Spring context?
  |                       |
  |                       +-- Không --> component scan/profile/condition
  |                       +-- Có --> exporter/annotation/MBean compliance
  |
  +-- Đúng MBeanServer không?
  |       +-- Không --> chỉ định server/connector đúng
  |
  +-- Client queryNames() nhìn thấy?
  |       +-- Không --> connector, quyền, kết nối, namespace
  |
  +-- Client API thấy nhưng UI không hiện?
          +-- refresh, tree filter, phiên bản/plugin, metadata
\`\`\`

Đi theo sơ đồ này sẽ giữ từng giả thuyết có thể kiểm chứng. Một dấu hiệu “không thấy” có thể bắt nguồn từ nhiều nguyên nhân hoàn toàn khác nhau; ghi lại bằng chứng tại từng ranh giới trước khi đổi cấu hình.

## 17. Các lỗi tư duy cần tránh

- **“Không thấy trên UI nghĩa là bean không tồn tại.”** UI là lớp cuối cùng; đọc trực tiếp \`MBeanServer\` để xác nhận.
- **“Bật \`spring.jmx.enabled=true\` là client remote sẽ kết nối được.”** Export nội bộ và remote connector là hai việc khác nhau.
- **“Tên class chính là ObjectName.”** Domain và key-property xác định JMX ObjectName, không nhất thiết trùng class.
- **“Có platform MBeanServer là mọi custom server sẽ hiện chung.”** Mỗi server có registry riêng.
- **“Thêm \`@ManagedResource\` đủ để được đăng ký.”** Exporter và metadata mapping phải thực sự hoạt động.
- **“Nên tắt security để kiểm tra.”** Chẩn đoán bằng probe, log và cấu hình được kiểm soát; không vô hiệu kiểm soát truy cập.
- **“Reconnect luôn sửa được.”** Nếu \`isRegistered\` false, reconnect không thay thế việc sửa registration.

## 18. Ghi nhớ

Khi một MBean không hiện trong JConsole hoặc VisualVM, hãy xác nhận theo thứ tự: **đúng JVM → bean được Spring tạo → exporter đăng ký đúng ObjectName → đúng MBeanServer → connector tới đúng server → client API nhìn thấy → giao diện hiển thị**. \`isRegistered\`, \`queryNames\` và \`getMBeanInfo\` là những công cụ chẩn đoán cốt lõi. Chúng giúp phân biệt lỗi đăng ký, lỗi tên, lỗi kết nối và lỗi giao diện mà không phải đoán mò từ màn hình.
