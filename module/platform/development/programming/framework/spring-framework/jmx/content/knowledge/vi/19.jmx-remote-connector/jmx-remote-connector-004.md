# RMI connector và các thành phần liên quan trong Spring Framework JMX

## 1. RMI connector trong hệ sinh thái JMX

JMX (Java Management Extensions) quản lý các đối tượng MBean trong một MBeanServer. Khi ứng dụng Spring muốn cho phép JConsole, VisualVM hoặc một client chạy ở JVM khác truy cập MBean, cần mở một **JMX connector**. Giao thức thường dùng là RMI (Java Remote Method Invocation).

Cần phân biệt bốn thành phần:
- **MBeanServer:** registry chứa MBean và thực thi các thao tác như getAttribute, invoke, queryNames.
- **JMXConnectorServer:** đầu phía server, chuyển các yêu cầu từ client thành lời gọi tới MBeanServer.
- **RMI Registry:** dịch vụ tra cứu tên, giúp client tìm stub của remote connector.
- **JMXConnector và MBeanServerConnection:** phía client, cho phép mã Java truy cập MBean từ xa.

Spring MBeanExporter đưa các bean vào MBeanServer; việc export bean **không tự động mở cổng remote JMX**. Connector cần được cấu hình và khởi động riêng, hoặc được JVM management agent cung cấp.

## 2. Luồng kết nối hai giai đoạn

Mô hình thường gặp:

~~~text
                   JVM ứng dụng Spring
      +-------------------------------------+
      | MBeanExporter -> MBeanServer        |
      |                         ^           |
      |                         |           |
      |                JMXConnectorServer   |
      |                         |           |
      +-------------------------|-----------+
                                | RMI stub
                          RMI Registry
                                ^
                                | 1. lookup "jmxrmi"
                                |
                JConsole / JMXConnector
                                |
                                | 2. dùng địa chỉ trong stub
                                v
                       RMI endpoint
                                |
                                v
                     MBeanServerConnection
~~~

RMI Registry chỉ là nơi tra cứu stub, không chứa MBean. Client thường kết nối tới registry trước, sau đó gọi tới endpoint thực tế được stub quảng bá. Chính vì vậy **mở được registry port không chứng minh đã kết nối được JMX**.

Một địa chỉ service URL phổ biến:

~~~text
service:jmx:rmi:///jndi/rmi://host.example.internal:9010/jmxrmi
~~~

Trong đó:
- \`service:jmx:rmi\` chọn JMX connector protocol RMI.
- \`/jndi/rmi://host:9010/jmxrmi\` chỉ nơi tra cứu đối tượng remote bằng JNDI/RMI.
- \`jmxrmi\` là tên binding thường dùng khi JVM management agent cung cấp connector.
- RMI stub trả về có thể chứa **host và port khác** với endpoint lookup.

Không diễn giải service URL như một HTTP URL hoặc cho rằng mọi gói mạng sẽ đi qua cổng 9010.

## 3. MBeanServer và JMXConnectorServer

Tạo hoặc lấy platform server:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();
~~~

Một JVM cũng có thể chứa MBeanServer do ứng dụng tự tạo:

~~~java
import javax.management.MBeanServerFactory;

MBeanServer custom =
    MBeanServerFactory.createMBeanServer("com.example.management");
~~~

Khi khởi tạo connector, phải gắn nó vào **cùng server** mà MBeanExporter đã đăng ký MBean. Nếu exporter ghi vào custom server nhưng connector đọc platform server, client có thể kết nối thành công mà không thấy các MBean của ứng dụng.

Connector được tạo qua JMX API:

~~~java
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

MBeanServer server = /* server đã cấu hình */;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        url, Map.of(), server
    );

connector.start();

// Khi ứng dụng dừng:
// connector.stop();
~~~

Ví dụ này giả định đã có RMI Registry phù hợp ở cổng 9010. Nó chỉ minh họa wiring, **không phải cấu hình bảo mật hoàn chỉnh**: cần xác thực, phân quyền, TLS và cô lập mạng cho endpoint quản trị.

## 4. RMI Registry dùng để làm gì?

RMI Registry ánh xạ một tên như \`jmxrmi\` tới remote reference. Có thể tạo registry trong cùng JVM:

~~~java
import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

Registry registry = LocateRegistry.createRegistry(9010);
~~~

Nếu cổng đã bị một process khác chiếm dụng, thao tác tạo registry có thể thất bại. Trong container/application server, cần xác định rõ component nào sở hữu registry; không nên tạo một registry mới cho mỗi Spring bean khi đã có registry chung.

Khi JMXConnectorServer start, connector có thể đăng ký stub vào registry qua cấu hình URL JNDI. Client dùng tên binding để lấy stub và thực hiện bước kết nối thứ hai.

Registry không chịu trách nhiệm:
- quyết định những MBean được xuất;
- cấp quyền gọi từng operation;
- chuyển đổi Spring bean thành Standard MBean;
- bảo đảm địa chỉ RMI trong stub có thể truy cập từ bên ngoài.

## 5. Registry port khác RMI server port

Một điểm đặc trưng của JMX RMI là có thể xuất hiện hai kết nối TCP:

1. Kết nối tới **registry port** để thực hiện JNDI lookup.
2. Kết nối tới **RMI connector endpoint** được mô tả trong stub.

Ví dụ cấu hình JVM management agent:

~~~text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.example.internal
~~~

Ở mô hình này, client cần truy cập cổng 9010 để lookup và cổng 9011 để gọi RMI endpoint. Nếu chỉ cho phép 9010 qua firewall, lookup có thể hoàn thành nhưng các lời gọi sau đó thất bại.

Các thuộc tính \`com.sun.management.jmxremote.*\` dành cho JVM management agent; chúng không nhất thiết điều khiển connector tùy chỉnh do ứng dụng tự tạo bằng \`JMXConnectorServerFactory\`. Với connector tự tạo, cần cấu hình endpoint port/socket factory theo API và implementation đang dùng.

Không chọn một port ngẫu nhiên trong production nếu network policy yêu cầu whitelist cổng cố định.

## 6. java.rmi.server.hostname và địa chỉ quảng bá

RMI stub có thể chứa host mà client phải kết nối. Nếu máy chủ chạy trong container, địa chỉ IP nội bộ container thường không truy cập được trực tiếp từ máy quản trị.

Ví dụ lỗi:

~~~text
Laptop -> localhost:9010 (port-forward) -> RMI Registry
Registry -> trả stub có host 172.18.0.5:9011
Laptop -> 172.18.0.5:9011 -> timeout
~~~

Lệnh kiểm tra cổng registry vẫn có thể báo thành công, nhưng client không thể dùng stub.

Cần xác định:
- địa chỉ RMI được quảng bá;
- cổng thực tế trong stub;
- đường truy cập của client;
- NAT, tunnel, firewall, Docker port mapping hoặc Kubernetes port-forward;
- DNS/hostname có khả dụng với client không.

\`java.rmi.server.hostname\` có thể được sử dụng để điều khiển hostname được quảng bá cho đối tượng RMI trong cấu hình phù hợp. Với client từ xa, không đặt hostname thành \`localhost\` trừ khi tunnel được thiết kế khiến địa chỉ loopback thực sự là endpoint đúng ở phía client.

Trong Kubernetes, load balancing có thể đưa registry lookup và kết nối RMI tiếp theo tới hai pod khác nhau. Đối với JMX RMI, kết nối/tunnel ổn định tới một pod cụ thể thường ít bất ngờ hơn.

## 7. Client Java truy cập MBeanServer từ xa

Client tạo JMXServiceURL, kết nối và lấy MBeanServerConnection:

~~~java
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
            MBeanServerConnection remote =
                connector.getMBeanServerConnection();

            System.out.println("MBean count = " +
                remote.getMBeanCount());

            ObjectName pattern =
                new ObjectName("com.example:*");

            for (ObjectName name :
                    remote.queryNames(pattern, null)) {
                System.out.println(name.getCanonicalName());
            }
        }
    }
}
~~~

Chạy probe từ cùng vị trí mạng với công cụ đang gặp lỗi để tái hiện DNS, firewall, NAT và chính sách xác thực. Nếu server bật authentication hoặc TLS, cần cung cấp cấu hình client tương ứng.

Client không cần có class implementation của bean để truy vấn MBean chuẩn. Nó chỉ cần biết \`ObjectName\`, tên attribute/operation, chữ ký tham số và những kiểu dữ liệu có thể xử lý.

## 8. Spring Framework: nối exporter và connector vào cùng server

Spring Framework có \`MBeanExporter\` để xuất bean và \`ConnectorServerFactoryBean\` để quản lý connector theo lifecycle Spring. Ví dụ minh họa:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.ConnectorServerFactoryBean;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    MBeanExporter mbeanExporter(MBeanServer server) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        // Chọn beans và metadata theo cấu hình thực tế.
        return exporter;
    }

    @Bean
    ConnectorServerFactoryBean connectorServer(
            MBeanServer server) throws Exception {
        ConnectorServerFactoryBean factory =
            new ConnectorServerFactoryBean();
        factory.setServer(server);
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );
        return factory;
    }
}
~~~

Đây chỉ là skeleton cho thấy cả exporter và connector dùng chung một instance \`MBeanServer\`. Để chạy được, cần registry tạo trước, security environment và cấu hình đăng ký bean thực tế. Trong Spring Boot, auto-configuration JMX hoặc JVM management agent có thể đã tạo những thành phần tương tự; không khởi tạo thêm một connector/exporter trùng lặp khi chưa rõ ownership.

**MBeanExporter không đồng nghĩa remote connector**: một MBean có thể được export đầy đủ dù không mở bất kỳ JMX remote port nào.

## 9. Bảo mật remote connector

Remote JMX có thể đọc thông tin JVM và thực thi những operation ảnh hưởng ứng dụng. Phải thiết kế nó như một endpoint quản trị nhạy cảm.

### Xác thực

Client có thể đưa credentials vào environment:

~~~java
import java.util.Map;
import javax.management.remote.JMXConnector;

Map<String, ?> env = Map.of(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);
~~~

Sau đó:

~~~java
try (JMXConnector connector =
        JMXConnectorFactory.connect(url, env)) {
    // ...
}
~~~

Không hard-code password trong mã nguồn hoặc đưa vào log. Server phải thực sự được cấu hình cơ chế xác thực tương ứng; chỉ gửi credential từ client không tự bật bảo vệ server.

### Mã hóa

Cần bảo vệ cả những kênh mạng liên quan tới registry/bootstrap và endpoint remote. Việc kiểm tra certificate, truststore và hostname phải tương thích với mô hình RMI đang triển khai. Không suy luận rằng có một kênh TLS là mọi kênh liên quan đều đã được bảo vệ.

### Phân quyền và giới hạn kết nối

Connector cần được đặt trong mạng quản trị hoặc tunnel có kiểm soát, chỉ cho phép những client cần thiết truy cập. Authentication không tự bảo đảm từng operation được phân quyền theo nghiệp vụ; với thao tác thay đổi trạng thái, nên có authorization và audit ở lớp ứng dụng.

Không mở cổng JMX ra Internet. Không dùng \`authenticate=false\` hoặc \`ssl=false\` như một phương án sửa lỗi production.

## 10. Notification đi qua RMI connector

Ngoài đọc attribute và invoke operation, client có thể đăng ký JMX notification listener:

~~~java
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Primary"
);

NotificationListener listener =
    (notification, handback) -> {
        System.out.println(notification.getType());
    };

remote.addNotificationListener(
    name, listener, null, null
);
~~~

MBean phải thực sự hỗ trợ notification. Với remote JMX, callback không nên được xem như một lời gọi đồng bộ bảo đảm xảy ra ngay sau khi operation hoàn tất: quá trình vận chuyển và khả năng kết nối có thể gây độ trễ hoặc mất kênh. Khi client shutdown, gỡ listener khi có thể và đóng \`JMXConnector\`; sau reconnect, kiểm tra có cần đăng ký lại listener hay không.

## 11. Lifecycle và redeploy

Có ít nhất ba loại tài nguyên cần sở hữu rõ ràng:

- **MBean registrations:** do \`MBeanExporter\` hoặc module quản trị sở hữu.
- **JMX connector endpoint:** do \`JMXConnectorServer\` hoặc Spring \`ConnectorServerFactoryBean\` sở hữu.
- **RMI Registry:** do JVM management agent, ứng dụng hoặc infrastructure tạo.

Nếu context Spring shutdown nhưng connector/registry vẫn giữ tham chiếu tới classloader cũ, ứng dụng redeploy có thể gặp lỗi cổng đã chiếm dụng, stub không còn hợp lệ hoặc memory leak.

Một trình tự shutdown hợp lý:

1. Ngừng nhận yêu cầu quản trị mới ở endpoint do module quản lý.
2. Stop connector do module tạo.
3. Gỡ listener/notification handler do module đăng ký.
4. Để exporter unregister MBean do context sở hữu.
5. Dọn registry nếu thực sự thuộc module, không xóa registry dùng chung.

Với registry tạo bằng \`LocateRegistry.createRegistry\`, việc gỡ/unexport phải tuân theo API RMI và ownership. Không cố đóng một registry do JVM/application khác sở hữu.

## 12. Lỗi thường gặp

| Hiện tượng | Lớp lỗi cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| Connection refused đến registry | Sai host/port hoặc registry không chạy | Kiểm tra listener và URL |
| Registry lookup thành công rồi timeout | RMI stub quảng bá host/port không tới được | Kiểm tra RMI endpoint, firewall, NAT |
| NotBoundException | Binding \`jmxrmi\` không có trong registry | Xác minh connector đã start và tên binding |
| Address already in use | Trùng registry/connector port khi startup | Kiểm tra process owner và lifecycle |
| Authentication failed | Credentials hoặc server policy sai | Kiểm tra cấu hình auth và secret |
| TLS handshake failed | Certificate/truststore/protocol không tương thích | Kiểm tra TLS cả phía client/server |
| Chỉ thấy MBean \`java.lang\` | Connector dùng server khác exporter | So sánh MBeanServer instance |
| Có MBean nhưng không thấy operation | Contract/assembler/mapping không khớp | \`getMBeanInfo\` |
| Kết nối cũ hỏng sau redeploy | Connector hoặc registry cũ còn sống | Stop/cleanup, reconnect |
| Chỉ lỗi khi chạy trong container | Địa chỉ quảng bá nội bộ hoặc port thứ hai | Kiểm tra hostname và forward hai kênh |

Không đọc một lỗi network rồi suy ngay rằng Spring exporter chưa đăng ký MBean. Trước hết xác minh registry và endpoint, sau đó mới kiểm tra MBeanServer.

## 13. Quy trình chẩn đoán từng lớp

\`\`\`text
Ứng dụng có MBean?
  |
  +-- Không -> kiểm tra exporter, ObjectName, MBean compliance
  |
  +-- Có -> connector dùng đúng MBeanServer?
             |
             +-- Không -> sửa wiring
             |
             +-- Có -> registry lookup thành công?
                        |
                        +-- Không -> host/port/binding
                        |
                        +-- Có -> RMI endpoint trong stub tới được?
                                   |
                                   +-- Không -> hostname/NAT/firewall
                                   |
                                   +-- Có -> auth/TLS thành công?
                                              |
                                              +-- Không -> security
                                              |
                                              +-- Có -> queryNames/getAttribute
\`\`\`

Một phép thử cổng TCP chỉ xác nhận có dịch vụ nhận kết nối trên cổng được thử. Bằng chứng đầy đủ hơn phải gồm \`JMXConnectorFactory.connect\`, \`getMBeanServerConnection\`, \`queryNames\` và đọc một MBean ứng dụng cụ thể.

Đối với JConsole hoặc VisualVM, xác minh công cụ đang kết nối đúng JVM/deployment, đúng endpoint và có quyền truy cập cần thiết.

## 14. Kiểm thử tích hợp RMI connector

Kiểm thử ở môi trường cô lập có thể triển khai như sau:

1. Tạo \`MBeanServer\` riêng bằng \`MBeanServerFactory.createMBeanServer\`.
2. Tạo Standard MBean test với ObjectName duy nhất.
3. Tạo RMI registry ở một cổng local còn trống, bảo đảm connector sử dụng đúng registry.
4. Start \`JMXConnectorServer\`, cố định endpoint nếu test yêu cầu chạy qua firewall/container.
5. Kết nối bằng \`JMXConnectorFactory\` từ client test.
6. Dùng \`MBeanServerConnection.isRegistered\`, \`getAttribute\` và \`invoke\` để xác minh hợp đồng.
7. Đóng connector client, stop connector server, unregister MBean và giải phóng registry trong \`finally\`.

Để tránh các test song song tranh cổng, lựa chọn/đặt chỗ cổng một cách nguyên tử theo test fixture hoặc chạy test được cô lập. Việc tìm một cổng trống rồi đóng socket trước khi bind vẫn có race condition, vì process khác có thể chiếm cổng ở giữa hai bước.

Trong Spring integration test, xác minh exporter và connector nhận **cùng một MBeanServer bean**. Nếu sử dụng platform server để dễ tích hợp công cụ, đặt ObjectName có namespace riêng cho test.

## 15. Khi nào không nên dùng JMX RMI trực tiếp?

Trong môi trường đa vùng, nhiều lớp NAT hoặc hạ tầng chỉ chấp nhận HTTP, việc cấu hình RMI (registry port, endpoint port, advertised host) có thể phức tạp.

Có thể cân nhắc:
- **Micrometer/Prometheus** cho metrics và alerting.
- **Spring Boot Actuator** cho health/info và một số nhu cầu giám sát qua HTTP.
- **API quản trị nội bộ có xác thực và audit** khi cần lệnh nghiệp vụ.
- **Bridge JMX qua giao thức khác** trong mạng được bảo vệ nếu vẫn cần MBean.

Các lựa chọn này không thay thế hoàn toàn JMX: JMX hỗ trợ mô hình attribute, operation và notification phong phú. Cần chọn theo khả năng, cách vận hành mạng và tiêu chuẩn bảo mật.

## 16. Ghi nhớ

**RMI connector nối JMX client với MBeanServer qua một endpoint RMI.** Registry chỉ giúp tra cứu stub; endpoint thực tế có thể dùng địa chỉ/cổng khác nên phải kiểm tra cả hai. Với Spring, \`MBeanExporter\` quyết định bean nào trở thành MBean, còn connector quyết định server nào được truy cập từ xa. Một triển khai đáng tin cậy phải có wiring đúng, hostname/port quảng bá truy cập được, authentication/TLS phù hợp và lifecycle cleanup rõ ràng.
